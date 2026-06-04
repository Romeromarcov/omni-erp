---
name: omni-ctf-deuda
description: Use this skill whenever you must introduce technical debt or an exception to a project rule in the Omni project, and cannot resolve it within the current change. Triggers include any unavoidable shortcut, a deferred fix, a `fields="__all__"` left in place, a rule (R-CODE/R-PROC) you cannot fully satisfy now, an accepted-but-not-closed security finding, or any time the Definition of Done step 6 forces you to register debt instead of fixing it. Apply it to create a Compromiso Técnico Fechado (CTF) in `docs/ctf/` with `vence_en` and `dueño` (R-PROC-6). Do NOT use for debt you can simply fix now (fix it instead), or for normal completed work with no exception.
---

# Skill: Compromisos Técnicos Fechados (CTF, R-PROC-6)

## Cuándo usar esta skill

Cargá esta skill cuando vas a **introducir deuda técnica o una excepción a una regla** y **no podés cerrarla dentro del cambio actual**. Por ejemplo:
- Dejás un `fields="__all__"` por ahora, mitigado pero no cerrado.
- Una regla R-CODE/R-PROC no se puede satisfacer 100% en este PR.
- Un hallazgo de seguridad se acepta como riesgo bajo temporalmente.
- El paso 6 del Definition of Done detecta deuda inevitable.

**Si la deuda se puede arreglar ahora, arreglala — no abras un CTF.** El CTF es para lo inevitable, no para posponer lo cómodo.

## La regla: la deuda se vence

> **Toda excepción a una regla es un Compromiso Técnico Fechado con `vence_en` y `dueño`** (R-PROC-6). La deuda no es permanente ni informal: tiene fecha de vencimiento y un responsable.

Esto evita que los atajos se vuelvan invisibles. Un `# TODO` perdido en el código no es un compromiso; un CTF sí.

## Dónde viven

`docs/ctf/CTF-NNN.md`, numerados secuencialmente. El índice está en `docs/ctf/README.md`. Los CTF cerrados se marcan como tales (no se borran: son memoria institucional).

## Formato de un CTF

Cada CTF abre con una tabla de metadatos y secciones fijas. Plantilla:

```markdown
# CTF-NNN: <título corto del compromiso>

| Campo        | Valor                                                  |
|--------------|--------------------------------------------------------|
| **ID**       | CTF-NNN                                                |
| **Título**   | <título descriptivo>                                   |
| **Regla**    | <regla afectada, ej. R-CODE-7 / CWE-915>               |
| **Estado**   | ABIERTO — <YYYY-MM-DD>                                 |
| **Fase**     | <fase en que se acepta> → <fase en que se cierra>      |
| **Vence**    | <YYYY-MM-DD>                                            |
| **Owner**    | <dueño: persona o equipo>                              |
| **Ref.**     | <hallazgo/auditoría/PR que lo origina>                 |

## Deuda

<Qué se dejó incompleto, dónde (archivos), y por qué es deuda.>

## Por qué se ACEPTA (de momento)

<Las mitigaciones presentes que hacen aceptable el riesgo AHORA. Sé honesto:
si no hay mitigación, el riesgo no es bajo y quizá no deberías diferirlo.>

## Condición de cierre

1. <Paso concreto y verificable para saldar la deuda.>
2. <...>
3. <Test que demuestra el cierre.>
```

## Cómo llenar cada campo

- **Vence:** una fecha real y razonable (no "algún día"). Convertí plazos relativos a fecha absoluta. Si es seguridad, el plazo es corto.
- **Owner:** una persona o equipo concreto (`equipo-backend`, el founder). Nunca "nadie" / "TBD".
- **Regla:** la regla R-CODE/R-PROC que se está exceptuando, o el CWE si es seguridad.
- **Por qué se acepta:** las mitigaciones reales presentes hoy. Este es el campo que distingue un riesgo bajo gestionado de una bomba de tiempo.
- **Condición de cierre:** pasos verificables, idealmente con un test que pruebe el cierre.

## Flujo de trabajo

1. Detectás deuda inevitable (típicamente en el paso 6 del Definition of Done).
2. Mirá `docs/ctf/README.md` para el siguiente número libre.
3. Creá `docs/ctf/CTF-NNN.md` con la plantilla.
4. Agregá la línea al índice en `docs/ctf/README.md`.
5. **Enlazá el CTF desde el PR** (sección "Compromisos Técnicos Fechados creados" de la plantilla de `omni-pr-discipline`).
6. Si dejaste un marcador en el código, que apunte al CTF: `# CTF-NNN: whitelist pendiente` — no un `# TODO` huérfano.

## Cerrar un CTF

Cuando se salda la deuda:
1. Implementá la condición de cierre (con su test).
2. Cambiá **Estado** a `CERRADO — <YYYY-MM-DD>` y anotá el PR que lo cerró.
3. Actualizá el índice en `docs/ctf/README.md`.

## Anti-patrones

### Anti-patrón 1: abrir CTF para no hacer trabajo fácil
```
# MAL — "abro un CTF para mover esta validación que me toma 5 minutos"
# BIEN — si se arregla ahora, se arregla ahora. El CTF es para lo inevitable.
```

### Anti-patrón 2: CTF sin fecha o sin dueño
```
# MAL — Vence: TBD / Owner: nadie  → es deuda informal, justo lo que R-PROC-6 prohíbe
# BIEN — fecha absoluta + responsable concreto
```

### Anti-patrón 3: `# TODO` en vez de CTF
```python
# MAL
# TODO: arreglar el aislamiento acá algún día

# BIEN
# CTF-012: filtro de empresa pendiente de endurecer (vence 2026-09-01, owner equipo-backend)
```

### Anti-patrón 4: "por qué se acepta" vacío o falso
```
# MAL — declarar riesgo bajo sin mitigación real
# BIEN — listar las mitigaciones presentes; si no hay, no lo difieras
```

### Anti-patrón 5: CTF que nadie enlaza
```
# MAL — el CTF existe pero el PR no lo menciona y el código no lo referencia
# BIEN — enlazado desde el PR y desde el marcador en el código
```

## Checklist final

- [ ] La deuda es genuinamente inevitable en este cambio (no se podía arreglar ahora).
- [ ] CTF creado en `docs/ctf/CTF-NNN.md` con la tabla de metadatos completa.
- [ ] `Vence` con fecha absoluta razonable; `Owner` concreto.
- [ ] "Por qué se acepta" lista mitigaciones reales presentes hoy.
- [ ] "Condición de cierre" con pasos verificables y un test.
- [ ] Agregado al índice `docs/ctf/README.md`.
- [ ] Enlazado desde el PR; cualquier marcador en código apunta al CTF (no `# TODO` huérfano).

## Referencias

- Ejemplos reales: `docs/ctf/CTF-001.md` … `CTF-006.md`, índice en `docs/ctf/README.md`.
- Skill: `omni-definition-of-done` (paso 6), `omni-pr-discipline` (sección CTF del PR).
- Regla R-PROC-6 (los compromisos técnicos se vencen), R-PROC-7 (la deuda no se pospone).

## Changelog

### v1.0
- Versión inicial, basada en el formato de `docs/ctf/`.
