"""
Gaps E2E (PR #76) — endpoints de conversión del ciclo de ventas.

El frontend ya llamaba a estos endpoints y el backend no los tenía (404):

- POST /api/ventas/pedidos/{id}/convertir-nota-venta/
    Crea la NotaVenta BORRADOR desde un pedido APROBADO (copia detalles,
    marca convertido_a_nota_venta). Delegado en convertir_pedido_a_nota_venta.
- POST /api/ventas/notas-venta/{id}/convertir-factura/
    Emite la FacturaFiscal desde una nota ENTREGADA. Delegado en
    emitir_factura_fiscal (asiento R-CODE-11 + CxC única BUG-A4).

Cobertura:
- camino feliz de ambas conversiones (estado, detalles copiados, enlaces)
- estados inválidos → 400 con mensaje de dominio
- doble conversión → 400 (no duplica)
- aislamiento multi-tenant → 404 para documentos de otra empresa (R-CODE-1)
"""

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


@pytest.fixture
def cliente_conv(db, empresa_a):
    from apps.crm.models import Cliente

    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Conversiones",
        rif="J-44444444-4",
        tipo_cliente="CONTADO",
    )


@pytest.fixture
def producto_conv(db, empresa_a, moneda_usd):
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad", abreviatura="UN-CONV", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(
        id_empresa=empresa_a, nombre_categoria="Cat Conversiones"
    )
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto Conversiones",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("100.00"),
        costo_promedio=Decimal("60.00"),
    )


def _pedido(empresa, cliente, producto, estado="APROBADO", numero="PED-CONV-001", con_detalle=True):
    from apps.ventas.models import DetallePedido, Pedido

    pedido = Pedido.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        numero_pedido=numero,
        fecha_pedido=timezone.now().date(),
        estado=estado,
        observaciones="Obs del pedido",
    )
    if con_detalle:
        DetallePedido.objects.create(
            id_pedido=pedido,
            id_producto=producto,
            cantidad=Decimal("3"),
            precio_unitario=Decimal("100.00"),
            subtotal=Decimal("300.00"),
            observaciones="Línea 1",
        )
    return pedido


def _nota_entregada(empresa, cliente, producto, numero="NV-CONV-001"):
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
        codigo_cuenta="CONV-1201",
        nombre_cuenta="CxC Conversión",
        tipo_cuenta="ACTIVO",
        naturaleza="DEUDORA",
        nivel=1,
    )
    haber = PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta="CONV-4101",
        nombre_cuenta="Ingresos Conversión",
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


# ── Pedido → Nota de Venta ────────────────────────────────────────────────────


class TestConvertirPedidoANotaVenta:
    def _url(self, pedido):
        return f"/api/ventas/pedidos/{pedido.id_pedido}/convertir-nota-venta/"

    def test_pedido_aprobado_crea_nota_borrador_con_detalles(
        self, client_a, empresa_a, cliente_conv, producto_conv
    ):
        from apps.ventas.models import NotaVenta

        pedido = _pedido(empresa_a, cliente_conv, producto_conv)
        resp = client_a.post(self._url(pedido), {}, format="json")
        assert resp.status_code == 201, resp.content

        nota = NotaVenta.objects.get(pk=resp.data["id_nota_venta"])
        assert nota.estado == "BORRADOR"
        assert nota.id_pedido_origen_id == pedido.id_pedido
        assert nota.id_empresa_id == empresa_a.pk
        detalles = list(nota.detalles.all())
        assert len(detalles) == 1
        assert detalles[0].cantidad == Decimal("3")
        assert detalles[0].precio_unitario == Decimal("100.00")
        assert detalles[0].subtotal == Decimal("300.00")

        pedido.refresh_from_db()
        assert pedido.convertido_a_nota_venta is True
        assert pedido.id_nota_venta_resultante_id == nota.id_nota_venta

    def test_doble_conversion_no_duplica(self, client_a, empresa_a, cliente_conv, producto_conv):
        from apps.ventas.models import NotaVenta

        pedido = _pedido(empresa_a, cliente_conv, producto_conv, numero="PED-CONV-002")
        assert client_a.post(self._url(pedido), {}, format="json").status_code == 201
        resp2 = client_a.post(self._url(pedido), {}, format="json")
        assert resp2.status_code == 400
        assert NotaVenta.objects.filter(id_pedido_origen=pedido).count() == 1

    def test_pedido_pendiente_rechazado(self, client_a, empresa_a, cliente_conv, producto_conv):
        pedido = _pedido(
            empresa_a, cliente_conv, producto_conv, estado="PENDIENTE", numero="PED-CONV-003"
        )
        resp = client_a.post(self._url(pedido), {}, format="json")
        assert resp.status_code == 400
        assert "APROBADOS" in str(resp.data)

    def test_pedido_sin_detalles_rechazado(self, client_a, empresa_a, cliente_conv, producto_conv):
        pedido = _pedido(
            empresa_a, cliente_conv, producto_conv, numero="PED-CONV-004", con_detalle=False
        )
        resp = client_a.post(self._url(pedido), {}, format="json")
        assert resp.status_code == 400

    def test_aislamiento_multitenant(self, client_b, empresa_a, cliente_conv, producto_conv):
        # R-CODE-1: usuario de empresa B no ve (404) un pedido de empresa A.
        pedido = _pedido(empresa_a, cliente_conv, producto_conv, numero="PED-CONV-005")
        resp = client_b.post(self._url(pedido), {}, format="json")
        assert resp.status_code == 404
        pedido.refresh_from_db()
        assert pedido.convertido_a_nota_venta is False


# ── Nota de Venta → Factura Fiscal ────────────────────────────────────────────


class TestConvertirNotaVentaAFactura:
    def _url(self, nota):
        return f"/api/ventas/notas-venta/{nota.id_nota_venta}/convertir-factura/"

    def test_nota_entregada_emite_factura(self, client_a, empresa_a, cliente_conv, producto_conv):
        from apps.ventas.models import FacturaFiscal

        _mapeo_factura(empresa_a)
        nota = _nota_entregada(empresa_a, cliente_conv, producto_conv)
        resp = client_a.post(self._url(nota), {}, format="json")
        assert resp.status_code == 201, resp.content

        factura = FacturaFiscal.objects.get(pk=resp.data["id_factura"])
        assert factura.estado == "EMITIDA"
        assert factura.base_imponible == Decimal("200.00")
        assert factura.id_nota_venta_origen_id == nota.id_nota_venta

        nota.refresh_from_db()
        assert nota.estado == "FACTURADA"
        assert nota.convertido_a_factura is True
        assert nota.id_factura_resultante_id == factura.id_factura

    def test_nota_borrador_rechazada(self, client_a, empresa_a, cliente_conv, producto_conv):
        from apps.ventas.models import NotaVenta

        _mapeo_factura(empresa_a)
        nota = _nota_entregada(empresa_a, cliente_conv, producto_conv, numero="NV-CONV-002")
        nota.estado = "BORRADOR"
        nota.save(update_fields=["estado"])
        resp = client_a.post(self._url(nota), {}, format="json")
        assert resp.status_code == 400
        assert "ENTREGADA" in str(resp.data)
        assert not NotaVenta.objects.get(pk=nota.pk).convertido_a_factura

    def test_doble_conversion_rechazada(self, client_a, empresa_a, cliente_conv, producto_conv):
        from apps.ventas.models import FacturaFiscal

        _mapeo_factura(empresa_a)
        nota = _nota_entregada(empresa_a, cliente_conv, producto_conv, numero="NV-CONV-003")
        assert client_a.post(self._url(nota), {}, format="json").status_code == 201
        resp2 = client_a.post(self._url(nota), {}, format="json")
        assert resp2.status_code == 400
        assert FacturaFiscal.objects.filter(id_nota_venta_origen=nota).count() == 1

    def test_aislamiento_multitenant(self, client_b, empresa_a, cliente_conv, producto_conv):
        _mapeo_factura(empresa_a)
        nota = _nota_entregada(empresa_a, cliente_conv, producto_conv, numero="NV-CONV-004")
        resp = client_b.post(self._url(nota), {}, format="json")
        assert resp.status_code == 404
