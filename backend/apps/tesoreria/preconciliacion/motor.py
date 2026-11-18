"""Motor puro y determinístico de pre-conciliación bancaria multi-tenant.

Reglas contables (desacopladas de cualquier empresa concreta):
- R1: comisiones bancarias e impuestos IGTF -> cuenta contable configurada en la cuenta bancaria.
- R2: emparejamiento contra pagos candidatos (nativos de Omni ERP y/o externos de Odoo en modo
      estrictamente ``solo_lectura``) de la misma cuenta/diario, mismo monto al centavo, sentido
      coincidente (crédito=ingreso, débito=egreso) y ventana de ±N días (default 3).
      Desempate por puntaje: cercanía de fecha (+3 mismo día, +2 1d, +1 >=2d), sufijo de >=4
      dígitos de referencia bancaria (+3) y RIF/cédula normalizado (+3, excluyendo el RIF propio
      de la empresa). Gana el mayor puntaje estrictamente; empates quedan ``AMBIGUO``.
- R3: operaciones de punto de venta, compras con tarjeta o nómina sin pago candidato -> cuenta de
      tránsito / pagos pendientes configurada en la cuenta bancaria.
- En cualquier otro caso -> ``SIN_PROPUESTA``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

CENT = Decimal("0.01")
VENTANA_DIAS_DEFAULT = 3

CATEGORIAS_COMISION = frozenset({"comision_bancaria"})
CATEGORIAS_IGTF = frozenset({"impuesto_igtf"})
CATEGORIAS_PENDIENTES = frozenset({"compra_tarjeta", "operacion_pos", "nomina"})

TIPO_PAGO = "PAGO"
TIPO_CUENTA = "CUENTA"
TIPO_AMBIGUO = "AMBIGUO"
TIPO_SIN_PROPUESTA = "SIN_PROPUESTA"

METODOS_LECTURA_ODOO = frozenset({"search_read", "read", "search_count", "search", "fields_get"})
ESTADOS_PAGO_ODOO = ["posted", "in_process", "paid"]

_RIF_RE = re.compile(r"\b([VJEGBP])-?0*(\d{6,10})(?:-(\d))?\b")
_NO_DIGITOS_RE = re.compile(r"\D+")
_SOLO_ALNUM_RE = re.compile(r"[^A-Z0-9]")

ExecuteOdoo = Callable[..., Any]


def rifs(texto: str | None) -> frozenset[str]:
    """Extrae RIF/cédulas normalizados ('J-050783614-2' y 'J507836142' -> 'J507836142')."""
    if not texto:
        return frozenset()
    mayus = texto.upper()
    hallados = {f"{letra}{int(num)}{dv}" for letra, num, dv in _RIF_RE.findall(mayus)}
    compacto = _SOLO_ALNUM_RE.sub("", mayus)
    if compacto and len(compacto) >= 7 and compacto[0] in "VJEGBP" and compacto[1:].isdigit():
        hallados.add(f"{compacto[0]}{int(compacto[1:])}")
    return frozenset(hallados)


def digitos_referencia(ref: str | None) -> str:
    """Conserva únicamente dígitos significativos (sin ceros iniciales)."""
    return _NO_DIGITOS_RE.sub("", ref or "").lstrip("0")


@dataclass(frozen=True)
class ReglasCuentaConciliacion:
    """Reglas configuradas para una cuenta bancaria concreta de una empresa."""

    cuenta_comisiones_id: str | None = None
    cuenta_comisiones_codigo: str = ""
    cuenta_igtf_id: str | None = None
    cuenta_igtf_codigo: str = ""
    cuenta_transito_id: str | None = None
    cuenta_transito_codigo: str = ""
    ventana_dias: int = VENTANA_DIAS_DEFAULT
    rifs_propios_empresa: frozenset[str] = frozenset()


@dataclass(frozen=True)
class MovimientoParaConciliar:
    """Proyección canónica de un ``MovimientoBancario`` para evaluar reglas."""

    movimiento_id: str
    huella: str
    fecha: date
    orden: int
    es_credito: bool
    monto: Decimal
    referencia: str = ""
    descripcion: str = ""
    categoria: str = ""
    regla_clasificacion: str = ""


@dataclass(frozen=True)
class PagoCandidato:
    """Pago candidato normalizado (sea nativo ``OMNI`` o leído desde ``ODOO``)."""

    fuente: str  # "OMNI" | "ODOO"
    pago_id: str
    nombre: str
    fecha: date
    monto: Decimal
    entrante: bool
    memo: str = ""
    socio: str = ""
    partner_rifs: frozenset[str] = frozenset()
    ya_conciliado: bool = False

    @property
    def clave(self) -> str:
        return f"{self.fuente}:{self.pago_id}"

    def como_dict(self, puntaje: int = 0) -> dict[str, Any]:
        return {
            "fuente": self.fuente,
            "id": self.pago_id,
            "nombre": self.nombre,
            "fecha": self.fecha.isoformat(),
            "monto": f"{self.monto.quantize(CENT):.2f}",
            "socio": self.socio,
            "memo": self.memo,
            "puntaje": puntaje,
            "ya_conciliado": self.ya_conciliado,
        }


@dataclass(frozen=True)
class PropuestaCalculada:
    """Resultado determinístico del motor para un movimiento bancario."""

    movimiento_id: str
    huella: str
    tipo: str
    regla: str
    motivo: str
    fuente_pago: str = ""
    pago_id: str = ""
    pago_nombre: str = ""
    pago_socio: str = ""
    cuenta_id: str | None = None
    cuenta_codigo: str = ""
    puntaje: int = 0
    candidatos: list[dict[str, Any]] = field(default_factory=list)


def calcular_puntaje(
    m_fecha: date,
    m_ref: str,
    m_rifs: frozenset[str],
    pago: PagoCandidato,
) -> int:
    """Puntaje de afinidad entre un movimiento bancario y un pago candidato."""
    dias = abs((pago.fecha - m_fecha).days)
    puntaje = 3 if dias == 0 else (2 if dias == 1 else 1)

    ref = digitos_referencia(m_ref)
    if len(ref) >= 4:
        grupos_memo = [g.lstrip("0") for g in _NO_DIGITOS_RE.sub(" ", pago.memo).split() if g.lstrip("0")]
        if any(len(g) >= 4 and (ref.endswith(g) or g.endswith(ref)) for g in grupos_memo):
            puntaje += 3

    if m_rifs and (m_rifs & pago.partner_rifs):
        puntaje += 3

    return puntaje


def proponer_conciliacion(
    movimientos: Iterable[MovimientoParaConciliar],
    pagos: Iterable[PagoCandidato],
    reglas: ReglasCuentaConciliacion | None = None,
) -> list[PropuestaCalculada]:
    """Genera exactamente una propuesta por movimiento en orden cronológico determinístico."""
    cfg = reglas or ReglasCuentaConciliacion()
    ventana = timedelta(days=max(0, int(cfg.ventana_dias)))

    disponibles: dict[tuple[bool, Decimal], list[PagoCandidato]] = {}
    for p in pagos:
        monto_q = p.monto.quantize(CENT)
        disponibles.setdefault((p.entrante, monto_q), []).append(p)

    usados: set[str] = set()
    salida: list[PropuestaCalculada] = []

    ordenados = sorted(
        movimientos,
        key=lambda m: (m.fecha, m.orden, m.movimiento_id),
    )

    for m in ordenados:
        etiqueta_regla = m.regla_clasificacion or m.categoria or "extracto"

        # Regla R1: comisiones bancarias e IGTF
        if m.categoria in CATEGORIAS_COMISION and (cfg.cuenta_comisiones_id or cfg.cuenta_comisiones_codigo):
            salida.append(
                PropuestaCalculada(
                    movimiento_id=m.movimiento_id,
                    huella=m.huella,
                    tipo=TIPO_CUENTA,
                    regla="R1",
                    motivo=f"comisión ({etiqueta_regla})",
                    cuenta_id=cfg.cuenta_comisiones_id,
                    cuenta_codigo=cfg.cuenta_comisiones_codigo,
                )
            )
            continue

        if m.categoria in CATEGORIAS_IGTF and (cfg.cuenta_igtf_id or cfg.cuenta_igtf_codigo):
            salida.append(
                PropuestaCalculada(
                    movimiento_id=m.movimiento_id,
                    huella=m.huella,
                    tipo=TIPO_CUENTA,
                    regla="R1",
                    motivo=f"IGTF ({etiqueta_regla})",
                    cuenta_id=cfg.cuenta_igtf_id,
                    cuenta_codigo=cfg.cuenta_igtf_codigo,
                )
            )
            continue

        # Regla R2: emparejamiento contra pagos candidatos
        monto_mov = abs(m.monto).quantize(CENT)
        candidatos_rango = [
            p
            for p in disponibles.get((m.es_credito, monto_mov), [])
            if p.clave not in usados and abs(p.fecha - m.fecha) <= ventana
        ]
        m_rifs = rifs(m.descripcion) - cfg.rifs_propios_empresa
        puntuados = sorted(
            ((calcular_puntaje(m.fecha, m.referencia, m_rifs, p), p) for p in candidatos_rango),
            key=lambda par: (-par[0], par[1].fuente != "OMNI", par[1].clave),
        )

        if puntuados and (len(puntuados) == 1 or puntuados[0][0] > puntuados[1][0]):
            mejor_puntaje, mejor_pago = puntuados[0]
            usados.add(mejor_pago.clave)
            sufijo_conciliado = f" (ya conciliado en {mejor_pago.fuente})" if mejor_pago.ya_conciliado else ""
            salida.append(
                PropuestaCalculada(
                    movimiento_id=m.movimiento_id,
                    huella=m.huella,
                    tipo=TIPO_PAGO,
                    regla="R2",
                    motivo=(
                        f"pago {mejor_pago.nombre} de {len(puntuados)} candidato(s), "
                        f"puntaje {mejor_puntaje}{sufijo_conciliado}"
                    ),
                    fuente_pago=mejor_pago.fuente,
                    pago_id=mejor_pago.pago_id,
                    pago_nombre=mejor_pago.nombre,
                    pago_socio=mejor_pago.socio,
                    puntaje=mejor_puntaje,
                    candidatos=[q.como_dict(puntaje=pts) for pts, q in puntuados],
                )
            )
            continue

        if puntuados:
            empate_pts = puntuados[0][0]
            salida.append(
                PropuestaCalculada(
                    movimiento_id=m.movimiento_id,
                    huella=m.huella,
                    tipo=TIPO_AMBIGUO,
                    regla="R2",
                    motivo=f"{len(puntuados)} pagos empatan con puntaje {empate_pts}",
                    puntaje=empate_pts,
                    candidatos=[q.como_dict(puntaje=pts) for pts, q in puntuados],
                )
            )
            continue

        # Regla R3: POS / compra con tarjeta / nómina sin pago candidato -> cuenta tránsito
        if m.categoria in CATEGORIAS_PENDIENTES and (cfg.cuenta_transito_id or cfg.cuenta_transito_codigo):
            salida.append(
                PropuestaCalculada(
                    movimiento_id=m.movimiento_id,
                    huella=m.huella,
                    tipo=TIPO_CUENTA,
                    regla="R3",
                    motivo=f"{m.categoria} sin pago que la cierre",
                    cuenta_id=cfg.cuenta_transito_id,
                    cuenta_codigo=cfg.cuenta_transito_codigo,
                )
            )
            continue

        salida.append(
            PropuestaCalculada(
                movimiento_id=m.movimiento_id,
                huella=m.huella,
                tipo=TIPO_SIN_PROPUESTA,
                regla="-",
                motivo="sin pago candidato",
            )
        )

    return salida


# ── Guardián y lector de solo lectura para Odoo ───────────────────────────────


def solo_lectura(execute: ExecuteOdoo) -> ExecuteOdoo:
    """Envuelve el cliente XML-RPC de Odoo bloqueando cualquier método de escritura."""

    def _ejecutar(
        model: str,
        method: str,
        args: list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        if method not in METODOS_LECTURA_ODOO:
            raise PermissionError(f"Operación bloqueada: {model}.{method} no es de lectura.")
        return execute(model, method, args if args is not None else [[]], kwargs or {})

    return _ejecutar


def pagos_candidatos_odoo(
    execute: ExecuteOdoo,
    *,
    journal_id: int,
    desde: date,
    hasta: date,
    ventana_dias: int = VENTANA_DIAS_DEFAULT,
    excluir_ids: frozenset[str] = frozenset(),
    rifs_propios: frozenset[str] = frozenset(),
) -> list[PagoCandidato]:
    """Lee pagos publicados de Odoo en ``[desde - ventana, hasta + ventana]`` en modo solo lectura."""
    ex = solo_lectura(execute)
    ventana = timedelta(days=max(0, int(ventana_dias)))

    campos_modelo = ex("account.payment", "fields_get", [], {"attributes": ["type"]}) or {}
    campo_memo = "memo" if "memo" in campos_modelo else ("ref" if "ref" in campos_modelo else "")
    tiene_is_matched = "is_matched" in campos_modelo

    campos_lectura = ["id", "name", "date", "amount", "payment_type", "partner_id"]
    if campo_memo:
        campos_lectura.append(campo_memo)
    if tiene_is_matched:
        campos_lectura.append("is_matched")

    registros = ex(
        "account.payment",
        "search_read",
        [
            [
                ["journal_id", "=", int(journal_id)],
                ["date", ">=", (desde - ventana).isoformat()],
                ["date", "<=", (hasta + ventana).isoformat()],
                ["state", "in", ESTADOS_PAGO_ODOO],
            ]
        ],
        {"fields": campos_lectura},
    )
    if not isinstance(registros, list):
        return []

    socios_ids = sorted(
        {
            int(r["partner_id"][0])
            for r in registros
            if isinstance(r, dict) and isinstance(r.get("partner_id"), (list, tuple)) and len(r["partner_id"]) >= 1
        }
    )
    vats_por_socio: dict[int, frozenset[str]] = {}
    if socios_ids:
        socios_leidos = ex("res.partner", "read", [socios_ids], {"fields": ["vat"]}) or []
        for socio in socios_leidos:
            if not isinstance(socio, dict) or socio.get("id") is None or socio.get("id") is False:
                continue
            vat_limpio = str(socio.get("vat") or "") if socio.get("vat") else ""
            vats_por_socio[int(socio["id"])] = rifs(vat_limpio) - rifs_propios

    candidatos: list[PagoCandidato] = []
    for r in registros:
        if not isinstance(r, dict) or r.get("id") in (None, False):
            continue
        pid_str = str(int(r["id"]))
        if pid_str in excluir_ids:
            continue
        fecha_raw = r.get("date")
        monto_raw = r.get("amount")
        if not fecha_raw or isinstance(fecha_raw, bool) or monto_raw is None or isinstance(monto_raw, bool):
            continue
        try:
            fecha_pago = date.fromisoformat(str(fecha_raw)[:10])
            monto_pago = Decimal(str(monto_raw)).quantize(CENT)
        except (ValueError, InvalidOperation):
            continue
        if monto_pago <= Decimal("0.00"):
            continue
        partner_val = r.get("partner_id")
        tiene_partner_tupla = isinstance(partner_val, (list, tuple)) and len(partner_val) >= 1
        socio_id = int(partner_val[0]) if tiene_partner_tupla else None  # type: ignore[index]
        socio_nombre = (
            str(partner_val[1] or "")  # type: ignore[index]
            if isinstance(partner_val, (list, tuple)) and len(partner_val) >= 2
            else ""
        )
        memo_raw = r.get(campo_memo) if campo_memo else ""
        memo_val = str(memo_raw) if memo_raw and not isinstance(memo_raw, bool) else ""
        nombre_raw = r.get("name")
        nombre_val = str(nombre_raw) if nombre_raw and not isinstance(nombre_raw, bool) else f"ODOO-{pid_str}"
        candidatos.append(
            PagoCandidato(
                fuente="ODOO",
                pago_id=pid_str,
                nombre=nombre_val,
                fecha=fecha_pago,
                monto=monto_pago,
                entrante=r.get("payment_type") == "inbound",
                memo=memo_val,
                socio=socio_nombre,
                partner_rifs=vats_por_socio.get(socio_id, frozenset()) if socio_id else frozenset(),
                ya_conciliado=bool(r.get("is_matched")) if tiene_is_matched else False,
            )
        )
    return candidatos


def contactos_por_rif_odoo(
    execute: ExecuteOdoo,
    buscados: Iterable[str],
    *,
    rifs_propios: frozenset[str] = frozenset(),
) -> dict[str, str]:
    """Resuelve RIF/cédula -> nombre en Odoo cuando exactamente UN tercero lo posee."""
    ex = solo_lectura(execute)
    lista = sorted(set(buscados) - rifs_propios)
    if not lista:
        return {}

    cias_raw = ex("res.company", "search_read", [[]], {"fields": ["partner_id"]}) or []
    propios_ids = {
        int(c["partner_id"][0])
        for c in cias_raw
        if isinstance(c, dict) and isinstance(c.get("partner_id"), (list, tuple)) and len(c["partner_id"]) >= 1
    }

    por_rif: dict[str, dict[int, str]] = {}
    for i in range(0, len(lista), 200):
        bloque = [r for r in lista[i : i + 200] if len(r) >= 3]
        if not bloque:
            continue
        dominio: list[Any] = ["|"] * (len(bloque) - 1)
        dominio += [["vat", "ilike", r[1:-1]] for r in bloque]
        socios_raw = (
            ex(
                "res.partner",
                "search_read",
                [dominio],
                {"fields": ["id", "display_name", "vat"]},
            )
            or []
        )
        for socio in socios_raw:
            if not isinstance(socio, dict) or socio.get("id") in (None, False):
                continue
            sid = int(socio["id"])
            if sid in propios_ids:
                continue
            vat_raw = socio.get("vat")
            vat_txt = str(vat_raw) if vat_raw and not isinstance(vat_raw, bool) else ""
            disp_raw = socio.get("display_name")
            disp_txt = str(disp_raw) if disp_raw and not isinstance(disp_raw, bool) else ""
            for rif_norm in rifs(vat_txt) & set(bloque):
                por_rif.setdefault(rif_norm, {})[sid] = disp_txt

    return {r: next(iter(ids.values())) for r, ids in por_rif.items() if len(ids) == 1}
