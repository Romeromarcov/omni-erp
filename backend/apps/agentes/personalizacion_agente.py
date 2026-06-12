"""
Agente de Personalización Capa 2 — M9-T2.

Analiza la configuración actual de la empresa y sugiere ajustes a:
  - ConfiguracionFlujoDocumentos: habilitar/deshabilitar pasos del flujo
  - Listas de precios: ajustes porcentuales sugeridos basados en márgenes
  - Límites de crédito de clientes: sugerencias basadas en historial de pagos

Opera en modo sugerencia: NUNCA aplica cambios directamente.
Devuelve un dict estructurado con sugerencias que pueden revisarse y aceptarse.

Uso:
    from apps.agentes.personalizacion_agente import PersonalizacionCapa2Agent
    agente = PersonalizacionCapa2Agent(empresa=empresa)
    resultado = agente.analizar()
    # resultado["flujo_documentos"], resultado["listas_precios"], resultado["credito_clientes"]
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

logger = logging.getLogger("omni.agentes.personalizacion")

AGENTE_ID = "personalizacion_capa2"


# ── Tipos de resultado ────────────────────────────────────────────────────────


@dataclass
class SugerenciaFlujo:
    paso: str
    accion: str          # "habilitar" | "deshabilitar"
    razonamiento: str
    prioridad: str = "media"  # "alta" | "media" | "baja"


@dataclass
class SugerenciaPrecio:
    descripcion: str
    ajuste_porcentual: Decimal   # positivo = subida, negativo = baja
    razonamiento: str
    aplicar_a: str = "todos"     # "todos" | nombre de lista específica


@dataclass
class SugerenciaCredito:
    cliente_id: str
    cliente_nombre: str
    limite_actual: Decimal
    limite_sugerido: Decimal
    razonamiento: str
    riesgo: str = "bajo"         # "bajo" | "medio" | "alto"


@dataclass
class ResultadoPersonalizacionCapa2:
    flujo_documentos: list[SugerenciaFlujo] = field(default_factory=list)
    listas_precios: list[SugerenciaPrecio] = field(default_factory=list)
    credito_clientes: list[SugerenciaCredito] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    modelo_llm: str = "fallback-reglas"


# ── Lógica de reglas (fallback) ───────────────────────────────────────────────


def _analizar_flujo_documentos(empresa) -> list[SugerenciaFlujo]:
    """Sugiere ajustes al flujo de documentos basándose en la config actual."""
    sugerencias = []
    try:
        from apps.core.models import ConfiguracionFlujoDocumentos

        configs = ConfiguracionFlujoDocumentos.objects.filter(id_empresa=empresa)
        pasos_habilitados = {c.paso for c in configs if c.activo}
        pasos_deshabilitados = {c.paso for c in configs if not c.activo}

        # Sugerir habilitar APROBACION_PEDIDO si no está activo
        if "APROBACION_PEDIDO" in pasos_deshabilitados:
            sugerencias.append(SugerenciaFlujo(
                paso="APROBACION_PEDIDO",
                accion="habilitar",
                razonamiento="Habilitar la aprobación de pedidos reduce errores y mejora el control interno.",
                prioridad="media",
            ))

        # Sugerir revisar COTIZACION si hay muchos pasos habilitados
        if len(pasos_habilitados) > 5 and "COTIZACION" in pasos_habilitados:
            sugerencias.append(SugerenciaFlujo(
                paso="COTIZACION",
                accion="revisar",
                razonamiento="Con muchos pasos habilitados, considere si la cotización es obligatoria o solo para clientes nuevos.",
                prioridad="baja",
            ))

    except Exception as exc:
        logger.warning("No se pudo analizar ConfiguracionFlujoDocumentos: %s", exc)
        sugerencias.append(SugerenciaFlujo(
            paso="CONFIGURACION_FLUJO",
            accion="revisar",
            razonamiento="No se encontró configuración de flujo. Se recomienda revisar y configurar los pasos del proceso.",
            prioridad="alta",
        ))

    return sugerencias


def _analizar_credito_clientes(empresa) -> list[SugerenciaCredito]:
    """Sugiere ajustes de límite de crédito basado en historial de pagos."""
    sugerencias = []
    try:
        from apps.crm.models import Cliente
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        clientes = Cliente.objects.filter(id_empresa=empresa)

        for cliente in clientes:
            try:
                # Analizar historial de pagos
                cxc_vencidas = CuentaPorCobrar.objects.filter(
                    cliente=cliente,
                    estado="vencida",
                ).count()
                cxc_pagadas = CuentaPorCobrar.objects.filter(
                    cliente=cliente,
                    estado="pagada",
                ).count()
                total_cxc = cxc_vencidas + cxc_pagadas

                if total_cxc == 0:
                    continue

                tasa_mora = cxc_vencidas / total_cxc
                limite_actual = getattr(cliente, "limite_credito", None) or Decimal("0")

                if limite_actual <= 0:
                    continue

                if tasa_mora > 0.30:
                    # Reduir límite
                    limite_sugerido = limite_actual * Decimal("0.70")
                    sugerencias.append(SugerenciaCredito(
                        cliente_id=str(cliente.pk),
                        cliente_nombre=str(cliente),
                        limite_actual=limite_actual,
                        limite_sugerido=limite_sugerido.quantize(Decimal("0.01")),
                        razonamiento=f"Tasa de mora: {tasa_mora:.0%}. Se sugiere reducir el límite de crédito en 30%.",
                        riesgo="alto",
                    ))
                elif tasa_mora == 0 and cxc_pagadas >= 5:
                    # Buen historial → aumentar límite
                    limite_sugerido = limite_actual * Decimal("1.25")
                    sugerencias.append(SugerenciaCredito(
                        cliente_id=str(cliente.pk),
                        cliente_nombre=str(cliente),
                        limite_actual=limite_actual,
                        limite_sugerido=limite_sugerido.quantize(Decimal("0.01")),
                        razonamiento=f"Historial de pagos excelente ({cxc_pagadas} facturas pagadas, 0 moras). Se sugiere aumentar el límite en 25%.",
                        riesgo="bajo",
                    ))
            except Exception:
                continue

    except Exception as exc:
        logger.warning("No se pudo analizar crédito de clientes: %s", exc)

    return sugerencias


def _analizar_listas_precios(empresa) -> list[SugerenciaPrecio]:
    """Sugiere ajustes a listas de precios basándose en márgenes de productos."""
    sugerencias = []
    try:
        from apps.inventario.models import Producto

        # Detectar productos con margen muy bajo (precio_venta < 1.15 * costo)
        productos_bajo_margen = Producto.objects.filter(
            id_empresa=empresa,
            precio_venta_sugerido__gt=0,
            costo_promedio__gt=0,
        )

        bajo_margen_count = 0
        for p in productos_bajo_margen:
            if p.costo_promedio > 0:
                margen = (p.precio_venta_sugerido - p.costo_promedio) / p.costo_promedio
                if margen < Decimal("0.15"):
                    bajo_margen_count += 1

        if bajo_margen_count > 0:
            sugerencias.append(SugerenciaPrecio(
                descripcion=f"{bajo_margen_count} producto(s) con margen < 15%",
                ajuste_porcentual=Decimal("10.00"),
                razonamiento=(
                    f"Se detectaron {bajo_margen_count} producto(s) con margen bruto menor al 15%. "
                    "Se recomienda revisar los precios de venta o negociar costos con proveedores."
                ),
                aplicar_a="productos_bajo_margen",
            ))

    except Exception as exc:
        logger.warning("No se pudo analizar listas de precios: %s", exc)

    return sugerencias


# ── Agente principal ──────────────────────────────────────────────────────────


class PersonalizacionCapa2Agent:
    """
    Agente de personalización Capa 2.

    Analiza la configuración empresarial y genera sugerencias de ajuste
    sobre: flujo de documentos, listas de precios y límites de crédito.
    NUNCA aplica cambios automáticamente.
    """

    MODELO_DEFAULT = "claude-haiku-4-5-20251001"

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

    def analizar(self) -> ResultadoPersonalizacionCapa2:
        """
        Realiza análisis completo de Capa 2 y retorna sugerencias.

        Returns:
            ResultadoPersonalizacionCapa2 con sugerencias por dominio.
        """
        resultado = ResultadoPersonalizacionCapa2()

        # Flujo de documentos
        try:
            resultado.flujo_documentos = _analizar_flujo_documentos(self.empresa)
        except Exception as exc:
            resultado.advertencias.append(f"Flujo documentos: {exc}")

        # Listas de precios
        try:
            resultado.listas_precios = _analizar_listas_precios(self.empresa)
        except Exception as exc:
            resultado.advertencias.append(f"Listas de precios: {exc}")

        # Crédito clientes
        try:
            resultado.credito_clientes = _analizar_credito_clientes(self.empresa)
        except Exception as exc:
            resultado.advertencias.append(f"Crédito clientes: {exc}")

        logger.info(
            "personalizacion_capa2 | empresa=%s | flujo=%d | precios=%d | credito=%d",
            self.empresa.pk,
            len(resultado.flujo_documentos),
            len(resultado.listas_precios),
            len(resultado.credito_clientes),
        )
        return resultado

    def sugerir_credito(
        self,
        cliente_nombre: str,
        limite_actual: Decimal,
        cxc_vencidas: int,
        cxc_pagadas: int,
    ) -> SugerenciaCredito:
        """
        Sugiere límite de crédito para un cliente dado su historial.
        Entrada directa (sin BD). Útil para tests y eval.
        """
        total = cxc_vencidas + cxc_pagadas
        tasa_mora = Decimal(cxc_vencidas) / Decimal(total) if total > 0 else Decimal("0")

        if tasa_mora > Decimal("0.30"):
            sugerido = (limite_actual * Decimal("0.70")).quantize(Decimal("0.01"))
            riesgo = "alto"
            razon = f"Tasa de mora: {float(tasa_mora):.0%}. Límite reducido en 30%."
        elif tasa_mora == 0 and cxc_pagadas >= 5:
            sugerido = (limite_actual * Decimal("1.25")).quantize(Decimal("0.01"))
            riesgo = "bajo"
            razon = f"Sin moras, {cxc_pagadas} facturas pagadas. Límite aumentado en 25%."
        else:
            sugerido = limite_actual
            riesgo = "medio"
            razon = "Historial mixto. Se mantiene el límite actual."

        return SugerenciaCredito(
            cliente_id="",
            cliente_nombre=cliente_nombre,
            limite_actual=limite_actual,
            limite_sugerido=sugerido,
            razonamiento=razon,
            riesgo=riesgo,
        )
