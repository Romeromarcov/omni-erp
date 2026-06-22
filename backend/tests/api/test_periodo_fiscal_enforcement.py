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
