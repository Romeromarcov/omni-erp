"""URL configuration for Omni ERP project."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from apps.core.auth_views import (
    CustomTokenObtainPairView,
    login_view,
    logout_view,
    user_profile_view,
    update_profile_view,
    change_password_view,
    refresh_token_view,
    verify_token_view,
)

schema_view = get_schema_view(
    openapi.Info(
        title='Omni ERP API',
        default_version='v1',
        description='API del sistema ERP para el mercado venezolano',
    ),
    public=False,
    permission_classes=[permissions.IsAuthenticated],
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # API docs (solo en DEBUG)
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('api/redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),

    # Authentication
    path('api/auth/login/', login_view, name='login'),
    path('api/auth/logout/', logout_view, name='logout'),
    path('api/auth/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', refresh_token_view, name='token_refresh'),
    path('api/auth/token/verify/', verify_token_view, name='token_verify'),
    path('api/auth/profile/', user_profile_view, name='user_profile'),
    path('api/auth/profile/update/', update_profile_view, name='update_profile'),
    path('api/auth/change-password/', change_password_view, name='change_password'),

    # Modules
    path('api/core/', include('apps.core.urls')),
    path('api/configuracion/', include('apps.configuracion_motor.urls')),
    path('api/inventario/', include('apps.inventario.urls')),
    path('api/ventas/', include('apps.ventas.urls')),
    path('api/compras/', include('apps.compras.urls')),
    path('api/proveedores/', include('apps.proveedores.urls')),
    path('api/finanzas/', include('apps.finanzas.urls')),
    path('api/crm/', include('apps.crm.urls')),
    path('api/gastos/', include('apps.gastos.urls')),
    path('api/nomina/', include('apps.nomina.urls')),
    path('api/cuentas-por-pagar/', include('apps.cuentas_por_pagar.urls')),
    path('api/rrhh/', include('apps.rrhh.urls')),
    path('api/auditoria/', include('apps.auditoria.urls')),
    path('api/fiscal/', include('apps.fiscal.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
