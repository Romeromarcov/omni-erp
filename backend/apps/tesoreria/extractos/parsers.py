"""Parsers multi-banco y multi-empresa para estados de cuenta venezolanos, cripto y genéricos.

Cero acoplamiento a cuentas de una empresa específica:
- ``cuenta_clave`` identifica la cuenta bancaria del tenant en la huella SHA-256.
- ``moneda`` proviene de ``CuentaBancariaEmpresa.id_moneda.codigo_iso``.
- ``cuenta_sufijo`` se deriva dinámicamente de los últimos dígitos de
  ``CuentaBancariaEmpresa.numero_cuenta`` para impedir cargar el archivo de otra cuenta.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .lector_hojas import leer_filas_tabular
from .modelos_canonicos import (
    CERO,
    EstadoCuentaCanonico,
    ExtractoBancarioError,
    LineaExtractoCanonica,
)
from .numeros import limpiar_ref, parse_fecha, parse_monto

FORMATOS_BANCO_SOPORTADOS: tuple[str, ...] = (
    "BANCAMIGA",
    "BANESCO",
    "VENEZUELA",
    "BDT",
    "MERCANTIL",
    "PROVINCIAL",
    "BINANCE",
    "GENERICO_DEB_CRED",
)

_FOOTER_RE = re.compile(r"(?i)^\s*cr[eé]ditos\s+total")
_CUENTA_ENCABEZADO_RE = re.compile(r"(?i)^\s*cuenta:\s*([\d\s-]+)")
_SALDO_INICIAL_ENCABEZADO_RE = re.compile(r"(?i)^\s*saldo inicial:\s*(-?[\d.,()]+)")
_ID_BINANCE_RE = re.compile(r"\b(P_[A-Z0-9]+|N\d{10,})\b")


def inferir_formato_banco(nombre_banco: str) -> str:
    """Infiere el formato de parser a partir del nombre del banco de la cuenta."""
    texto = (nombre_banco or "").strip().upper()
    if "BANCAMIGA" in texto:
        return "BANCAMIGA"
    if "BANESCO" in texto:
        return "BANESCO"
    if "VENEZUELA" in texto or re.search(r"\bBDV\b", texto):
        return "VENEZUELA"
    if "TESORO" in texto or re.search(r"\bBDT\b", texto) or "BICENTENARIO" in texto:
        return "BDT"
    if "PROVINCIAL" in texto or "BBVA" in texto:
        return "PROVINCIAL"
    if "MERCANTIL" in texto:
        return "MERCANTIL"
    if "BINANCE" in texto:
        return "BINANCE"
    return "GENERICO_DEB_CRED"


def extraer_sufijo_cuenta(numero_cuenta: str | None, longitud: int = 4) -> str | None:
    """Extrae los últimos ``longitud`` dígitos de un número de cuenta bancaria."""
    digitos = re.sub(r"\D", "", numero_cuenta or "")
    if len(digitos) >= longitud:
        return digitos[-longitud:]
    return None


def _celda(fila: list[Any], idx: int | None) -> Any:
    if idx is None or idx < 0 or idx >= len(fila):
        return None
    return fila[idx]


def _idx_opcional(header: list[Any], *nombres: str) -> int | None:
    norm = [str(h if h is not None else "").strip().lower() for h in header]
    for n in nombres:
        objetivo = n.lower()
        if objetivo in norm:
            return norm.index(objetivo)
    return None


def _idx(header: list[Any], *nombres: str) -> int:
    pos = _idx_opcional(header, *nombres)
    if pos is None:
        raise ExtractoBancarioError(f"No se encontró la columna {nombres} en el encabezado {header}.")
    return pos


def _fila_vacia(fila: list[Any]) -> bool:
    return all(c in (None, "") for c in fila)


def _construir_linea(
    *,
    formato_banco: str,
    cuenta_clave: str,
    moneda: str,
    fecha: date,
    referencia: str,
    descripcion: Any,
    debito: Decimal | None,
    credito: Decimal | None,
    saldo: Decimal | None,
    orden: int,
    codigo: str = "",
    correlativo: str = "",
) -> LineaExtractoCanonica:
    deb = debito if debito is not None else CERO
    cre = credito if credito is not None else CERO
    if deb < CERO or cre < CERO:
        raise ExtractoBancarioError(f"Fila #{orden}: débito/crédito negativo inválido ({deb}/{cre}).")
    return LineaExtractoCanonica(
        formato_banco=formato_banco,
        cuenta_clave=cuenta_clave,
        moneda=moneda,
        fecha=fecha,
        referencia=referencia,
        descripcion=re.sub(r"\s+", " ", str(descripcion or "")).strip(),
        debito=deb,
        credito=cre,
        saldo=saldo,
        orden=orden,
        codigo=codigo,
        correlativo=correlativo,
    )


def _derivar_saldo_inicial(est: EstadoCuentaCanonico) -> None:
    if est.saldo_inicial is not None or not est.movimientos:
        return
    primero = est.movimientos[0]
    if primero.saldo is not None:
        est.saldo_inicial = primero.saldo - primero.neto
        est.saldo_inicial_derivado = True


def _parse_deb_cred(
    contenido: bytes,
    nombre_archivo: str,
    *,
    formato_banco: str,
    cuenta_clave: str,
    moneda: str,
    con_codigo: bool = False,
    cuenta_sufijo: str | None = None,
    permitir_flexible: bool = False,
) -> EstadoCuentaCanonico:
    filas, datemode = leer_filas_tabular(contenido, nombre_archivo)
    try:
        h = next(
            i
            for i, f in enumerate(filas)
            if any(str(c if c is not None else "").strip().lower() == "fecha" for c in f)
        )
    except StopIteration:
        raise ExtractoBancarioError(
            f"{nombre_archivo}: no se encontró la fila de encabezado (columna 'Fecha')."
        ) from None

    saldo_inicial_encabezado: Decimal | None = None
    for fila_pre in filas[:h]:
        for valor_celda in fila_pre:
            texto_celda = str(valor_celda if valor_celda is not None else "").strip()
            if not texto_celda:
                continue
            m_cta = _CUENTA_ENCABEZADO_RE.match(texto_celda)
            if m_cta and cuenta_sufijo:
                numero = re.sub(r"\D", "", m_cta.group(1))
                if len(numero) >= len(cuenta_sufijo) and not numero.endswith(cuenta_sufijo):
                    raise ExtractoBancarioError(
                        f"{nombre_archivo}: es de la cuenta {numero}, no coincide con la cuenta "
                        f"seleccionada (…{cuenta_sufijo})."
                    )
            m_si = _SALDO_INICIAL_ENCABEZADO_RE.match(texto_celda)
            if m_si:
                saldo_inicial_encabezado = parse_monto(m_si.group(1))

    header = filas[h]
    i_f = _idx(header, "fecha")
    i_r = (
        _idx_opcional(header, "referencia", "ref", "documento", "nro. referencia")
        if permitir_flexible
        else _idx(header, "referencia", "documento", "nro. referencia")
    )
    i_d = _idx(header, "concepto", "descripción", "descripcion", "detalle")

    i_deb = _idx_opcional(header, "débito", "debito", "cargo", "cargos")
    i_cre = _idx_opcional(header, "crédito", "credito", "abono", "abonos")
    i_imp: int | None = None
    if i_deb is None or i_cre is None:
        if permitir_flexible:
            i_imp = _idx(header, "monto", "importe")
        else:
            i_deb = _idx(header, "débito", "debito")
            i_cre = _idx(header, "crédito", "credito")

    i_s = _idx_opcional(header, "saldo", "balance") if permitir_flexible else _idx(header, "saldo", "balance")
    i_c = _idx_opcional(header, "código", "codigo", "tipo") if con_codigo else None

    est = EstadoCuentaCanonico(
        formato_banco=formato_banco,
        cuenta_clave=cuenta_clave,
        moneda=moneda,
        archivo=nombre_archivo,
        saldo_inicial=saldo_inicial_encabezado,
    )
    orden = 0
    for fila in filas[h + 1 :]:
        if _fila_vacia(fila):
            continue
        primera_celda = str(_celda(fila, 0) or "")
        texto_fila = " ".join("" if c is None else str(c) for c in fila)
        if _FOOTER_RE.match(primera_celda):
            m_sf = re.search(r"Saldo Final:\s*(-?[\d.,]+)", texto_fila, re.I)
            est.avisos.append(f"footer del banco: {texto_fila.strip()}")
            if m_sf:
                est.saldo_final = parse_monto(m_sf.group(1))
            continue

        concepto_upper = str(_celda(fila, i_d) or "").strip().upper()
        try:
            saldo = parse_monto(_celda(fila, i_s)) if i_s is not None else None
        except ValueError as exc:
            raise ExtractoBancarioError(f"{nombre_archivo}: saldo inválido en fila: {exc}") from exc

        if concepto_upper.startswith("SALDO INICIAL"):
            if not est.movimientos:
                est.saldo_inicial = saldo
            else:
                previo = est.movimientos[-1].saldo
                if saldo is not None and previo is not None and saldo != previo:
                    est.avisos.append(
                        f"SALDO INICIAL {saldo} a mitad de archivo no coincide con el " f"saldo previo {previo}"
                    )
            continue

        celda_fecha = _celda(fila, i_f)
        if celda_fecha in (None, ""):
            continue

        try:
            fecha_mov = parse_fecha(celda_fecha, datemode)
            if i_imp is not None:
                imp = parse_monto(_celda(fila, i_imp))
                if imp is None:
                    raise ExtractoBancarioError(f"{nombre_archivo}: fila sin monto/importe en fecha {fecha_mov}.")
                deb_val = -imp if imp < CERO else CERO
                cre_val = imp if imp > CERO else CERO
            else:
                deb_val = parse_monto(_celda(fila, i_deb)) or CERO
                cre_val = parse_monto(_celda(fila, i_cre)) or CERO
        except ValueError as exc:
            raise ExtractoBancarioError(f"{nombre_archivo}: {exc}") from exc

        orden += 1
        est.movimientos.append(
            _construir_linea(
                formato_banco=formato_banco,
                cuenta_clave=cuenta_clave,
                moneda=moneda,
                fecha=fecha_mov,
                referencia=limpiar_ref(_celda(fila, i_r)),
                descripcion=_celda(fila, i_d),
                debito=deb_val,
                credito=cre_val,
                saldo=saldo,
                orden=orden,
                codigo=str(_celda(fila, i_c) or "").strip() if i_c is not None else "",
            )
        )

    _derivar_saldo_inicial(est)
    return est


def _parse_provincial(
    contenido: bytes,
    nombre_archivo: str,
    *,
    cuenta_clave: str,
    moneda: str,
) -> EstadoCuentaCanonico:
    filas, datemode = leer_filas_tabular(contenido, nombre_archivo)
    try:
        h = next(
            i
            for i, f in enumerate(filas)
            if any(str(c if c is not None else "").strip().lower() == "fecha" for c in f)
        )
    except StopIteration:
        raise ExtractoBancarioError(
            f"{nombre_archivo}: no se encontró la fila de encabezado (columna 'Fecha')."
        ) from None

    header = filas[h]
    i_f = _idx(header, "fecha")
    i_r = _idx(header, "referencia")
    i_d = _idx(header, "descripción", "descripcion", "concepto")
    i_i = _idx(header, "importe", "monto")
    i_s = _idx(header, "saldo", "balance")

    est = EstadoCuentaCanonico(
        formato_banco="PROVINCIAL",
        cuenta_clave=cuenta_clave,
        moneda=moneda,
        archivo=nombre_archivo,
    )
    crudo: list[tuple[date, int, Any, Decimal, Decimal | None]] = []
    for fila in filas[h + 1 :]:
        if _fila_vacia(fila) or _celda(fila, i_f) in (None, ""):
            continue
        try:
            imp = parse_monto(_celda(fila, i_i))
            if imp is None:
                raise ExtractoBancarioError(f"{nombre_archivo}: fila sin importe.")
            corr_raw = _celda(fila, i_r)
            corr = int(float(str(corr_raw).strip())) if corr_raw not in (None, "") else 0
            fecha_mov = parse_fecha(_celda(fila, i_f), datemode)
            saldo_mov = parse_monto(_celda(fila, i_s))
        except (ValueError, OverflowError) as exc:
            raise ExtractoBancarioError(f"{nombre_archivo}: {exc}") from exc

        crudo.append((fecha_mov, corr, _celda(fila, i_d), imp, saldo_mov))

    crudo.sort(key=lambda t: (t[0], t[1]))
    for orden, (f_mov, corr, desc, imp, saldo) in enumerate(crudo, start=1):
        est.movimientos.append(
            _construir_linea(
                formato_banco="PROVINCIAL",
                cuenta_clave=cuenta_clave,
                moneda=moneda,
                fecha=f_mov,
                referencia="",
                descripcion=desc,
                debito=-imp if imp < CERO else CERO,
                credito=imp if imp > CERO else CERO,
                saldo=saldo,
                orden=orden,
                correlativo=str(corr),
            )
        )
    _derivar_saldo_inicial(est)
    return est


def _parse_binance(
    contenido: bytes,
    nombre_archivo: str,
    *,
    cuenta_clave: str,
    moneda: str,
) -> EstadoCuentaCanonico:
    filas, _datemode = leer_filas_tabular(contenido, nombre_archivo)
    try:
        h = next(
            i
            for i, f in enumerate(filas)
            if any(str(c if c is not None else "").strip().lower() in ("operación", "operacion") for c in f)
        )
    except StopIteration:
        raise ExtractoBancarioError(
            f"{nombre_archivo}: no se encontró el encabezado de Binance (columna 'Operación')."
        ) from None

    header = filas[h]
    i_h = _idx(header, "hora")
    i_cta = _idx(header, "cuenta")
    i_op = _idx(header, "operación", "operacion")
    i_mon = _idx(header, "moneda")
    i_monto = _idx(header, "cambiar")
    i_com = _idx(header, "comentario")

    est = EstadoCuentaCanonico(
        formato_banco="BINANCE",
        cuenta_clave=cuenta_clave,
        moneda=moneda,
        archivo=nombre_archivo,
    )
    crudo: list[tuple[datetime, int, list[Any]]] = []
    for pos, fila in enumerate(filas[h + 1 :]):
        celda_hora = _celda(fila, i_h)
        if _fila_vacia(fila) or celda_hora in (None, ""):
            continue
        if isinstance(celda_hora, datetime):
            hora = celda_hora
        else:
            try:
                hora = datetime.strptime(str(celda_hora).strip(), "%Y-%m-%d %H:%M:%S")
            except ValueError as exc:
                raise ExtractoBancarioError(f"{nombre_archivo}: hora inválida en Binance ({celda_hora!r}).") from exc
        crudo.append((hora, pos, fila))

    crudo.sort(key=lambda t: (t[0], t[1]))
    monedas_vistas: set[str] = set()
    monedas_permitidas = {"USD", "USDT"} if moneda.upper() in ("USD", "USDT") else {moneda.upper()}
    for orden, (hora, _pos, fila) in enumerate(crudo, start=1):
        try:
            monto = parse_monto(_celda(fila, i_monto), punto_miles=False)
        except ValueError as exc:
            raise ExtractoBancarioError(f"{nombre_archivo}: {exc}") from exc
        if monto is None:
            raise ExtractoBancarioError(f"{nombre_archivo}: fila sin monto en Binance.")
        mon_fila = str(_celda(fila, i_mon) or "").strip().upper()
        monedas_vistas.add(mon_fila)
        if mon_fila not in monedas_permitidas:
            raise ExtractoBancarioError(
                f"{nombre_archivo}: moneda {mon_fila!r} no compatible con la cuenta ({moneda})."
            )
        comentario = str(_celda(fila, i_com) or "").strip()
        m_id = _ID_BINANCE_RE.search(comentario)
        desc = f"{_celda(fila, i_op)} {mon_fila} ({_celda(fila, i_cta)})" + (f" - {comentario}" if comentario else "")
        est.movimientos.append(
            _construir_linea(
                formato_banco="BINANCE",
                cuenta_clave=cuenta_clave,
                moneda=moneda,
                fecha=hora.date(),
                referencia=m_id.group(1) if m_id else "",
                descripcion=desc,
                debito=-monto if monto < CERO else CERO,
                credito=monto if monto > CERO else CERO,
                saldo=None,
                orden=orden,
                correlativo=hora.isoformat(sep=" "),
            )
        )

    est.avisos.append("Binance no informa saldo: no se valida la cadena ni hay saldo de cierre")
    if "USDT" in monedas_vistas and moneda.upper() == "USD":
        est.avisos.append("USDT tomado 1:1 con USD")
    return est


def parsear_extracto(
    contenido: bytes,
    nombre_archivo: str,
    formato_banco: str,
    *,
    cuenta_clave: str,
    moneda: str = "VES",
    cuenta_sufijo: str | None = None,
) -> EstadoCuentaCanonico:
    """Parsea los bytes de un extracto bancario al modelo canónico multi-tenant."""
    clave = (formato_banco or "").strip().upper()
    if clave == "BANCAMIGA_USD":
        clave = "BANCAMIGA"
        if moneda == "VES":
            moneda = "USD"

    if clave not in FORMATOS_BANCO_SOPORTADOS:
        raise ExtractoBancarioError(
            f"Formato de banco no soportado: '{formato_banco}'. "
            f"Disponibles: {', '.join(FORMATOS_BANCO_SOPORTADOS)}."
        )

    if clave == "PROVINCIAL":
        return _parse_provincial(contenido, nombre_archivo, cuenta_clave=cuenta_clave, moneda=moneda)
    if clave == "BINANCE":
        return _parse_binance(contenido, nombre_archivo, cuenta_clave=cuenta_clave, moneda=moneda)
    if clave == "BDT":
        return _parse_deb_cred(
            contenido,
            nombre_archivo,
            formato_banco=clave,
            cuenta_clave=cuenta_clave,
            moneda=moneda,
            con_codigo=True,
            cuenta_sufijo=cuenta_sufijo,
        )
    if clave in ("MERCANTIL", "GENERICO_DEB_CRED"):
        return _parse_deb_cred(
            contenido,
            nombre_archivo,
            formato_banco=clave,
            cuenta_clave=cuenta_clave,
            moneda=moneda,
            con_codigo=True,
            cuenta_sufijo=cuenta_sufijo,
            permitir_flexible=True,
        )
    return _parse_deb_cred(
        contenido,
        nombre_archivo,
        formato_banco=clave,
        cuenta_clave=cuenta_clave,
        moneda=moneda,
        cuenta_sufijo=cuenta_sufijo,
    )
