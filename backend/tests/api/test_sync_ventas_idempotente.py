"""Replay idempotente de ventas POS creadas offline — CTF-008 Nivel 2.

La estrategia de escritura offline para ventas POS NO necesita un endpoint de
sync nuevo: el alta `POST /api/ventas/notas-venta/` ya es idempotente
(`IdempotentCreateMixin`, scope ``ventas:nota-venta-create``) y el POS ya envía
`Idempotency-Key`. El outbox del cliente, al reconectar, reenvía la MISMA
petición y el backend deduplica por (empresa, usuario, scope, clave) — sin
duplicar la venta ni sus efectos.

Estos tests fijan esa garantía (antes solo estaba cubierta para Pago y Abono).
"""
import pytest

pytestmark = pytest.mark.django_db

URL = "/api/ventas/notas-venta/"


@pytest.fixture
def cliente_a(db, empresa_a):
    from apps.crm.models import Cliente

    return Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Consumidor Final", rif="V-00000000-0"
    )


def _payload(cliente, numero="NV-SYNC-1"):
    return {
        "id_cliente": str(cliente.id_cliente),
        "numero_nota": numero,
        "fecha_nota": "2026-06-18",
        "estado": "BORRADOR",
    }


def _count(empresa):
    from apps.ventas.models import NotaVenta

    return NotaVenta.objects.filter(id_empresa=empresa).count()


def test_replay_misma_clave_no_duplica_venta(client_a, empresa_a, cliente_a):
    """Reenviar la misma venta con la misma Idempotency-Key (replay del outbox)
    no crea una segunda nota y devuelve la respuesta cacheada (mismo id)."""
    payload = _payload(cliente_a)
    headers = {"HTTP_IDEMPOTENCY_KEY": "venta-offline-1"}

    r1 = client_a.post(URL, payload, format="json", **headers)
    assert r1.status_code == 201, r1.data
    r2 = client_a.post(URL, payload, format="json", **headers)
    assert r2.status_code == 201, r2.data

    assert r1.data["id_nota_venta"] == r2.data["id_nota_venta"]
    assert _count(empresa_a) == 1


def test_misma_clave_payload_distinto_rechaza(client_a, empresa_a, cliente_a):
    """Misma clave con payload distinto = conflicto (no se cuela otra venta)."""
    headers = {"HTTP_IDEMPOTENCY_KEY": "venta-offline-2"}
    r1 = client_a.post(URL, _payload(cliente_a, "NV-SYNC-2"), format="json", **headers)
    assert r1.status_code == 201, r1.data
    r2 = client_a.post(URL, _payload(cliente_a, "NV-SYNC-2-bis"), format="json", **headers)
    assert r2.status_code == 422
    assert _count(empresa_a) == 1


def test_sin_clave_no_deduplica(client_a, empresa_a, cliente_a):
    """Sin Idempotency-Key, dos altas distintas crean dos notas (no hay magia)."""
    assert client_a.post(URL, _payload(cliente_a, "NV-SYNC-3"), format="json").status_code == 201
    assert client_a.post(URL, _payload(cliente_a, "NV-SYNC-4"), format="json").status_code == 201
    assert _count(empresa_a) == 2


def test_replay_aislado_por_tenant(client_a, client_b, empresa_a, empresa_b, cliente_a):
    """La misma clave en otra empresa NO colisiona (scope multi-tenant)."""
    from apps.crm.models import Cliente

    cliente_b = Cliente.objects.create(
        id_empresa=empresa_b, razon_social="Consumidor B", rif="V-11111111-1"
    )
    headers = {"HTTP_IDEMPOTENCY_KEY": "misma-clave"}
    ra = client_a.post(URL, _payload(cliente_a, "NV-A"), format="json", **headers)
    rb = client_b.post(URL, _payload(cliente_b, "NV-B"), format="json", **headers)
    assert ra.status_code == 201, ra.data
    assert rb.status_code == 201, rb.data
    assert ra.data["id_nota_venta"] != rb.data["id_nota_venta"]
    assert _count(empresa_a) == 1
    assert _count(empresa_b) == 1
