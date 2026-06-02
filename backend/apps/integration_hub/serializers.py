"""
Serializers del Integration Hub.
"""
from rest_framework import serializers

from .models import (
    ConectorInstancia,
    ConectorProveedor,
    EntidadSincronizada,
    JobSincronizacion,
    LogDetalleSincronizacion,
)


class ConectorProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConectorProveedor
        fields = [
            "id_proveedor", "codigo", "nombre", "descripcion",
            "icono_url", "versiones_soportadas", "capacidades",
            "requiere_url", "requiere_db", "estado", "activo", "orden",
        ]
        read_only_fields = fields


class ConectorInstanciaSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(
        source="id_proveedor.nombre", read_only=True
    )
    proveedor_codigo = serializers.CharField(
        source="id_proveedor.codigo", read_only=True
    )
    proveedor_capacidades = serializers.JSONField(
        source="id_proveedor.capacidades", read_only=True
    )
    # Nunca serializar configuracion completa — R-CODE-8
    # Solo mostrar campos seguros (host, user) sin api_key ni password
    configuracion_publica = serializers.SerializerMethodField()

    class Meta:
        model = ConectorInstancia
        fields = [
            "id_conector", "id_empresa", "id_proveedor",
            "proveedor_nombre", "proveedor_codigo", "proveedor_capacidades",
            "nombre", "configuracion_publica",
            "estado", "mensaje_estado",
            "ultimo_test_conexion", "ultimo_sync",
            "intervalo_sync_minutos", "entidades_activas",
            "version_detectada", "activo",
            "fecha_creacion", "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_conector", "id_empresa",
            "proveedor_nombre", "proveedor_codigo", "proveedor_capacidades",
            "configuracion_publica",
            "estado", "mensaje_estado",
            "ultimo_test_conexion", "ultimo_sync",
            "version_detectada",
            "fecha_creacion", "fecha_actualizacion",
        ]

    def get_configuracion_publica(self, obj) -> dict:
        """Retorna solo campos seguros de configuracion (sin api_key)."""
        cfg = obj.get_config()
        return {
            "host": cfg.get("host", ""),
            "db": cfg.get("db", ""),
            "user": cfg.get("user", ""),
            "timeout": cfg.get("timeout", 30),
            # api_key: nunca (R-CODE-8)
        }


class ConectorInstanciaCreateSerializer(serializers.ModelSerializer):
    """Serializer de creación/edición que acepta configuracion completa."""

    class Meta:
        model = ConectorInstancia
        fields = [
            "id_proveedor", "nombre", "configuracion",
            "intervalo_sync_minutos", "entidades_activas", "activo",
        ]

    def validate_configuracion(self, value: dict) -> dict:
        """Valida que la configuracion tenga los campos mínimos."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("La configuración debe ser un objeto JSON.")
        if not value.get("host"):
            raise serializers.ValidationError("Se requiere el campo 'host'.")
        if not value.get("user"):
            raise serializers.ValidationError("Se requiere el campo 'user'.")
        if not value.get("api_key"):
            raise serializers.ValidationError("Se requiere el campo 'api_key'.")
        return value

    def validate_nombre(self, value: str) -> str:
        """El nombre debe ser único por empresa."""
        # SEC-NEW-2: empresa vía el helper vetado get_empresas_visible.
        from apps.core.viewsets import get_empresas_visible

        empresa = get_empresas_visible(self.context["request"].user).first()
        qs = ConectorInstancia.objects.filter(id_empresa=empresa, nombre=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Ya existe un conector con el nombre '{value}' en esta empresa."
            )
        return value


class JobSincronizacionSerializer(serializers.ModelSerializer):
    instancia_nombre = serializers.CharField(
        source="id_instancia.nombre", read_only=True
    )
    duracion_segundos = serializers.FloatField(read_only=True)
    iniciado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = JobSincronizacion
        fields = [
            "id_job", "id_instancia", "instancia_nombre",
            "tipo_entidad", "direccion", "estado",
            "total_registros", "procesados",
            "creados", "actualizados", "omitidos", "fallidos",
            "resumen_errores",
            "iniciado_en", "completado_en", "duracion_segundos",
            "iniciado_por", "iniciado_por_nombre",
            "parametros",
        ]
        read_only_fields = [f for f in fields if f not in ("tipo_entidad", "direccion", "parametros")]

    def get_iniciado_por_nombre(self, obj) -> str:
        if obj.iniciado_por:
            return getattr(obj.iniciado_por, "get_full_name", lambda: "")() or str(obj.iniciado_por)
        return "Automático"


class JobSincronizacionTriggerSerializer(serializers.Serializer):
    """Serializer para disparar un job manualmente."""
    tipo_entidad = serializers.ChoiceField(choices=[
        "contactos", "productos", "pedidos_venta", "pedidos_compra",
        "facturas_venta", "pagos", "inventario",
    ])
    direccion = serializers.ChoiceField(
        choices=["inbound", "outbound", "bidireccional"],
        default="inbound",
    )
    sync_completo = serializers.BooleanField(
        default=False,
        help_text="True = ignorar último sync, traer todos los registros.",
    )
    desde = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Fecha ISO desde la cual sincronizar (opcional).",
    )


class LogDetalleSincronizacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogDetalleSincronizacion
        fields = [
            "id_log", "id_job",
            "id_externo", "id_omni", "operacion",
            "resumen_externo", "mensaje_error", "creado_en",
        ]
        read_only_fields = fields


class EntidadSincronizadaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntidadSincronizada
        fields = [
            "id_entidad_sync", "id_instancia",
            "tipo_entidad", "id_externo", "id_omni",
            "modelo_omni", "ultimo_sync", "activo",
        ]
        read_only_fields = fields
