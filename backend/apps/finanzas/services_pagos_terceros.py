"""
Servicios de Pagos de Terceros (Zelle) — Capa B, tropicalización VE (§6.6).

Un cobro en USD entra por la cuenta Zelle de un PROVEEDOR (tercero). Acciones:

  abonar_pago_tercero()   — pendiente → abonado: reduce la CxP del proveedor
                            (reusa ``registrar_abono_cxp`` de cuentas_por_pagar)
                            + asiento PAGO_TERCERO.
  solicitar_reintegro()   — pendiente → reintegro_pendiente: crea una
                            CuentaPorCobrar contra el proveedor por
                            monto − comisión + asiento PAGO_TERCERO.
  asociar_proveedor()     — fija el proveedor de un cobro originado en caja
                            (solo en estado pendiente).
  marcar_reintegrado()    — reintegro_pendiente → reintegrado (confirmación
                            manual de que el proveedor devolvió el dinero).
  anular_pago_tercero()   — pendiente → anulado (sin efectos que revertir).

R-CODE-11: cada acción corre en UNA transacción atómica; el asiento contable
se genera dentro de la misma transacción vía ``generar_asiento_o_fallar``:
con ``empresa.contabilidad_activa`` y sin MapeoContable PAGO_TERCERO se lanza
``AsientoError`` (la vista lo traduce a 422) y TODO se revierte; con
contabilidad inactiva la operación procede sin asiento (best-effort, R-PROD-3).

Puente proveedor→CxC (decisión de diseño): ``CuentaPorCobrar.cliente`` es
OPCIONAL (ADR-009 / patrón ``cliente_externo_id``); el reintegro identifica al
deudor con ``cliente_externo_id = "proveedor:<uuid>"`` y denormaliza la razón
social en ``cliente_externo_nombre`` — NO se crea un ``crm.Cliente`` espejo.
Las transiciones inválidas lanzan ``PagoTerceroError`` (la vista responde 400).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:  # solo para anotaciones (evita imports circulares en runtime)
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    from apps.cuentas_por_pagar.models import AbonoCxP

    from .models import PagoTercero

TIPO_ASIENTO_PAGO_TERCERO = "PAGO_TERCERO"

#: Prefijo del identificador externo del deudor en la CxC de reintegro (ADR-009).
PREFIJO_DEUDOR_PROVEEDOR = "proveedor:"

#: Tope del campo CuentaPorCobrar.monto (max_digits=12, decimal_places=2).
_MAX_MONTO_CXC = Decimal("9999999999.99")

_DOS_DECIMALES = Decimal("0.01")

#: Días de plazo por defecto para el vencimiento de la CxC de reintegro.
PLAZO_REINTEGRO_DIAS = 30


class PagoTerceroError(Exception):
    """Error de negocio (transición inválida, datos inconsistentes) → 400."""


def _lock(pago: "PagoTercero") -> "PagoTercero":
    """Relee el pago con ``select_for_update`` dentro de la transacción."""
    from .models import PagoTercero

    return PagoTercero.objects.select_for_update().get(pk=pago.pk)


def _exigir_estado(pago: "PagoTercero", esperado: str, accion: str) -> None:
    if pago.estado != esperado:
        raise PagoTerceroError(
            f"No se puede {accion} un pago de tercero en estado '{pago.estado}' "
            f"(se requiere '{esperado}')."
        )


def _exigir_proveedor(pago: "PagoTercero", accion: str) -> None:
    if not pago.id_proveedor_id:
        raise PagoTerceroError(
            f"No se puede {accion} sin proveedor asociado. "
            "Use la acción 'asociar-proveedor' primero."
        )


@transaction.atomic
# Supuesto de monedas: la CxP no lleva moneda propia (la hereda de su factura
# origen); el abono se registra en la moneda del pago tercero (USD típico).
def abonar_pago_tercero(pago: "PagoTercero", cxp, usuario, descripcion: str = "") -> "AbonoCxP":
    """
    pendiente → abonado: el cobro que entró por la cuenta del proveedor se
    aplica como pago USD a una CxP de ESE proveedor (reduce su saldo) y genera
    el asiento PAGO_TERCERO por el monto del cobro — todo o nada.

    Args:
        pago:        PagoTercero en estado ``pendiente`` con proveedor asociado.
        cxp:         CuentaPorPagar del MISMO proveedor y la MISMA empresa.
        usuario:     usuario que ejecuta la acción (queda en el AbonoCxP).
        descripcion: texto opcional para el AbonoCxP.

    Returns:
        El AbonoCxP creado (vía ``registrar_abono_cxp``, que valida saldo/estado).

    Raises:
        PagoTerceroError: transición inválida, proveedor faltante o CxP ajena.
        AsientoError:     contabilidad activa sin mapeo PAGO_TERCERO (→ 422).
    """
    from apps.contabilidad.services import generar_asiento_o_fallar
    from apps.cuentas_por_pagar.services import AbonoCxPError, registrar_abono_cxp

    pago = _lock(pago)
    _exigir_estado(pago, "pendiente", "abonar")
    _exigir_proveedor(pago, "abonar")

    # Defensa en profundidad (la vista ya acota por tenant): la CxP debe ser de
    # la misma empresa y del mismo proveedor por cuya cuenta entró el cobro.
    if str(cxp.id_empresa_id) != str(pago.id_empresa_id):
        raise PagoTerceroError("La CxP no pertenece a la empresa del pago de tercero.")
    if str(cxp.id_proveedor_id) != str(pago.id_proveedor_id):
        raise PagoTerceroError(
            "La CxP no pertenece al proveedor asociado al pago de tercero."
        )

    try:
        abono = registrar_abono_cxp(
            cxp=cxp,
            monto=pago.monto,
            usuario=usuario,
            descripcion=descripcion
            or f"Pago de tercero Zelle {pago.referencia_zelle}",
            # El pago de tercero lleva su PROPIO asiento PAGO_TERCERO (más abajo);
            # no debe generar también PAGO_CXP o se duplicaría el cargo a la CxP
            # y un AbonoCxPError por falta de mapeo PAGO_CXP taparía el 422 real.
            generar_asiento=False,
        )
    except AbonoCxPError as exc:
        raise PagoTerceroError(str(exc)) from exc

    pago.estado = "abonado"
    pago.id_abono_cxp = abono
    pago.save(update_fields=["estado", "id_abono_cxp", "fecha_actualizacion"])

    # R-CODE-11: asiento en la MISMA transacción; si falla con contabilidad
    # activa, el abono y el cambio de estado se revierten completos.
    generar_asiento_o_fallar(
        TIPO_ASIENTO_PAGO_TERCERO, pago, pago.id_empresa, monto=pago.monto, usuario=usuario
    )
    return abono


@transaction.atomic
def solicitar_reintegro(
    pago: "PagoTercero",
    usuario=None,
    comision: Decimal | None = None,
    fecha_vencimiento=None,
    descripcion: str = "",
) -> "CuentaPorCobrar":
    """
    pendiente → reintegro_pendiente: el proveedor debe devolver el dinero, así
    que se emite una CuentaPorCobrar CONTRA el proveedor por
    ``monto − comisión`` (la comisión es lo que el tercero cobra por el favor)
    y se genera el asiento PAGO_TERCERO por el neto — todo o nada.

    El deudor de la CxC se identifica con el patrón ADR-009
    (``cliente_externo_id = "proveedor:<uuid>"``), sin crear un crm.Cliente.

    Raises:
        PagoTerceroError: transición inválida, proveedor faltante o comisión
                          inválida (negativa o ≥ monto).
        AsientoError:     contabilidad activa sin mapeo PAGO_TERCERO (→ 422).
    """
    from apps.contabilidad.services import generar_asiento_o_fallar
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar

    pago = _lock(pago)
    _exigir_estado(pago, "pendiente", "solicitar reintegro de")
    _exigir_proveedor(pago, "solicitar reintegro")

    if comision is None:
        comision_norm = Decimal("0.00")
    else:
        try:
            comision_norm = Decimal(str(comision)).quantize(_DOS_DECIMALES)
        except (InvalidOperation, ValueError) as exc:
            raise PagoTerceroError(f"Comisión inválida: {comision!r}.") from exc
    if comision_norm < 0:
        raise PagoTerceroError("La comisión no puede ser negativa.")
    if comision_norm >= pago.monto:
        raise PagoTerceroError(
            f"La comisión ({comision_norm}) debe ser menor que el monto del cobro ({pago.monto})."
        )

    monto_neto = (pago.monto - comision_norm).quantize(_DOS_DECIMALES)
    if monto_neto > _MAX_MONTO_CXC:
        raise PagoTerceroError(
            f"El monto del reintegro ({monto_neto}) excede el máximo soportado por CxC."
        )

    # localdate() = hoy en TIME_ZONE (America/Caracas), no en UTC: con
    # now().date() la fecha de emisión/vencimiento de la CxC de reintegro se
    # adelantaba un día tras las 20:00 Caracas (= 00:00 UTC).
    hoy = timezone.localdate()
    proveedor = pago.id_proveedor
    assert proveedor is not None  # noqa: S101 — _exigir_proveedor ya lo garantizó
    cxc = CuentaPorCobrar.objects.create(
        empresa=pago.id_empresa,
        cliente=None,
        cliente_externo_id=f"{PREFIJO_DEUDOR_PROVEEDOR}{pago.id_proveedor_id}",
        cliente_externo_nombre=proveedor.razon_social,
        monto=monto_neto,
        fecha_emision=hoy,
        fecha_vencimiento=fecha_vencimiento or (hoy + timedelta(days=PLAZO_REINTEGRO_DIAS)),
        estado="pendiente",
        tipo_operacion="REINTEGRO_PAGO_TERCERO",
        descripcion=(
            descripcion
            or f"Reintegro de pago de tercero Zelle {pago.referencia_zelle} "
            f"(cobro {pago.monto}, comisión {comision_norm})"
        ),
        documento_json={
            "origen": "pago_tercero",
            "id_pago_tercero": str(pago.pk),
            "monto_cobro": str(pago.monto),
            "comision": str(comision_norm),
            "solicitado_por": str(usuario.pk) if usuario is not None else None,
        },
    )

    pago.comision = comision_norm
    pago.estado = "reintegro_pendiente"
    pago.id_cxc_reintegro = cxc
    pago.save(update_fields=["comision", "estado", "id_cxc_reintegro", "fecha_actualizacion"])

    # R-CODE-11: asiento por el neto del reintegro, en la MISMA transacción.
    generar_asiento_o_fallar(
        TIPO_ASIENTO_PAGO_TERCERO, pago, pago.id_empresa, monto=monto_neto, usuario=usuario
    )
    return cxc


@transaction.atomic
def asociar_proveedor(pago: "PagoTercero", proveedor) -> "PagoTercero":
    """
    Asocia (o re-asocia) el proveedor a un cobro originado en caja. Solo es
    válido mientras el pago sigue ``pendiente`` (después, el proveedor ya
    participó en documentos financieros y no debe cambiar).

    Raises:
        PagoTerceroError: estado distinto de pendiente o proveedor de otra empresa.
    """
    pago = _lock(pago)
    _exigir_estado(pago, "pendiente", "asociar proveedor a")

    if str(proveedor.id_empresa_id) != str(pago.id_empresa_id):
        raise PagoTerceroError("El proveedor no pertenece a la empresa del pago de tercero.")

    pago.id_proveedor = proveedor
    pago.save(update_fields=["id_proveedor", "fecha_actualizacion"])
    return pago


@transaction.atomic
def marcar_reintegrado(pago: "PagoTercero") -> "PagoTercero":
    """
    reintegro_pendiente → reintegrado: confirmación manual de que el proveedor
    devolvió el dinero. No toca la CxC del reintegro — su saldo lo gobierna el
    flujo normal de cobranza (AbonoCxC), que es quien la marca pagada.

    Raises:
        PagoTerceroError: si el pago no está en ``reintegro_pendiente``.
    """
    pago = _lock(pago)
    _exigir_estado(pago, "reintegro_pendiente", "marcar reintegrado")

    pago.estado = "reintegrado"
    pago.save(update_fields=["estado", "fecha_actualizacion"])
    return pago


@transaction.atomic
def anular_pago_tercero(pago: "PagoTercero") -> "PagoTercero":
    """
    pendiente → anulado. Solo se anula un pago sin efectos financieros (los
    estados abonado/reintegro_pendiente ya movieron CxP/CxC y exigirían una
    reversión contable que está fuera del alcance de esta acción).

    Raises:
        PagoTerceroError: si el pago no está ``pendiente``.
    """
    pago = _lock(pago)
    _exigir_estado(pago, "pendiente", "anular")

    pago.estado = "anulado"
    pago.save(update_fields=["estado", "fecha_actualizacion"])
    return pago
