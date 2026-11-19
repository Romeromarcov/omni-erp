# Generated for P1-5: Inmutabilidad de auditoria (R13)

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("auditoria", "0004_rls_lote3_auditoria"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION omni_prevent_logauditoria_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'La tabla de auditoría % es inmutable (append-only): % no permitido.',
                    TG_TABLE_NAME, TG_OP
                    USING ERRCODE = '42501';
            END;
            $$;

            DROP TRIGGER IF EXISTS trg_prevent_logauditoria_mutation ON auditoria_logauditoria;
            CREATE TRIGGER trg_prevent_logauditoria_mutation
            BEFORE UPDATE OR DELETE ON auditoria_logauditoria
            FOR EACH ROW
            EXECUTE FUNCTION omni_prevent_logauditoria_mutation();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS trg_prevent_logauditoria_mutation ON auditoria_logauditoria;
            DROP FUNCTION IF EXISTS omni_prevent_logauditoria_mutation();
            """,
        ),
    ]
