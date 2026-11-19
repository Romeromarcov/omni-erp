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

    def _assert_no_global_mutation(self, empresa_id):
        if empresa_id is None and not getattr(self.request.user, "es_superusuario_omni", False):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Solo un superusuario Omni puede modificar cargos globales.")

    def check_object_permissions(self, request, obj):
        from rest_framework.permissions import SAFE_METHODS

        super().check_object_permissions(request, obj)
        if request.method not in SAFE_METHODS:
            self._assert_no_global_mutation(obj.empresa_id)

    def perform_create(self, serializer):
        empresa = serializer.validated_data.get("empresa")
        self._assert_no_global_mutation(getattr(empresa, "pk", empresa))
        super().perform_create(serializer)

    def perform_update(self, serializer):
        self._assert_no_global_mutation(serializer.instance.empresa_id)
        if "empresa" in serializer.validated_data:
            empresa = serializer.validated_data.get("empresa")
            self._assert_no_global_mutation(getattr(empresa, "pk", empresa))
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._assert_no_global_mutation(instance.empresa_id)
        super().perform_destroy(instance)


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
