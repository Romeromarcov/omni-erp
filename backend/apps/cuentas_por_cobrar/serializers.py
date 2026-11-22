from drf_yasg.utils import swagger_serializer_method
from rest_framework import serializers

from .models import CuentaPorCobrar


class CuentaPorCobrarSerializer(serializers.ModelSerializer):
    # Nombre resuelto del deudor: razón social del crm.Cliente (FK) o el nombre
    # externo denormalizado (Odoo). Plan D-D1: la FK es opcional.
    cliente_nombre = serializers.CharField(source="cliente_display", read_only=True)
    cliente_ref = serializers.CharField(read_only=True)
    contacto_id = serializers.SerializerMethodField()
    saldo_pendiente = serializers.SerializerMethodField()

    class Meta:
        model = CuentaPorCobrar
        # CTF-005 (fase 3): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id",
            "cliente_nombre",
            "cliente_ref",
            "contacto_id",
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

    @swagger_serializer_method(serializer_or_field=serializers.UUIDField(allow_null=True))
    def get_contacto_id(self, obj):
        if obj.cliente_id and obj.cliente and obj.cliente.contacto_id:
            return str(obj.cliente.contacto_id)
        externo = (obj.cliente_externo_id or "").strip()
        if externo.startswith("proveedor:"):
            raw_prov = externo[len("proveedor:") :].strip()
            try:
                from uuid import UUID

                from apps.proveedores.models import Proveedor

                prov_uuid = UUID(raw_prov)
                cid = (
                    Proveedor.objects.filter(pk=prov_uuid, id_empresa_id=obj.empresa_id)
                    .values_list("contacto_id", flat=True)
                    .first()
                )
                return str(cid) if cid else None
            except (ValueError, TypeError):
                return None
        return None

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
