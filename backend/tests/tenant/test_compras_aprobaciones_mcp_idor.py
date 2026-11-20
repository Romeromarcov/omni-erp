"""
Tests multi-tenant (IDOR + RLS fail-closed), conectores opt-in de aprobaciones
(PAGO_TERCERO y OPERACION_CAMBIO_DIVISA) y tools MCP de Compras + Aprobaciones (Plan 08 §B.2).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import uuid

import pytest
from django.conf import settings
from django.db import connection
from django.test import override_settings
from django.utils import timezone

from apps.almacenes.models import Almacen
from apps.compras.mcp import MCP_TOOLS as COMPRAS_MCP_TOOLS
from apps.compras.mcp import compras_adjudicar_oferta, compras_crear_requisicion
from apps.compras.models import (
    DetalleOfertaProveedor,
    OfertaProveedor,
    OrdenCompra,
    RequisicionCompra,
    SolicitudCotizacion,
)
from apps.compras.services_procurement import confirmar_aprobacion_requisicion, crear_rfq_desde_requisiciones
from apps.core import rls
from apps.core.mcp_server import _DISCOVERED_TOOLS as CORE_MCP_TOOLS
from apps.core.models import CapabilityToken, Departamento, Roles, UsuarioRoles
from apps.cuentas_por_pagar.models import CuentaPorPagar
from apps.finanzas.models import Caja, Moneda, PagoTercero
from apps.finanzas.services_pagos_terceros import PagoTerceroError, abonar_pago_tercero, solicitar_reintegro
from apps.gestion_aprobaciones.mcp import MCP_TOOLS as APROBACIONES_MCP_TOOLS
from apps.gestion_aprobaciones.mcp import aprobaciones_decidir, aprobaciones_pendientes
from apps.gestion_aprobaciones.models import FlujoAprobacion, SolicitudAprobacion, TipoAprobacion
from apps.gestion_aprobaciones.services import registrar_decision
from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
from apps.proveedores.models import Proveedor
from apps.tesoreria.models import OperacionCambioDivisa

pytestmark = [pytest.mark.django_db]


def _hoy() -> date:
    return timezone.localdate()


def _token(empresa, scopes: list[str]) -> str:
    tok = CapabilityToken.objects.create(empresa=empresa, nombre="tok-proc", scopes=scopes)
    return str(tok.token)


def _setup_contabilidad_pago_tercero(empresa):
    from apps.contabilidad.models import MapeoContable, PlanCuentas

    def _cta(cod, nom, tipo, nat):
        return PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta=cod,
            nombre_cuenta=nom,
            tipo_cuenta=tipo,
            naturaleza=nat,
            nivel=1,
        )

    c_db = _cta("2.1.01", "CxP Proveedores", "PASIVO", "ACREEDORA")
    c_cr = _cta("1.1.01", "Caja Tercero", "ACTIVO", "DEUDORA")
    MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento="PAGO_TERCERO",
        cuenta_debe=c_db,
        cuenta_haber=c_cr,
        activo=True,
    )


def _setup_contabilidad_cambio_divisa(empresa):
    from apps.contabilidad.models import MapeoContable, PlanCuentas

    def _cta(cod, nom, tipo, nat):
        return PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta=cod,
            nombre_cuenta=nom,
            tipo_cuenta=tipo,
            naturaleza=nat,
            nivel=1,
        )

    c_1 = _cta("1.1.01", "Caja Divisas", "ACTIVO", "DEUDORA")
    c_2 = _cta("1.1.02", "Caja VES", "ACTIVO", "DEUDORA")
    c_g = _cta("5.1.01", "Comisiones", "EGRESO", "DEUDORA")
    MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento="CAMBIO_DIVISA",
        cuenta_debe=c_2,
        cuenta_haber=c_1,
        activo=True,
    )
    MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento="GASTO",
        cuenta_debe=c_g,
        cuenta_haber=c_1,
        activo=True,
    )


@pytest.mark.tenant
class TestConectoresOptInAprobaciones:
    def test_pago_tercero_con_y_sin_regla_e_idempotency_preserva_solicitud(
        self, client_a, empresa_a, user_a, moneda_usd
    ):
        _setup_contabilidad_pago_tercero(empresa_a)
        prov = Proveedor.objects.create(id_empresa=empresa_a, razon_social="Prov PT", rif="J-55555555-1")
        cxp = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov,
            monto_total=Decimal("1000.00"),
            monto_pendiente=Decimal("1000.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=30),
            estado="PENDIENTE",
        )
        pago1 = PagoTercero.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov,
            id_moneda=moneda_usd,
            monto=Decimal("300.00"),
            referencia_zelle="Z-OPT-1",
            fecha=_hoy(),
        )
        pago2 = PagoTercero.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov,
            id_moneda=moneda_usd,
            monto=Decimal("350.00"),
            referencia_zelle="Z-OPT-2",
            fecha=_hoy(),
        )

        # 1) Sin regla PAGO_TERCERO: abonar y solicitar-reintegro pasan directo (cero fricción)
        r_direct = client_a.post(
            f"/api/finanzas/pagos-terceros/{pago1.pk}/abonar/",
            {"cxp": str(cxp.pk)},
            format="json",
            HTTP_IDEMPOTENCY_KEY="pt-direct-1",
        )
        assert r_direct.status_code == 200, r_direct.json()

        # 2) Activamos regla PAGO_TERCERO para montos >= 200
        tipo = TipoAprobacion.objects.create(
            id_empresa=empresa_a, codigo_tipo="PAGO_TERCERO", nombre_tipo="Pago Tercero", modulo_origen="finanzas"
        )
        FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            orden_etapa=1,
            nombre_etapa="Tesorería",
            id_usuario_aprobador=user_a,
            monto_minimo=Decimal("200.00"),
            activo=True,
        )

        # Si se llama al servicio directo sin usuario cuando requiere aprobación -> PagoTerceroError
        with pytest.raises(PagoTerceroError, match="usuario solicitante"):
            abonar_pago_tercero(pago2, cxp, usuario=None)
        with pytest.raises(PagoTerceroError, match="usuario solicitante"):
            solicitar_reintegro(pago2, usuario=None, comision=Decimal("0"))

        # Con Idempotency-Key + regla activa: 400 detail Y SolicitudAprobacion persistida (patrón T03)
        r_block = client_a.post(
            f"/api/finanzas/pagos-terceros/{pago2.pk}/abonar/",
            {"cxp": str(cxp.pk)},
            format="json",
            HTTP_IDEMPOTENCY_KEY="pt-block-1",
        )
        assert r_block.status_code == 400
        assert "requiere aprobación" in r_block.json()["detail"]
        sol = SolicitudAprobacion.objects.get(id_entidad_origen=pago2.pk, nombre_modelo_origen="PagoTercero")
        assert sol.estado_solicitud == "PENDIENTE"

        # Aprobar solicitud -> ahora abonar con nueva clave sí ejecuta
        registrar_decision(sol, user_a, aprobado=True, comentarios="Autorizado")
        r_ok = client_a.post(
            f"/api/finanzas/pagos-terceros/{pago2.pk}/abonar/",
            {"cxp": str(cxp.pk)},
            format="json",
            HTTP_IDEMPOTENCY_KEY="pt-exec-2",
        )
        assert r_ok.status_code == 200, r_ok.json()
        pago2.refresh_from_db()
        assert pago2.estado == "abonado"

        # Misma verificación para solicitar-reintegro
        pago3 = PagoTercero.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov,
            id_moneda=moneda_usd,
            monto=Decimal("280.00"),
            referencia_zelle="Z-REINT-3",
            fecha=_hoy(),
        )
        r_reint_block = client_a.post(
            f"/api/finanzas/pagos-terceros/{pago3.pk}/solicitar-reintegro/",
            {"comision": "5.00"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="pt-reint-block-3",
        )
        assert r_reint_block.status_code == 400
        sol3 = SolicitudAprobacion.objects.get(id_entidad_origen=pago3.pk, nombre_modelo_origen="PagoTercero")
        registrar_decision(sol3, user_a, aprobado=True)
        r_reint_ok = client_a.post(
            f"/api/finanzas/pagos-terceros/{pago3.pk}/solicitar-reintegro/",
            {"comision": "5.00"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="pt-reint-ok-3",
        )
        assert r_reint_ok.status_code == 200, r_reint_ok.json()

    def test_operacion_cambio_divisa_opt_in_y_proteccion_tampering_monto(
        self, client_a, empresa_a, user_a, moneda_usd, metodo_efectivo
    ):
        _setup_contabilidad_cambio_divisa(empresa_a)
        moneda_ves = Moneda.objects.create(
            tipo_moneda="fiat", codigo_iso="VES", nombre="Bolívar", simbolo="Bs.", es_generica=True, es_publica=True
        )
        caja_usd = Caja.objects.create(
            empresa=empresa_a, nombre="Caja USD Opt", moneda=moneda_usd, tipo_caja="REGISTRADORA"
        )
        caja_ves = Caja.objects.create(
            empresa=empresa_a, nombre="Caja VES Opt", moneda=moneda_ves, tipo_caja="REGISTRADORA"
        )

        tipo = TipoAprobacion.objects.create(
            id_empresa=empresa_a,
            codigo_tipo="OPERACION_CAMBIO_DIVISA",
            nombre_tipo="Cambio Divisas",
            modulo_origen="tesoreria",
        )
        FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            orden_etapa=1,
            nombre_etapa="Dirección Tesorería",
            id_usuario_aprobador=user_a,
            monto_minimo=Decimal("500.00"),
            activo=True,
        )

        payload = {
            "empresa": str(empresa_a.id_empresa),
            "numero_operacion": "CAM-OPT-001",
            "fecha_operacion": "2026-06-12T10:00:00Z",
            "tipo_operacion": "VENTA",
            "moneda_origen": str(moneda_usd.id_moneda),
            "moneda_destino": str(moneda_ves.id_moneda),
            "monto_origen": "600.0000",
            "tasa_cambio": "36.500000",
            "monto_destino": "21900.0000",
            "comision": "0.0000",
            "caja_origen": caja_usd.id_caja,
            "caja_destino": caja_ves.id_caja,
            "metodo_pago_origen": str(metodo_efectivo.id_metodo_pago),
            "metodo_pago_destino": str(metodo_efectivo.id_metodo_pago),
            "observaciones": "Venta opt-in",
        }
        r_block = client_a.post("/api/tesoreria/operaciones-cambio-divisa/", payload, format="json")
        assert r_block.status_code == 400
        assert "requiere aprobación" in str(r_block.json()["detail"])
        assert OperacionCambioDivisa.objects.count() == 0

        ref_uuid = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"omni:OperacionCambioDivisa:{empresa_a.pk}:CAM-OPT-001",
        )
        sol = SolicitudAprobacion.objects.get(id_entidad_origen=ref_uuid, nombre_modelo_origen="OperacionCambioDivisa")
        registrar_decision(sol, user_a, aprobado=True)

        # Si el cliente intenta subir el monto después de aprobar 600 → bloquea por monto_minimo_aprobado
        payload_tamper = dict(payload, monto_origen="900.0000", monto_destino="32850.0000")
        r_tamper = client_a.post("/api/tesoreria/operaciones-cambio-divisa/", payload_tamper, format="json")
        assert r_tamper.status_code == 400

        # Con el monto aprobado ejecuta atómicamente (201)
        r_ok = client_a.post("/api/tesoreria/operaciones-cambio-divisa/", payload, format="json")
        assert r_ok.status_code == 201, r_ok.json()
        assert OperacionCambioDivisa.objects.count() == 1


@pytest.mark.tenant
class TestComprasAprobacionesIDORYRLS:
    def test_idor_endpoints_source_to_po_y_aprobaciones(self, api_client, client_a, empresa_b, user_b, moneda_usd):
        prov_b = Proveedor.objects.create(id_empresa=empresa_b, razon_social="Prov B", rif="J-90000000-1")
        alm_b = Almacen.objects.create(id_empresa=empresa_b, nombre_almacen="Alm B", codigo_almacen="ALM-B-IDOR")
        req_b = RequisicionCompra.objects.create(
            id_empresa=empresa_b,
            id_solicitante=user_b,
            numero_requisicion="REQ-B-IDOR",
            fecha_requisicion=_hoy(),
            fecha_necesidad=_hoy() + timedelta(days=4),
            estado="APROBADA",
            justificacion="Ajena",
        )
        rfq_b = SolicitudCotizacion.objects.create(
            id_empresa=empresa_b,
            numero_solicitud="RFQ-B-IDOR",
            fecha_solicitud=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=4),
            estado="ENVIADA",
        )
        of_b = OfertaProveedor.objects.create(
            id_solicitud_cotizacion=rfq_b,
            id_proveedor=prov_b,
            numero_oferta="OF-B-IDOR",
            fecha_oferta=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=4),
            estado="RECIBIDA",
        )
        tipo_b = TipoAprobacion.objects.create(
            id_empresa=empresa_b, codigo_tipo="T-B-IDOR", nombre_tipo="TB", modulo_origen="compras"
        )
        sol_b = SolicitudAprobacion.objects.create(
            id_tipo_aprobacion=tipo_b,
            id_entidad_origen=uuid.uuid4(),
            nombre_modelo_origen="OrdenCompra",
            id_usuario_solicitante=user_b,
            estado_solicitud="PENDIENTE",
            monto=Decimal("10.00"),
        )

        # Anónimos -> 401
        assert api_client.post(f"/api/compras/requisiciones-compra/{req_b.pk}/enviar-aprobacion/").status_code == 401
        assert api_client.post("/api/compras/solicitudes-cotizacion/desde-requisiciones/").status_code == 401
        assert api_client.get(f"/api/compras/solicitudes-cotizacion/{rfq_b.pk}/comparar-ofertas/").status_code == 401
        assert api_client.post(f"/api/compras/ofertas-proveedor/{of_b.pk}/adjudicar/").status_code == 401
        assert (
            api_client.post(f"/api/gestion-aprobaciones/solicitudes-aprobacion/{sol_b.pk}/decidir/").status_code == 401
        )

        # Cross-tenant empresa A -> B -> 404
        assert client_a.post(f"/api/compras/requisiciones-compra/{req_b.pk}/enviar-aprobacion/").status_code == 404
        assert client_a.post(f"/api/compras/requisiciones-compra/{req_b.pk}/confirmar-aprobacion/").status_code == 404
        assert (
            client_a.post(
                "/api/compras/solicitudes-cotizacion/desde-requisiciones/",
                {
                    "requisicion_ids": [str(req_b.pk)],
                    "proveedores_ids": [str(prov_b.pk)],
                    "fecha_vencimiento": (_hoy() + timedelta(days=3)).isoformat(),
                },
                format="json",
            ).status_code
            == 404
        )
        assert client_a.get(f"/api/compras/solicitudes-cotizacion/{rfq_b.pk}/comparar-ofertas/").status_code == 404
        assert (
            client_a.post(
                f"/api/compras/ofertas-proveedor/{of_b.pk}/adjudicar/",
                {"id_almacen_destino": str(alm_b.pk)},
                format="json",
            ).status_code
            == 404
        )
        assert (
            client_a.post(
                f"/api/gestion-aprobaciones/solicitudes-aprobacion/{sol_b.pk}/decidir/",
                {"aprobado": True},
                format="json",
            ).status_code
            == 404
        )

    def test_rls_postgresql_compras_y_aprobaciones_aislado(self, empresa_a, empresa_b, user_a, user_b, rls_test_role):
        req_a = RequisicionCompra.objects.create(
            id_empresa=empresa_a,
            id_solicitante=user_a,
            numero_requisicion="REQ-RLS-A",
            fecha_requisicion=_hoy(),
            fecha_necesidad=_hoy() + timedelta(days=1),
            justificacion="A",
        )
        req_b = RequisicionCompra.objects.create(
            id_empresa=empresa_b,
            id_solicitante=user_b,
            numero_requisicion="REQ-RLS-B",
            fecha_requisicion=_hoy(),
            fecha_necesidad=_hoy() + timedelta(days=1),
            justificacion="B",
        )
        with connection.cursor() as cur:
            if rls_test_role is not None:
                cur.execute(f'SET ROLE "{rls_test_role}"')
            try:
                rls.apply_context([empresa_a.id_empresa], bypass=False)
                assert list(RequisicionCompra.objects.values_list("pk", flat=True)) == [req_a.pk]
                rls.apply_context([empresa_b.id_empresa], bypass=False)
                assert list(RequisicionCompra.objects.values_list("pk", flat=True)) == [req_b.pk]
                rls.apply_context([], bypass=False)
                assert RequisicionCompra.objects.count() == 0
            finally:
                rls.apply_system_default()
                if rls_test_role is not None:
                    cur.execute("RESET ROLE")


@pytest.mark.tenant
class TestComprasYAprobacionesMCP:
    def test_cuatro_tools_mcp_registradas_y_scopes_configurados(self):
        nombres_compras = {item["name"] for item in COMPRAS_MCP_TOOLS}
        nombres_aprob = {item["name"] for item in APROBACIONES_MCP_TOOLS}
        assert nombres_compras == {"compras_crear_requisicion", "compras_adjudicar_oferta"}
        assert nombres_aprob == {"aprobaciones_pendientes", "aprobaciones_decidir"}
        assert set(CORE_MCP_TOOLS.keys()).issuperset(nombres_compras | nombres_aprob)
        caps = set(settings.MCP_AGENT_CAPABILITIES["scopes"])
        assert {"compras:write", "aprobaciones:read", "aprobaciones:write"}.issubset(caps)

    def test_flujo_mcp_completo_bajo_rls_y_validaciones(
        self, empresa_a, empresa_b, user_a, user_b, moneda_usd, rls_test_role
    ):
        dep_a = Departamento.objects.create(id_empresa=empresa_a, nombre_departamento="Logística")
        rol_a = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Aprobador MCP")
        UsuarioRoles.objects.create(id_usuario=user_a, id_rol=rol_a)
        tipo = TipoAprobacion.objects.create(
            id_empresa=empresa_a, codigo_tipo="REQUISICION_COMPRA", nombre_tipo="Req MCP", modulo_origen="compras"
        )
        FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            id_departamento=dep_a,
            orden_etapa=1,
            nombre_etapa="Líder Logística",
            rol_aprobador=rol_a,
            monto_minimo=Decimal("10.00"),
            activo=True,
        )

        unidad = UnidadMedida.objects.create(
            id_empresa=empresa_a, nombre="Caja MCP", abreviatura="CJA-M", tipo="CANTIDAD"
        )
        cat = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="MCP Cat")
        prod = Producto.objects.create(
            id_empresa=empresa_a,
            nombre_producto="Papel Bond",
            sku="MCP-BOND",
            id_unidad_medida_base=unidad,
            id_categoria=cat,
            id_moneda_precio=moneda_usd,
        )
        prov = Proveedor.objects.create(id_empresa=empresa_a, razon_social="Prov MCP", rif="J-60000000-1")
        alm = Almacen.objects.create(id_empresa=empresa_a, nombre_almacen="Alm MCP", codigo_almacen="ALM-MCP")

        emp_id = str(empresa_a.pk)
        tok_c_write = _token(empresa_a, ["compras:write"])
        tok_a_read = _token(empresa_a, ["aprobaciones:read"])
        tok_a_write = _token(empresa_a, ["aprobaciones:write"])
        tok_b = _token(empresa_b, ["compras:write", "aprobaciones:read", "aprobaciones:write"])

        # Scopes insuficientes -> PermissionError
        with pytest.raises(PermissionError):
            compras_crear_requisicion(
                tok_a_read, emp_id, "REQ-M1", "x", [{"id_producto": str(prod.pk), "cantidad": "1"}]
            )
        with pytest.raises(PermissionError):
            aprobaciones_pendientes(tok_c_write, emp_id)
        with pytest.raises(PermissionError):
            aprobaciones_decidir(tok_a_read, emp_id, str(uuid.uuid4()), str(user_a.pk), True)

        # Token ajeno -> PermissionError
        with pytest.raises(PermissionError):
            aprobaciones_pendientes(tok_b, emp_id)

        with override_settings(RLS_ENABLED=True):
            # 1) Crear requisición + enviar a aprobación vía MCP
            res_req = compras_crear_requisicion(
                tok_c_write,
                emp_id,
                "REQ-MCP-01",
                "Reposición almacén",
                [{"id_producto": str(prod.pk), "cantidad": "10", "precio_estimado": "15"}],
                prioridad="URGENTE",
                id_departamento=str(dep_a.pk),
                id_solicitante=str(user_a.pk),
                enviar_aprobacion=True,
            )
            assert res_req["estado"] == "PENDIENTE"
            assert res_req["monto_estimado"] == "150.0000"

            # 2) Listar pendientes y aprobar vía MCP
            pend = aprobaciones_pendientes(tok_a_read, emp_id, codigo_tipo="REQUISICION_COMPRA")
            assert len(pend) == 1
            sol_id = pend[0]["id_solicitud_aprobacion"]
            assert pend[0]["id_departamento"] == str(dep_a.pk)

            # Verificar filtro solo_escaladas
            assert aprobaciones_pendientes(tok_a_read, emp_id, solo_escaladas=True) == []

            res_dec = aprobaciones_decidir(tok_a_write, emp_id, sol_id, str(user_a.pk), True, "Aprobada MCP")
            assert res_dec["estado_solicitud"] == "APROBADA"

        # Confirmar requisición → crear RFQ → oferta → adjudicar vía MCP
        req_obj = RequisicionCompra.objects.get(pk=res_req["id_requisicion"])
        confirmar_aprobacion_requisicion(req_obj, user_a)
        rfq = crear_rfq_desde_requisiciones(empresa_a, [req_obj.pk], [prov.pk], _hoy() + timedelta(days=5))
        oferta = OfertaProveedor.objects.create(
            id_solicitud_cotizacion=rfq,
            id_proveedor=prov,
            numero_oferta="OF-MCP-01",
            fecha_oferta=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=4),
            estado="RECIBIDA",
            monto_total=Decimal("120.0000"),
        )
        DetalleOfertaProveedor.objects.create(
            id_oferta=oferta,
            id_producto=prod,
            cantidad=Decimal("10.0000"),
            precio_unitario=Decimal("12.0000"),
            subtotal=Decimal("120.0000"),
        )

        res_adj = compras_adjudicar_oferta(
            tok_c_write,
            emp_id,
            str(oferta.pk),
            str(alm.pk),
            adjudicacion_parcial=[{"id_producto": str(prod.pk), "cantidad": "5.0000"}],
            rechazar_competidoras=True,
            usuario_id=str(user_a.pk),
        )
        assert res_adj["estado_orden"] == "BORRADOR"
        assert res_adj["monto_total"] == "60.0000"
        assert res_adj["rfq_estado"] == "RESPONDIDA"
        assert OrdenCompra.objects.filter(pk=res_adj["id_orden_compra"], id_almacen_destino=alm).exists()

        # Validaciones de error seguras en las 4 tools MCP
        assert "error" in compras_crear_requisicion(
            tok_c_write, emp_id, "REQ-MCP-01", "dup", [{"id_producto": str(prod.pk), "cantidad": "1"}]
        )
        assert "error" in compras_crear_requisicion(
            tok_c_write, emp_id, "REQ-BAD-1", "", [{"id_producto": str(prod.pk), "cantidad": "1"}]
        )
        assert "error" in compras_crear_requisicion(
            tok_c_write,
            emp_id,
            "REQ-BAD-2",
            "x",
            [{"id_producto": str(prod.pk), "cantidad": "1"}],
            prioridad="INVALID",
        )
        assert "error" in compras_crear_requisicion(
            tok_c_write,
            emp_id,
            "REQ-BAD-3",
            "x",
            [{"id_producto": str(prod.pk), "cantidad": "1"}],
            fecha_necesidad="bad-date",
        )
        assert "error" in compras_crear_requisicion(
            tok_c_write,
            emp_id,
            "REQ-BAD-4",
            "x",
            [{"id_producto": str(prod.pk), "cantidad": "1"}],
            id_departamento=str(uuid.uuid4()),
        )
        assert "error" in compras_crear_requisicion(tok_c_write, emp_id, "REQ-BAD-5", "x", [])
        assert "error" in compras_crear_requisicion(tok_c_write, emp_id, "REQ-BAD-6", "x", ["not-dict"])  # type: ignore[list-item]
        assert "error" in compras_crear_requisicion(
            tok_c_write, emp_id, "REQ-BAD-7", "x", [{"id_producto": str(uuid.uuid4()), "cantidad": "1"}]
        )
        assert "error" in compras_crear_requisicion(
            tok_c_write, emp_id, "REQ-BAD-8", "x", [{"id_producto": str(prod.pk), "cantidad": "0"}]
        )
        assert "error" in compras_crear_requisicion(
            tok_c_write, emp_id, "REQ-BAD-9", "x", [{"id_producto": str(prod.pk), "cantidad": True}]
        )
        assert "error" in compras_crear_requisicion(
            tok_c_write, emp_id, "REQ-BAD-10", "x", [{"id_producto": str(prod.pk), "cantidad": "NaN"}]
        )
        assert "error" in compras_crear_requisicion(
            tok_c_write,
            emp_id,
            "REQ-BAD-11",
            "x",
            [{"id_producto": str(prod.pk), "cantidad": "1", "precio_estimado": "-5"}],
        )
        assert "error" in compras_adjudicar_oferta(tok_c_write, emp_id, "no-uuid", str(alm.pk))
        assert "error" in compras_adjudicar_oferta(tok_c_write, emp_id, str(uuid.uuid4()), str(alm.pk))
        assert "error" in compras_adjudicar_oferta(tok_c_write, emp_id, str(oferta.pk), str(uuid.uuid4()))
        assert "error" in compras_adjudicar_oferta(
            tok_c_write, emp_id, str(oferta.pk), str(alm.pk), usuario_id=str(uuid.uuid4())
        )
        assert "error" in compras_adjudicar_oferta(
            tok_c_write, emp_id, str(oferta.pk), str(alm.pk), adjudicacion_parcial="no-lista"
        )  # type: ignore[arg-type]
        assert "error" in compras_adjudicar_oferta(
            tok_c_write, emp_id, str(oferta.pk), str(alm.pk), adjudicacion_parcial=["bad"]
        )  # type: ignore[list-item]
        assert "error" in aprobaciones_pendientes(tok_a_read, emp_id, limit=True)  # type: ignore[arg-type]
        assert "error" in aprobaciones_decidir(tok_a_write, emp_id, "no-uuid", str(user_a.pk), True)
        assert "error" in aprobaciones_decidir(tok_a_write, emp_id, sol_id, str(user_a.pk), "yes")  # type: ignore[arg-type]
        assert "error" in aprobaciones_decidir(tok_a_write, emp_id, str(uuid.uuid4()), str(user_a.pk), True)
        assert "error" in aprobaciones_decidir(tok_a_write, emp_id, sol_id, str(user_b.pk), True)
