# Plantillas de Prompts para Pedir Skills al Agente

**Propósito:** prompts listos para copiar-y-pegar cuando llegue el momento de pedirle al agente que cree cada skill de Fase 0 y Fases 1-2.

> **Cómo usar:** identificá el momento correcto según el plan (`05_PLAN_CREACION_SKILLS.md`), copiá el prompt correspondiente, ajustá las partes entre `[corchetes]` con info específica de tu situación, pegáselo al agente.

---

## Plantilla genérica (base para customizar)

```
Tarea: crear la skill `[nombre-de-la-skill]`.

Contexto:
Acabamos de [implementar/refactorizar/usar por primera vez] el patrón de [breve descripción] en el PR #[número] / archivos [ruta1, ruta2]. El patrón es importante porque va a repetirse en [explicar cuándo se aplicará a futuro].

Tu tarea es crear una skill que capture este patrón para que en futuras tareas (tuyas o de otros agentes) se aplique consistentemente sin redescubrir las decisiones que ya tomamos.

Instrucciones:

1. Leé atentamente el código relevante:
   - [archivo1]
   - [archivo2]
   - [archivo3]

2. Leé skills existentes en `docs/skills/` (especialmente `omni-django-module/SKILL.md`) para entender el formato y estilo establecidos.

3. Identificá:
   - Las convenciones que establecimos en el código real (nombres, estructura, patrones).
   - Las decisiones que se tomaron explícitamente y deben respetarse.
   - Los errores que cometiste en el camino y corregimos.
   - Casos típicos donde esta skill aplicará a futuro.
   - Casos donde NO debe aplicar.

4. Creá la skill en `docs/skills/[nombre-de-la-skill]/SKILL.md` con la siguiente estructura:

   - Frontmatter con `name` y `description`. El `description` debe estar optimizado para activarse cuando la skill aplica y NO activarse cuando no aplica. Sigue el patrón de los otros skills (en inglés, "Use this skill whenever..." + triggers + "Do NOT use for...").

   - Sección "Cuándo usar esta skill" en lenguaje humano.

   - Sección de plantillas con código real del proyecto, no genérico.

   - Sección de convenciones específicas.

   - Sección "Anti-patrones" con casos concretos del proyecto.

   - Checklist final accionable.

   - Sección de referencias a otras skills relacionadas.

   - Changelog.

   Largo objetivo: 200-500 líneas. Si menos, faltan detalles. Si más, sobre-especificada.

5. Antes de empezar a escribir:
   - Reformulame en tus palabras el patrón que vas a capturar.
   - Mostrame qué archivos vas a leer.
   - Esperá mi confirmación.

6. Después de crear la skill:
   - Abrí PR draft.
   - En la descripción del PR, documentá las decisiones clave: qué incluiste, qué dejaste fuera, y por qué.
   - Listo para mi revisión.
```

---

## Skills de Fase 0

### Cuando se establece el patrón de tests del proyecto

**Disparador:** después del primer PR donde se establezca cómo se escriben los tests del proyecto (probablemente en semana 2-3).

```
Tarea: crear la skill `omni-test-strategy`.

Contexto:
Acabamos de establecer el patrón de tests del proyecto. En el PR #[número] definimos cómo se escriben tests unitarios, de integración, de aislamiento multi-tenant, y la estructura general de la carpeta tests/. Quiero capturar este patrón antes de que avancemos.

Tu tarea es crear una skill que estandarice cómo se escriben tests en Omni.

Específicamente, capturá:

1. Pirámide de tests del proyecto:
   - Cuándo unitarios, cuándo integración, cuándo end-to-end.
   - Targets de coverage por fase (Fase 0: ≥30% backend, ≥20% frontend; Fase 1: ≥50%; etc.).

2. Uso de factories con factory_boy:
   - Convención de naming.
   - Cómo manejar SubFactory para mantener consistencia de id_empresa.
   - Cómo evitar acoplamiento entre tests.

3. Cuándo mockear:
   - Mockear servicios externos (BCV API, WhatsApp API, LLM API).
   - NO mockear queries de DB en tests de integración.
   - Cómo mockear el LLM con respuestas determinísticas para tests.

4. Tests de aislamiento multi-tenant (referenciar la skill omni-multi-tenant-isolation pero agregando matices específicos del patrón establecido).

5. Tests de código async (Celery tasks):
   - Modo eager para tests.
   - Cómo verificar que se encolaron las tasks correctas.

6. Tests de capacidades MCP cuando lleguen.

7. Tests de agentes cuando lleguen (golden cases vs unit tests del orquestador).

8. Tests del DSL de personalización cuando llegue.

Convenciones específicas de Omni:
- Nombres de tests en español o inglés? (Verificá lo que establecimos.)
- Estructura de archivos test_*.py vs *_test.py.
- Cómo organizar fixtures.

Plantillas:
- Test unitario de service.
- Test de integración de viewset.
- Test de aislamiento.
- Factory típica.

Anti-patrones específicos del proyecto:
[Documentá lo que viste en el PR]

Sigue el formato de las skills existentes en docs/skills/.

Antes de empezar:
1. Leé los archivos de tests del PR #[número].
2. Leé skills existentes para mantener el estilo.
3. Reformulame qué patrones vas a capturar.
4. Esperá mi confirmación.
```

### Cuando se implementa el event store con primer dominio (semana 7-9)

```
Tarea: crear la skill `omni-event-sourcing`.

Contexto:
En el PR #[número] implementamos el event store usando Redpanda y emitimos los primeros eventos del dominio `ventas`. Establecimos el formato del Event Envelope, las convenciones de naming, cómo se emite, cómo se consume, y cómo se actualizan las proyecciones.

Tu tarea es crear una skill que capture todo esto, para que cuando agreguemos event sourcing a otros dominios (compras, inventario, fiscal, etc.), se haga consistente.

Específicamente, capturá:

1. Event Envelope estándar:
   - Estructura completa de un evento (id, timestamp, tenant_id, aggregate_id, type, version, payload, metadata).
   - Cómo se versiona.
   - Cómo se firma/valida si aplica.

2. Naming de eventos:
   - Convención `<bounded_context>.<aggregate>.<event_name>`.
   - Tiempo verbal pasado (Created, Updated, Cancelled — o equivalentes en español si ese es el patrón establecido).

3. Emisión:
   - Cuándo se emite (post_save signal vs commit explícito).
   - Idempotencia: cómo garantizamos que un evento se procesa una sola vez.
   - Manejo de fallas: qué pasa si el publish falla después del commit.

4. Consumo:
   - Estructura de un consumer.
   - Cómo se actualiza una proyección.
   - Manejo de errores y dead-letter queue.

5. Versionado de eventos:
   - Cómo manejar cambios de schema (nuevos campos, campos removidos).
   - Cuándo bumpear versión major vs minor.

6. Replay:
   - Cómo se reconstruye una proyección desde cero.
   - Cuándo conviene hacer replay vs migración.

7. Plantillas:
   - Modelo de evento.
   - Función de emisión.
   - Consumer básico.
   - Test de idempotencia.

Anti-patrones que cometimos y corregimos:
[Documentá los errores reales del PR]

Sigue el formato de las skills existentes.

Antes de empezar:
1. Leé el código del event store y el dominio ventas.
2. Reformulame el patrón.
3. Esperá confirmación.
```

### Cuando se exponen primeros módulos como MCP (semana 10-11)

```
Tarea: crear la skill `omni-mcp-server`.

Contexto:
En el PR #[número] implementamos el MCP runtime y expusimos las primeras capacidades de los módulos `ventas` y `finanzas` como servidores MCP. Establecimos cómo se decoran las funciones, cómo se autoriza con capability tokens, cómo se loguea, y la convención de qué se expone vs qué no.

Tu tarea es crear una skill que estandarice cómo se exponen capacidades MCP en cada módulo.

Específicamente, capturá:

1. Estructura del archivo `mcp.py` por módulo.

2. Convención de capacidades:
   - Operaciones de negocio, no CRUD genérico (`crear_pedido` SÍ, `create_pedido_object` NO).
   - Cómo nombrar (verbo + sustantivo en español).
   - Cuándo una operación amerita ser capacidad MCP (regla: si tiene sentido que un agente la invoque para resolver una tarea de negocio).

3. Decorador `@register_capability` y sus parámetros:
   - name, description, requires_capability_token.
   - Cómo escribir descriptions útiles para que el agente sepa cuándo usarlas.

4. Validación de inputs:
   - Schemas con Pydantic o equivalente.
   - Validación de tenant.
   - Manejo de errores.

5. Capability tokens:
   - Cómo se asignan permisos por capacidad.
   - Cómo se incluye `empresa_id` en el contexto.
   - Defense-in-depth: filtrar por empresa aunque el token ya esté validado.

6. Observabilidad:
   - Loggear cada llamada con prompt origen, latencia, costo de inferencia.
   - Cómo se ven las métricas.

7. Testing:
   - Test de capacidad MCP (llamar y verificar resultado).
   - Test de autorización (rechazo cuando token no tiene la capacidad).
   - Test de aislamiento multi-tenant.

8. Plantillas:
   - Capacidad de lectura.
   - Capacidad de escritura.
   - Capacidad con efectos secundarios (envía email, etc.).

Anti-patrones detectados en el PR:
[Documentá]

Sigue formato de skills existentes.

Antes de empezar:
1. Leé el MCP runtime y los servidores ya creados.
2. Reformulame el patrón.
3. Esperá.
```

### Cuando aparece la primera migración compleja

```
Tarea: crear la skill `omni-migration-guide`.

Contexto:
En el PR #[número] hicimos una migración Django compleja que involucró [data migration / cambio de schema con datos existentes / split de modelo / etc.]. Aprendimos varias cosas que conviene documentar.

Tu tarea es crear una skill sobre cómo hacer migraciones seguras en este proyecto.

Capturá:

1. Tipos de migraciones:
   - Schema migrations.
   - Data migrations.
   - Mixed (cuándo evitarlas).

2. Reversibilidad:
   - Cómo escribir migrations reversibles.
   - Cuándo es legítimamente irreversible.
   - Cómo verificar reversibilidad antes del PR.

3. Migraciones grandes en producción:
   - Cómo evitar table locks largos.
   - Estrategia de double-write si aplica.
   - Backfilling de datos en lotes.

4. Multi-tenant en migraciones:
   - Cómo iterar por tenants sin asumir contexto de request.
   - Manejo de fallas parciales (tenant 50 falla, ¿qué pasa con los 49 ya migrados?).

5. Conflictos de migraciones:
   - Cuando dos PRs paralelos crean migraciones que chocan.
   - Cómo resolver.

6. Seed data:
   - Cómo se manejan datos iniciales.
   - Diferencia entre migration data y fixtures de tests.

7. Plantillas:
   - Schema migration típica.
   - Data migration con backfill.
   - Migration reversible con `RunPython.noop` cuando corresponde.

Anti-patrones:
[Documentá los errores que vimos]

Antes de empezar:
1. Leé la migración del PR.
2. Reformulame.
3. Esperá.
```

### Cuando se acepta el primer Compromiso Técnico Fechado

```
Tarea: crear la skill `omni-debt-management`.

Contexto:
Aceptamos el primer Compromiso Técnico Fechado (CTF-[ID]) en el contexto de [explicar]. El proceso reveló cómo manejamos esto.

Tu tarea es crear una skill que estandarice cómo se gestionan los CTFs.

Capturá:

1. Cuándo se justifica un CTF:
   - Casos legítimos vs procrastinación disfrazada.
   - Quién puede crear uno.

2. Estructura del CTF:
   - Plantilla.
   - Campos obligatorios (regla violada, razón, plan, dueño, fecha).

3. Tracking:
   - Cómo se versionan.
   - Cómo se asocian a issues.
   - Notificaciones cuando vencen.

4. Vencimiento:
   - Qué pasa el día que vence.
   - Quién decide si extender o resolver.
   - Escalation cuando vence sin resolverse.

5. Cómo distinguir CTF legítimo de "lo arreglo después" disfrazado:
   - Red flags.
   - Preguntas a hacerse.

6. Plantillas:
   - CTF nuevo.
   - Renovación de CTF.
   - Cierre de CTF.

Antes de empezar:
1. Leé el CTF que aceptamos.
2. Reformulame.
3. Esperá.
```

### Cuando se construye el primer agente operativo (semana 12-13)

```
Tarea: crear las skills `omni-agent-construction` Y `omni-eval-suite`.

Contexto:
En el PR #[número] construimos el primer agente operativo (clasificador de gastos / agente de cobranza / lo que sea) en modo shadow. Establecimos el patrón completo: prompt, herramientas via MCP, guardarraíles, evaluador, dashboard de métricas.

Tu tarea es crear DOS skills relacionadas pero separadas:

A. `omni-agent-construction`: cómo se construye un agente nuevo.

Capturá:
1. Estructura estándar de un agente:
   - Archivo prompt.
   - Conexión con MCP (qué capacidades carga).
   - Guardarraíles (qué no puede hacer).
   - Logging y observabilidad.

2. Niveles de autonomía:
   - "Sugerir" — propone pero no ejecuta.
   - "Ejecutar con reversa" — actúa pero todo es revertible.
   - "Ejecutar" — actúa sin pedir permiso.
   - Cómo se configura por tenant.

3. Selección de modelo:
   - Cuándo Claude Sonnet vs Opus vs Haiku.
   - Cuándo GPT vs Gemini.
   - Cuándo modelo local.
   - Cómo decidir según tarea, costo, latencia.

4. System prompts:
   - Qué incluir.
   - Qué evitar.
   - Cómo mantenerlos versionados.

5. Manejo de feedback humano:
   - Cómo se loguea cuando un humano corrige.
   - Cómo se incorpora al banco de evals.

6. Plantillas:
   - Estructura mínima de agente.
   - Prompt template.
   - Test de comportamiento.

B. `omni-eval-suite`: cómo se construyen y mantienen evals.

Capturá:
1. Estructura de un caso dorado (input, expected output, criterios).
2. Cómo construir el dataset inicial (50-100 casos).
3. Runner automatizado y CI integration.
4. Métricas (accuracy, precision/recall, latencia, costo).
5. A/B testing.
6. Detección de regresiones.

Sigue el formato de skills existentes.

Antes de empezar:
1. Leé el código del primer agente y su eval suite.
2. Reformulame ambas skills.
3. Esperá confirmación.
```

---

## Skills de Fases 1-2 (cuando emerjan)

### Patrón general para skills bajo demanda

Cuando detectes (durante revisión semanal) que se necesita una skill nueva, usá la plantilla genérica del inicio de este documento, customizada con:

- **Contexto:** describí qué patrón emergió y dónde.
- **Archivos a leer:** los específicos del PR donde se estableció.
- **Por qué se necesita:** la razón concreta (vos viste el patrón repetirse, el agente cometió el error dos veces, etc.).

### Ejemplos breves de cuándo cada una

**`omni-venezuela-payments`** (mes 3-4):
> "Acabamos de implementar Pago Móvil y Zelle. Tenemos patrones para validación de referencias, manejo de duplicados, conciliación. Crear skill que capture esto y prepare para los métodos siguientes (USDT, transferencia, punto de venta)."

**`omni-bcv-rates`** (mes 2-3):
> "Implementamos integración con BCV vía scraping/API en el PR #X. Tenemos manejo de feriados, fallback cuando falla, snapshot por transacción. Crear skill."

**`omni-cobranza-patterns`** (mes 5-6):
> "El agente de cobranza ya lleva 4 semanas en producción. Detecté tres patrones que repite mal sin guía: [...]. Crear skill que codifique cómo el agente debe manejar [...]."

**`omni-pos-patterns`** (mes 7):
> "Implementamos el POS de mostrador. Patrón de búsqueda rápida, manejo de código de barras, cobro multimoneda en línea. Crear skill antes de implementar el POS de la fábrica."

**`omni-bom-and-mrp`** (mes 10-11):
> "Implementamos BOM para los primeros 10 productos de muebles. Patrón de jerarquía de materiales, costeo, integración con OF. Crear skill antes de extender a más productos."

---

## Cómo agendar la creación

**Inmediatamente después de mergear el PR donde se estableció el patrón.**

Antes de avanzar a la próxima tarea de producto, dedicás una sesión a la skill. El agente la crea, vos la revisás, la mergeás. **Después** seguís con producto.

Si avanzás a producto sin crear la skill, el patrón se difumina y se pierde el momento.

---

## Plantilla de revisión de skill creada

Cuando el agente entrega una skill, tu protocolo de revisión es la PARTE 7 del documento `05_PLAN_CREACION_SKILLS.md`. Resumen rápido:

1. **Description** activa cuando debe, no cuando no debe.
2. **Plantillas** son del código real, no genéricas.
3. **Anti-patrones** son errores reales del proyecto, no hipotéticos.
4. **Checklist** es accionable y verificable.
5. **Largo razonable** (200-500 líneas).

Si pasa los 5: aprobar y mergear.
Si falla alguno: pedir ajustes específicos.

---

*Documento de plantillas. Customizar antes de usar.*
