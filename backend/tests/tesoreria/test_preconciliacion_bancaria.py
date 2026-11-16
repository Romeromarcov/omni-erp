"""Suite integral para el motor multi-tenant de pre-conciliación bancaria y cola de revisión humana."""

from __future__ import annotations

from datetime import date, datetime, timezone as dt_tz
from decimal import Decimal as D
from typing import Any
from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIClient

from apps.contabilidad.models import PlanCuentas
from apps.core.models import CapabilityToken, Contacto
from apps.core.rls import apply_context, apply_system_default, current_role_bypasses_rls
from apps.core.uuid import uuid7
from apps.crm.models import Cliente
from apps.cuentas_por_pagar.models import CuentaPorPagar
from apps.finanzas.models import CuentaBancariaEmpresa, MetodoPago, Moneda, Pago
from apps.gastos.models import CategoriaGasto, Gasto
from apps.integration_hub.connectors.odoo.client import OdooAuthError
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor
from apps.proveedores.models import Proveedor
from apps.tesoreria.extractos import (
    ExtractoBancarioError,
    desactivar_extracto_bancario,
    importar_extracto_bancario,
)
from apps.tesoreria.extractos.lector_hojas import construir_xlsx_simple
from apps.tesoreria.mcp import (
    tesoreria_generar_propuestas_conciliacion,
    tesoreria_listar_propuestas_conciliacion,
)
from apps.tesoreria.models import (
    ConciliacionBancaria,
    ConfiguracionConciliacionCuenta,
    DecisionPreconciliacionBancaria,
    MovimientoBancario,
    PropuestaConciliacionBancaria,
)
from apps.tesoreria.preconciliacion import (
    TIPO_AMBIGUO,
    TIPO_CUENTA,
    TIPO_PAGO,
    TIPO_SIN_PROPUESTA,
    DecisionPreconciliacionInvalida,
    MovimientoParaConciliar,
    PagoCandidato,
    PreconciliacionError,
    ReglasCuentaConciliacion,
    calcular_puntaje,
    contactos_por_rif_nativos,
    contactos_por_rif_odoo,
    decidir_propuesta_conciliacion,
    digitos_referencia,
    generar_propuestas_conciliacion,
    pagos_candidatos_odoo,
    proponer_conciliacion,
    rifs,
    solo_lectura,
)
from apps.ventas.models import Pedido


def _xlsx(filas: list[list[Any]]) -> bytes:
    return construir_xlsx_simple([("Movimientos", filas)])


# ── Motor puro y determinístico (R1, R2, R3, solo_lectura) ───────────────────


class TestMotorPuroPreconciliacion:
    def test_rifs_y_digitos_referencia(self) -> None:
        assert rifs(None) == frozenset()
        assert rifs("") == frozenset()
        assert rifs("TRF J-050783614-2 PAGO") == frozenset({"J507836142"})
        assert rifs("J507836142 y V-0012345678") == frozenset({"J507836142", "V12345678"})
        assert rifs("B-12345678-9") == frozenset({"B123456789"})
        assert digitos_referencia("0000123456") == "123456"
        assert digitos_referencia("REF-009876") == "9876"
        assert digitos_referencia(None) == ""

    def test_puntaje_fecha_referencia_y_rif(self) -> None:
        pago = PagoCandidato(
            fuente="OMNI",
            pago_id="p1",
            nombre="Cobro 001",
            fecha=date(2026, 9, 10),
            monto=D("250.00"),
            entrante=True,
            memo="Transferencia ref 99887766 cliente",
            socio="Distribuidora Sol",
            partner_rifs=frozenset({"J507836142"}),
        )
        # Mismo día (+3) + últimos dígitos en memo (+3) + RIF socio (+3) = 9
        pts = calcular_puntaje(
            date(2026, 9, 10),
            "0099887766",
            frozenset({"J507836142"}),
            pago,
        )
        assert pts == 9

        # A 1 día sin ref ni RIF = 2; a 3 días = 1
        assert calcular_puntaje(date(2026, 9, 11), "11", frozenset(), pago) == 2
        assert calcular_puntaje(date(2026, 9, 13), "", frozenset(), pago) == 1

    def test_reglas_r1_r2_r3_empate_y_consumo_unico(self) -> None:
        reglas = ReglasCuentaConciliacion(
            cuenta_comisiones_codigo="6.2.1.01 Comisiones Bancarias",
            cuenta_igtf_codigo="6.2.1.02 IGTF",
            cuenta_transito_codigo="1.1.1.99 Pagos en Tránsito",
            ventana_dias=3,
            rifs_propios_empresa=frozenset({"J111111111"}),
        )
        movs = [
            # R1 comisión
            MovimientoParaConciliar(
                movimiento_id="m_com",
                huella="h_com",
                fecha=date(2026, 9, 1),
                orden=1,
                es_credito=False,
                monto=D("12.50"),
                categoria="comision_bancaria",
                regla_clasificacion="comision_mantenimiento",
            ),
            # R1 IGTF
            MovimientoParaConciliar(
                movimiento_id="m_igtf",
                huella="h_igtf",
                fecha=date(2026, 9, 1),
                orden=2,
                es_credito=False,
                monto=D("5.00"),
                categoria="impuesto_igtf",
                regla_clasificacion="igtf_2pct",
            ),
            # R2 cobro que gana el único pago de 100.00 (orden 3)
            MovimientoParaConciliar(
                movimiento_id="m_cobro_1",
                huella="h_cob1",
                fecha=date(2026, 9, 2),
                orden=3,
                es_credito=True,
                monto=D("100.00"),
                referencia="00554433",
                descripcion="TRF J-50783614-2 J-11111111-1",
                categoria="cobro_candidato",
            ),
            # Segundo movimiento de 100.00 el mismo día (orden 4): el pago ya fue consumido -> SIN_PROPUESTA
            MovimientoParaConciliar(
                movimiento_id="m_cobro_2",
                huella="h_cob2",
                fecha=date(2026, 9, 2),
                orden=4,
                es_credito=True,
                monto=D("100.00"),
                referencia="00999999",
                descripcion="OTRO COBRO",
                categoria="cobro_candidato",
            ),
            # R2 empate exacto entre dos pagos de 75.00 -> AMBIGUO (y ninguno se consume)
            MovimientoParaConciliar(
                movimiento_id="m_empate",
                huella="h_emp",
                fecha=date(2026, 9, 3),
                orden=5,
                es_credito=True,
                monto=D("75.00"),
                referencia="12",
                descripcion="DEPOSITO SIN DATO",
                categoria="cobro_candidato",
            ),
            # R3 compra con tarjeta sin pago -> cuenta tránsito
            MovimientoParaConciliar(
                movimiento_id="m_tdc",
                huella="h_tdc",
                fecha=date(2026, 9, 4),
                orden=6,
                es_credito=False,
                monto=D("42.00"),
                categoria="compra_tarjeta",
            ),
        ]
        pagos = [
            PagoCandidato(
                fuente="OMNI",
                pago_id="p_100",
                nombre="INGRESO PEDIDO (554433)",
                fecha=date(2026, 9, 2),
                monto=D("100.00"),
                entrante=True,
                memo="Ref 554433",
                socio="Cliente Alfa",
                partner_rifs=frozenset({"J507836142"}),
            ),
            # Candidato con RIF propio de la empresa no debe sumar +3 por RIF propio
            PagoCandidato(
                fuente="ODOO",
                pago_id="901",
                nombre="BNK1/2026/001",
                fecha=date(2026, 9, 3),
                monto=D("75.00"),
                entrante=True,
                ya_conciliado=True,
            ),
            PagoCandidato(
                fuente="ODOO",
                pago_id="902",
                nombre="BNK1/2026/002",
                fecha=date(2026, 9, 3),
                monto=D("75.00"),
                entrante=True,
            ),
        ]

        res = {p.movimiento_id: p for p in proponer_conciliacion(movs, pagos, reglas)}
        assert res["m_com"].tipo == TIPO_CUENTA and res["m_com"].regla == "R1"
        assert res["m_com"].cuenta_codigo == "6.2.1.01 Comisiones Bancarias"
        assert res["m_igtf"].tipo == TIPO_CUENTA and res["m_igtf"].regla == "R1"
        assert res["m_cobro_1"].tipo == TIPO_PAGO and res["m_cobro_1"].pago_id == "p_100"
        assert res["m_cobro_1"].puntaje == 9
        assert res["m_cobro_2"].tipo == TIPO_SIN_PROPUESTA
        assert res["m_empate"].tipo == TIPO_AMBIGUO and len(res["m_empate"].candidatos) == 2
        assert res["m_tdc"].tipo == TIPO_CUENTA and res["m_tdc"].regla == "R3"

    def test_solo_lectura_odoo_bloquea_escrituras_y_lee_pagos_y_contactos(self) -> None:
        llamadas: list[tuple[str, str]] = []

        def fake_execute(model: str, method: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
            llamadas.append((model, method))
            if model == "account.payment" and method == "fields_get":
                return {"ref": {"type": "char"}, "is_matched": {"type": "boolean"}}
            if model == "account.payment" and method == "search_read":
                return [
                    {
                        "id": 501,
                        "name": "BNK/2026/501",
                        "date": "2026-09-05",
                        "amount": 320.5,
                        "payment_type": "inbound",
                        "ref": "REF-778899",
                        "partner_id": [10, "Comercial Sur C.A."],
                        "is_matched": True,
                    },
                    {
                        "id": 502,
                        "name": "BNK/2026/502",
                        "date": "2026-09-06",
                        "amount": 80.0,
                        "payment_type": "outbound",
                        "ref": "",
                        "partner_id": False,
                        "is_matched": False,
                    },
                ]
            if model == "res.partner" and method == "read":
                return [{"id": 10, "vat": "J-40123456-7"}]
            if model == "res.company" and method == "search_read":
                return [{"partner_id": [1, "Empresa Propia"]}]
            if model == "res.partner" and method == "search_read":
                return [
                    {"id": 1, "display_name": "Empresa Propia", "vat": "J-11111111-1"},
                    {"id": 10, "display_name": "Comercial Sur C.A.", "vat": "J401234567"},
                    {"id": 20, "display_name": "Dup Uno", "vat": "J-99999999-0"},
                    {"id": 21, "display_name": "Dup Dos", "vat": "J999999990"},
                ]
            return []

        guard = solo_lectura(fake_execute)
        with pytest.raises(PermissionError, match="no es de lectura"):
            guard("account.payment", "write", [[501], {"state": "draft"}])
        with pytest.raises(PermissionError, match="no es de lectura"):
            guard("account.move", "create", [{}])
        with pytest.raises(PermissionError, match="no es de lectura"):
            guard("account.payment", "unlink", [[501]])

        cands = pagos_candidatos_odoo(
            fake_execute,
            journal_id=7,
            desde=date(2026, 9, 5),
            hasta=date(2026, 9, 6),
            excluir_ids=frozenset({"502"}),
            rifs_propios=frozenset({"J111111111"}),
        )
        assert len(cands) == 1
        assert cands[0].pago_id == "501"
        assert cands[0].memo == "REF-778899"
        assert cands[0].partner_rifs == frozenset({"J401234567"})
        assert cands[0].ya_conciliado is True

        contactos = contactos_por_rif_odoo(
            fake_execute,
            ["J401234567", "J111111111", "J999999990"],
            rifs_propios=frozenset({"J111111111"}),
        )
        assert contactos == {"J401234567": "Comercial Sur C.A."}
        assert contactos_por_rif_odoo(fake_execute, []) == {}


# ── Fixtures PostgreSQL, API y Multi-Tenant ──────────────────────────────────


@pytest.fixture
def moneda_ves(db) -> Moneda:
    moneda, _ = Moneda.objects.get_or_create(
        codigo_iso="VES",
        defaults={
            "nombre": "Bolívar",
            "simbolo": "Bs",
            "tipo_moneda": "fiat",
            "es_generica": True,
        },
    )
    return moneda


@pytest.fixture
def metodo_transferencia_a(db, empresa_a) -> MetodoPago:
    return MetodoPago.objects.create(
        empresa=empresa_a,
        nombre_metodo="Transferencia Bancaria",
        tipo_metodo="ELECTRONICO",
        activo=True,
    )


@pytest.fixture
def cuenta_ves_a(db, empresa_a, moneda_ves) -> CuentaBancariaEmpresa:
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_a,
        nombre_banco="Mercantil",
        numero_cuenta="0105-0011-22-1234567806",
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda_ves,
    )


@pytest.fixture
def cuenta_ves_b(db, empresa_b, moneda_ves) -> CuentaBancariaEmpresa:
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_b,
        nombre_banco="Banesco",
        numero_cuenta="0134-0099-88-9999996747",
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda_ves,
    )


@pytest.fixture
def plan_comisiones_a(db, empresa_a) -> PlanCuentas:
    return PlanCuentas.objects.create(
        id_empresa=empresa_a,
        codigo_cuenta="6.2.1.01",
        nombre_cuenta="Gastos y Comisiones Bancarias",
        tipo_cuenta="GASTO",
        naturaleza="DEUDORA",
        nivel=4,
        activo=True,
    )


@pytest.fixture
def plan_transito_a(db, empresa_a) -> PlanCuentas:
    return PlanCuentas.objects.create(
        id_empresa=empresa_a,
        codigo_cuenta="1.1.1.09",
        nombre_cuenta="Pagos en Tránsito Tarjetas y Nómina",
        tipo_cuenta="ACTIVO",
        naturaleza="DEUDORA",
        nivel=4,
        activo=True,
    )


@pytest.fixture
def plan_comisiones_b(db, empresa_b) -> PlanCuentas:
    return PlanCuentas.objects.create(
        id_empresa=empresa_b,
        codigo_cuenta="6.9.9.99",
        nombre_cuenta="Comisiones Otra Empresa",
        tipo_cuenta="GASTO",
        naturaleza="DEUDORA",
        nivel=4,
        activo=True,
    )


@pytest.fixture
def api_a(user_a) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def api_b(user_b) -> APIClient:
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


# ── Servicio transaccional, decisiones humanas y bloqueos contables ──────────


@pytest.mark.django_db
class TestServicioPreconciliacionYColaHumana:
    def test_flujo_completo_nativo_decisiones_reejecucion_y_bloqueos(
        self,
        empresa_a,
        cuenta_ves_a,
        moneda_ves,
        metodo_transferencia_a,
        plan_comisiones_a,
        plan_transito_a,
        user_a,
    ) -> None:
        empresa_a.identificador_fiscal = "J-11111111-1"
        empresa_a.save(update_fields=["identificador_fiscal"])

        ConfiguracionConciliacionCuenta.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_ves_a,
            id_cuenta_comisiones=plan_comisiones_a,
            codigo_cuenta_igtf="6.2.1.05 IGTF Bancario",
            id_cuenta_transito_pendientes=plan_transito_a,
            ventana_dias=3,
        )

        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Ferretería Norte C.A.",
            rif="J-405556667",
        )
        pedido = Pedido.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_pedido="PED-9001",
            fecha_pedido=date(2026, 9, 10),
            estado="APROBADO",
        )
        pago_ingreso = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="PEDIDO",
            id_documento=pedido.id_pedido,
            id_pedido=pedido,
            fecha_pago=datetime(2026, 9, 10, 14, 0, tzinfo=dt_tz.utc),
            monto=D("1500.00"),
            id_moneda=moneda_ves,
            id_metodo_pago=metodo_transferencia_a,
            id_cuenta_bancaria=cuenta_ves_a,
            referencia="000887766",
            observaciones="Cobro pedido PED-9001",
        )

        proveedor = Proveedor.objects.create(
            id_empresa=empresa_a,
            razon_social="Transporte Andino C.A.",
            rif="J-301112223",
        )
        cxp = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor,
            monto_total=D("400.00"),
            monto_pendiente=D("0.00"),
            fecha_emision=date(2026, 9, 9),
            fecha_vencimiento=date(2026, 9, 19),
            estado="PAGADA",
        )
        pago_egreso = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="EGRESO",
            tipo_documento="CXP",
            id_documento=cxp.id_cxp,
            id_cxp=cxp,
            fecha_pago=datetime(2026, 9, 11, 15, 0, tzinfo=dt_tz.utc),
            monto=D("400.00"),
            id_moneda=moneda_ves,
            id_metodo_pago=metodo_transferencia_a,
            id_cuenta_bancaria=cuenta_ves_a,
            referencia="332211",
        )

        corte_bytes = _xlsx(
            [
                ["Cuenta: 0105-0011-22-1234567806"],
                ["Saldo Inicial: 2.000,00"],
                ["Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"],
                ["10/09/2026", "99887766", "TRF CR J-40555666-7 FERRETERIA", "", "1.500,00", "3.500,00"],
                ["10/09/2026", "1001", "COM MANTENIMIENTO DE CUENTA", "25,00", "", "3.475,00"],
                ["11/09/2026", "00332211", "PAGO PROVEEDOR J-30111222-3", "400,00", "", "3.075,00"],
                ["12/09/2026", "7777", "COMPRA TDD POS COMERCIO", "75,00", "", "3.000,00"],
                ["12/09/2026", "8888", "ABONO NO IDENTIFICADO", "", "120,00", "3.120,00"],
            ]
        )
        res_imp = importar_extracto_bancario(
            empresa=empresa_a,
            cuenta_bancaria=cuenta_ves_a,
            contenido=corte_bytes,
            nombre_archivo="mercantil_sep.xlsx",
            formato_banco="MERCANTIL",
            usuario=user_a,
        )
        assert res_imp.cuadra is True and res_imp.lineas_nuevas == 5

        res_gen = generar_propuestas_conciliacion(
            empresa=empresa_a,
            cuenta_bancaria=cuenta_ves_a,
        )
        assert res_gen == {"nuevas": 5, "actualizadas": 0, "ya_decididas": 0, "total_evaluados": 5}

        props = {
            p.id_movimiento_bancario.referencia: p
            for p in PropuestaConciliacionBancaria.objects.filter(
                id_empresa=empresa_a, activo=True
            ).select_related("id_movimiento_bancario")
        }
        assert props["99887766"].tipo == TIPO_PAGO
        assert props["99887766"].id_pago_nativo_id == pago_ingreso.id_pago
        assert props["99887766"].pago_socio == "Ferretería Norte C.A."
        assert props["1001"].tipo == TIPO_CUENTA and props["1001"].regla == "R1"
        assert props["1001"].id_cuenta_contable_id == plan_comisiones_a.pk
        assert props["00332211"].tipo == TIPO_PAGO
        assert props["00332211"].id_pago_nativo_id == pago_egreso.id_pago
        assert props["7777"].tipo == TIPO_CUENTA and props["7777"].regla == "R3"
        assert props["8888"].tipo == TIPO_SIN_PROPUESTA

        # 1. Aprobar cobro nativo -> marca MovimientoBancario CONCILIADO + id_pago_conciliado
        aprobada = decidir_propuesta_conciliacion(
            empresa=empresa_a,
            propuesta_id=str(props["99887766"].pk),
            accion="APROBAR",
            usuario=user_a,
            comentario="Verificado en estado de cuenta",
        )
        assert aprobada.estado == "APROBADA"
        mov_cobro = MovimientoBancario.objects.get(pk=props["99887766"].id_movimiento_bancario_id)
        assert mov_cobro.estado == "CONCILIADO"
        assert mov_cobro.id_pago_conciliado_id == pago_ingreso.pk

        # No se puede aprobar SIN_PROPUESTA directamente -> debe corregirse
        with pytest.raises(DecisionPreconciliacionInvalida, match="CORREGIR"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(props["8888"].pk),
                accion="APROBAR",
                usuario=user_a,
            )

        # No se puede corregir asignando un pago ya conciliado con otro movimiento
        with pytest.raises(DecisionPreconciliacionInvalida, match="ya está conciliado"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(props["8888"].pk),
                accion="CORREGIR",
                usuario=user_a,
                pago_nativo_id=str(pago_ingreso.pk),
            )

        # 2. Corregir SIN_PROPUESTA con cuenta contable explícita
        corregida = decidir_propuesta_conciliacion(
            empresa=empresa_a,
            propuesta_id=str(props["8888"].pk),
            accion="CORREGIR",
            usuario=user_a,
            cuenta_contable_id=str(plan_transito_a.pk),
            comentario="Abono por identificar cliente",
        )
        assert corregida.estado == "CORREGIDA"
        assert corregida.tipo == TIPO_CUENTA
        assert "1.1.1.09" in corregida.cuenta_contable_codigo

        # 3. Rechazar exige comentario
        with pytest.raises(DecisionPreconciliacionInvalida, match="comentario"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(props["7777"].pk),
                accion="RECHAZAR",
                usuario=user_a,
            )
        rechazada = decidir_propuesta_conciliacion(
            empresa=empresa_a,
            propuesta_id=str(props["7777"].pk),
            accion="RECHAZAR",
            usuario=user_a,
            comentario="Cargo en disputa bancaria",
        )
        assert rechazada.estado == "RECHAZADA"

        # 4. Re-ejecutar motor NO sobrescribe APROBADA, CORREGIDA ni RECHAZADA
        res_regen = generar_propuestas_conciliacion(
            empresa=empresa_a,
            cuenta_bancaria=cuenta_ves_a,
        )
        assert res_regen["nuevas"] == 0
        assert res_regen["actualizadas"] == 2
        assert res_regen["ya_decididas"] == 3

        # 5. Extracto con decisiones humanas o movimientos conciliados NO puede desactivarse
        with pytest.raises(ExtractoBancarioError):
            desactivar_extracto_bancario(res_imp.archivo)

        # 6. Reabrir vuelve a PENDIENTE y libera el MovimientoBancario, salvo si el período cerró
        sesion = ConciliacionBancaria.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_ves_a,
            periodo_inicio=date(2026, 9, 1),
            periodo_fin=date(2026, 9, 30),
            saldo_banco=D("3120.00"),
            saldo_libro=D("3120.00"),
            estado="CERRADA",
        )
        with pytest.raises(DecisionPreconciliacionInvalida, match="cerrado"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(aprobada.pk),
                accion="REABRIR",
                usuario=user_a,
                comentario="Intento en período cerrado",
            )
        sesion.estado = "ABIERTA"
        sesion.save(update_fields=["estado"])

        reabierta = decidir_propuesta_conciliacion(
            empresa=empresa_a,
            propuesta_id=str(aprobada.pk),
            accion="REABRIR",
            usuario=user_a,
            comentario="Revisión solicitada por auditoría",
        )
        assert reabierta.estado == "PENDIENTE"
        mov_cobro.refresh_from_db()
        assert mov_cobro.estado == "PENDIENTE" and mov_cobro.id_pago_conciliado is None

        # Bitácora inmutable contiene las 4 decisiones registradas
        assert DecisionPreconciliacionBancaria.objects.filter(id_empresa=empresa_a).count() == 4

    def test_integracion_conector_odoo_y_contactos_por_rif_nativos(
        self,
        monkeypatch: pytest.MonkeyPatch,
        empresa_a,
        cuenta_ves_a,
        moneda_ves,
        metodo_transferencia_a,
    ) -> None:
        empresa_a.identificador_fiscal = "J-11111111-1"
        empresa_a.save(update_fields=["identificador_fiscal"])

        # Contactos nativos: único vs ambiguo vs propio
        Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cliente Único C.A.", rif="J-223344556"
        )
        Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Duplicado Uno", rif="J-777777778"
        )
        Proveedor.objects.create(
            id_empresa=empresa_a, razon_social="Duplicado Dos", rif="J-777777778"
        )
        Contacto.objects.create(
            id_empresa=empresa_a,
            tipo_persona="NATURAL",
            nombre="María",
            apellido="Pérez",
            cedula="V-14555666",
            es_cliente=True,
        )
        res_rifs = contactos_por_rif_nativos(
            empresa_a, ["J223344556", "J777777778", "V14555666", "J111111111"]
        )
        assert res_rifs == {
            "J223344556": "Cliente Único C.A.",
            "V14555666": "María Pérez",
        }

        # Gasto con proveedor para cubrir extracción de RIF en gastos
        prov_gasto = Proveedor.objects.create(
            id_empresa=empresa_a, razon_social="Servicios Luz C.A.", rif="J-888888889"
        )
        cat_gasto = CategoriaGasto.objects.create(
            id_empresa=empresa_a, nombre_categoria="Servicios"
        )
        gasto = Gasto.objects.create(
            id_empresa=empresa_a,
            fecha_gasto=date(2026, 9, 15),
            descripcion="Factura eléctrica",
            monto=D("90.00"),
            id_moneda=moneda_ves,
            id_categoria_gasto=cat_gasto,
            id_proveedor=prov_gasto,
        )
        Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="EGRESO",
            tipo_documento="GASTO",
            id_documento=gasto.id_gasto,
            id_gasto=gasto,
            fecha_pago=datetime(2026, 9, 15, 12, 0, tzinfo=dt_tz.utc),
            monto=D("90.00"),
            id_moneda=moneda_ves,
            id_metodo_pago=metodo_transferencia_a,
            banco_destino=cuenta_ves_a,
            referencia="556677",
        )

        prov_odoo, _ = ConectorProveedor.objects.get_or_create(
            codigo="odoo", defaults={"nombre": "Odoo"}
        )
        instancia_odoo = ConectorInstancia.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov_odoo,
            nombre="Odoo Principal",
            configuracion={
                "host": "https://odoo.ejemplo.test",
                "db": "prod",
                "user": "api@ejemplo.test",
                "api_key": "dummy-test-key",
            },
            estado="activo",
            activo=True,
        )
        ConfiguracionConciliacionCuenta.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_ves_a,
            id_conector_odoo=instancia_odoo,
            odoo_journal_id=14,
            incluir_pagos_nativos=True,
            incluir_pagos_odoo=True,
        )

        MovimientoBancario.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_ves_a,
            fecha_mov=date(2026, 9, 15),
            descripcion="PAGO GASTO J-88888888-9",
            tipo="DEBITO",
            monto=D("90.00"),
            referencia="00556677",
            origen="EXTRACTO",
        )
        mov_odoo = MovimientoBancario.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_ves_a,
            fecha_mov=date(2026, 9, 16),
            descripcion="COBRO ODOO J-22334455-6",
            tipo="CREDITO",
            monto=D("740.00"),
            referencia="00443322",
            origen="EXTRACTO",
        )

        fake_client = MagicMock()

        def fake_call(model: str, method: str, domain: list | None = None, kwargs: dict | None = None):
            if model == "account.payment" and method == "fields_get":
                return {"memo": {"type": "char"}, "is_matched": {"type": "boolean"}}
            if model == "account.payment" and method == "search_read":
                return [
                    {
                        "id": 8801,
                        "name": "BNK14/2026/8801",
                        "date": "2026-09-16",
                        "amount": 740.0,
                        "payment_type": "inbound",
                        "memo": "Ref 443322",
                        "partner_id": [55, "Cliente Único C.A."],
                        "is_matched": False,
                    }
                ]
            if model == "res.partner" and method == "read":
                return [{"id": 55, "vat": "J223344556"}]
            return []

        fake_client.call.side_effect = fake_call
        monkeypatch.setattr(
            "apps.integration_hub.connectors.odoo.connector.OdooConnector._get_client",
            lambda _self: fake_client,
        )

        res = generar_propuestas_conciliacion(empresa=empresa_a, cuenta_bancaria=cuenta_ves_a)
        assert res["nuevas"] == 2
        prop_odoo = PropuestaConciliacionBancaria.objects.get(id_movimiento_bancario=mov_odoo)
        assert prop_odoo.fuente_pago == "ODOO"
        assert prop_odoo.pago_externo_id == "8801"
        assert prop_odoo.pago_nombre == "BNK14/2026/8801"

        # Si Odoo falla al autenticar, devuelve PreconciliacionError limpio sin exponer secretos
        def fail_client(_self):
            raise OdooAuthError("Fallo simulado")

        monkeypatch.setattr(
            "apps.integration_hub.connectors.odoo.connector.OdooConnector._get_client",
            fail_client,
        )
        with pytest.raises(PreconciliacionError, match="No fue posible consultar"):
            generar_propuestas_conciliacion(empresa=empresa_a, cuenta_bancaria=cuenta_ves_a)

    def test_corregir_pagos_nativos_y_externos_y_validaciones_borde(
        self,
        empresa_a,
        empresa_b,
        cuenta_ves_a,
        cuenta_ves_b,
        moneda_ves,
        metodo_transferencia_a,
        plan_comisiones_b,
        user_a,
    ) -> None:
        empresa_a.identificador_fiscal = "J-11111111-1"
        empresa_a.save(update_fields=["identificador_fiscal"])

        # Contactos nativos cuando sólo se busca el RIF propio -> vacío
        assert contactos_por_rif_nativos(empresa_a, ["J111111111"]) == {}

        # Validaciones de entrada en generar_propuestas_conciliacion
        with pytest.raises(PreconciliacionError, match="no pertenece"):
            generar_propuestas_conciliacion(empresa=empresa_a, cuenta_bancaria=cuenta_ves_b)
        with pytest.raises(PreconciliacionError, match="posterior"):
            generar_propuestas_conciliacion(
                empresa=empresa_a,
                cuenta_bancaria=cuenta_ves_a,
                desde=date(2026, 9, 20),
                hasta=date(2026, 9, 10),
            )
        with pytest.raises(PreconciliacionError, match="incluir_odoo"):
            generar_propuestas_conciliacion(
                empresa=empresa_a,
                cuenta_bancaria=cuenta_ves_a,
                incluir_odoo=True,
            )
        # Cuenta sin movimientos devuelve ceros
        assert generar_propuestas_conciliacion(
            empresa=empresa_a, cuenta_bancaria=cuenta_ves_a
        ) == {"nuevas": 0, "actualizadas": 0, "ya_decididas": 0, "total_evaluados": 0}

        # Moneda distinta en pago nativo es ignorada por cargar_pagos_nativos_candidatos
        moneda_usd, _ = Moneda.objects.get_or_create(
            codigo_iso="USD",
            defaults={"nombre": "Dólar", "simbolo": "$", "tipo_moneda": "fiat", "es_generica": True},
        )
        cliente = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cliente Manual C.A.", rif="J-501112223"
        )
        pedido = Pedido.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_pedido="PED-9901",
            fecha_pedido=date(2026, 11, 1),
            estado="APROBADO",
        )
        Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="PEDIDO",
            id_documento=pedido.id_pedido,
            id_pedido=pedido,
            fecha_pago=datetime(2026, 11, 1, 10, 0, tzinfo=dt_tz.utc),
            monto=D("500.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_transferencia_a,
            id_cuenta_bancaria=cuenta_ves_a,
            referencia="USD-IGNORE",
        )
        pago_manual = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="PEDIDO",
            id_documento=pedido.id_pedido,
            id_pedido=pedido,
            fecha_pago=datetime(2026, 10, 1, 10, 0, tzinfo=dt_tz.utc),
            monto=D("500.00"),
            id_moneda=moneda_ves,
            id_metodo_pago=metodo_transferencia_a,
            id_cuenta_bancaria=cuenta_ves_a,
            referencia="MANUAL-500",
        )

        # Importar extracto con 2 movimientos pendientes sin match automático
        corte = _xlsx(
            [
                ["Cuenta: 0105-0011-22-1234567806"],
                ["Saldo Inicial: 1.000,00"],
                ["Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"],
                ["01/11/2026", "9001", "ABONO MANUAL NATIVO", "", "500,00", "1.500,00"],
                ["02/11/2026", "9002", "ABONO MANUAL ODOO", "", "250,00", "1.750,00"],
            ]
        )
        imp = importar_extracto_bancario(
            empresa=empresa_a,
            cuenta_bancaria=cuenta_ves_a,
            contenido=corte,
            nombre_archivo="noviembre.xlsx",
            formato_banco="MERCANTIL",
            usuario=user_a,
        )
        generar_propuestas_conciliacion(empresa=empresa_a, cuenta_bancaria=cuenta_ves_a)
        p1, p2 = list(
            PropuestaConciliacionBancaria.objects.filter(
                id_empresa=empresa_a, activo=True
            ).order_by("id_movimiento_bancario__fecha_mov")
        )
        p2.candidatos_json = [
            {"fuente": "ODOO", "id": "7701", "nombre": "BNK/2026/7701", "socio": "Socio Odoo"}
        ]
        p2.save(update_fields=["candidatos_json"])

        # Validaciones de borde en decidir_propuesta_conciliacion
        with pytest.raises(DecisionPreconciliacionInvalida, match="Acción desconocida"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a, propuesta_id=str(p1.pk), accion="SALTAR", usuario=user_a
            )
        with pytest.raises(DecisionPreconciliacionInvalida, match="no ambos"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(p1.pk),
                accion="CORREGIR",
                usuario=user_a,
                pago_nativo_id=str(pago_manual.pk),
                pago_externo_id="7701",
            )
        with pytest.raises(DecisionPreconciliacionInvalida, match="exclusivamente"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a, propuesta_id=str(p1.pk), accion="CORREGIR", usuario=user_a
            )
        with pytest.raises(PreconciliacionError, match="no encontrada"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(uuid7()),
                accion="RECHAZAR",
                usuario=user_a,
                comentario="No existe",
            )
        with pytest.raises(DecisionPreconciliacionInvalida, match="ya se encuentra en estado PENDIENTE"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(p1.pk),
                accion="REABRIR",
                usuario=user_a,
                comentario="Ya pendiente",
            )
        with pytest.raises(DecisionPreconciliacionInvalida, match="pago nativo indicado no existe"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(p1.pk),
                accion="CORREGIR",
                usuario=user_a,
                pago_nativo_id=str(uuid7()),
            )
        with pytest.raises(DecisionPreconciliacionInvalida, match="pertenece a otra empresa"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(p1.pk),
                accion="CORREGIR",
                usuario=user_a,
                cuenta_contable_id=str(plan_comisiones_b.pk),
            )

        # Rechazar p1 -> movimiento sigue PENDIENTE pero desactivar_extracto_bancario bloquea por decisión humana
        decidir_propuesta_conciliacion(
            empresa=empresa_a,
            propuesta_id=str(p1.pk),
            accion="RECHAZAR",
            usuario=user_a,
            comentario="Revisión temporal",
        )
        with pytest.raises(ExtractoBancarioError, match="decisiones humanas"):
            desactivar_extracto_bancario(imp.archivo)
        with pytest.raises(DecisionPreconciliacionInvalida, match="ya fue decidida"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(p1.pk),
                accion="RECHAZAR",
                usuario=user_a,
                comentario="Doble decisión",
            )
        decidir_propuesta_conciliacion(
            empresa=empresa_a,
            propuesta_id=str(p1.pk),
            accion="REABRIR",
            usuario=user_a,
            comentario="Reabierto para corregir",
        )

        # CORREGIR con pago_nativo_id válido y CORREGIR con pago_externo_id (ODOO) + choque de unicidad
        c_nativo = decidir_propuesta_conciliacion(
            empresa=empresa_a,
            propuesta_id=str(p1.pk),
            accion="CORREGIR",
            usuario=user_a,
            pago_nativo_id=str(pago_manual.pk),
            comentario="Asignado manualmente a cobro de octubre",
        )
        assert c_nativo.estado == "CORREGIDA"
        assert c_nativo.fuente_pago == "OMNI"
        assert c_nativo.id_pago_nativo_id == pago_manual.pk
        assert c_nativo.pago_socio == "Cliente Manual C.A."

        c_odoo = decidir_propuesta_conciliacion(
            empresa=empresa_a,
            propuesta_id=str(p2.pk),
            accion="CORREGIR",
            usuario=user_a,
            pago_externo_id="7701",
            comentario="Asignado manualmente a pago Odoo",
        )
        assert c_odoo.estado == "CORREGIDA"
        assert c_odoo.fuente_pago == "ODOO"
        assert c_odoo.pago_nombre == "BNK/2026/7701"
        assert c_odoo.pago_socio == "Socio Odoo"

        # Intentar asignar el mismo pago_externo_id 7701 a p1 (tras reabrirlo) dispara UniqueConstraint -> DecisionPreconciliacionInvalida
        decidir_propuesta_conciliacion(
            empresa=empresa_a,
            propuesta_id=str(p1.pk),
            accion="REABRIR",
            usuario=user_a,
            comentario="Reabrir p1",
        )
        with pytest.raises(DecisionPreconciliacionInvalida, match="ya se encuentra aprobado"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(p1.pk),
                accion="CORREGIR",
                usuario=user_a,
                pago_externo_id="7701",
            )

        # Reabrir p2 -> todas las propuestas vuelven a PENDIENTE -> desactivar_extracto_bancario desactiva propuestas limpiamente
        decidir_propuesta_conciliacion(
            empresa=empresa_a,
            propuesta_id=str(p2.pk),
            accion="REABRIR",
            usuario=user_a,
            comentario="Reabrir p2 para anular extracto",
        )
        assert desactivar_extracto_bancario(imp.archivo) == 2
        assert not PropuestaConciliacionBancaria.objects.filter(
            id_empresa=empresa_a, activo=True
        ).exists()

        # Configuración con conector inactivo o sin journal_id falla limpiamente
        prov_odoo, _ = ConectorProveedor.objects.get_or_create(
            codigo="odoo", defaults={"nombre": "Odoo"}
        )
        con_inactivo = ConectorInstancia.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov_odoo,
            nombre="Odoo Inactivo",
            configuracion={"host": "https://x.test", "db": "x", "user": "u", "api_key": "k"},
            estado="inactivo",
            activo=False,
        )
        cfg_odoo = ConfiguracionConciliacionCuenta.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_ves_a,
            id_conector_odoo=con_inactivo,
            odoo_journal_id=None,
            incluir_pagos_odoo=True,
        )
        MovimientoBancario.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_ves_a,
            fecha_mov=date(2026, 11, 5),
            descripcion="MOV PRUEBA CONECTOR",
            tipo="CREDITO",
            monto=D("100.00"),
            origen="EXTRACTO",
        )
        with pytest.raises(PreconciliacionError, match="conector Odoo activo"):
            generar_propuestas_conciliacion(empresa=empresa_a, cuenta_bancaria=cuenta_ves_a)
        con_inactivo.activo = True
        con_inactivo.save(update_fields=["activo"])
        cfg_odoo.refresh_from_db()
        with pytest.raises(PreconciliacionError, match="odoo_journal_id"):
            generar_propuestas_conciliacion(empresa=empresa_a, cuenta_bancaria=cuenta_ves_a)


# ── API REST, Aislamiento Multi-Tenant (@pytest.mark.tenant), RLS y MCP ──────


@pytest.mark.tenant
@pytest.mark.django_db
class TestAPIPreconciliacionMultiTenantYRLS:
    URL_CFG = "/api/tesoreria/configuraciones-conciliacion/"
    URL_PROP = "/api/tesoreria/propuestas-conciliacion/"

    def test_aislamiento_cross_tenant_api_rls_y_mcp(
        self,
        empresa_a,
        empresa_b,
        cuenta_ves_a,
        cuenta_ves_b,
        plan_comisiones_a,
        plan_comisiones_b,
        user_a,
        api_a: APIClient,
        api_b: APIClient,
    ) -> None:
        # 1. Rechazar FK cross-tenant y validaciones de serializer al configurar reglas
        r_cross_cta = api_a.post(
            self.URL_CFG,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_cuenta_bancaria": str(cuenta_ves_b.id_cuenta_bancaria),
                "codigo_cuenta_comisiones": "6.1.1",
            },
            format="json",
        )
        assert r_cross_cta.status_code == 400

        r_cross_plan = api_a.post(
            self.URL_CFG,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                "id_cuenta_comisiones": str(plan_comisiones_b.pk),
            },
            format="json",
        )
        assert r_cross_plan.status_code == 400

        assert (
            api_a.post(
                self.URL_CFG,
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "id_cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                    "ventana_dias": 45,
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            api_a.post(
                self.URL_CFG,
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "id_cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                    "incluir_pagos_odoo": True,
                },
                format="json",
            ).status_code
            == 400
        )
        prov_odoo, _ = ConectorProveedor.objects.get_or_create(
            codigo="odoo", defaults={"nombre": "Odoo"}
        )
        conector_b = ConectorInstancia.objects.create(
            id_empresa=empresa_b,
            id_proveedor=prov_odoo,
            nombre="Odoo Empresa B",
            configuracion={"host": "https://b.test", "db": "b", "user": "u", "api_key": "k"},
            estado="activo",
            activo=True,
        )
        assert (
            api_a.post(
                self.URL_CFG,
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "id_cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                    "id_conector_odoo": str(conector_b.pk),
                },
                format="json",
            ).status_code
            == 400
        )
        # Usuario A no puede crear configuración indicando empresa_b (TenantFKScopeMixin rechaza con 400/403)
        assert (
            api_a.post(
                self.URL_CFG,
                {
                    "id_empresa": str(empresa_b.id_empresa),
                    "id_cuenta_bancaria": str(cuenta_ves_b.id_cuenta_bancaria),
                },
                format="json",
            ).status_code
            in (400, 403)
        )

        # 2. Crear configuración válida en empresa A y verificar unicidad activa + PATCH + soft delete
        r_cfg = api_a.post(
            self.URL_CFG,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                "id_cuenta_comisiones": str(plan_comisiones_a.pk),
                "codigo_cuenta_transito_pendientes": "1.1.1.08 Pendientes POS",
                "ventana_dias": 3,
            },
            format="json",
        )
        assert r_cfg.status_code == 201, r_cfg.content
        cfg_id = r_cfg.json()["id"]

        # Filtros ?empresa=&cuenta= y PATCH válido + bloqueo de cambio de empresa
        assert (
            api_a.get(
                self.URL_CFG,
                {
                    "empresa": str(empresa_a.id_empresa),
                    "cuenta": str(cuenta_ves_a.id_cuenta_bancaria),
                },
            ).json()["count"]
            == 1
        )
        assert (
            api_a.patch(
                f"{self.URL_CFG}{cfg_id}/",
                {"ventana_dias": 5},
                format="json",
            ).status_code
            == 200
        )
        assert (
            api_a.patch(
                f"{self.URL_CFG}{cfg_id}/",
                {"id_empresa": str(empresa_b.id_empresa)},
                format="json",
            ).status_code
            == 400
        )

        # Duplicado activo devuelve 400 limpio (nunca 500)
        r_dup = api_a.post(
            self.URL_CFG,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
            },
            format="json",
        )
        assert r_dup.status_code == 400

        # Empresa B no ve ni puede editar/borrar la configuración de A
        assert api_b.get(self.URL_CFG).json()["count"] == 0
        assert api_b.get(f"{self.URL_CFG}{cfg_id}/").status_code == 404
        assert api_b.delete(f"{self.URL_CFG}{cfg_id}/").status_code == 404

        # 3. Generar propuestas vía API y decidir en cola de revisión
        mov_com = MovimientoBancario.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_ves_a,
            fecha_mov=date(2026, 10, 1),
            descripcion="COMISION BANCARIA MENSUAL",
            tipo="DEBITO",
            monto=D("18.00"),
            referencia="77001",
            categoria_clasificacion="comision_bancaria",
            regla_clasificacion="comision_mensual",
            origen="EXTRACTO",
        )
        mov_pend = MovimientoBancario.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_ves_a,
            fecha_mov=date(2026, 10, 2),
            descripcion="LIQUIDACION POS TDD",
            tipo="CREDITO",
            monto=D("350.00"),
            referencia="77002",
            categoria_clasificacion="operacion_pos",
            regla_clasificacion="pos",
            origen="EXTRACTO",
        )

        # Empresa B no puede generar sobre cuenta de empresa A (404 sin empresa, 403 con empresa ajena)
        assert (
            api_b.post(
                f"{self.URL_PROP}generar/",
                {"cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria)},
                format="json",
            ).status_code
            == 404
        )
        assert (
            api_b.post(
                f"{self.URL_PROP}generar/",
                {
                    "empresa": str(empresa_a.id_empresa),
                    "cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                },
                format="json",
            ).status_code
            == 403
        )
        # Error de negocio en /generar/ (desde > hasta) -> 400
        assert (
            api_a.post(
                f"{self.URL_PROP}generar/",
                {
                    "empresa": str(empresa_a.id_empresa),
                    "cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                    "desde": "2026-10-10",
                    "hasta": "2026-10-01",
                },
                format="json",
            ).status_code
            == 400
        )

        r_gen = api_a.post(
            f"{self.URL_PROP}generar/",
            {
                "empresa": str(empresa_a.id_empresa),
                "cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                "desde": "2026-10-01",
                "hasta": "2026-10-05",
            },
            format="json",
        )
        assert r_gen.status_code == 200 and r_gen.json()["nuevas"] == 2

        listado_a = api_a.get(
            self.URL_PROP,
            {
                "empresa": str(empresa_a.id_empresa),
                "cuenta": str(cuenta_ves_a.id_cuenta_bancaria),
                "estado": "PENDIENTE",
                "tipo": "CUENTA",
                "regla": "R1",
                "desde": "2026-10-01",
                "hasta": "2026-10-05",
                "search": "COMISION",
            },
        ).json()
        assert listado_a["count"] == 1
        prop_com_id = listado_a["results"][0]["id"]

        # Empresa B ve 0 propuestas, 0 aprobadas y 0 bitácora, y recibe 404 al intentar decidir
        assert api_b.get(self.URL_PROP).json()["count"] == 0
        assert api_b.get(f"{self.URL_PROP}aprobadas/").json()["count"] == 0
        assert api_b.get(f"{self.URL_PROP}bitacora/").json()["count"] == 0
        assert (
            api_b.post(
                f"{self.URL_PROP}{prop_com_id}/decidir/",
                {"accion": "APROBAR"},
                format="json",
            ).status_code
            == 404
        )

        # Aprobar en empresa A y consultar /aprobadas/ + /bitacora/
        r_dec = api_a.post(
            f"{self.URL_PROP}{prop_com_id}/decidir/",
            {"accion": "APROBAR", "comentario": "Comisión estándar"},
            format="json",
        )
        assert r_dec.status_code == 200
        assert r_dec.json()["estado"] == "APROBADA"

        # Volver a decidir sin reabrir -> 400
        assert (
            api_a.post(
                f"{self.URL_PROP}{prop_com_id}/decidir/",
                {"accion": "APROBAR"},
                format="json",
            ).status_code
            == 400
        )

        aprobadas_a = api_a.get(
            f"{self.URL_PROP}aprobadas/",
            {
                "decididas_desde": date.today().isoformat(),
                "decididas_hasta": date.today().isoformat(),
            },
        ).json()
        assert aprobadas_a["count"] == 1

        bitacora_a = api_a.get(
            f"{self.URL_PROP}bitacora/",
            {
                "empresa": str(empresa_a.id_empresa),
                "propuesta": prop_com_id,
                "movimiento": str(mov_com.pk),
                "accion": "aprobar",
            },
        ).json()
        assert bitacora_a["count"] == 1
        assert bitacora_a["results"][0]["comentario"] == "Comisión estándar"

        # Si una propuesta es RECHAZADA, el movimiento tampoco puede borrarse hasta reabrirla
        prop_pend = PropuestaConciliacionBancaria.objects.get(
            id_movimiento_bancario=mov_pend, activo=True
        )
        assert (
            api_a.post(
                f"{self.URL_PROP}{prop_pend.pk}/decidir/",
                {"accion": "RECHAZAR", "comentario": "Verificar lote POS"},
                format="json",
            ).status_code
            == 200
        )
        assert (
            api_a.delete(f"/api/tesoreria/movimientos-bancarios/{mov_pend.pk}/").status_code == 400
        )
        assert (
            api_a.post(
                f"{self.URL_PROP}{prop_pend.pk}/decidir/",
                {"accion": "REABRIR", "comentario": "Listo para eliminar"},
                format="json",
            ).status_code
            == 200
        )

        # Borrar movimiento pendiente desactiva también su propuesta PENDIENTE
        r_del_mov = api_a.delete(f"/api/tesoreria/movimientos-bancarios/{mov_pend.pk}/")
        assert r_del_mov.status_code == 204
        assert not PropuestaConciliacionBancaria.objects.filter(
            id_movimiento_bancario=mov_pend, activo=True
        ).exists()

        # Movimiento ya conciliado no puede borrarse
        assert (
            api_a.delete(f"/api/tesoreria/movimientos-bancarios/{mov_com.pk}/").status_code == 400
        )

        # Parámetros inválidos devuelven 400 (nunca 500)
        assert api_a.get(self.URL_PROP, {"desde": "no-es-fecha"}).status_code == 400
        assert api_a.get(self.URL_PROP, {"cuenta": "no-es-uuid"}).status_code == 400

        # 4. Verificación directa de políticas RLS en PostgreSQL
        if not current_role_bypasses_rls():
            try:
                apply_context([empresa_b.id_empresa], bypass=False)
                assert ConfiguracionConciliacionCuenta.objects.count() == 0
                assert PropuestaConciliacionBancaria.objects.count() == 0
                assert DecisionPreconciliacionBancaria.objects.count() == 0

                apply_context([empresa_a.id_empresa], bypass=False)
                assert ConfiguracionConciliacionCuenta.objects.count() == 1
                assert PropuestaConciliacionBancaria.objects.count() >= 1
                assert DecisionPreconciliacionBancaria.objects.count() >= 1
            finally:
                apply_system_default()

        # 5. Herramientas MCP (tesoreria:read y tesoreria:write)
        tok_rw = CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="MCP Tesorería RW",
            scopes=["tesoreria:read", "tesoreria:write"],
        )
        tok_ro = CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="MCP Tesorería RO",
            scopes=["tesoreria:read"],
        )

        gen_mcp = tesoreria_generar_propuestas_conciliacion(
            str(tok_rw.token),
            str(empresa_a.id_empresa),
            str(cuenta_ves_a.id_cuenta_bancaria),
            desde="2026-10-01",
            hasta="2026-10-05",
        )
        assert gen_mcp["ya_decididas"] == 1

        lista_mcp = tesoreria_listar_propuestas_conciliacion(
            str(tok_ro.token),
            str(empresa_a.id_empresa),
            cuenta_id=str(cuenta_ves_a.id_cuenta_bancaria),
            estado="aprobada",
            tipo="cuenta",
        )
        assert len(lista_mcp) == 1 and lista_mcp[0]["id"] == prop_com_id

        with pytest.raises(PermissionError, match="scope"):
            tesoreria_generar_propuestas_conciliacion(
                str(tok_ro.token),
                str(empresa_a.id_empresa),
                str(cuenta_ves_a.id_cuenta_bancaria),
            )
        with pytest.raises(PermissionError, match="no coincide"):
            tesoreria_generar_propuestas_conciliacion(
                str(tok_rw.token),
                str(empresa_b.id_empresa),
                str(cuenta_ves_a.id_cuenta_bancaria),
            )
        with pytest.raises(PermissionError, match="no coincide"):
            tesoreria_listar_propuestas_conciliacion(
                str(tok_ro.token),
                str(empresa_b.id_empresa),
            )
        with pytest.raises(ValueError, match="UUID"):
            tesoreria_listar_propuestas_conciliacion(
                str(tok_ro.token),
                str(empresa_a.id_empresa),
                cuenta_id="no-uuid",
            )
        with pytest.raises(ValueError, match="entero"):
            tesoreria_listar_propuestas_conciliacion(
                str(tok_ro.token),
                str(empresa_a.id_empresa),
                limite="abc",  # type: ignore[arg-type]
            )
        with pytest.raises(ValueError, match="UUID"):
            tesoreria_generar_propuestas_conciliacion(
                str(tok_rw.token),
                str(empresa_a.id_empresa),
                "invalido",
            )
        with pytest.raises(ValueError, match="no encontrada"):
            tesoreria_generar_propuestas_conciliacion(
                str(tok_rw.token),
                str(empresa_a.id_empresa),
                str(uuid7()),
            )
        with pytest.raises(ValueError, match="posterior"):
            tesoreria_generar_propuestas_conciliacion(
                str(tok_rw.token),
                str(empresa_a.id_empresa),
                str(cuenta_ves_a.id_cuenta_bancaria),
                desde="2026-10-20",
                hasta="2026-10-01",
            )
        with pytest.raises(ValueError, match="ISO"):
            tesoreria_generar_propuestas_conciliacion(
                str(tok_rw.token),
                str(empresa_a.id_empresa),
                str(cuenta_ves_a.id_cuenta_bancaria),
                desde="31-10-2026",
            )

        # Soft delete de la configuración vía DELETE
        assert api_a.delete(f"{self.URL_CFG}{cfg_id}/").status_code == 204
        assert not ConfiguracionConciliacionCuenta.objects.get(pk=cfg_id).activo

    def test_regresion_b1_b2_b3_m1_m2_integridad_periodos_cerrados_y_odoo_defensivo(
        self,
        empresa_a,
        cuenta_ves_a,
        moneda_ves,
        metodo_transferencia_a,
        plan_comisiones_a,
        user_a,
        api_a: APIClient,
    ) -> None:
        from apps.tesoreria.services import conciliar_automatico

        moneda_usd, _ = Moneda.objects.get_or_create(
            codigo_iso="USD",
            defaults={"nombre": "Dólar", "simbolo": "$", "tipo_moneda": "fiat", "es_generica": True},
        )
        otra_cuenta_a = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_a,
            nombre_banco="Provincial",
            numero_cuenta="0108-0022-33-1111112222",
            tipo_cuenta="CORRIENTE",
            id_moneda=moneda_ves,
        )
        plan_inactivo = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="6.9.9.01",
            nombre_cuenta="Cuenta Inactiva",
            tipo_cuenta="GASTO",
            naturaleza="DEUDORA",
            nivel=4,
            activo=False,
        )

        # M-1 + B-1 en serializer: rechaza cuenta contable inactiva y conector de otro proveedor != odoo
        prov_sheets, _ = ConectorProveedor.objects.get_or_create(
            codigo="google_sheets", defaults={"nombre": "Google Sheets"}
        )
        conector_sheets = ConectorInstancia.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov_sheets,
            nombre="Sheets A",
            configuracion={"spreadsheet_id": "abc"},
            estado="activo",
            activo=True,
        )
        assert (
            api_a.post(
                self.URL_CFG,
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "id_cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                    "id_cuenta_comisiones": str(plan_inactivo.pk),
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            api_a.post(
                self.URL_CFG,
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "id_cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                    "id_conector_odoo": str(conector_sheets.pk),
                },
                format="json",
            ).status_code
            == 400
        )

        # M-1 en motor Odoo: registros con campos False / tuplas de 1 elemento no rompen
        def fake_ex_atipico(model: str, method: str, args: list[Any], kwargs: dict[str, Any]) -> Any:
            if model == "account.payment" and method == "fields_get":
                return {"memo": {"type": "char"}}
            if model == "account.payment" and method == "search_read":
                return [
                    {"id": False, "date": "2026-11-01", "amount": 10},
                    {"id": 1, "date": False, "amount": 10},
                    {"id": 2, "date": "no-fecha", "amount": 10},
                    {"id": 3, "date": "2026-11-01", "amount": 0},
                    {
                        "id": 4,
                        "name": False,
                        "date": "2026-11-01",
                        "amount": 55.5,
                        "payment_type": "inbound",
                        "memo": False,
                        "partner_id": [99],
                    },
                ]
            if model == "res.partner" and method == "read":
                return [{"id": False}, {"id": 99, "vat": False}]
            if model == "res.company" and method == "search_read":
                return [{"partner_id": False}, {"partner_id": [1]}]
            if model == "res.partner" and method == "search_read":
                return [{"id": False}, {"id": 50, "display_name": False, "vat": "J401234567"}]
            return []

        cands_atip = pagos_candidatos_odoo(
            fake_ex_atipico, journal_id=1, desde=date(2026, 11, 1), hasta=date(2026, 11, 2)
        )
        assert len(cands_atip) == 1 and cands_atip[0].nombre == "ODOO-4" and cands_atip[0].socio == ""
        assert contactos_por_rif_odoo(fake_ex_atipico, ["J401234567"]) == {"J401234567": ""}

        # B-1: CORREGIR rechaza pagos nativos con sentido invertido, otra moneda u otra cuenta bancaria
        cliente = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cliente Regresión", rif="J-334455667"
        )
        pedido = Pedido.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_pedido="PED-REG-1",
            fecha_pedido=date(2026, 11, 10),
            estado="APROBADO",
        )
        prov = Proveedor.objects.create(
            id_empresa=empresa_a, razon_social="Prov Regresión", rif="J-665544332"
        )
        cxp = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=prov,
            monto_total=D("200.00"),
            monto_pendiente=D("0.00"),
            fecha_emision=date(2026, 11, 10),
            fecha_vencimiento=date(2026, 11, 20),
            estado="PAGADA",
        )
        pago_egreso = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="EGRESO",
            tipo_documento="CXP",
            id_documento=cxp.id_cxp,
            id_cxp=cxp,
            fecha_pago=datetime(2026, 11, 10, 12, 0, tzinfo=dt_tz.utc),
            monto=D("200.00"),
            id_moneda=moneda_ves,
            id_metodo_pago=metodo_transferencia_a,
            id_cuenta_bancaria=cuenta_ves_a,
            referencia="EGR-200",
        )
        pago_usd = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="PEDIDO",
            id_documento=pedido.id_pedido,
            id_pedido=pedido,
            fecha_pago=datetime(2026, 11, 10, 12, 0, tzinfo=dt_tz.utc),
            monto=D("200.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_transferencia_a,
            id_cuenta_bancaria=cuenta_ves_a,
            referencia="USD-200",
        )
        pago_otra_cta = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="PEDIDO",
            id_documento=pedido.id_pedido,
            id_pedido=pedido,
            fecha_pago=datetime(2026, 11, 10, 12, 0, tzinfo=dt_tz.utc),
            monto=D("200.00"),
            id_moneda=moneda_ves,
            id_metodo_pago=metodo_transferencia_a,
            id_cuenta_bancaria=otra_cuenta_a,
            referencia="OTRACTA-200",
        )
        pago_ok = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="PEDIDO",
            id_documento=pedido.id_pedido,
            id_pedido=pedido,
            fecha_pago=datetime(2026, 11, 10, 12, 0, tzinfo=dt_tz.utc),
            monto=D("200.00"),
            id_moneda=moneda_ves,
            id_metodo_pago=metodo_transferencia_a,
            id_cuenta_bancaria=cuenta_ves_a,
            referencia="OK-200",
        )

        ConfiguracionConciliacionCuenta.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_ves_a,
            id_cuenta_comisiones=plan_comisiones_a,
        )
        mov_manual = MovimientoBancario.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_ves_a,
            fecha_mov=date(2026, 11, 10),
            descripcion="ABONO MANUAL CLIENTE",
            tipo="CREDITO",
            monto=D("200.00"),
            referencia="OK-200",
            origen="MANUAL",
        )
        mov_com = MovimientoBancario.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_ves_a,
            fecha_mov=date(2026, 11, 11),
            descripcion="COMISION BANCARIA",
            tipo="DEBITO",
            monto=D("15.00"),
            referencia="COM-15",
            categoria_clasificacion="comision_bancaria",
            origen="MANUAL",
        )
        generar_propuestas_conciliacion(empresa=empresa_a, cuenta_bancaria=cuenta_ves_a)
        prop_abono = PropuestaConciliacionBancaria.objects.get(id_movimiento_bancario=mov_manual)
        prop_com = PropuestaConciliacionBancaria.objects.get(id_movimiento_bancario=mov_com)

        with pytest.raises(DecisionPreconciliacionInvalida, match="sentido contable"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(prop_abono.pk),
                accion="CORREGIR",
                usuario=user_a,
                pago_nativo_id=str(pago_egreso.pk),
            )
        with pytest.raises(DecisionPreconciliacionInvalida, match="moneda"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(prop_abono.pk),
                accion="CORREGIR",
                usuario=user_a,
                pago_nativo_id=str(pago_usd.pk),
            )
        with pytest.raises(DecisionPreconciliacionInvalida, match="otra cuenta bancaria"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(prop_abono.pk),
                accion="CORREGIR",
                usuario=user_a,
                pago_nativo_id=str(pago_otra_cta.pk),
            )

        # B-1: Si la cuenta contable propuesta pasa a estar inactiva, APROBAR es rechazado
        plan_comisiones_a.activo = False
        plan_comisiones_a.save(update_fields=["activo"])
        with pytest.raises(DecisionPreconciliacionInvalida, match="inactiva"):
            decidir_propuesta_conciliacion(
                empresa=empresa_a,
                propuesta_id=str(prop_com.pk),
                accion="APROBAR",
                usuario=user_a,
            )
        plan_comisiones_a.activo = True
        plan_comisiones_a.save(update_fields=["activo"])

        # M-2 + S-1: decidir acepta nulls en campos opcionales y limpia saltos de línea en pago_externo_id
        r_nulls = api_a.post(
            f"{self.URL_PROP}{prop_com.pk}/decidir/",
            {
                "accion": "CORREGIR",
                "pago_externo_id": "EXT\n9001",
                "pago_nombre": None,
                "cuenta_contable_codigo": None,
                "comentario": None,
            },
            format="json",
        )
        assert r_nulls.status_code == 200
        assert r_nulls.json()["pago_externo_id"] == "EXT 9001"

        # B-3: Movimiento MANUAL con decisión humana RECHAZADA no permite mutar monto por PATCH
        decidir_propuesta_conciliacion(
            empresa=empresa_a,
            propuesta_id=str(prop_abono.pk),
            accion="RECHAZAR",
            usuario=user_a,
            comentario="En disputa",
        )
        assert (
            api_a.patch(
                f"/api/tesoreria/movimientos-bancarios/{mov_manual.pk}/",
                {"monto": "999.00"},
                format="json",
            ).status_code
            == 400
        )
        # B-2: conciliar_automatico respeta propuestas decididas (RECHAZADA) y no concilia mov_manual
        res_auto_bloq = conciliar_automatico(empresa_a, cuenta_ves_a)
        assert res_auto_bloq["conciliados"] == 0

        # Al reabrir, conciliar_automatico sí concilia mov_manual contra pago_ok y desactiva la propuesta PENDIENTE
        decidir_propuesta_conciliacion(
            empresa=empresa_a,
            propuesta_id=str(prop_abono.pk),
            accion="REABRIR",
            usuario=user_a,
            comentario="Autorizado conciliar",
        )
        res_auto_ok = conciliar_automatico(empresa_a, cuenta_ves_a)
        assert res_auto_ok["conciliados"] == 1
        mov_manual.refresh_from_db()
        assert mov_manual.id_pago_conciliado_id == pago_ok.pk
        prop_abono.refresh_from_db()
        assert prop_abono.activo is False

        # B-3: Período CERRADO bloquea crear/editar/borrar movimientos y desactivar extractos
        corte_cerrado = _xlsx(
            [
                ["Cuenta: 0105-0011-22-1234567806"],
                ["Saldo Inicial: 0,00"],
                ["Fecha", "Referencia", "Concepto", "Débito", "Crédito", "Saldo"],
                ["15/11/2026", "5501", "ABONO EN PERIODO A CERRAR", "", "100,00", "100,00"],
            ]
        )
        imp_cerr = importar_extracto_bancario(
            empresa=empresa_a,
            cuenta_bancaria=cuenta_ves_a,
            contenido=corte_cerrado,
            nombre_archivo="cierre_nov.xlsx",
            formato_banco="MERCANTIL",
            usuario=user_a,
        )
        mov_en_cierre = imp_cerr.archivo.movimientos.first()
        assert mov_en_cierre is not None

        ConciliacionBancaria.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_ves_a,
            periodo_inicio=date(2026, 11, 14),
            periodo_fin=date(2026, 11, 30),
            saldo_banco=D("100.00"),
            saldo_libro=D("100.00"),
            estado="CERRADA",
        )
        with pytest.raises(ExtractoBancarioError, match="período de conciliación cerrado"):
            desactivar_extracto_bancario(imp_cerr.archivo)
        assert (
            api_a.delete(f"/api/tesoreria/movimientos-bancarios/{mov_en_cierre.pk}/").status_code
            == 400
        )
        assert (
            api_a.post(
                "/api/tesoreria/movimientos-bancarios/",
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "id_cuenta_bancaria": str(cuenta_ves_a.id_cuenta_bancaria),
                    "fecha_mov": "2026-11-20",
                    "descripcion": "Intento en período cerrado",
                    "tipo": "CREDITO",
                    "monto": "50.00",
                },
                format="json",
            ).status_code
            == 400
        )


