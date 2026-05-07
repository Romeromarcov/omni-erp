from rest_framework import viewsets, permissions, filters
from rest_framework.pagination import PageNumberPagination
from .models import Empresa, Sucursal, Departamento, Usuarios, Dispositivo
from .serializers import EmpresaSerializer, SucursalSerializer, DepartamentoSerializer, UsuariosSerializer, DispositivoSerializer

class BaseModelViewSet(viewsets.ModelViewSet):
    """ViewSet base para CRUD genérico con paginación, búsqueda y permisos estándar."""
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    # Campos permitidos para búsqueda en modelos comunes (ajusta según tus modelos)
    search_fields = ['razon_social', 'rif', 'telefono', 'nombre_comercial']
    ordering_fields = '__all__'


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
    if getattr(user, 'es_superusuario_omni', False):
        return Empresa.objects.all()
    empresas = user.empresas.all()
    ids = set(empresas.values_list('id_empresa', flat=True))
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
    if getattr(user, 'es_superusuario_omni', False):
        return Sucursal.objects.all()
    sucursales = user.sucursales.all()
    empresas = get_empresas_visible(user)
    ids = set(sucursales.values_list('id_sucursal', flat=True))
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
    if getattr(user, 'es_superusuario_omni', False):
        return Departamento.objects.all()
    empresas = get_empresas_visible(user)
    departamentos = Departamento.objects.filter(id_empresa__in=empresas)
    ids = set(departamentos.values_list('id_departamento', flat=True))
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
        if getattr(user, 'es_superusuario_omni', False):
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
    search_fields = ['fingerprint', 'nombre_dispositivo', 'user_agent', 'ip_address']
    ordering_fields = ['fecha_registro', 'ultimo_login', 'nombre_dispositivo']

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'es_superusuario_omni', False):
            # Superusuarios ven todos los dispositivos
            return Dispositivo.objects.all()
        else:
            # Usuarios normales solo ven dispositivos que crearon
            return Dispositivo.objects.filter(creado_por=user)

    def perform_create(self, serializer):
        # Asegurar que el dispositivo se crea para el usuario autenticado
        serializer.save(creado_por=self.request.user)
