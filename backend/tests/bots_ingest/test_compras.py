# ruff: noqa: F811
"""Bot de Compras: proveedores, facturas de proveedor (→ cuenta por pagar) y vínculo con los pagos."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.bots_ingest.models import IngestaBot
from apps.core.models import Contacto
from apps.cuentas_por_pagar.models import CuentaPorPagar
from apps.proveedores.models import Proveedor

from .test_ingest import UBIC, api, bot_usuario, enviar, servicio  # noqa: F401  (fixtures)

pytestmark = [pytest.mark.django_db]


def _prov(**kw):
    d = {
        "nombre": "Lubricantes del Centro C.A.",
        "rif": "j-30123456-7",
        "telefono": "0241-8001122",
    }
    d.update(kw)
    return d


def _factura(**kw):
    d = {
        "proveedor": "Lubricantes del Centro C.A.",
        "rif": "J-301234567",
        "numero_factura": "A-000123",
        "numero_control": "00-0456",
        "fecha_emision": "2026-11-10",
        "moneda": "USD",
        "base_imponible": "1000",
        "iva": "160",
        "monto_total": "1160",
    }
    d.update(kw)
    return d


# ── proveedor ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("quitar", ["nombre", "rif", "telefono"])
def test_proveedor_exige_nombre_rif_y_telefono(api, bot_usuario, quitar):  # noqa: F811
    d = _prov()
    d.pop(quitar)
    r = enviar(api, "proveedor", d)
    assert r.status_code == 422 and quitar in r.data["faltan"]
    assert Proveedor.objects.count() == 0 and IngestaBot.objects.count() == 0


def test_proveedor_se_crea_con_contacto_gps_y_credito(api, bot_usuario, empresa_a):  # noqa: F811
    r = enviar(
        api,
        "proveedor",
        _prov(
            email="v@x.com",
            direccion="Zona Industrial",
            dias_credito=45,
            ubicacion=UBIC,
        ),
    )
    assert r.status_code == 201, r.data
    p = Proveedor.objects.get(id_empresa=empresa_a)
    assert (
        p.rif == "J-301234567"
        and p.email == "v@x.com"
        and p.documento_json["origen"] == "bot"
    )
    c = p.contacto
    assert c.es_proveedor and c.dias_pago == 45 and c.latitud == Decimal("10.480600")
    assert Contacto.objects.filter(id_empresa=empresa_a, rif="J-301234567").count() == 1


def test_proveedor_existente_por_rif_no_se_duplica_ni_se_pisa(
    api, bot_usuario, empresa_a
):  # noqa: F811
    p = Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Nombre Original",
        rif="J-301234567",
        telefono="0414-1111111",
    )
    r = enviar(api, "proveedor", _prov(email="nuevo@x.com", telefono="0212-9998877"))
    assert r.status_code == 201 and r.data["resultado"]["creado"] is False
    p.refresh_from_db()
    assert Proveedor.objects.count() == 1
    assert (
        p.razon_social == "Nombre Original" and p.telefono == "0414-1111111"
    )  # no se pisa lo que ya había
    assert p.email == "nuevo@x.com"  # sí se completa lo que faltaba
    assert p.contacto.es_proveedor


def test_proveedor_rif_y_telefono_invalidos(api, bot_usuario):  # noqa: F811
    assert enviar(api, "proveedor", _prov(rif="ABC")).status_code == 422
    assert enviar(api, "proveedor", _prov(telefono="12")).status_code == 422
    assert enviar(api, "proveedor", _prov(dias_credito="mucho")).status_code == 422
    assert (
        enviar(
            api, "proveedor", _prov(ubicacion={"latitud": 99, "longitud": 0})
        ).status_code
        == 422
    )


def test_proveedor_idempotente(api, bot_usuario, empresa_a):  # noqa: F811
    r1, r2 = (
        enviar(api, "proveedor", _prov(), key="x"),
        enviar(api, "proveedor", _prov(), key="x"),
    )
    assert (r1.status_code, r2.status_code) == (201, 200)
    assert Proveedor.objects.filter(id_empresa=empresa_a).count() == 1


# ── factura de proveedor ─────────────────────────────────────────────────────


@pytest.fixture
def proveedor(empresa_a):
    return Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Lubricantes del Centro C.A.",
        rif="J-301234567",
    )


def test_factura_crea_cuenta_por_pagar(api, bot_usuario, proveedor):  # noqa: F811
    r = enviar(api, "factura_proveedor", _factura(fecha_vencimiento="2026-12-10"))
    assert r.status_code == 201 and r.data["estado"] == "PROCESADO", r.data
    cxp = CuentaPorPagar.objects.get(id_proveedor=proveedor)
    assert (
        cxp.monto_total == cxp.monto_pendiente == Decimal("1160")
        and cxp.estado == "PENDIENTE"
    )
    assert str(cxp.fecha_vencimiento) == "2026-12-10"
    d = cxp.documento_json
    assert (
        d["numero_factura"] == "A-000123"
        and d["moneda"] == "USD"
        and d["numero_control"] == "00-0456"
    )
    assert d["iva"] == "160" and d["base_imponible"] == "1000"
    assert r.data["resultado"]["avisos"] == []


def test_factura_sin_vencimiento_usa_los_dias_de_credito_del_proveedor(
    api, bot_usuario, proveedor, empresa_a
):  # noqa: F811
    c = Contacto.objects.create(
        id_empresa=empresa_a, nombre="X", es_proveedor=True, dias_pago=15
    )
    proveedor.contacto = c
    proveedor.save()
    enviar(api, "factura_proveedor", _factura())
    assert str(CuentaPorPagar.objects.get().fecha_vencimiento) == "2026-11-25"


def test_factura_sin_numero_de_control_avisa_pero_se_carga(api, bot_usuario, proveedor):  # noqa: F811
    r = enviar(api, "factura_proveedor", _factura(numero_control=None))
    assert r.status_code == 201 and r.data["resultado"]["avisos"] == [
        "sin número de control"
    ]


def test_factura_incompleta_no_crea_nada_y_se_completa_despues(
    api, bot_usuario, proveedor
):  # noqa: F811
    r = enviar(
        api,
        "factura_proveedor",
        _factura(monto_total=None, fecha_emision=None),
        key="f1",
        auto=True,
    )
    assert r.status_code == 201 and r.data["estado"] == "INCOMPLETO"
    assert (
        set(r.data["incompleto"]) == {"monto_total", "fecha_emision"}
        and CuentaPorPagar.objects.count() == 0
    )
    r2 = api.post(
        f"/api/bots/ingest/{r.data['id_ingesta']}/completar/",
        {"cambios": {"monto_total": "1160", "fecha_emision": "2026-11-10"}},
        format="json",
    )
    assert (
        r2.status_code == 200
        and r2.data["estado"] == "PROCESADO"
        and r2.data["incompleto"] == []
    )
    assert CuentaPorPagar.objects.get().monto_total == Decimal("1160")
    # ya procesada: no se puede volver a completar
    assert (
        api.post(
            f"/api/bots/ingest/{r.data['id_ingesta']}/completar/",
            {"cambios": {"iva": "1"}},
            format="json",
        ).status_code
        == 409
    )


def test_factura_sin_proveedor_queda_incompleta(api, bot_usuario):  # noqa: F811
    r = enviar(api, "factura_proveedor", _factura(proveedor=None, rif=None))
    assert (
        r.data["estado"] == "INCOMPLETO"
        and "proveedor (nombre o RIF)" in r.data["incompleto"]
    )


def test_factura_con_proveedor_desconocido_sin_rif_se_rechaza(api, bot_usuario):  # noqa: F811
    r = enviar(api, "factura_proveedor", _factura(rif=None, proveedor="Nadie S.A."))
    assert (
        r.status_code == 422
        and "/proveedor" in r.data["error"]
        and CuentaPorPagar.objects.count() == 0
    )


def test_factura_con_proveedor_nuevo_y_rif_lo_crea_provisional(
    api, bot_usuario, empresa_a
):  # noqa: F811
    r = enviar(
        api, "factura_proveedor", _factura(proveedor="Nuevo Prov", rif="J-999999999")
    )
    assert r.status_code == 201, r.data
    p = Proveedor.objects.get(id_empresa=empresa_a, rif="J-999999999")
    assert (
        p.documento_json["provisional"] is True
        and CuentaPorPagar.objects.get().id_proveedor == p
    )


def test_factura_duplicada_se_rechaza_con_409(api, bot_usuario, proveedor):  # noqa: F811
    assert enviar(api, "factura_proveedor", _factura(), key="a").status_code == 201
    r = enviar(api, "factura_proveedor", _factura(), key="b")
    assert r.status_code == 409 and "ya está cargada" in r.data["error"]
    assert CuentaPorPagar.objects.count() == 1


def test_misma_factura_de_otro_proveedor_es_valida(
    api, bot_usuario, proveedor, empresa_a
):  # noqa: F811
    Proveedor.objects.create(
        id_empresa=empresa_a, razon_social="Otro", rif="J-111111111"
    )
    enviar(api, "factura_proveedor", _factura(), key="a")
    assert (
        enviar(
            api,
            "factura_proveedor",
            _factura(proveedor="Otro", rif="J-111111111"),
            key="b",
        ).status_code
        == 201
    )


@pytest.mark.parametrize(
    "cambio",
    [
        {"monto_total": "-5"},
        {"monto_total": "abc"},
        {"fecha_emision": "10/11/2026"},
        {"fecha_vencimiento": "2026-01-01"},
    ],
)
def test_factura_con_datos_invalidos(api, bot_usuario, proveedor, cambio):  # noqa: F811
    assert enviar(api, "factura_proveedor", _factura(**cambio)).status_code == 422
    assert CuentaPorPagar.objects.count() == 0


# ── pago a proveedor ligado a su factura ─────────────────────────────────────


def test_pago_proveedor_referencia_la_factura_cargada(api, bot_usuario, proveedor):  # noqa: F811
    enviar(api, "factura_proveedor", _factura(), key="f")
    cxp = CuentaPorPagar.objects.get()
    r = enviar(
        api,
        "pago_proveedor",
        {
            "proveedor": "Lubricantes del Centro C.A.",
            "monto": "1160",
            "moneda": "USD",
            "factura_ref": "A-000123",
        },
        key="p",
    )
    assert r.status_code == 201 and r.data["estado"] == "BORRADOR"
    assert r.data["resultado"]["cxp_id"] == str(cxp.pk)
    cxp.refresh_from_db()
    assert cxp.monto_pendiente == Decimal(
        "1160"
    )  # solo se referencia: el abono lo aplica quien concilia


def test_pago_proveedor_con_factura_desconocida_no_falla(api, bot_usuario, proveedor):  # noqa: F811
    r = enviar(
        api,
        "pago_proveedor",
        {
            "proveedor": "Lubricantes del Centro C.A.",
            "monto": "5",
            "moneda": "USD",
            "factura_ref": "NO-EXISTE",
        },
    )
    assert r.status_code == 201 and "cxp_id" not in r.data["resultado"]


# ── aislamiento ──────────────────────────────────────────────────────────────


@pytest.mark.tenant
def test_no_usa_proveedores_de_otra_empresa(api, bot_usuario, empresa_b):  # noqa: F811
    Proveedor.objects.create(
        id_empresa=empresa_b, razon_social="Ajeno", rif="J-301234567"
    )
    r = enviar(api, "proveedor", _prov())
    assert (
        r.data["resultado"]["creado"] is True
    )  # el RIF ajeno no cuenta como existente
    assert (
        enviar(
            api, "factura_proveedor", _factura(rif=None, proveedor="Ajeno"), key="otra"
        ).status_code
        == 422
    )
