"""
Agente Sugeridor de Reorden — M9-T4.

Opera en shadow mode: analiza StockActual + historial de salidas (30 días)
y sugiere cuándo reordenar productos sin modificar ningún dato.

Lógica de clasificación:
  - REORDENAR: stock disponible < cantidad_minima  OR  días_restantes < umbral_critico (10)
  - REVISAR:   días_restantes < umbral_alerta (20)
  - OK:        stock suficiente, no se requiere acción

Modos:
  - Fallback determinista (sin API key): reglas numéricas puras.
  - LLM (con ANTHROPIC_API_KEY o client inyectado): Claude enriquece
    la sugerencia con justificación narrativa.

Uso:
    from apps.agentes.reorden import ReordenSugeridorAgent
    agente = ReordenSugeridorAgent(empresa=empresa)
    sugerencias = agente.analizar()
    for s in sugerencias:
        print(s.producto_nombre, s.estado, s.dias_restantes)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from apps.core import llm_gateway

logger = logging.getLogger("omni.agentes.reorden")

AGENTE_ID = "reorden_sugeridor"

# ── Estados de recomendación ──────────────────────────────────────────────────
ESTADO_REORDENAR = "REORDENAR"
ESTADO_REVISAR = "REVISAR"
ESTADO_OK = "OK"

# ── Umbrales por defecto (días) ───────────────────────────────────────────────
UMBRAL_CRITICO_DEFAULT = 10   # días restantes → REORDENAR
UMBRAL_ALERTA_DEFAULT = 20    # días restantes → REVISAR


# ── Resultado tipado ──────────────────────────────────────────────────────────


@dataclass
class SugerenciaReorden:
    producto_id: str
    producto_nombre: str
    almacen_id: str
    almacen_nombre: str
    stock_disponible: Decimal
    cantidad_minima: Decimal
    consumo_diario: Decimal         # promedio de salidas/día últimos 30 días
    dias_restantes: Optional[float]  # None si consumo_diario == 0
    estado: str                      # REORDENAR | REVISAR | OK
    cantidad_sugerida_reorden: Decimal
    razonamiento: str
    modelo_llm: str = "fallback-reglas"
    latencia_ms: int = 0


# ── Cálculo determinista ──────────────────────────────────────────────────────


def _calcular_estado(
    stock: Decimal,
    cantidad_minima: Decimal,
    dias_restantes: Optional[float],
    umbral_critico: int,
    umbral_alerta: int,
) -> str:
    if stock <= cantidad_minima:
        return ESTADO_REORDENAR
    if dias_restantes is None:
        return ESTADO_OK  # sin consumo → sin urgencia
    if dias_restantes < umbral_critico:
        return ESTADO_REORDENAR
    if dias_restantes < umbral_alerta:
        return ESTADO_REVISAR
    return ESTADO_OK


def _cantidad_sugerida(
    stock: Decimal,
    consumo_diario: Decimal,
    cantidad_maxima: Decimal,
    dias_cobertura: int = 30,
) -> Decimal:
    """Cuánto pedir: cobertura para `dias_cobertura` días - stock actual, min 0."""
    meta = consumo_diario * dias_cobertura
    sugerida = max(Decimal("0"), meta - stock)
    # No exceder cantidad_maxima si está configurada
    if cantidad_maxima > 0:
        sugerida = min(sugerida, cantidad_maxima - stock)
    return sugerida.quantize(Decimal("0.01"))


def _analizar_stock_fallback(
    producto_id: str,
    producto_nombre: str,
    almacen_id: str,
    almacen_nombre: str,
    stock_disponible: Decimal,
    cantidad_minima: Decimal,
    cantidad_maxima: Decimal,
    consumo_diario: Decimal,
    umbral_critico: int = UMBRAL_CRITICO_DEFAULT,
    umbral_alerta: int = UMBRAL_ALERTA_DEFAULT,
) -> SugerenciaReorden:
    if consumo_diario > 0:
        try:
            dias = float(stock_disponible / consumo_diario)
        except (InvalidOperation, ZeroDivisionError):
            dias = None
    else:
        dias = None

    estado = _calcular_estado(stock_disponible, cantidad_minima, dias, umbral_critico, umbral_alerta)
    sugerida = _cantidad_sugerida(stock_disponible, consumo_diario, cantidad_maxima)

    if dias is not None:
        dias_txt = f"{dias:.1f} días"
    else:
        dias_txt = "sin consumo registrado"

    razon = (
        f"Stock: {stock_disponible} uds, consumo diario: {consumo_diario:.2f}/día, "
        f"cobertura estimada: {dias_txt}, mínimo configurado: {cantidad_minima} uds → {estado}."
    )

    return SugerenciaReorden(
        producto_id=producto_id,
        producto_nombre=producto_nombre,
        almacen_id=almacen_id,
        almacen_nombre=almacen_nombre,
        stock_disponible=stock_disponible,
        cantidad_minima=cantidad_minima,
        consumo_diario=consumo_diario,
        dias_restantes=dias,
        estado=estado,
        cantidad_sugerida_reorden=sugerida,
        razonamiento=razon,
    )


# ── Agente principal ──────────────────────────────────────────────────────────


class ReordenSugeridorAgent:
    """
    Agente sugeridor de reorden de inventario en shadow mode.

    Analiza StockActual + MovimientoInventario (últimos 30 días) y genera
    sugerencias de compra sin modificar datos.
    """

    # Resuelto por el gateway (env LLM_MODEL); aquí solo informativo.
    MODELO_DEFAULT = llm_gateway.modelo_configurado(llm_gateway.USO_AGENTE)
    SYSTEM_PROMPT = """Eres un analista de inventario para empresas venezolanas.
Analiza el nivel de stock y consumo de un producto y genera una recomendación de reorden.

Responde SOLO con un JSON válido:
{{
  "estado": "REORDENAR|REVISAR|OK",
  "cantidad_sugerida_reorden": <número>,
  "razonamiento": "<explicación breve en español>"
}}"""

    def __init__(
        self,
        empresa,
        llm_client=None,
        umbral_critico: int = UMBRAL_CRITICO_DEFAULT,
        umbral_alerta: int = UMBRAL_ALERTA_DEFAULT,
        ventana_dias: int = 30,
        gateway=None,
    ):
        self.empresa = empresa
        self.umbral_critico = umbral_critico
        self.umbral_alerta = umbral_alerta
        self.ventana_dias = ventana_dias
        self._llm_client = llm_client
        self._gateway = gateway if gateway is not None else llm_gateway.get_gateway(client=llm_client)
        self._usar_llm = self._gateway.disponible()

    def analizar(
        self,
        hoy: Optional[date] = None,
        solo_alertas: bool = False,
        persistir: bool = True,
    ) -> list[SugerenciaReorden]:
        """
        Analiza todo el stock de la empresa y genera sugerencias de reorden.

        Args:
            hoy:         Fecha de referencia (default: date.today()).
            solo_alertas: Si True, retorna solo REORDENAR y REVISAR.
            persistir:   Si True, persiste en PrediccionAgente.

        Returns:
            Lista de SugerenciaReorden, ordenada: REORDENAR → REVISAR → OK.
        """
        from django.db.models import Sum
        from django.utils import timezone as tz

        from apps.inventario.models import MovimientoInventario, StockActual

        hoy = hoy or date.today()
        fecha_inicio = hoy - timedelta(days=self.ventana_dias)

        # Consumo total por (producto, almacen) en ventana
        salidas_qs = (
            MovimientoInventario.objects.filter(
                id_empresa=self.empresa,
                tipo_movimiento__in=("SALIDA", "DESPACHO_VENTA", "SALIDA_INTERNA", "CONSUMO_PRODUCCION"),
                fecha_hora_movimiento__date__gte=fecha_inicio,
                fecha_hora_movimiento__date__lte=hoy,
            )
            .values("id_producto_id", "id_almacen_origen_id")
            .annotate(total_salidas=Sum("cantidad"))
        )

        consumo_map: dict[tuple, Decimal] = {}
        for row in salidas_qs:
            key = (str(row["id_producto_id"]), str(row["id_almacen_origen_id"]))
            consumo_map[key] = Decimal(str(row["total_salidas"] or 0)) / self.ventana_dias

        stocks = StockActual.objects.filter(
            id_empresa=self.empresa,
        ).select_related("id_producto", "id_almacen")

        sugerencias = []
        for stock in stocks:
            t0 = time.perf_counter()
            key = (str(stock.id_producto_id), str(stock.id_almacen_id))
            consumo_diario = consumo_map.get(key, Decimal("0"))

            if self._usar_llm:
                s = self._analizar_llm(stock, consumo_diario)
            else:
                s = _analizar_stock_fallback(
                    producto_id=str(stock.id_producto_id),
                    producto_nombre=stock.id_producto.nombre_producto,
                    almacen_id=str(stock.id_almacen_id),
                    almacen_nombre=stock.id_almacen.nombre_almacen,
                    stock_disponible=stock.cantidad_disponible,
                    cantidad_minima=stock.cantidad_minima,
                    cantidad_maxima=stock.cantidad_maxima,
                    consumo_diario=consumo_diario,
                    umbral_critico=self.umbral_critico,
                    umbral_alerta=self.umbral_alerta,
                )

            s.latencia_ms = int((time.perf_counter() - t0) * 1000)

            if persistir:
                self._persistir(stock, s, consumo_diario)

            if solo_alertas and s.estado == ESTADO_OK:
                continue
            sugerencias.append(s)

        orden = {ESTADO_REORDENAR: 0, ESTADO_REVISAR: 1, ESTADO_OK: 2}
        sugerencias.sort(key=lambda s: orden.get(s.estado, 9))
        return sugerencias

    def evaluar(
        self,
        stock_disponible: Decimal,
        cantidad_minima: Decimal,
        consumo_diario: Decimal,
        cantidad_maxima: Decimal = Decimal("0"),
        producto_id: str = "test",
        producto_nombre: str = "Producto Test",
        almacen_id: str = "test",
        almacen_nombre: str = "Almacén Test",
    ) -> SugerenciaReorden:
        """
        Evalúa un producto con datos directos (sin tocar la BD).
        Útil para tests y golden cases del eval suite.
        """
        return _analizar_stock_fallback(
            producto_id=producto_id,
            producto_nombre=producto_nombre,
            almacen_id=almacen_id,
            almacen_nombre=almacen_nombre,
            stock_disponible=stock_disponible,
            cantidad_minima=cantidad_minima,
            cantidad_maxima=cantidad_maxima,
            consumo_diario=consumo_diario,
            umbral_critico=self.umbral_critico,
            umbral_alerta=self.umbral_alerta,
        )

    def _analizar_llm(self, stock, consumo_diario: Decimal) -> SugerenciaReorden:
        import json

        producto_nombre = stock.id_producto.nombre_producto
        user_msg = (
            f"Producto: {producto_nombre}\n"
            f"Stock disponible: {stock.cantidad_disponible}\n"
            f"Stock mínimo: {stock.cantidad_minima}\n"
            f"Consumo diario promedio (últimos {self.ventana_dias}d): {consumo_diario:.2f}\n"
            f"Umbrales: crítico={self.umbral_critico}d, alerta={self.umbral_alerta}d"
        )
        try:
            respuesta = self._gateway.generate(
                prompt=user_msg,
                system=self.SYSTEM_PROMPT,
                max_tokens=256,
                uso=llm_gateway.USO_AGENTE,
                empresa=self.empresa,
            )
            data = json.loads(respuesta.text.strip())
            estado_raw = data.get("estado", ESTADO_OK)
            estado = estado_raw if estado_raw in (ESTADO_REORDENAR, ESTADO_REVISAR, ESTADO_OK) else ESTADO_OK
            dias_r = float(stock.cantidad_disponible / consumo_diario) if consumo_diario > 0 else None
            return SugerenciaReorden(
                producto_id=str(stock.id_producto_id),
                producto_nombre=producto_nombre,
                almacen_id=str(stock.id_almacen_id),
                almacen_nombre=stock.id_almacen.nombre_almacen,
                stock_disponible=stock.cantidad_disponible,
                cantidad_minima=stock.cantidad_minima,
                consumo_diario=consumo_diario,
                dias_restantes=dias_r,
                estado=estado,
                cantidad_sugerida_reorden=Decimal(str(data.get("cantidad_sugerida_reorden", 0))),
                razonamiento=data.get("razonamiento", ""),
                modelo_llm=respuesta.model,
            )
        except Exception as exc:
            logger.error("LLM reorden fallo, fallback: %s", exc)
            s = _analizar_stock_fallback(
                str(stock.id_producto_id),
                stock.id_producto.nombre_producto,
                str(stock.id_almacen_id),
                stock.id_almacen.nombre_almacen,
                stock.cantidad_disponible,
                stock.cantidad_minima,
                stock.cantidad_maxima,
                consumo_diario,
                self.umbral_critico,
                self.umbral_alerta,
            )
            s.modelo_llm = f"fallback-error:{llm_gateway.nombre_error(exc)}"
            return s

    def _persistir(self, stock, sugerencia: SugerenciaReorden, consumo_diario: Decimal) -> None:
        try:
            from apps.agentes.models import PrediccionAgente

            PrediccionAgente.objects.create(
                id_empresa=self.empresa,
                agente=AGENTE_ID,
                input_texto=f"{sugerencia.producto_nombre} | stock={sugerencia.stock_disponible} | consumo={consumo_diario:.2f}/día",
                input_monto=sugerencia.stock_disponible,
                input_metadata={
                    "almacen_id": sugerencia.almacen_id,
                    "consumo_diario": str(consumo_diario),
                    "dias_restantes": sugerencia.dias_restantes,
                },
                categoria_predicha=sugerencia.estado,
                confianza=0.85,
                razonamiento=sugerencia.razonamiento,
                alternativas=[{"cantidad_sugerida": str(sugerencia.cantidad_sugerida_reorden)}],
                modelo_llm=sugerencia.modelo_llm,
                latencia_ms=sugerencia.latencia_ms,
            )
        except Exception as exc:
            logger.error("Error persistiendo prediccion reorden: %s", exc)
