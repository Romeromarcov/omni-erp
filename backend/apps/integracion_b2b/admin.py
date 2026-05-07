from django.contrib import admin
from .models import ConfiguracionIntegracion, LogIntegracion, MapeoCampo

admin.site.register(ConfiguracionIntegracion)
admin.site.register(LogIntegracion)
admin.site.register(MapeoCampo)
