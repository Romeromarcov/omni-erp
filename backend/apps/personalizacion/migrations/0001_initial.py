import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0009_add_capability_token"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonalizacionConfig",
            fields=[
                ("id_config", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("id_empresa", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, to="core.empresa")),
                ("version", models.PositiveIntegerField(default=1)),
                ("descripcion", models.CharField(blank=True, max_length=200)),
                ("config_yaml", models.TextField()),
                ("config_dict", models.JSONField()),
                ("activo", models.BooleanField(db_index=True, default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_aplicacion", models.DateTimeField(blank=True, null=True)),
                ("resultado_aplicacion", models.JSONField(blank=True, null=True)),
            ],
            options={"ordering": ["-version"]},
        ),
        migrations.AlterUniqueTogether(
            name="personalizacionconfig",
            unique_together={("id_empresa", "version")},
        ),
    ]
