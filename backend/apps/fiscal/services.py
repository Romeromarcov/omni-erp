"""
Servicios de cálculo fiscal venezolano.

Funciones deterministas (sin I/O) que calculan impuestos.
Las tasas se leen de ConfiguracionImpuesto; si no existe, se usan defaults.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction


# ── Tasas por defecto (SENIAT 2024) ──────────────────────────────────────────

TASA_IVA_GENERAL = Decimal("0.16")
TASA_IVA_REDUCIDO = Decimal("0.08")
TASA_IVA_EXENTO = Decimal("0")
TASA_IGTF_DEFAULT = Decimal("0.03")


METODOS_PAGO_IGTF = frozenset({
    "DIVISA_EFECTIVO",
    "DIVISA_TRANSFERENCIA",
    "CRYPTO",
    "PETRO",
})


# ── Excepciones ───────────────────────────────────────────────────────────────


class ImpuestoError(Exception):
    pass


class PeriodoCerradoError(Exception):
    """Se intentó emitir/modificar un documento fiscal en un período ya cerrado."""

    pass


# ── Enforcement de cierre de período fiscal (deuda #1, auditoría 2026-06-21) ───


def validar_periodo_abierto(empresa, fecha) -> None:
    """
    Verifica que el PeriodoFiscal correspondiente a ``fecha`` NO esté cerrado
    para ``empresa`` (multi-tenant: el período se filtra por empresa).

    Una vez que un período mensual se marca como cerrado (cierre contable/fiscal,
    declaración SENIAT presentada) no se pueden emitir ni modificar documentos
    fiscales con fecha dentro de ese período. Este guard hace cumplir esa regla,
    que antes era cosmética (``PeriodoFiscal.esta_cerrado`` existía pero ningún
    flujo de emisión lo consultaba).

    Args:
        empresa: instancia core.Empresa (o su pk) dueña del período.
        fecha:   date del documento (se usan su año y mes).

    Raises:
        PeriodoCerradoError: si el período (empresa, fecha.year, fecha.month)
            está cerrado. Los callers la traducen a 400 con mensaje claro.
    """
    from .models import PeriodoFiscal

    if PeriodoFiscal.esta_cerrado(empresa, fecha.year, fecha.month):
        raise PeriodoCerradoError(
            f"El período fiscal {fecha.year:04d}-{fecha.month:02d} está cerrado; "
            "no se pueden emitir ni modificar documentos fiscales en ese período."
        )


# ── Helpers internos ──────────────────────────────────────────────────────────


def _obtener_tasa_iva(empresa, tipo: str) -> Decimal:
    """Lee la tasa de TasaIVAEmpresa o devuelve el default SENIAT."""
    from .models import TasaIVAEmpresa

    try:
        cfg = TasaIVAEmpresa.objects.get(id_empresa=empresa, tipo=tipo, activo=True)
        return Decimal(str(cfg.tasa))
    except TasaIVAEmpresa.DoesNotExist:
        defaults = {
            "GENERAL": TASA_IVA_GENERAL,
            "REDUCIDO": TASA_IVA_REDUCIDO,
            "EXENTO": TASA_IVA_EXENTO,
        }
        return defaults.get(tipo, TASA_IVA_GENERAL)


def _obtener_tasa_igtf(empresa) -> Decimal:
    from .models import ConfiguracionFiscalEmpresa

    try:
        cfg = ConfiguracionFiscalEmpresa.objects.get(id_empresa=empresa)
        return Decimal(str(cfg.tasa_igtf))
    except ConfiguracionFiscalEmpresa.DoesNotExist:
        return TASA_IGTF_DEFAULT


# ── API pública ───────────────────────────────────────────────────────────────


def calcular_iva(subtotal: Decimal, tipo_iva: str, empresa=None) -> dict:
    """
    Calcula IVA sobre un subtotal.

    Args:
        subtotal: monto base sin impuesto
        tipo_iva: "GENERAL" | "REDUCIDO" | "EXENTO"
        empresa: instancia Empresa (para leer tasa configurada) o None (usa default)

    Returns:
        {
            "base_imponible": Decimal,
            "tasa": Decimal,
            "monto_iva": Decimal,
            "total": Decimal,
        }
    """
    subtotal = Decimal(str(subtotal))
    if subtotal < 0:
        raise ImpuestoError("El subtotal no puede ser negativo.")

    tasa = _obtener_tasa_iva(empresa, tipo_iva) if empresa else {
        "GENERAL": TASA_IVA_GENERAL,
        "REDUCIDO": TASA_IVA_REDUCIDO,
        "EXENTO": TASA_IVA_EXENTO,
    }.get(tipo_iva, TASA_IVA_GENERAL)

    monto_iva = (subtotal * tasa).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "base_imponible": subtotal,
        "tasa": tasa,
        "monto_iva": monto_iva,
        "total": subtotal + monto_iva,
    }


def calcular_igtf(monto_pago: Decimal, metodo_pago: str, empresa=None) -> dict:
    """
    Calcula IGTF si el método de pago está sujeto.

    Args:
        monto_pago: monto total del pago
        metodo_pago: código del método de pago
        empresa: instancia Empresa o None (usa default 3%)

    Returns:
        {
            "aplica": bool,
            "base": Decimal,
            "tasa": Decimal,
            "monto_igtf": Decimal,
            "total_con_igtf": Decimal,
        }
    """
    monto_pago = Decimal(str(monto_pago))
    aplica = metodo_pago in METODOS_PAGO_IGTF

    # GAP-2 / ADR-007: el IGTF es de la capa legal venezolana. No aplica si la
    # empresa tiene la localización legal desactivada o su país no es Venezuela.
    if empresa is not None:
        if not getattr(empresa, "localizacion_legal_activa", True):
            aplica = False
        pais = getattr(empresa, "pais_codigo_iso", None)
        if pais and pais.upper() not in ("VE", "VEN"):
            aplica = False

    if not aplica:
        return {
            "aplica": False,
            "base": monto_pago,
            "tasa": Decimal("0"),
            "monto_igtf": Decimal("0"),
            "total_con_igtf": monto_pago,
        }

    tasa = _obtener_tasa_igtf(empresa) if empresa else TASA_IGTF_DEFAULT
    monto_igtf = (monto_pago * tasa).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "aplica": True,
        "base": monto_pago,
        "tasa": tasa,
        "monto_igtf": monto_igtf,
        "total_con_igtf": monto_pago + monto_igtf,
    }


def calcular_impuestos_pedido(lineas: list, metodo_pago: str = "EFECTIVO_BS", empresa=None) -> dict:
    """
    Calcula IVA y opcionalmente IGTF para un pedido completo.

    Args:
        lineas: lista de dicts con {"subtotal": Decimal, "tipo_iva": str}
        metodo_pago: código de método de pago
        empresa: instancia Empresa o None

    Returns:
        {
            "subtotal": Decimal,
            "base_exenta": Decimal,
            "base_reducida": Decimal,
            "base_general": Decimal,
            "iva_reducido": Decimal,
            "iva_general": Decimal,
            "total_iva": Decimal,
            "igtf": dict,
            "total": Decimal,
        }
    """
    subtotal_total = Decimal("0")
    base_exenta = Decimal("0")
    base_reducida = Decimal("0")
    base_general = Decimal("0")
    iva_reducido = Decimal("0")
    iva_general = Decimal("0")

    for linea in lineas:
        sub = Decimal(str(linea["subtotal"]))
        tipo = linea.get("tipo_iva", "GENERAL")
        resultado = calcular_iva(sub, tipo, empresa)
        subtotal_total += sub

        if tipo == "EXENTO":
            base_exenta += sub
        elif tipo == "REDUCIDO":
            base_reducida += sub
            iva_reducido += resultado["monto_iva"]
        else:
            base_general += sub
            iva_general += resultado["monto_iva"]

    total_iva = iva_reducido + iva_general
    total_antes_igtf = subtotal_total + total_iva
    igtf = calcular_igtf(total_antes_igtf, metodo_pago, empresa)

    return {
        "subtotal": subtotal_total,
        "base_exenta": base_exenta,
        "base_reducida": base_reducida,
        "base_general": base_general,
        "iva_reducido": iva_reducido,
        "iva_general": iva_general,
        "total_iva": total_iva,
        "igtf": igtf,
        "total": igtf["total_con_igtf"],
    }


# ── M8: Numeración correlativa y cálculo de impuestos por empresa ─────────────


def siguiente_numero(empresa, tipo: str) -> str:
    """
    Returns next formatted correlative number for empresa+tipo, guaranteed unique.
    Uses select_for_update() to prevent race conditions.
    Creates the NumeroCorrelativo row if it doesn't exist yet (get_or_create + lock).
    """
    from .models import NumeroCorrelativo

    with transaction.atomic():
        # First get_or_create without lock (can't lock non-existent row)
        config, _ = NumeroCorrelativo.objects.get_or_create(
            id_empresa=empresa,
            tipo=tipo,
            defaults={"numero_actual": 0, "digitos": 8},
        )
        # Now lock the existing row
        config = NumeroCorrelativo.objects.select_for_update().get(pk=config.pk)
        config.numero_actual += 1
        config.save(update_fields=["numero_actual", "fecha_actualizacion"])
        return f"{config.prefijo}{config.numero_actual:0{config.digitos}d}"


def calcular_impuestos(subtotal: Decimal, empresa, moneda=None) -> dict:
    """
    Calcula IVA e IGTF para un subtotal dado la configuración de la empresa.

    Args:
        subtotal: base imponible
        empresa: instancia Empresa
        moneda: instancia Moneda o None (IGTF solo aplica si moneda no es VES/BS)

    Returns:
        {
            "base_imponible": Decimal,
            "tasa_iva": Decimal,
            "monto_iva": Decimal,
            "tasa_igtf": Decimal,
            "monto_igtf": Decimal,
            "total": Decimal,
        }
    """
    from .models import ConfiguracionFiscalEmpresa, TasaIVAEmpresa

    subtotal = Decimal(str(subtotal))

    # Get empresa fiscal config (or use defaults)
    try:
        config = ConfiguracionFiscalEmpresa.objects.get(id_empresa=empresa)
        contribuyente_iva = config.contribuyente_iva
        aplica_igtf = config.aplica_igtf
        tasa_igtf_cfg = Decimal(str(config.tasa_igtf))
    except ConfiguracionFiscalEmpresa.DoesNotExist:
        contribuyente_iva = True
        aplica_igtf = False
        tasa_igtf_cfg = TASA_IGTF_DEFAULT

    # Get IVA rate — GENERAL first, fallback to default
    try:
        tasa_iva_obj = TasaIVAEmpresa.objects.get(id_empresa=empresa, tipo="GENERAL", activo=True)
        tasa_iva = Decimal(str(tasa_iva_obj.tasa))
    except TasaIVAEmpresa.DoesNotExist:
        tasa_iva = TASA_IVA_GENERAL if contribuyente_iva else TASA_IVA_EXENTO

    # Get IGTF rate for return value
    try:
        tasa_iva_reducido_obj = TasaIVAEmpresa.objects.get(id_empresa=empresa, tipo="REDUCIDO", activo=True)
        _tasa_reducido = Decimal(str(tasa_iva_reducido_obj.tasa))  # noqa: F841 — available for callers
    except TasaIVAEmpresa.DoesNotExist:
        _tasa_reducido = TASA_IVA_REDUCIDO

    # Compute IVA
    monto_iva = (subtotal * tasa_iva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Compute IGTF — only if applies and moneda is not VES/bolivar
    moneda_es_bolivar = False
    if moneda is not None:
        codigo = getattr(moneda, "codigo_iso", "") or ""
        moneda_es_bolivar = codigo.upper() in ("VES", "BS", "VEF", "VEB")

    tasa_igtf_efectiva = Decimal("0")
    monto_igtf = Decimal("0")
    if aplica_igtf and moneda is not None and not moneda_es_bolivar:
        tasa_igtf_efectiva = tasa_igtf_cfg
        monto_igtf = (subtotal * tasa_igtf_efectiva).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "base_imponible": subtotal,
        "tasa_iva": tasa_iva,
        "monto_iva": monto_iva,
        "tasa_igtf": tasa_igtf_efectiva,
        "monto_igtf": monto_igtf,
        "total": subtotal + monto_iva + monto_igtf,
    }
