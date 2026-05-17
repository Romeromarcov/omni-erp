"""
Generación de libros fiscales en formato SENIAT (TXT delimitado por pipes).

Formato de cada línea:
  RIF_EMISOR|RIF_RECEPTOR|FECHA|NRO_CTRL|NRO_FAC|BASE_IMPONIBLE|IVA|TOTAL
"""


def generar_libro_ventas_txt(empresa, fecha_inicio, fecha_fin) -> str:
    """
    Genera el libro de ventas en formato SENIAT TXT.

    Args:
        empresa: instancia Empresa (emisor)
        fecha_inicio: date
        fecha_fin: date

    Returns:
        str con cada línea separada por newline
    """
    from apps.ventas.models import FacturaFiscal

    rif_emisor = getattr(empresa, "identificador_fiscal", "") or ""

    facturas = FacturaFiscal.objects.filter(
        id_empresa=empresa,
        fecha_emision__gte=fecha_inicio,
        fecha_emision__lte=fecha_fin,
        estado__in=["EMITIDA", "PAGADA", "VENCIDA"],
    ).select_related("id_cliente").order_by("fecha_emision", "numero_control")

    lineas = []
    for f in facturas:
        cliente = f.id_cliente
        rif_receptor = getattr(cliente, "identificador_fiscal", "") or ""
        linea = "|".join([
            rif_emisor,
            rif_receptor,
            str(f.fecha_emision),
            f.numero_control,
            f.numero_factura,
            f"{f.base_imponible:.2f}",
            f"{f.monto_iva:.2f}",
            f"{f.monto_total:.2f}",
        ])
        lineas.append(linea)

    return "\n".join(lineas)


def generar_libro_compras_txt(empresa, fecha_inicio, fecha_fin) -> str:
    """
    Genera el libro de compras en formato SENIAT TXT.

    Args:
        empresa: instancia Empresa (receptor/comprador)
        fecha_inicio: date
        fecha_fin: date

    Returns:
        str con cada línea separada por newline
    """
    # Importamos facturas de proveedor si existe ese modelo;
    # si no, devolvemos vacío con cabecera de aviso.
    try:
        from apps.compras.models import FacturaProveedor  # type: ignore

        rif_receptor = getattr(empresa, "identificador_fiscal", "") or ""

        facturas = FacturaProveedor.objects.filter(
            id_empresa=empresa,
            fecha_emision__gte=fecha_inicio,
            fecha_emision__lte=fecha_fin,
        ).select_related("id_proveedor").order_by("fecha_emision")

        lineas = []
        for f in facturas:
            proveedor = f.id_proveedor
            rif_emisor = getattr(proveedor, "identificador_fiscal", "") or ""
            base = getattr(f, "base_imponible", 0)
            iva = getattr(f, "monto_iva", 0)
            total = getattr(f, "monto_total", 0)
            nro_ctrl = getattr(f, "numero_control", "")
            nro_fac = getattr(f, "numero_factura", "")
            fecha = getattr(f, "fecha_emision", "")
            linea = "|".join([
                rif_emisor,
                rif_receptor,
                str(fecha),
                str(nro_ctrl),
                str(nro_fac),
                f"{base:.2f}",
                f"{iva:.2f}",
                f"{total:.2f}",
            ])
            lineas.append(linea)

        return "\n".join(lineas)

    except ImportError:
        return ""
