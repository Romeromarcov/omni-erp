from django.contrib import admin

from .models import Carpeta, Documento, PermisoDocumento, VinculoDocumento

admin.site.register(Carpeta)
admin.site.register(Documento)
admin.site.register(VinculoDocumento)
admin.site.register(PermisoDocumento)
