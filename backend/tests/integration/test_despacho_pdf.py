"""
Backfill de cobertura — apps/despacho/pdf_nota_entrega.py (plan "Cero Dudas").

- Generación con modelos reales (Despacho + DetalleDespacho): bytes %PDF válidos.
- Ramas con duck-typing (sin DB): pedido vinculado, sin detalles, fechas datetime,
  observaciones presentes.
- Rama de ImportError cuando reportlab no está disponible.
"""
import sys
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from django.utils import timezone

from apps.despacho.pdf_nota_entrega import generar_pdf_nota_entrega

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def unidad(db, empresa_a):
    from apps.inventario.models import UnidadMedida
    return UnidadMedida.objects.create(id_empresa=empresa_a, nombre="Caja", abreviatura="CJ")


@pytest.fixture
def categoria(db, empresa_a):
    from apps.inventario.models import CategoriaProducto
    return CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat PDF")


@pytest.fixture
def producto(db, empresa_a, unidad, categoria, moneda_usd):
    from apps.inventario.models import Producto
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto PDF",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
    )


@pytest.fixture
def almacen(db, empresa_a):
    from apps.almacenes.models import Almacen
    return Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Central PDF", codigo_almacen="ALM-PDF"
    )


@pytest.fixture
def despacho(db, empresa_a, almacen):
    from apps.despacho.models import Despacho
    return Despacho.objects.create(
        id_empresa=empresa_a,
        numero_despacho="DESP-PDF-001",
        fecha_despacho=timezone.now(),
        id_almacen_origen=almacen,
        direccion_destino="Av. Principal, Caracas",
    )


# ── Tests con modelos reales ──────────────────────────────────────────────────

class TestGenerarPdfConModelos:
    def test_pdf_con_detalles(self, despacho, producto, unidad):
        from apps.despacho.models import DetalleDespacho
        DetalleDespacho.objects.create(
            id_despacho=despacho,
            id_producto=producto,
            cantidad_despachada=Decimal("10.0000"),
            id_unidad_medida=unidad,
            lote="LOTE-7",
        )
        DetalleDespacho.objects.create(
            id_despacho=despacho,
            id_producto=producto,
            cantidad_despachada=Decimal("2.5000"),
            id_unidad_medida=unidad,
            lote=None,  # rama "lote or '-'"
        )

        pdf = generar_pdf_nota_entrega(despacho)
        assert isinstance(pdf, bytes)
        assert pdf.startswith(b"%PDF")
        assert b"%%EOF" in pdf
        assert len(pdf) > 1000  # documento real, no vacío

    def test_pdf_sin_detalles_ni_fecha_entrega(self, despacho):
        """Sin ítems → fila 'Sin ítems registrados'; fecha_entrega None → 'Por confirmar'."""
        assert despacho.fecha_entrega_real is None
        assert despacho.fecha_entrega_estimada is None
        pdf = generar_pdf_nota_entrega(despacho)
        assert pdf.startswith(b"%PDF")

    def test_pdf_con_fecha_entrega_y_observaciones(self, despacho):
        despacho.fecha_entrega_estimada = timezone.now() + timedelta(days=2)
        despacho.observaciones = "Entregar en horario de oficina"
        despacho.save()
        pdf = generar_pdf_nota_entrega(despacho)
        assert pdf.startswith(b"%PDF")


# ── Ramas vía duck-typing (sin DB) ────────────────────────────────────────────

class TestGenerarPdfDuckTyping:
    def test_pedido_vinculado_y_fechas_date(self):
        """Cubre la rama de pedido vinculado y empresa sin nombre_legal."""
        ahora = timezone.now()
        despacho = SimpleNamespace(
            id_empresa=SimpleNamespace(nombre_legal="Empresa Duck S.A.", identificador_fiscal="J-1"),
            numero_despacho="DESP-DUCK-1",
            fecha_despacho=ahora,                 # datetime → .date()
            fecha_entrega_real=None,
            fecha_entrega_estimada=ahora.date(),  # date sin .date() → no entra al if
            estado_despacho="EN_TRANSITO",
            id_almacen_origen=SimpleNamespace(nombre_almacen="Duck Origen"),
            direccion_destino="Calle Falsa 123",
            id_pedido="PED-0001",                 # truthy → rama de pedido de referencia
            observaciones="Frágil",
            # sin atributo 'detalles' → rama hasattr(...) False → lista vacía
        )
        pdf = generar_pdf_nota_entrega(despacho)
        assert pdf.startswith(b"%PDF")

    def test_import_error_cuando_no_hay_reportlab(self, monkeypatch):
        """Si reportlab falta, debe levantar ImportError con mensaje accionable."""
        monkeypatch.setitem(sys.modules, "reportlab.lib", None)
        with pytest.raises(ImportError, match="reportlab no está instalado"):
            generar_pdf_nota_entrega(SimpleNamespace())
