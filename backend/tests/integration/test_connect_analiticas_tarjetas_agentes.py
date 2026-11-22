"""Tests de integración y seguridad para Omni Connect S10 + S11 + S12.

Cubre:
  - S10: analíticas agregadas multi-tenant, validaciones, aislamiento y purga Celery Beat con RLS.
  - S11: TarjetaViewSet CRUD/ciclo de vida, generación QR SVG/PNG con reportlab+zlib y paridad MCP.
  - S12: agentes connect_calificador y connect_seguimiento, aprobación obligatoria
    CONNECT_ENVIO_EXTERNO (nunca envío directo), Celery, REST y MCP.
"""

from __future__ import annotations

import json
import struct
import uuid
import zlib
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.agentes.connect_agents import (
    AGENTE_CALIFICADOR_ID,
    AGENTE_SEGUIMIENTO_ID,
    CODIGO_APROBACION_ENVIO_EXTERNO,
    MODELO_ORIGEN_PREDICCION,
    ejecutar_connect_calificador,
    ejecutar_connect_seguimiento,
)
from apps.agentes.mcp import (
    agentes_calificar_lead_connect,
    agentes_disparar_analisis,
    agentes_proponer_seguimiento_connect,
)
from apps.agentes.models import ConfigAgente, EjecucionAgente, PrediccionAgente
from apps.agentes.services import AgenteError
from apps.connect.analytics import obtener_analiticas_connect
from apps.connect.mcp import (
    connect_analiticas,
    connect_gestionar_tarjeta,
    connect_listar_tarjetas,
)
from apps.connect.models import Perfil, Tarjeta, Toque
from apps.connect.qr import (
    construir_url_publica_perfil,
    generar_qr_png,
    generar_qr_svg,
    sanitizar_nombre_archivo_qr,
)
from apps.connect.services import ConnectError, asegurar_pipeline_predeterminado
from apps.connect.tasks import purgar_toques_antiguos
from apps.core import rls
from apps.core.models import CapabilityToken, Usuarios
from apps.crm.models import Etapa, Lead
from apps.gestion_aprobaciones.models import FlujoAprobacion, SolicitudAprobacion, TipoAprobacion

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _auth_client(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _mcp_token(empresa, scopes: list[str], *, creado_por=None) -> str:
    tok = CapabilityToken.objects.create(
        empresa=empresa,
        nombre="tok-connect-s10-s12",
        scopes=scopes,
        creado_por=creado_por,
    )
    return str(tok.token)


@pytest.fixture
def perfil_a(empresa_a, user_a) -> Perfil:
    perfil = Perfil(
        id_empresa=empresa_a,
        usuario=user_a,
        slug="vendedor-alpha",
        nombre_publico="Vendedor Alpha",
        cargo="Ejecutivo Comercial",
        email_publico="alpha@empresa.com",
        telefono_publico="+584141112233",
    )
    perfil.full_clean()
    perfil.save()
    return perfil


@pytest.fixture
def perfil_b(empresa_b, user_b) -> Perfil:
    perfil = Perfil(
        id_empresa=empresa_b,
        usuario=user_b,
        slug="vendedor-beta",
        nombre_publico="Vendedor Beta",
    )
    perfil.full_clean()
    perfil.save()
    return perfil


def _crear_lead(
    empresa,
    user,
    *,
    perfil=None,
    fuente=Lead.Fuente.NFC,
    nombre="Carlos",
    apellido="Ruiz",
    empresa_nombre="Distribuidora Centro",
    email="carlos@distcentro.com",
    telefono="+584141234567",
    mensaje="Solicito cotización urgente para pedido mensual.",
    consentimiento=True,
    etapa_tipo=Etapa.Tipo.ABIERTA,
    anonimizado=False,
    activo=True,
) -> Lead:
    pipeline = asegurar_pipeline_predeterminado(empresa)
    etapa = Etapa.objects.filter(id_empresa=empresa, pipeline=pipeline, tipo=etapa_tipo, activo=True).first()
    assert etapa is not None
    lead = Lead(
        id_empresa=empresa,
        nombre=nombre,
        apellido=apellido,
        empresa_nombre=empresa_nombre,
        email=email,
        telefono=telefono,
        mensaje=mensaje,
        fuente=fuente,
        perfil=perfil,
        pipeline=pipeline,
        etapa=etapa,
        propietario=user,
        consentimiento_aceptado=consentimiento,
        consentimiento_fecha=timezone.now() if consentimiento else None,
        consentimiento_texto="Autorizo tratamiento de datos." if consentimiento else "",
        anonimizado=anonimizado,
        activo=activo,
    )
    lead.full_clean()
    lead.save()
    return lead


# ══════════════════════════════════════════════════════════════════════════════
# S10 — Analíticas de Omni Connect y purga Celery Beat
# ══════════════════════════════════════════════════════════════════════════════


class TestConnectAnaliticasS10:
    def test_analiticas_agregadas_y_aislamiento_multitenant(
        self, empresa_a, empresa_b, user_a, user_b, perfil_a, perfil_b
    ):
        hoy = timezone.localdate()
        # 3 toques en Empresa A (2 IPs únicas + 1 sin ip_hash)
        t1 = Toque.objects.create(
            id_empresa=empresa_a,
            perfil=perfil_a,
            origen=Toque.Origen.NFC,
            dispositivo=Toque.Dispositivo.IOS,
            ip_hash="a" * 64,
        )
        Toque.objects.create(
            id_empresa=empresa_a,
            perfil=perfil_a,
            origen=Toque.Origen.QR,
            dispositivo=Toque.Dispositivo.ANDROID,
            ip_hash="a" * 64,
        )
        Toque.objects.create(
            id_empresa=empresa_a,
            perfil=perfil_a,
            origen=Toque.Origen.ENLACE,
            dispositivo=Toque.Dispositivo.ESCRITORIO,
            ip_hash="b" * 64,
        )
        Toque.objects.create(
            id_empresa=empresa_a,
            perfil=perfil_a,
            origen=Toque.Origen.QR,
            dispositivo=Toque.Dispositivo.OTRO,
            ip_hash="",
        )
        # Toque ajeno en Empresa B no debe aparecer nunca
        Toque.objects.create(
            id_empresa=empresa_b,
            perfil=perfil_b,
            origen=Toque.Origen.NFC,
            dispositivo=Toque.Dispositivo.IOS,
            ip_hash="c" * 64,
        )

        # 2 leads en Empresa A (1 abierto, 1 ganado) + 1 en Empresa B
        _crear_lead(empresa_a, user_a, perfil=perfil_a, fuente=Lead.Fuente.NFC, etapa_tipo=Etapa.Tipo.ABIERTA)
        _crear_lead(empresa_a, user_a, perfil=perfil_a, fuente=Lead.Fuente.QR, etapa_tipo=Etapa.Tipo.GANADA)
        _crear_lead(empresa_b, user_b, perfil=perfil_b, fuente=Lead.Fuente.NFC)

        # Toque fuera de rango (hace 60 días) no entra en ventana de 7 días
        Toque.objects.filter(pk=t1.pk).update(fecha_toque=timezone.now() - timedelta(days=60))

        client_a = _auth_client(user_a)
        resp = client_a.get("/api/connect/analiticas/?dias=7")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_toques"] == 3
        assert data["visitantes_unicos"] == 2
        assert data["total_leads"] == 2
        assert data["leads_convertidos"] == 1
        assert data["tasa_conversion_pct"] == "66.67"
        assert data["tasa_cierre_pct"] == "50.00"
        assert data["por_origen"] == {"NFC": 0, "QR": 2, "ENLACE": 1}
        assert data["por_dispositivo"] == {"IOS": 0, "ANDROID": 1, "ESCRITORIO": 1, "OTRO": 1}
        assert len(data["serie_diaria"]) >= 1
        assert data["serie_diaria"][-1]["fecha"] == hoy.isoformat()
        assert len(data["top_perfiles"]) == 1
        top = data["top_perfiles"][0]
        assert top["id_perfil"] == str(perfil_a.id_perfil)
        assert top["slug"] == perfil_a.slug
        assert top["toques"] == 3
        assert top["leads"] == 2
        assert "usuario_id" not in top
        assert "ip_hash" not in top

        # Filtro por perfil propio vs perfil ajeno
        resp_perfil = client_a.get(
            f"/api/connect/analiticas/?perfil_id={perfil_a.id_perfil}&desde={hoy.isoformat()}&hasta={hoy.isoformat()}"
        )
        assert resp_perfil.status_code == 200
        assert resp_perfil.json()["perfil_id"] == str(perfil_a.id_perfil)

        resp_ajeno = client_a.get(f"/api/connect/analiticas/?perfil_id={perfil_b.id_perfil}")
        assert resp_ajeno.status_code == 404

        # Empresa ajena -> 403
        assert client_a.get(f"/api/connect/analiticas/?empresa_id={empresa_b.pk}").status_code == 403
        # Anónimo -> 401
        assert APIClient().get("/api/connect/analiticas/").status_code == 401

    def test_analiticas_cero_toques_y_validaciones_rango(self, empresa_a, user_a):
        client_a = _auth_client(user_a)
        resp_cero = client_a.get("/api/connect/analiticas/?dias=999")
        assert resp_cero.status_code == 200
        body = resp_cero.json()
        assert body["total_toques"] == 0
        assert body["tasa_conversion_pct"] == "0.00"
        assert body["tasa_cierre_pct"] == "0.00"
        assert body["periodo"]["dias"] == 365

        # Validaciones de fechas, dias, UUIDs y NUL
        assert client_a.get("/api/connect/analiticas/?desde=2026-11-20&hasta=2026-11-10").status_code == 400
        assert client_a.get("/api/connect/analiticas/?desde=2026-99-99").status_code == 400
        assert client_a.get("/api/connect/analiticas/?desde=no-fecha").status_code == 400
        assert client_a.get("/api/connect/analiticas/?dias=abc").status_code == 400
        assert client_a.get("/api/connect/analiticas/?perfil_id=no-uuid").status_code == 400
        assert client_a.get("/api/connect/analiticas/?desde=2026-11-01%00").status_code == 400

        # Variantes solo desde / solo hasta y errores directos de servicio
        hoy = timezone.localdate()
        res_desde = obtener_analiticas_connect(empresa_a, desde=hoy - timedelta(days=5))
        assert res_desde["periodo"]["hasta"] == hoy.isoformat()
        res_hasta = obtener_analiticas_connect(empresa_a, hasta=hoy, dias=10)
        assert res_hasta["periodo"]["dias"] == 10

        with pytest.raises(ConnectError):
            obtener_analiticas_connect(empresa_a, dias=True)
        with pytest.raises(ConnectError):
            obtener_analiticas_connect(empresa_a, perfil_id="abc\x00")
        with pytest.raises(ConnectError):
            obtener_analiticas_connect(empresa_a, perfil_id="no-uuid")
        with pytest.raises(ConnectError):
            obtener_analiticas_connect(empresa_a, desde="2026-01-01\x00")

    def test_mcp_connect_analiticas(self, empresa_a, empresa_b, perfil_a):
        Toque.objects.create(
            id_empresa=empresa_a,
            perfil=perfil_a,
            origen=Toque.Origen.NFC,
            dispositivo=Toque.Dispositivo.IOS,
            ip_hash="d" * 64,
        )
        tok = _mcp_token(empresa_a, ["connect:read"])
        res = connect_analiticas(tok, empresa_id=str(empresa_a.pk), dias=30)
        assert res["total_toques"] == 1
        assert res["por_origen"]["NFC"] == 1

        res_err = connect_analiticas(tok, empresa_id=str(empresa_a.pk), desde="2026-12-10", hasta="2026-12-01")
        assert "error" in res_err

        with pytest.raises(PermissionError):
            connect_analiticas(tok, empresa_id=str(empresa_b.pk))

    @override_settings(RLS_ENABLED=True)
    def test_purgar_toques_antiguos_en_lotes_y_rls_fail_closed(
        self, empresa_a, empresa_b, perfil_a, perfil_b, rls_test_role
    ):
        with rls.rls_bypass():
            viejos_a = [
                Toque.objects.create(
                    id_empresa=empresa_a,
                    perfil=perfil_a,
                    origen=Toque.Origen.QR,
                    dispositivo=Toque.Dispositivo.ANDROID,
                    ip_hash=f"{i:064x}",
                )
                for i in range(5)
            ]
            reciente_a = Toque.objects.create(
                id_empresa=empresa_a,
                perfil=perfil_a,
                origen=Toque.Origen.NFC,
                dispositivo=Toque.Dispositivo.IOS,
                ip_hash="f" * 64,
            )
            viejo_b = Toque.objects.create(
                id_empresa=empresa_b,
                perfil=perfil_b,
                origen=Toque.Origen.ENLACE,
                dispositivo=Toque.Dispositivo.ESCRITORIO,
                ip_hash="e" * 64,
            )
            antiguo_dt = timezone.now() - timedelta(days=400)
            Toque.objects.filter(pk__in=[t.pk for t in viejos_a] + [viejo_b.pk]).update(fecha_toque=antiguo_dt)

        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            rls.apply_system_default()
            assert Toque.objects.count() == 0

            resultado = purgar_toques_antiguos.apply(kwargs={"dias_retencion": 365, "batch_size": 2}).get()
            assert resultado["toques_eliminados"] == 6
            assert resultado["errores"] == 0
            assert resultado["empresas_procesadas"] >= 2
            assert rls._get_current_context() == ("off", "")

            with rls.rls_bypass():
                assert Toque.objects.filter(pk=reciente_a.pk).exists()
                assert not Toque.objects.filter(pk=viejo_b.pk).exists()
                assert Toque.objects.filter(id_empresa=empresa_a).count() == 1
        finally:
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")
            rls.apply_system_default()


# ══════════════════════════════════════════════════════════════════════════════
# S11 — TarjetaViewSet + Generación QR SVG/PNG + MCP
# ══════════════════════════════════════════════════════════════════════════════


class TestConnectQrYTarjetasS11:
    def test_qr_svg_y_png_puro_sin_dependencias_nuevas(self):
        url_qr = construir_url_publica_perfil("Vendedor-Alpha", origen="QR")
        assert url_qr.endswith("/c/vendedor-alpha?origen=QR")

        url_nfc = construir_url_publica_perfil("vendedor-alpha", uid="04:a2:b3:c4:d5")
        assert url_nfc.endswith("/c/vendedor-alpha?uid=04A2B3C4D5")

        svg = generar_qr_svg(url_qr, scale=6, border=2)
        assert svg.startswith("<?xml version=")
        assert "<svg " in svg and "<path " in svg and "</svg>" in svg

        png = generar_qr_png(url_nfc, scale=4, border=2)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        # Verificar chunk IHDR (offset 8..33) y validez de stream zlib en IDAT
        ihdr_len, ihdr_type = struct.unpack(">I4s", png[8:16])
        assert ihdr_type == b"IHDR" and ihdr_len == 13
        width, height, bit_depth, color_type = struct.unpack(">IIBB", png[16:26])
        assert width == height and width > 80
        assert bit_depth == 8 and color_type == 0
        idat_offset = 8 + 12 + ihdr_len
        idat_len, idat_type = struct.unpack(">I4s", png[idat_offset : idat_offset + 8])
        assert idat_type == b"IDAT"
        raw = zlib.decompress(png[idat_offset + 8 : idat_offset + 8 + idat_len])
        assert len(raw) == height * (1 + width)

        assert sanitizar_nombre_archivo_qr("qr/../../bad\r\nname") == "qrbadname"
        assert sanitizar_nombre_archivo_qr("!!!") == "connect-qr"

        with pytest.raises(ConnectError):
            generar_qr_svg("")
        with pytest.raises(ConnectError):
            generar_qr_png("https://omni.link/c/x\x00")
        with pytest.raises(ConnectError):
            generar_qr_svg("x" * 3000)
        with pytest.raises(ConnectError):
            generar_qr_svg("https://omni.link/c/ok", scale=True)  # type: ignore[arg-type]
        with pytest.raises(ConnectError):
            construir_url_publica_perfil("admin")
        with pytest.raises(ConnectError):
            construir_url_publica_perfil("vendedor-alpha", uid="corto")

    def test_tarjeta_crud_ciclo_vida_qr_y_bloqueo_publico(
        self, empresa_a, empresa_b, user_a, user_b, perfil_a, perfil_b
    ):
        client_a = _auth_client(user_a)
        client_b = _auth_client(user_b)
        anon = APIClient()

        assert anon.get("/api/connect/tarjetas/").status_code == 401

        # Crear en inventario normalizando UID con dos puntos
        resp_create = client_a.post(
            "/api/connect/tarjetas/",
            {"uid_chip": "04:a1:b2:c3:d4:e5:f6", "tipo": "METAL", "notas": "Lote 1"},
            format="json",
        )
        assert resp_create.status_code == 201, resp_create.data
        tarjeta_data = resp_create.json()
        tarjeta_id = tarjeta_data["id_tarjeta"]
        assert tarjeta_data["uid_chip"] == "04A1B2C3D4E5F6"
        assert tarjeta_data["estado"] == "INVENTARIO"
        assert tarjeta_data["perfil"] is None

        # UID duplicado -> 400
        assert (
            client_a.post(
                "/api/connect/tarjetas/",
                {"uid_chip": "04A1B2C3D4E5F6", "tipo": "PVC"},
                format="json",
            ).status_code
            == 400
        )

        # No se puede activar ni descargar QR sin perfil asignado
        assert client_a.post(f"/api/connect/tarjetas/{tarjeta_id}/activar/", {}, format="json").status_code == 400
        assert client_a.get(f"/api/connect/tarjetas/{tarjeta_id}/qr/").status_code == 400

        # No se puede asignar perfil de Empresa B
        assert (
            client_a.post(
                f"/api/connect/tarjetas/{tarjeta_id}/asignar/",
                {"perfil_id": str(perfil_b.id_perfil), "activar": True},
                format="json",
            ).status_code
            == 400
        )

        # Asignar y activar sobre perfil propio
        resp_asig = client_a.post(
            f"/api/connect/tarjetas/{tarjeta_id}/asignar/",
            {"perfil_id": str(perfil_a.id_perfil), "activar": True},
            format="json",
        )
        assert resp_asig.status_code == 200
        assert resp_asig.json()["estado"] == "ACTIVA"
        assert resp_asig.json()["perfil"] == str(perfil_a.id_perfil)
        assert resp_asig.json()["fecha_activacion"] is not None

        # Acceso público por UID funciona mientras está ACTIVA
        resp_pub_ok = anon.get(f"/api/public/connect/{perfil_a.slug}/?uid=04A1B2C3D4E5F6")
        assert resp_pub_ok.status_code == 200

        # Descarga QR SVG y PNG de tarjeta y de perfil + mi-perfil
        resp_qr_svg = client_a.get(f"/api/connect/tarjetas/{tarjeta_id}/qr/?formato=svg")
        assert resp_qr_svg.status_code == 200
        assert resp_qr_svg["Content-Type"].startswith("image/svg+xml")
        assert b"<svg" in resp_qr_svg.content

        resp_qr_png = client_a.get(f"/api/connect/tarjetas/{tarjeta_id}/qr/?formato=png")
        assert resp_qr_png.status_code == 200
        assert resp_qr_png["Content-Type"] == "image/png"
        assert resp_qr_png.content[:8] == b"\x89PNG\r\n\x1a\n"

        assert client_a.get(f"/api/connect/tarjetas/{tarjeta_id}/qr/?formato=webp").status_code == 400

        resp_perf_qr = client_a.get(f"/api/connect/perfiles/{perfil_a.id_perfil}/qr/?formato=png")
        assert resp_perf_qr.status_code == 200 and resp_perf_qr.content[:8] == b"\x89PNG\r\n\x1a\n"

        resp_mi_qr = client_a.get("/api/connect/perfiles/mi-perfil/qr/?formato=svg")
        assert resp_mi_qr.status_code == 200 and b"<svg" in resp_mi_qr.content

        # Desactivar y reactivar
        resp_des = client_a.post(f"/api/connect/tarjetas/{tarjeta_id}/desactivar/", {}, format="json")
        assert resp_des.status_code == 200 and resp_des.json()["estado"] == "DESACTIVADA"
        assert anon.get(f"/api/public/connect/{perfil_a.slug}/?uid=04A1B2C3D4E5F6").status_code == 404

        resp_act = client_a.post(f"/api/connect/tarjetas/{tarjeta_id}/activar/", {}, format="json")
        assert resp_act.status_code == 200 and resp_act.json()["estado"] == "ACTIVA"

        # Marcar perdida revoca inmediatamente acceso público y bloquea reactivación/reasignación
        resp_perd = client_a.post(f"/api/connect/tarjetas/{tarjeta_id}/marcar-perdida/", {}, format="json")
        assert resp_perd.status_code == 200 and resp_perd.json()["estado"] == "PERDIDA"
        assert anon.get(f"/api/public/connect/{perfil_a.slug}/?uid=04A1B2C3D4E5F6").status_code == 404
        assert client_a.post(f"/api/connect/tarjetas/{tarjeta_id}/activar/", {}, format="json").status_code == 400
        assert client_a.post(f"/api/connect/tarjetas/{tarjeta_id}/desactivar/", {}, format="json").status_code == 400
        assert (
            client_a.post(
                f"/api/connect/tarjetas/{tarjeta_id}/asignar/",
                {"perfil_id": str(perfil_a.id_perfil)},
                format="json",
            ).status_code
            == 400
        )

        # Aislamiento cross-tenant: Empresa B no ve ni opera la tarjeta de Empresa A
        assert client_b.get(f"/api/connect/tarjetas/{tarjeta_id}/").status_code == 404
        assert (
            client_b.post(f"/api/connect/tarjetas/{tarjeta_id}/marcar-perdida/", {}, format="json").status_code == 404
        )
        assert client_b.get(f"/api/connect/tarjetas/{tarjeta_id}/qr/").status_code == 404

        # Inmutabilidad id_empresa, filtros, NUL, UUID inválido y soft delete
        assert (
            client_a.patch(
                f"/api/connect/tarjetas/{tarjeta_id}/",
                {"id_empresa": str(empresa_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.patch(f"/api/connect/tarjetas/{tarjeta_id}/", {"notas": "Revocada"}, format="json").status_code
            == 200
        )
        assert client_a.get("/api/connect/tarjetas/?estado=PERDIDA&tipo=METAL").status_code == 200
        assert client_a.get("/api/connect/tarjetas/no-uuid/").status_code == 400
        assert client_a.get("/api/connect/tarjetas/?search=bad%00val").status_code == 400
        assert client_a.post("/api/connect/tarjetas/", {"uid_chip": "AA11BB22\x00"}, format="json").status_code == 400

        assert client_a.delete(f"/api/connect/tarjetas/{tarjeta_id}/").status_code == 204
        resp_list_activas = client_a.get("/api/connect/tarjetas/")
        assert resp_list_activas.json()["count"] == 0
        resp_list_todas = client_a.get("/api/connect/tarjetas/?incluir_inactivos=true")
        assert resp_list_todas.json()["count"] == 1

    def test_mcp_tarjetas_listar_y_gestionar(self, empresa_a, empresa_b, perfil_a):
        tarjeta = Tarjeta(id_empresa=empresa_a, uid_chip="AABB11223344", tipo=Tarjeta.Tipo.PVC)
        tarjeta.full_clean()
        tarjeta.save()

        tok_rw = _mcp_token(empresa_a, ["connect:read", "connect:write"])
        listado = connect_listar_tarjetas(tok_rw, empresa_id=str(empresa_a.pk), estado="INVENTARIO")
        assert listado["total"] == 1
        assert listado["tarjetas"][0]["id_tarjeta"] == str(tarjeta.id_tarjeta)

        asig = connect_gestionar_tarjeta(
            tok_rw,
            tarjeta_id=str(tarjeta.id_tarjeta),
            accion="asignar",
            empresa_id=str(empresa_a.pk),
            perfil_id=str(perfil_a.id_perfil),
            activar=False,
        )
        assert asig["perfil_id"] == str(perfil_a.id_perfil)
        assert asig["estado"] == "INVENTARIO"

        act = connect_gestionar_tarjeta(tok_rw, tarjeta_id=str(tarjeta.id_tarjeta), accion="activar")
        assert act["estado"] == "ACTIVA"

        des = connect_gestionar_tarjeta(tok_rw, tarjeta_id=str(tarjeta.id_tarjeta), accion="desactivar")
        assert des["estado"] == "DESACTIVADA"

        perd = connect_gestionar_tarjeta(tok_rw, tarjeta_id=str(tarjeta.id_tarjeta), accion="marcar_perdida")
        assert perd["estado"] == "PERDIDA"

        assert "error" in connect_gestionar_tarjeta(tok_rw, tarjeta_id=str(tarjeta.id_tarjeta), accion="otra")
        assert "error" in connect_gestionar_tarjeta(tok_rw, tarjeta_id=str(tarjeta.id_tarjeta), accion="asignar")
        assert "error" in connect_gestionar_tarjeta(tok_rw, tarjeta_id=str(uuid.uuid4()), accion="activar")

        with pytest.raises(PermissionError):
            connect_listar_tarjetas(tok_rw, empresa_id=str(empresa_b.pk))


# ══════════════════════════════════════════════════════════════════════════════
# S12 — Agentes connect_calificador y connect_seguimiento + Aprobación obligatoria
# ══════════════════════════════════════════════════════════════════════════════


class TestAgentesConnectS12:
    def test_calificador_y_seguimiento_con_aprobacion_obligatoria(self, empresa_a, empresa_b, user_a, perfil_a):
        lead_caliente = _crear_lead(
            empresa_a,
            user_a,
            perfil=perfil_a,
            fuente=Lead.Fuente.NFC,
            nombre="Elena",
            empresa_nombre="Flota Norte C.A.",
            email="elena@flotanorte.com",
            telefono="+584145556677",
            mensaje="Gerente de compras, necesito cotización urgente para 200 unidades.",
            consentimiento=True,
        )

        # 1. Calificador determinístico persiste PrediccionAgente con full_clean
        res_cal = ejecutar_connect_calificador(empresa_a, lead_caliente.id_lead, usuario=user_a)
        assert res_cal["agente"] == AGENTE_CALIFICADOR_ID
        assert res_cal["prioridad"] == "ALTA"
        assert res_cal["score"] >= 70
        pred_cal = PrediccionAgente.objects.get(pk=res_cal["prediccion_id"])
        assert pred_cal.agente == AGENTE_CALIFICADOR_ID
        assert pred_cal.id_empresa_id == empresa_a.pk
        assert pred_cal.categoria_predicha == "ALTA"

        # 2. Seguimiento crea SolicitudAprobacion CONNECT_ENVIO_EXTERNO y NUNCA envía correo/mensaje
        with patch("django.core.mail.send_mail") as mock_mail:
            res_seg = ejecutar_connect_seguimiento(empresa_a, lead_caliente.id_lead, usuario=user_a)
        mock_mail.assert_not_called()

        assert res_seg["agente"] == AGENTE_SEGUIMIENTO_ID
        assert res_seg["accion"] == "ENVIO_EXTERNO"
        assert res_seg["canal"] == "EMAIL"
        assert res_seg["requiere_aprobacion"] is True
        assert res_seg["codigo_tipo_aprobacion"] == CODIGO_APROBACION_ENVIO_EXTERNO
        assert res_seg["enviado_directamente"] is False
        assert res_seg["solicitud_aprobacion_id"] is not None

        solicitud = SolicitudAprobacion.objects.select_related("id_tipo_aprobacion").get(
            pk=res_seg["solicitud_aprobacion_id"]
        )
        assert solicitud.id_tipo_aprobacion.codigo_tipo == CODIGO_APROBACION_ENVIO_EXTERNO
        assert solicitud.id_tipo_aprobacion.modulo_origen == "connect"
        assert solicitud.estado_solicitud == "PENDIENTE"
        assert str(solicitud.id_entidad_origen) == res_seg["prediccion_id"]
        assert solicitud.nombre_modelo_origen == MODELO_ORIGEN_PREDICCION

        # 3. Aislamiento: Empresa B no puede evaluar lead de Empresa A
        with pytest.raises(AgenteError):
            ejecutar_connect_calificador(empresa_b, lead_caliente.id_lead)
        with pytest.raises(AgenteError):
            ejecutar_connect_seguimiento(empresa_b, lead_caliente.id_lead)

    def test_seguimiento_flujo_personalizado_con_monto_minimo_aun_retiene_aprobacion(
        self, empresa_a, user_a, perfil_a
    ):
        tipo = TipoAprobacion.objects.create(
            id_empresa=empresa_a,
            codigo_tipo=CODIGO_APROBACION_ENVIO_EXTERNO,
            nombre_tipo="Envío Connect",
            modulo_origen="connect",
            activo=True,
        )
        FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            orden_etapa=1,
            nombre_etapa="Dirección",
            monto_minimo=Decimal("500.00"),
            activo=True,
        )
        lead = _crear_lead(
            empresa_a,
            user_a,
            perfil=perfil_a,
            email="",
            telefono="+584121234567",
            mensaje="Hola, seguimos en contacto por WhatsApp.",
            consentimiento=True,
        )
        res = ejecutar_connect_seguimiento(empresa_a, lead.id_lead, usuario=user_a)
        assert res["accion"] == "ENVIO_EXTERNO"
        assert res["canal"] == "WHATSAPP"
        assert res["solicitud_aprobacion_id"] is not None
        sol = SolicitudAprobacion.objects.get(pk=res["solicitud_aprobacion_id"])
        assert sol.estado_solicitud == "PENDIENTE"

    def test_seguimiento_bloquea_anonimizado_sin_consentimiento_y_cerrado(self, empresa_a, user_a, perfil_a):
        lead_anon = _crear_lead(
            empresa_a,
            user_a,
            perfil=perfil_a,
            fuente=Lead.Fuente.MANUAL,
            nombre="Anonimizado",
            email="",
            telefono="",
            consentimiento=False,
            anonimizado=True,
            activo=False,
        )
        lead_sin_optin = _crear_lead(
            empresa_a,
            user_a,
            perfil=perfil_a,
            fuente=Lead.Fuente.MANUAL,
            email="sinoptin@empresa.com",
            telefono="+584141110000",
            consentimiento=False,
        )
        lead_ganado = _crear_lead(
            empresa_a,
            user_a,
            perfil=perfil_a,
            fuente=Lead.Fuente.NFC,
            etapa_tipo=Etapa.Tipo.GANADA,
            consentimiento=True,
        )

        gw_mock = MagicMock()
        gw_mock.disponible.return_value = True

        for lead_bloqueado in (lead_anon, lead_sin_optin, lead_ganado):
            res = ejecutar_connect_seguimiento(empresa_a, lead_bloqueado.id_lead, usuario=user_a, gateway=gw_mock)
            assert res["accion"] == "NO_CONTACTAR"
            assert res["canal"] == "NINGUNO"
            assert res["requiere_aprobacion"] is False
            assert res["solicitud_aprobacion_id"] is None

        # El gateway LLM nunca debe llamarse para casos NO_CONTACTAR
        gw_mock.generate.assert_not_called()
        assert SolicitudAprobacion.objects.count() == 0

    def test_agentes_connect_con_llm_gateway_y_fallback_y_config_inactiva(self, empresa_a, user_a, perfil_a):
        lead = _crear_lead(
            empresa_a,
            user_a,
            perfil=perfil_a,
            mensaje="Quisiera información del catálogo de productos.",
        )

        # LLM válido refina calificador y seguimiento
        gw_ok = MagicMock()
        gw_ok.disponible.return_value = True
        gw_ok.generate.side_effect = [
            SimpleNamespace(
                text=json.dumps(
                    {
                        "prioridad": "ALTA",
                        "score": 85,
                        "confianza": 0.91,
                        "siguiente_actividad": "LLAMADA",
                        "razonamiento": "Alta intención detectada por gateway.",
                    }
                ),
                model="modelo-test-gateway",
            ),
            SimpleNamespace(
                text=json.dumps(
                    {
                        "asunto": "Catálogo solicitado",
                        "borrador_mensaje": "Hola, adjuntamos el catálogo solicitado para su revisión.",
                        "razonamiento": "Borrador personalizado por gateway.",
                    }
                ),
                model="modelo-test-gateway",
            ),
        ]
        res_c = ejecutar_connect_calificador(empresa_a, lead.id_lead, usuario=user_a, gateway=gw_ok)
        assert res_c["prioridad"] == "ALTA" and res_c["modelo_llm"] == "modelo-test-gateway"

        res_s = ejecutar_connect_seguimiento(empresa_a, lead.id_lead, usuario=user_a, gateway=gw_ok)
        assert res_s["asunto"] == "Catálogo solicitado"
        assert res_s["solicitud_aprobacion_id"] is not None

        # Fallo de gateway cae limpiamente a fallback determinístico
        gw_err = MagicMock()
        gw_err.disponible.return_value = True
        gw_err.generate.side_effect = TimeoutError("timeout gateway")
        res_c_fb = ejecutar_connect_calificador(empresa_a, lead.id_lead, usuario=user_a, gateway=gw_err)
        assert res_c_fb["modelo_llm"].startswith("fallback-error:")
        res_s_fb = ejecutar_connect_seguimiento(empresa_a, lead.id_lead, usuario=user_a, gateway=gw_err)
        assert res_s_fb["modelo_llm"].startswith("fallback-error:")

        # ConfigAgente desactivada rechaza ejecución
        ConfigAgente.objects.create(id_empresa=empresa_a, agente=AGENTE_CALIFICADOR_ID, activo=False)
        with pytest.raises(AgenteError, match="desactivado"):
            ejecutar_connect_calificador(empresa_a, lead.id_lead, usuario=user_a)

    def test_rest_celery_y_mcp_agentes_connect(
        self, empresa_a, empresa_b, user_a, user_b, perfil_a, django_capture_on_commit_callbacks
    ):
        lead = _crear_lead(
            empresa_a,
            user_a,
            perfil=perfil_a,
            mensaje="Por favor enviar cotización a mi correo.",
        )
        client_a = _auth_client(user_a)
        client_b = _auth_client(user_b)

        # Cross-tenant -> 404
        assert (
            client_b.post(
                "/api/agentes/predicciones/calificar-lead-connect/",
                {"lead_id": str(lead.id_lead)},
                format="json",
            ).status_code
            == 404
        )
        assert (
            client_b.post(
                "/api/agentes/predicciones/proponer-seguimiento-connect/",
                {"lead_id": str(lead.id_lead)},
                format="json",
            ).status_code
            == 404
        )

        # Usuario sin empresa -> 403
        sin_emp = Usuarios.objects.create_user(username="sin_emp_connect_ag", password="x", email="se@test.com")
        assert (
            _auth_client(sin_emp)
            .post("/api/agentes/predicciones/calificar-lead-connect/", {"lead_id": str(lead.id_lead)}, format="json")
            .status_code
            == 403
        )

        # REST 202 + ejecución Celery eager -> completado
        with django_capture_on_commit_callbacks(execute=True):
            r1 = client_a.post(
                "/api/agentes/predicciones/calificar-lead-connect/",
                {"lead_id": str(lead.id_lead)},
                format="json",
            )
        assert r1.status_code == 202
        ej1 = EjecucionAgente.objects.get(pk=r1.json()["id_ejecucion"])
        assert ej1.estado == "completado"
        assert ej1.resultado["prioridad"] in ("ALTA", "MEDIA", "BAJA")

        with django_capture_on_commit_callbacks(execute=True):
            r2 = client_a.post(
                "/api/agentes/predicciones/proponer-seguimiento-connect/",
                {"lead_id": str(lead.id_lead)},
                format="json",
            )
        assert r2.status_code == 202
        ej2 = EjecucionAgente.objects.get(pk=r2.json()["id_ejecucion"])
        assert ej2.estado == "completado"
        assert ej2.resultado["solicitud_aprobacion_id"] is not None
        assert ej2.resultado["enviado_directamente"] is False

        # sugerencias-activas formatea títulos y url_accion correctamente
        resp_sug = client_a.get("/api/agentes/predicciones/sugerencias-activas/")
        assert resp_sug.status_code == 200
        agentes_en_sug = {s["agente"]: s for s in resp_sug.json()["sugerencias"]}
        assert AGENTE_CALIFICADOR_ID in agentes_en_sug
        assert AGENTE_SEGUIMIENTO_ID in agentes_en_sug
        assert agentes_en_sug[AGENTE_CALIFICADOR_ID]["url_accion"] == "/crm/pipeline"
        assert agentes_en_sug[AGENTE_SEGUIMIENTO_ID]["url_accion"] == "/aprobaciones/solicitudes"

        # MCP tools directas y vía agentes_disparar_analisis
        tok_w = _mcp_token(empresa_a, ["agentes:write"], creado_por=user_a)
        mcp_cal = agentes_calificar_lead_connect(tok_w, str(empresa_a.pk), str(lead.id_lead))
        assert mcp_cal["agente"] == AGENTE_CALIFICADOR_ID
        assert "prediccion_id" in mcp_cal

        mcp_seg = agentes_proponer_seguimiento_connect(tok_w, str(empresa_a.pk), str(lead.id_lead))
        assert mcp_seg["agente"] == AGENTE_SEGUIMIENTO_ID
        assert mcp_seg["solicitud_aprobacion_id"] is not None
        assert mcp_seg["enviado_directamente"] is False

        with django_capture_on_commit_callbacks(execute=True):
            mcp_disp = agentes_disparar_analisis(
                tok_w,
                str(empresa_a.pk),
                agente=AGENTE_CALIFICADOR_ID,
                lead_id=str(lead.id_lead),
            )
        assert mcp_disp["agente"] == AGENTE_CALIFICADOR_ID

        assert "error" in agentes_disparar_analisis(tok_w, str(empresa_a.pk), agente=AGENTE_CALIFICADOR_ID)
        assert "error" in agentes_calificar_lead_connect(tok_w, str(empresa_a.pk), "no-uuid")
        assert "error" in agentes_proponer_seguimiento_connect(tok_w, str(empresa_a.pk), str(uuid.uuid4()))

        with pytest.raises(PermissionError):
            agentes_calificar_lead_connect(tok_w, str(empresa_b.pk), str(lead.id_lead))


@pytest.mark.django_db
class TestCoberturaBordesS10S12:
    """Casos de borde, validaciones de error y cobertura integral de S10/S11/S12."""

    def test_bordes_analytics_qr_renderers_y_purga(self, empresa_a, user_a, perfil_a):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from apps.connect.analytics import _normalizar_dias, _parse_fecha_iso, _parse_perfil_id
        from apps.connect.views import PngRenderer, SvgRenderer

        # Renderers SVG/PNG para bytes, str y fallback
        assert SvgRenderer().render(b"<svg/>") == b"<svg/>"
        assert SvgRenderer().render("<svg/>") == b"<svg/>"
        assert SvgRenderer().render(123) == b"123"
        assert PngRenderer().render(b"\x89PNG") == b"\x89PNG"
        assert PngRenderer().render("abc") == b"abc"

        # Helpers puros de analytics
        ahora = timezone.now()
        assert _parse_fecha_iso(ahora, "desde") == ahora.date()
        assert _parse_fecha_iso("   ", "desde") is None
        assert _normalizar_dias(None) == 30
        assert _normalizar_dias("   ") == 30
        with pytest.raises(ConnectError):
            _normalizar_dias("7\x00")
        assert _parse_perfil_id(perfil_a.pk) == perfil_a.pk
        assert _parse_perfil_id("   ") is None

        # Helpers de QR con NUL y sin query
        with pytest.raises(ConnectError):
            construir_url_publica_perfil("ana\x00bad")
        with pytest.raises(ConnectError):
            construir_url_publica_perfil(perfil_a.slug, uid="04AA\x00BB")
        assert construir_url_publica_perfil(perfil_a.slug, origen="OTRO").endswith(f"/c/{perfil_a.slug}")

        # ConnectAnaliticasView maneja DjangoValidationError
        client_a = _auth_client(user_a)
        with patch("apps.connect.views.obtener_analiticas_connect", side_effect=DjangoValidationError("invalido")):
            assert client_a.get("/api/connect/analiticas/").status_code == 400

        # Purga tolera fallo aislado en una empresa sin abortar el resto
        with patch("apps.connect.models.Toque.objects.filter", side_effect=RuntimeError("fallo aislado")):
            res_purga = purgar_toques_antiguos(dias_retencion=365, batch_size=10)
        assert res_purga["errores"] >= 1

    def test_bordes_tarjeta_viewset_qr_y_mcp(self, empresa_a, empresa_b, user_a, user_b, perfil_a, perfil_b):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from apps.connect.views import TarjetaViewSet

        # swagger_fake_view
        vs = TarjetaViewSet()
        vs.swagger_fake_view = True
        assert vs.get_queryset().count() == 0

        client_a = _auth_client(user_a)
        sin_emp = Usuarios.objects.create_user(username="sin_emp_tarjeta_s11", password="x", email="st@test.com")
        client_sin = _auth_client(sin_emp)

        # POST sin empresa -> 403
        assert client_sin.post("/api/connect/tarjetas/", {"uid_chip": "0499887766"}, format="json").status_code == 403

        # POST estado ACTIVA sin perfil -> 400
        assert (
            client_a.post(
                "/api/connect/tarjetas/",
                {"uid_chip": "0499887766", "estado": "ACTIVA"},
                format="json",
            ).status_code
            == 400
        )

        # POST perfil cross-tenant -> 400
        assert (
            client_a.post(
                "/api/connect/tarjetas/",
                {"uid_chip": "0499887767", "perfil": str(perfil_b.pk)},
                format="json",
            ).status_code
            == 400
        )

        # Crear tarjeta válida y probar duplicado -> 400
        r_ok = client_a.post(
            "/api/connect/tarjetas/",
            {"uid_chip": "04ABCD1234", "tipo": "PVC", "perfil": str(perfil_a.pk)},
            format="json",
        )
        assert r_ok.status_code == 201
        tid = r_ok.json()["id_tarjeta"]
        assert client_a.post("/api/connect/tarjetas/", {"uid_chip": "04ABCD1234"}, format="json").status_code == 400

        # Filtros empresa_id, perfil_id y tipo
        r_filt = client_a.get(f"/api/connect/tarjetas/?empresa_id={empresa_a.pk}&perfil_id={perfil_a.pk}&tipo=PVC")
        assert r_filt.status_code == 200
        assert len(r_filt.json()["results"]) >= 1

        # PATCH con perfil inactivo -> 400; PATCH cambiando id_empresa -> 400
        user_a2 = Usuarios.objects.create_user(username="inactivo_perf_u", password="x", email="ip@test.com")
        user_a2.empresas.add(empresa_a)
        perfil_inactivo = Perfil.objects.create(
            id_empresa=empresa_a,
            usuario=user_a2,
            slug="perfil-inactivo-s11",
            nombre_publico="Inactivo",
            activo=False,
        )
        assert (
            client_a.patch(
                f"/api/connect/tarjetas/{tid}/", {"perfil": str(perfil_inactivo.pk)}, format="json"
            ).status_code
            == 400
        )
        user_a.empresas.add(empresa_b)
        assert (
            client_a.patch(
                f"/api/connect/tarjetas/{tid}/", {"id_empresa": str(empresa_b.pk)}, format="json"
            ).status_code
            == 400
        )
        user_a.empresas.remove(empresa_b)

        # QR mi-perfil sin perfil (404) y error de generación en perfil/mi-perfil/tarjeta (400)
        client_a2 = _auth_client(user_a2)
        perfil_inactivo.delete()
        assert client_a2.get("/api/connect/perfiles/mi-perfil/qr/").status_code == 404

        with patch("apps.connect.views.generar_qr_svg", side_effect=ConnectError("error qr")):
            assert client_a.get(f"/api/connect/perfiles/{perfil_a.pk}/qr/").status_code == 400
            assert client_a.get("/api/connect/perfiles/mi-perfil/qr/").status_code == 400
            assert client_a.get(f"/api/connect/tarjetas/{tid}/qr/").status_code == 400

        # Acciones con DjangoValidationError / ConnectError
        with patch("apps.connect.views.asignar_tarjeta", side_effect=DjangoValidationError("err")):
            assert (
                client_a.post(
                    f"/api/connect/tarjetas/{tid}/asignar/", {"perfil_id": str(perfil_a.pk)}, format="json"
                ).status_code
                == 400
            )
        with patch("apps.connect.views.activar_tarjeta", side_effect=DjangoValidationError("err")):
            assert client_a.post(f"/api/connect/tarjetas/{tid}/activar/").status_code == 400
        with patch("apps.connect.views.desactivar_tarjeta", side_effect=DjangoValidationError("err")):
            assert client_a.post(f"/api/connect/tarjetas/{tid}/desactivar/").status_code == 400
        with patch("apps.connect.views.marcar_tarjeta_perdida", side_effect=ConnectError("err")):
            assert client_a.post(f"/api/connect/tarjetas/{tid}/marcar-perdida/").status_code == 400
        with patch("apps.connect.views.marcar_tarjeta_perdida", side_effect=DjangoValidationError("err")):
            assert client_a.post(f"/api/connect/tarjetas/{tid}/marcar-perdida/").status_code == 400

        # DELETE soft-delete pasa tarjeta a DESACTIVADA y activo=False
        assert client_a.delete(f"/api/connect/tarjetas/{tid}/").status_code == 204
        tarjeta_del = Tarjeta.objects.get(pk=tid)
        assert tarjeta_del.activo is False
        assert tarjeta_del.estado == Tarjeta.Estado.DESACTIVADA

        # MCP Connect bordes (perfil_id en analiticas/listar, limite bool, acción con ConnectError)
        tok_rw = _mcp_token(empresa_a, ["connect:read", "connect:write"], creado_por=user_a)
        res_an = connect_analiticas(tok_rw, empresa_id=str(empresa_a.pk), perfil_id=str(perfil_a.pk))
        assert res_an["perfil_id"] == str(perfil_a.pk)

        res_list = connect_listar_tarjetas(
            tok_rw,
            empresa_id=str(empresa_a.pk),
            perfil_id=str(perfil_a.pk),
            incluir_inactivos=True,
        )
        assert res_list["total"] >= 1
        with pytest.raises(ValueError, match="limite"):
            connect_listar_tarjetas(tok_rw, limite=True)

        t_sin_perfil = Tarjeta.objects.create(id_empresa=empresa_a, uid_chip="0477665544", tipo=Tarjeta.Tipo.PVC)
        res_err = connect_gestionar_tarjeta(tok_rw, str(t_sin_perfil.pk), accion="activar")
        assert "error" in res_err

    def test_bordes_agentes_connect_mcp_views_y_tasks(self, empresa_a, user_a, perfil_a):
        from apps.agentes.connect_agents import (
            _config_permite_llm,
            _entero_seguro,
            _refinar_seguimiento_con_llm,
            _tiene_email_valido,
            calificar_lead_deterministico,
            proponer_seguimiento_deterministico,
        )
        from apps.agentes.tasks import ejecutar_analisis_agente

        # Helpers puros + ramas de scoring y seguimiento
        assert _tiene_email_valido("a@sinpunto") == (False, False)
        assert _entero_seguro(True, 7) == 7
        assert _entero_seguro("no-num", 9) == 9

        cal_baja = calificar_lead_deterministico(
            {
                "cargo": "Analista",
                "mensaje": "solo prueba interna",
                "fuente": "IMPORTACION",
                "dias_desde_captura": 45,
                "total_toques": 3,
                "tiene_contacto_previo": True,
                "total_actividades": 2,
            }
        )
        assert cal_baja["prioridad"] == "BAJA"

        cal_sem = calificar_lead_deterministico({"email": "a@corp.com", "dias_desde_captura": 5, "mensaje": "info"})
        assert "captura_semana" in cal_sem["factores"]

        seg_sin_datos = proponer_seguimiento_deterministico(
            {"nombre": "Luis", "consentimiento_aceptado": True, "email": "", "telefono": ""}
        )
        assert seg_sin_datos["accion"] == "TAREA_INTERNA" and seg_sin_datos["canal"] == "NINGUNO"

        seg_llamada = proponer_seguimiento_deterministico(
            {
                "nombre": "Luis",
                "empresa_nombre": "Acme",
                "consentimiento_aceptado": True,
                "telefono": "+584121234567",
                "mensaje": "Por favor llamar hoy",
            }
        )
        assert seg_llamada["accion"] == "TAREA_INTERNA" and seg_llamada["canal"] == "LLAMADA"

        # Guardrail directo en _refinar_seguimiento_con_llm
        base_no = {"accion": "NO_CONTACTAR", "canal": "NINGUNO"}
        assert _refinar_seguimiento_con_llm(empresa_a, {}, base_no, MagicMock()) == base_no

        # _config_permite_llm con ConfigAgente inactivo vs activo con usar_llm
        cfg = ConfigAgente.objects.create(
            id_empresa=empresa_a,
            agente=AGENTE_SEGUIMIENTO_ID,
            activo=False,
            config_extra={"usar_llm": True},
        )
        assert _config_permite_llm(empresa_a, AGENTE_SEGUIMIENTO_ID) is False
        cfg.activo = True
        cfg.save(update_fields=["activo"])
        assert _config_permite_llm(empresa_a, AGENTE_SEGUIMIENTO_ID) is True

        # UUID inválido en servicios
        with pytest.raises(AgenteError, match="inválido"):
            ejecutar_connect_calificador(empresa_a, "no-uuid", usuario=user_a)
        with pytest.raises(AgenteError, match="inválido"):
            ejecutar_connect_seguimiento(empresa_a, "no-uuid", usuario=user_a)

        # Lead sin perfil (usa propietario) + LLM devolviendo prioridad inválida -> fallback prioridad
        lead_sin_perfil = _crear_lead(
            empresa_a,
            user_a,
            perfil=None,
            fuente=Lead.Fuente.MANUAL,
            email="cliente@empresa.com",
            mensaje="Enviar presupuesto por correo por favor",
            consentimiento=True,
        )
        gw_inv = MagicMock()
        gw_inv.disponible.return_value = True
        gw_inv.generate.return_value = SimpleNamespace(
            text=json.dumps({"prioridad": "INVALIDA", "score": 72, "confianza": 0.9, "siguiente_actividad": "CORREO"}),
            model="test-gw",
        )
        res_inv = ejecutar_connect_calificador(empresa_a, lead_sin_perfil.id_lead, usuario=user_a, gateway=gw_inv)
        assert res_inv["prioridad"] in ("ALTA", "MEDIA", "BAJA")

        # TipoAprobacion preexistente inactivo se reactiva automáticamente al proponer envío externo
        TipoAprobacion.objects.create(
            id_empresa=empresa_a,
            codigo_tipo=CODIGO_APROBACION_ENVIO_EXTERNO,
            nombre_tipo="Old",
            modulo_origen="otro",
            activo=False,
        )
        res_seg = ejecutar_connect_seguimiento(empresa_a, lead_sin_perfil.id_lead, usuario=user_a)
        assert res_seg["solicitud_aprobacion_id"] is not None
        tipo_act = TipoAprobacion.objects.get(id_empresa=empresa_a, codigo_tipo=CODIGO_APROBACION_ENVIO_EXTERNO)
        assert tipo_act.activo is True and tipo_act.modulo_origen == "connect"

        # REST proponer-seguimiento sin empresa -> 403
        sin_emp = Usuarios.objects.create_user(username="sin_emp_seg_s12", password="x", email="ss@test.com")
        assert (
            _auth_client(sin_emp)
            .post(
                "/api/agentes/predicciones/proponer-seguimiento-connect/",
                {"lead_id": str(lead_sin_perfil.id_lead)},
                format="json",
            )
            .status_code
            == 403
        )

        # MCP errores (lead_id inválido y lead no encontrado)
        tok_w = _mcp_token(empresa_a, ["agentes:write"], creado_por=user_a)
        assert "error" in agentes_disparar_analisis(
            tok_w, str(empresa_a.pk), agente=AGENTE_CALIFICADOR_ID, lead_id="bad"
        )
        assert "error" in agentes_disparar_analisis(
            tok_w, str(empresa_a.pk), agente=AGENTE_CALIFICADOR_ID, lead_id=str(uuid.uuid4())
        )
        assert "error" in agentes_calificar_lead_connect(tok_w, str(empresa_a.pk), str(uuid.uuid4()))
        assert "error" in agentes_proponer_seguimiento_connect(tok_w, str(empresa_a.pk), "bad-uuid")

        # Celery task maneja Lead.DoesNotExist y AgenteError limpiamente (estado=fallido)
        ej_missing = EjecucionAgente.objects.create(
            id_empresa=empresa_a,
            agente=AGENTE_CALIFICADOR_ID,
            estado="pendiente",
            parametros={"lead_id": str(uuid.uuid4())},
            iniciado_por=user_a,
        )
        with patch("apps.agentes.connect_agents.ejecutar_connect_calificador", side_effect=Lead.DoesNotExist):
            ejecutar_analisis_agente(str(ej_missing.pk), str(empresa_a.pk))
        ej_missing.refresh_from_db()
        assert ej_missing.estado == "fallido"
        assert "lead" in ej_missing.mensaje_error.lower()

        ej_err = EjecucionAgente.objects.create(
            id_empresa=empresa_a,
            agente=AGENTE_SEGUIMIENTO_ID,
            estado="pendiente",
            parametros={"lead_id": str(uuid.uuid4())},
            iniciado_por=user_a,
        )
        ejecutar_analisis_agente(str(ej_err.pk), str(empresa_a.pk))
        ej_err.refresh_from_db()
        assert ej_err.estado == "fallido"
        assert "no encontrado" in ej_err.mensaje_error.lower()
