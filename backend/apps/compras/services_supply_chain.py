"""Servicios de Supply Chain e Importaciones (Plan 09 Fase 5.1 y 5.4).

Incluye:
- Costos en Destino (Landed Costs): prorrateo por VALOR / CANTIDAD / PESO / VOLUMEN,
  revaloración de capas ``ValoracionInventario``, recálculo de ``Producto.costo_promedio``
  y asiento contable R-CODE-11.
- 3-Way Matching: validación cruzada ``OrdenCompra ↔ RecepcionMercancia ↔ FacturaCompra``.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from django.db import transaction

from apps.contabilidad.models import MapeoContable
from apps.contabilidad.services import AsientoError, generar_asiento_o_fallar
from apps.inventario.models import Producto, ValoracionInventario

from .models import (
    AsignacionCostoDestino,
    CostoDestino,
    DetalleFacturaCompra,
    DetalleOrdenCompra,
    DetalleRecepcionMercancia,
    FacturaCompra,
    RecepcionMercancia,
)

_CERO = Decimal("0")
_CIEN = Decimal("100")
_Q4 = Decimal("0.0001")
_Q2 = Decimal("0.01")


class SupplyChainCompraError(Exception):
    """Error de dominio en costos en destino o 3-way matching."""


def _q4(val: Decimal) -> Decimal:
    return val.quantize(_Q4, rounding=ROUND_HALF_UP)


def _q2(val: Decimal) -> Decimal:
    return val.quantize(_Q2, rounding=ROUND_HALF_UP)


def _dec(val: Any, default: Decimal = _CERO) -> Decimal:
    if val is None or val == "":
        return default
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise SupplyChainCompraError(f"Valor numérico inválido: {val!r}.") from exc


def _peso_prorrateo_detalle(detalle: DetalleRecepcionMercancia, metodo: str) -> Decimal:
    qty = _dec(detalle.cantidad_recibida)
    if qty <= _CERO:
        return _CERO
    if metodo == "VALOR":
        sub = _dec(detalle.subtotal)
        if sub > _CERO:
            return sub
        return _q4(qty * _dec(detalle.costo_unitario))
    if metodo == "CANTIDAD":
        return qty
    producto = detalle.id_producto
    if metodo == "PESO":
        peso_u = _dec(getattr(producto, "peso_unitario_kg", None))
        return _q4(qty * peso_u)
    if metodo == "VOLUMEN":
        vol_u = _dec(getattr(producto, "volumen_unitario_m3", None))
        return _q4(qty * vol_u)
    raise SupplyChainCompraError(f"Método de prorrateo no soportado: {metodo!r}.")


def _recalcular_costo_promedio_producto(empresa, producto: Producto, fallback: Decimal) -> Decimal:
    """Recalcula el costo promedio ponderado desde las capas vivas de entrada."""
    capas = ValoracionInventario.objects.filter(
        id_empresa=empresa,
        id_producto=producto,
        sentido="ENTRADA",
        cantidad_restante__gt=_CERO,
    )
    total_qty = _CERO
    total_val = _CERO
    for capa in capas:
        total_qty += _dec(capa.cantidad_restante)
        total_val += _dec(capa.cantidad_restante) * _dec(capa.costo_unitario)
    if total_qty > _CERO:
        return _q4(total_val / total_qty)
    return _q4(fallback)


@transaction.atomic
def aplicar_costo_destino(costo_destino: CostoDestino, usuario) -> dict[str, Any]:
    """Prorratea los costos en destino sobre la recepción y revalúa inventario."""
    costo_locked = (
        CostoDestino.objects.select_for_update(of=("self",))
        .select_related("id_empresa", "id_recepcion", "id_recepcion__id_orden_compra")
        .get(pk=costo_destino.pk)
    )
    if costo_locked.estado != "BORRADOR":
        raise SupplyChainCompraError(
            f"Solo se pueden aplicar costos en destino en BORRADOR. Estado actual: {costo_locked.estado}."
        )

    lineas = list(costo_locked.lineas.filter(activo=True))
    if not lineas:
        raise SupplyChainCompraError("El costo en destino debe tener al menos una línea de gasto activa.")

    monto_total = _q4(sum((_dec(ln.monto) for ln in lineas), _CERO))
    if monto_total <= _CERO:
        raise SupplyChainCompraError("El monto total de costos en destino debe ser mayor a cero.")

    recepcion = costo_locked.id_recepcion
    empresa = costo_locked.id_empresa
    if recepcion.id_empresa_id != empresa.pk or not recepcion.activo:
        raise SupplyChainCompraError("La recepción asociada no pertenece a la empresa o está inactiva.")

    detalles = list(recepcion.detalles.select_related("id_producto").order_by("id_detalle_recepcion"))
    if not detalles:
        raise SupplyChainCompraError("La recepción asociada no posee líneas de productos.")

    pesos: list[tuple[DetalleRecepcionMercancia, Decimal]] = [
        (det, _peso_prorrateo_detalle(det, costo_locked.metodo_prorrateo)) for det in detalles
    ]
    total_peso = sum((p for _d, p in pesos), _CERO)
    if total_peso <= _CERO:
        raise SupplyChainCompraError(
            f"La suma de bases de prorrateo para el método '{costo_locked.metodo_prorrateo}' "
            "es cero; verifique cantidades, subtotales o peso/volumen unitario de los productos."
        )

    # Prorrateo exacto ajustando residuo decimal en la línea de mayor peso.
    montos_asignados: list[Decimal] = []
    porcentajes: list[Decimal] = []
    acumulado = _CERO
    idx_mayor = 0
    mayor_peso = Decimal("-1")

    for idx, (_det, peso) in enumerate(pesos):
        if peso > mayor_peso:
            mayor_peso = peso
            idx_mayor = idx
        proporcion = peso / total_peso
        asignado = _q4(monto_total * proporcion)
        pct = _q4(proporcion * _CIEN)
        montos_asignados.append(asignado)
        porcentajes.append(pct)
        acumulado += asignado

    diferencia_centimos = _q4(monto_total - acumulado)
    if diferencia_centimos != _CERO:
        montos_asignados[idx_mayor] = _q4(montos_asignados[idx_mayor] + diferencia_centimos)

    asignaciones: list[AsignacionCostoDestino] = []
    productos_revaluados: list[dict[str, Any]] = []

    for idx, (det, peso) in enumerate(pesos):
        adicional_total = montos_asignados[idx]
        qty = _dec(det.cantidad_recibida)
        adicional_unitario = _q4(adicional_total / qty) if qty > _CERO else _CERO
        costo_anterior = _dec(det.costo_unitario)
        costo_nuevo = _q4(costo_anterior + adicional_unitario)

        asig = AsignacionCostoDestino.objects.create(
            id_empresa=empresa,
            id_costo_destino=costo_locked,
            id_detalle_recepcion=det,
            id_producto=det.id_producto,
            base_prorrateo=_q4(peso),
            porcentaje_prorrateo=porcentajes[idx],
            costo_adicional_total=adicional_total,
            costo_adicional_unitario=adicional_unitario,
            costo_unitario_anterior=_q4(costo_anterior),
            costo_unitario_nuevo=costo_nuevo,
        )
        asignaciones.append(asig)

        capas = ValoracionInventario.objects.select_for_update().filter(
            id_empresa=empresa,
            id_producto=det.id_producto,
            id_movimiento__id_documento_origen=recepcion.id_recepcion,
            sentido="ENTRADA",
        )
        for capa in capas:
            nuevo_costo_capa = _q4(_dec(capa.costo_unitario) + adicional_unitario)
            capa.costo_unitario = nuevo_costo_capa
            capa.valor_total = _q4(_dec(capa.cantidad) * nuevo_costo_capa)
            capa.save(update_fields=["costo_unitario", "valor_total", "fecha_actualizacion"])

        prod_locked = Producto.objects.select_for_update().get(pk=det.id_producto_id)
        nuevo_promedio = _recalcular_costo_promedio_producto(empresa, prod_locked, costo_nuevo)
        prod_locked.costo_promedio = nuevo_promedio
        prod_locked.save(update_fields=["costo_promedio", "fecha_actualizacion"])

        productos_revaluados.append(
            {
                "id_producto": str(prod_locked.pk),
                "producto": prod_locked.nombre_producto,
                "porcentaje": str(porcentajes[idx]),
                "costo_adicional_total": str(adicional_total),
                "costo_adicional_unitario": str(adicional_unitario),
                "costo_unitario_anterior": str(_q4(costo_anterior)),
                "costo_unitario_nuevo": str(costo_nuevo),
                "costo_promedio_actualizado": str(nuevo_promedio),
            }
        )

    tipo_asiento = "COSTO_DESTINO"
    if (
        not MapeoContable.objects.filter(id_empresa=empresa, tipo_asiento="COSTO_DESTINO", activo=True).exists()
        and MapeoContable.objects.filter(id_empresa=empresa, tipo_asiento="RECEPCION_MERCANCIA", activo=True).exists()
    ):
        tipo_asiento = "RECEPCION_MERCANCIA"

    asiento = None
    try:
        asiento, _ = generar_asiento_o_fallar(
            tipo_asiento,
            costo_locked,
            empresa,
            monto=monto_total,
            usuario=usuario,
            ambito=costo_locked.ambito,
        )
    except AsientoError as exc:
        raise SupplyChainCompraError(f"Error generando asiento de costo en destino: {exc}") from exc

    costo_locked.monto_total = monto_total
    costo_locked.estado = "APLICADO"
    costo_locked.id_asiento = asiento
    costo_locked.save(update_fields=["monto_total", "estado", "id_asiento", "fecha_actualizacion"])

    return {
        "costo_destino": costo_locked,
        "monto_total": monto_total,
        "asignaciones": asignaciones,
        "productos_revaluados": productos_revaluados,
        "asiento_id": str(asiento.pk) if asiento is not None else None,
    }


@transaction.atomic
def anular_costo_destino(costo_destino: CostoDestino) -> CostoDestino:
    """Anula un CostoDestino que aún está en BORRADOR."""
    costo_locked = CostoDestino.objects.select_for_update().get(pk=costo_destino.pk)
    if costo_locked.estado != "BORRADOR":
        raise SupplyChainCompraError(
            f"Solo se pueden anular costos en destino en BORRADOR. Estado actual: {costo_locked.estado}."
        )
    costo_locked.estado = "ANULADO"
    costo_locked.save(update_fields=["estado", "fecha_actualizacion"])
    return costo_locked


def validar_three_way_matching(
    factura_compra: FacturaCompra,
    *,
    tolerancia_cantidad_pct: Decimal = _CERO,
    tolerancia_precio_pct: Decimal = Decimal("1.00"),
) -> dict[str, Any]:
    """Ejecuta el cruce 3-Way Matching entre OC, Recepción(es) y Factura de Compra."""
    tol_cant = _dec(tolerancia_cantidad_pct)
    tol_prec = _dec(tolerancia_precio_pct)
    if tol_cant < _CERO or tol_prec < _CERO:
        raise SupplyChainCompraError("Las tolerancias de cantidad y precio deben ser mayores o iguales a cero.")

    orden = factura_compra.id_orden_compra
    if orden is None:
        return {
            "factura_id": str(factura_compra.pk),
            "numero_factura": factura_compra.numero_factura,
            "orden_compra_id": None,
            "recepcion_id": str(factura_compra.id_recepcion_id) if factura_compra.id_recepcion_id else None,
            "estado": "SIN_ORDEN_COMPRA",
            "aprobable_automaticamente": False,
            "discrepancias": ["La factura no tiene Orden de Compra asociada."],
            "comparativo_productos": [],
        }

    recepciones: list[RecepcionMercancia] = []
    if factura_compra.id_recepcion_id is not None and factura_compra.id_recepcion is not None:
        if factura_compra.id_recepcion.activo:
            recepciones = [factura_compra.id_recepcion]
    else:
        recepciones = list(RecepcionMercancia.objects.filter(id_orden_compra=orden, activo=True))

    if not recepciones:
        return {
            "factura_id": str(factura_compra.pk),
            "numero_factura": factura_compra.numero_factura,
            "orden_compra_id": str(orden.pk),
            "recepcion_id": None,
            "estado": "SIN_RECEPCION",
            "aprobable_automaticamente": False,
            "discrepancias": ["No existen recepciones de mercancía activas para la Orden de Compra."],
            "comparativo_productos": [],
        }

    oc_agg: dict[str, dict[str, Any]] = defaultdict(lambda: {"nombre": "", "qty": _CERO, "subtotal": _CERO})
    for d_oc in DetalleOrdenCompra.objects.filter(id_orden_compra=orden).select_related("id_producto"):
        pid = str(d_oc.id_producto_id)
        oc_agg[pid]["nombre"] = d_oc.id_producto.nombre_producto
        oc_agg[pid]["qty"] += _dec(d_oc.cantidad)
        oc_agg[pid]["subtotal"] += _dec(d_oc.subtotal)

    rec_agg: dict[str, dict[str, Any]] = defaultdict(lambda: {"nombre": "", "qty": _CERO, "subtotal": _CERO})
    for d_rec in DetalleRecepcionMercancia.objects.filter(id_recepcion__in=recepciones).select_related("id_producto"):
        pid = str(d_rec.id_producto_id)
        rec_agg[pid]["nombre"] = d_rec.id_producto.nombre_producto
        rec_agg[pid]["qty"] += _dec(d_rec.cantidad_recibida)
        rec_agg[pid]["subtotal"] += _dec(d_rec.subtotal) or _q4(
            _dec(d_rec.cantidad_recibida) * _dec(d_rec.costo_unitario)
        )

    fac_detalles = list(
        DetalleFacturaCompra.objects.filter(id_factura_compra=factura_compra).select_related("id_producto")
    )
    fac_agg: dict[str, dict[str, Any]] = defaultdict(lambda: {"nombre": "", "qty": _CERO, "subtotal": _CERO})
    for d_fac in fac_detalles:
        pid = str(d_fac.id_producto_id)
        fac_agg[pid]["nombre"] = d_fac.id_producto.nombre_producto
        fac_agg[pid]["qty"] += _dec(d_fac.cantidad)
        fac_agg[pid]["subtotal"] += _dec(d_fac.subtotal)

    discrepancias: list[str] = []
    discrepancia_cantidad = False
    discrepancia_precio = False
    comparativo: list[dict[str, Any]] = []

    if fac_agg:
        productos_ids = sorted(set(oc_agg.keys()) | set(rec_agg.keys()) | set(fac_agg.keys()))
        for pid in productos_ids:
            o = oc_agg[pid]
            r = rec_agg[pid]
            f = fac_agg[pid]
            nombre = f["nombre"] or r["nombre"] or o["nombre"]

            qty_oc = _q4(o["qty"])
            qty_rec = _q4(r["qty"])
            qty_fac = _q4(f["qty"])

            pu_oc = _q4(o["subtotal"] / qty_oc) if qty_oc > _CERO else _CERO
            pu_fac = _q4(f["subtotal"] / qty_fac) if qty_fac > _CERO else _CERO

            max_qty_permitida = _q4(qty_rec * (_UNO := Decimal("1")) + (qty_rec * (tol_cant / _CIEN)))
            min_qty_permitida = _q4(qty_rec * (_UNO - (tol_cant / _CIEN)))
            ok_qty = min_qty_permitida <= qty_fac <= max_qty_permitida
            if not ok_qty:
                discrepancia_cantidad = True
                discrepancias.append(
                    f"{nombre}: facturado ({qty_fac}) difiere de recibido ({qty_rec}) "
                    f"fuera de tolerancia ({tol_cant}%)."
                )

            ok_precio = True
            if pu_oc > _CERO and pu_fac > _CERO:
                var_pct = _q2(abs(pu_fac - pu_oc) / pu_oc * _CIEN)
                if var_pct > tol_prec:
                    ok_precio = False
                    discrepancia_precio = True
                    discrepancias.append(
                        f"{nombre}: precio facturado ({pu_fac}) difiere de OC ({pu_oc}) "
                        f"en {var_pct}% (máx {tol_prec}%)."
                    )
            elif pu_fac > _CERO and pu_oc == _CERO:
                ok_precio = False
                discrepancia_precio = True
                discrepancias.append(f"{nombre}: producto facturado no consta en la Orden de Compra.")

            comparativo.append(
                {
                    "id_producto": pid,
                    "producto": nombre,
                    "cantidad_oc": str(qty_oc),
                    "cantidad_recibida": str(qty_rec),
                    "cantidad_facturada": str(qty_fac),
                    "precio_unitario_oc": str(pu_oc),
                    "precio_unitario_factura": str(pu_fac),
                    "conforme_cantidad": ok_qty,
                    "conforme_precio": ok_precio,
                }
            )
    else:
        # Factura sin líneas de detalle: valida total contra recepciones y OC.
        total_rec = _q4(sum((_dec(r.monto_total) for r in recepciones), _CERO))
        total_fac = _q4(_dec(factura_compra.monto_total))
        if total_rec <= _CERO:
            discrepancia_cantidad = True
            discrepancias.append("La recepción asociada tiene monto total cero.")
        else:
            var_total_pct = _q2(abs(total_fac - total_rec) / total_rec * _CIEN)
            tol_efectiva = max(tol_cant, tol_prec)
            if var_total_pct > tol_efectiva:
                discrepancia_precio = True
                discrepancias.append(
                    f"Monto total facturado ({total_fac}) difiere del recibido ({total_rec}) "
                    f"en {var_total_pct}% (máx {tol_efectiva}%)."
                )

    if discrepancia_cantidad:
        estado = "DISCREPANCIA_CANTIDAD"
    elif discrepancia_precio:
        estado = "DISCREPANCIA_PRECIO"
    else:
        estado = "CONFORME"

    return {
        "factura_id": str(factura_compra.pk),
        "numero_factura": factura_compra.numero_factura,
        "orden_compra_id": str(orden.pk),
        "recepcion_id": str(recepciones[0].pk),
        "estado": estado,
        "aprobable_automaticamente": estado == "CONFORME",
        "tolerancia_cantidad_pct": str(tol_cant),
        "tolerancia_precio_pct": str(tol_prec),
        "discrepancias": discrepancias,
        "comparativo_productos": comparativo,
    }
