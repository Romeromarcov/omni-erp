"""Tests de integración contra PostgreSQL real para PR-11 (Ola A2).

Cubre ``apps.finanzas.services_conciliacion_pagos``:
1. Conciliación 1 -> N y N -> 1 (``FacturaFiscal``, ``CuentaPorCobrar``, ``CuentaPorPagar``, ``FacturaCompra``).
2. Anticipos / saldos a favor por ``core.Contacto`` (sin crear pagos duplicados, consulta BD sin N+1).
3. Propuesta FIFO determinística ``sugerir_distribucion_fifo`` (INGRESO y EGRESO, multimoneda y falta de tasa).
4. Multimoneda estricto (``R-CODE-4``, nunca 1:1 implícito) y diferencial cambiario (``GANANCIA``/``PERDIDA``).
5. Política contable ``R-CODE-11`` (``contabilidad_activa``, modo sin fricción, ``generar_asiento=False``)
   y reversión controlada con contra-asiento cuadrado (``R-PROD-4``) + consistencia de aging.
6. ``ADR-009`` (``CuentaPorCobrar`` externa vía ``EntidadSincronizada`` y fail-closed con ``empresa=None``),
   aislamiento multi-tenant, validación de contacto, dirección y concurrencia real con ``select_for_update``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest
from django.db import connections
from django.utils import timezone

from apps.compras.models import FacturaCompra, OrdenCompra
from apps.contabilidad.models import AsientoContable, DetalleAsiento, MapeoContable, PlanCuentas
from apps.core.models import Contacto
from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar
from apps.cuentas_por_cobrar.services import calcular_aging
from apps.cuentas_por_pagar.models import AbonoCxP, CuentaPorPagar
from apps.cuentas_por_pagar.services import calcular_aging_cxp, registrar_abono_cxp
from apps.finanzas.models import AsignacionPago, Moneda, Pago, TasaCambio
from apps.finanzas.services_conciliacion_pagos import (
    ConciliacionContableError,
    ConciliacionPagoError,
    ConciliacionTenantError,
    aplicar_pago_a_documentos,
    revertir_asignacion_pago,
    saldo_a_favor_contacto,
    saldo_disponible_pago,
    saldo_pendiente_documento,
    sugerir_distribucion_fifo,
)
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor, EntidadSincronizada
from apps.proveedores.models import Proveedor
from apps.ventas.models import FacturaFiscal

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Helpers y fixtures locales ───────────────────────────────────────────────


def _hoy() -> date:
    return timezone.localdate()


def _cuenta(empresa, codigo: str, nombre: str, tipo: str = "ACTIVO", nat: str = "DEUDORA") -> PlanCuentas:
    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=nombre,
        tipo_cuenta=tipo,
        naturaleza=nat,
        nivel=1,
    )


def _mapeo(empresa, tipo_asiento: str, debe: PlanCuentas, haber: PlanCuentas) -> MapeoContable:
    return MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento=tipo_asiento,
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla=f"{tipo_asiento} - {{numero}}",
        activo=True,
    )


def _configurar_mapeos_conciliacion(empresa) -> dict[str, PlanCuentas]:
    banco = _cuenta(empresa, "1.1.01", "Banco Principal", "ACTIVO", "DEUDORA")
    cxc = _cuenta(empresa, "1.1.02", "Cuentas por Cobrar", "ACTIVO", "DEUDORA")
    cxp = _cuenta(empresa, "2.1.01", "Cuentas por Pagar", "PASIVO", "ACREEDORA")
    gan = _cuenta(empresa, "4.7.01", "Ganancia Cambiaria", "INGRESO", "ACREEDORA")
    perd = _cuenta(empresa, "5.7.01", "Pérdida Cambiaria", "GASTO", "DEUDORA")
    dif_puente = _cuenta(empresa, "1.1.99", "Puente Diferencial", "ACTIVO", "DEUDORA")

    _mapeo(empresa, "PAGO_CXC", banco, cxc)
    _mapeo(empresa, "PAGO_CXP", cxp, banco)
    _mapeo(empresa, "GANANCIA_CAMBIARIA", dif_puente, gan)
    _mapeo(empresa, "PERDIDA_CAMBIARIA", perd, dif_puente)

    return {"banco": banco, "cxc": cxc, "cxp": cxp, "gan": gan, "perd": perd, "puente": dif_puente}


def _crear_pago(
    empresa,
    moneda,
    metodo,
    *,
    monto: Decimal,
    tipo_operacion: str = "INGRESO",
    contacto: Contacto | None = None,
    tipo_documento: str = "ANTICIPO",
    tasa: Decimal = Decimal("1.0000"),
    referencia: str = "REF-TEST",
    fecha_pago=None,
) -> Pago:
    return Pago.objects.create(
        id_empresa=empresa,
        id_contacto=contacto,
        tipo_operacion=tipo_operacion,
        tipo_documento=tipo_documento,
        id_documento=None,
        fecha_pago=fecha_pago or timezone.now(),
        monto=monto,
        id_moneda=moneda,
        tasa=tasa,
        id_metodo_pago=metodo,
        referencia=referencia,
    )


def _crear_factura_venta(
    empresa,
    cliente,
    moneda,
    *,
    numero: str,
    monto_total: Decimal,
    estado: str = "EMITIDA",
    fecha_emision: date | None = None,
    fecha_vencimiento: date | None = None,
    tasa_cambio: Decimal = Decimal("1.0000"),
    activo: bool = True,
) -> FacturaFiscal:
    f_emi = fecha_emision or _hoy()
    return FacturaFiscal.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        numero_control=f"CTRL-{numero}",
        numero_factura=numero,
        fecha_emision=f_emi,
        fecha_vencimiento=fecha_vencimiento,
        base_imponible=monto_total,
        monto_iva=Decimal("0.0000"),
        monto_igtf=Decimal("0.0000"),
        monto_total=monto_total,
        id_moneda=moneda,
        tasa_cambio=tasa_cambio,
        estado=estado,
        activo=activo,
    )


def _crear_factura_compra(
    empresa,
    proveedor,
    *,
    numero: str,
    monto_total: Decimal,
    fecha_emision: date | None = None,
    activo: bool = True,
) -> FacturaCompra:
    f_emi = fecha_emision or _hoy()
    oc = OrdenCompra.objects.create(
        id_empresa=empresa,
        id_proveedor=proveedor,
        numero_orden=f"OC-{numero}",
        fecha_orden=f_emi,
        estado="APROBADA",
    )
    return FacturaCompra.objects.create(
        id_empresa=empresa,
        id_orden_compra=oc,
        numero_factura=numero,
        fecha_emision=f_emi,
        monto_total=monto_total,
        activo=activo,
    )


@pytest.fixture
def moneda_ves(db):
    return Moneda.objects.create(
        codigo_iso="VES",
        nombre="Bolívar",
        simbolo="Bs",
        tipo_moneda="fiat",
        es_generica=True,
    )


@pytest.fixture
def moneda_eur(db):
    return Moneda.objects.create(
        codigo_iso="EUR",
        nombre="Euro",
        simbolo="€",
        tipo_moneda="fiat",
        es_generica=True,
    )


@pytest.fixture
def contacto_cliente_a(db, empresa_a):
    return Contacto.objects.create(
        id_empresa=empresa_a,
        tipo_persona="JURIDICA",
        nombre="Cliente Alpha C.A.",
        rif="J-10000001-1",
        es_cliente=True,
    )


@pytest.fixture
def contacto_cliente_a2(db, empresa_a):
    return Contacto.objects.create(
        id_empresa=empresa_a,
        tipo_persona="JURIDICA",
        nombre="Cliente Dos C.A.",
        rif="J-10000002-2",
        es_cliente=True,
    )


@pytest.fixture
def contacto_proveedor_a(db, empresa_a):
    return Contacto.objects.create(
        id_empresa=empresa_a,
        tipo_persona="JURIDICA",
        nombre="Proveedor Alpha S.A.",
        rif="J-20000001-2",
        es_proveedor=True,
    )


@pytest.fixture
def contacto_b(db, empresa_b):
    return Contacto.objects.create(
        id_empresa=empresa_b,
        tipo_persona="JURIDICA",
        nombre="Contacto Beta C.A.",
        rif="J-30000001-3",
        es_cliente=True,
        es_proveedor=True,
    )


@pytest.fixture
def cliente_a(db, empresa_a, contacto_cliente_a):
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Alpha C.A.",
        rif="J-10000001-1",
        contacto=contacto_cliente_a,
    )


@pytest.fixture
def cliente_a2(db, empresa_a, contacto_cliente_a2):
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Dos C.A.",
        rif="J-10000002-2",
        contacto=contacto_cliente_a2,
    )


@pytest.fixture
def cliente_b(db, empresa_b, contacto_b):
    return Cliente.objects.create(
        id_empresa=empresa_b,
        razon_social="Cliente Beta C.A.",
        rif="J-30000001-3",
        contacto=contacto_b,
    )


@pytest.fixture
def proveedor_a(db, empresa_a, contacto_proveedor_a):
    return Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Proveedor Alpha S.A.",
        rif="J-20000001-2",
        contacto=contacto_proveedor_a,
    )


@pytest.fixture
def proveedor_b(db, empresa_b, contacto_b):
    return Proveedor.objects.create(
        id_empresa=empresa_b,
        razon_social="Proveedor Beta S.A.",
        rif="J-40000001-4",
        contacto=contacto_b,
    )


# ── 1. Conciliación 1 -> N ───────────────────────────────────────────────────


class TestConciliacionUnoAN:
    def test_un_pago_salda_remanente_factura_y_abona_parcial_otra(
        self, empresa_a, cliente_a, contacto_cliente_a, moneda_usd, metodo_efectivo, user_a
    ):
        fac1 = _crear_factura_venta(
            empresa_a, cliente_a, moneda_usd, numero="FV-1N-1", monto_total=Decimal("100.0000")
        )
        fac2 = _crear_factura_venta(
            empresa_a, cliente_a, moneda_usd, numero="FV-1N-2", monto_total=Decimal("120.0000")
        )
        pago_previo = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("65.0000"), contacto=contacto_cliente_a
        )
        aplicar_pago_a_documentos(
            pago_previo,
            [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac1.pk, "monto_asignado_pago": "65.00"}],
            usuario=user_a,
        )
        assert saldo_pendiente_documento(fac1) == Decimal("35.0000")

        pago_100 = _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("100.0000"),
            contacto=None,  # Debe auto-vincularse al contacto común en la transacción
            tipo_documento="CONCILIACION_MULTIPLE",
        )
        asigs = aplicar_pago_a_documentos(
            pago_100,
            [
                {"tipo_documento": "FACTURA_VENTA", "id_documento": fac1.pk, "monto_asignado_pago": "35.00"},
                {"tipo_documento": "FACTURA_VENTA", "documento": fac2, "monto_asignado_pago": Decimal("65.00")},
            ],
            usuario=user_a,
        )

        assert len(asigs) == 2
        fac1.refresh_from_db()
        fac2.refresh_from_db()
        pago_100.refresh_from_db()
        assert pago_100.id_contacto_id == contacto_cliente_a.pk
        assert fac1.estado == "PAGADA"
        assert fac2.estado == "EMITIDA"
        assert saldo_pendiente_documento(fac1) == Decimal("0.0000")
        assert saldo_pendiente_documento(fac2) == Decimal("55.0000")
        assert saldo_disponible_pago(pago_100) == Decimal("0.0000")

    def test_un_pago_cubre_multiples_cxc_y_sincroniza_abonos(
        self, empresa_a, cliente_a, contacto_cliente_a, moneda_usd, metodo_efectivo, user_a
    ):
        cxc1 = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("80.00"),
            fecha_emision=_hoy() - timedelta(days=20),
            fecha_vencimiento=_hoy() - timedelta(days=5),
            estado="vencida",
        )
        cxc2 = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("150.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=15),
            estado="pendiente",
        )
        pago = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("130.0000"), contacto=contacto_cliente_a
        )
        asigs = aplicar_pago_a_documentos(
            pago,
            [
                {"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc1.pk, "monto_asignado_pago": "80.00"},
                {"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc2.pk, "monto_asignado_pago": "50.00"},
            ],
            usuario=user_a,
        )
        cxc1.refresh_from_db()
        cxc2.refresh_from_db()
        assert cxc1.estado == "pagada"
        assert cxc2.estado == "parcial"
        assert saldo_pendiente_documento(cxc1) == Decimal("0.00")
        assert saldo_pendiente_documento(cxc2) == Decimal("100.00")
        assert asigs[0].id_abono_cxc is not None
        assert asigs[0].id_abono_cxc.monto == Decimal("80.00")
        assert asigs[1].id_abono_cxc is not None
        assert asigs[1].id_abono_cxc.monto == Decimal("50.00")
        assert saldo_disponible_pago(pago) == Decimal("0.0000")

    def test_un_pago_egreso_cubre_cxp_y_factura_compra(
        self, empresa_a, proveedor_a, contacto_proveedor_a, moneda_usd, metodo_efectivo, user_a
    ):
        fc = _crear_factura_compra(empresa_a, proveedor_a, numero="FC-1N-1", monto_total=Decimal("200.0000"))
        cxp = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            monto_total=Decimal("300.0000"),
            monto_pendiente=Decimal("300.0000"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=10),
            estado="PENDIENTE",
        )
        pago = _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("350.0000"),
            tipo_operacion="EGRESO",
            contacto=contacto_proveedor_a,
        )
        asigs = aplicar_pago_a_documentos(
            pago,
            [
                {"tipo_documento": "CUENTA_POR_PAGAR", "id_documento": cxp.pk, "monto_asignado_pago": "250.00"},
                {"tipo_documento": "FACTURA_COMPRA", "id_documento": fc.pk, "monto_asignado_pago": "100.00"},
            ],
            usuario=user_a,
        )
        cxp.refresh_from_db()
        assert cxp.monto_pendiente == Decimal("50.0000")
        assert cxp.estado == "PARCIAL"
        assert asigs[0].id_abono_cxp is not None
        assert asigs[0].id_abono_cxp.monto == Decimal("250.0000")
        assert saldo_pendiente_documento(fc) == Decimal("100.0000")
        assert saldo_disponible_pago(pago) == Decimal("0.0000")


# ── 2. Saldo a favor / anticipo del contacto ─────────────────────────────────


class TestSaldoAFavorAnticipos:
    def test_pago_mayor_que_obligaciones_deja_saldo_a_favor_y_se_aplica_luego(
        self,
        empresa_a,
        cliente_a,
        contacto_cliente_a,
        moneda_usd,
        moneda_eur,
        metodo_efectivo,
        user_a,
        django_assert_num_queries,
    ):
        cxc1 = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("180.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=10),
            estado="pendiente",
        )
        pago_anticipo = _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("500.0000"),
            contacto=contacto_cliente_a,
            referencia="ANT-500",
        )
        # Otro pago en EUR para verificar separación por moneda sin N+1
        _crear_pago(
            empresa_a,
            moneda_eur,
            metodo_efectivo,
            monto=Decimal("75.0000"),
            contacto=contacto_cliente_a,
            referencia="ANT-EUR",
        )

        aplicar_pago_a_documentos(
            pago_anticipo,
            [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc1.pk, "monto_asignado_pago": "180.00"}],
            usuario=user_a,
        )

        # Consulta agregada en BD en 1 sola query (sin N+1)
        with django_assert_num_queries(1):
            resumen = saldo_a_favor_contacto(empresa_a, contacto_cliente_a, tipo_operacion="INGRESO")

        assert resumen["contacto_id"] == str(contacto_cliente_a.pk)
        assert resumen["empresa_id"] == str(empresa_a.pk)
        assert resumen["por_operacion"]["INGRESO"]["USD"] == Decimal("320.0000")
        assert resumen["por_operacion"]["INGRESO"]["EUR"] == Decimal("75.0000")
        assert resumen["total_por_moneda"]["USD"]["INGRESO"] == Decimal("320.0000")
        assert len(resumen["pagos_con_saldo"]) == 2

        # Aplicar el remanente del mismo pago a una factura nueva sin crear Pago duplicado
        fac_nueva = _crear_factura_venta(
            empresa_a, cliente_a, moneda_usd, numero="FV-ANT-2", monto_total=Decimal("200.0000")
        )
        aplicar_pago_a_documentos(
            pago_anticipo,
            [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_nueva.pk, "monto_asignado_pago": "200.00"}],
            usuario=user_a,
        )
        assert Pago.objects.filter(id_empresa=empresa_a, id_contacto=contacto_cliente_a).count() == 2
        fac_nueva.refresh_from_db()
        assert fac_nueva.estado == "PAGADA"
        assert saldo_disponible_pago(pago_anticipo) == Decimal("120.0000")

        resumen_post = saldo_a_favor_contacto(empresa_a, contacto_cliente_a)
        assert resumen_post["por_operacion"]["INGRESO"]["USD"] == Decimal("120.0000")


# ── 3. Conciliación N -> 1 ───────────────────────────────────────────────────


class TestConciliacionNAUno:
    def test_multiples_pagos_cubren_una_factura_cxc_y_cxp(
        self,
        empresa_a,
        cliente_a,
        proveedor_a,
        contacto_cliente_a,
        contacto_proveedor_a,
        moneda_usd,
        metodo_efectivo,
        user_a,
    ):
        # FacturaFiscal cubierta por 2 pagos
        fac = _crear_factura_venta(empresa_a, cliente_a, moneda_usd, numero="FV-N1", monto_total=Decimal("100.0000"))
        p1 = _crear_pago(empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("40.0000"), contacto=contacto_cliente_a)
        p2 = _crear_pago(empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("60.0000"), contacto=contacto_cliente_a)

        aplicar_pago_a_documentos(
            p1,
            [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac.pk, "monto_asignado_pago": "40.00"}],
            usuario=user_a,
        )
        fac.refresh_from_db()
        assert fac.estado == "EMITIDA"
        assert saldo_pendiente_documento(fac) == Decimal("60.0000")

        aplicar_pago_a_documentos(
            p2,
            [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac.pk, "monto_asignado_pago": "60.00"}],
            usuario=user_a,
        )
        fac.refresh_from_db()
        assert fac.estado == "PAGADA"
        assert saldo_pendiente_documento(fac) == Decimal("0.0000")

        # CuentaPorCobrar cubierta por 2 pagos
        cxc = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("250.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=5),
            estado="pendiente",
        )
        p3 = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("100.0000"), contacto=contacto_cliente_a
        )
        p4 = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("150.0000"), contacto=contacto_cliente_a
        )
        aplicar_pago_a_documentos(
            p3,
            [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc.pk, "monto_asignado_pago": "100.00"}],
            usuario=user_a,
        )
        cxc.refresh_from_db()
        assert cxc.estado == "parcial"
        aplicar_pago_a_documentos(
            p4,
            [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc.pk, "monto_asignado_pago": "150.00"}],
            usuario=user_a,
        )
        cxc.refresh_from_db()
        assert cxc.estado == "pagada"
        assert cxc.abonos.count() == 2

        # CuentaPorPagar cubierta por 2 pagos
        cxp = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            monto_total=Decimal("300.0000"),
            monto_pendiente=Decimal("300.0000"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=5),
            estado="PENDIENTE",
        )
        pe1 = _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("120.0000"),
            tipo_operacion="EGRESO",
            contacto=contacto_proveedor_a,
        )
        pe2 = _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("180.0000"),
            tipo_operacion="EGRESO",
            contacto=contacto_proveedor_a,
        )
        aplicar_pago_a_documentos(
            pe1,
            [{"tipo_documento": "CUENTA_POR_PAGAR", "id_documento": cxp.pk, "monto_asignado_pago": "120.00"}],
            usuario=user_a,
        )
        cxp.refresh_from_db()
        assert cxp.estado == "PARCIAL"
        assert cxp.monto_pendiente == Decimal("180.0000")
        aplicar_pago_a_documentos(
            pe2,
            [{"tipo_documento": "CUENTA_POR_PAGAR", "id_documento": cxp.pk, "monto_asignado_pago": "180.00"}],
            usuario=user_a,
        )
        cxp.refresh_from_db()
        assert cxp.estado == "PAGADA"
        assert cxp.monto_pendiente == Decimal("0.0000")

    def test_mismo_documento_repetido_en_un_lote_respeta_tope_acumulado(
        self, empresa_a, cliente_a, contacto_cliente_a, moneda_usd, metodo_efectivo, user_a
    ):
        fac = _crear_factura_venta(
            empresa_a, cliente_a, moneda_usd, numero="FV-DUP-LOTE", monto_total=Decimal("100.0000")
        )
        pago = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("120.0000"), contacto=contacto_cliente_a
        )
        with pytest.raises(ConciliacionPagoError, match="excede el saldo pendiente"):
            aplicar_pago_a_documentos(
                pago,
                [
                    {"tipo_documento": "FACTURA_VENTA", "id_documento": fac.pk, "monto_asignado_pago": "60.00"},
                    {"tipo_documento": "FACTURA_VENTA", "id_documento": fac.pk, "monto_asignado_pago": "50.00"},
                ],
                usuario=user_a,
            )
        assert AsignacionPago.objects.count() == 0

        asigs = aplicar_pago_a_documentos(
            pago,
            [
                {
                    "tipo_documento": "FACTURA_VENTA",
                    "id_documento": fac.pk,
                    "monto_asignado_pago": "40.00",
                    "referencia_externa": "R1",
                },
                {
                    "tipo_documento": "FACTURA_VENTA",
                    "id_documento": fac.pk,
                    "monto_asignado_pago": "60.00",
                    "referencia_externa": "R2",
                },
            ],
            usuario=user_a,
        )
        assert len(asigs) == 2
        fac.refresh_from_db()
        assert fac.estado == "PAGADA"
        assert saldo_disponible_pago(pago) == Decimal("20.0000")


# ── 4. sugerir_distribucion_fifo ─────────────────────────────────────────────


class TestSugerirDistribucionFifo:
    def test_fifo_ingreso_ordena_por_vencimiento_respeta_topes_y_omite_sin_tasa(
        self, empresa_a, cliente_a, contacto_cliente_a, moneda_usd, moneda_eur, metodo_efectivo, user_a
    ):
        hoy = _hoy()
        cxc_antigua = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("50.00"),
            fecha_emision=hoy - timedelta(days=30),
            fecha_vencimiento=hoy - timedelta(days=10),
            estado="vencida",
        )
        fac_media = _crear_factura_venta(
            empresa_a,
            cliente_a,
            moneda_usd,
            numero="FV-FIFO-1",
            monto_total=Decimal("80.0000"),
            fecha_emision=hoy - timedelta(days=15),
            fecha_vencimiento=hoy - timedelta(days=2),
            estado="VENCIDA",
        )
        fac_eur_sin_tasa = _crear_factura_venta(
            empresa_a,
            cliente_a,
            moneda_eur,
            numero="FV-FIFO-EUR",
            monto_total=Decimal("40.0000"),
            fecha_emision=hoy - timedelta(days=20),
            fecha_vencimiento=hoy - timedelta(days=5),
            estado="EMITIDA",
        )
        # Borrador y pagada deben ignorarse
        _crear_factura_venta(
            empresa_a, cliente_a, moneda_usd, numero="FV-BORR", monto_total=Decimal("99.0000"), estado="BORRADOR"
        )
        cxc_futura = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("100.00"),
            fecha_emision=hoy,
            fecha_vencimiento=hoy + timedelta(days=20),
            estado="pendiente",
        )

        pago = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("300.0000"), contacto=contacto_cliente_a
        )
        propuesta = sugerir_distribucion_fifo(pago)

        assert propuesta["pago_id"] == str(pago.pk)
        assert propuesta["saldo_disponible"] == Decimal("300.0000")
        assert [p["id_documento"] for p in propuesta["propuestas"]] == [
            str(cxc_antigua.pk),
            str(fac_media.pk),
            str(cxc_futura.pk),
        ]
        assert propuesta["total_a_aplicar"] == Decimal("230.0000")
        assert propuesta["saldo_a_favor_resultante"] == Decimal("70.0000")
        assert len(propuesta["omitidas_sin_tasa"]) == 1
        assert propuesta["omitidas_sin_tasa"][0]["id_documento"] == str(fac_eur_sin_tasa.pk)

        # La propuesta puede aplicarse directamente
        aplicar_pago_a_documentos(pago, propuesta["propuestas"], usuario=user_a)
        assert saldo_disponible_pago(pago) == Decimal("70.0000")

        # Pago sin contacto falla explícito
        pago_sin = _crear_pago(empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("50.0000"), contacto=None)
        with pytest.raises(ConciliacionPagoError, match="contacto asignado"):
            sugerir_distribucion_fifo(pago_sin)

    def test_fifo_egreso_ordena_cxp_y_factura_compra(
        self, empresa_a, proveedor_a, contacto_proveedor_a, moneda_usd, metodo_efectivo
    ):
        hoy = _hoy()
        cxp_vence_pronto = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            monto_total=Decimal("120.0000"),
            monto_pendiente=Decimal("120.0000"),
            fecha_emision=hoy - timedelta(days=10),
            fecha_vencimiento=hoy + timedelta(days=2),
            estado="PENDIENTE",
        )
        fc_posterior = _crear_factura_compra(
            empresa_a,
            proveedor_a,
            numero="FC-FIFO-2",
            monto_total=Decimal("200.0000"),
            fecha_emision=hoy + timedelta(days=5),
        )
        pago_egreso = _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("150.0000"),
            tipo_operacion="EGRESO",
            contacto=contacto_proveedor_a,
        )
        propuesta = sugerir_distribucion_fifo(pago_egreso)
        assert [p["id_documento"] for p in propuesta["propuestas"]] == [
            str(cxp_vence_pronto.pk),
            str(fc_posterior.pk),
        ]
        assert propuesta["propuestas"][0]["monto_asignado_pago"] == Decimal("120.0000")
        assert propuesta["propuestas"][1]["monto_asignado_pago"] == Decimal("30.0000")
        assert propuesta["total_a_aplicar"] == Decimal("150.0000")
        assert propuesta["saldo_a_favor_resultante"] == Decimal("0.0000")

        # Filtro por tipo_documento funciona y rechaza tipo incompatible
        solo_fc = sugerir_distribucion_fifo(pago_egreso, tipo_documento="FACTURA_COMPRA")
        assert [p["id_documento"] for p in solo_fc["propuestas"]] == [str(fc_posterior.pk)]
        with pytest.raises(ConciliacionPagoError, match="no es compatible"):
            sugerir_distribucion_fifo(pago_egreso, tipo_documento="FACTURA_VENTA")


# ── 5. Multimoneda y diferencial cambiario (R-CODE-4) ────────────────────────


class TestMultimonedaYDiferencialCambiario:
    def test_moneda_distinta_sin_tasa_falla_cerrado_nunca_1_a_1(
        self, empresa_a, cliente_a, contacto_cliente_a, moneda_usd, moneda_ves, metodo_efectivo, user_a
    ):
        fac_usd = _crear_factura_venta(
            empresa_a, cliente_a, moneda_usd, numero="FV-NO-RATE", monto_total=Decimal("100.0000")
        )
        pago_ves = _crear_pago(
            empresa_a, moneda_ves, metodo_efectivo, monto=Decimal("100.0000"), contacto=contacto_cliente_a
        )
        with pytest.raises(ConciliacionPagoError, match="tasa"):
            aplicar_pago_a_documentos(
                pago_ves,
                [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_usd.pk, "monto_asignado_pago": "100.00"}],
                usuario=user_a,
            )
        fac_usd.refresh_from_db()
        assert fac_usd.estado == "EMITIDA"
        assert AsignacionPago.objects.count() == 0

    def test_conversion_multimoneda_con_tasa_bcv_y_validacion_monto_documento(
        self, empresa_a, cliente_a, contacto_cliente_a, moneda_usd, moneda_ves, metodo_efectivo, user_a
    ):
        TasaCambio.objects.create(
            id_empresa=None,
            id_moneda_origen=moneda_ves,
            id_moneda_destino=moneda_usd,
            tipo_tasa="OFICIAL_BCV",
            valor_tasa=Decimal("0.02500000"),
            fecha_tasa=_hoy(),
        )
        fac_usd = _crear_factura_venta(
            empresa_a, cliente_a, moneda_usd, numero="FV-VES-USD", monto_total=Decimal("100.0000")
        )
        pago_ves = _crear_pago(
            empresa_a, moneda_ves, metodo_efectivo, monto=Decimal("4000.0000"), contacto=contacto_cliente_a
        )

        # Monto_asignado_documento inconsistente (> 0.01) rechazado
        with pytest.raises(ConciliacionPagoError, match="difiere"):
            aplicar_pago_a_documentos(
                pago_ves,
                [
                    {
                        "tipo_documento": "FACTURA_VENTA",
                        "id_documento": fac_usd.pk,
                        "monto_asignado_pago": "2000.00",
                        "monto_asignado_documento": "99.00",
                    }
                ],
                usuario=user_a,
            )

        asigs = aplicar_pago_a_documentos(
            pago_ves,
            [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_usd.pk, "monto_asignado_pago": "4000.00"}],
            usuario=user_a,
        )
        assert asigs[0].tasa_aplicada == Decimal("0.02500000")
        assert asigs[0].monto_asignado_pago == Decimal("4000.0000")
        assert asigs[0].monto_asignado_documento == Decimal("100.0000")
        fac_usd.refresh_from_db()
        assert fac_usd.estado == "PAGADA"

    def test_diferencial_cambiario_ganancia_y_perdida_en_ingreso_y_egreso(
        self,
        empresa_a,
        cliente_a,
        proveedor_a,
        contacto_cliente_a,
        contacto_proveedor_a,
        moneda_usd,
        metodo_efectivo,
        user_a,
    ):
        # INGRESO: Factura tasa_cambio=36, Pago tasa=40 -> delta=+4 -> GANANCIA 400
        fac_gan = _crear_factura_venta(
            empresa_a,
            cliente_a,
            moneda_usd,
            numero="FV-DIF-G",
            monto_total=Decimal("100.0000"),
            tasa_cambio=Decimal("36.0000"),
        )
        pago_ing_gan = _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("100.0000"),
            tasa=Decimal("40.0000"),
            contacto=contacto_cliente_a,
        )
        asig_ing_gan = aplicar_pago_a_documentos(
            pago_ing_gan,
            [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_gan.pk, "monto_asignado_pago": "100.00"}],
            usuario=user_a,
        )[0]
        assert asig_ing_gan.tipo_diferencia == "GANANCIA"
        assert asig_ing_gan.diferencia_cambiaria == Decimal("400.0000")

        # INGRESO: CxC tasa_orig=40, tasa_liq=36 -> delta=-4 -> PERDIDA 400
        cxc_perd = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("100.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=10),
            estado="pendiente",
        )
        pago_ing_perd = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("100.0000"), contacto=contacto_cliente_a
        )
        asig_ing_perd = aplicar_pago_a_documentos(
            pago_ing_perd,
            [
                {
                    "tipo_documento": "CUENTA_POR_COBRAR",
                    "id_documento": cxc_perd.pk,
                    "monto_asignado_pago": "100.00",
                    "tasa_original": "40",
                    "tasa_liquidacion": "36",
                }
            ],
            usuario=user_a,
        )[0]
        assert asig_ing_perd.tipo_diferencia == "PERDIDA"
        assert asig_ing_perd.diferencia_cambiaria == Decimal("400.0000")

        # EGRESO: CxP tasa_orig=36, tasa_liq=40 -> delta=+4 -> PERDIDA 400
        cxp_perd = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            monto_total=Decimal("100.0000"),
            monto_pendiente=Decimal("100.0000"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=10),
            estado="PENDIENTE",
        )
        pago_eg_perd = _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("100.0000"),
            tipo_operacion="EGRESO",
            contacto=contacto_proveedor_a,
        )
        asig_eg_perd = aplicar_pago_a_documentos(
            pago_eg_perd,
            [
                {
                    "tipo_documento": "CUENTA_POR_PAGAR",
                    "id_documento": cxp_perd.pk,
                    "monto_asignado_pago": "100.00",
                    "tasa_original": "36",
                    "tasa_liquidacion": "40",
                }
            ],
            usuario=user_a,
        )[0]
        assert asig_eg_perd.tipo_diferencia == "PERDIDA"
        assert asig_eg_perd.diferencia_cambiaria == Decimal("400.0000")

        # EGRESO: FacturaCompra tasa_orig=40, tasa_liq=36 -> delta=-4 -> GANANCIA 400
        fc_gan = _crear_factura_compra(empresa_a, proveedor_a, numero="FC-DIF-G", monto_total=Decimal("100.0000"))
        pago_eg_gan = _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("100.0000"),
            tipo_operacion="EGRESO",
            contacto=contacto_proveedor_a,
        )
        asig_eg_gan = aplicar_pago_a_documentos(
            pago_eg_gan,
            [
                {
                    "tipo_documento": "FACTURA_COMPRA",
                    "id_documento": fc_gan.pk,
                    "monto_asignado_pago": "100.00",
                    "tasa_original": "40",
                    "tasa_liquidacion": "36",
                }
            ],
            usuario=user_a,
        )[0]
        assert asig_eg_gan.tipo_diferencia == "GANANCIA"
        assert asig_eg_gan.diferencia_cambiaria == Decimal("400.0000")

        # Tasa no positiva rechazada (sobre factura abierta)
        fc_bad = _crear_factura_compra(empresa_a, proveedor_a, numero="FC-DIF-BAD", monto_total=Decimal("50.0000"))
        with pytest.raises(ConciliacionPagoError, match="mayor a cero"):
            aplicar_pago_a_documentos(
                _crear_pago(
                    empresa_a,
                    moneda_usd,
                    metodo_efectivo,
                    monto=Decimal("10.0000"),
                    tipo_operacion="EGRESO",
                    contacto=contacto_proveedor_a,
                ),
                [
                    {
                        "tipo_documento": "FACTURA_COMPRA",
                        "id_documento": fc_bad.pk,
                        "monto_asignado_pago": "10.00",
                        "tasa_original": "0",
                        "tasa_liquidacion": "40",
                    }
                ],
                usuario=user_a,
            )


# ── 6. Contabilidad (R-CODE-11) y reversión (R-PROD-4) ───────────────────────


class TestContabilidadYReversion:
    def test_contabilidad_activa_con_mapeo_genera_asientos_y_reversion_contra_asiento_cuadrado(
        self, empresa_a, cliente_a, contacto_cliente_a, moneda_usd, metodo_efectivo, user_a
    ):
        empresa_a.contabilidad_activa = True
        empresa_a.contabilidad_auto_aprobar = True
        empresa_a.save(update_fields=["contabilidad_activa", "contabilidad_auto_aprobar"])
        _configurar_mapeos_conciliacion(empresa_a)

        cxc_vencida = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("100.00"),
            fecha_emision=_hoy() - timedelta(days=40),
            fecha_vencimiento=_hoy() - timedelta(days=10),
            estado="vencida",
        )
        cxc_vigente = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("200.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=15),
            estado="pendiente",
        )
        pago = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("300.0000"), contacto=contacto_cliente_a
        )

        asigs = aplicar_pago_a_documentos(
            pago,
            [
                {
                    "tipo_documento": "CUENTA_POR_COBRAR",
                    "id_documento": cxc_vencida.pk,
                    "monto_asignado_pago": "100.00",
                    "tasa_original": "36",
                    "tasa_liquidacion": "40",
                },
                {
                    "tipo_documento": "CUENTA_POR_COBRAR",
                    "id_documento": cxc_vigente.pk,
                    "monto_asignado_pago": "200.00",
                },
            ],
            usuario=user_a,
        )
        asig_venc = asigs[0]
        asig_vig = asigs[1]
        assert asig_venc.id_asiento is not None
        assert asig_venc.id_asiento.estado_asiento == "APROBADO"

        # 2 asientos para asig_venc (PAGO_CXC + GANANCIA_CAMBIARIA) + 1 para asig_vig
        asientos_venc = AsientoContable.objects.filter(
            id_empresa=empresa_a,
            id_documento_origen=asig_venc.id_asignacion,
            nombre_modelo_origen="AsignacionPago",
        )
        assert asientos_venc.count() == 2

        # Mientras están pagadas, aging CxC está en 0
        assert calcular_aging(empresa_a.pk)["total_general"] == Decimal("0")

        # Revertir ambas asignaciones
        rev_venc = revertir_asignacion_pago(asig_venc, usuario=user_a, motivo="Devolución cheque")
        rev_vig = revertir_asignacion_pago(asig_vig, usuario=user_a, motivo="Error de aplicación")

        assert rev_venc.estado == "REVERTIDA"
        assert rev_venc.activo is False
        assert rev_venc.id_abono_cxc is None
        assert rev_venc.id_asiento_reversion is not None
        assert rev_venc.id_asiento_reversion.estado_asiento == "APROBADO"
        assert rev_venc.motivo_reversion == "Devolución cheque"

        # Doble reversión bloqueada
        with pytest.raises(ConciliacionPagoError, match="ya fue revertida"):
            revertir_asignacion_pago(rev_venc, usuario=user_a)

        # Saldos, estados y aging restaurados
        cxc_vencida.refresh_from_db()
        cxc_vigente.refresh_from_db()
        assert cxc_vencida.estado == "vencida"
        assert cxc_vigente.estado == "pendiente"
        assert saldo_disponible_pago(pago) == Decimal("300.0000")

        aging = calcular_aging(empresa_a.pk)
        assert aging["dias_1_30"]["total"] == Decimal("100.00")
        assert aging["corriente"]["total"] == Decimal("200.00")
        assert aging["total_general"] == Decimal("300.00")

        # Verificar contra-asiento cuadrado (debe/haber invertidos) y neto contable en cero por cuenta
        orig_det = list(DetalleAsiento.objects.filter(id_asiento=rev_venc.id_asiento).order_by("fecha_creacion", "pk"))
        contra_det = list(
            DetalleAsiento.objects.filter(id_asiento=rev_venc.id_asiento_reversion).order_by("fecha_creacion", "pk")
        )
        assert len(orig_det) == len(contra_det) == 2
        assert contra_det[0].debe == orig_det[0].haber
        assert contra_det[0].haber == orig_det[0].debe
        assert contra_det[1].debe == orig_det[1].haber
        assert contra_det[1].haber == orig_det[1].debe

        # Todo asiento APROBADO cuadra y el neto por cuenta tras revertir todo es 0
        neto_por_cuenta: dict[uuid.UUID, Decimal] = {}
        for det in DetalleAsiento.objects.filter(
            id_asiento__id_empresa=empresa_a, id_asiento__estado_asiento="APROBADO"
        ):
            neto_por_cuenta[det.id_cuenta_contable_id] = (
                neto_por_cuenta.get(det.id_cuenta_contable_id, Decimal("0.00")) + det.debe - det.haber
            )
        assert all(v == Decimal("0.00") for v in neto_por_cuenta.values())

    def test_contabilidad_activa_sin_mapeo_falla_422_y_revierte_todo_atomico(
        self, empresa_a, cliente_a, moneda_usd, metodo_efectivo, user_a
    ):
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])

        cxc = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("100.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=10),
            estado="pendiente",
        )
        pago = _crear_pago(empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("100.0000"), contacto=None)

        with pytest.raises(ConciliacionContableError):
            aplicar_pago_a_documentos(
                pago,
                [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc.pk, "monto_asignado_pago": "100.00"}],
                usuario=user_a,
            )

        cxc.refresh_from_db()
        pago.refresh_from_db()
        assert cxc.estado == "pendiente"
        assert pago.id_contacto is None
        assert AsignacionPago.objects.count() == 0
        assert AbonoCxC.objects.count() == 0
        assert AsientoContable.objects.count() == 0

    def test_contabilidad_inactiva_y_generar_asiento_false_y_reversion_cxp_con_aging(
        self, empresa_a, proveedor_a, contacto_proveedor_a, moneda_usd, metodo_efectivo, user_a
    ):
        # 1. contabilidad_activa=False sin mapeo opera sin fricción
        assert empresa_a.contabilidad_activa is False
        cxp_vencida = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            monto_total=Decimal("200.0000"),
            monto_pendiente=Decimal("200.0000"),
            fecha_emision=_hoy() - timedelta(days=35),
            fecha_vencimiento=_hoy() - timedelta(days=5),
            estado="VENCIDA",
        )
        # Abono previo directo (como PagoTercero) de 50
        registrar_abono_cxp(cxp_vencida, Decimal("50.00"), user_a, generar_asiento=False)
        cxp_vencida.refresh_from_db()
        assert cxp_vencida.monto_pendiente == Decimal("150.0000")

        # 2. Activar contabilidad + mapeos pero pasar generar_asiento=False (uso history-only Odoo)
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])
        _configurar_mapeos_conciliacion(empresa_a)

        pago = _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("150.0000"),
            tipo_operacion="EGRESO",
            contacto=contacto_proveedor_a,
        )
        asig = aplicar_pago_a_documentos(
            pago,
            [{"tipo_documento": "CUENTA_POR_PAGAR", "id_documento": cxp_vencida.pk, "monto_asignado_pago": "150.00"}],
            usuario=user_a,
            generar_asiento=False,
        )[0]
        assert asig.id_asiento is None
        assert AsientoContable.objects.filter(id_empresa=empresa_a).count() == 0
        cxp_vencida.refresh_from_db()
        assert cxp_vencida.estado == "PAGADA"
        assert cxp_vencida.monto_pendiente == Decimal("0.0000")
        assert calcular_aging_cxp(empresa_a.pk)["total_general"] == Decimal("0")

        # Reversión de CxP con abono previo -> vuelve a PARCIAL y monto_pendiente=150
        revertir_asignacion_pago(asig, usuario=user_a, motivo="Reverso parcial")
        cxp_vencida.refresh_from_db()
        assert cxp_vencida.estado == "PARCIAL"
        assert cxp_vencida.monto_pendiente == Decimal("150.0000")
        assert AbonoCxP.objects.filter(cuenta_por_pagar=cxp_vencida).count() == 1
        assert calcular_aging_cxp(empresa_a.pk)["dias_1_30"]["total"] == Decimal("150.0000")

    def test_reversion_borrador_y_factura_venta_pagada(
        self, empresa_a, cliente_a, contacto_cliente_a, moneda_usd, metodo_efectivo, user_a
    ):
        empresa_a.contabilidad_activa = True
        empresa_a.contabilidad_auto_aprobar = False
        empresa_a.save(update_fields=["contabilidad_activa", "contabilidad_auto_aprobar"])
        _configurar_mapeos_conciliacion(empresa_a)

        fac_venc = _crear_factura_venta(
            empresa_a,
            cliente_a,
            moneda_usd,
            numero="FV-REV-VENC",
            monto_total=Decimal("90.0000"),
            fecha_emision=_hoy() - timedelta(days=20),
            fecha_vencimiento=_hoy() - timedelta(days=2),
            estado="VENCIDA",
        )
        pago = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("90.0000"), contacto=contacto_cliente_a
        )
        asig = aplicar_pago_a_documentos(
            pago,
            [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_venc.pk, "monto_asignado_pago": "90.00"}],
            usuario=user_a,
        )[0]
        assert asig.id_asiento is not None
        assert asig.id_asiento.estado_asiento == "BORRADOR"
        fac_venc.refresh_from_db()
        assert fac_venc.estado == "PAGADA"

        rev = revertir_asignacion_pago(asig, usuario=user_a, motivo="Anulación borrador")
        asig.id_asiento.refresh_from_db()
        assert asig.id_asiento.estado_asiento == "ANULADO"
        assert rev.id_asiento_reversion is None
        fac_venc.refresh_from_db()
        assert fac_venc.estado == "VENCIDA"
        assert saldo_pendiente_documento(fac_venc) == Decimal("90.0000")
        assert saldo_disponible_pago(pago) == Decimal("90.0000")


# ── 7. ADR-009 + Seguridad multi-tenant / contacto / reglas / concurrencia ──


class TestSeguridadAdr009YConcurrencia:
    def test_cxc_externa_adr009_resuelta_via_entidad_sincronizada_y_fail_closed(
        self, empresa_a, empresa_b, contacto_cliente_a, contacto_b, moneda_usd, metodo_efectivo, user_a
    ):
        proveedor_conn = ConectorProveedor.objects.create(
            codigo="odoo_test_concil",
            nombre="Odoo Test",
            capacidades=["contactos"],
        )
        instancia_a = ConectorInstancia.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_conn,
            nombre="Odoo Alpha",
            estado="activo",
        )
        EntidadSincronizada.objects.create(
            id_instancia=instancia_a,
            tipo_entidad="contactos",
            id_externo="odoo-p-42",
            id_omni=str(contacto_cliente_a.pk),
            modelo_omni="apps.core.models.Contacto",
            activo=True,
        )
        cxc_ext = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=None,
            cliente_externo_id="odoo-p-42",
            cliente_externo_nombre="Socio Odoo 42",
            monto=Decimal("150.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=15),
            estado="pendiente",
        )
        pago = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("150.0000"), contacto=contacto_cliente_a
        )
        # FIFO también encuentra la CxC externa ADR-009
        fifo = sugerir_distribucion_fifo(pago)
        assert [p["id_documento"] for p in fifo["propuestas"]] == [str(cxc_ext.pk)]

        asig = aplicar_pago_a_documentos(
            pago,
            [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc_ext.pk, "monto_asignado_pago": "150.00"}],
            usuario=user_a,
        )[0]
        cxc_ext.refresh_from_db()
        assert cxc_ext.estado == "pagada"
        assert asig.id_contacto_id == contacto_cliente_a.pk

        # CxC externa sin EntidadSincronizada -> falla cerrado
        cxc_sin_mapa = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=None,
            cliente_externo_id="odoo-sin-mapa",
            cliente_externo_nombre="Sin Mapa",
            monto=Decimal("50.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=10),
            estado="pendiente",
        )
        pago_nuevo = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("50.0000"), contacto=contacto_cliente_a
        )
        with pytest.raises(ConciliacionPagoError, match="Contacto sincronizado"):
            aplicar_pago_a_documentos(
                pago_nuevo,
                [
                    {
                        "tipo_documento": "CUENTA_POR_COBRAR",
                        "id_documento": cxc_sin_mapa.pk,
                        "monto_asignado_pago": "50.00",
                    }
                ],
                usuario=user_a,
            )

        # EntidadSincronizada que apunta a contacto de empresa_b -> falla cerrado cross-tenant
        EntidadSincronizada.objects.create(
            id_instancia=instancia_a,
            tipo_entidad="contactos",
            id_externo="odoo-cruzado",
            id_omni=str(contacto_b.pk),
            modelo_omni="apps.core.models.Contacto",
            activo=True,
        )
        cxc_cruzada = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=None,
            cliente_externo_id="odoo-cruzado",
            monto=Decimal("50.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=10),
            estado="pendiente",
        )
        with pytest.raises(ConciliacionTenantError, match="otra empresa"):
            aplicar_pago_a_documentos(
                pago_nuevo,
                [
                    {
                        "tipo_documento": "CUENTA_POR_COBRAR",
                        "id_documento": cxc_cruzada.pk,
                        "monto_asignado_pago": "50.00",
                    }
                ],
                usuario=user_a,
            )

    def test_validaciones_tenant_contacto_direccion_estados_y_topes(
        self,
        empresa_a,
        empresa_b,
        cliente_a,
        cliente_a2,
        cliente_b,
        proveedor_a,
        contacto_cliente_a,
        contacto_proveedor_a,
        moneda_usd,
        metodo_efectivo,
        user_a,
    ):
        # CxC sin empresa (ADR-009 nullable) -> ConciliacionTenantError
        cxc_huerfana = CuentaPorCobrar.objects.create(
            empresa=None,
            cliente=cliente_a,
            monto=Decimal("50.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=5),
        )
        pago_a = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("200.0000"), contacto=contacto_cliente_a
        )
        with pytest.raises(ConciliacionTenantError):
            saldo_pendiente_documento(cxc_huerfana)
        with pytest.raises(ConciliacionTenantError):
            aplicar_pago_a_documentos(
                pago_a,
                [
                    {
                        "tipo_documento": "CUENTA_POR_COBRAR",
                        "id_documento": cxc_huerfana.pk,
                        "monto_asignado_pago": "10.00",
                    }
                ],
                usuario=user_a,
            )

        # Cross-tenant: pago empresa_a + factura empresa_b -> ConciliacionTenantError
        fac_b = _crear_factura_venta(
            empresa_b, cliente_b, moneda_usd, numero="FV-EMP-B", monto_total=Decimal("80.0000")
        )
        with pytest.raises(ConciliacionTenantError):
            saldo_pendiente_documento(fac_b, empresa_id=empresa_a.pk)
        with pytest.raises(ConciliacionTenantError):
            aplicar_pago_a_documentos(
                pago_a,
                [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_b.pk, "monto_asignado_pago": "10.00"}],
                usuario=user_a,
            )

        # Cross-contacto en misma empresa -> ConciliacionPagoError
        fac_otro_contacto = _crear_factura_venta(
            empresa_a, cliente_a2, moneda_usd, numero="FV-OTRO-CONT", monto_total=Decimal("80.0000")
        )
        with pytest.raises(ConciliacionPagoError, match="contacto"):
            aplicar_pago_a_documentos(
                pago_a,
                [
                    {
                        "tipo_documento": "FACTURA_VENTA",
                        "id_documento": fac_otro_contacto.pk,
                        "monto_asignado_pago": "10.00",
                    }
                ],
                usuario=user_a,
            )

        # Dirección incompatible: INGRESO vs CxP/FacturaCompra y EGRESO vs CxC/FacturaFiscal
        cxp_a = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            monto_total=Decimal("100.0000"),
            monto_pendiente=Decimal("100.0000"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=10),
            estado="PENDIENTE",
        )
        fc_a = _crear_factura_compra(empresa_a, proveedor_a, numero="FC-DIR-1", monto_total=Decimal("100.0000"))
        with pytest.raises(ConciliacionPagoError, match="compatible"):
            aplicar_pago_a_documentos(
                pago_a,
                [{"tipo_documento": "CUENTA_POR_PAGAR", "id_documento": cxp_a.pk, "monto_asignado_pago": "10.00"}],
                usuario=user_a,
            )
        with pytest.raises(ConciliacionPagoError, match="compatible"):
            aplicar_pago_a_documentos(
                pago_a,
                [{"tipo_documento": "FACTURA_COMPRA", "id_documento": fc_a.pk, "monto_asignado_pago": "10.00"}],
                usuario=user_a,
            )

        pago_eg = _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("100.0000"),
            tipo_operacion="EGRESO",
            contacto=contacto_proveedor_a,
        )
        fac_a = _crear_factura_venta(
            empresa_a, cliente_a, moneda_usd, numero="FV-DIR-1", monto_total=Decimal("100.0000")
        )
        with pytest.raises(ConciliacionPagoError, match="compatible"):
            aplicar_pago_a_documentos(
                pago_eg,
                [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_a.pk, "monto_asignado_pago": "10.00"}],
                usuario=user_a,
            )

        # Montos inválidos, sobre-aplicación del pago, sobre-aplicación del doc y estados cerrados
        for monto_bad in ("0", "-5.00", "abc", "", "NaN", True, None):
            with pytest.raises(ConciliacionPagoError):
                aplicar_pago_a_documentos(
                    pago_a,
                    [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_a.pk, "monto_asignado_pago": monto_bad}],
                    usuario=user_a,
                )

        with pytest.raises(ConciliacionPagoError, match="saldo disponible"):
            aplicar_pago_a_documentos(
                pago_a,
                [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_a.pk, "monto_asignado_pago": "250.00"}],
                usuario=user_a,
            )

        with pytest.raises(ConciliacionPagoError, match="saldo pendiente"):
            aplicar_pago_a_documentos(
                pago_a,
                [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_a.pk, "monto_asignado_pago": "150.00"}],
                usuario=user_a,
            )

        fac_borrador = _crear_factura_venta(
            empresa_a, cliente_a, moneda_usd, numero="FV-BORR-2", monto_total=Decimal("50.0000"), estado="BORRADOR"
        )
        with pytest.raises(ConciliacionPagoError, match="BORRADOR"):
            aplicar_pago_a_documentos(
                pago_a,
                [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_borrador.pk, "monto_asignado_pago": "10.00"}],
                usuario=user_a,
            )

    def test_ramas_borde_moneda_fifo_reversion_y_validaciones_extra(
        self,
        empresa_a,
        empresa_b,
        cliente_a,
        cliente_a2,
        proveedor_a,
        contacto_cliente_a,
        contacto_proveedor_a,
        contacto_b,
        moneda_usd,
        moneda_ves,
        moneda_eur,
        metodo_efectivo,
        user_a,
    ):
        from datetime import datetime as _dt

        # 1. Pago EGRESO en saldo_a_favor_contacto + validaciones de error
        _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("90.0000"),
            tipo_operacion="EGRESO",
            contacto=contacto_proveedor_a,
        )
        res_eg = saldo_a_favor_contacto(empresa_a, contacto_proveedor_a, tipo_operacion="EGRESO")
        assert res_eg["por_operacion"]["EGRESO"]["USD"] == Decimal("90.0000")
        assert res_eg["total_por_moneda"]["USD"]["EGRESO"] == Decimal("90.0000")

        with pytest.raises(ConciliacionTenantError):
            saldo_a_favor_contacto(empresa_a, contacto_b)
        with pytest.raises(ConciliacionTenantError):
            saldo_a_favor_contacto(None, contacto_cliente_a)  # type: ignore[arg-type]
        with pytest.raises(ConciliacionPagoError):
            saldo_a_favor_contacto(empresa_a, contacto_cliente_a, tipo_operacion="INVALIDO")

        # 2. FIFO multimoneda con tasa válida (cache hit en 2da factura) + pago agotado + corte mid-loop
        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_ves,
            id_moneda_destino=moneda_eur,
            tipo_tasa="FIJA",
            valor_tasa=Decimal("0.02000000"),
            fecha_tasa=_hoy(),
        )
        _crear_factura_venta(
            empresa_a,
            cliente_a,
            moneda_eur,
            numero="FV-EUR-1",
            monto_total=Decimal("10.0000"),
            fecha_vencimiento=_hoy() + timedelta(days=1),
        )
        _crear_factura_venta(
            empresa_a,
            cliente_a,
            moneda_eur,
            numero="FV-EUR-2",
            monto_total=Decimal("50.0000"),
            fecha_vencimiento=_hoy() + timedelta(days=2),
        )
        _crear_factura_venta(
            empresa_a,
            cliente_a,
            moneda_eur,
            numero="FV-EUR-3",
            monto_total=Decimal("20.0000"),
            fecha_vencimiento=_hoy() + timedelta(days=3),
        )
        # Pago con fecha aware (y prueba directa de _fecha_local_pago naive) y monto 1000 VES (= 20 EUR)
        from apps.finanzas.services_conciliacion_pagos import _fecha_local_pago

        assert _fecha_local_pago(SimpleNamespace(fecha_pago=_dt(2026, 5, 1, 12, 0))) == date(2026, 5, 1)
        pago_ves_naive = _crear_pago(
            empresa_a,
            moneda_ves,
            metodo_efectivo,
            monto=Decimal("1000.0000"),
            contacto=contacto_cliente_a,
            fecha_pago=timezone.make_aware(_dt.combine(_hoy(), _dt.min.time())),
        )
        fifo_mc = sugerir_distribucion_fifo(pago_ves_naive, tipo_documento="FACTURA_VENTA")
        assert len(fifo_mc["propuestas"]) == 2
        assert fifo_mc["propuestas"][0]["monto_asignado_documento"] == Decimal("10.0000")
        assert fifo_mc["propuestas"][1]["monto_asignado_documento"] == Decimal("10.0000")
        assert fifo_mc["saldo_a_favor_resultante"] == Decimal("0.0000")

        aplicar_pago_a_documentos(pago_ves_naive, fifo_mc["propuestas"], usuario=user_a)
        fifo_agotado = sugerir_distribucion_fifo(pago_ves_naive)
        assert fifo_agotado["propuestas"] == []
        assert fifo_agotado["saldo_disponible"] == Decimal("0.0000")

        # 3. Moneda explícita, tasa_aplicada explícita, >2 dec en CxC, y documentos inactivos/cerrados
        moneda_priv_b = Moneda.objects.create(
            codigo_iso="MXN",
            nombre="Peso MX",
            simbolo="$",
            empresa=empresa_b,
            es_generica=False,
            es_publica=False,
        )
        moneda_inactiva = Moneda.objects.create(
            codigo_iso="COP",
            nombre="Peso CO",
            simbolo="$",
            es_generica=True,
            activo=False,
        )
        fac_eur = FacturaFiscal.objects.get(id_empresa=empresa_a, numero_factura="FV-EUR-3")
        pago_usd_extra = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("500.0000"), contacto=contacto_cliente_a
        )
        with pytest.raises(ConciliacionPagoError, match="coincide con la moneda"):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [
                    {
                        "tipo_documento": "FACTURA_VENTA",
                        "id_documento": fac_eur.pk,
                        "monto_asignado_pago": "10.00",
                        "moneda_documento": "USD",
                    }
                ],
                usuario=user_a,
            )

        cxc_dec = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("100.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=5),
        )
        with pytest.raises(ConciliacionTenantError, match="otra empresa"):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [
                    {
                        "tipo_documento": "CUENTA_POR_COBRAR",
                        "id_documento": cxc_dec.pk,
                        "monto_asignado_pago": "10.00",
                        "moneda_documento": str(moneda_priv_b.pk),
                    }
                ],
                usuario=user_a,
            )
        with pytest.raises(ConciliacionPagoError, match="inactiva"):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [
                    {
                        "tipo_documento": "CUENTA_POR_COBRAR",
                        "id_documento": cxc_dec.pk,
                        "monto_asignado_pago": "10.00",
                        "moneda_documento": moneda_inactiva,
                    }
                ],
                usuario=user_a,
            )
        with pytest.raises(ConciliacionPagoError, match="no encontrada"):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [
                    {
                        "tipo_documento": "CUENTA_POR_COBRAR",
                        "id_documento": cxc_dec.pk,
                        "monto_asignado_pago": "10.00",
                        "moneda_documento": "ZZZ",
                    }
                ],
                usuario=user_a,
            )
        with pytest.raises(ConciliacionPagoError, match="múltiplo exacto de 0.01"):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [
                    {
                        "tipo_documento": "CUENTA_POR_COBRAR",
                        "id_documento": cxc_dec.pk,
                        "monto_asignado_pago": "10.1234",
                        "monto_asignado_documento": "10.1234",
                    }
                ],
                usuario=user_a,
            )
        with pytest.raises(ConciliacionPagoError, match="tasa_aplicada debe ser 1"):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [
                    {
                        "tipo_documento": "CUENTA_POR_COBRAR",
                        "id_documento": cxc_dec.pk,
                        "monto_asignado_pago": "10.00",
                        "tasa_aplicada": "2.00",
                    }
                ],
                usuario=user_a,
            )

        # Tasa aplicada explícita en moneda distinta + diferencial cambiario con id_moneda_pais
        empresa_a.id_moneda_pais = moneda_ves
        empresa_a.save(update_fields=["id_moneda_pais"])
        asig_exp = aplicar_pago_a_documentos(
            pago_usd_extra,
            [
                {
                    "tipo_documento": "FACTURA_VENTA",
                    "id_documento": fac_eur.pk,
                    "monto_asignado_pago": "10.00",
                    "tasa_aplicada": "0.90",
                    "tasa_original": "36",
                    "tasa_liquidacion": "40",
                }
            ],
            usuario=user_a,
        )[0]
        assert asig_exp.monto_asignado_documento == Decimal("9.0000")
        assert asig_exp.diferencia_cambiaria == Decimal("36.0000")

        # 4. Validaciones estructurales de entrada en aplicar/revertir/saldo_pendiente
        with pytest.raises(ConciliacionPagoError):
            saldo_disponible_pago(Pago())
        with pytest.raises(ConciliacionTenantError):
            saldo_pendiente_documento(None)
        with pytest.raises(ConciliacionTenantError):
            saldo_pendiente_documento(fac_eur, empresa_id="uuid-malo")
        with pytest.raises(ConciliacionPagoError):
            saldo_pendiente_documento(contacto_cliente_a)

        cxp_inactiva = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            monto_total=Decimal("50.0000"),
            monto_pendiente=Decimal("50.0000"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=5),
            estado="ANULADA",
            activo=False,
        )
        fc_inactiva = _crear_factura_compra(
            empresa_a, proveedor_a, numero="FC-INACT", monto_total=Decimal("50.0000"), activo=False
        )
        assert saldo_pendiente_documento(cxp_inactiva) == Decimal("0.0000")
        assert saldo_pendiente_documento(fc_inactiva) == Decimal("0.0000")

        pago_eg_val = _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("100.0000"),
            tipo_operacion="EGRESO",
            contacto=contacto_proveedor_a,
        )
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(
                pago_eg_val,
                [
                    {
                        "tipo_documento": "CUENTA_POR_PAGAR",
                        "id_documento": cxp_inactiva.pk,
                        "monto_asignado_pago": "10.00",
                    }
                ],
            )
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(
                pago_eg_val,
                [{"tipo_documento": "FACTURA_COMPRA", "id_documento": fc_inactiva.pk, "monto_asignado_pago": "10.00"}],
            )

        # Pago sin contacto con 2 documentos de distintos contactos en el mismo lote
        fac_c1 = _crear_factura_venta(
            empresa_a, cliente_a, moneda_usd, numero="FV-MIX-1", monto_total=Decimal("20.0000")
        )
        fac_c2 = _crear_factura_venta(
            empresa_a, cliente_a2, moneda_usd, numero="FV-MIX-2", monto_total=Decimal("20.0000")
        )
        pago_sin_c = _crear_pago(empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("50.0000"), contacto=None)
        with pytest.raises(ConciliacionPagoError, match="mismo contacto"):
            aplicar_pago_a_documentos(
                pago_sin_c,
                [
                    {"tipo_documento": "FACTURA_VENTA", "id_documento": fac_c1.pk, "monto_asignado_pago": "10.00"},
                    {"tipo_documento": "FACTURA_VENTA", "id_documento": fac_c2.pk, "monto_asignado_pago": "10.00"},
                ],
            )

        # Inputs malformados / no existentes
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(
                Pago(), [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_c1.pk, "monto_asignado_pago": "1"}]
            )
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(pago_usd_extra, [])
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(pago_usd_extra, ["bad"])  # type: ignore[list-item]
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(
                pago_usd_extra, [{"tipo_documento": "OTRO", "id_documento": fac_c1.pk, "monto_asignado_pago": "1"}]
            )
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(
                pago_usd_extra, [{"tipo_documento": "FACTURA_VENTA", "documento": cxc_dec, "monto_asignado_pago": "1"}]
            )
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [{"tipo_documento": "FACTURA_VENTA", "id_documento": "no-uuid", "monto_asignado_pago": "1"}],
            )
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": "abc", "monto_asignado_pago": "1"}],
            )
        with pytest.raises(ConciliacionTenantError):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [{"tipo_documento": "FACTURA_VENTA", "id_documento": uuid.uuid4(), "monto_asignado_pago": "1"}],
            )

        # 5. Reversión de FacturaCompra y de CxP vencida sin abonos previos -> VENCIDA + CxC parcial
        fc_rev = _crear_factura_compra(empresa_a, proveedor_a, numero="FC-REV-1", monto_total=Decimal("80.0000"))
        cxp_rev_venc = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            monto_total=Decimal("60.0000"),
            monto_pendiente=Decimal("60.0000"),
            fecha_emision=_hoy() - timedelta(days=20),
            fecha_vencimiento=_hoy() - timedelta(days=3),
            estado="VENCIDA",
        )
        asigs_eg = aplicar_pago_a_documentos(
            pago_eg_val,
            [
                {"tipo_documento": "FACTURA_COMPRA", "id_documento": fc_rev.pk, "monto_asignado_pago": "30.00"},
                {
                    "tipo_documento": "CUENTA_POR_PAGAR",
                    "id_documento": cxp_rev_venc.pk,
                    "monto_asignado_pago": "60.00",
                },
            ],
            usuario=user_a,
        )
        revertir_asignacion_pago(asigs_eg[0], usuario=user_a)
        revertir_asignacion_pago(asigs_eg[1], usuario=user_a)
        cxp_rev_venc.refresh_from_db()
        assert cxp_rev_venc.estado == "VENCIDA"
        assert cxp_rev_venc.monto_pendiente == Decimal("60.0000")
        assert saldo_pendiente_documento(fc_rev) == Decimal("80.0000")
        assert saldo_disponible_pago(pago_eg_val) == Decimal("100.0000")

        # CxC con 2 abonos: revertir 1 deja CxC en "parcial"
        asig_cxc_1 = aplicar_pago_a_documentos(
            pago_usd_extra,
            [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc_dec.pk, "monto_asignado_pago": "40.00"}],
            usuario=user_a,
        )[0]
        asig_cxc_2 = aplicar_pago_a_documentos(
            pago_usd_extra,
            [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc_dec.pk, "monto_asignado_pago": "60.00"}],
            usuario=user_a,
        )[0]
        cxc_dec.refresh_from_db()
        assert cxc_dec.estado == "pagada"
        revertir_asignacion_pago(asig_cxc_2, usuario=user_a)
        cxc_dec.refresh_from_db()
        assert cxc_dec.estado == "parcial"
        assert saldo_pendiente_documento(cxc_dec) == Decimal("60.00")
        assert asig_cxc_1.estado == "ACTIVA"

        with pytest.raises(ConciliacionPagoError):
            revertir_asignacion_pago(AsignacionPago())
        with pytest.raises(ConciliacionTenantError):
            revertir_asignacion_pago(SimpleNamespace(pk=uuid.uuid4()))  # type: ignore[arg-type]

        # 6. Cobertura de ramas borde adicionales (moneda fallback, FX parcial/tasa_pago, contactos inactivos/sin contacto, ADR-009 inválido, asiento anulado)
        from apps.finanzas.services_conciliacion_pagos import (
            _cargar_moneda_para_empresa,
            _resolver_contacto_documento,
        )

        with pytest.raises(ConciliacionPagoError):
            _cargar_moneda_para_empresa(empresa_a, "   ")

        with pytest.raises(ConciliacionTenantError):
            aplicar_pago_a_documentos(
                SimpleNamespace(pk=uuid.uuid4()),  # type: ignore[arg-type]
                [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_c1.pk, "monto_asignado_pago": "1"}],
            )
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [{"tipo_documento": "FACTURA_VENTA", "documento": FacturaFiscal(), "monto_asignado_pago": "1"}],
            )
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [
                    {
                        "tipo_documento": "FACTURA_VENTA",
                        "id_documento": uuid.uuid4(),
                        "documento": fac_c1,
                        "monto_asignado_pago": "1",
                    }
                ],
            )
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [{"tipo_documento": "FACTURA_VENTA", "monto_asignado_pago": "1"}],
            )
        with pytest.raises(ConciliacionPagoError):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": True, "monto_asignado_pago": "1"}],
            )

        # FacturaVenta sin moneda base + FX con tasa_liquidacion sola (usa documento.tasa_cambio) y con tasa_original sola (usa pago.tasa)
        moneda_orig_emp = empresa_a.id_moneda_base
        empresa_a.id_moneda_base = None
        empresa_a.save(update_fields=["id_moneda_base"])
        cxc_sin_base = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("20.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=2),
        )
        asig_sin_base = aplicar_pago_a_documentos(
            pago_usd_extra,
            [{"tipo_documento": "CUENTA_POR_COBRAR", "id_documento": cxc_sin_base.pk, "monto_asignado_pago": "5.00"}],
            usuario=user_a,
        )[0]
        assert asig_sin_base.id_moneda_documento_id == pago_usd_extra.id_moneda_id
        empresa_a.id_moneda_base = moneda_orig_emp
        empresa_a.save(update_fields=["id_moneda_base"])

        fv_fx_solo_liq = _crear_factura_venta(
            empresa_a,
            cliente_a,
            moneda_usd,
            numero="FV-FX-LIQ",
            monto_total=Decimal("50.0000"),
            tasa_cambio=Decimal("38.0000"),
        )
        pago_tasa_42 = _crear_pago(
            empresa_a,
            moneda_usd,
            metodo_efectivo,
            monto=Decimal("50.0000"),
            contacto=contacto_cliente_a,
            tasa=Decimal("42.0000"),
        )
        asig_liq = aplicar_pago_a_documentos(
            pago_tasa_42,
            [
                {
                    "tipo_documento": "FACTURA_VENTA",
                    "id_documento": fv_fx_solo_liq.pk,
                    "monto_asignado_pago": "10.00",
                    "tasa_liquidacion": "40.00",
                },
                {
                    "tipo_documento": "FACTURA_VENTA",
                    "id_documento": fv_fx_solo_liq.pk,
                    "monto_asignado_pago": "10.00",
                    "tasa_original": "40.00",
                },
                {
                    "tipo_documento": "FACTURA_VENTA",
                    "id_documento": fv_fx_solo_liq.pk,
                    "monto_asignado_pago": "10.00",
                    "tasa_original": "40.000000",
                    "tasa_liquidacion": "40.000004",
                },
            ],
            usuario=user_a,
        )
        assert asig_liq[0].diferencia_cambiaria == Decimal("20.0000")
        assert asig_liq[0].tipo_diferencia == "GANANCIA"
        assert asig_liq[1].diferencia_cambiaria == Decimal("20.0000")
        assert asig_liq[2].diferencia_cambiaria == Decimal("0.0000")

        # Moneda doc == id_moneda_pais (VES) pagada en USD -> base de cálculo es monto_asignado_pago
        cxc_ves_pais = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("400.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=4),
        )
        asig_pais = aplicar_pago_a_documentos(
            pago_usd_extra,
            [
                {
                    "tipo_documento": "CUENTA_POR_COBRAR",
                    "id_documento": cxc_ves_pais.pk,
                    "monto_asignado_pago": "5.00",
                    "moneda_documento": "VES",
                    "tasa_aplicada": "40",
                    "tasa_original": "36",
                    "tasa_liquidacion": "40",
                }
            ],
            usuario=user_a,
        )[0]
        assert asig_pais.diferencia_cambiaria == Decimal("20.0000")

        # FIFO omitiendo obligación ya saldada con abono pero aún en estado parcial + contacto inactivo
        cxc_llena = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("10.00"),
            estado="parcial",
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=1),
        )
        AbonoCxC.objects.create(cuenta_por_cobrar=cxc_llena, monto=Decimal("10.00"), usuario=user_a)
        prop_llena = sugerir_distribucion_fifo(pago_usd_extra, tipo_documento="CUENTA_POR_COBRAR")
        assert all(p["id_documento"] != str(cxc_llena.pk) for p in prop_llena["propuestas"])

        # Cliente sin contacto / contacto inactivo / ADR-009 inválido / doc sin empresa
        cli_sin_c = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cli Sin Contacto",
            rif="J-99990001-1",
            contacto=None,
        )
        cxc_sin_c = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cli_sin_c,
            monto=Decimal("15.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=1),
        )
        with pytest.raises(ConciliacionPagoError, match="Contacto"):
            _resolver_contacto_documento(empresa_a, cxc_sin_c)

        proveedor_conn = ConectorProveedor.objects.create(
            codigo=f"odoo-err-{uuid.uuid4().hex[:6]}",
            nombre="Odoo Err",
            capacidades=["contactos"],
        )
        inst_err = ConectorInstancia.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_conn,
            nombre="Odoo Err Inst",
            estado="activo",
        )
        EntidadSincronizada.objects.create(
            id_instancia=inst_err,
            tipo_entidad="contactos",
            id_externo="ext-bad-uuid",
            id_omni="no-es-uuid",
            modelo_omni="apps.core.models.Contacto",
            activo=True,
        )
        EntidadSincronizada.objects.create(
            id_instancia=inst_err,
            tipo_entidad="contactos",
            id_externo="ext-missing-c",
            id_omni=str(uuid.uuid4()),
            modelo_omni="apps.core.models.Contacto",
            activo=True,
        )
        with pytest.raises(ConciliacionPagoError):
            _resolver_contacto_documento(
                empresa_a,
                CuentaPorCobrar.objects.create(
                    empresa=empresa_a,
                    cliente=None,
                    cliente_externo_id="   ",
                    monto=Decimal("5.00"),
                    fecha_emision=_hoy(),
                    fecha_vencimiento=_hoy(),
                ),
            )
        with pytest.raises(ConciliacionPagoError):
            _resolver_contacto_documento(
                empresa_a,
                CuentaPorCobrar.objects.create(
                    empresa=empresa_a,
                    cliente=None,
                    cliente_externo_id="ext-bad-uuid",
                    monto=Decimal("5.00"),
                    fecha_emision=_hoy(),
                    fecha_vencimiento=_hoy(),
                ),
            )
        with pytest.raises(ConciliacionPagoError):
            _resolver_contacto_documento(
                empresa_a,
                CuentaPorCobrar.objects.create(
                    empresa=empresa_a,
                    cliente=None,
                    cliente_externo_id="ext-missing-c",
                    monto=Decimal("5.00"),
                    fecha_emision=_hoy(),
                    fecha_vencimiento=_hoy(),
                ),
            )
        with pytest.raises(ConciliacionPagoError):
            _resolver_contacto_documento(empresa_a, pago_usd_extra)

        # Contacto inactivo rechazado en FIFO y en aplicar_pago
        contacto_cliente_a.activo = False
        contacto_cliente_a.save(update_fields=["activo"])
        with pytest.raises(ConciliacionPagoError, match="inactivo"):
            sugerir_distribucion_fifo(pago_usd_extra)
        with pytest.raises(ConciliacionPagoError, match="inactivo"):
            aplicar_pago_a_documentos(
                pago_usd_extra,
                [
                    {
                        "tipo_documento": "FACTURA_VENTA",
                        "id_documento": fv_fx_solo_liq.pk,
                        "monto_asignado_pago": "1.00",
                    }
                ],
            )
        contacto_cliente_a.activo = True
        contacto_cliente_a.save(update_fields=["activo"])

        # Reversión con asiento previamente ANULADO se omite limpiamente
        cuenta_act = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="1.1.01.99",
            nombre_cuenta="Caja Test Anul",
            tipo_cuenta="ACTIVO",
            naturaleza="DEUDORA",
            nivel=1,
        )
        asiento_pre_anulado = AsientoContable.objects.create(
            id_empresa=empresa_a,
            fecha_asiento=_hoy(),
            numero_asiento=f"PREANUL-{uuid.uuid4().hex[:6]}",
            descripcion="Pre anulado",
            estado_asiento="ANULADO",
        )
        DetalleAsiento.objects.create(
            id_asiento=asiento_pre_anulado, id_cuenta_contable=cuenta_act, debe=Decimal("1.00")
        )
        DetalleAsiento.objects.create(
            id_asiento=asiento_pre_anulado, id_cuenta_contable=cuenta_act, haber=Decimal("1.00")
        )
        asig_pre = asig_liq[0]
        asig_pre.id_asiento = asiento_pre_anulado
        asig_pre.save(update_fields=["id_asiento"])
        asig_rev_ret = revertir_asignacion_pago(asig_pre, usuario=user_a, motivo="Anulado previo")
        assert asig_rev_ret.id_asiento_reversion is None


@pytest.mark.django_db(transaction=True)
class TestConcurrenciaSelectForUpdate:
    def test_concurrencia_real_sobre_mismo_pago_no_sobreasigna(
        self, empresa_a, cliente_a, contacto_cliente_a, moneda_usd, metodo_efectivo, user_a
    ):
        fac1 = _crear_factura_venta(
            empresa_a, cliente_a, moneda_usd, numero="FV-CONC-1", monto_total=Decimal("100.0000")
        )
        fac2 = _crear_factura_venta(
            empresa_a, cliente_a, moneda_usd, numero="FV-CONC-2", monto_total=Decimal("100.0000")
        )
        pago = _crear_pago(
            empresa_a, moneda_usd, metodo_efectivo, monto=Decimal("100.0000"), contacto=contacto_cliente_a
        )

        def _aplicar(fac_pk):
            connections.close_all()
            try:
                aplicar_pago_a_documentos(
                    pago,
                    [{"tipo_documento": "FACTURA_VENTA", "id_documento": fac_pk, "monto_asignado_pago": "80.00"}],
                    usuario=user_a,
                )
                return "ok"
            except ConciliacionPagoError:
                return "error"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(_aplicar, [fac1.pk, fac2.pk]))

        assert sorted(resultados) == ["error", "ok"]
        assert AsignacionPago.objects.filter(id_pago=pago, estado="ACTIVA").count() == 1
        assert saldo_disponible_pago(pago) == Decimal("20.0000")
