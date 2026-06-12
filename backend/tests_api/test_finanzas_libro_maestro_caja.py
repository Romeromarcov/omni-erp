"""
Libro maestro de caja — Capa B §6.8 (tropicalización VE).

Cobertura del reporte consolidado de TODAS las cajas (físicas y virtuales):

- saldo inicial / entradas / salidas / saldo final por caja, con montos
  verificados a mano (movimientos antes, dentro y después del rango).
- multimoneda: una caja física con movimientos en USD y VES produce una fila
  por moneda; los totales se agrupan por moneda y NUNCA se suman entre sí.
- filtros: moneda, tipo (VIRTUAL/FISICA), incluir_inactivas, periodo YYYY-MM.
- validaciones de parámetros → 400; R-CODE-1: empresa ajena → 404 y las cajas
  de otra empresa jamás aparecen ni contaminan totales.
"""

from datetime import date, time
from decimal import Decimal

import pytest

from apps.finanzas.models import Caja, CajaFisica, Moneda, MovimientoCajaBanco

pytestmark = pytest.mark.django_db

BASE_URL = "/api/finanzas/libro-maestro-caja/"

DESDE = date(2026, 6, 10)
HASTA = date(2026, 6, 11)


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def moneda_ves(db):
    return Moneda.objects.create(
        nombre="Bolívar Digital", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat"
    )


@pytest.fixture
def caja_usd(db, empresa_a, moneda_usd):
    return Caja.objects.create(
        empresa=empresa_a, nombre="Caja USD", tipo_caja="MATRIZ", moneda=moneda_usd
    )


@pytest.fixture
def caja_ves(db, empresa_a, moneda_ves):
    return Caja.objects.create(
        empresa=empresa_a, nombre="Caja VES", tipo_caja="REGISTRADORA", moneda=moneda_ves
    )


@pytest.fixture
def caja_fisica(db, empresa_a):
    return CajaFisica.objects.create(
        empresa=empresa_a, nombre="Caja Física Mostrador", identificador_dispositivo="disp-lm-001"
    )


def _mov(
    empresa,
    usuario,
    *,
    tipo,
    monto,
    fecha,
    caja=None,
    caja_fisica=None,
    moneda=None,
):
    """Crea un MovimientoCajaBanco mínimo (el libro deriva saldos del log)."""
    return MovimientoCajaBanco.objects.create(
        id_empresa=empresa,
        fecha_movimiento=fecha,
        hora_movimiento=time(10, 0),
        tipo_movimiento=tipo,
        monto=Decimal(monto),
        id_moneda=moneda,
        concepto=f"{tipo} test",
        id_caja=caja,
        id_caja_fisica=caja_fisica,
        saldo_anterior=Decimal("0.00"),
        saldo_nuevo=Decimal("0.00"),
        id_usuario_registro=usuario,
    )


@pytest.fixture
def escenario(db, empresa_a, user_a, moneda_usd, moneda_ves, caja_usd, caja_ves, caja_fisica):
    """
    Escenario con movimientos antes / dentro / después del rango [06-10, 06-11].

    caja_usd (virtual USD):
      antes:   INGRESO 100.00 (06-01), EGRESO 30.00 (06-05)    → inicial  70.00
      ventana: INGRESO 50.25, TRANSFERENCIA_ENTRADA 5.00,
               EGRESO 20.10, AJUSTE_NEGATIVO 1.15, CIERRE 0.00 → +55.25 / −21.25
      después: INGRESO 999.99 (06-12)                          → excluido
      final esperado: 70.00 + 55.25 − 21.25 = 104.00

    caja_ves (virtual VES):
      ventana: INGRESO 1000.50 → inicial 0.00, final 1000.50

    caja_fisica (multimoneda):
      USD: antes INGRESO 10.00; ventana EGRESO 4.50 → inicial 10.00, final 5.50
      VES: ventana INGRESO 200.00                   → inicial 0.00, final 200.00
    """
    e, u = empresa_a, user_a
    # caja_usd — antes
    _mov(e, u, tipo="INGRESO", monto="100.00", fecha=date(2026, 6, 1), caja=caja_usd, moneda=moneda_usd)
    _mov(e, u, tipo="EGRESO", monto="30.00", fecha=date(2026, 6, 5), caja=caja_usd, moneda=moneda_usd)
    # caja_usd — ventana
    _mov(e, u, tipo="INGRESO", monto="50.25", fecha=DESDE, caja=caja_usd, moneda=moneda_usd)
    _mov(e, u, tipo="TRANSFERENCIA_ENTRADA", monto="5.00", fecha=DESDE, caja=caja_usd, moneda=moneda_usd)
    _mov(e, u, tipo="EGRESO", monto="20.10", fecha=HASTA, caja=caja_usd, moneda=moneda_usd)
    _mov(e, u, tipo="AJUSTE_NEGATIVO", monto="1.15", fecha=HASTA, caja=caja_usd, moneda=moneda_usd)
    _mov(e, u, tipo="CIERRE", monto="0.00", fecha=DESDE, caja=caja_usd, moneda=moneda_usd)
    # caja_usd — después (excluido)
    _mov(e, u, tipo="INGRESO", monto="999.99", fecha=date(2026, 6, 12), caja=caja_usd, moneda=moneda_usd)
    # caja_ves — ventana
    _mov(e, u, tipo="INGRESO", monto="1000.50", fecha=DESDE, caja=caja_ves, moneda=moneda_ves)
    # caja_fisica — USD
    _mov(e, u, tipo="INGRESO", monto="10.00", fecha=date(2026, 6, 1), caja_fisica=caja_fisica, moneda=moneda_usd)
    _mov(e, u, tipo="EGRESO", monto="4.50", fecha=HASTA, caja_fisica=caja_fisica, moneda=moneda_usd)
    # caja_fisica — VES
    _mov(e, u, tipo="INGRESO", monto="200.00", fecha=DESDE, caja_fisica=caja_fisica, moneda=moneda_ves)
    return {"caja_usd": caja_usd, "caja_ves": caja_ves, "caja_fisica": caja_fisica}


@pytest.fixture
def client_a(user_a):
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    from rest_framework.test import APIClient

    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


def _get_libro(client, empresa, **params):
    base = {"empresa": str(empresa.id_empresa), "desde": str(DESDE), "hasta": str(HASTA)}
    base.update(params)
    return client.get(BASE_URL, base)


def _fila(data, caja_id, moneda=None):
    return next(
        f for f in data["cajas"] if f["id_caja"] == str(caja_id) and f["moneda"] == moneda
    )


def _total(data, moneda):
    return next(t for t in data["totales_por_moneda"] if t["moneda"] == moneda)


# ─────────────────────────────────────────────
# Montos exactos por caja (a mano)
# ─────────────────────────────────────────────


class TestMontosExactos:
    def test_caja_virtual_usd(self, client_a, empresa_a, escenario):
        resp = _get_libro(client_a, empresa_a)
        assert resp.status_code == 200, resp.data
        fila = _fila(resp.data, escenario["caja_usd"].pk, "USD")
        assert fila["tipo"] == "VIRTUAL"
        assert fila["saldo_inicial"] == "70.00"
        assert fila["entradas"] == "55.25"
        assert fila["salidas"] == "21.25"
        assert fila["saldo_final"] == "104.00"
        # CIERRE (monto 0) cuenta como movimiento del rango pero no afecta sumas
        assert fila["movimientos"] == 5

    def test_caja_virtual_ves(self, client_a, empresa_a, escenario):
        resp = _get_libro(client_a, empresa_a)
        fila = _fila(resp.data, escenario["caja_ves"].pk, "VES")
        assert fila["saldo_inicial"] == "0.00"
        assert fila["entradas"] == "1000.50"
        assert fila["salidas"] == "0.00"
        assert fila["saldo_final"] == "1000.50"

    def test_caja_fisica_multimoneda_una_fila_por_moneda(self, client_a, empresa_a, escenario):
        resp = _get_libro(client_a, empresa_a)
        fisica_usd = _fila(resp.data, escenario["caja_fisica"].pk, "USD")
        fisica_ves = _fila(resp.data, escenario["caja_fisica"].pk, "VES")
        assert fisica_usd["tipo"] == "FISICA"
        assert fisica_usd["saldo_inicial"] == "10.00"
        assert fisica_usd["entradas"] == "0.00"
        assert fisica_usd["salidas"] == "4.50"
        assert fisica_usd["saldo_final"] == "5.50"
        assert fisica_ves["saldo_inicial"] == "0.00"
        assert fisica_ves["entradas"] == "200.00"
        assert fisica_ves["saldo_final"] == "200.00"

    def test_caja_virtual_sin_movimientos_aparece_en_cero(
        self, client_a, empresa_a, moneda_usd, escenario
    ):
        vacia = Caja.objects.create(empresa=empresa_a, nombre="Caja Nueva", moneda=moneda_usd)
        resp = _get_libro(client_a, empresa_a)
        fila = _fila(resp.data, vacia.pk, "USD")
        assert fila["saldo_inicial"] == "0.00"
        assert fila["saldo_final"] == "0.00"
        assert fila["movimientos"] == 0

    def test_caja_fisica_sin_movimientos_aparece_sin_moneda(self, client_a, empresa_a, escenario):
        vacia = CajaFisica.objects.create(
            empresa=empresa_a, nombre="Física Nueva", identificador_dispositivo="disp-lm-002"
        )
        resp = _get_libro(client_a, empresa_a)
        fila = _fila(resp.data, vacia.pk, None)
        assert fila["moneda"] is None
        assert fila["saldo_inicial"] == "0.00"
        assert fila["saldo_final"] == "0.00"


# ─────────────────────────────────────────────
# Totales por moneda: NUNCA se mezclan monedas
# ─────────────────────────────────────────────


class TestTotalesPorMoneda:
    def test_totales_usd_y_ves_separados(self, client_a, empresa_a, escenario):
        resp = _get_libro(client_a, empresa_a)
        # USD = caja_usd (70.00/55.25/21.25/104.00) + física USD (10.00/0/4.50/5.50)
        total_usd = _total(resp.data, "USD")
        assert total_usd["saldo_inicial"] == "80.00"
        assert total_usd["entradas"] == "55.25"
        assert total_usd["salidas"] == "25.75"
        assert total_usd["saldo_final"] == "109.50"
        assert total_usd["cajas"] == 2
        # VES = caja_ves (1000.50) + física VES (200.00)
        total_ves = _total(resp.data, "VES")
        assert total_ves["saldo_inicial"] == "0.00"
        assert total_ves["entradas"] == "1200.50"
        assert total_ves["salidas"] == "0.00"
        assert total_ves["saldo_final"] == "1200.50"
        assert total_ves["cajas"] == 2
        # Ningún total "global" suma USD + VES
        monedas = {t["moneda"] for t in resp.data["totales_por_moneda"]}
        assert monedas == {"USD", "VES"}


# ─────────────────────────────────────────────
# Filtros
# ─────────────────────────────────────────────


class TestFiltros:
    def test_filtro_moneda(self, client_a, empresa_a, escenario):
        resp = _get_libro(client_a, empresa_a, moneda="USD")
        assert resp.status_code == 200
        assert {f["moneda"] for f in resp.data["cajas"]} == {"USD"}
        assert {t["moneda"] for t in resp.data["totales_por_moneda"]} == {"USD"}

    def test_filtro_tipo_virtual(self, client_a, empresa_a, escenario):
        resp = _get_libro(client_a, empresa_a, tipo="VIRTUAL")
        assert {f["tipo"] for f in resp.data["cajas"]} == {"VIRTUAL"}

    def test_filtro_tipo_fisica(self, client_a, empresa_a, escenario):
        resp = _get_libro(client_a, empresa_a, tipo="FISICA")
        assert {f["tipo"] for f in resp.data["cajas"]} == {"FISICA"}
        assert len(resp.data["cajas"]) == 2  # USD y VES de la misma caja física

    def test_filtro_tipo_invalido_retorna_400(self, client_a, empresa_a, escenario):
        resp = _get_libro(client_a, empresa_a, tipo="OTRA")
        assert resp.status_code == 400

    def test_cajas_inactivas_excluidas_por_defecto(
        self, client_a, empresa_a, user_a, moneda_usd, escenario
    ):
        inactiva = Caja.objects.create(
            empresa=empresa_a, nombre="Caja Cerrada", moneda=moneda_usd, activa=False
        )
        _mov(empresa_a, user_a, tipo="INGRESO", monto="500.00", fecha=DESDE, caja=inactiva, moneda=moneda_usd)

        resp = _get_libro(client_a, empresa_a)
        ids = {f["id_caja"] for f in resp.data["cajas"]}
        assert str(inactiva.pk) not in ids
        # ...y NO contamina los totales USD
        assert _total(resp.data, "USD")["entradas"] == "55.25"

        resp = _get_libro(client_a, empresa_a, incluir_inactivas="true")
        ids = {f["id_caja"] for f in resp.data["cajas"]}
        assert str(inactiva.pk) in ids
        assert _total(resp.data, "USD")["entradas"] == "555.25"

    def test_periodo_mensual(self, client_a, empresa_a, escenario):
        resp = client_a.get(
            BASE_URL, {"empresa": str(empresa_a.id_empresa), "periodo": "2026-06"}
        )
        assert resp.status_code == 200, resp.data
        assert resp.data["fecha_desde"] == "2026-06-01"
        assert resp.data["fecha_hasta"] == "2026-06-30"
        # El mes completo incluye lo "antes" y lo "después" del escenario:
        # entradas USD caja virtual = 100.00 + 50.25 + 5.00 + 999.99 = 1155.24
        fila = _fila(resp.data, escenario["caja_usd"].pk, "USD")
        assert fila["saldo_inicial"] == "0.00"
        assert fila["entradas"] == "1155.24"
        assert fila["salidas"] == "51.25"
        assert fila["saldo_final"] == "1103.99"


# ─────────────────────────────────────────────
# Validación de parámetros
# ─────────────────────────────────────────────


class TestValidacionParametros:
    def test_sin_empresa_retorna_400(self, client_a, escenario):
        resp = client_a.get(BASE_URL, {"desde": str(DESDE), "hasta": str(HASTA)})
        assert resp.status_code == 400

    def test_sin_fechas_retorna_400(self, client_a, empresa_a, escenario):
        resp = client_a.get(BASE_URL, {"empresa": str(empresa_a.id_empresa)})
        assert resp.status_code == 400

    def test_fecha_malformada_retorna_400(self, client_a, empresa_a, escenario):
        resp = client_a.get(
            BASE_URL,
            {"empresa": str(empresa_a.id_empresa), "desde": "10-06-2026", "hasta": str(HASTA)},
        )
        assert resp.status_code == 400

    def test_periodo_malformado_retorna_400(self, client_a, empresa_a, escenario):
        resp = client_a.get(
            BASE_URL, {"empresa": str(empresa_a.id_empresa), "periodo": "junio-2026"}
        )
        assert resp.status_code == 400

    def test_desde_mayor_que_hasta_retorna_400(self, client_a, empresa_a, escenario):
        resp = client_a.get(
            BASE_URL,
            {"empresa": str(empresa_a.id_empresa), "desde": str(HASTA), "hasta": str(DESDE)},
        )
        assert resp.status_code == 400

    def test_requiere_autenticacion(self, escenario, empresa_a):
        from rest_framework.test import APIClient

        resp = APIClient().get(BASE_URL, {"empresa": str(empresa_a.id_empresa)})
        assert resp.status_code in (401, 403)


# ─────────────────────────────────────────────
# R-CODE-1: aislamiento multi-tenant
# ─────────────────────────────────────────────


class TestAislamientoTenant:
    def test_empresa_ajena_retorna_404(self, client_b, empresa_a, escenario):
        resp = _get_libro(client_b, empresa_a)
        assert resp.status_code == 404

    def test_cajas_de_otra_empresa_no_aparecen_ni_contaminan(
        self, client_a, empresa_a, empresa_b, user_b, moneda_usd, escenario
    ):
        caja_b = Caja.objects.create(empresa=empresa_b, nombre="Caja de B", moneda=moneda_usd)
        _mov(empresa_b, user_b, tipo="INGRESO", monto="7777.77", fecha=DESDE, caja=caja_b, moneda=moneda_usd)

        resp = _get_libro(client_a, empresa_a)
        assert resp.status_code == 200
        ids = {f["id_caja"] for f in resp.data["cajas"]}
        assert str(caja_b.pk) not in ids
        assert _total(resp.data, "USD")["entradas"] == "55.25"

    def test_usuario_b_ve_solo_sus_cajas(self, client_b, empresa_b, user_b, moneda_usd, escenario):
        caja_b = Caja.objects.create(empresa=empresa_b, nombre="Caja de B", moneda=moneda_usd)
        _mov(empresa_b, user_b, tipo="INGRESO", monto="7777.77", fecha=DESDE, caja=caja_b, moneda=moneda_usd)

        resp = _get_libro(client_b, empresa_b)
        assert resp.status_code == 200
        assert {f["id_caja"] for f in resp.data["cajas"]} == {str(caja_b.pk)}
        assert _total(resp.data, "USD")["entradas"] == "7777.77"


# ─────────────────────────────────────────────
# Service directo: validación de rango
# ─────────────────────────────────────────────


class TestServiceDirecto:
    def test_rango_invertido_lanza_value_error(self, empresa_a):
        from apps.finanzas.services_libro_caja import generar_libro_maestro_caja

        with pytest.raises(ValueError):
            generar_libro_maestro_caja(empresa_a, HASTA, DESDE)

    def test_tipo_invalido_lanza_value_error(self, empresa_a):
        from apps.finanzas.services_libro_caja import generar_libro_maestro_caja

        with pytest.raises(ValueError):
            generar_libro_maestro_caja(empresa_a, DESDE, HASTA, tipo="BANCO")

    def test_montos_decimal_en_service(self, empresa_a, escenario):
        """R-CODE-4: el service trabaja en Decimal de punta a punta."""
        from apps.finanzas.services_libro_caja import generar_libro_maestro_caja

        libro = generar_libro_maestro_caja(empresa_a, DESDE, HASTA)
        for fila in libro["cajas"]:
            for campo in ("saldo_inicial", "entradas", "salidas", "saldo_final"):
                assert isinstance(fila[campo], Decimal)
