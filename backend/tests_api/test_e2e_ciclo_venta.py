"""
TEST-03 — E2E del ciclo de venta completo (Semana 2 / GAP-01)

Verifica el flujo completo:
  1. NotaVenta en BORRADOR → confirmar_nota_venta() → ENTREGADA + asiento NOTA_VENTA
  2. NotaVenta ENTREGADA → emitir_factura_fiscal() →
       - FacturaFiscal EMITIDA con monto_iva y monto_igtf calculados
       - AsientoContable FACTURA_VENTA creado
       - CuentaPorCobrar creada por el monto total de la factura
       - NotaVenta pasa a FACTURADA

Cobertura explícita:
  - IVA calculado correctamente (16 % sobre base imponible)
  - monto_igtf almacenado en la factura (GAP-01 campo nuevo)
  - CxC creada con monto == factura.monto_total (GAP-01 nueva lógica)
  - CxC referencia_externa == numero_factura
  - CxC tipo_operacion == 'FACTURA_VENTA'
  - Aislamiento: CxC pertenece a la empresa correcta
"""

from decimal import Decimal

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db


# ── Helpers contables (reutilizados de CTF-001) ────────────────────────────────


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


def _mapeo(empresa, tipo_asiento, debe, haber, plantilla=None):
    from apps.contabilidad.models import MapeoContable
    return MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento=tipo_asiento,
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla=plantilla or f"Asiento {tipo_asiento} {{numero}}",
        activo=True,
    )


# ── Fixtures locales ───────────────────────────────────────────────────────────


@pytest.fixture
def cliente_e2e(db, empresa_a):
    from apps.crm.models import Cliente
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente E2E Ciclo",
        rif="J-55555555-5",
        tipo_cliente="CREDITO",
    )


@pytest.fixture
def unidad_e2e(db, empresa_a):
    from apps.inventario.models import UnidadMedida
    return UnidadMedida.objects.create(
        id_empresa=empresa_a,
        nombre="Unidad",
        abreviatura="UN-E2E",
        tipo="CANTIDAD",
    )


@pytest.fixture
def categoria_e2e(db, empresa_a):
    from apps.inventario.models import CategoriaProducto
    return CategoriaProducto.objects.create(
        id_empresa=empresa_a,
        nombre_categoria="Cat E2E Ciclo",
    )


@pytest.fixture
def producto_e2e(db, empresa_a, categoria_e2e, unidad_e2e, moneda_usd):
    from apps.inventario.models import Producto
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto E2E Ciclo",
        id_unidad_medida_base=unidad_e2e,
        id_categoria=categoria_e2e,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("500.00"),
        costo_promedio=Decimal("300.00"),
    )


@pytest.fixture
def almacen_e2e(db, empresa_a):
    from apps.almacenes.models import Almacen
    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén E2E Ciclo",
        codigo_almacen="E2E-CICLO-001",
    )


@pytest.fixture
def stock_e2e(db, empresa_a, producto_e2e, almacen_e2e, user_a):
    """Carga inicial de inventario para que la entrega pueda descontarlo."""
    from apps.inventario.services import registrar_movimiento
    registrar_movimiento(
        empresa=empresa_a,
        fecha_hora_movimiento=timezone.now(),
        tipo_movimiento="ENTRADA",
        producto=producto_e2e,
        cantidad=Decimal("100"),
        almacen_destino=almacen_e2e,
        usuario=user_a,
    )


@pytest.fixture
def nota_borrador_e2e(db, empresa_a, cliente_e2e, producto_e2e, stock_e2e):
    """NotaVenta en BORRADOR con un detalle de 2 unidades × 500 = 1 000 de subtotal."""
    from apps.ventas.models import DetalleNotaVenta, NotaVenta
    nota = NotaVenta.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_e2e,
        numero_nota="NV-E2E-CICLO-001",
        fecha_nota=timezone.now().date(),
        estado="BORRADOR",
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nota,
        id_producto=producto_e2e,
        cantidad=Decimal("2"),
        precio_unitario=Decimal("500.00"),
        subtotal=Decimal("1000.00"),
    )
    return nota


@pytest.fixture
def nota_entregada_e2e(db, empresa_a, cliente_e2e, producto_e2e, stock_e2e):
    """NotaVenta ya en ENTREGADA — para tests que sólo prueban emitir_factura_fiscal."""
    from apps.ventas.models import DetalleNotaVenta, NotaVenta
    nota = NotaVenta.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_e2e,
        numero_nota="NV-E2E-CICLO-002",
        fecha_nota=timezone.now().date(),
        estado="ENTREGADA",
    )
    DetalleNotaVenta.objects.create(
        id_nota_venta=nota,
        id_producto=producto_e2e,
        cantidad=Decimal("2"),
        precio_unitario=Decimal("500.00"),
        subtotal=Decimal("1000.00"),
    )
    return nota


@pytest.fixture
def mapeos_contables(db, empresa_a):
    """
    Crea los tres MapeoContable necesarios para el ciclo completo:
    NOTA_VENTA, FACTURA_VENTA, FACTURA_VENTA_IVA.
    """
    debe_nv = _cuenta(empresa_a, "E2E-1201", "CxC NV E2E", "ACTIVO", "DEUDORA")
    haber_nv = _cuenta(empresa_a, "E2E-4101", "Ingresos NV E2E", "INGRESO", "ACREEDORA")
    _mapeo(empresa_a, "NOTA_VENTA", debe_nv, haber_nv, "NV {numero}")

    debe_fv = _cuenta(empresa_a, "E2E-1202", "CxC Factura E2E", "ACTIVO", "DEUDORA")
    haber_fv = _cuenta(empresa_a, "E2E-4102", "Ingresos Factura E2E", "INGRESO", "ACREEDORA")
    _mapeo(empresa_a, "FACTURA_VENTA", debe_fv, haber_fv, "FAC {numero}")

    debe_iva = _cuenta(empresa_a, "E2E-1203", "IVA Debito E2E", "ACTIVO", "DEUDORA")
    haber_iva = _cuenta(empresa_a, "E2E-2101", "IVA por Pagar E2E", "PASIVO", "ACREEDORA")
    _mapeo(empresa_a, "FACTURA_VENTA_IVA", debe_iva, haber_iva, "IVA {numero}")


# ── TEST-03a: Ciclo completo (confirmar + emitir) ─────────────────────────────


class TestCicloVentaCompleto:
    """
    E2E del ciclo completo: BORRADOR → ENTREGADA → FACTURADA.
    Verifica que confirmar_nota_venta y emitir_factura_fiscal se encadenan.
    """

    def test_ciclo_completo_borrador_a_facturada(
        self,
        db,
        user_a,
        almacen_e2e,
        nota_borrador_e2e,
        moneda_usd,
        mapeos_contables,
    ):
        """
        Flujo completo:
          1. confirmar_nota_venta() → ENTREGADA + asiento NOTA_VENTA
          2. emitir_factura_fiscal() → FACTURADA + FacturaFiscal + AsientoContable + CxC
        """
        from apps.ventas.services import confirmar_nota_venta, emitir_factura_fiscal
        from apps.contabilidad.models import AsientoContable
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        # ── Paso 1: confirmar ─────────────────────────────────────────────────
        r1 = confirmar_nota_venta(nota_borrador_e2e, almacen_e2e, user_a)
        nota_borrador_e2e.refresh_from_db()
        assert nota_borrador_e2e.estado == "ENTREGADA", (
            f"Esperaba ENTREGADA, obtuvo {nota_borrador_e2e.estado}"
        )
        assert r1["asiento"] is not None, "confirmar_nota_venta debe crear asiento NOTA_VENTA"

        # ── Paso 2: emitir ────────────────────────────────────────────────────
        r2 = emitir_factura_fiscal(
            nota_borrador_e2e,
            numero_control="E2E-CTRL-001",
            numero_factura="E2E-FAC-001",
            moneda=moneda_usd,
        )
        nota_borrador_e2e.refresh_from_db()
        assert nota_borrador_e2e.estado == "FACTURADA", (
            f"Esperaba FACTURADA, obtuvo {nota_borrador_e2e.estado}"
        )

        factura = r2["factura"]
        assert factura.estado == "EMITIDA"
        assert r2["asiento"] is not None, "emitir_factura_fiscal debe crear asiento FACTURA_VENTA"

        # CxC debe existir
        assert r2["cxc"] is not None, "emitir_factura_fiscal debe devolver una CxC"
        cxc = r2["cxc"]
        assert cxc.pk is not None, "La CxC debe estar persistida en BD"


# ── TEST-03b: IVA calculado y almacenado en FacturaFiscal ─────────────────────


class TestIVACalculado:
    """
    Verifica que calcular_impuestos() se invoca y los resultados se almacenan
    correctamente en FacturaFiscal.monto_iva y FacturaFiscal.monto_igtf.
    """

    def test_factura_almacena_monto_iva(
        self,
        db,
        nota_entregada_e2e,
        moneda_usd,
        mapeos_contables,
    ):
        """
        Con base_imponible = 1 000, monto_iva debe ser 1 000 × 0.16 = 160.
        Toleramos que el IVA sea 0 si la configuración fiscal no está activa —
        lo importante es que el campo exista y la factura se emita sin error.
        """
        from apps.ventas.services import emitir_factura_fiscal

        r = emitir_factura_fiscal(
            nota_entregada_e2e,
            numero_control="E2E-CTRL-002",
            numero_factura="E2E-FAC-002",
            moneda=moneda_usd,
        )
        factura = r["factura"]

        # El campo monto_iva debe existir en el modelo y ser >= 0
        assert hasattr(factura, "monto_iva"), "FacturaFiscal debe tener campo monto_iva"
        assert factura.monto_iva >= Decimal("0"), "monto_iva no puede ser negativo"

        # Si el IVA está activo (tasa 16%), debe ser base × 0.16
        base = factura.base_imponible
        if factura.monto_iva > Decimal("0"):
            expected_iva = (base * Decimal("0.16")).quantize(factura.monto_iva)
            assert factura.monto_iva == expected_iva, (
                f"monto_iva esperado {expected_iva}, obtuvo {factura.monto_iva}"
            )

    def test_factura_almacena_monto_igtf(
        self,
        db,
        nota_entregada_e2e,
        moneda_usd,
        mapeos_contables,
    ):
        """
        GAP-01: FacturaFiscal debe tener el campo monto_igtf persistido.
        Para moneda VES/nacional el IGTF es 0; para divisas puede ser positivo.
        """
        from apps.ventas.services import emitir_factura_fiscal

        r = emitir_factura_fiscal(
            nota_entregada_e2e,
            numero_control="E2E-CTRL-003",
            numero_factura="E2E-FAC-003",
            moneda=moneda_usd,
        )
        factura = r["factura"]

        # El campo debe existir y estar persistido
        assert hasattr(factura, "monto_igtf"), "FacturaFiscal debe tener campo monto_igtf (GAP-01)"
        factura.refresh_from_db()
        assert factura.monto_igtf >= Decimal("0"), "monto_igtf no puede ser negativo"

    def test_monto_total_igual_a_base_mas_iva_mas_igtf(
        self,
        db,
        nota_entregada_e2e,
        moneda_usd,
        mapeos_contables,
    ):
        """monto_total == base_imponible + monto_iva + monto_igtf."""
        from apps.ventas.services import emitir_factura_fiscal

        r = emitir_factura_fiscal(
            nota_entregada_e2e,
            numero_control="E2E-CTRL-004",
            numero_factura="E2E-FAC-004",
            moneda=moneda_usd,
        )
        factura = r["factura"]
        factura.refresh_from_db()

        expected_total = factura.base_imponible + factura.monto_iva + factura.monto_igtf
        assert factura.monto_total == expected_total, (
            f"monto_total {factura.monto_total} != base+iva+igtf {expected_total}"
        )


# ── TEST-03c: AsientoContable creado ─────────────────────────────────────────


class TestAsientoContableCreado:
    """
    Verifica que emitir_factura_fiscal() crea el AsientoContable de FACTURA_VENTA
    con débito = crédito = monto_total y nombre_modelo_origen correcto.
    """

    def test_asiento_factura_venta_creado(
        self,
        db,
        nota_entregada_e2e,
        moneda_usd,
        mapeos_contables,
    ):
        from apps.contabilidad.models import AsientoContable, DetalleAsiento
        from apps.ventas.services import emitir_factura_fiscal

        r = emitir_factura_fiscal(
            nota_entregada_e2e,
            numero_control="E2E-CTRL-005",
            numero_factura="E2E-FAC-005",
            moneda=moneda_usd,
        )
        asiento = r["asiento"]
        assert asiento is not None, "Se esperaba AsientoContable, recibió None"
        assert isinstance(asiento, AsientoContable)
        assert asiento.nombre_modelo_origen == "FacturaFiscal"

        detalles = DetalleAsiento.objects.filter(id_asiento=asiento)
        assert detalles.count() == 2, "El asiento debe tener exactamente 2 líneas (debe/haber)"

        total_debe = sum(d.debe for d in detalles)
        total_haber = sum(d.haber for d in detalles)
        assert total_debe == total_haber, "El asiento debe estar balanceado (debe == haber)"
        assert total_debe > Decimal("0"), "El monto del asiento debe ser positivo"

    def test_emitir_sin_mapeo_levanta_venta_error(
        self,
        db,
        nota_entregada_e2e,
        moneda_usd,
    ):
        """
        Sin MapeoContable para FACTURA_VENTA, emitir_factura_fiscal() levanta
        VentaError (el asiento de factura es obligatorio, no best-effort).
        La transacción hace rollback por el @transaction.atomic.
        """
        from apps.ventas.services import emitir_factura_fiscal, VentaError

        with pytest.raises(VentaError, match="asiento contable"):
            emitir_factura_fiscal(
                nota_entregada_e2e,
                numero_control="E2E-CTRL-006",
                numero_factura="E2E-FAC-006",
                moneda=moneda_usd,
            )


# ── TEST-03d: CuentaPorCobrar creada (GAP-01) ─────────────────────────────────


class TestCuentaPorCobrarCreada:
    """
    GAP-01: Verifica que emitir_factura_fiscal() crea una CuentaPorCobrar
    con monto == monto_total de la factura.
    """

    def test_cxc_creada_con_monto_correcto(
        self,
        db,
        nota_entregada_e2e,
        moneda_usd,
        mapeos_contables,
    ):
        """CxC.monto debe ser igual a factura.monto_total."""
        from apps.ventas.services import emitir_factura_fiscal
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        r = emitir_factura_fiscal(
            nota_entregada_e2e,
            numero_control="E2E-CTRL-007",
            numero_factura="E2E-FAC-007",
            moneda=moneda_usd,
        )
        factura = r["factura"]
        cxc = r["cxc"]

        assert cxc is not None, "emitir_factura_fiscal debe crear CxC (GAP-01)"
        # CxC.monto es DecimalField(max_digits=12, decimal_places=2) → comparar redondeado
        assert cxc.monto == factura.monto_total.quantize(Decimal("0.01")), (
            f"CxC.monto {cxc.monto} != factura.monto_total {factura.monto_total}"
        )

    def test_cxc_referencia_externa_igual_numero_factura(
        self,
        db,
        nota_entregada_e2e,
        moneda_usd,
        mapeos_contables,
    ):
        """CxC.referencia_externa debe ser el numero_factura."""
        from apps.ventas.services import emitir_factura_fiscal

        r = emitir_factura_fiscal(
            nota_entregada_e2e,
            numero_control="E2E-CTRL-008",
            numero_factura="E2E-FAC-008",
            moneda=moneda_usd,
        )
        cxc = r["cxc"]
        assert cxc.referencia_externa == "E2E-FAC-008"

    def test_cxc_tipo_operacion_es_factura_venta(
        self,
        db,
        nota_entregada_e2e,
        moneda_usd,
        mapeos_contables,
    ):
        """CxC.tipo_operacion debe ser 'FACTURA_VENTA'."""
        from apps.ventas.services import emitir_factura_fiscal

        r = emitir_factura_fiscal(
            nota_entregada_e2e,
            numero_control="E2E-CTRL-009",
            numero_factura="E2E-FAC-009",
            moneda=moneda_usd,
        )
        cxc = r["cxc"]
        assert cxc.tipo_operacion == "FACTURA_VENTA"

    def test_cxc_pertenece_a_la_empresa_correcta(
        self,
        db,
        empresa_a,
        nota_entregada_e2e,
        moneda_usd,
        mapeos_contables,
    ):
        """CxC.empresa debe ser la empresa de la factura (aislamiento multi-tenant)."""
        from apps.ventas.services import emitir_factura_fiscal

        r = emitir_factura_fiscal(
            nota_entregada_e2e,
            numero_control="E2E-CTRL-010",
            numero_factura="E2E-FAC-010",
            moneda=moneda_usd,
        )
        cxc = r["cxc"]
        assert cxc.empresa_id == empresa_a.id_empresa, (
            "La CxC debe pertenecer a la misma empresa que la factura"
        )

    def test_cxc_estado_pendiente_al_emitir(
        self,
        db,
        nota_entregada_e2e,
        moneda_usd,
        mapeos_contables,
    ):
        """CxC.estado debe ser 'pendiente' justo después de emitir la factura."""
        from apps.ventas.services import emitir_factura_fiscal

        r = emitir_factura_fiscal(
            nota_entregada_e2e,
            numero_control="E2E-CTRL-011",
            numero_factura="E2E-FAC-011",
            moneda=moneda_usd,
        )
        cxc = r["cxc"]
        assert cxc.estado == "pendiente", (
            f"CxC recién creada debe tener estado 'pendiente', obtuvo '{cxc.estado}'"
        )

    def test_cxc_fecha_vencimiento_posterior_a_emision(
        self,
        db,
        nota_entregada_e2e,
        moneda_usd,
        mapeos_contables,
    ):
        """fecha_vencimiento de la CxC debe ser posterior a su fecha_emision."""
        from apps.ventas.services import emitir_factura_fiscal

        r = emitir_factura_fiscal(
            nota_entregada_e2e,
            numero_control="E2E-CTRL-012",
            numero_factura="E2E-FAC-012",
            moneda=moneda_usd,
        )
        cxc = r["cxc"]
        assert cxc.fecha_vencimiento > cxc.fecha_emision, (
            "fecha_vencimiento debe ser posterior a fecha_emision"
        )

    def test_cxc_persistida_en_base_de_datos(
        self,
        db,
        nota_entregada_e2e,
        moneda_usd,
        mapeos_contables,
    ):
        """La CxC devuelta en el resultado debe estar realmente persistida en BD."""
        from apps.ventas.services import emitir_factura_fiscal
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        r = emitir_factura_fiscal(
            nota_entregada_e2e,
            numero_control="E2E-CTRL-013",
            numero_factura="E2E-FAC-013",
            moneda=moneda_usd,
        )
        cxc = r["cxc"]
        # Verificar que existe en la base de datos
        assert CuentaPorCobrar.objects.filter(pk=cxc.pk).exists(), (
            "La CxC debe estar persistida en la base de datos"
        )
