"""
Campos de modelo personalizados de core.

H-SEC-4: ``EncryptedJSONField`` cifra el VALOR con Fernet y lo almacena como un
token opaco (string) dentro de la columna jsonb. Así un dump SQL nunca expone
credenciales en claro, sin requerir un cambio de tipo de columna (la columna
sigue siendo jsonb; solo cambia lo que contiene). A nivel ORM el campo se lee y
escribe como un dict/list normal.
"""
import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet() -> Fernet:
    """Devuelve un Fernet con la clave de settings (o derivada de SECRET_KEY en dev)."""
    key = getattr(settings, "CRYPTOGRAPHY_KEY", None)
    if not key:
        # Fallback dev/test: derivar una clave Fernet determinística del SECRET_KEY.
        # En producción se DEBE configurar CRYPTOGRAPHY_KEY explícito (ver settings).
        secret_key = settings.SECRET_KEY or ""
        key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


class EncryptedJSONField(models.JSONField):
    """JSONField cuyo contenido se almacena cifrado (Fernet) — H-SEC-4."""

    def from_db_value(self, value, expression, connection):
        value = super().from_db_value(value, expression, connection)
        if value is None:
            return None
        if isinstance(value, str):
            # Caso normal: token cifrado almacenado como string JSON.
            try:
                plano = _fernet().decrypt(value.encode()).decode()
                return json.loads(plano)
            except (InvalidToken, ValueError):
                # Legacy: string JSON sin cifrar.
                try:
                    return json.loads(value)
                except (ValueError, TypeError):
                    return value
        # Legacy: dict/list plano aún no migrado.
        return value

    def get_prep_value(self, value):
        if value is None:
            return super().get_prep_value(value)
        token = _fernet().encrypt(json.dumps(value, default=str).encode()).decode()
        # super() (JSONField) serializa el token como string JSON dentro de jsonb.
        return super().get_prep_value(token)
