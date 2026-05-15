from django.contrib import admin

from .models import (
    ConfiguracionImpuesto,
    ConfiguracionRetencion,
    ContribucionEmpresaActiva,
    ContribucionParafiscal,
    EmpresaContribucionParafiscal,
    Impuesto,
    ImpuestoEmpresaActiva,
    Retencion,
    RetencionEmpresaActiva,
)

# Register your models here.
admin.site.register(ContribucionParafiscal)
admin.site.register(ImpuestoEmpresaActiva)
admin.site.register(RetencionEmpresaActiva)
admin.site.register(ContribucionEmpresaActiva)
admin.site.register(EmpresaContribucionParafiscal)
admin.site.register(ConfiguracionRetencion)
