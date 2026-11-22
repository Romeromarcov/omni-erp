"""Vistas públicas y autenticadas de Omni Connect (S2 + S3)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import domain_error_response
from apps.core.models import Empresa, Usuarios
from apps.core.viewsets import (
    ActiveFilterMixin,
    BaseModelViewSet,
    NulSafeFilterMixin,
    get_empresa_primaria,
    get_empresas_visible,
    validar_uuid_param,
)

from .analytics import obtener_analiticas_connect
from .models import Perfil, Tarjeta
from .qr import (
    construir_url_publica_perfil,
    generar_qr_png,
    generar_qr_svg,
    sanitizar_nombre_archivo_qr,
)
from .serializers import (
    ConnectAnaliticasSerializer,
    MiPerfilSerializer,
    PerfilSerializer,
    PublicLeadCreateResponseSerializer,
    PublicLeadCreateSerializer,
    PublicPerfilSerializer,
    TarjetaAsignarInputSerializer,
    TarjetaSerializer,
)
from .services import (
    TEXTO_CONSENTIMIENTO_DEFAULT,
    ConnectError,
    ConsentimientoRequeridoError,
    PerfilNoEncontradoError,
    activar_tarjeta,
    asignar_tarjeta,
    capturar_lead_publico,
    desactivar_tarjeta,
    generar_vcard,
    marcar_tarjeta_perdida,
    obtener_ip_cliente,
    registrar_toque_publico,
    resolver_origen_publico,
    resolver_perfil_publico,
    sanitizar_nombre_archivo_vcard,
    usuario_es_admin_empresa,
)
from .throttles import ConnectLeadThrottle, ConnectPublicoThrottle

_UID_PARAM = openapi.Parameter(
    "uid",
    openapi.IN_QUERY,
    description="UID hexadecimal de la tarjeta NFC física (opcional).",
    type=openapi.TYPE_STRING,
    required=False,
)
_ORIGEN_PARAM = openapi.Parameter(
    "origen",
    openapi.IN_QUERY,
    description="Origen de visita pública: NFC, QR o ENLACE (opcional).",
    type=openapi.TYPE_STRING,
    required=False,
)
_EMPRESA_ID_PARAM = openapi.Parameter(
    "empresa_id",
    openapi.IN_QUERY,
    description="UUID de la empresa visible activa (opcional).",
    type=openapi.TYPE_STRING,
    format=openapi.FORMAT_UUID,
    required=False,
)
_FORMATO_QR_PARAM = openapi.Parameter(
    "formato",
    openapi.IN_QUERY,
    description="Formato de salida del código QR: svg (defecto) o png.",
    type=openapi.TYPE_STRING,
    enum=["svg", "png"],
    required=False,
)
_ANALITICAS_PARAMS = [
    _EMPRESA_ID_PARAM,
    openapi.Parameter(
        "desde",
        openapi.IN_QUERY,
        description="Fecha inicial inclusive (YYYY-MM-DD).",
        type=openapi.TYPE_STRING,
        format=openapi.FORMAT_DATE,
        required=False,
    ),
    openapi.Parameter(
        "hasta",
        openapi.IN_QUERY,
        description="Fecha final inclusive (YYYY-MM-DD).",
        type=openapi.TYPE_STRING,
        format=openapi.FORMAT_DATE,
        required=False,
    ),
    openapi.Parameter(
        "dias",
        openapi.IN_QUERY,
        description="Ventana en días (1..365, defecto 30) si no se especifica rango completo.",
        type=openapi.TYPE_INTEGER,
        required=False,
    ),
    openapi.Parameter(
        "perfil_id",
        openapi.IN_QUERY,
        description="UUID de un perfil Connect de la empresa para filtrar métricas.",
        type=openapi.TYPE_STRING,
        format=openapi.FORMAT_UUID,
        required=False,
    ),
]


class VCardRenderer(BaseRenderer):
    """Permite negociación ``Accept: text/vcard`` sin rechazar con 406."""

    media_type = "text/vcard"
    format = "vcf"
    charset = "utf-8"

    def render(self, data: Any, accepted_media_type: str | None = None, renderer_context: Any = None) -> bytes:
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            return data.encode(self.charset)
        return str(data or "").encode(self.charset)


class SvgRenderer(BaseRenderer):
    """Permite negociación ``Accept: image/svg+xml`` en descargas QR."""

    media_type = "image/svg+xml"
    format = "svg"
    charset = "utf-8"

    def render(self, data: Any, accepted_media_type: str | None = None, renderer_context: Any = None) -> bytes:
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            return data.encode(self.charset)
        return str(data or "").encode(self.charset)


class PngRenderer(BaseRenderer):
    """Permite negociación ``Accept: image/png`` en descargas QR."""

    media_type = "image/png"
    format = "png"
    charset = None
    render_style = "binary"

    def render(self, data: Any, accepted_media_type: str | None = None, renderer_context: Any = None) -> bytes:
        if isinstance(data, bytes):
            return data
        return bytes(str(data or ""), "utf-8")


def _respuesta_qr(url: str, *, nombre_base: str, formato_raw: str | None) -> HttpResponse:
    formato = (formato_raw or "svg").strip().lower()
    if formato not in ("svg", "png"):
        raise ValidationError({"formato": "Formato inválido. Use 'svg' o 'png'."})
    filename = sanitizar_nombre_archivo_qr(nombre_base)
    if formato == "png":
        contenido_png = generar_qr_png(url)
        resp = HttpResponse(contenido_png, content_type="image/png")
        resp["Content-Disposition"] = f'inline; filename="{filename}.png"'
        return resp
    contenido_svg = generar_qr_svg(url)
    resp = HttpResponse(contenido_svg, content_type="image/svg+xml; charset=utf-8")
    resp["Content-Disposition"] = f'inline; filename="{filename}.svg"'
    return resp


def _validar_request_sin_nul(request: Request, slug: str | None = None) -> None:
    if slug is not None and "\x00" in slug:
        raise ValidationError({"slug": "Slug inválido."})
    for key, values in request.query_params.lists():
        if "\x00" in str(key):
            raise ValidationError({"error": "Parámetro de consulta inválido."})
        for val in values:
            if "\x00" in str(val):
                raise ValidationError({key: "Parámetro de consulta inválido."})


def _validar_payload_sin_nul(data: Any, campo: str = "error") -> None:
    if isinstance(data, Mapping):
        for key, val in data.items():
            if "\x00" in str(key):
                raise ValidationError({campo: "Parámetro inválido."})
            _validar_payload_sin_nul(val, str(key))
    elif isinstance(data, (list, tuple)):
        for item in data:
            _validar_payload_sin_nul(item, campo)
    elif isinstance(data, str) and "\x00" in data:
        raise ValidationError({campo: "El valor contiene caracteres inválidos."})


def _extraer_honeypot_activo(data: Any) -> bool:
    if not isinstance(data, Mapping):
        return False
    for campo in ("website", "company_url"):
        val = data.get(campo)
        if isinstance(val, str) and val.strip() != "":
            return True
    return False


def _manejar_django_validation(exc: DjangoValidationError) -> ValidationError:
    if hasattr(exc, "message_dict"):
        return ValidationError(exc.message_dict)
    return ValidationError(exc.messages)


class PublicPerfilDetailView(APIView):
    """GET /api/public/connect/<slug>/ — Perfil digital público y registro de toque."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ConnectPublicoThrottle]
    throttle_scope = "connect_publico"

    @swagger_auto_schema(
        operation_summary="Detalle público del perfil Connect y registro de toque",
        manual_parameters=[_UID_PARAM, _ORIGEN_PARAM],
        responses={200: PublicPerfilSerializer, 400: "Parámetros inválidos", 404: "Perfil no encontrado"},
    )
    def get(self, request: Request, slug: str) -> Response:
        _validar_request_sin_nul(request, slug)
        uid = request.query_params.get("uid")
        origen_param = request.query_params.get("origen") or request.query_params.get("src")

        try:
            perfil = resolver_perfil_publico(slug, uid=uid)
        except DjangoValidationError as exc:
            raise _manejar_django_validation(exc) from exc
        except PerfilNoEncontradoError:
            return Response({"detail": "Perfil no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        origen = resolver_origen_publico(origen_param, tiene_tarjeta=perfil["tarjeta_id"] is not None)
        registrar_toque_publico(
            perfil_id=perfil["id_perfil"],
            empresa_id=perfil["id_empresa_id"],
            tarjeta_id=perfil["tarjeta_id"],
            origen=origen,
            user_agent=str(request.META.get("HTTP_USER_AGENT", "") or ""),
            client_ip=obtener_ip_cliente(request),
        )

        payload = {
            "slug": perfil["slug"],
            "nombre_publico": perfil["nombre_publico"],
            "cargo": perfil["cargo"],
            "bio": perfil["bio"],
            "telefono_publico": perfil["telefono_publico"],
            "email_publico": perfil["email_publico"],
            "tema": perfil["tema"],
            "botones": perfil["botones"],
            "empresa_nombre": perfil["empresa_nombre"],
            "acepta_leads": True,
            "consentimiento_texto": TEXTO_CONSENTIMIENTO_DEFAULT,
        }
        return Response(PublicPerfilSerializer(payload).data, status=status.HTTP_200_OK)


class PublicPerfilVCardView(APIView):
    """GET /api/public/connect/<slug>/vcard/ — Descarga de contacto vCard RFC 6350."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ConnectPublicoThrottle]
    throttle_scope = "connect_publico"
    renderer_classes = [JSONRenderer, VCardRenderer]

    @swagger_auto_schema(
        operation_summary="Descarga de archivo vCard (.vcf) del perfil público",
        manual_parameters=[_UID_PARAM],
        produces=["text/vcard"],
        responses={
            200: openapi.Response(
                description="Archivo vCard RFC 6350",
                schema=openapi.Schema(type=openapi.TYPE_STRING),
            ),
            400: "Parámetros inválidos",
            404: "Perfil no encontrado",
        },
    )
    def get(self, request: Request, slug: str) -> HttpResponse | Response:
        _validar_request_sin_nul(request, slug)
        uid = request.query_params.get("uid")

        try:
            perfil = resolver_perfil_publico(slug, uid=uid)
        except DjangoValidationError as exc:
            raise _manejar_django_validation(exc) from exc
        except PerfilNoEncontradoError:
            return Response({"detail": "Perfil no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        vcard = generar_vcard(perfil)
        filename = sanitizar_nombre_archivo_vcard(perfil["slug"])
        response = HttpResponse(vcard, content_type="text/vcard; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}.vcf"'
        return response


class PublicLeadCreateView(APIView):
    """POST /api/public/connect/<slug>/leads/ — Captura pública de lead con consentimiento."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ConnectLeadThrottle]
    throttle_scope = "connect_lead"

    @swagger_auto_schema(
        operation_summary="Captura pública de lead desde perfil Omni Connect",
        manual_parameters=[_UID_PARAM, _ORIGEN_PARAM],
        request_body=PublicLeadCreateSerializer,
        responses={
            201: PublicLeadCreateResponseSerializer,
            400: "Datos o consentimiento inválidos",
            404: "Perfil no encontrado",
            429: "Límite de envíos excedido",
        },
    )
    def post(self, request: Request, slug: str) -> Response:
        _validar_request_sin_nul(request, slug)
        _validar_payload_sin_nul(request.data)

        uid_query = request.query_params.get("uid")
        origen_query = request.query_params.get("origen") or request.query_params.get("src")

        # Si el campo honeypot viene relleno, verificar existencia del perfil activo y
        # responder 201 neutro silenciosamente sin revelar detección ni crear Lead/Toque.
        if _extraer_honeypot_activo(request.data):
            uid_body = ""
            if isinstance(request.data, Mapping):
                uid_body = str(request.data.get("uid") or request.data.get("uid_chip") or "").strip()
            try:
                resolver_perfil_publico(slug, uid=uid_body or uid_query)
            except DjangoValidationError as exc:
                raise _manejar_django_validation(exc) from exc
            except PerfilNoEncontradoError:
                return Response({"detail": "Perfil no encontrado."}, status=status.HTTP_404_NOT_FOUND)
            return Response(
                {"ok": True, "mensaje": "Contacto enviado correctamente."},
                status=status.HTTP_201_CREATED,
            )

        serializer = PublicLeadCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = dict(serializer.validated_data)

        uid = (datos.get("uid") or datos.get("uid_chip") or uid_query or "").strip() or None
        if not datos.get("fuente") and not datos.get("origen") and origen_query:
            datos["origen"] = origen_query

        try:
            resultado = capturar_lead_publico(
                slug=slug,
                datos=datos,
                uid=uid,
                client_ip=obtener_ip_cliente(request),
                user_agent=str(request.META.get("HTTP_USER_AGENT", "") or ""),
            )
        except DjangoValidationError as exc:
            raise _manejar_django_validation(exc) from exc
        except PerfilNoEncontradoError:
            return Response({"detail": "Perfil no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except (ConsentimientoRequeridoError, ConnectError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")

        return Response(
            {"ok": bool(resultado["ok"]), "mensaje": str(resultado["mensaje"])},
            status=status.HTTP_201_CREATED,
        )


def _resolver_empresa_usuario(request: Request) -> Empresa:
    """Resuelve la empresa activa visible del usuario autenticado (validando pertenencia)."""
    user = request.user
    empresas = get_empresas_visible(user)
    if not empresas.exists():
        raise PermissionDenied("El usuario no tiene empresa asignada.")

    empresa_param = request.query_params.get("empresa_id") or request.query_params.get("empresa")
    if empresa_param is not None:
        empresa_uuid = uuid.UUID(validar_uuid_param(empresa_param, "empresa_id"))
        empresa = empresas.filter(pk=empresa_uuid).first()
        if empresa is None:
            raise PermissionDenied("No tienes acceso a la empresa solicitada.")
        return empresa

    empresa_primaria = get_empresa_primaria(user)
    if empresa_primaria is None:
        raise PermissionDenied("El usuario no tiene empresa asignada.")
    return empresa_primaria


class PerfilViewSet(NulSafeFilterMixin, BaseModelViewSet):
    """CRUD multi-tenant de perfiles digitales Connect y gestión de ``mi-perfil``."""

    queryset = Perfil.objects.all()
    serializer_class = PerfilSerializer
    search_fields = ["slug", "nombre_publico", "cargo", "email_publico"]
    ordering_fields = ["nombre_publico", "slug", "fecha_creacion"]
    ordering = ["nombre_publico"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Perfil.objects.none()
        empresas = get_empresas_visible(self.request.user)
        qs = Perfil.objects.filter(id_empresa__in=empresas).select_related("id_empresa", "usuario")
        empresa_param = self.request.query_params.get("empresa") or self.request.query_params.get("empresa_id")
        if empresa_param:
            empresa_uuid = validar_uuid_param(empresa_param, "empresa_id")
            qs = qs.filter(id_empresa_id=empresa_uuid)
        return qs

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if lookup_url_kwarg in self.kwargs:
            validar_uuid_param(self.kwargs[lookup_url_kwarg], self.lookup_field)
        return super().get_object()

    def _verificar_permisos_escritura(
        self,
        *,
        empresa_id: uuid.UUID,
        target_usuario_id: uuid.UUID,
        cambiando_bloqueo: bool,
        cambiando_tema_bloqueado: bool,
    ) -> None:
        user = self.request.user
        es_admin = usuario_es_admin_empresa(user, empresa_id)
        if str(target_usuario_id) != str(user.pk) and not es_admin:
            raise PermissionDenied("No tienes permiso para modificar el perfil de otro usuario.")
        if cambiando_bloqueo and not es_admin:
            raise PermissionDenied("Solo un administrador puede modificar plantilla_bloqueada.")
        if cambiando_tema_bloqueado and not es_admin:
            raise PermissionDenied("La plantilla está bloqueada por el administrador de tu empresa.")

    def _guardar_perfil_validado(self, instancia: Perfil) -> None:
        try:
            with transaction.atomic():
                instancia.full_clean()
                instancia.save()
        except DjangoValidationError as exc:
            raise _manejar_django_validation(exc) from exc
        except IntegrityError as exc:
            raise ValidationError(
                {"detail": "Ya existe un perfil con ese slug o para ese usuario en la empresa."}
            ) from exc

    def perform_create(self, serializer):
        data = serializer.validated_data
        empresa = data.get("id_empresa") or get_empresa_primaria(self.request.user)
        if empresa is None:
            raise PermissionDenied("El usuario no tiene empresa asignada.")
        usuario = data.get("usuario") or self.request.user

        self._verificar_permisos_escritura(
            empresa_id=empresa.pk,
            target_usuario_id=usuario.pk,
            cambiando_bloqueo=bool(data.get("plantilla_bloqueada", False)),
            cambiando_tema_bloqueado=False,
        )

        instancia = Perfil(
            id_empresa=empresa,
            usuario=usuario,
            slug=data["slug"],
            nombre_publico=data["nombre_publico"],
            cargo=data.get("cargo", ""),
            bio=data.get("bio", ""),
            telefono_publico=data.get("telefono_publico", ""),
            email_publico=data.get("email_publico", ""),
            tema=data.get("tema", "CLASICO"),
            botones=data.get("botones", []),
            plantilla_bloqueada=bool(data.get("plantilla_bloqueada", False)),
            activo=bool(data.get("activo", True)),
        )
        self._guardar_perfil_validado(instancia)
        serializer.instance = instancia

    def perform_update(self, serializer):
        instancia: Perfil = serializer.instance
        data = serializer.validated_data
        es_admin = usuario_es_admin_empresa(self.request.user, instancia.id_empresa_id)

        if "id_empresa" in data and data["id_empresa"].pk != instancia.id_empresa_id:
            raise ValidationError({"id_empresa": "La empresa de un perfil Connect es inmutable."})
        if "usuario" in data and data["usuario"].pk != instancia.usuario_id and not es_admin:
            raise PermissionDenied("No puedes reasignar el propietario del perfil.")

        cambiando_bloqueo = (
            "plantilla_bloqueada" in data and bool(data["plantilla_bloqueada"]) != instancia.plantilla_bloqueada
        )
        cambiando_tema_bloqueado = instancia.plantilla_bloqueada and "tema" in data and data["tema"] != instancia.tema

        self._verificar_permisos_escritura(
            empresa_id=instancia.id_empresa_id,
            target_usuario_id=instancia.usuario_id,
            cambiando_bloqueo=cambiando_bloqueo,
            cambiando_tema_bloqueado=cambiando_tema_bloqueado,
        )

        for campo, valor in data.items():
            setattr(instancia, campo, valor)
        self._guardar_perfil_validado(instancia)

    def perform_destroy(self, instance: Perfil) -> None:
        es_admin = usuario_es_admin_empresa(self.request.user, instance.id_empresa_id)
        if str(instance.usuario_id) != str(self.request.user.pk) and not es_admin:
            raise PermissionDenied("No tienes permiso para desactivar el perfil de otro usuario.")
        instance.soft_delete()

    @swagger_auto_schema(
        method="get",
        operation_summary="Obtiene el perfil Connect propio del usuario autenticado",
        manual_parameters=[_EMPRESA_ID_PARAM],
        responses={200: MiPerfilSerializer, 403: "Sin acceso", 404: "Perfil no configurado"},
    )
    @swagger_auto_schema(
        method="patch",
        operation_summary="Crea o actualiza el perfil Connect propio del usuario autenticado",
        manual_parameters=[_EMPRESA_ID_PARAM],
        request_body=MiPerfilSerializer,
        responses={200: MiPerfilSerializer, 201: MiPerfilSerializer, 400: "Datos inválidos", 403: "Sin acceso"},
    )
    @action(detail=False, methods=["get", "patch"], url_path="mi-perfil", serializer_class=MiPerfilSerializer)
    def mi_perfil(self, request: Request) -> Response:
        _validar_request_sin_nul(request)
        _validar_payload_sin_nul(request.data)
        empresa = _resolver_empresa_usuario(request)
        user = request.user
        if not isinstance(user, Usuarios):
            raise PermissionDenied("Se requiere un usuario autenticado.")

        if not user.empresas.filter(pk=empresa.pk).exists():
            raise PermissionDenied("El usuario no pertenece a la empresa activa para operar su perfil Connect.")

        perfil = Perfil.objects.filter(id_empresa=empresa, usuario=user).first()

        if request.method == "GET":
            if perfil is None:
                return Response(
                    {"detail": "Aún no tienes perfil Connect configurado en esta empresa."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(MiPerfilSerializer(perfil).data, status=status.HTTP_200_OK)

        # PATCH: actualizar existente o crear si aún no existe.
        creado = perfil is None
        serializer = MiPerfilSerializer(
            instance=perfil,
            data=request.data,
            partial=not creado,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        es_admin = usuario_es_admin_empresa(user, empresa.pk)
        if creado:
            if bool(data.get("plantilla_bloqueada", False)) and not es_admin:
                raise PermissionDenied("Solo un administrador puede activar plantilla_bloqueada.")
            instancia = Perfil(
                id_empresa=empresa,
                usuario=user,
                slug=data["slug"],
                nombre_publico=data["nombre_publico"],
                cargo=data.get("cargo", ""),
                bio=data.get("bio", ""),
                telefono_publico=data.get("telefono_publico", ""),
                email_publico=data.get("email_publico", ""),
                tema=data.get("tema", "CLASICO"),
                botones=data.get("botones", []),
                plantilla_bloqueada=bool(data.get("plantilla_bloqueada", False)),
            )
            self._guardar_perfil_validado(instancia)
            return Response(MiPerfilSerializer(instancia).data, status=status.HTTP_201_CREATED)

        assert perfil is not None  # noqa: S101 — narrowing para mypy
        cambiando_bloqueo = (
            "plantilla_bloqueada" in data and bool(data["plantilla_bloqueada"]) != perfil.plantilla_bloqueada
        )
        cambiando_tema_bloqueado = perfil.plantilla_bloqueada and "tema" in data and data["tema"] != perfil.tema
        if cambiando_bloqueo and not es_admin:
            raise PermissionDenied("Solo un administrador puede modificar plantilla_bloqueada.")
        if cambiando_tema_bloqueado and not es_admin:
            raise PermissionDenied("La plantilla está bloqueada por el administrador de tu empresa.")

        for campo, valor in data.items():
            setattr(perfil, campo, valor)
        if not perfil.activo and "activo" not in data:
            # Si el perfil había sido desactivado, editar/guardar en mi-perfil lo reactiva.
            perfil.activo = True
        self._guardar_perfil_validado(perfil)
        return Response(MiPerfilSerializer(perfil).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method="get",
        operation_summary="Genera y descarga el código QR (SVG o PNG) del perfil Connect",
        manual_parameters=[_FORMATO_QR_PARAM],
        produces=["image/svg+xml", "image/png"],
        responses={
            200: openapi.Response(
                description="Código QR en formato SVG o PNG",
                schema=openapi.Schema(type=openapi.TYPE_STRING),
            ),
            400: "Formato o perfil inválido",
            404: "Perfil no encontrado",
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="qr",
        renderer_classes=[JSONRenderer, SvgRenderer, PngRenderer],
    )
    def qr(self, request: Request, pk: str | None = None) -> HttpResponse | Response:
        _validar_request_sin_nul(request)
        perfil = self.get_object()
        try:
            url = construir_url_publica_perfil(perfil.slug, origen="QR")
            return _respuesta_qr(
                url,
                nombre_base=f"qr-{perfil.slug}",
                formato_raw=request.query_params.get("formato"),
            )
        except ConnectError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")

    @swagger_auto_schema(
        method="get",
        operation_summary="Genera y descarga el código QR (SVG o PNG) del perfil propio del usuario",
        manual_parameters=[_EMPRESA_ID_PARAM, _FORMATO_QR_PARAM],
        produces=["image/svg+xml", "image/png"],
        responses={
            200: openapi.Response(
                description="Código QR en formato SVG o PNG",
                schema=openapi.Schema(type=openapi.TYPE_STRING),
            ),
            400: "Formato inválido",
            404: "Perfil no configurado",
        },
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="mi-perfil/qr",
        renderer_classes=[JSONRenderer, SvgRenderer, PngRenderer],
    )
    def mi_perfil_qr(self, request: Request) -> HttpResponse | Response:
        _validar_request_sin_nul(request)
        empresa = _resolver_empresa_usuario(request)
        user = request.user
        if not isinstance(user, Usuarios):
            raise PermissionDenied("Se requiere un usuario autenticado.")
        perfil = Perfil.objects.filter(id_empresa=empresa, usuario=user).first()
        if perfil is None:
            return Response(
                {"detail": "Aún no tienes perfil Connect configurado en esta empresa."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            url = construir_url_publica_perfil(perfil.slug, origen="QR")
            return _respuesta_qr(
                url,
                nombre_base=f"qr-{perfil.slug}",
                formato_raw=request.query_params.get("formato"),
            )
        except ConnectError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")


class ConnectAnaliticasView(NulSafeFilterMixin, APIView):
    """GET /api/connect/analiticas/ — Analíticas agregadas multi-tenant de Omni Connect (S10)."""

    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Analíticas agregadas de toques, leads y conversión de Omni Connect",
        manual_parameters=_ANALITICAS_PARAMS,
        responses={
            200: ConnectAnaliticasSerializer,
            400: "Parámetros de rango o filtros inválidos",
            403: "Sin acceso a la empresa solicitada",
            404: "Perfil no encontrado en la empresa",
        },
    )
    def get(self, request: Request) -> Response:
        _validar_request_sin_nul(request)
        empresa = _resolver_empresa_usuario(request)
        desde = request.query_params.get("desde")
        hasta = request.query_params.get("hasta")
        dias_raw = request.query_params.get("dias")
        perfil_raw = request.query_params.get("perfil_id")
        perfil_uuid = validar_uuid_param(perfil_raw, "perfil_id") if perfil_raw else None

        try:
            datos = obtener_analiticas_connect(
                empresa,
                desde=desde,
                hasta=hasta,
                perfil_id=perfil_uuid,
                dias=dias_raw if dias_raw is not None else 30,
            )
        except PerfilNoEncontradoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_404_NOT_FOUND, key="detail")
        except ConnectError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        except DjangoValidationError as exc:
            raise _manejar_django_validation(exc) from exc

        return Response(ConnectAnaliticasSerializer(datos).data, status=status.HTTP_200_OK)


class TarjetaViewSet(NulSafeFilterMixin, ActiveFilterMixin, BaseModelViewSet):
    """CRUD multi-tenant y ciclo de vida de tarjetas NFC físicas (Plan 07 S11)."""

    queryset = Tarjeta.objects.all()
    serializer_class = TarjetaSerializer
    search_fields = ["uid_chip", "notas", "perfil__slug", "perfil__nombre_publico"]
    ordering_fields = ["fecha_creacion", "estado", "tipo", "uid_chip"]
    ordering = ["-fecha_creacion"]

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        _validar_request_sin_nul(request)
        if request.method in ("POST", "PUT", "PATCH"):
            _validar_payload_sin_nul(request.data)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Tarjeta.objects.none()
        qs = super().get_queryset()
        empresas = get_empresas_visible(self.request.user)
        qs = qs.filter(id_empresa__in=empresas).select_related("id_empresa", "perfil")

        empresa_param = self.request.query_params.get("empresa") or self.request.query_params.get("empresa_id")
        if empresa_param:
            empresa_uuid = validar_uuid_param(empresa_param, "empresa_id")
            qs = qs.filter(id_empresa_id=empresa_uuid)

        perfil_param = self.request.query_params.get("perfil") or self.request.query_params.get("perfil_id")
        if perfil_param:
            perfil_uuid = validar_uuid_param(perfil_param, "perfil_id")
            qs = qs.filter(perfil_id=perfil_uuid)

        estado_param = self.request.query_params.get("estado")
        if estado_param:
            qs = qs.filter(estado=estado_param.strip().upper())

        tipo_param = self.request.query_params.get("tipo")
        if tipo_param:
            qs = qs.filter(tipo=tipo_param.strip().upper())

        return qs

    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        if lookup_url_kwarg in self.kwargs:
            validar_uuid_param(self.kwargs[lookup_url_kwarg], self.lookup_field)
        return super().get_object()

    def _guardar_tarjeta_validada(self, instancia: Tarjeta) -> None:
        if instancia.estado == Tarjeta.Estado.ACTIVA:
            if instancia.perfil is None or not instancia.perfil.activo:
                raise ValidationError(
                    {"perfil": "Una tarjeta activa debe tener un perfil activo asignado en la misma empresa."}
                )
        try:
            with transaction.atomic():
                instancia.full_clean()
                instancia.save()
        except DjangoValidationError as exc:
            raise _manejar_django_validation(exc) from exc
        except IntegrityError as exc:
            raise ValidationError({"uid_chip": "Ya existe una tarjeta registrada con ese UID de chip."}) from exc

    def perform_create(self, serializer) -> None:
        data = serializer.validated_data
        empresa = data.get("id_empresa") or get_empresa_primaria(self.request.user)
        if empresa is None:
            raise PermissionDenied("El usuario no tiene empresa asignada.")
        perfil = data.get("perfil")
        if perfil is not None and (perfil.id_empresa_id != empresa.pk or not perfil.activo):
            raise ValidationError({"perfil": "El perfil debe estar activo y pertenecer a la misma empresa."})

        instancia = Tarjeta(
            id_empresa=empresa,
            perfil=perfil,
            uid_chip=data["uid_chip"],
            tipo=data.get("tipo", Tarjeta.Tipo.PVC),
            estado=data.get("estado", Tarjeta.Estado.INVENTARIO),
            notas=data.get("notas", ""),
            activo=bool(data.get("activo", True)),
        )
        self._guardar_tarjeta_validada(instancia)
        serializer.instance = instancia

    def perform_update(self, serializer) -> None:
        instancia: Tarjeta = serializer.instance
        data = serializer.validated_data
        if "id_empresa" in data and data["id_empresa"].pk != instancia.id_empresa_id:
            raise ValidationError({"id_empresa": "La empresa de una tarjeta Connect es inmutable."})
        if "perfil" in data and data["perfil"] is not None:
            nuevo_perfil = data["perfil"]
            if nuevo_perfil.id_empresa_id != instancia.id_empresa_id or not nuevo_perfil.activo:
                raise ValidationError({"perfil": "El perfil debe estar activo y pertenecer a la misma empresa."})
        for campo, valor in data.items():
            setattr(instancia, campo, valor)
        self._guardar_tarjeta_validada(instancia)

    def perform_destroy(self, instance: Tarjeta) -> None:
        if instance.estado != Tarjeta.Estado.PERDIDA:
            instance.estado = Tarjeta.Estado.DESACTIVADA
        instance.activo = False
        instance.save(update_fields=["estado", "activo", "fecha_actualizacion"])

    @swagger_auto_schema(
        method="post",
        operation_summary="Asigna una tarjeta física a un perfil activo (opcionalmente activándola)",
        request_body=TarjetaAsignarInputSerializer,
        responses={200: TarjetaSerializer, 400: "Datos o estado inválido", 404: "Tarjeta no encontrada"},
    )
    @action(detail=True, methods=["post"], url_path="asignar")
    def asignar(self, request: Request, pk: str | None = None) -> Response:
        tarjeta = self.get_object()
        serializer = TarjetaAsignarInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        datos = serializer.validated_data
        try:
            actualizada = asignar_tarjeta(
                tarjeta,
                perfil_id=datos["perfil_id"],
                activar=bool(datos.get("activar", False)),
            )
        except ConnectError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        except DjangoValidationError as exc:
            raise _manejar_django_validation(exc) from exc
        return Response(TarjetaSerializer(actualizada).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method="post",
        operation_summary="Activa una tarjeta física con perfil activo asignado",
        responses={200: TarjetaSerializer, 400: "Estado o perfil inválido", 404: "Tarjeta no encontrada"},
    )
    @action(detail=True, methods=["post"], url_path="activar")
    def activar(self, request: Request, pk: str | None = None) -> Response:
        tarjeta = self.get_object()
        try:
            actualizada = activar_tarjeta(tarjeta)
        except ConnectError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        except DjangoValidationError as exc:
            raise _manejar_django_validation(exc) from exc
        return Response(TarjetaSerializer(actualizada).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method="post",
        operation_summary="Desactiva una tarjeta física bloqueando su acceso público",
        responses={200: TarjetaSerializer, 400: "Estado inválido", 404: "Tarjeta no encontrada"},
    )
    @action(detail=True, methods=["post"], url_path="desactivar")
    def desactivar(self, request: Request, pk: str | None = None) -> Response:
        tarjeta = self.get_object()
        try:
            actualizada = desactivar_tarjeta(tarjeta)
        except ConnectError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        except DjangoValidationError as exc:
            raise _manejar_django_validation(exc) from exc
        return Response(TarjetaSerializer(actualizada).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method="post",
        operation_summary="Marca una tarjeta como PERDIDA revocando inmediatamente su acceso público",
        responses={200: TarjetaSerializer, 404: "Tarjeta no encontrada"},
    )
    @action(detail=True, methods=["post"], url_path="marcar-perdida")
    def marcar_perdida(self, request: Request, pk: str | None = None) -> Response:
        tarjeta = self.get_object()
        try:
            actualizada = marcar_tarjeta_perdida(tarjeta)
        except ConnectError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        except DjangoValidationError as exc:
            raise _manejar_django_validation(exc) from exc
        return Response(TarjetaSerializer(actualizada).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method="get",
        operation_summary="Genera y descarga el código QR (SVG o PNG) asociado a la tarjeta",
        manual_parameters=[_FORMATO_QR_PARAM],
        produces=["image/svg+xml", "image/png"],
        responses={
            200: openapi.Response(
                description="Código QR en formato SVG o PNG",
                schema=openapi.Schema(type=openapi.TYPE_STRING),
            ),
            400: "Tarjeta sin perfil asignado o formato inválido",
            404: "Tarjeta no encontrada",
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="qr",
        renderer_classes=[JSONRenderer, SvgRenderer, PngRenderer],
    )
    def qr(self, request: Request, pk: str | None = None) -> HttpResponse | Response:
        tarjeta = self.get_object()
        if tarjeta.perfil is None:
            return domain_error_response(
                ConnectError("La tarjeta debe tener un perfil asignado para generar su código QR."),
                status_code=status.HTTP_400_BAD_REQUEST,
                key="detail",
            )
        try:
            url = construir_url_publica_perfil(tarjeta.perfil.slug, uid=tarjeta.uid_chip)
            return _respuesta_qr(
                url,
                nombre_base=f"qr-{tarjeta.perfil.slug}-{tarjeta.uid_chip}",
                formato_raw=request.query_params.get("formato"),
            )
        except ConnectError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
