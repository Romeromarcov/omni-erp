"""Siembra el catálogo de proveedores de conectores (Integration Hub).

El catálogo ``ConectorProveedor`` es seed data global (sin ``id_empresa``, fuera
de RLS). Hasta ahora solo existía como fixture
(``fixtures/proveedores_iniciales.json``) que nada cargaba automáticamente: ni el
``entrypoint.sh``, ni una migración, ni ``post_migrate``. Resultado: en cualquier
entorno donde nadie corriera ``loaddata`` a mano, el catálogo quedaba vacío y la
UI no mostraba ningún proveedor para crear conectores.

Esta migración siembra el catálogo de forma **idempotente** (``update_or_create``
por ``codigo``) en cada ``migrate``, de modo que dev/staging/prod siempre tengan
los proveedores disponibles. Reverso = noop (no borramos: las instancias de
conector referencian estas filas vía FK PROTECT).
"""

from django.db import migrations

# Snapshot congelado del catálogo (espejo de fixtures/proveedores_iniciales.json).
# Mantener en sync con el fixture si se agregan proveedores nuevos.
PROVEEDORES = [
    {
        "codigo": "odoo",
        "nombre": "Odoo",
        "descripcion": (
            "Integración con Odoo ERP (Community, Enterprise y SaaS). Soporta "
            "todas las versiones desde la 8 hasta la 18+. Conexión vía XML-RPC "
            "estándar."
        ),
        "icono_url": "/static/integration_hub/icons/odoo.svg",
        "versiones_soportadas": [
            "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18",
        ],
        "capacidades": [
            "contactos", "productos", "pedidos_venta", "pedidos_compra",
            "facturas_venta", "pagos", "inventario",
        ],
        "requiere_url": True,
        "requiere_db": False,
        "estado": "activo",
        "activo": True,
        "orden": 1,
    },
    {
        "codigo": "sap_b1",
        "nombre": "SAP Business One",
        "descripcion": (
            "Integración con SAP Business One vía Service Layer REST API."
        ),
        "icono_url": "/static/integration_hub/icons/sap.svg",
        "versiones_soportadas": ["9.3", "10.0"],
        "capacidades": [
            "contactos", "productos", "pedidos_venta", "pedidos_compra",
            "facturas_venta", "pagos",
        ],
        "requiere_url": True,
        "requiere_db": True,
        "estado": "proximamente",
        "activo": True,
        "orden": 2,
    },
    {
        "codigo": "woocommerce",
        "nombre": "WooCommerce",
        "descripcion": (
            "Integración con tiendas WooCommerce vía REST API. Sincroniza "
            "productos, pedidos y clientes."
        ),
        "icono_url": "/static/integration_hub/icons/woocommerce.svg",
        "versiones_soportadas": ["3.x", "4.x", "5.x", "6.x", "7.x", "8.x"],
        "capacidades": ["contactos", "productos", "pedidos_venta"],
        "requiere_url": True,
        "requiere_db": False,
        "estado": "proximamente",
        "activo": True,
        "orden": 3,
    },
    {
        "codigo": "shopify",
        "nombre": "Shopify",
        "descripcion": (
            "Integración con Shopify vía Admin API. Sincroniza catálogo, "
            "pedidos e inventario."
        ),
        "icono_url": "/static/integration_hub/icons/shopify.svg",
        "versiones_soportadas": [
            "2023-01", "2023-04", "2023-07", "2023-10", "2024-01",
        ],
        "capacidades": ["contactos", "productos", "pedidos_venta", "inventario"],
        "requiere_url": True,
        "requiere_db": False,
        "estado": "proximamente",
        "activo": True,
        "orden": 4,
    },
    {
        "codigo": "google_sheets",
        "nombre": "Google Sheets",
        "descripcion": (
            "Exporta datos de otro conector (p. ej. Odoo) a hojas de Google "
            "Sheets, una pestaña por entidad. Autenticación con cuenta de "
            "servicio; la planilla y las pestañas se crean automáticamente. "
            "Escritura por upsert (clave id_externo)."
        ),
        "icono_url": "/static/integration_hub/icons/google_sheets.svg",
        "versiones_soportadas": ["v4"],
        "capacidades": [
            "contactos", "productos", "pedidos_venta", "pedidos_compra",
            "facturas_venta", "pagos", "inventario",
        ],
        "requiere_url": False,
        "requiere_db": False,
        "estado": "activo",
        "activo": True,
        "orden": 5,
    },
]


def seed_proveedores(apps, schema_editor):
    ConectorProveedor = apps.get_model("integration_hub", "ConectorProveedor")
    for prov in PROVEEDORES:
        defaults = {k: v for k, v in prov.items() if k != "codigo"}
        ConectorProveedor.objects.update_or_create(
            codigo=prov["codigo"], defaults=defaults
        )


def noop_reverse(apps, schema_editor):
    """Reverso noop: no borramos el catálogo (FK PROTECT desde instancias)."""
    return


class Migration(migrations.Migration):

    dependencies = [
        ("integration_hub", "0004_rls_lote3_integration_hub"),
    ]

    operations = [
        migrations.RunPython(seed_proveedores, noop_reverse),
    ]
