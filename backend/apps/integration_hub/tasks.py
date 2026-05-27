"""
Tareas Celery del Integration Hub.

Permite sincronizaciones automáticas y manuales asíncronas.
"""
import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="integration_hub.ejecutar_job_sincronizacion",
)
def ejecutar_job_sincronizacion(self, job_id: str):
    """
    Ejecuta un JobSincronizacion dado su ID.
    Se llama tanto desde triggers manuales (view) como desde el scheduler.
    """
    from apps.integration_hub.models import JobSincronizacion
    from apps.integration_hub.services.sync_engine import SyncEngine

    try:
        job = JobSincronizacion.objects.select_related(
            "id_instancia__id_proveedor", "id_instancia__id_empresa"
        ).get(pk=job_id)
    except JobSincronizacion.DoesNotExist:
        logger.error("Job no encontrado: %s", job_id)
        return {"error": f"Job {job_id} no encontrado"}

    if job.estado not in ("pendiente", "en_progreso"):
        logger.info("Job %s ya está en estado '%s' — omitiendo", job_id, job.estado)
        return {"estado": job.estado, "mensaje": "Job ya procesado"}

    logger.info(
        "Iniciando job [%s] tipo=%s instancia=%s",
        job_id, job.tipo_entidad, job.id_instancia.nombre,
    )

    engine = SyncEngine()
    resultado = engine.ejecutar_job(job)

    return {
        "job_id": job_id,
        "estado": job.estado,
        "creados": resultado.creados,
        "actualizados": resultado.actualizados,
        "omitidos": resultado.omitidos,
        "fallidos": resultado.fallidos,
    }


@shared_task(name="integration_hub.sync_automatico_todos")
def sync_automatico_todos():
    """
    Tarea periódica que dispara sync automático para todos los conectores
    con intervalo_sync_minutos > 0 cuyo próximo sync ya venció.
    Se programa típicamente cada 15 minutos vía django-celery-beat.
    """
    from datetime import timedelta

    from apps.integration_hub.models import ConectorInstancia, JobSincronizacion

    ahora = timezone.now()
    conectores = ConectorInstancia.objects.filter(
        activo=True,
        estado="activo",
        intervalo_sync_minutos__gt=0,
    ).select_related("id_proveedor")

    disparados = 0
    for instancia in conectores:
        # Calcular si ya es hora del próximo sync
        if instancia.ultimo_sync:
            proximo = instancia.ultimo_sync + timedelta(
                minutes=instancia.intervalo_sync_minutos
            )
            if ahora < proximo:
                continue  # No es hora todavía

        # Disparar job para cada entidad activa
        for tipo_entidad in instancia.entidades_activas:
            # Verificar que no haya un job en progreso para esta entidad
            en_progreso = JobSincronizacion.objects.filter(
                id_instancia=instancia,
                tipo_entidad=tipo_entidad,
                estado__in=["pendiente", "en_progreso"],
            ).exists()
            if en_progreso:
                logger.info(
                    "Sync automático omitido para %s/%s — ya hay un job en progreso",
                    instancia.nombre, tipo_entidad,
                )
                continue

            job = JobSincronizacion.objects.create(
                id_instancia=instancia,
                tipo_entidad=tipo_entidad,
                direccion="inbound",
                estado="pendiente",
                # iniciado_por=None → automático
            )
            ejecutar_job_sincronizacion.delay(str(job.id_job))
            disparados += 1

    logger.info("sync_automatico_todos: %d jobs disparados", disparados)
    return {"jobs_disparados": disparados}


@shared_task(name="integration_hub.limpiar_logs_antiguos")
def limpiar_logs_antiguos(dias: int = 30):
    """
    Limpia logs de detalle de sincronización más antiguos que N días.
    Los jobs y mappings se mantienen; solo se purgan los logs verbose.
    """
    from datetime import timedelta

    from apps.integration_hub.models import LogDetalleSincronizacion

    corte = timezone.now() - timedelta(days=dias)
    eliminados, _ = LogDetalleSincronizacion.objects.filter(
        creado_en__lt=corte
    ).delete()

    logger.info("limpiar_logs_antiguos: %d registros eliminados (>%d días)", eliminados, dias)
    return {"eliminados": eliminados}
