"""
TEST-1 — Guard de cobertura de aislamiento multi-tenant (R-CODE-1), auto-descubierto.

A diferencia de los tests de aislamiento por módulo (que verifican el COMPORTAMIENTO
cross-tenant con instancias reales), este test verifica ESTRUCTURALMENTE que **todo**
ViewSet expuesto en el URLconf que sirve un modelo tenant-aware (con FK a ``core.Empresa``)
sobreescribe ``get_queryset`` — el mecanismo de aislamiento.

Por qué importa: el ``get_queryset`` por defecto de DRF devuelve ``self.queryset`` SIN
filtrar por empresa. Si alguien registra un ViewSet nuevo sobre un modelo tenant y olvida
filtrar, este test **falla automáticamente** — blindando R-CODE-1 para el futuro sin que
nadie tenga que acordarse de escribir un test de aislamiento manual.

Cómo extender: si un ViewSet expone legítimamente un catálogo GLOBAL o aplica el filtrado
por otra vía justificada, añádelo a ``ALLOWLIST`` con el motivo. Cualquier otra fila obliga
a revisar antes de hacer merge.
"""

import pytest

from django.urls import get_resolver
from rest_framework.generics import GenericAPIView

from apps.core.models import Empresa


# ViewSets que NO requieren override de get_queryset, con su justificación.
# Formato: "modulo.ClaseViewSet": "motivo".
ALLOWLIST: dict[str, str] = {
    # Catálogos globales y ViewSets de la propia Empresa se filtran vía
    # get_empresas_visible / SuperuserWriteMixin, no por id_empresa del objeto.
    "apps.core.viewsets.EmpresaViewSet": "El modelo es la propia Empresa; se filtra por get_empresas_visible.",
}


def _empresa_fk_field(model):
    """Devuelve el nombre del campo FK a Empresa, o None si el modelo no es tenant-aware."""
    for field in model._meta.get_fields():
        if getattr(field, "many_to_one", False) and getattr(field, "related_model", None) is Empresa:
            return field.name
    return None


def _viewset_model(cls):
    """Modelo servido por un ViewSet (vía queryset o serializer Meta)."""
    qs = getattr(cls, "queryset", None)
    if qs is not None:
        return qs.model
    serializer = getattr(cls, "serializer_class", None)
    meta = getattr(serializer, "Meta", None)
    return getattr(meta, "model", None)


def _iter_view_classes(patterns):
    """Recorre recursivamente el URLconf y produce las clases de vista (DRF .cls)."""
    for pattern in patterns:
        sub = getattr(pattern, "url_patterns", None)
        if sub is not None:
            yield from _iter_view_classes(sub)
            continue
        cls = getattr(getattr(pattern, "callback", None), "cls", None)
        if cls is not None:
            yield cls


def _discover_tenant_viewsets():
    """
    Descubre todos los ViewSets registrados que sirven un modelo tenant-aware.
    Devuelve lista de (dotted_name, cls, model, empresa_field).
    """
    seen = set()
    result = []
    for cls in _iter_view_classes(get_resolver().url_patterns):
        dotted = f"{cls.__module__}.{cls.__qualname__}"
        if dotted in seen:
            continue
        seen.add(dotted)

        # Solo nos interesan vistas con get_queryset (GenericAPIView/ViewSet).
        if not hasattr(cls, "get_queryset"):
            continue
        model = None
        try:
            model = _viewset_model(cls)
        except Exception:
            model = None
        if model is None:
            continue
        empresa_field = _empresa_fk_field(model)
        if empresa_field is None:
            continue  # no es tenant-aware
        result.append((dotted, cls, model, empresa_field))
    return result


def _overrides_get_queryset(cls) -> bool:
    """True si la clase (o un mixin/base del proyecto) sobreescribe get_queryset."""
    return cls.get_queryset is not GenericAPIView.get_queryset


TENANT_VIEWSETS = _discover_tenant_viewsets()


def test_se_descubrieron_viewsets_tenant():
    """Sanity: la introspección encontró ViewSets tenant (si no, el guard sería inútil)."""
    assert len(TENANT_VIEWSETS) > 10, (
        f"Solo se descubrieron {len(TENANT_VIEWSETS)} ViewSets tenant; "
        "la introspección del URLconf puede estar rota."
    )


@pytest.mark.parametrize(
    "dotted,cls,model,empresa_field",
    TENANT_VIEWSETS,
    ids=[t[0] for t in TENANT_VIEWSETS],
)
def test_viewset_tenant_filtra_por_empresa(dotted, cls, model, empresa_field):
    """
    R-CODE-1: todo ViewSet sobre un modelo con FK a Empresa debe sobreescribir
    get_queryset (filtrado por empresa). Si este test falla para un ViewSet nuevo,
    añade el filtrado por empresa — o, si es un caso legítimo, agrégalo a ALLOWLIST
    con su justificación.
    """
    if dotted in ALLOWLIST:
        pytest.skip(f"Allowlist: {ALLOWLIST[dotted]}")
    assert _overrides_get_queryset(cls), (
        f"{dotted} sirve el modelo tenant-aware {model.__name__} "
        f"(FK '{empresa_field}'->Empresa) pero NO sobreescribe get_queryset: "
        "el get_queryset por defecto de DRF NO filtra por empresa → posible fuga "
        "cross-tenant (R-CODE-1). Filtra por empresa en get_queryset o justifica en ALLOWLIST."
    )
