from django.contrib import admin

from .models import Despacho, DetalleDespacho


class DetalleDespachoInline(admin.TabularInline):
    model = DetalleDespacho
    extra = 0
    raw_id_fields = ["id_producto", "id_unidad_medida"]


@admin.register(Despacho)
class DespachoAdmin(admin.ModelAdmin):
    list_display = [
        "numero_despacho",
        "id_empresa",
        "estado_despacho",
        "fecha_despacho",
        "id_transportista",
    ]
    list_filter = ["estado_despacho", "fecha_despacho"]
    search_fields = ["numero_despacho", "direccion_destino"]
    raw_id_fields = ["id_empresa", "id_nota_venta", "id_pedido", "id_almacen_origen", "id_transportista"]
    readonly_fields = ["fecha_en_ruta", "fecha_entrega_real", "fecha_devolucion", "fecha_cancelacion"]
    inlines = [DetalleDespachoInline]


@admin.register(DetalleDespacho)
class DetalleDespachoAdmin(admin.ModelAdmin):
    list_display = ["id_despacho", "id_producto", "cantidad_despachada", "id_unidad_medida"]
    search_fields = ["id_despacho__numero_despacho", "id_producto__nombre_producto"]
    raw_id_fields = ["id_despacho", "id_producto", "id_unidad_medida"]
