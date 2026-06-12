"""
API de Pagos de Terceros (Zelle) — Capa B §6.6 (tropicalización VE).

POST   /api/finanzas/pagos-terceros/                            — registrar cobro
POST   /api/finanzas/pagos-terceros/{pk}/abonar/                — pendiente → abonado
POST   /api/finanzas/pagos-terceros/{pk}/solicitar-reintegro/   — pendiente → reintegro_pendiente
POST   /api/finanzas/pagos-terceros/{pk}/asociar-proveedor/     — fija proveedor (pendiente)
POST   /api/finanzas/pagos-terceros/{pk}/marcar-reintegrado/    — reintegro_pendiente → reintegrado
POST   /api/finanzas/pagos-terceros/{pk}/anular/                — pendiente → anulado

Las acciones que mueven dinero (abonar / solicitar-reintegro) aceptan la
cabecera ``Idempotency-Key`` (P1-2, mismo contrato que cxc:abonar/cxp:abonar).
Errores: transición inválida o datos de negocio → 400; contabilidad activa sin
MapeoContable PAGO_TERCERO → 422 (la transacción completa ya fue revertida);
recursos de otra empresa → 404 (R-CODE-1).
"""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.idempotency import idempotent
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import PagoTercero
from .serializers_pagos_terceros import PagoTerceroSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class PagoTerceroViewSet(BaseModelViewSet):
    queryset = PagoTercero.objects.all()
    serializer_class = PagoTerceroSerializer
    search_fields = ["referencia_zelle", "concepto"]

    # P1-1: techo estricto para escritura financiera (scope 'escritura').
    throttle_classes = [*BaseModelViewSet.throttle_classes, EscrituraRateThrottle]

    def get_queryset(self):
        # R-CODE-1: solo pagos de empresas visibles del usuario.
        qs = PagoTercero.objects.filter(
            id_empresa__in=_empresas(self.request)
        ).select_related("id_proveedor", "id_moneda", "id_abono_cxp", "id_cxc_reintegro")

        estado = self.request.query_params.get("estado")
        proveedor_id = self.request.query_params.get("proveedor")
        if estado:
            qs = qs.filter(estado=estado)
        if proveedor_id:
            qs = qs.filter(id_proveedor=proveedor_id)
        return qs.order_by("-fecha", "-fecha_creacion")

    def destroy(self, request, *args, **kwargs):
        # R-CODE-6: un documento financiero no se borra (ni soft) — se ANULA,
        # y solo desde 'pendiente', para preservar la trazabilidad contable.
        return Response(
            {"error": "Un pago de tercero no se elimina; use la acción 'anular'."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    # ── helpers ────────────────────────────────────────────────────────────

    def _respuesta(self, pago, extra=None, http_status=status.HTTP_200_OK):
        data = PagoTerceroSerializer(pago).data
        if extra:
            data.update(extra)
        return Response(data, status=http_status)

    # ── acciones de transición ─────────────────────────────────────────────

    @idempotent("finanzas:pago-tercero-abonar")
    @action(detail=True, methods=["post"], url_path="abonar")
    def abonar(self, request, pk=None):
        """
        Body: {"cxp": "<uuid CxP del proveedor>", "descripcion": "..."}

        Aplica el cobro como abono USD a la CxP del proveedor (su saldo baja
        por ``monto``) y genera el asiento PAGO_TERCERO — todo o nada.
        """
        from apps.contabilidad.services import AsientoError
        from apps.cuentas_por_pagar.models import CuentaPorPagar

        from .services_pagos_terceros import PagoTerceroError, abonar_pago_tercero

        pago = self.get_object()

        cxp_id = request.data.get("cxp")
        if not cxp_id:
            raise ValidationError({"cxp": "Este campo es requerido."})
        try:
            # R-CODE-1: la CxP se busca SOLO dentro de la empresa del pago
            # (que ya está acotada a empresas visibles) — ajena → 404.
            # Un uuid malformado lanza DjangoValidationError → también 404.
            cxp = CuentaPorPagar.objects.get(pk=cxp_id, id_empresa=pago.id_empresa)
        except (CuentaPorPagar.DoesNotExist, DjangoValidationError, ValueError):
            return Response(
                {"error": "CxP no encontrada en la empresa del pago."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            abono = abonar_pago_tercero(
                pago=pago,
                cxp=cxp,
                usuario=request.user,
                descripcion=request.data.get("descripcion", ""),
            )
        except PagoTerceroError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        except AsientoError as exc:
            # R-CODE-11: la transacción ya fue revertida (abono + estado).
            return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        pago.refresh_from_db()
        cxp.refresh_from_db()
        return self._respuesta(
            pago,
            extra={
                "abono_id": str(abono.pk),
                "cxp_id": str(cxp.pk),
                "cxp_monto_pendiente": str(cxp.monto_pendiente),
                "cxp_estado": cxp.estado,
            },
        )

    @idempotent("finanzas:pago-tercero-reintegro")
    @action(detail=True, methods=["post"], url_path="solicitar-reintegro")
    def solicitar_reintegro(self, request, pk=None):
        """
        Body: {"comision": "5.00" (opcional), "fecha_vencimiento": "YYYY-MM-DD"
               (opcional), "descripcion": "..." (opcional)}

        Emite una CxC contra el proveedor por monto − comisión y genera el
        asiento PAGO_TERCERO por el neto — todo o nada.
        """
        from apps.contabilidad.services import AsientoError

        from .services_pagos_terceros import PagoTerceroError, solicitar_reintegro

        pago = self.get_object()

        comision_raw = request.data.get("comision")
        comision = None
        if comision_raw not in (None, ""):
            try:
                comision = Decimal(str(comision_raw))
            except (InvalidOperation, ValueError):
                raise ValidationError({"comision": "Comisión inválida."})

        fecha_vencimiento = None
        fecha_raw = request.data.get("fecha_vencimiento")
        if fecha_raw:
            from rest_framework.fields import DateField

            fecha_vencimiento = DateField().run_validation(fecha_raw)

        try:
            cxc = solicitar_reintegro(
                pago=pago,
                usuario=request.user,
                comision=comision,
                fecha_vencimiento=fecha_vencimiento,
                descripcion=request.data.get("descripcion", ""),
            )
        except PagoTerceroError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        except AsientoError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        pago.refresh_from_db()
        return self._respuesta(
            pago,
            extra={
                "cxc_id": str(cxc.pk),
                "cxc_monto": str(cxc.monto),
                "cxc_fecha_vencimiento": str(cxc.fecha_vencimiento),
            },
        )

    @action(detail=True, methods=["post"], url_path="asociar-proveedor")
    def asociar_proveedor(self, request, pk=None):
        """Body: {"proveedor": "<uuid>"} — fija el proveedor (solo pendiente)."""
        from apps.proveedores.models import Proveedor

        from .services_pagos_terceros import PagoTerceroError, asociar_proveedor

        pago = self.get_object()

        proveedor_id = request.data.get("proveedor")
        if not proveedor_id:
            raise ValidationError({"proveedor": "Este campo es requerido."})
        try:
            # R-CODE-1: proveedor de otra empresa (o uuid malformado) → 404.
            proveedor = Proveedor.objects.get(pk=proveedor_id, id_empresa=pago.id_empresa)
        except (Proveedor.DoesNotExist, DjangoValidationError, ValueError):
            return Response(
                {"error": "Proveedor no encontrado en la empresa del pago."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            pago = asociar_proveedor(pago, proveedor)
        except PagoTerceroError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return self._respuesta(pago)

    @action(detail=True, methods=["post"], url_path="marcar-reintegrado")
    def marcar_reintegrado(self, request, pk=None):
        """reintegro_pendiente → reintegrado (confirmación manual)."""
        from .services_pagos_terceros import PagoTerceroError, marcar_reintegrado

        pago = self.get_object()
        try:
            pago = marcar_reintegrado(pago)
        except PagoTerceroError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return self._respuesta(pago)

    @action(detail=True, methods=["post"], url_path="anular")
    def anular(self, request, pk=None):
        """pendiente → anulado (solo sin efectos financieros generados)."""
        from .services_pagos_terceros import PagoTerceroError, anular_pago_tercero

        pago = self.get_object()
        try:
            pago = anular_pago_tercero(pago)
        except PagoTerceroError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return self._respuesta(pago)
