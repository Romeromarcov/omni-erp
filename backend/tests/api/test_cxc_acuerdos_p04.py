"""
P0-4 (auditoría integral 2026-06-10) — BUG-A2 + BUG-M3 en apps/cxc.

BUG-A2 — registrar-pago de cuotas de acuerdo:
- los pagos parciales se ACUMULAN en monto_pagado (antes se sobrescribían);
- monto con min_value > 0 (antes aceptaba 0 y negativos);
- pago en moneda distinta a la del acuerdo se convierte con TasaCambio
  (100 VES NO saldan una cuota de 100 USD); sin tasa disponible → 400.

BUG-M3 — generar_cuotas / AcuerdoPagoCreateSerializer:
- las cuotas nunca exceden el monto_total del acuerdo (cap por cuota);
- monto_total > 0, monto_cuota > 0 y <= total, porcentaje 0–100, no ambos;
- FK cxc/gestion de otra empresa → 400 (aislamiento multi-tenant).

(El doble pago concurrente se cubre en
tests/integration/test_cxc_acuerdos_concurrencia.py.)
"""
import datetime
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cxc.models import AcuerdoPago
from apps.cxc.services.cuotas import generar_cuotas
from apps.finanzas.models import MetodoPago, Moneda, Pago, TasaCambio

pytestmark = pytest.mark.django_db

URL = "/api/cobranza/acuerdos/"


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def metodo_a(empresa_a, moneda_usd):
    metodo = MetodoPago.objects.create(
        nombre_metodo="Transferencia A", tipo_metodo="ELECTRONICO", empresa=empresa_a
    )
    metodo.monedas.add(moneda_usd)
    return metodo


@pytest.fixture
def moneda_ves(db):
    return Moneda.objects.create(
        nombre="Bolívar", codigo_iso="VES", simbolo="Bs",
        tipo_moneda="fiat", es_generica=True,
    )


def _payload_acuerdo(**overrides):
    base = {
        "cliente_id": "CLI-P04",
        "cliente_nombre": "Cliente P04",
        "monto_total": "100.0000",
        "periodicidad": "unico",
        "plazo_total_dias": 30,
        "fecha_inicio": "2026-06-10",
        "moneda_codigo": "USD",
    }
    base.update(overrides)
    return base


@pytest.fixture
def acuerdo_a(client_a):
    """Acuerdo USD de 100 con una única cuota de 100."""
    resp = client_a.post(URL, _payload_acuerdo(), format="json")
    assert resp.status_code == 201, resp.content
    return AcuerdoPago.objects.get()


def _pagar(client, acuerdo, cuota, monto, moneda, metodo):
    return client.post(
        f"{URL}{acuerdo.id}/registrar-pago/",
        {
            "cuota_id": str(cuota.id),
            "monto": str(monto),
            "moneda_id": str(moneda.id_moneda),
            "metodo_pago_id": str(metodo.id_metodo_pago),
        },
        format="json",
    )


# ── BUG-A2: acumulación de pagos parciales ────────────────────────────────────

class TestPagosParcialesAcumulan:
    def test_dos_parciales_se_suman(self, client_a, acuerdo_a, moneda_usd, metodo_a):
        cuota = acuerdo_a.cuotas.get()
        resp = _pagar(client_a, acuerdo_a, cuota, "40.0000", moneda_usd, metodo_a)
        assert resp.status_code == 200, resp.content
        cuota.refresh_from_db()
        assert cuota.monto_pagado == Decimal("40.0000")
        assert cuota.estado == "parcial"

        resp = _pagar(client_a, acuerdo_a, cuota, "30.0000", moneda_usd, metodo_a)
        assert resp.status_code == 200, resp.content
        cuota.refresh_from_db()
        # ANTES (bug): monto_pagado quedaba en 30 (sobrescrito).
        assert cuota.monto_pagado == Decimal("70.0000")
        assert cuota.estado == "parcial"

    def test_parciales_completan_la_cuota_y_el_acuerdo(
        self, client_a, acuerdo_a, moneda_usd, metodo_a
    ):
        cuota = acuerdo_a.cuotas.get()
        _pagar(client_a, acuerdo_a, cuota, "60.0000", moneda_usd, metodo_a)
        resp = _pagar(client_a, acuerdo_a, cuota, "40.0000", moneda_usd, metodo_a)
        assert resp.status_code == 200, resp.content
        cuota.refresh_from_db()
        assert cuota.monto_pagado == Decimal("100.0000")
        assert cuota.estado == "pagado"
        acuerdo_a.refresh_from_db()
        assert acuerdo_a.estado == "cumplido"
        # Cada pago parcial genera su propio finanzas.Pago.
        assert Pago.objects.count() == 2

    def test_cuota_completada_no_acepta_mas_pagos(
        self, client_a, acuerdo_a, moneda_usd, metodo_a
    ):
        cuota = acuerdo_a.cuotas.get()
        _pagar(client_a, acuerdo_a, cuota, "60.0000", moneda_usd, metodo_a)
        _pagar(client_a, acuerdo_a, cuota, "40.0000", moneda_usd, metodo_a)
        resp = _pagar(client_a, acuerdo_a, cuota, "10.0000", moneda_usd, metodo_a)
        assert resp.status_code == 400
        assert resp.json() == {"error": "Esta cuota ya está pagada"}


# ── BUG-A2: min_value en monto ────────────────────────────────────────────────

class TestMontoMinimo:
    @pytest.mark.parametrize("monto", ["0", "0.0000", "-1", "-100.5"])
    def test_monto_cero_o_negativo_400(self, client_a, acuerdo_a, moneda_usd, metodo_a, monto):
        cuota = acuerdo_a.cuotas.get()
        resp = _pagar(client_a, acuerdo_a, cuota, monto, moneda_usd, metodo_a)
        assert resp.status_code == 400, resp.content
        assert "monto" in resp.json()
        cuota.refresh_from_db()
        assert cuota.monto_pagado == Decimal("0")
        assert cuota.estado == "pendiente"
        assert Pago.objects.count() == 0


# ── BUG-A2: conversión de moneda pago → moneda del acuerdo ────────────────────

class TestConversionMoneda:
    def test_100_ves_no_saldan_cuota_de_100_usd(
        self, client_a, acuerdo_a, moneda_usd, moneda_ves, metodo_a
    ):
        """Con tasa VES→USD = 0.0274: 100 VES aplican 2.74 USD, NO 100 USD."""
        TasaCambio.objects.create(
            id_empresa=None, id_moneda_origen=moneda_ves, id_moneda_destino=moneda_usd,
            tipo_tasa="OFICIAL_BCV", valor_tasa=Decimal("0.02740000"),
            fecha_tasa=timezone.now().date(),
        )
        cuota = acuerdo_a.cuotas.get()
        resp = _pagar(client_a, acuerdo_a, cuota, "100.0000", moneda_ves, metodo_a)
        assert resp.status_code == 200, resp.content
        cuota.refresh_from_db()
        # ANTES (bug): 100 VES marcaban la cuota de 100 USD como "pagado".
        assert cuota.estado == "parcial"
        assert cuota.monto_pagado == Decimal("2.7400")
        # El Pago conserva el monto en su moneda original.
        pago = Pago.objects.get()
        assert pago.monto == Decimal("100.0000")
        assert pago.id_moneda == moneda_ves

    def test_pagos_en_dos_monedas_acumulan_convertidos(
        self, client_a, acuerdo_a, moneda_usd, moneda_ves, metodo_a
    ):
        TasaCambio.objects.create(
            id_empresa=None, id_moneda_origen=moneda_ves, id_moneda_destino=moneda_usd,
            tipo_tasa="OFICIAL_BCV", valor_tasa=Decimal("0.02500000"),
            fecha_tasa=timezone.now().date(),
        )
        cuota = acuerdo_a.cuotas.get()
        _pagar(client_a, acuerdo_a, cuota, "2000.0000", moneda_ves, metodo_a)  # 50 USD
        resp = _pagar(client_a, acuerdo_a, cuota, "50.0000", moneda_usd, metodo_a)
        assert resp.status_code == 200, resp.content
        cuota.refresh_from_db()
        assert cuota.monto_pagado == Decimal("100.0000")
        assert cuota.estado == "pagado"

    def test_moneda_distinta_sin_tasa_rechaza_400(
        self, client_a, acuerdo_a, moneda_ves, metodo_a
    ):
        """Sin tasa VES→USD el pago se rechaza: jamás tasa implícita 1:1."""
        cuota = acuerdo_a.cuotas.get()
        resp = _pagar(client_a, acuerdo_a, cuota, "100.0000", moneda_ves, metodo_a)
        assert resp.status_code == 400, resp.content
        assert resp.json()["code"] == "tasa_no_disponible"
        cuota.refresh_from_db()
        assert cuota.estado == "pendiente"
        assert cuota.monto_pagado == Decimal("0")
        assert Pago.objects.count() == 0


# ── BUG-M3: generar_cuotas capeado al total ───────────────────────────────────

class TestCuotasNoExcedenTotal:
    def test_monto_cuota_fijo_capea_cuotas_intermedias(self, client_a):
        """total=100, cuota fija=80, 3 períodos → [80, 20], nunca 240."""
        resp = client_a.post(
            URL,
            _payload_acuerdo(
                monto_total="100.0000", periodicidad="semanal",
                plazo_total_dias=21, monto_cuota="80.0000",
            ),
            format="json",
        )
        assert resp.status_code == 201, resp.content
        acuerdo = AcuerdoPago.objects.get()
        cuotas = list(acuerdo.cuotas.order_by("numero_cuota"))
        assert sum(c.monto for c in cuotas) == Decimal("100.0000")
        assert [c.monto for c in cuotas] == [Decimal("80.0000"), Decimal("20.0000")]

    def test_porcentaje_alto_capea_al_total(self, client_a):
        """total=100, 60 % por cuota, 3 períodos → [60, 40] (no 60+60+(-20))."""
        resp = client_a.post(
            URL,
            _payload_acuerdo(
                monto_total="100.0000", periodicidad="semanal",
                plazo_total_dias=21, porcentaje_abono="60.00",
            ),
            format="json",
        )
        assert resp.status_code == 201, resp.content
        acuerdo = AcuerdoPago.objects.get()
        cuotas = list(acuerdo.cuotas.order_by("numero_cuota"))
        assert sum(c.monto for c in cuotas) == Decimal("100.0000")
        assert [c.monto for c in cuotas] == [Decimal("60.0000"), Decimal("40.0000")]

    def test_servicio_directo_nunca_excede_total(self):
        """Propiedad del service puro: sum(cuotas) == total para cuota fija grande."""
        cuotas = generar_cuotas(
            acuerdo=None,
            fecha_inicio=datetime.date(2026, 6, 10),
            plazo_total_dias=90,
            periodicidad="mensual",
            monto_total=Decimal("100.00"),
            monto_cuota=Decimal("45.00"),
        )
        montos = [c["monto"] for c in cuotas]
        assert sum(montos) == Decimal("100.00")
        assert all(m > 0 for m in montos)

    def test_servicio_rechaza_total_no_positivo(self):
        with pytest.raises(ValueError):
            generar_cuotas(
                acuerdo=None,
                fecha_inicio=datetime.date(2026, 6, 10),
                plazo_total_dias=30,
                periodicidad="unico",
                monto_total=Decimal("0"),
            )


# ── BUG-M3: validaciones del serializer de creación ──────────────────────────

class TestValidacionesCrearAcuerdo:
    @pytest.mark.parametrize("monto_total", ["0", "-100"])
    def test_monto_total_no_positivo_400(self, client_a, monto_total):
        resp = client_a.post(URL, _payload_acuerdo(monto_total=monto_total), format="json")
        assert resp.status_code == 400, resp.content
        assert "monto_total" in resp.json()
        assert AcuerdoPago.objects.count() == 0

    def test_monto_cuota_no_positivo_400(self, client_a):
        resp = client_a.post(URL, _payload_acuerdo(monto_cuota="-10"), format="json")
        assert resp.status_code == 400, resp.content
        assert AcuerdoPago.objects.count() == 0

    def test_monto_cuota_mayor_al_total_400(self, client_a):
        resp = client_a.post(
            URL, _payload_acuerdo(monto_total="100", monto_cuota="150"), format="json"
        )
        assert resp.status_code == 400, resp.content
        assert AcuerdoPago.objects.count() == 0

    @pytest.mark.parametrize("pct", ["0", "-5", "150"])
    def test_porcentaje_fuera_de_rango_400(self, client_a, pct):
        resp = client_a.post(URL, _payload_acuerdo(porcentaje_abono=pct), format="json")
        assert resp.status_code == 400, resp.content
        assert AcuerdoPago.objects.count() == 0

    def test_monto_cuota_y_porcentaje_juntos_400(self, client_a):
        resp = client_a.post(
            URL,
            _payload_acuerdo(monto_cuota="50", porcentaje_abono="50"),
            format="json",
        )
        assert resp.status_code == 400, resp.content
        assert AcuerdoPago.objects.count() == 0


# ── BUG-M3: aislamiento multi-tenant de los FK cxc / gestion ─────────────────

class TestAislamientoFK:
    def _cxc_de(self, empresa):
        from apps.crm.models import Cliente
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        cliente = Cliente.objects.create(
            id_empresa=empresa,
            razon_social=f"Cliente {empresa.nombre_legal}",
            rif="J-55555555-5",
            tipo_cliente="CREDITO",
        )
        return CuentaPorCobrar.objects.create(
            cliente=cliente,
            empresa=empresa,
            monto=Decimal("100.00"),
            fecha_emision=timezone.now().date(),
            fecha_vencimiento=timezone.now().date(),
            estado="pendiente",
        )

    def test_cxc_de_otra_empresa_400(self, client_a, empresa_b):
        cxc_b = self._cxc_de(empresa_b)
        resp = client_a.post(URL, _payload_acuerdo(cxc=str(cxc_b.id)), format="json")
        assert resp.status_code == 400, resp.content
        assert "cxc" in resp.json()
        assert AcuerdoPago.objects.count() == 0

    def test_cxc_propia_ok(self, client_a, empresa_a):
        cxc_a = self._cxc_de(empresa_a)
        resp = client_a.post(URL, _payload_acuerdo(cxc=str(cxc_a.id)), format="json")
        assert resp.status_code == 201, resp.content
        assert AcuerdoPago.objects.get().cxc_id == cxc_a.id

    def test_gestion_de_otra_empresa_400(self, client_a, empresa_b):
        from apps.cxc.models import GestionCobranza

        gestion_b = GestionCobranza.objects.create(
            empresa=empresa_b,
            cliente_id="CLI-B",
            canal="email",
            resultado="contactado",
            fecha_gestion=timezone.now(),
        )
        resp = client_a.post(URL, _payload_acuerdo(gestion=str(gestion_b.id)), format="json")
        assert resp.status_code == 400, resp.content
        assert "gestion" in resp.json()
        assert AcuerdoPago.objects.count() == 0
