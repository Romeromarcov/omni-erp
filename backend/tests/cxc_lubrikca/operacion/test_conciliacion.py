"""Conciliación (Fase 4) — semáforo motor-vs-factura: servicio + API + tenant."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.cxc_lubrikca.models import (
    ConciliacionLubrikca,
    ConfiguracionConciliacion,
    PedidoLubrikca,
)
from apps.cxc_lubrikca.services.conciliacion import (
    ConciliacionError,
    conciliar_pedido,
    marcar_revisado,
    resumen_cartera,
)

from . import helpers as h

pytestmark = [pytest.mark.django_db, pytest.mark.tenant]

BASE = "/api/cxc-lubrikca"


# ---------------------------------------------------------------------------
# Servicio: semáforo verde / amarillo / rojo
# ---------------------------------------------------------------------------
_SO_SEQ = {"n": 0}


def _pedido_facturado(empresa, monto_facturado, total_motor="100", ncs="0"):
    _SO_SEQ["n"] += 1
    pedido = h.crear_pedido(
        empresa,
        so_id=f"SO-F{_SO_SEQ['n']}",
        facturada=True,
        factura_id="INV1",
        monto_facturado=Decimal(monto_facturado),
        ncs_facturadas=Decimal(ncs),
    )
    h.crear_bandeja(empresa, pedido, total_motor=total_motor)
    return pedido


def test_conciliar_verde(empresa_a):
    pedido = _pedido_facturado(empresa_a, monto_facturado="100.00")
    c = conciliar_pedido(pedido)
    assert c.resultado == "verde"
    assert c.diferencia == Decimal("0.00")
    assert c.total_motor == Decimal("100.00")
    assert c.monto_facturado == Decimal("100.00")
    assert c.ncs == Decimal("0.00")


def test_conciliar_amarillo(empresa_a):
    # |100 - 99.50| = 0.50 → entre rounding (0.01) y red (1.00) → amarillo
    pedido = _pedido_facturado(empresa_a, monto_facturado="99.50")
    c = conciliar_pedido(pedido)
    assert c.resultado == "amarillo"
    assert c.diferencia == Decimal("0.50")


def test_conciliar_rojo(empresa_a):
    # |100 - 90| = 10 > red (1.00) → rojo
    pedido = _pedido_facturado(empresa_a, monto_facturado="90.00")
    c = conciliar_pedido(pedido)
    assert c.resultado == "rojo"
    assert c.diferencia == Decimal("10.00")


def test_conciliar_resta_ncs(empresa_a):
    # neto = 105 - 5 = 100 → cuadra con total_motor 100 → verde
    pedido = _pedido_facturado(empresa_a, monto_facturado="105.00", ncs="5.00")
    c = conciliar_pedido(pedido)
    assert c.resultado == "verde"
    assert c.ncs == Decimal("5.00")
    assert c.diferencia == Decimal("0.00")


def test_conciliar_es_upsert(empresa_a):
    pedido = _pedido_facturado(empresa_a, monto_facturado="90.00")
    conciliar_pedido(pedido)
    # cambia el monto facturado y reconcilia: debe actualizar, no duplicar
    pedido.monto_facturado = Decimal("100.00")
    pedido.save(update_fields=["monto_facturado"])
    c2 = conciliar_pedido(pedido)
    assert c2.resultado == "verde"
    assert ConciliacionLubrikca.objects.filter(pedido=pedido).count() == 1


def test_conciliar_monto_facturado_nulo_usa_cero(empresa_a):
    # monto_facturado None → neto 0 → diferencia = total_motor → rojo
    pedido = h.crear_pedido(empresa_a, facturada=True, monto_facturado=None)
    h.crear_bandeja(empresa_a, pedido, total_motor="100")
    c = conciliar_pedido(pedido)
    assert c.resultado == "rojo"
    assert c.diferencia == Decimal("100.00")


def test_conciliar_no_facturado_error(empresa_a):
    pedido = h.crear_pedido(empresa_a, facturada=False)
    h.crear_bandeja(empresa_a, pedido)
    with pytest.raises(ConciliacionError) as exc:
        conciliar_pedido(pedido)
    assert "no está facturado" in str(exc.value)


def test_conciliar_sin_bandeja_error(empresa_a):
    pedido = h.crear_pedido(empresa_a, facturada=True, monto_facturado=Decimal("100"))
    with pytest.raises(ConciliacionError) as exc:
        conciliar_pedido(pedido)
    assert "recalcule la bandeja" in str(exc.value)


# ---------------------------------------------------------------------------
# Tolerancias configurables cambian el resultado
# ---------------------------------------------------------------------------
def test_tolerancia_custom_cambia_resultado(empresa_a):
    # Sin config custom: |100 - 99.50| = 0.50 → amarillo
    pedido = _pedido_facturado(empresa_a, monto_facturado="99.50")
    assert conciliar_pedido(pedido).resultado == "amarillo"
    # Con rounding ampliado a 0.60 → ahora cuadra → verde
    ConfiguracionConciliacion.objects.create(
        empresa=empresa_a,
        tolerance_rounding=Decimal("0.60"),
        tolerance_red=Decimal("1.00"),
    )
    assert conciliar_pedido(pedido).resultado == "verde"


def test_config_get_or_create_implicito(empresa_a):
    # No hay config previa: el servicio la crea con defaults.
    assert ConfiguracionConciliacion.objects.filter(empresa=empresa_a).count() == 0
    pedido = _pedido_facturado(empresa_a, monto_facturado="100")
    conciliar_pedido(pedido)
    assert ConfiguracionConciliacion.objects.filter(empresa=empresa_a).count() == 1


# ---------------------------------------------------------------------------
# marcar_revisado
# ---------------------------------------------------------------------------
def test_marcar_revisado_service(empresa_a, user_a):
    pedido = _pedido_facturado(empresa_a, monto_facturado="90")
    c = conciliar_pedido(pedido)
    assert c.revisado_por is None
    marcar_revisado(c, user_a)
    c.refresh_from_db()
    assert c.revisado_por_id == user_a.pk


# ---------------------------------------------------------------------------
# resumen_cartera
# ---------------------------------------------------------------------------
def test_resumen_cartera(empresa_a):
    # verde
    conciliar_pedido(
        _pedido_facturado(empresa_a, monto_facturado="100")
    )
    # rojo
    p_rojo = h.crear_pedido(
        empresa_a, so_id="SO-ROJO", facturada=True, monto_facturado=Decimal("80")
    )
    h.crear_bandeja(empresa_a, p_rojo, total_motor="100")
    conciliar_pedido(p_rojo)
    # facturado sin conciliar
    h.crear_pedido(
        empresa_a, so_id="SO-SIN", facturada=True, monto_facturado=Decimal("50")
    )
    # con devolución
    h.crear_pedido(empresa_a, so_id="SO-DEV", tiene_devolucion=True)
    # cartera atascada: no facturado, entrega vieja
    vieja = timezone.now().date() - timedelta(days=60)
    h.crear_pedido(
        empresa_a, so_id="SO-VIEJA", facturada=False, fecha_entrega=vieja
    )

    r = resumen_cartera(empresa_a)
    assert r["por_resultado"]["verde"] == 1
    assert r["por_resultado"]["rojo"] == 1
    assert r["total_conciliados"] == 2
    assert r["total_facturados"] == 3
    assert r["facturados_sin_conciliar"] == 1
    assert r["pedidos_con_devolucion"] == 1
    assert r["cartera_atascada"] == 1
    assert isinstance(r["diferencia_total"], str)


def test_resumen_cuenta_bandeja_candidata_sin_aprobar(empresa_a):
    pedido = h.crear_pedido(empresa_a, so_id="SO-CAND")
    h.crear_bandeja(
        empresa_a, pedido, total_motor="100", candidata_a_cierre=True
    )
    r = resumen_cartera(empresa_a)
    assert r["bandejas_candidatas_sin_aprobar"] == 1


# ---------------------------------------------------------------------------
# API: acción conciliar / revisar / resumen
# ---------------------------------------------------------------------------
def test_api_conciliar(client_a, empresa_a):
    pedido = _pedido_facturado(empresa_a, monto_facturado="90")
    r = client_a.post(
        f"{BASE}/conciliaciones/conciliar/",
        {"pedido": str(pedido.id)},
        format="json",
    )
    assert r.status_code == 201, r.content
    assert r.data["resultado"] == "rojo"


def test_api_conciliar_no_facturado_da_400(client_a, empresa_a):
    pedido = h.crear_pedido(empresa_a, facturada=False)
    h.crear_bandeja(empresa_a, pedido)
    r = client_a.post(
        f"{BASE}/conciliaciones/conciliar/",
        {"pedido": str(pedido.id)},
        format="json",
    )
    assert r.status_code == 400
    assert "facturado" in r.data["detail"]


def test_api_conciliar_sin_bandeja_da_400(client_a, empresa_a):
    pedido = h.crear_pedido(empresa_a, facturada=True, monto_facturado=Decimal("100"))
    r = client_a.post(
        f"{BASE}/conciliaciones/conciliar/",
        {"pedido": str(pedido.id)},
        format="json",
    )
    assert r.status_code == 400
    assert "bandeja" in r.data["detail"]


def test_api_conciliar_pedido_ajeno_da_404(client_a, empresa_b):
    pedido_b = _pedido_facturado(empresa_b, monto_facturado="100")
    r = client_a.post(
        f"{BASE}/conciliaciones/conciliar/",
        {"pedido": str(pedido_b.id)},
        format="json",
    )
    assert r.status_code == 404


def test_api_revisar(client_a, empresa_a, user_a):
    pedido = _pedido_facturado(empresa_a, monto_facturado="90")
    c = conciliar_pedido(pedido)
    r = client_a.post(f"{BASE}/conciliaciones/{c.id}/revisar/")
    assert r.status_code == 200, r.content
    c.refresh_from_db()
    assert c.revisado_por_id == user_a.pk


def test_api_resumen(client_a, empresa_a):
    conciliar_pedido(_pedido_facturado(empresa_a, monto_facturado="100"))
    r = client_a.get(f"{BASE}/conciliaciones/resumen/")
    assert r.status_code == 200, r.content
    assert r.data["por_resultado"]["verde"] == 1
    assert r.data["total_conciliados"] == 1


# ---------------------------------------------------------------------------
# API: CRUD ConfiguracionConciliacion
# ---------------------------------------------------------------------------
def test_api_config_crud(client_a, empresa_a):
    r = client_a.post(
        f"{BASE}/config-conciliacion/",
        {"tolerance_rounding": "0.05", "tolerance_red": "2.00"},
        format="json",
    )
    assert r.status_code == 201, r.content
    cfg_id = r.data["id"]
    obj = ConfiguracionConciliacion.objects.get(id=cfg_id)
    assert obj.empresa == empresa_a
    assert obj.tolerance_red == Decimal("2.00")

    r2 = client_a.get(f"{BASE}/config-conciliacion/")
    assert r2.status_code == 200
    assert any(row["id"] == cfg_id for row in r2.data["results"])


def test_api_config_sin_empresa_da_403():
    from rest_framework.test import APIClient

    from tests.factories import UsuariosFactory

    user = UsuariosFactory()
    client = APIClient()
    client.force_authenticate(user=user)
    r = client.post(
        f"{BASE}/config-conciliacion/",
        {"tolerance_rounding": "0.05", "tolerance_red": "2.00"},
        format="json",
    )
    assert r.status_code == 403


def test_api_conciliar_sin_empresa_da_403():
    from rest_framework.test import APIClient

    from tests.factories import UsuariosFactory

    user = UsuariosFactory()
    client = APIClient()
    client.force_authenticate(user=user)
    r = client.post(
        f"{BASE}/conciliaciones/conciliar/",
        {"pedido": "00000000-0000-0000-0000-000000000000"},
        format="json",
    )
    assert r.status_code == 403


def test_api_resumen_sin_empresa_da_403():
    from rest_framework.test import APIClient

    from tests.factories import UsuariosFactory

    user = UsuariosFactory()
    client = APIClient()
    client.force_authenticate(user=user)
    r = client.get(f"{BASE}/conciliaciones/resumen/")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Multi-tenant
# ---------------------------------------------------------------------------
def test_conciliacion_ajena_no_visible(client_a, empresa_b):
    pedido_b = _pedido_facturado(empresa_b, monto_facturado="90")
    c = conciliar_pedido(pedido_b)
    r = client_a.get(f"{BASE}/conciliaciones/{c.id}/")
    assert r.status_code == 404


def test_listado_conciliaciones_no_filtra_otra_empresa(
    client_a, empresa_a, empresa_b
):
    c_a = conciliar_pedido(
        _pedido_facturado(empresa_a, monto_facturado="90")
    )
    conciliar_pedido(_pedido_facturado(empresa_b, monto_facturado="90"))
    r = client_a.get(f"{BASE}/conciliaciones/")
    assert r.status_code == 200
    ids = [row["id"] for row in r.data["results"]]
    assert str(c_a.id) in ids
    assert len(ids) == 1


def test_config_ajena_no_visible(client_a, empresa_b):
    cfg_b = ConfiguracionConciliacion.objects.create(empresa=empresa_b)
    r = client_a.get(f"{BASE}/config-conciliacion/{cfg_b.id}/")
    assert r.status_code == 404


def test_resumen_es_por_empresa(client_a, empresa_a, empresa_b):
    conciliar_pedido(_pedido_facturado(empresa_a, monto_facturado="100"))
    conciliar_pedido(_pedido_facturado(empresa_b, monto_facturado="100"))
    conciliar_pedido(_pedido_facturado(empresa_b, monto_facturado="100", total_motor="100"))
    r = client_a.get(f"{BASE}/conciliaciones/resumen/")
    assert r.data["total_conciliados"] == 1
