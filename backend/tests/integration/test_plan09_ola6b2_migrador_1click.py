"""Tests de integración Plan 09 Ola 6B-2: Migrador 1-Click Odoo (SOLO LECTURA) + Saint/Profit/Galac CSV."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import uuid
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.almacenes.models import Almacen
from apps.contabilidad.models import PlanCuentas
from apps.core.models import CapabilityToken, Usuarios
from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.models import CuentaPorCobrar
from apps.cuentas_por_pagar.models import CuentaPorPagar
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor
from apps.inventario.models import Producto, StockActual
from apps.migracion_datos.mcp import migracion_listar_formatos_1click, migracion_preview_1click
from apps.migracion_datos.migrador_1click import (
    MigracionError,
    MigracionReadOnlyError,
    OdooReadOnlyGuard,
    construir_guard_desde_conector,
    ejecutar_migracion_1click,
    preview_migracion_1click,
)
from apps.migracion_datos.models import DetalleErrorMigracion, ProcesoMigracion
from apps.proveedores.models import Proveedor

pytestmark = [pytest.mark.django_db]


def _crear_usuario_empresa(empresa, *, staff: bool = False):
    u = Usuarios.objects.create_user(
        username=f"usr_{uuid.uuid4().hex[:6]}",
        email=f"usr_{uuid.uuid4().hex[:6]}@omni.test",
        password="TestPass123!@#",
        is_staff=staff,
    )
    u.empresas.add(empresa)
    return u


def _crear_cap_token(empresa, user, scopes: list[str]) -> str:
    tok = CapabilityToken.objects.create(
        nombre=f"tok_{uuid.uuid4().hex[:6]}",
        empresa=empresa,
        creado_por=user,
        scopes=scopes,
    )
    return str(tok.token)


class _FakeOdooClient:
    """Cliente XML-RPC simulado en memoria para verificar llamadas estrictamente read-only."""

    def __init__(self, datasets: dict[str, list[dict]] | None = None) -> None:
        self.datasets = datasets or {}
        self.calls: list[tuple[str, str]] = []

    def call(self, model: str, method: str, domain=None, kwargs=None):
        self.calls.append((model, method))
        data = list(self.datasets.get(model, []))
        # Soporte básico de filtro [["id", "in", ids]] usado por stock y partners
        if (
            domain
            and isinstance(domain[0], list)
            and domain[0]
            and isinstance(domain[0][0], list)
            and len(domain[0][0]) >= 3
            and domain[0][0][0] == "id"
            and domain[0][0][1] == "in"
        ):
            ids = set(domain[0][0][2])
            data = [r for r in data if r.get("id") in ids]
        limite = int((kwargs or {}).get("limit") or len(data) or 500)
        return data[:limite]


def test_odoo_readonly_guard_bloquea_escrituras_y_valida_conector(empresa_a, empresa_b):
    fake = _FakeOdooClient({"res.lang": [{"id": 1}]})
    guard = OdooReadOnlyGuard(fake)

    assert guard.call("res.lang", "search_read", [[]], {"limit": 10}) == [{"id": 1}]
    assert guard.call("res.lang", "read", [[1]], {"fields": ["id"]}) == [{"id": 1}]
    assert guard.call("res.lang", "search_count", [[]]) == [{"id": 1}]
    assert guard.call("res.lang", "read_group", [[]]) == [{"id": 1}]
    assert guard.call("res.lang", "fields_get", [[]]) == [{"id": 1}]

    for metodo_prohibido in ("create", "write", "unlink", "action_post", "execute_kw"):
        with pytest.raises(MigracionReadOnlyError, match="SOLO LECTURA"):
            guard.call("res.partner", metodo_prohibido, [[{"name": "X"}]])

    assert [m for _, m in fake.calls] == ["search_read", "read", "search_count", "read_group", "fields_get"]

    prov_odoo, _ = ConectorProveedor.objects.get_or_create(
        codigo="odoo",
        defaults={"nombre": "Odoo ERP", "activo": True},
    )
    inst_b = ConectorInstancia.objects.create(
        id_empresa=empresa_b,
        id_proveedor=prov_odoo,
        nombre="Odoo Otro Tenant",
        configuracion={
            "host": "https://demo.odoo.local",
            "db": "demo_db",
            "user": "ro_user",
            "api_key": "ci-only-dummy-key-0001",
            "write_user": "w_user",
            "write_api_key": "ci-only-dummy-key-0002",
        },
        activo=True,
    )
    with pytest.raises(MigracionError, match="Conector Odoo no encontrado"):
        construir_guard_desde_conector(empresa_a, inst_b.pk)

    inst_a = ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=prov_odoo,
        nombre="Odoo Empresa A",
        configuracion={
            "host": "https://demo.odoo.local",
            "db": "demo_db",
            "user": "ro_user",
            "api_key": "ci-only-dummy-key-0001",
            "write_user": "w_user",
            "write_api_key": "ci-only-dummy-key-0002",
        },
        activo=True,
    )
    with patch("apps.migracion_datos.migrador_1click.OdooXMLRPCClient", return_value=fake) as mock_cls:
        guard_a = construir_guard_desde_conector(empresa_a, inst_a.pk)
        assert isinstance(guard_a, OdooReadOnlyGuard)
        mock_cls.assert_called_once_with(
            host="https://demo.odoo.local",
            db="demo_db",
            user="ro_user",
            api_key="ci-only-dummy-key-0001",
        )


def test_odoo_1click_cinco_entidades_preview_e_idempotencia(empresa_a, moneda_usd):
    user = _crear_usuario_empresa(empresa_a)
    almacen = Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Principal",
        codigo_almacen="ALM-01",
    )
    fake = _FakeOdooClient(
        {
            "account.account": [
                {
                    "id": 1,
                    "code": "1.1.01",
                    "name": "Caja Principal",
                    "account_type": "asset_cash",
                    "deprecated": False,
                },
                {
                    "id": 2,
                    "code": "4.1.01",
                    "name": "Ventas Locales",
                    "account_type": "income",
                    "deprecated": False,
                },
            ],
            "res.partner": [
                {
                    "id": 10,
                    "name": "Distribuidora Alfa CA",
                    "vat": "J-30111222-3",
                    "email": "alfa@test.ve",
                    "phone": "+584141112233",
                    "street": "Av Bolívar",
                    "customer_rank": 1,
                    "supplier_rank": 0,
                },
                {
                    "id": 11,
                    "name": "Insumos Beta SA",
                    "vat": "J-40999888-1",
                    "email": "beta@test.ve",
                    "phone": "+584129998877",
                    "street": "Zona Industrial",
                    "customer_rank": 0,
                    "supplier_rank": 2,
                },
            ],
            "product.template": [
                {
                    "id": 20,
                    "default_code": "LUB-15W40",
                    "name": "Aceite Mineral 15W40",
                    "list_price": 18.5,
                    "standard_price": 12.0,
                    "categ_id": [1, "Lubricantes"],
                    "uom_id": [1, "UND"],
                    "type": "consu",
                    "barcode": "7590001002003",
                }
            ],
            "stock.quant": [
                {
                    "id": 30,
                    "product_id": [200, "[LUB-15W40] Aceite Mineral 15W40"],
                    "location_id": [50, "ALM-01"],
                    "quantity": 45.0,
                    "reserved_quantity": 5.0,
                }
            ],
            "product.product": [{"id": 200, "default_code": "LUB-15W40"}],
            "stock.location": [{"id": 50, "name": "ALM-01", "complete_name": "WH/ALM-01"}],
            "account.move": [
                {
                    "id": 40,
                    "name": "FAC-0001",
                    "move_type": "out_invoice",
                    "partner_id": [10, "Distribuidora Alfa CA"],
                    "amount_residual": 120.5,
                    "invoice_date": "2026-11-01",
                    "invoice_date_due": "2026-11-15",
                    "ref": "NE-101",
                },
                {
                    "id": 41,
                    "name": "OC-FAC-09",
                    "move_type": "in_invoice",
                    "partner_id": [11, "Insumos Beta SA"],
                    "amount_residual": 310.0,
                    "invoice_date": "2026-11-02",
                    "invoice_date_due": "2026-12-02",
                    "ref": "PROV-9",
                },
            ],
        }
    )
    guard = OdooReadOnlyGuard(fake)

    # Preview no debe mutar BD
    prev_plan = preview_migracion_1click(empresa_a, fuente="ODOO", entidad="plan_cuentas", odoo_guard=guard)
    assert prev_plan["dry_run"] is True
    assert prev_plan["validos"] == 2
    assert PlanCuentas.objects.filter(id_empresa=empresa_a).count() == 0

    for entidad in ("plan_cuentas", "contactos", "productos", "stock", "cxc_cxp"):
        res1 = ejecutar_migracion_1click(empresa_a, user, fuente="ODOO", entidad=entidad, odoo_guard=guard)
        assert res1["estado_proceso"] == "COMPLETADO", res1
        assert res1["total_fallidos"] == 0

    assert PlanCuentas.objects.filter(id_empresa=empresa_a).count() == 2
    assert Cliente.objects.filter(id_empresa=empresa_a, rif="J-301112223").exists()
    assert Proveedor.objects.filter(id_empresa=empresa_a, rif="J-409998881").exists()
    prod = Producto.objects.get(id_empresa=empresa_a, sku="LUB-15W40")
    assert prod.id_moneda_precio == moneda_usd
    assert prod.costo_reposicion_usd == Decimal("12")
    stock = StockActual.objects.get(id_empresa=empresa_a, id_producto=prod, id_almacen=almacen)
    assert stock.cantidad_disponible == Decimal("40")
    cxc = CuentaPorCobrar.objects.get(empresa=empresa_a, referencia_externa="FAC-0001")
    assert cxc.monto == Decimal("120.50")
    cxp = CuentaPorPagar.objects.get(id_empresa=empresa_a, referencia_externa="OC-FAC-09")
    assert cxp.monto_pendiente == Decimal("310")

    # Segunda pasada: idempotente (actualizados, sin duplicados)
    for entidad in ("plan_cuentas", "contactos", "productos", "stock", "cxc_cxp"):
        res2 = ejecutar_migracion_1click(empresa_a, user, fuente="ODOO", entidad=entidad, odoo_guard=guard)
        assert res2["actualizados"] >= 1
        assert res2["creados"] == 0

    assert PlanCuentas.objects.filter(id_empresa=empresa_a).count() == 2
    assert Producto.objects.filter(id_empresa=empresa_a, sku="LUB-15W40").count() == 1
    assert CuentaPorCobrar.objects.filter(empresa=empresa_a, referencia_externa="FAC-0001").count() == 1
    assert all(method == "search_read" for _, method in fake.calls)


def test_saint_profit_galac_csv_parcial_y_errores(empresa_a, moneda_usd):
    user = _crear_usuario_empresa(empresa_a)

    # SAINT (delimitador ';' y columnas legacy) con 1 fila válida y 1 sin RIF
    csv_saint = (
        "CODCLIE;DESCRIP;RIF;TELEF;EMAIL;LIMITECRED;DIASCRED\n"
        "C001;Comercial Los Andes CA;j 29.888.777-4;04145550011;andes@test.ve;1500,50;15\n"
        "C002;Cliente Sin Rif;;04140000000;;;0\n"
    )
    prev = preview_migracion_1click(empresa_a, fuente="SAINT", entidad="contactos", contenido_csv=csv_saint)
    assert prev["total_detectados"] == 2
    assert prev["validos"] == 1
    assert prev["invalidos"] == 1
    assert Cliente.objects.filter(id_empresa=empresa_a).count() == 0

    ejec = ejecutar_migracion_1click(empresa_a, user, fuente="SAINT", entidad="contactos", contenido_csv=csv_saint)
    assert ejec["estado_proceso"] == "COMPLETADO_CON_ERRORES"
    assert ejec["creados"] == 1
    assert ejec["total_fallidos"] == 1
    cli = Cliente.objects.get(id_empresa=empresa_a, rif="J-298887774")
    assert cli.limite_credito == Decimal("1500.50")
    assert DetalleErrorMigracion.objects.filter(id_proceso_migracion_id=ejec["id_proceso_migracion"]).count() == 1

    # PROFIT (artículos) + GALAC (cartera CxC)
    csv_profit = "co_art;art_des;lin_des;co_uni;co_mone;cos_un;prec_vta1\nP-100;Filtro Aceite;Filtros;UND;USD;4.25;7.50\n"
    res_p = ejecutar_migracion_1click(empresa_a, user, fuente="PROFIT", entidad="productos", contenido_csv=csv_profit)
    assert res_p["estado_proceso"] == "COMPLETADO"
    assert Producto.objects.filter(id_empresa=empresa_a, sku="P-100").exists()

    csv_galac = (
        "Tipo,RIF,Documento,Saldo,Fecha,Vence\n"
        f"CXC,J29888777-4,F-GALAC-1,\"1.250,75\",{date(2026, 11, 1)},{date(2026, 11, 30)}\n"
    )
    res_g = ejecutar_migracion_1click(empresa_a, user, fuente="GALAC", entidad="cxc_cxp", contenido_csv=csv_galac)
    assert res_g["estado_proceso"] == "COMPLETADO"
    assert CuentaPorCobrar.objects.get(empresa=empresa_a, referencia_externa="F-GALAC-1").monto == Decimal("1250.75")


def test_http_endpoints_idempotencia_aislamiento_y_mcp(empresa_a, empresa_b):
    user = _crear_usuario_empresa(empresa_a)
    client = APIClient()

    # Anónimo bloqueado
    assert client.get("/api/migracion-datos/migrador-1click/formatos/").status_code == 401

    client.force_authenticate(user=user)
    fmt = client.get("/api/migracion-datos/migrador-1click/formatos/")
    assert fmt.status_code == 200
    assert fmt.data["odoo_solo_lectura"] is True
    assert "ODOO" in [f["codigo"] for f in fmt.data["fuentes"]]

    # NUL byte rechazado
    bad_nul = client.post(
        "/api/migracion-datos/migrador-1click/preview/",
        {
            "id_empresa": str(empresa_a.pk),
            "fuente": "SAINT",
            "entidad": "plan_cuentas",
            "contenido_csv": "CODCTA;DESCRIP\n1;Caja\x00",
        },
        format="json",
    )
    assert bad_nul.status_code == 400

    # Cross-tenant empresa rechazada
    cross = client.post(
        "/api/migracion-datos/migrador-1click/preview/",
        {
            "id_empresa": str(empresa_b.pk),
            "fuente": "GALAC",
            "entidad": "plan_cuentas",
            "contenido_csv": "Codigo,Descripcion\n1,Activo",
        },
        format="json",
    )
    assert cross.status_code == 403

    # Ejecución con Idempotency-Key + replay
    idem_key = f"mig-1click-{uuid.uuid4().hex[:8]}"
    payload = {
        "id_empresa": str(empresa_a.pk),
        "fuente": "GALAC",
        "entidad": "plan_cuentas",
        "contenido_csv": "Codigo,Descripcion,Tipo\n1.1,Banco Nacional,ACTIVO\n",
    }
    resp1 = client.post(
        "/api/migracion-datos/migrador-1click/ejecutar/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=idem_key,
    )
    assert resp1.status_code == 201
    resp2 = client.post(
        "/api/migracion-datos/migrador-1click/ejecutar/",
        payload,
        format="json",
        HTTP_IDEMPOTENCY_KEY=idem_key,
    )
    assert resp2.status_code == 201
    assert resp2.data["id_proceso_migracion"] == resp1.data["id_proceso_migracion"]
    assert ProcesoMigracion.objects.filter(id_empresa=empresa_a).count() == 1

    # MCP tools
    tok = _crear_cap_token(empresa_a, user, ["migracion_datos:read"])
    mcp_fmt = migracion_listar_formatos_1click(tok, str(empresa_a.pk))
    assert mcp_fmt["odoo_solo_lectura"] is True

    mcp_prev = migracion_preview_1click(
        tok,
        str(empresa_a.pk),
        fuente="PROFIT",
        entidad="plan_cuentas",
        contenido_csv="codigo;nombre;tipo\n5.1;Costo Ventas;COSTO\n",
    )
    assert mcp_prev["dry_run"] is True
    assert mcp_prev["validos"] == 1

    # MCP edge cases (NUL, UUID inválido, error controlado de migración)
    assert "error" in migracion_preview_1click(tok, str(empresa_a.pk), "ODOO", "stock", id_conector="bad\x00")
    assert "error" in migracion_preview_1click(tok, str(empresa_a.pk), "ODOO", "stock", id_conector="not-a-uuid")
    assert "error" in migracion_preview_1click(tok, str(empresa_a.pk), "SAINT", "stock", contenido_csv="")
    assert "error" in migracion_preview_1click(
        tok, str(empresa_a.pk), "ODOO", "stock", id_conector=str(uuid.uuid4())
    )

    # X-Empresa-ID header, empresa primaria sin id_empresa y errores serializer/endpoint
    no_emp_user = Usuarios.objects.create_user(
        username=f"noemp_{uuid.uuid4().hex[:6]}",
        email=f"noemp_{uuid.uuid4().hex[:6]}@omni.test",
        password="TestPass123!@#",
    )
    c_no = APIClient()
    c_no.force_authenticate(user=no_emp_user)
    assert (
        c_no.post(
            "/api/migracion-datos/migrador-1click/preview/",
            {"fuente": "SAINT", "entidad": "plan_cuentas", "contenido_csv": "codigo;nombre\n1;A\n"},
            format="json",
        ).status_code
        == 400
    )

    resp_hdr = client.post(
        "/api/migracion-datos/migrador-1click/preview/",
        {"fuente": "SAINT", "entidad": "plan_cuentas", "contenido_csv": "codigo;nombre\n1;A\n"},
        format="json",
        HTTP_X_EMPRESA_ID=str(empresa_a.pk),
    )
    assert resp_hdr.status_code == 200

    # Serializer validaciones (ODOO sin id_conector, SAINT sin contenido_csv, ejecutar ODOO inexistente -> 400)
    assert (
        client.post(
            "/api/migracion-datos/migrador-1click/preview/",
            {"id_empresa": str(empresa_a.pk), "fuente": "ODOO", "entidad": "productos"},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/migracion-datos/migrador-1click/preview/",
            {"id_empresa": str(empresa_a.pk), "fuente": "SAINT", "entidad": "productos", "contenido_csv": "   "},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/migracion-datos/migrador-1click/preview/",
            {
                "id_empresa": str(empresa_a.pk),
                "fuente": "ODOO",
                "entidad": "productos",
                "id_conector": str(uuid.uuid4()),
            },
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/migracion-datos/migrador-1click/ejecutar/",
            {
                "id_empresa": str(empresa_a.pk),
                "fuente": "ODOO",
                "entidad": "productos",
                "id_conector": str(uuid.uuid4()),
            },
            format="json",
        ).status_code
        == 400
    )


def test_migrador_1click_cobertura_bordes_y_errores(empresa_a, moneda_usd):
    from apps.integration_hub.connectors.odoo.client import OdooAuthError, OdooCallError
    from apps.migracion_datos.migrador_1click import (
        _a_decimal,
        _a_fecha,
        _aplicar_fila_normalizada,
        _decodificar_csv,
        _normalizar_rif,
    )

    user = _crear_usuario_empresa(empresa_a)
    Almacen.objects.create(id_empresa=empresa_a, nombre_almacen="Sec", codigo_almacen="ALM-02")

    # Helpers decodificación / fechas / decimales / RIF
    assert _decodificar_csv("codigo\tnombre\n1.2.1\tCaja\n".encode("latin-1")).startswith("codigo")
    with pytest.raises(MigracionError):
        _decodificar_csv(b"   ")
    assert _normalizar_rif("VE J-12345678-9") == "J-123456789"
    assert _a_decimal("1,234.50", "monto") == Decimal("1234.50")
    assert _a_decimal("", "monto", default=Decimal("5")) == Decimal("5")
    with pytest.raises(MigracionError):
        _a_decimal("", "monto")
    with pytest.raises(MigracionError):
        _a_decimal("abc", "monto")
    assert _a_fecha(date(2026, 1, 2), "f") == date(2026, 1, 2)
    assert _a_fecha("02/01/2026", "f") == date(2026, 1, 2)
    with pytest.raises(MigracionError):
        _a_fecha("", "f")
    with pytest.raises(MigracionError):
        _a_fecha("no-fecha", "f")

    # Guard edge cases & Odoo errors
    bad_guard = OdooReadOnlyGuard(object())
    with pytest.raises(MigracionError, match="carece de método call"):
        bad_guard.call("res.partner", "search_read")
    assert OdooReadOnlyGuard._m2o_id(False) is None
    assert OdooReadOnlyGuard._m2o_id("bad") is None
    assert OdooReadOnlyGuard._m2o_id([42, "Nombre"]) == 42
    assert OdooReadOnlyGuard._m2o_name(False) == ""

    prov_odoo, _ = ConectorProveedor.objects.get_or_create(codigo="odoo", defaults={"nombre": "Odoo", "activo": True})
    inst_incompleta = ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=prov_odoo,
        nombre="Odoo Incompleto",
        configuracion={"host": "https://demo.odoo.local"},
        activo=True,
    )
    with pytest.raises(MigracionError, match="no tiene credenciales"):
        construir_guard_desde_conector(empresa_a, inst_incompleta.pk)

    inst_ok = ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=prov_odoo,
        nombre="Odoo OK Edge",
        configuracion={
            "host": "https://demo.odoo.local",
            "db": "demo_db",
            "user": "ro_user",
            "api_key": "ci-only-dummy-key-0001",
        },
        activo=True,
    )
    with patch("apps.migracion_datos.migrador_1click.OdooXMLRPCClient", side_effect=OdooAuthError("bad creds")):
        with pytest.raises(MigracionError, match="autenticando"):
            construir_guard_desde_conector(empresa_a, inst_ok.pk)

    class _ErrOdooClient:
        def call(self, *args, **kwargs):
            raise OdooCallError("rpc fault")

    with pytest.raises(MigracionError, match="Error leyendo"):
        preview_migracion_1click(
            empresa_a,
            fuente="ODOO",
            entidad="productos",
            odoo_guard=OdooReadOnlyGuard(_ErrOdooClient()),
        )

    # Validación de fuente/entidad/límite y fallback FALLIDO total
    with pytest.raises(MigracionError):
        preview_migracion_1click(empresa_a, fuente="OTRA", entidad="stock", contenido_csv="x\n")
    with pytest.raises(MigracionError):
        preview_migracion_1click(empresa_a, fuente="SAINT", entidad="desconocida", contenido_csv="x\n")
    with pytest.raises(MigracionError):
        preview_migracion_1click(empresa_a, fuente="SAINT", entidad="stock", contenido_csv="x\n", limite=9999)
    with pytest.raises(MigracionError):
        preview_migracion_1click(empresa_a, fuente="ODOO", entidad="stock")

    # Cobertura variantes plan_cuentas, contactos AMBOS + updates, productos SERVICIO/KIT, stock errors, cxc_cxp errors
    csv_plan = (
        "codigo\tnombre\ttipo\tnaturaleza\tnivel\tactivo\n"
        "2.1\tCuentas por Pagar\tPASIVO\tA\t2\t1\n"
        "3.1\tCapital\tPATRIMONIO\t\t2\t1\n"
        "6.1\tGastos\tGASTO\tD\t2\t0\n"
        "7.1\tTipoMal\tINVALIDO\tD\t1\t1\n"
        "8.1\tNivelMal\tACTIVO\tD\tabc\t1\n"
    )
    r_plan = ejecutar_migracion_1click(empresa_a, user, fuente="OMNI_CSV", entidad="plan_cuentas", contenido_csv=csv_plan)
    assert r_plan["estado_proceso"] == "COMPLETADO_CON_ERRORES"
    assert r_plan["total_exitosos"] == 3
    assert r_plan["total_fallidos"] == 2

    csv_cont = (
        "razon_social;rif;rol;tipo_cliente;limite_credito;dias_credito\n"
        "Socio Dual CA;J-501112223;AMBOS;CREDITO;500;30\n"
        "Rol Mal;J-501112224;OTRO;CONTADO;0;0\n"
        "Dias Mal;J-501112225;CLIENTE;CONTADO;0;abc\n"
    )
    r_cont1 = ejecutar_migracion_1click(empresa_a, user, fuente="SAINT", entidad="contactos", contenido_csv=csv_cont)
    assert r_cont1["creados"] == 1
    assert r_cont1["total_fallidos"] == 2
    # Update rol AMBOS segunda pasada
    csv_cont_up = "razon_social;rif;rol;tipo_cliente\nSocio Dual Upd;J-501112223;AMBOS;OTRO\n"
    r_cont2 = ejecutar_migracion_1click(empresa_a, user, fuente="SAINT", entidad="contactos", contenido_csv=csv_cont_up)
    assert r_cont2["actualizados"] == 1

    csv_prod = (
        "sku;nombre_producto;categoria;unidad_medida;moneda;tipo_producto;costo_promedio;precio_venta_sugerido\n"
        "SRV-1;Consultoria;Servicios;SRV;USD;service;10;25\n"
        "KIT-1;Combo;Combos;UND;USD;kit;5;12\n"
        "BAD-MON;Sin Moneda;G;UND;ZZZ;consu;1;2\n"
        "BAD-TIPO;Tipo Mal;G;UND;USD;raro;1;2\n"
    )
    r_prod = ejecutar_migracion_1click(empresa_a, user, fuente="SAINT", entidad="productos", contenido_csv=csv_prod)
    assert r_prod["creados"] == 2
    assert r_prod["total_fallidos"] == 2
    # Update existing product + missing SKU on stock
    csv_prod_up = "sku;nombre_producto;moneda;tipo_producto\nSRV-1;Consultoria Upd;USD;service\n"
    assert ejecutar_migracion_1click(empresa_a, user, fuente="SAINT", entidad="productos", contenido_csv=csv_prod_up)["actualizados"] == 1

    csv_stock = "sku;almacen;cantidad_disponible\nKIT-1;ALM-02;15\nNO-SKU;ALM-02;5\nKIT-1;NO-ALM;5\n"
    r_stk = ejecutar_migracion_1click(empresa_a, user, fuente="SAINT", entidad="stock", contenido_csv=csv_stock)
    assert r_stk["creados"] == 1
    assert r_stk["total_fallidos"] == 2
    assert ejecutar_migracion_1click(empresa_a, user, fuente="SAINT", entidad="stock", contenido_csv="sku;almacen;cantidad_disponible\nKIT-1;ALM-02;20\n")["actualizados"] == 1

    # CXP crear + actualizar + errores totales FALLIDO
    csv_cxp = (
        "tipo,rif,referencia_externa,monto,fecha_emision,fecha_vencimiento\n"
        "CXP,J-501112223,FACT-P-1,200,2026-11-01,2026-11-30\n"
        "CXC,J-999999999,NO-CLI,10,2026-11-01,2026-11-30\n"
        "CXP,J-999999998,NO-PROV,10,2026-11-01,2026-11-30\n"
        "BAD,J-501112223,X,10,2026-11-01,2026-11-30\n"
        "CXP,J-501112223,NEG,-5,2026-11-01,2026-11-30\n"
    )
    r_cxp = ejecutar_migracion_1click(empresa_a, user, fuente="GALAC", entidad="cxc_cxp", contenido_csv=csv_cxp)
    assert r_cxp["creados"] == 1
    assert r_cxp["total_fallidos"] == 4
    r_cxp_up = ejecutar_migracion_1click(
        empresa_a,
        user,
        fuente="GALAC",
        entidad="cxc_cxp",
        contenido_csv="tipo,rif,referencia_externa,monto,fecha_emision\nCXP,J-501112223,FACT-P-1,180,2026-11-01\n",
    )
    assert r_cxp_up["actualizados"] == 1

    r_fail = ejecutar_migracion_1click(
        empresa_a,
        user,
        fuente="GALAC",
        entidad="stock",
        contenido_csv="sku,almacen,cantidad_disponible\nNO-EXISTE,NO-ALM,1\n",
    )
    assert r_fail["estado_proceso"] == "FALLIDO"
    with pytest.raises(MigracionError):
        _aplicar_fila_normalizada(empresa_a, "otra", {})
