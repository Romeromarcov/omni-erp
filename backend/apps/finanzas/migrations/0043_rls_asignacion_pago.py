"""RLS para finanzas_asignacion_pago (PR-10 / Ola A1).

Activa RLS + FORCE ROW LEVEL SECURITY con política ``omni_rls_tenant`` sobre
``finanzas_asignacion_pago`` (``id_empresa_id``, fail-closed ``null_visible=False``).
"""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql


class Migration(migrations.Migration):
    dependencies = [
        ("finanzas", "0042_asignacionpago_y_pago_contacto"),
    ]

    operations = [
        migrations.RunSQL(
            sql=build_enable_rls_sql("finanzas_asignacion_pago", "id_empresa_id", null_visible=False),
            reverse_sql=build_disable_rls_sql("finanzas_asignacion_pago"),
        ),
    ]
