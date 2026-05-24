from django.contrib import admin

from .models import ConfiguracionFiscalEmpresa, ConfiguracionImpuesto

admin.site.register(ConfiguracionFiscalEmpresa)
admin.site.register(ConfiguracionImpuesto)
