"""
SEC-M1 (Auditoría integral 2026-06-10) — Scope de tenant para FKs writable en serializers.

Problema sistémico: DRF autogenera los ``PrimaryKeyRelatedField`` de todo
``ModelSerializer`` con el manager COMPLETO del modelo destino
(``Modelo.objects.all()``). Eso permite que un POST/PATCH inyecte el id de un
objeto de OTRA empresa (p. ej. ``id_pedido`` ajeno en un detalle de pedido, o
``id_cliente`` ajeno en un pedido — que además filtra nombre/RIF/teléfono de la
víctima en la representación).

Solución: ``TenantFKScopeMixin`` (mixin de ViewSet) intercepta ``get_serializer``
y RESTRINGE el queryset de cada campo relacional writable cuyo modelo destino es
tenant-aware a las empresas visibles del usuario (``get_empresas_visible``):

- FK directa a ``core.Empresa`` (``id_empresa``/``empresa``);
- modelos "detalle" con FK a Empresa a 2 saltos (DetallePedido→Pedido→Empresa);
- el modelo de usuario (membresía vía M2M ``empresas``);
- la propia ``Empresa`` como destino.

Si la FK a Empresa del modelo destino es nullable, las filas globales
(``empresa=None`` — catálogos compartidos) siguen siendo elegibles para todos.

Garantías de diseño:
- **Solo restringe, nunca amplía**: se aplica ``.filter()`` sobre el queryset que
  ya tenga el campo, así que los serializers que ya hacían su propio scoping
  conservan sus restricciones (intersección, no reemplazo).
- Barato: ``get_empresas_visible`` se evalúa una sola vez por serializer.
- No toca campos read-only ni la representación de salida (los querysets de
  ``RelatedField`` solo se usan para validar input).

Guard que lo hace obligatorio: ``tests/tenant/test_fk_tenant_scope.py`` (todo
ViewSet de escritura con FKs tenant-aware debe heredar este mixin, y un POST con
un pk de otra empresa debe responder 400).
"""

from __future__ import annotations

from django.db.models import Q
from rest_framework import relations, serializers


def _empresa_fk(model):
    """FK concreta y directa del modelo a ``core.Empresa`` (o None)."""
    from apps.core.models import Empresa

    for f in model._meta.concrete_fields:
        if f.is_relation and f.many_to_one and f.related_model is Empresa:
            return f
    return None


def _tenant_scope_cond(model):
    """
    Cómo restringir ``model`` a un conjunto de empresas, o None si el modelo
    no es tenant-aware. Devuelve ``(path, null_paths)``: ``path`` para el
    lookup ``__in`` y rutas nullable que habilitan filas globales
    (``empresa=None``, catálogos compartidos).

    Cubre FK directa a Empresa y modelos "detalle" (FK a Empresa a 2 saltos,
    p. ej. DetallePedido→Pedido→Empresa), espejo del guard SEC-B1.
    """
    fk = _empresa_fk(model)
    if fk is not None:
        return fk.name, ([fk.name] if fk.null else [])
    # 2 saltos: FK a un modelo padre que sí tiene FK directa a Empresa.
    for f in model._meta.concrete_fields:
        if f.is_relation and f.many_to_one and f.related_model is not model:
            parent_fk = _empresa_fk(f.related_model)
            if parent_fk is not None:
                nulls = []
                if f.null:
                    nulls.append(f.name)
                if parent_fk.null:
                    nulls.append(f"{f.name}__{parent_fk.name}")
                return f"{f.name}__{parent_fk.name}", nulls
    return None


def _scoped_queryset(queryset, empresas_visibles):
    """
    Devuelve el queryset RESTRINGIDO a empresas visibles, o None si el modelo
    destino no es tenant-aware (sin FK a Empresa a 1-2 saltos) y no debe tocarse.
    """
    from django.contrib.auth import get_user_model

    from apps.core.models import Empresa

    model = queryset.model
    if model is Empresa:
        return queryset.filter(pk__in=empresas_visibles.values("pk"))
    if model is get_user_model():
        # La membresía multi-tenant del usuario es la M2M ``empresas`` (no la FK
        # nullable ``id_sucursal_predeterminada``, bypasseable con null): un FK
        # writable a usuario solo puede apuntar a usuarios de empresas visibles.
        return queryset.filter(empresas__in=empresas_visibles).distinct()
    scope = _tenant_scope_cond(model)
    if scope is None:
        return None
    path, null_paths = scope
    cond = Q(**{f"{path}__in": empresas_visibles})
    for null_path in null_paths:
        # Filas globales (empresa=None): catálogos compartidos entre tenants.
        cond |= Q(**{f"{null_path}__isnull": True})
    return queryset.filter(cond)


def scope_tenant_fks(serializer, empresas_visibles, _seen=None):
    """
    Recorre los campos del serializer (incl. anidados y many=True) y acota el
    queryset de todo campo relacional writable cuyo destino sea tenant-aware.
    """
    if _seen is None:
        _seen = set()
    if id(serializer) in _seen:
        return
    _seen.add(id(serializer))

    if isinstance(serializer, serializers.ListSerializer):
        scope_tenant_fks(serializer.child, empresas_visibles, _seen)
        return
    fields = getattr(serializer, "fields", None)
    if fields is None:
        return

    for field in fields.values():
        # Serializers anidados writable (nested create) también validan FKs.
        if isinstance(field, serializers.BaseSerializer):
            if not field.read_only:
                scope_tenant_fks(field, empresas_visibles, _seen)
            continue
        target = field.child_relation if isinstance(field, relations.ManyRelatedField) else field
        if not isinstance(target, relations.RelatedField) or target.read_only:
            continue
        queryset = getattr(target, "queryset", None)
        if queryset is None:
            continue
        if hasattr(queryset, "all") and not hasattr(queryset, "model"):
            continue  # objeto exótico sin modelo: no introspeccionable
        scoped = _scoped_queryset(queryset, empresas_visibles)
        if scoped is not None:
            target.queryset = scoped
            target._tenant_fk_scoped = True


class TenantFKScopeMixin:
    """
    Mixin de ViewSet: engancha el scope de tenant en ``get_serializer``.

    Se eligió el enganche a nivel de ViewSet (y no una clase base de serializer)
    porque el serializer no conoce al usuario hasta tener el request en su
    context, y porque TODOS los serializers de escritura del ERP se instancian
    vía ``get_serializer`` — una sola línea de MRO cubre el ViewSet completo,
    incluidos los campos autogenerados por DRF.
    """

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        request = getattr(self, "request", None)
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            from apps.core.viewsets import get_empresas_visible

            scope_tenant_fks(serializer, get_empresas_visible(user))
        return serializer
