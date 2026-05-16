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
            name="PrediccionAgente",
            fields=[
                ("id_prediccion", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("id_empresa", models.ForeignKey(db_index=True, on_delete=django.db.models.deletion.CASCADE, to="core.empresa")),
                ("agente", models.CharField(choices=[("clasificador_gastos", "Clasificador de Gastos")], db_index=True, max_length=50)),
                ("input_texto", models.TextField()),
                ("input_monto", models.DecimalField(blank=True, decimal_places=2, max_digits=18, null=True)),
                ("input_metadata", models.JSONField(blank=True, default=dict)),
                ("categoria_predicha", models.CharField(max_length=100)),
                ("confianza", models.FloatField()),
                ("razonamiento", models.TextField(blank=True)),
                ("alternativas", models.JSONField(blank=True, default=list)),
                ("resultado_humano", models.CharField(choices=[("aceptada", "Aceptada por humano"), ("rechazada", "Rechazada por humano"), ("pendiente", "Pendiente revisión")], default="pendiente", max_length=20)),
                ("categoria_correcta", models.CharField(blank=True, max_length=100)),
                ("modelo_llm", models.CharField(default="fallback", max_length=100)),
                ("latencia_ms", models.IntegerField(default=0)),
                ("fecha_prediccion", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"ordering": ["-fecha_prediccion"]},
        ),
        migrations.AddIndex(
            model_name="prediccionagente",
            index=models.Index(fields=["id_empresa", "agente", "fecha_prediccion"], name="agentes_pre_id_empr_idx"),
        ),
        migrations.AddIndex(
            model_name="prediccionagente",
            index=models.Index(fields=["agente", "resultado_humano"], name="agentes_pre_agente_idx"),
        ),
    ]
