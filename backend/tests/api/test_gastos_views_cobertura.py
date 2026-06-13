"""
Backfill de cobertura — apps/gastos/views.py (plan "Cero Dudas").

Complementa `tests/api/test_auth_completo.py` (que ya cubre list/retrieve,
aislamiento multi-tenant y 401 de gastos, categorías y reembolsos) cubriendo
los @action que estaban sin tests:

- categorias-gasto/activas
- gastos/{id}/aprobar y /rechazar (felices + 400)
- gastos/resumen_por_categoria (totales Decimal exactos)
- gastos/pendientes_aprobacion
- reembolsos-gasto/{id}/procesar_pago y /anular (felices + 400)
- reembolsos-gasto/pendientes_pago

Dinero como Decimal con aserciones exactas.
"""
import datetime
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.gastos.models import CategoriaGasto, Gasto, ReembolsoGasto

pytestmark = pytest.mark.django_db

BASE = "/api/gastos/"


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


@pytest.fixture
def categoria_a(empresa_a):
    return CategoriaGasto.objects.create(
        id_empresa=empresa_a, nombre_categoria="Transporte", activo=True
    )


@pytest.fixture
def gasto_pendiente_a(empresa_a, categoria_a, moneda_usd):
    return Gasto.objects.create(
        id_empresa=empresa_a,
        fecha_gasto=datetime.date(2026, 6, 1),
        descripcion="Taxi al aeropuerto",
        monto=Decimal("25.50"),
        id_moneda=moneda_usd,
        id_categoria_gasto=categoria_a,
        estado_gasto="PENDIENTE_APROBACION",
    )


@pytest.fixture
def metodo_pago(empresa_a):
    from apps.finanzas.models import MetodoPago

    return MetodoPago.objects.create(
        empresa=empresa_a, nombre_metodo="Transferencia", tipo_metodo="ELECTRONICO"
    )


@pytest.fixture
def reembolso_pendiente_a(empresa_a, gasto_pendiente_a, moneda_usd, metodo_pago):
    return ReembolsoGasto.objects.create(
        id_empresa=empresa_a,
        id_gasto=gasto_pendiente_a,
        monto_reembolso=Decimal("25.50"),
        id_moneda=moneda_usd,
        id_metodo_pago=metodo_pago,
        fecha_reembolso=datetime.date(2026, 6, 2),
        estado_reembolso="PENDIENTE",
    )


class TestCategoriaGastoActions:
    def test_activas_filtra_inactivas(self, client_a, empresa_a, categoria_a):
        inactiva = CategoriaGasto.objects.create(
            id_empresa=empresa_a, nombre_categoria="Obsoleta", activo=False
        )
        resp = client_a.get(f"{BASE}categorias-gasto/activas/")
        assert resp.status_code == 200
        ids = [r["id_categoria_gasto"] for r in resp.json()]
        assert str(categoria_a.id_categoria_gasto) in ids
        assert str(inactiva.id_categoria_gasto) not in ids

    def test_activas_401_sin_token(self):
        resp = APIClient().get(f"{BASE}categorias-gasto/activas/")
        assert resp.status_code == 401


class TestGastoActions:
    def test_aprobar_ok(self, client_a, gasto_pendiente_a):
        resp = client_a.post(f"{BASE}gastos/{gasto_pendiente_a.id_gasto}/aprobar/")
        assert resp.status_code == 200
        gasto_pendiente_a.refresh_from_db()
        assert gasto_pendiente_a.estado_gasto == "APROBADO"

    def test_aprobar_no_pendiente_400(self, client_a, gasto_pendiente_a):
        gasto_pendiente_a.estado_gasto = "APROBADO"
        gasto_pendiente_a.save()
        resp = client_a.post(f"{BASE}gastos/{gasto_pendiente_a.id_gasto}/aprobar/")
        assert resp.status_code == 400

    def test_aprobar_cross_tenant_404(self, client_b, gasto_pendiente_a):
        resp = client_b.post(f"{BASE}gastos/{gasto_pendiente_a.id_gasto}/aprobar/")
        assert resp.status_code == 404
        gasto_pendiente_a.refresh_from_db()
        assert gasto_pendiente_a.estado_gasto == "PENDIENTE_APROBACION"

    def test_rechazar_ok(self, client_a, gasto_pendiente_a):
        resp = client_a.post(f"{BASE}gastos/{gasto_pendiente_a.id_gasto}/rechazar/")
        assert resp.status_code == 200
        gasto_pendiente_a.refresh_from_db()
        assert gasto_pendiente_a.estado_gasto == "RECHAZADO"

    def test_rechazar_no_pendiente_400(self, client_a, gasto_pendiente_a):
        gasto_pendiente_a.estado_gasto = "RECHAZADO"
        gasto_pendiente_a.save()
        resp = client_a.post(f"{BASE}gastos/{gasto_pendiente_a.id_gasto}/rechazar/")
        assert resp.status_code == 400

    def test_resumen_por_categoria_exacto(
        self, client_a, empresa_a, categoria_a, moneda_usd
    ):
        otra = CategoriaGasto.objects.create(
            id_empresa=empresa_a, nombre_categoria="Alimentación", activo=True
        )
        Gasto.objects.create(
            id_empresa=empresa_a,
            fecha_gasto=datetime.date(2026, 6, 1),
            descripcion="g1",
            monto=Decimal("10.25"),
            id_moneda=moneda_usd,
            id_categoria_gasto=categoria_a,
            estado_gasto="APROBADO",
        )
        Gasto.objects.create(
            id_empresa=empresa_a,
            fecha_gasto=datetime.date(2026, 6, 2),
            descripcion="g2",
            monto=Decimal("5.75"),
            id_moneda=moneda_usd,
            id_categoria_gasto=categoria_a,
            estado_gasto="REEMBOLSADO",
        )
        Gasto.objects.create(
            id_empresa=empresa_a,
            fecha_gasto=datetime.date(2026, 6, 3),
            descripcion="g3",
            monto=Decimal("100.00"),
            id_moneda=moneda_usd,
            id_categoria_gasto=otra,
            estado_gasto="CONTABILIZADO",
        )
        # PENDIENTE_APROBACION no entra en el resumen
        Gasto.objects.create(
            id_empresa=empresa_a,
            fecha_gasto=datetime.date(2026, 6, 4),
            descripcion="g4",
            monto=Decimal("999.99"),
            id_moneda=moneda_usd,
            id_categoria_gasto=categoria_a,
            estado_gasto="PENDIENTE_APROBACION",
        )
        resp = client_a.get(f"{BASE}gastos/resumen_por_categoria/")
        assert resp.status_code == 200
        data = resp.json()
        por_nombre = {r["categoria_nombre"]: r for r in data["resumen_por_categoria"]}
        assert Decimal(str(por_nombre["Transporte"]["total_gastos"])) == Decimal("16.00")
        assert por_nombre["Transporte"]["cantidad_gastos"] == 2
        assert Decimal(str(por_nombre["Alimentación"]["total_gastos"])) == Decimal("100.00")
        assert por_nombre["Alimentación"]["cantidad_gastos"] == 1
        assert Decimal(str(data["total_general"])) == Decimal("116.00")

    def test_resumen_por_categoria_vacio(self, client_a, empresa_a):
        resp = client_a.get(f"{BASE}gastos/resumen_por_categoria/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resumen_por_categoria"] == []
        assert data["total_general"] == 0

    def test_pendientes_aprobacion(self, client_a, gasto_pendiente_a, empresa_a,
                                    categoria_a, moneda_usd):
        aprobado = Gasto.objects.create(
            id_empresa=empresa_a,
            fecha_gasto=datetime.date(2026, 6, 5),
            descripcion="ya aprobado",
            monto=Decimal("1.00"),
            id_moneda=moneda_usd,
            id_categoria_gasto=categoria_a,
            estado_gasto="APROBADO",
        )
        resp = client_a.get(f"{BASE}gastos/pendientes_aprobacion/")
        assert resp.status_code == 200
        ids = [r["id_gasto"] for r in resp.json()]
        assert ids == [str(gasto_pendiente_a.id_gasto)]
        assert str(aprobado.id_gasto) not in ids


class TestReembolsoGastoActions:
    def test_procesar_pago_actualiza_gasto_aprobado(
        self, client_a, reembolso_pendiente_a, gasto_pendiente_a
    ):
        gasto_pendiente_a.estado_gasto = "APROBADO"
        gasto_pendiente_a.save()
        resp = client_a.post(
            f"{BASE}reembolsos-gasto/{reembolso_pendiente_a.id_reembolso}/procesar_pago/"
        )
        assert resp.status_code == 200
        reembolso_pendiente_a.refresh_from_db()
        gasto_pendiente_a.refresh_from_db()
        assert reembolso_pendiente_a.estado_reembolso == "PAGADO"
        assert gasto_pendiente_a.estado_gasto == "REEMBOLSADO"

    def test_procesar_pago_gasto_no_aprobado_no_lo_toca(
        self, client_a, reembolso_pendiente_a, gasto_pendiente_a
    ):
        # El gasto sigue PENDIENTE_APROBACION: el reembolso se paga pero el
        # estado del gasto no cambia (rama else de la vista).
        resp = client_a.post(
            f"{BASE}reembolsos-gasto/{reembolso_pendiente_a.id_reembolso}/procesar_pago/"
        )
        assert resp.status_code == 200
        gasto_pendiente_a.refresh_from_db()
        assert gasto_pendiente_a.estado_gasto == "PENDIENTE_APROBACION"

    def test_procesar_pago_no_pendiente_400(self, client_a, reembolso_pendiente_a):
        reembolso_pendiente_a.estado_reembolso = "PAGADO"
        reembolso_pendiente_a.save()
        resp = client_a.post(
            f"{BASE}reembolsos-gasto/{reembolso_pendiente_a.id_reembolso}/procesar_pago/"
        )
        assert resp.status_code == 400

    def test_procesar_pago_cross_tenant_404(self, client_b, reembolso_pendiente_a):
        resp = client_b.post(
            f"{BASE}reembolsos-gasto/{reembolso_pendiente_a.id_reembolso}/procesar_pago/"
        )
        assert resp.status_code == 404

    def test_anular_ok(self, client_a, reembolso_pendiente_a):
        resp = client_a.post(
            f"{BASE}reembolsos-gasto/{reembolso_pendiente_a.id_reembolso}/anular/"
        )
        assert resp.status_code == 200
        reembolso_pendiente_a.refresh_from_db()
        assert reembolso_pendiente_a.estado_reembolso == "ANULADO"

    def test_anular_pagado_400(self, client_a, reembolso_pendiente_a):
        reembolso_pendiente_a.estado_reembolso = "PAGADO"
        reembolso_pendiente_a.save()
        resp = client_a.post(
            f"{BASE}reembolsos-gasto/{reembolso_pendiente_a.id_reembolso}/anular/"
        )
        assert resp.status_code == 400

    def test_pendientes_pago(self, client_a, reembolso_pendiente_a, empresa_a,
                              gasto_pendiente_a, moneda_usd, metodo_pago):
        pagado = ReembolsoGasto.objects.create(
            id_empresa=empresa_a,
            id_gasto=gasto_pendiente_a,
            monto_reembolso=Decimal("9.99"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_pago,
            fecha_reembolso=datetime.date(2026, 6, 3),
            estado_reembolso="PAGADO",
        )
        resp = client_a.get(f"{BASE}reembolsos-gasto/pendientes_pago/")
        assert resp.status_code == 200
        ids = [r["id_reembolso"] for r in resp.json()]
        assert ids == [str(reembolso_pendiente_a.id_reembolso)]
        assert str(pagado.id_reembolso) not in ids
