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
    assert p.rif == "J-301234567" and p.email == "v@x.com" and p.documento_json["origen"] == "bot"
    c = p.contacto
    assert c.es_proveedor and c.dias_pago == 45 and c.latitud == Decimal("10.480600")
    assert Contacto.objects.filter(id_empresa=empresa_a, rif="J-301234567").count() == 1


def test_proveedor_existente_por_rif_no_se_duplica_ni_se_pisa(api, bot_usuario, empresa_a):  # noqa: F811
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
    assert p.razon_social == "Nombre Original" and p.telefono == "0414-1111111"  # no se pisa lo que ya había
    assert p.email == "nuevo@x.com"  # sí se completa lo que faltaba
    assert p.contacto.es_proveedor


def test_proveedor_rif_y_telefono_invalidos(api, bot_usuario):  # noqa: F811
    assert enviar(api, "proveedor", _prov(rif="ABC")).status_code == 422
    assert enviar(api, "proveedor", _prov(telefono="12")).status_code == 422
    assert enviar(api, "proveedor", _prov(dias_credito="mucho")).status_code == 422
    assert enviar(api, "proveedor", _prov(ubicacion={"latitud": 99, "longitud": 0})).status_code == 422


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
    assert cxp.monto_total == cxp.monto_pendiente == Decimal("1160") and cxp.estado == "PENDIENTE"
    assert str(cxp.fecha_vencimiento) == "2026-12-10"
    d = cxp.documento_json
    assert d["numero_factura"] == "A-000123" and d["moneda"] == "USD" and d["numero_control"] == "00-0456"
    assert d["iva"] == "160" and d["base_imponible"] == "1000"
    assert r.data["resultado"]["avisos"] == []


def test_factura_sin_vencimiento_usa_los_dias_de_credito_del_proveedor(api, bot_usuario, proveedor, empresa_a):  # noqa: F811
    c = Contacto.objects.create(id_empresa=empresa_a, nombre="X", es_proveedor=True, dias_pago=15)
    proveedor.contacto = c
    proveedor.save()
    enviar(api, "factura_proveedor", _factura())
    assert str(CuentaPorPagar.objects.get().fecha_vencimiento) == "2026-11-25"


def test_factura_sin_numero_de_control_avisa_pero_se_carga(api, bot_usuario, proveedor):  # noqa: F811
    r = enviar(api, "factura_proveedor", _factura(numero_control=None))
    assert r.status_code == 201 and r.data["resultado"]["avisos"] == ["sin número de control"]


def test_factura_incompleta_no_crea_nada_y_se_completa_despues(api, bot_usuario, proveedor):  # noqa: F811
    r = enviar(
        api,
        "factura_proveedor",
        _factura(monto_total=None, fecha_emision=None),
        key="f1",
        auto=True,
    )
    assert r.status_code == 201 and r.data["estado"] == "INCOMPLETO"
    assert set(r.data["incompleto"]) == {"monto_total", "fecha_emision"} and CuentaPorPagar.objects.count() == 0
    r2 = api.post(
        f"/api/bots/ingest/{r.data['id_ingesta']}/completar/",
        {"cambios": {"monto_total": "1160", "fecha_emision": "2026-11-10"}},
        format="json",
    )
    assert r2.status_code == 200 and r2.data["estado"] == "PROCESADO" and r2.data["incompleto"] == []
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
    assert r.data["estado"] == "INCOMPLETO" and "proveedor (nombre o RIF)" in r.data["incompleto"]


def test_factura_con_proveedor_desconocido_sin_rif_lo_crea_provisional(api, bot_usuario, empresa_a):  # noqa: F811
    r = enviar(api, "factura_proveedor", _factura(rif=None, proveedor="Nadie S.A."))
    assert r.status_code == 201 and r.data["resultado"]["proveedor_creado"] is True, r.data
    p = Proveedor.objects.get(id_empresa=empresa_a, razon_social="Nadie S.A.")
    assert p.rif.startswith("PEND-") and p.documento_json["provisional"] is True
    assert CuentaPorPagar.objects.get().id_proveedor == p


def test_factura_sin_nombre_y_con_rif_desconocido_pide_el_nombre(api, bot_usuario):  # noqa: F811
    r = enviar(api, "factura_proveedor", _factura(proveedor=None, rif="J-555555555"))
    assert r.status_code == 422 and "nombre del proveedor" in r.data["error"]
    assert CuentaPorPagar.objects.count() == 0


def test_factura_con_proveedor_nuevo_y_rif_lo_crea_provisional(api, bot_usuario, empresa_a):  # noqa: F811
    r = enviar(api, "factura_proveedor", _factura(proveedor="Nuevo Prov", rif="J-999999999"))
    assert r.status_code == 201, r.data
    p = Proveedor.objects.get(id_empresa=empresa_a, rif="J-999999999")
    assert p.documento_json["provisional"] is True and CuentaPorPagar.objects.get().id_proveedor == p


def test_factura_duplicada_se_rechaza_con_409(api, bot_usuario, proveedor):  # noqa: F811
    assert enviar(api, "factura_proveedor", _factura(), key="a").status_code == 201
    r = enviar(api, "factura_proveedor", _factura(), key="b")
    assert r.status_code == 409 and "ya está cargada" in r.data["error"]
    assert CuentaPorPagar.objects.count() == 1


def test_misma_factura_de_otro_proveedor_es_valida(api, bot_usuario, proveedor, empresa_a):  # noqa: F811
    Proveedor.objects.create(id_empresa=empresa_a, razon_social="Otro", rif="J-111111111")
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
    assert cxp.monto_pendiente == Decimal("1160")  # solo se referencia: el abono lo aplica quien concilia


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
    Proveedor.objects.create(id_empresa=empresa_b, razon_social="Ajeno", rif="J-301234567")
    r = enviar(api, "proveedor", _prov())
    assert r.data["resultado"]["creado"] is True  # el RIF ajeno no cuenta como existente
    r = enviar(api, "factura_proveedor", _factura(rif=None, proveedor="Ajeno"), key="otra")
    assert r.status_code == 201 and r.data["resultado"]["proveedor_creado"] is True  # no usa el ajeno


# ── carreras y robustez (hallazgos de las pruebas de punta a punta) ──────────


def test_alta_de_proveedor_que_pierde_la_carrera_devuelve_el_existente(api, bot_usuario, empresa_a, monkeypatch):
    """Si otro envío simultáneo creó el proveedor entre la búsqueda y el alta, no hay 500: se usa el que quedó."""
    from apps.bots_ingest.services import handlers

    Proveedor.objects.create(id_empresa=empresa_a, razon_social="Ya existe", rif="J-301234567")
    real = handlers._proveedor_por
    llamadas = {"n": 0}

    def primero_no_lo_ve(*a, **k):
        llamadas["n"] += 1
        return None if llamadas["n"] == 1 else real(*a, **k)  # la 1.ª búsqueda ocurre «antes» de que el otro cree

    monkeypatch.setattr(handlers, "_proveedor_por", primero_no_lo_ve)
    r = enviar(api, "proveedor", _prov())
    assert r.status_code == 201, r.data
    assert r.data["resultado"]["creado"] is False and Proveedor.objects.filter(id_empresa=empresa_a).count() == 1


def test_factura_con_proveedor_nuevo_que_pierde_la_carrera_tambien_se_resuelve(
    api, bot_usuario, empresa_a, monkeypatch
):
    from apps.bots_ingest.services import handlers

    Proveedor.objects.create(id_empresa=empresa_a, razon_social="Nuevo Prov", rif="J-999999999")
    real = handlers._proveedor_por
    llamadas = {"n": 0}

    def primero_no_lo_ve(*a, **k):
        llamadas["n"] += 1
        return None if llamadas["n"] == 1 else real(*a, **k)

    monkeypatch.setattr(handlers, "_proveedor_por", primero_no_lo_ve)
    r = enviar(api, "factura_proveedor", _factura(proveedor="Nuevo Prov", rif="J-999999999"))
    assert r.status_code == 201, r.data
    assert Proveedor.objects.filter(id_empresa=empresa_a, rif="J-999999999").count() == 1


@pytest.mark.django_db(transaction=True)
def test_la_misma_factura_enviada_en_paralelo_se_carga_una_sola_vez(servicio, bot_usuario, proveedor, empresa_a):
    """Seis envíos simultáneos de la misma factura (claves distintas): una sola cuenta por pagar."""
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connection
    from rest_framework.test import APIClient

    def enviar_en_hilo(i):
        try:
            c = APIClient()
            c.force_authenticate(user=servicio)
            return enviar(
                c,
                "factura_proveedor",
                _factura(numero_factura="RACE-1"),
                key=f"carrera-{i}",
            ).status_code
        finally:
            connection.close()

    from unittest.mock import patch

    with patch("apps.bots_ingest.tasks.encolar_sync"):
        with ThreadPoolExecutor(max_workers=6) as ex:
            codigos = list(ex.map(enviar_en_hilo, range(6)))
    assert codigos.count(201) == 1 and codigos.count(409) == 5, codigos
    assert CuentaPorPagar.objects.filter(id_proveedor=proveedor).count() == 1


# ── gastos / compras menores (proveedor leído del documento) ─────────────────

from apps.finanzas.models import Moneda  # noqa: E402
from apps.gastos.models import CategoriaGasto, Gasto  # noqa: E402


def _gasto(**kw):
    d = {
        "proveedor": "Comidas Rápidas Valencia C.A.",
        "rif": "J-30765432-1",
        "proveedor_direccion": "C.C. Sambil, local 12, Valencia",
        "proveedor_telefono": "0241-5551234",
        "numero_factura": "00012345",
        "fecha_emision": "2026-11-14",
        "moneda": "USD",
        "base_imponible": "10.00",
        "iva": "1.60",
        "monto_total": "11.60",
        "concepto": "Almuerzo de la jornada de campo",
        "categoria": "Alimentación",
    }
    d.update(kw)
    return d


@pytest.fixture
def monedas(db):
    return {
        c: Moneda.objects.get_or_create(codigo_iso=c, defaults={"nombre": c, "simbolo": c})[0] for c in ("USD", "VES")
    }


def test_gasto_crea_el_proveedor_desde_el_documento_y_el_gasto(api, bot_usuario, monedas, empresa_a):  # noqa: F811
    r = enviar(api, "gasto", _gasto())
    assert r.status_code == 201 and r.data["estado"] == "PROCESADO", r.data
    assert r.data["resultado"]["proveedor_creado"] is True
    p = Proveedor.objects.get(id_empresa=empresa_a, rif="J-307654321")
    assert p.razon_social == "Comidas Rápidas Valencia C.A." and p.direccion.startswith("C.C. Sambil")
    assert p.telefono == "0241-5551234" and p.contacto.es_proveedor and p.documento_json["provisional"] is True
    g = Gasto.objects.get(id_empresa=empresa_a)
    assert (g.monto, g.monto_iva, g.id_moneda.codigo_iso) == (
        Decimal("11.60"),
        Decimal("1.60"),
        "USD",
    )
    assert g.id_proveedor == p and g.numero_factura == "00012345" and g.tiene_factura is True
    assert g.id_categoria_gasto.nombre_categoria == "Compras menores"  # «Alimentación» no existe: va a la por defecto
    assert g.estado_gasto == "PENDIENTE_APROBACION" and g.id_usuario_registro_id == bot_usuario.usuario_id
    assert g.descripcion == "Almuerzo de la jornada de campo"


def test_gasto_con_proveedor_existente_no_lo_duplica_ni_pisa_sus_datos(api, bot_usuario, monedas, empresa_a):  # noqa: F811
    p = Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Nombre Original",
        rif="J-307654321",
        telefono="0414-1112233",
    )
    r = enviar(api, "gasto", _gasto())
    assert r.status_code == 201 and r.data["resultado"]["proveedor_creado"] is False
    p.refresh_from_db()
    assert Proveedor.objects.filter(id_empresa=empresa_a).count() == 1
    assert p.razon_social == "Nombre Original" and p.telefono == "0414-1112233"  # no se pisa
    assert p.direccion == "C.C. Sambil, local 12, Valencia"  # sí se completa lo que le faltaba
    assert Gasto.objects.get().id_proveedor == p


def test_gasto_sin_rif_usa_un_rif_provisional_estable_y_reconoce_al_proveedor_despues(
    api, bot_usuario, monedas, empresa_a
):  # noqa: F811
    r1 = enviar(api, "gasto", _gasto(rif=None, numero_factura="A1"), key="a")
    r2 = enviar(
        api,
        "gasto",
        _gasto(rif=None, proveedor="  comidas  rápidas valencia c.a. ", numero_factura="A2"),
        key="b",
    )
    assert r1.status_code == r2.status_code == 201, (r1.data, r2.data)
    assert (
        r2.data["resultado"]["proveedor_creado"] is False
    )  # mismo nombre (otro espaciado/mayúsculas): el mismo proveedor
    assert Proveedor.objects.filter(id_empresa=empresa_a).count() == 1
    assert "proveedor sin RIF: pendiente de completar" in r1.data["resultado"]["avisos"]


def test_llega_el_rif_de_un_proveedor_creado_sin_el(api, bot_usuario, monedas, empresa_a):  # noqa: F811
    enviar(api, "gasto", _gasto(rif=None, numero_factura="A1"), key="a")
    enviar(api, "gasto", _gasto(numero_factura="A2"), key="b")  # ahora el documento trae el RIF
    p = Proveedor.objects.get(id_empresa=empresa_a)
    assert p.rif == "J-307654321"


def test_mismo_nombre_con_otro_rif_es_otro_proveedor(api, bot_usuario, monedas, empresa_a):  # noqa: F811
    Proveedor.objects.create(
        id_empresa=empresa_a,
        razon_social="Comidas Rápidas Valencia C.A.",
        rif="J-111111111",
    )
    r = enviar(api, "gasto", _gasto())  # el documento trae otro RIF
    assert r.status_code == 201 and r.data["resultado"]["proveedor_creado"] is True
    assert Proveedor.objects.filter(id_empresa=empresa_a).count() == 2


def test_gasto_usa_la_categoria_existente_por_nombre(api, bot_usuario, monedas, empresa_a):  # noqa: F811
    CategoriaGasto.objects.create(id_empresa=empresa_a, nombre_categoria="Alimentación y bebidas")
    enviar(api, "gasto", _gasto())
    assert Gasto.objects.get().id_categoria_gasto.nombre_categoria == "Alimentación y bebidas"


def test_gasto_en_bolivares_acepta_bs_y_variantes(api, bot_usuario, monedas):  # noqa: F811
    r = enviar(api, "gasto", _gasto(moneda="Bs.", numero_factura="B1"))
    assert r.status_code == 201 and Gasto.objects.get().id_moneda.codigo_iso == "VES"


def test_gasto_con_moneda_inexistente_se_rechaza_sin_basura(api, bot_usuario, monedas, empresa_a):  # noqa: F811
    r = enviar(api, "gasto", _gasto(moneda="XYZ"))
    assert r.status_code == 422 and "moneda" in r.data["error"].lower()
    assert Proveedor.objects.filter(id_empresa=empresa_a).count() == 0 and Gasto.objects.count() == 0  # nada a medias


def test_gasto_sin_numero_de_factura_se_registra_con_aviso(api, bot_usuario, monedas):  # noqa: F811
    r = enviar(api, "gasto", _gasto(numero_factura=None))
    assert r.status_code == 201 and "sin número de factura" in r.data["resultado"]["avisos"]
    g = Gasto.objects.get()
    assert g.tiene_factura is False and g.numero_factura is None


def test_gasto_duplicado_del_mismo_proveedor_es_409(api, bot_usuario, monedas):  # noqa: F811
    assert enviar(api, "gasto", _gasto(), key="a").status_code == 201
    r = enviar(api, "gasto", _gasto(), key="b")
    assert r.status_code == 409 and "ya está cargada" in r.data["error"] and Gasto.objects.count() == 1


@pytest.mark.parametrize("quitar", ["proveedor", "fecha_emision", "monto_total", "moneda"])
def test_gasto_incompleto_no_crea_nada_hasta_completarse(api, bot_usuario, monedas, empresa_a, quitar):  # noqa: F811
    d = _gasto()
    d.pop(quitar)
    r = enviar(api, "gasto", d, key="g1", auto=True)
    assert r.status_code == 201 and r.data["estado"] == "INCOMPLETO" and quitar in r.data["incompleto"][0]
    assert Gasto.objects.count() == 0 and Proveedor.objects.filter(id_empresa=empresa_a).count() == 0
    r2 = api.post(
        f"/api/bots/ingest/{r.data['id_ingesta']}/completar/",
        {"cambios": {quitar: _gasto()[quitar]}},
        format="json",
    )
    assert r2.status_code == 200 and r2.data["estado"] == "PROCESADO", r2.data
    assert Gasto.objects.count() == 1


@pytest.mark.parametrize(
    "cambio",
    [
        {"monto_total": "0"},
        {"monto_total": "-3"},
        {"iva": "-1"},
        {"fecha_emision": "14/11/2026"},
        {"rif": "ABC"},
    ],
)
def test_gasto_con_datos_invalidos(api, bot_usuario, monedas, empresa_a, cambio):  # noqa: F811
    assert enviar(api, "gasto", _gasto(**cambio)).status_code == 422
    assert Gasto.objects.count() == 0 and Proveedor.objects.filter(id_empresa=empresa_a).count() == 0


@pytest.mark.django_db(transaction=True)
def test_gastos_simultaneos_de_un_proveedor_nuevo_no_lo_duplican(servicio, bot_usuario, monedas, empresa_a):  # noqa: F811
    """Seis recibos de un proveedor que aún no existe, enviados a la vez: un solo proveedor y seis gastos."""
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connection
    from rest_framework.test import APIClient

    def enviar_en_hilo(i):
        try:
            c = APIClient()
            c.force_authenticate(user=servicio)
            return enviar(c, "gasto", _gasto(numero_factura=f"R-{i}"), key=f"g-{i}").status_code
        finally:
            connection.close()

    from unittest.mock import patch

    with patch("apps.bots_ingest.tasks.encolar_sync"):
        with ThreadPoolExecutor(max_workers=6) as ex:
            codigos = list(ex.map(enviar_en_hilo, range(6)))
    assert codigos == [201] * 6, codigos
    assert Proveedor.objects.filter(id_empresa=empresa_a).count() == 1 and Gasto.objects.count() == 6


@pytest.mark.tenant
def test_gasto_no_usa_el_proveedor_ni_la_categoria_de_otra_empresa(api, bot_usuario, monedas, empresa_a, empresa_b):  # noqa: F811
    Proveedor.objects.create(
        id_empresa=empresa_b,
        razon_social="Comidas Rápidas Valencia C.A.",
        rif="J-307654321",
    )
    CategoriaGasto.objects.create(id_empresa=empresa_b, nombre_categoria="Alimentación")
    r = enviar(api, "gasto", _gasto())
    assert r.status_code == 201 and r.data["resultado"]["proveedor_creado"] is True
    g = Gasto.objects.get(id_empresa=empresa_a)
    assert g.id_proveedor.id_empresa_id == empresa_a.pk and g.id_categoria_gasto.id_empresa_id == empresa_a.pk


@pytest.mark.tenant
def test_gasto_no_usa_moneda_privada_de_otra_empresa(api, bot_usuario, monedas, empresa_a, empresa_b):  # noqa: F811
    Moneda.objects.create(
        codigo_iso="TKB",
        nombre="Token Privado B",
        simbolo="TB",
        tipo_moneda="otro",
        es_generica=False,
        es_publica=False,
        empresa=empresa_b,
    )
    r = enviar(api, "gasto", _gasto(moneda="TKB"))
    assert r.status_code == 422
    assert "no existe en Omni" in r.data["error"]
    assert "moneda" in r.data["faltan"]
    assert not Gasto.objects.filter(id_empresa=empresa_a).exists()
