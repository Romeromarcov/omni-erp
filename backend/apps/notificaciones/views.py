from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.exceptions import domain_error_response
from apps.core.idempotency import idempotent
from apps.core.models import Notificacion
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import get_empresa_primaria, get_empresas_visible, validar_uuid_param

from .models import MensajeChatterDocumento
from .serializers import (
    CrearChatterInputSerializer,
    EnviarWhatsAppInputSerializer,
    MensajeChatterDocumentoSerializer,
    NotificacionSerializer,
)
from .whatsapp import WhatsAppBusinessError, enviar_whatsapp_documento


class NotificacionViewSet(GenericViewSet):
    """
    GET  /api/notificaciones/notificaciones/mis-notificaciones/            → últimas 20
    GET  /api/notificaciones/notificaciones/mis-notificaciones/?no_leidas=true
    PATCH /api/notificaciones/notificaciones/{id}/marcar-leida/
    """

    permission_classes = [IsAuthenticated]
    serializer_class = NotificacionSerializer

    def get_queryset(self):
        return Notificacion.objects.filter(id_usuario=self.request.user)

    @action(detail=False, methods=["get"], url_path="mis-notificaciones")
    def mis_notificaciones(self, request):
        qs = self.get_queryset()

        no_leidas = request.query_params.get("no_leidas", "").lower() in ("true", "1", "yes")
        if no_leidas:
            qs = qs.filter(leida=False)

        qs = qs.order_by("-fecha_creacion")[:20]
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="marcar-leida")
    def marcar_leida(self, request, pk=None):
        try:
            notificacion = self.get_queryset().get(pk=pk)
        except Notificacion.DoesNotExist:
            return Response({"detail": "No encontrada."}, status=status.HTTP_404_NOT_FOUND)

        notificacion.marcar_leida()
        serializer = self.get_serializer(notificacion)
        return Response(serializer.data)


def _resolver_empresa_notificacion(request, empresa_id=None):
    visibles = get_empresas_visible(request.user)
    raw_emp = (
        empresa_id
        or request.query_params.get("empresa")
        or (request.data.get("id_empresa") if isinstance(request.data, dict) else None)
    )
    if raw_emp:
        uid = validar_uuid_param(str(raw_emp), "id_empresa")
        emp = visibles.filter(pk=uid).first()
        if emp is None:
            raise ValidationError({"id_empresa": "Empresa fuera de su alcance."})
        return emp
    emp = get_empresa_primaria(request.user) or visibles.first()
    if emp is None:
        raise ValidationError({"id_empresa": "Usuario sin empresa asignada."})
    return emp


class ChatterDocumentoViewSet(viewsets.ViewSet):
    """Chatter interno y despacho WhatsApp Business sobre documentos comerciales/logísticos (Plan 09 Fase 8.1)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [*viewsets.ViewSet.throttle_classes, EscrituraRateThrottle]

    def list(self, request):
        empresa = _resolver_empresa_notificacion(request)
        qs = (
            MensajeChatterDocumento.objects.filter(id_empresa=empresa, activo=True)
            .select_related("autor")
            .order_by("-fecha_creacion")
        )
        tipo = request.query_params.get("tipo_documento")
        if tipo is not None:
            if "\x00" in tipo:
                raise ValidationError({"tipo_documento": "Parámetro inválido."})
            if tipo.strip():
                qs = qs.filter(tipo_documento=tipo.strip().upper())

        doc_id = request.query_params.get("documento_id")
        if doc_id is not None and doc_id.strip():
            qs = qs.filter(documento_id=validar_uuid_param(doc_id, "documento_id"))

        ser = MensajeChatterDocumentoSerializer(qs[:100], many=True)
        return Response({"empresa_id": str(empresa.pk), "mensajes": ser.data})

    @swagger_auto_schema(request_body=CrearChatterInputSerializer, responses={201: MensajeChatterDocumentoSerializer})
    @idempotent(scope="notificaciones:chatter_crear")
    def create(self, request):
        ser = CrearChatterInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        empresa = _resolver_empresa_notificacion(request, vd.get("id_empresa"))
        cuerpo = vd["cuerpo"].strip()
        if "\x00" in cuerpo or not cuerpo:
            raise ValidationError({"cuerpo": "El cuerpo del mensaje es obligatorio y no puede contener NUL."})

        msg = MensajeChatterDocumento.objects.create(
            id_empresa=empresa,
            tipo_documento=vd["tipo_documento"],
            documento_id=vd["documento_id"],
            autor=request.user,
            canal=vd["canal"],
            es_nota_interna=vd["es_nota_interna"],
            destinatario_telefono=vd.get("destinatario_telefono", "").strip(),
            cuerpo=cuerpo,
            estado_envio="REGISTRADO",
        )
        return Response(MensajeChatterDocumentoSerializer(msg).data, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        request_body=EnviarWhatsAppInputSerializer, responses={201: MensajeChatterDocumentoSerializer}
    )
    @idempotent(scope="notificaciones:chatter_whatsapp")
    @action(detail=False, methods=["post"], url_path="enviar-whatsapp")
    def enviar_whatsapp(self, request):
        ser = EnviarWhatsAppInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        empresa = _resolver_empresa_notificacion(request, vd.get("id_empresa"))
        try:
            msg = enviar_whatsapp_documento(
                empresa=empresa,
                tipo_documento=vd["tipo_documento"],
                documento_id=vd["documento_id"],
                telefono=vd["telefono"],
                cuerpo=vd.get("cuerpo", ""),
                plantilla=vd.get("plantilla", "libre"),
                contexto=vd.get("contexto") or {},
                autor=request.user,
            )
        except WhatsAppBusinessError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        return Response(MensajeChatterDocumentoSerializer(msg).data, status=status.HTTP_201_CREATED)
