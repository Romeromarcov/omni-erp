from decimal import Decimal

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import CuentaPorPagar
from .serializers import CuentaPorPagarSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class CuentaPorPagarViewSet(BaseModelViewSet):
    queryset = CuentaPorPagar.objects.all()
    serializer_class = CuentaPorPagarSerializer

    def get_queryset(self):
        qs = CuentaPorPagar.objects.filter(
            id_empresa__in=_empresas(self.request)
        ).select_related("id_empresa", "id_proveedor").prefetch_related("abonos")

        empresa_id = self.request.query_params.get("empresa")
        proveedor_id = self.request.query_params.get("proveedor")
        estado = self.request.query_params.get("estado")

        if empresa_id:
            qs = qs.filter(id_empresa=empresa_id)
        if proveedor_id:
            qs = qs.filter(id_proveedor=proveedor_id)
        if estado:
            qs = qs.filter(estado=estado)

        return qs.order_by("fecha_vencimiento")

    @action(detail=False, methods=["get"], url_path="aging")
    def aging(self, request):
        """
        GET /api/cuentas-por-pagar/cuentas-por-pagar/aging/?empresa=<uuid>

        Devuelve el reporte de antigüedad de saldos CxP por empresa.
        """
        from .services import calcular_aging_cxp

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

        resultado = calcular_aging_cxp(empresa_id)

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
        POST /api/cuentas-por-pagar/cuentas-por-pagar/{pk}/abonar/
        Body: {"monto": "500.00", "descripcion": "Pago a proveedor"}
        """
        from .services import AbonoCxPError, registrar_abono_cxp

        cxp = self.get_object()
        monto_raw = request.data.get("monto")
        if not monto_raw:
            raise ValidationError({"monto": "Este campo es requerido."})

        try:
            monto = Decimal(str(monto_raw))
        except Exception:
            raise ValidationError({"monto": "Monto inválido."})

        descripcion = request.data.get("descripcion", "")

        try:
            abono = registrar_abono_cxp(
                cxp=cxp,
                monto=monto,
                usuario=request.user,
                descripcion=descripcion,
            )
        except AbonoCxPError as exc:
            raise ValidationError(str(exc)) from exc

        cxp.refresh_from_db()
        return Response(
            {
                "abono_id": str(abono.pk),
                "cxp_id": str(cxp.pk),
                "monto_abonado": str(abono.monto),
                "monto_pendiente": str(cxp.monto_pendiente),
                "estado_cxp": cxp.estado,
            },
            status=status.HTTP_201_CREATED,
        )
