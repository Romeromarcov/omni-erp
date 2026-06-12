"""
Cobertura del filtro ``?cliente=`` del CuentaPorCobrarViewSet (Plan D — D1).

El filtro acepta el PK del ``crm.Cliente`` (UUID) o el id externo (Odoo, no-UUID):
la FK ``cliente`` solo se filtra si el valor es un UUID válido; en cualquier caso
se filtra por ``cliente_externo_id``. Ambas ramas deben responder 200 sin romper.
"""

import pytest

from rest_framework.test import APIClient

URL = "/api/cxc/cuentas-por-cobrar/"


@pytest.mark.django_db
def test_filtro_cliente_uuid_valido(user_a):
    client = APIClient()
    client.force_authenticate(user=user_a)
    resp = client.get(URL, {"cliente": "11111111-1111-1111-1111-111111111111"})
    assert resp.status_code == 200


@pytest.mark.django_db
def test_filtro_cliente_id_externo_no_uuid(user_a):
    """Un id externo (Odoo) no-UUID no rompe el filtro; no lanza ValueError."""
    client = APIClient()
    client.force_authenticate(user=user_a)
    resp = client.get(URL, {"cliente": "ODOO-123"})
    assert resp.status_code == 200
