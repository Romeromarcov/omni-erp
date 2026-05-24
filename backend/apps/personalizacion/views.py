from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.viewsets import get_empresas_visible

from .models import PersonalizacionConfig
from .serializers import PersonalizacionConfigSerializer


def _empresas(request):
    return get_empresas_visible(request.user)


class PersonalizacionConfigViewSet(viewsets.ModelViewSet):
    queryset = PersonalizacionConfig.objects.all()
    serializer_class = PersonalizacionConfigSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["activo", "id_empresa"]
    search_fields = ["descripcion"]
    ordering_fields = ["version", "fecha_creacion"]
    ordering = ["-version"]

    def get_queryset(self):
        # R-CODE-1
        return PersonalizacionConfig.objects.filter(id_empresa__in=_empresas(self.request))

    @action(detail=False, methods=["get"])
    def activa(self, request):
        """Obtiene la configuración activa de la empresa del usuario"""
        empresa_id = request.query_params.get("empresa_id")
        filters = {"activo": True}
        if empresa_id:
            filters["id_empresa"] = empresa_id

        config = self.get_queryset().filter(**filters).first()
        if not config:
            return Response({"error": "No hay configuración activa"}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(config)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def activar(self, request, pk=None):
        """Activa esta versión de configuración y desactiva las demás de la misma empresa"""
        config = self.get_object()

        # Desactivar todas las configuraciones anteriores de la misma empresa
        PersonalizacionConfig.objects.filter(
            id_empresa=config.id_empresa, activo=True
        ).exclude(pk=config.pk).update(activo=False)

        config.activo = True
        config.save()

        serializer = self.get_serializer(config)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def historial(self, request):
        """Obtiene el historial de versiones de configuración"""
        empresa_id = request.query_params.get("empresa_id")
        filters = {}
        if empresa_id:
            filters["id_empresa"] = empresa_id

        configs = self.get_queryset().filter(**filters).order_by("-version")
        serializer = self.get_serializer(configs, many=True)
        return Response(serializer.data)
