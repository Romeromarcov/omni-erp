"""Utilidades de caché distribuida multi-tenant sobre ``CACHES["default"]`` (Plan 05 P2-4).

Reglas de diseño:
- **Aislamiento estricto por tenant (R-CODE-1):** toda clave lleva ``namespace``,
  ``tenant_key`` normalizado (UUID de ``Empresa`` o ``"global"`` explícito para
  catálogos compartidos) y versión del par ``(namespace, tenant_key)``.
- **Invalidación selectiva sin ``cache.clear()``:** las señales de dominio
  incrementan la versión del namespace/tenant afectado vía ``incr`` (con
  fallback atómico ``add(..., 1)`` en frío), dejando intactas las entradas de
  los demás tenants.
- **Serialización segura:** prohíbe almacenar ``QuerySet`` perezosos o instancias
  ORM en caché; los callers deben almacenar PKs (``tuple[UUID, ...]``), DTOs o
  ``dict``/``tuple`` inmutables con tipos nativos (``Decimal``, ``UUID``,
  ``date``, ``str``, ``int``, ``bool``, ``None``).
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Callable, Iterable
from typing import Any, TypeVar, cast

from django.core.cache import cache
from django.db import models

T = TypeVar("T")

GLOBAL_TENANT_KEY = "global"
DEFAULT_CACHE_TIMEOUT = 300

_NAMESPACE_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_SAFE_HINT_RE = re.compile(r"[^A-Za-z0-9._-]+")


class _CacheMissType:
    """Centinela interno para distinguir ``None`` cacheado de un cache miss."""


_CACHE_MISS = _CacheMissType()


def normalize_namespace(namespace: str) -> str:
    """Valida y normaliza un nombre de namespace de caché."""
    ns = str(namespace).strip()
    if not ns or "\x00" in ns or not _NAMESPACE_RE.match(ns):
        raise ValueError(f"Namespace de caché inválido: {namespace!r}")
    return ns


def normalize_tenant_key(tenant_key: uuid.UUID | str | Any | None) -> str:
    """Normaliza ``tenant_key`` a UUID canónico, ``"global"`` o hash seguro."""
    if tenant_key is None:
        return GLOBAL_TENANT_KEY
    if isinstance(tenant_key, uuid.UUID):
        return str(tenant_key)
    if hasattr(tenant_key, "pk"):
        pk = getattr(tenant_key, "pk")
        if pk is None:
            raise ValueError("El objeto tenant no tiene pk asignado.")
        return normalize_tenant_key(pk)

    raw = str(tenant_key).strip()
    if not raw or "\x00" in raw:
        raise ValueError(f"tenant_key de caché inválido: {tenant_key!r}")
    if raw == GLOBAL_TENANT_KEY:
        return GLOBAL_TENANT_KEY
    try:
        return str(uuid.UUID(raw))
    except (ValueError, TypeError):
        hint = _SAFE_HINT_RE.sub("_", raw).strip("_")[:24] or "tenant"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"{hint}_{digest}"


def _version_cache_key(namespace: str, tenant_key: uuid.UUID | str | Any | None = None) -> str:
    ns = normalize_namespace(namespace)
    tenant = normalize_tenant_key(tenant_key)
    return f"omni:ver:{ns}:t:{tenant}"


def get_namespace_version(namespace: str, tenant_key: uuid.UUID | str | Any | None = None) -> int:
    """Obtiene la versión vigente de ``(namespace, tenant_key)`` (inicializa en 1)."""
    vkey = _version_cache_key(namespace, tenant_key)
    ver = cache.get(vkey)
    if ver is None:
        cache.add(vkey, 1, timeout=None)
        ver = cache.get(vkey)
        if ver is None:
            cache.set(vkey, 1, timeout=None)
            return 1
    return int(ver)


def bump_namespace_version(namespace: str, tenant_key: uuid.UUID | str | Any | None = None) -> int:
    """Incrementa atómicamente la versión de ``(namespace, tenant_key)``."""
    vkey = _version_cache_key(namespace, tenant_key)
    try:
        return int(cache.incr(vkey))
    except ValueError:
        if cache.add(vkey, 1, timeout=None):
            return 1
        try:
            return int(cache.incr(vkey))
        except ValueError:
            cache.set(vkey, 1, timeout=None)
            return 1


def build_cache_key(
    namespace: str,
    tenant_key: uuid.UUID | str | Any | None,
    subkey: str,
    *,
    version: int | None = None,
) -> str:
    """Construye la clave versionada y segura para ``CACHES["default"]``."""
    ns = normalize_namespace(namespace)
    tenant = normalize_tenant_key(tenant_key)
    ver = get_namespace_version(ns, tenant_key) if version is None else int(version)
    raw_subkey = str(subkey)
    if "\x00" in raw_subkey:
        raise ValueError("subkey de caché contiene byte NUL.")
    digest = hashlib.sha256(raw_subkey.encode("utf-8")).hexdigest()[:24]
    hint = _SAFE_HINT_RE.sub("_", raw_subkey).strip("_")[:32]
    suffix = f"{hint}:{digest}" if hint else digest
    return f"omni:data:{ns}:t:{tenant}:v{ver}:{suffix}"


def _validate_cacheable(value: Any) -> None:
    """Rechaza ``QuerySet`` perezosos o instancias ORM antes de escribir en caché."""
    if isinstance(value, models.QuerySet):
        raise TypeError("No se permite cachear QuerySets perezosos; serialice PKs o DTOs.")
    if isinstance(value, models.Model):
        raise TypeError("No se permite cachear instancias ORM en caché; serialice PKs o DTOs.")
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, (models.QuerySet, models.Model)):
                raise TypeError("No se permite cachear colecciones con instancias ORM o QuerySets.")
    elif isinstance(value, dict):
        for item in value.values():
            if isinstance(item, (models.QuerySet, models.Model)):
                raise TypeError("No se permite cachear dicts con instancias ORM o QuerySets.")


def get_cached_or_set(
    namespace: str,
    tenant_key: uuid.UUID | str | Any | None,
    subkey: str,
    factory: Callable[[], T],
    timeout: int | None = DEFAULT_CACHE_TIMEOUT,
) -> T:
    """Lee un valor de caché versionada por tenant; en miss ejecuta ``factory`` y guarda."""
    version = get_namespace_version(namespace, tenant_key)
    key = build_cache_key(namespace, tenant_key, subkey, version=version)
    cached = cache.get(key, _CACHE_MISS)
    if cached is not _CACHE_MISS:
        return cast(T, cached)

    value = factory()
    _validate_cacheable(value)
    cache.set(key, value, timeout=timeout)
    return value


def bump_namespaces(items: Iterable[tuple[str, uuid.UUID | str | Any | None]]) -> None:
    """Invalida selectivamente múltiples pares ``(namespace, tenant_key)``."""
    for namespace, tenant_key in items:
        bump_namespace_version(namespace, tenant_key)
