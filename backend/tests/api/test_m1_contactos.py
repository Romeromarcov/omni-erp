"""
Tests for M1 — Contactos Unificados (DoD).

DoD requirements verified here:
  - Contacto model with multi-role support
  - Strangler fig: Cliente and Proveedor have FK to Contacto
  - MCP tool omni_buscar_contacto
  - Tests for multi-role, RIF search, isolation
"""

import pytest
from rest_framework.test import APIClient


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def capability_token(db, empresa_a):
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.models import CapabilityToken

    return CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="Token test m1",
        scopes=["*"],
        expires_at=timezone.now() + timedelta(hours=1),
    )


# ── Multi-role ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_contacto_puede_ser_cliente_y_proveedor(empresa_a):
    """Un Contacto puede tener es_cliente=True y es_proveedor=True simultáneamente."""
    from apps.core.models import Contacto

    contacto = Contacto.objects.create(
        id_empresa=empresa_a,
        tipo_persona="JURIDICA",
        nombre="Empresa Dual",
        rif="J-11111111",
        es_cliente=True,
        es_proveedor=True,
    )

    assert contacto.es_cliente is True
    assert contacto.es_proveedor is True
    assert contacto.es_empleado is False
    assert contacto.es_usuario is False


@pytest.mark.django_db
def test_contacto_cliente_y_proveedor_en_modelos_legacy(empresa_a):
    """Strangler fig: Cliente y Proveedor pueden enlazarse a un Contacto unificado."""
    from apps.core.models import Contacto
    from apps.crm.models import Cliente
    from apps.proveedores.models import Proveedor

    contacto = Contacto.objects.create(
        id_empresa=empresa_a,
        tipo_persona="JURIDICA",
        nombre="Empresa Dual Legacy",
        rif="J-22222222",
        es_cliente=True,
        es_proveedor=True,
    )

    cliente = Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Empresa Dual Legacy",
        rif="J-22222222",
        tipo_cliente="CONTADO",
        contacto=contacto,
    )
    proveedor = Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Empresa Dual Legacy",
        rif="J-22222222",
        contacto=contacto,
    )

    # Verificar relaciones inversas (strangler fig)
    assert cliente.contacto == contacto
    assert proveedor.contacto == contacto
    assert contacto.cliente == cliente
    assert contacto.proveedor == proveedor


# ── RIF search ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_buscar_contacto_por_rif(empresa_a, user_a):
    """GET /api/core/contactos/?search=J-12345678-9 retorna el contacto correcto."""
    from apps.core.models import Contacto

    Contacto.objects.create(
        id_empresa=empresa_a,
        nombre="Cliente RIF",
        rif="J-12345678-9",
        es_cliente=True,
    )
    # Another contact with different RIF — should NOT appear
    Contacto.objects.create(
        id_empresa=empresa_a,
        nombre="Otro Cliente",
        rif="J-99999999-1",
        es_cliente=True,
    )

    client = APIClient()
    client.force_authenticate(user=user_a)
    resp = client.get("/api/core/contactos/?search=J-12345678-9")

    assert resp.status_code == 200
    assert resp.data["count"] >= 1
    rifs = [r["rif"] for r in resp.data["results"]]
    assert "J-12345678-9" in rifs
    assert "J-99999999-1" not in rifs


@pytest.mark.django_db
def test_buscar_contacto_por_rif_via_mcp(empresa_a, capability_token):
    """omni_buscar_contacto filtra por RIF correctamente."""
    from apps.core.models import Contacto
    from apps.core.mcp_server import omni_buscar_contacto

    c = Contacto.objects.create(
        id_empresa=empresa_a,
        nombre="Proveedor MCP",
        rif="V-12345678",
        es_proveedor=True,
    )

    resultado = omni_buscar_contacto(
        capability_token=str(capability_token.token),
        empresa_id=str(empresa_a.id_empresa),
        query="V-12345678",
    )

    ids = [r["id_contacto"] for r in resultado]
    assert str(c.id_contacto) in ids


# ── Isolation ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_aislamiento_contacto(empresa_a, empresa_b, user_a, user_b):
    """user_a no puede ver los contactos de empresa_b vía la API."""
    from apps.core.models import Contacto

    c_a = Contacto.objects.create(
        id_empresa=empresa_a, nombre="Contacto A", rif="J-11111111"
    )
    c_b = Contacto.objects.create(
        id_empresa=empresa_b, nombre="Contacto B", rif="J-22222222"
    )

    client = APIClient()
    client.force_authenticate(user=user_a)
    resp = client.get("/api/core/contactos/")

    assert resp.status_code == 200
    ids_retornados = [r["id_contacto"] for r in resp.data["results"]]

    assert str(c_a.id_contacto) in ids_retornados
    assert str(c_b.id_contacto) not in ids_retornados


@pytest.mark.django_db
def test_aislamiento_contacto_via_mcp(empresa_a, empresa_b, capability_token):
    """omni_buscar_contacto nunca retorna contactos de otro tenant."""
    from apps.core.models import Contacto
    from apps.core.mcp_server import omni_buscar_contacto

    c_a = Contacto.objects.create(
        id_empresa=empresa_a, nombre="Contacto Alpha", rif="J-11111111"
    )
    # Mismo nombre en empresa_b — no debe aparecer en búsqueda de empresa_a
    Contacto.objects.create(
        id_empresa=empresa_b, nombre="Contacto Alpha", rif="J-99999999"
    )

    resultado = omni_buscar_contacto(
        capability_token=str(capability_token.token),
        empresa_id=str(empresa_a.id_empresa),
        query="Alpha",
    )

    ids = [r["id_contacto"] for r in resultado]
    assert str(c_a.id_contacto) in ids
    # All returned contacts must belong to empresa_a
    for r in resultado:
        assert r["id_contacto"] == str(c_a.id_contacto)


@pytest.mark.django_db
def test_aislamiento_mcp_token_otra_empresa(empresa_a, empresa_b, capability_token):
    """omni_buscar_contacto lanza PermissionError si empresa_id no coincide con token."""
    from apps.core.mcp_server import omni_buscar_contacto

    with pytest.raises(PermissionError):
        omni_buscar_contacto(
            capability_token=str(capability_token.token),
            empresa_id=str(empresa_b.id_empresa),
            query="",
        )
