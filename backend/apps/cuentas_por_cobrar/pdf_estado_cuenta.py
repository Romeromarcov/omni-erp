"""
M10-T2: PDF para Estado de Cuenta CxC.

Genera un estado de cuenta detallado de CuentaPorCobrar para un cliente.
Requiere reportlab: pip install reportlab
"""

from datetime import date

from django.utils import timezone


def generar_pdf_estado_cuenta(empresa, cliente, fecha_corte: date = None) -> bytes:
    """
    Genera PDF del estado de cuenta CxC de un cliente.

    Args:
        empresa:      instancia de Empresa.
        cliente:      instancia de Cliente.
        fecha_corte:  fecha hasta la cual incluir documentos (default: hoy).

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
    from decimal import Decimal

    from apps.cuentas_por_cobrar.models import CuentaPorCobrar

    # localdate() = hoy en TIME_ZONE (America/Caracas), no en UTC, para que el
    # corte por defecto coincida con el día local (no se adelante tras las 20:00).
    fecha_corte = fecha_corte or timezone.localdate()

    cxc_qs = CuentaPorCobrar.objects.filter(
        empresa=empresa,
        cliente=cliente,
        fecha_emision__lte=fecha_corte,
    ).order_by("fecha_vencimiento")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    story = []

    # ── Encabezado ────────────────────────────────────────────────────────────
    story.append(Paragraph(f"<b>{getattr(empresa, 'nombre_legal', str(empresa))}</b>", styles["Title"]))
    story.append(Paragraph(f"RIF: {getattr(empresa, 'identificador_fiscal', 'N/A')}", styles["Normal"]))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph("<b>ESTADO DE CUENTA</b>", styles["Heading1"]))
    story.append(Spacer(1, 0.2 * cm))

    nombre_cliente = getattr(cliente, "razon_social", str(cliente))
    rif_cliente = getattr(cliente, "rif", "")
    story.append(Paragraph(f"<b>Cliente:</b> {nombre_cliente}  |  <b>RIF:</b> {rif_cliente}", styles["Normal"]))
    story.append(Paragraph(f"<b>Fecha de Corte:</b> {fecha_corte}", styles["Normal"]))
    story.append(Spacer(1, 0.5 * cm))

    # ── Tabla de cuentas ──────────────────────────────────────────────────────
    encabezado = [["Referencia", "Emisión", "Vencimiento", "Monto", "Estado"]]
    filas = list(encabezado)

    total_pendiente = Decimal("0")
    total_vencido = Decimal("0")
    total_pagado = Decimal("0")

    for cxc in cxc_qs:
        ref = cxc.referencia_externa or str(cxc.pk)[:8]
        filas.append([
            ref,
            str(cxc.fecha_emision),
            str(cxc.fecha_vencimiento),
            f"{cxc.monto:,.2f}",
            cxc.estado.upper(),
        ])
        if cxc.estado in ("pendiente", "parcial"):
            total_pendiente += cxc.monto
            if cxc.fecha_vencimiento < fecha_corte:
                total_vencido += cxc.monto
        elif cxc.estado == "pagada":
            total_pagado += cxc.monto

    if len(filas) == 1:
        filas.append(["—", "—", "—", "Sin documentos", "—"])

    t_cxc = Table(filas, colWidths=[3.5 * cm, 3 * cm, 3 * cm, 3.5 * cm, 4 * cm])
    t_cxc.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkgreen),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("ALIGN", (4, 0), (4, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
    ]))
    story.append(t_cxc)
    story.append(Spacer(1, 0.5 * cm))

    # ── Resumen ───────────────────────────────────────────────────────────────
    story.append(Paragraph("<b>Resumen</b>", styles["Heading2"]))
    resumen = [
        ["Saldo Pendiente:", f"{total_pendiente:,.2f}"],
        ["Saldo Vencido:", f"{total_vencido:,.2f}"],
        ["Total Pagado:", f"{total_pagado:,.2f}"],
    ]
    t_res = Table(resumen, colWidths=[8 * cm, 5 * cm])
    t_res.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TEXTCOLOR", (0, 1), (1, 1), colors.red),  # vencido en rojo
    ]))
    story.append(t_res)

    doc.build(story)
    return buffer.getvalue()
