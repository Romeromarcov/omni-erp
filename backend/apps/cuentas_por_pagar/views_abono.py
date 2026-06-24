from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import AbonoCxP
from .serializers_abono import AbonoCxPSerializer


class AbonoCxPViewSet(BaseModelViewSet):
    queryset = AbonoCxP.objects.all()
    serializer_class = AbonoCxPSerializer

    # Integridad financiera (deuda auditoría 2026-06-21 "AbonoCxP CRUD libre";
    # espejo del blindaje aplicado a CuentaPorPagar): un AbonoCxP NO se crea ni
    # edita por CRUD directo. Crear un abono debe pasar por el flujo atómico
    # ``registrar_abono_cxp`` (acción POST ``cuentas-por-pagar/{pk}/abonar/``),
    # que toma el lock de la CxP, valida el saldo, actualiza estado/pendiente y
    # postea el asiento PAGO_CXP. Un POST/PUT/PATCH/DELETE directo aquí saltaba
    # todo eso (saldo sin actualizar, sin asiento). Se deja solo lectura.
    http_method_names = ["get", "head", "options"]

    # P1-1: se conserva el throttle de escritura (no aplica en solo-lectura, pero
    # el contrato de seguridad S1 lo exige declarado en todos los viewsets de pago).
    throttle_classes = [*BaseModelViewSet.throttle_classes, EscrituraRateThrottle]

    def get_queryset(self):
        empresas = get_empresas_visible(self.request.user)
        return AbonoCxP.objects.filter(
            cuenta_por_pagar__id_empresa__in=empresas
        ).select_related("cuenta_por_pagar", "usuario")
