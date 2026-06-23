"""
Enforcement de cierre de período fiscal (deuda #1 — auditoría 2026-06-21).

``PeriodoFiscal.esta_cerrado()`` existía pero ningún flujo de emisión lo
consultaba: el flag de cierre era cosmético y se podían emitir/modificar
documentos fiscales (factura, nota de crédito, devolución) en un período ya
cerrado → riesgo fiscal SENIAT.

Este módulo prueba el guard ``validar_periodo_abierto``:

- emitir factura fiscal en un período CERRADO → 400 (y nada se persiste);
- emitir en período ABIERTO (o sin registro de período) → 201;
- el cierre es por empresa (multi-tenant): un período cerrado de OTRA empresa
  no bloquea la emisión propia;
- la devolución (que emite nota de crédito) también respeta el cierre.
"""

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def cliente_pf(db, empresa_a):
    from apps.crm.models import Cliente

    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Período Fiscal",
        rif="J-55555555-5",
        tipo_cliente="CONTADO",
    )


@pytest.fixture
def producto_pf(db, empresa_a, moneda_usd):
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad", abreviatura="UN-PF", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(
        id_empresa=empresa_a, nombre_categoria="Cat Período Fiscal"
    )
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto Período Fiscal",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("100.00"),
        costo_promedio=Decimal("60.00"),
    )


def _nota_entregada(empresa, cliente, producto, numero="NV-PF-001"):
    from apps.ventas.models import DetalleNotaVenta, NotaVenta

    nota = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        numero_nota=numero,
        fecha_nota=timezone.now().date(),
        estado="ENTREGADA",
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nota,
        id_producto=producto,
        cantidad=Decimal("2"),
        precio_unitario=Decimal("100.00"),
        subtotal=Decimal("200.00"),
    )
    return nota


def _mapeo_factura(empresa):
    from apps.contabilidad.models import MapeoContable, PlanCuentas

    debe = PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta="PF-1201",
        nombre_cuenta="CxC Período Fiscal",
        tipo_cuenta="ACTIVO",
        naturaleza="DEUDORA",
        nivel=1,
    )
    haber = PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta="PF-4101",
        nombre_cuenta="Ingresos Período Fiscal",
        tipo_cuenta="INGRESO",
        naturaleza="ACREEDORA",
        nivel=1,
    )
    MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento="FACTURA_VENTA",
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla="FAC {numero}",
        activo=True,
    )


def _periodo(empresa, *, cerrado, fecha=None):
    """Crea el PeriodoFiscal del mes de ``fecha`` (hoy por defecto)."""
    from apps.fiscal.models import PeriodoFiscal

    fecha = fecha or timezone.localdate()
    return PeriodoFiscal.objects.create(
        id_empresa=empresa,
        año=fecha.year,
        mes=fecha.month,
        cerrado=cerrado,
        fecha_cierre=timezone.now() if cerrado else None,
    )


# ── Factura fiscal vs. cierre de período ──────────────────────────────────────


class TestEmitirFacturaPeriodoFiscal:
    def _url(self, nota):
        return f"/api/ventas/notas-venta/{nota.id_nota_venta}/convertir-factura/"

    def test_periodo_cerrado_rechaza_emision(
        self, client_a, empresa_a, cliente_pf, producto_pf
    ):
        from apps.ventas.models import FacturaFiscal, NotaVenta

        _mapeo_factura(empresa_a)
        _periodo(empresa_a, cerrado=True)
        nota = _nota_entregada(empresa_a, cliente_pf, producto_pf)

        resp = client_a.post(self._url(nota), {}, format="json")

        assert resp.status_code == 400, resp.content
        assert "cerrado" in str(resp.data).lower()
        # Nada se persiste: ni factura ni cambio de estado de la nota.
        assert not FacturaFiscal.objects.filter(id_nota_venta_origen=nota).exists()
        nota = NotaVenta.objects.get(pk=nota.pk)
        assert nota.estado == "ENTREGADA"
        assert nota.convertido_a_factura is False

    def test_periodo_abierto_permite_emision(
        self, client_a, empresa_a, cliente_pf, producto_pf
    ):
        from apps.ventas.models import FacturaFiscal

        _mapeo_factura(empresa_a)
        _periodo(empresa_a, cerrado=False)
        nota = _nota_entregada(empresa_a, cliente_pf, producto_pf, numero="NV-PF-002")

        resp = client_a.post(self._url(nota), {}, format="json")

        assert resp.status_code == 201, resp.content
        factura = FacturaFiscal.objects.get(pk=resp.data["id_factura"])
        assert factura.estado == "EMITIDA"

    def test_sin_periodo_registrado_permite_emision(
        self, client_a, empresa_a, cliente_pf, producto_pf
    ):
        # Sin fila de PeriodoFiscal el período se considera abierto (default).
        from apps.ventas.models import FacturaFiscal

        _mapeo_factura(empresa_a)
        nota = _nota_entregada(empresa_a, cliente_pf, producto_pf, numero="NV-PF-003")

        resp = client_a.post(self._url(nota), {}, format="json")

        assert resp.status_code == 201, resp.content
        assert FacturaFiscal.objects.filter(id_nota_venta_origen=nota).exists()

    def test_cierre_es_por_empresa_multitenant(
        self, client_a, empresa_a, empresa_b, cliente_pf, producto_pf
    ):
        # R-CODE-1: un período cerrado de OTRA empresa no bloquea la emisión de A.
        from apps.ventas.models import FacturaFiscal

        _mapeo_factura(empresa_a)
        _periodo(empresa_b, cerrado=True)  # B cerrado el mismo mes
        nota = _nota_entregada(empresa_a, cliente_pf, producto_pf, numero="NV-PF-004")

        resp = client_a.post(self._url(nota), {}, format="json")

        assert resp.status_code == 201, resp.content
        assert FacturaFiscal.objects.filter(id_nota_venta_origen=nota).exists()


# ── Devolución (nota de crédito) vs. cierre de período ─────────────────────────


class TestDevolucionPeriodoFiscal:
    def test_periodo_cerrado_rechaza_devolucion(
        self, empresa_a, user_a, cliente_pf, producto_pf, metodo_efectivo
    ):
        from apps.ventas.services import VentaError, registrar_devolucion_pos

        _periodo(empresa_a, cerrado=True)
        nota = _nota_entregada(empresa_a, cliente_pf, producto_pf, numero="NV-PF-005")
        linea = nota.detalles.first()

        # El guard de período fiscal corre al inicio del flujo: aún sin sesión de
        # caja ni almacén válidos, la emisión de la nota de crédito se bloquea.
        with pytest.raises(VentaError, match="cerrado"):
            registrar_devolucion_pos(
                nota_venta=nota,
                lineas=[{"id_detalle": str(linea.id_detalle_nota_venta), "cantidad": "1"}],
                almacen=None,
                usuario=user_a,
                metodo_pago=metodo_efectivo,
            )


# ── Compras (recepción / factura de compra) vs. cierre de período ──────────────
#
# El ciclo de compras también postea asientos contables en un período fiscal:
#   - registrar_recepcion()      → AsientoContable(RECEPCION_MERCANCIA)
#   - registrar_factura_compra() → AsientoContable(FACTURA_COMPRA)
# Ambos flujos deben respetar el cierre igual que la emisión de ventas.


def _proveedor_pf(empresa):
    from apps.proveedores.models import Proveedor

    return Proveedor.objects.create(
        id_empresa=empresa,
        razon_social="Proveedor Período Fiscal S.A.",
        rif="J-66666666-6",
    )


def _almacen_pf(empresa):
    from apps.almacenes.models import Almacen

    return Almacen.objects.create(
        id_empresa=empresa,
        nombre_almacen="Almacén Período Fiscal",
        codigo_almacen="AC-PF",
    )


def _orden_aprobada_pf(empresa, proveedor, numero="OC-PF-001"):
    from apps.compras.models import OrdenCompra

    return OrdenCompra.objects.create(
        id_empresa=empresa,
        id_proveedor=proveedor,
        numero_orden=numero,
        fecha_orden=timezone.now().date(),
        estado="APROBADA",
    )


def _recepcion_directa_pf(empresa, orden, monto="100.00"):
    # Crea la RecepcionMercancia por ORM (sin pasar por el servicio guardado),
    # para poder probar el guard de registrar_factura_compra de forma aislada.
    from apps.compras.models import RecepcionMercancia

    return RecepcionMercancia.objects.create(
        id_empresa=empresa,
        id_orden_compra=orden,
        fecha_recepcion=timezone.now().date(),
        monto_total=Decimal(monto),
    )


class TestRecepcionPeriodoFiscal:
    def _items(self, producto):
        return [{"producto": producto, "cantidad": "4", "costo_unitario": "25.00"}]

    def test_periodo_cerrado_rechaza_recepcion(self, empresa_a, user_a, producto_pf):
        from apps.compras.models import RecepcionMercancia
        from apps.compras.services import CompraError, registrar_recepcion

        _periodo(empresa_a, cerrado=True)
        proveedor = _proveedor_pf(empresa_a)
        almacen = _almacen_pf(empresa_a)
        orden = _orden_aprobada_pf(empresa_a, proveedor)

        with pytest.raises(CompraError, match="cerrado"):
            registrar_recepcion(orden, almacen, user_a, self._items(producto_pf))

        # Nada se persiste (la transacción atómica revierte).
        assert not RecepcionMercancia.objects.filter(id_orden_compra=orden).exists()

    def test_periodo_abierto_permite_recepcion(self, empresa_a, user_a, producto_pf):
        from apps.compras.services import registrar_recepcion

        _periodo(empresa_a, cerrado=False)
        proveedor = _proveedor_pf(empresa_a)
        almacen = _almacen_pf(empresa_a)
        orden = _orden_aprobada_pf(empresa_a, proveedor, numero="OC-PF-002")

        resultado = registrar_recepcion(orden, almacen, user_a, self._items(producto_pf))
        assert resultado["recepcion"].monto_total == Decimal("100.00")

    def test_cierre_es_por_empresa_multitenant(
        self, empresa_a, empresa_b, user_a, producto_pf
    ):
        # R-CODE-1: período cerrado de OTRA empresa no bloquea la recepción de A.
        from apps.compras.services import registrar_recepcion

        _periodo(empresa_b, cerrado=True)
        proveedor = _proveedor_pf(empresa_a)
        almacen = _almacen_pf(empresa_a)
        orden = _orden_aprobada_pf(empresa_a, proveedor, numero="OC-PF-003")

        resultado = registrar_recepcion(orden, almacen, user_a, self._items(producto_pf))
        assert resultado["recepcion"] is not None


class TestFacturaCompraPeriodoFiscal:
    def test_periodo_cerrado_rechaza_factura(self, empresa_a):
        from apps.compras.models import FacturaCompra
        from apps.compras.services import CompraError, registrar_factura_compra

        proveedor = _proveedor_pf(empresa_a)
        orden = _orden_aprobada_pf(empresa_a, proveedor, numero="OC-PF-004")
        recepcion = _recepcion_directa_pf(empresa_a, orden)
        _periodo(empresa_a, cerrado=True)

        with pytest.raises(CompraError, match="cerrado"):
            registrar_factura_compra(recepcion, numero_factura="FC-PF-001")

        assert not FacturaCompra.objects.filter(id_recepcion=recepcion).exists()

    def test_periodo_abierto_permite_factura(self, empresa_a):
        from apps.compras.services import registrar_factura_compra

        proveedor = _proveedor_pf(empresa_a)
        orden = _orden_aprobada_pf(empresa_a, proveedor, numero="OC-PF-005")
        recepcion = _recepcion_directa_pf(empresa_a, orden)
        _periodo(empresa_a, cerrado=False)

        resultado = registrar_factura_compra(recepcion, numero_factura="FC-PF-002")
        assert resultado["factura"].numero_factura == "FC-PF-002"
