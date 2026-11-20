"""Backfill idempotente y reversible de ``Pago.id_contacto`` (PR-10 / Ola A1).

Popula ``id_contacto`` en pagos históricos que tienen ``id_contacto IS NULL``
siguiendo el orden de precedencia documental:
``id_factura.id_cliente.contacto`` → ``id_pedido.id_cliente.contacto`` →
``id_nota_venta.id_cliente.contacto`` → ``id_cxp.id_proveedor.contacto``.

Solo asigna el contacto si pertenece exactamente a la misma empresa del pago
(``contacto.id_empresa_id == pago.id_empresa_id``).
"""

from django.db import migrations
from django.db.models import Q

from apps.core.rls import rls_bypass

_BATCH_SIZE = 500


def _resolver_contacto_pago(pago):
    """Resuelve ``contacto_id`` desde el documento enlazado verificando misma empresa."""
    cadenas = (
        ("id_factura", "id_cliente"),
        ("id_pedido", "id_cliente"),
        ("id_nota_venta", "id_cliente"),
        ("id_cxp", "id_proveedor"),
    )
    for doc_attr, tercero_attr in cadenas:
        if not getattr(pago, f"{doc_attr}_id", None):
            continue
        doc = getattr(pago, doc_attr, None)
        if doc is None or not getattr(doc, f"{tercero_attr}_id", None):
            continue
        tercero = getattr(doc, tercero_attr, None)
        if tercero is None or not getattr(tercero, "contacto_id", None):
            continue
        contacto = getattr(tercero, "contacto", None)
        if contacto is not None and contacto.id_empresa_id == pago.id_empresa_id:
            return contacto.pk
    return None


def backfill_pago_id_contacto(apps, schema_editor):
    Pago = apps.get_model("finanzas", "Pago")
    alias = schema_editor.connection.alias

    with rls_bypass(using=alias):
        base_qs = (
            Pago.objects.using(alias)
            .filter(id_contacto__isnull=True)
            .filter(
                Q(id_factura__id_cliente__contacto__isnull=False)
                | Q(id_pedido__id_cliente__contacto__isnull=False)
                | Q(id_nota_venta__id_cliente__contacto__isnull=False)
                | Q(id_cxp__id_proveedor__contacto__isnull=False)
            )
            .select_related(
                "id_factura__id_cliente__contacto",
                "id_pedido__id_cliente__contacto",
                "id_nota_venta__id_cliente__contacto",
                "id_cxp__id_proveedor__contacto",
            )
            .order_by("id_pago")
        )

        ultimo_pk = None
        while True:
            chunk_qs = base_qs.filter(id_pago__gt=ultimo_pk) if ultimo_pk is not None else base_qs
            pagina = list(chunk_qs[:_BATCH_SIZE])
            if not pagina:
                break
            ultimo_pk = pagina[-1].id_pago

            lote = []
            for pago in pagina:
                contacto_id = _resolver_contacto_pago(pago)
                if contacto_id is not None:
                    pago.id_contacto_id = contacto_id
                    lote.append(pago)

            if lote:
                Pago.objects.using(alias).bulk_update(lote, ["id_contacto"])


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0007_cliente_contacto"),
        ("finanzas", "0043_rls_asignacion_pago"),
        ("proveedores", "0004_proveedor_contacto"),
    ]

    operations = [
        migrations.RunPython(
            code=backfill_pago_id_contacto,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
