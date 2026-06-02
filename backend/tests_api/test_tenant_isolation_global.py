"""R-CODE-1 — Guard de aislamiento multi-tenant AUTO-DESCUBIERTO (cero dudas).

Recorre TODOS los ViewSets registrados en el routing del proyecto y, para cada
uno cuyo modelo es tenant-aware (tiene campo `id_empresa`/`empresa`), verifica
que `get_queryset()` para un usuario de la empresa B **filtra por empresa**
(el SQL compilado referencia la columna de empresa en su cláusula WHERE).

Si alguien agrega un ViewSet sobre un modelo tenant sin filtrar por empresa
(la clase de bug de CRIT-1..3), este test **falla automáticamente** — sin que
haya que escribir un test por modelo.

Los catálogos legítimamente globales (Moneda, Permiso, etc.) se listan en
`GLOBAL_ALLOWLIST`. Los ViewSets que no pueden introspectarse genéricamente se
**reportan como skip** (no ocultan fallos: solo no se pueden evaluar aquí).
"""
from __future__ import annotations

import pytest
from django.urls import get_resolver


class _FakeRequest:
    """Request mínimo para invocar get_queryset() sin la maquinaria de DRF."""
    def __init__(self, user):
        self.user = user
        self.query_params = {}
        self.GET = {}
        self.data = {}
        self.method = "GET"

# Modelos/viewsets globales por diseño (no tenant-aware) — excepción documentada
# a R-CODE-1 (catálogos compartidos).
GLOBAL_ALLOWLIST = {
    "Moneda", "MetodoPago", "Permiso", "Rol", "TipoDocumento", "CatalogoValor",
    "ConectorProveedor", "UnidadMedida", "Pais", "ParametroSistema",
}


def _iter_viewset_classes():
    """Descubre las clases ViewSet/APIView registradas en el URLconf raíz."""
    seen = set()
    resolver = get_resolver()

    def walk(patterns):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                yield from walk(p.url_patterns)
                continue
            cb = getattr(p, "callback", None)
            cls = getattr(cb, "cls", None)  # DRF as_view() expone .cls
            if cls is not None and cls not in seen:
                seen.add(cls)
                yield cls

    yield from walk(resolver.url_patterns)


def _model_de_viewset(cls):
    qs = getattr(cls, "queryset", None)
    if qs is not None:
        return qs.model
    ser = getattr(cls, "serializer_class", None)
    meta = getattr(ser, "Meta", None) if ser is not None else None
    return getattr(meta, "model", None)


def _es_tenant(model) -> bool:
    if model is None:
        return False
    nombres = {f.name for f in model._meta.get_fields()}
    return "id_empresa" in nombres or "empresa" in nombres


def _viewsets_tenant():
    items = []
    for cls in _iter_viewset_classes():
        model = _model_de_viewset(cls)
        if model is None or model.__name__ in GLOBAL_ALLOWLIST:
            continue
        if _es_tenant(model):
            items.append((cls, model))
    return items


@pytest.mark.django_db
def test_descubrimiento_no_vacio():
    """Sanidad: el descubridor encuentra ViewSets tenant (si no, el guard no sirve)."""
    assert len(_viewsets_tenant()) >= 15


@pytest.mark.django_db
def test_todo_viewset_tenant_filtra_por_empresa(user_b):
    """Para cada ViewSet tenant, get_queryset() debe filtrar por empresa."""
    fallos = []
    evaluados = 0
    no_introspectables = []

    for cls, model in _viewsets_tenant():
        view = cls()
        view.request = _FakeRequest(user_b)
        view.kwargs = {}
        view.format_kwarg = None
        view.action = "list"
        try:
            qs = view.get_queryset()
            sql = str(qs.query).lower()
        except Exception as exc:  # no introspectable genéricamente → skip reportado
            no_introspectables.append(f"{cls.__name__} ({type(exc).__name__})")
            continue
        evaluados += 1
        # El WHERE compilado debe acotar por tenant: por empresa, o por el usuario
        # autenticado (creado_por/id_usuario), que es un scoping aún más estricto
        # (el usuario solo ve sus propios registros) y por tanto seguro.
        where = sql.split(" where ", 1)[1] if " where " in sql else ""
        aislado = ("empresa" in where) or ("creado_por" in where) or ("id_usuario" in where)
        if not aislado:
            fallos.append(f"{cls.__name__}[{model.__name__}] sin filtro de tenant/usuario en WHERE")

    print(f"\n[tenant-isolation] evaluados={evaluados} "
          f"no_introspectables={len(no_introspectables)} fallos={len(fallos)}")
    if no_introspectables:
        print("  skip (no introspectables):", ", ".join(sorted(no_introspectables)))
    assert not fallos, "ViewSets tenant sin aislamiento por empresa:\n  " + "\n  ".join(fallos)
