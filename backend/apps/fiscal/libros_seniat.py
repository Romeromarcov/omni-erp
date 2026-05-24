"""
Generación de libros fiscales en formato SENIAT.

TXT (pipe-delimited):
  RIF_EMISOR|RIF_RECEPTOR|FECHA|NRO_CTRL|NRO_FAC|BASE_IMPONIBLE|IVA|TOTAL

PDF: Tabla ReportLab con totales al pie.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal


# ── helpers ────────────────────────────────────────────────────────────────────

def _periodo_a_rango(periodo: str) -> tuple[date, date]:
    """Convierte 'YYYY-MM' en (date_inicio, date_fin) del mes completo."""
    try:
        año, mes = periodo.split("-")
        año, mes = int(año), int(mes)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Formato de período inválido: '{periodo}'. Use YYYY-MM.") from exc
    ultimo_dia = calendar.monthrange(año, mes)[1]
    return date(año, mes, 1), date(año, mes, ultimo_dia)


def _rif(obj, *campos) -> str:
    """Extrae el RIF del objeto probando varios nombres de campo."""
    for campo in campos:
        val = getattr(obj, campo, None)
        if val:
            return str(val)
    return ""


# ── TXT ventas ─────────────────────────────────────────────────────────────────

def generar_libro_ventas_txt(empresa, fecha_inicio: date, fecha_fin: date) -> str:
    """
    Genera el libro de ventas en formato SENIAT TXT (pipe-delimited).

    Cabecera:
        RIF_EMISOR|RIF_RECEPTOR|FECHA|NRO_CTRL|NRO_FAC|BASE_IMPONIBLE|IVA|TOTAL
    """
    from apps.ventas.models import FacturaFiscal

    rif_emisor = _rif(empresa, "identificador_fiscal", "rif")

    facturas = (
        FacturaFiscal.objects.filter(
            id_empresa=empresa,
            fecha_emision__gte=fecha_inicio,
            fecha_emision__lte=fecha_fin,
            estado__in=["EMITIDA", "PAGADA", "VENCIDA"],
        )
        .select_related("id_cliente")
        .order_by("fecha_emision", "numero_control")
    )

    cabecera = "RIF_EMISOR|RIF_RECEPTOR|FECHA|NRO_CTRL|NRO_FAC|BASE_IMPONIBLE|IVA|TOTAL"
    lineas = [cabecera]
    for f in facturas:
        cliente = f.id_cliente
        rif_receptor = _rif(cliente, "rif", "identificador_fiscal")
        lineas.append(
            "|".join(
                [
                    rif_emisor,
                    rif_receptor,
                    str(f.fecha_emision),
                    f.numero_control,
                    f.numero_factura,
                    f"{Decimal(str(f.base_imponible)):.2f}",
                    f"{Decimal(str(f.monto_iva)):.2f}",
                    f"{Decimal(str(f.monto_total)):.2f}",
                ]
            )
        )

    return "\n".join(lineas)


# ── TXT compras ────────────────────────────────────────────────────────────────

def generar_libro_compras_txt(empresa, fecha_inicio: date, fecha_fin: date) -> str:
    """
    Genera el libro de compras en formato SENIAT TXT (pipe-delimited).
    Si no existe el modelo FacturaProveedor devuelve solo la cabecera.
    """
    cabecera = "RIF_EMISOR|RIF_RECEPTOR|FECHA|NRO_CTRL|NRO_FAC|BASE_IMPONIBLE|IVA|TOTAL"

    try:
        from apps.compras.models import FacturaProveedor  # type: ignore
    except ImportError:
        return cabecera

    rif_receptor = _rif(empresa, "identificador_fiscal", "rif")

    facturas = (
        FacturaProveedor.objects.filter(
            id_empresa=empresa,
            fecha_emision__gte=fecha_inicio,
            fecha_emision__lte=fecha_fin,
        )
        .select_related("id_proveedor")
        .order_by("fecha_emision")
    )

    lineas = [cabecera]
    for f in facturas:
        proveedor = f.id_proveedor
        rif_emisor = _rif(proveedor, "identificador_fiscal", "rif")
        base = Decimal(str(getattr(f, "base_imponible", 0)))
        iva = Decimal(str(getattr(f, "monto_iva", 0)))
        total = Decimal(str(getattr(f, "monto_total", 0)))
        lineas.append(
            "|".join(
                [
                    rif_emisor,
                    rif_receptor,
                    str(getattr(f, "fecha_emision", "")),
                    str(getattr(f, "numero_control", "")),
                    str(getattr(f, "numero_factura", "")),
                    f"{base:.2f}",
                    f"{iva:.2f}",
                    f"{total:.2f}",
                ]
            )
        )

    return "\n".join(lineas)


# ── PDF helpers ────────────────────────────────────────────────────────────────

def _build_libro_pdf(
    *,
    titulo: str,
    empresa,
    fecha_inicio: date,
    fecha_fin: date,
    filas: list[list[str]],
) -> bytes:
    """Genera el PDF del libro fiscal con ReportLab."""
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=titulo,
    )

    styles = getSampleStyleSheet()
    AZUL = colors.HexColor("#1a3a5c")
    GRIS = colors.HexColor("#f5f5f5")

    titulo_style = ParagraphStyle(
        "Titulo",
        parent=styles["Heading1"],
        fontSize=14,
        textColor=AZUL,
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#555555"),
        spaceAfter=8,
    )

    nombre_empresa = getattr(empresa, "nombre_legal", None) or getattr(empresa, "nombre", "") or ""
    rif_empresa = _rif(empresa, "identificador_fiscal", "rif")
    periodo_str = f"{fecha_inicio.strftime('%d/%m/%Y')} — {fecha_fin.strftime('%d/%m/%Y')}"

    elementos = [
        Paragraph(titulo, titulo_style),
        Paragraph(f"{nombre_empresa}  |  RIF: {rif_empresa}  |  Período: {periodo_str}", sub_style),
        Spacer(1, 0.3 * cm),
    ]

    # Tabla de datos
    encabezados = ["RIF Emisor", "RIF Receptor", "Fecha", "N° Control", "N° Factura", "Base Imp.", "IVA", "Total"]
    data = [encabezados] + (filas if filas else [["(sin registros)", "", "", "", "", "", "", ""]])

    col_widths = [3.5 * cm, 3.5 * cm, 2.3 * cm, 2.8 * cm, 2.8 * cm, 3.2 * cm, 2.8 * cm, 3.2 * cm]
    tabla = Table(data, colWidths=col_widths, repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                # Encabezado
                ("BACKGROUND", (0, 0), (-1, 0), AZUL),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                # Datos
                ("FONTSIZE", (0, 1), (-1, -1), 7.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS]),
                ("ALIGN", (5, 1), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 1), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
            ]
        )
    )
    elementos.append(tabla)

    # Totales
    if filas:
        total_base = Decimal("0")
        total_iva = Decimal("0")
        total_total = Decimal("0")
        for fila in filas:
            try:
                total_base += Decimal(fila[5].replace(",", "."))
                total_iva += Decimal(fila[6].replace(",", "."))
                total_total += Decimal(fila[7].replace(",", "."))
            except Exception:
                pass

        elementos.append(Spacer(1, 0.4 * cm))
        resumen_data = [
            ["", "", "", "", "TOTALES:", f"{total_base:.2f}", f"{total_iva:.2f}", f"{total_total:.2f}"],
        ]
        resumen = Table(resumen_data, colWidths=col_widths)
        resumen.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ALIGN", (4, 0), (-1, 0), "RIGHT"),
                    ("TEXTCOLOR", (0, 0), (-1, 0), AZUL),
                ]
            )
        )
        elementos.append(resumen)

    # Pie SENIAT
    elementos.append(Spacer(1, 0.6 * cm))
    pie_style = ParagraphStyle("Pie", parent=styles["Normal"], fontSize=6.5, textColor=colors.HexColor("#888888"))
    elementos.append(
        Paragraph(
            "Libro generado de conformidad con el Artículo 76 de la Ley del IVA y "
            "la Providencia Administrativa SNAT/2011/0071. "
            "La adulteración de libros fiscales es sancionada por el Código Orgánico Tributario.",
            pie_style,
        )
    )

    doc.build(elementos)
    return buffer.getvalue()


# ── PDF ventas ─────────────────────────────────────────────────────────────────

def generar_libro_ventas_pdf(empresa, fecha_inicio: date, fecha_fin: date) -> bytes:
    """Genera el PDF del libro de ventas SENIAT."""
    from apps.ventas.models import FacturaFiscal

    rif_emisor = _rif(empresa, "identificador_fiscal", "rif")
    facturas = (
        FacturaFiscal.objects.filter(
            id_empresa=empresa,
            fecha_emision__gte=fecha_inicio,
            fecha_emision__lte=fecha_fin,
            estado__in=["EMITIDA", "PAGADA", "VENCIDA"],
        )
        .select_related("id_cliente")
        .order_by("fecha_emision", "numero_control")
    )

    filas = []
    for f in facturas:
        rif_receptor = _rif(f.id_cliente, "rif", "identificador_fiscal")
        filas.append(
            [
                rif_emisor,
                rif_receptor,
                str(f.fecha_emision),
                f.numero_control,
                f.numero_factura,
                f"{Decimal(str(f.base_imponible)):.2f}",
                f"{Decimal(str(f.monto_iva)):.2f}",
                f"{Decimal(str(f.monto_total)):.2f}",
            ]
        )

    nombre_empresa = getattr(empresa, "nombre_legal", None) or getattr(empresa, "nombre", "")
    return _build_libro_pdf(
        titulo=f"Libro de Ventas — {nombre_empresa}",
        empresa=empresa,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        filas=filas,
    )


# ── PDF compras ────────────────────────────────────────────────────────────────

def generar_libro_compras_pdf(empresa, fecha_inicio: date, fecha_fin: date) -> bytes:
    """Genera el PDF del libro de compras SENIAT."""
    rif_receptor = _rif(empresa, "identificador_fiscal", "rif")
    filas = []

    try:
        from apps.compras.models import FacturaProveedor  # type: ignore

        facturas = (
            FacturaProveedor.objects.filter(
                id_empresa=empresa,
                fecha_emision__gte=fecha_inicio,
                fecha_emision__lte=fecha_fin,
            )
            .select_related("id_proveedor")
            .order_by("fecha_emision")
        )

        for f in facturas:
            rif_emisor = _rif(f.id_proveedor, "identificador_fiscal", "rif")
            base = Decimal(str(getattr(f, "base_imponible", 0)))
            iva = Decimal(str(getattr(f, "monto_iva", 0)))
            total = Decimal(str(getattr(f, "monto_total", 0)))
            filas.append(
                [
                    rif_emisor,
                    rif_receptor,
                    str(getattr(f, "fecha_emision", "")),
                    str(getattr(f, "numero_control", "")),
                    str(getattr(f, "numero_factura", "")),
                    f"{base:.2f}",
                    f"{iva:.2f}",
                    f"{total:.2f}",
                ]
            )
    except ImportError:
        pass

    nombre_empresa = getattr(empresa, "nombre_legal", None) or getattr(empresa, "nombre", "")
    return _build_libro_pdf(
        titulo=f"Libro de Compras — {nombre_empresa}",
        empresa=empresa,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        filas=filas,
    )
