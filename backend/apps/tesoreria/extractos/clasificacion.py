"""Clasificación determinística por reglas para movimientos de extractos bancarios.

Primera regla que coincide gana. Lo no cubierto queda en ``ingreso_por_revisar`` o
``por_revisar`` para revisión humana o sugerencia asistida posterior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .modelos_canonicos import LineaExtractoCanonica


@dataclass(frozen=True)
class ReglaClasificacion:
    nombre: str
    categoria: str
    patron: str
    solo: str | None = None  # 'debito' | 'credito' | None


REGLAS_CLASIFICACION: list[ReglaClasificacion] = [
    ReglaClasificacion("nomina_devuelta", "nomina_devuelta", r"N[OÓ]MINA DEVUELTO", "credito"),
    ReglaClasificacion(
        "igtf",
        "impuesto_igtf",
        r"\bIGTF\b|IMP\.?\s*(A\s*LAS\s*)?GRANDES\s*TRANSACCIONES|PERCEPCI[OÓ]N\s*IGTF",
        "debito",
    ),
    # Antes que "nomina": "Comisión servicio pago de nómina" es comisión bancaria, no nómina.
    ReglaClasificacion(
        "comision",
        "comision_bancaria",
        r"^COM[\s.]|^COMIS|^COM(SERV|ENVIO)|COMISI[OÓ|\ufffd]N|CARGO POR SERVICIO|"
        r"MANTENIMIENTO DE CUENTA|^MANT AFIL|ENVIO DE SMS|EMISION ESTADO|USO (DE )?CANAL|"
        r"PIN INVALIDO|CEDULA INVALIDA|SERVICIO MENSAJERIA|SALDO INSUFICIENTE",
        "debito",
    ),
    ReglaClasificacion("nomina", "nomina", r"N[OÓ]MINA", "debito"),
    ReglaClasificacion("interes_islr", "impuesto_retencion", r"INT\.?\s*ISLR"),
    ReglaClasificacion("interes", "interes_ganado", r"\bINTERES(ES)?\b", "credito"),
    ReglaClasificacion("impuesto", "impuesto", r"PAGO IMPUESTOS|SENIAT"),
    ReglaClasificacion("parafiscal", "parafiscal", r"\bIVSS\b|BANAVIH|\bINCES\b"),
    ReglaClasificacion(
        "servicio_publico",
        "servicio",
        r"HIDROCAPITAL|CORPOELEC|CANTV|DIGITEL|MOVISTAR|MOVILNET",
    ),
    ReglaClasificacion(
        "operacion_cambiaria",
        "operacion_cambiaria",
        r"COMPRA USD|VENTA USD|INTERVENCI[OÓ]N",
    ),
    ReglaClasificacion("binance_pay_entra", "cobro_candidato", r"^TRANSFER (USDT|USD).*BINANCE PAY", "credito"),
    ReglaClasificacion("binance_pay_sale", "pago_a_terceros", r"^TRANSFER (USDT|USD).*BINANCE PAY", "debito"),
    ReglaClasificacion("binance_deposito", "transferencia_propia_candidata", r"^DEPOSIT USD"),
    ReglaClasificacion("binance_conversion", "conversion_cripto", r"^BUY CRYPTO WITH FIAT"),
    ReglaClasificacion("binance_retiro", "retiro_cripto", r"^WITHDRAW (USDT|USD)", "debito"),
    ReglaClasificacion("zelle_entra", "cobro_candidato", r"\bZELLE\b", "credito"),
    ReglaClasificacion("zelle_sale", "pago_a_terceros", r"\bZELLE\b", "debito"),
    ReglaClasificacion("compra_internacional", "compra_tarjeta", r"OP\.? INTERNAC\.? MASTERDEBIT", "debito"),
    ReglaClasificacion("transferencia_propia", "transferencia_propia_candidata", r"MISMO CLIENTE"),
    ReglaClasificacion("consumo_debito", "compra_tarjeta", r"CONSUMO MASTERDEBIT|CONSUMO MAESTRO", "debito"),
    ReglaClasificacion("alcaldia", "impuesto", r"ALCALDIA|ALCALD[IÍ]A", "debito"),
    ReglaClasificacion(
        "transf_saliente",
        "pago_a_terceros",
        r"TRANSF\.?( INTERNET)? TERC|TRANSF EN LINEA|PAGO MOVIL|PAGO M[OÓ]VIL",
        "debito",
    ),
    ReglaClasificacion("nc_transferencia", "cobro_candidato", r"^NC (TRANSF|PAGO DE PROVEEDORES)", "credito"),
    ReglaClasificacion("platco_pos", "operacion_pos", r"INV\.?\s?PLATCO"),
    ReglaClasificacion("cobro_pos", "cobro_pos", r"^(TD|TC) POS\b", "credito"),
    ReglaClasificacion("compra_tarjeta", "compra_tarjeta", r"COMPRAS?\b.*\bPOS\b|COMPRA POS", "debito"),
    ReglaClasificacion(
        "pago_terceros",
        "pago_a_terceros",
        r"PAGO A (TERCEROS|PROVEEDORES)|CR\.?\s?I\.?/?\s?OB|DIST CLIENTE",
        "debito",
    ),
    ReglaClasificacion(
        "entrada_transferencia",
        "cobro_candidato",
        r"CR\.? ?INM|TRF CR INM|CREDITO INMEDIATO|PAGO RECIBIDO|TRANSF RECIBIDA|FONDOS RECIBIDOS|"
        r"PAGO A (TERCEROS|PROVEEDORES)|TRAV\d",
        "credito",
    ),
]


def clasificar_linea(linea: LineaExtractoCanonica) -> tuple[str, str]:
    """Devuelve ``(categoria, nombre_regla)`` para una línea canónica de extracto."""
    desc = linea.descripcion.upper()
    for regla in REGLAS_CLASIFICACION:
        if regla.solo == "debito" and linea.debito <= 0:
            continue
        if regla.solo == "credito" and linea.credito <= 0:
            continue
        if re.search(regla.patron, desc):
            return regla.categoria, regla.nombre
    if linea.credito > 0 and linea.debito == 0:
        return "ingreso_por_revisar", "sin_regla_credito"
    return "por_revisar", "sin_regla"
