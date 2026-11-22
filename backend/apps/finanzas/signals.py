"""Signals de invalidación selectiva de caché para ``apps.finanzas`` (Plan 05 P2-4)."""

from __future__ import annotations

from typing import Any

from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from .cache import (
    NS_METODO_PAGO_ACTIVO,
    NS_MONEDA_ACTIVA,
    invalidar_cache_metodo_pago,
    invalidar_cache_moneda,
    invalidar_cache_tasa_cambio,
)
from .models import MetodoPago, MetodoPagoEmpresaActiva, Moneda, MonedaEmpresaActiva, TasaCambio


@receiver(pre_save, sender=TasaCambio)
def _capturar_empresa_previa_tasa(sender: Any, instance: TasaCambio, **kwargs: Any) -> None:
    if instance._state.adding or not instance.pk:
        return
    prev = TasaCambio.objects.filter(pk=instance.pk).values_list("id_empresa_id", flat=True).first()
    instance._prev_id_empresa_id = prev  # type: ignore[attr-defined]


@receiver([post_save, post_delete], sender=TasaCambio)
def on_tasa_cambio_changed(sender: Any, instance: TasaCambio, **kwargs: Any) -> None:
    prev_emp = getattr(instance, "_prev_id_empresa_id", instance.id_empresa_id)
    invalidar_cache_tasa_cambio(empresa_id=instance.id_empresa_id)
    if prev_emp != instance.id_empresa_id:
        invalidar_cache_tasa_cambio(empresa_id=prev_emp)


@receiver(pre_save, sender=Moneda)
def _capturar_scope_previo_moneda(sender: Any, instance: Moneda, **kwargs: Any) -> None:
    if instance._state.adding or not instance.pk:
        return
    prev = Moneda.objects.filter(pk=instance.pk).values("empresa_id", "es_generica", "es_publica").first()
    instance._prev_cache_scope = prev  # type: ignore[attr-defined]


@receiver([post_save, post_delete], sender=Moneda)
def on_moneda_changed(sender: Any, instance: Moneda, **kwargs: Any) -> None:
    es_global = bool(instance.empresa_id is None or instance.es_generica or instance.es_publica)
    invalidar_cache_moneda(empresa_id=instance.empresa_id, es_global=es_global)

    prev = getattr(instance, "_prev_cache_scope", None)
    if isinstance(prev, dict):
        prev_emp = prev.get("empresa_id")
        prev_global = bool(prev_emp is None or prev.get("es_generica") or prev.get("es_publica"))
        if prev_emp != instance.empresa_id or prev_global != es_global:
            invalidar_cache_moneda(empresa_id=prev_emp, es_global=prev_global)


@receiver([post_save, post_delete], sender=MonedaEmpresaActiva)
def on_moneda_empresa_activa_changed(sender: Any, instance: MonedaEmpresaActiva, **kwargs: Any) -> None:
    if instance.empresa_id is not None:
        from apps.core.cache_utils import bump_namespace_version

        bump_namespace_version(NS_MONEDA_ACTIVA, instance.empresa_id)


@receiver(pre_save, sender=MetodoPago)
def _capturar_scope_previo_metodo(sender: Any, instance: MetodoPago, **kwargs: Any) -> None:
    if instance._state.adding or not instance.pk:
        return
    prev = MetodoPago.objects.filter(pk=instance.pk).values("empresa_id", "es_generico", "es_publico").first()
    instance._prev_cache_scope = prev  # type: ignore[attr-defined]


@receiver([post_save, post_delete], sender=MetodoPago)
def on_metodo_pago_changed(sender: Any, instance: MetodoPago, **kwargs: Any) -> None:
    es_global = bool(instance.empresa_id is None or instance.es_generico or instance.es_publico)
    invalidar_cache_metodo_pago(empresa_id=instance.empresa_id, es_global=es_global)

    prev = getattr(instance, "_prev_cache_scope", None)
    if isinstance(prev, dict):
        prev_emp = prev.get("empresa_id")
        prev_global = bool(prev_emp is None or prev.get("es_generico") or prev.get("es_publico"))
        if prev_emp != instance.empresa_id or prev_global != es_global:
            invalidar_cache_metodo_pago(empresa_id=prev_emp, es_global=prev_global)


@receiver(m2m_changed, sender=MetodoPago.monedas.through)
def on_metodo_pago_monedas_changed(sender: Any, action: str, instance: Any, **kwargs: Any) -> None:
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if isinstance(instance, MetodoPago):
        es_global = bool(instance.empresa_id is None or instance.es_generico or instance.es_publico)
        invalidar_cache_metodo_pago(empresa_id=instance.empresa_id, es_global=es_global)
    else:
        invalidar_cache_metodo_pago(empresa_id=None, es_global=True)


@receiver([post_save, post_delete], sender=MetodoPagoEmpresaActiva)
def on_metodo_pago_empresa_activa_changed(sender: Any, instance: MetodoPagoEmpresaActiva, **kwargs: Any) -> None:
    if instance.empresa_id is not None:
        from apps.core.cache_utils import bump_namespace_version

        bump_namespace_version(NS_METODO_PAGO_ACTIVO, instance.empresa_id)
