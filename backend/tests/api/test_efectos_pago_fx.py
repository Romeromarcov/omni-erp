"""
Conversión FX en registrar_efectos_pago (deuda auditoría 2026-06-21).

Antes, ``registrar_efectos_pago`` asumía ``id_moneda_base = moneda del pago`` y
``monto_base_empresa = monto`` (comentario "Simplificación: misma moneda del
pago"). Un pago en divisa registraba así un ``monto_base_empresa`` incorrecto en
la ``TransaccionFinanciera`` (no convertido a la moneda base de la empresa).

Ahora, entre monedas distintas se convierte con la tasa (BCV) vía
``convertir_monto``; sin tasa disponible el pago se rechaza (nunca 1:1).
"""

import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.finanzas.models import MetodoPago, Moneda, Pago, TasaCambio, TransaccionFinanciera
from apps.finanzas.services import TasaCambioError, registrar_efectos_pago

pytestmark = pytest.mark.django_db


@pytest.fixture
def metodo(db):
    return MetodoPago.objects.create(
        nombre_metodo="Efectivo FX", tipo_metodo="EFECTIVO", es_generico=True
    )


@pytest.fixture
def moneda_ves(db):
    return Moneda.objects.create(
        nombre="Bolívar", codigo_iso="VES", simbolo="Bs",
        tipo_moneda="fiat", es_generica=True,
    )


def _pago(empresa, moneda, metodo, usuario, monto="100.00"):
    return Pago.objects.create(
        id_empresa=empresa,
        tipo_operacion="INGRESO",
        tipo_documento="FACTURA",
        id_documento=uuid.uuid4(),
        fecha_pago=timezone.now(),
        monto=Decimal(monto),
        id_moneda=moneda,
        id_metodo_pago=metodo,
        id_usuario_registro=usuario,
    )


class TestEfectosPagoFX:
    def test_pago_en_divisa_convierte_a_moneda_base(
        self, empresa_a, moneda_usd, moneda_ves, metodo, user_a
    ):
        # empresa_a base = USD. Pago de 100 VES con tasa 1 VES = 0.025 USD → 2.5 USD.
        pago = _pago(empresa_a, moneda_ves, metodo, user_a, monto="100.00")
        TasaCambio.objects.create(
            id_empresa=None,
            id_moneda_origen=moneda_ves,
            id_moneda_destino=moneda_usd,
            tipo_tasa="OFICIAL_BCV",
            valor_tasa=Decimal("0.025"),
            fecha_tasa=pago.fecha_pago.date(),
        )

        transaccion, _ = registrar_efectos_pago(pago)

        # La transacción se registra en la moneda del pago…
        assert transaccion.id_moneda_transaccion == moneda_ves
        assert transaccion.monto_transaccion == Decimal("100.00")
        # …pero el monto base va convertido a la moneda base de la empresa (USD).
        assert transaccion.id_moneda_base == moneda_usd
        assert transaccion.monto_base_empresa == Decimal("2.5000")

    def test_pago_en_moneda_base_no_convierte(
        self, empresa_a, moneda_usd, metodo, user_a
    ):
        # Pago ya en la moneda base (USD): monto_base = monto, sin tasa requerida.
        pago = _pago(empresa_a, moneda_usd, metodo, user_a, monto="80.00")

        transaccion, _ = registrar_efectos_pago(pago)

        assert transaccion.id_moneda_base == moneda_usd
        assert transaccion.monto_base_empresa == Decimal("80.00")

    def test_pago_en_divisa_sin_tasa_se_rechaza(
        self, empresa_a, moneda_ves, metodo, user_a
    ):
        # Sin TasaCambio VES→USD el pago se rechaza (no se asume 1:1) y nada persiste.
        pago = _pago(empresa_a, moneda_ves, metodo, user_a, monto="100.00")

        with pytest.raises(TasaCambioError):
            registrar_efectos_pago(pago)

        assert TransaccionFinanciera.objects.count() == 0
        pago.refresh_from_db()
        assert pago.id_transaccion_financiera is None
