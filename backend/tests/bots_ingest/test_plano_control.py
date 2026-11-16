"""Tests del plano de control multi-tenant de bots, CapabilityToken REST y herramientas MCP."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.bots_ingest.mcp import bots_cambiar_habilitado, bots_estado_flota
from apps.bots_ingest.models import (
    BotBitacora,
    BotLatidoDiario,
    BotRegistro,
    BotUsuario,
)
from apps.bots_ingest.services import control as ctrl_svc
from apps.bots_ingest.services.control import DatoControlInvalido
from apps.core.capability_auth import CapabilityPrincipal
from apps.core.models import CapabilityToken
from tests.factories.core import UsuariosFactory

pytestmark = [pytest.mark.django_db]


def _cliente_token(header_name: str, valor: str) -> APIClient:
    c = APIClient()
    c.credentials(**{header_name: valor})
    return c


# ── Autenticación máquina-a-máquina y aislamiento multi-tenant ───────────────


@pytest.mark.tenant
def test_capability_token_aisla_latido_y_flota_entre_empresas(
    empresa_a, empresa_b, user_a, user_b
):
    tok_a = CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="Worker A",
        scopes=["bots:heartbeat", "bots:read", "bots:write"],
        creado_por=user_a,
    )
    tok_b = CapabilityToken.objects.create(
        empresa=empresa_b,
        nombre="Worker B",
        scopes=["bots:heartbeat", "bots:read"],
        creado_por=user_b,
    )
    BotUsuario.objects.create(
        id_empresa=empresa_a,
        telegram_user_id=700001,
        usuario=user_a,
        nombre="Vendedor A",
        bots=["pedidos"],
    )
    BotUsuario.objects.create(
        id_empresa=empresa_b,
        telegram_user_id=700002,
        usuario=user_b,
        nombre="Vendedor B",
        bots=["pedidos"],
    )

    cli_a = _cliente_token("HTTP_X_CAPABILITY_TOKEN", str(tok_a.token))
    cli_b = _cliente_token("HTTP_X_BOT_KEY", str(tok_b.token))

    r_a = cli_a.post(
        "/api/bots/heartbeat/",
        {
            "bot": "pedidos",
            "nombre": "Ventas A",
            "version": "1.2",
            "estado": {
                "modo": "polling",
                "gemini": "ok",
                "omni": "ok",
                "cxc": "desactivado",
                "outbox_pendientes": 3,
                "mensajes_hoy": 14,
                "errores_hoy": 1,
            },
        },
        format="json",
    )
    assert r_a.status_code == 200, r_a.data
    assert [u["telegram_id"] for u in r_a.data["usuarios"]] == [700001]
    tok_a.refresh_from_db()
    assert tok_a.ultimo_uso is not None

    # Empresa B no ve el latido ni la pausa ni los usuarios de Empresa A.
    flota_b = cli_b.get("/api/bots/control/").data["items"]
    pedidos_b = next(x for x in flota_b if x["bot"] == "pedidos")
    assert pedidos_b["visto_alguna_vez"] is False
    assert pedidos_b["n_usuarios"] == 1

    pausa_a = cli_a.patch(
        "/api/bots/control/pedidos/",
        {"habilitado": False, "mensaje": "Mantenimiento A"},
        format="json",
    )
    assert pausa_a.status_code == 200
    assert pausa_a.data["habilitado"] is False

    r_b = cli_b.post(
        "/api/bots/heartbeat/",
        {"bot": "pedidos", "version": "1.0", "estado": {}},
        format="json",
    )
    assert r_b.status_code == 200
    assert r_b.data["habilitado"] is True
    assert [u["telegram_id"] for u in r_b.data["usuarios"]] == [700002]


@pytest.mark.tenant
def test_capability_token_authorization_header_y_rechazos_invalidos(
    empresa_a, user_a
):
    tok_valido = CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="Bot Auth Header",
        scopes=["bots:heartbeat"],
        creado_por=user_a,
    )
    cli_ok = _cliente_token(
        "HTTP_AUTHORIZATION", f"CapabilityToken {tok_valido.token}"
    )
    assert (
        cli_ok.post("/api/bots/heartbeat/", {"bot": "eventos"}, format="json").status_code
        == 200
    )

    # Token malformado, inexistente, revocado o expirado -> 401
    assert (
        _cliente_token("HTTP_X_CAPABILITY_TOKEN", "no-es-uuid")
        .post("/api/bots/heartbeat/", {"bot": "eventos"}, format="json")
        .status_code
        == 401
    )
    assert (
        _cliente_token(
            "HTTP_X_CAPABILITY_TOKEN", "00000000-0000-0000-0000-000000000000"
        )
        .post("/api/bots/heartbeat/", {"bot": "eventos"}, format="json")
        .status_code
        == 401
    )

    tok_exp = CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="Expirado",
        scopes=["bots:heartbeat"],
        expires_at=timezone.now() - timedelta(minutes=5),
        creado_por=user_a,
    )
    assert (
        _cliente_token("HTTP_X_CAPABILITY_TOKEN", str(tok_exp.token))
        .post("/api/bots/heartbeat/", {"bot": "eventos"}, format="json")
        .status_code
        == 401
    )

    # Un CapabilityToken nunca autentica en endpoints humanos ajenos al opt-in.
    assert (
        _cliente_token("HTTP_X_CAPABILITY_TOKEN", str(tok_valido.token))
        .get("/api/core/empresas/")
        .status_code
        == 401
    )

    # Cobertura explícita de propiedades del principal máquina-a-máquina.
    p = CapabilityPrincipal(tok_valido)
    assert p.pk.startswith("cap:")
    assert p.id == tok_valido.pk
    assert p.empresa == empresa_a
    assert p.username.startswith("cap:")
    assert p.is_authenticated is True
    assert p.is_anonymous is False
    assert p.is_active is True
    assert p.is_staff is False
    assert p.is_superuser is False
    assert p.es_superusuario_omni is False
    assert p.has_perm("bots_ingest.ingestar") is False
    assert p.has_perms(["bots_ingest.ingestar"]) is False
    assert p.has_module_perms("bots_ingest") is False
    assert p.has_scope("bots:heartbeat") is True
    assert p.has_scope("bots:write") is False


@pytest.mark.tenant
def test_scopes_granulares_impiden_escalacion_en_ingest_y_control(
    empresa_a, user_a
):
    BotUsuario.objects.create(
        id_empresa=empresa_a,
        telegram_user_id=800111,
        usuario=user_a,
        nombre="Vendedor",
        bots=["compras"],
    )
    tok_solo_latido = CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="Solo Latido",
        scopes=["bots:heartbeat"],
        creado_por=user_a,
    )
    cli_latido = _cliente_token("HTTP_X_CAPABILITY_TOKEN", str(tok_solo_latido.token))
    assert (
        cli_latido.post(
            "/api/bots/ingest/",
            {
                "kind": "proveedor",
                "draft": {"nombre": "Prov X"},
                "source": {"telegram_user_id": 800111},
                "idempotency_key": "idem-1",
            },
            format="json",
        ).status_code
        == 403
    )
    assert cli_latido.get("/api/bots/control/").status_code == 403
    assert (
        cli_latido.patch(
            "/api/bots/control/compras/", {"habilitado": False}, format="json"
        ).status_code
        == 403
    )

    # Token con bots:ingest puede ingerir para bot autorizado, pero respeta BotUsuario.bots
    tok_ingest = CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="Ingestor",
        scopes=["bots:ingest"],
        creado_por=user_a,
    )
    cli_ingest = _cliente_token("HTTP_X_CAPABILITY_TOKEN", str(tok_ingest.token))
    r_bloqueado = cli_ingest.post(
        "/api/bots/ingest/",
        {
            "kind": "proveedor",
            "draft": {"nombre": "Prov X", "rif": "J-12345678-9", "telefono": "0414-1234567"},
            "source": {"telegram_user_id": 800111, "bot": "pedidos"},
            "idempotency_key": "idem-bloqueado",
        },
        format="json",
    )
    assert r_bloqueado.status_code == 403

    r_permitido = cli_ingest.post(
        "/api/bots/ingest/",
        {
            "kind": "proveedor",
            "draft": {"nombre": "Prov X", "rif": "J-12345678-9", "telefono": "0414-1234567"},
            "source": {"telegram_user_id": 800111, "bot": "compras"},
            "idempotency_key": "idem-ok",
        },
        format="json",
    )
    assert r_permitido.status_code == 201, r_permitido.data


# ── Redacción de secretos, configuración, historial, destinos y bitácora ─────


def test_redaccion_secretos_y_retencion_suave_de_latidos(empresa_a):
    secreto_tg = f"{1234567890}:AAH" + ("x" * 32)
    secreto_gm = "AIza" + "Sy" + ("0" * 33)
    secreto_bearer = "Bearer " + ("z" * 28)

    dia_viejo = timezone.now() - timedelta(days=40)
    BotLatidoDiario.objects.create(
        id_empresa=empresa_a,
        codigo="pedidos",
        dia=dia_viejo.date(),
        latidos=5,
        mensajes=10,
        errores=0,
        ultimo=dia_viejo,
    )

    ctrl_svc.registrar_latido(
        empresa=empresa_a,
        codigo="pedidos",
        nombre="Ventas",
        version="2.0",
        estado={
            "modo": "webhook",
            "gemini": "error",
            "omni": "ok",
            "cxc": "error",
            "outbox_pendientes": 4,
            "mensajes_hoy": 20,
            "errores_hoy": 2,
            "ultimo_error": f"Fallo en /bot{secreto_tg}/getUpdates con {secreto_gm} y {secreto_bearer}",
        },
    )
    # Segundo latido el mismo día: incrementa latidos y conserva máximo de mensajes/errores
    ctrl_svc.registrar_latido(
        empresa=empresa_a,
        codigo="pedidos",
        nombre="Ventas",
        version="2.0",
        estado={
            "gemini": "ok",
            "omni": "ok",
            "cxc": "ok",
            "mensajes_hoy": 12,
            "errores_hoy": 5,
        },
    )

    reg = BotRegistro.objects.get(id_empresa=empresa_a, codigo="pedidos")
    ctrl_svc.registrar_latido(
        empresa=empresa_a,
        codigo="pedidos",
        estado={"ultimo_error": f"Token {secreto_tg}"},
    )
    reg.refresh_from_db()
    err = reg.estado["ultimo_error"]
    assert secreto_tg not in err
    assert "[oculto]" in err

    diario_hoy = BotLatidoDiario.objects.get(
        id_empresa=empresa_a, codigo="pedidos", dia=timezone.now().date()
    )
    assert diario_hoy.latidos == 3
    assert diario_hoy.mensajes == 20
    assert diario_hoy.errores == 5

    # El registro de >30 días se desactiva por soft-delete (nunca borrado físico)
    viejo = BotLatidoDiario.objects.get(
        id_empresa=empresa_a, codigo="pedidos", dia=dia_viejo.date()
    )
    assert viejo.activo is False


def test_configuracion_auditada_destinos_y_usuarios_staff(empresa_a, user_a):
    user_a.is_staff = True
    user_a.save(update_fields=["is_staff"])
    cli = APIClient()
    cli.force_authenticate(user=user_a)

    # Alta, edición y baja de BotUsuario dejan rastro en BotBitacora
    otro = UsuariosFactory(empresa=empresa_a)
    r_alta = cli.post(
        "/api/bots/usuarios/",
        {
            "telegram_user_id": 555666,
            "usuario": str(otro.pk),
            "nombre": "Ana",
            "bots": ["tareas", "compras"],
        },
        format="json",
    )
    assert r_alta.status_code == 201, r_alta.data
    uid = r_alta.data["id_bot_usuario"]

    # Equivalencia tareas <-> asana al reportar latido de transición
    latido_asana = ctrl_svc.registrar_latido(
        empresa=empresa_a,
        codigo="asana",
        estado={"gemini": "sin_clave", "omni": "desactivado", "cxc": "desactivado"},
    )
    assert [u["telegram_id"] for u in latido_asana["usuarios"]] == [555666]

    r_edit = cli.patch(
        f"/api/bots/usuarios/{uid}/",
        {"nombre": "Ana María", "bots": ["tareas"]},
        format="json",
    )
    assert r_edit.status_code == 200

    # Configuración del bot y bitácora sin ruido en guardados idénticos
    r_cfg = cli.patch(
        "/api/bots/control/compras/",
        {
            "habilitado": False,
            "nombre": "Compras Mayor",
            "parametros": {"auto_envio_min": 25, "gemini_model": "gemini-2.5-pro"},
            "chats": {"grupo": -100123456, "respaldo": None},
            "url_panel": "https://panel.ejemplo.com/bots",
            "mensaje": "Pausado por cierre mensual",
        },
        format="json",
    )
    assert r_cfg.status_code == 200, r_cfg.data
    assert r_cfg.data["habilitado"] is False
    assert r_cfg.data["parametros"]["auto_envio_min"] == 25
    assert r_cfg.data["chats"]["grupo"] == -100123456
    assert len(r_cfg.data["bitacora"]) == 1

    # Repetir el mismo PATCH no agrega entradas duplicadas a la bitácora
    r_noop = cli.patch(
        "/api/bots/control/compras/",
        {"habilitado": False, "parametros": {"auto_envio_min": 25}},
        format="json",
    )
    assert r_noop.status_code == 200
    assert len(r_noop.data["bitacora"]) == 1

    # Destinos y bitácora general
    r_dest = cli.get("/api/bots/destinos/")
    assert r_dest.status_code == 200
    assert r_dest.data["bots_en_linea"] == 1
    assert r_dest.data["gemini"]["estado"] == "sin_clave"

    r_del = cli.delete(f"/api/bots/usuarios/{uid}/")
    assert r_del.status_code == 204

    r_bit = cli.get("/api/bots/bitacora/?limite=invalido")
    assert r_bit.status_code == 200
    acciones = [x["accion"] for x in r_bit.data["items"]]
    assert {"alta", "actualizar", "baja"}.issubset(set(acciones))
    assert BotBitacora.objects.filter(id_empresa=empresa_a).count() == 4


def test_validaciones_rechazan_entradas_invalidas(empresa_a, user_a):
    user_a.is_staff = True
    user_a.save(update_fields=["is_staff"])
    cli = APIClient()
    cli.force_authenticate(user=user_a)

    assert cli.get("/api/bots/control/CODIGO INVALIDO!/").status_code == 422
    assert (
        cli.patch(
            "/api/bots/control/pedidos/",
            {"parametros": {"auto_envio_min": 0}},
            format="json",
        ).status_code
        == 422
    )
    assert (
        cli.patch(
            "/api/bots/control/pedidos/",
            {"parametros": {"desconocido": 1}},
            format="json",
        ).status_code
        == 422
    )
    assert (
        cli.patch(
            "/api/bots/control/pedidos/",
            {"chats": {"grupo": 0}},
            format="json",
        ).status_code
        == 422
    )
    assert (
        cli.patch(
            "/api/bots/control/pedidos/",
            {"url_panel": "ftp://malo"},
            format="json",
        ).status_code
        == 422
    )
    assert (
        cli.patch("/api/bots/control/pedidos/", {}, format="json").status_code == 422
    )
    assert (
        cli.post(
            "/api/bots/usuarios/",
            {
                "telegram_user_id": 999111,
                "usuario": str(user_a.pk),
                "bots": ["BAD CODE!"],
            },
            format="json",
        ).status_code
        == 400
    )

    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_parametros({"auto_envio_min": True})
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_parametros({"gemini_model": "x"})
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_chats({"otro": 123})
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_mensaje("x" * 281)


# ── Herramientas MCP ─────────────────────────────────────────────────────────


@pytest.mark.tenant
def test_mcp_bots_estado_y_cambio_con_aislamiento(empresa_a, empresa_b, user_a):
    tok_rw = CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="MCP Bots",
        scopes=["bots:read", "bots:write"],
        creado_por=user_a,
    )
    tok_ro = CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="MCP Solo Lectura",
        scopes=["bots:read"],
        creado_por=user_a,
    )

    estado = bots_estado_flota(str(tok_rw.token), str(empresa_a.id_empresa))
    assert len(estado["bots"]) >= 5
    assert "omni" in estado["destinos"]

    actualizado = bots_cambiar_habilitado(
        str(tok_rw.token),
        str(empresa_a.id_empresa),
        "eventos",
        False,
        "Cerrado por inventario",
    )
    assert actualizado["habilitado"] is False
    assert actualizado["mensaje"] == "Cerrado por inventario"

    # Cross-tenant y falta de scope fallan con PermissionError
    with pytest.raises(PermissionError):
        bots_estado_flota(str(tok_rw.token), str(empresa_b.id_empresa))
    with pytest.raises(PermissionError):
        bots_cambiar_habilitado(
            str(tok_ro.token), str(empresa_a.id_empresa), "eventos", True
        )
    with pytest.raises(PermissionError):
        bots_estado_flota("token-invalido", str(empresa_a.id_empresa))


def test_casos_borde_modelos_permisos_y_destinos(empresa_a, empresa_b, user_a, user_b):
    from django.contrib.auth.models import AnonymousUser

    from apps.core.viewsets import get_empresas_visible

    assert list(get_empresas_visible(AnonymousUser())) == []

    # Peticiones anónimas -> 401 en todos los endpoints nuevos
    anon = APIClient()
    assert anon.post("/api/bots/heartbeat/", {"bot": "pedidos"}, format="json").status_code == 401
    assert anon.get("/api/bots/control/").status_code == 401
    assert anon.get("/api/bots/destinos/").status_code == 401

    # Usuario autenticado sin empresa -> 403 en endpoints de control
    huerfano = UsuariosFactory(empresa=None)
    huerfano.is_staff = True
    huerfano.save(update_fields=["is_staff"])
    cli_h = APIClient()
    cli_h.force_authenticate(user=huerfano)
    assert cli_h.get("/api/bots/control/").status_code == 403

    # Latido con código inválido en serializer -> 400
    user_a.is_staff = True
    user_a.is_superuser = True
    user_a.save(update_fields=["is_staff", "is_superuser"])
    cli_a = APIClient()
    cli_a.force_authenticate(user=user_a)
    assert (
        cli_a.post("/api/bots/heartbeat/", {"bot": "MALO!"}, format="json").status_code
        == 400
    )

    # Estados variados en resumen_destinos (ok, error, desactivado) + detalle de bot sin kinds
    ctrl_svc.registrar_latido(
        empresa=empresa_a,
        codigo="pedidos",
        estado={"omni": "ok", "cxc": "desactivado", "gemini": "ok"},
    )
    ctrl_svc.registrar_latido(
        empresa=empresa_a,
        codigo="tareas",
        estado={"omni": "error", "cxc": "desactivado", "gemini": "error"},
    )
    dest = ctrl_svc.resumen_destinos(empresa_a)
    assert dest["omni"]["estado"] == "error"
    assert dest["cxc"]["estado"] == "desactivado"
    assert dest["gemini"]["estado"] == "error"

    det_tareas = cli_a.get("/api/bots/control/tareas/").data
    assert det_tareas["ingestas_recientes"] == []

    # Actualizar un BotRegistro ya existente modificando todos sus campos y limpiando url_panel
    r_upd = cli_a.patch(
        "/api/bots/control/pedidos/",
        {
            "habilitado": False,
            "nombre": "Ventas Principal",
            "parametros": {"auto_envio_min": 15},
            "chats": {"respaldo": -999},
            "url_panel": "",
            "mensaje": "Aviso",
        },
        format="json",
    )
    assert r_upd.status_code == 200
    assert r_upd.data["nombre"] == "Ventas Principal"

    # Cross-tenant usuario en PATCH de BotUsuario -> 400 por TenantFKScopeMixin,
    # y 403 en perform_update si es_superusuario_omni=True intenta cruzar empresa
    bu = BotUsuario.objects.create(
        id_empresa=empresa_a, telegram_user_id=321321, usuario=user_a, nombre="Op"
    )
    assert (
        cli_a.patch(
            f"/api/bots/usuarios/{bu.pk}/",
            {"usuario": str(user_b.pk)},
            format="json",
        ).status_code
        == 400
    )
    user_a.es_superusuario_omni = True
    user_a.save(update_fields=["es_superusuario_omni"])
    assert (
        cli_a.patch(
            f"/api/bots/usuarios/{bu.pk}/",
            {"usuario": str(user_b.pk)},
            format="json",
        ).status_code
        == 403
    )

    # MCP cross-empresa en bots_cambiar_habilitado -> PermissionError
    tok_write = CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="MCP Write",
        scopes=["bots:write"],
        creado_por=user_a,
    )
    with pytest.raises(PermissionError):
        bots_cambiar_habilitado(str(tok_write.token), str(empresa_b.pk), "pedidos", False)

    # Representación __str__ de modelos nuevos y bordes de validadores
    reg = BotRegistro.objects.get(id_empresa=empresa_a, codigo="pedidos")
    diario = BotLatidoDiario.objects.filter(id_empresa=empresa_a, codigo="pedidos").first()
    bit = BotBitacora.objects.filter(id_empresa=empresa_a).first()
    assert "pedidos" in str(reg)
    assert "pedidos" in str(diario)
    assert "actualizar" in str(bit)
    assert ctrl_svc.sanear_estado("no-dict")["outbox_pendientes"] == 0
    assert ctrl_svc.sanear_estado({"outbox_pendientes": True, "mensajes_hoy": "mal"})["mensajes_hoy"] == 0
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_codigo_bot(123)
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_lista_bots("no-lista")
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_parametros({"auto_envio_min": "abc"})
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_parametros("no-dict")
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_chats("no-dict")
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_url_panel(123)
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_mensaje(123)
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.actualizar_bot(empresa=empresa_a, codigo="pedidos", cambios="mal", actor="x")
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.actualizar_bot(
            empresa=empresa_a, codigo="pedidos", cambios={"habilitado": "si"}, actor="x"
        )
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.actualizar_bot(
            empresa=empresa_a, codigo="pedidos", cambios={"nombre": "  "}, actor="x"
        )


@pytest.mark.tenant
def test_endurecimiento_seguridad_tokens_secretos_y_unicidad(empresa_a, user_a):
    from django.contrib.admin.sites import AdminSite

    from apps.bots_ingest.admin import BotBitacoraAdmin
    from apps.bots_ingest.services.ingesta import resolver_bot_usuario

    user_a.is_staff = True
    user_a.save(update_fields=["is_staff"])
    cli = APIClient()
    cli.force_authenticate(user=user_a)

    # 1. Unicidad limpia (400 en vez de 500) y campos de solo lectura en BotUsuario
    otro = UsuariosFactory(empresa=empresa_a)
    secreto_sk = "sk-" + ("a" * 28)
    r1 = cli.post(
        "/api/bots/usuarios/",
        {
            "telegram_user_id": 707070,
            "usuario": str(user_a.pk),
            "nombre": f"Operador {secreto_sk}",
        },
        format="json",
    )
    assert r1.status_code == 201, r1.data
    assert secreto_sk not in r1.data["nombre"]
    assert "[oculto]" in r1.data["nombre"]

    r_dup_create = cli.post(
        "/api/bots/usuarios/",
        {
            "telegram_user_id": 707070,
            "usuario": str(otro.pk),
            "nombre": "Duplicado",
        },
        format="json",
    )
    assert r_dup_create.status_code == 400
    assert "telegram_user_id" in r_dup_create.data

    r2 = cli.post(
        "/api/bots/usuarios/",
        {
            "telegram_user_id": 707071,
            "usuario": str(otro.pk),
            "nombre": "Segundo",
            "activo": False,
        },
        format="json",
    )
    assert r2.status_code == 201
    # activo=False enviado en payload es ignorado por read_only_fields
    assert BotUsuario.objects.get(pk=r2.data["id_bot_usuario"]).activo is True

    r_dup_patch = cli.patch(
        f"/api/bots/usuarios/{r2.data['id_bot_usuario']}/",
        {"telegram_user_id": 707070},
        format="json",
    )
    assert r_dup_patch.status_code == 400
    assert "telegram_user_id" in r_dup_patch.data

    # Tras baja lógica (soft-delete), el mismo telegram_user_id puede volver a darse de alta
    assert cli.delete(f"/api/bots/usuarios/{r2.data['id_bot_usuario']}/").status_code == 204
    r2_re = cli.post(
        "/api/bots/usuarios/",
        {
            "telegram_user_id": 707071,
            "usuario": str(otro.pk),
            "nombre": "Reincorporado",
        },
        format="json",
    )
    assert r2_re.status_code == 201, r2_re.data

    from apps.bots_ingest.services.ingesta import UsuarioBotDesconocido

    # 2. resolver_bot_usuario rechaza bool y desbordamiento BigInteger
    with pytest.raises(UsuarioBotDesconocido):
        resolver_bot_usuario(user_a, True)
    with pytest.raises(UsuarioBotDesconocido):
        resolver_bot_usuario(user_a, 0)
    with pytest.raises(UsuarioBotDesconocido):
        resolver_bot_usuario(user_a, 2**64)

    # 3. Rechazo de secretos/credenciales en url_panel y gemini_model + limpieza de bytes nulos
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_parametros({"gemini_model": "AIza" + "Sy" + ("9" * 33)})
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_url_panel("https://usuario:secreto@panel.ejemplo.com/bots")
    with pytest.raises(DatoControlInvalido):
        ctrl_svc.validar_url_panel(f"https://panel.ejemplo.com/bots?k={secreto_sk}")

    cfg_nulos = ctrl_svc.registrar_latido(
        empresa=empresa_a,
        codigo="pedidos\x00",
        nombre="Ventas\x00Bot",
        version="1.0\x00",
        estado={"ultimo_error": "fallo\x00grave"},
    )
    assert cfg_nulos["habilitado"] is True
    reg_nulos = BotRegistro.objects.get(id_empresa=empresa_a, codigo="pedidos")
    assert "\x00" not in reg_nulos.nombre
    assert "\x00" not in reg_nulos.version
    assert "\x00" not in reg_nulos.estado["ultimo_error"]
    r_bit_nulo = cli.get("/api/bots/bitacora/?entidad=bot:pedidos%00")
    assert r_bit_nulo.status_code == 200

    # 4. MCP limpia mensaje con cadena vacía y rechaza token revocado o empresa inactiva
    tok = CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="MCP Hardening",
        scopes=["bots:read", "bots:write", "bots:heartbeat"],
        creado_por=user_a,
    )
    bots_cambiar_habilitado(
        str(tok.token), str(empresa_a.pk), "pedidos", False, "En mantenimiento"
    )
    limpio = bots_cambiar_habilitado(
        str(tok.token), str(empresa_a.pk), "pedidos", True, ""
    )
    assert limpio["habilitado"] is True
    assert limpio["mensaje"] == ""

    empresa_a.activo = False
    empresa_a.save(update_fields=["activo"])
    with pytest.raises(PermissionError):
        bots_estado_flota(str(tok.token), str(empresa_a.pk))
    with pytest.raises(PermissionError):
        bots_cambiar_habilitado(str(tok.token), str(empresa_a.pk), "pedidos", False)
    cli_tok = APIClient()
    cli_tok.credentials(HTTP_X_CAPABILITY_TOKEN=str(tok.token))
    assert (
        cli_tok.post("/api/bots/heartbeat/", {"bot": "pedidos"}, format="json").status_code
        == 401
    )

    empresa_a.activo = True
    empresa_a.save(update_fields=["activo"])
    tok.activo = False
    tok.save(update_fields=["activo"])
    with pytest.raises(PermissionError):
        bots_estado_flota(str(tok.token), str(empresa_a.pk))
    assert (
        cli_tok.post("/api/bots/heartbeat/", {"bot": "pedidos"}, format="json").status_code
        == 401
    )

    # 5. BotBitacoraAdmin es estrictamente de solo lectura
    adm = BotBitacoraAdmin(BotBitacora, AdminSite())
    assert adm.has_add_permission(None) is False
    assert adm.has_change_permission(None) is False
    assert adm.has_delete_permission(None) is False

