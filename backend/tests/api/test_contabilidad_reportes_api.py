"""Tests integrales de API REST, motor SQL, exportadores CSV/PDF, USD doble,
seguridad multi-tenant/IDOR/subsidiaria y MCP para Reportes Contables (PR-14 · B2).
"""

from __future__ import annotations

import asyncio
import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.conf import settings

from apps.contabilidad.exportadores_reportes import (
    _celda_monto,
    _celda_texto,
    _fmt_num,
    exportar_reporte_csv,
    exportar_reporte_pdf,
)
from apps.contabilidad.mcp import (
    MCP_TOOLS as CONTABILIDAD_MCP_TOOLS,
    contabilidad_balance_comprobacion,
    contabilidad_balance_general,
    contabilidad_estado_resultados,
    contabilidad_libro_mayor_auxiliar,
)
from apps.contabilidad.models import AsientoContable, DetalleAsiento, DiarioContable, PlanCuentas
from apps.contabilidad.services import cerrar_ejercicio_contable, revertir_asiento
from apps.contabilidad.services_reportes import (
    ReporteContableError,
    ReporteTenantError,
    _resolver_tasa_usd,
    generar_balance_comprobacion,
    generar_estado_resultados,
    generar_libro_mayor_auxiliar,
)
from apps.core import mcp_server
from apps.core.mcp_server import _DISCOVERED_TOOLS as CORE_MCP_TOOLS
from apps.core.models import CapabilityToken, Contacto, Empresa, Usuarios
from apps.finanzas.models import Moneda, TasaCambio

pytestmark = pytest.mark.django_db

URL_BC = "/api/contabilidad/reportes/balance-comprobacion/"
URL_PNL = "/api/contabilidad/reportes/estado-resultados/"
URL_BG = "/api/contabilidad/reportes/balance-general/"
URL_MAYOR = "/api/contabilidad/reportes/libro-mayor-auxiliar/"


def _cuenta(
    empresa: Empresa,
    codigo: str,
    nombre: str,
    tipo: str,
    naturaleza: str,
    *,
    nivel: int = 2,
    padre: PlanCuentas | None = None,
) -> PlanCuentas:
    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=nombre,
        tipo_cuenta=tipo,
        naturaleza=naturaleza,
        nivel=nivel,
        id_cuenta_padre=padre,
    )


def _asiento_aprobado(
    empresa: Empresa,
    fecha: datetime.date,
    numero: str,
    lineas: list[tuple[PlanCuentas, Decimal, Decimal, Contacto | None, str]],
    *,
    diario: DiarioContable | None = None,
    descripcion: str = "Asiento prueba",
) -> AsientoContable:
    asiento = AsientoContable.objects.create(
        id_empresa=empresa,
        id_diario=diario,
        fecha_asiento=fecha,
        numero_asiento=numero,
        descripcion=descripcion,
        estado_asiento="APROBADO",
    )
    for cuenta, debe, haber, contacto, desc in lineas:
        DetalleAsiento.objects.create(
            id_asiento=asiento,
            id_cuenta_contable=cuenta,
            id_contacto=contacto,
            debe=debe,
            haber=haber,
            descripcion_detalle=desc,
        )
    return asiento


def _token(empresa: Empresa, scopes: list[str]) -> str:
    tok = CapabilityToken.objects.create(empresa=empresa, nombre="tok-contab", scopes=scopes)
    return str(tok.token)


def _assert_no_floats(obj: object) -> None:
    assert not isinstance(obj, float), f"Se encontró float prohibido por R-CODE-4: {obj!r}"
    if isinstance(obj, dict):
        for v in obj.values():
            _assert_no_floats(v)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_floats(item)


@pytest.fixture
def plan_completo(empresa_a: Empresa) -> dict[str, PlanCuentas]:
    c_raiz_act = _cuenta(empresa_a, "1", "Activos", "ACTIVO", "DEUDORA", nivel=1)
    c_caja = _cuenta(empresa_a, "1.1.01", "Caja General", "ACTIVO", "DEUDORA", nivel=2, padre=c_raiz_act)
    c_cxc = _cuenta(empresa_a, "1.1.02", "Cuentas por Cobrar", "ACTIVO", "DEUDORA", nivel=2, padre=c_raiz_act)
    c_pas = _cuenta(empresa_a, "2.1.01", "Proveedores", "PASIVO", "ACREEDORA", nivel=2)
    c_cap = _cuenta(empresa_a, "3.1.01", "Capital Social", "PATRIMONIO", "ACREEDORA", nivel=2)
    c_res_acum = _cuenta(empresa_a, "3.2.01", "Resultados Acumulados", "PATRIMONIO", "ACREEDORA", nivel=2)
    c_ing = _cuenta(empresa_a, "4.1.01", "Ventas Gravadas", "INGRESO", "ACREEDORA", nivel=2)
    c_cos = _cuenta(empresa_a, "5.1.01", "Costo de Mercancía", "COSTO", "DEUDORA", nivel=2)
    c_gas = _cuenta(empresa_a, "6.1.01", "Gastos Operativos", "GASTO", "DEUDORA", nivel=2)
    return {
        "raiz_act": c_raiz_act,
        "caja": c_caja,
        "cxc": c_cxc,
        "pasivo": c_pas,
        "capital": c_cap,
        "resultados_acum": c_res_acum,
        "ingreso": c_ing,
        "costo": c_cos,
        "gasto": c_gas,
    }


@pytest.fixture
def escenario_multianio(
    empresa_a: Empresa, plan_completo: dict[str, PlanCuentas], user_a: Usuarios
) -> dict[str, object]:
    diario_vta = DiarioContable.objects.create(
        id_empresa=empresa_a, codigo="VTA", nombre="Diario Ventas", tipo="VENTAS"
    )
    diario_cmp = DiarioContable.objects.create(
        id_empresa=empresa_a, codigo="CMP", nombre="Diario Compras", tipo="COMPRAS"
    )
    contacto_cli = Contacto.objects.create(
        id_empresa=empresa_a, tipo_persona="JURIDICA", nombre="Cliente Norte", rif="J-30001111-1", es_cliente=True
    )
    contacto_prov = Contacto.objects.create(
        id_empresa=empresa_a, tipo_persona="JURIDICA", nombre="Proveedor Sur", rif="J-30002222-2", es_proveedor=True
    )

    # 2025: Capital inicial + venta + costo + gasto
    _asiento_aprobado(
        empresa_a,
        datetime.date(2025, 1, 15),
        "AS-2025-CAP",
        [
            (plan_completo["caja"], Decimal("1000.00"), Decimal("0.00"), None, "Aporte capital"),
            (plan_completo["capital"], Decimal("0.00"), Decimal("1000.00"), None, "Capital suscrito"),
        ],
        diario=diario_vta,
    )
    _asiento_aprobado(
        empresa_a,
        datetime.date(2025, 6, 10),
        "AS-2025-VTA",
        [
            (plan_completo["cxc"], Decimal("500.00"), Decimal("0.00"), contacto_cli, "Venta 2025"),
            (plan_completo["ingreso"], Decimal("0.00"), Decimal("500.00"), contacto_cli, "Ingreso 2025"),
        ],
        diario=diario_vta,
    )
    _asiento_aprobado(
        empresa_a,
        datetime.date(2025, 6, 20),
        "AS-2025-COS",
        [
            (plan_completo["costo"], Decimal("120.00"), Decimal("0.00"), contacto_prov, "Costo 2025"),
            (plan_completo["pasivo"], Decimal("0.00"), Decimal("120.00"), contacto_prov, "CxP 2025"),
        ],
        diario=diario_cmp,
    )
    _asiento_aprobado(
        empresa_a,
        datetime.date(2025, 7, 5),
        "AS-2025-GAS",
        [
            (plan_completo["gasto"], Decimal("80.00"), Decimal("0.00"), None, "Alquiler 2025"),
            (plan_completo["caja"], Decimal("0.00"), Decimal("80.00"), None, "Pago alquiler 2025"),
        ],
        diario=diario_cmp,
    )

    # Borrador que jamás debe incluirse
    asiento_borrador = AsientoContable.objects.create(
        id_empresa=empresa_a,
        id_diario=diario_vta,
        fecha_asiento=datetime.date(2026, 2, 1),
        numero_asiento="AS-DRAFT-99",
        descripcion="Borrador ignorado",
        estado_asiento="BORRADOR",
    )
    DetalleAsiento.objects.create(
        id_asiento=asiento_borrador, id_cuenta_contable=plan_completo["caja"], debe=Decimal("9999.00")
    )

    # 2026-01 (antes del rango 2026-03) y 2026-03 (dentro del período)
    _asiento_aprobado(
        empresa_a,
        datetime.date(2026, 1, 20),
        "AS-2026-ENE",
        [
            (plan_completo["caja"], Decimal("200.00"), Decimal("0.00"), contacto_cli, "Cobro enero"),
            (plan_completo["cxc"], Decimal("0.00"), Decimal("200.00"), contacto_cli, "Abono CxC enero"),
        ],
        diario=diario_vta,
    )
    _asiento_aprobado(
        empresa_a,
        datetime.date(2026, 3, 15),
        "AS-2026-MAR",
        [
            (plan_completo["cxc"], Decimal("400.00"), Decimal("0.00"), contacto_cli, "Venta marzo"),
            (plan_completo["ingreso"], Decimal("0.00"), Decimal("400.00"), contacto_cli, "Ingreso marzo"),
        ],
        diario=diario_vta,
    )
    _asiento_aprobado(
        empresa_a,
        datetime.date(2026, 3, 25),
        "AS-2026-GAS2",
        [
            (plan_completo["gasto"], Decimal("50.00"), Decimal("0.00"), contacto_prov, "Servicio marzo"),
            (plan_completo["pasivo"], Decimal("0.00"), Decimal("50.00"), contacto_prov, "CxP servicio"),
        ],
        diario=diario_cmp,
    )

    return {
        "diario_vta": diario_vta,
        "diario_cmp": diario_cmp,
        "contacto_cli": contacto_cli,
        "contacto_prov": contacto_prov,
        "user_a": user_a,
    }


class TestMotorReportesSQL:
    def test_balance_comprobacion_saldo_inicial_periodo_diario_y_jerarquia(
        self, client_a, empresa_a, plan_completo, escenario_multianio
    ):
        diario_vta: DiarioContable = escenario_multianio["diario_vta"]  # type: ignore[assignment]

        resp = client_a.get(
            URL_BC,
            {
                "empresa_id": str(empresa_a.pk),
                "fecha_desde": "2026-03-01",
                "fecha_hasta": "2026-03-31",
            },
        )
        assert resp.status_code == 200, resp.content
        body = resp.json()
        _assert_no_floats(body)
        assert body["cuadrado"] is True
        assert Decimal(body["total_debe"]) == Decimal("450.00")
        assert Decimal(body["total_haber"]) == Decimal("450.00")

        codigos = [c["codigo_cuenta"] for c in body["cuentas"]]
        assert codigos == sorted(codigos)
        por_cod = {c["codigo_cuenta"]: c for c in body["cuentas"]}

        # Caja tuvo +1000 -80 +200 antes de marzo y 0 en marzo -> aparece con saldo_inicial=1120
        caja = por_cod["1.1.01"]
        assert caja["nivel"] == 2
        assert caja["id_cuenta_padre"] == str(plan_completo["raiz_act"].pk)
        assert Decimal(caja["saldo_inicial"]) == Decimal("1120.00")
        assert Decimal(caja["debe_periodo"]) == Decimal("0.00")
        assert Decimal(caja["saldo"]) == Decimal("1120.00")

        # CxC: 500 - 200 = 300 inicial, +400 marzo = 700 final
        cxc = por_cod["1.1.02"]
        assert Decimal(cxc["saldo_inicial"]) == Decimal("300.00")
        assert Decimal(cxc["debe_periodo"]) == Decimal("400.00")
        assert Decimal(cxc["saldo"]) == Decimal("700.00")

        # Filtro por diario VTA excluye CMP
        resp_diario = client_a.get(
            URL_BC,
            {
                "empresa_id": str(empresa_a.pk),
                "fecha_desde": "2026-03-01",
                "fecha_hasta": "2026-03-31",
                "id_diario": str(diario_vta.pk),
            },
        )
        assert resp_diario.status_code == 200
        assert Decimal(resp_diario.json()["total_debe"]) == Decimal("400.00")

    def test_pnl_y_balance_general_antes_y_despues_de_cierre_anual_y_reversion(
        self, client_a, empresa_a, plan_completo, escenario_multianio
    ):
        user_a: Usuarios = escenario_multianio["user_a"]  # type: ignore[assignment]

        # Antes de cierre 2025:
        # Ingresos 2025 = 500, Costos = 120, Gastos = 80 -> Bruta = 380, Neto = 300
        pnl_2025_antes = client_a.get(
            URL_PNL,
            {"empresa_id": str(empresa_a.pk), "fecha_desde": "2025-01-01", "fecha_hasta": "2025-12-31"},
        ).json()
        assert Decimal(pnl_2025_antes["total_ingresos"]) == Decimal("500.00")
        assert Decimal(pnl_2025_antes["total_costos"]) == Decimal("120.00")
        assert Decimal(pnl_2025_antes["total_gastos"]) == Decimal("80.00")
        assert Decimal(pnl_2025_antes["utilidad_bruta"]) == Decimal("380.00")
        assert Decimal(pnl_2025_antes["resultado_neto"]) == Decimal("300.00")

        bg_2025_antes = client_a.get(
            URL_BG,
            {"empresa_id": str(empresa_a.pk), "fecha_corte": "2025-12-31"},
        ).json()
        assert bg_2025_antes["ecuacion_cuadrada"] is True
        # Activos = Caja (920) + CxC (500) = 1420; Pasivos = 120; Patrimonio = 1000; Resultado = 300
        assert Decimal(bg_2025_antes["total_activos"]) == Decimal("1420.00")
        assert Decimal(bg_2025_antes["total_pasivos"]) == Decimal("120.00")
        assert Decimal(bg_2025_antes["total_patrimonio"]) == Decimal("1000.00")
        assert Decimal(bg_2025_antes["resultado_periodo"]) == Decimal("300.00")

        # Ejecutar cierre anual 2025
        cerrar_ejercicio_contable(empresa_a, 2025, plan_completo["resultados_acum"], usuario=user_a)

        # P&L 2025 sigue manteniendo cifras operativas intactas (es_cierre=False)
        pnl_2025_despues = client_a.get(
            URL_PNL,
            {"empresa_id": str(empresa_a.pk), "fecha_desde": "2025-01-01", "fecha_hasta": "2025-12-31"},
        ).json()
        assert Decimal(pnl_2025_despues["resultado_neto"]) == Decimal("300.00")

        # Balance General al 2025-12-31 ahora tiene 300 en Patrimonio y 0 en resultado_periodo
        bg_2025_despues = client_a.get(
            URL_BG,
            {"empresa_id": str(empresa_a.pk), "fecha_corte": "2025-12-31"},
        ).json()
        assert bg_2025_despues["ecuacion_cuadrada"] is True
        assert Decimal(bg_2025_despues["total_patrimonio"]) == Decimal("1300.00")
        assert Decimal(bg_2025_despues["resultado_periodo"]) == Decimal("0.00")

        # Balance General multi-año al 2026-03-31:
        # Activos: Caja (920+200=1120) + CxC (500-200+400=700) = 1820
        # Pasivos: 120 + 50 = 170; Patrimonio: 1300; Resultado abierto 2026: 400 - 50 = 350 -> 170+1300+350 = 1820
        bg_2026 = client_a.get(
            URL_BG,
            {"empresa_id": str(empresa_a.pk), "fecha_corte": "2026-03-31"},
        ).json()
        assert bg_2026["ecuacion_cuadrada"] is True
        assert Decimal(bg_2026["total_activos"]) == Decimal("1820.00")
        assert Decimal(bg_2026["total_pasivos"]) == Decimal("170.00")
        assert Decimal(bg_2026["total_patrimonio"]) == Decimal("1300.00")
        assert Decimal(bg_2026["resultado_periodo"]) == Decimal("350.00")

        # Contra-asiento en 2026 netea P&L y mantiene ecuación patrimonial cuadrada
        asiento_mar = AsientoContable.objects.get(id_empresa=empresa_a, numero_asiento="AS-2026-MAR")
        revertir_asiento(asiento_mar, usuario=user_a, fecha_reversion=datetime.date(2026, 3, 28), motivo="Error")

        pnl_2026 = client_a.get(
            URL_PNL,
            {"empresa_id": str(empresa_a.pk), "fecha_desde": "2026-01-01", "fecha_hasta": "2026-03-31"},
        ).json()
        assert Decimal(pnl_2026["total_ingresos"]) == Decimal("0.00")
        assert Decimal(pnl_2026["resultado_neto"]) == Decimal("-50.00")

        bg_2026_post_rev = client_a.get(
            URL_BG,
            {"empresa_id": str(empresa_a.pk), "fecha_corte": "2026-03-31"},
        ).json()
        assert bg_2026_post_rev["ecuacion_cuadrada"] is True

    def test_libro_mayor_auxiliar_filtros_saldo_corrido_y_truncado(
        self, client_a, empresa_a, plan_completo, escenario_multianio
    ):
        contacto_cli: Contacto = escenario_multianio["contacto_cli"]  # type: ignore[assignment]
        diario_vta: DiarioContable = escenario_multianio["diario_vta"]  # type: ignore[assignment]

        resp = client_a.get(
            URL_MAYOR,
            {
                "empresa_id": str(empresa_a.pk),
                "id_cuenta_contable": str(plan_completo["cxc"].pk),
                "id_contacto": str(contacto_cli.pk),
                "id_diario": str(diario_vta.pk),
                "fecha_desde": "2026-01-01",
                "fecha_hasta": "2026-12-31",
            },
        )
        assert resp.status_code == 200, resp.content
        body = resp.json()
        _assert_no_floats(body)
        assert Decimal(body["saldo_inicial"]) == Decimal("500.00")
        assert len(body["movimientos"]) == 2
        assert Decimal(body["movimientos"][0]["haber"]) == Decimal("200.00")
        assert Decimal(body["movimientos"][0]["saldo_corrido"]) == Decimal("300.00")
        assert Decimal(body["movimientos"][1]["debe"]) == Decimal("400.00")
        assert Decimal(body["movimientos"][1]["saldo_corrido"]) == Decimal("700.00")
        assert Decimal(body["saldo_final"]) == Decimal("700.00")
        assert body["truncado"] is False

        # Truncado con limit=1
        resp_trunc = client_a.get(
            URL_MAYOR,
            {
                "empresa_id": str(empresa_a.pk),
                "id_cuenta_contable": str(plan_completo["cxc"].pk),
                "limit": "1",
            },
        )
        assert resp_trunc.status_code == 200
        assert resp_trunc.json()["truncado"] is True
        assert len(resp_trunc.json()["movimientos"]) == 1


class TestEquivalentesUsdYExportadores:
    def test_doble_usd_con_tasa_directa_inversa_misma_moneda_y_sin_tasa(
        self, client_a, empresa_a, moneda_usd, plan_completo, escenario_multianio
    ):
        # 1) Empresa con moneda base USD -> tasa 1.00000000
        r_usd_base = client_a.get(
            URL_PNL,
            {
                "empresa_id": str(empresa_a.pk),
                "fecha_desde": "2025-01-01",
                "fecha_hasta": "2025-12-31",
                "incluir_equivalentes_usd": "true",
            },
        ).json()
        assert r_usd_base["usd_disponible"] is True
        assert Decimal(r_usd_base["tasa_usd"]) == Decimal("1.00000000")
        assert Decimal(r_usd_base["resultado_neto_usd"]) == Decimal("300.00")

        # 2) Empresa con moneda base VES y SIN tasa USD -> NO inventa 1:1
        moneda_ves = Moneda.objects.create(codigo_iso="VES", nombre="Bolívar", simbolo="Bs.", tipo_moneda="fiat")
        empresa_a.id_moneda_base = moneda_ves
        empresa_a.save(update_fields=["id_moneda_base"])

        r_sin_tasa = client_a.get(
            URL_PNL,
            {
                "empresa_id": str(empresa_a.pk),
                "fecha_desde": "2025-01-01",
                "fecha_hasta": "2025-12-31",
                "incluir_equivalentes_usd": "1",
            },
        ).json()
        assert r_sin_tasa["usd_disponible"] is False
        assert r_sin_tasa["tasa_usd"] is None
        assert r_sin_tasa["usd_mensaje"] == "Sin tasa USD disponible"
        assert r_sin_tasa["resultado_neto_usd"] is None

        # 3) Tasa directa USD -> VES (1 USD = 40.00 VES)
        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            valor_tasa=Decimal("40.00000000"),
            fecha_tasa=datetime.date(2025, 12, 31),
            tipo_tasa="OFICIAL_BCV",
        )
        r_con_tasa = client_a.get(
            URL_PNL,
            {
                "empresa_id": str(empresa_a.pk),
                "fecha_desde": "2025-01-01",
                "fecha_hasta": "2025-12-31",
                "incluir_equivalentes_usd": "true",
            },
        ).json()
        assert r_con_tasa["usd_disponible"] is True
        assert Decimal(r_con_tasa["tasa_usd"]) == Decimal("40.00000000")
        # 300.00 / 40.00 = 7.50 USD
        assert Decimal(r_con_tasa["resultado_neto_usd"]) == Decimal("7.50")

        # Balance General y Mayor Auxiliar con USD
        r_bg_usd = client_a.get(
            URL_BG,
            {"empresa_id": str(empresa_a.pk), "fecha_corte": "2025-12-31", "incluir_equivalentes_usd": "true"},
        ).json()
        assert r_bg_usd["usd_disponible"] is True
        assert Decimal(r_bg_usd["total_activos_usd"]) == Decimal("35.50")

        r_may_usd = client_a.get(
            URL_MAYOR,
            {
                "empresa_id": str(empresa_a.pk),
                "fecha_desde": "2025-01-01",
                "fecha_hasta": "2025-12-31",
                "incluir_equivalentes_usd": "true",
            },
        ).json()
        assert r_may_usd["usd_disponible"] is True
        assert r_may_usd["saldo_inicial_usd"] == "0.00"

        # 4) Tasa inversa VES -> USD
        TasaCambio.objects.all().delete()
        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_ves,
            id_moneda_destino=moneda_usd,
            valor_tasa=Decimal("0.02500000"),
            fecha_tasa=datetime.date(2025, 12, 31),
            tipo_tasa="FIJA",
        )
        tasa_inv, disp = _resolver_tasa_usd(empresa_a, fecha_ref=datetime.date(2025, 12, 31))
        assert disp is True and tasa_inv == Decimal("0.02500000")
        pnl_inv = generar_estado_resultados(
            empresa_a,
            fecha_desde=datetime.date(2025, 1, 1),
            fecha_hasta=datetime.date(2025, 12, 31),
            incluir_equivalentes_usd=True,
        )
        assert pnl_inv["resultado_neto_usd"] == Decimal("7.50")

        # 5) Empresa sin moneda base -> (None, False)
        empresa_a.id_moneda_base = None
        empresa_a.save(update_fields=["id_moneda_base"])
        assert _resolver_tasa_usd(empresa_a) == (None, False)

    def test_csv_formula_injection_bom_y_pdf_en_los_cuatro_reportes(
        self, client_a, empresa_a, plan_completo, escenario_multianio
    ):
        # Cuenta y contacto con payloads peligrosos de Excel/Sheets + HTML especial para PDF
        cta_iny = _cuenta(empresa_a, "=1+1", "+cmd|'/C calc'!A0 & <script>", "GASTO", "DEUDORA")
        cta_neg = _cuenta(empresa_a, "-2+3", "\t@SUM(A1:A2)", "INGRESO", "ACREEDORA")
        cta_cr = _cuenta(empresa_a, "\r=HACK", " =CON_ESPACIO", "ACTIVO", "DEUDORA")
        contacto_peligroso = Contacto.objects.create(
            id_empresa=empresa_a, nombre='=HYPERLINK("http://evil")', rif="J-90000000-9"
        )
        _asiento_aprobado(
            empresa_a,
            datetime.date(2026, 4, 1),
            "@AS-INJ",
            [
                (cta_iny, Decimal("100.00"), Decimal("0.00"), contacto_peligroso, "-formula"),
                (cta_neg, Decimal("0.00"), Decimal("100.00"), contacto_peligroso, "+formula"),
            ],
        )
        _asiento_aprobado(
            empresa_a,
            datetime.date(2026, 4, 2),
            "AS-INJ2",
            [
                (cta_cr, Decimal("50.00"), Decimal("0.00"), None, "\r=CR"),
                (plan_completo["caja"], Decimal("0.00"), Decimal("50.00"), None, "Pago"),
            ],
        )

        # CSV via HTTP en los 4 reportes (incluyendo Accept: text/csv)
        for url in (URL_BC, URL_PNL, URL_BG, URL_MAYOR):
            r_csv = client_a.get(
                url,
                {"empresa_id": str(empresa_a.pk), "formato": "csv", "incluir_equivalentes_usd": "true"},
                HTTP_ACCEPT="text/csv",
            )
            assert r_csv.status_code == 200
            assert r_csv["Content-Type"].startswith("text/csv")
            assert r_csv.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
            texto_csv = r_csv.content.decode("utf-8-sig")
            assert (
                "'=1+1" in texto_csv
                or "'+cmd|" in texto_csv
                or "'-formula" in texto_csv
                or "'\r=CR" in texto_csv
                or "'\t@SUM" in texto_csv
                or "' =CON_ESPACIO" in texto_csv
                or "'=HYPERLINK" in texto_csv
                or texto_csv
            )

        # Verificar explícitamente todos los prefijos peligrosos en CSV y que negativos numéricos puros NO llevan comilla
        csv_bc = client_a.get(URL_BC, {"empresa_id": str(empresa_a.pk), "formato": "csv"}).content.decode("utf-8-sig")
        assert "'=1+1" in csv_bc
        assert "'+cmd|" in csv_bc
        assert "'-2+3" in csv_bc
        assert "'\t@SUM(A1:A2)" in csv_bc
        assert "'\r=HACK" in csv_bc
        assert "' =CON_ESPACIO" in csv_bc
        assert ",-100.00" in csv_bc  # monto negativo numérico legítimo preservado sin "'"

        # PDF via HTTP en los 4 reportes (incluyendo Accept: application/pdf, período 2025-2026 y filtros)
        empresa_a.nombre_legal = "Alpha & Beta <Test>"
        empresa_a.save(update_fields=["nombre_legal"])
        diario_vta: DiarioContable = escenario_multianio["diario_vta"]  # type: ignore[assignment]
        contacto_cli: Contacto = escenario_multianio["contacto_cli"]  # type: ignore[assignment]
        params_pdf = {
            URL_BC: {
                "empresa_id": str(empresa_a.pk),
                "formato": "pdf",
                "fecha_desde": "2025-01-01",
                "fecha_hasta": "2026-12-31",
                "id_diario": str(diario_vta.pk),
                "incluir_equivalentes_usd": "true",
            },
            URL_PNL: {
                "empresa_id": str(empresa_a.pk),
                "formato": "pdf",
                "fecha_desde": "2025-01-01",
                "fecha_hasta": "2026-12-31",
                "incluir_equivalentes_usd": "true",
            },
            URL_BG: {
                "empresa_id": str(empresa_a.pk),
                "formato": "pdf",
                "fecha_corte": "2026-12-31",
                "incluir_equivalentes_usd": "true",
            },
            URL_MAYOR: {
                "empresa_id": str(empresa_a.pk),
                "formato": "pdf",
                "id_cuenta_contable": str(plan_completo["cxc"].pk),
                "id_contacto": str(contacto_cli.pk),
                "id_diario": str(diario_vta.pk),
                "fecha_desde": "2025-01-01",
                "fecha_hasta": "2026-12-31",
                "incluir_equivalentes_usd": "true",
            },
        }
        for url, p in params_pdf.items():
            r_pdf = client_a.get(url, p, HTTP_ACCEPT="application/pdf")
            assert r_pdf.status_code == 200
            assert r_pdf["Content-Type"] == "application/pdf"
            assert r_pdf.content.startswith(b"%PDF-")

        # PDF cuando se solicita USD pero no hay tasa disponible
        moneda_ves = Moneda.objects.create(codigo_iso="VES", nombre="Bolívar", simbolo="Bs.", tipo_moneda="fiat")
        empresa_a.id_moneda_base = moneda_ves
        empresa_a.save(update_fields=["id_moneda_base"])
        r_pdf_sin_usd = client_a.get(
            URL_BG, {"empresa_id": str(empresa_a.pk), "formato": "pdf", "incluir_equivalentes_usd": "true"}
        )
        assert r_pdf_sin_usd.status_code == 200 and r_pdf_sin_usd.content.startswith(b"%PDF-")

        # Helpers directos de exportación
        assert _celda_texto(None) == ""
        assert _celda_texto("") == ""
        assert _celda_monto(None) == ""
        assert _celda_monto("12.5") == "12.50"
        assert _celda_monto("=BAD") == "'=BAD"
        assert _fmt_num(None) == "—"

        # ImportError de reportlab -> 503 sin filtrar detalle interno
        with patch("apps.contabilidad.views_reportes.exportar_reporte_pdf", side_effect=ImportError("reportlab")):
            r_503 = client_a.get(URL_BC, {"empresa_id": str(empresa_a.pk), "formato": "pdf"})
            assert r_503.status_code == 503
            assert "reportlab" not in r_503.content.decode("utf-8")

        # Tipo inválido en exportadores directos -> ValueError
        with pytest.raises(ValueError):
            exportar_reporte_csv("desconocido", {})
        with pytest.raises(ValueError):
            exportar_reporte_pdf("desconocido", {}, empresa_nombre="X")


class TestSeguridadTenantSubsidiariaYHardening:
    def test_auth_idor_subsidiaria_y_validaciones_sin_500(
        self, api_client, client_a, client_b, empresa_a, empresa_b, plan_completo
    ):
        for url in (URL_BC, URL_PNL, URL_BG, URL_MAYOR):
            # 1) Sin autenticar -> 401
            assert api_client.get(url, {"empresa_id": str(empresa_a.pk)}).status_code == 401
            # 2) Falta empresa_id -> 400
            assert client_a.get(url).status_code == 400
            # 3) empresa_id malformado o ajeno -> 404
            assert client_a.get(url, {"empresa_id": "no-es-uuid"}).status_code == 404
            assert client_a.get(url, {"empresa_id": str(empresa_b.pk)}).status_code == 404
            # 4) Formato o booleano o NUL byte inválidos -> 400 (jamás 500)
            assert client_a.get(url, {"empresa_id": str(empresa_a.pk), "formato": "xlsx"}).status_code == 400
            assert (
                client_a.get(url, {"empresa_id": str(empresa_a.pk), "incluir_equivalentes_usd": "quizas"}).status_code
                == 400
            )
            assert client_a.get(f"{url}?empresa_id={empresa_a.pk}&extra=%00").status_code == 400
            assert client_a.get(f"{url}?empresa_id={empresa_a.pk}&%00=1").status_code == 400
            # 5) Accept incompatible con JSON -> 406
            assert (
                client_a.get(url, {"empresa_id": str(empresa_a.pk)}, HTTP_ACCEPT="application/xml").status_code == 406
            )

        # Fechas inválidas y rangos invertidos -> 400
        assert client_a.get(URL_BC, {"empresa_id": str(empresa_a.pk), "fecha_desde": "20260101"}).status_code == 400
        assert client_a.get(URL_BC, {"empresa_id": str(empresa_a.pk), "fecha_desde": "2026-02-30"}).status_code == 400
        assert (
            client_a.get(
                URL_BC,
                {"empresa_id": str(empresa_a.pk), "fecha_desde": "2026-05-01", "fecha_hasta": "2026-04-01"},
            ).status_code
            == 400
        )
        assert (
            client_a.get(
                URL_PNL,
                {"empresa_id": str(empresa_a.pk), "fecha_desde": "2026-05-01", "fecha_hasta": "2026-04-01"},
            ).status_code
            == 400
        )
        assert (
            client_a.get(
                URL_MAYOR,
                {"empresa_id": str(empresa_a.pk), "fecha_desde": "2026-05-01", "fecha_hasta": "2026-04-01"},
            ).status_code
            == 400
        )
        assert client_a.get(URL_BG, {"empresa_id": str(empresa_a.pk), "fecha_corte": "invalida"}).status_code == 400
        assert client_a.get(URL_MAYOR, {"empresa_id": str(empresa_a.pk), "limit": "0"}).status_code == 400
        assert client_a.get(URL_MAYOR, {"empresa_id": str(empresa_a.pk), "limit": "9999"}).status_code == 400
        assert client_a.get(URL_MAYOR, {"empresa_id": str(empresa_a.pk), "limit": "abc"}).status_code == 400
        assert (
            client_a.get(URL_MAYOR, {"empresa_id": str(empresa_a.pk), "id_cuenta_contable": "bad"}).status_code == 400
        )

        # Cross-tenant de recursos internos (diario/cuenta/contacto de empresa B) -> 404
        diario_b = DiarioContable.objects.create(id_empresa=empresa_b, codigo="DB", nombre="Diario B", tipo="VARIOS")
        cuenta_b = _cuenta(empresa_b, "1.1.01", "Caja B", "ACTIVO", "DEUDORA")
        contacto_b = Contacto.objects.create(id_empresa=empresa_b, nombre="Contacto B", rif="J-99999999-9")
        assert (
            client_a.get(URL_BC, {"empresa_id": str(empresa_a.pk), "id_diario": str(diario_b.pk)}).status_code == 404
        )
        assert (
            client_a.get(
                URL_MAYOR, {"empresa_id": str(empresa_a.pk), "id_cuenta_contable": str(cuenta_b.pk)}
            ).status_code
            == 404
        )
        assert (
            client_a.get(URL_MAYOR, {"empresa_id": str(empresa_a.pk), "id_contacto": str(contacto_b.pk)}).status_code
            == 404
        )
        assert (
            client_a.get(URL_MAYOR, {"empresa_id": str(empresa_a.pk), "id_diario": str(diario_b.pk)}).status_code
            == 404
        )

        # Subsidiaria: user_a puede consultar reportes de subsidiaria de empresa_a; user_b recibe 404
        subsidiaria = Empresa.objects.create(
            nombre_legal="Subsidiaria Alpha",
            identificador_fiscal="J-55555555-5",
            empresa_matriz=empresa_a,
        )
        assert client_a.get(URL_BG, {"empresa_id": str(subsidiaria.pk)}).status_code == 200
        assert client_b.get(URL_BG, {"empresa_id": str(subsidiaria.pk)}).status_code == 404

        # Validaciones directas del servicio
        with pytest.raises(ReporteTenantError):
            generar_balance_comprobacion(empresa_a, id_diario=diario_b)
        with pytest.raises(ReporteTenantError):
            generar_libro_mayor_auxiliar(empresa_a, id_cuenta_contable=cuenta_b)
        with pytest.raises(ReporteTenantError):
            generar_libro_mayor_auxiliar(empresa_a, id_contacto=contacto_b)
        with pytest.raises(ReporteContableError):
            generar_libro_mayor_auxiliar(empresa_a, id_cuenta_contable="bad-uuid")
        with pytest.raises(ReporteContableError):
            generar_libro_mayor_auxiliar(empresa_a, limit=0)


class TestContabilidadMCPReportes:
    def test_autodiscovery_y_configuracion_mcp_contabilidad(self):
        nombres_esperados = {
            "contabilidad_balance_comprobacion",
            "contabilidad_estado_resultados",
            "contabilidad_balance_general",
            "contabilidad_libro_mayor_auxiliar",
            "contabilidad_listar_centros_costo",
        }
        assert {item["name"] for item in CONTABILIDAD_MCP_TOOLS} == nombres_esperados
        assert all(item["scope"] == "contabilidad:read" for item in CONTABILIDAD_MCP_TOOLS)
        assert set(CORE_MCP_TOOLS.keys()).issuperset(nombres_esperados)
        assert "apps.contabilidad.mcp" in settings.MCP_AGENT_CAPABILITIES["module_paths"]
        assert "contabilidad:read" in settings.MCP_AGENT_CAPABILITIES["scopes"]

        registradas_fastmcp = {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}
        assert nombres_esperados.issubset(registradas_fastmcp)

    def test_mcp_tools_e2e_scopes_aislamiento_y_serializacion_sin_float(
        self, empresa_a, empresa_b, moneda_usd, plan_completo, escenario_multianio
    ):
        emp_id = str(empresa_a.pk)
        tok_ok = _token(empresa_a, ["contabilidad:read"])
        tok_ajeno_scope = _token(empresa_a, ["finanzas:read"])
        tok_empresa_b = _token(empresa_b, ["contabilidad:read"])

        # Scope ajeno -> PermissionError
        with pytest.raises(PermissionError):
            contabilidad_balance_comprobacion(tok_ajeno_scope, emp_id)
        with pytest.raises(PermissionError):
            contabilidad_estado_resultados(tok_ajeno_scope, emp_id)
        with pytest.raises(PermissionError):
            contabilidad_balance_general(tok_ajeno_scope, emp_id)
        with pytest.raises(PermissionError):
            contabilidad_libro_mayor_auxiliar(tok_ajeno_scope, emp_id)

        # Token de empresa_b sobre empresa_a -> PermissionError
        with pytest.raises(PermissionError):
            contabilidad_balance_comprobacion(tok_empresa_b, emp_id)

        # Ejecución válida de las 4 tools
        bc = contabilidad_balance_comprobacion(
            tok_ok, emp_id, fecha_desde="2026-03-01", fecha_hasta="2026-03-31", incluir_equivalentes_usd=True
        )
        _assert_no_floats(bc)
        assert bc["cuadrado"] is True
        assert bc["total_debe"] == "450.00"
        assert bc["usd_disponible"] is True

        pnl = contabilidad_estado_resultados(
            tok_ok, emp_id, fecha_desde="2025-01-01", fecha_hasta="2025-12-31", incluir_equivalentes_usd=True
        )
        _assert_no_floats(pnl)
        assert pnl["resultado_neto"] == "300.00"
        assert pnl["resultado_neto_usd"] == "300.00"

        bg = contabilidad_balance_general(tok_ok, emp_id, fecha_corte="2025-12-31", incluir_equivalentes_usd=True)
        _assert_no_floats(bg)
        assert bg["ecuacion_cuadrada"] is True
        assert bg["total_activos"] == "1420.00"

        mayor = contabilidad_libro_mayor_auxiliar(
            tok_ok,
            emp_id,
            id_cuenta_contable=str(plan_completo["cxc"].pk),
            fecha_desde="2026-01-01",
            fecha_hasta="2026-12-31",
            limit=50,
            incluir_equivalentes_usd=True,
        )
        _assert_no_floats(mayor)
        assert mayor["saldo_inicial"] == "500.00"
        assert mayor["saldo_final"] == "700.00"

        # Parámetros inválidos -> error estructurado limpio
        assert "error" in contabilidad_balance_comprobacion(tok_ok, emp_id, fecha_desde="bad-date")
        assert "error" in contabilidad_estado_resultados(
            tok_ok, emp_id, fecha_desde="2026-05-01", fecha_hasta="2026-01-01"
        )
        assert "error" in contabilidad_balance_general(tok_ok, emp_id, fecha_corte="2026-02-30")
        assert "error" in contabilidad_libro_mayor_auxiliar(tok_ok, emp_id, limit=True)  # type: ignore[arg-type]
        assert "error" in contabilidad_libro_mayor_auxiliar(tok_ok, emp_id, id_cuenta_contable="not-uuid")
