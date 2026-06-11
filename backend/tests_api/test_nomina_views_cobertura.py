"""
Backfill de cobertura — apps/nomina/views.py (plan "Cero Dudas").

Cubre por la API real (router en apps/nomina/urls.py, prefijo /api/nomina/):

- list 200 autenticado + 401 sin token en las 7 rutas del router.
- Aislamiento multi-tenant (R-CODE-1) directo y vía cadena de FKs
  (Nomina → ProcesoNomina → empresa; DetalleNomina → Nomina → …).
- Actions: activos, abiertos, cerrar, por_tipo, devengados, deducciones,
  procesar (stub: solo EN_PROCESO → COMPLETADO), aprobar, resumen,
  marcar_pagada, y los equivalentes extrasalariales (felices + 400).

Nota: ``procesar`` es un stub que solo cambia estado — se testea tal cual.
Dinero como Decimal con aserciones de valor exacto.
"""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.nomina.models import (
    ConceptoNomina,
    DetalleNomina,
    Nomina,
    NominaExtrasalarial,
    PeriodoNomina,
    ProcesoNomina,
    ProcesoNominaExtrasalarial,
)
from apps.rrhh.models import Empleado

pytestmark = pytest.mark.django_db

BASE = "/api/nomina/"

ROUTES = [
    "periodos-nomina",
    "conceptos-nomina",
    "procesos-nomina",
    "nominas",
    "detalles-nomina",
    "procesos-nomina-extrasalarial",
    "nominas-extrasalarial",
]


def _results(resp):
    data = resp.json()
    return data.get("results", data) if isinstance(data, dict) else data


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


@pytest.fixture
def empleado_a(empresa_a):
    return Empleado.objects.create(
        empresa=empresa_a,
        nombre="Carla",
        apellido="Castro",
        cedula="V-33333333",
        fecha_ingreso=datetime.date(2023, 3, 1),
    )


@pytest.fixture
def periodo_a(empresa_a):
    return PeriodoNomina.objects.create(
        id_empresa=empresa_a,
        nombre_periodo="Junio 2026 - 1ra Quincena",
        fecha_inicio=datetime.date(2026, 6, 1),
        fecha_fin=datetime.date(2026, 6, 15),
        fecha_pago=datetime.date(2026, 6, 16),
        tipo_periodo="QUINCENAL",
        estado="ABIERTO",
        activo=True,
    )


@pytest.fixture
def periodo_b(empresa_b):
    return PeriodoNomina.objects.create(
        id_empresa=empresa_b,
        nombre_periodo="Junio 2026 Beta",
        fecha_inicio=datetime.date(2026, 6, 1),
        fecha_fin=datetime.date(2026, 6, 30),
        fecha_pago=datetime.date(2026, 7, 1),
        tipo_periodo="MENSUAL",
        estado="ABIERTO",
        activo=True,
    )


@pytest.fixture
def concepto_devengado_a(empresa_a):
    return ConceptoNomina.objects.create(
        id_empresa=empresa_a,
        codigo_concepto="SUE-001",
        nombre_concepto="Sueldo Base",
        tipo_concepto="DEVENGADO",
        categoria="SUELDO_BASE",
        es_fijo=True,
        monto_fijo=Decimal("500.0000"),
        activo=True,
    )


@pytest.fixture
def concepto_deduccion_a(empresa_a):
    return ConceptoNomina.objects.create(
        id_empresa=empresa_a,
        codigo_concepto="SSO-001",
        nombre_concepto="Seguro Social",
        tipo_concepto="DEDUCCION",
        categoria="SEGURO_SOCIAL",
        es_porcentaje=True,
        porcentaje=Decimal("4.00"),
        activo=True,
    )


@pytest.fixture
def proceso_a(empresa_a, periodo_a):
    return ProcesoNomina.objects.create(
        id_empresa=empresa_a,
        id_periodo_nomina=periodo_a,
        numero_proceso="PROC-A-001",
        fecha_proceso=timezone.now(),
        estado="EN_PROCESO",
    )


@pytest.fixture
def nomina_a(proceso_a, empleado_a):
    return Nomina.objects.create(
        id_proceso_nomina=proceso_a,
        id_empleado=empleado_a,
        sueldo_base=Decimal("500.0000"),
        total_devengado=Decimal("550.0000"),
        total_deducciones=Decimal("50.0000"),
        total_neto=Decimal("500.0000"),
        estado="CALCULADA",
        fecha_calculo=timezone.now(),
    )


@pytest.fixture
def proceso_extra_a(empresa_a):
    return ProcesoNominaExtrasalarial.objects.create(
        id_empresa=empresa_a,
        numero_proceso="EXTRA-A-001",
        tipo_proceso="AGUINALDO",
        fecha_proceso=timezone.now(),
        fecha_corte=datetime.date(2026, 11, 30),
        estado="EN_PROCESO",
    )


@pytest.fixture
def nomina_extra_a(proceso_extra_a, empleado_a):
    return NominaExtrasalarial.objects.create(
        id_proceso_extrasalarial=proceso_extra_a,
        id_empleado=empleado_a,
        periodo_inicio=datetime.date(2026, 1, 1),
        periodo_fin=datetime.date(2026, 11, 30),
        monto_calculado=Decimal("1000.0000"),
        deducciones=Decimal("0.0000"),
        monto_neto=Decimal("1000.0000"),
        estado="CALCULADA",
        fecha_calculo=timezone.now(),
    )


class TestAutenticacionRequerida:
    @pytest.mark.parametrize("route", ROUTES)
    def test_401_sin_token(self, route):
        resp = APIClient().get(f"{BASE}{route}/")
        assert resp.status_code == 401


class TestAislamientoMultiTenant:
    def test_b_no_ve_periodos_de_a(self, client_b, periodo_a, periodo_b):
        resp = client_b.get(f"{BASE}periodos-nomina/")
        assert resp.status_code == 200
        ids = [r["id_periodo_nomina"] for r in _results(resp)]
        assert str(periodo_b.id_periodo_nomina) in ids
        assert str(periodo_a.id_periodo_nomina) not in ids

    def test_retrieve_periodo_cross_tenant_404(self, client_b, periodo_a):
        resp = client_b.get(f"{BASE}periodos-nomina/{periodo_a.id_periodo_nomina}/")
        assert resp.status_code == 404

    def test_b_no_ve_conceptos_de_a(self, client_b, concepto_devengado_a):
        resp = client_b.get(f"{BASE}conceptos-nomina/")
        assert resp.status_code == 200
        ids = [r["id_concepto_nomina"] for r in _results(resp)]
        assert str(concepto_devengado_a.id_concepto_nomina) not in ids

    def test_b_no_ve_procesos_de_a(self, client_b, proceso_a):
        resp = client_b.get(f"{BASE}procesos-nomina/")
        assert resp.status_code == 200
        ids = [r["id_proceso_nomina"] for r in _results(resp)]
        assert str(proceso_a.id_proceso_nomina) not in ids

    def test_b_no_ve_nominas_de_a(self, client_b, nomina_a):
        # FK chain: Nomina → ProcesoNomina → empresa
        resp = client_b.get(f"{BASE}nominas/")
        assert resp.status_code == 200
        ids = [r["id_nomina"] for r in _results(resp)]
        assert str(nomina_a.id_nomina) not in ids

    def test_b_no_ve_detalles_de_a(self, client_b, nomina_a, concepto_devengado_a):
        detalle = DetalleNomina.objects.create(
            id_nomina=nomina_a,
            id_concepto_nomina=concepto_devengado_a,
            valor_unitario=Decimal("500.0000"),
            valor_total=Decimal("500.0000"),
        )
        resp = client_b.get(f"{BASE}detalles-nomina/")
        assert resp.status_code == 200
        ids = [r["id_detalle_nomina"] for r in _results(resp)]
        assert str(detalle.id_detalle_nomina) not in ids

    def test_a_si_ve_sus_detalles(self, client_a, nomina_a, concepto_devengado_a):
        detalle = DetalleNomina.objects.create(
            id_nomina=nomina_a,
            id_concepto_nomina=concepto_devengado_a,
            valor_unitario=Decimal("500.0000"),
            valor_total=Decimal("500.0000"),
        )
        resp = client_a.get(f"{BASE}detalles-nomina/")
        assert resp.status_code == 200
        assert str(detalle.id_detalle_nomina) in [
            r["id_detalle_nomina"] for r in _results(resp)
        ]

    def test_b_no_ve_extrasalariales_de_a(self, client_b, proceso_extra_a, nomina_extra_a):
        resp = client_b.get(f"{BASE}procesos-nomina-extrasalarial/")
        assert str(proceso_extra_a.id_proceso_extrasalarial) not in [
            r["id_proceso_extrasalarial"] for r in _results(resp)
        ]
        resp2 = client_b.get(f"{BASE}nominas-extrasalarial/")
        assert str(nomina_extra_a.id_nomina_extrasalarial) not in [
            r["id_nomina_extrasalarial"] for r in _results(resp2)
        ]


class TestPeriodoNominaActions:
    def test_activos(self, client_a, empresa_a, periodo_a):
        inactivo = PeriodoNomina.objects.create(
            id_empresa=empresa_a,
            nombre_periodo="Viejo",
            fecha_inicio=datetime.date(2025, 1, 1),
            fecha_fin=datetime.date(2025, 1, 15),
            fecha_pago=datetime.date(2025, 1, 16),
            tipo_periodo="QUINCENAL",
            estado="CERRADO",
            activo=False,
        )
        resp = client_a.get(f"{BASE}periodos-nomina/activos/")
        assert resp.status_code == 200
        ids = [r["id_periodo_nomina"] for r in resp.json()]
        assert str(periodo_a.id_periodo_nomina) in ids
        assert str(inactivo.id_periodo_nomina) not in ids

    def test_abiertos(self, client_a, empresa_a, periodo_a):
        cerrado = PeriodoNomina.objects.create(
            id_empresa=empresa_a,
            nombre_periodo="Cerrado",
            fecha_inicio=datetime.date(2026, 5, 1),
            fecha_fin=datetime.date(2026, 5, 15),
            fecha_pago=datetime.date(2026, 5, 16),
            tipo_periodo="QUINCENAL",
            estado="CERRADO",
            activo=True,
        )
        resp = client_a.get(f"{BASE}periodos-nomina/abiertos/")
        assert resp.status_code == 200
        ids = [r["id_periodo_nomina"] for r in resp.json()]
        assert str(periodo_a.id_periodo_nomina) in ids
        assert str(cerrado.id_periodo_nomina) not in ids

    def test_cerrar_ok(self, client_a, periodo_a):
        resp = client_a.post(f"{BASE}periodos-nomina/{periodo_a.id_periodo_nomina}/cerrar/")
        assert resp.status_code == 200
        periodo_a.refresh_from_db()
        assert periodo_a.estado == "CERRADO"

    def test_cerrar_no_abierto_400(self, client_a, periodo_a):
        periodo_a.estado = "CERRADO"
        periodo_a.save()
        resp = client_a.post(f"{BASE}periodos-nomina/{periodo_a.id_periodo_nomina}/cerrar/")
        assert resp.status_code == 400

    def test_cerrar_cross_tenant_404(self, client_b, periodo_a):
        resp = client_b.post(f"{BASE}periodos-nomina/{periodo_a.id_periodo_nomina}/cerrar/")
        assert resp.status_code == 404
        periodo_a.refresh_from_db()
        assert periodo_a.estado == "ABIERTO"


class TestConceptoNominaActions:
    def test_por_tipo_sin_filtro(self, client_a, concepto_devengado_a, concepto_deduccion_a):
        resp = client_a.get(f"{BASE}conceptos-nomina/por_tipo/")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_por_tipo_con_filtro(self, client_a, concepto_devengado_a, concepto_deduccion_a):
        resp = client_a.get(f"{BASE}conceptos-nomina/por_tipo/", {"tipo": "DEDUCCION"})
        assert resp.status_code == 200
        assert [r["id_concepto_nomina"] for r in resp.json()] == [
            str(concepto_deduccion_a.id_concepto_nomina)
        ]

    def test_devengados(self, client_a, concepto_devengado_a, concepto_deduccion_a):
        resp = client_a.get(f"{BASE}conceptos-nomina/devengados/")
        assert resp.status_code == 200
        assert [r["id_concepto_nomina"] for r in resp.json()] == [
            str(concepto_devengado_a.id_concepto_nomina)
        ]

    def test_deducciones(self, client_a, concepto_devengado_a, concepto_deduccion_a):
        resp = client_a.get(f"{BASE}conceptos-nomina/deducciones/")
        assert resp.status_code == 200
        assert [r["id_concepto_nomina"] for r in resp.json()] == [
            str(concepto_deduccion_a.id_concepto_nomina)
        ]


class TestProcesoNominaActions:
    def test_procesar_stub_cambia_a_completado(self, client_a, proceso_a):
        # `procesar` es un stub: solo cambia estado EN_PROCESO → COMPLETADO
        resp = client_a.post(f"{BASE}procesos-nomina/{proceso_a.id_proceso_nomina}/procesar/")
        assert resp.status_code == 200
        proceso_a.refresh_from_db()
        assert proceso_a.estado == "COMPLETADO"

    def test_procesar_ya_completado_400(self, client_a, proceso_a):
        proceso_a.estado = "COMPLETADO"
        proceso_a.save()
        resp = client_a.post(f"{BASE}procesos-nomina/{proceso_a.id_proceso_nomina}/procesar/")
        assert resp.status_code == 400

    def test_aprobar_no_completado_400(self, client_a, proceso_a):
        resp = client_a.post(f"{BASE}procesos-nomina/{proceso_a.id_proceso_nomina}/aprobar/")
        assert resp.status_code == 400

    def test_aprobar_actualiza_nominas_calculadas(self, client_a, proceso_a, nomina_a):
        proceso_a.estado = "COMPLETADO"
        proceso_a.save()
        resp = client_a.post(f"{BASE}procesos-nomina/{proceso_a.id_proceso_nomina}/aprobar/")
        assert resp.status_code == 200
        proceso_a.refresh_from_db()
        nomina_a.refresh_from_db()
        assert proceso_a.estado == "APROBADO"
        assert nomina_a.estado == "APROBADA"

    def test_resumen_exacto(self, client_a, proceso_a, nomina_a, empleado_a):
        Nomina.objects.create(
            id_proceso_nomina=proceso_a,
            id_empleado=empleado_a,
            sueldo_base=Decimal("300.0000"),
            total_devengado=Decimal("330.0000"),
            total_deducciones=Decimal("30.0000"),
            total_neto=Decimal("300.0000"),
            estado="CALCULADA",
            fecha_calculo=timezone.now(),
        )
        resp = client_a.get(f"{BASE}procesos-nomina/{proceso_a.id_proceso_nomina}/resumen/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_empleados"] == 2
        assert Decimal(str(data["total_devengado"])) == Decimal("880.0000")
        assert Decimal(str(data["total_deducciones"])) == Decimal("80.0000")
        assert Decimal(str(data["total_neto"])) == Decimal("800.0000")

    def test_resumen_proceso_vacio(self, client_a, proceso_a):
        resp = client_a.get(f"{BASE}procesos-nomina/{proceso_a.id_proceso_nomina}/resumen/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_empleados"] == 0
        assert data["total_neto"] == 0


class TestNominaActions:
    def test_aprobar_ok(self, client_a, nomina_a):
        resp = client_a.post(f"{BASE}nominas/{nomina_a.id_nomina}/aprobar/")
        assert resp.status_code == 200
        nomina_a.refresh_from_db()
        assert nomina_a.estado == "APROBADA"

    def test_aprobar_no_calculada_400(self, client_a, nomina_a):
        nomina_a.estado = "PAGADA"
        nomina_a.save()
        resp = client_a.post(f"{BASE}nominas/{nomina_a.id_nomina}/aprobar/")
        assert resp.status_code == 400

    def test_marcar_pagada_no_aprobada_400(self, client_a, nomina_a):
        resp = client_a.post(f"{BASE}nominas/{nomina_a.id_nomina}/marcar_pagada/")
        assert resp.status_code == 400
        nomina_a.refresh_from_db()
        assert nomina_a.estado == "CALCULADA"

    def test_marcar_pagada_ok(self, client_a, nomina_a):
        nomina_a.estado = "APROBADA"
        nomina_a.save()
        resp = client_a.post(f"{BASE}nominas/{nomina_a.id_nomina}/marcar_pagada/")
        assert resp.status_code == 200
        nomina_a.refresh_from_db()
        assert nomina_a.estado == "PAGADA"

    def test_aprobar_cross_tenant_404(self, client_b, nomina_a):
        resp = client_b.post(f"{BASE}nominas/{nomina_a.id_nomina}/aprobar/")
        assert resp.status_code == 404


class TestProcesoExtrasalarialActions:
    def test_procesar_ok(self, client_a, proceso_extra_a):
        resp = client_a.post(
            f"{BASE}procesos-nomina-extrasalarial/{proceso_extra_a.id_proceso_extrasalarial}/procesar/"
        )
        assert resp.status_code == 200
        proceso_extra_a.refresh_from_db()
        assert proceso_extra_a.estado == "COMPLETADO"

    def test_procesar_ya_completado_400(self, client_a, proceso_extra_a):
        proceso_extra_a.estado = "COMPLETADO"
        proceso_extra_a.save()
        resp = client_a.post(
            f"{BASE}procesos-nomina-extrasalarial/{proceso_extra_a.id_proceso_extrasalarial}/procesar/"
        )
        assert resp.status_code == 400

    def test_aprobar_no_completado_400(self, client_a, proceso_extra_a):
        resp = client_a.post(
            f"{BASE}procesos-nomina-extrasalarial/{proceso_extra_a.id_proceso_extrasalarial}/aprobar/"
        )
        assert resp.status_code == 400

    def test_aprobar_actualiza_nominas(self, client_a, proceso_extra_a, nomina_extra_a):
        proceso_extra_a.estado = "COMPLETADO"
        proceso_extra_a.save()
        resp = client_a.post(
            f"{BASE}procesos-nomina-extrasalarial/{proceso_extra_a.id_proceso_extrasalarial}/aprobar/"
        )
        assert resp.status_code == 200
        proceso_extra_a.refresh_from_db()
        nomina_extra_a.refresh_from_db()
        assert proceso_extra_a.estado == "APROBADO"
        assert nomina_extra_a.estado == "APROBADA"


class TestNominaExtrasalarialActions:
    def test_aprobar_ok(self, client_a, nomina_extra_a):
        resp = client_a.post(
            f"{BASE}nominas-extrasalarial/{nomina_extra_a.id_nomina_extrasalarial}/aprobar/"
        )
        assert resp.status_code == 200
        nomina_extra_a.refresh_from_db()
        assert nomina_extra_a.estado == "APROBADA"

    def test_aprobar_no_calculada_400(self, client_a, nomina_extra_a):
        nomina_extra_a.estado = "PAGADA"
        nomina_extra_a.save()
        resp = client_a.post(
            f"{BASE}nominas-extrasalarial/{nomina_extra_a.id_nomina_extrasalarial}/aprobar/"
        )
        assert resp.status_code == 400

    def test_marcar_pagada_flujo(self, client_a, nomina_extra_a):
        # No aprobada aún → 400
        resp = client_a.post(
            f"{BASE}nominas-extrasalarial/{nomina_extra_a.id_nomina_extrasalarial}/marcar_pagada/"
        )
        assert resp.status_code == 400
        nomina_extra_a.estado = "APROBADA"
        nomina_extra_a.save()
        resp2 = client_a.post(
            f"{BASE}nominas-extrasalarial/{nomina_extra_a.id_nomina_extrasalarial}/marcar_pagada/"
        )
        assert resp2.status_code == 200
        nomina_extra_a.refresh_from_db()
        assert nomina_extra_a.estado == "PAGADA"
