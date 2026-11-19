# Generated for P1-5: Inmutabilidad de auditoria (R13)

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0024_contacto_gps"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION omni_prevent_registro_auditoria_mutation()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION 'La tabla de auditoría % es inmutable (append-only): % no permitido.',
                    TG_TABLE_NAME, TG_OP
                    USING ERRCODE = '42501';
            END;
            $$;

            DROP TRIGGER IF EXISTS trg_prevent_registro_auditoria_mutation ON registro_auditoria;
            CREATE TRIGGER trg_prevent_registro_auditoria_mutation
            BEFORE UPDATE OR DELETE ON registro_auditoria
            FOR EACH ROW
            EXECUTE FUNCTION omni_prevent_registro_auditoria_mutation();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS trg_prevent_registro_auditoria_mutation ON registro_auditoria;
            DROP FUNCTION IF EXISTS omni_prevent_registro_auditoria_mutation();
            """,
        ),
    ]
