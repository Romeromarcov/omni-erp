"""
Gateway LLM agnóstico de proveedor — punto ÚNICO de entrada a modelos de
lenguaje en Omni ERP (Plan 05 · P2-1; registro de consumo: P2-3 básico).

Ningún otro módulo debe instanciar SDKs de proveedor ni hardcodear IDs de
modelo; ``tests_api/test_llm_gateway.py`` lo verifica con un test de
superficie (grep) sobre ``apps/``.

Uso típico::

    from apps.core import llm_gateway

    gw = llm_gateway.get_gateway()
    if gw.disponible():
        r = gw.generate(prompt="...", system="...", max_tokens=256,
                        uso=llm_gateway.USO_AGENTE, empresa=empresa)
        # r.text, r.model, r.input_tokens, r.output_tokens

    with gw.stream(messages=[...], system="...", tools=TOOLS,
                   uso=llm_gateway.USO_CHAT, empresa=empresa) as s:
        for trozo in s.text_stream:
            ...
        final = s.get_final_message()

Configuración por variables de entorno (sin secretos en código: la API key
del proveedor sigue viniendo del entorno, p. ej. ``ANTHROPIC_API_KEY``):

    LLM_PROVIDER         Proveedor LLM ("anthropic", único soportado hoy).
    LLM_MODEL            Modelo principal del uso "agente"
                         (default: claude-haiku-4-5-20251001).
    LLM_MODEL_CHAT       Modelo del uso "chat" (default: claude-sonnet-4-6).
    LLM_MODEL_ANALISIS   Modelo del uso "analisis" (default: claude-opus-4-5).
    LLM_MODEL_FALLBACK   Modelo alterno de la cascada (default: claude-sonnet-4-6).
    LLM_TIMEOUT          Timeout por request, en segundos (default: 60).
    LLM_MAX_RETRIES      Reintentos con backoff exponencial del SDK (default: 2).
    LLM_CB_UMBRAL        Fallos consecutivos que abren el circuito (default: 5).
    LLM_CB_VENTANA       Segundos que el circuito permanece abierto (default: 60).

Los defaults de modelo son los IDs que ya usaba el código antes del gateway.
Si el modelo principal y el alterno coinciden (p. ej. uso "chat" con el
fallback por defecto), la cascada se reduce a un solo intento.

Resiliencia:
  - Reintentos con backoff exponencial: los hace el SDK de anthropic
    (errores de conexión, 408/409/429/5xx) según ``LLM_MAX_RETRIES``.
  - Timeout por request según ``LLM_TIMEOUT``.
  - Fallback en cascada: modelo principal → modelo alterno → ``LLMUnavailable``.
    Los call sites conservan su fallback determinista capturando la excepción.
  - Circuit breaker por proveedor: N fallos de disponibilidad consecutivos
    (conexión/timeout/429/5xx) abren el circuito durante una ventana; mientras
    está abierto, las llamadas fallan rápido con ``LLMUnavailable`` sin tocar
    la red. El estado vive en la cache de Django si responde (compartido entre
    workers) y, si no, en memoria del proceso.

Registro de consumo por tenant (P2-3 básico):
  - Cada llamada emite un log estructurado ``llm_consumo`` con proveedor, uso,
    modelo realmente usado, empresa (si el caller la pasa) y tokens in/out.
  - Punto de extensión para persistencia: asignar ``registrar_consumo_hook``
    (callable que recibe un dict con esas claves). No se persiste hoy en
    ``RegistroAuditoria`` porque sus ``choices`` de ``tipo_evento`` son
    cerradas (exigiría migración de core) y supondría una escritura por
    llamada dentro de loops y streams; P2-3 decidirá tabla dedicada o nuevo
    ``tipo_evento`` enganchándose a este hook.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("omni.llm_gateway")

# ── Proveedores y usos ────────────────────────────────────────────────────────

PROVEEDOR_ANTHROPIC = "anthropic"

#: Usos conocidos: cada uno resuelve su modelo principal desde una env distinta.
USO_AGENTE = "agente"      # agentes shadow (clasificador, cobranza, reorden…)
USO_CHAT = "chat"          # asistente conversacional (SSE)
USO_ANALISIS = "analisis"  # análisis profundos (agente CxC)

_MODELOS_DEFAULT = {
    USO_AGENTE: "claude-haiku-4-5-20251001",
    USO_CHAT: "claude-sonnet-4-6",
    USO_ANALISIS: "claude-opus-4-5",
}
_ENV_MODELO_POR_USO = {
    USO_AGENTE: "LLM_MODEL",
    USO_CHAT: "LLM_MODEL_CHAT",
    USO_ANALISIS: "LLM_MODEL_ANALISIS",
}
_MODELO_FALLBACK_DEFAULT = "claude-sonnet-4-6"

#: Punto de inyección para tests: si se asigna un módulo aquí, ``_sdk()`` lo
#: devuelve en lugar de importar el SDK real.
anthropic = None


def _sdk():
    """Devuelve el módulo ``anthropic`` o ``None`` si no está instalado.

    El import es perezoso y por llamada para respetar ``sys.modules``
    parcheado en tests (p. ej. simular "SDK no instalado").
    """
    if anthropic is not None:
        return anthropic
    try:
        import anthropic as sdk_real  # noqa: PLC0415 — perezoso a propósito
    except ImportError:
        return None
    return sdk_real


# ── Configuración por env ─────────────────────────────────────────────────────


def _int_env(nombre: str, default: int) -> int:
    try:
        return int(os.environ.get(nombre, "") or default)
    except (TypeError, ValueError):
        logger.warning("Valor inválido en %s; usando default %s", nombre, default)
        return default


def _float_env(nombre: str, default: float) -> float:
    try:
        return float(os.environ.get(nombre, "") or default)
    except (TypeError, ValueError):
        logger.warning("Valor inválido en %s; usando default %s", nombre, default)
        return default


def modelo_configurado(uso: str = USO_AGENTE) -> str:
    """Modelo principal para un uso, resuelto por env con default sensato."""
    env_var = _ENV_MODELO_POR_USO.get(uso, "LLM_MODEL")
    return os.environ.get(env_var) or _MODELOS_DEFAULT.get(uso, _MODELOS_DEFAULT[USO_AGENTE])


def modelo_fallback() -> str:
    """Modelo alterno de la cascada, resuelto por env."""
    return os.environ.get("LLM_MODEL_FALLBACK") or _MODELO_FALLBACK_DEFAULT


# ── Excepción y resultado tipados ────────────────────────────────────────────


class LLMUnavailable(Exception):
    """El proveedor LLM no está disponible (cascada agotada o circuito abierto).

    Los call sites la capturan para activar su fallback determinista.
    ``causa`` conserva la excepción original (la última de la cascada).
    """

    def __init__(self, mensaje: str, *, proveedor: str = "", modelos: tuple | list = (), causa: Exception | None = None):
        super().__init__(mensaje)
        self.proveedor = proveedor
        self.modelos = list(modelos)
        self.causa = causa


def nombre_error(exc: Exception) -> str:
    """Nombre del tipo de error original (desempaqueta ``LLMUnavailable.causa``)."""
    if isinstance(exc, LLMUnavailable) and exc.causa is not None:
        return type(exc.causa).__name__
    return type(exc).__name__


@dataclass
class LLMResult:
    """Resultado unificado de una llamada al gateway."""

    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: Optional[str] = None
    latencia_ms: int = 0
    content: list = field(default_factory=list)  # bloques crudos (tool_use, etc.)


# ── Helpers defensivos (toleran mocks/MagicMock de los tests) ────────────────


def _entero(valor: Any) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _texto_de(content: Any) -> str:
    """Concatena los bloques de texto de un ``response.content``."""
    partes = []
    for bloque in content or []:
        texto = getattr(bloque, "text", None)
        if isinstance(texto, str):
            partes.append(texto)
    return "".join(partes)


def _stop_reason_de(respuesta: Any) -> Optional[str]:
    valor = getattr(respuesta, "stop_reason", None)
    return valor if isinstance(valor, str) else None


def _contenido_de(respuesta: Any) -> list:
    contenido = getattr(respuesta, "content", None)
    if contenido is None:
        return []
    try:
        return list(contenido)
    except TypeError:
        return []


def _empresa_pk(empresa: Any):
    """Acepta instancia de Empresa, pk (uuid/str) o ``None``."""
    if empresa is None:
        return None
    return getattr(empresa, "pk", empresa)


# ── Circuit breaker ──────────────────────────────────────────────────────────


class _CircuitBreaker:
    """Contador de fallos consecutivos con ventana, por clave (proveedor).

    ``compartido=True`` usa la cache de Django (estado común entre workers) con
    fallback transparente a memoria del proceso si la cache no responde.
    ``compartido=False`` (clientes inyectados / tests) aísla el estado en la
    instancia. ``reloj`` es inyectable para tests.
    """

    _ESTADO_CERO = {"fallos": 0, "abierto_hasta": 0.0}

    def __init__(self, compartido: bool = False, reloj: Callable[[], float] = time.time):
        self._compartido = compartido
        self._reloj = reloj
        self._local: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._claves: set[str] = set()

    # Los umbrales se leen del env en cada operación: barato y amigable con tests.
    @staticmethod
    def _umbral() -> int:
        return max(1, _int_env("LLM_CB_UMBRAL", 5))

    @staticmethod
    def _ventana() -> float:
        return _float_env("LLM_CB_VENTANA", 60.0)

    @staticmethod
    def _clave_cache(clave: str) -> str:
        return f"llm_gw:cb:{clave}"

    def _cache(self):
        if not self._compartido:
            return None
        try:
            from django.core.cache import cache  # noqa: PLC0415 — perezoso: no exigir settings al importar
            return cache
        except Exception:  # noqa: BLE001 — sin cache utilizable → memoria local
            return None

    def _leer(self, clave: str) -> dict:
        cache = self._cache()
        if cache is not None:
            try:
                estado = cache.get(self._clave_cache(clave))
                if isinstance(estado, dict):
                    return dict(estado)
            except Exception:  # noqa: BLE001 — cache caída no debe tumbar al caller
                logger.debug("Cache no disponible para el circuito LLM; usando memoria local")
        with self._lock:
            return dict(self._local.get(clave, self._ESTADO_CERO))

    def _guardar(self, clave: str, estado: dict) -> None:
        self._claves.add(clave)
        with self._lock:
            self._local[clave] = dict(estado)
        cache = self._cache()
        if cache is not None:
            try:
                # El estado debe sobrevivir al menos la ventana de apertura.
                cache.set(self._clave_cache(clave), dict(estado), timeout=max(int(self._ventana()) * 4, 300))
            except Exception:  # noqa: BLE001
                logger.debug("No se pudo guardar el circuito LLM en cache; queda en memoria local")

    def permite(self, clave: str) -> bool:
        estado = self._leer(clave)
        return self._reloj() >= float(estado.get("abierto_hasta") or 0.0)

    def _incrementar_fallos(self, clave: str) -> int:
        """Incrementa el contador de fallos de forma atómica entre workers.

        Con cache compartida usa ``incr`` (atómico en Redis/Memcached) sobre una
        clave-contador dedicada; el read-modify-write del dict NO es seguro
        entre procesos. Sin cache, el lock local basta (un solo proceso).
        """
        cache = self._cache()
        if cache is not None:
            clave_n = self._clave_cache(clave) + ":n"
            ttl = max(int(self._ventana()) * 4, 300)
            try:
                try:
                    return int(cache.incr(clave_n))
                except ValueError:
                    # La clave no existía: add atómico + incr cubre la carrera
                    # de dos workers inicializando a la vez.
                    cache.add(clave_n, 0, timeout=ttl)
                    return int(cache.incr(clave_n))
            except Exception:  # noqa: BLE001 — cache caída → memoria local
                logger.debug("Cache no disponible para el contador del circuito LLM")
        with self._lock:
            estado = dict(self._local.get(clave, self._ESTADO_CERO))
            estado["fallos"] = _entero(estado.get("fallos")) + 1
            self._local[clave] = estado
            self._claves.add(clave)
            return int(estado["fallos"])

    def registrar_fallo(self, clave: str) -> None:
        fallos = self._incrementar_fallos(clave)
        if fallos >= self._umbral():
            estado = self._leer(clave)
            estado["fallos"] = fallos
            estado["abierto_hasta"] = self._reloj() + self._ventana()
            logger.warning(
                "Circuito LLM ABIERTO | proveedor=%s | fallos_consecutivos=%d | reintento_en=%.0fs",
                clave, fallos, self._ventana(),
            )
            self._guardar(clave, estado)

    def registrar_exito(self, clave: str) -> None:
        cache = self._cache()
        if cache is not None:
            try:
                cache.delete(self._clave_cache(clave) + ":n")
            except Exception:  # noqa: BLE001
                pass
        estado = self._leer(clave)
        if estado.get("fallos") or estado.get("abierto_hasta"):
            self._guardar(clave, dict(self._ESTADO_CERO))

    def reset(self) -> None:
        cache = self._cache()
        if cache is not None:
            for clave in list(self._claves):
                try:
                    cache.delete(self._clave_cache(clave))
                    cache.delete(self._clave_cache(clave) + ":n")
                except Exception:  # noqa: BLE001
                    pass
        with self._lock:
            self._local.clear()
        self._claves.clear()


#: Estado compartido del circuito para clientes reales (todos los gateways sin
#: cliente inyectado comparten este breaker, y vía cache, todos los workers).
_breaker_compartido = _CircuitBreaker(compartido=True)


def resetear_circuito() -> None:
    """Limpia el estado del circuit breaker compartido (uso en tests)."""
    _breaker_compartido.reset()


# ── Hook de consumo (punto de extensión P2-3) ────────────────────────────────

#: Si se asigna un callable, recibe por cada llamada un dict:
#: {proveedor, uso, modelo, empresa_id, tokens_entrada, tokens_salida, latencia_ms}.
#: Pensado para que P2-3 persista consumo por tenant sin tocar el gateway.
registrar_consumo_hook: Optional[Callable[[dict], None]] = None


# ── Stream envuelto ──────────────────────────────────────────────────────────


class _LLMStream:
    """Envoltura mínima del stream del proveedor.

    Expone lo que usan los call sites de streaming: ``text_stream`` y
    ``get_final_message()`` (cacheado), más ``model``/``provider`` informativos.
    """

    def __init__(self, interno: Any, model: str, provider: str):
        self._interno = interno
        self.model = model
        self.provider = provider
        self._final: Any = None

    @property
    def text_stream(self):
        return self._interno.text_stream

    def get_final_message(self):
        if self._final is None:
            self._final = self._interno.get_final_message()
        return self._final

    def __iter__(self):
        return iter(self._interno)


# ── Gateway ──────────────────────────────────────────────────────────────────


class LLMGateway:
    """Cliente LLM unificado: proveedor/modelos por env, fallback en cascada,
    timeouts, reintentos del SDK y circuit breaker por proveedor.

    Args:
        proveedor:   override del proveedor (default: env ``LLM_PROVIDER``).
        client:      cliente inyectado (mocks en tests, integraciones custom).
                     Con cliente inyectado el circuito es local a la instancia.
        timeout:     override de ``LLM_TIMEOUT`` (segundos).
        max_retries: override de ``LLM_MAX_RETRIES``.
        breaker:     circuit breaker inyectable (tests).
    """

    def __init__(
        self,
        *,
        proveedor: str | None = None,
        client: Any = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        breaker: _CircuitBreaker | None = None,
    ):
        self.proveedor = (proveedor or os.environ.get("LLM_PROVIDER") or PROVEEDOR_ANTHROPIC).lower()
        self._client = client
        self.timeout = timeout if timeout is not None else _float_env("LLM_TIMEOUT", 60.0)
        self.max_retries = max_retries if max_retries is not None else _int_env("LLM_MAX_RETRIES", 2)
        if breaker is not None:
            self._breaker = breaker
        elif client is not None:
            self._breaker = _CircuitBreaker()  # aislado: no contamina el estado global
        else:
            self._breaker = _breaker_compartido

    # ── Disponibilidad y cliente ──────────────────────────────────────────────

    def disponible(self) -> bool:
        """True si el gateway puede intentar llamadas LLM (no garantiza éxito)."""
        if self._client is not None:
            return True
        if self.proveedor != PROVEEDOR_ANTHROPIC:
            return False
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False
        if _sdk() is None:
            logger.warning("anthropic SDK no instalado; usando fallback determinista")
            return False
        return True

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self.proveedor != PROVEEDOR_ANTHROPIC:
            raise LLMUnavailable(
                f"Proveedor LLM no soportado: {self.proveedor}", proveedor=self.proveedor
            )
        sdk = _sdk()
        if sdk is None:
            raise LLMUnavailable("SDK de anthropic no instalado", proveedor=self.proveedor)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LLMUnavailable("ANTHROPIC_API_KEY no configurada", proveedor=self.proveedor)
        # La API key la lee el SDK del entorno (R-CODE-8: sin secretos en código).
        return sdk.Anthropic(timeout=self.timeout, max_retries=self.max_retries)

    # ── Cascada y clasificación de errores ───────────────────────────────────

    def _cascada(self, model: str | None, uso: str) -> list[str]:
        candidatos = [model or modelo_configurado(uso), modelo_fallback()]
        vistos: set[str] = set()
        orden: list[str] = []
        for candidato in candidatos:
            if candidato and candidato not in vistos:
                vistos.add(candidato)
                orden.append(candidato)
        return orden

    def _modelos_o_abierto(self, model: str | None, uso: str) -> list[str]:
        if not self._breaker.permite(self.proveedor):
            raise LLMUnavailable(
                f"Circuito abierto para el proveedor {self.proveedor}; llamada LLM omitida",
                proveedor=self.proveedor,
            )
        return self._cascada(model, uso)

    def _es_error_disponibilidad(self, exc: Exception) -> bool:
        """Errores que cuentan para el circuito: conexión/timeout/429/5xx.

        Los 4xx de petición (request inválido, auth, modelo inexistente) activan
        la cascada pero no abren el circuito.
        """
        sdk = _sdk()
        try:
            if sdk is not None and isinstance(exc, sdk.APIStatusError):
                return exc.status_code == 429 or exc.status_code >= 500
            if sdk is not None and isinstance(exc, sdk.APIConnectionError):
                return True  # incluye APITimeoutError
            if sdk is not None and isinstance(exc, sdk.APIError):
                return False
        except TypeError:
            # SDK falso (MagicMock) en tests: isinstance no aplica.
            pass
        return True  # excepciones genéricas de red/transporte cuentan

    def _anotar_fallo(self, modelo: str, exc: Exception) -> None:
        if self._es_error_disponibilidad(exc):
            self._breaker.registrar_fallo(self.proveedor)
        # Solo el tipo del error: el mensaje puede arrastrar payload (R-CODE-8).
        logger.warning(
            "llm_fallo | proveedor=%s | modelo=%s | error=%s",
            self.proveedor, modelo, type(exc).__name__,
        )

    # ── API pública ───────────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str | None = None,
        *,
        messages: list | None = None,
        system: str | None = None,
        max_tokens: int = 1024,
        tools: list | None = None,
        model: str | None = None,
        uso: str = USO_AGENTE,
        empresa: Any = None,
    ) -> LLMResult:
        """Llamada no-streaming. Exactamente uno de ``prompt`` o ``messages``.

        Recorre la cascada principal → alterno; si todos fallan lanza
        ``LLMUnavailable`` (los call sites conservan su fallback determinista).
        """
        if (prompt is None) == (messages is None):
            raise ValueError("generate() requiere exactamente uno de `prompt` o `messages`.")
        if messages is None:
            messages = [{"role": "user", "content": prompt}]

        modelos = self._modelos_o_abierto(model, uso)
        client = self._get_client()
        kwargs_base: dict[str, Any] = {"max_tokens": max_tokens, "messages": messages}
        if system is not None:
            kwargs_base["system"] = system
        if tools:
            kwargs_base["tools"] = tools

        ultima_exc: Exception | None = None
        for indice, modelo in enumerate(modelos):
            t0 = time.perf_counter()
            try:
                respuesta = client.messages.create(model=modelo, **kwargs_base)
            except Exception as exc:  # noqa: BLE001 — clasificado en _anotar_fallo
                ultima_exc = exc
                self._anotar_fallo(modelo, exc)
                continue

            self._breaker.registrar_exito(self.proveedor)
            usage = getattr(respuesta, "usage", None)
            resultado = LLMResult(
                text=_texto_de(getattr(respuesta, "content", None)),
                model=modelo,
                provider=self.proveedor,
                input_tokens=_entero(getattr(usage, "input_tokens", 0)),
                output_tokens=_entero(getattr(usage, "output_tokens", 0)),
                stop_reason=_stop_reason_de(respuesta),
                latencia_ms=int((time.perf_counter() - t0) * 1000),
                content=_contenido_de(respuesta),
            )
            if indice > 0:
                logger.warning(
                    "llm_fallback_ok | proveedor=%s | modelo_alterno=%s", self.proveedor, modelo
                )
            self._registrar_consumo(resultado, empresa=empresa, uso=uso)
            return resultado

        raise LLMUnavailable(
            f"Proveedor LLM no disponible ({self.proveedor}); "
            f"modelos intentados: {', '.join(modelos)}",
            proveedor=self.proveedor,
            modelos=modelos,
            causa=ultima_exc,
        ) from ultima_exc

    @contextmanager
    def stream(
        self,
        *,
        messages: list,
        system: str | None = None,
        max_tokens: int = 1024,
        tools: list | None = None,
        model: str | None = None,
        uso: str = USO_CHAT,
        empresa: Any = None,
    ):
        """Llamada streaming (context manager). Preserva el streaming de los
        call sites: el objeto cedido expone ``text_stream`` y
        ``get_final_message()``.

        El fallback en cascada aplica al ABRIR el stream (conexión/4xx/5xx
        antes del primer token). Una vez abierto y emitiendo, un corte a mitad
        de stream se propaga tal cual: el texto ya enviado al cliente no puede
        deshacerse, así que reintentar aquí duplicaría salida.
        """
        modelos = self._modelos_o_abierto(model, uso)
        client = self._get_client()
        kwargs_base: dict[str, Any] = {"max_tokens": max_tokens, "messages": messages}
        if system is not None:
            kwargs_base["system"] = system
        if tools:
            kwargs_base["tools"] = tools

        ultima_exc: Exception | None = None
        for indice, modelo in enumerate(modelos):
            t0 = time.perf_counter()
            manager = None
            try:
                manager = client.messages.stream(model=modelo, **kwargs_base)
                interno = manager.__enter__()
            except Exception as exc:  # noqa: BLE001 — clasificado en _anotar_fallo
                ultima_exc = exc
                self._anotar_fallo(modelo, exc)
                continue

            envuelto = _LLMStream(interno, model=modelo, provider=self.proveedor)
            if indice > 0:
                logger.warning(
                    "llm_fallback_ok | proveedor=%s | modelo_alterno=%s", self.proveedor, modelo
                )
            try:
                yield envuelto
            except BaseException:
                manager.__exit__(*sys.exc_info())
                raise
            # Cuerpo completado sin excepción: registrar consumo ANTES de cerrar.
            resultado = self._resultado_de_stream(envuelto, modelo, t0)
            manager.__exit__(None, None, None)
            self._breaker.registrar_exito(self.proveedor)
            self._registrar_consumo(resultado, empresa=empresa, uso=uso)
            return

        raise LLMUnavailable(
            f"Proveedor LLM no disponible ({self.proveedor}); "
            f"modelos intentados: {', '.join(modelos)}",
            proveedor=self.proveedor,
            modelos=modelos,
            causa=ultima_exc,
        ) from ultima_exc

    # ── Consumo ───────────────────────────────────────────────────────────────

    def _resultado_de_stream(self, envuelto: _LLMStream, modelo: str, t0: float) -> LLMResult:
        final = None
        try:
            final = envuelto.get_final_message()
        except Exception:  # noqa: BLE001 — el registro de consumo nunca rompe al caller
            logger.debug("Stream sin mensaje final accesible; consumo sin tokens")
        usage = getattr(final, "usage", None)
        return LLMResult(
            text="",  # el texto ya fue emitido por el stream
            model=modelo,
            provider=self.proveedor,
            input_tokens=_entero(getattr(usage, "input_tokens", 0)),
            output_tokens=_entero(getattr(usage, "output_tokens", 0)),
            stop_reason=_stop_reason_de(final),
            latencia_ms=int((time.perf_counter() - t0) * 1000),
        )

    def _registrar_consumo(self, resultado: LLMResult, *, empresa: Any, uso: str) -> None:
        empresa_pk = _empresa_pk(empresa)
        logger.info(
            "llm_consumo | proveedor=%s | uso=%s | modelo=%s | empresa=%s | "
            "tokens_in=%d | tokens_out=%d | ms=%d",
            resultado.provider,
            uso,
            resultado.model,
            empresa_pk if empresa_pk is not None else "-",
            resultado.input_tokens,
            resultado.output_tokens,
            resultado.latencia_ms,
        )
        hook = registrar_consumo_hook
        if hook is None:
            return
        try:
            hook(
                {
                    "proveedor": resultado.provider,
                    "uso": uso,
                    "modelo": resultado.model,
                    "empresa_id": str(empresa_pk) if empresa_pk is not None else None,
                    "tokens_entrada": resultado.input_tokens,
                    "tokens_salida": resultado.output_tokens,
                    "latencia_ms": resultado.latencia_ms,
                }
            )
        except Exception:  # noqa: BLE001 — el hook jamás tumba la llamada LLM
            logger.exception("registrar_consumo_hook falló; el consumo quedó solo en logs")


def get_gateway(client: Any = None, **kwargs: Any) -> LLMGateway:
    """Crea un gateway (instancia nueva: el estado compartido vive en el breaker)."""
    return LLMGateway(client=client, **kwargs)
