"""Suite integral PR-17 (Ola B5): consolidación bancaria, lotes VE, RLS, Matriz-Subsidiaria y MCP."""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import ProgrammingError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.banca_electronica.mcp import banca_listar_lotes_pago, banca_validar_referencia
from apps.banca_electronica.models import DetalleLotePagoBancario, LotePagoBancario
from apps.banca_electronica.services import (
    BancaElectronicaError,
    cambiar_estado_lote,
    generar_lote_pagos_nomina,
    generar_lote_pagos_proveedores,
    validar_cuenta_bancaria_ve,
    validar_referencia_bancaria,
)
from apps.compras.models import FacturaCompra, OrdenCompra
from apps.core import rls
from apps.core.mcp_server import mcp
from apps.core.models import CapabilityToken, Contacto, Empresa
from apps.cuentas_por_pagar.models import CuentaPorPagar
from apps.finanzas.models import AsignacionPago, CuentaBancariaEmpresa, MetodoPago, Moneda, Pago
from apps.finanzas.serializers import CuentaBancariaEmpresaSerializer
from apps.nomina.models import Nomina, PeriodoNomina, ProcesoNomina
from apps.proveedores.models import CuentaBancariaProveedor, Proveedor
from apps.rrhh.models import Empleado
from apps.tesoreria.models import MovimientoBancario

pytestmark = [pytest.mark.django_db]


def _client_para(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _mk_moneda_global(codigo: str = "USD") -> Moneda:
    moneda, _ = Moneda.objects.get_or_create(
        codigo_iso=codigo,
        defaults={
            "nombre": f"Moneda {codigo}",
            "simbolo": "$",
            "es_generica": True,
            "es_publica": True,
        },
    )
    return moneda


def _mk_metodo(empresa: Empresa | None = None, nombre: str = "Transferencia") -> MetodoPago:
    metodo, _ = MetodoPago.objects.get_or_create(
        empresa=empresa,
        nombre_metodo=nombre,
        defaults={
            "tipo_metodo": "TRANSFERENCIA",
            "es_generico": empresa is None,
            "es_publico": empresa is None,
        },
    )
    return metodo


def _mk_cuenta(
    empresa: Empresa,
    moneda: Moneda,
    numero: str | None = None,
    banco: str = "Banesco",
    activo: bool = True,
) -> CuentaBancariaEmpresa:
    num = numero or f"0134000101{uuid.uuid4().hex[:10].upper()}"
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa,
        nombre_banco=banco,
        numero_cuenta=num,
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda,
        saldo_actual=Decimal("50000.00"),
        activo=activo,
    )


def _mk_proveedor_y_pago(
    empresa: Empresa,
    moneda: Moneda,
    metodo: MetodoPago,
    cuenta_empresa: CuentaBancariaEmpresa | None = None,
    *,
    nombre: str = "Proveedor Prueba CA",
    rif: str | None = None,
    cuenta_prov_num: str | None = "AUTO",
    monto: Decimal = Decimal("250.50"),
    tipo_operacion: str = "EGRESO",
    referencia: str = "REF-PROV-001",
    observaciones: str = "Pago factura compra",
    via: str = "contacto",
) -> tuple[Proveedor, Pago]:
    rif_val = rif or f"J-{str(uuid.uuid4().int % (10**8)).zfill(8)}-9"
    contacto = Contacto.objects.create(
        id_empresa=empresa,
        nombre=nombre,
        rif=rif_val,
        es_proveedor=True,
    )
    prov = Proveedor.objects.create(
        id_empresa=empresa,
        razon_social=nombre,
        rif=rif_val,
        contacto=contacto,
    )
    if cuenta_prov_num is not None:
        num_cta = f"0102{str(uuid.uuid4().int % (10**16)).zfill(16)}" if cuenta_prov_num == "AUTO" else cuenta_prov_num
        CuentaBancariaProveedor.objects.create(
            id_proveedor=prov,
            nombre_banco="Banco de Venezuela",
            numero_cuenta=num_cta,
            tipo_cuenta="CORRIENTE",
            moneda=moneda,
            es_cuenta_principal=True,
        )

    cxp = CuentaPorPagar.objects.create(
        id_empresa=empresa,
        id_proveedor=prov,
        referencia_externa=f"CXP-{uuid.uuid4().hex[:6]}",
        fecha_emision=date.today(),
        fecha_vencimiento=date.today() + timedelta(days=15),
        monto_total=monto,
        monto_pendiente=monto,
        estado="PENDIENTE",
    )

    if via == "contacto":
        pago = Pago.objects.create(
            id_empresa=empresa,
            id_contacto=contacto,
            tipo_operacion=tipo_operacion,
            tipo_documento="CXP",
            id_documento=cxp.pk,
            id_cxp=cxp,
            fecha_pago=timezone.now(),
            monto=monto,
            id_moneda=moneda,
            id_metodo_pago=metodo,
            id_cuenta_bancaria=cuenta_empresa,
            referencia=referencia,
            observaciones=observaciones,
        )
    else:
        # Sin contacto directo ni id_cxp en Pago: resuelto via AsignacionPago.
        contacto_alt = Contacto.objects.create(
            id_empresa=empresa,
            nombre="Otro Contacto",
            rif=f"J-{uuid.uuid4().hex[:8]}",
            es_proveedor=True,
        )
        pago = Pago.objects.create(
            id_empresa=empresa,
            id_contacto=contacto_alt,
            tipo_operacion=tipo_operacion,
            tipo_documento="AJUSTE",
            fecha_pago=timezone.now(),
            monto=monto,
            id_moneda=moneda,
            id_metodo_pago=metodo,
            id_cuenta_bancaria=cuenta_empresa,
            referencia=referencia,
            observaciones=observaciones,
        )
        AsignacionPago.objects.create(
            id_empresa=empresa,
            id_contacto=contacto,
            id_pago=pago,
            tipo_documento="CUENTA_POR_PAGAR",
            id_documento=str(cxp.pk),
            id_cxp=cxp,
            id_moneda_documento=moneda,
            monto_asignado_pago=monto,
            monto_asignado_documento=monto,
            estado="ACTIVA",
        )
    return prov, pago


# ── 1. Migración de datos 0004 + esquema 0005/0006 reversible ────────────────


@pytest.mark.django_db(transaction=True)
def test_migracion_0004_copia_cuentas_sin_duplicar_y_reversa_limpia():
    executor = MigrationExecutor(connection)
    executor.migrate([("banca_electronica", "0003_rls_lote3_banca_electronica")])
    try:
        targets_0003 = [
            ("banca_electronica", "0003_rls_lote3_banca_electronica") if app == "banca_electronica" else (app, name)
            for app, name in executor.loader.graph.leaf_nodes()
        ]
        old_apps = executor.loader.project_state(targets_0003).apps
        OldEmpresa = old_apps.get_model("core", "Empresa")
        OldMoneda = old_apps.get_model("finanzas", "Moneda")
        OldBancaCuenta = old_apps.get_model("banca_electronica", "CuentaBancariaEmpresa")
        OldFinCuenta = old_apps.get_model("finanzas", "CuentaBancariaEmpresa")

        with rls.rls_bypass():
            moneda = OldMoneda.objects.create(
                codigo_iso=f"M{uuid.uuid4().hex[:2].upper()}",
                nombre="Moneda Migración",
                simbolo="$",
                es_generica=True,
                es_publica=True,
            )
            emp = OldEmpresa.objects.create(
                nombre_legal="Empresa Mig SA",
                identificador_fiscal=f"J-{uuid.uuid4().hex[:8]}",
                id_moneda_base=moneda,
            )
            cta_existente_num = f"0134-EXIST-{uuid.uuid4().hex[:6]}"
            OldFinCuenta.objects.create(
                id_empresa=emp,
                nombre_banco="Banesco Previo",
                numero_cuenta=cta_existente_num,
                tipo_cuenta="CORRIENTE",
                id_moneda=moneda,
                saldo_actual=Decimal("999.00"),
                activo=True,
            )
            cta_corr_num = f"0102-MIG-{uuid.uuid4().hex[:6]}"
            cta_aho_num = f"0105-MIG-{uuid.uuid4().hex[:6]}"
            OldBancaCuenta.objects.create(
                empresa=emp,
                banco="Banco de Venezuela",
                numero_cuenta=cta_corr_num,
                tipo_cuenta="CORRIENTE ",
                moneda=moneda,
                saldo_actual=Decimal("1250.25"),
                activa=True,
            )
            OldBancaCuenta.objects.create(
                empresa=emp,
                banco="Mercantil",
                numero_cuenta=cta_aho_num,
                tipo_cuenta="ahorro",
                moneda=moneda,
                saldo_actual=Decimal("500.00"),
                activa=False,
            )
            OldBancaCuenta.objects.create(
                empresa=emp,
                banco="Duplicada",
                numero_cuenta=cta_existente_num,
                tipo_cuenta="corriente",
                moneda=moneda,
                saldo_actual=Decimal("10.00"),
                activa=True,
            )

        executor = MigrationExecutor(connection)
        executor.migrate([("banca_electronica", "0006_rls_lote_pago")])

        mig_corr = CuentaBancariaEmpresa.objects.get(numero_cuenta=cta_corr_num)
        assert mig_corr.nombre_banco == "Banco de Venezuela"
        assert mig_corr.tipo_cuenta == "CORRIENTE"
        assert mig_corr.saldo_actual == Decimal("1250.25")
        assert mig_corr.activo is True

        mig_aho = CuentaBancariaEmpresa.objects.get(numero_cuenta=cta_aho_num)
        assert mig_aho.tipo_cuenta == "AHORRO"
        assert mig_aho.activo is False

        assert CuentaBancariaEmpresa.objects.filter(numero_cuenta=cta_existente_num).count() == 1
        assert CuentaBancariaEmpresa.objects.get(numero_cuenta=cta_existente_num).saldo_actual == Decimal("999.00")

        # Reversa 0006 -> 0004 (recrea tabla antigua + RLS) y vuelta a 0006
        executor = MigrationExecutor(connection)
        executor.migrate([("banca_electronica", "0004_migrar_cuentas_a_finanzas")])
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


# ── 2. Validador SUDEBAN VE ──────────────────────────────────────────────────


def test_validar_cuenta_bancaria_ve():
    ok = validar_cuenta_bancaria_ve("0134-0001-01 0123456789")
    assert ok == {
        "valida": True,
        "numero_normalizado": "01340001010123456789",
        "codigo_banco": "0134",
        "banco_nombre": "Banesco",
        "errores": [],
    }

    bdv = validar_cuenta_bancaria_ve("01020102010123456789")
    assert bdv["valida"] is True
    assert bdv["banco_nombre"] == "Banco de Venezuela"

    bad_prefix = validar_cuenta_bancaria_ve("99990001010123456789")
    assert bad_prefix["valida"] is False
    assert bad_prefix["banco_nombre"] is None
    assert any("9999" in e for e in bad_prefix["errores"])

    short = validar_cuenta_bancaria_ve("0134-123")
    assert short["valida"] is False
    assert any("20 dígitos" in e for e in short["errores"])

    letters = validar_cuenta_bancaria_ve("0134000101012345678A")
    assert letters["valida"] is False
    assert any("dígitos numéricos" in e for e in letters["errores"])

    empty = validar_cuenta_bancaria_ve("")
    assert empty["valida"] is False
    assert empty["errores"]


# ── 3. Validador de referencia bancaria duplicada ────────────────────────────


def test_validar_referencia_bancaria_tres_fuentes_e_isolacion(empresa_a, empresa_b):
    moneda = _mk_moneda_global("USD")
    metodo = _mk_metodo()
    cta_a = _mk_cuenta(empresa_a, moneda)
    cta_b = _mk_cuenta(empresa_b, moneda)

    _, pago_a = _mk_proveedor_y_pago(
        empresa_a,
        moneda,
        metodo,
        cta_a,
        referencia="REF-DUP-01",
    )
    MovimientoBancario.objects.create(
        id_empresa=empresa_a,
        id_cuenta_bancaria=cta_a,
        fecha_mov=date.today(),
        descripcion="Transferencia banco",
        tipo="DEBITO",
        monto=Decimal("100.00"),
        referencia="MOV-EXT-99",
    )
    lote_a = LotePagoBancario.objects.create(
        id_empresa=empresa_a,
        id_cuenta_bancaria=cta_a,
        tipo_lote="PROVEEDORES",
        formato_banco="BANESCO_TXT",
        referencia_lote="LOTE-REF-1",
        fecha_valor=date.today(),
        estado="GENERADO",
    )
    DetalleLotePagoBancario.objects.create(
        id_lote_pago=lote_a,
        beneficiario_nombre="Benef",
        beneficiario_identificacion="J-1",
        cuenta_destino="01340001010123456789",
        monto=Decimal("50.00"),
        referencia_linea="LOTE-LIN-77",
    )
    lote_anulado = LotePagoBancario.objects.create(
        id_empresa=empresa_a,
        id_cuenta_bancaria=cta_a,
        tipo_lote="PROVEEDORES",
        formato_banco="BANESCO_TXT",
        referencia_lote="LOTE-ANUL-1",
        fecha_valor=date.today(),
        estado="ANULADO",
    )
    DetalleLotePagoBancario.objects.create(
        id_lote_pago=lote_anulado,
        beneficiario_nombre="Benef Anul",
        beneficiario_identificacion="J-2",
        cuenta_destino="01340001010123456789",
        monto=Decimal("50.00"),
        referencia_linea="REF-ANULADA-55",
    )

    with pytest.raises(BancaElectronicaError):
        validar_referencia_bancaria(empresa=empresa_a, cuenta_bancaria=cta_a, referencia="   ")

    # 1) Match case-insensitive en Pago + excluir_pago_id
    r_pago = validar_referencia_bancaria(empresa=empresa_a, cuenta_bancaria=cta_a, referencia=" ref-dup-01 ")
    assert r_pago["duplicada"] is True
    assert r_pago["referencia_normalizada"] == "REF-DUP-01"
    assert r_pago["coincidencias"][0]["origen"] == "finanzas.Pago"

    r_excluido = validar_referencia_bancaria(
        empresa=empresa_a,
        cuenta_bancaria=cta_a,
        referencia="REF-DUP-01",
        excluir_pago_id=pago_a.pk,
    )
    assert r_excluido["duplicada"] is False

    # 2) Match en MovimientoBancario
    r_mov = validar_referencia_bancaria(empresa=empresa_a, cuenta_bancaria=cta_a, referencia="mov-ext-99")
    assert r_mov["duplicada"] is True
    assert r_mov["coincidencias"][0]["origen"] == "tesoreria.MovimientoBancario"

    # 3) Match en DetalleLotePagoBancario activo, pero ignora ANULADO
    r_lote = validar_referencia_bancaria(empresa=empresa_a, cuenta_bancaria=cta_a, referencia="lote-lin-77")
    assert r_lote["duplicada"] is True
    assert r_lote["coincidencias"][0]["origen"] == "banca_electronica.DetalleLotePagoBancario"

    r_anul = validar_referencia_bancaria(empresa=empresa_a, cuenta_bancaria=cta_a, referencia="REF-ANULADA-55")
    assert r_anul["duplicada"] is False

    # 4) Aislamiento estricto cross-tenant
    r_b = validar_referencia_bancaria(empresa=empresa_b, cuenta_bancaria=cta_b, referencia="REF-DUP-01")
    assert r_b["duplicada"] is False


# ── 4. Generadores de lotes (Proveedores & Nómina) + Máquina de estados ──────


@pytest.mark.parametrize("formato", ["BANESCO_TXT", "MERCANTIL_TXT", "BDV_TXT", "GENERICO_CSV"])
def test_generar_lote_proveedores_formatos_y_sanitizacion(empresa_a, user_a, formato):
    moneda = _mk_moneda_global("USD")
    metodo = _mk_metodo()
    cta = _mk_cuenta(empresa_a, moneda)
    _, p1 = _mk_proveedor_y_pago(
        empresa_a,
        moneda,
        metodo,
        cta,
        nombre='=cmd|"/C calc"!A0\nProveedor',
        rif="J-11111111-1",
        cuenta_prov_num="0102-0001-01-1234567890",
        monto=Decimal("100.25"),
        referencia="PAG-001",
        observaciones="+SUM(A1:A2)\rFactura",
    )
    _, p2 = _mk_proveedor_y_pago(
        empresa_a,
        moneda,
        metodo,
        cta,
        nombre="Proveedor Dos",
        rif="J-22222222-2",
        cuenta_prov_num=None,
        monto=Decimal("200.75"),
        referencia="PAG-002",
        via="asignacion",
    )

    lote = generar_lote_pagos_proveedores(
        empresa=empresa_a,
        cuenta_bancaria=cta,
        pagos_ids=[p1.pk, p2.pk],
        formato_banco=formato,
        fecha_valor=date(2026, 11, 20),
        usuario=user_a,
        cuentas_destino_override={str(p2.pk): "01910001019876543210"},
    )
    assert lote.estado == "GENERADO"
    assert lote.tipo_lote == "PROVEEDORES"
    assert lote.total_registros == 2
    assert lote.monto_total == Decimal("301.00")
    assert lote.sha256_archivo == hashlib.sha256(lote.contenido_archivo.encode("utf-8")).hexdigest()
    assert lote.detalles.count() == 2

    if formato == "GENERICO_CSV":
        assert "''" not in lote.contenido_archivo
        assert "'=cmd" in lote.contenido_archivo
        assert "'+SUM" in lote.contenido_archivo
        assert lote.nombre_archivo.endswith(".csv")
    else:
        assert lote.nombre_archivo.endswith(".txt")
        # Saltos de línea inyectados dentro del nombre/concepto fueron sanitizados (1 header + 2 detalles)
        assert len(lote.contenido_archivo.strip().splitlines()) == 3


def test_generar_lote_proveedores_reglas_y_bloqueos(empresa_a, empresa_b, user_a):
    moneda = _mk_moneda_global("USD")
    metodo = _mk_metodo()
    cta = _mk_cuenta(empresa_a, moneda)
    _, pago_ok = _mk_proveedor_y_pago(empresa_a, moneda, metodo, cta, referencia="P-OK")
    _, pago_ingreso = _mk_proveedor_y_pago(
        empresa_a, moneda, metodo, cta, tipo_operacion="INGRESO", referencia="P-ING", rif="J-99999999-1"
    )
    cta_b = _mk_cuenta(empresa_b, moneda)
    _, pago_b = _mk_proveedor_y_pago(empresa_b, moneda, metodo, cta_b, referencia="P-B")

    with pytest.raises(BancaElectronicaError, match="INGRESO"):
        generar_lote_pagos_proveedores(
            empresa=empresa_a,
            cuenta_bancaria=cta,
            pagos_ids=[pago_ingreso.pk],
            formato_banco="BANESCO_TXT",
            fecha_valor=date.today(),
            usuario=user_a,
        )

    with pytest.raises(BancaElectronicaError):
        generar_lote_pagos_proveedores(
            empresa=empresa_a,
            cuenta_bancaria=cta,
            pagos_ids=[pago_b.pk],
            formato_banco="BANESCO_TXT",
            fecha_valor=date.today(),
            usuario=user_a,
        )

    lote = generar_lote_pagos_proveedores(
        empresa=empresa_a,
        cuenta_bancaria=cta,
        pagos_ids=[pago_ok.pk],
        formato_banco="BANESCO_TXT",
        fecha_valor=date.today(),
        usuario=user_a,
    )
    # Bloqueo doble pago en lote activo
    with pytest.raises(BancaElectronicaError, match="lote activo"):
        generar_lote_pagos_proveedores(
            empresa=empresa_a,
            cuenta_bancaria=cta,
            pagos_ids=[pago_ok.pk],
            formato_banco="BANESCO_TXT",
            fecha_valor=date.today(),
            usuario=user_a,
        )

    # Tras ANULAR sí permite generar otro lote para ese pago
    cambiar_estado_lote(lote, "ANULADO", user_a)
    lote2 = generar_lote_pagos_proveedores(
        empresa=empresa_a,
        cuenta_bancaria=cta,
        pagos_ids=[pago_ok.pk],
        formato_banco="GENERICO_CSV",
        fecha_valor=date.today(),
        usuario=user_a,
    )
    assert lote2.estado == "GENERADO"


def test_generar_lote_nomina_y_maquina_estados(empresa_a, user_a):
    moneda = _mk_moneda_global("USD")
    cta = _mk_cuenta(empresa_a, moneda)
    periodo = PeriodoNomina.objects.create(
        id_empresa=empresa_a,
        nombre_periodo="Quincena 1 Nov",
        tipo_periodo="QUINCENAL",
        fecha_inicio=date(2026, 11, 1),
        fecha_fin=date(2026, 11, 15),
        fecha_pago=date(2026, 11, 15),
    )
    proc_en_proceso = ProcesoNomina.objects.create(
        id_empresa=empresa_a,
        id_periodo_nomina=periodo,
        numero_proceso="NOM-PROC-01",
        fecha_proceso=timezone.now(),
        estado="EN_PROCESO",
    )
    with pytest.raises(BancaElectronicaError, match="COMPLETADO o APROBADO"):
        generar_lote_pagos_nomina(
            empresa=empresa_a,
            cuenta_bancaria=cta,
            proceso_nomina=proc_en_proceso,
            formato_banco="MERCANTIL_TXT",
            fecha_valor=date.today(),
            usuario=user_a,
        )

    proc_ok = ProcesoNomina.objects.create(
        id_empresa=empresa_a,
        id_periodo_nomina=periodo,
        numero_proceso="NOM-PROC-02",
        fecha_proceso=timezone.now(),
        estado="APROBADO",
    )
    emp1 = Empleado.objects.create(
        empresa=empresa_a,
        nombre="Ana",
        apellido="Pérez",
        cedula="V-12345678",
        fecha_ingreso=date(2024, 1, 10),
        documento_json={"numero_cuenta": "01050001011234567890"},
    )
    emp2 = Empleado.objects.create(
        empresa=empresa_a,
        nombre="Luis",
        apellido="Gómez",
        cedula="V-87654321",
        fecha_ingreso=date(2024, 3, 1),
    )
    Nomina.objects.create(
        id_proceso_nomina=proc_ok,
        id_empleado=emp1,
        sueldo_base=Decimal("500.00"),
        total_neto=Decimal("450.50"),
        fecha_calculo=timezone.now(),
    )
    Nomina.objects.create(
        id_proceso_nomina=proc_ok,
        id_empleado=emp2,
        sueldo_base=Decimal("600.00"),
        total_neto=Decimal("549.50"),
        fecha_calculo=timezone.now(),
    )

    lote = generar_lote_pagos_nomina(
        empresa=empresa_a,
        cuenta_bancaria=cta,
        proceso_nomina=proc_ok,
        formato_banco="MERCANTIL_TXT",
        fecha_valor=date(2026, 11, 15),
        usuario=user_a,
        cuentas_empleados={str(emp2.pk): "01340001010123456789"},
    )
    assert lote.tipo_lote == "NOMINA"
    assert lote.total_registros == 2
    assert lote.monto_total == Decimal("1000.00")

    # Bloqueo doble lote para el mismo proceso
    with pytest.raises(BancaElectronicaError, match="lote activo"):
        generar_lote_pagos_nomina(
            empresa=empresa_a,
            cuenta_bancaria=cta,
            proceso_nomina=proc_ok,
            formato_banco="MERCANTIL_TXT",
            fecha_valor=date(2026, 11, 15),
            usuario=user_a,
            cuentas_empleados={str(emp2.pk): "01340001010123456789"},
        )

    # Máquina estricta de estados
    with pytest.raises(BancaElectronicaError):
        cambiar_estado_lote(lote, "PROCESADO", user_a)

    lote = cambiar_estado_lote(lote, "ENVIADO", user_a)
    assert lote.estado == "ENVIADO"
    with pytest.raises(BancaElectronicaError):
        cambiar_estado_lote(lote, "ANULADO", user_a)

    lote = cambiar_estado_lote(lote, "PROCESADO", user_a)
    assert lote.estado == "PROCESADO"
    with pytest.raises(BancaElectronicaError):
        cambiar_estado_lote(lote, "GENERADO", user_a)


# ── 5. REST API, Matriz ↔ Subsidiaria, IDOR y NulSafeFilterMixin ─────────────


def test_api_rest_lotes_validador_descarga_y_seguridad(empresa_a, empresa_b, user_a):
    moneda_global = _mk_moneda_global("USD")
    moneda_b = Moneda.objects.create(
        codigo_iso="EURB",
        nombre="Privada B",
        simbolo="E",
        es_generica=False,
        es_publica=False,
        empresa=empresa_b,
    )
    metodo_global = _mk_metodo()
    metodo_b = _mk_metodo(empresa_b, "Metodo Privado B")
    cta_a = _mk_cuenta(empresa_a, moneda_global)
    cta_b = _mk_cuenta(empresa_b, moneda_global)
    _, pago_a = _mk_proveedor_y_pago(empresa_a, moneda_global, metodo_global, cta_a, referencia="REF-API-1")
    _, pago_b = _mk_proveedor_y_pago(empresa_b, moneda_global, metodo_global, cta_b, referencia="REF-API-B")

    client_a = _client_para(user_a)

    # POST libre, PATCH y DELETE bloqueados con 405
    assert client_a.post("/api/banca-electronica/lotes-pago/", {}, format="json").status_code == 405

    # Validador VE
    r_ve = client_a.post(
        "/api/banca-electronica/validar-cuenta-ve/",
        {"numero_cuenta": "0105-0001-01-1234567890"},
        format="json",
    )
    assert r_ve.status_code == 200
    assert r_ve.data["valida"] is True
    assert r_ve.data["banco_nombre"] == "Mercantil"

    # Validador referencia
    r_ref = client_a.post(
        "/api/banca-electronica/validar-referencia/",
        {"id_cuenta_bancaria": str(cta_a.pk), "referencia": "ref-api-1"},
        format="json",
    )
    assert r_ref.status_code == 200
    assert r_ref.data["duplicada"] is True

    # Cross-tenant en validar-referencia -> 400
    assert (
        client_a.post(
            "/api/banca-electronica/validar-referencia/",
            {"id_cuenta_bancaria": str(cta_b.pk), "referencia": "REF-API-B"},
            format="json",
        ).status_code
        == 400
    )

    # Cross-tenant en generar-proveedores -> 400
    assert (
        client_a.post(
            "/api/banca-electronica/lotes-pago/generar-proveedores/",
            {
                "id_cuenta_bancaria": str(cta_a.pk),
                "pagos_ids": [str(pago_b.pk)],
                "formato_banco": "BANESCO_TXT",
                "fecha_valor": "2026-11-20",
            },
            format="json",
        ).status_code
        == 400
    )

    # Generación válida via API
    r_gen = client_a.post(
        "/api/banca-electronica/lotes-pago/generar-proveedores/",
        {
            "id_cuenta_bancaria": str(cta_a.pk),
            "pagos_ids": [str(pago_a.pk)],
            "formato_banco": "BDV_TXT",
            "fecha_valor": "2026-11-20",
            "referencia_lote": "LOTE-REST-01",
        },
        format="json",
    )
    assert r_gen.status_code == 201
    lote_id = r_gen.data["id_lote_pago"]
    assert r_gen.data["estado"] == "GENERADO"

    # PATCH / DELETE retornan 405
    assert client_a.patch(f"/api/banca-electronica/lotes-pago/{lote_id}/", {}, format="json").status_code == 405
    assert client_a.delete(f"/api/banca-electronica/lotes-pago/{lote_id}/").status_code == 405

    # Listado + filtro NUL-safe (\x00) bloqueado limpiamente (400, nunca 500) + ?empresa= UUID validación
    assert client_a.get("/api/banca-electronica/lotes-pago/?search=foo%00bar").status_code == 400
    assert client_a.get("/api/banca-electronica/lotes-pago/?search=LOTE-REST-01").status_code == 200
    assert client_a.get("/api/banca-electronica/lotes-pago/?empresa=no-uuid").status_code == 400
    assert client_a.get(f"/api/banca-electronica/lotes-pago/?empresa={empresa_a.pk}").data["count"] == 1

    # Descarga y headers seguros
    r_dl = client_a.get(f"/api/banca-electronica/lotes-pago/{lote_id}/descargar/")
    assert r_dl.status_code == 200
    assert r_dl["Content-Type"].startswith("text/plain")
    assert 'attachment; filename="' in r_dl["Content-Disposition"]
    assert r_dl["X-Content-Type-Options"] == "nosniff"
    assert r_dl["X-Lote-Sha256"] == r_gen.data["sha256_archivo"]

    # Transiciones REST
    assert (
        client_a.post(f"/api/banca-electronica/lotes-pago/{lote_id}/marcar-enviado/", {}, format="json").data["estado"]
        == "ENVIADO"
    )
    assert (
        client_a.post(f"/api/banca-electronica/lotes-pago/{lote_id}/marcar-procesado/", {}, format="json").data[
            "estado"
        ]
        == "PROCESADO"
    )
    assert client_a.post(f"/api/banca-electronica/lotes-pago/{lote_id}/anular/", {}, format="json").status_code == 400

    # Endurecimiento finanzas.CuentaBancariaEmpresaViewSet + serializer
    assert client_a.get("/api/finanzas/cuentas-bancarias-empresa/?search=foo%00bar").status_code == 400
    assert client_a.get("/api/finanzas/cuentas-bancarias-empresa/?search=Banesco").status_code == 200
    assert client_a.get("/api/finanzas/cuentas-bancarias-empresa/?empresa=bad-uuid").status_code == 400
    r_cta_bad_moneda = client_a.post(
        "/api/finanzas/cuentas-bancarias-empresa/",
        {
            "id_empresa": str(empresa_a.pk),
            "nombre_banco": "Banesco",
            "numero_cuenta": "01340001010000000001",
            "tipo_cuenta": "CORRIENTE",
            "id_moneda": str(moneda_b.pk),
        },
        format="json",
    )
    assert r_cta_bad_moneda.status_code == 400

    r_cta_bad_met = client_a.post(
        "/api/finanzas/cuentas-bancarias-empresa/",
        {
            "id_empresa": str(empresa_a.pk),
            "nombre_banco": "Banesco",
            "numero_cuenta": "01340001010000000002",
            "tipo_cuenta": "CORRIENTE",
            "id_moneda": str(moneda_global.pk),
            "metodos_pago": [str(metodo_b.pk)],
        },
        format="json",
    )
    assert r_cta_bad_met.status_code == 400

    # Alta sin metodos_pago y bloqueo cambio id_empresa en PATCH
    r_cta_ok = client_a.post(
        "/api/finanzas/cuentas-bancarias-empresa/",
        {
            "id_empresa": str(empresa_a.pk),
            "nombre_banco": "Bancamiga",
            "numero_cuenta": "01720001010000000003",
            "tipo_cuenta": "AHORRO",
            "id_moneda": str(moneda_global.pk),
        },
        format="json",
    )
    assert r_cta_ok.status_code == 201
    cta_ok_id = r_cta_ok.data["id_cuenta_bancaria"]
    assert (
        client_a.patch(
            f"/api/finanzas/cuentas-bancarias-empresa/{cta_ok_id}/",
            {"id_empresa": str(empresa_b.pk)},
            format="json",
        ).status_code
        == 400
    )


def test_matriz_subsidiaria_scoping_finanzas_y_banca(empresa_a, user_a):
    moneda_global = _mk_moneda_global("USD")
    subsidiaria = Empresa.objects.create(
        nombre_legal="Subsidiaria A",
        identificador_fiscal=f"J-{uuid.uuid4().hex[:8]}",
        id_moneda_base=moneda_global,
        empresa_matriz=empresa_a,
    )
    empresa_otra = Empresa.objects.create(
        nombre_legal="Ajena",
        identificador_fiscal=f"J-{uuid.uuid4().hex[:8]}",
        id_moneda_base=moneda_global,
    )
    metodo_matriz = _mk_metodo(empresa_a, "Metodo Matriz")
    metodo_sub = _mk_metodo(subsidiaria, "Metodo Subsidiaria")

    client = _client_para(user_a)

    # Matriz NO puede mezclar empresa Subsidiaria con método privado de Matriz
    assert (
        client.post(
            "/api/finanzas/cuentas-bancarias-empresa/",
            {
                "id_empresa": str(subsidiaria.pk),
                "nombre_banco": "Mercantil",
                "numero_cuenta": "01050001010000001111",
                "tipo_cuenta": "CORRIENTE",
                "id_moneda": str(moneda_global.pk),
                "metodos_pago": [str(metodo_matriz.pk)],
            },
            format="json",
        ).status_code
        == 400
    )

    # Matriz SÍ puede crear cuenta de su Subsidiaria usando método propio de la Subsidiaria
    r_sub = client.post(
        "/api/finanzas/cuentas-bancarias-empresa/",
        {
            "id_empresa": str(subsidiaria.pk),
            "nombre_banco": "Mercantil",
            "numero_cuenta": "01050001010000002222",
            "tipo_cuenta": "CORRIENTE",
            "id_moneda": str(moneda_global.pk),
            "metodos_pago": [str(metodo_sub.pk)],
        },
        format="json",
    )
    assert r_sub.status_code == 201
    cta_sub_id = r_sub.data["id_cuenta_bancaria"]
    cta_sub = CuentaBancariaEmpresa.objects.get(pk=cta_sub_id)

    # Filtro ?empresa=subsidiaria funciona para Matriz, pero ajena -> vacío
    assert client.get(f"/api/finanzas/cuentas-bancarias-empresa/?empresa={subsidiaria.pk}").data["count"] == 1
    assert client.get(f"/api/finanzas/cuentas-bancarias-empresa/?empresa={empresa_otra.pk}").data["count"] == 0

    # Banca: no permite mezclar cuenta_sub con pago_matriz
    _, pago_matriz = _mk_proveedor_y_pago(empresa_a, moneda_global, metodo_matriz, referencia="REF-MATRIZ")
    assert (
        client.post(
            "/api/banca-electronica/lotes-pago/generar-proveedores/",
            {
                "id_cuenta_bancaria": str(cta_sub.pk),
                "pagos_ids": [str(pago_matriz.pk)],
                "formato_banco": "BANESCO_TXT",
                "fecha_valor": "2026-11-20",
            },
            format="json",
        ).status_code
        == 400
    )

    # Banca: SÍ permite operar lote de la Subsidiaria cuando todo pertenece a la Subsidiaria
    _, pago_sub = _mk_proveedor_y_pago(subsidiaria, moneda_global, metodo_sub, cta_sub, referencia="REF-SUB")
    r_lote_sub = client.post(
        "/api/banca-electronica/lotes-pago/generar-proveedores/",
        {
            "id_cuenta_bancaria": str(cta_sub.pk),
            "pagos_ids": [str(pago_sub.pk)],
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
        },
        format="json",
    )
    assert r_lote_sub.status_code == 201
    assert str(r_lote_sub.data["id_empresa"]) == str(subsidiaria.pk)


# ── 6. RLS PostgreSQL en banca_electronica_lote_pago ─────────────────────────


def test_rls_banca_electronica_lote_pago(empresa_a, empresa_b, rls_test_role):
    moneda = _mk_moneda_global("USD")
    rls.apply_system_default()
    cta_a = _mk_cuenta(empresa_a, moneda)
    cta_b = _mk_cuenta(empresa_b, moneda)
    lote_a = LotePagoBancario.objects.create(
        id_empresa=empresa_a,
        id_cuenta_bancaria=cta_a,
        tipo_lote="PROVEEDORES",
        formato_banco="BANESCO_TXT",
        referencia_lote="RLS-A",
        fecha_valor=date.today(),
    )
    lote_b = LotePagoBancario.objects.create(
        id_empresa=empresa_b,
        id_cuenta_bancaria=cta_b,
        tipo_lote="PROVEEDORES",
        formato_banco="BANESCO_TXT",
        referencia_lote="RLS-B",
        fecha_valor=date.today(),
    )
    if rls_test_role is not None:
        with connection.cursor() as cur:
            cur.execute(f'SET ROLE "{rls_test_role}"')
    try:
        rls.apply_context([empresa_a.id_empresa], bypass=False)
        assert set(LotePagoBancario.objects.values_list("pk", flat=True)) == {lote_a.pk}

        rls.apply_context([empresa_b.id_empresa], bypass=False)
        assert set(LotePagoBancario.objects.values_list("pk", flat=True)) == {lote_b.pk}

        rls.apply_context([], bypass=False)
        assert LotePagoBancario.objects.count() == 0

        rls.apply_context([empresa_a.id_empresa], bypass=False)
        with pytest.raises((IntegrityError, ProgrammingError)):
            with transaction.atomic():
                LotePagoBancario.objects.create(
                    id_empresa=empresa_b,
                    id_cuenta_bancaria=cta_b,
                    tipo_lote="PROVEEDORES",
                    formato_banco="BANESCO_TXT",
                    referencia_lote="RLS-INTRUSION",
                    fecha_valor=date.today(),
                )
    finally:
        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute("RESET ROLE")
        rls.apply_system_default()


# ── 7. MCP Tools & FastMCP discovery ─────────────────────────────────────────


def test_mcp_banca_electronica_registro_y_ejecucion(empresa_a, empresa_b):
    tool_names = {t.name for t in mcp._tool_manager.list_tools()}
    assert {"banca_validar_referencia", "banca_listar_lotes_pago"}.issubset(tool_names)

    moneda = _mk_moneda_global("USD")
    metodo = _mk_metodo()
    cta_a = _mk_cuenta(empresa_a, moneda)
    _mk_proveedor_y_pago(empresa_a, moneda, metodo, cta_a, referencia="REF-MCP-1")
    LotePagoBancario.objects.create(
        id_empresa=empresa_a,
        id_cuenta_bancaria=cta_a,
        tipo_lote="PROVEEDORES",
        formato_banco="GENERICO_CSV",
        referencia_lote="MCP-LOTE-1",
        fecha_valor=date.today(),
        estado="GENERADO",
        total_registros=1,
        monto_total=Decimal("125.00"),
    )

    tok_read = CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="tok-banca-read",
        scopes=["banca_electronica:read"],
        activo=True,
    )
    tok_otro_scope = CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="tok-crm",
        scopes=["crm:read"],
        activo=True,
    )

    res_ref = banca_validar_referencia(
        str(tok_read.token),
        str(empresa_a.pk),
        str(cta_a.pk),
        "ref-mcp-1",
    )
    assert res_ref["duplicada"] is True
    assert res_ref["referencia_normalizada"] == "REF-MCP-1"

    res_lotes = banca_listar_lotes_pago(
        str(tok_read.token),
        str(empresa_a.pk),
        tipo_lote="PROVEEDORES",
        estado="GENERADO",
    )
    assert len(res_lotes) == 1
    assert res_lotes[0]["monto_total"] == "125.00"
    assert isinstance(res_lotes[0]["monto_total"], str)

    # Denegar scope faltante o cross-tenant
    with pytest.raises(PermissionError):
        banca_validar_referencia(str(tok_otro_scope.token), str(empresa_a.pk), str(cta_a.pk), "REF-MCP-1")

    with pytest.raises(PermissionError):
        banca_listar_lotes_pago(str(tok_read.token), str(empresa_b.pk))

    # Denegar bytes NUL en parámetros MCP sin tocar PostgreSQL
    assert "error" in banca_validar_referencia(str(tok_read.token), str(empresa_a.pk), "", "REF\x00BAD")
    assert "error" in banca_listar_lotes_pago(str(tok_read.token), str(empresa_a.pk), tipo_lote="PROV\x00")
    assert "error" in banca_listar_lotes_pago(str(tok_read.token), str(empresa_a.pk), estado="GEN\x00")

    # Cuenta inexistente / ajena y consulta global sin cuenta_bancaria_id
    res_err = banca_validar_referencia(str(tok_read.token), str(empresa_a.pk), str(uuid.uuid4()), "REF-MCP-1")
    assert "error" in res_err
    res_global = banca_validar_referencia(str(tok_read.token), str(empresa_a.pk), "", "REF-MCP-1")
    assert res_global["duplicada"] is True


# ── 8. Cobertura exhaustiva de bordes (servicios, serializers, views) ─────────


def test_servicios_y_modelos_edge_cases(empresa_a, empresa_b, user_a):
    from rest_framework.exceptions import ValidationError as DRFValidationError
    from rest_framework.test import APIRequestFactory

    from apps.banca_electronica.services import _formatear_archivo_lote, _resolver_proveedor_de_pago

    moneda = _mk_moneda_global("USD")
    metodo = _mk_metodo()
    cta_a = _mk_cuenta(empresa_a, moneda)
    cta_inactiva = _mk_cuenta(empresa_a, moneda, activo=False)
    cta_b = _mk_cuenta(empresa_b, moneda)

    # __str__ de modelos
    lote_str_obj = LotePagoBancario(
        id_empresa=empresa_a,
        id_cuenta_bancaria=cta_a,
        tipo_lote="PROVEEDORES",
        formato_banco="BANESCO_TXT",
        referencia_lote="STR-01",
        fecha_valor=date.today(),
        estado="GENERADO",
    )
    assert "STR-01" in str(lote_str_obj)
    det_str_obj = DetalleLotePagoBancario(
        id_lote_pago=lote_str_obj,
        beneficiario_nombre="Benef",
        beneficiario_identificacion="J-1",
        cuenta_destino="01340001010123456789",
        monto=Decimal("10.00"),
    )
    assert "Benef" in str(det_str_obj)

    # validar_referencia_bancaria sin cuenta_bancaria
    prov_a, pago_a = _mk_proveedor_y_pago(empresa_a, moneda, metodo, cta_a, referencia="REF-EDGE-1")
    assert validar_referencia_bancaria(empresa=empresa_a, cuenta_bancaria=None, referencia="REF-EDGE-1")["duplicada"]

    # _formatear_archivo_lote formato inválido
    with pytest.raises(BancaElectronicaError):
        _formatear_archivo_lote(
            formato_banco="OTRO",
            tipo_lote="PROVEEDORES",
            referencia_lote="X",
            fecha_valor=date.today(),
            cuenta_origen=cta_a.numero_cuenta,
            detalles=[],
            monto_total=Decimal("0.00"),
        )

    # Cuenta origen inexistente / inactiva / formato / lista vacía / duplicada / monto <= 0
    with pytest.raises(BancaElectronicaError):
        generar_lote_pagos_proveedores(
            empresa=empresa_a,
            cuenta_bancaria=cta_b,
            pagos_ids=[pago_a.pk],
            formato_banco="BANESCO_TXT",
            fecha_valor=date.today(),
            usuario=user_a,
        )
    with pytest.raises(BancaElectronicaError, match="inactiva"):
        generar_lote_pagos_proveedores(
            empresa=empresa_a,
            cuenta_bancaria=cta_inactiva,
            pagos_ids=[pago_a.pk],
            formato_banco="BANESCO_TXT",
            fecha_valor=date.today(),
            usuario=user_a,
        )
    with pytest.raises(BancaElectronicaError):
        generar_lote_pagos_proveedores(
            empresa=empresa_a,
            cuenta_bancaria=cta_a,
            pagos_ids=[pago_a.pk],
            formato_banco="INVALIDO",
            fecha_valor=date.today(),
            usuario=user_a,
        )
    with pytest.raises(BancaElectronicaError):
        generar_lote_pagos_proveedores(
            empresa=empresa_a,
            cuenta_bancaria=cta_a,
            pagos_ids=[],
            formato_banco="BANESCO_TXT",
            fecha_valor=date.today(),
            usuario=user_a,
        )
    with pytest.raises(BancaElectronicaError):
        generar_lote_pagos_proveedores(
            empresa=empresa_a,
            cuenta_bancaria=cta_a,
            pagos_ids=[pago_a.pk, pago_a.pk],
            formato_banco="BANESCO_TXT",
            fecha_valor=date.today(),
            usuario=user_a,
        )

    pago_cero = Pago.objects.create(
        id_empresa=empresa_a,
        tipo_operacion="EGRESO",
        tipo_documento="AJUSTE",
        fecha_pago=timezone.now(),
        monto=Decimal("0.00"),
        id_moneda=moneda,
        id_metodo_pago=metodo,
    )
    with pytest.raises(BancaElectronicaError, match="monto mayor a cero"):
        generar_lote_pagos_proveedores(
            empresa=empresa_a,
            cuenta_bancaria=cta_a,
            pagos_ids=[pago_cero.pk],
            formato_banco="GENERICO_CSV",
            fecha_valor=date.today(),
            usuario=user_a,
        )

    # _resolver_proveedor_de_pago via id_cxp (sin contacto proveedor) y via FacturaCompra -> OrdenCompra
    contacto_suelto = Contacto.objects.create(id_empresa=empresa_a, nombre="Contacto Suelto", rif="V-10101010")
    pago_sin_prov = Pago.objects.create(
        id_empresa=empresa_a,
        id_contacto=contacto_suelto,
        tipo_operacion="EGRESO",
        tipo_documento="AJUSTE",
        fecha_pago=timezone.now(),
        monto=Decimal("25.00"),
        id_moneda=moneda,
        id_metodo_pago=metodo,
    )
    assert _resolver_proveedor_de_pago(pago_sin_prov, empresa_a) is None

    cxp_solo = CuentaPorPagar.objects.create(
        id_empresa=empresa_a,
        id_proveedor=prov_a,
        fecha_emision=date.today(),
        fecha_vencimiento=date.today(),
        monto_total=Decimal("40.00"),
        monto_pendiente=Decimal("40.00"),
    )
    pago_via_cxp = Pago.objects.create(
        id_empresa=empresa_a,
        id_contacto=contacto_suelto,
        tipo_operacion="EGRESO",
        tipo_documento="CXP",
        id_documento=cxp_solo.pk,
        id_cxp=cxp_solo,
        fecha_pago=timezone.now(),
        monto=Decimal("40.00"),
        id_moneda=moneda,
        id_metodo_pago=metodo,
    )
    assert _resolver_proveedor_de_pago(pago_via_cxp, empresa_a) == prov_a

    oc = OrdenCompra.objects.create(
        id_empresa=empresa_a,
        id_proveedor=prov_a,
        numero_orden="OC-EDGE-1",
        fecha_orden=date.today(),
    )
    fc = FacturaCompra.objects.create(
        id_empresa=empresa_a,
        id_orden_compra=oc,
        numero_factura="FC-EDGE-1",
        fecha_emision=date.today(),
        monto_total=Decimal("30.00"),
    )
    pago_via_fc = Pago.objects.create(
        id_empresa=empresa_a,
        tipo_operacion="EGRESO",
        tipo_documento="AJUSTE",
        fecha_pago=timezone.now(),
        monto=Decimal("30.00"),
        id_moneda=moneda,
        id_metodo_pago=metodo,
    )
    AsignacionPago.objects.create(
        id_empresa=empresa_a,
        id_contacto=contacto_suelto,
        id_pago=pago_via_fc,
        tipo_documento="FACTURA_COMPRA",
        id_documento=str(fc.pk),
        id_factura_compra=fc,
        id_moneda_documento=moneda,
        monto_asignado_pago=Decimal("30.00"),
        monto_asignado_documento=Decimal("30.00"),
    )
    assert _resolver_proveedor_de_pago(pago_via_fc, empresa_a) == prov_a

    # Sin cuenta asociada -> error, cuenta vacía / inválida TXT -> error, contacto/ninguno con override -> OK
    with pytest.raises(BancaElectronicaError, match="no tiene cuenta"):
        generar_lote_pagos_proveedores(
            empresa=empresa_a,
            cuenta_bancaria=cta_a,
            pagos_ids=[pago_sin_prov.pk],
            formato_banco="GENERICO_CSV",
            fecha_valor=date.today(),
            usuario=user_a,
        )
    with pytest.raises(BancaElectronicaError, match="inválida"):
        generar_lote_pagos_proveedores(
            empresa=empresa_a,
            cuenta_bancaria=cta_a,
            pagos_ids=[pago_sin_prov.pk],
            formato_banco="BANESCO_TXT",
            fecha_valor=date.today(),
            usuario=user_a,
            cuentas_destino_override={str(pago_sin_prov.pk): "123"},
        )
    lote_ref_dup = generar_lote_pagos_proveedores(
        empresa=empresa_a,
        cuenta_bancaria=cta_a,
        pagos_ids=[pago_sin_prov.pk, pago_via_fc.pk],
        formato_banco="GENERICO_CSV",
        fecha_valor=date.today(),
        usuario=user_a,
        referencia_lote="REF-UNICA-EDGE",
        cuentas_destino_override={str(pago_sin_prov.pk): "CUENTA-EXT-1"},
    )
    assert lote_ref_dup.total_registros == 2
    with pytest.raises(BancaElectronicaError, match="Ya existe un lote"):
        generar_lote_pagos_proveedores(
            empresa=empresa_a,
            cuenta_bancaria=cta_a,
            pagos_ids=[pago_via_cxp.pk],
            formato_banco="GENERICO_CSV",
            fecha_valor=date.today(),
            usuario=user_a,
            referencia_lote="REF-UNICA-EDGE",
        )

    # Nómina edge cases: formato inválido, sin nóminas > 0, empleado sin cuenta, estado/lote inexistente
    periodo = PeriodoNomina.objects.create(
        id_empresa=empresa_a,
        nombre_periodo="Q2 Edge",
        tipo_periodo="QUINCENAL",
        fecha_inicio=date.today(),
        fecha_fin=date.today(),
        fecha_pago=date.today(),
    )
    proc_vacio = ProcesoNomina.objects.create(
        id_empresa=empresa_a,
        id_periodo_nomina=periodo,
        numero_proceso="PROC-VACIO",
        fecha_proceso=timezone.now(),
        estado="COMPLETADO",
    )
    with pytest.raises(BancaElectronicaError):
        generar_lote_pagos_nomina(
            empresa=empresa_a,
            cuenta_bancaria=cta_a,
            proceso_nomina=proc_vacio,
            formato_banco="NO_VALIDO",
            fecha_valor=date.today(),
            usuario=user_a,
        )
    with pytest.raises(BancaElectronicaError, match="neto a pagar"):
        generar_lote_pagos_nomina(
            empresa=empresa_a,
            cuenta_bancaria=cta_a,
            proceso_nomina=proc_vacio,
            formato_banco="BANESCO_TXT",
            fecha_valor=date.today(),
            usuario=user_a,
        )
    emp_sin_cta = Empleado.objects.create(
        empresa=empresa_a, nombre="Sin", apellido="Cuenta", cedula="V-999999", fecha_ingreso=date.today()
    )
    Nomina.objects.create(
        id_proceso_nomina=proc_vacio,
        id_empleado=emp_sin_cta,
        sueldo_base=Decimal("100.00"),
        total_neto=Decimal("100.00"),
        fecha_calculo=timezone.now(),
    )
    with pytest.raises(BancaElectronicaError, match="no tiene cuenta"):
        generar_lote_pagos_nomina(
            empresa=empresa_a,
            cuenta_bancaria=cta_a,
            proceso_nomina=proc_vacio,
            formato_banco="BANESCO_TXT",
            fecha_valor=date.today(),
            usuario=user_a,
        )
    with pytest.raises(BancaElectronicaError):
        cambiar_estado_lote(uuid.uuid4(), "ENVIADO", user_a)
    with pytest.raises(BancaElectronicaError):
        cambiar_estado_lote(lote_ref_dup, "ESTADO_FALSO", user_a)

    # Serializer CuentaBancariaEmpresaSerializer edge cases (finanzas/serializers.py)
    sub = Empresa.objects.create(
        nombre_legal="Sub Finanzas",
        identificador_fiscal=f"J-{uuid.uuid4().hex[:8]}",
        id_moneda_base=moneda,
        empresa_matriz=empresa_a,
    )
    moneda_priv_a = Moneda.objects.create(
        codigo_iso="PXA",
        nombre="Privada A",
        simbolo="P",
        es_generica=False,
        es_publica=False,
        empresa=empresa_a,
    )
    req = APIRequestFactory().post("/")
    req.user = user_a

    # Cambiar id_empresa en PATCH hacia subsidiaria visible
    ser_patch = CuentaBancariaEmpresaSerializer(
        instance=cta_a,
        data={"id_empresa": str(sub.pk)},
        partial=True,
        context={"request": req},
    )
    assert not ser_patch.is_valid()
    assert "id_empresa" in ser_patch.errors

    # Empresa no visible directamente en serializer
    ser_no_vis = CuentaBancariaEmpresaSerializer(
        data={
            "id_empresa": str(empresa_b.pk),
            "nombre_banco": "B",
            "numero_cuenta": "0134-UNVIS-1",
            "tipo_cuenta": "CORRIENTE",
            "id_moneda": str(moneda.pk),
        },
        context={"request": req},
    )
    assert not ser_no_vis.is_valid()

    # Moneda privada de matriz cuando cuenta es de subsidiaria -> rechaza
    ser_mon_mismatch = CuentaBancariaEmpresaSerializer(
        data={
            "id_empresa": str(sub.pk),
            "nombre_banco": "B",
            "numero_cuenta": "0134-MON-MIS",
            "tipo_cuenta": "CORRIENTE",
            "id_moneda": str(moneda_priv_a.pk),
        },
        context={"request": req},
    )
    assert not ser_mon_mismatch.is_valid()

    # M2M monedas privadas fuera de empresa efectiva -> rechaza; global -> acepta
    ser_mons_bad = CuentaBancariaEmpresaSerializer(
        data={
            "id_empresa": str(sub.pk),
            "nombre_banco": "B",
            "numero_cuenta": "0134-MONS-BAD",
            "tipo_cuenta": "CORRIENTE",
            "id_moneda": str(moneda.pk),
            "monedas": [str(moneda_priv_a.pk)],
        },
        context={"request": req},
    )
    assert not ser_mons_bad.is_valid()

    # numero_cuenta solo espacios -> error; numero_cuenta con espacios duplicando cta_a -> error
    ser_num_blank = CuentaBancariaEmpresaSerializer(
        data={
            "id_empresa": str(empresa_a.pk),
            "nombre_banco": "B",
            "numero_cuenta": "   ",
            "tipo_cuenta": "CORRIENTE",
            "id_moneda": str(moneda.pk),
        },
        context={"request": req},
    )
    assert not ser_num_blank.is_valid()

    ser_num_dup = CuentaBancariaEmpresaSerializer(
        data={
            "id_empresa": str(empresa_a.pk),
            "nombre_banco": "B",
            "numero_cuenta": f" {cta_a.numero_cuenta} ",
            "tipo_cuenta": "CORRIENTE",
            "id_moneda": str(moneda.pk),
        },
        context={"request": req},
    )
    assert not ser_num_dup.is_valid()

    # saldo_actual no finito directo en validate()
    ser_nan = CuentaBancariaEmpresaSerializer(context={"request": req})
    ser_nan._validated_data = {}
    with pytest.raises(DRFValidationError):
        ser_nan.validate({"id_empresa": empresa_a, "saldo_actual": Decimal("NaN")})


def test_serializers_y_endpoints_cobertura_borde(empresa_a, empresa_b, user_a):
    moneda = _mk_moneda_global("USD")
    metodo = _mk_metodo()
    cta_a = _mk_cuenta(empresa_a, moneda)
    cta_b = _mk_cuenta(empresa_b, moneda)
    _, pago_a = _mk_proveedor_y_pago(empresa_a, moneda, metodo, cta_a, referencia="REF-COV-1")
    _, pago_b = _mk_proveedor_y_pago(empresa_b, moneda, metodo, cta_b, referencia="REF-COV-B")
    _, pago_ingreso = _mk_proveedor_y_pago(
        empresa_a, moneda, metodo, cta_a, tipo_operacion="INGRESO", referencia="REF-ING-COV"
    )

    periodo = PeriodoNomina.objects.create(
        id_empresa=empresa_a,
        nombre_periodo="Nom REST",
        tipo_periodo="QUINCENAL",
        fecha_inicio=date.today(),
        fecha_fin=date.today(),
        fecha_pago=date.today(),
    )
    proc_ok = ProcesoNomina.objects.create(
        id_empresa=empresa_a,
        id_periodo_nomina=periodo,
        numero_proceso="PROC-REST-1",
        fecha_proceso=timezone.now(),
        estado="COMPLETADO",
    )
    emp = Empleado.objects.create(
        empresa=empresa_a, nombre="Carlos", apellido="Ruiz", cedula="V-555555", fecha_ingreso=date.today()
    )
    Nomina.objects.create(
        id_proceso_nomina=proc_ok,
        id_empleado=emp,
        sueldo_base=Decimal("300.00"),
        total_neto=Decimal("300.00"),
        fecha_calculo=timezone.now(),
    )
    proc_en_proc = ProcesoNomina.objects.create(
        id_empresa=empresa_a,
        id_periodo_nomina=periodo,
        numero_proceso="PROC-REST-ENCURSO",
        fecha_proceso=timezone.now(),
        estado="EN_PROCESO",
    )
    proc_b = ProcesoNomina.objects.create(
        id_empresa=empresa_b,
        id_periodo_nomina=PeriodoNomina.objects.create(
            id_empresa=empresa_b,
            nombre_periodo="Nom B",
            tipo_periodo="QUINCENAL",
            fecha_inicio=date.today(),
            fecha_fin=date.today(),
            fecha_pago=date.today(),
        ),
        numero_proceso="PROC-B",
        fecha_proceso=timezone.now(),
        estado="COMPLETADO",
    )

    client = _client_para(user_a)

    # generar-proveedores errores de serializer y BancaElectronicaError via REST
    for bad_payload in (
        {
            "id_cuenta_bancaria": str(uuid.uuid4()),
            "pagos_ids": [str(pago_a.pk)],
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
        },
        {
            "id_empresa": str(empresa_b.pk),
            "id_cuenta_bancaria": str(cta_a.pk),
            "pagos_ids": [str(pago_a.pk)],
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
        },
        {
            "id_cuenta_bancaria": str(cta_b.pk),
            "pagos_ids": [str(pago_b.pk)],
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
        },
        {
            "id_empresa": str(empresa_a.pk),
            "id_cuenta_bancaria": str(cta_a.pk),
            "pagos_ids": [str(uuid.uuid4())],
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
        },
        {
            "id_cuenta_bancaria": str(cta_a.pk),
            "pagos_ids": [str(pago_a.pk)],
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
            "cuentas_destino_override": {str(uuid.uuid4()): "01340001010123456789"},
        },
        {
            "id_cuenta_bancaria": str(cta_a.pk),
            "pagos_ids": [str(pago_ingreso.pk)],
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
        },
    ):
        assert (
            client.post(
                "/api/banca-electronica/lotes-pago/generar-proveedores/", bad_payload, format="json"
            ).status_code
            == 400
        )

    # generar-nomina validaciones y exito REST
    for bad_nom in (
        {
            "id_cuenta_bancaria": str(cta_a.pk),
            "id_proceso_nomina": str(uuid.uuid4()),
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
        },
        {
            "id_cuenta_bancaria": str(cta_a.pk),
            "id_proceso_nomina": str(proc_b.pk),
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
        },
        {
            "id_cuenta_bancaria": str(cta_a.pk),
            "id_proceso_nomina": str(proc_ok.pk),
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
            "cuentas_empleados": {"999999": "01340001010123456789"},
        },
        {
            "id_cuenta_bancaria": str(cta_a.pk),
            "id_proceso_nomina": str(proc_en_proc.pk),
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
        },
    ):
        assert (
            client.post("/api/banca-electronica/lotes-pago/generar-nomina/", bad_nom, format="json").status_code == 400
        )

    r_nom_ok = client.post(
        "/api/banca-electronica/lotes-pago/generar-nomina/",
        {
            "id_empresa": str(empresa_a.pk),
            "id_cuenta_bancaria": str(cta_a.pk),
            "id_proceso_nomina": str(proc_ok.pk),
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
            "cuentas_empleados": {str(emp.pk): "01340001010123456789"},
        },
        format="json",
    )
    assert r_nom_ok.status_code == 201
    lote_nom_id = r_nom_ok.data["id_lote_pago"]

    # Filtros ?tipo_lote= & ?estado= y errores de transición + anular 200
    assert client.get("/api/banca-electronica/lotes-pago/?tipo_lote=NOMINA&estado=GENERADO").data["count"] == 1
    assert (
        client.post(
            f"/api/banca-electronica/lotes-pago/{lote_nom_id}/marcar-procesado/", {}, format="json"
        ).status_code
        == 400
    )
    assert (
        client.post(f"/api/banca-electronica/lotes-pago/{lote_nom_id}/anular/", {}, format="json").status_code == 200
    )
    assert (
        client.post(f"/api/banca-electronica/lotes-pago/{lote_nom_id}/marcar-enviado/", {}, format="json").status_code
        == 400
    )

    # validar-referencia bordes REST
    assert (
        client.post("/api/banca-electronica/validar-referencia/", {"referencia": "REF-COV-1"}, format="json").data[
            "duplicada"
        ]
        is True
    )
    assert (
        client.post(
            "/api/banca-electronica/validar-referencia/",
            {"id_empresa": str(empresa_a.pk), "referencia": "REF-COV-1", "excluir_pago_id": str(pago_a.pk)},
            format="json",
        ).data["duplicada"]
        is False
    )
    assert (
        client.post(
            "/api/banca-electronica/validar-referencia/",
            {"id_empresa": str(empresa_a.pk), "referencia": "REF-COV-1", "excluir_pago_id": str(pago_b.pk)},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/banca-electronica/validar-referencia/",
            {"id_cuenta_bancaria": str(uuid.uuid4()), "referencia": "X"},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/banca-electronica/validar-referencia/",
            {"id_empresa": str(empresa_b.pk), "referencia": "X"},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/banca-electronica/validar-referencia/",
            {"id_empresa": str(empresa_a.pk), "referencia": "   "},
            format="json",
        ).status_code
        == 400
    )


def test_ronda2_race_referencia_cero_oraculo_y_filtros_pagos(empresa_a, empresa_b, user_a):
    from unittest.mock import patch

    moneda = _mk_moneda_global("USD")
    metodo = _mk_metodo()
    cta_a = _mk_cuenta(empresa_a, moneda)
    cta_b = _mk_cuenta(empresa_b, moneda)
    _, pago_a = _mk_proveedor_y_pago(empresa_a, moneda, metodo, cta_a, referencia="REF-RACE-1")
    _, pago_a2 = _mk_proveedor_y_pago(empresa_a, moneda, metodo, cta_a, referencia="REF-RACE-2")
    _, pago_ing = _mk_proveedor_y_pago(
        empresa_a, moneda, metodo, cta_a, tipo_operacion="INGRESO", referencia="REF-ING-1"
    )
    _, pago_b = _mk_proveedor_y_pago(empresa_b, moneda, metodo, cta_b, referencia="REF-RACE-B")
    proc_b = ProcesoNomina.objects.create(
        id_empresa=empresa_b,
        id_periodo_nomina=PeriodoNomina.objects.create(
            id_empresa=empresa_b,
            nombre_periodo="Nom R2 B",
            tipo_periodo="QUINCENAL",
            fecha_inicio=date.today(),
            fecha_fin=date.today(),
            fecha_pago=date.today(),
        ),
        numero_proceso="PROC-R2-B",
        fecha_proceso=timezone.now(),
        estado="COMPLETADO",
    )

    client = _client_para(user_a)

    # [BLOQUEANTE #1] Race condition en unicidad (id_empresa, referencia_lote)
    lote_existente = generar_lote_pagos_proveedores(
        empresa=empresa_a,
        cuenta_bancaria=cta_a,
        pagos_ids=[pago_a.pk],
        formato_banco="BANESCO_TXT",
        fecha_valor=date.today(),
        usuario=user_a,
        referencia_lote="LOTE-RACE-EXISTE",
    )

    # 1a) Colisión concurrente con referencia explícita -> BancaElectronicaError / REST 400 (no 500)
    with patch(
        "apps.banca_electronica.services._resolver_referencia_lote", return_value=lote_existente.referencia_lote
    ):
        resp_dup = client.post(
            "/api/banca-electronica/lotes-pago/generar-proveedores/",
            {
                "id_cuenta_bancaria": str(cta_a.pk),
                "pagos_ids": [str(pago_a2.pk)],
                "formato_banco": "BANESCO_TXT",
                "fecha_valor": "2026-11-20",
                "referencia_lote": "LOTE-RACE-EXISTE",
            },
            format="json",
        )
    assert resp_dup.status_code == 400

    # 1b) Colisión concurrente con referencia autogenerada -> reintenta y crea exitosamente
    ref_retry = f"LOTE-RETRY-{uuid.uuid4().hex[:8].upper()}"
    with patch(
        "apps.banca_electronica.services._resolver_referencia_lote",
        side_effect=[lote_existente.referencia_lote, ref_retry],
    ):
        lote_retry = generar_lote_pagos_proveedores(
            empresa=empresa_a,
            cuenta_bancaria=cta_a,
            pagos_ids=[pago_a2.pk],
            formato_banco="BANESCO_TXT",
            fecha_valor=date.today(),
            usuario=user_a,
        )
    assert lote_retry.referencia_lote == ref_retry
    assert lote_retry.total_registros == 1

    # 1c) Agota 5 reintentos autogenerados -> BancaElectronicaError limpia
    _, pago_a3 = _mk_proveedor_y_pago(empresa_a, moneda, metodo, cta_a, referencia="REF-RACE-3")
    with patch(
        "apps.banca_electronica.services._resolver_referencia_lote",
        side_effect=[lote_existente.referencia_lote] * 5,
    ):
        with pytest.raises(BancaElectronicaError, match="reintentos"):
            generar_lote_pagos_proveedores(
                empresa=empresa_a,
                cuenta_bancaria=cta_a,
                pagos_ids=[pago_a3.pk],
                formato_banco="BANESCO_TXT",
                fecha_valor=date.today(),
                usuario=user_a,
            )

    # [BLOQUEANTE #2] Cero oráculo de existencia cross-tenant en validar-referencia y lotes
    r_excluir_ajeno = client.post(
        "/api/banca-electronica/validar-referencia/",
        {"id_empresa": str(empresa_a.pk), "referencia": "REF-RACE-1", "excluir_pago_id": str(pago_b.pk)},
        format="json",
    )
    r_excluir_random = client.post(
        "/api/banca-electronica/validar-referencia/",
        {"id_empresa": str(empresa_a.pk), "referencia": "REF-RACE-1", "excluir_pago_id": str(uuid.uuid4())},
        format="json",
    )
    assert r_excluir_ajeno.status_code == 400
    assert r_excluir_random.status_code == 400
    assert r_excluir_ajeno.data == r_excluir_random.data

    r_cta_ajena = client.post(
        "/api/banca-electronica/validar-referencia/",
        {"id_cuenta_bancaria": str(cta_b.pk), "referencia": "REF-RACE-B"},
        format="json",
    )
    r_cta_random = client.post(
        "/api/banca-electronica/validar-referencia/",
        {"id_cuenta_bancaria": str(uuid.uuid4()), "referencia": "REF-RACE-B"},
        format="json",
    )
    assert r_cta_ajena.status_code == 400
    assert r_cta_random.status_code == 400
    assert r_cta_ajena.data == r_cta_random.data

    r_proc_ajeno = client.post(
        "/api/banca-electronica/lotes-pago/generar-nomina/",
        {
            "id_cuenta_bancaria": str(cta_a.pk),
            "id_proceso_nomina": str(proc_b.pk),
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
        },
        format="json",
    )
    r_proc_random = client.post(
        "/api/banca-electronica/lotes-pago/generar-nomina/",
        {
            "id_cuenta_bancaria": str(cta_a.pk),
            "id_proceso_nomina": str(uuid.uuid4()),
            "formato_banco": "BANESCO_TXT",
            "fecha_valor": "2026-11-20",
        },
        format="json",
    )
    assert r_proc_ajeno.status_code == 400
    assert r_proc_random.status_code == 400
    assert r_proc_ajeno.data == r_proc_random.data

    # [MENOR #3] PagoViewSet ?tipo_operacion= y ?id_empresa=
    r_pagos_egreso = client.get(f"/api/finanzas/pagos/?tipo_operacion=EGRESO&id_empresa={empresa_a.pk}")
    assert r_pagos_egreso.status_code == 200
    ids_ret = {row["id_pago"] for row in r_pagos_egreso.data["results"]}
    assert str(pago_a.pk) in ids_ret
    assert str(pago_ing.pk) not in ids_ret
    assert str(pago_b.pk) not in ids_ret
    assert client.get(f"/api/finanzas/pagos/?empresa={empresa_b.pk}").data["count"] == 0
    assert client.get("/api/finanzas/pagos/?tipo_operacion=OTRO").status_code == 400
    assert client.get("/api/finanzas/pagos/?id_empresa=no-uuid").status_code == 400
