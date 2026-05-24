"""
Eval suite — Agente Sugeridor de Reorden (CTF-003).

Ejecuta los 33 casos dorados del dataset y verifica que la precision@1
sea >= 0.80 (80% de clasificaciones correctas).

Uso:
    pytest tests_eval/test_eval_reorden.py -v

Sin BD: todos los tests usan ReordenSugeridorAgent.evaluar() con datos directos.
"""

import pytest
from decimal import Decimal

from apps.agentes.reorden import ReordenSugeridorAgent
from apps.agentes.eval_reorden import CASOS_DORADOS_REORDEN, PRECISION_MINIMA_REORDEN

PRECISION_MINIMA_CTF = 0.80  # CTF-003: >= 0.80


@pytest.fixture(scope="module")
def agente():
    """Instancia del agente con fallback determinístico (sin LLM, sin BD).
    Al no pasar llm_client, el agente usa _analizar_stock_fallback() directamente.
    """
    return ReordenSugeridorAgent(empresa=None, llm_client=None)


class TestEvalReorden:
    """
    Eval suite para ReordenSugeridorAgent.

    Cada test verifica un caso individual. El test de precision agrega todos.
    """

    def _clasificar(self, agente, caso):
        """Llama a evaluar() con los datos del caso y retorna el estado obtenido."""
        sugerencia = agente.evaluar(
            stock_disponible=caso["stock"],
            cantidad_minima=caso["minimo"],
            consumo_diario=caso["consumo"],
        )
        return sugerencia.estado

    @pytest.mark.parametrize("caso", CASOS_DORADOS_REORDEN)
    def test_caso_individual(self, agente, caso):
        """Cada caso dorado debe clasificarse correctamente."""
        estado_obtenido = self._clasificar(agente, caso)
        assert estado_obtenido == caso["estado"], (
            f"Caso: stock={caso['stock']}, minimo={caso['minimo']}, consumo={caso['consumo']} "
            f"→ esperado={caso['estado']}, obtenido={estado_obtenido}"
        )

    def test_precision_global(self, agente):
        """
        La precisión global sobre todos los casos dorados debe ser >= 80%.

        Este test es el criterio de aceptación principal del CTF-003.
        """
        correctos = 0
        total = len(CASOS_DORADOS_REORDEN)

        for caso in CASOS_DORADOS_REORDEN:
            estado_obtenido = self._clasificar(agente, caso)
            if estado_obtenido == caso["estado"]:
                correctos += 1

        precision = correctos / total
        assert precision >= PRECISION_MINIMA_CTF, (
            f"Precisión del agente de reorden: {precision:.1%} ({correctos}/{total}). "
            f"Mínima requerida: {PRECISION_MINIMA_CTF:.0%} (CTF-003)"
        )

    def test_cobertura_estados(self, agente):
        """El eval suite cubre los 3 estados: REORDENAR, REVISAR y OK."""
        estados_cubiertos = {caso["estado"] for caso in CASOS_DORADOS_REORDEN}
        assert "REORDENAR" in estados_cubiertos
        assert "REVISAR" in estados_cubiertos
        assert "OK" in estados_cubiertos

    def test_tamanio_dataset(self):
        """El dataset debe tener al menos 25 casos (CTF-003: 25 por agente)."""
        assert len(CASOS_DORADOS_REORDEN) >= 25, (
            f"El dataset de reorden necesita >= 25 casos; hay {len(CASOS_DORADOS_REORDEN)}"
        )

    def test_sin_stock_siempre_reordenar(self, agente):
        """Sin stock y con consumo → siempre REORDENAR."""
        sugerencia = agente.evaluar(
            stock_disponible=Decimal("0"),
            cantidad_minima=Decimal("0"),
            consumo_diario=Decimal("5.0"),
        )
        assert sugerencia.estado == "REORDENAR"

    def test_stock_abundante_sin_consumo_ok(self, agente):
        """Stock abundante, sin consumo, minimo cero → OK."""
        sugerencia = agente.evaluar(
            stock_disponible=Decimal("1000"),
            cantidad_minima=Decimal("0"),
            consumo_diario=Decimal("0"),
        )
        assert sugerencia.estado == "OK"

    def test_limite_umbral_critico(self, agente):
        """Exactamente 10 días restantes → REVISAR (no REORDENAR)."""
        # 20 unidades / 2.0 por día = 10 días exactos → REVISAR (no < 10)
        sugerencia = agente.evaluar(
            stock_disponible=Decimal("20"),
            cantidad_minima=Decimal("0"),
            consumo_diario=Decimal("2.0"),
        )
        assert sugerencia.estado == "REVISAR", (
            f"Con 10 días exactos se esperaba REVISAR, obtuvo {sugerencia.estado}"
        )

    def test_limite_umbral_alerta(self, agente):
        """Exactamente 20 días restantes → OK (no REVISAR)."""
        # 40 unidades / 2.0 por día = 20 días exactos → OK (no < 20)
        sugerencia = agente.evaluar(
            stock_disponible=Decimal("40"),
            cantidad_minima=Decimal("0"),
            consumo_diario=Decimal("2.0"),
        )
        assert sugerencia.estado == "OK", (
            f"Con 20 días exactos se esperaba OK, obtuvo {sugerencia.estado}"
        )
