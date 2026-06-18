"""Comando ``seed_proveedores_integracion`` — idempotente y no destructivo."""
from io import StringIO

import pytest

from django.core.management import call_command

from apps.integration_hub.models import ConectorProveedor
from apps.integration_hub.seed_data import PROVEEDORES_BASE

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _run(*args):
    out = StringIO()
    call_command("seed_proveedores_integracion", *args, stdout=out)
    return out.getvalue()


def test_siembra_todos_los_proveedores_base(db):
    ConectorProveedor.objects.all().delete()
    _run()
    codigos = set(ConectorProveedor.objects.values_list("codigo", flat=True))
    assert codigos == {p["codigo"] for p in PROVEEDORES_BASE}
    # Odoo y Google Sheets activos (conectores implementados)
    assert ConectorProveedor.objects.get(codigo="odoo").estado == "activo"
    assert ConectorProveedor.objects.get(codigo="google_sheets").estado == "activo"


def test_es_idempotente_no_duplica(db):
    ConectorProveedor.objects.all().delete()
    _run()
    _run()
    _run()
    assert ConectorProveedor.objects.count() == len(PROVEEDORES_BASE)


def test_respeta_cambios_del_admin_sin_forzar(db):
    """Sin --forzar, una fila existente editada por el admin NO se pisa."""
    ConectorProveedor.objects.all().delete()
    _run()
    odoo = ConectorProveedor.objects.get(codigo="odoo")
    odoo.estado = "proximamente"
    odoo.nombre = "Odoo (custom)"
    odoo.save(update_fields=["estado", "nombre"])

    _run()  # sin --forzar

    odoo.refresh_from_db()
    assert odoo.estado == "proximamente"
    assert odoo.nombre == "Odoo (custom)"


def test_forzar_reescribe_a_los_valores_base(db):
    ConectorProveedor.objects.all().delete()
    _run()
    odoo = ConectorProveedor.objects.get(codigo="odoo")
    odoo.estado = "proximamente"
    odoo.save(update_fields=["estado"])

    _run("--forzar")

    odoo.refresh_from_db()
    assert odoo.estado == "activo"  # restaurado al valor base
