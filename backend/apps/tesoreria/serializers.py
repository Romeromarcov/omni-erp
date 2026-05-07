from rest_framework import serializers
from .models import Caja, MovimientoInternoFondo, OperacionCambioDivisa

class CajaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Caja
        fields = '__all__'

class MovimientoInternoFondoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimientoInternoFondo
        fields = '__all__'

    def create(self, validated_data):
        from apps.finanzas.models import MovimientoCajaBanco
        # Crear el movimiento interno
        movimiento = super().create(validated_data)

        # Crear transferencia salida en caja/banco origen
        MovimientoCajaBanco.objects.create(
            id_empresa=movimiento.caja_origen.empresa,
            fecha_movimiento=movimiento.fecha.date(),
            hora_movimiento=movimiento.fecha.time(),
            tipo_movimiento='TRANSFERENCIA_SALIDA',
            monto=movimiento.monto,
            id_moneda=movimiento.id_moneda,
            concepto=movimiento.descripcion or '',
            referencia=movimiento.referencia_externa or '',
            id_caja=movimiento.caja_origen,
            id_cuenta_bancaria=movimiento.id_banco_origen,
            id_transaccion_financiera=None,
            saldo_anterior=0,
            saldo_nuevo=0,
            id_usuario_registro=movimiento.usuario,
        )
        # Crear transferencia entrada en caja/banco destino
        MovimientoCajaBanco.objects.create(
            id_empresa=movimiento.caja_destino.empresa,
            fecha_movimiento=movimiento.fecha.date(),
            hora_movimiento=movimiento.fecha.time(),
            tipo_movimiento='TRANSFERENCIA_ENTRADA',
            monto=movimiento.monto,
            id_moneda=movimiento.id_moneda,
            concepto=movimiento.descripcion or '',
            referencia=movimiento.referencia_externa or '',
            id_caja=movimiento.caja_destino,
            id_cuenta_bancaria=movimiento.id_banco_destino,
            id_transaccion_financiera=None,
            saldo_anterior=0,
            saldo_nuevo=0,
            id_usuario_registro=movimiento.usuario,
        )
        return movimiento


class OperacionCambioDivisaSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperacionCambioDivisa
        fields = '__all__'

    def create(self, validated_data):
        from apps.finanzas.models import TransaccionFinanciera, MovimientoCajaBanco, MetodoPago
        from apps.gastos.models import DocumentoGasto
        # Crear la operación de cambio
        operacion = super().create(validated_data)

        usuario = validated_data.get('usuario') if 'usuario' in validated_data else None
        empresa = operacion.empresa
        fecha = operacion.fecha_operacion
        descripcion = operacion.observaciones or ''

        # Egreso por monto_origen (concepto: cambio de divisas)
        trans_egreso = TransaccionFinanciera.objects.create(
            id_empresa=empresa,
            fecha_hora_transaccion=fecha,
            tipo_transaccion='EGRESO',
            monto_transaccion=operacion.monto_origen,
            id_moneda_transaccion=operacion.moneda_origen,
            descripcion=f"Cambio de divisas: {descripcion}",
            id_caja=operacion.caja_origen,
            id_cuenta_bancaria=operacion.banco_origen,
            referencia_pago=operacion.referencia_transaccion_origen,
            id_metodo_pago=operacion.metodo_pago_origen,
            id_usuario_registro=usuario,
        )
        MovimientoCajaBanco.objects.create(
            id_empresa=empresa,
            fecha_movimiento=fecha.date(),
            hora_movimiento=fecha.time(),
            tipo_movimiento='EGRESO',
            monto=operacion.monto_origen,
            id_moneda=operacion.moneda_origen,
            concepto=f"Cambio de divisas: {descripcion}",
            referencia=operacion.referencia_transaccion_origen or '',
            id_caja=operacion.caja_origen,
            id_cuenta_bancaria=operacion.banco_origen,
            id_transaccion_financiera=trans_egreso,
            saldo_anterior=0,
            saldo_nuevo=0,
            id_usuario_registro=usuario,
        )

        # Egreso por comisión (si aplica)
        if operacion.comision and operacion.comision > 0:
            trans_comision = TransaccionFinanciera.objects.create(
                id_empresa=empresa,
                fecha_hora_transaccion=fecha,
                tipo_transaccion='EGRESO',
                monto_transaccion=operacion.comision,
                id_moneda_transaccion=operacion.moneda_origen,
                descripcion=f"Comisión cambio divisas: {descripcion}",
                id_caja=operacion.caja_origen,
                id_cuenta_bancaria=operacion.banco_origen,
                referencia_pago=operacion.referencia_transaccion_origen,
                id_metodo_pago=operacion.metodo_pago_origen,
                id_usuario_registro=usuario,
            )
            MovimientoCajaBanco.objects.create(
                id_empresa=empresa,
                fecha_movimiento=fecha.date(),
                hora_movimiento=fecha.time(),
                tipo_movimiento='EGRESO',
                monto=operacion.comision,
                id_moneda=operacion.moneda_origen,
                concepto=f"Comisión cambio divisas: {descripcion}",
                referencia=operacion.referencia_transaccion_origen or '',
                id_caja=operacion.caja_origen,
                id_cuenta_bancaria=operacion.banco_origen,
                id_transaccion_financiera=trans_comision,
                saldo_anterior=0,
                saldo_nuevo=0,
                id_usuario_registro=usuario,
            )
            # Documento de gasto por la comisión
            DocumentoGasto.objects.create(
                empresa=empresa,
                tipo_documento=operacion.tipo_documento_gasto,
                numero_documento=operacion.numero_documento_gasto,
                monto=operacion.comision,
                moneda=operacion.moneda_origen,
                descripcion=f"Comisión cambio divisas: {descripcion}",
                fecha=fecha,
                proveedor=operacion.casa_de_cambio,
            )

        # Ingreso por monto_destino (concepto: cambio de divisas)
        trans_ingreso = TransaccionFinanciera.objects.create(
            id_empresa=empresa,
            fecha_hora_transaccion=fecha,
            tipo_transaccion='INGRESO',
            monto_transaccion=operacion.monto_destino,
            id_moneda_transaccion=operacion.moneda_destino,
            descripcion=f"Cambio de divisas: {descripcion}",
            id_caja=operacion.caja_destino,
            id_cuenta_bancaria=operacion.banco_destino,
            referencia_pago=operacion.referencia_transaccion_destino,
            id_metodo_pago=operacion.metodo_pago_destino,
            id_usuario_registro=usuario,
        )
        MovimientoCajaBanco.objects.create(
            id_empresa=empresa,
            fecha_movimiento=fecha.date(),
            hora_movimiento=fecha.time(),
            tipo_movimiento='INGRESO',
            monto=operacion.monto_destino,
            id_moneda=operacion.moneda_destino,
            concepto=f"Cambio de divisas: {descripcion}",
            referencia=operacion.referencia_transaccion_destino or '',
            id_caja=operacion.caja_destino,
            id_cuenta_bancaria=operacion.banco_destino,
            id_transaccion_financiera=trans_ingreso,
            saldo_anterior=0,
            saldo_nuevo=0,
            id_usuario_registro=usuario,
        )

        return operacion
