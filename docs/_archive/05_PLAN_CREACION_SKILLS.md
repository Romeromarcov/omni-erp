# Plan de Creación de Skills — Fases 0, 1 y 2

**Versión:** 1.0
**Audiencia:** vos (responsable) y el agente IA cuando le encargues skills.
**Propósito:** definir qué skills se crean, cuándo, cómo, y por qué este orden.

> **Antes de leer:** este plan asume que ya leíste el documento donde mapeamos todas las skills posibles del proyecto. Si no, ese documento define qué hace cada skill. Este define cuándo y cómo se crean.

---

## ÍNDICE

- [PARTE 1 — La Filosofía: Skills "Just-in-Time"](#parte-1)
- [PARTE 2 — Las Tres Capas Temporales](#parte-2)
- [PARTE 3 — Capa 1: Skills del Día 1 (vos las escribís)](#parte-3)
- [PARTE 4 — Capa 2: Skills de Fase 0 (creadas durante mes 1)](#parte-4)
- [PARTE 5 — Capa 3: Skills bajo demanda en Fases 1-2](#parte-5)
- [PARTE 6 — Cómo Pedirle al Agente que Cree una Skill](#parte-6)
- [PARTE 7 — Cómo Revisar una Skill que el Agente Creó](#parte-7)
- [PARTE 8 — Mantenimiento y Evolución de Skills](#parte-8)
- [PARTE 9 — Anti-Patrones de Skills](#parte-9)

---

# PARTE 1 — La Filosofía: Skills "Just-in-Time"

## 1.1 La regla central

**Una skill se crea cuando se necesita, no antes.**

Esto es contraintuitivo si venís de pensar "preparemos todo de antemano". Pero en el contexto de skills para un agente IA, las que se crean por adelantado tienen tres problemas:

1. Capturan suposiciones, no aprendizajes.
2. No reflejan el código real que existe (porque aún no existe).
3. Cuando llega el momento de usarlas, igual hay que reescribirlas.

## 1.2 Las dos excepciones a la regla

**Excepción 1 — Skills que el agente necesita en su primer commit.**
Sin ellas, los primeros PRs salen mal y arrastran problemas. Estas se crean antes (vos las escribís, no el agente).

**Excepción 2 — Skills sobre dominio que el agente no conocería de fábrica.**
Fiscalidad venezolana, convenciones de nombres en español, terminología local. El agente no las puede improvisar. Estas también se crean antes.

Todo lo demás se crea cuando llega el momento, con conocimiento del código real.

## 1.3 La promesa que esto te hace

Si seguís este plan, terminás con:
- 5 skills del día 1 (vos las escribís, ya las tenés).
- 4-6 skills creadas durante Fase 0 (en momentos específicos del mes 1).
- 8-12 skills creadas durante Fases 1-2 (bajo demanda real).

**Total: 17-23 skills de calidad, no 30 skills genéricas.**

Y crucialmente, cada una tiene una historia clara de por qué existe y qué problema concreto resuelve.

---

# PARTE 2 — Las Tres Capas Temporales

## 2.1 Capa 1 — Día 1 (antes de cualquier código)

**Cuándo:** ahora, antes de que el agente toque código.
**Quién las escribe:** **vos** (con mi ayuda; las entrego junto a este plan).
**Por qué vos y no el agente:** el agente no tiene contexto suficiente para escribirlas bien. Estas son las que aseguran que el primer código que escriba sea correcto.

**Las 5 skills:**

| # | Nombre | Razón crítica |
|---|--------|---------------|
| D1.1 | `omni-django-module` | Convenciones de cualquier módulo Django nuevo |
| D1.2 | `omni-multi-tenant-isolation` | Bug más caro de detectar después; debe estar bloqueado de entrada |
| D1.3 | `omni-decimal-money` | Errores de céntimos en producción son devastadores |
| D1.4 | `omni-pr-discipline` | Estandariza el flujo de entrega desde el primer PR |
| D1.5 | `omni-venezuela-fiscal` | Conocimiento de dominio que el agente no tiene |

Las cuatro primeras se aplican a casi cualquier tarea. La quinta solo cuando se trabaja en facturación, retenciones, libros fiscales — pero eso pasa muy temprano (Mes 3).

## 2.2 Capa 2 — Fase 0 (durante mes 1)

**Cuándo:** durante el primer mes, en momentos específicos, según se van necesitando.
**Quién las escribe:** el agente, bajo tu supervisión, usando el protocolo de PARTE 6.
**Por qué durante Fase 0:** porque las primitivas AI-nativas (event sourcing, MCP, agentes) se construyen ahí. El agente las pisa, aprende los patrones reales, y entonces escribe la skill bien.

**Las skills esperadas:**

| # | Nombre | Cuándo crearla | Disparador |
|---|--------|----------------|------------|
| F0.1 | `omni-event-sourcing` | Semana 7-9 | Cuando se implementa el event store inicial con dominio `ventas` |
| F0.2 | `omni-mcp-server` | Semana 10-11 | Cuando se exponen los primeros módulos como MCP |
| F0.3 | `omni-test-strategy` | Semana 2-3 | Cuando se establecen los patrones de tests del proyecto |
| F0.4 | `omni-migration-guide` | Cuando aparezca la primera migración compleja | Disparador: bug o conflicto de migración |
| F0.5 | `omni-debt-management` | Cuando se cree el primer Compromiso Técnico Fechado | Naturaleza |
| F0.6 | `omni-agent-construction` | Semana 12-13 | Cuando se construye el primer agente operativo |
| F0.7 | `omni-eval-suite` | Semana 12-13 | Junto con F0.6 |

## 2.3 Capa 3 — Fases 1-2 (bajo demanda)

**Cuándo:** según se van necesitando durante meses 2 al 9-15.
**Quién las escribe:** el agente, bajo tu supervisión.
**Por qué bajo demanda:** porque sin pisar el problema concreto no se puede escribir una skill útil.

**Las skills esperadas (probables, no garantizadas):**

| # | Nombre | Cuándo probablemente surge | Por qué |
|---|--------|----------------------------|---------|
| F1.1 | `omni-venezuela-payments` | Mes 3-4 | Cuando se implementan métodos de pago |
| F1.2 | `omni-venezuela-labor` | Mes 7-8 | Si la fábrica empieza a usar pagos a destajo |
| F1.3 | `omni-bcv-rates` | Mes 2-3 | Cuando se implementa multimoneda |
| F1.4 | `omni-personalization-dsl` | Mes 5 | Cuando se construye el motor de personalización |
| F1.5 | `omni-localization-pack` | Mes 8-10 | Cuando se empaqueta la localización VE |
| F2.1 | `omni-pos-patterns` | Mes 7 | Cuando se construye el POS |
| F2.2 | `omni-bom-and-mrp` | Mes 10-11 | Cuando se construyen BOMs para la fábrica |
| F2.3 | `omni-cobranza-patterns` | Mes 5-6 | Cuando el agente de cobranza muestra patrones repetidos |

**Esta lista no es prescripción.** Es predicción. Las skills reales que se crean dependen de los patrones que efectivamente aparezcan en el código. Algunas de esta lista no se crean nunca porque no se necesitan; otras nuevas que no anticipo aparecen.

## 2.4 Lo que NO se crea en Fases 0-2

Skills que están en el mapeo pero que **no corresponde crear hasta Fase 3+**:

- `omni-platform-spaces` (Fase 4)
- `omni-blockchain-anchoring` (Fase 5+)
- `omni-mexico-fiscal` (Fase 3 cuando expandís)
- `omni-mobile-app-builder` (Fase 4)
- `omni-marketplace-publisher` (Fase 3)
- `omni-iot-integration` (Fase 2 tardía o Fase 3)

Si te tienta construir alguna antes, releé la PARTE 1.

---

# PARTE 3 — Capa 1: Skills del Día 1

> **Buenas noticias: estas 5 skills te las entrego ya escritas en archivos separados, listas para usar. Solo las copiás al directorio del proyecto.**

## 3.1 Cómo instalar las skills del día 1

Las 5 skills llegan como archivos `SKILL.md` en carpetas separadas. Instalación:

```
proyecto-omni/
├── docs/
│   └── skills/
│       ├── omni-django-module/
│       │   └── SKILL.md
│       ├── omni-multi-tenant-isolation/
│       │   └── SKILL.md
│       ├── omni-decimal-money/
│       │   └── SKILL.md
│       ├── omni-pr-discipline/
│       │   └── SKILL.md
│       └── omni-venezuela-fiscal/
│           └── SKILL.md
```

## 3.2 Cómo el agente las descubre

En tu mensaje inicial al agente, además del protocolo de arranque, agregás:

> "Las skills del proyecto están en `docs/skills/`. Antes de cualquier tarea, revisá si alguna skill aplica al trabajo. Si la descripción de la skill matchea con la tarea, leé el SKILL.md completo y seguí sus convenciones."

Si tu agente es Claude Code o similar, va a descubrir las skills automáticamente al inicio de cada sesión.

## 3.3 Validación de que están funcionando

En las primeras 2-3 sesiones, observá:

- ¿El agente menciona las skills cuando hace tareas relacionadas?
- ¿Sigue las convenciones que ahí están?
- ¿Cuando hay conflicto entre lo que escribiría por defecto y la skill, gana la skill?

Si no las usa, el problema puede ser:
1. La descripción de la skill no se activa con las tareas que estás dando.
2. El agente no ubicó el directorio.
3. Necesita instrucción más explícita en cada tarea.

Iterás según veas.

---

# PARTE 4 — Capa 2: Skills de Fase 0

## 4.1 Filosofía de creación durante Fase 0

Durante el primer mes, el agente está construyendo las primitivas AI-nativas. **Cada vez que termina de implementar una primitiva nueva, hay una decisión a tomar:**

¿Se va a usar este patrón en otros lugares del código en el futuro? Si la respuesta es sí, es momento de capturarlo en una skill.

Esto es lo que se llama "extracción de patrón después de tres usos" pero adaptado al contexto AI-nativo: en lugar de esperar tres usos, capturás el patrón después del **primer uso completo y validado**.

## 4.2 Disparadores para crear skills durante Fase 0

| Cuando pase esto... | ...crear esta skill |
|---------------------|---------------------|
| Se implementa el primer test de aislamiento multi-tenant | (Ya cubierto por D1.2 del día 1) |
| Se establece el patrón de tests del proyecto | F0.3 — `omni-test-strategy` |
| Se crea la primera migración compleja con datos | F0.4 — `omni-migration-guide` |
| Se acepta el primer Compromiso Técnico Fechado | F0.5 — `omni-debt-management` |
| Se implementa el event store con primer dominio | F0.1 — `omni-event-sourcing` |
| Se expone el primer módulo como servidor MCP | F0.2 — `omni-mcp-server` |
| Se construye el primer agente operativo | F0.6 — `omni-agent-construction` y F0.7 — `omni-eval-suite` |

## 4.3 El protocolo: cuándo exactamente le pedís al agente que escriba la skill

**Momento ideal:** **inmediatamente después de mergear el PR donde se implementó por primera vez el patrón**, antes de avanzar a la próxima tarea.

Por ejemplo:

1. Asignás tarea "implementar event store con dominio ventas" (semana 7-9).
2. El agente trabaja, abre PR.
3. Vos revisás, pedís ajustes, finalmente mergeás.
4. **Antes de la próxima tarea, le pedís: "Ahora escribí la skill `omni-event-sourcing` capturando el patrón que acabamos de establecer."**
5. El agente escribe la skill.
6. Vos la revisás (PARTE 7).
7. Mergeás la skill.
8. Recién ahí avanzás a la próxima tarea de producto.

**Por qué este momento exacto:** el agente tiene fresco el contexto de lo que acaba de hacer, las decisiones que tomó, los errores que cometió en el camino. Si esperás dos semanas, ese contexto se pierde.

## 4.4 Estimación de tiempo

Crear una skill durante Fase 0 toma típicamente:

- **30-60 min de trabajo del agente** escribiéndola.
- **30-45 min tuyos revisándola.**
- Total: 1-1.5 hrs por skill.

Sumando las 6-7 skills de Fase 0, son aproximadamente **6-10 horas extra durante el mes 1**. Distribuido en sesiones, son 1-2 sesiones extras o algunas sesiones más largas.

**Es una inversión real.** Pero las skills bien hechas se pagan solas en las próximas 50 tareas que dependen de ese patrón.

---

# PARTE 5 — Capa 3: Skills bajo demanda en Fases 1-2

## 5.1 Filosofía de creación durante Fases 1-2

Durante meses 2 al 9-15, **vas a estar construyendo features de producto, no infraestructura.** El criterio para crear una skill cambia:

**Crear skill cuando:**

1. **El agente repite el mismo error en dos tareas distintas.** Ej: olvida agregar IGTF en cálculos de venta dos veces. Skill: convenciones de cálculo fiscal VE.

2. **Vos repetís la misma corrección en dos PRs distintos.** Ej: en cada PR de cobranza tenés que pedirle que use el patrón X. Skill: patrones de módulo de cobranza.

3. **Una tarea va a requerir el mismo patrón implementado 3+ veces a futuro.** Ej: vas a tener varios módulos con POS-like behavior. Skill: patrones de POS antes del segundo POS.

4. **Aparece un dominio nuevo que el agente no conoce.** Ej: pago a destajo (LOTTT). Skill: convenciones laborales VE.

5. **Una decisión arquitectónica establecida tiene que ser respetada en muchos lugares.** Ej: cómo modelar relaciones entre tenants para el futuro Platform Spaces (aunque no construyas Platform Spaces aún). Skill: futuro-proofing arquitectónico.

**NO crear skill cuando:**

1. Es solo un gusto personal sobre estilo (eso va al linter, no a una skill).
2. Es algo que va a aparecer una sola vez.
3. Es algo que el agente ya hace bien sin guía.
4. Es información que cambia cada mes (versiones de librerías, etc.).

## 5.2 Tu rutina de detección de skills necesarias

Durante tu revisión semanal de PRs (PARTE 4 del Protocolo de Revisión Humana), agregá esta pregunta:

**"¿Vi un patrón esta semana que valga la pena capturar como skill?"**

Si la respuesta es sí, lo anotás en una lista. No la creás ya; primero verificás:
- ¿Es la primera vez que veo este patrón? Esperá la segunda vez.
- ¿Es la segunda vez? Probablemente sí, creá la skill.

## 5.3 Cómo agendás la creación

Las skills nuevas no son tareas urgentes. Tu sistema:

- **Lista de skills pendientes de crear** en `docs/skills/_backlog.md`.
- Cuando hay una sesión "ligera" (no hay tarea de producto urgente, o el agente terminó antes), le encargás una skill del backlog.
- **No creás skills en sesiones donde estás empujando un milestone.**

## 5.4 Estimación

Skills durante Fases 1-2 típicamente toman lo mismo que las de Fase 0: 1-1.5 hrs entre creación y revisión. **A lo largo de 8-12 meses, son 8-15 horas de tu tiempo.** Manejable.

---

# PARTE 6 — Cómo Pedirle al Agente que Cree una Skill

## 6.1 Plantilla de prompt para crear una skill

Cuando le encargues al agente crear una skill, usá exactamente este formato:

```
Tarea: crear la skill `<nombre-de-la-skill>`.

Contexto:
- Acabamos de implementar/usar el patrón en [PR específico, archivo, módulo].
- Esta skill debe capturar las convenciones, plantillas, y errores comunes de ese patrón para que en el futuro tu trabajo y el de otros agentes sea más consistente.

Instrucciones específicas:
1. Lee atentamente el código que acabamos de escribir/mergear: [archivos específicos].
2. Lee skills existentes en `docs/skills/` para entender el formato y estilo.
3. Identifica:
   - Las convenciones que establecimos (nombres, estructura, patrones).
   - Los errores que cometiste y corregimos en el camino.
   - Las decisiones que se tomaron y deberían respetarse a futuro.
4. Crea la skill en `docs/skills/<nombre-de-la-skill>/SKILL.md` siguiendo:
   - El frontmatter con name y description (description optimizada para que se cargue cuando corresponde — ver guía interna).
   - Estructura: Cuándo usar, Plantillas, Convenciones, Checklist, Errores comunes, Referencias.
   - Tono directo, ejemplos concretos del código real del proyecto.
   - Largo objetivo: 200-500 líneas. Si es más corta, faltan detalles. Si es más larga, está sobre-especificada.

Antes de empezar:
- Reformulá la tarea con tus palabras.
- Mostrame qué archivos vas a leer y qué patrones vas a capturar.
- Esperá mi confirmación antes de empezar a escribir.

Después de terminar:
- Abrí PR draft.
- Documentá qué decisiones tomaste sobre qué incluir y qué dejar fuera.
```

## 6.2 La parte crítica: el `description` del frontmatter

La skill se carga (o no) cuando el agente decide leerla. Esa decisión la toma leyendo el `description`. Por eso el `description` es la parte más importante de toda la skill.

Reglas para un `description` que funciona:

1. **Empezá con "Use this skill whenever..."** o "Use this skill when..." en tercera persona.
2. **Sé específica sobre el trigger:** menciona archivos, patrones, palabras clave que aparecen en las tareas que deberían activar la skill.
3. **Decí cuándo NO usarla:** "Do NOT use for tasks that..." — esto es tan importante como el trigger positivo.
4. **No la hagas demasiado genérica.** "Use this skill for any Python code" no sirve; se carga siempre y se ignora siempre.
5. **No la hagas demasiado específica.** "Use this skill when implementing the second cobranza module" tampoco sirve.

**Ejemplo bueno:**

```yaml
description: Use this skill whenever you create a new Django module or add models, viewsets, or serializers to an existing one in the Omni project. Triggers include any task that touches files under `backend/apps/<module>/`, requests like "create a new module for X", "add model Y to module Z", or any work involving `BaseModel`, `BaseModelViewSet`, or multi-tenant isolation patterns. Do NOT use for tasks that only modify frontend, only modify migrations of pre-existing models without schema changes, or pure documentation tasks.
```

**Ejemplo malo:**

```yaml
description: Skill for working with Django modules in Omni.
```

(Demasiado vago, no dice cuándo aplica ni cuándo no.)

## 6.3 Cuántas iteraciones esperar

Es normal que la primera versión de una skill no esté del todo bien. Esperá:

- **Iteración 1:** primer borrador del agente.
- **Iteración 2:** después de tu feedback, ajustes principales.
- **A veces iteración 3:** ajustes finos al `description` o errores comunes.

Si llegás a 4 iteraciones, **el problema probablemente no es la skill — es que vos no tenés claro qué pattern querés capturar**. Pausá, pensá, y reformulá la tarea.

---

# PARTE 7 — Cómo Revisar una Skill que el Agente Creó

## 7.1 Tu protocolo de revisión

A diferencia de revisar código, revisar una skill es más sobre juicio editorial. Tu protocolo:

### Paso 1 — Leer el `description` (5 min)

- ¿Activa cuándo debe activar?
- ¿No activa cuando no debe?
- ¿Tiene el "Do NOT use" claro?

**Test mental:** pensá en 5 tareas distintas que podrías asignar al agente. Para cada una, ¿esta skill se cargaría correctamente?

- Si en alguna se carga cuando no debería: el `description` es muy amplio.
- Si en alguna no se carga cuando debería: el `description` es muy estrecho.

Pedí ajustes hasta que pase el test mental.

### Paso 2 — Leer la sección "Cuándo usar" (5 min)

Debe ser consistente con el `description` pero más larga y para humanos. Verificás que coincidan.

### Paso 3 — Revisar plantillas y ejemplos (15 min)

Las plantillas son lo que más usa el agente. Verificás:

- ¿Las plantillas son **del código real del proyecto**, no genéricas?
- ¿Tienen comentarios explicando partes no obvias?
- ¿Reflejan las decisiones inmutables del proyecto (UUIDv7, multi-tenant, etc.)?
- ¿Si las copia y pega, funcionan o son pseudocódigo?

**Skills con plantillas genéricas tipo "ejemplo de cómo se hace una clase Django" son inútiles.** Las plantillas tienen que ser de Omni específicamente.

### Paso 4 — Revisar "Errores comunes" (10 min)

Esta sección es lo que más valor agrega a largo plazo. Verificás:

- ¿Los errores listados son reales (los cometió el agente o vos en el código que estás capturando)?
- ¿Cada error tiene su antídoto claro?
- ¿No es una lista genérica de "cosas a tener en cuenta" sin sustancia?

Si la sección es vaga ("evitá errores de lógica"), pedí reescritura con casos concretos.

### Paso 5 — Verificar checklist final (5 min)

La skill debe terminar con un checklist accionable que el agente pueda usar para auto-revisar su trabajo. Verificás:

- ¿Cada item del checklist es verificable objetivamente (sí/no)?
- ¿No hay items vagos como "código limpio" o "buenas prácticas"?
- ¿Cubre los puntos críticos del patrón?

### Paso 6 — Decisión

- **Aprobar y mergear:** si pasa todos los pasos.
- **Pedir ajustes:** comentarios específicos.
- **Rechazar:** si la skill no captura el patrón realmente o no aplica.

## 7.2 Tiempo total de revisión

30-45 minutos por skill. Si terminás en menos, la revisaste superficialmente.

## 7.3 Después de mergear

Una vez mergeada, **observá las próximas 2-3 sesiones donde la skill debería aplicar.** ¿El agente la cargó? ¿La siguió? ¿Cometió los errores que la skill anticipa?

Si la skill no rinde lo esperado, ajustes en próxima iteración.

---

# PARTE 8 — Mantenimiento y Evolución de Skills

## 8.1 Las skills no son permanentes

Una skill puede:

- **Quedar obsoleta** porque cambió el patrón del proyecto.
- **Necesitar actualización** porque aprendiste algo nuevo.
- **Necesitar split** porque captura demasiados patrones distintos.
- **Ser eliminada** porque ya no se usa o se reemplazó por otra.

## 8.2 Frecuencia de revisión

| Cadencia | Acción |
|----------|--------|
| Cada vez que se usa | Observación pasiva: ¿la skill rinde? |
| Mensual | Revisión rápida del listado de skills, marcar las que parecen no rendir |
| Trimestral | Revisión profunda de skills marcadas |
| Cada cambio mayor de arquitectura | Auditoría de skills afectadas |

## 8.3 Versionado de skills

Cada skill tiene un changelog al final del SKILL.md:

```markdown
## Changelog

### v1.2 — 2026-08-15
- Agregado: ejemplo de manejo de IGTF en ventas USD.
- Corregido: el ejemplo de viewset usaba `select_related` mal.

### v1.1 — 2026-07-10
- Actualizado: nueva convención de naming para servicios.

### v1.0 — 2026-05-08
- Versión inicial.
```

Cuando hacés cambio mayor a una skill, incrementás versión y anotás en changelog.

## 8.4 Cuándo eliminar una skill

Si una skill no se ha usado en 60 días según el log de carga (si tu sistema lo trackea), o si los patrones que captura ya no aplican al proyecto, la archivás:

```
docs/skills/_archived/<nombre>-vX.Y.md
```

No la borrás del git, la archivás. Sirve como histórico.

---

# PARTE 9 — Anti-Patrones de Skills

## 9.1 Anti-patrón "Skill enciclopedia"

**Síntoma:** una skill de 2000 líneas que cubre todo lo relacionado con un dominio.
**Por qué falla:** el agente la carga y se pierde en el ruido. No la sigue porque hay demasiado.
**Antídoto:** una skill cubre un patrón específico, no un dominio completo. Si abarca mucho, dividila.

## 9.2 Anti-patrón "Skill genérica"

**Síntoma:** una skill que podría aplicar a cualquier proyecto Django/Python/Web. Sin nada específico de Omni.
**Por qué falla:** el agente ya sabe esas cosas. La skill no agrega valor.
**Antídoto:** las skills capturan **decisiones específicas del proyecto**. Si no podrías mostrarle la skill a otro proyecto y que les sirva sin cambios, está bien.

## 9.3 Anti-patrón "Skill defensiva"

**Síntoma:** una skill llena de "evitá hacer X", "no hagas Y", "ten cuidado con Z" sin antídotos concretos.
**Por qué falla:** el agente sabe qué evitar pero no qué hacer en su lugar.
**Antídoto:** cada "no hacer X" viene acompañado de "hacer Y en su lugar".

## 9.4 Anti-patrón "Skill copiada"

**Síntoma:** una skill que es 80% igual a otra.
**Por qué falla:** mantenimiento doble, inconsistencias, ruido.
**Antídoto:** si dos skills son muy parecidas, fusionar o referenciar la una a la otra.

## 9.5 Anti-patrón "Skill aspiracional"

**Síntoma:** una skill que describe cómo nos gustaría que el código fuera, no cómo realmente es.
**Por qué falla:** el agente sigue la skill pero el código real está distinto. Conflicto.
**Antídoto:** las skills reflejan código real. Si querés cambiar una convención, cambiala en código primero, después actualizá la skill.

## 9.6 Anti-patrón "Skill sin owner"

**Síntoma:** una skill creada hace meses, nadie sabe si está actualizada, nadie la mantiene.
**Por qué falla:** se vuelve ruido o, peor, dirige al agente a patrones obsoletos.
**Antídoto:** cada skill tiene un dueño (vos, en proyecto solo) y se revisa al menos cada trimestre.

## 9.7 Anti-patrón "Skill que reemplaza al revisor"

**Síntoma:** asumís que como hay skill, no necesitás revisar tan a fondo.
**Por qué falla:** las skills capturan patrones, no garantías. El agente puede aplicar la skill mal o cambiar el contexto.
**Antídoto:** las skills aceleran tu revisión, no la reemplazan.

---

# Cierre

Las skills son una de las inversiones más rentables que podés hacer en este proyecto, **siempre que se creen en el momento correcto**. Crearlas todas de antemano se siente productivo pero produce ruido. Crearlas just-in-time produce skills que el agente realmente sigue y que te ahorran horas de revisión.

Las 5 skills del día 1 las tenés ya escritas en archivos separados. Las de Fase 0 las creás durante el mes 1 según los disparadores de PARTE 4. Las de Fases 1-2 emergen orgánicamente con el trabajo real.

Si seguís este plan con disciplina, al final de Fase 2 vas a tener un cuerpo de 17-23 skills útiles, calibradas con código real, que aceleran cada tarea futura.

---

*Plan vivo. Ajustable cuando aparezcan disparadores que este plan no anticipó.*
