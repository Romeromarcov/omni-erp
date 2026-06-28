"""Captura de vinculaciones pago↔pedido (Fase 3).

Registra la vinculación humana entre un ``PagoLubrikca`` y un ``PedidoLubrikca``,
estampa las tasas (BCV / Binance) del momento del pago, congela los cuatro
equivalentes (sección 3.9b — inmutables) y dispara el recálculo de la bandeja.

El sync de Odoo NUNCA toca estas filas (es trabajo humano).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.cxc_lubrikca.models import MetodoPago, Vinculacion
from apps.cxc_lubrikca.services.bridge import recalcular_bandeja
from apps.cxc_lubrikca.services.motor.equivalents import calcular_equivalentes
from apps.cxc_lubrikca.services.motor.models import Moneda as MonedaDC
from apps.cxc_lubrikca.services.motor.models import TipoTasa as TipoTasaDC

# Tipos de tasa en TasaCambio del núcleo finanzas.
_TIPO_BCV = "OFICIAL_BCV"
_TIPO_BINANCE = "PROMEDIO_MERCADO"


class VinculacionError(Exception):
    """Error de negocio al registrar una vinculación (datos inválidos)."""


def _buscar_tasa(empresa, tipo_tasa: str, fecha) -> Decimal | None:
    """Tasa VES-por-USD (origen USD, destino VES) del tipo y fecha indicados.

    Busca primero específica de la empresa, luego global (id_empresa=None).
    Devuelve None si no hay tasa cargada para esa fecha.
    """
    from apps.finanzas.models import Moneda, TasaCambio

    try:
        usd = Moneda.objects.get(codigo_iso="USD")
        ves = Moneda.objects.get(codigo_iso="VES")
    except Moneda.DoesNotExist:
        return None

    qs = TasaCambio.objects.filter(
        id_moneda_origen=usd,
        id_moneda_destino=ves,
        tipo_tasa=tipo_tasa,
        fecha_tasa=fecha,
    )
    tasa = (
        qs.filter(id_empresa=empresa).order_by("-fecha_creacion").first()
        or qs.filter(id_empresa__isnull=True).order_by("-fecha_creacion").first()
    )
    return tasa.valor_tasa if tasa is not None else None


def _monto_ya_vinculado(pago) -> Decimal:
    total = pago.vinculaciones.filter(deleted_at__isnull=True).aggregate(
        s=Sum("monto_aplicado")
    )["s"]
    return total or Decimal("0")


@transaction.atomic
def registrar_vinculacion(
    *,
    pedido,
    pago,
    monto_aplicado: Decimal,
    hora_pago_confirmada,
    usuario,
    es_tasa_heredada: bool = False,
) -> Vinculacion:
    """Crea una ``Vinculacion`` con tasas estampadas y equivalentes congelados.

    Valida: monto > 0, mismo cliente, sin sobre-vinculación, misma empresa, y
    tasas disponibles. Recalcula la bandeja al final.
    """
    monto_aplicado = Decimal(str(monto_aplicado))

    # Bloqueo del pago para evitar sobre-vinculación concurrente.
    pago = type(pago).objects.select_for_update().get(pk=pago.pk)

    if monto_aplicado <= 0:
        raise VinculacionError("El monto aplicado debe ser mayor a cero.")

    if pedido.empresa_id != pago.empresa_id:
        raise VinculacionError("El pago y el pedido deben ser de la misma empresa.")

    if pago.cliente_externo_id != pedido.cliente_externo_id:
        raise VinculacionError(
            "El pago y el pedido deben pertenecer al mismo cliente."
        )

    ya_vinculado = _monto_ya_vinculado(pago)
    disponible = pago.monto - ya_vinculado
    if monto_aplicado > disponible:
        raise VinculacionError(
            f"Sobre-vinculación: monto disponible del pago = {disponible}, "
            f"se intentó aplicar {monto_aplicado}."
        )

    # La tasa se indexa por fecha local de Caracas (igual que el resto de finanzas,
    # ver finanzas.services.obtener_tasa_cambio): un pago confirmado de noche en hora
    # local no debe estampar la tasa del día siguiente (UTC).
    momento = hora_pago_confirmada
    if timezone.is_aware(momento):
        momento = timezone.localtime(momento)
    fecha = momento.date()
    tasa_bcv = _buscar_tasa(pedido.empresa, _TIPO_BCV, fecha)
    tasa_binance = _buscar_tasa(pedido.empresa, _TIPO_BINANCE, fecha)
    if tasa_bcv is None or tasa_binance is None:
        faltan = []
        if tasa_bcv is None:
            faltan.append("BCV (OFICIAL_BCV)")
        if tasa_binance is None:
            faltan.append("Binance (PROMEDIO_MERCADO)")
        raise VinculacionError(
            f"No hay tasa(s) cargada(s) para {fecha}: {', '.join(faltan)}. "
            "Cargue la tasa USD→VES antes de vincular."
        )

    # tipo_tasa del abono según el método de pago configurado del tenant.
    metodo = MetodoPago.objects.filter(
        empresa=pedido.empresa, codigo=pago.metodo_pago, deleted_at__isnull=True
    ).first()
    tipo_tasa_abono = metodo.tipo_tasa if metodo is not None else TipoTasaDC.N_A.value

    # Equivalentes congelados (UNA vez, inmutables).
    eq = calcular_equivalentes(
        monto_aplicado,
        MonedaDC(pago.moneda),
        tasa_bcv,
        tasa_binance,
    )

    vinc = Vinculacion.objects.create(
        empresa=pedido.empresa,
        pedido=pedido,
        pago=pago,
        monto_aplicado=monto_aplicado,
        hora_pago_confirmada=hora_pago_confirmada,
        tasa_bcv_aplicada=tasa_bcv,
        tasa_binance_aplicada=tasa_binance,
        es_tasa_heredada=es_tasa_heredada,
        moneda_abono=pago.moneda,
        tipo_tasa_abono=tipo_tasa_abono,
        equiv_usd_bcv=eq.equiv_usd_bcv,
        equiv_usd_binance=eq.equiv_usd_binance,
        equiv_ves_bcv=eq.equiv_ves_bcv,
        equiv_ves_binance=eq.equiv_ves_binance,
        confirmado_por=usuario,
    )

    # Marcar el pago como vinculado si quedó totalmente aplicado.
    if ya_vinculado + monto_aplicado >= pago.monto:
        pago.vinculado = True
        pago.save(update_fields=["vinculado"])

    recalcular_bandeja(pedido)
    return vinc
