import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0008_remove_pagopedido_banco_destino_and_more"),
        ("core", "0011_empresa_contabilidad_auto_aprobar"),
        ("finanzas", "0001_initial"),
        ("inventario", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ListaPrecio",
            fields=[
                ("id_lista", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("nombre", models.CharField(max_length=100)),
                ("codigo", models.CharField(max_length=20)),
                ("es_referencia", models.BooleanField(default=False)),
                ("activo", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                (
                    "id_empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="listas_precio",
                        to="core.empresa",
                    ),
                ),
                (
                    "id_moneda",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="listas_precio",
                        to="finanzas.moneda",
                    ),
                ),
            ],
            options={
                "verbose_name": "Lista de Precios",
                "verbose_name_plural": "Listas de Precios",
                "db_table": "ventas_lista_precio",
            },
        ),
        migrations.AlterUniqueTogether(
            name="listaprecio",
            unique_together={("id_empresa", "codigo")},
        ),
        migrations.CreateModel(
            name="DetallePrecio",
            fields=[
                ("id_detalle", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("precio", models.DecimalField(decimal_places=4, max_digits=18)),
                ("precio_minimo", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                ("vigente_desde", models.DateField(blank=True, null=True)),
                ("vigente_hasta", models.DateField(blank=True, null=True)),
                ("activo", models.BooleanField(default=True)),
                (
                    "id_lista",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="detalles",
                        to="ventas.listaprecio",
                    ),
                ),
                (
                    "id_producto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="precios_lista",
                        to="inventario.producto",
                    ),
                ),
            ],
            options={
                "verbose_name": "Detalle de Precio",
                "verbose_name_plural": "Detalles de Precio",
                "db_table": "ventas_detalle_precio",
            },
        ),
        migrations.AlterUniqueTogether(
            name="detalleprecio",
            unique_together={("id_lista", "id_producto")},
        ),
    ]
