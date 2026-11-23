import uuid
from contextvars import ContextVar

from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import Departamento, Dispositivo, Empresa, Permisos, Roles, Sucursal, Usuarios
from .serializer_mixins import TenantFKScopeMixin
from .serializers import (
    DepartamentoSerializer,
    DispositivoSerializer,
    EmpresaSerializer,
    PermisosSerializer,
    RolesSerializer,
    SucursalSerializer,
    UsuariosSerializer,
)


class NulSafeFilterMixin:
    """Rechaza bytes NUL en query params (``?search=``, ``?ordering=``, etc.) con HTTP 400."""

    def filter_queryset(self, queryset):
        request = getattr(self, "request", None)
        if request is not None:
            for key, values in request.query_params.lists():
                if "\x00" in str(key):
                    raise ValidationError({"error": "Parámetro de consulta inválido."})
                for val in values:
                    if isinstance(val, str) and "\x00" in val:
                        raise ValidationError({key: "Parámetro de consulta inválido."})
        return super().filter_queryset(queryset)


def validar_uuid_param(valor: str, campo: str) -> str:
    """Valida que un query param sea un UUID válido (sin NUL); si no, lanza ValidationError (400)."""
    if "\x00" in str(valor):
        raise ValidationError({campo: "Parámetro inválido."})
    limpio = str(valor).strip()
    try:
        return str(uuid.UUID(limpio))
    except (ValueError, TypeError) as exc:
        raise ValidationError({campo: f"'{valor}' no es un UUID válido."}) from exc


def filtrar_ambito_queryset(qs, request):
    """Filtra un queryset por ``?ambito=FISCAL|GERENCIAL`` rechazando NUL o valores inválidos."""
    ambito = request.query_params.get("ambito")
    if ambito is None or ambito == "":
        return qs
    if "\x00" in str(ambito):
        raise ValidationError({"ambito": "Parámetro 'ambito' inválido."})
    val = str(ambito).strip().upper()
    if val not in ("FISCAL", "GERENCIAL"):
        raise ValidationError({"ambito": "El ámbito debe ser 'FISCAL' o 'GERENCIAL'."})
    return qs.filter(ambito=val)


class BaseModelViewSet(TenantFKScopeMixin, viewsets.ModelViewSet):
    """
    ViewSet base para CRUD genérico con paginación, búsqueda y permisos estándar.

    Todos los ViewSets del ERP deben heredar de este en lugar de
    ``viewsets.ModelViewSet`` directamente.

    Funcionalidades incluidas:
    - Autenticación requerida (IsAuthenticated)
    - Paginación con PageNumberPagination
    - Filtros de búsqueda y ordenamiento
    - Campos de búsqueda por defecto para modelos de empresa
    - SEC-M1: FKs writable acotadas a empresas visibles (TenantFKScopeMixin)
    """

    permission_classes = [permissions.IsAuthenticated]
    pagination_class: type[PageNumberPagination] | None = PageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["razon_social", "rif", "telefono", "nombre_comercial"]
    # DRF acepta lista de campos o el literal "__all__"; las subclases sobreescriben con listas.
    ordering_fields: list[str] | str = "__all__"

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
        """
        M-BUG-5 (R-CODE-6): borrado lógico únicamente. Si el modelo no soporta
        soft_delete, NO se hace hard delete silencioso (perdería historial/
        auditoría); se aborta con un error explícito. Este mixin solo debe
        mezclarse en ViewSets cuyos modelos extienden SoftDeleteModel.
        """
        if hasattr(instance, "soft_delete"):
            instance.soft_delete()
        else:
            from rest_framework.exceptions import APIException

            raise APIException(
                f"{instance.__class__.__name__} no soporta borrado lógico; "
                "el hard delete está deshabilitado (R-CODE-6)."
            )

    def _get_object_any_state(self):
        """
        Como get_object() pero sin el filtro activo=True.
        Necesario para /activar/ — el objeto está inactivo y no aparecería
        en el queryset normal filtrado por ActiveFilterMixin.
        """
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


# --- Cache por ciclo de request + distribuido para get_empresas_visible ---
_empresas_visible_cache: ContextVar[dict | None] = ContextVar("omni_empresas_visible_cache", default=None)

CACHE_NS_EMPRESA_TREE = "core.empresa_tree"
CACHE_NS_USER_EMPRESAS = "core.user_empresas"


def iniciar_cache_empresas_visible():
    """Activa la memoización de ``get_empresas_visible`` durante un request."""
    return _empresas_visible_cache.set({})


def limpiar_cache_empresas_visible(token) -> None:
    """Restaura el estado previo del ``ContextVar`` al finalizar el request."""
    _empresas_visible_cache.reset(token)


def invalidar_cache_empresas_visible(user_pk=None, *, invalidate_tree: bool = False) -> None:
    """Invalida la memoización activa y la versión distribuida en ``CACHES``."""
    from .cache_utils import GLOBAL_TENANT_KEY, bump_namespace_version

    l1_cache = _empresas_visible_cache.get()
    if l1_cache is not None:
        l1_cache.clear()

    if invalidate_tree or user_pk is None:
        bump_namespace_version(CACHE_NS_EMPRESA_TREE, GLOBAL_TENANT_KEY)
    if user_pk is not None:
        bump_namespace_version(CACHE_NS_USER_EMPRESAS, f"user:{user_pk}")


def _puede_usar_cache_distribuida_empresas() -> bool:
    """Con RLS activo solo usa caché L2 bajo ``rls_bypass`` para evitar entradas parciales."""
    from django.conf import settings

    if not getattr(settings, "RLS_ENABLED", False):
        return True
    from . import rls

    bypass, _ = rls._get_current_context()
    return bypass == "on"


# --- Visibilidad recursiva (BFS por niveles, O(profundidad) queries) ---
def get_all_subsidiarias_ids(raiz_ids) -> set[uuid.UUID]:
    """Retorna los UUIDs de todas las subsidiarias descendientes vía BFS por niveles."""
    visitados: set[uuid.UUID] = set(raiz_ids)
    frontera: set[uuid.UUID] = set(raiz_ids)
    subsidiarias: set[uuid.UUID] = set()
    while frontera:
        hijas = set(Empresa.objects.filter(empresa_matriz_id__in=frontera).values_list("id_empresa", flat=True))
        nuevas = hijas - visitados
        if not nuevas:
            break
        subsidiarias.update(nuevas)
        visitados.update(nuevas)
        frontera = nuevas
    return subsidiarias


def get_all_subsidiarias(empresa):
    emp_id = getattr(empresa, "id_empresa", None) or getattr(empresa, "pk", empresa)
    if emp_id is None:
        return set()
    return get_all_subsidiarias_ids([emp_id])


def get_empresas_visible(user):
    if getattr(user, "es_superusuario_omni", False):
        return Empresa.objects.all()
    cap_token = getattr(user, "capability_token", None)
    if cap_token is not None:
        return Empresa.objects.filter(id_empresa=cap_token.empresa_id, activo=True)
    if not getattr(user, "is_authenticated", False) or not hasattr(user, "empresas"):
        return Empresa.objects.none()

    l1_cache = _empresas_visible_cache.get()
    user_pk = getattr(user, "pk", None)
    cache_key = ("user", user_pk) if l1_cache is not None and user_pk is not None else None
    if cache_key is not None and cache_key in l1_cache:
        ids_cached = l1_cache[cache_key]
        return Empresa.objects.filter(id_empresa__in=ids_cached) if ids_cached else Empresa.objects.none()

    def _compute_visible_ids() -> tuple[uuid.UUID, ...]:
        directas = tuple(user.empresas.values_list("id_empresa", flat=True))
        if not directas:
            return ()
        ids = set(directas)
        ids.update(get_all_subsidiarias_ids(directas))
        return tuple(ids)

    if user_pk is not None and _puede_usar_cache_distribuida_empresas():
        from .cache_utils import DEFAULT_CACHE_TIMEOUT, GLOBAL_TENANT_KEY, get_cached_or_set, get_namespace_version

        tree_version = get_namespace_version(CACHE_NS_EMPRESA_TREE, GLOBAL_TENANT_KEY)
        ids_tuple = get_cached_or_set(
            CACHE_NS_USER_EMPRESAS,
            f"user:{user_pk}",
            f"visible:tree-{tree_version}",
            _compute_visible_ids,
            timeout=DEFAULT_CACHE_TIMEOUT,
        )
    else:
        ids_tuple = _compute_visible_ids()

    if l1_cache is not None and cache_key is not None:
        l1_cache[cache_key] = ids_tuple
    return Empresa.objects.filter(id_empresa__in=ids_tuple) if ids_tuple else Empresa.objects.none()


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


class SuperuserWriteMixin:
    """
    H-SEC-6: gate de escritura para catálogos GLOBALES (sin id_empresa o con
    filas globales id_empresa=None). Solo un superusuario Omni puede crear,
    modificar o eliminar; cualquier usuario autenticado puede leer.

    Para modelos con id_empresa nullable (p. ej. ParametroSistema), las filas
    de empresa las gestiona el tenant y solo las globales exigen superusuario:
    sobreescribir ``_es_fila_global``.
    """

    def _assert_superuser(self):
        if not getattr(self.request.user, "es_superusuario_omni", False):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Solo un superusuario Omni puede modificar esta configuración global.")

    def _es_fila_global(self, instance_or_data) -> bool:
        return True  # por defecto el modelo entero es global

    def perform_create(self, serializer):
        if self._es_fila_global(serializer.validated_data):
            self._assert_superuser()
        serializer.save()

    def perform_update(self, serializer):
        if self._es_fila_global(serializer.instance):
            self._assert_superuser()
        serializer.save()

    def perform_destroy(self, instance):
        if self._es_fila_global(instance):
            self._assert_superuser()
        instance.delete()


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

    @action(detail=True, methods=["get", "put"], url_path="matriz-acceso")
    def matriz_acceso(self, request, pk=None):
        """Obtiene o reemplaza atómicamente la matriz RBAC/ABAC del rol."""
        from django.core.exceptions import ValidationError as DjangoValidationError

        from .exceptions import domain_error_response
        from .models import PoliticaAccesoRol, RolPermisos
        from .serializers import GuardarMatrizAccesoInputSerializer, PoliticaAccesoRolSerializer
        from .services_rbac import guardar_matriz_rol, obtener_catalogo_rbac

        rol = self.get_object()
        if request.method == "GET":
            empresa = rol.id_empresa or _resolver_empresa_rbac(request.user, request.query_params.get("id_empresa"))
            qs = PoliticaAccesoRol.objects.filter(id_empresa=empresa, id_rol=rol, activo=True).order_by(
                "modulo", "accion"
            )
            permisos_ids = list(RolPermisos.objects.filter(id_rol=rol).values_list("id_permiso_id", flat=True))
            return Response(
                {
                    "id_rol": str(rol.pk),
                    "nombre_rol": rol.nombre_rol,
                    "id_empresa": str(empresa.pk),
                    "politicas": PoliticaAccesoRolSerializer(qs, many=True).data,
                    "permisos_asignados": [str(pid) for pid in permisos_ids],
                    "catalogo": obtener_catalogo_rbac(),
                }
            )

        _assert_admin_rbac(request.user)
        inp = GuardarMatrizAccesoInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        req_emp_id = inp.validated_data.get("id_empresa")
        if rol.id_empresa_id is not None and req_emp_id and str(req_emp_id) != str(rol.id_empresa_id):
            raise ValidationError({"id_empresa": "El rol pertenece a otra empresa."})
        empresa = rol.id_empresa or _resolver_empresa_rbac(request.user, req_emp_id)
        try:
            creadas = guardar_matriz_rol(
                rol,
                empresa,
                inp.validated_data["politicas"],
                usuario=request.user,
                direccion_ip=_ip_cliente_rbac(request),
            )
        except (DjangoValidationError, ValueError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "id_rol": str(rol.pk),
                "id_empresa": str(empresa.pk),
                "politicas": PoliticaAccesoRolSerializer(creadas, many=True).data,
            }
        )

    @action(detail=True, methods=["post"], url_path="aplicar-plantilla")
    def aplicar_plantilla(self, request, pk=None):
        """Aplica una plantilla predefinida (CONTADOR_FISCAL, VENDEDOR, ALMACENISTA, GERENTE_GENERAL)."""
        from django.core.exceptions import ValidationError as DjangoValidationError

        from .exceptions import domain_error_response
        from .serializers import AplicarPlantillaInputSerializer, PoliticaAccesoRolSerializer
        from .services_rbac import aplicar_plantilla_rol

        _assert_admin_rbac(request.user)
        rol = self.get_object()
        inp = AplicarPlantillaInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        req_emp_id = inp.validated_data.get("id_empresa")
        if rol.id_empresa_id is not None and req_emp_id and str(req_emp_id) != str(rol.id_empresa_id):
            raise ValidationError({"id_empresa": "El rol pertenece a otra empresa."})
        empresa = rol.id_empresa or _resolver_empresa_rbac(request.user, req_emp_id)
        try:
            creadas = aplicar_plantilla_rol(
                rol,
                empresa,
                inp.validated_data["codigo_plantilla"],
                usuario=request.user,
                direccion_ip=_ip_cliente_rbac(request),
            )
        except (DjangoValidationError, ValueError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "id_rol": str(rol.pk),
                "id_empresa": str(empresa.pk),
                "codigo_plantilla": inp.validated_data["codigo_plantilla"].strip().upper(),
                "politicas": PoliticaAccesoRolSerializer(creadas, many=True).data,
            }
        )

    @action(detail=True, methods=["post"], url_path="asignar-permisos")
    def asignar_permisos(self, request, pk=None):
        """Sincroniza los permisos globales (`RolPermisos`) asignados al rol."""
        from django.db import transaction

        from .models import RegistroAuditoria, RolPermisos
        from .serializers import AsignarPermisosRolInputSerializer

        _assert_admin_rbac(request.user)
        rol = self.get_object()
        inp = AsignarPermisosRolInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        ids = list(dict.fromkeys(inp.validated_data["permisos_ids"]))
        permisos_qs = list(Permisos.objects.filter(activo=True, id_permiso__in=ids))
        if len(permisos_qs) != len(ids):
            raise ValidationError({"permisos_ids": "Uno o más permisos no existen o están inactivos."})

        empresa = rol.id_empresa or _resolver_empresa_rbac(request.user)
        with transaction.atomic():
            RolPermisos.objects.filter(id_rol=rol).delete()
            if permisos_qs:
                RolPermisos.objects.bulk_create([RolPermisos(id_rol=rol, id_permiso=p) for p in permisos_qs])
            RegistroAuditoria.objects.create(
                id_empresa=empresa,
                id_usuario=request.user,
                tipo_evento="ACTUALIZAR",
                modulo_afectado="core",
                nombre_modelo_afectado="RolPermisos",
                id_registro_afectado=str(rol.pk),
                descripcion_accion=f"Sincronización de permisos del rol '{rol.nombre_rol}' ({len(ids)}).",
                cambios_json={"id_rol": str(rol.pk), "permisos_ids": [str(x) for x in ids]},
                direccion_ip=_ip_cliente_rbac(request),
                resultado_evento="EXITO",
            )
        return Response({"id_rol": str(rol.pk), "permisos_ids": [str(x) for x in ids]})


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

    @action(detail=True, methods=["post"])
    def activar(self, request, pk=None):
        """Reactiva un permiso global del sistema (solo superusuario Omni)."""
        self._assert_superuser()
        return super().activar(request, pk=pk)

    @action(detail=True, methods=["post"])
    def desactivar(self, request, pk=None):
        """Desactiva lógicamente un permiso global del sistema (solo superusuario Omni)."""
        self._assert_superuser()
        return super().desactivar(request, pk=pk)


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
        for flag_fiscal in ("es_agente_retencion_iva", "es_agente_retencion_islr", "exento_islr"):
            val = self.request.query_params.get(flag_fiscal)
            if val is not None:
                qs = qs.filter(**{flag_fiscal: val.lower() in ("true", "1", "yes")})
        tipo_contrib = self.request.query_params.get("tipo_contribuyente")
        if tipo_contrib:
            limpio = str(tipo_contrib).replace("\x00", "").strip().upper()
            qs = qs.filter(tipo_contribuyente=limpio)
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


# ── Access Studio: RBAC / ABAC Granular (Plan 09 Fase 7.1) ─────────────────────


def _assert_admin_rbac(user):
    if not (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or getattr(user, "es_superusuario_omni", False)
    ):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("Solo administradores pueden modificar políticas o permisos de acceso.")


def _resolver_empresa_rbac(user, empresa_id=None):
    empresas = get_empresas_visible(user)
    if empresa_id:
        uid = validar_uuid_param(str(empresa_id), "id_empresa")
        empresa = empresas.filter(pk=uid).first()
        if empresa is None:
            raise ValidationError({"id_empresa": "Empresa no encontrada o sin acceso."})
        return empresa
    empresa = empresas.first()
    if empresa is None:
        raise ValidationError({"id_empresa": "No tiene una empresa activa asignada."})
    return empresa


def _ip_cliente_rbac(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


from .models import PoliticaAccesoRol  # noqa: E402
from .serializers import PoliticaAccesoRolSerializer  # noqa: E402


class PoliticaAccesoRolViewSet(NulSafeFilterMixin, SoftDeleteModelMixin, ActiveFilterMixin, BaseModelViewSet):
    """CRUD y motor de evaluación de políticas granulares RBAC/ABAC por rol y empresa."""

    queryset = PoliticaAccesoRol.objects.all()
    serializer_class = PoliticaAccesoRolSerializer
    ordering_fields = ["modulo", "accion", "fecha_creacion"]
    ordering = ["modulo", "accion"]

    def get_queryset(self):
        qs = super().get_queryset()
        empresas = get_empresas_visible(self.request.user)
        qs = qs.filter(id_empresa__in=empresas)
        id_rol = self.request.query_params.get("id_rol")
        if id_rol:
            qs = qs.filter(id_rol_id=validar_uuid_param(id_rol, "id_rol"))
        modulo = self.request.query_params.get("modulo")
        if modulo:
            if "\x00" in str(modulo):
                raise ValidationError({"modulo": "Parámetro inválido."})
            qs = qs.filter(modulo=str(modulo).strip().lower())
        ambito = self.request.query_params.get("ambito")
        if ambito:
            if "\x00" in str(ambito):
                raise ValidationError({"ambito": "Parámetro inválido."})
            qs = qs.filter(ambito=str(ambito).strip().upper())
        return qs

    def perform_create(self, serializer):
        _assert_admin_rbac(self.request.user)
        serializer.save()

    def perform_update(self, serializer):
        _assert_admin_rbac(self.request.user)
        serializer.save()

    def perform_destroy(self, instance):
        _assert_admin_rbac(self.request.user)
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def activar(self, request, pk=None):
        """Reactiva una política de acceso (solo administradores)."""
        _assert_admin_rbac(request.user)
        return super().activar(request, pk=pk)

    @action(detail=True, methods=["post"])
    def desactivar(self, request, pk=None):
        """Desactiva lógicamente una política de acceso (solo administradores)."""
        _assert_admin_rbac(request.user)
        return super().desactivar(request, pk=pk)

    @action(detail=False, methods=["get"])
    def catalogo(self, request):
        """Devuelve módulos, acciones, ámbitos, alcances, campos sensibles y plantillas RBAC/ABAC."""
        from .services_rbac import obtener_catalogo_rbac

        return Response(obtener_catalogo_rbac())

    @action(detail=False, methods=["get"], url_path="mi-matriz")
    def mi_matriz(self, request):
        """Devuelve la matriz efectiva de acceso del usuario autenticado para su empresa activa."""
        from .services_rbac import obtener_matriz_acceso_usuario

        emp_id = request.query_params.get("id_empresa") or request.query_params.get("empresa")
        empresa = _resolver_empresa_rbac(request.user, emp_id)
        return Response(obtener_matriz_acceso_usuario(request.user, empresa))

    @action(detail=False, methods=["post"])
    def evaluar(self, request):
        """Evalúa acceso efectivo por Módulo × Acción × Ámbito × Alcance."""
        from .exceptions import domain_error_response
        from .serializers import EvaluarAccesoInputSerializer
        from .services_rbac import verificar_acceso

        inp = EvaluarAccesoInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        empresa = _resolver_empresa_rbac(request.user, inp.validated_data.get("id_empresa"))
        try:
            resultado = verificar_acceso(
                request.user,
                empresa,
                inp.validated_data["modulo"],
                inp.validated_data["accion"],
                ambito=inp.validated_data.get("ambito", "AMBOS"),
                alcance_requerido=inp.validated_data.get("alcance_requerido"),
            )
        except ValueError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(resultado)
