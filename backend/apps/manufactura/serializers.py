from rest_framework import serializers

from .models import (
    CentroTrabajo,
    ConfiguracionManufactura,
    ConsumoMaterial,
    EtapaOrdenProduccion,
    EtapaProduccion,
    ListaMateriales,
    ListaMaterialesDetalle,
    OperacionProduccion,
    OrdenProduccion,
    ProduccionTerminada,
    RegistroOperacion,
    RutaProduccion,
    RutaProduccionDetalle,
)


class ListaMaterialesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListaMateriales
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "referencia_externa",
            "documento_json",
            "nombre",
            "descripcion",
            "empresa",
            "producto_final",
        ]
        # empresa se inyecta en perform_create desde request.user — R-CODE-1
        read_only_fields = ["empresa"]


class RutaProduccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RutaProduccion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "referencia_externa",
            "documento_json",
            "nombre",
            "descripcion",
            "empresa",
        ]
        # empresa se inyecta en perform_create desde request.user — R-CODE-1
        read_only_fields = ["empresa"]


class OrdenProduccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrdenProduccion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "cantidad",
            "fecha_inicio",
            "fecha_fin",
            "referencia_externa",
            "documento_json",
            "tipo_operacion",
            "fecha_cierre_estimada",
            "estado",
            "observaciones",
            "producto",
            "empresa",
            "lista_materiales",
            "ruta_produccion",
        ]
        # empresa se inyecta en perform_create desde request.user — R-CODE-1
        read_only_fields = ["empresa"]

    def validate_cantidad(self, value):
        # CTF-015.2: la API permitía crear/actualizar OF con cantidad 0 (el
        # costeo luego respondía 400 para no dividir entre cero). Paridad con
        # el service crear_orden_produccion: la cantidad debe ser positiva.
        if value <= 0:
            raise serializers.ValidationError("La cantidad de la orden debe ser positiva.")
        return value


class ConsumoMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsumoMaterial
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "referencia_externa",
            "documento_json",
            "cantidad",
            "costo_unitario",
            "orden_produccion",
            "producto",
        ]


class ProduccionTerminadaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProduccionTerminada
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "referencia_externa",
            "documento_json",
            "cantidad",
            "fecha",
            "orden_produccion",
        ]


class ListaMaterialesDetalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListaMaterialesDetalle
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_detalle_lista",
            "cantidad_requerida",
            "es_opcional",
            "observaciones",
            "id_lista_materiales",
            "id_producto",
            "id_unidad_medida",
        ]


class CentroTrabajoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CentroTrabajo
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_centro_trabajo",
            "codigo_centro",
            "nombre_centro",
            "descripcion",
            "tipo_centro",
            "capacidad_horas_dia",
            "costo_hora",
            "activo",
            "fecha_creacion",
            "id_empresa",
        ]


class OperacionProduccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperacionProduccion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_operacion",
            "codigo_operacion",
            "nombre_operacion",
            "descripcion",
            "tiempo_estandar_minutos",
            "activo",
            "fecha_creacion",
            "id_empresa",
        ]


class RutaProduccionDetalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RutaProduccionDetalle
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_detalle_ruta",
            "numero_secuencia",
            "tiempo_preparacion_minutos",
            "tiempo_operacion_minutos",
            "observaciones",
            "id_ruta_produccion",
            "id_operacion",
            "id_centro_trabajo",
        ]


class RegistroOperacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistroOperacion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_registro",
            "fecha_inicio",
            "fecha_fin",
            "cantidad_procesada",
            "cantidad_defectuosa",
            "estado",
            "observaciones",
            "fecha_creacion",
            "id_orden_produccion",
            "id_detalle_ruta",
            "id_empleado",
        ]


class EtapaProduccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EtapaProduccion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "activo",
            "codigo",
            "nombre",
            "orden",
            "tarifa_destajo",
            "descripcion",
            "fecha_creacion",
            "empresa",
        ]
        # empresa se inyecta en perform_create desde request.user — R-CODE-1
        read_only_fields = ["empresa"]


class EtapaOrdenProduccionSerializer(serializers.ModelSerializer):
    etapa_codigo = serializers.CharField(source="etapa.codigo", read_only=True)
    etapa_nombre = serializers.CharField(source="etapa.nombre", read_only=True)
    costo_mano_obra = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model = EtapaOrdenProduccion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "etapa_codigo",
            "etapa_nombre",
            "costo_mano_obra",
            "orden",
            "estado",
            "horas_trabajadas",
            "tarifa_hora",
            "cantidad_destajo",
            "pago_destajo",
            "fecha_completada",
            "observaciones",
            "orden_produccion",
            "etapa",
            "completada_por",
        ]
        # las transiciones pasan por el service (avanzar_etapa_orden) — solo lectura
        read_only_fields = [
            "orden_produccion", "etapa", "orden", "estado", "horas_trabajadas",
            "tarifa_hora", "cantidad_destajo", "pago_destajo", "completada_por",
            "fecha_completada",
        ]


class ConfiguracionManufacturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionManufactura
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "porcentaje_overhead",
            "empresa",
        ]
        # empresa se inyecta en perform_create desde request.user — R-CODE-1
        read_only_fields = ["empresa"]
