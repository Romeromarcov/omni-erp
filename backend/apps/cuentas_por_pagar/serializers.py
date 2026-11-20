from rest_framework import serializers

from .models import CuentaPorPagar


class CuentaPorPagarSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(
        source="id_proveedor.razon_social", read_only=True, allow_blank=True, default=""
    )
    contacto_id = serializers.UUIDField(
        source="id_proveedor.contacto_id", read_only=True, allow_null=True, default=None
    )

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
            "proveedor_nombre",
            "contacto_id",
            "id_factura_compra",
        ]
