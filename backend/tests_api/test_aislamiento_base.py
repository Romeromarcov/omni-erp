"""
Tests de aislamiento multi-tenant — base mínima (R-CODE-1).

Estos tests verifican la regla más importante del sistema:
un usuario autenticado en Empresa A NUNCA puede ver ni modificar
datos de Empresa B.

Si alguno de estos tests falla, hay un leak de datos entre tenants.
"""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from apps.crm.models import Cliente


URL_CLIENTES = "/api/crm/clientes/"


@pytest.fixture
def cliente_a(db, empresa_a):
    """Cliente perteneciente a Empresa A."""
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente de Alpha S.A.",
        rif="J-11111111-1",
    )


@pytest.fixture
def cliente_b(db, empresa_b):
    """Cliente perteneciente a Empresa B."""
    return Cliente.objects.create(
        id_empresa=empresa_b,
        razon_social="Cliente de Beta C.A.",
        rif="J-22222222-2",
    )


@pytest.mark.django_db
class TestAislamientoClientes:
    """
    Plantilla de aislamiento multi-tenant para el modelo Cliente (crm).
    Ref: skill omni-multi-tenant-isolation, sección 'Tests de aislamiento obligatorios'.
    """

    def test_listado_solo_devuelve_clientes_de_empresa_propia(
        self, user_a, user_b, cliente_a, cliente_b
    ):
        """
        Usuario A lista clientes → solo ve el cliente de su empresa.
        No debe ver el cliente de Empresa B aunque existe en la DB.
        """
        client = APIClient()
        client.force_authenticate(user=user_a)

        response = client.get(URL_CLIENTES)

        assert response.status_code == 200

        # Extraer IDs del listado (paginado o no)
        data = response.data
        if isinstance(data, dict) and "results" in data:
            resultados = data["results"]
        else:
            resultados = data

        ids_recibidos = {str(r["id_cliente"]) for r in resultados}

        assert str(cliente_a.id_cliente) in ids_recibidos, (
            "El cliente propio de Empresa A no aparece en el listado."
        )
        assert str(cliente_b.id_cliente) not in ids_recibidos, (
            "LEAK: el cliente de Empresa B aparece en el listado de Empresa A."
        )

    def test_get_cliente_de_otra_empresa_devuelve_404(
        self, user_a, cliente_a, cliente_b
    ):
        """
        Usuario A intenta obtener el detalle de un cliente de Empresa B → 404.
        No debe recibir 200 ni 403 (que revelaría que el objeto existe).
        """
        client = APIClient()
        client.force_authenticate(user=user_a)

        response = client.get(f"{URL_CLIENTES}{cliente_b.id_cliente}/")

        assert response.status_code == 404, (
            f"LEAK: usuario de Empresa A obtuvo status {response.status_code} "
            f"al acceder a cliente de Empresa B. Esperado: 404."
        )

    def test_patch_cliente_de_otra_empresa_devuelve_404(
        self, user_a, cliente_a, cliente_b
    ):
        """
        Usuario A intenta modificar un cliente de Empresa B → 404.
        El objeto no debe ser modificado y tampoco debe revelarse que existe.
        """
        client = APIClient()
        client.force_authenticate(user=user_a)

        response = client.patch(
            f"{URL_CLIENTES}{cliente_b.id_cliente}/",
            {"razon_social": "Hackeado"},
            format="json",
        )

        assert response.status_code == 404, (
            f"LEAK: usuario de Empresa A obtuvo status {response.status_code} "
            f"al intentar modificar cliente de Empresa B. Esperado: 404."
        )

        # Verificar que el objeto no fue modificado
        cliente_b.refresh_from_db()
        assert cliente_b.razon_social == "Cliente de Beta C.A.", (
            "CRÍTICO: el nombre del cliente de Empresa B fue modificado desde Empresa A."
        )
