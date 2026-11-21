"""Servicios de orquestación y serialización para ejecuciones asíncronas de agentes IA (P2-2)."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import logging
from typing import Any
import uuid

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import DomainError

from .models import EjecucionAgente, PrediccionAgente

logger = logging.getLogger("agentes")

AGENTES_VALIDOS = frozenset(choice[0] for choice in PrediccionAgente.AGENTE_CHOICES)


class AgenteError(DomainError):
    """Error controlado del dominio de agentes IA."""


def jsonable(val: Any) -> Any:
    """Convierte recursivamente dataclasses, Decimal, UUID y fechas a tipos JSON seguros."""
    if val is None or isinstance(val, (bool, int, float, str)):
        return val
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if is_dataclass(val) and not isinstance(val, type):
        return jsonable(asdict(val))
    if isinstance(val, dict):
        return {str(k): jsonable(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [jsonable(item) for item in val]
    return str(val)


def serializar_sugerencia_cobranza(sugerencia: Any) -> dict[str, Any]:
    """Serializa una sugerencia de cobranza al contrato JSON estable."""
    canal = getattr(sugerencia, "canal_sugerido", None)
    if canal is None:
        canal = getattr(sugerencia, "canal", "")
    mensaje = getattr(sugerencia, "mensaje", None)
    if mensaje is None:
        mensaje = getattr(sugerencia, "mensaje_whatsapp", "")
    motivo = getattr(sugerencia, "motivo", None)
    if motivo is None:
        motivo = getattr(sugerencia, "razonamiento", "")
    return {
        "cxc_id": str(sugerencia.cxc_id),
        "cliente_nombre": str(sugerencia.cliente_nombre),
        "monto": str(sugerencia.monto),
        "dias_vencida": int(sugerencia.dias_vencida),
        "prioridad": str(sugerencia.prioridad),
        "canal_sugerido": str(canal),
        "mensaje": str(mensaje),
        "motivo": str(motivo),
    }


def serializar_sugerencia_reorden(sugerencia: Any) -> dict[str, Any]:
    """Serializa una sugerencia de reorden al contrato JSON estable (Decimal → str)."""
    nombre = getattr(sugerencia, "nombre_producto", None)
    if nombre is None:
        nombre = getattr(sugerencia, "producto_nombre", "")
    cantidad_sug = getattr(sugerencia, "cantidad_sugerida", None)
    if cantidad_sug is None:
        cantidad_sug = getattr(sugerencia, "cantidad_sugerida_reorden", Decimal("0"))
    motivo = getattr(sugerencia, "motivo", None)
    if motivo is None:
        motivo = getattr(sugerencia, "razonamiento", "")
    prioridad = getattr(sugerencia, "prioridad", None)
    if prioridad is None:
        estado = str(getattr(sugerencia, "estado", ""))
        prioridad = "alta" if estado == "REORDENAR" else ("media" if estado == "REVISAR" else "baja")
    return {
        "producto_id": str(sugerencia.producto_id),
        "nombre_producto": str(nombre),
        "stock_disponible": str(sugerencia.stock_disponible),
        "cantidad_minima": str(sugerencia.cantidad_minima),
        "estado": str(sugerencia.estado),
        "cantidad_sugerida": str(cantidad_sug),
        "motivo": str(motivo),
        "prioridad": str(prioridad),
    }


def serializar_ejecucion_dict(ejecucion: EjecucionAgente) -> dict[str, Any]:
    """Serializa ``EjecucionAgente`` como dict plano JSON-compatible para MCP/servicios."""
    return {
        "id_ejecucion": str(ejecucion.id_ejecucion),
        "id_empresa": str(ejecucion.id_empresa_id),
        "agente": ejecucion.agente,
        "estado": ejecucion.estado,
        "celery_task_id": ejecucion.celery_task_id,
        "parametros": jsonable(ejecucion.parametros or {}),
        "resultado": jsonable(ejecucion.resultado or {}),
        "mensaje_error": ejecucion.mensaje_error,
        "iniciado_por": str(ejecucion.iniciado_por_id) if ejecucion.iniciado_por_id else None,
        "fecha_creacion": ejecucion.fecha_creacion.isoformat() if ejecucion.fecha_creacion else None,
        "fecha_inicio": ejecucion.fecha_inicio.isoformat() if ejecucion.fecha_inicio else None,
        "fecha_fin": ejecucion.fecha_fin.isoformat() if ejecucion.fecha_fin else None,
    }


def encolar_ejecucion_agente(
    *,
    empresa,
    agente: str,
    parametros: dict[str, Any] | None = None,
    iniciado_por=None,
) -> EjecucionAgente:
    """
    Crea un ``EjecucionAgente`` pendiente y difiere ``.delay()`` al ``on_commit``.

    Tras confirmar la transacción, despacha ``agentes.ejecutar_analisis_agente`` y
    registra ``celery_task_id`` con UPDATE condicional atómico
    (``celery_task_id=""``) para no pisar al worker si éste finaliza antes.
    """
    from . import tasks as agentes_tasks  # noqa: PLC0415

    if agente not in AGENTES_VALIDOS:
        raise AgenteError(f"Agente no soportado: {agente}")

    with transaction.atomic():
        ejecucion = EjecucionAgente.objects.create(
            id_empresa=empresa,
            agente=agente,
            estado="pendiente",
            parametros=jsonable(parametros or {}),
            iniciado_por=iniciado_por,
        )
        ejecucion_pk = ejecucion.pk
        empresa_pk = empresa.pk

        def _despachar() -> None:
            try:
                task = agentes_tasks.ejecutar_analisis_agente.delay(str(ejecucion_pk), str(empresa_pk))
            except Exception as exc:
                logger.exception("Error encolando ejecución %s de agente %s", ejecucion_pk, agente)
                EjecucionAgente.objects.filter(pk=ejecucion_pk, estado="pendiente").update(
                    estado="fallido",
                    mensaje_error="No se pudo encolar el análisis del agente.",
                    fecha_fin=timezone.now(),
                )
                raise AgenteError("No se pudo encolar el análisis del agente.") from exc

            task_id = getattr(task, "id", None)
            if task_id:
                EjecucionAgente.objects.filter(pk=ejecucion_pk, celery_task_id="").update(
                    celery_task_id=str(task_id),
                )

        transaction.on_commit(_despachar)

    ejecucion.refresh_from_db()
    return ejecucion
