from django.contrib import admin
from .models import (
    Impuesto, ConfiguracionImpuesto, Retencion, ContribucionParafiscal,
    ImpuestoEmpresaActiva, RetencionEmpresaActiva, ContribucionEmpresaActiva,
    EmpresaContribucionParafiscal, ConfiguracionRetencion
)

# Register your models here.
admin.site.register(ContribucionParafiscal)
admin.site.register(ImpuestoEmpresaActiva)
admin.site.register(RetencionEmpresaActiva)
admin.site.register(ContribucionEmpresaActiva)
admin.site.register(EmpresaContribucionParafiscal)
admin.site.register(ConfiguracionRetencion)
