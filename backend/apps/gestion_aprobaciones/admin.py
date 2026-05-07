from django.contrib import admin
from .models import TipoAprobacion, FlujoAprobacion, SolicitudAprobacion, RegistroAprobacion

admin.site.register(TipoAprobacion)
admin.site.register(FlujoAprobacion)
admin.site.register(SolicitudAprobacion)
admin.site.register(RegistroAprobacion)
