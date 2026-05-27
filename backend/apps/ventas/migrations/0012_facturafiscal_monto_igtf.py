from decimal import Decimal
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ventas", "0011_fix_unique_documentos_fiscales"),
    ]

    operations = [
        migrations.AddField(
            model_name="facturafiscal",
            name="monto_igtf",
            field=models.DecimalField(decimal_places=4, default=0.00, max_digits=18),
        ),
    ]
