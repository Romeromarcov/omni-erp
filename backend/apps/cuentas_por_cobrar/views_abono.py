"""
ViewSet de Abonos CxC.

BUG-C1 (auditoría integral 2026-06-10): este ViewSet era un ModelViewSet de
CRUD libre — por POST se creaban abonos sin lock, sin tope de saldo, sin
actualizar el estado de la CxC y apuntando a CxC de otra empresa; DELETE
dejaba la CxC en `pagada` con saldo pendiente.

Ahora:
- ``create`` delega en el service ``registrar_abono`` (atómico + lock +
  tope de saldo + actualización de estado), validando el tenant de la CxC.
- ``update`` / ``partial_update`` / ``destroy`` están bloqueados (405):
  la anulación de un abono va por proceso de negocio, no por DELETE.
"""

from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import AbonoCxC, CuentaPorCobrar
from .serializers_abono import AbonoCxCSerializer


class AbonoCxCViewSet(BaseModelViewSet):
    queryset = AbonoCxC.objects.all()
    serializer_class = AbonoCxCSerializer

    # P1-1: techo estricto para escritura de pagos (scope 'escritura');
    # los GET siguen bajo los throttles globales anon/user.
    throttle_classes = BaseModelViewSet.throttle_classes + [EscrituraRateThrottle]

    # BUG-C1: sin PUT/PATCH/DELETE — DRF responde 405 Method Not Allowed.
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        empresas = get_empresas_visible(self.request.user)
        return AbonoCxC.objects.filter(
            cuenta_por_cobrar__empresa__in=empresas
        ).select_related("cuenta_por_cobrar", "usuario")

    def create(self, request, *args, **kwargs):
        """
        POST /api/cxc/abonos-cxc/
        Body: {"cuenta_por_cobrar": <id>, "monto": "500.00", "descripcion": "..."}

        Delega en ``registrar_abono`` (transacción atómica con
        ``select_for_update``): valida monto > 0, tope de saldo pendiente y
        actualiza el estado de la CxC. La CxC debe pertenecer a una empresa
        visible del usuario (R-CODE-1); si no, 404 sin revelar existencia.
        """
        from .services import AbonoError, registrar_abono

        cxc_id = request.data.get("cuenta_por_cobrar")
        if not cxc_id:
            raise ValidationError({"cuenta_por_cobrar": "Este campo es requerido."})

        try:
            cxc = CuentaPorCobrar.objects.get(
                pk=cxc_id,
                empresa__in=get_empresas_visible(request.user),
            )
        except (CuentaPorCobrar.DoesNotExist, ValueError, TypeError):
            # R-CODE-1: misma respuesta para "no existe" y "es de otra empresa".
            raise NotFound("Cuenta por cobrar no encontrada.")

        monto_raw = request.data.get("monto")
        if monto_raw in (None, ""):
            raise ValidationError({"monto": "Este campo es requerido."})
        try:
            monto = Decimal(str(monto_raw))
        except (InvalidOperation, ValueError):
            raise ValidationError({"monto": "Monto inválido."})

        descripcion = request.data.get("descripcion", "") or ""

        try:
            abono = registrar_abono(
                cxc=cxc,
                monto=monto,
                usuario=request.user,
                descripcion=descripcion,
            )
        except AbonoError as exc:
            # Mensaje de dominio controlado (no es un str(e) arbitrario).
            raise ValidationError({"monto": str(exc)}) from exc

        serializer = self.get_serializer(abono)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
