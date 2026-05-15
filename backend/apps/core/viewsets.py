from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import Departamento, Dispositivo, Empresa, Sucursal, Usuarios
from .serializers import (
    DepartamentoSerializer,
    DispositivoSerializer,
    EmpresaSerializer,
    SucursalSerializer,
    UsuariosSerializer,
)


class BaseModelViewSet(viewsets.ModelViewSet):
    """
    ViewSet base para CRUD genérico con paginación, búsqueda y permisos estándar.

    Todos los ViewSets del ERP deben heredar de este en lugar de
    ``viewsets.ModelViewSet`` directamente.

    Funcionalidades incluidas:
    - Autenticación requerida (IsAuthenticated)
    - Paginación con PageNumberPagination
    - Filtros de búsqueda y ordenamiento
    - Campos de búsqueda por defecto para modelos de empresa
    """

    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["razon_social", "rif", "telefono", "nombre_comercial"]
    ordering_fields = "__all__"


class ActiveFilterMixin:
    """
    Mixin para ViewSets que soporten filtrado por ``activo``.

    Por defecto retorna SOLO registros activos (``activo=True``).
    Para incluir inactivos, pasar ``?incluir_inactivos=true`` en la query.

    Uso:
        class MiViewSet(ActiveFilterMixin, BaseModelViewSet):
            queryset = MiModelo.objects.all()
            serializer_class = MiSerializer

            def get_queryset(self):
                qs = super().get_queryset()   # aplica filtro activo
                return qs.filter(id_empresa__in=_empresas(self.request))

    El método ``get_queryset()`` de este mixin llama a ``super().get_queryset()``
    y aplica el filtro ``activo=True`` a menos que se pase ``?incluir_inactivos=true``.

    Nota: Para que funcione, el modelo subyacente debe tener el campo ``activo``.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        incluir_inactivos = self.request.query_params.get("incluir_inactivos", "false")
        if incluir_inactivos.lower() not in ("true", "1", "yes"):
            qs = qs.filter(activo=True)
        return qs


class SoftDeleteModelMixin:
    """
    Mixin para ViewSets cuyos modelos usen ``SoftDeleteModel``.

    Sobreescribe ``perform_destroy()`` para hacer borrado lógico en lugar de
    físico. Si el modelo no tiene el método ``soft_delete()``, cae back al
    borrado físico estándar de Django.

    Adicionalmente expone dos acciones:
    - ``POST /{pk}/activar/``   — Reactiva un registro inactivo.
    - ``POST /{pk}/desactivar/`` — Desactiva (soft-delete) un registro activo.

    Uso:
        class MiViewSet(SoftDeleteModelMixin, ActiveFilterMixin, BaseModelViewSet):
            queryset = MiModelo.objects.all()
            ...
    """

    def perform_destroy(self, instance):
        """Usa soft_delete() si está disponible; sino borra físicamente."""
        if hasattr(instance, "soft_delete"):
            instance.soft_delete()
        else:
            instance.delete()

    @action(detail=True, methods=["post"], url_path="activar")
    def activar(self, request, pk=None):
        """
        POST /{pk}/activar/
        Reactiva un registro que fue desactivado.
        """
        instance = self.get_object()
        if not hasattr(instance, "restore"):
            return Response(
                {"error": "Este modelo no soporta activación/desactivación."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if getattr(instance, "activo", True):
            return Response(
                {"error": "El registro ya está activo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.restore()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="desactivar")
    def desactivar(self, request, pk=None):
        """
        POST /{pk}/desactivar/
        Desactiva (borrado lógico) un registro activo.
        """
        instance = self.get_object()
        if not hasattr(instance, "soft_delete"):
            return Response(
                {"error": "Este modelo no soporta activación/desactivación."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not getattr(instance, "activo", True):
            return Response(
                {"error": "El registro ya está inactivo."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.soft_delete()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


# --- Visibilidad recursiva ---
def get_all_subsidiarias(empresa):
    ids = set()

    def collect(e):
        for sub in e.subsidiarias.all():
            if sub.id_empresa not in ids:
                ids.add(sub.id_empresa)
                collect(sub)

    collect(empresa)
    return ids


def get_empresas_visible(user):
    if getattr(user, "es_superusuario_omni", False):
        return Empresa.objects.all()
    empresas = user.empresas.all()
    ids = set(empresas.values_list("id_empresa", flat=True))
    for empresa in empresas:
        ids.update(get_all_subsidiarias(empresa))
    return Empresa.objects.filter(id_empresa__in=ids)


class EmpresaViewSet(BaseModelViewSet):
    queryset = Empresa.objects.all()
    serializer_class = EmpresaSerializer

    def get_queryset(self):
        return get_empresas_visible(self.request.user)


def get_all_subsucursales(sucursal):
    ids = set()

    def collect(s):
        for sub in s.subsucursales.all():
            if sub.id_sucursal not in ids:
                ids.add(sub.id_sucursal)
                collect(sub)

    collect(sucursal)
    return ids


def get_sucursales_visible(user):
    if getattr(user, "es_superusuario_omni", False):
        return Sucursal.objects.all()
    sucursales = user.sucursales.all()
    empresas = get_empresas_visible(user)
    ids = set(sucursales.values_list("id_sucursal", flat=True))
    for suc in sucursales:
        ids.update(get_all_subsucursales(suc))
    # Sucursales de empresas visibles (recursivo)
    for empresa in empresas:
        for suc in empresa.sucursales.all():
            ids.add(suc.id_sucursal)
            ids.update(get_all_subsucursales(suc))
    return Sucursal.objects.filter(id_sucursal__in=ids)


class SucursalViewSet(BaseModelViewSet):
    queryset = Sucursal.objects.all()
    serializer_class = SucursalSerializer

    def get_queryset(self):
        return get_sucursales_visible(self.request.user)


def get_all_subdepartamentos(dep):
    ids = set()

    def collect(d):
        for sub in d.subdepartamentos.all():
            if sub.id_departamento not in ids:
                ids.add(sub.id_departamento)
                collect(sub)

    collect(dep)
    return ids


def get_departamentos_visible(user):
    if getattr(user, "es_superusuario_omni", False):
        return Departamento.objects.all()
    empresas = get_empresas_visible(user)
    departamentos = Departamento.objects.filter(id_empresa__in=empresas)
    ids = set(departamentos.values_list("id_departamento", flat=True))
    for dep in departamentos:
        ids.update(get_all_subdepartamentos(dep))
    return Departamento.objects.filter(id_departamento__in=ids)


class DepartamentoViewSet(BaseModelViewSet):
    queryset = Departamento.objects.all()
    serializer_class = DepartamentoSerializer

    def get_queryset(self):
        return get_departamentos_visible(self.request.user)


class UsuariosViewSet(BaseModelViewSet):
    queryset = Usuarios.objects.all()
    serializer_class = UsuariosSerializer

    # Solo superusuarios Innova pueden ver y editar todos los usuarios
    def get_queryset(self):
        user = self.request.user
        if getattr(user, "es_superusuario_omni", False):
            return Usuarios.objects.all()
        # Por defecto, solo puede ver su propio usuario
        return Usuarios.objects.filter(id=user.id)


class DispositivoViewSet(BaseModelViewSet):
    """
    ViewSet para gestión de dispositivos.
    Permite registrar, consultar y gestionar dispositivos asociados a usuarios.
    """

    queryset = Dispositivo.objects.all()
    serializer_class = DispositivoSerializer
    search_fields = ["fingerprint", "nombre_dispositivo", "user_agent", "ip_address"]
    ordering_fields = ["fecha_registro", "ultimo_login", "nombre_dispositivo"]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, "es_superusuario_omni", False):
            # Superusuarios ven todos los dispositivos
            return Dispositivo.objects.all()
        else:
            # Usuarios normales solo ven dispositivos que crearon
            return Dispositivo.objects.filter(creado_por=user)

    def perform_create(self, serializer):
        # Asegurar que el dispositivo se crea para el usuario autenticado
        serializer.save(creado_por=self.request.user)
