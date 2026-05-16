"""
Servicios de cálculo fiscal venezolano.

Funciones deterministas (sin I/O) que calculan impuestos.
Las tasas se leen de ConfiguracionImpuesto; si no existe, se usan defaults.
"""

from decimal import ROUND_HALF_UP, Decimal


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
