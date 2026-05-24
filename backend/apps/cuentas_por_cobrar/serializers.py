from rest_framework import serializers

from .models import CuentaPorCobrar


class CuentaPorCobrarSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.CharField(source="cliente.razon_social", read_only=True)
    saldo_pendiente = serializers.SerializerMethodField()

    class Meta:
        model = CuentaPorCobrar
        fields = "__all__"

    def get_saldo_pendiente(self, obj):
        from django.db.models import Sum
        from decimal import Decimal
        total_abonado = obj.abonos.aggregate(t=Sum("monto"))["t"] or Decimal("0")
        return str(obj.monto - total_abonado)
