"""
M10-T2: PDF para Cotización.

Genera un documento PDF profesional para una Cotización de ventas.
Requiere reportlab: pip install reportlab
"""


def generar_pdf_cotizacion(cotizacion) -> bytes:
    """
    Genera PDF de una Cotización.

    Args:
        cotizacion: instancia de Cotizacion (apps.ventas.models.Cotizacion)

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
    story = []

    empresa = cotizacion.id_empresa
    cliente = cotizacion.id_cliente

    # ── Encabezado ────────────────────────────────────────────────────────────
    story.append(Paragraph(f"<b>{getattr(empresa, 'nombre_legal', str(empresa))}</b>", styles["Title"]))
    story.append(Paragraph(f"RIF: {getattr(empresa, 'identificador_fiscal', 'N/A')}", styles["Normal"]))
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph("<b>COTIZACIÓN DE VENTA</b>", styles["Heading1"]))
    story.append(Spacer(1, 0.3 * cm))

    # ── Datos del documento ───────────────────────────────────────────────────
    datos_doc = [
        ["N° Cotización:", cotizacion.numero_cotizacion],
        ["Fecha:", str(cotizacion.fecha_cotizacion)],
        ["Válida hasta:", str(cotizacion.fecha_vencimiento)],
        ["Estado:", cotizacion.estado],
        ["Moneda:", str(cotizacion.id_moneda)],
    ]
    t_doc = Table(datos_doc, colWidths=[5 * cm, 10 * cm])
    t_doc.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_doc)
    story.append(Spacer(1, 0.5 * cm))

    # ── Datos del cliente ─────────────────────────────────────────────────────
    story.append(Paragraph("<b>Cliente</b>", styles["Heading2"]))
    nombre_cliente = getattr(cliente, "razon_social", str(cliente))
    rif_cliente = getattr(cliente, "rif", "")
    datos_cli = [
        ["Razón Social:", nombre_cliente],
        ["RIF:", rif_cliente],
    ]
    t_cli = Table(datos_cli, colWidths=[5 * cm, 10 * cm])
    t_cli.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_cli)
    story.append(Spacer(1, 0.5 * cm))

    # ── Líneas de detalle ─────────────────────────────────────────────────────
    story.append(Paragraph("<b>Detalle</b>", styles["Heading2"]))
    encabezado = [["#", "Producto", "Cant.", "P. Unit.", "Subtotal"]]
    filas = list(encabezado)

    detalles = list(cotizacion.detalles.select_related("id_producto").all() if hasattr(cotizacion, "detalles") else [])
    for i, det in enumerate(detalles, 1):
        nombre_prod = getattr(getattr(det, "id_producto", None), "nombre_producto", str(det))
        filas.append([
            str(i),
            nombre_prod,
            str(det.cantidad),
            f"{det.precio_unitario:,.2f}",
            f"{det.subtotal:,.2f}",
        ])

    if not detalles:
        filas.append(["-", "Sin líneas de detalle", "-", "-", f"{cotizacion.monto_total:,.2f}"])

    t_det = Table(filas, colWidths=[1 * cm, 9 * cm, 2 * cm, 3 * cm, 3 * cm])
    t_det.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
    ]))
    story.append(t_det)
    story.append(Spacer(1, 0.5 * cm))

    # ── Total ─────────────────────────────────────────────────────────────────
    t_total = Table(
        [["TOTAL:", f"{cotizacion.monto_total:,.2f} {cotizacion.id_moneda}"]],
        colWidths=[14 * cm, 4 * cm],
    )
    t_total.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t_total)

    # ── Condiciones ───────────────────────────────────────────────────────────
    if cotizacion.condiciones_comerciales:
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("<b>Condiciones Comerciales:</b>", styles["Heading3"]))
        story.append(Paragraph(cotizacion.condiciones_comerciales, styles["Normal"]))

    if cotizacion.observaciones:
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(f"<i>Observaciones: {cotizacion.observaciones}</i>", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()
