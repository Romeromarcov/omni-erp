"""Backfill idempotente de ``email_normalizado`` y ``telefono_normalizado`` en ``core.Contacto`` (S5)."""

from django.db import migrations
from django.db.models import Q

from apps.core.rls import rls_bypass
from apps.core.validators import normalizar_email, normalizar_telefono

_BATCH_SIZE = 500


def backfill_contacto_normalizado(apps, schema_editor):
    """Popula ``email_normalizado`` y ``telefono_normalizado`` bajo ``rls_bypass()``."""
    Contacto = apps.get_model("core", "Contacto")
    alias = schema_editor.connection.alias

    with rls_bypass(using=alias):
        base_qs = Contacto.objects.using(alias).filter(Q(email__gt="") | Q(telefono__gt="")).order_by("id_contacto")

        ultimo_pk = None
        while True:
            chunk_qs = base_qs.filter(id_contacto__gt=ultimo_pk) if ultimo_pk is not None else base_qs
            pagina = list(chunk_qs[:_BATCH_SIZE])
            if not pagina:
                break
            ultimo_pk = pagina[-1].id_contacto

            lote = []
            for contacto in pagina:
                email_norm = normalizar_email(getattr(contacto, "email", ""))
                tel_norm = normalizar_telefono(getattr(contacto, "telefono", ""))
                if contacto.email_normalizado != email_norm or contacto.telefono_normalizado != tel_norm:
                    contacto.email_normalizado = email_norm
                    contacto.telefono_normalizado = tel_norm
                    lote.append(contacto)

            if lote:
                Contacto.objects.using(alias).bulk_update(
                    lote,
                    ["email_normalizado", "telefono_normalizado"],
                )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0026_contacto_email_normalizado_and_more"),
    ]

    operations = [
        migrations.RunPython(
            code=backfill_contacto_normalizado,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
