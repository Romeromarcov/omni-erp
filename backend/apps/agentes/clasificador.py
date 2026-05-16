"""
Clasificador de Gastos — Agente AI-nativo en shadow mode.

Opera en dos modos:
  - LLM (cuando ANTHROPIC_API_KEY está configurada): usa Claude para clasificar.
  - Fallback determinista (sin API key o en tests con mock): usa reglas de keywords.

Shadow mode: predice la categoría de un gasto pero nunca modifica el modelo Gasto.
El resultado se persiste en PrediccionAgente para análisis de calidad.

Uso:
    from apps.agentes.clasificador import ClasificadorGastos
    agente = ClasificadorGastos(empresa=empresa)
    resultado = agente.clasificar(descripcion="Almuerzo con cliente", monto=45.00)
    # resultado.categoria, resultado.confianza, resultado.razonamiento
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .eval_dataset import CATEGORIAS_CANONICAS

logger = logging.getLogger("omni.agentes.clasificador")

# ── Resultado tipado ──────────────────────────────────────────────────────────


@dataclass
class ResultadoClasificacion:
    categoria: str
    confianza: float  # 0.0 – 1.0
    razonamiento: str
    alternativas: list[dict] = field(default_factory=list)
    modelo_llm: str = "fallback"
    latencia_ms: int = 0


# ── Reglas de fallback (sin LLM) ─────────────────────────────────────────────

_KEYWORDS: dict[str, list[str]] = {
    "alimentacion": [
        "almuerzo", "cena", "desayuno", "comida", "café", "restaurant",
        "catering", "snack", "pizza", "lunch", "refrigerio",
    ],
    "transporte": [
        "taxi", "uber", "avión", "pasaje", "gasolina", "peaje", "metro",
        "autobús", "vuelo", "parking", "estacionamiento", "vehículo", "alquiler auto",
    ],
    "alojamiento": [
        "hotel", "airbnb", "hospedaje", "posada", "habitación", "noche",
    ],
    "materiales_oficina": [
        "papel", "tóner", "toner", "boli", "marcador", "archivador",
        "carpeta", "impresora", "cartucho",
    ],
    "tecnologia_software": [
        "suscripción", "licencia", "software", "servidor", "cloud",
        "dominio", "hosting", "saas", "app", "antivirus",
    ],
    "servicios_profesionales": [
        "consultoría", "honorario", "asesor", "abogado", "contador",
        "auditoría", "diseño", "freelance",
    ],
    "marketing_publicidad": [
        "anuncio", "publicidad", "folleto", "marketing", "campaña",
        "patrocinio", "banner", "instagram", "facebook",
    ],
    "mantenimiento_reparacion": [
        "reparación", "mantenimiento", "cerrajero", "plomero",
        "electricista", "ac", "aire acondicionado",
    ],
    "servicios_publicos": [
        "electricidad", "eléctrica", "agua", "gas", "luz", "cloacas",
    ],
    "comunicaciones": [
        "internet", "fibra", "móvil", "celular", "telefonía", "plan",
    ],
    "capacitacion_formacion": [
        "curso", "capacitación", "taller", "seminario", "certificación",
        "formación", "entrenamiento",
    ],
    "impuestos_tasas": [
        "impuesto", "tasa", "timbre", "municipal", "seniat", "iva", "igtf",
    ],
}


def _clasificar_por_keywords(descripcion: str) -> tuple[str, float]:
    """Clasifica usando coincidencia de palabras clave. Retorna (categoria, confianza)."""
    texto = descripcion.lower()
    scores: dict[str, int] = {}

    for categoria, keywords in _KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in texto)
        if score > 0:
            scores[categoria] = score

    if not scores:
        return "otros", 0.40

    mejor = max(scores, key=lambda c: scores[c])
    total = sum(scores.values())
    confianza = min(0.90, 0.50 + (scores[mejor] / total) * 0.50)
    return mejor, round(confianza, 2)


# ── Agente principal ──────────────────────────────────────────────────────────


class ClasificadorGastos:
    """
    Agente clasificador de gastos en shadow mode.

    Args:
        empresa: instancia de Empresa (para contexto del tenant).
        llm_client: cliente Anthropic inyectable (permite mock en tests).
            Si None, intentará crear uno si hay ANTHROPIC_API_KEY.
    """

    AGENTE_ID = "clasificador_gastos"
    MODELO_DEFAULT = "claude-haiku-4-5-20251001"
    SYSTEM_PROMPT = """Eres un asistente contable para empresas venezolanas.
Tu tarea es clasificar gastos empresariales en categorías contables.

Categorías disponibles: {categorias}

Responde SOLO con un JSON válido con esta estructura exacta:
{{
  "categoria": "<categoria_de_la_lista>",
  "confianza": <número entre 0.0 y 1.0>,
  "razonamiento": "<explicación breve en español>",
  "alternativas": [
    {{"categoria": "<alt1>", "confianza": <num>}},
    {{"categoria": "<alt2>", "confianza": <num>}}
  ]
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

    def clasificar(
        self,
        descripcion: str,
        monto: Optional[Decimal] = None,
        persistir: bool = True,
    ) -> ResultadoClasificacion:
        """
        Clasifica un gasto y opcionalmente persiste la predicción en BD.

        Args:
            descripcion: Texto libre del gasto.
            monto:       Monto en la moneda del gasto (contexto para el LLM).
            persistir:   Si True, guarda PrediccionAgente en BD.

        Returns:
            ResultadoClasificacion con categoria, confianza, razonamiento.
        """
        t0 = time.perf_counter()

        if self._usar_llm:
            resultado = self._clasificar_llm(descripcion, monto)
        else:
            resultado = self._clasificar_fallback(descripcion)

        resultado.latencia_ms = int((time.perf_counter() - t0) * 1000)

        if persistir:
            self._persistir(descripcion, monto, resultado)

        logger.info(
            "clasificar_gasto | empresa=%s | categoria=%s | confianza=%.2f | modelo=%s | ms=%d",
            self.empresa.pk,
            resultado.categoria,
            resultado.confianza,
            resultado.modelo_llm,
            resultado.latencia_ms,
        )
        return resultado

    # ── Implementaciones ──────────────────────────────────────────────────────

    def _clasificar_fallback(self, descripcion: str) -> ResultadoClasificacion:
        categoria, confianza = _clasificar_por_keywords(descripcion)
        alternativas = []
        for cat in CATEGORIAS_CANONICAS:
            if cat != categoria:
                _, c = _clasificar_por_keywords(f"{descripcion} {cat}")
                if c > 0.40:
                    alternativas.append({"categoria": cat, "confianza": round(c * 0.6, 2)})
        alternativas = sorted(alternativas, key=lambda x: -x["confianza"])[:2]

        return ResultadoClasificacion(
            categoria=categoria,
            confianza=confianza,
            razonamiento=f"Clasificado por coincidencia de palabras clave en la descripción.",
            alternativas=alternativas,
            modelo_llm="fallback-keywords",
        )

    def _clasificar_llm(self, descripcion: str, monto: Optional[Decimal]) -> ResultadoClasificacion:
        import json

        categorias_str = ", ".join(CATEGORIAS_CANONICAS)
        system = self.SYSTEM_PROMPT.format(categorias=categorias_str)

        contexto_monto = f" (monto: {monto} USD)" if monto else ""
        user_msg = f"Gasto: {descripcion}{contexto_monto}"

        try:
            response = self._llm_client.messages.create(
                model=self.MODELO_DEFAULT,
                max_tokens=256,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = response.content[0].text.strip()
            data = json.loads(raw)

            return ResultadoClasificacion(
                categoria=data.get("categoria", "otros"),
                confianza=float(data.get("confianza", 0.5)),
                razonamiento=data.get("razonamiento", ""),
                alternativas=data.get("alternativas", []),
                modelo_llm=self.MODELO_DEFAULT,
            )
        except Exception as exc:
            logger.error("LLM clasificacion fallo, usando fallback: %s", exc)
            resultado = self._clasificar_fallback(descripcion)
            resultado.modelo_llm = f"fallback-error:{type(exc).__name__}"
            return resultado

    def _persistir(
        self,
        descripcion: str,
        monto: Optional[Decimal],
        resultado: ResultadoClasificacion,
    ) -> None:
        try:
            from .models import PrediccionAgente

            PrediccionAgente.objects.create(
                id_empresa=self.empresa,
                agente=self.AGENTE_ID,
                input_texto=descripcion,
                input_monto=monto,
                categoria_predicha=resultado.categoria,
                confianza=resultado.confianza,
                razonamiento=resultado.razonamiento,
                alternativas=resultado.alternativas,
                modelo_llm=resultado.modelo_llm,
                latencia_ms=resultado.latencia_ms,
            )
        except Exception as exc:
            logger.error("Error persistiendo prediccion: %s", exc)

    # ── Métricas ──────────────────────────────────────────────────────────────

    @classmethod
    def metricas_empresa(cls, empresa_id: str) -> dict:
        """Calcula métricas de calidad del agente para una empresa."""
        from django.db.models import Avg, Count
        from .models import PrediccionAgente

        qs = PrediccionAgente.objects.filter(
            id_empresa=empresa_id,
            agente=cls.AGENTE_ID,
        )
        total = qs.count()
        if total == 0:
            return {"total": 0, "precision": None, "confianza_promedio": None}

        evaluadas = qs.exclude(resultado_humano="pendiente")
        aceptadas = evaluadas.filter(resultado_humano="aceptada").count()
        precision = aceptadas / evaluadas.count() if evaluadas.count() > 0 else None

        stats = qs.aggregate(
            confianza_promedio=Avg("confianza"),
            latencia_promedio=Avg("latencia_ms"),
            total_evaluadas=Count("pk", filter=~__import__("django.db.models", fromlist=["Q"]).Q(resultado_humano="pendiente")),
        )

        return {
            "total": total,
            "evaluadas": evaluadas.count(),
            "precision": round(precision, 3) if precision is not None else None,
            "confianza_promedio": round(float(stats["confianza_promedio"] or 0), 3),
            "latencia_promedio_ms": round(float(stats["latencia_promedio"] or 0), 1),
        }
