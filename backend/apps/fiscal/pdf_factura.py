"""
Generación de PDF para facturas fiscales venezolanas.
Requiere reportlab: pip install reportlab
"""


def generar_pdf_factura(factura) -> bytes:
    """
    Genera un PDF para una FacturaFiscal.

    Args:
        factura: instancia de FacturaFiscal

    Returns:
        bytes del PDF generado

    Raises:
        ImportError: si reportlab no está instalado
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise ImportError(
            "reportlab no está instalado. Instálelo con: pip install reportlab"
        ) from exc

    import io

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    elements = []

    # ── Encabezado empresa ────────────────────────────────────────────────────
    empresa = factura.id_empresa
    nombre_empresa = getattr(empresa, "nombre_legal", str(empresa))
    rif_empresa = getattr(empresa, "identificador_fiscal", "")

    elements.append(Paragraph(f"<b>{nombre_empresa}</b>", styles["Title"]))
    elements.append(Paragraph(f"RIF: {rif_empresa}", styles["Normal"]))
    elements.append(Spacer(1, 0.5 * cm))

    # ── Datos de la factura ───────────────────────────────────────────────────
    elements.append(Paragraph(f"<b>FACTURA FISCAL</b>", styles["Heading2"]))
    factura_data = [
        ["N° Control:", factura.numero_control],
        ["N° Factura:", factura.numero_factura],
        ["Fecha Emisión:", str(factura.fecha_emision)],
    ]

    # Cliente info
    cliente = factura.id_cliente
    nombre_cliente = getattr(cliente, "nombre_cliente", str(cliente))
    rif_cliente = getattr(cliente, "identificador_fiscal", "") or ""
    factura_data.append(["Cliente:", nombre_cliente])
    if rif_cliente:
        factura_data.append(["RIF Cliente:", rif_cliente])

    header_table = Table(factura_data, colWidths=[4 * cm, 12 * cm])
    header_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.lightgrey]),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.5 * cm))

    # ── Detalles (líneas) ─────────────────────────────────────────────────────
    detalles = list(factura.detalles.select_related("id_producto")) if hasattr(factura, "detalles") else []

    if detalles:
        items_data = [["Producto", "Cantidad", "Precio Unit.", "Subtotal"]]
        for detalle in detalles:
            producto = getattr(detalle, "id_producto", None)
            nombre_prod = getattr(producto, "nombre_producto", "—") if producto else "—"
            items_data.append([
                nombre_prod,
                str(getattr(detalle, "cantidad", "")),
                str(getattr(detalle, "precio_unitario", "")),
                str(getattr(detalle, "subtotal", "")),
            ])
        items_table = Table(items_data, colWidths=[8 * cm, 2.5 * cm, 3 * cm, 3 * cm])
        items_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 0.5 * cm))

    # ── Totales ───────────────────────────────────────────────────────────────
    totales_data = [
        ["Base Imponible:", f"{factura.base_imponible:,.2f}"],
        ["IVA:", f"{factura.monto_iva:,.2f}"],
        ["TOTAL:", f"{factura.monto_total:,.2f}"],
    ]
    totales_table = Table(totales_data, colWidths=[12 * cm, 4 * cm])
    totales_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
    ]))
    elements.append(totales_table)

    doc.build(elements)
    return buffer.getvalue()
