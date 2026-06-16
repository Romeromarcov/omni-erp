"""Catálogo base de proveedores de integración (seed canónico).

Fuente de verdad **vigente** del catálogo `ConectorProveedor`. La usa el comando
idempotente ``seed_proveedores_integracion`` que el ``entrypoint.sh`` corre en cada
deploy, de modo que los proveedores base existan siempre (dev/staging/prod) sin
depender de una migración de una sola vez.

Solo deben listarse aquí proveedores cuyo conector esté implementado y registrado
en ``connectors/registry.py`` (hoy: odoo, google_sheets) o que sean placeholders
``estado="proximamente"`` para la UI. Si agregas un proveedor nuevo, agrégalo aquí.
"""

PROVEEDORES_BASE = [
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
        "orden": 2,
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
        "orden": 3,
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
        "orden": 4,
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
        "orden": 5,
    },
]
