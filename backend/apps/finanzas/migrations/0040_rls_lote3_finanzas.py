"""RLS lote 3 (CTF-012, P0-1 rollout) — tablas tenant de ``finanzas``.

Genera la misma política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` de
los lotes 1 y 2 (ver ``apps/core/rls.py``). ``null_visible=True`` marca los
catálogos compartidos: empresa ``NULL`` = fila global visible por todos.
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("finanzas_caja_fisica", "empresa_id", True),
    ("finanzas_caja_virtual", "empresa_id", True),
    ("finanzas_cuenta_bancaria_empresa", "id_empresa_id", False),
    ("finanzas_datafono", "id_empresa_id", False),
    ("finanzas_metodo_pago", "empresa_id", True),
    ("finanzas_metodopagoempresaactiva", "empresa_id", False),
    ("finanzas_moneda", "empresa_id", True),
    ("finanzas_monedaempresaactiva", "empresa_id", False),
    ("finanzas_movimiento_caja_banco", "id_empresa_id", False),
    ("finanzas_pago", "id_empresa_id", False),
    ("finanzas_plantilla_maestro_cajas", "empresa_id", False),
    ("finanzas_sesion_caja_fisica", "empresa_id", False),
    ("finanzas_tasacambio", "id_empresa_id", True),
]


def _enable():
    return "\n".join(
        build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES
    )


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("finanzas", "0039_alter_cajavirtualauto_caja_fisica"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
