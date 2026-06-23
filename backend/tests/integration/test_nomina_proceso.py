"""
TEST-5 — Flujo de nómina LOTTT: período → proceso → procesar → recibos + asiento.

Cierra la parte de nómina de CTF-013: `ProcesoNominaViewSet.procesar` deja de ser
stub y orquesta el cálculo LOTTT (`apps.nomina.calculo_lottt`) para cada empleado
activo, persiste `Nomina` + `DetalleNomina`, totaliza el proceso y genera el
asiento contable `NOMINA` (R-CODE-11) — todo en UNA transacción atómica.

Montos verificados A MANO (Decimal exacto, HALF_UP a centavos):

Empleado 1 — Ana Alvarez, salario 3000.00, 30 días, sin extras, cestaticket 40.00:
    salario_periodo = 3000.00          devengado salarial = 3000.00
    SSO 4% = 120.00 · FAOV 1% = 30.00 · RPE 0.5% = 15.00 · ISLR = 0
    total deducciones = 165.00
    asignaciones = 3000 + 40 = 3040.00 · neto = 2875.00
    aportes patronales: SSO 9% = 270.00, FAOV 2% = 60.00, INCES 2% = 60.00, RPE 2% = 60.00

Empleado 2 — Bruno Bravo, salario 1500.00, 30 días, 10 h extra diurnas (+50%):
    valor hora = 1500/180 · HED = 10 × (1500/180) × 1.5 = 125.00
    devengado salarial = 1625.00
    SSO = 65.00 · FAOV = 16.25 · RPE = 8.125 → 8.13 (HALF_UP) · ISLR = 0
    total deducciones = 89.38
    asignaciones = 1625 + 40 = 1665.00 · neto = 1575.62

Totales del proceso: devengado 4705.00 · deducciones 254.38 · neto 4450.62.
Asiento NOMINA balanceado: debe = haber = 4450.62.
"""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.configuracion_motor.models import ParametroSistema
from apps.contabilidad.models import AsientoContable, DetalleAsiento, MapeoContable, PlanCuentas
from apps.nomina.models import DetalleNomina, Nomina, PeriodoNomina, ProcesoNomina
from apps.rrhh.models import Empleado

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

BASE = "/api/nomina/procesos-nomina/"


# ── Helpers / fixtures ─────────────────────────────────────────────────────────


def _cuenta(empresa, codigo, nombre, tipo="GASTO", naturaleza="DEUDORA"):
    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=nombre,
        tipo_cuenta=tipo,
        naturaleza=naturaleza,
        nivel=1,
    )


def _mapeo_nomina(empresa):
    debe = _cuenta(empresa, "5101", "Gasto de Nómina", "GASTO", "DEUDORA")
    haber = _cuenta(empresa, "2102", "Nómina por Pagar", "PASIVO", "ACREEDORA")
    return MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento="NOMINA",
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla="Asiento NOMINA {numero}",
        activo=True,
    )


def _param(empresa, codigo, valor):
    return ParametroSistema.objects.create(
        id_empresa=empresa,
        nombre_parametro=codigo,
        codigo_parametro=codigo,
        valor_parametro=valor,
        tipo_dato="NUMERO",
        activo=True,
    )


@pytest.fixture
def periodo_a(empresa_a):
    return PeriodoNomina.objects.create(
        id_empresa=empresa_a,
        nombre_periodo="Junio 2026",
        fecha_inicio=datetime.date(2026, 6, 1),
        fecha_fin=datetime.date(2026, 6, 30),
        fecha_pago=datetime.date(2026, 7, 1),
        tipo_periodo="MENSUAL",
        estado="ABIERTO",
        activo=True,
    )


@pytest.fixture
def proceso_a(empresa_a, periodo_a):
    return ProcesoNomina.objects.create(
        id_empresa=empresa_a,
        id_periodo_nomina=periodo_a,
        numero_proceso="PROC-NOM-001",
        fecha_proceso=timezone.now(),
        estado="EN_PROCESO",
    )


@pytest.fixture
def empleado_ana(empresa_a):
    """Salario mensual 3000.00 vía documento_json (puente hasta que rrhh lo modele)."""
    return Empleado.objects.create(
        empresa=empresa_a,
        nombre="Ana",
        apellido="Alvarez",
        cedula="V-11111111",
        fecha_ingreso=datetime.date(2024, 1, 15),
        documento_json={"salario_mensual": "3000.00"},
    )


@pytest.fixture
def empleado_bruno(empresa_a):
    """Salario mensual 1500.00; en el happy path recibe 10 h extra diurnas."""
    return Empleado.objects.create(
        empresa=empresa_a,
        nombre="Bruno",
        apellido="Bravo",
        cedula="V-22222222",
        fecha_ingreso=datetime.date(2025, 2, 1),
        documento_json={"salario_mensual": "1500.00"},
    )


@pytest.fixture
def empresa_contable(empresa_a):
    empresa_a.contabilidad_activa = True
    empresa_a.save(update_fields=["contabilidad_activa"])
    return empresa_a


# ── Camino feliz: 2 empleados, montos exactos, asiento balanceado ──────────────


class TestProcesarFeliz:
    @pytest.fixture
    def respuesta(self, client_a, empresa_contable, proceso_a, empleado_ana, empleado_bruno):
        _mapeo_nomina(empresa_contable)
        _param(empresa_contable, "nomina.cestaticket_mensual", "40.00")
        return client_a.post(
            f"{BASE}{proceso_a.id_proceso_nomina}/procesar/",
            {"empleados": {str(empleado_bruno.pk): {"horas_extra_diurnas": "10"}}},
            format="json",
        )

    def test_responde_200_con_totales_exactos(self, respuesta):
        assert respuesta.status_code == 200, respuesta.json()
        data = respuesta.json()
        assert data["estado"] == "COMPLETADO"
        assert data["total_empleados"] == 2
        assert Decimal(data["total_devengado"]) == Decimal("4705.00")
        assert Decimal(data["total_deducciones"]) == Decimal("254.38")
        assert Decimal(data["total_neto"]) == Decimal("4450.62")
        assert data["asiento_contable"] is not None

    def test_recibos_persistidos_con_montos_exactos(self, respuesta, proceso_a, empleado_ana, empleado_bruno):
        assert respuesta.status_code == 200
        nomina_ana = Nomina.objects.get(id_proceso_nomina=proceso_a, id_empleado=empleado_ana)
        assert nomina_ana.sueldo_base == Decimal("3000.00")
        assert nomina_ana.total_devengado == Decimal("3040.00")
        assert nomina_ana.total_deducciones == Decimal("165.00")
        assert nomina_ana.total_neto == Decimal("2875.00")
        assert nomina_ana.estado == "CALCULADA"

        nomina_bruno = Nomina.objects.get(id_proceso_nomina=proceso_a, id_empleado=empleado_bruno)
        assert nomina_bruno.sueldo_base == Decimal("1500.00")
        assert nomina_bruno.total_devengado == Decimal("1665.00")
        assert nomina_bruno.total_deducciones == Decimal("89.38")
        assert nomina_bruno.total_neto == Decimal("1575.62")
        assert nomina_bruno.horas_extras == Decimal("10.00")

    def test_detalles_deducciones_y_aportes_exactos(self, respuesta, proceso_a, empleado_bruno):
        assert respuesta.status_code == 200
        nomina = Nomina.objects.get(id_proceso_nomina=proceso_a, id_empleado=empleado_bruno)
        detalles = {
            d.id_concepto_nomina.codigo_concepto: d.valor_total
            for d in DetalleNomina.objects.filter(id_nomina=nomina).select_related("id_concepto_nomina")
        }
        assert detalles["SUELDO"] == Decimal("1500.00")
        assert detalles["HED"] == Decimal("125.00")
        assert detalles["CESTATICKET"] == Decimal("40.00")
        # Deducciones del trabajador: SSO 4% / FAOV 1% / RPE 0.5%
        assert detalles["SSO"] == Decimal("65.00")
        assert detalles["FAOV"] == Decimal("16.25")
        assert detalles["RPE"] == Decimal("8.13")  # 8.125 → HALF_UP
        assert "ISLR" not in detalles  # bajo el umbral (aplica_islr=False)
        # Aportes patronales informativos: SSO 9% / FAOV 2% / INCES 2% / RPE 2%
        assert detalles["AP_SSO"] == Decimal("146.25")
        assert detalles["AP_FAOV"] == Decimal("32.50")
        assert detalles["AP_INCES"] == Decimal("32.50")
        assert detalles["AP_RPE"] == Decimal("32.50")

    def test_asiento_nomina_balanceado(self, respuesta, proceso_a, user_a):
        assert respuesta.status_code == 200
        asiento = AsientoContable.objects.get(
            id_documento_origen=proceso_a.pk, nombre_modelo_origen="ProcesoNomina"
        )
        # El asiento registra al usuario que procesó la nómina (request.user).
        assert asiento.id_usuario_registro == user_a
        detalles = list(DetalleAsiento.objects.filter(id_asiento=asiento))
        assert len(detalles) == 2
        total_debe = sum(d.debe for d in detalles)
        total_haber = sum(d.haber for d in detalles)
        assert total_debe == total_haber == Decimal("4450.62")


# ── Atomicidad: fallo a mitad → rollback completo ──────────────────────────────


class TestProcesarRollback:
    def test_empleado_sin_salario_revierte_todo(self, client_a, proceso_a, empleado_ana, empresa_a):
        # Bruno-bis no tiene salario ni hay parámetro nomina.salario_minimo:
        # Ana (procesada primero, orden alfabético) también debe revertirse.
        Empleado.objects.create(
            empresa=empresa_a,
            nombre="Zoe",
            apellido="Zambrano",
            cedula="V-99999999",
            fecha_ingreso=datetime.date(2025, 5, 1),
        )
        resp = client_a.post(f"{BASE}{proceso_a.id_proceso_nomina}/procesar/", format="json")
        assert resp.status_code == 400
        assert "salario" in resp.json()["error"].lower()
        proceso_a.refresh_from_db()
        assert proceso_a.estado == "EN_PROCESO"
        assert Nomina.objects.filter(id_proceso_nomina=proceso_a).count() == 0
        assert DetalleNomina.objects.filter(id_nomina__id_proceso_nomina=proceso_a).count() == 0

    def test_contabilidad_activa_sin_mapeo_revierte_todo(
        self, client_a, empresa_contable, proceso_a, empleado_ana
    ):
        # Sin MapeoContable NOMINA y contabilidad_activa=True → AsientoError → 422
        resp = client_a.post(f"{BASE}{proceso_a.id_proceso_nomina}/procesar/", format="json")
        assert resp.status_code == 422
        assert "Mapeo" in resp.json()["error"]
        proceso_a.refresh_from_db()
        assert proceso_a.estado == "EN_PROCESO"
        assert Nomina.objects.filter(id_proceso_nomina=proceso_a).count() == 0
        assert AsientoContable.objects.filter(id_documento_origen=proceso_a.pk).count() == 0

    def test_datos_empleado_invalidos_revierte(self, client_a, proceso_a, empleado_ana):
        resp = client_a.post(
            f"{BASE}{proceso_a.id_proceso_nomina}/procesar/",
            {"empleados": {str(empleado_ana.pk): {"campo_inventado": "1"}}},
            format="json",
        )
        assert resp.status_code == 400
        assert "no soportados" in resp.json()["error"]
        assert Nomina.objects.filter(id_proceso_nomina=proceso_a).count() == 0


# ── Bodega informal: sin mapeo y contabilidad inactiva → procesa sin asiento ──


def test_sin_mapeo_contabilidad_inactiva_procesa_con_advertencia(client_a, proceso_a, empleado_ana):
    resp = client_a.post(f"{BASE}{proceso_a.id_proceso_nomina}/procesar/", format="json")
    assert resp.status_code == 200, resp.json()
    data = resp.json()
    assert data["estado"] == "COMPLETADO"
    assert data["asiento_contable"] is None
    assert "advertencia_asiento" in data
    assert Nomina.objects.filter(id_proceso_nomina=proceso_a).count() == 1


# ── Parámetros actualizables (ParametroSistema) ────────────────────────────────


def test_salario_minimo_de_parametro_sistema(client_a, proceso_a, empresa_a):
    """Empleado sin salario propio usa nomina.salario_minimo de la empresa."""
    Empleado.objects.create(
        empresa=empresa_a,
        nombre="Mario",
        apellido="Mendez",
        cedula="V-44444444",
        fecha_ingreso=datetime.date(2026, 1, 1),
    )
    _param(empresa_a, "nomina.salario_minimo", "130.00")
    resp = client_a.post(f"{BASE}{proceso_a.id_proceso_nomina}/procesar/", format="json")
    assert resp.status_code == 200, resp.json()
    nomina = Nomina.objects.get(id_proceso_nomina=proceso_a)
    assert nomina.sueldo_base == Decimal("130.00")
    # 130 − (5.20 + 1.30 + 0.65) = 122.85
    assert nomina.total_deducciones == Decimal("7.15")
    assert nomina.total_neto == Decimal("122.85")


# ── Contratos de estado y aislamiento ──────────────────────────────────────────


def test_reprocesar_completado_400(client_a, proceso_a, empleado_ana):
    assert client_a.post(f"{BASE}{proceso_a.id_proceso_nomina}/procesar/", format="json").status_code == 200
    resp = client_a.post(f"{BASE}{proceso_a.id_proceso_nomina}/procesar/", format="json")
    assert resp.status_code == 400
    assert "COMPLETADO" in resp.json()["error"]
    # Los recibos del primer procesamiento quedan intactos (inmutables)
    assert Nomina.objects.filter(id_proceso_nomina=proceso_a).count() == 1


def test_sin_empleados_activos_400(client_a, proceso_a, empleado_ana):
    empleado_ana.activo = False
    empleado_ana.save(update_fields=["activo"])
    resp = client_a.post(f"{BASE}{proceso_a.id_proceso_nomina}/procesar/", format="json")
    assert resp.status_code == 400
    assert "empleados activos" in resp.json()["error"]


def test_cross_tenant_procesar_404(client_b, proceso_a, empleado_ana):
    """R-CODE-1: un usuario de Empresa B no ve ni procesa procesos de Empresa A."""
    resp = client_b.post(f"{BASE}{proceso_a.id_proceso_nomina}/procesar/", format="json")
    assert resp.status_code == 404
    proceso_a.refresh_from_db()
    assert proceso_a.estado == "EN_PROCESO"
    assert Nomina.objects.filter(id_proceso_nomina=proceso_a).count() == 0
