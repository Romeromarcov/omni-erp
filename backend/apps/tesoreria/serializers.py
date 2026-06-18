import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from rest_framework import serializers

logger = logging.getLogger(__name__)

from .models import Caja, ConciliacionBancaria, MovimientoBancario, MovimientoInternoFondo, OperacionCambioDivisa


class CajaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Caja
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_caja",
            "nombre",
            "tipo_caja",
            "descripcion",
            "activa",
            "referencia_externa",
            "documento_json",
            "fecha_creacion",
            "saldo_actual",
            "empresa",
            "sucursal",
            "moneda",
            "caja_fisica",
            "plantilla_maestro",
            "metodos_pago",
        ]
        ref_name = "CajaTesoreria"  # evita colisión OpenAPI con finanzas.CajaSerializer


class MovimientoInternoFondoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimientoInternoFondo
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "referencia_externa",
            "documento_json",
            "monto",
            "fecha",
            "descripcion",
            "caja_origen",
            "caja_destino",
            "id_moneda",
            "id_banco_origen",
            "id_banco_destino",
            "usuario",
        ]

    def create(self, validated_data):
        from apps.finanzas.models import MovimientoCajaBanco

        # Crear el movimiento interno
        movimiento = super().create(validated_data)

        # Crear transferencia salida en caja/banco origen
        MovimientoCajaBanco.objects.create(
            id_empresa=movimiento.caja_origen.empresa,
            fecha_movimiento=movimiento.fecha.date(),
            hora_movimiento=movimiento.fecha.time(),
            tipo_movimiento="TRANSFERENCIA_SALIDA",
            monto=movimiento.monto,
            id_moneda=movimiento.id_moneda,
            concepto=movimiento.descripcion or "",
            referencia=movimiento.referencia_externa or "",
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
            tipo_movimiento="TRANSFERENCIA_ENTRADA",
            monto=movimiento.monto,
            id_moneda=movimiento.id_moneda,
            concepto=movimiento.descripcion or "",
            referencia=movimiento.referencia_externa or "",
            id_caja=movimiento.caja_destino,
            id_cuenta_bancaria=movimiento.id_banco_destino,
            id_transaccion_financiera=None,
            saldo_anterior=0,
            saldo_nuevo=0,
            id_usuario_registro=movimiento.usuario,
        )
        return movimiento


class OperacionCambioDivisaSerializer(serializers.ModelSerializer):
    """
    Registra una operación de cambio de divisa con su doble registro financiero
    (egreso en moneda origen + comisión opcional + ingreso en moneda destino),
    los MovimientoCajaBanco asociados, el Gasto por la comisión y el asiento
    contable CAMBIO_DIVISA — todo dentro de UNA transacción (R-CODE-11, CTF-013).
    """

    class Meta:
        model = OperacionCambioDivisa
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "referencia_externa",
            "documento_json",
            "numero_operacion",
            "fecha_operacion",
            "tipo_operacion",
            "monto_origen",
            "tasa_cambio",
            "monto_destino",
            "comision",
            "referencia_transaccion_origen",
            "referencia_transaccion_destino",
            "tipo_documento_gasto",
            "numero_documento_gasto",
            "observaciones",
            "activo",
            "fecha_creacion",
            "empresa",
            "moneda_origen",
            "moneda_destino",
            "caja_origen",
            "caja_destino",
            "banco_origen",
            "banco_destino",
            "metodo_pago_origen",
            "metodo_pago_destino",
            "casa_de_cambio",
        ]

    _DOS_DECIMALES = Decimal("0.01")

    def validate(self, attrs):
        # finanzas.TransaccionFinanciera exige id_metodo_pago (NOT NULL): sin
        # método de pago el doble registro es imposible — se rechaza con 400.
        if not attrs.get("metodo_pago_origen"):
            raise serializers.ValidationError(
                {"metodo_pago_origen": "Requerido: el egreso genera una TransaccionFinanciera."}
            )
        if not attrs.get("metodo_pago_destino"):
            raise serializers.ValidationError(
                {"metodo_pago_destino": "Requerido: el ingreso genera una TransaccionFinanciera."}
            )
        return attrs

    def _monto_base_empresa(self, operacion, monto, moneda):
        """Convierte `monto` (Decimal, en `moneda`) a la moneda base de la empresa."""
        from apps.finanzas.models import TasaCambio

        monto = Decimal(str(monto))
        base = operacion.empresa.id_moneda_base
        if base is None or moneda == base:
            return monto.quantize(self._DOS_DECIMALES, rounding=ROUND_HALF_UP)

        # La propia operación define la tasa origen→destino: úsala si conecta con la base.
        tasa_op = Decimal(str(operacion.tasa_cambio))
        if moneda == operacion.moneda_origen and operacion.moneda_destino == base:
            return (monto * tasa_op).quantize(self._DOS_DECIMALES, rounding=ROUND_HALF_UP)
        if moneda == operacion.moneda_destino and operacion.moneda_origen == base and tasa_op:
            return (monto / tasa_op).quantize(self._DOS_DECIMALES, rounding=ROUND_HALF_UP)

        fecha = operacion.fecha_operacion.date()
        tasa = (
            TasaCambio.objects.filter(
                id_moneda_origen=moneda, id_moneda_destino=base, fecha_tasa__lte=fecha
            )
            .order_by("-fecha_tasa", "-hora_tasa")
            .first()
        )
        if tasa:
            return (monto * Decimal(str(tasa.valor_tasa))).quantize(
                self._DOS_DECIMALES, rounding=ROUND_HALF_UP
            )
        inversa = (
            TasaCambio.objects.filter(
                id_moneda_origen=base, id_moneda_destino=moneda, fecha_tasa__lte=fecha
            )
            .order_by("-fecha_tasa", "-hora_tasa")
            .first()
        )
        if inversa and Decimal(str(inversa.valor_tasa)):
            return (monto / Decimal(str(inversa.valor_tasa))).quantize(
                self._DOS_DECIMALES, rounding=ROUND_HALF_UP
            )
        raise serializers.ValidationError(
            {
                "tasa_cambio": (
                    f"No hay TasaCambio para convertir {moneda.codigo_iso} a la moneda "
                    f"base de la empresa ({base.codigo_iso}). Registre la tasa del día."
                )
            }
        )

    def _crear_transaccion_y_movimiento(
        self, *, operacion, usuario, tipo, monto, moneda, concepto, caja, banco, referencia, metodo
    ):
        from apps.finanzas.models import MovimientoCajaBanco, TransaccionFinanciera

        empresa = operacion.empresa
        fecha = operacion.fecha_operacion
        transaccion = TransaccionFinanciera.objects.create(
            id_empresa=empresa,
            fecha_hora_transaccion=fecha,
            tipo_transaccion=tipo,
            monto_transaccion=monto,
            id_moneda_transaccion=moneda,
            id_moneda_base=empresa.id_moneda_base,
            monto_base_empresa=self._monto_base_empresa(operacion, monto, moneda),
            descripcion=concepto,
            id_caja=caja,
            id_cuenta_bancaria=banco,
            referencia_pago=referencia,
            id_metodo_pago=metodo,
            id_usuario_registro=usuario,
        )
        MovimientoCajaBanco.objects.create(
            id_empresa=empresa,
            fecha_movimiento=fecha.date(),
            hora_movimiento=fecha.time(),
            tipo_movimiento=tipo,
            monto=monto,
            id_moneda=moneda,
            concepto=concepto,
            referencia=referencia or "",
            id_caja=caja,
            id_cuenta_bancaria=banco,
            id_transaccion_financiera=transaccion,
            saldo_anterior=0,
            saldo_nuevo=0,
            id_usuario_registro=usuario,
        )
        return transaccion

    def create(self, validated_data):
        from apps.contabilidad.services import generar_asiento_o_fallar
        from apps.gastos.models import CategoriaGasto, Gasto

        # CTF-013: el usuario sale del request (OperacionCambioDivisa no tiene
        # campo `usuario`; antes se leía de validated_data y quedaba None).
        request = self.context.get("request")
        usuario = getattr(request, "user", None)
        if usuario is None or not usuario.is_authenticated:
            raise serializers.ValidationError({"usuario": "Se requiere un usuario autenticado."})

        # R-CODE-11: doble registro + gasto + asiento — todo o nada.
        with transaction.atomic():
            operacion = super().create(validated_data)
            empresa = operacion.empresa
            descripcion = operacion.observaciones or ""

            # Egreso por monto_origen
            self._crear_transaccion_y_movimiento(
                operacion=operacion,
                usuario=usuario,
                tipo="EGRESO",
                monto=operacion.monto_origen,
                moneda=operacion.moneda_origen,
                concepto=f"Cambio de divisas: {descripcion}",
                caja=operacion.caja_origen,
                banco=operacion.banco_origen,
                referencia=operacion.referencia_transaccion_origen,
                metodo=operacion.metodo_pago_origen,
            )

            # Egreso por comisión (si aplica) + Gasto asociado
            if operacion.comision and operacion.comision > 0:
                self._crear_transaccion_y_movimiento(
                    operacion=operacion,
                    usuario=usuario,
                    tipo="EGRESO",
                    monto=operacion.comision,
                    moneda=operacion.moneda_origen,
                    concepto=f"Comisión cambio divisas: {descripcion}",
                    caja=operacion.caja_origen,
                    banco=operacion.banco_origen,
                    referencia=operacion.referencia_transaccion_origen,
                    metodo=operacion.metodo_pago_origen,
                )
                # CTF-013: el código anterior importaba `apps.gastos.models.DocumentoGasto`,
                # que NO existe (ImportError seguro). El modelo real es `Gasto`.
                categoria, _ = CategoriaGasto.objects.get_or_create(
                    id_empresa=empresa,
                    nombre_categoria="Comisiones cambio de divisa",
                    defaults={"descripcion": "Comisiones de operaciones de cambio de divisa"},
                )
                Gasto.objects.create(
                    id_empresa=empresa,
                    fecha_gasto=operacion.fecha_operacion.date(),
                    descripcion=(
                        f"Comisión cambio divisas {operacion.numero_operacion}: {descripcion}"
                    ),
                    monto=Decimal(str(operacion.comision)).quantize(
                        self._DOS_DECIMALES, rounding=ROUND_HALF_UP
                    ),
                    id_moneda=operacion.moneda_origen,
                    id_categoria_gasto=categoria,
                    estado_gasto="APROBADO",
                )

            # Ingreso por monto_destino
            self._crear_transaccion_y_movimiento(
                operacion=operacion,
                usuario=usuario,
                tipo="INGRESO",
                monto=operacion.monto_destino,
                moneda=operacion.moneda_destino,
                concepto=f"Cambio de divisas: {descripcion}",
                caja=operacion.caja_destino,
                banco=operacion.banco_destino,
                referencia=operacion.referencia_transaccion_destino,
                metodo=operacion.metodo_pago_destino,
            )

            # R-CODE-11 centralizado: contabilidad activa sin mapeo → AsientoError
            # (la vista lo traduce a 422) y TODO lo anterior se revierte; empresa
            # informal → warning y la operación procede sin asiento.
            generar_asiento_o_fallar(
                "CAMBIO_DIVISA", operacion, empresa, monto=operacion.monto_origen
            )

        return operacion


class MovimientoBancarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimientoBancario
        fields = [
            "id", "id_empresa", "id_cuenta_bancaria",
            "fecha_mov", "descripcion", "tipo", "monto", "referencia",
            "estado", "id_pago_conciliado", "origen", "fecha_creacion",
        ]
        read_only_fields = ["id", "estado", "id_pago_conciliado", "fecha_creacion"]


class ConciliacionBancariaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConciliacionBancaria
        fields = [
            "id", "id_empresa", "id_cuenta_bancaria",
            "periodo_inicio", "periodo_fin",
            "saldo_banco", "saldo_libro", "diferencia",
            "estado", "movimientos_conciliados", "movimientos_pendientes",
            "realizada_por", "fecha_creacion", "fecha_cierre", "observaciones",
        ]
        read_only_fields = [
            "id", "diferencia", "estado",
            "movimientos_conciliados", "movimientos_pendientes",
            "fecha_creacion", "fecha_cierre",
        ]
