from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.viewsets import (
    BaseModelViewSet,
    EmpresaInjectMixin,
    get_empresa_primaria,
    get_empresas_visible,
)

from .models import BotUsuario, IngestaBot
from .serializers import (
    BotUsuarioSerializer,
    IngestaEntradaSerializer,
    IngestaSerializer,
)
from .services import ingesta as svc
from .services.handlers import HandlerError


class PuedeIngestar(permissions.BasePermission):
    """Solo cuentas de servicio con el permiso ``bots_ingest.ingestar`` (o superusuario)."""

    def has_permission(self, request, view):
        u = request.user
        return bool(
            u
            and u.is_authenticated
            and (u.is_superuser or u.has_perm("bots_ingest.ingestar"))
        )


class IngestaBotViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """``POST /ingest/`` recibe un borrador confirmado; ``GET`` lista lo recibido (p. ej. ``?estado=INCOMPLETO``)."""

    serializer_class = IngestaSerializer
    permission_classes = [PuedeIngestar]
    filterset_fields = ["estado", "kind"]

    def get_queryset(self):
        qs = IngestaBot.objects.filter(
            id_empresa__in=get_empresas_visible(self.request.user), activo=True
        )
        p = self.request.query_params
        if p.get("estado"):
            qs = qs.filter(estado=p["estado"])
        if p.get("kind"):
            qs = qs.filter(kind=p["kind"])
        return qs

    def create(self, request, *args, **kwargs):
        ser = IngestaEntradaSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            ing, creada = svc.ingerir(
                servicio=request.user,
                kind=d["kind"],
                draft=d["draft"],
                fuente=d["source"],
                idempotency_key=d["idempotency_key"],
            )
        except svc.UsuarioBotDesconocido as e:
            raise PermissionDenied(str(e)) from e
        except HandlerError as e:
            return Response({"error": str(e), "faltan": e.faltan}, status=e.status)
        return Response(
            IngestaSerializer(ing).data,
            status=status.HTTP_201_CREATED if creada else 200,
        )

    @action(detail=True, methods=["post"], url_path="completar")
    def completar(self, request, pk=None):
        """Completa un pago incompleto: ``{"cambios": {"referencia": "123"}}``."""
        ing = self.get_object()
        cambios = request.data.get("cambios")
        if not isinstance(cambios, dict) or not cambios:
            return Response(
                {"error": "Envía «cambios» con al menos un campo."}, status=400
            )
        try:
            ing = svc.completar(ing, cambios)
        except HandlerError as e:
            return Response({"error": str(e)}, status=e.status)
        return Response(IngestaSerializer(ing).data)


class BotUsuarioViewSet(EmpresaInjectMixin, BaseModelViewSet):
    """Alta de usuarios de Telegram autorizados (administración)."""

    serializer_class = BotUsuarioSerializer
    search_fields = ["nombre"]

    def get_queryset(self):
        return BotUsuario.objects.filter(
            id_empresa__in=get_empresas_visible(self.request.user), activo=True
        )

    def perform_create(self, serializer):
        empresa = get_empresa_primaria(self.request.user)
        usuario = serializer.validated_data["usuario"]
        if not usuario.empresas.filter(pk=empresa.pk).exists():
            raise PermissionDenied("El usuario no pertenece a tu empresa.")
        serializer.save(id_empresa=empresa)

    def perform_destroy(self, instance):
        instance.soft_delete()
