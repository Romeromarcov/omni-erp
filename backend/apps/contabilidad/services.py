"""
Servicio central de asientos contables automáticos, diarios, contra-asientos y cierre (R-CODE-11).

Uso:
    from apps.contabilidad.services import generar_asiento

    @transaction.atomic
    def aprobar_factura(factura, empresa):
        factura.estado = 'EMITIDA'
        factura.save()
        generar_asiento('FACTURA_VENTA', factura, empresa)  # falla → revierte todo

generar_asiento() se llama SIEMPRE dentro de la misma @transaction.atomic que el
documento origen. Si el asiento no puede crearse, toda la transacción se revierte.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    AMBITO_CONTABLE_CHOICES,
    AsientoContable,
    CentroCosto,
    DetalleAsiento,
    DiarioContable,
    MapeoContable,
    PeriodoContable,
    PlanCuentas,
)

if TYPE_CHECKING:
    from apps.core.models import Contacto, Empresa, Usuarios

_AMBITOS_VALIDOS = frozenset(k for k, _ in AMBITO_CONTABLE_CHOICES)
_CENT = Decimal("0.01")

logger = logging.getLogger(__name__)

# ── Tipos soportados ──────────────────────────────────────────────────────────

TIPOS_ASIENTO = frozenset(
    {
        "FACTURA_VENTA",
        "FACTURA_VENTA_IVA",  # CTF-001: asiento separado para el IVA
        "NOTA_VENTA",  # CTF-001: asiento al confirmar nota de venta
        "DEVOLUCION_VENTA",  # 1.G: reverso de la venta (espejo del asiento de venta)
        "DEVOLUCION_VENTA_IVA",  # 1.G: reverso del IVA débito fiscal de la factura
        "FACTURA_COMPRA",
        "GASTO",  # Gasto aprobado → DR Cuenta Gasto / CR CxP o Banco
        "GASTO_IVA",  # Porción IVA crédito fiscal del gasto (asiento separado)
        "RECEPCION_MERCANCIA",
        "COSTO_VENTA",  # COGS: DR Costo de Ventas / CR Inventario al despachar venta
        "AJUSTE_INVENTARIO",
        "SALIDA_INTERNA",
        "PAGO_CXC",
        "PAGO_CXP",
        "GANANCIA_CAMBIARIA",  # Diferencia en cambio favorable al pagar una CxP en divisa
        "PERDIDA_CAMBIARIA",  # Diferencia en cambio desfavorable al pagar una CxP en divisa
        "NOMINA",  # CTF-013: asiento del proceso de nómina LOTTT
        "CAMBIO_DIVISA",  # CTF-013: asiento de la operación de cambio de divisa
        "PAGO_TERCERO",  # Capa B §6.6: pago de terceros (Zelle) — abono CxP / reintegro
        "PAGO_PARAFISCAL",  # Capa B §6.7: pago de contribución parafiscal (IVSS/FAOV/INCES…)
    }
)

_TIPO_ASIENTO_TO_DIARIO: dict[str, str] = {
    "FACTURA_VENTA": "VENTAS",
    "FACTURA_VENTA_IVA": "VENTAS",
    "NOTA_VENTA": "VENTAS",
    "DEVOLUCION_VENTA": "VENTAS",
    "DEVOLUCION_VENTA_IVA": "VENTAS",
    "COSTO_VENTA": "VENTAS",
    "PAGO_CXC": "VENTAS",
    "FACTURA_COMPRA": "COMPRAS",
    "GASTO": "COMPRAS",
    "GASTO_IVA": "COMPRAS",
    "RECEPCION_MERCANCIA": "COMPRAS",
    "PAGO_CXP": "COMPRAS",
    "PAGO_TERCERO": "COMPRAS",
    "NOMINA": "NOMINA",
    "PAGO_PARAFISCAL": "NOMINA",
    "CAMBIO_DIVISA": "BANCO",
}


# ── Excepciones ───────────────────────────────────────────────────────────────


class AsientoError(Exception):
    pass


class MapeoContableNoEncontrado(AsientoError):
    pass


class PeriodoContableCerradoError(AsientoError):
    pass


# ── Validación de período contable / fiscal ───────────────────────────────────


def validar_periodo_contable_abierto(empresa: Empresa, fecha: date) -> None:
    """Valida que el período (contable y fiscal) correspondiente a ``fecha`` esté abierto."""
    from apps.fiscal.services import PeriodoCerradoError, validar_periodo_abierto

    if PeriodoContable.esta_cerrado(empresa, fecha.year, fecha.month):
        raise PeriodoContableCerradoError(
            f"El período contable {fecha.year:04d}-{fecha.month:02d} está cerrado; "
            "no se pueden registrar ni aprobar asientos en ese período."
        )

    try:
        validar_periodo_abierto(empresa, fecha)
    except PeriodoCerradoError as exc:
        raise PeriodoContableCerradoError(str(exc)) from exc


# ── R-CODE-11 centralizado ────────────────────────────────────────────────────


def generar_asiento_o_fallar(
    tipo: str,
    documento: Any,
    empresa: Empresa | None = None,
    monto: Decimal | None = None,
    usuario: Usuarios | None = None,
    *,
    ambito: str | None = None,
    centro_costo: CentroCosto | None = None,
) -> tuple[AsientoContable | None, str | None]:
    """Aplica la política R-CODE-11 de forma uniforme en todos los callsites.

    - ``AsientoError`` (descuadre, período cerrado, error real del asiento)
      **siempre** se propaga, rompiendo la ``@transaction.atomic`` del documento origen.
    - ``MapeoContableNoEncontrado``:
        * si ``empresa.contabilidad_activa`` es True → se re-lanza como
          ``AsientoError`` (error duro: la empresa exige contabilidad y falta el
          mapeo, no se puede continuar);
        * si es False (bodega informal, R-PROD-3) → se loguea un warning y la
          operación continúa sin asiento.

    Returns:
        (asiento|None, asiento_error_str|None)
    """
    empresa_resuelta = empresa if empresa is not None else _extraer_empresa(documento)
    try:
        asiento = generar_asiento(
            tipo,
            documento,
            empresa_resuelta,
            monto=monto,
            usuario=usuario,
            ambito=ambito,
            centro_costo=centro_costo,
        )
        return asiento, None
    except MapeoContableNoEncontrado as exc:
        if getattr(empresa_resuelta, "contabilidad_activa", False):
            raise AsientoError(
                f"Configure el Mapeo Contable antes de continuar (contabilidad activa, {tipo}): {exc}"
            ) from exc
        logger.warning(
            "Asiento omitido (sin mapeo, contabilidad inactiva) | tipo=%s | empresa=%s | razón=%s",
            tipo,
            getattr(empresa_resuelta, "pk", None),
            exc,
        )
        return None, str(exc)


# ── Helpers internos ──────────────────────────────────────────────────────────


def _extraer_empresa(documento: Any) -> Any:
    for attr in ("id_empresa", "empresa"):
        val = getattr(documento, attr, None)
        if val is not None:
            return val
    raise AsientoError(f"No se pudo extraer empresa de {documento.__class__.__name__}")


def _extraer_monto(documento: Any) -> Decimal:
    for attr in ("monto_total", "total", "monto", "subtotal", "base_imponible"):
        val = getattr(documento, attr, None)
        if val is not None:
            return Decimal(str(val))
    raise AsientoError(f"No se pudo extraer monto de {documento.__class__.__name__}")


def _numero_asiento(tipo: str) -> str:
    fecha = timezone.localdate().strftime("%Y%m%d")  # M-BUG-12: TZ-aware
    sufijo = uuid.uuid4().hex[:8].upper()
    return f"AST-{tipo[:4]}-{fecha}-{sufijo}"


def _numero_contra_asiento(asiento_original: AsientoContable, fecha: date | None = None) -> str:
    fecha_str = (fecha or timezone.localdate()).strftime("%Y%m%d")
    sufijo = uuid.uuid4().hex[:8].upper()
    return f"REV-{fecha_str}-{sufijo}-{asiento_original.numero_asiento[:40]}"[:100]


def _siguiente_numero_asiento(tipo: str, diario: DiarioContable | None) -> str:
    """Genera un número de asiento usando la secuencia atómica del diario si tiene prefijo."""
    if diario is not None and (diario.prefijo_secuencia or "").strip():
        prefijo = diario.prefijo_secuencia.strip()
        diario_locked = DiarioContable.objects.select_for_update().get(pk=diario.pk)
        numero_seq = int(diario_locked.siguiente_numero)
        candidato = f"{prefijo}-{numero_seq:06d}"
        while AsientoContable.objects.filter(
            id_empresa_id=diario_locked.id_empresa_id,
            numero_asiento=candidato,
        ).exists():
            numero_seq += 1
            candidato = f"{prefijo}-{numero_seq:06d}"
        diario_locked.siguiente_numero = numero_seq + 1
        diario_locked.save(update_fields=["siguiente_numero", "fecha_actualizacion"])
        diario.siguiente_numero = diario_locked.siguiente_numero
        return candidato
    return _numero_asiento(tipo)


def _resolver_diario_para_asiento(
    empresa: Empresa,
    tipo: str,
    mapeo: MapeoContable | None = None,
) -> DiarioContable | None:
    if mapeo is not None and mapeo.id_diario_id is not None:
        diario_mapeo = mapeo.id_diario
        if diario_mapeo is not None and diario_mapeo.activo and diario_mapeo.id_empresa_id == empresa.pk:
            return diario_mapeo
    tipo_diario = _TIPO_ASIENTO_TO_DIARIO.get(tipo, "VARIOS")
    return DiarioContable.objects.filter(id_empresa=empresa, tipo=tipo_diario, activo=True).order_by("codigo").first()


def _contacto_valido_empresa(candidato: Any, empresa: Empresa) -> Contacto | None:
    from apps.core.models import Contacto

    if isinstance(candidato, Contacto) and candidato.id_empresa_id == empresa.pk and candidato.activo:
        return candidato
    return None


def _resolver_contacto_documento_asiento(documento: Any, empresa: Empresa) -> Contacto | None:
    """Extrae el ``core.Contacto`` asociado al documento origen dentro de ``empresa``."""
    if documento is None:
        return None

    directo = _contacto_valido_empresa(getattr(documento, "id_contacto", None), empresa)
    if directo is not None:
        return directo

    cliente = getattr(documento, "id_cliente", None)
    if cliente is not None:
        c_cli = _contacto_valido_empresa(getattr(cliente, "contacto", None), empresa)
        if c_cli is not None:
            return c_cli

    proveedor = getattr(documento, "id_proveedor", None)
    if proveedor is not None:
        c_prov = _contacto_valido_empresa(getattr(proveedor, "contacto", None), empresa)
        if c_prov is not None:
            return c_prov

    orden = getattr(documento, "id_orden_compra", None)
    if orden is not None:
        prov_orden = getattr(orden, "id_proveedor", None)
        c_ord = _contacto_valido_empresa(getattr(prov_orden, "contacto", None), empresa)
        if c_ord is not None:
            return c_ord

    cxc = getattr(documento, "cuenta_por_cobrar", None)
    if cxc is not None:
        cli_cxc = getattr(cxc, "cliente", None)
        c_cxc = _contacto_valido_empresa(getattr(cli_cxc, "contacto", None), empresa)
        if c_cxc is not None:
            return c_cxc

    cxp = getattr(documento, "cuenta_por_pagar", None)
    if cxp is not None:
        prov_cxp = getattr(cxp, "id_proveedor", None)
        c_cxp = _contacto_valido_empresa(getattr(prov_cxp, "contacto", None), empresa)
        if c_cxp is not None:
            return c_cxp

    abono_cxp = getattr(documento, "id_abono_cxp", None)
    if abono_cxp is not None:
        cxp_abono = getattr(abono_cxp, "cuenta_por_pagar", None)
        if cxp_abono is not None:
            prov_dif = getattr(cxp_abono, "id_proveedor", None)
            c_dif = _contacto_valido_empresa(getattr(prov_dif, "contacto", None), empresa)
            if c_dif is not None:
                return c_dif

    casa = getattr(documento, "casa_de_cambio", None)
    if casa is not None:
        c_casa = _contacto_valido_empresa(getattr(casa, "contacto", None), empresa)
        if c_casa is not None:
            return c_casa

    return None


def _descripcion(plantilla: str, tipo: str, documento: Any) -> str:
    desc = plantilla.replace("{tipo}", tipo)
    for attr in ("numero_factura", "numero_orden", "numero_nota", "numero_recepcion", "numero_pedido"):
        val = getattr(documento, attr, None)
        if val:
            return desc.replace("{numero}", str(val))
    return desc.replace("{numero}", str(documento.pk)[:8])


def _resolver_ambito_asiento(
    ambito: str | None,
    documento: Any,
    diario: DiarioContable | None,
) -> str:
    """Resuelve y valida el ámbito dual del asiento (``FISCAL`` o ``GERENCIAL``)."""
    candidato = ambito
    if not candidato and documento is not None:
        doc_ambito = getattr(documento, "ambito", None)
        if isinstance(doc_ambito, str) and doc_ambito.strip():
            candidato = doc_ambito
    if not candidato and diario is not None:
        candidato = getattr(diario, "ambito", None)
    normalizado = str(candidato or "FISCAL").strip().upper()
    if normalizado not in _AMBITOS_VALIDOS:
        raise AsientoError(f"Ámbito contable inválido: {candidato!r}. Válidos: {sorted(_AMBITOS_VALIDOS)}")
    return normalizado


def _calcular_importes_trimonetarios_linea(
    empresa: Empresa,
    monto_base: Decimal,
    fecha: date,
) -> dict[str, Decimal | None]:
    """Calcula importes Base, País/Fiscal (BCV) y Referencia + tasas aplicadas."""
    base_q = monto_base.quantize(_CENT, rounding=ROUND_HALF_UP)
    moneda_base = getattr(empresa, "id_moneda_base", None)
    moneda_pais_id = getattr(empresa, "id_moneda_pais_id", None)

    if moneda_base is None:
        return {
            "base": base_q,
            "pais": base_q
            if moneda_pais_id is not None and moneda_pais_id == getattr(empresa, "id_moneda_base_id", None)
            else None,
            "referencia": None,
            "tasa_bcv": None,
            "tasa_referencia": None,
        }

    try:
        from apps.finanzas.services import TasaCambioError
        from apps.finanzas.services_trimonetario import calcular_equivalencias_trimonetarias

        eq = calcular_equivalencias_trimonetarias(base_q, moneda_base, empresa=empresa, fecha=fecha)
        m_pais = eq.get("monto_pais_fiscal")
        m_ref = eq.get("monto_referencia")
        t_pais = eq.get("tasa_pais_fiscal")
        t_ref = eq.get("tasa_referencia")
        return {
            "base": base_q,
            "pais": Decimal(str(m_pais)).quantize(_CENT, rounding=ROUND_HALF_UP) if m_pais is not None else None,
            "referencia": Decimal(str(m_ref)).quantize(_CENT, rounding=ROUND_HALF_UP) if m_ref is not None else None,
            "tasa_bcv": Decimal(str(t_pais["valor_tasa"]))
            if isinstance(t_pais, dict) and t_pais.get("valor_tasa") is not None
            else None,
            "tasa_referencia": Decimal(str(t_ref["valor_tasa"]))
            if isinstance(t_ref, dict) and t_ref.get("valor_tasa") is not None
            else None,
        }
    except TasaCambioError:
        return {
            "base": base_q,
            "pais": base_q
            if moneda_pais_id is not None and moneda_pais_id == getattr(empresa, "id_moneda_base_id", None)
            else None,
            "referencia": None,
            "tasa_bcv": None,
            "tasa_referencia": None,
        }


# ── Generación, aprobación y reversión de asientos ────────────────────────────


@transaction.atomic
def generar_asiento(
    tipo: str,
    documento: Any,
    empresa: Empresa | None = None,
    monto: Decimal | None = None,
    usuario: Usuarios | None = None,
    *,
    ambito: str | None = None,
    centro_costo: CentroCosto | None = None,
) -> AsientoContable:
    """
    Crea un AsientoContable con dos líneas (debe/haber) para el documento dado.
    """
    if tipo not in TIPOS_ASIENTO:
        raise AsientoError(f"Tipo desconocido: {tipo!r}. Válidos: {sorted(TIPOS_ASIENTO)}")

    if empresa is None:
        empresa = _extraer_empresa(documento)

    assert empresa is not None  # narrowing para mypy tras _extraer_empresa

    if centro_costo is not None and centro_costo.id_empresa_id != empresa.pk:
        raise AsientoError("El centro de costo no pertenece a la empresa del asiento.")

    if monto is None:
        monto = _extraer_monto(documento)
    else:
        monto = Decimal(str(monto))
    if monto <= Decimal("0"):
        raise AsientoError(f"El monto del asiento debe ser mayor a cero. Obtenido: {monto}")

    fecha = timezone.localdate()
    validar_periodo_contable_abierto(empresa, fecha)

    try:
        mapeo = MapeoContable.objects.select_related("cuenta_debe", "cuenta_haber", "id_diario").get(
            id_empresa=empresa, tipo_asiento=tipo, activo=True
        )
    except MapeoContable.DoesNotExist:
        raise MapeoContableNoEncontrado(
            f"No hay MapeoContable activo para empresa={empresa.pk!s:.8}, tipo={tipo!r}. "
            "Configure el mapeo en Contabilidad → Configuración de Mapeos."
        )

    diario = _resolver_diario_para_asiento(empresa, tipo, mapeo)
    ambito_resuelto = _resolver_ambito_asiento(ambito, documento, diario)
    descripcion = _descripcion(mapeo.descripcion_plantilla, tipo, documento)
    numero = _siguiente_numero_asiento(tipo, diario)
    contacto = _resolver_contacto_documento_asiento(documento, empresa)
    trimo = _calcular_importes_trimonetarios_linea(empresa, monto, fecha)
    cero = Decimal("0.00")

    asiento = AsientoContable.objects.create(
        id_empresa=empresa,
        id_diario=diario,
        ambito=ambito_resuelto,
        fecha_asiento=fecha,
        numero_asiento=numero,
        descripcion=descripcion,
        id_documento_origen=documento.pk,
        nombre_modelo_origen=documento.__class__.__name__,
        estado_asiento="BORRADOR",
        id_usuario_registro=usuario,
    )

    DetalleAsiento.objects.create(
        id_asiento=asiento,
        id_cuenta_contable=mapeo.cuenta_debe,
        id_contacto=contacto,
        id_centro_costo=centro_costo,
        debe=monto,
        haber=Decimal("0"),
        debe_base=trimo["base"],
        haber_base=cero,
        debe_pais=trimo["pais"],
        haber_pais=cero if trimo["pais"] is not None else None,
        debe_referencia=trimo["referencia"],
        haber_referencia=cero if trimo["referencia"] is not None else None,
        tasa_bcv_aplicada=trimo["tasa_bcv"],
        tasa_referencia_aplicada=trimo["tasa_referencia"],
        descripcion_detalle=descripcion,
    )
    DetalleAsiento.objects.create(
        id_asiento=asiento,
        id_cuenta_contable=mapeo.cuenta_haber,
        id_contacto=contacto,
        id_centro_costo=centro_costo,
        debe=Decimal("0"),
        haber=monto,
        debe_base=cero,
        haber_base=trimo["base"],
        debe_pais=cero if trimo["pais"] is not None else None,
        haber_pais=trimo["pais"],
        debe_referencia=cero if trimo["referencia"] is not None else None,
        haber_referencia=trimo["referencia"],
        tasa_bcv_aplicada=trimo["tasa_bcv"],
        tasa_referencia_aplicada=trimo["tasa_referencia"],
        descripcion_detalle=descripcion,
    )

    if getattr(empresa, "contabilidad_auto_aprobar", False):
        asiento.estado_asiento = "APROBADO"
        asiento.save(update_fields=["estado_asiento"])

    return asiento


@transaction.atomic
def aprobar_asiento(asiento: AsientoContable, *, usuario: Usuarios | None = None) -> AsientoContable:
    """Aprueba atómicamente un asiento en ``BORRADOR`` tras validar período y cuadre."""
    del usuario  # reservado para trazabilidad futura
    asiento_locked = (
        AsientoContable.objects.select_for_update(of=("self",)).select_related("id_empresa").get(pk=asiento.pk)
    )

    if asiento_locked.estado_asiento != "BORRADOR":
        raise AsientoError("Solo se pueden aprobar asientos en estado borrador")

    validar_periodo_contable_abierto(asiento_locked.id_empresa, asiento_locked.fecha_asiento)

    detalles_qs = DetalleAsiento.objects.filter(id_asiento=asiento_locked)
    if detalles_qs.count() < 2:
        raise AsientoError("El asiento debe tener al menos dos líneas contables para aprobarse.")

    agregados = detalles_qs.aggregate(
        total_debe=Coalesce(Sum("debe"), Decimal("0.00")),
        total_haber=Coalesce(Sum("haber"), Decimal("0.00")),
    )
    total_debe = Decimal(str(agregados["total_debe"]))
    total_haber = Decimal(str(agregados["total_haber"]))

    if total_debe != total_haber:
        raise AsientoError(f"El asiento no cuadra. Debe: {total_debe}, Haber: {total_haber}")
    if total_debe <= Decimal("0.00"):
        raise AsientoError("El asiento debe tener un total mayor a cero para aprobarse.")

    asiento_locked.estado_asiento = "APROBADO"
    asiento_locked.save(update_fields=["estado_asiento"])
    return asiento_locked


@transaction.atomic
def revertir_asiento(
    asiento: AsientoContable,
    *,
    usuario: Usuarios | None = None,
    fecha_reversion: date | None = None,
    motivo: str = "",
) -> AsientoContable:
    """Genera un contra-asiento ``APROBADO`` con debe/haber invertidos para un asiento ``APROBADO``."""
    asiento_locked = (
        AsientoContable.objects.select_for_update(of=("self",))
        .select_related("id_empresa", "id_diario")
        .get(pk=asiento.pk)
    )

    if asiento_locked.estado_asiento != "APROBADO":
        raise AsientoError("Solo se pueden revertir asientos en estado APROBADO.")

    if asiento_locked.asiento_revertido_id is not None:
        raise AsientoError("No se puede revertir un contra-asiento.")

    if AsientoContable.objects.filter(asiento_revertido=asiento_locked).exists():
        raise AsientoError("El asiento ya fue revertido.")

    fecha_rev = fecha_reversion or timezone.localdate()
    validar_periodo_contable_abierto(asiento_locked.id_empresa, fecha_rev)

    detalles = list(
        DetalleAsiento.objects.select_related("id_cuenta_contable", "id_contacto")
        .filter(id_asiento=asiento_locked)
        .order_by("fecha_creacion", "pk")
    )
    if not detalles:
        raise AsientoError(f"El asiento {asiento_locked.numero_asiento} no tiene detalles para revertir.")

    total_orig_debe = sum((Decimal(str(d.debe)) for d in detalles), Decimal("0.00"))
    total_orig_haber = sum((Decimal(str(d.haber)) for d in detalles), Decimal("0.00"))
    if total_orig_debe != total_orig_haber:
        raise AsientoError(
            f"El asiento {asiento_locked.numero_asiento} está descuadrado ({total_orig_debe} != {total_orig_haber})."
        )

    diario = asiento_locked.id_diario
    if diario is not None and diario.activo and (diario.prefijo_secuencia or "").strip():
        numero_contra = _siguiente_numero_asiento("REV", diario)
    else:
        numero_contra = _numero_contra_asiento(asiento_locked, fecha=fecha_rev)

    desc_contra = f"Contra-asiento reversión {asiento_locked.numero_asiento}"
    motivo_limpio = (motivo or "").strip()
    if motivo_limpio:
        desc_contra = f"{desc_contra} — {motivo_limpio}"

    contra = AsientoContable.objects.create(
        id_empresa=asiento_locked.id_empresa,
        id_diario=diario,
        ambito=asiento_locked.ambito,
        asiento_revertido=asiento_locked,
        fecha_asiento=fecha_rev,
        numero_asiento=numero_contra,
        descripcion=desc_contra,
        id_documento_origen=asiento_locked.id_documento_origen,
        nombre_modelo_origen=asiento_locked.nombre_modelo_origen,
        estado_asiento="APROBADO",
        id_usuario_registro=usuario,
    )

    total_rev_debe = Decimal("0.00")
    total_rev_haber = Decimal("0.00")
    for det in detalles:
        rev_debe = Decimal(str(det.haber))
        rev_haber = Decimal(str(det.debe))
        DetalleAsiento.objects.create(
            id_asiento=contra,
            id_cuenta_contable=det.id_cuenta_contable,
            id_contacto=det.id_contacto,
            id_centro_costo=det.id_centro_costo,
            debe=rev_debe,
            haber=rev_haber,
            debe_base=det.haber_base,
            haber_base=det.debe_base,
            debe_pais=det.haber_pais,
            haber_pais=det.debe_pais,
            debe_referencia=det.haber_referencia,
            haber_referencia=det.debe_referencia,
            tasa_bcv_aplicada=det.tasa_bcv_aplicada,
            tasa_referencia_aplicada=det.tasa_referencia_aplicada,
            descripcion_detalle=f"Reversión: {det.descripcion_detalle or asiento_locked.descripcion}",
        )
        total_rev_debe += rev_debe
        total_rev_haber += rev_haber

    if total_rev_debe != total_rev_haber:
        raise AsientoError("El contra-asiento de reversión quedó descuadrado.")

    return contra


# ── Períodos contables y cierre de ejercicio ──────────────────────────────────


def _validar_anio_mes(anio: int, mes: int | None = None) -> None:
    if anio < 1900 or anio > 2100:
        raise AsientoError(f"Año contable fuera de rango válido: {anio}.")
    if mes is not None and (mes < 1 or mes > 12):
        raise AsientoError(f"Mes contable inválido: {mes}. Debe estar entre 1 y 12.")


@transaction.atomic
def cerrar_periodo_contable(
    empresa: Empresa,
    anio: int,
    mes: int,
    *,
    usuario: Usuarios | None = None,
    observaciones: str = "",
) -> PeriodoContable:
    """Cierra el período mensual ``(empresa, anio, mes)`` exigiendo cero borradores."""
    _validar_anio_mes(anio, mes)

    borradores = AsientoContable.objects.filter(
        id_empresa=empresa,
        fecha_asiento__year=anio,
        fecha_asiento__month=mes,
        estado_asiento="BORRADOR",
    ).count()
    if borradores > 0:
        raise AsientoError(
            f"No se puede cerrar el período {anio:04d}-{mes:02d}: existen {borradores} "
            "asiento(s) en estado BORRADOR. Apruébelos o anúlelos antes de cerrar."
        )

    periodo, _ = PeriodoContable.objects.get_or_create(
        id_empresa=empresa,
        anio=anio,
        mes=mes,
    )
    periodo_locked = PeriodoContable.objects.select_for_update().get(pk=periodo.pk)
    if periodo_locked.estado == "CERRADO" and periodo_locked.activo:
        return periodo_locked

    periodo_locked.activo = True
    periodo_locked.estado = "CERRADO"
    periodo_locked.fecha_cierre = timezone.now()
    periodo_locked.cerrado_por = usuario
    if observaciones and observaciones.strip():
        periodo_locked.observaciones = observaciones.strip()
    periodo_locked.save(
        update_fields=["activo", "estado", "fecha_cierre", "cerrado_por", "observaciones", "fecha_actualizacion"]
    )
    return periodo_locked


@transaction.atomic
def reabrir_periodo_contable(
    periodo: PeriodoContable,
    *,
    usuario: Usuarios | None = None,
    motivo: str = "",
) -> PeriodoContable:
    """Reabre un período contable cerrado salvo si está ligado a un cierre anual activo."""
    del usuario
    periodo_locked = (
        PeriodoContable.objects.select_for_update(of=("self",)).select_related("asiento_cierre").get(pk=periodo.pk)
    )
    if periodo_locked.estado != "CERRADO":
        raise AsientoError(f"El período {periodo_locked.anio:04d}-{periodo_locked.mes:02d} ya se encuentra abierto.")

    asiento_cierre = periodo_locked.asiento_cierre
    if asiento_cierre is not None:
        cierre_activo = (
            asiento_cierre.estado_asiento == "APROBADO"
            and not AsientoContable.objects.filter(asiento_revertido=asiento_cierre).exists()
        )
        if cierre_activo:
            raise AsientoError(
                f"No se puede reabrir el período {periodo_locked.anio:04d}-{periodo_locked.mes:02d} "
                "porque pertenece a un ejercicio cerrado con asiento de cierre activo."
            )
        periodo_locked.asiento_cierre = None

    periodo_locked.estado = "ABIERTO"
    periodo_locked.fecha_cierre = None
    periodo_locked.cerrado_por = None
    motivo_limpio = (motivo or "").strip()
    if motivo_limpio:
        nota = f"Reapertura: {motivo_limpio}"
        periodo_locked.observaciones = (
            f"{periodo_locked.observaciones}\n{nota}".strip() if periodo_locked.observaciones else nota
        )
    periodo_locked.save(
        update_fields=[
            "asiento_cierre",
            "estado",
            "fecha_cierre",
            "cerrado_por",
            "observaciones",
            "fecha_actualizacion",
        ]
    )
    return periodo_locked


@transaction.atomic
def cerrar_ejercicio_contable(
    empresa: Empresa,
    anio: int,
    cuenta_resultado_acumulado: PlanCuentas,
    *,
    usuario: Usuarios | None = None,
    fecha_cierre: date | None = None,
) -> dict[str, Any]:
    """Salda cuentas de resultado (INGRESO/COSTO/GASTO) a PATRIMONIO y cierra los 12 períodos."""
    _validar_anio_mes(anio)

    if cuenta_resultado_acumulado.id_empresa_id != empresa.pk:
        raise AsientoError("La cuenta de resultado acumulado no pertenece a la empresa.")
    if not cuenta_resultado_acumulado.activo:
        raise AsientoError("La cuenta de resultado acumulado está inactiva.")
    if cuenta_resultado_acumulado.tipo_cuenta != "PATRIMONIO":
        raise AsientoError("La cuenta de resultado acumulado debe ser de tipo PATRIMONIO.")

    fecha_asiento = fecha_cierre or date(anio, 12, 31)
    if fecha_asiento.year != anio:
        raise AsientoError(f"La fecha de cierre ({fecha_asiento}) debe pertenecer al ejercicio {anio}.")

    borradores = AsientoContable.objects.filter(
        id_empresa=empresa,
        fecha_asiento__year=anio,
        estado_asiento="BORRADOR",
    ).count()
    if borradores > 0:
        raise AsientoError(
            f"No se puede cerrar el ejercicio {anio}: existen {borradores} asiento(s) en estado BORRADOR."
        )

    ya_existe_cierre = (
        AsientoContable.objects.filter(
            id_empresa=empresa,
            fecha_asiento__year=anio,
            es_cierre=True,
        )
        .exclude(estado_asiento="ANULADO")
        .filter(contra_asiento__isnull=True)
        .exists()
    )
    if ya_existe_cierre:
        raise AsientoError(f"El ejercicio {anio} ya posee un asiento de cierre activo.")

    periodos_con_cierre = (
        PeriodoContable.objects.filter(
            id_empresa=empresa,
            anio=anio,
            activo=True,
            asiento_cierre__isnull=False,
            asiento_cierre__estado_asiento="APROBADO",
        )
        .filter(asiento_cierre__contra_asiento__isnull=True)
        .exists()
    )
    if periodos_con_cierre:
        raise AsientoError(f"El ejercicio {anio} ya tiene períodos cerrados vinculados a un asiento de cierre.")

    filas = list(
        DetalleAsiento.objects.filter(
            id_asiento__id_empresa=empresa,
            id_asiento__estado_asiento="APROBADO",
            id_asiento__fecha_asiento__year=anio,
            id_cuenta_contable__tipo_cuenta__in=["INGRESO", "COSTO", "GASTO"],
        )
        .values("id_cuenta_contable")
        .annotate(
            sum_debe=Coalesce(Sum("debe"), Decimal("0.00")),
            sum_haber=Coalesce(Sum("haber"), Decimal("0.00")),
        )
        .order_by("id_cuenta_contable")
    )

    lineas_cuentas: list[tuple[uuid.UUID, Decimal, Decimal]] = []
    total_debe = Decimal("0.00")
    total_haber = Decimal("0.00")

    for fila in filas:
        sum_debe = Decimal(str(fila["sum_debe"]))
        sum_haber = Decimal(str(fila["sum_haber"]))
        neto = (sum_debe - sum_haber).quantize(Decimal("0.01"))
        if neto == Decimal("0.00"):
            continue
        if neto > Decimal("0.00"):
            # Saldo neto deudor → acreditar para saldar a 0
            linea_debe = Decimal("0.00")
            linea_haber = neto
        else:
            # Saldo neto acreedor → debitar para saldar a 0
            linea_debe = abs(neto)
            linea_haber = Decimal("0.00")
        lineas_cuentas.append((fila["id_cuenta_contable"], linea_debe, linea_haber))
        total_debe += linea_debe
        total_haber += linea_haber

    resultado_ejercicio = (total_debe - total_haber).quantize(Decimal("0.01"))
    asiento_cierre: AsientoContable | None = None

    if lineas_cuentas:
        diario = (
            DiarioContable.objects.filter(id_empresa=empresa, tipo="VARIOS", activo=True).order_by("codigo").first()
        )
        if diario is not None and (diario.prefijo_secuencia or "").strip():
            numero_cierre = _siguiente_numero_asiento("CIER", diario)
        else:
            numero_cierre = f"CIER-{anio}-{uuid.uuid4().hex[:8].upper()}"

        asiento_cierre = AsientoContable.objects.create(
            id_empresa=empresa,
            id_diario=diario,
            es_cierre=True,
            fecha_asiento=fecha_asiento,
            numero_asiento=numero_cierre,
            descripcion=f"Cierre del ejercicio contable {anio}",
            nombre_modelo_origen="PeriodoContable",
            estado_asiento="APROBADO",
            id_usuario_registro=usuario,
        )

        cuentas_map = PlanCuentas.objects.in_bulk([cid for cid, _, _ in lineas_cuentas])
        for cid, l_debe, l_haber in lineas_cuentas:
            DetalleAsiento.objects.create(
                id_asiento=asiento_cierre,
                id_cuenta_contable=cuentas_map[cid],
                debe=l_debe,
                haber=l_haber,
                descripcion_detalle=f"Cierre ejercicio {anio}",
            )

        if resultado_ejercicio > Decimal("0.00"):
            # Ganancia neta → Haber en Patrimonio
            DetalleAsiento.objects.create(
                id_asiento=asiento_cierre,
                id_cuenta_contable=cuenta_resultado_acumulado,
                debe=Decimal("0.00"),
                haber=resultado_ejercicio,
                descripcion_detalle=f"Resultado neto del ejercicio {anio} (Ganancia)",
            )
            total_haber += resultado_ejercicio
        elif resultado_ejercicio < Decimal("0.00"):
            # Pérdida neta → Debe en Patrimonio
            perdida = abs(resultado_ejercicio)
            DetalleAsiento.objects.create(
                id_asiento=asiento_cierre,
                id_cuenta_contable=cuenta_resultado_acumulado,
                debe=perdida,
                haber=Decimal("0.00"),
                descripcion_detalle=f"Resultado neto del ejercicio {anio} (Pérdida)",
            )
            total_debe += perdida

        if total_debe != total_haber:
            raise AsientoError(f"El asiento de cierre del ejercicio {anio} quedó descuadrado.")

    ahora = timezone.now()
    periodos_cerrados: list[PeriodoContable] = []
    for mes in range(1, 13):
        periodo, _ = PeriodoContable.objects.get_or_create(
            id_empresa=empresa,
            anio=anio,
            mes=mes,
        )
        p_locked = PeriodoContable.objects.select_for_update().get(pk=periodo.pk)
        p_locked.activo = True
        p_locked.estado = "CERRADO"
        if p_locked.fecha_cierre is None:
            p_locked.fecha_cierre = ahora
        if p_locked.cerrado_por_id is None and usuario is not None:
            p_locked.cerrado_por = usuario
        p_locked.asiento_cierre = asiento_cierre
        p_locked.save(
            update_fields=[
                "activo",
                "estado",
                "fecha_cierre",
                "cerrado_por",
                "asiento_cierre",
                "fecha_actualizacion",
            ]
        )
        periodos_cerrados.append(p_locked)

    return {
        "anio": anio,
        "asiento_cierre": asiento_cierre,
        "resultado_ejercicio": resultado_ejercicio,
        "periodos_cerrados": periodos_cerrados,
        "cantidad_cuentas_saldadas": len(lineas_cuentas),
    }
