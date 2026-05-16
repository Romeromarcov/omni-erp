"""
Lógica de negocio para confirmar pedidos.

confirmar_pedido() — cambia estado a APROBADO, descuenta stock via registrar_movimiento,
                     y genera CuentaPorCobrar si el cliente es de crédito.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.inventario.services import MovimientoInvalidoError, StockInsuficienteError, registrar_movimiento


class PedidoConfirmacionError(Exception):
    pass


@transaction.atomic
def confirmar_pedido(pedido, almacen, usuario, generar_cxc: bool = None) -> dict:
    """
    Confirma un pedido: descuenta stock y opcionalmente genera CxC.

    Args:
        pedido:        instancia Pedido en estado PENDIENTE o ENVIADO
        almacen:       instancia Almacen desde donde se despacha
        usuario:       instancia Usuarios que confirma
        generar_cxc:   None = auto (sigue tipo_cliente); True/False = forzar

    Returns:
        {
            "movimientos": [MovimientoInventario, ...],
            "cxc": CuentaPorCobrar | None,
        }
    """
    if pedido.estado not in ("PENDIENTE", "ENVIADO"):
        raise PedidoConfirmacionError(
            f"Solo se pueden confirmar pedidos en estado PENDIENTE o ENVIADO. Estado actual: {pedido.estado}"
        )

    detalles = list(pedido.detalles.select_related("id_producto"))
    if not detalles:
        raise PedidoConfirmacionError("El pedido no tiene líneas de detalle.")

    movimientos = []
    for detalle in detalles:
        try:
            mov = registrar_movimiento(
                empresa=pedido.id_empresa,
                fecha_hora_movimiento=timezone.now(),
                tipo_movimiento="DESPACHO_VENTA",
                producto=detalle.id_producto,
                cantidad=detalle.cantidad,
                almacen_origen=almacen,
                documento_origen_id=pedido.id_pedido,
                nombre_modelo_origen="Pedido",
                usuario=usuario,
                observaciones=f"Despacho pedido {pedido.numero_pedido}",
            )
        except StockInsuficienteError as exc:
            raise PedidoConfirmacionError(str(exc)) from exc
        except MovimientoInvalidoError as exc:
            raise PedidoConfirmacionError(str(exc)) from exc

        movimientos.append(mov)

    pedido.estado = "APROBADO"
    pedido.save(update_fields=["estado"])

    cxc = None
    cliente = pedido.id_cliente
    debe_generar = generar_cxc if generar_cxc is not None else (cliente.tipo_cliente == "CREDITO")

    if debe_generar:
        from datetime import timedelta

        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        subtotal = sum(d.subtotal for d in detalles)
        dias = cliente.dias_credito or 30
        fecha_vencimiento = timezone.now().date() + timedelta(days=dias)

        cxc = CuentaPorCobrar.objects.create(
            cliente=cliente,
            empresa=pedido.id_empresa,
            monto=subtotal,
            fecha_emision=timezone.now().date(),
            fecha_vencimiento=fecha_vencimiento,
            estado="pendiente",
            descripcion=f"Pedido {pedido.numero_pedido}",
        )

    # Emitir evento WS-2
    from apps.core.events import VentasEvents, publish

    publish(
        event_type=VentasEvents.PEDIDO_CONFIRMADO,
        tenant_id=str(pedido.id_empresa_id),
        payload={
            "pedido_id": str(pedido.id_pedido),
            "numero_pedido": pedido.numero_pedido,
            "cliente_id": str(pedido.id_cliente_id),
            "movimientos": [str(m.id_movimiento_inventario) for m in movimientos],
            "cxc_id": str(cxc.pk) if cxc else None,
        },
        actor_id=str(usuario.pk),
    )

    return {"movimientos": movimientos, "cxc": cxc}
