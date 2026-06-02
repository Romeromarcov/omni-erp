"""
Servicio central de asientos contables automáticos (R-CODE-11).

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

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import AsientoContable, DetalleAsiento, MapeoContable

# ── Tipos soportados ──────────────────────────────────────────────────────────

TIPOS_ASIENTO = frozenset(
    {
        "FACTURA_VENTA",
        "FACTURA_VENTA_IVA",   # CTF-001: asiento separado para el IVA
        "NOTA_VENTA",          # CTF-001: asiento al confirmar nota de venta
        "FACTURA_COMPRA",
        "RECEPCION_MERCANCIA",
        "AJUSTE_INVENTARIO",
        "SALIDA_INTERNA",
        "PAGO_CXC",
        "PAGO_CXP",
    }
)


# ── Excepciones ───────────────────────────────────────────────────────────────


class AsientoError(Exception):
    pass


class MapeoContableNoEncontrado(AsientoError):
    pass


# ── Helpers internos ──────────────────────────────────────────────────────────


def _extraer_empresa(documento):
    for attr in ("id_empresa", "empresa"):
        val = getattr(documento, attr, None)
        if val is not None:
            return val
    raise AsientoError(f"No se pudo extraer empresa de {documento.__class__.__name__}")


def _extraer_monto(documento) -> Decimal:
    for attr in ("monto_total", "total", "monto", "subtotal", "base_imponible"):
        val = getattr(documento, attr, None)
        if val is not None:
            return Decimal(str(val))
    raise AsientoError(f"No se pudo extraer monto de {documento.__class__.__name__}")


def _numero_asiento(tipo: str) -> str:
    fecha = timezone.now().date().strftime("%Y%m%d")  # M-BUG-12: TZ-aware
    sufijo = uuid.uuid4().hex[:8].upper()
    return f"AST-{tipo[:4]}-{fecha}-{sufijo}"


def _descripcion(plantilla: str, tipo: str, documento) -> str:
    desc = plantilla.replace("{tipo}", tipo)
    for attr in ("numero_factura", "numero_orden", "numero_nota", "numero_recepcion", "numero_pedido"):
        val = getattr(documento, attr, None)
        if val:
            return desc.replace("{numero}", str(val))
    return desc.replace("{numero}", str(documento.pk)[:8])


# ── Función pública ───────────────────────────────────────────────────────────


@transaction.atomic
def generar_asiento(tipo: str, documento, empresa=None, monto: Decimal = None) -> AsientoContable:
    """
    Crea un AsientoContable con dos líneas (debe/haber) para el documento dado.

    Args:
        tipo:      Uno de TIPOS_ASIENTO.
        documento: Instancia del modelo origen (FacturaFiscal, RecepcionMercancia, etc.).
        empresa:   Instancia de Empresa. Si None, se infiere del documento.
        monto:     Monto explícito. Si None, se infiere del documento (útil para IVA, etc.).

    Returns:
        AsientoContable creado (estado BORRADOR o APROBADO según empresa.contabilidad_auto_aprobar).

    Raises:
        AsientoError: Si falta mapeo, empresa o monto.
        MapeoContableNoEncontrado: Si no hay MapeoContable configurado para este tipo.
    """
    if tipo not in TIPOS_ASIENTO:
        raise AsientoError(f"Tipo desconocido: {tipo!r}. Válidos: {sorted(TIPOS_ASIENTO)}")

    if empresa is None:
        empresa = _extraer_empresa(documento)

    if monto is None:
        monto = _extraer_monto(documento)
    else:
        monto = Decimal(str(monto))
    if monto <= Decimal("0"):
        raise AsientoError(f"El monto del asiento debe ser mayor a cero. Obtenido: {monto}")

    try:
        mapeo = MapeoContable.objects.select_related("cuenta_debe", "cuenta_haber").get(
            id_empresa=empresa, tipo_asiento=tipo, activo=True
        )
    except MapeoContable.DoesNotExist:
        raise MapeoContableNoEncontrado(
            f"No hay MapeoContable activo para empresa={empresa.pk!s:.8}, tipo={tipo!r}. "
            "Configure el mapeo en Contabilidad → Configuración de Mapeos."
        )

    descripcion = _descripcion(mapeo.descripcion_plantilla, tipo, documento)
    numero = _numero_asiento(tipo)

    asiento = AsientoContable.objects.create(
        id_empresa=empresa,
        fecha_asiento=timezone.now().date(),  # M-BUG-12: TZ-aware
        numero_asiento=numero,
        descripcion=descripcion,
        id_documento_origen=documento.pk,
        nombre_modelo_origen=documento.__class__.__name__,
        estado_asiento="BORRADOR",
    )

    DetalleAsiento.objects.create(
        id_asiento=asiento,
        id_cuenta_contable=mapeo.cuenta_debe,
        debe=monto,
        haber=Decimal("0"),
        descripcion_detalle=descripcion,
    )
    DetalleAsiento.objects.create(
        id_asiento=asiento,
        id_cuenta_contable=mapeo.cuenta_haber,
        debe=Decimal("0"),
        haber=monto,
        descripcion_detalle=descripcion,
    )

    if getattr(empresa, "contabilidad_auto_aprobar", False):
        asiento.estado_asiento = "APROBADO"
        asiento.save(update_fields=["estado_asiento"])

    return asiento
