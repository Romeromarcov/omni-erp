"""Tests de integración Plan 09 Ola 5A: Portales Independientes (Vendedores SFA, Clientes B2B/B2C y Conductores)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import override_settings
from django.utils import timezone

pytestmark = [pytest.mark.django_db]


def _setup_portal_base(empresa, moneda_usd):
    from apps.almacenes.models import Almacen
    from apps.core.models import Contacto, Usuarios
    from apps.crm.models import Cliente, DireccionCliente
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    from apps.despacho.models import Conductor, Despacho, DetalleDespacho, ParadaEntrega, RutaDespacho, Vehiculo
    from apps.finanzas.models import Moneda, TasaCambio
    from apps.inventario.models import CategoriaProducto, Producto, StockActual, UnidadMedida
    from apps.ventas.models import EsquemaComision, FacturaFiscal, NotaVenta

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

    vendedor = Usuarios.objects.create_user(
        username=f"vend_{uuid.uuid4().hex[:6]}",
        email=f"vend_{uuid.uuid4().hex[:6]}@omni.test",
        password="TestPass123!@#",
    )
    vendedor.empresas.add(empresa)

    conductor_user = Usuarios.objects.create_user(
        username=f"cond_{uuid.uuid4().hex[:6]}",
        email=f"cond_{uuid.uuid4().hex[:6]}@omni.test",
        password="TestPass123!@#",
    )
    conductor_user.empresas.add(empresa)

    admin_user = Usuarios.objects.create_user(
        username=f"adm_{uuid.uuid4().hex[:6]}",
        email=f"adm_{uuid.uuid4().hex[:6]}@omni.test",
        password="TestPass123!@#",
        is_staff=True,
    )
    admin_user.empresas.add(empresa)

    contacto = Contacto.objects.create(
        id_empresa=empresa,
        nombre="Distribuidora Portal CA",
        rif=f"J-{uuid.uuid4().hex[:8].upper()}",
        es_cliente=True,
    )
    cliente = Cliente.objects.create(
        id_empresa=empresa,
        razon_social="Distribuidora Portal CA",
        rif=contacto.rif,
        telefono="+584141234567",
        email="cliente@portal.test",
        tipo_cliente="CREDITO",
        limite_credito=Decimal("5000"),
        dias_credito=15,
        bloquear_por_mora=True,
        contacto=contacto,
        id_vendedor_asignado=vendedor,
    )
    DireccionCliente.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        tipo_direccion="ENTREGA",
        direccion_completa="Av. Principal Las Mercedes, Caracas",
        ciudad="Caracas",
        estado_provincia="Miranda",
        latitud=Decimal("10.481000"),
        longitud=Decimal("-66.858000"),
        es_direccion_principal=True,
    )
    CuentaPorCobrar.objects.create(
        empresa=empresa,
        cliente=cliente,
        monto=Decimal("150.00"),
        fecha_emision=timezone.localdate() - timedelta(days=20),
        fecha_vencimiento=timezone.localdate() - timedelta(days=5),
        estado="vencida",
    )

    um = UnidadMedida.objects.create(id_empresa=empresa, nombre="Galón", abreviatura="GAL", tipo="CANTIDAD")
    cat = CategoriaProducto.objects.create(id_empresa=empresa, nombre_categoria="Aceites")
    prod = Producto.objects.create(
        id_empresa=empresa,
        nombre_producto="Aceite 20W50",
        sku=f"OIL-{uuid.uuid4().hex[:6].upper()}",
        codigo_barras="759000112233",
        id_categoria=cat,
        id_unidad_medida_base=um,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("25.0000"),
    )
    alm = Almacen.objects.create(
        id_empresa=empresa,
        nombre_almacen="CD Principal",
        codigo_almacen=f"CD-{uuid.uuid4().hex[:4]}",
    )
    StockActual.objects.create(
        id_empresa=empresa,
        id_producto=prod,
        id_almacen=alm,
        cantidad_disponible=Decimal("40.0000"),
        cantidad_comprometida=Decimal("5.0000"),
    )

    EsquemaComision.objects.create(
        id_empresa=empresa,
        vendedor=vendedor,
        porcentaje_base=Decimal("5.0000"),
        meta_mensual_monto=Decimal("1000.0000"),
        bono_meta_porcentaje=Decimal("2.0000"),
    )

    nota = NotaVenta.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        id_vendedor=vendedor,
        numero_nota=f"NV-{uuid.uuid4().hex[:6]}",
        fecha_nota=timezone.localdate(),
        estado="ENTREGADA",
        ambito="GERENCIAL",
    )
    FacturaFiscal.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        id_nota_venta_origen=nota,
        numero_control=f"00-{uuid.uuid4().hex[:6]}",
        numero_factura=f"F-{uuid.uuid4().hex[:6]}",
        fecha_emision=timezone.localdate(),
        monto_total=Decimal("116.0000"),
        id_moneda=moneda_usd,
        estado="EMITIDA",
    )

    veh = Vehiculo.objects.create(id_empresa=empresa, placa=f"P-{uuid.uuid4().hex[:5]}", marca_modelo="NPR")
    cond = Conductor.objects.create(
        id_empresa=empresa,
        id_usuario=conductor_user,
        nombre_completo="Pedro Chofer",
        cedula=f"V-{uuid.uuid4().hex[:7]}",
        id_vehiculo_asignado=veh,
    )
    desp = Despacho.objects.create(
        id_empresa=empresa,
        numero_despacho=f"DSP-{uuid.uuid4().hex[:6]}",
        id_nota_venta=nota,
        fecha_despacho=timezone.now(),
        id_almacen_origen=alm,
        direccion_destino="Las Mercedes",
        estado_despacho="EN_RUTA",
    )
    DetalleDespacho.objects.create(
        id_despacho=desp,
        id_producto=prod,
        cantidad_despachada=Decimal("2.0000"),
        id_unidad_medida=um,
    )
    ruta = RutaDespacho.objects.create(
        id_empresa=empresa,
        codigo=f"RUTA-{uuid.uuid4().hex[:6]}",
        fecha_ruta=timezone.localdate(),
        id_almacen_origen=alm,
        id_vehiculo=veh,
        id_conductor=cond,
        estado="EN_CURSO",
        origen_lat=Decimal("10.480000"),
        origen_lng=Decimal("-66.900000"),
    )
    parada = ParadaEntrega.objects.create(
        id_empresa=empresa,
        id_ruta=ruta,
        id_despacho=desp,
        secuencia=1,
        estado="EN_CAMINO",
        latitud=Decimal("10.481000"),
        longitud=Decimal("-66.858000"),
        direccion_texto="Las Mercedes",
    )

    return {
        "vendedor": vendedor,
        "conductor_user": conductor_user,
        "admin_user": admin_user,
        "cliente": cliente,
        "prod": prod,
        "alm": alm,
        "ruta": ruta,
        "parada": parada,
        "conductor": cond,
        "moneda_ves": moneda_ves,
    }


class TestRLSYValidacionesPortalesOla5A:
    def test_rls_tablas_portales_y_validaciones_modelo(self, rls_test_role, empresa_a, empresa_b, moneda_usd):
        from apps.core.models import Usuarios
        from apps.crm.models import Cliente, VisitaGPSVendedor

        tablas = (
            "crm_visita_gps_vendedor",
            "ventas_token_portal_cliente",
            "ventas_pago_portal_cliente",
        )
        with connection.cursor() as cur:
            for tabla in tablas:
                cur.execute("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename=%s", [tabla])
                assert cur.fetchone()[0] >= 1, f"Falta RLS en {tabla}"

        ctx_a = _setup_portal_base(empresa_a, moneda_usd)
        ctx_b = _setup_portal_base(empresa_b, moneda_usd)

        usr_b = Usuarios.objects.create_user(
            username=f"ub_{uuid.uuid4().hex[:6]}", email=f"ub_{uuid.uuid4().hex[:6]}@test.com", password="x"
        )
        usr_b.empresas.add(empresa_b)

        with pytest.raises(ValidationError):
            Cliente(
                id_empresa=empresa_a,
                razon_social="Bad Vendedor",
                rif="J-12345678",
                id_vendedor_asignado=usr_b,
            ).clean()

        v_ok = VisitaGPSVendedor.objects.create(
            id_empresa=empresa_a,
            id_vendedor=ctx_a["vendedor"],
            id_cliente=ctx_a["cliente"],
            latitud=Decimal("10.48"),
            longitud=Decimal("-66.86"),
        )
        assert str(v_ok)
        with pytest.raises(ValidationError):
            VisitaGPSVendedor(
                id_empresa=empresa_a,
                id_vendedor=ctx_a["vendedor"],
                id_cliente=ctx_b["cliente"],
                latitud=Decimal("10.48"),
                longitud=Decimal("-66.86"),
            ).clean()


class TestPortalVendedorSFA:
    def test_flujo_completo_vendedor_sfa(self, empresa_a, empresa_b, moneda_usd, metodo_efectivo):
        from rest_framework.test import APIClient

        ctx_a = _setup_portal_base(empresa_a, moneda_usd)
        ctx_b = _setup_portal_base(empresa_b, moneda_usd)

        client = APIClient()
        client.force_authenticate(user=ctx_a["vendedor"])

        # Cartera y bloqueo por mora
        r_cart = client.get("/api/ventas/portal-vendedor/cartera/")
        assert r_cart.status_code == 200
        assert len(r_cart.data["clientes"]) == 1
        cli_row = r_cart.data["clientes"][0]
        assert cli_row["cuentas_vencidas"] == 1
        assert cli_row["bloquear_por_mora"] is True

        # Catálogo trimonetario + stock neto (40 - 5 = 35)
        r_cat = client.get(f"/api/ventas/portal-vendedor/catalogo/?q={ctx_a['prod'].sku}")
        assert r_cat.status_code == 200
        assert len(r_cat.data["productos"]) == 1
        p_row = r_cat.data["productos"][0]
        assert Decimal(p_row["stock_disponible"]) == Decimal("35.0000")
        assert Decimal(p_row["equivalencias_trimonetarias"]["pais_fiscal"]) == Decimal("1125.0000")

        # Check-in GPS calcula distancia en metros al cliente
        r_chk = client.post(
            "/api/ventas/portal-vendedor/checkin/",
            {
                "id_cliente": str(ctx_a["cliente"].pk),
                "latitud": "10.481000",
                "longitud": "-66.858000",
                "resultado": "COBRANZA",
                "notas": "Promesa de pago",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_chk.status_code == 201
        assert Decimal(r_chk.data["distancia_cliente_m"]) == Decimal("0.00")

        # Pedido móvil
        r_ped = client.post(
            "/api/ventas/portal-vendedor/pedidos/",
            {
                "id_cliente": str(ctx_a["cliente"].pk),
                "lineas": [{"id_producto": str(ctx_a["prod"].pk), "cantidad": "3.0000"}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_ped.status_code == 201
        assert Decimal(r_ped.data["total_estimado"]) == Decimal("75.0000")

        # Cobro en campo válido + validación cross-tenant / URL inválida
        r_cob = client.post(
            "/api/ventas/portal-vendedor/cobros/",
            {
                "id_cliente": str(ctx_a["cliente"].pk),
                "monto": "100.0000",
                "id_moneda": str(moneda_usd.pk),
                "id_metodo_pago": str(metodo_efectivo.pk),
                "referencia": "ZELLE-7788",
                "comprobante_url": "https://cdn.omni.local/recibo.jpg",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_cob.status_code == 201
        assert (
            client.post(
                "/api/ventas/portal-vendedor/cobros/",
                {
                    "id_cliente": str(ctx_a["cliente"].pk),
                    "monto": "10",
                    "id_moneda": str(moneda_usd.pk),
                    "id_metodo_pago": str(metodo_efectivo.pk),
                    "comprobante_url": "javascript:alert(1)",
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/ventas/portal-vendedor/checkin/",
                {"id_cliente": str(ctx_b["cliente"].pk), "latitud": "10.5", "longitud": "-66.8"},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/ventas/portal-vendedor/pedidos/",
                {
                    "id_cliente": str(ctx_a["cliente"].pk),
                    "lineas": [{"id_producto": str(ctx_b["prod"].pk), "cantidad": "1"}],
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 400
        )

        # Metas y comisiones + validación empresa fuera de alcance
        r_met = client.get("/api/ventas/portal-vendedor/metas-comisiones/")
        assert r_met.status_code == 200
        assert len(r_met.data["esquemas"]) == 1
        assert client.get(f"/api/ventas/portal-vendedor/cartera/?empresa={empresa_b.pk}").status_code == 400


class TestPortalClienteSelfService:
    def test_otp_sesion_resumen_ocr_pedidos_y_tracking(
        self, rls_test_role, empresa_a, empresa_b, moneda_usd, metodo_efectivo
    ):
        from django.contrib.auth.hashers import make_password
        from rest_framework.test import APIClient

        from apps.core.rls import apply_context
        from apps.ventas.models import TokenPortalCliente
        from apps.ventas.portal_cliente import extraer_comprobante_pago_ocr

        ctx_a = _setup_portal_base(empresa_a, moneda_usd)
        ctx_b = _setup_portal_base(empresa_b, moneda_usd)
        anon = APIClient()

        # Sin autenticación -> 401/403
        assert anon.get("/api/ventas/portal-cliente/resumen/").status_code in (401, 403)

        # Solicitar OTP no filtra código en respuesta y maneja RIF inexistente silenciosamente
        r_missing = anon.post(
            "/api/ventas/portal-cliente/auth/solicitar-otp/",
            {"rif": "J-00000000"},
            format="json",
        )
        assert r_missing.status_code == 200

        r_otp = anon.post(
            "/api/ventas/portal-cliente/auth/solicitar-otp/",
            {"rif": ctx_a["cliente"].rif, "id_empresa": str(empresa_a.pk), "canal": "WHATSAPP"},
            format="json",
        )
        assert r_otp.status_code == 201
        assert "codigo" not in r_otp.data

        # Setear código conocido en BD para test determinista de intentos y verificación
        tok = TokenPortalCliente.objects.get(pk=r_otp.data["id_token"])
        tok.codigo_hash = make_password("654321")
        tok.save(update_fields=["codigo_hash"])

        assert (
            anon.post(
                "/api/ventas/portal-cliente/auth/verificar-otp/",
                {"id_token": str(tok.pk), "rif": ctx_a["cliente"].rif, "codigo": "000000"},
                format="json",
            ).status_code
            == 400
        )

        with override_settings(RLS_ENABLED=True):
            apply_context([], bypass=False)
            try:
                r_ver = anon.post(
                    "/api/ventas/portal-cliente/auth/verificar-otp/",
                    {"id_token": str(tok.pk), "rif": ctx_a["cliente"].rif, "codigo": "654321"},
                    format="json",
                )
                assert r_ver.status_code == 200
                session_tok = r_ver.data["session_token"]

                # Endpoints autenticados vía X-Portal-Cliente-Token con RLS activo
                hdrs = {"HTTP_X_PORTAL_CLIENTE_TOKEN": session_tok}
                r_res = anon.get("/api/ventas/portal-cliente/resumen/", **hdrs)
                assert r_res.status_code == 200
                assert len(r_res.data["facturas_fiscales"]) == 1
                assert len(r_res.data["notas_venta"]) == 1
                assert Decimal(r_res.data["estado_cuenta_trimonetario"]["saldo_pendiente"]) == Decimal("150.00")

                # Pago self-service con OCR regex fallback y luego OCR con mock LLMGateway
                r_pag = anon.post(
                    "/api/ventas/portal-cliente/pagos/",
                    {
                        "monto": "150.0000",
                        "id_moneda": str(moneda_usd.pk),
                        "id_metodo_pago": str(metodo_efectivo.pk),
                        "texto_comprobante_ocr": "Transferencia USD 150.00 Ref: 99887766",
                    },
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
                    **hdrs,
                )
                assert r_pag.status_code == 201
                assert r_pag.data["referencia"] == "99887766"
                assert r_pag.data["ocr_extraido"]["fuente"] == "REGEX_DETERMINISTA"

                # Pedido self-service (rechaza producto de empresa B)
                assert (
                    anon.post(
                        "/api/ventas/portal-cliente/pedidos/",
                        {"lineas": [{"id_producto": str(ctx_b["prod"].pk), "cantidad": "1"}]},
                        format="json",
                        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
                        **hdrs,
                    ).status_code
                    == 400
                )
                r_ped = anon.post(
                    "/api/ventas/portal-cliente/pedidos/",
                    {"lineas": [{"id_producto": str(ctx_a["prod"].pk), "cantidad": "2.0000"}]},
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
                    **hdrs,
                )
                assert r_ped.status_code == 201

                # Tracking en vivo de despachos propios
                r_trk = anon.get("/api/ventas/portal-cliente/tracking/", **hdrs)
                assert r_trk.status_code == 200
                assert len(r_trk.data["despachos"]) == 1
                assert r_trk.data["despachos"][0]["token_tracking"] is not None

                # Token inválido -> 401/403
                assert anon.get(
                    "/api/ventas/portal-cliente/resumen/", HTTP_X_PORTAL_CLIENTE_TOKEN="bad"
                ).status_code in (
                    401,
                    403,
                )
            finally:
                apply_context([], bypass=True)

        # Test unitario de hook OCR vía LLMGateway mockeado
        fake_gw = SimpleNamespace(
            disponible=lambda: True,
            generate=lambda **kw: SimpleNamespace(text='{"monto": "50.00", "moneda": "USDT", "referencia": "BIN-99"}'),
        )
        ocr_llm = extraer_comprobante_pago_ocr("Bin Pay 50", empresa=empresa_a, llm_gateway=fake_gw)
        assert ocr_llm["fuente"] == "LLM_GATEWAY"
        assert ocr_llm["referencia"] == "BIN-99"


class TestPortalConductorLogistica:
    def test_rutas_waze_escanear_bulto_y_epod(self, empresa_a, empresa_b, moneda_usd, metodo_efectivo):
        from rest_framework.test import APIClient

        ctx_a = _setup_portal_base(empresa_a, moneda_usd)
        ctx_b = _setup_portal_base(empresa_b, moneda_usd)
        client = APIClient()
        client.force_authenticate(user=ctx_a["conductor_user"])

        # Lista solo rutas propias con links Waze / Google Maps
        r_rutas = client.get("/api/despacho/portal-conductor/mis-rutas/")
        assert r_rutas.status_code == 200
        assert len(r_rutas.data["rutas"]) == 1
        p_data = r_rutas.data["rutas"][0]["paradas"][0]
        assert "waze.com/ul" in p_data["waze_url"]
        assert "google.com/maps" in p_data["google_maps_url"]

        parada_id = p_data["id_parada"]
        # Escanear código incorrecto -> 400; correcto (código barras producto) -> 200
        assert (
            client.post(
                f"/api/despacho/portal-conductor/paradas/{parada_id}/escanear-bulto/",
                {"codigo_bulto": "NO-EXISTE"},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 400
        )
        r_scan = client.post(
            f"/api/despacho/portal-conductor/paradas/{parada_id}/escanear-bulto/",
            {"codigo_bulto": "759000112233"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_scan.status_code == 200
        assert r_scan.data["verificado"] is True

        # Cross-tenant bloqueado (parada empresa B)
        assert (
            client.post(
                f"/api/despacho/portal-conductor/paradas/{ctx_b['parada'].pk}/escanear-bulto/",
                {"codigo_bulto": "759000112233"},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 400
        )

        # Captura ePOD + cobro contra entrega desde Portal Conductor
        r_epod = client.post(
            f"/api/despacho/portal-conductor/paradas/{parada_id}/epod/",
            {
                "resultado": "ENTREGADA",
                "receptor_nombre": "Carlos Receptor",
                "receptor_cedula": "V-20111222",
                "latitud": "10.481000",
                "longitud": "-66.858000",
                "cobro": {
                    "monto": "25.0000",
                    "id_metodo_pago": str(metodo_efectivo.pk),
                    "id_moneda": str(moneda_usd.pk),
                    "referencia": "COND-CASH-1",
                },
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_epod.status_code == 200
        assert r_epod.data["pago_id"] is not None
        assert r_epod.data["ruta_completada"] is True

    def test_edge_cases_conductor_y_otp_lockout(self, empresa_a, empresa_b, moneda_usd, metodo_efectivo):
        from django.contrib.auth.hashers import make_password
        from rest_framework.test import APIClient

        from apps.core.models import Usuarios
        from apps.despacho.models import Conductor, Despacho, ParadaEntrega, RutaDespacho
        from apps.despacho.portal_conductor import _links_navegacion
        from apps.finanzas.models import MetodoPago
        from apps.ventas.models import PagoPortalCliente, TokenPortalCliente
        from apps.ventas.portal_cliente import _enmascarar_destino, extraer_comprobante_pago_ocr

        ctx_a = _setup_portal_base(empresa_a, moneda_usd)
        ctx_b = _setup_portal_base(empresa_b, moneda_usd)

        assert extraer_comprobante_pago_ocr("")["fuente"] == "VACIO"
        assert _enmascarar_destino("ab") == "****"
        assert _links_navegacion(None, None) == {"waze_url": None, "google_maps_url": None}

        # Conductor endpoint edge cases: ?empresa= out of scope, ?conductor=, usuario sin conductor, parada de otro conductor, ePOD error
        client_cond = APIClient()
        client_cond.force_authenticate(user=ctx_a["conductor_user"])
        assert client_cond.get(f"/api/despacho/portal-conductor/mis-rutas/?empresa={empresa_b.pk}").status_code == 400
        assert (
            client_cond.get(f"/api/despacho/portal-conductor/mis-rutas/?conductor={ctx_a['conductor'].pk}").status_code
            == 200
        )

        u_sin_cond = Usuarios.objects.create_user(
            username=f"sc_{uuid.uuid4().hex[:6]}", email=f"sc_{uuid.uuid4().hex[:6]}@test.com", password="x"
        )
        u_sin_cond.empresas.add(empresa_a)
        client_sc = APIClient()
        client_sc.force_authenticate(user=u_sin_cond)
        assert client_sc.get("/api/despacho/portal-conductor/mis-rutas/").data["rutas"] == []
        # Usuario distinto al conductor asignado recibe 403 fail-closed
        assert (
            client_sc.post(
                f"/api/despacho/portal-conductor/paradas/{ctx_a['parada'].pk}/escanear-bulto/",
                {"codigo_bulto": "759000112233"},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 403
        )
        # ePOD inválido (sin receptor_nombre) -> 400 TMSError
        assert (
            client_cond.post(
                f"/api/despacho/portal-conductor/paradas/{ctx_a['parada'].pk}/epod/",
                {"resultado": "ENTREGADA", "receptor_nombre": ""},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 400
        )

        # OTP 5 intentos fallidos -> revoca token; + PagoPortalCliente errores URL/MetodoPago + __str__
        anon = APIClient()
        r_otp = anon.post(
            "/api/ventas/portal-cliente/auth/solicitar-otp/",
            {"rif": ctx_a["cliente"].rif, "id_empresa": str(empresa_a.pk), "canal": "EMAIL"},
            format="json",
        )
        tok = TokenPortalCliente.objects.get(pk=r_otp.data["id_token"])
        tok.codigo_hash = make_password("112233")
        tok.save(update_fields=["codigo_hash"])
        for _ in range(5):
            anon.post(
                "/api/ventas/portal-cliente/auth/verificar-otp/",
                {"id_token": str(tok.pk), "rif": ctx_a["cliente"].rif, "codigo": "999999"},
                format="json",
            )
        tok.refresh_from_db()
        assert tok.revocado is True

        # Crear sesión válida nueva para probar errores en pagos portal cliente + __str__
        r_otp2 = anon.post(
            "/api/ventas/portal-cliente/auth/solicitar-otp/",
            {"rif": ctx_a["cliente"].rif, "id_empresa": str(empresa_a.pk)},
            format="json",
        )
        tok2 = TokenPortalCliente.objects.get(pk=r_otp2.data["id_token"])
        tok2.codigo_hash = make_password("445566")
        tok2.save(update_fields=["codigo_hash"])
        sess = anon.post(
            "/api/ventas/portal-cliente/auth/verificar-otp/",
            {"id_token": str(tok2.pk), "rif": ctx_a["cliente"].rif, "codigo": "445566"},
            format="json",
        ).data["session_token"]
        hdrs = {"HTTP_X_PORTAL_CLIENTE_TOKEN": sess}
        mp_b = MetodoPago.objects.create(
            nombre_metodo="Privado B", tipo_metodo="EFECTIVO", empresa=empresa_b, es_generico=False, es_publico=False
        )
        assert (
            anon.post(
                "/api/ventas/portal-cliente/pagos/",
                {"monto": "10", "id_moneda": str(moneda_usd.pk), "id_metodo_pago": str(mp_b.pk)},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
                **hdrs,
            ).status_code
            == 400
        )
        assert (
            anon.post(
                "/api/ventas/portal-cliente/pagos/",
                {
                    "monto": "10",
                    "id_moneda": str(moneda_usd.pk),
                    "id_metodo_pago": str(metodo_efectivo.pk),
                    "comprobante_url": "ftp://bad",
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
                **hdrs,
            ).status_code
            == 400
        )
        pp = PagoPortalCliente.objects.create(
            id_empresa=empresa_a,
            id_cliente=ctx_a["cliente"],
            monto=Decimal("10"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        assert str(tok2) and str(pp)
        assert (
            Despacho.objects.filter(id_empresa=empresa_a).exists()
            and RutaDespacho.objects.filter(id_empresa=empresa_a).exists()
        )
        assert (
            Conductor.objects.filter(id_empresa=empresa_a).exists()
            and ParadaEntrega.objects.filter(id_empresa=empresa_a).exists()
        )
        assert ctx_b["cliente"] is not None


class TestCierreHallazgosRevisionPortales:
    """Pruebas unitarias/integración para los 5 hallazgos de revisión PR #346."""

    def test_alto1_conductor_idor_mis_rutas_y_parada_sin_asignar(self, empresa_a, moneda_usd):
        from rest_framework.test import APIClient

        from apps.core.models import Usuarios
        from apps.despacho.models import Conductor, Despacho, ParadaEntrega, RutaDespacho

        ctx = _setup_portal_base(empresa_a, moneda_usd)
        otro_user = Usuarios.objects.create_user(
            username=f"cond2_{uuid.uuid4().hex[:6]}",
            email=f"cond2_{uuid.uuid4().hex[:6]}@omni.test",
            password="TestPass123!@#",
        )
        otro_user.empresas.add(empresa_a)
        otro_cond = Conductor.objects.create(
            id_empresa=empresa_a,
            id_usuario=otro_user,
            nombre_completo="Segundo Chofer",
            cedula=f"V-{uuid.uuid4().hex[:7]}",
        )

        # Ruta sin conductor asignado (id_conductor=None) -> fail-closed 403 para conductor no-admin
        desp2 = Despacho.objects.create(
            id_empresa=empresa_a,
            numero_despacho=f"DSP-NC-{uuid.uuid4().hex[:6]}",
            id_nota_venta=ctx["parada"].id_despacho.id_nota_venta,
            fecha_despacho=timezone.now(),
            id_almacen_origen=ctx["ruta"].id_almacen_origen,
            direccion_destino="Altamira",
            estado_despacho="EN_RUTA",
        )
        ruta_sin_cond = RutaDespacho.objects.create(
            id_empresa=empresa_a,
            codigo=f"RUTA-NC-{uuid.uuid4().hex[:6]}",
            fecha_ruta=timezone.localdate(),
            id_almacen_origen=ctx["ruta"].id_almacen_origen,
            id_conductor=None,
            estado="EN_CURSO",
        )
        parada_sin_cond = ParadaEntrega.objects.create(
            id_empresa=empresa_a,
            id_ruta=ruta_sin_cond,
            id_despacho=desp2,
            secuencia=1,
            direccion_texto="Altamira",
        )

        cli_cond2 = APIClient()
        cli_cond2.force_authenticate(user=otro_user)

        # IDOR query param ?conductor= de otro chofer -> 403
        r_idor = cli_cond2.get(f"/api/despacho/portal-conductor/mis-rutas/?conductor={ctx['conductor'].pk}")
        assert r_idor.status_code == 403

        # Propio ?conductor= sí permitido -> 200
        r_propio = cli_cond2.get(f"/api/despacho/portal-conductor/mis-rutas/?conductor={otro_cond.pk}")
        assert r_propio.status_code == 200

        # Operar parada de ruta sin conductor o de otro conductor -> 403 fail-closed
        r_unassigned = cli_cond2.post(
            f"/api/despacho/portal-conductor/paradas/{parada_sin_cond.pk}/escanear-bulto/",
            {"codigo_bulto": "ANY"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_unassigned.status_code == 403

        r_other = cli_cond2.post(
            f"/api/despacho/portal-conductor/paradas/{ctx['parada'].pk}/escanear-bulto/",
            {"codigo_bulto": "ANY"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_other.status_code == 403

    def test_alto2_portal_cliente_idempotencia_replay(self, empresa_a, moneda_usd, metodo_efectivo):
        from django.contrib.auth.hashers import make_password
        from rest_framework.test import APIClient

        from apps.core.models import ClaveIdempotencia
        from apps.ventas.models import PagoPortalCliente, Pedido, TokenPortalCliente

        ctx = _setup_portal_base(empresa_a, moneda_usd)
        anon = APIClient()
        r_otp = anon.post(
            "/api/ventas/portal-cliente/auth/solicitar-otp/",
            {"rif": ctx["cliente"].rif, "id_empresa": str(empresa_a.pk), "canal": "EMAIL"},
            format="json",
        )
        tok = TokenPortalCliente.objects.get(pk=r_otp.data["id_token"])
        tok.codigo_hash = make_password("123123")
        tok.save(update_fields=["codigo_hash"])
        sess = anon.post(
            "/api/ventas/portal-cliente/auth/verificar-otp/",
            {"id_token": str(tok.pk), "rif": ctx["cliente"].rif, "codigo": "123123"},
            format="json",
        ).data["session_token"]
        hdrs = {"HTTP_X_PORTAL_CLIENTE_TOKEN": sess}

        idem_pago = f"cli-pago-{uuid.uuid4()}"
        pago_payload = {
            "monto": "45.00",
            "id_moneda": str(moneda_usd.pk),
            "id_metodo_pago": str(metodo_efectivo.pk),
            "referencia": "IDEMP-001",
        }
        r1 = anon.post(
            "/api/ventas/portal-cliente/pagos/", pago_payload, format="json", HTTP_IDEMPOTENCY_KEY=idem_pago, **hdrs
        )
        r2 = anon.post(
            "/api/ventas/portal-cliente/pagos/", pago_payload, format="json", HTTP_IDEMPOTENCY_KEY=idem_pago, **hdrs
        )
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.data["id_pago_portal"] == r2.data["id_pago_portal"]
        assert (
            PagoPortalCliente.objects.filter(
                id_empresa=empresa_a, id_cliente=ctx["cliente"], referencia="IDEMP-001"
            ).count()
            == 1
        )
        assert ClaveIdempotencia.objects.filter(empresa=empresa_a, usuario__isnull=True, clave=idem_pago).exists()

        idem_ped = f"cli-ped-{uuid.uuid4()}"
        ped_payload = {"lineas": [{"id_producto": str(ctx["prod"].pk), "cantidad": "2.0000"}]}
        p1 = anon.post(
            "/api/ventas/portal-cliente/pedidos/", ped_payload, format="json", HTTP_IDEMPOTENCY_KEY=idem_ped, **hdrs
        )
        p2 = anon.post(
            "/api/ventas/portal-cliente/pedidos/", ped_payload, format="json", HTTP_IDEMPOTENCY_KEY=idem_ped, **hdrs
        )
        assert p1.status_code == 201 and p2.status_code == 201
        assert p1.data["id_pedido"] == p2.data["id_pedido"]
        assert Pedido.objects.filter(pk=p1.data["id_pedido"]).count() == 1

    def test_medio1_vendedor_bloqueado_en_cliente_de_otro_vendedor(self, empresa_a, moneda_usd, metodo_efectivo):
        from rest_framework.test import APIClient

        from apps.core.models import Usuarios
        from apps.crm.models import Cliente, VisitaGPSVendedor
        from apps.ventas.models import PagoPortalCliente, Pedido

        ctx = _setup_portal_base(empresa_a, moneda_usd)
        otro_vend = Usuarios.objects.create_user(
            username=f"vend2_{uuid.uuid4().hex[:6]}",
            email=f"vend2_{uuid.uuid4().hex[:6]}@omni.test",
            password="TestPass123!@#",
        )
        otro_vend.empresas.add(empresa_a)
        cli_otro = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente Otro Vendedor",
            rif=f"J-{uuid.uuid4().hex[:8].upper()}",
            id_vendedor_asignado=otro_vend,
        )

        client = APIClient()
        client.force_authenticate(user=ctx["vendedor"])
        assert (
            client.post(
                "/api/ventas/portal-vendedor/checkin/",
                {"id_cliente": str(cli_otro.pk), "latitud": "10.48", "longitud": "-66.85"},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/ventas/portal-vendedor/pedidos/",
                {"id_cliente": str(cli_otro.pk), "lineas": [{"id_producto": str(ctx["prod"].pk), "cantidad": "1"}]},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/ventas/portal-vendedor/cobros/",
                {
                    "id_cliente": str(cli_otro.pk),
                    "monto": "10.00",
                    "id_moneda": str(moneda_usd.pk),
                    "id_metodo_pago": str(metodo_efectivo.pk),
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 404
        )
        assert not VisitaGPSVendedor.objects.filter(id_cliente=cli_otro).exists()
        assert not Pedido.objects.filter(id_cliente=cli_otro).exists()
        assert not PagoPortalCliente.objects.filter(id_cliente=cli_otro).exists()

    def test_medio2_saldo_neto_cxc_abono_y_gracia_mora(self, empresa_a, moneda_usd):
        from django.contrib.auth.hashers import make_password
        from rest_framework.test import APIClient

        from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar
        from apps.ventas.models import TokenPortalCliente

        ctx = _setup_portal_base(empresa_a, moneda_usd)
        cli = ctx["cliente"]
        cli.dias_gracia_mora = 10  # La CxC venció hace 5 días -> cubierta por 10 días de gracia
        cli.save(update_fields=["dias_gracia_mora"])
        cxc = CuentaPorCobrar.objects.get(empresa=empresa_a, cliente=cli)
        AbonoCxC.objects.create(cuenta_por_cobrar=cxc, monto=Decimal("50.00"))

        client_v = APIClient()
        client_v.force_authenticate(user=ctx["vendedor"])
        r_v = client_v.get("/api/ventas/portal-vendedor/cartera/")
        assert r_v.status_code == 200
        row = r_v.data["clientes"][0]
        assert row["saldo_pendiente"] == "100.00"
        assert row["cuentas_vencidas"] == 0
        assert row["bloquear_por_mora"] is False

        anon = APIClient()
        r_otp = anon.post(
            "/api/ventas/portal-cliente/auth/solicitar-otp/",
            {"rif": cli.rif, "id_empresa": str(empresa_a.pk)},
            format="json",
        )
        tok = TokenPortalCliente.objects.get(pk=r_otp.data["id_token"])
        tok.codigo_hash = make_password("654321")
        tok.save(update_fields=["codigo_hash"])
        sess = anon.post(
            "/api/ventas/portal-cliente/auth/verificar-otp/",
            {"id_token": str(tok.pk), "rif": cli.rif, "codigo": "654321"},
            format="json",
        ).data["session_token"]
        r_c = anon.get("/api/ventas/portal-cliente/resumen/", HTTP_X_PORTAL_CLIENTE_TOKEN=sess)
        assert r_c.status_code == 200
        ec = r_c.data["estado_cuenta_trimonetario"]
        assert ec["saldo_pendiente"] == "100.00"
        assert ec["cuentas_vencidas"] == 0
        assert ec["documentos_pendientes"] == 1

    def test_bajo1_validacion_cross_tenant_serializers_y_conductor(self, empresa_a, empresa_b):
        from apps.core.models import Usuarios
        from apps.crm.serializers import ClienteSerializer
        from apps.despacho.models import Conductor
        from apps.despacho.serializers_tms import ConductorSerializer

        usr_a = Usuarios.objects.create_user(
            username=f"ua_{uuid.uuid4().hex[:6]}", email=f"ua_{uuid.uuid4().hex[:6]}@omni.test", password="x"
        )
        usr_a.empresas.add(empresa_a)
        usr_b = Usuarios.objects.create_user(
            username=f"ub_{uuid.uuid4().hex[:6]}", email=f"ub_{uuid.uuid4().hex[:6]}@omni.test", password="x"
        )
        usr_b.empresas.add(empresa_b)

        ser_cli = ClienteSerializer(
            data={
                "razon_social": "Bad Ser Cli",
                "rif": f"J-{uuid.uuid4().int % 90000000 + 10000000}",
                "id_empresa": str(empresa_a.pk),
                "id_vendedor_asignado": str(usr_b.pk),
            }
        )
        assert ser_cli.is_valid() is False
        assert "id_vendedor_asignado" in ser_cli.errors

        with pytest.raises(ValidationError):
            Conductor(
                id_empresa=empresa_a,
                id_usuario=usr_b,
                nombre_completo="Bad Cond",
                cedula=f"V-{uuid.uuid4().hex[:7]}",
            ).clean()

        req = SimpleNamespace(user=usr_a)
        ser_cond = ConductorSerializer(
            data={
                "id_usuario": str(usr_b.pk),
                "nombre_completo": "Bad Cond Ser",
                "cedula": f"V-{uuid.uuid4().hex[:7]}",
            },
            context={"request": req},
        )
        assert ser_cond.is_valid() is False
        assert "id_usuario" in ser_cond.errors
