"""
M5 — Control de Salidas Internas de Inventario:
  - Agrega SALIDA_INTERNA a MovimientoInventario.tipo_movimiento
  - Crea RequisicionInterna y DetalleRequisicion
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("almacenes", "0001_initial"),
        ("core", "0012_contacto"),
        ("inventario", "0004_alter_categoriaproducto_options_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Ampliar choices de MovimientoInventario ───────────────────────────
        migrations.AlterField(
            model_name="movimientoinventario",
            name="tipo_movimiento",
            field=models.CharField(
                choices=[
                    ("ENTRADA", "Entrada"),
                    ("SALIDA", "Salida"),
                    ("TRANSFERENCIA", "Transferencia"),
                    ("AJUSTE", "Ajuste"),
                    ("CONSUMO_PRODUCCION", "Consumo Producción"),
                    ("RECEPCION_COMPRA", "Recepción Compra"),
                    ("DESPACHO_VENTA", "Despacho Venta"),
                    ("SALIDA_INTERNA", "Salida Interna"),
                ],
                max_length=50,
            ),
        ),
        # ── RequisicionInterna ────────────────────────────────────────────────
        migrations.CreateModel(
            name="RequisicionInterna",
            fields=[
                (
                    "id_requisicion",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("activo", models.BooleanField(default=True)),
                ("fecha_creacion", models.DateTimeField(auto_now_add=True)),
                ("fecha_actualizacion", models.DateTimeField(auto_now=True)),
                ("numero_requisicion", models.CharField(max_length=30)),
                (
                    "estado",
                    models.CharField(
                        choices=[
                            ("BORRADOR", "Borrador"),
                            ("APROBADA", "Aprobada"),
                            ("DESPACHADA", "Despachada"),
                            ("CANCELADA", "Cancelada"),
                        ],
                        default="BORRADOR",
                        max_length=12,
                    ),
                ),
                ("fecha_solicitud", models.DateField(auto_now_add=True)),
                ("fecha_aprobacion", models.DateField(blank=True, null=True)),
                ("observaciones", models.TextField(blank=True, default="")),
                (
                    "aprobado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="requisiciones_internas_aprobadas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "id_almacen_origen",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="requisiciones_origen",
                        to="almacenes.almacen",
                    ),
                ),
                (
                    "id_departamento_destino",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="requisiciones_recibidas",
                        to="core.departamento",
                    ),
                ),
                (
                    "id_empresa",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="requisiciones_internas",
                        to="core.empresa",
                    ),
                ),
                (
                    "solicitado_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="requisiciones_internas_solicitadas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Requisición Interna",
                "verbose_name_plural": "Requisiciones Internas",
                "db_table": "inventario_requisicion_interna",
                "unique_together": {("id_empresa", "numero_requisicion")},
            },
        ),
        # ── DetalleRequisicion ────────────────────────────────────────────────
        migrations.CreateModel(
            name="DetalleRequisicion",
            fields=[
                (
                    "id_detalle",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("cantidad_solicitada", models.DecimalField(decimal_places=4, max_digits=18)),
                ("cantidad_despachada", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                (
                    "id_producto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="detalles_requisicion_interna",
                        to="inventario.producto",
                    ),
                ),
                (
                    "id_requisicion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="detalles",
                        to="inventario.requisicioninterna",
                    ),
                ),
                (
                    "id_variante",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="inventario.varianteproducto",
                    ),
                ),
            ],
            options={
                "verbose_name": "Detalle de Requisición",
                "verbose_name_plural": "Detalles de Requisición",
                "db_table": "inventario_detalle_requisicion",
                "unique_together": {("id_requisicion", "id_producto")},
            },
        ),
    ]
