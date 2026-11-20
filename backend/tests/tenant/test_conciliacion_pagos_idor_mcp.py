"""
Tests de aislamiento multi-tenant (IDOR + RLS PostgreSQL) y tools MCP de conciliación de pagos (Ola A3).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone

from apps.core import rls
from apps.core.mcp_server import _DISCOVERED_TOOLS as CORE_MCP_TOOLS
from apps.core.models import CapabilityToken, Contacto
from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.models import CuentaPorCobrar
from apps.finanzas.mcp import (
    MCP_TOOLS as FINANZAS_MCP_TOOLS,
    finanzas_conciliar_pago_multiple,
    finanzas_get_saldos_favor_contacto,
    finanzas_revertir_asignacion_pago,
)
from apps.finanzas.models import AsignacionPago, Pago
from apps.finanzas.services_conciliacion_pagos import aplicar_pago_a_documentos
from apps.ventas.models import FacturaFiscal

pytestmark = [pytest.mark.django_db]


def _hoy():
    return timezone.localdate()


def _token(empresa, scopes: list[str]) -> str:
    tok = CapabilityToken.objects.create(empresa=empresa, nombre="tok-conciliacion", scopes=scopes)
    return str(tok.token)


@pytest.fixture
def escenario_b(db, empresa_b, moneda_usd, metodo_efectivo, user_b):
    contacto_b = Contacto.objects.create(
        id_empresa=empresa_b,
        tipo_persona="JURIDICA",
        nombre="Contacto Privado B",
        rif="J-99900011-1",
        es_cliente=True,
    )
    cliente_b = Cliente.objects.create(
        id_empresa=empresa_b,
        razon_social=contacto_b.nombre,
        rif=contacto_b.rif,
        contacto=contacto_b,
    )
    fv_b = FacturaFiscal.objects.create(
        id_empresa=empresa_b,
        id_cliente=cliente_b,
        numero_control="CTRL-B-1",
        numero_factura="FV-B-1",
        fecha_emision=_hoy(),
        fecha_vencimiento=_hoy() + timedelta(days=10),
        base_imponible=Decimal("100.0000"),
        monto_iva=Decimal("0.0000"),
        monto_igtf=Decimal("0.0000"),
        monto_total=Decimal("100.0000"),
        id_moneda=moneda_usd,
        tasa_cambio=Decimal("1.0000"),
        estado="EMITIDA",
        activo=True,
    )
    pago_b = Pago.objects.create(
        id_empresa=empresa_b,
        id_contacto=contacto_b,
        tipo_operacion="INGRESO",
        tipo_documento="ANTICIPO",
        fecha_pago=timezone.now(),
        monto=Decimal("100.0000"),
        id_moneda=moneda_usd,
        id_metodo_pago=metodo_efectivo,
        referencia="PAGO-B-1",
    )
    asig_b = aplicar_pago_a_documentos(
        pago_b,
        [{"tipo_documento": "FACTURA_VENTA", "id_documento": fv_b.pk, "monto_asignado_pago": "40.00"}],
        usuario=user_b,
        generar_asiento=False,
    )[0]
    return {
        "contacto_b": contacto_b,
        "cliente_b": cliente_b,
        "fv_b": fv_b,
        "pago_b": pago_b,
        "asig_b": asig_b,
    }


@pytest.mark.tenant
class TestConciliacionPagosIDOR:
    def test_usuario_a_no_accede_ni_muta_recursos_empresa_b(
        self, api_client, client_a, empresa_a, moneda_usd, metodo_efectivo, escenario_b
    ):
        contacto_b = escenario_b["contacto_b"]
        fv_b = escenario_b["fv_b"]
        pago_b = escenario_b["pago_b"]
        asig_b = escenario_b["asig_b"]

        # Sin autenticar -> 401
        assert api_client.get("/api/finanzas/asignaciones-pago/").status_code == 401
        assert api_client.get(f"/api/finanzas/contactos/{contacto_b.pk}/estado-conciliacion/").status_code == 401

        # Acceso directo IDOR sobre recursos de Empresa B -> 404
        assert client_a.get(f"/api/finanzas/contactos/{contacto_b.pk}/estado-conciliacion/").status_code == 404
        assert client_a.get(f"/api/finanzas/pagos/{pago_b.pk}/sugerir-distribucion/").status_code == 404
        assert (
            client_a.post(
                f"/api/finanzas/pagos/{pago_b.pk}/conciliar-documentos/",
                {
                    "asignaciones": [
                        {
                            "tipo_documento": "FACTURA_VENTA",
                            "id_documento": str(fv_b.pk),
                            "monto_asignado_pago": "10.00",
                        }
                    ],
                    "generar_asiento": False,
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY="idor-conc-1",
            ).status_code
            == 404
        )
        assert client_a.get(f"/api/finanzas/asignaciones-pago/{asig_b.pk}/").status_code == 404
        assert (
            client_a.post(
                f"/api/finanzas/asignaciones-pago/{asig_b.pk}/revertir/",
                {"motivo": "idor"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="idor-rev-1",
            ).status_code
            == 404
        )

        # POST /asignaciones-pago/ con pago ajeno -> 404
        assert (
            client_a.post(
                "/api/finanzas/asignaciones-pago/",
                {
                    "pago": str(pago_b.pk),
                    "asignaciones": [
                        {
                            "tipo_documento": "FACTURA_VENTA",
                            "id_documento": str(fv_b.pk),
                            "monto_asignado_pago": "10.00",
                        }
                    ],
                    "generar_asiento": False,
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY="idor-create-1",
            ).status_code
            == 404
        )

        # Pago de A intentando conciliar documento de B -> 404 ConciliacionTenantError
        contacto_a = Contacto.objects.create(
            id_empresa=empresa_a,
            tipo_persona="JURIDICA",
            nombre="Contacto A",
            rif="J-11100022-3",
            es_cliente=True,
        )
        pago_a = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_a,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("50.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        assert (
            client_a.post(
                "/api/finanzas/asignaciones-pago/",
                {
                    "pago": str(pago_a.pk),
                    "asignaciones": [
                        {
                            "tipo_documento": "FACTURA_VENTA",
                            "id_documento": str(fv_b.pk),
                            "monto_asignado_pago": "10.00",
                        }
                    ],
                    "generar_asiento": False,
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY="idor-cross-doc-1",
            ).status_code
            == 404
        )

        # Listado filtrado con contacto_b no fuga asignaciones de B
        r_list = client_a.get(f"/api/finanzas/asignaciones-pago/?contacto={contacto_b.pk}")
        assert r_list.status_code == 200
        rows = r_list.data["results"] if "results" in r_list.data else r_list.data
        assert rows == []

    def test_rls_postgresql_en_asignaciones_vía_api_y_rol_no_privilegiado(
        self, rls_test_role, empresa_a, empresa_b, moneda_usd, metodo_efectivo, user_a, escenario_b
    ):
        contacto_a = Contacto.objects.create(
            id_empresa=empresa_a,
            tipo_persona="JURIDICA",
            nombre="RLS Cliente A",
            rif="J-77700011-1",
            es_cliente=True,
        )
        cliente_a = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social=contacto_a.nombre,
            rif=contacto_a.rif,
            contacto=contacto_a,
        )
        cxc_a = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("60.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=5),
        )
        pago_a = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_a,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("60.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        asig_a = aplicar_pago_a_documentos(
            pago_a,
            [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc_a.pk, "monto_asignado_pago": "30.00"}],
            usuario=user_a,
            generar_asiento=False,
        )[0]
        asig_b = escenario_b["asig_b"]

        with connection.cursor() as cur:
            if rls_test_role is not None:
                cur.execute(f'SET ROLE "{rls_test_role}"')
            try:
                rls.apply_context([empresa_a.id_empresa], bypass=False)
                assert list(AsignacionPago.objects.values_list("pk", flat=True)) == [asig_a.pk]

                rls.apply_context([empresa_b.id_empresa], bypass=False)
                assert list(AsignacionPago.objects.values_list("pk", flat=True)) == [asig_b.pk]

                rls.apply_context([], bypass=False)
                assert AsignacionPago.objects.count() == 0
            finally:
                rls.apply_system_default()
                if rls_test_role is not None:
                    cur.execute("RESET ROLE")


@pytest.mark.tenant
class TestConciliacionPagosMCP:
    def test_mcp_autodiscovery_incluye_tres_tools_nuevas(self):
        nombres_finanzas = {item["name"] for item in FINANZAS_MCP_TOOLS}
        assert {
            "finanzas_get_saldos_favor_contacto",
            "finanzas_conciliar_pago_multiple",
            "finanzas_revertir_asignacion_pago",
        }.issubset(nombres_finanzas)
        assert set(CORE_MCP_TOOLS.keys()).issuperset(nombres_finanzas)

    def test_mcp_flujo_saldos_conciliar_y_revertir_con_aislamiento_y_scopes(
        self, empresa_a, empresa_b, moneda_usd, metodo_efectivo, escenario_b
    ):
        contacto = Contacto.objects.create(
            id_empresa=empresa_a,
            tipo_persona="JURIDICA",
            nombre="Contacto MCP S.A.",
            rif="J-88800011-2",
            es_cliente=True,
        )
        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social=contacto.nombre,
            rif=contacto.rif,
            contacto=contacto,
        )
        fv1 = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_control="CTRL-MCP-1",
            numero_factura="FV-MCP-1",
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=5),
            base_imponible=Decimal("80.0000"),
            monto_iva=Decimal("0.0000"),
            monto_igtf=Decimal("0.0000"),
            monto_total=Decimal("80.0000"),
            id_moneda=moneda_usd,
            tasa_cambio=Decimal("1.0000"),
            estado="EMITIDA",
            activo=True,
        )
        pago = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("120.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
            referencia="TRF-MCP",
        )

        tok_read = _token(empresa_a, ["finanzas:read"])
        tok_write = _token(empresa_a, ["finanzas:write"])
        tok_ajeno = _token(empresa_b, ["finanzas:read", "finanzas:write"])
        emp_id = str(empresa_a.id_empresa)

        # 1) Consultar saldo a favor
        saldos = finanzas_get_saldos_favor_contacto(tok_read, emp_id, str(contacto.pk), tipo_operacion="INGRESO")
        assert saldos["contacto_id"] == str(contacto.pk)
        assert saldos["pagos_con_saldo"][0]["saldo_disponible"] == Decimal("120.0000")

        # Scope insuficiente en write tools -> PermissionError
        with pytest.raises(PermissionError):
            finanzas_conciliar_pago_multiple(
                tok_read,
                emp_id,
                str(pago.pk),
                [{"tipo_documento": "FACTURA_VENTA", "id_documento": str(fv1.pk), "monto_asignado_pago": "50.00"}],
            )

        # Token de empresa B sobre empresa A -> PermissionError (fail-closed)
        with pytest.raises(PermissionError):
            finanzas_get_saldos_favor_contacto(tok_ajeno, emp_id, str(contacto.pk))

        # 2) Conciliar pago múltiple via MCP
        res_conc = finanzas_conciliar_pago_multiple(
            tok_write,
            emp_id,
            str(pago.pk),
            [
                {
                    "tipo_documento": "FACTURA_VENTA",
                    "id_documento": str(fv1.pk),
                    "monto_asignado_pago": "80.00",
                    "tasa_aplicada": "1.00",
                }
            ],
            descripcion="Conciliación vía MCP",
        )
        assert len(res_conc["asignaciones_creadas"]) == 1
        assert res_conc["saldo_disponible"] == Decimal("40.0000")
        asig_id = res_conc["asignaciones_creadas"][0]["id_asignacion"]

        # Verificar saldo a favor actualizado
        saldos_post = finanzas_get_saldos_favor_contacto(tok_read, emp_id, str(contacto.pk))
        assert saldos_post["pagos_con_saldo"][0]["saldo_disponible"] == Decimal("40.0000")

        # 3) Revertir via MCP
        with pytest.raises(PermissionError):
            finanzas_revertir_asignacion_pago(tok_read, emp_id, asig_id, motivo="sin permiso")

        res_rev = finanzas_revertir_asignacion_pago(tok_write, emp_id, asig_id, motivo="Reversión MCP")
        assert res_rev["estado"] == "REVERTIDA"
        assert res_rev["saldo_disponible_pago"] == Decimal("120.0000")
        assert res_rev["motivo_reversion"] == "Reversión MCP"

        # 4) Aislamiento de entidades B y validaciones de entrada
        assert "error" in finanzas_get_saldos_favor_contacto(tok_read, emp_id, "no-uuid")
        assert "error" in finanzas_get_saldos_favor_contacto(tok_read, emp_id, str(escenario_b["contacto_b"].pk))
        assert "error" in finanzas_get_saldos_favor_contacto(tok_read, emp_id, str(contacto.pk), tipo_operacion="BAD")
        assert "error" in finanzas_conciliar_pago_multiple(tok_write, emp_id, "no-uuid", [{"x": 1}])
        assert "error" in finanzas_conciliar_pago_multiple(tok_write, emp_id, str(pago.pk), [])
        assert "error" in finanzas_conciliar_pago_multiple(
            tok_write, emp_id, str(escenario_b["pago_b"].pk), [{"x": 1}]
        )
        assert "error" in finanzas_conciliar_pago_multiple(tok_write, emp_id, str(pago.pk), ["no-dict"])  # type: ignore[list-item]
        assert "error" in finanzas_conciliar_pago_multiple(
            tok_write,
            emp_id,
            str(pago.pk),
            [{"tipo_documento": "FACTURA_VENTA", "id_documento": str(fv1.pk), "monto_asignado_pago": "abc"}],
        )
        assert "error" in finanzas_conciliar_pago_multiple(
            tok_write,
            emp_id,
            str(pago.pk),
            [{"tipo_documento": "FACTURA_VENTA", "id_documento": str(fv1.pk), "monto_asignado_pago": True}],
        )
        assert "error" in finanzas_conciliar_pago_multiple(
            tok_write,
            emp_id,
            str(pago.pk),
            [{"tipo_documento": "FACTURA_VENTA", "id_documento": str(fv1.pk), "monto_asignado_pago": "NaN"}],
        )
        assert "error" in finanzas_conciliar_pago_multiple(
            tok_write,
            emp_id,
            str(pago.pk),
            [
                {
                    "tipo_documento": "FACTURA_VENTA",
                    "id_documento": str(escenario_b["fv_b"].pk),
                    "monto_asignado_pago": "10.00",
                }
            ],
        )
        assert "error" in finanzas_revertir_asignacion_pago(tok_write, emp_id, "no-uuid")
        assert "error" in finanzas_revertir_asignacion_pago(tok_write, emp_id, str(escenario_b["asig_b"].pk))
        assert "error" in finanzas_revertir_asignacion_pago(tok_write, emp_id, asig_id, motivo="doble")

        # [O-3] Llamada Python directa con motivo=None no debe romper .strip() ni fallar tipo
        res_conc2 = finanzas_conciliar_pago_multiple(
            tok_write,
            emp_id,
            str(pago.pk),
            [{"tipo_documento": "FACTURA_VENTA", "id_documento": str(fv1.pk), "monto_asignado_pago": "20.00"}],
        )
        asig2_id = res_conc2["asignaciones_creadas"][0]["id_asignacion"]
        res_rev_none = finanzas_revertir_asignacion_pago(tok_write, emp_id, asig2_id, motivo=None)
        assert res_rev_none["estado"] == "REVERTIDA"
        assert res_rev_none["motivo_reversion"] == ""

        with pytest.raises(PermissionError):
            finanzas_get_saldos_favor_contacto(tok_read, str(uuid.uuid4()), str(contacto.pk))
        empresa_a.activo = False
        empresa_a.save(update_fields=["activo"])
        assert "error" in finanzas_get_saldos_favor_contacto(tok_read, emp_id, str(contacto.pk))
