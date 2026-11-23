"""Servicios inteligentes de Inventario y Supply Chain (Plan 09 Fase 5.2, 5.3 y 5.4).

Incluye:
- Semáforo de margen real sobre ``costo_reposicion_usd`` (VERDE / AMARILLO / ROJO / SIN_COSTO).
- Búsqueda por código de barras / SKU.
- Conteo físico cíclico/total dual (``FISCAL`` vs ``GERENCIAL``) con ajuste automático.
- Escaneo barcode en stepper Pick-Pack-Ship (``OperacionInventarioLinea``).
- Resumen dual de inventario por ámbito.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.almacenes.models import Almacen, StockUbicacion, UbicacionAlmacen

from .models import (
    ConteoInventario,
    LineaConteoInventario,
    MovimientoInventario,
    OperacionInventario,
    OperacionInventarioLinea,
    Producto,
    StockActual,
    VarianteProducto,
)
from .services import (
    TIPOS_AJUSTE,
    TIPOS_ENTRADA,
    TIPOS_SALIDA,
    TIPOS_TRANSFERENCIA,
    MovimientoInvalidoError,
    StockInsuficienteError,
    registrar_movimiento,
)

_CERO = Decimal("0")
_CIEN = Decimal("100")
_Q4 = Decimal("0.0001")
_Q2 = Decimal("0.01")


class InventarioSupplyChainError(Exception):
    """Error de dominio en semáforo, conteo físico o escaneo de operaciones."""


def _q4(val: Decimal) -> Decimal:
    return val.quantize(_Q4, rounding=ROUND_HALF_UP)


def _q2(val: Decimal) -> Decimal:
    return val.quantize(_Q2, rounding=ROUND_HALF_UP)


def _dec(val: Any, default: Decimal | None = None) -> Decimal:
    if val is None or val == "":
        if default is not None:
            return default
        raise InventarioSupplyChainError("Se esperaba un valor numérico.")
    if isinstance(val, Decimal):
        return val
    try:
        dec = Decimal(str(val).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise InventarioSupplyChainError(f"Valor numérico inválido: {val!r}.") from exc
    if not dec.is_finite():
        raise InventarioSupplyChainError(f"Valor numérico no finito: {val!r}.")
    return dec


def evaluar_semaforo_margen_producto(
    producto: Producto,
    precio_venta_usd: Any | None = None,
) -> dict[str, Any]:
    """Evalúa el margen bruto real respecto al costo de reposición USD (o costo promedio)."""
    precio = (
        _dec(precio_venta_usd, _CERO)
        if precio_venta_usd is not None
        else _dec(getattr(producto, "precio_venta_sugerido", None), _CERO)
    )
    costo_repo = getattr(producto, "costo_reposicion_usd", None)
    fuente_costo = "COSTO_REPOSICION_USD"
    if costo_repo is not None and _dec(costo_repo, _CERO) > _CERO:
        costo_ref = _q4(_dec(costo_repo))
    else:
        costo_prom = _dec(getattr(producto, "costo_promedio", None), _CERO)
        costo_ref = _q4(costo_prom)
        fuente_costo = "COSTO_PROMEDIO"

    margen_min = _q2(_dec(getattr(producto, "margen_minimo_pct", Decimal("15.00")), Decimal("15.00")))
    margen_alerta = _q2(_dec(getattr(producto, "margen_alerta_pct", Decimal("25.00")), Decimal("25.00")))
    if margen_alerta < margen_min:
        margen_alerta = margen_min

    if costo_ref <= _CERO:
        return {
            "producto_id": str(producto.pk),
            "producto": producto.nombre_producto,
            "semaforo": "SIN_COSTO",
            "alerta_activa": False,
            "precio_venta_usd": str(_q4(precio)),
            "costo_referencia_usd": "0.0000",
            "fuente_costo": "NINGUNO",
            "utilidad_unitaria_usd": str(_q4(precio)),
            "margen_pct": None,
            "margen_minimo_pct": str(margen_min),
            "margen_alerta_pct": str(margen_alerta),
            "mensaje": "El producto no tiene costo de reposición ni costo promedio cargado.",
        }

    utilidad = _q4(precio - costo_ref)
    if precio > _CERO:
        margen_pct = _q2((utilidad / precio) * _CIEN)
    else:
        margen_pct = Decimal("-100.00")

    if margen_pct < margen_min:
        semaforo = "ROJO"
        alerta_activa = True
        mensaje = (
            f"Margen real ({margen_pct}%) por debajo del mínimo configurado ({margen_min}%) "
            f"sobre {fuente_costo.lower()}."
        )
    elif margen_pct < margen_alerta:
        semaforo = "AMARILLO"
        alerta_activa = True
        mensaje = (
            f"Margen preventivo ({margen_pct}%): entre mínimo ({margen_min}%) "
            f"y umbral objetivo ({margen_alerta}%)."
        )
    else:
        semaforo = "VERDE"
        alerta_activa = False
        mensaje = f"Margen saludable ({margen_pct}%)."

    return {
        "producto_id": str(producto.pk),
        "producto": producto.nombre_producto,
        "semaforo": semaforo,
        "alerta_activa": alerta_activa,
        "precio_venta_usd": str(_q4(precio)),
        "costo_referencia_usd": str(costo_ref),
        "fuente_costo": fuente_costo,
        "utilidad_unitaria_usd": str(utilidad),
        "margen_pct": str(margen_pct),
        "margen_minimo_pct": str(margen_min),
        "margen_alerta_pct": str(margen_alerta),
        "mensaje": mensaje,
    }


def buscar_producto_por_barcode(empresa, codigo: str) -> Producto:
    """Busca un producto activo de ``empresa`` por ``codigo_barras`` exacto o ``sku``."""
    limpio = (codigo or "").strip()
    if not limpio:
        raise InventarioSupplyChainError("Debe indicar un código de barras o SKU.")
    prod = (
        Producto.objects.filter(id_empresa=empresa, activo=True)
        .filter(Q(codigo_barras=limpio) | Q(sku=limpio))
        .order_by("nombre_producto")
        .first()
    )
    if prod is None:
        raise InventarioSupplyChainError(f"No se encontró producto activo con código '{limpio}' en la empresa.")
    return prod


def _cantidad_sistema_teorica(
    *,
    empresa,
    almacen: Almacen,
    producto: Producto,
    variante: VarianteProducto | None,
    ubicacion: UbicacionAlmacen | None,
) -> Decimal:
    if ubicacion is not None and almacen.usa_ubicaciones:
        su = StockUbicacion.objects.filter(
            id_empresa=empresa,
            id_almacen=almacen,
            id_ubicacion=ubicacion,
            id_producto=producto,
            id_variante=variante,
        ).first()
        return _q4(_dec(su.cantidad_disponible, _CERO)) if su is not None else _CERO
    sa = StockActual.objects.filter(
        id_empresa=empresa,
        id_almacen=almacen,
        id_producto=producto,
        id_variante=variante,
    ).first()
    return _q4(_dec(sa.cantidad_disponible, _CERO)) if sa is not None else _CERO


def _numero_conteo(empresa) -> str:
    n = ConteoInventario.objects.filter(id_empresa=empresa).count() + 1
    return f"CNT-{n:06d}"


@transaction.atomic
def crear_conteo_inventario(
    *,
    empresa,
    almacen: Almacen,
    responsable,
    tipo_conteo: str = "CICLICO",
    ambito: str = "FISCAL",
    fecha_conteo: date | None = None,
    numero: str | None = None,
    observaciones: str = "",
    items: list[dict[str, Any]] | None = None,
) -> ConteoInventario:
    """Crea una sesión de conteo físico (opcionalmente precargada con líneas o automática por almacén)."""
    if almacen.id_empresa_id != empresa.pk:
        raise InventarioSupplyChainError("El almacén no pertenece a la empresa.")
    if tipo_conteo not in dict(ConteoInventario.TIPOS):
        raise InventarioSupplyChainError(f"Tipo de conteo inválido: {tipo_conteo!r}.")
    if ambito not in ("FISCAL", "GERENCIAL"):
        raise InventarioSupplyChainError(f"Ámbito contable inválido: {ambito!r}.")

    num = (numero or "").strip() or _numero_conteo(empresa)
    conteo = ConteoInventario.objects.create(
        id_empresa=empresa,
        numero=num,
        id_almacen=almacen,
        ambito=ambito,
        tipo_conteo=tipo_conteo,
        estado="EN_PROGRESO",
        fecha_conteo=fecha_conteo or timezone.localdate(),
        id_responsable=responsable,
        observaciones=observaciones or "",
    )

    if items:
        for it in items:
            prod = it["producto"]
            var = it.get("variante")
            ubic = it.get("ubicacion")
            if prod.id_empresa_id != empresa.pk:
                raise InventarioSupplyChainError(f"El producto '{prod}' no pertenece a la empresa.")
            if ubic is not None and (ubic.id_empresa_id != empresa.pk or ubic.id_almacen_id != almacen.pk):
                raise InventarioSupplyChainError("La ubicación indicada no pertenece al almacén del conteo.")
            cant_sis = _cantidad_sistema_teorica(
                empresa=empresa,
                almacen=almacen,
                producto=prod,
                variante=var,
                ubicacion=ubic,
            )
            costo_ref = _q4(_dec(prod.costo_reposicion_usd or prod.costo_promedio, _CERO))
            LineaConteoInventario.objects.create(
                id_empresa=empresa,
                id_conteo=conteo,
                id_producto=prod,
                id_variante=var,
                id_ubicacion=ubic,
                cantidad_sistema=cant_sis,
                costo_unitario_referencia=costo_ref,
            )
    elif tipo_conteo == "TOTAL":
        stocks = StockActual.objects.filter(id_empresa=empresa, id_almacen=almacen).select_related(
            "id_producto", "id_variante"
        )
        for sa in stocks:
            costo_ref = _q4(_dec(sa.id_producto.costo_reposicion_usd or sa.id_producto.costo_promedio, _CERO))
            LineaConteoInventario.objects.create(
                id_empresa=empresa,
                id_conteo=conteo,
                id_producto=sa.id_producto,
                id_variante=sa.id_variante,
                cantidad_sistema=_q4(_dec(sa.cantidad_disponible, _CERO)),
                costo_unitario_referencia=costo_ref,
            )

    return conteo


@transaction.atomic
def registrar_escaneo_conteo(
    *,
    conteo: ConteoInventario,
    codigo_o_producto_id: str,
    cantidad: Any = Decimal("1"),
    modo: str = "INCREMENTAL",
    variante_id: str | None = None,
    ubicacion_id: str | None = None,
    observaciones: str = "",
) -> LineaConteoInventario:
    """Registra el escaneo de un producto en un conteo (incrementa o fija cantidad contada)."""
    conteo_locked = (
        ConteoInventario.objects.select_for_update(of=("self",))
        .select_related("id_empresa", "id_almacen")
        .get(pk=conteo.pk)
    )
    if conteo_locked.estado not in ("BORRADOR", "EN_PROGRESO"):
        raise InventarioSupplyChainError(f"El conteo no admite escaneos en estado {conteo_locked.estado}.")
    if modo not in ("INCREMENTAL", "REEMPLAZAR"):
        raise InventarioSupplyChainError(f"Modo de escaneo inválido: {modo!r}.")

    cant_dec = _q4(_dec(cantidad))
    if modo == "INCREMENTAL" and cant_dec <= _CERO:
        raise InventarioSupplyChainError("En modo INCREMENTAL la cantidad escaneada debe ser mayor a cero.")
    if modo == "REEMPLAZAR" and cant_dec < _CERO:
        raise InventarioSupplyChainError("La cantidad contada no puede ser negativa.")

    empresa = conteo_locked.id_empresa
    almacen = conteo_locked.id_almacen

    prod = (
        Producto.objects.filter(
            id_empresa=empresa,
            activo=True,
        )
        .filter(Q(codigo_barras=codigo_o_producto_id) | Q(sku=codigo_o_producto_id))
        .first()
    )
    if prod is None:
        # También acepta UUID exacto del producto.
        try:
            prod = Producto.objects.filter(id_empresa=empresa, pk=codigo_o_producto_id, activo=True).first()
        except Exception:
            prod = None
    if prod is None:
        raise InventarioSupplyChainError(
            f"Producto con código/ID '{codigo_o_producto_id}' no encontrado en la empresa."
        )

    variante = None
    if variante_id:
        variante = VarianteProducto.objects.filter(pk=variante_id, id_producto=prod).first()
        if variante is None:
            raise InventarioSupplyChainError("La variante no pertenece al producto escaneado.")

    ubicacion = None
    if ubicacion_id:
        ubicacion = UbicacionAlmacen.objects.filter(pk=ubicacion_id, id_empresa=empresa, id_almacen=almacen).first()
        if ubicacion is None:
            raise InventarioSupplyChainError("La ubicación no pertenece al almacén del conteo.")

    linea = (
        LineaConteoInventario.objects.select_for_update()
        .filter(
            id_conteo=conteo_locked,
            id_producto=prod,
            id_variante=variante,
            id_ubicacion=ubicacion,
        )
        .first()
    )
    if linea is None:
        cant_sis = _cantidad_sistema_teorica(
            empresa=empresa,
            almacen=almacen,
            producto=prod,
            variante=variante,
            ubicacion=ubicacion,
        )
        costo_ref = _q4(_dec(prod.costo_reposicion_usd or prod.costo_promedio, _CERO))
        linea = LineaConteoInventario.objects.create(
            id_empresa=empresa,
            id_conteo=conteo_locked,
            id_producto=prod,
            id_variante=variante,
            id_ubicacion=ubicacion,
            cantidad_sistema=cant_sis,
            costo_unitario_referencia=costo_ref,
        )

    base_contada = _dec(linea.cantidad_contada, _CERO)
    nueva_contada = _q4(base_contada + cant_dec) if modo == "INCREMENTAL" else cant_dec
    diferencia = _q4(nueva_contada - _dec(linea.cantidad_sistema, _CERO))
    valor_diferencia = _q4(diferencia * _dec(linea.costo_unitario_referencia, _CERO))

    linea.cantidad_contada = nueva_contada
    linea.diferencia = diferencia
    linea.valor_diferencia = valor_diferencia
    linea.conteos_escaneados = (linea.conteos_escaneados or 0) + 1
    if observaciones:
        linea.observaciones = observaciones
    linea.save(
        update_fields=[
            "cantidad_contada",
            "diferencia",
            "valor_diferencia",
            "conteos_escaneados",
            "observaciones",
            "fecha_actualizacion",
        ]
    )

    if conteo_locked.estado == "BORRADOR":
        conteo_locked.estado = "EN_PROGRESO"
        conteo_locked.save(update_fields=["estado", "fecha_actualizacion"])

    return linea


@transaction.atomic
def enviar_conteo_aprobacion(conteo: ConteoInventario) -> ConteoInventario:
    """Cierra la captura de escaneos y deja el conteo listo para aprobación."""
    conteo_locked = ConteoInventario.objects.select_for_update().get(pk=conteo.pk)
    if conteo_locked.estado not in ("BORRADOR", "EN_PROGRESO"):
        raise InventarioSupplyChainError(
            f"Solo se pueden enviar a aprobación conteos en BORRADOR o EN_PROGRESO. Estado: {conteo_locked.estado}."
        )
    if not conteo_locked.lineas.exists():
        raise InventarioSupplyChainError("No se puede enviar a aprobación un conteo sin líneas registradas.")
    conteo_locked.estado = "PENDIENTE_APROBACION"
    conteo_locked.save(update_fields=["estado", "fecha_actualizacion"])
    return conteo_locked


@transaction.atomic
def aprobar_aplicar_conteo(conteo: ConteoInventario, aprobador) -> dict[str, Any]:
    """Aprueba un conteo y genera ajustes de inventario para cada diferencia detectada."""
    conteo_locked = (
        ConteoInventario.objects.select_for_update(of=("self",))
        .select_related("id_empresa", "id_almacen")
        .get(pk=conteo.pk)
    )
    if conteo_locked.estado not in ("EN_PROGRESO", "PENDIENTE_APROBACION"):
        raise InventarioSupplyChainError(f"El conteo no puede aprobarse en estado {conteo_locked.estado}.")

    lineas = list(
        conteo_locked.lineas.select_for_update(of=("self",)).select_related(
            "id_producto", "id_variante", "id_ubicacion"
        )
    )
    if not lineas:
        raise InventarioSupplyChainError("El conteo no posee líneas para aplicar.")

    empresa = conteo_locked.id_empresa
    almacen = conteo_locked.id_almacen
    ahora = timezone.now()
    movimientos: list[MovimientoInventario] = []

    for ln in lineas:
        if ln.cantidad_contada is None:
            # Línea no escaneada: no se ajusta automáticamente; se preserva sistema.
            continue
        dif = _q4(_dec(ln.cantidad_contada) - _dec(ln.cantidad_sistema))
        ln.diferencia = dif
        ln.valor_diferencia = _q4(dif * _dec(ln.costo_unitario_referencia))
        ln.save(update_fields=["diferencia", "valor_diferencia", "fecha_actualizacion"])

        if dif == _CERO:
            continue

        costo_u = _dec(ln.costo_unitario_referencia, _CERO) if dif > _CERO else None
        try:
            mov = registrar_movimiento(
                empresa=empresa,
                fecha_hora_movimiento=ahora,
                tipo_movimiento="AJUSTE",
                producto=ln.id_producto,
                variante=ln.id_variante,
                cantidad=dif,
                almacen_destino=almacen,
                costo_unitario=costo_u,
                documento_origen_id=conteo_locked.id_conteo,
                nombre_modelo_origen="ConteoInventario",
                usuario=aprobador,
                observaciones=f"Ajuste conteo {conteo_locked.numero} [{conteo_locked.ambito}]",
                ambito=conteo_locked.ambito,
            )
        except (StockInsuficienteError, MovimientoInvalidoError) as exc:
            raise InventarioSupplyChainError(f"Error ajustando stock de {ln.id_producto}: {exc}") from exc
        movimientos.append(mov)

        if ln.id_ubicacion is not None and almacen.usa_ubicaciones:
            su, _ = StockUbicacion.objects.get_or_create(
                id_empresa=empresa,
                id_almacen=almacen,
                id_ubicacion=ln.id_ubicacion,
                id_producto=ln.id_producto,
                id_variante=ln.id_variante,
                defaults={"cantidad_disponible": _CERO, "cantidad_reservada": _CERO},
            )
            su_locked = StockUbicacion.objects.select_for_update().get(pk=su.pk)
            su_locked.cantidad_disponible = _q4(_dec(ln.cantidad_contada))
            su_locked.save(update_fields=["cantidad_disponible", "fecha_actualizacion"])

    conteo_locked.estado = "APLICADO"
    conteo_locked.id_aprobador = aprobador
    conteo_locked.fecha_aprobacion = ahora
    conteo_locked.save(update_fields=["estado", "id_aprobador", "fecha_aprobacion", "fecha_actualizacion"])

    return {
        "conteo": conteo_locked,
        "ajustes_generados": len(movimientos),
        "movimientos_ids": [str(m.pk) for m in movimientos],
    }


@transaction.atomic
def anular_conteo(conteo: ConteoInventario) -> ConteoInventario:
    """Anula un conteo que aún no ha sido aplicado."""
    conteo_locked = ConteoInventario.objects.select_for_update().get(pk=conteo.pk)
    if conteo_locked.estado in ("APLICADO", "ANULADO"):
        raise InventarioSupplyChainError(f"No se puede anular un conteo en estado {conteo_locked.estado}.")
    conteo_locked.estado = "ANULADO"
    conteo_locked.save(update_fields=["estado", "fecha_actualizacion"])
    return conteo_locked


@transaction.atomic
def escanear_linea_operacion(
    *,
    operacion: OperacionInventario,
    codigo: str,
    cantidad: Any = Decimal("1"),
) -> dict[str, Any]:
    """Incrementa ``cantidad_escaneada`` en la línea Pick-Pack-Ship que coincide por barcode/SKU."""
    op_locked = OperacionInventario.objects.select_for_update().get(pk=operacion.pk)
    if op_locked.estado != "EN_PROCESO":
        raise InventarioSupplyChainError(
            f"La operación {op_locked.numero} debe estar EN_PROCESO para escanear bultos."
        )

    cant_dec = _q4(_dec(cantidad))
    if cant_dec <= _CERO:
        raise InventarioSupplyChainError("La cantidad escaneada debe ser mayor a cero.")

    limpio = (codigo or "").strip()
    if not limpio:
        raise InventarioSupplyChainError("Debe indicar un código de barras o SKU.")

    lineas = list(
        OperacionInventarioLinea.objects.select_for_update(of=("self",))
        .select_related("id_producto")
        .filter(id_operacion=op_locked)
        .filter(Q(id_producto__codigo_barras=limpio) | Q(id_producto__sku=limpio))
        .order_by("id_linea")
    )
    if not lineas:
        raise InventarioSupplyChainError(
            f"El código '{limpio}' no corresponde a ninguna línea de la operación {op_locked.numero}."
        )

    # Seleccionar primera línea pendiente por completar.
    linea_objetivo = None
    for ln in lineas:
        if _dec(ln.cantidad_escaneada, _CERO) + cant_dec <= _dec(ln.cantidad):
            linea_objetivo = ln
            break

    if linea_objetivo is None:
        raise InventarioSupplyChainError(
            f"Sobre-escaneo detectado para '{limpio}': excede la cantidad planificada de la operación."
        )

    linea_objetivo.cantidad_escaneada = _q4(_dec(linea_objetivo.cantidad_escaneada, _CERO) + cant_dec)
    linea_objetivo.save(update_fields=["cantidad_escaneada"])

    todas = list(OperacionInventarioLinea.objects.filter(id_operacion=op_locked))
    completo = all(_dec(it.cantidad_escaneada, _CERO) >= _dec(it.cantidad) for it in todas)

    return {
        "operacion_id": str(op_locked.pk),
        "numero": op_locked.numero,
        "linea_id": str(linea_objetivo.pk),
        "producto_id": str(linea_objetivo.id_producto_id),
        "producto": linea_objetivo.id_producto.nombre_producto,
        "cantidad_planificada": str(linea_objetivo.cantidad),
        "cantidad_escaneada": str(linea_objetivo.cantidad_escaneada),
        "escaneo_completo": completo,
    }


def resumen_inventario_dual(empresa, almacen_id: str | None = None) -> dict[str, Any]:
    """Consolida movimientos de inventario diferenciados por ámbito FISCAL vs GERENCIAL."""
    qs = MovimientoInventario.objects.filter(id_empresa=empresa).select_related("id_producto")
    if almacen_id:
        qs = qs.filter(Q(id_almacen_origen_id=almacen_id) | Q(id_almacen_destino_id=almacen_id))

    por_ambito: dict[str, dict[str, Decimal]] = {
        "FISCAL": {"entradas": _CERO, "salidas": _CERO, "ajustes_netos": _CERO, "valor_movido": _CERO},
        "GERENCIAL": {"entradas": _CERO, "salidas": _CERO, "ajustes_netos": _CERO, "valor_movido": _CERO},
    }
    conteos_movs = {"FISCAL": 0, "GERENCIAL": 0}

    for mov in qs:
        amb = mov.ambito if mov.ambito in por_ambito else "FISCAL"
        conteos_movs[amb] += 1
        qty = _dec(mov.cantidad, _CERO)
        costo = _dec(mov.costo_unitario_movimiento, _CERO)
        val = _q4(abs(qty) * costo)
        if mov.tipo_movimiento in TIPOS_ENTRADA or mov.tipo_movimiento in TIPOS_TRANSFERENCIA:
            por_ambito[amb]["entradas"] += qty
        elif mov.tipo_movimiento in TIPOS_SALIDA:
            por_ambito[amb]["salidas"] += qty
        elif mov.tipo_movimiento in TIPOS_AJUSTE:
            por_ambito[amb]["ajustes_netos"] += qty
        por_ambito[amb]["valor_movido"] += val

    stock_tot = StockActual.objects.filter(id_empresa=empresa)
    if almacen_id:
        stock_tot = stock_tot.filter(id_almacen_id=UUID(str(almacen_id)))
    stock_agg = stock_tot.aggregate(
        disp=Sum("cantidad_disponible"),
        comp=Sum("cantidad_comprometida"),
        valor_costo=Sum(F("cantidad_disponible") * F("id_producto__costo_promedio")),
    )

    return {
        "almacen_id": almacen_id,
        "ambitos": {
            amb: {k: str(_q4(v)) for k, v in metrics.items()} | {"movimientos": conteos_movs[amb]}
            for amb, metrics in por_ambito.items()
        },
        "stock_consolidado": {
            "cantidad_disponible": str(_q4(_dec(stock_agg["disp"], _CERO))),
            "cantidad_comprometida": str(_q4(_dec(stock_agg["comp"], _CERO))),
            "valor_inventario_costo_promedio": str(_q4(_dec(stock_agg["valor_costo"], _CERO))),
        },
    }
