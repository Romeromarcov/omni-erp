"""Orquestación de la ingesta: resolución de usuario, idempotencia, handler y registro."""

from __future__ import annotations

from django.db import IntegrityError, transaction

from apps.core.viewsets import get_empresas_visible

from ..models import BotUsuario, IngestaBot
from . import handlers
from .handlers import Ctx, HandlerError

# Pagos: se pueden completar después de enviados (desde el grupo o desde Odoo).
COMPLETABLES = {IngestaBot.Kind.PAGO, IngestaBot.Kind.PAGO_PROVEEDOR}


class UsuarioBotDesconocido(Exception):
    pass


def resolver_bot_usuario(servicio, telegram_user_id) -> BotUsuario:
    try:
        tid = int(telegram_user_id)
    except (TypeError, ValueError) as e:
        raise UsuarioBotDesconocido("telegram_user_id inválido.") from e
    bu = (
        BotUsuario.objects.filter(
            telegram_user_id=tid,
            activo=True,
            id_empresa__in=get_empresas_visible(servicio),
            usuario__is_active=True,
        )
        .select_related("usuario", "id_empresa")
        .first()
    )
    if bu is None:
        raise UsuarioBotDesconocido("Usuario de Telegram no autorizado.")
    return bu


def ingerir(*, servicio, kind: str, draft: dict, fuente: dict, idempotency_key: str):
    """→ (IngestaBot, creada: bool). Lanza UsuarioBotDesconocido / HandlerError."""
    bu = resolver_bot_usuario(servicio, fuente.get("telegram_user_id"))
    existente = IngestaBot.objects.filter(
        id_empresa=bu.id_empresa, idempotency_key=idempotency_key
    ).first()
    if existente:
        return existente, False
    handler = handlers.HANDLERS[kind]
    try:
        with transaction.atomic():
            r = handler(
                Ctx(
                    empresa=bu.id_empresa,
                    usuario=bu.usuario,
                    payload=draft,
                    fuente=fuente,
                )
            )
            ing = IngestaBot.objects.create(
                id_empresa=bu.id_empresa,
                bot_usuario=bu,
                kind=kind,
                idempotency_key=idempotency_key,
                payload=draft,
                fuente=fuente,
                auto=bool(fuente.get("auto")),
                estado=r.estado,
                incompleto=r.incompleto,
                resultado=r.resultado,
            )
    except IntegrityError:
        # Carrera: otra petición con la misma clave ganó. Si no existe esa ingesta, el conflicto
        # es de otra restricción (dato real duplicado): no se enmascara.
        ganadora = IngestaBot.objects.filter(
            id_empresa=bu.id_empresa, idempotency_key=idempotency_key
        ).first()
        if ganadora is None:
            raise
        return ganadora, False
    return ing, True


def completar(ingesta: IngestaBot, cambios: dict) -> IngestaBot:
    """Completa/corrige un pago ya enviado: fusiona campos y reevalúa lo que falta."""
    if ingesta.kind not in COMPLETABLES:
        raise HandlerError("Solo se pueden completar pagos.")
    if ingesta.estado not in (IngestaBot.Estado.INCOMPLETO, IngestaBot.Estado.BORRADOR):
        raise HandlerError(
            "Esta ingesta ya fue sincronizada o cerrada; edítala en Odoo.", status=409
        )
    payload = {
        **ingesta.payload,
        **{
            k: v
            for k, v in cambios.items()
            if k in ingesta.payload or k in _CAMPOS_PAGO
        },
    }
    r = handlers.HANDLERS[ingesta.kind](
        Ctx(
            empresa=ingesta.id_empresa,
            usuario=ingesta.bot_usuario.usuario,
            payload=payload,
            fuente=ingesta.fuente,
        )
    )
    ingesta.payload, ingesta.incompleto, ingesta.resultado, ingesta.estado = (
        payload,
        r.incompleto,
        r.resultado,
        r.estado,
    )
    ingesta.save(
        update_fields=[
            "payload",
            "incompleto",
            "resultado",
            "estado",
            "fecha_actualizacion",
        ]
    )
    return ingesta


_CAMPOS_PAGO = {
    "cliente",
    "rif",
    "monto",
    "moneda",
    "metodo_pago",
    "referencia",
    "banco",
    "fecha_pago",
    "pedido_ref",
    "proveedor",
    "factura_ref",
}
