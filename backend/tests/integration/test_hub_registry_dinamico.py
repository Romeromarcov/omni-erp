"""
Carga dinámica de conectores (Fase 3) — ``ConnectorRegistry`` resuelve la clase
del conector desde ``ConectorProveedor.clase_conector`` (ruta dotted) sin
re-desplegar. Permite añadir proveedores o reutilizar un conector genérico
configurando una fila del catálogo.
"""

import pytest

from apps.integration_hub.connectors.base import ConnectorError
from apps.integration_hub.connectors.odoo.connector import OdooConnector
from apps.integration_hub.connectors.registry import registry
from apps.integration_hub.models import ConectorInstancia, ConectorProveedor

pytestmark = pytest.mark.django_db

_ODOO_PATH = "apps.integration_hub.connectors.odoo.connector.OdooConnector"


def _instancia(empresa, codigo, clase_conector=""):
    proveedor = ConectorProveedor.objects.create(
        codigo=codigo,
        nombre=f"Prov {codigo}",
        capacidades=["contactos"],
        clase_conector=clase_conector,
    )
    return ConectorInstancia.objects.create(
        id_empresa=empresa,
        id_proveedor=proveedor,
        nombre=f"Inst {codigo}",
        configuracion={"host": "x.local"},
        estado="activo",
        entidades_activas=["contactos"],
    )


class TestRegistryDinamico:
    def test_carga_clase_desde_clase_conector(self, empresa_a):
        codigo = "odoo_dinamico_test"
        try:
            inst = _instancia(empresa_a, codigo, _ODOO_PATH)
            conector = registry.get_connector(inst)
            assert isinstance(conector, OdooConnector)
            assert codigo in registry.list_registered()  # quedó cacheado
        finally:
            registry._registry.pop(codigo, None)

    def test_segunda_llamada_usa_cache(self, empresa_a):
        codigo = "odoo_cache_test"
        try:
            inst = _instancia(empresa_a, codigo, _ODOO_PATH)
            registry.get_connector(inst)
            # Ya cacheado: aunque la ruta cambie a una inválida, no se re-importa.
            inst.id_proveedor.clase_conector = "ruta.que.no.existe.Cls"
            inst.id_proveedor.save()
            conector = registry.get_connector(inst)
            assert isinstance(conector, OdooConnector)
        finally:
            registry._registry.pop(codigo, None)

    def test_sin_clase_ni_registro_estatico_lanza_error(self, empresa_a):
        codigo = "proveedor_sin_clase_test"
        inst = _instancia(empresa_a, codigo, clase_conector="")
        with pytest.raises(ConnectorError, match="No hay conector registrado"):
            registry.get_connector(inst)
        assert codigo not in registry.list_registered()

    def test_ruta_invalida_lanza_error_y_no_cachea(self, empresa_a):
        codigo = "proveedor_ruta_mala_test"
        try:
            inst = _instancia(empresa_a, codigo, "apps.integration_hub.no_existe.Clase")
            with pytest.raises(ConnectorError, match="No se pudo importar"):
                registry.get_connector(inst)
            assert codigo not in registry.list_registered()
        finally:
            registry._registry.pop(codigo, None)

    def test_clase_no_es_baseconnector_lanza_error(self, empresa_a):
        codigo = "proveedor_clase_mala_test"
        try:
            # Apunta a un modelo (no es BaseConnector) → error claro.
            inst = _instancia(
                empresa_a, codigo, "apps.integration_hub.models.ConectorProveedor"
            )
            with pytest.raises(ConnectorError, match="no es un BaseConnector"):
                registry.get_connector(inst)
            assert codigo not in registry.list_registered()
        finally:
            registry._registry.pop(codigo, None)

    def test_registro_estatico_tiene_prioridad_sobre_clase_conector(self, empresa_a):
        # 'odoo' está registrado estáticamente (apps.py) y sembrado en el catálogo.
        # Aunque su clase_conector apunte a una ruta inválida, gana el registro
        # estático: no se intenta importar (no lanza) y devuelve el OdooConnector.
        proveedor = ConectorProveedor.objects.get(codigo="odoo")
        proveedor.clase_conector = "ruta.invalida.Cls"
        proveedor.save()
        inst = ConectorInstancia.objects.create(
            id_empresa=empresa_a,
            id_proveedor=proveedor,
            nombre="Inst odoo estático",
            configuracion={"host": "x.local"},
            estado="activo",
            entidades_activas=["contactos"],
        )
        conector = registry.get_connector(inst)
        assert isinstance(conector, OdooConnector)
