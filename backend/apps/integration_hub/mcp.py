"""
MCP Server del Integration Hub.

Expone capacidades para que los agentes de IA puedan:
- Listar y gestionar conectores
- Disparar sincronizaciones
- Consultar estado de sincronizaciones

Convención de nombres: integration_hub.<operacion>
"""
import logging

logger = logging.getLogger(__name__)


# Registro de capacidades MCP
# Se usa cuando apps.mcp_runtime está disponible (Fase 0 WS-3)
# Por ahora se define la interfaz para cuando el runtime esté listo.

MCP_CAPABILITIES = [
    {
        "name": "integration_hub.listar_conectores",
        "description": (
            "Lista todos los conectores de integración configurados para la empresa actual. "
            "Retorna nombre, proveedor, estado y último sync."
        ),
        "requires_capabilities": ["integration_hub.leer"],
    },
    {
        "name": "integration_hub.test_conector",
        "description": (
            "Prueba la conexión de un conector específico con el sistema externo. "
            "Requiere el ID del conector."
        ),
        "requires_capabilities": ["integration_hub.leer"],
    },
    {
        "name": "integration_hub.sincronizar",
        "description": (
            "Dispara una sincronización de datos para una entidad específica "
            "(contactos, productos, pedidos_venta, etc.) en un conector dado."
        ),
        "requires_capabilities": ["integration_hub.ejecutar_sync"],
    },
    {
        "name": "integration_hub.estado_sync",
        "description": (
            "Consulta el estado de las sincronizaciones recientes: "
            "jobs completados, en progreso, fallidos y métricas."
        ),
        "requires_capabilities": ["integration_hub.leer"],
    },
    {
        "name": "integration_hub.preview_datos",
        "description": (
            "Previsualiza los primeros registros que se recibirían al sincronizar "
            "una entidad de un conector sin ejecutar la sincronización real."
        ),
        "requires_capabilities": ["integration_hub.leer"],
    },
]


def listar_conectores(empresa_id: str) -> list[dict]:
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
        }
        for c in conectores
    ]


def test_conector(empresa_id: str, conector_id: str) -> dict:
    """
    Prueba la conexión de un conector.
    Capacidad MCP: integration_hub.test_conector
    """
    from apps.integration_hub.connectors.registry import registry
    from apps.integration_hub.models import ConectorInstancia

    try:
        instancia = ConectorInstancia.objects.get(
            pk=conector_id,
            id_empresa=empresa_id,
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


def sincronizar(
    empresa_id: str,
    conector_id: str,
    tipo_entidad: str,
    usuario_id: str | None = None,
) -> dict:
    """
    Dispara una sincronización para una entidad.
    Capacidad MCP: integration_hub.sincronizar
    """
    from apps.integration_hub.models import ConectorInstancia, JobSincronizacion
    from apps.integration_hub.tasks import ejecutar_job_sincronizacion

    try:
        instancia = ConectorInstancia.objects.get(
            pk=conector_id,
            id_empresa=empresa_id,
            activo=True,
        )
    except ConectorInstancia.DoesNotExist:
        return {"success": False, "message": f"Conector {conector_id} no encontrado."}

    job = JobSincronizacion.objects.create(
        id_instancia=instancia,
        tipo_entidad=tipo_entidad,
        direccion="inbound",
        estado="pendiente",
    )

    try:
        task = ejecutar_job_sincronizacion.delay(str(job.id_job))
        job.celery_task_id = task.id
        job.save(update_fields=["celery_task_id"])
    except Exception:
        # BUG-NEW-5: si el broker Celery falla, no dejar el job "pendiente" eterno
        # sin rastro: marcarlo fallido y loguear con traza.
        logger.exception("No se pudo encolar el job de sincronización %s", job.id_job)
        job.estado = "fallido"
        job.resumen_errores = [
            "No se pudo encolar la tarea de sincronización (procesador de tareas no disponible)."
        ]
        job.save(update_fields=["estado", "resumen_errores"])
        return {
            "success": False,
            "job_id": str(job.id_job),
            "mensaje": "No se pudo iniciar la sincronización: el procesador de tareas no está disponible.",
        }

    return {
        "success": True,
        "job_id": str(job.id_job),
        "mensaje": f"Sync de '{tipo_entidad}' iniciado para '{instancia.nombre}'.",
    }


def estado_sync(empresa_id: str) -> dict:
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
