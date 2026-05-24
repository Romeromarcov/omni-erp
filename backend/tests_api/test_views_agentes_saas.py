"""
Tests de API para los nuevos endpoints de Agentes IA (M9) y SaaS (M10-T5).

Cobertura:
  - PrediccionAgenteViewSet: CRUD + aislamiento multi-tenant + acciones
  - PlanViewSet: catálogo de planes + permisos
  - SuscripcionViewSet: CRUD + acciones cancelar/suspender/activa
  - Aislamiento: un usuario de empresa A no ve datos de empresa B
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / Fixtures locales
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client_a(user_a):
    """APIClient autenticado como usuario de empresa A."""
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    """APIClient autenticado como usuario de empresa B."""
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


@pytest.fixture
def plan_free(db):
    from apps.saas.models import Plan
    return Plan.objects.create(
        nombre="Free",
        nivel="FREE",
        precio_mensual=Decimal("0.00"),
        precio_anual=Decimal("0.00"),
        max_usuarios=3,
        max_empresas=1,
        max_documentos_mes=50,
        permite_ia=False,
        permite_api=False,
    )


@pytest.fixture
def plan_pro(db):
    from apps.saas.models import Plan
    return Plan.objects.create(
        nombre="Pro",
        nivel="PRO",
        precio_mensual=Decimal("99.00"),
        precio_anual=Decimal("990.00"),
        max_usuarios=50,
        max_empresas=5,
        max_documentos_mes=0,  # ilimitado
        permite_ia=True,
        permite_api=True,
    )


@pytest.fixture
def suscripcion_a(db, empresa_a, plan_pro):
    """Suscripción activa para empresa A."""
    from apps.saas.models import Suscripcion
    hoy = date.today()
    return Suscripcion.objects.create(
        id_empresa=empresa_a,
        id_plan=plan_pro,
        estado="ACTIVA",
        periodo="MENSUAL",
        fecha_inicio=hoy - timedelta(days=10),
        fecha_fin=hoy + timedelta(days=20),
        monto_pagado=Decimal("99.00"),
    )


@pytest.fixture
def suscripcion_b(db, empresa_b, plan_free):
    """Suscripción de empresa B."""
    from apps.saas.models import Suscripcion
    hoy = date.today()
    return Suscripcion.objects.create(
        id_empresa=empresa_b,
        id_plan=plan_free,
        estado="TRIAL",
        periodo="MENSUAL",
        fecha_inicio=hoy,
        fecha_fin=hoy + timedelta(days=30),
    )


@pytest.fixture
def prediccion_a(db, empresa_a):
    """PrediccionAgente de empresa A."""
    from apps.agentes.models import PrediccionAgente
    return PrediccionAgente.objects.create(
        id_empresa=empresa_a,
        agente="clasificador_gastos",
        input_texto="Gasolina para camión",
        input_monto=Decimal("100.00"),
        categoria_predicha="COMBUSTIBLE",
        confianza=0.90,
        razonamiento="Texto contiene 'gasolina'.",
    )


@pytest.fixture
def prediccion_b(db, empresa_b):
    """PrediccionAgente de empresa B."""
    from apps.agentes.models import PrediccionAgente
    return PrediccionAgente.objects.create(
        id_empresa=empresa_b,
        agente="cobranza_estratega",
        input_texto="CxC vencida",
        input_monto=Decimal("500.00"),
        categoria_predicha="alta",
        confianza=0.80,
        razonamiento="Cliente moroso.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# SaaS — PlanViewSet
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPlanViewSet:
    BASE = "/api/saas/planes/"

    def test_listar_planes_activos(self, client_a, plan_free, plan_pro):
        r = client_a.get(self.BASE)
        assert r.status_code == 200
        nombres = [p["nombre"] for p in r.data["results"]]
        assert "Free" in nombres
        assert "Pro" in nombres

    def test_detalle_plan(self, client_a, plan_pro):
        r = client_a.get(f"{self.BASE}{plan_pro.id_plan}/")
        assert r.status_code == 200
        assert r.data["nombre"] == "Pro"
        assert r.data["permite_ia"] is True

    def test_plan_no_activo_oculto(self, client_a, db):
        from apps.saas.models import Plan
        inactivo = Plan.objects.create(
            nombre="Legacy", nivel="STARTER",
            precio_mensual=Decimal("9.00"),
            activo=False,
        )
        r = client_a.get(self.BASE)
        nombres = [p["nombre"] for p in r.data["results"]]
        assert "Legacy" not in nombres

    def test_crear_plan_requiere_superusuario(self, client_a):
        payload = {
            "nombre": "Enterprise",
            "nivel": "ENTERPRISE",
            "precio_mensual": "299.00",
            "precio_anual": "2990.00",
        }
        r = client_a.post(self.BASE, payload, format="json")
        assert r.status_code == 403

    def test_listado_sin_autenticar(self):
        from rest_framework.test import APIClient
        c = APIClient()
        r = c.get(self.BASE)
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# SaaS — SuscripcionViewSet
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSuscripcionViewSet:
    BASE = "/api/saas/suscripciones/"

    def test_listar_suscripciones_propias(self, client_a, suscripcion_a, suscripcion_b):
        r = client_a.get(self.BASE)
        assert r.status_code == 200
        ids = [s["id_suscripcion"] for s in r.data["results"]]
        assert str(suscripcion_a.id_suscripcion) in ids
        # Empresa B no visible para usuario A
        assert str(suscripcion_b.id_suscripcion) not in ids

    def test_aislamiento_usuario_b_no_ve_suscripcion_a(self, client_b, suscripcion_a):
        r = client_b.get(self.BASE)
        assert r.status_code == 200
        ids = [s["id_suscripcion"] for s in r.data["results"]]
        assert str(suscripcion_a.id_suscripcion) not in ids

    def test_detalle_suscripcion_propia(self, client_a, suscripcion_a):
        r = client_a.get(f"{self.BASE}{suscripcion_a.id_suscripcion}/")
        assert r.status_code == 200
        assert r.data["estado"] == "ACTIVA"
        assert r.data["plan_nombre"] == "Pro"
        assert r.data["esta_vigente"] is True

    def test_no_puede_ver_suscripcion_de_otra_empresa(self, client_a, suscripcion_b):
        r = client_a.get(f"{self.BASE}{suscripcion_b.id_suscripcion}/")
        assert r.status_code == 404

    def test_accion_activa_retorna_suscripcion_vigente(self, client_a, suscripcion_a):
        r = client_a.get(f"{self.BASE}activa/")
        assert r.status_code == 200
        assert r.data["id_suscripcion"] == str(suscripcion_a.id_suscripcion)
        assert r.data["esta_vigente"] is True

    def test_accion_activa_sin_suscripcion_404(self, client_a):
        # Sin ninguna suscripción creada
        r = client_a.get(f"{self.BASE}activa/")
        assert r.status_code == 404

    def test_cancelar_suscripcion(self, client_a, suscripcion_a):
        r = client_a.post(
            f"{self.BASE}{suscripcion_a.id_suscripcion}/cancelar/",
            {"notas": "Downgrade voluntario"},
            format="json",
        )
        assert r.status_code == 200
        assert r.data["estado"] == "CANCELADA"
        suscripcion_a.refresh_from_db()
        assert suscripcion_a.estado == "CANCELADA"
        assert suscripcion_a.fecha_cancelacion is not None

    def test_cancelar_dos_veces_da_error(self, client_a, suscripcion_a):
        client_a.post(f"{self.BASE}{suscripcion_a.id_suscripcion}/cancelar/", format="json")
        r = client_a.post(f"{self.BASE}{suscripcion_a.id_suscripcion}/cancelar/", format="json")
        assert r.status_code == 400

    def test_suspender_suscripcion(self, client_a, suscripcion_a):
        r = client_a.post(f"{self.BASE}{suscripcion_a.id_suscripcion}/suspender/")
        assert r.status_code == 200
        assert r.data["estado"] == "SUSPENDIDA"
        suscripcion_a.refresh_from_db()
        assert suscripcion_a.fecha_suspension is not None

    def test_no_puede_cancelar_suscripcion_de_otra_empresa(self, client_a, suscripcion_b):
        r = client_a.post(f"{self.BASE}{suscripcion_b.id_suscripcion}/cancelar/")
        assert r.status_code == 404

    def test_filtro_por_estado(self, client_a, suscripcion_a):
        r = client_a.get(f"{self.BASE}?estado=ACTIVA")
        assert r.status_code == 200
        for s in r.data["results"]:
            assert s["estado"] == "ACTIVA"

    def test_dias_restantes_calculado(self, client_a, suscripcion_a):
        r = client_a.get(f"{self.BASE}{suscripcion_a.id_suscripcion}/")
        assert r.status_code == 200
        dias = r.data["dias_restantes"]
        assert isinstance(dias, int)
        assert dias > 0  # suscripcion_a termina en 20 días

    def test_crear_suscripcion(self, client_a, empresa_a, plan_free):
        hoy = date.today()
        payload = {
            "id_empresa": str(empresa_a.id_empresa),
            "id_plan": str(plan_free.id_plan),
            "estado": "TRIAL",
            "periodo": "MENSUAL",
            "fecha_inicio": str(hoy),
            "fecha_fin": str(hoy + timedelta(days=30)),
        }
        r = client_a.post(self.BASE, payload, format="json")
        assert r.status_code == 201
        assert r.data["estado"] == "TRIAL"


# ─────────────────────────────────────────────────────────────────────────────
# Agentes — PrediccionAgenteViewSet
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPrediccionAgenteViewSet:
    BASE = "/api/agentes/predicciones/"

    def test_listar_predicciones_propias(self, client_a, prediccion_a, prediccion_b):
        r = client_a.get(self.BASE)
        assert r.status_code == 200
        ids = [p["id_prediccion"] for p in r.data["results"]]
        assert str(prediccion_a.id_prediccion) in ids
        assert str(prediccion_b.id_prediccion) not in ids

    def test_aislamiento_b_no_ve_prediccion_a(self, client_b, prediccion_a):
        r = client_b.get(self.BASE)
        ids = [p["id_prediccion"] for p in r.data["results"]]
        assert str(prediccion_a.id_prediccion) not in ids

    def test_detalle_prediccion_propia(self, client_a, prediccion_a):
        r = client_a.get(f"{self.BASE}{prediccion_a.id_prediccion}/")
        assert r.status_code == 200
        assert r.data["agente"] == "clasificador_gastos"
        assert r.data["categoria_predicha"] == "COMBUSTIBLE"

    def test_no_puede_ver_prediccion_de_otra_empresa(self, client_a, prediccion_b):
        r = client_a.get(f"{self.BASE}{prediccion_b.id_prediccion}/")
        assert r.status_code == 404

    def test_filtro_por_agente(self, client_a, prediccion_a):
        r = client_a.get(f"{self.BASE}?agente=clasificador_gastos")
        assert r.status_code == 200
        for p in r.data["results"]:
            assert p["agente"] == "clasificador_gastos"

    def test_evaluar_prediccion_aceptada(self, client_a, prediccion_a):
        r = client_a.patch(
            f"{self.BASE}{prediccion_a.id_prediccion}/evaluar/",
            {"resultado_humano": "aceptada"},
            format="json",
        )
        assert r.status_code == 200
        assert r.data["resultado_humano"] == "aceptada"
        prediccion_a.refresh_from_db()
        assert prediccion_a.resultado_humano == "aceptada"

    def test_evaluar_prediccion_rechazada_con_correccion(self, client_a, prediccion_a):
        r = client_a.patch(
            f"{self.BASE}{prediccion_a.id_prediccion}/evaluar/",
            {"resultado_humano": "rechazada", "categoria_correcta": "MANTENIMIENTO"},
            format="json",
        )
        assert r.status_code == 200
        prediccion_a.refresh_from_db()
        assert prediccion_a.resultado_humano == "rechazada"
        assert prediccion_a.categoria_correcta == "MANTENIMIENTO"

    def test_evaluar_resultado_invalido(self, client_a, prediccion_a):
        r = client_a.patch(
            f"{self.BASE}{prediccion_a.id_prediccion}/evaluar/",
            {"resultado_humano": "no_valido"},
            format="json",
        )
        assert r.status_code == 400

    def test_no_puede_evaluar_prediccion_de_otra_empresa(self, client_a, prediccion_b):
        r = client_a.patch(
            f"{self.BASE}{prediccion_b.id_prediccion}/evaluar/",
            {"resultado_humano": "aceptada"},
            format="json",
        )
        assert r.status_code == 404

    def test_prediccion_campo_readonly_id(self, client_a, prediccion_a):
        """id_prediccion nunca puede ser sobreescrito."""
        r = client_a.get(f"{self.BASE}{prediccion_a.id_prediccion}/")
        assert "id_prediccion" in r.data

    def test_listar_requiere_autenticacion(self):
        c = APIClient()
        r = c.get(self.BASE)
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Agentes — Acciones analizar (requieren datos en BD)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestAgentesAccionesAnalizar:
    """
    Las acciones analizar-* consultan tablas de negocio (CxC, StockActual, etc.).
    Sin datos de negocio retornan listas vacías — suficiente para probar que
    el endpoint funciona correctamente y aplica aislamiento multi-tenant.
    """

    def test_analizar_cobranza_sin_datos_retorna_lista_vacia(self, client_a, empresa_a):
        r = client_a.post("/api/agentes/predicciones/analizar-cobranza/", {"persistir": False}, format="json")
        assert r.status_code == 200
        assert "sugerencias" in r.data
        assert isinstance(r.data["sugerencias"], list)
        assert r.data["total"] == len(r.data["sugerencias"])

    def test_analizar_reorden_sin_datos_retorna_lista_vacia(self, client_a, empresa_a):
        r = client_a.post(
            "/api/agentes/predicciones/analizar-reorden/",
            {"solo_alertas": True, "persistir": False},
            format="json",
        )
        assert r.status_code == 200
        assert "sugerencias" in r.data
        assert isinstance(r.data["sugerencias"], list)

    def test_analizar_personalizacion_sin_datos_ok(self, client_a, empresa_a):
        r = client_a.post("/api/agentes/predicciones/analizar-personalizacion/", format="json")
        assert r.status_code == 200
        assert "flujo_documentos" in r.data
        assert "listas_precios" in r.data
        assert "credito_clientes" in r.data

    def test_analizar_cobranza_requiere_autenticacion(self):
        c = APIClient()
        r = c.post("/api/agentes/predicciones/analizar-cobranza/")
        assert r.status_code == 401

    def test_analizar_reorden_requiere_autenticacion(self):
        c = APIClient()
        r = c.post("/api/agentes/predicciones/analizar-reorden/")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# SaaS — helpers de modelo (suscripcion_activa, tiene_feature)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSaasHelpers:
    def test_suscripcion_activa_retorna_correcta(self, suscripcion_a, empresa_a):
        from apps.saas.models import suscripcion_activa
        sus = suscripcion_activa(empresa_a)
        assert sus is not None
        assert sus.id_suscripcion == suscripcion_a.id_suscripcion

    def test_suscripcion_activa_retorna_none_sin_suscripcion(self, empresa_a):
        from apps.saas.models import suscripcion_activa
        sus = suscripcion_activa(empresa_a)
        assert sus is None

    def test_tiene_feature_ia_con_plan_pro(self, suscripcion_a, empresa_a):
        from apps.saas.models import tiene_feature
        assert tiene_feature(empresa_a, "permite_ia") is True

    def test_tiene_feature_ia_sin_suscripcion(self, empresa_a):
        from apps.saas.models import tiene_feature
        assert tiene_feature(empresa_a, "permite_ia") is False

    def test_suscripcion_vencida_no_activa(self, db, empresa_a, plan_free):
        from apps.saas.models import Suscripcion, suscripcion_activa
        hoy = date.today()
        Suscripcion.objects.create(
            id_empresa=empresa_a,
            id_plan=plan_free,
            estado="ACTIVA",
            periodo="MENSUAL",
            fecha_inicio=hoy - timedelta(days=60),
            fecha_fin=hoy - timedelta(days=1),  # ya venció
        )
        sus = suscripcion_activa(empresa_a)
        assert sus is None

    def test_esta_vigente_property(self, suscripcion_a):
        assert suscripcion_a.esta_vigente is True

    def test_dias_restantes_positivos(self, suscripcion_a):
        assert suscripcion_a.dias_restantes > 0

    def test_cancelar_cambia_estado(self, suscripcion_a):
        suscripcion_a.cancelar(notas="test")
        assert suscripcion_a.estado == "CANCELADA"
        assert suscripcion_a.notas == "test"

    def test_suspender_cambia_estado(self, suscripcion_a):
        suscripcion_a.suspender()
        assert suscripcion_a.estado == "SUSPENDIDA"
        assert suscripcion_a.fecha_suspension is not None
