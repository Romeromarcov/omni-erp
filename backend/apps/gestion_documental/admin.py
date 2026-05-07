from django.contrib import admin
from .models import Carpeta, Documento, VinculoDocumento, PermisoDocumento

admin.site.register(Carpeta)
admin.site.register(Documento)
admin.site.register(VinculoDocumento)
admin.site.register(PermisoDocumento)
