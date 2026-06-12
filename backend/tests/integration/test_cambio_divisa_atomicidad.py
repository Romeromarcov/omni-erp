"""
TEST-5 / CTF-013 — Atomicidad del flujo de cambio de divisa (R-CODE-11).

`OperacionCambioDivisaSerializer.create` registra la operación + doble registro
financiero (egreso origen, comisión opcional, ingreso destino), los
`MovimientoCajaBanco`, el `Gasto` por la comisión y el asiento `CAMBIO_DIVISA`
en UNA sola `transaction.atomic`. Si la empresa exige contabilidad
(`contabilidad_activa=True`) y falta el mapeo `CAMBIO_DIVISA`, el ViewSet
responde 422 y NADA persiste.

Espeja `test_cobranza_atomicidad.py`.
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.finanzas.models import Caja, Moneda, MovimientoCajaBanco, TransaccionFinanciera
from apps.gastos.models import Gasto
from apps.tesoreria.models import OperacionCambioDivisa

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

URL = "/api/tesoreria/operaciones-cambio-divisa/"


def _cuenta(empresa, codigo, nombre, tipo="ACTIVO", naturaleza="DEUDORA"):
    from apps.contabilidad.models import PlanCuentas

    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=nombre,
        tipo_cuenta=tipo,
        naturaleza=naturaleza,
        nivel=1,
    )


def _mapeo_cambio_divisa(empresa):
    from apps.contabilidad.models import MapeoContable

    debe = _cuenta(empresa, "1105", "Caja VES", "ACTIVO", "DEUDORA")
    haber = _cuenta(empresa, "1106", "Caja USD", "ACTIVO", "ACREEDORA")
    return MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento="CAMBIO_DIVISA",
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla="Asiento CAMBIO_DIVISA {numero}",
        activo=True,
    )


@pytest.fixture
def empresa_contable(empresa_a):
    empresa_a.contabilidad_activa = True
    empresa_a.save(update_fields=["contabilidad_activa"])
    return empresa_a


@pytest.fixture
def moneda_ves(db):
    return Moneda.objects.create(
        nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat", es_generica=True
    )


@pytest.fixture
def caja_usd(empresa_a, moneda_usd):
    return Caja.objects.create(
        empresa=empresa_a, nombre="Caja USD", moneda=moneda_usd, tipo_caja="REGISTRADORA"
    )


@pytest.fixture
def caja_ves(empresa_a, moneda_ves):
    return Caja.objects.create(
        empresa=empresa_a, nombre="Caja VES", moneda=moneda_ves, tipo_caja="REGISTRADORA"
    )


def _payload(empresa, moneda_usd, moneda_ves, caja_usd, caja_ves, metodo, **extra):
    """VENTA de 100 USD a 36.50 → 3650 VES, comisión 2.50 USD."""
    data = {
        "empresa": empresa.id_empresa,
        "numero_operacion": "OP-ATOM-001",
        "fecha_operacion": "2026-06-12T10:00:00Z",
        "tipo_operacion": "VENTA",
        "moneda_origen": str(moneda_usd.id_moneda),
        "moneda_destino": str(moneda_ves.id_moneda),
        "monto_origen": "100.0000",
        "tasa_cambio": "36.500000",
        "monto_destino": "3650.0000",
        "comision": "2.5000",
        "caja_origen": caja_usd.id_caja,
        "caja_destino": caja_ves.id_caja,
        "metodo_pago_origen": str(metodo.id_metodo_pago),
        "metodo_pago_destino": str(metodo.id_metodo_pago),
        "observaciones": "Venta de divisas test",
    }
    data.update(extra)
    return data


def _nada_persistido():
    assert OperacionCambioDivisa.objects.count() == 0, "ATOMICIDAD: quedó la operación."
    assert TransaccionFinanciera.objects.count() == 0, "ATOMICIDAD: quedó TransaccionFinanciera."
    assert MovimientoCajaBanco.objects.count() == 0, "ATOMICIDAD: quedó MovimientoCajaBanco."
    assert Gasto.objects.count() == 0, "ATOMICIDAD: quedó el Gasto de la comisión."


class TestCambioDivisaAtomico:
    def test_camino_feliz_doble_registro_y_asiento_balanceado(
        self, client_a, empresa_contable, moneda_usd, moneda_ves, caja_usd, caja_ves, metodo_efectivo
    ):
        """Con mapeo CAMBIO_DIVISA: 201, 3 transacciones, Gasto y asiento balanceado.

        Montos verificados a mano (moneda base de la empresa = USD):
        - egreso 100.0000 USD  → monto_base_empresa = 100.00
        - comisión 2.5000 USD  → monto_base_empresa = 2.50
        - ingreso 3650.0000 VES → 3650 / 36.5 = monto_base_empresa 100.00
        """
        from apps.contabilidad.models import AsientoContable, DetalleAsiento

        _mapeo_cambio_divisa(empresa_contable)

        resp = client_a.post(
            URL,
            _payload(empresa_contable, moneda_usd, moneda_ves, caja_usd, caja_ves, metodo_efectivo),
            format="json",
        )
        assert resp.status_code == 201, f"Esperado 201, fue {resp.status_code}: {resp.data}"

        operacion = OperacionCambioDivisa.objects.get()
        assert operacion.monto_origen == Decimal("100.0000")
        assert operacion.monto_destino == Decimal("3650.0000")

        # Doble registro: egreso + comisión + ingreso, con monto_base_empresa correcto
        egresos = TransaccionFinanciera.objects.filter(tipo_transaccion="EGRESO").order_by(
            "-monto_transaccion"
        )
        ingreso = TransaccionFinanciera.objects.get(tipo_transaccion="INGRESO")
        assert egresos.count() == 2
        principal, comision = egresos
        assert principal.monto_transaccion == Decimal("100.0000")
        assert principal.monto_base_empresa == Decimal("100.00")
        assert principal.id_moneda_transaccion == moneda_usd
        assert comision.monto_transaccion == Decimal("2.5000")
        assert comision.monto_base_empresa == Decimal("2.50")
        assert ingreso.monto_transaccion == Decimal("3650.0000")
        assert ingreso.id_moneda_transaccion == moneda_ves
        assert ingreso.monto_base_empresa == Decimal("100.00")  # 3650 / 36.5
        # Usuario resuelto del request (antes quedaba None → IntegrityError)
        for t in (principal, comision, ingreso):
            assert t.id_usuario_registro.username == "user_empresa_a"

        assert MovimientoCajaBanco.objects.count() == 3
        gasto = Gasto.objects.get()
        assert gasto.monto == Decimal("2.50")
        assert gasto.id_empresa == empresa_contable

        # Asiento balanceado por monto_origen
        asiento = AsientoContable.objects.get(nombre_modelo_origen="OperacionCambioDivisa")
        detalles = DetalleAsiento.objects.filter(id_asiento=asiento)
        assert sum(d.debe for d in detalles) == sum(d.haber for d in detalles) == Decimal("100.0000")

    def test_rollback_total_si_falta_mapeo_y_contabilidad_activa(
        self, client_a, empresa_contable, moneda_usd, moneda_ves, caja_usd, caja_ves, metodo_efectivo
    ):
        """contabilidad_activa + sin mapeo CAMBIO_DIVISA → 422 y rollback total."""
        resp = client_a.post(
            URL,
            _payload(empresa_contable, moneda_usd, moneda_ves, caja_usd, caja_ves, metodo_efectivo),
            format="json",
        )
        assert resp.status_code == 422, f"Esperado 422, fue {resp.status_code}: {resp.data}"
        assert "CAMBIO_DIVISA" in str(resp.data.get("error", ""))
        _nada_persistido()

    def test_empresa_informal_sin_mapeo_procede_sin_asiento(
        self, client_a, empresa_a, moneda_usd, moneda_ves, caja_usd, caja_ves, metodo_efectivo
    ):
        """Sin contabilidad_activa y sin mapeo: 201 best-effort, sin asiento (R-PROD-3)."""
        from apps.contabilidad.models import AsientoContable

        resp = client_a.post(
            URL,
            _payload(empresa_a, moneda_usd, moneda_ves, caja_usd, caja_ves, metodo_efectivo),
            format="json",
        )
        assert resp.status_code == 201, f"Esperado 201, fue {resp.status_code}: {resp.data}"
        assert OperacionCambioDivisa.objects.count() == 1
        assert TransaccionFinanciera.objects.count() == 3
        assert AsientoContable.objects.count() == 0

    def test_sin_metodo_pago_400_sin_efectos(
        self, client_a, empresa_a, moneda_usd, moneda_ves, caja_usd, caja_ves, metodo_efectivo
    ):
        """TransaccionFinanciera exige método de pago: payload sin él → 400 limpio."""
        payload = _payload(empresa_a, moneda_usd, moneda_ves, caja_usd, caja_ves, metodo_efectivo)
        payload.pop("metodo_pago_origen")
        resp = client_a.post(URL, payload, format="json")
        assert resp.status_code == 400
        _nada_persistido()


class TestCambioDivisaAislamientoTenant:
    def test_detail_cross_tenant_404(
        self, client_a, client_b, empresa_a, moneda_usd, moneda_ves, caja_usd, caja_ves, metodo_efectivo
    ):
        """R-CODE-1: la operación de la empresa A no es visible/accesible para B."""
        resp = client_a.post(
            URL,
            _payload(empresa_a, moneda_usd, moneda_ves, caja_usd, caja_ves, metodo_efectivo),
            format="json",
        )
        assert resp.status_code == 201, resp.data
        pk = resp.data["id"]

        assert client_b.get(f"{URL}{pk}/").status_code == 404
        assert client_b.get(URL).json()["count"] == 0
        assert client_a.get(f"{URL}{pk}/").status_code == 200

    def test_sin_auth_401(self):
        assert APIClient().get(URL).status_code == 401
