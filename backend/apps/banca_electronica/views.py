import os
import re
import uuid

from django.http import HttpResponse
from django.utils.decorators import method_decorator
from drf_yasg import openapi
from drf_yasg.utils import no_body, swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import domain_error_response
from apps.core.viewsets import (
    BaseModelViewSet,
    NulSafeFilterMixin,
    get_empresas_visible,
    validar_uuid_param,
)

from .models import LotePagoBancario
from .serializers import (
    GenerarLoteNominaInputSerializer,
    GenerarLoteProveedoresInputSerializer,
    LotePagoBancarioSerializer,
    ValidarCuentaVeInputSerializer,
    ValidarCuentaVeResponseSerializer,
    ValidarReferenciaInputSerializer,
    ValidarReferenciaResponseSerializer,
)
from .services import (
    BancaElectronicaError,
    cambiar_estado_lote,
    generar_lote_pagos_nomina,
    generar_lote_pagos_proveedores,
    validar_cuenta_bancaria_ve,
    validar_referencia_bancaria,
)


@method_decorator(
    name="list",
    decorator=swagger_auto_schema(
        manual_parameters=[
            openapi.Parameter(
                "empresa",
                openapi.IN_QUERY,
                description="Filtrar lotes por UUID de empresa.",
                type=openapi.TYPE_STRING,
                format=openapi.FORMAT_UUID,
            ),
            openapi.Parameter(
                "tipo_lote",
                openapi.IN_QUERY,
                description="Filtrar por tipo de lote (PROVEEDORES | NOMINA).",
                type=openapi.TYPE_STRING,
                enum=[c[0] for c in LotePagoBancario.TIPOS_LOTE],
            ),
            openapi.Parameter(
                "estado",
                openapi.IN_QUERY,
                description="Filtrar por estado del lote.",
                type=openapi.TYPE_STRING,
                enum=[c[0] for c in LotePagoBancario.ESTADOS],
            ),
        ]
    ),
)
@method_decorator(name="create", decorator=swagger_auto_schema(auto_schema=None))
class LotePagoBancarioViewSet(NulSafeFilterMixin, BaseModelViewSet):
    """Gestión de lotes de pagos masivos VE (proveedores y nómina)."""

    queryset = LotePagoBancario.objects.all()
    serializer_class = LotePagoBancarioSerializer
    http_method_names = ["get", "post", "head", "options"]
    search_fields = ["referencia_lote", "nombre_archivo", "tipo_lote", "formato_banco", "estado"]
    ordering_fields = ["fecha_valor", "monto_total", "total_registros", "fecha_creacion", "estado"]

    def get_queryset(self):
        qs = (
            LotePagoBancario.objects.select_related(
                "id_empresa",
                "id_cuenta_bancaria",
                "id_proceso_nomina",
                "generado_por",
            )
            .prefetch_related("detalles")
            .filter(id_empresa__in=get_empresas_visible(self.request.user))
        )
        empresa_param = self.request.query_params.get("empresa")
        if empresa_param:
            qs = qs.filter(id_empresa_id=uuid.UUID(validar_uuid_param(empresa_param, "empresa")))
        tipo_lote = self.request.query_params.get("tipo_lote")
        if tipo_lote:
            qs = qs.filter(tipo_lote=tipo_lote.replace("\x00", "").strip())
        estado = self.request.query_params.get("estado")
        if estado:
            qs = qs.filter(estado=estado.replace("\x00", "").strip())
        return qs

    def create(self, request, *args, **kwargs):
        return Response(
            {"detail": "Use /generar-proveedores/ o /generar-nomina/ para crear lotes de pago."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @swagger_auto_schema(
        request_body=GenerarLoteProveedoresInputSerializer,
        responses={201: LotePagoBancarioSerializer},
    )
    @action(detail=False, methods=["post"], url_path="generar-proveedores")
    def generar_proveedores(self, request):
        serializer = GenerarLoteProveedoresInputSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            lote = generar_lote_pagos_proveedores(
                empresa=data["empresa"],
                cuenta_bancaria=data["cuenta_bancaria"],
                pagos_ids=data["pagos_ids"],
                formato_banco=data["formato_banco"],
                fecha_valor=data["fecha_valor"],
                usuario=request.user,
                referencia_lote=data.get("referencia_lote"),
                cuentas_destino_override=data.get("cuentas_destino_override"),
            )
        except BancaElectronicaError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(LotePagoBancarioSerializer(lote).data, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        request_body=GenerarLoteNominaInputSerializer,
        responses={201: LotePagoBancarioSerializer},
    )
    @action(detail=False, methods=["post"], url_path="generar-nomina")
    def generar_nomina(self, request):
        serializer = GenerarLoteNominaInputSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            lote = generar_lote_pagos_nomina(
                empresa=data["empresa"],
                cuenta_bancaria=data["cuenta_bancaria"],
                proceso_nomina=data["proceso_nomina"],
                formato_banco=data["formato_banco"],
                fecha_valor=data["fecha_valor"],
                usuario=request.user,
                cuentas_empleados=data.get("cuentas_empleados"),
                referencia_lote=data.get("referencia_lote"),
            )
        except BancaElectronicaError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(LotePagoBancarioSerializer(lote).data, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        responses={
            200: openapi.Response(
                description="Archivo plano/CSV del lote bancario",
                schema=openapi.Schema(type=openapi.TYPE_STRING),
            )
        }
    )
    @action(detail=True, methods=["get"], url_path="descargar")
    def descargar(self, request, pk=None):
        lote = self.get_object()
        ext_default = "csv" if lote.formato_banco == "GENERICO_CSV" else "txt"
        raw_name = lote.nombre_archivo or f"lote_{lote.pk}.{ext_default}"
        safe_name = os.path.basename(re.sub(r"[^A-Za-z0-9._\-]", "_", raw_name)) or f"lote.{ext_default}"
        content_type = (
            "text/csv; charset=utf-8" if lote.formato_banco == "GENERICO_CSV" else "text/plain; charset=utf-8"
        )
        resp = HttpResponse(lote.contenido_archivo, content_type=content_type)
        resp["Content-Disposition"] = f'attachment; filename="{safe_name}"'
        resp["X-Content-Type-Options"] = "nosniff"
        if lote.sha256_archivo:
            resp["X-Lote-Sha256"] = lote.sha256_archivo
        return resp

    @swagger_auto_schema(request_body=no_body, responses={200: LotePagoBancarioSerializer})
    @action(detail=True, methods=["post"], url_path="marcar-enviado")
    def marcar_enviado(self, request, pk=None):
        lote = self.get_object()
        try:
            actualizado = cambiar_estado_lote(lote, "ENVIADO", request.user)
        except BancaElectronicaError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(LotePagoBancarioSerializer(actualizado).data)

    @swagger_auto_schema(request_body=no_body, responses={200: LotePagoBancarioSerializer})
    @action(detail=True, methods=["post"], url_path="marcar-procesado")
    def marcar_procesado(self, request, pk=None):
        lote = self.get_object()
        try:
            actualizado = cambiar_estado_lote(lote, "PROCESADO", request.user)
        except BancaElectronicaError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(LotePagoBancarioSerializer(actualizado).data)

    @swagger_auto_schema(request_body=no_body, responses={200: LotePagoBancarioSerializer})
    @action(detail=True, methods=["post"], url_path="anular")
    def anular(self, request, pk=None):
        lote = self.get_object()
        try:
            actualizado = cambiar_estado_lote(lote, "ANULADO", request.user)
        except BancaElectronicaError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(LotePagoBancarioSerializer(actualizado).data)


class ValidarReferenciaView(APIView):
    """Detecta referencias bancarias duplicadas en pagos, extractos y lotes activos del tenant."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=ValidarReferenciaInputSerializer,
        responses={200: ValidarReferenciaResponseSerializer},
    )
    def post(self, request):
        serializer = ValidarReferenciaInputSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            resultado = validar_referencia_bancaria(
                empresa=data["empresa"],
                cuenta_bancaria=data.get("cuenta_bancaria"),
                referencia=data["referencia"],
                excluir_pago_id=data.get("excluir_pago_id"),
            )
        except BancaElectronicaError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(resultado)


class ValidarCuentaVeView(APIView):
    """Valida estructura y prefijo SUDEBAN de 20 dígitos para cuentas bancarias VE."""

    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        request_body=ValidarCuentaVeInputSerializer,
        responses={200: ValidarCuentaVeResponseSerializer},
    )
    def post(self, request):
        serializer = ValidarCuentaVeInputSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        resultado = validar_cuenta_bancaria_ve(serializer.validated_data["numero_cuenta"])
        return Response(resultado)
