"""
Tests del gateway LLM (apps/core/llm_gateway.py) — Plan 05 · P2-1.

Todo sin red: el SDK de anthropic se usa solo para construir excepciones
tipadas reales; los clientes son mocks. Cubre:

  - Fallback en cascada: principal falla → alterno responde → LLMUnavailable.
  - Circuit breaker por proveedor: abre tras N fallos consecutivos, falla
    rápido mientras está abierto y se recupera pasada la ventana.
  - Timeouts/reintentos configurados por env al construir el cliente.
  - Streaming: fallback al abrir, passthrough de text_stream/get_final_message,
    propagación de errores del cuerpo.
  - Registro de consumo por tenant (log estructurado + hook P2-3).
  - Superficie: ningún SDK instanciado ni modelo hardcodeado fuera del gateway.
"""

import logging
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic as sdk_anthropic
import httpx
import pytest

from apps.core import llm_gateway
from apps.core.llm_gateway import (

pytestmark = pytest.mark.unit
    LLMGateway,
    LLMResult,
    LLMUnavailable,
    PROVEEDOR_ANTHROPIC,
    USO_AGENTE,
    USO_ANALISIS,
    USO_CHAT,
)

_ENVS_GATEWAY = (
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_MODEL_CHAT",
    "LLM_MODEL_ANALISIS",
    "LLM_MODEL_FALLBACK",
    "LLM_TIMEOUT",
    "LLM_MAX_RETRIES",
    "LLM_CB_UMBRAL",
    "LLM_CB_VENTANA",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    """Aísla env y estado del circuito compartido en cada test del módulo."""
    for var in _ENVS_GATEWAY:
        monkeypatch.delenv(var, raising=False)
    llm_gateway.resetear_circuito()
    yield
    llm_gateway.resetear_circuito()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _respuesta_ok(texto="hola", tokens_in=11, tokens_out=7, stop="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(text=texto)],
        usage=SimpleNamespace(input_tokens=tokens_in, output_tokens=tokens_out),
        stop_reason=stop,
    )


def _exc_conexion():
    return sdk_anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.invalid/v1/messages")
    )


def _exc_status(codigo):
    peticion = httpx.Request("POST", "https://api.invalid/v1/messages")
    respuesta = httpx.Response(codigo, request=peticion)
    return sdk_anthropic.APIStatusError(f"http {codigo}", response=respuesta, body=None)


class _StreamFalso:
    def __init__(self, textos, final=None):
        self.text_stream = iter(textos)
        self._final = final

    def get_final_message(self):
        return self._final


class _ManagerFalso:
    """Context manager estilo client.messages.stream(...)."""

    def __init__(self, stream=None, error_apertura=None):
        self._stream = stream
        self._error = error_apertura
        self.salidas = []

    def __enter__(self):
        if self._error is not None:
            raise self._error
        return self._stream

    def __exit__(self, *exc_info):
        self.salidas.append(exc_info)
        return False


def _gateway_aislado(client, **kwargs):
    """Gateway con breaker propio (sin tocar el estado compartido)."""
    kwargs.setdefault("breaker", llm_gateway._CircuitBreaker())
    return LLMGateway(client=client, **kwargs)


# ── Resolución de configuración ───────────────────────────────────────────────


class TestConfiguracionModelos:
    def test_defaults_por_uso_son_los_ids_historicos(self):
        assert llm_gateway.modelo_configurado(USO_AGENTE) == "claude-haiku-4-5-20251001"
        assert llm_gateway.modelo_configurado(USO_CHAT) == "claude-sonnet-4-6"
        assert llm_gateway.modelo_configurado(USO_ANALISIS) == "claude-opus-4-5"
        assert llm_gateway.modelo_fallback() == "claude-sonnet-4-6"

    def test_env_sobreescribe_cada_uso(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "modelo-agente-x")
        monkeypatch.setenv("LLM_MODEL_CHAT", "modelo-chat-x")
        monkeypatch.setenv("LLM_MODEL_ANALISIS", "modelo-analisis-x")
        monkeypatch.setenv("LLM_MODEL_FALLBACK", "modelo-alterno-x")
        assert llm_gateway.modelo_configurado(USO_AGENTE) == "modelo-agente-x"
        assert llm_gateway.modelo_configurado(USO_CHAT) == "modelo-chat-x"
        assert llm_gateway.modelo_configurado(USO_ANALISIS) == "modelo-analisis-x"
        assert llm_gateway.modelo_fallback() == "modelo-alterno-x"

    def test_uso_desconocido_cae_al_default_de_agente(self):
        assert llm_gateway.modelo_configurado("otro") == "claude-haiku-4-5-20251001"

    def test_cascada_deduplica_principal_igual_a_alterno(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "mismo-modelo")
        monkeypatch.setenv("LLM_MODEL_FALLBACK", "mismo-modelo")
        gw = _gateway_aislado(MagicMock())
        assert gw._cascada(None, USO_AGENTE) == ["mismo-modelo"]

    def test_env_numerico_invalido_usa_default(self, monkeypatch):
        monkeypatch.setenv("LLM_TIMEOUT", "no-es-numero")
        monkeypatch.setenv("LLM_MAX_RETRIES", "tampoco")
        gw = _gateway_aislado(MagicMock())
        assert gw.timeout == 60.0
        assert gw.max_retries == 2


# ── Disponibilidad y cliente ──────────────────────────────────────────────────


class TestDisponibilidad:
    def test_sin_api_key_no_disponible(self):
        gw = LLMGateway(breaker=llm_gateway._CircuitBreaker())
        assert gw.disponible() is False

    def test_con_api_key_y_sdk_disponible(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-falso")
        gw = LLMGateway(breaker=llm_gateway._CircuitBreaker())
        assert gw.disponible() is True

    def test_cliente_inyectado_siempre_disponible(self):
        assert _gateway_aislado(MagicMock()).disponible() is True

    def test_proveedor_no_soportado(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-falso")
        gw = LLMGateway(breaker=llm_gateway._CircuitBreaker())
        assert gw.disponible() is False
        with pytest.raises(LLMUnavailable, match="no soportado"):
            gw.generate(prompt="hola")

    def test_sin_api_key_generate_lanza_llm_unavailable(self):
        gw = LLMGateway(breaker=llm_gateway._CircuitBreaker())
        with pytest.raises(LLMUnavailable, match="ANTHROPIC_API_KEY"):
            gw.generate(prompt="hola")

    def test_cliente_anthropic_con_timeout_y_retries_de_env(self, monkeypatch):
        """LLM_TIMEOUT / LLM_MAX_RETRIES llegan al constructor del SDK."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-falso")
        monkeypatch.setenv("LLM_TIMEOUT", "7.5")
        monkeypatch.setenv("LLM_MAX_RETRIES", "4")
        modulo_falso = MagicMock()
        cliente = MagicMock()
        cliente.messages.create.return_value = _respuesta_ok()
        modulo_falso.Anthropic.return_value = cliente
        monkeypatch.setattr(llm_gateway, "anthropic", modulo_falso)

        gw = LLMGateway(breaker=llm_gateway._CircuitBreaker())
        resultado = gw.generate(prompt="hola")

        assert modulo_falso.Anthropic.call_args.kwargs == {"timeout": 7.5, "max_retries": 4}
        assert resultado.text == "hola"


# ── generate(): contrato y fallback en cascada ────────────────────────────────


class TestGenerate:
    def test_exige_exactamente_prompt_o_messages(self):
        gw = _gateway_aislado(MagicMock())
        with pytest.raises(ValueError):
            gw.generate()
        with pytest.raises(ValueError):
            gw.generate(prompt="a", messages=[{"role": "user", "content": "b"}])

    def test_respuesta_ok_construye_llmresult(self):
        cliente = MagicMock()
        cliente.messages.create.return_value = _respuesta_ok("texto", 21, 9)
        gw = _gateway_aislado(cliente)

        r = gw.generate(
            prompt="hola",
            system="eres un test",
            max_tokens=99,
            tools=[{"name": "t"}],
        )

        assert isinstance(r, LLMResult)
        assert (r.text, r.input_tokens, r.output_tokens) == ("texto", 21, 9)
        assert r.model == llm_gateway.modelo_configurado(USO_AGENTE)
        assert r.provider == PROVEEDOR_ANTHROPIC
        assert r.stop_reason == "end_turn"
        kwargs = cliente.messages.create.call_args.kwargs
        assert kwargs["system"] == "eres un test"
        assert kwargs["max_tokens"] == 99
        assert kwargs["tools"] == [{"name": "t"}]
        assert kwargs["messages"] == [{"role": "user", "content": "hola"}]

    def test_fallback_al_alterno_cuando_el_principal_falla(self, monkeypatch):
        """Cascada: principal lanza error de disponibilidad → responde el alterno."""
        monkeypatch.setenv("LLM_MODEL", "modelo-principal")
        monkeypatch.setenv("LLM_MODEL_FALLBACK", "modelo-alterno")
        cliente = MagicMock()
        cliente.messages.create.side_effect = [_exc_conexion(), _respuesta_ok("plan b")]
        gw = _gateway_aislado(cliente)

        r = gw.generate(prompt="hola")

        assert r.text == "plan b"
        assert r.model == "modelo-alterno"
        modelos_llamados = [c.kwargs["model"] for c in cliente.messages.create.call_args_list]
        assert modelos_llamados == ["modelo-principal", "modelo-alterno"]

    def test_cascada_agotada_lanza_llm_unavailable_tipada(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "modelo-principal")
        monkeypatch.setenv("LLM_MODEL_FALLBACK", "modelo-alterno")
        cliente = MagicMock()
        cliente.messages.create.side_effect = TimeoutError("sin red")
        gw = _gateway_aislado(cliente)

        with pytest.raises(LLMUnavailable) as excinfo:
            gw.generate(prompt="hola")

        exc = excinfo.value
        assert exc.proveedor == PROVEEDOR_ANTHROPIC
        assert exc.modelos == ["modelo-principal", "modelo-alterno"]
        assert isinstance(exc.causa, TimeoutError)
        # nombre_error desempaqueta la causa original (paridad con los agentes).
        assert llm_gateway.nombre_error(exc) == "TimeoutError"
        assert llm_gateway.nombre_error(ValueError("x")) == "ValueError"

    def test_error_4xx_activa_cascada_pero_no_abre_circuito(self, monkeypatch):
        monkeypatch.setenv("LLM_CB_UMBRAL", "1")  # cualquier fallo contable abriría
        breaker = llm_gateway._CircuitBreaker()
        cliente = MagicMock()
        cliente.messages.create.side_effect = [_exc_status(404), _respuesta_ok("alterno")]
        gw = LLMGateway(client=cliente, breaker=breaker)

        r = gw.generate(prompt="hola")

        assert r.text == "alterno"
        assert breaker.permite(PROVEEDOR_ANTHROPIC)  # el 404 no contó

    @pytest.mark.parametrize("codigo", [429, 500, 529])
    def test_429_y_5xx_cuentan_para_el_circuito(self, monkeypatch, codigo):
        monkeypatch.setenv("LLM_CB_UMBRAL", "1")
        breaker = llm_gateway._CircuitBreaker()
        cliente = MagicMock()
        cliente.messages.create.side_effect = [_exc_status(codigo), _respuesta_ok()]
        gw = LLMGateway(client=cliente, breaker=breaker)

        gw.generate(prompt="hola")  # el alterno responde

        # El fallo contable abrió el circuito (umbral=1)… y el éxito posterior lo resetea.
        assert breaker.permite(PROVEEDOR_ANTHROPIC)
        estado = breaker._leer(PROVEEDOR_ANTHROPIC)
        assert estado["fallos"] == 0


# ── Circuit breaker ───────────────────────────────────────────────────────────


class TestCircuitBreaker:
    def test_abre_tras_n_fallos_y_falla_rapido(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "m1")
        monkeypatch.setenv("LLM_MODEL_FALLBACK", "m2")
        monkeypatch.setenv("LLM_CB_UMBRAL", "3")
        monkeypatch.setenv("LLM_CB_VENTANA", "60")
        reloj = {"t": 1000.0}
        breaker = llm_gateway._CircuitBreaker(reloj=lambda: reloj["t"])
        cliente = MagicMock()
        cliente.messages.create.side_effect = _exc_conexion
        gw = LLMGateway(client=cliente, breaker=breaker)

        with pytest.raises(LLMUnavailable):
            gw.generate(prompt="x")  # 2 fallos (principal + alterno)
        with pytest.raises(LLMUnavailable):
            gw.generate(prompt="x")  # 4 fallos → abierto en el 3º
        assert cliente.messages.create.call_count == 4

        # Circuito abierto: falla rápido SIN tocar al proveedor.
        with pytest.raises(LLMUnavailable, match="Circuito abierto"):
            gw.generate(prompt="x")
        assert cliente.messages.create.call_count == 4

    def test_se_recupera_tras_la_ventana_y_el_exito_resetea(self, monkeypatch):
        monkeypatch.setenv("LLM_CB_UMBRAL", "2")
        monkeypatch.setenv("LLM_CB_VENTANA", "60")
        reloj = {"t": 1000.0}
        breaker = llm_gateway._CircuitBreaker(reloj=lambda: reloj["t"])
        cliente = MagicMock()
        cliente.messages.create.side_effect = _exc_conexion
        gw = LLMGateway(client=cliente, breaker=breaker)

        with pytest.raises(LLMUnavailable):
            gw.generate(prompt="x")  # 2 fallos → circuito abierto hasta t+60
        with pytest.raises(LLMUnavailable, match="Circuito abierto"):
            gw.generate(prompt="x")

        # Pasada la ventana, el circuito se semiabre y deja intentar de nuevo.
        reloj["t"] += 61
        cliente.messages.create.side_effect = None
        cliente.messages.create.return_value = _respuesta_ok("de vuelta")
        r = gw.generate(prompt="x")

        assert r.text == "de vuelta"
        assert breaker._leer(PROVEEDOR_ANTHROPIC)["fallos"] == 0  # éxito resetea

    def test_estado_compartido_via_cache_django(self, monkeypatch):
        """Dos breakers `compartido=True` ven el mismo estado (cache de Django)."""
        monkeypatch.setenv("LLM_CB_UMBRAL", "1")
        b1 = llm_gateway._CircuitBreaker(compartido=True)
        b2 = llm_gateway._CircuitBreaker(compartido=True)
        try:
            b1.registrar_fallo("proveedor-prueba-cache")
            assert b2.permite("proveedor-prueba-cache") is False
        finally:
            b1.reset()
        assert b2.permite("proveedor-prueba-cache") is True

    def test_resetear_circuito_limpia_el_estado_compartido(self, monkeypatch):
        monkeypatch.setenv("LLM_CB_UMBRAL", "1")
        gw = LLMGateway()  # sin cliente → usa el breaker compartido del módulo
        gw._breaker.registrar_fallo(PROVEEDOR_ANTHROPIC)
        assert gw._breaker.permite(PROVEEDOR_ANTHROPIC) is False
        llm_gateway.resetear_circuito()
        assert gw._breaker.permite(PROVEEDOR_ANTHROPIC) is True


# ── stream() ──────────────────────────────────────────────────────────────────


class TestStream:
    def test_passthrough_de_text_stream_y_final_message(self):
        final = _respuesta_ok("", 30, 12)
        manager = _ManagerFalso(stream=_StreamFalso(["ho", "la"], final=final))
        cliente = MagicMock()
        cliente.messages.stream.return_value = manager
        gw = _gateway_aislado(cliente)

        with gw.stream(messages=[{"role": "user", "content": "hola"}], uso=USO_CHAT) as s:
            assert list(s.text_stream) == ["ho", "la"]
            assert s.get_final_message() is final

        assert manager.salidas == [(None, None, None)]
        kwargs = cliente.messages.stream.call_args.kwargs
        assert kwargs["model"] == llm_gateway.modelo_configurado(USO_CHAT)

    def test_fallback_al_alterno_si_el_principal_no_abre(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL_CHAT", "chat-principal")
        monkeypatch.setenv("LLM_MODEL_FALLBACK", "chat-alterno")
        manager_roto = _ManagerFalso(error_apertura=_exc_conexion())
        manager_ok = _ManagerFalso(stream=_StreamFalso(["plan b"]))
        cliente = MagicMock()
        cliente.messages.stream.side_effect = [manager_roto, manager_ok]
        gw = _gateway_aislado(cliente)

        with gw.stream(messages=[{"role": "user", "content": "hola"}], uso=USO_CHAT) as s:
            assert s.model == "chat-alterno"
            assert "".join(s.text_stream) == "plan b"

        modelos = [c.kwargs["model"] for c in cliente.messages.stream.call_args_list]
        assert modelos == ["chat-principal", "chat-alterno"]

    def test_cascada_agotada_en_apertura_lanza_llm_unavailable(self):
        cliente = MagicMock()
        cliente.messages.stream.side_effect = lambda **_: _ManagerFalso(
            error_apertura=_exc_conexion()
        )
        gw = _gateway_aislado(cliente)

        with pytest.raises(LLMUnavailable):
            with gw.stream(messages=[{"role": "user", "content": "hola"}]):
                pytest.fail("no debe entrar al cuerpo")  # pragma: no cover

    def test_excepcion_del_cuerpo_se_propaga_y_cierra_el_stream(self):
        manager = _ManagerFalso(stream=_StreamFalso(["x"]))
        cliente = MagicMock()
        cliente.messages.stream.return_value = manager
        gw = _gateway_aislado(cliente)

        with pytest.raises(RuntimeError, match="se cayó el consumidor"):
            with gw.stream(messages=[{"role": "user", "content": "hola"}]):
                raise RuntimeError("se cayó el consumidor")

        assert len(manager.salidas) == 1
        assert manager.salidas[0][0] is RuntimeError  # __exit__ recibió el exc_info

    def test_registra_consumo_con_tokens_del_final_message(self, caplog):
        final = _respuesta_ok("", tokens_in=40, tokens_out=15)
        manager = _ManagerFalso(stream=_StreamFalso(["a"], final=final))
        cliente = MagicMock()
        cliente.messages.stream.return_value = manager
        gw = _gateway_aislado(cliente)
        empresa = SimpleNamespace(pk="emp-stream-1")

        with caplog.at_level(logging.INFO, logger="omni.llm_gateway"):
            with gw.stream(
                messages=[{"role": "user", "content": "hola"}], empresa=empresa
            ) as s:
                list(s.text_stream)

        consumo = [m for m in caplog.messages if "llm_consumo" in m]
        assert len(consumo) == 1
        assert "empresa=emp-stream-1" in consumo[0]
        assert "tokens_in=40" in consumo[0]
        assert "tokens_out=15" in consumo[0]


# ── Registro de consumo (P2-3 básico) ────────────────────────────────────────


class TestConsumo:
    def test_log_estructurado_con_empresa_y_tokens(self, caplog):
        cliente = MagicMock()
        cliente.messages.create.return_value = _respuesta_ok("ok", 33, 44)
        gw = _gateway_aislado(cliente)
        empresa = SimpleNamespace(pk="emp-123")

        with caplog.at_level(logging.INFO, logger="omni.llm_gateway"):
            gw.generate(prompt="hola", uso=USO_AGENTE, empresa=empresa)

        consumo = [m for m in caplog.messages if "llm_consumo" in m]
        assert len(consumo) == 1
        assert "proveedor=anthropic" in consumo[0]
        assert "uso=agente" in consumo[0]
        assert "empresa=emp-123" in consumo[0]
        assert "tokens_in=33" in consumo[0]
        assert "tokens_out=44" in consumo[0]

    def test_sin_empresa_loguea_guion(self, caplog):
        cliente = MagicMock()
        cliente.messages.create.return_value = _respuesta_ok()
        gw = _gateway_aislado(cliente)

        with caplog.at_level(logging.INFO, logger="omni.llm_gateway"):
            gw.generate(prompt="hola")

        consumo = [m for m in caplog.messages if "llm_consumo" in m]
        assert "| empresa=- |" in consumo[0]

    def test_usage_ausente_no_rompe(self):
        """Respuestas sin usage (p. ej. mocks de los agentes) → tokens 0."""
        cliente = MagicMock()
        cliente.messages.create.return_value = SimpleNamespace(
            content=[SimpleNamespace(text="ok")], usage=None, stop_reason=None
        )
        gw = _gateway_aislado(cliente)
        r = gw.generate(prompt="hola")
        assert (r.input_tokens, r.output_tokens) == (0, 0)
        assert r.stop_reason is None

    def test_respuesta_magicmock_pura_no_rompe(self):
        """Un cliente MagicMock sin configurar tampoco rompe el gateway."""
        cliente = MagicMock()
        gw = _gateway_aislado(cliente)
        r = gw.generate(prompt="hola")
        assert isinstance(r, LLMResult)
        assert r.text == ""  # sin bloques de texto reales
        assert r.stop_reason is None

    def test_hook_p23_recibe_el_consumo(self, monkeypatch):
        recibido = {}
        monkeypatch.setattr(llm_gateway, "registrar_consumo_hook", recibido.update)
        cliente = MagicMock()
        cliente.messages.create.return_value = _respuesta_ok("ok", 5, 3)
        gw = _gateway_aislado(cliente)
        empresa = SimpleNamespace(pk="emp-hook")

        gw.generate(prompt="hola", uso=USO_AGENTE, empresa=empresa)

        assert recibido == {
            "proveedor": "anthropic",
            "uso": "agente",
            "modelo": llm_gateway.modelo_configurado(USO_AGENTE),
            "empresa_id": "emp-hook",
            "tokens_entrada": 5,
            "tokens_salida": 3,
            "latencia_ms": recibido["latencia_ms"],
        }

    def test_hook_que_falla_no_rompe_la_llamada(self, monkeypatch, caplog):
        def hook_roto(_):
            raise RuntimeError("hook explotó")

        monkeypatch.setattr(llm_gateway, "registrar_consumo_hook", hook_roto)
        cliente = MagicMock()
        cliente.messages.create.return_value = _respuesta_ok("ok")
        gw = _gateway_aislado(cliente)

        with caplog.at_level(logging.ERROR, logger="omni.llm_gateway"):
            r = gw.generate(prompt="hola")

        assert r.text == "ok"
        assert any("registrar_consumo_hook" in m for m in caplog.messages)


# ── Bordes defensivos ────────────────────────────────────────────────────────


class TestBordesDefensivos:
    def test_helpers_toleran_valores_raros(self):
        assert llm_gateway._entero("abc") == 0
        assert llm_gateway._entero(None) == 0
        assert llm_gateway._contenido_de(SimpleNamespace()) == []
        assert llm_gateway._contenido_de(SimpleNamespace(content=5)) == []
        assert llm_gateway._texto_de(None) == ""

    def test_llmstream_es_iterable(self):
        class _Interno:
            text_stream = ()

            def __iter__(self):
                return iter([1, 2])

        envuelto = llm_gateway._LLMStream(_Interno(), model="m", provider="p")
        assert list(envuelto) == [1, 2]
        assert envuelto.model == "m"

    def test_sdk_no_instalado_degrada_y_tipifica(self, monkeypatch):
        """Sin SDK importable: disponible() False y generate() LLMUnavailable."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-falso")
        monkeypatch.setitem(sys.modules, "anthropic", None)  # import → ImportError
        gw = LLMGateway(breaker=llm_gateway._CircuitBreaker())
        assert gw.disponible() is False
        with pytest.raises(LLMUnavailable, match="SDK"):
            gw.generate(prompt="x")

    def test_clasificacion_de_errores(self, monkeypatch):
        gw = _gateway_aislado(MagicMock())
        api_err = sdk_anthropic.APIError(
            "x", httpx.Request("POST", "https://api.invalid/v1/messages"), body=None
        )
        assert gw._es_error_disponibilidad(api_err) is False  # APIError genérico: no cuenta
        assert gw._es_error_disponibilidad(_exc_conexion()) is True
        assert gw._es_error_disponibilidad(_exc_status(400)) is False
        # SDK falso (MagicMock): isinstance lanza TypeError → cuenta por defecto.
        monkeypatch.setattr(llm_gateway, "anthropic", MagicMock())
        assert gw._es_error_disponibilidad(ValueError("x")) is True

    def test_breaker_sin_django_cache_usa_memoria(self, monkeypatch):
        monkeypatch.setenv("LLM_CB_UMBRAL", "1")
        monkeypatch.setitem(sys.modules, "django.core.cache", None)
        b = llm_gateway._CircuitBreaker(compartido=True)
        b.registrar_fallo("prov-mem")
        assert b.permite("prov-mem") is False
        b.reset()
        assert b.permite("prov-mem") is True

    def test_breaker_con_cache_rota_cae_a_memoria(self, monkeypatch):
        class _CacheRota:
            def get(self, *a, **k):
                raise RuntimeError("cache caída")

            def set(self, *a, **k):
                raise RuntimeError("cache caída")

            def delete(self, *a, **k):
                raise RuntimeError("cache caída")

        monkeypatch.setenv("LLM_CB_UMBRAL", "1")
        monkeypatch.setattr(
            llm_gateway._CircuitBreaker, "_cache", lambda self: _CacheRota()
        )
        b = llm_gateway._CircuitBreaker(compartido=True)
        b.registrar_fallo("prov-roto")
        assert b.permite("prov-roto") is False
        b.reset()
        assert b.permite("prov-roto") is True

    def test_stream_final_message_que_falla_no_rompe_el_consumo(self, caplog):
        class _StreamSinFinal:
            def __init__(self):
                self.text_stream = iter(("a",))

            def get_final_message(self):
                raise RuntimeError("stream cerrado")

        manager = _ManagerFalso(stream=_StreamSinFinal())
        cliente = MagicMock()
        cliente.messages.stream.return_value = manager
        gw = _gateway_aislado(cliente)

        with caplog.at_level(logging.INFO, logger="omni.llm_gateway"):
            with gw.stream(
                messages=[{"role": "user", "content": "x"}],
                system="sistema",
                tools=[{"name": "t"}],
            ) as s:
                list(s.text_stream)

        kwargs = cliente.messages.stream.call_args.kwargs
        assert kwargs["system"] == "sistema"
        assert kwargs["tools"] == [{"name": "t"}]
        consumo = [m for m in caplog.messages if "llm_consumo" in m]
        assert len(consumo) == 1
        assert "tokens_in=0" in consumo[0]


# ── Superficie: el gateway es el ÚNICO punto de entrada (DoD P2-1) ───────────

_RAIZ_APPS = Path(llm_gateway.__file__).resolve().parents[1]  # …/backend/apps
_RUTA_GATEWAY = Path(llm_gateway.__file__).resolve()


class TestSuperficie:
    def _archivos_apps(self):
        for ruta in sorted(_RAIZ_APPS.rglob("*.py")):
            if ruta != _RUTA_GATEWAY:
                yield ruta

    def test_sdk_no_instanciado_fuera_del_gateway(self):
        patron = re.compile(r"Anthropic\s*\(")
        infractores = [
            str(ruta.relative_to(_RAIZ_APPS))
            for ruta in self._archivos_apps()
            if patron.search(ruta.read_text(encoding="utf-8"))
        ]
        assert infractores == [], (
            "El SDK de anthropic solo se instancia en apps/core/llm_gateway.py; "
            f"infractores: {infractores}"
        )

    def test_modelos_no_hardcodeados_fuera_del_gateway(self):
        patron = re.compile(r"""["']claude-""")
        infractores = [
            str(ruta.relative_to(_RAIZ_APPS))
            for ruta in self._archivos_apps()
            if patron.search(ruta.read_text(encoding="utf-8"))
        ]
        assert infractores == [], (
            "Los IDs de modelo viven solo en apps/core/llm_gateway.py (por env); "
            f"infractores: {infractores}"
        )
