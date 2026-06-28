"""Tests de las tareas Celery de sincronización periódica (Fase 5 — sync programado)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.cxc_lubrikca.tasks import sync_cxc_lubrikca, sync_cxc_lubrikca_todos

pytestmark = pytest.mark.django_db


def _parametro_datasource(empresa, valor="odoo"):
    from apps.configuracion_motor.models import ParametroSistema

    return ParametroSistema.objects.create(
        id_empresa=empresa,
        nombre_parametro="Fuente de datos CxC",
        codigo_parametro="cxc.datasource",
        valor_parametro=valor,
        tipo_dato="TEXTO",
        activo=True,
    )


def test_sync_todos_encola_solo_tenants_odoo(empresa_a, empresa_b):
    _parametro_datasource(empresa_a, "odoo")
    _parametro_datasource(empresa_b, "nativo")  # no debe encolarse

    with patch("apps.cxc_lubrikca.tasks.sync_cxc_lubrikca.delay") as mock_delay:
        res = sync_cxc_lubrikca_todos()

    assert res == {"tenants_odoo": 1}
    mock_delay.assert_called_once_with(str(empresa_a.id_empresa))


def test_sync_empresa_happy_path(empresa_a):
    with patch(
        "apps.cxc_lubrikca.services.sync.sincronizar_empresa",
        return_value={"pedidos": 2, "lineas": 3, "pagos": 1, "precios": 2, "facturas": 1},
    ) as mock_sync:
        res = sync_cxc_lubrikca(str(empresa_a.id_empresa))

    mock_sync.assert_called_once()
    assert res["empresa_id"] == str(empresa_a.id_empresa)
    assert res["pedidos"] == 2
    assert "error" not in res


def test_sync_empresa_tolera_errores(empresa_a):
    with patch(
        "apps.cxc_lubrikca.services.sync.sincronizar_empresa",
        side_effect=RuntimeError("Odoo caído"),
    ):
        res = sync_cxc_lubrikca(str(empresa_a.id_empresa))

    # No relanza: devuelve el error como dato para no tumbar el worker.
    assert res["empresa_id"] == str(empresa_a.id_empresa)
    assert "Odoo caído" in res["error"]


def test_sync_empresa_inexistente_no_rompe():
    res = sync_cxc_lubrikca("00000000-0000-0000-0000-000000000000")
    assert "error" in res
