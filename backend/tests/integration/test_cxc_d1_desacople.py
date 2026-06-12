"""
Plan D — Fase D1: desacople del ledger de CxC respecto de crm.Cliente.

Verifica que una CuentaPorCobrar pueda existir SIN crm.Cliente (identificada por
`cliente_externo_id`, p. ej. un partner de Odoo) y siga funcionando en todo el
flujo: providers de cartera, aging, pagos y serializador. Mantiene el camino
clásico (con FK) intacto y cubre el aislamiento multi-tenant.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar
from apps.cuentas_por_cobrar.services_aging import PartidaCartera
from apps.cuentas_por_cobrar.services_cartera_provider import NativeCarteraProvider

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def cliente_crm(empresa_a):
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente CRM Omni",
        rif="J-30543012-5",
    )


def _cxc_externa(empresa, externo_id="odoo-42", nombre="Ferretería Odoo", **kw):
    hoy = date.today()
    defaults = dict(
        empresa=empresa,
        cliente=None,
        cliente_externo_id=externo_id,
        cliente_externo_nombre=nombre,
        monto=Decimal("100.00"),
        fecha_emision=hoy - timedelta(days=10),
        fecha_vencimiento=hoy - timedelta(days=1),  # vencida
        estado="pendiente",
    )
    defaults.update(kw)
    return CuentaPorCobrar.objects.create(**defaults)


class TestModeloDesacoplado:
    def test_cxc_con_fk_resuelve_ref_y_display(self, empresa_a, cliente_crm):
        hoy = date.today()
        cxc = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_crm,
            monto=Decimal("50.00"),
            fecha_emision=hoy,
            fecha_vencimiento=hoy + timedelta(days=30),
        )
        assert cxc.cliente_ref == str(cliente_crm.id_cliente)
        assert cxc.cliente_display == "Cliente CRM Omni"

    def test_cxc_externa_sin_crm(self, empresa_a):
        cxc = _cxc_externa(empresa_a)
        assert cxc.cliente is None
        assert cxc.cliente_ref == "odoo-42"
        assert cxc.cliente_display == "Ferretería Odoo"
        assert "Ferretería Odoo" in str(cxc)

    def test_constraint_exige_alguna_identificacion(self, empresa_a):
        """Una CxC sin FK y sin id externo viola la CheckConstraint."""
        hoy = date.today()
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CuentaPorCobrar.objects.create(
                    empresa=empresa_a,
                    cliente=None,
                    cliente_externo_id="",
                    monto=Decimal("10.00"),
                    fecha_emision=hoy,
                    fecha_vencimiento=hoy,
                )


class TestProvidersConExterna:
    def test_partida_cartera_from_omni_externa(self, empresa_a):
        cxc = _cxc_externa(empresa_a)
        partida = PartidaCartera.from_omni(cxc)
        assert partida.cliente_id == "odoo-42"
        assert partida.cliente_nombre == "Ferretería Odoo"
        assert partida.vencida is True

    def test_native_provider_incluye_externa(self, empresa_a):
        _cxc_externa(empresa_a)
        partidas = NativeCarteraProvider(empresa_a).get_partidas(solo_vencidas=True)
        assert len(partidas) == 1
        assert partidas[0].cliente_id == "odoo-42"

    def test_get_pagos_cliente_por_id_externo(self, empresa_a):
        cxc = _cxc_externa(empresa_a)
        AbonoCxC.objects.create(cuenta_por_cobrar=cxc, monto=Decimal("20.00"))
        pagos = NativeCarteraProvider(empresa_a).get_pagos_cliente("odoo-42")
        assert len(pagos) == 1
        assert pagos[0]["monto"] == "20.00"

    def test_get_pagos_cliente_id_externo_no_uuid_no_falla(self, empresa_a):
        """Un id externo no-UUID no debe romper el filtro del UUIDField (FK)."""
        _cxc_externa(empresa_a, externo_id="PARTNER-NO-UUID")
        pagos = NativeCarteraProvider(empresa_a).get_pagos_cliente("PARTNER-NO-UUID")
        assert pagos == []  # sin abonos, pero sin error


class TestAislamientoMultiTenant:
    def test_externa_respeta_empresa(self, empresa_a, empresa_b):
        _cxc_externa(empresa_a, externo_id="a-1")
        _cxc_externa(empresa_b, externo_id="b-1")
        partidas_a = NativeCarteraProvider(empresa_a).get_partidas()
        ids = {p.cliente_id for p in partidas_a}
        assert ids == {"a-1"}
