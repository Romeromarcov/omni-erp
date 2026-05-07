from rest_framework import viewsets
from .models import Empleado, Cargo, Beneficio, BeneficioEmpleado, TipoLicencia, LicenciaEmpleado
from .serializers import (
    EmpleadoSerializer, CargoSerializer, BeneficioSerializer,
    BeneficioEmpleadoSerializer, TipoLicenciaSerializer, LicenciaEmpleadoSerializer
)
from apps.core.viewsets import BaseModelViewSet

class CargoViewSet(BaseModelViewSet):
    queryset = Cargo.objects.all()
    serializer_class = CargoSerializer

class EmpleadoViewSet(BaseModelViewSet):
    queryset = Empleado.objects.all()
    serializer_class = EmpleadoSerializer

class BeneficioViewSet(BaseModelViewSet):
    queryset = Beneficio.objects.all()
    serializer_class = BeneficioSerializer

class BeneficioEmpleadoViewSet(BaseModelViewSet):
    queryset = BeneficioEmpleado.objects.all()
    serializer_class = BeneficioEmpleadoSerializer

class TipoLicenciaViewSet(BaseModelViewSet):
    queryset = TipoLicencia.objects.all()
    serializer_class = TipoLicenciaSerializer

class LicenciaEmpleadoViewSet(BaseModelViewSet):
    queryset = LicenciaEmpleado.objects.all()
    serializer_class = LicenciaEmpleadoSerializer
