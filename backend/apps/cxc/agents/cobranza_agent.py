"""
Agente IA de Cobranza.

Usa el gateway LLM (apps.core.llm_gateway) con streaming para analizar cartera
y gestionar clientes. El modelo se resuelve por env (LLM_MODEL_ANALISIS).
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from apps.core import llm_gateway

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres el Agente de Cobranza Inteligente de Omni ERP.
Tu rol es analizar la cartera de cuentas por cobrar y generar recomendaciones
de gestión de cobranza personalizadas para cada cliente.

REGLAS:
- Prioriza clientes con score alto (más días vencidos + mayor monto + más intentos sin respuesta).
- Si un cliente ya tiene acuerdo de pago vigente, solo sugiere seguimiento de cuotas.
- Para montos > $500 con más de 30 días vencidos, sugiere formalizar acuerdo de pago.
- Tono profesional pero cercano. Nunca amenazante.
- Siempre registra la gestión al final de cada interacción.
- Usa la tasa BCV del día para conversiones USD/VES cuando sea necesario.

FLUJO RECOMENDADO:
1. Obtén cartera vencida priorizada (get_cartera_vencida).
2. Para cada cliente top: verifica si tiene acuerdo vigente (get_acuerdos_vigentes).
3. Obtén tasa del día (get_tasa_cambio_hoy).
4. Genera recomendación personalizada.
5. Registra la gestión (registrar_gestion_cobranza).
"""


class CobranzaAgent:
    """Agente IA de cobranza con streaming via Anthropic SDK."""

    def __init__(self, empresa_id: str):
        self.empresa_id = empresa_id

    def _get_client(self):
        """Cliente inyectable para el gateway (los tests lo parchean).

        En producción devuelve None: el gateway crea el cliente del proveedor
        configurado. Conserva el contrato histórico: RuntimeError si el SDK
        no está instalado.
        """
        try:
            import anthropic  # noqa: F401 — solo verifica que el SDK exista
        except ImportError:
            raise RuntimeError("anthropic SDK no instalado. Ejecutar: pip install anthropic")
        return None

    async def analizar_cartera(self, top_n: int = 10) -> AsyncIterator[str]:
        """Análisis y recomendaciones de cobranza con streaming."""
        try:
            gateway = llm_gateway.get_gateway(client=self._get_client())

            # Obtener datos directamente (sin MCP externo en esta implementación)
            from apps.cuentas_por_cobrar.services_cartera_provider import get_cartera_provider
            from apps.cuentas_por_cobrar.services_scoring import priorizar
            from apps.core.models import Empresa
            from datetime import date
            from apps.finanzas.models import TasaCambio

            empresa = Empresa.objects.get(pk=self.empresa_id)
            provider = get_cartera_provider(empresa)
            partidas = provider.get_partidas(solo_vencidas=True)
            prioridades = priorizar(partidas)[:top_n]

            tasa_hoy = TasaCambio.objects.filter(
                fecha_tasa=date.today(),
                tipo_tasa="OFICIAL_BCV",
                id_moneda_origen__codigo_iso="USD",
                id_moneda_destino__codigo_iso="VES",
            ).order_by("-fecha_creacion").first()

            tasa_str = str(tasa_hoy.valor_tasa) if tasa_hoy else "N/D"

            contexto = (
                f"Empresa ID: {self.empresa_id}\n"
                f"Tasa BCV hoy: {tasa_str} VES/USD\n"
                f"Top {len(prioridades)} clientes por score:\n"
            )
            for p in prioridades:
                contexto += (
                    f"- {p['cliente_nombre']}: ${p['monto_pendiente']} "
                    f"({p['dias_vencida']} días vencido, score={p['score']})\n"
                )

            with gateway.stream(
                messages=[{
                    "role": "user",
                    "content": f"Analiza esta cartera y genera plan de cobranza:\n\n{contexto}",
                }],
                system=SYSTEM_PROMPT,
                max_tokens=4096,
                uso=llm_gateway.USO_ANALISIS,
                empresa=empresa,
            ) as stream:
                for text in stream.text_stream:
                    yield text

        except Exception as exc:
            logger.exception("CobranzaAgent.analizar_cartera error: %s", exc)
            yield f"Error al analizar cartera: {exc}"

    async def gestionar_cliente(
        self,
        cliente_id: str,
        instrucciones: str = "",
    ) -> AsyncIterator[str]:
        """Gestión específica de un cliente con contexto completo."""
        try:
            from apps.cuentas_por_cobrar.services_cartera_provider import get_cartera_provider
            from apps.cxc.models import AcuerdoPago, GestionCobranza
            from apps.core.models import Empresa

            empresa = Empresa.objects.get(pk=self.empresa_id)
            provider = get_cartera_provider(empresa)

            # Contexto del cliente
            partidas = provider.get_partidas()
            partidas_cliente = [p for p in partidas if p.cliente_id == cliente_id]
            pagos = provider.get_pagos_cliente(cliente_id)

            acuerdos_vigentes = AcuerdoPago.objects.filter(
                empresa=empresa,
                cliente_id=cliente_id,
                estado="vigente",
                deleted_at__isnull=True,
            ).prefetch_related("cuotas")

            historial = GestionCobranza.objects.filter(
                empresa=empresa,
                cliente_id=cliente_id,
                deleted_at__isnull=True,
            ).order_by("-fecha_gestion")[:5]

            contexto = f"Cliente ID: {cliente_id}\n"
            if partidas_cliente:
                p = partidas_cliente[0]
                contexto += f"Nombre: {p.cliente_nombre}\n"
                contexto += f"Deuda total pendiente: ${sum(x.monto_pendiente for x in partidas_cliente)}\n"
                contexto += f"Días máximos vencido: {max(x.dias_vencida for x in partidas_cliente)}\n"

            if acuerdos_vigentes.exists():
                ac = acuerdos_vigentes.first()
                contexto += f"\nACUERDO VIGENTE: ${ac.monto_total} — {ac.periodicidad}\n"
                pendientes = ac.cuotas.filter(estado__in=["pendiente", "vencido"]).count()
                contexto += f"Cuotas pendientes: {pendientes}\n"

            if historial:
                contexto += f"\nÚltimas gestiones:\n"
                for g in historial:
                    contexto += f"- {g.fecha_gestion}: {g.canal} → {g.resultado}\n"

            if instrucciones:
                contexto += f"\nInstrucciones especiales: {instrucciones}\n"

            gateway = llm_gateway.get_gateway(client=self._get_client())
            with gateway.stream(
                messages=[{
                    "role": "user",
                    "content": f"Gestiona este cliente específico:\n\n{contexto}",
                }],
                system=SYSTEM_PROMPT,
                max_tokens=2048,
                uso=llm_gateway.USO_ANALISIS,
                empresa=empresa,
            ) as stream:
                for text in stream.text_stream:
                    yield text

        except Exception as exc:
            logger.exception("CobranzaAgent.gestionar_cliente error: %s", exc)
            yield f"Error al gestionar cliente {cliente_id}: {exc}"
