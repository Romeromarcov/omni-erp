from decimal import Decimal

from django.utils import timezone

from apps.finanzas.models import Caja, MovimientoCajaBanco


def transferencia_entre_cajas(origen: Caja, destino: Caja, monto, usuario=None, referencia=None):
    """
    Realiza una transferencia interna entre dos cajas (registradora a gerente, etc).
    Crea dos movimientos: salida en origen y entrada en destino.
    """
    monto = Decimal(monto)
    if origen.empresa is None or destino.empresa is None:
        raise ValueError("Las cajas de la transferencia deben tener empresa asignada.")
    ahora = timezone.now()
    mov_salida = MovimientoCajaBanco.objects.create(
        id_empresa=origen.empresa,
        fecha_movimiento=ahora.date(),
        hora_movimiento=ahora.time(),
        tipo_movimiento="TRANSFERENCIA_SALIDA",
        monto=monto,
        id_moneda=origen.moneda,
        concepto=f"Transferencia interna a caja {destino.nombre}",
        referencia=referencia,
        id_caja=origen,
        saldo_anterior=origen.saldo_actual,
        saldo_nuevo=origen.saldo_actual - monto,
        id_usuario_registro=usuario,
    )
    origen.saldo_actual -= monto
    origen.save()
    mov_entrada = MovimientoCajaBanco.objects.create(
        id_empresa=destino.empresa,
        fecha_movimiento=ahora.date(),
        hora_movimiento=ahora.time(),
        tipo_movimiento="TRANSFERENCIA_ENTRADA",
        monto=monto,
        id_moneda=destino.moneda,
        concepto=f"Transferencia interna desde caja {origen.nombre}",
        referencia=referencia,
        id_caja=destino,
        saldo_anterior=destino.saldo_actual,
        saldo_nuevo=destino.saldo_actual + monto,
        id_usuario_registro=usuario,
    )
    destino.saldo_actual += monto
    destino.save()
    return mov_salida, mov_entrada
