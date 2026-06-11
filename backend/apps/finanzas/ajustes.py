from decimal import Decimal

from django.utils import timezone

from apps.finanzas.models import Caja, CajaFisica, CuentaBancariaEmpresa, Moneda, MovimientoCajaBanco


def crear_ajuste_caja_banco(
    empresa,
    monto,
    moneda,
    caja=None,
    caja_fisica=None,
    cuenta_bancaria=None,
    usuario=None,
    motivo="",
    tipo_ajuste="POSITIVO",
    referencia=None,
    fecha_movimiento=None,
    hora_movimiento=None,
):
    """
    Crea un ajuste positivo o negativo en una caja (virtual o física) o banco.
    tipo_ajuste: 'POSITIVO' o 'NEGATIVO'

    fecha_movimiento/hora_movimiento permiten fechar el ajuste explícitamente
    (p. ej. en el límite de un cierre de caja para que pertenezca a la ventana
    recién cerrada); por defecto se usa el momento actual.
    """
    tipo_movimiento = "AJUSTE_POSITIVO" if tipo_ajuste == "POSITIVO" else "AJUSTE_NEGATIVO"
    now = timezone.now()
    movimiento = MovimientoCajaBanco.objects.create(
        id_empresa=empresa,
        fecha_movimiento=fecha_movimiento or now.date(),
        hora_movimiento=hora_movimiento or now.time(),
        tipo_movimiento=tipo_movimiento,
        monto=Decimal(monto),
        id_moneda=moneda,
        concepto=motivo or f"Ajuste {'positivo' if tipo_ajuste == 'POSITIVO' else 'negativo'} de saldo",
        referencia=referencia,
        id_caja=caja,
        id_caja_fisica=caja_fisica,
        id_cuenta_bancaria=cuenta_bancaria,
        id_transaccion_financiera=None,
        saldo_anterior=0,
        saldo_nuevo=0,
        id_usuario_registro=usuario,
    )
    return movimiento
