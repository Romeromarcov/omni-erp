"""Tests de integración para diarios contables, secuencias atómicas, contra-asientos,
trazabilidad por contacto y períodos/cierre de ejercicio (PR-13 · B1).
"""

from __future__ import annotations

import datetime
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import connections
from django.utils import timezone

from apps.compras.models import FacturaCompra, OrdenCompra, RecepcionMercancia
from apps.contabilidad.models import (
    AsientoContable,
    DetalleAsiento,
    DiarioContable,
    MapeoContable,
    PeriodoContable,
    PlanCuentas,
)
from apps.contabilidad.services import (
    AsientoError,
    PeriodoContableCerradoError,
    _resolver_contacto_documento_asiento,
    aprobar_asiento,
    cerrar_ejercicio_contable,
    cerrar_periodo_contable,
    generar_asiento,
    generar_asiento_o_fallar,
    reabrir_periodo_contable,
    revertir_asiento,
)
from apps.core.models import Contacto
from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar
from apps.cuentas_por_pagar.models import AbonoCxP, CuentaPorPagar, DiferenciaCambiaria
from apps.finanzas.models import AsignacionPago, Pago
from apps.finanzas.services_conciliacion_pagos import (
    ConciliacionContableError,
    aplicar_pago_a_documentos,
    revertir_asignacion_pago,
)
from apps.fiscal.models import PeriodoFiscal
from apps.gastos.models import CategoriaGasto, Gasto
from apps.proveedores.models import Proveedor
from apps.ventas.models import FacturaFiscal

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _cuenta(empresa, codigo: str, nombre: str, tipo: str = "ACTIVO", naturaleza: str = "DEUDORA") -> PlanCuentas:
    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=nombre,
        tipo_cuenta=tipo,
        naturaleza=naturaleza,
        nivel=2,
    )


def _mapeo(
    empresa, tipo: str, debe: PlanCuentas, haber: PlanCuentas, diario: DiarioContable | None = None
) -> MapeoContable:
    return MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento=tipo,
        id_diario=diario,
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla="{tipo} - {numero}",
        activo=True,
    )


def _asiento_manual(
    empresa,
    cuenta_debe: PlanCuentas,
    cuenta_haber: PlanCuentas,
    monto: Decimal,
    *,
    fecha: datetime.date | None = None,
    estado: str = "APROBADO",
    diario: DiarioContable | None = None,
    contacto: Contacto | None = None,
) -> AsientoContable:
    asiento = AsientoContable.objects.create(
        id_empresa=empresa,
        id_diario=diario,
        fecha_asiento=fecha or timezone.localdate(),
        numero_asiento=f"MAN-{uuid.uuid4().hex[:8].upper()}",
        descripcion="Asiento manual test",
        estado_asiento=estado,
    )
    DetalleAsiento.objects.create(
        id_asiento=asiento,
        id_cuenta_contable=cuenta_debe,
        id_contacto=contacto,
        debe=monto,
        haber=Decimal("0.00"),
        descripcion_detalle="Línea debe",
    )
    DetalleAsiento.objects.create(
        id_asiento=asiento,
        id_cuenta_contable=cuenta_haber,
        id_contacto=contacto,
        debe=Decimal("0.00"),
        haber=monto,
        descripcion_detalle="Línea haber",
    )
    return asiento


class TestDiariosYSecuencias:
    def test_modo_sin_friccion_sin_diarios_ni_periodos(self, empresa_a):
        assert empresa_a.contabilidad_activa is False
        assert DiarioContable.objects.filter(id_empresa=empresa_a).count() == 0
        assert PeriodoContable.objects.filter(id_empresa=empresa_a).count() == 0

        doc = SimpleNamespace(pk=uuid.uuid4(), monto_total=Decimal("50.00"))
        asiento, err = generar_asiento_o_fallar("FACTURA_VENTA", doc, empresa=empresa_a)
        assert asiento is None
        assert err is not None

        c_debe = _cuenta(empresa_a, "1.1.01", "Caja")
        c_haber = _cuenta(empresa_a, "4.1.01", "Ventas", tipo="INGRESO", naturaleza="ACREEDORA")
        _mapeo(empresa_a, "FACTURA_VENTA", c_debe, c_haber, diario=None)

        asiento_ok = generar_asiento("FACTURA_VENTA", doc, empresa=empresa_a)
        assert asiento_ok.id_diario is None
        assert asiento_ok.numero_asiento.startswith("AST-FACT-")

    def test_resolucion_diario_mapeo_y_fallback_por_tipo_con_secuencia(self, empresa_a):
        c_debe = _cuenta(empresa_a, "1.1.02", "CxC")
        c_haber = _cuenta(empresa_a, "4.1.02", "Ventas Mercancía", tipo="INGRESO", naturaleza="ACREEDORA")
        diario_ventas = DiarioContable.objects.create(
            id_empresa=empresa_a,
            codigo="VTA",
            nombre="Diario de Ventas",
            tipo="VENTAS",
            prefijo_secuencia="FAC",
            siguiente_numero=1,
        )
        assert str(diario_ventas) == "VTA — Diario de Ventas"
        diario_compras = DiarioContable.objects.create(
            id_empresa=empresa_a,
            codigo="CMP",
            nombre="Diario de Compras",
            tipo="COMPRAS",
            prefijo_secuencia="CMP",
            siguiente_numero=10,
        )

        # Mapeo sin id_diario cae al primer diario activo del tipo correspondiente (VENTAS)
        _mapeo(empresa_a, "FACTURA_VENTA", c_debe, c_haber, diario=None)
        doc1 = SimpleNamespace(pk=uuid.uuid4(), monto_total=Decimal("100.00"))
        a1 = generar_asiento("FACTURA_VENTA", doc1, empresa=empresa_a)
        assert a1.id_diario_id == diario_ventas.pk
        assert a1.numero_asiento == "FAC-000001"

        # Pre-crear colisión manual FAC-000002 para verificar salto seguro al siguiente libre
        AsientoContable.objects.create(
            id_empresa=empresa_a,
            id_diario=diario_ventas,
            fecha_asiento=timezone.localdate(),
            numero_asiento="FAC-000002",
            descripcion="Manual colisión",
            estado_asiento="BORRADOR",
        )
        a2 = generar_asiento("FACTURA_VENTA", doc1, empresa=empresa_a)
        assert a2.numero_asiento == "FAC-000003"

        # Mapeo con id_diario explícito prevalece sobre el tipo
        _mapeo(empresa_a, "GASTO", c_debe, c_haber, diario=diario_compras)
        a3 = generar_asiento("GASTO", doc1, empresa=empresa_a)
        assert a3.id_diario_id == diario_compras.pk
        assert a3.numero_asiento == "CMP-000010"


@pytest.mark.django_db(transaction=True)
def test_secuencia_atomica_concurrente_sin_colisiones(empresa_a):
    c_debe = _cuenta(empresa_a, "1.1.03", "Banco")
    c_haber = _cuenta(empresa_a, "4.1.03", "Servicios", tipo="INGRESO", naturaleza="ACREEDORA")
    diario = DiarioContable.objects.create(
        id_empresa=empresa_a,
        codigo="VTA-CONC",
        nombre="Diario Concurrente",
        tipo="VENTAS",
        prefijo_secuencia="CONC",
        siguiente_numero=1,
    )
    _mapeo(empresa_a, "FACTURA_VENTA", c_debe, c_haber, diario=diario)

    def _worker(idx: int) -> str:
        try:
            doc = SimpleNamespace(pk=uuid.uuid4(), monto_total=Decimal("25.00"), numero_factura=f"F-{idx}")
            asiento = generar_asiento("FACTURA_VENTA", doc, empresa=empresa_a)
            return asiento.numero_asiento
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=4) as pool:
        numeros = list(pool.map(_worker, range(6)))

    assert sorted(numeros) == [
        "CONC-000001",
        "CONC-000002",
        "CONC-000003",
        "CONC-000004",
        "CONC-000005",
        "CONC-000006",
    ]
    diario.refresh_from_db()
    assert diario.siguiente_numero == 7


class TestTrazabilidadContacto:
    def test_puebla_id_contacto_desde_multiples_documentos_y_bloquea_ajenos(
        self, empresa_a, empresa_b, moneda_usd, metodo_efectivo, user_a
    ):
        c_debe = _cuenta(empresa_a, "1.1.10", "Caja Contacto")
        c_haber = _cuenta(empresa_a, "4.1.10", "Ingresos Contacto", tipo="INGRESO", naturaleza="ACREEDORA")
        for tipo in ("FACTURA_VENTA", "FACTURA_COMPRA", "GASTO", "PAGO_CXC", "PAGO_CXP", "GANANCIA_CAMBIARIA"):
            _mapeo(empresa_a, tipo, c_debe, c_haber)

        contacto_cli = Contacto.objects.create(
            id_empresa=empresa_a, nombre="Cliente Contacto", rif="J-10000001-1", es_cliente=True
        )
        contacto_prov = Contacto.objects.create(
            id_empresa=empresa_a, nombre="Proveedor Contacto", rif="J-20000002-2", es_proveedor=True
        )
        contacto_ajeno = Contacto.objects.create(
            id_empresa=empresa_b, nombre="Contacto Ajeno", rif="J-90000009-9", es_cliente=True
        )

        cliente = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cliente SA", rif="J-10000001-1", contacto=contacto_cli
        )
        cliente_ajeno = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cliente Cross", rif="J-10000003-3", contacto=contacto_ajeno
        )
        proveedor = Proveedor.objects.create(
            id_empresa=empresa_a, razon_social="Proveedor SA", rif="J-20000002-2", contacto=contacto_prov
        )

        factura_v = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_control="00-001",
            numero_factura="FV-CONT-1",
            fecha_emision=timezone.localdate(),
            monto_total=Decimal("100.00"),
            id_moneda=moneda_usd,
        )
        a_fv = generar_asiento("FACTURA_VENTA", factura_v, empresa=empresa_a)
        assert list(DetalleAsiento.objects.filter(id_asiento=a_fv).values_list("id_contacto_id", flat=True)) == [
            contacto_cli.pk,
            contacto_cli.pk,
        ]

        # Contacto de empresa_b nunca se asigna a asientos de empresa_a
        factura_cross = FacturaFiscal.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_ajeno,
            numero_control="00-002",
            numero_factura="FV-CONT-2",
            fecha_emision=timezone.localdate(),
            monto_total=Decimal("50.00"),
            id_moneda=moneda_usd,
        )
        a_cross = generar_asiento("FACTURA_VENTA", factura_cross, empresa=empresa_a)
        assert list(DetalleAsiento.objects.filter(id_asiento=a_cross).values_list("id_contacto_id", flat=True)) == [
            None,
            None,
        ]

        # Compra vía OrdenCompra -> Proveedor -> Contacto
        oc = OrdenCompra.objects.create(
            id_empresa=empresa_a, id_proveedor=proveedor, numero_orden="OC-CONT-1", fecha_orden=timezone.localdate()
        )
        fc = FacturaCompra.objects.create(
            id_empresa=empresa_a,
            id_orden_compra=oc,
            numero_factura="FC-CONT-1",
            fecha_emision=timezone.localdate(),
            monto_total=Decimal("80.00"),
        )
        a_fc = generar_asiento("FACTURA_COMPRA", fc, empresa=empresa_a)
        assert list(DetalleAsiento.objects.filter(id_asiento=a_fc).values_list("id_contacto_id", flat=True)) == [
            contacto_prov.pk,
            contacto_prov.pk,
        ]

        # Gasto -> Proveedor -> Contacto
        cat = CategoriaGasto.objects.create(id_empresa=empresa_a, nombre_categoria="Servicios")
        gasto = Gasto.objects.create(
            id_empresa=empresa_a,
            fecha_gasto=timezone.localdate(),
            descripcion="Internet",
            monto=Decimal("30.00"),
            id_moneda=moneda_usd,
            id_categoria_gasto=cat,
            id_proveedor=proveedor,
        )
        a_gasto = generar_asiento("GASTO", gasto, empresa=empresa_a)
        assert list(DetalleAsiento.objects.filter(id_asiento=a_gasto).values_list("id_contacto_id", flat=True)) == [
            contacto_prov.pk,
            contacto_prov.pk,
        ]

        # AbonoCxC, AbonoCxP, DiferenciaCambiaria y Pago
        cxc = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente,
            monto=Decimal("100.00"),
            fecha_emision=timezone.localdate(),
            fecha_vencimiento=timezone.localdate(),
        )
        abono_cxc = AbonoCxC.objects.create(cuenta_por_cobrar=cxc, monto=Decimal("40.00"), usuario=user_a)
        a_cxc = generar_asiento("PAGO_CXC", abono_cxc, empresa=empresa_a, monto=Decimal("40.00"))
        assert list(DetalleAsiento.objects.filter(id_asiento=a_cxc).values_list("id_contacto_id", flat=True)) == [
            contacto_cli.pk,
            contacto_cli.pk,
        ]

        cxp = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor,
            monto_total=Decimal("80.00"),
            monto_pendiente=Decimal("80.00"),
            fecha_emision=timezone.localdate(),
            fecha_vencimiento=timezone.localdate(),
        )
        abono_cxp = AbonoCxP.objects.create(cuenta_por_pagar=cxp, monto=Decimal("20.00"), usuario=user_a)
        a_cxp = generar_asiento("PAGO_CXP", abono_cxp, empresa=empresa_a, monto=Decimal("20.00"))
        assert list(DetalleAsiento.objects.filter(id_asiento=a_cxp).values_list("id_contacto_id", flat=True)) == [
            contacto_prov.pk,
            contacto_prov.pk,
        ]

        dif = DiferenciaCambiaria.objects.create(
            id_empresa=empresa_a,
            id_abono_cxp=abono_cxp,
            monto_moneda=Decimal("20.00"),
            tasa_original=Decimal("36.0"),
            tasa_pago=Decimal("35.0"),
            monto_diferencia=Decimal("20.00"),
            tipo="GANANCIA",
        )
        a_dif = generar_asiento("GANANCIA_CAMBIARIA", dif, empresa=empresa_a, monto=Decimal("20.00"))
        assert list(DetalleAsiento.objects.filter(id_asiento=a_dif).values_list("id_contacto_id", flat=True)) == [
            contacto_prov.pk,
            contacto_prov.pk,
        ]

        pago = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_cli,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("50.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        a_pago = generar_asiento("PAGO_CXC", pago, empresa=empresa_a, monto=Decimal("50.00"))
        assert list(DetalleAsiento.objects.filter(id_asiento=a_pago).values_list("id_contacto_id", flat=True)) == [
            contacto_cli.pk,
            contacto_cli.pk,
        ]


class TestAprobacionReversionYConciliacion:
    def test_aprobar_y_revertir_asiento_reglas_y_doble_reversion(self, empresa_a, user_a):
        c1 = _cuenta(empresa_a, "1.1.20", "Banco")
        c2 = _cuenta(empresa_a, "4.1.20", "Ingresos", tipo="INGRESO", naturaleza="ACREEDORA")
        diario = DiarioContable.objects.create(
            id_empresa=empresa_a,
            codigo="VTA-REV",
            nombre="Ventas Reversión",
            tipo="VENTAS",
            prefijo_secuencia="RV",
            siguiente_numero=1,
        )
        contacto = Contacto.objects.create(
            id_empresa=empresa_a, nombre="Tercero Reversión", rif="J-30000003-3", es_cliente=True
        )

        # Borrador con < 2 líneas falla
        asiento_1_linea = AsientoContable.objects.create(
            id_empresa=empresa_a,
            fecha_asiento=timezone.localdate(),
            numero_asiento="BORR-1L",
            descripcion="Solo 1 línea",
            estado_asiento="BORRADOR",
        )
        DetalleAsiento.objects.create(id_asiento=asiento_1_linea, id_cuenta_contable=c1, debe=Decimal("10.00"))
        with pytest.raises(AsientoError, match="al menos dos líneas"):
            aprobar_asiento(asiento_1_linea, usuario=user_a)

        # Borrador en 0.00 falla
        asiento_cero = _asiento_manual(empresa_a, c1, c2, Decimal("0.00"), estado="BORRADOR")
        with pytest.raises(AsientoError, match="mayor a cero"):
            aprobar_asiento(asiento_cero, usuario=user_a)

        # No se puede revertir un BORRADOR
        asiento = _asiento_manual(
            empresa_a, c1, c2, Decimal("250.00"), estado="BORRADOR", diario=diario, contacto=contacto
        )
        with pytest.raises(AsientoError, match="APROBADO"):
            revertir_asiento(asiento, usuario=user_a)

        aprobado = aprobar_asiento(asiento, usuario=user_a)
        assert aprobado.estado_asiento == "APROBADO"

        contra = revertir_asiento(aprobado, usuario=user_a, motivo="Corrección factura")
        assert contra.estado_asiento == "APROBADO"
        assert contra.asiento_revertido_id == aprobado.pk
        assert contra.id_diario_id == diario.pk
        assert contra.numero_asiento == "RV-000001"
        assert "Corrección factura" in contra.descripcion

        det_contra = list(DetalleAsiento.objects.filter(id_asiento=contra).order_by("fecha_creacion", "pk"))
        assert len(det_contra) == 2
        assert det_contra[0].debe == Decimal("0.00")
        assert det_contra[0].haber == Decimal("250.00")
        assert det_contra[0].id_contacto_id == contacto.pk
        assert det_contra[1].debe == Decimal("250.00")
        assert det_contra[1].haber == Decimal("0.00")
        assert det_contra[1].id_contacto_id == contacto.pk

        # Bloquea doble reversión
        with pytest.raises(AsientoError, match="ya fue revertido"):
            revertir_asiento(aprobado, usuario=user_a)

        # Bloquea revertir un contra-asiento
        with pytest.raises(AsientoError, match="contra-asiento"):
            revertir_asiento(contra, usuario=user_a)

    def test_propagacion_vía_revertir_asignacion_pago_y_periodo_cerrado(
        self, empresa_a, moneda_usd, metodo_efectivo, user_a
    ):
        empresa_a.contabilidad_activa = True
        empresa_a.contabilidad_auto_aprobar = True
        empresa_a.save(update_fields=["contabilidad_activa", "contabilidad_auto_aprobar"])

        c_banco = _cuenta(empresa_a, "1.1.30", "Banco")
        c_cxc = _cuenta(empresa_a, "1.1.31", "CxC")
        _mapeo(empresa_a, "PAGO_CXC", c_banco, c_cxc)

        contacto = Contacto.objects.create(
            id_empresa=empresa_a, nombre="Cliente Concil", rif="J-40000004-4", es_cliente=True
        )
        cliente = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cliente Concil", rif="J-40000004-4", contacto=contacto
        )
        cxc = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente,
            monto=Decimal("120.00"),
            fecha_emision=timezone.localdate(),
            fecha_vencimiento=timezone.localdate() + datetime.timedelta(days=10),
        )
        pago = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("120.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )

        asig = aplicar_pago_a_documentos(
            pago,
            [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc.pk, "monto_asignado_pago": "120.00"}],
            usuario=user_a,
        )[0]
        assert asig.id_asiento is not None
        assert list(
            DetalleAsiento.objects.filter(id_asiento=asig.id_asiento).values_list("id_contacto_id", flat=True)
        ) == [
            contacto.pk,
            contacto.pk,
        ]

        # Si el período contable actual está cerrado, revertir_asignacion_pago falla atómicamente con ConciliacionContableError
        hoy = timezone.localdate()
        periodo = cerrar_periodo_contable(empresa_a, hoy.year, hoy.month, usuario=user_a)
        with pytest.raises(ConciliacionContableError, match="cerrado"):
            revertir_asignacion_pago(asig, usuario=user_a, motivo="Bloqueado")

        asig.refresh_from_db()
        assert asig.estado == "ACTIVA"

        reabrir_periodo_contable(periodo, usuario=user_a, motivo="Permitir reverso")
        rev = revertir_asignacion_pago(asig, usuario=user_a, motivo="Cheque devuelto")
        assert rev.id_asiento_reversion is not None
        assert rev.id_asiento_reversion.asiento_revertido_id == rev.id_asiento_id
        assert list(
            DetalleAsiento.objects.filter(id_asiento=rev.id_asiento_reversion).values_list("id_contacto_id", flat=True)
        ) == [contacto.pk, contacto.pk]


class TestPeriodosYCierreEjercicio:
    def test_cerrar_periodo_bloquea_borradores_y_operaciones_y_aisla_empresa(self, empresa_a, empresa_b, user_a):
        c1 = _cuenta(empresa_a, "1.1.40", "Caja")
        c2 = _cuenta(empresa_a, "4.1.40", "Ventas", tipo="INGRESO", naturaleza="ACREEDORA")
        _mapeo(empresa_a, "FACTURA_VENTA", c1, c2)

        hoy = timezone.localdate()
        borrador = _asiento_manual(empresa_a, c1, c2, Decimal("75.00"), fecha=hoy, estado="BORRADOR")

        with pytest.raises(AsientoError, match="BORRADOR"):
            cerrar_periodo_contable(empresa_a, hoy.year, hoy.month, usuario=user_a)

        # Cerrar período en empresa_b NO bloquea a empresa_a
        cerrar_periodo_contable(empresa_b, hoy.year, hoy.month, usuario=user_a)
        aprobar_asiento(borrador, usuario=user_a)

        periodo = cerrar_periodo_contable(
            empresa_a, hoy.year, hoy.month, usuario=user_a, observaciones="Cierre mensual"
        )
        assert PeriodoContable.esta_cerrado(empresa_a, hoy.year, hoy.month) is True
        # Idempotente
        periodo_dup = cerrar_periodo_contable(empresa_a, hoy.year, hoy.month, usuario=user_a)
        assert periodo_dup.pk == periodo.pk

        doc = SimpleNamespace(pk=uuid.uuid4(), monto_total=Decimal("10.00"))
        with pytest.raises(PeriodoContableCerradoError):
            generar_asiento("FACTURA_VENTA", doc, empresa=empresa_a)

        with pytest.raises(PeriodoContableCerradoError):
            revertir_asiento(borrador, usuario=user_a)

        reabierto = reabrir_periodo_contable(periodo, usuario=user_a, motivo="Ajuste auditoría")
        assert reabierto.estado == "ABIERTO"
        assert "Ajuste auditoría" in reabierto.observaciones
        with pytest.raises(AsientoError, match="ya se encuentra abierto"):
            reabrir_periodo_contable(reabierto, usuario=user_a)

        # Período fiscal cerrado también bloquea generar_asiento
        PeriodoFiscal.objects.create(id_empresa=empresa_a, año=hoy.year, mes=hoy.month, cerrado=True)
        with pytest.raises(PeriodoContableCerradoError):
            generar_asiento("FACTURA_VENTA", doc, empresa=empresa_a)

    def test_cerrar_ejercicio_ganancia_perdida_sin_movimientos_y_doble_cierre(self, empresa_a, empresa_b, user_a):
        c_caja = _cuenta(empresa_a, "1.1.50", "Caja")
        c_ing = _cuenta(empresa_a, "4.1.50", "Ventas", tipo="INGRESO", naturaleza="ACREEDORA")
        c_costo = _cuenta(empresa_a, "5.1.50", "Costo Ventas", tipo="COSTO", naturaleza="DEUDORA")
        c_gasto = _cuenta(empresa_a, "6.1.50", "Gastos Admin", tipo="GASTO", naturaleza="DEUDORA")
        c_res_acum = _cuenta(empresa_a, "3.2.01", "Resultado del Ejercicio", tipo="PATRIMONIO", naturaleza="ACREEDORA")
        c_res_b = _cuenta(empresa_b, "3.2.01", "Patrimonio B", tipo="PATRIMONIO", naturaleza="ACREEDORA")

        # Validaciones de cuenta de resultado
        with pytest.raises(AsientoError, match="no pertenece"):
            cerrar_ejercicio_contable(empresa_a, 2025, c_res_b, usuario=user_a)
        with pytest.raises(AsientoError, match="PATRIMONIO"):
            cerrar_ejercicio_contable(empresa_a, 2025, c_caja, usuario=user_a)

        # Año 2024 sin movimientos -> no crea asiento en 0.00 y cierra los 12 períodos
        res_vacio = cerrar_ejercicio_contable(empresa_a, 2024, c_res_acum, usuario=user_a)
        assert res_vacio["asiento_cierre"] is None
        assert res_vacio["resultado_ejercicio"] == Decimal("0.00")
        assert len(res_vacio["periodos_cerrados"]) == 12
        assert PeriodoContable.objects.filter(id_empresa=empresa_a, anio=2024, estado="CERRADO").count() == 12

        # Año 2025 con ganancia neta: Ingresos 1000 - Costos 400 - Gastos 250 = +350
        _asiento_manual(empresa_a, c_caja, c_ing, Decimal("1000.00"), fecha=datetime.date(2025, 3, 15))
        _asiento_manual(empresa_a, c_costo, c_caja, Decimal("400.00"), fecha=datetime.date(2025, 5, 10))
        _asiento_manual(empresa_a, c_gasto, c_caja, Decimal("250.00"), fecha=datetime.date(2025, 8, 20))

        # Si existe un BORRADOR en 2025, bloquea cierre anual
        borrador_2025 = _asiento_manual(
            empresa_a, c_gasto, c_caja, Decimal("10.00"), fecha=datetime.date(2025, 9, 1), estado="BORRADOR"
        )
        with pytest.raises(AsientoError, match="BORRADOR"):
            cerrar_ejercicio_contable(empresa_a, 2025, c_res_acum, usuario=user_a)
        borrador_2025.estado_asiento = "ANULADO"
        borrador_2025.save(update_fields=["estado_asiento"])

        res_2025 = cerrar_ejercicio_contable(empresa_a, 2025, c_res_acum, usuario=user_a)
        asiento_cierre = res_2025["asiento_cierre"]
        assert asiento_cierre is not None
        assert asiento_cierre.es_cierre is True
        assert asiento_cierre.estado_asiento == "APROBADO"
        assert res_2025["resultado_ejercicio"] == Decimal("350.00")
        assert res_2025["cantidad_cuentas_saldadas"] == 3

        # Verificar que cada cuenta de resultado queda en 0 y Patrimonio recibe 350.00 al Haber
        for cuenta_res in (c_ing, c_costo, c_gasto):
            aggs = DetalleAsiento.objects.filter(
                id_asiento__id_empresa=empresa_a,
                id_asiento__estado_asiento="APROBADO",
                id_asiento__fecha_asiento__year=2025,
                id_cuenta_contable=cuenta_res,
            ).values_list("debe", "haber")
            saldo = sum(d - h for d, h in aggs)
            assert saldo == Decimal("0.00")

        linea_pat = DetalleAsiento.objects.get(id_asiento=asiento_cierre, id_cuenta_contable=c_res_acum)
        assert linea_pat.haber == Decimal("350.00")
        assert linea_pat.debe == Decimal("0.00")

        # Bloquea doble cierre y bloquea reapertura mientras el asiento de cierre esté activo
        with pytest.raises(AsientoError, match="ya posee un asiento de cierre"):
            cerrar_ejercicio_contable(empresa_a, 2025, c_res_acum, usuario=user_a)

        dic_2025 = PeriodoContable.objects.get(id_empresa=empresa_a, anio=2025, mes=12)
        with pytest.raises(AsientoError, match="ejercicio cerrado"):
            reabrir_periodo_contable(dic_2025, usuario=user_a)

        # Año 2026 con pérdida neta: Ingresos 200 - Gastos 500 = -300
        _asiento_manual(empresa_a, c_caja, c_ing, Decimal("200.00"), fecha=datetime.date(2026, 2, 1))
        _asiento_manual(empresa_a, c_gasto, c_caja, Decimal("500.00"), fecha=datetime.date(2026, 2, 10))
        res_2026 = cerrar_ejercicio_contable(empresa_a, 2026, c_res_acum, usuario=user_a)
        assert res_2026["resultado_ejercicio"] == Decimal("-300.00")
        linea_perdida = DetalleAsiento.objects.get(
            id_asiento=res_2026["asiento_cierre"], id_cuenta_contable=c_res_acum
        )
        assert linea_perdida.debe == Decimal("300.00")
        assert linea_perdida.haber == Decimal("0.00")

    def test_ramas_defensivas_diario_reversion_y_cierre(self, empresa_a, user_a):
        assert _resolver_contacto_documento_asiento(None, empresa_a) is None

        c_casa = Contacto.objects.create(id_empresa=empresa_a, nombre="Casa Cambio Test", rif="J-55555555-5")
        doc_casa = SimpleNamespace(casa_de_cambio=SimpleNamespace(contacto=c_casa))
        assert _resolver_contacto_documento_asiento(doc_casa, empresa_a) == c_casa

        c_caja = _cuenta(empresa_a, "1.1.60", "Caja")
        c_ing = _cuenta(empresa_a, "4.1.60", "Ventas Neto Cero", tipo="INGRESO", naturaleza="ACREEDORA")
        c_ing_2 = _cuenta(empresa_a, "4.1.61", "Ventas Activas", tipo="INGRESO", naturaleza="ACREEDORA")
        c_pat_inact = _cuenta(empresa_a, "3.2.99", "Patrimonio Inactivo", tipo="PATRIMONIO", naturaleza="ACREEDORA")
        c_pat_inact.activo = False
        c_pat_inact.save(update_fields=["activo"])
        c_pat = _cuenta(empresa_a, "3.2.60", "Patrimonio Activo", tipo="PATRIMONIO", naturaleza="ACREEDORA")

        # Asiento aprobado sin detalles y descuadrado -> AsientoError al revertir
        asiento_vacio = AsientoContable.objects.create(
            id_empresa=empresa_a,
            fecha_asiento=datetime.date(2023, 4, 1),
            numero_asiento="AS-VAC-1",
            descripcion="Vacio",
            estado_asiento="APROBADO",
        )
        with pytest.raises(AsientoError, match="no tiene detalles"):
            revertir_asiento(asiento_vacio, usuario=user_a)

        asiento_descuad = AsientoContable.objects.create(
            id_empresa=empresa_a,
            fecha_asiento=datetime.date(2023, 4, 1),
            numero_asiento="AS-DESC-1",
            descripcion="Descuadrado",
            estado_asiento="APROBADO",
        )
        DetalleAsiento.objects.create(id_asiento=asiento_descuad, id_cuenta_contable=c_caja, debe=Decimal("10.00"))
        with pytest.raises(AsientoError, match="descuadrado"):
            revertir_asiento(asiento_descuad, usuario=user_a)

        # Validaciones de rango año/mes y cuenta/fecha en cierre de ejercicio
        with pytest.raises(AsientoError, match="fuera de rango"):
            cerrar_periodo_contable(empresa_a, 1850, 1, usuario=user_a)
        with pytest.raises(AsientoError, match="Mes contable inválido"):
            cerrar_periodo_contable(empresa_a, 2023, 13, usuario=user_a)
        with pytest.raises(AsientoError, match="inactiva"):
            cerrar_ejercicio_contable(empresa_a, 2023, c_pat_inact, usuario=user_a)
        with pytest.raises(AsientoError, match="debe pertenecer al ejercicio"):
            cerrar_ejercicio_contable(empresa_a, 2023, c_pat, usuario=user_a, fecha_cierre=datetime.date(2024, 1, 1))

        # Cuenta con movimientos cuyo neto es 0 se omite; diario VARIOS con prefijo numera el cierre
        _asiento_manual(empresa_a, c_caja, c_ing, Decimal("50.00"), fecha=datetime.date(2023, 5, 1))
        _asiento_manual(empresa_a, c_ing, c_caja, Decimal("50.00"), fecha=datetime.date(2023, 5, 2))
        _asiento_manual(empresa_a, c_caja, c_ing_2, Decimal("120.00"), fecha=datetime.date(2023, 6, 1))
        diario_varios = DiarioContable.objects.create(
            id_empresa=empresa_a,
            codigo="VAR-C",
            nombre="Diario Varios",
            tipo="VARIOS",
            prefijo_secuencia="CIER",
            siguiente_numero=1,
        )
        res_2023 = cerrar_ejercicio_contable(empresa_a, 2023, c_pat, usuario=user_a)
        assert res_2023["asiento_cierre"] is not None
        assert res_2023["asiento_cierre"].id_diario_id == diario_varios.pk
        assert res_2023["asiento_cierre"].numero_asiento == "CIER-000001"
        assert res_2023["cantidad_cuentas_saldadas"] == 1
        assert str(res_2023["periodos_cerrados"][0]) == "2023-01 (CERRADO)"

        # Periodo cerrado vinculado a asiento_cierre diferente aún bloquea segundo cierre
        res_2023["asiento_cierre"].estado_asiento = "ANULADO"
        res_2023["asiento_cierre"].save(update_fields=["estado_asiento"])
        asiento_cierre_2022 = _asiento_manual(
            empresa_a, c_caja, c_ing_2, Decimal("10.00"), fecha=datetime.date(2022, 12, 31)
        )
        PeriodoContable.objects.filter(id_empresa=empresa_a, anio=2023, mes=12).update(
            asiento_cierre=asiento_cierre_2022
        )
        with pytest.raises(AsientoError, match="vinculados a un asiento de cierre"):
            cerrar_ejercicio_contable(empresa_a, 2023, c_pat, usuario=user_a)

    def test_reversion_asignacion_pago_guardas_borrador(self, empresa_a, moneda_usd, metodo_efectivo, user_a):
        c_caja = _cuenta(empresa_a, "1.1.70", "Caja Conciliación")
        c_ing = _cuenta(empresa_a, "4.1.70", "Ingresos Conciliación", tipo="INGRESO", naturaleza="ACREEDORA")
        contacto = Contacto.objects.create(
            id_empresa=empresa_a, nombre="Cliente Guardas", rif="J-77777777-7", es_cliente=True
        )
        cliente = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Cliente Guardas", rif="J-77777777-7", contacto=contacto
        )
        cxc = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente,
            monto=Decimal("50.00"),
            estado="pagada",
            fecha_emision=timezone.localdate(),
            fecha_vencimiento=timezone.localdate() + datetime.timedelta(days=10),
        )
        pago = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("100.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        borrador_vacio = AsientoContable.objects.create(
            id_empresa=empresa_a,
            fecha_asiento=timezone.localdate(),
            numero_asiento="BOR-VAC-1",
            descripcion="Borrador sin detalles",
            estado_asiento="BORRADOR",
        )
        asig = AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_pago=pago,
            id_contacto=contacto,
            tipo_documento="CUENTA_POR_COBRAR",
            id_cxc=cxc,
            id_documento=str(cxc.pk),
            monto_asignado_pago=Decimal("50.0000"),
            monto_asignado_documento=Decimal("50.0000"),
            id_moneda_documento=moneda_usd,
            tasa_aplicada=Decimal("1"),
            id_asiento=borrador_vacio,
        )
        with pytest.raises(ConciliacionContableError, match="no tiene detalles"):
            revertir_asignacion_pago(asig, usuario=user_a, motivo="Sin detalles")

        DetalleAsiento.objects.create(id_asiento=borrador_vacio, id_cuenta_contable=c_caja, debe=Decimal("50.00"))
        with pytest.raises(ConciliacionContableError, match="descuadrado"):
            revertir_asignacion_pago(asig, usuario=user_a, motivo="Descuadrado")

        # Contra-asiento ya asignado se omite limpiamente
        orig = _asiento_manual(empresa_a, c_caja, c_ing, Decimal("25.00"))
        contra = revertir_asiento(orig, usuario=user_a, motivo="Pre-revertido")
        asig.id_asiento = contra
        asig.save(update_fields=["id_asiento"])
        rev = revertir_asignacion_pago(asig, usuario=user_a, motivo="Contra ya presente")
        assert rev.estado == "REVERTIDA"
