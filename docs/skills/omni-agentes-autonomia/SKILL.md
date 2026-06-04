---
name: omni-agentes-autonomia
description: Use this skill whenever you create, modify, or evaluate an AI agent in the Omni project. Triggers include any work under `apps/agentes/` (subclassing `OmniAgente`, `_analizar`/`_ejecutar`, `Prediccion`, `PrediccionAgente`, `ConfigAgente`), autonomy levels SOMBRA/SUGERENCIA/AUTONOMO, confidence thresholds, the eval suite (`tests_eval/`, golden datasets, precision@1 ≥ 80%), or implementing R-PROD-4 (reversibility) and R-PROD-5 (AI transparency). Apply it whenever an agent predicts, suggests, or executes a business action. Do NOT use for non-agent backend logic, plain REST/MCP tools (use omni-mcp-capacidades), or frontend.
---

# Skill: Agentes AI-nativos con Autonomía Graduada

## Cuándo usar esta skill

Cargá esta skill cuando:
- Creás un agente nuevo (subclase de `OmniAgente`).
- Modificás la lógica de inferencia (`_analizar`) o de acción (`_ejecutar`) de un agente.
- Trabajás con niveles de autonomía, umbrales de confianza o `PrediccionAgente`.
- Agregás o cambiás casos del eval suite (`tests_eval/`).

No la cargués para lógica de negocio normal, tools MCP (usá `omni-mcp-capacidades`) ni frontend.

## Por qué existe la autonomía graduada

Un agente que ejecuta acciones de negocio sin red de seguridad es un riesgo de producto y de confianza. Omni resuelve esto con **tres niveles de autonomía** y un **contrato base** (`OmniAgente`) que los gestiona automáticamente. El agente sube de nivel **solo cuando demuestra precisión** (eval suite) y siempre bajo R-PROD-4 (reversibilidad) y R-PROD-5 (transparencia).

## Los tres niveles

| Nivel | Qué hace | Toca datos |
|---|---|---|
| **SOMBRA** | Predice y persiste la predicción. Mide precisión contra la realidad. | No |
| **SUGERENCIA** | Predice, persiste y propone al humano (acepta/rechaza en UI). | No (hasta que el humano acepta) |
| **AUTONOMO** | Predice, y si `confianza ≥ umbral`, ejecuta la acción. | Sí, dentro de límites |

**Estado actual del proyecto:** los agentes operan en SOMBRA / SUGERENCIA. AUTONOMO se habilita por empresa, por agente, tras evidencia de precisión.

## El contrato base: `OmniAgente`

Vive en `apps/agentes/base.py`. **No reimplementes la orquestación de niveles**; heredá y rellená los hooks.

```python
from apps.agentes.base import OmniAgente, Prediccion, ResultadoAccion


class ClasificadorGastosAgent(OmniAgente):
    AGENTE_ID = "clasificador_gastos"   # OBLIGATORIO; coincide con ConfigAgente.agente

    def _analizar(self, contexto: dict) -> Prediccion:
        # Lógica de inferencia (heurística o LLM). NO toca datos de escritura.
        categoria, confianza, razon = self._inferir(contexto)
        return Prediccion(
            categoria=categoria,
            confianza=confianza,          # float 0.0–1.0
            razonamiento=razon,           # explicable en lenguaje natural (R-PROD-5)
            alternativas=[{"categoria": "...", "confianza": 0.2}],
        )

    def _ejecutar(self, prediccion: Prediccion) -> ResultadoAccion:
        # Solo se llama en AUTONOMO y si confianza ≥ umbral.
        # DEBE ser reversible (R-PROD-4) y registrar qué hizo.
        gasto = self._aplicar_categoria(prediccion.categoria)
        return ResultadoAccion(
            ejecutado=True,
            descripcion=f"Categoría '{prediccion.categoria}' aplicada al gasto {gasto.pk}.",
            datos={"id_gasto": str(gasto.pk)},
        )
```

El método público `procesar(empresa_id, contexto, input_texto, input_monto)` orquesta todo:
1. Resuelve `ConfigAgente` de la empresa (o defaults conservadores: SOMBRA, umbral 0.80).
2. Llama a `_analizar`.
3. Si `nivel == "AUTONOMO"` y `confianza ≥ umbral`, llama a `_ejecutar` (con try/except que loguea sin romper).
4. **Persiste siempre** un `PrediccionAgente` (registro de sombra + feedback).
5. Devuelve un dict estructurado.

**Vos nunca llamás `_analizar`/`_ejecutar` directamente desde afuera; llamás `procesar()`.**

## Reglas que todo agente cumple

1. **`AGENTE_ID` único** y consistente con `ConfigAgente.agente` y `PrediccionAgente.agente`.
2. **`_analizar` no escribe datos de negocio.** Solo infiere. La escritura vive en `_ejecutar`.
3. **`_ejecutar` solo corre en AUTONOMO + confianza suficiente.** Nunca asumas que se ejecutará.
4. **Toda acción autónoma es reversible** (R-PROD-4): el humano puede deshacerla en el plazo configurado.
5. **Toda predicción y acción es transparente** (R-PROD-5): `razonamiento` en lenguaje natural, registrado en `PrediccionAgente`.
6. **Multi-tenant:** `procesar()` recibe `empresa_id`; toda query interna filtra por empresa (ver `omni-multi-tenant-isolation`).
7. **Confianza honesta:** `confianza` refleja la incertidumbre real. Inflarla para cruzar el umbral es el peor anti-patrón.

## Confianza y umbral

- `confianza` ∈ [0.0, 1.0]. El default del umbral es **0.80**.
- En AUTONOMO, `_ejecutar` solo corre si `confianza ≥ umbral_confianza_minimo` de `ConfigAgente`.
- Si dudás, devolvé confianza baja: el costo de no actuar (queda como sugerencia) es mucho menor que el de una acción incorrecta ejecutada.

## Eval suite — el gate de precisión (CTF-003)

Un agente que ejecuta sin evidencia de precisión es inaceptable. Antes de subir a SUGERENCIA/AUTONOMO, el agente pasa su **eval suite** con **precision@1 ≥ 80%** en CI.

Estructura (ver `tests_eval/test_eval_cobranza.py` + `apps/agentes/eval_cobranza.py`):
- **Dataset dorado** (`CASOS_DORADOS_*`): ≥ 25 casos por agente, con entrada esperada y salida correcta.
- **Tests parametrizados** por caso + tests de **precisión global** (`correctos/total ≥ 0.80`).
- **Tests de cobertura**: el dataset cubre todas las clases (prioridades, canales, categorías).
- Corre **sin BD ni LLM**: el agente usa su fallback determinístico (`llm_client=None`).

```python
# tests_eval/test_eval_mi_agente.py
@pytest.mark.parametrize("caso", CASOS_DORADOS_MI_AGENTE)
def test_caso_individual(self, agente, caso):
    pred = agente._analizar(caso["contexto"])
    assert pred.categoria == caso["esperado"]

def test_precision_global(self, agente):
    correctos = sum(
        agente._analizar(c["contexto"]).categoria == c["esperado"]
        for c in CASOS_DORADOS_MI_AGENTE
    )
    precision = correctos / len(CASOS_DORADOS_MI_AGENTE)
    assert precision >= 0.80, f"precision@1={precision:.1%} < 80% (CTF-003)"
```

> El eval suite corre en el job `agent-eval` de CI y con `pytest tests_eval/ --no-cov`. Si tocás un agente o su lógica de reorden/cobranza, **corré el eval** antes de cerrar (ver Definition of Done).

## LLM vs fallback determinístico

- Los agentes deben funcionar **sin LLM** mediante un `_analizar_fallback()` determinístico (heurísticas). Esto permite tests sin red y un piso de calidad.
- El LLM (Anthropic SDK directo, ADR-004 — no LangChain/CrewAI) mejora la inferencia cuando está disponible, pero **no es requisito para que el agente funcione**.
- Construir Apps con IA: usá los modelos Claude más capaces y recientes (Opus/Sonnet) y prompt caching (ver skill `claude-api`).

## Anti-patrones

### Anti-patrón 1: escribir datos en `_analizar`
```python
# MAL — _analizar muta estado; se ejecuta incluso en SOMBRA
def _analizar(self, ctx):
    gasto.categoria = "X"; gasto.save()   # ¡SOMBRA no debe tocar datos!

# BIEN — inferencia pura en _analizar; escritura en _ejecutar
```

### Anti-patrón 2: inflar la confianza
```python
# MAL — forzar 0.95 para cruzar el umbral
return Prediccion(categoria=c, confianza=0.95)   # cuando la real es 0.5

# BIEN — confianza honesta; quedará como sugerencia y un humano decide
return Prediccion(categoria=c, confianza=0.55)
```

### Anti-patrón 3: acción no reversible en AUTONOMO
```python
# MAL — borra/emite algo irreversible sin posibilidad de deshacer (viola R-PROD-4)
# BIEN — soft delete / estado reversible; el humano puede revertir en el plazo configurado
```

### Anti-patrón 4: subir de nivel sin eval verde
```python
# MAL — activar AUTONOMO sin precision@1 ≥ 80% demostrada
# BIEN — eval suite verde en CI primero; luego ConfigAgente sube el nivel por empresa
```

### Anti-patrón 5: predicción sin razonamiento
```python
# MAL — Prediccion(categoria=c, confianza=0.9)  (opaco; viola R-PROD-5)
# BIEN — razonamiento explicable en lenguaje natural, persistido en PrediccionAgente
```

## Checklist final

- [ ] El agente hereda de `OmniAgente` y define `AGENTE_ID` único.
- [ ] `_analizar` no escribe datos; solo infiere y devuelve `Prediccion`.
- [ ] `_ejecutar` (si existe) es reversible (R-PROD-4) y describe lo que hizo.
- [ ] `razonamiento` explicable en lenguaje natural (R-PROD-5).
- [ ] `confianza` honesta, sin inflar para cruzar el umbral.
- [ ] Queries internas filtran por `empresa_id`.
- [ ] Existe `_analizar_fallback()` determinístico (funciona sin LLM).
- [ ] Eval suite con ≥ 25 casos dorados y precision@1 ≥ 80% verde en CI.
- [ ] El nivel AUTONOMO solo se habilita con evidencia de precisión.

## Referencias

- Código: `apps/agentes/base.py` (`OmniAgente`, `Prediccion`, `ResultadoAccion`), `apps/agentes/cobranza.py`, `apps/agentes/clasificador.py`, `apps/agentes/eval_*.py`.
- Tests: `tests_eval/test_eval_cobranza.py`, `tests_eval/test_eval_reorden.py`.
- Skill: `omni-mcp-capacidades`, `omni-multi-tenant-isolation`, `omni-testing-pytest`, `claude-api`.
- ADR-004 (Anthropic SDK directo), CTF-003 (umbral precision@1), Plan Maestro §3.5, reglas R-PROD-4 / R-PROD-5.

## Changelog

### v1.0
- Versión inicial, basada en `apps/agentes/base.py` y el eval suite.
