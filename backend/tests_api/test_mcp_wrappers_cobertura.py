"""
Backfill de cobertura — herramientas MCP misceláneas (plan "Cero Dudas").

Cubre:
- ``apps/integration_hub/mcp.py``: listar_conectores, test_conector, sincronizar
  (éxito y fallo del broker — BUG-NEW-5) y estado_sync.
- ``apps/inventario/mcp.py``: enforcement de scope/tenant del CapabilityToken
  (patrón de tests_api/test_mcp_server_scope.py), inventario_get_productos e
  inventario_get_stock_resumen.

BUG DOCUMENTADO (sin enmascarar):
- ``inventario_get_alertas_stock`` filtra por ``id_producto__punto_reorden`` pero el
  modelo ``Producto`` NO tiene campo ``punto_reorden`` → FieldError en runtime.
  Ver ``TestInventarioAlertasStock``.
"""
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import pytest

from django.utils import timezone

from apps.core.models import CapabilityToken
from apps.integration_hub import mcp as hub_mcp
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor, JobSincronizacion
from apps.inventario import mcp as inv_mcp

pytestmark = pytest.mark.django_db


def _token(empresa, scopes, *, activo=True, expires_at=None, creado_por=None):
    return CapabilityToken.objects.create(
        empresa=empresa,
        nombre="tok-test",
        scopes=scopes,
        activo=activo,
        expires_at=expires_at,
        creado_por=creado_por,
    )


# ── Fixtures locales ──────────────────────────────────────────────────────────

@pytest.fixture
def proveedor(db):
    return ConectorProveedor.objects.create(codigo="odoo-test", nombre="Odoo Test")


@pytest.fixture
def conector_a(db, empresa_a, proveedor):
    return ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor,
        nombre="Conector Alpha",
        estado="activo",
        entidades_activas=["contactos"],
    )


@pytest.fixture
def unidad(db, empresa_a):
    from apps.inventario.models import UnidadMedida
    return UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad", abreviatura="UN"
    )


@pytest.fixture
def categoria(db, empresa_a):
    from apps.inventario.models import CategoriaProducto
    return CategoriaProducto.objects.create(
        id_empresa=empresa_a, nombre_categoria="Cat MCP"
    )


@pytest.fixture
def producto_a(db, empresa_a, unidad, categoria, moneda_usd):
    from apps.inventario.models import Producto
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Aceite MCP 10W-40",
        sku="MCP-001",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("25.5000"),
    )


@pytest.fixture
def almacen_a(db, empresa_a):
    from apps.almacenes.models import Almacen
    return Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Principal MCP", codigo_almacen="ALM-MCP"
    )


# ═══════════════════════════════ integration_hub.mcp ═════════════════════════


class TestListarConectores:
    def test_lista_solo_activos_de_la_empresa(self, empresa_a, empresa_b, proveedor, conector_a):
        # Inactivo (no debe salir)
        ConectorInstancia.objects.create(
            id_empresa=empresa_a, id_proveedor=proveedor, nombre="Inactivo", activo=False
        )
        # De otra empresa (no debe salir)
        ConectorInstancia.objects.create(
            id_empresa=empresa_b, id_proveedor=proveedor, nombre="Beta"
        )

        res = hub_mcp.listar_conectores(str(empresa_a.id_empresa))
        assert len(res) == 1
        item = res[0]
        assert item["id"] == str(conector_a.id_conector)
        assert item["nombre"] == "Conector Alpha"
        assert item["proveedor"] == "Odoo Test"
        assert item["estado"] == "activo"
        assert item["ultimo_sync"] is None  # nunca sincronizó
        assert item["entidades_activas"] == ["contactos"]

    def test_ultimo_sync_se_serializa_como_string(self, empresa_a, conector_a):
        conector_a.ultimo_sync = timezone.now()
        conector_a.save(update_fields=["ultimo_sync"])
        res = hub_mcp.listar_conectores(str(empresa_a.id_empresa))
        assert isinstance(res[0]["ultimo_sync"], str)

    def test_empresa_sin_conectores_devuelve_lista_vacia(self, empresa_b):
        assert hub_mcp.listar_conectores(str(empresa_b.id_empresa)) == []


class TestTestConector:
    def test_conector_inexistente(self, empresa_a):
        falso = str(uuid.uuid4())
        res = hub_mcp.test_conector(str(empresa_a.id_empresa), falso)
        assert res["success"] is False
        assert falso in res["message"]

    def test_conector_de_otra_empresa_no_se_encuentra(self, empresa_b, conector_a):
        """Aislamiento multi-tenant: el conector de A no es visible para B."""
        res = hub_mcp.test_conector(str(empresa_b.id_empresa), str(conector_a.id_conector))
        assert res["success"] is False

    def test_conexion_exitosa_via_registry(self, empresa_a, conector_a):
        resultado = SimpleNamespace(success=True, message="Conexión OK", version="17.0")
        fake_connector = mock.Mock()
        fake_connector.test_connection.return_value = resultado

        from apps.integration_hub.connectors.registry import registry
        with mock.patch.object(registry, "get_connector", return_value=fake_connector) as gc:
            res = hub_mcp.test_conector(str(empresa_a.id_empresa), str(conector_a.id_conector))

        gc.assert_called_once()
        assert res == {"success": True, "message": "Conexión OK", "version": "17.0"}


class TestSincronizar:
    def test_conector_inexistente(self, empresa_a):
        res = hub_mcp.sincronizar(str(empresa_a.id_empresa), str(uuid.uuid4()), "contactos")
        assert res["success"] is False
        assert JobSincronizacion.objects.count() == 0

    def test_sincronizacion_encolada_ok(self, empresa_a, conector_a):
        fake_task = SimpleNamespace(id="celery-task-123")
        with mock.patch(
            "apps.integration_hub.tasks.ejecutar_job_sincronizacion.delay",
            return_value=fake_task,
        ):
            res = hub_mcp.sincronizar(
                str(empresa_a.id_empresa), str(conector_a.id_conector), "contactos"
            )

        assert res["success"] is True
        assert "contactos" in res["mensaje"]
        job = JobSincronizacion.objects.get(id_job=res["job_id"])
        assert job.tipo_entidad == "contactos"
        assert job.direccion == "inbound"
        assert job.celery_task_id == "celery-task-123"

    def test_broker_caido_marca_job_fallido(self, empresa_a, conector_a):
        """BUG-NEW-5: si el broker falla, el job no queda 'pendiente' eterno."""
        with mock.patch(
            "apps.integration_hub.tasks.ejecutar_job_sincronizacion.delay",
            side_effect=ConnectionError("broker caído"),
        ):
            res = hub_mcp.sincronizar(
                str(empresa_a.id_empresa), str(conector_a.id_conector), "productos"
            )

        assert res["success"] is False
        assert "procesador de tareas" in res["mensaje"]
        job = JobSincronizacion.objects.get(id_job=res["job_id"])
        assert job.estado == "fallido"
        assert job.resumen_errores  # mensaje de error registrado


class TestEstadoSync:
    def test_conteo_ultimas_24h_y_conectores_activos(self, empresa_a, conector_a):
        ahora = timezone.now()

        def _job(estado, iniciado_en):
            return JobSincronizacion.objects.create(
                id_instancia=conector_a,
                tipo_entidad="contactos",
                estado=estado,
                iniciado_en=iniciado_en,
            )

        _job("completado", ahora)
        _job("completado_con_errores", ahora)
        _job("fallido", ahora)
        _job("pendiente", ahora)
        _job("en_progreso", ahora)
        # Job viejo: fuera de la ventana de 24h
        _job("completado", ahora - timedelta(hours=48))

        res = hub_mcp.estado_sync(str(empresa_a.id_empresa))
        assert res["ultima_24h"]["total"] == 5
        assert res["ultima_24h"]["completados"] == 1
        assert res["ultima_24h"]["con_errores"] == 1
        assert res["ultima_24h"]["fallidos"] == 1
        assert res["ultima_24h"]["en_progreso"] == 2
        assert res["conectores_activos"] == 1

    def test_empresa_sin_actividad(self, empresa_b):
        res = hub_mcp.estado_sync(str(empresa_b.id_empresa))
        assert res["ultima_24h"]["total"] == 0
        assert res["conectores_activos"] == 0


# ═══════════════════════════════ inventario.mcp ══════════════════════════════


class TestInventarioGetProductos:
    def test_token_sin_scope_lanza(self, empresa_a):
        tok = _token(empresa_a, ["ventas:read"])
        with pytest.raises(PermissionError):
            inv_mcp.inventario_get_productos(str(tok.token), str(empresa_a.id_empresa))

    def test_empresa_distinta_al_tenant_lanza(self, empresa_a, empresa_b):
        tok = _token(empresa_a, ["inventario:read"])
        with pytest.raises(PermissionError, match="empresa_id no coincide"):
            inv_mcp.inventario_get_productos(str(tok.token), str(empresa_b.id_empresa))

    def test_lista_productos_con_decimal(self, empresa_a, producto_a):
        tok = _token(empresa_a, ["inventario:read"])
        res = inv_mcp.inventario_get_productos(str(tok.token), str(empresa_a.id_empresa))
        assert len(res) == 1
        p = res[0]
        assert p["id_producto"] == str(producto_a.id_producto)
        assert p["nombre_producto"] == "Aceite MCP 10W-40"
        assert p["sku"] == "MCP-001"
        # M-BUG-1: el monto debe ser Decimal, nunca float
        assert isinstance(p["precio_venta_sugerido"], Decimal)
        assert p["precio_venta_sugerido"] == Decimal("25.5000")
        assert p["activo"] is True

    def test_filtro_buscar_y_activos_solo(self, empresa_a, producto_a, unidad, categoria, moneda_usd):
        from apps.inventario.models import Producto
        Producto.objects.create(
            id_empresa=empresa_a,
            nombre_producto="Grasa Inactiva",
            sku="MCP-002",
            id_unidad_medida_base=unidad,
            id_categoria=categoria,
            id_moneda_precio=moneda_usd,
            activo=False,
        )
        tok = _token(empresa_a, ["inventario:read"])

        # activos_solo=True (default) excluye el inactivo
        res = inv_mcp.inventario_get_productos(str(tok.token), str(empresa_a.id_empresa))
        assert [p["sku"] for p in res] == ["MCP-001"]

        # activos_solo=False incluye ambos
        res = inv_mcp.inventario_get_productos(
            str(tok.token), str(empresa_a.id_empresa), activos_solo=False
        )
        assert len(res) == 2

        # buscar filtra por nombre
        res = inv_mcp.inventario_get_productos(
            str(tok.token), str(empresa_a.id_empresa), buscar="aceite"
        )
        assert len(res) == 1
        assert res[0]["nombre_producto"] == "Aceite MCP 10W-40"

        # buscar sin coincidencias
        res = inv_mcp.inventario_get_productos(
            str(tok.token), str(empresa_a.id_empresa), buscar="inexistente"
        )
        assert res == []

    def test_limit_se_acota_a_200(self, empresa_a, producto_a):
        tok = _token(empresa_a, ["inventario:read"])
        # No hay 200 productos; solo verificamos que limit gigante no rompe
        res = inv_mcp.inventario_get_productos(
            str(tok.token), str(empresa_a.id_empresa), limit=10_000
        )
        assert len(res) == 1


class TestInventarioStockResumen:
    def test_empresa_distinta_al_tenant_lanza(self, empresa_a, empresa_b):
        tok = _token(empresa_a, ["inventario:read"])
        with pytest.raises(PermissionError):
            inv_mcp.inventario_get_stock_resumen(str(tok.token), str(empresa_b.id_empresa))

    def test_resumen_y_filtro_por_almacen(self, empresa_a, producto_a, almacen_a):
        from apps.almacenes.models import Almacen
        from apps.inventario.models import StockActual

        StockActual.objects.create(
            id_empresa=empresa_a,
            id_producto=producto_a,
            id_almacen=almacen_a,
            cantidad_disponible=Decimal("100.0000"),
            cantidad_comprometida=Decimal("30.0000"),
        )
        otro = Almacen.objects.create(
            id_empresa=empresa_a, nombre_almacen="Secundario", codigo_almacen="ALM-2"
        )
        StockActual.objects.create(
            id_empresa=empresa_a,
            id_producto=producto_a,
            id_almacen=otro,
            cantidad_disponible=Decimal("5.0000"),
        )

        tok = _token(empresa_a, ["inventario:read"])
        res = inv_mcp.inventario_get_stock_resumen(str(tok.token), str(empresa_a.id_empresa))
        assert len(res) == 2

        fila = next(r for r in res if r["almacen"] == "Principal MCP")
        assert fila["producto_id"] == str(producto_a.id_producto)
        assert fila["cantidad_disponible"] == 100.0
        assert fila["cantidad_comprometida"] == 30.0
        assert fila["disponible_neto"] == 70.0

        # Filtro por almacén
        res = inv_mcp.inventario_get_stock_resumen(
            str(tok.token), str(empresa_a.id_empresa), almacen_id=str(otro.id_almacen)
        )
        assert len(res) == 1
        assert res[0]["almacen"] == "Secundario"


class TestInventarioAlertasStock:
    def test_bug_punto_reorden_no_existe_en_producto(self, empresa_a):
        """BUG documentado (sin enmascarar): inventario_get_alertas_stock filtra por
        ``id_producto__punto_reorden`` pero ``Producto`` no define ese campo, por lo
        que la herramienta MCP siempre falla con FieldError al ejecutarse.
        Cuando se agregue el campo ``punto_reorden`` al modelo (o se corrija la
        consulta), este test debe reemplazarse por aserciones funcionales.
        """
        from django.core.exceptions import FieldError

        tok = _token(empresa_a, ["inventario:read"])
        with pytest.raises(FieldError):
            inv_mcp.inventario_get_alertas_stock(str(tok.token), str(empresa_a.id_empresa))

    def test_tenant_se_valida_antes_del_bug(self, empresa_a, empresa_b):
        """El aislamiento de tenant también ocurre antes de la consulta defectuosa."""
        tok = _token(empresa_a, ["inventario:read"])
        with pytest.raises(PermissionError, match="empresa_id no coincide"):
            inv_mcp.inventario_get_alertas_stock(str(tok.token), str(empresa_b.id_empresa))

    def test_scope_se_valida_antes_del_bug(self, empresa_a):
        """El enforcement de scope ocurre antes de la consulta defectuosa."""
        tok = _token(empresa_a, ["crm:read"])
        with pytest.raises(PermissionError):
            inv_mcp.inventario_get_alertas_stock(str(tok.token), str(empresa_a.id_empresa))


class TestMcpToolsRegistro:
    def test_mcp_tools_declara_las_tres_herramientas(self):
        nombres = {t["name"] for t in inv_mcp.MCP_TOOLS}
        assert nombres == {
            "inventario_get_productos",
            "inventario_get_stock_resumen",
            "inventario_get_alertas_stock",
        }
        assert all(t["scope"] == "inventario:read" for t in inv_mcp.MCP_TOOLS)

    def test_capacidades_integration_hub_declaradas(self):
        nombres = {c["name"] for c in hub_mcp.MCP_CAPABILITIES}
        assert "integration_hub.sincronizar" in nombres
        assert "integration_hub.listar_conectores" in nombres
