from django.db import migrations


class Migration(migrations.Migration):
    """
    Agrega ordering a Caja (Caja Virtual) y CuentaBancariaEmpresa
    para eliminar UnorderedObjectListWarning en paginación.
    """

    dependencies = [
        ("finanzas", "0034_fix_sesion_caja_unique_constraint"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="caja",
            options={
                "ordering": ["empresa", "nombre"],
                "verbose_name": "Caja Virtual",
                "verbose_name_plural": "Cajas Virtuales",
            },
        ),
        migrations.AlterModelOptions(
            name="cuentabancariaempresa",
            options={
                "ordering": ["id_empresa", "nombre_banco"],
                "verbose_name": "Cuenta Bancaria Empresa",
                "verbose_name_plural": "Cuentas Bancarias Empresa",
            },
        ),
    ]
