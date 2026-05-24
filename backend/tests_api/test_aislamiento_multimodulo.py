"""
Tests de aislamiento multi-tenant — cobertura completa de módulos (R-CODE-1).

Cada test verifica que un usuario de Empresa A NO puede ver ni modificar datos
de Empresa B, incluso aunque ambas estén en la misma base de datos.

Módulos cubiertos:
  - ventas        → Cotizacion   (/api/ventas/cotizaciones/)
  - inventario    → CategoriaProducto (/api/inventario/categorias-producto/)
  - finanzas      → Pago         (/api/finanzas/pagos/)
  - compras       → OrdenCompra  (/api/compras/ordenes-compra/)
  - proveedores   → Proveedor    (/api/proveedores/proveedores/)
  - gastos        → CategoriaGasto (/api/gastos/categorias-gasto/)
  - nomina        → PeriodoNomina  (/api/nomina/periodos-nomina/)

Un FAIL = leak de datos entre tenants → bloquea merge.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from rest_framework.test import APIClient

from apps.compras.models import OrdenCompra
from apps.crm.models import Cliente
from apps.finanzas.models import MetodoPago, Pago
from apps.gastos.models import CategoriaGasto
from apps.inventario.models import CategoriaProducto
from apps.nomina.models import PeriodoNomina
from apps.proveedores.models import Proveedor
from apps.ventas.models import Cotizacion

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures compartidos entre módulos
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def metodo_efectivo(db):
    """MetodoPago genérico (sin empresa) necesario para crear Pagos."""
    return MetodoPago.objects.create(
        nombre_metodo="Efectivo Test",
        tipo_metodo="EFECTIVO",
    )


@pytest.fixture
def cliente_a(db, empresa_a):
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Alpha S.A.",
        rif="J-11111111-1",
    )


@pytest.fixture
def cliente_b(db, empresa_b):
    return Cliente.objects.create(
        id_empresa=empresa_b,
        razon_social="Cliente Beta C.A.",
        rif="J-22222222-2",
    )


@pytest.fixture
def proveedor_a(db, empresa_a):
    return Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Proveedor Alpha S.A.",
        rif="J-33333333-3",
    )


@pytest.fixture
def proveedor_b(db, empresa_b):
    return Proveedor.objects.create(
        id_empresa=empresa_b,
        razon_social="Proveedor Beta C.A.",
        rif="J-44444444-4",
    )


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: ventas / Cotizacion
# ─────────────────────────────────────────────────────────────────────────────

URL_COTIZACIONES = "/api/ventas/cotizaciones/"


@pytest.fixture
def cotizacion_a(db, empresa_a, cliente_a, moneda_usd):
    return Cotizacion.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_a,
        id_moneda=moneda_usd,
        numero_cotizacion="COT-A-001",
        fecha_cotizacion=date.today(),
        fecha_vencimiento=date.today() + timedelta(days=30),
        estado="BORRADOR",
    )


@pytest.fixture
def cotizacion_b(db, empresa_b, cliente_b, moneda_usd):
    return Cotizacion.objects.create(
        id_empresa=empresa_b,
        id_cliente=cliente_b,
        id_moneda=moneda_usd,
        numero_cotizacion="COT-B-001",
        fecha_cotizacion=date.today(),
        fecha_vencimiento=date.today() + timedelta(days=30),
        estado="BORRADOR",
    )


@pytest.mark.django_db
class TestAislamientoVentas:
    """R-CODE-1 :: ventas.Cotizacion"""

    def test_list_solo_devuelve_cotizaciones_propias(self, user_a, cotizacion_a, cotizacion_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(URL_COTIZACIONES)
        assert resp.status_code == 200

        data = resp.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_cotizacion"]) for r in resultados}

        assert str(cotizacion_a.id_cotizacion) in ids, "La cotización propia de Empresa A no aparece en el listado."
        assert (
            str(cotizacion_b.id_cotizacion) not in ids
        ), "LEAK: cotización de Empresa B aparece en listado de Empresa A."

    def test_get_cotizacion_ajena_devuelve_404(self, user_a, cotizacion_a, cotizacion_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(f"{URL_COTIZACIONES}{cotizacion_b.id_cotizacion}/")
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al acceder a cotización de Empresa B."

    def test_patch_cotizacion_ajena_devuelve_404(self, user_a, cotizacion_a, cotizacion_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.patch(
            f"{URL_COTIZACIONES}{cotizacion_b.id_cotizacion}/",
            {"estado": "ACEPTADA"},
            format="json",
        )
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al parchear cotización de Empresa B."

        cotizacion_b.refresh_from_db()
        assert (
            cotizacion_b.estado == "BORRADOR"
        ), "CRÍTICO: el estado de la cotización de Empresa B fue modificado desde Empresa A."


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: inventario / CategoriaProducto
# ─────────────────────────────────────────────────────────────────────────────

URL_CAT_PRODUCTO = "/api/inventario/categorias-producto/"


@pytest.fixture
def categoria_a(db, empresa_a):
    return CategoriaProducto.objects.create(
        id_empresa=empresa_a,
        nombre_categoria="Categoría Alpha",
    )


@pytest.fixture
def categoria_b(db, empresa_b):
    return CategoriaProducto.objects.create(
        id_empresa=empresa_b,
        nombre_categoria="Categoría Beta",
    )


@pytest.mark.django_db
class TestAislamientoInventario:
    """R-CODE-1 :: inventario.CategoriaProducto"""

    def test_list_solo_devuelve_categorias_propias(self, user_a, categoria_a, categoria_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(URL_CAT_PRODUCTO)
        assert resp.status_code == 200

        data = resp.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_categoria_producto"]) for r in resultados}

        assert (
            str(categoria_a.id_categoria_producto) in ids
        ), "La categoría propia de Empresa A no aparece en el listado."
        assert (
            str(categoria_b.id_categoria_producto) not in ids
        ), "LEAK: categoría de Empresa B aparece en listado de Empresa A."

    def test_get_categoria_ajena_devuelve_404(self, user_a, categoria_a, categoria_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(f"{URL_CAT_PRODUCTO}{categoria_b.id_categoria_producto}/")
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al acceder a categoría de Empresa B."

    def test_patch_categoria_ajena_devuelve_404(self, user_a, categoria_a, categoria_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.patch(
            f"{URL_CAT_PRODUCTO}{categoria_b.id_categoria_producto}/",
            {"nombre_categoria": "Hackeada"},
            format="json",
        )
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al parchear categoría de Empresa B."

        categoria_b.refresh_from_db()
        assert (
            categoria_b.nombre_categoria == "Categoría Beta"
        ), "CRÍTICO: nombre de categoría de Empresa B fue modificado desde Empresa A."


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: finanzas / Pago
# ─────────────────────────────────────────────────────────────────────────────

URL_PAGOS = "/api/finanzas/pagos/"


@pytest.fixture
def pago_a(db, empresa_a, moneda_usd, metodo_efectivo):
    return Pago.objects.create(
        id_empresa=empresa_a,
        tipo_operacion="INGRESO",
        tipo_documento="PEDIDO",
        id_documento=uuid.uuid4(),
        fecha_pago="2026-01-15T10:00:00Z",
        monto=Decimal("100.00"),
        id_moneda=moneda_usd,
        tasa=Decimal("1.0"),
        id_metodo_pago=metodo_efectivo,
    )


@pytest.fixture
def pago_b(db, empresa_b, moneda_usd, metodo_efectivo):
    return Pago.objects.create(
        id_empresa=empresa_b,
        tipo_operacion="INGRESO",
        tipo_documento="PEDIDO",
        id_documento=uuid.uuid4(),
        fecha_pago="2026-01-15T10:00:00Z",
        monto=Decimal("200.00"),
        id_moneda=moneda_usd,
        tasa=Decimal("1.0"),
        id_metodo_pago=metodo_efectivo,
    )


@pytest.mark.django_db
class TestAislamientoFinanzas:
    """R-CODE-1 :: finanzas.Pago"""

    def test_list_solo_devuelve_pagos_propios(self, user_a, pago_a, pago_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(URL_PAGOS)
        assert resp.status_code == 200

        data = resp.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_pago"]) for r in resultados}

        assert str(pago_a.id_pago) in ids, "El pago propio de Empresa A no aparece en el listado."
        assert str(pago_b.id_pago) not in ids, "LEAK: pago de Empresa B aparece en listado de Empresa A."

    def test_get_pago_ajeno_devuelve_404(self, user_a, pago_a, pago_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(f"{URL_PAGOS}{pago_b.id_pago}/")
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al acceder a pago de Empresa B."

    def test_patch_pago_ajeno_devuelve_404(self, user_a, pago_a, pago_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.patch(
            f"{URL_PAGOS}{pago_b.id_pago}/",
            {"monto": "999.00"},
            format="json",
        )
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al parchear pago de Empresa B."

        pago_b.refresh_from_db()
        assert pago_b.monto == Decimal(
            "200.00"
        ), "CRÍTICO: monto del pago de Empresa B fue modificado desde Empresa A."


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: compras / OrdenCompra
# ─────────────────────────────────────────────────────────────────────────────

URL_ORDENES = "/api/compras/ordenes-compra/"


@pytest.fixture
def orden_a(db, empresa_a, proveedor_a):
    return OrdenCompra.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor_a,
        numero_orden="OC-A-001",
        fecha_orden=date.today(),
        estado="BORRADOR",
    )


@pytest.fixture
def orden_b(db, empresa_b, proveedor_b):
    return OrdenCompra.objects.create(
        id_empresa=empresa_b,
        id_proveedor=proveedor_b,
        numero_orden="OC-B-001",
        fecha_orden=date.today(),
        estado="BORRADOR",
    )


@pytest.mark.django_db
class TestAislamientoCompras:
    """R-CODE-1 :: compras.OrdenCompra"""

    def test_list_solo_devuelve_ordenes_propias(self, user_a, orden_a, orden_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(URL_ORDENES)
        assert resp.status_code == 200

        data = resp.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_orden_compra"]) for r in resultados}

        assert str(orden_a.id_orden_compra) in ids, "La orden propia de Empresa A no aparece en el listado."
        assert str(orden_b.id_orden_compra) not in ids, "LEAK: orden de Empresa B aparece en listado de Empresa A."

    def test_get_orden_ajena_devuelve_404(self, user_a, orden_a, orden_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(f"{URL_ORDENES}{orden_b.id_orden_compra}/")
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al acceder a orden de Empresa B."

    def test_patch_orden_ajena_devuelve_404(self, user_a, orden_a, orden_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.patch(
            f"{URL_ORDENES}{orden_b.id_orden_compra}/",
            {"estado": "APROBADA"},
            format="json",
        )
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al parchear orden de Empresa B."

        orden_b.refresh_from_db()
        assert orden_b.estado == "BORRADOR", "CRÍTICO: estado de orden de Empresa B fue modificado desde Empresa A."


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: proveedores / Proveedor
# ─────────────────────────────────────────────────────────────────────────────

URL_PROVEEDORES = "/api/proveedores/proveedores/"


@pytest.mark.django_db
class TestAislamientoProveedores:
    """R-CODE-1 :: proveedores.Proveedor"""

    def test_list_solo_devuelve_proveedores_propios(self, user_a, proveedor_a, proveedor_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(URL_PROVEEDORES)
        assert resp.status_code == 200

        data = resp.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_proveedor"]) for r in resultados}

        assert str(proveedor_a.id_proveedor) in ids, "El proveedor propio de Empresa A no aparece en el listado."
        assert (
            str(proveedor_b.id_proveedor) not in ids
        ), "LEAK: proveedor de Empresa B aparece en listado de Empresa A."

    def test_get_proveedor_ajeno_devuelve_404(self, user_a, proveedor_a, proveedor_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(f"{URL_PROVEEDORES}{proveedor_b.id_proveedor}/")
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al acceder a proveedor de Empresa B."

    def test_patch_proveedor_ajeno_devuelve_404(self, user_a, proveedor_a, proveedor_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.patch(
            f"{URL_PROVEEDORES}{proveedor_b.id_proveedor}/",
            {"razon_social": "Hackeado S.A."},
            format="json",
        )
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al parchear proveedor de Empresa B."

        proveedor_b.refresh_from_db()
        assert (
            proveedor_b.razon_social == "Proveedor Beta C.A."
        ), "CRÍTICO: razón social de proveedor de Empresa B fue modificada desde Empresa A."


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: gastos / CategoriaGasto
# ─────────────────────────────────────────────────────────────────────────────

URL_CAT_GASTO = "/api/gastos/categorias-gasto/"


@pytest.fixture
def cat_gasto_a(db, empresa_a):
    return CategoriaGasto.objects.create(
        id_empresa=empresa_a,
        nombre_categoria="Gastos Alpha",
    )


@pytest.fixture
def cat_gasto_b(db, empresa_b):
    return CategoriaGasto.objects.create(
        id_empresa=empresa_b,
        nombre_categoria="Gastos Beta",
    )


@pytest.mark.django_db
class TestAislamientoGastos:
    """R-CODE-1 :: gastos.CategoriaGasto"""

    def test_list_solo_devuelve_categorias_propias(self, user_a, cat_gasto_a, cat_gasto_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(URL_CAT_GASTO)
        assert resp.status_code == 200

        data = resp.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_categoria_gasto"]) for r in resultados}

        assert (
            str(cat_gasto_a.id_categoria_gasto) in ids
        ), "La categoría de gasto propia de Empresa A no aparece en el listado."
        assert (
            str(cat_gasto_b.id_categoria_gasto) not in ids
        ), "LEAK: categoría de gasto de Empresa B aparece en listado de Empresa A."

    def test_get_categoria_gasto_ajena_devuelve_404(self, user_a, cat_gasto_a, cat_gasto_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(f"{URL_CAT_GASTO}{cat_gasto_b.id_categoria_gasto}/")
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al acceder a categoría gasto de Empresa B."

    def test_patch_categoria_gasto_ajena_devuelve_404(self, user_a, cat_gasto_a, cat_gasto_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.patch(
            f"{URL_CAT_GASTO}{cat_gasto_b.id_categoria_gasto}/",
            {"nombre_categoria": "Hackeada"},
            format="json",
        )
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al parchear categoría gasto de Empresa B."

        cat_gasto_b.refresh_from_db()
        assert (
            cat_gasto_b.nombre_categoria == "Gastos Beta"
        ), "CRÍTICO: nombre de categoría de Empresa B fue modificado desde Empresa A."


# ─────────────────────────────────────────────────────────────────────────────
# MÓDULO: nomina / PeriodoNomina
# ─────────────────────────────────────────────────────────────────────────────

URL_PERIODOS = "/api/nomina/periodos-nomina/"


@pytest.fixture
def periodo_a(db, empresa_a):
    hoy = date.today()
    return PeriodoNomina.objects.create(
        id_empresa=empresa_a,
        nombre_periodo="Período Alpha Enero",
        fecha_inicio=hoy,
        fecha_fin=hoy + timedelta(days=30),
        fecha_pago=hoy + timedelta(days=35),
        tipo_periodo="MENSUAL",
        estado="ABIERTO",
    )


@pytest.fixture
def periodo_b(db, empresa_b):
    hoy = date.today()
    return PeriodoNomina.objects.create(
        id_empresa=empresa_b,
        nombre_periodo="Período Beta Enero",
        fecha_inicio=hoy,
        fecha_fin=hoy + timedelta(days=30),
        fecha_pago=hoy + timedelta(days=35),
        tipo_periodo="MENSUAL",
        estado="ABIERTO",
    )


@pytest.mark.django_db
class TestAislamientoNomina:
    """R-CODE-1 :: nomina.PeriodoNomina"""

    def test_list_solo_devuelve_periodos_propios(self, user_a, periodo_a, periodo_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(URL_PERIODOS)
        assert resp.status_code == 200

        data = resp.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_periodo_nomina"]) for r in resultados}

        assert str(periodo_a.id_periodo_nomina) in ids, "El período propio de Empresa A no aparece en el listado."
        assert (
            str(periodo_b.id_periodo_nomina) not in ids
        ), "LEAK: período de Empresa B aparece en listado de Empresa A."

    def test_get_periodo_ajeno_devuelve_404(self, user_a, periodo_a, periodo_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.get(f"{URL_PERIODOS}{periodo_b.id_periodo_nomina}/")
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al acceder a período de Empresa B."

    def test_patch_periodo_ajeno_devuelve_404(self, user_a, periodo_a, periodo_b):
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.patch(
            f"{URL_PERIODOS}{periodo_b.id_periodo_nomina}/",
            {"estado": "CERRADO"},
            format="json",
        )
        assert resp.status_code == 404, f"LEAK: status {resp.status_code} al parchear período de Empresa B."

        periodo_b.refresh_from_db()
        assert (
            periodo_b.estado == "ABIERTO"
        ), "CRÍTICO: estado del período de Empresa B fue modificado desde Empresa A."
