"""
Servicios de negocio para Finanzas.

obtener_tasa_cambio()      — busca la mejor tasa disponible entre dos monedas.
convertir_monto()          — convierte un monto usando la tasa vigente.
registrar_efectos_pago()   — side-effects financieros de un Pago (transacción,
                             movimiento de caja/banco y saldos) con atomic + lock.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone


class TasaCambioError(Exception):
    pass


# Priority order for rate lookup (lowest index = highest priority)
_TIPO_TASA_PRIORIDAD = ["ESPECIAL_USUARIO", "FIJA", "PROMEDIO_MERCADO", "OFICIAL_BCV"]


def obtener_tasa_cambio(moneda_origen, moneda_destino, empresa=None, fecha=None):
    """
    Busca la tasa de cambio más adecuada entre dos monedas para una fecha.

    Prioridad de búsqueda:
    1. Tasa específica de la empresa (ESPECIAL_USUARIO > FIJA > PROMEDIO_MERCADO) para la fecha exacta.
    2. Tasa global OFICIAL_BCV (id_empresa=None) para la fecha exacta.
    3. Tasa más reciente disponible (empresa-específica o global) dentro de los últimos 30 días.

    Si moneda_origen == moneda_destino devuelve tasa 1.0.

    Args:
        moneda_origen:  Instancia Moneda o código ISO (str).
        moneda_destino: Instancia Moneda o código ISO (str).
        empresa:        Instancia Empresa o UUID; puede ser None para buscar solo tasas globales.
        fecha:          date — fecha de referencia; default hoy (timezone.now().date()).

    Returns:
        TasaCambio — instancia con la mejor tasa disponible.

    Raises:
        TasaCambioError si no se encuentra ninguna tasa.
    """
    from .models import Moneda, TasaCambio

    # Resolver monedas por ISO si se pasan como strings
    if isinstance(moneda_origen, str):
        try:
            moneda_origen = Moneda.objects.get(codigo_iso=moneda_origen)
        except Moneda.DoesNotExist:
            raise TasaCambioError(f"Moneda '{moneda_origen}' no encontrada.")
    if isinstance(moneda_destino, str):
        try:
            moneda_destino = Moneda.objects.get(codigo_iso=moneda_destino)
        except Moneda.DoesNotExist:
            raise TasaCambioError(f"Moneda '{moneda_destino}' no encontrada.")

    # Misma moneda — tasa identidad (usamos un stub no persistente)
    if moneda_origen.pk == moneda_destino.pk:
        tasa = TasaCambio(
            id_moneda_origen=moneda_origen,
            id_moneda_destino=moneda_destino,
            valor_tasa=Decimal("1.00000000"),
            fecha_tasa=timezone.now().date(),
            tipo_tasa="FIJA",
        )
        return tasa

    if fecha is None:
        fecha = timezone.now().date()

    base_qs = TasaCambio.objects.filter(
        id_moneda_origen=moneda_origen,
        id_moneda_destino=moneda_destino,
        fecha_tasa=fecha,
    )

    # 1. Tasa empresa-específica (fecha exacta)
    if empresa is not None:
        empresa_qs = base_qs.filter(id_empresa=empresa)
        for tipo in _TIPO_TASA_PRIORIDAD:
            tasa = empresa_qs.filter(tipo_tasa=tipo).order_by("-fecha_creacion").first()
            if tasa:
                return tasa

    # 2. Tasa global OFICIAL_BCV (fecha exacta)
    tasa = base_qs.filter(id_empresa=None, tipo_tasa="OFICIAL_BCV").order_by("-fecha_creacion").first()
    if tasa:
        return tasa

    # 3. Tasa más reciente disponible (últimos 30 días)
    from datetime import timedelta

    fecha_limite = fecha - timedelta(days=30)
    recientes_qs = TasaCambio.objects.filter(
        id_moneda_origen=moneda_origen,
        id_moneda_destino=moneda_destino,
        fecha_tasa__gte=fecha_limite,
        fecha_tasa__lte=fecha,
    ).order_by("-fecha_tasa", "-fecha_creacion")

    if empresa is not None:
        tasa = recientes_qs.filter(id_empresa=empresa).first()
        if tasa:
            return tasa

    tasa = recientes_qs.filter(id_empresa=None).first()
    if tasa:
        return tasa

    raise TasaCambioError(
        f"No hay tasa de cambio disponible entre {moneda_origen.codigo_iso} "
        f"y {moneda_destino.codigo_iso} para {fecha} (últimos 30 días)."
    )


def convertir_monto(monto: Decimal, moneda_origen, moneda_destino, empresa=None, fecha=None) -> Decimal:
    """
    Convierte un monto de moneda_origen a moneda_destino.

    Args:
        monto:          Monto a convertir (Decimal o numérico).
        moneda_origen:  Instancia Moneda o código ISO.
        moneda_destino: Instancia Moneda o código ISO.
        empresa:        Instancia Empresa o UUID; None para tasas globales.
        fecha:          date; default hoy.

    Returns:
        Decimal — monto convertido, redondeado a 4 decimales.

    Raises:
        TasaCambioError si no hay tasa disponible.
        ValueError si el monto es negativo.
    """
    monto = Decimal(str(monto))
    if monto < 0:
        raise ValueError("El monto a convertir no puede ser negativo.")

    tasa = obtener_tasa_cambio(moneda_origen, moneda_destino, empresa=empresa, fecha=fecha)
    resultado = monto * tasa.valor_tasa
    return resultado.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


@transaction.atomic
def registrar_efectos_pago(pago):
    """
    Genera los side-effects financieros de un ``Pago`` recién creado (BUG-C2).

    En la MISMA transacción (R-CODE-11):
    1. Crea la ``TransaccionFinanciera`` y la asocia al pago.
    2. Si el pago usó datafono, crea la ``TransaccionDatafono``.
    3. Si el pago afecta caja virtual o cuenta bancaria, bloquea el registro
       (``select_for_update``), crea el ``MovimientoCajaBanco`` con los saldos
       correctos y actualiza ``saldo_actual``.

    Args:
        pago: Instancia ``Pago`` ya persistida (con empresa, moneda y método).

    Returns:
        tuple (TransaccionFinanciera, MovimientoCajaBanco | None)
    """
    from .models import (
        Caja,
        CuentaBancariaEmpresa,
        MovimientoCajaBanco,
        TransaccionDatafono,
        TransaccionFinanciera,
    )

    transaccion = TransaccionFinanciera.objects.create(
        id_empresa=pago.id_empresa,
        fecha_hora_transaccion=pago.fecha_pago,
        tipo_transaccion=pago.tipo_operacion,
        monto_transaccion=pago.monto,
        id_moneda_transaccion=pago.id_moneda,
        id_moneda_base=pago.id_moneda,  # Simplificación: misma moneda del pago
        monto_base_empresa=pago.monto,
        id_metodo_pago=pago.id_metodo_pago,
        referencia_pago=pago.referencia,
        descripcion=f"Pago {pago.tipo_operacion.lower()} - {pago.get_tipo_documento_display()}",
        tipo_documento_asociado=pago.tipo_documento,
        nro_documento_asociado=str(pago.id_documento),
        id_caja=pago.id_caja_virtual,
        id_cuenta_bancaria=pago.id_cuenta_bancaria,
        id_usuario_registro=pago.id_usuario_registro,
    )

    pago.id_transaccion_financiera = transaccion
    pago.save(update_fields=["id_transaccion_financiera"])

    if pago.id_datafono_id:
        TransaccionDatafono.objects.create(
            id_datafono=pago.id_datafono,
            monto=pago.monto,
            referencia_bancaria=pago.referencia,
            id_transaccion_financiera_origen=transaccion,
            id_usuario_registro=pago.id_usuario_registro,
        )

    movimiento = None
    if pago.id_caja_virtual_id or pago.id_cuenta_bancaria_id:
        # Lock pesimista sobre el contenedor de saldo para evitar carreras.
        if pago.id_caja_virtual_id:
            contenedor = Caja.objects.select_for_update().get(pk=pago.id_caja_virtual_id)
        else:
            contenedor = CuentaBancariaEmpresa.objects.select_for_update().get(
                pk=pago.id_cuenta_bancaria_id
            )

        tipo_movimiento = "INGRESO" if pago.tipo_operacion == "INGRESO" else "EGRESO"
        saldo_anterior = contenedor.saldo_actual
        delta = pago.monto if tipo_movimiento == "INGRESO" else -pago.monto
        saldo_nuevo = saldo_anterior + delta

        movimiento = MovimientoCajaBanco.objects.create(
            id_empresa=pago.id_empresa,
            fecha_movimiento=pago.fecha_pago.date(),
            hora_movimiento=pago.fecha_pago.time(),
            tipo_movimiento=tipo_movimiento,
            monto=pago.monto,
            id_moneda=pago.id_moneda,
            concepto=f"{pago.tipo_operacion} - {pago.get_tipo_documento_display()}",
            referencia=pago.referencia or f"Pago {pago.id_pago}",
            id_caja=pago.id_caja_virtual,
            id_cuenta_bancaria=pago.id_cuenta_bancaria,
            id_transaccion_financiera=transaccion,
            saldo_anterior=saldo_anterior,
            saldo_nuevo=saldo_nuevo,
            id_usuario_registro=pago.id_usuario_registro,
        )

        contenedor.saldo_actual = saldo_nuevo
        contenedor.save(update_fields=["saldo_actual"])

    return transaccion, movimiento
