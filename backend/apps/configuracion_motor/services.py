"""Servicios cacheados de lectura de ``ParametroSistema`` (Plan 05 P2-4)."""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings

from apps.core.cache_utils import (
    DEFAULT_CACHE_TIMEOUT,
    GLOBAL_TENANT_KEY,
    bump_namespace_version,
    get_cached_or_set,
    get_namespace_version,
)

from .models import ParametroSistema

NS_PARAMETRO_SISTEMA = "configuracion_motor.parametro"
NS_PARAMETRO_SISTEMA_GLOBAL = "configuracion_motor.parametro_global"


def _normalizar_empresa_id(empresa: Any) -> uuid.UUID | None:
    if empresa is None:
        return None
    raw = getattr(empresa, "pk", empresa)
    if raw is None:
        return None
    if isinstance(raw, uuid.UUID):
        return raw
    return uuid.UUID(str(raw))


def _rls_permite_cache_empresa(empresa_id: uuid.UUID | None) -> bool:
    if not getattr(settings, "RLS_ENABLED", False):
        return True
    from apps.core import rls

    bypass, empresas_csv = rls._get_current_context()
    if bypass == "on" or empresa_id is None:
        return True
    return str(empresa_id) in {emp for emp in empresas_csv.split(",") if emp}


def obtener_parametro(
    codigo_parametro: str,
    empresa: Any = None,
    *,
    default: str | None = None,
    incluir_global: bool = False,
    strip: bool = True,
) -> str | None:
    """Lee un ``ParametroSistema`` activo usando caché versionada por empresa.

    - ``empresa=None``: consulta únicamente filas globales (``id_empresa=None``).
    - ``empresa=<Empresa|UUID>``: consulta filas de esa empresa; con
      ``incluir_global=True`` cae a la fila global si no hay override por tenant.
    """
    codigo = str(codigo_parametro).strip()
    if not codigo:
        return default

    empresa_id = _normalizar_empresa_id(empresa)

    if empresa_id is None:

        def _fetch_global() -> str | None:
            return (
                ParametroSistema.objects.filter(
                    id_empresa__isnull=True,
                    codigo_parametro=codigo,
                    activo=True,
                )
                .values_list("valor_parametro", flat=True)
                .first()
            )

        valor = get_cached_or_set(
            NS_PARAMETRO_SISTEMA,
            GLOBAL_TENANT_KEY,
            f"param:{codigo}",
            _fetch_global,
            timeout=DEFAULT_CACHE_TIMEOUT,
        )
    else:

        def _fetch_tenant() -> str | None:
            val = (
                ParametroSistema.objects.filter(
                    id_empresa_id=empresa_id,
                    codigo_parametro=codigo,
                    activo=True,
                )
                .values_list("valor_parametro", flat=True)
                .first()
            )
            if val is not None or not incluir_global:
                return val
            return (
                ParametroSistema.objects.filter(
                    id_empresa__isnull=True,
                    codigo_parametro=codigo,
                    activo=True,
                )
                .values_list("valor_parametro", flat=True)
                .first()
            )

        if _rls_permite_cache_empresa(empresa_id):
            if incluir_global:
                global_ver = get_namespace_version(NS_PARAMETRO_SISTEMA_GLOBAL, GLOBAL_TENANT_KEY)
                subkey = f"g{global_ver}:param_ig:{codigo}"
            else:
                subkey = f"param:{codigo}"
            valor = get_cached_or_set(
                NS_PARAMETRO_SISTEMA,
                empresa_id,
                subkey,
                _fetch_tenant,
                timeout=DEFAULT_CACHE_TIMEOUT,
            )
        else:
            valor = _fetch_tenant()

    if valor is None:
        return default
    return valor.strip() if strip else valor


def invalidar_cache_parametro(*, empresa_id: uuid.UUID | None = None) -> None:
    """Invalida selectivamente los parámetros cacheados del tenant o globales."""
    if empresa_id is None:
        bump_namespace_version(NS_PARAMETRO_SISTEMA, GLOBAL_TENANT_KEY)
        bump_namespace_version(NS_PARAMETRO_SISTEMA_GLOBAL, GLOBAL_TENANT_KEY)
    else:
        bump_namespace_version(NS_PARAMETRO_SISTEMA, empresa_id)
