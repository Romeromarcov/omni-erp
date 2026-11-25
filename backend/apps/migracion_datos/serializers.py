from rest_framework import serializers

from .migrador_1click import ENTIDADES_SOPORTADAS, FUENTES_SOPORTADAS
from .models import DetalleErrorMigracion, PlantillaMigracion, ProcesoMigracion


class _NoNulStringMixin:
    def _check_no_nul(self, value: str | None, field: str) -> str | None:
        if value is not None and "\x00" in value:
            raise serializers.ValidationError(f"El campo '{field}' contiene caracteres inválidos.")
        return value


class Migrador1ClickInputSerializer(_NoNulStringMixin, serializers.Serializer):
    id_empresa = serializers.UUIDField(required=False, allow_null=True)
    fuente = serializers.ChoiceField(choices=FUENTES_SOPORTADAS)
    entidad = serializers.ChoiceField(choices=ENTIDADES_SOPORTADAS)
    id_conector = serializers.UUIDField(required=False, allow_null=True)
    contenido_csv = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=2_000_000)
    limite = serializers.IntegerField(required=False, default=500, min_value=1, max_value=2000)

    def validate_contenido_csv(self, value):
        return self._check_no_nul(value, "contenido_csv")

    def validate(self, attrs):
        fuente = attrs["fuente"]
        if fuente == "ODOO":
            if not attrs.get("id_conector"):
                raise serializers.ValidationError({"id_conector": "Requerido cuando fuente es ODOO."})
        else:
            csv_txt = attrs.get("contenido_csv")
            if not csv_txt or not csv_txt.strip():
                raise serializers.ValidationError({"contenido_csv": f"Requerido cuando fuente es {fuente}."})
        return attrs


class Migrador1ClickPreviewInputSerializer(Migrador1ClickInputSerializer):
    muestra = serializers.IntegerField(required=False, default=10, min_value=1, max_value=50)


class Migrador1ClickFormatosResponseSerializer(serializers.Serializer):
    odoo_solo_lectura = serializers.BooleanField()
    odoo_metodos_permitidos = serializers.ListField(child=serializers.CharField())
    fuentes = serializers.ListField(child=serializers.DictField())
    entidades = serializers.ListField(child=serializers.CharField())
    columnas_canonicas = serializers.DictField()


class Migrador1ClickPreviewResponseSerializer(serializers.Serializer):
    empresa_id = serializers.UUIDField()
    fuente = serializers.CharField()
    entidad = serializers.CharField()
    dry_run = serializers.BooleanField()
    total_detectados = serializers.IntegerField()
    validos = serializers.IntegerField()
    invalidos = serializers.IntegerField()
    muestra_normalizada = serializers.ListField(child=serializers.DictField())
    errores = serializers.ListField(child=serializers.DictField())


class Migrador1ClickEjecutarResponseSerializer(serializers.Serializer):
    id_proceso_migracion = serializers.UUIDField()
    empresa_id = serializers.UUIDField()
    fuente = serializers.CharField()
    entidad = serializers.CharField()
    estado_proceso = serializers.CharField()
    total_detectados = serializers.IntegerField()
    total_exitosos = serializers.IntegerField()
    creados = serializers.IntegerField()
    actualizados = serializers.IntegerField()
    total_fallidos = serializers.IntegerField()
    errores = serializers.ListField(child=serializers.DictField())


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
