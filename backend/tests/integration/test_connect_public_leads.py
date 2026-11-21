"""Cobertura integral PR-26 (Plan 07 — Omni Connect S2 + S3).

Cubre:
- Resolución pública acotada con ``rls_bypass()`` (solo perfiles activos y tarjetas ``ACTIVA``).
- Fail-closed bajo PostgreSQL RLS fuera del bypass (``SET ROLE`` no-privilegiado).
- Hash HMAC-SHA256 salado de IP (nunca IP en claro), clasificación de dispositivo y deduplicación 60s.
- Generación de vCard RFC 6350 con escape de ``\\``, ``;``, ``,`` y sanitización anti-CRLF/NUL.
- Captura pública de leads con consentimiento obligatorio, honeypot silencioso, throttle 429,
  ``full_clean()`` cross-tenant, pipeline predeterminado auto-creado, notificación y evento ``crm.lead.capturado``.
- ``PerfilViewSet`` multi-tenant + ``/mi-perfil/`` + restricción ``plantilla_bloqueada`` y perfiles ajenos.
- Herramientas MCP ``connect_mi_perfil`` (``connect:read``) y ``connect_actualizar_perfil`` (``connect:write``).
"""

from __future__ import annotations

import asyncio
from unittest import mock

import pytest
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from rest_framework.test import APIClient

from apps.connect import mcp as connect_mcp
from apps.connect.models import Perfil, Tarjeta, Toque
from apps.connect.services import (
    TEXTO_CONSENTIMIENTO_DEFAULT,
    PerfilNoEncontradoError,
    _hash_ip,
    _sanitizar_botones_publicos,
    asegurar_pipeline_predeterminado,
    clasificar_dispositivo,
    generar_vcard,
    resolver_origen_publico,
    resolver_perfil_publico,
    sanitizar_nombre_archivo_vcard,
)
from apps.connect.validators import normalizar_email, normalizar_telefono
from apps.core import mcp_server, rls
from apps.core.models import CapabilityToken, Notificacion, Roles, UsuarioRoles
from apps.crm.models import Etapa, Lead, Pipeline
from tests.connect.builders import crear_perfil, crear_tarjeta, crear_usuario

pytestmark = [pytest.mark.django_db]


def _token(empresa, scopes: list[str], *, creado_por=None) -> str:
    tok = CapabilityToken.objects.create(
        empresa=empresa,
        nombre="tok-connect",
        scopes=scopes,
        activo=True,
        creado_por=creado_por,
    )
    return str(tok.token)


# ── 1. Helpers puros (S2 + S3) ────────────────────────────────────────────────


class TestHelpersConnect:
    @pytest.mark.unit
    def test_hash_ip_hmac_salado_nunca_en_claro(self, settings):
        settings.CONNECT_IP_HASH_SECRET = "secreto-connect-test"
        h1 = _hash_ip("190.10.20.30")
        h2 = _hash_ip("190.10.20.30")
        h3 = _hash_ip("190.10.20.30", salt="emp-1")
        h4 = _hash_ip("190.10.20.30", salt="emp-2")
        assert h1 == h2
        assert len(h1) == 64
        assert "190.10.20.30" not in h1
        assert h3 != h4
        assert _hash_ip("") == ""
        assert _hash_ip(None) == ""

    @pytest.mark.unit
    def test_clasificar_dispositivo_user_agent(self):
        assert (
            clasificar_dispositivo("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15")
            == Toque.Dispositivo.IOS
        )
        assert clasificar_dispositivo("Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X)") == Toque.Dispositivo.IOS
        assert (
            clasificar_dispositivo("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36")
            == Toque.Dispositivo.ANDROID
        )
        assert (
            clasificar_dispositivo("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0")
            == Toque.Dispositivo.ESCRITORIO
        )
        assert (
            clasificar_dispositivo("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)") == Toque.Dispositivo.ESCRITORIO
        )
        assert clasificar_dispositivo("curl/8.4.0") == Toque.Dispositivo.OTRO
        assert clasificar_dispositivo("") == Toque.Dispositivo.OTRO
        assert clasificar_dispositivo(None) == Toque.Dispositivo.OTRO

    @pytest.mark.unit
    def test_resolver_origen_y_normalizadores_contacto(self):
        assert resolver_origen_publico("qr", tiene_tarjeta=True) == Toque.Origen.NFC
        assert resolver_origen_publico("qr", tiene_tarjeta=False) == Toque.Origen.QR
        assert resolver_origen_publico("NFC", tiene_tarjeta=False) == Toque.Origen.ENLACE
        assert resolver_origen_publico("otro", tiene_tarjeta=False) == Toque.Origen.ENLACE

        assert normalizar_email("  Ana.Perez@Ejemplo.COM ") == "ana.perez@ejemplo.com"
        assert normalizar_email(None) == ""
        assert normalizar_telefono("+58 (412) 123-4567") == "584121234567"
        assert normalizar_telefono("0412-1234567") == "584121234567"
        assert normalizar_telefono("0058 414 9998877") == "584149998877"
        assert normalizar_telefono("---", codigo_pais_default="58") == ""
        assert normalizar_telefono(None) == ""

    @pytest.mark.unit
    def test_generar_vcard_rfc6350_escape_y_anti_inyeccion_crlf(self):
        perfil = {
            "slug": "juan-perez",
            "nombre_publico": "Juan; Pérez, Jr.\\Dev\r\nTEL;TYPE=CELL:+19999999999",
            "cargo": "Gerente;\nEMAIL:evil@attacker.com",
            "empresa_nombre": "ACME, C.A.\\VE",
            "telefono_publico": "+584121234567\x00\nADR:Fake",
            "email_publico": "juan@acme.com\r\nORG:Evil",
            "bio": "Hola; mundo, 100% \\confiable\nURL:https://evil.example",
            "botones": [
                {"tipo": "web", "etiqueta": "Web", "valor": "https://acme.com/catalogo"},
                {"tipo": "web", "etiqueta": "Mal", "valor": "javascript:alert(1)"},
            ],
        }
        vcard = generar_vcard(perfil)
        lines = vcard.split("\r\n")
        assert lines[0] == "BEGIN:VCARD"
        assert lines[1] == "VERSION:3.0"
        assert lines[-2] == "END:VCARD"
        assert lines[-1] == ""

        # Ninguna propiedad inyectada puede aparecer como línea propia
        assert not any(line.startswith("TEL;TYPE=CELL:+1999") for line in lines)
        assert not any(line.startswith("EMAIL:evil@") for line in lines)
        assert not any(line.startswith("ORG:Evil") for line in lines)
        assert not any(line.startswith("ADR:") for line in lines)
        assert not any(line.startswith("URL:https://evil.example") for line in lines)
        assert "\x00" not in vcard
        assert "javascript:" not in vcard
        assert "URL:https://acme.com/catalogo" in lines

        # Escapes RFC 6350 (\ ; ,)
        fn_line = next(line for line in lines if line.startswith("FN:"))
        assert "\\;" in fn_line
        assert "\\," in fn_line
        assert "\\\\" in fn_line

        org_line = next(line for line in lines if line.startswith("ORG:"))
        assert org_line == r"ORG:ACME\, C.A.\\VE"

        # Nombre de una sola palabra + filename sanitizado
        vcard_simple = generar_vcard({"nombre_publico": "Ana"})
        assert "N:Ana;;;;" in vcard_simple
        assert sanitizar_nombre_archivo_vcard('juan\r\n"evil') == "juanevil"
        assert sanitizar_nombre_archivo_vcard("!!!") == "contacto"

    @pytest.mark.unit
    def test_sanitizar_botones_descarta_entradas_corruptas(self):
        assert _sanitizar_botones_publicos("no-lista") == []
        res = _sanitizar_botones_publicos(
            [
                {"tipo": "web", "etiqueta": "Ok", "valor": "https://omni.test"},
                {"tipo": "web", "etiqueta": "XSS", "valor": "javascript:alert(1)"},
            ]
        )
        assert res == [{"tipo": "web", "etiqueta": "Ok", "valor": "https://omni.test"}]


# ── 2. Perfil público, RLS acotado, Toque y vCard (S2) ────────────────────────


class TestPerfilPublicoYToque:
    def test_rls_bypass_acotado_consulta_previa_fail_closed(self, empresa_a, rls_test_role):
        """Bajo PostgreSQL RLS (bypass='off'), la consulta directa sin bypass da 0 filas,
        mientras resolver_perfil_publico resuelve solo el perfil activo y deja bypass='off' al salir."""
        perfil = crear_perfil(empresa_a, slug="ana-rls", nombre_publico="Ana RLS")

        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            rls.apply_context([], bypass=False)
            assert Perfil.objects.count() == 0

            proyeccion = resolver_perfil_publico("ANA-RLS")
            assert proyeccion["id_perfil"] == perfil.id_perfil
            assert proyeccion["slug"] == "ana-rls"

            # Al salir de resolver_perfil_publico el contexto vuelve a fail-closed.
            assert Perfil.objects.count() == 0
        finally:
            rls.apply_system_default()
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")

    def test_perfil_publico_no_expone_ids_internos_y_registra_toque_deduplicado(self, empresa_a):
        perfil = crear_perfil(
            empresa_a,
            slug="carlos-ventas",
            nombre_publico="Carlos Ventas",
            cargo="Ejecutivo",
            bio="Especialista NFC",
            telefono_publico="+584141112233",
            email_publico="carlos@alpha.test",
            tema="CORPORATIVO",
            botones=[{"tipo": "whatsapp", "etiqueta": "Escríbeme", "valor": "+584141112233"}],
        )

        client = APIClient()
        resp = client.get(
            "/api/public/connect/Carlos-Ventas/?origen=qr",
            HTTP_USER_AGENT="Mozilla/5.0 (Linux; Android 14; Pixel 8)",
            REMOTE_ADDR="198.51.100.42",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["slug"] == "carlos-ventas"
        assert data["nombre_publico"] == "Carlos Ventas"
        assert data["empresa_nombre"] == empresa_a.nombre_legal
        assert data["acepta_leads"] is True
        assert data["consentimiento_texto"] == TEXTO_CONSENTIMIENTO_DEFAULT
        for interno in ("id_empresa", "id_empresa_id", "usuario", "usuario_id", "id_perfil", "tarjeta_id"):
            assert interno not in data

        # Toque creado con hash HMAC (nunca IP en claro)
        assert Toque.objects.filter(perfil=perfil).count() == 1
        toque = Toque.objects.get(perfil=perfil)
        assert toque.origen == Toque.Origen.QR
        assert toque.dispositivo == Toque.Dispositivo.ANDROID
        assert toque.tarjeta is None
        assert len(toque.ip_hash) == 64
        assert "198.51.100.42" not in toque.ip_hash

        # Segunda visita dentro de 60s con mismo (perfil, origen, ip_hash) -> deduplicada
        resp2 = client.get(
            "/api/public/connect/carlos-ventas/?origen=qr",
            HTTP_USER_AGENT="Mozilla/5.0 (Linux; Android 14; Pixel 8)",
            REMOTE_ADDR="198.51.100.42",
        )
        assert resp2.status_code == 200
        assert Toque.objects.filter(perfil=perfil).count() == 1

        # Distinto origen -> sí registra nuevo toque
        resp3 = client.get(
            "/api/public/connect/carlos-ventas/",
            HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            REMOTE_ADDR="198.51.100.42",
        )
        assert resp3.status_code == 200
        assert Toque.objects.filter(perfil=perfil).count() == 2

        # Expirada la ventana de caché -> vuelve a registrar
        cache.clear()
        resp4 = client.get(
            "/api/public/connect/carlos-ventas/?origen=qr",
            REMOTE_ADDR="198.51.100.42",
        )
        assert resp4.status_code == 200
        assert Toque.objects.filter(perfil=perfil).count() == 3

    def test_perfil_con_tarjeta_activa_registra_nfc_y_rechaza_otros_estados_404(self, empresa_a, empresa_b):
        perfil = crear_perfil(empresa_a, slug="tarjeta-test")
        otro_perfil = crear_perfil(empresa_a, slug="otro-perfil")
        perfil_b = crear_perfil(empresa_b, slug="perfil-b")

        t_activa = crear_tarjeta(empresa_a, perfil=perfil, uid_chip="04A1B2C3D4", estado=Tarjeta.Estado.ACTIVA)
        t_inv = crear_tarjeta(empresa_a, perfil=None, uid_chip="04B1B2C3D4", estado=Tarjeta.Estado.INVENTARIO)
        t_des = crear_tarjeta(empresa_a, perfil=perfil, uid_chip="04C1B2C3D4", estado=Tarjeta.Estado.DESACTIVADA)
        t_per = crear_tarjeta(empresa_a, perfil=perfil, uid_chip="04D1B2C3D4", estado=Tarjeta.Estado.PERDIDA)
        t_inact = crear_tarjeta(
            empresa_a, perfil=perfil, uid_chip="04E1B2C3D4", estado=Tarjeta.Estado.ACTIVA, activo=False
        )
        t_ajena_misma_emp = crear_tarjeta(
            empresa_a, perfil=otro_perfil, uid_chip="04F1B2C3D4", estado=Tarjeta.Estado.ACTIVA
        )
        t_otra_emp = crear_tarjeta(empresa_b, perfil=perfil_b, uid_chip="0411B2C3D4", estado=Tarjeta.Estado.ACTIVA)

        client = APIClient()

        # UID válido con separadores y minúsculas -> 200 + Toque NFC con tarjeta
        resp_ok = client.get("/api/public/connect/tarjeta-test/?uid=04:a1:b2:c3:d4")
        assert resp_ok.status_code == 200
        toque = Toque.objects.get(perfil=perfil)
        assert toque.origen == Toque.Origen.NFC
        assert toque.tarjeta_id == t_activa.id_tarjeta

        # Cualquier tarjeta inválida / no ACTIVA / de otro perfil -> 404 sin filtrar estado
        for uid_malo in (
            t_inv.uid_chip,
            t_des.uid_chip,
            t_per.uid_chip,
            t_inact.uid_chip,
            t_ajena_misma_emp.uid_chip,
            t_otra_emp.uid_chip,
            "ZZZZ",
            "00000000",
        ):
            r = client.get(f"/api/public/connect/tarjeta-test/?uid={uid_malo}")
            assert r.status_code == 404
            assert "PERDIDA" not in r.content.decode()
            assert "DESACTIVADA" not in r.content.decode()
            assert "INVENTARIO" not in r.content.decode()

        # Perfil inactivo -> 404
        perfil.soft_delete()
        assert client.get("/api/public/connect/tarjeta-test/").status_code == 404

        # Empresa inactiva -> 404
        perfil.restore()
        empresa_a.activo = False
        empresa_a.save(update_fields=["activo"])
        assert client.get("/api/public/connect/tarjeta-test/").status_code == 404

        # Slugs inválidos / NUL -> 404 / 400
        assert client.get("/api/public/connect/admin/").status_code == 404
        assert client.get("/api/public/connect/bad%00slug/").status_code == 400
        assert client.get("/api/public/connect/tarjeta-test/?uid=abc%00").status_code == 400

    def test_descarga_vcard_publica_y_content_negotiation(self, empresa_a):
        crear_perfil(
            empresa_a,
            slug="maria-vcard",
            nombre_publico="María; López\r\nTEL:000",
            cargo="Directora",
            telefono_publico="+584129998877",
            email_publico="maria@alpha.test",
            bio="Contacto comercial",
        )
        client = APIClient()
        resp = client.get("/api/public/connect/maria-vcard/vcard/", HTTP_ACCEPT="text/vcard")
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/vcard")
        assert resp["Content-Disposition"] == 'attachment; filename="maria-vcard.vcf"'
        cuerpo = resp.content.decode("utf-8")
        assert "BEGIN:VCARD" in cuerpo
        assert "END:VCARD" in cuerpo
        assert not any(line.startswith("TEL:000") for line in cuerpo.splitlines())

        assert client.get("/api/public/connect/no-existe/vcard/").status_code == 404


# ── 3. Captura pública de leads, honeypot, throttle y eventos (S3) ───────────


class TestCapturaLeadPublico:
    def _payload(self, **extra):
        datos = {
            "nombre": "Luis",
            "apellido": "Gómez",
            "empresa_nombre": "Comercial Sur",
            "email": "  Luis.Gomez@Ejemplo.COM ",
            "telefono": "0412-555-6677",
            "mensaje": "Quiero cotización de tarjetas.",
            "consentimiento_aceptado": True,
            "consentimiento_texto": TEXTO_CONSENTIMIENTO_DEFAULT,
        }
        datos.update(extra)
        return datos

    def test_captura_lead_exitosa_crea_pipeline_notificacion_y_evento(
        self, empresa_a, empresa_b, django_capture_on_commit_callbacks
    ):
        perfil = crear_perfil(empresa_a, slug="vendedor-pro")
        tarjeta = crear_tarjeta(empresa_a, perfil=perfil, uid_chip="04AABBCCDDEE", estado=Tarjeta.Estado.ACTIVA)

        # Creamos un pipeline NO predeterminado llamado "Ventas" para probar desambiguación de nombre
        Pipeline.objects.create(id_empresa=empresa_a, nombre="Ventas", es_predeterminado=False)

        client = APIClient()
        with mock.patch("apps.eventos.producer.publicar_evento") as mock_pub:
            with django_capture_on_commit_callbacks(execute=True):
                resp = client.post(
                    f"/api/public/connect/vendedor-pro/leads/?uid={tarjeta.uid_chip}",
                    # Intento de inyectar id_empresa ajeno debe ignorarse
                    self._payload(id_empresa=str(empresa_b.id_empresa)),
                    format="json",
                )

        assert resp.status_code == 201
        assert resp.json()["ok"] is True

        lead = Lead.objects.get(perfil=perfil)
        assert lead.id_empresa_id == empresa_a.id_empresa
        assert lead.propietario_id == perfil.usuario_id
        assert lead.tarjeta_id == tarjeta.id_tarjeta
        assert lead.fuente == Lead.Fuente.NFC
        assert lead.email_normalizado == "luis.gomez@ejemplo.com"
        assert lead.telefono_normalizado == "584125556677"
        assert lead.consentimiento_aceptado is True
        assert lead.consentimiento_fecha is not None
        assert lead.consentimiento_texto == TEXTO_CONSENTIMIENTO_DEFAULT

        # Pipeline predeterminado auto-creado con las 5 etapas esperadas
        pipeline = Pipeline.objects.get(id_empresa=empresa_a, es_predeterminado=True, activo=True)
        etapas = list(Etapa.objects.filter(pipeline=pipeline).order_by("orden").values_list("nombre", "tipo"))
        assert etapas == [
            ("Nuevo", Etapa.Tipo.ABIERTA),
            ("Contactado", Etapa.Tipo.ABIERTA),
            ("Calificado", Etapa.Tipo.ABIERTA),
            ("Ganado", Etapa.Tipo.GANADA),
            ("Perdido", Etapa.Tipo.PERDIDA),
        ]
        assert lead.pipeline_id == pipeline.id_pipeline
        assert lead.etapa.nombre == "Nuevo"

        # Notificación interna in-app al propietario
        notif = Notificacion.objects.get(id_empresa=empresa_a, id_usuario=perfil.usuario)
        assert notif.metadata["codigo_evento"] == "CONNECT_LEAD_CAPTURADO"
        assert notif.metadata["lead_id"] == str(lead.id_lead)
        assert "Luis Gómez" in notif.mensaje

        # Evento de dominio emitido
        mock_pub.assert_called_once()
        kwargs = mock_pub.call_args.kwargs
        assert kwargs["tipo"] == "crm.lead.capturado"
        assert kwargs["empresa_id"] == str(empresa_a.id_empresa)
        assert kwargs["payload"]["lead_id"] == str(lead.id_lead)

        # Segundo lead reutiliza el mismo pipeline predeterminado (ahora vía QR)
        resp2 = client.post(
            "/api/public/connect/vendedor-pro/leads/?origen=QR",
            self._payload(nombre="Elena", email="elena@test.local"),
            format="json",
        )
        assert resp2.status_code == 201
        assert Pipeline.objects.filter(id_empresa=empresa_a, es_predeterminado=True).count() == 1
        assert Lead.objects.filter(id_empresa=empresa_a).count() == 2

    def test_captura_lead_sin_consentimiento_falla_400_fail_closed(self, empresa_a):
        crear_perfil(empresa_a, slug="sin-consent")
        client = APIClient()

        for malo in (
            self._payload(consentimiento_aceptado=False),
            self._payload(consentimiento_texto=""),
            self._payload(consentimiento_texto="   "),
            {"nombre": "SoloNombre"},
        ):
            resp = client.post("/api/public/connect/sin-consent/leads/", malo, format="json")
            assert resp.status_code == 400
            assert Lead.objects.count() == 0

    def test_captura_lead_honeypot_silencioso_no_crea_lead_ni_toque(self, empresa_a):
        crear_perfil(empresa_a, slug="honeypot-slug")
        client = APIClient()

        resp = client.post(
            "/api/public/connect/honeypot-slug/leads/",
            self._payload(website="https://spam.example"),
            format="json",
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["ok"] is True
        assert "honeypot" not in str(body).lower()
        assert Lead.objects.count() == 0
        assert Toque.objects.count() == 0

        # También si solo envía partial payload con company_url
        resp2 = client.post(
            "/api/public/connect/honeypot-slug/leads/",
            {"nombre": "Bot", "company_url": "https://bot.example"},
            format="json",
        )
        assert resp2.status_code == 201
        assert Lead.objects.count() == 0

        # Slug inexistente con honeypot sigue devolviendo 404
        resp3 = client.post(
            "/api/public/connect/no-existe-slug/leads/",
            {"website": "https://bot.example"},
            format="json",
        )
        assert resp3.status_code == 404

    def test_fallo_en_notificacion_no_revierte_lead(self, empresa_a):
        crear_perfil(empresa_a, slug="notif-resiliente")
        client = APIClient()
        with mock.patch("apps.notificaciones.services.emitir_notificacion", side_effect=RuntimeError("boom")):
            resp = client.post(
                "/api/public/connect/notif-resiliente/leads/",
                self._payload(),
                format="json",
            )
        assert resp.status_code == 201
        assert Lead.objects.count() == 1

    def test_throttle_connect_lead_y_publico_retornan_429(self, empresa_a, monkeypatch):
        crear_perfil(empresa_a, slug="rate-limit-slug")
        monkeypatch.setitem(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "connect_lead", "2/min")
        monkeypatch.setitem(settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "connect_publico", "2/min")

        client = APIClient()
        # ConnectLeadThrottle (2/min)
        for _ in range(2):
            r = client.post("/api/public/connect/rate-limit-slug/leads/", self._payload(), format="json")
            assert r.status_code == 201
        r3 = client.post("/api/public/connect/rate-limit-slug/leads/", self._payload(), format="json")
        assert r3.status_code == 429

        # ConnectPublicoThrottle (2/min)
        for _ in range(2):
            rg = client.get("/api/public/connect/rate-limit-slug/")
            assert rg.status_code == 200
        rg3 = client.get("/api/public/connect/rate-limit-slug/")
        assert rg3.status_code == 429

    def test_asegurar_pipeline_predeterminado_crea_etapas_si_estaba_vacio(self, empresa_a):
        pipeline_vacio = Pipeline.objects.create(id_empresa=empresa_a, nombre="Principal", es_predeterminado=True)
        res = asegurar_pipeline_predeterminado(empresa_a)
        assert res.pk == pipeline_vacio.pk
        assert Etapa.objects.filter(pipeline=pipeline_vacio).count() == 5

    def test_resolver_perfil_publico_no_encontrado_lanza_error(self, empresa_a):
        with pytest.raises(PerfilNoEncontradoError):
            resolver_perfil_publico("no-existe-test")


# ── 4. Endpoints autenticados PerfilViewSet + MCP (S2 + S3) ──────────────────


class TestPerfilViewSetYMCP:
    def test_mi_perfil_requiere_auth_y_crea_y_actualiza_perfil_propio(self, empresa_a, user_a):
        assert APIClient().get("/api/connect/perfiles/mi-perfil/").status_code == 401

        client = APIClient()
        client.force_authenticate(user=user_a)

        # Antes de crear -> 404
        assert client.get("/api/connect/perfiles/mi-perfil/").status_code == 404

        # PATCH inicial crea perfil (201) normalizando slug
        resp_create = client.patch(
            "/api/connect/perfiles/mi-perfil/",
            {
                "slug": " User-A-Slug ",
                "nombre_publico": "Usuario A",
                "cargo": "Vendedor",
                "tema": "CLASICO",
                "botones": [{"tipo": "web", "etiqueta": "Web", "valor": "https://alpha.test"}],
            },
            format="json",
        )
        assert resp_create.status_code == 201, resp_create.content
        assert resp_create.json()["slug"] == "user-a-slug"

        # GET devuelve el perfil creado (200)
        resp_get = client.get("/api/connect/perfiles/mi-perfil/")
        assert resp_get.status_code == 200
        assert resp_get.json()["nombre_publico"] == "Usuario A"

        # PATCH subsecuente actualiza (200)
        resp_upd = client.patch(
            "/api/connect/perfiles/mi-perfil/",
            {"cargo": "Gerente Comercial"},
            format="json",
        )
        assert resp_upd.status_code == 200
        assert resp_upd.json()["cargo"] == "Gerente Comercial"

    def test_aislamiento_cross_tenant_y_permisos_plantilla_bloqueada(self, empresa_a, empresa_b, user_a, user_b):
        otro_user_a = crear_usuario(empresa_a)
        perfil_a = crear_perfil(empresa_a, usuario=user_a, slug="user-a-iso")
        perfil_otro_a = crear_perfil(empresa_a, usuario=otro_user_a, slug="otro-a-iso")
        perfil_b = crear_perfil(empresa_b, usuario=user_b, slug="user-b-iso")

        client_a = APIClient()
        client_a.force_authenticate(user=user_a)

        # A no ve perfiles de B en listado ni retrieve/patch/delete
        list_resp = client_a.get("/api/connect/perfiles/")
        assert list_resp.status_code == 200
        items = list_resp.data["results"] if "results" in list_resp.data else list_resp.data
        ids = {str(x["id_perfil"]) for x in items}
        assert str(perfil_a.id_perfil) in ids
        assert str(perfil_b.id_perfil) not in ids

        assert client_a.get(f"/api/connect/perfiles/{perfil_b.id_perfil}/").status_code == 404
        assert (
            client_a.patch(
                f"/api/connect/perfiles/{perfil_b.id_perfil}/", {"nombre_publico": "Hack"}, format="json"
            ).status_code
            == 404
        )
        assert client_a.delete(f"/api/connect/perfiles/{perfil_b.id_perfil}/").status_code == 404

        # No-admin no puede editar perfil ajeno en la misma empresa ni activar plantilla_bloqueada
        assert (
            client_a.patch(
                f"/api/connect/perfiles/{perfil_otro_a.id_perfil}/", {"nombre_publico": "Ajeno"}, format="json"
            ).status_code
            == 403
        )
        assert (
            client_a.patch(
                f"/api/connect/perfiles/{perfil_a.id_perfil}/", {"plantilla_bloqueada": True}, format="json"
            ).status_code
            == 403
        )
        assert (
            client_a.patch(
                "/api/connect/perfiles/mi-perfil/", {"plantilla_bloqueada": True}, format="json"
            ).status_code
            == 403
        )

        # Admin (rol Administrador) SÍ puede bloquear plantilla y luego usuario no-admin no puede cambiar tema
        rol_admin = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Administrador")
        admin_a = crear_usuario(empresa_a)
        UsuarioRoles.objects.create(id_usuario=admin_a, id_rol=rol_admin)

        client_admin = APIClient()
        client_admin.force_authenticate(user=admin_a)
        resp_lock = client_admin.patch(
            f"/api/connect/perfiles/{perfil_a.id_perfil}/",
            {"plantilla_bloqueada": True, "tema": "CORPORATIVO"},
            format="json",
        )
        assert resp_lock.status_code == 200

        # Usuario sin rol admin no puede cambiar tema mientras plantilla_bloqueada=True
        resp_tema = client_a.patch("/api/connect/perfiles/mi-perfil/", {"tema": "OSCURO"}, format="json")
        assert resp_tema.status_code == 403

        # Pero SÍ puede editar su nombre/cargo sin cambiar el tema
        resp_cargo = client_a.patch("/api/connect/perfiles/mi-perfil/", {"cargo": "Senior"}, format="json")
        assert resp_cargo.status_code == 200

        # Validaciones NUL y UUID inválido
        assert client_a.get("/api/connect/perfiles/no-es-uuid/").status_code == 400
        assert client_a.get("/api/connect/perfiles/?search=a%00b").status_code == 400

    def test_mcp_connect_tools_autodiscovery_permisos_y_flujo(self, empresa_a, empresa_b, user_a, user_b):
        assert {t["name"] for t in connect_mcp.MCP_TOOLS} == {"connect_mi_perfil", "connect_actualizar_perfil"}
        assert "connect_mi_perfil" in mcp_server._DISCOVERED_TOOLS
        assert "connect_actualizar_perfil" in mcp_server._DISCOVERED_TOOLS
        assert "apps.connect.mcp" in settings.MCP_AGENT_CAPABILITIES["module_paths"]
        assert "connect:read" in settings.MCP_AGENT_CAPABILITIES["scopes"]
        assert "connect:write" in settings.MCP_AGENT_CAPABILITIES["scopes"]

        registradas = {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}
        assert {"connect_mi_perfil", "connect_actualizar_perfil"} <= registradas

        tok_read = _token(empresa_a, ["connect:read"], creado_por=user_a)
        tok_write = _token(empresa_a, ["connect:write"], creado_por=user_a)

        # Sin perfil aún -> dict con error descriptivo
        sin_perfil = connect_mcp.connect_mi_perfil(tok_read)
        assert "error" in sin_perfil

        # Crear vía connect_actualizar_perfil (valida full_clean())
        creado = connect_mcp.connect_actualizar_perfil(
            tok_write,
            slug=" MCP-User-A ",
            nombre_publico="MCP User A",
            cargo="Consultor",
            tema="CLASICO",
            botones=[{"tipo": "correo", "etiqueta": "Email", "valor": "mcp@alpha.test"}],
        )
        assert creado["slug"] == "mcp-user-a"
        assert creado["nombre_publico"] == "MCP User A"

        # Leer vía connect_mi_perfil
        leido = connect_mcp.connect_mi_perfil(tok_read, empresa_id=str(empresa_a.pk))
        assert leido["id_perfil"] == creado["id_perfil"]

        # Validación full_clean() bloquea botón inseguro
        invalido = connect_mcp.connect_actualizar_perfil(
            tok_write,
            botones=[{"tipo": "web", "etiqueta": "XSS", "valor": "javascript:alert(1)"}],
        )
        assert "error" in invalido

        # Scopes / cross-tenant / UUID / NUL
        with pytest.raises(PermissionError):
            connect_mcp.connect_mi_perfil(tok_write)  # no tiene connect:read
        with pytest.raises(PermissionError):
            connect_mcp.connect_actualizar_perfil(tok_read, cargo="Hack")  # no tiene connect:write
        with pytest.raises(PermissionError):
            connect_mcp.connect_mi_perfil(tok_read, empresa_id=str(empresa_b.pk))
        with pytest.raises(PermissionError):
            connect_mcp.connect_mi_perfil(tok_read, usuario_id=str(user_b.pk))
        with pytest.raises(ValueError, match="UUID"):
            connect_mcp.connect_mi_perfil(tok_read, empresa_id="no-uuid")
        with pytest.raises(ValueError, match="inválidos"):
            connect_mcp.connect_mi_perfil(tok_read, usuario_id=f"{user_a.pk}\x00")
        with pytest.raises(ValueError, match="inválidos"):
            connect_mcp.connect_actualizar_perfil(tok_write, cargo="abc\x00")

        # IDOR intra-tenant: actor no-admin no puede editar el perfil de otro usuario vía MCP
        colega_a = crear_usuario(empresa_a)
        crear_perfil(empresa_a, colega_a, slug="colega-alpha", nombre_publico="Colega")
        with pytest.raises(PermissionError, match="otro usuario"):
            connect_mcp.connect_actualizar_perfil(tok_write, usuario_id=str(colega_a.pk), cargo="Hackeado")

        # Validación recursiva de byte NUL dentro de botones en MCP
        with pytest.raises(ValueError, match="inválidos"):
            connect_mcp.connect_actualizar_perfil(
                tok_write,
                botones=[{"tipo": "web", "etiqueta": "Web", "valor": "https://alpha.test/\x00xss"}],
            )

        # Un actor admin SÍ puede actualizar el perfil de otro usuario de la misma empresa vía MCP
        rol_admin_mcp = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Administrador")
        admin_mcp = crear_usuario(empresa_a)
        UsuarioRoles.objects.create(id_usuario=admin_mcp, id_rol=rol_admin_mcp)
        tok_admin_mcp = _token(empresa_a, ["connect:write"], creado_por=admin_mcp)
        editado_admin = connect_mcp.connect_actualizar_perfil(
            tok_admin_mcp,
            usuario_id=str(colega_a.pk),
            cargo="Actualizado Admin",
        )
        assert editado_admin["cargo"] == "Actualizado Admin"

        # plantilla_bloqueada impide cambio de tema por usuario no-admin
        Perfil.objects.filter(pk=creado["id_perfil"]).update(plantilla_bloqueada=True)
        with pytest.raises(PermissionError, match="bloqueada"):
            connect_mcp.connect_actualizar_perfil(tok_write, tema="OSCURO")

        # Faltan slug/nombre_publico al crear nuevo perfil
        otro_emp_user = crear_usuario(empresa_b)
        tok_b = _token(empresa_b, ["connect:write"], creado_por=otro_emp_user)
        err_crear = connect_mcp.connect_actualizar_perfil(tok_b, cargo="Solo cargo")
        assert "error" in err_crear

        # Creación y actualización completa de todos los campos vía MCP
        creado_b = connect_mcp.connect_actualizar_perfil(
            tok_b,
            empresa_id=str(empresa_b.pk),
            slug="mcp-b-1",
            nombre_publico="MCP B",
        )
        assert creado_b["slug"] == "mcp-b-1"
        actualizado_b = connect_mcp.connect_actualizar_perfil(
            tok_b,
            slug="MCP-B-2",
            nombre_publico="MCP B Editado",
            cargo="VP",
            bio="Bio actualizada",
            telefono_publico="+584120001122",
            email_publico="vp@beta.test",
            tema="MODERNO",
        )
        assert actualizado_b["slug"] == "mcp-b-2"
        assert actualizado_b["bio"] == "Bio actualizada"
        assert actualizado_b["email_publico"] == "vp@beta.test"

    def test_perfil_viewset_create_delete_filtros_y_permisos_extra(self, empresa_a, empresa_b, user_a, user_b):
        otro_a = crear_usuario(empresa_a)
        client_a = APIClient()
        client_a.force_authenticate(user=user_a)
        client_otro = APIClient()
        client_otro.force_authenticate(user=otro_a)

        # GET mi-perfil antes de crear -> 404; empresa ajena -> 403
        assert client_a.get("/api/connect/perfiles/mi-perfil/").status_code == 404
        assert client_a.get(f"/api/connect/perfiles/mi-perfil/?empresa_id={empresa_b.pk}").status_code == 403

        # Non-admin no puede crear con plantilla_bloqueada=True ni para otro usuario
        resp_lock_create = client_a.post(
            "/api/connect/perfiles/",
            {"slug": "bloqueado-no-admin", "nombre_publico": "X", "plantilla_bloqueada": True},
            format="json",
        )
        assert resp_lock_create.status_code == 403

        # Crear perfil vía POST /api/connect/perfiles/
        resp_create = client_a.post(
            "/api/connect/perfiles/",
            {
                "slug": "creado-api",
                "nombre_publico": "Creado API",
                "cargo": "Ejecutivo",
                "tema": "CLASICO",
                "botones": [],
            },
            format="json",
        )
        assert resp_create.status_code == 201
        perfil_id = resp_create.data["id_perfil"]

        # Segundo POST mismo usuario/empresa dispara IntegrityError -> 400
        resp_dup = client_a.post(
            "/api/connect/perfiles/",
            {"slug": "otro-slug-libre", "nombre_publico": "Duplicado"},
            format="json",
        )
        assert resp_dup.status_code == 400

        # Listado filtrado por empresa_id
        resp_list = client_a.get(f"/api/connect/perfiles/?empresa_id={empresa_a.pk}")
        assert resp_list.status_code == 200

        # Intentar cambiar id_empresa a empresa no visible -> 400 (TenantFKScopeMixin)
        assert (
            client_a.patch(
                f"/api/connect/perfiles/{perfil_id}/",
                {"id_empresa": str(empresa_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        # Incluso si pertenece a empresa_b (no-admin o admin), id_empresa es estrictamente inmutable (400)
        user_a.empresas.add(empresa_b)
        assert (
            client_a.patch(
                f"/api/connect/perfiles/{perfil_id}/",
                {"id_empresa": str(empresa_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        rol_admin_emp = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Admin")
        admin_multi = crear_usuario(empresa_a)
        admin_multi.empresas.add(empresa_b)
        UsuarioRoles.objects.create(id_usuario=admin_multi, id_rol=rol_admin_emp)
        client_admin_multi = APIClient()
        client_admin_multi.force_authenticate(user=admin_multi)
        assert (
            client_admin_multi.patch(
                f"/api/connect/perfiles/{perfil_id}/",
                {"id_empresa": str(empresa_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.patch(
                f"/api/connect/perfiles/{perfil_id}/",
                {"usuario": str(otro_a.pk)},
                format="json",
            ).status_code
            == 403
        )

        # Byte NUL dentro de botones (nested JSONField) se rechaza con 400 en vez de DataError 500
        assert (
            client_a.patch(
                "/api/connect/perfiles/mi-perfil/",
                {"botones": [{"tipo": "web", "etiqueta": "Web", "valor": "https://a.com/\x00bad"}]},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_otro.post(
                "/api/connect/perfiles/",
                {
                    "slug": "con-nul-boton",
                    "nombre_publico": "NUL",
                    "botones": [{"tipo": "web", "etiqueta": "Bad\x00Label", "valor": "https://a.com"}],
                },
                format="json",
            ).status_code
            == 400
        )

        # Con plantilla_bloqueada=True, cambiar tema vía PATCH /{id}/ -> 403
        Perfil.objects.filter(pk=perfil_id).update(plantilla_bloqueada=True)
        assert (
            client_a.patch(
                f"/api/connect/perfiles/{perfil_id}/",
                {"tema": "OSCURO"},
                format="json",
            ).status_code
            == 403
        )

        # Otro usuario de la misma empresa no puede eliminar el perfil
        assert client_otro.delete(f"/api/connect/perfiles/{perfil_id}/").status_code == 403

        # En creación vía mi-perfil, usuario no-admin no puede activar plantilla_bloqueada -> 403
        assert (
            client_otro.patch(
                "/api/connect/perfiles/mi-perfil/",
                {"slug": "otro-mi-perfil", "nombre_publico": "Otro", "plantilla_bloqueada": True},
                format="json",
            ).status_code
            == 403
        )

        # El dueño sí puede soft-delete y luego reactivar vía PATCH /mi-perfil/
        resp_del = client_a.delete(f"/api/connect/perfiles/{perfil_id}/")
        assert resp_del.status_code == 204
        assert Perfil.objects.get(pk=perfil_id).activo is False
        assert APIClient().get("/api/public/connect/creado-api/").status_code == 404

        resp_reactivar = client_a.patch(
            "/api/connect/perfiles/mi-perfil/",
            {"nombre_publico": "Creado Reactivado"},
            format="json",
        )
        assert resp_reactivar.status_code == 200
        assert resp_reactivar.data["activo"] is True
        assert Perfil.objects.get(pk=perfil_id).activo is True
        assert APIClient().get("/api/public/connect/creado-api/").status_code == 200

    def test_validaciones_publicas_vcard_accept_throttles_y_helpers(self, empresa_a, empresa_b, user_a):
        from django.contrib.auth.models import AnonymousUser
        from django.core.exceptions import ImproperlyConfigured, ValidationError as DjangoValidationError
        from django.test import override_settings
        from rest_framework.test import APIRequestFactory

        from apps.connect.services import (
            DEFAULT_PIPELINE_NOMBRE,
            ConsentimientoRequeridoError,
            capturar_lead_publico,
            obtener_ip_cliente,
            usuario_es_admin_empresa,
        )
        from apps.connect.throttles import _ConnectScopedThrottle

        perfil = crear_perfil(empresa_a, user_a, slug="soporte-extra", nombre_publico="Soporte Extra")
        client = APIClient()

        # Negociación Accept: text/vcard y renderizador VCardRenderer
        from apps.connect.views import VCardRenderer

        resp_vcf = client.get(f"/api/public/connect/{perfil.slug}/vcard/", HTTP_ACCEPT="text/vcard")
        assert resp_vcf.status_code == 200
        assert b"BEGIN:VCARD" in resp_vcf.content
        renderer = VCardRenderer()
        assert renderer.render(b"BEGIN:VCARD") == b"BEGIN:VCARD"
        assert renderer.render("END:VCARD") == b"END:VCARD"
        assert b"Perfil no encontrado" in renderer.render({"detail": "Perfil no encontrado"})

        # Validaciones de slug/parámetros con NUL o caracteres inválidos
        assert client.get("/api/public/connect/--invalido--/").status_code == 404
        assert client.get(f"/api/public/connect/{perfil.slug}/?uid=ab%00cd").status_code == 400
        assert client.get(f"/api/public/connect/{perfil.slug}/vcard/?uid=ab%00cd").status_code == 400
        assert (
            client.post(
                f"/api/public/connect/{perfil.slug}/leads/?uid=ab%00cd",
                {"nombre": "Bot", "website": "https://spam.invalid"},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/public/connect/{perfil.slug}/leads/",
                {"nombre": "Bad\x00Name", "consentimiento_aceptado": True, "consentimiento_texto": "Ok"},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client.post(
                f"/api/public/connect/{perfil.slug}/leads/",
                {"k\x00ey": "val", "nombre": "Ana", "consentimiento_aceptado": True, "consentimiento_texto": "Ok"},
                format="json",
            ).status_code
            == 400
        )
        # Honeypot sobre perfil inexistente responde 404
        assert (
            client.post(
                "/api/public/connect/inexistente-bot/leads/",
                {"nombre": "Bot", "website": "https://spam.invalid"},
                format="json",
            ).status_code
            == 404
        )
        # Honeypot y validaciones directas de servicio capturar_lead_publico
        silencioso = capturar_lead_publico(
            slug=perfil.slug,
            datos={"nombre": "Bot", "company_url": "https://bot.test"},
        )
        assert silencioso["ok"] is True
        assert silencioso["lead_id"] is None

        with pytest.raises(ConsentimientoRequeridoError):
            capturar_lead_publico(
                slug=perfil.slug,
                datos={"nombre": "Ana", "consentimiento_aceptado": False, "consentimiento_texto": "Ok"},
            )
        with pytest.raises(DjangoValidationError):
            capturar_lead_publico(
                slug=perfil.slug,
                datos={"nombre": "   ", "consentimiento_aceptado": True, "consentimiento_texto": "Ok"},
            )
        with pytest.raises(DjangoValidationError):
            resolver_perfil_publico("slug\x00mal")

        # _hash_ip vacío retorna "" y obtener_ip_cliente alinea XFF con NUM_PROXIES / REMOTE_ADDR
        assert _hash_ip("") == ""
        req_xff = APIRequestFactory().get(
            "/",
            REMOTE_ADDR="198.51.100.77",
            HTTP_X_FORWARDED_FOR="192.0.2.99, 203.0.113.5, 10.0.0.1",
        )
        # Sin NUM_PROXIES ignora X-Forwarded-For spoofable y usa REMOTE_ADDR
        assert obtener_ip_cliente(req_xff) == "198.51.100.77"
        with override_settings(NUM_PROXIES=1):
            assert obtener_ip_cliente(req_xff) == "10.0.0.1"
        with override_settings(NUM_PROXIES=2):
            assert obtener_ip_cliente(req_xff) == "203.0.113.5"

        # validar_botones rechaza \x00 explícitamente
        from apps.connect.validators import validar_botones

        with pytest.raises(DjangoValidationError, match="inválidos"):
            validar_botones([{"tipo": "web", "etiqueta": "Web", "valor": "https://ok.com/\x00x"}])

        # asegurar_pipeline_predeterminado cuando DEFAULT_PIPELINE_NOMBRE y "Ventas Connect" ya existen
        Pipeline.objects.create(id_empresa=empresa_a, nombre=DEFAULT_PIPELINE_NOMBRE, es_predeterminado=False)
        Pipeline.objects.create(id_empresa=empresa_a, nombre="Ventas Connect", es_predeterminado=False)
        pipe_creado = asegurar_pipeline_predeterminado(empresa_a)
        assert pipe_creado.es_predeterminado is True
        assert pipe_creado.nombre == "Ventas Connect 2"

        # usuario_es_admin_empresa: match exacto normalizado y membresía obligatoria para rol global
        assert usuario_es_admin_empresa(None) is False
        assert usuario_es_admin_empresa(AnonymousUser()) is False
        rol_falso = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Asistente Administrativo")
        user_falso = crear_usuario(empresa_a)
        UsuarioRoles.objects.create(id_usuario=user_falso, id_rol=rol_falso)
        assert usuario_es_admin_empresa(user_falso, empresa_a.pk) is False

        rol_global = Roles.objects.create(id_empresa=None, nombre_rol="Administrador General")
        user_global = crear_usuario(empresa_a)
        UsuarioRoles.objects.create(id_usuario=user_global, id_rol=rol_global)
        assert usuario_es_admin_empresa(user_global, empresa_a.pk) is True
        assert usuario_es_admin_empresa(user_global, empresa_b.pk) is False

        staff_user = crear_usuario(empresa_a)
        staff_user.is_staff = True
        staff_user.save(update_fields=["is_staff"])
        assert usuario_es_admin_empresa(staff_user) is True
        assert usuario_es_admin_empresa(staff_user, empresa_a.pk) is True

        # Throttles edge cases: sin scope, fallback a api_settings y scope faltante -> ImproperlyConfigured
        req = APIRequestFactory().get("/")

        class DummyViewNoScope:
            pass

        t_no_scope = _ConnectScopedThrottle()
        assert t_no_scope.get_rate() is None
        assert t_no_scope.allow_request(req, DummyViewNoScope()) is True

        class DummyViewFallbackScope:
            throttle_scope = "anon"

        with override_settings(REST_FRAMEWORK={}):
            t_fallback = _ConnectScopedThrottle()
            assert isinstance(t_fallback.allow_request(req, DummyViewFallbackScope()), bool)

        class DummyViewMissingScope:
            throttle_scope = "scope_inexistente_connect"

        t_missing = _ConnectScopedThrottle()
        with pytest.raises(ImproperlyConfigured):
            t_missing.allow_request(req, DummyViewMissingScope())

        # Cobertura adicional: superuser, usuario sin empresa en /mi-perfil/, swagger_fake_view y fallo en evento
        from apps.connect.services import _emitir_evento_lead_capturado
        from apps.connect.views import PerfilViewSet
        from apps.core.models import Usuarios

        super_u = crear_usuario(empresa_a)
        super_u.is_superuser = True
        super_u.save(update_fields=["is_superuser"])
        assert usuario_es_admin_empresa(super_u, empresa_a.pk) is True

        sin_empresa = Usuarios.objects.create_user(username="sinemp_conn", password=None)
        client_sin = APIClient()
        client_sin.force_authenticate(user=sin_empresa)
        assert client_sin.get("/api/connect/perfiles/mi-perfil/").status_code == 403

        vs = PerfilViewSet()
        vs.swagger_fake_view = True
        assert vs.get_queryset().count() == 0

        with mock.patch("apps.eventos.producer.publicar_evento", side_effect=RuntimeError("Kafka down")):
            _emitir_evento_lead_capturado({"lead_id": "1"}, str(empresa_a.pk))
