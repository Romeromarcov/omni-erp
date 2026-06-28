"""Aislamiento multi-tenant y API de operación (Fase 3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.cxc_lubrikca.models import Vinculacion

from . import helpers as h

pytestmark = [pytest.mark.django_db, pytest.mark.tenant]

BASE = "/api/cxc-lubrikca"


def test_pedido_de_otra_empresa_da_404(client_a, empresa_b):
    pedido = h.crear_pedido(empresa_b)
    r = client_a.get(f"{BASE}/pedidos/{pedido.id}/")
    assert r.status_code == 404


def test_listado_pedidos_no_filtra_otra_empresa(client_a, empresa_a, empresa_b):
    h.crear_pedido(empresa_a, so_id="MIO")
    h.crear_pedido(empresa_b, so_id="AJENO")
    r = client_a.get(f"{BASE}/pedidos/")
    assert r.status_code == 200
    so_ids = [row["so_id"] for row in r.data["results"]]
    assert "MIO" in so_ids
    assert "AJENO" not in so_ids


def test_create_pedido_fuerza_empresa(client_a, user_a, empresa_b):
    payload = {
        "so_id": "SO-NEW",
        "cliente_externo_id": "C1",
        "fecha": "2026-06-01",
        "lista_precios": "5",
        "empresa": str(empresa_b.id_empresa),
    }
    r = client_a.post(f"{BASE}/pedidos/", payload, format="json")
    assert r.status_code == 201, r.content
    from apps.cxc_lubrikca.models import PedidoLubrikca

    obj = PedidoLubrikca.objects.get(id=r.data["id"])
    assert obj.empresa_id != empresa_b.id_empresa
    assert obj.empresa in user_a.empresas.all()


def test_recalcular_action(client_a, empresa_a):
    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)
    h.crear_precio(empresa_a, lista=pedido.lista_precios, precio="100")
    r = client_a.post(f"{BASE}/pedidos/{pedido.id}/recalcular/")
    assert r.status_code == 200, r.content
    assert r.data["precio_base_calculado"] == "100.00"


def test_registrar_vinculacion_via_api(client_a, empresa_a):
    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)
    h.crear_precio(empresa_a, lista="4", precio="100")
    h.crear_metodo(empresa_a)
    h.crear_descuento(empresa_a)
    h.crear_recompra(empresa_a)
    h.cargar_tasas(empresa_a)
    pago = h.crear_pago(empresa_a, monto=Decimal("94"))

    r = client_a.post(
        f"{BASE}/vinculaciones/registrar/",
        {
            "pedido": str(pedido.id),
            "pago": str(pago.id),
            "monto_aplicado": "94",
            "hora_pago_confirmada": "2026-06-05T10:00:00Z",
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    assert Vinculacion.objects.filter(pedido=pedido).count() == 1


def test_registrar_vinculacion_pedido_ajeno_da_404(client_a, empresa_b):
    pedido_b = h.crear_pedido(empresa_b)
    pago_b = h.crear_pago(empresa_b)
    r = client_a.post(
        f"{BASE}/vinculaciones/registrar/",
        {
            "pedido": str(pedido_b.id),
            "pago": str(pago_b.id),
            "monto_aplicado": "10",
            "hora_pago_confirmada": "2026-06-05T10:00:00Z",
        },
        format="json",
    )
    assert r.status_code == 404


def test_registrar_vinculacion_error_negocio_da_400(client_a, empresa_a):
    pedido = h.crear_pedido(empresa_a)
    h.crear_metodo(empresa_a)
    h.cargar_tasas(empresa_a)
    pago = h.crear_pago(empresa_a, cliente_externo_id="OTRO")
    r = client_a.post(
        f"{BASE}/vinculaciones/registrar/",
        {
            "pedido": str(pedido.id),
            "pago": str(pago.id),
            "monto_aplicado": "10",
            "hora_pago_confirmada": "2026-06-05T10:00:00Z",
        },
        format="json",
    )
    assert r.status_code == 400
    assert "cliente" in r.data["detail"]


def test_vinculacion_de_otra_empresa_no_visible(client_a, empresa_b, user_b):
    pedido_b = h.crear_pedido(empresa_b)
    pago_b = h.crear_pago(empresa_b)
    from apps.cxc_lubrikca.services.captura import registrar_vinculacion

    h.crear_metodo(empresa_b)
    h.cargar_tasas(empresa_b)
    vinc = registrar_vinculacion(
        pedido=pedido_b,
        pago=pago_b,
        monto_aplicado=Decimal("50"),
        hora_pago_confirmada=pago_b.fecha_pago,
        usuario=user_b,
    )
    r = client_a.get(f"{BASE}/vinculaciones/{vinc.id}/")
    assert r.status_code == 404


def test_bandeja_readonly_no_permite_post_directo(client_a, empresa_a):
    # La bandeja es de solo lectura (sin create); POST a la colección → 405.
    r = client_a.post(f"{BASE}/bandeja/", {}, format="json")
    assert r.status_code == 405


def test_recalcular_sin_precio_da_400(client_a, empresa_a):
    # Pedido con línea pero SIN precio sembrado → BridgeError → 400 (no 500).
    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)
    r = client_a.post(f"{BASE}/pedidos/{pedido.id}/recalcular/")
    assert r.status_code == 400
    assert "precio" in r.data["detail"].lower()


def test_registrar_sin_precio_bcv_da_400(client_a, empresa_a):
    # Abono VES con método BCV → ruta BCV pura → falta precio lista "5" → 400.
    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)
    h.crear_precio(empresa_a, lista="4", precio="100")  # solo USD, falta BCV
    h.crear_metodo(empresa_a, codigo="PAGO_MOVIL", moneda="VES", tipo_tasa="BCV")
    h.cargar_tasas(empresa_a)
    pago = h.crear_pago(
        empresa_a, pago_id="PG-VES", monto=Decimal("3600"), moneda="VES",
        metodo_pago="PAGO_MOVIL",
    )
    r = client_a.post(
        f"{BASE}/vinculaciones/registrar/",
        {
            "pedido": str(pedido.id),
            "pago": str(pago.id),
            "monto_aplicado": "3600",
            "hora_pago_confirmada": "2026-06-05T10:00:00Z",
        },
        format="json",
    )
    assert r.status_code == 400
    assert "precio" in r.data["detail"].lower()


def test_registrar_pago_ajeno_da_404(client_a, empresa_a, empresa_b):
    # Pedido propio, pago de otra empresa → 404 en la resolución del pago.
    pedido = h.crear_pedido(empresa_a)
    pago_b = h.crear_pago(empresa_b)
    r = client_a.post(
        f"{BASE}/vinculaciones/registrar/",
        {
            "pedido": str(pedido.id),
            "pago": str(pago_b.id),
            "monto_aplicado": "10",
            "hora_pago_confirmada": "2026-06-05T10:00:00Z",
        },
        format="json",
    )
    assert r.status_code == 404


def _seed_candidata(empresa, usuario):
    from apps.cxc_lubrikca.services.captura import registrar_vinculacion

    pedido = h.crear_pedido(empresa)
    h.crear_linea(empresa, pedido)
    h.crear_precio(empresa, lista="4", precio="100")
    h.crear_metodo(empresa, tipo_tasa="N_A")
    h.crear_descuento(empresa)
    h.crear_recompra(empresa)
    h.cargar_tasas(empresa)
    pago = h.crear_pago(empresa, monto=Decimal("94"))
    registrar_vinculacion(
        pedido=pedido,
        pago=pago,
        monto_aplicado=Decimal("94"),
        hora_pago_confirmada=pago.fecha_pago,
        usuario=usuario,
    )
    pedido.refresh_from_db()
    return pedido.bandeja


def test_bandeja_proponer_sin_flujo_no_requiere(client_a, empresa_a, user_a):
    bandeja = _seed_candidata(empresa_a, user_a)
    r = client_a.post(f"{BASE}/bandeja/{bandeja.id}/proponer/")
    assert r.status_code == 200, r.content
    assert r.data["solicitud"] is None


def test_bandeja_proponer_no_candidata_da_400(client_a, empresa_a):
    pedido = h.crear_pedido(empresa_a)
    h.crear_linea(empresa_a, pedido)
    h.crear_precio(empresa_a, lista=pedido.lista_precios, precio="100")
    from apps.cxc_lubrikca.services.bridge import recalcular_bandeja

    bandeja = recalcular_bandeja(pedido)
    r = client_a.post(f"{BASE}/bandeja/{bandeja.id}/proponer/")
    assert r.status_code == 400


def test_bandeja_proponer_confirmar_flujo_completo(client_a, empresa_a, user_a):
    from apps.core.models import Roles, UsuarioRoles
    from apps.gestion_aprobaciones.models import FlujoAprobacion, TipoAprobacion
    from apps.cxc_lubrikca.services.aprobacion import CODIGO_TIPO

    tipo = TipoAprobacion.objects.create(
        id_empresa=empresa_a,
        codigo_tipo=CODIGO_TIPO,
        nombre_tipo="Cierre",
        modulo_origen="cxc_lubrikca",
        activo=True,
    )
    rol = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Aprobador")
    FlujoAprobacion.objects.create(
        id_tipo_aprobacion=tipo, orden_etapa=1, nombre_etapa="Gerencia",
        rol_aprobador=rol,
    )
    # user_a es el aprobador (se le asigna el rol).
    UsuarioRoles.objects.create(id_usuario=user_a, id_rol=rol)

    bandeja = _seed_candidata(empresa_a, user_a)
    r = client_a.post(f"{BASE}/bandeja/{bandeja.id}/proponer/")
    assert r.status_code == 200, r.content
    assert r.data["solicitud"] is not None

    r2 = client_a.post(
        f"{BASE}/bandeja/{bandeja.id}/confirmar/",
        {"aprobado": True, "comentarios": "ok"},
        format="json",
    )
    assert r2.status_code == 200, r2.content
    assert r2.data["estado"] == "aprobado"


def test_registrar_usuario_sin_empresa_da_403():
    # Usuario sin empresa visible → PermissionDenied (403) en la acción registrar.
    from rest_framework.test import APIClient

    from tests.factories import UsuariosFactory

    user = UsuariosFactory()  # sin empresa
    client = APIClient()
    client.force_authenticate(user=user)
    r = client.post(
        f"{BASE}/vinculaciones/registrar/",
        {
            "pedido": "00000000-0000-0000-0000-000000000000",
            "pago": "00000000-0000-0000-0000-000000000000",
            "monto_aplicado": "10",
            "hora_pago_confirmada": "2026-06-05T10:00:00Z",
        },
        format="json",
    )
    assert r.status_code == 403


def test_create_pedido_sin_empresa_da_403():
    from rest_framework.test import APIClient

    from tests.factories import UsuariosFactory

    user = UsuariosFactory()
    client = APIClient()
    client.force_authenticate(user=user)
    r = client.post(
        f"{BASE}/pedidos/",
        {"so_id": "X", "cliente_externo_id": "C", "fecha": "2026-06-01",
         "lista_precios": "4"},
        format="json",
    )
    assert r.status_code == 403


def test_bandeja_confirmar_sin_solicitud_da_400(client_a, empresa_a, user_a):
    bandeja = _seed_candidata(empresa_a, user_a)
    r = client_a.post(
        f"{BASE}/bandeja/{bandeja.id}/confirmar/",
        {"aprobado": True},
        format="json",
    )
    assert r.status_code == 400
