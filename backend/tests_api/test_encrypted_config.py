"""H-SEC-4: ConectorInstancia.configuracion se cifra en reposo (Fernet)."""

import pytest

from django.db import connection


@pytest.mark.django_db
def test_configuracion_cifrada_en_db_y_legible_via_orm(empresa_a):
    from apps.integration_hub.models import ConectorInstancia, ConectorProveedor

    proveedor = ConectorProveedor.objects.create(codigo="odoo_test", nombre="Odoo Test")
    secreto = "api-key-super-secreta-12345"
    inst = ConectorInstancia.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor,
        nombre="Odoo Prod",
        configuracion={"host": "https://x", "api_key": secreto},
    )

    # 1) Vía ORM se lee como dict en claro.
    inst.refresh_from_db()
    assert inst.configuracion["api_key"] == secreto

    # 2) En la BD el valor NO contiene el secreto en claro (está cifrado).
    tabla = ConectorInstancia._meta.db_table
    with connection.cursor() as cur:
        cur.execute(
            f'SELECT configuracion::text FROM "{tabla}" WHERE id_conector = %s',
            [str(inst.id_conector)],
        )
        raw = cur.fetchone()[0]
    assert secreto not in raw, "FUGA: el secreto está en claro en la columna de la BD."
    assert "gAAAA" in raw or "api_key" not in raw, "El valor no parece cifrado (Fernet token)."
