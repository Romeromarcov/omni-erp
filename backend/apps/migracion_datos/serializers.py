from rest_framework import serializers

from .models import DetalleErrorMigracion, PlantillaMigracion, ProcesoMigracion


class PlantillaMigracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantillaMigracion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_plantilla_migracion",
            "nombre_plantilla",
            "modulo_destino",
            "modelo_destino",
            "formato_archivo",
            "estructura_json",
            "activo",
            "fecha_creacion",
        ]


class ProcesoMigracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcesoMigracion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_proceso_migracion",
            "fecha_inicio",
            "fecha_fin",
            "estado_proceso",
            "total_registros_procesados",
            "total_registros_exitosos",
            "total_registros_fallidos",
            "ruta_archivo_cargado",
            "ruta_archivo_errores",
            "id_empresa",
            "id_plantilla_migracion",
            "id_usuario_ejecutor",
        ]


class DetalleErrorMigracionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleErrorMigracion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_detalle_error",
            "numero_fila_archivo",
            "campo_error",
            "mensaje_error",
            "datos_originales_json",
            "fecha_registro_error",
            "id_proceso_migracion",
        ]
