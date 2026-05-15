# ADR-003: Integration Hub Centralizado con MCP Bidireccional

**Estado:** Aceptado
**Fecha:** 2026-05-14
**Autor:** Responsable del proyecto
**Categoría:** Arquitectura de integraciones
**Relacionado con:** ADR-002 (arquitectura modular), ADR-004 (primer standalone)

---

## Contexto

La decisión ADR-002 establece que ciertos módulos de Omni se venden standalone, integrándose al ERP que el cliente ya tiene (Odoo, SAP, Profit, etc.). Esto requiere infraestructura de integración.

Hay dos formas de construir esto:

**Forma A — Integración por producto:** cada producto Omni standalone tiene su propia integración con cada ERP destino. Si tenemos 4 productos standalone × 3 ERPs destino, son 12 integraciones independientes.

**Forma B — Integration Hub centralizado:** una sola pieza de software ("el Hub") sabe hablar con cada ERP destino. Todos los productos Omni le hablan al Hub en vocabulario canónico, y el Hub traduce al ERP específico.

La Forma B es claramente superior por economía de mantenimiento, consistencia, y escalabilidad. Esta es la decisión.

Adicionalmente, el Hub debe ser bidireccional:
- **Saliente:** Omni habla a ERPs externos.
- **Entrante:** sistemas externos (especialmente agentes de IA) hablan a Omni.

La superficie entrante usa MCP (Model Context Protocol), consistente con la arquitectura AI-nativa interna de Omni (decisión inmutable A-012).

---

## Decisión

**Construir un Integration Hub centralizado con tres responsabilidades:**

1. **Saliente:** un solo conector por ERP destino (Odoo, SAP, Profit, etc.), compartido entre todos los productos Omni.
2. **Entrante:** un servidor MCP que expone capacidades de Omni a sistemas externos (agentes de IA, integraciones de terceros).
3. **Servicios transversales:** auth, sync engine, conflict resolution, cache, rate limiting, observabilidad, todos compartidos entre adaptadores.

---

## Arquitectura del Hub

```
┌────────────────────────────────────────────────────────┐
│ SISTEMAS EXTERNOS                                       │
│                                                          │
│  Agentes IA       ERPs externos       Apps custom       │
│  externos         (Odoo, SAP, etc)   (ERP-agnósticas)  │
└──────┬────────────────┬──────────────────┬─────────────┘
       │                │                  │
       │ MCP            │ APIs nativas     │ MCP / REST
       ▼                ▼                  ▼
┌────────────────────────────────────────────────────────┐
│ OMNI INTEGRATION HUB                                    │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Servidor MCP de Omni                              │  │
│  │ - Expone capacidades a agentes externos          │  │
│  │ - Capability tokens granulares                    │  │
│  │ - Audit log completo                              │  │
│  │ - Rate limiting agresivo                          │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Modelo canónico Omni                              │  │
│  │ Cliente, Producto, Pedido, Factura, etc.          │  │
│  │ Rico (no lowest-common-denominator)               │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Servicios transversales                           │  │
│  │ - Auth y credenciales por cliente                 │  │
│  │ - Sync engine (event sourcing)                    │  │
│  │ - Conflict resolution                             │  │
│  │ - Cache, rate limiting, retry                     │  │
│  │ - Observabilidad y logging                        │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Adaptadores salientes por ERP destino             │  │
│  │                                                    │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐         │  │
│  │  │ Odoo     │ │ SAP B1   │ │ Profit   │  ...    │  │
│  │  └──────────┘ └──────────┘ └──────────┘         │  │
│  └──────────────────────────────────────────────────┘  │
└────────────┬───────────────────────────────────────────┘
             │ Productos Omni hablan al Hub en
             │ vocabulario canónico
             ▼
┌────────────────────────────────────────────────────────┐
│ PRODUCTOS OMNI                                          │
│  Omni ERP   Omni Cobranza   Omni Routes   Omni Adapt  │
└────────────────────────────────────────────────────────┘
```

---

## Plan de implementación gradual

**El Hub se construye en versiones incrementales, no todo de una vez.**

### Hub v0 — MVP funcional (primera versión)

**Cuándo:** se construye junto con el primer producto standalone (Omni Cobranza, mes 5-6).

**Capacidades:**
- Modelo canónico básico: Cliente, Producto, Factura, Pago.
- Adaptador Odoo funcional, basado en el código existente de gestion-cxc-V2.
- Servicios transversales mínimos: auth, retry básico, logging.
- Sin MCP entrante todavía.
- Sin cache sofisticado.
- Sincronización: pull on-demand (cuando el producto Omni pide datos, el Hub consulta a Odoo).

**Por qué empezamos así:** el código de gestion-cxc-V2 ya tiene integración Odoo funcionando. Lo refactorizamos para que sea el adaptador del Hub, no integración custom de Cobranza. Esto reduce el costo de construcción del Hub v0 a refactor + organización, no construcción desde cero. Estimado: 2-4 semanas.

### Hub v1 — Sync engine robusto (segunda versión)

**Cuándo:** cuando aparezca demanda real de sincronización proactiva (probablemente mes 9-12).

**Capacidades nuevas:**
- Sincronización programada (cada X horas/minutos según configuración).
- Detección de cambios (qué cambió desde el último sync).
- Webhooks bidireccionales con Odoo donde sea posible.
- Cache inteligente de datos frecuentes.
- Conflict resolution básico.

**Estimado:** 4-6 semanas adicionales.

### Hub v2 — Multi-ERP (tercera versión)

**Cuándo:** cuando un cliente concreto con SAP o Profit lo necesite, no antes.

**Capacidades nuevas:**
- Adaptador SAP B1.
- Adaptador Profit (o el que se necesite).
- Mejoras a auth multi-credencial.
- UI para configurar mapeos por tenant.

**Estimado:** 6-10 semanas por cada adaptador nuevo de calidad.

### Hub v3 — MCP entrante (cuarta versión)

**Cuándo:** cuando el primer cliente quiera exponer Omni a agentes externos (probablemente Bloque 2 tardío).

**Capacidades nuevas:**
- Servidor MCP de Omni completo.
- Capability tokens granulares.
- Audit log completo de llamadas externas.
- Marketplace de agentes externos certificados (eventualmente).

**Estimado:** 8-12 semanas.

---

## Principios técnicos del Hub

### Modelo canónico rico, no minimalista

El modelo canónico Omni debe ser **expresivo**, capaz de representar conceptos complejos. Cuando un ERP destino no tenga un concepto, el adaptador correspondiente lo simula o lo deja vacío. No reducir el modelo canónico al "máximo común denominador" entre ERPs.

Ejemplo: Cliente en Omni canónico tiene campos para identificador fiscal con validación, categoría fiscal, condición de pago, condiciones especiales por cliente. Si un ERP destino no tiene "categoría fiscal", el adaptador lo deja en `null` y se documenta la limitación.

### Adaptadores son código aislado

Cada adaptador es un módulo separado, con su propia configuración, sus propios tests, su propia documentación. Cambios en el adaptador Odoo nunca rompen el adaptador SAP.

### Read-only por defecto, read-write con cuidado

La primera versión de cualquier adaptador es **read-only**: el Hub lee del ERP destino pero no escribe. Read-write se habilita módulo por módulo, con análisis explícito de conflictos.

### Sin loops infinitos

Cuando el Hub escribe a un ERP destino que tiene webhooks hacia Omni, hay que prevenir loops. Mecanismo: cada cambio escrito por el Hub se marca con un tag/header que el listener de webhooks detecta y descarta.

### Multi-tenant en el Hub mismo

El Hub también es multi-tenant. Las credenciales para conectar a Odoo del cliente A son completamente distintas e independientes de las del cliente B. Sin shared state que cruce tenants.

### Cada operación es idempotente

Si una operación se ejecuta dos veces por error (retry, duplicación), no debe causar daño. Operaciones de escritura tienen IDs únicos que permiten detectar duplicados.

---

## Decisiones sobre el modelo canónico

El modelo canónico Omni vive en un módulo Python compartido: `omni_canonical_model` (o nombre similar). Este módulo:

- No tiene dependencias con Django ni con un ORM específico.
- Define las entidades como dataclasses o Pydantic models.
- Es importable por cualquier producto Omni (ERP, Cobranza, Routes, etc.).
- Es importable por adaptadores del Hub.

**Las entidades de Django de los productos Omni se mapean al modelo canónico**, no son el modelo canónico.

Esto es importante para Capa 1 de cualquier módulo: trabaja con el modelo canónico, no con modelos Django directamente.

---

## Sobre el MCP entrante

Cuando se construya el MCP entrante (Hub v3+), los principios son:

### Seguridad first

- Sin acceso por defecto. Cada tenant decide explícitamente qué capacidades exponer a qué agentes externos.
- Capability tokens con scope mínimo. Un agente que solo necesita leer saldos no recibe permisos de escritura.
- Rotación de tokens automática (90 días por defecto).
- Audit log completo: quién hizo qué, cuándo, con qué token.
- Rate limiting agresivo por token.
- Revocación inmediata posible por el tenant.

### Compatibilidad con el ecosistema

- Implementar la especificación MCP completa, no una variante propia.
- Compatible con Claude Desktop, otros clientes MCP estándar.
- Capacidades nombradas en inglés (convención MCP), aunque internamente operen en español.

### Sandbox para agentes nuevos

- Cuando un agente nuevo se conecta, empieza en modo sandbox: solo lectura, scope reducido, alta visibilidad para el tenant.
- Promoción a producción requiere acción explícita del tenant.

---

## Consecuencias

### Positivas

- **Una sola integración por ERP destino**, reutilizable en todos los productos.
- **Curva de aprendizaje amortizada:** aprender Odoo una vez, no por producto.
- **Cambios del ERP destino afectan un solo lugar** (mantenimiento).
- **Superficie MCP entrante futuro-proof** para ecosistema de agentes IA.
- **Aprovechamiento del código existente** de gestion-cxc-V2 (su adaptador Odoo).

### Negativas

- **Complejidad inicial:** construir un Hub bien es más trabajo que integración point-to-point.
- **Tentación de over-engineering:** hay que resistir construir features del Hub sin demanda.
- **El Hub se vuelve crítico:** si el Hub falla, todos los standalone fallan.
- **El modelo canónico requiere disciplina:** cambios al modelo afectan todos los productos.

### Neutras

- El Hub vive como código separado de los productos. Tiene su propio repo o subdirectorio claro.
- Tests del Hub son complejos (involucran ERPs externos, mocks, sincronización).
- Documentación del modelo canónico se vuelve un artefacto crítico.

---

## Cómo se mide el éxito

Indicadores positivos a los 12 meses:

- Hub v0 funcional con adaptador Odoo, usado por al menos 1 producto standalone.
- Tiempo de agregar capacidad nueva al adaptador Odoo (ya existente): menos de 1 semana.
- Tiempo de onboarding de cliente Odoo nuevo: menos de 3 días.

Indicadores positivos a los 24 meses:

- Hub v1-v2 con al menos 2 adaptadores (Odoo + uno más).
- Costo de agregar adaptador nuevo: 6-10 semanas, no más.
- Al menos 1 cliente usando 2+ productos Omni standalone a través del mismo Hub.

Indicadores que sugieren revisar la arquitectura:

- Cada producto standalone termina construyendo su propia integración paralela al Hub.
- El modelo canónico requiere extensión constante (más de 1 cambio mayor por mes).
- Bugs frecuentes por desajustes entre Hub y productos.

---

## Cómo revisitar esta decisión

Esta decisión se revisita explícitamente si:

- Tras 12 meses, el Hub demuestra ser cuello de botella en lugar de facilitador.
- Aparece una tecnología nueva (estándar de integración mejor que MCP, plataforma como Apideck u otros).
- La diversidad de ERPs destino se vuelve inmanejable (más de 5 adaptadores activos sin escalar el equipo).

---

## Referencias

- ADR-002: arquitectura modular y estrategia wedge.
- ADR-004: gestion-cxc-V2 como primer standalone (el código que se reutiliza para el adaptador Odoo del Hub).
- Decisión inmutable A-012: MCP como protocolo de capacidades de cada módulo.
- Especificación MCP: https://spec.modelcontextprotocol.io

## Changelog

### v1.0 — 2026-05-14
- Versión inicial. Decisión tomada y documentada.
