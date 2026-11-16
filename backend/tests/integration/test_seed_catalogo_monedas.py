"""Catálogo base de monedas (USD, VES, EUR, USDT): siembra idempotente y no destructiva.

Sin ``USD`` y ``VES`` en el catálogo global, ``integration_hub.sync_tasas_ve`` y la captura de CxC
Lubrikca no funcionan en un entorno nuevo. Estos tests fijan el contrato del seed:
  1. Crea lo que falta, con datos completos y marcado como moneda global pública.
  2. Es idempotente (relanzarlo no duplica ni cambia nada).
  3. Completa solo los placeholders de un seed mínimo (``nombre == codigo``).
  4. Nunca pisa una edición humana.
  5. Se invoca desde ``seed_empresa_inicial``.
"""

import pytest

from django.core.management import call_command

from apps.core.models import Empresa
from apps.finanzas.catalogo_monedas import CATALOGO_BASE, sembrar_catalogo_monedas
from apps.finanzas.models import Moneda

pytestmark = pytest.mark.django_db

CODIGOS = sorted(c[0] for c in CATALOGO_BASE)


def test_catalogo_base_contiene_usd_y_ves():
    """USD y VES son las que exige sync_tasas_ve: no pueden desaparecer del catálogo."""
    assert {"USD", "VES"} <= set(CODIGOS)


def test_crea_el_catalogo_completo_y_global():
    r = sembrar_catalogo_monedas()

    assert sorted(r.creadas) == CODIGOS
    assert r.completadas == [] and r.sin_cambios == []

    usd = Moneda.objects.get(codigo_iso="USD")
    assert (usd.nombre, usd.simbolo, usd.pais_codigo_iso, usd.pais_nombre) == (
        "Dólar estadounidense",
        "$",
        "USA",
        "Estados Unidos",
    )
    ves = Moneda.objects.get(codigo_iso="VES")
    assert (ves.simbolo, ves.pais_codigo_iso, ves.decimales) == ("Bs", "VEN", 2)
    assert Moneda.objects.get(codigo_iso="USDT").tipo_moneda == "crypto"
    eur = Moneda.objects.get(codigo_iso="EUR")
    assert eur.pais_codigo_iso is None and eur.pais_nombre == "Zona euro"

    for m in Moneda.objects.filter(codigo_iso__in=CODIGOS):
        assert m.es_generica and m.es_publica and m.activo
        assert m.empresa_id is None  # catálogo global, no de una empresa


def test_es_idempotente():
    sembrar_catalogo_monedas()
    antes = list(Moneda.objects.order_by("codigo_iso").values_list("id_moneda", "nombre", "simbolo"))

    r = sembrar_catalogo_monedas()

    assert r.creadas == [] and r.completadas == []
    assert sorted(r.sin_cambios) == CODIGOS
    assert Moneda.objects.count() == len(CODIGOS)
    assert list(Moneda.objects.order_by("codigo_iso").values_list("id_moneda", "nombre", "simbolo")) == antes


def test_completa_los_placeholders_de_un_seed_minimo():
    """Lo que dejaba seed_empresa_inicial: nombre y símbolo iguales al código, sin país."""
    Moneda.objects.create(codigo_iso="USD", nombre="USD", simbolo="USD", es_publica=True)

    r = sembrar_catalogo_monedas()

    assert r.completadas == ["USD"]
    assert sorted(r.creadas) == ["EUR", "USDT", "VES"]
    usd = Moneda.objects.get(codigo_iso="USD")
    assert (usd.nombre, usd.simbolo, usd.pais_codigo_iso) == ("Dólar estadounidense", "$", "USA")


def test_no_pisa_los_datos_editados():
    Moneda.objects.create(
        codigo_iso="USD",
        nombre="Dólar de la casa",
        simbolo="US$",
        pais_codigo_iso="USA",
        pais_nombre="EE. UU.",
    )

    r = sembrar_catalogo_monedas()

    assert "USD" in r.sin_cambios
    usd = Moneda.objects.get(codigo_iso="USD")
    assert (usd.nombre, usd.simbolo, usd.pais_nombre) == ("Dólar de la casa", "US$", "EE. UU.")


def test_el_comando_informa_lo_que_hizo(capsys):
    call_command("seed_catalogo_monedas")
    salida = capsys.readouterr().out
    assert f"{len(CODIGOS)} creada(s)" in salida

    call_command("seed_catalogo_monedas")
    assert f"{len(CODIGOS)} sin cambios" in capsys.readouterr().out


def test_seed_empresa_inicial_siembra_el_catalogo(monkeypatch):
    monkeypatch.setenv("OMNI_SEED_ADMIN_PASSWORD", "Sup3rS3gura_2026!")

    call_command(
        "seed_empresa_inicial",
        nombre_legal="Catálogo Test C.A.",
        rif="J-40111222-3",
        admin_username="admin_catalogo",
        admin_email="admin@catalogo.test",
    )

    assert sorted(Moneda.objects.filter(codigo_iso__in=CODIGOS).values_list("codigo_iso", flat=True)) == CODIGOS
    empresa = Empresa.objects.get(identificador_fiscal="J-40111222-3")
    # La moneda base sale completa porque el catálogo se siembra antes de crearla.
    assert empresa.id_moneda_base.nombre == "Dólar estadounidense"
