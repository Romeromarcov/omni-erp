"""Aislamiento multi-tenant (R-CODE-1) de la config del motor CxC Lubrikca."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.cxc_lubrikca.models import DescuentoMarcaCategoria, MetodoPago

pytestmark = [pytest.mark.django_db, pytest.mark.tenant]

BASE = "/api/cxc-lubrikca"


def test_listado_no_filtra_filas_de_otra_empresa(client_a, empresa_b):
    DescuentoMarcaCategoria.objects.create(
        empresa=empresa_b,
        marca="Ajena",
        categoria="*",
        porcentaje=Decimal("0.10"),
        vigencia_desde=date(2026, 1, 1),
    )
    r = client_a.get(f"{BASE}/descuentos-marca-categoria/")
    assert r.status_code == 200
    assert r.data["results"] == [] or all(
        row["marca"] != "Ajena" for row in r.data["results"]
    )


def test_retrieve_de_otra_empresa_da_404(client_a, empresa_b):
    ajeno = DescuentoMarcaCategoria.objects.create(
        empresa=empresa_b,
        marca="Ajena",
        categoria="*",
        porcentaje=Decimal("0.10"),
        vigencia_desde=date(2026, 1, 1),
    )
    r = client_a.get(f"{BASE}/descuentos-marca-categoria/{ajeno.id}/")
    assert r.status_code == 404


def test_create_fuerza_empresa_del_usuario(client_a, user_a, empresa_b):
    # Aunque el cliente intente fijar empresa, se ignora (read-only) y se usa la suya.
    payload = {
        "marca": "Sinoco",
        "categoria": "*",
        "tipo_descuento": "contado",
        "porcentaje": "0.030000",
        "vigencia_desde": "2026-01-01",
        "empresa": str(empresa_b.id_empresa),
    }
    r = client_a.post(f"{BASE}/descuentos-marca-categoria/", payload, format="json")
    assert r.status_code == 201, r.content
    obj = DescuentoMarcaCategoria.objects.get(id=r.data["id"])
    # La empresa asignada es la del usuario A, NO la empresa_b inyectada.
    assert obj.empresa_id != empresa_b.id_empresa
    assert obj.empresa in user_a.empresas.all()


def test_patch_de_otra_empresa_da_404(client_a, empresa_b):
    """Un tenant no puede MUTAR (PATCH) una fila de otra empresa: 404."""
    ajeno = DescuentoMarcaCategoria.objects.create(
        empresa=empresa_b,
        marca="Ajena",
        categoria="*",
        porcentaje=Decimal("0.10"),
        vigencia_desde=date(2026, 1, 1),
    )
    r = client_a.patch(
        f"{BASE}/descuentos-marca-categoria/{ajeno.id}/",
        {"porcentaje": "0.000000"},
        format="json",
    )
    assert r.status_code == 404
    ajeno.refresh_from_db()
    assert ajeno.porcentaje == Decimal("0.10")  # intacto


def test_create_sin_empresa_da_403():
    """Usuario sin empresa visible → PermissionDenied (403), no IntegrityError."""
    from rest_framework.test import APIClient

    from tests.factories import UsuariosFactory

    user = UsuariosFactory()  # sin empresa asociada
    client = APIClient()
    client.force_authenticate(user=user)
    r = client.post(
        f"{BASE}/metodos-pago/",
        {"codigo": "X", "nombre": "X", "moneda": "USD", "tipo_tasa": "N_A"},
        format="json",
    )
    assert r.status_code == 403


def test_metodo_pago_aislado_entre_empresas(client_a, client_b):
    # Cada cliente crea su método; ninguno ve el del otro.
    r_a = client_a.post(
        f"{BASE}/metodos-pago/",
        {"codigo": "ZELLE", "nombre": "Zelle A", "moneda": "USD", "tipo_tasa": "N_A"},
        format="json",
    )
    assert r_a.status_code == 201, r_a.content
    r_b = client_b.post(
        f"{BASE}/metodos-pago/",
        {"codigo": "ZELLE", "nombre": "Zelle B", "moneda": "USD", "tipo_tasa": "N_A"},
        format="json",
    )
    assert r_b.status_code == 201, r_b.content

    list_a = client_a.get(f"{BASE}/metodos-pago/")
    nombres_a = [row["nombre"] for row in list_a.data["results"]]
    assert "Zelle A" in nombres_a
    assert "Zelle B" not in nombres_a
    assert MetodoPago.objects.count() == 2
