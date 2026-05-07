from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from .models import Usuarios
from .serializers import UsuariosSerializer
# Endpoint para obtener el usuario autenticado
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_view(request):
    user = request.user
    try:
        usuario = Usuarios.objects.get(id=user.id)
    except Usuarios.DoesNotExist:
        return Response({'detail': 'Usuario no encontrado.'}, status=404)
    serializer = UsuariosSerializer(usuario)
    return Response(serializer.data)
from .models import UsuarioRoles
from .serializers import UsuarioRolesSerializer

# Endpoint para consultar roles asignados a un usuario
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def usuario_roles_view(request):
    id_usuario = request.GET.get('id_usuario')
    queryset = UsuarioRoles.objects.all()
    if id_usuario:
        queryset = queryset.filter(id_usuario__id=id_usuario)
    serializer = UsuarioRolesSerializer(queryset, many=True)
    return Response(serializer.data)
from rest_framework.generics import RetrieveUpdateDestroyAPIView
from .models import Usuarios
from .serializers import UsuariosSerializer

class UsuarioDetailView(RetrieveUpdateDestroyAPIView):
    def get(self, request, *args, **kwargs):
        try:
            usuario = self.get_object()
        except Exception:
            return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(usuario)
        return Response(serializer.data, status=status.HTTP_200_OK)
    queryset = Usuarios.objects.all()
    serializer_class = UsuariosSerializer
    lookup_field = 'id'

    def put(self, request, *args, **kwargs):
        try:
            usuario = self.get_object()
        except Exception:
            return Response({"detail": "Usuario no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(usuario, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
"""
Views for the Core module
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.contrib.auth.models import User
import logging
from rest_framework.generics import RetrieveAPIView
from .models import Empresa
from .serializers import EmpresaSerializer

class EmpresaDetailView(RetrieveAPIView):
    queryset = Empresa.objects.all()
    serializer_class = EmpresaSerializer
    lookup_field = 'id_empresa'

    def put(self, request, *args, **kwargs):
        empresa = self.get_object()
        serializer = self.get_serializer(empresa, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_kpis_view(request):
    """
    Dashboard KPIs endpoint
    """
    # Mock data for now - replace with real calculations
    kpis = {
        'totalRevenue': 125000,
        'revenueChange': '+12.5%',
        'revenueChangeType': 'positive',
        'openOrders': 45,
        'ordersChange': '+8%',
        'ordersChangeType': 'positive',
        'inventoryValue': 89000,
        'inventoryChange': '-2.1%',
        'inventoryChangeType': 'negative',
        'pendingApprovals': 12,
        'approvalsChange': '+3',
        'approvalsChangeType': 'neutral'
    }
    
    return Response(kpis, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_stats_view(request):
    """
    Dashboard statistics endpoint
    """
    # Mock data for now
    stats = {
        'sales_this_month': 45000,
        'sales_last_month': 38000,
        'new_customers': 15,
        'active_users': User.objects.filter(is_active=True).count(),
        'total_products': 250,
        'low_stock_items': 8
    }
    
    return Response(stats, status=status.HTTP_200_OK)

# Placeholder views for testing - replace with proper ViewSets later

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def placeholder_usuarios_view(request):
    """Placeholder for usuarios endpoint"""
    from .models import Usuarios, Empresa
    from .serializers import UsuariosSerializer
    if request.method == 'GET':
        id_empresa = request.GET.get('id_empresa')
        queryset = Usuarios.objects.all()
        if id_empresa:
            queryset = queryset.filter(empresas__id_empresa=id_empresa)
        serializer = UsuariosSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    elif request.method == 'POST':
        serializer = UsuariosSerializer(data=request.data)
        if serializer.is_valid():
            usuario = serializer.save()
            # Si se pasa id_empresa, asociar el usuario a la empresa
            id_empresa = request.data.get('id_empresa')
            if id_empresa:
                empresa = Empresa.objects.get(id_empresa=id_empresa)
                usuario.empresas.add(empresa)
            return Response(UsuariosSerializer(usuario).data, status=status.HTTP_201_CREATED)
        # Log the serializer errors for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"User creation failed: {serializer.errors}")
        return Response({'detail': 'Validation error', 'errors': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def placeholder_empresas_view(request):
    """Endpoint real para empresas: lista y creación"""
    from .models import Empresa
    from .serializers import EmpresaSerializer
    if request.method == 'GET':
        queryset = Empresa.objects.all()
        serializer = EmpresaSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    elif request.method == 'POST':
        serializer = EmpresaSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
from rest_framework.generics import RetrieveUpdateDestroyAPIView
from .models import Sucursal
from .serializers import SucursalSerializer

class SucursalDetailView(RetrieveUpdateDestroyAPIView):
    queryset = Sucursal.objects.all()
    serializer_class = SucursalSerializer
    lookup_field = 'id_sucursal'

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def placeholder_sucursales_view(request):
    """Placeholder for sucursales endpoint"""
    if request.method == 'GET':
        from .models import Sucursal
        from .serializers import SucursalSerializer
        id_empresa = request.GET.get('id_empresa')
        queryset = Sucursal.objects.all()
        if id_empresa:
            queryset = queryset.filter(id_empresa=id_empresa)
        serializer = SucursalSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        from .models import Sucursal
        from .serializers import SucursalSerializer
        serializer = SucursalSerializer(data=request.data)
        if serializer.is_valid():
            sucursal = serializer.save()
            return Response(SucursalSerializer(sucursal).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def placeholder_departamentos_view(request):
    """Endpoint real para departamentos: lista y creación"""
    from .models import Departamento
    from .serializers import DepartamentoSerializer
    if request.method == 'GET':
        id_empresa = request.GET.get('id_empresa')
        queryset = Departamento.objects.all()
        if id_empresa:
            queryset = queryset.filter(id_empresa=id_empresa)
        serializer = DepartamentoSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    elif request.method == 'POST':
        serializer = DepartamentoSerializer(data=request.data)
        if serializer.is_valid():
            departamento = serializer.save()
            return Response(DepartamentoSerializer(departamento).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ENDPOINTS REALES PARA ROLES
from rest_framework import generics
from .models import Roles
from .serializers import RolesSerializer

class RoleListCreateView(generics.ListCreateAPIView):
    queryset = Roles.objects.all()
    serializer_class = RolesSerializer
    permission_classes = [IsAuthenticated]

class RoleRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Roles.objects.all()
    serializer_class = RolesSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id_rol'

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def placeholder_permisos_view(request):
    """Placeholder for permisos endpoint"""
    if request.method == 'GET':
        permisos = [
            {
                'id': 1,
                'nombre': 'usuarios.crear',
                'descripcion': 'Crear usuarios',
                'modulo': 'core',
                'accion': 'crear',
                'es_activo': True
            },
            {
                'id': 2,
                'nombre': 'usuarios.leer',
                'descripcion': 'Ver usuarios',
                'modulo': 'core',
                'accion': 'leer',
                'es_activo': True
            }
        ]
        return Response(permisos, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        return Response({
            'id': 3,
            'message': 'Permiso creado exitosamente (mock)'
        }, status=status.HTTP_201_CREATED)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def placeholder_monedas_view(request):
    """Placeholder for monedas endpoint"""
    if request.method == 'GET':
        monedas = [
            {
                'id': 1,
                'nombre': 'Dólar Estadounidense',
                'codigo_iso': 'USD',
                'simbolo': '$',
                'es_activa': True
            },
            {
                'id': 2,
                'nombre': 'Euro',
                'codigo_iso': 'EUR',
                'simbolo': '€',
                'es_activa': True
            },
            {
                'id': 3,
                'nombre': 'Peso Mexicano',
                'codigo_iso': 'MXN',
                'simbolo': '$',
                'es_activa': True
            }
        ]
        return Response(monedas, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        return Response({
            'id': 4,
            'message': 'Moneda creada exitosamente (mock)'
        }, status=status.HTTP_201_CREATED)
from rest_framework.generics import RetrieveUpdateDestroyAPIView
from .models import Departamento
from .serializers import DepartamentoSerializer

class DepartamentoDetailView(RetrieveUpdateDestroyAPIView):
    queryset = Departamento.objects.all()
    serializer_class = DepartamentoSerializer
    lookup_field = 'id_departamento'