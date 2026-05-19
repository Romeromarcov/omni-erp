"""
Tests M8 — Fiscal Venezuela (completo).

Cubre:
  - generar_libro_ventas_txt: formato TXT SENIAT correcto
  - calcular_impuestos: IVA 16% por defecto (default SENIAT)
  - calcular_impuestos: IGTF 3% en moneda extranjera
  - calcular_impuestos: IGTF no aplica en bolivares
"""

from decimal import Decimal

import pytest
from django.utils import timezone


# ── Fixtures locales ──────────────────────────────────────────────────────────


@pytest.fixture
def moneda_usd_m8(db):
    from apps.finanzas.models import Moneda
    return Moneda.objects.create(
        nombre="Dólar M8 Test",
        codigo_iso="USD",
        simbolo="$",
        tipo_moneda="fiat",
        es_generica=True,
    )


@pytest.fixture
def moneda_ves_m8(db):
    from apps.finanzas.models import Moneda
    return Moneda.objects.create(
        nombre="Bolívar M8 Test",
        codigo_iso="VES",
        simbolo="Bs.",
        tipo_moneda="fiat",
        es_generica=True,
    )


@pytest.fixture
def empresa_fiscal(db, moneda_usd_m8):
    from apps.core.models import Empresa
    return Empresa.objects.create(
        nombre_legal="Empresa Fiscal M8 C.A.",
        identificador_fiscal="J-55555555-5",
        id_moneda_base=moneda_usd_m8,
    )


@pytest.fixture
def cliente_m8_test(db, empresa_fiscal):
    from apps.crm.models import Cliente
    return Cliente.objects.create(
        id_empresa=empresa_fiscal,
        razon_social="Cliente M8 Completo S.A.",
        rif="J-11111111-1",
        tipo_cliente="CONTADO",
    )


def _crear_factura(empresa, cliente, moneda, numero_ctrl, numero_fac, fecha):
    from apps.ventas.models import FacturaFiscal
    return FacturaFiscal.objects.create(
        id_empresa=empresa,
        id_cliente=cliente,
        numero_control=numero_ctrl,
        numero_factura=numero_fac,
        fecha_emision=fecha,
        base_imponible=Decimal("1000.00"),
        monto_iva=Decimal("160.00"),
        monto_total=Decimal("1160.00"),
        id_moneda=moneda,
        estado="EMITIDA",
    )


# ── TestGenerarLibroVentasTxtFormato ──────────────────────────────────────────


@pytest.mark.django_db
class TestGenerarLibroVentasTxtFormato:
    """Verifica que generar_libro_ventas_txt produce TXT con columnas correctas."""

    def test_formato_correcto_8_columnas(self, empresa_fiscal, cliente_m8_test, moneda_usd_m8):
        from apps.fiscal.libros_seniat import generar_libro_ventas_txt

        fecha = timezone.now().date()
        _crear_factura(empresa_fiscal, cliente_m8_test, moneda_usd_m8, "CTRL-001", "FAC-001", fecha)

        resultado = generar_libro_ventas_txt(empresa_fiscal, fecha, fecha)

        assert isinstance(resultado, str), "El resultado debe ser un string"
        assert len(resultado) > 0, "El resultado no debe estar vacío"

        lineas = [l for l in resultado.split("\n") if l.strip()]
        assert len(lineas) == 1, f"Debe haber exactamente 1 línea, hay {len(lineas)}"

        campos = lineas[0].split("|")
        assert len(campos) == 8, (
            f"Deben ser 8 columnas (RIF_EMISOR|RIF_RECEPTOR|FECHA|NRO_CTRL|NRO_FAC|BASE|IVA|TOTAL), "
            f"se obtuvieron {len(campos)}: {campos}"
        )

    def test_columnas_posicion_correcta(self, empresa_fiscal, cliente_m8_test, moneda_usd_m8):
        from apps.fiscal.libros_seniat import generar_libro_ventas_txt

        fecha = timezone.now().date()
        _crear_factura(empresa_fiscal, cliente_m8_test, moneda_usd_m8, "CTRL-POS-001", "FAC-POS-001", fecha)

        resultado = generar_libro_ventas_txt(empresa_fiscal, fecha, fecha)
        lineas = [l for l in resultado.split("\n") if l.strip()]
        campos = lineas[0].split("|")

        # Posición 0: RIF emisor (empresa)
        assert campos[0] == "J-55555555-5", f"Columna 0 debe ser RIF emisor, es: {campos[0]}"
        # Posición 1: RIF receptor (cliente)
        assert campos[1] == "J-11111111-1", f"Columna 1 debe ser RIF cliente, es: {campos[1]}"
        # Posición 2: FECHA
        assert campos[2] == str(fecha), f"Columna 2 debe ser la fecha, es: {campos[2]}"
        # Posición 3: NRO_CTRL
        assert campos[3] == "CTRL-POS-001", f"Columna 3 debe ser numero_control, es: {campos[3]}"
        # Posición 4: NRO_FAC
        assert campos[4] == "FAC-POS-001", f"Columna 4 debe ser numero_factura, es: {campos[4]}"
        # Posición 5: BASE_IMPONIBLE
        assert campos[5] == "1000.00", f"Columna 5 debe ser base_imponible, es: {campos[5]}"
        # Posición 6: IVA
        assert campos[6] == "160.00", f"Columna 6 debe ser monto_iva, es: {campos[6]}"
        # Posición 7: TOTAL
        assert campos[7] == "1160.00", f"Columna 7 debe ser monto_total, es: {campos[7]}"

    def test_sin_facturas_devuelve_string_vacio(self, empresa_fiscal):
        from apps.fiscal.libros_seniat import generar_libro_ventas_txt

        fecha = timezone.now().date()
        resultado = generar_libro_ventas_txt(empresa_fiscal, fecha, fecha)
        assert resultado == "", "Sin facturas debe retornar string vacío"

    def test_multiples_facturas_multiples_lineas(self, empresa_fiscal, cliente_m8_test, moneda_usd_m8):
        from apps.fiscal.libros_seniat import generar_libro_ventas_txt

        fecha = timezone.now().date()
        _crear_factura(empresa_fiscal, cliente_m8_test, moneda_usd_m8, "CTRL-MUL-001", "FAC-MUL-001", fecha)
        _crear_factura(empresa_fiscal, cliente_m8_test, moneda_usd_m8, "CTRL-MUL-002", "FAC-MUL-002", fecha)
        _crear_factura(empresa_fiscal, cliente_m8_test, moneda_usd_m8, "CTRL-MUL-003", "FAC-MUL-003", fecha)

        resultado = generar_libro_ventas_txt(empresa_fiscal, fecha, fecha)
        lineas = [l for l in resultado.split("\n") if l.strip()]
        assert len(lineas) == 3, f"Debe haber 3 líneas (una por factura), hay {len(lineas)}"

    def test_facturas_fuera_de_rango_excluidas(self, empresa_fiscal, cliente_m8_test, moneda_usd_m8):
        from apps.fiscal.libros_seniat import generar_libro_ventas_txt
        from datetime import date, timedelta

        hoy = date.today()
        hace_60_dias = hoy - timedelta(days=60)

        # Factura en fecha pasada fuera de rango
        _crear_factura(
            empresa_fiscal, cliente_m8_test, moneda_usd_m8,
            "CTRL-OUT-001", "FAC-OUT-001", hace_60_dias
        )

        # Consultar solo el rango de hoy
        resultado = generar_libro_ventas_txt(empresa_fiscal, hoy, hoy)
        assert resultado == "", "No deben incluirse facturas fuera del rango de fechas"

    def test_libro_compras_retorna_string(self, empresa_fiscal):
        from apps.fiscal.libros_seniat import generar_libro_compras_txt

        fecha = timezone.now().date()
        resultado = generar_libro_compras_txt(empresa_fiscal, fecha, fecha)
        assert isinstance(resultado, str), "generar_libro_compras_txt debe retornar un string"


# ── TestCalcularImpuestosIVA ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestCalcularImpuestosIVA12:
    """Verifica que calcular_impuestos aplica la tasa IVA configurada."""

    def test_iva_16_por_defecto_sin_config(self, empresa_fiscal):
        """Sin TasaIVAEmpresa configurada usa TASA_IVA_GENERAL (0.16 = 16%)."""
        from apps.fiscal.services import calcular_impuestos, TASA_IVA_GENERAL

        resultado = calcular_impuestos(Decimal("100.00"), empresa_fiscal)

        assert resultado["tasa_iva"] == TASA_IVA_GENERAL, (
            f"La tasa IVA default debe ser {TASA_IVA_GENERAL}, se obtuvo {resultado['tasa_iva']}"
        )
        expected_iva = (Decimal("100.00") * TASA_IVA_GENERAL).quantize(Decimal("0.01"))
        assert resultado["monto_iva"] == expected_iva, (
            f"El monto IVA debe ser {expected_iva}, se obtuvo {resultado['monto_iva']}"
        )

    def test_tasa_iva_12_configurable(self, empresa_fiscal):
        """TasaIVAEmpresa GENERAL=12% anula el default 16%."""
        from apps.fiscal.models import TasaIVAEmpresa
        from apps.fiscal.services import calcular_impuestos

        TasaIVAEmpresa.objects.create(
            id_empresa=empresa_fiscal,
            tipo="GENERAL",
            nombre="IVA 12%",
            tasa=Decimal("0.12"),
        )

        resultado = calcular_impuestos(Decimal("100.00"), empresa_fiscal)

        assert resultado["tasa_iva"] == Decimal("0.12"), (
            f"La tasa configurada 12% no se aplicó, se obtuvo {resultado['tasa_iva']}"
        )
        assert resultado["monto_iva"] == Decimal("12.00"), (
            f"El IVA debe ser 12.00, se obtuvo {resultado['monto_iva']}"
        )

    def test_total_es_base_mas_iva(self, empresa_fiscal):
        """total = base_imponible + monto_iva cuando no hay IGTF."""
        from apps.fiscal.services import calcular_impuestos

        resultado = calcular_impuestos(Decimal("500.00"), empresa_fiscal)
        expected_total = resultado["base_imponible"] + resultado["monto_iva"]
        assert resultado["total"] == expected_total, (
            f"total debe ser {expected_total}, se obtuvo {resultado['total']}"
        )

    def test_monto_iva_redondeado_correctamente(self, empresa_fiscal):
        """El monto IVA debe estar redondeado a 2 decimales (ROUND_HALF_UP)."""
        from apps.fiscal.services import calcular_impuestos
        from decimal import ROUND_HALF_UP

        subtotal = Decimal("333.33")
        resultado = calcular_impuestos(subtotal, empresa_fiscal)
        expected = (subtotal * resultado["tasa_iva"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert resultado["monto_iva"] == expected


# ── TestCalcularImpuestosIGTF ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestCalcularImpuestosIGTFEnDivisas:
    """Verifica que IGTF 3% aplica solo para moneda extranjera."""

    @pytest.fixture(autouse=True)
    def _config_fiscal(self, empresa_fiscal):
        """Crea ConfiguracionFiscalEmpresa con aplica_igtf=True."""
        from apps.fiscal.models import ConfiguracionFiscalEmpresa
        ConfiguracionFiscalEmpresa.objects.create(
            id_empresa=empresa_fiscal,
            contribuyente_iva=True,
            aplica_igtf=True,
            tasa_igtf=Decimal("0.03"),
        )

    def test_igtf_3_por_ciento_en_usd(self, empresa_fiscal, moneda_usd_m8):
        """IGTF aplica cuando la moneda es USD (divisas)."""
        from apps.fiscal.services import calcular_impuestos

        resultado = calcular_impuestos(Decimal("1000.00"), empresa_fiscal, moneda_usd_m8)

        assert resultado["tasa_igtf"] == Decimal("0.03"), (
            f"La tasa IGTF debe ser 0.03 (3%), se obtuvo {resultado['tasa_igtf']}"
        )
        assert resultado["monto_igtf"] == Decimal("30.00"), (
            f"El monto IGTF debe ser 30.00, se obtuvo {resultado['monto_igtf']}"
        )

    def test_igtf_no_aplica_en_bolivares(self, empresa_fiscal, moneda_ves_m8):
        """IGTF NO aplica cuando la moneda es VES/Bolívar."""
        from apps.fiscal.services import calcular_impuestos

        resultado = calcular_impuestos(Decimal("1000.00"), empresa_fiscal, moneda_ves_m8)

        assert resultado["tasa_igtf"] == Decimal("0"), (
            f"La tasa IGTF debe ser 0 para bolívares, se obtuvo {resultado['tasa_igtf']}"
        )
        assert resultado["monto_igtf"] == Decimal("0"), (
            f"El monto IGTF debe ser 0 para bolívares, se obtuvo {resultado['monto_igtf']}"
        )

    def test_igtf_no_aplica_sin_moneda(self, empresa_fiscal):
        """IGTF NO aplica cuando moneda=None."""
        from apps.fiscal.services import calcular_impuestos

        resultado = calcular_impuestos(Decimal("1000.00"), empresa_fiscal, moneda=None)

        assert resultado["monto_igtf"] == Decimal("0"), (
            f"Sin moneda, el IGTF debe ser 0, se obtuvo {resultado['monto_igtf']}"
        )

    def test_total_incluye_igtf_en_divisas(self, empresa_fiscal, moneda_usd_m8):
        """total = base + iva + igtf cuando aplica IGTF."""
        from apps.fiscal.services import calcular_impuestos

        resultado = calcular_impuestos(Decimal("1000.00"), empresa_fiscal, moneda_usd_m8)
        expected_total = (
            resultado["base_imponible"] + resultado["monto_iva"] + resultado["monto_igtf"]
        )
        assert resultado["total"] == expected_total, (
            f"total debe incluir IGTF: {expected_total}, se obtuvo {resultado['total']}"
        )

    def test_igtf_tasa_configurable(self, empresa_fiscal, moneda_usd_m8):
        """La tasa IGTF es configurable a través de ConfiguracionFiscalEmpresa."""
        from apps.fiscal.models import ConfiguracionFiscalEmpresa
        from apps.fiscal.services import calcular_impuestos

        # Ya existe la config del autouse, la actualizamos
        cfg = ConfiguracionFiscalEmpresa.objects.get(id_empresa=empresa_fiscal)
        cfg.tasa_igtf = Decimal("0.02")
        cfg.save()

        resultado = calcular_impuestos(Decimal("1000.00"), empresa_fiscal, moneda_usd_m8)

        assert resultado["tasa_igtf"] == Decimal("0.02"), (
            f"La tasa IGTF configurada debe ser 0.02, se obtuvo {resultado['tasa_igtf']}"
        )
        assert resultado["monto_igtf"] == Decimal("20.00"), (
            f"El monto IGTF debe ser 20.00, se obtuvo {resultado['monto_igtf']}"
        )
