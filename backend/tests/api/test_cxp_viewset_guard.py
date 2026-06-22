"""
Integridad financiera — CuentaPorPagarViewSet no permite CRUD libre.

Deuda nueva (auditoría 2026-06-21): el ViewSet de CxP era un ``BaseModelViewSet``
(CRUD completo), así que un cliente podía hacer ``PATCH``/``PUT`` directo de
``monto_pendiente``/``estado`` (p. ej. marcar ``PAGADA`` sin abonos o alterar el
saldo) o ``DELETE`` de la cuenta, saltándose el flujo de abono atómico
(lock + tope + asiento). Es el mismo bug que ya se corrigió en CxC
(auditoría 2026-06-10); aquí se espeja el fix.

Ahora se bloquean PUT/PATCH/DELETE (405); quedan los GET (list/retrieve/aging),
la acción POST ``abonar`` (única escritura del saldo) y el POST de creación.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cuentas_por_pagar.models import AbonoCxP, CuentaPorPagar

URL = "/api/cuentas-por-pagar/cuentas-por-pagar/"

pytestmark = pytest.mark.django_db


def _today():
    return timezone.now().date()


@pytest.fixture
def proveedor_a(empresa_a):
    from apps.proveedores.models import Proveedor

    return Proveedor.objects.create(
        razon_social="Proveedor Guard S.A.",
        rif="J-22222222-2",
        id_empresa=empresa_a,
    )


@pytest.fixture
def cxp_a(empresa_a, proveedor_a):
    return CuentaPorPagar.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor_a,
        monto_total=Decimal("1000.00"),
        monto_pendiente=Decimal("1000.00"),
        fecha_emision=_today(),
        fecha_vencimiento=_today() + timedelta(days=30),
        estado="PENDIENTE",
    )


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


class TestCuentaPorPagarViewSetGuard:
    def test_patch_estado_bloqueado_405(self, cxp_a, client_a):
        resp = client_a.patch(f"{URL}{cxp_a.pk}/", {"estado": "PAGADA"}, format="json")
        assert resp.status_code == 405
        cxp_a.refresh_from_db()
        assert cxp_a.estado == "PENDIENTE"  # no se mutó

    def test_patch_monto_pendiente_bloqueado_405(self, cxp_a, client_a):
        resp = client_a.patch(
            f"{URL}{cxp_a.pk}/", {"monto_pendiente": "1.00"}, format="json"
        )
        assert resp.status_code == 405
        cxp_a.refresh_from_db()
        assert cxp_a.monto_pendiente == Decimal("1000.00")  # no se mutó

    def test_put_bloqueado_405(self, cxp_a, client_a):
        resp = client_a.put(f"{URL}{cxp_a.pk}/", {"monto_pendiente": "5.00"}, format="json")
        assert resp.status_code == 405

    def test_delete_bloqueado_405(self, cxp_a, client_a):
        resp = client_a.delete(f"{URL}{cxp_a.pk}/")
        assert resp.status_code == 405
        assert CuentaPorPagar.objects.filter(pk=cxp_a.pk).exists()

    def test_get_list_sigue_funcionando(self, cxp_a, client_a):
        resp = client_a.get(URL)
        assert resp.status_code == 200

    def test_abonar_sigue_funcionando(self, cxp_a, client_a):
        """La única escritura legítima del saldo (acción POST detalle) sigue viva."""
        resp = client_a.post(
            f"{URL}{cxp_a.pk}/abonar/",
            {"monto": "400.00", "descripcion": "Pago parcial a proveedor"},
            format="json",
        )
        assert resp.status_code == 201
        assert AbonoCxP.objects.filter(cuenta_por_pagar=cxp_a).count() == 1
        cxp_a.refresh_from_db()
        assert cxp_a.estado == "PARCIAL"
