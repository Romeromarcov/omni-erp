"""Los 5 Agentes IA Operativos del Plan 09 Fase 8.2 (Cobranza, Tesorero, Logístico, Comprador y CFO Copilot)."""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db.models import Sum
from django.utils import timezone

from apps.core.llm_gateway import LLMGateway, LLMUnavailable

from .cobranza import CobranzaEstrategaAgent
from .models import EjecucionAgente
from .reorden import ReordenSugeridorAgent
from .services import AgenteError, jsonable, serializar_sugerencia_cobranza, serializar_sugerencia_reorden

logger = logging.getLogger("omni.agentes.operativos")

_CERO = Decimal("0")
_Q2 = Decimal("0.01")

AGENTES_OPERATIVOS: dict[str, dict[str, str]] = {
    "COBRANZA": {
        "codigo": "COBRANZA",
        "agente_modelo": "cobranza_estratega",
        "nombre": "Agente Estratega de Cobranza",
        "descripcion": "Analiza CxC vencidas, prioriza gestión y redacta mensajes de cobranza.",
    },
    "TESORERO": {
        "codigo": "TESORERO",
        "agente_modelo": "tesorero_conciliador",
        "nombre": "Agente Tesorero (Pre-Conciliación)",
        "descripcion": "Empareja cobros reportados / ingresos Zelle y Pago Móvil con CxC abiertas.",
    },
    "LOGISTICO": {
        "codigo": "LOGISTICO",
        "agente_modelo": "logistico_ruteo",
        "nombre": "Agente Logístico (Re-Ruteo TMS)",
        "descripcion": "Detecta paradas pendientes/atrasadas y propone secuencia de re-ruteo.",
    },
    "COMPRADOR": {
        "codigo": "COMPRADOR",
        "agente_modelo": "reorden_sugeridor",
        "nombre": "Agente Comprador (Reabastecimiento)",
        "descripcion": "Identifica SKUs bajo mínimo con costo de reposición USD.",
    },
    "CFO_COPILOT": {
        "codigo": "CFO_COPILOT",
        "agente_modelo": "cfo_copilot_trimonetario",
        "nombre": "CFO Copilot Trimonetario",
        "descripcion": "Consolidado de liquidez, CxC/CxP y posición en USD / VES / USDT.",
    },
}


def _enriquecer_con_llm(empresa, uso: str, resumen_determinista: str) -> tuple[str, str]:
    """Enriquece un análisis operativo vía ``llm_gateway`` con fallback determinista seguro."""
    gw = LLMGateway()
    if not gw.disponible():
        return resumen_determinista, "DETERMINISTA"
    try:
        res = gw.generate(
            prompt=(
                "Resume en 2 frases ejecutivas en español venezolano para gerencia ERP los siguientes hallazgos:\n"
                f"{resumen_determinista[:1500]}"
            ),
            max_tokens=180,
            uso=uso,
            empresa=empresa,
        )
        texto = (res.text or "").strip()
        if texto:
            return texto, "LLM_GATEWAY"
    except (LLMUnavailable, ValueError, TypeError, RuntimeError):
        logger.info("agente operativo fallback determinista | uso=%s | empresa=%s", uso, getattr(empresa, "pk", None))
    return resumen_determinista, "DETERMINISTA"


def _run_cobranza(empresa, limite: int) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    sugerencias = [
        serializar_sugerencia_cobranza(s) for s in CobranzaEstrategaAgent(empresa=empresa).analizar()[:limite]
    ]
    total_vencido = sum((Decimal(item["monto"]) for item in sugerencias), _CERO).quantize(_Q2, rounding=ROUND_HALF_UP)
    metricas = {"total_sugerencias": len(sugerencias), "monto_vencido": str(total_vencido)}
    resumen = f"Cobranza identificó {len(sugerencias)} cuenta(s) por gestionar por {total_vencido}."
    return sugerencias, metricas, resumen


def _run_tesorero(empresa, limite: int) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar  # noqa: PLC0415
    from apps.ventas.models import PagoPortalCliente  # noqa: PLC0415

    cxc_abiertas = list(
        CuentaPorCobrar.objects.filter(
            empresa=empresa,
            estado__in=("pendiente", "vencida", "parcial"),
        )
        .select_related("cliente")
        .order_by("fecha_vencimiento")[:200]
    )
    pagos_pendientes = list(
        PagoPortalCliente.objects.filter(id_empresa=empresa, estado="PENDIENTE_VALIDACION", activo=True)
        .select_related("id_cliente", "id_moneda", "id_metodo_pago")
        .order_by("-fecha_creacion")[:limite]
    )

    propuestas: list[dict[str, Any]] = []
    for p in pagos_pendientes:
        candidatas = [c for c in cxc_abiertas if c.cliente_id == p.id_cliente_id]
        match_cxc = min(candidatas, key=lambda c: abs(c.monto - p.monto), default=None) if candidatas else None
        dif = (match_cxc.monto - p.monto).quantize(_Q2, rounding=ROUND_HALF_UP) if match_cxc else None
        propuestas.append(
            {
                "id_pago_portal": str(p.pk),
                "cliente": p.id_cliente.razon_social,
                "metodo": p.id_metodo_pago.nombre_metodo,
                "monto_reportado": str(p.monto),
                "moneda": p.id_moneda.codigo_iso,
                "referencia": p.referencia,
                "cxc_sugerida_id": str(match_cxc.pk) if match_cxc else None,
                "diferencia": str(dif) if dif is not None else None,
                "confianza": 0.95 if (dif is not None and dif == _CERO) else (0.75 if match_cxc else 0.30),
            }
        )

    metricas = {
        "pagos_pendientes_revision": len(pagos_pendientes),
        "matches_alta_confianza": sum(1 for pr in propuestas if pr["confianza"] >= 0.75),
    }
    resumen = (
        f"Tesorero evaluó {len(pagos_pendientes)} cobro(s) pendiente(s) y propuso "
        f"{metricas['matches_alta_confianza']} pre-conciliación(es)."
    )
    return propuestas, metricas, resumen


def _run_logistico(empresa, limite: int) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    from apps.despacho.models import ParadaEntrega  # noqa: PLC0415

    ahora = timezone.now()
    paradas = list(
        ParadaEntrega.objects.filter(
            id_empresa=empresa,
            activo=True,
            estado__in=("PENDIENTE", "EN_CAMINO", "REPROGRAMADA"),
        )
        .select_related("id_ruta", "id_despacho")
        .order_by("id_ruta", "secuencia")[:limite]
    )

    alertas: list[dict[str, Any]] = []
    for p in paradas:
        atrasada = bool(p.eta_estimada and p.eta_estimada < ahora)
        sin_gps = p.latitud is None or p.longitud is None
        prioridad = "ALTA" if atrasada or p.estado == "REPROGRAMADA" else ("MEDIA" if sin_gps else "NORMAL")
        alertas.append(
            {
                "id_parada": str(p.pk),
                "ruta": p.id_ruta.codigo,
                "despacho": p.id_despacho.numero_despacho,
                "secuencia": p.secuencia,
                "estado": p.estado,
                "atrasada": atrasada,
                "sin_gps": sin_gps,
                "prioridad_reruteo": prioridad,
            }
        )

    metricas = {
        "paradas_activas": len(alertas),
        "requieren_reruteo": sum(1 for a in alertas if a["prioridad_reruteo"] == "ALTA"),
    }
    resumen = (
        f"Logístico revisó {len(alertas)} parada(s) activa(s); "
        f"{metricas['requieren_reruteo']} con prioridad ALTA de re-ruteo."
    )
    return alertas, metricas, resumen


def _run_comprador(empresa, limite: int) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    from apps.inventario.models import Producto  # noqa: PLC0415

    raw = ReordenSugeridorAgent(empresa=empresa).analizar()[:limite]
    prod_map = {
        str(p.pk): str(getattr(p, "costo_reposicion_usd", None) or _CERO)
        for p in Producto.objects.filter(id_empresa=empresa, pk__in=[s.producto_id for s in raw])
    }
    items = []
    for s in raw:
        d = serializar_sugerencia_reorden(s)
        d["costo_reposicion_usd"] = prod_map.get(d["producto_id"], "0.00")
        items.append(d)
    criticos = sum(1 for it in items if it.get("prioridad") == "alta")
    metricas = {"total_items": len(items), "alertas_criticas": criticos}
    resumen = f"Comprador evaluó {len(items)} SKU(s) para reabastecimiento ({criticos} críticos)."
    return items, metricas, resumen


def _run_cfo_copilot(empresa, _limite: int) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar  # noqa: PLC0415
    from apps.cuentas_por_pagar.models import CuentaPorPagar  # noqa: PLC0415
    from apps.finanzas.models import Pago  # noqa: PLC0415
    from apps.finanzas.services_trimonetario import calcular_equivalencias_trimonetarias  # noqa: PLC0415

    hoy = timezone.localdate()
    cxc_total = (
        CuentaPorCobrar.objects.filter(empresa=empresa, estado__in=("pendiente", "vencida", "parcial")).aggregate(
            t=Sum("monto")
        )["t"]
        or _CERO
    )
    cxc_vencida = (
        CuentaPorCobrar.objects.filter(
            empresa=empresa, estado__in=("pendiente", "vencida", "parcial"), fecha_vencimiento__lt=hoy
        ).aggregate(t=Sum("monto"))["t"]
        or _CERO
    )
    cxp_total = (
        CuentaPorPagar.objects.filter(
            id_empresa=empresa, activo=True, estado__in=("PENDIENTE", "VENCIDA", "PARCIAL")
        ).aggregate(t=Sum("monto_pendiente"))["t"]
        or _CERO
    )
    ingresos = (
        Pago.objects.filter(id_empresa=empresa, tipo_operacion="INGRESO").aggregate(t=Sum("monto"))["t"] or _CERO
    )
    egresos = Pago.objects.filter(id_empresa=empresa, tipo_operacion="EGRESO").aggregate(t=Sum("monto"))["t"] or _CERO
    posicion_neta = (cxc_total - cxp_total).quantize(_Q2, rounding=ROUND_HALF_UP)

    moneda_base = getattr(empresa, "id_moneda_base", None)
    trimonetario: dict[str, Any] = {}
    if moneda_base is not None:
        try:
            eq = calcular_equivalencias_trimonetarias(abs(posicion_neta), moneda_base, empresa=empresa)
            trimonetario = {k: str(v) if isinstance(v, Decimal) else v for k, v in eq.items()}
        except Exception:  # noqa: BLE001
            trimonetario = {"moneda_base": moneda_base.codigo_iso, "monto": str(posicion_neta)}

    metricas = {
        "cxc_abierta": str(Decimal(str(cxc_total)).quantize(_Q2, rounding=ROUND_HALF_UP)),
        "cxc_vencida": str(Decimal(str(cxc_vencida)).quantize(_Q2, rounding=ROUND_HALF_UP)),
        "cxp_abierta": str(Decimal(str(cxp_total)).quantize(_Q2, rounding=ROUND_HALF_UP)),
        "flujo_ingresos_acumulados": str(Decimal(str(ingresos)).quantize(_Q2, rounding=ROUND_HALF_UP)),
        "flujo_egresos_acumulados": str(Decimal(str(egresos)).quantize(_Q2, rounding=ROUND_HALF_UP)),
        "posicion_neta_cxc_cxp": str(posicion_neta),
        "trimonetario": trimonetario,
    }
    resumen = (
        f"CFO Copilot: CxC abierta {metricas['cxc_abierta']} (vencida {metricas['cxc_vencida']}) vs "
        f"CxP {metricas['cxp_abierta']}; posición neta {posicion_neta}."
    )
    return [metricas], metricas, resumen


_RUNNERS = {
    "COBRANZA": _run_cobranza,
    "TESORERO": _run_tesorero,
    "LOGISTICO": _run_logistico,
    "COMPRADOR": _run_comprador,
    "CFO_COPILOT": _run_cfo_copilot,
}


def ejecutar_agente_operativo(
    empresa,
    agente_codigo: str,
    *,
    usuario=None,
    persistir: bool = True,
    limite: int = 25,
) -> dict[str, Any]:
    """Ejecuta sincrónicamente uno de los 5 agentes operativos con registro opcional en ``EjecucionAgente``."""
    codigo = str(agente_codigo or "").strip().upper()
    meta = AGENTES_OPERATIVOS.get(codigo)
    runner = _RUNNERS.get(codigo)
    if meta is None or runner is None:
        raise AgenteError(f"Agente operativo desconocido: {codigo}")

    items, metricas, resumen_base = runner(empresa, max(1, min(int(limite), 100)))
    resumen_exec, modo = _enriquecer_con_llm(empresa, f"operativo_{codigo.lower()}", resumen_base)

    payload = jsonable(
        {
            "agente_codigo": codigo,
            "agente_modelo": meta["agente_modelo"],
            "nombre": meta["nombre"],
            "modo_ejecucion": modo,
            "resumen_ejecutivo": resumen_exec,
            "metricas": metricas,
            "items": items,
        }
    )

    ejecucion_id: str | None = None
    if persistir:
        ahora = timezone.now()
        ej = EjecucionAgente.objects.create(
            id_empresa=empresa,
            agente=meta["agente_modelo"],
            estado="completado",
            parametros={"agente_codigo": codigo, "limite": limite},
            resultado=payload,
            iniciado_por=usuario,
            fecha_inicio=ahora,
            fecha_fin=ahora,
        )
        ejecucion_id = str(ej.pk)

    return {"ejecucion_id": ejecucion_id, **payload}
