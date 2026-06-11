"""ViewSet para GestionCobranza y PlantillaCobranza."""
import logging
from apps.core.serializer_mixins import TenantFKScopeMixin
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from apps.core.viewsets import get_empresas_visible
from apps.cxc.models import GestionCobranza, PlantillaCobranza
from apps.cxc.api.serializers import (
    GestionCobranzaSerializer,
    PlantillaCobranzaSerializer,
)


def _empresa_actual(user):
    """SEC-NEW-2: empresa de trabajo del usuario vía el helper vetado
    get_empresas_visible (en vez de la property user.empresa, que ignora el
    aislamiento multi-empresa)."""
    return get_empresas_visible(user).first()


class PlantillaCobranzaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PlantillaCobranzaSerializer

    def get_queryset(self):
        return PlantillaCobranza.objects.filter(
            empresa__in=get_empresas_visible(self.request.user),
            deleted_at__isnull=True,
        ).order_by("canal", "nombre")

    def perform_create(self, serializer):
        serializer.save(empresa=_empresa_actual(self.request.user))

    def perform_destroy(self, instance):
        instance.soft_delete()


class GestionCobranzaViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = GestionCobranzaSerializer

    def get_queryset(self):
        return GestionCobranza.objects.filter(
            empresa__in=get_empresas_visible(self.request.user),
            deleted_at__isnull=True,
        ).order_by("-fecha_gestion")

    def perform_create(self, serializer):
        empresa = _empresa_actual(self.request.user)
        # Calcular score automáticamente
        from apps.cuentas_por_cobrar.services_scoring import ScoreInput, calcular_score
        from apps.cuentas_por_cobrar.services_cartera_provider import get_cartera_provider
        from django.db.models import Count

        cliente_id = serializer.validated_data.get("cliente_id", "")

        # Obtener datos para score
        dias_vencida = 0
        monto_pendiente = Decimal("0")
        try:
            provider = get_cartera_provider(empresa)
            partidas = provider.get_partidas(solo_vencidas=True)
            partida = next((p for p in partidas if p.cliente_id == cliente_id), None)
            if partida:
                dias_vencida = partida.dias_vencida
                monto_pendiente = partida.monto_pendiente
        except Exception as exc:  # noqa: BLE001 — score best-effort si la cartera no carga
            # M-BUG-7: no silenciar; el score degrada a defaults pero queda rastro.
            logger.warning(
                "cobranza: no se pudo obtener cartera para score (cliente=%s): %s",
                cliente_id, exc,
            )

        intentos = GestionCobranza.objects.filter(
            empresa=empresa,
            cliente_id=cliente_id,
            resultado="sin_respuesta",
            deleted_at__isnull=True,
        ).count()

        score = calcular_score(
            ScoreInput(
                dias_vencida=dias_vencida,
                monto_pendiente=monto_pendiente,
                intentos_sin_respuesta=intentos,
            )
        )

        # Invalidar cache de aging
        from django.core.cache import cache
        cache.delete(f"cxc:aging:{empresa.pk}")

        gestion = serializer.save(
            empresa=empresa,
            score=score,
            gestionado_por=self.request.user,
        )

        logger.info(
            "gestion_registrada | empresa=%s | cliente_id=%s | canal=%s | resultado=%s | score=%s",
            empresa.pk,
            gestion.cliente_id,
            gestion.canal,
            gestion.resultado,
            gestion.score,
        )

    def perform_destroy(self, instance):
        instance.soft_delete()

    @action(detail=False, methods=["get"])
    def prioridades(self, request):
        """Top clientes por score DESC."""
        from apps.cuentas_por_cobrar.services_cartera_provider import get_cartera_provider
        from apps.cuentas_por_cobrar.services_scoring import priorizar
        from django.db.models import Count

        empresa = _empresa_actual(request.user)
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

        provider = get_cartera_provider(empresa)
        partidas = provider.get_partidas(solo_vencidas=True)
        prioridades = priorizar(partidas, intentos_map)

        limit = min(int(request.query_params.get("limit", 20)), 100)
        return Response(prioridades[:limit])

    @action(detail=False, methods=["get"])
    def agenda(self, request):
        """Gestiones con próxima acción en los próximos N días."""
        dias = int(request.query_params.get("dias", 7))
        hoy = date.today()
        limite = hoy + timedelta(days=dias)

        qs = self.get_queryset().filter(
            proxima_accion__gte=hoy,
            proxima_accion__lte=limite,
        ).order_by("proxima_accion")

        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="preview-plantilla")
    def preview_plantilla(self, request, pk=None):
        """Renderiza variables de la plantilla con contexto real del cliente."""
        gestion = self.get_object()
        if not gestion.plantilla:
            return Response({"error": "Esta gestión no tiene plantilla asignada"}, status=400)

        contexto = {
            "cliente": gestion.cliente_nombre,
            "orden": gestion.orden_ref,
            "monto": request.data.get("monto", ""),
            "vencimiento": request.data.get("vencimiento", ""),
            "dias_vencida": request.data.get("dias_vencida", ""),
        }
        texto = gestion.plantilla.renderizar(contexto)
        return Response({"preview": texto, "asunto": gestion.plantilla.asunto})
