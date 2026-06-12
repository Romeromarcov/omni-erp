import logging

from rest_framework import serializers

from apps.crm.models import Cliente
from apps.inventario.models import Producto

from .models import (
    ComisionVenta,
    Cotizacion,
    DetalleCotizacion,
    DetalleDevolucionVenta,
    DetalleFacturaFiscal,
    DetalleNotaCreditoFiscal,
    DetalleNotaCreditoVenta,
    DetalleNotaVenta,
    DetallePedido,
    DetallePrecio,
    DevolucionVenta,
    EsquemaComision,
    EsquemaComisionCategoria,
    FacturaFiscal,
    ListaPrecio,
    NotaCreditoFiscal,
    NotaCreditoVenta,
    NotaVenta,
    Pedido,
)

logger = logging.getLogger(__name__)


# BUG-DUP-2: este serializer (con id_producto anidado para lectura) se usaba con el
# MISMO nombre que el de validación de más abajo; Python ligaba según la posición
# (PedidoSerializer.detalles usaba este; el ViewSet usaba el otro). Se renombra para
# eliminar la colisión sin cambiar comportamiento.
class DetallePedidoNestedSerializer(serializers.ModelSerializer):
    id_pedido = serializers.PrimaryKeyRelatedField(queryset=Pedido.objects.all(), required=False)
    id_producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all())

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        prod = getattr(instance, "id_producto", None)
        if prod:
            rep["id_producto"] = {
                "id_producto": str(getattr(prod, "id_producto", "")),
                "nombre_producto": getattr(prod, "nombre_producto", ""),
                "sku": getattr(prod, "sku", ""),
            }
        else:
            rep["id_producto"] = None
        return rep

    class Meta:
        model = DetallePedido
        fields = "__all__"


class PedidoSerializer(serializers.ModelSerializer):
    detalles = DetallePedidoNestedSerializer(many=True, required=False)
    # Cliente anidado para mostrar nombre, razon_social, rif, telefono
    id_cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.all())

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        cli = getattr(instance, "id_cliente", None)
        if cli:
            rep["id_cliente"] = {
                "id_cliente": str(getattr(cli, "id_cliente", "")),
                "nombre": getattr(cli, "nombre", ""),
                "razon_social": getattr(cli, "razon_social", ""),
                "rif": getattr(cli, "rif", ""),
                "telefono": getattr(cli, "telefono", ""),
            }
        else:
            rep["id_cliente"] = None

        # Agregar información de sucursal y usuario
        caja = getattr(instance, "id_caja", None)
        if caja:
            rep["id_caja"] = {"id_caja": str(getattr(caja, "id_caja", "")), "nombre": getattr(caja, "nombre", "")}
            sucursal = getattr(caja, "sucursal", None)
            if sucursal:
                rep["id_sucursal"] = {
                    "id_sucursal": str(getattr(sucursal, "id_sucursal", "")),
                    "nombre": getattr(sucursal, "nombre", ""),
                }

        # Usuario que creó el pedido (de documento_json o de la sesión)
        documento_json = getattr(instance, "documento_json", {}) or {}
        usuario_id = documento_json.get("id_usuario")
        if usuario_id:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            try:
                usuario = User.objects.get(id=usuario_id)
                rep["id_usuario"] = {
                    "id": usuario.id,
                    "username": usuario.username,
                    "first_name": usuario.first_name,
                    "last_name": usuario.last_name,
                }
            except User.DoesNotExist:
                pass

        return rep

    class Meta:
        model = Pedido
        exclude = ("referencia_externa", "documento_json")  # SEC-NEW-3: ocultar campos internos
        # H-API-1: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("numero_pedido", "id_empresa", "id_pedido", "fecha_creacion")

    def validate(self, data):
        if data.get("fecha_cierre_estimada") and data["fecha_cierre_estimada"] < data["fecha_pedido"]:
            raise serializers.ValidationError(
                {"fecha_cierre_estimada": "La fecha de cierre estimada no puede ser anterior a la fecha del pedido."}
            )
        return data

    def create(self, validated_data):
        detalles_data = validated_data.pop("detalles", [])

        # Asignación automática del número de pedido
        from django.db.models import Max

        from apps.core.models import Sucursal
        from apps.finanzas.models import Caja, SesionCajaFisica

        id_empresa = validated_data.get("id_empresa")

        # Buscar sucursal y caja - PRIMERO intentar usar sesión activa del usuario
        sucursal = None
        caja = None

        # Obtener usuario del contexto
        usuario = None
        if self.context and "request" in self.context:
            usuario = self.context["request"].user

        # Buscar sesión activa del usuario (acotada a la empresa — multi-tenant)
        # FIX: la rama era inalcanzable — hacía select_related("caja_fisica_principal"),
        # campo que no existe en SesionCajaFisica (el FK es `caja_fisica`); el
        # FieldError se tragaba en un except Exception y siempre caía al fallback.
        sesion_activa = None
        if usuario is not None and getattr(usuario, "is_authenticated", False):
            sesion_activa = (
                SesionCajaFisica.objects.filter(usuario=usuario, estado="ABIERTA", empresa=id_empresa)
                .select_related("caja_fisica__sucursal")
                .first()
            )

        if sesion_activa and sesion_activa.caja_fisica_id:
            # Usar la caja virtual activa asociada a la caja física de la sesión
            # (el resto del flujo — prefijo y filtro por id_caja — trabaja con Caja).
            caja = (
                Caja.objects.filter(caja_fisica=sesion_activa.caja_fisica, activa=True)
                .select_related("sucursal")
                .first()
            )
            sucursal = caja.sucursal if caja else sesion_activa.caja_fisica.sucursal
            logger.debug(
                "Usando caja de sesión activa: %s, sucursal: %s",
                caja.nombre if caja else "N/A",
                sucursal.nombre if sucursal else "N/A",
            )

        if caja is None:
            # Fallback: Si el frontend envía sucursal/caja en documento_json, extraerlo
            doc_json = validated_data.get("documento_json", {})
            sucursal_id = doc_json.get("id_sucursal")
            caja_id = doc_json.get("id_caja")

            # R-CODE-1: acotados a la empresa del pedido — un id ajeno se
            # ignora (cae al código genérico), nunca contamina cross-tenant.
            if sucursal_id:
                try:
                    sucursal = Sucursal.objects.get(
                        id_sucursal=sucursal_id, id_empresa=id_empresa
                    )
                except Sucursal.DoesNotExist:
                    sucursal = None
            if caja_id:
                try:
                    caja = Caja.objects.get(id_caja=caja_id, empresa=id_empresa)
                except Caja.DoesNotExist:
                    caja = None

        # Códigos
        codigo_sucursal = sucursal.codigo_sucursal if sucursal else "GEN"
        codigo_caja = caja.nombre[:6].upper() if caja else "CAJGEN"
        prefijo = f"{codigo_sucursal}-{codigo_caja}-"

        # Secuencia: buscar el último pedido con el mismo prefijo
        filtro = {"id_empresa": id_empresa, "numero_pedido__startswith": prefijo}
        if sucursal:
            filtro["documento_json__id_sucursal"] = str(sucursal.id_sucursal)
        if caja:
            filtro["documento_json__id_caja"] = str(caja.id_caja)

        # Obtener todos los números de pedido con este prefijo y extraer las secuencias
        pedidos_con_prefijo = Pedido.objects.filter(**filtro).values_list("numero_pedido", flat=True)
        secuencias = []
        import re

        for num_pedido in pedidos_con_prefijo:
            m = re.search(r"-([0-9]{6})$", num_pedido)
            if m:
                secuencias.append(int(m.group(1)))

        secuencia = max(secuencias) + 1 if secuencias else 1

        numero_pedido = f"{prefijo}{secuencia:06d}"
        validated_data["numero_pedido"] = numero_pedido

        # Agregar información al documento_json
        doc_json = validated_data.get("documento_json", {}) or {}
        if usuario:
            doc_json["id_usuario"] = str(usuario.id)
        if sucursal:
            doc_json["id_sucursal"] = str(sucursal.id_sucursal)
        if caja:
            doc_json["id_caja"] = str(caja.id_caja)
        validated_data["documento_json"] = doc_json

        pedido = super().create(validated_data)

        for detalle in detalles_data:
            DetallePedido.objects.create(id_pedido=pedido, **detalle)

        return pedido


class DetallePedidoSerializer(serializers.ModelSerializer):
    id_pedido = serializers.PrimaryKeyRelatedField(queryset=Pedido.objects.all(), required=False)

    class Meta:
        model = DetallePedido
        fields = "__all__"

    def validate_cantidad(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor que cero.")
        return value

    def validate_precio_unitario(self, value):
        if value < 0:
            raise serializers.ValidationError("El precio unitario debe ser mayor o igual a cero.")
        return value


class FacturaFiscalSerializer(serializers.ModelSerializer):
    # Cliente anidado para mostrar nombre, razon_social, rif, telefono
    id_cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.all())

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        cli = getattr(instance, "id_cliente", None)
        if cli:
            rep["id_cliente"] = {
                "id_cliente": str(getattr(cli, "id_cliente", "")),
                "nombre": getattr(cli, "nombre", ""),
                "razon_social": getattr(cli, "razon_social", ""),
                "rif": getattr(cli, "rif", ""),
                "telefono": getattr(cli, "telefono", ""),
            }
        else:
            rep["id_cliente"] = None
        return rep

    class Meta:
        model = FacturaFiscal
        exclude = ("referencia_externa", "documento_json")  # SEC-NEW-3: ocultar campos internos
        # H-API-1: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_factura", "fecha_creacion")


class DetalleFacturaFiscalSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleFacturaFiscal
        fields = "__all__"


class NotaCreditoVentaSerializer(serializers.ModelSerializer):
    # Cliente anidado para mostrar nombre, razon_social, rif, telefono
    id_cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.all())

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        cli = getattr(instance, "id_cliente", None)
        if cli:
            rep["id_cliente"] = {
                "id_cliente": str(getattr(cli, "id_cliente", "")),
                "nombre": getattr(cli, "nombre", ""),
                "razon_social": getattr(cli, "razon_social", ""),
                "rif": getattr(cli, "rif", ""),
                "telefono": getattr(cli, "telefono", ""),
            }
        else:
            rep["id_cliente"] = None
        return rep

    class Meta:
        model = NotaCreditoVenta
        fields = "__all__"
        # H-API-1: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_nota_credito", "fecha_creacion")


class DetalleNotaCreditoVentaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleNotaCreditoVenta
        fields = "__all__"


class DevolucionVentaSerializer(serializers.ModelSerializer):
    # Cliente anidado para mostrar nombre, razon_social, rif, telefono
    id_cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.all())

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        cli = getattr(instance, "id_cliente", None)
        if cli:
            rep["id_cliente"] = {
                "id_cliente": str(getattr(cli, "id_cliente", "")),
                "nombre": getattr(cli, "nombre", ""),
                "razon_social": getattr(cli, "razon_social", ""),
                "rif": getattr(cli, "rif", ""),
                "telefono": getattr(cli, "telefono", ""),
            }
        else:
            rep["id_cliente"] = None
        return rep

    class Meta:
        model = DevolucionVenta
        fields = "__all__"
        # H-API-1: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_devolucion", "fecha_creacion")


class DetalleDevolucionVentaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleDevolucionVenta
        fields = "__all__"


class CotizacionSerializer(serializers.ModelSerializer):
    # Cliente anidado para mostrar nombre, razon_social, rif, telefono
    id_cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.all())

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        cli = getattr(instance, "id_cliente", None)
        if cli:
            rep["id_cliente"] = {
                "id_cliente": str(getattr(cli, "id_cliente", "")),
                "nombre": getattr(cli, "nombre", ""),
                "razon_social": getattr(cli, "razon_social", ""),
                "rif": getattr(cli, "rif", ""),
                "telefono": getattr(cli, "telefono", ""),
            }
        else:
            rep["id_cliente"] = None
        return rep

    class Meta:
        model = Cotizacion
        exclude = ("referencia_externa", "documento_json")  # SEC-NEW-3: ocultar campos internos
        # H-API-1: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        # FE-HIGH-5: numero_cotizacion lo asigna el backend (no el cliente).
        read_only_fields = ("id_empresa", "id_cotizacion", "fecha_creacion", "numero_cotizacion")


class DetalleCotizacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleCotizacion
        fields = "__all__"


class NotaVentaSerializer(serializers.ModelSerializer):
    # Cliente anidado para mostrar nombre, razon_social, rif, telefono
    id_cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.all())

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        cli = getattr(instance, "id_cliente", None)
        if cli:
            rep["id_cliente"] = {
                "id_cliente": str(getattr(cli, "id_cliente", "")),
                "nombre": getattr(cli, "nombre", ""),
                "razon_social": getattr(cli, "razon_social", ""),
                "rif": getattr(cli, "rif", ""),
                "telefono": getattr(cli, "telefono", ""),
            }
        else:
            rep["id_cliente"] = None
        return rep

    class Meta:
        model = NotaVenta
        exclude = ("referencia_externa", "documento_json")  # SEC-NEW-3: ocultar campos internos
        # H-API-1: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_nota_venta", "fecha_creacion")

    def validate_numero_nota(self, value):
        if not value:
            raise serializers.ValidationError("El número de nota es obligatorio.")
        return value


class DetalleNotaVentaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleNotaVenta
        fields = "__all__"

    def validate_cantidad(self, value):
        if value <= 0:
            raise serializers.ValidationError("La cantidad debe ser mayor que cero.")
        return value

    def validate_precio_unitario(self, value):
        if value < 0:
            raise serializers.ValidationError("El precio unitario no puede ser negativo.")
        return value


class NotaCreditoFiscalSerializer(serializers.ModelSerializer):
    # Cliente anidado para mostrar nombre, razon_social, rif, telefono
    id_cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.all())

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        cli = getattr(instance, "id_cliente", None)
        if cli:
            rep["id_cliente"] = {
                "id_cliente": str(getattr(cli, "id_cliente", "")),
                "nombre": getattr(cli, "nombre", ""),
                "razon_social": getattr(cli, "razon_social", ""),
                "rif": getattr(cli, "rif", ""),
                "telefono": getattr(cli, "telefono", ""),
            }
        else:
            rep["id_cliente"] = None
        return rep

    class Meta:
        model = NotaCreditoFiscal
        exclude = ("referencia_externa", "documento_json")  # SEC-NEW-3: ocultar campos internos
        # H-API-1: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ("id_empresa", "id_nota_credito_fiscal", "fecha_creacion")


class DetalleNotaCreditoFiscalSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleNotaCreditoFiscal
        fields = "__all__"


class ListaPrecioSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListaPrecio
        fields = "__all__"
        # H-API-1: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ["id_lista", "fecha_creacion", "id_empresa"]


class DetallePrecioSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetallePrecio
        fields = "__all__"
        read_only_fields = ["id_detalle"]


# ── Comisiones de vendedores (1.G) ────────────────────────────────────────────


def _validar_porcentaje_comision(value):
    if value < 0 or value > 100:
        raise serializers.ValidationError("El porcentaje debe estar entre 0 y 100.")
    return value


class EsquemaComisionCategoriaSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source="categoria.nombre_categoria", read_only=True)

    class Meta:
        model = EsquemaComisionCategoria
        fields = "__all__"
        read_only_fields = ["id_esquema_comision_categoria"]

    def validate_porcentaje(self, value):
        return _validar_porcentaje_comision(value)

    def validate(self, data):
        # Coherencia de tenant entre los dos FKs: TenantFKScopeMixin ya acota
        # cada uno a empresas VISIBLES, pero un usuario con varias empresas
        # podría cruzar esquema de la empresa A con categoría de la B.
        esquema = data.get("esquema") or getattr(self.instance, "esquema", None)
        categoria = data.get("categoria") or getattr(self.instance, "categoria", None)
        if esquema is not None and categoria is not None and esquema.id_empresa_id != categoria.id_empresa_id:
            raise serializers.ValidationError(
                {"categoria": "La categoría debe pertenecer a la misma empresa que el esquema."}
            )
        return data


class EsquemaComisionSerializer(serializers.ModelSerializer):
    vendedor_username = serializers.CharField(source="vendedor.username", read_only=True)
    overrides_categoria = EsquemaComisionCategoriaSerializer(many=True, read_only=True)

    class Meta:
        model = EsquemaComision
        fields = "__all__"
        # H-API-1: id_empresa nunca lo fija el cliente; lo inyecta el ViewSet.
        read_only_fields = ["id_esquema_comision", "id_empresa", "fecha_creacion"]

    def validate_porcentaje_base(self, value):
        return _validar_porcentaje_comision(value)

    def validate(self, data):
        desde = data.get("vigente_desde", getattr(self.instance, "vigente_desde", None))
        hasta = data.get("vigente_hasta", getattr(self.instance, "vigente_hasta", None))
        if desde and hasta and desde > hasta:
            raise serializers.ValidationError(
                {"vigente_hasta": "La vigencia 'hasta' no puede ser anterior a 'desde'."}
            )
        return data


class LiquidarComisionesInputSerializer(serializers.Serializer):
    """
    Input de POST /comisiones/liquidar/ — vendedor + período devengado.
    La coherencia del rango (desde ≤ hasta) la valida el service
    ``liquidar_comisiones`` (única fuente de verdad; la vista mapea a 400).
    """

    vendedor = serializers.UUIDField()
    desde = serializers.DateField()
    hasta = serializers.DateField()


class ComisionVentaSerializer(serializers.ModelSerializer):
    """Solo lectura: las comisiones nacen del devengo y mutan vía /liquidar/."""

    vendedor_username = serializers.CharField(source="vendedor.username", read_only=True)
    numero_nota = serializers.CharField(source="nota_venta.numero_nota", read_only=True)

    class Meta:
        model = ComisionVenta
        fields = "__all__"
        read_only_fields = [f.name for f in ComisionVenta._meta.concrete_fields]
