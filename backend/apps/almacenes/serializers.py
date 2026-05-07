from rest_framework import serializers
from .models import Almacen, UbicacionAlmacen

class AlmacenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Almacen
        fields = '__all__'


class UbicacionAlmacenSerializer(serializers.ModelSerializer):
    class Meta:
        model = UbicacionAlmacen
        fields = '__all__'
