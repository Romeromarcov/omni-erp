"""
Utilidades para la app core
"""
from .models import Dispositivo


def detectar_o_registrar_dispositivo(fingerprint, user_agent, ip_address, empresa, sucursal, usuario):
    """
    Detecta un dispositivo existente o registra uno nuevo.
    Retorna el dispositivo y si fue creado.
    """
    dispositivo, created = Dispositivo.obtener_o_crear(
        fingerprint=fingerprint,
        user_agent=user_agent,
        ip_address=ip_address,
        empresa=empresa,
        sucursal=sucursal,
        usuario=usuario
    )

    return dispositivo, created


def determinar_accion_dispositivo(dispositivo, usuario):
    """
    Determina qué acción tomar con un dispositivo después del login.

    Retorna un diccionario con:
    - 'accion': 'nada', 'preguntar_caja', 'abrir_sesion_automatico', 'abrir_sesion'
    - 'mensaje': mensaje descriptivo
    - 'datos': datos adicionales si es necesario
    """
    # Si ya tiene caja física, abrir sesión automáticamente
    if dispositivo.tiene_caja_fisica:
        from apps.finanzas.models import SesionCajaFisica
        
        # Verificar si ya hay una sesión activa
        sesion_activa = SesionCajaFisica.obtener_sesion_activa(dispositivo.caja_fisica)
        if sesion_activa:
            # Ya hay sesión activa, no hacer nada
            return {
                'accion': 'sesion_activa',
                'mensaje': f'Sesión ya activa en {dispositivo.caja_fisica.nombre}',
                'datos': {
                    'caja_fisica': dispositivo.caja_fisica,
                    'sesion': sesion_activa
                }
            }
        else:
            # No hay sesión activa, abrir automáticamente
            return {
                'accion': 'abrir_sesion_automatico',
                'mensaje': f'Dispositivo reconocido. Abriendo sesión automáticamente en {dispositivo.caja_fisica.nombre}',
                'datos': {
                    'caja_fisica': dispositivo.caja_fisica,
                    'dispositivo': dispositivo
                }
            }

    # Si no tiene caja y no se debe preguntar, no hacer nada
    if not dispositivo.preguntar_crear_caja:
        return {
            'accion': 'nada',
            'mensaje': 'Dispositivo registrado sin caja física asociada',
            'datos': {}
        }

    # Si tiene caja y se debe preguntar, pero el usuario no puede crear cajas
    if not dispositivo.puede_crear_caja_fisica:
        dispositivo.marcar_no_preguntar_caja()
        return {
            'accion': 'nada',
            'mensaje': 'Dispositivo registrado. No tienes permisos para crear cajas físicas',
            'datos': {}
        }

    # Preguntar si quiere crear caja física
    return {
        'accion': 'preguntar_caja',
        'mensaje': '¿Deseas crear una caja física para este dispositivo?',
        'datos': {
            'dispositivo': dispositivo,
            'empresa': dispositivo.empresa,
            'sucursal': dispositivo.sucursal,
            'user_agent': dispositivo.user_agent,
            'ip_address': dispositivo.ip_address
        }
    }