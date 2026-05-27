"""
Views del Integration Hub.

Endpoints:
  GET  /api/integration-hub/proveedores/              — lista de conectores disponibles
  GET/POST  /api/integration-hub/instancias/          — mis conectores configurados
  GET/PUT/PATCH/DELETE  /api/integration-hub/instancias/{id}/
  POST /api/integration-hub/instancias/{id}/test/     — probar conexión
  POST /api/integration-hub/instancias/{id}/sync/     — disparar sync manual
  GET  /api/integration-hub/instancias/{id}/jobs/     — historial de jobs
  GET  /api/integration-hub/instancias/{id}/entidades/{tipo}/  — ver mapa entidades
  GET  /api/integration-hub/jobs/{id}/logs/           — logs de un job
  GET  /api/integration-hub/status/                   — estado general del hub
"""
import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .connectors.registry import registry
from .models import (
    ConectorInstancia,
    ConectorProveedor,
    EntidadSincronizada,
    JobSincronizacion,
    LogDetalleSincronizacion,
)
from .serializers import (
    ConectorInstanciaCreateSerializer,
    ConectorInstanciaSerializer,
    ConectorProveedorSerializer,
    EntidadSincronizadaSerializer,
    JobSincronizacionSerializer,
    JobSincronizacionTriggerSerializer,
    LogDetalleSincronizacionSerializer,
)

logger = logging.getLogger(__name__)


def _empresa(request):
    """Retorna la empresa del usuario autenticado."""
    return request.user.empresa


# ── Catálogo de proveedores (solo lectura) ────────────────────────────────────

class ConectorProveedorViewSet(ReadOnlyModelViewSet):
    """Lista los conectores disponibles en el sistema."""
    queryset = ConectorProveedor.objects.filter(activo=True).order_by("orden", "nombre")
    serializer_class = ConectorProveedorSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Lista pequeña, sin paginación


# ── Instancias de conectores ─────────────────────────────────────────────────

class ConectorInstanciaViewSet(BaseModelViewSet):
    """
    CRUD de conectores configurados por empresa.
    Acciones adicionales: test, sync, jobs, entidades.
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # R-CODE-1: solo empresa del usuario
        empresas = get_empresas_visible(self.request.user)
        return ConectorInstancia.objects.filter(
            id_empresa__in=empresas,
            activo=True,
        ).select_related("id_proveedor")

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ConectorInstanciaCreateSerializer
        return ConectorInstanciaSerializer

    def perform_create(self, serializer):
        serializer.save(
            id_empresa=_empresa(self.request),
            estado="configurando",
        )

    @action(detail=True, methods=["post"], url_path="test")
    def test_connection(self, request, pk=None):
        """
        Prueba la conexión con el sistema externo.
        Actualiza estado y version_detectada en la instancia.
        """
        instancia = self.get_object()

        try:
            conector = registry.get_connector(instancia)
            resultado = conector.test_connection()
        except Exception as exc:
            logger.error("test_connection error [%s]: %s", instancia.nombre, exc)
            instancia.estado = "error"
            instancia.mensaje_estado = str(exc)[:500]
            instancia.ultimo_test_conexion = timezone.now()
            instancia.save(update_fields=["estado", "mensaje_estado", "ultimo_test_conexion"])
            return Response(
                {"success": False, "message": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Actualizar instancia con resultado
        instancia.ultimo_test_conexion = timezone.now()
        instancia.mensaje_estado = resultado.message
        if resultado.success:
            instancia.estado = "activo"
            instancia.version_detectada = resultado.version or ""
        else:
            instancia.estado = "error"

        instancia.save(update_fields=[
            "estado", "mensaje_estado", "version_detectada", "ultimo_test_conexion"
        ])

        return Response({
            "success": resultado.success,
            "message": resultado.message,
            "version": resultado.version,
            "details": resultado.details,
        })

    @action(detail=True, methods=["post"], url_path="sync")
    def trigger_sync(self, request, pk=None):
        """
        Dispara una sincronización manual para una entidad específica.
        El job se encola en Celery para ejecución asíncrona.
        """
        instancia = self.get_object()

        if instancia.estado == "error":
            return Response(
                {
                    "error": "La instancia está en estado de error. "
                             "Realice un test de conexión antes de sincronizar."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = JobSincronizacionTriggerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data

        tipo_entidad = params["tipo_entidad"]
        direccion = params["direccion"]
        sync_completo = params.get("sync_completo", False)
        desde_fecha = params.get("desde")

        # Verificar que la entidad esté activa en la instancia
        if tipo_entidad not in instancia.entidades_activas and instancia.entidades_activas:
            return Response(
                {
                    "error": f"La entidad '{tipo_entidad}' no está habilitada en este conector. "
                             f"Entidades activas: {instancia.entidades_activas}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Crear el job
        parametros = {}
        if sync_completo:
            parametros["sync_completo"] = True
        if desde_fecha:
            parametros["desde"] = str(desde_fecha)

        job = JobSincronizacion.objects.create(
            id_instancia=instancia,
            tipo_entidad=tipo_entidad,
            direccion=direccion,
            estado="pendiente",
            iniciado_por=request.user,
            parametros=parametros,
        )

        # Encolar en Celery
        try:
            from .tasks import ejecutar_job_sincronizacion
            task = ejecutar_job_sincronizacion.delay(str(job.id_job))
            job.celery_task_id = task.id
            job.save(update_fields=["celery_task_id"])
        except Exception as exc:
            logger.warning(
                "No se pudo encolar job en Celery — ejecutando sincrónicamente. Error: %s", exc
            )
            # Fallback: ejecutar sincrónicamente (ej. si Celery no está disponible)
            from .services.sync_engine import SyncEngine
            engine = SyncEngine()
            engine.ejecutar_job(job)
            job.refresh_from_db()

        return Response(
            JobSincronizacionSerializer(job).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="jobs")
    def list_jobs(self, request, pk=None):
        """Lista el historial de jobs de sincronización de esta instancia."""
        instancia = self.get_object()
        jobs = JobSincronizacion.objects.filter(
            id_instancia=instancia
        ).order_by("-iniciado_en")[:50]
        return Response(JobSincronizacionSerializer(jobs, many=True).data)

    @action(detail=True, methods=["get"], url_path="entidades/(?P<tipo_entidad>[^/.]+)")
    def list_entidades(self, request, pk=None, tipo_entidad=None):
        """Lista las entidades sincronizadas de un tipo específico."""
        instancia = self.get_object()
        entidades = EntidadSincronizada.objects.filter(
            id_instancia=instancia,
            tipo_entidad=tipo_entidad,
            activo=True,
        ).order_by("-ultimo_sync")[:200]
        return Response(EntidadSincronizadaSerializer(entidades, many=True).data)

    @action(detail=True, methods=["get"], url_path="preview/(?P<tipo_entidad>[^/.]+)")
    def preview_data(self, request, pk=None, tipo_entidad=None):
        """
        Previsualiza datos del sistema externo sin sincronizar.
        Útil para validar la conexión y ver qué datos se recibirán.
        """
        instancia = self.get_object()

        try:
            conector = registry.get_connector(instancia)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        if not conector.supports(tipo_entidad):
            return Response(
                {"error": f"'{tipo_entidad}' no soportado por este conector."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.integration_hub.services.sync_engine import SyncEngine
        pull_methods = SyncEngine.PULL_METHODS
        method_name = pull_methods.get(tipo_entidad)
        if not method_name:
            return Response(
                {"error": f"Sin método pull para '{tipo_entidad}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            method = getattr(conector, method_name)
            # Preview: máximo 10 registros
            registros = method(desde=None)[:10]
            return Response({
                "tipo_entidad": tipo_entidad,
                "total_disponible": "desconocido (preview)",
                "muestra": registros,
            })
        except Exception as exc:
            logger.error("preview_data error [%s / %s]: %s", instancia.nombre, tipo_entidad, exc)
            return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


# ── Jobs de sincronización ────────────────────────────────────────────────────

class JobSincronizacionViewSet(ReadOnlyModelViewSet):
    """Vista de solo lectura para jobs de sincronización."""
    serializer_class = JobSincronizacionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        empresas = get_empresas_visible(self.request.user)
        return JobSincronizacion.objects.filter(
            id_instancia__id_empresa__in=empresas
        ).select_related("id_instancia", "iniciado_por").order_by("-iniciado_en")

    @action(detail=True, methods=["get"], url_path="logs")
    def list_logs(self, request, pk=None):
        """Logs detallados de un job específico."""
        job = self.get_object()
        logs = LogDetalleSincronizacion.objects.filter(
            id_job=job
        ).order_by("-creado_en")[:500]
        return Response(LogDetalleSincronizacionSerializer(logs, many=True).data)

    @action(detail=True, methods=["post"], url_path="cancelar")
    def cancelar(self, request, pk=None):
        """Cancela un job pendiente o en progreso."""
        job = self.get_object()
        if job.estado not in ("pendiente", "en_progreso"):
            return Response(
                {"error": f"No se puede cancelar un job en estado '{job.estado}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if job.celery_task_id:
            try:
                from config.celery import app as celery_app
                celery_app.control.revoke(job.celery_task_id, terminate=True)
            except Exception:
                pass

        job.estado = "cancelado"
        job.completado_en = timezone.now()
        job.save(update_fields=["estado", "completado_en"])

        return Response(JobSincronizacionSerializer(job).data)


# ── Estado general del hub ────────────────────────────────────────────────────

class IntegrationHubStatusView(APIView):
    """Estado general del Integration Hub para el tenant actual."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        empresa = _empresa(request)
        conectores = ConectorInstancia.objects.filter(
            id_empresa=empresa, activo=True
        ).select_related("id_proveedor")

        activos = conectores.filter(estado="activo").count()
        con_error = conectores.filter(estado="error").count()
        configurando = conectores.filter(estado="configurando").count()

        # Jobs recientes (últimas 24h)
        from django.utils.timezone import timedelta
        hace_24h = timezone.now() - timedelta(hours=24)
        jobs_recientes = JobSincronizacion.objects.filter(
            id_instancia__id_empresa=empresa,
            iniciado_en__gte=hace_24h,
        )

        return Response({
            "conectores": {
                "total": conectores.count(),
                "activos": activos,
                "con_error": con_error,
                "configurando": configurando,
                "inactivos": conectores.filter(estado="inactivo").count(),
            },
            "jobs_24h": {
                "total": jobs_recientes.count(),
                "completados": jobs_recientes.filter(estado="completado").count(),
                "con_errores": jobs_recientes.filter(estado="completado_con_errores").count(),
                "fallidos": jobs_recientes.filter(estado="fallido").count(),
                "en_progreso": jobs_recientes.filter(estado="en_progreso").count(),
            },
            "proveedores_disponibles": registry.list_registered(),
        })
