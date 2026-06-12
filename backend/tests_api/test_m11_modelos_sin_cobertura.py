"""
Tests de modelo — Módulos sin cobertura (Sesión H).

Módulos cubiertos:
  - apps/rrhh/models.py       — Cargo, Empleado, Beneficio
  - apps/nomina/models.py     — PeriodoNomina, ConceptoNomina
  - apps/tesoreria/models.py  — OperacionCambioDivisa
  - apps/despacho/models.py   — Despacho (sin deps de Pedido/NotaVenta)
  - apps/costos/models.py     — CostoEstandarProducto (requiere Producto)

Nota: todos los tests son de creación y __str__/unicidad. No requieren
      endpoints ni servicios complejos. El objetivo es superar el umbral
      de cobertura de líneas en estos módulos.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures compartidas
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def almacen_despacho(db, empresa_a):
    from apps.almacenes.models import Almacen

    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén Despacho",
        codigo_almacen="AC-DSP",
    )


@pytest.fixture
def unidad(db, empresa_a):
    from apps.inventario.models import UnidadMedida

    return UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad M11", abreviatura="UN-M11", tipo="CANTIDAD"
    )


@pytest.fixture
def categoria(db, empresa_a):
    from apps.inventario.models import CategoriaProducto

    return CategoriaProducto.objects.create(
        id_empresa=empresa_a, nombre_categoria="Cat M11"
    )


@pytest.fixture
def producto_m11(db, empresa_a, unidad, categoria, moneda_usd):
    from apps.inventario.models import Producto

    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto M11",
        sku="PROD-M11-001",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
    )


# ─────────────────────────────────────────────────────────────────────────────
# RRHH — Cargo, Empleado, Beneficio
# ─────────────────────────────────────────────────────────────────────────────


class TestRRHHModelos:
    def test_cargo_creacion_y_str(self, empresa_a):
        from apps.rrhh.models import Cargo

        cargo = Cargo.objects.create(empresa=empresa_a, nombre="Gerente de Ventas")
        assert str(cargo) == "Gerente de Ventas"
        assert cargo.activo is True

    def test_empleado_creacion_y_str(self, empresa_a):
        from apps.rrhh.models import Cargo, Empleado

        cargo = Cargo.objects.create(empresa=empresa_a, nombre="Analista")
        empleado = Empleado.objects.create(
            empresa=empresa_a,
            nombre="Juan",
            apellido="Pérez",
            cedula="V-12345678",
            cargo=cargo,
            fecha_ingreso=timezone.now().date(),
        )
        assert "Juan" in str(empleado)
        assert "Pérez" in str(empleado)
        assert "V-12345678" in str(empleado)

    def test_empleado_unicidad_cedula_por_empresa(self, empresa_a, empresa_b):
        from apps.rrhh.models import Empleado

        # Misma cédula en empresa distinta → válido
        Empleado.objects.create(
            empresa=empresa_a,
            nombre="Ana",
            apellido="López",
            cedula="V-99999999",
            fecha_ingreso=timezone.now().date(),
        )
        # Empresa B puede tener el mismo RIF
        empleado_b = Empleado.objects.create(
            empresa=empresa_b,
            nombre="Ana",
            apellido="López",
            cedula="V-99999999",
            fecha_ingreso=timezone.now().date(),
        )
        assert empleado_b.pk is not None

    def test_empleado_cedula_duplicada_misma_empresa_falla(self, empresa_a):
        from django.db import IntegrityError
        from apps.rrhh.models import Empleado

        Empleado.objects.create(
            empresa=empresa_a,
            nombre="Carlos",
            apellido="García",
            cedula="V-11111111",
            fecha_ingreso=timezone.now().date(),
        )
        with pytest.raises(IntegrityError):
            Empleado.objects.create(
                empresa=empresa_a,
                nombre="Carlos Dos",
                apellido="García",
                cedula="V-11111111",
                fecha_ingreso=timezone.now().date(),
            )

    def test_beneficio_creacion_y_str(self, empresa_a):
        from apps.rrhh.models import Beneficio

        b = Beneficio.objects.create(
            id_empresa=empresa_a,
            nombre_beneficio="Seguro Médico",
            tipo_beneficio="SALUD",
        )
        assert "Seguro Médico" in str(b)
        assert b.activo is True

    def test_beneficio_monetario_con_monto(self, empresa_a):
        from apps.rrhh.models import Beneficio

        b = Beneficio.objects.create(
            id_empresa=empresa_a,
            nombre_beneficio="Bono Alimentación",
            tipo_beneficio="ALIMENTACION",
            monto_fijo=Decimal("200.00"),
        )
        assert b.monto_fijo == Decimal("200.00")

    def test_cargo_sin_empresa(self):
        from apps.rrhh.models import Cargo

        # empresa nullable en Cargo
        cargo = Cargo.objects.create(nombre="Cargo Global")
        assert cargo.empresa is None


# ─────────────────────────────────────────────────────────────────────────────
# Nómina — PeriodoNomina, ConceptoNomina
# ─────────────────────────────────────────────────────────────────────────────


class TestNominaModelos:
    def test_periodo_nomina_creacion_y_str(self, empresa_a):
        from apps.nomina.models import PeriodoNomina

        hoy = timezone.now().date()
        periodo = PeriodoNomina.objects.create(
            id_empresa=empresa_a,
            nombre_periodo="Quincena Mayo 2026",
            fecha_inicio=hoy,
            fecha_fin=hoy + timezone.timedelta(days=14),
            fecha_pago=hoy + timezone.timedelta(days=15),
            tipo_periodo="QUINCENAL",
            estado="ABIERTO",
        )
        assert "Quincena Mayo 2026" in str(periodo)
        assert periodo.estado == "ABIERTO"
        assert periodo.activo is True

    def test_periodo_nomina_estados(self, empresa_a):
        from apps.nomina.models import PeriodoNomina

        hoy = timezone.now().date()
        for estado in ("ABIERTO", "PROCESANDO", "CERRADO", "PAGADO"):
            p = PeriodoNomina.objects.create(
                id_empresa=empresa_a,
                nombre_periodo=f"Periodo {estado}",
                fecha_inicio=hoy,
                fecha_fin=hoy + timezone.timedelta(days=6),
                fecha_pago=hoy + timezone.timedelta(days=7),
                tipo_periodo="SEMANAL",
                estado=estado,
            )
            assert p.estado == estado

    def test_concepto_nomina_fijo(self, empresa_a):
        from apps.nomina.models import ConceptoNomina

        concepto = ConceptoNomina.objects.create(
            id_empresa=empresa_a,
            codigo_concepto="SB001",
            nombre_concepto="Sueldo Base",
            tipo_concepto="DEVENGADO",
            categoria="SUELDO_BASE",
            es_fijo=True,
            monto_fijo=Decimal("500.00"),
        )
        assert "SB001" in str(concepto)
        assert "Sueldo Base" in str(concepto)
        assert concepto.monto_fijo == Decimal("500.00")

    def test_concepto_nomina_porcentaje(self, empresa_a):
        from apps.nomina.models import ConceptoNomina

        concepto = ConceptoNomina.objects.create(
            id_empresa=empresa_a,
            codigo_concepto="SS001",
            nombre_concepto="Seguro Social",
            tipo_concepto="DEDUCCION",
            categoria="SEGURO_SOCIAL",
            es_porcentaje=True,
            porcentaje=Decimal("9.00"),
        )
        assert concepto.porcentaje == Decimal("9.00")

    def test_concepto_nomina_unicidad_empresa_codigo(self, empresa_a):
        from django.db import IntegrityError
        from apps.nomina.models import ConceptoNomina

        ConceptoNomina.objects.create(
            id_empresa=empresa_a,
            codigo_concepto="UNICO01",
            nombre_concepto="Concepto Único",
            tipo_concepto="DEVENGADO",
            categoria="BONO",
        )
        with pytest.raises(IntegrityError):
            ConceptoNomina.objects.create(
                id_empresa=empresa_a,
                codigo_concepto="UNICO01",
                nombre_concepto="Concepto Duplicado",
                tipo_concepto="DEVENGADO",
                categoria="BONO",
            )

    def test_concepto_nomina_mismo_codigo_otra_empresa(self, empresa_a, empresa_b):
        from apps.nomina.models import ConceptoNomina

        ConceptoNomina.objects.create(
            id_empresa=empresa_a,
            codigo_concepto="COM01",
            nombre_concepto="Comisión A",
            tipo_concepto="DEVENGADO",
            categoria="COMISION",
        )
        c = ConceptoNomina.objects.create(
            id_empresa=empresa_b,
            codigo_concepto="COM01",
            nombre_concepto="Comisión B",
            tipo_concepto="DEVENGADO",
            categoria="COMISION",
        )
        assert c.pk is not None


# ─────────────────────────────────────────────────────────────────────────────
# Tesorería — OperacionCambioDivisa
# ─────────────────────────────────────────────────────────────────────────────


class TestTesoreriaModelos:
    @pytest.fixture
    def moneda_bs(self, db, empresa_a):
        from apps.finanzas.models import Moneda

        return Moneda.objects.create(
            nombre="Bolívar Soberano",
            codigo_iso="VES",
            simbolo="Bs.",
            tipo_moneda="fiat",
        )

    def test_operacion_cambio_divisa_creacion(self, empresa_a, moneda_usd, moneda_bs):
        from apps.tesoreria.models import OperacionCambioDivisa

        op = OperacionCambioDivisa.objects.create(
            empresa=empresa_a,
            numero_operacion="OCD-2026-001",
            fecha_operacion=timezone.now(),
            tipo_operacion="COMPRA",
            moneda_origen=moneda_bs,
            moneda_destino=moneda_usd,
            monto_origen=Decimal("36.00"),
            tasa_cambio=Decimal("36.00"),
            monto_destino=Decimal("1.00"),
        )
        assert op.pk is not None
        assert "OCD-2026-001" in str(op)
        assert "COMPRA" in str(op)

    def test_operacion_cambio_venta(self, empresa_a, moneda_usd, moneda_bs):
        from apps.tesoreria.models import OperacionCambioDivisa

        op = OperacionCambioDivisa.objects.create(
            empresa=empresa_a,
            numero_operacion="OCD-2026-002",
            fecha_operacion=timezone.now(),
            tipo_operacion="VENTA",
            moneda_origen=moneda_usd,
            moneda_destino=moneda_bs,
            monto_origen=Decimal("100.00"),
            tasa_cambio=Decimal("36.50"),
            monto_destino=Decimal("3650.00"),
        )
        assert op.tipo_operacion == "VENTA"
        assert op.activo is True

    def test_operacion_unicidad_empresa_numero(self, empresa_a, moneda_usd, moneda_bs):
        from django.db import IntegrityError
        from apps.tesoreria.models import OperacionCambioDivisa

        OperacionCambioDivisa.objects.create(
            empresa=empresa_a,
            numero_operacion="OCD-UNICO",
            fecha_operacion=timezone.now(),
            tipo_operacion="COMPRA",
            moneda_origen=moneda_bs,
            moneda_destino=moneda_usd,
            monto_origen=Decimal("36.00"),
            tasa_cambio=Decimal("36.00"),
            monto_destino=Decimal("1.00"),
        )
        with pytest.raises(IntegrityError):
            OperacionCambioDivisa.objects.create(
                empresa=empresa_a,
                numero_operacion="OCD-UNICO",
                fecha_operacion=timezone.now(),
                tipo_operacion="VENTA",
                moneda_origen=moneda_usd,
                moneda_destino=moneda_bs,
                monto_origen=Decimal("1.00"),
                tasa_cambio=Decimal("36.00"),
                monto_destino=Decimal("36.00"),
            )


# ─────────────────────────────────────────────────────────────────────────────
# Despacho — modelo sin dependencia a Pedido (id_pedido nullable)
# ─────────────────────────────────────────────────────────────────────────────


class TestDespachoModelo:
    def test_despacho_creacion_y_str(self, empresa_a, almacen_despacho):
        from apps.despacho.models import Despacho

        despacho = Despacho.objects.create(
            id_empresa=empresa_a,
            numero_despacho="DSP-2026-001",
            fecha_despacho=timezone.now(),
            id_almacen_origen=almacen_despacho,
            direccion_destino="Av. Principal, Caracas",
            estado_despacho="PENDIENTE",
        )
        assert "DSP-2026-001" in str(despacho)
        assert "PENDIENTE" in str(despacho)
        assert despacho.activo is True

    def test_despacho_transicion_estados(self, empresa_a, almacen_despacho):
        from apps.despacho.models import Despacho

        for estado in ("PENDIENTE", "EN_RUTA", "ENTREGADO", "DEVUELTO", "CANCELADO"):
            d = Despacho.objects.create(
                id_empresa=empresa_a,
                numero_despacho=f"DSP-{estado}",
                fecha_despacho=timezone.now(),
                id_almacen_origen=almacen_despacho,
                direccion_destino="Destino Test",
                estado_despacho=estado,
            )
            assert d.estado_despacho == estado

    def test_despacho_sin_venta_ni_pedido(self, empresa_a, almacen_despacho):
        """Despacho manual sin NotaVenta ni Pedido vinculado (ambos nullables)."""
        from apps.despacho.models import Despacho

        d = Despacho.objects.create(
            id_empresa=empresa_a,
            numero_despacho="DSP-AUTONOMO",
            fecha_despacho=timezone.now(),
            id_almacen_origen=almacen_despacho,
            direccion_destino="Almacén Transitorio",
        )
        assert d.id_pedido is None
        assert d.id_nota_venta is None


# ─────────────────────────────────────────────────────────────────────────────
# Costos — CostoEstandarProducto (requiere Producto + Moneda)
# ─────────────────────────────────────────────────────────────────────────────


class TestCostosModelos:
    def test_costo_estandar_producto_creacion(self, empresa_a, producto_m11, moneda_usd):
        from apps.costos.models import CostoEstandarProducto

        hoy = timezone.now().date()
        costo = CostoEstandarProducto.objects.create(
            id_empresa=empresa_a,
            id_producto=producto_m11,
            tipo_costo="MATERIAL_DIRECTO",
            costo_unitario_estandar=Decimal("12.50"),
            id_moneda=moneda_usd,
            fecha_vigencia_desde=hoy,
        )
        assert costo.pk is not None
        assert costo.costo_unitario_estandar == Decimal("12.50")
        assert costo.activo is True

    def test_costo_estandar_multiples_tipos(self, empresa_a, producto_m11, moneda_usd):
        from apps.costos.models import CostoEstandarProducto

        hoy = timezone.now().date()
        tipos = ["MATERIAL_DIRECTO", "MANO_OBRA_DIRECTA", "COSTOS_INDIRECTOS", "OVERHEAD"]
        for tipo in tipos:
            c = CostoEstandarProducto.objects.create(
                id_empresa=empresa_a,
                id_producto=producto_m11,
                tipo_costo=tipo,
                costo_unitario_estandar=Decimal("5.00"),
                id_moneda=moneda_usd,
                fecha_vigencia_desde=hoy,
                fecha_vigencia_hasta=hoy + timezone.timedelta(days=30),
            )
            assert c.tipo_costo == tipo

    def test_costo_estandar_con_vigencia(self, empresa_a, producto_m11, moneda_usd):
        from apps.costos.models import CostoEstandarProducto

        desde = timezone.now().date()
        hasta = desde + timezone.timedelta(days=90)
        c = CostoEstandarProducto.objects.create(
            id_empresa=empresa_a,
            id_producto=producto_m11,
            tipo_costo="OVERHEAD",
            costo_unitario_estandar=Decimal("2.00"),
            id_moneda=moneda_usd,
            fecha_vigencia_desde=desde,
            fecha_vigencia_hasta=hasta,
        )
        assert c.fecha_vigencia_hasta == hasta
