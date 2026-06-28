"""Registro de modelos en el admin de Django para CxC Lubrikca.

Los modelos se administran principalmente desde la UI (DRF + MUI); el admin se
ofrece como herramienta de soporte/diagnóstico.
"""

from django.contrib import admin

from .models import (
    ConciliacionLubrikca,
    ConfiguracionConciliacion,
    DescuentoBCVCompleto,
    DescuentoMarcaCategoria,
    Feriado,
    MetodoPago,
    PromocionPrimeraCompra,
    ReglaRecurrencia,
)


@admin.register(DescuentoMarcaCategoria)
class DescuentoMarcaCategoriaAdmin(admin.ModelAdmin):
    list_display = ("marca", "categoria", "tipo_descuento", "porcentaje", "vigencia_desde", "vigencia_hasta", "activo")


@admin.register(DescuentoBCVCompleto)
class DescuentoBCVCompletoAdmin(admin.ModelAdmin):
    list_display = ("porcentaje", "vigencia_desde", "vigencia_hasta", "activo")


@admin.register(PromocionPrimeraCompra)
class PromocionPrimeraCompraAdmin(admin.ModelAdmin):
    list_display = ("producto", "vigencia_desde", "vigencia_hasta", "activo")


@admin.register(ReglaRecurrencia)
class ReglaRecurrenciaAdmin(admin.ModelAdmin):
    list_display = ("condicion", "tipo_beneficio", "valor", "vigencia_desde", "vigencia_hasta", "activo")


@admin.register(Feriado)
class FeriadoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "descripcion", "tipo", "activo")


@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "moneda", "tipo_tasa", "es_contado", "activo")


@admin.register(ConfiguracionConciliacion)
class ConfiguracionConciliacionAdmin(admin.ModelAdmin):
    list_display = ("empresa", "tolerance_rounding", "tolerance_red", "created_at")


@admin.register(ConciliacionLubrikca)
class ConciliacionLubrikcaAdmin(admin.ModelAdmin):
    list_display = ("pedido", "resultado", "diferencia", "total_motor", "monto_facturado", "conciliado_en")
