"""Serializers OpenAPI de respuesta para reportes financieros canónicos (PR-14)."""

from __future__ import annotations

from rest_framework import serializers


class _BaseReporteMetaSerializer(serializers.Serializer):
    empresa_id = serializers.UUIDField(read_only=True)
    moneda_base = serializers.CharField(read_only=True)
    moneda_base_simbolo = serializers.CharField(read_only=True)
    incluir_equivalentes_usd = serializers.BooleanField(read_only=True)
    usd_disponible = serializers.BooleanField(read_only=True)
    tasa_usd = serializers.DecimalField(max_digits=18, decimal_places=8, allow_null=True, read_only=True)
    tasa_usd_inversa = serializers.BooleanField(read_only=True)
    usd_mensaje = serializers.CharField(read_only=True, allow_blank=True)


class BalanceComprobacionCuentaSerializer(serializers.Serializer):
    id_cuenta_contable = serializers.UUIDField(read_only=True)
    id_cuenta_padre = serializers.UUIDField(allow_null=True, read_only=True)
    codigo_cuenta = serializers.CharField(read_only=True)
    nombre_cuenta = serializers.CharField(read_only=True)
    tipo_cuenta = serializers.CharField(read_only=True)
    naturaleza = serializers.CharField(read_only=True)
    nivel = serializers.IntegerField(read_only=True)
    debe_inicial = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    haber_inicial = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    saldo_inicial = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    saldo_inicial_deudor = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    saldo_inicial_acreedor = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    debe = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    haber = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    debe_periodo = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    haber_periodo = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    debe_final_acum = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    haber_final_acum = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    saldo = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    saldo_final_deudor = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    saldo_final_acreedor = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    debe_inicial_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    haber_inicial_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    saldo_inicial_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    debe_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    haber_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    debe_final_acum_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    haber_final_acum_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    saldo_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )


class BalanceComprobacionResponseSerializer(_BaseReporteMetaSerializer):
    fecha_desde = serializers.DateField(allow_null=True, read_only=True)
    fecha_hasta = serializers.DateField(allow_null=True, read_only=True)
    id_diario = serializers.UUIDField(allow_null=True, read_only=True)
    diario_nombre = serializers.CharField(allow_blank=True, read_only=True)
    cuentas = BalanceComprobacionCuentaSerializer(many=True, read_only=True)
    total_debe_inicial = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_haber_inicial = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_saldo_inicial_deudor = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_saldo_inicial_acreedor = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_debe = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_haber = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_debe_periodo = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_haber_periodo = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_debe_final_acum = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_haber_final_acum = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_saldo_final_deudor = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_saldo_final_acreedor = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    cuadrado = serializers.BooleanField(read_only=True)
    total_debe_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    total_haber_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )


class EstadoFinancieroCuentaSerializer(serializers.Serializer):
    id_cuenta_contable = serializers.UUIDField(read_only=True)
    id_cuenta_padre = serializers.UUIDField(allow_null=True, read_only=True)
    codigo_cuenta = serializers.CharField(read_only=True)
    nombre_cuenta = serializers.CharField(read_only=True)
    tipo_cuenta = serializers.CharField(read_only=True)
    naturaleza = serializers.CharField(read_only=True)
    nivel = serializers.IntegerField(read_only=True)
    debe = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    haber = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    saldo = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    saldo_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )


class EstadoResultadosResponseSerializer(_BaseReporteMetaSerializer):
    fecha_desde = serializers.DateField(read_only=True)
    fecha_hasta = serializers.DateField(read_only=True)
    ingresos = EstadoFinancieroCuentaSerializer(many=True, read_only=True)
    costos = EstadoFinancieroCuentaSerializer(many=True, read_only=True)
    gastos = EstadoFinancieroCuentaSerializer(many=True, read_only=True)
    total_ingresos = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_costos = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_gastos = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    utilidad_bruta = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    resultado_neto = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_ingresos_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    total_costos_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    total_gastos_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    utilidad_bruta_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    resultado_neto_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )


class BalanceGeneralResponseSerializer(_BaseReporteMetaSerializer):
    fecha_corte = serializers.DateField(read_only=True)
    activos = EstadoFinancieroCuentaSerializer(many=True, read_only=True)
    pasivos = EstadoFinancieroCuentaSerializer(many=True, read_only=True)
    patrimonio = EstadoFinancieroCuentaSerializer(many=True, read_only=True)
    total_activos = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_pasivos = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_patrimonio = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    resultado_periodo = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_pasivo_patrimonio_y_resultado = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    ecuacion_cuadrada = serializers.BooleanField(read_only=True)
    total_activos_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    total_pasivos_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    total_patrimonio_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    resultado_periodo_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    total_pasivo_patrimonio_y_resultado_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )


class LibroMayorMovimientoSerializer(serializers.Serializer):
    id_detalle_asiento = serializers.UUIDField(read_only=True)
    id_asiento = serializers.UUIDField(read_only=True)
    fecha_asiento = serializers.DateField(read_only=True)
    numero_asiento = serializers.CharField(read_only=True)
    descripcion_asiento = serializers.CharField(read_only=True)
    descripcion_detalle = serializers.CharField(allow_blank=True, read_only=True)
    id_diario = serializers.UUIDField(allow_null=True, read_only=True)
    diario_codigo = serializers.CharField(allow_blank=True, read_only=True)
    diario_nombre = serializers.CharField(allow_blank=True, read_only=True)
    id_cuenta_contable = serializers.UUIDField(read_only=True)
    codigo_cuenta = serializers.CharField(read_only=True)
    nombre_cuenta = serializers.CharField(read_only=True)
    id_contacto = serializers.UUIDField(allow_null=True, read_only=True)
    contacto_nombre = serializers.CharField(allow_blank=True, read_only=True)
    debe = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    haber = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    saldo_corrido = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    debe_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    haber_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    saldo_corrido_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )


class LibroMayorAuxiliarResponseSerializer(_BaseReporteMetaSerializer):
    fecha_desde = serializers.DateField(allow_null=True, read_only=True)
    fecha_hasta = serializers.DateField(allow_null=True, read_only=True)
    id_cuenta_contable = serializers.UUIDField(allow_null=True, read_only=True)
    cuenta_label = serializers.CharField(allow_blank=True, read_only=True)
    id_contacto = serializers.UUIDField(allow_null=True, read_only=True)
    contacto_label = serializers.CharField(allow_blank=True, read_only=True)
    id_diario = serializers.UUIDField(allow_null=True, read_only=True)
    diario_label = serializers.CharField(allow_blank=True, read_only=True)
    limit = serializers.IntegerField(read_only=True)
    saldo_inicial = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_debe = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_haber = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    saldo_final = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    truncado = serializers.BooleanField(read_only=True)
    movimientos = LibroMayorMovimientoSerializer(many=True, read_only=True)
    saldo_inicial_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    total_debe_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    total_haber_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
    saldo_final_usd = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True, read_only=True
    )
