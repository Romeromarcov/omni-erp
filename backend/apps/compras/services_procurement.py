"""
Servicios transaccionales Source-to-PO del módulo de Compras (Plan 08 §B.2).

Flujo:
  enviar_requisicion_aprobacion()    → RequisicionCompra: BORRADOR → PENDIENTE | APROBADA
  confirmar_aprobacion_requisicion() → RequisicionCompra: PENDIENTE → APROBADA (si SolicitudAprobacion APROBADA)
  crear_rfq_desde_requisiciones()    → consolida requisiciones APROBADA en SolicitudCotizacion (ENVIADA)
  comparar_ofertas_rfq()             → matriz comparativa lado a lado (Decimal, sin float)
  adjudicar_oferta_a_orden_compra()  → OfertaProveedor → OrdenCompra (BORRADOR) + DetalleOrdenCompra
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
import uuid

from django.db import transaction
from django.utils import timezone

from apps.compras.models import (
    DetalleOfertaProveedor,
    DetalleOrdenCompra,
    DetalleRequisicionCompra,
    DetalleSolicitudCotizacion,
    OfertaProveedor,
    OrdenCompra,
    RequisicionCompra,
    SolicitudCotizacion,
)
from apps.compras.services import CompraError

_CUATRO_DECIMALES = Decimal("0.0001")
_CERO = Decimal("0.0000")


def _generar_numero_unico(modelo, campo: str, prefijo: str, empresa) -> str:
    fecha_str = timezone.localdate().strftime("%Y%m%d")
    for _ in range(10):
        candidato = f"{prefijo}-{fecha_str}-{uuid.uuid4().hex[:6].upper()}"
        if not modelo.objects.filter(id_empresa=empresa, **{campo: candidato}).exists():
            return candidato
    raise CompraError(f"No se pudo generar un {campo} único.")


@transaction.atomic
def enviar_requisicion_aprobacion(requisicion: RequisicionCompra, usuario=None) -> RequisicionCompra:
    """Envía una requisición en BORRADOR a aprobación departamental/general o la aprueba directo."""
    from apps.gestion_aprobaciones.services import (
        AprobacionError,
        crear_solicitud,
        esta_aprobada,
        requiere_aprobacion,
    )

    req = (
        RequisicionCompra.objects.select_for_update(of=("self",))
        .select_related("id_empresa", "id_departamento", "id_solicitante")
        .get(pk=requisicion.pk)
    )
    if req.estado != "BORRADOR":
        raise CompraError(f"Solo se envían a aprobación requisiciones en BORRADOR. Estado actual: {req.estado}")

    detalles = list(req.detalles.all())
    if not detalles:
        raise CompraError("La requisición debe tener al menos una línea antes de enviarse a aprobación.")

    monto_estimado = sum(
        (d.cantidad_solicitada * (d.precio_estimado or Decimal("0")) for d in detalles),
        Decimal("0"),
    )

    try:
        necesita = requiere_aprobacion(
            req.id_empresa,
            "REQUISICION_COMPRA",
            monto_estimado,
            departamento=req.id_departamento,
        )
        if necesita and not esta_aprobada(req):
            solicitante = usuario or req.id_solicitante
            crear_solicitud(
                req,
                req.id_empresa,
                solicitante,
                "REQUISICION_COMPRA",
                monto_estimado,
                departamento=req.id_departamento,
            )
            req.estado = "PENDIENTE"
        else:
            req.estado = "APROBADA"
    except AprobacionError as exc:
        raise CompraError(str(exc)) from exc

    req.save(update_fields=["estado"])
    return req


@transaction.atomic
def confirmar_aprobacion_requisicion(requisicion: RequisicionCompra, usuario=None) -> RequisicionCompra:
    """Transiciona una requisición PENDIENTE a APROBADA si su SolicitudAprobacion fue aprobada."""
    from apps.gestion_aprobaciones.services import esta_aprobada

    req = RequisicionCompra.objects.select_for_update(of=("self",)).get(pk=requisicion.pk)
    if req.estado != "PENDIENTE":
        raise CompraError(f"Solo se confirman requisiciones en estado PENDIENTE. Estado actual: {req.estado}")

    if not esta_aprobada(req):
        raise CompraError("La solicitud de aprobación de la requisición aún no ha sido aprobada.")

    req.estado = "APROBADA"
    req.save(update_fields=["estado"])
    return req


@transaction.atomic
def crear_rfq_desde_requisiciones(
    empresa,
    requisicion_ids: list[Any],
    proveedores_ids: list[Any],
    fecha_vencimiento: date | str,
    usuario=None,
    *,
    observaciones: str = "",
    numero_solicitud: str = "",
) -> SolicitudCotizacion:
    """Consolida líneas de requisiciones APROBADA en una SolicitudCotizacion (ENVIADA)."""
    from apps.proveedores.models import Proveedor

    if not requisicion_ids:
        raise CompraError("Debe seleccionar al menos una requisición aprobada.")
    if not proveedores_ids:
        raise CompraError("Debe invitar al menos un proveedor.")

    fecha_solicitud = timezone.localdate()
    if isinstance(fecha_vencimiento, str):
        try:
            fecha_venc = date.fromisoformat(fecha_vencimiento.strip())
        except ValueError as exc:
            raise CompraError("La fecha de vencimiento no tiene formato ISO válido (YYYY-MM-DD).") from exc
    else:
        fecha_venc = fecha_vencimiento

    if fecha_venc < fecha_solicitud:
        raise CompraError("La fecha de vencimiento no puede ser anterior a la fecha de solicitud.")

    req_pks = sorted({str(pk) for pk in requisicion_ids})
    requisiciones = list(
        RequisicionCompra.objects.select_for_update(of=("self",)).filter(pk__in=req_pks).order_by("pk")
    )
    if len(requisiciones) != len(req_pks):
        raise CompraError("Una o más requisiciones indicadas no existen.")

    for req in requisiciones:
        if str(req.id_empresa_id) != str(empresa.pk):
            raise CompraError("Todas las requisiciones deben pertenecer a la empresa.")
        if req.estado != "APROBADA":
            raise CompraError(f"La requisición {req.numero_requisicion} no está APROBADA (estado: {req.estado}).")

    prov_pks = sorted({str(pk) for pk in proveedores_ids})
    proveedores = list(Proveedor.objects.filter(pk__in=prov_pks, id_empresa=empresa, activo=True).order_by("pk"))
    if len(proveedores) != len(prov_pks):
        raise CompraError("Uno o más proveedores no existen, están inactivos o pertenecen a otra empresa.")

    detalles = list(
        DetalleRequisicionCompra.objects.filter(id_requisicion__in=requisiciones)
        .select_related("id_producto")
        .order_by("id_producto_id", "pk")
    )
    if not detalles:
        raise CompraError("Las requisiciones seleccionadas no tienen líneas de productos.")

    consolidado: dict[str, dict[str, Any]] = {}
    for det in detalles:
        prod_id = str(det.id_producto_id)
        if prod_id not in consolidado:
            consolidado[prod_id] = {
                "producto": det.id_producto,
                "cantidad": _CERO,
                "specs": [],
            }
        consolidado[prod_id]["cantidad"] += det.cantidad_solicitada
        for texto in (det.justificacion, det.observaciones):
            limpio = (texto or "").strip()
            if limpio and limpio not in consolidado[prod_id]["specs"]:
                consolidado[prod_id]["specs"].append(limpio)

    num_sol = (numero_solicitud or "").strip()
    if num_sol:
        if SolicitudCotizacion.objects.filter(id_empresa=empresa, numero_solicitud=num_sol).exists():
            raise CompraError(f"Ya existe una solicitud de cotización con el número '{num_sol}'.")
    else:
        num_sol = _generar_numero_unico(SolicitudCotizacion, "numero_solicitud", "RFQ", empresa)

    rfq = SolicitudCotizacion.objects.create(
        id_empresa=empresa,
        numero_solicitud=num_sol,
        fecha_solicitud=fecha_solicitud,
        fecha_vencimiento=fecha_venc,
        estado="ENVIADA",
        observaciones=(observaciones or "").strip() or None,
    )
    for item in consolidado.values():
        DetalleSolicitudCotizacion.objects.create(
            id_solicitud_cotizacion=rfq,
            id_producto=item["producto"],
            cantidad=item["cantidad"].quantize(_CUATRO_DECIMALES),
            especificaciones=" | ".join(item["specs"]) if item["specs"] else None,
        )

    rfq.requisiciones.set(requisiciones)
    rfq.proveedores_invitados.set(proveedores)
    return rfq


def comparar_ofertas_rfq(rfq: SolicitudCotizacion) -> dict[str, Any]:
    """Construye la matriz comparativa lado a lado de todas las ofertas de una RFQ (Decimal → str)."""
    detalles_rfq = list(rfq.detalles.select_related("id_producto").order_by("id_producto__nombre_producto", "pk"))
    ofertas_raw = list(
        rfq.ofertas.select_related("id_proveedor")
        .prefetch_related("detalles__id_producto")
        .order_by("monto_total", "fecha_oferta", "pk")
    )

    totales_oferta: dict[str, Decimal] = {}
    detalles_por_oferta: dict[str, dict[str, DetalleOfertaProveedor]] = {}
    productos_extra: dict[str, Any] = {}

    for oferta in ofertas_raw:
        oid = str(oferta.pk)
        dets = list(oferta.detalles.all())
        detalles_por_oferta[oid] = {str(d.id_producto_id): d for d in dets}
        for d in dets:
            productos_extra.setdefault(str(d.id_producto_id), d.id_producto)
        suma_dets = sum((d.subtotal for d in dets), _CERO)
        totales_oferta[oid] = oferta.monto_total if oferta.monto_total > 0 else suma_dets

    ofertas_ordenadas = sorted(
        ofertas_raw,
        key=lambda o: (totales_oferta[str(o.pk)], o.fecha_oferta, str(o.pk)),
    )

    elegibles = [o for o in ofertas_ordenadas if o.estado in ("RECIBIDA", "EVALUADA", "ACEPTADA")]
    mejor_total = min((totales_oferta[str(o.pk)] for o in elegibles), default=None)
    mejor_oferta = next((o for o in elegibles if totales_oferta[str(o.pk)] == mejor_total), None)

    productos_meta: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for d_rfq in detalles_rfq:
        pid = str(d_rfq.id_producto_id)
        vistos.add(pid)
        productos_meta.append(
            {
                "id_producto": pid,
                "producto_nombre": d_rfq.id_producto.nombre_producto,
                "sku": d_rfq.id_producto.sku or "",
                "cantidad_solicitada": d_rfq.cantidad.quantize(_CUATRO_DECIMALES),
                "especificaciones": d_rfq.especificaciones or "",
            }
        )
    for pid, prod in sorted(productos_extra.items(), key=lambda kv: kv[1].nombre_producto):
        if pid in vistos:
            continue
        productos_meta.append(
            {
                "id_producto": pid,
                "producto_nombre": prod.nombre_producto,
                "sku": prod.sku or "",
                "cantidad_solicitada": _CERO,
                "especificaciones": "",
            }
        )

    productos_salida: list[dict[str, Any]] = []
    for pmeta in productos_meta:
        pid = pmeta["id_producto"]
        precios_validos = [
            detalles_por_oferta[str(o.pk)][pid].precio_unitario
            for o in ofertas_ordenadas
            if o.estado not in ("RECHAZADA", "VENCIDA") and pid in detalles_por_oferta[str(o.pk)]
        ]
        mejor_pu = min(precios_validos, default=None)

        cotizaciones: list[dict[str, Any]] = []
        for o in ofertas_ordenadas:
            oid = str(o.pk)
            det_o = detalles_por_oferta[oid].get(pid)
            cotizaciones.append(
                {
                    "id_oferta": oid,
                    "id_proveedor": str(o.id_proveedor_id),
                    "proveedor_nombre": o.id_proveedor.razon_social,
                    "cantidad": str(det_o.cantidad.quantize(_CUATRO_DECIMALES)) if det_o is not None else None,
                    "precio_unitario": (
                        str(det_o.precio_unitario.quantize(_CUATRO_DECIMALES)) if det_o is not None else None
                    ),
                    "subtotal": str(det_o.subtotal.quantize(_CUATRO_DECIMALES)) if det_o is not None else None,
                    "tiempo_entrega": (det_o.tiempo_entrega or o.tiempo_entrega or "") if det_o is not None else None,
                    "es_mejor_precio": (
                        det_o is not None
                        and mejor_pu is not None
                        and o.estado not in ("RECHAZADA", "VENCIDA")
                        and det_o.precio_unitario == mejor_pu
                    ),
                }
            )

        productos_salida.append(
            {
                "id_producto": pid,
                "producto_nombre": pmeta["producto_nombre"],
                "sku": pmeta["sku"],
                "cantidad_solicitada": str(pmeta["cantidad_solicitada"]),
                "especificaciones": pmeta["especificaciones"],
                "mejor_precio_unitario": str(mejor_pu.quantize(_CUATRO_DECIMALES)) if mejor_pu is not None else None,
                "cotizaciones": cotizaciones,
            }
        )

    return {
        "rfq_id": str(rfq.pk),
        "numero_solicitud": rfq.numero_solicitud,
        "estado": rfq.estado,
        "fecha_solicitud": str(rfq.fecha_solicitud),
        "fecha_vencimiento": str(rfq.fecha_vencimiento),
        "mejor_oferta_id": str(mejor_oferta.pk) if mejor_oferta is not None else None,
        "ofertas": [
            {
                "id_oferta": str(o.pk),
                "numero_oferta": o.numero_oferta,
                "id_proveedor": str(o.id_proveedor_id),
                "proveedor_nombre": o.id_proveedor.razon_social,
                "estado": o.estado,
                "monto_total": str(totales_oferta[str(o.pk)].quantize(_CUATRO_DECIMALES)),
                "tiempo_entrega": o.tiempo_entrega or "",
                "condiciones_pago": o.condiciones_pago or "",
                "es_mejor_total": (mejor_oferta is not None and o.pk == mejor_oferta.pk),
            }
            for o in ofertas_ordenadas
        ],
        "productos": productos_salida,
    }


@transaction.atomic
def adjudicar_oferta_a_orden_compra(
    oferta: OfertaProveedor,
    almacen_destino,
    usuario=None,
    *,
    adjudicacion_parcial: list[dict[str, Any]] | None = None,
    rechazar_competidoras: bool = True,
) -> dict[str, Any]:
    """Adjudica una oferta (total o parcial) generando una OrdenCompra en BORRADOR."""
    rfq = (
        SolicitudCotizacion.objects.select_for_update(of=("self",))
        .select_related("id_empresa")
        .get(pk=oferta.id_solicitud_cotizacion_id)
    )
    oferta_locked = (
        OfertaProveedor.objects.select_for_update(of=("self",))
        .select_related("id_proveedor", "id_solicitud_cotizacion")
        .get(pk=oferta.pk)
    )
    requisiciones = list(rfq.requisiciones.select_for_update(of=("self",)).order_by("pk"))

    empresa = rfq.id_empresa
    if str(oferta_locked.id_proveedor.id_empresa_id) != str(empresa.pk):
        raise CompraError("El proveedor de la oferta no pertenece a la empresa de la solicitud.")
    if almacen_destino is None or str(almacen_destino.id_empresa_id) != str(empresa.pk):
        raise CompraError("El almacén destino no pertenece a la empresa de la solicitud.")

    if rfq.estado not in ("ENVIADA", "RESPONDIDA"):
        raise CompraError(
            f"La solicitud de cotización debe estar en ENVIADA o RESPONDIDA para adjudicar. Estado actual: {rfq.estado}"
        )
    if oferta_locked.estado not in ("RECIBIDA", "EVALUADA"):
        raise CompraError(
            f"Solo se pueden adjudicar ofertas en estado RECIBIDA o EVALUADA. Estado actual: {oferta_locked.estado}"
        )

    detalles_oferta = list(oferta_locked.detalles.select_related("id_producto").order_by("pk"))
    if not detalles_oferta:
        raise CompraError("La oferta no tiene líneas de productos para adjudicar.")

    detalle_por_prod: dict[str, DetalleOfertaProveedor] = {str(d.id_producto_id): d for d in detalles_oferta}
    lineas_a_adjudicar: list[tuple[Any, Decimal, Decimal, str | None]] = []

    if adjudicacion_parcial is not None:
        if not adjudicacion_parcial:
            raise CompraError("La adjudicación parcial debe especificar al menos un producto.")
        vistos: set[str] = set()
        for item in adjudicacion_parcial:
            prod_id = str(item.get("id_producto", "")).strip()
            if not prod_id or prod_id in vistos:
                raise CompraError("Cada línea de adjudicación parcial debe indicar un producto único.")
            vistos.add(prod_id)
            if prod_id not in detalle_por_prod:
                raise CompraError(f"El producto '{prod_id}' no pertenece a la oferta seleccionada.")
            det = detalle_por_prod[prod_id]
            try:
                cant = Decimal(str(item.get("cantidad")))
            except (InvalidOperation, ValueError, TypeError) as exc:
                raise CompraError(f"Cantidad inválida para el producto '{prod_id}'.") from exc
            if cant <= 0:
                raise CompraError("La cantidad a adjudicar debe ser mayor que cero.")
            if cant > det.cantidad:
                raise CompraError(
                    f"La cantidad a adjudicar ({cant}) supera la ofertada ({det.cantidad}) "
                    f"para '{det.id_producto.nombre_producto}'."
                )
            lineas_a_adjudicar.append((det.id_producto, cant, det.precio_unitario, det.observaciones))
    else:
        for det in detalles_oferta:
            lineas_a_adjudicar.append((det.id_producto, det.cantidad, det.precio_unitario, det.observaciones))

    for producto, _cant, _pu, _obs in lineas_a_adjudicar:
        if str(producto.id_empresa_id) != str(empresa.pk):
            raise CompraError("Todos los productos adjudicados deben pertenecer a la empresa.")

    numero_orden = _generar_numero_unico(OrdenCompra, "numero_orden", "OC", empresa)
    oc = OrdenCompra.objects.create(
        id_empresa=empresa,
        id_proveedor=oferta_locked.id_proveedor,
        id_oferta_origen=oferta_locked,
        id_almacen_destino=almacen_destino,
        numero_orden=numero_orden,
        fecha_orden=timezone.localdate(),
        estado="BORRADOR",
        observaciones=f"Adjudicada desde RFQ {rfq.numero_solicitud} / Oferta {oferta_locked.numero_oferta}",
    )

    monto_total = _CERO
    for producto, cantidad, precio_u, obs in lineas_a_adjudicar:
        cant_q = cantidad.quantize(_CUATRO_DECIMALES)
        pu_q = precio_u.quantize(_CUATRO_DECIMALES)
        subtotal = (cant_q * pu_q).quantize(_CUATRO_DECIMALES)
        monto_total += subtotal
        DetalleOrdenCompra.objects.create(
            id_orden_compra=oc,
            id_producto=producto,
            cantidad=cant_q,
            precio_unitario=pu_q,
            subtotal=subtotal,
            observaciones=obs,
        )

    oferta_locked.estado = "ACEPTADA"
    oferta_locked.save(update_fields=["estado"])

    if rechazar_competidoras:
        OfertaProveedor.objects.filter(
            id_solicitud_cotizacion=rfq,
            estado__in=("RECIBIDA", "EVALUADA"),
        ).exclude(pk=oferta_locked.pk).update(estado="RECHAZADA")

    quedan_abiertas = OfertaProveedor.objects.filter(
        id_solicitud_cotizacion=rfq,
        estado__in=("RECIBIDA", "EVALUADA"),
    ).exists()
    if not quedan_abiertas:
        rfq.estado = "RESPONDIDA"
        rfq.save(update_fields=["estado"])
        for req in requisiciones:
            if req.estado == "APROBADA":
                req.estado = "PROCESADA"
                req.save(update_fields=["estado"])

    return {
        "orden_compra": oc,
        "oferta": oferta_locked,
        "rfq": rfq,
        "monto_total": monto_total.quantize(_CUATRO_DECIMALES),
        "lineas": len(lineas_a_adjudicar),
    }
