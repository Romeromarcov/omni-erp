"""
Vistas del módulo SaaS (M10-T5).

Expone:
  - PlanViewSet:        Catálogo de planes (lectura pública, escritura solo superusuarios Omni).
  - SuscripcionViewSet: Suscripciones de empresa, con acciones cancelar/suspender.
"""
import datetime

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import Plan, Suscripcion, suscripcion_activa
from .serializers import PlanSerializer, SignupSerializer, SuscripcionSerializer

User = get_user_model()

# Duración del trial de auto-registro.
TRIAL_DIAS = 30


def _exigir_superusuario_omni(user, accion: str = "gestionar suscripciones") -> None:
    """
    Gate de escritura del negocio SaaS. Política (Plan C — C2):
      - Crear, modificar (PATCH/PUT) o eliminar suscripciones: SOLO el proveedor
        (es_superusuario_omni). Esto evita que un tenant se auto-asigne un plan o
        REACTIVE (PATCH estado=ACTIVA) una suscripción que el proveedor suspendió.
      - Cancelar / suspender la PROPIA suscripción: permitido al tenant
        (self-service), acotado por get_queryset a sus empresas visibles.
      - Leer: abierto y acotado por tenant (R-CODE-1).
    """
    if not getattr(user, "es_superusuario_omni", False):
        raise PermissionDenied(f"Solo superusuarios Omni pueden {accion}.")


class PlanViewSet(BaseModelViewSet):
    """
    Catálogo de planes SaaS.

    GET  /saas/planes/        — listar planes activos
    GET  /saas/planes/{pk}/   — detalle de un plan
    POST/PATCH/DELETE          — solo superusuarios Omni

    Solo se muestran planes activos por defecto.
    """

    queryset = Plan.objects.filter(activo=True)
    serializer_class = PlanSerializer
    search_fields = ["nombre", "nivel"]
    ordering_fields = ["precio_mensual", "nivel", "nombre"]
    ordering = ["precio_mensual"]

    def get_queryset(self):
        # Planes son globales (no por empresa); mostrar todos los activos
        incluir_inactivos = self.request.query_params.get("incluir_inactivos", "false")
        if incluir_inactivos.lower() in ("true", "1", "yes"):
            return Plan.objects.all()
        return Plan.objects.filter(activo=True)

    def perform_create(self, serializer):
        if not getattr(self.request.user, "es_superusuario_omni", False):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Solo superusuarios Omni pueden crear planes.")
        serializer.save()

    def perform_update(self, serializer):
        if not getattr(self.request.user, "es_superusuario_omni", False):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Solo superusuarios Omni pueden modificar planes.")
        serializer.save()

    def perform_destroy(self, instance):
        if not getattr(self.request.user, "es_superusuario_omni", False):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Solo superusuarios Omni pueden eliminar planes.")
        instance.activo = False
        instance.save(update_fields=["activo"])


class SuscripcionViewSet(BaseModelViewSet):
    """
    Gestión de suscripciones por empresa.

    GET  /saas/suscripciones/              — listar suscripciones de mis empresas
    POST /saas/suscripciones/              — crear nueva suscripción
    GET  /saas/suscripciones/{pk}/         — detalle
    PATCH /saas/suscripciones/{pk}/        — actualizar
    POST /saas/suscripciones/{pk}/cancelar/  — cancelar suscripción
    POST /saas/suscripciones/{pk}/suspender/ — suspender suscripción
    GET  /saas/suscripciones/activa/       — suscripción activa de mi empresa principal
    """

    queryset = Suscripcion.objects.all()
    serializer_class = SuscripcionSerializer
    search_fields = []
    ordering_fields = ["fecha_inicio", "fecha_fin", "estado"]
    ordering = ["-fecha_inicio"]

    def get_queryset(self):
        # R-CODE-1
        empresas = get_empresas_visible(self.request.user)
        qs = Suscripcion.objects.filter(id_empresa__in=empresas).select_related("id_plan", "id_empresa")

        # Filtros opcionales
        estado = self.request.query_params.get("estado")
        if estado:
            qs = qs.filter(estado=estado)
        empresa_id = self.request.query_params.get("empresa")
        if empresa_id:
            qs = qs.filter(id_empresa=empresa_id)

        return qs

    def perform_create(self, serializer):
        _exigir_superusuario_omni(self.request.user, "crear suscripciones")
        serializer.save()

    def perform_update(self, serializer):
        _exigir_superusuario_omni(self.request.user, "modificar suscripciones")
        serializer.save()

    def perform_destroy(self, instance):
        _exigir_superusuario_omni(self.request.user, "eliminar suscripciones")
        instance.delete()

    @action(detail=False, methods=["get"], url_path="activa")
    def activa(self, request):
        """
        GET /saas/suscripciones/activa/

        Retorna la suscripción activa de la primera empresa visible del usuario.
        Útil para el dashboard: ¿cuál es mi plan actual?
        """
        empresas = get_empresas_visible(request.user)
        empresa = empresas.first()
        if not empresa:
            return Response({"detail": "Sin empresa asignada."}, status=status.HTTP_404_NOT_FOUND)

        sus = suscripcion_activa(empresa)
        if not sus:
            return Response(
                {"detail": "Sin suscripción activa.", "empresa_id": str(empresa.id_empresa)},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(SuscripcionSerializer(sus).data)

    @action(detail=True, methods=["post"], url_path="cancelar")
    def cancelar(self, request, pk=None):
        """
        POST /saas/suscripciones/{pk}/cancelar/

        Cancela la suscripción. Body (opcional): {"notas": "motivo de cancelación"}

        Self-service: el tenant puede cancelar la suya (get_object la acota a sus
        empresas visibles); el proveedor puede cancelar cualquiera.
        """
        sus = self.get_object()
        if sus.estado in ("CANCELADA",):
            return Response({"detail": "La suscripción ya está cancelada."}, status=status.HTTP_400_BAD_REQUEST)
        notas = request.data.get("notas", "")
        sus.cancelar(notas=notas)
        return Response(SuscripcionSerializer(sus).data)

    @action(detail=True, methods=["post"], url_path="suspender")
    def suspender(self, request, pk=None):
        """
        POST /saas/suscripciones/{pk}/suspender/

        Suspende la suscripción (bloquea acceso sin cancelar definitivamente).

        Self-service: el tenant puede suspender la suya; el proveedor cualquiera.
        La REACTIVACIÓN (estado=ACTIVA) NO pasa por aquí — es un PATCH y queda
        restringida al proveedor en perform_update.
        """
        sus = self.get_object()
        if sus.estado in ("SUSPENDIDA", "CANCELADA"):
            return Response(
                {"detail": f"La suscripción ya está en estado {sus.estado}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sus.suspender()
        return Response(SuscripcionSerializer(sus).data)


class SignupView(APIView):
    """
    POST /api/saas/signup/ — auto-registro de un prospecto (Plan C — Fase C3).

    Endpoint PÚBLICO y con rate-limit. Crea, en una sola transacción:
      - una Empresa nueva,
      - su usuario administrador (es_superusuario_omni e is_staff forzados a
        False — nunca se aceptan del cliente),
      - una Suscripcion TRIAL de 30 días sobre un plan activo.

    No devuelve tokens: el frontend hace login con las credenciales recién
    creadas, reutilizando el flujo seguro de sesión (cookie httpOnly de refresh).
    """

    permission_classes = [AllowAny]
    authentication_classes = []  # endpoint público: no exigir ni procesar auth
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "signup"

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        plan = self._resolver_plan(data.get("plan_nivel"))
        if plan is None:
            return Response(
                {"detail": "No hay planes disponibles para el registro. "
                           "Contacte al proveedor."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        from apps.core.models import Empresa

        # localdate() (fecha en TIME_ZONE), NO now().date() (UTC con USE_TZ): si no,
        # cerca de medianoche UTC el trial nacería con fecha_inicio=mañana y
        # suscripcion_activa (que usa la fecha local) no lo vería como vigente.
        hoy = timezone.localdate()
        with transaction.atomic():
            empresa = Empresa.objects.create(
                nombre_legal=data["empresa_nombre_legal"],
                nombre_comercial=data.get("empresa_nombre_comercial") or "",
                identificador_fiscal=data.get("empresa_identificador_fiscal") or "",
                email_contacto=data.get("empresa_email") or "",
            )
            usuario = User(
                username=data["username"],
                email=data["email"],
                first_name=data.get("first_name") or "",
                last_name=data.get("last_name") or "",
                is_active=True,
                is_staff=False,
                es_superusuario_omni=False,
            )
            usuario.set_password(data["password"])
            usuario.save()
            usuario.empresas.add(empresa)

            suscripcion = Suscripcion.objects.create(
                id_empresa=empresa,
                id_plan=plan,
                estado="TRIAL",
                periodo="MENSUAL",
                fecha_inicio=hoy,
                fecha_fin=hoy + datetime.timedelta(days=TRIAL_DIAS),
            )

        return Response(
            {
                "empresa_id": str(empresa.id_empresa),
                "usuario_id": str(usuario.id),
                "username": usuario.username,
                "suscripcion_id": str(suscripcion.id_suscripcion),
                "plan": plan.nombre,
                "estado": suscripcion.estado,
                "trial_fin": suscripcion.fecha_fin.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _resolver_plan(nivel):
        """Plan activo para el trial: el del nivel pedido (más económico de ese
        nivel) o, si no se pidió nivel, el plan activo más económico."""
        qs = Plan.objects.filter(activo=True)
        if nivel:
            qs = qs.filter(nivel=nivel)
        return qs.order_by("precio_mensual").first()
