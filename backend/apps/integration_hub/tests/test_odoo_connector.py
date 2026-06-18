"""
Tests del OdooConnector y OdooXMLRPCClient.

Los tests de conexión real se omiten en CI (requieren servidor Odoo real).
Los tests unitarios usan mocks para verificar la lógica de normalización.
"""
import pytest
from unittest.mock import MagicMock, patch


class TestOdooXMLRPCClient:
    """Tests del cliente XML-RPC de Odoo con mocks."""

    def _make_client(self):
        """Crea un OdooXMLRPCClient con autenticación mockeada."""
        from apps.integration_hub.connectors.odoo.client import OdooXMLRPCClient

        with patch("xmlrpc.client.ServerProxy") as mock_proxy:
            # Mockear common.authenticate
            mock_common = MagicMock()
            mock_common.authenticate.return_value = 1  # uid = 1
            mock_common.version.return_value = {"server_version": "17.0", "protocol_version": 1}

            mock_models = MagicMock()
            mock_proxy.side_effect = [mock_common, mock_models]

            client = OdooXMLRPCClient(
                host="test.odoo.com",
                db="testdb",
                user="admin@test.com",
                api_key="test_key_123",
            )
            client._models = mock_models
            return client, mock_models

    def test_autenticacion_exitosa(self):
        """El cliente se crea correctamente cuando la autenticación es exitosa."""
        from apps.integration_hub.connectors.odoo.client import OdooXMLRPCClient

        with patch("xmlrpc.client.ServerProxy") as mock_proxy:
            mock_common = MagicMock()
            mock_common.authenticate.return_value = 42
            mock_common.version.return_value = {"server_version": "18.0"}
            mock_models = MagicMock()
            mock_proxy.side_effect = [mock_common, mock_models]

            client = OdooXMLRPCClient("test.odoo.com", "db", "user@test.com", "key")
            assert client.uid == 42

    def test_autenticacion_fallida_lanza_error(self):
        """Si authenticate retorna None/False, debe lanzar OdooAuthError."""
        from apps.integration_hub.connectors.odoo.client import OdooAuthError, OdooXMLRPCClient

        with patch("xmlrpc.client.ServerProxy") as mock_proxy:
            mock_common = MagicMock()
            mock_common.authenticate.return_value = False  # login fallido
            mock_common.version.return_value = {}
            mock_models = MagicMock()
            mock_proxy.side_effect = [mock_common, mock_models]

            with pytest.raises(OdooAuthError):
                OdooXMLRPCClient("test.odoo.com", "db", "wrong@test.com", "wrong_key")

    def test_call_ejecuta_execute_kw(self):
        """call() debe invocar execute_kw con los parámetros correctos."""
        client, mock_models = self._make_client()

        mock_models.execute_kw.return_value = [{"id": 1, "name": "Test"}]

        result = client.call("sale.order", "search_read", [[["state", "=", "sale"]]])

        mock_models.execute_kw.assert_called_once()
        assert result == [{"id": 1, "name": "Test"}]

    def test_ping_retorna_true_cuando_conexion_ok(self):
        """ping() debe retornar True cuando la conexión responde."""
        client, mock_models = self._make_client()
        mock_models.execute_kw.return_value = 5  # count de idiomas

        assert client.ping() is True

    def test_ping_retorna_false_cuando_falla(self):
        """ping() debe retornar False si hay error de conexión."""
        client, mock_models = self._make_client()
        mock_models.execute_kw.side_effect = Exception("Connection refused")

        assert client.ping() is False


class TestNormalizeOdooHost:
    """Tests de normalize_odoo_host — saneo de la URL base de Odoo."""

    @pytest.mark.parametrize(
        "raw,esperado",
        [
            # Caso del bug real: el usuario pega la URL de login del navegador.
            (
                "https://lixie-dev-lubrika-qa-33433878.dev.odoo.com/en/web/login",
                "https://lixie-dev-lubrika-qa-33433878.dev.odoo.com",
            ),
            # Sin esquema → asume https.
            ("miempresa.odoo.com", "https://miempresa.odoo.com"),
            ("miempresa.odoo.com/en/web/login", "https://miempresa.odoo.com"),
            # Con query y fragmento.
            ("https://x.odoo.com/web/login?db=foo#bar", "https://x.odoo.com"),
            # Conserva puerto y esquema http (on-premise/local).
            ("http://localhost:8069/web", "http://localhost:8069"),
            # Quita la barra final.
            ("https://x.odoo.com/", "https://x.odoo.com"),
            # Ya estaba limpio: idempotente.
            ("https://x.odoo.com", "https://x.odoo.com"),
            # Espacios alrededor.
            ("  https://x.odoo.com/web  ", "https://x.odoo.com"),
            # Vacío.
            ("", ""),
        ],
    )
    def test_normaliza(self, raw, esperado):
        from apps.integration_hub.connectors.odoo.client import normalize_odoo_host

        assert normalize_odoo_host(raw) == esperado

    def test_construye_endpoint_xmlrpc_valido(self):
        """Con una URL de login pegada, el endpoint XML-RPC queda correcto."""
        from apps.integration_hub.connectors.odoo.client import OdooXMLRPCClient

        with patch("xmlrpc.client.ServerProxy") as mock_proxy:
            mock_common = MagicMock()
            mock_common.authenticate.return_value = 1
            mock_common.version.return_value = {"server_version": "17.0"}
            mock_proxy.side_effect = [mock_common, MagicMock()]

            client = OdooXMLRPCClient(
                host="https://x.odoo.com/en/web/login",
                db="db",
                user="u@x.com",
                api_key="k",
            )

            assert client._common_url == "https://x.odoo.com/xmlrpc/2/common"
            assert client._object_url == "https://x.odoo.com/xmlrpc/2/object"


class TestOdooConnectorNormalizacion:
    """Tests de las funciones de normalización del OdooConnector."""

    @pytest.fixture
    def connector(self, db):
        """Crea un OdooConnector con instancia mockeada."""
        from apps.integration_hub.connectors.odoo.connector import OdooConnector

        instancia = MagicMock()
        instancia.get_config.return_value = {
            "host": "test.odoo.com",
            "db": "testdb",
            "user": "admin@test.com",
            "api_key": "test_key",
        }
        instancia.id_proveedor.codigo = "odoo"
        return OdooConnector(instancia)

    def test_normalizar_contacto_socio_cliente(self, connector):
        """Normaliza correctamente un res.partner de cliente."""
        raw = {
            "id": 42,
            "name": "Distribuidora Los Andes",
            "email": "compras@losandes.com.ve",
            "phone": "0212-5551234",
            "mobile": "0414-5551234",
            "customer_rank": 5,
            "supplier_rank": 0,
            "company_type": "company",
            "vat": "J-12345678-9",
            "street": "Av. Principal",
            "city": "Caracas",
            "country_id": [240, "Venezuela"],
            "state_id": [135, "Distrito Capital"],
            "parent_id": False,
            "website": "https://losandes.com.ve",
            "comment": "Cliente preferencial",
            "active": True,
            "write_date": "2024-03-15 10:30:00",
            "create_date": "2023-01-01 09:00:00",
        }

        result = connector.normalizar_contacto(raw)

        assert result["id_externo"] == "42"
        assert result["nombre"] == "Distribuidora Los Andes"
        assert result["email"] == "compras@losandes.com.ve"
        assert result["es_cliente"] is True
        assert result["es_proveedor"] is False
        assert result["es_empresa"] is True
        assert result["identificador_fiscal"] == "J-12345678-9"
        assert result["ciudad"] == "Caracas"
        assert result["pais_nombre"] == "Venezuela"
        assert result["activo"] is True
        assert "_checksum" in result
        assert result["_fuente"] == "odoo"
        # Verificar que NO hay campos sensibles
        assert "api_key" not in result
        assert "password" not in result

    def test_normalizar_contacto_proveedor(self, connector):
        """Normaliza correctamente un res.partner de proveedor."""
        raw = {
            "id": 99,
            "name": "Proveedor XYZ",
            "email": "ventas@xyz.com",
            "phone": "0212-999",
            "mobile": "",
            "customer_rank": 0,
            "supplier_rank": 3,
            "company_type": "company",
            "vat": "J-99999999-9",
            "street": "Zona Industrial",
            "city": "Valencia",
            "country_id": [240, "Venezuela"],
            "state_id": [138, "Carabobo"],
            "parent_id": False,
            "website": "",
            "comment": "",
            "active": True,
            "write_date": "2024-04-01 12:00:00",
            "create_date": "2023-06-15 09:00:00",
        }

        result = connector.normalizar_contacto(raw)

        assert result["es_cliente"] is False
        assert result["es_proveedor"] is True

    def test_normalizar_producto(self, connector):
        """Normaliza correctamente un product.template de Odoo."""
        raw = {
            "id": 10,
            "name": "Silla Ejecutiva Ergonómica",
            "default_code": "SILLA-EXEC-001",
            "description_sale": "Silla ergonómica para oficina",
            "list_price": 450.00,
            "standard_price": 280.00,
            "categ_id": [3, "Muebles / Sillas"],
            "uom_id": [1, "Unidades"],
            "uom_po_id": [1, "Unidades"],
            "type": "product",
            "sale_ok": True,
            "purchase_ok": True,
            "active": True,
            "barcode": "7591234567890",
            "weight": 15.5,
            "volume": 0.8,
            "write_date": "2024-03-10 08:00:00",
            "create_date": "2023-02-20 10:00:00",
        }

        result = connector.normalizar_producto(raw)

        assert result["id_externo"] == "10"
        assert result["nombre"] == "Silla Ejecutiva Ergonómica"
        assert result["codigo_interno"] == "SILLA-EXEC-001"
        assert result["precio_venta"] == 450.00
        assert result["costo"] == 280.00
        assert result["tipo"] == "almacenable"
        assert result["categoria_nombre"] == "Muebles / Sillas"
        assert result["unidad_medida"] == "Unidades"
        assert result["codigo_barras"] == "7591234567890"
        assert result["_fuente"] == "odoo"

    def test_normalizar_pago_inbound(self, connector):
        """Normaliza correctamente un pago de cliente (inbound)."""
        raw = {
            "id": 55,
            "name": "PAGO/2024/00123",
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": [42, "Distribuidora Los Andes"],
            "amount": 1500.00,
            "date": "2024-03-20",
            "state": "paid",
            "journal_id": [7, "Banco Mercantil USD"],
            "currency_id": [2, "USD"],
            "memo": "Abono factura INV/2024/0045",
            "write_date": "2024-03-20 15:30:00",
            "create_date": "2024-03-20 14:00:00",
        }

        result = connector._normalizar_pago(raw)

        assert result["id_externo"] == "55"
        assert result["tipo"] == "inbound"
        assert result["monto"] == 1500.00
        assert result["moneda"] == "USD"
        assert result["socio_nombre"] == "Distribuidora Los Andes"
        assert result["referencia"] == "Abono factura INV/2024/0045"

    def test_checksum_identico_para_mismo_dato(self, connector):
        """El checksum debe ser idéntico para el mismo dict."""
        data = {"id": 1, "name": "Test", "amount": 100.0}
        assert connector._checksum(data) == connector._checksum(data)

    def test_checksum_distinto_para_datos_diferentes(self, connector):
        """El checksum debe cambiar si cambian los datos."""
        data1 = {"id": 1, "name": "Test", "amount": 100.0}
        data2 = {"id": 1, "name": "Test", "amount": 200.0}
        assert connector._checksum(data1) != connector._checksum(data2)

    def test_checksum_ignora_write_date(self, connector):
        """El checksum no debe cambiar si solo cambia write_date."""
        data1 = {"id": 1, "name": "Test", "write_date": "2024-01-01"}
        data2 = {"id": 1, "name": "Test", "write_date": "2024-12-31"}
        assert connector._checksum(data1) == connector._checksum(data2)


class TestOdooConnectorTestConnection:
    """Tests del método test_connection con mocks."""

    @pytest.fixture
    def connector(self):
        from apps.integration_hub.connectors.odoo.connector import OdooConnector

        instancia = MagicMock()
        instancia.get_config.return_value = {
            "host": "https://test.odoo.com",
            "db": "testdb",
            "user": "admin@test.com",
            "api_key": "test_key_secure_123",
        }
        instancia.id_proveedor.codigo = "odoo"
        return OdooConnector(instancia)

    def test_test_connection_exitoso(self, connector):
        """test_connection debe retornar success=True con servidor Odoo disponible."""
        mock_client = MagicMock()
        mock_client.get_version.return_value = {
            "server_version": "17.0",
            "server_version_info": [17, 0, 0, "final", 0],
            "protocol_version": 1,
        }
        mock_client.ping.return_value = True
        mock_client.call.return_value = 5  # res.lang count

        connector._client = mock_client

        result = connector.test_connection()

        assert result.success is True
        assert "17.0" in result.message
        assert result.version == "17.0"

    def test_test_connection_credenciales_incorrectas(self, connector):
        """test_connection debe retornar success=False con credenciales incorrectas."""
        from apps.integration_hub.connectors.base import ConnectorConnectionError

        with patch.object(connector, "_get_client", side_effect=ConnectorConnectionError("Credenciales inválidas")):
            result = connector.test_connection()

        assert result.success is False
        assert "Credenciales" in result.message
