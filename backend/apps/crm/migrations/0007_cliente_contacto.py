import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0006_add_credito_fields"),
        ("core", "0012_contacto"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="contacto",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cliente",
                to="core.contacto",
            ),
        ),
    ]
