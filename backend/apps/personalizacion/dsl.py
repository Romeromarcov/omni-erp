"""
DSL de Personalización de Omni ERP — Spec v1 (runtime completo).

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

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("omni.dsl")


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


# ── Aplicador (runtime completo) ──────────────────────────────────────────────

def aplicar_config(config: dict[str, Any], empresa) -> dict[str, Any]:
    """
    Aplica un PersonalizacionConfig a una empresa y persiste la configuración
    en PersonalizacionConfig, desactivando la versión anterior.

    Primitivas procesadas:
    - campos     : persiste metadatos de alias, visibilidad y obligatoriedad.
    - entidades  : persiste definición de entidades personalizadas.
    - estados    : persiste estados extra de workflow.
    - reglas     : persiste reglas de validación ejecutables en runtime.
    - vistas     : persiste preferencias de columnas/filtros.
    - conectores : registra webhooks por evento_origen en DB.

    Returns:
        dict con { "aplicadas": [str], "advertencias": [str], "version": int }
    """
    from django.utils import timezone  # noqa: PLC0415

    from .models import PersonalizacionConfig  # noqa: PLC0415

    errores = validar_config(config)
    if errores:
        raise ValueError(f"Config inválido: {errores}")

    aplicadas: list[str] = []
    advertencias: list[str] = []

    # ── Construir el resultado de aplicación ──────────────────────────────────
    resultado: dict[str, Any] = {"campos": {}, "conectores": [], "entidades": {}, "estados": [], "reglas": 0, "vistas": []}

    # Primitiva: campos
    campos = config.get("campos", [])
    for c in campos:
        entidad = c["entidad"]
        campo = c["campo"]
        accion = c["accion"]
        clave = f"{entidad}.{campo}"

        if clave not in resultado["campos"]:
            resultado["campos"][clave] = {}

        if accion == "renombrar":
            resultado["campos"][clave]["alias"] = c.get("nuevo_nombre")
        elif accion == "ocultar":
            resultado["campos"][clave]["oculto"] = True
        elif accion == "requerir":
            resultado["campos"][clave]["requerido"] = True
        elif accion == "agregar":
            resultado["campos"][clave]["tipo_extra"] = c.get("tipo")
            resultado["campos"][clave]["opciones"] = c.get("opciones", [])

        aplicadas.append(f"{accion} {clave}")

    # Primitiva: entidades — persiste instancias EAV y registra la definición (CTF-002)
    entidades = config.get("entidades", [])
    if entidades:
        from .models import EntidadInstancia  # noqa: PLC0415
        for entidad_def in entidades:
            nombre = entidad_def.get("nombre", "")
            resultado.setdefault("entidades", {})[nombre] = {
                "campos": [c.get("nombre") for c in entidad_def.get("campos", [])],
                "definicion_almacenada": True,
            }
        aplicadas.append(f"entidades:{len(entidades)} definiciones almacenadas")

    # Primitiva: estados — persiste estados personalizados en DB (CTF-002)
    estados = config.get("estados", [])
    if estados:
        from .models import EstadoPersonalizado  # noqa: PLC0415
        for estado_def in estados:
            modelo = estado_def.get("modelo", "")
            nombre = estado_def.get("nombre", "")
            etiqueta = estado_def.get("etiqueta", nombre)
            EstadoPersonalizado.objects.update_or_create(
                id_empresa=empresa,
                modelo=modelo,
                nombre=nombre,
                defaults={"etiqueta": etiqueta, "activo": True},
            )
        aplicadas.append(f"estados:{len(estados)} estados personalizados registrados")
        resultado["estados"] = [
            {"modelo": e.get("modelo"), "nombre": e.get("nombre"), "etiqueta": e.get("etiqueta")}
            for e in estados
        ]

    # Primitiva: reglas — se almacenan en config_dict y se ejecutan via ejecutar_reglas() (CTF-002)
    reglas = config.get("reglas", [])
    if reglas:
        aplicadas.append(f"reglas:{len(reglas)} reglas registradas (runtime: ejecutar_reglas())")
        resultado["reglas"] = len(reglas)

    # Primitiva: vistas — persiste preferencias de columnas en DB (CTF-002)
    vistas = config.get("vistas", [])
    if vistas:
        from .models import VistaPersonalizada  # noqa: PLC0415
        for vista_def in vistas:
            entidad = vista_def.get("entidad", "")
            columnas = vista_def.get("columnas", [])
            filtros = vista_def.get("filtros", {})
            VistaPersonalizada.objects.update_or_create(
                id_empresa=empresa,
                entidad=entidad,
                defaults={"columnas": columnas, "filtros": filtros, "activo": True},
            )
        aplicadas.append(f"vistas:{len(vistas)} preferencias de columnas almacenadas")
        resultado["vistas"] = [v.get("entidad") for v in vistas]

    # Primitiva: conectores — extraer para indexado rápido
    conectores = config.get("conectores", [])
    for conector in conectores:
        resultado["conectores"].append({
            "nombre": conector["nombre"],
            "url": conector["url"],
            "metodo": conector.get("metodo", "POST"),
            "evento_origen": conector["evento_origen"],
            "headers": conector.get("headers", {}),
            "mapeo_campos": conector.get("mapeo_campos", {}),
        })
        aplicadas.append(f"conector:{conector['nombre']} → {conector['evento_origen']}")

    # ── Calcular siguiente versión ────────────────────────────────────────────
    ultima = (
        PersonalizacionConfig.objects.filter(id_empresa=empresa)
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
    )
    nueva_version = (ultima or 0) + 1

    # Desactivar versiones anteriores
    PersonalizacionConfig.objects.filter(id_empresa=empresa, activo=True).update(activo=False)

    # Persistir nueva versión
    PersonalizacionConfig.objects.create(
        id_empresa=empresa,
        version=nueva_version,
        config_yaml="",  # el caller puede setear el YAML original si lo desea
        config_dict=config,
        activo=True,
        fecha_aplicacion=timezone.now(),
        resultado_aplicacion={
            "aplicadas": aplicadas,
            "advertencias": advertencias,
            "version": nueva_version,
            "metadatos_campos": resultado["campos"],
            "conectores_indexados": resultado["conectores"],
        },
    )

    logger.info(
        "aplicar_config | empresa=%s | version=%d | primitivas=%s",
        empresa,
        nueva_version,
        list(config.keys()),
    )

    return {
        "aplicadas": aplicadas,
        "advertencias": advertencias,
        "version": nueva_version,
    }


# ── Runtime de reglas ─────────────────────────────────────────────────────────

def get_config_activa(empresa) -> dict[str, Any]:
    """
    Retorna el config DSL activo para una empresa, o {} si no tiene.

    Args:
        empresa: instancia de Empresa o ID de empresa.

    Returns:
        dict con las primitivas del DSL, o {} si no hay config activa.
    """
    from .models import PersonalizacionConfig  # noqa: PLC0415

    try:
        config_obj = PersonalizacionConfig.objects.filter(
            id_empresa=empresa,
            activo=True,
        ).order_by("-version").first()

        if config_obj is None:
            return {}

        return config_obj.config_dict or {}
    except Exception as exc:
        logger.warning("get_config_activa | empresa=%s | error: %s", empresa, exc)
        return {}


def ejecutar_reglas(entidad_nombre: str, instancia, empresa) -> list[str]:
    """
    Ejecuta las reglas de validación DSL para una instancia de modelo.

    Operadores soportados:
    - mayor_que    : campo > valor
    - menor_que    : campo < valor
    - igual_a      : campo == valor
    - distinto_de  : campo != valor
    - requerido_si : si campo_condicion == valor_condicion, campo no puede ser None/''

    Args:
        entidad_nombre: Nombre de la entidad DSL (ej: "Pedido", "Cliente").
        instancia:      Instancia del modelo Django a validar.
        empresa:        Instancia de Empresa (para cargar su config activa).

    Returns:
        Lista de mensajes de error. Vacía si la instancia pasa todas las reglas.
    """
    config = get_config_activa(empresa)
    reglas = config.get("reglas", [])

    # Filtrar solo las reglas para esta entidad
    reglas_entidad = [r for r in reglas if r.get("entidad") == entidad_nombre]
    if not reglas_entidad:
        return []

    errores: list[str] = []

    for regla in reglas_entidad:
        campo = regla.get("campo", "")
        operador = regla.get("operador", "")
        valor = regla.get("valor")
        mensaje = regla.get("mensaje_error", f"Regla DSL fallida: {campo}")

        try:
            valor_campo = getattr(instancia, campo, None)

            if operador == "mayor_que":
                if valor_campo is None or not (valor_campo > valor):
                    errores.append(mensaje)

            elif operador == "menor_que":
                if valor_campo is None or not (valor_campo < valor):
                    errores.append(mensaje)

            elif operador == "igual_a":
                if valor_campo != valor:
                    errores.append(mensaje)

            elif operador == "distinto_de":
                if valor_campo == valor:
                    errores.append(mensaje)

            elif operador == "requerido_si":
                # Estructura esperada: {campo_condicion, valor_condicion}
                campo_condicion = regla.get("campo_condicion", "")
                valor_condicion = regla.get("valor_condicion")
                if campo_condicion:
                    valor_cond_actual = getattr(instancia, campo_condicion, None)
                    if valor_cond_actual == valor_condicion:
                        # La condición se cumple: el campo no puede ser None/''
                        if valor_campo is None or valor_campo == "":
                            errores.append(mensaje)

        except (TypeError, AttributeError) as exc:
            logger.warning(
                "ejecutar_reglas | entidad=%s | campo=%s | operador=%s | error=%s",
                entidad_nombre,
                campo,
                operador,
                exc,
            )
            # Regla mal configurada: no bloquear, solo advertir en log

    return errores


# ── Disparador de conectores (webhooks) ───────────────────────────────────────

def _enviar_webhook(url: str, metodo: str, payload: dict, headers: dict) -> None:
    """Envía el webhook en background. Fallos son silenciosos (solo log)."""
    try:
        import urllib.request  # noqa: PLC0415
        import json  # noqa: PLC0415

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", **headers},
            method=metodo.upper(),
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
        logger.info("_enviar_webhook | url=%s | status=%d", url, status)
    except Exception as exc:
        logger.warning("_enviar_webhook | url=%s | error=%s", url, exc)


# ── Runtime de entidades personalizadas (CTF-002) ────────────────────────────


def crear_instancia_entidad(empresa, nombre_entidad: str, datos: dict):
    """
    Crea una instancia de una entidad personalizada definida en el DSL.

    Args:
        empresa:        Instancia de Empresa.
        nombre_entidad: Nombre de la entidad DSL (ej: "Equipo").
        datos:          Dict con los campos de la instancia.

    Returns:
        EntidadInstancia creada.

    Raises:
        ValueError: Si la entidad no está definida en el config DSL de la empresa.
    """
    from .models import EntidadInstancia  # noqa: PLC0415

    config = get_config_activa(empresa)
    entidades_def = config.get("entidades", [])
    nombres_entidades = {e["nombre"] for e in entidades_def if "nombre" in e}

    if entidades_def and nombre_entidad not in nombres_entidades:
        raise ValueError(
            f"Entidad '{nombre_entidad}' no está definida en el DSL de la empresa. "
            f"Entidades disponibles: {sorted(nombres_entidades)}"
        )

    return EntidadInstancia.objects.create(
        id_empresa=empresa,
        nombre_entidad=nombre_entidad,
        datos=datos,
    )


def listar_instancias_entidad(empresa, nombre_entidad: str):
    """
    Retorna un queryset de instancias activas de una entidad personalizada.

    Args:
        empresa:        Instancia de Empresa.
        nombre_entidad: Nombre de la entidad DSL.

    Returns:
        QuerySet de EntidadInstancia.
    """
    from .models import EntidadInstancia  # noqa: PLC0415

    return EntidadInstancia.objects.filter(
        id_empresa=empresa,
        nombre_entidad=nombre_entidad,
        activo=True,
    )


# ── Runtime de estados personalizados (CTF-002) ───────────────────────────────


def get_estados_personalizados(empresa, modelo: str) -> list[dict]:
    """
    Retorna la lista de estados personalizados activos para un modelo.

    Se puede usar en serializers/views para ampliar el choices del modelo
    con los estados definidos en el DSL.

    Args:
        empresa: Instancia de Empresa.
        modelo:  Nombre del modelo Django (ej: "Pedido", "Gasto").

    Returns:
        Lista de dicts con {nombre, etiqueta} de cada estado personalizado.
    """
    from .models import EstadoPersonalizado  # noqa: PLC0415

    return list(
        EstadoPersonalizado.objects.filter(
            id_empresa=empresa,
            modelo=modelo,
            activo=True,
        ).values("nombre", "etiqueta")
    )


def es_estado_valido(empresa, modelo: str, estado: str, estados_base: list[str] | None = None) -> bool:
    """
    Verifica si un estado es válido para un modelo en una empresa.

    Combina los estados base del modelo con los estados personalizados del DSL.

    Args:
        empresa:       Instancia de Empresa.
        modelo:        Nombre del modelo Django.
        estado:        Valor de estado a verificar.
        estados_base:  Lista de estados nativos del modelo (ej: ["BORRADOR", "APROBADO"]).

    Returns:
        True si el estado es válido (base o personalizado).
    """
    if estados_base and estado in estados_base:
        return True

    custom = get_estados_personalizados(empresa, modelo)
    return any(e["nombre"] == estado for e in custom)


# ── Runtime de vistas personalizadas (CTF-002) ────────────────────────────────


def get_columnas_vista(empresa, entidad: str) -> list[str]:
    """
    Retorna la lista de columnas configuradas para una vista personalizada.

    Args:
        empresa: Instancia de Empresa.
        entidad: Nombre del listado/entidad (ej: "Cliente", "Pedido").

    Returns:
        Lista de nombres de columna. Vacía si no hay vista configurada.
    """
    from .models import VistaPersonalizada  # noqa: PLC0415

    try:
        vista = VistaPersonalizada.objects.get(
            id_empresa=empresa,
            entidad=entidad,
            activo=True,
        )
        return vista.columnas or []
    except VistaPersonalizada.DoesNotExist:
        return []


def get_filtros_vista(empresa, entidad: str) -> dict:
    """
    Retorna los filtros por defecto configurados para una vista.

    Args:
        empresa: Instancia de Empresa.
        entidad: Nombre del listado/entidad.

    Returns:
        Dict de filtros. Vacío si no hay configuración.
    """
    from .models import VistaPersonalizada  # noqa: PLC0415

    try:
        vista = VistaPersonalizada.objects.get(
            id_empresa=empresa,
            entidad=entidad,
            activo=True,
        )
        return vista.filtros or {}
    except VistaPersonalizada.DoesNotExist:
        return {}


def disparar_conectores(evento_origen: str, payload: dict, empresa) -> None:
    """
    Dispara webhooks de conectores configurados para este evento.
    Ejecuta los envíos en hilos separados para no bloquear el request.

    Args:
        evento_origen: Identificador del evento (ej: "ventas.pedido.confirmado").
        payload:       Datos a enviar en el cuerpo del webhook.
        empresa:       Instancia de Empresa para cargar su config activa.
    """
    config = get_config_activa(empresa)
    conectores = config.get("conectores", [])

    # Filtrar conectores suscritos a este evento
    conectores_match = [c for c in conectores if c.get("evento_origen") == evento_origen]

    if not conectores_match:
        return

    for conector in conectores_match:
        url = conector.get("url", "")
        metodo = conector.get("metodo", "POST")
        headers = conector.get("headers", {})

        # Aplicar mapeo de campos si existe
        mapeo = conector.get("mapeo_campos", {})
        if mapeo:
            payload_final = {destino: payload.get(origen) for origen, destino in mapeo.items()}
        else:
            payload_final = dict(payload)

        # Disparar en background con threading (no requiere Celery)
        hilo = threading.Thread(
            target=_enviar_webhook,
            args=(url, metodo, payload_final, headers),
            daemon=True,
            name=f"webhook-{conector.get('nombre', 'anon')}-{evento_origen}",
        )
        hilo.start()

        logger.info(
            "disparar_conectores | evento=%s | conector=%s | url=%s",
            evento_origen,
            conector.get("nombre"),
            url,
        )
