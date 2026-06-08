"""
Unit de los **helpers puros** de ``apps.contabilidad.services`` (sin BD).

El corazón ORM (``generar_asiento``) está bajo ``@transaction.atomic`` y se prueba con
BD en ``tests_api``/``tests/integration``. Aquí se cubren —rápido, sin BD— las funciones
de extracción/formato duck-typed, que son las que un mutante podría romper en silencio:
extracción defensiva de empresa y monto, formato del número de asiento y construcción de
la descripción a partir de la plantilla del mapeo.
"""

import re
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.contabilidad.services import (
    AsientoError,
    _descripcion,
    _extraer_empresa,
    _extraer_monto,
    _numero_asiento,
)

pytestmark = pytest.mark.unit


# ── _extraer_empresa ────────────────────────────────────────────────────────────


def test_extraer_empresa_prefiere_id_empresa():
    emp = object()
    doc = SimpleNamespace(id_empresa=emp, empresa=object())
    assert _extraer_empresa(doc) is emp


def test_extraer_empresa_cae_a_empresa():
    emp = object()
    doc = SimpleNamespace(empresa=emp)
    assert _extraer_empresa(doc) is emp


def test_extraer_empresa_sin_campos_levanta_error():
    with pytest.raises(AsientoError):
        _extraer_empresa(SimpleNamespace())


# ── _extraer_monto ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "attr, valor, esperado",
    [
        ("monto_total", "100.50", Decimal("100.50")),
        ("total", 200, Decimal("200")),
        ("monto", "300.25", Decimal("300.25")),
        ("subtotal", 400, Decimal("400")),
        ("base_imponible", "500", Decimal("500")),
    ],
)
def test_extraer_monto_por_cada_alias(attr, valor, esperado):
    doc = SimpleNamespace(**{attr: valor})
    assert _extraer_monto(doc) == esperado


def test_extraer_monto_respeta_orden_de_preferencia():
    # monto_total gana sobre total/monto si todos están presentes.
    doc = SimpleNamespace(monto_total=10, total=20, monto=30)
    assert _extraer_monto(doc) == Decimal("10")


def test_extraer_monto_devuelve_decimal():
    assert isinstance(_extraer_monto(SimpleNamespace(total=1.5)), Decimal)


def test_extraer_monto_sin_campos_levanta_error():
    with pytest.raises(AsientoError):
        _extraer_monto(SimpleNamespace())


# ── _numero_asiento ─────────────────────────────────────────────────────────────


def test_numero_asiento_formato():
    num = _numero_asiento("FACTURA_VENTA")
    # AST-{tipo[:4]}-{YYYYMMDD}-{8 hex MAYUS}
    assert re.fullmatch(r"AST-FACT-\d{8}-[0-9A-F]{8}", num), num


def test_numero_asiento_unico_entre_llamadas():
    assert _numero_asiento("PAGO_CXC") != _numero_asiento("PAGO_CXC")


def test_numero_asiento_trunca_tipo_a_cuatro():
    assert _numero_asiento("X").startswith("AST-X-")


# ── _descripcion ────────────────────────────────────────────────────────────────


def test_descripcion_reemplaza_tipo_y_numero():
    doc = SimpleNamespace(numero_factura="F-001")
    out = _descripcion("Asiento {tipo} doc {numero}", "FACTURA_VENTA", doc)
    assert out == "Asiento FACTURA_VENTA doc F-001"


def test_descripcion_usa_primer_numero_disponible():
    # numero_factura no está; cae a numero_orden.
    doc = SimpleNamespace(numero_orden="OC-9")
    assert _descripcion("{numero}", "FACTURA_COMPRA", doc) == "OC-9"


def test_descripcion_fallback_a_pk_truncado():
    doc = SimpleNamespace(pk="abcdef1234567890")
    out = _descripcion("doc {numero}", "NOTA_VENTA", doc)
    assert out == "doc abcdef12"  # primeros 8 chars del pk


def test_descripcion_ignora_numero_vacio_y_usa_pk():
    # numero_factura presente pero falsy ("") ⇒ no se usa; cae a pk.
    doc = SimpleNamespace(numero_factura="", pk="0123456789")
    assert _descripcion("{numero}", "FACTURA_VENTA", doc) == "01234567"
