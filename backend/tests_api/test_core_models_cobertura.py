"""
Backfill de cobertura — apps/core/models.py (métodos de modelo sin cubrir).

Cubre:
- ``Dispositivo``: ``generar_nombre_dispositivo`` (todas las ramas de plataforma/
  navegador), ``obtener_o_crear`` (crear vs reusar), propiedades ``tiene_caja_fisica``
  y ``puede_crear_caja_fisica``, ``marcar_no_preguntar_caja`` y ``__str__``.
- ``CapabilityToken``: ``is_expired``, ``comodin_autorizado`` (M-SEC-9),
  ``has_scope`` (explícito / comodín autorizado / comodín NO autorizado),
  ``mark_used`` y ``__str__``.
- ``Usuarios``: propiedad ``empresa`` y ``get_cajas_virtuales_disponibles``
  (registradora / gerencia / filtro por empresa / usuario sin asignaciones).
- ``Notificacion.marcar_leida`` + helper ``crear_notificacion``.
- ``__str__`` de Empresa, Sucursal, Departamento, Roles, Permisos, RolPermisos,
  UsuarioRoles, RegistroAuditoria, ClaveIdempotencia, Contacto (3 ramas),
  ConfiguracionFlujoDocumentos y Notificacion; ``Contacto.nombre_completo``.
"""
import datetime

import pytest
from django.utils import timezone

from apps.core.models import (
    CapabilityToken,
    ClaveIdempotencia,
    ConfiguracionFlujoDocumentos,
    Contacto,
    Departamento,
    Dispositivo,
    Notificacion,
    Permisos,
    RegistroAuditoria,
    Roles,
    RolPermisos,
    Sucursal,
    UsuarioRoles,
    crear_notificacion,
)
from apps.finanzas.models import Caja, CajaFisica, CajaFisicaUsuario

pytestmark = pytest.mark.django_db


@pytest.fixture
def sucursal_a(empresa_a):
    return Sucursal.objects.create(
        id_empresa=empresa_a, nombre="Sucursal Modelos", codigo_sucursal="SUC-M1"
    )


# ── Dispositivo ───────────────────────────────────────────────────────────────


class TestGenerarNombreDispositivo:
    @pytest.mark.parametrize(
        ("user_agent", "esperado"),
        [
            ("Mozilla (Windows NT 10.0) Chrome/120", "Chrome en Windows"),
            ("Mozilla (Macintosh; Mac OS X) Safari/605", "Safari en macOS"),
            ("Mozilla (X11; Linux x86_64) Firefox/118", "Firefox en Linux"),
            ("Mozilla (Android 13) Edge/120", "Edge en Android"),
            ("Mozilla (iPhone; CPU iPhone OS)", "Navegador en iOS"),
            ("curl/8.0", "Navegador en Desconocido"),
        ],
    )
    def test_ramas_plataforma_navegador(self, user_agent, esperado):
        assert Dispositivo.generar_nombre_dispositivo(user_agent) == esperado


class TestDispositivoModelo:
    @pytest.fixture
    def dispositivo(self, empresa_a, sucursal_a, user_a):
        return Dispositivo.objects.create(
            fingerprint="fp-modelo-1",
            user_agent="Chrome Windows",
            ip_address="10.0.0.9",
            nombre_dispositivo="Chrome en Windows",
            empresa=empresa_a,
            sucursal=sucursal_a,
            creado_por=user_a,
        )

    def test_obtener_o_crear_crea_nuevo(self, empresa_a, sucursal_a, user_a):
        disp, created = Dispositivo.obtener_o_crear(
            fingerprint="fp-nuevo",
            user_agent="Mozilla Linux Firefox",
            ip_address="10.0.0.2",
            empresa=empresa_a,
            sucursal=sucursal_a,
            usuario=user_a,
        )
        assert created is True
        assert disp.nombre_dispositivo == "Firefox en Linux"
        assert disp.creado_por == user_a
        assert disp.ultimo_login is not None

    def test_obtener_o_crear_reusa_existente(self, dispositivo, empresa_a, sucursal_a, user_b):
        antes = dispositivo.ultimo_login
        disp, created = Dispositivo.obtener_o_crear(
            fingerprint="fp-modelo-1",
            user_agent="otro UA",
            ip_address="9.9.9.9",
            empresa=empresa_a,
            sucursal=sucursal_a,
            usuario=user_b,
        )
        assert created is False
        assert disp.id_dispositivo == dispositivo.id_dispositivo
        # No pisa los datos originales, solo refresca ultimo_login
        assert disp.user_agent == "Chrome Windows"
        assert disp.creado_por == dispositivo.creado_por
        assert disp.ultimo_login >= antes

    def test_tiene_caja_fisica(self, dispositivo, empresa_a):
        assert dispositivo.tiene_caja_fisica is False
        dispositivo.caja_fisica = CajaFisica.objects.create(
            empresa=empresa_a, nombre="Caja M", identificador_dispositivo="disp-m-1"
        )
        dispositivo.save()
        assert dispositivo.tiene_caja_fisica is True

    def test_puede_crear_caja_fisica_solo_superusuario(self, dispositivo, user_a):
        assert dispositivo.puede_crear_caja_fisica is False
        user_a.es_superusuario_omni = True
        user_a.save(update_fields=["es_superusuario_omni"])
        dispositivo.refresh_from_db()
        assert dispositivo.puede_crear_caja_fisica is True

    def test_marcar_no_preguntar_caja(self, dispositivo):
        dispositivo.marcar_no_preguntar_caja()
        dispositivo.refresh_from_db()
        assert dispositivo.preguntar_crear_caja is False
        assert dispositivo.ultima_pregunta_caja is not None

    def test_str(self, dispositivo, empresa_a):
        assert str(dispositivo) == "Chrome en Windows - Empresa Alpha S.A."
        empresa_a.nombre_comercial = "Alpha"
        empresa_a.save()
        dispositivo.refresh_from_db()
        assert str(dispositivo) == "Chrome en Windows - Alpha"


# ── CapabilityToken ───────────────────────────────────────────────────────────


class TestCapabilityToken:
    def test_is_expired(self, empresa_a):
        t = CapabilityToken.objects.create(empresa=empresa_a, nombre="t", scopes=["crm:read"])
        assert t.is_expired() is False  # expires_at None
        t.expires_at = timezone.now() + datetime.timedelta(days=1)
        assert t.is_expired() is False
        t.expires_at = timezone.now() - datetime.timedelta(seconds=1)
        assert t.is_expired() is True

    def test_comodin_autorizado_sin_creador(self, empresa_a):
        t = CapabilityToken.objects.create(empresa=empresa_a, nombre="sistema", scopes=["*"])
        assert t.comodin_autorizado is True
        assert t.has_scope("ventas:write") is True

    def test_comodin_no_autorizado_para_usuario_normal(self, empresa_a, user_a):
        """M-SEC-9: un usuario normal no escala con '*'."""
        t = CapabilityToken.objects.create(
            empresa=empresa_a, nombre="t", scopes=["*"], creado_por=user_a
        )
        assert t.comodin_autorizado is False
        assert t.has_scope("ventas:write") is False

    def test_comodin_autorizado_para_superusuario(self, empresa_a, user_a):
        user_a.es_superusuario_omni = True
        user_a.save(update_fields=["es_superusuario_omni"])
        t = CapabilityToken.objects.create(
            empresa=empresa_a, nombre="t", scopes=["*"], creado_por=user_a
        )
        assert t.comodin_autorizado is True
        assert t.has_scope("cxc:write") is True

    def test_has_scope_explicito(self, empresa_a, user_a):
        t = CapabilityToken.objects.create(
            empresa=empresa_a, nombre="t", scopes=["crm:read"], creado_por=user_a
        )
        assert t.has_scope("crm:read") is True
        assert t.has_scope("crm:write") is False

    def test_mark_used_no_toca_fecha_actualizacion(self, empresa_a):
        t = CapabilityToken.objects.create(empresa=empresa_a, nombre="t", scopes=[])
        assert t.ultimo_uso is None
        fecha_act = t.fecha_actualizacion
        t.mark_used()
        t.refresh_from_db()
        assert t.ultimo_uso is not None
        assert t.fecha_actualizacion == fecha_act  # update_fields evita el auto_now

    def test_str_incluye_nombre_y_prefijo_token(self, empresa_a):
        t = CapabilityToken.objects.create(empresa=empresa_a, nombre="Agente CxC", scopes=[])
        s = str(t)
        assert s.startswith("Agente CxC (")
        assert str(t.token)[:8] in s
        assert "Empresa Alpha S.A." in s


# ── Usuarios ──────────────────────────────────────────────────────────────────


class TestUsuariosModelo:
    def test_propiedad_empresa(self, user_a, empresa_a):
        assert user_a.empresa == empresa_a

    def test_str_es_username(self, user_a):
        assert str(user_a) == "user_empresa_a"

    def test_cajas_virtuales_sin_asignaciones(self, user_a, empresa_a):
        assert list(user_a.get_cajas_virtuales_disponibles()) == []

    def test_cajas_virtuales_disponibles_por_tipo(self, user_a, empresa_a, empresa_b, moneda_usd):
        cf_a = CajaFisica.objects.create(
            empresa=empresa_a, nombre="CF-A", identificador_dispositivo="cv-a"
        )
        cf_b = CajaFisica.objects.create(
            empresa=empresa_b, nombre="CF-B", identificador_dispositivo="cv-b"
        )
        CajaFisicaUsuario.objects.create(usuario=user_a, caja_fisica=cf_a)
        CajaFisicaUsuario.objects.create(usuario=user_a, caja_fisica=cf_b)
        reg = Caja.objects.create(
            empresa=empresa_a, nombre="Registradora", tipo_caja="REGISTRADORA",
            moneda=moneda_usd, caja_fisica=cf_a,
        )
        ger = Caja.objects.create(
            empresa=empresa_a, nombre="Gerencia", tipo_caja="GERENCIA",
            moneda=moneda_usd, caja_fisica=cf_a,
        )
        otra = Caja.objects.create(
            empresa=empresa_a, nombre="Otra", tipo_caja="OTRO",
            moneda=moneda_usd, caja_fisica=cf_a,
        )
        caja_b = Caja.objects.create(
            empresa=empresa_b, nombre="Caja B", tipo_caja="REGISTRADORA",
            moneda=moneda_usd, caja_fisica=cf_b,
        )
        # Sin asignación a caja física no aparece
        Caja.objects.create(
            empresa=empresa_a, nombre="Huérfana", tipo_caja="REGISTRADORA", moneda=moneda_usd
        )
        todas = set(user_a.get_cajas_virtuales_disponibles().values_list("nombre", flat=True))
        assert todas == {"Registradora", "Gerencia", "Otra", "Caja B"}
        # Filtro por empresa
        solo_a = set(
            user_a.get_cajas_virtuales_disponibles(empresa=empresa_a).values_list("nombre", flat=True)
        )
        assert solo_a == {"Registradora", "Gerencia", "Otra"}
        assert caja_b.nombre not in solo_a


# ── __str__ de modelos ────────────────────────────────────────────────────────


class TestStrs:
    def test_empresa_str(self, empresa_a):
        assert str(empresa_a) == "Empresa Alpha S.A."
        empresa_a.nombre_comercial = "Alpha"
        assert str(empresa_a) == "Alpha"

    def test_sucursal_str(self, sucursal_a):
        assert str(sucursal_a) == "Sucursal Modelos (Empresa Alpha S.A.)"

    def test_departamento_str(self, empresa_a):
        dep = Departamento.objects.create(id_empresa=empresa_a, nombre_departamento="Ventas")
        assert str(dep) == "Ventas (Empresa Alpha S.A.)"

    def test_roles_permisos_strs(self, empresa_a, user_a):
        rol = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Cajero")
        permiso = Permisos.objects.create(
            codigo_permiso="ventas.cobrar", nombre_permiso="Cobrar ventas", modulo="ventas"
        )
        rp = RolPermisos.objects.create(id_rol=rol, id_permiso=permiso)
        ur = UsuarioRoles.objects.create(id_usuario=user_a, id_rol=rol)
        assert str(rol) == "Cajero"
        assert str(permiso) == "Cobrar ventas"
        assert str(rp) == "Cajero - Cobrar ventas"
        assert str(ur) == "user_empresa_a - Cajero"

    def test_registro_auditoria_str(self, empresa_a, user_a):
        log = RegistroAuditoria.objects.create(
            id_empresa=empresa_a,
            id_usuario=user_a,
            tipo_evento="LOGIN",
            modulo_afectado="core",
            nombre_modelo_afectado="Usuarios",
            id_registro_afectado="1",
            resultado_evento="EXITO",
        )
        assert "user_empresa_a - LOGIN en core.Usuarios" in str(log)
        log_sin_user = RegistroAuditoria.objects.create(
            id_empresa=empresa_a,
            tipo_evento="ERROR",
            modulo_afectado="core",
            resultado_evento="FALLO",
        )
        assert "N/A - ERROR" in str(log_sin_user)

    def test_clave_idempotencia_str(self, empresa_a):
        clave = ClaveIdempotencia.objects.create(
            empresa=empresa_a,
            scope="cxc:abonar",
            clave="abcdef0123456789XYZ",
            payload_hash="0" * 64,
            status_respuesta=201,
        )
        assert str(clave).startswith("cxc:abonar:abcdef0123456789…")

    def test_contacto_str_y_nombre_completo(self, empresa_a):
        juridica = Contacto.objects.create(
            id_empresa=empresa_a, tipo_persona="JURIDICA", nombre="Acme C.A."
        )
        assert str(juridica) == "Acme C.A."
        assert juridica.nombre_completo == "Acme C.A."
        natural = Contacto.objects.create(
            id_empresa=empresa_a, tipo_persona="NATURAL", nombre="Ana", apellido="Pérez"
        )
        assert str(natural) == "Ana Pérez"
        assert natural.nombre_completo == "Ana Pérez"
        comercial = Contacto.objects.create(
            id_empresa=empresa_a, tipo_persona="JURIDICA", nombre="X", nombre_comercial="MarcaX"
        )
        assert str(comercial) == "MarcaX"
        assert comercial.nombre_completo == "MarcaX"

    def test_configuracion_flujo_str(self, empresa_a):
        cfg = ConfiguracionFlujoDocumentos.objects.create(
            id_empresa=empresa_a,
            tipo_documento="VENTAS",
            paso="FACTURA",
            obligatorio=True,
            orden=4,
        )
        assert "VENTAS | FACTURA (obligatorio, orden 4)" in str(cfg)
        cfg.obligatorio = False
        assert "(opcional, orden 4)" in str(cfg)


# ── Notificacion ──────────────────────────────────────────────────────────────


class TestNotificacion:
    def test_crear_notificacion_helper_y_str(self, empresa_a, user_a):
        n = crear_notificacion(
            empresa=empresa_a,
            titulo="Stock bajo",
            mensaje="El producto X está por agotarse",
            tipo="INVENTARIO",
            usuario=user_a,
            url_accion="/inventario/x/",
            metadata={"producto": "X"},
        )
        assert n.id_empresa == empresa_a
        assert n.id_usuario == user_a
        assert n.metadata == {"producto": "X"}
        assert str(n) == "[INVENTARIO] Stock bajo"

    def test_crear_notificacion_broadcast_metadata_default(self, empresa_a):
        n = crear_notificacion(empresa=empresa_a, titulo="Aviso", mensaje="m")
        assert n.id_usuario is None
        assert n.tipo == "INFO"
        assert n.metadata == {}

    def test_marcar_leida(self, empresa_a):
        n = crear_notificacion(empresa=empresa_a, titulo="t", mensaje="m")
        assert n.leida is False
        assert n.fecha_lectura is None
        n.marcar_leida()
        n.refresh_from_db()
        assert n.leida is True
        assert n.fecha_lectura is not None
