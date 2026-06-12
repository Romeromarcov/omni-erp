"""
Backfill de cobertura — apps/ventas/mcp.py (plan "Cero Dudas", COV/ventas).

Herramientas MCP del dominio ventas (ADR-003), llamadas directo como funciones
con CapabilityToken reales (patrón de ``test_mcp_server_scope.py``):

- ``ventas_get_cotizacion``: happy path con detalles, no encontrada, scope
  faltante, empresa_id ≠ tenant del token y aislamiento cross-tenant.
- ``ventas_get_notas_venta``: listado, filtro por estado, límite.
- ``ventas_get_facturas``: listado, filtro por estado, campos devueltos.
- Export ``MCP_TOOLS`` para el auto-discovery del servidor.
"""
import datetime
import uuid
from decimal import Decimal

import pytest

from apps.core.models import CapabilityToken
from apps.ventas.mcp import (
    MCP_TOOLS,
    ventas_get_cotizacion,
    ventas_get_facturas,
    ventas_get_notas_venta,
)
from apps.ventas.models import (
    Cotizacion,
    DetalleCotizacion,
    FacturaFiscal,
    NotaVenta,
)

pytestmark = pytest.mark.django_db

HOY = datetime.date(2026, 6, 9)


def _token(empresa, scopes, *, activo=True, expires_at=None, creado_por=None):
    return CapabilityToken.objects.create(
        empresa=empresa,
        nombre="tok-ventas-test",
        scopes=scopes,
        activo=activo,
        expires_at=expires_at,
        creado_por=creado_por,
    )


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cliente(db, empresa_a):
    from apps.crm.models import Cliente

    return Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Cliente MCP", rif="J-44444444-4"
    )


@pytest.fixture
def producto(db, empresa_a, moneda_usd):
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad", abreviatura="UN-MCP", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(
        id_empresa=empresa_a, nombre_categoria="General MCP"
    )
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto MCP",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
    )


@pytest.fixture
def cotizacion(db, empresa_a, cliente, producto, moneda_usd):
    cot = Cotizacion.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente,
        numero_cotizacion="COT-MCP-001",
        fecha_cotizacion=HOY,
        fecha_vencimiento=HOY + datetime.timedelta(days=10),
        estado="ENVIADA",
        monto_total=Decimal("75.0000"),
        id_moneda=moneda_usd,
    )
    DetalleCotizacion.objects.create(
        id_cotizacion=cot,
        id_producto=producto,
        cantidad=Decimal("3.0000"),
        precio_unitario=Decimal("25.0000"),
        subtotal=Decimal("75.0000"),
    )
    return cot


@pytest.fixture
def notas_venta(db, empresa_a, cliente):
    n1 = NotaVenta.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente,
        numero_nota="NV-MCP-001",
        fecha_nota=HOY,
        estado="BORRADOR",
    )
    n2 = NotaVenta.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente,
        numero_nota="NV-MCP-002",
        fecha_nota=HOY + datetime.timedelta(days=1),
        estado="ENTREGADA",
    )
    return [n1, n2]


@pytest.fixture
def facturas(db, empresa_a, cliente, moneda_usd):
    f1 = FacturaFiscal.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente,
        numero_control="MC-001",
        numero_factura="FAC-MCP-001",
        fecha_emision=HOY,
        monto_total=Decimal("116.0000"),
        id_moneda=moneda_usd,
        estado="EMITIDA",
    )
    f2 = FacturaFiscal.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente,
        numero_control="MC-002",
        numero_factura="FAC-MCP-002",
        fecha_emision=HOY,
        monto_total=Decimal("58.0000"),
        id_moneda=moneda_usd,
        estado="ANULADA",
    )
    return [f1, f2]


# ── ventas_get_cotizacion ─────────────────────────────────────────────────────

class TestGetCotizacion:
    def test_devuelve_detalle_completo(self, empresa_a, cotizacion):
        tok = _token(empresa_a, ["ventas:read"])
        res = ventas_get_cotizacion(
            str(tok.token), str(empresa_a.id_empresa), str(cotizacion.id_cotizacion)
        )
        assert res["id_cotizacion"] == str(cotizacion.id_cotizacion)
        assert res["numero"] == "COT-MCP-001"
        assert res["cliente"] == "Cliente MCP"
        assert res["estado"] == "ENVIADA"
        assert res["fecha"] == "2026-06-09"
        assert len(res["detalles"]) == 1
        det = res["detalles"][0]
        assert det["producto"] == "Producto MCP"
        assert det["cantidad"] == 3.0
        # M-BUG-1: precio/subtotal salen como Decimal (nunca float)
        assert det["precio_unitario"] == Decimal("25.0000")
        assert det["subtotal"] == Decimal("75.0000")

    def test_no_encontrada_devuelve_error(self, empresa_a):
        tok = _token(empresa_a, ["ventas:read"])
        res = ventas_get_cotizacion(
            str(tok.token), str(empresa_a.id_empresa), str(uuid.uuid4())
        )
        assert "error" in res

    def test_scope_faltante_lanza_permissionerror(self, empresa_a, cotizacion):
        tok = _token(empresa_a, ["crm:read"])  # falta ventas:read
        with pytest.raises(PermissionError):
            ventas_get_cotizacion(
                str(tok.token), str(empresa_a.id_empresa), str(cotizacion.id_cotizacion)
            )

    def test_empresa_distinta_al_token_lanza_permissionerror(
        self, empresa_a, empresa_b, cotizacion
    ):
        tok = _token(empresa_a, ["ventas:read"])
        with pytest.raises(PermissionError):
            ventas_get_cotizacion(
                str(tok.token), str(empresa_b.id_empresa), str(cotizacion.id_cotizacion)
            )

    def test_cross_tenant_no_filtra_datos(self, empresa_b, cotizacion):
        """Token de B con empresa_id de B no puede leer la cotización de A."""
        tok_b = _token(empresa_b, ["ventas:read"])
        res = ventas_get_cotizacion(
            str(tok_b.token), str(empresa_b.id_empresa), str(cotizacion.id_cotizacion)
        )
        assert "error" in res

    def test_token_invalido_lanza_permissionerror(self, empresa_a, cotizacion):
        with pytest.raises(PermissionError):
            ventas_get_cotizacion(
                "no-es-uuid", str(empresa_a.id_empresa), str(cotizacion.id_cotizacion)
            )


# ── ventas_get_notas_venta ────────────────────────────────────────────────────

class TestGetNotasVenta:
    def test_lista_todas_ordenadas_por_fecha_desc(self, empresa_a, notas_venta):
        tok = _token(empresa_a, ["ventas:read"])
        res = ventas_get_notas_venta(str(tok.token), str(empresa_a.id_empresa))
        assert [n["numero"] for n in res] == ["NV-MCP-002", "NV-MCP-001"]
        assert res[0]["cliente"] == "Cliente MCP"
        assert res[0]["estado"] == "ENTREGADA"

    def test_filtra_por_estado(self, empresa_a, notas_venta):
        tok = _token(empresa_a, ["ventas:read"])
        res = ventas_get_notas_venta(
            str(tok.token), str(empresa_a.id_empresa), estado="BORRADOR"
        )
        assert len(res) == 1
        assert res[0]["numero"] == "NV-MCP-001"

    def test_respeta_limit(self, empresa_a, notas_venta):
        tok = _token(empresa_a, ["ventas:read"])
        res = ventas_get_notas_venta(str(tok.token), str(empresa_a.id_empresa), limit=1)
        assert len(res) == 1

    def test_empresa_distinta_lanza_permissionerror(self, empresa_a, empresa_b):
        tok = _token(empresa_a, ["ventas:read"])
        with pytest.raises(PermissionError):
            ventas_get_notas_venta(str(tok.token), str(empresa_b.id_empresa))


# ── ventas_get_facturas ───────────────────────────────────────────────────────

class TestGetFacturas:
    """
    Regresión del BUG "rota contra el modelo real": ``ventas_get_facturas``
    ordenaba por ``-fecha_factura`` y leía ``f.fecha_factura`` / ``f.total``,
    campos inexistentes en ``FacturaFiscal`` (los reales son ``fecha_emision``
    y ``monto_total``) y toda evaluación lanzaba FieldError. Ahora se valida
    el comportamiento funcional correcto.
    """

    def test_listar_devuelve_facturas_con_campos_reales(self, empresa_a, facturas):
        tok = _token(empresa_a, ["ventas:read"])
        res = ventas_get_facturas(str(tok.token), str(empresa_a.id_empresa))
        assert {f["numero_factura"] for f in res} == {"FAC-MCP-001", "FAC-MCP-002"}
        f1 = next(f for f in res if f["numero_factura"] == "FAC-MCP-001")
        assert f1["numero_control"] == "MC-001"
        assert f1["cliente"] == "Cliente MCP"
        assert f1["estado"] == "EMITIDA"
        assert f1["fecha"] == str(HOY)
        # M-BUG-1: monetario como Decimal, nunca float.
        assert f1["total"] == Decimal("116.0000")

    def test_filtro_por_estado(self, empresa_a, facturas):
        tok = _token(empresa_a, ["ventas:read"])
        res = ventas_get_facturas(str(tok.token), str(empresa_a.id_empresa), estado="ANULADA")
        assert len(res) == 1
        assert res[0]["numero_factura"] == "FAC-MCP-002"
        assert res[0]["total"] == Decimal("58.0000")

    def test_scope_faltante_lanza_permissionerror(self, empresa_a, facturas):
        tok = _token(empresa_a, ["crm:read"])  # falta ventas:read
        with pytest.raises(PermissionError):
            ventas_get_facturas(str(tok.token), str(empresa_a.id_empresa))

    def test_empresa_distinta_lanza_permissionerror(self, empresa_a, empresa_b, facturas):
        tok = _token(empresa_a, ["ventas:read"])
        with pytest.raises(PermissionError):
            ventas_get_facturas(str(tok.token), str(empresa_b.id_empresa))


# ── Export para auto-discovery ────────────────────────────────────────────────

def test_mcp_tools_exporta_las_tres_herramientas_con_scope():
    nombres = {t["name"] for t in MCP_TOOLS}
    assert nombres == {
        "ventas_get_cotizacion",
        "ventas_get_notas_venta",
        "ventas_get_facturas",
    }
    assert all(t["scope"] == "ventas:read" for t in MCP_TOOLS)
    assert all(callable(t["fn"]) for t in MCP_TOOLS)
