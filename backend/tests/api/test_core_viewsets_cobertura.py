"""
Backfill de cobertura — apps/core/viewsets.py y apps/core/serializers.py.

ViewSets (montados en /api/core/):
- ``get_empresas_visible`` / ``get_sucursales_visible`` / ``get_departamentos_visible``:
  recursión por subsidiarias/subsucursales/subdepartamentos y bypass de superusuario.
- ``BaseModelViewSet.paginate_queryset``: orden determinístico por pk cuando el
  queryset llega sin ordering (NEW-PAG-1).
- ``ActiveFilterMixin``: filtro activo=True por defecto + ``?incluir_inactivos=true``.
- ``SoftDeleteModelMixin`` vía RolesViewSet: DELETE = soft-delete (R-CODE-6),
  /activar/ y /desactivar/ con sus ramas de error.
- ``UsuariosViewSet`` / ``DispositivoViewSet``: visibilidad por usuario y
  ``perform_create`` que fuerza ``creado_por``.
- ``PermisosViewSet``: gate de superusuario para escritura (H-SEC-7).
- ``ContactoViewSet`` / ``ConfiguracionFlujoDocumentosViewSet``: filtros e
  inyección de empresa (y 403 sin empresa).
- ``NotificacionViewSet``: aislamiento + broadcast + acciones marcar_leida,
  marcar_todas_leidas y no_leidas.

Serializers:
- ``EmpresaSerializer.validate`` (moneda país no coincide / no existe).
- ``SucursalSerializer.create`` (resolución del UUID anidado de empresa).
- ``UsuariosSerializer``: get_roles y gates de ``es_superusuario_omni`` en
  create/update.
- ``DispositivoSerializer.create`` fuerza ``creado_por`` del request.
"""
import uuid
from types import SimpleNamespace

import pytest
from rest_framework import serializers as drf_serializers
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.request import Request

from apps.core.models import (
    ConfiguracionFlujoDocumentos,
    Contacto,
    Departamento,
    Dispositivo,
    Empresa,
    Notificacion,
    Permisos,
    Roles,
    Sucursal,
    UsuarioRoles,
    crear_notificacion,
)
from apps.core.serializers import (
    DispositivoSerializer,
    EmpresaSerializer,
    SucursalSerializer,
    UsuariosSerializer,
)
from apps.core.viewsets import (
    EmpresaViewSet,
    get_departamentos_visible,
    get_empresa_primaria,
    get_empresas_visible,
    get_sucursales_visible,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def superuser(db, empresa_a):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(
        username="super_omni", password="testpass123", is_active=True
    )
    user.es_superusuario_omni = True
    user.save(update_fields=["es_superusuario_omni"])
    return user


@pytest.fixture
def client_super(superuser):
    c = APIClient()
    c.force_authenticate(user=superuser)
    return c


@pytest.fixture
def sucursal_a(empresa_a):
    return Sucursal.objects.create(
        id_empresa=empresa_a, nombre="Matriz", codigo_sucursal="VS-A1"
    )


# ── Visibilidad recursiva ─────────────────────────────────────────────────────


class TestVisibilidad:
    def test_empresas_visible_incluye_subsidiarias_recursivas(self, user_a, empresa_a, moneda_usd):
        hija = Empresa.objects.create(
            nombre_legal="Hija", empresa_matriz=empresa_a, id_moneda_base=moneda_usd
        )
        nieta = Empresa.objects.create(
            nombre_legal="Nieta", empresa_matriz=hija, id_moneda_base=moneda_usd
        )
        ajena = Empresa.objects.create(nombre_legal="Ajena", id_moneda_base=moneda_usd)
        visibles = set(get_empresas_visible(user_a).values_list("nombre_legal", flat=True))
        assert visibles == {"Empresa Alpha S.A.", "Hija", "Nieta"}
        assert ajena.nombre_legal not in visibles
        assert get_empresa_primaria(user_a) is not None

    def test_empresas_visible_superusuario_ve_todas(self, superuser, empresa_a, empresa_b):
        assert get_empresas_visible(superuser).count() == Empresa.objects.count()

    def test_sucursales_visible_recursivo_y_por_empresa(self, user_a, empresa_a, empresa_b, sucursal_a):
        sub = Sucursal.objects.create(
            id_empresa=empresa_a, nombre="Sub", codigo_sucursal="VS-A2", sucursal_matriz=sucursal_a
        )
        ajena = Sucursal.objects.create(id_empresa=empresa_b, nombre="Ajena", codigo_sucursal="VS-B1")
        user_a.sucursales.add(sucursal_a)
        visibles = set(get_sucursales_visible(user_a).values_list("nombre", flat=True))
        assert visibles == {"Matriz", "Sub"}
        assert ajena.nombre not in visibles

    def test_sucursales_visible_superusuario(self, superuser, sucursal_a):
        assert get_sucursales_visible(superuser).count() == Sucursal.objects.count()

    def test_departamentos_visible_recursivo(self, user_a, empresa_a, empresa_b):
        padre = Departamento.objects.create(id_empresa=empresa_a, nombre_departamento="Dirección")
        hijo = Departamento.objects.create(
            id_empresa=empresa_a, nombre_departamento="Ventas", departamento_general=padre
        )
        Departamento.objects.create(id_empresa=empresa_b, nombre_departamento="Ajeno")
        visibles = set(get_departamentos_visible(user_a).values_list("nombre_departamento", flat=True))
        assert visibles == {"Dirección", "Ventas"}

    def test_departamentos_visible_superusuario(self, superuser, empresa_a):
        Departamento.objects.create(id_empresa=empresa_a, nombre_departamento="D1")
        assert get_departamentos_visible(superuser).count() == Departamento.objects.count()


# ── Endpoints de listado (get_queryset de Empresa/Sucursal/Departamento) ─────


class TestListadosBasicos:
    def test_list_empresas_solo_visibles(self, client_a, empresa_a, empresa_b):
        resp = client_a.get("/api/core/empresas/")
        assert resp.status_code == 200
        nombres = [e["nombre_legal"] for e in resp.json()["results"]]
        assert nombres == ["Empresa Alpha S.A."]

    def test_list_sucursales_de_empresas_visibles(self, client_a, sucursal_a, empresa_b):
        Sucursal.objects.create(id_empresa=empresa_b, nombre="Ajena", codigo_sucursal="VS-B7")
        resp = client_a.get("/api/core/sucursales/")
        assert resp.status_code == 200
        nombres = [s["nombre"] for s in resp.json()["results"]]
        assert nombres == ["Matriz"]

    def test_list_departamentos_de_empresas_visibles(self, client_a, empresa_a, empresa_b):
        Departamento.objects.create(id_empresa=empresa_a, nombre_departamento="Propio")
        Departamento.objects.create(id_empresa=empresa_b, nombre_departamento="Ajeno")
        resp = client_a.get("/api/core/departamentos/")
        assert resp.status_code == 200
        nombres = [d["nombre_departamento"] for d in resp.json()["results"]]
        assert nombres == ["Propio"]


# ── Mixins (ramas no alcanzables vía URLs registradas) ────────────────────────


class TestMixinsUnitarios:
    def test_perform_destroy_sin_soft_delete_aborta(self):
        """M-BUG-5: sin soft_delete NO hay hard delete silencioso (R-CODE-6)."""
        from rest_framework.exceptions import APIException

        from apps.core.viewsets import SoftDeleteModelMixin

        mixin = SoftDeleteModelMixin()
        with pytest.raises(APIException, match="no soporta borrado lógico"):
            mixin.perform_destroy(object())

    def test_activar_modelo_sin_restore_400(self):
        from apps.core.viewsets import RolesViewSet

        v = RolesViewSet()
        v._get_object_any_state = lambda: SimpleNamespace(activo=False)  # sin restore()
        resp = v.activar(request=None)
        assert resp.status_code == 400
        assert resp.data["error"] == "Este modelo no soporta activación/desactivación."

    def test_desactivar_modelo_sin_soft_delete_400(self):
        from apps.core.viewsets import RolesViewSet

        v = RolesViewSet()
        v.get_object = lambda: SimpleNamespace(activo=True)  # sin soft_delete()
        resp = v.desactivar(request=None)
        assert resp.status_code == 400
        assert resp.data["error"] == "Este modelo no soporta activación/desactivación."

    def test_desactivar_ya_inactivo_400(self):
        from apps.core.viewsets import RolesViewSet

        v = RolesViewSet()
        v.get_object = lambda: SimpleNamespace(activo=False, soft_delete=lambda: None)
        resp = v.desactivar(request=None)
        assert resp.status_code == 400
        assert resp.data["error"] == "El registro ya está inactivo."

    def test_empresa_inject_mixin_inyecta_empresa(self, user_a, empresa_a):
        from unittest.mock import MagicMock

        from apps.core.viewsets import EmpresaInjectMixin

        m = EmpresaInjectMixin()
        m.request = SimpleNamespace(user=user_a)
        serializer = MagicMock()
        m.perform_create(serializer)
        serializer.save.assert_called_once_with(id_empresa=empresa_a)

    def test_empresa_inject_mixin_sin_empresa_denegado(self, db):
        from unittest.mock import MagicMock

        from django.contrib.auth import get_user_model
        from rest_framework.exceptions import PermissionDenied

        from apps.core.viewsets import EmpresaInjectMixin

        huerfano = get_user_model().objects.create_user(username="inject_huerfano", password="x")
        m = EmpresaInjectMixin()
        m.request = SimpleNamespace(user=huerfano)
        with pytest.raises(PermissionDenied, match="no tiene empresa asignada"):
            m.perform_create(MagicMock())

    def test_superuser_write_mixin_bloquea_usuario_normal(self, user_a):
        from unittest.mock import MagicMock

        from rest_framework.exceptions import PermissionDenied

        from apps.core.viewsets import SuperuserWriteMixin

        m = SuperuserWriteMixin()
        m.request = SimpleNamespace(user=user_a)
        serializer = MagicMock()
        with pytest.raises(PermissionDenied):
            m.perform_create(serializer)
        with pytest.raises(PermissionDenied):
            m.perform_update(serializer)
        with pytest.raises(PermissionDenied):
            m.perform_destroy(MagicMock())
        serializer.save.assert_not_called()

    def test_superuser_write_mixin_permite_superusuario(self, superuser):
        from unittest.mock import MagicMock

        from apps.core.viewsets import SuperuserWriteMixin

        m = SuperuserWriteMixin()
        m.request = SimpleNamespace(user=superuser)
        serializer = MagicMock()
        m.perform_create(serializer)
        m.perform_update(serializer)
        assert serializer.save.call_count == 2
        instancia = MagicMock()
        m.perform_destroy(instancia)
        instancia.delete.assert_called_once()


# ── BaseModelViewSet.paginate_queryset ────────────────────────────────────────


class TestPaginacionDeterministica:
    def _viewset(self, user):
        v = EmpresaViewSet()
        req = Request(APIRequestFactory().get("/api/core/empresas/"))
        req.user = user
        v.request = req
        v.format_kwarg = None
        v.kwargs = {}
        return v

    def test_queryset_sin_orden_se_ordena_por_pk(self, user_a, empresa_a, empresa_b):
        v = self._viewset(user_a)
        qs = Empresa.objects.all().order_by()  # quita el Meta.ordering
        assert qs.ordered is False
        page = v.paginate_queryset(qs)
        assert page is not None
        assert [e.pk for e in page] == sorted(e.pk for e in page)

    def test_queryset_ordenado_se_respeta(self, user_a, empresa_a, empresa_b):
        v = self._viewset(user_a)
        qs = Empresa.objects.all().order_by("-nombre_legal")
        page = v.paginate_queryset(qs)
        nombres = [e.nombre_legal for e in page]
        assert nombres == sorted(nombres, reverse=True)


# ── RolesViewSet: ActiveFilterMixin + SoftDeleteModelMixin ────────────────────


class TestRolesSoftDelete:
    @pytest.fixture
    def rol(self, empresa_a):
        return Roles.objects.create(id_empresa=empresa_a, nombre_rol="Cajero")

    def test_lista_excluye_inactivos_por_defecto(self, client_a, empresa_a, rol):
        inactivo = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Viejo", activo=False)
        resp = client_a.get("/api/core/roles/")
        assert resp.status_code == 200
        nombres = [r["nombre_rol"] for r in resp.json()["results"]]
        assert nombres == ["Cajero"]
        resp2 = client_a.get("/api/core/roles/?incluir_inactivos=true")
        nombres2 = {r["nombre_rol"] for r in resp2.json()["results"]}
        assert nombres2 == {"Cajero", "Viejo"}

    def test_delete_es_soft_delete(self, client_a, rol):
        resp = client_a.delete(f"/api/core/roles/{rol.id_rol}/")
        assert resp.status_code == 204
        rol.refresh_from_db()  # NO se borró físicamente (R-CODE-6)
        assert rol.activo is False

    def test_desactivar_y_activar(self, client_a, rol):
        resp = client_a.post(f"/api/core/roles/{rol.id_rol}/desactivar/")
        assert resp.status_code == 200
        assert resp.json()["activo"] is False
        rol.refresh_from_db()
        assert rol.activo is False
        # Reactivar (el objeto ya no está en el queryset de activos)
        resp = client_a.post(f"/api/core/roles/{rol.id_rol}/activar/")
        assert resp.status_code == 200
        assert resp.json()["activo"] is True
        rol.refresh_from_db()
        assert rol.activo is True

    def test_activar_ya_activo_400(self, client_a, rol):
        resp = client_a.post(f"/api/core/roles/{rol.id_rol}/activar/")
        assert resp.status_code == 400
        assert resp.json()["error"] == "El registro ya está activo."

    def test_activar_inexistente_404(self, client_a):
        resp = client_a.post(f"/api/core/roles/{uuid.uuid4()}/activar/")
        assert resp.status_code == 404

    def test_rol_de_otra_empresa_no_visible(self, client_a, empresa_b):
        ajeno = Roles.objects.create(id_empresa=empresa_b, nombre_rol="Ajeno")
        resp = client_a.get(f"/api/core/roles/{ajeno.id_rol}/")
        assert resp.status_code == 404


# ── UsuariosViewSet / DispositivoViewSet ──────────────────────────────────────


class TestUsuariosViewSet:
    def test_usuario_normal_solo_se_ve_a_si_mismo(self, client_a, user_a, user_b):
        resp = client_a.get("/api/core/usuarios/")
        assert resp.status_code == 200
        usernames = [u["username"] for u in resp.json()["results"]]
        assert usernames == [user_a.username]

    def test_superusuario_ve_todos(self, client_super, user_a, user_b):
        resp = client_super.get("/api/core/usuarios/")
        usernames = {u["username"] for u in resp.json()["results"]}
        assert {"user_empresa_a", "user_empresa_b", "super_omni"} <= usernames


class TestDispositivoViewSet:
    @pytest.fixture
    def dispositivo_b(self, empresa_b, user_b):
        suc = Sucursal.objects.create(id_empresa=empresa_b, nombre="S", codigo_sucursal="VS-B9")
        return Dispositivo.objects.create(
            fingerprint="fp-vs-b",
            user_agent="ua",
            nombre_dispositivo="Ajeno",
            empresa=empresa_b,
            sucursal=suc,
            creado_por=user_b,
        )

    def test_usuario_solo_ve_sus_dispositivos(self, client_a, dispositivo_b):
        resp = client_a.get("/api/core/dispositivos/")
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    def test_superusuario_ve_todos(self, client_super, dispositivo_b):
        resp = client_super.get("/api/core/dispositivos/")
        assert len(resp.json()["results"]) == 1

    def test_perform_create_fuerza_creado_por(self, client_a, user_a, user_b, empresa_a, sucursal_a):
        # SEC-M1: el intento de spoofing con un usuario de otra empresa ahora
        # se RECHAZA (400) por el scope de tenant de FKs, en vez de ignorarse.
        resp = client_a.post(
            "/api/core/dispositivos/",
            {
                "fingerprint": "fp-vs-nuevo",
                "user_agent": "Mozilla Chrome Windows",
                "nombre_dispositivo": "Mi PC",
                "empresa": str(empresa_a.id_empresa),
                "sucursal": str(sucursal_a.id_sucursal),
                "creado_por": str(user_b.id),  # intento de spoofing
            },
            format="json",
        )
        assert resp.status_code == 400

        # Con un usuario visible (el propio), perform_create sigue forzando
        # creado_por=request.user sin importar el payload.
        resp = client_a.post(
            "/api/core/dispositivos/",
            {
                "fingerprint": "fp-vs-nuevo",
                "user_agent": "Mozilla Chrome Windows",
                "nombre_dispositivo": "Mi PC",
                "empresa": str(empresa_a.id_empresa),
                "sucursal": str(sucursal_a.id_sucursal),
                "creado_por": str(user_a.id),
            },
            format="json",
        )
        assert resp.status_code == 201
        disp = Dispositivo.objects.get(fingerprint="fp-vs-nuevo")
        assert disp.creado_por == user_a


# ── PermisosViewSet (gate H-SEC-7) ────────────────────────────────────────────


class TestPermisosGate:
    PAYLOAD = {
        "codigo_permiso": "ventas.facturar",
        "nombre_permiso": "Facturar",
        "modulo": "ventas",
    }

    def test_usuario_normal_no_puede_crear_403(self, client_a):
        resp = client_a.post("/api/core/permisos/", self.PAYLOAD, format="json")
        assert resp.status_code == 403
        assert Permisos.objects.count() == 0

    def test_superusuario_crea_modifica_borra(self, client_super):
        resp = client_super.post("/api/core/permisos/", self.PAYLOAD, format="json")
        assert resp.status_code == 201
        pk = resp.json()["id_permiso"]
        resp = client_super.patch(
            f"/api/core/permisos/{pk}/", {"nombre_permiso": "Facturar v2"}, format="json"
        )
        assert resp.status_code == 200
        assert resp.json()["nombre_permiso"] == "Facturar v2"
        resp = client_super.delete(f"/api/core/permisos/{pk}/")
        assert resp.status_code == 204
        # Soft-delete: sigue en DB pero inactivo
        assert Permisos.objects.get(id_permiso=pk).activo is False

    def test_usuario_normal_no_puede_modificar_403(self, client_a, client_super):
        client_super.post("/api/core/permisos/", self.PAYLOAD, format="json")
        permiso = Permisos.objects.get()
        resp = client_a.patch(
            f"/api/core/permisos/{permiso.id_permiso}/", {"modulo": "otro"}, format="json"
        )
        assert resp.status_code == 403
        resp = client_a.delete(f"/api/core/permisos/{permiso.id_permiso}/")
        assert resp.status_code == 403


# ── ContactoViewSet ───────────────────────────────────────────────────────────


class TestContactoViewSet:
    def test_filtro_por_rol_booleano(self, client_a, empresa_a):
        Contacto.objects.create(id_empresa=empresa_a, nombre="Cliente1", es_cliente=True)
        Contacto.objects.create(id_empresa=empresa_a, nombre="Prov1", es_proveedor=True)
        resp = client_a.get("/api/core/contactos/?es_cliente=true")
        nombres = [c["nombre"] for c in resp.json()["results"]]
        assert nombres == ["Cliente1"]
        resp = client_a.get("/api/core/contactos/?es_cliente=false")
        nombres = [c["nombre"] for c in resp.json()["results"]]
        assert nombres == ["Prov1"]

    def test_create_inyecta_empresa_del_usuario(self, client_a, empresa_a, empresa_b):
        resp = client_a.post(
            "/api/core/contactos/",
            {"nombre": "Nuevo", "tipo_persona": "JURIDICA", "id_empresa": str(empresa_b.id_empresa)},
            format="json",
        )
        assert resp.status_code == 201
        contacto = Contacto.objects.get(nombre="Nuevo")
        assert contacto.id_empresa == empresa_a  # NO la del payload (H-API-1)

    def test_create_sin_empresa_403(self, db):
        from django.contrib.auth import get_user_model

        huerfano = get_user_model().objects.create_user(username="sin_empresa", password="x")
        c = APIClient()
        c.force_authenticate(user=huerfano)
        resp = c.post("/api/core/contactos/", {"nombre": "X"}, format="json")
        assert resp.status_code == 403

    def test_aislamiento_multitenant(self, client_a, empresa_b):
        Contacto.objects.create(id_empresa=empresa_b, nombre="Ajeno")
        resp = client_a.get("/api/core/contactos/")
        assert resp.json()["results"] == []


# ── ConfiguracionFlujoDocumentosViewSet ───────────────────────────────────────


class TestConfiguracionFlujoViewSet:
    def test_create_y_filtro_tipo_documento(self, client_a, empresa_a):
        resp = client_a.post(
            "/api/core/flujo-documentos/",
            {"tipo_documento": "VENTAS", "paso": "FACTURA", "obligatorio": True, "orden": 4},
            format="json",
        )
        assert resp.status_code == 201
        cfg = ConfiguracionFlujoDocumentos.objects.get()
        assert cfg.id_empresa == empresa_a
        ConfiguracionFlujoDocumentos.objects.create(
            id_empresa=empresa_a, tipo_documento="COMPRAS", paso="RECEPCION", orden=3
        )
        resp = client_a.get("/api/core/flujo-documentos/?tipo_documento=VENTAS")
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["paso"] == "FACTURA"

    def test_create_sin_empresa_403(self, db):
        from django.contrib.auth import get_user_model

        huerfano = get_user_model().objects.create_user(username="sin_empresa2", password="x")
        c = APIClient()
        c.force_authenticate(user=huerfano)
        resp = c.post(
            "/api/core/flujo-documentos/",
            {"tipo_documento": "VENTAS", "paso": "PEDIDO"},
            format="json",
        )
        assert resp.status_code == 403


# ── NotificacionViewSet ───────────────────────────────────────────────────────


class TestNotificacionViewSet:
    def test_ve_propias_y_broadcast_pero_no_ajenas(self, client_a, empresa_a, empresa_b, user_a, user_b):
        crear_notificacion(empresa=empresa_a, titulo="Mía", mensaje="m", usuario=user_a)
        crear_notificacion(empresa=empresa_a, titulo="Broadcast", mensaje="m")
        crear_notificacion(empresa=empresa_b, titulo="Otra empresa", mensaje="m")
        n_user_b = Notificacion.objects.create(
            id_empresa=empresa_a, id_usuario=user_b, titulo="De B", mensaje="m"
        )
        resp = client_a.get("/api/core/notificaciones/")
        titulos = {n["titulo"] for n in resp.json()["results"]}
        assert titulos == {"Mía", "Broadcast"}

    def test_marcar_leida(self, client_a, empresa_a, user_a):
        n = crear_notificacion(empresa=empresa_a, titulo="t", mensaje="m", usuario=user_a)
        resp = client_a.post(f"/api/core/notificaciones/{n.id_notificacion}/marcar_leida/")
        assert resp.status_code == 200
        assert resp.json()["leida"] is True
        n.refresh_from_db()
        assert n.fecha_lectura is not None

    def test_no_leidas_y_marcar_todas(self, client_a, empresa_a, user_a):
        crear_notificacion(empresa=empresa_a, titulo="a", mensaje="m", usuario=user_a)
        crear_notificacion(empresa=empresa_a, titulo="b", mensaje="m", usuario=user_a)
        resp = client_a.get("/api/core/notificaciones/no_leidas/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2
        assert len(resp.json()["notificaciones"]) == 2
        resp = client_a.post("/api/core/notificaciones/marcar_todas_leidas/")
        assert resp.json()["marcadas_leidas"] == 2
        resp = client_a.get("/api/core/notificaciones/no_leidas/")
        assert resp.json()["count"] == 0


# ── Serializers ───────────────────────────────────────────────────────────────


class TestEmpresaSerializerValidate:
    def test_moneda_pais_no_coincide_con_pais(self, empresa_a, moneda_usd):
        moneda_usd.pais_codigo_iso = "US"
        moneda_usd.save()
        empresa_a.id_moneda_pais = moneda_usd
        empresa_a.pais_codigo_iso = "VE"
        empresa_a.save()
        serializer = EmpresaSerializer(instance=empresa_a)
        with pytest.raises(drf_serializers.ValidationError) as exc:
            serializer.validate({})
        assert "id_moneda_pais" in exc.value.detail

    def test_moneda_pais_coincide_pasa(self, empresa_a, moneda_usd):
        moneda_usd.pais_codigo_iso = "US"
        moneda_usd.save()
        empresa_a.id_moneda_pais = moneda_usd
        empresa_a.pais_codigo_iso = "US"
        empresa_a.save()
        serializer = EmpresaSerializer(instance=empresa_a)
        assert serializer.validate({}) == {}

    def test_moneda_pais_inexistente(self, empresa_a):
        serializer = EmpresaSerializer(instance=empresa_a)
        with pytest.raises(drf_serializers.ValidationError) as exc:
            serializer.validate({"id_moneda_pais": uuid.uuid4(), "pais_codigo_iso": "VE"})
        assert "no existe" in str(exc.value.detail["id_moneda_pais"])


class TestSucursalSerializerCreate:
    def test_create_resuelve_uuid_de_empresa(self, empresa_a):
        serializer = SucursalSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "nombre": "Nueva Sucursal",
                "codigo_sucursal": "VS-NEW",
            }
        )
        assert serializer.is_valid(), serializer.errors
        sucursal = serializer.save()
        assert sucursal.id_empresa == empresa_a
        assert Sucursal.objects.filter(codigo_sucursal="VS-NEW").exists()


class TestUsuariosSerializer:
    def test_get_roles(self, user_a, empresa_a):
        rol = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Vendedor")
        UsuarioRoles.objects.create(id_usuario=user_a, id_rol=rol)
        data = UsuariosSerializer(user_a).data
        assert data["roles"] == [{"id": str(rol.id_rol), "name": "Vendedor"}]
        assert "password" not in data  # write_only
        assert "is_superuser" not in data  # whitelist H-API-3

    def test_update_usuario_normal_no_escala_superusuario(self, user_a):
        ctx = {"request": SimpleNamespace(user=user_a)}
        serializer = UsuariosSerializer(
            instance=user_a, data={"es_superusuario_omni": True}, partial=True, context=ctx
        )
        assert serializer.is_valid(), serializer.errors
        actualizado = serializer.save()
        assert actualizado.es_superusuario_omni is False  # gate aplicado

    def test_update_superusuario_si_puede(self, user_a, superuser):
        ctx = {"request": SimpleNamespace(user=superuser)}
        serializer = UsuariosSerializer(
            instance=user_a, data={"es_superusuario_omni": True}, partial=True, context=ctx
        )
        assert serializer.is_valid(), serializer.errors
        assert serializer.save().es_superusuario_omni is True

    def test_create_sin_contexto_descarta_superusuario(self, db):
        serializer = UsuariosSerializer(
            data={"username": "nuevo_u", "password": "x12345", "es_superusuario_omni": True}
        )
        assert serializer.is_valid(), serializer.errors
        creado = serializer.save()
        assert creado.es_superusuario_omni is False


class TestDispositivoSerializerCreate:
    def test_create_fuerza_creado_por_del_request(self, user_a, user_b, empresa_a, sucursal_a):
        ctx = {"request": SimpleNamespace(user=user_a)}
        serializer = DispositivoSerializer(
            data={
                "fingerprint": "fp-ser-1",
                "user_agent": "ua",
                "nombre_dispositivo": "PC",
                "empresa": str(empresa_a.id_empresa),
                "sucursal": str(sucursal_a.id_sucursal),
                "creado_por": str(user_b.id),
            },
            context=ctx,
        )
        assert serializer.is_valid(), serializer.errors
        disp = serializer.save()
        assert disp.creado_por == user_a
