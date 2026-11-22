"""
Servicios 2FA / TOTP RFC 6238 en Python puro (Plan 05 P3-1).

Cero dependencias externas adicionales:
  - TOTP RFC 6238 / HOTP RFC 4226 con ``hmac``, ``hashlib``, ``struct``, ``base64``, ``secrets``.
  - QR vectorial SVG mediante ``reportlab.graphics.barcode.qr.QrCode`` (ya pineado).
  - Códigos de respaldo de un solo uso con ``make_password`` / ``check_password`` (PBKDF2-SHA256).
  - Token efímero pre-sesión firmado con ``django.core.signing.TimestampSigner``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import re
import secrets
import struct
import time
from typing import TYPE_CHECKING
from urllib.parse import quote, urlencode

from django.contrib.auth.hashers import check_password, make_password
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from reportlab.graphics.barcode import qr as reportlab_qr

if TYPE_CHECKING:
    from .models import ConfiguracionMFA, Usuarios

TOTP_DIGITS = 6
TOTP_PERIOD_SECONDS = 30
TOTP_WINDOW_STEPS = 1
BACKUP_CODES_COUNT = 8
MFA_CHALLENGE_TTL_SECONDS = 300
_MFA_TOKEN_SALT = "omni.core.mfa.login"
_BACKUP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_TOTP_RE = re.compile(r"^\d{6}$")


def generar_secreto_totp() -> str:
    """Genera un secreto Base32 de 160 bits sin relleno '=' (RFC 6238)."""
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _normalizar_base32(secret: str) -> bytes:
    limpio = re.sub(r"[\s-]+", "", (secret or "").strip().upper())
    if not limpio:
        raise ValueError("El secreto TOTP no puede estar vacío.")
    pad = (-len(limpio)) % 8
    return base64.b32decode(limpio + ("=" * pad), casefold=True)


def calcular_totp(
    secret: str,
    paso: int | None = None,
    *,
    digits: int = TOTP_DIGITS,
    period: int = TOTP_PERIOD_SECONDS,
    ahora: float | None = None,
) -> str:
    """Calcula el código TOTP (HMAC-SHA1) para un contador ``paso``."""
    key = _normalizar_base32(secret)
    if paso is None:
        ts = time.time() if ahora is None else ahora
        paso = int(ts // period)
    msg = struct.pack(">Q", paso)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10**digits)).zfill(digits)


def verificar_totp(
    secret: str,
    codigo: str,
    *,
    ultimo_paso: int | None = None,
    ventana: int = TOTP_WINDOW_STEPS,
    period: int = TOTP_PERIOD_SECONDS,
    ahora: float | None = None,
) -> tuple[bool, int | None]:
    """
    Valida un código TOTP de 6 dígitos en ventana ``±ventana`` pasos.

    Retorna ``(True, paso_aceptado)`` o ``(False, None)``. Rechaza códigos ya
    utilizados (``paso <= ultimo_paso``) para impedir replay dentro de la ventana.
    """
    candidato = re.sub(r"\s+", "", str(codigo or ""))
    if not _TOTP_RE.match(candidato):
        return False, None
    try:
        _normalizar_base32(secret)
    except ValueError:
        return False, None

    ts = time.time() if ahora is None else ahora
    paso_actual = int(ts // period)

    paso_matched: int | None = None
    for delta in range(-ventana, ventana + 1):
        paso = paso_actual + delta
        if paso < 0:
            continue
        esperado = calcular_totp(secret, paso=paso)
        if hmac.compare_digest(candidato, esperado):
            paso_matched = paso
            break

    if paso_matched is None:
        return False, None
    if ultimo_paso is not None and paso_matched <= ultimo_paso:
        return False, None
    return True, paso_matched


def construir_otpauth_uri(secret: str, username: str, issuer: str = "Omni ERP") -> str:
    """Construye el URI estándar ``otpauth://totp/...``."""
    etiqueta = f"{issuer}:{username}"
    params = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": TOTP_DIGITS,
            "period": TOTP_PERIOD_SECONDS,
        }
    )
    return f"otpauth://totp/{quote(etiqueta)}?{params}"


def generar_qr_svg_mfa(otpauth_uri: str, *, scale: int = 6, border: int = 2) -> str:
    """Renderiza el código QR de ``otpauth_uri`` como SVG vectorial limpio."""
    qr_widget = reportlab_qr.QrCode(otpauth_uri, qrLevel="M")
    qr_widget.qr.make()
    matriz = [[bool(celda) for celda in fila] for fila in qr_widget.qr.modules]
    modulos = len(matriz)
    lado = (modulos + 2 * border) * scale

    comandos: list[str] = []
    for fila_idx, fila in enumerate(matriz):
        y = (fila_idx + border) * scale
        col = 0
        for es_oscuro, grupo in itertools.groupby(fila):
            largo = sum(1 for _ in grupo)
            if es_oscuro:
                x = (col + border) * scale
                ancho = largo * scale
                comandos.append(f"M{x} {y}h{ancho}v{scale}h-{ancho}z")
            col += largo

    path_data = "".join(comandos)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lado} {lado}" '
        f'width="{lado}" height="{lado}" shape-rendering="crispEdges">'
        f'<rect width="100%" height="100%" fill="#ffffff"/>'
        f'<path d="{path_data}" fill="#000000"/>'
        f"</svg>"
    )


def generar_codigos_respaldo(cantidad: int = BACKUP_CODES_COUNT) -> tuple[list[str], list[str]]:
    """Genera ``cantidad`` códigos ``XXXX-XXXX`` y sus hashes PBKDF2-SHA256."""
    planos: list[str] = []
    hashes: list[str] = []
    for _ in range(cantidad):
        parte_a = "".join(secrets.choice(_BACKUP_ALPHABET) for _ in range(4))
        parte_b = "".join(secrets.choice(_BACKUP_ALPHABET) for _ in range(4))
        codigo = f"{parte_a}-{parte_b}"
        planos.append(codigo)
        hashes.append(make_password(codigo))
    return planos, hashes


def _normalizar_codigo_respaldo(codigo: str) -> str:
    limpio = re.sub(r"[\s-]+", "", str(codigo or "")).upper()
    if len(limpio) == 8:
        return f"{limpio[:4]}-{limpio[4:]}"
    return str(codigo or "").strip().upper()


def consumir_codigo_respaldo(config: ConfiguracionMFA, codigo: str) -> bool:
    """Verifica y consume (un solo uso) un código de respaldo de ``config``."""
    hashes = list(config.codigos_respaldo or [])
    if not hashes:
        return False
    normalizado = _normalizar_codigo_respaldo(codigo)
    for idx, hashed in enumerate(hashes):
        if check_password(normalizado, str(hashed)):
            restantes = hashes[:idx] + hashes[idx + 1 :]
            config.codigos_respaldo = restantes
            config.save(update_fields=["codigos_respaldo", "fecha_actualizacion"])
            return True
    return False


def emitir_mfa_token(user_id: object) -> str:
    """Emite un token firmado efímero para completar el segundo factor en login."""
    signer = TimestampSigner(salt=_MFA_TOKEN_SALT)
    return signer.sign(str(user_id))


def validar_mfa_token(token: str, *, max_age: int = MFA_CHALLENGE_TTL_SECONDS) -> str | None:
    """Valida el token MFA efímero y retorna el ``user_id`` si sigue vigente."""
    if not token or not isinstance(token, str):
        return None
    signer = TimestampSigner(salt=_MFA_TOKEN_SALT)
    try:
        return signer.unsign(token.strip(), max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def usuario_tiene_mfa_activo(user: Usuarios) -> bool:
    """True si el usuario ya confirmó y habilitó su configuración TOTP."""
    config = getattr(user, "configuracion_mfa", None)
    if config is None:
        from .models import ConfiguracionMFA

        config = ConfiguracionMFA.objects.filter(usuario=user, habilitado=True).first()
    return bool(config and config.habilitado and config.secret)


def usuario_requiere_configurar_mfa(user: Usuarios) -> bool:
    """True si alguna empresa del usuario exige 2FA para administradores."""
    es_admin = bool(
        getattr(user, "es_superusuario_omni", False)
        or getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
    )
    if not es_admin or not hasattr(user, "empresas"):
        return False
    return user.empresas.filter(requerir_mfa_admins=True, activo=True).exists()
