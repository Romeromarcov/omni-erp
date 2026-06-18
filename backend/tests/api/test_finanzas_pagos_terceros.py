"""
Pagos de terceros (Zelle) — Capa B §6.6 (tropicalización VE).

Cobertura de integración del ciclo completo:

- abonar: la CxP del proveedor baja por el monto del cobro + asiento
  PAGO_TERCERO balanceado (montos verificados a mano).
- solicitar reintegro con comisión: CxC contra el proveedor por
  monto − comisión (puente ADR-009 ``cliente_externo_id="proveedor:<uuid>"``)
  + asiento balanceado por el neto.
- R-CODE-11: contabilidad activa sin MapeoContable PAGO_TERCERO → 422 y
  rollback TOTAL (ni abono, ni CxC, ni cambio de estado).
- Transiciones inválidas → 400.
- R-CODE-1: recursos de otra empresa → 404 (y POST con empresa ajena → 400).
- Idempotencia opt-in (cabecera ``Idempotency-Key``) en los POST de dinero.
- Tool MCP ``finanzas_pagos_terceros_pendientes`` (scope finanzas:read).
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.contabilidad.models import AsientoContable, DetalleAsiento
from apps.cuentas_por_cobrar.models import CuentaPorCobrar
from apps.cuentas_por_pagar.models import AbonoCxP, CuentaPorPagar
from apps.finanzas.models import PagoTercero

pytestmark = pytest.mark.django_db


def _today():
    return timezone.now().date()


BASE_URL = "/api/finanzas/pagos-terceros/"


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def proveedor_a(db, empresa_a):
    from apps.proveedores.models import Proveedor

    return Proveedor.objects.create(
        razon_social="Distribuidora Tercero C.A.",
        rif="J-22222222-2",
        id_empresa=empresa_a,
    )


@pytest.fixture
def proveedor_b(db, empresa_b):
    from apps.proveedores.models import Proveedor

    return Proveedor.objects.create(
        razon_social="Proveedor Ajeno S.A.",
        rif="J-33333333-3",
        id_empresa=empresa_b,
    )


@pytest.fixture
def cxp_proveedor_a(db, empresa_a, proveedor_a):
    return CuentaPorPagar.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor_a,
        monto_total=Decimal("1000.00"),
        monto_pendiente=Decimal("1000.00"),
        fecha_emision=_today(),
        fecha_vencimiento=_today() + timedelta(days=30),
        estado="PENDIENTE",
    )


@pytest.fixture
def pago_tercero_a(db, empresa_a, proveedor_a, moneda_usd):
    """Cobro USD de 750.50 que entró por la cuenta Zelle del proveedor A."""
    return PagoTercero.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor_a,
        id_moneda=moneda_usd,
        monto=Decimal("750.50"),
        referencia_zelle="ZELLE-REF-0001",
        fecha=_today(),
        concepto="Cobro de cliente final vía cuenta del proveedor",
    )


@pytest.fixture
def mapeo_pago_tercero(db, empresa_a):
    """PlanCuentas + MapeoContable PAGO_TERCERO para la empresa A."""
    from apps.contabilidad.models import MapeoContable, PlanCuentas

    debe = PlanCuentas.objects.create(
        id_empresa=empresa_a,
        codigo_cuenta="1.1.01",
        nombre_cuenta="CxP proveedores (terceros)",
        tipo_cuenta="PASIVO",
        naturaleza="ACREEDORA",
        nivel=1,
    )
    haber = PlanCuentas.objects.create(
        id_empresa=empresa_a,
        codigo_cuenta="1.1.02",
        nombre_cuenta="Fondos en cuentas de terceros",
        tipo_cuenta="ACTIVO",
        naturaleza="DEUDORA",
        nivel=1,
    )
    return MapeoContable.objects.create(
        id_empresa=empresa_a,
        tipo_asiento="PAGO_TERCERO",
        cuenta_debe=debe,
        cuenta_haber=haber,
    )


@pytest.fixture
def client_a(user_a):
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


def _asiento_de(pago):
    return AsientoContable.objects.filter(
        id_documento_origen=pago.pk, nombre_modelo_origen="PagoTercero"
    )


# ─────────────────────────────────────────────
# CRUD básico (creación tenant-safe)
# ─────────────────────────────────────────────


class TestCrearPagoTercero:
    def test_crear_pago_tercero(self, client_a, empresa_a, proveedor_a, moneda_usd):
        resp = client_a.post(
            BASE_URL,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_proveedor": str(proveedor_a.id_proveedor),
                "id_moneda": str(moneda_usd.id_moneda),
                "monto": "200.00",
                "referencia_zelle": "ZELLE-NEW-1",
                "fecha": str(_today()),
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["estado"] == "pendiente"
        assert Decimal(resp.data["monto"]) == Decimal("200.00")

    def test_crear_sin_proveedor_queda_pendiente(self, client_a, empresa_a, moneda_usd):
        """Un cobro originado en caja puede registrarse sin proveedor."""
        resp = client_a.post(
            BASE_URL,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_moneda": str(moneda_usd.id_moneda),
                "monto": "99.99",
                "referencia_zelle": "ZELLE-CAJA-1",
                "fecha": str(_today()),
            },
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert resp.data["id_proveedor"] is None

    def test_crear_con_empresa_ajena_retorna_400(self, client_a, empresa_b, proveedor_b, moneda_usd):
        """SEC-M1 / R-CODE-1: la FK de empresa está acotada a empresas visibles."""
        resp = client_a.post(
            BASE_URL,
            {
                "id_empresa": str(empresa_b.id_empresa),
                "id_proveedor": str(proveedor_b.id_proveedor),
                "id_moneda": str(moneda_usd.id_moneda),
                "monto": "10.00",
                "referencia_zelle": "ZELLE-HACK-1",
                "fecha": str(_today()),
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_monto_cero_retorna_400(self, client_a, empresa_a, moneda_usd):
        resp = client_a.post(
            BASE_URL,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_moneda": str(moneda_usd.id_moneda),
                "monto": "0.00",
                "referencia_zelle": "ZELLE-CERO",
                "fecha": str(_today()),
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_estado_no_es_escribible_por_payload(self, client_a, empresa_a, moneda_usd):
        """El ciclo de vida solo se mueve con las acciones, nunca con el POST."""
        resp = client_a.post(
            BASE_URL,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_moneda": str(moneda_usd.id_moneda),
                "monto": "50.00",
                "referencia_zelle": "ZELLE-EST",
                "fecha": str(_today()),
                "estado": "reintegrado",
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["estado"] == "pendiente"


# ─────────────────────────────────────────────
# Ciclo abonar (CxP baja + asiento balanceado)
# ─────────────────────────────────────────────


class TestAbonar:
    def test_ciclo_abonar_completo(
        self, client_a, pago_tercero_a, cxp_proveedor_a, mapeo_pago_tercero
    ):
        url = f"{BASE_URL}{pago_tercero_a.pk}/abonar/"
        resp = client_a.post(url, {"cxp": str(cxp_proveedor_a.pk)}, format="json")
        assert resp.status_code == 200, resp.data

        # Estado y trazabilidad del pago
        pago_tercero_a.refresh_from_db()
        assert pago_tercero_a.estado == "abonado"
        assert pago_tercero_a.id_abono_cxp is not None

        # La CxP del proveedor baja EXACTAMENTE por el monto del cobro:
        # 1000.00 − 750.50 = 249.50 (a mano)
        cxp_proveedor_a.refresh_from_db()
        assert cxp_proveedor_a.monto_pendiente == Decimal("249.50")
        assert cxp_proveedor_a.estado == "PARCIAL"
        abono = AbonoCxP.objects.get(pk=pago_tercero_a.id_abono_cxp_id)
        assert abono.monto == Decimal("750.50")
        assert abono.cuenta_por_pagar_id == cxp_proveedor_a.pk

        # Asiento PAGO_TERCERO balanceado: debe == haber == 750.50
        asiento = _asiento_de(pago_tercero_a).get()
        detalles = DetalleAsiento.objects.filter(id_asiento=asiento)
        assert detalles.count() == 2
        total_debe = sum(d.debe for d in detalles)
        total_haber = sum(d.haber for d in detalles)
        assert total_debe == Decimal("750.50")
        assert total_haber == Decimal("750.50")
        assert total_debe == total_haber

        # Respuesta del endpoint expone los montos como string (R-CODE-4)
        assert resp.data["cxp_monto_pendiente"] == "249.5000"
        assert resp.data["cxp_estado"] == "PARCIAL"

    def test_abonar_excede_saldo_cxp_retorna_400(
        self, client_a, empresa_a, proveedor_a, moneda_usd, mapeo_pago_tercero
    ):
        """El cobro (2000) excede la CxP (1000): el service de CxP lo rechaza."""
        pago = PagoTercero.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            id_moneda=moneda_usd,
            monto=Decimal("2000.00"),
            referencia_zelle="ZELLE-GRANDE",
            fecha=_today(),
        )
        cxp = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            monto_total=Decimal("1000.00"),
            monto_pendiente=Decimal("1000.00"),
            fecha_emision=_today(),
            fecha_vencimiento=_today() + timedelta(days=30),
            estado="PENDIENTE",
        )
        resp = client_a.post(f"{BASE_URL}{pago.pk}/abonar/", {"cxp": str(cxp.pk)}, format="json")
        assert resp.status_code == 400
        cxp.refresh_from_db()
        assert cxp.monto_pendiente == Decimal("1000.00")

    def test_abonar_sin_proveedor_retorna_400(self, client_a, empresa_a, moneda_usd, cxp_proveedor_a):
        pago = PagoTercero.objects.create(
            id_empresa=empresa_a,
            id_moneda=moneda_usd,
            monto=Decimal("100.00"),
            referencia_zelle="ZELLE-SINPROV",
            fecha=_today(),
        )
        resp = client_a.post(
            f"{BASE_URL}{pago.pk}/abonar/", {"cxp": str(cxp_proveedor_a.pk)}, format="json"
        )
        assert resp.status_code == 400

    def test_abonar_cxp_de_otro_proveedor_retorna_400(
        self, client_a, empresa_a, pago_tercero_a, mapeo_pago_tercero
    ):
        from apps.proveedores.models import Proveedor

        otro = Proveedor.objects.create(
            razon_social="Otro Proveedor C.A.", rif="J-44444444-4", id_empresa=empresa_a
        )
        cxp_otro = CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=otro,
            monto_total=Decimal("5000.00"),
            monto_pendiente=Decimal("5000.00"),
            fecha_emision=_today(),
            fecha_vencimiento=_today() + timedelta(days=30),
            estado="PENDIENTE",
        )
        resp = client_a.post(
            f"{BASE_URL}{pago_tercero_a.pk}/abonar/", {"cxp": str(cxp_otro.pk)}, format="json"
        )
        assert resp.status_code == 400

    def test_abonar_sin_cxp_retorna_400(self, client_a, pago_tercero_a):
        resp = client_a.post(f"{BASE_URL}{pago_tercero_a.pk}/abonar/", {}, format="json")
        assert resp.status_code == 400


# ─────────────────────────────────────────────
# Reintegro con comisión (CxC contra proveedor)
# ─────────────────────────────────────────────


class TestSolicitarReintegro:
    def test_reintegro_con_comision(self, client_a, pago_tercero_a, mapeo_pago_tercero, proveedor_a):
        url = f"{BASE_URL}{pago_tercero_a.pk}/solicitar-reintegro/"
        resp = client_a.post(url, {"comision": "25.75"}, format="json")
        assert resp.status_code == 200, resp.data

        pago_tercero_a.refresh_from_db()
        assert pago_tercero_a.estado == "reintegro_pendiente"
        assert pago_tercero_a.comision == Decimal("25.75")
        assert pago_tercero_a.id_cxc_reintegro is not None

        # CxC contra el proveedor por monto − comisión: 750.50 − 25.75 = 724.75
        cxc = CuentaPorCobrar.objects.get(pk=pago_tercero_a.id_cxc_reintegro_id)
        assert cxc.monto == Decimal("724.75")
        assert cxc.empresa_id == pago_tercero_a.id_empresa_id
        # Puente ADR-009: deudor identificado SIN crear crm.Cliente espejo
        assert cxc.cliente_id is None
        assert cxc.cliente_externo_id == f"proveedor:{proveedor_a.id_proveedor}"
        assert cxc.cliente_externo_nombre == proveedor_a.razon_social
        assert cxc.tipo_operacion == "REINTEGRO_PAGO_TERCERO"
        assert cxc.estado == "pendiente"
        assert cxc.documento_json["monto_cobro"] == "750.50"
        assert cxc.documento_json["comision"] == "25.75"

        # Asiento PAGO_TERCERO balanceado por el NETO del reintegro
        asiento = _asiento_de(pago_tercero_a).get()
        detalles = DetalleAsiento.objects.filter(id_asiento=asiento)
        assert sum(d.debe for d in detalles) == Decimal("724.75")
        assert sum(d.haber for d in detalles) == Decimal("724.75")

        assert resp.data["cxc_monto"] == "724.75"

    def test_reintegro_sin_comision(self, client_a, pago_tercero_a, mapeo_pago_tercero):
        url = f"{BASE_URL}{pago_tercero_a.pk}/solicitar-reintegro/"
        resp = client_a.post(url, {}, format="json")
        assert resp.status_code == 200, resp.data
        pago_tercero_a.refresh_from_db()
        cxc = CuentaPorCobrar.objects.get(pk=pago_tercero_a.id_cxc_reintegro_id)
        assert cxc.monto == Decimal("750.50")
        assert pago_tercero_a.comision == Decimal("0.00")

    def test_reintegro_comision_mayor_al_monto_retorna_400(
        self, client_a, pago_tercero_a, mapeo_pago_tercero
    ):
        url = f"{BASE_URL}{pago_tercero_a.pk}/solicitar-reintegro/"
        resp = client_a.post(url, {"comision": "750.50"}, format="json")
        assert resp.status_code == 400
        pago_tercero_a.refresh_from_db()
        assert pago_tercero_a.estado == "pendiente"
        assert CuentaPorCobrar.objects.count() == 0

    def test_reintegro_comision_negativa_retorna_400(
        self, client_a, pago_tercero_a, mapeo_pago_tercero
    ):
        url = f"{BASE_URL}{pago_tercero_a.pk}/solicitar-reintegro/"
        resp = client_a.post(url, {"comision": "-5.00"}, format="json")
        assert resp.status_code == 400

    def test_reintegro_fecha_vencimiento_explicita(self, client_a, pago_tercero_a, mapeo_pago_tercero):
        vence = _today() + timedelta(days=7)
        url = f"{BASE_URL}{pago_tercero_a.pk}/solicitar-reintegro/"
        resp = client_a.post(url, {"fecha_vencimiento": str(vence)}, format="json")
        assert resp.status_code == 200, resp.data
        pago_tercero_a.refresh_from_db()
        cxc = CuentaPorCobrar.objects.get(pk=pago_tercero_a.id_cxc_reintegro_id)
        assert cxc.fecha_vencimiento == vence

    def test_reintegro_fecha_emision_usa_localdate_caracas(
        self, client_a, pago_tercero_a, mapeo_pago_tercero
    ):
        # Hallazgo BAJO (auditoría 2026-06-10): la fecha del documento usaba UTC.
        # Con now()=02:00 UTC (= 22:00 Caracas del 14), la CxC de reintegro debe
        # emitirse con la fecha LOCAL (Caracas, 06-14), no la UTC (06-15).
        import datetime
        from unittest import mock

        now_utc = datetime.datetime(2026, 6, 15, 2, 0, 0, tzinfo=datetime.timezone.utc)
        caracas_hoy = datetime.date(2026, 6, 14)
        url = f"{BASE_URL}{pago_tercero_a.pk}/solicitar-reintegro/"
        with mock.patch("django.utils.timezone.now", return_value=now_utc):
            resp = client_a.post(url, {}, format="json")
        assert resp.status_code == 200, resp.data
        pago_tercero_a.refresh_from_db()
        cxc = CuentaPorCobrar.objects.get(pk=pago_tercero_a.id_cxc_reintegro_id)
        assert cxc.fecha_emision == caracas_hoy
        assert cxc.fecha_vencimiento == caracas_hoy + timedelta(days=30)


# ─────────────────────────────────────────────
# R-CODE-11: rollback total si falta mapeo (422)
# ─────────────────────────────────────────────


class TestRollbackSinMapeo:
    def test_abonar_sin_mapeo_contabilidad_activa_422_y_rollback(
        self, client_a, empresa_a, pago_tercero_a, cxp_proveedor_a
    ):
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])

        url = f"{BASE_URL}{pago_tercero_a.pk}/abonar/"
        resp = client_a.post(url, {"cxp": str(cxp_proveedor_a.pk)}, format="json")
        assert resp.status_code == 422

        # Rollback TOTAL: ni abono, ni saldo tocado, ni cambio de estado, ni asiento
        pago_tercero_a.refresh_from_db()
        cxp_proveedor_a.refresh_from_db()
        assert pago_tercero_a.estado == "pendiente"
        assert pago_tercero_a.id_abono_cxp is None
        assert cxp_proveedor_a.monto_pendiente == Decimal("1000.00")
        assert cxp_proveedor_a.estado == "PENDIENTE"
        assert AbonoCxP.objects.count() == 0
        assert _asiento_de(pago_tercero_a).count() == 0

    def test_reintegro_sin_mapeo_contabilidad_activa_422_y_rollback(
        self, client_a, empresa_a, pago_tercero_a
    ):
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])

        url = f"{BASE_URL}{pago_tercero_a.pk}/solicitar-reintegro/"
        resp = client_a.post(url, {"comision": "10.00"}, format="json")
        assert resp.status_code == 422

        pago_tercero_a.refresh_from_db()
        assert pago_tercero_a.estado == "pendiente"
        assert pago_tercero_a.id_cxc_reintegro is None
        assert pago_tercero_a.comision is None
        assert CuentaPorCobrar.objects.count() == 0
        assert _asiento_de(pago_tercero_a).count() == 0

    def test_abonar_sin_mapeo_contabilidad_inactiva_procede_sin_asiento(
        self, client_a, empresa_a, pago_tercero_a, cxp_proveedor_a
    ):
        """R-PROD-3 (bodega informal): sin contabilidad activa, la operación procede."""
        assert empresa_a.contabilidad_activa is False
        url = f"{BASE_URL}{pago_tercero_a.pk}/abonar/"
        resp = client_a.post(url, {"cxp": str(cxp_proveedor_a.pk)}, format="json")
        assert resp.status_code == 200, resp.data
        pago_tercero_a.refresh_from_db()
        assert pago_tercero_a.estado == "abonado"
        assert _asiento_de(pago_tercero_a).count() == 0


# ─────────────────────────────────────────────
# Transiciones inválidas → 400
# ─────────────────────────────────────────────


class TestTransicionesInvalidas:
    def test_abonar_dos_veces_retorna_400(
        self, client_a, pago_tercero_a, cxp_proveedor_a, mapeo_pago_tercero
    ):
        url = f"{BASE_URL}{pago_tercero_a.pk}/abonar/"
        assert client_a.post(url, {"cxp": str(cxp_proveedor_a.pk)}, format="json").status_code == 200
        resp = client_a.post(url, {"cxp": str(cxp_proveedor_a.pk)}, format="json")
        assert resp.status_code == 400
        # Solo un abono quedó registrado
        assert AbonoCxP.objects.count() == 1

    def test_reintegro_sobre_abonado_retorna_400(
        self, client_a, pago_tercero_a, cxp_proveedor_a, mapeo_pago_tercero
    ):
        client_a.post(
            f"{BASE_URL}{pago_tercero_a.pk}/abonar/", {"cxp": str(cxp_proveedor_a.pk)}, format="json"
        )
        resp = client_a.post(
            f"{BASE_URL}{pago_tercero_a.pk}/solicitar-reintegro/", {}, format="json"
        )
        assert resp.status_code == 400

    def test_marcar_reintegrado_sobre_pendiente_retorna_400(self, client_a, pago_tercero_a):
        resp = client_a.post(f"{BASE_URL}{pago_tercero_a.pk}/marcar-reintegrado/", {}, format="json")
        assert resp.status_code == 400

    def test_marcar_reintegrado_tras_reintegro_ok(
        self, client_a, pago_tercero_a, mapeo_pago_tercero
    ):
        client_a.post(f"{BASE_URL}{pago_tercero_a.pk}/solicitar-reintegro/", {"comision": "1.00"}, format="json")
        resp = client_a.post(f"{BASE_URL}{pago_tercero_a.pk}/marcar-reintegrado/", {}, format="json")
        assert resp.status_code == 200
        pago_tercero_a.refresh_from_db()
        assert pago_tercero_a.estado == "reintegrado"

    def test_asociar_proveedor_tras_abonar_retorna_400(
        self, client_a, pago_tercero_a, cxp_proveedor_a, proveedor_a, mapeo_pago_tercero
    ):
        client_a.post(
            f"{BASE_URL}{pago_tercero_a.pk}/abonar/", {"cxp": str(cxp_proveedor_a.pk)}, format="json"
        )
        resp = client_a.post(
            f"{BASE_URL}{pago_tercero_a.pk}/asociar-proveedor/",
            {"proveedor": str(proveedor_a.id_proveedor)},
            format="json",
        )
        assert resp.status_code == 400

    def test_anular_pendiente_ok_y_reanular_400(self, client_a, pago_tercero_a):
        url = f"{BASE_URL}{pago_tercero_a.pk}/anular/"
        resp = client_a.post(url, {}, format="json")
        assert resp.status_code == 200
        pago_tercero_a.refresh_from_db()
        assert pago_tercero_a.estado == "anulado"
        assert client_a.post(url, {}, format="json").status_code == 400

    def test_anular_tras_reintegro_retorna_400(self, client_a, pago_tercero_a, mapeo_pago_tercero):
        client_a.post(f"{BASE_URL}{pago_tercero_a.pk}/solicitar-reintegro/", {}, format="json")
        resp = client_a.post(f"{BASE_URL}{pago_tercero_a.pk}/anular/", {}, format="json")
        assert resp.status_code == 400

    def test_patch_sobre_abonado_retorna_400(
        self, client_a, pago_tercero_a, cxp_proveedor_a, mapeo_pago_tercero
    ):
        """La historia financiera es inmutable: PATCH tras mover dinero → 400."""
        client_a.post(
            f"{BASE_URL}{pago_tercero_a.pk}/abonar/", {"cxp": str(cxp_proveedor_a.pk)}, format="json"
        )
        resp = client_a.patch(
            f"{BASE_URL}{pago_tercero_a.pk}/", {"monto": "1.00"}, format="json"
        )
        assert resp.status_code == 400
        pago_tercero_a.refresh_from_db()
        assert pago_tercero_a.monto == Decimal("750.50")

    def test_patch_sobre_pendiente_si_es_editable(self, client_a, pago_tercero_a):
        resp = client_a.patch(
            f"{BASE_URL}{pago_tercero_a.pk}/", {"concepto": "corregido"}, format="json"
        )
        assert resp.status_code == 200
        pago_tercero_a.refresh_from_db()
        assert pago_tercero_a.concepto == "corregido"

    def test_delete_retorna_405(self, client_a, pago_tercero_a):
        """R-CODE-6: los documentos financieros se anulan, nunca se borran."""
        resp = client_a.delete(f"{BASE_URL}{pago_tercero_a.pk}/")
        assert resp.status_code == 405
        assert PagoTercero.objects.filter(pk=pago_tercero_a.pk).exists()


# ─────────────────────────────────────────────
# Asociar proveedor (cobro originado en caja)
# ─────────────────────────────────────────────


class TestAsociarProveedor:
    def test_asociar_proveedor_y_luego_abonar(
        self, client_a, empresa_a, proveedor_a, moneda_usd, cxp_proveedor_a, mapeo_pago_tercero
    ):
        pago = PagoTercero.objects.create(
            id_empresa=empresa_a,
            id_moneda=moneda_usd,
            monto=Decimal("300.00"),
            referencia_zelle="ZELLE-CAJA-2",
            fecha=_today(),
        )
        resp = client_a.post(
            f"{BASE_URL}{pago.pk}/asociar-proveedor/",
            {"proveedor": str(proveedor_a.id_proveedor)},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        pago.refresh_from_db()
        assert pago.id_proveedor_id == proveedor_a.id_proveedor

        resp = client_a.post(f"{BASE_URL}{pago.pk}/abonar/", {"cxp": str(cxp_proveedor_a.pk)}, format="json")
        assert resp.status_code == 200, resp.data
        cxp_proveedor_a.refresh_from_db()
        assert cxp_proveedor_a.monto_pendiente == Decimal("700.00")

    def test_asociar_proveedor_de_otra_empresa_retorna_404(
        self, client_a, empresa_a, moneda_usd, proveedor_b
    ):
        pago = PagoTercero.objects.create(
            id_empresa=empresa_a,
            id_moneda=moneda_usd,
            monto=Decimal("10.00"),
            referencia_zelle="ZELLE-CAJA-3",
            fecha=_today(),
        )
        resp = client_a.post(
            f"{BASE_URL}{pago.pk}/asociar-proveedor/",
            {"proveedor": str(proveedor_b.id_proveedor)},
            format="json",
        )
        assert resp.status_code == 404

    def test_asociar_sin_proveedor_retorna_400(self, client_a, pago_tercero_a):
        resp = client_a.post(f"{BASE_URL}{pago_tercero_a.pk}/asociar-proveedor/", {}, format="json")
        assert resp.status_code == 400


# ─────────────────────────────────────────────
# R-CODE-1: aislamiento multi-tenant → 404
# ─────────────────────────────────────────────


class TestAislamientoTenant:
    def test_usuario_b_no_ve_pago_de_empresa_a(self, client_b, pago_tercero_a):
        resp = client_b.get(f"{BASE_URL}{pago_tercero_a.pk}/")
        assert resp.status_code == 404

    def test_usuario_b_no_puede_abonar_pago_de_empresa_a(
        self, client_b, pago_tercero_a, cxp_proveedor_a
    ):
        resp = client_b.post(
            f"{BASE_URL}{pago_tercero_a.pk}/abonar/", {"cxp": str(cxp_proveedor_a.pk)}, format="json"
        )
        assert resp.status_code == 404
        pago_tercero_a.refresh_from_db()
        assert pago_tercero_a.estado == "pendiente"

    def test_usuario_b_no_puede_marcar_reintegrado(self, client_b, pago_tercero_a):
        resp = client_b.post(f"{BASE_URL}{pago_tercero_a.pk}/marcar-reintegrado/", {}, format="json")
        assert resp.status_code == 404

    def test_listado_no_filtra_pagos_ajenos(self, client_b, pago_tercero_a):
        resp = client_b.get(BASE_URL)
        assert resp.status_code == 200
        ids = [p["id_pago_tercero"] for p in resp.data["results"]]
        assert str(pago_tercero_a.pk) not in ids

    def test_abonar_con_cxp_de_otra_empresa_retorna_404(
        self, client_a, pago_tercero_a, empresa_b, proveedor_b, mapeo_pago_tercero
    ):
        cxp_ajena = CuentaPorPagar.objects.create(
            id_empresa=empresa_b,
            id_proveedor=proveedor_b,
            monto_total=Decimal("800.00"),
            monto_pendiente=Decimal("800.00"),
            fecha_emision=_today(),
            fecha_vencimiento=_today() + timedelta(days=30),
            estado="PENDIENTE",
        )
        resp = client_a.post(
            f"{BASE_URL}{pago_tercero_a.pk}/abonar/", {"cxp": str(cxp_ajena.pk)}, format="json"
        )
        assert resp.status_code == 404
        cxp_ajena.refresh_from_db()
        assert cxp_ajena.monto_pendiente == Decimal("800.00")


# ─────────────────────────────────────────────
# Idempotencia (P1-2) en los POST de dinero
# ─────────────────────────────────────────────


class TestIdempotencia:
    def test_abonar_reintento_con_misma_clave_no_duplica(
        self, client_a, pago_tercero_a, cxp_proveedor_a, mapeo_pago_tercero
    ):
        url = f"{BASE_URL}{pago_tercero_a.pk}/abonar/"
        body = {"cxp": str(cxp_proveedor_a.pk)}
        r1 = client_a.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="zelle-abono-001")
        assert r1.status_code == 200, r1.data
        r2 = client_a.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="zelle-abono-001")
        assert r2.status_code == 200

        # La respuesta se reproduce y NO se re-ejecuta la lógica de negocio
        assert r2.data["abono_id"] == r1.data["abono_id"]
        assert AbonoCxP.objects.count() == 1
        cxp_proveedor_a.refresh_from_db()
        assert cxp_proveedor_a.monto_pendiente == Decimal("249.50")
        from apps.contabilidad.models import AsientoContable

        assert AsientoContable.objects.filter(id_documento_origen=pago_tercero_a.pk).count() == 1

    def test_misma_clave_con_payload_distinto_retorna_422(
        self, client_a, pago_tercero_a, cxp_proveedor_a, empresa_a, proveedor_a, mapeo_pago_tercero
    ):
        url = f"{BASE_URL}{pago_tercero_a.pk}/abonar/"
        r1 = client_a.post(
            url, {"cxp": str(cxp_proveedor_a.pk)}, format="json", HTTP_IDEMPOTENCY_KEY="clave-x"
        )
        assert r1.status_code == 200
        r2 = client_a.post(
            url,
            {"cxp": str(cxp_proveedor_a.pk), "descripcion": "otro"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="clave-x",
        )
        assert r2.status_code == 422

    def test_reintegro_reintento_con_misma_clave_no_duplica(
        self, client_a, pago_tercero_a, mapeo_pago_tercero
    ):
        url = f"{BASE_URL}{pago_tercero_a.pk}/solicitar-reintegro/"
        body = {"comision": "25.75"}
        r1 = client_a.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="zelle-reintegro-001")
        assert r1.status_code == 200, r1.data
        r2 = client_a.post(url, body, format="json", HTTP_IDEMPOTENCY_KEY="zelle-reintegro-001")
        assert r2.status_code == 200
        assert r2.data["cxc_id"] == r1.data["cxc_id"]
        assert CuentaPorCobrar.objects.count() == 1

    def test_clave_fallida_no_se_consume(self, client_a, pago_tercero_a, cxp_proveedor_a):
        """Un 4xx no consume la clave: el reintento corregido puede ejecutarse."""
        url = f"{BASE_URL}{pago_tercero_a.pk}/abonar/"
        r1 = client_a.post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="clave-y")
        assert r1.status_code == 400
        r2 = client_a.post(
            url, {"cxp": str(cxp_proveedor_a.pk)}, format="json", HTTP_IDEMPOTENCY_KEY="clave-y"
        )
        assert r2.status_code == 200, r2.data


# ─────────────────────────────────────────────
# Service directo: locking/validaciones extra
# ─────────────────────────────────────────────


class TestServiceDirecto:
    def test_abonar_cxp_de_otra_empresa_falla_en_service(
        self, empresa_b, proveedor_b, pago_tercero_a, user_a
    ):
        """Defensa en profundidad: aunque una vista no filtre, el service exige tenant."""
        from apps.finanzas.services_pagos_terceros import PagoTerceroError, abonar_pago_tercero

        cxp_ajena = CuentaPorPagar.objects.create(
            id_empresa=empresa_b,
            id_proveedor=proveedor_b,
            monto_total=Decimal("100.00"),
            monto_pendiente=Decimal("100.00"),
            fecha_emision=_today(),
            fecha_vencimiento=_today() + timedelta(days=10),
            estado="PENDIENTE",
        )
        with pytest.raises(PagoTerceroError):
            abonar_pago_tercero(pago=pago_tercero_a, cxp=cxp_ajena, usuario=user_a)

    def test_asociar_proveedor_de_otra_empresa_falla_en_service(
        self, pago_tercero_a, proveedor_b
    ):
        from apps.finanzas.services_pagos_terceros import PagoTerceroError, asociar_proveedor

        with pytest.raises(PagoTerceroError):
            asociar_proveedor(pago_tercero_a, proveedor_b)


# ─────────────────────────────────────────────
# Tool MCP: finanzas_pagos_terceros_pendientes
# ─────────────────────────────────────────────


class TestMCPPagosTercerosPendientes:
    @pytest.fixture
    def token_a(self, empresa_a):
        from apps.core.models import CapabilityToken

        return CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="tok-finanzas",
            scopes=["finanzas:read"],
            activo=True,
        )

    def test_lista_solo_pendientes_y_reintegros(
        self, token_a, empresa_a, proveedor_a, moneda_usd, pago_tercero_a
    ):
        from apps.finanzas.mcp import finanzas_pagos_terceros_pendientes

        # Uno abonado (cerrado) que NO debe aparecer
        PagoTercero.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            id_moneda=moneda_usd,
            monto=Decimal("10.00"),
            referencia_zelle="ZELLE-CERRADO",
            fecha=_today(),
            estado="abonado",
        )
        # Uno en reintegro_pendiente que SÍ debe aparecer
        PagoTercero.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            id_moneda=moneda_usd,
            monto=Decimal("80.00"),
            comision=Decimal("4.00"),
            referencia_zelle="ZELLE-REINT",
            fecha=_today(),
            estado="reintegro_pendiente",
        )

        resultado = finanzas_pagos_terceros_pendientes(
            str(token_a.token), str(empresa_a.id_empresa)
        )
        estados = {r["estado"] for r in resultado}
        refs = {r["referencia_zelle"] for r in resultado}
        assert estados == {"pendiente", "reintegro_pendiente"}
        assert "ZELLE-CERRADO" not in refs
        # R-CODE-4: el monto viaja como Decimal, nunca float
        assert all(isinstance(r["monto"], Decimal) for r in resultado)

    def test_tenant_distinto_lanza_permission_error(self, token_a, empresa_b):
        from apps.finanzas.mcp import finanzas_pagos_terceros_pendientes

        with pytest.raises(PermissionError):
            finanzas_pagos_terceros_pendientes(str(token_a.token), str(empresa_b.id_empresa))

    def test_scope_insuficiente_lanza_permission_error(self, empresa_a):
        from apps.core.models import CapabilityToken
        from apps.finanzas.mcp import finanzas_pagos_terceros_pendientes

        token = CapabilityToken.objects.create(
            empresa=empresa_a, nombre="tok-crm", scopes=["crm:read"], activo=True
        )
        with pytest.raises(PermissionError):
            finanzas_pagos_terceros_pendientes(str(token.token), str(empresa_a.id_empresa))
