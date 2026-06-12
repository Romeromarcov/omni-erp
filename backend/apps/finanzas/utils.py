"""
Utilidades para el manejo de cajas y sesiones en el sistema ERP venezolano.
"""

from django.db import models


def asignar_permisos_caja_fisica(usuario, caja_fisica, puede_abrir=True, puede_cerrar=True, es_predeterminada=False):
    """
    Asigna permisos de caja física a un usuario.

    Args:
        usuario: Instancia del modelo Usuarios
        caja_fisica: Instancia del modelo CajaFisica
        puede_abrir: Si el usuario puede abrir sesiones
        puede_cerrar: Si el usuario puede cerrar sesiones
        es_predeterminada: Si esta es la caja predeterminada del usuario
    """
    from .models import CajaFisicaUsuario

    asignacion, created = CajaFisicaUsuario.objects.get_or_create(
        usuario=usuario,
        caja_fisica=caja_fisica,
        defaults={
            "puede_abrir_sesion": puede_abrir,
            "puede_cerrar_sesion": puede_cerrar,
            "es_predeterminada": es_predeterminada,
        },
    )

    if not created:
        # Actualizar permisos existentes
        asignacion.puede_abrir_sesion = puede_abrir
        asignacion.puede_cerrar_sesion = puede_cerrar
        asignacion.es_predeterminada = es_predeterminada
        asignacion.save()

    return asignacion, created


def obtener_sesion_activa_usuario(usuario):
    """
    Obtiene la sesión activa del usuario actual.
    Retorna None si no hay sesión activa.
    """
    from .models import SesionCajaFisica

    return (
        SesionCajaFisica.objects.filter(usuario=usuario, estado="ABIERTA")
        .select_related("caja_fisica")
        .first()
    )


def validar_acceso_caja_usuario(usuario, caja):
    """
    Valida si un usuario tiene acceso a una caja específica.
    Considera asignaciones directas y sesiones activas.
    """
    from .models import CajaUsuario

    # Verificar asignación directa
    asignacion_directa = CajaUsuario.objects.filter(usuario=usuario, caja=caja, caja__activa=True).exists()

    if asignacion_directa:
        return True

    # Verificar si tiene sesión activa en esa caja
    sesion_activa = obtener_sesion_activa_usuario(usuario)
    if sesion_activa and sesion_activa.caja_fisica == caja:
        return True

    return False


def obtener_caja_activa_sesion(usuario):
    """
    Obtiene la caja física activa de la sesión del usuario.
    Útil para determinar dónde registrar transacciones.
    """
    sesion_activa = obtener_sesion_activa_usuario(usuario)
    if sesion_activa:
        return sesion_activa.caja_fisica
    return None


def crear_configuracion_inicial_venezolana(empresa):
    """
    Crea la configuración inicial de cajas virtuales para un contexto venezolano.
    """
    from .models import MetodoPago, Moneda, PlantillaMaestroCajasVirtuales

    # Obtener monedas y métodos de pago disponibles
    try:
        ves = Moneda.objects.get(codigo_iso="VES", empresa=empresa)
        usd = Moneda.objects.get(codigo_iso="USD", empresa=empresa)
    except Moneda.DoesNotExist:
        return {"error": "Monedas VES y USD no encontradas"}

    try:
        efectivo = MetodoPago.objects.get(nombre_metodo="EFECTIVO", empresa=empresa)
        tarjeta = MetodoPago.objects.get(nombre_metodo="TARJETA", empresa=empresa)
        credito = MetodoPago.objects.get(nombre_metodo="CREDITO", empresa=empresa)
    except MetodoPago.DoesNotExist:
        return {"error": "Métodos de pago básicos no encontrados"}

    # Crear plantilla maestra para cajas físicas
    plantilla_fisica, created_fisica = PlantillaMaestroCajasVirtuales.objects.get_or_create(
        empresa=empresa,
        nombre="Plantilla Cajas Físicas Venezuela",
        defaults={
            "descripcion": "Configuración automática para todas las cajas físicas venezolanas",
            "aplicar_a_todas_cajas_fisicas": True,
            "aplicar_a_empleados_con_rol": None,
            "activa": True,
        },
    )

    if created_fisica:
        plantilla_fisica.monedas_base.set([ves, usd])
        plantilla_fisica.metodos_pago_base.set([efectivo, tarjeta, credito])
        plantilla_fisica.save()

    # Crear plantilla para vendedores móviles
    plantilla_movil, created_movil = PlantillaMaestroCajasVirtuales.objects.get_or_create(
        empresa=empresa,
        nombre="Plantilla Vendedores Móviles",
        defaults={
            "descripcion": "Configuración para vendedores que usan la app móvil",
            "aplicar_a_todas_cajas_fisicas": False,
            "aplicar_a_empleados_con_rol": "vendedor",  # Ajustar según el rol real
            "activa": True,
        },
    )

    if created_movil:
        plantilla_movil.monedas_base.set([ves, usd])
        plantilla_movil.metodos_pago_base.set([efectivo, tarjeta])
        plantilla_movil.save()

    return {
        "plantilla_fisica": plantilla_fisica,
        "plantilla_movil": plantilla_movil,
        "mensaje": "Configuración inicial creada exitosamente",
    }
