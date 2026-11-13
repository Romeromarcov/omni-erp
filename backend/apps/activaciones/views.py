from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.core.viewsets import (
    BaseModelViewSet,
    EmpresaInjectMixin,
    get_empresa_primaria,
    get_empresas_visible,
)
from apps.core.permissions import IsAdminOrReadOnly
from apps.crm.models import Cliente

from . import services
from .models import CalendarioActivacion, EventoActivacion, RecursoActivacion
from .serializers import (
    CalendarioActivacionSerializer,
    EventoActivacionSerializer,
    EventoCrearSerializer,
    RecursoActivacionSerializer,
)


class _TenantViewSet(EmpresaInjectMixin, BaseModelViewSet):
    model = None
    search_fields: list[str] = []

    def get_queryset(self):
        return self.model.objects.filter(
            id_empresa__in=get_empresas_visible(self.request.user), activo=True
        )

    def perform_destroy(self, instance):
        instance.soft_delete()


class CalendarioActivacionViewSet(_TenantViewSet):
    # Configuración: cualquier usuario autenticado lee; solo staff escribe.
    permission_classes = [IsAdminOrReadOnly]
    model = CalendarioActivacion
    serializer_class = CalendarioActivacionSerializer
    search_fields = ["nombre"]

    @action(detail=True, methods=["get"], url_path="disponibilidad")
    def disponibilidad(self, request, pk=None):
        """GET …/calendarios/{id}/disponibilidad/?inicio=ISO&fin=ISO → capacidad y libres por recurso."""
        cal = self.get_object()
        inicio = parse_datetime(request.query_params.get("inicio", ""))
        fin = parse_datetime(request.query_params.get("fin", ""))
        if not inicio or not fin or fin <= inicio:
            return Response(
                {"error": "Indica inicio y fin válidos (ISO 8601), con fin > inicio."},
                status=400,
            )
        return Response(
            [
                {
                    "codigo": d.codigo,
                    "nombre": d.nombre,
                    "capacidad": d.capacidad,
                    "usado": d.pico_usado,
                    "libres": d.libres,
                }
                for d in services.disponibilidad(cal, inicio, fin)
            ]
        )


class RecursoActivacionViewSet(_TenantViewSet):
    permission_classes = [IsAdminOrReadOnly]
    model = RecursoActivacion
    serializer_class = RecursoActivacionSerializer
    search_fields = ["codigo", "nombre"]

    def perform_create(self, serializer):
        cal = serializer.validated_data["calendario"]
        if (
            not get_empresas_visible(self.request.user)
            .filter(pk=cal.id_empresa_id)
            .exists()
        ):
            raise PermissionDenied("Calendario fuera de tus empresas.")
        serializer.save(id_empresa=cal.id_empresa)


class EventoActivacionViewSet(_TenantViewSet):
    model = EventoActivacion
    serializer_class = EventoActivacionSerializer
    http_method_names = ["get", "post", "head", "options"]
    search_fields = ["cliente_nombre", "vendedor_nombre", "ubicacion"]

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("calendario")
            .prefetch_related("usos__recurso")
        )
        p = self.request.query_params
        if p.get("estado"):
            qs = qs.filter(estado=p["estado"])
        if p.get("desde"):
            qs = qs.filter(fin__gte=p["desde"])
        if p.get("hasta"):
            qs = qs.filter(inicio__lte=p["hasta"])
        return qs

    def create(self, request, *args, **kwargs):
        ser = EventoCrearSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        empresa = get_empresa_primaria(request.user)
        if empresa is None:
            raise PermissionDenied("El usuario no tiene empresa asignada.")
        try:
            if d.get("calendario"):
                cal = CalendarioActivacion.objects.get(
                    pk=d["calendario"], id_empresa=empresa, activo=True
                )
            else:
                cal = services.calendario_predeterminado(empresa)
        except CalendarioActivacion.DoesNotExist:
            return Response({"error": "Calendario no encontrado."}, status=404)
        except services.ActivacionError as e:
            return Response({"error": str(e)}, status=400)
        cliente = (
            Cliente.objects.filter(pk=d["cliente"], id_empresa=empresa).first()
            if d.get("cliente")
            else None
        )
        try:
            evento = services.crear_evento(
                empresa=empresa,
                calendario=cal,
                cliente=cliente,
                cliente_nombre=d["cliente_nombre"],
                vendedor=request.user,
                vendedor_nombre=d["vendedor_nombre"] or request.user.get_full_name(),
                ubicacion=d["ubicacion"],
                inicio=d["inicio"],
                fin=d["fin"],
                usos=d["usos"],
                materiales=d["materiales"],
                notas=d["notas"],
            )
        except services.CapacidadExcedida as e:
            return Response(
                {"error": str(e), "detalle": e.detalle}, status=status.HTTP_409_CONFLICT
            )
        except services.ActivacionError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            EventoActivacionSerializer(evento).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"], url_path="cancelar")
    def cancelar(self, request, pk=None):
        try:
            evento = services.cancelar_evento(self.get_object())
        except services.ActivacionError as e:
            return Response({"error": str(e)}, status=400)
        return Response(EventoActivacionSerializer(evento).data)
