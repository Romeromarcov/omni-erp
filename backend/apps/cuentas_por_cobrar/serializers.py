from rest_framework import serializers

from .models import CuentaPorCobrar


class CuentaPorCobrarSerializer(serializers.ModelSerializer):
    # Nombre resuelto del deudor: razón social del crm.Cliente (FK) o el nombre
    # externo denormalizado (Odoo). Plan D-D1: la FK es opcional.
    cliente_nombre = serializers.CharField(source="cliente_display", read_only=True)
    cliente_ref = serializers.CharField(read_only=True)
    saldo_pendiente = serializers.SerializerMethodField()

    class Meta:
        model = CuentaPorCobrar
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "cliente_nombre",
            "cliente_ref",
            "saldo_pendiente",
            "cliente_externo_id",
            "cliente_externo_nombre",
            "monto",
            "fecha_emision",
            "fecha_vencimiento",
            "referencia_externa",
            "documento_json",
            "tipo_operacion",
            "fecha_cierre_estimada",
            "estado",
            "descripcion",
            "cliente",
            "empresa",
        ]

    def get_saldo_pendiente(self, obj):
        # BUG-M2: el queryset del list anota `total_abonado_agg` (una sola
        # consulta); el aggregate por instancia queda solo como fallback
        # para instancias sin anotación (p. ej. retrieve/create).
        total_abonado = getattr(obj, "total_abonado_agg", None)
        if total_abonado is None:
            from decimal import Decimal

            from django.db.models import Sum

            total_abonado = obj.abonos.aggregate(t=Sum("monto"))["t"] or Decimal("0")
        return str(obj.monto - total_abonado)
