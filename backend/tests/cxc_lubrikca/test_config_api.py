"""Tests de CRUD por API de la configuración del motor (Fase 1).

Cubre 3 modelos representativos vía ``client_a``: DescuentoMarcaCategoria,
ReglaRecurrencia, Feriado. Verifica list/create/retrieve/update/soft-delete y
las validaciones de serializer.
"""

from __future__ import annotations

import pytest

from apps.cxc_lubrikca.models import DescuentoMarcaCategoria, Feriado, ReglaRecurrencia

pytestmark = pytest.mark.django_db

BASE = "/api/cxc-lubrikca"


def test_health_endpoint(client_a):
    r = client_a.get(f"{BASE}/health/")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "modulo": "cxc_lubrikca"}


def test_bcv_completo_create_ok(client_a):
    url = f"{BASE}/descuentos-bcv-completo/"
    r = client_a.post(
        url,
        {"porcentaje": "0.020000", "vigencia_desde": "2026-01-01"},
        format="json",
    )
    assert r.status_code == 201, r.content
    assert r.data["porcentaje"] == "0.020000"


def test_bcv_completo_rechaza_porcentaje_negativo(client_a):
    url = f"{BASE}/descuentos-bcv-completo/"
    r = client_a.post(
        url,
        {"porcentaje": "-0.010000", "vigencia_desde": "2026-01-01"},
        format="json",
    )
    assert r.status_code == 400
    assert "porcentaje" in r.data


# --- DescuentoMarcaCategoria -------------------------------------------------
def test_descuento_crud_completo(client_a):
    url = f"{BASE}/descuentos-marca-categoria/"
    payload = {
        "marca": "Sinoco",
        "categoria": "*",
        "tipo_descuento": "contado",
        "porcentaje": "0.030000",
        "vigencia_desde": "2026-01-01",
    }
    # create 201
    r = client_a.post(url, payload, format="json")
    assert r.status_code == 201, r.content
    obj_id = r.data["id"]

    # list 200 contiene el objeto
    r = client_a.get(url)
    assert r.status_code == 200
    ids = [row["id"] for row in r.data["results"]]
    assert obj_id in ids

    # retrieve
    r = client_a.get(f"{url}{obj_id}/")
    assert r.status_code == 200
    assert r.data["marca"] == "Sinoco"

    # patch
    r = client_a.patch(f"{url}{obj_id}/", {"porcentaje": "0.050000"}, format="json")
    assert r.status_code == 200
    assert r.data["porcentaje"] == "0.050000"

    # soft-delete vía DELETE → deleted_at set, fuera del listado
    r = client_a.delete(f"{url}{obj_id}/")
    assert r.status_code == 204
    obj = DescuentoMarcaCategoria.objects.get(id=obj_id)
    assert obj.deleted_at is not None
    r = client_a.get(url)
    assert obj_id not in [row["id"] for row in r.data["results"]]
    # tras soft-delete, ya no es accesible por retrieve
    assert client_a.get(f"{url}{obj_id}/").status_code == 404


def test_descuento_rechaza_porcentaje_negativo(client_a):
    url = f"{BASE}/descuentos-marca-categoria/"
    payload = {
        "marca": "Sinoco",
        "categoria": "*",
        "tipo_descuento": "contado",
        "porcentaje": "-0.010000",
        "vigencia_desde": "2026-01-01",
    }
    r = client_a.post(url, payload, format="json")
    assert r.status_code == 400
    assert "porcentaje" in r.data


def test_descuento_rechaza_vigencia_invertida(client_a):
    url = f"{BASE}/descuentos-marca-categoria/"
    payload = {
        "marca": "Sinoco",
        "categoria": "*",
        "tipo_descuento": "contado",
        "porcentaje": "0.030000",
        "vigencia_desde": "2026-06-01",
        "vigencia_hasta": "2026-01-01",
    }
    r = client_a.post(url, payload, format="json")
    assert r.status_code == 400
    assert "vigencia_hasta" in r.data


# --- ReglaRecurrencia --------------------------------------------------------
def test_recurrencia_crud_completo(client_a):
    url = f"{BASE}/reglas-recurrencia/"
    payload = {
        "condicion": "recompra",
        "tipo_beneficio": "porcentaje",
        "valor": "0.040000",
        "vigencia_desde": "2026-01-01",
    }
    r = client_a.post(url, payload, format="json")
    assert r.status_code == 201, r.content
    obj_id = r.data["id"]

    r = client_a.get(url)
    assert r.status_code == 200
    assert obj_id in [row["id"] for row in r.data["results"]]

    r = client_a.get(f"{url}{obj_id}/")
    assert r.status_code == 200
    assert r.data["condicion"] == "recompra"

    r = client_a.patch(f"{url}{obj_id}/", {"valor": "0.060000"}, format="json")
    assert r.status_code == 200
    assert r.data["valor"] == "0.060000"

    r = client_a.delete(f"{url}{obj_id}/")
    assert r.status_code == 204
    assert ReglaRecurrencia.objects.get(id=obj_id).deleted_at is not None


def test_recurrencia_rechaza_valor_negativo(client_a):
    url = f"{BASE}/reglas-recurrencia/"
    r = client_a.post(
        url,
        {
            "condicion": "recompra",
            "tipo_beneficio": "porcentaje",
            "valor": "-0.010000",
            "vigencia_desde": "2026-01-01",
        },
        format="json",
    )
    assert r.status_code == 400
    assert "valor" in r.data


# --- Feriado -----------------------------------------------------------------
def test_feriado_crud_completo(client_a):
    url = f"{BASE}/feriados/"
    payload = {
        "fecha": "2026-06-08",
        "descripcion": "Feriado de prueba",
        "tipo": "nacional",
    }
    r = client_a.post(url, payload, format="json")
    assert r.status_code == 201, r.content
    obj_id = r.data["id"]

    r = client_a.get(url)
    assert r.status_code == 200
    assert obj_id in [row["id"] for row in r.data["results"]]

    r = client_a.get(f"{url}{obj_id}/")
    assert r.status_code == 200
    assert r.data["descripcion"] == "Feriado de prueba"

    r = client_a.put(
        f"{url}{obj_id}/",
        {"fecha": "2026-06-08", "descripcion": "Actualizado", "tipo": "bancario"},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["descripcion"] == "Actualizado"
    assert r.data["tipo"] == "bancario"

    r = client_a.delete(f"{url}{obj_id}/")
    assert r.status_code == 204
    assert Feriado.objects.get(id=obj_id).deleted_at is not None
