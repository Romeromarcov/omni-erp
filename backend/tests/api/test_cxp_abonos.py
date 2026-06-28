"""
Tests para el ciclo completo de Cuentas por Pagar:
- AbonoCxP model
- registrar_abono_cxp() service
- calcular_aging_cxp() service
- Endpoint /abonar/
- Endpoint /aging/
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.cuentas_por_pagar.models import AbonoCxP, CuentaPorPagar
from apps.cuentas_por_pagar.services import AbonoCxPError, calcular_aging_cxp, registrar_abono_cxp


def _today():
    return timezone.now().date()


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def proveedor_a(db, empresa_a):
    from apps.proveedores.models import Proveedor

    return Proveedor.objects.create(
        razon_social="Proveedor Alpha S.A.",
        rif="J-11111111-1",
        id_empresa=empresa_a,
    )


@pytest.fixture
def orden_compra_a(db, empresa_a, proveedor_a):
    from apps.compras.models import OrdenCompra

    return OrdenCompra.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor_a,
        numero_orden="OC-2026-001",
        fecha_orden=_today(),
        estado="APROBADA",
    )


@pytest.fixture
def factura_compra_a(db, empresa_a, orden_compra_a):
    from apps.compras.models import FacturaCompra

    return FacturaCompra.objects.create(
        id_empresa=empresa_a,
        id_orden_compra=orden_compra_a,
        numero_factura="FC-2026-001",
        fecha_emision=_today(),
        monto_total=Decimal("1000.00"),
    )


@pytest.fixture
def cxp_pendiente(db, empresa_a, proveedor_a, factura_compra_a):
    return CuentaPorPagar.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor_a,
        id_factura_compra=factura_compra_a,
        monto_total=Decimal("1000.00"),
        monto_pendiente=Decimal("1000.00"),
        fecha_emision=_today(),
        fecha_vencimiento=_today() + timedelta(days=30),
        estado="PENDIENTE",
    )


@pytest.fixture
def cxp_vencida(db, empresa_a, proveedor_a, factura_compra_a):
    return CuentaPorPagar.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor_a,
        id_factura_compra=factura_compra_a,
        monto_total=Decimal("500.00"),
        monto_pendiente=Decimal("500.00"),
        fecha_emision=_today() - timedelta(days=60),
        fecha_vencimiento=_today() - timedelta(days=30),
        estado="VENCIDA",
    )


# ─────────────────────────────────────────────
# Tests de modelo
# ─────────────────────────────────────────────


class TestAbonoCxPModel:
    def test_abono_se_crea_correctamente(self, db, cxp_pendiente, user_a):
        abono = AbonoCxP.objects.create(
            cuenta_por_pagar=cxp_pendiente,
            monto=Decimal("200.00"),
            usuario=user_a,
            descripcion="Pago parcial",
        )
        assert abono.pk is not None
        assert abono.monto == Decimal("200.0000")
        assert str(abono) != ""

    def test_abono_relacionado_con_cxp(self, db, cxp_pendiente, user_a):
        AbonoCxP.objects.create(
            cuenta_por_pagar=cxp_pendiente,
            monto=Decimal("100.00"),
            usuario=user_a,
        )
        assert cxp_pendiente.abonos.count() == 1


# ─────────────────────────────────────────────
# Tests de service registrar_abono_cxp
# ─────────────────────────────────────────────


class TestRegistrarAbonoCxP:
    def test_abono_parcial_actualiza_pendiente(self, db, cxp_pendiente, user_a):
        registrar_abono_cxp(cxp_pendiente, Decimal("300.00"), user_a)
        cxp_pendiente.refresh_from_db()
        assert cxp_pendiente.monto_pendiente == Decimal("700.0000")
        assert cxp_pendiente.estado == "PARCIAL"

    def test_abono_total_marca_pagada(self, db, cxp_pendiente, user_a):
        registrar_abono_cxp(cxp_pendiente, Decimal("1000.00"), user_a)
        cxp_pendiente.refresh_from_db()
        assert cxp_pendiente.monto_pendiente == Decimal("0.0000")
        assert cxp_pendiente.estado == "PAGADA"

    def test_abono_cero_lanza_error(self, db, cxp_pendiente, user_a):
        with pytest.raises(AbonoCxPError):
            registrar_abono_cxp(cxp_pendiente, Decimal("0"), user_a)

    def test_abono_negativo_lanza_error(self, db, cxp_pendiente, user_a):
        with pytest.raises(AbonoCxPError):
            registrar_abono_cxp(cxp_pendiente, Decimal("-50"), user_a)

    def test_abono_excede_saldo_lanza_error(self, db, cxp_pendiente, user_a):
        with pytest.raises(AbonoCxPError):
            registrar_abono_cxp(cxp_pendiente, Decimal("9999.00"), user_a)

    def test_abono_sobre_cxp_pagada_lanza_error(self, db, cxp_pendiente, user_a):
        registrar_abono_cxp(cxp_pendiente, Decimal("1000.00"), user_a)
        cxp_pendiente.refresh_from_db()
        with pytest.raises(AbonoCxPError):
            registrar_abono_cxp(cxp_pendiente, Decimal("1.00"), user_a)

    def test_abono_sobre_cxp_anulada_lanza_error(self, db, cxp_pendiente, user_a):
        cxp_pendiente.estado = "ANULADA"
        cxp_pendiente.save()
        with pytest.raises(AbonoCxPError):
            registrar_abono_cxp(cxp_pendiente, Decimal("100.00"), user_a)

    def test_abonos_multiples_acumulan(self, db, cxp_pendiente, user_a):
        registrar_abono_cxp(cxp_pendiente, Decimal("300.00"), user_a)
        registrar_abono_cxp(cxp_pendiente, Decimal("300.00"), user_a)
        cxp_pendiente.refresh_from_db()
        assert cxp_pendiente.monto_pendiente == Decimal("400.0000")
        assert cxp_pendiente.abonos.count() == 2


# ─────────────────────────────────────────────
# Tests de service calcular_aging_cxp
# ─────────────────────────────────────────────


class TestCalcularAgingCxP:
    def test_aging_corriente(self, db, cxp_pendiente, empresa_a):
        resultado = calcular_aging_cxp(empresa_a.id_empresa)
        assert resultado["corriente"]["count"] == 1
        assert resultado["corriente"]["total"] == Decimal("1000.0000")

    def test_aging_vencida_30_dias(self, db, cxp_vencida, empresa_a):
        resultado = calcular_aging_cxp(empresa_a.id_empresa)
        assert resultado["dias_1_30"]["count"] == 1
        assert resultado["dias_1_30"]["total"] == Decimal("500.0000")

    def test_aging_total_general(self, db, cxp_pendiente, cxp_vencida, empresa_a):
        resultado = calcular_aging_cxp(empresa_a.id_empresa)
        assert resultado["total_general"] == Decimal("1500.0000")

    def test_aging_excluye_empresa_b(self, db, empresa_b, cxp_pendiente):
        resultado = calcular_aging_cxp(empresa_b.id_empresa)
        assert resultado["total_general"] == Decimal("0")

    def test_aging_excluye_pagadas(self, db, cxp_pendiente, user_a, empresa_a):
        registrar_abono_cxp(cxp_pendiente, Decimal("1000.00"), user_a)
        resultado = calcular_aging_cxp(empresa_a.id_empresa)
        assert resultado["corriente"]["count"] == 0
        assert resultado["total_general"] == Decimal("0")

    def test_aging_vence_hoy_caracas_es_corriente(
        self, db, empresa_a, proveedor_a, factura_compra_a
    ):
        # Hallazgo BAJO (auditoría 2026-06-10): el aging usaba la fecha UTC.
        # Congelamos now() a las 02:00 UTC (= 22:00 Caracas del día anterior),
        # la ventana que fallaba: una CxP que vence HOY en Caracas debe quedar
        # en "corriente" (0 días), no en "dias_1_30" como daría la fecha UTC.
        import datetime
        from unittest import mock

        now_utc = datetime.datetime(2026, 6, 15, 2, 0, 0, tzinfo=datetime.timezone.utc)
        caracas_hoy = datetime.date(2026, 6, 14)
        CuentaPorPagar.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor_a,
            id_factura_compra=factura_compra_a,
            monto_total=Decimal("300.00"),
            monto_pendiente=Decimal("300.00"),
            fecha_emision=caracas_hoy,
            fecha_vencimiento=caracas_hoy,  # vence hoy en Caracas
            estado="PENDIENTE",
        )

        with mock.patch("django.utils.timezone.now", return_value=now_utc):
            resultado = calcular_aging_cxp(empresa_a.id_empresa)

        assert resultado["corriente"]["count"] == 1
        assert resultado["corriente"]["total"] == Decimal("300.0000")
        assert resultado["dias_1_30"]["count"] == 0


# ─────────────────────────────────────────────
# Tests de endpoints REST
# ─────────────────────────────────────────────


class TestCxPEndpoints:
    @pytest.fixture
    def client_a(self, user_a):
        from rest_framework.test import APIClient

        c = APIClient()
        c.force_authenticate(user=user_a)
        return c

    def test_abonar_endpoint_parcial(self, db, cxp_pendiente, client_a):
        url = f"/api/cuentas-por-pagar/cuentas-por-pagar/{cxp_pendiente.pk}/abonar/"
        resp = client_a.post(url, {"monto": "400.00"}, format="json")
        assert resp.status_code == 201
        assert resp.data["estado_cxp"] == "PARCIAL"
        assert Decimal(resp.data["monto_pendiente"]) == Decimal("600.00")

    def test_abonar_endpoint_total(self, db, cxp_pendiente, client_a):
        url = f"/api/cuentas-por-pagar/cuentas-por-pagar/{cxp_pendiente.pk}/abonar/"
        resp = client_a.post(url, {"monto": "1000.00"}, format="json")
        assert resp.status_code == 201
        assert resp.data["estado_cxp"] == "PAGADA"

    def test_abonar_monto_excesivo_retorna_400(self, db, cxp_pendiente, client_a):
        url = f"/api/cuentas-por-pagar/cuentas-por-pagar/{cxp_pendiente.pk}/abonar/"
        resp = client_a.post(url, {"monto": "9999.00"}, format="json")
        assert resp.status_code == 400

    def test_aging_endpoint(self, db, cxp_pendiente, client_a, empresa_a):
        url = f"/api/cuentas-por-pagar/cuentas-por-pagar/aging/?empresa={empresa_a.id_empresa}"
        resp = client_a.get(url)
        assert resp.status_code == 200
        assert "corriente" in resp.data
        assert "total_general" in resp.data

    def test_aging_sin_empresa_retorna_400(self, db, client_a):
        resp = client_a.get("/api/cuentas-por-pagar/cuentas-por-pagar/aging/")
        assert resp.status_code == 400


# ─────────────────────────────────────────────
# Asiento PAGO_CXP (R-CODE-11)
# ─────────────────────────────────────────────


def _cuenta(empresa, codigo, nombre, tipo, naturaleza):
    from apps.contabilidad.models import PlanCuentas

    return PlanCuentas.objects.create(
        id_empresa=empresa, codigo_cuenta=codigo, nombre_cuenta=nombre,
        tipo_cuenta=tipo, naturaleza=naturaleza, nivel=1,
    )


def _mapeo_pago_cxp(empresa):
    from apps.contabilidad.models import MapeoContable

    debe = _cuenta(empresa, "2101", "CxP Proveedores", "PASIVO", "ACREEDORA")
    haber = _cuenta(empresa, "1101", "Banco", "ACTIVO", "DEUDORA")
    return MapeoContable.objects.create(
        id_empresa=empresa, tipo_asiento="PAGO_CXP", cuenta_debe=debe,
        cuenta_haber=haber, descripcion_plantilla="Pago CxP - {numero}", activo=True,
    )


class TestAsientoPagoCxP:
    def test_abono_genera_asiento_pago_cxp(self, db, cxp_pendiente, user_a, empresa_a):
        from apps.contabilidad.models import AsientoContable

        _mapeo_pago_cxp(empresa_a)
        registrar_abono_cxp(cxp_pendiente, Decimal("400.00"), user_a)
        asiento = AsientoContable.objects.get(nombre_modelo_origen="AbonoCxP")
        assert asiento.id_usuario_registro == user_a
        detalles = list(asiento.detalleasiento_set.all())
        assert sum(d.debe for d in detalles) == sum(d.haber for d in detalles) == Decimal("400.00")

    def test_abono_sin_mapeo_no_falla(self, db, cxp_pendiente, user_a):
        """Empresa informal sin mapeo (R-PROD-3): el abono procede sin asiento."""
        from apps.contabilidad.models import AsientoContable

        registrar_abono_cxp(cxp_pendiente, Decimal("400.00"), user_a)
        cxp_pendiente.refresh_from_db()
        assert cxp_pendiente.monto_pendiente == Decimal("600.00")
        assert not AsientoContable.objects.filter(nombre_modelo_origen="AbonoCxP").exists()

    def test_generar_asiento_false_omite_asiento(self, db, cxp_pendiente, user_a, empresa_a):
        """Flujos con asiento propio (pago de tercero) pasan generar_asiento=False:
        el abono se aplica pero NO se postea PAGO_CXP, ni con mapeo y contabilidad
        activa — evita el doble cargo a la CxP."""
        from apps.contabilidad.models import AsientoContable

        _mapeo_pago_cxp(empresa_a)
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])
        registrar_abono_cxp(cxp_pendiente, Decimal("400.00"), user_a, generar_asiento=False)
        cxp_pendiente.refresh_from_db()
        assert cxp_pendiente.monto_pendiente == Decimal("600.00")
        assert not AsientoContable.objects.filter(nombre_modelo_origen="AbonoCxP").exists()


class TestAbonoCxPReadOnly:
    """La deuda 'AbonoCxP CRUD libre': el endpoint es de solo lectura."""

    @pytest.fixture
    def client_a(self, user_a):
        from rest_framework.test import APIClient

        c = APIClient()
        c.force_authenticate(user=user_a)
        return c

    def test_post_directo_bloqueado_405(self, db, cxp_pendiente, client_a):
        resp = client_a.post(
            "/api/cuentas-por-pagar/abonos-cxp/",
            {"cuenta_por_pagar": str(cxp_pendiente.pk), "monto": "100.00"},
            format="json",
        )
        assert resp.status_code == 405

    def test_list_solo_lectura_ok(self, db, cxp_pendiente, user_a, client_a):
        registrar_abono_cxp(cxp_pendiente, Decimal("100.00"), user_a)
        resp = client_a.get("/api/cuentas-por-pagar/abonos-cxp/")
        assert resp.status_code == 200


# ─────────────────────────────────────────────
# Diferencia cambiaria (multi-tasa) — T06
# ─────────────────────────────────────────────


def _mapeos_diferencia(empresa):
    """Configura PAGO_CXP + GANANCIA/PERDIDA_CAMBIARIA para una empresa."""
    from apps.contabilidad.models import MapeoContable

    _mapeo_pago_cxp(empresa)
    perd_d = _cuenta(empresa, "5701", "Pérdida Cambiaria", "GASTO", "DEUDORA")
    perd_h = _cuenta(empresa, "1101b", "Banco Dif", "ACTIVO", "DEUDORA")
    gan_d = _cuenta(empresa, "2101b", "CxP Dif", "PASIVO", "ACREEDORA")
    gan_h = _cuenta(empresa, "4701", "Ganancia Cambiaria", "INGRESO", "ACREEDORA")
    MapeoContable.objects.create(
        id_empresa=empresa, tipo_asiento="PERDIDA_CAMBIARIA", cuenta_debe=perd_d,
        cuenta_haber=perd_h, descripcion_plantilla="Pérdida cambiaria", activo=True,
    )
    MapeoContable.objects.create(
        id_empresa=empresa, tipo_asiento="GANANCIA_CAMBIARIA", cuenta_debe=gan_d,
        cuenta_haber=gan_h, descripcion_plantilla="Ganancia cambiaria", activo=True,
    )


class TestDiferenciaCambiaria:
    def test_pago_a_tasa_mayor_genera_perdida(self, db, cxp_pendiente, user_a, empresa_a):
        from apps.cuentas_por_pagar.models import DiferenciaCambiaria
        from apps.cuentas_por_pagar.services import registrar_abono_cxp

        _mapeos_diferencia(empresa_a)
        # CxP en divisa: pago de 100 a tasa 40 vs reconocida a 36 → pérdida 100*4=400
        registrar_abono_cxp(
            cxp_pendiente, Decimal("100.00"), user_a,
            tasa_original=Decimal("36"), tasa_pago=Decimal("40"),
        )
        dif = DiferenciaCambiaria.objects.get(id_empresa=empresa_a)
        assert dif.tipo == "PERDIDA"
        assert dif.monto_diferencia == Decimal("400.0000")

    def test_pago_a_tasa_menor_genera_ganancia(self, db, cxp_pendiente, user_a, empresa_a):
        from apps.cuentas_por_pagar.models import DiferenciaCambiaria
        from apps.cuentas_por_pagar.services import registrar_abono_cxp

        _mapeos_diferencia(empresa_a)
        registrar_abono_cxp(
            cxp_pendiente, Decimal("100.00"), user_a,
            tasa_original=Decimal("40"), tasa_pago=Decimal("36"),
        )
        dif = DiferenciaCambiaria.objects.get(id_empresa=empresa_a)
        assert dif.tipo == "GANANCIA"
        assert dif.monto_diferencia == Decimal("400.0000")

    def test_asiento_diferencia_cuadrado(self, db, cxp_pendiente, user_a, empresa_a):
        from apps.contabilidad.models import AsientoContable
        from apps.cuentas_por_pagar.services import registrar_abono_cxp

        _mapeos_diferencia(empresa_a)
        registrar_abono_cxp(
            cxp_pendiente, Decimal("100.00"), user_a,
            tasa_original=Decimal("36"), tasa_pago=Decimal("40"),
        )
        asiento = AsientoContable.objects.get(nombre_modelo_origen="DiferenciaCambiaria")
        detalles = list(asiento.detalleasiento_set.all())
        assert sum(d.debe for d in detalles) == sum(d.haber for d in detalles) == Decimal("400.00")

    def test_tasas_iguales_sin_diferencia(self, db, cxp_pendiente, user_a, empresa_a):
        from apps.cuentas_por_pagar.models import DiferenciaCambiaria
        from apps.cuentas_por_pagar.services import registrar_abono_cxp

        _mapeos_diferencia(empresa_a)
        registrar_abono_cxp(
            cxp_pendiente, Decimal("100.00"), user_a,
            tasa_original=Decimal("36"), tasa_pago=Decimal("36"),
        )
        assert not DiferenciaCambiaria.objects.filter(id_empresa=empresa_a).exists()

    def test_sin_tasas_sin_diferencia(self, db, cxp_pendiente, user_a, empresa_a):
        from apps.cuentas_por_pagar.models import DiferenciaCambiaria
        from apps.cuentas_por_pagar.services import registrar_abono_cxp

        _mapeo_pago_cxp(empresa_a)
        registrar_abono_cxp(cxp_pendiente, Decimal("100.00"), user_a)
        assert not DiferenciaCambiaria.objects.filter(id_empresa=empresa_a).exists()

    def test_tasa_no_positiva_en_servicio_lanza_error(self, db, cxp_pendiente, user_a):
        """Defensa en profundidad: el helper rechaza tasas no positivas."""
        from apps.cuentas_por_pagar.models import AbonoCxP
        from apps.cuentas_por_pagar.services import (
            AbonoCxPError,
            registrar_diferencia_cambiaria_cxp,
        )

        abono = AbonoCxP.objects.create(
            cuenta_por_pagar=cxp_pendiente, monto=Decimal("100.00"), usuario=user_a
        )
        with pytest.raises(AbonoCxPError, match="mayores a cero"):
            registrar_diferencia_cambiaria_cxp(abono, Decimal("100"), Decimal("0"), Decimal("40"))


class TestDiferenciaCambiariaEndpoint:
    @pytest.fixture
    def client_a(self, user_a):
        from rest_framework.test import APIClient

        c = APIClient()
        c.force_authenticate(user=user_a)
        return c

    def test_abonar_con_tasas_devuelve_diferencia(self, db, cxp_pendiente, client_a, empresa_a):
        _mapeos_diferencia(empresa_a)
        url = f"/api/cuentas-por-pagar/cuentas-por-pagar/{cxp_pendiente.pk}/abonar/"
        resp = client_a.post(
            url, {"monto": "100.00", "tasa_original": "36", "tasa_pago": "40"}, format="json"
        )
        assert resp.status_code == 201
        assert resp.data["diferencia_cambiaria"]["tipo"] == "PERDIDA"
        assert resp.data["diferencia_cambiaria"]["monto"] == "400.0000"

    def test_abonar_sin_tasas_diferencia_null(self, db, cxp_pendiente, client_a, empresa_a):
        _mapeo_pago_cxp(empresa_a)
        url = f"/api/cuentas-por-pagar/cuentas-por-pagar/{cxp_pendiente.pk}/abonar/"
        resp = client_a.post(url, {"monto": "100.00"}, format="json")
        assert resp.status_code == 201
        assert resp.data["diferencia_cambiaria"] is None

    def test_abonar_tasa_invalida_400(self, db, cxp_pendiente, client_a):
        url = f"/api/cuentas-por-pagar/cuentas-por-pagar/{cxp_pendiente.pk}/abonar/"
        resp = client_a.post(url, {"monto": "100.00", "tasa_pago": "-1"}, format="json")
        assert resp.status_code == 400
