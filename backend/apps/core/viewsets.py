from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import Departamento, Dispositivo, Empresa, Permisos, Roles, Sucursal, Usuarios
from .serializers import (
    DepartamentoSerializer,
    DispositivoSerializer,
    EmpresaSerializer,
    PermisosSerializer,
    RolesSerializer,
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

    def paginate_queryset(self, queryset):
        # NEW-PAG-1: garantizar un orden determinístico antes de paginar.
        # Solo aplica si el queryset no trae ya un ordering (Meta.ordering u
        # order_by explícito), para no pisar ordenamientos intencionales.
        # uuid7/auto-id son cronológicos, así que ordenar por pk es estable.
        if queryset.ordered is False:
            queryset = queryset.order_by("pk")
        return super().paginate_queryset(queryset)


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

    def _get_object_any_state(self):
        """
        Como get_object() pero sin el filtro activo=True.
        Necesario para /activar/ — el objeto está inactivo y no aparecería
        en el queryset normal filtrado por ActiveFilterMixin.
        """
        # Obtiene el queryset sin filtro de activo (incluye inactivos)
        queryset = self.filter_queryset(
            self.get_queryset().model.objects.all()
            if hasattr(self.get_queryset(), "model")
            else self.get_queryset()
        )
        # Si el ViewSet tiene get_queryset con filtros de empresa, los aplicamos
        # usando el queryset base del modelo pero con los filtros de empresa del ViewSet
        # Para lograr esto correctamente, sobreescribimos sólo el filtro de activo:
        base_qs = super().get_queryset() if hasattr(super(), "get_queryset") else queryset  # type: ignore[misc]
        # Llamamos directamente al get_queryset del ViewSet padre para mantener
        # los filtros de empresa, pero quitamos el filtro de activo
        qs_sin_activo = self.get_queryset().model.objects.all()

        # Re-aplicar los filtros propios del ViewSet (empresa, etc.) sin pasar por ActiveFilterMixin
        # La forma más limpia: obtener el queryset sin filtro de activo
        # tomando los filtros de empresa del ViewSet heredado.
        filter_kwargs = {self.lookup_field: self.kwargs[self.lookup_field]}
        obj = None

        # Intentar obtener el objeto en el queryset ya filtrado (activos)
        qs = self.get_queryset()
        try:
            obj = qs.get(**filter_kwargs)
        except qs.model.DoesNotExist:
            pass

        if obj is None:
            # No está en activos — buscar en inactivos con los mismos filtros de empresa.
            # Usamos una copia mutable del GET dict para no mutar el QueryDict original
            # (que es inmutable y causaría AttributeError en producción).
            from django.http import QueryDict  # noqa: PLC0415

            original_get = self.request._request.GET
            mutable_get = original_get.copy()  # copy() retorna un QueryDict mutable
            mutable_get["incluir_inactivos"] = "true"
            self.request._request.GET = mutable_get
            try:
                qs_full = self.get_queryset()
                obj = qs_full.filter(activo=False).filter(**filter_kwargs).first()
            finally:
                self.request._request.GET = original_get  # siempre restaurar

        if obj is None:
            from rest_framework.exceptions import NotFound  # noqa: PLC0415

            raise NotFound()

        self.check_object_permissions(self.request, obj)
        return obj

    @action(detail=True, methods=["post"], url_path="activar")
    def activar(self, request, pk=None):
        """
        POST /{pk}/activar/
        Reactiva un registro que fue desactivado.
        Busca el objeto incluyendo inactivos (necesario para reactivar).
        """
        instance = self._get_object_any_state()
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


def get_empresa_primaria(user):
    """Empresa por defecto del usuario para inyección en creaciones."""
    return get_empresas_visible(user).first()


class EmpresaInjectMixin:
    """
    H-API-1/H-API-2: inyecta la empresa del usuario autenticado al crear, en
    vez de confiar en el ``id_empresa`` del payload (que permitiría crear
    registros en otra empresa). El serializer debe declarar ``id_empresa`` como
    read_only para que el valor del cliente se ignore por completo.

    ``empresa_field`` permite ajustar el nombre del campo FK a empresa.
    """

    empresa_field = "id_empresa"

    def perform_create(self, serializer):
        empresa = get_empresa_primaria(self.request.user)
        if empresa is None:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("El usuario no tiene empresa asignada.")
        serializer.save(**{self.empresa_field: empresa})


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


class RolesViewSet(SoftDeleteModelMixin, ActiveFilterMixin, BaseModelViewSet):
    """
    ViewSet para gestión de Roles.

    Endpoints:
      GET    /api/core/roles/               — listar roles activos (R-CODE-1)
      POST   /api/core/roles/               — crear rol
      GET    /api/core/roles/{pk}/          — detalle
      PATCH  /api/core/roles/{pk}/          — actualizar
      DELETE /api/core/roles/{pk}/          — soft-delete (activo=False)
      POST   /api/core/roles/{pk}/activar/  — reactivar
      POST   /api/core/roles/{pk}/desactivar/ — desactivar
    """

    queryset = Roles.objects.all()
    serializer_class = RolesSerializer
    search_fields = ["nombre_rol", "descripcion"]
    ordering_fields = ["nombre_rol", "fecha_creacion"]
    ordering = ["nombre_rol"]

    def get_queryset(self):
        qs = super().get_queryset()  # aplica filtro activo=True de ActiveFilterMixin
        empresas = get_empresas_visible(self.request.user)
        return qs.filter(id_empresa__in=empresas)


class PermisosViewSet(SoftDeleteModelMixin, ActiveFilterMixin, BaseModelViewSet):
    """
    ViewSet para gestión de Permisos del sistema.

    Los permisos son globales (no por empresa), por lo que solo
    superusuarios Omni deben poder crearlos o eliminarlos.
    """

    queryset = Permisos.objects.all()
    serializer_class = PermisosSerializer
    search_fields = ["codigo_permiso", "nombre_permiso", "modulo"]
    ordering_fields = ["codigo_permiso", "modulo", "fecha_creacion"]
    ordering = ["modulo", "codigo_permiso"]

    def get_queryset(self):
        return super().get_queryset()  # solo filtro activo, no por empresa

    # H-SEC-7: los permisos son un catálogo global. Solo un superusuario Omni
    # puede crearlos, modificarlos o eliminarlos.
    def _assert_superuser(self):
        if not getattr(self.request.user, "es_superusuario_omni", False):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Solo un superusuario Omni puede modificar permisos globales.")

    def perform_create(self, serializer):
        self._assert_superuser()
        serializer.save()

    def perform_update(self, serializer):
        self._assert_superuser()
        serializer.save()

    def perform_destroy(self, instance):
        self._assert_superuser()
        super().perform_destroy(instance)


# ── ConfiguracionFlujoDocumentosViewSet ───────────────────────────────────────

from .models import ConfiguracionFlujoDocumentos, Contacto, Notificacion  # noqa: E402
from .serializers import (  # noqa: E402
    ConfiguracionFlujoDocumentosSerializer,
    ContactoSerializer,
    NotificacionSerializer,
)


class ConfiguracionFlujoDocumentosViewSet(ActiveFilterMixin, BaseModelViewSet):
    """
    CRUD de la configuración de flujo de documentos por empresa.

    Filtros disponibles:
      - ?tipo_documento=VENTAS|COMPRAS
      - ?empresa=<uuid>

    Cada empresa tiene hasta 8 registros (4 pasos ventas + 4 pasos compras).
    Si no existe un registro para un paso, la lógica de negocio asume 'obligatorio=True'.
    """

    queryset = ConfiguracionFlujoDocumentos.objects.select_related("id_empresa").order_by("tipo_documento", "orden")
    serializer_class = ConfiguracionFlujoDocumentosSerializer
    search_fields = []
    ordering_fields = ["tipo_documento", "paso", "orden"]

    def get_queryset(self):
        empresas = get_empresas_visible(self.request.user)
        qs = super().get_queryset().filter(id_empresa__in=empresas)
        tipo = self.request.query_params.get("tipo_documento")
        if tipo:
            qs = qs.filter(tipo_documento=tipo)
        return qs

    def perform_create(self, serializer):
        empresa = get_empresas_visible(self.request.user).first()
        if not empresa:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("El usuario no tiene empresa asignada.")
        serializer.save(id_empresa=empresa)


# ── ContactoViewSet ───────────────────────────────────────────────────────────


class ContactoViewSet(ActiveFilterMixin, BaseModelViewSet):
    """
    CRUD de Contactos unificados.
    Filtros disponibles: ?es_cliente=true, ?es_proveedor=true, ?es_empleado=true
    Búsqueda: ?search=<rif|nombre|email>
    """

    queryset = Contacto.objects.select_related("id_empresa", "lista_precio", "usuario").order_by("nombre")
    serializer_class = ContactoSerializer
    search_fields = ["nombre", "apellido", "nombre_comercial", "rif", "cedula", "email"]
    ordering_fields = ["nombre", "rif", "fecha_creacion"]

    def get_queryset(self):
        empresas = get_empresas_visible(self.request.user)
        qs = super().get_queryset().filter(id_empresa__in=empresas)
        for rol in ("es_cliente", "es_proveedor", "es_empleado", "es_usuario"):
            val = self.request.query_params.get(rol)
            if val is not None:
                qs = qs.filter(**{rol: val.lower() in ("true", "1", "yes")})
        return qs

    def perform_create(self, serializer):
        empresa = get_empresas_visible(self.request.user).first()
        if not empresa:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("El usuario no tiene empresa asignada.")
        serializer.save(id_empresa=empresa)


# ── NotificacionViewSet ───────────────────────────────────────────────────────


class NotificacionViewSet(BaseModelViewSet):
    """
    CRUD de Notificaciones in-app.

    Filtra por empresa y usuario del autenticado.
    Incluye acciones: marcar_leida, marcar_todas_leidas, no_leidas.
    """

    queryset = Notificacion.objects.all()
    serializer_class = NotificacionSerializer
    filterset_fields = ["leida", "tipo", "id_empresa", "id_usuario"]
    search_fields = ["titulo", "mensaje"]
    ordering_fields = ["fecha_creacion", "leida"]
    ordering = ["-fecha_creacion"]

    def get_queryset(self):
        # R-CODE-1: filtrar por empresa y usuario (o broadcast id_usuario=None)
        from django.db import models as django_models

        empresas = get_empresas_visible(self.request.user)
        usuario = self.request.user
        return Notificacion.objects.filter(id_empresa__in=empresas).filter(
            django_models.Q(id_usuario=usuario) | django_models.Q(id_usuario__isnull=True)
        )

    @action(detail=True, methods=["post"])
    def marcar_leida(self, request, pk=None):
        """Marca una notificación como leída."""
        notificacion = self.get_object()
        notificacion.marcar_leida()  # usa el método del modelo que actualiza fecha_lectura
        serializer = self.get_serializer(notificacion)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def marcar_todas_leidas(self, request):
        """Marca todas las notificaciones no leídas del usuario como leídas."""
        count = self.get_queryset().filter(leida=False).update(leida=True)
        return Response({"marcadas_leidas": count})

    @action(detail=False, methods=["get"])
    def no_leidas(self, request):
        """Obtiene conteo y listado de notificaciones no leídas."""
        qs = self.get_queryset().filter(leida=False)
        serializer = self.get_serializer(qs, many=True)
        return Response({"count": qs.count(), "notificaciones": serializer.data})
