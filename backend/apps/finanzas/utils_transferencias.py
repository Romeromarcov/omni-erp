from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.finanzas.models import Caja, MovimientoCajaBanco


def transferencia_entre_cajas(origen: Caja, destino: Caja, monto, usuario=None, referencia=None):
    """
    Realiza una transferencia interna entre dos cajas (registradora a gerente, etc).
    Crea dos movimientos: salida en origen y entrada en destino.

    BUG-A1: la operación es atómica, bloquea ambas cajas (``select_for_update``)
    y valida monto > 0, saldo suficiente y misma moneda antes de mover saldos.

    Raises:
        ValueError con mensaje de negocio si alguna validación falla.
    """
    try:
        monto = Decimal(str(monto))
    except (ArithmeticError, TypeError):
        raise ValueError("El monto de la transferencia no es un número válido.")
    if not monto.is_finite():
        raise ValueError("El monto de la transferencia no es un número válido.")
    if monto <= 0:
        raise ValueError("El monto de la transferencia debe ser mayor a cero.")
    if origen.empresa_id is None or destino.empresa_id is None:
        raise ValueError("Las cajas de la transferencia deben tener empresa asignada.")
    if origen.pk == destino.pk:
        raise ValueError("La caja origen y la caja destino deben ser distintas.")

    with transaction.atomic():
        # Lock de ambas cajas en orden determinístico (por pk) para evitar
        # deadlocks entre transferencias cruzadas concurrentes.
        cajas = {
            caja.pk: caja
            for caja in Caja.objects.select_for_update()
            .filter(pk__in=[origen.pk, destino.pk])
            .order_by("pk")
        }
        origen_lock = cajas[origen.pk]
        destino_lock = cajas[destino.pk]

        # Re-validación sobre los objetos lockeados (y narrowing para mypy:
        # `empresa` es Optional en el modelo).
        empresa_origen = origen_lock.empresa
        empresa_destino = destino_lock.empresa
        if empresa_origen is None or empresa_destino is None:
            raise ValueError("Las cajas de la transferencia deben tener empresa asignada.")
        if origen_lock.moneda_id != destino_lock.moneda_id:
            raise ValueError("Las cajas origen y destino deben tener la misma moneda.")
        if origen_lock.saldo_actual < monto:
            raise ValueError("Saldo insuficiente en la caja origen para la transferencia.")

        ahora = timezone.now()
        mov_salida = MovimientoCajaBanco.objects.create(
            id_empresa=empresa_origen,
            fecha_movimiento=ahora.date(),
            hora_movimiento=ahora.time(),
            tipo_movimiento="TRANSFERENCIA_SALIDA",
            monto=monto,
            id_moneda=origen_lock.moneda,
            concepto=f"Transferencia interna a caja {destino_lock.nombre}",
            referencia=referencia,
            id_caja=origen_lock,
            saldo_anterior=origen_lock.saldo_actual,
            saldo_nuevo=origen_lock.saldo_actual - monto,
            id_usuario_registro=usuario,
        )
        origen_lock.saldo_actual -= monto
        origen_lock.save(update_fields=["saldo_actual"])

        mov_entrada = MovimientoCajaBanco.objects.create(
            id_empresa=empresa_destino,
            fecha_movimiento=ahora.date(),
            hora_movimiento=ahora.time(),
            tipo_movimiento="TRANSFERENCIA_ENTRADA",
            monto=monto,
            id_moneda=destino_lock.moneda,
            concepto=f"Transferencia interna desde caja {origen_lock.nombre}",
            referencia=referencia,
            id_caja=destino_lock,
            saldo_anterior=destino_lock.saldo_actual,
            saldo_nuevo=destino_lock.saldo_actual + monto,
            id_usuario_registro=usuario,
        )
        destino_lock.saldo_actual += monto
        destino_lock.save(update_fields=["saldo_actual"])

    return mov_salida, mov_entrada
