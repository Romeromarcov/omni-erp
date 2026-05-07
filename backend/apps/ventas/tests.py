
import pytest
from rest_framework.test import APIClient
from django.urls import reverse
from apps.ventas.models import Pedido, DetallePedido, NotaVenta, DetalleNotaVenta
from apps.core.models import Empresa
from apps.crm.models import Cliente
import uuid
from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def empresa():
    return Empresa.objects.create(nombre_legal="Empresa Test", nombre_comercial="TestCom", identificador_fiscal="J123456789")

@pytest.fixture
def cliente(empresa):
    return Cliente.objects.create(
        id_empresa=empresa,
        razon_social="Cliente Test",
        nombre_comercial="ClienteCom",
        rif="V123456789"
    )

@pytest.fixture
def user(empresa):
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="testpass123", empresa=empresa)
    return user

def test_create_pedido(api_client, user, empresa, cliente):
    api_client.force_authenticate(user=user)
    url = reverse('pedido-list')
    data = {
        "id_empresa": empresa.id_empresa,
        "id_cliente": cliente.id_cliente,
        "numero_pedido": str(uuid.uuid4()),
        "fecha_pedido": "2024-06-01",
        "estado": "BORRADOR"
    }
    response = api_client.post(url, data, format='json')
    assert response.status_code == 201
    assert Pedido.objects.count() == 1

def test_create_detalle_pedido(api_client, user, empresa, cliente):
    from apps.inventario.models import Producto, CategoriaProducto, UnidadMedida
    from apps.finanzas.models import Moneda
    api_client.force_authenticate(user=user)
    pedido = Pedido.objects.create(id_empresa=empresa, id_cliente=cliente, numero_pedido=str(uuid.uuid4()), fecha_pedido="2024-06-01", estado="BORRADOR")
    # Crear dependencias mínimas para Producto
    categoria = CategoriaProducto.objects.create(id_empresa=empresa, nombre_categoria="General")
    unidad = UnidadMedida.objects.create(id_empresa=empresa, nombre_unidad="Unidad", abreviatura="u")
    moneda = Moneda.objects.create(id_empresa=empresa, nombre_moneda="Bolívar", codigo_moneda="VES", simbolo="Bs.")
    producto = Producto.objects.create(
        id_empresa=empresa,
        nombre_producto="Producto Test",
        sku="P001",
        id_categoria=categoria,
        id_unidad_medida_base=unidad,
        tipo_producto="PRODUCTO_FISICO",
        id_moneda_precio=moneda
    )
    url = reverse('detallepedido-list')
    data = {
        "id_pedido": pedido.id_pedido,
        "id_producto": producto.id_producto,
        "cantidad": 1,
        "precio_unitario": 10,
        "subtotal": 10
    }
    response = api_client.post(url, data, format='json')
    assert response.status_code == 201
