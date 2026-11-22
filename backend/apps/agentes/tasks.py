"""
Tareas Celery del módulo de Agentes IA.

generar_sugerencias_diarias():
  Ejecuta CobranzaEstrategaAgent y ReordenSugeridorAgent para todas las empresas
  activas, persistiendo PrediccionAgente con resultado_humano="pendiente".
  Programada para correr a las 06:00 AM cada día (configurada en Celery Beat).

ejecutar_analisis_agente(ejecucion_id, empresa_id):
  Ejecuta de forma asíncrona fuera del request HTTP un análisis de agente
  (cobranza, reorden, personalización o clasificación de gasto) bajo
  ``rls_tenant_context([empresa_id])`` y persiste el resultado en ``EjecucionAgente``.
"""

from __future__ import annotations

import logging
from typing import Any
import uuid

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger("agentes")

_MENSAJE_ERROR_GENERICO = "No se pudo completar el análisis del agente."


@shared_task(
    name="agentes.ejecutar_analisis_agente",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def ejecutar_analisis_agente(self, ejecucion_id: str, empresa_id: str) -> dict[str, Any] | None:
    """
    Ejecuta asíncronamente un análisis de agente IA aislado por tenant RLS.

    Transiciona ``EjecucionAgente`` de ``pendiente`` → ``ejecutando`` → ``completado``
    o ``fallido`` (con ``mensaje_error`` genérico y saneado conforme a R-CODE-8).
    """
    from apps.core import rls  # noqa: PLC0415
    from apps.crm.models import Lead  # noqa: PLC0415
    from apps.gastos.models import CategoriaGasto, Gasto  # noqa: PLC0415

    from .clasificador import ClasificadorGastos  # noqa: PLC0415
    from .cobranza import CobranzaEstrategaAgent  # noqa: PLC0415
    from .connect_agents import (  # noqa: PLC0415
        ejecutar_connect_calificador,
        ejecutar_connect_seguimiento,
    )
    from .models import EjecucionAgente, PrediccionAgente  # noqa: PLC0415
    from .personalizacion_agente import PersonalizacionCapa2Agent  # noqa: PLC0415
    from .reorden import ReordenSugeridorAgent  # noqa: PLC0415
    from .services import (  # noqa: PLC0415
        AgenteError,
        jsonable,
        serializar_sugerencia_cobranza,
        serializar_sugerencia_reorden,
    )

    try:
        ejecucion_uuid = uuid.UUID(str(ejecucion_id))
        empresa_uuid = uuid.UUID(str(empresa_id))
    except (ValueError, TypeError):
        logger.warning(
            "ejecutar_analisis_agente: identificadores inválidos ejecucion=%r empresa=%r.",
            ejecucion_id,
            empresa_id,
        )
        return None

    with rls.rls_tenant_context([str(empresa_uuid)]):
        ejecucion = (
            EjecucionAgente.objects.select_related("id_empresa")
            .filter(pk=ejecucion_uuid, id_empresa_id=empresa_uuid)
            .first()
        )
        if ejecucion is None:
            if self.request.retries < self.max_retries:
                logger.warning(
                    "ejecutar_analisis_agente: ejecución %s aún no visible para empresa %s; reintentando (%d/%d).",
                    ejecucion_uuid,
                    empresa_uuid,
                    self.request.retries + 1,
                    self.max_retries,
                )
                raise self.retry(countdown=2)
            logger.warning(
                "ejecutar_analisis_agente: ejecución %s no encontrada para empresa %s.",
                ejecucion_uuid,
                empresa_uuid,
            )
            return None

        ejecucion.estado = "ejecutando"
        ejecucion.fecha_inicio = timezone.now()
        update_fields = ["estado", "fecha_inicio"]
        req_id = getattr(getattr(self, "request", None), "id", None)
        if not ejecucion.celery_task_id and req_id:
            ejecucion.celery_task_id = str(req_id)
            update_fields.append("celery_task_id")
        ejecucion.save(update_fields=update_fields)

        empresa = ejecucion.id_empresa
        parametros = ejecucion.parametros if isinstance(ejecucion.parametros, dict) else {}

        try:
            if ejecucion.agente == "cobranza_estratega":
                sugerencias_cobranza = CobranzaEstrategaAgent(empresa=empresa).analizar(
                    persistir=bool(parametros.get("persistir", False))
                )
                data = [serializar_sugerencia_cobranza(s) for s in sugerencias_cobranza]
                resultado_payload: dict[str, Any] = {"sugerencias": data, "total": len(data)}

            elif ejecucion.agente == "reorden_sugeridor":
                sugerencias_reorden = ReordenSugeridorAgent(empresa=empresa).analizar(
                    solo_alertas=bool(parametros.get("solo_alertas", True)),
                    persistir=bool(parametros.get("persistir", False)),
                )
                data = [serializar_sugerencia_reorden(s) for s in sugerencias_reorden]
                resultado_payload = {"sugerencias": data, "total": len(data)}

            elif ejecucion.agente == "personalizacion_capa2":
                res = PersonalizacionCapa2Agent(empresa=empresa).analizar()
                resultado_payload = {
                    "flujo_documentos": jsonable(res.flujo_documentos),
                    "listas_precios": jsonable(res.listas_precios),
                    "credito_clientes": jsonable(res.credito_clientes),
                }

            elif ejecucion.agente == "clasificador_gastos":
                gasto_id_raw = parametros.get("gasto_id")
                gasto_uuid = uuid.UUID(str(gasto_id_raw))
                aplicar = bool(parametros.get("aplicar", False))

                gasto = Gasto.objects.get(pk=gasto_uuid, id_empresa=empresa)
                agente = ClasificadorGastos(empresa=empresa)
                clasificacion = agente.clasificar(
                    descripcion=gasto.descripcion,
                    monto=gasto.monto,
                    persistir=True,
                )
                prediccion = None
                if clasificacion.prediccion_id:
                    prediccion = PrediccionAgente.objects.filter(
                        pk=clasificacion.prediccion_id,
                        id_empresa=empresa,
                    ).first()

                aplicado = False
                categoria_id = None
                if aplicar and clasificacion.confianza >= 0.5:
                    categoria_nombre = clasificacion.categoria.replace("_", " ").title()
                    categoria_obj = CategoriaGasto.objects.filter(id_empresa=empresa).filter(
                        Q(nombre_categoria__iexact=categoria_nombre)
                        | Q(nombre_categoria__iexact=clasificacion.categoria)
                    ).first() or CategoriaGasto.objects.create(
                        id_empresa=empresa,
                        nombre_categoria=categoria_nombre,
                        activo=True,
                    )
                    gasto.id_categoria_gasto = categoria_obj
                    gasto.save(update_fields=["id_categoria_gasto"])
                    aplicado = True
                    categoria_id = str(categoria_obj.pk)

                    if prediccion:
                        prediccion.resultado_humano = "aceptada"
                        prediccion.categoria_correcta = clasificacion.categoria
                        prediccion.save(update_fields=["resultado_humano", "categoria_correcta"])

                resultado_payload = {
                    "prediccion_id": str(prediccion.pk) if prediccion else None,
                    "categoria": clasificacion.categoria,
                    "confianza": float(clasificacion.confianza),
                    "razonamiento": clasificacion.razonamiento,
                    "alternativas": jsonable(clasificacion.alternativas),
                    "modelo_llm": clasificacion.modelo_llm,
                    "aplicado": aplicado,
                    "categoria_id": categoria_id,
                }

            elif ejecucion.agente == "connect_calificador":
                lead_id_raw = parametros.get("lead_id")
                lead_uuid = uuid.UUID(str(lead_id_raw))
                resultado_payload = ejecutar_connect_calificador(
                    empresa=empresa,
                    lead_id=lead_uuid,
                    usuario=ejecucion.iniciado_por,
                )

            elif ejecucion.agente == "connect_seguimiento":
                lead_id_raw = parametros.get("lead_id")
                lead_uuid = uuid.UUID(str(lead_id_raw))
                resultado_payload = ejecutar_connect_seguimiento(
                    empresa=empresa,
                    lead_id=lead_uuid,
                    usuario=ejecucion.iniciado_por,
                )

            else:
                raise ValueError(f"Agente no soportado: {ejecucion.agente}")

            ejecucion.estado = "completado"
            ejecucion.resultado = jsonable(resultado_payload)
            ejecucion.fecha_fin = timezone.now()
            ejecucion.save(update_fields=["estado", "resultado", "fecha_fin"])
            return ejecucion.resultado

        except (Gasto.DoesNotExist, Lead.DoesNotExist):
            logger.warning(
                "ejecutar_analisis_agente: entidad %r no encontrada para empresa %s (ejecucion=%s)",
                parametros.get("gasto_id") or parametros.get("lead_id"),
                empresa_uuid,
                ejecucion.pk,
            )
            ejecucion.estado = "fallido"
            ejecucion.mensaje_error = (
                "El lead solicitado no fue encontrado."
                if ejecucion.agente in ("connect_calificador", "connect_seguimiento")
                else "El gasto solicitado no fue encontrado."
            )
            ejecucion.fecha_fin = timezone.now()
            ejecucion.save(update_fields=["estado", "mensaje_error", "fecha_fin"])
            return None

        except AgenteError as exc:
            logger.warning(
                "ejecutar_analisis_agente: error controlado en %s (ejecucion=%s, empresa=%s): %s",
                ejecucion.agente,
                ejecucion.pk,
                empresa_uuid,
                exc,
            )
            ejecucion.estado = "fallido"
            ejecucion.mensaje_error = str(exc) or _MENSAJE_ERROR_GENERICO
            ejecucion.fecha_fin = timezone.now()
            ejecucion.save(update_fields=["estado", "mensaje_error", "fecha_fin"])
            return None

        except Exception:
            logger.exception(
                "Error ejecutando análisis de agente %s (ejecucion=%s, empresa=%s)",
                ejecucion.agente,
                ejecucion.pk,
                empresa_uuid,
            )
            ejecucion.estado = "fallido"
            ejecucion.mensaje_error = _MENSAJE_ERROR_GENERICO
            ejecucion.fecha_fin = timezone.now()
            ejecucion.save(update_fields=["estado", "mensaje_error", "fecha_fin"])
            return None


@shared_task(
    name="agentes.generar_sugerencias_diarias",
    bind=True,
    max_retries=2,
    default_retry_delay=300,  # 5 min retry
)
def generar_sugerencias_diarias(self):
    """
    Genera sugerencias diarias de cobranza y reorden para todas las empresas activas.

    Para cada empresa:
    - CobranzaEstrategaAgent: crea predicciones para CxC vencidas con prioridad ALTA.
    - ReordenSugeridorAgent: crea predicciones para productos en umbral de reorden.

    Solo persiste predicciones nuevas; no duplica las del mismo día.
    """
    from apps.core import rls
    from apps.core.models import Empresa

    with rls.rls_bypass():
        empresas = list(Empresa.objects.filter(activo=True) if hasattr(Empresa, "activo") else Empresa.objects.all())

    total_sugerencias = 0

    for empresa in empresas:
        with rls.rls_tenant_context([empresa.pk]):
            total_sugerencias += _generar_cobranza(empresa)
            total_sugerencias += _generar_reorden(empresa)

    total_empresas = len(empresas)
    logger.info(
        "generar_sugerencias_diarias: %d sugerencias creadas para %d empresas.", total_sugerencias, total_empresas
    )
    return {"total_sugerencias": total_sugerencias, "empresas": total_empresas}


def _generar_cobranza(empresa) -> int:
    """Genera sugerencias de cobranza para una empresa. Retorna cantidad creada."""
    try:
        from .cobranza import CobranzaEstrategaAgent

        agente = CobranzaEstrategaAgent(empresa=empresa)
        sugerencias = agente.analizar(persistir=True)
        # Solo contar las de prioridad ALTA para el reporte
        count = sum(1 for s in sugerencias if getattr(s, "prioridad", "") == "ALTA")
        return count
    except Exception as exc:
        logger.warning("Cobranza para empresa %s: %s", empresa.pk, exc)
        return 0


def _generar_reorden(empresa) -> int:
    """Genera sugerencias de reorden para una empresa. Retorna cantidad creada."""
    try:
        from .reorden import ReordenSugeridorAgent

        agente = ReordenSugeridorAgent(empresa=empresa)
        sugerencias = agente.analizar(solo_alertas=True, persistir=True)
        return len(sugerencias)
    except Exception as exc:
        logger.warning("Reorden para empresa %s: %s", empresa.pk, exc)
        return 0
