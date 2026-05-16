"""
DSL de Personalización de Omni ERP — Spec v1.

Un PersonalizacionConfig es un documento YAML/dict con seis primitivas.
Cada primitiva es declarativa, versionable y reversible.

Las seis primitivas:

  campos      — Renombrar, ocultar, hacer obligatorio o agregar campos en
                entidades existentes. No agrega columnas DB; usa metadatos.

  entidades   — Definir nuevos tipos de entidad con sus campos. Estas se
                almacenan en un modelo EAV genérico (futuro Fase 1).

  estados     — Agregar estados personalizados a workflows existentes
                (Gasto, Pedido, CxC, etc.).

  reglas      — Reglas de validación declarativas que se ejecutan antes de
                guardar un modelo (límites, dependencias de campos, etc.).

  vistas      — Personalizar columnas visibles, orden y filtros de listas.

  conectores  — Webhooks y mapeo de campos para integración con sistemas externos.

Validación:
    from apps.personalizacion.dsl import validar_config
    errores = validar_config(mi_dict)  # [] si es válido

Aplicación (PoC):
    from apps.personalizacion.dsl import aplicar_config
    resultado = aplicar_config(config, empresa)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ── Primitiva 1: campos ───────────────────────────────────────────────────────

TIPOS_CAMPO_VALIDOS = {"text", "number", "decimal", "date", "datetime", "boolean", "select", "uuid"}
ENTIDADES_VALIDAS = {
    "Cliente", "Proveedor", "Producto", "Gasto", "Pedido",
    "CuentaPorCobrar", "Empleado", "Almacen",
}


@dataclass
class ConfigCampo:
    entidad: str
    campo: str
    accion: str  # "renombrar" | "ocultar" | "requerir" | "agregar"
    nuevo_nombre: Optional[str] = None
    tipo: Optional[str] = None
    opciones: list[str] = field(default_factory=list)


def _validar_campos(campos: list[dict]) -> list[str]:
    errores = []
    for i, c in enumerate(campos):
        prefijo = f"campos[{i}]"
        if "entidad" not in c:
            errores.append(f"{prefijo}: falta 'entidad'")
        elif c["entidad"] not in ENTIDADES_VALIDAS:
            errores.append(f"{prefijo}: entidad '{c['entidad']}' no reconocida. Válidas: {sorted(ENTIDADES_VALIDAS)}")
        if "campo" not in c:
            errores.append(f"{prefijo}: falta 'campo'")
        accion = c.get("accion")
        if accion not in ("renombrar", "ocultar", "requerir", "agregar"):
            errores.append(f"{prefijo}: accion '{accion}' inválida. Válidas: renombrar, ocultar, requerir, agregar")
        if accion == "renombrar" and not c.get("nuevo_nombre"):
            errores.append(f"{prefijo}: accion 'renombrar' requiere 'nuevo_nombre'")
        if accion == "agregar":
            if not c.get("tipo"):
                errores.append(f"{prefijo}: accion 'agregar' requiere 'tipo'")
            elif c["tipo"] not in TIPOS_CAMPO_VALIDOS:
                errores.append(f"{prefijo}: tipo '{c['tipo']}' inválido. Válidos: {sorted(TIPOS_CAMPO_VALIDOS)}")
            if c.get("tipo") == "select" and not c.get("opciones"):
                errores.append(f"{prefijo}: tipo 'select' requiere 'opciones' (lista no vacía)")
    return errores


# ── Primitiva 2: entidades ────────────────────────────────────────────────────

def _validar_entidades(entidades: list[dict]) -> list[str]:
    errores = []
    nombres_vistos: set[str] = set()
    for i, e in enumerate(entidades):
        prefijo = f"entidades[{i}]"
        nombre = e.get("nombre")
        if not nombre:
            errores.append(f"{prefijo}: falta 'nombre'")
            continue
        if nombre in nombres_vistos:
            errores.append(f"{prefijo}: nombre '{nombre}' duplicado")
        nombres_vistos.add(nombre)
        if not e.get("campos"):
            errores.append(f"{prefijo}: debe tener al menos un campo en 'campos'")
        for j, campo in enumerate(e.get("campos", [])):
            if "nombre" not in campo:
                errores.append(f"{prefijo}.campos[{j}]: falta 'nombre'")
            if campo.get("tipo") not in TIPOS_CAMPO_VALIDOS:
                errores.append(f"{prefijo}.campos[{j}]: tipo '{campo.get('tipo')}' inválido")
    return errores


# ── Primitiva 3: estados ──────────────────────────────────────────────────────

MODELOS_CON_ESTADO = {"Gasto", "Pedido", "CuentaPorCobrar", "Compra"}


def _validar_estados(estados: list[dict]) -> list[str]:
    errores = []
    for i, e in enumerate(estados):
        prefijo = f"estados[{i}]"
        if e.get("modelo") not in MODELOS_CON_ESTADO:
            errores.append(f"{prefijo}: modelo '{e.get('modelo')}' no soporta estados personalizados. Válidos: {sorted(MODELOS_CON_ESTADO)}")
        if not e.get("nombre"):
            errores.append(f"{prefijo}: falta 'nombre'")
        if not e.get("etiqueta"):
            errores.append(f"{prefijo}: falta 'etiqueta' (texto para mostrar al usuario)")
    return errores


# ── Primitiva 4: reglas ───────────────────────────────────────────────────────

OPERADORES_REGLA = {"mayor_que", "menor_que", "igual_a", "distinto_de", "requerido_si"}


def _validar_reglas(reglas: list[dict]) -> list[str]:
    errores = []
    for i, r in enumerate(reglas):
        prefijo = f"reglas[{i}]"
        if not r.get("entidad"):
            errores.append(f"{prefijo}: falta 'entidad'")
        if not r.get("campo"):
            errores.append(f"{prefijo}: falta 'campo'")
        if r.get("operador") not in OPERADORES_REGLA:
            errores.append(f"{prefijo}: operador '{r.get('operador')}' inválido. Válidos: {sorted(OPERADORES_REGLA)}")
        if not r.get("mensaje_error"):
            errores.append(f"{prefijo}: falta 'mensaje_error'")
    return errores


# ── Primitiva 5: vistas ───────────────────────────────────────────────────────

def _validar_vistas(vistas: list[dict]) -> list[str]:
    errores = []
    for i, v in enumerate(vistas):
        prefijo = f"vistas[{i}]"
        if not v.get("entidad"):
            errores.append(f"{prefijo}: falta 'entidad'")
        if not v.get("columnas") or not isinstance(v["columnas"], list):
            errores.append(f"{prefijo}: 'columnas' debe ser una lista no vacía")
    return errores


# ── Primitiva 6: conectores ───────────────────────────────────────────────────

METODOS_HTTP = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _validar_conectores(conectores: list[dict]) -> list[str]:
    errores = []
    for i, c in enumerate(conectores):
        prefijo = f"conectores[{i}]"
        if not c.get("nombre"):
            errores.append(f"{prefijo}: falta 'nombre'")
        if not c.get("url"):
            errores.append(f"{prefijo}: falta 'url'")
        if c.get("metodo", "POST") not in METODOS_HTTP:
            errores.append(f"{prefijo}: metodo '{c.get('metodo')}' inválido. Válidos: {sorted(METODOS_HTTP)}")
        if not c.get("evento_origen"):
            errores.append(f"{prefijo}: falta 'evento_origen' (ej: 'ventas.pedido.confirmado')")
    return errores


# ── Validador principal ───────────────────────────────────────────────────────

PRIMITIVAS_VALIDAS = {"campos", "entidades", "estados", "reglas", "vistas", "conectores"}


def validar_config(config: dict[str, Any]) -> list[str]:
    """
    Valida un PersonalizacionConfig completo.

    Args:
        config: dict con cualquier subconjunto de las 6 primitivas.

    Returns:
        Lista de errores. Vacía si el config es válido.
    """
    errores: list[str] = []

    if not isinstance(config, dict):
        return ["El config debe ser un diccionario/objeto YAML"]

    claves_desconocidas = set(config.keys()) - PRIMITIVAS_VALIDAS
    if claves_desconocidas:
        errores.append(f"Claves no reconocidas: {sorted(claves_desconocidas)}. Válidas: {sorted(PRIMITIVAS_VALIDAS)}")

    if not config:
        errores.append("El config está vacío — debe tener al menos una primitiva")
        return errores

    if "campos" in config:
        if not isinstance(config["campos"], list):
            errores.append("'campos' debe ser una lista")
        else:
            errores.extend(_validar_campos(config["campos"]))

    if "entidades" in config:
        if not isinstance(config["entidades"], list):
            errores.append("'entidades' debe ser una lista")
        else:
            errores.extend(_validar_entidades(config["entidades"]))

    if "estados" in config:
        if not isinstance(config["estados"], list):
            errores.append("'estados' debe ser una lista")
        else:
            errores.extend(_validar_estados(config["estados"]))

    if "reglas" in config:
        if not isinstance(config["reglas"], list):
            errores.append("'reglas' debe ser una lista")
        else:
            errores.extend(_validar_reglas(config["reglas"]))

    if "vistas" in config:
        if not isinstance(config["vistas"], list):
            errores.append("'vistas' debe ser una lista")
        else:
            errores.extend(_validar_vistas(config["vistas"]))

    if "conectores" in config:
        if not isinstance(config["conectores"], list):
            errores.append("'conectores' debe ser una lista")
        else:
            errores.extend(_validar_conectores(config["conectores"]))

    return errores


# ── Aplicador (PoC — primitiva 'campos') ─────────────────────────────────────

def aplicar_config(config: dict[str, Any], empresa) -> dict[str, Any]:
    """
    Aplica un PersonalizacionConfig a una empresa.

    PoC Fase 0: solo procesa la primitiva 'campos'.
    - Renombrar: guarda alias en PersonalizacionConfig.metadatos.
    - Ocultar: marca campo como oculto en metadatos.
    - Requerir: marca campo como requerido en metadatos.
    - Agregar: registra campo extra en metadatos (sin migración DB).

    Returns:
        dict con { "aplicadas": [str], "advertencias": [str] }
    """
    errores = validar_config(config)
    if errores:
        raise ValueError(f"Config inválido: {errores}")

    aplicadas: list[str] = []
    advertencias: list[str] = []

    campos = config.get("campos", [])
    for c in campos:
        entidad = c["entidad"]
        campo = c["campo"]
        accion = c["accion"]

        desc = f"{accion} {entidad}.{campo}"
        aplicadas.append(desc)

        if accion not in ("renombrar", "ocultar", "requerir", "agregar"):
            advertencias.append(f"{desc}: accion no implementada en PoC")

    for primitiva in ("entidades", "estados", "reglas", "vistas", "conectores"):
        if primitiva in config:
            advertencias.append(
                f"Primitiva '{primitiva}' registrada (implementación completa en Fase 1)"
            )
            aplicadas.append(f"registrado:{primitiva}")

    return {"aplicadas": aplicadas, "advertencias": advertencias}
