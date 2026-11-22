"""Signals de invalidación de caché para ``apps.configuracion_motor`` (Plan 05 P2-4)."""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import ParametroSistema
from .services import invalidar_cache_parametro


@receiver(pre_save, sender=ParametroSistema)
def _capturar_empresa_previa_parametro(sender: Any, instance: ParametroSistema, **kwargs: Any) -> None:
    if instance._state.adding or not instance.pk:
        return
    prev = ParametroSistema.objects.filter(pk=instance.pk).values_list("id_empresa_id", flat=True).first()
    instance._prev_id_empresa_id = prev  # type: ignore[attr-defined]


@receiver([post_save, post_delete], sender=ParametroSistema)
def on_parametro_sistema_changed(sender: Any, instance: ParametroSistema, **kwargs: Any) -> None:
    prev_emp = getattr(instance, "_prev_id_empresa_id", instance.id_empresa_id)
    invalidar_cache_parametro(empresa_id=instance.id_empresa_id)
    if prev_emp != instance.id_empresa_id:
        invalidar_cache_parametro(empresa_id=prev_emp)
