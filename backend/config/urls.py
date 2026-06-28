"""URL configuration for Omni ERP project."""

from csp.constants import SELF
from csp.decorators import csp_update
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

from apps.core.auth_views import (
    CustomTokenObtainPairView,
    change_password_view,
    login_view,
    logout_view,
    refresh_token_view,
    update_profile_view,
    user_profile_view,
    verify_token_view,
)

# Info a nivel de módulo para que `generate_swagger` (DEFAULT_INFO) y el contract
# testing (schemathesis) puedan resolver el esquema OpenAPI.
api_info = openapi.Info(
    title="Omni ERP API",
    default_version="v1",
    description="API del sistema ERP para el mercado venezolano",
)

schema_view = get_schema_view(
    api_info,
    public=False,
    permission_classes=[permissions.IsAuthenticated],
)

from apps.core.views import health_view

# P2-5: relajación CSP MÍNIMA y POR VISTA para la UI de docs (drf-yasg), que
# solo existe con DEBUG (SEC-05). La política global queda estricta ('self');
# aquí se suma únicamente lo que swagger-ui/redoc necesitan en runtime:
#   * style-src 'unsafe-inline' — ambos inyectan estilos vía JS (CSS-in-JS de
#     React/styled-components) y no aceptan nonce del servidor.
#   * img-src data: — swagger-ui.css embebe iconos como data:image.
#   * worker-src blob: — redoc lanza su web worker de búsqueda desde un blob.
# Definido a nivel de módulo (no dentro del `if settings.DEBUG`) para poder
# testearlo de forma determinista sin reimportar el URLconf.
docs_csp_update = csp_update(
    {
        "style-src": ["'unsafe-inline'"],
        "img-src": ["data:"],
        "worker-src": [SELF, "blob:"],
    }
)

urlpatterns = [
    path("admin/", admin.site.urls),
    # Healthcheck (sin auth — orquestadores). NEW-INFRA-5.
    path("api/health/", health_view, name="health"),
    # Authentication
    path("api/auth/login/", login_view, name="login"),
    path("api/auth/logout/", logout_view, name="logout"),
    path("api/auth/token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/token/refresh/", refresh_token_view, name="token_refresh"),
    path("api/auth/token/verify/", verify_token_view, name="token_verify"),
    path("api/auth/profile/", user_profile_view, name="user_profile"),
    path("api/auth/profile/update/", update_profile_view, name="update_profile"),
    path("api/auth/change-password/", change_password_view, name="change_password"),
    # Modules
    path("api/core/", include("apps.core.urls")),
    path("api/configuracion/", include("apps.configuracion_motor.urls")),
    path("api/inventario/", include("apps.inventario.urls")),
    path("api/ventas/", include("apps.ventas.urls")),
    path("api/compras/", include("apps.compras.urls")),
    path("api/proveedores/", include("apps.proveedores.urls")),
    path("api/finanzas/", include("apps.finanzas.urls")),
    path("api/crm/", include("apps.crm.urls")),
    path("api/gastos/", include("apps.gastos.urls")),
    path("api/nomina/", include("apps.nomina.urls")),
    path("api/cuentas-por-pagar/", include("apps.cuentas_por_pagar.urls")),
    path("api/rrhh/", include("apps.rrhh.urls")),
    path("api/auditoria/", include("apps.auditoria.urls")),
    path("api/fiscal/", include("apps.fiscal.urls")),
    path("api/cxc/", include("apps.cuentas_por_cobrar.urls")),
    path("api/gestion-documental/", include("apps.gestion_documental.urls")),
    path("api/contabilidad/", include("apps.contabilidad.urls")),
    path("api/agentes/", include("apps.agentes.urls")),
    path("api/notificaciones/", include("apps.notificaciones.urls")),
    path("api/saas/", include("apps.saas.urls")),
    # Fase C — apps registradas
    path("api/almacenes/", include("apps.almacenes.urls")),
    path("api/despacho/", include("apps.despacho.urls")),
    path("api/tesoreria/", include("apps.tesoreria.urls")),
    path("api/banca-electronica/", include("apps.banca_electronica.urls")),
    path("api/costos/", include("apps.costos.urls")),
    path("api/manufactura/", include("apps.manufactura.urls")),
    path("api/control-asistencia/", include("apps.control_asistencia.urls")),
    path("api/servicio-cliente/", include("apps.servicio_cliente.urls")),
    path("api/gestion-aprobaciones/", include("apps.gestion_aprobaciones.urls")),
    path("api/integracion-b2b/", include("apps.integracion_b2b.urls")),
    path("api/integration-hub/", include("apps.integration_hub.urls")),
    path("api/migracion-datos/", include("apps.migracion_datos.urls")),
    path("api/personalizacion/", include("apps.personalizacion.urls")),
    path("api/cobranza/", include("apps.cxc.api.router")),
    path("api/cxc-lubrikca/", include("apps.cxc_lubrikca.api.router")),
    path("api/sync/", include("apps.sync.urls")),
]

if settings.DEBUG:
    # API docs — solo disponibles en modo desarrollo (SEC-05)
    urlpatterns += [
        path("api/docs/", docs_csp_update(schema_view.with_ui("swagger", cache_timeout=0)), name="schema-swagger-ui"),
        path("api/redoc/", docs_csp_update(schema_view.with_ui("redoc", cache_timeout=0)), name="schema-redoc"),
    ]
    # En modo S3 no hay MEDIA_ROOT local — solo servir static y media local si aplica
    if not getattr(settings, "USE_S3", False):
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
