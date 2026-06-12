"""
API de pagos de contribuciones parafiscales — Capa B §6.7 (tropicalización VE).

POST   /api/fiscal/pagos-parafiscales/               — declarar período por pagar
GET    /api/fiscal/pagos-parafiscales/?estado=&contribucion=&periodo_año=&periodo_mes=
POST   /api/fiscal/pagos-parafiscales/{pk}/pagar/    — pendiente → pagado
POST   /api/fiscal/pagos-parafiscales/{pk}/anular/   — pendiente → anulado

El POST de creación y la acción ``pagar`` (que mueve dinero) aceptan la
cabecera ``Idempotency-Key`` (P1-2, mismo contrato que finanzas:pago).
Errores: transición inválida o datos de negocio → 400; contabilidad activa sin
MapeoContable PAGO_PARAFISCAL → 422 (la transacción completa ya fue revertida);
recursos de otra empresa → 404 (R-CODE-1).
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.fields import DateField
from rest_framework.response import Response

from apps.core.idempotency import IdempotentCreateMixin, idempotent
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import PagoContribucionParafiscal
from .serializers_parafiscales import PagoContribucionParafiscalSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class PagoContribucionParafiscalViewSet(IdempotentCreateMixin, BaseModelViewSet):
    queryset = PagoContribucionParafiscal.objects.all()
    serializer_class = PagoContribucionParafiscalSerializer
    search_fields = ["referencia", "contribucion__codigo", "contribucion__nombre"]

    # P1-2: POST de creación idempotente por cabecera Idempotency-Key (opt-in).
    idempotency_scope = "fiscal:pago-parafiscal"
    # P1-1: techo estricto para escritura financiera (scope 'escritura').
    throttle_classes = [*BaseModelViewSet.throttle_classes, EscrituraRateThrottle]

    def get_queryset(self):
        # R-CODE-1: solo pagos de empresas visibles del usuario.
        qs = PagoContribucionParafiscal.objects.filter(
            id_empresa__in=_empresas(self.request)
        ).select_related("contribucion", "id_moneda", "id_pago", "id_proceso_nomina")

        estado = self.request.query_params.get("estado")
        contribucion_id = self.request.query_params.get("contribucion")
        año = self.request.query_params.get("periodo_año")
        mes = self.request.query_params.get("periodo_mes")
        if estado:
            qs = qs.filter(estado=estado)
        if contribucion_id:
            qs = qs.filter(contribucion=contribucion_id)
        if año:
            qs = qs.filter(periodo_año=año)
        if mes:
            qs = qs.filter(periodo_mes=mes)
        return qs.order_by("-periodo_año", "-periodo_mes", "-fecha_creacion")

    def destroy(self, request, *args, **kwargs):
        # R-CODE-6: un documento financiero no se borra (ni soft) — se ANULA,
        # y solo desde 'pendiente', para preservar la trazabilidad contable.
        return Response(
            {"error": "Un pago parafiscal no se elimina; use la acción 'anular'."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def _guardar_sin_doble_pago(self, serializer, **kwargs):
        """
        Persiste dentro de un savepoint y traduce la violación del constraint
        condicional ``uniq_pago_parafiscal_periodo_no_anulado`` (carrera de
        doble declaración que el validate() del serializer no alcanzó a ver)
        a un 400 de negocio en lugar de un 500.
        """
        from django.db import IntegrityError, transaction

        try:
            with transaction.atomic():
                serializer.save(**kwargs)
        except IntegrityError as exc:
            raise ValidationError(
                {
                    "detail": (
                        "Ya existe un pago (no anulado) de esa contribución para el mismo "
                        "período. No se permite el doble pago del mismo período + contribución."
                    )
                }
            ) from exc

    def perform_create(self, serializer):
        self._guardar_sin_doble_pago(serializer)

    def perform_update(self, serializer):
        self._guardar_sin_doble_pago(serializer)

    # ── helpers ────────────────────────────────────────────────────────────

    def _respuesta(self, pago, extra=None, http_status=status.HTTP_200_OK):
        data = PagoContribucionParafiscalSerializer(pago).data
        if extra:
            data.update(extra)
        return Response(data, status=http_status)

    # ── acciones de transición ─────────────────────────────────────────────

    @idempotent("fiscal:pago-parafiscal-pagar")
    @action(detail=True, methods=["post"], url_path="pagar")
    def pagar(self, request, pk=None):
        """
        Body: {"metodo_pago": "<uuid>", "caja": "<uuid Caja virtual>" |
               "cuenta_bancaria": "<uuid>", "referencia": "PLANILLA-123"
               (opcional), "fecha_pago": "YYYY-MM-DD" (opcional)}

        Ejecuta el pago: egreso en el libro de caja (Pago genérico +
        MovimientoCajaBanco + saldo) y asiento PAGO_PARAFISCAL — todo o nada.
        """
        from apps.contabilidad.services import AsientoError
        from apps.finanzas.models import Caja, CuentaBancariaEmpresa, MetodoPago

        from .services_parafiscales import PagoParafiscalError, pagar_contribucion_parafiscal

        pago_parafiscal = self.get_object()

        metodo_id = request.data.get("metodo_pago")
        if not metodo_id:
            raise ValidationError({"metodo_pago": "Este campo es requerido."})
        try:
            # El método puede ser de la empresa, global (empresa=None) o público.
            metodo = MetodoPago.objects.filter(
                Q(empresa_id=pago_parafiscal.id_empresa_id)
                | Q(empresa__isnull=True)
                | Q(es_publico=True)
            ).get(pk=metodo_id)
        except (MetodoPago.DoesNotExist, DjangoValidationError, ValueError):
            return Response(
                {"error": "Método de pago no encontrado para la empresa del pago."},
                status=status.HTTP_404_NOT_FOUND,
            )

        caja_id = request.data.get("caja")
        cuenta_id = request.data.get("cuenta_bancaria")
        if bool(caja_id) == bool(cuenta_id):
            raise ValidationError(
                {"detail": "Indique exactamente un origen de fondos: 'caja' o 'cuenta_bancaria'."}
            )

        caja = cuenta = None
        if caja_id:
            try:
                # R-CODE-1: la caja se busca SOLO dentro de la empresa del pago
                # (ya acotada a empresas visibles) — ajena/malformada → 404.
                caja = Caja.objects.get(pk=caja_id, empresa_id=pago_parafiscal.id_empresa_id)
            except (Caja.DoesNotExist, DjangoValidationError, ValueError):
                return Response(
                    {"error": "Caja no encontrada en la empresa del pago."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            try:
                cuenta = CuentaBancariaEmpresa.objects.get(
                    pk=cuenta_id, id_empresa_id=pago_parafiscal.id_empresa_id
                )
            except (CuentaBancariaEmpresa.DoesNotExist, DjangoValidationError, ValueError):
                return Response(
                    {"error": "Cuenta bancaria no encontrada en la empresa del pago."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        fecha_pago = None
        fecha_raw = request.data.get("fecha_pago")
        if fecha_raw:
            fecha_pago = DateField().run_validation(fecha_raw)

        try:
            pago = pagar_contribucion_parafiscal(
                pago_parafiscal=pago_parafiscal,
                usuario=request.user,
                metodo_pago=metodo,
                caja_virtual=caja,
                cuenta_bancaria=cuenta,
                referencia=request.data.get("referencia", ""),
                fecha_pago=fecha_pago,
            )
        except PagoParafiscalError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        except AsientoError as exc:
            # R-CODE-11: la transacción ya fue revertida (Pago + caja + estado).
            return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        pago_parafiscal.refresh_from_db()
        extra = {"pago_id": str(pago.pk)}
        if caja is not None:
            caja.refresh_from_db()
            extra["caja_saldo_actual"] = str(caja.saldo_actual)
        if cuenta is not None:
            cuenta.refresh_from_db()
            extra["cuenta_saldo_actual"] = str(cuenta.saldo_actual)
        return self._respuesta(pago_parafiscal, extra=extra)

    @action(detail=True, methods=["post"], url_path="anular")
    def anular(self, request, pk=None):
        """pendiente → anulado (libera el período para re-declarar)."""
        from .services_parafiscales import PagoParafiscalError, anular_pago_parafiscal

        pago_parafiscal = self.get_object()
        try:
            pago_parafiscal = anular_pago_parafiscal(pago_parafiscal)
        except PagoParafiscalError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return self._respuesta(pago_parafiscal)
