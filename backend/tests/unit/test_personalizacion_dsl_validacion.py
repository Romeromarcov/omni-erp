"""
Unit puro (sin BD) del validador del DSL de personalización
(``apps.personalizacion.dsl.validar_config`` y las 6 primitivas).

``validar_config`` es una función pura dict→list[str] (errores). Aquí se cubren los
caminos de error de cada primitiva y el caso válido (lista vacía), que son las ramas
que la suite de runtime no ejercitaba.
"""

import pytest

from apps.personalizacion.dsl import validar_config

pytestmark = pytest.mark.unit


# ── Top-level ───────────────────────────────────────────────────────────────────


def test_config_no_dict():
    assert validar_config(["no", "soy", "dict"]) == ["El config debe ser un diccionario/objeto YAML"]


def test_config_vacio():
    errs = validar_config({})
    assert any("vacío" in e for e in errs)


def test_claves_desconocidas():
    errs = validar_config({"campos": [], "inventado": []})
    assert any("no reconocidas" in e for e in errs)


@pytest.mark.parametrize("prim", ["campos", "entidades", "estados", "reglas", "vistas", "conectores"])
def test_primitiva_no_es_lista(prim):
    errs = validar_config({prim: {"no": "lista"}})
    assert any(f"'{prim}' debe ser una lista" in e for e in errs)


# ── campos ──────────────────────────────────────────────────────────────────────


def test_campos_errores_varios():
    errs = validar_config({"campos": [
        {"campo": "x", "accion": "ocultar"},                       # falta entidad
        {"entidad": "Marciano", "campo": "x", "accion": "ocultar"},  # entidad inválida
        {"entidad": "Cliente", "accion": "ocultar"},               # falta campo
        {"entidad": "Cliente", "campo": "x", "accion": "explotar"},  # accion inválida
        {"entidad": "Cliente", "campo": "x", "accion": "renombrar"},  # falta nuevo_nombre
        {"entidad": "Cliente", "campo": "x", "accion": "agregar"},   # falta tipo
        {"entidad": "Cliente", "campo": "x", "accion": "agregar", "tipo": "raro"},  # tipo inválido
        {"entidad": "Cliente", "campo": "x", "accion": "agregar", "tipo": "select"},  # select sin opciones
    ]})
    assert any("falta 'entidad'" in e for e in errs)
    assert any("no reconocida" in e for e in errs)
    assert any("falta 'campo'" in e for e in errs)
    assert any("inválida" in e for e in errs)
    assert any("requiere 'nuevo_nombre'" in e for e in errs)
    assert any("requiere 'tipo'" in e for e in errs)
    assert any("tipo 'raro' inválido" in e for e in errs)
    assert any("requiere 'opciones'" in e for e in errs)


def test_campos_validos_sin_errores():
    errs = validar_config({"campos": [
        {"entidad": "Cliente", "campo": "alias", "accion": "renombrar", "nuevo_nombre": "Apodo"},
        {"entidad": "Producto", "campo": "color", "accion": "agregar", "tipo": "select", "opciones": ["rojo", "azul"]},
        {"entidad": "Gasto", "campo": "nota", "accion": "ocultar"},
    ]})
    assert errs == []


# ── entidades ───────────────────────────────────────────────────────────────────


def test_entidades_errores():
    errs = validar_config({"entidades": [
        {"campos": [{"nombre": "a", "tipo": "text"}]},   # falta nombre
        {"nombre": "Dup", "campos": [{"nombre": "a", "tipo": "text"}]},
        {"nombre": "Dup", "campos": [{"nombre": "b", "tipo": "text"}]},  # duplicado
        {"nombre": "SinCampos"},                          # sin campos
        {"nombre": "MalCampo", "campos": [{"tipo": "text"}]},  # campo sin nombre
        {"nombre": "MalTipo", "campos": [{"nombre": "z", "tipo": "raro"}]},  # tipo inválido
    ]})
    assert any("falta 'nombre'" in e for e in errs)
    assert any("duplicado" in e for e in errs)
    assert any("al menos un campo" in e for e in errs)
    assert any("falta 'nombre'" in e for e in errs)
    assert any("tipo 'raro' inválido" in e for e in errs)


def test_entidades_validas():
    errs = validar_config({"entidades": [
        {"nombre": "Mascota", "campos": [{"nombre": "especie", "tipo": "text"}]},
    ]})
    assert errs == []


# ── estados ─────────────────────────────────────────────────────────────────────


def test_estados_errores():
    errs = validar_config({"estados": [
        {"modelo": "Inexistente", "nombre": "x", "etiqueta": "X"},  # modelo inválido
        {"modelo": "Pedido", "etiqueta": "X"},                       # falta nombre
        {"modelo": "Pedido", "nombre": "x"},                         # falta etiqueta
    ]})
    assert any("no soporta estados" in e for e in errs)
    assert any("falta 'nombre'" in e for e in errs)
    assert any("falta 'etiqueta'" in e for e in errs)


def test_estados_validos():
    assert validar_config({"estados": [{"modelo": "Gasto", "nombre": "rev", "etiqueta": "En revisión"}]}) == []


# ── reglas ──────────────────────────────────────────────────────────────────────


def test_reglas_errores():
    errs = validar_config({"reglas": [
        {"campo": "x", "operador": "mayor_que", "mensaje_error": "m"},  # falta entidad
        {"entidad": "Gasto", "operador": "mayor_que", "mensaje_error": "m"},  # falta campo
        {"entidad": "Gasto", "campo": "x", "operador": "raro", "mensaje_error": "m"},  # operador inválido
        {"entidad": "Gasto", "campo": "x", "operador": "igual_a"},  # falta mensaje_error
    ]})
    assert any("falta 'entidad'" in e for e in errs)
    assert any("falta 'campo'" in e for e in errs)
    assert any("operador 'raro' inválido" in e for e in errs)
    assert any("falta 'mensaje_error'" in e for e in errs)


def test_reglas_validas():
    assert validar_config({"reglas": [
        {"entidad": "Gasto", "campo": "monto", "operador": "mayor_que", "mensaje_error": "muy alto"},
    ]}) == []


# ── vistas ──────────────────────────────────────────────────────────────────────


def test_vistas_errores():
    errs = validar_config({"vistas": [
        {"columnas": ["a"]},                 # falta entidad
        {"entidad": "Cliente"},              # columnas faltante
        {"entidad": "Cliente", "columnas": "no-lista"},
    ]})
    assert any("falta 'entidad'" in e for e in errs)
    assert any("'columnas' debe ser una lista no vacía" in e for e in errs)


def test_vistas_validas():
    assert validar_config({"vistas": [{"entidad": "Cliente", "columnas": ["nombre", "rif"]}]}) == []


# ── conectores ──────────────────────────────────────────────────────────────────


def test_conectores_errores():
    errs = validar_config({"conectores": [
        {"url": "http://x", "evento_origen": "a.b.c"},          # falta nombre
        {"nombre": "n", "evento_origen": "a.b.c"},              # falta url
        {"nombre": "n", "url": "http://x", "metodo": "TRACE", "evento_origen": "a.b.c"},  # metodo inválido
        {"nombre": "n", "url": "http://x"},                     # falta evento_origen
    ]})
    assert any("falta 'nombre'" in e for e in errs)
    assert any("falta 'url'" in e for e in errs)
    assert any("metodo 'TRACE' inválido" in e for e in errs)
    assert any("falta 'evento_origen'" in e for e in errs)


def test_conectores_validos():
    assert validar_config({"conectores": [
        {"nombre": "n", "url": "http://x", "metodo": "POST", "evento_origen": "ventas.pedido.confirmado"},
    ]}) == []


# ── config combinado válido ─────────────────────────────────────────────────────


def test_config_completo_valido():
    config = {
        "campos": [{"entidad": "Cliente", "campo": "alias", "accion": "ocultar"}],
        "vistas": [{"entidad": "Cliente", "columnas": ["nombre"]}],
    }
    assert validar_config(config) == []
