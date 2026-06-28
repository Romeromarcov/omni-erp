"""
Tests de integración — Módulo Gastos (T08/T09).

Cubre apps/gastos/services.py:
  - aprobar_gasto()  — respaldo documental, asientos GASTO/GASTO_IVA (R-CODE-11),
                       marca sin_respaldo, enforcement de período fiscal.
  - rechazar_gasto() — transición a RECHAZADO.

Espejo de tests/integration/test_m6_compras.py.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.gastos.models import CategoriaGasto, Gasto
from apps.gastos.services import GastoError, aprobar_gasto, rechazar_gasto

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Helpers contables ──────────────────────────────────────────────────────────


def _crear_cuenta(empresa, codigo, nombre, tipo="GASTO", naturaleza="DEUDORA"):
    from apps.contabilidad.models import PlanCuentas

    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=nombre,
        tipo_cuenta=tipo,
        naturaleza=naturaleza,
        nivel=1,
    )


def _crear_mapeo(empresa, tipo_asiento, debe, haber):
    from apps.contabilidad.models import MapeoContable

    return MapeoContable.objects.create(
        id_empresa=empresa,
        tipo_asiento=tipo_asiento,
        cuenta_debe=debe,
        cuenta_haber=haber,
        descripcion_plantilla=f"Asiento {tipo_asiento}",
        activo=True,
    )


def _mapeos_gasto(empresa):
    """Configura los mapeos GASTO y GASTO_IVA de la empresa."""
    gasto_cta = _crear_cuenta(empresa, "5201", "Gasto Operativo", "GASTO", "DEUDORA")
    iva_cta = _crear_cuenta(empresa, "1108", "IVA Crédito Fiscal", "ACTIVO", "DEUDORA")
    cxp_cta = _crear_cuenta(empresa, "2101", "CxP Gastos", "PASIVO", "ACREEDORA")
    _crear_mapeo(empresa, "GASTO", gasto_cta, cxp_cta)
    _crear_mapeo(empresa, "GASTO_IVA", iva_cta, cxp_cta)
    return gasto_cta, iva_cta, cxp_cta


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def categoria(db, empresa_a):
    return CategoriaGasto.objects.create(
        id_empresa=empresa_a,
        nombre_categoria="Servicios Generales",
        requiere_factura=False,
    )


@pytest.fixture
def categoria_con_factura(db, empresa_a):
    return CategoriaGasto.objects.create(
        id_empresa=empresa_a,
        nombre_categoria="Servicios Profesionales",
        requiere_factura=True,
    )


def _crear_gasto(empresa, categoria, moneda, monto="100.00", iva="0", tiene_factura=False):
    return Gasto.objects.create(
        id_empresa=empresa,
        fecha_gasto=timezone.now().date(),
        descripcion="Gasto de prueba",
        monto=Decimal(monto),
        monto_iva=Decimal(iva),
        id_moneda=moneda,
        id_categoria_gasto=categoria,
        tiene_factura=tiene_factura,
        estado_gasto="PENDIENTE_APROBACION",
    )


# ── TestAprobarGasto: respaldo documental (T08/T09) ────────────────────────────


class TestRespaldoDocumental:
    def test_sin_factura_se_aprueba_y_marca_sin_respaldo(self, empresa_a, categoria, moneda_usd, user_a):
        """T09: gasto sin factura (categoría no la exige) → aprobado + sin_respaldo."""
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, tiene_factura=False)
        resultado = aprobar_gasto(gasto, usuario=user_a)
        g = resultado["gasto"]
        assert g.sin_respaldo is True
        assert g.estado_gasto == "APROBADO"  # sin mapeo no contabiliza

    def test_con_factura_no_marca_sin_respaldo(self, empresa_a, categoria, moneda_usd, user_a):
        """T08: gasto con factura → aprobado, con respaldo."""
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, tiene_factura=True)
        resultado = aprobar_gasto(gasto, usuario=user_a)
        assert resultado["gasto"].sin_respaldo is False

    def test_categoria_exige_factura_y_no_la_tiene_bloquea(
        self, empresa_a, categoria_con_factura, moneda_usd, user_a
    ):
        gasto = _crear_gasto(empresa_a, categoria_con_factura, moneda_usd, tiene_factura=False)
        with pytest.raises(GastoError, match="exige factura"):
            aprobar_gasto(gasto, usuario=user_a)
        gasto.refresh_from_db()
        assert gasto.estado_gasto == "PENDIENTE_APROBACION"  # no cambió

    def test_categoria_exige_factura_y_la_tiene_aprueba(
        self, empresa_a, categoria_con_factura, moneda_usd, user_a
    ):
        gasto = _crear_gasto(empresa_a, categoria_con_factura, moneda_usd, tiene_factura=True)
        resultado = aprobar_gasto(gasto, usuario=user_a)
        assert resultado["gasto"].estado_gasto == "APROBADO"


# ── TestAprobarGasto: asientos contables (R-CODE-11) ───────────────────────────


class TestAsientosGasto:
    def test_genera_asiento_gasto_sin_iva(self, empresa_a, categoria, moneda_usd, user_a):
        _mapeos_gasto(empresa_a)
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, monto="250.00", iva="0", tiene_factura=True)
        resultado = aprobar_gasto(gasto, usuario=user_a)
        asiento = resultado["asiento"]
        assert asiento is not None
        assert asiento.nombre_modelo_origen == "Gasto"
        assert asiento.id_usuario_registro == user_a
        assert resultado["asiento_iva"] is None
        assert resultado["gasto"].estado_gasto == "CONTABILIZADO"

    def test_asiento_gasto_cuadra_debe_haber(self, empresa_a, categoria, moneda_usd, user_a):
        _mapeos_gasto(empresa_a)
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, monto="300.00", tiene_factura=True)
        asiento = aprobar_gasto(gasto, usuario=user_a)["asiento"]
        detalles = list(asiento.detalleasiento_set.all())
        total_debe = sum(d.debe for d in detalles)
        total_haber = sum(d.haber for d in detalles)
        assert total_debe == total_haber == Decimal("300.00")

    def test_genera_asiento_iva_separado(self, empresa_a, categoria, moneda_usd, user_a):
        """T08: gasto con IVA → asiento base (GASTO) + asiento IVA (GASTO_IVA)."""
        _mapeos_gasto(empresa_a)
        # monto total 116, IVA 16 → base 100
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, monto="116.00", iva="16.00", tiene_factura=True)
        resultado = aprobar_gasto(gasto, usuario=user_a)
        asiento, asiento_iva = resultado["asiento"], resultado["asiento_iva"]
        assert asiento is not None and asiento_iva is not None
        base_debe = sum(d.debe for d in asiento.detalleasiento_set.all())
        iva_debe = sum(d.debe for d in asiento_iva.detalleasiento_set.all())
        assert base_debe == Decimal("100.00")
        assert iva_debe == Decimal("16.00")

    def test_sin_mapeo_no_falla(self, empresa_a, categoria, moneda_usd, user_a):
        """Empresa informal sin mapeo (R-PROD-3) → aprueba sin asiento."""
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, tiene_factura=True)
        resultado = aprobar_gasto(gasto, usuario=user_a)
        assert resultado["asiento"] is None
        assert resultado["gasto"].estado_gasto == "APROBADO"

    def test_gasto_100_pct_iva_solo_asiento_iva(self, empresa_a, categoria, moneda_usd, user_a):
        """monto == iva → base 0 → solo asiento GASTO_IVA (simétrico a iva=0)."""
        _mapeos_gasto(empresa_a)
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, monto="16.00", iva="16.00", tiene_factura=True)
        resultado = aprobar_gasto(gasto, usuario=user_a)
        assert resultado["asiento"] is None  # no hay base
        assert resultado["asiento_iva"] is not None
        iva_debe = sum(d.debe for d in resultado["asiento_iva"].detalleasiento_set.all())
        assert iva_debe == Decimal("16.00")
        assert resultado["gasto"].estado_gasto == "CONTABILIZADO"  # aún contabiliza

    def test_iva_excede_monto_lanza_error(self, empresa_a, categoria, moneda_usd, user_a):
        """IVA > monto → base negativa → error."""
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, monto="10.00", iva="16.00", tiene_factura=True)
        with pytest.raises(GastoError, match="no puede ser negativa"):
            aprobar_gasto(gasto, usuario=user_a)

    def test_monto_cero_lanza_error(self, empresa_a, categoria, moneda_usd, user_a):
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, monto="0", iva="0", tiene_factura=True)
        with pytest.raises(GastoError, match="mayor a cero"):
            aprobar_gasto(gasto, usuario=user_a)


# ── TestDetallesReconciliacion ─────────────────────────────────────────────────


class TestDetallesReconciliacion:
    def _cuenta(self, empresa, codigo="5401"):
        from apps.contabilidad.models import PlanCuentas

        return PlanCuentas.objects.create(
            id_empresa=empresa, codigo_cuenta=codigo, nombre_cuenta="Gasto Línea",
            tipo_cuenta="GASTO", naturaleza="DEUDORA", nivel=1,
        )

    def test_detalles_que_reconcilian_aprueban(self, empresa_a, categoria, moneda_usd, user_a):
        from apps.gastos.models import DetalleGasto

        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, monto="100.00", tiene_factura=True)
        cta = self._cuenta(empresa_a)
        DetalleGasto.objects.create(id_gasto=gasto, id_cuenta_contable=cta, monto=Decimal("60.00"))
        DetalleGasto.objects.create(id_gasto=gasto, id_cuenta_contable=cta, monto=Decimal("40.00"))
        resultado = aprobar_gasto(gasto, usuario=user_a)
        assert resultado["gasto"].estado_gasto == "APROBADO"  # sin mapeo, pero reconcilia

    def test_detalles_que_no_reconcilian_bloquean(self, empresa_a, categoria, moneda_usd, user_a):
        from apps.gastos.models import DetalleGasto

        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, monto="100.00", tiene_factura=True)
        cta = self._cuenta(empresa_a, "5402")
        DetalleGasto.objects.create(id_gasto=gasto, id_cuenta_contable=cta, monto=Decimal("60.00"))
        with pytest.raises(GastoError, match="no reconcilian"):
            aprobar_gasto(gasto, usuario=user_a)


# ── TestEstadoYRechazo ─────────────────────────────────────────────────────────


class TestEstadoYRechazo:
    def test_no_se_aprueba_dos_veces(self, empresa_a, categoria, moneda_usd, user_a):
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, tiene_factura=True)
        aprobar_gasto(gasto, usuario=user_a)
        with pytest.raises(GastoError, match="PENDIENTE_APROBACION"):
            aprobar_gasto(gasto, usuario=user_a)

    def test_rechazar_pendiente_con_motivo(self, empresa_a, categoria, moneda_usd, user_a):
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd)
        resultado = rechazar_gasto(gasto, usuario=user_a, motivo="Fuera de presupuesto")
        assert resultado["gasto"].estado_gasto == "RECHAZADO"

    def test_rechazar_pendiente_sin_motivo(self, empresa_a, categoria, moneda_usd, user_a):
        """Cubre la rama de log con motivo vacío (motivo or '—')."""
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd)
        resultado = rechazar_gasto(gasto, usuario=user_a)
        assert resultado["gasto"].estado_gasto == "RECHAZADO"

    def test_no_rechaza_aprobado(self, empresa_a, categoria, moneda_usd, user_a):
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, tiene_factura=True)
        aprobar_gasto(gasto, usuario=user_a)
        with pytest.raises(GastoError, match="PENDIENTE_APROBACION"):
            rechazar_gasto(gasto, usuario=user_a)

    def test_no_rechaza_contabilizado(self, empresa_a, categoria, moneda_usd, user_a):
        """El estado más peligroso: rechazar un gasto ya contabilizado se bloquea."""
        _mapeos_gasto(empresa_a)
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, monto="50.00", tiene_factura=True)
        aprobar_gasto(gasto, usuario=user_a)
        gasto.refresh_from_db()
        assert gasto.estado_gasto == "CONTABILIZADO"
        with pytest.raises(GastoError, match="PENDIENTE_APROBACION"):
            rechazar_gasto(gasto, usuario=user_a)


# ── TestStr: cobertura de __str__ (ratchet) ────────────────────────────────────


class TestStr:
    def test_str_modelos(self, empresa_a, categoria, moneda_usd):
        from apps.gastos.models import DetalleGasto, ReembolsoGasto

        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, monto="12.00")
        assert "Servicios Generales" in str(categoria)
        assert "12.00" in str(gasto)
        from apps.contabilidad.models import PlanCuentas

        cta = PlanCuentas.objects.create(
            id_empresa=empresa_a, codigo_cuenta="5999", nombre_cuenta="X",
            tipo_cuenta="GASTO", naturaleza="DEUDORA", nivel=1,
        )
        det = DetalleGasto.objects.create(id_gasto=gasto, id_cuenta_contable=cta, monto=Decimal("12.00"))
        assert "12.00" in str(det)
        from apps.finanzas.models import MetodoPago

        mp = MetodoPago.objects.create(empresa=empresa_a, nombre_metodo="Efx", tipo_metodo="EFECTIVO")
        reemb = ReembolsoGasto.objects.create(
            id_empresa=empresa_a, id_gasto=gasto, monto_reembolso=Decimal("12.00"),
            id_moneda=moneda_usd, id_metodo_pago=mp, fecha_reembolso=timezone.now().date(),
            estado_reembolso="PENDIENTE",
        )
        assert "PENDIENTE" in str(reemb)


# ── TestPeriodoFiscal ──────────────────────────────────────────────────────────


class TestPeriodoFiscal:
    def test_periodo_cerrado_bloquea(self, empresa_a, categoria, moneda_usd, user_a, monkeypatch):
        from apps.fiscal import services as fiscal_services

        def _cerrado(empresa, fecha):
            raise fiscal_services.PeriodoCerradoError("Período cerrado para esa fecha.")

        monkeypatch.setattr(fiscal_services, "validar_periodo_abierto", _cerrado)
        gasto = _crear_gasto(empresa_a, categoria, moneda_usd, tiene_factura=True)
        with pytest.raises(GastoError, match="cerrado"):
            aprobar_gasto(gasto, usuario=user_a)
