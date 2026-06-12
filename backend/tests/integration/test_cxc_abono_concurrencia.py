"""
TEST-4 (ampliación) — Race test de abonos a CxC (no sobre-abono).

Verifica que ``registrar_abono`` (que toma ``select_for_update`` sobre la
``CuentaPorCobrar``) serializa correctamente bajo concurrencia: si varios hilos
intentan abonar simultáneamente más de lo que resta del saldo, NUNCA se cobra de
más (la suma de abonos jamás supera el monto) y sólo tienen éxito los que caben.

Cierra el pendiente del plan en saldos CxC/CxP que dejaba ``TEST-4`` (hasta ahora
sólo cubría stock y correlativos fiscales). Mismo patrón que
``tests/integration/test_inventario_concurrencia.py``: requiere ``transaction=True`` para
que el commit de cada hilo sea visible a los demás y el lock funcione entre hilos.
"""

import threading
from decimal import Decimal

import pytest
from django.db import connections
from django.utils import timezone

pytestmark = pytest.mark.integration


@pytest.mark.django_db(transaction=True)
class TestAbonoCxCConcurrencia:
    def _crear_cliente(self, empresa):
        from apps.crm.models import Cliente

        return Cliente.objects.create(
            id_empresa=empresa,
            razon_social="Cliente Race CxC",
            rif="J-44444444-4",
            tipo_cliente="CREDITO",
            limite_credito=Decimal("100000.00"),
            dias_credito=30,
        )

    def test_no_sobre_abono_bajo_concurrencia(self, empresa_a, user_a):
        """
        Saldo = 1000. 5 hilos intentan abonar 400 c/u (total 2000 > 1000).
        Sólo 2 deben tener éxito (400+400=800 ≤ 1000; el 3º necesitaría 1200).
        Invariante crítica: la suma de abonos NUNCA supera el monto de la CxC.
        """
        from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar
        from apps.cuentas_por_cobrar.services import AbonoError, registrar_abono

        cliente = self._crear_cliente(empresa_a)
        cxc = CuentaPorCobrar.objects.create(
            cliente=cliente,
            empresa=empresa_a,
            monto=Decimal("1000.00"),
            fecha_emision=timezone.now().date(),
            fecha_vencimiento=timezone.now().date(),
            estado="pendiente",
            descripcion="CxC race test",
        )

        N_HILOS = 5
        MONTO = Decimal("400.00")
        exitos = []
        rechazos = []
        otros_errores = []
        lock = threading.Lock()

        def intentar_abono():
            try:
                registrar_abono(cxc=cxc, monto=MONTO, usuario=user_a)
                with lock:
                    exitos.append(1)
            except AbonoError:
                with lock:
                    rechazos.append(1)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    otros_errores.append(str(exc))
            finally:
                from django.db import connection as _conn

                _conn.close()

        hilos = [threading.Thread(target=intentar_abono) for _ in range(N_HILOS)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=15)
        connections.close_all()

        assert not otros_errores, f"Errores inesperados en hilos: {otros_errores}"

        total_abonado = sum(
            (a.monto for a in AbonoCxC.objects.filter(cuenta_por_cobrar=cxc)),
            Decimal("0"),
        )
        # Invariante anti-sobre-abono: jamás se cobra más que el monto.
        assert total_abonado <= cxc.monto, (
            f"¡SOBRE-ABONO! total={total_abonado} > monto={cxc.monto}"
        )
        # Exactamente 2 abonos caben (prueba la serialización, no sólo el tope).
        assert len(exitos) == 2, f"Esperados 2 éxitos, hubo {len(exitos)}"
        assert len(rechazos) == 3, f"Esperados 3 rechazos, hubo {len(rechazos)}"
        assert total_abonado == Decimal("800.00")

        cxc.refresh_from_db()
        assert cxc.estado == "parcial"
