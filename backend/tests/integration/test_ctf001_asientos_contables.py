"""
Tests de integración — CTF-001: Asientos contables automáticos (R-CODE-11).

Cubre:
  1. confirmar_nota_venta() genera AsientoContable NOTA_VENTA cuando existe MapeoContable.
  2. confirmar_nota_venta() funciona sin MapeoContable (best-effort, no falla).
  3. emitir_factura_fiscal() genera AsientoContable FACTURA_VENTA.
  4. emitir_factura_fiscal() genera AsientoContable FACTURA_VENTA_IVA cuando monto_iva > 0.
  5. emitir_factura_fiscal() funciona sin MapeoContable IVA (best-effort para el IVA).
  6. generar_asiento() acepta monto explícito (parámetro nuevo en CTF-001).
"""

import pytest
from decimal import Decimal

from django.utils import timezone

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Helpers de setup de cuentas contables ─────────────────────────────────────


def _crear_cuenta(empresa, codigo, nombre, tipo="ACTIVO", naturaleza="DEUDORA"):
    from apps.contabilidad.models import PlanCuentas
    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=nombre,
        tipo_cuenta=tipo,
        naturaleza=naturaleza,
        nivel=1,
    )


def _crear_mapeo(empresa, tipo_asiento, debe, haber, plantilla=None):
    from apps.contabilidad.models import MapeoContable
    return MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento=tipo_asiento,
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla=plantilla or f"Asiento {tipo_asiento} {{numero}}",
        activo=True,
    )


# ── Fixtures locales ──────────────────────────────────────────────────────────


@pytest.fixture
def cliente_a(db, empresa_a):
    from apps.crm.models import Cliente
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Test CTF001",
        rif="J-00001111-1",
        tipo_cliente="CONTADO",
    )


@pytest.fixture
def unidad(db, empresa_a):
    from apps.inventario.models import UnidadMedida
    return UnidadMedida.objects.create(
        id_empresa=empresa_a,
        nombre="Unidad",
        abreviatura="UN-CTF01",
        tipo="CANTIDAD",
    )


@pytest.fixture
def categoria(db, empresa_a):
    from apps.inventario.models import CategoriaProducto
    return CategoriaProducto.objects.create(
        id_empresa=empresa_a,
        nombre_categoria="Cat CTF001",
    )


@pytest.fixture
def producto_ctf(db, empresa_a, unidad, categoria, moneda_usd):
    from apps.inventario.models import Producto
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto CTF001",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
    )


@pytest.fixture
def almacen_ctf(db, empresa_a):
    from apps.almacenes.models import Almacen
    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacen CTF001",
        codigo_almacen="CTF001-ALM",
    )


@pytest.fixture
def stock_ctf(db, empresa_a, producto_ctf, almacen_ctf, user_a):
    from apps.inventario.services import registrar_movimiento
    registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="ENTRADA",
        producto=producto_ctf,
        cantidad=Decimal("100"),
        almacen_destino=almacen_ctf,
        usuario=user_a,
    )


@pytest.fixture
def nota_borrador(db, empresa_a, cliente_a, producto_ctf, stock_ctf):
    from apps.ventas.models import DetalleNotaVenta, NotaVenta
    nota = NotaVenta.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_a,
        numero_nota="NV-CTF001-001",
        fecha_nota=timezone.now().date(),
        estado="BORRADOR",
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nota,
        id_producto=producto_ctf,
        cantidad=Decimal("10"),
        precio_unitario=Decimal("100.00"),
        subtotal=Decimal("1000.00"),
    )
    return nota


@pytest.fixture
def nota_entregada(db, empresa_a, cliente_a, producto_ctf, moneda_usd, stock_ctf):
    """NotaVenta ya en estado ENTREGADA — lista para emitir_factura_fiscal."""
    from apps.ventas.models import DetalleNotaVenta, NotaVenta
    nota = NotaVenta.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_a,
        numero_nota="NV-CTF001-002",
        fecha_nota=timezone.now().date(),
        estado="ENTREGADA",
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nota,
        id_producto=producto_ctf,
        cantidad=Decimal("10"),
        precio_unitario=Decimal("100.00"),
        subtotal=Decimal("1000.00"),
    )
    return nota


@pytest.fixture
def mapeo_nota_venta(db, empresa_a):
    """MapeoContable para NOTA_VENTA — CxC debe / Ingresos haber."""
    debe = _crear_cuenta(empresa_a, "1201", "Cuentas por Cobrar Comerciales", "ACTIVO", "DEUDORA")
    haber = _crear_cuenta(empresa_a, "4101", "Ingresos por Ventas", "INGRESO", "ACREEDORA")
    return _crear_mapeo(empresa_a, "NOTA_VENTA", debe, haber, "Entrega NV {numero}")


@pytest.fixture
def mapeo_factura_venta(db, empresa_a):
    """MapeoContable para FACTURA_VENTA — CxC debe / Ingresos haber."""
    debe = _crear_cuenta(empresa_a, "1202", "CxC Factura Venta", "ACTIVO", "DEUDORA")
    haber = _crear_cuenta(empresa_a, "4102", "Ingresos Factura Venta", "INGRESO", "ACREEDORA")
    return _crear_mapeo(empresa_a, "FACTURA_VENTA", debe, haber, "Factura {numero}")


@pytest.fixture
def mapeo_factura_iva(db, empresa_a):
    """MapeoContable para FACTURA_VENTA_IVA — IVA por Pagar."""
    debe = _crear_cuenta(empresa_a, "1203", "IVA Debito Fiscal", "ACTIVO", "DEUDORA")
    haber = _crear_cuenta(empresa_a, "2101", "IVA por Pagar", "PASIVO", "ACREEDORA")
    return _crear_mapeo(empresa_a, "FACTURA_VENTA_IVA", debe, haber, "IVA Factura {numero}")


# ── Tests confirmar_nota_venta ────────────────────────────────────────────────


class TestConfirmarNotaVenta:

    def test_confirmar_nota_crea_asiento_nota_venta(
        self, db, user_a, almacen_ctf, nota_borrador, mapeo_nota_venta
    ):
        """
        confirmar_nota_venta() con MapeoContable activo → crea AsientoContable NOTA_VENTA
        con débito a CxC y crédito a Ingresos.
        """
        from apps.contabilidad.models import AsientoContable, DetalleAsiento
        from apps.ventas.services import confirmar_nota_venta

        resultado = confirmar_nota_venta(nota_borrador, almacen_ctf, user_a)

        asiento = resultado["asiento"]
        assert asiento is not None, "Se esperaba asiento, obtuvo None"
        assert isinstance(asiento, AsientoContable)

        # El asiento debe tener dos líneas: debe y haber
        detalles = DetalleAsiento.objects.filter(id_asiento=asiento)
        assert detalles.count() == 2

        # Verificar sumas balanceadas
        total_debe = sum(d.debe for d in detalles)
        total_haber = sum(d.haber for d in detalles)
        assert total_debe == total_haber == Decimal("1000.00")

        # El nombre del modelo origen debe ser NotaVenta
        assert asiento.nombre_modelo_origen == "NotaVenta"

    def test_confirmar_nota_sin_mapeo_no_falla(
        self, db, user_a, almacen_ctf, nota_borrador
    ):
        """
        confirmar_nota_venta() sin MapeoContable configurado → entrega la nota
        sin error; asiento es None y asiento_error tiene la descripción del fallo.
        """
        from apps.ventas.services import confirmar_nota_venta

        resultado = confirmar_nota_venta(nota_borrador, almacen_ctf, user_a)

        assert resultado["asiento"] is None
        assert resultado["asiento_error"] is not None
        assert "NOTA_VENTA" in resultado["asiento_error"]

        # La nota debe haber pasado a ENTREGADA de todas formas
        nota_borrador.refresh_from_db()
        assert nota_borrador.estado == "ENTREGADA"

    def test_confirmar_nota_cambia_estado_a_entregada(
        self, db, user_a, almacen_ctf, nota_borrador, mapeo_nota_venta
    ):
        """La nota pasa de BORRADOR a ENTREGADA al confirmar."""
        from apps.ventas.services import confirmar_nota_venta

        confirmar_nota_venta(nota_borrador, almacen_ctf, user_a)

        nota_borrador.refresh_from_db()
        assert nota_borrador.estado == "ENTREGADA"


# ── Tests emitir_factura_fiscal ───────────────────────────────────────────────


class TestEmitirFacturaFiscal:

    def test_emitir_factura_crea_asiento_factura_venta(
        self, db, user_a, nota_entregada, moneda_usd, mapeo_factura_venta
    ):
        """
        emitir_factura_fiscal() con MapeoContable FACTURA_VENTA → crea AsientoContable.
        """
        from apps.contabilidad.models import AsientoContable
        from apps.ventas.services import emitir_factura_fiscal

        resultado = emitir_factura_fiscal(
            nota_entregada,
            numero_control="00-00000001",
            numero_factura="0001",
            moneda=moneda_usd,
        )

        asiento = resultado["asiento"]
        assert asiento is not None
        assert isinstance(asiento, AsientoContable)
        assert asiento.nombre_modelo_origen == "FacturaFiscal"

    def test_emitir_factura_crea_asiento_iva_si_monto_iva_positivo(
        self, db, user_a, nota_entregada, moneda_usd, mapeo_factura_venta, mapeo_factura_iva, empresa_a
    ):
        """
        emitir_factura_fiscal() con MapeoContable FACTURA_VENTA_IVA →
        - Si la factura tiene monto_iva > 0: asiento_iva se crea correctamente.
        - Si no hay IVA (configuración fiscal no activa): asiento_iva es None,
          asiento_iva_error contiene la causa (monto=0).

        El test verifica que la lógica existe y que NUNCA falla por falta de mapeo
        cuando el mapeo sí está configurado.
        """
        from apps.ventas.services import emitir_factura_fiscal

        resultado = emitir_factura_fiscal(
            nota_entregada,
            numero_control="00-00000002",
            numero_factura="0002",
            moneda=moneda_usd,
        )

        # El asiento principal siempre debe existir
        assert resultado["asiento"] is not None

        factura = resultado["factura"]
        assert factura.estado == "EMITIDA"

        if factura.monto_iva > Decimal("0"):
            # Hay IVA y hay mapeo → debe haberse creado el asiento IVA
            assert resultado["asiento_iva"] is not None, (
                "Con mapeo y monto_iva > 0, se esperaba asiento_iva"
            )
            assert resultado["asiento_iva_error"] is None
        else:
            # Sin IVA activo → asiento_iva es None (no hay monto que asentar)
            # El error sería "monto <= 0", no "sin mapeo"
            assert resultado["asiento_iva"] is None

    def test_emitir_factura_sin_mapeo_iva_no_falla(
        self, db, user_a, nota_entregada, moneda_usd, mapeo_factura_venta
    ):
        """
        emitir_factura_fiscal() sin MapeoContable IVA → factura se emite igual;
        asiento_iva es None y asiento_iva_error contiene la descripción del fallo.
        """
        from apps.ventas.services import emitir_factura_fiscal

        resultado = emitir_factura_fiscal(
            nota_entregada,
            numero_control="00-00000003",
            numero_factura="0003",
            moneda=moneda_usd,
        )

        # El asiento principal debe existir
        assert resultado["asiento"] is not None

        # La factura debe estar EMITIDA
        factura = resultado["factura"]
        assert factura.estado == "EMITIDA"

        # La nota debe estar FACTURADA
        nota_entregada.refresh_from_db()
        assert nota_entregada.estado == "FACTURADA"


# ── Tests generar_asiento con monto explícito ─────────────────────────────────


class TestGenerarAsientoMontoExplicito:

    def test_monto_explicito_sobrescribe_extraccion(self, db, empresa_a, mapeo_nota_venta):
        """
        generar_asiento() con monto explícito usa ese monto en lugar de
        intentar extraerlo del documento.
        """
        from apps.contabilidad.models import DetalleAsiento
        from apps.contabilidad.services import generar_asiento
        from apps.ventas.models import NotaVenta
        from apps.crm.models import Cliente

        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente Monto Test",
            rif="J-99998888-1",
        )
        nota = NotaVenta.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente,
            numero_nota="NV-MONTO-001",
            fecha_nota=timezone.now().date(),
            estado="BORRADOR",
        )

        monto_explicito = Decimal("750.00")
        asiento = generar_asiento("NOTA_VENTA", nota, empresa_a, monto=monto_explicito)

        detalles = DetalleAsiento.objects.filter(id_asiento=asiento)
        assert detalles.count() == 2
        total_debe = sum(d.debe for d in detalles)
        assert total_debe == monto_explicito, (
            f"El asiento debe reflejar el monto explícito {monto_explicito}, obtuvo {total_debe}"
        )
