"""Servicios de deduplicación y resolución de ``core.Contacto`` para CRM / Omni Connect (S5)."""

from __future__ import annotations

import hashlib
import uuid

from django.db import connection, transaction

from apps.core.models import Contacto, Empresa
from apps.core.validators import normalizar_email, normalizar_telefono

from .models import Lead


def _advisory_lock_contacto_empresa(empresa_id: uuid.UUID) -> None:
    """Serializa la resolución de contactos duplicados por tenant en PostgreSQL."""
    if connection.vendor != "postgresql":
        return
    digest = hashlib.sha256(f"crm-contacto-dedup:{empresa_id}".encode("utf-8")).digest()
    lock_key = int.from_bytes(digest[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])


@transaction.atomic
def resolver_o_vincular_contacto(
    empresa: Empresa,
    *,
    nombre: str,
    apellido: str = "",
    email: str = "",
    telefono: str = "",
    empresa_nombre: str = "",
) -> Contacto | None:
    """Resuelve un ``core.Contacto`` activo dentro de ``empresa`` o crea uno validado.

    Prioriza match exacto por ``email_normalizado`` activo y, si no encuentra, por
    ``telefono_normalizado`` activo dentro de ``id_empresa``. Nunca enlaza registros
    de otra empresa ni sobrescribe datos existentes no vacíos.
    """
    nombre_limpio = (nombre or "").strip()
    apellido_limpio = (apellido or "").strip()
    empresa_limpia = (empresa_nombre or "").strip()
    email_limpio = (email or "").strip()
    telefono_limpio = (telefono or "").strip()

    email_norm = normalizar_email(email_limpio)
    tel_norm = normalizar_telefono(telefono_limpio)
    if not email_norm and not tel_norm:
        return None

    _advisory_lock_contacto_empresa(empresa.pk)

    contacto: Contacto | None = None
    if email_norm:
        contacto = (
            Contacto.objects.select_for_update()
            .filter(id_empresa=empresa, activo=True, email_normalizado=email_norm)
            .order_by("fecha_creacion", "id_contacto")
            .first()
        )
    if contacto is None and tel_norm:
        contacto = (
            Contacto.objects.select_for_update()
            .filter(id_empresa=empresa, activo=True, telefono_normalizado=tel_norm)
            .order_by("fecha_creacion", "id_contacto")
            .first()
        )

    if contacto is not None:
        actualizado = False
        if not (contacto.nombre or "").strip() and nombre_limpio:
            contacto.nombre = nombre_limpio[:255]
            actualizado = True
        if not (contacto.apellido or "").strip() and apellido_limpio:
            contacto.apellido = apellido_limpio[:255]
            actualizado = True
        if not (contacto.nombre_comercial or "").strip() and empresa_limpia:
            contacto.nombre_comercial = empresa_limpia[:255]
            actualizado = True
        if not (contacto.email or "").strip() and email_limpio:
            contacto.email = email_limpio[:254]
            actualizado = True
        if not (contacto.telefono or "").strip() and telefono_limpio:
            contacto.telefono = telefono_limpio[:50]
            actualizado = True
        if actualizado:
            contacto.full_clean()
            contacto.save()
        return contacto

    nuevo = Contacto(
        id_empresa=empresa,
        tipo_persona="NATURAL",
        nombre=(nombre_limpio or empresa_limpia or email_limpio or telefono_limpio)[:255],
        apellido=apellido_limpio[:255],
        nombre_comercial=empresa_limpia[:255],
        email=email_limpio[:254],
        telefono=telefono_limpio[:50],
    )
    nuevo.full_clean()
    nuevo.save()
    return nuevo


@transaction.atomic
def vincular_lead_a_contacto(lead: Lead, *, contacto: Contacto | None = None) -> Lead:
    """Vincula un ``Lead`` a un ``core.Contacto`` del mismo tenant validando ``full_clean()``."""
    lead_locked = Lead.objects.select_for_update(of=("self",)).select_related("id_empresa").get(pk=lead.pk)
    if contacto is None:
        contacto_resuelto = resolver_o_vincular_contacto(
            lead_locked.id_empresa,
            nombre=lead_locked.nombre,
            apellido=lead_locked.apellido,
            email=lead_locked.email,
            telefono=lead_locked.telefono,
            empresa_nombre=lead_locked.empresa_nombre,
        )
    else:
        contacto_resuelto = contacto
    lead_locked.contacto = contacto_resuelto
    lead_locked.full_clean()
    lead_locked.save(update_fields=["contacto", "fecha_actualizacion"])
    return lead_locked
