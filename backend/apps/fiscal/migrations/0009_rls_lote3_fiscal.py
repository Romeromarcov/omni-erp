"""RLS lote 3 (CTF-012, P0-1 rollout) — tablas tenant de ``fiscal``.

Genera la misma política ``omni_rls_tenant`` + ``FORCE ROW LEVEL SECURITY`` de
los lotes 1 y 2 (ver ``apps/core/rls.py``). ``null_visible=True`` marca los
catálogos compartidos: empresa ``NULL`` = fila global visible por todos.
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

# (tabla, columna_empresa, null_visible)
_TABLES = [
    ("fiscal_configuracion_empresa", "id_empresa_id", False),
    ("fiscal_configuracionimpuesto", "empresa_id", False),
    ("fiscal_configuracionretencion", "empresa_id", False),
    ("fiscal_contribucionempresaactiva", "empresa_id", False),
    ("fiscal_contribucionparafiscal", "empresa_id", True),
    ("fiscal_pago_contribucion_parafiscal", "id_empresa_id", False),
    ("fiscal_empresacontribucionparafiscal", "empresa_id", False),
    ("fiscal_impuesto", "empresa_id", True),
    ("fiscal_impuestoempresaactiva", "empresa_id", False),
    ("fiscal_numero_correlativo", "id_empresa_id", False),
    ("fiscal_periodo_fiscal", "id_empresa_id", False),
    ("fiscal_retencionempresaactiva", "empresa_id", False),
    ("fiscal_tasa_iva_empresa", "id_empresa_id", False),
]


def _enable():
    return "\n".join(
        build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES
    )


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0008_pagocontribucionparafiscal_ck_pago_parafiscal_mes_entre_1_y_12_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
