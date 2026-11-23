"""Seed idempotente de 35 conceptos oficiales de Retención ISLR (Decreto 1808 VE)."""

from decimal import Decimal
import uuid

from django.db import migrations


_CONCEPTOS_DECRETO_1808 = [
    ("001", "Honorarios profesionales no mercantiles (PNR)", "PNR", "100.00", "3.00", True, "83.3334"),
    ("002", "Honorarios profesionales no mercantiles (PNNR)", "PNNR", "90.00", "34.00", False, "0.0000"),
    ("003", "Honorarios profesionales no mercantiles (PJDO)", "PJDO", "100.00", "5.00", False, "0.0000"),
    ("004", "Honorarios profesionales no mercantiles (PJND)", "PJND", "90.00", "34.00", False, "0.0000"),
    ("005", "Honorarios médicos y paramédicos en clínicas (PNR)", "PNR", "100.00", "3.00", True, "83.3334"),
    ("006", "Comisiones mercantiles y bursátiles (PNR)", "PNR", "100.00", "3.00", True, "83.3334"),
    ("007", "Comisiones mercantiles y bursátiles (PNNR)", "PNNR", "100.00", "34.00", False, "0.0000"),
    ("008", "Comisiones mercantiles y bursátiles (PJDO)", "PJDO", "100.00", "5.00", False, "0.0000"),
    ("009", "Comisiones mercantiles por venta de inmuebles (PJDO)", "PJDO", "100.00", "5.00", False, "0.0000"),
    ("010", "Intereses a instituciones financieras (PJND)", "PJND", "100.00", "4.95", False, "0.0000"),
    ("011", "Intereses a personas jurídicas no domiciliadas (PJND)", "PJND", "100.00", "34.00", False, "0.0000"),
    ("012", "Intereses a personas naturales residentes (PNR)", "PNR", "100.00", "3.00", True, "83.3334"),
    ("013", "Intereses a personas jurídicas domiciliadas (PJDO)", "PJDO", "100.00", "5.00", False, "0.0000"),
    ("014", "Contratistas y subcontratistas de obras o servicios (PNR)", "PNR", "100.00", "1.00", True, "83.3334"),
    ("015", "Contratistas y subcontratistas de obras o servicios (PJDO)", "PJDO", "100.00", "2.00", False, "0.0000"),
    ("016", "Arrendamiento de bienes inmuebles (PNR)", "PNR", "100.00", "3.00", True, "83.3334"),
    ("017", "Arrendamiento de bienes inmuebles (PJDO)", "PJDO", "100.00", "5.00", False, "0.0000"),
    ("018", "Arrendamiento de bienes muebles (PNR)", "PNR", "100.00", "3.00", True, "83.3334"),
    ("019", "Arrendamiento de bienes muebles (PJDO)", "PJDO", "100.00", "5.00", False, "0.0000"),
    ("020", "Cánones de arrendamiento financieros (PJND)", "PJND", "100.00", "34.00", False, "0.0000"),
    ("021", "Gastos de transporte y fletes terrestres (PNR)", "PNR", "100.00", "1.00", True, "83.3334"),
    ("022", "Gastos de transporte y fletes terrestres (PJDO)", "PJDO", "100.00", "3.00", False, "0.0000"),
    ("023", "Publicidad, propaganda y cuñas (PNR)", "PNR", "100.00", "3.00", True, "83.3334"),
    ("024", "Publicidad, propaganda y cuñas (PJDO)", "PJDO", "100.00", "5.00", False, "0.0000"),
    ("025", "Emisoras de radio y televisión publicidad (PJDO)", "PJDO", "100.00", "3.00", False, "0.0000"),
    ("026", "Primas de seguros y reaseguros (PJND)", "PJND", "30.00", "10.00", False, "0.0000"),
    ("027", "Corretaje de seguros (PNR)", "PNR", "100.00", "3.00", True, "83.3334"),
    ("028", "Corretaje de seguros (PJDO)", "PJDO", "100.00", "5.00", False, "0.0000"),
    ("029", "Asistencia técnica del exterior (PJND)", "PJND", "30.00", "34.00", False, "0.0000"),
    ("030", "Servicios tecnológicos y regalías del exterior (PJND)", "PJND", "50.00", "34.00", False, "0.0000"),
    ("031", "Regalías y participación análoga domiciliadas (PJDO)", "PJDO", "90.00", "5.00", False, "0.0000"),
    ("032", "Servicios técnicos y mantenimiento equipos (PNR)", "PNR", "100.00", "1.00", True, "83.3334"),
    ("033", "Servicios técnicos y mantenimiento equipos (PJDO)", "PJDO", "100.00", "2.00", False, "0.0000"),
    ("034", "Pagos con tarjetas de crédito / débito en comercios (PJDO)", "PJDO", "100.00", "3.00", False, "0.0000"),
    ("035", "Ganancias fortuitas, loterías e hipódromos (PNR)", "PNR", "100.00", "34.00", False, "0.0000"),
]


def _seed(apps, schema_editor):
    Concepto = apps.get_model("fiscal", "ConceptoRetencionISLR")
    for codigo, nombre, tipo_persona, base_pct, pct_ret, aplica_sust, factor_ut in _CONCEPTOS_DECRETO_1808:
        Concepto.objects.update_or_create(
            codigo=codigo,
            defaults={
                "id": uuid.uuid5(uuid.NAMESPACE_DNS, f"omni-erp.islr.1808.{codigo}"),
                "nombre": nombre,
                "tipo_persona_fiscal": tipo_persona,
                "base_imponible_pct": Decimal(base_pct),
                "porcentaje_retencion": Decimal(pct_ret),
                "aplica_sustraendo": aplica_sust,
                "factor_sustraendo_ut": Decimal(factor_ut),
                "activo": True,
            },
        )


def _unseed(apps, schema_editor):
    Concepto = apps.get_model("fiscal", "ConceptoRetencionISLR")
    codigos = [row[0] for row in _CONCEPTOS_DECRETO_1808]
    Concepto.objects.filter(codigo__in=codigos).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0011_blindaje_seniat_retenciones_imprenta"),
    ]

    operations = [
        migrations.RunPython(code=_seed, reverse_code=_unseed),
    ]
