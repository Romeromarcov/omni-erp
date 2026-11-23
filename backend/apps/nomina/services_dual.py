"""Motor de Nómina Dual Venezolana VE (Plan 09 Ola 3B / Fase 4).

Une en una sola corrida atómica y sin excels paralelos:
1. Capa Formal LOTTT (``ambito="FISCAL"``, Bs): salario formal, horas extra y bono
   nocturno (desde ``control_asistencia``), cestaticket, retenciones SSO/FAOV/RPE/ISLR-ARI,
   aportes patronales (SSO/FAOV/INCES/RPE/LOPCYMAT) y amortización de préstamos fiscales.
2. Capa Gerencial / Bonificaciones (``ambito="GERENCIAL"``, USD/USDT): cálculo automático del
   diferencial ``Bono Gerencial = max(0, Paquete Objetivo - Equivalente Formal USD)`` + bonos
   fijos gerenciales, amortización de préstamos gerenciales y arqueo de efectivo USD ($100..$1).
3. Simulador de Liquidación LOTTT (Art. 142 garantía vs retroactividad, vacaciones/bono/
   utilidades fraccionadas, doble indemnización Art. 92 y saldo de préstamos pendientes).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.db import transaction
from django.utils import timezone

from .calculo_lottt import EntradaNomina, ParametrosLOTTT, calcular_nomina
from .services import _conceptos_de_empresa, config_nomina_de_empresa

_CERO = Decimal("0.00")
_DOS_DEC = Decimal("0.01")
_CUATRO_DEC = Decimal("0.0001")
_CIEN = Decimal("100")
_DENOMINACIONES_USD: tuple[int, ...] = (100, 50, 20, 10, 5, 1)


class NominaDualError(Exception):
    """Error de dominio en operaciones de Nómina Dual VE (→ 400 en la API)."""


@dataclass
class _AcumuladorProceso:
    emp: int = 0
    dev: Decimal = _CERO
    ded: Decimal = _CERO
    neto: Decimal = _CERO


def _q2(val: Any) -> Decimal:
    return Decimal(str(val)).quantize(_DOS_DEC, rounding=ROUND_HALF_UP)


def _q4(val: Any) -> Decimal:
    return Decimal(str(val)).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)


def _factor_periodo(tipo_periodo: str, dias_trabajados: int) -> Decimal:
    if tipo_periodo == "QUINCENAL":
        base = Decimal(dias_trabajados) / Decimal("15")
        return (base / Decimal("2")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    if tipo_periodo == "SEMANAL":
        return (Decimal(dias_trabajados) / Decimal("30")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return (Decimal(dias_trabajados) / Decimal("30")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _dias_nominales_periodo(tipo_periodo: str) -> int:
    if tipo_periodo == "QUINCENAL":
        return 15
    if tipo_periodo == "SEMANAL":
        return 7
    return 30


def _asegurar_conceptos_duales(empresa) -> dict[str, Any]:
    from .models import ConceptoNomina

    conceptos = _conceptos_de_empresa(empresa)
    extras = {
        "BONO_GERENCIAL": ("Diferencial Paquete Objetivo Gerencial", "DEVENGADO", "BONO"),
        "BONO_FIJO_GER": ("Bono Fijo Gerencial", "DEVENGADO", "BONO"),
        "PRESTAMO_DED": ("Descuento Cuota Préstamo/Adelanto", "DEDUCCION", "OTROS"),
        "AP_LOPCYMAT": ("Aporte Patronal LOPCYMAT (0.75%)", "APORTE_PATRONAL", "OTROS"),
    }
    for codigo, (nombre, tipo, categoria) in extras.items():
        obj, _ = ConceptoNomina.objects.get_or_create(
            id_empresa=empresa,
            codigo_concepto=codigo,
            defaults={"nombre_concepto": nombre, "tipo_concepto": tipo, "categoria": categoria},
        )
        conceptos[codigo] = obj
    return conceptos


def calcular_arqueo_efectivo_usd(montos_por_empleado: list[dict[str, Any]]) -> dict[str, Any]:
    """Calcula el desglose óptimo de billetes USD ($100/$50/$20/$10/$5/$1 + centavos) por persona y bóveda."""
    totales_boveda: dict[str, int] = {str(d): 0 for d in _DENOMINACIONES_USD}
    total_efectivo = _CERO
    total_centavos = _CERO
    detalle: list[dict[str, Any]] = []

    for row in montos_por_empleado:
        monto_d = _q2(row.get("monto") or _CERO)
        if monto_d < 0:
            raise NominaDualError("El monto de arqueo no puede ser negativo.")
        entero = int(monto_d)
        centavos = (monto_d - Decimal(entero)).quantize(_DOS_DEC, rounding=ROUND_HALF_UP)
        restante = entero
        billetes: dict[str, int] = {}
        for denom in _DENOMINACIONES_USD:
            qty, restante = divmod(restante, denom)
            billetes[str(denom)] = qty
            totales_boveda[str(denom)] += qty
        total_efectivo += monto_d
        total_centavos += centavos
        detalle.append(
            {
                "empleado_id": str(row.get("empleado_id", "")),
                "empleado_nombre": str(row.get("empleado_nombre", "")),
                "monto": str(monto_d),
                "billetes": billetes,
                "centavos_residuales": str(centavos),
            }
        )

    return {
        "total_efectivo_usd": str(_q2(total_efectivo)),
        "total_centavos_residuales_usd": str(_q2(total_centavos)),
        "boveda_billetes": totales_boveda,
        "empleados": detalle,
    }


def extraer_novedades_asistencia(empresa, periodo) -> dict[str, dict[str, Any]]:
    """Agrega novedades de ``control_asistencia.ResumenAsistenciaDiario`` para el período."""
    from apps.control_asistencia.models import ResumenAsistenciaDiario

    resumenes = ResumenAsistenciaDiario.objects.filter(
        id_empleado__empresa=empresa,
        fecha__gte=periodo.fecha_inicio,
        fecha__lte=periodo.fecha_fin,
    ).select_related("id_empleado")

    por_emp: dict[str, dict[str, Any]] = {}
    for res in resumenes:
        if res.id_empleado_id is None:
            continue
        eid = str(res.id_empleado_id)
        item = por_emp.setdefault(
            eid,
            {
                "ausencias": 0,
                "horas_extra_diurnas": Decimal("0"),
                "horas_extra_nocturnas": Decimal("0"),
                "minutos_tardanza": 0,
            },
        )
        if res.es_ausencia:
            item["ausencias"] += 1
        item["horas_extra_diurnas"] += Decimal(str(res.horas_extras_normal or 0))
        item["horas_extra_nocturnas"] += Decimal(str(res.horas_extras_feriado or 0))
        item["minutos_tardanza"] += int(res.minutos_tardanza or 0)
    return por_emp


def _resolver_tasa_bcv_periodo(empresa, fecha_ref: date, tasa_override: Decimal | None) -> Decimal:
    if tasa_override is not None:
        tasa = Decimal(str(tasa_override))
        if tasa <= 0:
            raise NominaDualError("'tasa_bcv' debe ser mayor a cero.")
        return tasa

    from apps.finanzas.services_trimonetario import TasaCambioError, obtener_tasa_por_tipo

    moneda_base = getattr(empresa, "id_moneda_base", None)
    moneda_pais = getattr(empresa, "id_moneda_pais", None)
    if moneda_base is not None and moneda_pais is not None and moneda_base.pk != moneda_pais.pk:
        try:
            obj = obtener_tasa_por_tipo(
                moneda_base, moneda_pais, empresa=empresa, solo_oficial_fiscal=True, fecha=fecha_ref
            )
            if obj is not None and Decimal(str(obj.valor_tasa)) > 0:
                return Decimal(str(obj.valor_tasa))
        except TasaCambioError:
            pass
    raise NominaDualError("Debe suministrar 'tasa_bcv' o configurar una tasa BCV oficial vigente.")


def calcular_paquete_dual_empleado(
    *,
    ficha,
    empleado,
    periodo,
    tasa_bcv: Decimal,
    parametros: ParametrosLOTTT | None = None,
    dias_trabajados: int | None = None,
    horas_extra_diurnas: Decimal = _CERO,
    horas_extra_nocturnas: Decimal = _CERO,
    horas_nocturnas: Decimal = _CERO,
    descuento_prestamo_fiscal_ves: Decimal = _CERO,
    descuento_prestamo_gerencial_usd: Decimal = _CERO,
    alicuota_lopcymat: Decimal = Decimal("0.0075"),
) -> dict[str, Any]:
    """Calcula en Decimal puro ambas capas (Formal LOTTT Bs y Gerencial/Bono USD) sin doble pago."""
    if tasa_bcv <= 0:
        raise NominaDualError("'tasa_bcv' debe ser mayor a cero.")

    params = parametros or ParametrosLOTTT()
    dias_nom = _dias_nominales_periodo(periodo.tipo_periodo)
    dias_ef = dias_trabajados if dias_trabajados is not None else dias_nom
    if dias_ef < 0:
        raise NominaDualError("'dias_trabajados' no puede ser negativo.")

    antiguedad = max(((periodo.fecha_fin or periodo.fecha_pago) - empleado.fecha_ingreso).days // 365, 0)
    entrada = EntradaNomina(
        salario_mensual=Decimal(str(ficha.salario_base_formal_ves)),
        dias_trabajados=dias_ef,
        horas_extra_diurnas=Decimal(str(horas_extra_diurnas)),
        horas_extra_nocturnas=Decimal(str(horas_extra_nocturnas)),
        horas_nocturnas=Decimal(str(horas_nocturnas)),
        antiguedad_anios=antiguedad,
        cestaticket_mensual=Decimal(str(ficha.cestaticket_mensual_ves)),
        otras_deducciones=Decimal("0"),
    )
    res_lottt = calcular_nomina(entrada, params)

    # AR-I explícito del empleado tiene precedencia sobre estimación simplificada por tramos
    pct_ari = Decimal(str(getattr(ficha, "porcentaje_ari", _CERO) or _CERO))
    islr_ves = res_lottt.islr
    if pct_ari > 0:
        islr_ves = _q2(res_lottt.total_devengado_salarial * pct_ari / _CIEN)

    deducciones_formal_ves = _q2(
        res_lottt.sso + res_lottt.faov + res_lottt.rpe + islr_ves + Decimal(str(descuento_prestamo_fiscal_ves))
    )
    neto_formal_ves = max(_CERO, _q2(res_lottt.total_asignaciones - deducciones_formal_ves))
    aporte_lopcymat_ves = _q2(res_lottt.total_devengado_salarial * Decimal(str(alicuota_lopcymat)))

    factor_periodo = _factor_periodo(periodo.tipo_periodo, dias_ef)
    paquete_obj_periodo_usd = _q2(Decimal(str(ficha.paquete_objetivo_mensual)) * factor_periodo)
    bono_fijo_periodo_usd = _q2(Decimal(str(ficha.bono_fijo_gerencial)) * factor_periodo)

    # Equivalente formal sin restar préstamo fiscal para comparar remuneración bruta neta pactada
    neto_formal_sin_prestamo_ves = max(
        _CERO, _q2(res_lottt.total_asignaciones - (res_lottt.sso + res_lottt.faov + res_lottt.rpe + islr_ves))
    )
    equivalente_formal_usd = _q2(neto_formal_sin_prestamo_ves / Decimal(str(tasa_bcv)))
    diferencial_bono_usd = max(_CERO, _q2(paquete_obj_periodo_usd - equivalente_formal_usd))

    total_devengado_gerencial_usd = _q2(diferencial_bono_usd + bono_fijo_periodo_usd)
    deduccion_gerencial_usd = _q2(descuento_prestamo_gerencial_usd)
    neto_gerencial_usd = max(_CERO, _q2(total_devengado_gerencial_usd - deduccion_gerencial_usd))

    return {
        "dias_trabajados": dias_ef,
        "tasa_bcv": Decimal(str(tasa_bcv)),
        "formal": {
            "lottt": res_lottt,
            "islr_ves": islr_ves,
            "descuento_prestamo_ves": _q2(descuento_prestamo_fiscal_ves),
            "total_deducciones_ves": deducciones_formal_ves,
            "neto_pagar_ves": neto_formal_ves,
            "equivalente_usd": equivalente_formal_usd,
            "aporte_lopcymat_ves": aporte_lopcymat_ves,
        },
        "gerencial": {
            "paquete_objetivo_periodo_usd": paquete_obj_periodo_usd,
            "diferencial_bono_usd": diferencial_bono_usd,
            "bono_fijo_usd": bono_fijo_periodo_usd,
            "total_devengado_usd": total_devengado_gerencial_usd,
            "descuento_prestamo_usd": deduccion_gerencial_usd,
            "neto_pagar_usd": neto_gerencial_usd,
        },
    }


def _crear_nomina_y_detalles(
    *,
    proceso,
    empleado,
    sueldo_base: Decimal,
    total_devengado: Decimal,
    total_deducciones: Decimal,
    total_neto: Decimal,
    dias_trabajados: int,
    horas_extras: Decimal,
    ahora: datetime,
    lineas: list[tuple[Any, Decimal]],
):
    from .models import DetalleNomina, Nomina

    nomina = Nomina.objects.create(
        id_proceso_nomina=proceso,
        id_empleado=empleado,
        sueldo_base=_q4(sueldo_base),
        total_devengado=_q4(total_devengado),
        total_deducciones=_q4(total_deducciones),
        total_neto=_q4(total_neto),
        dias_trabajados=dias_trabajados,
        horas_extras=_q2(horas_extras),
        estado="CALCULADA",
        fecha_calculo=ahora,
    )
    detalles = [
        DetalleNomina(
            id_nomina=nomina,
            id_concepto_nomina=concepto,
            cantidad=Decimal("1.0000"),
            valor_unitario=_q4(monto),
            valor_total=_q4(monto),
        )
        for concepto, monto in lineas
        if monto > 0
    ]
    if detalles:
        DetalleNomina.objects.bulk_create(detalles)
    return nomina


def _amortizar_prestamos_empleado(empresa, empleado, *, ambito: str) -> Decimal:
    from .models import PrestamoEmpleado

    prestamos = list(
        PrestamoEmpleado.objects.select_for_update()
        .filter(id_empresa=empresa, id_empleado=empleado, ambito_descuento=ambito, estado="ACTIVO", activo=True)
        .order_by("fecha_otorgamiento", "pk")
    )
    total_desc = _CERO
    for pres in prestamos:
        cuota = min(Decimal(str(pres.monto_cuota)), Decimal(str(pres.saldo_pendiente)))
        if cuota <= 0:
            continue
        pres.saldo_pendiente = _q4(Decimal(str(pres.saldo_pendiente)) - cuota)
        pres.cuotas_pagadas = int(pres.cuotas_pagadas) + 1
        if pres.saldo_pendiente <= 0:
            pres.saldo_pendiente = Decimal("0.0000")
            pres.estado = "PAGADO"
        pres.save(update_fields=["saldo_pendiente", "cuotas_pagadas", "estado", "fecha_actualizacion"])
        total_desc += cuota
    return _q2(total_desc)


def _generar_asiento_ambito(empresa, proceso, *, tipo_preferido: str, ambito: str, monto: Decimal, usuario):
    from apps.contabilidad.models import MapeoContable
    from apps.contabilidad.services import generar_asiento_o_fallar

    if monto <= 0:
        return None, None
    tipo = tipo_preferido
    if (
        tipo_preferido != "NOMINA"
        and not MapeoContable.objects.filter(id_empresa=empresa, tipo_asiento=tipo_preferido, activo=True).exists()
    ):
        tipo = "NOMINA"
    return generar_asiento_o_fallar(tipo, proceso, empresa, monto=monto, usuario=usuario, ambito=ambito)


@transaction.atomic
def procesar_nomina_dual(
    empresa,
    periodo,
    *,
    tasa_bcv: Decimal | None = None,
    incluir_asistencia: bool = True,
    amortizar_prestamos: bool = True,
    generar_dispersion: bool = True,
    datos_empleados: dict[str, Any] | None = None,
    usuario=None,
) -> dict[str, Any]:
    """Ejecuta en una sola transacción atómica ambos procesos (``FISCAL`` y ``GERENCIAL``), préstamos y dispersión."""
    from apps.rrhh.models import Empleado

    from .models import DispersionPagoNomina, FichaSalarialDual, ProcesoNomina

    if getattr(periodo, "id_empresa_id", None) != empresa.pk:
        raise NominaDualError("El período de nómina no pertenece a la empresa activa.")
    if periodo.estado in ("CERRADO", "PAGADO"):
        raise NominaDualError(f"El período está en estado {periodo.estado}; no puede procesarse nuevamente.")

    tasa = _resolver_tasa_bcv_periodo(empresa, periodo.fecha_fin or timezone.localdate(), tasa_bcv)
    empleados = list(Empleado.objects.filter(empresa=empresa, activo=True).order_by("apellido", "nombre"))
    if not empleados:
        raise NominaDualError("La empresa no tiene empleados activos para procesar.")

    fichas_map = {
        str(f.id_empleado_id): f
        for f in FichaSalarialDual.objects.filter(id_empresa=empresa, activo=True).select_related("moneda_paquete")
    }
    if not fichas_map:
        raise NominaDualError("No hay fichas salariales duales configuradas en la empresa.")

    from apps.core.uuid import uuid7

    config = config_nomina_de_empresa(empresa)
    conceptos = _asegurar_conceptos_duales(empresa)
    novedades = extraer_novedades_asistencia(empresa, periodo) if incluir_asistencia else {}
    ahora = timezone.now()
    sufijo = f"{ahora:%Y%m%d%H%M%S}-{uuid7().hex[:6]}"
    moneda_pais = getattr(empresa, "id_moneda_pais", None) or getattr(empresa, "id_moneda_base", None)
    moneda_base = getattr(empresa, "id_moneda_base", None) or moneda_pais

    proc_fiscal = ProcesoNomina.objects.create(
        id_empresa=empresa,
        id_periodo_nomina=periodo,
        numero_proceso=f"NF-{sufijo}",
        fecha_proceso=ahora,
        estado="COMPLETADO",
        ambito="FISCAL",
    )
    proc_gerencial = ProcesoNomina.objects.create(
        id_empresa=empresa,
        id_periodo_nomina=periodo,
        numero_proceso=f"NG-{sufijo}",
        fecha_proceso=ahora,
        estado="COMPLETADO",
        ambito="GERENCIAL",
    )

    tot_f = _AcumuladorProceso()
    tot_g = _AcumuladorProceso()
    dispersiones: list[DispersionPagoNomina] = []

    for emp in empleados:
        ficha = fichas_map.get(str(emp.pk))
        if ficha is None:
            continue
        nov = novedades.get(str(emp.pk), {})
        ovr = (datos_empleados or {}).get(str(emp.pk)) or {}
        dias_nom = _dias_nominales_periodo(periodo.tipo_periodo)
        dias_ef = int(ovr.get("dias_trabajados", max(0, dias_nom - int(nov.get("ausencias", 0)))))
        hed = Decimal(str(ovr.get("horas_extra_diurnas", nov.get("horas_extra_diurnas", 0))))
        hen = Decimal(str(ovr.get("horas_extra_nocturnas", nov.get("horas_extra_nocturnas", 0))))
        hn = Decimal(str(ovr.get("horas_nocturnas", 0)))

        desc_f = _amortizar_prestamos_empleado(empresa, emp, ambito="FISCAL") if amortizar_prestamos else _CERO
        desc_g = _amortizar_prestamos_empleado(empresa, emp, ambito="GERENCIAL") if amortizar_prestamos else _CERO

        calc = calcular_paquete_dual_empleado(
            ficha=ficha,
            empleado=emp,
            periodo=periodo,
            tasa_bcv=tasa,
            parametros=config.parametros,
            dias_trabajados=dias_ef,
            horas_extra_diurnas=hed,
            horas_extra_nocturnas=hen,
            horas_nocturnas=hn,
            descuento_prestamo_fiscal_ves=desc_f,
            descuento_prestamo_gerencial_usd=desc_g,
        )

        # ── 1. Persistir Nomina + Detalles FISCAL (Bs) ──
        cf = calc["formal"]
        res_l = cf["lottt"]
        nom_f = _crear_nomina_y_detalles(
            proceso=proc_fiscal,
            empleado=emp,
            sueldo_base=ficha.salario_base_formal_ves,
            total_devengado=res_l.total_asignaciones,
            total_deducciones=cf["total_deducciones_ves"],
            total_neto=cf["neto_pagar_ves"],
            dias_trabajados=dias_ef,
            horas_extras=hed + hen,
            ahora=ahora,
            lineas=[
                (conceptos["SUELDO"], res_l.salario_periodo),
                (conceptos["HED"], res_l.monto_horas_extra_diurnas),
                (conceptos["HEN"], res_l.monto_horas_extra_nocturnas),
                (conceptos["BONO_NOCT"], res_l.monto_bono_nocturno),
                (conceptos["CESTATICKET"], res_l.cestaticket),
                (conceptos["SSO"], res_l.sso),
                (conceptos["FAOV"], res_l.faov),
                (conceptos["RPE"], res_l.rpe),
                (conceptos["ISLR"], cf["islr_ves"]),
                (conceptos["PRESTAMO_DED"], cf["descuento_prestamo_ves"]),
                (conceptos["AP_SSO"], res_l.aporte_patronal_sso),
                (conceptos["AP_FAOV"], res_l.aporte_patronal_faov),
                (conceptos["AP_INCES"], res_l.aporte_patronal_inces),
                (conceptos["AP_RPE"], res_l.aporte_patronal_rpe),
                (conceptos["AP_LOPCYMAT"], cf["aporte_lopcymat_ves"]),
            ],
        )
        tot_f.emp += 1
        tot_f.dev += res_l.total_asignaciones
        tot_f.ded += cf["total_deducciones_ves"]
        tot_f.neto += cf["neto_pagar_ves"]

        if generar_dispersion and cf["neto_pagar_ves"] > 0:
            dispersiones.append(
                DispersionPagoNomina(
                    id_empresa=empresa,
                    id_proceso_nomina=proc_fiscal,
                    id_nomina=nom_f,
                    id_empleado=emp,
                    ambito="FISCAL",
                    canal_pago="TRANSFERENCIA_BS",
                    moneda=moneda_pais,
                    monto=_q4(cf["neto_pagar_ves"]),
                    referencia_destino=ficha.cuenta_bancaria_formal,
                )
            )

        # ── 2. Persistir Nomina + Detalles GERENCIAL (USD/USDT) ──
        cg = calc["gerencial"]
        nom_g = _crear_nomina_y_detalles(
            proceso=proc_gerencial,
            empleado=emp,
            sueldo_base=cg["paquete_objetivo_periodo_usd"],
            total_devengado=cg["total_devengado_usd"],
            total_deducciones=cg["descuento_prestamo_usd"],
            total_neto=cg["neto_pagar_usd"],
            dias_trabajados=dias_ef,
            horas_extras=Decimal("0.00"),
            ahora=ahora,
            lineas=[
                (conceptos["BONO_GERENCIAL"], cg["diferencial_bono_usd"]),
                (conceptos["BONO_FIJO_GER"], cg["bono_fijo_usd"]),
                (conceptos["PRESTAMO_DED"], cg["descuento_prestamo_usd"]),
            ],
        )
        tot_g.emp += 1
        tot_g.dev += cg["total_devengado_usd"]
        tot_g.ded += cg["descuento_prestamo_usd"]
        tot_g.neto += cg["neto_pagar_usd"]

        if generar_dispersion and cg["neto_pagar_usd"] > 0:
            desglose = {}
            if ficha.canal_pago_gerencial == "EFECTIVO_USD":
                desglose = calcular_arqueo_efectivo_usd(
                    [
                        {
                            "empleado_id": emp.pk,
                            "empleado_nombre": f"{emp.nombre} {emp.apellido}",
                            "monto": cg["neto_pagar_usd"],
                        }
                    ]
                )["empleados"][0]
            dispersiones.append(
                DispersionPagoNomina(
                    id_empresa=empresa,
                    id_proceso_nomina=proc_gerencial,
                    id_nomina=nom_g,
                    id_empleado=emp,
                    ambito="GERENCIAL",
                    canal_pago=ficha.canal_pago_gerencial,
                    moneda=ficha.moneda_paquete or moneda_base,
                    monto=_q4(cg["neto_pagar_usd"]),
                    desglose_denominaciones=desglose,
                    referencia_destino=ficha.referencia_pago_gerencial,
                )
            )

    if tot_f.emp == 0:
        raise NominaDualError("Ningún empleado activo posee ficha salarial dual activa.")

    for proc, tot in ((proc_fiscal, tot_f), (proc_gerencial, tot_g)):
        proc.total_empleados = tot.emp
        proc.total_devengado = _q4(tot.dev)
        proc.total_deducciones = _q4(tot.ded)
        proc.total_neto = _q4(tot.neto)
        proc.save(update_fields=["total_empleados", "total_devengado", "total_deducciones", "total_neto"])

    if dispersiones:
        DispersionPagoNomina.objects.bulk_create(dispersiones)

    asiento_f, _ = _generar_asiento_ambito(
        empresa, proc_fiscal, tipo_preferido="NOMINA", ambito="FISCAL", monto=tot_f.neto, usuario=usuario
    )
    asiento_g, _ = _generar_asiento_ambito(
        empresa,
        proc_gerencial,
        tipo_preferido="NOMINA_GERENCIAL",
        ambito="GERENCIAL",
        monto=tot_g.neto,
        usuario=usuario,
    )

    return {
        "tasa_bcv_aplicada": str(tasa),
        "proceso_fiscal": proc_fiscal,
        "proceso_gerencial": proc_gerencial,
        "asiento_fiscal_id": str(asiento_f.pk) if asiento_f else None,
        "asiento_gerencial_id": str(asiento_g.pk) if asiento_g else None,
        "total_dispersiones": len(dispersiones),
    }


def simular_liquidacion_lottt(
    *,
    empleado,
    salario_mensual_integral: Decimal,
    fecha_egreso: date,
    dias_vacaciones_pendientes: int = 0,
    despido_injustificado: bool = False,
    tasa_interes_prestaciones: Decimal = Decimal("0.18"),
    empresa=None,
) -> dict[str, Any]:
    """Simulador de liquidación LOTTT: Art. 142 (garantía vs retroactividad), Art. 92 y préstamos."""
    sal_mensual = Decimal(str(salario_mensual_integral))
    if sal_mensual <= 0:
        raise NominaDualError("El salario integral mensual debe ser mayor a cero.")
    if fecha_egreso < empleado.fecha_ingreso:
        raise NominaDualError("La fecha de egreso no puede ser anterior a la fecha de ingreso.")

    dias_servicio = (fecha_egreso - empleado.fecha_ingreso).days
    anios_completos = dias_servicio // 365
    dias_resto = dias_servicio % 365
    anios_retro = anios_completos + (1 if dias_resto > 180 else 0)
    trimestres = max(1, (dias_servicio // 90))

    sal_diario = (sal_mensual / Decimal("30")).quantize(_CUATRO_DEC, rounding=ROUND_HALF_UP)

    # Garantía Art. 142 lit. a) y b): 15 días/trimestre + 2 días adicionales/año tras el 1er año (máx 30)
    dias_adicionales = min(30, sum(min(30, 2 * i) for i in range(1, anios_completos + 1)))
    dias_garantia = trimestres * 15 + dias_adicionales
    monto_garantia = _q2(Decimal(dias_garantia) * sal_diario)
    intereses_prestaciones = _q2(
        monto_garantia * Decimal(str(tasa_interes_prestaciones)) * Decimal(dias_servicio) / Decimal("365")
    )
    total_garantia_con_intereses = _q2(monto_garantia + intereses_prestaciones)

    # Retroactividad Art. 142 lit. c): 30 días por año o fracción > 6 meses al último salario
    dias_retro = anios_retro * 30
    monto_retroactividad = _q2(Decimal(dias_retro) * sal_diario)

    regimen_aplicado = (
        "RETROACTIVIDAD_ART142_C" if monto_retroactividad >= total_garantia_con_intereses else "GARANTIA_ART142_AB"
    )
    prestaciones_lottt = max(total_garantia_con_intereses, monto_retroactividad)

    # Vacaciones y bono vacacional fraccionados + utilidades fraccionadas del ejercicio
    meses_fraccion = Decimal(max(1, (fecha_egreso.month)))
    vacaciones_fracc = _q2(
        (Decimal("15") + Decimal(min(15, anios_completos))) * (meses_fraccion / Decimal("12")) * sal_diario
    )
    bono_vac_fracc = vacaciones_fracc
    vacaciones_vencidas = _q2(Decimal(max(0, dias_vacaciones_pendientes)) * sal_diario)
    utilidades_fracc = _q2(Decimal("30") * (meses_fraccion / Decimal("12")) * sal_diario)

    indemnizacion_art92 = prestaciones_lottt if despido_injustificado else _CERO

    prestamos_pendientes = _CERO
    if empresa is not None:
        from .models import PrestamoEmpleado

        for p in PrestamoEmpleado.objects.filter(
            id_empresa=empresa, id_empleado=empleado, estado="ACTIVO", activo=True
        ):
            prestamos_pendientes += Decimal(str(p.saldo_pendiente))
        prestamos_pendientes = _q2(prestamos_pendientes)

    bruto = _q2(
        prestaciones_lottt
        + vacaciones_fracc
        + bono_vac_fracc
        + vacaciones_vencidas
        + utilidades_fracc
        + indemnizacion_art92
    )
    neto_liquidacion = max(_CERO, _q2(bruto - prestamos_pendientes))

    return {
        "empleado_id": str(empleado.pk),
        "fecha_ingreso": empleado.fecha_ingreso.isoformat(),
        "fecha_egreso": fecha_egreso.isoformat(),
        "dias_servicio": dias_servicio,
        "anios_antiguedad_completos": anios_completos,
        "salario_diario_integral": str(sal_diario),
        "garantia_art142_capital": str(monto_garantia),
        "intereses_prestaciones": str(intereses_prestaciones),
        "retroactividad_art142_c": str(monto_retroactividad),
        "regimen_aplicado": regimen_aplicado,
        "prestaciones_aplicadas": str(prestaciones_lottt),
        "vacaciones_fraccionadas": str(vacaciones_fracc),
        "bono_vacacional_fraccionado": str(bono_vac_fracc),
        "vacaciones_pendientes": str(vacaciones_vencidas),
        "utilidades_fraccionadas": str(utilidades_fracc),
        "indemnizacion_art92": str(indemnizacion_art92),
        "deduccion_prestamos_pendientes": str(prestamos_pendientes),
        "total_bruto": str(bruto),
        "neto_liquidacion": str(neto_liquidacion),
    }
