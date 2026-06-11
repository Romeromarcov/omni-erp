"""
TEST-3 / SEC-M1 — FKs writable acotadas a tenant en serializers, auto-descubierto.

Complementa al guard estructural (TEST-1, ``test_aislamiento_cobertura.py``) y al de
comportamiento GET/PATCH/DELETE (TEST-2): aquí cubrimos la **inyección de FK en
CREATE** — ``POST`` con el id de un objeto de la Empresa B debe ser rechazado (400)
para un usuario de la Empresa A, en TODOS los endpoints de escritura del router.

Dos capas:

1. **Estructural** (``test_viewset_escritura_tiene_scope_de_fk``): todo ViewSet con
   ``POST → create`` cuyo serializer expone FKs writable hacia modelos tenant-aware
   debe incluir ``TenantFKScopeMixin`` en su MRO (es el mecanismo que acota los
   querysets de validación a ``get_empresas_visible``).

2. **Comportamiento** (``test_post_con_fk_ajena_rechazada``): para cada
   (endpoint, campo FK) se construye una instancia REAL del modelo destino en la
   Empresa B (builder genérico) y se hace ``POST {campo: pk_ajeno}`` como usuario
   de A: la respuesta debe ser 4xx y, si la validación corrió (400), el campo debe
   figurar en los errores con "no existe" — prueba de que el queryset está acotado.

Cómo extender: si un campo apunta legítimamente a un catálogo global/cross-tenant,
añádelo a ``ALLOWLIST_CAMPOS`` con su motivo.
"""

import itertools
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from django.urls import get_resolver
from django.utils import timezone
from rest_framework import relations, serializers
from rest_framework.test import APIClient

from apps.core.models import Empresa
from apps.core.serializer_mixins import TenantFKScopeMixin, _tenant_scope_cond

pytestmark = [pytest.mark.django_db, pytest.mark.tenant]


# ---------------------------------------------------------------------------
# Allowlists documentadas
# ---------------------------------------------------------------------------

# Campos FK que legítimamente NO se acotan por tenant (catálogos globales, etc.).
# Formato: "modulo.ViewSet.campo": "motivo".
ALLOWLIST_CAMPOS: dict[str, str] = {
    "apps.cuentas_por_cobrar.views_abono.AbonoCxCViewSet.usuario": (
        "create custom (BUG-C1) que NO usa el serializer para validar input: "
        "delega en el service registrar_abono, inyecta usuario=request.user "
        "(ignora el payload) y valida el tenant de la CxC manualmente. El 400 "
        "temprano por 'cuenta_por_cobrar requerido' impide observar el error de "
        "campo que espera este test, pero el FK ajeno nunca se persiste."
    ),
}

# ViewSets de escritura que no usan el mixin por una razón justificada.
ALLOWLIST_VIEWSETS: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Descubrimiento: endpoints de escritura del router + FKs tenant-aware writable
# ---------------------------------------------------------------------------


def _iter_write_endpoints():
    """(cls, url) por cada endpoint list con POST→create registrado en el URLconf."""

    def walk(patterns, prefix):
        for p in patterns:
            sub = getattr(p, "url_patterns", None)
            piece = str(p.pattern)
            if sub is not None:
                yield from walk(sub, prefix + piece)
                continue
            cb = getattr(p, "callback", None)
            cls = getattr(cb, "cls", None)
            actions = getattr(cb, "actions", None) or {}
            if cls is not None and actions.get("post") == "create":
                yield cls, prefix + piece

    yield from walk(get_resolver().url_patterns, "")


def _clean_url(raw: str) -> str | None:
    """Convierte el patrón acumulado en URL invocable; None si tiene parámetros."""
    if "(?P<" in raw or "<" in raw:
        return None  # rutas con captura (detail o sufijo .format): no son el POST list
    return "/" + raw.replace("^", "").replace("$", "")


def _writable_tenant_fk_fields(serializer_cls):
    """[(nombre_campo, modelo_destino)] de FKs writable hacia modelos tenant-aware."""
    try:
        ser = serializer_cls()
        fields = ser.fields
    except Exception:
        return []
    found = []
    for name, field in fields.items():
        target = field.child_relation if isinstance(field, relations.ManyRelatedField) else field
        if isinstance(field, serializers.BaseSerializer):
            continue  # anidados: cubiertos por la recursión del mixin
        if not isinstance(target, relations.RelatedField) or target.read_only:
            continue
        qs = getattr(target, "queryset", None)
        if qs is None or not hasattr(qs, "model"):
            continue
        model = qs.model
        from django.contrib.auth import get_user_model

        if model is Empresa or model is get_user_model() or _tenant_scope_cond(model) is not None:
            found.append((name, model))
    return found


def _discover_cases():
    write_viewsets = []  # (dotted, cls, url) con al menos una FK tenant writable
    field_cases = []  # (dotted, cls, url, campo, modelo_destino)
    seen = set()
    for cls, raw_url in _iter_write_endpoints():
        url = _clean_url(raw_url)
        if url is None:
            continue
        dotted = f"{cls.__module__}.{cls.__qualname__}"
        if dotted in seen:
            continue
        seen.add(dotted)
        serializer_cls = getattr(cls, "serializer_class", None)
        if serializer_cls is None:
            continue  # serializer dinámico: lo cubre el guard estructural TEST-1
        fk_fields = _writable_tenant_fk_fields(serializer_cls)
        if not fk_fields:
            continue
        write_viewsets.append((dotted, cls, url))
        for name, model in fk_fields:
            field_cases.append((dotted, cls, url, name, model))
    return write_viewsets, field_cases


WRITE_VIEWSETS, FIELD_CASES = _discover_cases()


# ---------------------------------------------------------------------------
# Builder genérico de instancias mínimas (para poblar la Empresa B)
# ---------------------------------------------------------------------------

_seq = itertools.count(1)


def _dummy_value(f):
    n = next(_seq)
    choices = getattr(f, "choices", None)
    if choices:
        return choices[0][0]
    t = f.get_internal_type()
    if t in ("CharField", "SlugField"):
        val = f"x{n}"
        return val[: f.max_length] if f.max_length else val
    if t == "TextField":
        return f"texto {n}"
    if t == "EmailField":
        return f"t{n}@test.local"
    if t == "URLField":
        return f"https://test.local/{n}"
    if t in ("IntegerField", "BigIntegerField", "SmallIntegerField",
             "PositiveIntegerField", "PositiveSmallIntegerField", "PositiveBigIntegerField"):
        return 1
    if t == "DecimalField":
        return Decimal("1")
    if t == "FloatField":
        return 1.0
    if t == "BooleanField":
        return False
    if t == "DateField":
        return date.today()
    if t == "DateTimeField":
        return timezone.now()
    if t == "TimeField":
        return timezone.now().time()
    if t == "DurationField":
        return timedelta(hours=1)
    if t == "UUIDField":
        return uuid.uuid4()
    if t == "JSONField":
        return {}
    if t == "GenericIPAddressField":
        return "127.0.0.1"
    if t == "BinaryField":
        return b""
    raise NotImplementedError(f"Sin valor dummy para {t}")


def _build_instance(model, empresa, _stack=()):
    """Crea una instancia mínima de ``model`` perteneciente a ``empresa``."""
    if model is Empresa:
        return empresa
    if model in _stack:
        raise RuntimeError(f"ciclo de FKs requeridas en {model.__name__}")
    kwargs = {}
    for f in model._meta.concrete_fields:
        if f.auto_created or f.primary_key:
            continue
        if f.is_relation:
            if f.related_model is Empresa:
                kwargs[f.name] = empresa
            elif f.null or f.has_default():
                continue
            else:
                kwargs[f.name] = _build_instance(f.related_model, empresa, (*_stack, model))
            continue
        if getattr(f, "auto_now", False) or getattr(f, "auto_now_add", False):
            continue
        if f.has_default() or f.null:
            continue
        kwargs[f.name] = _dummy_value(f)
    obj = model(**kwargs)
    obj.save()
    # El modelo de usuario es tenant vía M2M `empresas`: lo afiliamos a la
    # empresa para que el caso sea "usuario DE la Empresa B" (no un huérfano).
    from django.contrib.auth import get_user_model

    if model is get_user_model():
        obj.empresas.add(empresa)
    return obj


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_se_descubrieron_endpoints_de_escritura():
    """Sanity: la introspección encontró endpoints de escritura con FKs tenant."""
    assert len(FIELD_CASES) > 30, (
        f"Solo se descubrieron {len(FIELD_CASES)} campos FK tenant en endpoints de "
        "escritura; la introspección del router puede estar rota."
    )


@pytest.mark.parametrize(
    "dotted,cls,url",
    WRITE_VIEWSETS,
    ids=[c[0] for c in WRITE_VIEWSETS],
)
def test_viewset_escritura_tiene_scope_de_fk(dotted, cls, url):
    """
    SEC-M1: todo ViewSet de escritura cuyo serializer expone FKs writable hacia
    modelos tenant-aware debe heredar TenantFKScopeMixin (acota los querysets de
    validación a get_empresas_visible). Si tu ViewSet es un caso legítimo,
    justifícalo en ALLOWLIST_VIEWSETS.
    """
    if dotted in ALLOWLIST_VIEWSETS:
        pytest.skip(f"Allowlist: {ALLOWLIST_VIEWSETS[dotted]}")
    assert issubclass(cls, TenantFKScopeMixin), (
        f"{dotted} ({url}) acepta POST con FKs writable hacia modelos tenant-aware "
        "pero NO hereda TenantFKScopeMixin: un cliente puede inyectar ids de otra "
        "empresa (SEC-M1 / R-CODE-1). Añade el mixin al MRO o justifica en "
        "ALLOWLIST_VIEWSETS."
    )


@pytest.mark.parametrize(
    "dotted,cls,url,campo,modelo",
    FIELD_CASES,
    ids=[f"{c[0]}.{c[3]}" for c in FIELD_CASES],
)
def test_post_con_fk_ajena_rechazada(dotted, cls, url, campo, modelo, user_a, empresa_b):
    """
    SEC-M1 (comportamiento): POST como usuario de Empresa A con ``{campo: pk}`` de
    un objeto REAL de Empresa B → la API debe responder 4xx y, si la validación
    corrió (400 con errores por campo), el campo debe figurar en los errores
    (el pk ajeno "no existe" dentro del queryset acotado).
    """
    key = f"{dotted}.{campo}"
    if key in ALLOWLIST_CAMPOS:
        pytest.skip(f"Allowlist: {ALLOWLIST_CAMPOS[key]}")

    try:
        ajeno = _build_instance(modelo, empresa_b)
    except (Exception,) as exc:  # modelo no construible genéricamente
        # Fallback estructural: el mixin debe estar en el MRO (la capa de
        # comportamiento de este mecanismo ya se prueba con los modelos sí
        # construibles; aquí garantizamos que el ViewSet no quedó fuera).
        assert issubclass(cls, TenantFKScopeMixin), (
            f"No se pudo construir {modelo.__name__} ({exc}) y {dotted} no hereda "
            "TenantFKScopeMixin."
        )
        return

    client = APIClient()
    client.force_authenticate(user=user_a)
    resp = client.post(url, {campo: str(ajeno.pk)}, format="json")

    assert 400 <= resp.status_code < 500, (
        f"{dotted} ({url}): POST con {campo} de Empresa B devolvió "
        f"{resp.status_code}; se esperaba 4xx (rechazo)."
    )
    if resp.status_code == 400 and isinstance(resp.data, dict):
        # Si la validación de serializer corrió, el campo ajeno DEBE estar entre
        # los errores (queryset acotado → "Invalid pk ... object does not exist").
        assert campo in resp.data, (
            f"{dotted} ({url}): el POST falló con 400 pero NO por el campo "
            f"{campo!r} (errores: {list(resp.data)}). El pk de Empresa B fue "
            "aceptado por la validación → FK sin scope de tenant (SEC-M1)."
        )
