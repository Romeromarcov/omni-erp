"""RLS de Omni Connect (S1) — tablas tenant de ``connect``.

Misma política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` que los lotes
1–3 (ver ``apps/core/rls.py``). Ninguna tabla es catálogo compartido, así que
``null_visible=False``: sin contexto de empresa no se ve ninguna fila.
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("connect_perfil", "id_empresa_id", False),
    ("connect_tarjeta", "id_empresa_id", False),
    ("connect_toque", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("connect", "0001_connect_inicial"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
