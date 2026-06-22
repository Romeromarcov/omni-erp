"""
Servicios de pagos de contribuciones parafiscales — Capa B §6.7 (plan §6.3).

Las contribuciones parafiscales (IVSS, FAOV/BANAVIH, INCES, RPE/paro forzoso…)
que la nómina calcula como aportes patronales se declaran por período mensual
(``PagoContribucionParafiscal`` en estado ``pendiente``) y se pagan con:

  pagar_contribucion_parafiscal()  — pendiente → pagado: crea el ``finanzas.Pago``
                                     genérico (EGRESO, tipo IMPUESTO) y reusa
                                     ``registrar_efectos_pago`` (Transacción +
                                     MovimientoCajaBanco de egreso + saldo con
                                     ``select_for_update``) + asiento
                                     PAGO_PARAFISCAL — todo o nada.
  anular_pago_parafiscal()         — pendiente → anulado (sin efectos que
                                     revertir); libera el período para
                                     re-declarar (constraint condicional).

R-CODE-11: cada acción corre en UNA transacción atómica; el asiento contable se
genera dentro de la misma transacción vía ``generar_asiento_o_fallar``: con
``empresa.contabilidad_activa`` y sin MapeoContable PAGO_PARAFISCAL se lanza
``AsientoError`` (la vista lo traduce a 422) y TODO se revierte (ni Pago, ni
movimiento de caja, ni cambio de estado); con contabilidad inactiva la
operación procede sin asiento (best-effort, R-PROD-3).

No-doble-pago: la BD solo admite UNA fila no anulada por (empresa, contribución,
período) — ``uniq_pago_parafiscal_periodo_no_anulado`` — y el estado ``pagado``
es terminal: pagar dos veces el mismo período+contribución es imposible.

Las transiciones inválidas lanzan ``PagoParafiscalError`` (la vista responde 400).
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:  # solo para anotaciones (evita imports circulares en runtime)
    from apps.finanzas.models import Pago

    from .models import PagoContribucionParafiscal

TIPO_ASIENTO_PAGO_PARAFISCAL = "PAGO_PARAFISCAL"


class PagoParafiscalError(Exception):
    """Error de negocio (transición inválida, datos inconsistentes) → 400."""


def _lock(pago: "PagoContribucionParafiscal") -> "PagoContribucionParafiscal":
    """Relee el pago con ``select_for_update`` dentro de la transacción."""
    from .models import PagoContribucionParafiscal

    return PagoContribucionParafiscal.objects.select_for_update().get(pk=pago.pk)


def _exigir_estado(pago: "PagoContribucionParafiscal", esperado: str, accion: str) -> None:
    if pago.estado != esperado:
        raise PagoParafiscalError(
            f"No se puede {accion} un pago parafiscal en estado '{pago.estado}' "
            f"(se requiere '{esperado}')."
        )


def _validar_contenedor(pago, caja_virtual, cuenta_bancaria) -> None:
    """Exactamente UN contenedor de fondos, del mismo tenant y la misma moneda."""
    if (caja_virtual is None) == (cuenta_bancaria is None):
        raise PagoParafiscalError(
            "Indique exactamente un origen de fondos: 'caja' (virtual) o "
            "'cuenta_bancaria' — el pago genera un egreso en el libro de caja."
        )
    if caja_virtual is not None:
        if str(caja_virtual.empresa_id) != str(pago.id_empresa_id):
            raise PagoParafiscalError("La caja no pertenece a la empresa del pago parafiscal.")
        if not caja_virtual.activa:
            raise PagoParafiscalError("La caja indicada está inactiva.")
        if str(caja_virtual.moneda_id) != str(pago.id_moneda_id):
            raise PagoParafiscalError(
                "La moneda de la caja no coincide con la moneda del pago parafiscal "
                "(no se mezclan monedas, R-CODE-4)."
            )
    if cuenta_bancaria is not None:
        if str(cuenta_bancaria.id_empresa_id) != str(pago.id_empresa_id):
            raise PagoParafiscalError(
                "La cuenta bancaria no pertenece a la empresa del pago parafiscal."
            )
        if not cuenta_bancaria.activo:
            raise PagoParafiscalError("La cuenta bancaria indicada está inactiva.")
        if str(cuenta_bancaria.id_moneda_id) != str(pago.id_moneda_id):
            raise PagoParafiscalError(
                "La moneda de la cuenta bancaria no coincide con la moneda del "
                "pago parafiscal (no se mezclan monedas, R-CODE-4)."
            )


def _validar_metodo_pago(pago, metodo_pago) -> None:
    """El método debe estar activo y ser de la empresa, genérico o público."""
    if not metodo_pago.activo:
        raise PagoParafiscalError("El método de pago indicado está inactivo.")
    es_global = metodo_pago.empresa_id is None or metodo_pago.es_generico or metodo_pago.es_publico
    if not es_global and str(metodo_pago.empresa_id) != str(pago.id_empresa_id):
        raise PagoParafiscalError("El método de pago no pertenece a la empresa del pago parafiscal.")


def _fecha_pago_datetime(fecha_pago) -> datetime:
    """
    Datetime TZ-aware para el ``finanzas.Pago``. Sin fecha explícita → ahora;
    con fecha (pago registrado a posteriori) → mediodía local de ese día
    (determinístico, sin ambigüedad de cambio de día).
    """
    if fecha_pago is None:
        return timezone.now()
    return timezone.make_aware(datetime.combine(fecha_pago, time(12, 0)))


@transaction.atomic
def pagar_contribucion_parafiscal(
    pago_parafiscal: "PagoContribucionParafiscal",
    usuario,
    metodo_pago,
    caja_virtual=None,
    cuenta_bancaria=None,
    referencia: str = "",
    fecha_pago=None,
) -> "Pago":
    """
    pendiente → pagado: ejecuta el pago de la contribución para el período.

    En la MISMA transacción (R-CODE-11):
      1. Bloquea el registro (``select_for_update``) y valida la transición.
      2. Crea el ``finanzas.Pago`` (EGRESO, tipo_documento=IMPUESTO, FK a la
         contribución) y llama ``registrar_efectos_pago``: Transacción
         financiera + MovimientoCajaBanco de EGRESO + actualización del saldo
         de la caja/cuenta con su propio ``select_for_update``.
      3. Marca el registro como ``pagado`` (referencia + fecha + FK al Pago).
      4. Genera el asiento PAGO_PARAFISCAL — si falla con contabilidad activa,
         TODO se revierte.

    Args:
        pago_parafiscal: registro en estado ``pendiente``.
        usuario:         usuario que ejecuta el pago (auditoría del Pago).
        metodo_pago:     ``finanzas.MetodoPago`` activo (propio, genérico o público).
        caja_virtual:    ``finanzas.Caja`` origen del egreso (o ``cuenta_bancaria``).
        cuenta_bancaria: ``finanzas.CuentaBancariaEmpresa`` origen del egreso.
        referencia:      referencia del pago (planilla/comprobante); opcional.
        fecha_pago:      date del pago; default hoy.

    Returns:
        El ``finanzas.Pago`` creado.

    Raises:
        PagoParafiscalError: transición inválida o datos inconsistentes (→ 400).
        AsientoError:        contabilidad activa sin mapeo PAGO_PARAFISCAL (→ 422).
    """
    from apps.contabilidad.services import generar_asiento_o_fallar
    from apps.finanzas.models import Pago
    from apps.finanzas.services import registrar_efectos_pago

    pago_parafiscal = _lock(pago_parafiscal)
    _exigir_estado(pago_parafiscal, "pendiente", "pagar")
    _validar_contenedor(pago_parafiscal, caja_virtual, cuenta_bancaria)
    _validar_metodo_pago(pago_parafiscal, metodo_pago)

    if pago_parafiscal.monto <= Decimal("0"):
        raise PagoParafiscalError("El monto del pago parafiscal debe ser mayor a cero.")

    referencia_final = (referencia or pago_parafiscal.referencia or "").strip()
    fecha_efectiva = fecha_pago or timezone.now().date()

    try:
        pago = Pago.objects.create(
            id_empresa=pago_parafiscal.id_empresa,
            tipo_operacion="EGRESO",
            tipo_documento="IMPUESTO",
            id_documento=pago_parafiscal.pk,
            id_contribucion=pago_parafiscal.contribucion,
            fecha_pago=_fecha_pago_datetime(fecha_pago),
            monto=pago_parafiscal.monto,
            id_moneda=pago_parafiscal.id_moneda,
            id_metodo_pago=metodo_pago,
            referencia=referencia_final or None,
            observaciones=(
                f"Pago parafiscal {pago_parafiscal.contribucion.codigo} "
                f"período {pago_parafiscal.periodo}"
            ),
            id_caja_virtual=caja_virtual,
            id_cuenta_bancaria=cuenta_bancaria,
            id_usuario_registro=usuario,
        )
    except ValueError as exc:
        # Pago._validar_documento: contribución inexistente/ajena (defensa en
        # profundidad; el serializer del registro ya la validó al crear).
        raise PagoParafiscalError(str(exc)) from exc

    # Egreso en el libro de caja (plan §6.3): transacción + movimiento + saldo,
    # con select_for_update sobre la caja/cuenta — en ESTA misma transacción.
    registrar_efectos_pago(pago)

    pago_parafiscal.estado = "pagado"
    pago_parafiscal.referencia = referencia_final
    pago_parafiscal.fecha_pago = fecha_efectiva
    pago_parafiscal.id_pago = pago
    pago_parafiscal.save(
        update_fields=["estado", "referencia", "fecha_pago", "id_pago", "fecha_actualizacion"]
    )

    # R-CODE-11: asiento en la MISMA transacción; si falla con contabilidad
    # activa, el Pago, el movimiento de caja y el cambio de estado se revierten.
    generar_asiento_o_fallar(
        TIPO_ASIENTO_PAGO_PARAFISCAL,
        pago_parafiscal,
        pago_parafiscal.id_empresa,
        monto=pago_parafiscal.monto,
        usuario=usuario,
    )
    return pago


@transaction.atomic
def anular_pago_parafiscal(pago_parafiscal: "PagoContribucionParafiscal") -> "PagoContribucionParafiscal":
    """
    pendiente → anulado. Solo se anula una declaración sin pagar (un pago
    ejecutado ya movió caja y contabilidad; su reversión es un ajuste contable
    explícito fuera del alcance de esta acción). Anular libera el período:
    la constraint condicional permite re-declarar el mismo período+contribución.

    Raises:
        PagoParafiscalError: si el registro no está ``pendiente``.
    """
    pago_parafiscal = _lock(pago_parafiscal)
    _exigir_estado(pago_parafiscal, "pendiente", "anular")

    pago_parafiscal.estado = "anulado"
    pago_parafiscal.save(update_fields=["estado", "fecha_actualizacion"])
    return pago_parafiscal
