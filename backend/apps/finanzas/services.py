"""
Servicios de negocio para Finanzas.

obtener_tasa_cambio()      — busca la mejor tasa disponible entre dos monedas.
convertir_monto()          — convierte un monto usando la tasa vigente.
registrar_efectos_pago()   — side-effects financieros de un Pago (transacción,
                             movimiento de caja/banco y saldos) con atomic + lock.
realizar_cierre_caja()     — cierre con corte persistente (patrón PR #73) común
                             a Caja virtual y CajaFisica.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone


class TasaCambioError(Exception):
    pass


# Priority order for rate lookup (lowest index = highest priority)
_TIPO_TASA_PRIORIDAD = ["ESPECIAL_USUARIO", "FIJA", "PROMEDIO_MERCADO", "OFICIAL_BCV"]


def obtener_tasa_cambio(moneda_origen, moneda_destino, empresa=None, fecha=None):
    """
    Busca la tasa de cambio más adecuada entre dos monedas para una fecha.

    Prioridad de búsqueda:
    1. Tasa específica de la empresa (ESPECIAL_USUARIO > FIJA > PROMEDIO_MERCADO) para la fecha exacta.
    2. Tasa global OFICIAL_BCV (id_empresa=None) para la fecha exacta.
    3. Tasa más reciente disponible (empresa-específica o global) dentro de los últimos 30 días.

    Si moneda_origen == moneda_destino devuelve tasa 1.0.

    Args:
        moneda_origen:  Instancia Moneda o código ISO (str).
        moneda_destino: Instancia Moneda o código ISO (str).
        empresa:        Instancia Empresa o UUID; puede ser None para buscar solo tasas globales.
        fecha:          date — fecha de referencia; default hoy (timezone.localdate()).

    Returns:
        TasaCambio — instancia con la mejor tasa disponible.

    Raises:
        TasaCambioError si no se encuentra ninguna tasa.
    """
    from .models import Moneda, TasaCambio

    # Resolver monedas por ISO si se pasan como strings
    if isinstance(moneda_origen, str):
        try:
            moneda_origen = Moneda.objects.get(codigo_iso=moneda_origen)
        except Moneda.DoesNotExist:
            raise TasaCambioError(f"Moneda '{moneda_origen}' no encontrada.")
    if isinstance(moneda_destino, str):
        try:
            moneda_destino = Moneda.objects.get(codigo_iso=moneda_destino)
        except Moneda.DoesNotExist:
            raise TasaCambioError(f"Moneda '{moneda_destino}' no encontrada.")

    # Misma moneda — tasa identidad (usamos un stub no persistente)
    if moneda_origen.pk == moneda_destino.pk:
        tasa = TasaCambio(
            id_moneda_origen=moneda_origen,
            id_moneda_destino=moneda_destino,
            valor_tasa=Decimal("1.00000000"),
            fecha_tasa=timezone.localdate(),
            tipo_tasa="FIJA",
        )
        return tasa

    if fecha is None:
        # localdate() = hoy en TIME_ZONE (America/Caracas), no en UTC: con
        # now().date() la búsqueda de tasa tomaba la del día siguiente tras las
        # 20:00 Caracas (= 00:00 UTC) y podía no encontrar tasa para "hoy".
        fecha = timezone.localdate()

    base_qs = TasaCambio.objects.filter(
        id_moneda_origen=moneda_origen,
        id_moneda_destino=moneda_destino,
        fecha_tasa=fecha,
    )

    # 1. Tasa empresa-específica (fecha exacta)
    if empresa is not None:
        empresa_qs = base_qs.filter(id_empresa=empresa)
        for tipo in _TIPO_TASA_PRIORIDAD:
            tasa = empresa_qs.filter(tipo_tasa=tipo).order_by("-fecha_creacion").first()
            if tasa:
                return tasa

    # 2. Tasa global OFICIAL_BCV (fecha exacta)
    tasa = base_qs.filter(id_empresa=None, tipo_tasa="OFICIAL_BCV").order_by("-fecha_creacion").first()
    if tasa:
        return tasa

    # 3. Tasa más reciente disponible (últimos 30 días)
    from datetime import timedelta

    fecha_limite = fecha - timedelta(days=30)
    recientes_qs = TasaCambio.objects.filter(
        id_moneda_origen=moneda_origen,
        id_moneda_destino=moneda_destino,
        fecha_tasa__gte=fecha_limite,
        fecha_tasa__lte=fecha,
    ).order_by("-fecha_tasa", "-fecha_creacion")

    if empresa is not None:
        tasa = recientes_qs.filter(id_empresa=empresa).first()
        if tasa:
            return tasa

    tasa = recientes_qs.filter(id_empresa=None).first()
    if tasa:
        return tasa

    raise TasaCambioError(
        f"No hay tasa de cambio disponible entre {moneda_origen.codigo_iso} "
        f"y {moneda_destino.codigo_iso} para {fecha} (últimos 30 días)."
    )


def convertir_monto(monto: Decimal, moneda_origen, moneda_destino, empresa=None, fecha=None) -> Decimal:
    """
    Convierte un monto de moneda_origen a moneda_destino.

    Args:
        monto:          Monto a convertir (Decimal o numérico).
        moneda_origen:  Instancia Moneda o código ISO.
        moneda_destino: Instancia Moneda o código ISO.
        empresa:        Instancia Empresa o UUID; None para tasas globales.
        fecha:          date; default hoy.

    Returns:
        Decimal — monto convertido, redondeado a 4 decimales.

    Raises:
        TasaCambioError si no hay tasa disponible.
        ValueError si el monto es negativo.
    """
    monto = Decimal(str(monto))
    if monto < 0:
        raise ValueError("El monto a convertir no puede ser negativo.")

    tasa = obtener_tasa_cambio(moneda_origen, moneda_destino, empresa=empresa, fecha=fecha)
    resultado = monto * tasa.valor_tasa
    return resultado.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


@transaction.atomic
def registrar_efectos_pago(pago):
    """
    Genera los side-effects financieros de un ``Pago`` recién creado (BUG-C2).

    En la MISMA transacción (R-CODE-11):
    1. Crea la ``TransaccionFinanciera`` y la asocia al pago.
    2. Si el pago usó datafono, crea la ``TransaccionDatafono``.
    3. Si el pago afecta caja virtual o cuenta bancaria, bloquea el registro
       (``select_for_update``), crea el ``MovimientoCajaBanco`` con los saldos
       correctos y actualiza ``saldo_actual``.

    Args:
        pago: Instancia ``Pago`` ya persistida (con empresa, moneda y método).

    Returns:
        tuple (TransaccionFinanciera, MovimientoCajaBanco | None)
    """
    from .models import (
        Caja,
        CuentaBancariaEmpresa,
        MovimientoCajaBanco,
        TransaccionDatafono,
        TransaccionFinanciera,
    )

    transaccion = TransaccionFinanciera.objects.create(
        id_empresa=pago.id_empresa,
        fecha_hora_transaccion=pago.fecha_pago,
        tipo_transaccion=pago.tipo_operacion,
        monto_transaccion=pago.monto,
        id_moneda_transaccion=pago.id_moneda,
        id_moneda_base=pago.id_moneda,  # Simplificación: misma moneda del pago
        monto_base_empresa=pago.monto,
        id_metodo_pago=pago.id_metodo_pago,
        referencia_pago=pago.referencia,
        descripcion=f"Pago {pago.tipo_operacion.lower()} - {pago.get_tipo_documento_display()}",
        tipo_documento_asociado=pago.tipo_documento,
        nro_documento_asociado=str(pago.id_documento),
        id_caja=pago.id_caja_virtual,
        id_cuenta_bancaria=pago.id_cuenta_bancaria,
        id_usuario_registro=pago.id_usuario_registro,
    )

    pago.id_transaccion_financiera = transaccion
    pago.save(update_fields=["id_transaccion_financiera"])

    if pago.id_datafono_id:
        TransaccionDatafono.objects.create(
            id_datafono=pago.id_datafono,
            monto=pago.monto,
            referencia_bancaria=pago.referencia,
            id_transaccion_financiera_origen=transaccion,
            id_usuario_registro=pago.id_usuario_registro,
        )

    movimiento = None
    if pago.id_caja_virtual_id or pago.id_cuenta_bancaria_id:
        # Lock pesimista sobre el contenedor de saldo para evitar carreras.
        if pago.id_caja_virtual_id:
            contenedor = Caja.objects.select_for_update().get(pk=pago.id_caja_virtual_id)
        else:
            contenedor = CuentaBancariaEmpresa.objects.select_for_update().get(
                pk=pago.id_cuenta_bancaria_id
            )

        tipo_movimiento = "INGRESO" if pago.tipo_operacion == "INGRESO" else "EGRESO"
        saldo_anterior = contenedor.saldo_actual
        delta = pago.monto if tipo_movimiento == "INGRESO" else -pago.monto
        saldo_nuevo = saldo_anterior + delta

        movimiento = MovimientoCajaBanco.objects.create(
            id_empresa=pago.id_empresa,
            fecha_movimiento=pago.fecha_pago.date(),
            hora_movimiento=pago.fecha_pago.time(),
            tipo_movimiento=tipo_movimiento,
            monto=pago.monto,
            id_moneda=pago.id_moneda,
            concepto=f"{pago.tipo_operacion} - {pago.get_tipo_documento_display()}",
            referencia=pago.referencia or f"Pago {pago.id_pago}",
            id_caja=pago.id_caja_virtual,
            id_cuenta_bancaria=pago.id_cuenta_bancaria,
            id_transaccion_financiera=transaccion,
            saldo_anterior=saldo_anterior,
            saldo_nuevo=saldo_nuevo,
            id_usuario_registro=pago.id_usuario_registro,
        )

        contenedor.saldo_actual = saldo_nuevo
        contenedor.save(update_fields=["saldo_actual"])

    return transaccion, movimiento


def realizar_cierre_caja(caja, saldo_real, usuario=None, hasta=None):
    """
    Cierre de caja con corte persistente (patrón PR #73), común a ``Caja``
    (virtual) y ``CajaFisica``.

    - La fuente de verdad del corte es el último ``MovimientoCajaBanco`` de
      tipo ``CIERRE`` de la caja: su ``saldo_nuevo`` (= saldo real contado) es
      el saldo base del período siguiente y su (fecha, hora) el inicio
      EXCLUSIVO de la ventana siguiente (semántica BUG-M4: comparación por
      fecha + hora).
    - Calcula ingresos/egresos de la ventana (hasta el límite, inclusive),
      compara con el saldo real contado y, si hay descuadre, registra un
      ajuste fechado en el límite del cierre — queda DENTRO de la ventana
      recién cerrada y el siguiente cierre no lo vuelve a contar.
    - Persiste el corte como movimiento ``CIERRE`` (monto 0,
      ``saldo_nuevo`` = saldo real contado).
    - Para cajas virtuales además reconcilia ``saldo_actual`` (saldo real
      contado + movimientos posteriores al límite, que la ventana cerrada no
      cubre); las cajas físicas no mantienen saldo vivo (finanzas/0021).

    Args:
        caja:       Instancia ``Caja`` (virtual) o ``CajaFisica``.
        saldo_real: Saldo contado (Decimal o str; R-CODE-4: nunca float).
        usuario:    Usuario que realiza el cierre (opcional).
        hasta:      datetime límite del cierre (opcional; default ahora).

    Returns:
        dict con ingresos, egresos, saldo_teorico, saldo_real, descuadre,
        movimiento_cierre_id, movimiento_ajuste_id, fecha_cierre y mensaje.

    Raises:
        ValueError si el límite es anterior al último cierre.
    """
    from django.db.models import Q

    from .ajustes import crear_ajuste_caja_banco
    from .models import Caja, MovimientoCajaBanco

    es_virtual = isinstance(caja, Caja)
    if es_virtual:
        # Las cajas virtuales también mueven saldo vía transferencias internas.
        tipos_ingreso = ["INGRESO", "AJUSTE_POSITIVO", "TRANSFERENCIA_ENTRADA"]
        tipos_egreso = ["EGRESO", "AJUSTE_NEGATIVO", "TRANSFERENCIA_SALIDA"]
        etiqueta = "caja"
    else:
        tipos_ingreso = ["INGRESO", "AJUSTE_POSITIVO"]
        tipos_egreso = ["EGRESO", "AJUSTE_NEGATIVO"]
        etiqueta = "caja física"

    ahora = timezone.now()
    limite = hasta or ahora
    fecha_limite = limite.date()
    hora_limite = limite.time()
    # R-CODE-4: nunca Decimal(float) — pasar por str preserva el valor.
    saldo_real = saldo_real if isinstance(saldo_real, Decimal) else Decimal(str(saldo_real))

    with transaction.atomic():
        # Lock de la caja: serializa cierres concurrentes sobre la misma caja
        # (dos cierres simultáneos leerían el mismo corte y doble-contarían la
        # ventana).
        caja = type(caja).objects.select_for_update().get(pk=caja.pk)
        ultimo_cierre = (
            caja.movimientos.filter(tipo_movimiento="CIERRE")
            .order_by("-fecha_movimiento", "-hora_movimiento", "-fecha_creacion")
            .first()
        )
        # BUG-M4: la ventana se compara con (fecha, hora) del movimiento, no
        # solo con la fecha, para no recontar movimientos del mismo día
        # anteriores al cierre previo ni incluir los posteriores al límite.
        if ultimo_cierre:
            inicio_fecha = ultimo_cierre.fecha_movimiento
            inicio_hora = ultimo_cierre.hora_movimiento
            if (fecha_limite, hora_limite) < (inicio_fecha, inicio_hora):
                raise ValueError("El límite del cierre no puede ser anterior al último cierre.")
            saldo_base = ultimo_cierre.saldo_nuevo
            # Estrictamente DESPUÉS del último cierre
            movimientos = caja.movimientos.filter(
                Q(fecha_movimiento__gt=inicio_fecha)
                | Q(fecha_movimiento=inicio_fecha, hora_movimiento__gt=inicio_hora)
            )
        else:
            saldo_base = Decimal("0.00")
            movimientos = caja.movimientos.all()
        # Hasta el límite del cierre, inclusive
        movimientos = movimientos.filter(
            Q(fecha_movimiento__lt=fecha_limite)
            | Q(fecha_movimiento=fecha_limite, hora_movimiento__lte=hora_limite)
        )
        ingresos = sum(
            (m.monto for m in movimientos.filter(tipo_movimiento__in=tipos_ingreso)),
            Decimal("0.00"),
        )
        egresos = sum(
            (m.monto for m in movimientos.filter(tipo_movimiento__in=tipos_egreso)),
            Decimal("0.00"),
        )
        saldo_teorico = saldo_base + ingresos - egresos
        descuadre = saldo_real - saldo_teorico

        movimiento_ajuste = None
        if descuadre != 0:
            # Crear ajuste para cuadrar el saldo. Se fecha en el límite del
            # cierre (no en now()) para que pertenezca a la ventana recién
            # cerrada y no se doble-cuente en el cierre siguiente.
            tipo_ajuste = "POSITIVO" if descuadre > 0 else "NEGATIVO"
            movimiento_ajuste = crear_ajuste_caja_banco(
                empresa=caja.empresa,
                monto=abs(descuadre),
                moneda=caja.moneda if es_virtual else None,
                caja=caja if es_virtual else None,
                caja_fisica=None if es_virtual else caja,
                usuario=usuario,
                motivo=f"Ajuste por descuadre en cierre de {etiqueta} {caja.nombre}",
                tipo_ajuste=tipo_ajuste,
                referencia=f'Ajuste cierre {caja.nombre} {limite.strftime("%Y-%m-%d %H:%M:%S")}',
                fecha_movimiento=fecha_limite,
                hora_movimiento=hora_limite,
            )
        # Registrar movimiento de cierre (corte persistente: saldo_nuevo y
        # fecha/hora son la base y el inicio de la ventana del siguiente
        # cierre).
        movimiento_cierre = MovimientoCajaBanco.objects.create(
            id_empresa=caja.empresa,
            fecha_movimiento=fecha_limite,
            hora_movimiento=hora_limite,
            tipo_movimiento="CIERRE",
            monto=Decimal("0.00"),
            id_moneda=caja.moneda if es_virtual else None,
            concepto=(
                f"Cierre de {etiqueta}. Saldo real: {saldo_real}, "
                f"saldo teórico: {saldo_teorico}, descuadre: {descuadre}"
            ),
            referencia=f'Cierre {caja.nombre} {limite.strftime("%Y-%m-%d %H:%M:%S")}',
            id_caja=caja if es_virtual else None,
            id_caja_fisica=None if es_virtual else caja,
            saldo_anterior=saldo_base,
            saldo_nuevo=saldo_real,
            id_usuario_registro=usuario if usuario else None,
        )
        if es_virtual:
            # Reconciliar el saldo vivo de la caja virtual: el saldo real
            # contado más los movimientos posteriores al límite (fuera de la
            # ventana cerrada, ya reflejados en el saldo incremental).
            posteriores = caja.movimientos.filter(
                Q(fecha_movimiento__gt=fecha_limite)
                | Q(fecha_movimiento=fecha_limite, hora_movimiento__gt=hora_limite)
            )
            delta_posterior = sum(
                (m.monto for m in posteriores.filter(tipo_movimiento__in=tipos_ingreso)),
                Decimal("0.00"),
            ) - sum(
                (m.monto for m in posteriores.filter(tipo_movimiento__in=tipos_egreso)),
                Decimal("0.00"),
            )
            caja.saldo_actual = saldo_real + delta_posterior
            caja.save(update_fields=["saldo_actual"])
    return {
        "ingresos": ingresos,
        "egresos": egresos,
        "saldo_teorico": saldo_teorico,
        "saldo_real": saldo_real,
        "descuadre": descuadre,
        "movimiento_cierre_id": movimiento_cierre.id_movimiento,
        "movimiento_ajuste_id": movimiento_ajuste.id_movimiento if movimiento_ajuste else None,
        "fecha_cierre": limite,
        "mensaje": (
            f"Cierre de {etiqueta} realizado."
            if descuadre == 0
            else f"Cierre de {etiqueta} realizado con ajuste."
        ),
    }
