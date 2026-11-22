"""
Endpoints HTTP para 2FA / TOTP (RFC 6238, Plan 05 P3-1).

Montados bajo ``/api/auth/mfa/``:
  - ``GET  /api/auth/mfa/estado/``
  - ``POST /api/auth/mfa/iniciar/``
  - ``POST /api/auth/mfa/confirmar/``
  - ``POST /api/auth/mfa/desactivar/``
  - ``POST /api/auth/mfa/regenerar-codigos/``
  - ``POST /api/auth/mfa/verificar/``
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .auth_views import LOCKOUT_MESSAGE, _esta_bloqueado_por_axes, _uref, emitir_sesion_login_response
from .exceptions import DomainError, domain_error_response
from .mfa import (
    construir_otpauth_uri,
    consumir_codigo_respaldo,
    generar_codigos_respaldo,
    generar_qr_svg_mfa,
    generar_secreto_totp,
    usuario_requiere_configurar_mfa,
    validar_mfa_token,
    verificar_totp,
)
from .models import ConfiguracionMFA, Usuarios

logger = logging.getLogger(__name__)


class MfaCodigoInputSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=32, required=True, allow_blank=False)


class MfaDesactivarInputSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=256, required=True, allow_blank=False)
    codigo = serializers.CharField(max_length=32, required=True, allow_blank=False)


class MfaVerificarInputSerializer(serializers.Serializer):
    mfa_token = serializers.CharField(max_length=512, required=True, allow_blank=False)
    codigo = serializers.CharField(max_length=32, required=True, allow_blank=False)


def _limpiar_campo(valor: object) -> str:
    texto = str(valor or "")
    if "\x00" in texto:
        raise DomainError("El parámetro contiene caracteres no permitidos.")
    return texto.strip()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def mfa_estado_view(request):
    """Retorna el estado de 2FA/TOTP del usuario autenticado (sin exponer secretos)."""
    config = ConfiguracionMFA.objects.filter(usuario=request.user).first()
    habilitado = bool(config and config.habilitado)
    return Response(
        {
            "habilitado": habilitado,
            "confirmado_en": config.confirmado_en.isoformat() if (config and config.confirmado_en) else None,
            "codigos_respaldo_restantes": len(config.codigos_respaldo) if (config and habilitado) else 0,
            "requerido_por_politica": usuario_requiere_configurar_mfa(request.user),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mfa_iniciar_view(request):
    """Genera secreto pendiente y QR SVG para configurar TOTP."""
    with transaction.atomic():
        config, _creado = ConfiguracionMFA.objects.select_for_update().get_or_create(usuario=request.user)
        if config.habilitado:
            return domain_error_response(DomainError("El 2FA ya se encuentra habilitado para esta cuenta."))

        secret = generar_secreto_totp()
        config.secret = secret
        config.habilitado = False
        config.confirmado_en = None
        config.ultimo_paso_totp = None
        config.codigos_respaldo = []
        config.save(
            update_fields=[
                "secret",
                "habilitado",
                "confirmado_en",
                "ultimo_paso_totp",
                "codigos_respaldo",
                "fecha_actualizacion",
            ]
        )

    otpauth_uri = construir_otpauth_uri(secret, request.user.username)
    qr_svg = generar_qr_svg_mfa(otpauth_uri)
    logger.info("MFA setup initiated for %s", _uref(request.user.username))
    return Response(
        {
            "otpauth_uri": otpauth_uri,
            "qr_svg": qr_svg,
            "secret_manual": secret,
        },
        status=status.HTTP_200_OK,
    )


@swagger_auto_schema(method="post", request_body=MfaCodigoInputSerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mfa_confirmar_view(request):
    """Valida el primer código TOTP y activa 2FA devolviendo códigos de respaldo una sola vez."""
    serializer = MfaCodigoInputSerializer(data=request.data)
    if not serializer.is_valid():
        return domain_error_response(DomainError("Debe proporcionar un código de verificación válido."))

    try:
        codigo = _limpiar_campo(serializer.validated_data["codigo"])
    except DomainError as exc:
        return domain_error_response(exc)

    with transaction.atomic():
        config = ConfiguracionMFA.objects.select_for_update().filter(usuario=request.user).first()
        if config is None or not config.secret:
            return domain_error_response(DomainError("Debe iniciar la configuración 2FA antes de confirmarla."))
        if config.habilitado:
            return domain_error_response(DomainError("El 2FA ya se encuentra habilitado para esta cuenta."))

        valido, paso = verificar_totp(config.secret, codigo, ultimo_paso=config.ultimo_paso_totp)
        if not valido or paso is None:
            return domain_error_response(DomainError("El código de verificación TOTP es inválido o expiró."))

        codigos_planos, codigos_hash = generar_codigos_respaldo()
        ahora = timezone.now()
        config.habilitado = True
        config.confirmado_en = ahora
        config.ultimo_paso_totp = paso
        config.codigos_respaldo = codigos_hash
        config.save(
            update_fields=[
                "habilitado",
                "confirmado_en",
                "ultimo_paso_totp",
                "codigos_respaldo",
                "fecha_actualizacion",
            ]
        )

    logger.info("MFA enabled for %s", _uref(request.user.username))
    return Response(
        {
            "habilitado": True,
            "confirmado_en": ahora.isoformat(),
            "codigos_respaldo": codigos_planos,
        },
        status=status.HTTP_200_OK,
    )


@swagger_auto_schema(method="post", request_body=MfaDesactivarInputSerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mfa_desactivar_view(request):
    """Desactiva 2FA exigiendo contraseña actual + código TOTP o de respaldo válido."""
    serializer = MfaDesactivarInputSerializer(data=request.data)
    if not serializer.is_valid():
        return domain_error_response(DomainError("Debe indicar contraseña actual y código de verificación."))

    try:
        password = _limpiar_campo(serializer.validated_data["password"])
        codigo = _limpiar_campo(serializer.validated_data["codigo"])
    except DomainError as exc:
        return domain_error_response(exc)

    if not request.user.check_password(password):
        return domain_error_response(DomainError("La contraseña actual es incorrecta."), status_code=401)

    with transaction.atomic():
        config = ConfiguracionMFA.objects.select_for_update().filter(usuario=request.user).first()
        if config is None or not config.habilitado:
            return domain_error_response(DomainError("El 2FA no está activo en esta cuenta."))

        valido_totp, _paso = verificar_totp(config.secret, codigo, ultimo_paso=config.ultimo_paso_totp)
        valido_respaldo = False if valido_totp else consumir_codigo_respaldo(config, codigo)
        if not (valido_totp or valido_respaldo):
            return domain_error_response(DomainError("El código TOTP o de respaldo es inválido."))

        config.habilitado = False
        config.secret = ""
        config.confirmado_en = None
        config.ultimo_paso_totp = None
        config.codigos_respaldo = []
        config.save(
            update_fields=[
                "habilitado",
                "secret",
                "confirmado_en",
                "ultimo_paso_totp",
                "codigos_respaldo",
                "fecha_actualizacion",
            ]
        )

    logger.info("MFA disabled for %s", _uref(request.user.username))
    return Response({"habilitado": False}, status=status.HTTP_200_OK)


@swagger_auto_schema(method="post", request_body=MfaCodigoInputSerializer)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mfa_regenerar_codigos_view(request):
    """Rota los 8 códigos de respaldo tras verificar un TOTP vigente."""
    serializer = MfaCodigoInputSerializer(data=request.data)
    if not serializer.is_valid():
        return domain_error_response(DomainError("Debe proporcionar un código TOTP válido."))

    try:
        codigo = _limpiar_campo(serializer.validated_data["codigo"])
    except DomainError as exc:
        return domain_error_response(exc)

    with transaction.atomic():
        config = ConfiguracionMFA.objects.select_for_update().filter(usuario=request.user).first()
        if config is None or not config.habilitado:
            return domain_error_response(DomainError("El 2FA no está activo en esta cuenta."))

        valido, paso = verificar_totp(config.secret, codigo, ultimo_paso=config.ultimo_paso_totp)
        if not valido or paso is None:
            return domain_error_response(DomainError("El código TOTP es inválido o ya fue utilizado."))

        codigos_planos, codigos_hash = generar_codigos_respaldo()
        config.ultimo_paso_totp = paso
        config.codigos_respaldo = codigos_hash
        config.save(update_fields=["ultimo_paso_totp", "codigos_respaldo", "fecha_actualizacion"])

    logger.info("MFA backup codes rotated for %s", _uref(request.user.username))
    return Response({"codigos_respaldo": codigos_planos}, status=status.HTTP_200_OK)


def _ratelimit_ip_key(group: str, request) -> str:
    return str(request.META.get("REMOTE_ADDR") or "127.0.0.1")


@swagger_auto_schema(method="post", request_body=MfaVerificarInputSerializer)
@ratelimit(key=_ratelimit_ip_key, rate="10/m", method="POST", block=False, group="omni_erp.mfa_verificar")
@api_view(["POST"])
@permission_classes([AllowAny])
def mfa_verificar_view(request):
    """Completa el login validando ``mfa_token`` efímero + código TOTP o de respaldo."""
    if getattr(request, "limited", False):
        return Response(
            {"error": "Demasiados intentos de verificación 2FA. Espere un momento."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    serializer = MfaVerificarInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"error": "Se requieren mfa_token y código de verificación."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        mfa_token = _limpiar_campo(serializer.validated_data["mfa_token"])
        codigo = _limpiar_campo(serializer.validated_data["codigo"])
    except DomainError as exc:
        return domain_error_response(exc)

    user_id = validar_mfa_token(mfa_token)
    if not user_id:
        return Response(
            {"error": "El token de verificación 2FA es inválido o ha expirado."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    user = Usuarios.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        return Response(
            {"error": "Sesión de verificación 2FA inválida."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if _esta_bloqueado_por_axes(request, user.username):
        logger.warning("MFA verify blocked by axes for %s", _uref(user.username))
        return Response({"error": LOCKOUT_MESSAGE}, status=status.HTTP_429_TOO_MANY_REQUESTS)

    with transaction.atomic():
        config = ConfiguracionMFA.objects.select_for_update().filter(usuario=user, habilitado=True).first()
        if config is None or not config.secret:
            return Response(
                {"error": "La cuenta no tiene 2FA activo."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        valido_totp, paso = verificar_totp(config.secret, codigo, ultimo_paso=config.ultimo_paso_totp)
        if valido_totp and paso is not None:
            config.ultimo_paso_totp = paso
            config.save(update_fields=["ultimo_paso_totp", "fecha_actualizacion"])
        elif not consumir_codigo_respaldo(config, codigo):
            logger.warning("Failed MFA verification attempt for %s", _uref(user.username))
            return Response(
                {"error": "Código de verificación 2FA inválido."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

    logger.info("Successful MFA login for %s", _uref(user.username))
    return emitir_sesion_login_response(request, user)
