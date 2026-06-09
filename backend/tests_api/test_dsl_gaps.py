"""
Backfill de cobertura — apps/personalizacion/dsl.py, ramas restantes (plan "Cero Dudas").

Complementa los tests existentes (test_agentes_dsl.py, test_ctf002_dsl_runtime.py)
cubriendo las ramas que faltaban según term-missing:

- Errores de validación por primitiva (campos/entidades/estados/reglas/vistas/conectores).
- ``validar_config`` con tipos inválidos (no-dict, primitivas no-lista, claves desconocidas).
- ``aplicar_config``: config inválido (ValueError), acciones de campos y conectores.
- ``get_config_activa``: sin config, con config y rama de excepción.
- ``ejecutar_reglas``: los 5 operadores + regla mal configurada (TypeError).
- ``_validar_url_externa`` (guard SSRF) y ``_enviar_webhook`` (sin red).
- ``disparar_conectores`` con y sin mapeo de campos (threads falsos, síncronos).
- Runtime de entidades/estados/vistas personalizadas (ramas vacías/DoesNotExist).
"""
import socket
from types import SimpleNamespace
from unittest import mock

import pytest

from apps.personalizacion import dsl

pytestmark = pytest.mark.django_db


# ═════════════════════════════ Validación por primitiva ══════════════════════


class TestValidarCampos:
    def test_falta_entidad_y_campo(self):
        errores = dsl._validar_campos([{"accion": "ocultar"}])
        assert any("falta 'entidad'" in e for e in errores)
        assert any("falta 'campo'" in e for e in errores)

    def test_entidad_no_reconocida(self):
        errores = dsl._validar_campos([{"entidad": "Nave", "campo": "x", "accion": "ocultar"}])
        assert any("no reconocida" in e for e in errores)

    def test_accion_invalida(self):
        errores = dsl._validar_campos([{"entidad": "Cliente", "campo": "x", "accion": "borrar"}])
        assert any("accion 'borrar' inválida" in e for e in errores)

    def test_renombrar_sin_nuevo_nombre(self):
        errores = dsl._validar_campos([{"entidad": "Cliente", "campo": "x", "accion": "renombrar"}])
        assert errores == ["campos[0]: accion 'renombrar' requiere 'nuevo_nombre'"]

    def test_agregar_sin_tipo_y_tipo_invalido(self):
        errores = dsl._validar_campos([{"entidad": "Cliente", "campo": "x", "accion": "agregar"}])
        assert any("requiere 'tipo'" in e for e in errores)
        errores = dsl._validar_campos(
            [{"entidad": "Cliente", "campo": "x", "accion": "agregar", "tipo": "blob"}]
        )
        assert any("tipo 'blob' inválido" in e for e in errores)

    def test_select_sin_opciones(self):
        errores = dsl._validar_campos(
            [{"entidad": "Cliente", "campo": "x", "accion": "agregar", "tipo": "select"}]
        )
        assert any("requiere 'opciones'" in e for e in errores)


class TestValidarEntidades:
    def test_falta_nombre(self):
        errores = dsl._validar_entidades([{}])
        assert errores == ["entidades[0]: falta 'nombre'"]

    def test_nombre_duplicado(self):
        entidades = [
            {"nombre": "Equipo", "campos": [{"nombre": "serial", "tipo": "text"}]},
            {"nombre": "Equipo", "campos": [{"nombre": "serial", "tipo": "text"}]},
        ]
        errores = dsl._validar_entidades(entidades)
        assert any("duplicado" in e for e in errores)

    def test_sin_campos_y_campo_invalido(self):
        errores = dsl._validar_entidades([{"nombre": "Equipo"}])
        assert any("al menos un campo" in e for e in errores)
        errores = dsl._validar_entidades([{"nombre": "Equipo", "campos": [{"tipo": "raro"}]}])
        assert any("falta 'nombre'" in e for e in errores)
        assert any("tipo 'raro' inválido" in e for e in errores)


class TestValidarEstados:
    def test_modelo_no_soportado_y_faltantes(self):
        errores = dsl._validar_estados([{"modelo": "Nave"}])
        assert any("no soporta estados personalizados" in e for e in errores)
        assert any("falta 'nombre'" in e for e in errores)
        assert any("falta 'etiqueta'" in e for e in errores)

    def test_estado_valido_sin_errores(self):
        errores = dsl._validar_estados(
            [{"modelo": "Pedido", "nombre": "EN_RUTA", "etiqueta": "En ruta"}]
        )
        assert errores == []


class TestValidarReglas:
    def test_regla_incompleta(self):
        errores = dsl._validar_reglas([{}])
        assert any("falta 'entidad'" in e for e in errores)
        assert any("falta 'campo'" in e for e in errores)
        assert any("operador 'None' inválido" in e for e in errores)
        assert any("falta 'mensaje_error'" in e for e in errores)

    def test_regla_valida(self):
        errores = dsl._validar_reglas([{
            "entidad": "Pedido", "campo": "total", "operador": "mayor_que",
            "valor": 0, "mensaje_error": "El total debe ser positivo",
        }])
        assert errores == []


class TestValidarVistas:
    def test_vista_incompleta(self):
        errores = dsl._validar_vistas([{}])
        assert any("falta 'entidad'" in e for e in errores)
        assert any("'columnas' debe ser una lista no vacía" in e for e in errores)

    def test_columnas_no_lista(self):
        errores = dsl._validar_vistas([{"entidad": "Cliente", "columnas": "nombre"}])
        assert any("'columnas' debe ser una lista no vacía" in e for e in errores)


class TestValidarConectores:
    def test_conector_incompleto(self):
        errores = dsl._validar_conectores([{"metodo": "FETCH"}])
        assert any("falta 'nombre'" in e for e in errores)
        assert any("falta 'url'" in e for e in errores)
        assert any("metodo 'FETCH' inválido" in e for e in errores)
        assert any("falta 'evento_origen'" in e for e in errores)

    def test_metodo_default_post_es_valido(self):
        errores = dsl._validar_conectores([{
            "nombre": "hook", "url": "https://example.com", "evento_origen": "x.y.z",
        }])
        assert errores == []


class TestValidarConfig:
    def test_no_dict(self):
        assert dsl.validar_config("yaml-roto") == ["El config debe ser un diccionario/objeto YAML"]

    def test_config_vacio(self):
        errores = dsl.validar_config({})
        assert errores == ["El config está vacío — debe tener al menos una primitiva"]

    def test_claves_desconocidas(self):
        errores = dsl.validar_config({"magia": []})
        assert any("Claves no reconocidas" in e for e in errores)

    @pytest.mark.parametrize("primitiva", sorted(dsl.PRIMITIVAS_VALIDAS))
    def test_primitiva_no_lista(self, primitiva):
        errores = dsl.validar_config({primitiva: "no-lista"})
        assert f"'{primitiva}' debe ser una lista" in errores


# ═════════════════════════════ aplicar_config ════════════════════════════════


class TestAplicarConfig:
    def test_config_invalido_lanza_value_error(self, empresa_a):
        with pytest.raises(ValueError, match="Config inválido"):
            dsl.aplicar_config({"campos": "no-lista"}, empresa_a)

    def test_acciones_de_campos_y_conectores(self, empresa_a):
        config = {
            "campos": [
                {"entidad": "Cliente", "campo": "rif", "accion": "renombrar", "nuevo_nombre": "RIF/Cédula"},
                {"entidad": "Cliente", "campo": "email", "accion": "ocultar"},
                {"entidad": "Cliente", "campo": "telefono", "accion": "requerir"},
                {"entidad": "Producto", "campo": "color", "accion": "agregar",
                 "tipo": "select", "opciones": ["rojo", "azul"]},
            ],
            "conectores": [
                {"nombre": "crm-hook", "url": "https://hooks.example.com/x",
                 "evento_origen": "ventas.pedido.confirmado",
                 "mapeo_campos": {"total": "amount"}},
            ],
        }
        res = dsl.aplicar_config(config, empresa_a)
        assert res["version"] == 1
        assert "renombrar Cliente.rif" in res["aplicadas"]
        assert "ocultar Cliente.email" in res["aplicadas"]
        assert "requerir Cliente.telefono" in res["aplicadas"]
        assert "agregar Producto.color" in res["aplicadas"]
        assert "conector:crm-hook → ventas.pedido.confirmado" in res["aplicadas"]

        from apps.personalizacion.models import PersonalizacionConfig
        cfg = PersonalizacionConfig.objects.get(id_empresa=empresa_a, activo=True)
        metadatos = cfg.resultado_aplicacion["metadatos_campos"]
        assert metadatos["Cliente.rif"]["alias"] == "RIF/Cédula"
        assert metadatos["Cliente.email"]["oculto"] is True
        assert metadatos["Cliente.telefono"]["requerido"] is True
        assert metadatos["Producto.color"]["tipo_extra"] == "select"
        assert metadatos["Producto.color"]["opciones"] == ["rojo", "azul"]
        conectores = cfg.resultado_aplicacion["conectores_indexados"]
        assert conectores[0]["metodo"] == "POST"  # default
        assert conectores[0]["mapeo_campos"] == {"total": "amount"}

    def test_reglas_se_registran_en_resultado(self, empresa_a):
        config = {
            "reglas": [{
                "entidad": "Pedido", "campo": "total", "operador": "mayor_que",
                "valor": 0, "mensaje_error": "total > 0",
            }],
        }
        assert dsl.validar_config(config) == []  # rama 'reglas' lista válida
        res = dsl.aplicar_config(config, empresa_a)
        assert "reglas:1 reglas registradas (runtime: ejecutar_reglas())" in res["aplicadas"]

    def test_nueva_version_desactiva_anterior(self, empresa_a):
        from apps.personalizacion.models import PersonalizacionConfig
        config = {"vistas": [{"entidad": "Cliente", "columnas": ["rif"]}]}
        r1 = dsl.aplicar_config(config, empresa_a)
        r2 = dsl.aplicar_config(config, empresa_a)
        assert (r1["version"], r2["version"]) == (1, 2)
        activos = PersonalizacionConfig.objects.filter(id_empresa=empresa_a, activo=True)
        assert activos.count() == 1
        assert activos.first().version == 2


# ═════════════════════════════ get_config_activa ═════════════════════════════


class TestGetConfigActiva:
    def test_sin_config_devuelve_vacio(self, empresa_a):
        assert dsl.get_config_activa(empresa_a) == {}

    def test_devuelve_config_dict(self, empresa_a):
        config = {"vistas": [{"entidad": "Cliente", "columnas": ["rif"]}]}
        dsl.aplicar_config(config, empresa_a)
        assert dsl.get_config_activa(empresa_a) == config

    def test_excepcion_degrada_a_vacio(self):
        """Un argumento inválido no debe propagar la excepción."""
        assert dsl.get_config_activa(object()) == {}


# ═════════════════════════════ ejecutar_reglas ═══════════════════════════════


def _config_reglas(monkeypatch, reglas):
    monkeypatch.setattr(dsl, "get_config_activa", lambda empresa: {"reglas": reglas})


class TestEjecutarReglas:
    def test_sin_reglas_para_entidad(self, monkeypatch):
        _config_reglas(monkeypatch, [{"entidad": "Cliente", "campo": "x",
                                      "operador": "igual_a", "valor": 1,
                                      "mensaje_error": "err"}])
        assert dsl.ejecutar_reglas("Pedido", SimpleNamespace(), None) == []

    def test_mayor_que(self, monkeypatch):
        _config_reglas(monkeypatch, [{"entidad": "Pedido", "campo": "total",
                                      "operador": "mayor_que", "valor": 0,
                                      "mensaje_error": "total debe ser > 0"}])
        assert dsl.ejecutar_reglas("Pedido", SimpleNamespace(total=10), None) == []
        assert dsl.ejecutar_reglas("Pedido", SimpleNamespace(total=0), None) == ["total debe ser > 0"]
        assert dsl.ejecutar_reglas("Pedido", SimpleNamespace(total=None), None) == ["total debe ser > 0"]

    def test_menor_que(self, monkeypatch):
        _config_reglas(monkeypatch, [{"entidad": "Pedido", "campo": "descuento",
                                      "operador": "menor_que", "valor": 50,
                                      "mensaje_error": "descuento < 50"}])
        assert dsl.ejecutar_reglas("Pedido", SimpleNamespace(descuento=10), None) == []
        assert dsl.ejecutar_reglas("Pedido", SimpleNamespace(descuento=60), None) == ["descuento < 50"]

    def test_igual_a_y_distinto_de(self, monkeypatch):
        _config_reglas(monkeypatch, [
            {"entidad": "Pedido", "campo": "estado", "operador": "igual_a",
             "valor": "BORRADOR", "mensaje_error": "debe ser borrador"},
            {"entidad": "Pedido", "campo": "tipo", "operador": "distinto_de",
             "valor": "PROHIBIDO", "mensaje_error": "tipo prohibido"},
        ])
        ok = SimpleNamespace(estado="BORRADOR", tipo="NORMAL")
        assert dsl.ejecutar_reglas("Pedido", ok, None) == []
        mal = SimpleNamespace(estado="APROBADO", tipo="PROHIBIDO")
        assert dsl.ejecutar_reglas("Pedido", mal, None) == ["debe ser borrador", "tipo prohibido"]

    def test_requerido_si(self, monkeypatch):
        _config_reglas(monkeypatch, [{
            "entidad": "Pedido", "campo": "motivo", "operador": "requerido_si",
            "campo_condicion": "estado", "valor_condicion": "ANULADO",
            "mensaje_error": "motivo requerido al anular",
        }])
        # Condición cumplida + campo vacío → error
        assert dsl.ejecutar_reglas(
            "Pedido", SimpleNamespace(estado="ANULADO", motivo=""), None
        ) == ["motivo requerido al anular"]
        # Condición cumplida + campo lleno → ok
        assert dsl.ejecutar_reglas(
            "Pedido", SimpleNamespace(estado="ANULADO", motivo="duplicado"), None
        ) == []
        # Condición no cumplida → ok aunque esté vacío
        assert dsl.ejecutar_reglas(
            "Pedido", SimpleNamespace(estado="ACTIVO", motivo=None), None
        ) == []

    def test_requerido_si_sin_campo_condicion_no_valida(self, monkeypatch):
        _config_reglas(monkeypatch, [{
            "entidad": "Pedido", "campo": "motivo", "operador": "requerido_si",
            "mensaje_error": "no debería dispararse",
        }])
        assert dsl.ejecutar_reglas("Pedido", SimpleNamespace(motivo=None), None) == []

    def test_regla_mal_configurada_no_bloquea(self, monkeypatch):
        """TypeError en la comparación → se loguea y no se agrega error."""
        _config_reglas(monkeypatch, [{
            "entidad": "Pedido", "campo": "total", "operador": "mayor_que",
            "valor": 5, "mensaje_error": "no debería dispararse",
        }])
        assert dsl.ejecutar_reglas("Pedido", SimpleNamespace(total="texto"), None) == []


# ═════════════════════════════ Guard SSRF + webhook ══════════════════════════


def _addrinfo(ip):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


class TestValidarUrlExterna:
    def test_esquema_no_permitido(self):
        with pytest.raises(ValueError, match="Esquema de URL no permitido"):
            dsl._validar_url_externa("file:///etc/passwd")

    def test_sin_host(self):
        with pytest.raises(ValueError, match="sin host válido"):
            dsl._validar_url_externa("https://")

    def test_host_no_resoluble(self, monkeypatch):
        def _raise(*a, **k):
            raise socket.gaierror("nx")
        monkeypatch.setattr(socket, "getaddrinfo", _raise)
        with pytest.raises(ValueError, match="No se pudo resolver"):
            dsl._validar_url_externa("https://no-existe.example.invalid/hook")

    @pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "169.254.169.254"])
    def test_ips_internas_bloqueadas(self, monkeypatch, ip):
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo(ip))
        with pytest.raises(ValueError, match="IP interna"):
            dsl._validar_url_externa("https://interno.example.com/hook")

    def test_ip_publica_pasa(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34"))
        dsl._validar_url_externa("http://publico.example.com/hook")  # no lanza


class TestEnviarWebhook:
    def test_envio_exitoso(self, monkeypatch):
        monkeypatch.setattr(dsl, "_validar_url_externa", lambda url: None)
        resp = mock.MagicMock()
        resp.__enter__.return_value = SimpleNamespace(status=200)
        urlopen = mock.Mock(return_value=resp)
        monkeypatch.setattr("urllib.request.urlopen", urlopen)

        dsl._enviar_webhook("https://ok.example.com", "post", {"a": 1}, {"X-Token": "t"})

        assert urlopen.call_count == 1
        req = urlopen.call_args[0][0]
        assert req.get_method() == "POST"  # metodo.upper()
        assert req.get_header("X-token") == "t"
        assert req.data == b'{"a": 1}'

    def test_fallo_es_silencioso(self, monkeypatch):
        """Cualquier excepción solo se loguea — nunca propaga."""
        monkeypatch.setattr(dsl, "_validar_url_externa", mock.Mock(side_effect=ValueError("ssrf")))
        dsl._enviar_webhook("file:///x", "POST", {}, {})  # no lanza


class _FakeThread:
    """Reemplazo síncrono de threading.Thread para tests deterministas."""
    def __init__(self, target=None, args=(), daemon=None, name=None):
        self._target = target
        self._args = args

    def start(self):
        self._target(*self._args)


class TestDispararConectores:
    def _setup(self, monkeypatch, conectores):
        monkeypatch.setattr(dsl, "get_config_activa", lambda e: {"conectores": conectores})
        monkeypatch.setattr(dsl.threading, "Thread", _FakeThread)
        enviados = []
        monkeypatch.setattr(
            dsl, "_enviar_webhook",
            lambda url, metodo, payload, headers: enviados.append((url, metodo, payload, headers)),
        )
        return enviados

    def test_sin_conectores_para_el_evento(self, monkeypatch):
        enviados = self._setup(monkeypatch, [
            {"nombre": "otro", "url": "https://x", "evento_origen": "otro.evento"},
        ])
        dsl.disparar_conectores("ventas.pedido.confirmado", {"total": 1}, None)
        assert enviados == []

    def test_dispara_con_mapeo_de_campos(self, monkeypatch):
        enviados = self._setup(monkeypatch, [{
            "nombre": "crm", "url": "https://crm.example.com", "metodo": "PUT",
            "evento_origen": "ventas.pedido.confirmado",
            "headers": {"X-K": "v"},
            "mapeo_campos": {"total": "amount", "cliente": "customer"},
        }])
        dsl.disparar_conectores(
            "ventas.pedido.confirmado", {"total": 100, "cliente": "ACME", "extra": 1}, None
        )
        assert enviados == [(
            "https://crm.example.com", "PUT",
            {"amount": 100, "customer": "ACME"},
            {"X-K": "v"},
        )]

    def test_dispara_sin_mapeo_copia_payload(self, monkeypatch):
        enviados = self._setup(monkeypatch, [{
            "nombre": "hook", "url": "https://h.example.com",
            "evento_origen": "ventas.pedido.confirmado",
        }])
        payload = {"total": 5}
        dsl.disparar_conectores("ventas.pedido.confirmado", payload, None)
        url, metodo, payload_enviado, headers = enviados[0]
        assert metodo == "POST"  # default
        assert payload_enviado == {"total": 5}
        assert payload_enviado is not payload  # copia, no la referencia original


# ═════════════════════════════ Runtime EAV / estados / vistas ════════════════


class TestRuntimeEntidades:
    def test_entidad_no_definida_lanza(self, empresa_a):
        dsl.aplicar_config(
            {"entidades": [{"nombre": "Equipo", "campos": [{"nombre": "serial", "tipo": "text"}]}]},
            empresa_a,
        )
        with pytest.raises(ValueError, match="no está definida en el DSL"):
            dsl.crear_instancia_entidad(empresa_a, "Vehiculo", {"placa": "AA123BB"})

    def test_crear_y_listar_instancias(self, empresa_a):
        dsl.aplicar_config(
            {"entidades": [{"nombre": "Equipo", "campos": [{"nombre": "serial", "tipo": "text"}]}]},
            empresa_a,
        )
        inst = dsl.crear_instancia_entidad(empresa_a, "Equipo", {"serial": "S-1"})
        assert inst.datos == {"serial": "S-1"}
        qs = dsl.listar_instancias_entidad(empresa_a, "Equipo")
        assert list(qs) == [inst]

    def test_sin_definiciones_no_restringe(self, empresa_a):
        """Si la empresa no tiene entidades definidas, se permite crear libremente."""
        inst = dsl.crear_instancia_entidad(empresa_a, "Libre", {"x": 1})
        assert inst.nombre_entidad == "Libre"


class TestRuntimeEstadosYVistas:
    def test_estado_valido_base_y_personalizado(self, empresa_a):
        dsl.aplicar_config(
            {"estados": [{"modelo": "Pedido", "nombre": "EN_RUTA", "etiqueta": "En ruta"}]},
            empresa_a,
        )
        estados = dsl.get_estados_personalizados(empresa_a, "Pedido")
        assert estados == [{"nombre": "EN_RUTA", "etiqueta": "En ruta"}]
        assert dsl.es_estado_valido(empresa_a, "Pedido", "BORRADOR", ["BORRADOR"]) is True
        assert dsl.es_estado_valido(empresa_a, "Pedido", "EN_RUTA") is True
        assert dsl.es_estado_valido(empresa_a, "Pedido", "INVENTADO", ["BORRADOR"]) is False

    def test_vistas_columnas_y_filtros(self, empresa_a):
        dsl.aplicar_config(
            {"vistas": [{"entidad": "Cliente", "columnas": ["rif", "razon_social"],
                         "filtros": {"activo": True}}]},
            empresa_a,
        )
        assert dsl.get_columnas_vista(empresa_a, "Cliente") == ["rif", "razon_social"]
        assert dsl.get_filtros_vista(empresa_a, "Cliente") == {"activo": True}

    def test_vista_inexistente_devuelve_vacios(self, empresa_a):
        assert dsl.get_columnas_vista(empresa_a, "NoExiste") == []
        assert dsl.get_filtros_vista(empresa_a, "NoExiste") == {}
