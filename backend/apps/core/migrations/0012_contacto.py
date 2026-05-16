import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_empresa_contabilidad_auto_aprobar"),
        ("ventas", "0009_listaprecio_detalleprecio"),
    ]

    operations = [
        migrations.CreateModel(
            name="Contacto",
            fields=[
                ("id_contacto", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                ("activo", models.BooleanField(default=True)),
                ("tipo_persona", models.CharField(
                    choices=[("NATURAL", "Persona Natural"), ("JURIDICA", "Persona Jurídica")],
                    default="JURIDICA",
                    max_length=10,
                )),
                ("nombre", models.CharField(max_length=255)),
                ("apellido", models.CharField(blank=True, default="", max_length=255)),
                ("nombre_comercial", models.CharField(blank=True, default="", max_length=255)),
                ("rif", models.CharField(blank=True, default="", max_length=20)),
                ("cedula", models.CharField(blank=True, default="", max_length=20)),
                ("email", models.EmailField(blank=True, default="")),
                ("telefono", models.CharField(blank=True, default="", max_length=50)),
                ("direccion_fiscal", models.TextField(blank=True, default="")),
                ("es_cliente", models.BooleanField(default=False)),
                ("es_proveedor", models.BooleanField(default=False)),
                ("es_empleado", models.BooleanField(default=False)),
                ("es_usuario", models.BooleanField(default=False)),
                ("tipo_credito", models.CharField(
                    choices=[("CONTADO", "Contado"), ("CREDITO", "Crédito")],
                    default="CONTADO",
                    max_length=10,
                )),
                ("limite_credito", models.DecimalField(decimal_places=2, default=0, max_digits=18)),
                ("dias_credito", models.PositiveSmallIntegerField(default=0)),
                ("dias_pago", models.PositiveSmallIntegerField(default=30)),
                (
                    "id_empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contactos",
                        to="core.empresa",
                    ),
                ),
                (
                    "lista_precio",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="contactos",
                        to="ventas.listaprecio",
                    ),
                ),
                (
                    "usuario",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="contacto",
                        to="core.usuarios",
                    ),
                ),
            ],
            options={
                "verbose_name": "Contacto",
                "verbose_name_plural": "Contactos",
                "db_table": "core_contacto",
            },
        ),
        migrations.AddIndex(
            model_name="contacto",
            index=models.Index(fields=["id_empresa", "es_cliente"], name="core_contacto_empresa_cliente_idx"),
        ),
        migrations.AddIndex(
            model_name="contacto",
            index=models.Index(fields=["id_empresa", "es_proveedor"], name="core_contacto_empresa_proveedor_idx"),
        ),
        migrations.AddIndex(
            model_name="contacto",
            index=models.Index(fields=["rif"], name="core_contacto_rif_idx"),
        ),
    ]
