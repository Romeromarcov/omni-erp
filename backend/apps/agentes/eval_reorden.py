"""
Dataset de evaluación para el Agente Sugeridor de Reorden (M9-T4).

Cada caso dorado define:
  - stock_disponible:  unidades actuales disponibles
  - cantidad_minima:   stock mínimo configurado
  - consumo_diario:    promedio de salidas/día (últimos 30 días)
  - estado_esperado:   "REORDENAR" | "REVISAR" | "OK"

Umbrales de evaluación (por defecto del agente):
  - UMBRAL_CRITICO = 10 días → REORDENAR
  - UMBRAL_ALERTA  = 20 días → REVISAR

El agente debe clasificar correctamente ≥ 75% de los casos.
"""

from decimal import Decimal

PRECISION_MINIMA_REORDEN = 0.75

CASOS_DORADOS_REORDEN = [
    # ── REORDENAR: stock < cantidad_minima ─────────────────────────────────────
    {"stock": Decimal("5"),   "minimo": Decimal("10"),  "consumo": Decimal("2.0"),  "estado": "REORDENAR"},
    {"stock": Decimal("0"),   "minimo": Decimal("5"),   "consumo": Decimal("1.0"),  "estado": "REORDENAR"},
    {"stock": Decimal("2"),   "minimo": Decimal("20"),  "consumo": Decimal("3.0"),  "estado": "REORDENAR"},
    {"stock": Decimal("1"),   "minimo": Decimal("50"),  "consumo": Decimal("5.0"),  "estado": "REORDENAR"},
    {"stock": Decimal("9"),   "minimo": Decimal("10"),  "consumo": Decimal("1.5"),  "estado": "REORDENAR"},

    # ── REORDENAR: dias_restantes < 10 (umbral crítico) ───────────────────────
    # stock/consumo_diario < 10
    {"stock": Decimal("9"),   "minimo": Decimal("0"),   "consumo": Decimal("2.0"),  "estado": "REORDENAR"},  # 4.5 días
    {"stock": Decimal("5"),   "minimo": Decimal("0"),   "consumo": Decimal("1.0"),  "estado": "REORDENAR"},  # 5 días
    {"stock": Decimal("15"),  "minimo": Decimal("0"),   "consumo": Decimal("3.0"),  "estado": "REORDENAR"},  # 5 días
    {"stock": Decimal("8"),   "minimo": Decimal("0"),   "consumo": Decimal("1.5"),  "estado": "REORDENAR"},  # 5.3 días
    {"stock": Decimal("19"),  "minimo": Decimal("0"),   "consumo": Decimal("4.0"),  "estado": "REORDENAR"},  # 4.75 días
    {"stock": Decimal("3"),   "minimo": Decimal("0"),   "consumo": Decimal("0.5"),  "estado": "REORDENAR"},  # 6 días
    {"stock": Decimal("10"),  "minimo": Decimal("0"),   "consumo": Decimal("2.0"),  "estado": "REORDENAR"},  # 5 días
    {"stock": Decimal("40"),  "minimo": Decimal("0"),   "consumo": Decimal("8.0"),  "estado": "REORDENAR"},  # 5 días

    # ── REVISAR: 10 <= dias_restantes < 20 ────────────────────────────────────
    {"stock": Decimal("20"),  "minimo": Decimal("0"),   "consumo": Decimal("2.0"),  "estado": "REVISAR"},   # 10 días
    {"stock": Decimal("30"),  "minimo": Decimal("0"),   "consumo": Decimal("2.0"),  "estado": "REVISAR"},   # 15 días
    {"stock": Decimal("19"),  "minimo": Decimal("0"),   "consumo": Decimal("1.0"),  "estado": "REVISAR"},   # 19 días
    {"stock": Decimal("25"),  "minimo": Decimal("0"),   "consumo": Decimal("2.0"),  "estado": "REVISAR"},   # 12.5 días
    {"stock": Decimal("50"),  "minimo": Decimal("0"),   "consumo": Decimal("4.0"),  "estado": "REVISAR"},   # 12.5 días
    {"stock": Decimal("75"),  "minimo": Decimal("0"),   "consumo": Decimal("5.0"),  "estado": "REVISAR"},   # 15 días
    {"stock": Decimal("11"),  "minimo": Decimal("0"),   "consumo": Decimal("1.0"),  "estado": "REVISAR"},   # 11 días
    {"stock": Decimal("35"),  "minimo": Decimal("0"),   "consumo": Decimal("2.5"),  "estado": "REVISAR"},   # 14 días
    {"stock": Decimal("55"),  "minimo": Decimal("0"),   "consumo": Decimal("3.5"),  "estado": "REVISAR"},   # 15.7 días
    {"stock": Decimal("18"),  "minimo": Decimal("0"),   "consumo": Decimal("1.0"),  "estado": "REVISAR"},   # 18 días

    # ── OK: dias_restantes >= 20 ──────────────────────────────────────────────
    {"stock": Decimal("100"), "minimo": Decimal("10"),  "consumo": Decimal("2.0"),  "estado": "OK"},        # 50 días
    {"stock": Decimal("200"), "minimo": Decimal("5"),   "consumo": Decimal("5.0"),  "estado": "OK"},        # 40 días
    {"stock": Decimal("50"),  "minimo": Decimal("0"),   "consumo": Decimal("1.0"),  "estado": "OK"},        # 50 días
    {"stock": Decimal("60"),  "minimo": Decimal("0"),   "consumo": Decimal("2.0"),  "estado": "OK"},        # 30 días
    {"stock": Decimal("500"), "minimo": Decimal("20"),  "consumo": Decimal("10.0"), "estado": "OK"},        # 50 días
    {"stock": Decimal("1000"),"minimo": Decimal("50"),  "consumo": Decimal("20.0"), "estado": "OK"},        # 50 días
    {"stock": Decimal("40"),  "minimo": Decimal("5"),   "consumo": Decimal("1.5"),  "estado": "OK"},        # 26.7 días
    {"stock": Decimal("80"),  "minimo": Decimal("10"),  "consumo": Decimal("3.0"),  "estado": "OK"},        # 26.7 días

    # ── OK: sin consumo (consumo = 0) → no urgencia ───────────────────────────
    {"stock": Decimal("50"),  "minimo": Decimal("5"),   "consumo": Decimal("0.0"),  "estado": "OK"},
    {"stock": Decimal("100"), "minimo": Decimal("10"),  "consumo": Decimal("0.0"),  "estado": "OK"},
]

assert len(CASOS_DORADOS_REORDEN) >= 30, (
    f"El eval suite de reorden necesita >= 30 casos; hay {len(CASOS_DORADOS_REORDEN)}"
)
