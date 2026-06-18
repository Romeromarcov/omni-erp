"""
Tests para el servicio de conversión de monedas:
- obtener_tasa_cambio(): prioridad empresa > BCV global > reciente
- convertir_monto(): conversión directa e inversa
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.finanzas.services import TasaCambioError, convertir_monto, obtener_tasa_cambio

pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────
# Fixtures de monedas y tasas
# ─────────────────────────────────────────────


@pytest.fixture
def moneda_ves(db):
    from apps.finanzas.models import Moneda

    return Moneda.objects.create(
        codigo_iso="VES",
        nombre="Bolívar Soberano",
        simbolo="Bs.",
        tipo_moneda="fiat",
        es_generica=True,
    )


@pytest.fixture
def moneda_eur(db):
    from apps.finanzas.models import Moneda

    return Moneda.objects.create(
        codigo_iso="EUR",
        nombre="Euro",
        simbolo="€",
        tipo_moneda="fiat",
        es_generica=True,
    )


@pytest.fixture
def tasa_usd_ves_bcv(db, moneda_usd, moneda_ves):
    """Tasa BCV global USD→VES para hoy: 1 USD = 36.50 VES."""
    from apps.finanzas.models import TasaCambio

    return TasaCambio.objects.create(
        id_moneda_origen=moneda_usd,
        id_moneda_destino=moneda_ves,
        valor_tasa=Decimal("36.50000000"),
        fecha_tasa=timezone.localdate(),
        tipo_tasa="OFICIAL_BCV",
        id_empresa=None,
    )


@pytest.fixture
def tasa_usd_ves_empresa(db, empresa_a, moneda_usd, moneda_ves):
    """Tasa ESPECIAL_USUARIO de empresa_a USD→VES: 1 USD = 37.00 VES."""
    from apps.finanzas.models import TasaCambio

    return TasaCambio.objects.create(
        id_empresa=empresa_a,
        id_moneda_origen=moneda_usd,
        id_moneda_destino=moneda_ves,
        valor_tasa=Decimal("37.00000000"),
        fecha_tasa=timezone.localdate(),
        tipo_tasa="ESPECIAL_USUARIO",
    )


@pytest.fixture
def tasa_antigua(db, moneda_usd, moneda_ves):
    """Tasa BCV de hace 15 días (dentro del ventana de 30 días)."""
    from apps.finanzas.models import TasaCambio

    return TasaCambio.objects.create(
        id_moneda_origen=moneda_usd,
        id_moneda_destino=moneda_ves,
        valor_tasa=Decimal("35.00000000"),
        fecha_tasa=timezone.localdate() - timedelta(days=15),
        tipo_tasa="OFICIAL_BCV",
        id_empresa=None,
    )


@pytest.fixture
def tasa_muy_antigua(db, moneda_usd, moneda_ves):
    """Tasa BCV de hace 45 días (fuera del ventana de 30 días)."""
    from apps.finanzas.models import TasaCambio

    return TasaCambio.objects.create(
        id_moneda_origen=moneda_usd,
        id_moneda_destino=moneda_ves,
        valor_tasa=Decimal("30.00000000"),
        fecha_tasa=timezone.localdate() - timedelta(days=45),
        tipo_tasa="OFICIAL_BCV",
        id_empresa=None,
    )


# ─────────────────────────────────────────────
# Tests obtener_tasa_cambio
# ─────────────────────────────────────────────


class TestObtenerTasaCambio:
    def test_misma_moneda_retorna_tasa_uno(self, db, moneda_usd):
        tasa = obtener_tasa_cambio(moneda_usd, moneda_usd)
        assert tasa.valor_tasa == Decimal("1.00000000")

    def test_tasa_bcv_global(self, db, tasa_usd_ves_bcv, moneda_usd, moneda_ves):
        tasa = obtener_tasa_cambio(moneda_usd, moneda_ves)
        assert tasa.valor_tasa == Decimal("36.50000000")
        assert tasa.tipo_tasa == "OFICIAL_BCV"

    def test_tasa_empresa_tiene_prioridad_sobre_bcv(
        self, db, tasa_usd_ves_bcv, tasa_usd_ves_empresa, moneda_usd, moneda_ves, empresa_a
    ):
        tasa = obtener_tasa_cambio(moneda_usd, moneda_ves, empresa=empresa_a)
        assert tasa.valor_tasa == Decimal("37.00000000")
        assert tasa.tipo_tasa == "ESPECIAL_USUARIO"

    def test_bcv_global_si_empresa_sin_tasa_especifica(
        self, db, tasa_usd_ves_bcv, moneda_usd, moneda_ves, empresa_a
    ):
        """empresa_a no tiene tasa específica → usa BCV global."""
        tasa = obtener_tasa_cambio(moneda_usd, moneda_ves, empresa=empresa_a)
        assert tasa.valor_tasa == Decimal("36.50000000")

    def test_tasa_reciente_como_fallback(self, db, tasa_antigua, moneda_usd, moneda_ves):
        """No hay tasa para hoy, pero sí una de hace 15 días."""
        tasa = obtener_tasa_cambio(moneda_usd, moneda_ves)
        assert tasa.valor_tasa == Decimal("35.00000000")

    def test_tasa_muy_antigua_no_aplica(self, db, tasa_muy_antigua, moneda_usd, moneda_ves):
        """Tasa de hace 45 días está fuera del ventana de 30 días."""
        with pytest.raises(TasaCambioError):
            obtener_tasa_cambio(moneda_usd, moneda_ves)

    def test_sin_tasa_lanza_error(self, db, moneda_usd, moneda_ves):
        with pytest.raises(TasaCambioError):
            obtener_tasa_cambio(moneda_usd, moneda_ves)

    def test_busqueda_por_codigo_iso(self, db, tasa_usd_ves_bcv):
        """Se pueden pasar códigos ISO en lugar de instancias Moneda."""
        tasa = obtener_tasa_cambio("USD", "VES")
        assert tasa.valor_tasa == Decimal("36.50000000")

    def test_codigo_iso_inexistente_lanza_error(self, db):
        with pytest.raises(TasaCambioError):
            obtener_tasa_cambio("XYZ", "ABC")

    def test_fecha_especifica(self, db, tasa_antigua, moneda_usd, moneda_ves):
        """Se puede pedir la tasa de una fecha específica pasada."""
        fecha = timezone.localdate() - timedelta(days=15)
        tasa = obtener_tasa_cambio(moneda_usd, moneda_ves, fecha=fecha)
        assert tasa.valor_tasa == Decimal("35.00000000")

    def test_fallback_reciente_empresa_tiene_prioridad(
        self, db, empresa_a, moneda_usd, moneda_ves
    ):
        """Sin tasa de la fecha exacta, el fallback de 30 días prefiere la
        tasa empresa-específica sobre la global (cubre la rama empresa del
        bloque de recientes en services.obtener_tasa_cambio)."""
        from apps.finanzas.models import TasaCambio

        hace_5 = timezone.localdate() - timedelta(days=5)
        # Global reciente (más nueva) y empresa reciente (más vieja): debe ganar
        # la de la empresa pese a ser anterior, por la prioridad empresa>global.
        TasaCambio.objects.create(
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            valor_tasa=Decimal("36.00000000"),
            fecha_tasa=timezone.localdate() - timedelta(days=2),
            tipo_tasa="OFICIAL_BCV",
            id_empresa=None,
        )
        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            valor_tasa=Decimal("38.00000000"),
            fecha_tasa=hace_5,
            tipo_tasa="ESPECIAL_USUARIO",
        )
        tasa = obtener_tasa_cambio(moneda_usd, moneda_ves, empresa=empresa_a)
        assert tasa.valor_tasa == Decimal("38.00000000")


# ─────────────────────────────────────────────
# Tests convertir_monto
# ─────────────────────────────────────────────


class TestConvertirMonto:
    def test_conversion_directa(self, db, tasa_usd_ves_bcv, moneda_usd, moneda_ves):
        resultado = convertir_monto(Decimal("100"), moneda_usd, moneda_ves)
        assert resultado == Decimal("3650.0000")

    def test_conversion_con_empresa(self, db, tasa_usd_ves_empresa, moneda_usd, moneda_ves, empresa_a):
        resultado = convertir_monto(Decimal("100"), moneda_usd, moneda_ves, empresa=empresa_a)
        assert resultado == Decimal("3700.0000")

    def test_conversion_misma_moneda(self, db, moneda_usd):
        resultado = convertir_monto(Decimal("500"), moneda_usd, moneda_usd)
        assert resultado == Decimal("500.0000")

    def test_conversion_cero(self, db, tasa_usd_ves_bcv, moneda_usd, moneda_ves):
        resultado = convertir_monto(Decimal("0"), moneda_usd, moneda_ves)
        assert resultado == Decimal("0.0000")

    def test_conversion_por_codigo_iso(self, db, tasa_usd_ves_bcv):
        resultado = convertir_monto(Decimal("10"), "USD", "VES")
        assert resultado == Decimal("365.0000")

    def test_monto_negativo_lanza_error(self, db, tasa_usd_ves_bcv, moneda_usd, moneda_ves):
        with pytest.raises(ValueError):
            convertir_monto(Decimal("-1"), moneda_usd, moneda_ves)

    def test_sin_tasa_lanza_error(self, db, moneda_usd, moneda_ves):
        with pytest.raises(TasaCambioError):
            convertir_monto(Decimal("100"), moneda_usd, moneda_ves)

    def test_redondeo_a_4_decimales(self, db, moneda_usd, moneda_ves):
        from apps.finanzas.models import TasaCambio

        TasaCambio.objects.create(
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            valor_tasa=Decimal("36.12345678"),
            fecha_tasa=timezone.localdate(),
            tipo_tasa="OFICIAL_BCV",
            id_empresa=None,
        )
        resultado = convertir_monto(Decimal("1"), moneda_usd, moneda_ves)
        # 36.12345678 rounded to 4 places = 36.1235
        assert resultado == Decimal("36.1235")
