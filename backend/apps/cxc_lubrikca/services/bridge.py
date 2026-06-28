"""Bridge Django→motor (Fase 3).

Construye las dataclasses puras del motor determinístico a partir de las filas
Django (espejo + config) y persiste la salida del motor en
``BandejaFacturacion``. El motor NO conoce Django; este módulo es el único
acoplamiento.
"""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.cxc_lubrikca.models import (
    BandejaFacturacion,
    DescuentoBCVCompleto,
    DescuentoMarcaCategoria,
    Feriado,
    MetodoPago,
    PromocionPrimeraCompra,
    ReglaRecurrencia,
)
from apps.cxc_lubrikca.services.motor import config as motor_config
from apps.cxc_lubrikca.services.motor import models as M
from apps.cxc_lubrikca.services.motor.discounts import EngineInputs, calcular_factura
from apps.cxc_lubrikca.services.price_resolver_db import DBPriceResolver

# Mapeo de listas por defecto (ODOO_MAPEO): lista "4" = USD, "5" = BCV.
# Overridable por la config del tenant en el futuro; constantes por ahora.
LISTA_USD_DEFAULT = "4"
LISTA_BCV_DEFAULT = "5"


class BridgeError(Exception):
    """Error de datos al construir/recalcular la bandeja (p. ej. falta un precio)."""


def _engine_config(empresa) -> motor_config.EngineConfig:
    """Config del motor para el tenant. Por ahora usa los defaults del motor
    pero con ``lista_usd`` / ``lista_bcv`` del mapeo ODOO (overridable)."""
    base = motor_config.default_engine_config()
    return motor_config.EngineConfig(
        cash_window_business_days=base.cash_window_business_days,
        bcv_complete_formula=base.bcv_complete_formula,
        lista_usd=LISTA_USD_DEFAULT,
        lista_bcv=LISTA_BCV_DEFAULT,
    )


def _orden_dc(pedido) -> M.OrdenVenta:
    return M.OrdenVenta(
        so_id=pedido.so_id,
        cliente_id=pedido.cliente_externo_id,
        fecha=pedido.fecha,
        fecha_entrega=pedido.fecha_entrega,
        monto_total=pedido.monto_total,
        lista_precios=pedido.lista_precios,
        vendedor_email=pedido.vendedor_email,
        es_primera_compra=pedido.es_primera_compra,
        facturada=pedido.facturada,
        factura_id=pedido.factura_id or None,
        monto_facturado=pedido.monto_facturado,
        estado_entrega=pedido.estado_entrega or "",
        entregada_completa=pedido.entregada_completa,
        tiene_devolucion=pedido.tiene_devolucion,
    )


def _linea_dc(linea, so_id: str) -> M.LineaOrden:
    return M.LineaOrden(
        linea_id=linea.linea_id,
        so_id=so_id,
        producto=linea.producto,
        marca=linea.marca,
        categoria=linea.categoria,
        cantidad=linea.cantidad,
        precio_unitario=linea.precio_unitario,
        cantidad_entregada=linea.cantidad_entregada,
    )


def _metodo_dc(metodo: MetodoPago | None, codigo: str, moneda: str) -> M.MetodoPago:
    """Dataclass del método de pago. Si no hay fila de config para el código,
    se usa un método neutro (N_A) con la moneda del abono."""
    if metodo is None:
        return M.MetodoPago(
            metodo_id=codigo,
            nombre=codigo,
            moneda=M.Moneda(moneda),
            tipo_tasa=M.TipoTasa.N_A,
            es_contado=False,
        )
    return M.MetodoPago(
        metodo_id=metodo.codigo,
        nombre=metodo.nombre,
        moneda=M.Moneda(metodo.moneda),
        tipo_tasa=M.TipoTasa(metodo.tipo_tasa),
        es_contado=metodo.es_contado,
    )


def _vinculacion_dc(vinc) -> M.Vinculacion:
    return M.Vinculacion(
        vinc_id=str(vinc.id),
        pago_id=str(vinc.pago_id),
        so_id=str(vinc.pedido_id),
        monto_aplicado=vinc.monto_aplicado,
        hora_pago_confirmada=vinc.hora_pago_confirmada,
        tasa_bcv_aplicada=vinc.tasa_bcv_aplicada,
        tasa_binance_aplicada=vinc.tasa_binance_aplicada,
        es_tasa_heredada=vinc.es_tasa_heredada,
        equiv_usd_bcv=vinc.equiv_usd_bcv,
        equiv_usd_binance=vinc.equiv_usd_binance,
        equiv_ves_bcv=vinc.equiv_ves_bcv,
        equiv_ves_binance=vinc.equiv_ves_binance,
        confirmado_por=str(vinc.confirmado_por_id) if vinc.confirmado_por_id else "",
        moneda_abono=M.Moneda(vinc.moneda_abono),
        tipo_tasa_abono=M.TipoTasa(vinc.tipo_tasa_abono),
    )


def _descuento_dc(row) -> M.DescuentoMarcaCategoria:
    return M.DescuentoMarcaCategoria(
        regla_id=str(row.id),
        marca=row.marca,
        categoria=row.categoria,
        tipo_descuento=M.TipoDescuento(row.tipo_descuento),
        porcentaje=row.porcentaje,
        vigencia_desde=row.vigencia_desde,
        vigencia_hasta=row.vigencia_hasta,
        activo=row.activo,
    )


def _regla_recurrencia_dc(row) -> M.ReglaRecurrencia:
    return M.ReglaRecurrencia(
        condicion=M.Condicion(row.condicion),
        tipo_beneficio=M.TipoBeneficio(row.tipo_beneficio),
        valor=row.valor,
        vigencia_desde=row.vigencia_desde,
        vigencia_hasta=row.vigencia_hasta,
        activo=row.activo,
    )


def _bcv_completo_dc(row) -> M.DescuentoBCVCompleto:
    return M.DescuentoBCVCompleto(
        vigencia_desde=row.vigencia_desde,
        porcentaje=row.porcentaje,
        vigencia_hasta=row.vigencia_hasta,
        activo=row.activo,
    )


def _promo_dc(row) -> M.PromocionPrimeraCompra:
    return M.PromocionPrimeraCompra(
        producto=row.producto,
        vigencia_desde=row.vigencia_desde,
        vigencia_hasta=row.vigencia_hasta,
        activo=row.activo,
    )


def _feriado_dc(row) -> M.Feriado:
    return M.Feriado(
        fecha=row.fecha,
        descripcion=row.descripcion,
        tipo=M.TipoFeriado(row.tipo),
    )


def construir_engine_inputs(pedido, *, fecha_calculo: date) -> EngineInputs:
    """Arma ``EngineInputs`` desde las filas Django del tenant del pedido."""
    empresa = pedido.empresa

    lineas = list(pedido.lineas.filter(deleted_at__isnull=True))

    # Métodos de pago del tenant indexados por código (para resolver tipo_tasa).
    metodos_by_codigo = {
        m.codigo: m
        for m in MetodoPago.objects.filter(empresa=empresa, deleted_at__isnull=True)
    }

    abonos: list[tuple[M.Vinculacion, M.MetodoPago]] = []
    for vinc in pedido.vinculaciones.filter(deleted_at__isnull=True).select_related(
        "pago"
    ):
        metodo = metodos_by_codigo.get(vinc.pago.metodo_pago)
        abonos.append(
            (
                _vinculacion_dc(vinc),
                _metodo_dc(metodo, vinc.pago.metodo_pago, vinc.pago.moneda),
            )
        )

    descuentos = [
        _descuento_dc(r)
        for r in DescuentoMarcaCategoria.objects.filter(
            empresa=empresa, deleted_at__isnull=True
        )
    ]
    reglas_recurrencia = [
        _regla_recurrencia_dc(r)
        for r in ReglaRecurrencia.objects.filter(
            empresa=empresa, deleted_at__isnull=True
        )
    ]
    descuento_bcv_diario = [
        _bcv_completo_dc(r)
        for r in DescuentoBCVCompleto.objects.filter(
            empresa=empresa, deleted_at__isnull=True
        )
    ]
    promociones = [
        _promo_dc(r)
        for r in PromocionPrimeraCompra.objects.filter(
            empresa=empresa, deleted_at__isnull=True
        )
    ]
    feriados = [
        _feriado_dc(r)
        for r in Feriado.objects.filter(empresa=empresa, deleted_at__isnull=True)
    ]

    return EngineInputs(
        orden=_orden_dc(pedido),
        lineas=[_linea_dc(ln, pedido.so_id) for ln in lineas],
        abonos=abonos,
        descuentos=descuentos,
        reglas_recurrencia=reglas_recurrencia,
        descuento_bcv_diario=descuento_bcv_diario,
        promociones_primera_compra=promociones,
        feriados_tabla=feriados,
        price_resolver=DBPriceResolver(empresa),
        engine_config=_engine_config(empresa),
        fecha_calculo=fecha_calculo,
    )


@transaction.atomic
def recalcular_bandeja(pedido) -> BandejaFacturacion:
    """Recalcula y persiste la ``BandejaFacturacion`` del pedido (upsert)."""
    fecha_calculo = timezone.localdate()
    try:
        resultado = calcular_factura(
            construir_engine_inputs(pedido, fecha_calculo=fecha_calculo)
        )
    except KeyError as exc:
        # El price resolver lanza KeyError("Sin precio para producto=... lista=...")
        # cuando falta una fila PrecioListaLubrikca. Lo convertimos en un error de
        # dominio para que la API devuelva 400 en vez de un 500 sin contexto.
        raise BridgeError(
            f"Falta un precio para calcular la bandeja ({exc}); cargue "
            "PrecioListaLubrikca o sincronice Odoo (Fase 5)."
        ) from exc

    detalle = [
        {"origen": d.origen, "descripcion": d.descripcion, "monto": str(d.monto)}
        for d in resultado.descuentos_detalle
    ]

    bandeja, _ = BandejaFacturacion.objects.update_or_create(
        pedido=pedido,
        defaults={
            "empresa": pedido.empresa,
            "lista_aplicada": resultado.lista_aplicada,
            "precio_base_calculado": resultado.precio_base_calculado,
            "descuentos_detalle": detalle,
            "total_descuentos": resultado.total_descuentos,
            "ncs_calculadas": resultado.ncs_calculadas,
            "total_motor": resultado.total_motor,
            "requiere_revision": resultado.requiere_revision,
            "candidata_a_cierre": resultado.candidata_a_cierre,
        },
    )
    return bandeja
