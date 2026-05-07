"""
URLs for the Core module
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import EmpresaDetailView, SucursalDetailView, DepartamentoDetailView, UsuarioDetailView
from .auth_views import change_password_view, dispositivo_accion_view

# Create router for ViewSets
router = DefaultRouter()


# Registrar ViewSets reales
from . import viewsets as core_viewsets
router.register(r'usuarios', core_viewsets.UsuariosViewSet)
router.register(r'empresas', core_viewsets.EmpresaViewSet)
router.register(r'sucursales', core_viewsets.SucursalViewSet)
router.register(r'departamentos', core_viewsets.DepartamentoViewSet)
router.register(r'dispositivos', core_viewsets.DispositivoViewSet)

urlpatterns = [
    # Custom endpoints que deben tener prioridad sobre el router
    path('usuarios/me/', views.me_view, name='usuarios_me'),
    path('usuarios/change_password/', change_password_view, name='usuarios_change_password'),
    path('dispositivos/accion/', dispositivo_accion_view, name='dispositivo_accion'),

    # Include router URLs
    path('', include(router.urls)),

    # Custom endpoints
    path('dashboard/kpis/', views.dashboard_kpis_view, name='dashboard_kpis'),
    path('dashboard/stats/', views.dashboard_stats_view, name='dashboard_stats'),

    # Placeholder endpoints for testing
    path('usuarios/', views.placeholder_usuarios_view, name='usuarios_list'),
    path('sucursales/', views.placeholder_sucursales_view, name='sucursales_list'),
    path('departamentos/', views.placeholder_departamentos_view, name='departamentos_list'),
    path('departamentos/<uuid:id_departamento>/', DepartamentoDetailView.as_view(), name='departamento_detail'),
    path('roles/', views.RoleListCreateView.as_view(), name='roles_list'),
    path('roles/<uuid:id_rol>/', views.RoleRetrieveUpdateDestroyView.as_view(), name='role_detail'),
    path('permisos/', views.placeholder_permisos_view, name='permisos_list'),
    path('monedas/', views.placeholder_monedas_view, name='monedas_list'),
    path('empresas/<uuid:id_empresa>/', EmpresaDetailView.as_view(), name='empresa_detail'),
    path('sucursales/<uuid:id_sucursal>/', SucursalDetailView.as_view(), name='sucursal_detail'),
    path('usuarios/<uuid:id>/', UsuarioDetailView.as_view(), name='usuario_detail'),
    path('usuario_roles/', views.usuario_roles_view, name='usuario_roles_list'),
]