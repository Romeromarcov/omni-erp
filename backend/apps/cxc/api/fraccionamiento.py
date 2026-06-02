"""ViewSets para Fraccionamiento (feature-flagged)."""
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.cxc.models import LoteFraccionado, VentaFraccionada
from apps.cxc.api.serializers import LoteFraccionadoSerializer, VentaFraccionadaSerializer
from apps.core.viewsets import get_empresas_visible


def _fraccionamiento_enabled(empresa) -> bool:
    """Verifica si el módulo de fraccionamiento está habilitado para el tenant."""
    from apps.configuracion_motor.models import ParametroSistema
    try:
        param = ParametroSistema.objects.get(
            id_empresa=empresa,
            codigo_parametro="cxc.fraccionamiento.enabled",
            activo=True,
        )
        return param.valor_parametro.strip().lower() in ("true", "1", "yes")
    except ParametroSistema.DoesNotExist:
        return False


class LoteFraccionadoViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = LoteFraccionadoSerializer

    def get_queryset(self):
        return LoteFraccionado.objects.filter(
            empresa__in=get_empresas_visible(self.request.user),
            deleted_at__isnull=True,
        ).order_by("-created_at")

    def list(self, request, *args, **kwargs):
        if not _fraccionamiento_enabled(get_empresas_visible(request.user).first()):
            return Response({"detail": "Módulo de fraccionamiento no habilitado."}, status=403)
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        empresa = get_empresas_visible(self.request.user).first()
        if not _fraccionamiento_enabled(empresa):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Módulo de fraccionamiento no habilitado.")
        lote = serializer.save(empresa=empresa)
        # Inicializar cantidad_actual = cantidad_inicial
        if lote.cantidad_actual == 0:
            lote.cantidad_actual = lote.cantidad_inicial
            lote.save(update_fields=["cantidad_actual"])

    def perform_destroy(self, instance):
        instance.soft_delete()


class VentaFraccionadaViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = VentaFraccionadaSerializer

    def get_queryset(self):
        return VentaFraccionada.objects.filter(
            empresa__in=get_empresas_visible(self.request.user),
            deleted_at__isnull=True,
        ).select_related("lote").order_by("-created_at")

    def perform_create(self, serializer):
        empresa = get_empresas_visible(self.request.user).first()
        if not _fraccionamiento_enabled(empresa):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Módulo de fraccionamiento no habilitado.")

        # M-BUG-8: reservar stock al crear la venta pendiente. Las ventas
        # pendientes del lote ya comprometen cantidad; rechazamos crear una que
        # sobrevendería el lote (evita pendientes que nunca podrán confirmarse).
        from django.db.models import Sum
        from rest_framework.exceptions import ValidationError

        lote = serializer.validated_data.get("lote")
        cantidad = serializer.validated_data.get("cantidad")
        if lote is not None and cantidad is not None:
            with transaction.atomic():
                lote_lock = LoteFraccionado.objects.select_for_update().get(pk=lote.pk)
                reservado = (
                    VentaFraccionada.objects.filter(
                        lote=lote_lock, estado="pendiente", deleted_at__isnull=True
                    ).aggregate(s=Sum("cantidad"))["s"]
                    or 0
                )
                if reservado + cantidad > lote_lock.cantidad_actual:
                    raise ValidationError(
                        f"Stock insuficiente para reservar: {lote_lock.cantidad_actual} disponibles, "
                        f"{reservado} ya reservados por ventas pendientes."
                    )
                serializer.save(empresa=empresa)
            return
        serializer.save(empresa=empresa)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def confirmar(self, request, pk=None):
        """Confirma la venta fraccionada y descuenta stock del lote."""
        venta = self.get_object()
        if venta.estado != "pendiente":
            return Response({"error": f"No se puede confirmar venta en estado '{venta.estado}'"}, status=400)

        lote = LoteFraccionado.objects.select_for_update().get(pk=venta.lote_id)
        if lote.cantidad_actual < venta.cantidad:
            return Response(
                {"error": f"Stock insuficiente: {lote.cantidad_actual} {lote.unidad_venta} disponibles"},
                status=400,
            )

        lote.cantidad_actual -= venta.cantidad
        if lote.cantidad_actual == 0:
            lote.estado = "agotado"
        lote.save(update_fields=["cantidad_actual", "estado"])

        venta.estado = "confirmada"
        venta.save(update_fields=["estado"])

        return Response(VentaFraccionadaSerializer(venta).data)

    @action(detail=False, methods=["get"])
    def resumen(self, request):
        """KPIs del módulo de fraccionamiento."""
        from django.db.models import Count, Sum
        from django.utils import timezone

        empresa = get_empresas_visible(request.user).first()
        inicio_mes = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        lotes_activos = LoteFraccionado.objects.filter(
            empresa=empresa, estado="activo", deleted_at__isnull=True
        ).count()

        ventas_mes = VentaFraccionada.objects.filter(
            empresa=empresa,
            estado="confirmada",
            created_at__gte=inicio_mes,
            deleted_at__isnull=True,
        ).aggregate(count=Count("id"), total=Sum("monto_total"))

        pendiente_cobro = VentaFraccionada.objects.filter(
            empresa=empresa,
            estado__in=["pendiente", "confirmada"],
            pago__isnull=True,
            deleted_at__isnull=True,
        ).aggregate(total=Sum("monto_total"))

        return Response({
            "lotes_activos": lotes_activos,
            "ventas_mes": ventas_mes["count"] or 0,
            "ingresos_mes": str(ventas_mes["total"] or 0),
            "pendiente_cobro": str(pendiente_cobro["total"] or 0),
        })
