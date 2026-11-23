"""Tests de integración Plan 09 Ola 4B: Logística Inteligente, TMS, VRP, Delivery Externo y ePOD."""

from __future__ import annotations

import uuid
from datetime import date, time
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.core import rls

pytestmark = [pytest.mark.django_db]


def _setup_tms_base(empresa, moneda_usd):
    from apps.almacenes.models import Almacen
    from apps.core.models import Contacto, Usuarios
    from apps.crm.models import Cliente, DireccionCliente
    from apps.despacho.models import Despacho, DetalleDespacho
    from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

    user = Usuarios.objects.create_user(
        username=f"tms_user_{uuid.uuid4().hex[:8]}",
        email=f"tms_{uuid.uuid4().hex[:6]}@omni.test",
        password="TestPass123!@#",
        is_staff=True,
    )
    user.empresas.add(empresa)

    um = UnidadMedida.objects.create(id_empresa=empresa, nombre="Caja", abreviatura="CAJ", tipo="CANTIDAD")
    cat = CategoriaProducto.objects.create(id_empresa=empresa, nombre_categoria="Lubricantes TMS")
    prod = Producto.objects.create(
        id_empresa=empresa,
        nombre_producto="Tambor Lubricante",
        sku=f"TMS-{uuid.uuid4().hex[:6]}",
        id_categoria=cat,
        id_unidad_medida_base=um,
        id_moneda_precio=moneda_usd,
        peso_unitario_kg=Decimal("20.0000"),
        volumen_unitario_m3=Decimal("0.050000"),
    )
    alm = Almacen.objects.create(
        id_empresa=empresa,
        nombre_almacen="CD Caracas",
        codigo_almacen=f"CDC-{uuid.uuid4().hex[:4]}",
    )

    contacto = Contacto.objects.create(
        id_empresa=empresa,
        nombre="Cliente Logístico CA",
        rif=f"J-{uuid.uuid4().hex[:8].upper()}",
        es_cliente=True,
    )
    cliente = Cliente.objects.create(
        id_empresa=empresa,
        razon_social="Cliente Logístico CA",
        rif=f"J-{uuid.uuid4().hex[:8].upper()}",
        contacto=contacto,
    )
    dir_ok = DireccionCliente.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        tipo_direccion="ENTREGA",
        direccion_completa="Av. Francisco de Miranda, Chacao",
        ciudad="Caracas",
        estado_provincia="Miranda",
        latitud=Decimal("10.495900"),
        longitud=Decimal("-66.853700"),
        ventana_entrega_inicio=time(8, 0),
        ventana_entrega_fin=time(17, 0),
        referencia_gps="Frente a plaza Altamira",
        es_direccion_principal=True,
    )

    despachos = []
    for idx in range(4):
        d = Despacho.objects.create(
            id_empresa=empresa,
            numero_despacho=f"DSP-{uuid.uuid4().hex[:6]}",
            fecha_despacho=timezone.now(),
            id_almacen_origen=alm,
            direccion_destino=f"Parada {idx + 1}, Caracas",
            estado_despacho="PENDIENTE",
        )
        DetalleDespacho.objects.create(
            id_despacho=d,
            id_producto=prod,
            cantidad_despachada=Decimal("5.0000"),  # 5 * 20kg = 100kg, 0.25m3 por despacho
            id_unidad_medida=um,
        )
        despachos.append(d)

    return {
        "user": user,
        "alm": alm,
        "prod": prod,
        "cliente": cliente,
        "dir_ok": dir_ok,
        "despachos": despachos,
    }


# ---------------------------------------------------------------------------
# 1. RLS en las 6 tablas nuevas + validaciones cross-tenant de modelos
# ---------------------------------------------------------------------------


class TestRLSYModelosTMS:
    def test_rls_seis_tablas_y_validaciones_modelo(self, rls_test_role, empresa_a, empresa_b, moneda_usd):
        from apps.despacho.models import Conductor, ParadaEntrega, RutaDespacho, TarifaFlete, Vehiculo, ZonaLogistica
        from apps.rrhh.models import Empleado

        tablas = (
            "despacho_zona_logistica",
            "despacho_tarifa_flete",
            "despacho_vehiculo",
            "despacho_conductor",
            "despacho_ruta",
            "despacho_parada_entrega",
        )
        with connection.cursor() as cur:
            for tabla in tablas:
                cur.execute(
                    "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename=%s",
                    [tabla],
                )
                assert cur.fetchone()[0] >= 1, f"Falta política RLS en {tabla}"

        ctx_a = _setup_tms_base(empresa_a, moneda_usd)
        ctx_b = _setup_tms_base(empresa_b, moneda_usd)

        zona_a = ZonaLogistica.objects.create(
            id_empresa=empresa_a, codigo="CCS-ESTE", nombre="Caracas Este", tarifa_base_usd=Decimal("10")
        )
        zona_b = ZonaLogistica.objects.create(
            id_empresa=empresa_b, codigo="VAL-SUR", nombre="Valencia Sur", tarifa_base_usd=Decimal("15")
        )
        tarifa_a = TarifaFlete.objects.create(
            id_empresa=empresa_a, id_zona=zona_a, tipo_calculo="POR_KM", monto_base_usd=Decimal("5")
        )
        TarifaFlete.objects.create(
            id_empresa=empresa_b, id_zona=zona_b, tipo_calculo="FIJA", monto_base_usd=Decimal("8")
        )
        veh_a = Vehiculo.objects.create(
            id_empresa=empresa_a, placa="A11AA11", marca_modelo="NPR Turbo", capacidad_kg=Decimal("3500")
        )
        veh_b = Vehiculo.objects.create(
            id_empresa=empresa_b, placa="B22BB22", marca_modelo="NKR", capacidad_kg=Decimal("2000")
        )
        cond_a = Conductor.objects.create(
            id_empresa=empresa_a, nombre_completo="Pedro Pérez", cedula="V-12345678", id_vehiculo_asignado=veh_a
        )
        Conductor.objects.create(
            id_empresa=empresa_b, nombre_completo="Juan Gómez", cedula="V-87654321", id_vehiculo_asignado=veh_b
        )
        ruta_a = RutaDespacho.objects.create(
            id_empresa=empresa_a,
            codigo="RUTA-RLS-1",
            fecha_ruta=date(2026, 11, 23),
            id_almacen_origen=ctx_a["alm"],
            id_vehiculo=veh_a,
            id_conductor=cond_a,
            id_zona=zona_a,
        )
        ruta_b = RutaDespacho.objects.create(
            id_empresa=empresa_b,
            codigo="RUTA-RLS-B",
            fecha_ruta=date(2026, 11, 23),
            id_almacen_origen=ctx_b["alm"],
            id_vehiculo=veh_b,
        )
        par_a = ParadaEntrega.objects.create(
            id_empresa=empresa_a,
            id_ruta=ruta_a,
            id_despacho=ctx_a["despachos"][0],
            id_direccion_cliente=ctx_a["dir_ok"],
            secuencia=1,
        )
        ParadaEntrega.objects.create(
            id_empresa=empresa_b,
            id_ruta=ruta_b,
            id_despacho=ctx_b["despachos"][0],
            secuencia=1,
        )
        assert "Caracas Este" in str(zona_a)
        assert "POR_KM" in str(tarifa_a)
        assert "A11AA11" in str(veh_a)
        assert "Pedro Pérez" in str(cond_a)
        assert "RUTA-RLS-1" in str(ruta_a)
        assert "RUTA-RLS-1 #1" in str(par_a)

        # Validaciones cross-empresa clean()
        emp_b_rrhh = Empleado.objects.create(
            empresa=empresa_b, nombre="Luis", apellido="R", cedula="V-99887766", fecha_ingreso=date(2024, 1, 1)
        )
        with pytest.raises(ValidationError):
            TarifaFlete(id_empresa=empresa_a, id_zona=zona_b).clean()
        with pytest.raises(ValidationError):
            Conductor(id_empresa=empresa_a, nombre_completo="X", cedula="1", id_vehiculo_asignado=veh_b).clean()
        with pytest.raises(ValidationError):
            Conductor(id_empresa=empresa_a, nombre_completo="X", cedula="2", id_empleado=emp_b_rrhh).clean()
        with pytest.raises(ValidationError):
            RutaDespacho(
                id_empresa=empresa_a, codigo="RX", fecha_ruta=date(2026, 11, 23), id_almacen_origen=ctx_b["alm"]
            ).clean()
        with pytest.raises(ValidationError):
            RutaDespacho(
                id_empresa=empresa_a,
                codigo="RX",
                fecha_ruta=date(2026, 11, 23),
                id_almacen_origen=ctx_a["alm"],
                id_vehiculo=veh_b,
            ).clean()
        with pytest.raises(ValidationError):
            ParadaEntrega(id_empresa=empresa_a, id_ruta=ruta_b, id_despacho=ctx_a["despachos"][0], secuencia=1).clean()
        with pytest.raises(ValidationError):
            ParadaEntrega(id_empresa=empresa_a, id_ruta=ruta_a, id_despacho=ctx_b["despachos"][0], secuencia=1).clean()

        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(f"SET LOCAL ROLE {rls_test_role}")
                cur.execute("SELECT set_config(%s, 'off', true)", [rls.GUC_BYPASS])
                cur.execute("SELECT set_config(%s, %s, true)", [rls.GUC_EMPRESAS, str(empresa_a.pk)])
                assert list(ZonaLogistica.objects.values_list("codigo", flat=True)) == ["CCS-ESTE"]
                assert list(Vehiculo.objects.values_list("placa", flat=True)) == ["A11AA11"]
                assert list(RutaDespacho.objects.values_list("codigo", flat=True)) == ["RUTA-RLS-1"]
                assert TarifaFlete.objects.count() == 1
                assert Conductor.objects.count() == 1
                assert ParadaEntrega.objects.count() == 1


# ---------------------------------------------------------------------------
# 2. Optimizador VRP, Tarifas de Flete y API de Catálogos TMS
# ---------------------------------------------------------------------------


class TestOptimizadorVRPYTarifas:
    def test_vrp_haversine_tarifas_capacidad_y_2opt(self, empresa_a, empresa_b, moneda_usd):
        from rest_framework.test import APIClient

        from apps.despacho.models import TarifaFlete, Vehiculo, ZonaLogistica
        from apps.despacho.services_vrp import (
            VRPError,
            calcular_tarifa_flete,
            distancia_haversine_km,
            optimizar_rutas_vrp,
        )

        ctx = _setup_tms_base(empresa_a, moneda_usd)
        ctx_b = _setup_tms_base(empresa_b, moneda_usd)

        # Haversine Caracas (10.4806, -66.9036) -> Valencia (10.1620, -68.0077) ~ 125-128 km
        dist = distancia_haversine_km("10.480600", "-66.903600", "10.162000", "-68.007700")
        assert Decimal("120") < dist < Decimal("135")
        with pytest.raises(VRPError):
            distancia_haversine_km("95.0", "-66.9", "10.0", "-66.9")
        with pytest.raises(VRPError):
            distancia_haversine_km("10.0", "-185.0", "10.0", "-66.9")

        # Tarifa Flete todos los tipos + mínimo + fallback
        zona = ZonaLogistica.objects.create(
            id_empresa=empresa_a, codigo="GRAN-CCS", nombre="Gran Caracas", tarifa_base_usd=Decimal("12.0000")
        )
        assert calcular_tarifa_flete(None) == Decimal("0.0000")
        assert calcular_tarifa_flete(zona) == Decimal("12.0000")
        regla = TarifaFlete.objects.create(
            id_empresa=empresa_a,
            id_zona=zona,
            tipo_calculo="POR_KG",
            monto_base_usd=Decimal("5.0000"),
            tarifa_unidad_usd=Decimal("0.1000"),
            minimo_usd=Decimal("15.0000"),
        )
        assert calcular_tarifa_flete(zona, peso_kg=Decimal("50")) == Decimal("15.0000")  # aplica mínimo
        assert calcular_tarifa_flete(zona, peso_kg=Decimal("200")) == Decimal("25.0000")
        for tipo, kw in (
            ("POR_KM", {"distancia_km": Decimal("10")}),
            ("POR_M3", {"volumen_m3": Decimal("2")}),
            ("POR_PALETA", {"paletas": Decimal("3")}),
            ("FIJA", {}),
        ):
            regla.tipo_calculo = tipo
            regla.save(update_fields=["tipo_calculo"])
            assert calcular_tarifa_flete(zona, **kw) >= Decimal("15.0000")

        # Vehículo con capacidad 250kg (caben 2 despachos de 100kg c/u; otros 2 quedan sin asignar si solo hay 1 veh)
        veh1 = Vehiculo.objects.create(
            id_empresa=empresa_a,
            placa="VAN-01",
            marca_modelo="Hyundai H1",
            capacidad_kg=Decimal("250.0000"),
            capacidad_m3=Decimal("5.0000"),
        )
        veh2 = Vehiculo.objects.create(
            id_empresa=empresa_a,
            placa="CAM-02",
            marca_modelo="Iveco Daily",
            capacidad_kg=Decimal("500.0000"),
            capacidad_m3=Decimal("10.0000"),
        )

        # Coordenadas con cruce intencional para ejercitar 2-opt sobre 4 paradas
        coords = {
            str(ctx["despachos"][0].pk): ("10.500000", "-66.850000"),
            str(ctx["despachos"][1].pk): ("10.480000", "-66.900000"),
            str(ctx["despachos"][2].pk): ("10.510000", "-66.820000"),
            str(ctx["despachos"][3].pk): ("10.490000", "-66.870000"),
        }
        res_parcial = optimizar_rutas_vrp(
            empresa=empresa_a,
            almacen_origen=ctx["alm"],
            despachos=ctx["despachos"],
            vehiculos=[veh1],
            origen_lat="10.480600",
            origen_lng="-66.903600",
            zona=zona,
            coords_override=coords,
        )
        assert res_parcial["despachos_asignados"] == 2
        assert len(res_parcial["despachos_no_asignados"]) == 2

        # Ahora optimizar los otros 2 despachos vía API usando veh2
        client = APIClient()
        client.force_authenticate(user=ctx["user"])
        r_vrp = client.post(
            "/api/despacho/rutas/optimizar-vrp/",
            {
                "id_almacen_origen": str(ctx["alm"].pk),
                "despachos": res_parcial["despachos_no_asignados"],
                "vehiculos": [str(veh2.pk)],
                "origen_lat": "10.480600",
                "origen_lng": "-66.903600",
                "id_zona": str(zona.pk),
            },
            format="json",
        )
        assert r_vrp.status_code == 201, r_vrp.data
        assert r_vrp.data["rutas_creadas"] == 1
        assert r_vrp.data["despachos_asignados"] == 2

        # Endpoints CRUD + GPS + filtros NUL
        assert (
            client.post(
                f"/api/despacho/vehiculos/{veh1.pk}/actualizar-gps/",
                {"latitud": "10.491000", "longitud": "-66.881000"},
                format="json",
            ).status_code
            == 200
        )
        assert client.get("/api/despacho/vehiculos/?estado=DISPO\x00NIBLE").status_code == 400
        assert client.get("/api/despacho/rutas/?estado=PLAN\x00").status_code == 400
        assert client.get(f"/api/despacho/tarifas-flete/?zona={zona.pk}").status_code == 200
        assert (
            client.post(
                "/api/despacho/rutas/optimizar-vrp/",
                {
                    "id_empresa": str(ctx_b["alm"].id_empresa_id),
                    "id_almacen_origen": str(ctx["alm"].pk),
                    "despachos": [str(ctx["despachos"][0].pk)],
                    "vehiculos": [str(veh1.pk)],
                    "origen_lat": "10.48",
                    "origen_lng": "-66.90",
                },
                format="json",
            ).status_code
            == 400
        )


# ---------------------------------------------------------------------------
# 3. Delivery Externo (Uber/Ridery/Yummy), ePOD, Cobro en Sitio, Tracking y SENIAT
# ---------------------------------------------------------------------------


class TestDeliveryExternoEPODTrackingYSeniat:
    def test_ciclo_tms_completo_delivery_guia_epod_cobro_y_tracking(
        self, empresa_a, empresa_b, moneda_usd, metodo_efectivo
    ):
        from rest_framework.test import APIClient

        from apps.despacho.delivery_externo import DeliveryExternoError, obtener_proveedor_delivery
        from apps.despacho.models import Conductor, RutaDespacho, Vehiculo
        from apps.despacho.services_vrp import optimizar_rutas_vrp

        ctx = _setup_tms_base(empresa_a, moneda_usd)
        ctx_b = _setup_tms_base(empresa_b, moneda_usd)

        veh = Vehiculo.objects.create(
            id_empresa=empresa_a, placa="TMS-900", marca_modelo="Ford 350", capacidad_kg=Decimal("4000")
        )
        cond = Conductor.objects.create(
            id_empresa=empresa_a, nombre_completo="Carlos Silva", cedula="V-15222333", id_vehiculo_asignado=veh
        )

        # 1) Probar adaptadores Delivery Externo (SIMULADO + HTTP inyectable + validaciones HTTPS)
        for cod in ("SIMULADO", "UBER_DIRECT", "RIDERY", "YUMMY"):
            adp = obtener_proveedor_delivery(cod)
            cot = adp.cotizar(
                origen_lat=Decimal("10.48"),
                origen_lng=Decimal("-66.90"),
                destino_lat=Decimal("10.50"),
                destino_lng=Decimal("-66.85"),
                peso_kg=Decimal("10"),
            )
            assert Decimal(cot["tarifa_usd"]) > 0
            req = adp.solicitar_entrega(
                referencia_ruta="R-1",
                origen_lat=Decimal("10.48"),
                origen_lng=Decimal("-66.90"),
                destino_lat=Decimal("10.50"),
                destino_lng=Decimal("-66.85"),
                direccion_destino="Altamira",
                peso_kg=Decimal("10"),
            )
            assert adp.consultar_tracking(referencia_externa=req["referencia_externa"])["estado"] == "EN_CAMINO"
            assert adp.cancelar_entrega(referencia_externa=req["referencia_externa"])["estado"] == "CANCELADO"

        llamadas = []

        def fake_transport(*, method, endpoint, payload, provider):
            llamadas.append((method, endpoint, provider))
            return {
                "referencia_externa": "UBR-LIVE-99",
                "tracking_url": "https://uber.example/track/UBR-LIVE-99",
                "tarifa_usd": "7.5000",
                "eta_minutos": 18,
                "estado": "ASIGNADO",
            }

        uber_http = obtener_proveedor_delivery(
            "UBER_DIRECT",
            config={"base_url": "https://api.uber.example", "api_token": "ci-tok"},
            transport=fake_transport,
        )
        assert (
            uber_http.solicitar_entrega(
                referencia_ruta="R-HTTP",
                origen_lat=Decimal("10.48"),
                origen_lng=Decimal("-66.90"),
                destino_lat=Decimal("10.50"),
                destino_lng=Decimal("-66.85"),
                direccion_destino="Chacao",
                peso_kg=Decimal("12"),
            )["referencia_externa"]
            == "UBR-LIVE-99"
        )
        assert (
            uber_http.cotizar(
                origen_lat=Decimal("10.48"),
                origen_lng=Decimal("-66.90"),
                destino_lat=Decimal("10.50"),
                destino_lng=Decimal("-66.85"),
                peso_kg=Decimal("12"),
            )["tarifa_usd"]
            == "7.5000"
        )
        assert uber_http.consultar_tracking(referencia_externa="UBR-LIVE-99")["referencia_externa"] == "UBR-LIVE-99"
        assert uber_http.cancelar_entrega(referencia_externa="UBR-LIVE-99")["estado"] == "ASIGNADO"

        with pytest.raises(DeliveryExternoError):
            obtener_proveedor_delivery("OTRO_PROV")
        with pytest.raises(DeliveryExternoError):
            obtener_proveedor_delivery(
                "RIDERY", config={"base_url": "http://insegura.local", "api_token": "x"}
            ).cotizar(
                origen_lat=Decimal("10"),
                origen_lng=Decimal("-66"),
                destino_lat=Decimal("10.1"),
                destino_lng=Decimal("-66.1"),
                peso_kg=Decimal("1"),
            )

        # 2) Crear ruta con 2 paradas (parada 1 -> ENTREGADA con cobro, parada 2 -> RECHAZADA)
        plan = optimizar_rutas_vrp(
            empresa=empresa_a,
            almacen_origen=ctx["alm"],
            despachos=ctx["despachos"][:2],
            vehiculos=[veh],
            origen_lat="10.480600",
            origen_lng="-66.903600",
        )
        ruta = plan["rutas"][0]
        ruta.id_conductor = cond
        ruta.save(update_fields=["id_conductor"])

        client = APIClient()
        client.force_authenticate(user=ctx["user"])
        client_b = APIClient()
        client_b.force_authenticate(user=ctx_b["user"])

        # Cotizar + Solicitar delivery externo (idempotente) + Consultar tracking + Emitir Guía SENIAT
        assert (
            client.post(
                "/api/despacho/rutas/cotizar-delivery/",
                {
                    "proveedor": "RIDERY",
                    "origen_lat": "10.48",
                    "origen_lng": "-66.90",
                    "destino_lat": "10.50",
                    "destino_lng": "-66.85",
                },
                format="json",
            ).status_code
            == 200
        )

        r_deliv = client.post(
            f"/api/despacho/rutas/{ruta.pk}/solicitar-delivery/",
            {
                "proveedor": "YUMMY",
                "destino_lat": "10.50",
                "destino_lng": "-66.85",
                "direccion_destino": "Las Mercedes",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_deliv.status_code == 200
        assert client.get(f"/api/despacho/rutas/{ruta.pk}/tracking-delivery/").status_code == 200

        r_guia = client.post(
            f"/api/despacho/rutas/{ruta.pk}/emitir-guia-seniat/",
            {"proveedor": "SIMULADO"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_guia.status_code == 201
        assert r_guia.data["numero_control"]
        # Re-emisión bloqueada con 400
        assert (
            client.post(
                f"/api/despacho/rutas/{ruta.pk}/emitir-guia-seniat/",
                {"proveedor": "SIMULADO"},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 400
        )

        # Iniciar ruta (idempotente) -> Vehículo pasa a EN_RUTA, PATCH/DELETE quedan bloqueados (400)
        r_ini = client.post(
            f"/api/despacho/rutas/{ruta.pk}/iniciar/", {}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())
        )
        assert r_ini.status_code == 200
        assert r_ini.data["estado"] == "EN_CURSO"
        assert (
            client.patch(f"/api/despacho/rutas/{ruta.pk}/", {"observaciones": "x"}, format="json").status_code == 400
        )
        assert client.delete(f"/api/despacho/rutas/{ruta.pk}/").status_code == 400
        assert client_b.get(f"/api/despacho/rutas/{ruta.pk}/").status_code == 404

        # Torre de Control + WhatsApp tracking + Tracking Público anónimo
        r_tc = client.get("/api/despacho/rutas/torre-control/")
        assert r_tc.status_code == 200
        assert r_tc.data["kpis"]["rutas_en_curso"] == 1
        assert r_tc.data["kpis"]["vehiculos_en_ruta"] == 1

        paradas = list(ruta.paradas.order_by("secuencia"))
        p1, p2 = paradas[0], paradas[1]
        r_wa = client.get(f"/api/despacho/paradas/{p1.pk}/whatsapp-tracking/?base_url=https://app.omni.local")
        assert r_wa.status_code == 200
        assert str(p1.token_tracking) in r_wa.data["tracking_url"]
        assert "wa.me" in r_wa.data["whatsapp_deeplink"]

        anon_client = APIClient()
        r_pub = anon_client.get(f"/api/despacho/tracking/{p1.token_tracking}/")
        assert r_pub.status_code == 200
        assert r_pub.data["ruta_codigo"] == ruta.codigo
        assert "epod_receptor_cedula" not in r_pub.data
        assert anon_client.get(f"/api/despacho/tracking/{uuid.uuid4()}/").status_code == 404

        # Parada 1: ePOD ENTREGADA + Cobro en sitio -> genera finanzas.Pago + avanza Parada 2 a EN_CAMINO
        r_epod1 = client.post(
            f"/api/despacho/paradas/{p1.pk}/registrar-epod/",
            {
                "resultado": "ENTREGADA",
                "receptor_nombre": "Ana Morales",
                "receptor_cedula": "V-18999111",
                "firma_base64": "data:image/png;base64,iVBORw0KGgo=",
                "foto_url": "https://cdn.omni.local/epod/1.jpg",
                "latitud": "10.495900",
                "longitud": "-66.853700",
                "cobro": {
                    "monto": "125.5000",
                    "id_metodo_pago": str(metodo_efectivo.pk),
                    "id_moneda": str(moneda_usd.pk),
                    "referencia": "CASH-EPOD-01",
                },
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_epod1.status_code == 200, r_epod1.data
        assert r_epod1.data["pago_id"] is not None
        assert r_epod1.data["ruta_completada"] is False
        p2.refresh_from_db()
        assert p2.estado == "EN_CAMINO"

        # Parada 2: ePOD RECHAZADA sin motivo -> 400; con motivo -> DEVUELTO y completa ruta + libera vehículo
        assert (
            client.post(
                f"/api/despacho/paradas/{p2.pk}/registrar-epod/",
                {"resultado": "RECHAZADA"},
                format="json",
            ).status_code
            == 400
        )
        r_epod2 = client.post(
            f"/api/despacho/paradas/{p2.pk}/registrar-epod/",
            {"resultado": "RECHAZADA", "motivo_rechazo": "Local cerrado fuera de horario"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        assert r_epod2.status_code == 200
        assert r_epod2.data["despacho_estado"] == "DEVUELTO"
        assert r_epod2.data["ruta_completada"] is True

        veh.refresh_from_db()
        assert veh.estado == "DISPONIBLE"

        # Cancelar y soft-delete de una ruta PLANIFICADA
        plan2 = optimizar_rutas_vrp(
            empresa=empresa_a,
            almacen_origen=ctx["alm"],
            despachos=ctx["despachos"][2:3],
            vehiculos=[veh],
            origen_lat="10.48",
            origen_lng="-66.90",
        )
        r2_id = plan2["rutas"][0].pk
        assert client.delete(f"/api/despacho/rutas/{r2_id}/").status_code == 204
        assert RutaDespacho.objects.get(pk=r2_id).activo is False

        # Test CRUD Zona/Conductor + errores 400/404
        r_z = client.post(
            "/api/despacho/zonas-logisticas/",
            {"codigo": "Z-API", "nombre": "Zona API", "tarifa_base_usd": "8.00"},
            format="json",
        )
        assert r_z.status_code == 201
        r_c = client.post(
            "/api/despacho/conductores/",
            {"nombre_completo": "Mario Bros", "cedula": "V-11223344", "id_vehiculo_asignado": str(veh.pk)},
            format="json",
        )
        assert r_c.status_code == 201
        assert client.get(f"/api/despacho/paradas/?ruta={ruta.pk}").status_code == 200
        assert client.get("/api/despacho/rutas/torre-control/?empresa=no-uuid\x00").status_code == 400


@pytest.mark.django_db
class TestEdgeCasesTMSYAdapters:
    """Cubre casos borde de VRP (2-opt >= 3 paradas), adaptadores HTTP, serializers cross-tenant y acciones TMS."""

    def test_adapters_http_transport_y_errores(self):
        from apps.despacho.delivery_externo import (
            DeliveryExternoError,
            RideryAdapter,
            SimuladoDeliveryAdapter,
            UberDirectAdapter,
            YummyAdapter,
            obtener_proveedor_delivery,
        )

        sim = SimuladoDeliveryAdapter(codigo="SIMULADO")
        with pytest.raises(DeliveryExternoError):
            sim.consultar_tracking(referencia_externa="")
        with pytest.raises(DeliveryExternoError):
            sim.cancelar_entrega(referencia_externa="  ")

        calls = []

        def fake_transport(*, method, endpoint, payload, provider):
            calls.append((provider, method, endpoint))
            if endpoint == "/quotes":
                return {"tarifa_usd": "4.2500", "eta_minutos": 12}
            if endpoint == "/deliveries":
                return {"referencia_externa": f"{provider}-999", "tracking_url": "https://t.local/999"}
            if endpoint.startswith("/deliveries/") and method == "GET":
                return {
                    "estado": "EN_CAMINO",
                    "latitud_repartidor": "10.5",
                    "longitud_repartidor": "-66.9",
                    "eta_minutos": 8,
                }
            return {"estado": "CANCELADO"}

        for prov, cls in (("UBER_DIRECT", UberDirectAdapter), ("RIDERY", RideryAdapter), ("YUMMY", YummyAdapter)):
            sim_fb = obtener_proveedor_delivery(prov)
            assert (
                sim_fb.cotizar(
                    origen_lat=Decimal("10.48"),
                    origen_lng=Decimal("-66.90"),
                    destino_lat=Decimal("10.50"),
                    destino_lng=Decimal("-66.85"),
                    peso_kg=Decimal("5"),
                )["proveedor"]
                == prov
            )
            adp = cls(transport=fake_transport)
            q = adp.cotizar(
                origen_lat=Decimal("10.48"),
                origen_lng=Decimal("-66.90"),
                destino_lat=Decimal("10.50"),
                destino_lng=Decimal("-66.85"),
                peso_kg=Decimal("5"),
            )
            assert q["tarifa_usd"] == "4.2500"
            d = adp.solicitar_entrega(
                referencia_ruta="RUTA-1",
                origen_lat=Decimal("10.48"),
                origen_lng=Decimal("-66.90"),
                destino_lat=Decimal("10.50"),
                destino_lng=Decimal("-66.85"),
                direccion_destino="Altamira",
                peso_kg=Decimal("5"),
            )
            assert d["referencia_externa"] == f"{prov}-999"
            tr = adp.consultar_tracking(referencia_externa=d["referencia_externa"])
            assert tr["estado"] == "EN_CAMINO"
            cn = adp.cancelar_entrega(referencia_externa=d["referencia_externa"], motivo="test")
            assert cn["estado"] == "CANCELADO"

        # Sin transport ni credenciales / URL no HTTPS -> DeliveryExternoError
        with pytest.raises(DeliveryExternoError):
            UberDirectAdapter(base_url="", api_token="").cotizar(
                origen_lat=Decimal("10.48"),
                origen_lng=Decimal("-66.90"),
                destino_lat=Decimal("10.50"),
                destino_lng=Decimal("-66.85"),
                peso_kg=Decimal("5"),
            )
        with pytest.raises(DeliveryExternoError):
            RideryAdapter(base_url="http://insecure.local", api_token="tok").cotizar(
                origen_lat=Decimal("10.48"),
                origen_lng=Decimal("-66.90"),
                destino_lat=Decimal("10.50"),
                destino_lng=Decimal("-66.85"),
                peso_kg=Decimal("5"),
            )

    def test_vrp_2opt_tres_paradas_y_validaciones_completas(self, empresa_a, empresa_b, moneda_usd, metodo_efectivo):
        from apps.crm.serializers import DireccionClienteSerializer
        from apps.despacho.models import (
            Conductor,
            Despacho,
            ParadaEntrega,
            TarifaFlete,
            Vehiculo,
            ZonaLogistica,
        )
        from apps.despacho.services_tms import (
            TMSError,
            cancelar_ruta_despacho,
            registrar_epod_parada,
            solicitar_delivery_externo_ruta,
        )
        from apps.despacho.services_vrp import VRPError, _dec, optimizar_rutas_vrp
        from rest_framework.test import APIClient

        ctx = _setup_tms_base(empresa_a, moneda_usd)
        ctx_b = _setup_tms_base(empresa_b, moneda_usd)

        # Valida _dec y serializador DireccionCliente con GPS/ventanas
        assert _dec(None, Decimal("1")) == Decimal("1")
        with pytest.raises(VRPError):
            _dec(None)
        with pytest.raises(VRPError):
            _dec("abc")
        with pytest.raises(VRPError):
            _dec("NaN")
        ser_dir = DireccionClienteSerializer(ctx["dir_ok"])
        assert ser_dir.data["referencia_gps"] == "Frente a plaza Altamira"

        zona = ZonaLogistica.objects.create(
            id_empresa=empresa_a, codigo="Z-2OPT", nombre="Z 2-opt", tarifa_base_usd=Decimal("5")
        )
        veh = Vehiculo.objects.create(
            id_empresa=empresa_a,
            placa="V2OPT1",
            marca_modelo="Iveco",
            capacidad_kg=Decimal("500"),
            capacidad_m3=Decimal("10"),
        )
        veh_sin_uso = Vehiculo.objects.create(
            id_empresa=empresa_a,
            placa="VSMALL",
            marca_modelo="Moto",
            capacidad_kg=Decimal("50"),
            capacidad_m3=Decimal("1"),
        )
        veh_mant = Vehiculo.objects.create(
            id_empresa=empresa_a,
            placa="VMANT1",
            marca_modelo="Ford",
            capacidad_kg=Decimal("100"),
            capacidad_m3=Decimal("2"),
            estado="MANTENIMIENTO",
        )
        assert str(veh_mant)

        # Validaciones VRPError
        with pytest.raises(VRPError):
            optimizar_rutas_vrp(
                empresa=empresa_a,
                almacen_origen=ctx_b["alm"],
                despachos=ctx["despachos"],
                vehiculos=[veh],
                origen_lat="10.48",
                origen_lng="-66.90",
            )
        zona_b = ZonaLogistica.objects.create(id_empresa=empresa_b, codigo="ZB", nombre="Zona B")
        with pytest.raises(VRPError):
            optimizar_rutas_vrp(
                empresa=empresa_a,
                almacen_origen=ctx["alm"],
                despachos=ctx["despachos"],
                vehiculos=[veh],
                origen_lat="10.48",
                origen_lng="-66.90",
                zona=zona_b,
            )
        with pytest.raises(VRPError):
            optimizar_rutas_vrp(
                empresa=empresa_a,
                almacen_origen=ctx["alm"],
                despachos=[],
                vehiculos=[veh],
                origen_lat="10.48",
                origen_lng="-66.90",
            )
        with pytest.raises(VRPError):
            optimizar_rutas_vrp(
                empresa=empresa_a,
                almacen_origen=ctx["alm"],
                despachos=ctx["despachos"],
                vehiculos=[],
                origen_lat="10.48",
                origen_lng="-66.90",
            )
        with pytest.raises(VRPError):
            optimizar_rutas_vrp(
                empresa=empresa_a,
                almacen_origen=ctx["alm"],
                despachos=ctx["despachos"],
                vehiculos=[veh],
                origen_lat="10.48",
                origen_lng="-66.90",
                factor_trafico="9.0",
            )
        with pytest.raises(VRPError):
            optimizar_rutas_vrp(
                empresa=empresa_a,
                almacen_origen=ctx["alm"],
                despachos=ctx_b["despachos"][:1],
                vehiculos=[veh],
                origen_lat="10.48",
                origen_lng="-66.90",
            )
        with pytest.raises(VRPError):
            optimizar_rutas_vrp(
                empresa=empresa_a,
                almacen_origen=ctx["alm"],
                despachos=ctx["despachos"],
                vehiculos=[veh_mant],
                origen_lat="10.48",
                origen_lng="-66.90",
            )

        # coords_override + 4 paradas en zig-zag dispara mejora local 2-opt y veh_sin_uso queda vacío
        desps4 = ctx["despachos"]
        overrides = {
            str(desps4[0].pk): ("10.48", "-66.89"),
            str(desps4[1].pk): ("10.49", "-66.89"),
            str(desps4[2].pk): ("10.49", "-66.90"),
            str(desps4[3].pk): ("10.48", "-66.84"),
        }
        res_2opt = optimizar_rutas_vrp(
            empresa=empresa_a,
            almacen_origen=ctx["alm"],
            despachos=desps4,
            vehiculos=[veh, veh_sin_uso],
            origen_lat="10.48",
            origen_lng="-66.90",
            zona=zona,
            coords_override=overrides,
        )
        assert res_2opt["rutas_creadas"] == 1
        assert res_2opt["despachos_asignados"] == 4
        ruta = res_2opt["rutas"][0]
        paradas = list(ruta.paradas.order_by("secuencia"))
        assert len(paradas) == 4

        # Probar CRUD, filtros, errores REST y validación cross-tenant en ViewSets TMS
        client = APIClient()
        client.force_authenticate(user=ctx["user"])
        assert client.get("/api/despacho/vehiculos/?estado=DISPONIBLE").status_code == 200
        assert client.get(f"/api/despacho/tarifas-flete/?zona={zona.pk}").status_code == 200
        assert client.get("/api/despacho/rutas/?estado=PLANIFICADA").status_code == 200

        # Error cross-tenant en TarifaFlete / Conductor / RutaDespacho
        assert (
            client.post(
                "/api/despacho/tarifas-flete/",
                {"id_zona": str(zona_b.pk), "tipo_calculo": "FIJA", "monto_base_usd": "10.00"},
                format="json",
            ).status_code
            == 400
        )
        veh_b = Vehiculo.objects.create(id_empresa=empresa_b, placa="VB-999", marca_modelo="Test")
        assert (
            client.post(
                "/api/despacho/conductores/",
                {"nombre_completo": "X", "cedula": "V-1", "id_vehiculo_asignado": str(veh_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/despacho/rutas/",
                {"codigo": "R-BAD", "fecha_ruta": "2026-11-23", "id_almacen_origen": str(ctx_b["alm"].pk)},
                format="json",
            ).status_code
            == 400
        )

        # Acciones: tracking-delivery sin proveedor -> 400; cancelar ruta -> 200 y luego -> 400
        assert client.get(f"/api/despacho/rutas/{ruta.pk}/tracking-delivery/").status_code == 400
        assert client.post(f"/api/despacho/rutas/{ruta.pk}/cancelar/", {}, format="json").status_code == 200
        assert client.post(f"/api/despacho/rutas/{ruta.pk}/cancelar/", {}, format="json").status_code == 400
        ruta.refresh_from_db()
        assert ruta.estado == "CANCELADA"
        with pytest.raises(TMSError):
            cancelar_ruta_despacho(ruta)
        with pytest.raises(TMSError):
            solicitar_delivery_externo_ruta(
                ruta, proveedor_codigo="SIMULADO", destino_lat="10.5", destino_lng="-66.8", direccion_destino="X"
            )
        with pytest.raises(TMSError):
            registrar_epod_parada(paradas[0], ctx["user"], resultado="ENTREGADA", receptor_nombre="Ana")

        # Soft delete y PATCH en Zona/Tarifa/Vehiculo/Conductor
        tarifa = TarifaFlete.objects.create(
            id_empresa=empresa_a, id_zona=zona, tipo_calculo="FIJA", monto_base_usd=Decimal("10")
        )
        cond = Conductor.objects.create(
            id_empresa=empresa_a, nombre_completo="Luis", cedula="V-99", id_vehiculo_asignado=veh
        )
        assert (
            client.patch(
                f"/api/despacho/vehiculos/{veh.pk}/", {"marca_modelo": "Iveco Daily"}, format="json"
            ).status_code
            == 200
        )
        assert client.delete(f"/api/despacho/tarifas-flete/{tarifa.pk}/").status_code == 204
        assert client.delete(f"/api/despacho/conductores/{cond.pk}/").status_code == 204
        assert client.delete(f"/api/despacho/vehiculos/{veh_mant.pk}/").status_code == 204
        assert client.delete(f"/api/despacho/zonas-logisticas/{zona.pk}/").status_code == 204

        # Error ePOD sin receptor_nombre / monto <= 0 en nueva ruta activa
        desp_ok = Despacho.objects.get(pk=desps4[0].pk)
        res2 = optimizar_rutas_vrp(
            empresa=empresa_a,
            almacen_origen=ctx["alm"],
            despachos=[desp_ok],
            vehiculos=[veh],
            origen_lat="10.48",
            origen_lng="-66.90",
        )
        ruta_act = res2["rutas"][0]
        p_act = ruta_act.paradas.first()
        with pytest.raises(TMSError):
            registrar_epod_parada(p_act, ctx["user"], resultado="ENTREGADA", receptor_nombre="")
        with pytest.raises(TMSError):
            registrar_epod_parada(
                p_act,
                ctx["user"],
                resultado="ENTREGADA",
                receptor_nombre="Ana",
                cobro={"monto": "0", "id_metodo_pago": str(metodo_efectivo.pk), "id_moneda": str(moneda_usd.pk)},
            )
        with pytest.raises(TMSError):
            registrar_epod_parada(
                p_act, ctx["user"], resultado="ENTREGADA", receptor_nombre="Ana", cobro={"monto": "10"}
            )
        with pytest.raises(TMSError):
            registrar_epod_parada(
                p_act,
                ctx["user"],
                resultado="ENTREGADA",
                receptor_nombre="Ana",
                cobro={"monto": "10", "id_metodo_pago": str(uuid.uuid4()), "id_moneda": str(moneda_usd.pk)},
            )
        # Validaciones adicionales GPS, optimizar-vrp 404, iniciar sin paradas / cancelada, solicitud sin origen_lat
        assert (
            client.post(
                f"/api/despacho/vehiculos/{veh.pk}/actualizar-gps/",
                {"latitud": "999", "longitud": "-66.9"},
                format="json",
            ).status_code
            == 400
        )
        assert client.post(f"/api/despacho/rutas/{ruta.pk}/iniciar/", {}, format="json").status_code == 400
        assert (
            client.post(
                f"/api/despacho/rutas/{ruta.pk}/solicitar-delivery/",
                {"proveedor": "SIMULADO", "destino_lat": "10.5", "destino_lng": "-66.8", "direccion_destino": "X"},
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            ).status_code
            == 400
        )
        for bad_payload in (
            {
                "id_almacen_origen": str(uuid.uuid4()),
                "despachos": [str(desp_ok.pk)],
                "vehiculos": [str(veh.pk)],
                "origen_lat": "10.48",
                "origen_lng": "-66.90",
            },
            {
                "id_almacen_origen": str(ctx["alm"].pk),
                "id_zona": str(uuid.uuid4()),
                "despachos": [str(desp_ok.pk)],
                "vehiculos": [str(veh.pk)],
                "origen_lat": "10.48",
                "origen_lng": "-66.90",
            },
            {
                "id_almacen_origen": str(ctx["alm"].pk),
                "despachos": [str(uuid.uuid4())],
                "vehiculos": [str(veh.pk)],
                "origen_lat": "10.48",
                "origen_lng": "-66.90",
            },
            {
                "id_almacen_origen": str(ctx["alm"].pk),
                "despachos": [str(desp_ok.pk)],
                "vehiculos": [str(uuid.uuid4())],
                "origen_lat": "10.48",
                "origen_lng": "-66.90",
            },
        ):
            assert client.post("/api/despacho/rutas/optimizar-vrp/", bad_payload, format="json").status_code == 404
        # PATCH ruta ya no PLANIFICADA + ePOD cierre sobre ruta_act -> luego ePOD duplicado falla
        r_done = registrar_epod_parada(p_act, ctx["user"], resultado="ENTREGADA", receptor_nombre="Ana")
        assert r_done["ruta_completada"] is True
        assert (
            client.patch(f"/api/despacho/rutas/{ruta_act.pk}/", {"observaciones": "X"}, format="json").status_code
            == 400
        )
        with pytest.raises(TMSError):
            registrar_epod_parada(p_act, ctx["user"], resultado="ENTREGADA", receptor_nombre="Ana")
        assert str(ParadaEntrega.objects.get(pk=p_act.pk))
        assert str(tarifa) and str(cond) and str(zona) and str(ruta_act)

    def test_serializers_tms_directos_http_requests_y_ramas_tms(self, empresa_a, empresa_b, moneda_usd):
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch

        from django.core.exceptions import ValidationError as DjangoValidationError
        from rest_framework.exceptions import ValidationError as DRFValidationError

        from apps.core.models import Usuarios
        from apps.despacho.delivery_externo import DeliveryExternoError, obtener_proveedor_delivery
        from apps.despacho.models import Conductor, ParadaEntrega, RutaDespacho, TarifaFlete, Vehiculo, ZonaLogistica
        from apps.despacho.serializers_tms import ConductorSerializer, RutaDespachoSerializer, TarifaFleteSerializer
        from apps.despacho.services_tms import (
            TMSError,
            consultar_tracking_delivery_ruta,
            emitir_guia_despacho_seniat,
            iniciar_ruta_despacho,
            registrar_epod_parada,
            solicitar_delivery_externo_ruta,
        )

        ctx = _setup_tms_base(empresa_a, moneda_usd)
        ctx_b = _setup_tms_base(empresa_b, moneda_usd)
        zona_a = ZonaLogistica.objects.create(id_empresa=empresa_a, codigo="Z-SER", nombre="Zona Ser")
        zona_b = ZonaLogistica.objects.create(id_empresa=empresa_b, codigo="ZB-SER", nombre="Zona B Ser")
        veh_a = Vehiculo.objects.create(id_empresa=empresa_a, placa="VSER1", marca_modelo="Test")
        veh_b = Vehiculo.objects.create(id_empresa=empresa_b, placa="VB-SER", marca_modelo="Test")
        cond_b = Conductor.objects.create(id_empresa=empresa_b, nombre_completo="CB", cedula="V-777")

        # HTTP adapter mockeado + error de red (cubre lines 173-180 y YUMMY line 297)
        resp_ok = MagicMock()
        resp_ok.json.return_value = {"tarifa_usd": "3.5000", "eta_minutos": 10}
        with patch("apps.despacho.delivery_externo.requests.request", return_value=resp_ok):
            adp_y = obtener_proveedor_delivery(
                "YUMMY", config={"base_url": "https://api.yummy.local", "api_token": "tok"}
            )
            assert (
                adp_y.cotizar(
                    origen_lat=Decimal("10.48"),
                    origen_lng=Decimal("-66.90"),
                    destino_lat=Decimal("10.50"),
                    destino_lng=Decimal("-66.85"),
                    peso_kg=Decimal("5"),
                )["tarifa_usd"]
                == "3.5000"
            )
        with patch("apps.despacho.delivery_externo.requests.request", side_effect=RuntimeError("timeout")):
            with pytest.raises(DeliveryExternoError):
                adp_y.consultar_tracking(referencia_externa="Y-1")

        # Serializers TMS directos: usuario sin empresa, cross-tenant en validate(), y con instance
        usr_sin_emp = Usuarios.objects.create_user(
            username=f"noemp_{uuid.uuid4().hex[:5]}",
            email=f"ne_{uuid.uuid4().hex[:5]}@test.com",
            password="x",
        )
        req_sin_emp = SimpleNamespace(user=usr_sin_emp)
        ser_sin = TarifaFleteSerializer(
            data={"id_zona": str(zona_a.pk), "tipo_calculo": "FIJA", "monto_base_usd": "5"},
            context={"request": req_sin_emp},
        )
        with pytest.raises(DRFValidationError):
            ser_sin.is_valid(raise_exception=True)

        req_a = SimpleNamespace(user=ctx["user"])
        assert (
            TarifaFleteSerializer(
                data={"id_zona": str(zona_b.pk), "tipo_calculo": "FIJA", "monto_base_usd": "5"},
                context={"request": req_a},
            ).is_valid()
            is False
        )
        assert (
            ConductorSerializer(
                data={"nombre_completo": "C1", "cedula": "V-12", "id_vehiculo_asignado": str(veh_b.pk)},
                context={"request": req_a},
            ).is_valid()
            is False
        )
        for bad_ruta in (
            {"codigo": "R1", "fecha_ruta": "2026-11-23", "id_almacen_origen": str(ctx_b["alm"].pk)},
            {
                "codigo": "R2",
                "fecha_ruta": "2026-11-23",
                "id_almacen_origen": str(ctx["alm"].pk),
                "id_vehiculo": str(veh_b.pk),
            },
            {
                "codigo": "R3",
                "fecha_ruta": "2026-11-23",
                "id_almacen_origen": str(ctx["alm"].pk),
                "id_conductor": str(cond_b.pk),
            },
            {
                "codigo": "R4",
                "fecha_ruta": "2026-11-23",
                "id_almacen_origen": str(ctx["alm"].pk),
                "id_zona": str(zona_b.pk),
            },
        ):
            assert RutaDespachoSerializer(data=bad_ruta, context={"request": req_a}).is_valid() is False

        tar_ok = TarifaFlete.objects.create(
            id_empresa=empresa_a, id_zona=zona_a, tipo_calculo="FIJA", monto_base_usd=Decimal("5")
        )
        ser_upd = TarifaFleteSerializer(instance=tar_ok, data={"monto_base_usd": "7.00"}, partial=True)
        assert ser_upd.is_valid() is True

        # Modelos: RutaDespacho cross-tenant conductor/zona + ruta_vacia para ramas de error TMS
        ruta_vacia = RutaDespacho.objects.create(
            id_empresa=empresa_a,
            codigo="R-VACIA",
            fecha_ruta=timezone.localdate(),
            id_almacen_origen=ctx["alm"],
            id_vehiculo=veh_a,
            estado="PLANIFICADA",
        )
        with pytest.raises(DjangoValidationError):
            RutaDespacho(
                id_empresa=empresa_a,
                codigo="R-BAD-C",
                fecha_ruta=timezone.localdate(),
                id_almacen_origen=ctx["alm"],
                id_conductor=cond_b,
            ).clean()
        with pytest.raises(DjangoValidationError):
            RutaDespacho(
                id_empresa=empresa_a,
                codigo="R-BAD-Z",
                fecha_ruta=timezone.localdate(),
                id_almacen_origen=ctx["alm"],
                id_zona=zona_b,
            ).clean()

        # Ramas TMS de error: ruta vacía (sin paradas, sin coords), proveedor inválido, resultado inválido, cobro "abc"
        with pytest.raises(TMSError):
            iniciar_ruta_despacho(ruta_vacia, ctx["user"])
        with pytest.raises(TMSError):
            emitir_guia_despacho_seniat(ruta_vacia)
        with pytest.raises(TMSError):
            solicitar_delivery_externo_ruta(
                ruta_vacia, proveedor_codigo="SIMULADO", destino_lat="10.5", destino_lng="-66.8", direccion_destino="X"
            )
        ruta_vacia.origen_lat = Decimal("10.48")
        ruta_vacia.origen_lng = Decimal("-66.90")
        ruta_vacia.save(update_fields=["origen_lat", "origen_lng"])
        p_real = ParadaEntrega.objects.create(
            id_empresa=empresa_a, id_ruta=ruta_vacia, id_despacho=ctx["despachos"][0], secuencia=1
        )
        with pytest.raises(TMSError):
            solicitar_delivery_externo_ruta(
                ruta_vacia,
                proveedor_codigo="DESCONOCIDO",
                destino_lat="10.5",
                destino_lng="-66.8",
                direccion_destino="X",
            )
        ruta_vacia.proveedor_delivery_externo = "UBER_DIRECT"
        ruta_vacia.referencia_delivery_externo = "REF-1"
        ruta_vacia.save(update_fields=["proveedor_delivery_externo", "referencia_delivery_externo"])
        with pytest.raises(TMSError):
            consultar_tracking_delivery_ruta(ruta_vacia, config={"base_url": "http://bad.local", "api_token": "tok"})
        with pytest.raises(TMSError):
            emitir_guia_despacho_seniat(ruta_vacia, proveedor="PROVEEDOR_INVALIDO")
        with pytest.raises(TMSError):
            registrar_epod_parada(p_real, ctx["user"], resultado="OTRO")
        with pytest.raises(TMSError):
            registrar_epod_parada(
                p_real, ctx["user"], resultado="ENTREGADA", receptor_nombre="Ana", latitud="999", longitud="-66.9"
            )
        with pytest.raises(TMSError):
            registrar_epod_parada(
                p_real, ctx["user"], resultado="ENTREGADA", receptor_nombre="Ana", cobro={"monto": "abc"}
            )

    def test_hardening_rls_tracking_soft_delete_vrp_lock_y_sanitizacion(
        self, rls_test_role, empresa_a, empresa_b, moneda_usd, metodo_efectivo
    ):
        from unittest.mock import patch

        from rest_framework.test import APIClient

        from apps.core.rls import apply_context
        from apps.despacho.delivery_externo import DeliveryExternoError, UberDirectAdapter
        from apps.despacho.models import RutaDespacho, Vehiculo, ZonaLogistica
        from apps.despacho.serializers_tms import VehiculoSerializer
        from apps.despacho.services_tms import TMSError, registrar_epod_parada
        from apps.despacho.services_vrp import VRPError, optimizar_rutas_vrp
        from apps.finanzas.models import MetodoPago, Moneda

        ctx = _setup_tms_base(empresa_a, moneda_usd)
        veh = Vehiculo.objects.create(id_empresa=empresa_a, placa="VHARD1", marca_modelo="Iveco")
        veh_inact = Vehiculo.objects.create(
            id_empresa=empresa_a, placa="VINACT", marca_modelo="Inactivo", activo=False
        )

        # MEDIO #4: _siguiente_codigo_ruta evita colisión con ruta manual RUTA-000001
        RutaDespacho.objects.create(
            id_empresa=empresa_a,
            codigo="RUTA-000001",
            fecha_ruta=timezone.localdate(),
            id_almacen_origen=ctx["alm"],
            estado="PLANIFICADA",
        )
        res = optimizar_rutas_vrp(
            empresa=empresa_a,
            almacen_origen=ctx["alm"],
            despachos=ctx["despachos"][:1],
            vehiculos=[veh],
            origen_lat="10.48",
            origen_lng="-66.90",
        )
        ruta = res["rutas"][0]
        assert ruta.codigo == "RUTA-000002"
        parada = ruta.paradas.first()

        # MEDIO #4: Despacho ya asignado a una ruta activa no puede re-planificarse en paralelo
        with pytest.raises(VRPError):
            optimizar_rutas_vrp(
                empresa=empresa_a,
                almacen_origen=ctx["alm"],
                despachos=ctx["despachos"][:1],
                vehiculos=[veh],
                origen_lat="10.48",
                origen_lng="-66.90",
            )

        # MEDIO #3: ActiveFilterMixin oculta inactivos por defecto y los muestra con ?incluir_inactivos=true
        client = APIClient()
        client.force_authenticate(user=ctx["user"])
        zona = ZonaLogistica.objects.create(id_empresa=empresa_a, codigo="Z-ACT", nombre="Z Act", activo=False)
        assert not any(
            z["id_zona"] == str(zona.pk) for z in client.get("/api/despacho/zonas-logisticas/").data["results"]
        )
        assert any(
            z["id_zona"] == str(zona.pk)
            for z in client.get("/api/despacho/zonas-logisticas/?incluir_inactivos=true").data["results"]
        )
        assert not any(
            v["id_vehiculo"] == str(veh_inact.pk) for v in client.get("/api/despacho/vehiculos/").data["results"]
        )
        # optimizar-vrp rechaza vehículo soft-deleted con 404
        assert (
            client.post(
                "/api/despacho/rutas/optimizar-vrp/",
                {
                    "id_almacen_origen": str(ctx["alm"].pk),
                    "despachos": [str(ctx["despachos"][1].pk)],
                    "vehiculos": [str(veh_inact.pk)],
                    "origen_lat": "10.48",
                    "origen_lng": "-66.90",
                },
                format="json",
            ).status_code
            == 404
        )

        # BAJO #6: VehiculoSerializer valida rango lat/lng y bloqueo de estado si EN_RUTA
        assert (
            VehiculoSerializer(
                data={"placa": "VBADGPS", "marca_modelo": "X", "latitud_actual": "120.0", "longitud_actual": "-66.9"}
            ).is_valid()
            is False
        )
        assert (
            VehiculoSerializer(
                data={"placa": "VBADLN", "marca_modelo": "X", "latitud_actual": "10.5", "longitud_actual": "-200.0"}
            ).is_valid()
            is False
        )
        veh.estado = "EN_RUTA"
        veh.save(update_fields=["estado"])
        assert VehiculoSerializer(instance=veh, data={"estado": "DISPONIBLE"}, partial=True).is_valid() is False
        veh.estado = "DISPONIBLE"
        veh.save(update_fields=["estado"])

        # BAJO #6: whatsapp-tracking rechaza esquemas peligrosos
        assert (
            client.get(
                f"/api/despacho/paradas/{parada.pk}/whatsapp-tracking/?base_url=javascript:alert(1)"
            ).status_code
            == 400
        )

        # ALTO #2: registrar_epod_parada rechaza MetodoPago/Moneda privados de otra empresa o inactivos
        mp_priv_b = MetodoPago.objects.create(
            nombre_metodo="Privado Beta",
            tipo_metodo="EFECTIVO",
            empresa=empresa_b,
            es_generico=False,
            es_publico=False,
            activo=True,
        )
        mon_priv_b = Moneda.objects.create(
            codigo_iso=f"Z{uuid.uuid4().hex[:3].upper()}",
            nombre="Moneda Beta Privada",
            simbolo="B",
            empresa=empresa_b,
            es_generica=False,
            es_publica=False,
            activo=True,
        )
        with pytest.raises(TMSError):
            registrar_epod_parada(
                parada,
                ctx["user"],
                resultado="ENTREGADA",
                receptor_nombre="Ana",
                cobro={"monto": "10", "id_metodo_pago": str(mp_priv_b.pk), "id_moneda": str(moneda_usd.pk)},
            )
        with pytest.raises(TMSError):
            registrar_epod_parada(
                parada,
                ctx["user"],
                resultado="ENTREGADA",
                receptor_nombre="Ana",
                cobro={"monto": "10", "id_metodo_pago": str(metodo_efectivo.pk), "id_moneda": str(mon_priv_b.pk)},
            )

        # ALTO #1: TrackingPublicoParadaView funciona incluso bajo RLS fail-closed y da 404 si ruta.activo=False
        from django.test import override_settings

        anon = APIClient()
        with override_settings(RLS_ENABLED=True):
            apply_context([], bypass=False)
            try:
                r_pub = anon.get(f"/api/despacho/tracking/{parada.token_tracking}/")
                assert r_pub.status_code == 200
                assert r_pub.data["ruta_codigo"] == ruta.codigo
            finally:
                apply_context([], bypass=True)
        ruta.activo = False
        ruta.save(update_fields=["activo"])
        assert anon.get(f"/api/despacho/tracking/{parada.token_tracking}/").status_code == 404

        # MEDIO #5: delivery_externo sanitiza excepciones, valida referencia_externa y eta_minutos, y hace quote
        adp = UberDirectAdapter(base_url="https://api.uber.local", api_token="secret-tok")
        with patch("apps.despacho.delivery_externo.requests.request", side_effect=RuntimeError("secret-url-leak")):
            with pytest.raises(DeliveryExternoError) as err:
                adp.cotizar(
                    origen_lat=Decimal("10.48"),
                    origen_lng=Decimal("-66.90"),
                    destino_lat=Decimal("10.50"),
                    destino_lng=Decimal("-66.85"),
                    peso_kg=Decimal("5"),
                )
            assert "secret-url-leak" not in str(err.value)
        adp_bad = UberDirectAdapter(transport=lambda **kw: {"eta_minutos": "no-num"})
        with pytest.raises(DeliveryExternoError):
            adp_bad.cotizar(
                origen_lat=Decimal("10.48"),
                origen_lng=Decimal("-66.90"),
                destino_lat=Decimal("10.50"),
                destino_lng=Decimal("-66.85"),
                peso_kg=Decimal("5"),
            )
        with pytest.raises(DeliveryExternoError):
            adp_bad.solicitar_entrega(
                referencia_ruta="R",
                origen_lat=Decimal("10.48"),
                origen_lng=Decimal("-66.90"),
                destino_lat=Decimal("10.50"),
                destino_lng=Decimal("-66.85"),
                direccion_destino="Dir",
                peso_kg=Decimal("5"),
            )
        seen_urls = []
        adp_q = UberDirectAdapter(
            transport=lambda *, method, endpoint, payload, provider: (seen_urls.append(endpoint), {"estado": "OK"})[1]
        )
        adp_q.consultar_tracking(referencia_externa="REF/123?x=1")
        assert seen_urls[0] == "/deliveries/REF%2F123%3Fx%3D1"
