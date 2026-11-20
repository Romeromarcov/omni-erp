"""Servicios de dominio para reglas de reabastecimiento (Plan 08 §B.3).

Expone:
  - ``evaluar_reabastecimiento(empresa, *, almacen=None, incluir_ok=False)``
  - ``generar_borrador_reabastecimiento(regla, *, usuario, cantidad=None, fecha_necesidad=None)``
  - ``ReabastecimientoError``
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any
import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    OperacionInventario,
    OperacionInventarioLinea,
    PasoOperacion,
    ReglaReabastecimiento,
    StockActual,
)

_CERO = Decimal("0")
_Q4 = Decimal("0.0001")
_Q2 = Decimal("0.01")


class ReabastecimientoError(Exception):
    """Error controlado en la evaluación o generación de reabastecimiento."""


def _parse_decimal(valor: Any, campo: str) -> Decimal:
    if valor is None or isinstance(valor, bool):
        raise ReabastecimientoError(f"El campo '{campo}' debe ser numérico.")
    try:
        dec = valor if isinstance(valor, Decimal) else Decimal(str(valor).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ReabastecimientoError(f"Valor numérico inválido para '{campo}': {valor!r}.") from exc
    if not dec.is_finite():
        raise ReabastecimientoError(f"El valor de '{campo}' debe ser finito.")
    return dec


def _parse_fecha(valor: date | datetime | str | None) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor.strip())
        except ValueError as exc:
            raise ReabastecimientoError("fecha_necesidad debe tener formato YYYY-MM-DD.") from exc
    raise ReabastecimientoError("fecha_necesidad inválida.")


def _evaluar_regla_con_stock(regla: ReglaReabastecimiento, stock: StockActual | None) -> dict[str, Any]:
    disponible = stock.cantidad_disponible if stock is not None else _CERO
    comprometida = stock.cantidad_comprometida if stock is not None else _CERO
    en_transito = stock.cantidad_en_transito if stock is not None else _CERO
    stock_libre = disponible - comprometida
    stock_proyectado = stock_libre + en_transito

    requiere = stock_proyectado <= regla.stock_minimo
    if requiere:
        deficit = max(_CERO, regla.stock_maximo - stock_proyectado)
        if deficit > _CERO:
            multiplo = regla.cantidad_multiplo
            cantidad_sugerida = ((deficit / multiplo).to_integral_value(rounding=ROUND_CEILING) * multiplo).quantize(
                _Q4
            )
        else:
            cantidad_sugerida = _CERO
    else:
        deficit = _CERO
        cantidad_sugerida = _CERO

    return {
        "id_regla": str(regla.id_regla),
        "id_producto": str(regla.id_producto_id),
        "producto_nombre": regla.id_producto.nombre_producto,
        "producto_sku": regla.id_producto.sku or "",
        "id_variante": str(regla.id_variante_id) if regla.id_variante_id else None,
        "id_almacen": str(regla.id_almacen_id),
        "almacen_nombre": regla.id_almacen.nombre_almacen,
        "ruta": regla.ruta,
        "id_proveedor_preferido": str(regla.id_proveedor_preferido_id) if regla.id_proveedor_preferido_id else None,
        "id_almacen_origen": str(regla.id_almacen_origen_id) if regla.id_almacen_origen_id else None,
        "stock_disponible": disponible.quantize(_Q4),
        "cantidad_comprometida": comprometida.quantize(_Q4),
        "cantidad_en_transito": en_transito.quantize(_Q4),
        "stock_libre": stock_libre.quantize(_Q4),
        "stock_proyectado": stock_proyectado.quantize(_Q4),
        "stock_minimo": regla.stock_minimo.quantize(_Q4),
        "stock_maximo": regla.stock_maximo.quantize(_Q4),
        "cantidad_multiplo": regla.cantidad_multiplo.quantize(_Q4),
        "requiere_reabastecimiento": requiere,
        "deficit": deficit.quantize(_Q4),
        "cantidad_sugerida": cantidad_sugerida.quantize(_Q4),
    }


def evaluar_reabastecimiento(empresa, *, almacen=None, incluir_ok: bool = False) -> list[dict[str, Any]]:
    """Evalúa las reglas activas de reabastecimiento de ``empresa`` contra ``StockActual``."""
    reglas_qs = (
        ReglaReabastecimiento.objects.filter(id_empresa=empresa, activo=True)
        .select_related("id_producto", "id_variante", "id_almacen", "id_proveedor_preferido", "id_almacen_origen")
        .order_by("id_producto__nombre_producto", "id_almacen__nombre_almacen", "pk")
    )
    if almacen is not None:
        reglas_qs = reglas_qs.filter(id_almacen=almacen)

    reglas = list(reglas_qs)
    if not reglas:
        return []

    stocks_qs = StockActual.objects.filter(id_empresa=empresa)
    if almacen is not None:
        stocks_qs = stocks_qs.filter(id_almacen=almacen)
    stock_map = {(s.id_producto_id, s.id_variante_id, s.id_almacen_id): s for s in stocks_qs}

    resultados: list[dict[str, Any]] = []
    for regla in reglas:
        stock = stock_map.get((regla.id_producto_id, regla.id_variante_id, regla.id_almacen_id))
        item = _evaluar_regla_con_stock(regla, stock)
        if not incluir_ok and not item["requiere_reabastecimiento"]:
            continue
        resultados.append(item)
    return resultados


def _generar_numero_requisicion_unico(empresa) -> str:
    from apps.compras.models import RequisicionCompra

    fecha_str = timezone.localdate().strftime("%Y%m%d")
    for _ in range(10):
        candidato = f"REQ-RB-{fecha_str}-{uuid.uuid4().hex[:6].upper()}"
        if not RequisicionCompra.objects.filter(id_empresa=empresa, numero_requisicion=candidato).exists():
            return candidato
    raise ReabastecimientoError("No se pudo generar un número único de requisición.")


def _crear_operacion_transferencia_sin_pasos(
    *,
    empresa,
    almacen_origen,
    almacen_destino,
    producto,
    variante,
    cantidad: Decimal,
    motivo: str,
) -> OperacionInventario:
    """Crea una OperacionInventario EN_PROCESO cuando el almacén origen no usa stepper."""
    base_count = OperacionInventario.objects.filter(id_empresa=empresa, tipo_operacion="ENTREGA").count() + 1
    operacion = None
    for intento in range(10):
        numero = f"ENT-{base_count + intento:06d}" if intento < 5 else f"ENT-{uuid.uuid4().hex[:8].upper()}"
        try:
            with transaction.atomic():
                operacion = OperacionInventario.objects.create(
                    id_empresa=empresa,
                    numero=numero,
                    tipo_operacion="ENTREGA",
                    origen_tipo="TRANSFER",
                    id_almacen=almacen_origen,
                    id_almacen_contraparte=almacen_destino,
                    estado="EN_PROCESO",
                    motivo=motivo,
                    fecha=timezone.now(),
                )
            break
        except IntegrityError:
            if intento == 9:
                raise
            continue

    assert operacion is not None  # noqa: S101 — garantizado por el loop
    OperacionInventarioLinea.objects.create(
        id_operacion=operacion,
        id_producto=producto,
        id_variante=variante,
        cantidad=cantidad,
    )
    return operacion


@transaction.atomic
def generar_borrador_reabastecimiento(
    regla: ReglaReabastecimiento,
    *,
    usuario,
    cantidad=None,
    fecha_necesidad=None,
) -> dict[str, Any]:
    """Genera un borrador de RequisicionCompra, OrdenProduccion o Transferencia según ``regla.ruta``."""
    if usuario is None:
        raise ReabastecimientoError("El usuario solicitante es obligatorio.")

    regla_locked = (
        ReglaReabastecimiento.objects.select_for_update(of=("self",))
        .select_related(
            "id_empresa", "id_producto", "id_variante", "id_almacen", "id_proveedor_preferido", "id_almacen_origen"
        )
        .get(pk=regla.pk)
    )
    if not regla_locked.activo:
        raise ReabastecimientoError("La regla de reabastecimiento está inactiva.")

    empresa = regla_locked.id_empresa
    producto = regla_locked.id_producto
    almacen = regla_locked.id_almacen

    fecha_nec_parsed = _parse_fecha(fecha_necesidad)
    hoy = timezone.localdate()

    if cantidad is None:
        stock = StockActual.objects.filter(
            id_empresa=empresa,
            id_producto=producto,
            id_variante=regla_locked.id_variante,
            id_almacen=almacen,
        ).first()
        eval_item = _evaluar_regla_con_stock(regla_locked, stock)
        cantidad_dec = eval_item["cantidad_sugerida"]
        if cantidad_dec <= _CERO:
            raise ReabastecimientoError("La regla no presenta déficit de stock para generar un borrador.")
    else:
        cantidad_dec = _parse_decimal(cantidad, "cantidad").quantize(_Q4)
        if cantidad_dec <= _CERO:
            raise ReabastecimientoError("La cantidad debe ser mayor a cero.")

    if regla_locked.ruta == "COMPRA":
        from apps.compras.models import DetalleRequisicionCompra, RequisicionCompra

        if not producto.es_comprable:
            raise ReabastecimientoError("El producto no está habilitado para compras (es_comprable=False).")

        numero_req = _generar_numero_requisicion_unico(empresa)
        req = RequisicionCompra.objects.create(
            id_empresa=empresa,
            numero_requisicion=numero_req,
            fecha_requisicion=hoy,
            fecha_necesidad=fecha_nec_parsed or hoy,
            id_solicitante=usuario,
            estado="BORRADOR",
            justificacion=(
                f"Reabastecimiento automático regla {regla_locked.id_regla}: "
                f"{producto.nombre_producto} en {almacen.nombre_almacen}"
            ),
        )
        DetalleRequisicionCompra.objects.create(
            id_requisicion=req,
            id_producto=producto,
            cantidad_solicitada=cantidad_dec,
            precio_estimado=producto.costo_promedio or None,
        )
        return {
            "ruta": "COMPRA",
            "tipo_documento": "RequisicionCompra",
            "id_documento": str(req.id_requisicion),
            "numero": req.numero_requisicion,
            "estado": req.estado,
            "cantidad": str(cantidad_dec),
        }

    if regla_locked.ruta == "MANUFACTURA":
        from apps.manufactura.models import ListaMateriales, OrdenProduccion

        cantidad_op = cantidad_dec.quantize(_Q2)
        if cantidad_op <= _CERO:
            raise ReabastecimientoError("La cantidad redondeada para OrdenProduccion debe ser mayor a cero.")

        bom = ListaMateriales.objects.filter(empresa=empresa, producto_final=producto).order_by("pk").first()
        op = OrdenProduccion.objects.create(
            empresa=empresa,
            producto=producto,
            cantidad=cantidad_op,
            fecha_inicio=hoy,
            fecha_fin=fecha_nec_parsed,
            estado="pendiente",
            lista_materiales=bom,
            observaciones=(f"Reabastecimiento automático regla {regla_locked.id_regla} ({almacen.nombre_almacen})"),
        )
        return {
            "ruta": "MANUFACTURA",
            "tipo_documento": "OrdenProduccion",
            "id_documento": str(op.id),
            "numero": f"OP-{str(op.id)[:8].upper()}",
            "estado": op.estado,
            "cantidad": str(op.cantidad),
            "lista_materiales_id": str(bom.id) if bom is not None else None,
        }

    if regla_locked.ruta == "TRANSFERENCIA":
        from .operaciones import OperacionError, crear_operacion

        origen = regla_locked.id_almacen_origen
        if origen is None:
            raise ReabastecimientoError("La regla de ruta TRANSFERENCIA requiere id_almacen_origen.")
        if str(origen.id_empresa_id) != str(empresa.pk):
            raise ReabastecimientoError("El almacén origen no pertenece a la empresa de la regla.")
        if origen.pk == almacen.pk:
            raise ReabastecimientoError("El almacén origen y el almacén destino deben ser distintos.")

        motivo = (
            f"Reabastecimiento automático regla {regla_locked.id_regla}: "
            f"{producto.nombre_producto} hacia {almacen.nombre_almacen}"
        )
        tiene_pasos = PasoOperacion.objects.filter(
            id_empresa=empresa,
            id_almacen=origen,
            tipo_operacion="ENTREGA",
            activo=True,
        ).exists()

        if tiene_pasos:
            try:
                op_inv = crear_operacion(
                    empresa=empresa,
                    almacen=origen,
                    tipo_operacion="ENTREGA",
                    origen_tipo="TRANSFER",
                    almacen_contraparte=almacen,
                    lineas=[
                        {
                            "producto": producto,
                            "variante": regla_locked.id_variante,
                            "cantidad": cantidad_dec,
                        }
                    ],
                    usuario=usuario,
                    motivo=motivo,
                )
            except OperacionError as exc:
                raise ReabastecimientoError(str(exc)) from exc
        else:
            op_inv = _crear_operacion_transferencia_sin_pasos(
                empresa=empresa,
                almacen_origen=origen,
                almacen_destino=almacen,
                producto=producto,
                variante=regla_locked.id_variante,
                cantidad=cantidad_dec,
                motivo=motivo,
            )

        return {
            "ruta": "TRANSFERENCIA",
            "tipo_documento": "OperacionInventario",
            "id_documento": str(op_inv.id_operacion),
            "numero": op_inv.numero,
            "estado": op_inv.estado,
            "cantidad": str(cantidad_dec),
        }

    raise ReabastecimientoError(f"Ruta de reabastecimiento no soportada: {regla_locked.ruta!r}.")
