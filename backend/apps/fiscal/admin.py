from django.contrib import admin

from .models import ConfiguracionFiscalEmpresa, ConfiguracionImpuesto, PagoContribucionParafiscal

admin.site.register(ConfiguracionFiscalEmpresa)
admin.site.register(ConfiguracionImpuesto)


@admin.register(PagoContribucionParafiscal)
class PagoContribucionParafiscalAdmin(admin.ModelAdmin):
    list_display = ("contribucion", "periodo_año", "periodo_mes", "monto", "estado", "id_empresa")
    list_filter = ("estado", "periodo_año")
    search_fields = ("referencia", "contribucion__codigo", "contribucion__nombre")
