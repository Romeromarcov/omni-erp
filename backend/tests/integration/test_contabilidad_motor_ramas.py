"""Fase 3 (cobertura) — ramas del motor de asientos generar_asiento (R-CODE-11).

Cubre las validaciones y caminos de borde del motor contable (código de dinero
crítico): tipo inválido, monto ≤ 0, extracción de empresa/monto, mapeo faltante,
y auto-aprobación según empresa.contabilidad_auto_aprobar.
"""
import uuid
from decimal import Decimal

import pytest

from apps.contabilidad.services import (
    AsientoError,
    MapeoContableNoEncontrado,
    generar_asiento,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class _Doc:
    """Documento mínimo (pk + atributos opcionales) para el motor de asientos."""
    def __init__(self, **kw):
        self.pk = uuid.uuid4()
        for k, v in kw.items():
            setattr(self, k, v)


def _cuenta(empresa, codigo, nombre):
    from apps.contabilidad.models import PlanCuentas
    return PlanCuentas.objects.create(
        id_empresa=empresa, codigo_cuenta=codigo, nombre_cuenta=nombre,
        tipo_cuenta="ACTIVO", naturaleza="DEUDORA", nivel=1,
    )


def _mapeo(empresa, tipo):
    from apps.contabilidad.models import MapeoContable
    return MapeoContable.objects.create(
        id_empresa=empresa, tipo_asiento=tipo,
        cuenta_debe=_cuenta(empresa, "1.1", "Caja"),
        cuenta_haber=_cuenta(empresa, "4.1", "Ventas"),
        descripcion_plantilla="Asiento {tipo} {numero}", activo=True,
    )


def test_tipo_invalido(empresa_a):
    with pytest.raises(AsientoError, match="Tipo desconocido"):
        generar_asiento("TIPO_INEXISTENTE", _Doc(), empresa=empresa_a, monto=Decimal("10"))


def test_monto_cero_o_negativo(empresa_a):
    with pytest.raises(AsientoError, match="mayor a cero"):
        generar_asiento("FACTURA_VENTA", _Doc(), empresa=empresa_a, monto=Decimal("0"))
    with pytest.raises(AsientoError, match="mayor a cero"):
        generar_asiento("FACTURA_VENTA", _Doc(), empresa=empresa_a, monto=Decimal("-5"))


def test_empresa_no_extraible(empresa_a):
    # documento sin id_empresa/empresa y empresa=None → AsientoError.
    with pytest.raises(AsientoError, match="extraer empresa"):
        generar_asiento("FACTURA_VENTA", _Doc(), empresa=None, monto=Decimal("10"))


def test_empresa_inferida_del_documento(empresa_a):
    # documento con id_empresa → se infiere; sin mapeo → MapeoContableNoEncontrado.
    with pytest.raises(MapeoContableNoEncontrado):
        generar_asiento("FACTURA_VENTA", _Doc(id_empresa=empresa_a), empresa=None, monto=Decimal("10"))


def test_monto_no_extraible(empresa_a):
    # documento sin ningún campo de monto y monto=None → AsientoError.
    with pytest.raises(AsientoError, match="extraer monto"):
        generar_asiento("FACTURA_VENTA", _Doc(), empresa=empresa_a, monto=None)


def test_monto_inferido_del_documento(empresa_a):
    _mapeo(empresa_a, "FACTURA_VENTA")
    asiento = generar_asiento("FACTURA_VENTA", _Doc(monto_total=Decimal("123.45")), empresa=empresa_a)
    detalles = list(asiento.detalleasiento_set.all()) if hasattr(asiento, "detalleasiento_set") else None
    # El asiento se creó con el monto inferido (validamos vía total debe).
    from apps.contabilidad.models import DetalleAsiento
    debe = DetalleAsiento.objects.filter(id_asiento=asiento, debe__gt=0).first()
    assert debe.debe == Decimal("123.45")


def test_mapeo_no_encontrado(empresa_a):
    with pytest.raises(MapeoContableNoEncontrado):
        generar_asiento("FACTURA_VENTA", _Doc(), empresa=empresa_a, monto=Decimal("10"))


def test_borrador_por_defecto(empresa_a):
    _mapeo(empresa_a, "FACTURA_VENTA")
    asiento = generar_asiento("FACTURA_VENTA", _Doc(), empresa=empresa_a, monto=Decimal("10"))
    assert asiento.estado_asiento == "BORRADOR"


def test_auto_aprobacion(empresa_a):
    empresa_a.contabilidad_auto_aprobar = True
    empresa_a.save(update_fields=["contabilidad_auto_aprobar"])
    _mapeo(empresa_a, "FACTURA_VENTA")
    asiento = generar_asiento("FACTURA_VENTA", _Doc(), empresa=empresa_a, monto=Decimal("10"))
    assert asiento.estado_asiento == "APROBADO"
