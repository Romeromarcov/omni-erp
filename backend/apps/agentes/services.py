"""Servicios de orquestación y serialización para ejecuciones asíncronas de agentes IA (P2-2)."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any
import uuid

from django.db import DEFAULT_DB_ALIAS, connections, models, transaction
from django.db.models import Avg, Count, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.core import llm_gateway
from apps.core.exceptions import DomainError
from apps.core.models import Empresa

from .models import ConsumoLLM, EjecucionAgente, PrediccionAgente

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


# ── Persistencia y resumen de consumo LLM (Plan 05 P2-3) ──────────────────────

_COSTO_QUANT = Decimal("0.000001")


def _entero_no_negativo(valor: Any) -> int:
    if isinstance(valor, bool):
        return 0
    try:
        return max(0, int(valor))
    except (TypeError, ValueError):
        return 0


def persistir_consumo_llm(evento: dict[str, Any]) -> ConsumoLLM | None:
    """
    Persiste un evento de consumo emitido por ``apps.core.llm_gateway`` en ``ConsumoLLM``.

    Es fail-safe: valida UUID de ``empresa_id``, respeta rollbacks pendientes y usa un
    savepoint ``transaction.atomic()`` para nunca romper llamadas LLM ni envenenar
    transacciones externas ante fallos de BD o tests unitarios sin ``django_db``.
    """
    if not isinstance(evento, dict):
        return None

    empresa_raw = evento.get("empresa_id")
    empresa_uuid: uuid.UUID | None = None
    if empresa_raw is not None and str(empresa_raw).strip():
        try:
            empresa_uuid = uuid.UUID(str(empresa_raw).strip())
        except (ValueError, TypeError):
            logger.debug("persistir_consumo_llm: empresa_id inválido (%r); omitido", empresa_raw)
            return None

    conn = connections[DEFAULT_DB_ALIAS]
    if getattr(conn, "needs_rollback", False):
        logger.warning("persistir_consumo_llm: transacción en rollback pendiente; consumo no persistido")
        return None

    proveedor = str(evento.get("proveedor") or "desconocido").strip()[:50] or "desconocido"
    uso = str(evento.get("uso") or "agente").strip()[:30] or "agente"
    modelo = str(evento.get("modelo") or "desconocido").strip()[:100] or "desconocido"
    tokens_entrada = _entero_no_negativo(evento.get("tokens_entrada"))
    tokens_salida = _entero_no_negativo(evento.get("tokens_salida"))
    latencia_ms = _entero_no_negativo(evento.get("latencia_ms"))
    costo_usd = llm_gateway.calcular_costo_estimado_usd(modelo, tokens_entrada, tokens_salida)

    try:
        with transaction.atomic():
            if empresa_uuid is not None and not Empresa.objects.filter(pk=empresa_uuid).exists():
                logger.warning("persistir_consumo_llm: empresa %s no existe; consumo no persistido", empresa_uuid)
                return None
            return ConsumoLLM.objects.create(
                id_empresa_id=empresa_uuid,
                proveedor=proveedor,
                uso=uso,
                modelo=modelo,
                tokens_entrada=tokens_entrada,
                tokens_salida=tokens_salida,
                costo_estimado_usd=costo_usd,
                latencia_ms=latencia_ms,
            )
    except Exception as exc:  # noqa: BLE001 — fail-safe: no tumbar llamadas LLM ni transacciones padre
        if "Database access not allowed" in str(exc):
            logger.debug("persistir_consumo_llm omitido en test sin BD")
        else:
            logger.warning("No se pudo persistir ConsumoLLM (%s); el consumo quedó solo en logs", type(exc).__name__)
        return None


def registrar_hook_consumo_llm(*, force: bool = True) -> None:
    """Conecta ``persistir_consumo_llm`` en ``llm_gateway.registrar_consumo_hook`` (idempotente)."""
    if force or llm_gateway.registrar_consumo_hook is None:
        llm_gateway.registrar_consumo_hook = persistir_consumo_llm


def _formatear_usd(valor: Decimal | None) -> str:
    cuantizado = Decimal(valor or 0).quantize(_COSTO_QUANT, rounding=ROUND_HALF_UP)
    return f"{cuantizado:.6f}"


def calcular_resumen_consumo_llm(qs) -> dict[str, Any]:
    """Agrega métricas de consumo LLM (totales y desglose por modelo/uso) sobre ``qs``."""
    zero_dec = Value(Decimal("0.000000"), output_field=models.DecimalField(max_digits=16, decimal_places=6))
    totales = qs.aggregate(
        llamadas=Count("pk"),
        tokens_entrada_total=Coalesce(Sum("tokens_entrada"), 0),
        tokens_salida_total=Coalesce(Sum("tokens_salida"), 0),
        costo_total_usd=Coalesce(Sum("costo_estimado_usd"), zero_dec),
        latencia_promedio=Avg("latencia_ms"),
    )
    latencia_raw = totales["latencia_promedio"]
    latencia_promedio_ms = (
        int(Decimal(str(latencia_raw)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if latencia_raw is not None
        else 0
    )

    por_modelo_rows = (
        qs.values("modelo")
        .annotate(
            llamadas=Count("pk"),
            tokens_entrada_total=Coalesce(Sum("tokens_entrada"), 0),
            tokens_salida_total=Coalesce(Sum("tokens_salida"), 0),
            costo_total_usd=Coalesce(Sum("costo_estimado_usd"), zero_dec),
        )
        .order_by("-costo_total_usd", "-llamadas", "modelo")
    )
    por_uso_rows = (
        qs.values("uso")
        .annotate(
            llamadas=Count("pk"),
            tokens_entrada_total=Coalesce(Sum("tokens_entrada"), 0),
            tokens_salida_total=Coalesce(Sum("tokens_salida"), 0),
            costo_total_usd=Coalesce(Sum("costo_estimado_usd"), zero_dec),
        )
        .order_by("-costo_total_usd", "-llamadas", "uso")
    )

    return {
        "llamadas": int(totales["llamadas"] or 0),
        "tokens_entrada_total": int(totales["tokens_entrada_total"] or 0),
        "tokens_salida_total": int(totales["tokens_salida_total"] or 0),
        "costo_total_usd": _formatear_usd(totales["costo_total_usd"]),
        "latencia_promedio_ms": latencia_promedio_ms,
        "por_modelo": [
            {
                "modelo": row["modelo"],
                "llamadas": int(row["llamadas"] or 0),
                "tokens_entrada_total": int(row["tokens_entrada_total"] or 0),
                "tokens_salida_total": int(row["tokens_salida_total"] or 0),
                "costo_total_usd": _formatear_usd(row["costo_total_usd"]),
            }
            for row in por_modelo_rows
        ],
        "por_uso": [
            {
                "uso": row["uso"],
                "llamadas": int(row["llamadas"] or 0),
                "tokens_entrada_total": int(row["tokens_entrada_total"] or 0),
                "tokens_salida_total": int(row["tokens_salida_total"] or 0),
                "costo_total_usd": _formatear_usd(row["costo_total_usd"]),
            }
            for row in por_uso_rows
        ],
    }
