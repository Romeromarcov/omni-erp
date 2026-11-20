from __future__ import annotations

import uuid
from typing import Any

from django.db.models import QuerySet
from drf_yasg.utils import no_body, swagger_auto_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.exceptions import domain_error_response
from apps.core.serializer_mixins import TenantFKScopeMixin
from apps.core.viewsets import SoftDeleteModelMixin, get_empresas_visible

from .models import AsientoContable, DetalleAsiento, DiarioContable, MapeoContable, PeriodoContable, PlanCuentas
from .serializers import (
    AsientoContableSerializer,
    CerrarEjercicioInputSerializer,
    CerrarEjercicioResponseSerializer,
    CerrarPeriodoDetalleInputSerializer,
    CerrarPeriodoInputSerializer,
    DetalleAsientoSerializer,
    DiarioContableSerializer,
    MapeoContableSerializer,
    PeriodoContableSerializer,
    PlanCuentasSerializer,
    ReabrirPeriodoInputSerializer,
    RevertirAsientoInputSerializer,
)
from .services import (
    AsientoError,
    aprobar_asiento,
    cerrar_ejercicio_contable,
    cerrar_periodo_contable,
    reabrir_periodo_contable,
    revertir_asiento,
)
from .services_reportes import generar_balance_comprobacion
from .views_reportes import serializar_reporte_json


def _empresas(request: Request) -> Any:
    return get_empresas_visible(request.user)


class _NulSafeFilterMixin:
    """Rechaza bytes NUL en query params (``?search=``, ``?ordering=``, etc.) con HTTP 400."""

    def filter_queryset(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        request = getattr(self, "request", None)
        if request is not None:
            for key, value in request.query_params.items():
                if isinstance(value, str) and "\x00" in value:
                    raise ValidationError({key: "Parámetro de consulta inválido."})
        return super().filter_queryset(queryset)  # type: ignore[misc]


class PlanCuentasViewSet(_NulSafeFilterMixin, TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = PlanCuentas.objects.all()
    serializer_class = PlanCuentasSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["tipo_cuenta", "naturaleza", "activo", "id_empresa"]
    search_fields = ["codigo_cuenta", "nombre_cuenta"]
    ordering_fields = ["codigo_cuenta", "nombre_cuenta", "fecha_creacion"]
    ordering = ["codigo_cuenta"]

    def get_queryset(self) -> QuerySet[PlanCuentas]:
        # R-CODE-1
        return PlanCuentas.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=False, methods=["get"])
    def activos(self, request: Request) -> Response:
        """Obtiene solo las cuentas activas"""
        cuentas_activas = self.get_queryset().filter(activo=True)
        serializer = self.get_serializer(cuentas_activas, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def por_tipo(self, request: Request) -> Response:
        """Obtiene cuentas agrupadas por tipo"""
        tipo = request.query_params.get("tipo", None)
        if isinstance(tipo, str) and "\x00" in tipo:
            raise ValidationError({"tipo": "Parámetro inválido."})
        qs = self.get_queryset()
        if tipo:
            cuentas = qs.filter(tipo_cuenta=tipo, activo=True)
        else:
            cuentas = qs.filter(activo=True)

        serializer = self.get_serializer(cuentas, many=True)
        return Response(serializer.data)


class DiarioContableViewSet(_NulSafeFilterMixin, TenantFKScopeMixin, SoftDeleteModelMixin, viewsets.ModelViewSet):
    """CRUD de diarios contables (estilo ``account.journal``) aislado por tenant."""

    queryset = DiarioContable.objects.all()
    serializer_class = DiarioContableSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["tipo", "activo", "id_empresa"]
    search_fields = ["codigo", "nombre", "prefijo_secuencia"]
    ordering_fields = ["codigo", "nombre", "tipo", "fecha_creacion"]
    ordering = ["codigo"]

    def get_queryset(self) -> QuerySet[DiarioContable]:
        # R-CODE-1
        return DiarioContable.objects.filter(id_empresa__in=_empresas(self.request)).select_related(
            "cuenta_defecto_debe", "cuenta_defecto_haber", "id_cuenta_bancaria", "id_caja"
        )


class PeriodoContableViewSet(_NulSafeFilterMixin, TenantFKScopeMixin, viewsets.ModelViewSet):
    """Gestión de períodos contables mensuales y cierre de ejercicio."""

    queryset = PeriodoContable.objects.all()
    serializer_class = PeriodoContableSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["anio", "mes", "estado", "activo", "id_empresa"]
    search_fields = ["observaciones"]
    ordering_fields = ["anio", "mes", "estado", "fecha_cierre", "fecha_creacion"]
    ordering = ["-anio", "-mes"]

    def get_queryset(self) -> QuerySet[PeriodoContable]:
        # R-CODE-1
        return PeriodoContable.objects.filter(id_empresa__in=_empresas(self.request)).select_related(
            "asiento_cierre", "cerrado_por"
        )

    def perform_destroy(self, instance: PeriodoContable) -> None:
        if instance.estado == "CERRADO":
            raise ValidationError({"error": "No se puede eliminar un período contable cerrado."})
        instance.soft_delete()

    @swagger_auto_schema(
        request_body=CerrarPeriodoInputSerializer,
        responses={200: PeriodoContableSerializer},
    )
    @action(detail=False, methods=["post"], url_path="cerrar")
    def cerrar_por_fecha(self, request: Request) -> Response:
        """Cierra (o crea y cierra) un período mensual ``(id_empresa, anio, mes)``."""
        input_ser = CerrarPeriodoInputSerializer(data=request.data)
        input_ser.is_valid(raise_exception=True)
        datos = input_ser.validated_data

        empresa = _empresas(request).filter(pk=datos["id_empresa"]).first()
        if empresa is None:
            return Response({"error": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        try:
            periodo = cerrar_periodo_contable(
                empresa,
                datos["anio"],
                datos["mes"],
                usuario=request.user,  # type: ignore[arg-type]
                observaciones=datos.get("observaciones", ""),
            )
        except AsientoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)

        return Response(PeriodoContableSerializer(periodo).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        request_body=CerrarPeriodoDetalleInputSerializer,
        responses={200: PeriodoContableSerializer},
    )
    @action(detail=True, methods=["post"], url_path="cerrar")
    def cerrar_periodo(self, request: Request, pk: str | None = None) -> Response:
        """Cierra un período contable existente."""
        periodo_obj = self.get_object()
        input_ser = CerrarPeriodoDetalleInputSerializer(data=request.data)
        input_ser.is_valid(raise_exception=True)

        try:
            periodo = cerrar_periodo_contable(
                periodo_obj.id_empresa,
                periodo_obj.anio,
                periodo_obj.mes,
                usuario=request.user,  # type: ignore[arg-type]
                observaciones=input_ser.validated_data.get("observaciones", ""),
            )
        except AsientoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)

        return Response(PeriodoContableSerializer(periodo).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        request_body=ReabrirPeriodoInputSerializer,
        responses={200: PeriodoContableSerializer},
    )
    @action(detail=True, methods=["post"], url_path="reabrir")
    def reabrir(self, request: Request, pk: str | None = None) -> Response:
        """Reabre un período contable cerrado sin cierre anual activo."""
        periodo_obj = self.get_object()
        input_ser = ReabrirPeriodoInputSerializer(data=request.data)
        input_ser.is_valid(raise_exception=True)

        try:
            periodo = reabrir_periodo_contable(
                periodo_obj,
                usuario=request.user,  # type: ignore[arg-type]
                motivo=input_ser.validated_data.get("motivo", ""),
            )
        except AsientoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)

        return Response(PeriodoContableSerializer(periodo).data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        request_body=CerrarEjercicioInputSerializer,
        responses={200: CerrarEjercicioResponseSerializer},
    )
    @action(detail=False, methods=["post"], url_path="cerrar-ejercicio")
    def cerrar_ejercicio(self, request: Request) -> Response:
        """Ejecuta el cierre anual del ejercicio contable saldando cuentas de resultado a Patrimonio."""
        input_ser = CerrarEjercicioInputSerializer(data=request.data)
        input_ser.is_valid(raise_exception=True)
        datos = input_ser.validated_data

        empresa = _empresas(request).filter(pk=datos["id_empresa"]).first()
        if empresa is None:
            return Response({"error": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        cuenta = PlanCuentas.objects.filter(
            id_empresa=empresa,
            pk=datos["cuenta_resultado_acumulado"],
        ).first()
        if cuenta is None:
            return Response(
                {"error": "La cuenta de resultado acumulado no existe o no pertenece a la empresa."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            resultado = cerrar_ejercicio_contable(
                empresa,
                datos["anio"],
                cuenta,
                usuario=request.user,  # type: ignore[arg-type]
                fecha_cierre=datos.get("fecha_cierre"),
            )
        except AsientoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)

        return Response(CerrarEjercicioResponseSerializer(resultado).data, status=status.HTTP_200_OK)


class AsientoContableViewSet(_NulSafeFilterMixin, TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = AsientoContable.objects.all()
    serializer_class = AsientoContableSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["estado_asiento", "id_empresa", "fecha_asiento", "id_diario", "es_cierre"]
    search_fields = ["numero_asiento", "descripcion"]
    ordering_fields = ["fecha_asiento", "numero_asiento", "fecha_creacion"]
    ordering = ["-fecha_asiento"]

    def get_queryset(self) -> QuerySet[AsientoContable]:
        # R-CODE-1
        return AsientoContable.objects.filter(id_empresa__in=_empresas(self.request)).select_related(
            "id_diario", "asiento_revertido", "contra_asiento"
        )

    @swagger_auto_schema(request_body=no_body, responses={200: AsientoContableSerializer})
    @action(detail=True, methods=["post"])
    def aprobar(self, request: Request, pk: str | None = None) -> Response:
        """Aprueba un asiento contable"""
        asiento = self.get_object()
        try:
            asiento_aprobado = aprobar_asiento(asiento, usuario=request.user)  # type: ignore[arg-type]
        except AsientoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(asiento_aprobado)
        return Response(serializer.data)

    @swagger_auto_schema(request_body=no_body, responses={200: AsientoContableSerializer})
    @action(detail=True, methods=["post"])
    def anular(self, request: Request, pk: str | None = None) -> Response:
        """Anula un asiento contable en borrador"""
        asiento = self.get_object()

        if asiento.estado_asiento == "ANULADO":
            return Response({"error": "El asiento ya está anulado"}, status=status.HTTP_400_BAD_REQUEST)

        if asiento.estado_asiento == "APROBADO":
            return Response(
                {"error": "Un asiento APROBADO no se anula; use la acción 'revertir' para generar un contra-asiento."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        asiento.estado_asiento = "ANULADO"
        asiento.save(update_fields=["estado_asiento"])

        serializer = self.get_serializer(asiento)
        return Response(serializer.data)

    @swagger_auto_schema(
        request_body=RevertirAsientoInputSerializer,
        responses={201: AsientoContableSerializer},
    )
    @action(detail=True, methods=["post"], url_path="revertir")
    def revertir(self, request: Request, pk: str | None = None) -> Response:
        """Genera un contra-asiento atómico ``APROBADO`` con debe/haber invertidos."""
        asiento = self.get_object()
        input_ser = RevertirAsientoInputSerializer(data=request.data)
        input_ser.is_valid(raise_exception=True)
        datos = input_ser.validated_data

        try:
            contra = revertir_asiento(
                asiento,
                usuario=request.user,  # type: ignore[arg-type]
                fecha_reversion=datos.get("fecha_reversion"),
                motivo=datos.get("motivo", ""),
            )
        except AsientoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(contra)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def balance_comprobacion(self, request: Request) -> Response:
        """Genera un balance de comprobación básico delegando en el motor SQL canónico."""
        empresa_id = request.query_params.get("empresa_id")
        if not empresa_id:
            return Response({"error": "Debe especificar el ID de la empresa"}, status=status.HTTP_400_BAD_REQUEST)
        if "\x00" in empresa_id:
            return Response({"error": "ID de empresa inválido."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            empresa_uuid = uuid.UUID(empresa_id)
        except (ValueError, TypeError):
            return Response({"error": "ID de empresa inválido."}, status=status.HTTP_400_BAD_REQUEST)

        # H-SEC-10: la empresa solicitada debe estar entre las visibles del usuario.
        empresa = _empresas(request).filter(pk=empresa_uuid).first()
        if empresa is None:
            return Response({"error": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        reporte = generar_balance_comprobacion(empresa)
        return Response(serializar_reporte_json(reporte))


class DetalleAsientoViewSet(_NulSafeFilterMixin, TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = DetalleAsiento.objects.all()
    serializer_class = DetalleAsientoSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["id_asiento", "id_cuenta_contable", "id_contacto"]
    search_fields = ["descripcion_detalle", "id_cuenta_contable__codigo_cuenta", "id_cuenta_contable__nombre_cuenta"]
    ordering_fields = ["fecha_creacion", "debe", "haber"]
    ordering = ["fecha_creacion"]

    def get_queryset(self) -> QuerySet[DetalleAsiento]:
        # R-CODE-1 via parent AsientoContable
        return DetalleAsiento.objects.filter(id_asiento__id_empresa__in=_empresas(self.request)).select_related(
            "id_cuenta_contable", "id_contacto"
        )


class MapeoContableViewSet(_NulSafeFilterMixin, TenantFKScopeMixin, viewsets.ModelViewSet):
    """
    CRUD de mapeos contables (tipo de asiento automático → cuentas debe/haber).
    Expone también GET /tipos-asiento/ con el catálogo de tipos soportados.
    """

    queryset = MapeoContable.objects.all()
    serializer_class = MapeoContableSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["tipo_asiento", "activo", "id_empresa", "id_diario"]
    search_fields = ["tipo_asiento", "descripcion_plantilla"]
    ordering_fields = ["tipo_asiento", "fecha_creacion"]
    ordering = ["tipo_asiento"]

    def get_queryset(self) -> QuerySet[MapeoContable]:
        # R-CODE-1
        return MapeoContable.objects.filter(id_empresa__in=_empresas(self.request)).select_related(
            "cuenta_debe", "cuenta_haber", "id_diario"
        )

    @action(detail=False, methods=["get"], url_path="tipos-asiento")
    def tipos_asiento(self, request: Request) -> Response:
        """Catálogo de tipos de asiento automático soportados por el motor."""
        return Response([{"value": v, "label": etiqueta} for v, etiqueta in MapeoContable.TIPOS_ASIENTO])
