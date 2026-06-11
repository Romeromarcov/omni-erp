"""
Servicios de Tesorería — Conciliación Bancaria.

registrar_movimiento_bancario(): crea un MovimientoBancario manual.
importar_extracto_csv():         importa múltiples movimientos desde CSV.
conciliar_automatico():          empareja movimientos con pagos internos por monto+fecha.
iniciar_conciliacion():          crea una sesión ConciliacionBancaria.
cerrar_conciliacion():           cierra y calcula diferencias.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import IO

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # BUILD-1: solo para anotaciones (evita F821)
    from .models import MovimientoBancario, ConciliacionBancaria



class ConciliacionError(Exception):
    """Error de negocio en el proceso de conciliación."""


# ── registrar_movimiento_bancario ──────────────────────────────────────────────

def registrar_movimiento_bancario(
    *,
    empresa,
    cuenta_bancaria,
    fecha_mov: date,
    descripcion: str,
    tipo: str,
    monto: Decimal,
    referencia: str = "",
    origen: str = "MANUAL",
) -> "MovimientoBancario":
    """
    Registra un movimiento bancario individual.

    Args:
        empresa:         instancia Empresa (multi-tenant).
        cuenta_bancaria: instancia CuentaBancariaEmpresa.
        fecha_mov:       fecha del movimiento.
        descripcion:     descripción del movimiento.
        tipo:            "DEBITO" o "CREDITO".
        monto:           monto positivo (Decimal).
        referencia:      referencia bancaria (opcional).
        origen:          "MANUAL" | "CSV" | "API".

    Returns:
        MovimientoBancario creado.

    Raises:
        ConciliacionError: si el tipo es inválido o el monto es ≤ 0.
    """
    from .models import MovimientoBancario

    if tipo not in ("DEBITO", "CREDITO"):
        raise ConciliacionError(f"Tipo inválido: '{tipo}'. Use 'DEBITO' o 'CREDITO'.")
    if monto <= 0:
        raise ConciliacionError(f"El monto debe ser mayor que cero. Recibido: {monto}.")

    # Validar que la cuenta pertenece a la empresa
    if str(cuenta_bancaria.id_empresa_id) != str(empresa.pk):
        raise ConciliacionError("La cuenta bancaria no pertenece a la empresa indicada.")

    return MovimientoBancario.objects.create(
        id_empresa=empresa,
        id_cuenta_bancaria=cuenta_bancaria,
        fecha_mov=fecha_mov,
        descripcion=descripcion[:300],
        tipo=tipo,
        monto=monto,
        referencia=referencia[:100] if referencia else "",
        estado="PENDIENTE",
        origen=origen,
    )


# ── importar_extracto_csv ──────────────────────────────────────────────────────

CSV_CAMPOS = ["fecha", "descripcion", "tipo", "monto", "referencia"]


def importar_extracto_csv(
    empresa,
    cuenta_bancaria,
    archivo_csv: IO,
) -> dict:
    """
    Importa un extracto bancario desde un archivo CSV.

    Formato esperado del CSV (con cabecera):
        fecha,descripcion,tipo,monto,referencia
        2026-05-01,Pago cliente X,CREDITO,1500.00,REF-001
        2026-05-03,Débito comision,DEBITO,25.00,

    Args:
        empresa:        instancia Empresa.
        cuenta_bancaria: instancia CuentaBancariaEmpresa.
        archivo_csv:    file-like object (texto) con el CSV.

    Returns:
        dict con claves: importados, errores, lineas_error.
    """
    contenido = archivo_csv.read()
    if isinstance(contenido, bytes):
        contenido = contenido.decode("utf-8")

    reader = csv.DictReader(io.StringIO(contenido))
    importados = 0
    errores = 0
    lineas_error = []

    for i, fila in enumerate(reader, start=2):  # fila 1 = cabecera
        try:
            fecha_str = (fila.get("fecha") or "").strip()
            descripcion = (fila.get("descripcion") or "").strip()
            tipo = (fila.get("tipo") or "").strip().upper()
            monto_str = (fila.get("monto") or "").strip()
            referencia = (fila.get("referencia") or "").strip()

            if not fecha_str or not monto_str:
                raise ValueError("Campos 'fecha' y 'monto' son obligatorios.")

            fecha = date.fromisoformat(fecha_str)
            monto = Decimal(monto_str)

            registrar_movimiento_bancario(
                empresa=empresa,
                cuenta_bancaria=cuenta_bancaria,
                fecha_mov=fecha,
                descripcion=descripcion or "Sin descripción",
                tipo=tipo,
                monto=monto,
                referencia=referencia,
                origen="CSV",
            )
            importados += 1

        except (ConciliacionError, ValueError, InvalidOperation, KeyError) as exc:
            errores += 1
            lineas_error.append({"linea": i, "error": str(exc)})

    return {"importados": importados, "errores": errores, "lineas_error": lineas_error}


# ── conciliar_automatico ───────────────────────────────────────────────────────

def conciliar_automatico(
    empresa,
    cuenta_bancaria,
    tolerancia_dias: int = 3,
) -> dict:
    """
    Empareja automáticamente movimientos bancarios pendientes con pagos internos.

    Estrategia de matching (por prioridad):
    1. Monto exacto + misma referencia (texto).
    2. Monto exacto + fecha dentro de tolerancia_dias.

    Solo concilia movimientos CREDITO con pagos INGRESO de la misma cuenta.

    Returns:
        dict con claves: conciliados, sin_match, total_procesados.
    """
    from django.db import transaction

    from .models import MovimientoBancario

    conciliados = 0
    sin_match = 0

    # BUG-M5: todo el emparejamiento corre en una transacción con lock sobre
    # los movimientos pendientes y sobre el Pago candidato, para que dos
    # ejecuciones concurrentes no concilien el mismo Pago contra dos
    # movimientos distintos.
    with transaction.atomic():
        movimientos_pendientes = (
            MovimientoBancario.objects.select_for_update()
            .filter(
                id_empresa=empresa,
                id_cuenta_bancaria=cuenta_bancaria,
                estado="PENDIENTE",
                tipo="CREDITO",
            )
            .order_by("fecha_mov")
        )

        for mov in movimientos_pendientes:
            pago = _buscar_pago_matching(mov, cuenta_bancaria, tolerancia_dias)
            if pago:
                mov.estado = "CONCILIADO"
                mov.id_pago_conciliado = pago
                mov.save(update_fields=["estado", "id_pago_conciliado"])
                conciliados += 1
            else:
                sin_match += 1

    return {
        "conciliados": conciliados,
        "sin_match": sin_match,
        "total_procesados": conciliados + sin_match,
    }


def _buscar_pago_matching(mov, cuenta_bancaria, tolerancia_dias: int):
    """
    Busca un Pago que coincida con el MovimientoBancario.

    Debe llamarse dentro de una transacción: bloquea (``select_for_update``)
    el Pago elegido y re-verifica que siga sin conciliar antes de devolverlo
    (BUG-M5: evita que dos conciliaciones concurrentes usen el mismo Pago).
    """
    from datetime import timedelta

    from apps.finanzas.models import Pago

    from .models import MovimientoBancario

    ventana_inicio = mov.fecha_mov - timedelta(days=tolerancia_dias)
    ventana_fin = mov.fecha_mov + timedelta(days=tolerancia_dias)

    pagos_candidatos = Pago.objects.filter(
        id_cuenta_bancaria=cuenta_bancaria,
        monto=mov.monto,
        tipo_operacion="INGRESO",
        fecha_pago__date__gte=ventana_inicio,
        fecha_pago__date__lte=ventana_fin,
        movimientos_bancarios_conciliados__isnull=True,  # no conciliado antes
    )

    def _lock_y_verificar(pago):
        """Bloquea el Pago y confirma que nadie lo concilió en paralelo."""
        if pago is None:
            return None
        pago = Pago.objects.select_for_update().get(pk=pago.pk)
        if MovimientoBancario.objects.filter(id_pago_conciliado=pago).exists():
            return None
        return pago

    # Prioridad 1: referencia exacta (si existe en ambos)
    if mov.referencia:
        for candidato in pagos_candidatos.filter(referencia=mov.referencia):
            pago = _lock_y_verificar(candidato)
            if pago:
                return pago

    # Prioridad 2: monto + ventana de fecha (tomar el más cercano)
    for candidato in pagos_candidatos.order_by("fecha_pago"):
        pago = _lock_y_verificar(candidato)
        if pago:
            return pago
    return None


# ── iniciar / cerrar conciliación ─────────────────────────────────────────────

def iniciar_conciliacion(
    empresa,
    cuenta_bancaria,
    periodo_inicio: date,
    periodo_fin: date,
    saldo_banco: Decimal,
    saldo_libro: Decimal,
    usuario=None,
) -> "ConciliacionBancaria":
    """Crea una nueva sesión de conciliación bancaria."""
    from .models import ConciliacionBancaria

    diferencia = saldo_banco - saldo_libro

    pendientes = _contar_pendientes(empresa, cuenta_bancaria, periodo_inicio, periodo_fin)
    conciliados_cnt = _contar_conciliados(empresa, cuenta_bancaria, periodo_inicio, periodo_fin)

    return ConciliacionBancaria.objects.create(
        id_empresa=empresa,
        id_cuenta_bancaria=cuenta_bancaria,
        periodo_inicio=periodo_inicio,
        periodo_fin=periodo_fin,
        saldo_banco=saldo_banco,
        saldo_libro=saldo_libro,
        diferencia=diferencia,
        estado="ABIERTA",
        movimientos_pendientes=pendientes,
        movimientos_conciliados=conciliados_cnt,
        realizada_por=usuario,
    )


def cerrar_conciliacion(conciliacion, usuario=None) -> "ConciliacionBancaria":
    """Cierra la sesión de conciliación y recalcula contadores."""
    from django.utils import timezone

    from .models import MovimientoBancario

    empresa = conciliacion.id_empresa
    cuenta = conciliacion.id_cuenta_bancaria
    inicio = conciliacion.periodo_inicio
    fin = conciliacion.periodo_fin

    conciliacion.movimientos_pendientes = _contar_pendientes(empresa, cuenta, inicio, fin)
    conciliacion.movimientos_conciliados = _contar_conciliados(empresa, cuenta, inicio, fin)
    conciliacion.estado = "CERRADA"
    conciliacion.fecha_cierre = timezone.now()
    if usuario:
        conciliacion.realizada_por = usuario
    conciliacion.save(update_fields=[
        "movimientos_pendientes", "movimientos_conciliados",
        "estado", "fecha_cierre", "realizada_por",
    ])
    return conciliacion


def _contar_pendientes(empresa, cuenta, inicio, fin) -> int:
    from .models import MovimientoBancario
    return MovimientoBancario.objects.filter(
        id_empresa=empresa,
        id_cuenta_bancaria=cuenta,
        fecha_mov__gte=inicio,
        fecha_mov__lte=fin,
        estado="PENDIENTE",
    ).count()


def _contar_conciliados(empresa, cuenta, inicio, fin) -> int:
    from .models import MovimientoBancario
    return MovimientoBancario.objects.filter(
        id_empresa=empresa,
        id_cuenta_bancaria=cuenta,
        fecha_mov__gte=inicio,
        fecha_mov__lte=fin,
        estado="CONCILIADO",
    ).count()
