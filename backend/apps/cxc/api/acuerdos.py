"""ViewSet para AcuerdoPago."""
import logging
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from apps.core.viewsets import get_empresas_visible
from apps.cxc.models import AcuerdoPago, CuotaAcuerdo
from apps.cxc.api.serializers import (
    AcuerdoPagoSerializer,
    AcuerdoPagoCreateSerializer,
    CuotaAcuerdoSerializer,
    RegistrarPagoSerializer,
)


class AcuerdoPagoViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return AcuerdoPagoCreateSerializer
        return AcuerdoPagoSerializer

    def get_queryset(self):
        # H-SEC-12: aislar por empresas visibles (soporta usuarios multi-empresa).
        return AcuerdoPago.objects.filter(
            empresa__in=get_empresas_visible(self.request.user),
            deleted_at__isnull=True,
        ).prefetch_related("cuotas").order_by("-created_at")

    @transaction.atomic
    def perform_create(self, serializer):
        from apps.cxc.services.cuotas import generar_cuotas

        # H-SEC-12: empresa derivada del usuario, no del payload.
        empresa = get_empresas_visible(self.request.user).first()
        if empresa is None:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("El usuario no tiene empresa asignada.")
        acuerdo = serializer.save(empresa=empresa)

        # Generar cuotas en la misma transacción
        cuotas_data = generar_cuotas(
            acuerdo=acuerdo,
            fecha_inicio=acuerdo.fecha_inicio,
            plazo_total_dias=acuerdo.plazo_total_dias,
            periodicidad=acuerdo.periodicidad,
            monto_total=acuerdo.monto_total,
            monto_cuota=acuerdo.monto_cuota,
            porcentaje_abono=acuerdo.porcentaje_abono,
        )
        CuotaAcuerdo.objects.bulk_create([CuotaAcuerdo(**d) for d in cuotas_data])

    def perform_destroy(self, instance):
        instance.soft_delete()

    @action(detail=True, methods=["post"], url_path="registrar-pago")
    def registrar_pago(self, request, pk=None):
        """
        Registra el pago de una cuota.
        1. Valida datos de pago.
        2. Crea finanzas.Pago.
        3. Actualiza CuotaAcuerdo.
        4. Auto-completa el acuerdo si todas las cuotas están pagadas.
        """
        acuerdo = self.get_object()
        serializer = RegistrarPagoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            cuota = CuotaAcuerdo.objects.get(
                id=data["cuota_id"],
                acuerdo=acuerdo,
            )
        except CuotaAcuerdo.DoesNotExist:
            return Response({"error": "Cuota no encontrada en este acuerdo"}, status=404)

        if cuota.estado == "pagado":
            return Response({"error": "Esta cuota ya está pagada"}, status=400)

        with transaction.atomic():
            from apps.finanzas.models import Pago, Moneda, MetodoPago

            try:
                moneda = Moneda.objects.get(pk=data["moneda_id"])
            except Moneda.DoesNotExist:
                # M-API-3: código de error en vez de filtrar el str() de la excepción.
                return Response(
                    {"code": "moneda_no_encontrada", "detail": "La moneda indicada no existe."},
                    status=400,
                )
            try:
                metodo_pago = MetodoPago.objects.get(pk=data["metodo_pago_id"])
            except MetodoPago.DoesNotExist:
                return Response(
                    {"code": "metodo_pago_no_encontrado", "detail": "El método de pago indicado no existe."},
                    status=400,
                )

            # Crear pago en finanzas
            pago = Pago.objects.create(
                id_empresa=acuerdo.empresa,
                tipo_operacion="INGRESO",
                tipo_documento="AJUSTE",
                id_documento=cuota.id,
                fecha_pago=timezone.now(),
                monto=data["monto"],
                id_moneda=moneda,
                tasa=1,
                id_metodo_pago=metodo_pago,
                referencia=data.get("referencia", ""),
                observaciones=data.get("observaciones", f"Cuota {cuota.numero_cuota} — Acuerdo {acuerdo.pk}"),
            )

            # Actualizar cuota
            cuota.pago = pago
            cuota.monto_pagado = data["monto"]
            cuota.fecha_pago = timezone.now().date()

            if data["monto"] >= cuota.monto:
                cuota.estado = "pagado"
            else:
                cuota.estado = "parcial"
            cuota.save()

            # Auto-completar acuerdo si todas las cuotas están pagadas
            pendientes = CuotaAcuerdo.objects.filter(
                acuerdo=acuerdo,
                estado__in=["pendiente", "parcial", "vencido"],
            ).count()
            if pendientes == 0:
                acuerdo.estado = "cumplido"
                acuerdo.save(update_fields=["estado"])

            # R-CODE-11: AsientoContable en la misma transacción.
            # M-BUG-10: solo se tolera la ausencia de mapeo contable (empresa sin
            # contabilidad configurada). Cualquier otro error del asiento propaga
            # para que la transacción del pago revierta y no quede descuadrada.
            try:
                from apps.contabilidad.services import (
                    AsientoError,
                    MapeoContableNoEncontrado,
                    generar_asiento,
                )

                generar_asiento("PAGO_CXC", cuota, acuerdo.empresa, data["monto"])
            except (MapeoContableNoEncontrado, AsientoError) as exc:
                logger.warning(
                    "registrar_pago: asiento contable omitido para cuota=%s | empresa=%s | razón=%s",
                    cuota.id, acuerdo.empresa_id, exc,
                )

            logger.info(
                "pago_cuota_registrado | empresa=%s | acuerdo=%s | cuota=%s | "
                "monto=%s | estado_cuota=%s",
                acuerdo.empresa_id, acuerdo.pk, cuota.pk,
                data["monto"], cuota.estado,
            )

        return Response(
            CuotaAcuerdoSerializer(cuota).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="vencimientos-proximos")
    def vencimientos_proximos(self, request):
        """Cuotas que vencen en los próximos N días."""
        dias = int(request.query_params.get("dias", 7))
        hoy = date.today()
        limite = hoy + timedelta(days=dias)

        cuotas = CuotaAcuerdo.objects.filter(
            acuerdo__empresa__in=get_empresas_visible(request.user),
            acuerdo__deleted_at__isnull=True,
            fecha_vencimiento__gte=hoy,
            fecha_vencimiento__lte=limite,
            estado__in=["pendiente", "parcial"],
        ).select_related("acuerdo").order_by("fecha_vencimiento")

        serializer = CuotaAcuerdoSerializer(cuotas, many=True)
        return Response(serializer.data)
