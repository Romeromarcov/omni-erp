"""
P1-1 Hardening — throttles del proyecto.

``EscrituraRateThrottle`` aplica un techo más estricto (scope ``escritura``,
tasa configurable vía ``THROTTLE_RATE_ESCRITURA``) SOLO a métodos de escritura
(POST/PUT/PATCH/DELETE). Los métodos seguros (GET/HEAD/OPTIONS) no consumen
cuota de este scope — para ellos rigen los throttles globales anon/user.

Pensado para ViewSets de alto riesgo financiero (pagos, abonos), donde un
burst de escrituras es señal de abuso o de un cliente con bug, nunca de uso
legítimo.
"""

from rest_framework.permissions import SAFE_METHODS
from rest_framework.throttling import UserRateThrottle


class EscrituraRateThrottle(UserRateThrottle):
    """Throttle por usuario que solo cuenta métodos de escritura."""

    scope = "escritura"

    def allow_request(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return super().allow_request(request, view)
