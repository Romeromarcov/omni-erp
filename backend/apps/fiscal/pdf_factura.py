"""
Generación de PDF para facturas fiscales venezolanas.

Cumple los requisitos legales del SENIAT:
  - Número de control
  - Número de factura
  - RIF emisor y receptor
  - Base imponible, alícuota IVA, monto IVA, total
  - Detalle de líneas
  - Pie legal venezolano

Requiere reportlab (ya en requirements.txt).
"""


def generar_pdf_factura(factura) -> bytes:
    """
    Genera un PDF completo para una FacturaFiscal venezolana.

    Args:
        factura: instancia de FacturaFiscal

    Returns:
        bytes del PDF generado

    Raises:
        ImportError: si reportlab no está instalado
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise ImportError(
            "reportlab no está instalado. Instálelo con: pip install reportlab"
        ) from exc

    import io
    from decimal import Decimal

    # ── Configuración del documento ───────────────────────────────────────────
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=2.5 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    AZUL_OSCURO = colors.HexColor("#003366")
    GRIS_CLARO = colors.HexColor("#f5f5f5")

    estilo_centro = ParagraphStyle("centro", parent=styles["Normal"], alignment=TA_CENTER)
    estilo_derecha = ParagraphStyle("derecha", parent=styles["Normal"], alignment=TA_RIGHT)
    estilo_titulo = ParagraphStyle(
        "titulo",
        parent=styles["Title"],
        fontSize=14,
        textColor=AZUL_OSCURO,
        spaceAfter=2,
    )
    estilo_subtitulo = ParagraphStyle(
        "subtitulo", parent=styles["Normal"], fontSize=10, textColor=AZUL_OSCURO, spaceAfter=2
    )
    estilo_pie = ParagraphStyle(
        "pie", parent=styles["Normal"], fontSize=7, textColor=colors.grey, alignment=TA_CENTER
    )

    elements = []

    # ── Datos de la empresa ───────────────────────────────────────────────────
    empresa = factura.id_empresa
    nombre_empresa = getattr(empresa, "nombre_legal", str(empresa))
    rif_empresa = getattr(empresa, "identificador_fiscal", "")
    direccion_empresa = getattr(empresa, "direccion_fiscal", "") or getattr(empresa, "direccion", "")

    # ── Datos del cliente ─────────────────────────────────────────────────────
    cliente = factura.id_cliente
    nombre_cliente = getattr(cliente, "razon_social", str(cliente))
    rif_cliente = getattr(cliente, "rif", "") or ""
    direccion_cliente = ""
    try:
        direccion_obj = cliente.direcciones.filter(activo=True).first()
        if direccion_obj:
            direccion_cliente = getattr(direccion_obj, "direccion", "")
    except Exception:
        pass

    # ══════════════════════════════════════════════════════════════════════════
    # BLOQUE 1: Encabezado empresa + número de factura (layout 2 columnas)
    # ══════════════════════════════════════════════════════════════════════════
    encabezado_empresa = [
        [Paragraph(f"<b>{nombre_empresa}</b>", estilo_titulo),
         Paragraph("<b>FACTURA</b>", ParagraphStyle("fac", parent=styles["Title"], fontSize=16, alignment=TA_CENTER, textColor=AZUL_OSCURO))],
        [Paragraph(f"RIF: <b>{rif_empresa}</b>", styles["Normal"]),
         Paragraph(f"N° Control: <b>{factura.numero_control}</b>", estilo_centro)],
        [Paragraph(direccion_empresa, ParagraphStyle("dir", parent=styles["Normal"], fontSize=8, textColor=colors.grey)),
         Paragraph(f"N° Factura: <b>{factura.numero_factura}</b>", estilo_centro)],
        ["",
         Paragraph(f"Fecha: <b>{factura.fecha_emision}</b>", estilo_centro)],
    ]

    t_enc = Table(encabezado_empresa, colWidths=[10 * cm, 7 * cm])
    t_enc.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (1, 0), (1, 0), 2, AZUL_OSCURO),
    ]))
    elements.append(t_enc)
    elements.append(Spacer(1, 0.3 * cm))
    elements.append(HRFlowable(width="100%", thickness=2, color=AZUL_OSCURO))
    elements.append(Spacer(1, 0.3 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOQUE 2: Datos del receptor (cliente)
    # ══════════════════════════════════════════════════════════════════════════
    receptor_data = [
        ["Cliente:", nombre_cliente],
        ["RIF Receptor:", rif_cliente],
        ["Dirección:", direccion_cliente or "—"],
    ]
    t_receptor = Table(receptor_data, colWidths=[3.5 * cm, 13.5 * cm])
    t_receptor.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_CLARO),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ]))
    elements.append(t_receptor)
    elements.append(Spacer(1, 0.4 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOQUE 3: Detalle de líneas
    # ══════════════════════════════════════════════════════════════════════════
    detalles = []
    try:
        detalles = list(factura.detalles.select_related("id_producto").all())
    except Exception:
        pass

    encab_det = [["#", "Producto / Descripción", "Cant.", "P. Unitario", "Subtotal"]]
    filas_det = list(encab_det)

    for i, det in enumerate(detalles, 1):
        producto = getattr(det, "id_producto", None)
        nombre_prod = getattr(producto, "nombre_producto", "—") if producto else "—"
        filas_det.append([
            str(i),
            nombre_prod,
            f"{getattr(det, 'cantidad', 0):,.2f}",
            f"{getattr(det, 'precio_unitario', 0):,.4f}",
            f"{getattr(det, 'subtotal', 0):,.2f}",
        ])

    if not detalles:
        filas_det.append(["—", "Sin líneas de detalle registradas", "—", "—", "—"])

    t_det = Table(filas_det, colWidths=[0.8 * cm, 9.7 * cm, 2 * cm, 2.5 * cm, 2 * cm])
    t_det.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL_OSCURO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.lightgrey),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_CLARO]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_det)
    elements.append(Spacer(1, 0.4 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOQUE 4: Totales (base imponible, IVA, total)
    # ══════════════════════════════════════════════════════════════════════════
    base_imponible = getattr(factura, "base_imponible", Decimal("0"))
    monto_iva = getattr(factura, "monto_iva", Decimal("0"))
    monto_total = getattr(factura, "monto_total", Decimal("0"))
    moneda = str(getattr(factura, "id_moneda", ""))

    # Calcular alícuota IVA
    try:
        alicuota = (monto_iva / base_imponible * 100).quantize(Decimal("0.00")) if base_imponible else Decimal("16.00")
    except Exception:
        alicuota = Decimal("16.00")

    totales_data = [
        ["Base Imponible:", f"{base_imponible:,.2f} {moneda}"],
        [f"IVA ({alicuota}%):", f"{monto_iva:,.2f} {moneda}"],
        ["TOTAL:", f"{monto_total:,.2f} {moneda}"],
    ]
    t_totales = Table(totales_data, colWidths=[13 * cm, 4 * cm])
    t_totales.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -2), 9),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, AZUL_OSCURO),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, -1), (-1, -1), 6),
        ("BACKGROUND", (0, -1), (-1, -1), GRIS_CLARO),
    ]))
    elements.append(t_totales)
    elements.append(Spacer(1, 0.5 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOQUE 5: Observaciones
    # ══════════════════════════════════════════════════════════════════════════
    observaciones = getattr(factura, "observaciones", "")
    if observaciones:
        elements.append(Paragraph(f"<b>Observaciones:</b> {observaciones}", styles["Normal"]))
        elements.append(Spacer(1, 0.3 * cm))

    # ══════════════════════════════════════════════════════════════════════════
    # BLOQUE 6: Pie legal venezolano
    # ══════════════════════════════════════════════════════════════════════════
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    elements.append(Spacer(1, 0.2 * cm))

    pie_texto = (
        "Documento fiscal emitido de conformidad con la Ley del IVA y su Reglamento. "
        f"Emisor: {nombre_empresa} — RIF: {rif_empresa}. "
        "La falsificación de facturas es penada por la ley (Art. 12 Ley del SENIAT). "
        "Conserve este documento como comprobante de la operación realizada."
    )
    elements.append(Paragraph(pie_texto, estilo_pie))

    doc.build(elements)
    return buffer.getvalue()
