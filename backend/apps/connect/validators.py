"""Validadores y utilidades de Omni Connect."""

import re

from django.core.exceptions import ValidationError

# Slugs que colisionarían con rutas del sistema o serían engañosos en una URL
# pública corta (omni.link/<slug>).
SLUGS_RESERVADOS = frozenset(
    {
        "admin", "api", "static", "media", "login", "logout", "registro",
        "soporte", "ayuda", "omni", "connect", "perfil", "tarjeta", "www",
    }
)

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,58}[a-z0-9]$")
_UID_RE = re.compile(r"^[0-9A-F]{8,20}$")


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


def validar_misma_empresa(instancia, **relacionados) -> None:
    """Rechaza FKs que apunten a registros de otra empresa (R-CODE-1).

    ``relacionados`` mapea nombre de campo → objeto relacionado (o ``None``).
    Cada objeto debe exponer ``id_empresa_id``; se compara contra el de
    ``instancia``.
    """
    errores = {}
    for campo, obj in relacionados.items():
        if obj is None:
            continue
        if getattr(obj, "id_empresa_id", None) != instancia.id_empresa_id:
            errores[campo] = "Debe pertenecer a la misma empresa."
    if errores:
        raise ValidationError(errores)
