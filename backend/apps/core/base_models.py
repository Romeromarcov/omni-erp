"""
Modelos abstractos base de Omni ERP.

Estos modelos abstractos consolidan campos comunes que se repiten en >27 módulos
del ERP, garantizando consistencia y evitando copy-paste de definiciones.

Uso para NUEVOS modelos:
    from apps.core.base_models import OmniBaseModel, IntegrationFieldsMixin

    class MiModelo(OmniBaseModel, IntegrationFieldsMixin):
        id_mi_modelo = models.UUIDField(primary_key=True, default=uuid7, editable=False)
        id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE)
        # ...

Jerarquía de clases:
    TimeStampedModel    — fecha_creacion, fecha_actualizacion
    SoftDeleteModel     — activo, soft_delete(), restore()
    IntegrationFieldsMixin — referencia_externa, documento_json
    OmniBaseModel       = TimeStampedModel + SoftDeleteModel (combo estándar)

Regla de migración:
    Al heredar de estos modelos ABSTRACTOS, los campos se "inlinan" en la tabla
    concreta. Siempre que las definiciones coincidan exactamente con los campos
    que ya existen en la tabla, makemigrations NO generará migraciones.
"""

from __future__ import annotations

from django.db import models

# ── 1. Auditoría temporal ────────────────────────────────────────────────────


class TimeStampedModel(models.Model):
    """
    Mixin abstracto: registra cuándo se creó y actualizó un registro.

    Campos:
        fecha_creacion     — Set automáticamente al crear el objeto (auto_now_add).
        fecha_actualizacion — Actualizado automáticamente en cada save() (auto_now).

    Nota sobre auto_now/auto_now_add:
        Estos campos son de solo escritura vía Django ORM. Para tests que necesiten
        valores específicos, usar `update()` en lugar de `save()`.
    """

    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Creación",
        help_text="Fecha y hora de creación del registro.",
    )
    fecha_actualizacion = models.DateTimeField(
        auto_now=True,
        verbose_name="Fecha de Actualización",
        help_text="Fecha y hora de la última modificación del registro.",
    )

    class Meta:
        abstract = True


# ── 2. Borrado lógico (soft delete) ─────────────────────────────────────────


class SoftDeleteModel(models.Model):
    """
    Mixin abstracto: implementa borrado lógico con el campo ``activo``.

    En lugar de eliminar el registro de la DB (``DELETE``), se marca como
    inactivo (``activo=False``). El registro permanece en la DB para trazabilidad
    histórica pero desaparece de los querysets normales.

    Campos:
        activo — True = visible/operativo, False = "borrado" lógicamente.

    Métodos:
        soft_delete() — Desactiva el registro.
        restore()     — Reactiva el registro.
        hard_delete() — Elimina físicamente de la DB (usar solo en administración).

    Importante:
        Este mixin NO agrega un filtro automático ``activo=True`` a los querysets.
        Para ese comportamiento usa ``SoftDeleteModelMixin`` en el ViewSet
        (``apps.core.viewsets``), o filtra explícitamente en ``get_queryset()``.
    """

    activo = models.BooleanField(
        default=True,
        verbose_name="Activo",
        help_text="Indica si el registro está activo (False = borrado lógico).",
    )

    class Meta:
        abstract = True

    def soft_delete(self, *, update_fields: list[str] | None = None) -> None:
        """
        Desactiva el registro (borrado lógico).

        Solo actualiza el campo ``activo`` para no disparar señales
        de otros campos. Agrega 'activo' a ``update_fields`` si se proveen.
        """
        if update_fields is not None:
            if "activo" not in update_fields:
                update_fields = list(update_fields) + ["activo"]
            self.activo = False
            self.save(update_fields=update_fields)
        else:
            self.activo = False
            self.save(update_fields=["activo"])

    def restore(self) -> None:
        """Reactiva el registro (revierte el borrado lógico)."""
        self.activo = True
        self.save(update_fields=["activo"])

    def hard_delete(self) -> None:
        """Elimina el registro físicamente. Usar solo en administración."""
        super().delete()


# ── 3. Integración con sistemas externos ────────────────────────────────────


class IntegrationFieldsMixin(models.Model):
    """
    Mixin abstracto: campos para integración con sistemas externos (ERP legacy,
    APIs de terceros, importaciones batch, etc.).

    Campos:
        referencia_externa — Identificador del registro en un sistema externo.
                             Ej: ID en ERP anterior, SKU de proveedor, etc.
        documento_json     — Copia raw del documento original de la fuente
                             externa (factura XML, JSON de API, etc.) para
                             auditoría y reprocesamiento.

    Convención de uso:
        - Nunca leer ``documento_json`` en lógica de negocio; solo para auditoría.
        - ``referencia_externa`` es de libre formato — no usar como FK.
    """

    referencia_externa = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Referencia externa",
        help_text="Identificador del registro en el sistema externo de origen.",
    )
    documento_json = models.JSONField(
        null=True,
        blank=True,
        verbose_name="Documento JSON",
        help_text="Payload raw del documento externo (para auditoría/reprocesamiento).",
    )

    class Meta:
        abstract = True


# ── 4. Base combinada estándar ───────────────────────────────────────────────


class OmniBaseModel(TimeStampedModel, SoftDeleteModel):
    """
    Modelo abstracto base estándar de Omni ERP.

    Combina timestamps de auditoría + soft-delete. Es el punto de partida
    recomendado para todos los modelos nuevos del ERP.

    Uso mínimo:
        class MiEntidad(OmniBaseModel):
            id_entidad = models.UUIDField(primary_key=True, default=uuid7, editable=False)
            id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE)
            ...

    Para entidades que también necesiten integración con sistemas externos:
        class MiEntidad(OmniBaseModel, IntegrationFieldsMixin):
            ...
    """

    class Meta:
        abstract = True


# ── 5. Base para tablas "maestras" de empresa (tenant-aware) ─────────────────


class TenantModel(OmniBaseModel):
    """
    Modelo abstracto para entidades con aislamiento multi-tenant.

    Garantiza que cada instancia pertenece a una empresa. Los viewsets
    que hereden de ``BaseModelViewSet`` deben filtrar por
    ``get_empresas_visible(user)`` en su ``get_queryset()``.

    IMPORTANTE: Este modelo NO define el campo ``id_empresa`` porque el
    nombre de la FK varía por módulo. El modelo concreto DEBE definirlo:

        id_empresa = models.ForeignKey(
            'core.Empresa',
            on_delete=models.CASCADE,
            db_column='id_empresa',
        )
    """

    class Meta:
        abstract = True
