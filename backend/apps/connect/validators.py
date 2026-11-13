"""Validadores y utilidades de Omni Connect."""

import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

# Slugs que colisionarían con rutas del sistema o serían engañosos en una URL
# pública corta (omni.link/<slug>). Se aplican también como CheckConstraint.
SLUGS_RESERVADOS = frozenset(
    {
        "admin", "api", "static", "media", "login", "logout", "registro",
        "soporte", "ayuda", "omni", "connect", "perfil", "tarjeta", "www",
    }
)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$")
_UID_RE = re.compile(r"^[0-9A-F]{8,20}$")
_TELEFONO_RE = re.compile(r"^\+?[0-9]{7,15}$")
_URL_RE = re.compile(r"^https?://[^\s]{3,480}$", re.IGNORECASE)

# Botones del perfil público: tipo -> clase de valor permitida. Allowlist
# estricta: el perfil se sirve sin login, así que jamás se aceptan esquemas
# como ``javascript:`` o ``data:``.
BOTONES_URL = frozenset({"web", "instagram", "catalogo", "pago", "ubicacion"})
BOTONES_TELEFONO = frozenset({"whatsapp", "telefono"})
BOTONES_CORREO = frozenset({"correo"})
BOTONES_TIPOS = BOTONES_URL | BOTONES_TELEFONO | BOTONES_CORREO
BOTONES_MAX = 30


def normalizar_slug(value: str) -> str:
    """Minúsculas y sin espacios en los extremos (``' Juan-Perez '`` → ``'juan-perez'``)."""
    return (value or "").strip().lower()


def validar_slug_perfil(value: str) -> None:
    """3–60 caracteres, minúsculas/dígitos/guiones, sin extremos con guion."""
    if not _SLUG_RE.match(value or ""):
        raise ValidationError(
            "El slug debe tener 3–60 caracteres: minúsculas, números y guiones "
            "(sin guion al inicio ni al final)."
        )
    if "--" in value:
        raise ValidationError("El slug no puede contener guiones consecutivos.")
    if value in SLUGS_RESERVADOS:
        raise ValidationError("Ese slug está reservado.")


def normalizar_uid_chip(value: str) -> str:
    """UID en hex mayúsculas, sin separadores (``04:a2:..`` → ``04A2..``)."""
    return re.sub(r"[\s:\-]", "", value or "").upper()


def validar_uid_chip(value: str) -> None:
    """NTAG213/215 usan 7 bytes (14 hex); se aceptan 4–10 bytes."""
    if not _UID_RE.match(value or ""):
        raise ValidationError("UID de chip inválido: se esperan 8–20 dígitos hexadecimales.")


def validar_botones(value) -> None:
    """Estructura y valores de ``Perfil.botones`` (lista de ``{tipo, etiqueta, valor}``)."""
    if not isinstance(value, list):
        raise ValidationError("Los botones deben ser una lista.")
    if len(value) > BOTONES_MAX:
        raise ValidationError(f"Máximo {BOTONES_MAX} botones por perfil.")
    for i, boton in enumerate(value, start=1):
        if not isinstance(boton, dict) or set(boton) != {"tipo", "etiqueta", "valor"}:
            raise ValidationError(f"Botón {i}: debe tener exactamente tipo, etiqueta y valor.")
        tipo, etiqueta, valor = boton["tipo"], boton["etiqueta"], boton["valor"]
        if not all(isinstance(x, str) for x in (tipo, etiqueta, valor)):
            raise ValidationError(f"Botón {i}: tipo, etiqueta y valor deben ser texto.")
        if tipo not in BOTONES_TIPOS:
            raise ValidationError(f"Botón {i}: tipo '{tipo}' no permitido.")
        if not 1 <= len(etiqueta.strip()) <= 60:
            raise ValidationError(f"Botón {i}: la etiqueta debe tener entre 1 y 60 caracteres.")
        if tipo in BOTONES_URL and not _URL_RE.match(valor):
            raise ValidationError(f"Botón {i}: el valor debe ser una URL http(s).")
        if tipo in BOTONES_TELEFONO and not _TELEFONO_RE.match(valor):
            raise ValidationError(f"Botón {i}: el valor debe ser un teléfono (7–15 dígitos, + opcional).")
        if tipo in BOTONES_CORREO:
            try:
                validate_email(valor)
            except ValidationError:
                raise ValidationError(f"Botón {i}: correo inválido.") from None
