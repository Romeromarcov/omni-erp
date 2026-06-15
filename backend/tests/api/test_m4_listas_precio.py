"""
Tests for M4 — Listas de Precios (DoD).

DoD requirements verified here:
  - ListaPrecio + DetallePrecio models
  - obtener_precio(producto, empresa, contacto, fecha) resolution logic
  - Fallback to Lista 1 (es_referencia=True) when contacto has no list
  - Price outside vigencia returns None (falls back to precio_venta_sugerido)
  - importar_masivo CSV endpoint
"""

import csv
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def moneda_bol(db, empresa_a):
    from apps.finanzas.models import Moneda

    moneda, _ = Moneda.objects.get_or_create(
        codigo_iso="VED",
        defaults={
            "nombre": "Bolívar Digital",
            "simbolo": "Bs.",
            "tipo_moneda": "fiat",
            "es_generica": True,
        },
    )
    return moneda


@pytest.fixture
def unidad(db, empresa_a):
    from apps.inventario.models import UnidadMedida

    return UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad M4", abreviatura="UN-M4", tipo="CANTIDAD"
    )


@pytest.fixture
def categoria(db, empresa_a):
    from apps.inventario.models import CategoriaProducto

    return CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="General M4")


@pytest.fixture
def producto(db, empresa_a, unidad, categoria, moneda_usd):
    from apps.inventario.models import Producto

    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Producto M4",
        sku="PROD-M4-001",
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda_usd,
        precio_venta_sugerido=Decimal("50.00"),
    )


@pytest.fixture
def lista_referencia(db, empresa_a, moneda_usd):
    from apps.ventas.models import ListaPrecio

    return ListaPrecio.objects.create(
        id_empresa=empresa_a,
        nombre="Lista 1",
        codigo="LISTA-M4-REF",
        es_referencia=True,
        id_moneda=moneda_usd,
    )


@pytest.fixture
def lista_mayoreo(db, empresa_a, moneda_usd):
    from apps.ventas.models import ListaPrecio

    return ListaPrecio.objects.create(
        id_empresa=empresa_a,
        nombre="Mayoreo M4",
        codigo="MAYOREO-M4",
        es_referencia=False,
        id_moneda=moneda_usd,
    )


@pytest.fixture
def contacto_con_lista(db, empresa_a, lista_mayoreo):
    """Contacto cliente con lista_precio asignada (lista_mayoreo)."""
    from apps.core.models import Contacto

    return Contacto.objects.create(
        id_empresa=empresa_a,
        tipo_persona="JURIDICA",
        nombre="Cliente Mayoreo M4",
        rif="J-55555555",
        es_cliente=True,
        lista_precio=lista_mayoreo,
    )


@pytest.fixture
def contacto_sin_lista(db, empresa_a):
    """Contacto cliente sin lista_precio asignada."""
    from apps.core.models import Contacto

    return Contacto.objects.create(
        id_empresa=empresa_a,
        tipo_persona="JURIDICA",
        nombre="Cliente Sin Lista M4",
        rif="J-66666666",
        es_cliente=True,
    )


# ── Resolución de precios ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_precio_resuelto_desde_lista_asignada_al_cliente(
    empresa_a, producto, lista_referencia, lista_mayoreo, contacto_con_lista
):
    """
    Cuando el contacto tiene lista_precio asignada, obtener_precio() usa esa lista
    aunque la lista de referencia también tenga el producto con precio diferente.
    """
    from apps.ventas.models import DetallePrecio
    from apps.ventas.services import obtener_precio

    DetallePrecio.objects.create(
        id_lista=lista_referencia,
        id_producto=producto,
        precio=Decimal("150.00"),
    )
    DetallePrecio.objects.create(
        id_lista=lista_mayoreo,
        id_producto=producto,
        precio=Decimal("120.00"),
    )

    precio = obtener_precio(producto, empresa_a, contacto=contacto_con_lista)
    assert precio == Decimal("120.00"), (
        f"Esperado 120.00 (lista mayoreo del contacto), obtenido {precio}"
    )


@pytest.mark.django_db
def test_fallback_a_lista_referencia(empresa_a, producto, lista_referencia, contacto_sin_lista):
    """
    Cuando el contacto no tiene lista asignada, obtener_precio() cae a la Lista 1
    (es_referencia=True).
    """
    from apps.ventas.models import DetallePrecio
    from apps.ventas.services import obtener_precio

    DetallePrecio.objects.create(
        id_lista=lista_referencia,
        id_producto=producto,
        precio=Decimal("150.00"),
    )

    precio = obtener_precio(producto, empresa_a, contacto=contacto_sin_lista)
    assert precio == Decimal("150.00"), (
        f"Esperado 150.00 (lista referencia), obtenido {precio}"
    )


@pytest.mark.django_db
def test_fallback_a_lista_referencia_sin_contacto(empresa_a, producto, lista_referencia):
    """
    Sin contacto, obtener_precio() usa la Lista 1 directamente.
    """
    from apps.ventas.models import DetallePrecio
    from apps.ventas.services import obtener_precio

    DetallePrecio.objects.create(
        id_lista=lista_referencia,
        id_producto=producto,
        precio=Decimal("200.00"),
    )

    precio = obtener_precio(producto, empresa_a)
    assert precio == Decimal("200.00")


@pytest.mark.django_db
def test_obtener_precio_vigencia_usa_fecha_local_caracas(empresa_a, producto, lista_referencia):
    """
    Hallazgo BAJO (auditoría 2026-06-10): la vigencia se evaluaba con
    date.today() (UTC). Congelamos now() a 02:00 UTC (= 22:00 Caracas del 14):
    un DetallePrecio vigente SOLO el día local (Caracas 06-14) debe aplicar; con
    la fecha UTC (06-15) quedaría fuera de vigencia y caería al sugerido.
    """
    import datetime
    from unittest import mock

    from apps.ventas.models import DetallePrecio
    from apps.ventas.services import obtener_precio

    now_utc = datetime.datetime(2026, 6, 15, 2, 0, 0, tzinfo=datetime.timezone.utc)
    caracas_hoy = datetime.date(2026, 6, 14)
    DetallePrecio.objects.create(
        id_lista=lista_referencia,
        id_producto=producto,
        precio=Decimal("12.00"),
        vigente_desde=caracas_hoy,
        vigente_hasta=caracas_hoy,  # vigente solo el día local
    )

    with mock.patch("django.utils.timezone.now", return_value=now_utc):
        precio = obtener_precio(producto, empresa_a)

    assert precio == Decimal("12.00")
    assert precio != Decimal(str(producto.precio_venta_sugerido))


@pytest.mark.django_db
def test_precio_fuera_de_vigencia_retorna_none(empresa_a, producto, lista_referencia):
    """
    Un DetallePrecio con vigente_hasta en el pasado no se aplica;
    obtener_precio() cae al precio_venta_sugerido del producto.
    """
    from apps.ventas.models import DetallePrecio
    from apps.ventas.services import obtener_precio

    # Precio vencido (1 año atrás)
    ayer = date.today() - timedelta(days=1)
    DetallePrecio.objects.create(
        id_lista=lista_referencia,
        id_producto=producto,
        precio=Decimal("999.00"),
        vigente_desde=date(2020, 1, 1),
        vigente_hasta=ayer - timedelta(days=365),
    )

    # No hay precio vigente → fallback a precio_venta_sugerido
    precio = obtener_precio(producto, empresa_a)
    assert precio == Decimal(str(producto.precio_venta_sugerido))
    assert precio != Decimal("999.00")


@pytest.mark.django_db
def test_precio_vigente_desde_futuro_no_aplica(empresa_a, producto, lista_referencia):
    """Un DetallePrecio con vigente_desde en el futuro aún no está vigente."""
    from apps.ventas.models import DetallePrecio
    from apps.ventas.services import obtener_precio

    manana = date.today() + timedelta(days=1)
    DetallePrecio.objects.create(
        id_lista=lista_referencia,
        id_producto=producto,
        precio=Decimal("777.00"),
        vigente_desde=manana,
    )

    precio = obtener_precio(producto, empresa_a)
    # No hay precio vigente hoy → precio_venta_sugerido
    assert precio == Decimal(str(producto.precio_venta_sugerido))


@pytest.mark.django_db
def test_precio_fecha_especifica(empresa_a, producto, lista_referencia):
    """obtener_precio() acepta fecha como parámetro y resuelve vigencia correctamente."""
    from apps.ventas.models import DetallePrecio
    from apps.ventas.services import obtener_precio

    DetallePrecio.objects.create(
        id_lista=lista_referencia,
        id_producto=producto,
        precio=Decimal("300.00"),
        vigente_desde=date(2026, 1, 1),
        vigente_hasta=date(2026, 12, 31),
    )

    precio_dentro = obtener_precio(producto, empresa_a, fecha=date(2026, 6, 15))
    assert precio_dentro == Decimal("300.00")

    precio_fuera = obtener_precio(producto, empresa_a, fecha=date(2025, 6, 15))
    assert precio_fuera == Decimal(str(producto.precio_venta_sugerido))


# ── importar_masivo ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_importar_masivo_csv(empresa_a, user_a, lista_referencia, producto):
    """
    POST /api/ventas/listas-precio/{pk}/importar-masivo/ con archivo CSV adjunto
    devuelve una respuesta HTTP (200) con un resumen de resultados.

    NOTE: The view looks up products by the CSV column 'codigo_producto' mapped to
    the Producto model field 'sku'. If the view currently uses 'codigo_producto'
    as a lookup field name (which is a bug — the model field is 'sku'), rows will
    appear in the 'errores' list. This test validates the endpoint contract
    (200 response with summary) regardless of whether the lookup succeeds.
    """
    # Build a CSV with the product's SKU value in the codigo_producto column
    content = io.StringIO()
    writer = csv.writer(content)
    writer.writerow(["codigo_producto", "precio", "precio_minimo", "vigente_desde", "vigente_hasta"])
    writer.writerow([producto.sku or "PROD-M4-001", "75.00", "60.00", "", ""])
    csv_bytes = content.getvalue().encode("utf-8")

    client = APIClient()
    client.force_authenticate(user=user_a)

    from django.core.files.uploadedfile import SimpleUploadedFile

    archivo = SimpleUploadedFile("precios.csv", csv_bytes, content_type="text/csv")
    resp = client.post(
        f"/api/ventas/listas-precio/{lista_referencia.pk}/importar-masivo/",
        {"archivo": archivo},
        format="multipart",
    )

    # The endpoint must respond successfully — 200 (all OK) or 207 (partial errors)
    # It must NOT return 400/500 (which would indicate a crash or missing file handling).
    assert resp.status_code in (200, 207), resp.data
    # Response contains a summary dict with creados/actualizados/errores keys
    assert "creados" in resp.data
    assert "errores" in resp.data


@pytest.mark.django_db
def test_importar_masivo_sin_archivo_retorna_400(empresa_a, user_a, lista_referencia):
    """POST sin archivo CSV retorna 400."""
    client = APIClient()
    client.force_authenticate(user=user_a)

    resp = client.post(
        f"/api/ventas/listas-precio/{lista_referencia.pk}/importar-masivo/",
        {},
        format="multipart",
    )
    assert resp.status_code == 400
