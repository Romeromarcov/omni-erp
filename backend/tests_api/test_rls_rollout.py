"""Tests del rollout RLS completo — lote 3 (CTF-012 / P0-1).

Tres frentes:

1. **Registro vs. modelos**: ``rls.RLS_TABLES`` + ``rls.RLS_EXCLUDED_TABLES``
   deben cubrir *exactamente* los modelos con FK a ``core.Empresa`` (columna y
   nullabilidad incluidas). Un modelo tenant nuevo sin política RLS ni
   exclusión documentada rompe estos tests.
2. **Estado real en PostgreSQL** (parametrizado por tabla): política
   ``omni_rls_tenant`` presente en ``pg_policies`` con el predicado esperado,
   y ``ENABLE`` + ``FORCE ROW LEVEL SECURITY`` activos en ``pg_class``
   (``FORCE`` es lo que hace que la política aplique incluso al rol dueño).
3. **Aislamiento real** sobre tablas representativas del lote 3 (las tres
   variantes de columna y la semántica de catálogo compartido empresa-NULL),
   consultando el ORM SIN filtro por empresa, como en los lotes 1 y 2.
"""

import pytest

from django.apps import apps as django_apps
from django.db import connection

from apps.core import rls

pytestmark = [pytest.mark.django_db, pytest.mark.tenant]


@pytest.fixture(autouse=True)
def _enforce_rls_role(rls_test_role):
    """Corre el test bajo un rol sujeto a RLS si el rol de conexión la salta
    (CI superusuario); no-op en dev local. Ver tests_api/conftest.py."""
    if rls_test_role is None:
        yield
        return
    from django.db import connection as conn

    with conn.cursor() as cur:
        cur.execute(f'SET ROLE "{rls_test_role}"')
    try:
        yield
    finally:
        with conn.cursor() as cur:
            cur.execute("RESET ROLE")


def _modelos_tenant():
    """{tabla: (columna_empresa, nullable)} de todo modelo con FK a Empresa."""
    out = {}
    for model in django_apps.get_models(include_auto_created=True):
        meta = model._meta
        if not meta.managed or meta.proxy:
            continue
        for f in meta.local_fields:
            target = getattr(getattr(f, "remote_field", None), "model", None)
            if target is not None and target._meta.label == "core.Empresa":
                out[meta.db_table] = (f.column, f.null)
                break
    return out


# --- 1. Registro vs. modelos -------------------------------------------------


def test_registro_cubre_todo_modelo_tenant():
    tenant = _modelos_tenant()
    cubiertas = set(rls.RLS_TABLES) | set(rls.RLS_EXCLUDED_TABLES)
    faltantes = sorted(set(tenant) - cubiertas)
    assert not faltantes, (
        "Modelos con FK a Empresa sin RLS ni exclusión documentada. Agrega la "
        "tabla a una migración RLS + rls.RLS_TABLES, o a rls.RLS_EXCLUDED_TABLES "
        f"con su razón: {faltantes}"
    )


def test_registro_sin_tablas_fantasma():
    tenant = _modelos_tenant()
    fantasmas = sorted(
        (set(rls.RLS_TABLES) | set(rls.RLS_EXCLUDED_TABLES)) - set(tenant)
    )
    assert not fantasmas, f"Tablas en el registro RLS que ya no son modelos tenant: {fantasmas}"


def test_registro_columna_empresa_correcta_por_tabla():
    tenant = _modelos_tenant()
    mal = {
        t: {"registro": rls.RLS_TABLES[t], "modelo": tenant[t][0]}
        for t in rls.RLS_TABLES
        if t in tenant and rls.RLS_TABLES[t] != tenant[t][0]
    }
    assert not mal, f"Columna de empresa del registro no coincide con el modelo: {mal}"


def test_catalogos_compartidos_coinciden_con_nullabilidad():
    tenant = _modelos_tenant()
    esperado = {t for t in rls.RLS_TABLES if tenant.get(t, ("", False))[1]}
    assert esperado == set(rls.RLS_SHARED_NULL_TABLES), (
        "RLS_SHARED_NULL_TABLES debe ser exactamente el subconjunto de "
        "RLS_TABLES cuya columna de empresa es nullable. "
        f"Sobran: {sorted(set(rls.RLS_SHARED_NULL_TABLES) - esperado)} / "
        f"Faltan: {sorted(esperado - set(rls.RLS_SHARED_NULL_TABLES))}"
    )


def test_cubiertas_y_excluidas_disjuntas():
    solapadas = set(rls.RLS_TABLES) & set(rls.RLS_EXCLUDED_TABLES)
    assert not solapadas, f"Tablas a la vez cubiertas y excluidas: {sorted(solapadas)}"


# --- SQL builder: variante de catálogo compartido ----------------------------


def test_build_enable_sql_null_visible_agrega_clausula_is_null():
    sql = rls.build_enable_rls_sql("finanzas_moneda", "empresa_id", null_visible=True)
    assert '"empresa_id" IS NULL' in sql
    assert "FORCE ROW LEVEL SECURITY" in sql


def test_build_enable_sql_sin_null_visible_no_agrega_is_null():
    sql = rls.build_enable_rls_sql("ventas_pedido", "id_empresa_id")
    assert "IS NULL" not in sql


# --- 2. Estado real en PostgreSQL (pg_policies / pg_class) -------------------


@pytest.mark.parametrize("tabla", sorted(rls.RLS_TABLES))
def test_politica_activa_y_force_en_tabla(tabla):
    columna = rls.RLS_TABLES[tabla]
    with connection.cursor() as cur:
        cur.execute(
            "SELECT c.relrowsecurity, c.relforcerowsecurity"
            " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = 'public' AND c.relname = %s",
            [tabla],
        )
        estado = cur.fetchone()
        cur.execute(
            "SELECT qual, with_check FROM pg_policies"
            " WHERE schemaname = 'public' AND tablename = %s AND policyname = %s",
            [tabla, rls.POLICY_NAME],
        )
        politica = cur.fetchone()

    assert estado is not None, f"Tabla {tabla} no existe en el esquema public"
    assert estado[0], f"{tabla}: ROW LEVEL SECURITY no está ENABLE"
    assert estado[1], (
        f"{tabla}: falta FORCE ROW LEVEL SECURITY (sin FORCE el rol dueño "
        "salta la política)"
    )
    assert politica is not None, f"{tabla}: falta la política {rls.POLICY_NAME}"

    qual, with_check = politica
    assert columna in qual, f"{tabla}: la política no filtra por {columna}: {qual}"
    assert rls.GUC_EMPRESAS in qual and rls.GUC_BYPASS in qual, (
        f"{tabla}: la política no usa los GUC de sesión: {qual}"
    )
    es_compartida = tabla in rls.RLS_SHARED_NULL_TABLES
    assert (f"{columna} IS NULL" in qual) == es_compartida, (
        f"{tabla}: cláusula 'IS NULL' {'esperada' if es_compartida else 'inesperada'} "
        f"en la política: {qual}"
    )
    assert with_check == qual, f"{tabla}: WITH CHECK no es simétrico al USING"


# --- 3. Aislamiento real en tablas representativas del lote 3 ----------------


def _mk_almacen(empresa, marca):
    from apps.almacenes.models import Almacen

    return Almacen.objects.create(
        id_empresa=empresa, nombre_almacen=f"Almacén {marca}", codigo_almacen=f"AL-{marca}"
    )


def _mk_proveedor(empresa, marca):
    from apps.proveedores.models import Proveedor

    return Proveedor.objects.create(
        id_empresa=empresa, razon_social=f"Proveedor {marca}", rif=f"J-4040404{marca}"
    )


def _mk_categoria_gasto(empresa, marca):
    from apps.gastos.models import CategoriaGasto

    return CategoriaGasto.objects.create(
        id_empresa=empresa, nombre_categoria=f"Categoría {marca}"
    )


def _mk_categoria_ticket(empresa, marca):
    from apps.servicio_cliente.models import CategoriaTicket

    return CategoriaTicket.objects.create(
        id_empresa=empresa, nombre_categoria=f"Tickets {marca}"
    )


# (tabla, factory) — cubre apps distintas y la variante de columna por defecto.
_REPRESENTATIVAS = [
    ("almacenes_almacen", _mk_almacen),
    ("proveedores_proveedor", _mk_proveedor),
    ("gastos_categoriagasto", _mk_categoria_gasto),
    ("servicio_cliente_categoriaticket", _mk_categoria_ticket),
]


@pytest.mark.parametrize(
    "tabla,factory", _REPRESENTATIVAS, ids=[t for t, _ in _REPRESENTATIVAS]
)
def test_lote3_aisla_por_empresa_sin_filtro_de_aplicacion(
    tabla, factory, empresa_a, empresa_b
):
    rls.apply_system_default()
    obj_a = factory(empresa_a, "A")
    obj_b = factory(empresa_b, "B")
    modelo = type(obj_a)
    try:
        # Contexto = solo empresa A; el ORM consulta sin filtro por empresa.
        rls.apply_context([empresa_a.id_empresa], bypass=False)
        assert set(modelo.objects.values_list("pk", flat=True)) == {obj_a.pk}

        rls.apply_context([empresa_b.id_empresa], bypass=False)
        assert set(modelo.objects.values_list("pk", flat=True)) == {obj_b.pk}

        # Sin contexto => fail-closed; bypass => todo visible.
        rls.apply_context([], bypass=False)
        assert modelo.objects.count() == 0
        rls.apply_context([], bypass=True)
        assert set(modelo.objects.values_list("pk", flat=True)) == {obj_a.pk, obj_b.pk}
    finally:
        rls.apply_system_default()


@pytest.mark.parametrize("tabla", [t for t, _ in _REPRESENTATIVAS])
def test_lote3_no_permite_insertar_en_otra_empresa(tabla, empresa_a, empresa_b):
    from django.db import IntegrityError, transaction
    from django.db.utils import ProgrammingError

    factory = dict(_REPRESENTATIVAS)[tabla]
    rls.apply_system_default()
    try:
        rls.apply_context([empresa_a.id_empresa], bypass=False)
        with pytest.raises((IntegrityError, ProgrammingError)):
            with transaction.atomic():
                factory(empresa_b, "X")  # WITH CHECK debe rechazarlo
    finally:
        rls.apply_system_default()


def _mk_cargo(empresa, marca):
    from apps.rrhh.models import Cargo

    return Cargo.objects.create(empresa=empresa, nombre=f"Cargo {marca}")


def _mk_moneda(empresa, marca):
    from apps.finanzas.models import Moneda

    return Moneda.objects.create(
        empresa=empresa, codigo_iso=f"X{marca}", nombre=f"Moneda {marca}", simbolo="¤"
    )


def _mk_rol(empresa, marca):
    from apps.core.models import Roles

    return Roles.objects.create(id_empresa=empresa, nombre_rol=f"Rol {marca}")


# Catálogos compartidos (columna de empresa nullable): cubren las variantes
# empresa_id (rrhh/finanzas) e id_empresa con db_column (core.Roles).
_COMPARTIDAS = [
    ("rrhh_cargo", _mk_cargo),
    ("finanzas_moneda", _mk_moneda),
    ("roles", _mk_rol),
]


@pytest.mark.parametrize(
    "tabla,factory", _COMPARTIDAS, ids=[t for t, _ in _COMPARTIDAS]
)
def test_catalogo_compartido_fila_null_es_global_y_resto_aislado(
    tabla, factory, empresa_a, empresa_b
):
    rls.apply_system_default()
    obj_global = factory(None, "G")
    obj_a = factory(empresa_a, "A")
    obj_b = factory(empresa_b, "B")
    modelo = type(obj_global)
    creados = {obj_global.pk, obj_a.pk, obj_b.pk}

    def visibles():
        return set(modelo.objects.values_list("pk", flat=True)) & creados

    try:
        # Cada empresa ve lo global + lo suyo; nunca lo de la otra.
        rls.apply_context([empresa_a.id_empresa], bypass=False)
        assert visibles() == {obj_global.pk, obj_a.pk}

        rls.apply_context([empresa_b.id_empresa], bypass=False)
        assert visibles() == {obj_global.pk, obj_b.pk}

        # Sin contexto: solo lo global (fail-closed para filas con empresa).
        rls.apply_context([], bypass=False)
        assert visibles() == {obj_global.pk}

        rls.apply_context([], bypass=True)
        assert visibles() == creados
    finally:
        rls.apply_system_default()
