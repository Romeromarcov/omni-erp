"""Signals de ``apps.core``.

- ``connection_created``: fija el contexto RLS por defecto en toda conexión
  PostgreSQL nueva (``bypass='on'`` con ``RLS_ENABLED=False``; fail-closed
  ``bypass='off'`` con ``RLS_ENABLED=True``). Ver ``apps/core/rls.py``.
- ``pre_migrate`` / ``post_migrate``: habilita bypass durante ``migrate``
  (incluyendo data migrations) y restaura el default al finalizar.
- Invalidación del cache por request de ``get_empresas_visible`` ante cambios
  en ``Empresa`` o membresías ``Usuarios.empresas``.
"""

from __future__ import annotations

import logging

from django.db import DEFAULT_DB_ALIAS, connections
from django.db.backends.signals import connection_created
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_migrate, post_migrate
from django.dispatch import receiver

from . import rls
from .models import Usuarios

logger = logging.getLogger("apps")


@receiver(connection_created)
def set_default_rls_context(sender, connection, **kwargs):
    if connection.vendor != "postgresql":
        return
    try:
        with connection.cursor() as cursor:
            rls.apply_system_default_on_cursor(cursor)
    except Exception:  # pragma: no cover - no romper la creación de conexión
        # Sin contexto explícito, las políticas RLS dejan la conexión en
        # fail-closed; se registra para diagnóstico sin filtrar detalles.
        logger.warning("No se pudo fijar el contexto RLS por defecto en una conexión nueva")


@receiver(pre_migrate)
def enable_rls_bypass_for_migrate(sender, using=DEFAULT_DB_ALIAS, **kwargs):
    """Asegura ``bypass='on'`` durante ``manage.py migrate`` con ``RLS_ENABLED=True``."""
    db_alias = using or DEFAULT_DB_ALIAS
    conn = connections[db_alias]
    if conn.vendor != "postgresql":
        return
    rls.apply_context([], bypass=True, using=db_alias)


@receiver(post_migrate)
def restore_rls_default_after_migrate(sender, using=DEFAULT_DB_ALIAS, **kwargs):
    """Restaura el default RLS al finalizar ``manage.py migrate``."""
    db_alias = using or DEFAULT_DB_ALIAS
    conn = connections[db_alias]
    if conn.vendor != "postgresql":
        return
    rls.apply_system_default(using=db_alias)


def _invalidar_cache_visibilidad(*, user_pk=None, invalidate_tree: bool = False) -> None:
    from .viewsets import invalidar_cache_empresas_visible

    invalidar_cache_empresas_visible(user_pk=user_pk, invalidate_tree=invalidate_tree)


@receiver([post_save, post_delete], sender="core.Empresa")
def on_empresa_changed_invalidar_cache(sender, **kwargs):
    _invalidar_cache_visibilidad(invalidate_tree=True)


@receiver([post_save, post_delete], sender="core.Usuarios")
def on_usuario_changed_invalidar_cache(sender, instance=None, update_fields=None, **kwargs):
    if update_fields is not None and set(update_fields).issubset({"last_login", "fecha_ultimo_login"}):
        return
    user_pk = getattr(instance, "pk", None)
    _invalidar_cache_visibilidad(user_pk=user_pk, invalidate_tree=user_pk is None)


@receiver([post_save, post_delete], sender=Usuarios.empresas.through)
def on_usuario_empresa_changed_invalidar_cache(sender, instance=None, **kwargs):
    user_pk = getattr(instance, "usuarios_id", None)
    _invalidar_cache_visibilidad(user_pk=user_pk, invalidate_tree=user_pk is None)


@receiver(m2m_changed, sender=Usuarios.empresas.through)
def on_usuario_empresas_m2m_invalidar_cache(sender, action, instance=None, reverse=False, pk_set=None, **kwargs):
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if not reverse and isinstance(instance, Usuarios):
        _invalidar_cache_visibilidad(user_pk=instance.pk)
        return
    if pk_set:
        for uid in pk_set:
            _invalidar_cache_visibilidad(user_pk=uid)
        return
    _invalidar_cache_visibilidad(invalidate_tree=True)
