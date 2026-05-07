from django.contrib import admin
from .models import TipoDocumento, ParametroSistema, CatalogoValor

admin.site.register(TipoDocumento)
admin.site.register(ParametroSistema)
admin.site.register(CatalogoValor)
