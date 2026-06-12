"""
Backfill de cobertura — apps/ventas/views.py (plan "Cero Dudas", COV/ventas).

Complementa los tests de flujo existentes (``test_e2e_ciclo_venta.py``,
``test_e2e_flujos_ventas.py``) cubriendo, por la API real:

- Las ramas ``get_queryset`` de los ~16 ViewSets de ventas (lista 200 autenticado /
  401 sin token), que aplican el filtro multi-tenant ``get_empresas_visible``.
- Aislamiento cross-tenant en ``PedidoViewSet`` (B no ve ni recupera el pedido de A).
- Caminos de error del action ``pedidos/{id}/confirmar`` sin tocar stock:
  ``almacen_id`` faltante (400) y almacén de otra empresa (400) — antes sin cubrir.

Fixtures (`empresa_a/b`, `user_a/b`, `moneda_usd`) vienen del conftest de
``tests/``. Aserciones sobre estado/efecto exacto (runner de mutación).
"""
import datetime

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

BASE = "/api/ventas/"

# Rutas registradas en apps/ventas/urls.py (router DRF).
VENTAS_ROUTES = [
    "pedidos",
    "detalles-pedido",
    "notas-venta",
    "detalles-nota-venta",
    "facturas-fiscales",
    "detalles-factura-fiscal",
    "notas-credito-venta",
    "detalles-nota-credito-venta",
    "devoluciones-venta",
    "detalles-devolucion-venta",
    "cotizaciones",
    "detalles-cotizacion",
    "notas-credito-fiscal",
    "detalles-nota-credito-fiscal",
    "listas-precio",
    "detalles-precio",
]


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


@pytest.fixture
def cliente_a(db, empresa_a):
    from apps.crm.models import Cliente

    return Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Cliente Alpha", rif="J-11111111-1"
    )


@pytest.fixture
def pedido_a(db, empresa_a, cliente_a):
    from apps.ventas.models import Pedido

    return Pedido.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_a,
        numero_pedido="PED-A-001",
        fecha_pedido=datetime.date(2026, 6, 9),
    )


# ── Lista + AuthN de cada ViewSet de ventas ───────────────────────────────────

@pytest.mark.parametrize("route", VENTAS_ROUTES)
def test_list_autenticado_200(client_a, route):
    resp = client_a.get(f"{BASE}{route}/")
    assert resp.status_code == 200


@pytest.mark.parametrize("route", VENTAS_ROUTES)
def test_list_sin_token_401(route):
    resp = APIClient().get(f"{BASE}{route}/")
    assert resp.status_code == 401


# ── Aislamiento multi-tenant en PedidoViewSet ─────────────────────────────────

class TestPedidoAislamiento:
    def test_dueña_ve_su_pedido(self, client_a, pedido_a):
        resp = client_a.get(f"{BASE}pedidos/")
        assert resp.status_code == 200
        ids = {p["id_pedido"] for p in resp.json()["results"]}
        assert str(pedido_a.id_pedido) in ids

    def test_empresa_ajena_no_ve_el_pedido(self, client_b, pedido_a):
        resp = client_b.get(f"{BASE}pedidos/")
        assert resp.status_code == 200
        ids = {p["id_pedido"] for p in resp.json()["results"]}
        assert str(pedido_a.id_pedido) not in ids

    def test_retrieve_cross_tenant_404(self, client_b, pedido_a):
        resp = client_b.get(f"{BASE}pedidos/{pedido_a.id_pedido}/")
        assert resp.status_code == 404


# ── confirmar: caminos de error (sin tocar stock) ─────────────────────────────

class TestPedidoConfirmarErrores:
    def test_confirmar_sin_almacen_id_400(self, client_a, pedido_a):
        resp = client_a.post(f"{BASE}pedidos/{pedido_a.id_pedido}/confirmar/", {}, format="json")
        assert resp.status_code == 400

    def test_confirmar_almacen_de_otra_empresa_400(self, client_a, pedido_a, empresa_b):
        """Un almacén que no pertenece a la empresa del pedido → 400."""
        from apps.almacenes.models import Almacen

        almacen_b = Almacen.objects.create(
            id_empresa=empresa_b, nombre_almacen="Alm B", codigo_almacen="ALMB"
        )
        resp = client_a.post(
            f"{BASE}pedidos/{pedido_a.id_pedido}/confirmar/",
            {"almacen_id": str(almacen_b.pk)},
            format="json",
        )
        assert resp.status_code == 400

    def test_confirmar_cross_tenant_pedido_404(self, client_b, pedido_a):
        """B no puede confirmar un pedido de A (get_object filtra tenant → 404)."""
        resp = client_b.post(
            f"{BASE}pedidos/{pedido_a.id_pedido}/confirmar/",
            {"almacen_id": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        assert resp.status_code == 404
