from rest_framework import serializers
from .models import (
    ListaMateriales, RutaProduccion, OrdenProduccion, ConsumoMaterial,
    ProduccionTerminada, ListaMaterialesDetalle, CentroTrabajo,
    OperacionProduccion, RutaProduccionDetalle, RegistroOperacion
)

class ListaMaterialesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListaMateriales
        fields = '__all__'

class RutaProduccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RutaProduccion
        fields = '__all__'

class OrdenProduccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrdenProduccion
        fields = '__all__'

class ConsumoMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConsumoMaterial
        fields = '__all__'

class ProduccionTerminadaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProduccionTerminada
        fields = '__all__'


class ListaMaterialesDetalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListaMaterialesDetalle
        fields = '__all__'


class CentroTrabajoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CentroTrabajo
        fields = '__all__'


class OperacionProduccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperacionProduccion
        fields = '__all__'


class RutaProduccionDetalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = RutaProduccionDetalle
        fields = '__all__'


class RegistroOperacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RegistroOperacion
        fields = '__all__'
