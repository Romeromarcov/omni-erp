"""
Signal handlers que publican eventos de dominio cuando se crean/modifican
modelos clave del ERP.

Los imports se hacen con try/except porque algunos modelos pueden no existir
en todas las configuraciones del proyecto.
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.eventos.producer import publicar_evento

logger = logging.getLogger("omni.eventos")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _empresa_id(instance) -> str | None:
    """Extrae el empresa_id del modelo como string, o None."""
    try:
        empresa = getattr(instance, "id_empresa", None)
        if empresa is None:
            return None
        pk = getattr(empresa, "pk", empresa)
        return str(pk) if pk is not None else None
    except Exception:
        return None


def _safe_str(value) -> str | None:
    """Convierte a string o retorna None."""
    return str(value) if value is not None else None


def _safe_float(value) -> float | None:
    """Convierte Decimal/int a float o retorna None."""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_pk(fk_field) -> int | None:
    """Obtiene el pk de una FK o retorna None."""
    try:
        pk = getattr(fk_field, "pk", None)
        return pk
    except Exception:
        return None


# ── Ventas: Pedido ─────────────────────────────────────────────────────────────

try:
    from apps.ventas.models import Pedido

    @receiver(
        post_save,
        sender=Pedido,
        dispatch_uid="omni_eventos_pedido_post_save",
    )
    def on_pedido_saved(sender, instance, created, **kwargs):
        try:
            empresa_id = _empresa_id(instance)
            payload = {
                "pedido_id": instance.pk,
                "numero": _safe_str(getattr(instance, "numero_pedido", None)),
                "cliente_id": _safe_pk(getattr(instance, "id_cliente", None)),
                "estado": _safe_str(getattr(instance, "estado", None)),
                "fecha_pedido": _safe_str(getattr(instance, "fecha_pedido", None)),
            }
            tipo = "ventas.pedido.creado" if created else "ventas.pedido.actualizado"
            publicar_evento(tipo=tipo, payload=payload, empresa_id=empresa_id)
        except Exception as exc:
            logger.warning("on_pedido_saved: error al publicar evento: %s", exc)

except ImportError:
    logger.debug("omni.eventos: modelo Pedido no disponible, signal omitido.")


# ── Ventas: FacturaFiscal ─────────────────────────────────────────────────────

try:
    from apps.ventas.models import FacturaFiscal

    @receiver(
        post_save,
        sender=FacturaFiscal,
        dispatch_uid="omni_eventos_factura_fiscal_post_save",
    )
    def on_factura_fiscal_saved(sender, instance, created, **kwargs):
        if not created:
            return
        try:
            empresa_id = _empresa_id(instance)
            payload = {
                "factura_id": instance.pk,
                "numero_factura": _safe_str(getattr(instance, "numero_factura", None)),
                "numero_control": _safe_str(getattr(instance, "numero_control", None)),
                "cliente_id": _safe_pk(getattr(instance, "id_cliente", None)),
                "monto_total": _safe_float(getattr(instance, "monto_total", None)),
                "moneda_id": _safe_pk(getattr(instance, "id_moneda", None)),
                "estado": _safe_str(getattr(instance, "estado", None)),
                "fecha_emision": _safe_str(getattr(instance, "fecha_emision", None)),
            }
            publicar_evento(
                tipo="ventas.factura.creada",
                payload=payload,
                empresa_id=empresa_id,
            )
        except Exception as exc:
            logger.warning("on_factura_fiscal_saved: error al publicar evento: %s", exc)

except ImportError:
    logger.debug("omni.eventos: modelo FacturaFiscal no disponible, signal omitido.")


# ── Inventario: MovimientoInventario ──────────────────────────────────────────

try:
    from apps.inventario.models import MovimientoInventario

    @receiver(
        post_save,
        sender=MovimientoInventario,
        dispatch_uid="omni_eventos_movimiento_inventario_post_save",
    )
    def on_movimiento_inventario_saved(sender, instance, created, **kwargs):
        if not created:
            return
        try:
            empresa_id = _empresa_id(instance)
            almacen_origen = getattr(instance, "id_almacen_origen", None)
            payload = {
                "movimiento_id": instance.pk,
                "tipo_movimiento": _safe_str(getattr(instance, "tipo_movimiento", None)),
                "producto_id": _safe_pk(getattr(instance, "id_producto", None)),
                "cantidad": _safe_float(getattr(instance, "cantidad", None)),
                "almacen_id": _safe_pk(almacen_origen),
                "fecha_hora_movimiento": _safe_str(
                    getattr(instance, "fecha_hora_movimiento", None)
                ),
            }
            publicar_evento(
                tipo="inventario.movimiento.registrado",
                payload=payload,
                empresa_id=empresa_id,
            )
        except Exception as exc:
            logger.warning(
                "on_movimiento_inventario_saved: error al publicar evento: %s", exc
            )

except ImportError:
    logger.debug(
        "omni.eventos: modelo MovimientoInventario no disponible, signal omitido."
    )


# ── Finanzas: Pago ────────────────────────────────────────────────────────────

try:
    from apps.finanzas.models import Pago

    @receiver(
        post_save,
        sender=Pago,
        dispatch_uid="omni_eventos_pago_post_save",
    )
    def on_pago_saved(sender, instance, created, **kwargs):
        if not created:
            return
        try:
            empresa_id = _empresa_id(instance)
            payload = {
                "pago_id": instance.pk,
                "monto": _safe_float(getattr(instance, "monto", None)),
                "moneda_id": _safe_pk(getattr(instance, "id_moneda", None)),
                "metodo_pago_id": _safe_pk(getattr(instance, "id_metodo_pago", None)),
                "referencia": _safe_str(getattr(instance, "referencia", None)),
                "fecha_pago": _safe_str(getattr(instance, "fecha_pago", None)),
                "documento_id": _safe_str(getattr(instance, "id_documento", None)),
            }
            publicar_evento(
                tipo="finanzas.pago.registrado",
                payload=payload,
                empresa_id=empresa_id,
            )
        except Exception as exc:
            logger.warning("on_pago_saved: error al publicar evento: %s", exc)

except ImportError:
    logger.debug("omni.eventos: modelo Pago no disponible, signal omitido.")
