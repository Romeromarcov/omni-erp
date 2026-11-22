"""Analíticas multi-tenant de Omni Connect (Plan 07 S10).

Calcula métricas agregadas de ``connect.Toque`` y ``crm.Lead`` acotadas
estrictamente a ``id_empresa`` (y ``perfil_id`` opcional), mediante consultas
ORM agrupadas (``Count`` / ``TruncDate``) sin N+1 y porcentajes ``Decimal``.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.core.models import Empresa
from apps.crm.models import Etapa, Lead

from .models import Perfil, Toque
from .services import ConnectError, PerfilNoEncontradoError

_FECHA_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PCT_QUANT = Decimal("0.01")
_CIEN = Decimal("100")
_TOP_PERFILES_LIMITE = 10
_DIAS_MIN = 1
_DIAS_MAX = 365


def _parse_fecha_iso(raw: date | str | None, campo: str) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    texto = str(raw)
    if "\x00" in texto:
        raise ConnectError(f"Parámetro '{campo}' inválido.")
    limpio = texto.strip()
    if not limpio:
        return None
    if not _FECHA_ISO_RE.match(limpio):
        raise ConnectError(f"Formato de fecha inválido para '{campo}'. Use YYYY-MM-DD.")
    try:
        return date.fromisoformat(limpio)
    except ValueError as exc:
        raise ConnectError(f"Fecha inválida para '{campo}'.") from exc


def _normalizar_dias(dias: int | str | None) -> int:
    if dias is None:
        return 30
    if isinstance(dias, bool):
        raise ConnectError("El parámetro 'dias' debe ser un número entero.")
    if isinstance(dias, str):
        if "\x00" in dias:
            raise ConnectError("Parámetro 'dias' inválido.")
        dias = dias.strip()
        if not dias:
            return 30
    try:
        valor = int(dias)
    except (TypeError, ValueError) as exc:
        raise ConnectError("El parámetro 'dias' debe ser un número entero.") from exc
    return max(_DIAS_MIN, min(valor, _DIAS_MAX))


def _parse_perfil_id(perfil_id: uuid.UUID | str | None) -> uuid.UUID | None:
    if perfil_id is None:
        return None
    if isinstance(perfil_id, uuid.UUID):
        return perfil_id
    texto = str(perfil_id)
    if "\x00" in texto:
        raise ConnectError("Parámetro 'perfil_id' inválido.")
    limpio = texto.strip()
    if not limpio:
        return None
    try:
        return uuid.UUID(limpio)
    except (TypeError, ValueError) as exc:
        raise ConnectError("El parámetro 'perfil_id' no es un UUID válido.") from exc


def _calcular_porcentaje(numerador: int, denominador: int) -> str:
    if denominador <= 0 or numerador <= 0:
        return "0.00"
    ratio = (Decimal(numerador) * _CIEN / Decimal(denominador)).quantize(_PCT_QUANT, rounding=ROUND_HALF_UP)
    return format(ratio, ".2f")


def obtener_analiticas_connect(
    empresa: Empresa,
    *,
    desde: date | str | None = None,
    hasta: date | str | None = None,
    perfil_id: uuid.UUID | str | None = None,
    dias: int | str = 30,
) -> dict[str, Any]:
    """Calcula las analíticas de Omni Connect para ``empresa`` en el rango indicado."""
    dias_norm = _normalizar_dias(dias)
    fecha_desde = _parse_fecha_iso(desde, "desde")
    fecha_hasta = _parse_fecha_iso(hasta, "hasta")
    perfil_uuid = _parse_perfil_id(perfil_id)

    hoy = timezone.localdate()
    try:
        if fecha_desde is None and fecha_hasta is None:
            fecha_hasta = hoy
            fecha_desde = fecha_hasta - timedelta(days=dias_norm - 1)
        elif fecha_desde is not None and fecha_hasta is None:
            fecha_hasta = hoy
        elif fecha_desde is None and fecha_hasta is not None:
            fecha_desde = fecha_hasta - timedelta(days=dias_norm - 1)
    except OverflowError as exc:
        raise ConnectError("Rango de fechas fuera de los límites permitidos.") from exc

    assert fecha_desde is not None and fecha_hasta is not None  # noqa: S101 — narrowing para mypy
    if fecha_desde > fecha_hasta:
        raise ConnectError("La fecha 'desde' no puede ser posterior a 'hasta'.")
    if (fecha_hasta - fecha_desde).days > _DIAS_MAX:
        raise ConnectError(f"El rango de fechas no puede exceder {_DIAS_MAX} días.")

    if perfil_uuid is not None:
        if not Perfil.objects.filter(pk=perfil_uuid, id_empresa=empresa).exists():
            raise PerfilNoEncontradoError("Perfil no encontrado en la empresa.")

    tz = timezone.get_current_timezone()
    try:
        inicio_dt = timezone.make_aware(datetime.combine(fecha_desde, time.min), tz)
        fin_dt = timezone.make_aware(datetime.combine(fecha_hasta + timedelta(days=1), time.min), tz)
    except OverflowError as exc:
        raise ConnectError("Rango de fechas fuera de los límites permitidos.") from exc

    toques_qs = Toque.objects.filter(
        id_empresa=empresa,
        fecha_toque__gte=inicio_dt,
        fecha_toque__lt=fin_dt,
    )
    leads_qs = Lead.objects.filter(
        id_empresa=empresa,
        fecha_creacion__gte=inicio_dt,
        fecha_creacion__lt=fin_dt,
    )
    if perfil_uuid is not None:
        toques_qs = toques_qs.filter(perfil_id=perfil_uuid)
        leads_qs = leads_qs.filter(perfil_id=perfil_uuid)
    else:
        leads_qs = leads_qs.filter(
            Q(perfil__isnull=False) | Q(fuente__in=[Lead.Fuente.NFC, Lead.Fuente.QR, Lead.Fuente.ENLACE])
        )

    toques_totales = toques_qs.aggregate(
        total_toques=Count("pk"),
        visitantes_unicos=Count("ip_hash", filter=~Q(ip_hash=""), distinct=True),
    )
    total_toques = int(toques_totales["total_toques"] or 0)
    visitantes_unicos = int(toques_totales["visitantes_unicos"] or 0)

    filtro_convertido = Q(cliente_convertido__isnull=False) | Q(etapa__tipo=Etapa.Tipo.GANADA)
    leads_totales = leads_qs.aggregate(
        total_leads=Count("pk"),
        leads_convertidos=Count("pk", filter=filtro_convertido),
    )
    total_leads = int(leads_totales["total_leads"] or 0)
    leads_convertidos = int(leads_totales["leads_convertidos"] or 0)

    por_origen: dict[str, int] = {choice: 0 for choice in Toque.Origen.values}
    for row in toques_qs.values("origen").annotate(total=Count("pk")):
        clave_origen = str(row["origen"])
        if clave_origen in por_origen:
            por_origen[clave_origen] = int(row["total"] or 0)

    por_dispositivo: dict[str, int] = {choice: 0 for choice in Toque.Dispositivo.values}
    for row in toques_qs.values("dispositivo").annotate(total=Count("pk")):
        clave_disp = str(row["dispositivo"])
        if clave_disp in por_dispositivo:
            por_dispositivo[clave_disp] = int(row["total"] or 0)

    serie_map: dict[date, dict[str, int]] = {}
    for row in (
        toques_qs.annotate(dia=TruncDate("fecha_toque", tzinfo=tz))
        .values("dia")
        .annotate(total=Count("pk"))
        .order_by("dia")
    ):
        dia = row["dia"]
        if dia is not None:
            serie_map.setdefault(dia, {"toques": 0, "leads": 0})["toques"] = int(row["total"] or 0)

    for row in (
        leads_qs.annotate(dia=TruncDate("fecha_creacion", tzinfo=tz))
        .values("dia")
        .annotate(total=Count("pk"))
        .order_by("dia")
    ):
        dia = row["dia"]
        if dia is not None:
            serie_map.setdefault(dia, {"toques": 0, "leads": 0})["leads"] = int(row["total"] or 0)

    serie_diaria = [
        {
            "fecha": dia.isoformat(),
            "toques": conteo["toques"],
            "leads": conteo["leads"],
        }
        for dia, conteo in sorted(serie_map.items())
    ]

    perfiles_map: dict[str, dict[str, Any]] = {}
    for row in (
        toques_qs.values("perfil_id", "perfil__slug", "perfil__nombre_publico")
        .annotate(
            toques=Count("pk"),
            visitantes_unicos=Count("ip_hash", filter=~Q(ip_hash=""), distinct=True),
        )
        .order_by("-toques")
    ):
        pid = str(row["perfil_id"])
        perfiles_map[pid] = {
            "id_perfil": pid,
            "slug": str(row["perfil__slug"] or ""),
            "nombre_publico": str(row["perfil__nombre_publico"] or ""),
            "toques": int(row["toques"] or 0),
            "visitantes_unicos": int(row["visitantes_unicos"] or 0),
            "leads": 0,
            "leads_convertidos": 0,
        }

    for row in (
        leads_qs.filter(perfil__isnull=False)
        .values("perfil_id", "perfil__slug", "perfil__nombre_publico")
        .annotate(
            leads=Count("pk"),
            leads_convertidos=Count("pk", filter=filtro_convertido),
        )
    ):
        pid = str(row["perfil_id"])
        entrada = perfiles_map.setdefault(
            pid,
            {
                "id_perfil": pid,
                "slug": str(row["perfil__slug"] or ""),
                "nombre_publico": str(row["perfil__nombre_publico"] or ""),
                "toques": 0,
                "visitantes_unicos": 0,
                "leads": 0,
                "leads_convertidos": 0,
            },
        )
        entrada["leads"] = int(row["leads"] or 0)
        entrada["leads_convertidos"] = int(row["leads_convertidos"] or 0)

    top_perfiles_raw = sorted(
        perfiles_map.values(),
        key=lambda item: (-item["toques"], -item["leads"], item["nombre_publico"]),
    )[:_TOP_PERFILES_LIMITE]
    top_perfiles = [
        {
            **item,
            "tasa_conversion_pct": _calcular_porcentaje(item["leads"], item["toques"]),
        }
        for item in top_perfiles_raw
    ]

    return {
        "periodo": {
            "desde": fecha_desde.isoformat(),
            "hasta": fecha_hasta.isoformat(),
            "dias": (fecha_hasta - fecha_desde).days + 1,
        },
        "perfil_id": str(perfil_uuid) if perfil_uuid is not None else None,
        "total_toques": total_toques,
        "visitantes_unicos": visitantes_unicos,
        "total_leads": total_leads,
        "leads_convertidos": leads_convertidos,
        "tasa_conversion_pct": _calcular_porcentaje(total_leads, total_toques),
        "tasa_cierre_pct": _calcular_porcentaje(leads_convertidos, total_leads),
        "por_origen": por_origen,
        "por_dispositivo": por_dispositivo,
        "serie_diaria": serie_diaria,
        "top_perfiles": top_perfiles,
    }
