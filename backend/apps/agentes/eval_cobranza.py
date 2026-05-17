"""
Dataset de evaluación para el Agente Estratega de Cobranza (M9-T3).

Cada caso dorado define:
  - dias_vencida:      días de atraso respecto a fecha_vencimiento
  - monto:             monto de la cuenta por cobrar
  - intentos_contacto: intentos previos de contacto
  - prioridad_esperada: "alta" | "media" | "baja"
  - canal_esperado:    "whatsapp" | "telefono" | "email" | "visita_presencial"

El agente debe clasificar correctamente el ≥ 75% de los casos.
"""

from decimal import Decimal

PRECISION_MINIMA_COBRANZA = 0.75

CASOS_DORADOS_COBRANZA = [
    # ── Prioridad ALTA (dias > 60 o monto > 5000 o intentos >= 3) ────────────
    # Canal: telefono (alta prioridad, pocos intentos) o visita (alta + muchos intentos)
    {"dias_vencida": 90, "monto": Decimal("1200.00"), "intentos": 1,
     "prioridad": "alta", "canal": "telefono"},
    {"dias_vencida": 65, "monto": Decimal("800.00"),  "intentos": 0,
     "prioridad": "alta", "canal": "telefono"},
    {"dias_vencida": 15, "monto": Decimal("7500.00"), "intentos": 0,
     "prioridad": "alta", "canal": "telefono"},
    {"dias_vencida": 10, "monto": Decimal("6000.00"), "intentos": 0,
     "prioridad": "alta", "canal": "telefono"},
    {"dias_vencida": 45, "monto": Decimal("5500.00"), "intentos": 1,
     "prioridad": "alta", "canal": "telefono"},
    {"dias_vencida": 75, "monto": Decimal("300.00"),  "intentos": 0,
     "prioridad": "alta", "canal": "telefono"},
    {"dias_vencida": 20, "monto": Decimal("200.00"),  "intentos": 3,
     "prioridad": "alta", "canal": "telefono"},
    {"dias_vencida": 5,  "monto": Decimal("150.00"),  "intentos": 4,
     "prioridad": "alta", "canal": "telefono"},
    {"dias_vencida": 95, "monto": Decimal("950.00"),  "intentos": 2,
     "prioridad": "alta", "canal": "visita_presencial"},
    {"dias_vencida": 100,"monto": Decimal("2000.00"), "intentos": 5,
     "prioridad": "alta", "canal": "visita_presencial"},

    # alta + intentos >= 2 → visita
    {"dias_vencida": 70, "monto": Decimal("1500.00"), "intentos": 2,
     "prioridad": "alta", "canal": "visita_presencial"},
    {"dias_vencida": 80, "monto": Decimal("900.00"),  "intentos": 3,
     "prioridad": "alta", "canal": "visita_presencial"},

    # ── Prioridad MEDIA (30 < dias <= 60 o 1000 < monto <= 5000) ─────────────
    # Canal: whatsapp (sin intentos previos)
    {"dias_vencida": 35, "monto": Decimal("800.00"),  "intentos": 0,
     "prioridad": "media", "canal": "whatsapp"},
    {"dias_vencida": 40, "monto": Decimal("500.00"),  "intentos": 0,
     "prioridad": "media", "canal": "whatsapp"},
    {"dias_vencida": 50, "monto": Decimal("250.00"),  "intentos": 0,
     "prioridad": "media", "canal": "whatsapp"},
    {"dias_vencida": 55, "monto": Decimal("400.00"),  "intentos": 0,
     "prioridad": "media", "canal": "whatsapp"},
    {"dias_vencida": 10, "monto": Decimal("2000.00"), "intentos": 0,
     "prioridad": "media", "canal": "whatsapp"},
    {"dias_vencida": 5,  "monto": Decimal("3500.00"), "intentos": 0,
     "prioridad": "media", "canal": "whatsapp"},
    # Canal: email (media, 1 intento + > 30 días)
    {"dias_vencida": 35, "monto": Decimal("600.00"),  "intentos": 1,
     "prioridad": "media", "canal": "email"},
    {"dias_vencida": 45, "monto": Decimal("750.00"),  "intentos": 1,
     "prioridad": "media", "canal": "email"},
    # Canal: telefono (media + 3+ intentos → alta ó media+3 → telefono)
    {"dias_vencida": 40, "monto": Decimal("900.00"),  "intentos": 3,
     "prioridad": "alta", "canal": "telefono"},  # 3 intentos eleva a alta

    # ── Prioridad BAJA (dias <= 30 y monto <= 1000 y intentos < 3) ────────────
    {"dias_vencida": 5,  "monto": Decimal("200.00"),  "intentos": 0,
     "prioridad": "baja", "canal": "whatsapp"},
    {"dias_vencida": 10, "monto": Decimal("450.00"),  "intentos": 0,
     "prioridad": "baja", "canal": "whatsapp"},
    {"dias_vencida": 15, "monto": Decimal("300.00"),  "intentos": 0,
     "prioridad": "baja", "canal": "whatsapp"},
    {"dias_vencida": 20, "monto": Decimal("800.00"),  "intentos": 0,
     "prioridad": "baja", "canal": "whatsapp"},
    {"dias_vencida": 25, "monto": Decimal("100.00"),  "intentos": 0,
     "prioridad": "baja", "canal": "whatsapp"},
    {"dias_vencida": 28, "monto": Decimal("950.00"),  "intentos": 0,
     "prioridad": "baja", "canal": "whatsapp"},
    {"dias_vencida": 1,  "monto": Decimal("50.00"),   "intentos": 0,
     "prioridad": "baja", "canal": "whatsapp"},
    {"dias_vencida": 3,  "monto": Decimal("700.00"),  "intentos": 0,
     "prioridad": "baja", "canal": "whatsapp"},
    {"dias_vencida": 7,  "monto": Decimal("400.00"),  "intentos": 0,
     "prioridad": "baja", "canal": "whatsapp"},
    {"dias_vencida": 30, "monto": Decimal("999.00"),  "intentos": 0,
     "prioridad": "baja", "canal": "whatsapp"},

    # ── Casos borde ────────────────────────────────────────────────────────────
    {"dias_vencida": 91, "monto": Decimal("1.00"),    "intentos": 6,
     "prioridad": "alta", "canal": "visita_presencial"},  # > 90 días → visita
]

assert len(CASOS_DORADOS_COBRANZA) >= 30, (
    f"El eval suite de cobranza necesita >= 30 casos; hay {len(CASOS_DORADOS_COBRANZA)}"
)
