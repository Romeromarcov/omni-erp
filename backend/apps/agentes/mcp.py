"""Herramientas MCP de ``apps/agentes`` — Ejecución asíncrona de agentes IA (R-CODE-7 / P2-2)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import logging
from typing import Any
import uuid

from apps.core.exceptions import sanitize_mcp_error

logger = logging.getLogger("omni.mcp.agentes")

_SCOPE = "agentes"


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


def agentes_disparar_analisis(
    capability_token: str,
    empresa_id: str,
    agente: str,
    persistir: bool = False,
    solo_alertas: bool = True,
    gasto_id: str | None = None,
    aplicar: bool = False,
) -> dict[str, Any]:
    """
    Encola de forma asíncrona en Celery la ejecución de un agente IA para la empresa.

    Agentes soportados: ``cobranza_estratega``, ``reorden_sugeridor``,
    ``personalizacion_capa2``, ``clasificador_gastos``.

    Scope requerido: ``agentes:write``
    """
    from apps.agentes.services import (  # noqa: PLC0415
        AGENTES_VALIDOS,
        AgenteError,
        encolar_ejecucion_agente,
        serializar_ejecucion_dict,
    )
    from apps.core.models import Empresa  # noqa: PLC0415
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
]
