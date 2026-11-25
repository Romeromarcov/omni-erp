"""Tests de integración Plan 09 Ola 6B-1: Chatter + WhatsApp Business y 5 Agentes IA Operativos."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone

pytestmark = [pytest.mark.django_db]


def _crear_usuario_empresa(empresa, *, staff: bool = False):
    from apps.core.models import Usuarios

    u = Usuarios.objects.create_user(
        username=f"usr_{uuid.uuid4().hex[:6]}",
        email=f"usr_{uuid.uuid4().hex[:6]}@omni.test",
        password="TestPass123!@#",
        is_staff=staff,
    )
    u.empresas.add(empresa)
    return u


def _crear_cap_token(empresa, user, scopes: list[str]):
    from apps.core.models import CapabilityToken

    tok = CapabilityToken.objects.create(
        nombre=f"tok_{uuid.uuid4().hex[:6]}",
        empresa=empresa,
        creado_por=user,
        scopes=scopes,
    )
    return str(tok.token)


def _setup_datos_operativos(empresa, moneda_usd, metodo_efectivo):
    from apps.almacenes.models import Almacen
    from apps.core.models import Contacto
    from apps.crm.models import Cliente
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    from apps.cuentas_por_pagar.models import CuentaPorPagar
    from apps.despacho.models import Conductor, Despacho, ParadaEntrega, RutaDespacho
    from apps.finanzas.models import Moneda, Pago, TasaCambio
    from apps.inventario.models import CategoriaProducto, Producto, StockActual, UnidadMedida
    from apps.proveedores.models import Proveedor
    from apps.ventas.models import NotaVenta, PagoPortalCliente

    user = _crear_usuario_empresa(empresa)
    moneda_ves, _ = Moneda.objects.get_or_create(
        codigo_iso="VES", defaults={"nombre": "Bolívar", "simbolo": "Bs.", "es_generica": True, "es_publica": True}
    )
    empresa.id_moneda_base = moneda_usd
    empresa.id_moneda_pais = moneda_ves
    empresa.save(update_fields=["id_moneda_base", "id_moneda_pais"])
    TasaCambio.objects.create(
        id_empresa=empresa,
        id_moneda_origen=moneda_usd,
        id_moneda_destino=moneda_ves,
        fecha_tasa=timezone.localdate(),
        valor_tasa=Decimal("45.0000"),
        tipo_tasa="OFICIAL_BCV",
    )

    contacto = Contacto.objects.create(
        id_empresa=empresa, nombre="Cliente Operativo CA", rif=f"J-{uuid.uuid4().int % 90000000 + 10000000}"
    )
    cliente = Cliente.objects.create(
        id_empresa=empresa,
        razon_social="Cliente Operativo CA",
        rif=contacto.rif,
        telefono="+584141234567",
        email="op@omni.test",
        contacto=contacto,
    )
    CuentaPorCobrar.objects.create(
        empresa=empresa,
        cliente=cliente,
        monto=Decimal("250.00"),
        fecha_emision=timezone.localdate() - timedelta(days=30),
        fecha_vencimiento=timezone.localdate() - timedelta(days=10),
        estado="vencida",
    )
    PagoPortalCliente.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        monto=Decimal("250.00"),
        id_moneda=moneda_usd,
        id_metodo_pago=metodo_efectivo,
        referencia="ZELLE-9901",
    )

    prov = Proveedor.objects.create(
        id_empresa=empresa,
        razon_social="Proveedor Mayor CA",
        rif=f"J-{uuid.uuid4().int % 90000000 + 10000000}",
    )
    CuentaPorPagar.objects.create(
        id_empresa=empresa,
        id_proveedor=prov,
        monto_total=Decimal("100.00"),
        monto_pendiente=Decimal("100.00"),
        fecha_emision=timezone.localdate(),
        fecha_vencimiento=timezone.localdate() + timedelta(days=15),
        estado="PENDIENTE",
    )
    Pago.objects.create(
        id_empresa=empresa,
        id_contacto=contacto,
        tipo_operacion="INGRESO",
        tipo_documento="CXC",
        fecha_pago=timezone.now(),
        monto=Decimal("80.00"),
        id_moneda=moneda_usd,
        id_metodo_pago=metodo_efectivo,
        referencia="PAG-01",
    )

    um = UnidadMedida.objects.create(id_empresa=empresa, nombre="Unidad", abreviatura="UND", tipo="CANTIDAD")
    cat = CategoriaProducto.objects.create(id_empresa=empresa, nombre_categoria="Lubricantes")
    prod = Producto.objects.create(
        id_empresa=empresa,
        nombre_producto="Filtro Aceite",
        sku=f"FLT-{uuid.uuid4().hex[:6]}",
        id_categoria=cat,
        id_unidad_medida_base=um,
        id_moneda_precio=moneda_usd,
        costo_reposicion_usd=Decimal("6.5000"),
    )
    alm = Almacen.objects.create(id_empresa=empresa, nombre_almacen="CD", codigo_almacen=f"CD-{uuid.uuid4().hex[:4]}")
    StockActual.objects.create(
        id_empresa=empresa,
        id_producto=prod,
        id_almacen=alm,
        cantidad_disponible=Decimal("2.0000"),
        cantidad_minima=Decimal("20.0000"),
    )

    nota = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        numero_nota=f"NV-{uuid.uuid4().hex[:6]}",
        fecha_nota=timezone.localdate(),
        estado="ENTREGADA",
        ambito="GERENCIAL",
    )
    desp = Despacho.objects.create(
        id_empresa=empresa,
        numero_despacho=f"DSP-{uuid.uuid4().hex[:6]}",
        id_nota_venta=nota,
        fecha_despacho=timezone.now(),
        id_almacen_origen=alm,
        direccion_destino="Altamira",
        estado_despacho="EN_RUTA",
    )
    cond = Conductor.objects.create(
        id_empresa=empresa, nombre_completo="Chofer Demo", cedula=f"V-{uuid.uuid4().int % 90000000 + 10000000}"
    )
    ruta = RutaDespacho.objects.create(
        id_empresa=empresa,
        codigo=f"RUT-{uuid.uuid4().hex[:5]}",
        fecha_ruta=timezone.localdate(),
        id_almacen_origen=alm,
        id_conductor=cond,
        estado="EN_CURSO",
    )
    ParadaEntrega.objects.create(
        id_empresa=empresa,
        id_ruta=ruta,
        id_despacho=desp,
        secuencia=1,
        direccion_texto="Altamira",
        estado="EN_CAMINO",
        eta_estimada=timezone.now() - timedelta(minutes=30),
    )
    return {"user": user, "cliente": cliente, "nota": nota, "desp": desp}


class TestChatterWhatsAppFase81:
    def test_rls_aislamiento_chatter_y_whatsapp_simulado_cloud(self, rls_test_role, empresa_a, empresa_b, monkeypatch):
        from rest_framework.test import APIClient

        from apps.notificaciones.mcp import (
            notificaciones_enviar_whatsapp_documento,
            notificaciones_listar_chatter_documento,
        )
        from apps.notificaciones.models import MensajeChatterDocumento
        from apps.notificaciones.whatsapp import construir_mensaje_plantilla, normalizar_telefono_e164

        with connection.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='notificaciones_chatter_documento'"
            )
            assert cur.fetchone()[0] >= 1

        usr_a = _crear_usuario_empresa(empresa_a)
        usr_b = _crear_usuario_empresa(empresa_b)
        doc_id = uuid.uuid4()

        with pytest.raises(ValidationError):
            MensajeChatterDocumento(
                id_empresa=empresa_a,
                tipo_documento="COTIZACION",
                documento_id=doc_id,
                autor=usr_b,
                cuerpo="Cross-tenant author",
            ).clean()

        # Plantillas WhatsApp y validación teléfono
        assert normalizar_telefono_e164("0414-123 4567") == "+04141234567"
        assert "Cotización #COT-1" in construir_mensaje_plantilla(
            "cotizacion", {"numero": "COT-1", "cliente": "Beta", "monto": "100", "moneda": "USD"}
        )
        assert "saldo pendiente" in construir_mensaje_plantilla(
            "cobranza", {"cliente": "Beta", "numero": "F-1", "saldo": "50"}
        )
        assert "EN_RUTA" in construir_mensaje_plantilla(
            "tracking", {"numero": "DSP-1", "estado": "EN_RUTA", "tracking_url": "https://track.omni/1"}
        )

        cli = APIClient()
        cli.force_authenticate(user=usr_a)

        # POST chatter interno con idempotencia
        idem_chat = str(uuid.uuid4())
        r1 = cli.post(
            "/api/notificaciones/chatter/",
            {
                "tipo_documento": "PEDIDO",
                "documento_id": str(doc_id),
                "cuerpo": "Cliente solicita despacho prioritario.",
                "es_nota_interna": True,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=idem_chat,
        )
        r2 = cli.post(
            "/api/notificaciones/chatter/",
            {
                "tipo_documento": "PEDIDO",
                "documento_id": str(doc_id),
                "cuerpo": "Cliente solicita despacho prioritario.",
                "es_nota_interna": True,
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=idem_chat,
        )
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.data["id_mensaje"] == r2.data["id_mensaje"]

        # WhatsApp modo SIMULADO
        r_wa = cli.post(
            "/api/notificaciones/chatter/enviar-whatsapp/",
            {
                "tipo_documento": "COBRANZA",
                "documento_id": str(doc_id),
                "telefono": "+584141234567",
                "plantilla": "cobranza",
                "contexto": {"cliente": "Distribuidora", "numero": "FAC-01", "saldo": "200"},
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_wa.status_code == 201
        assert r_wa.data["estado_envio"] == "SIMULADO"

        # Teléfono inválido -> 400 domain_error_response
        r_bad = cli.post(
            "/api/notificaciones/chatter/enviar-whatsapp/",
            {
                "tipo_documento": "PEDIDO",
                "documento_id": str(doc_id),
                "telefono": "123",
                "cuerpo": "Hola",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_bad.status_code == 400

        # WhatsApp modo Cloud API (mock requests.post)
        monkeypatch.setenv("WHATSAPP_CLOUD_TOKEN", "ci-only-wa-dummy-token-01")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "100200300400")
        with patch("apps.notificaciones.whatsapp.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.content = b'{"messages":[{"id":"wamid.cloud.001"}]}'
            mock_post.return_value.json.return_value = {"messages": [{"id": "wamid.cloud.001"}]}
            r_cloud = cli.post(
                "/api/notificaciones/chatter/enviar-whatsapp/",
                {
                    "tipo_documento": "DESPACHO",
                    "documento_id": str(doc_id),
                    "telefono": "+584141234567",
                    "plantilla": "tracking",
                    "contexto": {"numero": "DSP-9", "estado": "EN_RUTA"},
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            )
        assert r_cloud.status_code == 201
        assert r_cloud.data["estado_envio"] == "ENVIADO"
        assert r_cloud.data["provider_message_id"] == "wamid.cloud.001"

        # Aislamiento tenant B no ve mensajes de empresa A
        cli_b = APIClient()
        cli_b.force_authenticate(user=usr_b)
        r_list_b = cli_b.get(f"/api/notificaciones/chatter/?documento_id={doc_id}")
        assert r_list_b.status_code == 200
        assert r_list_b.data["mensajes"] == []

        # MCP tools notificaciones
        cap_tok = _crear_cap_token(empresa_a, usr_a, ["notificaciones:read", "notificaciones:write"])
        monkeypatch.delenv("WHATSAPP_CLOUD_TOKEN", raising=False)
        res_mcp_wa = notificaciones_enviar_whatsapp_documento(
            cap_tok,
            str(empresa_a.pk),
            "COTIZACION",
            str(doc_id),
            "+584141234567",
            plantilla="libre",
            cuerpo="Cotización adjunta",
        )
        assert res_mcp_wa["estado_envio"] == "SIMULADO"
        res_mcp_list = notificaciones_listar_chatter_documento(cap_tok, str(empresa_a.pk), "COTIZACION", str(doc_id))
        assert len(res_mcp_list["mensajes"]) == 1


class TestAgentesOperativosFase82:
    def test_cinco_agentes_operativos_api_y_mcp(self, empresa_a, empresa_b, moneda_usd, metodo_efectivo):
        from rest_framework.test import APIClient

        from apps.agentes.mcp import agentes_ejecutar_operativo, agentes_listar_operativos
        from apps.agentes.models import EjecucionAgente
        from apps.agentes.operativos import ejecutar_agente_operativo

        ctx = _setup_datos_operativos(empresa_a, moneda_usd, metodo_efectivo)
        cli = APIClient()
        cli.force_authenticate(user=ctx["user"])

        r_cat = cli.get("/api/agentes/operativos/catalogo/")
        assert r_cat.status_code == 200
        codigos = {a["codigo"] for a in r_cat.data["agentes"]}
        assert codigos == {"COBRANZA", "TESORERO", "LOGISTICO", "COMPRADOR", "CFO_COPILOT"}

        # Ejecutar los 5 agentes por REST (y validar idempotencia + persistencia EjecucionAgente)
        for codigo in ("COBRANZA", "TESORERO", "LOGISTICO", "COMPRADOR", "CFO_COPILOT"):
            idem = str(uuid.uuid4())
            r1 = cli.post(
                "/api/agentes/operativos/ejecutar/",
                {"agente": codigo, "persistir": True, "limite": 10},
                format="json",
                HTTP_IDEMPOTENCY_KEY=idem,
            )
            r2 = cli.post(
                "/api/agentes/operativos/ejecutar/",
                {"agente": codigo, "persistir": True, "limite": 10},
                format="json",
                HTTP_IDEMPOTENCY_KEY=idem,
            )
            assert r1.status_code == 200 and r2.status_code == 200
            assert r1.data["ejecucion_id"] == r2.data["ejecucion_id"]
            assert r1.data["modo_ejecucion"] == "DETERMINISTA"
            assert EjecucionAgente.objects.filter(pk=r1.data["ejecucion_id"], id_empresa=empresa_a).exists()

        # Verificar métricas reales de cada agente
        res_tes = ejecutar_agente_operativo(empresa_a, "TESORERO", persistir=False)
        assert res_tes["metricas"]["matches_alta_confianza"] == 1
        res_log = ejecutar_agente_operativo(empresa_a, "LOGISTICO", persistir=False)
        assert res_log["metricas"]["requieren_reruteo"] == 1
        res_comp = ejecutar_agente_operativo(empresa_a, "COMPRADOR", persistir=False)
        assert res_comp["metricas"]["alertas_criticas"] >= 1
        res_cfo = ejecutar_agente_operativo(empresa_a, "CFO_COPILOT", persistir=False)
        assert Decimal(res_cfo["metricas"]["posicion_neta_cxc_cxp"]) == Decimal("150.00")

        # Enriquecimiento con LLMGateway mockeado
        with (
            patch("apps.agentes.operativos.LLMGateway.disponible", return_value=True),
            patch("apps.agentes.operativos.LLMGateway.generate") as mock_gen,
        ):
            mock_gen.return_value.text = "Liquidez positiva de $150; priorizar cobro Zelle pendiente."
            res_llm = ejecutar_agente_operativo(empresa_a, "CFO_COPILOT", persistir=False)
        assert res_llm["modo_ejecucion"] == "LLM_GATEWAY"
        assert "Liquidez positiva" in res_llm["resumen_ejecutivo"]

        # MCP tools
        cap = _crear_cap_token(empresa_a, ctx["user"], ["agentes:read", "agentes:write"])
        cat_mcp = agentes_listar_operativos(cap, str(empresa_a.pk))
        assert len(cat_mcp["agentes"]) == 5
        exec_mcp = agentes_ejecutar_operativo(cap, str(empresa_a.pk), "TESORERO", persistir=False)
        assert exec_mcp["agente_codigo"] == "TESORERO"
        bad_mcp = agentes_ejecutar_operativo(cap, str(empresa_a.pk), "NO_EXISTE")
        assert "error" in bad_mcp

        # Aislamiento empresa B no accede a empresa A
        assert cli.post(
            "/api/agentes/operativos/ejecutar/",
            {"id_empresa": str(empresa_b.pk), "agente": "COBRANZA"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        ).status_code in (400, 403)

    def test_edge_cases_chatter_whatsapp_mcp_y_agentes(self, empresa_a, empresa_b, monkeypatch):
        import requests as req_lib
        from rest_framework.test import APIClient

        from apps.core.llm_gateway import LLMUnavailable
        from apps.core.models import Usuarios
        from apps.notificaciones.mcp import (
            notificaciones_enviar_whatsapp_documento,
            notificaciones_listar_chatter_documento,
        )
        from apps.notificaciones.models import MensajeChatterDocumento
        from apps.notificaciones.whatsapp import (
            WhatsAppBusinessError,
            construir_mensaje_plantilla,
            enviar_whatsapp_documento,
            normalizar_telefono_e164,
        )
        from apps.agentes.operativos import AgenteError, ejecutar_agente_operativo

        usr_a = _crear_usuario_empresa(empresa_a)
        usr_sin = Usuarios.objects.create_user(
            username=f"sin_{uuid.uuid4().hex[:6]}", email=f"sin_{uuid.uuid4().hex[:6]}@omni.test", password="x"
        )
        cli = APIClient()
        cli.force_authenticate(user=usr_a)
        doc_id = uuid.uuid4()

        # WhatsApp validaciones y modos HTTP error / RequestException
        with pytest.raises(WhatsAppBusinessError):
            normalizar_telefono_e164("0414\x00123")
        with pytest.raises(WhatsAppBusinessError):
            construir_mensaje_plantilla("libre", {})
        with pytest.raises(WhatsAppBusinessError):
            enviar_whatsapp_documento(
                empresa=empresa_a, tipo_documento="INVALIDO", documento_id=doc_id, telefono="+584141234567", cuerpo="x"
            )

        monkeypatch.setenv("WHATSAPP_CLOUD_TOKEN", "ci-only-wa-dummy-token-02")
        monkeypatch.setenv("WHATSAPP_PHONE_NUMBER_ID", "100200300401")
        with patch("apps.notificaciones.whatsapp.requests.post") as m_post:
            m_post.return_value.status_code = 500
            m_post.return_value.content = b"{}"
            msg_fail = enviar_whatsapp_documento(
                empresa=empresa_a,
                tipo_documento="PEDIDO",
                documento_id=doc_id,
                telefono="+584141234567",
                cuerpo="Test 500",
            )
            assert msg_fail.estado_envio == "FALLIDO"
            assert str(msg_fail)

        with patch("apps.notificaciones.whatsapp.requests.post", side_effect=req_lib.RequestException("timeout")):
            msg_exc = enviar_whatsapp_documento(
                empresa=empresa_a,
                tipo_documento="PEDIDO",
                documento_id=doc_id,
                telefono="+584141234567",
                cuerpo="Test exc",
            )
            assert msg_exc.estado_envio == "FALLIDO"

        # Chatter view filters y errores (?empresa= ajena, ?tipo_documento= con NUL, cuerpo vacío, sin empresa)
        assert cli.get(f"/api/notificaciones/chatter/?empresa={empresa_b.pk}").status_code == 400
        assert cli.get(f"/api/notificaciones/chatter/?tipo_documento=PEDIDO&documento_id={doc_id}").status_code == 200
        assert cli.get("/api/notificaciones/chatter/?tipo_documento=BAD%00").status_code == 400
        assert (
            cli.post(
                "/api/notificaciones/chatter/",
                {"tipo_documento": "PEDIDO", "documento_id": str(doc_id), "cuerpo": "   "},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 400
        )

        cli_sin = APIClient()
        cli_sin.force_authenticate(user=usr_sin)
        assert cli_sin.get("/api/notificaciones/chatter/").status_code == 400
        assert cli_sin.get("/api/agentes/operativos/catalogo/").status_code == 403

        # Hallazgos PR #348: validar_uuid_param (400 en vez de 500), err de _resolver_empresa, EscrituraRateThrottle y ConsumoLLMResumenSerializer
        assert cli.get("/api/agentes/operativos/catalogo/?empresa_id=no-es-uuid").status_code == 400
        assert cli.get("/api/agentes/operativos/catalogo/?empresa_id=").status_code == 400
        assert cli.get(f"/api/agentes/operativos/catalogo/?empresa_id={empresa_b.pk}").status_code == 403
        su = Usuarios.objects.create_user(
            username=f"su_{uuid.uuid4().hex[:6]}",
            email=f"su_{uuid.uuid4().hex[:6]}@omni.test",
            password="x",
            es_superusuario_omni=True,
        )
        cli_su = APIClient()
        cli_su.force_authenticate(user=su)
        assert (
            cli_su.post(
                "/api/agentes/operativos/ejecutar/",
                {"agente": "COBRANZA"},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 400
        )

        from apps.agentes.serializers import ConsumoLLMResumenSerializer
        from apps.core.throttling import EscrituraRateThrottle
        from apps.notificaciones.views import ChatterDocumentoViewSet

        assert EscrituraRateThrottle in ChatterDocumentoViewSet.throttle_classes
        resumen_fields = set(ConsumoLLMResumenSerializer().fields.keys())
        assert {"por_modelo", "por_uso"}.issubset(resumen_fields)

        # MCP errores (UUID inválido, tipo inválido, teléfono inválido)
        cap = _crear_cap_token(empresa_a, usr_a, ["notificaciones:read", "notificaciones:write"])
        assert "error" in notificaciones_listar_chatter_documento(cap, str(empresa_a.pk), "PEDIDO", "bad-uuid")
        assert "error" in notificaciones_listar_chatter_documento(cap, str(empresa_a.pk), "NO_VALIDO", str(doc_id))
        assert "error" in notificaciones_enviar_whatsapp_documento(
            cap, str(empresa_a.pk), "PEDIDO", "bad-uuid", "+584141234567"
        )
        assert "error" in notificaciones_enviar_whatsapp_documento(
            cap, str(empresa_a.pk), "PEDIDO", str(doc_id), "bad"
        )

        # Agentes fallback LLMUnavailable + agente desconocido
        with (
            patch("apps.agentes.operativos.LLMGateway.disponible", return_value=True),
            patch("apps.agentes.operativos.LLMGateway.generate", side_effect=LLMUnavailable("down")),
        ):
            res_fb = ejecutar_agente_operativo(empresa_a, "COBRANZA", persistir=False)
            assert res_fb["modo_ejecucion"] == "DETERMINISTA"
        with pytest.raises(AgenteError):
            ejecutar_agente_operativo(empresa_a, "UNKNOWN_AGENT")
        assert MensajeChatterDocumento.objects.filter(id_empresa=empresa_a, documento_id=doc_id).count() >= 2
