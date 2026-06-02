"""Lógica de manufactura (Ola 5.3): explosión de BOM, órdenes de producción,
consumo de materiales ↔ inventario, costeo real y MRP básico.

El cálculo (explosión, MRP, costeo) está aislado en funciones PURAS (Decimal, sin
I/O) para ser testeable y portable (§5.2-ter); la orquestación lee/escribe el ORM
y reutiliza `inventario.services.registrar_movimiento` (R-CODE-11 vía inventario).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class ManufacturaError(Exception):
    pass


# ── Estructuras puras ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ComponenteBOM:
    producto_id: str
    cantidad_requerida: Decimal
    es_opcional: bool = False


@dataclass(frozen=True)
class RequerimientoMaterial:
    producto_id: str
    cantidad: Decimal


@dataclass(frozen=True)
class FaltanteMaterial:
    producto_id: str
    requerido: Decimal
    disponible: Decimal
    a_comprar: Decimal


def _d(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


# ── Núcleo puro ──────────────────────────────────────────────────────────────


def explotar_bom(
    componentes: list[ComponenteBOM],
    cantidad_a_producir,
    *,
    incluir_opcionales: bool = False,
) -> list[RequerimientoMaterial]:
    """Explota una lista de materiales: cantidad total de cada componente para
    producir `cantidad_a_producir` unidades del producto final."""
    cant = _d(cantidad_a_producir)
    if cant <= 0:
        raise ManufacturaError("La cantidad a producir debe ser positiva.")
    reqs: dict[str, Decimal] = {}
    for c in componentes:
        if c.es_opcional and not incluir_opcionales:
            continue
        reqs[c.producto_id] = reqs.get(c.producto_id, Decimal("0")) + _d(c.cantidad_requerida) * cant
    return [RequerimientoMaterial(pid, q) for pid, q in reqs.items()]


def calcular_mrp(
    requerimientos: list[RequerimientoMaterial],
    stock_disponible: dict[str, Decimal],
) -> list[FaltanteMaterial]:
    """MRP básico: compara requerimientos contra el stock y devuelve lo que falta
    comprar (a_comprar = max(0, requerido − disponible))."""
    faltantes: list[FaltanteMaterial] = []
    for req in requerimientos:
        disp = _d(stock_disponible.get(req.producto_id, Decimal("0")))
        a_comprar = req.cantidad - disp
        if a_comprar < 0:
            a_comprar = Decimal("0")
        faltantes.append(FaltanteMaterial(req.producto_id, req.cantidad, disp, a_comprar))
    return faltantes


def calcular_costo_produccion(
    consumos: list[tuple],  # [(costo_unitario, cantidad), ...]
    *,
    mano_obra: Decimal = Decimal("0"),
    costos_indirectos: Decimal = Decimal("0"),
    cantidad_producida: Decimal = Decimal("1"),
) -> dict:
    """Costo real de una OF: materiales + mano de obra + indirectos; y el costo
    unitario = costo_total / cantidad_producida."""
    cant = _d(cantidad_producida)
    if cant <= 0:
        raise ManufacturaError("La cantidad producida debe ser positiva.")
    costo_materiales = sum((_d(cu) * _d(q) for cu, q in consumos), Decimal("0"))
    costo_total = costo_materiales + _d(mano_obra) + _d(costos_indirectos)
    costo_unitario = (costo_total / cant).quantize(Decimal("0.0001"))
    return {
        "costo_materiales": costo_materiales,
        "mano_obra": _d(mano_obra),
        "costos_indirectos": _d(costos_indirectos),
        "costo_total": costo_total,
        "costo_unitario": costo_unitario,
    }


# ── Orquestación (ORM) ───────────────────────────────────────────────────────


def _componentes_de_lista(lista) -> list[ComponenteBOM]:
    return [
        ComponenteBOM(
            producto_id=str(det.id_producto_id),
            cantidad_requerida=_d(det.cantidad_requerida),
            es_opcional=det.es_opcional,
        )
        for det in lista.detalles.all()
    ]


def explotar_lista_materiales(lista, cantidad, *, incluir_opcionales: bool = False):
    """Explota una `ListaMateriales` del ORM para `cantidad` unidades."""
    return explotar_bom(_componentes_de_lista(lista), cantidad, incluir_opcionales=incluir_opcionales)


@transaction.atomic
def crear_orden_produccion(*, empresa, producto, cantidad, fecha_inicio=None,
                           lista_materiales=None, ruta_produccion=None, observaciones=""):
    """Crea una OrdenProduccion en estado pendiente."""
    from .models import OrdenProduccion

    if _d(cantidad) <= 0:
        raise ManufacturaError("La cantidad de la orden debe ser positiva.")
    return OrdenProduccion.objects.create(
        empresa=empresa,
        producto=producto,
        cantidad=_d(cantidad),
        fecha_inicio=fecha_inicio or timezone.now().date(),
        estado="pendiente",
        lista_materiales=lista_materiales,
        ruta_produccion=ruta_produccion,
        observaciones=observaciones,
    )


@transaction.atomic
def consumir_materiales_orden(orden, *, almacen, usuario, fecha_hora=None, incluir_opcionales=False):
    """Explota la BOM de la orden y descuenta los materiales del inventario
    (movimiento CONSUMO_PRODUCCION) creando un ConsumoMaterial por componente.

    Devuelve {"consumos": [...], "costo_materiales": Decimal}.
    """
    from apps.inventario.models import Producto
    from apps.inventario.services import registrar_movimiento

    from .models import ConsumoMaterial

    if orden.lista_materiales is None:
        raise ManufacturaError("La orden no tiene lista de materiales asociada.")

    fecha = fecha_hora or timezone.now()
    requerimientos = explotar_lista_materiales(
        orden.lista_materiales, orden.cantidad, incluir_opcionales=incluir_opcionales
    )
    consumos = []
    costo_materiales = Decimal("0")
    for req in requerimientos:
        producto = Producto.objects.get(pk=req.producto_id)
        registrar_movimiento(
            empresa=orden.empresa,
            fecha_hora_movimiento=fecha,
            tipo_movimiento="CONSUMO_PRODUCCION",
            producto=producto,
            cantidad=req.cantidad,
            almacen_origen=almacen,
            costo_unitario=producto.costo_promedio,
            documento_origen_id=orden.pk,
            nombre_modelo_origen="manufactura.OrdenProduccion",
            usuario=usuario,
            observaciones=f"Consumo de producción OP {orden.pk}",
        )
        consumos.append(
            ConsumoMaterial.objects.create(
                orden_produccion=orden, producto=producto, cantidad=req.cantidad
            )
        )
        costo_materiales += _d(producto.costo_promedio) * req.cantidad

    orden.estado = "en_proceso"
    orden.save(update_fields=["estado"])
    return {"consumos": consumos, "costo_materiales": costo_materiales}


@transaction.atomic
def registrar_produccion_terminada(orden, *, cantidad, almacen, usuario, fecha_hora=None,
                                   mano_obra=Decimal("0"), costos_indirectos=Decimal("0")):
    """Ingresa el producto terminado al inventario al costo real calculado y crea
    el registro ProduccionTerminada. Cierra la orden si se completó la cantidad."""
    from apps.inventario.services import registrar_movimiento

    from .models import ConsumoMaterial, ProduccionTerminada

    cant = _d(cantidad)
    if cant <= 0:
        raise ManufacturaError("La cantidad producida debe ser positiva.")
    fecha = fecha_hora or timezone.now()

    consumos = ConsumoMaterial.objects.filter(orden_produccion=orden).select_related("producto")
    costo = calcular_costo_produccion(
        [(c.producto.costo_promedio, c.cantidad) for c in consumos],
        mano_obra=mano_obra,
        costos_indirectos=costos_indirectos,
        cantidad_producida=cant,
    )

    registrar_movimiento(
        empresa=orden.empresa,
        fecha_hora_movimiento=fecha,
        tipo_movimiento="ENTRADA",
        producto=orden.producto,
        cantidad=cant,
        almacen_destino=almacen,
        costo_unitario=costo["costo_unitario"],
        documento_origen_id=orden.pk,
        nombre_modelo_origen="manufactura.OrdenProduccion",
        usuario=usuario,
        observaciones=f"Producción terminada OP {orden.pk}",
    )
    terminada = ProduccionTerminada.objects.create(orden_produccion=orden, cantidad=cant)

    producido = sum(
        (_d(p.cantidad) for p in ProduccionTerminada.objects.filter(orden_produccion=orden)),
        Decimal("0"),
    )
    orden.estado = "finalizada" if producido >= _d(orden.cantidad) else "parcial"
    orden.save(update_fields=["estado"])
    return {"produccion": terminada, "costo": costo}
