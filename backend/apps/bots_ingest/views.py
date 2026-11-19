from django.db import IntegrityError, transaction
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.capability_auth import (
    CapabilityTokenAuthentication,
    tiene_scope_capacidad,
)
from apps.core.exceptions import domain_error_response
from apps.core.viewsets import (
    BaseModelViewSet,
    EmpresaInjectMixin,
    get_empresa_primaria,
    get_empresas_visible,
)

from .models import BotBitacora, BotLatidoDiario, BotRegistro, BotUsuario, IngestaBot
from .serializers import (
    BotControlPatchSerializer,
    BotLatidoEntradaSerializer,
    BotUsuarioSerializer,
    IngestaEntradaSerializer,
    IngestaSerializer,
)
from .services import control as ctrl_svc
from .services import ingesta as svc
from .services.control import DatoControlInvalido
from .services.handlers import HandlerError

_AUTH_MAQUINA_Y_HUMANO = [
    JWTAuthentication,
    SessionAuthentication,
    CapabilityTokenAuthentication,
]


def _es_super(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "es_superusuario_omni", False))


def _empresa_requerida(user):
    empresa = get_empresa_primaria(user)
    if empresa is None:
        raise PermissionDenied("El usuario o token no tiene empresa activa asignada.")
    return empresa


class PuedeIngestar(permissions.BasePermission):
    """Enviar borradores: token ``bots:ingest`` o cuenta con ``bots_ingest.ingestar``.

    Consultar y completar lo ya recibido lo puede hacer staff o quien tenga permisos de bots.
    """

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        act = getattr(view, "action", None)
        if act == "create":
            return tiene_scope_capacidad(u, "bots:ingest") or _es_super(u) or u.has_perm("bots_ingest.ingestar")
        if _es_super(u) or u.has_perm("bots_ingest.ingestar"):
            return True
        if act in ("list", "retrieve"):
            return (
                u.is_staff
                or u.has_perm("bots_ingest.ver_bots")
                or u.has_perm("bots_ingest.gestionar_bots")
                or tiene_scope_capacidad(u, "bots:read")
            )
        if act in ("completar", "sincronizar"):
            return u.is_staff or u.has_perm("bots_ingest.gestionar_bots")
        return False


class PuedeEnviarLatido(permissions.BasePermission):
    """Latido periódico de procesos de bots: ``bots:heartbeat``, ``bots:ingest`` o cuenta de servicio."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return (
            tiene_scope_capacidad(u, "bots:heartbeat")
            or tiene_scope_capacidad(u, "bots:ingest")
            or _es_super(u)
            or u.has_perm("bots_ingest.ingestar")
        )


class PuedePanelBots(permissions.BasePermission):
    """Lectura del panel con ``ver_bots``/staff/``bots:read``; cambios con ``gestionar_bots``/staff/``bots:write``."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        if _es_super(u) or u.is_staff or u.has_perm("bots_ingest.gestionar_bots"):
            return True
        if tiene_scope_capacidad(u, "bots:write"):
            return True
        if request.method in permissions.SAFE_METHODS:
            return u.has_perm("bots_ingest.ver_bots") or tiene_scope_capacidad(u, "bots:read")
        return False


class IngestaBotViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """``POST /ingest/`` recibe un borrador confirmado; ``GET`` lista lo recibido (p. ej. ``?estado=INCOMPLETO``)."""

    authentication_classes = _AUTH_MAQUINA_Y_HUMANO
    serializer_class = IngestaSerializer
    permission_classes = [PuedeIngestar]
    filterset_fields = ["estado", "kind"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return IngestaBot.objects.none()
        qs = IngestaBot.objects.filter(id_empresa__in=get_empresas_visible(self.request.user), activo=True)
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
            return domain_error_response(e, status_code=e.status, extra={"faltan": e.faltan})
        return Response(
            IngestaSerializer(ing).data,
            status=status.HTTP_201_CREATED if creada else 200,
        )

    @action(detail=True, methods=["post"], url_path="completar")
    def completar(self, request, pk=None):
        """Completa un pago incompleto: ``{"cambios": {"referencia": "123"}}``."""
        ing = self.get_object()
        cambios = request.data.get("cambios") if isinstance(request.data, dict) else None
        if not isinstance(cambios, dict) or not cambios:
            return Response({"error": "Envía «cambios» con al menos un campo."}, status=400)
        try:
            ing = svc.completar(ing, cambios)
        except HandlerError as e:
            return domain_error_response(e, status_code=e.status)
        return Response(IngestaSerializer(ing).data)

    @action(detail=True, methods=["post"], url_path="sincronizar")
    def sincronizar(self, request, pk=None):
        """Reintenta el envío a Odoo (pedidos y pagos completos). Responde 202; es asíncrono."""
        from .services.odoo_push import KINDS_SINCRONIZABLES, debe_sincronizar
        from .tasks import encolar_sync

        ing = self.get_object()
        if ing.kind not in KINDS_SINCRONIZABLES:
            return Response({"error": "Este tipo de ingesta no se envía a Odoo."}, status=422)
        if ing.estado == IngestaBot.Estado.SINCRONIZADO:
            return Response({"error": "Ya está sincronizada con Odoo."}, status=409)
        if not debe_sincronizar(ing):
            return Response(
                {"error": "Faltan datos: complétala antes de enviarla a Odoo."},
                status=422,
            )
        encolar_sync(ing.pk)
        return Response(IngestaSerializer(ing).data, status=status.HTTP_202_ACCEPTED)


class BotUsuarioViewSet(EmpresaInjectMixin, BaseModelViewSet):
    """Administración multi-tenant de usuarios de Telegram autorizados por empresa."""

    serializer_class = BotUsuarioSerializer
    permission_classes = [PuedePanelBots]
    search_fields = ["nombre"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return BotUsuario.objects.none()
        return BotUsuario.objects.filter(id_empresa__in=get_empresas_visible(self.request.user), activo=True)

    @staticmethod
    def _resumen_usuario(inst: BotUsuario) -> dict:
        return {
            "telegram_user_id": inst.telegram_user_id,
            "usuario": str(inst.usuario_id),
            "nombre": inst.nombre,
            "bots": list(inst.bots or []),
        }

    def perform_create(self, serializer):
        empresa = _empresa_requerida(self.request.user)
        usuario = serializer.validated_data["usuario"]
        if not usuario.empresas.filter(pk=empresa.pk).exists():
            raise PermissionDenied("El usuario no pertenece a tu empresa.")
        try:
            with transaction.atomic():
                inst = serializer.save(id_empresa=empresa)
                ctrl_svc.registrar_bitacora(
                    empresa=empresa,
                    entidad=f"usuario:{inst.telegram_user_id}",
                    accion="alta",
                    antes={},
                    despues=self._resumen_usuario(inst),
                    actor=ctrl_svc.nombre_actor(self.request.user),
                )
        except IntegrityError as exc:
            raise ValidationError(
                {"telegram_user_id": "Este usuario de Telegram ya está vinculado a una cuenta activa."}
            ) from exc

    def perform_update(self, serializer):
        antes_obj: BotUsuario = serializer.instance
        antes = self._resumen_usuario(antes_obj)
        usuario = serializer.validated_data.get("usuario", antes_obj.usuario)
        if not usuario.empresas.filter(pk=antes_obj.id_empresa_id).exists():
            raise PermissionDenied("El usuario no pertenece a tu empresa.")
        try:
            with transaction.atomic():
                inst = serializer.save()
                despues = self._resumen_usuario(inst)
                if antes != despues:
                    ctrl_svc.registrar_bitacora(
                        empresa=inst.id_empresa,
                        entidad=f"usuario:{inst.telegram_user_id}",
                        accion="actualizar",
                        antes=antes,
                        despues=despues,
                        actor=ctrl_svc.nombre_actor(self.request.user),
                    )
        except IntegrityError as exc:
            raise ValidationError(
                {"telegram_user_id": "Este usuario de Telegram ya está vinculado a una cuenta activa."}
            ) from exc

    def perform_destroy(self, instance):
        antes = self._resumen_usuario(instance)
        with transaction.atomic():
            instance.soft_delete()
            ctrl_svc.registrar_bitacora(
                empresa=instance.id_empresa,
                entidad=f"usuario:{instance.telegram_user_id}",
                accion="baja",
                antes=antes,
                despues={},
                actor=ctrl_svc.nombre_actor(self.request.user),
            )


class BotHeartbeatView(APIView):
    """``POST /api/bots/heartbeat/`` — recibe latido del bot y devuelve su configuración vigente."""

    authentication_classes = _AUTH_MAQUINA_Y_HUMANO
    permission_classes = [PuedeEnviarLatido]

    def post(self, request):
        empresa = _empresa_requerida(request.user)
        ser = BotLatidoEntradaSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        cfg = ctrl_svc.registrar_latido(
            empresa=empresa,
            codigo=d["bot"],
            nombre=d.get("nombre", ""),
            version=d.get("version", ""),
            estado=d.get("estado") or {},
        )
        return Response(cfg, status=status.HTTP_200_OK)


class BotControlViewSet(viewsets.ViewSet):
    """Plano de control multi-tenant de bots (flota, detalle y configuración auditada)."""

    authentication_classes = _AUTH_MAQUINA_Y_HUMANO
    permission_classes = [PuedePanelBots]
    lookup_field = "codigo"

    def list(self, request):
        empresa = _empresa_requerida(request.user)
        return Response({"items": ctrl_svc.listar_bots(empresa)})

    def retrieve(self, request, codigo=None):
        empresa = _empresa_requerida(request.user)
        try:
            return Response(ctrl_svc.detalle_bot(empresa, str(codigo or "")))
        except DatoControlInvalido as exc:
            return domain_error_response(exc, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

    def partial_update(self, request, codigo=None):
        empresa = _empresa_requerida(request.user)
        ser = BotControlPatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            detalle = ctrl_svc.actualizar_bot(
                empresa=empresa,
                codigo=str(codigo or ""),
                cambios=ser.validated_data,
                actor=ctrl_svc.nombre_actor(request.user),
            )
        except DatoControlInvalido as exc:
            return domain_error_response(exc, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        return Response(detalle)


class BotDestinosView(APIView):
    """``GET /api/bots/destinos/`` — resumen de salud de Omni, CxC, Gemini y cola por empresa."""

    authentication_classes = _AUTH_MAQUINA_Y_HUMANO
    permission_classes = [PuedePanelBots]

    def get(self, request):
        empresa = _empresa_requerida(request.user)
        return Response(ctrl_svc.resumen_destinos(empresa))


class BotBitacoraView(APIView):
    """``GET /api/bots/bitacora/`` — historial auditable de cambios del panel de bots."""

    authentication_classes = _AUTH_MAQUINA_Y_HUMANO
    permission_classes = [PuedePanelBots]

    def get(self, request):
        empresa = _empresa_requerida(request.user)
        entidad = (request.query_params.get("entidad") or "").replace("\x00", "").strip() or None
        raw_lim = request.query_params.get("limite", "50")
        try:
            limite = int(raw_lim)
        except (TypeError, ValueError):
            limite = 50
        return Response({"items": ctrl_svc.listar_bitacora(empresa, entidad=entidad, limite=limite)})


__all__ = [
    "BotBitacora",
    "BotBitacoraView",
    "BotControlViewSet",
    "BotDestinosView",
    "BotHeartbeatView",
    "BotLatidoDiario",
    "BotRegistro",
    "BotUsuarioViewSet",
    "IngestaBotViewSet",
]
