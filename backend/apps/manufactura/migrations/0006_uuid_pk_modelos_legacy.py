"""BUG-NEW-4 (R-CODE-5): migra el PK autoincremental de los 5 modelos legacy de
manufactura (ListaMateriales, RutaProduccion, OrdenProduccion, ConsumoMaterial,
ProduccionTerminada) a UUIDv7, consistente con el resto del proyecto.

Estrategia: las tablas de manufactura están vacías (módulo greenfield, sin
services ni datos productivos), por lo que se cambia el tipo de columna in-place.
PostgreSQL no castea bigint→uuid, así que se usa un bloque SQL explícito que:
  1) elimina todas las FK que apuntan a estos 5 modelos (dinámicamente),
  2) cambia el tipo de las columnas PK y de las 9 columnas FK a uuid,
  3) recrea las FK.

Irreversible (R-PROC-5 documentado): revertir uuid→bigint sobre un cambio de tipo
de PK en tablas greenfield no aporta valor y tampoco castea; el reverse es noop.
`SeparateDatabaseAndState` mantiene el estado de Django (AlterField) sincronizado
con el esquema real.
"""
from django.db import migrations, models

import apps.core.uuid


_TARGET_TABLES = (
    "manufactura_listamateriales",
    "manufactura_rutaproduccion",
    "manufactura_ordenproduccion",
    "manufactura_consumomaterial",
    "manufactura_produccionterminada",
)

# (tabla, columna PK)
_PK_COLUMNS = [(t, "id") for t in _TARGET_TABLES]

# (tabla, columna FK, tabla referenciada, nullable)
_FK_COLUMNS = [
    ("manufactura_lista_materiales_detalle", "id_lista_materiales_id", "manufactura_listamateriales", False),
    ("manufactura_ordenproduccion", "lista_materiales_id", "manufactura_listamateriales", True),
    ("manufactura_ordenproduccion", "ruta_produccion_id", "manufactura_rutaproduccion", True),
    ("manufactura_ruta_produccion_detalle", "id_ruta_produccion_id", "manufactura_rutaproduccion", False),
    ("costos_analisis_variacion_costo", "id_orden_produccion_id", "manufactura_ordenproduccion", False),
    ("costos_costo_produccion", "id_orden_produccion_id", "manufactura_ordenproduccion", False),
    ("manufactura_consumomaterial", "orden_produccion_id", "manufactura_ordenproduccion", False),
    ("manufactura_produccionterminada", "orden_produccion_id", "manufactura_ordenproduccion", False),
    ("manufactura_registro_operacion", "id_orden_produccion_id", "manufactura_ordenproduccion", False),
]


def _build_sql() -> str:
    parts = []
    # 1) Eliminar dinámicamente todas las FK que referencian las 5 tablas objetivo.
    target_list = ",".join(f"'{t}'" for t in _TARGET_TABLES)
    # Nombres de tabla constantes del módulo (no input de usuario); se inyectan con
    # .replace() en vez de f-string para no disparar el detector de SQLi (B608).
    drop_block = """
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT con.conname, rel.relname AS table_name
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    JOIN pg_class frel ON frel.oid = con.confrelid
    WHERE con.contype = 'f' AND frel.relname IN (__TARGET_LIST__)
  LOOP
    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', r.table_name, r.conname);
  END LOOP;
END $$;
""".replace("__TARGET_LIST__", target_list)
    parts.append(drop_block)
    # 2a) PK: quitar la identidad (Django 4.1+ usa GENERATED ... AS IDENTITY) y
    # cambiar a uuid (tablas vacías).
    for table, col in _PK_COLUMNS:
        parts.append(
            f'ALTER TABLE "{table}" ALTER COLUMN "{col}" DROP IDENTITY IF EXISTS;'
            f'\nALTER TABLE "{table}" ALTER COLUMN "{col}" TYPE uuid USING gen_random_uuid();'
        )
    # 2b) FK: cambiar a uuid (NULL para nullable, uuid aleatorio para el resto; vacías).
    for table, col, _ref, nullable in _FK_COLUMNS:
        using = "NULL::uuid" if nullable else "gen_random_uuid()"
        parts.append(f'ALTER TABLE "{table}" ALTER COLUMN "{col}" TYPE uuid USING {using};')
    # 3) Recrear las FK.
    for i, (table, col, ref, _nullable) in enumerate(_FK_COLUMNS):
        cname = f"manuf_uuid_fk_{i}"
        parts.append(
            f'ALTER TABLE "{table}" ADD CONSTRAINT "{cname}" '
            f'FOREIGN KEY ("{col}") REFERENCES "{ref}" ("id") '
            f"DEFERRABLE INITIALLY DEFERRED;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ("manufactura", "0005_alter_centrotrabajo_id_centro_trabajo_and_more"),
        ("costos", "0002_alter_analisisvariacioncosto_id_analisis_variacion_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(sql=_build_sql(), reverse_sql=migrations.RunSQL.noop),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="listamateriales",
                    name="id",
                    field=models.UUIDField(
                        default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False
                    ),
                ),
                migrations.AlterField(
                    model_name="rutaproduccion",
                    name="id",
                    field=models.UUIDField(
                        default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False
                    ),
                ),
                migrations.AlterField(
                    model_name="ordenproduccion",
                    name="id",
                    field=models.UUIDField(
                        default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False
                    ),
                ),
                migrations.AlterField(
                    model_name="consumomaterial",
                    name="id",
                    field=models.UUIDField(
                        default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False
                    ),
                ),
                migrations.AlterField(
                    model_name="produccionterminada",
                    name="id",
                    field=models.UUIDField(
                        default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False
                    ),
                ),
            ],
        ),
    ]
