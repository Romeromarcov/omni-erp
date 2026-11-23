"""RLS para tablas fiscales SENIAT 360° (retenciones IVA/ISLR e imprenta digital)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLES = [
    ("fiscal_comprobante_retencion_iva", "id_empresa_id", False),
    ("fiscal_comprobante_retencion_islr", "id_empresa_id", False),
    ("fiscal_documento_imprenta_digital", "id_empresa_id", False),
]


def _enable():
    return "\n".join(build_enable_rls_sql(t, c, null_visible=n) for t, c, n in _TABLES)


def _disable():
    return "\n".join(build_disable_rls_sql(t) for t, _c, _n in _TABLES)


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0012_seed_conceptos_islr_decreto_1808"),
    ]

    operations = [
        migrations.RunSQL(sql=_enable(), reverse_sql=_disable()),
    ]
