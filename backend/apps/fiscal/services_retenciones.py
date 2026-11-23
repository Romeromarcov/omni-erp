"""Servicios SENIAT 360°: Retenciones IVA (.txt/PDF), ISLR (.xml/PDF), IGTF/ITF y Libro Inv. Art. 177."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from typing import Any

from django.db import transaction
from django.utils import timezone

_CERO = Decimal("0.0000")
_CIEN = Decimal("100")
_DOS_DEC = Decimal("0.01")
_CUATRO_DEC = Decimal("0.0001")
_PERIODO_RE = re.compile(r"^\d{6}$")

_TIPOS_ENTRADA = frozenset({"ENTRADA", "RECEPCION_COMPRA"})
_TIPOS_RETIRO = frozenset({"SALIDA_INTERNA"})
_TIPOS_SALIDA = frozenset({"SALIDA", "DESPACHO_VENTA", "CONSUMO_PRODUCCION"})


class RetencionFiscalError(ValueError):
    """Error de dominio en cálculo, emisión o exportación fiscal SENIAT."""


def _q2(val: Decimal | str | int | float) -> str:
    d = Decimal(str(val or "0")).quantize(_DOS_DEC, rounding=ROUND_HALF_UP)
    return f"{d:.2f}"


def _q4(val: Decimal | str | int | float) -> Decimal:
    return Decimal(str(val or "0")).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)


def _normalizar_rif(raw: str | None) -> str:
    limpio = re.sub(r"[^A-Za-z0-9]", "", str(raw or "")).upper()
    return limpio or "J000000000"


def _validar_periodo_yyyymm(periodo: str) -> str:
    limpio = str(periodo or "").strip()
    if not _PERIODO_RE.match(limpio):
        raise RetencionFiscalError(f"Período impositivo inválido '{periodo}'. Use formato AAAAMM (ej. 202611).")
    mes = int(limpio[4:6])
    if mes < 1 or mes > 12:
        raise RetencionFiscalError(f"Mes inválido en período '{periodo}'. Debe estar entre 01 y 12.")
    return limpio


def _generar_correlativo_comprobante(empresa, tipo_seq: str, periodo: str) -> str:
    from .services import siguiente_numero

    crudo = siguiente_numero(empresa, tipo_seq)
    digitos = re.sub(r"\D", "", crudo) or "1"
    sec = int(digitos[-8:])
    return f"{periodo}{sec:08d}"


@transaction.atomic
def emitir_retencion_iva(
    *,
    empresa,
    contacto,
    fecha_emision: date,
    numero_documento: str,
    base_imponible: Decimal,
    monto_total_documento: Decimal | None = None,
    monto_exento: Decimal = Decimal("0"),
    alicuota_iva: Decimal = Decimal("16.00"),
    monto_iva: Decimal | None = None,
    porcentaje_retencion: Decimal | None = None,
    numero_control: str = "",
    numero_documento_afectado: str = "0",
    tipo_operacion: str = "COMPRA",
    tipo_transaccion: str = "01",
    factura_compra=None,
    factura_venta=None,
    usuario=None,
):
    """Emite atómicamente un Comprobante de Retención de IVA con numeración AAAAMM00000001."""
    from apps.contabilidad.services import generar_asiento_o_fallar

    from .models import ComprobanteRetencionIVA
    from .services import PeriodoCerradoError, validar_periodo_abierto

    if getattr(contacto, "id_empresa_id", None) != empresa.pk:
        raise RetencionFiscalError("El contacto no pertenece a la empresa.")
    if factura_compra is not None and factura_compra.id_empresa_id != empresa.pk:
        raise RetencionFiscalError("La factura de compra no pertenece a la empresa.")
    if factura_venta is not None and factura_venta.id_empresa_id != empresa.pk:
        raise RetencionFiscalError("La factura de venta no pertenece a la empresa.")

    try:
        validar_periodo_abierto(empresa, fecha_emision)
    except PeriodoCerradoError as exc:
        raise RetencionFiscalError(str(exc)) from exc

    base_d = _q4(base_imponible)
    exento_d = _q4(monto_exento)
    alic_d = Decimal(str(alicuota_iva)).quantize(_DOS_DEC, rounding=ROUND_HALF_UP)
    if base_d < 0 or exento_d < 0:
        raise RetencionFiscalError("Los montos base y exento no pueden ser negativos.")

    iva_d = (
        _q4(monto_iva)
        if monto_iva is not None
        else (base_d * alic_d / _CIEN).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)
    )
    pct_ret = porcentaje_retencion
    if pct_ret is None:
        pct_cfg = getattr(contacto, "porcentaje_retencion_iva", None)
        pct_ret = Decimal(str(pct_cfg)) if pct_cfg and Decimal(str(pct_cfg)) > 0 else Decimal("75.00")
    pct_d = Decimal(str(pct_ret)).quantize(_DOS_DEC, rounding=ROUND_HALF_UP)
    if pct_d < 0 or pct_d > _CIEN:
        raise RetencionFiscalError("El porcentaje de retención IVA debe estar entre 0 y 100.")

    ret_d = (iva_d * pct_d / _CIEN).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)
    total_d = _q4(monto_total_documento) if monto_total_documento is not None else (base_d + exento_d + iva_d)

    periodo = f"{fecha_emision:%Y%m}"
    numero_comprobante = _generar_correlativo_comprobante(empresa, "RETENCION_IVA", periodo)
    tipo_op = str(tipo_operacion or "COMPRA").strip().upper()

    comp = ComprobanteRetencionIVA(
        id_empresa=empresa,
        numero_comprobante=numero_comprobante,
        tipo_operacion=tipo_op,
        contacto=contacto,
        factura_compra=factura_compra,
        factura_venta=factura_venta,
        fecha_emision=fecha_emision,
        periodo_impositivo=periodo,
        numero_documento=str(numero_documento).strip(),
        numero_control=str(numero_control or "").strip(),
        numero_documento_afectado=str(numero_documento_afectado or "0").strip() or "0",
        tipo_transaccion=str(tipo_transaccion or "01").strip(),
        monto_total_documento=total_d,
        monto_exento=exento_d,
        base_imponible=base_d,
        alicuota_iva=alic_d,
        monto_iva=iva_d,
        porcentaje_retencion=pct_d,
        monto_retenido=ret_d,
        estado="EMITIDO",
    )
    comp.full_clean()
    comp.save()

    if ret_d > 0:
        tipo_asiento = "RETENCION_IVA_COMPRA" if tipo_op == "COMPRA" else "RETENCION_IVA_VENTA"
        asiento, _err = generar_asiento_o_fallar(
            tipo_asiento,
            comp,
            empresa=empresa,
            monto=ret_d,
            usuario=usuario,
            ambito="FISCAL",
        )
        if asiento is not None:
            comp.asiento_contable = asiento
            comp.save(update_fields=["asiento_contable"])
    return comp


@transaction.atomic
def anular_retencion_iva(comprobante):
    from .models import ComprobanteRetencionIVA

    locked = ComprobanteRetencionIVA.objects.select_for_update().get(pk=comprobante.pk)
    if locked.estado == "ANULADO":
        raise RetencionFiscalError("El comprobante de retención IVA ya está anulado.")
    locked.estado = "ANULADO"
    locked.save(update_fields=["estado", "fecha_actualizacion"])
    return locked


def generar_txt_retenciones_iva_seniat(empresa, periodo_yyyymm: str) -> str:
    """Exporta archivo TXT SENIAT de 16 columnas separadas por tabulador."""
    from .models import ComprobanteRetencionIVA

    periodo = _validar_periodo_yyyymm(periodo_yyyymm)
    rif_agente = _normalizar_rif(getattr(empresa, "identificador_fiscal", None))
    qs = (
        ComprobanteRetencionIVA.objects.filter(
            id_empresa=empresa,
            periodo_impositivo=periodo,
            estado="EMITIDO",
            activo=True,
        )
        .select_related("contacto")
        .order_by("fecha_emision", "numero_comprobante")
    )

    lineas: list[str] = []
    for c in qs:
        tipo_op_txt = "C" if c.tipo_operacion == "COMPRA" else "V"
        rif_sujeto = _normalizar_rif(getattr(c.contacto, "rif", None))
        cols = [
            rif_agente,
            c.periodo_impositivo,
            c.fecha_emision.strftime("%Y-%m-%d"),
            tipo_op_txt,
            c.tipo_transaccion,
            rif_sujeto,
            c.numero_documento,
            c.numero_control or "0",
            _q2(c.monto_total_documento),
            _q2(c.base_imponible),
            _q2(c.monto_retenido),
            c.numero_documento_afectado or "0",
            c.numero_comprobante,
            _q2(c.monto_exento),
            _q2(c.alicuota_iva),
            "0",
        ]
        lineas.append("\t".join(cols))
    return "\n".join(lineas)


@transaction.atomic
def emitir_retencion_islr(
    *,
    empresa,
    contacto,
    concepto,
    fecha_emision: date,
    numero_factura: str,
    monto_operacion: Decimal,
    numero_control: str = "",
    factura_compra=None,
    valor_ut: Decimal | None = None,
    omitir_exencion: bool = False,
    usuario=None,
):
    """Emite atómicamente Comprobante de Retención ISLR con porcentaje/sustraendo Decreto 1808."""
    from apps.contabilidad.services import generar_asiento_o_fallar

    from .models import ComprobanteRetencionISLR, ConfiguracionFiscalEmpresa
    from .services import PeriodoCerradoError, validar_periodo_abierto

    if getattr(contacto, "id_empresa_id", None) != empresa.pk:
        raise RetencionFiscalError("El contacto no pertenece a la empresa.")
    if factura_compra is not None and factura_compra.id_empresa_id != empresa.pk:
        raise RetencionFiscalError("La factura de compra no pertenece a la empresa.")
    if getattr(contacto, "exento_islr", False) and not omitir_exencion:
        raise RetencionFiscalError("El sujeto retenido está marcado como exento de ISLR.")

    try:
        validar_periodo_abierto(empresa, fecha_emision)
    except PeriodoCerradoError as exc:
        raise RetencionFiscalError(str(exc)) from exc

    monto_d = _q4(monto_operacion)
    if monto_d <= 0:
        raise RetencionFiscalError("El monto de la operación debe ser mayor a cero.")

    if valor_ut is None:
        cfg = ConfiguracionFiscalEmpresa.objects.filter(id_empresa=empresa).first()
        ut_d = cfg.valor_unidad_tributaria if cfg is not None else Decimal("9.0000")
    else:
        ut_d = _q4(valor_ut)

    base_pct = Decimal(str(concepto.base_imponible_pct))
    pct_ret = Decimal(str(concepto.porcentaje_retencion))
    base_gravable = (monto_d * base_pct / _CIEN).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)

    sustraendo = _CERO
    if concepto.aplica_sustraendo and Decimal(str(concepto.factor_sustraendo_ut)) > 0:
        sustraendo = (Decimal(str(concepto.factor_sustraendo_ut)) * ut_d * (pct_ret / _CIEN)).quantize(
            _CUATRO_DEC, rounding=ROUND_HALF_UP
        )

    retenido = max(
        _CERO,
        (base_gravable * pct_ret / _CIEN - sustraendo).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP),
    )

    periodo = f"{fecha_emision:%Y%m}"
    numero_comprobante = _generar_correlativo_comprobante(empresa, "RETENCION_ISLR", periodo)

    comp = ComprobanteRetencionISLR(
        id_empresa=empresa,
        numero_comprobante=numero_comprobante,
        contacto=contacto,
        concepto=concepto,
        factura_compra=factura_compra,
        fecha_emision=fecha_emision,
        periodo_impositivo=periodo,
        numero_factura=str(numero_factura).strip(),
        numero_control=str(numero_control or "").strip(),
        monto_operacion=monto_d,
        valor_ut_aplicado=ut_d,
        sustraendo=sustraendo,
        porcentaje_retencion=pct_ret,
        monto_retenido=retenido,
        estado="EMITIDO",
    )
    comp.full_clean()
    comp.save()

    if retenido > 0:
        asiento, _err = generar_asiento_o_fallar(
            "RETENCION_ISLR",
            comp,
            empresa=empresa,
            monto=retenido,
            usuario=usuario,
            ambito="FISCAL",
        )
        if asiento is not None:
            comp.asiento_contable = asiento
            comp.save(update_fields=["asiento_contable"])
    return comp


@transaction.atomic
def anular_retencion_islr(comprobante):
    from .models import ComprobanteRetencionISLR

    locked = ComprobanteRetencionISLR.objects.select_for_update().get(pk=comprobante.pk)
    if locked.estado == "ANULADO":
        raise RetencionFiscalError("El comprobante de retención ISLR ya está anulado.")
    locked.estado = "ANULADO"
    locked.save(update_fields=["estado", "fecha_actualizacion"])
    return locked


def generar_xml_retenciones_islr_seniat(empresa, periodo_yyyymm: str) -> str:
    """Exporta XML SENIAT de relación mensual de retenciones ISLR."""
    from .models import ComprobanteRetencionISLR

    periodo = _validar_periodo_yyyymm(periodo_yyyymm)
    rif_agente = _normalizar_rif(getattr(empresa, "identificador_fiscal", None))

    root = ET.Element(
        "RelacionRetencionesISLR",
        attrib={"RifAgente": rif_agente, "Periodo": periodo},
    )
    qs = (
        ComprobanteRetencionISLR.objects.filter(
            id_empresa=empresa,
            periodo_impositivo=periodo,
            estado="EMITIDO",
            activo=True,
        )
        .select_related("contacto", "concepto")
        .order_by("fecha_emision", "numero_comprobante")
    )
    for c in qs:
        det = ET.SubElement(root, "DetalleRetencion")
        ET.SubElement(det, "RifRetenido").text = _normalizar_rif(getattr(c.contacto, "rif", None))
        ET.SubElement(det, "NumeroFactura").text = c.numero_factura
        ET.SubElement(det, "NumeroControl").text = c.numero_control or "0"
        ET.SubElement(det, "FechaOperacion").text = c.fecha_emision.strftime("%d/%m/%Y")
        ET.SubElement(det, "CodigoConcepto").text = c.concepto.codigo
        ET.SubElement(det, "MontoOperacion").text = _q2(c.monto_operacion)
        ET.SubElement(det, "PorcentajeRetencion").text = _q2(c.porcentaje_retencion)

    return ET.tostring(root, encoding="unicode")


def _render_comprobante_pdf(*, titulo: str, lineas: list[tuple[str, str]]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    pdf.setTitle(titulo)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, 740, titulo)
    pdf.line(50, 732, 560, 732)
    y = 706
    pdf.setFont("Helvetica", 10)
    for etiqueta, valor in lineas:
        pdf.drawString(50, y, f"{etiqueta}:")
        pdf.drawString(220, y, str(valor))
        y -= 20
        if y < 60:
            pdf.showPage()
            pdf.setFont("Helvetica", 10)
            y = 740
    pdf.save()
    return buf.getvalue()


def generar_pdf_comprobante_retencion_iva(comprobante) -> bytes:
    return _render_comprobante_pdf(
        titulo="COMPROBANTE DE RETENCIÓN DE IVA (SENIAT)",
        lineas=[
            ("Nro. Comprobante", comprobante.numero_comprobante),
            ("Período Impositivo", comprobante.periodo_impositivo),
            ("Fecha de Emisión", comprobante.fecha_emision.isoformat()),
            (
                "Agente de Retención",
                f"{comprobante.id_empresa.nombre_legal} ({_normalizar_rif(comprobante.id_empresa.identificador_fiscal)})",
            ),
            ("Sujeto Retenido", f"{comprobante.contacto.nombre} ({_normalizar_rif(comprobante.contacto.rif)})"),
            ("Documento / Control", f"{comprobante.numero_documento} / {comprobante.numero_control or 'N/A'}"),
            ("Monto Total Documento", _q2(comprobante.monto_total_documento)),
            ("Base Imponible", _q2(comprobante.base_imponible)),
            ("IVA Causado", _q2(comprobante.monto_iva)),
            ("% Retención", f"{_q2(comprobante.porcentaje_retencion)}%"),
            ("IVA Retenido", _q2(comprobante.monto_retenido)),
            ("Estado", comprobante.estado),
        ],
    )


def generar_pdf_comprobante_retencion_islr(comprobante) -> bytes:
    return _render_comprobante_pdf(
        titulo="COMPROBANTE DE RETENCIÓN DE ISLR (DECRETO 1808)",
        lineas=[
            ("Nro. Comprobante", comprobante.numero_comprobante),
            ("Período Impositivo", comprobante.periodo_impositivo),
            ("Fecha de Emisión", comprobante.fecha_emision.isoformat()),
            (
                "Agente de Retención",
                f"{comprobante.id_empresa.nombre_legal} ({_normalizar_rif(comprobante.id_empresa.identificador_fiscal)})",
            ),
            ("Sujeto Retenido", f"{comprobante.contacto.nombre} ({_normalizar_rif(comprobante.contacto.rif)})"),
            ("Concepto", f"{comprobante.concepto.codigo} - {comprobante.concepto.nombre}"),
            ("Factura / Control", f"{comprobante.numero_factura} / {comprobante.numero_control or 'N/A'}"),
            ("Monto Operación", _q2(comprobante.monto_operacion)),
            ("% Retención", f"{_q2(comprobante.porcentaje_retencion)}%"),
            ("Sustraendo Aplicado", _q2(comprobante.sustraendo)),
            ("ISLR Retenido", _q2(comprobante.monto_retenido)),
            ("Estado", comprobante.estado),
        ],
    )


def calcular_igtf_y_itf_bancario(
    monto: Decimal,
    moneda_iso: str,
    *,
    es_contribuyente_especial: bool = False,
    es_debito_bancario: bool = False,
    alicuota_igtf: Decimal = Decimal("3.00"),
    alicuota_itf: Decimal = Decimal("2.00"),
) -> dict[str, Any]:
    """Desglosa IGTF 3% (divisas/cripto) e ITF bancario 2% (débitos Bs de SPE)."""
    monto_d = _q4(monto)
    if monto_d < 0:
        raise RetencionFiscalError("El monto base para IGTF/ITF no puede ser negativo.")
    iso = str(moneda_iso or "USD").strip().upper()
    es_bolivar = iso in {"VES", "BS", "VEF", "VEB"}

    igtf_d = _CERO
    aplica_igtf = not es_bolivar and monto_d > 0
    if aplica_igtf:
        igtf_d = (monto_d * Decimal(str(alicuota_igtf)) / _CIEN).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)

    itf_d = _CERO
    aplica_itf = es_bolivar and es_contribuyente_especial and es_debito_bancario and monto_d > 0
    if aplica_itf:
        itf_d = (monto_d * Decimal(str(alicuota_itf)) / _CIEN).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)

    return {
        "moneda_iso": iso,
        "monto_base": monto_d,
        "aplica_igtf": aplica_igtf,
        "alicuota_igtf": Decimal(str(alicuota_igtf)).quantize(_DOS_DEC, rounding=ROUND_HALF_UP),
        "igtf": igtf_d,
        "aplica_itf_bancario": aplica_itf,
        "alicuota_itf_bancario": Decimal(str(alicuota_itf)).quantize(_DOS_DEC, rounding=ROUND_HALF_UP),
        "itf_bancario": itf_d,
        "total_impuestos": (igtf_d + itf_d).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP),
    }


def generar_libro_inventario_art177(empresa, fecha_inicio: date, fecha_fin: date) -> dict[str, Any]:
    """Libro de Inventario Fiscal (Art. 177 LISLR) usando únicamente movimientos ``ambito='FISCAL'``."""
    from apps.finanzas.services_trimonetario import TasaCambioError, obtener_tasa_por_tipo
    from apps.inventario.models import MovimientoInventario

    if fecha_inicio > fecha_fin:
        raise RetencionFiscalError("'fecha_inicio' no puede ser posterior a 'fecha_fin'.")

    tz = timezone.get_current_timezone()
    dt_inicio = timezone.make_aware(datetime.combine(fecha_inicio, time.min), tz)
    dt_fin = timezone.make_aware(datetime.combine(fecha_fin, time.max), tz)

    moneda_base = getattr(empresa, "id_moneda_base", None)
    moneda_pais = getattr(empresa, "id_moneda_pais", None) or moneda_base
    tasa_fiscal = Decimal("1.0000")
    if moneda_base is not None and moneda_pais is not None and moneda_base.pk != moneda_pais.pk:
        try:
            tasa_obj = obtener_tasa_por_tipo(
                moneda_base,
                moneda_pais,
                empresa=empresa,
                solo_oficial_fiscal=True,
                fecha=fecha_fin,
            )
            if tasa_obj is not None:
                tasa_fiscal = Decimal(str(tasa_obj.valor_tasa))
        except TasaCambioError:
            tasa_fiscal = Decimal("1.0000")

    movs = (
        MovimientoInventario.objects.filter(
            id_empresa=empresa,
            ambito="FISCAL",
            fecha_hora_movimiento__lte=dt_fin,
        )
        .select_related("id_producto")
        .order_by("fecha_hora_movimiento")
    )

    por_prod: dict[str, dict[str, Any]] = {}
    for m in movs:
        pid = str(m.id_producto_id)
        item = por_prod.setdefault(
            pid,
            {
                "id_producto": pid,
                "sku": getattr(m.id_producto, "sku", "") or "",
                "nombre_producto": m.id_producto.nombre_producto,
                "existencia_inicial": _CERO,
                "entradas": _CERO,
                "salidas": _CERO,
                "retiros_autoconsumo": _CERO,
                "costo_unitario_base": Decimal(str(getattr(m.id_producto, "costo_promedio", 0) or 0)),
            },
        )
        cant = Decimal(str(m.cantidad))
        es_previo = m.fecha_hora_movimiento < dt_inicio

        if m.tipo_movimiento in _TIPOS_ENTRADA:
            if es_previo:
                item["existencia_inicial"] += cant
            else:
                item["entradas"] += cant
        elif m.tipo_movimiento in _TIPOS_RETIRO:
            if es_previo:
                item["existencia_inicial"] -= cant
            else:
                item["retiros_autoconsumo"] += cant
        elif m.tipo_movimiento in _TIPOS_SALIDA:
            if es_previo:
                item["existencia_inicial"] -= cant
            else:
                item["salidas"] += cant
        elif m.tipo_movimiento == "AJUSTE":
            if es_previo:
                item["existencia_inicial"] += cant
            elif cant >= 0:
                item["entradas"] += cant
            else:
                item["salidas"] += abs(cant)

        if m.costo_unitario_movimiento is not None and not es_previo:
            item["costo_unitario_base"] = Decimal(str(m.costo_unitario_movimiento))

    filas: list[dict[str, Any]] = []
    valor_total_fiscal = _CERO
    for item in sorted(por_prod.values(), key=lambda x: x["nombre_producto"]):
        ex_final = (
            item["existencia_inicial"] + item["entradas"] - item["salidas"] - item["retiros_autoconsumo"]
        ).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)
        costo_fiscal = (item["costo_unitario_base"] * tasa_fiscal).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)
        val_final = (ex_final * costo_fiscal).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)
        valor_total_fiscal += val_final
        filas.append(
            {
                "id_producto": item["id_producto"],
                "sku": item["sku"],
                "nombre_producto": item["nombre_producto"],
                "existencia_inicial": str(item["existencia_inicial"].quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)),
                "entradas": str(item["entradas"].quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)),
                "salidas": str(item["salidas"].quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)),
                "retiros_autoconsumo": str(item["retiros_autoconsumo"].quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)),
                "existencia_final": str(ex_final),
                "costo_unitario_fiscal": str(costo_fiscal),
                "valor_final_fiscal": str(val_final),
            }
        )

    return {
        "empresa_id": str(empresa.pk),
        "fecha_inicio": fecha_inicio.isoformat(),
        "fecha_fin": fecha_fin.isoformat(),
        "ambito": "FISCAL",
        "moneda_pais": getattr(moneda_pais, "codigo_iso", "USD") if moneda_pais else "USD",
        "tasa_fiscal_aplicada": str(tasa_fiscal.quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)),
        "valor_total_fiscal": str(valor_total_fiscal.quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)),
        "items": filas,
    }
