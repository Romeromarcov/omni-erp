"""Agentes IA de Omni Connect (Plan 07 S12): ``connect_calificador`` y ``connect_seguimiento``.

Diseño:
  - Funciones puras y determinísticas (sin BD) para evaluación offline en
    ``tests_eval/test_eval_connect.py`` y fallback seguro sin red/API key:
      * ``calificar_lead_deterministico(datos_lead)``
      * ``proponer_seguimiento_deterministico(datos_lead)``
  - Orquestación transaccional multi-tenant con ``llm_gateway`` (opcional si está
    habilitado en ``ConfigAgente.config_extra["usar_llm"]``), persistencia en
    ``PrediccionAgente`` llamando ``full_clean()`` y compuerta humana obligatoria
    en ``gestion_aprobaciones`` (``codigo_tipo="CONNECT_ENVIO_EXTERNO"``) para
    toda propuesta de envío externo.

Regla inviolable (ADR-014):
  ``connect_seguimiento`` NUNCA envía correos, WhatsApp ni mensajes externos
  directamente. Toda propuesta con ``accion == "ENVIO_EXTERNO"`` crea una
  ``SolicitudAprobacion`` en estado ``PENDIENTE`` ligada a la ``PrediccionAgente``.
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core import llm_gateway

logger = logging.getLogger("omni.agentes.connect")

AGENTE_CALIFICADOR_ID = "connect_calificador"
AGENTE_SEGUIMIENTO_ID = "connect_seguimiento"
CODIGO_APROBACION_ENVIO_EXTERNO = "CONNECT_ENVIO_EXTERNO"
MODULO_ORIGEN_CONNECT = "connect"
MODELO_ORIGEN_PREDICCION = "agentes.PrediccionAgente"

_PRIORIDADES_VALIDAS = frozenset({"ALTA", "MEDIA", "BAJA"})
_ACTIVIDADES_VALIDAS = frozenset({"LLAMADA", "WHATSAPP", "CORREO", "NOTA", "NINGUNA"})
_CANALES_VALIDOS = frozenset({"WHATSAPP", "EMAIL", "LLAMADA", "NINGUNO"})
_ACCIONES_VALIDAS = frozenset({"ENVIO_EXTERNO", "TAREA_INTERNA", "NO_CONTACTAR"})

_DOMINIOS_GRATUITOS = frozenset(
    {
        "gmail.com",
        "hotmail.com",
        "outlook.com",
        "yahoo.com",
        "yahoo.es",
        "live.com",
        "icloud.com",
        "proton.me",
        "protonmail.com",
    }
)

_KEYWORDS_CARGO_DECISOR = (
    "gerente",
    "director",
    "directora",
    "ceo",
    "socio",
    "socia",
    "dueno",
    "duena",
    "propietario",
    "jefe",
    "compras",
    "presidente",
    "vp",
    "administrador",
)
_KEYWORDS_ALTA_INTENCION = (
    "cotizacion",
    "cotizar",
    "presupuesto",
    "comprar",
    "pedido",
    "urgente",
    "precio",
    "precios",
    "mayorista",
    "distribuidor",
    "flota",
    "contrato",
    "reunion",
    "demo",
    "factura",
    "volumen",
    "mensual",
    "orden de compra",
)
_KEYWORDS_MEDIA_INTENCION = (
    "informacion",
    "catalogo",
    "consulta",
    "interesado",
    "interesada",
    "productos",
    "servicios",
    "disponibilidad",
    "tarifas",
    "planes",
)
_KEYWORDS_BAJA_INTENCION = (
    "empleo",
    "curriculum",
    "hoja de vida",
    "pasantia",
    "solo mirando",
    "no gracias",
    "prueba tecnica",
    "test interno",
    "spam",
)
_KEYWORDS_LLAMADA = (
    "llamar",
    "llamada",
    "llamame",
    "telefonicamente",
    "por telefono",
    "conversar por telefono",
)
_KEYWORDS_CORREO_FORMAL = (
    "correo",
    "email",
    "cotizacion",
    "presupuesto",
    "propuesta",
    "catalogo",
    "pdf",
    "factura",
    "ficha tecnica",
    "lista de precios",
)

_DIGITS_RE = re.compile(r"\D+")
_WORD_TEST_RE = re.compile(r"\b(test|prueba|cv)\b")

_SYSTEM_PROMPT_CALIFICADOR = """Eres un calificador comercial B2B/B2C para Omni Connect.
Evalúa el lead proporcionado y responde SOLO con JSON válido:
{
  "prioridad": "ALTA|MEDIA|BAJA",
  "score": 0,
  "confianza": 0.85,
  "siguiente_actividad": "LLAMADA|WHATSAPP|CORREO|NOTA|NINGUNA",
  "razonamiento": "Explicación concisa en español"
}"""

_SYSTEM_PROMPT_SEGUIMIENTO = """Eres un asistente de seguimiento comercial de Omni Connect.
NUNCA indiques que el mensaje fue enviado; redacta un borrador profesional para aprobación humana.
Responde SOLO con JSON válido:
{
  "asunto": "Asunto breve",
  "borrador_mensaje": "Mensaje breve y cordial en español",
  "razonamiento": "Justificación concisa"
}"""


def _normalizar_texto(texto: Any) -> str:
    crudo = str(texto or "").strip().lower()
    if not crudo:
        return ""
    descompuesto = unicodedata.normalize("NFKD", crudo)
    return "".join(ch for ch in descompuesto if not unicodedata.combining(ch))


def _tiene_email_valido(email: Any) -> tuple[bool, bool]:
    """Retorna ``(valido, es_corporativo)``."""
    limpio = str(email or "").strip().lower()
    if "@" not in limpio or " " in limpio:
        return False, False
    local, _, dominio = limpio.partition("@")
    if not local or "." not in dominio or dominio.startswith(".") or dominio.endswith("."):
        return False, False
    return True, dominio not in _DOMINIOS_GRATUITOS


def _tiene_telefono_valido(telefono: Any) -> bool:
    digitos = _DIGITS_RE.sub("", str(telefono or ""))
    return 7 <= len(digitos) <= 15


def _contiene_alguno(texto_norm: str, keywords: tuple[str, ...]) -> bool:
    return any(kw in texto_norm for kw in keywords)


def _entero_seguro(valor: Any, default: int = 0) -> int:
    if isinstance(valor, bool) or valor is None:
        return default
    try:
        return int(valor)
    except (TypeError, ValueError):
        return default


def calificar_lead_deterministico(datos_lead: dict[str, Any]) -> dict[str, Any]:
    """Califica un lead de Omni Connect de forma 100 % determinística y sin BD."""
    anonimizado = bool(datos_lead.get("anonimizado", False))
    activo = bool(datos_lead.get("activo", True))
    if anonimizado or not activo:
        return {
            "prioridad": "BAJA",
            "score": 0,
            "score_decimal": "0.00",
            "confianza": 0.95,
            "siguiente_actividad": "NINGUNA",
            "razonamiento": "Lead anonimizado o inactivo; no procede calificación comercial activa.",
            "factores": ["lead_inactivo_o_anonimizado"],
            "modelo_llm": "fallback-reglas",
        }

    email_ok, email_corp = _tiene_email_valido(datos_lead.get("email"))
    tel_ok = _tiene_telefono_valido(datos_lead.get("telefono"))
    empresa_nombre = str(datos_lead.get("empresa_nombre") or "").strip()
    cargo = str(datos_lead.get("cargo") or "").strip()
    mensaje = str(datos_lead.get("mensaje") or "").strip()
    fuente = str(datos_lead.get("fuente") or "MANUAL").strip().upper()
    dias_captura = max(0, _entero_seguro(datos_lead.get("dias_desde_captura"), 0))
    total_toques = max(0, _entero_seguro(datos_lead.get("total_toques"), 0))
    total_actividades = max(0, _entero_seguro(datos_lead.get("total_actividades"), 0))
    tiene_contacto_previo = bool(datos_lead.get("tiene_contacto_previo", False))

    cargo_norm = _normalizar_texto(cargo)
    mensaje_norm = _normalizar_texto(mensaje)
    texto_rol = f"{cargo_norm} {mensaje_norm}".strip()

    score = 0
    factores: list[str] = []

    if email_ok:
        score += 12
        factores.append("email_valido")
        if email_corp:
            score += 6
            factores.append("email_corporativo")
    if tel_ok:
        score += 12
        factores.append("telefono_valido")
    if email_ok and tel_ok:
        score += 4
        factores.append("contacto_multicanal")

    if len(empresa_nombre) >= 2:
        score += 12
        factores.append("empresa_identificada")

    if _contiene_alguno(texto_rol, _KEYWORDS_CARGO_DECISOR):
        score += 12
        factores.append("rol_decisor")
    elif len(cargo) >= 2:
        score += 5
        factores.append("cargo_declarado")

    baja_intencion = _contiene_alguno(mensaje_norm, _KEYWORDS_BAJA_INTENCION) or bool(
        _WORD_TEST_RE.search(mensaje_norm)
    )
    if baja_intencion:
        score -= 25
        factores.append("intencion_no_comercial")
    elif _contiene_alguno(mensaje_norm, _KEYWORDS_ALTA_INTENCION):
        score += 26
        factores.append("alta_intencion_compra")
    elif _contiene_alguno(mensaje_norm, _KEYWORDS_MEDIA_INTENCION):
        score += 10
        factores.append("interes_exploratorio")

    puntos_fuente = {
        "NFC": 12,
        "QR": 8,
        "ENLACE": 6,
        "MANUAL": 5,
        "IMPORTACION": 2,
    }.get(fuente, 4)
    score += puntos_fuente
    factores.append(f"fuente_{fuente.lower()}")

    if dias_captura <= 2:
        score += 8
        factores.append("captura_reciente")
    elif dias_captura <= 7:
        score += 4
        factores.append("captura_semana")
    elif dias_captura > 30:
        score -= 10
        factores.append("lead_antiguo")

    if total_toques >= 2:
        score += 6
        factores.append("interaccion_recurrente")
    if tiene_contacto_previo:
        score += 5
        factores.append("contacto_previo")
    if total_actividades >= 1:
        score += 4
        factores.append("actividad_registrada")

    score_final = max(0, min(100, score))
    score_dec = Decimal(score_final).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if score_final >= 70:
        prioridad = "ALTA"
        confianza = 0.88 if score_final >= 80 else 0.84
        siguiente = "LLAMADA" if tel_ok else "CORREO"
    elif score_final >= 40:
        prioridad = "MEDIA"
        confianza = 0.82
        siguiente = "WHATSAPP" if tel_ok else ("CORREO" if email_ok else "NOTA")
    else:
        prioridad = "BAJA"
        confianza = 0.80
        siguiente = "CORREO" if email_ok and not baja_intencion else "NOTA"

    razonamiento = (
        f"Score {score_final}/100 ({prioridad}) para lead capturado vía {fuente}; "
        f"factores principales: {', '.join(factores[:5])}. Siguiente acción sugerida: {siguiente}."
    )
    return {
        "prioridad": prioridad,
        "score": score_final,
        "score_decimal": format(score_dec, ".2f"),
        "confianza": confianza,
        "siguiente_actividad": siguiente,
        "razonamiento": razonamiento,
        "factores": factores,
        "modelo_llm": "fallback-reglas",
    }


def proponer_seguimiento_deterministico(datos_lead: dict[str, Any]) -> dict[str, Any]:
    """Propone acción y borrador de seguimiento comercial sin enviar mensajes externos."""
    anonimizado = bool(datos_lead.get("anonimizado", False))
    activo = bool(datos_lead.get("activo", True))
    etapa_tipo = str(datos_lead.get("etapa_tipo") or "ABIERTA").strip().upper()
    consentimiento = datos_lead.get("consentimiento_aceptado") is True

    if anonimizado or not activo:
        return {
            "accion": "NO_CONTACTAR",
            "canal": "NINGUNO",
            "asunto": "",
            "borrador_mensaje": "",
            "confianza": 0.98,
            "razonamiento": "Lead anonimizado o inactivo; prohibido emitir seguimiento comercial.",
            "requiere_aprobacion": False,
            "codigo_tipo_aprobacion": None,
            "modelo_llm": "fallback-reglas",
        }

    if etapa_tipo in ("GANADA", "PERDIDA"):
        return {
            "accion": "NO_CONTACTAR",
            "canal": "NINGUNO",
            "asunto": "",
            "borrador_mensaje": "",
            "confianza": 0.95,
            "razonamiento": f"Lead cerrado en etapa {etapa_tipo}; no requiere seguimiento de prospección.",
            "requiere_aprobacion": False,
            "codigo_tipo_aprobacion": None,
            "modelo_llm": "fallback-reglas",
        }

    if not consentimiento:
        return {
            "accion": "NO_CONTACTAR",
            "canal": "NINGUNO",
            "asunto": "",
            "borrador_mensaje": "",
            "confianza": 0.96,
            "razonamiento": "El lead no cuenta con consentimiento aceptado para envío externo.",
            "requiere_aprobacion": False,
            "codigo_tipo_aprobacion": None,
            "modelo_llm": "fallback-reglas",
        }

    nombre = str(datos_lead.get("nombre") or "cliente").strip() or "cliente"
    empresa_nombre = str(datos_lead.get("empresa_nombre") or "").strip()
    mensaje = str(datos_lead.get("mensaje") or "").strip()
    mensaje_norm = _normalizar_texto(mensaje)
    prioridad = str(datos_lead.get("prioridad") or "").strip().upper()
    dias_sin_contacto = max(0, _entero_seguro(datos_lead.get("dias_sin_contacto"), 0))
    vendedor = str(datos_lead.get("vendedor_nombre") or "nuestro equipo comercial").strip()

    email_ok, _ = _tiene_email_valido(datos_lead.get("email"))
    tel_ok = _tiene_telefono_valido(datos_lead.get("telefono"))

    if not email_ok and not tel_ok:
        return {
            "accion": "TAREA_INTERNA",
            "canal": "NINGUNO",
            "asunto": f"Completar datos de contacto de {nombre}",
            "borrador_mensaje": "",
            "confianza": 0.86,
            "razonamiento": "El lead tiene consentimiento pero carece de teléfono y correo válidos.",
            "requiere_aprobacion": False,
            "codigo_tipo_aprobacion": None,
            "modelo_llm": "fallback-reglas",
        }

    pide_llamada = _contiene_alguno(mensaje_norm, _KEYWORDS_LLAMADA)
    requiere_llamada_urgente = prioridad == "ALTA" and dias_sin_contacto >= 5 and tel_ok
    if tel_ok and (pide_llamada or requiere_llamada_urgente):
        ref_empresa = f" de {empresa_nombre}" if empresa_nombre else ""
        return {
            "accion": "TAREA_INTERNA",
            "canal": "LLAMADA",
            "asunto": f"Llamada de seguimiento a {nombre}{ref_empresa}",
            "borrador_mensaje": (
                f"Guion sugerido: saludar a {nombre}{ref_empresa}, retomar su solicitud "
                f"y confirmar próximos pasos con {vendedor}."
            ),
            "confianza": 0.85,
            "razonamiento": (
                "Se recomienda llamada directa interna por solicitud explícita o alta prioridad sin respuesta."
            ),
            "requiere_aprobacion": False,
            "codigo_tipo_aprobacion": None,
            "modelo_llm": "fallback-reglas",
        }

    prefiere_email = email_ok and (not tel_ok or _contiene_alguno(mensaje_norm, _KEYWORDS_CORREO_FORMAL))
    ref_empresa = f" ({empresa_nombre})" if empresa_nombre else ""
    if prefiere_email:
        asunto = f"Seguimiento a tu solicitud{ref_empresa}"
        borrador = (
            f"Hola {nombre}, gracias por conectar con nosotros. "
            f"Dando seguimiento a tu consulta{ref_empresa}, quedamos atentos para compartir "
            f"la información solicitada y coordinar una breve reunión. Saludos, {vendedor}."
        )
        return {
            "accion": "ENVIO_EXTERNO",
            "canal": "EMAIL",
            "asunto": asunto,
            "borrador_mensaje": borrador,
            "confianza": 0.87,
            "razonamiento": (
                "Se propone seguimiento por correo electrónico con borrador listo para aprobación humana obligatoria."
            ),
            "requiere_aprobacion": True,
            "codigo_tipo_aprobacion": CODIGO_APROBACION_ENVIO_EXTERNO,
            "modelo_llm": "fallback-reglas",
        }

    asunto = f"Seguimiento WhatsApp — {nombre}"
    borrador = (
        f"Hola {nombre}, te saluda {vendedor}. Gracias por conectar con nosotros"
        f"{' desde ' + empresa_nombre if empresa_nombre else ''}. "
        f"¿Te gustaría que coordinemos los detalles de tu solicitud hoy?"
    )
    return {
        "accion": "ENVIO_EXTERNO",
        "canal": "WHATSAPP",
        "asunto": asunto,
        "borrador_mensaje": borrador,
        "confianza": 0.86,
        "razonamiento": (
            "El lead cuenta con teléfono y consentimiento; se redacta borrador WhatsApp sujeto a aprobación humana."
        ),
        "requiere_aprobacion": True,
        "codigo_tipo_aprobacion": CODIGO_APROBACION_ENVIO_EXTERNO,
        "modelo_llm": "fallback-reglas",
    }


def _config_permite_llm(empresa, agente_id: str) -> bool:
    from .models import ConfigAgente  # noqa: PLC0415

    cfg = ConfigAgente.objects.filter(id_empresa=empresa, agente=agente_id).first()
    if cfg is None:
        return False
    if not cfg.activo:
        return False
    extra = cfg.config_extra if isinstance(cfg.config_extra, dict) else {}
    return bool(extra.get("usar_llm", False))


def _verificar_agente_activo(empresa, agente_id: str) -> None:
    from .models import ConfigAgente  # noqa: PLC0415
    from .services import AgenteError  # noqa: PLC0415

    cfg = ConfigAgente.objects.filter(id_empresa=empresa, agente=agente_id).first()
    if cfg is not None and not cfg.activo:
        raise AgenteError(f"El agente '{agente_id}' está desactivado para esta empresa.")


def _extraer_datos_lead(empresa, lead) -> dict[str, Any]:
    from apps.connect.models import Toque  # noqa: PLC0415
    from apps.crm.models import Actividad  # noqa: PLC0415

    ahora = timezone.now()
    dias_captura = max(0, (ahora - lead.fecha_creacion).days) if lead.fecha_creacion else 0
    ultima_act = (
        Actividad.objects.filter(id_empresa=empresa, lead=lead)
        .order_by("-fecha_creacion")
        .values_list("fecha_creacion", flat=True)
        .first()
    )
    ref_contacto = ultima_act or lead.fecha_creacion or ahora
    dias_sin_contacto = max(0, (ahora - ref_contacto).days)

    total_toques = Toque.objects.filter(id_empresa=empresa, perfil_id=lead.perfil_id).count() if lead.perfil_id else 0
    total_actividades = Actividad.objects.filter(id_empresa=empresa, lead=lead).count()
    vendedor_nombre = ""
    if lead.perfil_id and lead.perfil:
        vendedor_nombre = lead.perfil.nombre_publico
    elif lead.propietario_id and lead.propietario:
        vendedor_nombre = getattr(lead.propietario, "username", "") or ""

    return {
        "nombre": lead.nombre,
        "apellido": lead.apellido,
        "empresa_nombre": lead.empresa_nombre,
        "cargo": "",
        "email": lead.email,
        "telefono": lead.telefono,
        "mensaje": lead.mensaje,
        "fuente": lead.fuente,
        "etapa_tipo": lead.etapa.tipo if lead.etapa_id and lead.etapa else "ABIERTA",
        "etapa_nombre": lead.etapa.nombre if lead.etapa_id and lead.etapa else "",
        "consentimiento_aceptado": bool(lead.consentimiento_aceptado),
        "anonimizado": bool(lead.anonimizado),
        "activo": bool(lead.activo),
        "dias_desde_captura": dias_captura,
        "dias_sin_contacto": dias_sin_contacto,
        "total_toques": total_toques,
        "total_actividades": total_actividades,
        "tiene_contacto_previo": lead.contacto_id is not None,
        "vendedor_nombre": vendedor_nombre,
    }


def _refinar_calificador_con_llm(empresa, datos_lead: dict[str, Any], base: dict[str, Any], gateway) -> dict[str, Any]:
    prompt = json.dumps(
        {
            "fuente": datos_lead["fuente"],
            "empresa_nombre": datos_lead["empresa_nombre"],
            "tiene_email": bool(datos_lead["email"]),
            "tiene_telefono": bool(datos_lead["telefono"]),
            "mensaje": datos_lead["mensaje"][:500],
            "dias_desde_captura": datos_lead["dias_desde_captura"],
            "total_toques": datos_lead["total_toques"],
            "score_base": base["score"],
        },
        ensure_ascii=False,
    )
    try:
        resp = gateway.generate(
            prompt=prompt,
            system=_SYSTEM_PROMPT_CALIFICADOR,
            max_tokens=300,
            uso=llm_gateway.USO_AGENTE,
            empresa=empresa,
        )
        parsed = json.loads(resp.text.strip())
        prioridad = str(parsed.get("prioridad", base["prioridad"])).strip().upper()
        if prioridad not in _PRIORIDADES_VALIDAS:
            prioridad = base["prioridad"]
        score_raw = _entero_seguro(parsed.get("score"), base["score"])
        score_final = max(0, min(100, score_raw))
        conf_raw = float(parsed.get("confianza", base["confianza"]))
        conf_final = max(0.0, min(1.0, conf_raw))
        siguiente = str(parsed.get("siguiente_actividad", base["siguiente_actividad"])).strip().upper()
        if siguiente not in _ACTIVIDADES_VALIDAS:
            siguiente = base["siguiente_actividad"]
        razon = (str(parsed.get("razonamiento", base["razonamiento"])).strip() or base["razonamiento"])[:1000]
        return {
            **base,
            "prioridad": prioridad,
            "score": score_final,
            "score_decimal": format(Decimal(score_final).quantize(Decimal("0.01")), ".2f"),
            "confianza": conf_final,
            "siguiente_actividad": siguiente,
            "razonamiento": razon,
            "modelo_llm": str(resp.model or "llm"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("connect_calificador LLM falló, usando fallback determinístico: %s", type(exc).__name__)
        return {
            **base,
            "modelo_llm": f"fallback-error:{llm_gateway.nombre_error(exc)}",
        }


def _refinar_seguimiento_con_llm(empresa, datos_lead: dict[str, Any], base: dict[str, Any], gateway) -> dict[str, Any]:
    if base["accion"] == "NO_CONTACTAR":
        # Guardrail legal inviolable: el LLM nunca puede anular NO_CONTACTAR.
        return base
    prompt = json.dumps(
        {
            "nombre": datos_lead["nombre"],
            "empresa_nombre": datos_lead["empresa_nombre"],
            "canal": base["canal"],
            "accion": base["accion"],
            "mensaje_lead": datos_lead["mensaje"][:500],
            "vendedor": datos_lead["vendedor_nombre"],
        },
        ensure_ascii=False,
    )
    try:
        resp = gateway.generate(
            prompt=prompt,
            system=_SYSTEM_PROMPT_SEGUIMIENTO,
            max_tokens=350,
            uso=llm_gateway.USO_AGENTE,
            empresa=empresa,
        )
        parsed = json.loads(resp.text.strip())
        asunto = str(parsed.get("asunto", base["asunto"])).strip()[:200] or base["asunto"]
        borrador = (
            str(parsed.get("borrador_mensaje", base["borrador_mensaje"])).strip()[:1500] or base["borrador_mensaje"]
        )
        razon = str(parsed.get("razonamiento", base["razonamiento"])).strip() or base["razonamiento"]
        return {
            **base,
            "asunto": asunto,
            "borrador_mensaje": borrador,
            "razonamiento": razon,
            "modelo_llm": str(resp.model or "llm"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("connect_seguimiento LLM falló, usando fallback determinístico: %s", type(exc).__name__)
        return {
            **base,
            "modelo_llm": f"fallback-error:{llm_gateway.nombre_error(exc)}",
        }


def _crear_solicitud_aprobacion_envio_externo(*, empresa, prediccion, solicitante, lead, propuesta: dict[str, Any]):
    """Crea obligatoriamente la ``SolicitudAprobacion`` PENDIENTE (``CONNECT_ENVIO_EXTERNO``)."""
    from apps.gestion_aprobaciones.models import FlujoAprobacion, SolicitudAprobacion, TipoAprobacion  # noqa: PLC0415
    from apps.gestion_aprobaciones.services import PENDIENTE, crear_solicitud  # noqa: PLC0415

    tipo_aprob, _ = TipoAprobacion.objects.get_or_create(
        id_empresa=empresa,
        codigo_tipo=CODIGO_APROBACION_ENVIO_EXTERNO,
        defaults={
            "nombre_tipo": "Envío externo Omni Connect",
            "descripcion": "Aprobación humana obligatoria antes de enviar mensajes externos sugeridos por IA.",
            "modulo_origen": MODULO_ORIGEN_CONNECT,
            "activo": True,
        },
    )
    if not tipo_aprob.activo or tipo_aprob.modulo_origen != MODULO_ORIGEN_CONNECT:
        tipo_aprob.activo = True
        tipo_aprob.modulo_origen = MODULO_ORIGEN_CONNECT
        tipo_aprob.save(update_fields=["activo", "modulo_origen"])

    primera_etapa = (
        FlujoAprobacion.objects.filter(id_tipo_aprobacion=tipo_aprob, activo=True).order_by("orden_etapa").first()
    )
    if primera_etapa is None:
        primera_etapa = FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo_aprob,
            orden_etapa=1,
            nombre_etapa="Revisión humana de envío Connect",
            activo=True,
        )

    solicitud = crear_solicitud(
        prediccion,
        empresa,
        solicitante,
        CODIGO_APROBACION_ENVIO_EXTERNO,
        Decimal("0.00"),
    )
    if solicitud is None:
        # Invariante ADR-014: incluso si el flujo tiene rangos de monto personalizados,
        # el envío externo de Connect SIEMPRE queda retenido en estado PENDIENTE.
        solicitud = SolicitudAprobacion.objects.create(
            id_tipo_aprobacion=tipo_aprob,
            id_entidad_origen=prediccion.pk,
            nombre_modelo_origen=MODELO_ORIGEN_PREDICCION,
            id_usuario_solicitante=solicitante,
            estado_solicitud=PENDIENTE,
            etapa_actual_flujo=primera_etapa,
            monto=Decimal("0.00"),
            fecha_inicio_etapa=timezone.now(),
        )

    resumen_comentario = (
        f"Propuesta {propuesta['canal']} para lead {lead} (ID {lead.id_lead}): {propuesta['asunto']}"
    )[:500]
    solicitud.comentarios_solicitante = resumen_comentario
    solicitud.save(update_fields=["comentarios_solicitante"])
    return solicitud


@transaction.atomic
def ejecutar_connect_calificador(
    empresa,
    lead_id: uuid.UUID | str,
    usuario=None,
    *,
    gateway=None,
) -> dict[str, Any]:
    """Ejecuta ``connect_calificador`` sobre un ``Lead`` del tenant y persiste ``PrediccionAgente``."""
    from apps.crm.models import Lead  # noqa: PLC0415

    from .models import PrediccionAgente  # noqa: PLC0415
    from .services import AgenteError  # noqa: PLC0415

    _verificar_agente_activo(empresa, AGENTE_CALIFICADOR_ID)

    try:
        lead_uuid = lead_id if isinstance(lead_id, uuid.UUID) else uuid.UUID(str(lead_id))
    except (ValueError, TypeError) as exc:
        raise AgenteError("Identificador de lead inválido.") from exc

    lead = (
        Lead.objects.select_related("etapa", "pipeline", "perfil", "propietario", "contacto")
        .filter(pk=lead_uuid, id_empresa=empresa)
        .first()
    )
    if lead is None:
        raise AgenteError("Lead no encontrado en la empresa.")

    t0 = time.perf_counter()
    datos_lead = _extract_y_calificar(empresa, lead, gateway=gateway)
    latencia_ms = int((time.perf_counter() - t0) * 1000)

    prediccion = PrediccionAgente(
        id_empresa=empresa,
        agente=AGENTE_CALIFICADOR_ID,
        input_texto=f"Lead {lead} | fuente={lead.fuente} | empresa={lead.empresa_nombre or '-'}",
        input_monto=Decimal(datos_lead["score_decimal"]),
        input_metadata={
            "lead_id": str(lead.id_lead),
            "fuente": lead.fuente,
            "score": datos_lead["score"],
            "prioridad": datos_lead["prioridad"],
            "siguiente_actividad": datos_lead["siguiente_actividad"],
            "factores": datos_lead["factores"],
            "solicitado_por": str(usuario.pk) if usuario is not None and getattr(usuario, "pk", None) else None,
        },
        categoria_predicha=datos_lead["prioridad"],
        confianza=float(datos_lead["confianza"]),
        razonamiento=datos_lead["razonamiento"],
        alternativas=[{"siguiente_actividad": datos_lead["siguiente_actividad"], "score": datos_lead["score"]}],
        modelo_llm=datos_lead["modelo_llm"],
        latencia_ms=latencia_ms,
    )
    prediccion.full_clean()
    prediccion.save()

    logger.info(
        "connect_calificador | empresa=%s | lead=%s | prioridad=%s | score=%d | prediccion=%s",
        empresa.pk,
        lead.id_lead,
        datos_lead["prioridad"],
        datos_lead["score"],
        prediccion.pk,
    )
    return {
        "prediccion_id": str(prediccion.pk),
        "lead_id": str(lead.id_lead),
        "agente": AGENTE_CALIFICADOR_ID,
        "prioridad": datos_lead["prioridad"],
        "score": datos_lead["score"],
        "score_decimal": datos_lead["score_decimal"],
        "confianza": float(datos_lead["confianza"]),
        "siguiente_actividad": datos_lead["siguiente_actividad"],
        "razonamiento": datos_lead["razonamiento"],
        "factores": datos_lead["factores"],
        "modelo_llm": datos_lead["modelo_llm"],
        "latencia_ms": latencia_ms,
    }


def _extract_y_calificar(empresa, lead, *, gateway=None) -> dict[str, Any]:
    datos_lead = _extraer_datos_lead(empresa, lead)
    resultado = calificar_lead_deterministico(datos_lead)
    usar_llm = _config_permite_llm(empresa, AGENTE_CALIFICADOR_ID) or gateway is not None
    if usar_llm and not datos_lead["anonimizado"] and datos_lead["activo"]:
        gw = gateway if gateway is not None else llm_gateway.get_gateway()
        if gw.disponible():
            resultado = _refinar_calificador_con_llm(empresa, datos_lead, resultado, gw)
    return resultado


@transaction.atomic
def ejecutar_connect_seguimiento(
    empresa,
    lead_id: uuid.UUID | str,
    usuario=None,
    *,
    gateway=None,
) -> dict[str, Any]:
    """Ejecuta ``connect_seguimiento`` y exige ``SolicitudAprobacion`` para todo envío externo."""
    from apps.core.models import Usuarios  # noqa: PLC0415
    from apps.crm.models import Lead  # noqa: PLC0415

    from .models import PrediccionAgente  # noqa: PLC0415
    from .services import AgenteError  # noqa: PLC0415

    _verificar_agente_activo(empresa, AGENTE_SEGUIMIENTO_ID)

    try:
        lead_uuid = lead_id if isinstance(lead_id, uuid.UUID) else uuid.UUID(str(lead_id))
    except (ValueError, TypeError) as exc:
        raise AgenteError("Identificador de lead inválido.") from exc

    lead = (
        Lead.objects.select_related("etapa", "pipeline", "perfil", "propietario", "contacto")
        .filter(pk=lead_uuid, id_empresa=empresa)
        .first()
    )
    if lead is None:
        raise AgenteError("Lead no encontrado en la empresa.")

    solicitante = usuario if isinstance(usuario, Usuarios) else lead.propietario
    if solicitante is None:
        raise AgenteError("No se pudo determinar un usuario solicitante válido para la aprobación.")

    t0 = time.perf_counter()
    datos_lead = _extraer_datos_lead(empresa, lead)
    calif = calificar_lead_deterministico(datos_lead)
    datos_lead["prioridad"] = calif["prioridad"]
    propuesta = proponer_seguimiento_deterministico(datos_lead)

    usar_llm = _config_permite_llm(empresa, AGENTE_SEGUIMIENTO_ID) or gateway is not None
    if usar_llm and propuesta["accion"] != "NO_CONTACTAR":
        gw = gateway if gateway is not None else llm_gateway.get_gateway()
        if gw.disponible():
            propuesta = _refinar_seguimiento_con_llm(empresa, datos_lead, propuesta, gw)

    latencia_ms = int((time.perf_counter() - t0) * 1000)

    categoria = f"{propuesta['accion']}:{propuesta['canal']}"
    prediccion = PrediccionAgente(
        id_empresa=empresa,
        agente=AGENTE_SEGUIMIENTO_ID,
        input_texto=f"Seguimiento Lead {lead} | etapa={datos_lead['etapa_nombre'] or datos_lead['etapa_tipo']}",
        input_metadata={
            "lead_id": str(lead.id_lead),
            "accion": propuesta["accion"],
            "canal": propuesta["canal"],
            "asunto": propuesta["asunto"],
            "borrador_mensaje": propuesta["borrador_mensaje"],
            "requiere_aprobacion": bool(propuesta["requiere_aprobacion"]),
            "enviado_directamente": False,
        },
        categoria_predicha=categoria,
        confianza=float(propuesta["confianza"]),
        razonamiento=propuesta["razonamiento"],
        alternativas=[
            {
                "accion": propuesta["accion"],
                "canal": propuesta["canal"],
                "asunto": propuesta["asunto"],
                "borrador_mensaje": propuesta["borrador_mensaje"],
            }
        ],
        modelo_llm=propuesta["modelo_llm"],
        latencia_ms=latencia_ms,
    )
    prediccion.full_clean()
    prediccion.save()

    solicitud_id: str | None = None
    if propuesta["accion"] == "ENVIO_EXTERNO":
        solicitud = _crear_solicitud_aprobacion_envio_externo(
            empresa=empresa,
            prediccion=prediccion,
            solicitante=solicitante,
            lead=lead,
            propuesta=propuesta,
        )
        solicitud_id = str(solicitud.pk)
        meta = dict(prediccion.input_metadata or {})
        meta["solicitud_aprobacion_id"] = solicitud_id
        meta["codigo_tipo_aprobacion"] = CODIGO_APROBACION_ENVIO_EXTERNO
        prediccion.input_metadata = meta
        prediccion.save(update_fields=["input_metadata"])

    logger.info(
        "connect_seguimiento | empresa=%s | lead=%s | accion=%s | canal=%s | aprobacion=%s",
        empresa.pk,
        lead.id_lead,
        propuesta["accion"],
        propuesta["canal"],
        solicitud_id or "none",
    )
    return {
        "prediccion_id": str(prediccion.pk),
        "lead_id": str(lead.id_lead),
        "agente": AGENTE_SEGUIMIENTO_ID,
        "accion": propuesta["accion"],
        "canal": propuesta["canal"],
        "asunto": propuesta["asunto"],
        "borrador_mensaje": propuesta["borrador_mensaje"],
        "confianza": float(propuesta["confianza"]),
        "razonamiento": propuesta["razonamiento"],
        "requiere_aprobacion": propuesta["accion"] == "ENVIO_EXTERNO",
        "codigo_tipo_aprobacion": CODIGO_APROBACION_ENVIO_EXTERNO if propuesta["accion"] == "ENVIO_EXTERNO" else None,
        "solicitud_aprobacion_id": solicitud_id,
        "enviado_directamente": False,
        "modelo_llm": propuesta["modelo_llm"],
        "latencia_ms": latencia_ms,
    }
