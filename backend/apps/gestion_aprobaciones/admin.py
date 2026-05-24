from django.contrib import admin

from .models import FlujoAprobacion, RegistroAprobacion, SolicitudAprobacion, TipoAprobacion

admin.site.register(TipoAprobacion)
admin.site.register(FlujoAprobacion)
admin.site.register(SolicitudAprobacion)
admin.site.register(RegistroAprobacion)
