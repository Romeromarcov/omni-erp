"""
Backfill de cobertura — apps/finanzas/views.py (plan "Cero Dudas", COV/finanzas).

Cubre los ViewSets de dinero por la API real (`APIClient`), ejercitando:
- `get_queryset` con sus ramas de visibilidad multi-tenant (R-CODE-1): monedas
  genéricas/públicas/propias, tasas globales (BCV) vs de empresa, métodos de pago.
- Acciones (`@action`): `monedas/activas`, `cajas/tipo-caja-choices`,
  `cajas/{id}/movimientos-caja-banco`, `cuentas-bancarias/{id}/movimientos-cuenta-bancaria`,
  `metodos-pago/buscar_reutilizar`.
- Aislamiento cross-tenant: la empresa B no ve los objetos privados de la empresa A,
  pero ambas ven los globales (tasa BCV con `id_empresa` nulo).
- AuthN: sin autenticación → 401.

Las fixtures `empresa_a/b`, `user_a/b`, `moneda_usd`, `caja_fisica_a` vienen del
conftest de `tests/`. Todas las aserciones usan valores exactos para que el
test sirva también de runner de mutación (convención del plan).
"""
import datetime
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.finanzas.models import (
    Caja,
    CuentaBancariaEmpresa,
    MetodoPago,
    Moneda,
    MonedaEmpresaActiva,
    TasaCambio,
)

pytestmark = pytest.mark.django_db


# ── Clients ───────────────────────────────────────────────────────────────────

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


# ── Fixtures de dominio ───────────────────────────────────────────────────────

@pytest.fixture
def moneda_ves(db):
    """Moneda genérica VES (visible para todos)."""
    return Moneda.objects.create(
        nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat",
        es_generica=True,
    )


@pytest.fixture
def moneda_privada_a(db, empresa_a):
    """Moneda privada de la empresa A (no genérica ni pública)."""
    return Moneda.objects.create(
        nombre="Token Interno A", codigo_iso="TKA", simbolo="T", tipo_moneda="otro",
        es_generica=False, es_publica=False, empresa=empresa_a,
    )


@pytest.fixture
def tasa_bcv(db, moneda_usd, moneda_ves):
    """Tasa OFICIAL_BCV global (id_empresa nulo) — visible para todas las empresas."""
    return TasaCambio.objects.create(
        id_empresa=None,
        id_moneda_origen=moneda_usd,
        id_moneda_destino=moneda_ves,
        tipo_tasa="OFICIAL_BCV",
        valor_tasa=Decimal("36.50000000"),
        fecha_tasa=datetime.date(2026, 6, 9),
    )


@pytest.fixture
def tasa_privada_a(db, empresa_a, moneda_usd, moneda_ves):
    """Tasa especial privada de la empresa A."""
    return TasaCambio.objects.create(
        id_empresa=empresa_a,
        id_moneda_origen=moneda_usd,
        id_moneda_destino=moneda_ves,
        tipo_tasa="ESPECIAL_USUARIO",
        valor_tasa=Decimal("40.00000000"),
        fecha_tasa=datetime.date(2026, 6, 9),
    )


@pytest.fixture
def metodo_generico(db):
    return MetodoPago.objects.create(
        nombre_metodo="Efectivo Global", tipo_metodo="EFECTIVO", es_generico=True,
    )


@pytest.fixture
def metodo_privado_a(db, empresa_a):
    return MetodoPago.objects.create(
        nombre_metodo="Zelle Empresa A", tipo_metodo="ELECTRONICO", empresa=empresa_a,
    )


@pytest.fixture
def caja_virtual_a(db, empresa_a, moneda_usd):
    return Caja.objects.create(
        empresa=empresa_a, nombre="Caja Virtual A", moneda=moneda_usd,
        tipo_caja="REGISTRADORA",
    )


@pytest.fixture
def cuenta_bancaria_a(db, empresa_a, moneda_usd):
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_a, nombre_banco="Banco A", numero_cuenta="0102-1",
        tipo_cuenta="CORRIENTE", id_moneda=moneda_usd, saldo_actual=Decimal("100.00"),
    )


# ── MonedaViewSet ─────────────────────────────────────────────────────────────

class TestMonedaViewSet:
    URL = "/api/finanzas/monedas/"

    def test_list_incluye_generica(self, client_a, moneda_usd):
        resp = client_a.get(self.URL)
        assert resp.status_code == 200
        codigos = {m["codigo_iso"] for m in resp.json()["results"]}
        assert "USD" in codigos

    def test_list_incluye_propia_no_la_ajena(self, client_b, moneda_privada_a):
        """B no debe ver la moneda privada de A (R-CODE-1)."""
        resp = client_b.get(self.URL)
        assert resp.status_code == 200
        codigos = {m["codigo_iso"] for m in resp.json()["results"]}
        assert "TKA" not in codigos

    def test_dueña_si_ve_su_moneda_privada(self, client_a, moneda_privada_a):
        resp = client_a.get(self.URL)
        codigos = {m["codigo_iso"] for m in resp.json()["results"]}
        assert "TKA" in codigos

    def test_activas_filtra_por_monedaempresaactiva(
        self, client_a, empresa_a, moneda_privada_a
    ):
        """`activas` devuelve solo las monedas marcadas activas para la empresa."""
        MonedaEmpresaActiva.objects.create(
            empresa=empresa_a, moneda=moneda_privada_a, activa=True
        )
        resp = client_a.get(self.URL + "activas/")
        assert resp.status_code == 200
        codigos = {m["codigo_iso"] for m in resp.json()["results"]}
        assert codigos == {"TKA"}

    def test_sin_auth_401(self, moneda_usd):
        resp = APIClient().get(self.URL)
        assert resp.status_code == 401


# ── TasaCambioViewSet ─────────────────────────────────────────────────────────

class TestTasaCambioViewSet:
    URL = "/api/finanzas/tasas-cambio/"

    def test_ambas_empresas_ven_la_tasa_bcv_global(self, client_a, client_b, tasa_bcv):
        for client in (client_a, client_b):
            resp = client.get(self.URL)
            assert resp.status_code == 200
            ids = {t["id_tasa_cambio"] for t in resp.json()["results"]}
            assert str(tasa_bcv.id_tasa_cambio) in ids

    def test_tasa_privada_no_visible_para_otra_empresa(
        self, client_b, tasa_privada_a
    ):
        resp = client_b.get(self.URL)
        ids = {t["id_tasa_cambio"] for t in resp.json()["results"]}
        assert str(tasa_privada_a.id_tasa_cambio) not in ids

    def test_dueña_ve_su_tasa_privada(self, client_a, tasa_privada_a):
        resp = client_a.get(self.URL)
        ids = {t["id_tasa_cambio"] for t in resp.json()["results"]}
        assert str(tasa_privada_a.id_tasa_cambio) in ids


# ── MetodoPagoViewSet ─────────────────────────────────────────────────────────

class TestMetodoPagoViewSet:
    URL = "/api/finanzas/metodos-pago/"

    def test_list_incluye_generico_y_propio(
        self, client_a, metodo_generico, metodo_privado_a
    ):
        resp = client_a.get(self.URL)
        assert resp.status_code == 200
        nombres = {m["nombre_metodo"] for m in resp.json()["results"]}
        assert "Efectivo Global" in nombres
        assert "Zelle Empresa A" in nombres

    def test_metodo_privado_ajeno_no_visible(self, client_b, metodo_privado_a):
        resp = client_b.get(self.URL)
        nombres = {m["nombre_metodo"] for m in resp.json()["results"]}
        assert "Zelle Empresa A" not in nombres

    def test_buscar_reutilizar_lista_genericos(self, client_a, metodo_generico):
        resp = client_a.get(self.URL + "buscar_reutilizar/")
        assert resp.status_code == 200
        data = resp.json()
        results = data["results"] if isinstance(data, dict) else data
        nombres = {m["nombre_metodo"] for m in results}
        assert "Efectivo Global" in nombres


# ── CajaViewSet ───────────────────────────────────────────────────────────────

class TestCajaViewSet:
    URL = "/api/finanzas/cajas/"

    def test_tipo_caja_choices(self, client_a):
        resp = client_a.get(self.URL + "tipo-caja-choices/")
        assert resp.status_code == 200
        values = {row["value"] for row in resp.json()}
        assert {"REGISTRADORA", "GERENCIA", "MATRIZ", "OTRO"} <= values

    def test_list_solo_cajas_de_empresa_propia(self, client_a, client_b, caja_virtual_a):
        resp_a = client_a.get(self.URL)
        assert resp_a.status_code == 200
        nombres_a = {c["nombre"] for c in resp_a.json()["results"]}
        assert "Caja Virtual A" in nombres_a

        resp_b = client_b.get(self.URL)
        nombres_b = {c["nombre"] for c in resp_b.json()["results"]}
        assert "Caja Virtual A" not in nombres_b

    def test_movimientos_caja_banco_vacio_200(self, client_a, caja_virtual_a):
        url = f"{self.URL}{caja_virtual_a.id_caja}/movimientos-caja-banco/"
        resp = client_a.get(url, {"tipo": "INGRESO", "concepto": "x"})
        assert resp.status_code == 200

    def test_movimientos_caja_banco_de_otra_empresa_404(self, client_b, caja_virtual_a):
        url = f"{self.URL}{caja_virtual_a.id_caja}/movimientos-caja-banco/"
        resp = client_b.get(url)
        assert resp.status_code == 404


# ── CuentaBancariaEmpresaViewSet ──────────────────────────────────────────────

class TestCuentaBancariaViewSet:
    URL = "/api/finanzas/cuentas-bancarias-empresa/"

    def test_list_aislada_por_empresa(self, client_a, client_b, cuenta_bancaria_a):
        resp_a = client_a.get(self.URL)
        assert resp_a.status_code == 200
        bancos_a = {c["nombre_banco"] for c in resp_a.json()["results"]}
        assert "Banco A" in bancos_a

        resp_b = client_b.get(self.URL)
        bancos_b = {c["nombre_banco"] for c in resp_b.json()["results"]}
        assert "Banco A" not in bancos_b

    def test_movimientos_cuenta_bancaria_200(self, client_a, cuenta_bancaria_a):
        url = f"{self.URL}{cuenta_bancaria_a.id_cuenta_bancaria}/movimientos-cuenta-bancaria/"
        resp = client_a.get(url, {"fecha_inicio": "2026-01-01"})
        assert resp.status_code == 200


# ── SesionCajaFisicaViewSet ───────────────────────────────────────────────────

class TestSesionCajaFisicaViewSet:
    URL = "/api/finanzas/sesiones-caja/"

    def test_list_vacia_200(self, client_a):
        resp = client_a.get(self.URL)
        assert resp.status_code == 200

    def test_crear_sin_caja_fisica_400(self, client_a):
        """`perform_create` exige `caja_fisica_principal` → ValidationError 400."""
        resp = client_a.post(self.URL, {}, format="json")
        assert resp.status_code == 400

    def test_sin_auth_401(self):
        resp = APIClient().get(self.URL)
        assert resp.status_code == 401
