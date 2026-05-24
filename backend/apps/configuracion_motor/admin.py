from django.contrib import admin

from .models import CatalogoValor, ParametroSistema, TipoDocumento

admin.site.register(TipoDocumento)
admin.site.register(ParametroSistema)
admin.site.register(CatalogoValor)
