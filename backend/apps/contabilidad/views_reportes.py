"""Endpoints REST de reportes financieros canónicos (PR-14).

Expone bajo ``/api/contabilidad/reportes/``:
  - ``balance-comprobacion/``
  - ``estado-resultados/``
  - ``balance-general/``
  - ``libro-mayor-auxiliar/``

Todos soportan ``formato=json|csv|pdf``, equivalentes dobles USD opcionales
(``incluir_equivalentes_usd``) y validación estricta multi-tenant (R-CODE-1).
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.http import HttpResponse
from django.utils import timezone
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.exceptions import NotAcceptable, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import domain_error_response
from apps.core.viewsets import get_empresas_visible

from .exportadores_reportes import exportar_reporte_csv, exportar_reporte_pdf
from .serializers_reportes import (
    BalanceComprobacionResponseSerializer,
    BalanceGeneralResponseSerializer,
    EstadoResultadosResponseSerializer,
    LibroMayorAuxiliarResponseSerializer,
)
from .services_reportes import (
    ReporteContableError,
    ReporteTenantError,
    generar_balance_comprobacion,
    generar_balance_general,
    generar_estado_resultados,
    generar_libro_mayor_auxiliar,
)

if TYPE_CHECKING:
    from apps.core.models import Empresa

logger = logging.getLogger(__name__)

_FECHA_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def serializar_reporte_json(valor: Any) -> Any:
    """Convierte ``Decimal`` a ``str`` recursivamente (R-CODE-4, cero floats)."""
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, dict):
        return {k: serializar_reporte_json(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [serializar_reporte_json(item) for item in valor]
    return valor


def _validar_sin_nul(request: Request) -> None:
    for key, values in request.query_params.lists():
        if "\x00" in str(key):
            raise ValidationError({"error": "Parámetro de consulta inválido."})
        for val in values:
            if "\x00" in str(val):
                raise ValidationError({key: "Parámetro de consulta inválido."})


def _resolver_empresa_reporte(request: Request) -> tuple[Empresa | None, Response | None]:
    empresa_id = request.query_params.get("empresa_id")
    if not empresa_id or not str(empresa_id).strip():
        return None, Response(
            {"error": "Debe especificar el ID de la empresa (empresa_id)."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        empresa_uuid = uuid.UUID(str(empresa_id).strip())
    except (ValueError, TypeError):
        return None, Response({"error": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)

    empresa = get_empresas_visible(request.user).filter(pk=empresa_uuid).first()
    if empresa is None:
        return None, Response({"error": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)
    return empresa, None


def _parse_fecha_param(raw: str | None, campo: str) -> date | None:
    if raw is None or not raw.strip():
        return None
    limpio = raw.strip()
    if not _FECHA_ISO_RE.match(limpio):
        raise ValidationError({campo: f"Formato de fecha inválido para '{campo}'. Use YYYY-MM-DD."})
    try:
        return date.fromisoformat(limpio)
    except ValueError as exc:
        raise ValidationError({campo: f"Fecha inválida para '{campo}'."}) from exc


def _parse_bool_param(raw: str | None, campo: str, *, default: bool = False) -> bool:
    if raw is None or not raw.strip():
        return default
    limpio = raw.strip().lower()
    if limpio in ("true", "1"):
        return True
    if limpio in ("false", "0"):
        return False
    raise ValidationError({campo: f"Valor booleano inválido para '{campo}'. Use true/false o 1/0."})


def _parse_formato_param(raw: str | None) -> str:
    if raw is None or not raw.strip():
        return "json"
    limpio = raw.strip().lower()
    if limpio not in ("json", "csv", "pdf"):
        raise ValidationError({"formato": "Formato inválido. Valores permitidos: json, csv, pdf."})
    return limpio


def _parse_uuid_param(raw: str | None, campo: str) -> uuid.UUID | None:
    if raw is None or not raw.strip():
        return None
    try:
        return uuid.UUID(raw.strip())
    except (ValueError, TypeError) as exc:
        raise ValidationError({campo: f"El parámetro '{campo}' no es un UUID válido."}) from exc


def _parse_limit_param(raw: str | None, *, default: int = 1000) -> int:
    if raw is None or not raw.strip():
        return default
    try:
        valor = int(raw.strip())
    except (ValueError, TypeError) as exc:
        raise ValidationError({"limit": "El parámetro 'limit' debe ser un número entero."}) from exc
    if valor < 1 or valor > 5000:
        raise ValidationError({"limit": "El parámetro 'limit' debe estar entre 1 y 5000."})
    return valor


def _responder_reporte(
    tipo_reporte: str,
    empresa: Empresa,
    data: dict[str, Any],
    formato: str,
) -> HttpResponse:
    if formato == "csv":
        csv_bytes = exportar_reporte_csv(tipo_reporte, data)
        resp = HttpResponse(csv_bytes, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{tipo_reporte}_{empresa.pk}.csv"'
        return resp

    if formato == "pdf":
        try:
            pdf_bytes = exportar_reporte_pdf(
                tipo_reporte,
                data,
                empresa_nombre=empresa.nombre_legal or str(empresa),
            )
        except ImportError:
            # SEC-M4 (R-CODE-8): no exponer detalle interno de paquetes faltantes.
            logger.exception("Generación de PDF de reporte contable no disponible")
            return Response(
                {"error": "Generación de PDF no disponible en este servidor."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        resp = HttpResponse(pdf_bytes, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{tipo_reporte}_{empresa.pk}.pdf"'
        return resp

    return Response(serializar_reporte_json(data), status=status.HTTP_200_OK)


_PARAM_EMPRESA = openapi.Parameter(
    "empresa_id",
    openapi.IN_QUERY,
    description="UUID de la empresa (requerido).",
    type=openapi.TYPE_STRING,
    format=openapi.FORMAT_UUID,
    required=True,
)
_PARAM_FORMATO = openapi.Parameter(
    "formato",
    openapi.IN_QUERY,
    description="Formato de salida: json (default), csv o pdf.",
    type=openapi.TYPE_STRING,
    enum=["json", "csv", "pdf"],
    default="json",
)
_PARAM_USD = openapi.Parameter(
    "incluir_equivalentes_usd",
    openapi.IN_QUERY,
    description="Si true, incluye equivalentes convertidos a USD cuando existe tasa disponible.",
    type=openapi.TYPE_BOOLEAN,
    default=False,
)


class ReporteContableBaseView(APIView):
    """Base común para reportes contables con soporte JSON/CSV/PDF sin 406."""

    permission_classes = [IsAuthenticated]

    def perform_content_negotiation(self, request: Request, force: bool = False) -> tuple[Any, str]:
        try:
            return super().perform_content_negotiation(request, force=force)
        except NotAcceptable:
            if (request.query_params.get("formato") or "").strip().lower() in ("csv", "pdf"):
                renderer = self.renderer_classes[0]()
                return (renderer, renderer.media_type)
            raise


class ReporteBalanceComprobacionView(ReporteContableBaseView):
    """GET /api/contabilidad/reportes/balance-comprobacion/"""

    @swagger_auto_schema(
        operation_summary="Balance de Comprobación canónico",
        manual_parameters=[
            _PARAM_EMPRESA,
            openapi.Parameter("fecha_desde", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
            openapi.Parameter("fecha_hasta", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
            openapi.Parameter("id_diario", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
            _PARAM_USD,
            _PARAM_FORMATO,
        ],
        responses={200: BalanceComprobacionResponseSerializer},
    )
    def get(self, request: Request) -> HttpResponse:
        _validar_sin_nul(request)
        empresa, err = _resolver_empresa_reporte(request)
        if err is not None or empresa is None:
            return err or Response({"error": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        fecha_desde = _parse_fecha_param(request.query_params.get("fecha_desde"), "fecha_desde")
        fecha_hasta = _parse_fecha_param(request.query_params.get("fecha_hasta"), "fecha_hasta")
        id_diario = _parse_uuid_param(request.query_params.get("id_diario"), "id_diario")
        incluir_usd = _parse_bool_param(
            request.query_params.get("incluir_equivalentes_usd"), "incluir_equivalentes_usd"
        )
        formato = _parse_formato_param(request.query_params.get("formato"))

        try:
            data = generar_balance_comprobacion(
                empresa,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                id_diario=id_diario,
                incluir_equivalentes_usd=incluir_usd,
            )
        except ReporteTenantError as exc:
            return domain_error_response(exc, status_code=status.HTTP_404_NOT_FOUND)
        except ReporteContableError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)

        return _responder_reporte("balance-comprobacion", empresa, data, formato)


class ReporteEstadoResultadosView(ReporteContableBaseView):
    """GET /api/contabilidad/reportes/estado-resultados/"""

    @swagger_auto_schema(
        operation_summary="Estado de Resultados (P&L) canónico",
        manual_parameters=[
            _PARAM_EMPRESA,
            openapi.Parameter("fecha_desde", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
            openapi.Parameter("fecha_hasta", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
            _PARAM_USD,
            _PARAM_FORMATO,
        ],
        responses={200: EstadoResultadosResponseSerializer},
    )
    def get(self, request: Request) -> HttpResponse:
        _validar_sin_nul(request)
        empresa, err = _resolver_empresa_reporte(request)
        if err is not None or empresa is None:
            return err or Response({"error": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        hoy = timezone.localdate()
        fecha_hasta = _parse_fecha_param(request.query_params.get("fecha_hasta"), "fecha_hasta") or hoy
        fecha_desde = _parse_fecha_param(
            request.query_params.get("fecha_desde"), "fecha_desde"
        ) or fecha_hasta.replace(month=1, day=1)
        incluir_usd = _parse_bool_param(
            request.query_params.get("incluir_equivalentes_usd"), "incluir_equivalentes_usd"
        )
        formato = _parse_formato_param(request.query_params.get("formato"))

        try:
            data = generar_estado_resultados(
                empresa,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                incluir_equivalentes_usd=incluir_usd,
            )
        except ReporteTenantError as exc:
            return domain_error_response(exc, status_code=status.HTTP_404_NOT_FOUND)
        except ReporteContableError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)

        return _responder_reporte("estado-resultados", empresa, data, formato)


class ReporteBalanceGeneralView(ReporteContableBaseView):
    """GET /api/contabilidad/reportes/balance-general/"""

    @swagger_auto_schema(
        operation_summary="Balance General canónico",
        manual_parameters=[
            _PARAM_EMPRESA,
            openapi.Parameter("fecha_corte", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
            _PARAM_USD,
            _PARAM_FORMATO,
        ],
        responses={200: BalanceGeneralResponseSerializer},
    )
    def get(self, request: Request) -> HttpResponse:
        _validar_sin_nul(request)
        empresa, err = _resolver_empresa_reporte(request)
        if err is not None or empresa is None:
            return err or Response({"error": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        fecha_corte = (
            _parse_fecha_param(request.query_params.get("fecha_corte"), "fecha_corte") or timezone.localdate()
        )
        incluir_usd = _parse_bool_param(
            request.query_params.get("incluir_equivalentes_usd"), "incluir_equivalentes_usd"
        )
        formato = _parse_formato_param(request.query_params.get("formato"))

        try:
            data = generar_balance_general(
                empresa,
                fecha_corte=fecha_corte,
                incluir_equivalentes_usd=incluir_usd,
            )
        except ReporteTenantError as exc:
            return domain_error_response(exc, status_code=status.HTTP_404_NOT_FOUND)
        except ReporteContableError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)

        return _responder_reporte("balance-general", empresa, data, formato)


class ReporteLibroMayorAuxiliarView(ReporteContableBaseView):
    """GET /api/contabilidad/reportes/libro-mayor-auxiliar/"""

    @swagger_auto_schema(
        operation_summary="Libro Mayor Auxiliar canónico",
        manual_parameters=[
            _PARAM_EMPRESA,
            openapi.Parameter(
                "id_cuenta_contable", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID
            ),
            openapi.Parameter("id_contacto", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
            openapi.Parameter("id_diario", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_UUID),
            openapi.Parameter("fecha_desde", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
            openapi.Parameter("fecha_hasta", openapi.IN_QUERY, type=openapi.TYPE_STRING, format=openapi.FORMAT_DATE),
            openapi.Parameter("limit", openapi.IN_QUERY, type=openapi.TYPE_INTEGER, default=1000),
            _PARAM_USD,
            _PARAM_FORMATO,
        ],
        responses={200: LibroMayorAuxiliarResponseSerializer},
    )
    def get(self, request: Request) -> HttpResponse:
        _validar_sin_nul(request)
        empresa, err = _resolver_empresa_reporte(request)
        if err is not None or empresa is None:
            return err or Response({"error": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        id_cuenta = _parse_uuid_param(request.query_params.get("id_cuenta_contable"), "id_cuenta_contable")
        id_contacto = _parse_uuid_param(request.query_params.get("id_contacto"), "id_contacto")
        id_diario = _parse_uuid_param(request.query_params.get("id_diario"), "id_diario")
        fecha_desde = _parse_fecha_param(request.query_params.get("fecha_desde"), "fecha_desde")
        fecha_hasta = _parse_fecha_param(request.query_params.get("fecha_hasta"), "fecha_hasta")
        limit = _parse_limit_param(request.query_params.get("limit"), default=1000)
        incluir_usd = _parse_bool_param(
            request.query_params.get("incluir_equivalentes_usd"), "incluir_equivalentes_usd"
        )
        formato = _parse_formato_param(request.query_params.get("formato"))

        try:
            data = generar_libro_mayor_auxiliar(
                empresa,
                id_cuenta_contable=id_cuenta,
                id_contacto=id_contacto,
                id_diario=id_diario,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                limit=limit,
                incluir_equivalentes_usd=incluir_usd,
            )
        except ReporteTenantError as exc:
            return domain_error_response(exc, status_code=status.HTTP_404_NOT_FOUND)
        except ReporteContableError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)

        return _responder_reporte("libro-mayor-auxiliar", empresa, data, formato)
