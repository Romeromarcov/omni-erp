"""
API de despacho/entrega (1.G) — CRUD, transiciones, filtros, aislamiento y MCP.

Capas cubiertas aquí (R-CODE-9: tests en el mismo cambio):
  - CRUD del encabezado: número correlativo y empresa inyectados (H-API-1),
    estado read-only, DELETE bloqueado (405).
  - desde-nota-venta: despacho total/parcial, sobre-despacho → 400, nota en
    estado inválido → 400, payload inválido → 400.
  - Transiciones: máquina de estados completa, timestamps, evidencia en
    documento_json, payloads requeridos.
  - Aislamiento multi-tenant R-CODE-1: Empresa B no ve, no transiciona y no
    crea despachos sobre datos de Empresa A.
  - MCP ``despacho_get_pendientes``: scope y tenant del token respetados.

El flujo de negocio completo (venta real con stock) vive en
``tests/integration/test_despacho_flujo.py``.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.models import CapabilityToken
from apps.despacho.mcp import MCP_TOOLS, despacho_get_pendientes
from apps.despacho.models import Despacho, DetalleDespacho

pytestmark = pytest.mark.django_db

URL = "/api/despacho/despachos/"
URL_DETALLES = "/api/despacho/detalles-despacho/"


# ── Fixtures de escenario ─────────────────────────────────────────────────────


def _escenario_venta(empresa, moneda, sufijo):
    """Construye cliente/producto/almacén/nota ENTREGADA (10 uds) para una empresa."""
    from apps.almacenes.models import Almacen
    from apps.crm.models import Cliente
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
    from apps.ventas.models import DetalleNotaVenta, NotaVenta

    cliente = Cliente.objects.create(
        id_empresa=empresa, razon_social=f"Cliente {sufijo}", rif=f"J-0000000{sufijo[-1]}-0"
    )
    unidad = UnidadMedida.objects.create(
        id_empresa=empresa, nombre=f"Unidad {sufijo}", abreviatura=f"UN-{sufijo}", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(
        id_empresa=empresa, nombre_categoria=f"Cat {sufijo}"
    )
    producto = Producto.objects.create(
        id_empresa=empresa,
        nombre_producto=f"Producto {sufijo}",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda,
        precio_venta_sugerido=Decimal("10.00"),
    )
    almacen = Almacen.objects.create(
        id_empresa=empresa, nombre_almacen=f"Almacén {sufijo}", codigo_almacen=f"ALM-{sufijo}"
    )
    nota = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        numero_nota=f"NV-{sufijo}-001",
        fecha_nota=timezone.localdate(),
        estado="ENTREGADA",
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nota,
        id_producto=producto,
        cantidad=Decimal("10.0000"),
        precio_unitario=Decimal("10.00"),
        subtotal=Decimal("100.00"),
    )
    return {
        "cliente": cliente,
        "producto": producto,
        "almacen": almacen,
        "nota": nota,
        "unidad": unidad,
    }


@pytest.fixture
def venta_a(empresa_a, moneda_usd):
    return _escenario_venta(empresa_a, moneda_usd, "DSPA")


@pytest.fixture
def venta_b(empresa_b, moneda_usd):
    return _escenario_venta(empresa_b, moneda_usd, "DSPB")


@pytest.fixture
def transportista_a(empresa_a):
    from apps.rrhh.models import Empleado

    return Empleado.objects.create(
        empresa=empresa_a,
        nombre="Carlos",
        apellido="Chofer",
        cedula="V-12345678",
        fecha_ingreso=date(2025, 1, 15),
    )


def _crear_despacho_api(client, venta, **extra):
    """POST desde-nota-venta con todo lo pendiente (helper)."""
    payload = {
        "id_nota_venta": str(venta["nota"].id_nota_venta),
        "almacen_id": str(venta["almacen"].id_almacen),
        "direccion_entrega": "Av. Bolívar, Galpón 7, Valencia",
        **extra,
    }
    return client.post(f"{URL}desde-nota-venta/", payload, format="json")


def _resultados(data):
    return data["results"] if isinstance(data, dict) and "results" in data else data


# ── CRUD básico ───────────────────────────────────────────────────────────────


class TestDespachoCRUD:
    def test_create_directo_inyecta_empresa_numero_y_estado(self, client_a, empresa_a, venta_a):
        """H-API-1: empresa del almacén, correlativo fiscal y estado PENDIENTE forzados."""
        resp = client_a.post(
            URL,
            {
                "id_almacen_origen": str(venta_a["almacen"].id_almacen),
                "direccion_destino": "Zona Industrial Norte",
                # Intentos de manipulación que deben ignorarse (read-only):
                "estado_despacho": "ENTREGADO",
                "numero_despacho": "HACK-1",
                "id_empresa": "00000000-0000-0000-0000-000000000000",
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["estado_despacho"] == "PENDIENTE"
        assert resp.data["numero_despacho"] == "00000001"  # correlativo DESPACHO
        assert str(resp.data["id_empresa"]) == str(empresa_a.id_empresa)
        # fecha_despacho opcional: default now
        assert resp.data["fecha_despacho"] is not None

    def test_create_con_nota_en_borrador_rechazado(self, client_a, venta_a):
        venta_a["nota"].estado = "BORRADOR"
        venta_a["nota"].save(update_fields=["estado"])
        resp = client_a.post(
            URL,
            {
                "id_almacen_origen": str(venta_a["almacen"].id_almacen),
                "id_nota_venta": str(venta_a["nota"].id_nota_venta),
                "direccion_destino": "Destino X",
            },
            format="json",
        )
        assert resp.status_code == 400
        assert "id_nota_venta" in resp.data

    def test_patch_estado_es_read_only(self, client_a, venta_a):
        resp = _crear_despacho_api(client_a, venta_a)
        assert resp.status_code == 201
        pk = resp.data["id_despacho"]
        resp = client_a.patch(
            f"{URL}{pk}/", {"estado_despacho": "ENTREGADO", "observaciones": "ok"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.data["estado_despacho"] == "PENDIENTE"
        assert resp.data["observaciones"] == "ok"

    def test_delete_bloqueado_405(self, client_a, venta_a):
        resp = _crear_despacho_api(client_a, venta_a)
        pk = resp.data["id_despacho"]
        resp = client_a.delete(f"{URL}{pk}/")
        assert resp.status_code == 405
        assert Despacho.objects.filter(pk=pk).exists()

    def test_retrieve_incluye_detalles(self, client_a, venta_a):
        resp = _crear_despacho_api(client_a, venta_a)
        pk = resp.data["id_despacho"]
        resp = client_a.get(f"{URL}{pk}/")
        assert resp.status_code == 200
        assert len(resp.data["detalles"]) == 1
        det = resp.data["detalles"][0]
        assert det["nombre_producto"] == venta_a["producto"].nombre_producto
        assert Decimal(det["cantidad_despachada"]) == Decimal("10.0000")

    def test_requiere_autenticacion(self, api_client):
        assert api_client.get(URL).status_code in (401, 403)


# ── Crear desde la venta ──────────────────────────────────────────────────────


class TestDesdeNotaVenta:
    def test_despacho_total_de_lo_pendiente(self, client_a, venta_a):
        resp = _crear_despacho_api(client_a, venta_a)
        assert resp.status_code == 201, resp.data
        assert str(resp.data["id_nota_venta"]) == str(venta_a["nota"].id_nota_venta)
        assert resp.data["numero_nota_venta"] == venta_a["nota"].numero_nota
        assert len(resp.data["detalles"]) == 1
        assert Decimal(resp.data["detalles"][0]["cantidad_despachada"]) == Decimal("10.0000")

    def test_despacho_parcial_y_acumulado(self, client_a, venta_a):
        producto_id = str(venta_a["producto"].id_producto)
        # Primer viaje: 6 de 10.
        resp = _crear_despacho_api(
            client_a, venta_a, lineas=[{"id_producto": producto_id, "cantidad": "6"}]
        )
        assert resp.status_code == 201, resp.data
        # Segundo viaje: el total pendiente (4).
        resp = _crear_despacho_api(client_a, venta_a)
        assert resp.status_code == 201
        assert Decimal(resp.data["detalles"][0]["cantidad_despachada"]) == Decimal("4.0000")
        # Tercero: ya no queda nada.
        resp = _crear_despacho_api(client_a, venta_a)
        assert resp.status_code == 400
        assert "completamente despachada" in str(resp.data)

    def test_sobre_despacho_rechazado_400(self, client_a, venta_a):
        producto_id = str(venta_a["producto"].id_producto)
        resp = _crear_despacho_api(
            client_a, venta_a, lineas=[{"id_producto": producto_id, "cantidad": "11"}]
        )
        assert resp.status_code == 400
        assert "Sobre-despacho" in str(resp.data)
        assert Despacho.objects.count() == 0

    def test_cancelado_libera_cupo(self, client_a, venta_a):
        producto_id = str(venta_a["producto"].id_producto)
        resp = _crear_despacho_api(
            client_a, venta_a, lineas=[{"id_producto": producto_id, "cantidad": "10"}]
        )
        pk = resp.data["id_despacho"]
        # Con todo el cupo consumido, otro despacho falla…
        resp = _crear_despacho_api(
            client_a, venta_a, lineas=[{"id_producto": producto_id, "cantidad": "1"}]
        )
        assert resp.status_code == 400
        # …pero al cancelar, el cupo vuelve a estar disponible.
        resp = client_a.post(f"{URL}{pk}/cancelar/", {"motivo": "Camión averiado"}, format="json")
        assert resp.status_code == 200
        resp = _crear_despacho_api(
            client_a, venta_a, lineas=[{"id_producto": producto_id, "cantidad": "10"}]
        )
        assert resp.status_code == 201, resp.data

    def test_nota_borrador_rechazada(self, client_a, venta_a):
        venta_a["nota"].estado = "BORRADOR"
        venta_a["nota"].save(update_fields=["estado"])
        resp = _crear_despacho_api(client_a, venta_a)
        assert resp.status_code == 400
        assert "ENTREGADAS o FACTURADAS" in str(resp.data)

    def test_producto_fuera_de_la_nota_rechazado(self, client_a, venta_a, venta_b):
        resp = _crear_despacho_api(
            client_a,
            venta_a,
            lineas=[{"id_producto": str(venta_b["producto"].id_producto), "cantidad": "1"}],
        )
        assert resp.status_code == 400
        assert "no pertenece a la nota" in str(resp.data)

    def test_cantidad_no_positiva_rechazada(self, client_a, venta_a):
        producto_id = str(venta_a["producto"].id_producto)
        resp = _crear_despacho_api(
            client_a, venta_a, lineas=[{"id_producto": producto_id, "cantidad": "0"}]
        )
        assert resp.status_code == 400

    def test_producto_repetido_rechazado(self, client_a, venta_a):
        producto_id = str(venta_a["producto"].id_producto)
        resp = _crear_despacho_api(
            client_a,
            venta_a,
            lineas=[
                {"id_producto": producto_id, "cantidad": "4"},
                {"id_producto": producto_id, "cantidad": "4"},
            ],
        )
        assert resp.status_code == 400
        assert "repetidos" in str(resp.data)

    def test_lineas_vacias_rechazadas(self, client_a, venta_a):
        resp = _crear_despacho_api(client_a, venta_a, lineas=[])
        assert resp.status_code == 400

    def test_direccion_vacia_rechazada(self, client_a, venta_a):
        resp = _crear_despacho_api(client_a, venta_a, direccion_entrega="")
        assert resp.status_code == 400

    def test_transportista_asignado(self, client_a, venta_a, transportista_a):
        resp = _crear_despacho_api(
            client_a, venta_a, id_transportista=str(transportista_a.pk)
        )
        assert resp.status_code == 201
        assert resp.data["id_transportista"] == transportista_a.pk


# ── Transiciones de estado ────────────────────────────────────────────────────


class TestTransiciones:
    @pytest.fixture
    def despacho_a(self, client_a, venta_a):
        resp = _crear_despacho_api(client_a, venta_a)
        assert resp.status_code == 201
        return resp.data["id_despacho"]

    def test_flujo_feliz_hasta_entregado(self, client_a, despacho_a, transportista_a):
        resp = client_a.post(
            f"{URL}{despacho_a}/iniciar-ruta/",
            {"id_transportista": str(transportista_a.pk)},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        assert resp.data["estado_despacho"] == "EN_RUTA"
        assert resp.data["fecha_en_ruta"] is not None
        assert resp.data["id_transportista"] == transportista_a.pk

        resp = client_a.post(
            f"{URL}{despacho_a}/entregar/",
            {"receptor": "María Pérez", "documento_receptor": "V-9999999", "firma_base64": "ZmlybWE="},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        assert resp.data["estado_despacho"] == "ENTREGADO"
        assert resp.data["fecha_entrega_real"] is not None
        entrega = resp.data["documento_json"]["entrega"]
        assert entrega["receptor"] == "María Pérez"
        assert entrega["documento_receptor"] == "V-9999999"
        assert entrega["firma_base64"] == "ZmlybWE="

    def test_devolver_en_ruta(self, client_a, despacho_a):
        client_a.post(f"{URL}{despacho_a}/iniciar-ruta/", {}, format="json")
        resp = client_a.post(
            f"{URL}{despacho_a}/devolver/", {"motivo": "Cliente ausente"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.data["estado_despacho"] == "DEVUELTO"
        assert resp.data["fecha_devolucion"] is not None
        assert resp.data["documento_json"]["devolucion"]["motivo"] == "Cliente ausente"

    def test_cancelar_pendiente(self, client_a, despacho_a):
        resp = client_a.post(
            f"{URL}{despacho_a}/cancelar/", {"motivo": "Pedido duplicado"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.data["estado_despacho"] == "CANCELADO"
        assert resp.data["fecha_cancelacion"] is not None

    def test_no_entregar_lo_pendiente_sin_ruta(self, client_a, despacho_a):
        resp = client_a.post(
            f"{URL}{despacho_a}/entregar/", {"receptor": "Alguien"}, format="json"
        )
        assert resp.status_code == 400
        assert "Transición inválida" in str(resp.data)

    def test_no_cancelar_lo_que_va_en_ruta(self, client_a, despacho_a):
        client_a.post(f"{URL}{despacho_a}/iniciar-ruta/", {}, format="json")
        resp = client_a.post(f"{URL}{despacho_a}/cancelar/", {"motivo": "x"}, format="json")
        assert resp.status_code == 400

    def test_estado_terminal_no_transiciona(self, client_a, despacho_a):
        client_a.post(f"{URL}{despacho_a}/cancelar/", {"motivo": "x"}, format="json")
        resp = client_a.post(f"{URL}{despacho_a}/iniciar-ruta/", {}, format="json")
        assert resp.status_code == 400
        assert "terminal" in str(resp.data)

    def test_entregar_sin_receptor_400(self, client_a, despacho_a):
        client_a.post(f"{URL}{despacho_a}/iniciar-ruta/", {}, format="json")
        resp = client_a.post(f"{URL}{despacho_a}/entregar/", {}, format="json")
        assert resp.status_code == 400

    def test_devolver_sin_motivo_400(self, client_a, despacho_a):
        client_a.post(f"{URL}{despacho_a}/iniciar-ruta/", {}, format="json")
        resp = client_a.post(f"{URL}{despacho_a}/devolver/", {}, format="json")
        assert resp.status_code == 400

    def test_pdf_nota_entrega(self, client_a, despacho_a):
        resp = client_a.get(f"{URL}{despacho_a}/pdf/")
        assert resp.status_code == 200
        assert resp["Content-Type"] == "application/pdf"
        assert bytes(resp.content).startswith(b"%PDF")


# ── Filtros ───────────────────────────────────────────────────────────────────


class TestFiltros:
    def test_filtros_estado_transportista_nota_y_fechas(
        self, client_a, venta_a, transportista_a
    ):
        r1 = _crear_despacho_api(
            client_a,
            venta_a,
            lineas=[{"id_producto": str(venta_a["producto"].id_producto), "cantidad": "5"}],
            id_transportista=str(transportista_a.pk),
        )
        r2 = _crear_despacho_api(client_a, venta_a)  # resto pendiente
        client_a.post(f"{URL}{r2.data['id_despacho']}/iniciar-ruta/", {}, format="json")

        resp = client_a.get(URL, {"estado": "pendiente"})
        ids = {d["id_despacho"] for d in _resultados(resp.data)}
        assert ids == {r1.data["id_despacho"]}

        resp = client_a.get(URL, {"id_transportista": str(transportista_a.pk)})
        ids = {d["id_despacho"] for d in _resultados(resp.data)}
        assert ids == {r1.data["id_despacho"]}

        resp = client_a.get(URL, {"id_nota_venta": str(venta_a["nota"].id_nota_venta)})
        assert len(_resultados(resp.data)) == 2

        hoy = timezone.localdate().isoformat()
        resp = client_a.get(URL, {"fecha_desde": hoy, "fecha_hasta": hoy})
        assert len(_resultados(resp.data)) == 2
        resp = client_a.get(URL, {"fecha_desde": "2099-01-01"})
        assert len(_resultados(resp.data)) == 0

    def test_filtro_fecha_invalida_400(self, client_a):
        resp = client_a.get(URL, {"fecha_desde": "ayer"})
        assert resp.status_code == 400

    def test_search_por_numero(self, client_a, venta_a):
        r1 = _crear_despacho_api(client_a, venta_a)
        resp = client_a.get(URL, {"search": r1.data["numero_despacho"]})
        assert {d["id_despacho"] for d in _resultados(resp.data)} == {r1.data["id_despacho"]}


# ── Aislamiento multi-tenant (R-CODE-1) ───────────────────────────────────────


class TestAislamiento:
    def test_b_no_ve_ni_transiciona_despachos_de_a(self, client_a, client_b, venta_a):
        resp = _crear_despacho_api(client_a, venta_a)
        pk = resp.data["id_despacho"]

        resp = client_b.get(URL)
        assert pk not in {d["id_despacho"] for d in _resultados(resp.data)}
        assert client_b.get(f"{URL}{pk}/").status_code == 404
        resp = client_b.post(f"{URL}{pk}/iniciar-ruta/", {}, format="json")
        assert resp.status_code == 404
        despacho = Despacho.objects.get(pk=pk)
        assert despacho.estado_despacho == "PENDIENTE"  # B no lo movió

    def test_b_no_crea_despacho_sobre_venta_de_a(self, client_b, venta_a, venta_b):
        resp = client_b.post(
            f"{URL}desde-nota-venta/",
            {
                "id_nota_venta": str(venta_a["nota"].id_nota_venta),
                "almacen_id": str(venta_b["almacen"].id_almacen),
                "direccion_entrega": "Destino intruso",
            },
            format="json",
        )
        assert resp.status_code == 400
        assert Despacho.objects.count() == 0

    def test_create_directo_con_almacen_ajeno_400(self, client_b, venta_a):
        resp = client_b.post(
            URL,
            {
                "id_almacen_origen": str(venta_a["almacen"].id_almacen),
                "direccion_destino": "Destino intruso",
            },
            format="json",
        )
        assert resp.status_code == 400  # TenantFKScopeMixin: pk fuera de su tenant

    def test_detalles_aislados(self, client_a, client_b, venta_a):
        _crear_despacho_api(client_a, venta_a)
        assert DetalleDespacho.objects.count() == 1
        resp = client_b.get(URL_DETALLES)
        assert len(_resultados(resp.data)) == 0
        resp = client_a.get(URL_DETALLES)
        assert len(_resultados(resp.data)) == 1

    def test_transportista_de_otra_empresa_rechazado(self, client_a, venta_a, empresa_b):
        from apps.rrhh.models import Empleado

        chofer_b = Empleado.objects.create(
            empresa=empresa_b,
            nombre="Ajeno",
            apellido="Beta",
            cedula="V-00000001",
            fecha_ingreso=date(2025, 1, 1),
        )
        resp = _crear_despacho_api(client_a, venta_a, id_transportista=str(chofer_b.pk))
        assert resp.status_code == 400


# ── MCP: despachos pendientes ─────────────────────────────────────────────────


def _token(empresa, scopes):
    return CapabilityToken.objects.create(
        empresa=empresa, nombre="tok-despacho-test", scopes=scopes, activo=True
    )


class TestMCPDespachosPendientes:
    def test_lista_pendientes_y_en_ruta(self, client_a, empresa_a, venta_a, transportista_a):
        r1 = _crear_despacho_api(
            client_a,
            venta_a,
            lineas=[{"id_producto": str(venta_a["producto"].id_producto), "cantidad": "5"}],
            id_transportista=str(transportista_a.pk),
        )
        r2 = _crear_despacho_api(client_a, venta_a)
        client_a.post(f"{URL}{r2.data['id_despacho']}/iniciar-ruta/", {}, format="json")

        token = _token(empresa_a, ["despacho:read"])
        resultado = despacho_get_pendientes(str(token.token), str(empresa_a.id_empresa))
        numeros = {d["numero"] for d in resultado}
        assert numeros == {r1.data["numero_despacho"], r2.data["numero_despacho"]}
        primero = resultado[0]
        assert primero["cliente"] == venta_a["cliente"].razon_social
        assert primero["nota_venta"] == venta_a["nota"].numero_nota
        assert primero["transportista"] == "Carlos Chofer"

        solo_pendientes = despacho_get_pendientes(
            str(token.token), str(empresa_a.id_empresa), incluir_en_ruta=False
        )
        assert {d["estado"] for d in solo_pendientes} == {"PENDIENTE"}

    def test_scope_faltante_rechazado(self, empresa_a):
        token = _token(empresa_a, ["ventas:read"])
        with pytest.raises(PermissionError, match="despacho:read"):
            despacho_get_pendientes(str(token.token), str(empresa_a.id_empresa))

    def test_empresa_distinta_al_token_rechazada(self, empresa_a, empresa_b):
        token = _token(empresa_b, ["despacho:read"])
        with pytest.raises(PermissionError, match="tenant"):
            despacho_get_pendientes(str(token.token), str(empresa_a.id_empresa))

    def test_token_de_b_no_lista_despachos_de_a(self, client_a, empresa_b, venta_a):
        _crear_despacho_api(client_a, venta_a)
        token = _token(empresa_b, ["despacho:read"])
        resultado = despacho_get_pendientes(str(token.token), str(empresa_b.id_empresa))
        assert resultado == []

    def test_export_para_autodiscovery(self):
        assert [t["name"] for t in MCP_TOOLS] == ["despacho_get_pendientes"]
        assert all(t["scope"] == "despacho:read" for t in MCP_TOOLS)
