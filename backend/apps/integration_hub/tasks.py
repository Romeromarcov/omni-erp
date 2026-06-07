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


@shared_task(name="integration_hub.sync_tasas_ve", bind=True, max_retries=3, default_retry_delay=120)
def sync_tasas_ve(self):
    """
    Sincroniza BCV + Binance P2P.
    Persiste en apps.finanzas.TasaCambio (modelo compartido).
    BCV → tipo OFICIAL_BCV, empresa=None (global)
    Binance → tipo PROMEDIO_MERCADO, empresa=None
    """
    from datetime import date
    from django.utils import timezone

    try:
        from apps.integration_hub.connectors.tasas_ve.connector import TasasVeConnector
        from apps.finanzas.models import TasaCambio, Moneda

        connector = TasasVeConnector()
        hoy = date.today()

        # Obtener monedas base
        try:
            usd = Moneda.objects.get(codigo_iso="USD")
            ves = Moneda.objects.get(codigo_iso="VES")
        except Moneda.DoesNotExist:
            logger.error("sync_tasas_ve: Monedas USD/VES no encontradas en BD")
            return {"error": "Monedas no encontradas"}

        resultados = {}

        # BCV
        tasa_bcv = connector.pull_tasa_bcv()
        if tasa_bcv is not None:
            obj, created = TasaCambio.objects.update_or_create(
                id_empresa=None,
                id_moneda_origen=usd,
                id_moneda_destino=ves,
                tipo_tasa="OFICIAL_BCV",
                fecha_tasa=hoy,
                defaults={
                    "valor_tasa": tasa_bcv,
                    "hora_tasa": timezone.now().time(),
                    "referencia_externa": "hub:sync_tasas_ve",
                },
            )
            resultados["bcv"] = {"tasa": str(tasa_bcv), "created": created}
            logger.info("sync_tasas_ve BCV: tasa=%s created=%s", tasa_bcv, created)
        else:
            logger.warning("sync_tasas_ve: BCV no disponible — reintentando")
            raise self.retry(countdown=120)

        # Binance P2P
        tasa_binance = connector.pull_tasa_binance_p2p()
        if tasa_binance is not None:
            obj_b, created_b = TasaCambio.objects.update_or_create(
                id_empresa=None,
                id_moneda_origen=usd,
                id_moneda_destino=ves,
                tipo_tasa="PROMEDIO_MERCADO",
                fecha_tasa=hoy,
                defaults={
                    "valor_tasa": tasa_binance,
                    "hora_tasa": timezone.now().time(),
                    "referencia_externa": "hub:binance_p2p",
                },
            )
            resultados["binance_p2p"] = {"tasa": str(tasa_binance), "created": created_b}
            logger.info("sync_tasas_ve Binance: tasa=%s created=%s", tasa_binance, created_b)

        return resultados

    except self.MaxRetriesExceededError:
        logger.error("sync_tasas_ve: máximo de reintentos alcanzado")
        return {"error": "max_retries"}
    except Exception as exc:
        logger.exception("sync_tasas_ve error inesperado: %s", exc)
        raise self.retry(exc=exc, countdown=60)


@shared_task(name="integration_hub.sync_cartera_odoo_todos")
def sync_cartera_odoo_todos():
    """
    Fan-out periódico (Plan D — D2): refresca el cache de aging de TODOS los
    tenants Mode A (cxc.datasource='odoo'). Programado vía django-celery-beat.
    """
    from apps.configuracion_motor.models import ParametroSistema

    params = ParametroSistema.objects.filter(
        codigo_parametro="cxc.datasource",
        activo=True,
        id_empresa__isnull=False,
    )
    disparados = 0
    for p in params:
        if (p.valor_parametro or "").strip().lower() == "odoo":
            sync_cartera_odoo.delay(str(p.id_empresa_id))
            disparados += 1

    logger.info("sync_cartera_odoo_todos: %d tenants Odoo encolados", disparados)
    return {"tenants_odoo": disparados}


@shared_task(name="integration_hub.sync_cartera_odoo")
def sync_cartera_odoo(empresa_id: str):
    """
    Para tenants Mode A: refresca cache de aging desde Odoo.
    Solo actualiza el cache de Redis — no persiste la cartera.
    """
    from django.core.cache import cache

    try:
        from apps.cuentas_por_cobrar.services_cartera_provider import (
            get_cartera_provider,
        )
        from apps.cuentas_por_cobrar.services_aging import calcular_aging
        from apps.core.models import Empresa

        empresa = Empresa.objects.get(pk=empresa_id)
        provider = get_cartera_provider(empresa)
        partidas = provider.get_partidas()
        resumen = calcular_aging(partidas)

        cache_key = f"cxc:aging:{empresa_id}"
        cache.set(cache_key, resumen, timeout=900)  # 15 min

        logger.info(
            "sync_cartera_odoo: empresa=%s partidas=%d",
            empresa_id,
            len(partidas),
        )
        return {"empresa_id": empresa_id, "partidas": len(partidas)}

    except Exception as exc:
        logger.exception("sync_cartera_odoo error: %s", exc)
        return {"error": str(exc)}
