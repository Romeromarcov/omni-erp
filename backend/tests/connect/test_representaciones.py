"""Representaciones de texto de los modelos de Connect y del CRM ligero (aparecen en el admin y en logs)."""

import pytest

from apps.connect.models import Tarjeta

from .builders import (
    crear_etapa,
    crear_lead,
    crear_perfil,
    crear_pipeline,
    crear_tarjeta,
    crear_toque,
)

pytestmark = [pytest.mark.django_db]


def test_perfil_se_muestra_con_su_nombre_y_slug(empresa_a):
    perfil = crear_perfil(empresa_a, slug="ana-lopez", nombre_publico="Ana López")
    assert str(perfil) == "Ana López (ana-lopez)"


def test_tarjeta_se_muestra_con_tipo_uid_y_estado(empresa_a):
    tarjeta = crear_tarjeta(empresa_a, uid_chip="04A2B3C4D5E6F7", tipo=Tarjeta.Tipo.METAL)
    assert str(tarjeta) == "METAL 04A2B3C4D5E6F7 [INVENTARIO]"


def test_toque_se_muestra_con_origen_perfil_y_fecha(empresa_a):
    perfil = crear_perfil(empresa_a)
    toque = crear_toque(empresa_a, perfil=perfil, origen="QR")
    texto = str(toque)
    assert texto.startswith("QR → ")
    assert str(perfil.pk) in texto


def test_pipeline_etapa_y_lead_se_muestran_legibles(empresa_a):
    pipeline = crear_pipeline(empresa_a, nombre="Ventas")
    etapa = crear_etapa(empresa_a, pipeline, nombre="Calificado")
    lead = crear_lead(empresa_a, pipeline, etapa, nombre="Pedro", apellido="Pérez")
    assert str(pipeline) == "Ventas"
    assert str(etapa) == "Ventas · Calificado"
    assert str(lead) == "Pedro Pérez"
