from rest_framework import serializers

from .models import CuentaPorPagar


class CuentaPorPagarSerializer(serializers.ModelSerializer):
    class Meta:
        model = CuentaPorPagar
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_cxp",
            "referencia_externa",
            "documento_json",
            "tipo_operacion",
            "fecha_cierre_estimada",
            "monto_total",
            "monto_pendiente",
            "fecha_emision",
            "fecha_vencimiento",
            "estado",
            "observaciones",
            "activo",
            "fecha_creacion",
            "id_empresa",
            "id_proveedor",
            "id_factura_compra",
        ]
