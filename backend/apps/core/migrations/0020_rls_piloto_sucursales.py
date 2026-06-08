"""RLS piloto (P0-1) — tabla ``sucursales`` (columna ``id_empresa`` por db_column)."""

from django.db import migrations

from apps.core.rls import build_disable_rls_sql, build_enable_rls_sql

_TABLE = "sucursales"
_COLUMN = "id_empresa"


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_empresa_localizacion_legal_activa_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=build_enable_rls_sql(_TABLE, _COLUMN),
            reverse_sql=build_disable_rls_sql(_TABLE),
        ),
    ]
