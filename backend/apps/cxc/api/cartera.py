"""
Dashboard de cartera.
Toda la lógica se delega a cuentas_por_cobrar.services.
CxC no implementa aging ni scoring — solo los consume y cachea.
"""
from datetime import date

from django.core.cache import cache
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.core.viewsets import get_empresas_visible


class CarteraDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        empresa = get_empresas_visible(request.user).first()
        cache_key = f"cxc:aging:{empresa.pk}"
        resumen = cache.get(cache_key)

        if not resumen:
            from apps.cuentas_por_cobrar.services_cartera_provider import get_cartera_provider
            from apps.cuentas_por_cobrar.services_aging import calcular_aging
            from apps.cuentas_por_cobrar.services_scoring import priorizar
            from apps.cxc.models import GestionCobranza

            provider = get_cartera_provider(empresa)
            partidas = provider.get_partidas()
            resumen = calcular_aging(partidas)

            # Calcular intentos sin respuesta desde historial CxC
            from django.db.models import Count
            intentos_raw = (
                GestionCobranza.objects.filter(
                    empresa=empresa,
                    resultado="sin_respuesta",
                    deleted_at__isnull=True,
                )
                .values("cliente_id")
                .annotate(n=Count("id"))
            )
            intentos_map = {row["cliente_id"]: row["n"] for row in intentos_raw}

            resumen["top_prioridades"] = priorizar(partidas, intentos_map)[:10]
            cache.set(cache_key, resumen, timeout=900)

        # Tasa del día desde finanzas.TasaCambio
        from apps.finanzas.models import TasaCambio
        tasa_hoy = (
            TasaCambio.objects.filter(
                fecha_tasa=date.today(),
                tipo_tasa="OFICIAL_BCV",
                id_moneda_origen__codigo_iso="USD",
                id_moneda_destino__codigo_iso="VES",
            )
            .order_by("-fecha_creacion")
            .first()
        )
        resumen["tasa_bcv_hoy"] = str(tasa_hoy.valor_tasa) if tasa_hoy else None

        return Response(resumen)
