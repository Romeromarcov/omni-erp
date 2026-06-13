"""
Tests P0-2 (BUG-C1, auditoría integral 2026-06-10): `AbonoCxCViewSet` deja de
ser CRUD libre.

- POST /api/cxc/abonos-cxc/ delega en el service `registrar_abono`
  (atómico + lock + tope de saldo) y actualiza saldo/estado de la CxC.
- monto ≤ 0, monto > saldo o monto inválido → 400.
- CxC de otra empresa (o inexistente) → 404, sin crear el abono.
- PUT / PATCH / DELETE → 405 (la anulación va por proceso, no por API).
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db.models import Sum
from django.utils import timezone
from rest_framework.test import APIClient

from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar

URL_ABONOS = "/api/cxc/abonos-cxc/"


def _today():
    return timezone.now().date()


def _saldo(cxc) -> Decimal:
    total = cxc.abonos.aggregate(t=Sum("monto"))["t"] or Decimal("0")
    return cxc.monto - total


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────


@pytest.fixture
def cxc_a(db, empresa_a):
    """CxC pendiente de Empresa A por 1000.00 (deudor externo, sin crm.Cliente)."""
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
def cxc_b(db, empresa_b):
    """CxC pendiente de Empresa B — para tests de aislamiento."""
    return CuentaPorCobrar.objects.create(
        empresa=empresa_b,
        cliente_externo_id="odoo-99",
        cliente_externo_nombre="Cliente Externo B",
        monto=Decimal("500.00"),
        fecha_emision=_today(),
        fecha_vencimiento=_today() + timedelta(days=30),
        estado="pendiente",
    )


@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


# ─────────────────────────────────────────────
# Create: delega en registrar_abono
# ─────────────────────────────────────────────


class TestAbonoCxCCreate:
    def test_abono_parcial_actualiza_saldo_y_estado(self, db, cxc_a, client_a):
        resp = client_a.post(
            URL_ABONOS,
            {"cuenta_por_cobrar": cxc_a.pk, "monto": "400.00", "descripcion": "Pago parcial"},
            format="json",
        )
        assert resp.status_code == 201
        cxc_a.refresh_from_db()
        assert cxc_a.estado == "parcial"
        assert _saldo(cxc_a) == Decimal("600.00")
        assert cxc_a.abonos.count() == 1
        assert Decimal(str(resp.data["monto"])) == Decimal("400.00")

    def test_abono_total_marca_pagada(self, db, cxc_a, client_a):
        resp = client_a.post(
            URL_ABONOS,
            {"cuenta_por_cobrar": cxc_a.pk, "monto": "1000.00"},
            format="json",
        )
        assert resp.status_code == 201
        cxc_a.refresh_from_db()
        assert cxc_a.estado == "pagada"
        assert _saldo(cxc_a) == Decimal("0.00")

    def test_abono_registra_usuario_autenticado(self, db, cxc_a, client_a, user_a):
        client_a.post(
            URL_ABONOS, {"cuenta_por_cobrar": cxc_a.pk, "monto": "100.00"}, format="json"
        )
        abono = cxc_a.abonos.get()
        assert abono.usuario_id == user_a.pk

    def test_abono_monto_cero_retorna_400(self, db, cxc_a, client_a):
        resp = client_a.post(
            URL_ABONOS, {"cuenta_por_cobrar": cxc_a.pk, "monto": "0"}, format="json"
        )
        assert resp.status_code == 400
        assert cxc_a.abonos.count() == 0

    def test_abono_monto_negativo_retorna_400(self, db, cxc_a, client_a):
        resp = client_a.post(
            URL_ABONOS, {"cuenta_por_cobrar": cxc_a.pk, "monto": "-50.00"}, format="json"
        )
        assert resp.status_code == 400
        assert cxc_a.abonos.count() == 0

    def test_abono_excede_saldo_retorna_400(self, db, cxc_a, client_a):
        resp = client_a.post(
            URL_ABONOS, {"cuenta_por_cobrar": cxc_a.pk, "monto": "1000.01"}, format="json"
        )
        assert resp.status_code == 400
        cxc_a.refresh_from_db()
        assert cxc_a.estado == "pendiente"
        assert cxc_a.abonos.count() == 0

    def test_abono_sobre_cxc_pagada_retorna_400(self, db, cxc_a, client_a):
        client_a.post(
            URL_ABONOS, {"cuenta_por_cobrar": cxc_a.pk, "monto": "1000.00"}, format="json"
        )
        resp = client_a.post(
            URL_ABONOS, {"cuenta_por_cobrar": cxc_a.pk, "monto": "1.00"}, format="json"
        )
        assert resp.status_code == 400
        assert cxc_a.abonos.count() == 1

    def test_abono_sin_monto_retorna_400(self, db, cxc_a, client_a):
        resp = client_a.post(
            URL_ABONOS, {"cuenta_por_cobrar": cxc_a.pk}, format="json"
        )
        assert resp.status_code == 400

    def test_abono_monto_invalido_retorna_400(self, db, cxc_a, client_a):
        resp = client_a.post(
            URL_ABONOS, {"cuenta_por_cobrar": cxc_a.pk, "monto": "no-es-numero"}, format="json"
        )
        assert resp.status_code == 400

    def test_abono_sin_cxc_retorna_400(self, db, client_a):
        resp = client_a.post(URL_ABONOS, {"monto": "100.00"}, format="json")
        assert resp.status_code == 400


# ─────────────────────────────────────────────
# Aislamiento multi-tenant (R-CODE-1)
# ─────────────────────────────────────────────


class TestAbonoCxCAislamiento:
    def test_abonar_cxc_de_otra_empresa_retorna_404(self, db, cxc_a, client_b):
        """user_b (Empresa B) no puede abonar a una CxC de Empresa A."""
        resp = client_b.post(
            URL_ABONOS, {"cuenta_por_cobrar": cxc_a.pk, "monto": "100.00"}, format="json"
        )
        assert resp.status_code == 404
        assert cxc_a.abonos.count() == 0
        cxc_a.refresh_from_db()
        assert cxc_a.estado == "pendiente"

    def test_abonar_cxc_inexistente_retorna_404(self, db, client_a):
        resp = client_a.post(
            URL_ABONOS, {"cuenta_por_cobrar": 999999, "monto": "100.00"}, format="json"
        )
        assert resp.status_code == 404

    def test_list_no_expone_abonos_de_otra_empresa(self, db, cxc_a, cxc_b, user_a, user_b, client_a):
        AbonoCxC.objects.create(cuenta_por_cobrar=cxc_a, monto=Decimal("100.00"), usuario=user_a)
        AbonoCxC.objects.create(cuenta_por_cobrar=cxc_b, monto=Decimal("50.00"), usuario=user_b)
        resp = client_a.get(URL_ABONOS)
        assert resp.status_code == 200
        resultados = resp.data["results"] if "results" in resp.data else resp.data
        assert len(resultados) == 1
        assert str(resultados[0]["cuenta_por_cobrar"]) == str(cxc_a.pk)


# ─────────────────────────────────────────────
# update / partial_update / destroy bloqueados
# ─────────────────────────────────────────────


class TestAbonoCxCMetodosBloqueados:
    @pytest.fixture
    def abono_a(self, db, cxc_a, user_a):
        return AbonoCxC.objects.create(
            cuenta_por_cobrar=cxc_a, monto=Decimal("200.00"), usuario=user_a
        )

    def test_delete_retorna_405_y_no_borra(self, db, abono_a, client_a):
        resp = client_a.delete(f"{URL_ABONOS}{abono_a.pk}/")
        assert resp.status_code == 405
        assert AbonoCxC.objects.filter(pk=abono_a.pk).exists()

    def test_put_retorna_405(self, db, abono_a, cxc_a, client_a):
        resp = client_a.put(
            f"{URL_ABONOS}{abono_a.pk}/",
            {"cuenta_por_cobrar": cxc_a.pk, "monto": "999.00"},
            format="json",
        )
        assert resp.status_code == 405
        abono_a.refresh_from_db()
        assert abono_a.monto == Decimal("200.00")

    def test_patch_retorna_405(self, db, abono_a, client_a):
        resp = client_a.patch(
            f"{URL_ABONOS}{abono_a.pk}/", {"monto": "999.00"}, format="json"
        )
        assert resp.status_code == 405
        abono_a.refresh_from_db()
        assert abono_a.monto == Decimal("200.00")

    def test_get_detalle_sigue_disponible(self, db, abono_a, client_a):
        resp = client_a.get(f"{URL_ABONOS}{abono_a.pk}/")
        assert resp.status_code == 200
        assert Decimal(str(resp.data["monto"])) == Decimal("200.00")
