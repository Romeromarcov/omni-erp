"""Exportadores CSV y PDF ReportLab para reportes contables canónicos (PR-14).

- CSV: UTF-8 con BOM (``\\ufeff``) para Excel y sanitización CWE-1236 contra
  inyección de fórmulas (``=``, ``+``, ``-``, ``@``, ``\\t``, ``\\r``) en campos
  de texto, preservando los montos decimales negativos legítimos.
- PDF: ReportLab con import perezoso (``ImportError`` controlado → HTTP 503).
"""

from __future__ import annotations

import csv
import html
import io
import re
from decimal import Decimal
from typing import Any

_PREFIJOS_FORMULA = ("=", "+", "-", "@", "\t", "\r")
_DECIMAL_PURO_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

_TIPOS_VALIDOS = frozenset(
    {
        "balance-comprobacion",
        "estado-resultados",
        "balance-general",
        "libro-mayor-auxiliar",
    }
)


def _normalizar_tipo_reporte(tipo_reporte: str) -> str:
    tipo = (tipo_reporte or "").strip().lower().replace("_", "-")
    if tipo not in _TIPOS_VALIDOS:
        raise ValueError(f"Tipo de reporte contable no soportado: {tipo_reporte!r}")
    return tipo


def _celda_texto(valor: Any) -> str:
    """Sanitiza valores textuales frente a formula injection en hojas de cálculo (CWE-1236)."""
    if valor is None:
        return ""
    texto = str(valor)
    if not texto:
        return ""
    limpio_izq = texto.lstrip(" ")
    if texto[0] in _PREFIJOS_FORMULA or (limpio_izq and limpio_izq[0] in _PREFIJOS_FORMULA):
        return "'" + texto
    return texto


def _celda_monto(valor: Any) -> str:
    """Formatea un monto decimal exacto con 2 decimales (sin float)."""
    if valor is None or valor == "":
        return ""
    if isinstance(valor, Decimal):
        return f"{valor:.2f}"
    texto = str(valor).strip()
    if _DECIMAL_PURO_RE.match(texto):
        return f"{Decimal(texto):.2f}"
    return _celda_texto(texto)


def _fmt_num(valor: Any) -> str:
    """Formatea un monto decimal con separador de miles para PDF."""
    if valor is None or valor == "":
        return "—"
    dec = valor if isinstance(valor, Decimal) else Decimal(str(valor))
    return f"{dec:,.2f}"


def _construir_filas_balance_comprobacion(data: dict[str, Any]) -> tuple[list[str], list[list[str]]]:
    con_usd = bool(data.get("usd_disponible"))
    headers = [
        "Código",
        "Cuenta",
        "Tipo",
        "Naturaleza",
        "Nivel",
        "Debe Inicial",
        "Haber Inicial",
        "Saldo Inicial",
        "Debe Período",
        "Haber Período",
        "Debe Acumulado",
        "Haber Acumulado",
        "Saldo Final",
    ]
    if con_usd:
        headers.extend(["Saldo Inicial USD", "Debe USD", "Haber USD", "Saldo Final USD"])

    rows: list[list[str]] = []
    for c in data.get("cuentas", []):
        fila = [
            _celda_texto(c.get("codigo_cuenta")),
            _celda_texto(c.get("nombre_cuenta", "")),
            _celda_texto(c.get("tipo_cuenta")),
            _celda_texto(c.get("naturaleza")),
            str(c.get("nivel", "")),
            _celda_monto(c.get("debe_inicial")),
            _celda_monto(c.get("haber_inicial")),
            _celda_monto(c.get("saldo_inicial")),
            _celda_monto(c.get("debe_periodo", c.get("debe"))),
            _celda_monto(c.get("haber_periodo", c.get("haber"))),
            _celda_monto(c.get("debe_final_acum")),
            _celda_monto(c.get("haber_final_acum")),
            _celda_monto(c.get("saldo")),
        ]
        if con_usd:
            fila.extend(
                [
                    _celda_monto(c.get("saldo_inicial_usd")),
                    _celda_monto(c.get("debe_usd")),
                    _celda_monto(c.get("haber_usd")),
                    _celda_monto(c.get("saldo_usd")),
                ]
            )
        rows.append(fila)

    totales = [
        "TOTALES",
        "",
        "",
        "",
        "",
        _celda_monto(data.get("total_debe_inicial")),
        _celda_monto(data.get("total_haber_inicial")),
        "",
        _celda_monto(data.get("total_debe")),
        _celda_monto(data.get("total_haber")),
        _celda_monto(data.get("total_debe_final_acum")),
        _celda_monto(data.get("total_haber_final_acum")),
        "",
    ]
    if con_usd:
        totales.extend(
            [
                "",
                _celda_monto(data.get("total_debe_usd")),
                _celda_monto(data.get("total_haber_usd")),
                "",
            ]
        )
    rows.append(totales)
    return headers, rows


def _construir_filas_estado_resultados(data: dict[str, Any]) -> tuple[list[str], list[list[str]]]:
    con_usd = bool(data.get("usd_disponible"))
    headers = ["Sección", "Código", "Cuenta", "Debe", "Haber", "Saldo Neto"]
    if con_usd:
        headers.append("Saldo Neto USD")

    rows: list[list[str]] = []

    def agregar_grupo(etiqueta: str, lista: list[dict[str, Any]], total_key: str, total_usd_key: str) -> None:
        for c in lista:
            fila = [
                etiqueta,
                _celda_texto(c.get("codigo_cuenta")),
                _celda_texto(c.get("nombre_cuenta", "")),
                _celda_monto(c.get("debe")),
                _celda_monto(c.get("haber")),
                _celda_monto(c.get("saldo")),
            ]
            if con_usd:
                fila.append(_celda_monto(c.get("saldo_usd")))
            rows.append(fila)
        sub = [f"Total {etiqueta}", "", "", "", "", _celda_monto(data.get(total_key))]
        if con_usd:
            sub.append(_celda_monto(data.get(total_usd_key)))
        rows.append(sub)

    agregar_grupo("INGRESO", data.get("ingresos", []), "total_ingresos", "total_ingresos_usd")
    agregar_grupo("COSTO", data.get("costos", []), "total_costos", "total_costos_usd")

    bruta = ["Utilidad Bruta", "", "", "", "", _celda_monto(data.get("utilidad_bruta"))]
    if con_usd:
        bruta.append(_celda_monto(data.get("utilidad_bruta_usd")))
    rows.append(bruta)

    agregar_grupo("GASTO", data.get("gastos", []), "total_gastos", "total_gastos_usd")

    neto = ["Resultado Neto", "", "", "", "", _celda_monto(data.get("resultado_neto"))]
    if con_usd:
        neto.append(_celda_monto(data.get("resultado_neto_usd")))
    rows.append(neto)
    return headers, rows


def _construir_filas_balance_general(data: dict[str, Any]) -> tuple[list[str], list[list[str]]]:
    con_usd = bool(data.get("usd_disponible"))
    headers = ["Sección", "Código", "Cuenta", "Debe", "Haber", "Saldo"]
    if con_usd:
        headers.append("Saldo USD")

    rows: list[list[str]] = []

    def agregar_grupo(etiqueta: str, lista: list[dict[str, Any]], total_key: str, total_usd_key: str) -> None:
        for c in lista:
            fila = [
                etiqueta,
                _celda_texto(c.get("codigo_cuenta")),
                _celda_texto(c.get("nombre_cuenta", "")),
                _celda_monto(c.get("debe")),
                _celda_monto(c.get("haber")),
                _celda_monto(c.get("saldo")),
            ]
            if con_usd:
                fila.append(_celda_monto(c.get("saldo_usd")))
            rows.append(fila)
        sub = [f"Total {etiqueta}", "", "", "", "", _celda_monto(data.get(total_key))]
        if con_usd:
            sub.append(_celda_monto(data.get(total_usd_key)))
        rows.append(sub)

    agregar_grupo("ACTIVO", data.get("activos", []), "total_activos", "total_activos_usd")
    agregar_grupo("PASIVO", data.get("pasivos", []), "total_pasivos", "total_pasivos_usd")
    agregar_grupo("PATRIMONIO", data.get("patrimonio", []), "total_patrimonio", "total_patrimonio_usd")

    res_per = ["Resultado del Período (No Cerrado)", "", "", "", "", _celda_monto(data.get("resultado_periodo"))]
    if con_usd:
        res_per.append(_celda_monto(data.get("resultado_periodo_usd")))
    rows.append(res_per)

    tot_pas_pat = [
        "Total Pasivo + Patrimonio + Resultado",
        "",
        "",
        "",
        "",
        _celda_monto(data.get("total_pasivo_patrimonio_y_resultado")),
    ]
    if con_usd:
        tot_pas_pat.append(_celda_monto(data.get("total_pasivo_patrimonio_y_resultado_usd")))
    rows.append(tot_pas_pat)

    ecuacion = ["Ecuación Cuadrada", "", "Sí" if data.get("ecuacion_cuadrada") else "No", "", "", ""]
    if con_usd:
        ecuacion.append("")
    rows.append(ecuacion)
    return headers, rows


def _construir_filas_libro_mayor(data: dict[str, Any]) -> tuple[list[str], list[list[str]]]:
    con_usd = bool(data.get("usd_disponible"))
    headers = [
        "Fecha",
        "Asiento",
        "Diario",
        "Código Cuenta",
        "Cuenta",
        "Contacto",
        "Descripción",
        "Debe",
        "Haber",
        "Saldo Corrido",
    ]
    if con_usd:
        headers.extend(["Debe USD", "Haber USD", "Saldo Corrido USD"])

    rows: list[list[str]] = []
    fila_inicial = [
        "",
        "SALDO INICIAL",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        _celda_monto(data.get("saldo_inicial")),
    ]
    if con_usd:
        fila_inicial.extend(["", "", _celda_monto(data.get("saldo_inicial_usd"))])
    rows.append(fila_inicial)

    for m in data.get("movimientos", []):
        desc = m.get("descripcion_detalle") or m.get("descripcion_asiento") or ""
        fila = [
            _celda_texto(m.get("fecha_asiento")),
            _celda_texto(m.get("numero_asiento")),
            _celda_texto(m.get("diario_codigo") or m.get("diario_nombre")),
            _celda_texto(m.get("codigo_cuenta")),
            _celda_texto(m.get("nombre_cuenta")),
            _celda_texto(m.get("contacto_nombre")),
            _celda_texto(desc),
            _celda_monto(m.get("debe")),
            _celda_monto(m.get("haber")),
            _celda_monto(m.get("saldo_corrido")),
        ]
        if con_usd:
            fila.extend(
                [
                    _celda_monto(m.get("debe_usd")),
                    _celda_monto(m.get("haber_usd")),
                    _celda_monto(m.get("saldo_corrido_usd")),
                ]
            )
        rows.append(fila)

    fila_final = [
        "",
        "TOTALES / SALDO FINAL",
        "",
        "",
        "",
        "",
        "",
        _celda_monto(data.get("total_debe")),
        _celda_monto(data.get("total_haber")),
        _celda_monto(data.get("saldo_final")),
    ]
    if con_usd:
        fila_final.extend(
            [
                _celda_monto(data.get("total_debe_usd")),
                _celda_monto(data.get("total_haber_usd")),
                _celda_monto(data.get("saldo_final_usd")),
            ]
        )
    rows.append(fila_final)
    return headers, rows


def exportar_reporte_csv(tipo_reporte: str, data: dict[str, Any]) -> bytes:
    """Exporta un reporte contable canónico a CSV UTF-8 con BOM y anti formula-injection."""
    tipo = _normalizar_tipo_reporte(tipo_reporte)

    if tipo == "balance-comprobacion":
        headers, rows = _construir_filas_balance_comprobacion(data)
    elif tipo == "estado-resultados":
        headers, rows = _construir_filas_estado_resultados(data)
    elif tipo == "balance-general":
        headers, rows = _construir_filas_balance_general(data)
    else:
        headers, rows = _construir_filas_libro_mayor(data)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _subtitulo_periodo_pdf(tipo: str, data: dict[str, Any]) -> str:
    if tipo == "balance-general":
        return f"Fecha de corte: {data.get('fecha_corte') or 'Al día'}"
    desde = data.get("fecha_desde") or "Inicio"
    hasta = data.get("fecha_hasta") or "Actual"
    partes = [f"Período: {desde} — {hasta}"]
    if tipo == "balance-comprobacion" and data.get("diario_nombre"):
        partes.append(f"Diario: {data['diario_nombre']}")
    if tipo == "libro-mayor-auxiliar":
        if data.get("cuenta_label"):
            partes.append(f"Cuenta: {data['cuenta_label']}")
        if data.get("contacto_label"):
            partes.append(f"Tercero: {data['contacto_label']}")
        if data.get("diario_label"):
            partes.append(f"Diario: {data['diario_label']}")
    return "  |  ".join(partes)


def exportar_reporte_pdf(
    tipo_reporte: str,
    data: dict[str, Any],
    *,
    empresa_nombre: str,
) -> bytes:
    """Genera el PDF ReportLab del reporte contable solicitado."""
    tipo = _normalizar_tipo_reporte(tipo_reporte)

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise ImportError("reportlab no está instalado. Instálelo con: pip install reportlab") from exc

    titulos = {
        "balance-comprobacion": "BALANCE DE COMPROBACIÓN",
        "estado-resultados": "ESTADO DE RESULTADOS (P&L)",
        "balance-general": "BALANCE GENERAL",
        "libro-mayor-auxiliar": "LIBRO MAYOR AUXILIAR",
    }

    con_usd = bool(data.get("usd_disponible"))
    es_apaisado = tipo in ("balance-comprobacion", "libro-mayor-auxiliar") or con_usd
    pagesize = landscape(A4) if es_apaisado else A4

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=1.3 * cm,
        rightMargin=1.3 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title=titulos[tipo],
    )

    styles = getSampleStyleSheet()
    azul = colors.HexColor("#1a3a5c")
    gris = colors.HexColor("#f5f7fa")
    borde = colors.HexColor("#cfd8dc")

    titulo_style = ParagraphStyle(
        "ReporteTitulo", parent=styles["Heading1"], fontSize=14, textColor=azul, spaceAfter=4
    )
    empresa_style = ParagraphStyle("ReporteEmpresa", parent=styles["Heading2"], fontSize=11, spaceAfter=2)
    meta_style = ParagraphStyle(
        "ReporteMeta", parent=styles["Normal"], fontSize=8.5, textColor=colors.HexColor("#455a64"), spaceAfter=6
    )
    cell_style = ParagraphStyle("ReporteCell", parent=styles["Normal"], fontSize=7.5, leading=9.5)

    moneda_base = data.get("moneda_base") or "N/D"
    subtitulo_usd = ""
    if data.get("incluir_equivalentes_usd"):
        if con_usd and data.get("tasa_usd") is not None:
            subtitulo_usd = f"  |  USD disponible (Tasa: {data['tasa_usd']})"
        elif data.get("usd_mensaje"):
            subtitulo_usd = f"  |  USD: {data['usd_mensaje']}"

    elementos: list[Any] = [
        Paragraph(f"<b>{html.escape(empresa_nombre or 'Empresa', quote=False)}</b>", empresa_style),
        Paragraph(f"<b>{html.escape(titulos[tipo], quote=False)}</b>", titulo_style),
        Paragraph(
            html.escape(
                f"{_subtitulo_periodo_pdf(tipo, data)}  |  Moneda base: {moneda_base}{subtitulo_usd}",
                quote=False,
            ),
            meta_style,
        ),
        Spacer(1, 0.25 * cm),
    ]

    if tipo == "balance-comprobacion":
        headers = [
            "Código",
            "Cuenta",
            "Tipo",
            "Saldo Ini.",
            "Debe Per.",
            "Haber Per.",
            "Debe Acum.",
            "Haber Acum.",
            "Saldo Final",
        ]
        if con_usd:
            headers.extend(["Debe USD", "Haber USD", "Saldo USD"])
        tabla_data: list[list[Any]] = [headers]
        for c in data.get("cuentas", []):
            indent = "&nbsp;" * (2 * max(0, int(c.get("nivel", 1)) - 1))
            nombre_html = f"{indent}{html.escape(str(c.get('nombre_cuenta', '')), quote=False)}"
            fila: list[Any] = [
                str(c.get("codigo_cuenta", "")),
                Paragraph(nombre_html, cell_style),
                str(c.get("tipo_cuenta", "")),
                _fmt_num(c.get("saldo_inicial")),
                _fmt_num(c.get("debe_periodo", c.get("debe"))),
                _fmt_num(c.get("haber_periodo", c.get("haber"))),
                _fmt_num(c.get("debe_final_acum")),
                _fmt_num(c.get("haber_final_acum")),
                _fmt_num(c.get("saldo")),
            ]
            if con_usd:
                fila.extend([_fmt_num(c.get("debe_usd")), _fmt_num(c.get("haber_usd")), _fmt_num(c.get("saldo_usd"))])
            tabla_data.append(fila)
        fila_tot: list[Any] = [
            "TOTALES",
            "",
            "",
            "—",
            _fmt_num(data.get("total_debe")),
            _fmt_num(data.get("total_haber")),
            _fmt_num(data.get("total_debe_final_acum")),
            _fmt_num(data.get("total_haber_final_acum")),
            "—",
        ]
        if con_usd:
            fila_tot.extend([_fmt_num(data.get("total_debe_usd")), _fmt_num(data.get("total_haber_usd")), "—"])
        tabla_data.append(fila_tot)
        col_widths = (
            [
                1.8 * cm,
                4.8 * cm,
                1.7 * cm,
                2.0 * cm,
                2.0 * cm,
                2.0 * cm,
                2.0 * cm,
                2.0 * cm,
                2.0 * cm,
                1.8 * cm,
                1.8 * cm,
                1.8 * cm,
            ]
            if con_usd
            else [2.0 * cm, 6.5 * cm, 1.9 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm]
        )
        num_start_col = 3
    elif tipo == "estado-resultados":
        headers = ["Sección", "Código", "Cuenta", "Saldo"] + (["Saldo USD"] if con_usd else [])
        tabla_data = [headers]
        for etiqueta, lista, tot_k, tot_usd_k in (
            ("INGRESO", data.get("ingresos", []), "total_ingresos", "total_ingresos_usd"),
            ("COSTO", data.get("costos", []), "total_costos", "total_costos_usd"),
            ("GASTO", data.get("gastos", []), "total_gastos", "total_gastos_usd"),
        ):
            for c in lista:
                indent = "&nbsp;" * (2 * max(0, int(c.get("nivel", 1)) - 1))
                fila = [
                    etiqueta,
                    str(c.get("codigo_cuenta", "")),
                    Paragraph(f"{indent}{html.escape(str(c.get('nombre_cuenta', '')), quote=False)}", cell_style),
                    _fmt_num(c.get("saldo")),
                ]
                if con_usd:
                    fila.append(_fmt_num(c.get("saldo_usd")))
                tabla_data.append(fila)
            sub = [f"Total {etiqueta}", "", "", _fmt_num(data.get(tot_k))]
            if con_usd:
                sub.append(_fmt_num(data.get(tot_usd_k)))
            tabla_data.append(sub)
        bruta = ["Utilidad Bruta", "", "", _fmt_num(data.get("utilidad_bruta"))]
        if con_usd:
            bruta.append(_fmt_num(data.get("utilidad_bruta_usd")))
        tabla_data.append(bruta)
        neto = ["RESULTADO NETO", "", "", _fmt_num(data.get("resultado_neto"))]
        if con_usd:
            neto.append(_fmt_num(data.get("resultado_neto_usd")))
        tabla_data.append(neto)
        col_widths = (
            [3.5 * cm, 2.8 * cm, 12.0 * cm, 4.0 * cm, 4.0 * cm]
            if con_usd
            else [3.2 * cm, 2.6 * cm, 8.6 * cm, 3.6 * cm]
        )
        num_start_col = 3
    elif tipo == "balance-general":
        headers = ["Sección", "Código", "Cuenta", "Saldo"] + (["Saldo USD"] if con_usd else [])
        tabla_data = [headers]
        for etiqueta, lista, tot_k, tot_usd_k in (
            ("ACTIVO", data.get("activos", []), "total_activos", "total_activos_usd"),
            ("PASIVO", data.get("pasivos", []), "total_pasivos", "total_pasivos_usd"),
            ("PATRIMONIO", data.get("patrimonio", []), "total_patrimonio", "total_patrimonio_usd"),
        ):
            for c in lista:
                indent = "&nbsp;" * (2 * max(0, int(c.get("nivel", 1)) - 1))
                fila = [
                    etiqueta,
                    str(c.get("codigo_cuenta", "")),
                    Paragraph(f"{indent}{html.escape(str(c.get('nombre_cuenta', '')), quote=False)}", cell_style),
                    _fmt_num(c.get("saldo")),
                ]
                if con_usd:
                    fila.append(_fmt_num(c.get("saldo_usd")))
                tabla_data.append(fila)
            sub = [f"Total {etiqueta}", "", "", _fmt_num(data.get(tot_k))]
            if con_usd:
                sub.append(_fmt_num(data.get(tot_usd_k)))
            tabla_data.append(sub)
        res_p = ["Resultado No Cerrado", "", "", _fmt_num(data.get("resultado_periodo"))]
        if con_usd:
            res_p.append(_fmt_num(data.get("resultado_periodo_usd")))
        tabla_data.append(res_p)
        tot_eq = ["Pasivo + Patrimonio + Resultado", "", "", _fmt_num(data.get("total_pasivo_patrimonio_y_resultado"))]
        if con_usd:
            tot_eq.append(_fmt_num(data.get("total_pasivo_patrimonio_y_resultado_usd")))
        tabla_data.append(tot_eq)
        col_widths = (
            [4.2 * cm, 2.8 * cm, 11.3 * cm, 4.0 * cm, 4.0 * cm]
            if con_usd
            else [4.0 * cm, 2.5 * cm, 8.1 * cm, 3.6 * cm]
        )
        num_start_col = 3
    else:
        headers = ["Fecha", "Asiento", "Diario", "Cuenta", "Contacto", "Detalle", "Debe", "Haber", "Saldo"]
        if con_usd:
            headers.extend(["Debe USD", "Haber USD", "Saldo USD"])
        tabla_data = [headers]
        ini_row: list[Any] = ["", "SALDO INICIAL", "", "", "", "", "", "", _fmt_num(data.get("saldo_inicial"))]
        if con_usd:
            ini_row.extend(["", "", _fmt_num(data.get("saldo_inicial_usd"))])
        tabla_data.append(ini_row)
        for m in data.get("movimientos", []):
            cuenta_txt = f"{m.get('codigo_cuenta', '')} {m.get('nombre_cuenta', '')}".strip()
            desc_txt = m.get("descripcion_detalle") or m.get("descripcion_asiento") or ""
            fila = [
                str(m.get("fecha_asiento", "")),
                Paragraph(html.escape(str(m.get("numero_asiento", "")), quote=False), cell_style),
                str(m.get("diario_codigo") or m.get("diario_nombre") or "—"),
                Paragraph(html.escape(cuenta_txt, quote=False), cell_style),
                Paragraph(html.escape(str(m.get("contacto_nombre") or "—"), quote=False), cell_style),
                Paragraph(html.escape(str(desc_txt), quote=False), cell_style),
                _fmt_num(m.get("debe")),
                _fmt_num(m.get("haber")),
                _fmt_num(m.get("saldo_corrido")),
            ]
            if con_usd:
                fila.extend(
                    [
                        _fmt_num(m.get("debe_usd")),
                        _fmt_num(m.get("haber_usd")),
                        _fmt_num(m.get("saldo_corrido_usd")),
                    ]
                )
            tabla_data.append(fila)
        fin_row: list[Any] = [
            "",
            "TOTALES",
            "",
            "",
            "",
            "",
            _fmt_num(data.get("total_debe")),
            _fmt_num(data.get("total_haber")),
            _fmt_num(data.get("saldo_final")),
        ]
        if con_usd:
            fin_row.extend(
                [
                    _fmt_num(data.get("total_debe_usd")),
                    _fmt_num(data.get("total_haber_usd")),
                    _fmt_num(data.get("saldo_final_usd")),
                ]
            )
        tabla_data.append(fin_row)
        col_widths = (
            [
                1.8 * cm,
                2.2 * cm,
                1.5 * cm,
                3.4 * cm,
                2.6 * cm,
                4.2 * cm,
                1.9 * cm,
                1.9 * cm,
                2.1 * cm,
                1.7 * cm,
                1.7 * cm,
                1.8 * cm,
            ]
            if con_usd
            else [2.0 * cm, 2.4 * cm, 1.8 * cm, 4.0 * cm, 3.2 * cm, 5.2 * cm, 2.4 * cm, 2.4 * cm, 2.6 * cm]
        )
        num_start_col = 6

    estilos_tabla: list[tuple[Any, ...]] = [
        ("BACKGROUND", (0, 0), (-1, 0), azul),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e3ecf5")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (num_start_col, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.35, borde),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    if len(tabla_data) > 2:
        estilos_tabla.append(("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, gris]))

    tabla = Table(tabla_data, colWidths=col_widths, repeatRows=1)
    tabla.setStyle(TableStyle(estilos_tabla))
    elementos.append(tabla)

    if tipo == "balance-general":
        elementos.append(Spacer(1, 0.3 * cm))
        estado_eq = "CUADRADA" if data.get("ecuacion_cuadrada") else "DESCUADRADA"
        elementos.append(
            Paragraph(
                f"<b>Verificación Ecuación Patrimonial:</b> {estado_eq} "
                f"(Activos = {_fmt_num(data.get('total_activos'))} vs "
                f"Pasivo + Patrimonio + Resultado = {_fmt_num(data.get('total_pasivo_patrimonio_y_resultado'))})",
                meta_style,
            )
        )

    doc.build(elementos)
    return buffer.getvalue()
