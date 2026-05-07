from apps.finanzas.models import MovimientoCajaBanco, Caja, CajaFisica, CuentaBancariaEmpresa, Moneda
from django.utils import timezone
from decimal import Decimal

def crear_ajuste_caja_banco(
    empresa,
    monto,
    moneda,
    caja=None,
    caja_fisica=None,
    cuenta_bancaria=None,
    usuario=None,
    motivo='',
    tipo_ajuste='POSITIVO',
    referencia=None
):
    """
    Crea un ajuste positivo o negativo en una caja (virtual o física) o banco.
    tipo_ajuste: 'POSITIVO' o 'NEGATIVO'
    """
    tipo_movimiento = 'AJUSTE_POSITIVO' if tipo_ajuste == 'POSITIVO' else 'AJUSTE_NEGATIVO'
    now = timezone.now()
    movimiento = MovimientoCajaBanco.objects.create(
        id_empresa=empresa,
        fecha_movimiento=now.date(),
        hora_movimiento=now.time(),
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
