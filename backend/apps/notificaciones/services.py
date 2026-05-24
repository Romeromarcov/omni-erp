"""
Servicio central de notificaciones.

emitir_notificacion() es el punto de entrada único para que los módulos
de negocio generen notificaciones sin conocer los detalles de entrega.

Las notificaciones in-app se persisten en core.Notificacion (ya existente).
Las notificaciones email se despachan vía Celery task.
"""

import logging

from django.template import Context, Template

logger = logging.getLogger("apps.notificaciones")

# Plantillas por defecto por evento (codigo_evento → codigo_plantilla EMAIL)
_PLANTILLA_EMAIL_POR_EVENTO = {
    "PEDIDO_CONFIRMADO": "PEDIDO_CONFIRMADO_EMAIL",
    "PAGO_RECIBIDO": "PAGO_RECIBIDO_EMAIL",
    "STOCK_BAJO": "STOCK_BAJO_EMAIL",
    "FACTURA_VENCIDA": "FACTURA_VENCIDA_EMAIL",
}

# Tipo de notificación in-app por evento (mapeo a TIPO_CHOICES de core.Notificacion)
_TIPO_POR_EVENTO = {
    "PEDIDO_CONFIRMADO": "EXITO",
    "PAGO_RECIBIDO": "EXITO",
    "STOCK_BAJO": "ALERTA",
    "FACTURA_VENCIDA": "ALERTA",
}

# Títulos por defecto para notificaciones in-app
_TITULO_POR_EVENTO = {
    "PEDIDO_CONFIRMADO": "Pedido confirmado",
    "PAGO_RECIBIDO": "Pago registrado",
    "STOCK_BAJO": "Alerta de stock bajo",
    "FACTURA_VENCIDA": "Factura por vencer",
}

# Templates de mensaje in-app por evento (Django template syntax)
_MENSAJE_TEMPLATES = {
    "PEDIDO_CONFIRMADO": (
        "El pedido #{{ numero_pedido }} del cliente {{ nombre_cliente }} "
        "ha sido confirmado exitosamente."
    ),
    "PAGO_RECIBIDO": (
        "Se registró un pago de {{ monto }} {{ moneda }} "
        "para la factura #{{ numero_factura }}."
    ),
    "STOCK_BAJO": (
        "El producto {{ nombre_producto }} tiene stock bajo: "
        "{{ cantidad_actual }} unidades (mínimo: {{ cantidad_minima }})."
    ),
    "FACTURA_VENCIDA": (
        "La factura #{{ numero_factura }} de {{ nombre_cliente }} "
        "venció el {{ fecha_vencimiento }}."
    ),
}


def _render(template_str: str, contexto: dict) -> str:
    try:
        return Template(template_str).render(Context(contexto))
    except Exception:  # noqa: BLE001
        return template_str


def emitir_notificacion(
    codigo_evento: str,
    empresa,
    usuario,
    contexto: dict,
    *,
    url_accion: str = "",
):
    """
    Emite una notificación in-app y encola email si hay plantilla activa.

    Args:
        codigo_evento: Código del evento (ej: "PEDIDO_CONFIRMADO").
        empresa:       Instancia core.Empresa.
        usuario:       Instancia core.Usuarios (destinatario in-app).
        contexto:      Dict con variables para personalizar el mensaje.
        url_accion:    URL relativa para el botón de acción.

    Returns:
        Instancia core.Notificacion creada, o None si hubo error.
    """
    from apps.core.models import crear_notificacion

    titulo = _titulo_para_evento(codigo_evento, contexto)
    mensaje = _render(_MENSAJE_TEMPLATES.get(codigo_evento, "{{ descripcion }}"), contexto)
    tipo = _TIPO_POR_EVENTO.get(codigo_evento, "INFO")

    try:
        notificacion = crear_notificacion(
            empresa=empresa,
            titulo=titulo,
            mensaje=mensaje,
            tipo=tipo,
            usuario=usuario,
            url_accion=url_accion,
            metadata={"codigo_evento": codigo_evento, **contexto},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Error creando notificación in-app [%s]: %s", codigo_evento, exc)
        return None

    # Encolar email si hay plantilla activa y el usuario tiene email
    _encolar_email(codigo_evento, usuario, contexto)

    return notificacion


def _encolar_email(codigo_evento: str, usuario, contexto: dict) -> None:
    from apps.notificaciones.models import CanalNotificacion, LogNotificacion, PlantillaNotificacion

    codigo_plantilla = _PLANTILLA_EMAIL_POR_EVENTO.get(codigo_evento)
    if not codigo_plantilla:
        return

    email = getattr(usuario, "email", None)
    if not email:
        return

    try:
        plantilla = PlantillaNotificacion.objects.filter(
            codigo_plantilla=codigo_plantilla,
            canal=CanalNotificacion.EMAIL,
            activo=True,
        ).first()
        if not plantilla:
            return

        log = LogNotificacion.objects.create(
            id_plantilla=plantilla,
            destinatario=email,
            canal=CanalNotificacion.EMAIL,
            estado="PENDIENTE",
        )
        from apps.notificaciones.tasks import enviar_notificacion_email
        enviar_notificacion_email.delay(
            str(plantilla.id_plantilla),
            email,
            contexto,
            str(log.id_log),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error encolando email para evento %s: %s", codigo_evento, exc)


def _titulo_para_evento(codigo_evento: str, contexto: dict) -> str:
    base = _TITULO_POR_EVENTO.get(codigo_evento, codigo_evento.replace("_", " ").title())
    numero = contexto.get("numero_pedido") or contexto.get("numero_factura", "")
    return f"{base} #{numero}" if numero else base
