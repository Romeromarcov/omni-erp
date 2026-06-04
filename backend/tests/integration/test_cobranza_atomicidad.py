"""
TEST-5 — Atomicidad del flujo de cobranza (R-CODE-11 + @transaction.atomic).

El endpoint `cxc` acuerdos `registrar-pago` (POST) registra el pago de una cuota,
crea un `finanzas.Pago`, actualiza la cuota/acuerdo y genera el asiento `PAGO_CXC`
en la MISMA transacción. Si la empresa exige contabilidad (`contabilidad_activa=True`)
y falta el mapeo, `generar_asiento_o_fallar` lanza `AsientoError`; el endpoint hace
`transaction.set_rollback(True)` y responde 422.

Hasta ahora este flujo **no tenía test**. Aquí verificamos la invariante crítica:
ante el 422, **NADA persiste** (ni el Pago, ni la cuota tocada, ni el acuerdo
auto-completado); y el camino feliz con mapeo sí persiste todo.
"""

from decimal import Decimal

import pytest

from django.utils import timezone
from rest_framework.test import APIClient

from apps.cxc.models import AcuerdoPago, CuotaAcuerdo

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _cuenta(empresa, codigo, nombre, tipo="ACTIVO", naturaleza="DEUDORA"):
    from apps.contabilidad.models import PlanCuentas

    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=nombre,
        tipo_cuenta=tipo,
        naturaleza=naturaleza,
        nivel=1,
    )


def _mapeo_pago_cxc(empresa):
    from apps.contabilidad.models import MapeoContable

    debe = _cuenta(empresa, "1102", "Banco CXC", "ACTIVO", "DEUDORA")
    haber = _cuenta(empresa, "1103", "CxC Clientes", "ACTIVO", "ACREEDORA")
    return MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento="PAGO_CXC",
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla="Asiento PAGO_CXC",
        activo=True,
    )


@pytest.fixture
def empresa_contable(empresa_a):
    empresa_a.contabilidad_activa = True
    empresa_a.save(update_fields=["contabilidad_activa"])
    return empresa_a


@pytest.fixture
def acuerdo_con_cuota(db, empresa_a):
    """Acuerdo de pago con una única cuota pendiente de 100."""
    acuerdo = AcuerdoPago.objects.create(
        empresa=empresa_a,
        cliente_id="CLI-COB-001",
        cliente_nombre="Cliente Cobranza",
        monto_total=Decimal("100.00"),
        periodicidad="unico",
        fecha_inicio=timezone.now().date(),
        moneda_codigo="USD",
    )
    cuota = CuotaAcuerdo.objects.create(
        acuerdo=acuerdo,
        numero_cuota=1,
        fecha_vencimiento=timezone.now().date(),
        monto=Decimal("100.00"),
        estado="pendiente",
    )
    return acuerdo, cuota


def _url(acuerdo):
    return f"/api/cobranza/acuerdos/{acuerdo.pk}/registrar-pago/"


def _payload(cuota, moneda, metodo, monto="100.00"):
    return {
        "cuota_id": str(cuota.pk),
        "monto": monto,
        "moneda_id": str(moneda.pk),
        "metodo_pago_id": str(metodo.pk),
    }


class TestRegistrarPagoAtomico:
    def test_pago_revierte_todo_si_falta_mapeo_y_contabilidad_activa(
        self, empresa_contable, acuerdo_con_cuota, user_a, moneda_usd, metodo_efectivo
    ):
        """contabilidad_activa + sin mapeo PAGO_CXC → 422 y rollback total."""
        from apps.finanzas.models import Pago

        acuerdo, cuota = acuerdo_con_cuota
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.post(
            _url(acuerdo), _payload(cuota, moneda_usd, metodo_efectivo), format="json"
        )

        assert resp.status_code == 422, f"Esperado 422, fue {resp.status_code}: {resp.data}"
        assert resp.data.get("code") == "asiento_contable_requerido"

        # Rollback: ni Pago, ni mutación de cuota, ni auto-completar acuerdo.
        assert not Pago.objects.filter(id_empresa=empresa_contable).exists(), (
            "ATOMICIDAD: quedó un finanzas.Pago tras el rollback del asiento."
        )
        cuota.refresh_from_db()
        assert cuota.estado == "pendiente", "ATOMICIDAD: la cuota cambió de estado pese al rollback."
        assert cuota.monto_pagado == Decimal("0"), "ATOMICIDAD: monto_pagado se actualizó pese al rollback."
        assert cuota.pago_id is None, "ATOMICIDAD: la cuota quedó enlazada a un Pago tras el rollback."
        acuerdo.refresh_from_db()
        assert acuerdo.estado == "vigente", "ATOMICIDAD: el acuerdo se auto-completó pese al rollback."

    def test_pago_exitoso_con_mapeo_persiste_todo(
        self, empresa_contable, acuerdo_con_cuota, user_a, moneda_usd, metodo_efectivo
    ):
        """Con mapeo PAGO_CXC: 200, se crea el Pago y la cuota/acuerdo se completan."""
        from apps.finanzas.models import Pago

        _mapeo_pago_cxc(empresa_contable)
        acuerdo, cuota = acuerdo_con_cuota
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.post(
            _url(acuerdo), _payload(cuota, moneda_usd, metodo_efectivo), format="json"
        )

        assert resp.status_code == 200, f"Esperado 200, fue {resp.status_code}: {resp.data}"
        assert Pago.objects.filter(id_empresa=empresa_contable).count() == 1
        cuota.refresh_from_db()
        assert cuota.estado == "pagado"
        assert cuota.monto_pagado == Decimal("100.00")
        acuerdo.refresh_from_db()
        assert acuerdo.estado == "cumplido", "La única cuota quedó pagada; el acuerdo debe auto-completarse."
