"""Servicio de conciliación (Fase 4) — semáforo motor-vs-factura.

El motor dice lo que la factura DEBERÍA ser (``BandejaFacturacion.total_motor``);
Odoo dice lo que FUE (``PedidoLubrikca.monto_facturado`` − ``ncs_facturadas``).
Este servicio aplica el semáforo determinístico (``clasificar_diferencia``) y
persiste el resultado en ``ConciliacionLubrikca``. Write-back purista: nada se
escribe a Odoo.

Reglas inviolables:
- Dinero en ``Decimal`` (R-CODE-4), nunca float.
- Multi-tenant: la config y la conciliación cuelgan de ``empresa`` (R-CODE-1).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.cxc_lubrikca.models import (
    BandejaFacturacion,
    ConciliacionLubrikca,
    ConfiguracionConciliacion,
    EstadoBandeja,
    PedidoLubrikca,
    ResultadoConciliacion,
)
from apps.cxc_lubrikca.services.motor.config import ReconciliationConfig
from apps.cxc_lubrikca.services.motor.reconcile import clasificar_diferencia

#: Antigüedad (días) a partir de la cual un pedido no facturado se considera
#: "cartera atascada" (DSO simple).
DIAS_CARTERA_ATASCADA = 30


class ConciliacionError(Exception):
    """Error de negocio al conciliar (no se ha facturado, falta bandeja, …)."""


def _config_de(empresa) -> ReconciliationConfig:
    """Construye la ``ReconciliationConfig`` del motor desde la fila de la empresa.

    Usa get-or-create con defaults para que toda empresa tenga tolerancias sin
    pasos previos. La fila más reciente (``-created_at``) es la activa.
    """
    fila = (
        ConfiguracionConciliacion.objects.filter(
            empresa=empresa, deleted_at__isnull=True
        )
        .order_by("-created_at")
        .first()
    )
    if fila is None:
        fila = ConfiguracionConciliacion.objects.create(empresa=empresa)
    return ReconciliationConfig(
        tolerance_rounding=fila.tolerance_rounding,
        tolerance_red=fila.tolerance_red,
    )


@transaction.atomic
def conciliar_pedido(pedido: PedidoLubrikca) -> ConciliacionLubrikca:
    """Aplica el semáforo a un pedido facturado y persiste la conciliación."""
    if not pedido.facturada:
        raise ConciliacionError("el pedido no está facturado en Odoo")

    bandeja = (
        BandejaFacturacion.objects.filter(
            pedido=pedido, deleted_at__isnull=True
        )
        .order_by("-calculado_en")
        .first()
    )
    if bandeja is None:
        raise ConciliacionError("recalcule la bandeja primero")

    resultado = clasificar_diferencia(
        bandeja.total_motor,
        pedido.monto_facturado or Decimal("0"),
        pedido.ncs_facturadas,
        _config_de(pedido.empresa),
    )

    conciliacion, _ = ConciliacionLubrikca.objects.update_or_create(
        pedido=pedido,
        defaults={
            "empresa": pedido.empresa,
            "total_motor": resultado.total_motor,
            "monto_facturado": resultado.monto_odoo,
            "ncs": resultado.ncs_odoo,
            "diferencia": resultado.diferencia,
            "resultado": resultado.resultado.value,
        },
    )
    return conciliacion


def marcar_revisado(conciliacion: ConciliacionLubrikca, usuario) -> ConciliacionLubrikca:
    """Marca quién revisó la conciliación (típicamente un rojo/amarillo)."""
    conciliacion.revisado_por = usuario
    conciliacion.save(update_fields=["revisado_por", "updated_at"])
    return conciliacion


def resumen_cartera(empresa) -> dict:
    """Agregados de tablero de la cartera de una empresa.

    Devuelve conteos por semáforo, facturados vs sin conciliar, pedidos con
    devolución, y una métrica simple de cartera atascada (pedidos no facturados
    cuya entrega completa es vieja, y bandejas candidatas a cierre aún sin
    aprobar). Los ``Decimal`` se devuelven como ``str`` para serialización exacta.
    """
    pedidos = PedidoLubrikca.objects.filter(
        empresa=empresa, deleted_at__isnull=True
    )
    conciliaciones = ConciliacionLubrikca.objects.filter(
        empresa=empresa, deleted_at__isnull=True
    )

    por_resultado = {
        ResultadoConciliacion.VERDE.value: 0,
        ResultadoConciliacion.AMARILLO.value: 0,
        ResultadoConciliacion.ROJO.value: 0,
    }
    diferencia_total = Decimal("0")
    for c in conciliaciones:
        por_resultado[c.resultado] = por_resultado.get(c.resultado, 0) + 1
        diferencia_total += c.diferencia

    facturados = pedidos.filter(facturada=True).count()
    conciliados_ids = set(conciliaciones.values_list("pedido_id", flat=True))
    facturados_sin_conciliar = (
        pedidos.filter(facturada=True)
        .exclude(id__in=conciliados_ids)
        .count()
    )

    con_devolucion = pedidos.filter(tiene_devolucion=True).count()

    limite = timezone.now().date() - timedelta(days=DIAS_CARTERA_ATASCADA)
    cartera_atascada = pedidos.filter(
        facturada=False,
        fecha_entrega__isnull=False,
        fecha_entrega__lt=limite,
    ).count()

    bandejas_pendientes = BandejaFacturacion.objects.filter(
        empresa=empresa,
        deleted_at__isnull=True,
        candidata_a_cierre=True,
    ).exclude(estado=EstadoBandeja.APROBADO).count()

    return {
        "por_resultado": por_resultado,
        "total_conciliados": conciliaciones.count(),
        "total_facturados": facturados,
        "facturados_sin_conciliar": facturados_sin_conciliar,
        "pedidos_con_devolucion": con_devolucion,
        "cartera_atascada": cartera_atascada,
        "bandejas_candidatas_sin_aprobar": bandejas_pendientes,
        "diferencia_total": str(diferencia_total),
    }
