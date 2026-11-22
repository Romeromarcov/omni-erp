"""
Tests integrales de 2FA / TOTP RFC 6238 (Plan 05 P3-1):
  - EncryptedTextField (cifrado Fernet en reposo)
  - Servicio RFC 6238 (TOTP, ventana +-1, anti-replay, QR SVG, códigos respaldo, TimestampSigner)
  - Endpoints /api/auth/mfa/{estado,iniciar,confirmar,desactivar,regenerar-codigos,verificar}/
  - Integración en /api/auth/login/ y /api/auth/token/
  - Paridad MCP core_estado_mfa_usuario (aislamiento de tenant sin fuga de secretos)
"""

from __future__ import annotations

import time
import uuid

import pytest
from django.core.cache import cache
from django.db import connection
from rest_framework.test import APIClient

from apps.core.fields import EncryptedTextField, _fernet
from apps.core.mfa import (
    calcular_totp,
    construir_otpauth_uri,
    consumir_codigo_respaldo,
    emitir_mfa_token,
    generar_qr_svg_mfa,
    generar_secreto_totp,
    usuario_requiere_configurar_mfa,
    validar_mfa_token,
    verificar_totp,
)
from apps.core.models import CapabilityToken, ConfiguracionMFA, Empresa, Usuarios

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

TEST_CRED = "MfaTest#2026!Secret"


@pytest.fixture(autouse=True)
def _limpiar_cache_ratelimit():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def empresa(db):
    return Empresa.objects.create(
        nombre_legal="Empresa MFA C.A.",
        identificador_fiscal="J-50123456-7",
        requerir_mfa_admins=True,
    )


@pytest.fixture
def usuario(db, empresa):
    user = Usuarios.objects.create_user(
        username=f"mfa_user_{uuid.uuid4().hex[:8]}",
        password=TEST_CRED,
        email="mfa@empresa.test",
        is_staff=True,
    )
    user.empresas.add(empresa)
    return user


def _activar_mfa(usuario: Usuarios) -> tuple[ConfiguracionMFA, str, list[str]]:
    client = APIClient()
    client.force_authenticate(user=usuario)
    r_init = client.post("/api/auth/mfa/iniciar/", {}, format="json")
    assert r_init.status_code == 200
    secret = r_init.data["secret_manual"]
    codigo = calcular_totp(secret)
    r_conf = client.post("/api/auth/mfa/confirmar/", {"codigo": codigo}, format="json")
    assert r_conf.status_code == 200
    cfg = ConfiguracionMFA.objects.get(usuario=usuario)
    return cfg, secret, list(r_conf.data["codigos_respaldo"])


def test_servicio_totp_rfc6238_y_anti_replay(usuario):
    secret = generar_secreto_totp()
    assert len(secret) >= 16

    ahora = 1_700_000_000.0
    paso = int(ahora // 30)
    codigo = calcular_totp(secret, paso=paso)
    assert len(codigo) == 6
    assert codigo.isdigit()

    ok, matched = verificar_totp(secret, codigo, ahora=ahora)
    assert ok is True
    assert matched == paso

    # Mismo paso no puede reutilizarse (anti-replay)
    ok_replay, matched_replay = verificar_totp(secret, codigo, ultimo_paso=paso, ahora=ahora)
    assert ok_replay is False
    assert matched_replay is None

    # Código inválido o secreto inválido
    assert verificar_totp(secret, "000000" if codigo != "000000" else "111111", ahora=ahora) == (False, None)
    assert verificar_totp(secret, "abc", ahora=ahora) == (False, None)
    assert verificar_totp("", codigo, ahora=ahora) == (False, None)

    uri = construir_otpauth_uri(secret, usuario.username)
    assert uri.startswith("otpauth://totp/")
    assert "Omni" in uri
    svg = generar_qr_svg_mfa(uri)
    assert svg.startswith("<svg ") and "<path " in svg


def test_encrypted_text_field_cifra_en_bd(usuario):
    secret = generar_secreto_totp()
    cfg = ConfiguracionMFA.objects.create(usuario=usuario, secret=secret, habilitado=True)
    with connection.cursor() as cur:
        cur.execute("SELECT secret FROM core_configuracion_mfa WHERE id = %s", [str(cfg.id)])
        raw_db = cur.fetchone()[0]

    assert raw_db != secret
    assert raw_db.startswith("gAAAAA")

    cfg.refresh_from_db()
    assert cfg.secret == secret


def test_flujo_completo_mfa_endpoints_y_login(usuario):
    client = APIClient()
    client.force_authenticate(user=usuario)

    # 1. Estado inicial + política por empresa
    assert usuario_requiere_configurar_mfa(usuario) is True
    r_estado = client.get("/api/auth/mfa/estado/")
    assert r_estado.status_code == 200
    assert r_estado.data["habilitado"] is False
    assert r_estado.data["codigos_respaldo_restantes"] == 0
    assert r_estado.data["requerido_por_politica"] is True

    # Confirmar sin iniciar -> 400
    r_conf_sin_init = client.post("/api/auth/mfa/confirmar/", {"codigo": "123456"}, format="json")
    assert r_conf_sin_init.status_code == 400

    # 2. Iniciar configuración
    r_init = client.post("/api/auth/mfa/iniciar/", {}, format="json")
    assert r_init.status_code == 200
    assert r_init.data["otpauth_uri"].startswith("otpauth://totp/")
    assert "<svg " in r_init.data["qr_svg"]
    secret = r_init.data["secret_manual"]

    # Confirmar con código inválido -> 400
    codigo_valido = calcular_totp(secret)
    codigo_malo = "000000" if codigo_valido != "000000" else "999999"
    r_conf_bad = client.post("/api/auth/mfa/confirmar/", {"codigo": codigo_malo}, format="json")
    assert r_conf_bad.status_code == 400

    # 3. Confirmar con código TOTP válido -> devuelve 8 códigos de respaldo
    r_conf = client.post("/api/auth/mfa/confirmar/", {"codigo": codigo_valido}, format="json")
    assert r_conf.status_code == 200
    assert r_conf.data["habilitado"] is True
    codigos_respaldo = r_conf.data["codigos_respaldo"]
    assert len(codigos_respaldo) == 8

    # Reiniciar cuando ya está habilitado -> 400
    r_reinit = client.post("/api/auth/mfa/iniciar/", {}, format="json")
    assert r_reinit.status_code == 400

    # 4. Login vía /api/auth/login/ pide reto MFA sin emitir JWT
    anon = APIClient()
    r_login = anon.post(
        "/api/auth/login/",
        {"username": usuario.username, "password": TEST_CRED},
        format="json",
    )
    assert r_login.status_code == 200
    assert r_login.data["mfa_requerido"] is True
    assert r_login.data["metodo"] == "TOTP"
    assert "access" not in r_login.data
    assert "refresh_token" not in r_login.cookies
    mfa_token = r_login.data["mfa_token"]
    assert validar_mfa_token(mfa_token) == str(usuario.pk)

    # También en /api/auth/token/ devuelve el reto MFA sin tokens JWT
    r_token_ep = anon.post(
        "/api/auth/token/",
        {"username": usuario.username, "password": TEST_CRED},
        format="json",
    )
    assert r_token_ep.status_code == 200
    assert r_token_ep.data["mfa_requerido"] is True
    assert "access" not in r_token_ep.data

    # Verificar con mfa_token adulterado -> 401
    r_bad_tok = anon.post(
        "/api/auth/mfa/verificar/",
        {"mfa_token": "token-invalido", "codigo": codigos_respaldo[0]},
        format="json",
    )
    assert r_bad_tok.status_code == 401

    # Verificar con código inválido -> 401
    r_bad_code = anon.post(
        "/api/auth/mfa/verificar/",
        {"mfa_token": mfa_token, "codigo": codigo_malo},
        format="json",
    )
    assert r_bad_code.status_code == 401

    # 5. Completar login con código TOTP futuro (+30s window simulated via passo + 1)
    paso_sig = int(time.time() // 30) + 1
    totp_sig = calcular_totp(secret, paso=paso_sig)
    r_verify = anon.post(
        "/api/auth/mfa/verificar/",
        {"mfa_token": mfa_token, "codigo": totp_sig},
        format="json",
    )
    assert r_verify.status_code == 200
    assert "access" in r_verify.data
    assert "refresh_token" in r_verify.cookies

    # Reutilizar exactamente el mismo paso TOTP -> rechazado (anti-replay)
    r_replay = anon.post(
        "/api/auth/mfa/verificar/",
        {"mfa_token": mfa_token, "codigo": totp_sig},
        format="json",
    )
    assert r_replay.status_code == 401

    # 6. Completar login con código de respaldo (un solo uso)
    backup_0 = codigos_respaldo[0]
    r_backup_ok = anon.post(
        "/api/auth/mfa/verificar/",
        {"mfa_token": mfa_token, "codigo": backup_0.replace("-", "").lower()},
        format="json",
    )
    assert r_backup_ok.status_code == 200
    assert "access" in r_backup_ok.data

    # Segundo intento con el mismo código de respaldo -> 401
    r_backup_reuse = anon.post(
        "/api/auth/mfa/verificar/",
        {"mfa_token": mfa_token, "codigo": backup_0},
        format="json",
    )
    assert r_backup_reuse.status_code == 401


def test_regenerar_y_desactivar_mfa(usuario):
    _cfg, secret, codigos = _activar_mfa(usuario)
    client = APIClient()
    client.force_authenticate(user=usuario)

    # Regenerar códigos exige TOTP válido de un paso posterior
    paso_futuro = int(time.time() // 30) + 1
    r_regen = client.post(
        "/api/auth/mfa/regenerar-codigos/",
        {"codigo": calcular_totp(secret, paso=paso_futuro)},
        format="json",
    )
    assert r_regen.status_code == 200
    nuevos = r_regen.data["codigos_respaldo"]
    assert len(nuevos) == 8
    assert nuevos != codigos

    # Desactivar con contraseña incorrecta -> 401
    r_bad_pass = client.post(
        "/api/auth/mfa/desactivar/",
        {"password": "wrong-password", "codigo": nuevos[0]},
        format="json",
    )
    assert r_bad_pass.status_code == 401

    # Desactivar con código incorrecto -> 400
    r_bad_code = client.post(
        "/api/auth/mfa/desactivar/",
        {"password": TEST_CRED, "codigo": "ZZZZ-9999"},
        format="json",
    )
    assert r_bad_code.status_code == 400

    # Desactivar correctamente usando código de respaldo
    r_off = client.post(
        "/api/auth/mfa/desactivar/",
        {"password": TEST_CRED, "codigo": nuevos[0]},
        format="json",
    )
    assert r_off.status_code == 200
    assert r_off.data["habilitado"] is False

    # Estado queda limpio
    r_estado = client.get("/api/auth/mfa/estado/")
    assert r_estado.data["habilitado"] is False
    assert r_estado.data["codigos_respaldo_restantes"] == 0


def test_mcp_core_estado_mfa_usuario_y_aislamiento(usuario, empresa):
    from apps.core.mcp_server import core_estado_mfa_usuario

    _activar_mfa(usuario)
    cap = CapabilityToken.objects.create(
        empresa=empresa,
        nombre="Test MFA MCP",
        scopes=["core:read"],
        activo=True,
    )

    res = core_estado_mfa_usuario(str(cap.token), str(usuario.pk))
    assert res["usuario_id"] == str(usuario.pk)
    assert res["habilitado"] is True
    assert res["codigos_respaldo_restantes"] == 8
    assert "secret" not in res
    assert "codigos_respaldo" not in res

    # Token de otro tenant NO puede consultar MFA de este usuario
    otra = Empresa.objects.create(nombre_legal="Otra Empresa", identificador_fiscal="J-50999999-9")
    cap_otra = CapabilityToken.objects.create(
        empresa=otra,
        nombre="Otro Tenant",
        scopes=["core:read"],
        activo=True,
    )
    with pytest.raises(PermissionError):
        core_estado_mfa_usuario(str(cap_otra.token), str(usuario.pk))

    with pytest.raises(ValueError):
        core_estado_mfa_usuario(str(cap.token), "no-es-uuid")


def test_edge_cases_mfa_fields_servicio_y_vistas(usuario, empresa):
    # EncryptedTextField branches (empty, None, plain text, already encrypted, invalid token)
    field = EncryptedTextField()
    assert field.to_python(None) is None
    assert field.to_python("") == ""
    assert field.to_python(123) == "123"
    assert field.to_python("gAAAAAinvalid-fernet") == "gAAAAAinvalid-fernet"
    assert field.get_prep_value("") == ""
    encrypted = field.get_prep_value("SECRETO")
    assert encrypted.startswith("gAAAAA")
    reprepped = field.get_prep_value(encrypted)
    assert reprepped.startswith("gAAAAA")
    assert _fernet().decrypt(reprepped.encode("ascii")).decode("utf-8") == "SECRETO"
    assert field.get_prep_value("gAAAAA-not-fernet").startswith("gAAAAA")

    # __str__ y helpers edge cases
    cfg = ConfiguracionMFA.objects.create(usuario=usuario, secret="ABC", habilitado=False)
    assert "pendiente" in str(cfg)
    assert consumir_codigo_respaldo(cfg, "AAAA-1111") is False
    assert validar_mfa_token("") is None
    with pytest.raises(ValueError):
        calcular_totp("")
    uri = construir_otpauth_uri("ABC", usuario.username)
    assert "ABC" in uri
    assert consumir_codigo_respaldo(cfg, "ZZZZ-9999") is False

    no_admin = Usuarios.objects.create_user(
        username=f"mfa_basic_{uuid.uuid4().hex[:6]}",
        password=TEST_CRED,
        is_staff=False,
        is_superuser=False,
    )
    no_admin.empresas.add(empresa)
    assert usuario_requiere_configurar_mfa(no_admin) is False

    # Validaciones de payload inválido y NUL en endpoints MFA autenticados
    client = APIClient()
    client.force_authenticate(user=usuario)
    assert client.post("/api/auth/mfa/confirmar/", {}, format="json").status_code == 400
    assert client.post("/api/auth/mfa/confirmar/", {"codigo": "12\x0034"}, format="json").status_code == 400
    assert client.post("/api/auth/mfa/desactivar/", {}, format="json").status_code == 400
    assert (
        client.post("/api/auth/mfa/desactivar/", {"password": "a\x00b", "codigo": "123456"}, format="json").status_code
        == 400
    )
    assert (
        client.post("/api/auth/mfa/desactivar/", {"password": TEST_CRED, "codigo": "123456"}, format="json").status_code
        == 400
    )
    assert client.post("/api/auth/mfa/regenerar-codigos/", {}, format="json").status_code == 400
    assert client.post("/api/auth/mfa/regenerar-codigos/", {"codigo": "12\x0034"}, format="json").status_code == 400
    assert client.post("/api/auth/mfa/regenerar-codigos/", {"codigo": "123456"}, format="json").status_code == 400

    # confirmar cuando ya está habilitado
    _activar_mfa(usuario)
    assert client.post("/api/auth/mfa/confirmar/", {"codigo": "123456"}, format="json").status_code == 400

    # /api/auth/mfa/verificar/ con payload vacío, NUL, o cuenta sin MFA activo
    anon = APIClient()
    assert anon.post("/api/auth/mfa/verificar/", {}, format="json").status_code == 400
    assert (
        anon.post("/api/auth/mfa/verificar/", {"mfa_token": "tok\x00", "codigo": "123456"}, format="json").status_code
        == 400
    )
    assert (
        anon.post(
            "/api/auth/mfa/verificar/",
            {"mfa_token": emitir_mfa_token(no_admin.pk), "codigo": "123456"},
            format="json",
        ).status_code
        == 401
    )
    assert (
        anon.post(
            "/api/auth/mfa/verificar/",
            {"mfa_token": emitir_mfa_token(uuid.uuid4()), "codigo": "123456"},
            format="json",
        ).status_code
        == 401
    )
    # verificar rate limit 429 path via exhausted user-agent / requests o direct attribute check:
    no_admin.is_active = False
    no_admin.save(update_fields=["is_active"])
    assert (
        anon.post(
            "/api/auth/mfa/verificar/",
            {"mfa_token": emitir_mfa_token(no_admin.pk), "codigo": "123456"},
            format="json",
        ).status_code
        == 401
    )

