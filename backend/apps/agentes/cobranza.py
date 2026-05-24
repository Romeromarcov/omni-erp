"""
Agente Estratega de Cobranza — M9-T3.

Opera en shadow mode: analiza CuentaPorCobrar vencidas y genera sugerencias
de contacto sin modificar ningún dato del negocio.

Modos:
  - Fallback determinista (sin API key): clasifica por reglas de días vencidos,
    monto y número de intentos previos.
  - LLM (con ANTHROPIC_API_KEY o client inyectado): Claude genera el mensaje
    personalizado de WhatsApp y la estrategia de contacto.

Uso:
    from apps.agentes.cobranza import CobranzaEstrategaAgent
    agente = CobranzaEstrategaAgent(empresa=empresa)
    sugerencias = agente.analizar()
    for s in sugerencias:
        print(s.prioridad, s.canal, s.mensaje_whatsapp)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

logger = logging.getLogger("omni.agentes.cobranza")

AGENTE_ID = "cobranza_estratega"

# ── Niveles de prioridad ──────────────────────────────────────────────────────
PRIORIDAD_ALTA = "alta"
PRIORIDAD_MEDIA = "media"
PRIORIDAD_BAJA = "baja"

# ── Canales recomendados ──────────────────────────────────────────────────────
CANAL_WHATSAPP = "whatsapp"
CANAL_TELEFONO = "telefono"
CANAL_EMAIL = "email"
CANAL_VISITA = "visita_presencial"


# ── Resultado tipado ──────────────────────────────────────────────────────────


@dataclass
class SugerenciaCobranza:
    cxc_id: str
    cliente_nombre: str
    monto: Decimal
    dias_vencida: int
    prioridad: str          # "alta" | "media" | "baja"
    canal: str              # "whatsapp" | "telefono" | "email" | "visita_presencial"
    mensaje_whatsapp: str   # Texto listo para copiar en WhatsApp
    razonamiento: str
    modelo_llm: str = "fallback-reglas"
    latencia_ms: int = 0
    alternativas: list[dict] = field(default_factory=list)


# ── Lógica de reglas (fallback) ───────────────────────────────────────────────


def _calcular_prioridad(dias_vencida: int, monto: Decimal, intentos: int) -> str:
    """Prioridad basada en días vencidos, monto e intentos de contacto previos."""
    if dias_vencida > 60 or monto > Decimal("5000") or intentos >= 3:
        return PRIORIDAD_ALTA
    if dias_vencida > 30 or monto > Decimal("1000"):
        return PRIORIDAD_MEDIA
    return PRIORIDAD_BAJA


def _calcular_canal(dias_vencida: int, intentos: int, prioridad: str) -> str:
    """Canal de contacto escalado según severidad."""
    if dias_vencida > 90 or intentos >= 5:
        return CANAL_VISITA
    if prioridad == PRIORIDAD_ALTA and intentos >= 2:
        return CANAL_VISITA
    if prioridad == PRIORIDAD_ALTA or intentos >= 3:
        return CANAL_TELEFONO
    if dias_vencida > 30 and intentos >= 1:
        return CANAL_EMAIL
    return CANAL_WHATSAPP


def _generar_mensaje_whatsapp(
    cliente_nombre: str,
    monto: Decimal,
    dias_vencida: int,
    prioridad: str,
) -> str:
    """Genera mensaje WhatsApp profesional según el contexto."""
    monto_fmt = f"{monto:,.2f}"

    if prioridad == PRIORIDAD_ALTA:
        return (
            f"Estimado/a {cliente_nombre}, le contactamos de manera urgente "
            f"respecto a su deuda de ${monto_fmt} con {dias_vencida} días de vencida. "
            f"Solicitamos comunicarse a la brevedad para regularizar su situación "
            f"y evitar acciones adicionales de recuperación. Gracias."
        )
    if prioridad == PRIORIDAD_MEDIA:
        return (
            f"Buenos días, {cliente_nombre}. Le recordamos que tiene un saldo "
            f"pendiente de ${monto_fmt} con {dias_vencida} días de mora. "
            f"¿Podríamos coordinar el pago o un plan de acuerdo? Quedamos atentos."
        )
    return (
        f"Hola {cliente_nombre}, le recordamos amablemente que tiene una factura "
        f"vencida por ${monto_fmt}. Si ya realizó el pago, por favor envíe el "
        f"comprobante. De lo contrario, con gusto le ayudamos a coordinar. Gracias."
    )


def _clasificar_fallback(
    cxc_id: str,
    cliente_nombre: str,
    monto: Decimal,
    dias_vencida: int,
    intentos_contacto: int,
) -> SugerenciaCobranza:
    prioridad = _calcular_prioridad(dias_vencida, monto, intentos_contacto)
    canal = _calcular_canal(dias_vencida, intentos_contacto, prioridad)
    mensaje = _generar_mensaje_whatsapp(cliente_nombre, monto, dias_vencida, prioridad)
    razon = (
        f"Días vencidos: {dias_vencida}, monto: ${monto:,.2f}, "
        f"intentos previos: {intentos_contacto} → prioridad {prioridad} via {canal}."
    )
    return SugerenciaCobranza(
        cxc_id=cxc_id,
        cliente_nombre=cliente_nombre,
        monto=monto,
        dias_vencida=dias_vencida,
        prioridad=prioridad,
        canal=canal,
        mensaje_whatsapp=mensaje,
        razonamiento=razon,
    )


# ── Agente principal ──────────────────────────────────────────────────────────


class CobranzaEstrategaAgent:
    """
    Agente estratega de cobranza en shadow mode.

    Analiza CuentaPorCobrar vencidas de la empresa y sugiere estrategia
    de contacto sin modificar ningún dato de negocio.
    """

    MODELO_DEFAULT = "claude-haiku-4-5-20251001"
    SYSTEM_PROMPT = """Eres un especialista en cobranza empresarial venezolana.
Analiza la información de una cuenta por cobrar vencida y genera una estrategia de contacto.

Responde SOLO con un JSON válido:
{{
  "prioridad": "alta|media|baja",
  "canal": "whatsapp|telefono|email|visita_presencial",
  "mensaje_whatsapp": "<mensaje profesional en español listo para enviar>",
  "razonamiento": "<explicación breve de la estrategia>"
}}"""

    def __init__(self, empresa, llm_client=None):
        self.empresa = empresa
        self._llm_client = llm_client
        self._usar_llm = False

        if llm_client is not None:
            self._usar_llm = True
        elif os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic  # type: ignore[import-untyped]
                self._llm_client = anthropic.Anthropic()
                self._usar_llm = True
            except ImportError:
                logger.warning("anthropic SDK no instalado; usando fallback determinista")

    def analizar(
        self,
        hoy: Optional[date] = None,
        persistir: bool = True,
    ) -> list[SugerenciaCobranza]:
        """
        Consulta todas las CxC vencidas/pendientes-vencidas de la empresa
        y genera sugerencias de cobranza.

        Args:
            hoy:       Fecha de referencia (default: date.today()).
            persistir: Si True, persiste cada sugerencia como PrediccionAgente.

        Returns:
            Lista de SugerenciaCobranza ordenada por prioridad desc.
        """
        from django.utils import timezone as tz

        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        hoy = hoy or date.today()

        cxc_qs = CuentaPorCobrar.objects.filter(
            empresa=self.empresa,
            estado__in=("vencida", "pendiente"),
            fecha_vencimiento__lte=hoy,
        ).select_related("cliente")

        sugerencias = []
        for cxc in cxc_qs:
            t0 = time.perf_counter()
            dias = (hoy - cxc.fecha_vencimiento).days
            intentos = getattr(cxc, "intentos_contacto", 0) or 0
            cliente_nombre = str(cxc.cliente)

            if self._usar_llm:
                s = self._analizar_llm(str(cxc.pk), cliente_nombre, cxc.monto, dias, intentos)
            else:
                s = _clasificar_fallback(str(cxc.pk), cliente_nombre, cxc.monto, dias, intentos)

            s.latencia_ms = int((time.perf_counter() - t0) * 1000)

            if persistir:
                self._persistir(cxc, s)

            sugerencias.append(s)
            logger.info(
                "cobranza | cxc=%s | prioridad=%s | canal=%s | dias=%d",
                cxc.pk, s.prioridad, s.canal, dias,
            )

        # Sort: alta → media → baja
        orden = {PRIORIDAD_ALTA: 0, PRIORIDAD_MEDIA: 1, PRIORIDAD_BAJA: 2}
        sugerencias.sort(key=lambda s: orden.get(s.prioridad, 9))
        return sugerencias

    def sugerir(
        self,
        cxc_id: str,
        cliente_nombre: str,
        monto: Decimal,
        dias_vencida: int,
        intentos_contacto: int = 0,
        persistir: bool = False,
    ) -> SugerenciaCobranza:
        """
        Genera sugerencia para una sola CxC sin consultar la BD.
        Útil para tests y uso directo.
        """
        t0 = time.perf_counter()
        if self._usar_llm:
            s = self._analizar_llm(cxc_id, cliente_nombre, monto, dias_vencida, intentos_contacto)
        else:
            s = _clasificar_fallback(cxc_id, cliente_nombre, monto, dias_vencida, intentos_contacto)
        s.latencia_ms = int((time.perf_counter() - t0) * 1000)
        return s

    def _analizar_llm(
        self,
        cxc_id: str,
        cliente_nombre: str,
        monto: Decimal,
        dias_vencida: int,
        intentos: int,
    ) -> SugerenciaCobranza:
        import json

        user_msg = (
            f"Cliente: {cliente_nombre}\n"
            f"Monto vencido: ${monto:,.2f}\n"
            f"Días vencidos: {dias_vencida}\n"
            f"Intentos de contacto previos: {intentos}"
        )
        try:
            resp = self._llm_client.messages.create(
                model=self.MODELO_DEFAULT,
                max_tokens=400,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            data = json.loads(resp.content[0].text.strip())
            return SugerenciaCobranza(
                cxc_id=cxc_id,
                cliente_nombre=cliente_nombre,
                monto=monto,
                dias_vencida=dias_vencida,
                prioridad=data.get("prioridad", PRIORIDAD_MEDIA),
                canal=data.get("canal", CANAL_WHATSAPP),
                mensaje_whatsapp=data.get("mensaje_whatsapp", ""),
                razonamiento=data.get("razonamiento", ""),
                modelo_llm=self.MODELO_DEFAULT,
            )
        except Exception as exc:
            logger.error("LLM cobranza fallo, fallback: %s", exc)
            s = _clasificar_fallback(cxc_id, cliente_nombre, monto, dias_vencida, intentos)
            s.modelo_llm = f"fallback-error:{type(exc).__name__}"
            return s

    def _persistir(self, cxc, sugerencia: SugerenciaCobranza) -> None:
        try:
            from apps.agentes.models import PrediccionAgente

            PrediccionAgente.objects.create(
                id_empresa=self.empresa,
                agente=AGENTE_ID,
                input_texto=f"{cxc.cliente} | ${cxc.monto} | {sugerencia.dias_vencida}d vencida",
                input_monto=cxc.monto,
                input_metadata={"dias_vencida": sugerencia.dias_vencida, "cxc_id": str(cxc.pk)},
                categoria_predicha=sugerencia.prioridad,
                confianza=0.90 if sugerencia.modelo_llm != "fallback-reglas" else 0.75,
                razonamiento=sugerencia.razonamiento,
                alternativas=[{"canal": sugerencia.canal, "mensaje": sugerencia.mensaje_whatsapp}],
                modelo_llm=sugerencia.modelo_llm,
                latencia_ms=sugerencia.latencia_ms,
            )
        except Exception as exc:
            logger.error("Error persistiendo prediccion cobranza: %s", exc)
