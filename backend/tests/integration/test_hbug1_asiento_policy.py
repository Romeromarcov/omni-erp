"""
H-BUG-1: confirmar_nota_venta falla en duro si la empresa exige contabilidad
y falta el mapeo contable; procede best-effort si no la exige.
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.contabilidad.services import MapeoContableNoEncontrado
from apps.ventas import services as ventas_services
from apps.ventas.services import VentaError, confirmar_nota_venta

pytestmark = pytest.mark.integration


def _nota_mock(empresa):
    nota = MagicMock()
    nota.id_empresa = empresa
    nota.detalles.all.return_value = []  # subtotal = 0
    return nota


@pytest.mark.django_db
def test_confirmar_falla_si_falta_mapeo_y_contabilidad_activa(empresa_a):
    empresa_a.contabilidad_activa = True
    empresa_a.save(update_fields=["contabilidad_activa"])
    nota = _nota_mock(empresa_a)
    with (
        patch.object(ventas_services, "entregar_nota_venta", return_value={"movimientos": [], "cxc": None}),
        patch.object(ventas_services, "generar_asiento", side_effect=MapeoContableNoEncontrado("sin mapeo")),
    ):
        with pytest.raises(VentaError):
            confirmar_nota_venta(nota, almacen=None, usuario=None)


@pytest.mark.django_db
def test_confirmar_ok_sin_mapeo_si_contabilidad_inactiva(empresa_a):
    assert empresa_a.contabilidad_activa is False  # default
    nota = _nota_mock(empresa_a)
    with (
        patch.object(ventas_services, "entregar_nota_venta", return_value={"movimientos": [], "cxc": None}),
        patch.object(ventas_services, "generar_asiento", side_effect=MapeoContableNoEncontrado("sin mapeo")),
    ):
        resultado = confirmar_nota_venta(nota, almacen=None, usuario=None)
    assert resultado["asiento"] is None
    assert "sin mapeo" in resultado["asiento_error"]
