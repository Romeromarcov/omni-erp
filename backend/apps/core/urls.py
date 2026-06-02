"""
URLs for the Core module.

Todo el CRUD de los recursos de core lo expone el router de ViewSets
(``viewsets.py``), que aplica aislamiento de tenant. Los endpoints de función
custom que deben ganar prioridad sobre el router se declaran ANTES del
``include(router.urls)``.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import viewsets as core_viewsets
from . import views
from .auth_views import change_password_view, dispositivo_accion_view

# Create router for ViewSets
router = DefaultRouter()
router.register(r"usuarios", core_viewsets.UsuariosViewSet)
router.register(r"empresas", core_viewsets.EmpresaViewSet)
router.register(r"sucursales", core_viewsets.SucursalViewSet)
router.register(r"departamentos", core_viewsets.DepartamentoViewSet)
router.register(r"dispositivos", core_viewsets.DispositivoViewSet)
router.register(r"roles", core_viewsets.RolesViewSet)
router.register(r"permisos", core_viewsets.PermisosViewSet)
router.register(r"contactos", core_viewsets.ContactoViewSet)
router.register(r"flujo-documentos", core_viewsets.ConfiguracionFlujoDocumentosViewSet)
router.register(r"notificaciones", core_viewsets.NotificacionViewSet)

urlpatterns = [
    # Custom endpoints que deben tener prioridad sobre el router
    path("usuarios/me/", views.me_view, name="usuarios_me"),
    path("usuarios/change_password/", change_password_view, name="usuarios_change_password"),
    path("dispositivos/accion/", dispositivo_accion_view, name="dispositivo_accion"),
    # Router URLs (CRUD con aislamiento de tenant)
    path("", include(router.urls)),
    # Custom function endpoints
    path("dashboard/kpis/", views.dashboard_kpis_view, name="dashboard_kpis"),
    path("dashboard/stats/", views.dashboard_stats_view, name="dashboard_stats"),
    path("usuario_roles/", views.usuario_roles_view, name="usuario_roles_list"),
]
