"""
Lógica de negocio de despacho/entrega (sub-fase 1.G).

Flujo:
  crear_despacho_desde_nota_venta() → Despacho PENDIENTE con líneas validadas
                                      contra el cupo de la venta
  transicionar_despacho()           → PENDIENTE → EN_RUTA → ENTREGADO|DEVUELTO
                                      PENDIENTE → CANCELADO, con timestamp por
                                      transición y evidencia en documento_json

Decisión de inventario (documentada): **ningún service de esta app toca
stock**. El movimiento físico ``DESPACHO_VENTA`` (descuento de inventario +
liberación de reserva) ya lo registró ``apps.ventas.services.entregar_nota_venta``
al confirmar la venta; el Despacho documenta la logística de entrega posterior.
Una devolución de mercancía al inventario es un flujo distinto
(``DevolucionVenta`` en apps/ventas), no responsabilidad de este módulo.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import Despacho, DetalleDespacho

logger = logging.getLogger(__name__)

# Estados de NotaVenta desde los que se puede despachar: el stock ya salió
# (entregar_nota_venta) y la venta no está anulada.
ESTADOS_NOTA_DESPACHABLES = ("ENTREGADA", "FACTURADA")


class DespachoError(Exception):
    """Error de dominio del flujo de despacho (se traduce a 400 en la API)."""


def cantidades_pendientes_por_producto(nota_venta) -> dict:
    """
    Cupo despachable por producto de una nota de venta:
    vendido (líneas de la nota) − despachado en despachos PENDIENTE/EN_RUTA/
    ENTREGADO de esa nota. CANCELADO y DEVUELTO liberan cupo.

    Returns:
        {id_producto (UUID): Decimal pendiente}  (puede ser 0, nunca negativo)
    """
    vendido: dict = {}
    for det in nota_venta.detalles.all():
        vendido[det.id_producto_id] = (
            vendido.get(det.id_producto_id, Decimal("0")) + det.cantidad
        )

    despachado = (
        DetalleDespacho.objects.filter(
            id_despacho__id_nota_venta=nota_venta,
            id_despacho__estado_despacho__in=Despacho.ESTADOS_CONSUMEN_CUPO,
        )
        .values("id_producto")
        .annotate(total=Sum("cantidad_despachada"))
    )
    despachado_map = {row["id_producto"]: row["total"] for row in despachado}

    return {
        producto_id: max(
            cantidad - despachado_map.get(producto_id, Decimal("0")), Decimal("0")
        )
        for producto_id, cantidad in vendido.items()
    }


def _validar_misma_empresa(nota_venta, almacen, transportista) -> None:
    if almacen.id_empresa_id != nota_venta.id_empresa_id:
        raise DespachoError("El almacén de origen no pertenece a la empresa de la venta.")
    if transportista is not None and transportista.empresa_id != nota_venta.id_empresa_id:
        raise DespachoError("El transportista no pertenece a la empresa de la venta.")


@transaction.atomic
def crear_despacho_desde_nota_venta(
    nota_venta,
    almacen,
    usuario,
    *,
    direccion_entrega: str,
    transportista=None,
    lineas: list | None = None,
    fecha_entrega_estimada=None,
    observaciones: str | None = None,
) -> Despacho:
    """
    Crea un Despacho PENDIENTE desde una venta confirmada (NotaVenta
    ENTREGADA/FACTURADA), sin tocar stock.

    Args:
        nota_venta:  NotaVenta origen (misma empresa que almacén/transportista).
        almacen:     Almacén desde donde sale la mercancía.
        usuario:     Usuario que registra el despacho (auditoría).
        direccion_entrega: dirección física de entrega (obligatoria).
        transportista: rrhh.Empleado opcional (chofer).
        lineas:      lista de dicts {"id_producto": UUID, "cantidad": Decimal}.
                     ``None`` = despachar TODO lo pendiente de la nota.
        fecha_entrega_estimada / observaciones: opcionales.

    Returns:
        Despacho creado (estado PENDIENTE, con sus DetalleDespacho).

    Raises:
        DespachoError: estado de nota inválido, empresa cruzada, dirección
        vacía, producto fuera de la nota, cantidad inválida o sobre-despacho.
    """
    from apps.fiscal.services import siguiente_numero
    from apps.ventas.models import NotaVenta

    # Lock de la nota: serializa creaciones concurrentes sobre la misma venta
    # para que dos requests simultáneos no puedan exceder el cupo entre ambos.
    nota_venta = NotaVenta.objects.select_for_update().get(pk=nota_venta.pk)

    if nota_venta.estado not in ESTADOS_NOTA_DESPACHABLES:
        raise DespachoError(
            "Solo se despachan notas de venta ENTREGADAS o FACTURADAS "
            f"(el stock ya salió). Estado actual: {nota_venta.estado}"
        )

    _validar_misma_empresa(nota_venta, almacen, transportista)

    if not (direccion_entrega or "").strip():
        raise DespachoError("La dirección de entrega es obligatoria.")

    detalles_nota = {
        det.id_producto_id: det
        for det in nota_venta.detalles.select_related(
            "id_producto", "id_producto__id_unidad_medida_base"
        )
    }
    if not detalles_nota:
        raise DespachoError("La nota de venta no tiene líneas de detalle.")

    pendientes = cantidades_pendientes_por_producto(nota_venta)

    if lineas is None:
        # Despacho total de lo pendiente.
        lineas = [
            {"id_producto": producto_id, "cantidad": pendiente}
            for producto_id, pendiente in pendientes.items()
            if pendiente > Decimal("0")
        ]
        if not lineas:
            raise DespachoError("La nota de venta ya está completamente despachada.")

    if not lineas:
        raise DespachoError("El despacho debe incluir al menos una línea.")

    lineas_validadas = []
    vistos = set()
    for linea in lineas:
        producto_id = linea["id_producto"]
        cantidad = Decimal(str(linea["cantidad"]))
        if producto_id in vistos:
            raise DespachoError("Hay productos repetidos en las líneas del despacho.")
        vistos.add(producto_id)
        detalle_nota = detalles_nota.get(producto_id)
        if detalle_nota is None:
            raise DespachoError(
                f"El producto {producto_id} no pertenece a la nota de venta."
            )
        if cantidad <= Decimal("0"):
            raise DespachoError("Las cantidades a despachar deben ser mayores a cero.")
        pendiente = pendientes.get(producto_id, Decimal("0"))
        if cantidad > pendiente:
            raise DespachoError(
                f"Sobre-despacho de '{detalle_nota.id_producto.nombre_producto}': "
                f"pendiente {pendiente}, solicitado {cantidad}."
            )
        lineas_validadas.append((detalle_nota, cantidad))

    despacho = Despacho.objects.create(
        id_empresa=nota_venta.id_empresa,
        numero_despacho=siguiente_numero(nota_venta.id_empresa, "DESPACHO"),
        id_nota_venta=nota_venta,
        id_pedido=nota_venta.id_pedido_origen,
        fecha_despacho=timezone.now(),
        id_almacen_origen=almacen,
        direccion_destino=direccion_entrega.strip(),
        id_transportista=transportista,
        estado_despacho=Despacho.ESTADO_PENDIENTE,
        fecha_entrega_estimada=fecha_entrega_estimada,
        observaciones=observaciones,
    )
    DetalleDespacho.objects.bulk_create(
        [
            DetalleDespacho(
                id_despacho=despacho,
                id_producto=detalle_nota.id_producto,
                cantidad_despachada=cantidad,
                id_unidad_medida=detalle_nota.id_producto.id_unidad_medida_base,
            )
            for detalle_nota, cantidad in lineas_validadas
        ]
    )

    logger.info(
        "despacho creado | empresa=%s | despacho=%s | nota=%s | usuario=%s",
        nota_venta.id_empresa_id,
        despacho.numero_despacho,
        nota_venta.numero_nota,
        usuario.pk,
    )
    return despacho


@transaction.atomic
def transicionar_despacho(
    despacho,
    nuevo_estado: str,
    usuario,
    *,
    transportista=None,
    receptor: str | None = None,
    documento_receptor: str | None = None,
    firma_base64: str | None = None,
    motivo: str | None = None,
) -> Despacho:
    """
    Aplica una transición de la máquina de estados con su timestamp y evidencia.

      EN_RUTA   — opcionalmente asigna ``transportista`` (misma empresa).
      ENTREGADO — exige ``receptor``; guarda receptor/documento/firma en
                  ``documento_json["entrega"]`` y fija ``fecha_entrega_real``.
      DEVUELTO  — exige ``motivo`` (documento_json["devolucion"]). NO reingresa
                  stock: eso es una DevolucionVenta (apps/ventas).
      CANCELADO — exige ``motivo`` (documento_json["cancelacion"]); solo desde
                  PENDIENTE (lo que ya salió en ruta se devuelve, no se cancela).

    Raises:
        DespachoError: transición no permitida o datos requeridos faltantes.
    """
    # Lock de fila: dos transiciones concurrentes no deben pisarse.
    despacho = Despacho.objects.select_for_update().get(pk=despacho.pk)

    if not despacho.puede_transicionar_a(nuevo_estado):
        permitidas = sorted(despacho.TRANSICIONES.get(despacho.estado_despacho, frozenset()))
        raise DespachoError(
            f"Transición inválida: {despacho.estado_despacho} → {nuevo_estado}. "
            f"Permitidas desde {despacho.estado_despacho}: {permitidas or 'ninguna (estado terminal)'}."
        )

    ahora = timezone.now()
    update_fields = ["estado_despacho", "fecha_actualizacion"]
    documento = dict(despacho.documento_json or {})

    if nuevo_estado == Despacho.ESTADO_EN_RUTA:
        if transportista is not None:
            if transportista.empresa_id != despacho.id_empresa_id:
                raise DespachoError("El transportista no pertenece a la empresa del despacho.")
            despacho.id_transportista = transportista
            update_fields.append("id_transportista")
        despacho.fecha_en_ruta = ahora
        update_fields.append("fecha_en_ruta")

    elif nuevo_estado == Despacho.ESTADO_ENTREGADO:
        if not (receptor or "").strip():
            raise DespachoError("Para marcar ENTREGADO se requiere el nombre del receptor.")
        despacho.fecha_entrega_real = ahora
        documento["entrega"] = {
            "receptor": receptor.strip(),
            "documento_receptor": (documento_receptor or "").strip() or None,
            "firma_base64": firma_base64 or None,
            "registrado_por": str(usuario.pk),
            "fecha": ahora.isoformat(),
        }
        despacho.documento_json = documento
        update_fields += ["fecha_entrega_real", "documento_json"]

    elif nuevo_estado == Despacho.ESTADO_DEVUELTO:
        if not (motivo or "").strip():
            raise DespachoError("Para marcar DEVUELTO se requiere el motivo de la devolución.")
        despacho.fecha_devolucion = ahora
        documento["devolucion"] = {
            "motivo": motivo.strip(),
            "registrado_por": str(usuario.pk),
            "fecha": ahora.isoformat(),
        }
        despacho.documento_json = documento
        update_fields += ["fecha_devolucion", "documento_json"]

    elif nuevo_estado == Despacho.ESTADO_CANCELADO:
        if not (motivo or "").strip():
            raise DespachoError("Para CANCELAR se requiere el motivo de la cancelación.")
        despacho.fecha_cancelacion = ahora
        documento["cancelacion"] = {
            "motivo": motivo.strip(),
            "registrado_por": str(usuario.pk),
            "fecha": ahora.isoformat(),
        }
        despacho.documento_json = documento
        update_fields += ["fecha_cancelacion", "documento_json"]

    despacho.estado_despacho = nuevo_estado
    despacho.save(update_fields=update_fields)

    logger.info(
        "despacho transicion | empresa=%s | despacho=%s | estado=%s | usuario=%s",
        despacho.id_empresa_id,
        despacho.numero_despacho,
        nuevo_estado,
        usuario.pk,
    )
    return despacho
