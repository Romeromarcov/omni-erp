"""
Serializers de Pagos de Terceros (Zelle) — Capa B §6.6.

``estado``, ``comision`` y las FKs a los documentos generados (abono CxP /
CxC de reintegro) son de SOLO lectura: el ciclo de vida se maneja únicamente
con las acciones del ViewSet (abonar / solicitar-reintegro / asociar-proveedor
/ marcar-reintegrado / anular), nunca con un PATCH directo.
"""

from decimal import Decimal

from rest_framework import serializers

from .models import PagoTercero


class PagoTerceroSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(
        source="id_proveedor.razon_social", read_only=True, default=None
    )
    moneda_codigo = serializers.CharField(
        source="id_moneda.codigo_iso", read_only=True, default=None
    )

    class Meta:
        model = PagoTercero
        fields = [
            "id_pago_tercero",
            "id_empresa",
            "id_proveedor",
            "proveedor_nombre",
            "id_moneda",
            "moneda_codigo",
            "monto",
            "comision",
            "referencia_zelle",
            "fecha",
            "concepto",
            "estado",
            "id_abono_cxp",
            "id_cxc_reintegro",
            "referencia_externa",
            "documento_json",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_pago_tercero",
            "estado",
            "comision",
            "id_abono_cxp",
            "id_cxc_reintegro",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def validate_monto(self, value):
        if value is None or Decimal(str(value)) <= 0:
            raise serializers.ValidationError("El monto debe ser mayor a cero.")
        return value

    def validate(self, attrs):
        # Un pago que ya movió dinero (abonado/reintegro) o se cerró es INMUTABLE
        # por PATCH/PUT: su historia financiera no puede reescribirse. Las
        # transiciones van solo por las acciones del ViewSet.
        if self.instance is not None and self.instance.estado != "pendiente":
            raise serializers.ValidationError(
                {
                    "detail": (
                        f"Un pago de tercero en estado '{self.instance.estado}' no es "
                        "editable. Use las acciones del ciclo de vida."
                    )
                }
            )

        # R-CODE-1: el proveedor debe pertenecer a la MISMA empresa del pago.
        # (TenantFKScopeMixin ya acota ambos a empresas visibles del usuario;
        # esto cierra el caso de un usuario con varias empresas visibles.)
        empresa = attrs.get("id_empresa") or getattr(self.instance, "id_empresa", None)
        proveedor = attrs.get("id_proveedor") or getattr(self.instance, "id_proveedor", None)
        if empresa is not None and proveedor is not None:
            if str(proveedor.id_empresa_id) != str(empresa.pk):
                raise serializers.ValidationError(
                    {"id_proveedor": "El proveedor no pertenece a la empresa indicada."}
                )
        return attrs
