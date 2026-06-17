"""
M10-T2: PDF para Nota de Entrega (Despacho).

Genera un documento PDF profesional para un Despacho/Nota de Entrega.
Requiere reportlab: pip install reportlab
"""


def generar_pdf_nota_entrega(despacho) -> bytes:
    """
    Genera PDF de una Nota de Entrega.

    Args:
        despacho: instancia de Despacho (apps.despacho.models.Despacho)

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

    empresa = despacho.id_empresa

    # ── Encabezado ────────────────────────────────────────────────────────────
    story.append(Paragraph(f"<b>{getattr(empresa, 'nombre_legal', str(empresa))}</b>", styles["Title"]))
    story.append(Paragraph(f"RIF: {getattr(empresa, 'identificador_fiscal', 'N/A')}", styles["Normal"]))
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph("<b>NOTA DE ENTREGA</b>", styles["Heading1"]))
    story.append(Spacer(1, 0.3 * cm))

    # ── Datos del despacho ────────────────────────────────────────────────────
    fecha_despacho = despacho.fecha_despacho
    if hasattr(fecha_despacho, "date"):
        fecha_despacho = fecha_despacho.date()

    fecha_entrega = despacho.fecha_entrega_real or despacho.fecha_entrega_estimada
    if fecha_entrega and hasattr(fecha_entrega, "date"):
        fecha_entrega = fecha_entrega.date()

    datos_doc = [
        ["N° Despacho:", despacho.numero_despacho],
        ["Fecha Despacho:", str(fecha_despacho)],
        ["Fecha Entrega:", str(fecha_entrega) if fecha_entrega else "Por confirmar"],
        ["Estado:", despacho.estado_despacho],
        ["Almacén Origen:", despacho.id_almacen_origen.nombre_almacen],
        ["Dirección Destino:", despacho.direccion_destino],
    ]
    t_doc = Table(datos_doc, colWidths=[5 * cm, 12 * cm])
    t_doc.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_doc)
    story.append(Spacer(1, 0.5 * cm))

    # ── Documentos vinculados ─────────────────────────────────────────────────
    nota_venta = getattr(despacho, "id_nota_venta", None)
    if nota_venta:
        story.append(Paragraph(
            f"<b>Nota de venta de referencia:</b> {nota_venta}",
            styles["Normal"],
        ))
        story.append(Spacer(1, 0.3 * cm))
    if despacho.id_pedido:
        story.append(Paragraph(
            f"<b>Pedido de referencia:</b> {despacho.id_pedido}",
            styles["Normal"],
        ))
        story.append(Spacer(1, 0.3 * cm))

    # ── Líneas de detalle ─────────────────────────────────────────────────────
    story.append(Paragraph("<b>Productos Despachados</b>", styles["Heading2"]))
    encabezado = [["#", "Producto", "Cantidad", "Unidad", "Lote"]]
    filas = list(encabezado)

    detalles = list(despacho.detalles.select_related("id_producto", "id_unidad_medida").all()
                    if hasattr(despacho, "detalles") else [])
    for i, det in enumerate(detalles, 1):
        nombre_prod = getattr(getattr(det, "id_producto", None), "nombre_producto", str(det))
        unidad = getattr(getattr(det, "id_unidad_medida", None), "abreviatura", "UN")
        filas.append([
            str(i),
            nombre_prod,
            str(det.cantidad_despachada),
            unidad,
            det.lote or "-",
        ])

    if not detalles:
        filas.append(["-", "Sin ítems registrados", "-", "-", "-"])

    t_det = Table(filas, colWidths=[1 * cm, 9 * cm, 2.5 * cm, 2.5 * cm, 3 * cm])
    t_det.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
    ]))
    story.append(t_det)
    story.append(Spacer(1, 1 * cm))

    # ── Firma ─────────────────────────────────────────────────────────────────
    t_firma = Table(
        [["____________________________", "____________________________"],
         ["Firma Receptor", "Firma Transportista / Empresa"]],
        colWidths=[9 * cm, 9 * cm],
    )
    t_firma.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 1), (-1, 1), 4),
    ]))
    story.append(t_firma)

    if despacho.observaciones:
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph(f"<i>Obs: {despacho.observaciones}</i>", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()
