"""
PR 1.1 — R-CODE-11 centralizado en `generar_asiento_o_fallar`.

Verifica la política uniforme aplicada a compras (H-BUG-1), inventario
(BUG-NEW-1) y cxc/acuerdos (M-BUG-10):

- AsientoError siempre propaga (rompe la transacción).
- MapeoContableNoEncontrado: error duro si empresa.contabilidad_activa, best-effort
  si no.
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.contabilidad import services as contab_services
from apps.contabilidad.services import (
    AsientoError,
    MapeoContableNoEncontrado,
    generar_asiento_o_fallar,
)

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_helper_falla_si_falta_mapeo_y_contabilidad_activa(empresa_a):
    empresa_a.contabilidad_activa = True
    empresa_a.save(update_fields=["contabilidad_activa"])
    doc = MagicMock()
    with patch.object(
        contab_services, "generar_asiento", side_effect=MapeoContableNoEncontrado("sin mapeo")
    ):
        with pytest.raises(AsientoError):
            generar_asiento_o_fallar("AJUSTE_INVENTARIO", doc, empresa_a)


@pytest.mark.django_db
def test_helper_best_effort_si_contabilidad_inactiva(empresa_a):
    assert empresa_a.contabilidad_activa is False  # default
    doc = MagicMock()
    with patch.object(
        contab_services, "generar_asiento", side_effect=MapeoContableNoEncontrado("sin mapeo")
    ):
        asiento, error = generar_asiento_o_fallar("AJUSTE_INVENTARIO", doc, empresa_a)
    assert asiento is None
    assert "sin mapeo" in error


@pytest.mark.django_db
def test_helper_propaga_asiento_error_aunque_contabilidad_inactiva(empresa_a):
    """Un descuadre real (AsientoError no-mapeo) SIEMPRE rompe, exija o no contabilidad."""
    assert empresa_a.contabilidad_activa is False
    doc = MagicMock()
    with patch.object(
        contab_services, "generar_asiento", side_effect=AsientoError("descuadre debe!=haber")
    ):
        with pytest.raises(AsientoError):
            generar_asiento_o_fallar("AJUSTE_INVENTARIO", doc, empresa_a)


@pytest.mark.django_db
def test_compras_importa_y_usa_el_helper_centralizado(empresa_a):
    """H-BUG-1: compras enruta su asiento por el helper (no por except/pass)."""
    from apps.compras import services as compras_services

    # compras debe exponer el helper centralizado (lo importa a su namespace).
    assert hasattr(compras_services, "generar_asiento_o_fallar")
    # y no debe quedar el swallow antiguo de MapeoContableNoEncontrado.
    import inspect

    src = inspect.getsource(compras_services)
    assert "MapeoContableNoEncontrado" not in src
