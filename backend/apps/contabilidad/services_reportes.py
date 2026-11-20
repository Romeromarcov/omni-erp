"""Motor SQL de reportes financieros canónicos (Plan 08 §B.1 ítem 5 / PR-14).

Genera los cuatro reportes contables canónicos agregados en PostgreSQL, con
aritmética exacta en ``Decimal`` (R-CODE-4) y conversión doble opcional a USD:

- ``generar_balance_comprobacion``: saldo inicial + período + saldo final + jerarquía.
- ``generar_estado_resultados``: P&L operativo (excluye asientos ``es_cierre=True``).
- ``generar_balance_general``: Activos = Pasivos + Patrimonio + Resultado no cerrado.
- ``generar_libro_mayor_auxiliar``: por cuenta, contacto y/o diario con saldo corrido.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import DetalleAsiento, DiarioContable, PlanCuentas

if TYPE_CHECKING:
    from apps.core.models import Contacto, Empresa

_CERO = Decimal("0.00")
_CENT = Decimal("0.01")
_TASA_UNO = Decimal("1.00000000")
_DEC_ZERO_EXPR = Value(_CERO, output_field=DecimalField(max_digits=18, decimal_places=2))
_SIN_TASA_USD_MSG = "Sin tasa USD disponible"


class ReporteContableError(Exception):
    """Error de dominio o validación al construir un reporte contable."""


class ReporteTenantError(ReporteContableError):
    """Referencia a entidad inexistente o perteneciente a otro tenant."""


def _q2(valor: Decimal | int | str | None) -> Decimal:
    if valor is None:
        return _CERO
    dec = valor if isinstance(valor, Decimal) else Decimal(str(valor))
    return dec.quantize(_CENT, rounding=ROUND_HALF_UP)


def _validar_rango_fechas(fecha_desde: date | None, fecha_hasta: date | None) -> None:
    if fecha_desde is not None and fecha_hasta is not None and fecha_desde > fecha_hasta:
        raise ReporteContableError("La fecha desde no puede ser posterior a la fecha hasta.")


def _parse_uuid(raw: Any, campo: str) -> uuid.UUID:
    if isinstance(raw, uuid.UUID):
        return raw
    texto = str(raw).strip()
    if "\x00" in texto or not texto:
        raise ReporteContableError(f"El parámetro {campo} es inválido.")
    try:
        return uuid.UUID(texto)
    except (ValueError, TypeError) as exc:
        raise ReporteContableError(f"El parámetro {campo} no es un UUID válido.") from exc


def _resolver_diario(empresa: Empresa, id_diario: DiarioContable | uuid.UUID | str | None) -> DiarioContable | None:
    if id_diario is None or id_diario == "":
        return None
    if isinstance(id_diario, DiarioContable):
        if id_diario.id_empresa_id != empresa.pk:
            raise ReporteTenantError("El diario contable no pertenece a la empresa.")
        return id_diario
    diario_uuid = _parse_uuid(id_diario, "id_diario")
    diario = DiarioContable.objects.filter(pk=diario_uuid, id_empresa=empresa).first()
    if diario is None:
        raise ReporteTenantError("Diario contable no encontrado en la empresa.")
    return diario


def _resolver_cuenta(empresa: Empresa, id_cuenta: PlanCuentas | uuid.UUID | str | None) -> PlanCuentas | None:
    if id_cuenta is None or id_cuenta == "":
        return None
    if isinstance(id_cuenta, PlanCuentas):
        if id_cuenta.id_empresa_id != empresa.pk:
            raise ReporteTenantError("La cuenta contable no pertenece a la empresa.")
        return id_cuenta
    cuenta_uuid = _parse_uuid(id_cuenta, "id_cuenta_contable")
    cuenta = PlanCuentas.objects.filter(pk=cuenta_uuid, id_empresa=empresa).first()
    if cuenta is None:
        raise ReporteTenantError("Cuenta contable no encontrada en la empresa.")
    return cuenta


def _resolver_contacto(empresa: Empresa, id_contacto: Contacto | uuid.UUID | str | None) -> Contacto | None:
    from apps.core.models import Contacto

    if id_contacto is None or id_contacto == "":
        return None
    if isinstance(id_contacto, Contacto):
        if id_contacto.id_empresa_id != empresa.pk:
            raise ReporteTenantError("El contacto no pertenece a la empresa.")
        return id_contacto
    contacto_uuid = _parse_uuid(id_contacto, "id_contacto")
    contacto = Contacto.objects.filter(pk=contacto_uuid, id_empresa=empresa).first()
    if contacto is None:
        raise ReporteTenantError("Contacto no encontrado en la empresa.")
    return contacto


def _resolver_conversion_usd(
    empresa: Empresa,
    fecha_ref: date | None = None,
) -> tuple[Decimal | None, bool, bool]:
    """Resuelve ``(tasa, usd_disponible, es_inversa)`` para convertir montos de moneda base a USD.

    - Si ``es_inversa=False``: ``tasa`` expresa cuántas unidades de ``moneda_base``
      equivalen a 1 USD (``monto_usd = monto / tasa``).
    - Si ``es_inversa=True``: ``tasa`` proviene de una ``TasaCambio`` almacenada como
      ``moneda_base -> USD`` (``monto_usd = monto * tasa``).
    """
    from apps.finanzas.models import Moneda
    from apps.finanzas.services import TasaCambioError, obtener_tasa_cambio

    moneda_base = getattr(empresa, "id_moneda_base", None)
    if moneda_base is None:
        return None, False, False

    if (moneda_base.codigo_iso or "").upper() == "USD":
        return _TASA_UNO, True, False

    moneda_usd = Moneda.objects.filter(codigo_iso="USD", activo=True).order_by("-es_generica", "pk").first()
    if moneda_usd is None:
        return None, False, False

    ref = fecha_ref or timezone.localdate()

    try:
        tasa_directa = obtener_tasa_cambio(moneda_usd, moneda_base, empresa=empresa, fecha=ref)
        valor_directa = Decimal(str(tasa_directa.valor_tasa))
        if valor_directa > Decimal("0"):
            return valor_directa, True, False
    except TasaCambioError:
        pass

    try:
        tasa_inversa = obtener_tasa_cambio(moneda_base, moneda_usd, empresa=empresa, fecha=ref)
        valor_inversa = Decimal(str(tasa_inversa.valor_tasa))
        if valor_inversa > Decimal("0"):
            return valor_inversa, True, True
    except TasaCambioError:
        pass

    return None, False, False


def _resolver_tasa_usd(empresa: Empresa, fecha_ref: date | None = None) -> tuple[Decimal | None, bool]:
    """Retorna ``(tasa_usd, usd_disponible)`` sin inventar 1:1 cuando falta tasa."""
    tasa, disponible, _es_inversa = _resolver_conversion_usd(empresa, fecha_ref=fecha_ref)
    return tasa, disponible


def _convertir_a_usd(monto: Decimal, tasa: Decimal | None, *, es_inversa: bool) -> Decimal | None:
    if tasa is None or tasa <= Decimal("0"):
        return None
    if es_inversa:
        return (monto * tasa).quantize(_CENT, rounding=ROUND_HALF_UP)
    return (monto / tasa).quantize(_CENT, rounding=ROUND_HALF_UP)


def _metadata_moneda_y_usd(
    empresa: Empresa,
    *,
    incluir_equivalentes_usd: bool,
    fecha_ref: date | None,
) -> tuple[dict[str, Any], Decimal | None, bool, bool]:
    moneda_base = getattr(empresa, "id_moneda_base", None)
    moneda_codigo = str(moneda_base.codigo_iso) if moneda_base is not None else ""
    moneda_simbolo = str(moneda_base.simbolo) if moneda_base is not None else ""

    tasa_usd: Decimal | None = None
    usd_disponible = False
    es_inversa = False
    usd_mensaje = ""

    if incluir_equivalentes_usd:
        tasa_usd, usd_disponible, es_inversa = _resolver_conversion_usd(empresa, fecha_ref=fecha_ref)
        if not usd_disponible:
            usd_mensaje = _SIN_TASA_USD_MSG

    meta: dict[str, Any] = {
        "moneda_base": moneda_codigo,
        "moneda_base_simbolo": moneda_simbolo,
        "incluir_equivalentes_usd": incluir_equivalentes_usd,
        "usd_disponible": usd_disponible,
        "tasa_usd": tasa_usd,
        "tasa_usd_inversa": es_inversa if usd_disponible else False,
        "usd_mensaje": usd_mensaje,
    }
    return meta, tasa_usd, usd_disponible, es_inversa


def generar_balance_comprobacion(
    empresa: Empresa,
    *,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    id_diario: DiarioContable | uuid.UUID | str | None = None,
    incluir_equivalentes_usd: bool = False,
) -> dict[str, Any]:
    """Genera el Balance de Comprobación agregado en PostgreSQL."""
    _validar_rango_fechas(fecha_desde, fecha_hasta)
    diario = _resolver_diario(empresa, id_diario)

    meta_usd, tasa_usd, usd_disponible, es_inversa = _metadata_moneda_y_usd(
        empresa,
        incluir_equivalentes_usd=incluir_equivalentes_usd,
        fecha_ref=fecha_hasta,
    )

    qs = DetalleAsiento.objects.filter(
        id_asiento__id_empresa=empresa,
        id_asiento__estado_asiento="APROBADO",
    )
    if diario is not None:
        qs = qs.filter(id_asiento__id_diario=diario)
    if fecha_hasta is not None:
        qs = qs.filter(id_asiento__fecha_asiento__lte=fecha_hasta)

    if fecha_desde is not None:
        agregados = qs.values(
            "id_cuenta_contable",
            "id_cuenta_contable__codigo_cuenta",
            "id_cuenta_contable__nombre_cuenta",
            "id_cuenta_contable__tipo_cuenta",
            "id_cuenta_contable__naturaleza",
            "id_cuenta_contable__nivel",
            "id_cuenta_contable__id_cuenta_padre",
        ).annotate(
            debe_inicial=Coalesce(Sum("debe", filter=Q(id_asiento__fecha_asiento__lt=fecha_desde)), _DEC_ZERO_EXPR),
            haber_inicial=Coalesce(Sum("haber", filter=Q(id_asiento__fecha_asiento__lt=fecha_desde)), _DEC_ZERO_EXPR),
            debe_periodo=Coalesce(Sum("debe", filter=Q(id_asiento__fecha_asiento__gte=fecha_desde)), _DEC_ZERO_EXPR),
            haber_periodo=Coalesce(Sum("haber", filter=Q(id_asiento__fecha_asiento__gte=fecha_desde)), _DEC_ZERO_EXPR),
        )
    else:
        agregados = qs.values(
            "id_cuenta_contable",
            "id_cuenta_contable__codigo_cuenta",
            "id_cuenta_contable__nombre_cuenta",
            "id_cuenta_contable__tipo_cuenta",
            "id_cuenta_contable__naturaleza",
            "id_cuenta_contable__nivel",
            "id_cuenta_contable__id_cuenta_padre",
        ).annotate(
            debe_inicial=_DEC_ZERO_EXPR,
            haber_inicial=_DEC_ZERO_EXPR,
            debe_periodo=Coalesce(Sum("debe"), _DEC_ZERO_EXPR),
            haber_periodo=Coalesce(Sum("haber"), _DEC_ZERO_EXPR),
        )

    filas = agregados.order_by("id_cuenta_contable__codigo_cuenta", "id_cuenta_contable")

    cuentas: list[dict[str, Any]] = []
    total_debe_inicial = _CERO
    total_haber_inicial = _CERO
    total_saldo_inicial_deudor = _CERO
    total_saldo_inicial_acreedor = _CERO
    total_debe = _CERO
    total_haber = _CERO
    total_debe_final_acum = _CERO
    total_haber_final_acum = _CERO
    total_saldo_final_deudor = _CERO
    total_saldo_final_acreedor = _CERO

    for fila in filas:
        debe_ini = _q2(fila["debe_inicial"])
        haber_ini = _q2(fila["haber_inicial"])
        debe_per = _q2(fila["debe_periodo"])
        haber_per = _q2(fila["haber_periodo"])

        saldo_ini = _q2(debe_ini - haber_ini)
        saldo_ini_deudor = saldo_ini if saldo_ini > _CERO else _CERO
        saldo_ini_acreedor = abs(saldo_ini) if saldo_ini < _CERO else _CERO

        debe_acum = _q2(debe_ini + debe_per)
        haber_acum = _q2(haber_ini + haber_per)
        saldo_final = _q2(debe_acum - haber_acum)
        saldo_fin_deudor = saldo_final if saldo_final > _CERO else _CERO
        saldo_fin_acreedor = abs(saldo_final) if saldo_final < _CERO else _CERO

        padre_id = fila["id_cuenta_contable__id_cuenta_padre"]
        item: dict[str, Any] = {
            "id_cuenta_contable": str(fila["id_cuenta_contable"]),
            "id_cuenta_padre": str(padre_id) if padre_id is not None else None,
            "codigo_cuenta": str(fila["id_cuenta_contable__codigo_cuenta"]),
            "nombre_cuenta": str(fila["id_cuenta_contable__nombre_cuenta"]),
            "tipo_cuenta": str(fila["id_cuenta_contable__tipo_cuenta"]),
            "naturaleza": str(fila["id_cuenta_contable__naturaleza"]),
            "nivel": int(fila["id_cuenta_contable__nivel"]),
            "debe_inicial": debe_ini,
            "haber_inicial": haber_ini,
            "saldo_inicial": saldo_ini,
            "saldo_inicial_deudor": saldo_ini_deudor,
            "saldo_inicial_acreedor": saldo_ini_acreedor,
            "debe": debe_per,
            "haber": haber_per,
            "debe_periodo": debe_per,
            "haber_periodo": haber_per,
            "debe_final_acum": debe_acum,
            "haber_final_acum": haber_acum,
            "saldo": saldo_final,
            "saldo_final_deudor": saldo_fin_deudor,
            "saldo_final_acreedor": saldo_fin_acreedor,
        }
        if incluir_equivalentes_usd:
            item.update(
                {
                    "debe_inicial_usd": _convertir_a_usd(debe_ini, tasa_usd, es_inversa=es_inversa)
                    if usd_disponible
                    else None,
                    "haber_inicial_usd": _convertir_a_usd(haber_ini, tasa_usd, es_inversa=es_inversa)
                    if usd_disponible
                    else None,
                    "saldo_inicial_usd": _convertir_a_usd(saldo_ini, tasa_usd, es_inversa=es_inversa)
                    if usd_disponible
                    else None,
                    "debe_usd": _convertir_a_usd(debe_per, tasa_usd, es_inversa=es_inversa)
                    if usd_disponible
                    else None,
                    "haber_usd": _convertir_a_usd(haber_per, tasa_usd, es_inversa=es_inversa)
                    if usd_disponible
                    else None,
                    "debe_final_acum_usd": _convertir_a_usd(debe_acum, tasa_usd, es_inversa=es_inversa)
                    if usd_disponible
                    else None,
                    "haber_final_acum_usd": _convertir_a_usd(haber_acum, tasa_usd, es_inversa=es_inversa)
                    if usd_disponible
                    else None,
                    "saldo_usd": _convertir_a_usd(saldo_final, tasa_usd, es_inversa=es_inversa)
                    if usd_disponible
                    else None,
                }
            )
        cuentas.append(item)

        total_debe_inicial = _q2(total_debe_inicial + debe_ini)
        total_haber_inicial = _q2(total_haber_inicial + haber_ini)
        total_saldo_inicial_deudor = _q2(total_saldo_inicial_deudor + saldo_ini_deudor)
        total_saldo_inicial_acreedor = _q2(total_saldo_inicial_acreedor + saldo_ini_acreedor)
        total_debe = _q2(total_debe + debe_per)
        total_haber = _q2(total_haber + haber_per)
        total_debe_final_acum = _q2(total_debe_final_acum + debe_acum)
        total_haber_final_acum = _q2(total_haber_final_acum + haber_acum)
        total_saldo_final_deudor = _q2(total_saldo_final_deudor + saldo_fin_deudor)
        total_saldo_final_acreedor = _q2(total_saldo_final_acreedor + saldo_fin_acreedor)

    cuadrado = total_debe == total_haber and total_debe_final_acum == total_haber_final_acum

    resultado: dict[str, Any] = {
        "empresa_id": str(empresa.pk),
        "fecha_desde": fecha_desde.isoformat() if fecha_desde is not None else None,
        "fecha_hasta": fecha_hasta.isoformat() if fecha_hasta is not None else None,
        "id_diario": str(diario.pk) if diario is not None else None,
        "diario_nombre": diario.nombre if diario is not None else "",
        **meta_usd,
        "cuentas": cuentas,
        "total_debe_inicial": total_debe_inicial,
        "total_haber_inicial": total_haber_inicial,
        "total_saldo_inicial_deudor": total_saldo_inicial_deudor,
        "total_saldo_inicial_acreedor": total_saldo_inicial_acreedor,
        "total_debe": total_debe,
        "total_haber": total_haber,
        "total_debe_periodo": total_debe,
        "total_haber_periodo": total_haber,
        "total_debe_final_acum": total_debe_final_acum,
        "total_haber_final_acum": total_haber_final_acum,
        "total_saldo_final_deudor": total_saldo_final_deudor,
        "total_saldo_final_acreedor": total_saldo_final_acreedor,
        "cuadrado": cuadrado,
    }
    if incluir_equivalentes_usd:
        resultado.update(
            {
                "total_debe_inicial_usd": _convertir_a_usd(total_debe_inicial, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "total_haber_inicial_usd": _convertir_a_usd(total_haber_inicial, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "total_saldo_inicial_deudor_usd": _convertir_a_usd(
                    total_saldo_inicial_deudor, tasa_usd, es_inversa=es_inversa
                )
                if usd_disponible
                else None,
                "total_saldo_inicial_acreedor_usd": _convertir_a_usd(
                    total_saldo_inicial_acreedor, tasa_usd, es_inversa=es_inversa
                )
                if usd_disponible
                else None,
                "total_debe_usd": _convertir_a_usd(total_debe, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "total_haber_usd": _convertir_a_usd(total_haber, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "total_debe_final_acum_usd": _convertir_a_usd(total_debe_final_acum, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "total_haber_final_acum_usd": _convertir_a_usd(total_haber_final_acum, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "total_saldo_final_deudor_usd": _convertir_a_usd(
                    total_saldo_final_deudor, tasa_usd, es_inversa=es_inversa
                )
                if usd_disponible
                else None,
                "total_saldo_final_acreedor_usd": _convertir_a_usd(
                    total_saldo_final_acreedor, tasa_usd, es_inversa=es_inversa
                )
                if usd_disponible
                else None,
            }
        )
    return resultado


def generar_estado_resultados(
    empresa: Empresa,
    *,
    fecha_desde: date,
    fecha_hasta: date,
    incluir_equivalentes_usd: bool = False,
) -> dict[str, Any]:
    """Genera el Estado de Resultados (P&L) excluyendo asientos de cierre anual."""
    _validar_rango_fechas(fecha_desde, fecha_hasta)

    meta_usd, tasa_usd, usd_disponible, es_inversa = _metadata_moneda_y_usd(
        empresa,
        incluir_equivalentes_usd=incluir_equivalentes_usd,
        fecha_ref=fecha_hasta,
    )

    filas = (
        DetalleAsiento.objects.filter(
            id_asiento__id_empresa=empresa,
            id_asiento__estado_asiento="APROBADO",
            id_asiento__es_cierre=False,
            id_asiento__fecha_asiento__gte=fecha_desde,
            id_asiento__fecha_asiento__lte=fecha_hasta,
            id_cuenta_contable__tipo_cuenta__in=["INGRESO", "COSTO", "GASTO"],
        )
        .values(
            "id_cuenta_contable",
            "id_cuenta_contable__codigo_cuenta",
            "id_cuenta_contable__nombre_cuenta",
            "id_cuenta_contable__tipo_cuenta",
            "id_cuenta_contable__naturaleza",
            "id_cuenta_contable__nivel",
            "id_cuenta_contable__id_cuenta_padre",
        )
        .annotate(
            sum_debe=Coalesce(Sum("debe"), _DEC_ZERO_EXPR),
            sum_haber=Coalesce(Sum("haber"), _DEC_ZERO_EXPR),
        )
        .order_by("id_cuenta_contable__codigo_cuenta", "id_cuenta_contable")
    )

    ingresos: list[dict[str, Any]] = []
    costos: list[dict[str, Any]] = []
    gastos: list[dict[str, Any]] = []

    total_ingresos = _CERO
    total_costos = _CERO
    total_gastos = _CERO

    for fila in filas:
        tipo = str(fila["id_cuenta_contable__tipo_cuenta"])
        debe = _q2(fila["sum_debe"])
        haber = _q2(fila["sum_haber"])
        neto = _q2(haber - debe) if tipo == "INGRESO" else _q2(debe - haber)
        padre_id = fila["id_cuenta_contable__id_cuenta_padre"]

        item: dict[str, Any] = {
            "id_cuenta_contable": str(fila["id_cuenta_contable"]),
            "id_cuenta_padre": str(padre_id) if padre_id is not None else None,
            "codigo_cuenta": str(fila["id_cuenta_contable__codigo_cuenta"]),
            "nombre_cuenta": str(fila["id_cuenta_contable__nombre_cuenta"]),
            "tipo_cuenta": tipo,
            "naturaleza": str(fila["id_cuenta_contable__naturaleza"]),
            "nivel": int(fila["id_cuenta_contable__nivel"]),
            "debe": debe,
            "haber": haber,
            "saldo": neto,
        }
        if incluir_equivalentes_usd:
            item["saldo_usd"] = _convertir_a_usd(neto, tasa_usd, es_inversa=es_inversa) if usd_disponible else None

        if tipo == "INGRESO":
            ingresos.append(item)
            total_ingresos = _q2(total_ingresos + neto)
        elif tipo == "COSTO":
            costos.append(item)
            total_costos = _q2(total_costos + neto)
        else:
            gastos.append(item)
            total_gastos = _q2(total_gastos + neto)

    utilidad_bruta = _q2(total_ingresos - total_costos)
    resultado_neto = _q2(total_ingresos - total_costos - total_gastos)

    resultado: dict[str, Any] = {
        "empresa_id": str(empresa.pk),
        "fecha_desde": fecha_desde.isoformat(),
        "fecha_hasta": fecha_hasta.isoformat(),
        **meta_usd,
        "ingresos": ingresos,
        "costos": costos,
        "gastos": gastos,
        "total_ingresos": total_ingresos,
        "total_costos": total_costos,
        "total_gastos": total_gastos,
        "utilidad_bruta": utilidad_bruta,
        "resultado_neto": resultado_neto,
    }
    if incluir_equivalentes_usd:
        resultado.update(
            {
                "total_ingresos_usd": _convertir_a_usd(total_ingresos, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "total_costos_usd": _convertir_a_usd(total_costos, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "total_gastos_usd": _convertir_a_usd(total_gastos, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "utilidad_bruta_usd": _convertir_a_usd(utilidad_bruta, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "resultado_neto_usd": _convertir_a_usd(resultado_neto, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
            }
        )
    return resultado


def generar_balance_general(
    empresa: Empresa,
    *,
    fecha_corte: date,
    incluir_equivalentes_usd: bool = False,
) -> dict[str, Any]:
    """Genera el Balance General acumulado hasta ``fecha_corte`` verificando la ecuación patrimonial."""
    meta_usd, tasa_usd, usd_disponible, es_inversa = _metadata_moneda_y_usd(
        empresa,
        incluir_equivalentes_usd=incluir_equivalentes_usd,
        fecha_ref=fecha_corte,
    )

    filas = (
        DetalleAsiento.objects.filter(
            id_asiento__id_empresa=empresa,
            id_asiento__estado_asiento="APROBADO",
            id_asiento__fecha_asiento__lte=fecha_corte,
        )
        .values(
            "id_cuenta_contable",
            "id_cuenta_contable__codigo_cuenta",
            "id_cuenta_contable__nombre_cuenta",
            "id_cuenta_contable__tipo_cuenta",
            "id_cuenta_contable__naturaleza",
            "id_cuenta_contable__nivel",
            "id_cuenta_contable__id_cuenta_padre",
        )
        .annotate(
            sum_debe=Coalesce(Sum("debe"), _DEC_ZERO_EXPR),
            sum_haber=Coalesce(Sum("haber"), _DEC_ZERO_EXPR),
        )
        .order_by("id_cuenta_contable__codigo_cuenta", "id_cuenta_contable")
    )

    activos: list[dict[str, Any]] = []
    pasivos: list[dict[str, Any]] = []
    patrimonio: list[dict[str, Any]] = []

    total_activos = _CERO
    total_pasivos = _CERO
    total_patrimonio = _CERO
    ingresos_no_cerrados = _CERO
    costos_gastos_no_cerrados = _CERO

    for fila in filas:
        tipo = str(fila["id_cuenta_contable__tipo_cuenta"])
        debe = _q2(fila["sum_debe"])
        haber = _q2(fila["sum_haber"])

        if tipo == "INGRESO":
            ingresos_no_cerrados = _q2(ingresos_no_cerrados + (haber - debe))
            continue
        if tipo in ("COSTO", "GASTO"):
            costos_gastos_no_cerrados = _q2(costos_gastos_no_cerrados + (debe - haber))
            continue

        saldo = _q2(debe - haber) if tipo == "ACTIVO" else _q2(haber - debe)
        padre_id = fila["id_cuenta_contable__id_cuenta_padre"]
        item: dict[str, Any] = {
            "id_cuenta_contable": str(fila["id_cuenta_contable"]),
            "id_cuenta_padre": str(padre_id) if padre_id is not None else None,
            "codigo_cuenta": str(fila["id_cuenta_contable__codigo_cuenta"]),
            "nombre_cuenta": str(fila["id_cuenta_contable__nombre_cuenta"]),
            "tipo_cuenta": tipo,
            "naturaleza": str(fila["id_cuenta_contable__naturaleza"]),
            "nivel": int(fila["id_cuenta_contable__nivel"]),
            "debe": debe,
            "haber": haber,
            "saldo": saldo,
        }
        if incluir_equivalentes_usd:
            item["saldo_usd"] = _convertir_a_usd(saldo, tasa_usd, es_inversa=es_inversa) if usd_disponible else None

        if tipo == "ACTIVO":
            activos.append(item)
            total_activos = _q2(total_activos + saldo)
        elif tipo == "PASIVO":
            pasivos.append(item)
            total_pasivos = _q2(total_pasivos + saldo)
        elif tipo == "PATRIMONIO":
            patrimonio.append(item)
            total_patrimonio = _q2(total_patrimonio + saldo)

    resultado_periodo = _q2(ingresos_no_cerrados - costos_gastos_no_cerrados)
    total_pasivo_patrimonio_y_resultado = _q2(total_pasivos + total_patrimonio + resultado_periodo)
    ecuacion_cuadrada = total_activos == total_pasivo_patrimonio_y_resultado

    resultado: dict[str, Any] = {
        "empresa_id": str(empresa.pk),
        "fecha_corte": fecha_corte.isoformat(),
        **meta_usd,
        "activos": activos,
        "pasivos": pasivos,
        "patrimonio": patrimonio,
        "total_activos": total_activos,
        "total_pasivos": total_pasivos,
        "total_patrimonio": total_patrimonio,
        "resultado_periodo": resultado_periodo,
        "total_pasivo_patrimonio_y_resultado": total_pasivo_patrimonio_y_resultado,
        "ecuacion_cuadrada": ecuacion_cuadrada,
    }
    if incluir_equivalentes_usd:
        resultado.update(
            {
                "total_activos_usd": _convertir_a_usd(total_activos, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "total_pasivos_usd": _convertir_a_usd(total_pasivos, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "total_patrimonio_usd": _convertir_a_usd(total_patrimonio, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "resultado_periodo_usd": _convertir_a_usd(resultado_periodo, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "total_pasivo_patrimonio_y_resultado_usd": _convertir_a_usd(
                    total_pasivo_patrimonio_y_resultado, tasa_usd, es_inversa=es_inversa
                )
                if usd_disponible
                else None,
            }
        )
    return resultado


def generar_libro_mayor_auxiliar(
    empresa: Empresa,
    *,
    id_cuenta_contable: PlanCuentas | uuid.UUID | str | None = None,
    id_contacto: Contacto | uuid.UUID | str | None = None,
    id_diario: DiarioContable | uuid.UUID | str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    limit: int = 1000,
    incluir_equivalentes_usd: bool = False,
) -> dict[str, Any]:
    """Genera el Libro Mayor Auxiliar con saldo inicial SQL y saldo corrido en ``Decimal``."""
    _validar_rango_fechas(fecha_desde, fecha_hasta)
    if limit < 1 or limit > 5000:
        raise ReporteContableError("El parámetro limit debe estar entre 1 y 5000.")

    cuenta = _resolver_cuenta(empresa, id_cuenta_contable)
    contacto = _resolver_contacto(empresa, id_contacto)
    diario = _resolver_diario(empresa, id_diario)

    meta_usd, tasa_usd, usd_disponible, es_inversa = _metadata_moneda_y_usd(
        empresa,
        incluir_equivalentes_usd=incluir_equivalentes_usd,
        fecha_ref=fecha_hasta,
    )

    base_qs = DetalleAsiento.objects.filter(
        id_asiento__id_empresa=empresa,
        id_asiento__estado_asiento="APROBADO",
    )
    if cuenta is not None:
        base_qs = base_qs.filter(id_cuenta_contable=cuenta)
    if contacto is not None:
        base_qs = base_qs.filter(id_contacto=contacto)
    if diario is not None:
        base_qs = base_qs.filter(id_asiento__id_diario=diario)

    saldo_inicial = _CERO
    if fecha_desde is not None:
        agg_ini = base_qs.filter(id_asiento__fecha_asiento__lt=fecha_desde).aggregate(
            sum_debe=Coalesce(Sum("debe"), _DEC_ZERO_EXPR),
            sum_haber=Coalesce(Sum("haber"), _DEC_ZERO_EXPR),
        )
        saldo_inicial = _q2(_q2(agg_ini["sum_debe"]) - _q2(agg_ini["sum_haber"]))

    periodo_qs = base_qs
    if fecha_desde is not None:
        periodo_qs = periodo_qs.filter(id_asiento__fecha_asiento__gte=fecha_desde)
    if fecha_hasta is not None:
        periodo_qs = periodo_qs.filter(id_asiento__fecha_asiento__lte=fecha_hasta)

    rows = list(
        periodo_qs.select_related(
            "id_asiento",
            "id_asiento__id_diario",
            "id_cuenta_contable",
            "id_contacto",
        ).order_by("id_asiento__fecha_asiento", "id_asiento__fecha_creacion", "pk")[: limit + 1]
    )
    truncado = len(rows) > limit
    if truncado:
        rows = rows[:limit]

    movimientos: list[dict[str, Any]] = []
    corrido = saldo_inicial
    total_debe = _CERO
    total_haber = _CERO

    for det in rows:
        debe = _q2(det.debe)
        haber = _q2(det.haber)
        corrido = _q2(corrido + debe - haber)
        total_debe = _q2(total_debe + debe)
        total_haber = _q2(total_haber + haber)

        asiento = det.id_asiento
        diario_det = asiento.id_diario
        cuenta_det = det.id_cuenta_contable
        contacto_det = det.id_contacto

        mov: dict[str, Any] = {
            "id_detalle_asiento": str(det.pk),
            "id_asiento": str(asiento.pk),
            "fecha_asiento": asiento.fecha_asiento.isoformat(),
            "numero_asiento": asiento.numero_asiento,
            "descripcion_asiento": asiento.descripcion,
            "descripcion_detalle": det.descripcion_detalle or "",
            "id_diario": str(diario_det.pk) if diario_det is not None else None,
            "diario_codigo": diario_det.codigo if diario_det is not None else "",
            "diario_nombre": diario_det.nombre if diario_det is not None else "",
            "id_cuenta_contable": str(cuenta_det.pk),
            "codigo_cuenta": cuenta_det.codigo_cuenta,
            "nombre_cuenta": cuenta_det.nombre_cuenta,
            "id_contacto": str(contacto_det.pk) if contacto_det is not None else None,
            "contacto_nombre": contacto_det.nombre_completo if contacto_det is not None else "",
            "debe": debe,
            "haber": haber,
            "saldo_corrido": corrido,
        }
        if incluir_equivalentes_usd:
            mov.update(
                {
                    "debe_usd": _convertir_a_usd(debe, tasa_usd, es_inversa=es_inversa) if usd_disponible else None,
                    "haber_usd": _convertir_a_usd(haber, tasa_usd, es_inversa=es_inversa) if usd_disponible else None,
                    "saldo_corrido_usd": _convertir_a_usd(corrido, tasa_usd, es_inversa=es_inversa)
                    if usd_disponible
                    else None,
                }
            )
        movimientos.append(mov)

    saldo_final = corrido

    resultado: dict[str, Any] = {
        "empresa_id": str(empresa.pk),
        "fecha_desde": fecha_desde.isoformat() if fecha_desde is not None else None,
        "fecha_hasta": fecha_hasta.isoformat() if fecha_hasta is not None else None,
        "id_cuenta_contable": str(cuenta.pk) if cuenta is not None else None,
        "cuenta_label": f"{cuenta.codigo_cuenta} — {cuenta.nombre_cuenta}" if cuenta is not None else "",
        "id_contacto": str(contacto.pk) if contacto is not None else None,
        "contacto_label": contacto.nombre_completo if contacto is not None else "",
        "id_diario": str(diario.pk) if diario is not None else None,
        "diario_label": f"{diario.codigo} — {diario.nombre}" if diario is not None else "",
        "limit": limit,
        **meta_usd,
        "saldo_inicial": saldo_inicial,
        "total_debe": total_debe,
        "total_haber": total_haber,
        "saldo_final": saldo_final,
        "truncado": truncado,
        "movimientos": movimientos,
    }
    if incluir_equivalentes_usd:
        resultado.update(
            {
                "saldo_inicial_usd": _convertir_a_usd(saldo_inicial, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "total_debe_usd": _convertir_a_usd(total_debe, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "total_haber_usd": _convertir_a_usd(total_haber, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
                "saldo_final_usd": _convertir_a_usd(saldo_final, tasa_usd, es_inversa=es_inversa)
                if usd_disponible
                else None,
            }
        )
    return resultado
