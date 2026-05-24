import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rrhh", "0001_initial"),
        ("core", "0012_contacto"),
    ]

    operations = [
        migrations.AddField(
            model_name="empleado",
            name="contacto",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="empleado",
                to="core.contacto",
            ),
        ),
    ]
