"""
Migration inicial de apps.cxc — Cobranza Inteligente.
Generada manualmente — ejecutar: python manage.py migrate cxc
"""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

import apps.core.uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("core", "0001_initial"),
        ("cuentas_por_cobrar", "0001_initial"),
        ("finanzas", "0001_initial"),
    ]

    operations = [

        # ── PlantillaCobranza ─────────────────────────────────────────────────
        migrations.CreateModel(
            name="PlantillaCobranza",
            fields=[
                ("id", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("empresa", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="cxc_plantillacobranza_set",
                    to="core.empresa",
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("nombre", models.CharField(max_length=100)),
                ("canal", models.CharField(
                    choices=[
                        ("whatsapp", "WhatsApp"),
                        ("email", "Email"),
                        ("sms", "SMS"),
                        ("carta", "Carta"),
                        ("llamada", "Guión Llamada"),
                    ],
                    max_length=20,
                )),
                ("asunto", models.CharField(blank=True, max_length=200)),
                ("cuerpo", models.TextField(
                    help_text="Variables: {cliente} {orden} {monto} {vencimiento} {dias_vencida}"
                )),
                ("activa", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Plantilla de Cobranza",
                "verbose_name_plural": "Plantillas de Cobranza",
            },
        ),
        migrations.AddIndex(
            model_name="plantillacobranza",
            index=models.Index(fields=["empresa", "canal", "activa"], name="cxc_planti_empresa_canal_activa_idx"),
        ),

        # ── GestionCobranza ───────────────────────────────────────────────────
        migrations.CreateModel(
            name="GestionCobranza",
            fields=[
                ("id", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("empresa", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="cxc_gestioncobranza_set",
                    to="core.empresa",
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("cliente_id", models.CharField(
                    help_text="ID del cliente (UUID Omni en Mode B, ID externo Odoo en Mode A)",
                    max_length=100,
                )),
                ("cliente_nombre", models.CharField(blank=True, max_length=255)),
                ("orden_ref", models.CharField(
                    blank=True,
                    help_text="Referencia de la orden/factura",
                    max_length=100,
                )),
                ("cxc", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="gestiones_cobranza",
                    to="cuentas_por_cobrar.cuentaporcobrar",
                )),
                ("canal", models.CharField(
                    choices=[
                        ("whatsapp", "WhatsApp"),
                        ("email", "Email"),
                        ("llamada", "Llamada"),
                        ("visita", "Visita"),
                        ("carta", "Carta"),
                    ],
                    max_length=20,
                )),
                ("resultado", models.CharField(
                    choices=[
                        ("contactado", "Contactado"),
                        ("sin_respuesta", "Sin Respuesta"),
                        ("promesa_pago", "Promesa de Pago"),
                        ("negativa", "Negativa"),
                        ("acuerdo_logrado", "Acuerdo Logrado"),
                    ],
                    max_length=30,
                )),
                ("notas", models.TextField(blank=True)),
                ("plantilla", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="gestiones",
                    to="cxc.plantillacobranza",
                )),
                ("score", models.DecimalField(decimal_places=4, default=0, max_digits=12)),
                ("fecha_gestion", models.DateField()),
                ("proxima_accion", models.DateField(
                    blank=True,
                    help_text="Fecha de próximo contacto (aplica cuando resultado=promesa_pago)",
                    null=True,
                )),
                ("gestionado_por", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="gestiones_cobranza",
                    to="core.usuarios",
                )),
            ],
            options={
                "verbose_name": "Gestión de Cobranza",
                "verbose_name_plural": "Gestiones de Cobranza",
                "ordering": ["-fecha_gestion"],
            },
        ),
        migrations.AddIndex(
            model_name="gestioncobranza",
            index=models.Index(fields=["empresa", "cliente_id"], name="cxc_gestion_empresa_cliente_idx"),
        ),
        migrations.AddIndex(
            model_name="gestioncobranza",
            index=models.Index(fields=["empresa", "proxima_accion"], name="cxc_gestion_empresa_prox_idx"),
        ),
        migrations.AddIndex(
            model_name="gestioncobranza",
            index=models.Index(fields=["empresa", "resultado", "fecha_gestion"], name="cxc_gestion_empresa_res_fecha_idx"),
        ),

        # ── AcuerdoPago ───────────────────────────────────────────────────────
        migrations.CreateModel(
            name="AcuerdoPago",
            fields=[
                ("id", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("empresa", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="cxc_acuerdopago_set",
                    to="core.empresa",
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("cliente_id", models.CharField(max_length=100)),
                ("cliente_nombre", models.CharField(blank=True, max_length=255)),
                ("cxc", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="acuerdos_pago",
                    to="cuentas_por_cobrar.cuentaporcobrar",
                )),
                ("gestion", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="acuerdos",
                    to="cxc.gestioncobranza",
                )),
                ("monto_total", models.DecimalField(decimal_places=4, max_digits=18)),
                ("periodicidad", models.CharField(
                    choices=[
                        ("unico", "Pago Único"),
                        ("semanal", "Semanal"),
                        ("quincenal", "Quincenal"),
                        ("mensual", "Mensual"),
                    ],
                    max_length=20,
                )),
                ("plazo_total_dias", models.PositiveIntegerField(default=30)),
                ("fecha_inicio", models.DateField()),
                ("monto_cuota", models.DecimalField(blank=True, decimal_places=4, max_digits=18, null=True)),
                ("porcentaje_abono", models.DecimalField(
                    blank=True,
                    decimal_places=2,
                    help_text="Porcentaje del total a pagar por cuota (0-100)",
                    max_digits=5,
                    null=True,
                )),
                ("estado", models.CharField(
                    choices=[
                        ("vigente", "Vigente"),
                        ("cumplido", "Cumplido"),
                        ("roto", "Roto"),
                        ("cancelado", "Cancelado"),
                    ],
                    default="vigente",
                    max_length=20,
                )),
                ("moneda_codigo", models.CharField(
                    default="USD",
                    help_text="Código ISO de moneda (USD, VES, etc.)",
                    max_length=5,
                )),
                ("observaciones", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "Acuerdo de Pago",
                "verbose_name_plural": "Acuerdos de Pago",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="acuerdopago",
            index=models.Index(fields=["empresa", "cliente_id", "estado"], name="cxc_acuerdo_empresa_cli_est_idx"),
        ),
        migrations.AddIndex(
            model_name="acuerdopago",
            index=models.Index(fields=["empresa", "estado"], name="cxc_acuerdo_empresa_estado_idx"),
        ),

        # ── CuotaAcuerdo ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name="CuotaAcuerdo",
            fields=[
                ("id", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("acuerdo", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="cuotas",
                    to="cxc.acuerdopago",
                )),
                ("numero_cuota", models.PositiveSmallIntegerField()),
                ("fecha_vencimiento", models.DateField()),
                ("monto", models.DecimalField(decimal_places=4, max_digits=18)),
                ("estado", models.CharField(
                    choices=[
                        ("pendiente", "Pendiente"),
                        ("pagado", "Pagado"),
                        ("parcial", "Parcial"),
                        ("vencido", "Vencido"),
                    ],
                    default="pendiente",
                    max_length=20,
                )),
                ("pago", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="cuotas_acuerdo",
                    to="finanzas.pago",
                )),
                ("monto_pagado", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                ("fecha_pago", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Cuota de Acuerdo",
                "verbose_name_plural": "Cuotas de Acuerdo",
                "ordering": ["numero_cuota"],
            },
        ),
        migrations.AddIndex(
            model_name="cuotaacuerdo",
            index=models.Index(fields=["acuerdo", "fecha_vencimiento", "estado"], name="cxc_cuota_acuerdo_fecha_est_idx"),
        ),

        # ── LoteFraccionado ───────────────────────────────────────────────────
        migrations.CreateModel(
            name="LoteFraccionado",
            fields=[
                ("id", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("empresa", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="cxc_lotefraccionado_set",
                    to="core.empresa",
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("producto_id", models.CharField(
                    help_text="ID del producto (Omni o externo Odoo)",
                    max_length=100,
                )),
                ("producto_nombre", models.CharField(max_length=255)),
                ("descripcion", models.TextField(blank=True)),
                ("cantidad_inicial", models.DecimalField(decimal_places=4, max_digits=14)),
                ("cantidad_actual", models.DecimalField(decimal_places=4, max_digits=14)),
                ("unidad_base", models.CharField(
                    help_text="Unidad de compra (kg, caja, etc.)",
                    max_length=20,
                )),
                ("unidad_venta", models.CharField(
                    help_text="Unidad de venta (g, unidad, etc.)",
                    max_length=20,
                )),
                ("factor_conversion", models.DecimalField(
                    decimal_places=6,
                    help_text="Cuántas unidades_venta hay en 1 unidad_base",
                    max_digits=14,
                )),
                ("precio_venta_unit", models.DecimalField(decimal_places=4, max_digits=18)),
                ("moneda_codigo", models.CharField(default="USD", max_length=5)),
                ("estado", models.CharField(
                    choices=[
                        ("activo", "Activo"),
                        ("agotado", "Agotado"),
                        ("cerrado", "Cerrado"),
                    ],
                    default="activo",
                    max_length=20,
                )),
            ],
            options={
                "verbose_name": "Lote Fraccionado",
                "verbose_name_plural": "Lotes Fraccionados",
            },
        ),
        migrations.AddIndex(
            model_name="lotefraccionado",
            index=models.Index(fields=["empresa", "estado"], name="cxc_lote_empresa_estado_idx"),
        ),

        # ── VentaFraccionada ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="VentaFraccionada",
            fields=[
                ("id", models.UUIDField(default=apps.core.uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("empresa", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="cxc_ventafraccionada_set",
                    to="core.empresa",
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("lote", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="ventas",
                    to="cxc.lotefraccionado",
                )),
                ("cliente_id", models.CharField(max_length=100)),
                ("cliente_nombre", models.CharField(blank=True, max_length=255)),
                ("cantidad", models.DecimalField(decimal_places=4, max_digits=14)),
                ("precio_unit", models.DecimalField(decimal_places=4, max_digits=18)),
                ("monto_total", models.DecimalField(decimal_places=4, max_digits=18)),
                ("moneda_codigo", models.CharField(default="USD", max_length=5)),
                ("estado", models.CharField(
                    choices=[
                        ("pendiente", "Pendiente"),
                        ("confirmada", "Confirmada"),
                        ("anulada", "Anulada"),
                    ],
                    default="pendiente",
                    max_length=20,
                )),
                ("pago", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="ventas_fraccionadas",
                    to="finanzas.pago",
                )),
                ("notas", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "Venta Fraccionada",
                "verbose_name_plural": "Ventas Fraccionadas",
                "ordering": ["-created_at"],
            },
        ),
    ]
