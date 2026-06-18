"""
Integridad financiera — CuentaPorCobrarViewSet no permite CRUD libre.

Hallazgo BAJO de la auditoría integral 2026-06-10: el ViewSet era un
``BaseModelViewSet`` (CRUD completo), así que un cliente podía hacer
``PATCH``/``PUT`` directo de ``monto``/``estado`` (p. ej. marcar ``pagada`` sin
abonos o alterar el saldo), saltándose el flujo de abono atómico (lock + tope +
asiento).

Ahora se bloquean PUT/PATCH/DELETE (405); quedan los GET (list/retrieve/aging/
estado-cuenta), la acción POST ``abonar`` (única escritura del saldo) y el POST
de creación (lo usan los flujos de venta/integración y el seed de los E2E).
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from django.utils import timezone
from rest_framework.test import APIClient

from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar

URL = "/api/cxc/cuentas-por-cobrar/"

pytestmark = pytest.mark.django_db


def _today():
    return timezone.now().date()


@pytest.fixture
def cxc_a(empresa_a):
    return CuentaPorCobrar.objects.create(
        empresa=empresa_a,
        cliente_externo_id="odoo-42",
        cliente_externo_nombre="Cliente Externo A",
        monto=Decimal("1000.00"),
        fecha_emision=_today(),
        fecha_vencimiento=_today() + timedelta(days=30),
        estado="pendiente",
    )


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


class TestCuentaPorCobrarViewSetGuard:
    def test_patch_estado_bloqueado_405(self, cxc_a, client_a):
        resp = client_a.patch(f"{URL}{cxc_a.pk}/", {"estado": "pagada"}, format="json")
        assert resp.status_code == 405
        cxc_a.refresh_from_db()
        assert cxc_a.estado == "pendiente"  # no se mutó

    def test_patch_monto_bloqueado_405(self, cxc_a, client_a):
        resp = client_a.patch(f"{URL}{cxc_a.pk}/", {"monto": "1.00"}, format="json")
        assert resp.status_code == 405
        cxc_a.refresh_from_db()
        assert cxc_a.monto == Decimal("1000.00")  # no se mutó

    def test_put_bloqueado_405(self, cxc_a, client_a):
        resp = client_a.put(f"{URL}{cxc_a.pk}/", {"monto": "5.00"}, format="json")
        assert resp.status_code == 405

    def test_delete_bloqueado_405(self, cxc_a, client_a):
        resp = client_a.delete(f"{URL}{cxc_a.pk}/")
        assert resp.status_code == 405
        assert CuentaPorCobrar.objects.filter(pk=cxc_a.pk).exists()

    def test_get_list_sigue_funcionando(self, cxc_a, client_a):
        resp = client_a.get(URL)
        assert resp.status_code == 200

    def test_abonar_sigue_funcionando(self, cxc_a, client_a):
        """La única escritura legítima del saldo (acción POST detalle) sigue viva."""
        resp = client_a.post(
            f"{URL}{cxc_a.pk}/abonar/",
            {"monto": "400.00", "descripcion": "Pago parcial"},
            format="json",
        )
        assert resp.status_code == 201
        assert AbonoCxC.objects.filter(cuenta_por_cobrar=cxc_a).count() == 1
        cxc_a.refresh_from_db()
        assert cxc_a.estado == "parcial"
