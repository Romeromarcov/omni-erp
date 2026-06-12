"""RLS lote 3 (CTF-012, P0-1 rollout) — tablas tenant de ``cxc``.

Genera la misma política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` de
los lotes 1 y 2 (ver ``apps/core/rls.py``). ``null_visible=True`` marca los
catálogos compartidos: empresa ``NULL`` = fila global visible por todos.
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("cxc_lotefraccionado", "empresa_id", False),
    ("cxc_plantillacobranza", "empresa_id", False),
    ("cxc_ventafraccionada", "empresa_id", False),
]


def _enable():
    return "\n".join(
        build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES
    )


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("cxc", "0003_rls_piloto_cxc"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
