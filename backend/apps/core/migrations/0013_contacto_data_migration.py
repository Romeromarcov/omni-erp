"""
Data migration (M1-T2 Strangler Fig):
  - For each Cliente without a contacto FK, create a Contacto row and link it.
  - For each Proveedor without a contacto FK, do the same.
  - When a Cliente and Proveedor share the same empresa + RIF, they get ONE shared
    Contacto with both es_cliente=True and es_proveedor=True.

Reverse migration: detaches the FK links (Contacto rows are left in place so that
any real FK child data is not destroyed).
"""
import uuid

from django.db import migrations


def _create_contacto_for_cliente(apps, cliente):
    """Create and return an unsaved Contacto populated from a Cliente."""
    Contacto = apps.get_model("core", "Contacto")
    return Contacto(
        id_contacto=uuid.uuid4(),
        id_empresa_id=cliente.id_empresa_id,
        tipo_persona="JURIDICA",
        nombre=cliente.razon_social or "",
        apellido="",
        nombre_comercial=getattr(cliente, "nombre_comercial", "") or "",
        rif=cliente.rif or "",
        email=getattr(cliente, "email", "") or "",
        telefono=getattr(cliente, "telefono", "") or "",
        es_cliente=True,
        es_proveedor=False,
        tipo_credito=getattr(cliente, "tipo_cliente", "CONTADO") or "CONTADO",
        limite_credito=getattr(cliente, "limite_credito", 0) or 0,
        dias_credito=getattr(cliente, "dias_credito", 0) or 0,
        dias_pago=30,
    )


def _create_contacto_for_proveedor(apps, proveedor):
    """Create and return an unsaved Contacto populated from a Proveedor."""
    Contacto = apps.get_model("core", "Contacto")
    return Contacto(
        id_contacto=uuid.uuid4(),
        id_empresa_id=proveedor.id_empresa_id,
        tipo_persona="JURIDICA",
        nombre=proveedor.razon_social or "",
        apellido="",
        nombre_comercial=getattr(proveedor, "nombre_comercial", "") or "",
        rif=proveedor.rif or "",
        email=getattr(proveedor, "email", "") or "",
        telefono=getattr(proveedor, "telefono", "") or "",
        es_cliente=False,
        es_proveedor=True,
        tipo_credito="CONTADO",
        limite_credito=0,
        dias_credito=0,
        dias_pago=30,
    )


def forwards(apps, schema_editor):
    Cliente = apps.get_model("crm", "Cliente")
    Proveedor = apps.get_model("proveedores", "Proveedor")
    Contacto = apps.get_model("core", "Contacto")

    # ── Pass 1: Clientes ─────────────────────────────────────────────────────
    # Build lookup: (empresa_id, rif) → Contacto for merge detection.
    contacto_by_key = {}

    clientes_sin_contacto = Cliente.objects.filter(contacto__isnull=True).select_related()
    for cliente in clientes_sin_contacto:
        key = (cliente.id_empresa_id, cliente.rif)
        if key not in contacto_by_key:
            new_contacto = _create_contacto_for_cliente(apps, cliente)
            new_contacto.save()
            contacto_by_key[key] = new_contacto
        else:
            # Duplicate RIF within same empresa (shouldn't happen due to unique_together,
            # but handle defensively — reuse existing Contacto).
            existing = contacto_by_key[key]
            existing.es_cliente = True
            existing.save(update_fields=["es_cliente"])

        cliente.contacto_id = contacto_by_key[key].id_contacto
        cliente.save(update_fields=["contacto_id"])

    # ── Pass 2: Proveedores ───────────────────────────────────────────────────
    proveedores_sin_contacto = Proveedor.objects.filter(contacto__isnull=True).select_related()
    for proveedor in proveedores_sin_contacto:
        key = (proveedor.id_empresa_id, proveedor.rif)
        if key in contacto_by_key:
            # Same empresa + RIF as a Cliente → share the Contacto, add proveedor flag.
            shared = contacto_by_key[key]
            if not shared.es_proveedor:
                shared.es_proveedor = True
                shared.save(update_fields=["es_proveedor"])
            proveedor.contacto_id = shared.id_contacto
        else:
            new_contacto = _create_contacto_for_proveedor(apps, proveedor)
            new_contacto.save()
            contacto_by_key[key] = new_contacto
            proveedor.contacto_id = new_contacto.id_contacto

        proveedor.save(update_fields=["contacto_id"])


def backwards(apps, schema_editor):
    """Detach FK links; Contacto rows are kept so child data is preserved."""
    Cliente = apps.get_model("crm", "Cliente")
    Proveedor = apps.get_model("proveedores", "Proveedor")

    Cliente.objects.exclude(contacto__isnull=True).update(contacto_id=None)
    Proveedor.objects.exclude(contacto__isnull=True).update(contacto_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_contacto"),
        ("crm", "0007_cliente_contacto"),
        ("proveedores", "0004_proveedor_contacto"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
