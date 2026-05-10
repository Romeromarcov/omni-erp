# Omni AI-Native — Plan de Ejecución (Edición Founder Solo)
**Versión:** 2.0 — Reemplaza `OMNI_AI_NATIVE_EXECUTION_PLAN.md` v1.0
**Razón del reemplazo:** v1.0 asumía equipo y tiempo full. v2.0 está calibrada para founder solo trabajando 15-25 horas semanales con AI como multiplicador, con clientes piloto familiares y target real de 12-15 meses para MVP completo.

> **La PARTE I (Visión Perpetua) sigue idéntica. Ese es el norte.**
> **La PARTE II (Reglas Inviolables) sigue idéntica. Esa es la disciplina.**
> **Lo que cambia es el ritmo, las fases, los hitos, y los criterios de éxito.**

---

## ÍNDICE

- [PARTE I — La Visión Perpetua (idéntica a v1)](#parte-i)
- [PARTE II — Reglas Inviolables (idénticas a v1)](#parte-ii)
- [PARTE III — Cómo Decidir cuando Tengas Dudas (idéntico a v1)](#parte-iii)
- [PARTE IV — Plan de Ejecución por Bloques (REESCRITO)](#parte-iv)
- [PARTE V — Mes a Mes del Año 1 (NUEVO)](#parte-v)
- [PARTE VI — Disciplina de Founder Solo (NUEVO)](#parte-vi)
- [PARTE VII — Sistema de Checkpoints Adaptado (REESCRITO)](#parte-vii)
- [PARTE VIII — Anti-Patrones Específicos para tu Escenario (REESCRITO)](#parte-viii)
- [APÉNDICE A — Decisiones Inmutables (sin cambios)](#apéndice-a)
- [APÉNDICE C — Norte Estrella (NUEVO)](#apéndice-c)

---

# PARTE I — La Visión Perpetua

> **Esta sección es idéntica a la del plan v1. La incluyo entera para que este documento sea autocontenido.**

## 1.1 Qué estamos construyendo (en una frase)

**Un sistema operativo de negocio AI-nativo, donde una empresa de cualquier tamaño, país, industria o nivel de formalidad puede operar y evolucionar su gestión completa hablándole en lenguaje natural — y eventualmente lanzar plataformas digitales propias sin contratar desarrolladores.**

## 1.2 Las cinco propiedades irrenunciables del producto

1. **Conversacional primero, no como añadidura.**
2. **Determinista donde la ley lo exige, agéntico donde el juicio paga.**
3. **Personalizable por conversación, no por consultoría.**
4. **Cada empresa es potencialmente un emisor de software.**
5. **Localización y regulación son ciudadanos de primera clase.**

## 1.3 Los cinco principios arquitectónicos no negociables

1. **Event sourcing como verdad.**
2. **Multi-tenant absoluto desde el día 1.**
3. **MCP en todo módulo, desde el primer módulo.**
4. **Determinismo donde aplica, no antes ni después.**
5. **Personalización como artefacto declarativo versionado.**

## 1.4 La frase que debe morir

**"Esto lo añadimos rápido, después lo hacemos bien."**

## 1.5 Las tres preguntas que respondes cada lunes en 5 minutos

1. **Lo que voy a construir esta semana, ¿se conecta con la frase del 1.1? ¿Cómo?**
2. **¿Algo de lo que voy a construir esta semana viola una propiedad o principio? Si sí, ¿por qué procede igual?**
3. **¿Qué métrica concreta va a estar mejor el viernes que hoy lunes, gracias a este trabajo?**

---

# PARTE II — Reglas Inviolables

> **Idénticas a v1. Las nombro brevemente; el detalle está en v1.**

**R-CODE-1 a R-CODE-10:** multi-tenant, no SQLite, sin any/print, Decimal para dinero, UUIDv7, soft delete, API-first, sin secretos, tests integración, no null=True en obligatorios.

**R-PROC-1 a R-PROC-8:** una fuente de verdad por dominio, PRs pequeños, code review obligatorio, CI verde no-negociable, migraciones reversibles, compromisos técnicos se vencen, **deuda técnica cada dos semanas**, **cliente real desde el día 90** ← **ESTA REGLA CAMBIA: ahora es "cliente real piloto operando, no externo pagando"**.

**R-PROD-1 a R-PROD-5:** nada se llama AI-powered si no es nativo, personalización del usuario antes que de consultor, complejidad escondida no eliminada, reversibilidad por defecto, transparencia de la IA.

## Cambios respecto a v1

**R-PROC-8 ajustado para founder solo:**
- v1 decía: "Cliente real desde el día 90 (cliente externo pagando)"
- v2 dice: "**Cliente piloto familiar operando desde el día 180**, **cliente externo pagando desde el día 480 (mes 16)**"

Razón: con 15-25 horas semanales no hay manera honesta de tener un MVP utilizable en 90 días. Forzarte a esa fecha te obliga a entregar algo malo o a quemarte.

**R-PROC-7 (deuda técnica) ajustado:**
- v1 decía: "Una semana cada dos para deuda técnica"
- v2 dice: "**Una sesión cada quince debe ser para deuda técnica, refactor, tests faltantes y documentación**". Equivalente proporcional.

---

# PARTE III — Cómo Decidir cuando Tengas Dudas

> **Idéntica a v1. Árbol de cinco niveles, conflictos entre reglas, excepciones genuinas.**

Para founder solo, **el Nivel 3 (decisiones que afectan futuro) es especialmente delicado** porque no tenés un par técnico al lado. La regla concreta:

**Cuando enfrentes una decisión Nivel 3 trabajando solo:**
1. Documentá las opciones.
2. **Esperá 24 horas antes de decidir.** No es opcional. Las decisiones tomadas a las 11pm bajo cansancio son las que duelen.
3. Si tenés acceso a un sparring informal (amigo técnico), ahí va.
4. Después de 24h y consulta opcional, decidís y avanzás.

---

# PARTE IV — Plan de Ejecución por Bloques

> **REESCRITO. Las seis "fases" del v1 se reagrupan en tres "bloques" más realistas.**

## 4.1 Filosofía de bloques (versión founder solo)

- **Un bloque dura un año o más, no semanas.**
- **No tenés equipo. Cada hito requiere planeación, ejecución, prueba y ajuste — todo lo hacés vos con AI.**
- **Los bloques son secuenciales y absolutos.** No empezás Bloque 2 antes de cerrar Bloque 1, sin importar qué oportunidad parezca surgir.
- **Cada bloque tiene una métrica única que importa**, no una lista larga de Definition of Done.

## 4.2 Resumen de bloques

| Bloque | Duración real | Métrica única que importa |
|--------|---------------|----------------------------|
| **1 — De idea a primer cliente piloto** | 12-15 meses | Un negocio familiar opera el sistema diariamente como reemplazo del anterior |
| **2 — De piloto a producto** | 12-18 meses | 5-10 clientes pagando con retención > 70% |
| **3 — Bifurcación** | Varía | Decidís: lifestyle business, levantar capital, o vender |

## 4.3 Bloque 1 — De idea a primer cliente piloto

**Duración real:** 12-15 meses con 15-25 horas/semana.

**Lo que se construye:** todo el alcance definido en el documento `01_MVP_SCOPE_NEGOCIOS_PILOTO.md`, en el roadmap mes-a-mes de su PARTE 8.

**Lo que NO se hace:**
- No buscás clientes externos.
- No hacés marketing.
- No publicás landing pages prometiendo el producto.
- No prometés timeline a nadie.
- No mostrás demos a desconocidos.

**Métrica única:** uno de los dos negocios familiares (idealmente la distribuidora) opera diariamente con tu sistema durante 30 días sin volver al anterior. Eso. Cuando eso pasa, cerraste Bloque 1 (aunque queden features pendientes).

**Las 6 sub-fases del Bloque 1 (con duración real):**

| Sub-fase | Duración | Output |
|----------|----------|--------|
| 1.A — Fundación técnica | Mes 1 | Build sólida, deuda técnica saldada, agente IA operando |
| 1.B — Núcleo común parte 1 | Mes 2 | Catálogos, inventario, multimoneda |
| 1.C — Núcleo común parte 2 | Mes 3 | Ciclo comercial completo, fiscal VE |
| 1.D — Núcleo común parte 3 | Mes 4 | Compras, CxP, listas de precios, reportes |
| 1.E — Personalización + agentes | Mes 5 | DSL Capa 1-2, dos agentes en modo sugerir |
| 1.F — Distribuidora en producción | Mes 6 | Distribuidora opera 30 días continuos |
| 1.G — Específicos distribuidora | Mes 7-9 | POS, comisiones, devoluciones, despacho |
| 1.H — Onboarding fábrica + BOM | Mes 10-11 | Fábrica usando lo común; BOM cargado |
| 1.I — OF y costeo | Mes 12-13 | OF con etapas, costeo real, pago destajo |
| 1.J — Estabilización | Mes 14-15 | Bugfixing, documentación, baseline para venta |

**Definition of Done de Bloque 1 (cierre completo):**

- [ ] Distribuidora operando sin volver al sistema anterior por 90 días continuos.
- [ ] Fábrica operando con OF y costeo por 60 días continuos.
- [ ] Documentación interna del producto al día.
- [ ] Backlog de feedback de los pilotos categorizado (bugs, nice-to-have, no relevante).
- [ ] Demo grabada en video que muestra ambos negocios operando.
- [ ] Caso de éxito escrito (con métricas reales: cuánto se redujo cobranza atrasada, cuánto cambió margen, etc.).
- [ ] Tu salud mental y física razonablemente intactas.

## 4.4 Bloque 2 — De piloto a producto

**Duración real:** 12-18 meses adicionales.

**Lo que se construye en Bloque 2:**
- Lo que pidan los primeros 5-10 clientes externos, dentro de lo razonable.
- Mejoras de onboarding (porque cliente externo no es familiar tolerante).
- Estabilización seria (porque ya no podés hotfixear a las 2am).
- Marketing y ventas básicas.
- Posiblemente: algunas features que dejaste fuera del MVP (multi-sucursal, integración bancaria, etc.).

**Lo que NO se hace:**
- No metés Platform Spaces.
- No metés blockchain.
- No metés generación de productos digitales.
- No metés multi-país (Venezuela sigue siendo el mercado).
- No buscás levantar capital todavía.

**Las 4 sub-fases del Bloque 2:**

| Sub-fase | Duración | Output |
|----------|----------|--------|
| 2.A — Primer cliente externo | Mes 16-18 | 1-2 clientes pagando, mucho aprendizaje de onboarding |
| 2.B — Estabilización | Mes 19-22 | Producto suficientemente confiable para no requerir tu intervención diaria |
| 2.C — Crecimiento controlado | Mes 23-30 | 5-10 clientes pagando, retención > 70% |
| 2.D — Decisión | Mes 30-33 | Análisis honesto del estado, decisión de Bloque 3 |

**Métrica única de Bloque 2:** 5+ clientes pagando con retención > 70% en los últimos 6 meses, y vos podés pasar 2 semanas sin tocar el sistema sin que se rompa.

## 4.5 Bloque 3 — Bifurcación

**Duración real:** indefinida; depende del camino elegido.

**Decisión que tomás al cerrar Bloque 2:** uno de los tres caminos.

### Camino A — Lifestyle business (Bloque 3A)

20-50 clientes, vos como dueño-operador, equipo de 2-5 personas, sin capital externo.

**Trabajo:** consolidación, eficiencia operativa, contratar 1-2 ingenieros senior, rentabilidad estable.
**Duración:** indefinida; sostenible mientras quieras seguir.
**Outcome:** ingreso estable, control total, sin retorno a inversores.

### Camino B — Levantar capital (Bloque 3B)

**Pre-requisitos:** retención > 80%, > 30 clientes, métricas que sostienen una conversación con VCs latinoamericanos (Kaszek, Monashees, ALLVP, regionales).

**Trabajo:** preparar pitch, levantar Serie A o pre-A, contratar equipo, expandir geográficamente, empezar a construir piezas que dejaste fuera (Platform Spaces, marketplace).

**Duración:** Bloque 3B es 5+ años por sí mismo.

**Outcome:** posibilidad de la visión grande original.

### Camino C — Vender a consolidador

**Cuándo:** si llegás a Bloque 2 cerrado pero ya no querés operar.

**Trabajo:** identificar consolidadores (Defontana, Loggro, otros locales), preparar data room, negociar.

**Outcome:** liquidez, libertad, learning para tu próximo proyecto.

**No decidís el camino hoy. Decidís en mes 30-33 con datos.**

## 4.6 Diferencias clave con el plan v1

| Aspecto | v1 | v2 |
|---------|----|----|
| Fase 0 | 3-4 meses, fundación AI-nativa | Sub-fase 1.A, mes 1 únicamente |
| Fase 1 | 3-4 meses, MVP vendible | Sub-fases 1.B-1.F, meses 2-6 |
| Fase 2 | 3-4 meses, profundización agéntica | Sub-fases 1.G-1.J, meses 7-15 (más amplio) |
| Fase 3 | 4-6 meses, diferenciación | Sub-fases 2.A-2.B, meses 16-22 |
| Fase 4 | 6-12 meses, plataforma de plataformas | **No es Bloque 1 ni 2. Es Bloque 3B si elegís ese camino.** |
| Fase 5+ | continuo, blockchain, expansión | **Bloque 3B avanzado. No antes del año 5.** |

**El plan no es menos ambicioso. Es más honesto sobre el ritmo.**

---

# PARTE V — Mes a Mes del Año 1

> **Esta es la versión zoom-in del Bloque 1, sub-fase por sub-fase, con detalle de qué hacer cada semana.**

## 5.1 Sub-fase 1.A — Mes 1: Fundación

### Semana 1 — Setup y diagnóstico

**Tu trabajo (humano):**
- Día 1-2: leer este plan, leer `01_MVP_SCOPE_NEGOCIOS_PILOTO.md`, leer protocolo del agente.
- Día 3: hacer las preguntas de la PARTE 9 del MVP Scope a la distribuidora.
- Día 4: hacer las preguntas de la PARTE 9 a la fábrica.
- Día 5: ajustar el MVP Scope según respuestas reales (probablemente 5-10% de cambios).
- Día 6-7: setup del entorno, branch nueva, CI básico.

**Trabajo del agente (con tu supervisión):**
- Diagnóstico inicial (PARTE 8 del protocolo del agente).
- Producir `docs/DIAGNOSTICO_INICIAL.md`.

**Output del fin de semana 1:** sabés exactamente qué tenés en código, qué necesitás de cada negocio piloto, y el agente está operando con disciplina.

### Semana 2-3 — Saldar deuda técnica

**Trabajo del agente:**
- Migración a PostgreSQL en todos los entornos.
- Setup de Docker Compose con Postgres + Redis + Celery.
- Tests básicos (cobertura mínima).
- Configurar pre-commit hooks.
- Refactor TanStack Query.
- División de ModalPago.
- Eliminar los `any` de TypeScript.

**Tu trabajo:** revisar PRs en lotes (martes y jueves, 1 hora cada uno), aprobar, mergear.

**Output del fin de semana 3:** build verde, tests corriendo en CI, deuda técnica de "alta prioridad" del Master Plan saldada.

### Semana 4 — Primitivas AI-nativas v0

**Trabajo del agente:**
- Setup mínimo de event store (Redpanda, en Docker Compose).
- MCP runtime básico (un servidor MCP con dos endpoints de prueba).
- Setup de cliente Anthropic API.
- Capability tokens estructura básica.
- BaseModel y BaseModelViewSet implementados con todas las protecciones multi-tenant.

**Output del fin de semana 4:** las primitivas AI-nativas existen aunque no se usen en producción todavía. Estás listo para construir módulos sobre ellas.

## 5.2 Sub-fase 1.B — Mes 2: Núcleo común parte 1

### Semana 5 — Modelo de datos central

**Plan:** `core` (empresa, usuario, rol, sucursal), `productos` (catálogo, categorías, unidades), `clientes`, `proveedores`. Todo con BaseModel.

**Trabajo del agente:** modelos, viewsets, serializers, tests de aislamiento, MCP servers básicos para cada uno.

**Tu trabajo:** confirmar que los campos cubren lo necesitado por los dos negocios (basado en las respuestas de la PARTE 9). Validar nombres de campos en español.

### Semana 6 — Inventario básico

**Plan:** `inventario` con movimientos (entrada, salida, ajuste, traslado), kardex, stock por sucursal.

**Trabajo del agente:** modelos de movimientos, lógica de cálculo de stock (event-sourced), reportes básicos.

**Output:** podés cargar productos, hacer un movimiento manual de entrada, ver el stock reflejado.

### Semana 7 — Multimoneda

**Plan:** módulo de tasas de cambio, integración con BCV (scraping o API), almacenamiento de snapshot por transacción.

**Trabajo del agente:** servicio de tasa BCV, modelo de tipo de cambio, conversiones automáticas en pantallas.

**Output:** un producto puede tener precio en USD y mostrarse en VES con tasa BCV vigente, o viceversa.

### Semana 8 — Integración + estabilización

**Plan:** todo lo de las semanas 5-7 funcionando junto, sin bugs evidentes.

**Trabajo del agente:** tests de integración, fix de bugs, refactor menor.

**Output:** el dueño de la distribuidora puede ver una pantalla de productos con precios multimoneda, y un kardex básico.

## 5.3 Sub-fase 1.C — Mes 3: Núcleo común parte 2

### Semana 9 — Cotización y pedido

**Plan:** `ventas` con cotización → pedido. Sin factura todavía.

**Trabajo del agente:** modelos, flujo de aprobación simple (cotización → pedido), MCP server de ventas.

### Semana 10 — Factura y fiscal VE

**Plan:** factura con IVA, IGTF, retenciones. Generación de PDF.

**Trabajo del agente:** módulo `fiscal`, cálculos de impuestos, plantilla PDF de factura, secuenciador de números fiscales.

**Crítico:** validá esto a fondo con el contador del negocio. Errores aquí son problemas legales.

### Semana 11 — Cobranza básica

**Plan:** `cuentas_por_cobrar` con aging, registro de abonos, estado de cuenta.

**Trabajo del agente:** modelos, lógica de aging, MCP server, primeros reportes.

### Semana 12 — Métodos de pago VE

**Plan:** registro de pagos en distintos métodos (efectivo USD/VES, Pago Móvil, transferencia, USDT, Zelle, punto de venta).

**Trabajo del agente:** modelo de métodos, validaciones (referencia, monto), conciliación manual.

**Output del mes 3:** la distribuidora podría hacer una venta completa: cotización → pedido → factura → registro de cobro. Todo en el sistema.

## 5.4 Sub-fase 1.D — Mes 4: Núcleo común parte 3

### Semana 13 — Compras

**Plan:** ciclo solicitud → OC → recepción → factura proveedor.

### Semana 14 — Cuentas por pagar

**Plan:** registro de facturas de proveedor, programación de pagos, registro de pagos.

### Semana 15 — Caja diaria

**Plan:** apertura de caja, registro de movimientos, arqueo, cierre.

**Crítico para distribuidora:** acá empieza a tomar forma el POS. Aún sin código de barras (eso es Mes 7), pero la lógica de caja ya está.

### Semana 16 — Listas de precios + reportes básicos

**Plan:** múltiples listas de precios con vigencia, asignación a clientes; reportes: ventas por período, cobranza, inventario.

**Output del mes 4:** el ciclo comercial completo funciona. La distribuidora podría operar el día a día en el sistema, aunque le faltan features de comodidad (POS ágil, código de barras).

## 5.5 Sub-fase 1.E — Mes 5: Personalización + Agentes

### Semana 17 — DSL de personalización Capa 1

**Plan:** schema YAML para preferencias y configuración simple, runtime de aplicación, validación.

**Trabajo del agente:** diseño del DSL (con tu supervisión cercana — esto es Nivel 3 del árbol de decisiones), implementación del runtime, tests.

### Semana 18 — Agente conversacional de personalización

**Plan:** el usuario habla, el agente entiende, el agente aplica vía DSL.

**Trabajo del agente:** prompt del agente, integración con Anthropic API, manejo de errores, eval suite básica.

### Semana 19 — Agente de cobranza (modo sugerir)

**Plan:** agente que cada mañana revisa CxC, prioriza, sugiere mensaje, no envía sin aprobación humana.

**Trabajo del agente:** prompt, conexión con MCP de CxC y de WhatsApp, eval suite, dashboard de aceptación.

### Semana 20 — Agente de stock (modo sugerir) + WhatsApp

**Plan:** agente que detecta productos bajos, sugiere reposición; WhatsApp Business API integrado para envío de mensajes.

**Output del mes 5:** la distribuidora tiene su sistema con dos agentes en modo sugerir, y el dueño puede pedirle al sistema cambios menores hablando.

## 5.6 Sub-fase 1.F — Mes 6: Distribuidora en producción

### Semana 21 — Migración de datos

**Plan:** importación del catálogo actual de la distribuidora, clientes, proveedores, deudas pendientes, stock inicial.

**Crítico:** este es el momento más delicado de todo el año. Si la migración va mal, el dueño pierde fe en el sistema.

**Tu trabajo:** estar presente toda la semana. Validar cada dataset antes de importarlo. Probar todo en sandbox primero. Tener plan de rollback si algo falla.

### Semana 22 — Capacitación + arranque controlado

**Plan:** entrenás al dueño y al equipo. Empezás con uso paralelo (sistema viejo + tuyo simultáneos).

### Semana 23-24 — Acompañamiento intensivo

**Plan:** estás disponible para resolver dudas y bugs en caliente. Cualquier error que aparezca lo arreglás en horas.

**Output del mes 6:** la distribuidora está usando el sistema diariamente para sus operaciones reales. Hito 1 cerrado.

## 5.7 Hitos del año 1 resumidos

| Mes | Hito | Riesgo principal |
|-----|------|------------------|
| 1 | Fundación técnica sólida | Que la deuda técnica te tome 2 meses en lugar de 1 |
| 3 | Ciclo comercial completo en sistema | Errores fiscales VE |
| 5 | Agentes operando, personalización Capa 1-2 | Costo de inferencia descontrolado |
| 6 | Distribuidora operando 30 días continuos | Migración de datos sale mal |
| 9 | Distribuidora completa (con POS, comisiones, despacho) | Que aparezca un bug crítico que tumbe la operación |
| 12 | Fábrica con OF y BOM | Complejidad de manufactura subestimada |
| 15 | Ambos negocios operando con sistema completo | Burnout |

---

# PARTE VI — Disciplina de Founder Solo

> **Esta sección es nueva. Trata las realidades específicas de trabajar solo, en horarios partidos, durante años.**

## 6.1 El ritmo sostenible

**Realidad:** vas a trabajar 15-25 horas semanales productivas en este proyecto, en paralelo a tu trabajo principal. Más es insostenible. Menos es lento de más.

**Cómo distribuir esas horas:**

Patrón recomendado:
- **Lunes a viernes:** 1-2 horas por noche (3-4 noches de las 5). Total: 4-8 horas.
- **Sábado o domingo:** 4-6 horas en bloque. Total: 4-6 horas.
- **Semanal real:** 8-14 horas. **Las "15-25 horas" son el techo aspiracional, no el suelo.**

**No te castigues si una semana hacés 6 horas.** Marcá la semana, retomá la siguiente. Lo que mata es abandonar, no ralentizar.

## 6.2 La sesión de 2-3 horas como unidad básica

Tu unidad mínima de trabajo productivo es una sesión de 2-3 horas. Sesiones de 30 minutos no rinden lo suficiente para justificar el costo de contexto-switch.

**Estructura de sesión típica de 2.5 horas:**

| Bloque | Duración | Qué hacés |
|--------|----------|-----------|
| Setup | 10 min | Café/té. Abrí el log. Releé tres preguntas del lunes (PARTE I.5). |
| Arranque agente | 15 min | El agente ejecuta PARTE 0 (secuencia de arranque). Tu reportá. |
| Trabajo concentrado | 90 min | Una tarea, focused. Sin redes, sin chat, sin notificaciones. |
| Revisión | 20 min | Mirás lo que produjo el agente. Aprobás o pedís ajustes. |
| Cierre | 15 min | Log actualizado. Push. Próxima sesión planeada. |

**Sesiones de 2-3h tres veces por semana = 6-9 horas concentradas reales = más output que 20 horas distraídas.**

## 6.3 Ritual del lunes (no negociable)

Todos los lunes, antes de cualquier otra cosa relacionada con el proyecto:

1. **Las tres preguntas de PARTE I.5** (5 minutos, escritas).
2. **Plan de la semana** (10 minutos): qué quiero terminar, en qué sesiones.
3. **Revisión del log de la semana anterior** (5 minutos): ¿qué quedó pendiente?

Si no podés hacer esto el lunes, hacelo el martes. Pero hacelo. **Sin este ritual, el proyecto deriva.**

## 6.4 Manejo de gaps

Vas a tener gaps. Días, semanas, ocasionalmente un mes entero. Reglas:

**Gap corto (1-7 días):**
- Antes de empezar el gap, hacé un commit limpio + log actualizado.
- Cuando volvés: ritual del lunes (aunque sea jueves).

**Gap medio (1-3 semanas):**
- Antes: cierre prolijo, PR a medias se cierra o se completa.
- Cuando volvés: leé el log de los últimos 30 días, no solo la última sesión. Mirá qué decisiones inmutables se tomaron. Si dudás de algo, releé las PARTE I y II.

**Gap largo (1+ mes):**
- Antes: si lo prevés, dejá una nota larga en `docs/agent-handoffs/`.
- Cuando volvés: **no te tires a codear inmediatamente.** Tomate una sesión completa solo para reorientarte. Releé el plan operativo. Mirá los últimos commits. Hacé una "sesión 0" sin código.

**Gap no planeado por crisis personal:**
- Es lo que es. La salud y la familia primero.
- El proyecto te espera.
- Cuando volvés, perdonate. Releé este párrafo.

## 6.5 Cuándo parar para descansar

Reglas duras:

- **Si trabajaste tres noches seguidas hasta tarde, la cuarta noche descansás.** Sin excepción.
- **Si llevás dos sesiones seguidas sin terminar la tarea planeada, parás esa serie y replaneás.** Empujar más fuerte cuando estás bloqueado no funciona.
- **Si te despertás un sábado pensando en bugs, ese día no codeás.** Salí, ejercicio, tiempo familiar. La mente necesita los sábados.
- **Una vez al mes, una semana sin tocar el proyecto.** Planeada de antemano. Tu cerebro hace su mejor trabajo cuando le das gaps.

## 6.6 Decisiones que no tomás solo (aunque podrías)

**Pedí input externo antes de decidir** para:

- Cualquier decisión Nivel 3 del árbol (afecta futuro de forma difícil de revertir).
- Cualquier cambio al modelo de pricing.
- Cualquier modificación al alcance del MVP.
- Cualquier decisión sobre buscar cliente externo antes de tiempo.
- Cualquier propuesta de "agregar una feature que no estaba en el plan".

**Quién puede ser ese input externo:**
- Un amigo técnico competente (idealmente con experiencia en software empresarial).
- El dueño del negocio piloto (para decisiones de producto).
- Un mentor o asesor (si tenés acceso).
- En última instancia, un foro como Indie Hackers, Founder Cafe, o un grupo de fundadores latinos.

**No es debilidad pedir input. Es lo que distingue a los founders solos que terminan de los que se queman.**

## 6.7 Salud mental — la única regla absoluta

Si en algún momento sentís alguna de estas señales, **el proyecto se pausa hasta resolver**:

- Insomnio recurrente por temas del proyecto.
- Ansiedad significativa.
- Aislamiento social (dejaste de ver amigos por trabajar).
- Cambios de humor marcados.
- Pensamientos de inutilidad o fracaso aunque las cosas vayan bien.

**El proyecto no vale tu salud mental. Ningún proyecto la vale.** Pausá, busca ayuda profesional si hace falta, retoma cuando estés bien. **Mejor pausar 3 meses que abandonar después de 12.**

---

# PARTE VII — Sistema de Checkpoints Adaptado

> **REESCRITO. La cadencia de v1 (diaria, semanal, quincenal) sigue, pero ajustada a founder solo.**

## 7.1 Cadencia para founder solo

| Cadencia | Tiempo invertido | Output |
|----------|------------------|--------|
| **Por sesión** | 5 min al cierre | Log de la sesión |
| **Semanal (lunes)** | 20 min | Tres preguntas + plan de semana + revisión log anterior |
| **Mensual** | 1 hora | Revisión de hito del mes, métricas, ajustes |
| **Trimestral** | 4 horas (un sábado) | Memo trimestral, releer PARTE I y II completas |
| **Cierre de sub-fase** | Medio día | Auditoría completa contra Definition of Done |

## 7.2 Checkpoint mensual — formato

Una hora, último viernes o sábado del mes:

1. **Estado contra el hito del mes** (15 min): ¿llegué? ¿con qué fricción?
2. **Métricas técnicas** (10 min): cobertura tests, errores en producción, latencia, deuda nueva.
3. **Métricas de proyecto** (10 min): horas reales trabajadas, gaps, calidad subjetiva del trabajo.
4. **Salud personal** (5 min): ¿cómo estoy? ¿estoy disfrutando? ¿estoy quemado?
5. **Plan del mes siguiente** (20 min).

Output escrito en `docs/checkpoints/mes-NN.md`.

## 7.3 Checkpoint trimestral — el más importante para founder solo

Cada 3 meses, **un sábado completo apartado.**

**Mañana — Reflexión:**
- Releer PARTE I y II de este plan completas. Sin código.
- Releer el `01_MVP_SCOPE_NEGOCIOS_PILOTO.md`.
- Releer el último mes de logs.
- Salir a caminar 30 min después (en serio, esto procesa).

**Tarde — Memo trimestral (formato Apéndice B.3 de v1):**
- ¿Estamos construyendo lo que dice 1.1?
- ¿Las cinco propiedades irrenunciables siguen siendo correctas para mi escenario?
- ¿Las sub-fases siguen siendo correctas?
- ¿Tentaciones detectadas?
- ¿Cambios al plan?

**Noche — descanso.** No trabajés más ese sábado. Domingo libre. Lunes empezás el nuevo trimestre.

## 7.4 Métricas que sí medís

Founder solo, sin equipo, sin VC pidiendo reportes — pero medís igual, **para vos**:

**Métricas técnicas (semanales, automáticas):**
- Cobertura de tests.
- Errores en producción (Sentry).
- Latencia p95.
- Costo de inferencia LLM por semana.

**Métricas de proyecto (mensuales, manuales):**
- Horas reales trabajadas (loguealas, vas a sorprenderte).
- Tareas planeadas vs completadas.
- CTFs creados vs cerrados.
- Calidad subjetiva (tu autoevaluación, 1-10).

**Métricas de cliente piloto (mensuales, una vez que arranque uso real):**
- Días de uso continuo.
- # de incidentes que requirieron tu intervención.
- # de sugerencias del agente aceptadas vs ignoradas.
- Feedback cualitativo del dueño.

## 7.5 Métricas que NO te obsesionan

Founder solo en Bloque 1, **no** mires obsesivamente:

- Hacker News rankings.
- Twitter/X engagement de cuentas competidoras.
- Anuncios de YC, ProductHunt.
- Funding rounds de startups en tu mismo espacio.
- Roadmaps públicos de SAP, Odoo, NetSuite.

Es ruido. Te desenfoca. Mirá una vez al trimestre máximo. **Tu juego es distinto: un cliente real andando vale más que mil tweets de competidores con humo.**

---

# PARTE VIII — Anti-Patrones Específicos para tu Escenario

> **REESCRITO. Los anti-patrones de v1 siguen aplicando; estos son los específicos de founder solo.**

## 8.1 Anti-patrón "Construyo todo en mi cabeza, no consulto"

**Síntoma:** decidís solo todo, racionalizás solo todo, terminás convencido de cosas que están mal.
**Por qué falla:** los puntos ciegos no se ven solo. Es físicamente imposible.
**Antídoto:** PARTE VI.6. Pedí input para decisiones Nivel 3.

## 8.2 Anti-patrón "El AI me dijo que está bien"

**Síntoma:** dejás que el agente IA valide su propio trabajo. Te dice "esto sigue las mejores prácticas", lo aprobás.
**Por qué falla:** los LLMs son sycophants. Te dicen lo que querés oír. No reemplazan revisión humana crítica.
**Antídoto:** revisá código del agente con la misma severidad con que revisarías el de un junior nuevo. Si algo se siente raro, lo es.

## 8.3 Anti-patrón "Construyo en stealth durante 2 años"

**Síntoma:** no le mostrás a nadie el proyecto hasta que esté "listo". Después de 2 años, está casi listo.
**Por qué falla:** el feedback temprano (incluso de un amigo) te ahorra meses de derroche.
**Antídoto:** desde el mes 3, una vez al mes le mostrás avances a alguien capaz. Aunque sea un amigo. Aunque te parezca demasiado pronto.

## 8.4 Anti-patrón "Mi familia me usa, eso es validación"

**Síntoma:** los negocios familiares lo usan, vos creés que tenés validación de mercado.
**Por qué falla:** un familiar tolera cosas que un cliente externo nunca toleraría. Validación familiar ≠ validación de mercado.
**Antídoto:** consciente de eso, en mes 12-15 buscás un cliente externo que no te conozca. Su feedback es la validación real.

## 8.5 Anti-patrón "Me compro mi propia historia"

**Síntoma:** te convencés de que el proyecto va increíble. Posteás avances en LinkedIn. Te ven con buenos ojos. Te decís "voy súper".
**Por qué falla:** la realidad de retención, uso, ROI del cliente es lo único que importa. La narrativa propia es trampa.
**Antídoto:** cada checkpoint mensual, escribí dos columnas: "lo que les diría a otros" y "la realidad fría". La diferencia entre las columnas es tu nivel de auto-engaño.

## 8.6 Anti-patrón "El próximo feature es el que cambia todo"

**Síntoma:** "una vez que termine X, todo va a fluir". Lo terminás. No fluye. "Una vez que termine Y...".
**Por qué falla:** el problema rara vez es la falta de un feature. Es construcción mal direccionada.
**Antídoto:** si pensás esto dos veces seguidas, parate y hacé un checkpoint trimestral aunque toque antes.

## 8.7 Anti-patrón "Tengo que aprovechar este momento de tracción"

**Síntoma:** llegás a un hito, sentís impulso, querés acelerar, dormís 4 horas, push, push, push.
**Por qué falla:** el sprint te lleva al burnout. La tracción real es maratón.
**Antídoto:** los hitos se celebran descansando, no acelerando.

## 8.8 Anti-patrón "Total nadie usa esto todavía, puedo cambiar lo que quiera"

**Síntoma:** como solo tus familiares usan el sistema, hacés cambios disruptivos sin avisar, rompes flujos.
**Por qué falla:** estás entrenándote a NO tener disciplina de producto. Cuando llegue cliente externo, será caótico.
**Antídoto:** desde el día 1, tratá los cambios disruptivos como si tuvieras 1.000 clientes. Versionado, comunicación, migración cuidadosa. Construye el músculo desde temprano.

## 8.9 Anti-patrón "El AI puede hacer todo, no necesito aprender"

**Síntoma:** dejás que el agente decida arquitectura, librerías, patrones, sin entender realmente.
**Por qué falla:** cuando el agente se equivoca (lo va a hacer), no detectás el error porque no entendés la lógica.
**Antídoto:** entendé al menos al 70% lo que el agente produce. Si no entendés algo, pediéndole explicación o leé documentación. Tu rol es supervisor, supervisor implica entender.

## 8.10 Anti-patrón "Voy a tomar un loan para acelerar"

**Síntoma:** después de 6 meses sin ingresos del proyecto, considerás endeudarte personalmente para "comprar tiempo".
**Por qué falla:** deuda personal con proyecto sin revenue es la receta más segura del estrés tóxico. Decidís peor bajo presión financiera.
**Antídoto:** si necesitás capital, levantás capital propiamente (familia y amigos como friends-and-family round, o angels regionales chicos). Deuda personal nunca para esto.

---

# APÉNDICE A — Decisiones Inmutables

> **Idéntico a v1. Las 20 decisiones inmutables. No las repito por brevedad. Están en `OMNI_AI_NATIVE_EXECUTION_PLAN.md` v1.**

---

# APÉNDICE C — Norte Estrella

> **NUEVO. La visión grande de los 5 puntos que agregaste, archivada acá. Se relee una vez al año, no entra al plan operativo.**

## C.1 La Visión a 10+ Años

Lo que Omni AI-Native podría ser, eventualmente, si todo va bien y se construye con paciencia:

**Un sustrato de software empresarial latinoamericano** sobre el cual:

1. **Una empresa puede operarse completamente** — todos sus procesos, datos, decisiones — con IA agéntica como motor central. El humano supervisa, decide en lo importante, delega lo rutinario.

2. **Una empresa puede convertirse de manual a AI-native** sin reescribir todo. El sistema absorbe sus procesos actuales, los modela, sugiere optimizaciones, los automatiza progresivamente.

3. **Una persona puede crear una empresa desde cero, con IA como cofundador.** Desde la idea hasta la operación, todo dentro del mismo ambiente: chat con IA → spec → app → infraestructura → ERP → primer cliente.

4. **Empresas en el sistema descubren y se conectan entre sí** — proveedores, clientes, partners, talento — formando una red comercial real, no una red social.

5. **Un usuario individual puede usar el mismo sistema** para sus finanzas personales, sus emprendimientos, sus servicios diarios, fluidamente, conectado al ecosistema empresarial cuando lo necesita.

6. **Cada cliente puede lanzar plataformas digitales propias** — webs, apps, marketplaces verticales, redes B2B sectoriales — sin contratar desarrolladores.

7. **Todo esto cumple regulación local** en cada país donde opera, con localización profunda, no superficial.

## C.2 Cómo se construye realmente

**No de una vez.** Las siete capacidades anteriores se construyen en orden, durante 10-15 años, con capital incrementado por etapa. Cada etapa valida la siguiente.

**No solo.** Bloque 1 sí solo + AI. Bloque 2 con 2-5 personas. Bloque 3+ con equipo, capital, posiblemente cofundadores complementarios.

**No el primero.** Otros van a intentar lo mismo. Algunos llegarán antes a piezas específicas. **El que gana es el que ejecuta su pieza con más profundidad, no el que prometió todo primero.**

**Bien construido.** La diferencia entre una superapp respetada y un Frankenstein vendrá de cuánta disciplina se mantuvo en los principios desde el día 1.

## C.3 Cuándo se relee este apéndice

- Una vez al año, en el aniversario del proyecto.
- Cuando estés en checkpoint trimestral y dudes si lo que estás haciendo "vale la pena".
- Cuando vayas a tomar una decisión Nivel 3 importante y necesites ver el horizonte.
- Cuando estés tentado a pivotar a algo más rápido y rentable a corto plazo.

**No se relee:** semanalmente. Mensualmente. En momentos de cansancio. Cuando estás escribiendo código.

El Norte Estrella es para orientar; no para presionar.

---

# Cierre del documento

Este plan v2.0 es la versión honesta para tu situación real. La visión grande sigue intacta como Norte Estrella. La disciplina de la PARTE I y II sigue intacta porque esa nunca cambia. Lo que cambia es el ritmo, el alcance del primer ciclo, y los anti-patrones específicos del founder solo.

Si seguís este plan con disciplina razonable durante 12-15 meses, vas a tener algo que pocos founders solos tienen: dos negocios reales operando con tu sistema, primitivas técnicas sólidas, y una decisión de bifurcación con datos en lugar de fe.

Eso es excelente posición para cualquiera de los tres caminos del Bloque 3.

---

*Documento operativo principal. Versión 2.0. Revisión obligatoria al cierre de cada sub-fase del Bloque 1, o cada trimestre — lo que ocurra primero.*
