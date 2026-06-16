"""
Integración 1.G — flujo completo de venta → despacho/entrega.

Cubre el ciclo real con stock:

  carga inicial → Pedido → confirmar_pedido (reserva) → convertir a NotaVenta →
  entregar_nota_venta (sale stock físico, DESPACHO_VENTA) →
  crear_despacho_desde_nota_venta (NO toca stock) → EN_RUTA → ENTREGADO

y las invariantes de dominio:
  - el despacho NUNCA mueve inventario (decisión 1.G documentada en la app);
  - sobre-despacho rechazado (service → DespachoError; API → 400);
  - despacho parcial acumulado hasta agotar el cupo;
  - estados de nota no despachables rechazados.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.despacho.models import Despacho
from apps.despacho.services import (
    DespachoError,
    cantidades_pendientes_por_producto,
    crear_despacho_desde_nota_venta,
    transicionar_despacho,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Escenario: venta real con stock ───────────────────────────────────────────


@pytest.fixture
def escenario(empresa_a, moneda_usd, user_a):
    """Venta completa lista para entregar: pedido aprobado → nota BORRADOR."""
    from apps.almacenes.models import Almacen
    from apps.crm.models import Cliente
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
    from apps.inventario.services import registrar_movimiento
    from apps.ventas.models import DetallePedido, Pedido

    cliente = Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Distribuidora Cliente Flujo",
        rif="J-77777777-7",
        tipo_cliente="CONTADO",
    )
    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Caja", abreviatura="CJ-FLJ", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(
        id_empresa=empresa_a, nombre_categoria="Cat Flujo"
    )
    producto = Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Harina 1kg",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("12.50"),
    )
    almacen = Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Galpón Central", codigo_almacen="GAL-FLJ"
    )
    # Carga inicial: 50 unidades.
    registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="ENTRADA",
        producto=producto,
        cantidad=Decimal("50.0000"),
        almacen_destino=almacen,
        usuario=user_a,
        observaciones="Carga inicial flujo despacho",
    )
    pedido = Pedido.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente,
        numero_pedido="PED-FLJ-001",
        fecha_pedido=timezone.now().date(),
        estado="PENDIENTE",
    )
    DetallePedido.objects.create(
        id_pedido=pedido,
        id_producto=producto,
        cantidad=Decimal("10.0000"),
        precio_unitario=Decimal("12.50"),
        subtotal=Decimal("125.00"),
    )
    return {
        "cliente": cliente,
        "producto": producto,
        "almacen": almacen,
        "pedido": pedido,
        "unidad": unidad,
    }


def _stock(empresa, producto, almacen):
    from apps.inventario.models import StockActual

    stock = StockActual.objects.filter(
        id_empresa=empresa, id_producto=producto, id_almacen=almacen
    ).first()
    return stock.cantidad_disponible if stock else Decimal("0")


def _entregar_venta(escenario, empresa_a, user_a):
    """Confirma el pedido, lo convierte a nota y la entrega (sale stock)."""
    from apps.ventas.services import (
        confirmar_pedido,
        convertir_pedido_a_nota_venta,
        entregar_nota_venta,
    )

    confirmar_pedido(escenario["pedido"], escenario["almacen"], user_a)
    nota = convertir_pedido_a_nota_venta(escenario["pedido"], user_a)
    entregar_nota_venta(nota, escenario["almacen"], user_a)
    nota.refresh_from_db()
    return nota


# ── Flujo completo ────────────────────────────────────────────────────────────


class TestFlujoCompleto:
    def test_venta_a_despacho_entregado_sin_tocar_stock(self, escenario, empresa_a, user_a):
        from apps.inventario.models import MovimientoInventario

        producto, almacen = escenario["producto"], escenario["almacen"]

        nota = _entregar_venta(escenario, empresa_a, user_a)
        assert nota.estado == "ENTREGADA"
        # entregar_nota_venta descontó las 10 vendidas: 50 → 40.
        stock_tras_venta = _stock(empresa_a, producto, almacen)
        assert stock_tras_venta == Decimal("40.0000")
        movimientos_tras_venta = MovimientoInventario.objects.count()

        # El despacho hereda venta/pedido y NO toca stock ni movimientos.
        despacho = crear_despacho_desde_nota_venta(
            nota,
            almacen,
            user_a,
            direccion_entrega="Calle 5, Maracay",
        )
        assert despacho.estado_despacho == Despacho.ESTADO_PENDIENTE
        assert despacho.id_nota_venta == nota
        assert despacho.id_pedido == escenario["pedido"]
        assert despacho.numero_despacho  # correlativo asignado
        detalles = list(despacho.detalles.all())
        assert len(detalles) == 1
        assert detalles[0].cantidad_despachada == Decimal("10.0000")
        assert detalles[0].id_unidad_medida == escenario["unidad"]

        # Transiciones con timestamps.
        despacho = transicionar_despacho(despacho, Despacho.ESTADO_EN_RUTA, user_a)
        assert despacho.fecha_en_ruta is not None
        despacho = transicionar_despacho(
            despacho, Despacho.ESTADO_ENTREGADO, user_a, receptor="Sr. Bodega"
        )
        assert despacho.estado_despacho == Despacho.ESTADO_ENTREGADO
        assert despacho.fecha_entrega_real is not None
        assert despacho.documento_json["entrega"]["receptor"] == "Sr. Bodega"

        # Invariante 1.G: el despacho no movió inventario.
        assert _stock(empresa_a, producto, almacen) == stock_tras_venta
        assert MovimientoInventario.objects.count() == movimientos_tras_venta

    def test_despacho_parcial_hasta_agotar_y_sobre_despacho(
        self, escenario, empresa_a, user_a
    ):
        nota = _entregar_venta(escenario, empresa_a, user_a)
        producto = escenario["producto"]

        d1 = crear_despacho_desde_nota_venta(
            nota,
            escenario["almacen"],
            user_a,
            direccion_entrega="Sucursal Norte",
            lineas=[{"id_producto": producto.id_producto, "cantidad": Decimal("6")}],
        )
        assert d1.detalles.get().cantidad_despachada == Decimal("6")
        assert cantidades_pendientes_por_producto(nota) == {
            producto.id_producto: Decimal("4.0000")
        }

        # Sobre-despacho del remanente → error de dominio, nada persiste.
        with pytest.raises(DespachoError, match="Sobre-despacho"):
            crear_despacho_desde_nota_venta(
                nota,
                escenario["almacen"],
                user_a,
                direccion_entrega="Sucursal Norte",
                lineas=[{"id_producto": producto.id_producto, "cantidad": Decimal("5")}],
            )
        assert Despacho.objects.count() == 1

        d2 = crear_despacho_desde_nota_venta(
            nota, escenario["almacen"], user_a, direccion_entrega="Sucursal Norte"
        )
        assert d2.detalles.get().cantidad_despachada == Decimal("4.0000")

        with pytest.raises(DespachoError, match="completamente despachada"):
            crear_despacho_desde_nota_venta(
                nota, escenario["almacen"], user_a, direccion_entrega="Sucursal Norte"
            )

    def test_sobre_despacho_via_api_400(self, escenario, empresa_a, user_a, client_a):
        """El mismo invariante, extremo a extremo por la API → 400."""
        nota = _entregar_venta(escenario, empresa_a, user_a)
        resp = client_a.post(
            "/api/despacho/despachos/desde-nota-venta/",
            {
                "id_nota_venta": str(nota.id_nota_venta),
                "almacen_id": str(escenario["almacen"].id_almacen),
                "direccion_entrega": "Av. Las Delicias",
                "lineas": [
                    {
                        "id_producto": str(escenario["producto"].id_producto),
                        "cantidad": "10.5",
                    }
                ],
            },
            format="json",
        )
        assert resp.status_code == 400
        assert "Sobre-despacho" in str(resp.data)
        assert Despacho.objects.count() == 0

    def test_nota_no_entregada_no_despachable(self, escenario, empresa_a, user_a):
        from apps.ventas.services import confirmar_pedido, convertir_pedido_a_nota_venta

        confirmar_pedido(escenario["pedido"], escenario["almacen"], user_a)
        nota = convertir_pedido_a_nota_venta(escenario["pedido"], user_a)  # BORRADOR
        with pytest.raises(DespachoError, match="ENTREGADAS o FACTURADAS"):
            crear_despacho_desde_nota_venta(
                nota, escenario["almacen"], user_a, direccion_entrega="X"
            )

    def test_devuelto_libera_cupo_y_es_terminal(self, escenario, empresa_a, user_a):
        nota = _entregar_venta(escenario, empresa_a, user_a)
        despacho = crear_despacho_desde_nota_venta(
            nota, escenario["almacen"], user_a, direccion_entrega="Zona Sur"
        )
        despacho = transicionar_despacho(despacho, Despacho.ESTADO_EN_RUTA, user_a)
        despacho = transicionar_despacho(
            despacho, Despacho.ESTADO_DEVUELTO, user_a, motivo="Local cerrado"
        )
        assert despacho.fecha_devolucion is not None
        assert despacho.documento_json["devolucion"]["motivo"] == "Local cerrado"

        # El cupo quedó libre: se puede despachar de nuevo el total.
        d2 = crear_despacho_desde_nota_venta(
            nota, escenario["almacen"], user_a, direccion_entrega="Zona Sur (reintento)"
        )
        assert d2.detalles.get().cantidad_despachada == Decimal("10.0000")

        # DEVUELTO es terminal.
        with pytest.raises(DespachoError, match="Transición inválida"):
            transicionar_despacho(despacho, Despacho.ESTADO_EN_RUTA, user_a)

    def test_almacen_de_otra_empresa_rechazado(self, escenario, empresa_a, empresa_b, user_a):
        from apps.almacenes.models import Almacen

        nota = _entregar_venta(escenario, empresa_a, user_a)
        almacen_b = Almacen.objects.create(
            id_empresa=empresa_b, nombre_almacen="Galpón B", codigo_almacen="GAL-B"
        )
        with pytest.raises(DespachoError, match="no pertenece a la empresa"):
            crear_despacho_desde_nota_venta(
                nota, almacen_b, user_a, direccion_entrega="Cruce de empresas"
            )

    def test_entregar_sin_receptor_y_cancelar_sin_motivo(self, escenario, empresa_a, user_a):
        nota = _entregar_venta(escenario, empresa_a, user_a)
        despacho = crear_despacho_desde_nota_venta(
            nota, escenario["almacen"], user_a, direccion_entrega="Centro"
        )
        with pytest.raises(DespachoError, match="motivo"):
            transicionar_despacho(despacho, Despacho.ESTADO_CANCELADO, user_a)
        despacho = transicionar_despacho(despacho, Despacho.ESTADO_EN_RUTA, user_a)
        with pytest.raises(DespachoError, match="receptor"):
            transicionar_despacho(despacho, Despacho.ESTADO_ENTREGADO, user_a)
