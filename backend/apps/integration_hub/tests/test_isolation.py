"""
Tests de aislamiento multi-tenant del Integration Hub.
R-CODE-1: Empresa A nunca ve datos de empresa B.
"""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.models import Empresa, Usuarios


@pytest.mark.django_db
class TestConectorInstanciaAislamiento:
    """
    Verifica que los conectores de una empresa no son visibles
    para otra empresa.
    """

    @pytest.fixture(autouse=True)
    def setup(self, db):
        from apps.integration_hub.models import ConectorInstancia, ConectorProveedor

        # Crear dos empresas
        self.empresa_a = Empresa.objects.create(nombre_legal="Empresa A")
        self.empresa_b = Empresa.objects.create(nombre_legal="Empresa B")

        # Crear usuarios para cada empresa
        self.user_a = Usuarios.objects.create_user(
            username="user_a@test.com",
            email="user_a@test.com",
            password="testpass123",
        )
        self.user_a.empresas.add(self.empresa_a)

        self.user_b = Usuarios.objects.create_user(
            username="user_b@test.com",
            email="user_b@test.com",
            password="testpass123",
        )
        self.user_b.empresas.add(self.empresa_b)

        # Crear un proveedor de prueba
        self.proveedor = ConectorProveedor.objects.create(
            codigo="test_proveedor",
            nombre="Test Proveedor",
            capacidades=["contactos"],
        )

        # Crear conector para empresa A
        self.conector_a = ConectorInstancia.objects.create(
            id_empresa=self.empresa_a,
            id_proveedor=self.proveedor,
            nombre="Conector de A",
            configuracion={"host": "a.test.com", "user": "a@test.com", "api_key": "key_a"},
            estado="activo",
        )

        # Crear conector para empresa B
        self.conector_b = ConectorInstancia.objects.create(
            id_empresa=self.empresa_b,
            id_proveedor=self.proveedor,
            nombre="Conector de B",
            configuracion={"host": "b.test.com", "user": "b@test.com", "api_key": "key_b"},
            estado="activo",
        )

        self.client_a = APIClient()
        self.client_a.force_authenticate(user=self.user_a)

        self.client_b = APIClient()
        self.client_b.force_authenticate(user=self.user_b)

    def test_usuario_a_solo_ve_sus_conectores(self):
        """Usuario A solo debe ver los conectores de empresa A."""
        response = self.client_a.get("/api/integration-hub/instancias/")
        assert response.status_code == 200

        ids = [str(c["id_conector"]) for c in response.data.get("results", response.data)]
        assert str(self.conector_a.id_conector) in ids
        assert str(self.conector_b.id_conector) not in ids

    def test_usuario_a_no_puede_ver_conector_de_b(self):
        """Usuario A debe recibir 404 al intentar acceder al conector de B."""
        response = self.client_a.get(
            f"/api/integration-hub/instancias/{self.conector_b.id_conector}/"
        )
        assert response.status_code == 404

    def test_usuario_b_no_puede_ver_conector_de_a(self):
        """Usuario B debe recibir 404 al intentar acceder al conector de A."""
        response = self.client_b.get(
            f"/api/integration-hub/instancias/{self.conector_a.id_conector}/"
        )
        assert response.status_code == 404

    def test_configuracion_no_expone_api_key(self):
        """
        La API nunca debe exponer el campo api_key en la configuración.
        R-CODE-8: sin secretos en respuestas.
        """
        response = self.client_a.get(
            f"/api/integration-hub/instancias/{self.conector_a.id_conector}/"
        )
        assert response.status_code == 200
        config_publica = response.data.get("configuracion_publica", {})
        assert "api_key" not in config_publica
        assert "password" not in config_publica

    def test_jobs_de_a_no_visibles_para_b(self):
        """Los jobs de sincronización de A no son visibles para B."""
        from apps.integration_hub.models import JobSincronizacion
        job_a = JobSincronizacion.objects.create(
            id_instancia=self.conector_a,
            tipo_entidad="contactos",
            estado="completado",
        )

        response = self.client_b.get("/api/integration-hub/jobs/")
        assert response.status_code == 200
        ids = [str(j["id_job"]) for j in response.data.get("results", response.data)]
        assert str(job_a.id_job) not in ids
