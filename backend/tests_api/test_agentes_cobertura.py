"""
Backfill de cobertura — apps/agentes/ (plan "Cero Dudas").

Cubre, SIN duplicar lo ya testeado en test_m9_agentes.py (reglas de cobranza/
reorden con evaluar()), test_sesion_l_agentes_ui.py (sugerencias-activas y
responder) ni test_chat_empresa_sec1.py (SEC-1 de empresa de trabajo):

  - apps/agentes/base.py        — OmniAgente: ciclo SOMBRA/SUGERENCIA/AUTONOMO,
                                   inactivo, errores en _ejecutar/_persistir.
  - apps/agentes/reorden.py     — analizar() contra BD (consumo 30d, persistencia,
                                   solo_alertas) y rama LLM con cliente mockeado.
  - apps/agentes/views.py       — acciones custom: analizar-cobranza/reorden
                                   (vacío, 403, 500), clasificar-gasto, métricas,
                                   evaluar y helpers de títulos/acciones.
  - apps/agentes/api/chat.py    — _jsonable, _sanitize_messages, tools de datos
                                   (tasa BCV, aging, saldo), _dispatch_tool y la
                                   vista SSE (sin API key y con Anthropic mockeado).

Toda llamada LLM externa está mockeada — cero red.
"""
import json
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.agentes.base import OmniAgente, Prediccion, ResultadoAccion
from apps.agentes.models import ConfigAgente, PrediccionAgente

pytestmark = pytest.mark.django_db


# ══════════════════════════════════════════════════════════════════════════════
# apps/agentes/base.py — OmniAgente
# ══════════════════════════════════════════════════════════════════════════════


class _AgenteDummy(OmniAgente):
    AGENTE_ID = "clasificador_gastos"

    def __init__(self, confianza=0.9, fallar_ejecucion=False):
        super().__init__()
        self.confianza = confianza
        self.fallar_ejecucion = fallar_ejecucion
        self.ejecuciones = 0

    def _analizar(self, contexto):
        return Prediccion(
            categoria="alimentacion",
            confianza=self.confianza,
            razonamiento="test",
            alternativas=[{"categoria": "otros", "confianza": 0.1}],
            metadata={"origen": "test"},
        )

    def _ejecutar(self, prediccion):
        self.ejecuciones += 1
        if self.fallar_ejecucion:
            raise RuntimeError("boom")
        return ResultadoAccion(ejecutado=True, descripcion="acción test", datos={"k": 1})


class TestOmniAgenteBase:
    def test_sin_agente_id_lanza_valueerror(self):
        class SinId(OmniAgente):
            pass

        with pytest.raises(ValueError, match="AGENTE_ID"):
            SinId()

    def test_analizar_no_implementado_lanza(self):
        class SoloId(OmniAgente):
            AGENTE_ID = "clasificador_gastos"

        with pytest.raises(NotImplementedError):
            SoloId()._analizar({})

    def test_ejecutar_default_no_hace_nada(self):
        class SoloId(OmniAgente):
            AGENTE_ID = "clasificador_gastos"

        res = SoloId()._ejecutar(Prediccion(categoria="x", confianza=1.0))
        assert res.ejecutado is False
        assert "sin acción" in res.descripcion

    def test_sombra_por_defecto_registra_y_no_ejecuta(self, empresa_a):
        """Sin ConfigAgente → defaults SOMBRA y persiste PrediccionAgente."""
        agente = _AgenteDummy()
        res = agente.procesar(str(empresa_a.id_empresa), {}, input_texto="almuerzo")

        assert res["nivel"] == "SOMBRA"
        assert res["activo"] is True
        assert res["ejecutado"] is False
        assert res["sugerencia"] is False
        assert res["accion"] is None
        assert agente.ejecuciones == 0
        assert res["prediccion"]["categoria"] == "alimentacion"

        pred = PrediccionAgente.objects.get(pk=res["id_prediccion"])
        assert pred.agente == "clasificador_gastos"
        assert pred.input_texto == "almuerzo"
        assert pred.confianza == 0.9
        assert pred.input_metadata == {"origen": "test"}

    def test_config_inactiva_omite_procesamiento(self, empresa_a):
        ConfigAgente.objects.create(
            id_empresa=empresa_a, agente="clasificador_gastos",
            nivel_autonomia="AUTONOMO", activo=False,
        )
        res = _AgenteDummy().procesar(str(empresa_a.id_empresa), {})
        assert res == {"nivel": "AUTONOMO", "activo": False, "ejecutado": False}
        assert PrediccionAgente.objects.count() == 0

    def test_sugerencia_marca_flag(self, empresa_a):
        ConfigAgente.objects.create(
            id_empresa=empresa_a, agente="clasificador_gastos",
            nivel_autonomia="SUGERENCIA",
        )
        res = _AgenteDummy().procesar(str(empresa_a.id_empresa), {})
        assert res["sugerencia"] is True
        assert res["ejecutado"] is False

    def test_autonomo_ejecuta_si_confianza_supera_umbral(self, empresa_a):
        ConfigAgente.objects.create(
            id_empresa=empresa_a, agente="clasificador_gastos",
            nivel_autonomia="AUTONOMO", umbral_confianza_minimo=0.8,
        )
        agente = _AgenteDummy(confianza=0.95)
        res = agente.procesar(str(empresa_a.id_empresa), {}, input_monto=Decimal("10.00"))

        assert res["ejecutado"] is True
        assert agente.ejecuciones == 1
        assert res["accion"] == {"descripcion": "acción test", "datos": {"k": 1}, "error": None}

    def test_autonomo_no_ejecuta_bajo_umbral(self, empresa_a):
        ConfigAgente.objects.create(
            id_empresa=empresa_a, agente="clasificador_gastos",
            nivel_autonomia="AUTONOMO", umbral_confianza_minimo=0.8,
        )
        agente = _AgenteDummy(confianza=0.5)
        res = agente.procesar(str(empresa_a.id_empresa), {})
        assert res["ejecutado"] is False
        assert agente.ejecuciones == 0

    def test_autonomo_error_en_ejecutar_no_tumba(self, empresa_a):
        ConfigAgente.objects.create(
            id_empresa=empresa_a, agente="clasificador_gastos",
            nivel_autonomia="AUTONOMO", umbral_confianza_minimo=0.5,
        )
        res = _AgenteDummy(fallar_ejecucion=True).procesar(str(empresa_a.id_empresa), {})
        assert res["ejecutado"] is False
        # la predicción se persiste igual
        assert res["id_prediccion"] is not None

    def test_persistir_falla_devuelve_id_none(self, empresa_a):
        """Si la BD falla al persistir, procesar() no revienta: id_prediccion=None."""
        with patch.object(
            PrediccionAgente.objects, "create", side_effect=RuntimeError("db down")
        ):
            res = _AgenteDummy().procesar(str(empresa_a.id_empresa), {})
        assert res["id_prediccion"] is None
        assert res["prediccion"]["categoria"] == "alimentacion"


# ══════════════════════════════════════════════════════════════════════════════
# apps/agentes/reorden.py — ReordenSugeridorAgent.analizar / rama LLM
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def stock_bajo(empresa_a, user_a):
    """Stock 5 uds (mínimo 10) con 30 uds de salidas en 30 días → consumo 1/día."""
    from tests_api.factories import AlmacenFactory, ProductoFactory
    from apps.inventario.models import MovimientoInventario, StockActual

    producto = ProductoFactory(id_empresa=empresa_a, nombre_producto="Aceite 1L")
    almacen = AlmacenFactory(id_empresa=empresa_a, nombre_almacen="Central")
    stock = StockActual.objects.create(
        id_empresa=empresa_a, id_producto=producto, id_almacen=almacen,
        cantidad_disponible=Decimal("5"), cantidad_minima=Decimal("10"),
    )
    MovimientoInventario.objects.create(
        id_empresa=empresa_a,
        fecha_hora_movimiento=timezone.now() - timedelta(days=3),
        tipo_movimiento="SALIDA",
        id_producto=producto,
        cantidad=Decimal("30"),
        id_almacen_origen=almacen,
        id_usuario_registro=user_a,
    )
    return stock


class TestReordenAnalizar:
    def test_analizar_calcula_consumo_y_persiste(self, empresa_a, stock_bajo):
        from apps.agentes.reorden import ReordenSugeridorAgent

        agente = ReordenSugeridorAgent(empresa=empresa_a)
        sugerencias = agente.analizar(persistir=True)

        assert len(sugerencias) == 1
        s = sugerencias[0]
        assert s.producto_nombre == "Aceite 1L"
        assert s.estado == "REORDENAR"
        assert s.consumo_diario == Decimal("1")        # 30 uds / 30 días
        assert s.dias_restantes == 5.0                 # 5 / 1
        assert s.cantidad_sugerida_reorden == Decimal("25.00")  # 1×30 − 5
        assert s.modelo_llm == "fallback-reglas"

        pred = PrediccionAgente.objects.get(agente="reorden_sugeridor")
        assert pred.categoria_predicha == "REORDENAR"
        assert pred.input_monto == Decimal("5")
        assert pred.alternativas == [{"cantidad_sugerida": "25.00"}]

    def test_solo_alertas_excluye_ok(self, empresa_a, stock_bajo):
        from tests_api.factories import AlmacenFactory, ProductoFactory
        from apps.agentes.reorden import ReordenSugeridorAgent
        from apps.inventario.models import StockActual

        # Stock holgado sin consumo → OK
        prod_ok = ProductoFactory(id_empresa=empresa_a, nombre_producto="Sal 1kg")
        StockActual.objects.create(
            id_empresa=empresa_a, id_producto=prod_ok,
            id_almacen=AlmacenFactory(id_empresa=empresa_a),
            cantidad_disponible=Decimal("1000"), cantidad_minima=Decimal("10"),
        )

        agente = ReordenSugeridorAgent(empresa=empresa_a)
        todas = agente.analizar(persistir=False)
        alertas = agente.analizar(solo_alertas=True, persistir=False)

        assert {s.estado for s in todas} == {"REORDENAR", "OK"}
        assert [s.estado for s in alertas] == ["REORDENAR"]

    def test_llm_inyectado_respuesta_valida(self, empresa_a, stock_bajo):
        from apps.agentes.reorden import ReordenSugeridorAgent

        llm = MagicMock()
        llm.messages.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps({
                "estado": "REVISAR",
                "cantidad_sugerida_reorden": 12,
                "razonamiento": "Consumo estable, revisar la próxima semana.",
            }))]
        )
        agente = ReordenSugeridorAgent(empresa=empresa_a, llm_client=llm)
        sugerencias = agente.analizar(persistir=False)

        assert len(sugerencias) == 1
        s = sugerencias[0]
        assert s.estado == "REVISAR"
        assert s.cantidad_sugerida_reorden == Decimal("12")
        assert s.razonamiento == "Consumo estable, revisar la próxima semana."
        assert s.modelo_llm == ReordenSugeridorAgent.MODELO_DEFAULT
        llm.messages.create.assert_called_once()

    def test_llm_estado_invalido_cae_a_ok(self, empresa_a, stock_bajo):
        from apps.agentes.reorden import ReordenSugeridorAgent

        llm = MagicMock()
        llm.messages.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(text=json.dumps({"estado": "PANICO"}))]
        )
        agente = ReordenSugeridorAgent(empresa=empresa_a, llm_client=llm)
        s = agente.analizar(persistir=False)[0]
        assert s.estado == "OK"

    def test_llm_excepcion_usa_fallback(self, empresa_a, stock_bajo):
        from apps.agentes.reorden import ReordenSugeridorAgent

        llm = MagicMock()
        llm.messages.create.side_effect = TimeoutError("sin red")
        agente = ReordenSugeridorAgent(empresa=empresa_a, llm_client=llm)
        s = agente.analizar(persistir=False)[0]

        assert s.estado == "REORDENAR"  # reglas deterministas
        assert s.modelo_llm == "fallback-error:TimeoutError"


# ══════════════════════════════════════════════════════════════════════════════
# apps/agentes/views.py — acciones custom del PrediccionAgenteViewSet
# ══════════════════════════════════════════════════════════════════════════════

URL_BASE = "/api/agentes/predicciones/"


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_sin_empresa(db):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(
        username="sin_empresa_cov", password="x", email="sin@cov.com", is_active=True
    )
    c = APIClient()
    c.force_authenticate(user=user)
    return c


class TestAnalizarCobranzaView:
    def test_cartera_vacia_200(self, client_a):
        resp = client_a.post(URL_BASE + "analizar-cobranza/", {}, format="json")
        assert resp.status_code == 200
        assert resp.json() == {"sugerencias": [], "total": 0}

    def test_sin_empresa_403(self, client_sin_empresa):
        resp = client_sin_empresa.post(URL_BASE + "analizar-cobranza/", {}, format="json")
        assert resp.status_code == 403

    def test_error_de_agente_500_sin_filtrar_detalle(self, client_a):
        with patch(
            "apps.agentes.cobranza.CobranzaEstrategaAgent.analizar",
            side_effect=RuntimeError("detalle interno secreto"),
        ):
            resp = client_a.post(URL_BASE + "analizar-cobranza/", {}, format="json")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "agente_error"
        assert "secreto" not in json.dumps(body)  # R-CODE-8


class TestAnalizarReordenView:
    def test_sin_stock_200_vacio(self, client_a):
        resp = client_a.post(URL_BASE + "analizar-reorden/", {}, format="json")
        assert resp.status_code == 200
        assert resp.json() == {"sugerencias": [], "total": 0}

    def test_sin_empresa_403(self, client_sin_empresa):
        resp = client_sin_empresa.post(URL_BASE + "analizar-reorden/", {}, format="json")
        assert resp.status_code == 403

    def test_error_de_agente_500(self, client_a):
        with patch(
            "apps.agentes.reorden.ReordenSugeridorAgent.analizar",
            side_effect=RuntimeError("x"),
        ):
            resp = client_a.post(URL_BASE + "analizar-reorden/", {}, format="json")
        assert resp.status_code == 500
        assert resp.json()["code"] == "agente_error"


class TestAnalizarPersonalizacionView:
    def test_empresa_nueva_200(self, client_a):
        resp = client_a.post(URL_BASE + "analizar-personalizacion/", {}, format="json")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"flujo_documentos", "listas_precios", "credito_clientes"}

    def test_sin_empresa_403(self, client_sin_empresa):
        resp = client_sin_empresa.post(
            URL_BASE + "analizar-personalizacion/", {}, format="json"
        )
        assert resp.status_code == 403

    def test_error_de_agente_500(self, client_a):
        with patch(
            "apps.agentes.personalizacion_agente.PersonalizacionCapa2Agent.analizar",
            side_effect=RuntimeError("x"),
        ):
            resp = client_a.post(URL_BASE + "analizar-personalizacion/", {}, format="json")
        assert resp.status_code == 500


class TestClasificarGastoView:
    @pytest.fixture
    def gasto(self, empresa_a, moneda_usd):
        from apps.gastos.models import CategoriaGasto, Gasto

        cat = CategoriaGasto.objects.create(
            id_empresa=empresa_a, nombre_categoria="Sin Clasificar"
        )
        return Gasto.objects.create(
            id_empresa=empresa_a,
            fecha_gasto=date.today(),
            descripcion="almuerzo en restaurant con cliente",
            monto=Decimal("45.00"),
            id_moneda=moneda_usd,
            id_categoria_gasto=cat,
            estado_gasto="PENDIENTE_APROBACION",
        )

    def test_sin_gasto_id_400(self, client_a):
        resp = client_a.post(URL_BASE + "clasificar-gasto/", {}, format="json")
        assert resp.status_code == 400

    def test_gasto_inexistente_404(self, client_a):
        import uuid

        resp = client_a.post(
            URL_BASE + "clasificar-gasto/", {"gasto_id": str(uuid.uuid4())}, format="json"
        )
        assert resp.status_code == 404

    def test_gasto_de_otra_empresa_404(self, user_b, gasto):
        """R-CODE-1: usuario de B no puede clasificar gastos de A."""
        c = APIClient()
        c.force_authenticate(user=user_b)
        resp = c.post(
            URL_BASE + "clasificar-gasto/", {"gasto_id": str(gasto.id_gasto)}, format="json"
        )
        assert resp.status_code == 404

    def test_clasifica_sin_aplicar(self, client_a, gasto):
        resp = client_a.post(
            URL_BASE + "clasificar-gasto/",
            {"gasto_id": str(gasto.id_gasto), "aplicar": False},
            format="json",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["categoria"] == "alimentacion"  # fallback por keywords
        assert body["aplicado"] is False
        assert body["categoria_id"] is None
        assert body["prediccion_id"] is not None

    def test_clasifica_y_aplica_crea_categoria(self, client_a, gasto):
        from apps.gastos.models import CategoriaGasto

        resp = client_a.post(
            URL_BASE + "clasificar-gasto/",
            {"gasto_id": str(gasto.id_gasto), "aplicar": True},
            format="json",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["aplicado"] is True

        gasto.refresh_from_db()
        assert str(gasto.id_categoria_gasto_id) == body["categoria_id"]
        assert CategoriaGasto.objects.filter(nombre_categoria="Alimentacion").exists()

        pred = PrediccionAgente.objects.get(pk=body["prediccion_id"])
        assert pred.resultado_humano == "aceptada"
        assert pred.categoria_correcta == "alimentacion"

    def test_error_de_agente_500(self, client_a, gasto):
        with patch(
            "apps.agentes.clasificador.ClasificadorGastos.clasificar",
            side_effect=RuntimeError("x"),
        ):
            resp = client_a.post(
                URL_BASE + "clasificar-gasto/", {"gasto_id": str(gasto.id_gasto)}, format="json"
            )
        assert resp.status_code == 500


class TestMetricasYEvaluar:
    def test_metricas_clasificador_200(self, client_a):
        resp = client_a.get(URL_BASE + "metricas-clasificador/")
        assert resp.status_code == 200
        assert "total" in resp.json()

    def test_metricas_sin_empresa_403(self, client_sin_empresa):
        resp = client_sin_empresa.get(URL_BASE + "metricas-clasificador/")
        assert resp.status_code == 403

    @pytest.fixture
    def prediccion(self, empresa_a):
        return PrediccionAgente.objects.create(
            id_empresa=empresa_a,
            agente="clasificador_gastos",
            input_texto="taxi al aeropuerto",
            categoria_predicha="transporte",
            confianza=0.7,
        )

    def test_evaluar_acepta_y_corrige(self, client_a, prediccion):
        resp = client_a.patch(
            URL_BASE + f"{prediccion.pk}/evaluar/",
            {"resultado_humano": "aceptada", "categoria_correcta": "transporte"},
            format="json",
        )
        assert resp.status_code == 200
        prediccion.refresh_from_db()
        assert prediccion.resultado_humano == "aceptada"
        assert prediccion.categoria_correcta == "transporte"

    def test_evaluar_valor_invalido_400(self, client_a, prediccion):
        resp = client_a.patch(
            URL_BASE + f"{prediccion.pk}/evaluar/",
            {"resultado_humano": "quizas"},
            format="json",
        )
        assert resp.status_code == 400


class TestHelpersSugerencias:
    def _pred(self, **kw):
        defaults = dict(
            agente="cobranza_estratega", input_metadata={}, input_monto=None,
            categoria_predicha="contactar", input_texto="",
        )
        defaults.update(kw)
        return PrediccionAgente(**defaults)

    def test_titulo_cobranza_con_cliente_y_monto(self):
        from apps.agentes.views import _titulo_sugerencia

        p = self._pred(
            input_metadata={"cliente_nombre": "ACME"}, input_monto=Decimal("100"),
        )
        assert _titulo_sugerencia(p) == "Contactar a ACME — $100"

    def test_titulo_cobranza_sin_cliente(self):
        from apps.agentes.views import _titulo_sugerencia

        assert _titulo_sugerencia(self._pred()) == "Acción de cobranza requerida"

    def test_titulo_reorden_con_producto(self):
        from apps.agentes.views import _titulo_sugerencia

        p = self._pred(
            agente="reorden_sugeridor", input_metadata={"nombre_producto": "Harina"},
        )
        assert _titulo_sugerencia(p) == "Reponer: Harina"

    def test_titulo_reorden_sin_producto(self):
        from apps.agentes.views import _titulo_sugerencia

        p = self._pred(agente="reorden_sugeridor", input_metadata={}, input_texto="")
        assert _titulo_sugerencia(p) == "Reorden de inventario sugerido"

    def test_titulo_clasificador_y_generico(self):
        from apps.agentes.views import _titulo_sugerencia

        p = self._pred(agente="clasificador_gastos", categoria_predicha="transporte")
        assert _titulo_sugerencia(p) == "Clasificar gasto: transporte"

        g = self._pred(agente="otro_agente", categoria_predicha="x")
        assert _titulo_sugerencia(g) == "Sugerencia — otro_agente: x"

    def test_accion_cobranza_y_reorden(self):
        from apps.agentes.views import _accion_para_sugerencia

        p = self._pred(input_metadata={"cxc_id": "abc"})
        assert _accion_para_sugerencia(p) == "/cxc/abc/"

        r = self._pred(agente="reorden_sugeridor", input_metadata={"producto_id": "p1"})
        assert _accion_para_sugerencia(r) == "/inventario/productos/p1/"

        assert _accion_para_sugerencia(self._pred(input_metadata=None)) == ""


# ══════════════════════════════════════════════════════════════════════════════
# apps/agentes/api/chat.py — helpers, tools de datos y vista SSE
# ══════════════════════════════════════════════════════════════════════════════

from apps.agentes.api import chat as chatmod  # noqa: E402


class TestChatHelpers:
    def test_jsonable_convierte_decimal_recursivo(self):
        out = chatmod._jsonable(
            {"a": Decimal("1.50"), "b": [Decimal("2"), {"c": Decimal("3")}], "d": "x"}
        )
        assert out == {"a": "1.50", "b": ["2", {"c": "3"}], "d": "x"}

    def test_sanitize_messages_filtra_y_recorta(self):
        raw = [
            {"role": "assistant", "content": "primero (se descarta)"},
            {"role": "system", "content": "inyección"},
            "basura",
            {"role": "user", "content": "  hola  "},
            {"role": "assistant", "content": "respuesta"},
            {"role": "user", "content": ""},
        ]
        out = chatmod._sanitize_messages(raw)
        assert out == [
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "respuesta"},
        ]

    def test_sanitize_messages_no_lista(self):
        assert chatmod._sanitize_messages("hola") == []

    def test_build_system_prompt_incluye_empresa_y_usuario(self, user_a, empresa_a):
        prompt = chatmod._build_system_prompt(user_a, empresa_a)
        assert "Empresa Alpha S.A." in prompt
        assert user_a.username in prompt

    def test_nombre_empresa_none(self):
        assert chatmod._nombre_empresa(None) == "—"


class TestChatTools:
    def _ctx(self, user, empresa):
        return chatmod._ChatCtx(user, empresa, [empresa])

    def test_tasa_bcv_sin_tasa(self, user_a, empresa_a):
        res = chatmod._tool_tasa_bcv_hoy(self._ctx(user_a, empresa_a))
        assert "No hay tasa BCV" in res["resultado"]

    def test_tasa_bcv_con_tasa(self, user_a, empresa_a, moneda_usd):
        from apps.finanzas.models import Moneda, TasaCambio

        ves = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat"
        )
        TasaCambio.objects.create(
            id_moneda_origen=moneda_usd, id_moneda_destino=ves,
            tipo_tasa="OFICIAL_BCV", valor_tasa=Decimal("40.00000000"),
            fecha_tasa=date.today(),
        )
        res = chatmod._tool_tasa_bcv_hoy(self._ctx(user_a, empresa_a))
        assert res["fecha"] == str(date.today())
        assert Decimal(res["valor_ves_por_usd"]) == Decimal("40")

    def test_aging_cartera_vacia(self, user_a, empresa_a):
        res = chatmod._tool_aging_cartera(self._ctx(user_a, empresa_a))
        assert res["total_partidas"] == 0
        assert Decimal(res["total_pendiente"]) == Decimal("0")

    def test_saldo_cliente_sin_id(self, user_a, empresa_a):
        res = chatmod._tool_saldo_cliente(self._ctx(user_a, empresa_a))
        assert "error" in res

    def test_saldo_cliente_sin_deuda(self, user_a, empresa_a):
        res = chatmod._tool_saldo_cliente(
            self._ctx(user_a, empresa_a), cliente_id="00000000-0000-0000-0000-000000000000"
        )
        assert res == {"resultado": "El cliente no tiene saldo pendiente."}

    def test_saldo_cliente_con_partidas(self, user_a, empresa_a):
        from tests_api.factories import ClienteFactory
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        cliente = ClienteFactory(id_empresa=empresa_a, razon_social="Deudor C.A.")
        CuentaPorCobrar.objects.create(
            cliente=cliente, empresa=empresa_a, monto=Decimal("200.00"),
            fecha_emision=date.today() - timedelta(days=20),
            fecha_vencimiento=date.today() - timedelta(days=5),
            estado="pendiente",
        )
        res = chatmod._tool_saldo_cliente(
            self._ctx(user_a, empresa_a), cliente_id=str(cliente.id_cliente)
        )
        assert res["total_pendiente"] == "200.00"
        assert res["dias_max_vencido"] == 5
        assert res["facturas_pendientes"] == 1

    def test_buscar_cliente_sin_termino(self, user_a, empresa_a):
        res = chatmod._tool_buscar_cliente(self._ctx(user_a, empresa_a))
        assert "error" in res

    def test_dispatch_desconocida(self, user_a, empresa_a):
        res = chatmod._dispatch_tool("hackear", {}, self._ctx(user_a, empresa_a))
        assert res == {"error": "Herramienta desconocida: hackear"}

    def test_dispatch_captura_excepciones(self, user_a, empresa_a):
        with patch.dict(
            chatmod._TOOL_DISPATCH,
            {"tasa_bcv_hoy": MagicMock(side_effect=RuntimeError("interno"))},
        ):
            res = chatmod._dispatch_tool("tasa_bcv_hoy", {}, self._ctx(user_a, empresa_a))
        assert res == {"error": "No se pudo ejecutar tasa_bcv_hoy."}


def _leer_sse(resp) -> str:
    return b"".join(resp.streaming_content).decode("utf-8")


class TestChatView:
    URL = "/api/agentes/chat/"

    def test_sin_mensajes_400(self, client_a):
        resp = client_a.post(self.URL, {"messages": []}, format="json")
        assert resp.status_code == 400

    def test_sin_api_key_devuelve_aviso_sse(self, client_a, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        resp = client_a.post(
            self.URL, {"messages": [{"role": "user", "content": "hola"}]}, format="json"
        )
        assert resp.status_code == 200
        assert resp["Content-Type"] == "text/event-stream"
        cuerpo = _leer_sse(resp)
        assert "no está configurado" in cuerpo
        assert "data: [DONE]" in cuerpo

    def test_stream_con_tool_use_mockeado(self, client_a, empresa_a, monkeypatch):
        """Cubre el loop de tool-calling: ronda 1 usa una tool, ronda 2 termina.

        El SDK se inyecta por el punto de monkeypatch del gateway
        (``llm_gateway.anthropic``): la vista ya no instancia anthropic directo.
        """
        from apps.core import llm_gateway

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-falso")

        bloque_tool = SimpleNamespace(
            type="tool_use", name="listar_empresas", input={}, id="toolu_1"
        )
        final_1 = SimpleNamespace(stop_reason="tool_use", content=[bloque_tool])
        final_2 = SimpleNamespace(stop_reason="end_turn", content=[])

        def _stream_cm(final, textos):
            stream = MagicMock()
            stream.text_stream = iter(textos)
            stream.get_final_message.return_value = final
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=stream)
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        cliente_falso = MagicMock()
        cliente_falso.messages.stream.side_effect = [
            _stream_cm(final_1, ["Consultando…"]),
            _stream_cm(final_2, ["Tienes 1 empresa."]),
        ]
        anthropic_falso = MagicMock()
        anthropic_falso.Anthropic.return_value = cliente_falso
        monkeypatch.setattr(llm_gateway, "anthropic", anthropic_falso)

        resp = client_a.post(
            self.URL, {"messages": [{"role": "user", "content": "mis empresas?"}]},
            format="json",
        )
        cuerpo = _leer_sse(resp)

        assert "Consultando…" in cuerpo
        assert "Tienes 1 empresa." in cuerpo
        assert "data: [DONE]" in cuerpo
        assert cliente_falso.messages.stream.call_count == 2
        # La 2ª ronda recibió el tool_result de listar_empresas con la empresa real
        conversacion = cliente_falso.messages.stream.call_args.kwargs["messages"]
        tool_result = conversacion[-1]["content"][0]
        assert tool_result["type"] == "tool_result"
        assert str(empresa_a.id_empresa) in tool_result["content"]
