"""Tests de integración PR-36 (Plan 09 · Ola 1B-1):
Contabilidad Dual (Fiscal/Gerencial), Trimonetaria (Base/País BCV/Referencia)
y Analítica (Centros de Costo + RLS PostgreSQL).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, ProgrammingError, connection, transaction
from django.utils import timezone

from apps.contabilidad.mcp import (
    contabilidad_balance_comprobacion,
    contabilidad_balance_general,
    contabilidad_estado_resultados,
    contabilidad_libro_mayor_auxiliar,
    contabilidad_listar_centros_costo,
)
from apps.contabilidad.models import (
    AsientoContable,
    CentroCosto,
    DiarioContable,
    MapeoContable,
    PlanCuentas,
)
from apps.contabilidad.services import (
    AsientoError,
    aprobar_asiento,
    generar_asiento,
    generar_asiento_o_fallar,
    revertir_asiento,
)
from apps.contabilidad.services_reportes import (
    ReporteContableError,
    ReporteTenantError,
    generar_balance_comprobacion,
    generar_balance_general,
    generar_estado_resultados,
    generar_libro_mayor_auxiliar,
)
from apps.core import rls
from apps.core.models import CapabilityToken
from apps.finanzas.models import Moneda, MonedaEmpresaActiva, TasaCambio, TipoTasaCambio

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

URL_CC = "/api/contabilidad/centros-costo/"
URL_DIARIOS = "/api/contabilidad/diarios/"
URL_BC = "/api/contabilidad/reportes/balance-comprobacion/"
URL_PNL = "/api/contabilidad/reportes/estado-resultados/"
URL_BG = "/api/contabilidad/reportes/balance-general/"
URL_MAYOR = "/api/contabilidad/reportes/libro-mayor-auxiliar/"


def _cuenta(empresa, codigo: str, nombre: str, tipo: str, naturaleza: str) -> PlanCuentas:
    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=nombre,
        tipo_cuenta=tipo,
        naturaleza=naturaleza,
        nivel=2,
    )


def _token(empresa, scopes: list[str]) -> str:
    tok = CapabilityToken.objects.create(empresa=empresa, nombre="tok-dual", scopes=scopes)
    return str(tok.token)


@pytest.fixture
def monedas_trimonetarias(db, empresa_a, moneda_usd):
    """Configura Base=USD, País=VES (tasa oficial BCV=40) y Referencia=USDT (tasa=1.05)."""
    ves = Moneda.objects.create(codigo_iso="VES", nombre="Bolívar", simbolo="Bs.", tipo_moneda="fiat")
    usdt = Moneda.objects.create(codigo_iso="USDT", nombre="Tether USD", simbolo="USDT", tipo_moneda="crypto")
    empresa_a.id_moneda_base = moneda_usd
    empresa_a.id_moneda_pais = ves
    empresa_a.save(update_fields=["id_moneda_base", "id_moneda_pais"])

    MonedaEmpresaActiva.objects.create(
        empresa=empresa_a,
        moneda=usdt,
        activa=True,
        es_moneda_referencia=True,
    )

    tt_bcv, _ = TipoTasaCambio.objects.get_or_create(
        id_empresa=None,
        codigo="OFICIAL_BCV",
        defaults={"nombre": "Oficial BCV", "es_oficial_fiscal": True, "prioridad": 1},
    )
    tt_usdt = TipoTasaCambio.objects.create(
        id_empresa=empresa_a,
        codigo="USDT_PAR",
        nombre="USDT Diario",
        es_oficial_fiscal=False,
        prioridad=10,
    )
    hoy = timezone.localdate()
    TasaCambio.objects.create(
        id_empresa=empresa_a,
        id_moneda_origen=moneda_usd,
        id_moneda_destino=ves,
        id_tipo_tasa=tt_bcv,
        tipo_tasa="OFICIAL_BCV",
        valor_tasa=Decimal("40.00000000"),
        fecha_tasa=hoy,
    )
    TasaCambio.objects.create(
        id_empresa=empresa_a,
        id_moneda_origen=moneda_usd,
        id_moneda_destino=usdt,
        id_tipo_tasa=tt_usdt,
        tipo_tasa="PERSONALIZADA",
        valor_tasa=Decimal("1.05000000"),
        fecha_tasa=hoy,
    )
    return {"usd": moneda_usd, "ves": ves, "usdt": usdt}


@pytest.fixture
def plan_dual(empresa_a):
    return {
        "caja": _cuenta(empresa_a, "1.1.01", "Caja General", "ACTIVO", "DEUDORA"),
        "ingreso": _cuenta(empresa_a, "4.1.01", "Ingresos Ventas", "INGRESO", "ACREEDORA"),
        "gasto": _cuenta(empresa_a, "6.1.01", "Gasto Operativo", "GASTO", "DEUDORA"),
    }


def test_rls_centro_costo_aislamiento_y_with_check(rls_test_role, empresa_a, empresa_b):
    """RLS en PostgreSQL aísla contabilidad_centro_costo en SELECT e INSERT cross-tenant."""
    rls.apply_system_default()
    cc_a = CentroCosto.objects.create(id_empresa=empresa_a, codigo="CC-A", nombre="Alpha Logística", tipo="LOGISTICA")
    cc_b = CentroCosto.objects.create(id_empresa=empresa_b, codigo="CC-B", nombre="Beta Comercial", tipo="COMERCIAL")

    try:
        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')

        rls.apply_context([empresa_a.id_empresa], bypass=False)
        visibles_a = set(CentroCosto.objects.values_list("id_centro_costo", flat=True))
        assert visibles_a == {cc_a.id_centro_costo}

        rls.apply_context([empresa_b.id_empresa], bypass=False)
        visibles_b = set(CentroCosto.objects.values_list("id_centro_costo", flat=True))
        assert visibles_b == {cc_b.id_centro_costo}

        # WITH CHECK debe rechazar insertar un centro de costo de B bajo el contexto de A
        rls.apply_context([empresa_a.id_empresa], bypass=False)
        with pytest.raises((IntegrityError, ProgrammingError)):
            with transaction.atomic():
                CentroCosto.objects.create(
                    id_empresa=empresa_b, codigo="CC-INTRUSO", nombre="Intruso", tipo="OPERATIVO"
                )
    finally:
        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute("RESET ROLE")
        rls.apply_system_default()


def test_centro_costo_api_crud_jerarquia_y_aislamiento(client_a, client_b, empresa_a, empresa_b, plan_dual):
    """CRUD de CentroCostoViewSet + validaciones cross-tenant y autociclo."""
    # Crear raíz en A
    res_padre = client_a.post(
        URL_CC,
        {"id_empresa": str(empresa_a.pk), "codigo": "OPS", "nombre": "Operaciones", "tipo": "OPERATIVO"},
        format="json",
    )
    assert res_padre.status_code == 201, res_padre.json()
    padre_id = res_padre.json()["id_centro_costo"]

    # Crear hijo en A
    res_hijo = client_a.post(
        URL_CC,
        {
            "id_empresa": str(empresa_a.pk),
            "codigo": "OPS-LOG",
            "nombre": "Despacho Urbano",
            "tipo": "LOGISTICA",
            "id_padre": padre_id,
        },
        format="json",
    )
    assert res_hijo.status_code == 201
    hijo_id = res_hijo.json()["id_centro_costo"]
    assert res_hijo.json()["padre_nombre"] == "Operaciones"

    # Autociclo rechazado (400)
    res_ciclo = client_a.patch(f"{URL_CC}{padre_id}/", {"id_padre": padre_id}, format="json")
    assert res_ciclo.status_code == 400

    # B no ve los centros de costo de A (404 / lista vacía)
    assert client_b.get(f"{URL_CC}{padre_id}/").status_code == 404
    res_b = client_b.post(
        URL_CC,
        {"id_empresa": str(empresa_b.pk), "codigo": "B-01", "nombre": "Beta CC", "tipo": "COMERCIAL"},
        format="json",
    )
    assert res_b.status_code == 201
    cc_b_id = res_b.json()["id_centro_costo"]

    # A no puede usar id_padre de B
    res_cross = client_a.patch(f"{URL_CC}{hijo_id}/", {"id_padre": cc_b_id}, format="json")
    assert res_cross.status_code == 400

    # Filtro NUL byte seguro -> 400
    assert client_a.get(f"{URL_CC}?tipo=%00").status_code == 400

    # Validación cross-tenant de id_diario en AsientoContable y id_centro_costo en DetalleAsiento
    diario_b = DiarioContable.objects.create(
        id_empresa=empresa_b, codigo="GER-B", nombre="Gerencial B", tipo="VARIOS", ambito="GERENCIAL"
    )
    res_as_cross = client_a.post(
        "/api/contabilidad/asientos-contables/",
        {
            "id_empresa": str(empresa_a.pk),
            "id_diario": str(diario_b.pk),
            "fecha_asiento": str(timezone.localdate()),
            "numero_asiento": "TEST-CROSS-1",
            "descripcion": "Cross diario",
            "estado_asiento": "BORRADOR",
        },
        format="json",
    )
    assert res_as_cross.status_code == 400

    asiento_a = AsientoContable.objects.create(
        id_empresa=empresa_a,
        fecha_asiento=timezone.localdate(),
        numero_asiento="TEST-A-1",
        descripcion="Asiento A",
        estado_asiento="BORRADOR",
    )
    res_det_cross = client_a.post(
        "/api/contabilidad/detalles-asiento/",
        {
            "id_asiento": str(asiento_a.pk),
            "id_cuenta_contable": str(plan_dual["caja"].pk),
            "id_centro_costo": cc_b_id,
            "debe": "10.00",
            "haber": "0.00",
        },
        format="json",
    )
    assert res_det_cross.status_code == 400

    # Filtrado de DiarioContable por ambito via API
    res_diario = client_a.post(
        URL_DIARIOS,
        {
            "id_empresa": str(empresa_a.pk),
            "codigo": "GER",
            "nombre": "Diario Gerencial",
            "tipo": "VENTAS",
            "ambito": "GERENCIAL",
        },
        format="json",
    )
    assert res_diario.status_code == 201
    assert res_diario.json()["ambito"] == "GERENCIAL"
    assert len(client_a.get(f"{URL_DIARIOS}?ambito=GERENCIAL").json().get("results", [])) >= 1


def test_generar_y_revertir_asiento_dual_trimonetario_y_centro_costo(
    empresa_a, empresa_b, monedas_trimonetarias, plan_dual
):
    """generar_asiento persiste ambito, centro_costo, e importes Base/País/Referencia y revertir_asiento los preserva."""
    MapeoContable.objects.create(
        id_empresa=empresa_a,
        tipo_asiento="FACTURA_VENTA",
        cuenta_debe=plan_dual["caja"],
        cuenta_haber=plan_dual["ingreso"],
        descripcion_plantilla="Venta {numero}",
        activo=True,
    )
    diario_ger = DiarioContable.objects.create(
        id_empresa=empresa_a,
        codigo="NVG",
        nombre="Notas de Venta Gerenciales",
        tipo="VARIOS",
        ambito="GERENCIAL",
        prefijo_secuencia="NVG",
    )
    MapeoContable.objects.create(
        id_empresa=empresa_a,
        tipo_asiento="GASTO",
        id_diario=diario_ger,
        cuenta_debe=plan_dual["gasto"],
        cuenta_haber=plan_dual["caja"],
        descripcion_plantilla="Gasto {numero}",
        activo=True,
    )
    cc_log = CentroCosto.objects.create(id_empresa=empresa_a, codigo="CC-LOG", nombre="Flota Norte", tipo="LOGISTICA")
    cc_b = CentroCosto.objects.create(id_empresa=empresa_b, codigo="CC-B", nombre="Ajeno", tipo="OPERATIVO")

    doc_fiscal = SimpleNamespace(pk=uuid.uuid4(), id_empresa=empresa_a, numero_factura="FAC-100", ambito="FISCAL")
    asiento_f = generar_asiento("FACTURA_VENTA", doc_fiscal, empresa_a, monto=Decimal("100.00"), centro_costo=cc_log)
    assert asiento_f.ambito == "FISCAL"
    det_debe = asiento_f.detalleasiento_set.get(debe__gt=0)
    assert det_debe.id_centro_costo == cc_log
    assert det_debe.debe_base == Decimal("100.00")
    assert det_debe.debe_pais == Decimal("4000.00")
    assert det_debe.debe_referencia == Decimal("105.00")
    assert det_debe.tasa_bcv_aplicada == Decimal("40.00000000")
    assert det_debe.tasa_referencia_aplicada == Decimal("1.05000000")

    # Documento heredando ámbito GERENCIAL desde su diario cuando no se pasa explícito
    doc_ger = SimpleNamespace(pk=uuid.uuid4(), id_empresa=empresa_a, numero_nota="NV-001")
    asiento_g, err = generar_asiento_o_fallar("GASTO", doc_ger, empresa_a, monto=Decimal("20.00"), centro_costo=cc_log)
    assert err is None and asiento_g is not None
    assert asiento_g.ambito == "GERENCIAL"

    # Error con ámbito inválido o centro de costo de otro tenant
    with pytest.raises(AsientoError):
        generar_asiento("FACTURA_VENTA", doc_fiscal, empresa_a, monto=Decimal("10.00"), ambito="OTRO")
    with pytest.raises(AsientoError):
        generar_asiento("FACTURA_VENTA", doc_fiscal, empresa_a, monto=Decimal("10.00"), centro_costo=cc_b)

    # Reversión preserva ámbito, centro de costo, tasas e invierte montos trimonetarios
    aprobar_asiento(asiento_f)
    contra = revertir_asiento(asiento_f, motivo="Anulación controlada")
    assert contra.ambito == "FISCAL"
    contra_haber = contra.detalleasiento_set.get(haber__gt=0)
    assert contra_haber.id_centro_costo == cc_log
    assert contra_haber.haber_base == Decimal("100.00")
    assert contra_haber.haber_pais == Decimal("4000.00")
    assert contra_haber.haber_referencia == Decimal("105.00")
    assert contra_haber.tasa_bcv_aplicada == Decimal("40.00000000")


def test_asiento_trimonetario_fallback_sin_tasas_y_misma_moneda_pais(empresa_b, moneda_usd):
    """Sin tasas configuradas no aborta la contabilización; si base==país resuelve país=base."""
    caja = _cuenta(empresa_b, "1.1.01", "Caja B", "ACTIVO", "DEUDORA")
    ing = _cuenta(empresa_b, "4.1.01", "Ingreso B", "INGRESO", "ACREEDORA")
    MapeoContable.objects.create(
        id_empresa=empresa_b,
        tipo_asiento="FACTURA_VENTA",
        cuenta_debe=caja,
        cuenta_haber=ing,
        descripcion_plantilla="Venta {numero}",
        activo=True,
    )
    # Caso A: empresa sin id_moneda_pais
    hoy = timezone.localdate()
    doc = SimpleNamespace(pk=uuid.uuid4(), id_empresa=empresa_b, numero_factura="B-1")
    asiento = generar_asiento("FACTURA_VENTA", doc, empresa_b, monto=Decimal("50.00"), ambito="GERENCIAL")
    aprobar_asiento(asiento)
    d = asiento.detalleasiento_set.get(debe__gt=0)
    assert d.debe_base == Decimal("50.00")
    assert d.debe_pais is None
    assert d.debe_referencia is None

    # Caso B: id_moneda_pais == id_moneda_base pero sin Referencia (TasaCambioError en país/ref manejado)
    empresa_b.id_moneda_pais = moneda_usd
    empresa_b.save(update_fields=["id_moneda_pais"])
    doc2 = SimpleNamespace(pk=uuid.uuid4(), id_empresa=empresa_b, numero_factura="B-2")
    asiento2 = generar_asiento("FACTURA_VENTA", doc2, empresa_b, monto=Decimal("30.00"))
    aprobar_asiento(asiento2)
    d2 = asiento2.detalleasiento_set.get(debe__gt=0)
    assert d2.debe_base == Decimal("30.00")
    assert d2.debe_pais == Decimal("30.00")

    # Reporte en moneda=PAIS con base==pais usa fallback a debe/haber si no hay debe_pais
    rep_pnl = generar_estado_resultados(empresa_b, fecha_desde=hoy, fecha_hasta=hoy, moneda="PAIS")
    assert rep_pnl["total_ingresos"] == Decimal("80.00")


def test_reportes_dual_trimonetario_analitico_http_y_mcp(
    client_a, empresa_a, empresa_b, monedas_trimonetarias, plan_dual
):
    """Los 4 reportes y herramientas MCP filtran por ámbito dual, moneda (BASE/PAIS/REFERENCIA) y CentroCosto."""
    cc_norte = CentroCosto.objects.create(
        id_empresa=empresa_a, codigo="CC-NORTE", nombre="Zona Norte", tipo="COMERCIAL"
    )
    cc_sur = CentroCosto.objects.create(id_empresa=empresa_a, codigo="CC-SUR", nombre="Zona Sur", tipo="LOGISTICA")
    cc_b = CentroCosto.objects.create(
        id_empresa=empresa_b, codigo="CC-AJENO", nombre="Ajeno", tipo="OPERATIVO", activo=False
    )

    hoy = timezone.localdate()
    MapeoContable.objects.create(
        id_empresa=empresa_a,
        tipo_asiento="FACTURA_VENTA",
        cuenta_debe=plan_dual["caja"],
        cuenta_haber=plan_dual["ingreso"],
        descripcion_plantilla="Vta {numero}",
        activo=True,
    )
    MapeoContable.objects.create(
        id_empresa=empresa_a,
        tipo_asiento="GASTO",
        cuenta_debe=plan_dual["gasto"],
        cuenta_haber=plan_dual["caja"],
        descripcion_plantilla="Gto {numero}",
        activo=True,
    )

    # Asiento FISCAL 100 USD en CC Norte (4000 VES / 105 USDT)
    asiento_f = generar_asiento(
        "FACTURA_VENTA",
        SimpleNamespace(pk=uuid.uuid4(), id_empresa=empresa_a, numero_factura="F-01"),
        empresa_a,
        monto=Decimal("100.00"),
        ambito="FISCAL",
        centro_costo=cc_norte,
    )
    aprobar_asiento(asiento_f)
    # Asiento GERENCIAL 40 USD en CC Sur (1600 VES / 42 USDT)
    asiento_g = generar_asiento(
        "GASTO",
        SimpleNamespace(pk=uuid.uuid4(), id_empresa=empresa_a, numero_factura="NV-02"),
        empresa_a,
        monto=Decimal("40.00"),
        ambito="GERENCIAL",
        centro_costo=cc_sur,
    )
    aprobar_asiento(asiento_g)

    # Servicio: FISCAL vs GERENCIAL vs CONSOLIDADO
    pnl_fiscal = generar_estado_resultados(empresa_a, fecha_desde=hoy, fecha_hasta=hoy, ambito="FISCAL", moneda="PAIS")
    assert pnl_fiscal["total_ingresos"] == Decimal("4000.00")
    assert pnl_fiscal["total_gastos"] == Decimal("0.00")

    pnl_ger = generar_estado_resultados(
        empresa_a, fecha_desde=hoy, fecha_hasta=hoy, ambito="GERENCIAL", moneda="REFERENCIA"
    )
    assert pnl_ger["total_ingresos"] == Decimal("0.00")
    assert pnl_ger["total_gastos"] == Decimal("42.00")

    bc_cc = generar_balance_comprobacion(
        empresa_a, fecha_desde=hoy, fecha_hasta=hoy, id_centro_costo=cc_norte, moneda="BASE"
    )
    assert bc_cc["total_debe"] == Decimal("100.00")
    assert bc_cc["centro_costo_nombre"] == "Zona Norte"

    bg_ger = generar_balance_general(
        empresa_a, fecha_corte=hoy, ambito="GERENCIAL", moneda="PAIS", id_centro_costo=str(cc_sur.pk)
    )
    assert bg_ger["moneda_reporte"] == "PAIS"
    assert bg_ger["ambito"] == "GERENCIAL"

    mayor_ref = generar_libro_mayor_auxiliar(
        empresa_a,
        id_cuenta_contable=plan_dual["caja"],
        ambito="FISCAL",
        moneda="REFERENCIA",
        id_centro_costo=cc_norte,
    )
    assert mayor_ref["total_debe"] == Decimal("105.00")
    assert mayor_ref["movimientos"][0]["centro_costo_nombre"] == "Zona Norte"

    # Errores esperados (400 / 404)
    with pytest.raises(ReporteContableError):
        generar_balance_comprobacion(empresa_a, ambito="INV")
    with pytest.raises(ReporteContableError):
        generar_balance_comprobacion(empresa_a, moneda="EUR")
    with pytest.raises(ReporteTenantError):
        generar_balance_comprobacion(empresa_a, id_centro_costo=cc_b)

    # HTTP GET en los 4 endpoints
    for url in (URL_BC, URL_PNL, URL_BG, URL_MAYOR):
        r_ok = client_a.get(
            url,
            {
                "empresa_id": str(empresa_a.pk),
                "ambito": "FISCAL",
                "moneda": "PAIS",
                "id_centro_costo": str(cc_norte.pk),
            },
        )
        assert r_ok.status_code == 200
        data = r_ok.json()
        assert data["ambito"] == "FISCAL"
        assert data["moneda_reporte"] == "PAIS"
        assert data["centro_costo_nombre"] == "Zona Norte"

        assert client_a.get(url, {"empresa_id": str(empresa_a.pk), "id_centro_costo": str(cc_b.pk)}).status_code == 404
        assert client_a.get(url, {"empresa_id": str(empresa_a.pk), "ambito": "XXX"}).status_code == 400
        assert client_a.get(url, {"empresa_id": str(empresa_a.pk), "moneda": "XXX"}).status_code == 400

    # MCP Tools
    tok = _token(empresa_a, ["contabilidad:read"])
    emp_id = str(empresa_a.pk)

    res_cc_mcp = contabilidad_listar_centros_costo(tok, emp_id, tipo="LOGISTICA", solo_activos=True)
    assert len(res_cc_mcp["centros_costo"]) == 1
    assert res_cc_mcp["centros_costo"][0]["codigo"] == "CC-SUR"
    assert "error" in contabilidad_listar_centros_costo(tok, emp_id, tipo="BAD\x00")

    mcp_bc = contabilidad_balance_comprobacion(
        tok, emp_id, ambito="FISCAL", moneda="REFERENCIA", id_centro_costo=str(cc_norte.pk)
    )
    assert mcp_bc["total_debe"] == "105.00"
    mcp_pnl = contabilidad_estado_resultados(
        tok, emp_id, fecha_desde=str(hoy), fecha_hasta=str(hoy), ambito="GERENCIAL", moneda="PAIS"
    )
    assert mcp_pnl["total_gastos"] == "1600.00"
    mcp_bg = contabilidad_balance_general(tok, emp_id, fecha_corte=str(hoy), ambito="FISCAL", moneda="BASE")
    assert mcp_bg["total_activos"] == "100.00"
    mcp_mayor = contabilidad_libro_mayor_auxiliar(
        tok, emp_id, id_cuenta_contable=str(plan_dual["caja"].pk), ambito="FISCAL", moneda="PAIS"
    )
    assert mcp_mayor["total_debe"] == "4000.00"
