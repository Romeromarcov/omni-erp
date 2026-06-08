"""Signals de ``apps.core``.

``connection_created``: fija el contexto RLS por defecto (``bypass='on'``) en
toda conexión PostgreSQL nueva, para que migraciones, Celery, shell y tests
operen con acceso total una vez que ``FORCE ROW LEVEL SECURITY`` está activo.
Ver ``apps/core/rls.py``.
"""

from __future__ import annotations

import logging

from django.db.backends.signals import connection_created
from django.dispatch import receiver

from . import rls

logger = logging.getLogger("apps")


@receiver(connection_created)
def set_default_rls_context(sender, connection, **kwargs):  # noqa: D401
    if connection.vendor != "postgresql":
        return
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config(%s, %s, false)", [rls.GUC_BYPASS, "on"])
            cursor.execute("SELECT set_config(%s, %s, false)", [rls.GUC_EMPRESAS, ""])
    except Exception:  # pragma: no cover - no romper la creación de conexión
        # Sin contexto explícito, las políticas RLS dejan la conexión en
        # fail-closed; se registra para diagnóstico sin filtrar detalles.
        logger.warning("No se pudo fijar el contexto RLS por defecto en una conexión nueva")
