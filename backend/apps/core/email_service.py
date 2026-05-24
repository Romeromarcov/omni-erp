"""
M10-T3: Servicio de correo electrónico (HTML + PDF adjunto).

Soporte para:
  - SMTP estándar (Django backend)
  - SendGrid (cuando SENDGRID_API_KEY está configurado)

Uso básico:
    from apps.core.email_service import enviar_email
    enviar_email(
        destinatario="cliente@empresa.com",
        asunto="Su cotización",
        cuerpo_html="<h1>Estimado cliente...</h1>",
        adjuntos=[("cotizacion.pdf", pdf_bytes, "application/pdf")],
    )
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("omni.core.email")


class EmailError(Exception):
    """Error en el envío de correo."""
    pass


def enviar_email(
    destinatario: str | list[str],
    asunto: str,
    cuerpo_html: str,
    cuerpo_texto: Optional[str] = None,
    adjuntos: Optional[list[tuple[str, bytes, str]]] = None,
    remitente: Optional[str] = None,
    cc: Optional[list[str]] = None,
    reply_to: Optional[str] = None,
) -> bool:
    """
    Envía un correo electrónico con soporte HTML y adjuntos PDF.

    Args:
        destinatario:  Email destino o lista de emails.
        asunto:        Asunto del mensaje.
        cuerpo_html:   Cuerpo en formato HTML.
        cuerpo_texto:  Cuerpo en texto plano (fallback). Si None, se extrae del HTML.
        adjuntos:      Lista de tuplas (nombre_archivo, bytes, mime_type).
                       Ejemplo: [("factura.pdf", pdf_bytes, "application/pdf")]
        remitente:     Email remitente (default: DEFAULT_FROM_EMAIL en settings).
        cc:            Lista de emails en copia.
        reply_to:      Email para respuestas.

    Returns:
        True si el envío fue exitoso.

    Raises:
        EmailError: Si el envío falla.
    """
    from django.conf import settings

    remitente = remitente or getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@omni-erp.com")
    destinatarios = [destinatario] if isinstance(destinatario, str) else destinatario

    sendgrid_key = os.environ.get("SENDGRID_API_KEY") or getattr(settings, "SENDGRID_API_KEY", None)

    if sendgrid_key:
        return _enviar_sendgrid(
            destinatarios=destinatarios,
            asunto=asunto,
            cuerpo_html=cuerpo_html,
            cuerpo_texto=cuerpo_texto,
            adjuntos=adjuntos or [],
            remitente=remitente,
            cc=cc or [],
            reply_to=reply_to,
            api_key=sendgrid_key,
        )
    else:
        return _enviar_smtp(
            destinatarios=destinatarios,
            asunto=asunto,
            cuerpo_html=cuerpo_html,
            cuerpo_texto=cuerpo_texto,
            adjuntos=adjuntos or [],
            remitente=remitente,
            cc=cc or [],
            reply_to=reply_to,
        )


# ── Backend SMTP (Django nativo) ──────────────────────────────────────────────


def _enviar_smtp(
    destinatarios: list[str],
    asunto: str,
    cuerpo_html: str,
    cuerpo_texto: Optional[str],
    adjuntos: list[tuple[str, bytes, str]],
    remitente: str,
    cc: list[str],
    reply_to: Optional[str],
) -> bool:
    """Envía email usando el backend SMTP configurado en Django."""
    from django.core.mail import EmailMultiAlternatives

    texto = cuerpo_texto or _html_a_texto(cuerpo_html)
    msg = EmailMultiAlternatives(
        subject=asunto,
        body=texto,
        from_email=remitente,
        to=destinatarios,
        cc=cc,
        reply_to=[reply_to] if reply_to else None,
    )
    msg.attach_alternative(cuerpo_html, "text/html")

    for nombre, contenido, mime in adjuntos:
        msg.attach(nombre, contenido, mime)

    try:
        msg.send(fail_silently=False)
        logger.info(
            "email_smtp | to=%s | asunto=%s | adjuntos=%d",
            destinatarios, asunto, len(adjuntos),
        )
        return True
    except Exception as exc:
        logger.error("email_smtp ERROR: %s", exc)
        raise EmailError(f"Error enviando email via SMTP: {exc}") from exc


# ── Backend SendGrid ──────────────────────────────────────────────────────────


def _enviar_sendgrid(
    destinatarios: list[str],
    asunto: str,
    cuerpo_html: str,
    cuerpo_texto: Optional[str],
    adjuntos: list[tuple[str, bytes, str]],
    remitente: str,
    cc: list[str],
    reply_to: Optional[str],
    api_key: str,
) -> bool:
    """Envía email usando la API de SendGrid."""
    import base64

    try:
        import sendgrid
        from sendgrid.helpers.mail import (
            Attachment,
            Content,
            Email,
            Mail,
            To,
        )
    except ImportError:
        logger.warning("sendgrid SDK no instalado, fallback a SMTP")
        return _enviar_smtp(
            destinatarios, asunto, cuerpo_html, cuerpo_texto,
            adjuntos, remitente, cc, reply_to,
        )

    sg = sendgrid.SendGridAPIClient(api_key=api_key)

    message = Mail(
        from_email=Email(remitente),
        to_emails=[To(d) for d in destinatarios],
        subject=asunto,
    )
    message.add_content(Content("text/plain", cuerpo_texto or _html_a_texto(cuerpo_html)))
    message.add_content(Content("text/html", cuerpo_html))

    for nombre, contenido, mime in adjuntos:
        encoded = base64.b64encode(contenido).decode()
        att = Attachment(
            file_content=encoded,
            file_type=mime,
            file_name=nombre,
            disposition="attachment",
        )
        message.add_attachment(att)

    for c in cc:
        message.add_cc(Email(c))

    if reply_to:
        message.reply_to = Email(reply_to)

    try:
        response = sg.send(message)
        logger.info(
            "email_sendgrid | to=%s | asunto=%s | status=%d",
            destinatarios, asunto, response.status_code,
        )
        return response.status_code in (200, 202)
    except Exception as exc:
        logger.error("email_sendgrid ERROR: %s", exc)
        raise EmailError(f"Error enviando email via SendGrid: {exc}") from exc


# ── Helpers ───────────────────────────────────────────────────────────────────


def _html_a_texto(html: str) -> str:
    """Extrae texto plano desde HTML (versión simple sin dependencias)."""
    import re
    texto = re.sub(r"<[^>]+>", " ", html)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


# ── Funciones de alto nivel ───────────────────────────────────────────────────


def enviar_cotizacion_pdf(cotizacion, destinatario: Optional[str] = None) -> bool:
    """
    Genera el PDF de una cotización y lo envía por email al cliente.

    Args:
        cotizacion:    instancia de Cotizacion.
        destinatario:  Email destino. Si None, usa el email del cliente.
    """
    from apps.ventas.pdf_cotizacion import generar_pdf_cotizacion

    cliente = cotizacion.id_cliente
    email_cliente = getattr(cliente, "email", None) or destinatario
    if not email_cliente:
        raise EmailError("El cliente no tiene email configurado y no se proporcionó destinatario.")

    pdf_bytes = generar_pdf_cotizacion(cotizacion)
    nombre_cliente = getattr(cliente, "razon_social", str(cliente))

    cuerpo_html = f"""
    <html><body>
    <p>Estimado/a {nombre_cliente},</p>
    <p>Adjunto encontrará su cotización <b>{cotizacion.numero_cotizacion}</b> válida hasta {cotizacion.fecha_vencimiento}.</p>
    <p>Monto total: <b>{cotizacion.monto_total} {cotizacion.id_moneda}</b></p>
    <p>Para cualquier consulta, no dude en contactarnos.</p>
    <br><p>Atentamente,<br>{cotizacion.id_empresa.nombre_empresa}</p>
    </body></html>
    """

    return enviar_email(
        destinatario=email_cliente,
        asunto=f"Cotización {cotizacion.numero_cotizacion} - {cotizacion.id_empresa.nombre_empresa}",
        cuerpo_html=cuerpo_html,
        adjuntos=[(f"Cotizacion_{cotizacion.numero_cotizacion}.pdf", pdf_bytes, "application/pdf")],
    )


def enviar_estado_cuenta_pdf(empresa, cliente, fecha_corte=None) -> bool:
    """
    Genera el PDF de estado de cuenta CxC y lo envía por email al cliente.
    """
    from apps.cuentas_por_cobrar.pdf_estado_cuenta import generar_pdf_estado_cuenta

    email_cliente = getattr(cliente, "email", None)
    if not email_cliente:
        raise EmailError("El cliente no tiene email configurado.")

    pdf_bytes = generar_pdf_estado_cuenta(empresa, cliente, fecha_corte)
    nombre_cliente = getattr(cliente, "razon_social", str(cliente))

    cuerpo_html = f"""
    <html><body>
    <p>Estimado/a {nombre_cliente},</p>
    <p>Adjunto encontrará su estado de cuenta actualizado a la fecha {fecha_corte or 'hoy'}.</p>
    <br><p>Atentamente,<br>{empresa.nombre_empresa}</p>
    </body></html>
    """

    return enviar_email(
        destinatario=email_cliente,
        asunto=f"Estado de Cuenta - {empresa.nombre_empresa}",
        cuerpo_html=cuerpo_html,
        adjuntos=[("EstadoCuenta.pdf", pdf_bytes, "application/pdf")],
    )
