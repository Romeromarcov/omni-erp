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
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from drf_yasg.utils import swagger_auto_schema
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.core.viewsets import (
    BaseModelViewSet,
    NulSafeFilterMixin,
    SuperuserWriteMixin,
    get_empresas_visible,
    validar_uuid_param,
)

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
    PushCobranzaInputSerializer,
    PushCobranzaResponseSerializer,
)

logger = logging.getLogger(__name__)


def _leer_idempotency_key(request) -> str | None:
    """Lee y valida la cabecera ``Idempotency-Key`` (máx 255 chars, sin NUL)."""
    raw = request.META.get("HTTP_IDEMPOTENCY_KEY") or request.headers.get("Idempotency-Key")
    if raw is None:
        return None
    clave = str(raw).strip()
    if "\x00" in clave or not clave or len(clave) > 255:
        raise ValidationError({"Idempotency-Key": "Cabecera Idempotency-Key inválida."})
    return clave


def _empresa(request):
    """Retorna la empresa de trabajo del usuario.

    SEC-NEW-2: vía el helper vetado get_empresas_visible (no la property
    user.empresa), de modo que solo resuelve empresas que el usuario realmente ve.
    """
    return get_empresas_visible(request.user).first()


# ── Catálogo de proveedores ───────────────────────────────────────────────────


class ConectorProveedorViewSet(NulSafeFilterMixin, SuperuserWriteMixin, BaseModelViewSet):
    """Catálogo global de proveedores de integración.

    - **Lectura** (GET list/detail): cualquier usuario autenticado. Por defecto
      solo proveedores activos (para el selector de "Nuevo conector"); con
      ``?incluir_inactivos=true`` se ven todos (Panel SaaS).
    - **Escritura** (POST/PUT/PATCH/DELETE): solo el dueño del software
      (``es_superusuario_omni``), vía SuperuserWriteMixin. DELETE es borrado
      lógico (``activo=False``) porque las instancias lo referencian (FK PROTECT).
    """

    queryset = ConectorProveedor.objects.all().order_by("orden", "nombre")
    serializer_class = ConectorProveedorSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Lista pequeña; contrato de array plano (modal Nuevo conector)
    lookup_value_regex = "[0-9a-fA-F-]{36}"
    search_fields = ["nombre", "codigo"]
    ordering_fields = ["orden", "nombre", "estado", "codigo"]

    def get_queryset(self):
        qs = ConectorProveedor.objects.all().order_by("orden", "nombre")
        incluir = self.request.query_params.get("incluir_inactivos", "false")
        if incluir.lower() not in ("true", "1", "yes"):
            qs = qs.filter(activo=True)
        return qs

    def perform_destroy(self, instance):
        # Borrado lógico: el catálogo es global y las instancias lo referencian
        # (FK PROTECT). Solo el superusuario Omni (gate de SuperuserWriteMixin).
        self._assert_superuser()
        instance.activo = False
        instance.save(update_fields=["activo"])


# ── Instancias de conectores ─────────────────────────────────────────────────


@method_decorator(
    name="create",
    decorator=swagger_auto_schema(responses={201: ConectorInstanciaSerializer}),
)
@method_decorator(
    name="update",
    decorator=swagger_auto_schema(responses={200: ConectorInstanciaSerializer}),
)
@method_decorator(
    name="partial_update",
    decorator=swagger_auto_schema(responses={200: ConectorInstanciaSerializer}),
)
class ConectorInstanciaViewSet(NulSafeFilterMixin, BaseModelViewSet):
    """
    CRUD de conectores configurados por empresa.
    Acciones adicionales: test, sync, push-cobranza, jobs, entidades.
    """

    permission_classes = [IsAuthenticated]
    lookup_value_regex = "[0-9a-fA-F-]{36}"
    search_fields = ["nombre", "estado", "version_detectada", "id_proveedor__nombre", "id_proveedor__codigo"]
    ordering_fields = [
        "nombre",
        "estado",
        "ultimo_sync",
        "fecha_creacion",
        "fecha_actualizacion",
        "intervalo_sync_minutos",
    ]

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
        empresa = serializer.validated_data.get("id_empresa") or _empresa(self.request)
        if empresa is None:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("El usuario no tiene empresa asignada.")
        serializer.save(
            id_empresa=empresa,
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
        except Exception:
            # SEC-M4 (R-CODE-8): no filtrar el detalle interno al cliente.
            # mensaje_estado también se expone vía serializer → mensaje genérico.
            logger.exception("test_connection error [%s]", instancia.nombre)
            mensaje = "Error de conexión con el sistema externo. Revise la configuración del conector."
            instancia.estado = "error"
            instancia.mensaje_estado = mensaje
            instancia.ultimo_test_conexion = timezone.now()
            instancia.save(update_fields=["estado", "mensaje_estado", "ultimo_test_conexion"])
            return Response(
                {"success": False, "message": mensaje},
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

        instancia.save(
            update_fields=[
                "estado",
                "mensaje_estado",
                "version_detectada",
                "ultimo_test_conexion",
            ]
        )

        return Response(
            {
                "success": resultado.success,
                "message": resultado.message,
                "version": resultado.version,
                "details": resultado.details,
            }
        )

    @swagger_auto_schema(
        request_body=JobSincronizacionTriggerSerializer,
        responses={202: JobSincronizacionSerializer},
    )
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

        # Guardia opt-in para push outbound / bidireccional
        if direccion in ("outbound", "bidireccional") and not instancia.get_config().get("push_habilitado", False):
            return Response(
                {"error": "Push outbound deshabilitado en este conector (push_habilitado=False)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verificar que la entidad esté activa en la instancia
        if tipo_entidad not in instancia.entidades_activas and instancia.entidades_activas:
            return Response(
                {
                    "error": f"La entidad '{tipo_entidad}' no está habilitada en este conector. "
                    f"Entidades activas: {instancia.entidades_activas}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        idem_key = _leer_idempotency_key(request)

        # Crear el job (con deduplicación atómica si viene Idempotency-Key)
        parametros: dict = {}
        if sync_completo:
            parametros["sync_completo"] = True
        if desde_fecha:
            parametros["desde"] = str(desde_fecha)
        if idem_key:
            parametros["idempotency_key"] = idem_key

        with transaction.atomic():
            if idem_key:
                ConectorInstancia.objects.select_for_update().get(pk=instancia.pk)
                ventana = timezone.now() - timedelta(hours=24)
                existente = (
                    JobSincronizacion.objects.filter(
                        id_instancia=instancia,
                        id_instancia__id_empresa=instancia.id_empresa_id,
                        parametros__idempotency_key=idem_key,
                    )
                    .filter(Q(estado__in=["pendiente", "en_progreso"]) | Q(iniciado_en__gte=ventana))
                    .exclude(estado="fallido")
                    .order_by("-iniciado_en", "-id_job")
                    .first()
                )
                if existente is not None:
                    if existente.tipo_entidad != tipo_entidad or existente.direccion != direccion:
                        return Response(
                            {"error": "La Idempotency-Key ya fue usada con otro tipo o dirección de sincronización."},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        )
                    return Response(
                        JobSincronizacionSerializer(existente).data,
                        status=status.HTTP_202_ACCEPTED,
                    )

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
                "No se pudo encolar job en Celery — ejecutando sincrónicamente. Error: %s",
                exc,
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

    @swagger_auto_schema(
        request_body=PushCobranzaInputSerializer,
        responses={202: PushCobranzaResponseSerializer},
    )
    @action(detail=True, methods=["post"], url_path="push-cobranza")
    def push_cobranza(self, request, pk=None):
        """
        Dispara un push outbound de cobranza (pagos y/o gestiones de cobranza)
        hacia el sistema externo. Requiere ``push_habilitado=True``.
        Soporta cabecera ``Idempotency-Key`` para evitar ejecuciones duplicadas.
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

        if not instancia.get_config().get("push_habilitado", False):
            return Response(
                {"error": "Push outbound deshabilitado en este conector (push_habilitado=False)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = PushCobranzaInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        tipo = data.get("tipo", "todos")
        tipos = ["pagos", "gestiones_cobranza"] if tipo == "todos" else [tipo]
        ids_str = [str(uid) for uid in (data.get("ids") or [])]
        push_modo_pago = data.get("push_modo_pago")
        journal_id = data.get("journal_id")
        sync_completo = bool(data.get("sync_completo", False))

        idem_key = _leer_idempotency_key(request)
        firma_op = f"{tipo}:{','.join(sorted(ids_str))}:{push_modo_pago or ''}:{journal_id or ''}:{sync_completo}"

        base_params: dict = {}
        if ids_str:
            base_params["ids"] = ids_str
        if push_modo_pago:
            base_params["push_modo_pago"] = push_modo_pago
        if journal_id:
            base_params["journal_id"] = journal_id
        if sync_completo:
            base_params["sync_completo"] = True
        if idem_key:
            base_params["push_cobranza_key"] = idem_key
            base_params["push_cobranza_sig"] = firma_op

        jobs_creados: list[JobSincronizacion] = []
        with transaction.atomic():
            if idem_key:
                ConectorInstancia.objects.select_for_update().get(pk=instancia.pk)
                ventana = timezone.now() - timedelta(hours=24)
                previos = list(
                    JobSincronizacion.objects.filter(
                        id_instancia=instancia,
                        id_instancia__id_empresa=instancia.id_empresa_id,
                        parametros__push_cobranza_key=idem_key,
                    )
                    .filter(Q(estado__in=["pendiente", "en_progreso"]) | Q(iniciado_en__gte=ventana))
                    .exclude(estado="fallido")
                    .order_by("tipo_entidad", "-id_job")
                )
                if previos:
                    sig_previa = (previos[0].parametros or {}).get("push_cobranza_sig")
                    if sig_previa != firma_op:
                        return Response(
                            {"error": "La Idempotency-Key ya fue usada con otros parámetros."},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        )
                    return Response(
                        {
                            "mensaje": "Push de cobranza ya encolado/procesado para esta Idempotency-Key.",
                            "job_id": str(previos[0].id_job),
                            "jobs": JobSincronizacionSerializer(previos, many=True).data,
                        },
                        status=status.HTTP_202_ACCEPTED,
                    )

            for entidad in tipos:
                jobs_creados.append(
                    JobSincronizacion.objects.create(
                        id_instancia=instancia,
                        tipo_entidad=entidad,
                        direccion="outbound",
                        estado="pendiente",
                        iniciado_por=request.user,
                        parametros=dict(base_params),
                    )
                )

        for job in jobs_creados:
            try:
                from .tasks import ejecutar_job_sincronizacion

                task = ejecutar_job_sincronizacion.delay(str(job.id_job))
                job.celery_task_id = task.id
                job.save(update_fields=["celery_task_id"])
            except Exception as exc:
                logger.warning(
                    "No se pudo encolar push-cobranza en Celery — ejecutando sincrónicamente. Error: %s",
                    exc,
                )
                from .services.sync_engine import SyncEngine

                SyncEngine().ejecutar_job(job)
                job.refresh_from_db()

        return Response(
            {
                "mensaje": f"Push outbound de cobranza iniciado ({', '.join(tipos)}).",
                "job_id": str(jobs_creados[0].id_job) if jobs_creados else None,
                "jobs": JobSincronizacionSerializer(jobs_creados, many=True).data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], url_path="exportar")
    def exportar(self, request, pk=None):
        """
        Dispara una exportación outbound a Google Sheets de forma asíncrona.

        Body JSON (opcional):
          - tipos: ["contactos", "productos", ...] | null → usa entidades_activas
          - full: bool (default false). true → export completo (no incremental).

        Solo válido para instancias del proveedor 'google_sheets'. Los resultados
        se consultan puleando la acción ``jobs`` (JobSincronizacion outbound).
        """
        instancia = self.get_object()  # respeta aislamiento de empresa (get_queryset)

        if instancia.id_proveedor.codigo != "google_sheets":
            return Response(
                {
                    "error": "La exportación a hojas de cálculo solo está disponible "
                    "para conectores del proveedor 'google_sheets'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        tipos = request.data.get("tipos")
        full = bool(request.data.get("full", False))

        from .tasks import ejecutar_export_instancia

        task = ejecutar_export_instancia.delay(str(instancia.pk), tipos, incremental=not full)

        return Response(
            {
                "mensaje": "Exportación encolada. Consulta el historial de jobs " "para ver el progreso.",
                "task_id": task.id,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="jobs")
    def list_jobs(self, request, pk=None):
        """Lista el historial de jobs de sincronización de esta instancia."""
        instancia = self.get_object()
        jobs = JobSincronizacion.objects.filter(id_instancia=instancia).order_by("-iniciado_en")[:50]
        return Response(JobSincronizacionSerializer(jobs, many=True).data)

    @action(detail=True, methods=["get"], url_path="entidades/(?P<tipo_entidad>[^/.]+)")
    def list_entidades(self, request, pk=None, tipo_entidad=None):
        """Lista las entidades sincronizadas de un tipo específico."""
        if "\x00" in str(tipo_entidad or ""):
            raise ValidationError({"tipo_entidad": "Parámetro inválido."})
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
        if "\x00" in str(tipo_entidad or ""):
            raise ValidationError({"tipo_entidad": "Parámetro inválido."})
        instancia = self.get_object()

        try:
            conector = registry.get_connector(instancia)
        except Exception:
            # SEC-M4 (R-CODE-8): no filtrar el detalle interno al cliente.
            logger.exception("preview_data: error obteniendo conector [%s]", instancia.nombre)
            return Response(
                {"error": "No se pudo inicializar el conector. Revise la configuración."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

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
            return Response(
                {
                    "tipo_entidad": tipo_entidad,
                    "total_disponible": "desconocido (preview)",
                    "muestra": registros,
                }
            )
        except Exception:
            # SEC-M4 (R-CODE-8): no filtrar el detalle interno al cliente.
            logger.exception("preview_data error [%s / %s]", instancia.nombre, tipo_entidad)
            return Response(
                {"error": "Error consultando datos del sistema externo."},
                status=status.HTTP_502_BAD_GATEWAY,
            )


# ── Jobs de sincronización ────────────────────────────────────────────────────


class JobSincronizacionViewSet(NulSafeFilterMixin, ReadOnlyModelViewSet):
    """Vista de solo lectura para jobs de sincronización."""

    serializer_class = JobSincronizacionSerializer
    permission_classes = [IsAuthenticated]
    lookup_value_regex = "[0-9a-fA-F-]{36}"
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["tipo_entidad", "direccion", "estado", "id_instancia__nombre"]
    ordering_fields = [
        "iniciado_en",
        "completado_en",
        "estado",
        "tipo_entidad",
        "direccion",
        "total_registros",
    ]

    def get_queryset(self):
        empresas = get_empresas_visible(self.request.user)
        qs = (
            JobSincronizacion.objects.filter(id_instancia__id_empresa__in=empresas)
            .select_related("id_instancia", "iniciado_por")
            .order_by("-iniciado_en")
        )
        instancia_id = self.request.query_params.get("instancia")
        if instancia_id:
            qs = qs.filter(id_instancia_id=validar_uuid_param(instancia_id, "instancia"))
        for param_name, field_name in (
            ("estado", "estado"),
            ("tipo_entidad", "tipo_entidad"),
            ("direccion", "direccion"),
        ):
            val = self.request.query_params.get(param_name)
            if val:
                if "\x00" in val:
                    raise ValidationError({param_name: "Parámetro de consulta inválido."})
                qs = qs.filter(**{field_name: val.strip()})
        return qs

    @action(detail=True, methods=["get"], url_path="logs")
    def list_logs(self, request, pk=None):
        """Logs detallados de un job específico."""
        job = self.get_object()
        logs = LogDetalleSincronizacion.objects.filter(id_job=job).order_by("-creado_en")[:500]
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
        conectores = ConectorInstancia.objects.filter(id_empresa=empresa, activo=True).select_related("id_proveedor")

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

        return Response(
            {
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
            }
        )
