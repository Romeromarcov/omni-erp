"""Migration: MovimientoBancario + ConciliacionBancaria."""
import apps.core.uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tesoreria", "0003_fix_unique_numero_operacion"),
        ("core", "0001_initial"),
        ("finanzas", "0018_pago"),
    ]

    operations = [
        migrations.CreateModel(
            name="MovimientoBancario",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.uuid.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("fecha_mov", models.DateField()),
                ("descripcion", models.CharField(max_length=300)),
                (
                    "tipo",
                    models.CharField(
                        choices=[("DEBITO", "Débito"), ("CREDITO", "Crédito")],
                        max_length=10,
                    ),
                ),
                ("monto", models.DecimalField(decimal_places=2, max_digits=18)),
                ("referencia", models.CharField(blank=True, max_length=100)),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("PENDIENTE", "Pendiente de conciliar"),
                            ("CONCILIADO", "Conciliado"),
                            ("DESCARTADO", "Descartado"),
                        ],
                        db_index=True,
                        default="PENDIENTE",
                        max_length=15,
                    ),
                ),
                (
                    "origen",
                    models.CharField(
                        choices=[
                            ("CSV", "Importado CSV"),
                            ("MANUAL", "Registrado manualmente"),
                            ("API", "API bancaria"),
                        ],
                        default="MANUAL",
                        max_length=20,
                    ),
                ),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                (
                    "id_empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="movimientos_bancarios",
                        to="core.empresa",
                    ),
                ),
                (
                    "id_cuenta_bancaria",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="movimientos_bancarios",
                        to="finanzas.cuentabancariaempresa",
                    ),
                ),
                (
                    "id_pago_conciliado",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="movimientos_bancarios_conciliados",
                        to="finanzas.pago",
                    ),
                ),
            ],
            options={
                "db_table": "tesoreria_movimiento_bancario",
                "ordering": ["-fecha_mov", "-fecha_creacion"],
            },
        ),
        migrations.AddIndex(
            model_name="movimientobancario",
            index=models.Index(fields=["id_empresa", "estado"], name="tesoreria_mov_empresa_estado_idx"),
        ),
        migrations.AddIndex(
            model_name="movimientobancario",
            index=models.Index(fields=["id_cuenta_bancaria", "fecha_mov"], name="tesoreria_mov_cuenta_fecha_idx"),
        ),
        migrations.CreateModel(
            name="ConciliacionBancaria",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=apps.core.uuid.uuid7,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("periodo_inicio", models.DateField()),
                ("periodo_fin", models.DateField()),
                (
                    "saldo_banco",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Saldo según extracto bancario",
                        max_digits=18,
                    ),
                ),
                (
                    "saldo_libro",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Saldo según libros contables",
                        max_digits=18,
                    ),
                ),
                ("diferencia", models.DecimalField(decimal_places=2, default=0, max_digits=18)),
                (
                    "estado",
                    models.CharField(
                        choices=[("ABIERTA", "Abierta"), ("CERRADA", "Cerrada")],
                        default="ABIERTA",
                        max_length=10,
                    ),
                ),
                ("movimientos_conciliados", models.IntegerField(default=0)),
                ("movimientos_pendientes", models.IntegerField(default=0)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_cierre", models.DateTimeField(blank=True, null=True)),
                ("observaciones", models.TextField(blank=True)),
                (
                    "id_empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conciliaciones_bancarias",
                        to="core.empresa",
                    ),
                ),
                (
                    "id_cuenta_bancaria",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conciliaciones",
                        to="finanzas.cuentabancariaempresa",
                    ),
                ),
                (
                    "realizada_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="core.usuarios",
                    ),
                ),
            ],
            options={
                "db_table": "tesoreria_conciliacion_bancaria",
                "ordering": ["-periodo_fin"],
            },
        ),
    ]
