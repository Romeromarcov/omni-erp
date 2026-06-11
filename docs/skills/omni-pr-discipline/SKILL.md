---
name: omni-pr-discipline
description: Use this skill whenever you are preparing to open, finalize, or update a Pull Request in the Omni project. Triggers include any task that has reached implementation phase and is moving toward delivery, requests like "open the PR", "finalize this", "ready for review", "what should the PR description say", or any time you've completed code changes and need to package them for human review. Apply this skill in EVERY PR without exception. Do NOT use for tasks that are still in design/exploration phase or for purely documentation updates that don't go through PR review.
---

# Skill: Disciplina para Preparar y Entregar un PR

## Cuándo usar esta skill

Cargá esta skill **antes de abrir cualquier PR**, sin excepción. También cuando vas a actualizar un PR existente con nuevos commits.

Casos típicos:
- Terminaste la implementación y vas a hacer push.
- Vas a marcar un PR como "ready for review" (en este proyecto, casi siempre se queda en draft hasta que el revisor humano lo apruebe — el agente NO marca ready).
- Vas a responder comentarios de un revisor y volver a entregar.

## Por qué importa esta disciplina

Un PR bien preparado:
- Se revisa más rápido (el revisor entiende contexto sin perder tiempo).
- Detecta problemas antes (al hacer auto-checklist, vos mismo encontrás cosas).
- Facilita rollback si algo sale mal después.
- Sirve como documentación histórica del "por qué".

Un PR mal preparado:
- Se rechaza o se devuelve por información faltante.
- Esconde problemas que aparecen después.
- Genera fricción innecesaria con el revisor.

## Pre-requisitos antes de abrir PR

Verificá ANTES de empezar a redactar el PR:

### Verificación 1: Build local

```bash
# Backend
cd backend
python manage.py check
pytest --no-cov -x -q  # Tests rápidos
python manage.py makemigrations --check --dry-run  # No deben haber migraciones sin generar

# Frontend
cd ../frontend
npm run type-check
npm run lint
```

**Si algo falla, NO abras el PR. Arreglá primero.**

### Verificación 2: Tamaño del PR

Contá las líneas del diff (sin tests, sin migrations, sin package locks):

```bash
git diff main...HEAD --stat | grep -v "test_\|migrations\|package-lock\|pnpm-lock\|yarn.lock"
```

| Tamaño | Acción |
|--------|--------|
| < 300 líneas | OK, procedé |
| 300-800 líneas | OK pero asegurate de que sea cohesivo |
| 800-1500 líneas | Considerá dividir; si genuinamente no se puede dividir, justificá en la descripción |
| > 1500 líneas | DIVIDÍ. PR muy grande de un solo agente significa que la tarea estaba mal acotada |

### Verificación 3: Cohesión

¿Todos los cambios responden a una sola idea? Si en el commit log tenés:
- "agregar modelo X"
- "fix typo en Y"
- "refactor de Z"

**Eso es 3 PRs, no uno.** Separá si es posible.

### Verificación 4: Sin código de debug

```bash
# Buscar prints, console.log, debugger, breakpoint
grep -rn "console\.log\|debugger" frontend/src/ --include="*.ts" --include="*.tsx"
grep -rn "print(\|breakpoint(\|import pdb" backend/apps/
```

Resultados: **vacíos.** Si encontrás algo, remové.

### Verificación 5: Sin secretos

```bash
# Buscar patrones de secrets
grep -rn "api_key\s*=\|password\s*=\|secret\s*=" --include="*.py" --include="*.ts" backend/ frontend/ \
  | grep -v "settings\|config\|env\|test"
```

Si encontrás algo que parezca un secreto real (no un placeholder, no un nombre de variable), **detené el flow y reportá al supervisor humano inmediatamente.**

## Mensajes de commit

### Formato estándar

Mensajes en **español**, **imperativo**, **una línea descriptiva** + cuerpo opcional.

```
agrega modelo Producto en módulo inventario

Implementa Producto con campos básicos (nombre, código, precio).
Incluye test de aislamiento multi-tenant. La integración con
movimientos de inventario queda para próximo PR.

Refs: spec-001
```

### Verbos en imperativo

| Mal | Bien |
|-----|------|
| agregando modelo | agrega modelo |
| agregué modelo | agrega modelo |
| Modelo agregado | agrega modelo |
| Add new model | agrega modelo |

### Tipos de cambio (prefijos opcionales)

Si el equipo adopta convención tipo Conventional Commits:

```
feat: agrega modelo Producto en inventario
fix: corrige cálculo de IVA en facturas en moneda extranjera
refactor: separa ModalPago en componentes
test: agrega tests de aislamiento para Producto
docs: actualiza README con instrucciones de setup
chore: actualiza dependencia de Django a 5.0.4
```

Confirmá con el responsable cuál convención usa el proyecto. Si no hay convención establecida, usá frases descriptivas en imperativo sin prefijo.

### Mensajes que NO usás

```
# MAL
"misc changes"
"updates"
"WIP"  (excepto en commits temporales que después squashás)
"fix"  (sin contexto)
"asdf"  (en serio, no hagas esto)
```

## Estructura del PR

### Plantilla obligatoria de descripción

Toda descripción de PR sigue esta estructura. **Sin esta plantilla, el PR no se acepta.**

```markdown
## Resumen

[2-4 líneas: qué cambia y por qué. Sin jerga innecesaria. Imaginá que lo lee
alguien que no estuvo en la sesión.]

## Conexión con el plan

- **Bloque/Fase:** [0/1/2/3/...]
- **Sub-fase:** [1.A / 1.B / etc.]
- **Workstream:** [si aplica]
- **Definition of Done que contribuye:** [item específico del plan]
- **Tarea origen:** [referencia a la tarea que asignó el responsable]

## Reglas verificadas (auto-checklist)

### Reglas de código
- [ ] R-CODE-1 (multi-tenant): [N/A o cómo se cumple]
- [ ] R-CODE-2 (no SQLite): [confirmado]
- [ ] R-CODE-3 (sin any/print): [confirmado]
- [ ] R-CODE-4 (Decimal para dinero): [N/A o confirmado]
- [ ] R-CODE-5 (UUIDv7): [N/A o confirmado]
- [ ] R-CODE-6 (soft delete): [N/A o confirmado]
- [ ] R-CODE-7 (API-first): [N/A o confirmado]
- [ ] R-CODE-8 (sin secretos): [confirmado]
- [ ] R-CODE-9 (tests integración para flujos críticos): [confirmado/N tests añadidos]
- [ ] R-CODE-10 (no null=True en obligatorios): [N/A o confirmado]

### Reglas de proceso
- [ ] R-PROC-2 (PR pequeño y focal): diff sin tests/migrations: [N líneas]
- [ ] CI verde local: [confirmado]
- [ ] Migración reversible (si aplica): [N/A o probada]

## Eventos emitidos / consumidos

[Lista de eventos de dominio nuevos o modificados, o "N/A"]

## Capacidades MCP expuestas / modificadas

[Lista de capacidades MCP nuevas o modificadas, o "N/A"]

## Decisiones tomadas

- [Decisión 1]: [razón breve]
- [Decisión 2]: [razón breve]

[Si tomaste alguna decisión que requirió juicio durante la implementación,
documentala. Si no requirió juicio, dejá "Ninguna decisión más allá de
seguir las skills aplicables".]

## Lo que NO hice (y por qué)

- [Cosa 1 que pude haber hecho pero no hice]: [razón]
- [Cosa 2]: [razón]

[Importante para que el revisor sepa que no es olvido sino decisión.]

## Compromisos Técnicos Fechados creados

[Si propusiste algún CTF, link al issue. Si no, "Ninguno".]

## Riesgos para el reviewer

[Qué mirar con especial atención. Áreas frágiles. Casos edge. Cualquier
cosa que vos como autor del código sospeches que puede romper.]

## Cómo probar manualmente

[Pasos concretos para verificar que el cambio funciona.]

1. [Paso]
2. [Paso]
3. [Resultado esperado]

## Screenshots (si aplica)

[Para cambios de UI.]
```

### Cómo llenar cada sección

**Resumen:** lo más importante. Imaginá que el reviewer va a leer 50 PRs hoy. Tu resumen debe captar la esencia en 10 segundos.

Mal resumen:
> Implementación del modelo Producto.

Buen resumen:
> Crea el modelo `Producto` en el módulo `inventario` con campos básicos
> (nombre, código, precio, categoría, unidad). Incluye viewset con búsqueda
> y filtros, serializers con validaciones de monto, y test de aislamiento
> multi-tenant. No incluye lógica de movimientos (queda para próximo PR).

**Reglas verificadas:** marca cada checkbox con honestidad. Si una regla no aplica, escribí "N/A" y la razón. Si no la verificaste, **vuelve y verificala**, no marques sin estar segura.

**Decisiones tomadas:** todas las decisiones que tomaste sin consultar. Aunque te parezcan obvias, escribilas. Le ahorra tiempo al revisor (no tiene que adivinar qué pensaste) y te protege a vos (queda registro).

**Lo que NO hice:** esta sección la subestima la mayoría. Es importantísima. Ejemplos:

> - No agregué endpoint de "exportar a Excel" porque la spec no lo pedía y agregaría 80 líneas y dependencia nueva.
> - No optimicé las queries con `select_related` en el listado porque el N de productos esperado es bajo (<500); lo añadiremos cuando sea necesario.
> - No agregué validación de duplicados por nombre porque el código_unique ya garantiza unicidad por empresa.

**Riesgos para el reviewer:** sé honesta. Áreas que te dejaron dudas:

> - El cálculo de margen porcentaje en `services.py` línea 45: usé Decimal pero el redondeo puede ser distinto al que el contador del cliente espera. Conviene validar con él.
> - El test de aislamiento prueba GET y PATCH pero no DELETE; debería estar OK pero no lo verifiqué explícitamente.

## Estado del PR: draft vs ready

Depende de la rama base (política actualizada por el owner el 2026-06-11, ver
`docs/FLUJO_DE_TRABAJO.md`):

- **PR a `develop`:** se abre en draft; con **CI completo en verde + gate corrido**, un
  agente revisor **distinto del autor** revisa el diff, lo marca ready, aprueba y mergea.
- **PR `develop`→`main` (producción):** el agente **NUNCA** lo marca ready ni lo mergea;
  esa puerta es exclusiva del revisor humano (owner).

Marcar ready/mergear sin CI verde o sin revisión del segundo agente da señal falsa de
"está listo" y rompe la confianza del flujo.

## Después de abrir el PR

### Reportá la entrega

Inmediatamente después de abrir el PR, mandá al supervisor (operador o responsable) este mensaje:

```
Entrega: [título de la tarea]

Lo que hice: [3-5 líneas]
PR: [link al PR]
Tests: [pasan / N agregados]
Reglas verificadas: [auto-checklist completo en el PR]

Decisiones que tomé:
- [Decisión 1]: [razón]
- [Decisión 2]: [razón]

Lo que NO hice (y por qué):
- [Cosa]: [razón]

Recomiendo siguiente paso: [próxima tarea natural]

Listo para tu revisión.
```

## Cuando el revisor pide cambios

### Recibís comentarios

El revisor va a dejar comentarios en el PR pidiendo cambios. Tu protocolo:

1. **Leé todos los comentarios primero antes de responder.** Algunos pueden estar relacionados.
2. **Para cada comentario, decidí:**
   - **Acordás:** vas a hacer el cambio.
   - **No estás segura:** preguntá clarificación antes de hacer cambios.
   - **No acordás:** explicá por qué con argumentos técnicos. **Si el revisor mantiene el comentario, acatás.**

3. **Hacé los cambios en commits separados**, no enmiendes commits anteriores. Los commits separados permiten ver qué cambió en respuesta al review.

```bash
# Ejemplo de commits de respuesta a review
git commit -m "ajusta validación de monto según review (#143)"
git commit -m "agrega test de DELETE solicitado en review (#143)"
```

4. **Después de hacer los cambios, respondé a cada comentario con "Done" o explicación.**

5. **Re-pedí review** mencionando los cambios:

```
Hice los siguientes ajustes según tu review:
- [Cambio 1]: commit abc123
- [Cambio 2]: commit def456

Sobre [punto que no acordamos]: [tu argumento o aceptación]

Listo para nueva revisión.
```

### Cuando aprueban

Cuando el revisor aprueba:
- **NO mergeás vos.** El revisor humano hace el merge.
- Esperás confirmación.
- Limpiás tu branch local cuando confirmen merge.

```bash
git checkout main
git pull
git branch -d feature/tarea-completada
```

## Anti-patrones

### Anti-patrón 1: PR sin auto-checklist

**Síntoma:** abrís PR con descripción "implementé X" y nada más.
**Por qué falla:** el revisor tiene que hacer todo el trabajo de descubrimiento.
**Antídoto:** plantilla obligatoria con todos los items.

### Anti-patrón 2: PR enorme

**Síntoma:** 2000 líneas de cambios en un solo PR.
**Por qué falla:** imposible de revisar bien. Errores se cuelan. Toma horas revisar.
**Antídoto:** dividir en PRs incrementales mergeables independientemente.

### Anti-patrón 3: Mezclar refactor con feature

**Síntoma:** "implementé feature X y de paso refactoricé módulo Y."
**Por qué falla:** no se puede revisar la feature sin entender el refactor; revertir uno arrastra el otro.
**Antídoto:** PR de refactor primero (mergeado), después PR de feature limpio.

### Anti-patrón 4: PR sin tests

**Síntoma:** "los tests vienen en el próximo PR."
**Por qué falla:** los tests del próximo PR nunca llegan. La feature queda sin red de seguridad.
**Antídoto:** tests en el mismo PR. Sin excepción salvo refactor mecánico explícitamente marcado.

### Anti-patrón 5: Auto-checklist marcado sin verificar

**Síntoma:** todos los items marcados con check, pero el revisor encuentra que el código no cumple.
**Por qué falla:** rompe la confianza. La próxima vez el revisor va a verificar todo manualmente, perdiendo el valor del checklist.
**Antídoto:** **honestidad absoluta**. Si no verificaste algo, no lo marqués.

### Anti-patrón 6: Mensaje de PR genérico

**Síntoma:** "este PR implementa lo solicitado."
**Por qué falla:** no aporta información. El revisor pierde tiempo.
**Antídoto:** descripción concreta del qué, por qué, y los detalles relevantes.

### Anti-patrón 7: Marcar ready / mergear sin cumplir la política

**Síntoma:** marcás ready o mergeás un PR a `develop` sin CI verde o sin revisión de un
segundo agente; o tocás la puerta `develop`→`main` que es exclusiva del humano.
**Por qué falla:** salta la fase de revisión, riesgo de merge prematuro a staging o prod.
**Antídoto:** PR a `develop` solo se autoaprueba con CI verde + revisión de otro agente;
`develop`→`main` lo decide únicamente el revisor humano.

### Anti-patrón 8: Responder review con resistencia

**Síntoma:** el revisor pide cambio, vos discutís 5 mensajes defendiendo tu opción.
**Por qué falla:** el revisor humano sabe cosas que vos no (contexto del proyecto, gusto del cliente, decisiones futuras). Discutir excesivamente es perder tiempo y respeto.
**Antídoto:** una vuelta de aclaración si genuinamente creés que hay un malentendido. Si el revisor mantiene su pedido, acatás.

## Checklist final antes de abrir PR

- [ ] Build local verde (backend + frontend).
- [ ] Tests pasan localmente.
- [ ] Lint y type-check sin errores.
- [ ] No hay prints, console.log, ni debug code.
- [ ] No hay secretos en el código.
- [ ] Diff sin tests/migrations < 800 líneas (o justificado si más).
- [ ] Mensajes de commit en español, imperativo, descriptivos.
- [ ] PR en estado draft (no ready).
- [ ] Plantilla de descripción completa con TODOS los items.
- [ ] Auto-checklist marcado con honestidad.
- [ ] Decisiones tomadas documentadas.
- [ ] Sección "Lo que NO hice" llenada.
- [ ] Riesgos para el reviewer identificados.
- [ ] Mensaje de entrega listo para enviar al supervisor.

## Referencias

- Skill: `omni-django-module` (estructura de módulos).
- Skill: `omni-multi-tenant-isolation` (verificación de aislamiento).
- Documento: protocolo de revisión humana (lo que el revisor busca).
- Reglas R-CODE-1 a R-CODE-10 del plan de ejecución.

## Changelog

### v1.0 — Día 1
- Versión inicial.
