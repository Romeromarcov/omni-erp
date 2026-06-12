"""
Integración end-to-end del cierre de caja física (FIX hallazgo P0-8).

``CajaFisica.realizar_cierre`` leía/escribía ``saldo_actual`` y
``fecha_ultimo_cierre``, campos eliminados en finanzas/0021 → AttributeError
en runtime y el corte nunca persistía. Además el frontend llama
``POST /api/finanzas/cajas-fisicas/{id}/cierre`` y esa ruta no existía.

Decisión (Opción A): el corte se re-deriva de los datos persistentes — el
último ``MovimientoCajaBanco`` de tipo ``CIERRE`` de la caja aporta el saldo
base (``saldo_nuevo``) y el inicio exclusivo de la ventana (fecha + hora).
Cada cierre persiste su propio movimiento CIERRE, por lo que el siguiente
solo cuenta lo nuevo.

Cubre por API: abrir movimientos → cerrar → corte persistido → segundo cierre
solo cuenta lo nuevo; descuadre con ajuste; validaciones de entrada; límite
anterior al último cierre; aislamiento multi-tenant (R-CODE-1).
"""
import datetime
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.finanzas.models import MovimientoCajaBanco

pytestmark = pytest.mark.django_db


def _crear_mov(caja, user, fecha, hora, tipo, monto, moneda):
    return MovimientoCajaBanco.objects.create(
        id_empresa=caja.empresa,
        fecha_movimiento=fecha,
        hora_movimiento=hora,
        tipo_movimiento=tipo,
        monto=Decimal(monto),
        id_moneda=moneda,
        concepto="mov cierre e2e",
        id_caja_fisica=caja,
        saldo_anterior=Decimal("0.00"),
        saldo_nuevo=Decimal("0.00"),
        id_usuario_registro=user,
    )


@pytest.fixture
def client_a(user_a):
    client = APIClient()
    client.force_authenticate(user=user_a)
    return client


URL = "/api/finanzas/cajas-fisicas/{}/cierre/"


class TestCierreCajaFisicaEndToEnd:
    def test_flujo_completo_dos_cierres(self, client_a, caja_fisica_a, user_a, moneda_usd):
        """Movimientos → cierre (corte persistido) → segundo cierre solo
        cuenta lo nuevo a partir del corte anterior."""
        caja = caja_fisica_a
        dia = datetime.date(2026, 6, 10)
        m = moneda_usd
        _crear_mov(caja, user_a, dia, datetime.time(9, 0), "INGRESO", "100.00", m)
        _crear_mov(caja, user_a, dia, datetime.time(10, 0), "EGRESO", "30.00", m)

        # Primer cierre: base 0.00 → teórico 70.00; contado 70.00 → sin ajuste
        resp = client_a.post(
            URL.format(caja.id_caja_fisica),
            {"saldo_real": "70.00", "hasta": "2026-06-10T12:00:00"},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        assert Decimal(str(resp.data["ingresos"])) == Decimal("100.00")
        assert Decimal(str(resp.data["egresos"])) == Decimal("30.00")
        assert Decimal(str(resp.data["saldo_teorico"])) == Decimal("70.00")
        assert Decimal(str(resp.data["descuadre"])) == Decimal("0.00")
        assert resp.data["movimiento_ajuste_id"] is None

        # El corte queda PERSISTIDO como MovimientoCajaBanco tipo CIERRE
        cierre1 = MovimientoCajaBanco.objects.get(id_movimiento=resp.data["movimiento_cierre_id"])
        assert cierre1.tipo_movimiento == "CIERRE"
        assert cierre1.saldo_anterior == Decimal("0.00")
        assert cierre1.saldo_nuevo == Decimal("70.00")
        assert cierre1.fecha_movimiento == dia
        assert cierre1.hora_movimiento == datetime.time(12, 0)

        # Movimientos nuevos tras el corte
        _crear_mov(caja, user_a, dia, datetime.time(14, 0), "INGRESO", "25.00", m)
        _crear_mov(caja, user_a, dia, datetime.time(15, 0), "EGRESO", "5.00", m)

        # Segundo cierre: SOLO cuenta lo nuevo → base 70 + 25 - 5 = 90
        resp2 = client_a.post(
            URL.format(caja.id_caja_fisica),
            {"saldo_real": "90.00", "hasta": "2026-06-10T18:00:00"},
            format="json",
        )
        assert resp2.status_code == 200, resp2.data
        assert Decimal(str(resp2.data["ingresos"])) == Decimal("25.00")
        assert Decimal(str(resp2.data["egresos"])) == Decimal("5.00")
        assert Decimal(str(resp2.data["saldo_teorico"])) == Decimal("90.00")
        assert Decimal(str(resp2.data["descuadre"])) == Decimal("0.00")
        cierre2 = MovimientoCajaBanco.objects.get(id_movimiento=resp2.data["movimiento_cierre_id"])
        assert cierre2.saldo_anterior == Decimal("70.00")
        assert cierre2.saldo_nuevo == Decimal("90.00")
        assert caja.movimientos.filter(tipo_movimiento="CIERRE").count() == 2

    def test_descuadre_crea_ajuste_y_no_se_doble_cuenta(
        self, client_a, caja_fisica_a, user_a, moneda_usd
    ):
        """El ajuste por descuadre se fecha en el límite del cierre → queda en
        la ventana cerrada y un cierre posterior no lo vuelve a contar."""
        caja = caja_fisica_a
        dia = datetime.date(2026, 6, 10)
        _crear_mov(caja, user_a, dia, datetime.time(9, 0), "INGRESO", "100.00", moneda_usd)

        # Teórico 100, contado 80 → ajuste NEGATIVO de 20
        resp = client_a.post(
            URL.format(caja.id_caja_fisica),
            {"saldo_real": "80.00", "hasta": "2026-06-10T12:00:00"},
            format="json",
        )
        assert resp.status_code == 200, resp.data
        assert Decimal(str(resp.data["descuadre"])) == Decimal("-20.00")
        ajuste = MovimientoCajaBanco.objects.get(id_movimiento=resp.data["movimiento_ajuste_id"])
        assert ajuste.tipo_movimiento == "AJUSTE_NEGATIVO"
        assert ajuste.monto == Decimal("20.00")
        assert (ajuste.fecha_movimiento, ajuste.hora_movimiento) == (dia, datetime.time(12, 0))

        # Cierre siguiente sin movimientos nuevos: base 80, teórico 80
        # (el ajuste del cierre anterior NO se recuenta).
        resp2 = client_a.post(
            URL.format(caja.id_caja_fisica),
            {"saldo_real": "80.00", "hasta": "2026-06-10T18:00:00"},
            format="json",
        )
        assert resp2.status_code == 200, resp2.data
        assert Decimal(str(resp2.data["ingresos"])) == Decimal("0.00")
        assert Decimal(str(resp2.data["egresos"])) == Decimal("0.00")
        assert Decimal(str(resp2.data["saldo_teorico"])) == Decimal("80.00")
        assert Decimal(str(resp2.data["descuadre"])) == Decimal("0.00")

    def test_limite_anterior_al_ultimo_cierre_rechazado(self, client_a, caja_fisica_a):
        resp = client_a.post(
            URL.format(caja_fisica_a.id_caja_fisica),
            {"saldo_real": "0.00", "hasta": "2026-06-10T12:00:00"},
            format="json",
        )
        assert resp.status_code == 200
        resp2 = client_a.post(
            URL.format(caja_fisica_a.id_caja_fisica),
            {"saldo_real": "0.00", "hasta": "2026-06-10T08:00:00"},
            format="json",
        )
        assert resp2.status_code == 400
        assert "anterior al último cierre" in resp2.data["error"]

    def test_validaciones_de_entrada(self, client_a, caja_fisica_a):
        url = URL.format(caja_fisica_a.id_caja_fisica)
        resp = client_a.post(url, {}, format="json")
        assert resp.status_code == 400
        assert "saldo_real" in resp.data["error"]

        resp = client_a.post(url, {"saldo_real": "no-numero"}, format="json")
        assert resp.status_code == 400

        resp = client_a.post(url, {"saldo_real": "10.00", "hasta": "fecha-mala"}, format="json")
        assert resp.status_code == 400

    def test_aislamiento_multi_tenant(self, caja_fisica_a, user_b):
        """R-CODE-1: un usuario de la empresa B no puede cerrar la caja de A
        (404, sin filtrar siquiera la existencia)."""
        client_b = APIClient()
        client_b.force_authenticate(user=user_b)
        resp = client_b.post(
            URL.format(caja_fisica_a.id_caja_fisica),
            {"saldo_real": "0.00"},
            format="json",
        )
        assert resp.status_code == 404
        assert not caja_fisica_a.movimientos.filter(tipo_movimiento="CIERRE").exists()

    def test_requiere_autenticacion(self, caja_fisica_a):
        client = APIClient()
        resp = client.post(URL.format(caja_fisica_a.id_caja_fisica), {"saldo_real": "0.00"}, format="json")
        assert resp.status_code in (401, 403)
