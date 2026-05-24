from rest_framework import viewsets

from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import Beneficio, BeneficioEmpleado, Cargo, Empleado, LicenciaEmpleado, TipoLicencia
from .serializers import (
    BeneficioEmpleadoSerializer,
    BeneficioSerializer,
    CargoSerializer,
    EmpleadoSerializer,
    LicenciaEmpleadoSerializer,
    TipoLicenciaSerializer,
)


def _empresas(request):
    return get_empresas_visible(request.user)


class CargoViewSet(BaseModelViewSet):
    queryset = Cargo.objects.all()
    serializer_class = CargoSerializer

    def get_queryset(self):
        # R-CODE-1 — Cargo.empresa puede ser null (cargos globales), incluimos ambos
        empresas = _empresas(self.request)
        return Cargo.objects.filter(empresa__in=empresas) | Cargo.objects.filter(empresa__isnull=True)


class EmpleadoViewSet(BaseModelViewSet):
    queryset = Empleado.objects.all()
    serializer_class = EmpleadoSerializer

    def get_queryset(self):
        # R-CODE-1
        return Empleado.objects.filter(empresa__in=_empresas(self.request))


class BeneficioViewSet(BaseModelViewSet):
    queryset = Beneficio.objects.all()
    serializer_class = BeneficioSerializer

    def get_queryset(self):
        # R-CODE-1
        return Beneficio.objects.filter(id_empresa__in=_empresas(self.request))


class BeneficioEmpleadoViewSet(BaseModelViewSet):
    queryset = BeneficioEmpleado.objects.all()
    serializer_class = BeneficioEmpleadoSerializer

    def get_queryset(self):
        # R-CODE-1 via parent Empleado
        return BeneficioEmpleado.objects.filter(id_empleado__empresa__in=_empresas(self.request))


class TipoLicenciaViewSet(BaseModelViewSet):
    queryset = TipoLicencia.objects.all()
    serializer_class = TipoLicenciaSerializer

    def get_queryset(self):
        # R-CODE-1
        return TipoLicencia.objects.filter(id_empresa__in=_empresas(self.request))


class LicenciaEmpleadoViewSet(BaseModelViewSet):
    queryset = LicenciaEmpleado.objects.all()
    serializer_class = LicenciaEmpleadoSerializer

    def get_queryset(self):
        # R-CODE-1 via parent Empleado
        return LicenciaEmpleado.objects.filter(id_empleado__empresa__in=_empresas(self.request))
