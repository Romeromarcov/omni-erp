"""ViewSet para AcuerdoPago."""
import logging
from apps.core.serializer_mixins import TenantFKScopeMixin
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from apps.core.idempotency import idempotent
from apps.core.viewsets import get_empresas_visible
from apps.cxc.models import AcuerdoPago, CuotaAcuerdo
from apps.cxc.api.serializers import (
    AcuerdoPagoSerializer,
    AcuerdoPagoCreateSerializer,
    CuotaAcuerdoSerializer,
    RegistrarPagoSerializer,
)


class AcuerdoPagoViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
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

    @idempotent("cxc:acuerdo-registrar-pago")
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

        with transaction.atomic():
            from apps.finanzas.models import Pago, Moneda, MetodoPago

            # BUG-A2: lock + verificación DENTRO de la transacción — dos pagos
            # concurrentes sobre la misma cuota se serializan y el segundo ve el
            # estado ya actualizado (no hay doble cobro).
            try:
                cuota = CuotaAcuerdo.objects.select_for_update().get(
                    id=data["cuota_id"],
                    acuerdo=acuerdo,
                )
            except CuotaAcuerdo.DoesNotExist:
                return Response({"error": "Cuota no encontrada en este acuerdo"}, status=404)

            if cuota.estado == "pagado":
                return Response({"error": "Esta cuota ya está pagada"}, status=400)

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

            from decimal import Decimal

            from apps.finanzas.services import (
                TasaCambioError,
                convertir_monto,
                obtener_tasa_cambio,
            )

            # BUG-A2: el monto aplicado a la cuota se convierte a la moneda del
            # acuerdo (100 VES NO saldan una cuota de 100 USD). Sin tasa
            # disponible el pago se rechaza — nunca se asume tasa 1 entre
            # monedas distintas.
            monto_aplicado = data["monto"]
            if moneda.codigo_iso != acuerdo.moneda_codigo:
                try:
                    monto_aplicado = convertir_monto(
                        data["monto"], moneda, acuerdo.moneda_codigo,
                        empresa=acuerdo.empresa,
                    )
                except TasaCambioError:
                    return Response(
                        {
                            "code": "tasa_no_disponible",
                            "detail": (
                                "No hay tasa de cambio disponible entre la moneda "
                                "del pago y la moneda del acuerdo."
                            ),
                        },
                        status=400,
                    )

            # M-BUG-9: tasa real (moneda del pago → moneda base de la empresa) en
            # vez de hardcodear 1. Fallback conservador a 1 si no hay tasa o es la
            # misma moneda, para no bloquear el pago.
            tasa_pago = Decimal("1")
            empresa_base = getattr(acuerdo.empresa, "id_moneda_base", None)
            if empresa_base is not None and empresa_base.pk != moneda.pk:
                try:
                    tasa_pago = obtener_tasa_cambio(
                        moneda, empresa_base, empresa=acuerdo.empresa
                    ).valor_tasa
                except TasaCambioError:
                    logger.warning(
                        "registrar_pago: sin tasa %s→base para empresa=%s; se usa tasa=1.",
                        getattr(moneda, "codigo_iso", moneda), acuerdo.empresa_id,
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
                tasa=tasa_pago,
                id_metodo_pago=metodo_pago,
                referencia=data.get("referencia", ""),
                observaciones=data.get("observaciones", f"Cuota {cuota.numero_cuota} — Acuerdo {acuerdo.pk}"),
            )

            # Actualizar cuota — BUG-A2: el pago parcial se ACUMULA, no se
            # sobrescribe (dos parciales de 40 y 60 saldan una cuota de 100).
            cuota.pago = pago
            cuota.monto_pagado = (cuota.monto_pagado or Decimal("0")) + monto_aplicado
            cuota.fecha_pago = timezone.now().date()

            if cuota.monto_pagado >= cuota.monto:
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

            # R-CODE-11: AsientoContable en la misma transacción (centralizado).
            # M-BUG-10: generar_asiento_o_fallar tolera la ausencia de mapeo SOLO si
            # la empresa no tiene contabilidad activa; si la tiene, o si el asiento
            # falla por descuadre (AsientoError), propaga y la transacción del pago
            # revierte para no quedar descuadrada.
            from apps.contabilidad.services import AsientoError, generar_asiento_o_fallar

            try:
                generar_asiento_o_fallar(
                    "PAGO_CXC", cuota, acuerdo.empresa, data["monto"], usuario=request.user
                )
            except AsientoError:
                logger.exception(
                    "registrar_pago: asiento contable obligatorio falló | empresa=%s | cuota=%s",
                    acuerdo.empresa_id, cuota.id,
                )
                transaction.set_rollback(True)
                return Response(
                    {
                        "code": "asiento_contable_requerido",
                        "detail": "No se pudo generar el asiento contable. "
                        "Configure el Mapeo Contable de la empresa.",
                    },
                    status=422,
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
