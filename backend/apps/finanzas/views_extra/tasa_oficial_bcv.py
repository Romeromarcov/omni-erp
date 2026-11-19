from datetime import date

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.finanzas.models import Moneda, TasaCambio
from apps.finanzas.serializers import TasaCambioSerializer


class TasaCambioOficialBCVView(APIView):
    """
    Devuelve la tasa oficial BCV global (id_empresa=None) para la fecha actual o la fecha indicada.
    Parámetros GET opcionales:
      - fecha (YYYY-MM-DD)
      - moneda_origen (ej: USD)
      - moneda_destino (ej: VES)
    """

    def get(self, request):
        # localdate() = hoy en TIME_ZONE (America/Caracas), no en UTC: con
        # date.today() la tasa "de hoy" no se encontraba tras las 20:00 Caracas
        # (= 00:00 UTC), porque buscaba la del día UTC siguiente.
        fecha = request.GET.get("fecha", timezone.localdate())
        if isinstance(fecha, str):
            try:
                fecha = date.fromisoformat(fecha)
            except Exception:
                return Response({"detail": "Formato de fecha inválido. Use YYYY-MM-DD."}, status=400)

        # Lógica para detectar moneda base y moneda de transacción
        moneda_origen = request.GET.get("moneda_origen")
        moneda_destino = request.GET.get("moneda_destino")
        id_empresa = request.GET.get("id_empresa")
        id_moneda_transaccion = request.GET.get("id_moneda_transaccion")

        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.db.models import Q

        from apps.core.viewsets import get_empresas_visible

        if getattr(request.user, "es_superusuario_omni", False):
            moneda_qs = Moneda.objects.all()
        else:
            moneda_qs = Moneda.objects.filter(
                Q(es_generica=True) | Q(es_publica=True) | Q(empresa__in=get_empresas_visible(request.user))
            )

        # Si no se especifica moneda_origen y moneda_destino, usar lógica de empresa y moneda de transacción
        if not moneda_origen or not moneda_destino:
            from apps.core.models import Empresa  # Ajusta el import si es necesario

            try:
                empresa = get_empresas_visible(request.user).get(id_empresa=id_empresa)
            except (Empresa.DoesNotExist, DjangoValidationError, ValueError, TypeError):
                return Response({"detail": "Empresa o moneda base no encontrada."}, status=404)
            # FIX: el campo del modelo es `id_moneda_base` (no `moneda_base`);
            # el AttributeError silenciado hacía que esta rama devolviera 404 siempre.
            moneda_base = empresa.id_moneda_base
            if moneda_base is None:
                return Response({"detail": "Empresa o moneda base no encontrada."}, status=404)
            try:
                moneda_transaccion = moneda_qs.get(id_moneda=id_moneda_transaccion)
            except (Moneda.DoesNotExist, DjangoValidationError, ValueError, TypeError):
                return Response({"detail": "Moneda de transacción no encontrada."}, status=404)
            origen = moneda_base
            destino = moneda_transaccion
        else:
            try:
                origen = moneda_qs.get(codigo_iso=moneda_origen)
                destino = moneda_qs.get(codigo_iso=moneda_destino)
            except Moneda.DoesNotExist:
                return Response({"detail": "Moneda no encontrada."}, status=404)

        tasa = (
            TasaCambio.objects.filter(
                fecha_tasa=fecha,
                id_moneda_origen=origen,
                id_moneda_destino=destino,
                tipo_tasa="OFICIAL_BCV",
                id_empresa=None,
            )
            .order_by("-fecha_tasa")
            .first()
        )
        if not tasa:
            return Response({"detail": "No hay tasa oficial BCV registrada para esa fecha."}, status=404)
        return Response(TasaCambioSerializer(tasa).data)
