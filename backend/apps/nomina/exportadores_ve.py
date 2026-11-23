"""Exportadores bancarios, parafiscales y recibos PDF VE para Nómina Dual (Ola 3B)."""

from __future__ import annotations

import io
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from .services_dual import NominaDualError

_DOS_DEC = Decimal("0.01")


def _q2(val: Any) -> Decimal:
    return Decimal(str(val or 0)).quantize(_DOS_DEC, rounding=ROUND_HALF_UP)


def _limpiar_cedula(cedula: str) -> str:
    return "".join(ch for ch in str(cedula or "").upper() if ch.isalnum())[:12]


def _limpiar_cuenta(cuenta: str) -> str:
    return "".join(ch for ch in str(cuenta or "") if ch.isdigit()).ljust(20, "0")[:20]


def generar_txt_bancario_nomina(proceso, banco: str) -> str:
    """Genera archivo TXT de dispersión bancaria VE (Banesco, Mercantil o BDV)."""
    bco = str(banco or "").strip().upper()
    if bco not in {"BANESCO_TXT", "MERCANTIL_TXT", "BDV_TXT"}:
        raise NominaDualError(f"Formato bancario no soportado: '{banco}'. Use BANESCO_TXT, MERCANTIL_TXT o BDV_TXT.")

    from .models import FichaSalarialDual, Nomina

    nominas = (
        Nomina.objects.filter(id_proceso_nomina=proceso, total_neto__gt=0)
        .select_related("id_empleado")
        .order_by("id_empleado__apellido", "id_empleado__nombre")
    )
    fichas = {
        str(f.id_empleado_id): f for f in FichaSalarialDual.objects.filter(id_empresa=proceso.id_empresa, activo=True)
    }

    lineas: list[str] = []
    if bco == "BANESCO_TXT":
        lineas.append(f"HDR|BANESCO|{proceso.numero_proceso}|{proceso.fecha_proceso:%Y%m%d}|{nominas.count()}")
        for nom in nominas:
            ficha = fichas.get(str(nom.id_empleado_id))
            cuenta = _limpiar_cuenta(getattr(ficha, "cuenta_bancaria_formal", ""))
            ced = _limpiar_cedula(nom.id_empleado.cedula)
            nombre = f"{nom.id_empleado.nombre} {nom.id_empleado.apellido}"[:40]
            monto = f"{_q2(nom.total_neto):.2f}"
            lineas.append(f"DET|{ced}|{nombre}|{cuenta}|{monto}|VES")
    elif bco == "MERCANTIL_TXT":
        lineas.append(f"1;{proceso.numero_proceso};{proceso.fecha_proceso:%Y%m%d};{_q2(proceso.total_neto):.2f}")
        for nom in nominas:
            ficha = fichas.get(str(nom.id_empleado_id))
            cuenta = _limpiar_cuenta(getattr(ficha, "cuenta_bancaria_formal", ""))
            ced = _limpiar_cedula(nom.id_empleado.cedula)
            nombre = f"{nom.id_empleado.nombre} {nom.id_empleado.apellido}"[:40]
            lineas.append(f"2;{ced};{cuenta};{nombre};{_q2(nom.total_neto):.2f}")
    else:  # BDV_TXT
        lineas.append(f"CAB,{proceso.numero_proceso},{proceso.fecha_proceso:%d/%m/%Y},{_q2(proceso.total_neto):.2f}")
        for nom in nominas:
            ficha = fichas.get(str(nom.id_empleado_id))
            cuenta = _limpiar_cuenta(getattr(ficha, "cuenta_bancaria_formal", ""))
            ced = _limpiar_cedula(nom.id_empleado.cedula)
            nombre = f"{nom.id_empleado.nombre} {nom.id_empleado.apellido}"[:40]
            lineas.append(f"REG,{ced},{nombre},{cuenta},{_q2(nom.total_neto):.2f}")
    return "\n".join(lineas)


def generar_exportacion_parafiscales_ve(proceso, ente: str) -> str:
    """Genera reporte/TXT parafiscal VE: FAOV, IVSS_TIUNA, INCES o ISLR_ARC."""
    ente_u = str(ente or "").strip().upper()
    if ente_u not in {"FAOV", "IVSS_TIUNA", "INCES", "ISLR_ARC"}:
        raise NominaDualError(f"Ente parafiscal no soportado: '{ente}'. Use FAOV, IVSS_TIUNA, INCES o ISLR_ARC.")

    from .models import DetalleNomina, Nomina

    nominas = list(
        Nomina.objects.filter(id_proceso_nomina=proceso).select_related("id_empleado").order_by("id_empleado__cedula")
    )
    det_map: dict[tuple[str, str], Decimal] = {}
    for det in DetalleNomina.objects.filter(id_nomina__in=nominas).select_related("id_concepto_nomina"):
        det_map[(str(det.id_nomina_id), det.id_concepto_nomina.codigo_concepto)] = Decimal(str(det.valor_total))

    rif = str(getattr(proceso.id_empresa, "identificador_fiscal", "") or "").strip().upper()
    periodo = f"{proceso.id_periodo_nomina.fecha_fin:%Y%m}"
    lineas: list[str] = []

    if ente_u == "FAOV":
        for nom in nominas:
            ced = _limpiar_cedula(nom.id_empleado.cedula)
            base = _q2(nom.total_devengado)
            ap_trab = _q2(det_map.get((str(nom.pk), "FAOV"), Decimal("0")))
            ap_pat = _q2(det_map.get((str(nom.pk), "AP_FAOV"), Decimal("0")))
            lineas.append(
                f"{ced},{nom.id_empleado.nombre},{nom.id_empleado.apellido},{base:.2f},{ap_trab:.2f},{ap_pat:.2f}"
            )
    elif ente_u == "IVSS_TIUNA":
        for nom in nominas:
            ced = _limpiar_cedula(nom.id_empleado.cedula)
            sso_trab = _q2(det_map.get((str(nom.pk), "SSO"), Decimal("0")))
            sso_pat = _q2(det_map.get((str(nom.pk), "AP_SSO"), Decimal("0")))
            rpe_trab = _q2(det_map.get((str(nom.pk), "RPE"), Decimal("0")))
            lineas.append(
                f"{rif}|{periodo}|{ced}|{_q2(nom.sueldo_base):.2f}|{sso_trab:.2f}|{sso_pat:.2f}|{rpe_trab:.2f}"
            )
    elif ente_u == "INCES":
        total_sal = sum((_q2(n.total_devengado) for n in nominas), Decimal("0.00"))
        total_ap = sum((_q2(det_map.get((str(n.pk), "AP_INCES"), Decimal("0"))) for n in nominas), Decimal("0.00"))
        lineas.append(
            f"INCES|{rif}|{periodo}|EMPLEADOS={len(nominas)}|BASE={total_sal:.2f}|APORTE_2PCT={total_ap:.2f}"
        )
    else:  # ISLR_ARC
        for nom in nominas:
            ced = _limpiar_cedula(nom.id_empleado.cedula)
            islr = _q2(det_map.get((str(nom.pk), "ISLR"), Decimal("0")))
            lineas.append(f"ARC\t{rif}\t{periodo}\t{ced}\t{_q2(nom.total_devengado):.2f}\t{islr:.2f}")

    return "\n".join(lineas)


def generar_pdf_recibo_nomina(nomina, *, modo: str = "SEPARADO") -> bytes:
    """Genera recibo de pago en PDF (ReportLab) en modo SEPARADO (solo el proceso) o CONSOLIDADO (fiscal+gerencial)."""
    modo_u = str(modo or "SEPARADO").strip().upper()
    if modo_u not in {"SEPARADO", "CONSOLIDADO"}:
        raise NominaDualError("El parámetro 'modo' debe ser SEPARADO o CONSOLIDADO.")

    from .models import DetalleNomina, Nomina

    emp = nomina.id_empleado
    proceso = nomina.id_proceso_nomina
    empresa = proceso.id_empresa

    nominas_incluir = [nomina]
    if modo_u == "CONSOLIDADO":
        nominas_incluir = list(
            Nomina.objects.filter(
                id_empleado=emp,
                id_proceso_nomina__id_empresa=empresa,
                id_proceso_nomina__id_periodo_nomina=proceso.id_periodo_nomina,
            )
            .select_related("id_proceso_nomina")
            .order_by("id_proceso_nomina__ambito")
        )

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=LETTER)
    pdf.setTitle(f"Recibo Nomina {emp.cedula} ({modo_u})")
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(50, 750, f"RECIBO DE PAGO DE NÓMINA ({modo_u})")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(50, 730, f"Empresa: {empresa.nombre_legal} ({empresa.identificador_fiscal or 'N/A'})")
    pdf.drawString(50, 715, f"Trabajador: {emp.nombre} {emp.apellido} — C.I.: {emp.cedula}")
    pdf.drawString(
        50,
        700,
        f"Período: {proceso.id_periodo_nomina.nombre_periodo} ({proceso.id_periodo_nomina.fecha_inicio} al {proceso.id_periodo_nomina.fecha_fin})",
    )
    pdf.line(50, 690, 560, 690)

    y = 670
    for nom in nominas_incluir:
        proc_n = nom.id_proceso_nomina
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(
            50, y, f"Capa [{proc_n.ambito}] — Proceso {proc_n.numero_proceso} (Neto: {_q2(nom.total_neto):.2f})"
        )
        y -= 16
        pdf.setFont("Helvetica", 9)
        for det in DetalleNomina.objects.filter(id_nomina=nom).select_related("id_concepto_nomina"):
            pdf.drawString(
                65, y, f"{det.id_concepto_nomina.codigo_concepto} - {det.id_concepto_nomina.nombre_concepto}"
            )
            pdf.drawRightString(545, y, f"{det.id_concepto_nomina.tipo_concepto}: {_q2(det.valor_total):.2f}")
            y -= 14
            if y < 65:
                pdf.showPage()
                pdf.setFont("Helvetica", 9)
                y = 740
        y -= 8

    pdf.save()
    return buf.getvalue()
