"""CTF-005 — whitelist explícita de campos en serializers.

Cierra el Compromiso Técnico Fechado CTF-005 (`docs/ctf/CTF-005.md`): los
serializers de ``ventas``, ``compras`` y ``core`` dejaron de usar
``fields = "__all__"`` (asignación masiva — CWE-915) y declaran una lista
explícita de campos. La **fase 2** extiende el mismo blindaje a los módulos de
**dinero y nómina** (``finanzas``, ``nomina``), donde la superficie de
asignación masiva toca pagos, cajas y salarios (PII sensible).

- ``test_sin_fields_all_*``: **guard estructural permanente** — falla si alguien
  reintroduce ``fields = "__all__"`` en estos módulos.
- ``test_campo_fuera_de_whitelist_se_ignora``: comportamiento — un campo que no
  está en la whitelist no se asigna al crear (defensa en profundidad).
"""

import importlib
import inspect

import pytest

from rest_framework.serializers import ModelSerializer

MODULOS_WHITELIST = [
    "apps.core.serializers",
    "apps.ventas.serializers",
    "apps.compras.serializers",
    # Fase 2 — dinero & nómina (CWE-915 sobre pagos, cajas y salarios/PII).
    "apps.finanzas.serializers",
    "apps.nomina.serializers",
]


def _serializers_con_all(modulo):
    """Devuelve los nombres de ModelSerializer del módulo con ``fields='__all__'``."""
    m = importlib.import_module(modulo)
    ofensores = []
    for nombre, obj in inspect.getmembers(m, inspect.isclass):
        if not issubclass(obj, ModelSerializer) or obj.__module__ != m.__name__:
            continue
        meta = getattr(obj, "Meta", None)
        if meta is not None and getattr(meta, "fields", None) == "__all__":
            ofensores.append(nombre)
    return ofensores


@pytest.mark.parametrize("modulo", MODULOS_WHITELIST)
def test_sin_fields_all_en_modulos_criticos(modulo):
    """Ningún serializer de ventas/compras/core usa ``fields='__all__'`` (CTF-005)."""
    ofensores = _serializers_con_all(modulo)
    assert ofensores == [], (
        f"{modulo} reintroduce fields='__all__' en: {ofensores}. "
        "Usa una whitelist explícita de campos (CTF-005, CWE-915)."
    )


@pytest.mark.django_db
def test_campo_fuera_de_whitelist_se_ignora(empresa_a):
    """Un campo no declarado en la whitelist se ignora al crear (no se asigna)."""
    from apps.core.models import Departamento
    from apps.core.serializers import DepartamentoSerializer

    # ``is_superuser`` y ``campo_inventado`` NO están en la whitelist del serializer.
    payload = {
        "nombre_departamento": "Ventas",
        "id_empresa": str(empresa_a.id_empresa),
        "is_superuser": True,
        "campo_inventado": "x" * 10,
    }
    serializer = DepartamentoSerializer(data=payload)
    assert serializer.is_valid(), serializer.errors

    # Los campos fuera de la whitelist ni siquiera entran a validated_data.
    assert "is_superuser" not in serializer.validated_data
    assert "campo_inventado" not in serializer.validated_data

    depto = serializer.save()
    assert isinstance(depto, Departamento)
    assert depto.nombre_departamento == "Ventas"
    assert depto.id_empresa_id == empresa_a.id_empresa
    # No se creó ningún atributo espurio en la instancia persistida.
    assert not hasattr(depto, "campo_inventado")
