"""
GenericRestConnector (Fase 3) — conector genérico REST configurado por datos,
conectado vía el registry dinámico (ConectorProveedor.clase_conector).

El HTTP (httpx.get) se mockea: no hay red en los tests.
"""

import httpx
import pytest

from apps.integration_hub.connectors.base import (
    ConnectorConnectionError,
    ConnectorNotSupportedError,
)
from apps.integration_hub.connectors.generico.connector import GenericRestConnector
from apps.integration_hub.connectors.registry import registry
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor

pytestmark = pytest.mark.django_db

_CLASE = "apps.integration_hub.connectors.generico.connector.GenericRestConnector"


class _FakeResp:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


def _fake_get(json_data, status=200, capture=None):
    def _get(url, **kwargs):
        if capture is not None:
            capture["url"] = url
            capture["kwargs"] = kwargs
        return _FakeResp(json_data, status)
    return _get


def _instancia(empresa, configuracion, codigo="erp_generico_test"):
    proveedor = ConectorProveedor.objects.create(
        codigo=codigo,
        nombre="ERP Genérico",
        capacidades=["contactos", "productos"],
        clase_conector=_CLASE,
    )
    return ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=proveedor,
        nombre="Inst genérica",
        configuracion=configuracion,
        estado="activo",
        entidades_activas=["contactos"],
    )


_CONFIG = {
    "base_url": "https://api.ext.test/",
    "headers": {"Authorization": "Bearer SECRETO-123"},
    "entidades": {
        "contactos": {
            "endpoint": "/clientes",
            "raiz": "data",
            "mapa": {
                "id_externo": "id",
                "nombre": "razon_social",
                "email": "correo",
                "identificador_fiscal": "rif",
                "es_cliente": "es_cliente",
            },
        },
        "productos": {
            "endpoint": "/productos",
            "mapa": {
                "id_externo": "id",
                "nombre": "titulo",
                "precio_venta": "precio",
                "codigo_interno": "sku",
            },
        },
    },
}


class TestGenericRestConnector:
    def test_pull_contactos_mapea_y_extrae_raiz(self, empresa_a, monkeypatch):
        payload = {"data": [
            {"id": 7, "razon_social": "ACME C.A.", "correo": "a@acme.test",
             "rif": "J-123", "es_cliente": True},
        ]}
        monkeypatch.setattr(httpx, "get", _fake_get(payload))
        conn = GenericRestConnector(_instancia(empresa_a, _CONFIG))

        out = conn.pull_contactos()

        assert len(out) == 1
        c = out[0]
        assert c["id_externo"] == "7"
        assert c["nombre"] == "ACME C.A."
        assert c["email"] == "a@acme.test"
        assert c["identificador_fiscal"] == "J-123"
        assert c["es_cliente"] is True
        assert c["_fuente"] == "generic_rest"
        assert c["_checksum"]  # checksum presente para dedup

    def test_pull_productos_lista_directa(self, empresa_a, monkeypatch):
        payload = [{"id": 1, "titulo": "Widget", "precio": "12.50", "sku": "W-1"}]
        monkeypatch.setattr(httpx, "get", _fake_get(payload))
        conn = GenericRestConnector(_instancia(empresa_a, _CONFIG))

        out = conn.pull_productos()
        assert out[0]["id_externo"] == "1"
        assert out[0]["nombre"] == "Widget"
        assert out[0]["precio_venta"] == "12.50"
        assert out[0]["codigo_interno"] == "W-1"

    def test_limite_recorta(self, empresa_a, monkeypatch):
        payload = [{"id": i, "titulo": f"P{i}", "precio": "1", "sku": f"S{i}"} for i in range(5)]
        monkeypatch.setattr(httpx, "get", _fake_get(payload))
        conn = GenericRestConnector(_instancia(empresa_a, _CONFIG))
        assert len(conn.pull_productos(limite=2)) == 2

    def test_supports_segun_config(self, empresa_a):
        conn = GenericRestConnector(_instancia(empresa_a, _CONFIG))
        assert conn.supports("contactos") is True
        assert conn.supports("productos") is True
        assert conn.supports("pedidos_venta") is False  # no configurada

    def test_entidad_no_configurada_lanza(self, empresa_a, monkeypatch):
        cfg = {"base_url": "https://api.ext.test", "entidades": {}}
        conn = GenericRestConnector(_instancia(empresa_a, cfg))
        with pytest.raises(ConnectorNotSupportedError, match="no tiene configurada"):
            conn.pull_contactos()

    def test_sin_base_url_lanza_connection_error(self, empresa_a):
        cfg = {"entidades": {"contactos": {"endpoint": "/x", "mapa": {}}}}
        conn = GenericRestConnector(_instancia(empresa_a, cfg))
        with pytest.raises(ConnectorConnectionError, match="base_url"):
            conn.pull_contactos()

    def test_http_error_no_filtra_secretos(self, empresa_a, monkeypatch):
        # Un 500 debe dar ConnectorConnectionError SIN exponer el token de auth.
        monkeypatch.setattr(httpx, "get", _fake_get({}, status=500))
        conn = GenericRestConnector(_instancia(empresa_a, _CONFIG))
        with pytest.raises(ConnectorConnectionError) as exc:
            conn.pull_contactos()
        assert "SECRETO-123" not in str(exc.value)
        assert "500" in str(exc.value)

    def test_test_connection_ok_y_fallo(self, empresa_a, monkeypatch):
        cfg = dict(_CONFIG, test_endpoint="/health")
        conn = GenericRestConnector(_instancia(empresa_a, cfg))

        monkeypatch.setattr(httpx, "get", _fake_get({"ok": True}))
        assert conn.test_connection().success is True

        monkeypatch.setattr(httpx, "get", _fake_get({}, status=503))
        res = conn.test_connection()
        assert res.success is False
        assert "SECRETO-123" not in res.message

    def test_se_resuelve_via_registry_dinamico(self, empresa_a):
        # End-to-end con #189: el registry carga la clase desde clase_conector.
        codigo = "erp_generico_registry_test"
        try:
            inst = _instancia(empresa_a, _CONFIG, codigo=codigo)
            conn = registry.get_connector(inst)
            assert isinstance(conn, GenericRestConnector)
        finally:
            registry._registry.pop(codigo, None)

    def test_version_info(self, empresa_a):
        conn = GenericRestConnector(_instancia(empresa_a, _CONFIG))
        info = conn.get_version_info()
        assert info["provider"] == "generic_rest"
        assert info["base_url_configurado"] is True
        assert info["entidades"] == ["contactos", "productos"]
