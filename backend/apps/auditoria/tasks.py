"""
Tareas Celery del módulo auditoria.

Permite registrar eventos de auditoría de forma asíncrona (fire-and-forget),
evitando que el registro afecte la latencia de la request HTTP.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="auditoria.registrar_evento",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,  # no consumir el mensaje hasta que la tarea termine
)
def registrar_evento(
    self,
    empresa_id: str,
    modulo: str,
    tipo_accion: str,
    descripcion: Optional[str] = None,
    usuario_id: Optional[int] = None,
    entidad_id: Optional[str] = None,
    nombre_entidad: Optional[str] = None,
    cambios: Optional[dict] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Persiste un registro de auditoría en LogAuditoria.

    Todos los parámetros deben ser JSON-serializables (str, int, dict, None)
    porque Celery los serializa al encolar la tarea.

    Args:
        empresa_id    — UUID de la empresa (str)
        modulo        — Nombre del módulo Django (ej. 'ventas')
        tipo_accion   — 'CREAR' | 'EDITAR' | 'ELIMINAR' | 'LOGIN' | etc.
        descripcion   — Texto libre opcional
        usuario_id    — PK del usuario que disparó la acción
        entidad_id    — UUID de la entidad afectada (str)
        nombre_entidad— Nombre del modelo (ej. 'Cotizacion')
        cambios       — Dict con snapshot de cambios (before/after)
        ip            — IP remota del cliente
        user_agent    — User-Agent del cliente

    Returns:
        dict con el id del log creado y un resumen de los parámetros.
    """
    from apps.auditoria.models import LogAuditoria
    from apps.core.models import Empresa, Usuarios

    try:
        empresa = Empresa.objects.get(pk=empresa_id)
        usuario = Usuarios.objects.get(pk=usuario_id) if usuario_id else None

        log = LogAuditoria.objects.create(
            id_empresa=empresa,
            id_usuario=usuario,
            modulo=modulo,
            tipo_accion=tipo_accion,
            descripcion_accion=descripcion,
            id_entidad_afectada=entidad_id,
            nombre_entidad_afectada=nombre_entidad,
            cambios_json=cambios,
            direccion_ip=ip,
            navegador_info=user_agent,
        )

        logger.info(
            "auditoria.registrar_evento OK — empresa=%s módulo=%s accion=%s log_id=%s",
            empresa_id,
            modulo,
            tipo_accion,
            log.pk,
        )

        return {
            "task_id": self.request.id,
            "log_id": str(log.pk),
            "empresa_id": empresa_id,
            "modulo": modulo,
            "tipo_accion": tipo_accion,
        }

    except Empresa.DoesNotExist:
        logger.error("auditoria.registrar_evento: empresa %s no encontrada", empresa_id)
        # No reintentar si la empresa no existe — es un error de programación
        raise

    except Exception as exc:
        logger.warning("auditoria.registrar_evento falló (intento %s): %s", self.request.retries, exc)
        raise self.retry(exc=exc)
