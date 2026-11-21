"""
Tests de integración, RLS, seguridad y MCP para agentes IA asíncronos (Plan 05 P2-2).

Cubre:
  1. Encolado HTTP ``202 Accepted`` con ``transaction.on_commit`` y UPDATE atómico
     de ``celery_task_id`` sin pisar al worker si finaliza antes.
  2. Multi-empresa, Matriz↔Subsidiaria (``clasificar-gasto`` sobre subsidiaria,
     ``empresa_id`` explícito, ``sugerencias-activas`` multi-empresa) y superusuario Omni.
  3. Ejecución real de ``agentes.ejecutar_analisis_agente`` para los 4 agentes
     (incluyendo ``Decimal``/dataclasses reales, ``clasificador_gastos`` con
     ``prediccion_id`` exacto y sin duplicar ``CategoriaGasto`` para ``servicios_profesionales``),
     y ``self.retry(countdown=2)`` cuando ``ejecucion is None``.
  4. Manejo de fallos en worker: ``estado="fallido"`` y ``mensaje_error`` saneado
     (R-CODE-8, sin tracebacks ni secretos).
  5. PostgreSQL RLS en ``agentes_ejecucion_agente`` (``FORCE ROW LEVEL SECURITY``,
     fail-closed sin contexto, aislamiento sin filtro ORM y ``WITH CHECK``).
  6. Endpoint ``/api/agentes/ejecuciones/`` + ``EscrituraRateThrottle`` en acciones POST
     + ``lookup_value_regex`` en ``PrediccionAgenteViewSet`` + Admin solo lectura.
  7. Paridad MCP (``apps.agentes.mcp``: ``CapabilityToken``, empresa ``activo=True``,
     ``limite=True`` rechazado, fail-closed RLS, anti-IDOR y validación de UUID/NUL).
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
import json
from unittest.mock import MagicMock, patch
import uuid

from celery.exceptions import Retry
from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.utils import ProgrammingError
from django.test import RequestFactory, override_settings
from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from apps.agentes.models import EjecucionAgente, PrediccionAgente
from apps.agentes.tasks import ejecutar_analisis_agente
from apps.core import rls
from apps.core.models import CapabilityToken, Empresa

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

URL_PRED = "/api/agentes/predicciones/"
URL_EJEC = "/api/agentes/ejecuciones/"


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
def gasto_a(empresa_a, moneda_usd):
    from apps.gastos.models import CategoriaGasto, Gasto

    cat = CategoriaGasto.objects.create(id_empresa=empresa_a, nombre_categoria="General")
    return Gasto.objects.create(
        id_empresa=empresa_a,
        fecha_gasto=date.today(),
        descripcion="almuerzo de trabajo con cliente",
        monto=Decimal("55.00"),
        id_moneda=moneda_usd,
        id_categoria_gasto=cat,
        estado_gasto="PENDIENTE_APROBACION",
    )


# ── 1. Encolado HTTP 202 + transaction.on_commit + actualización atómica ──────


class TestEncoladoHttp202:
    def test_4_acciones_difieren_delay_a_on_commit_sin_ejecutar_inline(
        self, client_a, empresa_a, user_a, gasto_a, django_capture_on_commit_callbacks
    ):
        mock_task = MagicMock(id="celery-async-123")
        with (
            patch("apps.agentes.tasks.ejecutar_analisis_agente.delay", return_value=mock_task) as delay_mock,
            patch("apps.agentes.cobranza.CobranzaEstrategaAgent.analizar") as cob_mock,
            patch("apps.agentes.reorden.ReordenSugeridorAgent.analizar") as reo_mock,
            patch("apps.agentes.personalizacion_agente.PersonalizacionCapa2Agent.analizar") as per_mock,
            patch("apps.agentes.clasificador.ClasificadorGastos.clasificar") as cla_mock,
        ):
            with django_capture_on_commit_callbacks(execute=True):
                r_cob = client_a.post(URL_PRED + "analizar-cobranza/", {"persistir": True}, format="json")
                r_reo = client_a.post(
                    URL_PRED + "analizar-reorden/",
                    {"solo_alertas": False, "persistir": True},
                    format="json",
                )
                r_per = client_a.post(URL_PRED + "analizar-personalizacion/", {}, format="json")
                r_cla = client_a.post(
                    URL_PRED + "clasificar-gasto/",
                    {"gasto_id": str(gasto_a.pk), "aplicar": True},
                    format="json",
                )
                # Antes de confirmar la transacción, .delay() aún no se ha disparado
                assert delay_mock.call_count == 0

        assert delay_mock.call_count == 4
        cob_mock.assert_not_called()
        reo_mock.assert_not_called()
        per_mock.assert_not_called()
        cla_mock.assert_not_called()

        for resp, expected_agente in (
            (r_cob, "cobranza_estratega"),
            (r_reo, "reorden_sugeridor"),
            (r_per, "personalizacion_capa2"),
            (r_cla, "clasificador_gastos"),
        ):
            assert resp.status_code == 202
            body = resp.json()
            assert body["agente"] == expected_agente
            assert body["estado"] == "pendiente"
            assert body["iniciado_por"] == str(user_a.pk)
            assert body["id_empresa"] == str(empresa_a.pk)
            ej = EjecucionAgente.objects.get(pk=body["id_ejecucion"])
            assert ej.celery_task_id == "celery-async-123"

        assert r_cob.json()["parametros"] == {"persistir": True}
        assert r_reo.json()["parametros"] == {"solo_alertas": False, "persistir": True}
        assert r_per.json()["parametros"] == {}
        assert r_cla.json()["parametros"] == {"gasto_id": str(gasto_a.pk), "aplicar": True}

    @pytest.mark.django_db(transaction=True)
    def test_on_commit_real_y_update_condicional_no_pisa_worker(self, client_a, empresa_a):
        """Si el worker finaliza antes del UPDATE de celery_task_id, no se sobrescribe su estado."""

        def _worker_mas_rapido(ejecucion_id: str, empresa_id: str):
            EjecucionAgente.objects.filter(pk=ejecucion_id, id_empresa_id=empresa_id).update(
                estado="completado",
                celery_task_id="worker-real-id",
                resultado={"total": 7},
            )
            return MagicMock(id="task-tardio-id")

        with patch("apps.agentes.tasks.ejecutar_analisis_agente.delay", side_effect=_worker_mas_rapido):
            resp = client_a.post(URL_PRED + "analizar-cobranza/", {}, format="json")

        assert resp.status_code == 202
        body = resp.json()
        assert body["estado"] == "completado"
        assert body["celery_task_id"] == "worker-real-id"
        assert body["resultado"] == {"total": 7}

    def test_payloads_invalidos_devuelven_400_sin_encolar(self, client_a):
        with patch("apps.agentes.tasks.ejecutar_analisis_agente.delay") as delay_mock:
            assert (
                client_a.post(URL_PRED + "analizar-cobranza/", {"persistir": "quizas"}, format="json").status_code
                == 400
            )
            assert (
                client_a.post(URL_PRED + "analizar-cobranza/", {"empresa_id": "bad-uuid"}, format="json").status_code
                == 400
            )
            assert (
                client_a.post(URL_PRED + "analizar-reorden/", {"solo_alertas": ["x"]}, format="json").status_code
                == 400
            )
            assert client_a.post(URL_PRED + "analizar-personalizacion/", ["lista"], format="json").status_code == 400
            assert (
                client_a.post(URL_PRED + "clasificar-gasto/", {"gasto_id": "no-es-uuid"}, format="json").status_code
                == 400
            )
            assert (
                client_a.post(URL_PRED + "clasificar-gasto/", {"gasto_id": "abc\x00def"}, format="json").status_code
                == 400
            )
        delay_mock.assert_not_called()


# ── 2. Multi-empresa, Matriz↔Subsidiaria y Superusuario Omni ──────────────────


class TestMultiEmpresaMatrizSuperusuario:
    @pytest.fixture
    def subsidiaria_a(self, empresa_a, moneda_usd):
        return Empresa.objects.create(
            nombre_legal="AAA Subsidiaria A",
            identificador_fiscal="J-11111111-1",
            empresa_matriz=empresa_a,
            id_moneda_base=moneda_usd,
        )

    def test_clasificar_gasto_en_subsidiaria_sin_404_falso(
        self, client_a, empresa_a, subsidiaria_a, moneda_usd, django_capture_on_commit_callbacks
    ):
        from apps.gastos.models import CategoriaGasto, Gasto

        cat = CategoriaGasto.objects.create(id_empresa=subsidiaria_a, nombre_categoria="General")
        gasto_sub = Gasto.objects.create(
            id_empresa=subsidiaria_a,
            fecha_gasto=date.today(),
            descripcion="almuerzo con proveedor",
            monto=Decimal("25.00"),
            id_moneda=moneda_usd,
            id_categoria_gasto=cat,
            estado_gasto="PENDIENTE_APROBACION",
        )
        with django_capture_on_commit_callbacks(execute=True):
            resp = client_a.post(
                URL_PRED + "clasificar-gasto/",
                {"gasto_id": str(gasto_sub.pk), "aplicar": False},
                format="json",
            )
        assert resp.status_code == 202
        ej = EjecucionAgente.objects.get(pk=resp.json()["id_ejecucion"])
        assert ej.id_empresa_id == subsidiaria_a.pk
        assert ej.estado == "completado"
        assert ej.resultado["categoria"] == "alimentacion"

    def test_empresa_id_explicito_subsidiaria_y_rechazo_ajena(
        self, client_a, empresa_a, empresa_b, subsidiaria_a, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            r_sub = client_a.post(
                URL_PRED + "analizar-cobranza/",
                {"empresa_id": str(subsidiaria_a.pk)},
                format="json",
            )
        assert r_sub.status_code == 202
        assert r_sub.json()["id_empresa"] == str(subsidiaria_a.pk)

        # Sin empresa_id, user_a prioriza su empresa asignada (empresa_a) antes que la subsidiaria
        with django_capture_on_commit_callbacks(execute=True):
            r_def = client_a.post(URL_PRED + "analizar-reorden/", {}, format="json")
        assert r_def.status_code == 202
        assert r_def.json()["id_empresa"] == str(empresa_a.pk)

        # Empresa ajena → 403
        r_ajena = client_a.post(
            URL_PRED + "analizar-personalizacion/",
            {"empresa_id": str(empresa_b.pk)},
            format="json",
        )
        assert r_ajena.status_code == 403
        assert client_a.get(f"{URL_PRED}metricas-clasificador/?empresa_id={empresa_b.pk}").status_code == 403
        assert client_a.get(f"{URL_PRED}metricas-clasificador/?empresa_id={subsidiaria_a.pk}").status_code == 200
        assert client_a.get(f"{URL_PRED}metricas-clasificador/?empresa_id=bad-uuid").status_code == 400

    def test_sugerencias_activas_multiempresa_y_filtro_empresa_id(self, client_a, empresa_a, empresa_b, subsidiaria_a):
        p_mat = PrediccionAgente.objects.create(
            id_empresa=empresa_a,
            agente="cobranza_estratega",
            input_texto="Matriz",
            categoria_predicha="alta",
            confianza=0.9,
        )
        p_sub = PrediccionAgente.objects.create(
            id_empresa=subsidiaria_a,
            agente="reorden_sugeridor",
            input_texto="Sub",
            categoria_predicha="REORDENAR",
            confianza=0.8,
        )
        p_b = PrediccionAgente.objects.create(
            id_empresa=empresa_b,
            agente="cobranza_estratega",
            input_texto="Ajena",
            categoria_predicha="alta",
            confianza=0.99,
        )
        r_all = client_a.get(f"{URL_PRED}sugerencias-activas/")
        assert r_all.status_code == 200
        ids_all = {s["id"] for s in r_all.json()["sugerencias"]}
        assert {str(p_mat.pk), str(p_sub.pk)} <= ids_all
        assert str(p_b.pk) not in ids_all

        r_sub = client_a.get(f"{URL_PRED}sugerencias-activas/?empresa_id={subsidiaria_a.pk}")
        assert [s["id"] for s in r_sub.json()["sugerencias"]] == [str(p_sub.pk)]
        assert client_a.get(f"{URL_PRED}sugerencias-activas/?empresa_id={empresa_b.pk}").status_code == 403

    def test_superusuario_omni_exige_empresa_id_explicito(
        self, empresa_a, empresa_b, django_capture_on_commit_callbacks
    ):
        User = get_user_model()
        super_u = User.objects.create_user(
            username="super_omni_p22",
            password="x",
            email="super@omni.test",
            is_active=True,
            es_superusuario_omni=True,
        )
        c = APIClient()
        c.force_authenticate(user=super_u)

        assert c.post(URL_PRED + "analizar-cobranza/", {}, format="json").status_code == 400
        assert c.post(URL_PRED + "analizar-reorden/", {}, format="json").status_code == 400
        assert c.post(URL_PRED + "analizar-personalizacion/", {}, format="json").status_code == 400
        assert c.get(f"{URL_PRED}metricas-clasificador/").status_code == 400
        assert c.get(f"{URL_PRED}sugerencias-activas/").status_code == 400

        with django_capture_on_commit_callbacks(execute=True):
            r_ok = c.post(
                URL_PRED + "analizar-cobranza/",
                {"empresa_id": str(empresa_b.pk)},
                format="json",
            )
        assert r_ok.status_code == 202
        assert r_ok.json()["id_empresa"] == str(empresa_b.pk)
        assert c.get(f"{URL_PRED}metricas-clasificador/?empresa_id={empresa_b.pk}").status_code == 200
        assert c.get(f"{URL_PRED}sugerencias-activas/?empresa_id={empresa_b.pk}").status_code == 200

    def test_usuario_con_id_empresa_propia_la_usa_como_default(
        self, user_a, empresa_a, subsidiaria_a, django_capture_on_commit_callbacks
    ):
        user_a.id_empresa = subsidiaria_a  # atributo opcional en memoria
        c = APIClient()
        c.force_authenticate(user=user_a)
        with django_capture_on_commit_callbacks(execute=True):
            resp = c.post(URL_PRED + "analizar-personalizacion/", {}, format="json")
        assert resp.status_code == 202
        assert resp.json()["id_empresa"] == str(subsidiaria_a.pk)


# ── 3. Ejecución real del worker Celery para los 4 agentes ────────────────────


class TestWorkerCeleryAgentes:
    @override_settings(RLS_ENABLED=True)
    def test_worker_cobranza_real_con_cxc_y_rls(self, rls_test_role, empresa_a, empresa_b, user_a):
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar
        from tests.factories import ClienteFactory

        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            with rls.rls_bypass():
                cli_a = ClienteFactory(id_empresa=empresa_a, razon_social="Deudor Alpha")
                CuentaPorCobrar.objects.create(
                    cliente=cli_a,
                    empresa=empresa_a,
                    monto=Decimal("1500.00"),
                    fecha_emision=date.today() - timedelta(days=45),
                    fecha_vencimiento=date.today() - timedelta(days=20),
                    estado="vencida",
                )
                cli_b = ClienteFactory(id_empresa=empresa_b, razon_social="Deudor Beta Ajeno")
                CuentaPorCobrar.objects.create(
                    cliente=cli_b,
                    empresa=empresa_b,
                    monto=Decimal("9999.00"),
                    fecha_emision=date.today() - timedelta(days=90),
                    fecha_vencimiento=date.today() - timedelta(days=60),
                    estado="vencida",
                )
                ej = EjecucionAgente.objects.create(
                    id_empresa=empresa_a,
                    agente="cobranza_estratega",
                    parametros={"persistir": True},
                    iniciado_por=user_a,
                )

            rls.apply_system_default()
            assert EjecucionAgente.objects.count() == 0

            res = ejecutar_analisis_agente.apply(args=[str(ej.pk), str(empresa_a.pk)]).get()
            assert res["total"] == 1
            assert res["sugerencias"][0]["cliente_nombre"] == "Deudor Alpha"
            assert res["sugerencias"][0]["monto"] == "1500.00"
            assert res["sugerencias"][0]["canal_sugerido"]

            assert rls._get_current_context() == ("off", "")

            with rls.rls_bypass():
                ej.refresh_from_db()
                assert ej.estado == "completado"
                assert ej.fecha_inicio is not None
                assert ej.fecha_fin is not None
                assert ej.resultado["total"] == 1
                assert PrediccionAgente.objects.filter(id_empresa=empresa_a, agente="cobranza_estratega").count() == 1
        finally:
            rls.apply_system_default()
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")

    def test_worker_reorden_real_serializa_decimal(self, empresa_a, user_a):
        from apps.inventario.models import MovimientoInventario, StockActual
        from tests.factories import AlmacenFactory, ProductoFactory

        prod = ProductoFactory(id_empresa=empresa_a, nombre_producto="Filtro Aceite")
        alm = AlmacenFactory(id_empresa=empresa_a, nombre_almacen="Principal")
        StockActual.objects.create(
            id_empresa=empresa_a,
            id_producto=prod,
            id_almacen=alm,
            cantidad_disponible=Decimal("4"),
            cantidad_minima=Decimal("10"),
        )
        MovimientoInventario.objects.create(
            id_empresa=empresa_a,
            fecha_hora_movimiento=timezone.now() - timedelta(days=2),
            tipo_movimiento="SALIDA",
            id_producto=prod,
            cantidad=Decimal("30"),
            id_almacen_origen=alm,
            id_usuario_registro=user_a,
        )
        ej = EjecucionAgente.objects.create(
            id_empresa=empresa_a,
            agente="reorden_sugeridor",
            parametros={"solo_alertas": True, "persistir": False},
        )
        ejecutar_analisis_agente.apply(args=[str(ej.pk), str(empresa_a.pk)]).get()
        ej.refresh_from_db()
        assert ej.estado == "completado"
        assert ej.resultado["total"] == 1
        item = ej.resultado["sugerencias"][0]
        assert item["nombre_producto"] == "Filtro Aceite"
        assert Decimal(item["stock_disponible"]) == Decimal("4")
        assert Decimal(item["cantidad_sugerida"]) == Decimal("26")
        assert item["prioridad"] == "alta"

    def test_worker_personalizacion_serializa_dataclasses_y_decimal(self, empresa_a):
        from tests.factories import ProductoFactory

        ProductoFactory(
            id_empresa=empresa_a,
            nombre_producto="Margen Bajo",
            precio_venta_sugerido=Decimal("10.50"),
            costo_promedio=Decimal("10.00"),
        )
        ej = EjecucionAgente.objects.create(
            id_empresa=empresa_a,
            agente="personalizacion_capa2",
            parametros={},
        )
        ejecutar_analisis_agente.apply(args=[str(ej.pk), str(empresa_a.pk)]).get()
        ej.refresh_from_db()
        assert ej.estado == "completado"
        assert len(ej.resultado["listas_precios"]) == 1
        assert ej.resultado["listas_precios"][0]["ajuste_porcentual"] == "10.00"

    def test_worker_clasificador_gastos_aplicar_true_y_false(self, empresa_a, gasto_a):
        from apps.gastos.models import CategoriaGasto

        ej_sin = EjecucionAgente.objects.create(
            id_empresa=empresa_a,
            agente="clasificador_gastos",
            parametros={"gasto_id": str(gasto_a.pk), "aplicar": False},
        )
        ejecutar_analisis_agente.apply(args=[str(ej_sin.pk), str(empresa_a.pk)]).get()
        ej_sin.refresh_from_db()
        assert ej_sin.estado == "completado"
        assert ej_sin.resultado["categoria"] == "alimentacion"
        assert ej_sin.resultado["aplicado"] is False

        ej_con = EjecucionAgente.objects.create(
            id_empresa=empresa_a,
            agente="clasificador_gastos",
            parametros={"gasto_id": str(gasto_a.pk), "aplicar": True},
        )
        ejecutar_analisis_agente.apply(args=[str(ej_con.pk), str(empresa_a.pk)]).get()
        ej_con.refresh_from_db()
        assert ej_con.estado == "completado"
        assert ej_con.resultado["aplicado"] is True
        gasto_a.refresh_from_db()
        assert str(gasto_a.id_categoria_gasto_id) == ej_con.resultado["categoria_id"]
        assert CategoriaGasto.objects.filter(id_empresa=empresa_a, nombre_categoria="Alimentacion").exists()

    def test_worker_clasificador_prediccion_id_exacto_y_sin_duplicar_categoria(self, empresa_a, moneda_usd):
        from apps.gastos.models import CategoriaGasto, Gasto

        cat_existente = CategoriaGasto.objects.create(
            id_empresa=empresa_a,
            nombre_categoria="Servicios Profesionales",
        )
        gasto = Gasto.objects.create(
            id_empresa=empresa_a,
            fecha_gasto=date.today(),
            descripcion="honorario contador mensual",
            monto=Decimal("200.00"),
            id_moneda=moneda_usd,
            id_categoria_gasto=cat_existente,
            estado_gasto="PENDIENTE_APROBACION",
        )
        # Predicción previa con la misma descripción (colisión potencial si no se usa prediccion_id exacto)
        pred_vieja = PrediccionAgente.objects.create(
            id_empresa=empresa_a,
            agente="clasificador_gastos",
            input_texto=gasto.descripcion,
            categoria_predicha="otros",
            confianza=0.4,
            resultado_humano="pendiente",
        )

        ej = EjecucionAgente.objects.create(
            id_empresa=empresa_a,
            agente="clasificador_gastos",
            parametros={"gasto_id": str(gasto.pk), "aplicar": True},
        )
        ejecutar_analisis_agente.apply(args=[str(ej.pk), str(empresa_a.pk)]).get()
        ej.refresh_from_db()
        assert ej.estado == "completado"
        assert ej.resultado["categoria"] == "servicios_profesionales"
        assert ej.resultado["aplicado"] is True
        assert ej.resultado["categoria_id"] == str(cat_existente.pk)
        assert CategoriaGasto.objects.filter(id_empresa=empresa_a).count() == 1

        pred_vieja.refresh_from_db()
        assert pred_vieja.resultado_humano == "pendiente"
        pred_nueva = PrediccionAgente.objects.get(pk=ej.resultado["prediccion_id"])
        assert pred_nueva.pk != pred_vieja.pk
        assert pred_nueva.resultado_humano == "aceptada"

    def test_worker_ejecucion_inexistente_reintenta_y_retorna_limpio(self, empresa_a):
        with patch.object(ejecutar_analisis_agente, "retry", wraps=ejecutar_analisis_agente.retry) as retry_mock:
            with pytest.raises(Retry):
                ejecutar_analisis_agente.apply(args=[str(uuid.uuid4()), str(empresa_a.pk)]).get()
        retry_mock.assert_called_once_with(countdown=2)

        # Al agotar max_retries (=1), registra warning y retorna None sin crashear
        assert (
            ejecutar_analisis_agente.apply(
                args=[str(uuid.uuid4()), str(empresa_a.pk)],
                retries=ejecutar_analisis_agente.max_retries,
            ).get()
            is None
        )
        assert ejecutar_analisis_agente.apply(args=["no-uuid", "tampoco"]).get() is None

    def test_worker_gasto_eliminado_marca_fallido_controlado(self, empresa_a):
        ej = EjecucionAgente.objects.create(
            id_empresa=empresa_a,
            agente="clasificador_gastos",
            parametros={"gasto_id": str(uuid.uuid4()), "aplicar": False},
        )
        ejecutar_analisis_agente.apply(args=[str(ej.pk), str(empresa_a.pk)]).get()
        ej.refresh_from_db()
        assert ej.estado == "fallido"
        assert ej.mensaje_error == "El gasto solicitado no fue encontrado."
        assert ej.fecha_fin is not None

    def test_worker_agente_desconocido_marca_fallido_y_str_modelo(self, empresa_a):
        ej = EjecucionAgente.objects.create(
            id_empresa=empresa_a,
            agente="no_existe",
            parametros={},
        )
        assert "no_existe" in str(ej)
        assert ejecutar_analisis_agente.apply(args=[str(ej.pk), str(empresa_a.pk)]).get() is None
        ej.refresh_from_db()
        assert ej.estado == "fallido"
        assert ej.mensaje_error == "No se pudo completar el análisis del agente."


# ── 4. Error en worker y saneamiento R-CODE-8 ─────────────────────────────────


class TestErrorSanitizadoRCode8:
    def test_error_worker_no_expone_traceback_ni_secretos(
        self, client_a, empresa_a, django_capture_on_commit_callbacks
    ):
        secreto = 'Traceback (most recent call last):\nFile "x.py", line 1\napi_key=ci-only-dummy-key-ant-999'
        with patch("apps.agentes.cobranza.CobranzaEstrategaAgent.analizar", side_effect=RuntimeError(secreto)):
            with django_capture_on_commit_callbacks(execute=True):
                resp_post = client_a.post(URL_PRED + "analizar-cobranza/", {}, format="json")

        assert resp_post.status_code == 202
        ej_id = resp_post.json()["id_ejecucion"]

        resp_get = client_a.get(f"{URL_EJEC}{ej_id}/")
        assert resp_get.status_code == 200
        body = resp_get.json()
        assert body["estado"] == "fallido"
        assert body["fecha_fin"] is not None
        assert body["mensaje_error"] == "No se pudo completar el análisis del agente."
        dumped = json.dumps(body)
        assert "ci-only-dummy-key-ant-999" not in dumped
        assert "Traceback" not in dumped
        assert "api_key" not in dumped


# ── 5. PostgreSQL RLS en agentes_ejecucion_agente ─────────────────────────────


@pytest.mark.tenant
class TestRlsEjecucionAgente:
    @override_settings(RLS_ENABLED=True)
    def test_rls_force_aisla_tenants_y_bloquea_with_check(self, rls_test_role, empresa_a, empresa_b):
        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            with rls.rls_bypass():
                ej_a = EjecucionAgente.objects.create(id_empresa=empresa_a, agente="cobranza_estratega")
                ej_b = EjecucionAgente.objects.create(id_empresa=empresa_b, agente="reorden_sugeridor")

            rls.apply_system_default()
            assert EjecucionAgente.objects.count() == 0

            with rls.rls_tenant_context([empresa_a.pk]):
                assert set(EjecucionAgente.objects.values_list("pk", flat=True)) == {ej_a.pk}
                with pytest.raises((IntegrityError, ProgrammingError)):
                    with transaction.atomic():
                        EjecucionAgente.objects.create(id_empresa=empresa_b, agente="cobranza_estratega")

            with rls.rls_tenant_context([empresa_b.pk]):
                assert set(EjecucionAgente.objects.values_list("pk", flat=True)) == {ej_b.pk}
        finally:
            rls.apply_system_default()
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")


# ── 6. EjecucionAgenteViewSet + Rate Throttle + UUID + NulSafe + Admin ────────


@pytest.mark.tenant
class TestEjecucionAgenteViewSetYAdmin:
    def test_listado_filtrado_busqueda_y_solo_lectura(self, client_a, client_b, empresa_a, empresa_b):
        ej_a1 = EjecucionAgente.objects.create(
            id_empresa=empresa_a,
            agente="cobranza_estratega",
            estado="completado",
            celery_task_id="task-alpha-1",
        )
        ej_a2 = EjecucionAgente.objects.create(
            id_empresa=empresa_a,
            agente="reorden_sugeridor",
            estado="fallido",
            celery_task_id="task-alpha-2",
        )
        ej_b = EjecucionAgente.objects.create(
            id_empresa=empresa_b,
            agente="cobranza_estratega",
            estado="completado",
            celery_task_id="task-beta-1",
        )

        # Solo ve ejecuciones de empresa A
        r_list = client_a.get(URL_EJEC)
        assert r_list.status_code == 200
        ids = {row["id_ejecucion"] for row in r_list.json()["results"]}
        assert ids == {str(ej_a1.pk), str(ej_a2.pk)}
        assert str(ej_b.pk) not in ids

        # Filtros ?agente= y ?estado= y ?search=
        r_filtro = client_a.get(f"{URL_EJEC}?agente=cobranza_estratega&estado=completado")
        assert [row["id_ejecucion"] for row in r_filtro.json()["results"]] == [str(ej_a1.pk)]

        r_search = client_a.get(f"{URL_EJEC}?search=task-alpha-2")
        assert [row["id_ejecucion"] for row in r_search.json()["results"]] == [str(ej_a2.pk)]

        # Anti-IDOR cross-tenant en retrieve -> 404
        assert client_a.get(f"{URL_EJEC}{ej_b.pk}/").status_code == 404
        assert client_b.get(f"{URL_EJEC}{ej_a1.pk}/").status_code == 404

        # Solo lectura
        assert client_a.post(URL_EJEC, {}, format="json").status_code == 405
        assert client_a.patch(f"{URL_EJEC}{ej_a1.pk}/", {}, format="json").status_code == 405
        assert client_a.delete(f"{URL_EJEC}{ej_a1.pk}/").status_code == 405

    def test_uuid_invalido_400_y_nul_bytes_400(self, client_a):
        # 36 chars coincidiendo con lookup_value_regex pero UUID inválido → 400 (no 500)
        assert client_a.get(f"{URL_EJEC}000000000000000000000000000000000000/").status_code == 400
        assert client_a.get(f"{URL_EJEC}------------------------------------/").status_code == 400
        assert client_a.get(f"{URL_PRED}000000000000000000000000000000000000/").status_code == 400
        # NUL bytes en query params → 400 (NulSafeFilterMixin + get_queryset)
        assert client_a.get(f"{URL_EJEC}?search=abc%00def").status_code == 400
        assert client_a.get(f"{URL_EJEC}?agente=cobranza%00").status_code == 400
        assert client_a.get(f"{URL_EJEC}?estado=pendiente%00").status_code == 400
        assert client_a.get(f"{URL_EJEC}?ordering=estado%00").status_code == 400
        assert client_a.get(f"{URL_PRED}?agente=cobranza%00").status_code == 400
        assert client_a.get(f"{URL_PRED}sugerencias-activas/?limite=abc").status_code == 400
        assert client_a.get(f"{URL_PRED}sugerencias-activas/?agente=x%00").status_code == 400

    def test_escritura_rate_throttle_en_4_acciones_post(self, client_a, empresa_a):
        from apps.agentes.views import PrediccionAgenteViewSet
        from apps.core.throttling import EscrituraRateThrottle

        for action_name in (
            "analizar_cobranza",
            "analizar_reorden",
            "analizar_personalizacion",
            "clasificar_gasto",
        ):
            method = getattr(PrediccionAgenteViewSet, action_name)
            throttles = method.kwargs.get("throttle_classes", [])
            assert any(issubclass(t, EscrituraRateThrottle) for t in throttles), action_name

        with patch.object(EscrituraRateThrottle, "get_rate", return_value="2/min"):
            assert client_a.post(URL_PRED + "analizar-cobranza/", {}, format="json").status_code == 202
            assert client_a.post(URL_PRED + "analizar-reorden/", {}, format="json").status_code == 202
            assert client_a.post(URL_PRED + "analizar-personalizacion/", {}, format="json").status_code == 429
            # GETs no consumen cuota ni quedan bloqueados por EscrituraRateThrottle
            assert client_a.get(f"{URL_PRED}metricas-clasificador/").status_code == 200

    def test_sin_auth_401(self):
        c = APIClient()
        assert c.get(URL_EJEC).status_code == 401

    def test_admin_ejecucion_agente_solo_lectura(self, user_a):
        model_admin = django_admin.site._registry[EjecucionAgente]
        req = RequestFactory().get("/admin/")
        req.user = user_a
        assert model_admin.has_add_permission(req) is False
        assert model_admin.has_change_permission(req) is False
        assert model_admin.has_delete_permission(req) is False


# ── 7. Paridad MCP (R-CODE-7) ─────────────────────────────────────────────────


@pytest.mark.tenant
class TestMcpAgentesParity:
    @pytest.fixture
    def tokens(self, empresa_a, empresa_b):
        tok_a = CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="Agentes A RW",
            scopes=["agentes:read", "agentes:write"],
        )
        tok_a_ro = CapabilityToken.objects.create(
            empresa=empresa_a,
            nombre="Agentes A RO",
            scopes=["agentes:read"],
        )
        tok_b = CapabilityToken.objects.create(
            empresa=empresa_b,
            nombre="Agentes B RW",
            scopes=["agentes:read", "agentes:write"],
        )
        return tok_a, tok_a_ro, tok_b

    def test_mcp_tools_autodiscovery_y_fastmcp(self):
        from apps.agentes.mcp import MCP_TOOLS
        from apps.core import mcp_server

        nombres = {t["name"] for t in MCP_TOOLS}
        assert nombres == {
            "agentes_disparar_analisis",
            "agentes_obtener_ejecucion",
            "agentes_listar_ejecuciones",
            "agentes_resumen_consumo_llm",
        }
        assert nombres.issubset(mcp_server._DISCOVERED_TOOLS.keys())
        registered = {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}
        assert nombres.issubset(registered)

    @pytest.mark.django_db(transaction=True)
    @override_settings(RLS_ENABLED=True)
    def test_mcp_disparar_consultar_listar_y_aislamiento(self, rls_test_role, tokens, empresa_a, empresa_b, gasto_a):
        from apps.agentes import mcp as agentes_mcp

        tok_a, tok_a_ro, tok_b = tokens
        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            rls.apply_system_default()

            # 1. Disparar análisis desde fail-closed
            ej_res = agentes_mcp.agentes_disparar_analisis(
                str(tok_a.token),
                str(empresa_a.pk),
                "clasificador_gastos",
                gasto_id=str(gasto_a.pk),
                aplicar=False,
            )
            assert ej_res["agente"] == "clasificador_gastos"
            assert ej_res["estado"] == "completado"
            assert ej_res["resultado"]["categoria"] == "alimentacion"
            assert rls._get_current_context() == ("off", "")

            # 2. Consultar ejecución por ID
            obtenido = agentes_mcp.agentes_obtener_ejecucion(
                str(tok_a_ro.token),
                str(empresa_a.pk),
                ej_res["id_ejecucion"],
            )
            assert obtenido["id_ejecucion"] == ej_res["id_ejecucion"]
            assert rls._get_current_context() == ("off", "")

            # 3. Listar ejecuciones
            listado = agentes_mcp.agentes_listar_ejecuciones(
                str(tok_a_ro.token),
                str(empresa_a.pk),
                agente="clasificador_gastos",
            )
            assert listado["total"] == 1
            assert listado["ejecuciones"][0]["id_ejecucion"] == ej_res["id_ejecucion"]

            # 4. Scope insuficiente → PermissionError
            with pytest.raises(PermissionError):
                agentes_mcp.agentes_disparar_analisis(
                    str(tok_a_ro.token),
                    str(empresa_a.pk),
                    "cobranza_estratega",
                )

            # 5. Cross-tenant → PermissionError o no encontrado
            with pytest.raises(PermissionError):
                agentes_mcp.agentes_obtener_ejecucion(
                    str(tok_a.token),
                    str(empresa_b.pk),
                    ej_res["id_ejecucion"],
                )
            cross = agentes_mcp.agentes_obtener_ejecucion(
                str(tok_b.token),
                str(empresa_b.pk),
                ej_res["id_ejecucion"],
            )
            assert "error" in cross

            # 6. Validación de UUID, NUL bytes, bool en limite, otros agentes
            assert "error" in agentes_mcp.agentes_obtener_ejecucion(str(tok_a.token), str(empresa_a.pk), "no-uuid")
            assert "error" in agentes_mcp.agentes_obtener_ejecucion(str(tok_a.token), str(empresa_a.pk), "abc\x00def")
            assert "error" in agentes_mcp.agentes_disparar_analisis(
                str(tok_a.token),
                str(empresa_a.pk),
                "clasificador_gastos",
                gasto_id="no-uuid",
            )
            assert "error" in agentes_mcp.agentes_disparar_analisis(
                str(tok_a.token),
                str(empresa_a.pk),
                "clasificador_gastos",
            )
            assert "error" in agentes_mcp.agentes_disparar_analisis(
                str(tok_a.token),
                str(empresa_a.pk),
                "clasificador_gastos",
                gasto_id=str(uuid.uuid4()),
            )
            assert "error" in agentes_mcp.agentes_disparar_analisis(
                str(tok_a.token),
                str(empresa_a.pk),
                "agente\x00falso",
            )
            assert "error" in agentes_mcp.agentes_disparar_analisis(
                str(tok_a.token),
                str(empresa_a.pk),
                "agente_falso",
            )
            assert "error" in agentes_mcp.agentes_listar_ejecuciones(
                str(tok_a.token),
                str(empresa_a.pk),
                agente="x\x00y",
            )
            assert "error" in agentes_mcp.agentes_listar_ejecuciones(
                str(tok_a.token),
                str(empresa_a.pk),
                limite=True,  # type: ignore[arg-type]
            )
            assert "error" in agentes_mcp.agentes_listar_ejecuciones(
                str(tok_a.token),
                str(empresa_a.pk),
                limite="bad",  # type: ignore[arg-type]
            )

            # 7. Disparo MCP para los otros 3 agentes y filtro por estado
            r_cob = agentes_mcp.agentes_disparar_analisis(
                str(tok_a.token), str(empresa_a.pk), "cobranza_estratega", persistir=False
            )
            r_reo = agentes_mcp.agentes_disparar_analisis(
                str(tok_a.token), str(empresa_a.pk), "reorden_sugeridor", solo_alertas=True, persistir=False
            )
            r_per = agentes_mcp.agentes_disparar_analisis(str(tok_a.token), str(empresa_a.pk), "personalizacion_capa2")
            assert r_cob["estado"] == "completado"
            assert r_reo["estado"] == "completado"
            assert r_per["estado"] == "completado"
            list_comp = agentes_mcp.agentes_listar_ejecuciones(
                str(tok_a_ro.token), str(empresa_a.pk), estado="completado"
            )
            assert list_comp["total"] >= 4

            # 8. Empresa inactiva rechazada
            with rls.rls_bypass():
                Empresa.objects.filter(pk=empresa_a.pk).update(activo=False)
            inactiva = agentes_mcp.agentes_disparar_analisis(str(tok_a.token), str(empresa_a.pk), "cobranza_estratega")
            assert inactiva == {"error": "Empresa inactiva o no encontrada."}
            assert rls._get_current_context() == ("off", "")
        finally:
            with rls.rls_bypass():
                Empresa.objects.filter(pk=empresa_a.pk).update(activo=True)
            rls.apply_system_default()
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")

    def test_mcp_errores_bd_y_services_jsonable(self, tokens, empresa_a):
        from apps.agentes import mcp as agentes_mcp
        from apps.agentes.services import AgenteError, encolar_ejecucion_agente, jsonable

        tok_a, _ro, _b = tokens

        uid = uuid.uuid4()
        hoy = date.today()
        sentinel = object()
        assert jsonable({"u": uid, "d": hoy, "o": sentinel}) == {
            "u": str(uid),
            "d": hoy.isoformat(),
            "o": str(sentinel),
        }
        with pytest.raises(AgenteError):
            encolar_ejecucion_agente(empresa=empresa_a, agente="agente_invalido")

        with patch("apps.agentes.services.encolar_ejecucion_agente", side_effect=RuntimeError("password=secret")):
            err = agentes_mcp.agentes_disparar_analisis(str(tok_a.token), str(empresa_a.pk), "cobranza_estratega")
        assert "error" in err
        assert "secret" not in err["error"]

        with patch("apps.agentes.models.EjecucionAgente.objects.filter", side_effect=RuntimeError("SELECT * FROM x")):
            err_get = agentes_mcp.agentes_obtener_ejecucion(str(tok_a.token), str(empresa_a.pk), str(uid))
            err_lst = agentes_mcp.agentes_listar_ejecuciones(str(tok_a.token), str(empresa_a.pk))
        assert "SELECT" not in err_get["error"]
        assert "SELECT" not in err_lst["error"]
