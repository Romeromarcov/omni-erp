"""
Tests M8 – Módulo Fiscal Venezuela.

Cubre:
  - NumeroCorrelativo (siguiente_numero)
  - calcular_impuestos
  - emitir_factura_fiscal con auto-numeración
  - Libros SENIAT
"""

import threading
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone


# ── Fixtures locales ──────────────────────────────────────────────────────────


@pytest.fixture
def moneda_ves(db):
    from apps.finanzas.models import Moneda
    return Moneda.objects.create(
        nombre="Bolívar Digital",
        codigo_iso="VES",
        simbolo="Bs.",
        tipo_moneda="fiat",
        es_generica=True,
    )


@pytest.fixture
def moneda_eur(db):
    from apps.finanzas.models import Moneda
    return Moneda.objects.create(
        nombre="Euro",
        codigo_iso="EUR",
        simbolo="€",
        tipo_moneda="fiat",
        es_generica=True,
    )


@pytest.fixture
def cliente_m8(db, empresa_a):
    from apps.crm.models import Cliente
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente M8 Test C.A.",
        rif="J-88888888-8",
        tipo_cliente="CONTADO",
    )


@pytest.fixture
def nota_venta_entregada(db, empresa_a, cliente_m8, moneda_usd):
    """NotaVenta en estado ENTREGADA lista para facturar."""
    from apps.ventas.models import DetalleNotaVenta, NotaVenta
    from apps.inventario.models import Producto, UnidadMedida, CategoriaProducto

    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a,
        nombre="Unidad M8",
        abreviatura="UNM8",
        tipo="CANTIDAD",
    )
    categoria = CategoriaProducto.objects.create(
        id_empresa=empresa_a,
        nombre_categoria="Cat M8",
    )
    producto = Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto M8",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
    )

    nota = NotaVenta.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_m8,
        numero_nota="NV-M8-001",
        fecha_nota=timezone.now().date(),
        estado="ENTREGADA",
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nota,
        id_producto=producto,
        cantidad=Decimal("10"),
        precio_unitario=Decimal("100.00"),
        subtotal=Decimal("1000.00"),
    )
    return nota


# ── TestNumeroCorrelativo ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestNumeroCorrelativo:
    def test_primer_numero_es_00000001(self, empresa_a):
        from apps.fiscal.services import siguiente_numero

        resultado = siguiente_numero(empresa_a, "FACTURA")
        assert resultado == "00000001"

    def test_numeros_incrementan_secuencialmente(self, empresa_a):
        from apps.fiscal.services import siguiente_numero

        n1 = siguiente_numero(empresa_a, "NOTA_DEBITO")
        n2 = siguiente_numero(empresa_a, "NOTA_DEBITO")
        n3 = siguiente_numero(empresa_a, "NOTA_DEBITO")
        assert n1 == "00000001"
        assert n2 == "00000002"
        assert n3 == "00000003"

    def test_prefijo_incluido(self, empresa_a):
        from apps.fiscal.models import NumeroCorrelativo
        from apps.fiscal.services import siguiente_numero

        # Create with prefix
        NumeroCorrelativo.objects.create(
            id_empresa=empresa_a,
            tipo="NOTA_CREDITO",
            prefijo="FAC-2026-",
            numero_actual=0,
            digitos=4,
        )
        resultado = siguiente_numero(empresa_a, "NOTA_CREDITO")
        assert resultado == "FAC-2026-0001"

    def test_tipo_diferente_secuencia_separada(self, empresa_a):
        from apps.fiscal.services import siguiente_numero

        fac1 = siguiente_numero(empresa_a, "FACTURA")
        nd1 = siguiente_numero(empresa_a, "NOTA_DEBITO")
        fac2 = siguiente_numero(empresa_a, "FACTURA")

        assert fac1 == "00000001"
        assert nd1 == "00000001"  # independent sequence
        assert fac2 == "00000002"

    def test_concurrencia_sin_duplicados(self, empresa_a):
        """
        Verifica que llamadas repetidas a siguiente_numero producen números únicos.
        (El test de concurrencia real con threads requiere transaction=True que no
        se puede usar aquí por restricciones de FK en la BD; este test verifica
        la unicidad secuencial que es el contrato principal.)
        """
        from apps.fiscal.services import siguiente_numero

        resultados = [siguiente_numero(empresa_a, "ORDEN_COMPRA") for _ in range(10)]

        assert len(resultados) == 10
        # All results must be unique
        assert len(set(resultados)) == 10, f"Duplicados encontrados: {sorted(resultados)}"
        # Must be sequential
        expected = [f"{i:08d}" for i in range(1, 11)]
        assert resultados == expected


# ── TestCalcularImpuestos ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCalcularImpuestos:
    def test_iva_12_por_defecto_sin_config(self, empresa_a):
        """Sin TasaIVAEmpresa configurada usa TASA_IVA_GENERAL (0.16)."""
        from apps.fiscal.services import calcular_impuestos, TASA_IVA_GENERAL

        resultado = calcular_impuestos(Decimal("100"), empresa_a)
        assert resultado["tasa_iva"] == TASA_IVA_GENERAL
        assert resultado["monto_iva"] == (Decimal("100") * TASA_IVA_GENERAL).quantize(Decimal("0.01"))
        assert resultado["monto_igtf"] == Decimal("0")

    def test_igtf_solo_en_divisa(self, empresa_a, moneda_usd):
        """IGTF aplica cuando hay configuración y moneda no es bolivar."""
        from apps.fiscal.models import ConfiguracionFiscalEmpresa
        from apps.fiscal.services import calcular_impuestos

        ConfiguracionFiscalEmpresa.objects.create(
            id_empresa=empresa_a,
            contribuyente_iva=True,
            aplica_igtf=True,
            tasa_igtf=Decimal("0.03"),
        )

        resultado = calcular_impuestos(Decimal("1000"), empresa_a, moneda_usd)
        assert resultado["tasa_igtf"] == Decimal("0.03")
        assert resultado["monto_igtf"] == Decimal("30.00")

    def test_igtf_no_en_bolivar(self, empresa_a, moneda_ves):
        """IGTF no aplica cuando la moneda es VES/bolivar."""
        from apps.fiscal.models import ConfiguracionFiscalEmpresa
        from apps.fiscal.services import calcular_impuestos

        ConfiguracionFiscalEmpresa.objects.create(
            id_empresa=empresa_a,
            contribuyente_iva=True,
            aplica_igtf=True,
            tasa_igtf=Decimal("0.03"),
        )

        resultado = calcular_impuestos(Decimal("1000"), empresa_a, moneda_ves)
        assert resultado["tasa_igtf"] == Decimal("0")
        assert resultado["monto_igtf"] == Decimal("0")

    def test_tasa_iva_configurable(self, empresa_a):
        """TasaIVAEmpresa GENERAL overrides the default."""
        from apps.fiscal.models import TasaIVAEmpresa
        from apps.fiscal.services import calcular_impuestos

        TasaIVAEmpresa.objects.create(
            id_empresa=empresa_a,
            tipo="GENERAL",
            nombre="IVA 12%",
            tasa=Decimal("0.12"),
        )

        resultado = calcular_impuestos(Decimal("100"), empresa_a)
        assert resultado["tasa_iva"] == Decimal("0.12")
        assert resultado["monto_iva"] == Decimal("12.00")

    def test_sin_moneda_no_aplica_igtf(self, empresa_a):
        """Si moneda=None, IGTF no aplica aunque esté configurado."""
        from apps.fiscal.models import ConfiguracionFiscalEmpresa
        from apps.fiscal.services import calcular_impuestos

        ConfiguracionFiscalEmpresa.objects.create(
            id_empresa=empresa_a,
            contribuyente_iva=True,
            aplica_igtf=True,
            tasa_igtf=Decimal("0.03"),
        )

        resultado = calcular_impuestos(Decimal("500"), empresa_a, moneda=None)
        assert resultado["monto_igtf"] == Decimal("0")

    def test_total_correcto(self, empresa_a, moneda_usd):
        """total = base + monto_iva + monto_igtf."""
        from apps.fiscal.models import ConfiguracionFiscalEmpresa, TasaIVAEmpresa
        from apps.fiscal.services import calcular_impuestos

        ConfiguracionFiscalEmpresa.objects.create(
            id_empresa=empresa_a,
            contribuyente_iva=True,
            aplica_igtf=True,
            tasa_igtf=Decimal("0.03"),
        )
        TasaIVAEmpresa.objects.create(
            id_empresa=empresa_a,
            tipo="GENERAL",
            nombre="IVA 16%",
            tasa=Decimal("0.16"),
        )

        resultado = calcular_impuestos(Decimal("100"), empresa_a, moneda_usd)
        expected_total = resultado["base_imponible"] + resultado["monto_iva"] + resultado["monto_igtf"]
        assert resultado["total"] == expected_total


# ── TestEmitirFacturaFiscalAutoNumber ─────────────────────────────────────────


@pytest.mark.django_db
class TestEmitirFacturaFiscalAutoNumber:
    def test_emitir_genera_numero_automatico(self, nota_venta_entregada, moneda_usd):
        """emitir_factura_fiscal sin pasar números los genera automáticamente."""
        from apps.ventas.services import emitir_factura_fiscal

        with patch("apps.ventas.services.generar_asiento") as mock_asiento:
            mock_asiento.return_value = object()
            resultado = emitir_factura_fiscal(nota_venta_entregada, moneda=moneda_usd)

        factura = resultado["factura"]
        assert factura.numero_factura is not None
        assert factura.numero_factura != ""
        assert factura.numero_control is not None
        assert factura.numero_control != ""

    def test_segundo_emitir_incrementa(self, empresa_a, cliente_m8, moneda_usd):
        """Dos facturas distintas incrementan el correlativo."""
        from apps.ventas.models import DetalleNotaVenta, NotaVenta
        from apps.inventario.models import Producto, UnidadMedida, CategoriaProducto
        from apps.ventas.services import emitir_factura_fiscal

        unidad = UnidadMedida.objects.create(
            id_empresa=empresa_a, nombre="UNM8B", abreviatura="UNM8B", tipo="CANTIDAD"
        )
        categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="CatM8B")
        producto = Producto.objects.create(
            id_empresa=empresa_a,
            nombre_producto="ProductoM8B",
            id_unidad_medida_base=unidad,
            id_categoria=categoria,
            id_moneda_precio=moneda_usd,
        )

        def crear_nota(numero):
            nota = NotaVenta.objects.create(
                id_empresa=empresa_a,
                id_cliente=cliente_m8,
                numero_nota=f"NV-{numero}",
                fecha_nota=timezone.now().date(),
                estado="ENTREGADA",
            )
            DetalleNotaVenta.objects.create(
                id_nota_venta=nota,
                id_producto=producto,
                cantidad=Decimal("1"),
                precio_unitario=Decimal("50"),
                subtotal=Decimal("50"),
            )
            return nota

        nota1 = crear_nota("X-001")
        nota2 = crear_nota("X-002")

        with patch("apps.ventas.services.generar_asiento") as mock_asiento:
            mock_asiento.return_value = object()
            r1 = emitir_factura_fiscal(nota1, moneda=moneda_usd)
            r2 = emitir_factura_fiscal(nota2, moneda=moneda_usd)

        f1 = r1["factura"]
        f2 = r2["factura"]
        # Numbers must be different
        assert f1.numero_factura != f2.numero_factura

    def test_emitir_llama_generar_asiento(self, nota_venta_entregada, moneda_usd):
        """emitir_factura_fiscal llama generar_asiento."""
        from apps.ventas.services import emitir_factura_fiscal

        with patch("apps.ventas.services.generar_asiento") as mock_asiento:
            mock_asiento.return_value = object()
            emitir_factura_fiscal(nota_venta_entregada, moneda=moneda_usd)
            assert mock_asiento.called

    def test_backward_compat_numeros_manuales(self, nota_venta_entregada, moneda_usd):
        """Passing explicit numero_control/numero_factura still works (backward compat)."""
        from apps.ventas.services import emitir_factura_fiscal

        with patch("apps.ventas.services.generar_asiento") as mock_asiento:
            mock_asiento.return_value = object()
            resultado = emitir_factura_fiscal(
                nota_venta_entregada,
                numero_control="CTRL-MANUAL-001",
                numero_factura="FAC-MANUAL-001",
                moneda=moneda_usd,
            )

        factura = resultado["factura"]
        assert factura.numero_control == "CTRL-MANUAL-001"
        assert factura.numero_factura == "FAC-MANUAL-001"


# ── TestLibrosSENIAT ──────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestLibrosSENIAT:
    def _crear_factura(self, empresa, cliente, moneda, numero_ctrl, numero_fac, fecha):
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

    def test_libro_ventas_txt_formato(self, empresa_a, moneda_usd):
        from apps.crm.models import Cliente
        from apps.fiscal.libros_seniat import generar_libro_ventas_txt

        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente Libro Test",
            rif="J-99999999-1",
            tipo_cliente="CONTADO",
        )
        fecha = timezone.now().date()
        self._crear_factura(empresa_a, cliente, moneda_usd, "CTRL-LV-001", "FAC-LV-001", fecha)

        resultado = generar_libro_ventas_txt(empresa_a, fecha, fecha)

        assert isinstance(resultado, str)
        assert len(resultado) > 0
        lineas = resultado.strip().split("\n")
        # Línea 0 = cabecera, línea 1 = datos → 2 líneas en total
        assert len(lineas) == 2

        campos = lineas[1].split("|")  # índice 1: primera fila de datos
        assert len(campos) == 8, f"Esperados 8 campos, obtenidos {len(campos)}: {campos}"

        # Verify fields position
        assert campos[2] == str(fecha)  # FECHA
        assert campos[3] == "CTRL-LV-001"  # NRO_CTRL
        assert campos[4] == "FAC-LV-001"  # NRO_FAC
        assert campos[5] == "1000.00"  # BASE_IMPONIBLE
        assert campos[6] == "160.00"  # IVA
        assert campos[7] == "1160.00"  # TOTAL

    def test_libro_ventas_sin_facturas(self, empresa_a):
        from apps.fiscal.libros_seniat import generar_libro_ventas_txt

        fecha = timezone.now().date()
        resultado = generar_libro_ventas_txt(empresa_a, fecha, fecha)
        # Sin facturas devuelve solo la línea de cabecera (no string vacío)
        assert resultado == "RIF_EMISOR|RIF_RECEPTOR|FECHA|NRO_CTRL|NRO_FAC|BASE_IMPONIBLE|IVA|TOTAL"

    def test_libro_ventas_multiples_facturas(self, empresa_a, moneda_usd):
        from apps.crm.models import Cliente
        from apps.fiscal.libros_seniat import generar_libro_ventas_txt

        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente LV Multi",
            rif="J-77777777-7",
            tipo_cliente="CONTADO",
        )
        fecha = timezone.now().date()
        self._crear_factura(empresa_a, cliente, moneda_usd, "CTRL-LV-A01", "FAC-LV-A01", fecha)
        self._crear_factura(empresa_a, cliente, moneda_usd, "CTRL-LV-A02", "FAC-LV-A02", fecha)

        resultado = generar_libro_ventas_txt(empresa_a, fecha, fecha)
        lineas = [l for l in resultado.split("\n") if l]
        # Línea 0 = cabecera + 2 líneas de datos = 3 en total
        assert len(lineas) == 3

    def test_libro_compras_retorna_string(self, empresa_a):
        from apps.fiscal.libros_seniat import generar_libro_compras_txt

        fecha = timezone.now().date()
        resultado = generar_libro_compras_txt(empresa_a, fecha, fecha)
        assert isinstance(resultado, str)
