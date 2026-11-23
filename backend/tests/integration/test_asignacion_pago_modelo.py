"""Tests integrales de PR-10 (Ola A1): ``AsignacionPago``, ``Pago.id_contacto``, RLS y backfill.

Cubre contra PostgreSQL real:
1. CheckConstraints en BD (``IntegrityError`` dentro de ``transaction.atomic()``).
2. Creación y ``full_clean()``/``save()`` válidos para los 4 ``tipo_documento``.
3. Aislamiento cross-tenant en ``AsignacionPago`` y ``Pago`` (fail-closed).
4. RLS en PostgreSQL (``pg_policies``, ``FORCE ROW LEVEL SECURITY`` y aislamiento con rol no-privilegiado).
5. ``Pago`` anticipo (``id_documento=None``) vía API + ``registrar_efectos_pago``, auto-derivación
   de ``id_contacto`` y rechazo anti-IDOR en ``PagoSerializer`` / ``PagoViewSet``.
6. Migración reversible ``0044_backfill_pago_id_contacto`` (forward, idempotencia y protección cross-tenant).
"""

from datetime import date, timedelta
from decimal import Decimal
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import ProgrammingError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.compras.models import FacturaCompra, OrdenCompra
from apps.core import rls
from apps.core.models import Contacto, Empresa
from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.models import AbonoCxC, CuentaPorCobrar
from apps.cuentas_por_pagar.models import AbonoCxP, CuentaPorPagar
from apps.finanzas.models import AsignacionPago, Pago, TransaccionFinanciera
from apps.finanzas.serializers import PagoSerializer
from apps.finanzas.services import registrar_efectos_pago
from apps.proveedores.models import Proveedor
from apps.ventas.models import FacturaFiscal, NotaVenta, Pedido

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Helpers / Fixtures locales ───────────────────────────────────────────────


def _hoy() -> date:
    return timezone.now().date()


@pytest.fixture
def contacto_cliente_a(db, empresa_a):
    return Contacto.objects.create(
        id_empresa=empresa_a,
        tipo_persona="JURIDICA",
        nombre="Cliente Alpha C.A.",
        rif="J-10000001-1",
        es_cliente=True,
    )


@pytest.fixture
def contacto_proveedor_a(db, empresa_a):
    return Contacto.objects.create(
        id_empresa=empresa_a,
        tipo_persona="JURIDICA",
        nombre="Proveedor Alpha S.A.",
        rif="J-20000001-2",
        es_proveedor=True,
    )


@pytest.fixture
def contacto_b(db, empresa_b):
    return Contacto.objects.create(
        id_empresa=empresa_b,
        tipo_persona="JURIDICA",
        nombre="Contacto Beta C.A.",
        rif="J-30000001-3",
        es_cliente=True,
        es_proveedor=True,
    )


@pytest.fixture
def cliente_a(db, empresa_a, contacto_cliente_a):
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Alpha C.A.",
        rif="J-10000001-1",
        contacto=contacto_cliente_a,
    )


@pytest.fixture
def cliente_b(db, empresa_b, contacto_b):
    return Cliente.objects.create(
        id_empresa=empresa_b,
        razon_social="Cliente Beta C.A.",
        rif="J-30000001-3",
        contacto=contacto_b,
    )


@pytest.fixture
def proveedor_a(db, empresa_a, contacto_proveedor_a):
    return Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Proveedor Alpha S.A.",
        rif="J-20000001-2",
        contacto=contacto_proveedor_a,
    )


@pytest.fixture
def proveedor_b(db, empresa_b, contacto_b):
    return Proveedor.objects.create(
        id_empresa=empresa_b,
        razon_social="Proveedor Beta S.A.",
        rif="J-40000001-4",
        contacto=contacto_b,
    )


@pytest.fixture
def cxc_a(db, empresa_a, cliente_a):
    return CuentaPorCobrar.objects.create(
        empresa=empresa_a,
        cliente=cliente_a,
        monto=Decimal("250.00"),
        fecha_emision=_hoy(),
        fecha_vencimiento=_hoy() + timedelta(days=15),
        estado="pendiente",
    )


@pytest.fixture
def factura_venta_a(db, empresa_a, cliente_a, moneda_usd):
    return FacturaFiscal.objects.create(
        id_empresa=empresa_a,
        id_cliente=cliente_a,
        numero_control="00-1001",
        numero_factura="FV-1001",
        fecha_emision=_hoy(),
        id_moneda=moneda_usd,
        base_imponible=Decimal("100.0000"),
        monto_iva=Decimal("16.0000"),
        monto_total=Decimal("116.0000"),
        estado="EMITIDA",
    )


@pytest.fixture
def factura_compra_a(db, empresa_a, proveedor_a):
    oc = OrdenCompra.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor_a,
        numero_orden="OC-1001",
        fecha_orden=_hoy(),
        estado="APROBADA",
    )
    return FacturaCompra.objects.create(
        id_empresa=empresa_a,
        id_orden_compra=oc,
        numero_factura="FC-1001",
        fecha_emision=_hoy(),
        monto_total=Decimal("300.0000"),
    )


@pytest.fixture
def cxp_a(db, empresa_a, proveedor_a, factura_compra_a):
    return CuentaPorPagar.objects.create(
        id_empresa=empresa_a,
        id_proveedor=proveedor_a,
        id_factura_compra=factura_compra_a,
        monto_total=Decimal("300.0000"),
        monto_pendiente=Decimal("300.0000"),
        fecha_emision=_hoy(),
        fecha_vencimiento=_hoy() + timedelta(days=30),
        estado="PENDIENTE",
    )


@pytest.fixture
def pago_ingreso_a(db, empresa_a, contacto_cliente_a, moneda_usd, metodo_efectivo):
    return Pago.objects.create(
        id_empresa=empresa_a,
        id_contacto=contacto_cliente_a,
        tipo_operacion="INGRESO",
        tipo_documento="ANTICIPO",
        id_documento=None,
        fecha_pago=timezone.now(),
        monto=Decimal("500.0000"),
        id_moneda=moneda_usd,
        id_metodo_pago=metodo_efectivo,
    )


@pytest.fixture
def pago_egreso_a(db, empresa_a, contacto_proveedor_a, moneda_usd, metodo_efectivo):
    return Pago.objects.create(
        id_empresa=empresa_a,
        id_contacto=contacto_proveedor_a,
        tipo_operacion="EGRESO",
        tipo_documento="CONCILIACION_MULTIPLE",
        id_documento=None,
        fecha_pago=timezone.now(),
        monto=Decimal("400.0000"),
        id_moneda=moneda_usd,
        id_metodo_pago=metodo_efectivo,
    )


# ── 1. Constraints en BD (IntegrityError) ────────────────────────────────────


class TestAsignacionPagoConstraintsBD:
    @pytest.mark.parametrize(
        "campo,valor",
        [
            ("monto_asignado_pago", Decimal("0")),
            ("monto_asignado_pago", Decimal("-10.0000")),
            ("monto_asignado_documento", Decimal("0")),
            ("monto_asignado_documento", Decimal("-5.0000")),
            ("tasa_aplicada", Decimal("0")),
            ("tasa_aplicada", Decimal("-1.00000000")),
        ],
    )
    def test_check_constraints_montos_y_tasa_positivos(
        self, empresa_a, contacto_cliente_a, pago_ingreso_a, cxc_a, moneda_usd, campo, valor
    ):
        kwargs = {
            "id_empresa": empresa_a,
            "id_contacto": contacto_cliente_a,
            "id_pago": pago_ingreso_a,
            "tipo_documento": "CUENTA_POR_COBRAR",
            "id_cxc": cxc_a,
            "monto_asignado_pago": Decimal("50.0000"),
            "monto_asignado_documento": Decimal("50.0000"),
            "id_moneda_documento": moneda_usd,
            "tasa_aplicada": Decimal("1.00000000"),
        }
        kwargs[campo] = valor
        with pytest.raises(IntegrityError), transaction.atomic():
            AsignacionPago.objects.create(**kwargs)

    def test_check_constraint_cero_fks_pobladas(self, empresa_a, contacto_cliente_a, pago_ingreso_a, moneda_usd):
        with pytest.raises(IntegrityError, match="asignacion_pago_fk_coherente"), transaction.atomic():
            AsignacionPago.objects.bulk_create(
                [
                    AsignacionPago(
                        id_empresa=empresa_a,
                        id_contacto=contacto_cliente_a,
                        id_pago=pago_ingreso_a,
                        tipo_documento="CUENTA_POR_COBRAR",
                        id_documento="1",
                        monto_asignado_pago=Decimal("10.0000"),
                        monto_asignado_documento=Decimal("10.0000"),
                        id_moneda_documento=moneda_usd,
                    )
                ]
            )

    def test_check_constraint_dos_fks_pobladas(
        self, empresa_a, contacto_cliente_a, pago_ingreso_a, cxc_a, factura_venta_a, moneda_usd
    ):
        with pytest.raises(IntegrityError, match="asignacion_pago_fk_coherente"), transaction.atomic():
            AsignacionPago.objects.bulk_create(
                [
                    AsignacionPago(
                        id_empresa=empresa_a,
                        id_contacto=contacto_cliente_a,
                        id_pago=pago_ingreso_a,
                        tipo_documento="CUENTA_POR_COBRAR",
                        id_documento=str(cxc_a.pk),
                        id_cxc=cxc_a,
                        id_factura_venta=factura_venta_a,
                        monto_asignado_pago=Decimal("10.0000"),
                        monto_asignado_documento=Decimal("10.0000"),
                        id_moneda_documento=moneda_usd,
                    )
                ]
            )

    def test_check_constraint_fk_no_coincide_con_tipo_documento(
        self, empresa_a, contacto_cliente_a, pago_ingreso_a, cxc_a, moneda_usd
    ):
        with pytest.raises(IntegrityError, match="asignacion_pago_fk_coherente"), transaction.atomic():
            AsignacionPago.objects.bulk_create(
                [
                    AsignacionPago(
                        id_empresa=empresa_a,
                        id_contacto=contacto_cliente_a,
                        id_pago=pago_ingreso_a,
                        tipo_documento="FACTURA_VENTA",
                        id_documento=str(cxc_a.pk),
                        id_cxc=cxc_a,
                        monto_asignado_pago=Decimal("10.0000"),
                        monto_asignado_documento=Decimal("10.0000"),
                        id_moneda_documento=moneda_usd,
                    )
                ]
            )


# ── 2. Creaciones válidas para los 4 tipo_documento y ciclo clean/save ────────


class TestAsignacionPagoCreacionesValidas:
    def test_cuatro_tipos_documento_y_sincronizacion_id_documento(
        self,
        empresa_a,
        contacto_cliente_a,
        contacto_proveedor_a,
        pago_ingreso_a,
        pago_egreso_a,
        cxc_a,
        cxp_a,
        factura_venta_a,
        factura_compra_a,
        moneda_usd,
        user_a,
    ):
        abono_cxc = AbonoCxC.objects.create(cuenta_por_cobrar=cxc_a, monto=Decimal("100.00"), usuario=user_a)
        abono_cxp = AbonoCxP.objects.create(cuenta_por_pagar=cxp_a, monto=Decimal("150.0000"), usuario=user_a)

        asig_cxc = AsignacionPago(
            id_empresa=empresa_a,
            id_contacto=contacto_cliente_a,
            id_pago=pago_ingreso_a,
            tipo_documento="CUENTA_POR_COBRAR",
            id_cxc=cxc_a,
            id_abono_cxc=abono_cxc,
            monto_asignado_pago=Decimal("100.0000"),
            monto_asignado_documento=Decimal("100.0000"),
            id_moneda_documento=moneda_usd,
            id_usuario_registro=user_a,
        )
        asig_cxc.full_clean()
        asig_cxc.save()
        assert asig_cxc.id_documento == str(cxc_a.pk)
        assert isinstance(cxc_a.pk, int)
        assert abono_cxc.asignacion_pago == asig_cxc
        assert f"CUENTA_POR_COBRAR:{cxc_a.pk}" in str(asig_cxc)

        asig_fv = AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_cliente_a,
            id_pago=pago_ingreso_a,
            tipo_documento="FACTURA_VENTA",
            id_documento="valor-temporal-sobrescrito",
            id_factura_venta=factura_venta_a,
            monto_asignado_pago=Decimal("116.0000"),
            monto_asignado_documento=Decimal("116.0000"),
            id_moneda_documento=moneda_usd,
        )
        asig_fv.refresh_from_db()
        assert asig_fv.id_documento == str(factura_venta_a.pk)

        asig_cxp = AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_proveedor_a,
            id_pago=pago_egreso_a,
            tipo_documento="CUENTA_POR_PAGAR",
            id_cxp=cxp_a,
            id_abono_cxp=abono_cxp,
            monto_asignado_pago=Decimal("150.0000"),
            monto_asignado_documento=Decimal("150.0000"),
            id_moneda_documento=moneda_usd,
        )
        assert asig_cxp.id_documento == str(cxp_a.pk)
        assert abono_cxp.asignacion_pago == asig_cxp

        asig_fc = AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_proveedor_a,
            id_pago=pago_egreso_a,
            tipo_documento="FACTURA_COMPRA",
            id_factura_compra=factura_compra_a,
            monto_asignado_pago=Decimal("200.0000"),
            monto_asignado_documento=Decimal("200.0000"),
            id_moneda_documento=moneda_usd,
        )
        assert asig_fc.id_documento == str(factura_compra_a.pk)

        # soft_delete con update_fields=["activo"] debe funcionar limpio
        asig_fc.soft_delete()
        asig_fc.refresh_from_db()
        assert asig_fc.activo is False

    def test_update_fields_sincroniza_id_documento_en_bd(
        self, empresa_a, contacto_cliente_a, pago_ingreso_a, cxc_a, cliente_a, factura_venta_a, moneda_usd
    ):
        """Regresión [B-1]: save(update_fields=...) persiste id_documento sincronizado en PostgreSQL."""
        cxc2 = CuentaPorCobrar.objects.create(
            empresa=empresa_a,
            cliente=cliente_a,
            monto=Decimal("90.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy() + timedelta(days=10),
            estado="pendiente",
        )
        asig = AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_cliente_a,
            id_pago=pago_ingreso_a,
            tipo_documento="CUENTA_POR_COBRAR",
            id_cxc=cxc_a,
            monto_asignado_pago=Decimal("40.0000"),
            monto_asignado_documento=Decimal("40.0000"),
            id_moneda_documento=moneda_usd,
        )
        assert asig.id_documento == str(cxc_a.pk)

        # Actualizar solo id_cxc con update_fields sin incluir id_documento
        asig.id_cxc = cxc2
        asig.save(update_fields=["id_cxc"])
        asig.refresh_from_db()
        assert asig.id_cxc_id == cxc2.pk
        assert asig.id_documento == str(cxc2.pk)

        # Cambiar tipo_documento + FK con update_fields como tupla
        asig.tipo_documento = "FACTURA_VENTA"
        asig.id_cxc = None
        asig.id_factura_venta = factura_venta_a
        asig.save(update_fields=("tipo_documento", "id_cxc", "id_factura_venta"))
        asig.refresh_from_db()
        assert asig.id_documento == str(factura_venta_a.pk)

    def test_validacion_modelo_rechaza_tipo_invalido_o_fk_incoherente(
        self, empresa_a, contacto_cliente_a, pago_ingreso_a, cxc_a, factura_venta_a, moneda_usd
    ):
        with pytest.raises(ValidationError):
            AsignacionPago(
                id_empresa=empresa_a,
                id_contacto=contacto_cliente_a,
                id_pago=pago_ingreso_a,
                tipo_documento="INVALIDO",
                id_cxc=cxc_a,
                monto_asignado_pago=Decimal("10.0000"),
                monto_asignado_documento=Decimal("10.0000"),
                id_moneda_documento=moneda_usd,
            ).full_clean()

        with pytest.raises(ValidationError):
            AsignacionPago.objects.create(
                id_empresa=empresa_a,
                id_contacto=contacto_cliente_a,
                id_pago=pago_ingreso_a,
                tipo_documento="FACTURA_VENTA",
                id_cxc=cxc_a,
                id_factura_venta=factura_venta_a,
                monto_asignado_pago=Decimal("10.0000"),
                monto_asignado_documento=Decimal("10.0000"),
                id_moneda_documento=moneda_usd,
            )


# ── 3. Validación cross-tenant en AsignacionPago y Pago ──────────────────────


class TestAislamientoCrossTenantModelos:
    def test_asignacion_rechaza_pago_y_contacto_de_otra_empresa(
        self, empresa_a, empresa_b, contacto_cliente_a, contacto_b, pago_ingreso_a, cxc_a, moneda_usd, metodo_efectivo
    ):
        pago_b = Pago.objects.create(
            id_empresa=empresa_b,
            id_contacto=contacto_b,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("100.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )

        # Pago de empresa_b en asignación de empresa_a
        with pytest.raises(ValidationError) as exc_pago:
            AsignacionPago.objects.create(
                id_empresa=empresa_a,
                id_contacto=contacto_cliente_a,
                id_pago=pago_b,
                tipo_documento="CUENTA_POR_COBRAR",
                id_cxc=cxc_a,
                monto_asignado_pago=Decimal("10.0000"),
                monto_asignado_documento=Decimal("10.0000"),
                id_moneda_documento=moneda_usd,
            )
        assert "id_pago" in exc_pago.value.message_dict

        # Contacto de empresa_b en asignación de empresa_a
        with pytest.raises(ValidationError) as exc_contacto:
            AsignacionPago.objects.create(
                id_empresa=empresa_a,
                id_contacto=contacto_b,
                id_pago=pago_ingreso_a,
                tipo_documento="CUENTA_POR_COBRAR",
                id_cxc=cxc_a,
                monto_asignado_pago=Decimal("10.0000"),
                monto_asignado_documento=Decimal("10.0000"),
                id_moneda_documento=moneda_usd,
            )
        assert "id_contacto" in exc_contacto.value.message_dict

    def test_asignacion_rechaza_documentos_de_otra_empresa_y_cxc_empresa_none(
        self,
        empresa_a,
        empresa_b,
        contacto_cliente_a,
        pago_ingreso_a,
        cliente_b,
        proveedor_b,
        moneda_usd,
    ):
        cxc_b = CuentaPorCobrar.objects.create(
            empresa=empresa_b,
            cliente=cliente_b,
            monto=Decimal("100.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
        )
        cxc_sin_empresa = CuentaPorCobrar.objects.create(
            empresa=None,
            cliente=cliente_b,
            monto=Decimal("100.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
        )
        fac_v_b = FacturaFiscal.objects.create(
            id_empresa=empresa_b,
            id_cliente=cliente_b,
            numero_control="B-001",
            numero_factura="FB-001",
            fecha_emision=_hoy(),
            id_moneda=moneda_usd,
            monto_total=Decimal("100.0000"),
        )
        oc_b = OrdenCompra.objects.create(
            id_empresa=empresa_b,
            id_proveedor=proveedor_b,
            numero_orden="OC-B-1",
            fecha_orden=_hoy(),
        )
        fac_c_b = FacturaCompra.objects.create(
            id_empresa=empresa_b,
            id_orden_compra=oc_b,
            numero_factura="FCB-1",
            fecha_emision=_hoy(),
            monto_total=Decimal("100.0000"),
        )
        cxp_b = CuentaPorPagar.objects.create(
            id_empresa=empresa_b,
            id_proveedor=proveedor_b,
            id_factura_compra=fac_c_b,
            monto_total=Decimal("100.0000"),
            monto_pendiente=Decimal("100.0000"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
        )

        casos = [
            ("CUENTA_POR_COBRAR", {"id_cxc": cxc_b}),
            ("CUENTA_POR_COBRAR", {"id_cxc": cxc_sin_empresa}),
            ("FACTURA_VENTA", {"id_factura_venta": fac_v_b}),
            ("CUENTA_POR_PAGAR", {"id_cxp": cxp_b}),
            ("FACTURA_COMPRA", {"id_factura_compra": fac_c_b}),
        ]
        for tipo, fk_kwarg in casos:
            with pytest.raises(ValidationError) as exc:
                AsignacionPago.objects.create(
                    id_empresa=empresa_a,
                    id_contacto=contacto_cliente_a,
                    id_pago=pago_ingreso_a,
                    tipo_documento=tipo,
                    monto_asignado_pago=Decimal("10.0000"),
                    monto_asignado_documento=Decimal("10.0000"),
                    id_moneda_documento=moneda_usd,
                    **fk_kwarg,
                )
            assert "tipo_documento" in exc.value.message_dict

    def test_asignacion_campos_faltantes_y_objetos_inexistentes_fail_closed(
        self, empresa_a, contacto_cliente_a, pago_ingreso_a, cxc_a, moneda_usd
    ):
        with pytest.raises(ValidationError):
            AsignacionPago(
                id_contacto=contacto_cliente_a,
                id_pago=pago_ingreso_a,
                tipo_documento="CUENTA_POR_COBRAR",
                id_cxc=cxc_a,
                monto_asignado_pago=Decimal("10.0000"),
                monto_asignado_documento=Decimal("10.0000"),
                id_moneda_documento=moneda_usd,
            ).clean()

        with pytest.raises(ValidationError):
            AsignacionPago(
                id_empresa=empresa_a,
                id_contacto=contacto_cliente_a,
                tipo_documento="CUENTA_POR_COBRAR",
                id_cxc=cxc_a,
                monto_asignado_pago=Decimal("10.0000"),
                monto_asignado_documento=Decimal("10.0000"),
                id_moneda_documento=moneda_usd,
            ).clean()

        with pytest.raises(ValidationError):
            AsignacionPago(
                id_empresa=empresa_a,
                id_pago=pago_ingreso_a,
                tipo_documento="CUENTA_POR_COBRAR",
                id_cxc=cxc_a,
                monto_asignado_pago=Decimal("10.0000"),
                monto_asignado_documento=Decimal("10.0000"),
                id_moneda_documento=moneda_usd,
            ).clean()

        with pytest.raises(ValidationError):
            AsignacionPago(
                id_empresa=empresa_a,
                id_contacto_id=uuid.uuid4(),
                id_pago=pago_ingreso_a,
                tipo_documento="CUENTA_POR_COBRAR",
                id_cxc=cxc_a,
                monto_asignado_pago=Decimal("10.0000"),
                monto_asignado_documento=Decimal("10.0000"),
                id_moneda_documento=moneda_usd,
            ).clean()

        with pytest.raises(ValidationError):
            AsignacionPago(
                id_empresa=empresa_a,
                id_contacto=contacto_cliente_a,
                id_pago_id=uuid.uuid4(),
                tipo_documento="CUENTA_POR_COBRAR",
                id_cxc=cxc_a,
                monto_asignado_pago=Decimal("10.0000"),
                monto_asignado_documento=Decimal("10.0000"),
                id_moneda_documento=moneda_usd,
            ).clean()

        with pytest.raises(ValidationError):
            AsignacionPago(
                id_empresa=empresa_a,
                id_contacto=contacto_cliente_a,
                id_pago=pago_ingreso_a,
                tipo_documento="CUENTA_POR_COBRAR",
                id_cxc_id=999999999,
                monto_asignado_pago=Decimal("10.0000"),
                monto_asignado_documento=Decimal("10.0000"),
                id_moneda_documento=moneda_usd,
            ).clean()

    def test_pago_rechaza_contacto_de_otra_empresa_o_inexistente(
        self, empresa_a, contacto_b, moneda_usd, metodo_efectivo
    ):
        with pytest.raises(ValueError, match="otra empresa"):
            Pago.objects.create(
                id_empresa=empresa_a,
                id_contacto=contacto_b,
                tipo_operacion="INGRESO",
                tipo_documento="ANTICIPO",
                fecha_pago=timezone.now(),
                monto=Decimal("50.0000"),
                id_moneda=moneda_usd,
                id_metodo_pago=metodo_efectivo,
            )

        with pytest.raises(ValueError, match="empresa asociada"):
            Pago(
                id_contacto=contacto_b,
                tipo_operacion="INGRESO",
                tipo_documento="ANTICIPO",
                fecha_pago=timezone.now(),
                monto=Decimal("50.0000"),
                id_moneda=moneda_usd,
                id_metodo_pago=metodo_efectivo,
            )._validar_documento()

        with pytest.raises(ValueError, match="no existe"):
            Pago(
                id_empresa=empresa_a,
                id_contacto_id=uuid.uuid4(),
                tipo_operacion="INGRESO",
                tipo_documento="ANTICIPO",
                fecha_pago=timezone.now(),
                monto=Decimal("50.0000"),
                id_moneda=moneda_usd,
                id_metodo_pago=metodo_efectivo,
            )._validar_documento()

    def test_pago_cxc_y_sin_id_documento_no_fallan(self, empresa_a, contacto_cliente_a, moneda_usd, metodo_efectivo):
        p_cxc = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_cliente_a,
            tipo_operacion="INGRESO",
            tipo_documento="CXC",
            id_documento=None,
            fecha_pago=timezone.now(),
            monto=Decimal("25.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        p_ped_vacio = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_cliente_a,
            tipo_operacion="INGRESO",
            tipo_documento="PEDIDO",
            id_documento=None,
            fecha_pago=timezone.now(),
            monto=Decimal("25.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        assert p_cxc.id_documento is None
        assert p_ped_vacio.id_documento is None

    def test_pago_anticipo_conciliacion_cxc_rechaza_fks_documentales_cruzadas(
        self, empresa_a, empresa_b, cliente_b, proveedor_b, moneda_usd, metodo_efectivo, factura_venta_a
    ):
        """Regresión [B-2]: ANTICIPO/CONCILIACION_MULTIPLE/CXC no saltan la validación de FKs documentales."""
        from apps.fiscal.models import ContribucionParafiscal
        from apps.gastos.models import CategoriaGasto, Gasto, ReembolsoGasto
        from apps.nomina.models import Nomina, PeriodoNomina, ProcesoNomina
        from apps.rrhh.models import Cargo, Empleado

        fac_b = FacturaFiscal.objects.create(
            id_empresa=empresa_b,
            id_cliente=cliente_b,
            numero_control="B-9001",
            numero_factura="FB-9001",
            fecha_emision=_hoy(),
            id_moneda=moneda_usd,
            monto_total=Decimal("100.0000"),
        )
        ped_b = Pedido.objects.create(
            id_empresa=empresa_b, id_cliente=cliente_b, numero_pedido="PED-B-9", fecha_pedido=_hoy()
        )
        nv_b = NotaVenta.objects.create(
            id_empresa=empresa_b, id_cliente=cliente_b, numero_nota="NV-B-9", fecha_nota=_hoy()
        )
        cxp_b = CuentaPorPagar.objects.create(
            id_empresa=empresa_b,
            id_proveedor=proveedor_b,
            monto_total=Decimal("50.0000"),
            monto_pendiente=Decimal("50.0000"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
        )
        cat_b = CategoriaGasto.objects.create(id_empresa=empresa_b, nombre_categoria="Cat B")
        gasto_b = Gasto.objects.create(
            id_empresa=empresa_b,
            fecha_gasto=_hoy(),
            descripcion="Gasto B",
            monto=Decimal("20.00"),
            id_moneda=moneda_usd,
            id_categoria_gasto=cat_b,
        )
        reemb_b = ReembolsoGasto.objects.create(
            id_empresa=empresa_b,
            id_gasto=gasto_b,
            monto_reembolso=Decimal("20.00"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
            fecha_reembolso=_hoy(),
            estado_reembolso="PENDIENTE",
        )
        periodo_b = PeriodoNomina.objects.create(
            id_empresa=empresa_b,
            nombre_periodo="P-B",
            fecha_inicio=_hoy(),
            fecha_fin=_hoy(),
            fecha_pago=_hoy(),
            tipo_periodo="MENSUAL",
        )
        proc_b = ProcesoNomina.objects.create(
            id_empresa=empresa_b,
            id_periodo_nomina=periodo_b,
            numero_proceso="PROC-B-1",
            fecha_proceso=timezone.now(),
        )
        cargo_b = Cargo.objects.create(empresa=empresa_b, nombre="Cargo B")
        emp_b = Empleado.objects.create(
            empresa=empresa_b,
            nombre="Ana",
            apellido="Beta",
            cedula="V-9999999",
            cargo=cargo_b,
            fecha_ingreso=_hoy(),
        )
        nom_b = Nomina.objects.create(
            id_proceso_nomina=proc_b,
            id_empleado=emp_b,
            sueldo_base=Decimal("100.0000"),
            total_neto=Decimal("100.0000"),
            fecha_calculo=timezone.now(),
        )
        contrib_b = ContribucionParafiscal.objects.create(
            nombre="Contrib B",
            codigo="CB99",
            tipo="OTRO",
            porcentaje=Decimal("1.00"),
            base_calculo="SALARIO",
            empresa=empresa_b,
            es_publico=False,
        )

        for tipo, fk_kwargs in (
            ("ANTICIPO", {"id_factura": fac_b}),
            ("CONCILIACION_MULTIPLE", {"id_cxp": cxp_b}),
            ("CXC", {"id_pedido": ped_b}),
            ("ANTICIPO", {"id_nota_venta": nv_b}),
            ("ANTICIPO", {"id_gasto": gasto_b}),
            ("ANTICIPO", {"id_reembolso_gasto": reemb_b}),
            ("ANTICIPO", {"id_nomina": nom_b}),
            ("ANTICIPO", {"id_contribucion": contrib_b}),
            ("ANTICIPO", {"id_factura_id": uuid.uuid4()}),
        ):
            with pytest.raises(ValueError, match="no existe"):
                Pago.objects.create(
                    id_empresa=empresa_a,
                    tipo_operacion="INGRESO",
                    tipo_documento=tipo,
                    id_documento=None,
                    fecha_pago=timezone.now(),
                    monto=Decimal("10.0000"),
                    id_moneda=moneda_usd,
                    id_metodo_pago=metodo_efectivo,
                    **fk_kwargs,
                )

        # Factura de la misma empresa con id_documento=None debe seguir funcionando
        pago_ok = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="FACTURA",
            id_documento=None,
            id_factura=factura_venta_a,
            fecha_pago=timezone.now(),
            monto=Decimal("15.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        assert pago_ok.id_factura_id == factura_venta_a.pk


# ── 4. Verificación real de RLS en PostgreSQL ────────────────────────────────


@pytest.mark.tenant
class TestAsignacionPagoRLSReal:
    def test_pg_policies_y_force_rls_en_finanzas_asignacion_pago(self):
        with connection.cursor() as cur:
            cur.execute(
                "SELECT c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = 'finanzas_asignacion_pago'"
            )
            estado = cur.fetchone()
            cur.execute(
                "SELECT qual, with_check FROM pg_policies "
                "WHERE schemaname = 'public' AND tablename = 'finanzas_asignacion_pago' AND policyname = %s",
                [rls.POLICY_NAME],
            )
            politica = cur.fetchone()

        assert estado == (True, True)
        assert politica is not None
        qual, with_check = politica
        assert "id_empresa_id" in qual
        assert "IS NULL" not in qual
        assert with_check == qual

    def test_aislamiento_rls_con_rol_no_privilegiado(
        self,
        rls_test_role,
        empresa_a,
        empresa_b,
        contacto_cliente_a,
        contacto_b,
        pago_ingreso_a,
        cxc_a,
        cliente_b,
        moneda_usd,
        metodo_efectivo,
    ):
        pago_b = Pago.objects.create(
            id_empresa=empresa_b,
            id_contacto=contacto_b,
            tipo_operacion="INGRESO",
            tipo_documento="ANTICIPO",
            fecha_pago=timezone.now(),
            monto=Decimal("200.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        cxc_b = CuentaPorCobrar.objects.create(
            empresa=empresa_b,
            cliente=cliente_b,
            monto=Decimal("200.00"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
        )
        asig_a = AsignacionPago.objects.create(
            id_empresa=empresa_a,
            id_contacto=contacto_cliente_a,
            id_pago=pago_ingreso_a,
            tipo_documento="CUENTA_POR_COBRAR",
            id_cxc=cxc_a,
            monto_asignado_pago=Decimal("50.0000"),
            monto_asignado_documento=Decimal("50.0000"),
            id_moneda_documento=moneda_usd,
        )
        asig_b = AsignacionPago.objects.create(
            id_empresa=empresa_b,
            id_contacto=contacto_b,
            id_pago=pago_b,
            tipo_documento="CUENTA_POR_COBRAR",
            id_cxc=cxc_b,
            monto_asignado_pago=Decimal("80.0000"),
            monto_asignado_documento=Decimal("80.0000"),
            id_moneda_documento=moneda_usd,
        )

        with connection.cursor() as cur:
            if rls_test_role is not None:
                cur.execute(f'SET ROLE "{rls_test_role}"')
            try:
                rls.apply_context([empresa_a.id_empresa], bypass=False)
                assert set(AsignacionPago.objects.values_list("pk", flat=True)) == {asig_a.pk}

                rls.apply_context([empresa_b.id_empresa], bypass=False)
                assert set(AsignacionPago.objects.values_list("pk", flat=True)) == {asig_b.pk}

                # Sin contexto -> fail-closed (0 filas)
                rls.apply_context([], bypass=False)
                assert AsignacionPago.objects.count() == 0

                # WITH CHECK bloquea insertar fila de B bajo contexto de A
                rls.apply_context([empresa_a.id_empresa], bypass=False)
                with pytest.raises((IntegrityError, ProgrammingError)), transaction.atomic():
                    AsignacionPago.objects.create(
                        id_empresa=empresa_b,
                        id_contacto=contacto_b,
                        id_pago=pago_b,
                        tipo_documento="CUENTA_POR_COBRAR",
                        id_cxc=cxc_b,
                        monto_asignado_pago=Decimal("10.0000"),
                        monto_asignado_documento=Decimal("10.0000"),
                        id_moneda_documento=moneda_usd,
                    )

                with rls.rls_bypass():
                    assert set(AsignacionPago.objects.values_list("pk", flat=True)) == {asig_a.pk, asig_b.pk}
            finally:
                rls.apply_system_default()
                if rls_test_role is not None:
                    cur.execute("RESET ROLE")


# ── 5. API POST /pagos/, PagoSerializer y registrar_efectos_pago ──────────────


class TestPagoAnticipoYSerializerContacto:
    URL = "/api/finanzas/pagos/"

    def test_post_pago_anticipo_sin_id_documento_usa_id_pago_en_efectos_y_notificacion(
        self, user_a, empresa_a, contacto_cliente_a, moneda_usd, metodo_efectivo, monkeypatch
    ):
        eventos = []

        import apps.notificaciones.services as notif

        monkeypatch.setattr(notif, "emitir_notificacion", lambda *args, **kwargs: eventos.append(args))
        client = APIClient()
        client.force_authenticate(user=user_a)

        resp = client.post(
            self.URL,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_contacto": str(contacto_cliente_a.id_contacto),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "ANTICIPO",
                "id_documento": None,
                "fecha_pago": timezone.now().isoformat(),
                "monto": "125.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        assert resp.data["id_documento"] is None
        assert str(resp.data["id_contacto"]) == str(contacto_cliente_a.id_contacto)
        assert resp.data["contacto_nombre"] == contacto_cliente_a.nombre_completo

        pago = Pago.objects.get(pk=resp.data["id_pago"])
        tf = TransaccionFinanciera.objects.get(pk=pago.id_transaccion_financiera_id)
        assert tf.nro_documento_asociado == str(pago.id_pago)
        assert tf.nro_documento_asociado != "None"
        assert len(eventos) == 1
        assert eventos[0][3]["numero_factura"] == str(pago.id_pago)

    def test_registrar_efectos_pago_sin_id_documento_usa_id_pago(self, user_a, empresa_a, moneda_usd, metodo_efectivo):
        pago = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="EGRESO",
            tipo_documento="ANTICIPO",
            id_documento=None,
            fecha_pago=timezone.now(),
            monto=Decimal("75.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
            id_usuario_registro=user_a,
        )
        tf, _ = registrar_efectos_pago(pago)
        assert tf.nro_documento_asociado == str(pago.id_pago)
        assert PagoSerializer(pago).data["contacto_nombre"] == ""

    def test_auto_derivacion_id_contacto_desde_documentos(
        self,
        user_a,
        empresa_a,
        empresa_b,
        cliente_a,
        proveedor_a,
        contacto_cliente_a,
        contacto_proveedor_a,
        contacto_b,
        factura_venta_a,
        cxp_a,
        moneda_usd,
        metodo_efectivo,
    ):
        pedido_a = Pedido.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            numero_pedido="PED-AUTO-1",
            fecha_pedido=_hoy(),
        )
        nota_a = NotaVenta.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            numero_nota="NV-AUTO-1",
            fecha_nota=_hoy(),
        )

        # Factura -> contacto_cliente_a
        s_fac = PagoSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "FACTURA",
                "id_documento": str(factura_venta_a.pk),
                "id_factura": str(factura_venta_a.pk),
                "fecha_pago": timezone.now().isoformat(),
                "monto": "50.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert s_fac.is_valid(), s_fac.errors
        assert s_fac.save().id_contacto == contacto_cliente_a

        # Pedido -> contacto_cliente_a
        s_ped = PagoSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "PEDIDO",
                "id_documento": str(pedido_a.pk),
                "id_pedido": str(pedido_a.pk),
                "fecha_pago": timezone.now().isoformat(),
                "monto": "50.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert s_ped.is_valid(), s_ped.errors
        assert s_ped.save().id_contacto == contacto_cliente_a

        # NotaVenta -> contacto_cliente_a
        s_nv = PagoSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "NOTA_VENTA",
                "id_documento": str(nota_a.pk),
                "id_nota_venta": str(nota_a.pk),
                "fecha_pago": timezone.now().isoformat(),
                "monto": "50.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert s_nv.is_valid(), s_nv.errors
        assert s_nv.save().id_contacto == contacto_cliente_a

        # CxP -> contacto_proveedor_a
        s_cxp = PagoSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "EGRESO",
                "tipo_documento": "CXP",
                "id_documento": str(cxp_a.pk),
                "id_cxp": str(cxp_a.pk),
                "fecha_pago": timezone.now().isoformat(),
                "monto": "50.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert s_cxp.is_valid(), s_cxp.errors
        assert s_cxp.save().id_contacto == contacto_proveedor_a

        # Cliente sin contacto -> None (no falla)
        cliente_sin = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Sin Contacto", rif="J-55555555-5", contacto=None
        )
        ped_sin = Pedido.objects.create(
            id_empresa=empresa_a, id_cliente=cliente_sin, numero_pedido="PED-SIN-1", fecha_pedido=_hoy()
        )
        s_sin = PagoSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "PEDIDO",
                "id_documento": str(ped_sin.pk),
                "id_pedido": str(ped_sin.pk),
                "fecha_pago": timezone.now().isoformat(),
                "monto": "10.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert s_sin.is_valid(), s_sin.errors
        assert s_sin.save().id_contacto is None

        # Si el cliente tuviera contacto de otra empresa (corrupto), NO se auto-deriva
        Cliente.objects.filter(pk=cliente_sin.pk).update(contacto=contacto_b)
        ped_sin.refresh_from_db()
        s_cross = PagoSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "PEDIDO",
                "id_documento": str(ped_sin.pk),
                "id_pedido": str(ped_sin.pk),
                "fecha_pago": timezone.now().isoformat(),
                "monto": "10.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert s_cross.is_valid(), s_cross.errors
        assert s_cross.save().id_contacto is None

    def test_anti_idor_y_visibilidad_en_pago_serializer_y_endpoint(
        self, user_a, empresa_a, empresa_b, contacto_cliente_a, contacto_b, moneda_usd, metodo_efectivo
    ):
        client = APIClient()
        client.force_authenticate(user=user_a)

        # Endpoint rechaza id_contacto de empresa_b (400)
        resp_contacto = client.post(
            self.URL,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_contacto": str(contacto_b.id_contacto),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "ANTICIPO",
                "fecha_pago": timezone.now().isoformat(),
                "monto": "40.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            format="json",
        )
        assert resp_contacto.status_code == 400
        assert "id_contacto" in resp_contacto.data

        # Endpoint rechaza id_empresa de empresa_b (400)
        resp_emp = client.post(
            self.URL,
            {
                "id_empresa": str(empresa_b.id_empresa),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "ANTICIPO",
                "fecha_pago": timezone.now().isoformat(),
                "monto": "40.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            format="json",
        )
        assert resp_emp.status_code == 400
        assert "id_empresa" in resp_emp.data

        # Serializer directo rechaza id_empresa ajena e id_contacto ajeno
        s_emp_ajena = PagoSerializer(
            data={
                "id_empresa": str(empresa_b.id_empresa),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "ANTICIPO",
                "fecha_pago": timezone.now().isoformat(),
                "monto": "40.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert not s_emp_ajena.is_valid()
        assert "id_empresa" in s_emp_ajena.errors

        s_c_ajeno = PagoSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "id_contacto": str(contacto_b.id_contacto),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "ANTICIPO",
                "fecha_pago": timezone.now().isoformat(),
                "monto": "40.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert not s_c_ajeno.is_valid()
        assert "id_contacto" in s_c_ajeno.errors

        # Usuario con empresa matriz + subsidiaria: no puede cruzar contacto de subsidiaria en pago de matriz
        sub = Empresa.objects.create(
            nombre_legal="Subsidiaria S.A.",
            identificador_fiscal="J-77777777-7",
            empresa_matriz=empresa_a,
            id_moneda_base=moneda_usd,
        )
        contacto_sub = Contacto.objects.create(
            id_empresa=sub,
            nombre="Contacto Sub",
            rif="J-77777777-8",
            es_cliente=True,
        )
        s_cruce = PagoSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "id_contacto": str(contacto_sub.id_contacto),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "ANTICIPO",
                "fecha_pago": timezone.now().isoformat(),
                "monto": "40.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert not s_cruce.is_valid()
        assert "id_contacto" in s_cruce.errors

        # create() usa get_empresas_visible(user) cuando id_empresa no viene en validated_data
        s_auto_emp = PagoSerializer(context={"request": SimpleNamespace(user=user_a)})
        pago_creado = s_auto_emp.create(
            {
                "tipo_operacion": "INGRESO",
                "tipo_documento": "ANTICIPO",
                "fecha_pago": timezone.now(),
                "monto": Decimal("33.0000"),
                "id_moneda": moneda_usd,
                "id_metodo_pago": metodo_efectivo,
                "id_contacto": contacto_cliente_a,
            }
        )
        assert pago_creado.id_empresa == empresa_a
        assert pago_creado.id_usuario_registro == user_a

        # PATCH cambiando id_empresa sin actualizar id_contacto -> ValidationError
        s_patch = PagoSerializer(
            instance=pago_creado,
            data={"id_empresa": str(sub.id_empresa)},
            partial=True,
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert not s_patch.is_valid()
        assert "id_contacto" in s_patch.errors

        # Superusuario Omni puede operar en empresa_b con contacto_b, pero no mezclar empresas
        from apps.core.models import Usuarios

        super_user = Usuarios.objects.create_user(
            username="super_pago_test",
            password="Password123!",
            email="super_pago@test.local",
            es_superusuario_omni=True,
        )
        s_super_ok = PagoSerializer(
            data={
                "id_empresa": str(empresa_b.id_empresa),
                "id_contacto": str(contacto_b.id_contacto),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "ANTICIPO",
                "fecha_pago": timezone.now().isoformat(),
                "monto": "20.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            context={"request": SimpleNamespace(user=super_user)},
        )
        assert s_super_ok.is_valid(), s_super_ok.errors
        assert s_super_ok.save().id_contacto == contacto_b

    def test_b2_api_anticipo_y_matriz_subsidiaria_devuelven_400_no_500(
        self, user_a, empresa_a, empresa_b, factura_venta_a, moneda_usd, metodo_efectivo, monkeypatch
    ):
        """Regresión [B-2]: mezcla matriz/subsidiaria o ANTICIPO con FK ajena devuelve 400 (nunca 500)."""
        from apps.fiscal.models import ContribucionParafiscal
        from apps.nomina.models import Nomina, PeriodoNomina, ProcesoNomina
        from apps.rrhh.models import Cargo, Empleado

        sub = Empresa.objects.create(
            nombre_legal="Subsidiaria B2 S.A.",
            identificador_fiscal="J-88888881-1",
            empresa_matriz=empresa_a,
            id_moneda_base=moneda_usd,
        )
        cliente_sub = Cliente.objects.create(id_empresa=sub, razon_social="Cliente Sub", rif="J-88888882-2")
        fac_sub = FacturaFiscal.objects.create(
            id_empresa=sub,
            id_cliente=cliente_sub,
            numero_control="SUB-001",
            numero_factura="FSUB-001",
            fecha_emision=_hoy(),
            id_moneda=moneda_usd,
            monto_total=Decimal("100.0000"),
        )
        prov_sub = Proveedor.objects.create(id_empresa=sub, razon_social="Prov Sub", rif="J-88888883-3")
        cxp_sub = CuentaPorPagar.objects.create(
            id_empresa=sub,
            id_proveedor=prov_sub,
            monto_total=Decimal("50.0000"),
            monto_pendiente=Decimal("50.0000"),
            fecha_emision=_hoy(),
            fecha_vencimiento=_hoy(),
        )

        client = APIClient()
        client.force_authenticate(user=user_a)

        # ANTICIPO de matriz con id_factura de subsidiaria -> 400
        resp_ant_sub = client.post(
            self.URL,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "ANTICIPO",
                "id_factura": str(fac_sub.pk),
                "fecha_pago": timezone.now().isoformat(),
                "monto": "25.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            format="json",
        )
        assert resp_ant_sub.status_code == 400
        assert "id_factura" in resp_ant_sub.data

        # FACTURA de matriz con id_factura de subsidiaria -> 400 (antes HTTP 500)
        resp_fac_sub = client.post(
            self.URL,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "FACTURA",
                "id_documento": str(fac_sub.pk),
                "id_factura": str(fac_sub.pk),
                "fecha_pago": timezone.now().isoformat(),
                "monto": "25.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            format="json",
        )
        assert resp_fac_sub.status_code == 400
        assert "id_factura" in resp_fac_sub.data

        # CONCILIACION_MULTIPLE de matriz con id_cxp de subsidiaria -> 400
        resp_cxp_sub = client.post(
            self.URL,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "EGRESO",
                "tipo_documento": "CONCILIACION_MULTIPLE",
                "id_cxp": str(cxp_sub.pk),
                "fecha_pago": timezone.now().isoformat(),
                "monto": "25.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            format="json",
        )
        assert resp_cxp_sub.status_code == 400
        assert "id_cxp" in resp_cxp_sub.data

        # PATCH cambiando id_empresa a sub dejando id_factura de matriz -> 400
        pago_matriz = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="FACTURA",
            id_documento=factura_venta_a.pk,
            id_factura=factura_venta_a,
            fecha_pago=timezone.now(),
            monto=Decimal("20.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        resp_patch = client.patch(
            f"{self.URL}{pago_matriz.pk}/",
            {"id_empresa": str(sub.id_empresa)},
            format="json",
        )
        assert resp_patch.status_code == 400
        assert "id_factura" in resp_patch.data

        # Serializer valida también id_nomina e id_contribucion privada de otra empresa
        periodo_b = PeriodoNomina.objects.create(
            id_empresa=empresa_b,
            nombre_periodo="P-B2",
            fecha_inicio=_hoy(),
            fecha_fin=_hoy(),
            fecha_pago=_hoy(),
            tipo_periodo="MENSUAL",
        )
        proc_b = ProcesoNomina.objects.create(
            id_empresa=empresa_b,
            id_periodo_nomina=periodo_b,
            numero_proceso="PROC-B-2",
            fecha_proceso=timezone.now(),
        )
        cargo_b = Cargo.objects.create(empresa=empresa_b, nombre="Cargo B2")
        emp_b = Empleado.objects.create(
            empresa=empresa_b,
            nombre="Luis",
            apellido="Beta",
            cedula="V-8888888",
            cargo=cargo_b,
            fecha_ingreso=_hoy(),
        )
        nom_b = Nomina.objects.create(
            id_proceso_nomina=proc_b,
            id_empleado=emp_b,
            sueldo_base=Decimal("100.0000"),
            total_neto=Decimal("100.0000"),
            fecha_calculo=timezone.now(),
        )
        contrib_b = ContribucionParafiscal.objects.create(
            nombre="Contrib B2",
            codigo="CB2",
            tipo="OTRO",
            porcentaje=Decimal("1.00"),
            base_calculo="SALARIO",
            empresa=empresa_b,
            es_publico=False,
        )

        s_nom = PagoSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "EGRESO",
                "tipo_documento": "NOMINA",
                "id_nomina": str(nom_b.pk),
                "fecha_pago": timezone.now().isoformat(),
                "monto": "10.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert not s_nom.is_valid()
        assert "id_nomina" in s_nom.errors

        s_contrib = PagoSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "EGRESO",
                "tipo_documento": "IMPUESTO",
                "id_contribucion": str(contrib_b.pk),
                "fecha_pago": timezone.now().isoformat(),
                "monto": "10.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            context={"request": SimpleNamespace(user=user_a)},
        )
        assert not s_contrib.is_valid()
        assert "id_contribucion" in s_contrib.errors

        # Defensa en profundidad en PagoViewSet: si save() lanza ValueError -> 400 (no 500)
        monkeypatch.setattr(Pago, "save", lambda self, *a, **kw: (_ for _ in ()).throw(ValueError("error dominio")))
        resp_post_val = client.post(
            self.URL,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_operacion": "INGRESO",
                "tipo_documento": "ANTICIPO",
                "fecha_pago": timezone.now().isoformat(),
                "monto": "10.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            format="json",
        )
        assert resp_post_val.status_code == 400
        resp_patch_val = client.patch(
            f"{self.URL}{pago_matriz.pk}/",
            {"referencia": "REF-X"},
            format="json",
        )
        assert resp_patch_val.status_code == 400

    def test_usuario_sin_empresas_visibles_falla_con_validation_error_y_no_integrity_error(
        self, moneda_usd, metodo_efectivo
    ):
        from apps.core.models import Usuarios
        from rest_framework.exceptions import ValidationError as DRFValidationError

        user_huerfano = Usuarios.objects.create_user(
            username="sin_empresa_pago",
            password="Password123!",
            email="sin_empresa@test.local",
        )
        s_partial = PagoSerializer(
            data={
                "tipo_operacion": "INGRESO",
                "tipo_documento": "ANTICIPO",
                "fecha_pago": timezone.now().isoformat(),
                "monto": "15.0000",
                "id_moneda": str(moneda_usd.id_moneda),
                "id_metodo_pago": str(metodo_efectivo.id_metodo_pago),
            },
            partial=True,
            context={"request": SimpleNamespace(user=user_huerfano)},
        )
        assert not s_partial.is_valid()
        assert "id_empresa" in s_partial.errors

        with pytest.raises(DRFValidationError):
            PagoSerializer(context={"request": SimpleNamespace(user=user_huerfano)}).create(
                {
                    "tipo_operacion": "INGRESO",
                    "tipo_documento": "ANTICIPO",
                    "fecha_pago": timezone.now(),
                    "monto": Decimal("15.0000"),
                    "id_moneda": moneda_usd,
                    "id_metodo_pago": metodo_efectivo,
                }
            )

    def test_b3_contacto_nombre_openapi_sin_minlength_contradictorio(self):
        """Regresión [B-3]: contacto_nombre permite blanco y openapi.json no exige minLength=1."""
        field = PagoSerializer().fields["contacto_nombre"]
        assert field.allow_blank is True

        openapi_path = Path(__file__).resolve().parents[3] / "frontend" / "src" / "api" / "openapi.json"
        if openapi_path.exists():
            schema = json.loads(openapi_path.read_text(encoding="utf-8"))
            prop = schema["definitions"]["Pago"]["properties"]["contacto_nombre"]
            assert prop.get("default") == ""
            assert "minLength" not in prop


# ── 6. Migración 0044_backfill_pago_id_contacto ──────────────────────────────


@pytest.mark.django_db(transaction=True)
class TestMigracionBackfillPagoContacto:
    def test_backfill_forward_idempotente_cross_tenant_y_reversible(
        self,
        empresa_a,
        empresa_b,
        contacto_cliente_a,
        contacto_proveedor_a,
        contacto_b,
        cliente_a,
        proveedor_a,
        factura_venta_a,
        cxp_a,
        moneda_usd,
        metodo_efectivo,
    ):
        pedido_a = Pedido.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            numero_pedido="PED-BF-1",
            fecha_pedido=_hoy(),
        )
        nota_a = NotaVenta.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_a,
            numero_nota="NV-BF-1",
            fecha_nota=_hoy(),
        )
        cliente_corrupto = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente Cruzado",
            rif="J-66666666-6",
            contacto=contacto_b,
        )
        pedido_cruzado = Pedido.objects.create(
            id_empresa=empresa_a,
            id_cliente=cliente_corrupto,
            numero_pedido="PED-BF-CRUZ",
            fecha_pedido=_hoy(),
        )
        otro_contacto_a = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Contacto Preservado",
            rif="J-66666666-9",
            es_cliente=True,
        )

        p_fac = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="FACTURA",
            id_documento=factura_venta_a.pk,
            id_factura=factura_venta_a,
            fecha_pago=timezone.now(),
            monto=Decimal("10.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        p_ped = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="PEDIDO",
            id_documento=pedido_a.pk,
            id_pedido=pedido_a,
            fecha_pago=timezone.now(),
            monto=Decimal("10.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        p_nv = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="NOTA_VENTA",
            id_documento=nota_a.pk,
            id_nota_venta=nota_a,
            fecha_pago=timezone.now(),
            monto=Decimal("10.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        p_cxp = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="EGRESO",
            tipo_documento="CXP",
            id_documento=cxp_a.pk,
            id_cxp=cxp_a,
            fecha_pago=timezone.now(),
            monto=Decimal("10.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        p_cruzado = Pago.objects.create(
            id_empresa=empresa_a,
            tipo_operacion="INGRESO",
            tipo_documento="PEDIDO",
            id_documento=pedido_cruzado.pk,
            id_pedido=pedido_cruzado,
            fecha_pago=timezone.now(),
            monto=Decimal("10.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )
        p_preservado = Pago.objects.create(
            id_empresa=empresa_a,
            id_contacto=otro_contacto_a,
            tipo_operacion="INGRESO",
            tipo_documento="FACTURA",
            id_documento=factura_venta_a.pk,
            id_factura=factura_venta_a,
            fecha_pago=timezone.now(),
            monto=Decimal("10.0000"),
            id_moneda=moneda_usd,
            id_metodo_pago=metodo_efectivo,
        )

        # Ejecutar migración real 0044 (reverse -> 0043 -> forward -> 0044)
        executor = MigrationExecutor(connection)
        executor.migrate([("finanzas", "0043_rls_asignacion_pago")])
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([("finanzas", "0044_backfill_pago_id_contacto")])

            # Usar project_state acorde al esquema actualmente aplicado (puede haber
            # migraciones posteriores en apps relacionadas ya revertidas temporalmente).
            executor = MigrationExecutor(connection)
            apps_0044 = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
            Pago0044 = apps_0044.get_model("finanzas", "Pago")

            with rls.rls_bypass():
                assert Pago0044.objects.get(pk=p_fac.pk).id_contacto_id == contacto_cliente_a.pk
                assert Pago0044.objects.get(pk=p_ped.pk).id_contacto_id == contacto_cliente_a.pk
                assert Pago0044.objects.get(pk=p_nv.pk).id_contacto_id == contacto_cliente_a.pk
                assert Pago0044.objects.get(pk=p_cxp.pk).id_contacto_id == contacto_proveedor_a.pk
                assert Pago0044.objects.get(pk=p_cruzado.pk).id_contacto_id is None
                assert Pago0044.objects.get(pk=p_preservado.pk).id_contacto_id == otro_contacto_a.pk

            # Idempotencia: segunda corrida no altera nada
            mod = importlib.import_module("apps.finanzas.migrations.0044_backfill_pago_id_contacto")

            with connection.schema_editor() as editor:
                mod.backfill_pago_id_contacto(apps_0044, editor)

            with rls.rls_bypass():
                assert Pago0044.objects.get(pk=p_preservado.pk).id_contacto_id == otro_contacto_a.pk
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
