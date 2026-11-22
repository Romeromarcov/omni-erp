"""
MCP Server del Integration Hub (R-CODE-7).

Expone capacidades para que los agentes de IA puedan:
- Listar y gestionar conectores
- Disparar sincronizaciones (inbound, outbound, bidireccional)
- Disparar push outbound de cobranza (pagos y gestiones_cobranza)
- Consultar estado de sincronizaciones
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError

from apps.core.exceptions import sanitize_mcp_error

logger = logging.getLogger(__name__)

_SCOPE = "integration_hub"

_ENTIDADES_VALIDAS = frozenset(
    {
        "contactos",
        "productos",
        "pedidos_venta",
        "pedidos_compra",
        "facturas_venta",
        "facturas_compra",
        "pagos",
        "gestiones_cobranza",
        "inventario",
    }
)
_DIRECCIONES_VALIDAS = frozenset({"inbound", "outbound", "bidireccional"})

# Registro declarativo de capacidades MCP (legacy + paridad REST/MCP).
MCP_CAPABILITIES = [
    {
        "name": "integration_hub.listar_conectores",
        "description": (
            "Lista todos los conectores de integración configurados para la empresa actual. "
            "Retorna nombre, proveedor, estado y último sync."
        ),
        "requires_capabilities": ["integration_hub:read"],
    },
    {
        "name": "integration_hub.test_conector",
        "description": (
            "Prueba la conexión de un conector específico con el sistema externo. " "Requiere el ID del conector."
        ),
        "requires_capabilities": ["integration_hub:read"],
    },
    {
        "name": "integration_hub.sincronizar",
        "description": (
            "Dispara una sincronización de datos (inbound, outbound o bidireccional) "
            "para una entidad específica (contactos, productos, pagos, gestiones_cobranza, etc.)."
        ),
        "requires_capabilities": ["integration_hub:write"],
    },
    {
        "name": "integration_hub.push_cobranza",
        "description": (
            "Dispara un push outbound de cobranza (pagos y/o gestiones_cobranza) hacia el sistema "
            "externo cuando push_habilitado=True."
        ),
        "requires_capabilities": ["integration_hub:write"],
    },
    {
        "name": "integration_hub.estado_sync",
        "description": (
            "Consulta el estado de las sincronizaciones recientes: "
            "jobs completados, en progreso, fallidos y métricas."
        ),
        "requires_capabilities": ["integration_hub:read"],
    },
    {
        "name": "integration_hub.preview_datos",
        "description": (
            "Previsualiza los primeros registros que se recibirían al sincronizar "
            "una entidad de un conector sin ejecutar la sincronización real."
        ),
        "requires_capabilities": ["integration_hub:read"],
    },
    {
        "name": "integration_hub.listar_outbox",
        "description": (
            "Lista los eventos de la cola Outbox multi-tenant del Integration Hub, "
            "filtrables por estado y tipo_evento."
        ),
        "requires_capabilities": ["integration_hub:read"],
    },
    {
        "name": "integration_hub.reintentar_outbox",
        "description": "Reencola un evento Outbox en estado FALLIDO o DLQ para un nuevo intento de despacho.",
        "requires_capabilities": ["integration_hub:write"],
    },
]


@contextmanager
def _ctx(capability_token: str, scope: str, *, empresa_id: str | None = None) -> Iterator[dict[str, Any]]:
    from apps.core.mcp_server import mcp_tenant_context  # noqa: PLC0415

    with mcp_tenant_context(capability_token, scope, empresa_id=empresa_id) as context:
        yield context


def listar_conectores(empresa_id: str) -> list[dict[str, Any]]:
    """
    Lista conectores activos de la empresa.
    Capacidad MCP: integration_hub.listar_conectores
    """
    from apps.integration_hub.models import ConectorInstancia

    conectores = ConectorInstancia.objects.filter(
        id_empresa=empresa_id,
        activo=True,
    ).select_related("id_proveedor")

    return [
        {
            "id": str(c.id_conector),
            "nombre": c.nombre,
            "proveedor": c.id_proveedor.nombre,
            "estado": c.estado,
            "ultimo_sync": str(c.ultimo_sync) if c.ultimo_sync else None,
            "entidades_activas": c.entidades_activas,
            "push_habilitado": bool(c.get_config().get("push_habilitado", False)),
        }
        for c in conectores
    ]


def _parse_uuid(raw: object) -> uuid.UUID | None:
    if not raw or isinstance(raw, bool):
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except (ValueError, TypeError, AttributeError):
        return None


def test_conector(empresa_id: str, conector_id: str) -> dict[str, Any]:
    """
    Prueba la conexión de un conector.
    Capacidad MCP: integration_hub.test_conector
    """
    from apps.integration_hub.connectors.registry import registry
    from apps.integration_hub.models import ConectorInstancia

    empresa_uuid = _parse_uuid(empresa_id)
    if empresa_uuid is None:
        return {"success": False, "message": f"empresa_id inválido: '{empresa_id}'."}
    conector_uuid = _parse_uuid(conector_id)
    if conector_uuid is None:
        return {"success": False, "message": f"conector_id inválido: '{conector_id}'."}

    try:
        instancia = ConectorInstancia.objects.get(
            pk=conector_uuid,
            id_empresa=empresa_uuid,
            activo=True,
        )
    except ConectorInstancia.DoesNotExist:
        return {"success": False, "message": f"Conector {conector_id} no encontrado."}

    connector = registry.get_connector(instancia)
    resultado = connector.test_connection()

    return {
        "success": resultado.success,
        "message": resultado.message,
        "version": resultado.version,
    }


def _encolar_job_mcp(job, ok_msg: str) -> dict[str, Any]:
    from apps.integration_hub.tasks import ejecutar_job_sincronizacion

    try:
        task = ejecutar_job_sincronizacion.delay(str(job.id_job))
        job.celery_task_id = task.id
        job.save(update_fields=["celery_task_id"])
    except Exception:
        # BUG-NEW-5: si el broker Celery falla, no dejar el job "pendiente" eterno
        logger.exception("No se pudo encolar el job de sincronización %s", job.id_job)
        job.estado = "fallido"
        job.resumen_errores = ["No se pudo encolar la tarea de sincronización (procesador de tareas no disponible)."]
        job.save(update_fields=["estado", "resumen_errores"])
        return {
            "success": False,
            "job_id": str(job.id_job),
            "mensaje": "No se pudo iniciar la sincronización: el procesador de tareas no está disponible.",
        }

    return {
        "success": True,
        "job_id": str(job.id_job),
        "mensaje": ok_msg,
    }


def sincronizar(
    empresa_id: str,
    conector_id: str,
    tipo_entidad: str,
    usuario_id: str | None = None,
    direccion: str = "inbound",
    sync_completo: bool = False,
) -> dict[str, Any]:
    """
    Dispara una sincronización (inbound, outbound o bidireccional) para una entidad.
    Capacidad MCP: integration_hub.sincronizar
    """
    from apps.integration_hub.models import ConectorInstancia, JobSincronizacion

    if tipo_entidad not in _ENTIDADES_VALIDAS:
        return {"success": False, "message": f"Entidad '{tipo_entidad}' no válida."}
    if direccion not in _DIRECCIONES_VALIDAS:
        return {"success": False, "message": f"Dirección '{direccion}' no válida."}

    empresa_uuid = _parse_uuid(empresa_id)
    if empresa_uuid is None:
        return {"success": False, "message": f"empresa_id inválido: '{empresa_id}'."}
    conector_uuid = _parse_uuid(conector_id)
    if conector_uuid is None:
        return {"success": False, "message": f"conector_id inválido: '{conector_id}'."}

    try:
        instancia = ConectorInstancia.objects.get(
            pk=conector_uuid,
            id_empresa=empresa_uuid,
            activo=True,
        )
    except ConectorInstancia.DoesNotExist:
        return {"success": False, "message": f"Conector {conector_id} no encontrado."}

    if instancia.estado == "error":
        return {"success": False, "message": "La instancia está en estado de error. Pruebe la conexión primero."}

    if direccion in ("outbound", "bidireccional") and not instancia.get_config().get("push_habilitado", False):
        return {
            "success": False,
            "message": "Push outbound deshabilitado en este conector (push_habilitado=False).",
        }

    parametros: dict[str, Any] = {}
    if sync_completo:
        parametros["sync_completo"] = True

    job = JobSincronizacion.objects.create(
        id_instancia=instancia,
        tipo_entidad=tipo_entidad,
        direccion=direccion,
        estado="pendiente",
        parametros=parametros,
    )

    return _encolar_job_mcp(job, f"Sync {direccion} de '{tipo_entidad}' iniciado para '{instancia.nombre}'.")


def push_cobranza(
    empresa_id: str,
    conector_id: str,
    tipo: str = "todos",
    ids: list[str] | None = None,
    push_modo_pago: str | None = None,
) -> dict[str, Any]:
    """
    Dispara un push outbound de cobranza (pagos y/o gestiones_cobranza) para un conector.
    Capacidad MCP: integration_hub.push_cobranza
    """
    from apps.integration_hub.models import ConectorInstancia, JobSincronizacion

    if tipo not in ("pagos", "gestiones_cobranza", "todos"):
        return {"success": False, "message": f"Tipo '{tipo}' no válido. Use 'pagos', 'gestiones_cobranza' o 'todos'."}
    if push_modo_pago is not None and push_modo_pago not in ("borrador", "confirmado"):
        return {"success": False, "message": "push_modo_pago inválido. Use 'borrador' o 'confirmado'."}

    empresa_uuid = _parse_uuid(empresa_id)
    if empresa_uuid is None:
        return {"success": False, "message": f"empresa_id inválido: '{empresa_id}'."}
    conector_uuid = _parse_uuid(conector_id)
    if conector_uuid is None:
        return {"success": False, "message": f"conector_id inválido: '{conector_id}'."}

    ids_normalizados: list[str] = []
    if ids is not None:
        if not isinstance(ids, (list, tuple)):
            return {"success": False, "message": "El parámetro 'ids' debe ser una lista de UUIDs."}
        for raw_id in ids:
            parsed_id = _parse_uuid(raw_id)
            if parsed_id is None:
                return {"success": False, "message": f"ID inválido en 'ids': '{raw_id}'."}
            ids_normalizados.append(str(parsed_id))

    try:
        instancia = ConectorInstancia.objects.get(
            pk=conector_uuid,
            id_empresa=empresa_uuid,
            activo=True,
        )
    except ConectorInstancia.DoesNotExist:
        return {"success": False, "message": f"Conector {conector_id} no encontrado."}

    if instancia.estado == "error":
        return {"success": False, "message": "La instancia está en estado de error. Pruebe la conexión primero."}

    if not instancia.get_config().get("push_habilitado", False):
        return {
            "success": False,
            "message": "Push outbound deshabilitado en este conector (push_habilitado=False).",
        }

    tipos = ["pagos", "gestiones_cobranza"] if tipo == "todos" else [tipo]
    parametros: dict[str, Any] = {}
    if ids_normalizados:
        parametros["ids"] = ids_normalizados
    if push_modo_pago:
        parametros["push_modo_pago"] = push_modo_pago

    job_ids: list[str] = []
    for entidad in tipos:
        job = JobSincronizacion.objects.create(
            id_instancia=instancia,
            tipo_entidad=entidad,
            direccion="outbound",
            estado="pendiente",
            parametros=dict(parametros),
        )
        res_job = _encolar_job_mcp(job, f"Push outbound '{entidad}' iniciado para '{instancia.nombre}'.")
        if not res_job["success"]:
            return res_job
        job_ids.append(res_job["job_id"])

    return {
        "success": True,
        "job_id": job_ids[0] if job_ids else None,
        "job_ids": job_ids,
        "mensaje": f"Push outbound de cobranza iniciado ({', '.join(tipos)}).",
    }


def estado_sync(empresa_id: str) -> dict[str, Any]:
    """
    Retorna el estado de sincronización de la empresa.
    Capacidad MCP: integration_hub.estado_sync
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.integration_hub.models import ConectorInstancia, JobSincronizacion

    hace_24h = timezone.now() - timedelta(hours=24)
    jobs = JobSincronizacion.objects.filter(
        id_instancia__id_empresa=empresa_id,
        iniciado_en__gte=hace_24h,
    )

    return {
        "ultima_24h": {
            "total": jobs.count(),
            "completados": jobs.filter(estado="completado").count(),
            "con_errores": jobs.filter(estado="completado_con_errores").count(),
            "fallidos": jobs.filter(estado="fallido").count(),
            "en_progreso": jobs.filter(estado__in=["pendiente", "en_progreso"]).count(),
        },
        "conectores_activos": ConectorInstancia.objects.filter(
            id_empresa=empresa_id, estado="activo", activo=True
        ).count(),
    }


# ── Tools FastMCP con CapabilityToken + RLS (R-CODE-7) ────────────────────────


def integration_hub_listar_conectores(
    capability_token: str,
    empresa_id: str,
) -> dict[str, Any]:
    """Lista los conectores activos configurados para la empresa. Scope: ``integration_hub:read``."""
    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        conectores = listar_conectores(ctx["empresa_id"])
        logger.info("integration_hub_listar_conectores | actor=%s | tenant=%s", ctx["actor_id"], ctx["tenant_id"])
        return {"conectores": conectores}


def integration_hub_test_conector(
    capability_token: str,
    empresa_id: str,
    conector_id: str,
) -> dict[str, Any]:
    """Prueba la conexión de un conector del tenant. Scope: ``integration_hub:read``."""
    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        res = test_conector(ctx["empresa_id"], conector_id)
        logger.info(
            "integration_hub_test_conector | actor=%s | tenant=%s | success=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            res.get("success"),
        )
        return res


def integration_hub_sincronizar(
    capability_token: str,
    empresa_id: str,
    conector_id: str,
    tipo_entidad: str,
    direccion: str = "inbound",
    sync_completo: bool = False,
) -> dict[str, Any]:
    """Dispara sincronización inbound, outbound o bidireccional. Scope: ``integration_hub:write``."""
    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=empresa_id) as ctx:
        res = sincronizar(
            ctx["empresa_id"],
            conector_id,
            tipo_entidad,
            direccion=direccion,
            sync_completo=sync_completo,
        )
        logger.info(
            "integration_hub_sincronizar | actor=%s | tenant=%s | entidad=%s | dir=%s | ok=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            tipo_entidad,
            direccion,
            res.get("success"),
        )
        return res


def integration_hub_push_cobranza(
    capability_token: str,
    empresa_id: str,
    conector_id: str,
    tipo: str = "todos",
    ids: list[str] | None = None,
    push_modo_pago: str | None = None,
) -> dict[str, Any]:
    """Dispara push outbound de pagos y/o gestiones de cobranza. Scope: ``integration_hub:write``."""
    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=empresa_id) as ctx:
        res = push_cobranza(
            ctx["empresa_id"],
            conector_id,
            tipo=tipo,
            ids=ids,
            push_modo_pago=push_modo_pago,
        )
        logger.info(
            "integration_hub_push_cobranza | actor=%s | tenant=%s | tipo=%s | ok=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            tipo,
            res.get("success"),
        )
        return res


def integration_hub_estado_sync(
    capability_token: str,
    empresa_id: str,
) -> dict[str, Any]:
    """Consulta el estado de sincronizaciones recientes del tenant. Scope: ``integration_hub:read``."""
    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=empresa_id) as ctx:
        res = estado_sync(ctx["empresa_id"])
        logger.info("integration_hub_estado_sync | actor=%s | tenant=%s", ctx["actor_id"], ctx["tenant_id"])
        return res


def _validar_sin_nul_mcp(valor: str | None, campo: str) -> str | None:
    if valor is None:
        return None
    texto = str(valor)
    if "\x00" in texto:
        raise ValueError(f"El parámetro '{campo}' contiene caracteres inválidos.")
    return texto


def _parse_uuid_strict_mcp(raw: str, campo: str) -> uuid.UUID:
    texto = _validar_sin_nul_mcp(raw, campo) or ""
    parsed = _parse_uuid(texto)
    if parsed is None:
        raise ValueError(f"El parámetro '{campo}' no es un UUID válido.")
    return parsed


def _parse_optional_uuid_mcp(raw: str | None, campo: str) -> uuid.UUID | None:
    if raw is None:
        return None
    texto = _validar_sin_nul_mcp(raw, campo) or ""
    if not texto.strip():
        return None
    return _parse_uuid_strict_mcp(texto, campo)


def _serializar_evento_outbox_mcp(evento) -> dict[str, Any]:
    return {
        "id_evento": str(evento.id_evento),
        "id_empresa": str(evento.id_empresa_id),
        "tipo_evento": evento.tipo_evento,
        "entidad_tipo": evento.entidad_tipo,
        "entidad_id": str(evento.entidad_id),
        "clave_idempotencia": evento.clave_idempotencia,
        "estado": evento.estado,
        "intentos": evento.intentos,
        "max_intentos": evento.max_intentos,
        "proximo_intento_en": evento.proximo_intento_en.isoformat() if evento.proximo_intento_en else None,
        "procesado_en": evento.procesado_en.isoformat() if evento.procesado_en else None,
        "ultimo_error": evento.ultimo_error,
    }


def hub_listar_outbox(
    capability_token: str,
    empresa_id: str | None = None,
    estado: str | None = None,
    tipo_evento: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Lista eventos de la cola Outbox multi-tenant. Scope: ``integration_hub:read``."""
    from apps.integration_hub.models import EventoOutbox  # noqa: PLC0415

    try:
        emp_uuid = _parse_optional_uuid_mcp(empresa_id, "empresa_id")
        estado_val = _validar_sin_nul_mcp(estado, "estado")
        tipo_val = _validar_sin_nul_mcp(tipo_evento, "tipo_evento")
        estado_norm: str | None = None
        if estado_val is not None and estado_val.strip():
            estado_norm = estado_val.strip().upper()
            if estado_norm not in set(EventoOutbox.Estado.values):
                raise ValueError(f"Estado '{estado_val}' no válido.")
        tope = max(1, min(int(limit), 200))
    except ValueError as exc:
        return {
            "success": False,
            "error": sanitize_mcp_error(
                exc,
                logger=logger,
                tool_name="hub_listar_outbox",
                controlled_types=(ValueError,),
            ),
            "eventos": [],
        }

    emp_str = str(emp_uuid) if emp_uuid is not None else None
    with _ctx(capability_token, f"{_SCOPE}:read", empresa_id=emp_str) as ctx:
        try:
            qs = EventoOutbox.objects.filter(
                id_empresa_id=ctx["empresa_id"],
                activo=True,
            ).order_by("-fecha_creacion")
            if estado_norm is not None:
                qs = qs.filter(estado=estado_norm)
            if tipo_val is not None and tipo_val.strip():
                qs = qs.filter(tipo_evento=tipo_val.strip())
            eventos = list(qs[:tope])
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "error": sanitize_mcp_error(exc, logger=logger, tool_name="hub_listar_outbox"),
                "eventos": [],
            }

        logger.info(
            "hub_listar_outbox | actor=%s | tenant=%s | count=%d",
            ctx["actor_id"],
            ctx["tenant_id"],
            len(eventos),
        )
        return {
            "success": True,
            "eventos": [_serializar_evento_outbox_mcp(ev) for ev in eventos],
        }


def hub_reintentar_outbox(
    capability_token: str,
    empresa_id: str | None = None,
    evento_id: str = "",
) -> dict[str, Any]:
    """Reencola un evento Outbox en estado ``FALLIDO`` o ``DLQ``. Scope: ``integration_hub:write``."""
    from apps.integration_hub.outbox import OutboxError, reintentar_evento_outbox  # noqa: PLC0415

    try:
        emp_uuid = _parse_optional_uuid_mcp(empresa_id, "empresa_id")
        evento_uuid = _parse_uuid_strict_mcp(evento_id, "evento_id")
    except ValueError as exc:
        return {
            "success": False,
            "error": sanitize_mcp_error(
                exc,
                logger=logger,
                tool_name="hub_reintentar_outbox",
                controlled_types=(ValueError,),
            ),
        }

    emp_str = str(emp_uuid) if emp_uuid is not None else None
    with _ctx(capability_token, f"{_SCOPE}:write", empresa_id=emp_str) as ctx:
        try:
            actualizado = reintentar_evento_outbox(
                evento_uuid,
                empresa_ids=[uuid.UUID(str(ctx["empresa_id"]))],
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "success": False,
                "error": sanitize_mcp_error(
                    exc,
                    logger=logger,
                    tool_name="hub_reintentar_outbox",
                    controlled_types=(OutboxError, DjangoValidationError, ValueError),
                ),
            }

        logger.info(
            "hub_reintentar_outbox | actor=%s | tenant=%s | evento=%s",
            ctx["actor_id"],
            ctx["tenant_id"],
            actualizado.id_evento,
        )
        return {
            "success": True,
            "evento": _serializar_evento_outbox_mcp(actualizado),
        }


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "fn": integration_hub_listar_conectores,
        "name": "integration_hub_listar_conectores",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": integration_hub_test_conector,
        "name": "integration_hub_test_conector",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": integration_hub_sincronizar,
        "name": "integration_hub_sincronizar",
        "scope": f"{_SCOPE}:write",
    },
    {
        "fn": integration_hub_push_cobranza,
        "name": "integration_hub_push_cobranza",
        "scope": f"{_SCOPE}:write",
    },
    {
        "fn": integration_hub_estado_sync,
        "name": "integration_hub_estado_sync",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": hub_listar_outbox,
        "name": "hub_listar_outbox",
        "scope": f"{_SCOPE}:read",
    },
    {
        "fn": hub_reintentar_outbox,
        "name": "hub_reintentar_outbox",
        "scope": f"{_SCOPE}:write",
    },
]
