from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import CategoriaGasto, DetalleGasto, Gasto, ReembolsoGasto
from .serializers import (
    CategoriaGastoSerializer,
    DetalleGastoSerializer,
    GastoSerializer,
    ReembolsoGastoSerializer,
)
from .services import GastoError, aprobar_gasto, rechazar_gasto


def _empresas(request):
    return get_empresas_visible(request.user)


class CategoriaGastoViewSet(BaseModelViewSet):  # BUG-03: era viewsets.ModelViewSet
    queryset = CategoriaGasto.objects.all()
    serializer_class = CategoriaGastoSerializer
    filterset_fields = ["activo", "id_empresa"]
    search_fields = ["nombre_categoria", "descripcion"]
    ordering_fields = ["nombre_categoria", "fecha_creacion"]
    ordering = ["nombre_categoria"]

    def get_queryset(self):
        # R-CODE-1: filtrar por empresas visibles del usuario autenticado
        return CategoriaGasto.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=False, methods=["get"])
    def activas(self, request):
        """Obtiene solo las categorías activas de las empresas propias"""
        categorias_activas = self.get_queryset().filter(activo=True)
        serializer = self.get_serializer(categorias_activas, many=True)
        return Response(serializer.data)


class GastoViewSet(BaseModelViewSet):  # BUG-03: era viewsets.ModelViewSet
    queryset = Gasto.objects.all()
    serializer_class = GastoSerializer
    filterset_fields = ["estado_gasto", "id_empresa", "id_categoria_gasto", "fecha_gasto"]
    search_fields = ["descripcion"]
    ordering_fields = ["fecha_gasto", "monto", "fecha_creacion"]
    ordering = ["-fecha_gasto"]

    def get_queryset(self):
        # R-CODE-1: filtrar por empresas visibles del usuario autenticado
        return Gasto.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=True, methods=["post"])
    def aprobar(self, request, pk=None):
        """Aprueba un gasto y genera su(s) asiento(s) contable(s) (R-CODE-11).

        La validación de respaldo documental, el enforcement de período fiscal y
        la generación de asientos viven en ``services.aprobar_gasto`` (atómico).
        """
        gasto = self.get_object()
        try:
            aprobar_gasto(gasto, usuario=request.user)
        except GastoError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        gasto.refresh_from_db()
        serializer = self.get_serializer(gasto)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def rechazar(self, request, pk=None):
        """Rechaza un gasto pendiente."""
        gasto = self.get_object()
        motivo = request.data.get("motivo", "")
        try:
            rechazar_gasto(gasto, usuario=request.user, motivo=motivo)
        except GastoError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        gasto.refresh_from_db()
        serializer = self.get_serializer(gasto)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def resumen_por_categoria(self, request):
        """Obtiene resumen de gastos por categoría"""
        # R-CODE-1: siempre parte de get_queryset() que ya filtra por empresa propia
        gastos = self.get_queryset().filter(
            estado_gasto__in=["APROBADO", "REEMBOLSADO", "CONTABILIZADO"]
        ).select_related("id_categoria_gasto")

        empresa_id = request.query_params.get("empresa_id")

        # Agrupar por categoría
        resumen = {}
        for gasto in gastos:
            categoria_id = str(gasto.id_categoria_gasto.id_categoria_gasto)
            if categoria_id not in resumen:
                resumen[categoria_id] = {
                    "categoria_nombre": gasto.id_categoria_gasto.nombre_categoria,
                    "total_gastos": 0,
                    "cantidad_gastos": 0,
                }

            resumen[categoria_id]["total_gastos"] += gasto.monto
            resumen[categoria_id]["cantidad_gastos"] += 1

        return Response(
            {
                "empresa_id": empresa_id,
                "resumen_por_categoria": list(resumen.values()),
                "total_general": sum(r["total_gastos"] for r in resumen.values()),
            }
        )

    @action(detail=False, methods=["get"])
    def pendientes_aprobacion(self, request):
        """Obtiene gastos pendientes de aprobación de las empresas propias"""
        # R-CODE-1: get_queryset() ya aplica filtro de empresa; nunca self.queryset
        gastos_pendientes = self.get_queryset().filter(estado_gasto="PENDIENTE_APROBACION")
        serializer = self.get_serializer(gastos_pendientes, many=True)
        return Response(serializer.data)


class ReembolsoGastoViewSet(BaseModelViewSet):  # BUG-03: era viewsets.ModelViewSet
    queryset = ReembolsoGasto.objects.all()
    serializer_class = ReembolsoGastoSerializer
    filterset_fields = ["estado_reembolso", "id_empresa", "fecha_reembolso"]

    def get_queryset(self):
        # R-CODE-1
        return ReembolsoGasto.objects.filter(id_empresa__in=_empresas(self.request))

    search_fields = ["id_gasto__descripcion"]
    ordering_fields = ["fecha_reembolso", "monto_reembolso", "fecha_creacion"]
    ordering = ["-fecha_reembolso"]

    @action(detail=True, methods=["post"])
    def procesar_pago(self, request, pk=None):
        """Procesa el pago de un reembolso"""
        reembolso = self.get_object()

        if reembolso.estado_reembolso != "PENDIENTE":
            return Response(
                {"error": "Solo se pueden procesar reembolsos pendientes"}, status=status.HTTP_400_BAD_REQUEST
            )

        reembolso.estado_reembolso = "PAGADO"
        reembolso.save()

        # También actualizar el estado del gasto asociado
        gasto = reembolso.id_gasto
        if gasto.estado_gasto == "APROBADO":
            gasto.estado_gasto = "REEMBOLSADO"
            gasto.save()

        serializer = self.get_serializer(reembolso)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        """Anula un reembolso"""
        reembolso = self.get_object()

        if reembolso.estado_reembolso == "PAGADO":
            return Response({"error": "No se puede anular un reembolso ya pagado"}, status=status.HTTP_400_BAD_REQUEST)

        reembolso.estado_reembolso = "ANULADO"
        reembolso.save()

        serializer = self.get_serializer(reembolso)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def pendientes_pago(self, request):
        """Obtiene reembolsos pendientes de pago (solo empresa propia — R-CODE-1)."""
        # R-CODE-1: get_queryset() ya filtra por empresa visible; nunca self.queryset
        reembolsos_pendientes = self.get_queryset().filter(estado_reembolso="PENDIENTE")
        serializer = self.get_serializer(reembolsos_pendientes, many=True)
        return Response(serializer.data)


class DetalleGastoViewSet(BaseModelViewSet):
    """Líneas de imputación contable de un gasto (ExpenseLine)."""

    queryset = DetalleGasto.objects.all()
    serializer_class = DetalleGastoSerializer
    filterset_fields = ["id_gasto", "id_cuenta_contable"]
    ordering_fields = ["monto"]

    def get_queryset(self):
        # R-CODE-1: el detalle se acota por la empresa del gasto padre.
        return DetalleGasto.objects.filter(id_gasto__id_empresa__in=_empresas(self.request))
