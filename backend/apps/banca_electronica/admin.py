from django.contrib import admin

from .models import DetalleLotePagoBancario, LotePagoBancario


@admin.register(LotePagoBancario)
class LotePagoBancarioAdmin(admin.ModelAdmin):
    list_display = [
        "referencia_lote",
        "id_empresa",
        "tipo_lote",
        "formato_banco",
        "fecha_valor",
        "total_registros",
        "monto_total",
        "estado",
        "activo",
    ]
    list_filter = ["tipo_lote", "formato_banco", "estado", "activo", "id_empresa"]
    search_fields = ["referencia_lote", "nombre_archivo", "sha256_archivo"]
    readonly_fields = ["id_lote_pago", "sha256_archivo", "fecha_creacion", "fecha_actualizacion"]


@admin.register(DetalleLotePagoBancario)
class DetalleLotePagoBancarioAdmin(admin.ModelAdmin):
    list_display = [
        "id_lote_pago",
        "beneficiario_nombre",
        "beneficiario_identificacion",
        "cuenta_destino",
        "monto",
        "referencia_linea",
    ]
    search_fields = ["beneficiario_nombre", "beneficiario_identificacion", "cuenta_destino", "referencia_linea"]
    readonly_fields = ["id_detalle"]
