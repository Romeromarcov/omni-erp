"""
CxcBaseModel — mixin para todos los modelos del módulo CxC.
Incluye: UUIDv7 PK, soft delete, empresa FK, timestamps.
"""
from apps.core.uuid import uuid7
from django.db import models


class CxcBaseModel(models.Model):
    """Clase base abstracta para todos los modelos de apps.cxc."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    empresa = models.ForeignKey(
        "core.Empresa",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def soft_delete(self):
        from django.utils import timezone
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
