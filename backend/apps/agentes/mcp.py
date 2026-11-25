"""Herramientas MCP de ``apps/agentes`` — Ejecución asíncrona de agentes IA (R-CODE-7 / P2-2)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
import logging
import re
from typing import Any
import uuid

from apps.core.exceptions import sanitize_mcp_error

logger = logging.getLogger("omni.mcp.agentes")

_SCOPE = "agentes"
_FECHA_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def _parse_uuid(valor: str, campo: str) -> uuid.UUID:
    raw = str(valor)
    if "\x00" in raw:
        raise ValueError(f"{campo} inválido.")
    return uuid.UUID(raw.strip())


def _parse_fecha(valor: str | None, campo: str) -> date | None:
    if valor is None:
        return None
    raw = str(valor)
    if "\x00" in raw:
        raise ValueError(f"{campo} inválido.")
    limpio = raw.strip()
    if not limpio:
        return None
    if not _FECHA_ISO_RE.match(limpio):
        raise ValueError(f"Formato de fecha inválido para '{campo}'. Use YYYY-MM-DD.")
    try:
        return date.fromisoformat(limpio)
    except ValueError as exc:
        raise ValueError(f"Fecha inválida para '{campo}'.") from exc


def agentes_disparar_analisis(
    capability_token: str,
    empresa_id: str,
    agente: str,
    persistir: bool = False,
    solo_alertas: bool = True,
    gasto_id: str | None = None,
    aplicar: bool = False,
    lead_id: str | None = None,
) -> dict[str, Any]:
    """
    Encola de forma asíncrona en Celery la ejecución de un agente IA para la empresa.

    Agentes soportados: ``cobranza_estratega``, ``reorden_sugeridor``,
    ``personalizacion_capa2``, ``clasificador_gastos``, ``connect_calificador``,
    ``connect_seguimiento``.

    Scope requerido: ``agentes:write``
    """
    from apps.agentes.services import (  # noqa: PLC0415
        AGENTES_VALIDOS,
        AgenteError,
        encolar_ejecucion_agente,
        serializar_ejecucion_dict,
    )
    from apps.core.models import Empresa  # noqa: PLC0415
    from apps.crm.models import Lead  # noqa: PLC0415
    from apps.gastos.models import Gasto  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=empresa_id) as ctx:
        if "\x00" in str(agente or ""):
            return {"error": "Parámetro agente inválido."}
        agente_clean = str(agente or "").strip()
        if agente_clean not in AGENTES_VALIDOS:
            return {"error": f"Agente no soportado: {agente_clean}"}

        empresa_uuid = uuid.UUID(str(ctx["empresa_id"]))
        empresa = Empresa.objects.filter(pk=empresa_uuid, activo=True).first()
        if empresa is None:
            return {"error": "Empresa inactiva o no encontrada."}

        parametros: dict[str, Any] = {}
        if agente_clean == "cobranza_estratega":
            parametros = {"persistir": bool(persistir)}
        elif agente_clean == "reorden_sugeridor":
            parametros = {
                "solo_alertas": bool(solo_alertas),
                "persistir": bool(persistir),
            }
        elif agente_clean == "clasificador_gastos":
            if not gasto_id:
                return {"error": "Se requiere gasto_id para clasificador_gastos."}
            try:
                gasto_uuid = _parse_uuid(gasto_id, "gasto_id")
            except (ValueError, TypeError):
                return {"error": "gasto_id no es un UUID válido."}
            if not Gasto.objects.filter(pk=gasto_uuid, id_empresa=empresa).exists():
                return {"error": "Gasto no encontrado en la empresa."}
            parametros = {"gasto_id": str(gasto_uuid), "aplicar": bool(aplicar)}
        elif agente_clean in ("connect_calificador", "connect_seguimiento"):
            if not lead_id:
                return {"error": f"Se requiere lead_id para {agente_clean}."}
            try:
                lead_uuid = _parse_uuid(lead_id, "lead_id")
            except (ValueError, TypeError):
                return {"error": "lead_id no es un UUID válido."}
            if not Lead.objects.filter(pk=lead_uuid, id_empresa=empresa).exists():
                return {"error": "Lead no encontrado en la empresa."}
            parametros = {"lead_id": str(lead_uuid)}

        try:
            ejecucion = encolar_ejecucion_agente(
                empresa=empresa,
                agente=agente_clean,
                parametros=parametros,
                iniciado_por=None,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="agentes_disparar_analisis",
                    controlled_types=(AgenteError,),
                    default_message="No se pudo encolar el análisis del agente.",
                )
            }

        logger.info(
            "agentes_disparar_analisis | actor=%s | tenant=%s | agente=%s | ejecucion=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            agente_clean,
            ejecucion.pk,
        )
        return serializar_ejecucion_dict(ejecucion)


def agentes_obtener_ejecucion(
    capability_token: str,
    empresa_id: str,
    ejecucion_id: str,
) -> dict[str, Any]:
    """
    Consulta el estado y resultado de una ``EjecucionAgente`` perteneciente a la empresa.

    Scope requerido: ``agentes:read``
    """
    from apps.agentes.models import EjecucionAgente  # noqa: PLC0415
    from apps.agentes.services import serializar_ejecucion_dict  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        try:
            ej_uuid = _parse_uuid(ejecucion_id, "ejecucion_id")
        except (ValueError, TypeError):
            return {"error": "ejecucion_id no es un UUID válido."}

        try:
            ejecucion = EjecucionAgente.objects.filter(
                pk=ej_uuid,
                id_empresa_id=ctx["empresa_id"],
            ).first()
        except Exception as exc:  # noqa: BLE001
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="agentes_obtener_ejecucion",
                )
            }

        if ejecucion is None:
            return {"error": "Ejecución no encontrada en la empresa."}

        logger.info(
            "agentes_obtener_ejecucion | actor=%s | tenant=%s | ejecucion=%s | estado=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            ejecucion.pk,
            ejecucion.estado,
        )
        return serializar_ejecucion_dict(ejecucion)


def agentes_listar_ejecuciones(
    capability_token: str,
    empresa_id: str,
    agente: str | None = None,
    estado: str | None = None,
    limite: int = 20,
) -> dict[str, Any]:
    """
    Lista las ejecuciones recientes de agentes IA de la empresa con filtros opcionales.

    Scope requerido: ``agentes:read``
    """
    from apps.agentes.models import EjecucionAgente  # noqa: PLC0415
    from apps.agentes.services import serializar_ejecucion_dict  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        if (agente and "\x00" in agente) or (estado and "\x00" in estado):
            return {"error": "Parámetro de filtro inválido."}
        if isinstance(limite, bool):
            return {"error": "El parámetro limite debe ser un entero válido."}
        try:
            tope = max(1, min(int(limite), 100))
        except (ValueError, TypeError):
            return {"error": "El parámetro limite debe ser un entero válido."}

        try:
            qs = EjecucionAgente.objects.filter(id_empresa_id=ctx["empresa_id"])
            if agente:
                qs = qs.filter(agente=agente.strip())
            if estado:
                qs = qs.filter(estado=estado.strip())
            items = list(qs.order_by("-fecha_creacion")[:tope])
        except Exception as exc:  # noqa: BLE001
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="agentes_listar_ejecuciones",
                )
            }

        logger.info(
            "agentes_listar_ejecuciones | actor=%s | tenant=%s | total=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(items),
        )
        return {
            "ejecuciones": [serializar_ejecucion_dict(e) for e in items],
            "total": len(items),
        }


def agentes_resumen_consumo_llm(
    capability_token: str,
    empresa_id: str,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    modelo: str | None = None,
    uso: str | None = None,
) -> dict[str, Any]:
    """
    Consulta el resumen agregado de consumo de tokens y costo estimado USD LLM de la empresa.

    Scope requerido: ``agentes:read``
    """
    from apps.agentes.models import ConsumoLLM  # noqa: PLC0415
    from apps.agentes.services import calcular_resumen_consumo_llm  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        try:
            empresa_uuid = _parse_uuid(str(ctx["empresa_id"]), "empresa_id")
            f_desde = _parse_fecha(fecha_desde, "fecha_desde")
            f_hasta = _parse_fecha(fecha_hasta, "fecha_hasta")
        except (ValueError, TypeError) as exc:
            return {"error": str(exc)}

        if f_desde is not None and f_hasta is not None and f_desde > f_hasta:
            return {"error": "'fecha_desde' no puede ser posterior a 'fecha_hasta'."}
        if (modelo and "\x00" in str(modelo)) or (uso and "\x00" in str(uso)):
            return {"error": "Parámetro de filtro inválido."}

        try:
            qs = ConsumoLLM.objects.filter(
                id_empresa__isnull=False,
                id_empresa_id=empresa_uuid,
            )
            if f_desde is not None:
                qs = qs.filter(creado_en__date__gte=f_desde)
            if f_hasta is not None:
                qs = qs.filter(creado_en__date__lte=f_hasta)
            if modelo and str(modelo).strip():
                qs = qs.filter(modelo=str(modelo).strip())
            if uso and str(uso).strip():
                qs = qs.filter(uso=str(uso).strip())
            resumen = calcular_resumen_consumo_llm(qs)
        except Exception as exc:  # noqa: BLE001
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="agentes_resumen_consumo_llm",
                )
            }

        logger.info(
            "agentes_resumen_consumo_llm | actor=%s | tenant=%s | llamadas=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            resumen["llamadas"],
        )
        return resumen


def agentes_calificar_lead_connect(
    capability_token: str,
    empresa_id: str,
    lead_id: str,
) -> dict[str, Any]:
    """Califica un lead de Omni Connect (prioridad, score y siguiente actividad) y persiste ``PrediccionAgente``.

    Scope requerido: ``agentes:write``
    """
    from apps.agentes.connect_agents import ejecutar_connect_calificador  # noqa: PLC0415
    from apps.agentes.services import AgenteError  # noqa: PLC0415
    from apps.core.models import CapabilityToken, Empresa  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=empresa_id) as ctx:
        try:
            lead_uuid = _parse_uuid(lead_id, "lead_id")
        except (ValueError, TypeError):
            return {"error": "lead_id no es un UUID válido."}

        empresa_uuid = uuid.UUID(str(ctx["empresa_id"]))
        empresa = Empresa.objects.filter(pk=empresa_uuid, activo=True).first()
        if empresa is None:
            return {"error": "Empresa inactiva o no encontrada."}

        token_obj = (
            CapabilityToken.objects.select_related("creado_por")
            .filter(token=capability_token, empresa=empresa, activo=True)
            .first()
        )
        usuario = token_obj.creado_por if token_obj is not None else None

        try:
            res = ejecutar_connect_calificador(empresa=empresa, lead_id=lead_uuid, usuario=usuario)
        except Exception as exc:  # noqa: BLE001
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="agentes_calificar_lead_connect",
                    controlled_types=(AgenteError, ValueError),
                )
            }

        logger.info(
            "agentes_calificar_lead_connect | actor=%s | tenant=%s | lead=%s | prioridad=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            lead_uuid,
            res["prioridad"],
        )
        return res


def agentes_proponer_seguimiento_connect(
    capability_token: str,
    empresa_id: str,
    lead_id: str,
) -> dict[str, Any]:
    """Genera una propuesta de seguimiento para un lead Connect y crea ``SolicitudAprobacion`` en envíos externos.

    Nunca envía mensajes externos directamente. Scope requerido: ``agentes:write``.
    """
    from apps.agentes.connect_agents import ejecutar_connect_seguimiento  # noqa: PLC0415
    from apps.agentes.services import AgenteError  # noqa: PLC0415
    from apps.core.models import CapabilityToken, Empresa  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=empresa_id) as ctx:
        try:
            lead_uuid = _parse_uuid(lead_id, "lead_id")
        except (ValueError, TypeError):
            return {"error": "lead_id no es un UUID válido."}

        empresa_uuid = uuid.UUID(str(ctx["empresa_id"]))
        empresa = Empresa.objects.filter(pk=empresa_uuid, activo=True).first()
        if empresa is None:
            return {"error": "Empresa inactiva o no encontrada."}

        token_obj = (
            CapabilityToken.objects.select_related("creado_por")
            .filter(token=capability_token, empresa=empresa, activo=True)
            .first()
        )
        usuario = token_obj.creado_por if token_obj is not None else None

        try:
            res = ejecutar_connect_seguimiento(empresa=empresa, lead_id=lead_uuid, usuario=usuario)
        except Exception as exc:  # noqa: BLE001
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="agentes_proponer_seguimiento_connect",
                    controlled_types=(AgenteError, ValueError),
                )
            }

        logger.info(
            "agentes_proponer_seguimiento_connect | actor=%s | tenant=%s | lead=%s | accion=%s | aprob=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            lead_uuid,
            res["accion"],
            res.get("solicitud_aprobacion_id"),
        )
        return res


def agentes_listar_operativos(capability_token: str, empresa_id: str) -> dict[str, Any]:
    """Lista los 5 agentes IA operativos (COBRANZA, TESORERO, LOGISTICO, COMPRADOR, CFO_COPILOT). Scope: ``agentes:read``."""
    from apps.agentes.operativos import AGENTES_OPERATIVOS  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        return {"empresa_id": str(ctx["empresa_id"]), "agentes": list(AGENTES_OPERATIVOS.values())}


def agentes_ejecutar_operativo(
    capability_token: str,
    empresa_id: str,
    agente: str,
    persistir: bool = True,
    limite: int = 25,
) -> dict[str, Any]:
    """Ejecuta un agente IA operativo para la empresa vía ``llm_gateway`` con fallback determinista. Scope: ``agentes:write``."""
    from apps.agentes.operativos import AGENTES_OPERATIVOS, ejecutar_agente_operativo  # noqa: PLC0415
    from apps.agentes.services import AgenteError  # noqa: PLC0415
    from apps.core.models import CapabilityToken, Empresa  # noqa: PLC0415

    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=empresa_id) as ctx:
        codigo = str(agente or "").strip().upper()
        if "\x00" in codigo or codigo not in AGENTES_OPERATIVOS:
            return {"error": f"Agente operativo no soportado: {codigo}"}
        empresa_uuid = uuid.UUID(str(ctx["empresa_id"]))
        empresa = Empresa.objects.filter(pk=empresa_uuid, activo=True).first()
        if empresa is None:
            return {"error": "Empresa inactiva o no encontrada."}
        token_obj = (
            CapabilityToken.objects.select_related("creado_por")
            .filter(token=capability_token, empresa=empresa, activo=True)
            .first()
        )
        usuario = token_obj.creado_por if token_obj is not None else None
        try:
            return ejecutar_agente_operativo(
                empresa,
                codigo,
                usuario=usuario,
                persistir=bool(persistir),
                limite=int(limite),
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="agentes_ejecutar_operativo",
                    controlled_types=(AgenteError, ValueError),
                )
            }


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": agentes_disparar_analisis,
        "name": "agentes_disparar_analisis",
        "scope": f"{_SCOPE}:write",
    },
    {
        "fn": agentes_obtener_ejecucion,
        "name": "agentes_obtener_ejecucion",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": agentes_listar_ejecuciones,
        "name": "agentes_listar_ejecuciones",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": agentes_resumen_consumo_llm,
        "name": "agentes_resumen_consumo_llm",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": agentes_calificar_lead_connect,
        "name": "agentes_calificar_lead_connect",
        "scope": f"{_SCOPE}:write",
    },
    {
        "fn": agentes_proponer_seguimiento_connect,
        "name": "agentes_proponer_seguimiento_connect",
        "scope": f"{_SCOPE}:write",
    },
    {
        "fn": agentes_listar_operativos,
        "name": "agentes_listar_operativos",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": agentes_ejecutar_operativo,
        "name": "agentes_ejecutar_operativo",
        "scope": f"{_SCOPE}:write",
    },
]
