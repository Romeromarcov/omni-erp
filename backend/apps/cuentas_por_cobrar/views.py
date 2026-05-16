from decimal import Decimal

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import CuentaPorCobrar
from .serializers import CuentaPorCobrarSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class CuentaPorCobrarViewSet(BaseModelViewSet):
    queryset = CuentaPorCobrar.objects.all()
    serializer_class = CuentaPorCobrarSerializer

    def get_queryset(self):
        qs = CuentaPorCobrar.objects.filter(
            empresa__in=_empresas(self.request)
        ).select_related("cliente", "empresa").prefetch_related("abonos")

        empresa_id = self.request.query_params.get("empresa")
        cliente_id = self.request.query_params.get("cliente")
        estado = self.request.query_params.get("estado")

        if empresa_id:
            qs = qs.filter(empresa=empresa_id)
        if cliente_id:
            qs = qs.filter(cliente=cliente_id)
        if estado:
            qs = qs.filter(estado=estado)

        return qs.order_by("fecha_vencimiento")

    @action(detail=False, methods=["get"], url_path="aging")
    def aging(self, request):
        """
        GET /api/cxc/cuentas-por-cobrar/aging/?empresa=<uuid>

        Devuelve el reporte de antigüedad de saldos por empresa.
        """
        from .services import calcular_aging

        empresa_id = request.query_params.get("empresa")
        if not empresa_id:
            return Response(
                {"error": "Parámetro 'empresa' requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if str(empresa_id) not in [str(e.id_empresa) for e in _empresas(request)]:
            return Response(
                {"error": "Empresa no encontrada o sin acceso."},
                status=status.HTTP_403_FORBIDDEN,
            )

        resultado = calcular_aging(empresa_id)
        # Serializar Decimals
        def fmt(d):
            return {k: str(v) if isinstance(v, Decimal) else v for k, v in d.items()}

        return Response(
            {
                "empresa_id": empresa_id,
                "corriente": fmt(resultado["corriente"]),
                "dias_1_30": fmt(resultado["dias_1_30"]),
                "dias_31_60": fmt(resultado["dias_31_60"]),
                "dias_61_90": fmt(resultado["dias_61_90"]),
                "dias_90_mas": fmt(resultado["dias_90_mas"]),
                "total_general": str(resultado["total_general"]),
            }
        )

    @action(detail=True, methods=["post"], url_path="abonar")
    def abonar(self, request, pk=None):
        """
        POST /api/cxc/cuentas-por-cobrar/{pk}/abonar/
        Body: {"monto": "500.00", "descripcion": "Pago parcial"}
        """
        from .services import AbonoError, registrar_abono

        cxc = self.get_object()
        monto_raw = request.data.get("monto")
        if not monto_raw:
            raise ValidationError({"monto": "Este campo es requerido."})

        try:
            monto = Decimal(str(monto_raw))
        except Exception:
            raise ValidationError({"monto": "Monto inválido."})

        descripcion = request.data.get("descripcion", "")

        try:
            abono = registrar_abono(
                cxc=cxc,
                monto=monto,
                usuario=request.user,
                descripcion=descripcion,
            )
        except AbonoError as exc:
            raise ValidationError(str(exc)) from exc

        cxc.refresh_from_db()
        return Response(
            {
                "abono_id": str(abono.pk),
                "cxc_id": str(cxc.pk),
                "monto_abonado": str(abono.monto),
                "estado_cxc": cxc.estado,
            },
            status=status.HTTP_201_CREATED,
        )
