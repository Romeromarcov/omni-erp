"""RLS piloto (P0-1) — tablas de cxc (columna ``empresa_id``)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = ["cxc_gestioncobranza", "cxc_acuerdopago"]


def _enable():
    return "\n".join(build_enable_rls_sql(t, "empresa_id") for t in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t in _TABLES)


class Migration(migrations.Migration):

    dependencies = [
        ("cxc", "0002_rename_cxc_acuerdo_empresa_cli_est_idx_cxc_acuerdo_empresa_942c39_idx_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
