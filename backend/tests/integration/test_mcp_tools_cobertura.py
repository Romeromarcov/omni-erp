"""
Backfill de cobertura — CUERPOS de las tools MCP de apps/core/mcp_server.py.

Complementa (sin duplicar):
  - tests/integration/test_mcp_server_scope.py  → núcleo de _resolve_token/_require_scope.
  - tests/integration/test_mcp_tools_bugfixes.py → omni_get_empresas / omni_get_saldo_cliente.
  - tests/api/test_cxc_ws2_mcp.py       → omni_get_cxc_aging / stock / ventas_resumen básicos.

Aquí se cubren los cuerpos restantes con datos reales y valores exactos:
  omni_get_clientes, omni_buscar_cliente, omni_buscar_contacto, omni_crear_pedido,
  omni_get_pedidos, omni_get_ventas_resumen (filtros de fecha), omni_get_stock_producto
  (filtro por almacén), omni_registrar_movimiento_inventario, omni_get_correlativo_fiscal
  y las tools CxC v2 (cartera vencida, aging summary, tasa de cambio, acuerdos vigentes).
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.core.models import CapabilityToken

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _token(empresa, scopes):
    """Mismo patrón que test_mcp_server_scope/_bugfixes: token de sistema."""
    tok = CapabilityToken.objects.create(empresa=empresa, nombre="tok-test", scopes=scopes)
    return str(tok.token)


# ── Fixtures de dominio mínimas ───────────────────────────────────────────────

@pytest.fixture
def cliente_a(empresa_a):
    from apps.crm.models import Cliente

    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Distribuidora Orinoco C.A.",
        nombre_comercial="Orinoco",
        rif="J-11111111-1",
        email="ventas@orinoco.com",
        telefono="0414-1234567",
    )


@pytest.fixture
def producto_a(empresa_a, moneda_usd):
    from tests.factories import ProductoFactory

    return ProductoFactory(id_empresa=empresa_a, nombre_producto="Harina PAN 1kg")


@pytest.fixture
def almacen_a(empresa_a):
    from tests.factories import AlmacenFactory

    return AlmacenFactory(id_empresa=empresa_a, nombre_almacen="Principal")


# ── omni_get_clientes ─────────────────────────────────────────────────────────

class TestGetClientes:
    def test_devuelve_valores_exactos(self, empresa_a, cliente_a):
        from apps.core.mcp_server import omni_get_clientes

        res = omni_get_clientes(_token(empresa_a, ["crm:read"]), str(empresa_a.id_empresa))
        assert res == [
            {
                "id_cliente": str(cliente_a.id_cliente),
                "razon_social": "Distribuidora Orinoco C.A.",
                "rif": "J-11111111-1",
                "activo": True,
            }
        ]

    def test_filtro_buscar_por_rif(self, empresa_a, cliente_a):
        from apps.core.mcp_server import omni_get_clientes
        from apps.crm.models import Cliente

        Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Otro Cliente", rif="J-22222222-2"
        )
        res = omni_get_clientes(
            _token(empresa_a, ["crm:read"]), str(empresa_a.id_empresa), buscar="J-11111111"
        )
        assert [c["razon_social"] for c in res] == ["Distribuidora Orinoco C.A."]

    def test_empresa_id_de_otro_tenant_lanza(self, empresa_a, empresa_b):
        from apps.core.mcp_server import omni_get_clientes

        with pytest.raises(PermissionError, match="empresa_id"):
            omni_get_clientes(_token(empresa_a, ["crm:read"]), str(empresa_b.id_empresa))

    def test_no_devuelve_clientes_de_otra_empresa(self, empresa_a, empresa_b, cliente_a):
        """R-CODE-1: el tenant B no ve clientes de A aunque su token sea válido."""
        from apps.core.mcp_server import omni_get_clientes

        res = omni_get_clientes(_token(empresa_b, ["crm:read"]), str(empresa_b.id_empresa))
        assert res == []


# ── omni_buscar_cliente ───────────────────────────────────────────────────────

class TestBuscarCliente:
    def test_busca_por_email_y_devuelve_campos(self, empresa_a, cliente_a):
        from apps.core.mcp_server import omni_buscar_cliente

        res = omni_buscar_cliente(
            _token(empresa_a, ["crm:read"]), str(empresa_a.id_empresa), "orinoco.com"
        )
        assert len(res) == 1
        assert res[0] == {
            "id_cliente": str(cliente_a.id_cliente),
            "razon_social": "Distribuidora Orinoco C.A.",
            "nombre_comercial": "Orinoco",
            "rif": "J-11111111-1",
            "email": "ventas@orinoco.com",
            "telefono": "0414-1234567",
            "tipo_cliente": "CONTADO",
        }

    def test_sin_coincidencias_lista_vacia(self, empresa_a, cliente_a):
        from apps.core.mcp_server import omni_buscar_cliente

        res = omni_buscar_cliente(
            _token(empresa_a, ["crm:read"]), str(empresa_a.id_empresa), "no-existe-xyz"
        )
        assert res == []

    def test_tenant_mismatch_lanza(self, empresa_a, empresa_b):
        from apps.core.mcp_server import omni_buscar_cliente

        with pytest.raises(PermissionError):
            omni_buscar_cliente(
                _token(empresa_a, ["crm:read"]), str(empresa_b.id_empresa), "x"
            )


# ── omni_buscar_contacto ──────────────────────────────────────────────────────

class TestBuscarContacto:
    @pytest.fixture
    def contacto_a(self, empresa_a):
        from apps.core.models import Contacto

        return Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Comercial Andina",
            rif="J-33333333-3",
            email="info@andina.com",
            telefono="0212-5551122",
            es_cliente=True,
            tipo_credito="CREDITO",
            limite_credito=Decimal("1500.00"),
        )

    def test_query_y_valores_exactos(self, empresa_a, contacto_a):
        from apps.core.mcp_server import omni_buscar_contacto

        res = omni_buscar_contacto(
            _token(empresa_a, ["contactos:read"]), str(empresa_a.id_empresa), query="Andina"
        )
        assert len(res) == 1
        c = res[0]
        assert c["id_contacto"] == str(contacto_a.id_contacto)
        assert c["rif"] == "J-33333333-3"
        assert c["email"] == "info@andina.com"
        assert c["roles"] == {
            "cliente": True, "proveedor": False, "empleado": False, "usuario": False,
        }
        assert c["tipo_credito"] == "CREDITO"
        assert c["limite_credito"] == "1500.00"
        assert c["lista_precio"] is None

    def test_filtro_rol_proveedor_excluye_cliente(self, empresa_a, contacto_a):
        from apps.core.mcp_server import omni_buscar_contacto

        res = omni_buscar_contacto(
            _token(empresa_a, ["contactos:read"]), str(empresa_a.id_empresa), rol="proveedor"
        )
        assert res == []

    def test_filtro_rol_cliente_incluye(self, empresa_a, contacto_a):
        from apps.core.mcp_server import omni_buscar_contacto

        res = omni_buscar_contacto(
            _token(empresa_a, ["contactos:read"]), str(empresa_a.id_empresa), rol="cliente"
        )
        assert [c["id_contacto"] for c in res] == [str(contacto_a.id_contacto)]

    def test_tenant_mismatch_lanza(self, empresa_a, empresa_b):
        from apps.core.mcp_server import omni_buscar_contacto

        with pytest.raises(PermissionError):
            omni_buscar_contacto(
                _token(empresa_a, ["contactos:read"]), str(empresa_b.id_empresa)
            )


# ── omni_get_stock_producto (filtro por almacén) ─────────────────────────────

class TestGetStockProducto:
    def test_filtra_por_almacen(self, empresa_a, producto_a, almacen_a):
        from tests.factories import AlmacenFactory
        from apps.core.mcp_server import omni_get_stock_producto
        from apps.inventario.models import StockActual

        almacen_2 = AlmacenFactory(id_empresa=empresa_a, nombre_almacen="Secundario")
        StockActual.objects.create(
            id_empresa=empresa_a, id_producto=producto_a, id_almacen=almacen_a,
            cantidad_disponible=Decimal("100"),
        )
        StockActual.objects.create(
            id_empresa=empresa_a, id_producto=producto_a, id_almacen=almacen_2,
            cantidad_disponible=Decimal("7.5"),
        )

        res = omni_get_stock_producto(
            _token(empresa_a, ["inventario:read"]),
            str(empresa_a.id_empresa),
            str(producto_a.id_producto),
            almacen_id=str(almacen_2.id_almacen),
        )
        assert res == [
            {
                "almacen_id": str(almacen_2.id_almacen),
                "almacen_nombre": "Secundario",
                "cantidad_disponible": 7.5,
            }
        ]

    def test_tenant_mismatch_lanza(self, empresa_a, empresa_b, producto_a):
        from apps.core.mcp_server import omni_get_stock_producto

        with pytest.raises(PermissionError):
            omni_get_stock_producto(
                _token(empresa_a, ["inventario:read"]),
                str(empresa_b.id_empresa),
                str(producto_a.id_producto),
            )


# ── omni_get_ventas_resumen (filtros de fecha) ───────────────────────────────

class TestVentasResumen:
    @pytest.fixture
    def pedido_aprobado(self, empresa_a, cliente_a, producto_a):
        from apps.ventas.models import DetallePedido, Pedido

        pedido = Pedido.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            numero_pedido="COV-001",
            fecha_pedido=date(2026, 1, 15),
            estado="APROBADO",
        )
        DetallePedido.objects.create(
            id_pedido=pedido, id_producto=producto_a,
            cantidad=Decimal("2"), precio_unitario=Decimal("50.00"),
            subtotal=Decimal("100.00"),
        )
        return pedido

    def test_rango_que_incluye_devuelve_totales_decimal(self, empresa_a, pedido_aprobado):
        from apps.core.mcp_server import omni_get_ventas_resumen

        res = omni_get_ventas_resumen(
            _token(empresa_a, ["ventas:read"]),
            str(empresa_a.id_empresa),
            fecha_desde="2026-01-01",
            fecha_hasta="2026-01-31",
        )
        assert res["cantidad_pedidos"] == 1
        assert res["total_ventas"] == Decimal("100.00")
        assert res["promedio_linea"] == Decimal("100.00")

    def test_rango_que_excluye_devuelve_cero(self, empresa_a, pedido_aprobado):
        from apps.core.mcp_server import omni_get_ventas_resumen

        res = omni_get_ventas_resumen(
            _token(empresa_a, ["ventas:read"]),
            str(empresa_a.id_empresa),
            fecha_desde="2026-02-01",
        )
        assert res["cantidad_pedidos"] == 0
        assert res["total_ventas"] == Decimal("0")
        assert res["promedio_linea"] == Decimal("0")


# ── omni_crear_pedido ─────────────────────────────────────────────────────────

class TestCrearPedido:
    def test_crea_pedido_con_detalle_exacto(self, empresa_a, cliente_a, producto_a):
        from apps.core.mcp_server import omni_crear_pedido
        from apps.ventas.models import DetallePedido, Pedido

        res = omni_crear_pedido(
            _token(empresa_a, ["ventas:write"]),
            str(empresa_a.id_empresa),
            str(cliente_a.id_cliente),
            productos=[{
                "id_producto": str(producto_a.id_producto),
                "cantidad": 2,
                "precio_unitario": "10.50",
            }],
        )
        assert "error" not in res
        assert res["estado"] == "PENDIENTE"
        assert res["cantidad_lineas"] == 1
        assert res["numero_pedido"].startswith("PED-")

        pedido = Pedido.objects.get(id_pedido=res["id_pedido"])
        assert pedido.id_empresa_id == empresa_a.id_empresa
        detalle = DetallePedido.objects.get(id_pedido=pedido)
        assert detalle.cantidad == Decimal("2")
        assert detalle.precio_unitario == Decimal("10.50")
        assert detalle.subtotal == Decimal("21.00")  # R-CODE-4: Decimal exacto

    def test_sin_productos_lanza_valueerror(self, empresa_a, cliente_a):
        from apps.core.mcp_server import omni_crear_pedido

        with pytest.raises(ValueError, match="al menos un producto"):
            omni_crear_pedido(
                _token(empresa_a, ["ventas:write"]),
                str(empresa_a.id_empresa),
                str(cliente_a.id_cliente),
                productos=[],
            )

    def test_linea_invalida_devuelve_error_y_no_deja_pedido(self, empresa_a, cliente_a, producto_a):
        """Cantidad no numérica → InvalidOperation dentro del atomic → dict de error."""
        from apps.core.mcp_server import omni_crear_pedido
        from apps.ventas.models import Pedido

        res = omni_crear_pedido(
            _token(empresa_a, ["ventas:write"]),
            str(empresa_a.id_empresa),
            str(cliente_a.id_cliente),
            productos=[{
                "id_producto": str(producto_a.id_producto),
                "cantidad": "no-es-numero",
                "precio_unitario": "5.00",
            }],
        )
        assert "error" in res
        # atómico: no debe quedar pedido huérfano
        assert Pedido.objects.filter(id_empresa=empresa_a).count() == 0

    def test_tenant_mismatch_lanza(self, empresa_a, empresa_b, cliente_a):
        from apps.core.mcp_server import omni_crear_pedido

        with pytest.raises(PermissionError):
            omni_crear_pedido(
                _token(empresa_a, ["ventas:write"]),
                str(empresa_b.id_empresa),
                str(cliente_a.id_cliente),
                productos=[{"id_producto": "x", "cantidad": 1, "precio_unitario": "1"}],
            )


# ── omni_get_pedidos ──────────────────────────────────────────────────────────

class TestGetPedidos:
    @pytest.fixture
    def pedidos(self, empresa_a, cliente_a):
        from apps.ventas.models import Pedido

        p1 = Pedido.objects.create(
            id_empresa=empresa_a, id_cliente=cliente_a, numero_pedido="P-001",
            fecha_pedido=date(2026, 3, 1), estado="PENDIENTE",
        )
        p2 = Pedido.objects.create(
            id_empresa=empresa_a, id_cliente=cliente_a, numero_pedido="P-002",
            fecha_pedido=date(2026, 3, 2), estado="APROBADO",
        )
        return p1, p2

    def test_lista_ordenada_por_fecha_desc(self, empresa_a, pedidos):
        from apps.core.mcp_server import omni_get_pedidos

        res = omni_get_pedidos(_token(empresa_a, ["ventas:read"]), str(empresa_a.id_empresa))
        assert [p["numero_pedido"] for p in res] == ["P-002", "P-001"]
        assert res[0] == {
            "id_pedido": str(pedidos[1].id_pedido),
            "numero_pedido": "P-002",
            "cliente": "Distribuidora Orinoco C.A.",
            "fecha_pedido": "2026-03-02",
            "estado": "APROBADO",
        }

    def test_filtro_por_estado(self, empresa_a, pedidos):
        from apps.core.mcp_server import omni_get_pedidos

        res = omni_get_pedidos(
            _token(empresa_a, ["ventas:read"]), str(empresa_a.id_empresa), estado="APROBADO"
        )
        assert [p["numero_pedido"] for p in res] == ["P-002"]

    def test_tenant_mismatch_lanza(self, empresa_a, empresa_b):
        from apps.core.mcp_server import omni_get_pedidos

        with pytest.raises(PermissionError):
            omni_get_pedidos(_token(empresa_a, ["ventas:read"]), str(empresa_b.id_empresa))


# ── omni_registrar_movimiento_inventario ─────────────────────────────────────

class TestRegistrarMovimiento:
    def test_tipo_invalido_devuelve_error(self, empresa_a, producto_a):
        from apps.core.mcp_server import omni_registrar_movimiento_inventario

        res = omni_registrar_movimiento_inventario(
            _token(empresa_a, ["inventario:write"]),
            str(empresa_a.id_empresa),
            str(producto_a.id_producto),
            tipo="ROBO",
            cantidad="1",
        )
        assert "inválido" in res["error"]

    def test_token_real_no_es_usuario_valido(self, empresa_a, producto_a, almacen_a):
        """
        El actor de un CapabilityToken real es 'mcp-token:<8 chars>' — nunca un
        UUID de Usuarios. La guarda M-SEC-10 rechaza el movimiento.
        (Hallazgo: con tokens reales la ruta de éxito es inalcanzable.)
        """
        from apps.core.mcp_server import omni_registrar_movimiento_inventario

        res = omni_registrar_movimiento_inventario(
            _token(empresa_a, ["inventario:write"]),
            str(empresa_a.id_empresa),
            str(producto_a.id_producto),
            tipo="ENTRADA",
            cantidad="10",
            almacen_destino_id=str(almacen_a.id_almacen),
        )
        assert res == {"error": "actor_id del token MCP no corresponde a un usuario válido."}

    def _ctx_con_actor(self, empresa, user):
        return {
            "tenant_id": str(empresa.id_empresa),
            "empresa_id": str(empresa.id_empresa),
            "actor_id": f"mcp-token:{user.pk}",
            "scopes": ["inventario:write"],
        }

    def test_entrada_exitosa_con_actor_usuario(self, empresa_a, user_a, producto_a, almacen_a):
        from apps.core import mcp_server
        from apps.inventario.models import MovimientoInventario

        with patch.object(
            mcp_server, "_resolve_token", return_value=self._ctx_con_actor(empresa_a, user_a)
        ):
            res = mcp_server.omni_registrar_movimiento_inventario(
                str(uuid.uuid4()),
                str(empresa_a.id_empresa),
                str(producto_a.id_producto),
                tipo="ENTRADA",
                cantidad="12.5",
                almacen_destino_id=str(almacen_a.id_almacen),
            )

        assert res["tipo"] == "ENTRADA"
        assert res["cantidad"] == "12.5"
        mov = MovimientoInventario.objects.get(pk=res["id_movimiento"])
        assert mov.id_empresa_id == empresa_a.id_empresa
        assert mov.cantidad == Decimal("12.5")
        assert mov.id_almacen_destino_id == almacen_a.id_almacen
        assert mov.id_almacen_origen_id is None
        assert mov.id_usuario_registro_id == user_a.pk

    def test_cantidad_invalida_devuelve_dict_error(self, empresa_a, user_a, producto_a, almacen_a):
        """Decimal('x') → InvalidOperation, capturado y devuelto como error."""
        from apps.core import mcp_server
        from apps.inventario.models import MovimientoInventario

        with patch.object(
            mcp_server, "_resolve_token", return_value=self._ctx_con_actor(empresa_a, user_a)
        ):
            res = mcp_server.omni_registrar_movimiento_inventario(
                str(uuid.uuid4()),
                str(empresa_a.id_empresa),
                str(producto_a.id_producto),
                tipo="SALIDA",
                cantidad="no-decimal",
                almacen_origen_id=str(almacen_a.id_almacen),
            )
        assert "error" in res
        assert MovimientoInventario.objects.count() == 0


# ── omni_get_correlativo_fiscal ───────────────────────────────────────────────

class TestCorrelativoFiscal:
    def test_devuelve_siguiente_formateado(self, empresa_a):
        from apps.core.mcp_server import omni_get_correlativo_fiscal
        from apps.fiscal.models import NumeroCorrelativo

        NumeroCorrelativo.objects.create(
            id_empresa=empresa_a, tipo="FACTURA", prefijo="FAC-", numero_actual=41, digitos=8
        )
        res = omni_get_correlativo_fiscal(
            _token(empresa_a, ["fiscal:read"]), str(empresa_a.id_empresa), "FACTURA"
        )
        assert res == {
            "tipo_documento": "FACTURA",
            "empresa_id": str(empresa_a.id_empresa),
            "numero_actual": 41,
            "siguiente_numero": 42,
            "prefijo": "FAC-",
            "numero_formateado": "FAC-00000042",
        }

    def test_tipo_invalido_devuelve_error(self, empresa_a):
        from apps.core.mcp_server import omni_get_correlativo_fiscal

        res = omni_get_correlativo_fiscal(
            _token(empresa_a, ["fiscal:read"]), str(empresa_a.id_empresa), "RECIBO"
        )
        assert "inválido" in res["error"]

    def test_sin_configuracion_devuelve_error(self, empresa_a):
        from apps.core.mcp_server import omni_get_correlativo_fiscal

        res = omni_get_correlativo_fiscal(
            _token(empresa_a, ["fiscal:read"]), str(empresa_a.id_empresa), "NOTA_CREDITO"
        )
        assert "No existe configuración" in res["error"]


# ── Tools CxC v2 ──────────────────────────────────────────────────────────────

@pytest.fixture
def cxc_vencida(empresa_a, cliente_a):
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar

    hoy = date.today()
    return CuentaPorCobrar.objects.create(
        cliente=cliente_a,
        empresa=empresa_a,
        monto=Decimal("500.00"),
        fecha_emision=hoy - timedelta(days=40),
        fecha_vencimiento=hoy - timedelta(days=10),
        estado="pendiente",
        descripcion="Factura vencida test",
    )


class TestCxcCarteraVencida:
    def test_devuelve_partida_con_score(self, empresa_a, cliente_a, cxc_vencida):
        from apps.core.mcp_server import omni_cxc_get_cartera_vencida

        res = omni_cxc_get_cartera_vencida(
            _token(empresa_a, ["cxc:read"]), str(empresa_a.id_empresa)
        )
        assert len(res) == 1
        p = res[0]
        assert p["cliente_nombre"] == "Distribuidora Orinoco C.A."
        assert p["monto_pendiente"] == "500.00"
        assert p["dias_vencida"] == 10
        assert p["bucket"] == "1_30"
        # score = 10×3 + 500/100 + 0 = 35
        assert Decimal(p["score"]) == Decimal("35")

    def test_tenant_mismatch_lanza(self, empresa_a, empresa_b):
        from apps.core.mcp_server import omni_cxc_get_cartera_vencida

        with pytest.raises(PermissionError):
            omni_cxc_get_cartera_vencida(
                _token(empresa_a, ["cxc:read"]), str(empresa_b.id_empresa)
            )


class TestCxcAgingSummary:
    def test_buckets_y_totales(self, empresa_a, cxc_vencida):
        from apps.core.mcp_server import omni_cxc_get_aging_summary

        res = omni_cxc_get_aging_summary(
            _token(empresa_a, ["cxc:read"]), str(empresa_a.id_empresa)
        )
        assert res["buckets"]["1_30"]["count"] == 1
        assert Decimal(res["buckets"]["1_30"]["total"]) == Decimal("500.00")
        assert Decimal(res["total_pendiente"]) == Decimal("500.00")
        assert res["total_partidas"] == 1
        assert res["partidas_vencidas"] == 1

    def test_segunda_llamada_usa_cache(self, empresa_a, cxc_vencida):
        from apps.core.mcp_server import omni_cxc_get_aging_summary

        tok = _token(empresa_a, ["cxc:read"])
        primera = omni_cxc_get_aging_summary(tok, str(empresa_a.id_empresa))
        with patch(
            "apps.cuentas_por_cobrar.services_aging.calcular_aging"
        ) as mock_aging:
            segunda = omni_cxc_get_aging_summary(tok, str(empresa_a.id_empresa))
        mock_aging.assert_not_called()
        assert segunda == primera


class TestCxcTasaCambioHoy:
    def test_sin_tasa_devuelve_error(self, empresa_a):
        from apps.core.mcp_server import omni_cxc_get_tasa_cambio_hoy

        res = omni_cxc_get_tasa_cambio_hoy(_token(empresa_a, ["finanzas:read"]))
        assert res["valor_tasa"] is None
        assert "No hay tasa OFICIAL_BCV" in res["error"]

    def test_con_tasa_del_dia(self, empresa_a, moneda_usd):
        from apps.core.mcp_server import omni_cxc_get_tasa_cambio_hoy
        from apps.finanzas.models import Moneda, TasaCambio

        ves = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat"
        )
        TasaCambio.objects.create(
            id_moneda_origen=moneda_usd,
            id_moneda_destino=ves,
            tipo_tasa="OFICIAL_BCV",
            valor_tasa=Decimal("36.50000000"),
            fecha_tasa=date.today(),
        )
        res = omni_cxc_get_tasa_cambio_hoy(_token(empresa_a, ["finanzas:read"]))
        assert res["fecha"] == str(date.today())
        assert res["tipo_tasa"] == "OFICIAL_BCV"
        assert Decimal(res["valor_tasa"]) == Decimal("36.5")

    def test_requiere_scope_finanzas(self, empresa_a):
        from apps.core.mcp_server import omni_cxc_get_tasa_cambio_hoy

        with pytest.raises(PermissionError):
            omni_cxc_get_tasa_cambio_hoy(_token(empresa_a, ["cxc:read"]))


class TestCxcAcuerdosVigentes:
    def test_acuerdo_vigente_con_cuotas_pendientes(self, empresa_a, cliente_a):
        from apps.core.mcp_server import omni_cxc_get_acuerdos_vigentes
        from apps.cxc.models import AcuerdoPago, CuotaAcuerdo

        acuerdo = AcuerdoPago.objects.create(
            empresa=empresa_a,
            cliente_id=str(cliente_a.id_cliente),
            cliente_nombre="Distribuidora Orinoco C.A.",
            monto_total=Decimal("300.0000"),
            periodicidad="mensual",
            fecha_inicio=date(2026, 6, 1),
        )
        for n, estado in [(1, "pagado"), (2, "pendiente"), (3, "vencido")]:
            CuotaAcuerdo.objects.create(
                acuerdo=acuerdo,
                numero_cuota=n,
                fecha_vencimiento=date(2026, 6, 1) + timedelta(days=30 * n),
                monto=Decimal("100.0000"),
                estado=estado,
            )
        # Un acuerdo cumplido NO debe aparecer
        AcuerdoPago.objects.create(
            empresa=empresa_a,
            cliente_id=str(cliente_a.id_cliente),
            monto_total=Decimal("50"),
            periodicidad="unico",
            fecha_inicio=date(2026, 1, 1),
            estado="cumplido",
        )

        res = omni_cxc_get_acuerdos_vigentes(
            _token(empresa_a, ["cxc:read"]),
            str(empresa_a.id_empresa),
            str(cliente_a.id_cliente),
        )
        assert len(res) == 1
        a = res[0]
        assert a["id"] == str(acuerdo.pk)
        assert Decimal(a["monto_total"]) == Decimal("300")
        assert a["periodicidad"] == "mensual"
        assert a["estado"] == "vigente"
        assert a["fecha_inicio"] == "2026-06-01"
        assert a["cuotas_pendientes"] == 2  # pendiente + vencido
        assert a["moneda"] == "USD"

    def test_tenant_mismatch_lanza(self, empresa_a, empresa_b, cliente_a):
        from apps.core.mcp_server import omni_cxc_get_acuerdos_vigentes

        with pytest.raises(PermissionError):
            omni_cxc_get_acuerdos_vigentes(
                _token(empresa_a, ["cxc:read"]),
                str(empresa_b.id_empresa),
                str(cliente_a.id_cliente),
            )
