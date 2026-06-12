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
        fields = "__all__"
        # empresa se inyecta en perform_create desde request.user — R-CODE-1
        read_only_fields = ["empresa"]


class RutaProduccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RutaProduccion
        fields = "__all__"
        # empresa se inyecta en perform_create desde request.user — R-CODE-1
        read_only_fields = ["empresa"]


class OrdenProduccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrdenProduccion
        fields = "__all__"
        # empresa se inyecta en perform_create desde request.user — R-CODE-1
        read_only_fields = ["empresa"]


class ConsumoMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsumoMaterial
        fields = "__all__"


class ProduccionTerminadaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProduccionTerminada
        fields = "__all__"


class ListaMaterialesDetalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListaMaterialesDetalle
        fields = "__all__"


class CentroTrabajoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CentroTrabajo
        fields = "__all__"


class OperacionProduccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperacionProduccion
        fields = "__all__"


class RutaProduccionDetalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RutaProduccionDetalle
        fields = "__all__"


class RegistroOperacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistroOperacion
        fields = "__all__"


class EtapaProduccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EtapaProduccion
        fields = "__all__"
        # empresa se inyecta en perform_create desde request.user — R-CODE-1
        read_only_fields = ["empresa"]


class EtapaOrdenProduccionSerializer(serializers.ModelSerializer):
    etapa_codigo = serializers.CharField(source="etapa.codigo", read_only=True)
    etapa_nombre = serializers.CharField(source="etapa.nombre", read_only=True)
    costo_mano_obra = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model = EtapaOrdenProduccion
        fields = "__all__"
        # las transiciones pasan por el service (avanzar_etapa_orden) — solo lectura
        read_only_fields = [
            "orden_produccion", "etapa", "orden", "estado", "horas_trabajadas",
            "tarifa_hora", "cantidad_destajo", "pago_destajo", "completada_por",
            "fecha_completada",
        ]


class ConfiguracionManufacturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionManufactura
        fields = "__all__"
        # empresa se inyecta en perform_create desde request.user — R-CODE-1
        read_only_fields = ["empresa"]
