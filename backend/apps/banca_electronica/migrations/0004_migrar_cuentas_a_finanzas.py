"""Migración de datos: consolida cuentas de banca_electronica en finanzas (PR-17 / Ola B5)."""

from django.db import migrations

from apps.core.rls import rls_bypass
from apps.core.uuid import uuid7


def migrar_cuentas_a_finanzas(apps, schema_editor):
    BancaCuenta = apps.get_model("banca_electronica", "CuentaBancariaEmpresa")
    FinanzasCuenta = apps.get_model("finanzas", "CuentaBancariaEmpresa")
    alias = schema_editor.connection.alias

    with rls_bypass(using=alias):
        for row in BancaCuenta.objects.using(alias).all().order_by("pk"):
            if FinanzasCuenta.objects.using(alias).filter(numero_cuenta=row.numero_cuenta).exists():
                continue
            tipo_cuenta = "CORRIENTE" if row.tipo_cuenta == "corriente" else "AHORRO"
            FinanzasCuenta.objects.using(alias).create(
                id_cuenta_bancaria=uuid7(),
                id_empresa_id=row.empresa_id,
                nombre_banco=row.banco,
                numero_cuenta=row.numero_cuenta,
                tipo_cuenta=tipo_cuenta,
                id_moneda_id=row.moneda_id,
                saldo_actual=row.saldo_actual,
                activo=row.activa,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("banca_electronica", "0003_rls_lote3_banca_electronica"),
        ("finanzas", "0044_backfill_pago_id_contacto"),
    ]

    operations = [
        migrations.RunPython(
            code=migrar_cuentas_a_finanzas,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
