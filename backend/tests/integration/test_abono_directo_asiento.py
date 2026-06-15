"""
R-CODE-11 — El abono DIRECTO a una CxC genera su asiento ``PAGO_CXC``.

Hallazgo BAJO de la auditoría integral 2026-06-10: ``registrar_abono`` (abono
directo vía ``/api/cxc/cuentas-por-cobrar/{pk}/abonar/`` y ``/api/cxc/abonos-cxc/``)
NO generaba asiento contable, en asimetría con el pago de cuotas de acuerdo
(``cxc/api/acuerdos.py``), que sí lo hace. Esto violaba R-CODE-11 (todo
movimiento contable genera su asiento en la misma ``@transaction.atomic``).

Aquí se verifica la política uniforme ``generar_asiento_o_fallar``:

- Empresa con contabilidad activa + mapeo ``PAGO_CXC`` → el abono crea su
  asiento (debe == haber == monto), enlazado al ``AbonoCxC``.
- Empresa con contabilidad activa SIN mapeo → ``AbonoError`` y rollback total
  (no persiste abono, estado de la CxC intacto, sin asiento).
- Empresa informal (contabilidad inactiva, sin mapeo) → el abono procede sin
  asiento (R-PROD-3).
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from django.utils import timezone

from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar
from apps.cuentas_por_cobrar.services import AbonoError, registrar_abono

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _today():
    return timezone.now().date()


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


def _asientos_pago_cxc(empresa):
    from apps.contabilidad.models import AsientoContable

    return AsientoContable.objects.filter(
        id_empresa=empresa, nombre_modelo_origen="AbonoCxC"
    )


class TestAbonoDirectoAsiento:
    def test_abono_con_contabilidad_y_mapeo_genera_asiento(
        self, empresa_a, user_a, cxc_a
    ):
        """Camino feliz: el abono crea su asiento PAGO_CXC con debe == haber == monto."""
        from apps.contabilidad.models import DetalleAsiento

        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])
        _mapeo_pago_cxc(empresa_a)

        abono = registrar_abono(cxc=cxc_a, monto=Decimal("400.00"), usuario=user_a)

        asientos = _asientos_pago_cxc(empresa_a)
        assert asientos.count() == 1
        asiento = asientos.get()
        # ``id_documento_origen`` es un UUIDField; ``AbonoCxC`` usa PK entera, así
        # que Django coacciona el pk int a ``UUID(int=pk)`` al guardarlo.
        assert asiento.id_documento_origen.int == abono.pk
        detalles = DetalleAsiento.objects.filter(id_asiento=asiento)
        assert detalles.count() == 2
        total_debe = sum(d.debe for d in detalles)
        total_haber = sum(d.haber for d in detalles)
        assert total_debe == total_haber == Decimal("400.00")

    def test_abono_contabilidad_activa_sin_mapeo_revierte_todo(
        self, empresa_a, user_a, cxc_a
    ):
        """R-CODE-11: sin mapeo y con contabilidad activa, el abono falla y NADA persiste."""
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["contabilidad_activa"])

        with pytest.raises(AbonoError):
            registrar_abono(cxc=cxc_a, monto=Decimal("400.00"), usuario=user_a)

        assert not AbonoCxC.objects.filter(cuenta_por_cobrar=cxc_a).exists()
        cxc_a.refresh_from_db()
        assert cxc_a.estado == "pendiente"
        assert not _asientos_pago_cxc(empresa_a).exists()

    def test_abono_empresa_informal_procede_sin_asiento(self, empresa_a, user_a, cxc_a):
        """R-PROD-3: empresa sin contabilidad activa ni mapeo → abono OK, sin asiento."""
        assert empresa_a.contabilidad_activa is False  # default

        abono = registrar_abono(cxc=cxc_a, monto=Decimal("400.00"), usuario=user_a)

        assert AbonoCxC.objects.filter(pk=abono.pk).exists()
        cxc_a.refresh_from_db()
        assert cxc_a.estado == "parcial"
        assert not _asientos_pago_cxc(empresa_a).exists()
