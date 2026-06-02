"""
Views for the Core module.

El CRUD de ``Empresa``, ``Usuarios``, ``Sucursal``, ``Departamento``,
``Roles`` y ``Permisos`` lo manejan los ViewSets registrados en el router
(ver ``viewsets.py`` y ``urls.py``), que aplican aislamiento de tenant vía
``get_empresas_visible``.

Históricamente este módulo contenía además ``*DetailView`` (RetrieveUpdate
DestroyAPIView con ``.objects.all()`` SIN filtro de tenant) y vistas
``placeholder_*`` mock. Eran endpoints paralelos sombreados por el router
pero registrados — bombas de retardo de IDOR cross-tenant (auditoría
CRIT-1..3 / M-API-1). Se eliminaron; aquí solo quedan endpoints de función
que no encajan en un ViewSet.
"""
import logging

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import UsuarioRoles, Usuarios
from .serializers import UsuarioRolesSerializer, UsuariosSerializer
from .viewsets import get_empresas_visible

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
def health_view(request):
    """
    Healthcheck liviano para orquestadores (Docker HEALTHCHECK, Railway, k8s).

    No toca la base de datos para que un fallo de BD no tumbe el liveness;
    para readiness con BD existe ``?db=1``. NEW-INFRA-5.
    """
    payload = {"status": "ok"}
    if request.query_params.get("db") == "1":
        from django.db import connection

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            payload["db"] = "ok"
        except Exception:  # noqa: BLE001 — readiness: reportar, no propagar
            payload["db"] = "error"
            return Response(payload, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    """Devuelve el usuario autenticado."""
    user = request.user
    try:
        usuario = Usuarios.objects.get(id=user.id)
    except Usuarios.DoesNotExist:
        return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)
    serializer = UsuariosSerializer(usuario)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def usuario_roles_view(request):
    """
    Lista los roles asignados a usuarios visibles para el solicitante.

    H-SEC-7: restringe a usuarios de empresas visibles (``get_empresas_visible``)
    para no filtrar asignaciones de otros tenants.
    """
    empresas = get_empresas_visible(request.user)
    queryset = UsuarioRoles.objects.filter(id_usuario__empresas__in=empresas).distinct()
    id_usuario = request.GET.get("id_usuario")
    if id_usuario:
        queryset = queryset.filter(id_usuario__id=id_usuario)
    serializer = UsuarioRolesSerializer(queryset, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_kpis_view(request):
    """Dashboard KPIs endpoint."""
    # Mock data for now - replace with real calculations
    kpis = {
        "totalRevenue": 125000,
        "revenueChange": "+12.5%",
        "revenueChangeType": "positive",
        "openOrders": 45,
        "ordersChange": "+8%",
        "ordersChangeType": "positive",
        "inventoryValue": 89000,
        "inventoryChange": "-2.1%",
        "inventoryChangeType": "negative",
        "pendingApprovals": 12,
        "approvalsChange": "+3",
        "approvalsChangeType": "neutral",
    }
    return Response(kpis, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats_view(request):
    """Dashboard statistics endpoint."""
    # Mock data for now
    stats = {
        "sales_this_month": 45000,
        "sales_last_month": 38000,
        "new_customers": 15,
        "active_users": User.objects.filter(is_active=True).count(),
        "total_products": 250,
        "low_stock_items": 8,
    }
    return Response(stats, status=status.HTTP_200_OK)
