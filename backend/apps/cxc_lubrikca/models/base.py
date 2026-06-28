"""Modelo base abstracto del subproyecto CxC Lubrikca.

Aporta el contrato común de todos los modelos de la app:
- ``id`` UUIDv7 (R-CODE-5, time-ordered, buena localidad de índice);
- ``empresa`` FK a ``core.Empresa`` para el aislamiento multi-tenant (R-CODE-1);
- timestamps ``created_at`` / ``updated_at``;
- *soft delete* vía ``deleted_at`` (R-CODE-6: nunca hard delete silencioso).
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.core.uuid import uuid7


class CxcLubrikcaBaseModel(models.Model):
    """Base abstracta: UUIDv7 + multi-tenant + timestamps + soft delete."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        verbose_name="Empresa",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Borrado lógico: marca ``deleted_at`` sin perder el registro."""
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])
