"""
apps/agentes/base.py — Clase base OmniAgente con shadow mode (Sprint 0.F).

Define el contrato que todo agente de Omni ERP debe implementar y gestiona
automáticamente el ciclo de vida del shadow mode / sugerencia / autonomía
según el ConfigAgente de la empresa.

Uso:

    class MiAgente(OmniAgente):
        AGENTE_ID = "mi_agente"

        def _analizar(self, contexto: dict) -> Prediccion:
            # Lógica de inferencia del agente
            ...

        def _ejecutar(self, prediccion: Prediccion) -> ResultadoAccion:
            # Acción de negocio (solo llamada si nivel=AUTONOMO y conf≥umbral)
            ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

logger = logging.getLogger("omni.agentes")


# ─────────────────────────────────────────────────────────────────────────────
# Estructuras de datos
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Prediccion:
    """Resultado de la fase de análisis de un agente."""

    categoria: str
    confianza: float  # 0.0 – 1.0
    razonamiento: str = ""
    alternativas: list[dict] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResultadoAccion:
    """Resultado de la fase de ejecución de un agente autónomo."""

    ejecutado: bool
    descripcion: str
    datos: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Clase base
# ─────────────────────────────────────────────────────────────────────────────


class OmniAgente:
    """
    Clase base para todos los agentes AI-nativos de Omni ERP.

    Subclases deben implementar:
      - ``AGENTE_ID`` (str): identificador único del agente (debe coincidir
        con las opciones de ConfigAgente.agente y PrediccionAgente.agente).
      - ``_analizar(contexto: dict) -> Prediccion``: lógica de inferencia.
      - ``_ejecutar(prediccion: Prediccion) -> ResultadoAccion`` (opcional):
        acción de negocio que se llama solo en modo AUTONOMO.

    El método público ``procesar(empresa_id, contexto, input_texto, input_monto)``
    orquesta la ejecución respetando el NivelAutonomia configurado:

      SOMBRA     → Analiza + persiste PrediccionAgente. No ejecuta.
      SUGERENCIA → Analiza + persiste. Devuelve sugerencia al llamador.
      AUTONOMO   → Analiza + (si confianza ≥ umbral) ejecuta + persiste.
    """

    AGENTE_ID: str = ""  # Subclases DEBEN sobreescribir esto

    def __init__(self) -> None:
        if not self.AGENTE_ID:
            raise ValueError(
                f"{self.__class__.__name__} debe definir AGENTE_ID."
            )

    # ── Interfaz pública ───────────────────────────────────────────────────────

    def procesar(
        self,
        empresa_id: str,
        contexto: dict[str, Any],
        input_texto: str = "",
        input_monto: Decimal | None = None,
    ) -> dict[str, Any]:
        """
        Punto de entrada principal del agente.

        Pasos:
          1. Resolver ConfigAgente (o usar defaults si no existe).
          2. Llamar a _analizar(contexto).
          3. Según NivelAutonomia y confianza:
             - SOMBRA     → solo registra.
             - SUGERENCIA → registra y retorna sugerencia.
             - AUTONOMO   → registra y ejecuta si confianza ≥ umbral.
          4. Persiste PrediccionAgente.
          5. Retorna resultado estructurado.

        Returns:
            dict con keys: nivel, prediccion, ejecutado, sugerencia, id_prediccion.
        """
        config = self._get_config(empresa_id)
        nivel = config.get("nivel_autonomia", "SOMBRA")
        umbral = config.get("umbral_confianza_minimo", 0.80)
        activo = config.get("activo", True)

        if not activo:
            logger.info(
                "OmniAgente[%s] | empresa=%s | INACTIVO, omitiendo procesamiento.",
                self.AGENTE_ID,
                empresa_id,
            )
            return {"nivel": nivel, "activo": False, "ejecutado": False}

        prediccion = self._analizar(contexto)

        resultado_accion: ResultadoAccion | None = None
        ejecutado = False

        if nivel == "AUTONOMO" and prediccion.confianza >= umbral:
            try:
                resultado_accion = self._ejecutar(prediccion)
                ejecutado = resultado_accion.ejecutado
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "OmniAgente[%s] | empresa=%s | ERROR en _ejecutar: %s",
                    self.AGENTE_ID,
                    empresa_id,
                    exc,
                )

        id_prediccion = self._persistir(
            empresa_id=empresa_id,
            prediccion=prediccion,
            input_texto=input_texto,
            input_monto=input_monto,
        )

        logger.info(
            "OmniAgente[%s] | empresa=%s | nivel=%s | categoria=%s | conf=%.2f | ejecutado=%s",
            self.AGENTE_ID,
            empresa_id,
            nivel,
            prediccion.categoria,
            prediccion.confianza,
            ejecutado,
        )

        return {
            "nivel": nivel,
            "activo": True,
            "prediccion": {
                "categoria": prediccion.categoria,
                "confianza": prediccion.confianza,
                "razonamiento": prediccion.razonamiento,
                "alternativas": prediccion.alternativas,
            },
            "ejecutado": ejecutado,
            "sugerencia": nivel == "SUGERENCIA",
            "id_prediccion": str(id_prediccion) if id_prediccion else None,
            "accion": {
                "descripcion": resultado_accion.descripcion,
                "datos": resultado_accion.datos,
                "error": resultado_accion.error,
            } if resultado_accion else None,
        }

    # ── Hooks para subclases ───────────────────────────────────────────────────

    def _analizar(self, contexto: dict[str, Any]) -> Prediccion:  # noqa: ARG002
        """Debe ser implementado por la subclase. Retorna una Prediccion."""
        raise NotImplementedError(
            f"{self.__class__.__name__} debe implementar _analizar()."
        )

    def _ejecutar(self, prediccion: Prediccion) -> ResultadoAccion:  # noqa: ARG002
        """
        Opcional en subclases. Solo se llama en nivel AUTONOMO.
        Default: no hace nada.
        """
        return ResultadoAccion(ejecutado=False, descripcion="Agente sin acción configurada.")

    # ── Helpers internos ───────────────────────────────────────────────────────

    def _get_config(self, empresa_id: str) -> dict[str, Any]:
        """
        Recupera la ConfigAgente de la empresa o devuelve defaults (SOMBRA).
        """
        try:
            from apps.agentes.models import ConfigAgente  # noqa: PLC0415

            cfg = ConfigAgente.objects.get(id_empresa=empresa_id, agente=self.AGENTE_ID)
            return {
                "nivel_autonomia": cfg.nivel_autonomia,
                "umbral_confianza_minimo": cfg.umbral_confianza_minimo,
                "activo": cfg.activo,
                "max_acciones_por_dia": cfg.max_acciones_por_dia,
                "config_extra": cfg.config_extra,
            }
        except Exception:  # noqa: BLE001
            # Sin configuración → modo más conservador por defecto
            return {
                "nivel_autonomia": "SOMBRA",
                "umbral_confianza_minimo": 0.80,
                "activo": True,
                "max_acciones_por_dia": 0,
                "config_extra": {},
            }

    def _persistir(
        self,
        empresa_id: str,
        prediccion: Prediccion,
        input_texto: str,
        input_monto: Decimal | None,
    ) -> Any:
        """
        Persiste la predicción como PrediccionAgente (registro de sombra).
        Retorna el pk de la instancia creada, o None si falla.
        """
        try:
            from apps.agentes.models import PrediccionAgente  # noqa: PLC0415

            obj = PrediccionAgente.objects.create(
                id_empresa_id=empresa_id,
                agente=self.AGENTE_ID,
                input_texto=input_texto or "",
                input_monto=input_monto,
                input_metadata=prediccion.metadata,
                categoria_predicha=prediccion.categoria,
                confianza=prediccion.confianza,
                razonamiento=prediccion.razonamiento,
                alternativas=prediccion.alternativas,
            )
            return obj.pk
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "OmniAgente[%s] | _persistir falló: %s",
                self.AGENTE_ID,
                exc,
            )
            return None
