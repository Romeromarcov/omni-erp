"""RLS para finanzas_tipo_tasa_cambio (Plan 09 — Ola 1A).

Activa RLS + FORCE ROW LEVEL SECURITY con política ``omni_rls_tenant`` sobre
``finanzas_tipo_tasa_cambio`` (``id_empresa_id``, catálogo compartido
``null_visible=True`` para permitir tipos globales como ``OFICIAL_BCV``).
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql


class Migration(migrations.Migration):
    dependencies = [
        ("finanzas", "0045_tipotasacambio_y_moneda_referencia"),
    ]

    operations = [
        migrations.RunSQL(
            sql=build_enable_rls_sql("finanzas_tipo_tasa_cambio", "id_empresa_id", null_visible=True),
            reverse_sql=build_disable_rls_sql("finanzas_tipo_tasa_cambio"),
        ),
    ]
