"""Lógica de manufactura (Ola 5.3): explosión de BOM, órdenes de producción,
consumo de materiales ↔ inventario, costeo real y MRP básico.

El cálculo (explosión, MRP, costeo) está aislado en funciones PURAS (Decimal, sin
I/O) para ser testeable y portable (§5.2-ter); la orquestación lee/escribe el ORM
y reutiliza `inventario.services.registrar_movimiento` (R-CODE-11 vía inventario).
"""
from __future__ import annotations

import logging
import uuid
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


def calcular_costo_mano_obra(
    etapas: list[tuple],  # [(horas, tarifa_hora, pago_destajo), ...]
) -> Decimal:
    """Mano de obra real de una OF a partir de sus etapas completadas:
    Σ (horas × tarifa) + pago a destajo. Función pura, Decimal."""
    total = Decimal("0")
    for horas, tarifa, destajo in etapas:
        total += _d(horas) * _d(tarifa) + _d(destajo)
    return total


def calcular_overhead(base: Decimal, porcentaje: Decimal) -> Decimal:
    """Overhead configurable: % sobre la base (materiales + mano de obra)."""
    return (_d(base) * _d(porcentaje) / Decimal("100")).quantize(Decimal("0.0001"))


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
    cuatro = Decimal("0.0001")
    costo_materiales = sum((_d(cu) * _d(q) for cu, q in consumos), Decimal("0")).quantize(cuatro)
    costo_total = (costo_materiales + _d(mano_obra) + _d(costos_indirectos)).quantize(cuatro)
    costo_unitario = (costo_total / cant).quantize(cuatro)
    return {
        "costo_materiales": costo_materiales,
        "mano_obra": _d(mano_obra).quantize(cuatro),
        "costos_indirectos": _d(costos_indirectos).quantize(cuatro),
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
    orden = OrdenProduccion.objects.create(
        empresa=empresa,
        producto=producto,
        cantidad=_d(cantidad),
        fecha_inicio=fecha_inicio or timezone.now().date(),
        estado="pendiente",
        lista_materiales=lista_materiales,
        ruta_produccion=ruta_produccion,
        observaciones=observaciones,
    )
    # 1.I — materializar las etapas vigentes del catálogo de la empresa.
    # Si la empresa no configuró etapas, la OF opera sin ellas (flujo simple).
    crear_etapas_para_orden(orden)
    return orden


# ── Etapas de OF (1.I) ───────────────────────────────────────────────────────


@transaction.atomic
def crear_etapas_estandar(empresa):
    """Siembra el catálogo de etapas estándar de mueblería para una empresa
    (corte → ensamble → lijado → pintura → tapizado → control final).
    Idempotente: no duplica códigos ya existentes."""
    from .models import ETAPAS_ESTANDAR, EtapaProduccion

    creadas = []
    for i, (codigo, nombre) in enumerate(ETAPAS_ESTANDAR, start=1):
        etapa, creada = EtapaProduccion.objects.get_or_create(
            empresa=empresa, codigo=codigo, defaults={"nombre": nombre, "orden": i}
        )
        if creada:
            creadas.append(etapa)
    return creadas


@transaction.atomic
def crear_etapas_para_orden(orden):
    """Copia la secuencia vigente de etapas (catálogo activo de la empresa)
    a la OF. No hace nada si la OF ya tiene etapas."""
    from .models import EtapaOrdenProduccion, EtapaProduccion

    if orden.etapas.exists():
        return list(orden.etapas.all())
    catalogo = EtapaProduccion.objects.filter(empresa=orden.empresa, activo=True).order_by("orden")
    return [
        EtapaOrdenProduccion.objects.create(orden_produccion=orden, etapa=etapa, orden=i)
        for i, etapa in enumerate(catalogo, start=1)
    ]


@transaction.atomic
def avanzar_etapa_orden(orden, *, usuario, horas_trabajadas=Decimal("0"),
                        tarifa_hora=Decimal("0"), cantidad_destajo=Decimal("0"),
                        observaciones=""):
    """Completa la siguiente etapa pendiente de la OF (en secuencia) registrando
    quién/cuándo y la mano de obra de la etapa: horas × tarifa y/o pago a
    destajo (cantidad × tarifa_destajo de la etapa del catálogo)."""
    if orden.estado in ("finalizada", "cancelada"):
        raise ManufacturaError(f"La orden está {orden.estado}; no admite avance de etapas.")

    # select_for_update: dos avances concurrentes no deben completar la misma etapa.
    etapa_of = (
        orden.etapas.select_for_update()
        .filter(estado="pendiente")
        .order_by("orden")
        .select_related("etapa")
        .first()
    )
    if etapa_of is None:
        raise ManufacturaError("La orden no tiene etapas pendientes.")

    horas = _d(horas_trabajadas)
    tarifa = _d(tarifa_hora)
    cant_destajo = _d(cantidad_destajo)
    if horas < 0 or tarifa < 0 or cant_destajo < 0:
        raise ManufacturaError("Horas, tarifa y cantidad a destajo no pueden ser negativas.")

    etapa_of.estado = "completada"
    etapa_of.horas_trabajadas = horas
    etapa_of.tarifa_hora = tarifa
    etapa_of.cantidad_destajo = cant_destajo
    etapa_of.pago_destajo = (cant_destajo * _d(etapa_of.etapa.tarifa_destajo)).quantize(Decimal("0.0001"))
    etapa_of.completada_por = usuario
    etapa_of.fecha_completada = timezone.now()
    if observaciones:
        etapa_of.observaciones = observaciones
    etapa_of.save()

    if orden.estado == "pendiente":
        orden.estado = "en_proceso"
        orden.save(update_fields=["estado"])
    return etapa_of


def costo_mano_obra_orden(orden) -> Decimal:
    """Mano de obra real acumulada de la OF (etapas completadas)."""
    return calcular_costo_mano_obra([
        (e.horas_trabajadas, e.tarifa_hora, e.pago_destajo)
        for e in orden.etapas.filter(estado="completada")
    ])


def _overhead_empresa(empresa, base: Decimal) -> Decimal:
    """Overhead según ConfiguracionManufactura de la empresa (0 si no hay)."""
    from .models import ConfiguracionManufactura

    config = ConfiguracionManufactura.objects.filter(empresa=empresa).first()
    if config is None:
        return Decimal("0")
    return calcular_overhead(base, config.porcentaje_overhead)


def costeo_real_orden(orden, *, mano_obra=None, costos_indirectos=None,
                      cantidad_producida=None) -> dict:
    """Costeo real de la OF: materiales consumidos (al costo del movimiento de
    inventario) + mano de obra (etapas: horas × tarifa + destajo, salvo monto
    explícito) + overhead configurable (salvo monto explícito).

    Devuelve el dict de `calcular_costo_produccion` (Decimal en todo, R-CODE-4).
    """
    from .models import ConsumoMaterial

    consumos = ConsumoMaterial.objects.filter(orden_produccion=orden).select_related("producto")
    # costo_unitario es el snapshot del movimiento; los consumos legados (0)
    # caen al costo_promedio vigente del producto.
    pares = [
        (c.costo_unitario if _d(c.costo_unitario) > 0 else c.producto.costo_promedio, c.cantidad)
        for c in consumos
    ]
    mo = _d(mano_obra) if mano_obra is not None else costo_mano_obra_orden(orden)
    costo_materiales = sum((_d(cu) * _d(q) for cu, q in pares), Decimal("0"))
    oh = _d(costos_indirectos) if costos_indirectos is not None else _overhead_empresa(
        orden.empresa, costo_materiales + mo
    )
    cant = _d(cantidad_producida) if cantidad_producida is not None else _d(orden.cantidad)
    return calcular_costo_produccion(pares, mano_obra=mo, costos_indirectos=oh, cantidad_producida=cant)


def calcular_mrp_orden(orden, *, almacen=None, incluir_opcionales=False) -> list[dict]:
    """MRP básico de la OF: explosión de su BOM vs StockActual de la empresa
    (disponible neto = disponible − comprometido) → faltantes a comprar."""
    if orden.lista_materiales is None:
        raise ManufacturaError("La orden no tiene lista de materiales asociada.")
    return calcular_mrp_lista(
        orden.lista_materiales, orden.cantidad, almacen=almacen, incluir_opcionales=incluir_opcionales
    )


def calcular_mrp_lista(lista, cantidad, *, almacen=None, incluir_opcionales=False) -> list[dict]:
    """MRP básico: materiales necesarios para producir `cantidad` unidades con
    la BOM `lista`, comparados contra el StockActual de la empresa (opcionalmente
    de un almacén). Devuelve requerido/disponible/a_comprar por componente."""
    from apps.inventario.models import Producto, StockActual

    requerimientos = explotar_lista_materiales(lista, cantidad, incluir_opcionales=incluir_opcionales)
    producto_ids = [r.producto_id for r in requerimientos]

    stock_qs = StockActual.objects.filter(id_empresa=lista.empresa, id_producto_id__in=producto_ids)
    if almacen is not None:
        stock_qs = stock_qs.filter(id_almacen=almacen)
    disponible: dict[str, Decimal] = {}
    for s in stock_qs:
        neto = _d(s.cantidad_disponible) - _d(s.cantidad_comprometida)
        disponible[str(s.id_producto_id)] = disponible.get(str(s.id_producto_id), Decimal("0")) + neto

    nombres = dict(
        Producto.objects.filter(pk__in=producto_ids).values_list("id_producto", "nombre_producto")
    )
    faltantes = calcular_mrp(requerimientos, disponible)
    return [
        {
            "producto_id": f.producto_id,
            "producto": nombres.get(uuid.UUID(f.producto_id), ""),
            "requerido": f.requerido,
            "disponible": f.disponible,
            "a_comprar": f.a_comprar,
        }
        for f in faltantes
    ]


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
    if orden.estado in ("finalizada", "cancelada"):
        raise ManufacturaError(f"La orden está {orden.estado}; no admite consumo de materiales.")

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
                orden_produccion=orden,
                producto=producto,
                cantidad=req.cantidad,
                # snapshot del costo del movimiento — base del costeo real (1.I)
                costo_unitario=_d(producto.costo_promedio),
            )
        )
        costo_materiales += _d(producto.costo_promedio) * req.cantidad

    orden.estado = "en_proceso"
    orden.save(update_fields=["estado"])
    return {"consumos": consumos, "costo_materiales": costo_materiales.quantize(Decimal("0.0001"))}


@transaction.atomic
def registrar_produccion_terminada(orden, *, cantidad, almacen, usuario, fecha_hora=None,
                                   mano_obra=None, costos_indirectos=None):
    """Ingresa el producto terminado al inventario al costo real calculado y crea
    el registro ProduccionTerminada. Cierra la orden si se completó la cantidad.

    1.I — Una OF con etapas NO puede cerrarse con etapas pendientes. Si no se
    pasa `mano_obra`, se toma de las etapas (horas × tarifa + destajo); si no
    se pasa `costos_indirectos`, se aplica el overhead configurado de la empresa.
    """
    from apps.inventario.services import registrar_movimiento

    from .models import ProduccionTerminada

    cant = _d(cantidad)
    if cant <= 0:
        raise ManufacturaError("La cantidad producida debe ser positiva.")
    if orden.estado in ("finalizada", "cancelada"):
        raise ManufacturaError(f"La orden está {orden.estado}; no admite más producción.")
    pendientes = orden.etapas.filter(estado="pendiente").count()
    if pendientes:
        raise ManufacturaError(
            f"La orden tiene {pendientes} etapa(s) pendiente(s); complétalas antes de cerrar."
        )
    fecha = fecha_hora or timezone.now()

    costo = costeo_real_orden(
        orden, mano_obra=mano_obra, costos_indirectos=costos_indirectos, cantidad_producida=cant
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
