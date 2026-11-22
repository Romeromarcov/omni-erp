from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql


class Migration(migrations.Migration):
    dependencies = [
        ("banca_electronica", "0005_consolidar_y_lotes_pago"),
    ]

    operations = [
        migrations.RunSQL(
            sql=build_enable_rls_sql("banca_electronica_lote_pago", "id_empresa_id", null_visible=False),
            reverse_sql=build_disable_rls_sql("banca_electronica_lote_pago"),
        ),
    ]
