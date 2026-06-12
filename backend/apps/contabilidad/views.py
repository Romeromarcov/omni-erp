from django.db.models import Sum
from apps.core.serializer_mixins import TenantFKScopeMixin
from decimal import Decimal

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.viewsets import get_empresas_visible

from .models import AsientoContable, DetalleAsiento, MapeoContable, PlanCuentas
from .serializers import (
    AsientoContableSerializer,
    DetalleAsientoSerializer,
    MapeoContableSerializer,
    PlanCuentasSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


class PlanCuentasViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = PlanCuentas.objects.all()
    serializer_class = PlanCuentasSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["tipo_cuenta", "naturaleza", "activo", "id_empresa"]
    search_fields = ["codigo_cuenta", "nombre_cuenta"]
    ordering_fields = ["codigo_cuenta", "nombre_cuenta", "fecha_creacion"]
    ordering = ["codigo_cuenta"]

    def get_queryset(self):
        # R-CODE-1
        return PlanCuentas.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=False, methods=["get"])
    def activos(self, request):
        """Obtiene solo las cuentas activas"""
        cuentas_activas = self.get_queryset().filter(activo=True)
        serializer = self.get_serializer(cuentas_activas, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def por_tipo(self, request):
        """Obtiene cuentas agrupadas por tipo"""
        tipo = request.query_params.get("tipo", None)
        qs = self.get_queryset()
        if tipo:
            cuentas = qs.filter(tipo_cuenta=tipo, activo=True)
        else:
            cuentas = qs.filter(activo=True)

        serializer = self.get_serializer(cuentas, many=True)
        return Response(serializer.data)


class AsientoContableViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = AsientoContable.objects.all()
    serializer_class = AsientoContableSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["estado_asiento", "id_empresa", "fecha_asiento"]
    search_fields = ["numero_asiento", "descripcion"]
    ordering_fields = ["fecha_asiento", "numero_asiento", "fecha_creacion"]
    ordering = ["-fecha_asiento"]

    def get_queryset(self):
        # R-CODE-1
        return AsientoContable.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=True, methods=["post"])
    def aprobar(self, request, pk=None):
        """Aprueba un asiento contable"""
        asiento = self.get_object()

        # Validar que el asiento esté en estado borrador
        if asiento.estado_asiento != "BORRADOR":
            return Response(
                {"error": "Solo se pueden aprobar asientos en estado borrador"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Validar que el asiento cuadre
        detalles = DetalleAsiento.objects.filter(id_asiento=asiento)
        total_debe = detalles.aggregate(total=Sum("debe"))["total"] or 0
        total_haber = detalles.aggregate(total=Sum("haber"))["total"] or 0

        if total_debe != total_haber:
            return Response(
                {"error": f"El asiento no cuadra. Debe: {total_debe}, Haber: {total_haber}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        asiento.estado_asiento = "APROBADO"
        asiento.save()

        serializer = self.get_serializer(asiento)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        """Anula un asiento contable"""
        asiento = self.get_object()

        if asiento.estado_asiento == "ANULADO":
            return Response({"error": "El asiento ya está anulado"}, status=status.HTTP_400_BAD_REQUEST)

        asiento.estado_asiento = "ANULADO"
        asiento.save()

        serializer = self.get_serializer(asiento)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def balance_comprobacion(self, request):
        """Genera un balance de comprobación básico"""
        empresa_id = request.query_params.get("empresa_id")
        if not empresa_id:
            return Response({"error": "Debe especificar el ID de la empresa"}, status=status.HTTP_400_BAD_REQUEST)

        # H-SEC-10: la empresa solicitada debe estar entre las visibles del usuario.
        if not _empresas(request).filter(pk=empresa_id).exists():
            return Response({"error": "Empresa no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        # Obtener asientos aprobados
        asientos_aprobados = AsientoContable.objects.filter(id_empresa=empresa_id, estado_asiento="APROBADO")

        # Obtener detalles de esos asientos
        detalles = DetalleAsiento.objects.filter(id_asiento__in=asientos_aprobados).select_related(
            "id_cuenta_contable"
        )

        # Agrupar por cuenta
        cuentas_balance = {}
        for detalle in detalles:
            cuenta_id = str(detalle.id_cuenta_contable.id_cuenta_contable)
            if cuenta_id not in cuentas_balance:
                cuentas_balance[cuenta_id] = {
                    "codigo_cuenta": detalle.id_cuenta_contable.codigo_cuenta,
                    "nombre_cuenta": detalle.id_cuenta_contable.nombre_cuenta,
                    "tipo_cuenta": detalle.id_cuenta_contable.tipo_cuenta,
                    "debe": Decimal(0),
                    "haber": Decimal(0),
                }

            cuentas_balance[cuenta_id]["debe"] += detalle.debe
            cuentas_balance[cuenta_id]["haber"] += detalle.haber

        # Calcular saldos
        for cuenta in cuentas_balance.values():
            cuenta["saldo"] = cuenta["debe"] - cuenta["haber"]

        return Response(
            {
                "empresa_id": empresa_id,
                "cuentas": list(cuentas_balance.values()),
                "total_debe": sum(c["debe"] for c in cuentas_balance.values()),
                "total_haber": sum(c["haber"] for c in cuentas_balance.values()),
            }
        )


class DetalleAsientoViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    queryset = DetalleAsiento.objects.all()
    serializer_class = DetalleAsientoSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["id_asiento", "id_cuenta_contable"]
    ordering_fields = ["fecha_creacion"]
    ordering = ["fecha_creacion"]

    def get_queryset(self):
        # R-CODE-1 via parent AsientoContable
        return DetalleAsiento.objects.filter(id_asiento__id_empresa__in=_empresas(self.request))


class MapeoContableViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    """
    CRUD de mapeos contables (tipo de asiento automático → cuentas debe/haber).
    Expone también GET /tipos-asiento/ con el catálogo de tipos soportados.
    """

    queryset = MapeoContable.objects.all()
    serializer_class = MapeoContableSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["tipo_asiento", "activo", "id_empresa"]
    ordering_fields = ["tipo_asiento", "fecha_creacion"]
    ordering = ["tipo_asiento"]

    def get_queryset(self):
        # R-CODE-1
        return MapeoContable.objects.filter(id_empresa__in=_empresas(self.request)).select_related(
            "cuenta_debe", "cuenta_haber"
        )

    @action(detail=False, methods=["get"], url_path="tipos-asiento")
    def tipos_asiento(self, request):
        """Catálogo de tipos de asiento automático soportados por el motor."""
        return Response([{"value": v, "label": etiqueta} for v, etiqueta in MapeoContable.TIPOS_ASIENTO])
