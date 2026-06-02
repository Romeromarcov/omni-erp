"""
TRACK-1F-5 · Smoke test integral de los management commands de migración de datos.

Construye CSVs diminutos en memoria (tmp_path), ejecuta cada comando con
``--confirm`` vía ``call_command`` y verifica los conteos creados/actualizados.

Usa los fixtures ``empresa_a`` y ``moneda_usd`` de backend/tests_api/conftest.py.
"""

import pytest

from django.core.management import call_command

from apps.almacenes.models import Almacen
from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.models import CuentaPorCobrar
from apps.inventario.models import Producto, StockActual

pytestmark = pytest.mark.django_db


def _escribir_csv(tmp_path, nombre, contenido):
    archivo = tmp_path / nombre
    archivo.write_text(contenido, encoding="utf-8")
    return str(archivo)


def test_importar_clientes_crea_y_es_idempotente(tmp_path, empresa_a):
    csv_clientes = _escribir_csv(
        tmp_path,
        "clientes.csv",
        "razon_social,rif,nombre_comercial,tipo_cliente,limite_credito,dias_credito\n"
        "Distribuidora Uno C.A.,J-111111111,Distri Uno,CREDITO,1000.00,30\n"
        "Comercial Dos S.A.,J-222222222,,CONTADO,0,0\n",
    )

    call_command(
        "importar_clientes",
        archivo=csv_clientes,
        empresa=str(empresa_a.pk),
        confirm=True,
    )

    assert Cliente.objects.filter(id_empresa=empresa_a).count() == 2
    c1 = Cliente.objects.get(id_empresa=empresa_a, rif="J-111111111")
    assert c1.tipo_cliente == "CREDITO"

    # Reejecutar con razon_social distinta -> actualiza, no duplica (idempotente por RIF)
    csv_update = _escribir_csv(
        tmp_path,
        "clientes2.csv",
        "razon_social,rif,tipo_cliente\n"
        "Distribuidora Uno (Actualizada) C.A.,J-111111111,CONTADO\n",
    )
    call_command(
        "importar_clientes",
        archivo=csv_update,
        empresa=str(empresa_a.pk),
        confirm=True,
    )
    assert Cliente.objects.filter(id_empresa=empresa_a).count() == 2
    c1.refresh_from_db()
    assert c1.razon_social == "Distribuidora Uno (Actualizada) C.A."
    assert c1.tipo_cliente == "CONTADO"


def test_importar_clientes_dry_run_no_escribe(tmp_path, empresa_a):
    csv_clientes = _escribir_csv(
        tmp_path,
        "clientes.csv",
        "razon_social,rif\nCliente Dry S.A.,J-333333333\n",
    )
    call_command("importar_clientes", archivo=csv_clientes, empresa=str(empresa_a.pk))
    assert Cliente.objects.filter(id_empresa=empresa_a).count() == 0


def test_importar_productos_crea(tmp_path, empresa_a, moneda_usd):
    csv_productos = _escribir_csv(
        tmp_path,
        "productos.csv",
        "sku,nombre_producto,categoria,unidad_medida,moneda,costo_promedio,precio_venta_sugerido\n"
        "SKU-001,Producto Uno,General,UND,USD,5.00,10.00\n"
        "SKU-002,Producto Dos,General,UND,USD,3.50,7.00\n",
    )

    call_command(
        "importar_productos",
        archivo=csv_productos,
        empresa=str(empresa_a.pk),
        confirm=True,
    )

    assert Producto.objects.filter(id_empresa=empresa_a).count() == 2
    p = Producto.objects.get(id_empresa=empresa_a, sku="SKU-001")
    assert p.nombre_producto == "Producto Uno"
    assert str(p.precio_venta_sugerido) == "10.0000"


def test_importar_inventario_inicial_crea(tmp_path, empresa_a, moneda_usd):
    # Productos previos
    csv_productos = _escribir_csv(
        tmp_path,
        "productos.csv",
        "sku,nombre_producto,categoria,unidad_medida,moneda\n"
        "SKU-001,Producto Uno,General,UND,USD\n",
    )
    call_command(
        "importar_productos",
        archivo=csv_productos,
        empresa=str(empresa_a.pk),
        confirm=True,
    )

    # Almacén destino
    Almacen.objects.create(
        id_empresa=empresa_a, nombre_almacen="Principal", codigo_almacen="ALM-01"
    )

    csv_stock = _escribir_csv(
        tmp_path,
        "stock.csv",
        "sku,almacen,cantidad_disponible,cantidad_minima\n"
        "SKU-001,ALM-01,150,10\n",
    )
    call_command(
        "importar_inventario_inicial",
        archivo=csv_stock,
        empresa=str(empresa_a.pk),
        confirm=True,
    )

    assert StockActual.objects.count() == 1
    stock = StockActual.objects.get()
    assert str(stock.cantidad_disponible) == "150.0000"

    # Idempotente: reejecutar con cantidad distinta actualiza el mismo registro
    csv_stock2 = _escribir_csv(
        tmp_path,
        "stock2.csv",
        "sku,almacen,cantidad_disponible\nSKU-001,ALM-01,200\n",
    )
    call_command(
        "importar_inventario_inicial",
        archivo=csv_stock2,
        empresa=str(empresa_a.pk),
        confirm=True,
    )
    assert StockActual.objects.count() == 1
    stock.refresh_from_db()
    assert str(stock.cantidad_disponible) == "200.0000"


def test_importar_saldos_cxc_crea(tmp_path, empresa_a):
    # Cliente previo
    csv_clientes = _escribir_csv(
        tmp_path,
        "clientes.csv",
        "razon_social,rif\nDistribuidora Uno C.A.,J-111111111\n",
    )
    call_command(
        "importar_clientes",
        archivo=csv_clientes,
        empresa=str(empresa_a.pk),
        confirm=True,
    )

    csv_saldos = _escribir_csv(
        tmp_path,
        "saldos.csv",
        "rif,monto,fecha_emision,fecha_vencimiento,referencia_externa,estado\n"
        "J-111111111,2500.00,2026-01-15,2026-02-15,FAC-001,pendiente\n",
    )
    call_command(
        "importar_saldos_cxc",
        archivo=csv_saldos,
        empresa=str(empresa_a.pk),
        confirm=True,
    )

    assert CuentaPorCobrar.objects.filter(empresa=empresa_a).count() == 1
    cxc = CuentaPorCobrar.objects.get(empresa=empresa_a)
    assert str(cxc.monto) == "2500.00"
    assert cxc.estado == "pendiente"

    # Idempotente por referencia_externa: reejecutar actualiza el monto
    csv_saldos2 = _escribir_csv(
        tmp_path,
        "saldos2.csv",
        "rif,monto,fecha_emision,fecha_vencimiento,referencia_externa,estado\n"
        "J-111111111,3000.00,2026-01-15,2026-02-15,FAC-001,parcial\n",
    )
    call_command(
        "importar_saldos_cxc",
        archivo=csv_saldos2,
        empresa=str(empresa_a.pk),
        confirm=True,
    )
    assert CuentaPorCobrar.objects.filter(empresa=empresa_a).count() == 1
    cxc.refresh_from_db()
    assert str(cxc.monto) == "3000.00"
    assert cxc.estado == "parcial"


def test_resolver_empresa_por_identificador_fiscal(tmp_path, empresa_a):
    # empresa_a tiene identificador_fiscal "J-12345678-9"
    csv_clientes = _escribir_csv(
        tmp_path,
        "clientes.csv",
        "razon_social,rif\nCliente X,J-444444444\n",
    )
    call_command(
        "importar_clientes",
        archivo=csv_clientes,
        empresa="J-12345678-9",
        confirm=True,
    )
    assert Cliente.objects.filter(id_empresa=empresa_a, rif="J-444444444").exists()
