"""
TEST-4 — Race test de reserva de stock (no overselling).

Verifica que `reservar_stock` (que usa `select_for_update`) serializa correctamente
bajo concurrencia: si N hilos intentan reservar simultáneamente más stock del que hay,
NUNCA se compromete más de lo disponible (no hay sobreventa) y solo tienen éxito los
que caben.

Igual que test_fiscal_concurrencia: requiere transaction=True para que los commits de
cada hilo sean visibles a los demás y el lock SELECT FOR UPDATE funcione entre hilos.
"""

import threading
from decimal import Decimal

import pytest
from django.db import connections

from tests.factories import AlmacenFactory, EmpresaFactory, ProductoFactory

pytestmark = pytest.mark.integration


@pytest.mark.django_db(transaction=True)
class TestReservaStockConcurrencia:
    def test_no_sobreventa_bajo_concurrencia(self):
        """
        Stock disponible = 10. 5 hilos intentan reservar 4 c/u (total 20 > 10).
        Solo 2 deben tener éxito (4+4=8 ≤ 10; el 3º necesitaría 12 > 10).
        Invariante crítica: cantidad_comprometida NUNCA supera cantidad_disponible.
        """
        from apps.inventario.models import StockActual
        from apps.inventario.services import StockInsuficienteError, reservar_stock

        empresa = EmpresaFactory()
        producto = ProductoFactory(id_empresa=empresa)
        almacen = AlmacenFactory(id_empresa=empresa)
        StockActual.objects.create(
            id_empresa=empresa,
            id_producto=producto,
            id_variante=None,
            id_almacen=almacen,
            cantidad_disponible=Decimal("10"),
            cantidad_comprometida=Decimal("0"),
        )

        N_HILOS = 5
        CANTIDAD = Decimal("4")
        exitos = []
        insuficientes = []
        otros_errores = []
        lock = threading.Lock()

        def intentar_reserva():
            try:
                reservar_stock(empresa, producto, None, almacen, CANTIDAD)
                with lock:
                    exitos.append(1)
            except StockInsuficienteError:
                with lock:
                    insuficientes.append(1)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    otros_errores.append(str(exc))
            finally:
                from django.db import connection as _conn
                _conn.close()

        hilos = [threading.Thread(target=intentar_reserva) for _ in range(N_HILOS)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=15)
        connections.close_all()

        assert not otros_errores, f"Errores inesperados en hilos: {otros_errores}"

        stock = StockActual.objects.get(id_producto=producto, id_almacen=almacen, id_variante=None)

        # Invariante anti-sobreventa: lo comprometido nunca supera lo disponible.
        assert stock.cantidad_comprometida <= stock.cantidad_disponible, (
            f"¡SOBREVENTA! comprometida={stock.cantidad_comprometida} > "
            f"disponible={stock.cantidad_disponible}"
        )
        # Exactamente 2 reservas caben (prueba la serialización, no solo el no-oversell).
        assert len(exitos) == 2, f"Esperados 2 éxitos, hubo {len(exitos)}"
        assert len(insuficientes) == 3, f"Esperados 3 rechazos, hubo {len(insuficientes)}"
        assert stock.cantidad_comprometida == Decimal("8")
