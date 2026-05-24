import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("proveedores", "0003_alter_contactoproveedor_options_and_more"),
        ("core", "0012_contacto"),
    ]

    operations = [
        migrations.AddField(
            model_name="proveedor",
            name="contacto",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proveedor",
                to="core.contacto",
            ),
        ),
    ]
