"""
Serializadores de despacho/entrega.

Campos de control (estado, numero, timestamps de transición, documento_json,
id_empresa) son **read-only**: el estado solo cambia por las acciones de
transición y la empresa se deriva del almacén de origen (H-API-1: nunca se
confía en el id_empresa del payload).
"""

from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from . import models
from .services import ESTADOS_NOTA_DESPACHABLES


class DetalleDespachoSerializer(serializers.ModelSerializer):
    nombre_producto = serializers.CharField(
        source="id_producto.nombre_producto", read_only=True
    )
    unidad_medida = serializers.CharField(
        source="id_unidad_medida.abreviatura", read_only=True
    )

    class Meta:
        model = models.DetalleDespacho
        fields = [
            "id_detalle_despacho",
            "id_despacho",
            "id_producto",
            "nombre_producto",
            "cantidad_despachada",
            "id_unidad_medida",
            "unidad_medida",
            "lote",
            "fecha_vencimiento",
            "observaciones",
        ]
        read_only_fields = fields


class DespachoSerializer(serializers.ModelSerializer):
    detalles = DetalleDespachoSerializer(many=True, read_only=True)
    numero_nota_venta = serializers.CharField(
        source="id_nota_venta.numero_nota", read_only=True
    )
    nombre_almacen = serializers.CharField(
        source="id_almacen_origen.nombre_almacen", read_only=True
    )
    # Opcional al crear: por defecto el documento se fecha "ahora".
    fecha_despacho = serializers.DateTimeField(default=timezone.now)

    class Meta:
        model = models.Despacho
        fields = [
            "id_despacho",
            "id_empresa",
            "numero_despacho",
            "id_nota_venta",
            "numero_nota_venta",
            "id_pedido",
            "fecha_despacho",
            "id_almacen_origen",
            "nombre_almacen",
            "direccion_destino",
            "id_transportista",
            "estado_despacho",
            "fecha_entrega_estimada",
            "fecha_en_ruta",
            "fecha_entrega_real",
            "fecha_devolucion",
            "fecha_cancelacion",
            "observaciones",
            "referencia_externa",
            "documento_json",
            "detalles",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_despacho",
            "id_empresa",          # inyectada desde el almacén (H-API-1)
            "numero_despacho",     # correlativo fiscal por empresa
            "estado_despacho",     # solo cambia vía acciones de transición
            "fecha_en_ruta",
            "fecha_entrega_real",
            "fecha_devolucion",
            "fecha_cancelacion",
            "documento_json",      # evidencia de entrega/devolución/cancelación
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def validate(self, attrs):
        """
        Coherencia multi-tenant entre las FKs del payload (R-CODE-1): la
        empresa del despacho es la del almacén de origen, y la nota de venta,
        el pedido y el transportista deben pertenecer a esa misma empresa.
        (TenantFKScopeMixin ya acota cada FK a las empresas *visibles*; aquí se
        exige además que no se mezclen empresas entre sí.)
        """
        instance = getattr(self, "instance", None)

        def _actual(campo):
            if campo in attrs:
                return attrs[campo]
            return getattr(instance, campo, None) if instance is not None else None

        almacen = _actual("id_almacen_origen")
        if almacen is None:  # create siempre lo trae (required); update parcial usa el actual
            return attrs
        empresa_id = almacen.id_empresa_id

        nota = _actual("id_nota_venta")
        if nota is not None and nota.id_empresa_id != empresa_id:
            raise serializers.ValidationError(
                {"id_nota_venta": "La nota de venta no pertenece a la empresa del almacén."}
            )
        if nota is not None and "id_nota_venta" in attrs and nota.estado not in ESTADOS_NOTA_DESPACHABLES:
            raise serializers.ValidationError(
                {
                    "id_nota_venta": (
                        "Solo se vincula a notas ENTREGADAS o FACTURADAS "
                        f"(estado actual: {nota.estado})."
                    )
                }
            )
        pedido = _actual("id_pedido")
        if pedido is not None and pedido.id_empresa_id != empresa_id:
            raise serializers.ValidationError(
                {"id_pedido": "El pedido no pertenece a la empresa del almacén."}
            )
        transportista = _actual("id_transportista")
        if transportista is not None and transportista.empresa_id != empresa_id:
            raise serializers.ValidationError(
                {"id_transportista": "El transportista no pertenece a la empresa del almacén."}
            )
        if instance is not None and "id_almacen_origen" in attrs:
            if almacen.id_empresa_id != instance.id_empresa_id:
                raise serializers.ValidationError(
                    {"id_almacen_origen": "El almacén no pertenece a la empresa del despacho."}
                )
        return attrs


# ── Payloads de acciones ──────────────────────────────────────────────────────


class LineaDespachoInputSerializer(serializers.Serializer):
    """Línea solicitada al crear un despacho parcial desde la venta."""

    id_producto = serializers.UUIDField()
    cantidad = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal("0.0001")
    )


class DespachoDesdeNotaVentaSerializer(serializers.Serializer):
    """Payload de POST /despachos/desde-nota-venta/."""

    id_nota_venta = serializers.UUIDField()
    almacen_id = serializers.UUIDField()
    direccion_entrega = serializers.CharField(max_length=2000)
    # rrhh.Empleado usa pk entero (BigAutoField), no UUID.
    id_transportista = serializers.IntegerField(required=False, allow_null=True)
    fecha_entrega_estimada = serializers.DateTimeField(required=False, allow_null=True)
    observaciones = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    # Sin "lineas" => se despacha todo lo pendiente de la nota.
    lineas = LineaDespachoInputSerializer(many=True, required=False)


class IniciarRutaSerializer(serializers.Serializer):
    """Payload opcional de POST /despachos/{pk}/iniciar-ruta/."""

    # rrhh.Empleado usa pk entero (BigAutoField), no UUID.
    id_transportista = serializers.IntegerField(required=False, allow_null=True)


class EntregaDespachoSerializer(serializers.Serializer):
    """Payload de POST /despachos/{pk}/entregar/ (receptor obligatorio)."""

    receptor = serializers.CharField(max_length=200)
    documento_receptor = serializers.CharField(required=False, allow_blank=True, max_length=50)
    # Imagen de firma en base64 (~375 KB máx): acotada para no inflar documento_json.
    firma_base64 = serializers.CharField(required=False, allow_blank=True, max_length=500_000)


class MotivoDespachoSerializer(serializers.Serializer):
    """Payload de /devolver/ y /cancelar/ (motivo obligatorio)."""

    motivo = serializers.CharField(max_length=1000)
