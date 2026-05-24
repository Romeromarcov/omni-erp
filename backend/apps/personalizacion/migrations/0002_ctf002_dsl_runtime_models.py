"""
0002_ctf002_dsl_runtime_models.py

CTF-002: Agrega modelos para el runtime completo del DSL de personalización.
- EntidadInstancia: almacén EAV genérico para entidades definidas via DSL
- EstadoPersonalizado: estados extra de workflow definidos via DSL
- VistaPersonalizada: preferencias de columnas/filtros definidas via DSL
"""

import apps.core.uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("personalizacion", "0001_initial"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EntidadInstancia",
            fields=[
                ("id_instancia", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("id_empresa", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="entidades_instancias",
                    to="core.empresa",
                )),
                ("nombre_entidad", models.CharField(
                    db_index=True,
                    help_text="Nombre de la entidad DSL (ej: 'Equipo', 'Contrato')",
                    max_length=100,
                )),
                ("datos", models.JSONField(
                    default=dict,
                    help_text="Campos de la instancia según la definición DSL de la entidad",
                )),
                ("activo", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_modificacion", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Instancia de Entidad",
                "verbose_name_plural": "Instancias de Entidades",
                "db_table": "personalizacion_entidad_instancia",
            },
        ),
        migrations.AddIndex(
            model_name="entidadinstancia",
            index=models.Index(fields=["id_empresa", "nombre_entidad"], name="idx_ent_inst_emp_nombre"),
        ),
        migrations.CreateModel(
            name="EstadoPersonalizado",
            fields=[
                ("id_estado", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("id_empresa", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="estados_personalizados",
                    to="core.empresa",
                )),
                ("modelo", models.CharField(
                    help_text="Nombre del modelo Django al que aplica (ej: 'Pedido', 'Gasto')",
                    max_length=100,
                )),
                ("nombre", models.CharField(
                    help_text="Clave del estado (ej: 'EN_REVISION')",
                    max_length=50,
                )),
                ("etiqueta", models.CharField(
                    help_text="Texto para mostrar al usuario (ej: 'En Revisión')",
                    max_length=100,
                )),
                ("activo", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Estado Personalizado",
                "verbose_name_plural": "Estados Personalizados",
                "db_table": "personalizacion_estado_personalizado",
            },
        ),
        migrations.AlterUniqueTogether(
            name="estadopersonalizado",
            unique_together={("id_empresa", "modelo", "nombre")},
        ),
        migrations.AddIndex(
            model_name="estadopersonalizado",
            index=models.Index(fields=["id_empresa", "modelo"], name="idx_estado_pers_emp_modelo"),
        ),
        migrations.CreateModel(
            name="VistaPersonalizada",
            fields=[
                ("id_vista", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("id_empresa", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="vistas_personalizadas",
                    to="core.empresa",
                )),
                ("entidad", models.CharField(
                    help_text="Nombre del listado/entidad (ej: 'Cliente', 'Pedido')",
                    max_length=100,
                )),
                ("columnas", models.JSONField(
                    default=list,
                    help_text="Lista de nombres de columna a mostrar, en orden",
                )),
                ("filtros", models.JSONField(
                    default=dict,
                    help_text="Filtros por defecto para esta vista",
                )),
                ("activo", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Vista Personalizada",
                "verbose_name_plural": "Vistas Personalizadas",
                "db_table": "personalizacion_vista_personalizada",
            },
        ),
        migrations.AlterUniqueTogether(
            name="vistapersonalizada",
            unique_together={("id_empresa", "entidad")},
        ),
        migrations.AddIndex(
            model_name="vistapersonalizada",
            index=models.Index(fields=["id_empresa", "entidad"], name="idx_vista_pers_emp_entidad"),
        ),
    ]
