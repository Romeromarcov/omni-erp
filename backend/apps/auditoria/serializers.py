from rest_framework import serializers

from .models import LogAuditoria


class LogAuditoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogAuditoria
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_log_auditoria",
            "id_entidad_afectada",
            "nombre_entidad_afectada",
            "modulo",
            "tipo_accion",
            "descripcion_accion",
            "cambios_json",
            "fecha_hora_accion",
            "direccion_ip",
            "navegador_info",
            "id_empresa",
            "id_usuario",
        ]
