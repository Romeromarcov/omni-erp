# Omni AI-Native — Plan de Ejecución y Disciplina Operativa
**Versión:** 1.0 — Plan vivo, debe revisarse quincenalmente
**Audiencia:** Cualquier persona o agente de IA que escriba una línea de código en este proyecto
**Relación con otros documentos:** Este plan no reemplaza el `OMNI_ERP_MASTER_PLAN.md` original; lo complementa. Cuando entren en conflicto, este plan tiene precedencia para todo lo escrito después de su fecha de aprobación. El plan original sigue siendo la fuente de verdad sobre el código existente, los bugs corregidos, y el conocimiento del dominio venezolano.

> **Cómo leer este documento:** No lo leas de corrido la primera vez. Lee la PARTE I (visión perpetua) hasta entenderla a fondo. Luego usa el resto como referencia. Vuelve a la PARTE I cada lunes en la mañana. Si algún día sientes que estás haciendo algo que la PARTE I no respalda, detente y resuelve la contradicción antes de seguir.

---

## ÍNDICE

- [PARTE I — La Visión Perpetua (relee cada lunes)](#parte-i--la-visión-perpetua)
- [PARTE II — Reglas Inviolables del Proyecto](#parte-ii--reglas-inviolables-del-proyecto)
- [PARTE III — Cómo Decidir cuando Tengas Dudas](#parte-iii--cómo-decidir-cuando-tengas-dudas)
- [PARTE IV — Plan de Ejecución por Fases](#parte-iv--plan-de-ejecución-por-fases)
- [PARTE V — Día 1 al Día 90: La Hoja de Ruta Concreta](#parte-v--día-1-al-día-90)
- [PARTE VI — Instrucciones para Agentes de IA Escribiendo Código](#parte-vi--instrucciones-para-agentes-de-ia)
- [PARTE VII — Sistema de Checkpoints y Auditorías](#parte-vii--sistema-de-checkpoints)
- [PARTE VIII — Anti-Patrones Específicos a Evitar](#parte-viii--anti-patrones)
- [PARTE IX — Glosario de Términos del Proyecto](#parte-ix--glosario)
- [APÉNDICE A — Decisiones Inmutables](#apéndice-a--decisiones-inmutables)
- [APÉNDICE B — Plantillas de Trabajo](#apéndice-b--plantillas-de-trabajo)

---

# PARTE I — La Visión Perpetua

> **Esta sección es la única que NUNCA cambia. Si en algún momento parece que necesita cambiar, no la cambies todavía: documenta el conflicto, espera una semana, vuelve a leerla. Si después de eso sigues creyendo que debe cambiar, abre una propuesta formal.**

## 1.1 Qué estamos construyendo (en una frase)

**Un sistema operativo de negocio AI-nativo, donde una empresa de cualquier tamaño, país, industria o nivel de formalidad puede operar y evolucionar su gestión completa hablándole en lenguaje natural — y eventualmente lanzar plataformas digitales propias sin contratar desarrolladores.**

Si tu trabajo de hoy no se conecta de manera comprensible con esa frase, párate y pregúntate por qué.

## 1.2 Las cinco propiedades irrenunciables del producto

Estas cinco propiedades son la firma del producto. Cualquier feature que las contradiga no se construye, sin importar quién la pida.

1. **Conversacional primero, no como añadidura.** El usuario debe poder operar y modificar el sistema hablándole. Las pantallas existen, son útiles, pero son una de las superficies de uso, no la principal.

2. **Determinista donde la ley lo exige, agéntico donde el juicio paga.** Asientos contables, cálculo de impuestos, folios fiscales: código determinista, jamás LLM. Decisiones operativas (qué cliente cobrar primero, cómo redactar un mensaje, qué proveedor contactar): agentes con humanos en el bucle.

3. **Personalizable por conversación, no por consultoría.** Una persona sin formación técnica debe poder adaptar su instancia del ERP hablándole. La personalización es un artefacto declarativo versionado, no código generado al vuelo.

4. **Cada empresa es potencialmente un emisor de software.** El ERP no solo opera el negocio: es sustrato sobre el cual el cliente puede lanzar webs, apps, plataformas, y servicios — eventualmente. Esto se construye en fases, pero las primitivas se respetan desde el día 1.

5. **Localización y regulación son ciudadanos de primera clase.** Venezuela primero, sí. Pero la arquitectura nunca asume Venezuela. Cada decisión que toque fiscalidad, comprobantes, monedas, calendarios, identificadores, derechos del consumidor, debe pasar por la pregunta: "¿cómo se ve esto en tres países distintos?".

## 1.3 Los cinco principios arquitectónicos no negociables

Distinto de las propiedades del producto. Estos son del código.

1. **Event sourcing como verdad.** Todo evento de negocio es inmutable. El estado actual es una proyección. Cualquier número en cualquier pantalla debe ser explicable: "este saldo viene de estos 47 eventos".

2. **Multi-tenant absoluto desde el día 1.** Toda tabla de negocio tiene `id_empresa`. Ningún endpoint devuelve datos de otra empresa, jamás. Esta regla es una pre-condición de fusión de cualquier PR.

3. **MCP en todo módulo, desde el primer módulo.** Cada bounded context expone capacidades vía Model Context Protocol además de su API REST. No es opcional; es co-requisito.

4. **Determinismo donde aplica, no antes ni después.** Es trampa hacer que un LLM "ayude" a generar un asiento contable y luego validarlo. La regla es: el LLM propone, código determinista valida y emite. Si el determinista rechaza, el LLM no insiste.

5. **Personalización como artefacto declarativo versionado.** Toda modificación a una instancia del ERP — desde "cambiar nombre de campo" hasta "agregar módulo entero" — se expresa como un YAML/DSL versionado, validable, reversible. Nunca como código suelto inyectado.

## 1.4 La frase que debe morir

**"Esto lo añadimos rápido, después lo hacemos bien."**

Cada vez que aparezca esa frase, párate. La deuda técnica documentada en el plan original no ocurrió por falta de talento; ocurrió porque esa frase ganó muchas pequeñas batallas. En este proyecto, esa frase pierde por defecto.

Si una excepción es genuinamente necesaria, se documenta como "Compromiso técnico fechado", con una fecha de vencimiento clara y un dueño asignado. Sin esos dos campos, la excepción no procede.

## 1.5 Las tres preguntas que respondes cada lunes en 5 minutos

Antes de empezar la semana, contesta por escrito (un párrafo cada una basta):

1. **Lo que voy a construir esta semana, ¿se conecta con la frase del 1.1? ¿Cómo?**
2. **¿Algo de lo que voy a construir esta semana viola una de las cinco propiedades irrenunciables o los cinco principios arquitectónicos? Si sí, ¿por qué procede igual?**
3. **¿Qué métrica concreta va a estar mejor el viernes que hoy lunes, gracias a este trabajo?**

Si alguna no se puede contestar con sinceridad, esa semana no está bien planeada. Replanéala antes de escribir código.

---

# PARTE II — Reglas Inviolables del Proyecto

> **Estas son reglas operativas. La violación de cualquiera bloquea la entrega.**

## 2.1 Reglas de código

### R-CODE-1: Multi-tenant siempre
Todo modelo de negocio nuevo tiene `id_empresa`. Todo viewset filtra por `id_empresa` del usuario autenticado. Cada PR incluye un test de aislamiento. Sin estos tres, no hay merge.

### R-CODE-2: Sin SQLite en ningún entorno
Desarrollo, staging, producción: PostgreSQL. La diferencia en comportamiento de constraints parciales y transacciones ya costó bugs documentados. SQLite no vuelve a entrar.

### R-CODE-3: Sin `any` en TypeScript, sin `print()` en Python de producción
TypeScript estricto, sin escapes. Python de producción usa `logger`, no `print` ni `traceback.print_exc()`. Esto se chequea en CI; no se merge si falla.

### R-CODE-4: Decimal para dinero, siempre
Nunca `float` para montos, tasas, porcentajes que afecten dinero. `DecimalField(max_digits=18, decimal_places=4)` para montos generales, `decimal_places=2` para totales finales al cliente, `decimal_places=8` para crypto y tasas de cambio precisas.

### R-CODE-5: UUIDv7, no UUIDv4
Cambio respecto al plan original: UUIDv7 (ordenable temporalmente). Mismas garantías de seguridad y unicidad, mejor localidad de índice. Hay librería estable en Python y JS; usarla.

### R-CODE-6: Soft delete, no hard delete
`activo=False` o `estado='ANULADO'`. La excepción única es contenido del usuario que la ley obliga a borrar (GDPR, LGPD): en ese caso, hay un proceso documentado y auditado, no DELETE silencioso.

### R-CODE-7: API-first
Toda lógica de negocio existe primero como capacidad invocable (REST + MCP) antes de tener UI. Si alguien construye UI sobre lógica que no expone API, el PR se rechaza.

### R-CODE-8: Sin secretos en código, sin secretos en logs
Variables de entorno o vault. Logs jamás contienen tokens, contraseñas, datos completos de tarjeta, claves privadas, ni datos médicos identificables. Pre-commit hook y revisión de PR lo verifican.

### R-CODE-9: Tests de integración para flujos críticos, antes de merge
Los flujos críticos son: crear venta + generar factura + descontar stock + asentar contable + generar saldo CxC. Cualquier cambio en cualquiera de estos requiere que el test end-to-end siga pasando. Sin esto, no hay merge.

### R-CODE-10: Prohibido `null=True, blank=True` en campos lógicamente obligatorios
Si un campo debe tener valor (FK obligatoria, monto requerido, fecha requerida), no se hace opcional para "evitar errores en migración". Se hace obligatorio y la migración resuelve los datos heredados.

## 2.2 Reglas de proceso

### R-PROC-1: Una sola fuente de verdad por dominio
El "Master Plan" original es la fuente de verdad para lo construido hasta abril 2026. Este plan es la fuente de verdad para lo que se construye desde ahora. No se duplica documentación; se enlaza. Documentos paralelos en repositorios distintos están prohibidos.

### R-PROC-2: PRs pequeños, mergeables, focales
Un PR hace una cosa. Si el diff supera 800 líneas (sin contar tests, migraciones, package locks), se divide. Excepción: refactors mecánicos o renombres masivos, que se marcan como tales.

### R-PROC-3: Code review obligatorio, también para humanos que trabajan con IA
Un agente de IA puede escribir código, pero un humano debe revisar y aprobar. Auto-merge desde PR generado por agente está prohibido. La razón es que la deriva de visión empieza en cambios pequeños que parecen razonables y nadie los cuestiona.

### R-PROC-4: CI verde es no-negociable
Tests, lint, type-check, build. Si alguno falla, no hay merge. "Es un fallo flaky" no es excusa: si es flaky, se marca como bug y se arregla, no se ignora.

### R-PROC-5: Migraciones reversibles o explícitamente marcadas como no reversibles
Toda migración Django se prueba en reverse. Si genuinamente no es reversible (caso raro), se documenta en el commit y en el changelog del release.

### R-PROC-6: Los compromisos técnicos se vencen
Cualquier excepción a una regla, marcada como "Compromiso técnico fechado", tiene un campo `vence_en` (fecha) y un campo `dueño` (persona). Cuando vence, hay un issue automático. Si pasa de 30 días vencido, escala a quien lleva el proyecto.

### R-PROC-7: La quincena impar es de pago de deuda
Cada dos semanas, una semana entera (o 30% del tiempo del equipo) se dedica a deuda técnica, refactor, tests faltantes, documentación de lo que se construyó. No se pospone "para cuando haya tiempo". Esto es lo que evita el escenario de "ya tenemos 60 módulos a medias".

### R-PROC-8: Un cliente real desde el día 90
A más tardar el día 90 desde el inicio del pivot, hay un cliente design partner real usando el sistema en producción para algo, aunque sea un módulo. La razón: el feedback real es la única defensa contra la deriva de visión interna.

## 2.3 Reglas de producto

### R-PROD-1: Nada se llama "AI-powered" si no es AI-nativo
Si una feature usa LLM solo para parsear input y luego es CRUD tradicional, no se promociona como AI. La diferencia entre "ERP con IA" y "ERP AI-nativo" se gana o se pierde en estos detalles. Marketing y producto se alinean en esto.

### R-PROD-2: Personalización del usuario antes que personalización por consultoría
Si una feature solo se puede activar/configurar por alguien técnico interno, antes de marcarla como entregada hay que asegurarse de que un usuario no técnico también pueda hacerlo conversacionalmente. La excepción son funciones de plataforma (creación de tenants, cambios de plan), no de negocio.

### R-PROD-3: La complejidad se esconde, no se elimina
La realidad fiscal venezolana es compleja; el usuario no debe lidiar con eso. La realidad de blockchain es compleja; el usuario no debe ver "gas fees". El sistema asume la complejidad por dentro y entrega simplicidad por fuera. Si una feature obliga al usuario a entender plumbing, está mal envuelta.

### R-PROD-4: Reversibilidad por defecto
El usuario puede deshacer cualquier acción operativa hecha por él o por un agente, durante un plazo razonable (configurable, default 30 días). Esto es co-requisito del agentic; sin reversibilidad fácil, el cliente no confía en delegar.

### R-PROD-5: Transparencia de la IA
Cualquier acción tomada por un agente queda registrada con: qué prompt usó, qué herramientas invocó, qué datos consideró, qué decidió, qué humano aprobó. El usuario puede pedir esa explicación y la recibe en lenguaje natural en menos de 3 segundos.

---

# PARTE III — Cómo Decidir cuando Tengas Dudas

Esta sección es para los momentos en los que aparece una decisión que no está cubierta por las reglas. Cómo procesar.

## 3.1 El árbol de decisiones de 5 niveles

Cuando aparezca una duda sobre qué hacer, recórrelo en orden:

**Nivel 1 — ¿Lo prohibe explícitamente alguna regla R-CODE, R-PROC o R-PROD?**
Si sí: no se hace. Caso cerrado.

**Nivel 2 — ¿Va contra alguna de las cinco propiedades irrenunciables del producto (1.2) o los cinco principios arquitectónicos (1.3)?**
Si sí: no se hace, o se replantea hasta que no contradiga. Caso cerrado.

**Nivel 3 — ¿La decisión afecta el comportamiento futuro del sistema en formas difíciles de revertir?**
(Schema de datos, API pública, modelo de personalización, formato de eventos.) Si sí: documenta dos alternativas, escribe los trade-offs en una página, comparte con al menos una persona más, espera 24 horas, decide. Una vez decidida, va al "Apéndice A — Decisiones Inmutables" de este documento.

**Nivel 4 — ¿La decisión es operativa y puede revertirse en una semana o menos?**
Si sí: decide tú, documenta brevemente en un commit message claro, sigue.

**Nivel 5 — ¿Es trivial?**
Decide y sigue. No documentes para no contaminar el historial.

## 3.2 Cuando aparezca un conflicto entre reglas

A veces dos reglas parecen pedir cosas opuestas. Orden de prioridad cuando eso pase:

1. Las cinco propiedades irrenunciables del producto (1.2).
2. Los cinco principios arquitectónicos (1.3).
3. Las reglas R-CODE.
4. Las reglas R-PROC.
5. Las reglas R-PROD.
6. Velocidad de entrega.

Si aplicar la regla más importante implica costo, ese costo se asume; no se baja la regla más importante para ahorrar costo.

## 3.3 Cuando aparezca una excepción genuina

A veces hay razones legítimas para excepciones. El proceso:

1. **Escribe la excepción como Compromiso Técnico Fechado** con el formato del Apéndice B.
2. **Asigna un dueño** (persona específica, no "el equipo").
3. **Pon fecha de vencimiento** (no más de 90 días por defecto).
4. **Documenta la regla violada y la razón.**
5. **Crea un issue en el tracker** con etiqueta `tech-debt` y el vencimiento.
6. **Continúa.**

El día que vence sin haberse resuelto, el dueño se reúne con quien lleva el proyecto. Pasados 30 días vencidos, escala al nivel siguiente.

## 3.4 Cuando un agente de IA proponga algo que parece razonable pero te incomoda

Esto es importante. Los agentes de IA tienden a producir soluciones que se ven competentes pero a veces pierden la visión. Si te incomoda algo, no lo apruebes hasta haber respondido por escrito:

1. ¿Qué propiedad irrenunciable o principio arquitectónico podría estar violando?
2. ¿Qué decisión inmutable del Apéndice A podría estar contradiciendo?
3. ¿En qué reescenarios futuros me puede doler esto?
4. ¿Hay una alternativa que respete todo?

Si las cuatro respuestas te dejan tranquilo, aprueba. Si alguna te deja incómodo, pide rework. La incomodidad es señal, no ruido.

---

# PARTE IV — Plan de Ejecución por Fases

> **Lectura obligatoria antes de planear sprint alguno. Las fases no son sugerencias; son la columna vertebral del plan.**

## 4.1 Filosofía de fases

- **Una fase no se da por terminada hasta que se cumple su criterio de éxito.** No por tiempo transcurrido.
- **No se empieza la fase N+1 antes de cerrar la fase N.** Excepción: trabajo de exploración o preparación, claramente marcado como tal, que no produce código de producción.
- **Cada fase tiene un Definition of Done explícito** y se reviewa con todo el equipo antes de declarar cierre.
- **Las fases tienen estimados de tiempo, pero los estimados son escenarios, no compromisos.** Si una fase toma el doble, eso es información, no fracaso. La pregunta es: ¿la fase sigue siendo correcta?

## 4.2 Resumen de fases

| Fase | Nombre | Duración estimada | Criterio de éxito |
|------|--------|-------------------|-------------------|
| 0 | Fundación AI-nativa | 3-4 meses | Event store + MCP runtime + plano agéntico v0 + deuda técnica de Master Plan saldada |
| 1 | MVP AI-nativo | 3-4 meses | Cliente real operando en VE; agentes operan en modo "sugerir"; DSL personalización Capa 1-2 funcional |
| 2 | Profundización agéntica | 3-4 meses | Agentes en modo "ejecutar con reversa"; IoT v1; presencia digital simple por cliente |
| 3 | Diferenciación y verticales | 4-6 meses | Marketplace personalizaciones v1; segundo país (MX o CO); app móvil contenedora |
| 4 | Plataforma de plataformas | 6-12 meses | Platform Spaces v1 funcional; Rosa puede lanzar FarmaCaracas |
| 5+ | Casos especializados y expansión | continuo | Anclajes blockchain útiles; salud; trazabilidad; expansión multi-país |

## 4.3 Fase 0 — Fundación AI-nativa

**Duración estimada:** 12-16 semanas. **Lo bloqueante:** todo lo demás depende de Fase 0; apurar es contraproducente.

### 4.3.1 Objetivos de Fase 0

1. Saldar la deuda técnica de la sección 2.4 del Master Plan.
2. Introducir las primitivas AI-nativas (event store, MCP runtime, plano agéntico v0) sin romper lo existente.
3. Migrar progresivamente lo construido para que opere en el nuevo modelo, sin big bang.

### 4.3.2 Workstreams de Fase 0 (paralelos)

**WS-1: Saneamiento técnico**
- Migración SQLite → PostgreSQL en todos los entornos.
- Configuración Docker Compose completa (Postgres, Redis, Celery, Kafka/Redpanda).
- Setup de pytest, vitest, CI con GitHub Actions.
- Refactor TanStack Query.
- División de ModalPago.tsx en subcomponentes.
- Eliminación de los `any` restantes.
- Tests de aislamiento multi-tenant para todos los módulos existentes.

**WS-2: Event store y proyecciones**
- Selección de tecnología (recomendación: Redpanda por simplicidad operativa, mismo protocolo Kafka).
- Diseño del esquema de eventos (Event Envelope estándar).
- Convención de nombres (`<bounded_context>.<aggregate>.<event_name>`).
- Primer dominio adoptado: `ventas`. Cada acción de ventas emite eventos. Las proyecciones existentes (tablas) se actualizan vía consumer.
- Documentación del catálogo de eventos vivo.

**WS-3: MCP Runtime**
- Framework propio delgado para exponer cada bounded context como servidor MCP.
- Convención: cada módulo Django genera automáticamente un servidor MCP con sus operaciones de negocio (no CRUD genérico, sino operaciones del dominio: `crear_pedido`, `confirmar_recepcion`).
- Capability tokens para autenticación y autorización por agente.
- Observabilidad: cada llamada MCP se loguea con prompt origen, agente, latencia, costo.

**WS-4: Plano agéntico v0**
- Selección de framework (recomendación: Anthropic SDK + orquestación propia delgada; no comprometerse con LangChain/CrewAI/AutoGen, son frameworks que cambian rápido).
- Multi-proveedor: Claude (default), GPT, Gemini. Modelos locales (Ollama) para tareas sensibles.
- Sistema de evals: dataset de casos dorados, runner automatizado.
- Primer agente piloto: clasificador de gastos (caso simple, alto valor inmediato, fácil de medir).
- Niveles de autonomía configurables por tenant.

**WS-5: DSL de Personalización (diseño)**
- Diseño de las seis primitivas (campos, entidades, estados, reglas, vistas, conectores).
- Esquema YAML/JSON validable.
- Versionado y diff de personalizaciones.
- Aún no se construye el agente de personalización (eso es Fase 1); en Fase 0 se diseña el formato y se hace un PoC.

### 4.3.3 Definition of Done de Fase 0

- [ ] Toda la deuda técnica del Master Plan sección 2.4 está saldada o tiene Compromiso Técnico Fechado vigente.
- [ ] PostgreSQL es la única base de datos en uso.
- [ ] Cobertura de tests: backend ≥ 30%, frontend ≥ 20%, flujos críticos al 100%.
- [ ] Event store en producción, con al menos un dominio (`ventas`) emitiendo eventos.
- [ ] MCP runtime funcional, con al menos `ventas` y `finanzas` exponiéndose como servidores MCP.
- [ ] Primer agente operativo (clasificador de gastos) en shadow mode, con eval suite corriendo en CI.
- [ ] DSL de personalización: spec aprobada, validador implementado, PoC de aplicación funcional.
- [ ] Documentación: este plan está actualizado, el Master Plan tiene anotaciones donde corresponde.

## 4.4 Fase 1 — MVP AI-nativo vendible

**Duración estimada:** 12-16 semanas. **Criterio de éxito definitorio:** un cliente venezolano pagando una suscripción y operando en producción.

### 4.4.1 Objetivos de Fase 1

1. Completar las integraciones de los módulos existentes para que el ciclo comercial funcione end-to-end (venta → factura fiscal → stock → CxC → contabilidad básica).
2. Activar el agente de personalización conversacional Capas 1-2 (preferencias y configuración de negocio).
3. Llevar al primer agente operativo a producción (modo "sugerir").
4. Cerrar el primer cliente design partner.

### 4.4.2 Trabajo concreto

**Heredado del Master Plan (completar):**
- `ventas` con todas las integraciones (inventario, fiscal, CxC, contabilidad básica).
- `inventario`: movimientos, stock por sucursal, kardex, lotes.
- `fiscal` Venezuela: IVA, IGTF, retenciones, libros SENIAT, factura fiscal PDF.
- `reportes`: plantillas PDF de factura, cotización, nota de entrega, recibo.
- `notificaciones`: in-app, email, WhatsApp Business API.
- `compras`: ciclo solicitud → OC → recepción.
- `crm`: clientes con búsqueda RIF, historial, límite de crédito.
- `cuentas_por_cobrar`: aging, estado de cuenta, abonos.
- `saas_core` mínimo: planes, suscripciones, expiración.

**Nuevo (AI-nativo):**
- Agente de personalización Capa 1 (preferencias) y Capa 2 (configuración de negocio): el usuario habla, el agente aplica.
- Agentes operativos en modo "sugerir":
  - Clasificador de gastos.
  - Estratega de cobranza diaria.
  - Conciliador bancario asistido.
  - Sugeridor de reorden de inventario.
- Sandbox espejo por tenant funcional.
- Primer paquete de localización: `vzla-localization-pack` v1, con todo lo fiscal venezolano encapsulado y versionado.

### 4.4.3 Definition of Done de Fase 1

- [ ] Cliente design partner real, pagando, operando diariamente, durante al menos 4 semanas continuas.
- [ ] Ciclo end-to-end funcional: cotización → pedido → factura fiscal → descuento de stock → asiento contable → saldo CxC → cobranza con agente sugiriendo.
- [ ] Agente de personalización aplicando cambios de Capa 1-2 sin intervención técnica humana.
- [ ] Al menos 4 agentes operativos en producción en modo "sugerir", con métricas de aceptación humana ≥ 60%.
- [ ] `vzla-localization-pack` v1: documentado, versionado, instalable como módulo.
- [ ] Documentación: handbook de cliente, manual de operador, runbook de incidentes.

## 4.5 Fase 2 — Profundización agéntica

**Duración estimada:** 12-16 semanas.

### 4.5.1 Objetivos

1. Pasar agentes a "ejecutar con reversa" en cobranza, OC rutinarias, conciliación.
2. Activar IoT v1 (lectores de barras, balanzas, gateway MQTT básico).
3. Activar generación de presencia digital simple (cada cliente tiene su web pública conectada al catálogo).
4. Tener 5-10 clientes pagando.

### 4.5.2 Trabajo concreto

**Heredado:**
- `rrhh` + `nomina` Venezuela completa.
- `contabilidad` con asientos automáticos.
- `cuentas_por_pagar`.
- `tesoreria` y conciliación bancaria.
- `portal_vendedores` PWA offline.
- `portal_empleados`.
- `delivery_general`.
- `retail_pos` básico.
- `gestion_documental` con MinIO.
- `gestion_aprobaciones`.
- `analitica_negocio` dashboard.
- `gestion_tareas_colaborativas`.
- `comunicacion_interna`.
- `migracion_datos` UI.

**Nuevo:**
- Agentes en modo "ejecutar con reversa" (cobranza, OC rutinarias, conciliación, clasificación).
- IoT v1: gateway MQTT, lectores de código de barras, balanzas, integración POS.
- DSL Capa 3 (extensiones de modelo).
- Generador de webs públicas v1 conectado al catálogo del ERP.
- Adaptadores MCP adicionales: bancos VE (Bancamiga, Mercantil), WhatsApp Business, BCV robusto.
- Meta-agente de mejora v1 (analiza correcciones humanas, propone ajustes a prompts/herramientas).

### 4.5.3 Definition of Done

- [ ] 5-10 clientes pagando, ≥ 3 con uso diario consistente.
- [ ] Agentes en producción en modo "ejecutar con reversa" con métricas de error < 2%.
- [ ] IoT funcionando en al menos un cliente (lector de barras o balanza integrada al POS).
- [ ] Cliente puede activar y configurar su web pública desde conversación con agente.
- [ ] DSL Capa 3 funcionando: usuario puede agregar campos personalizados conversacionalmente.

## 4.6 Fase 3 — Diferenciación y verticales

**Duración estimada:** 16-24 semanas.

### 4.6.1 Objetivos

1. Marketplace de personalizaciones v1.
2. Segundo país (México o Colombia) con paquete de localización propio.
3. App móvil contenedora con configuración remota lista para producción.
4. 30-50 clientes pagando.

### 4.6.2 Trabajo concreto

**Heredado:**
- `manufactura` MRP.
- `control_calidad`.
- `costos`.
- `servicio_cliente` mesa de ayuda.
- `crm_ventas_marketing`.
- `compliance`.
- `banca_electronica` automatizada.
- `planificacion_financiera`.
- `activos_fijos`.

**Nuevo:**
- Marketplace v1: catálogo de personalizaciones públicas, instalación con un clic, revenue share con creadores.
- Segundo paquete de localización: `mx-localization-pack` o `co-localization-pack`.
- App móvil contenedora con config remota.
- Agentes especializados verticales (manufactura, retail, servicios).
- Meta-agente de mejora operativo a escala.

### 4.6.3 Definition of Done

- [ ] 30-50 clientes pagando, ≥ 5 fuera de Venezuela.
- [ ] Marketplace con ≥ 20 personalizaciones públicas, ≥ 3 creadores externos.
- [ ] Segundo país operando con compliance fiscal completo.
- [ ] App móvil contenedora en stores con al menos un cliente lanzado.

## 4.7 Fase 4 — Plataforma de plataformas

**Duración estimada:** 24-48 semanas.

### 4.7.1 Objetivos

1. Platform Spaces v1 funcional.
2. Federación entre tenants con catálogo unificado y carrito multi-vendor.
3. Generación de apps móviles parametrizables.
4. APIs y servidores MCP públicos por Platform Space.

### 4.7.2 Trabajo concreto

- Platform Spaces como entidad de primera clase.
- Federación de catálogos e inventarios.
- Carrito multi-vendor + lógica de logística consolidada.
- Pagos cross-border básicos (USDT/USDC).
- Identidad Self-Sovereign básica (DIDs, VCs).
- Builds dedicados de apps móviles para clientes que lo justifiquen.

### 4.7.3 Definition of Done

- [ ] Al menos un Platform Space lanzado por un cliente real, operando con tres o más tenants miembros.
- [ ] Carrito multi-vendor funcionando con descomposición correcta de pedidos a sub-pedidos por vendedor.
- [ ] Apps móviles publicadas en App Store y Play Store sin rechazo.

## 4.8 Fase 5+ — Casos especializados y expansión

**Sin fecha de cierre, ciclo continuo.**

- Anclaje blockchain para auditoría y compliance.
- Casos verticales blockchain: salud, trazabilidad, royalties, KYB.
- Expansión a más países (uno nuevo cada 6 meses).
- Programa de partners de implementación.
- Profundización de IoT (visión por computador, edge agents).
- WMS avanzado para clientes industriales.

---

# PARTE V — Día 1 al Día 90

> **Esta sección es operativa. Es lo que se hace literalmente, día a día, las primeras 12-13 semanas. Es el zoom-in de Fase 0.**

## 5.1 Semana 1 (Día 1-7) — Establecer la base de trabajo

### Día 1 (lunes)
- Lectura del Master Plan completo y de este documento (este día sin código). Debe terminar con apuntes de dudas concretas.
- Revisión del estado actual del repositorio: qué compila, qué tests pasan, qué deuda hay.
- Reunión de kickoff (si hay equipo): alineación de la PARTE I de este documento.

### Día 2-3
- Setup local de cada miembro del equipo con PostgreSQL (no SQLite).
- Migración de datos de desarrollo de SQLite a Postgres (script reproducible).
- Verificación de que todos los tests existentes corren contra Postgres.
- Captura de los tests que rompen al cambiar DB; arreglarlos.

### Día 4-5
- Setup de CI con GitHub Actions: lint + type-check + tests sobre Postgres.
- Configuración de pre-commit hooks (black, flake8, isort, eslint).
- Sentry integrado para captura de errores.

### Día 6-7
- Documentación del setup (README actualizado, `make` o `just` para comandos comunes).
- Primera retro: ¿qué bloqueó? ¿qué hay que aprender?

## 5.2 Semana 2-3 — Pago de deuda técnica crítica

- Refactor TanStack Query en todas las páginas que hacen fetch manual.
- División de ModalPago.tsx en subcomponentes < 200 líneas cada uno.
- Eliminación de los `any` restantes (≤ 12 ocurrencias documentadas).
- Tests de aislamiento multi-tenant para los módulos ya construidos.
- BaseModelViewSet implementado y aplicado a todos los viewsets existentes.

**Definition of Done de la quincena:** Todas las casillas de la sección 2.4 del Master Plan que digan "Alta prioridad" están marcadas como hechas o convertidas en Compromisos Técnicos Fechados.

## 5.3 Semana 4-6 — Setup de Celery, Redis, MinIO

- Celery + Redis funcionando con al menos una tarea async real (envío de email).
- MinIO o S3-compatible para storage de archivos.
- Migración de adjuntos existentes (si los hay) al nuevo storage.
- Tests de integración con cola de tareas.

## 5.4 Semana 7-9 — Event store y primer dominio

- Selección y deploy de Redpanda (recomendado) o Kafka.
- Diseño del Event Envelope estándar.
- Catálogo inicial de eventos para el dominio `ventas`: `VentaCreada`, `VentaConfirmada`, `VentaFacturada`, `VentaAnulada`, `PagoRecibido`.
- Implementación de emisión de eventos en `ventas` (sin tocar el comportamiento existente).
- Implementación de consumer que actualiza una proyección paralela (verifica que da los mismos resultados que la lógica actual).
- Documentación del catálogo de eventos.

## 5.5 Semana 10-11 — MCP Runtime v0

- Framework para exponer un módulo Django como servidor MCP.
- Convención de operaciones (no CRUD genérico, operaciones de negocio).
- Implementación para `ventas` y `finanzas`.
- Capability tokens y autorización por capacidad.
- Observabilidad: cada llamada MCP se loguea.
- Cliente MCP de prueba que invoca capacidades.

## 5.6 Semana 12-13 — Primer agente y eval suite

- Selección final de stack agéntico (Anthropic SDK + orquestación delgada propia).
- Implementación del agente clasificador de gastos.
- Eval suite: 50+ casos dorados de clasificación de gastos, runner automatizado.
- Agente en shadow mode (predice, no ejecuta).
- Dashboard interno de métricas del agente.
- Documentación del patrón para construir más agentes.

**Definition of Done del Día 90:**

- [ ] Postgres en todos lados, SQLite no existe en el repo.
- [ ] CI verde y obligatorio.
- [ ] Cobertura de tests del backend ≥ 30%.
- [ ] Event store en producción con `ventas` emitiendo eventos.
- [ ] MCP runtime funcional con `ventas` y `finanzas`.
- [ ] Primer agente en shadow mode, con eval suite y métricas.
- [ ] Toda la deuda técnica de "alta prioridad" del Master Plan está saldada o tiene Compromiso Fechado.
- [ ] Documentación: este plan, el Master Plan, y un nuevo documento "Architectural Decision Records" están al día.

---

# PARTE VI — Instrucciones para Agentes de IA

> **Esta sección está dirigida específicamente a agentes de IA (Claude, GPT, otros) que ejecutan tareas de código en este proyecto. También aplica a humanos que trabajan con asistencia de IA.**

## 6.1 Antes de escribir código en una tarea

Cualquier agente debe, sin excepción, hacer esta secuencia antes de tocar código:

1. **Leer la tarea entera** (issue, ticket, instrucción) y reformularla en sus propias palabras al inicio del trabajo. Si esa reformulación no coincide con lo que pidió el solicitante, hacer una pregunta de clarificación antes de avanzar.
2. **Ubicar la tarea en este plan**: ¿qué fase, qué workstream, qué Definition of Done estoy contribuyendo? Si la tarea no encaja en ninguna fase activa, pedir aclaración.
3. **Verificar las reglas que aplican**: ¿qué reglas R-CODE, R-PROC, R-PROD podrían afectar este trabajo? Listarlas explícitamente.
4. **Revisar el Apéndice A — Decisiones Inmutables** y ver si alguna aplica.
5. **Buscar prior art en el código**: ¿ya existe algo parecido? ¿hay convención establecida?
6. **Solo entonces, escribir código.**

Si el agente no hace esta secuencia, el revisor humano debe rechazar el PR pidiendo que la haga.

## 6.2 Mientras escribe código

- **Escribir tests primero o en paralelo, no después.** Si la tarea no incluye tests, el PR no se merge.
- **Commits atómicos**: un commit es una idea. Si tienes que escribir "y" en el mensaje, son dos commits.
- **Mensajes de commit en español, descriptivos, en imperativo**: "agrega validación de RIF en CRM" (no "agregando" ni "agregué").
- **Nunca asumir contexto que no está en el código o documentación**: si no sabes algo del dominio, pregunta o búscalo en el Master Plan; no inventes.
- **Cuando hagas refactor, no agregues features**. Cuando agregues feature, no refactorices más allá de lo necesario. Mezclar las dos cosas es la receta del PR irrevisable.

## 6.3 Antes de proponer un PR

Auto-checklist obligatorio que debe estar en la descripción del PR:

```
## Auto-checklist

### Lo que cambia
- [Descripción de 2-4 líneas]

### Conexión con el plan
- Fase: [0/1/2/3/4/5+]
- Workstream: [WS-1/WS-2/...]
- Definition of Done que este PR contribuye: [item específico]

### Reglas verificadas
- [ ] R-CODE-1 (multi-tenant): [N/A o cómo se cumple]
- [ ] R-CODE-2 (no SQLite): [N/A o cómo se cumple]
- [ ] R-CODE-3 (sin any/print): [confirmado]
- [ ] R-CODE-4 (Decimal para dinero): [N/A o confirmado]
- [ ] R-CODE-5 (UUIDv7): [N/A o confirmado]
- [ ] R-CODE-6 (soft delete): [N/A o confirmado]
- [ ] R-CODE-7 (API-first): [N/A o confirmado]
- [ ] R-CODE-8 (sin secretos): [confirmado]
- [ ] R-CODE-9 (tests integración): [tests añadidos/actualizados]
- [ ] R-CODE-10 (no null=True en obligatorios): [N/A o confirmado]

### Eventos emitidos / consumidos (si aplica)
- [Listar eventos nuevos o modificados]

### MCP / capacidades expuestas (si aplica)
- [Listar capacidades nuevas]

### Decisiones tomadas
- [Decisiones que requirieron juicio, con razón breve]

### Compromisos técnicos fechados creados
- [Si alguno, link al issue con vence_en y dueño]

### Riesgos
- [Qué puede romper esto, qué watch-outs hay para el reviewer]
```

PRs sin este auto-checklist se rechazan de oficio.

## 6.4 Patrones que debe seguir un agente

### 6.4.1 Estructura de un nuevo modelo Django

```python
# apps/<modulo>/models.py

import uuid
from django.db import models
from apps.core.models import BaseModel  # ya implementado en Fase 0

class NuevoModelo(BaseModel):
    """
    Descripción breve del propósito del modelo.

    Eventos que emite:
    - <modulo>.nuevo_modelo.creado
    - <modulo>.nuevo_modelo.modificado
    - <modulo>.nuevo_modelo.anulado
    """
    id_nuevo_modelo = models.UUIDField(
        primary_key=True,
        default=uuid_v7,  # función helper en core.utils
        editable=False,
    )
    # id_empresa, fecha_creacion, fecha_modificacion, activo vienen de BaseModel

    nombre = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=18, decimal_places=4)
    estado = models.CharField(
        max_length=30,
        choices=ESTADO_CHOICES,
        default='PENDIENTE',
    )

    class Meta:
        unique_together = [['id_empresa', 'codigo_unico_por_empresa']]
        indexes = [
            models.Index(fields=['id_empresa', 'estado']),
            models.Index(fields=['id_empresa', 'fecha_creacion']),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.id_empresa})"
```

### 6.4.2 Estructura de un viewset

```python
# apps/<modulo>/views.py

from apps.core.viewsets import BaseModelViewSet
from .models import NuevoModelo
from .serializers import NuevoModeloSerializer
from .filters import NuevoModeloFilter
from .events import emitir_evento_creado

class NuevoModeloViewSet(BaseModelViewSet):
    serializer_class = NuevoModeloSerializer
    filterset_class = NuevoModeloFilter
    search_fields = ['nombre']
    ordering_fields = ['fecha_creacion', 'monto']
    ordering = ['-fecha_creacion']

    def perform_create(self, serializer):
        instance = serializer.save(
            id_empresa=self.request.user.empresa,
            id_usuario_creacion=self.request.user,
        )
        emitir_evento_creado(instance, usuario=self.request.user)
```

### 6.4.3 Estructura de un servidor MCP de un módulo

```python
# apps/<modulo>/mcp.py

from apps.mcp_runtime import register_capability
from .services import crear_nuevo_modelo, consultar_nuevo_modelo

@register_capability(
    name='crear_nuevo_modelo',
    description='Crea un nuevo registro del tipo X en la empresa actual.',
    requires_capabilities=['nuevo_modelo.crear'],
)
def mcp_crear(empresa_id, nombre, monto):
    return crear_nuevo_modelo(empresa_id=empresa_id, nombre=nombre, monto=monto)

@register_capability(
    name='consultar_nuevo_modelo',
    description='Devuelve los registros activos del tipo X en la empresa.',
    requires_capabilities=['nuevo_modelo.leer'],
)
def mcp_consultar(empresa_id, filtros=None):
    return consultar_nuevo_modelo(empresa_id=empresa_id, filtros=filtros or {})
```

### 6.4.4 Estructura de tests

```python
# apps/<modulo>/tests/test_isolation.py

class TestNuevoModeloAislamiento(TestCase):
    """
    Test obligatorio: empresa A nunca ve datos de empresa B.
    """
    def setUp(self):
        self.empresa_a = EmpresaFactory.create()
        self.empresa_b = EmpresaFactory.create()
        self.user_a = UsuarioFactory.create(empresa=self.empresa_a)
        self.objeto_a = NuevoModeloFactory.create(id_empresa=self.empresa_a)
        self.objeto_b = NuevoModeloFactory.create(id_empresa=self.empresa_b)

    def test_listado_solo_empresa_propia(self):
        self.client.force_authenticate(user=self.user_a)
        r = self.client.get('/api/v1/<modulo>/nuevo-modelo/')
        ids = [x['id_nuevo_modelo'] for x in r.data['results']]
        self.assertIn(str(self.objeto_a.id_nuevo_modelo), ids)
        self.assertNotIn(str(self.objeto_b.id_nuevo_modelo), ids)

    def test_detalle_otra_empresa_da_404(self):
        self.client.force_authenticate(user=self.user_a)
        r = self.client.get(f'/api/v1/<modulo>/nuevo-modelo/{self.objeto_b.id_nuevo_modelo}/')
        self.assertEqual(r.status_code, 404)
```

## 6.5 Cosas que un agente NO debe hacer jamás

- **No introducir librerías nuevas sin justificación documentada.** Cualquier dependencia nueva requiere mención en el PR de por qué, qué alternativa se descartó, y un compromiso de mantenimiento.
- **No reescribir código existente sin necesidad explícita.** Refactor por refactor degrada confianza. Refactor solo cuando hay bug, deuda en sección 2.4 o solicitud explícita.
- **No exponer datos en logs.** Ni tokens, ni contraseñas, ni datos de tarjeta, ni emails completos en errores. Si hay duda, omite.
- **No hacer "limpieza" de código que toca módulos no relacionados con la tarea.** Si encuentras algo que se debe arreglar, abre un issue separado, no lo metas en el PR actual.
- **No marcar `if/else` con `# TODO` y dejarlo así.** Si hay un TODO, hay un issue; si hay issue, hay dueño y fecha.
- **No crear "utility" / "helpers" / "common" como cajón de sastre.** Cada utilidad pertenece a un dominio; si no, probablemente no debería existir.
- **No generar código boilerplate enorme con la justificación "lo necesitábamos".** Mejor menos código, más enfocado.

## 6.6 Cómo presentar resultados al humano que revisa

Cuando el agente entrega un PR o resultado:

1. **Resumen ejecutivo de 3-5 líneas** sobre qué cambió y por qué.
2. **Decisiones tomadas que requirieron juicio**, listadas explícitamente.
3. **Lo que NO hizo** y por qué (si descartaste rutas, dilo).
4. **Lo que recomienda hacer después**, si algo quedó pendiente.
5. **El auto-checklist de la sección 6.3.**

Un PR bien presentado se mergea más rápido que uno que oculta su lógica interna.

---

# PARTE VII — Sistema de Checkpoints

> **Lo que evita la deriva no es escribir un buen plan; es revisarlo a intervalos fijos contra la realidad.**

## 7.1 Ritmo de checkpoints

| Cadencia | Quién participa | Duración | Output |
|----------|-----------------|----------|--------|
| Diario | Quien ejecuta | 5 min escritos | Anotación breve en log de proyecto |
| Semanal (lunes) | Equipo de ejecución | 30 min | Las 3 preguntas del 1.5 + plan de la semana |
| Quincenal (viernes #2) | Equipo + responsable | 60 min | Estado de Compromisos Técnicos Fechados, deuda nueva, métricas |
| Mensual | Equipo + stakeholders | 90 min | Revisión de fase actual contra Definition of Done |
| Cierre de fase | Todos | 1 día | Auditoría completa, decisión de pasar o no a la siguiente fase |
| Trimestral | Quien lleva el proyecto | 4 horas | Re-lectura completa de este documento, propuestas de cambio |

## 7.2 Daily — formato

Una nota escrita de 3 líneas, no más:

```
[Fecha]
- Lo que terminé hoy: [cosa concreta]
- Lo que voy a hacer mañana: [cosa concreta]
- Lo que me bloquea o me preocupa: [si algo]
```

Si por tres días seguidos lo que te bloquea es lo mismo, escala. Si por cinco días no completas nada concreto, escala.

## 7.3 Semanal (lunes) — formato

Las tres preguntas de 1.5, contestadas por escrito, antes de empezar el trabajo del lunes. Tiempo: 5 minutos. Si toman más, está mal pensado el plan.

## 7.4 Quincenal (viernes alternos) — formato

Reunión de 60 minutos con agenda fija:

1. **Estado de Compromisos Técnicos Fechados** (15 min): cuáles están al día, cuáles vencidos, cuáles vencen esta quincena.
2. **Métricas del producto** (15 min): cobertura de tests, latencia p95, errores en producción, uso de los agentes (% sugerencias aceptadas), clientes activos.
3. **Reflexión sobre visión** (15 min): ¿algo de lo que construimos esta quincena se desvió? ¿hay tentación de violar las cinco propiedades irrenunciables?
4. **Plan de la próxima quincena** (15 min).

Output escrito, archivado, accesible al equipo.

## 7.5 Mensual — formato

90 minutos con stakeholders (incluido el tomador de decisión final del proyecto):

1. Estado contra Definition of Done de la fase actual.
2. Riesgos materializados y nuevos riesgos.
3. Cambios en el contexto externo (clientes, regulación, mercado).
4. Decisión: ¿la fase actual sigue siendo la correcta?

## 7.6 Cierre de fase — formato

Día completo de auditoría. Estructura:

**Mañana — Auditoría técnica.**
- ¿Toda la deuda fue saldada o tiene Compromiso Fechado?
- ¿La cobertura de tests cumple el target?
- ¿Los flujos críticos pasan end-to-end?
- ¿Hay deuda no documentada?

**Tarde — Auditoría de visión.**
- ¿Lo construido cumple las cinco propiedades irrenunciables?
- ¿Lo construido respeta los cinco principios arquitectónicos?
- ¿La fase siguiente sigue siendo la adecuada o algo aprendido cambia el plan?

**Decisión final del día.** "Cerramos fase, abrimos siguiente" o "no cerramos, identificamos qué falta y lo cerramos en X semanas". Documentada y comunicada.

## 7.7 Trimestral — formato

Esta es la más importante para evitar deriva a largo plazo.

Quien lleva el proyecto se aparta 4 horas (idealmente fuera de la oficina o en un día sin interrupciones), lee de corrido:

1. Este documento entero.
2. El Master Plan original.
3. Las anotaciones de los daily, weekly, biweekly del trimestre.
4. Los issues con etiqueta `tech-debt`.
5. El feedback de clientes (si ya hay).

Y produce un memo escrito de 2-4 páginas:

- ¿Estamos construyendo lo que dice la frase 1.1?
- ¿Las cinco propiedades irrenunciables siguen siendo correctas? ¿Alguna debería revisarse?
- ¿Las cinco fases siguen siendo correctas en orden y contenido?
- ¿Hay tentaciones que están ganando terreno (leer la PARTE VIII)?
- ¿Qué cambia en este documento como resultado de este memo?

Si el memo concluye que algo cambia, el cambio se aplica explícitamente, se versiona, y se comunica. Si concluye que nada cambia, se firma y archiva la fecha.

## 7.8 Métricas mínimas que se miden siempre

Sin estas, los checkpoints son opinión. Con ellas, son auditoría.

**Métricas técnicas:**
- Cobertura de tests (backend %, frontend %).
- Tiempo de build CI (target < 10 min).
- Tiempo de deploy a staging (target < 5 min).
- Errores en producción (count por semana, por severidad).
- Latencia p95 de API (target < 500ms en Fase 2+).
- Tamaño de la deuda técnica abierta (count de Compromisos Fechados).

**Métricas de producto:**
- Clientes activos.
- Clientes pagando.
- Uso semanal del agente conversacional (count de interacciones).
- % de sugerencias del agente aceptadas por humanos.
- Tiempo medio de onboarding de un cliente nuevo.
- NPS / satisfacción del cliente (cuando aplique).

**Métricas de visión:**
- # de personalizaciones declarativas activas (Capa 1-4).
- # de Platform Spaces activos (cuando aplique).
- # de paquetes en marketplace (cuando aplique).
- # de agentes en producción.
- # de adaptadores MCP integrados.

---

# PARTE VIII — Anti-Patrones

> **Patrones específicos que han fallado en proyectos similares y que aquí no entran.**

## 8.1 Anti-patrón "AI bolted on"

**Síntoma:** "Vamos a hacer la lógica como siempre y le ponemos un chat encima al final."
**Por qué falla:** El chat termina siendo CRUD parlante; los agentes no pueden razonar sobre el dominio porque el dominio no expone capacidades semánticas; la "IA" es confettis.
**Antídoto:** MCP en cada módulo desde el primer módulo. El chat consume capacidades MCP, no llama APIs REST inventadas en el momento.

## 8.2 Anti-patrón "Backlog infinito de módulos"

**Síntoma:** Listas de 60+ módulos a construir, todos a medias.
**Por qué falla:** Mantener 60 módulos a medias es peor que mantener 15 completos. La complejidad es n^2.
**Antídoto:** Catálogo cerrado de ~25 módulos core. Todo lo demás es vertical pack en marketplace o personalización del cliente. Resistir la tentación de "agregar uno más".

## 8.3 Anti-patrón "Venezuela en el código"

**Síntoma:** Constantes hard-coded de IVA al 16%, RIF como tipo de identificador en columnas llamadas `rif`, asunción de que la moneda base es VES.
**Por qué falla:** Cuando llegas a México, cada uno de esos lugares es un bug de localización que tarda meses descubrir.
**Antídoto:** `id_paquete_localizacion` en empresa. Todas las constantes fiscales vienen del paquete activo. Columnas se llaman `identificador_fiscal`, no `rif`. Moneda base es campo de empresa, no asunción.

## 8.4 Anti-patrón "Big bang refactor"

**Síntoma:** "Vamos a tomar dos meses y reescribir todo lo de Fase 0."
**Por qué falla:** Big bang refactors históricamente fracasan. La operación no para esos dos meses, las prioridades cambian, lo nuevo nunca está listo, y al final hay dos sistemas a medio.
**Antídoto:** Strangler fig. Las primitivas nuevas (event store, MCP) entran en paralelo. Los módulos viejos siguen funcionando. La migración es módulo por módulo, con rollback siempre disponible.

## 8.5 Anti-patrón "Determinismo opcional"

**Síntoma:** "El LLM ya generó el asiento contable, vamos a usarlo, total el contador revisa."
**Por qué falla:** Errores sutiles del LLM en contabilidad terminan en problemas fiscales. La promesa de "el contador revisa" se diluye con el volumen.
**Antídoto:** El LLM nunca emite asiento contable. Propone, código determinista valida y emite, el humano confirma. La regla 1.3.4 es absoluta.

## 8.6 Anti-patrón "Personalización como código"

**Síntoma:** "El cliente quiere que cuando pase X, haga Y. Hacemos un script Python que se ejecute en su instancia."
**Por qué falla:** Cada cliente acumula scripts. Imposible actualizar el ERP base. Imposible auditar. Imposible revertir.
**Antídoto:** El usuario quiere personalizar — el agente la traduce al DSL declarativo, se valida, se aplica como artefacto versionado. Si no cabe en el DSL, escala al equipo del ERP para extender el DSL, no para escribir código suelto.

## 8.7 Anti-patrón "Plataforma sin operación"

**Síntoma:** Construir Platform Spaces antes de que la base operativa del ERP funcione bien.
**Por qué falla:** El operador del Platform Space necesita tener su propio negocio funcionando bien con el ERP antes de operar el de otros. La fase 4 depende de la fase 1.
**Antídoto:** No empezar Platform Spaces hasta que Fase 1, 2, 3 estén cerradas. Resistir el "y si lanzamos también...".

## 8.8 Anti-patrón "Blockchain decorativo"

**Síntoma:** "Pongamos blockchain en X porque marketing." donde X no pasa los tres filtros (desconfianza, verificación independiente, inmutabilidad pública).
**Por qué falla:** Costo, complejidad regulatoria, inutilidad real.
**Antídoto:** Tres filtros explícitos antes de cualquier integración blockchain. Si no pasa los tres, no entra.

## 8.9 Anti-patrón "Documento que nadie relee"

**Síntoma:** Un Master Plan de 100+ páginas escrito una vez, nunca actualizado, ignorado al tomar decisiones.
**Por qué falla:** Lo escribimos, lo leemos al inicio, y olvidamos. Las decisiones se toman en pasillos.
**Antídoto:** PARTE I de este documento corta y obligatoria de relectura semanal. Trimestral entero. Los compromisos fechados son issues activos, no notas en un PDF.

## 8.10 Anti-patrón "Cliente futuro hipotético"

**Síntoma:** "Esto lo construimos así porque los clientes enterprise lo van a necesitar."
**Por qué falla:** Cliente enterprise no existe; el mes que viene cambias de teoría sobre qué necesitan; mientras, el cliente real (la PYME venezolana) sufre la complejidad innecesaria.
**Antídoto:** Solo construir para el cliente más cercano en el tiempo. La arquitectura prepara el camino para escalar después, pero las features se construyen para el cliente que está hoy.

---

# PARTE IX — Glosario

Términos que se usan en este documento y en el proyecto. Cuando hay duda sobre qué significa algo, consultar aquí.

| Término | Significado |
|---------|-------------|
| AI-nativo | Sistema donde la IA es ciudadana de primera clase desde el día 1, no añadidura tardía. |
| Agente operativo | Agente de IA que ejecuta una tarea específica del negocio (cobranza, conciliación, etc.). |
| Agente de personalización | Agente de IA que traduce solicitudes en lenguaje natural del usuario a personalizaciones declarativas del ERP. |
| Bounded context | Concepto de DDD: un dominio del negocio con sus propios modelos y lenguaje (ventas, compras, finanzas, etc.). |
| Capability token | Token de autorización que da a un agente permisos específicos por sesión. |
| Compromiso Técnico Fechado | Excepción documentada a una regla, con dueño y fecha de vencimiento. |
| Definition of Done | Lista explícita de criterios que debe cumplir un trabajo para considerarse terminado. |
| DSL de personalización | Lenguaje declarativo (YAML/JSON) que expresa modificaciones a una instancia del ERP. |
| Event sourcing | Patrón donde la verdad del sistema son los eventos inmutables; el estado actual es una proyección. |
| Event store | Sistema donde se almacenan los eventos (Kafka, Redpanda, etc.). |
| MCP (Model Context Protocol) | Protocolo abierto para que modelos de IA descubran y usen capacidades de herramientas externas. |
| Meta-agente | Agente cuya función es analizar el desempeño de otros agentes y proponer mejoras. |
| Modo "ejecutar con reversa" | Nivel de autonomía de un agente: ejecuta acciones pero todas son fácilmente reversibles. |
| Modo "sugerir" | Nivel de autonomía de un agente: propone acciones pero no las ejecuta sin aprobación humana. |
| Paquete de localización | Módulo opt-in que aporta toda la regulación, fiscalidad, formatos y conectores de un país. |
| Platform Space | Entidad que permite a un cliente del ERP operar una plataforma con otros tenants federados. |
| Proyección | Vista materializada del estado actual derivada de los eventos. |
| Sandbox espejo | Entorno de prueba por tenant con datos sintéticos derivados de los reales. |
| Shadow mode | Agente que predice acciones pero no las ejecuta, para validar comportamiento antes de promover. |
| SSI (Self-Sovereign Identity) | Identidad digital donde el usuario controla sus credenciales sin depender de un emisor central permanente. |
| Strangler fig | Patrón de migración donde se construye lo nuevo en paralelo y se reemplaza gradualmente lo viejo. |
| Tenant | Empresa cliente del ERP, con sus datos aislados de otras. |
| VC (Verifiable Credential) | Credencial digital firmada criptográficamente, verificable independientemente del emisor. |

---

# APÉNDICE A — Decisiones Inmutables

> **Decisiones que ya se tomaron y que cambiar implica un costo enorme. No se cambian sin un trimestral que las cuestione formalmente.**

| # | Decisión | Razón | Cuándo se tomó |
|---|----------|-------|----------------|
| A-001 | Stack base: Django + DRF + React + TypeScript + MUI | Heredado del Master Plan; ecosistema maduro, tipos estrictos, componentes empresariales listos. | Heredada |
| A-002 | UUIDv7 como PK en todos los modelos | Seguridad (no enumerable) + ordenable temporalmente para localidad de índice. | Día 1 del pivot |
| A-003 | PostgreSQL en todos los entornos, sin SQLite | Diferencias en constraints parciales y comportamiento transaccional ya causaron bugs. | Día 1 del pivot |
| A-004 | Multi-tenant Row-Level con `id_empresa` | Simple, funciona hasta ~1000 tenants, migrable a schema-per-tenant después. | Heredada |
| A-005 | Soft delete por defecto | Auditoría, recuperación, integridad referencial. | Heredada |
| A-006 | JWT con refresh tokens y blacklist | Stateless, compatible con mobile, estándar. | Heredada |
| A-007 | Decimal para dinero, Float prohibido | Errores de redondeo en moneda son inaceptables. | Heredada |
| A-008 | i18next desde el día 1 en frontend | Agregar i18n después es 10x más caro que escribir con i18n. | Día 1 del pivot |
| A-009 | TanStack Query para server state | Cache, refetch, loading states sin boilerplate. | Heredada |
| A-010 | Event sourcing como verdad para eventos de negocio | Auditoría perfecta, replay, agentes pueden explicar números. | Día 1 del pivot |
| A-011 | Redpanda como event store (sobre Kafka) | Mismo protocolo, operativamente más simple, sin Zookeeper. | Día 1 del pivot |
| A-012 | MCP como protocolo de capacidades de cada módulo | Estándar abierto, compatible con múltiples LLMs, futuro-proof. | Día 1 del pivot |
| A-013 | Multi-proveedor LLM (Claude default + GPT + Gemini + locales) | No casarse con un proveedor; redundancia y opciones de costo. | Día 1 del pivot |
| A-014 | DSL declarativo para personalizaciones, no código generado | Versionable, validable, reversible, auditable. | Día 1 del pivot |
| A-015 | Paquetes de localización opt-in, núcleo agnóstico | Permite escalar país por país sin reescribir core. | Día 1 del pivot |
| A-016 | Determinismo en lo regulado (impuestos, asientos, folios) | Riesgo legal y de confianza. El LLM propone, código emite. | Día 1 del pivot |
| A-017 | Frontend: MUI v7 para core admin; opción de shadcn/Radix para UIs generativas | MUI es robusto pero pesado para componentes que un agente compone al vuelo. | Día 1 del pivot |
| A-018 | Celery + Redis para tareas operacionales; Redpanda para eventos de dominio | Carriles separados; cargas y patrones distintos. | Día 1 del pivot |
| A-019 | WeasyPrint para generación de PDFs | HTML/CSS → PDF, fácil templating, control fino. | Heredada |
| A-020 | WhatsApp Business API (Meta Cloud) directo, no Twilio | Oficial, sin intermediarios, menor costo. | Heredada |

> **Cuando se proponga cambiar una decisión inmutable**, documentar en una página: alternativa, razón, costo estimado de migración, beneficio esperado. Trimestral decide.

---

# APÉNDICE B — Plantillas de Trabajo

## B.1 Compromiso Técnico Fechado (template)

```markdown
## Compromiso Técnico Fechado

**ID:** CTF-YYYYMM-NNN
**Creado:** [fecha]
**Vence:** [fecha, máx 90 días]
**Dueño:** [nombre persona]

### Regla violada
[R-CODE-X / R-PROC-X / R-PROD-X / Principio arquitectónico Y / Otra]

### Razón de la excepción
[Por qué procede esta excepción ahora; qué costo tendría no procederla]

### Plan de resolución
[Cómo se va a resolver para la fecha de vencimiento]

### Riesgo si no se resuelve
[Qué pasa si pasa de fecha sin resolver]
```

## B.2 Architectural Decision Record (ADR template)

```markdown
# ADR-NNN: [Título corto]

**Estado:** Propuesto / Aceptado / Reemplazado por ADR-MMM
**Fecha:** [fecha]
**Autor(es):** [nombres]

## Contexto
[Qué situación motiva esta decisión, qué fuerzas están en juego]

## Decisión
[Qué se decide hacer]

## Alternativas consideradas
1. [Alt 1] — descartada porque [razón]
2. [Alt 2] — descartada porque [razón]

## Consecuencias
**Positivas:**
- [...]

**Negativas:**
- [...]

**Neutrales:**
- [...]

## Cómo revisitar esta decisión
[En qué señales habría que reconsiderar]
```

## B.3 Memo trimestral (template)

```markdown
# Memo Trimestral Q[N] — Omni AI-Native

**Autor:** [nombre]
**Fecha:** [fecha]
**Período cubierto:** [fechas]

## 1. ¿Estamos construyendo lo que dice la frase 1.1?
[Análisis honesto, ejemplos concretos]

## 2. Las cinco propiedades irrenunciables — ¿siguen siendo correctas?
[Una por una; señales de que alguna debería matizarse]

## 3. Las fases — ¿siguen siendo correctas?
[Estado de la fase actual; previsión para la siguiente]

## 4. Tentaciones detectadas
[Cosas que estuvimos a punto de violar; cómo se contuvo o no]

## 5. Aprendizajes del trimestre
[Lo que sabemos hoy que no sabíamos hace 3 meses]

## 6. Cambios propuestos a este documento
[Si alguno; con razón y alcance]

## 7. Compromisos para el próximo trimestre
[Lo concreto a lograr]

---
*Firma:* [nombre]
*Fecha:* [fecha]
```

## B.4 Daily log (template)

```
[YYYY-MM-DD]
- Hecho hoy:
- Mañana:
- Bloqueos / preocupaciones:
```

## B.5 Definition of Done de feature individual (template)

```markdown
## DoD para feature [nombre]

### Funcional
- [ ] Comportamiento esperado documentado en spec
- [ ] Casos felices y casos de error implementados
- [ ] Tests de integración cubren el flujo

### Calidad
- [ ] Tests unitarios ≥ 80% del código nuevo
- [ ] Lint y type-check pasan
- [ ] Sin TODOs sin issue asociado
- [ ] Sin console.log / print de debug

### Multi-tenant
- [ ] Test de aislamiento entre empresas
- [ ] Filtro por id_empresa verificado

### Eventos / MCP (si aplica)
- [ ] Eventos emitidos documentados en catálogo
- [ ] Capacidades MCP expuestas y documentadas

### Personalización (si aplica)
- [ ] Si la feature debería ser configurable por el cliente, está expuesta vía DSL
- [ ] Si la feature está hard-coded por una buena razón, está en Apéndice A

### Localización (si aplica)
- [ ] Strings en i18n
- [ ] Si toca fiscalidad, viene del paquete de localización activo

### Observabilidad
- [ ] Logs apropiados (sin secretos)
- [ ] Métricas relevantes expuestas

### Documentación
- [ ] README del módulo actualizado si aplica
- [ ] ADR creado si la feature implicó decisión arquitectónica
```

---

# Cierre del documento

Este plan es un documento vivo, pero su PARTE I no debería cambiar nunca y su PARTE II rara vez. Si después de seis meses de uso encuentras que las reglas se contradicen con la realidad, el problema probablemente es que estás haciendo algo que no es esto. La defensa contra eso es, cada lunes, releer la frase 1.1 y preguntarse honestamente si lo que se está construyendo se conecta con ella.

Mucho éxito. Y disciplina.

---

*Documento generado y mantenido como parte del proyecto Omni AI-Native.*
*Versión inicial: este día.*
*Próxima revisión obligatoria: 90 días desde aprobación, o al cierre de Fase 0.*
