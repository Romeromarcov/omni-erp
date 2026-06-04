# Skills de Omni ERP — Índice

Las **skills** son guías operativas que un agente (Claude Code, Cursor, Codex…) carga
cuando una tarea coincide con su `description`. Codifican las reglas inviolables y los
patrones del proyecto para que cada cambio salga correcto a la primera, sin reaprender el
contexto. Antes de tocar código, revisá la(s) skill(s) relevante(s).

> Cada skill vive en `docs/skills/<nombre>/SKILL.md` con frontmatter `name` + `description`.
> El `description` es lo que decide si la skill aplica a tu tarea: leelo para saber cuándo cargarla.

## Cómo se relacionan con el resto

- Reglas inviolables (R-CODE / R-PROC / R-PROD): [`../PLAN_MAESTRO_UNICO.md` §2](../PLAN_MAESTRO_UNICO.md#2--reglas-inviolables-del-proyecto)
- Gate de cierre obligatorio: [`../DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md)
- Decisiones arquitectónicas: [`../decisions/`](../decisions/)

---

## Backend — núcleo y modelado

| Skill | Cuándo cargarla |
|---|---|
| [omni-django-module](omni-django-module/SKILL.md) | Crear/modificar un módulo Django: modelos, viewsets, serializers, filters. Estructura estándar y convenciones. |
| [omni-multi-tenant-isolation](omni-multi-tenant-isolation/SKILL.md) | Cualquier acceso a datos. Filtrar por `id_empresa`, tests de aislamiento (R-CODE-1). |
| [omni-decimal-money](omni-decimal-money/SKILL.md) | Cualquier valor monetario: Decimal siempre, nunca float; precisión y redondeo (R-CODE-4). |
| [omni-asientos-contables](omni-asientos-contables/SKILL.md) | Documentos con impacto contable: asiento automático y atómico (R-CODE-11). |

## Backend — primitivas AI-nativas

| Skill | Cuándo cargarla |
|---|---|
| [omni-eventos-dominio](omni-eventos-dominio/SKILL.md) | Emitir/consumir eventos de dominio (`build_event`/`publish`); nunca rompen la transacción. |
| [omni-mcp-capacidades](omni-mcp-capacidades/SKILL.md) | Exponer una capacidad como tool MCP: scopes, CapabilityToken, verificación de tenant (R-CODE-7). |
| [omni-agentes-autonomia](omni-agentes-autonomia/SKILL.md) | Crear/evaluar agentes: niveles SOMBRA/SUGERENCIA/AUTONOMO, eval suite (R-PROD-4/5). |
| [omni-integration-hub](omni-integration-hub/SKILL.md) | Conectar con sistemas externos: ningún HTTP directo desde negocio (ADR-003). |

## Localización y mercado venezolano

| Skill | Cuándo cargarla |
|---|---|
| [omni-localizacion-l10n](omni-localizacion-l10n/SKILL.md) | Lógica específica de país: puertos, registro, núcleo agnóstico (ADR-007). Regla activa. |
| [omni-venezuela-fiscal](omni-venezuela-fiscal/SKILL.md) | Fiscalidad VE (Capa A): IVA, IGTF, retenciones, RIF, libros SENIAT, correlativos. |
| [omni-multimoneda-tasas](omni-multimoneda-tasas/SKILL.md) | Multimoneda y tasas (Capa B): doble tasa BCV/real, snapshot, pagos mixtos. |
| [omni-migracion-datos](omni-migracion-datos/SKILL.md) | Importar datos reales (clientes, productos, inventario, saldos CxC) — TRACK-1F / sub-fase 1.F. |

## Proceso y entrega

| Skill | Cuándo cargarla |
|---|---|
| [omni-testing-pytest](omni-testing-pytest/SKILL.md) | Escribir/depurar tests backend: factories, aislamiento, integración, eval, cobertura. |
| [omni-definition-of-done](omni-definition-of-done/SKILL.md) | Antes de declarar "terminado" o abrir PR: el gate de cierre de 7 pasos en orden. |
| [omni-ctf-deuda](omni-ctf-deuda/SKILL.md) | Deuda o excepción inevitable: crear un Compromiso Técnico Fechado con `vence_en` y dueño (R-PROC-6). |
| [omni-pr-discipline](omni-pr-discipline/SKILL.md) | Preparar/entregar un PR: plantilla, auto-checklist, draft (nunca ready). |

## Frontend (mantenidas aparte)

> Estas skills cubren la capa de presentación y se mantienen por separado del flujo backend.

| Skill | Cuándo cargarla |
|---|---|
| [omni-frontend-page](omni-frontend-page/SKILL.md) | Crear/reestructurar una página o ruta del frontend. |
| [omni-frontend-data](omni-frontend-data/SKILL.md) | Fetch/cache/mutación de datos del servidor (TanStack Query, `services/api.ts`). |
| [omni-frontend-forms](omni-frontend-forms/SKILL.md) | Formularios: react-hook-form, validación, flujo de submit. |
| [omni-design-system](omni-design-system/SKILL.md) | Capa visual: theme, tokens, componentes UI compartidos. |
| [omni-money-ui](omni-money-ui/SKILL.md) | Cálculo, formato y despliegue de dinero en el frontend. |
| [omni-frontend-i18n-l10n](omni-frontend-i18n-l10n/SKILL.md) | Texto visible, idioma (react-i18next) y features por localización activa. |
| [omni-ai-native-ux](omni-ai-native-ux/SKILL.md) | UX AI-nativa: asistente conversacional, sugerencias de agentes, reversibilidad. |
| [omni-frontend-responsive](omni-frontend-responsive/SKILL.md) | Multiplataforma: móvil/tablet/desktop, shell responsive, ergonomía táctil, PWA, módulo escáner. |
| [omni-frontend-reskin](omni-frontend-reskin/SKILL.md) | Migrar una página legacy (estilos inline, tablas HTML) al diseño actual (rama `frontend-forms-reskin`). |

---

## Crear o modificar skills

- Usá el skill `skill-creator` de Anthropic para crear/optimizar skills y medir su `description`.
- Mantené el formato: frontmatter (`name`, `description`), secciones "Cuándo usar", patrones,
  anti-patrones, checklist final, referencias, changelog.
- Una skill = un dominio acotado. Si crece demasiado, dividila y enlazá.
