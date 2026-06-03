"""
SEC-1 — El asistente IA opera sobre una empresa de trabajo VALIDADA por permisos.

Decisión de diseño: por defecto trabaja sobre la empresa activa que envía el cliente;
el usuario puede pedir cambiar a otra empresa SOLO si tiene permiso sobre ella
(get_empresas_visible). Antes, las herramientas usaban user.empresa (= empresas.first()),
que ignoraba el multi-empresa.
"""

import pytest

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.agentes.api import chat as chatmod
from tests_api.factories import ClienteFactory

pytestmark = pytest.mark.integration


@pytest.fixture
def user_ab(db, empresa_a, empresa_b):
    """Usuario con permiso sobre AMBAS empresas."""
    User = get_user_model()
    u = User.objects.create_user(
        username="user_ab_sec1", password="x", email="ab_sec1@x.com", is_active=True
    )
    u.empresas.add(empresa_a, empresa_b)
    return u


@pytest.mark.django_db
class TestChatEmpresaTrabajo:
    def test_tool_scoped_a_empresa_actual(self, user_ab, empresa_a, empresa_b):
        ClienteFactory(id_empresa=empresa_a, razon_social="Alpha Cliente Uno")
        ClienteFactory(id_empresa=empresa_b, razon_social="Beta Cliente Dos")
        ctx = chatmod._ChatCtx(user_ab, empresa_a, [empresa_a, empresa_b])

        r1 = chatmod._tool_buscar_cliente(ctx, termino="Cliente")
        assert {c["razon_social"] for c in r1["clientes"]} == {"Alpha Cliente Uno"}

    def test_usar_empresa_cambia_el_scope(self, user_ab, empresa_a, empresa_b):
        ClienteFactory(id_empresa=empresa_a, razon_social="Alpha Cliente Uno")
        ClienteFactory(id_empresa=empresa_b, razon_social="Beta Cliente Dos")
        ctx = chatmod._ChatCtx(user_ab, empresa_a, [empresa_a, empresa_b])

        sw = chatmod._tool_usar_empresa(ctx, empresa=str(empresa_b.id_empresa))
        assert sw.get("ok") is True
        r2 = chatmod._tool_buscar_cliente(ctx, termino="Cliente")
        assert {c["razon_social"] for c in r2["clientes"]} == {"Beta Cliente Dos"}

    def test_usar_empresa_por_nombre(self, user_ab, empresa_a, empresa_b):
        ctx = chatmod._ChatCtx(user_ab, empresa_a, [empresa_a, empresa_b])
        res = chatmod._tool_usar_empresa(ctx, empresa="Beta")  # nombre_legal "Empresa Beta C.A."
        assert res.get("ok") is True
        assert ctx.empresa == empresa_b

    def test_usar_empresa_rechaza_no_permitida(self, user_a, empresa_a, empresa_b):
        # user_a SOLO tiene empresa_a; no puede cambiar a empresa_b.
        ctx = chatmod._ChatCtx(user_a, empresa_a, [empresa_a])
        res = chatmod._tool_usar_empresa(ctx, empresa=str(empresa_b.id_empresa))
        assert "error" in res and "ok" not in res
        assert ctx.empresa == empresa_a

    def test_listar_empresas_solo_visibles(self, user_a, empresa_a, empresa_b):
        ctx = chatmod._ChatCtx(user_a, empresa_a, [empresa_a])
        res = chatmod._tool_listar_empresas(ctx)
        assert {e["id"] for e in res["empresas_disponibles"]} == {str(empresa_a.id_empresa)}

    def test_view_rechaza_empresa_sin_permiso(self, user_a, empresa_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        resp = client.post(
            reverse("asistente-chat"),
            {
                "messages": [{"role": "user", "content": "hola"}],
                "empresa_id": str(empresa_b.id_empresa),
            },
            format="json",
        )
        assert resp.status_code == 403
