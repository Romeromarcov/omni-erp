from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import ConfiguracionFiscalEmpresa, TasaIVAEmpresa
from .serializers import ConfiguracionFiscalEmpresaSerializer, TasaIVAEmpresaSerializer
from .services import calcular_impuestos_pedido


def _empresas(request):
    return get_empresas_visible(request.user)


class ConfiguracionFiscalEmpresaViewSet(BaseModelViewSet):
    queryset = ConfiguracionFiscalEmpresa.objects.all()
    serializer_class = ConfiguracionFiscalEmpresaSerializer

    def get_queryset(self):
        return ConfiguracionFiscalEmpresa.objects.filter(id_empresa__in=_empresas(self.request))


class TasaIVAEmpresaViewSet(BaseModelViewSet):
    queryset = TasaIVAEmpresa.objects.all()
    serializer_class = TasaIVAEmpresaSerializer

    def get_queryset(self):
        return TasaIVAEmpresa.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=False, methods=["post"], url_path="calcular")
    def calcular(self, request):
        """
        POST /api/fiscal/impuestos/calcular/
        Body: {"lineas": [{"subtotal": 100, "tipo_iva": "GENERAL"}], "metodo_pago": "EFECTIVO_BS", "empresa_id": "..."}
        """
        from decimal import Decimal

        lineas = request.data.get("lineas", [])
        metodo_pago = request.data.get("metodo_pago", "EFECTIVO_BS")
        empresa_id = request.data.get("empresa_id")

        empresa = None
        if empresa_id:
            from apps.core.models import Empresa
            try:
                # SEC-B2: el pk de Empresa es id_empresa (no id); con id__in el
                # ORM lanzaba FieldError (500). Se filtra por empresas visibles.
                empresa = Empresa.objects.get(pk=empresa_id, id_empresa__in=_empresas(request))
            except Empresa.DoesNotExist:
                pass

        resultado = calcular_impuestos_pedido(
            [{"subtotal": Decimal(str(l["subtotal"])), "tipo_iva": l.get("tipo_iva", "GENERAL")} for l in lineas],
            metodo_pago=metodo_pago,
            empresa=empresa,
        )
        return Response({k: str(v) if hasattr(v, "quantize") else v for k, v in resultado.items()})
