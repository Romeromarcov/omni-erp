# Authentication views for Omni ERP
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate, get_user_model
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom token serializer to include user information"""
    
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        
        # Add custom claims
        token['username'] = user.username
        token['email'] = user.email
        token['first_name'] = user.first_name
        token['last_name'] = user.last_name
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser
        
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Add user information to response
        data.update({
            'user': {
                'id': self.user.id,
                'username': self.user.username,
                'email': self.user.email,
                'first_name': self.user.first_name,
                'last_name': self.user.last_name,
                'is_staff': self.user.is_staff,
                'is_superuser': self.user.is_superuser,
                'last_login': self.user.last_login,
                'date_joined': self.user.date_joined,
            }
        })
        
        return data

class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom token view with additional logging"""
    serializer_class = CustomTokenObtainPairSerializer
    
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        username = request.data.get('username', 'unknown')
        if response.status_code == 200:
            logger.info(f"Successful login for user: {username}")
        else:
            logger.warning(f"Failed login attempt for user: {username}")
        return response

@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """
    Login endpoint that returns JWT tokens and maneja detección de dispositivos
    """
    username = request.data.get('username')
    password = request.data.get('password')
    device_fingerprint = request.data.get('device_fingerprint')
    device_user_agent = request.data.get('device_user_agent', request.META.get('HTTP_USER_AGENT', ''))
    device_ip = request.data.get('device_ip', request.META.get('REMOTE_ADDR', ''))

    if not username or not password:
        logger.warning("Username or password missing in request data")
        return Response({
            'error': 'Username and password are required'
        }, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(username=username, password=password)

    if user is not None:
        if user.is_active:
            refresh = RefreshToken.for_user(user)
            user.last_login = timezone.now()
            user.save(update_fields=['last_login'])
            logger.info(f"Successful login for user: {username}")

            from .serializers import UsuariosSerializer
            user_data = UsuariosSerializer(user).data

            # Información de dispositivo
            dispositivo_info = None
            sesion_abierta = False

            if device_fingerprint:
                try:
                    # Obtener empresa y sucursal del usuario (primera empresa/sucursal asignada)
                    empresa = user.empresas.first()
                    sucursal = user.sucursales.first() or user.id_sucursal_predeterminada

                    if empresa and sucursal:
                        from .utils import detectar_o_registrar_dispositivo, determinar_accion_dispositivo

                        # Detectar o registrar dispositivo
                        dispositivo, dispositivo_creado = detectar_o_registrar_dispositivo(
                            fingerprint=device_fingerprint,
                            user_agent=device_user_agent,
                            ip_address=device_ip,
                            empresa=empresa,
                            sucursal=sucursal,
                            usuario=user
                        )

                        # Determinar acción a tomar
                        accion_info = determinar_accion_dispositivo(dispositivo, user)

                        # Serializar datos del dispositivo para evitar errores de JSON
                        from .serializers import DispositivoSerializer
                        dispositivo_serializado = DispositivoSerializer(dispositivo).data

                        dispositivo_info = {
                            'id_dispositivo': str(dispositivo.id_dispositivo),
                            'nombre_dispositivo': dispositivo.nombre_dispositivo,
                            'creado': dispositivo_creado,
                            'accion': accion_info['accion'],
                            'mensaje': accion_info['mensaje'],
                            'datos': {}
                        }

                        # Serializar datos adicionales según la acción
                        if accion_info['accion'] in ['abrir_sesion', 'abrir_sesion_automatico']:
                            from apps.finanzas.serializers import CajaFisicaSerializer
                            caja_fisica_serializada = CajaFisicaSerializer(accion_info['datos']['caja_fisica']).data
                            dispositivo_info['datos'] = {
                                'caja_fisica': caja_fisica_serializada,
                                'dispositivo': dispositivo_serializado
                            }
                        elif accion_info['accion'] == 'sesion_activa':
                            from apps.finanzas.serializers import CajaFisicaSerializer, SesionCajaFisicaSerializer
                            caja_fisica_serializada = CajaFisicaSerializer(accion_info['datos']['caja_fisica']).data
                            sesion_serializada = SesionCajaFisicaSerializer(accion_info['datos']['sesion']).data
                            dispositivo_info['datos'] = {
                                'caja_fisica': caja_fisica_serializada,
                                'sesion': sesion_serializada
                            }
                        elif accion_info['accion'] == 'preguntar_caja':
                            dispositivo_info['datos'] = {
                                'dispositivo': dispositivo_serializado,
                                'empresa': {
                                    'id_empresa': str(accion_info['datos']['empresa'].id_empresa),
                                    'nombre_comercial': accion_info['datos']['empresa'].nombre_comercial
                                },
                                'sucursal': {
                                    'id_sucursal': str(accion_info['datos']['sucursal'].id_sucursal),
                                    'nombre': accion_info['datos']['sucursal'].nombre
                                },
                                'user_agent': accion_info['datos']['user_agent'],
                                'ip_address': accion_info['datos']['ip_address']
                            }

                        # Si se debe abrir sesión automáticamente
                        if accion_info['accion'] == 'abrir_sesion_automatico':
                            try:
                                caja_fisica = accion_info['datos']['caja_fisica']
                                from apps.finanzas.models import SesionCajaFisica

                                sesion = SesionCajaFisica.abrir_sesion(
                                    caja_fisica=caja_fisica,
                                    usuario=user,
                                    ip_address=device_ip,
                                    user_agent=device_user_agent
                                )

                                dispositivo_info['sesion_abierta'] = {
                                    'id_sesion': str(sesion.id_sesion),
                                    'estado': sesion.estado,
                                    'fecha_apertura': sesion.fecha_apertura,
                                    'caja_fisica': {
                                        'id_caja_fisica': str(caja_fisica.id_caja_fisica),
                                        'nombre': caja_fisica.nombre
                                    }
                                }
                                sesion_abierta = True

                            except Exception as e:
                                logger.error(f"Error abriendo sesión automáticamente: {e}")
                                dispositivo_info['error_sesion'] = str(e)

                        # Si se debe abrir sesión (modal)
                        elif accion_info['accion'] == 'abrir_sesion':
                            try:
                                caja_fisica = accion_info['datos']['caja_fisica']
                                from apps.finanzas.models import SesionCajaFisica

                                sesion = SesionCajaFisica.abrir_sesion(
                                    caja_fisica=caja_fisica,
                                    usuario=user,
                                    ip_address=device_ip,
                                    user_agent=device_user_agent
                                )

                                dispositivo_info['sesion_abierta'] = {
                                    'id_sesion': str(sesion.id_sesion),
                                    'estado': sesion.estado,
                                    'fecha_apertura': sesion.fecha_apertura,
                                    'caja_fisica': {
                                        'id_caja_fisica': str(caja_fisica.id_caja_fisica),
                                        'nombre': caja_fisica.nombre
                                    }
                                }
                                sesion_abierta = True

                            except Exception as e:
                                logger.error(f"Error abriendo sesión automáticamente: {e}")
                                dispositivo_info['error_sesion'] = str(e)

                    else:
                        logger.warning(f"Usuario {username} no tiene empresa o sucursal asignada")

                except Exception as e:
                    logger.error(f"Error procesando dispositivo: {e}")
                    dispositivo_info = {
                        'error': f'Error procesando dispositivo: {str(e)}'
                    }

            response_data = {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': user_data
            }

            if dispositivo_info:
                response_data['dispositivo'] = dispositivo_info

            return Response(response_data, status=status.HTTP_200_OK)

        else:
            logger.warning(f"Login attempt for inactive user: {username}")
            return Response({
                'error': 'User account is disabled'
            }, status=status.HTTP_401_UNAUTHORIZED)
    else:
        logger.warning(f"Failed login attempt for user: {username}")
        return Response({
            'error': 'Invalid credentials'
        }, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    """
    Logout endpoint that blacklists the refresh token
    """
    try:
        refresh_token = request.data.get('refresh')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
            
        logger.info(f"User {request.user.username} logged out successfully")
        
        return Response({
            'message': 'Successfully logged out'
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Logout error for user {request.user.username}: {str(e)}")
        return Response({
            'error': 'Error during logout'
        }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile_view(request):
    """
    Get current user profile information
    """
    user = request.user
    
    from .serializers import UsuariosSerializer
    user_data = UsuariosSerializer(user).data
    return Response(user_data, status=status.HTTP_200_OK)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_profile_view(request):
    """
    Update current user profile information
    """
    user = request.user
    
    # Update allowed fields
    allowed_fields = ['first_name', 'last_name', 'email']
    updated_fields = []
    
    for field in allowed_fields:
        if field in request.data:
            setattr(user, field, request.data[field])
            updated_fields.append(field)
    
    if updated_fields:
        user.save(update_fields=updated_fields)
        logger.info(f"User {user.username} updated profile fields: {updated_fields}")
    
    return Response({
        'message': 'Profile updated successfully',
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'last_login': user.last_login,
            'date_joined': user.date_joined,
        }
    }, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password_view(request):
    """Change user password and invalidate all existing tokens."""
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError

    user = request.user
    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')

    if not old_password or not new_password:
        return Response({'error': 'Both old and new passwords are required'}, status=status.HTTP_400_BAD_REQUEST)

    if not user.check_password(old_password):
        return Response({'error': 'Current password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        validate_password(new_password, user)
    except DjangoValidationError as e:
        return Response({'error': list(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.save(update_fields=['password'])

    # Blacklist the current refresh token so existing sessions are invalidated
    refresh_token = request.data.get('refresh')
    if refresh_token:
        try:
            RefreshToken(refresh_token).blacklist()
        except Exception:
            pass

    logger.info(f"User {user.username} changed password successfully")
    return Response({'message': 'Password changed successfully'}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token_view(request):
    """Refresh JWT access token, rotating the refresh token if configured."""
    from django.conf import settings as django_settings
    from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

    refresh_token = request.data.get('refresh')
    if not refresh_token:
        return Response({'error': 'Refresh token is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        refresh = RefreshToken(refresh_token)
        data = {'access': str(refresh.access_token)}

        rotate = django_settings.SIMPLE_JWT.get('ROTATE_REFRESH_TOKENS', False)
        blacklist = django_settings.SIMPLE_JWT.get('BLACKLIST_AFTER_ROTATION', False)
        if rotate:
            if blacklist:
                refresh.blacklist()
            refresh.set_jti()
            refresh.set_exp()
            data['refresh'] = str(refresh)

        return Response(data, status=status.HTTP_200_OK)
    except (TokenError, InvalidToken) as e:
        logger.warning(f"Token refresh failed: {e}")
        return Response({'error': 'Invalid or expired refresh token'}, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def verify_token_view(request):
    """
    Verify if the current token is valid
    """
    return Response({
        'valid': True,
        'user': {
            'id': request.user.id,
            'username': request.user.username,
            'email': request.user.email,
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
        }
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dispositivo_accion_view(request):
    """
    Maneja acciones relacionadas con dispositivos (crear caja física, no preguntar más, etc.)
    """
    accion = request.data.get('accion')
    id_dispositivo = request.data.get('id_dispositivo')

    if not accion or not id_dispositivo:
        return Response({
            'error': 'Se requieren accion e id_dispositivo'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        from .models import Dispositivo
        dispositivo = Dispositivo.objects.get(
            id_dispositivo=id_dispositivo,
            creado_por=request.user
        )
    except Dispositivo.DoesNotExist:
        return Response({
            'error': 'Dispositivo no encontrado o no pertenece al usuario'
        }, status=status.HTTP_404_NOT_FOUND)

    if accion == 'crear_caja_fisica':
        # Crear caja física para el dispositivo
        nombre_caja = request.data.get('nombre_caja')
        tipo_caja = request.data.get('tipo_caja', 'VENTA')

        if not nombre_caja:
            return Response({
                'error': 'Se requiere nombre_caja para crear la caja física'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            from apps.finanzas.models import CajaFisica

            # Verificar permisos
            if not dispositivo.puede_crear_caja_fisica:
                return Response({
                    'error': 'No tienes permisos para crear cajas físicas'
                }, status=status.HTTP_403_FORBIDDEN)

            # Crear la caja física
            caja_fisica = CajaFisica.objects.create(
                nombre=nombre_caja,
                tipo_caja=tipo_caja,
                empresa=dispositivo.empresa,
                sucursal=dispositivo.sucursal,
                identificador_dispositivo=dispositivo.fingerprint,
                activa=True,
                nombre_dispositivo=dispositivo.nombre_dispositivo,
                tipo_dispositivo='PC',  # Default to PC
                requiere_sesion_activa=True
            )

            # Crear la asociación usuario-caja física
            from apps.finanzas.models import CajaFisicaUsuario
            CajaFisicaUsuario.objects.create(
                usuario=request.user,
                caja_fisica=caja_fisica,
                puede_abrir_sesion=True,
                puede_cerrar_sesion=True,
                es_predeterminada=True  # Hacerla predeterminada para este usuario
            )

            # Asociar al dispositivo
            dispositivo.caja_fisica = caja_fisica
            dispositivo.save()

            # Abrir sesión automáticamente
            from apps.finanzas.models import SesionCajaFisica
            sesion = SesionCajaFisica.abrir_sesion(
                caja_fisica=caja_fisica,
                usuario=request.user,
                ip_address=request.META.get('REMOTE_ADDR', ''),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )

            return Response({
                'success': True,
                'mensaje': f'Caja física "{nombre_caja}" creada y sesión abierta',
                'caja_fisica': {
                    'id_caja_fisica': str(caja_fisica.id_caja_fisica),
                    'nombre': caja_fisica.nombre,
                    'tipo_caja': caja_fisica.tipo_caja
                },
                'sesion': {
                    'id_sesion': str(sesion.id_sesion),
                    'estado': sesion.estado,
                    'fecha_apertura': sesion.fecha_apertura
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creando caja física: {e}")
            return Response({
                'error': f'Error creando caja física: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    elif accion == 'no_preguntar_caja':
        # Marcar que no se pregunte más por caja física
        dispositivo.marcar_no_preguntar_caja()
        dispositivo.save()

        return Response({
            'success': True,
            'mensaje': 'No se volverá a preguntar por caja física para este dispositivo'
        }, status=status.HTTP_200_OK)

    elif accion == 'abrir_sesion':
        # Abrir sesión en la caja física asociada
        if not dispositivo.tiene_caja_fisica:
            return Response({
                'error': 'El dispositivo no tiene caja física asociada'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            from apps.finanzas.models import SesionCajaFisica
            sesion = SesionCajaFisica.abrir_sesion(
                caja_fisica=dispositivo.caja_fisica,
                usuario=request.user,
                ip_address=request.META.get('REMOTE_ADDR', ''),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )

            return Response({
                'success': True,
                'mensaje': f'Sesión abierta en {dispositivo.caja_fisica.nombre}',
                'sesion': {
                    'id_sesion': str(sesion.id_sesion),
                    'estado': sesion.estado,
                    'fecha_apertura': sesion.fecha_apertura,
                    'caja_fisica': {
                        'id_caja_fisica': str(dispositivo.caja_fisica.id_caja_fisica),
                        'nombre': dispositivo.caja_fisica.nombre
                    }
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error abriendo sesión: {e}")
            return Response({
                'error': f'Error abriendo sesión: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    else:
        return Response({
            'error': f'Acción "{accion}" no reconocida'
        }, status=status.HTTP_400_BAD_REQUEST)