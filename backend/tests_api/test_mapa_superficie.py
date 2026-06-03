"""Cubre el comando A1 `mapa_superficie` (Fase 0 — para satisfacer diff-cover)."""
import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_genera_matrices(tmp_path, monkeypatch):
    from apps.core.management.commands import mapa_superficie as cmd

    monkeypatch.setattr(cmd, "DOCS", tmp_path)
    call_command("mapa_superficie")
    endpoints = (tmp_path / "MAPA_ENDPOINTS.md").read_text(encoding="utf-8")
    modelos = (tmp_path / "MAPA_MODELOS.md").read_text(encoding="utf-8")
    assert "Mapa de endpoints" in endpoints
    assert "Total ViewSets" in endpoints
    assert "Mapa de modelos" in modelos
    # Debe detectar al menos un modelo tenant-aware y un ViewSet.
    assert "✅" in modelos
    assert "ViewSet" in endpoints


def test_check_al_dia_y_desactualizado(tmp_path, monkeypatch):
    from apps.core.management.commands import mapa_superficie as cmd

    monkeypatch.setattr(cmd, "DOCS", tmp_path)
    # Sin generar → --check debe fallar (SystemExit).
    with pytest.raises(SystemExit):
        call_command("mapa_superficie", "--check")
    # Tras generar → --check pasa.
    call_command("mapa_superficie")
    call_command("mapa_superficie", "--check")


def test_helpers_clasifican_tenant():
    from django.apps import apps as dj_apps

    from apps.core.management.commands.mapa_superficie import _es_tenant, _model_de
    from apps.crm.models import Cliente

    assert _es_tenant(Cliente) is True       # tiene id_empresa concreto
    assert _es_tenant(None) is False
    assert _model_de(object) is None          # objeto sin queryset/serializer

    # Existe al menos un modelo sin campo de empresa concreto → clasificado False.
    no_tenant = [
        m for m in dj_apps.get_models()
        if not ({f.name for f in m._meta.concrete_fields} & {"empresa", "id_empresa"})
    ]
    assert no_tenant, "se esperaba al menos un modelo no-tenant"
    assert _es_tenant(no_tenant[0]) is False
