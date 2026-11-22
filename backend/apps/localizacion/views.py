"""Endpoints REST del framework de localización (PR-25 / ADR-007)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.viewsets import get_empresas_visible, validar_uuid_param

from .serializers import EstadoLocalizacionResponseSerializer
from .services import resumen_localizacion

if TYPE_CHECKING:
    from apps.core.models import Empresa

_EMPRESA_ID_QUERY_PARAM = openapi.Parameter(
    "empresa_id",
    openapi.IN_QUERY,
    description="UUID de la empresa visible (obligatorio para superusuarios Omni sin empresa propia).",
    type=openapi.TYPE_STRING,
    format=openapi.FORMAT_UUID,
    required=False,
)


def _validar_query_sin_nul(request: Request) -> None:
    """Rechaza bytes NUL en cualquier query param con HTTP 400."""
    for key, values in request.query_params.lists():
        if "\x00" in str(key):
            raise ValidationError({"error": "Parámetro de consulta inválido."})
        for val in values:
            if "\x00" in str(val):
                raise ValidationError({key: "Parámetro de consulta inválido."})


def _resolver_empresa_estado(request: Request) -> tuple[Empresa | None, Response | None]:
    """Resuelve la empresa objetivo respetando visibilidad multi-tenant y superusuario Omni."""
    user = request.user
    empresas = get_empresas_visible(user)
    if not empresas.exists():
        return None, Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

    if "empresa_id" in request.query_params:
        empresa_raw = request.query_params.get("empresa_id", "")
        empresa_uuid = uuid.UUID(validar_uuid_param(empresa_raw, "empresa_id"))
        empresa = empresas.filter(pk=empresa_uuid).first()
        if empresa is None:
            return None, Response(
                {"detail": "No tienes permiso para consultar la localización de esa empresa."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return empresa, None

    id_empresa_propia = getattr(user, "id_empresa_id", None) or getattr(user, "id_empresa", None)
    if id_empresa_propia is not None:
        id_empresa_propia_pk = getattr(id_empresa_propia, "pk", id_empresa_propia)
        empresa_propia = empresas.filter(pk=id_empresa_propia_pk).first()
        if empresa_propia is not None:
            return empresa_propia, None

    if getattr(user, "es_superusuario_omni", False):
        return None, Response(
            {"detail": "Debe especificar empresa_id para operar como superusuario Omni."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if hasattr(user, "empresas"):
        propia_m2m = user.empresas.filter(pk__in=empresas.values("pk")).order_by("id_empresa").first()
        if propia_m2m is not None:
            return propia_m2m, None

    return empresas.order_by("id_empresa").first(), None


class EstadoLocalizacionView(APIView):
    """GET /api/localizacion/estado/ — Estado de localización y puertos de una empresa."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Estado de localización de dos capas de la empresa",
        manual_parameters=[_EMPRESA_ID_QUERY_PARAM],
        responses={200: EstadoLocalizacionResponseSerializer},
    )
    def get(self, request: Request) -> Response:
        _validar_query_sin_nul(request)
        empresa, err = _resolver_empresa_estado(request)
        if err is not None or empresa is None:
            return err or Response({"detail": "Sin empresa asignada."}, status=status.HTTP_403_FORBIDDEN)

        payload = {
            "empresa_id": str(empresa.pk),
            **resumen_localizacion(empresa),
        }
        return Response(EstadoLocalizacionResponseSerializer(payload).data, status=status.HTTP_200_OK)
