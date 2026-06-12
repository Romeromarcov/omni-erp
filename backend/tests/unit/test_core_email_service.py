"""
Backfill de cobertura — apps/core/email_service.py.

TODO el I/O de red está mockeado: el backend SMTP usa el locmem de pytest-django
(``django.core.mail.outbox``) y SendGrid se simula inyectando un módulo fake en
``sys.modules``. CERO envíos reales.

Cubre:
- ``enviar_email`` por la ruta SMTP: HTML + texto fallback, adjuntos, cc, reply_to.
- ``_enviar_smtp`` con fallo de envío → ``EmailError`` (sin tragar la causa).
- ``enviar_email`` por la ruta SendGrid (api key presente): éxito 202, status no-2xx,
  excepción del SDK → ``EmailError``, y fallback a SMTP si el SDK no está instalado.
- ``_html_a_texto``.
- ``enviar_cotizacion_pdf`` y ``enviar_estado_cuenta_pdf`` (PDF mockeado): feliz y
  ``EmailError`` cuando el cliente no tiene email.
"""
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core import mail

from apps.core.email_service import (
    EmailError,
    _html_a_texto,
    enviar_cotizacion_pdf,
    enviar_email,
    enviar_estado_cuenta_pdf,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _sin_sendgrid_env(monkeypatch, settings):
    """Por defecto NO hay API key de SendGrid → ruta SMTP (locmem, sin red)."""
    monkeypatch.delenv("SENDGRID_API_KEY", raising=False)
    if hasattr(settings, "SENDGRID_API_KEY"):
        monkeypatch.delattr(settings, "SENDGRID_API_KEY", raising=False)
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


# ── Ruta SMTP ─────────────────────────────────────────────────────────────────


class TestEnviarEmailSMTP:
    def test_envio_basico_html_y_texto(self):
        ok = enviar_email(
            destinatario="cliente@test.com",
            asunto="Hola",
            cuerpo_html="<h1>Título</h1><p>Cuerpo</p>",
        )
        assert ok is True
        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.subject == "Hola"
        assert msg.to == ["cliente@test.com"]
        # Texto plano extraído del HTML
        assert msg.body == "Título Cuerpo"
        assert msg.alternatives == [("<h1>Título</h1><p>Cuerpo</p>", "text/html")]

    def test_lista_destinatarios_cc_reply_to_y_adjuntos(self):
        ok = enviar_email(
            destinatario=["a@test.com", "b@test.com"],
            asunto="Factura",
            cuerpo_html="<p>Adjunto</p>",
            cuerpo_texto="Adjunto",
            adjuntos=[("factura.pdf", b"%PDF-1.4", "application/pdf")],
            remitente="ventas@omni.test",
            cc=["copia@test.com"],
            reply_to="responder@omni.test",
        )
        assert ok is True
        msg = mail.outbox[0]
        assert msg.to == ["a@test.com", "b@test.com"]
        assert msg.cc == ["copia@test.com"]
        assert msg.reply_to == ["responder@omni.test"]
        assert msg.from_email == "ventas@omni.test"
        assert msg.body == "Adjunto"  # cuerpo_texto explícito, no derivado
        assert msg.attachments == [("factura.pdf", b"%PDF-1.4", "application/pdf")]

    def test_fallo_de_envio_lanza_email_error(self):
        with patch(
            "django.core.mail.EmailMultiAlternatives.send",
            side_effect=Exception("smtp caído"),
        ):
            with pytest.raises(EmailError, match="Error enviando email via SMTP"):
                enviar_email(destinatario="x@test.com", asunto="a", cuerpo_html="<p>h</p>")
        assert len(mail.outbox) == 0


# ── Ruta SendGrid (SDK fake en sys.modules) ──────────────────────────────────


def _instalar_sendgrid_fake(monkeypatch, status_code=202, send_exc=None):
    """Inyecta un módulo sendgrid falso y retorna el registro de llamadas."""
    llamadas = {}

    class FakeMail:
        def __init__(self, from_email=None, to_emails=None, subject=None):
            self.from_email = from_email
            self.to_emails = to_emails
            self.subject = subject
            self.contents = []
            self.attachments = []
            self.ccs = []
            self.reply_to = None

        def add_content(self, c):
            self.contents.append(c)

        def add_attachment(self, a):
            self.attachments.append(a)

        def add_cc(self, c):
            self.ccs.append(c)

    class FakeClient:
        def __init__(self, api_key=None):
            llamadas["api_key"] = api_key

        def send(self, message):
            llamadas["message"] = message
            if send_exc:
                raise send_exc
            return SimpleNamespace(status_code=status_code)

    sendgrid_mod = types.ModuleType("sendgrid")
    sendgrid_mod.SendGridAPIClient = FakeClient
    helpers_mod = types.ModuleType("sendgrid.helpers")
    mail_mod = types.ModuleType("sendgrid.helpers.mail")
    mail_mod.Mail = FakeMail
    for nombre in ("Attachment", "Content", "Email", "To"):
        setattr(mail_mod, nombre, MagicMock(name=nombre))
    # Attachment necesita aceptar kwargs y guardarlos
    mail_mod.Attachment = lambda **kw: kw
    mail_mod.Content = lambda tipo, valor: (tipo, valor)
    mail_mod.Email = lambda e: e
    mail_mod.To = lambda e: e
    sendgrid_mod.helpers = helpers_mod
    helpers_mod.mail = mail_mod
    monkeypatch.setitem(sys.modules, "sendgrid", sendgrid_mod)
    monkeypatch.setitem(sys.modules, "sendgrid.helpers", helpers_mod)
    monkeypatch.setitem(sys.modules, "sendgrid.helpers.mail", mail_mod)
    return llamadas


class TestEnviarEmailSendGrid:
    def test_envio_exitoso_202(self, monkeypatch):
        llamadas = _instalar_sendgrid_fake(monkeypatch, status_code=202)
        monkeypatch.setenv("SENDGRID_API_KEY", "sg-test-key")
        ok = enviar_email(
            destinatario="c@test.com",
            asunto="SG",
            cuerpo_html="<p>hola</p>",
            adjuntos=[("doc.pdf", b"123", "application/pdf")],
            cc=["cc@test.com"],
            reply_to="re@test.com",
        )
        assert ok is True
        assert llamadas["api_key"] == "sg-test-key"
        msg = llamadas["message"]
        assert msg.subject == "SG"
        # texto plano + html
        assert ("text/plain", "hola") in msg.contents
        assert ("text/html", "<p>hola</p>") in msg.contents
        assert msg.attachments[0]["file_name"] == "doc.pdf"
        assert msg.attachments[0]["file_type"] == "application/pdf"
        assert msg.ccs == ["cc@test.com"]
        assert msg.reply_to == "re@test.com"
        assert len(mail.outbox) == 0  # NO pasó por SMTP

    def test_status_no_2xx_retorna_false(self, monkeypatch):
        _instalar_sendgrid_fake(monkeypatch, status_code=500)
        monkeypatch.setenv("SENDGRID_API_KEY", "sg-test-key")
        ok = enviar_email(destinatario="c@test.com", asunto="SG", cuerpo_html="<p>h</p>")
        assert ok is False

    def test_excepcion_del_sdk_lanza_email_error(self, monkeypatch):
        _instalar_sendgrid_fake(monkeypatch, send_exc=RuntimeError("api caída"))
        monkeypatch.setenv("SENDGRID_API_KEY", "sg-test-key")
        with pytest.raises(EmailError, match="Error enviando email via SendGrid"):
            enviar_email(destinatario="c@test.com", asunto="SG", cuerpo_html="<p>h</p>")

    def test_sdk_no_instalado_fallback_a_smtp(self, monkeypatch):
        # sys.modules[name] = None hace que `import sendgrid` lance ImportError
        monkeypatch.setitem(sys.modules, "sendgrid", None)
        monkeypatch.setenv("SENDGRID_API_KEY", "sg-test-key")
        ok = enviar_email(destinatario="c@test.com", asunto="Fallback", cuerpo_html="<p>h</p>")
        assert ok is True
        assert len(mail.outbox) == 1
        assert mail.outbox[0].subject == "Fallback"


# ── Helpers ───────────────────────────────────────────────────────────────────


class TestHtmlATexto:
    def test_extrae_texto_y_colapsa_espacios(self):
        assert _html_a_texto("<h1>Hola</h1>\n  <p>mundo   feliz</p>") == "Hola mundo feliz"

    def test_html_vacio(self):
        assert _html_a_texto("") == ""


# ── Funciones de alto nivel ──────────────────────────────────────────────────


def _cotizacion_fake(email_cliente):
    cliente = SimpleNamespace(email=email_cliente, razon_social="Acme C.A.")
    return SimpleNamespace(
        id_cliente=cliente,
        numero_cotizacion="COT-001",
        fecha_vencimiento="2026-07-01",
        monto_total="150.00",
        id_moneda="USD",
        id_empresa=SimpleNamespace(nombre_empresa="Omni Test"),
    )


class TestEnviarCotizacionPdf:
    def test_envia_con_pdf_adjunto(self):
        cot = _cotizacion_fake("cliente@acme.test")
        with patch(
            "apps.ventas.pdf_cotizacion.generar_pdf_cotizacion", return_value=b"%PDF-cot"
        ) as gen:
            ok = enviar_cotizacion_pdf(cot)
        assert ok is True
        gen.assert_called_once_with(cot)
        msg = mail.outbox[0]
        assert msg.to == ["cliente@acme.test"]
        assert msg.subject == "Cotización COT-001 - Omni Test"
        assert msg.attachments == [("Cotizacion_COT-001.pdf", b"%PDF-cot", "application/pdf")]
        assert "COT-001" in msg.alternatives[0][0]

    def test_cliente_sin_email_y_sin_destinatario_lanza_error(self):
        cot = _cotizacion_fake(None)
        with pytest.raises(EmailError, match="no tiene email"):
            enviar_cotizacion_pdf(cot)
        assert len(mail.outbox) == 0

    def test_cliente_sin_email_usa_destinatario_explicito(self):
        cot = _cotizacion_fake(None)
        with patch("apps.ventas.pdf_cotizacion.generar_pdf_cotizacion", return_value=b"%PDF"):
            ok = enviar_cotizacion_pdf(cot, destinatario="manual@test.com")
        assert ok is True
        assert mail.outbox[0].to == ["manual@test.com"]


class TestEnviarEstadoCuentaPdf:
    def test_envia_estado_cuenta(self):
        empresa = SimpleNamespace(nombre_empresa="Omni Test")
        cliente = SimpleNamespace(email="c@acme.test", razon_social="Acme C.A.")
        with patch(
            "apps.cuentas_por_cobrar.pdf_estado_cuenta.generar_pdf_estado_cuenta",
            return_value=b"%PDF-ec",
        ) as gen:
            ok = enviar_estado_cuenta_pdf(empresa, cliente, fecha_corte="2026-06-01")
        assert ok is True
        gen.assert_called_once_with(empresa, cliente, "2026-06-01")
        msg = mail.outbox[0]
        assert msg.subject == "Estado de Cuenta - Omni Test"
        assert msg.attachments == [("EstadoCuenta.pdf", b"%PDF-ec", "application/pdf")]
        assert "2026-06-01" in msg.alternatives[0][0]

    def test_cliente_sin_email_lanza_error(self):
        empresa = SimpleNamespace(nombre_empresa="Omni Test")
        cliente = SimpleNamespace(email=None, razon_social="Acme")
        with pytest.raises(EmailError, match="no tiene email"):
            enviar_estado_cuenta_pdf(empresa, cliente)
