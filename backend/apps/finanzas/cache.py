"""Caché multi-tenant de catálogos y tasas calientes de Finanzas (Plan 05 P2-4).

Almacena únicamente DTOs/dicts inmutables y tuplas de UUIDs en ``CACHES["default"]``
vía ``apps.core.cache_utils`` (jamás ``QuerySet`` perezosos ni instancias ORM).
Toda consulta tenant-específica se aísla por ``empresa_id`` (``R-CODE-1``) y los
importes monetarios preservan ``Decimal`` exacto (``R-CODE-4``).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from django.conf import settings
from django.db.models import Q

from apps.core.cache_utils import (
    DEFAULT_CACHE_TIMEOUT,
    GLOBAL_TENANT_KEY,
    bump_namespace_version,
    get_cached_or_set,
    get_namespace_version,
)

from .models import MetodoPago, Moneda, MonedaEmpresaActiva, TasaCambio

NS_MONEDA = "finanzas.moneda"
NS_MONEDA_GLOBAL = "finanzas.moneda_global"
NS_MONEDA_ACTIVA = "finanzas.moneda_activa"
NS_TASA_CAMBIO = "finanzas.tasa_cambio"
NS_TASA_CAMBIO_GLOBAL = "finanzas.tasa_cambio_global"
NS_METODO_PAGO = "finanzas.metodo_pago"
NS_METODO_PAGO_GLOBAL = "finanzas.metodo_pago_global"
NS_METODO_PAGO_ACTIVO = "finanzas.metodo_pago_activo"

TIPO_TASA_PRIORIDAD: tuple[str, ...] = ("ESPECIAL_USUARIO", "FIJA", "PROMEDIO_MERCADO", "OFICIAL_BCV")
_PRIORIDAD_IDX: dict[str, int] = {tipo: idx for idx, tipo in enumerate(TIPO_TASA_PRIORIDAD)}

_MONEDA_DTO_FIELDS: tuple[str, ...] = (
    "id_moneda",
    "tipo_moneda",
    "codigo_iso",
    "nombre",
    "simbolo",
    "decimales",
    "activo",
    "es_generica",
    "es_publica",
    "empresa_id",
)

_TASA_DTO_FIELDS: tuple[str, ...] = (
    "id_tasa_cambio",
    "id_empresa_id",
    "id_moneda_origen_id",
    "id_moneda_destino_id",
    "tipo_tasa",
    "valor_tasa",
    "fecha_tasa",
    "hora_tasa",
)


def normalizar_empresa_uuid(empresa: Any) -> uuid.UUID | None:
    """Extrae el UUID de una instancia ``Empresa`` o UUID/str; ``None`` si es global."""
    if empresa is None:
        return None
    raw = getattr(empresa, "pk", empresa)
    if raw is None:
        return None
    if isinstance(raw, uuid.UUID):
        return raw
    return uuid.UUID(str(raw))


def _rls_permite_cache_global() -> bool:
    """Con RLS activo solo usa caché L2 global bajo ``rls_bypass`` (evita divergencia con públicas)."""
    if not getattr(settings, "RLS_ENABLED", False):
        return True
    from apps.core import rls

    bypass, _ = rls._get_current_context()
    return bypass == "on"


def _rls_permite_cache_empresa(empresa_id: uuid.UUID | None) -> bool:
    """Evita leer/poblar caché L2 de una empresa cuando RLS activo la oculta."""
    if not getattr(settings, "RLS_ENABLED", False):
        return True
    from apps.core import rls

    bypass, empresas_csv = rls._get_current_context()
    if bypass == "on" or empresa_id is None:
        return True
    return str(empresa_id) in {emp for emp in empresas_csv.split(",") if emp}


def _reconstruir_moneda(dto: dict[str, Any]) -> Moneda:
    instancia = Moneda(
        id_moneda=dto["id_moneda"],
        tipo_moneda=dto["tipo_moneda"],
        codigo_iso=dto["codigo_iso"],
        nombre=dto["nombre"],
        simbolo=dto["simbolo"],
        decimales=dto["decimales"],
        activo=dto["activo"],
        es_generica=dto["es_generica"],
        es_publica=dto["es_publica"],
        empresa_id=dto["empresa_id"],
    )
    instancia._state.adding = False
    instancia._state.db = "default"
    return instancia


def _reconstruir_tasa(
    dto: dict[str, Any],
    *,
    moneda_origen: Moneda | None = None,
    moneda_destino: Moneda | None = None,
) -> TasaCambio:
    instancia = TasaCambio(
        id_tasa_cambio=dto["id_tasa_cambio"],
        id_empresa_id=dto["id_empresa_id"],
        id_moneda_origen_id=dto["id_moneda_origen_id"],
        id_moneda_destino_id=dto["id_moneda_destino_id"],
        tipo_tasa=dto["tipo_tasa"],
        valor_tasa=dto["valor_tasa"],
        fecha_tasa=dto["fecha_tasa"],
        hora_tasa=dto["hora_tasa"],
    )
    if moneda_origen is not None and moneda_origen.pk == dto["id_moneda_origen_id"]:
        instancia.id_moneda_origen = moneda_origen
    if moneda_destino is not None and moneda_destino.pk == dto["id_moneda_destino_id"]:
        instancia.id_moneda_destino = moneda_destino
    instancia._state.adding = False
    instancia._state.db = "default"
    return instancia


def obtener_moneda_por_iso(codigo_iso: str, *, empresa_id: uuid.UUID | None = None) -> Moneda | None:
    """Resuelve una ``Moneda`` por ``codigo_iso`` usando caché global y por empresa."""
    iso_clean = str(codigo_iso).strip()
    if not iso_clean:
        return None

    def _fetch_global() -> dict[str, Any] | None:
        return (
            Moneda.objects.filter(codigo_iso=iso_clean)
            .filter(Q(es_generica=True) | Q(es_publica=True) | Q(empresa__isnull=True))
            .values(*_MONEDA_DTO_FIELDS)
            .first()
        )

    if _rls_permite_cache_global():
        global_ver = get_namespace_version(NS_MONEDA_GLOBAL, GLOBAL_TENANT_KEY)
        dto_global = get_cached_or_set(
            NS_MONEDA,
            GLOBAL_TENANT_KEY,
            f"iso:g{global_ver}:{iso_clean}",
            _fetch_global,
            timeout=DEFAULT_CACHE_TIMEOUT,
        )
    else:
        dto_global = _fetch_global()
    if dto_global is not None:
        return _reconstruir_moneda(dto_global)

    if empresa_id is None:
        return None

    def _fetch_tenant() -> dict[str, Any] | None:
        return Moneda.objects.filter(codigo_iso=iso_clean, empresa_id=empresa_id).values(*_MONEDA_DTO_FIELDS).first()

    if _rls_permite_cache_empresa(empresa_id):
        dto_tenant = get_cached_or_set(
            NS_MONEDA,
            empresa_id,
            f"iso:{iso_clean}",
            _fetch_tenant,
            timeout=DEFAULT_CACHE_TIMEOUT,
        )
    else:
        dto_tenant = _fetch_tenant()
    return _reconstruir_moneda(dto_tenant) if dto_tenant is not None else None


def _buscar_mejor_tasa_dto(
    origen_id: uuid.UUID,
    destino_id: uuid.UUID,
    *,
    empresa_id: uuid.UUID | None,
    fecha: date,
) -> dict[str, Any] | None:
    base_qs = TasaCambio.objects.filter(
        id_moneda_origen_id=origen_id,
        id_moneda_destino_id=destino_id,
        fecha_tasa=fecha,
    )

    # 1. Tasa empresa-específica (fecha exacta, prioridad por tipo_tasa)
    if empresa_id is not None:
        candidatas = list(
            base_qs.filter(id_empresa_id=empresa_id).order_by("-fecha_creacion").values(*_TASA_DTO_FIELDS)
        )
        if candidatas:
            candidatas.sort(key=lambda item: _PRIORIDAD_IDX.get(str(item["tipo_tasa"]), len(TIPO_TASA_PRIORIDAD)))
            return candidatas[0]

    # 2. Tasa global OFICIAL_BCV (fecha exacta)
    tasa_bcv = (
        base_qs.filter(id_empresa__isnull=True, tipo_tasa="OFICIAL_BCV")
        .order_by("-fecha_creacion")
        .values(*_TASA_DTO_FIELDS)
        .first()
    )
    if tasa_bcv is not None:
        return tasa_bcv

    # 3. Tasa más reciente dentro de los últimos 30 días (empresa > global)
    fecha_limite = fecha - timedelta(days=30)
    recientes_qs = TasaCambio.objects.filter(
        id_moneda_origen_id=origen_id,
        id_moneda_destino_id=destino_id,
        fecha_tasa__gte=fecha_limite,
        fecha_tasa__lte=fecha,
    ).order_by("-fecha_tasa", "-fecha_creacion")

    if empresa_id is not None:
        tasa_emp_reciente = recientes_qs.filter(id_empresa_id=empresa_id).values(*_TASA_DTO_FIELDS).first()
        if tasa_emp_reciente is not None:
            return tasa_emp_reciente

    return recientes_qs.filter(id_empresa__isnull=True).values(*_TASA_DTO_FIELDS).first()


def obtener_tasa_cambio_cacheada(
    moneda_origen: Moneda,
    moneda_destino: Moneda,
    *,
    empresa_id: uuid.UUID | None,
    fecha: date,
) -> TasaCambio | None:
    """Obtiene la mejor ``TasaCambio`` vigente usando caché multi-tenant versionada."""
    origen_id = moneda_origen.pk
    destino_id = moneda_destino.pk

    def _factory() -> dict[str, Any] | None:
        return _buscar_mejor_tasa_dto(origen_id, destino_id, empresa_id=empresa_id, fecha=fecha)

    if empresa_id is None:
        dto = get_cached_or_set(
            NS_TASA_CAMBIO,
            GLOBAL_TENANT_KEY,
            f"rate:{origen_id}:{destino_id}:{fecha.isoformat()}",
            _factory,
            timeout=DEFAULT_CACHE_TIMEOUT,
        )
    elif _rls_permite_cache_empresa(empresa_id):
        global_ver = get_namespace_version(NS_TASA_CAMBIO_GLOBAL, GLOBAL_TENANT_KEY)
        dto = get_cached_or_set(
            NS_TASA_CAMBIO,
            empresa_id,
            f"g{global_ver}:rate:{origen_id}:{destino_id}:{fecha.isoformat()}",
            _factory,
            timeout=DEFAULT_CACHE_TIMEOUT,
        )
    else:
        dto = _factory()

    if dto is None:
        return None
    return _reconstruir_tasa(dto, moneda_origen=moneda_origen, moneda_destino=moneda_destino)


def obtener_tasa_oficial_bcv_payload(
    origen_id: uuid.UUID,
    destino_id: uuid.UUID,
    fecha: date,
) -> dict[str, Any] | None:
    """Devuelve el payload serializado de la tasa global ``OFICIAL_BCV`` cacheado."""
    from .serializers import TasaCambioSerializer

    def _factory() -> dict[str, Any] | None:
        tasa = (
            TasaCambio.objects.filter(
                fecha_tasa=fecha,
                id_moneda_origen_id=origen_id,
                id_moneda_destino_id=destino_id,
                tipo_tasa="OFICIAL_BCV",
                id_empresa__isnull=True,
            )
            .select_related("id_moneda_origen", "id_moneda_destino", "id_usuario_registro")
            .order_by("-fecha_tasa")
            .first()
        )
        if tasa is None:
            return None
        return dict(TasaCambioSerializer(tasa).data)

    return get_cached_or_set(
        NS_TASA_CAMBIO,
        GLOBAL_TENANT_KEY,
        f"bcv_api:{origen_id}:{destino_id}:{fecha.isoformat()}",
        _factory,
        timeout=DEFAULT_CACHE_TIMEOUT,
    )


def obtener_monedas_activas_ids(empresa_id: uuid.UUID) -> tuple[uuid.UUID, ...]:
    """Devuelve los UUIDs de monedas activas para ``empresa_id`` cacheados."""

    def _factory() -> tuple[uuid.UUID, ...]:
        return tuple(
            MonedaEmpresaActiva.objects.filter(empresa_id=empresa_id, activa=True).values_list("moneda_id", flat=True)
        )

    if not _rls_permite_cache_empresa(empresa_id):
        return _factory()

    return get_cached_or_set(
        NS_MONEDA_ACTIVA,
        empresa_id,
        "activas_ids",
        _factory,
        timeout=DEFAULT_CACHE_TIMEOUT,
    )


def obtener_metodos_pago_mcp(empresa_id: uuid.UUID) -> list[dict[str, str]]:
    """Lista métodos de pago activos visibles para ``empresa_id`` (MCP) desde caché."""

    def _factory() -> list[dict[str, str]]:
        qs = (
            MetodoPago.objects.filter(activo=True)
            .filter(Q(es_generico=True) | Q(es_publico=True) | Q(empresa__isnull=True) | Q(empresa_id=empresa_id))
            .order_by("nombre_metodo")
            .values("id_metodo_pago", "nombre_metodo", "tipo_metodo")
        )
        return [
            {
                "id_metodo_pago": str(row["id_metodo_pago"]),
                "nombre_metodo": str(row["nombre_metodo"]),
                "tipo_metodo": str(row["tipo_metodo"]),
            }
            for row in qs
        ]

    if not _rls_permite_cache_empresa(empresa_id):
        return _factory()

    global_ver = get_namespace_version(NS_METODO_PAGO_GLOBAL, GLOBAL_TENANT_KEY)
    return get_cached_or_set(
        NS_METODO_PAGO,
        empresa_id,
        f"g{global_ver}:mcp_activos",
        _factory,
        timeout=DEFAULT_CACHE_TIMEOUT,
    )


def obtener_metodos_pago_empresa_nombres(empresa_id: uuid.UUID) -> tuple[tuple[str, str], ...]:
    """Pares ``(tipo_metodo, nombre_metodo)`` propios de la empresa (evita N+1 en ``buscar_reutilizar``)."""

    def _factory() -> tuple[tuple[str, str], ...]:
        rows = MetodoPago.objects.filter(empresa_id=empresa_id).values_list("tipo_metodo", "nombre_metodo")
        return tuple((str(tipo), str(nombre)) for tipo, nombre in rows)

    if not _rls_permite_cache_empresa(empresa_id):
        return _factory()

    return get_cached_or_set(
        NS_METODO_PAGO,
        empresa_id,
        "propios_tipo_nombre",
        _factory,
        timeout=DEFAULT_CACHE_TIMEOUT,
    )


def invalidar_cache_moneda(
    *,
    empresa_id: uuid.UUID | None = None,
    es_global: bool = False,
) -> None:
    if empresa_id is not None:
        bump_namespace_version(NS_MONEDA, empresa_id)
        bump_namespace_version(NS_MONEDA_ACTIVA, empresa_id)
    if es_global or empresa_id is None:
        bump_namespace_version(NS_MONEDA, GLOBAL_TENANT_KEY)
        bump_namespace_version(NS_MONEDA_GLOBAL, GLOBAL_TENANT_KEY)


def invalidar_cache_tasa_cambio(*, empresa_id: uuid.UUID | None = None) -> None:
    if empresa_id is None:
        bump_namespace_version(NS_TASA_CAMBIO, GLOBAL_TENANT_KEY)
        bump_namespace_version(NS_TASA_CAMBIO_GLOBAL, GLOBAL_TENANT_KEY)
    else:
        bump_namespace_version(NS_TASA_CAMBIO, empresa_id)


def invalidar_cache_metodo_pago(
    *,
    empresa_id: uuid.UUID | None = None,
    es_global: bool = False,
) -> None:
    if empresa_id is not None:
        bump_namespace_version(NS_METODO_PAGO, empresa_id)
        bump_namespace_version(NS_METODO_PAGO_ACTIVO, empresa_id)
    if es_global or empresa_id is None:
        bump_namespace_version(NS_METODO_PAGO, GLOBAL_TENANT_KEY)
        bump_namespace_version(NS_METODO_PAGO_GLOBAL, GLOBAL_TENANT_KEY)
