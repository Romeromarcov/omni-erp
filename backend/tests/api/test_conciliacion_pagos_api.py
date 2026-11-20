"""
Tests API REST E2E de conciliación N:M de pagos (Ola A3).

Cubren:
  - Flujo completo: POST /pagos/ anticipo -> GET estado-conciliacion -> GET sugerir-distribucion ->
    POST /pagos/{id}/conciliar-documentos/ -> saldo a favor -> POST /asignaciones-pago/ ->
    GET /asignaciones-pago/ (filtros + search) -> POST revertir.
  - Idempotencia con cabecera Idempotency-Key (reintento exacto y conflicto 422).
  - HTTP 405 en PUT/PATCH/DELETE de AsignacionPagoViewSet.
  - Error 422 (ConciliacionContableError) con rollback completo cuando falta MapeoContable.
  - Error 400 (ConciliacionPagoError) y validación segura de query params sin 500.
  - Guarda de PagoSerializer.validate() que impide mutar Pago.id_contacto con asignaciones activas.
  - Campos contacto_id / pago_contacto_id expuestos en CxC, CxP y Tesorería.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.compras.models import FacturaCompra, OrdenCompra
from apps.contabilidad.models import MapeoContable, PlanCuentas
from apps.core.models import Contacto
from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.models import CuentaPorCobrar
from apps.cuentas_por_pagar.models import CuentaPorPagar
from apps.finanzas.models import AsignacionPago, CuentaBancariaEmpresa, Pago
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor, EntidadSincronizada
from apps.proveedores.models import Proveedor
from apps.tesoreria.models import MovimientoBancario
from apps.ventas.models import FacturaFiscal

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _hoy():
    return timezone.localdate()


def _configurar_mapeos(empresa) -> None:
    def _cta(codigo: str, nombre: str, tipo: str, nat: str) -> PlanCuentas:
        return PlanCuentas.objects.create(
            id_empresa=empresa,
            codigo_cuenta=codigo,
            nombre_cuenta=nombre,
            tipo_cuenta=tipo,
            naturaleza=nat,
            nivel=3,
        )

    banco = _cta("1.1.01", "Banco", "ACTIVO", "DEUDORA")
    cxc = _cta("1.1.02", "CxC", "ACTIVO", "DEUDORA")
    cxp = _cta("2.1.01", "CxP", "PASIVO", "ACREEDORA")
    MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento="PAGO_CXC",
        cuenta_debe=banco,
        cuenta_haber=cxc,
        descripcion_plantilla="Cobro {numero}",
        activo=True,
    )
    MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento="PAGO_CXP",
        cuenta_debe=cxp,
        cuenta_haber=banco,
        descripcion_plantilla="Pago {numero}",
        activo=True,
    )


def _crear_contacto(empresa, *, nombre: str, rif: str, es_cliente: bool = True, es_proveedor: bool = True) -> Contacto:
    return Contacto.objects.create(
        id_empresa=empresa,
        tipo_persona="JURIDICA",
        nombre=nombre,
        rif=rif,
        es_cliente=es_cliente,
        es_proveedor=es_proveedor,
    )


def _crear_factura_venta(
    empresa,
    cliente: Cliente,
    moneda,
    *,
    numero: str,
    monto_total: Decimal,
    dias_vencimiento: int = 10,
) -> FacturaFiscal:
    hoy = _hoy()
    return FacturaFiscal.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        numero_control=f"CTRL-{numero}",
        numero_factura=numero,
        fecha_emision=hoy,
        fecha_vencimiento=hoy + timedelta(days=dias_vencimiento),
        base_imponible=monto_total,
        monto_iva=Decimal("0.0000"),
        monto_igtf=Decimal("0.0000"),
        monto_total=monto_total,
        id_moneda=moneda,
        tasa_cambio=Decimal("1.0000"),
        estado="EMITIDA",
        activo=True,
    )


class TestConciliacionPagosAPIFlujoCompleto:
    def test_flujo_completo_anticipo_fifo_conciliacion_saldo_favor_y_reversion(
        self, client_a, empresa_a, moneda_usd, metodo_efectivo
    ):
        contacto = _crear_contacto(empresa_a, nombre="Grupo Andino C.A.", rif="J-30111222-3")
        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social=contacto.nombre,
            rif=contacto.rif,
            contacto=contacto,
        )
        fv1 = _crear_factura_venta(
            empresa_a, cliente, moneda_usd, numero="FV-API-001", monto_total=Decimal("100.0000"), dias_vencimiento=3
        )
        fv2 = _crear_factura_venta(
            empresa_a, cliente, moneda_usd, numero="FV-API-002", monto_total=Decimal("80.0000"), dias_vencimiento=15
        )
        cxc = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente,
            monto=Decimal("50.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=20),
            referencia_externa="CXC-API-01",
        )

        # 1) Crear pago anticipo por API REST
        resp_pago = client_a.post(
            "/api/finanzas/pagos/",
            {
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "ANTICIPO",
                "id_documento": str(uuid.uuid4()),
                "id_contacto": str(contacto.pk),
                "fecha_pago": timezone.now().isoformat(),
                "monto": "200.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
                "referencia": "TRF-ANTICIPO-API",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="pago-anticipo-1",
        )
        assert resp_pago.status_code == 201, resp_pago.content
        pago_id = resp_pago.data["id_pago"]

        # 2) Consultar estado-conciliacion del contacto
        resp_estado = client_a.get(
            f"/api/finanzas/contactos/{contacto.pk}/estado-conciliacion/?tipo_operacion=INGRESO"
        )
        assert resp_estado.status_code == 200, resp_estado.content
        assert resp_estado.data["contacto"]["id_contacto"] == str(contacto.pk)
        assert resp_estado.data["saldo_a_favor"]["total_pagos_con_saldo"] == 1
        assert resp_estado.data["pagos_disponibles"][0]["id_pago"] == pago_id
        tipos_ob = {o["tipo_documento"] for o in resp_estado.data["obligaciones_abiertas"]}
        assert {"FACTURA_VENTA", "CUENTA_POR_COBRAR"}.issubset(tipos_ob)

        # 3) Sugerir distribución FIFO (restringida y general)
        resp_fifo = client_a.get(f"/api/finanzas/pagos/{pago_id}/sugerir-distribucion/?tipo_documento=FACTURA_VENTA")
        assert resp_fifo.status_code == 200, resp_fifo.content
        assert Decimal(resp_fifo.data["saldo_disponible"]) == Decimal("200.0000")
        assert [p["referencia"] for p in resp_fifo.data["propuestas"]] == ["FV-API-001", "FV-API-002"]
        assert Decimal(resp_fifo.data["saldo_a_favor_resultante"]) == Decimal("20.0000")

        # 4) Aplicar pago parcialmente sobre fv1 (100) y fv2 (40), dejando 60 a favor
        payload_conciliar = {
            "asignaciones": [
                {"tipo_documento": "FACTURA_VENTA", "id_documento": str(fv1.pk), "monto_asignado_pago": "100.0000"},
                {"tipo_documento": "FACTURA_VENTA", "id_documento": str(fv2.pk), "monto_asignado_pago": "40.0000"},
            ],
            "descripcion": "Conciliación parcial API",
            "generar_asiento": False,
        }
        resp_conc = client_a.post(
            f"/api/finanzas/pagos/{pago_id}/conciliar-documentos/",
            payload_conciliar,
            format="json",
            HTTP_IDEMPOTENCY_KEY="conciliar-lote-1",
        )
        assert resp_conc.status_code == 200, resp_conc.content
        assert Decimal(resp_conc.data["saldo_disponible"]) == Decimal("60.0000")
        assert len(resp_conc.data["asignaciones"]) == 2
        asig_fv2_id = next(
            a["id_asignacion"] for a in resp_conc.data["asignaciones"] if a["id_documento"] == str(fv2.pk)
        )

        # Reintento idempotente con misma Idempotency-Key no duplica
        resp_conc_retry = client_a.post(
            f"/api/finanzas/pagos/{pago_id}/conciliar-documentos/",
            payload_conciliar,
            format="json",
            HTTP_IDEMPOTENCY_KEY="conciliar-lote-1",
        )
        assert resp_conc_retry.status_code == 200
        assert AsignacionPago.objects.filter(id_pago_id=pago_id, estado="ACTIVA").count() == 2

        # Misma clave + payload distinto -> 422 conflicto idempotencia
        resp_conc_conflict = client_a.post(
            f"/api/finanzas/pagos/{pago_id}/conciliar-documentos/",
            {
                "asignaciones": [
                    {"tipo_documento": "FACTURA_VENTA", "id_documento": str(fv2.pk), "monto_asignado_pago": "10.0000"}
                ],
                "generar_asiento": False,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="conciliar-lote-1",
        )
        assert resp_conc_conflict.status_code == 422

        # 5) Aplicar saldo a favor restante (50) contra la CxC usando POST /api/finanzas/asignaciones-pago/
        payload_asig_cxc = {
            "pago": pago_id,
            "asignaciones": [
                {"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": str(cxc.pk), "monto_asignado_pago": "50.0000"}
            ],
            "generar_asiento": False,
        }
        resp_asig = client_a.post(
            "/api/finanzas/asignaciones-pago/",
            payload_asig_cxc,
            format="json",
            HTTP_IDEMPOTENCY_KEY="crear-asig-1",
        )
        assert resp_asig.status_code == 201, resp_asig.content
        assert Decimal(resp_asig.data["saldo_disponible"]) == Decimal("10.0000")
        assert len(resp_asig.data["asignaciones"]) == 1

        # Reintento idempotente en /asignaciones-pago/
        resp_asig_retry = client_a.post(
            "/api/finanzas/asignaciones-pago/",
            payload_asig_cxc,
            format="json",
            HTTP_IDEMPOTENCY_KEY="crear-asig-1",
        )
        assert resp_asig_retry.status_code == 201
        assert AsignacionPago.objects.filter(id_pago_id=pago_id, estado="ACTIVA").count() == 3

        # 6) Listar / filtrar / buscar sin errores 500
        resp_list = client_a.get(
            f"/api/finanzas/asignaciones-pago/?pago={pago_id}&contacto={contacto.pk}"
            f"&tipo_documento=FACTURA_VENTA&id_documento={fv2.pk}&estado=ACTIVA&search=Grupo"
        )
        assert resp_list.status_code == 200
        results = resp_list.data["results"] if "results" in resp_list.data else resp_list.data
        assert len(results) == 1
        assert results[0]["id_asignacion"] == asig_fv2_id

        # HTTP 405 en PUT/PATCH/DELETE (inmutabilidad auditada)
        assert (
            client_a.patch(
                f"/api/finanzas/asignaciones-pago/{asig_fv2_id}/", {"motivo": "x"}, format="json"
            ).status_code
            == 405
        )
        assert client_a.put(f"/api/finanzas/asignaciones-pago/{asig_fv2_id}/", {}, format="json").status_code == 405
        assert client_a.delete(f"/api/finanzas/asignaciones-pago/{asig_fv2_id}/").status_code == 405

        # 7) Revertir asignación con Idempotency-Key
        resp_rev = client_a.post(
            f"/api/finanzas/asignaciones-pago/{asig_fv2_id}/revertir/",
            {"motivo": "Ajuste por nota de crédito"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rev-asig-1",
        )
        assert resp_rev.status_code == 200, resp_rev.content
        assert resp_rev.data["estado"] == "REVERTIDA"
        assert resp_rev.data["motivo_reversion"] == "Ajuste por nota de crédito"

        # Reintento idempotente de reversión devuelve el mismo 200 sin error de doble reversión
        resp_rev_retry = client_a.post(
            f"/api/finanzas/asignaciones-pago/{asig_fv2_id}/revertir/",
            {"motivo": "Ajuste por nota de crédito"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rev-asig-1",
        )
        assert resp_rev_retry.status_code == 200
        assert resp_rev_retry.data["estado"] == "REVERTIDA"

        # Segundo intento SIN misma Idempotency-Key (reversión duplicada) -> 400 ConciliacionPagoError
        resp_rev_dup = client_a.post(
            f"/api/finanzas/asignaciones-pago/{asig_fv2_id}/revertir/",
            {"motivo": "Segundo intento"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="rev-asig-2",
        )
        assert resp_rev_dup.status_code == 400

    def test_egreso_estado_conciliacion_y_asignacion_cxp_y_factura_compra(
        self, client_a, empresa_a, moneda_usd, metodo_efectivo
    ):
        contacto = _crear_contacto(
            empresa_a, nombre="Suministros Beta S.A.", rif="J-40123456-7", es_cliente=False, es_proveedor=True
        )
        proveedor = Proveedor.objects.create(
            id_empresa=empresa_a,
            razon_social=contacto.nombre,
            rif=contacto.rif,
            contacto=contacto,
        )
        cxp = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor,
            monto_total=Decimal("90.0000"),
            monto_pendiente=Decimal("90.0000"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=5),
            estado="PENDIENTE",
            referencia_externa="CXP-B-01",
        )
        oc = OrdenCompra.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor,
            numero_orden="OC-API-01",
            fecha_orden=_hoy(),
            estado="APROBADA",
        )
        fc = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=oc,
            numero_factura="FC-API-01",
            fecha_emision=_hoy(),
            monto_total=Decimal("120.0000"),
            activo=True,
        )
        pago = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="EGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("150.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
            referencia="EGR-01",
        )

        # CxC sincronizada via proveedor:<uuid> también se descubre en modo mixto/INGRESO
        prov_con = ConectorProveedor.objects.create(
            codigo=f"odoo-api-{uuid.uuid4().hex[:6]}",
            nombre="Odoo API",
            capacidades=["contactos"],
        )
        conector = ConectorInstancia.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov_con,
            nombre="Odoo Principal",
            configuracion={},
            activo=True,
        )
        EntidadSincronizada.objects.create(
            id_instancia=conector,
            tipo_entidad="contactos",
            id_externo="ext-partner-77",
            id_omni=str(contacto.pk),
            activo=True,
        )
        CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=None,
            cliente_externo_id=f"proveedor:{proveedor.pk}",
            cliente_externo_nombre=proveedor.razon_social,
            monto=Decimal("25.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=12),
            referencia_externa="CXC-PROV-1",
        )

        # GET sin tipo_operacion descubre INGRESO + EGRESO
        resp_all = client_a.get(f"/api/finanzas/contactos/{contacto.pk}/estado-conciliacion/")
        assert resp_all.status_code == 200, resp_all.content
        tipos = {o["tipo_documento"] for o in resp_all.data["obligaciones_abiertas"]}
        assert {"CUENTA_POR_PAGAR", "FACTURA_COMPRA", "CUENTA_POR_COBRAR"}.issubset(tipos)

        # GET filtrado a EGRESO
        resp_egr = client_a.get(f"/api/finanzas/contactos/{contacto.pk}/estado-conciliacion/?tipo_operacion=EGRESO")
        assert resp_egr.status_code == 200
        tipos_egr = {o["tipo_documento"] for o in resp_egr.data["obligaciones_abiertas"]}
        assert tipos_egr == {"CUENTA_POR_PAGAR", "FACTURA_COMPRA"}

        resp_conc = client_a.post(
            f"/api/finanzas/pagos/{pago.pk}/conciliar-documentos/",
            {
                "asignaciones": [
                    {
                        "tipo_documento": "CUENTA_POR_PAGAR",
                        "id_documento": str(cxp.pk),
                        "monto_asignado_pago": "90.00",
                    },
                    {"tipo_documento": "FACTURA_COMPRA", "id_documento": str(fc.pk), "monto_asignado_pago": "60.00"},
                ],
                "generar_asiento": False,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="conc-egr-1",
        )
        assert resp_conc.status_code == 200, resp_conc.content
        assert Decimal(resp_conc.data["saldo_disponible"]) == Decimal("0.0000")

    def test_error_contable_422_rollback_y_guard_pago_contacto_400(
        self, client_a, empresa_a, moneda_usd, metodo_efectivo
    ):
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])

        contacto1 = _crear_contacto(empresa_a, nombre="Cliente Cero C.A.", rif="J-50000001-1")
        contacto2 = _crear_contacto(empresa_a, nombre="Cliente Otro C.A.", rif="J-50000002-2")
        cliente1 = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social=contacto1.nombre,
            rif=contacto1.rif,
            contacto=contacto1,
        )
        fv = _crear_factura_venta(
            empresa_a, cliente1, moneda_usd, numero="FV-ERR-422", monto_total=Decimal("100.0000")
        )
        pago = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto1,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("100.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )

        # Sin MapeoContable PAGO_CXC y contabilidad_activa=True -> 422 y 0 filas creadas
        resp_422 = client_a.post(
            f"/api/finanzas/pagos/{pago.pk}/conciliar-documentos/",
            {
                "asignaciones": [
                    {"tipo_documento": "FACTURA_VENTA", "id_documento": str(fv.pk), "monto_asignado_pago": "50.00"}
                ],
                "generar_asiento": True,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="conc-err-422",
        )
        assert resp_422.status_code == 422, resp_422.content
        assert AsignacionPago.objects.filter(id_pago=pago).count() == 0

        # Al configurar mapeos sí aplica 201 en /asignaciones-pago/
        _configurar_mapeos(empresa_a)
        resp_ok = client_a.post(
            "/api/finanzas/asignaciones-pago/",
            {
                "pago": str(pago.pk),
                "asignaciones": [
                    {"tipo_documento": "FACTURA_VENTA", "id_documento": str(fv.pk), "monto_asignado_pago": "50.00"}
                ],
                "generar_asiento": True,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="conc-ok-map",
        )
        assert resp_ok.status_code == 201, resp_ok.content
        asig_id = resp_ok.data["asignaciones"][0]["id_asignacion"]

        # Guard PR-10 #2: PATCH Pago.id_contacto bloqueado mientras tenga asignaciones activas
        resp_patch_block = client_a.patch(
            f"/api/finanzas/pagos/{pago.pk}/",
            {"id_contacto": str(contacto2.pk)},
            format="json",
        )
        assert resp_patch_block.status_code == 400, resp_patch_block.content
        assert "id_contacto" in resp_patch_block.data

        # Mantener el mismo contacto (o editar referencia) sí pasa
        resp_patch_same = client_a.patch(
            f"/api/finanzas/pagos/{pago.pk}/",
            {"id_contacto": str(contacto1.pk), "referencia": "REF-EDIT"},
            format="json",
        )
        assert resp_patch_same.status_code == 200, resp_patch_same.content

        # Revertir y verificar que ahora sí permite cambiar id_contacto
        assert (
            client_a.post(
                f"/api/finanzas/asignaciones-pago/{asig_id}/revertir/",
                {"motivo": "Liberar contacto"},
                format="json",
                HTTP_IDEMPOTENCY_KEY="rev-guard-1",
            ).status_code
            == 200
        )
        resp_patch_unblocked = client_a.patch(
            f"/api/finanzas/pagos/{pago.pk}/",
            {"id_contacto": str(contacto2.pk)},
            format="json",
        )
        assert resp_patch_unblocked.status_code == 200

    def test_validacion_parametros_invalidos_y_campos_contacto_en_cxc_cxp_tesoreria(
        self, client_a, empresa_a, moneda_usd, metodo_efectivo
    ):
        contacto = _crear_contacto(empresa_a, nombre="Contacto Serializers", rif="J-60000001-6")
        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social=contacto.nombre,
            rif=contacto.rif,
            contacto=contacto,
        )
        proveedor = Proveedor.objects.create(
            id_empresa=empresa_a,
            razon_social=contacto.nombre,
            rif=contacto.rif,
            contacto=contacto,
        )
        CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente,
            monto=Decimal("40.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=7),
        )
        CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=None,
            cliente_externo_id=f"proveedor:{proveedor.pk}",
            cliente_externo_nombre=proveedor.razon_social,
            monto=Decimal("15.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=7),
        )
        CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=None,
            cliente_externo_id="sin-match-externo",
            cliente_externo_nombre="Externo",
            monto=Decimal("10.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=7),
        )
        CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=None,
            cliente_externo_id="proveedor:no-es-uuid",
            cliente_externo_nombre="Proveedor Mal UUID",
            monto=Decimal("12.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=7),
        )
        CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor,
            monto_total=Decimal("80.0000"),
            monto_pendiente=Decimal("80.0000"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=7),
            estado="PENDIENTE",
        )
        pago = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("40.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        cuenta_bco = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_a,
            nombre_banco="Banco Test",
            numero_cuenta="0102-0001",
            tipo_cuenta="CORRIENTE",
            id_moneda=moneda_usd,
        )
        MovimientoBancario.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_bco,
            fecha_mov=_hoy(),
            descripcion="Ingreso conciliado",
            tipo="CREDITO",
            monto=Decimal("40.00"),
            referencia="REF-BCO-1",
            estado="CONCILIADO",
            id_pago_conciliado=pago,
        )

        # Validaciones de query params controladas -> 400 (nunca 500)
        assert client_a.get("/api/finanzas/asignaciones-pago/?pago=no-es-uuid").status_code == 400
        assert client_a.get("/api/finanzas/asignaciones-pago/?contacto=mal").status_code == 400
        assert client_a.get("/api/finanzas/asignaciones-pago/?tipo_documento=OTRO").status_code == 400
        assert client_a.get("/api/finanzas/asignaciones-pago/?estado=INVALIDO").status_code == 400
        assert client_a.get("/api/finanzas/asignaciones-pago/?search=abc%00def").status_code == 400
        assert (
            client_a.get(f"/api/finanzas/pagos/{pago.pk}/sugerir-distribucion/?tipo_documento=BAD").status_code == 400
        )
        pago_sin_contacto = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=None,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("10.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        assert client_a.get(f"/api/finanzas/pagos/{pago_sin_contacto.pk}/sugerir-distribucion/").status_code == 400
        assert (
            client_a.get(f"/api/finanzas/contactos/{contacto.pk}/estado-conciliacion/?tipo_operacion=OTRO").status_code
            == 400
        )

        # Sobre-asignación supera saldo disponible -> 400 ConciliacionPagoError
        assert (
            client_a.post(
                f"/api/finanzas/pagos/{pago.pk}/conciliar-documentos/",
                {
                    "asignaciones": [
                        {
                            "tipo_documento": "CUENTA_POR_COBRAR",
                            "id_documento": str(CuentaPorCobrar.objects.first().pk),
                            "monto_asignado_pago": "999.00",
                        }
                    ],
                    "generar_asiento": False,
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY="over-alloc-1",
            ).status_code
            == 400
        )

        # Verificar contacto_id en CxC, CxP y pago_contacto_id en Tesorería
        r_cxc = client_a.get("/api/cxc/cuentas-por-cobrar/")
        assert r_cxc.status_code == 200
        items_cxc = r_cxc.data["results"] if "results" in r_cxc.data else r_cxc.data
        assert {item["contacto_id"] for item in items_cxc} == {str(contacto.pk), None}

        r_cxp = client_a.get("/api/cuentas-por-pagar/cuentas-por-pagar/")
        assert r_cxp.status_code == 200
        items_cxp = r_cxp.data["results"] if "results" in r_cxp.data else r_cxp.data
        assert items_cxp[0]["contacto_id"] == str(contacto.pk)
        assert items_cxp[0]["proveedor_nombre"] == contacto.nombre

        r_mov = client_a.get("/api/tesoreria/movimientos-bancarios/")
        assert r_mov.status_code == 200
        items_mov = r_mov.data["results"] if "results" in r_mov.data else r_mov.data
        assert items_mov[0]["pago_contacto_id"] == str(contacto.pk)
