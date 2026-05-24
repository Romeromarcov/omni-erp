"""
Eval suite — Agente Estratega de Cobranza (CTF-003).

Ejecuta los 33 casos dorados del dataset y verifica que la precision@1
(prioridad + canal correctos) sea >= 0.80 (80%).

Uso:
    pytest tests_eval/test_eval_cobranza.py -v

Sin BD: todos los tests usan CobranzaEstrategaAgent.sugerir() con datos directos.
"""

import pytest
from decimal import Decimal

from apps.agentes.cobranza import CobranzaEstrategaAgent
from apps.agentes.eval_cobranza import CASOS_DORADOS_COBRANZA, PRECISION_MINIMA_COBRANZA

PRECISION_MINIMA_CTF = 0.80  # CTF-003: >= 0.80


@pytest.fixture(scope="module")
def agente():
    """Instancia del agente con fallback determinístico (sin LLM, sin BD).
    Al no pasar llm_client, el agente usa _analizar_fallback() directamente.
    """
    return CobranzaEstrategaAgent(empresa=None, llm_client=None)


class TestEvalCobranza:
    """
    Eval suite para CobranzaEstrategaAgent.

    Un caso se considera correcto si PRIORIDAD y CANAL coinciden con lo esperado.
    """

    def _sugerir(self, agente, caso):
        """Llama a sugerir() con los datos del caso."""
        return agente.sugerir(
            cxc_id=f"eval-{id(caso)}",
            cliente_nombre="Cliente Eval",
            monto=caso["monto"],
            dias_vencida=caso["dias_vencida"],
            intentos_contacto=caso["intentos"],
            persistir=False,
        )

    @pytest.mark.parametrize("caso", CASOS_DORADOS_COBRANZA)
    def test_caso_individual(self, agente, caso):
        """Cada caso dorado debe clasificarse con prioridad y canal correctos."""
        sugerencia = self._sugerir(agente, caso)
        assert sugerencia.prioridad == caso["prioridad"], (
            f"Caso: dias={caso['dias_vencida']}, monto={caso['monto']}, intentos={caso['intentos']} "
            f"→ prioridad esperada={caso['prioridad']}, obtenida={sugerencia.prioridad}"
        )
        assert sugerencia.canal == caso["canal"], (
            f"Caso: dias={caso['dias_vencida']}, monto={caso['monto']}, intentos={caso['intentos']} "
            f"→ canal esperado={caso['canal']}, obtenido={sugerencia.canal}"
        )

    def test_precision_global_prioridad(self, agente):
        """
        La precisión de prioridad sobre todos los casos dorados debe ser >= 80%.

        Criterio de aceptación principal del CTF-003 para cobranza.
        """
        correctos = 0
        total = len(CASOS_DORADOS_COBRANZA)

        for caso in CASOS_DORADOS_COBRANZA:
            sugerencia = self._sugerir(agente, caso)
            if sugerencia.prioridad == caso["prioridad"]:
                correctos += 1

        precision = correctos / total
        assert precision >= PRECISION_MINIMA_CTF, (
            f"Precisión de prioridad del agente de cobranza: {precision:.1%} ({correctos}/{total}). "
            f"Mínima requerida: {PRECISION_MINIMA_CTF:.0%} (CTF-003)"
        )

    def test_precision_global_canal(self, agente):
        """
        La precisión de canal debe ser >= 80% también.
        """
        correctos = 0
        total = len(CASOS_DORADOS_COBRANZA)

        for caso in CASOS_DORADOS_COBRANZA:
            sugerencia = self._sugerir(agente, caso)
            if sugerencia.canal == caso["canal"]:
                correctos += 1

        precision = correctos / total
        assert precision >= PRECISION_MINIMA_CTF, (
            f"Precisión de canal del agente de cobranza: {precision:.1%} ({correctos}/{total}). "
            f"Mínima requerida: {PRECISION_MINIMA_CTF:.0%} (CTF-003)"
        )

    def test_cobertura_prioridades(self, agente):
        """El eval suite cubre las 3 prioridades: alta, media y baja."""
        prioridades = {caso["prioridad"] for caso in CASOS_DORADOS_COBRANZA}
        assert "alta" in prioridades
        assert "media" in prioridades
        assert "baja" in prioridades

    def test_cobertura_canales(self, agente):
        """El eval suite cubre al menos 2 canales de contacto."""
        canales = {caso["canal"] for caso in CASOS_DORADOS_COBRANZA}
        assert len(canales) >= 2, f"Solo hay {len(canales)} canales cubiertos: {canales}"

    def test_tamanio_dataset(self):
        """El dataset debe tener al menos 25 casos (CTF-003: 25 por agente)."""
        assert len(CASOS_DORADOS_COBRANZA) >= 25, (
            f"El dataset de cobranza necesita >= 25 casos; hay {len(CASOS_DORADOS_COBRANZA)}"
        )

    def test_alta_prioridad_monto_alto(self, agente):
        """Monto > 5000 → prioridad alta sin importar días."""
        sugerencia = agente.sugerir(
            cxc_id="eval-monto-alto",
            cliente_nombre="Gran Cliente",
            monto=Decimal("10000.00"),
            dias_vencida=5,
            intentos_contacto=0,
            persistir=False,
        )
        assert sugerencia.prioridad == "alta"

    def test_alta_prioridad_dias_vencida(self, agente):
        """Más de 60 días vencida → prioridad alta."""
        sugerencia = agente.sugerir(
            cxc_id="eval-dias-altos",
            cliente_nombre="Cliente Moroso",
            monto=Decimal("100.00"),
            dias_vencida=90,
            intentos_contacto=0,
            persistir=False,
        )
        assert sugerencia.prioridad == "alta"

    def test_baja_prioridad_reciente(self, agente):
        """Monto bajo, pocos días, ningún intento → prioridad baja."""
        sugerencia = agente.sugerir(
            cxc_id="eval-baja",
            cliente_nombre="Cliente Nuevo",
            monto=Decimal("200.00"),
            dias_vencida=10,
            intentos_contacto=0,
            persistir=False,
        )
        assert sugerencia.prioridad == "baja"
