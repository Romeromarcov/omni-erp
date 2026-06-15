"""
Hallazgo BAJO (auditoría integral 2026-06-10): "Fechas 'hoy' en UTC en aging y
búsqueda de tasas (corrimiento tras 20:00 Caracas)".

Con ``USE_TZ=True`` y ``TIME_ZONE="America/Caracas"`` (UTC-4), ``date.today()`` y
``timezone.now().date()`` devuelven la fecha **UTC**: entre las 20:00 y 23:59 de
Caracas (= 00:00–03:59 UTC del día siguiente) ya marcan "mañana". Eso corría un
día el aging de cartera y la fecha por defecto de la búsqueda de tasas. El fix
usa ``timezone.localdate()`` (fecha en TIME_ZONE).

Estos tests congelan ``timezone.now()`` a las 02:00 UTC (= 22:00 Caracas del día
anterior), la ventana que antes fallaba, y fijan el comportamiento correcto.
"""

import datetime
from decimal import Decimal
from unittest import mock

import pytest

from django.utils import timezone

# 02:00 UTC del 2026-06-15  ==  22:00 Caracas del 2026-06-14
_NOW_UTC = datetime.datetime(2026, 6, 15, 2, 0, 0, tzinfo=datetime.timezone.utc)
_CARACAS_HOY = datetime.date(2026, 6, 14)
_UTC_HOY = datetime.date(2026, 6, 15)


def test_localdate_difiere_de_now_date_en_la_ventana():
    """Sanity check: en la ventana elegida la fecha local ≠ la fecha UTC."""
    with mock.patch("django.utils.timezone.now", return_value=_NOW_UTC):
        assert timezone.localdate() == _CARACAS_HOY
        assert timezone.now().date() == _UTC_HOY


class TestAgingPartidaCartera:
    def test_vencimiento_hoy_caracas_no_esta_vencida(self):
        from apps.cuentas_por_cobrar.services_aging import PartidaCartera

        with mock.patch("django.utils.timezone.now", return_value=_NOW_UTC):
            partida = PartidaCartera(
                cliente_id="c1",
                cliente_nombre="Cliente",
                orden_ref="F-1",
                monto_total=Decimal("100.00"),
                monto_pendiente=Decimal("100.00"),
                fecha_vencimiento=_CARACAS_HOY,  # vence hoy (en Caracas)
                estado_pago="pendiente",
            )

        # En Caracas hoy == fecha_vencimiento => 0 días, al día.
        # Con el bug (fecha UTC) serían 1 día y bucket "1_30".
        assert partida.dias_vencida == 0
        assert partida.vencida is False
        assert partida.bucket == "al_dia"

    def test_vencimiento_ayer_caracas_si_esta_vencida(self):
        from apps.cuentas_por_cobrar.services_aging import PartidaCartera

        with mock.patch("django.utils.timezone.now", return_value=_NOW_UTC):
            partida = PartidaCartera(
                cliente_id="c1",
                cliente_nombre="Cliente",
                orden_ref="F-2",
                monto_total=Decimal("100.00"),
                monto_pendiente=Decimal("100.00"),
                fecha_vencimiento=_CARACAS_HOY - datetime.timedelta(days=1),
                estado_pago="pendiente",
            )

        assert partida.dias_vencida == 1
        assert partida.vencida is True
        assert partida.bucket == "1_30"


@pytest.mark.django_db
class TestCalcularAgingFechaLocal:
    def test_cxc_vence_hoy_caracas_cae_en_corriente(self, empresa_a):
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar
        from apps.cuentas_por_cobrar.services import calcular_aging

        CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente_externo_id="odoo-1",
            cliente_externo_nombre="Cliente",
            monto=Decimal("100.00"),
            fecha_emision=_CARACAS_HOY,
            fecha_vencimiento=_CARACAS_HOY,  # vence hoy en Caracas
            estado="pendiente",
        )

        with mock.patch("django.utils.timezone.now", return_value=_NOW_UTC):
            resultado = calcular_aging(empresa_a.id_empresa)

        # hoy (Caracas) == vencimiento => 0 días => corriente, no dias_1_30.
        assert resultado["corriente"]["count"] == 1
        assert resultado["corriente"]["total"] == Decimal("100.00")
        assert resultado["dias_1_30"]["count"] == 0


@pytest.mark.django_db
class TestObtenerTasaCambioFechaLocal:
    def test_tasa_identidad_usa_fecha_local(self):
        from apps.finanzas.models import Moneda
        from apps.finanzas.services import obtener_tasa_cambio

        usd, _ = Moneda.objects.get_or_create(
            codigo_iso="USD",
            defaults={
                "nombre": "Dólar",
                "simbolo": "$",
                "tipo_moneda": "fiat",
                "es_generica": True,
            },
        )

        with mock.patch("django.utils.timezone.now", return_value=_NOW_UTC):
            tasa = obtener_tasa_cambio(usd, usd)

        # El stub de identidad fecha su tasa con la fecha LOCAL (Caracas), no UTC.
        assert tasa.valor_tasa == Decimal("1.00000000")
        assert tasa.fecha_tasa == _CARACAS_HOY

    def test_busqueda_por_defecto_usa_fecha_local(self, empresa_a):
        from apps.finanzas.models import Moneda, TasaCambio
        from apps.finanzas.services import obtener_tasa_cambio

        usd, _ = Moneda.objects.get_or_create(
            codigo_iso="USD",
            defaults={"nombre": "Dólar", "simbolo": "$", "tipo_moneda": "fiat"},
        )
        ves, _ = Moneda.objects.get_or_create(
            codigo_iso="VES",
            defaults={"nombre": "Bolívar", "simbolo": "Bs.", "tipo_moneda": "fiat"},
        )
        # Dos tasas exactas: una para el día local (Caracas) y otra para el día
        # UTC siguiente. La búsqueda por defecto (prioridad 1: fecha exacta) debe
        # tomar la del día LOCAL. Con el bug (fecha UTC) tomaría la de _UTC_HOY.
        tasa_caracas = TasaCambio.objects.create(
            id_moneda_origen=usd,
            id_moneda_destino=ves,
            valor_tasa=Decimal("40.00000000"),
            fecha_tasa=_CARACAS_HOY,
            tipo_tasa="OFICIAL_BCV",
            id_empresa=None,
        )
        TasaCambio.objects.create(
            id_moneda_origen=usd,
            id_moneda_destino=ves,
            valor_tasa=Decimal("41.00000000"),
            fecha_tasa=_UTC_HOY,
            tipo_tasa="OFICIAL_BCV",
            id_empresa=None,
        )

        with mock.patch("django.utils.timezone.now", return_value=_NOW_UTC):
            tasa = obtener_tasa_cambio(usd, ves)

        assert tasa.pk == tasa_caracas.pk
        assert tasa.fecha_tasa == _CARACAS_HOY
        assert tasa.valor_tasa == Decimal("40.00000000")
