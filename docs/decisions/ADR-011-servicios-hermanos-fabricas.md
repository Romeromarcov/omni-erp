# ADR-011 — Servicios hermanos: fábrica de software y fábrica de marketing/contenido

| Campo | Valor |
|---|---|
| **Estado** | Aceptado — 2026-06-12 (decisión del owner en sesión, registrada por el agente) |
| **Contexto** | El owner posee `Romeromarcov/fabrica-software`: orquestador LangGraph de 11 agentes (A0 arquitecto → A1 PM → A2 DB → A3 MCP → A4 backend → A5 frontend → A6 refactor → A7 QA → A8 SecOps → A8.5 adversarial → A9 sandbox → A10 writer → A11 DevOps → PR) con gates duros que espejan el DoD de Omni (pytest/tsc/eslint/makemigrations + **gate AST de aislamiento multi-tenant**), riesgo por rutas (no auto-declarado), auto-merge solo LOW+verde, reconciliador plan↔código y memoria de lecciones. Ya tiene a OmniERP onboardeado (`docs/ONBOARDING_OMNIERP.md` en ese repo) y un backlog de auditoría de 102 ítems sobre Omni. |

## Decisión

### Patrón general: "servicio hermano"

Toda fábrica (de software, de marketing, futuras) corre como **servicio propio** junto a Omni (Railway), **nunca dentro del proceso multi-tenant del ERP** (misma línea roja L4 de ADR-010). Omni es su **frontend** (conversación del usuario/owner desde Omni) y su **gobernador** (lo producido pasa por los pipelines de aprobación de Omni). Comunicación: API/MCP de Omni con OAuth y scopes + GitHub.

### Fábrica de software (existente)

1. **Caso A — features para el propio Omni**: la fábrica apunta a `omni-erp` y arranca en **modo sombra**: propone PRs de tier LOW; el pipeline existente (CI + branch protection + revisor independiente) los juzga — la fábrica es un productor, no un bypass. Se gradúa a MEDIUM con tasa de éxito demostrada.
2. **Caso B — apps custom de clientes**: la fábrica es el **motor del carril de creación** (ADR-010): el cliente describe su app conversando en Omni → spec → la fábrica genera desde una **plantilla "app cliente Omni"** (cliente OAuth a la API/MCP con scopes del tenant, base PWA offline-first, CSP, i18n) → deploy en repo/infra propios del cliente o gestionados por Omni. El cliente obtiene L4 real sin tocar el proceso compartido.
3. **Gaps a cerrar antes de producción** (reconocidos en sus propios planes de hardening): sanitización de tokens en logs, auth de su UI, validación de `project_id` (~1 semana); **revisor independiente de PRs** (días — reusar el patrón de agente revisor de Omni); CI de la fábrica misma; entornos efímeros para probar apps generadas (patrón PR-envs).
4. **Reusabilidad medida** (exploración 2026-06-12): ~80% del pipeline/sandbox/governance es embebible tal cual; ajustar prompts por convenciones de Omni, simplificar multi-proveedor; rehacer: efímeros, revisor independiente, observabilidad.

### Fábrica de marketing y contenido RRSS (nueva, misma plantilla)

Mismo esqueleto (grafo de agentes especializados + gates + riesgo + memoria), cambiando los gates de calidad:

1. **Pipeline tentativo**: brief/calendario → estratega (campaña, audiencias) → copywriter multi-formato (IG/X/LinkedIn/TikTok/YouTube) → generador visual (imagen/video por modelos generativos del router) → **gate de verificación de claims contra datos reales del ERP** → gate de marca (brand kit del tenant: logo, paleta, tono) → gate legal/brand-safety → cola de aprobación humana → publicación programada vía OAuth de cada plataforma → **loop de analítica** (engagement → memoria de lecciones, como LESSONS_LEARNED de la fábrica).
2. **El diferenciador es el ERP**: el contenido se ancla en datos reales del tenant vía MCP con scopes de lectura — catálogo y precios vigentes, promociones, **sobre-stock a empujar / sin stock a no promocionar**, segmentos del CRM, métricas de venta. Marketing ERP-aware, no genérico.
3. **Riesgo y aprobación**: tier LOW = borradores y formatos recurrentes pre-aprobados (auto-publicables si el tenant lo habilita); MEDIUM = ventana de veto; HIGH (campañas pagas, claims sensibles) = aprobación humana siempre. Modo sugerencia por defecto, igual que los agentes L2.
4. **Multi-tenant**: brand kit por empresa, cuentas sociales conectadas por OAuth (superficie de conectores de ADR-010), presupuestos y límites de publicación por tenant, auditoría de todo lo publicado.
5. **Honestidad offline**: este servicio es mayormente online (LLM + APIs de plataformas); lo offline-able es la cola de borradores/aprobaciones.
6. **MVP propuesto** (en orden): brand kit + generador de posts de promo anclado al catálogo + cola de aprobación + export manual → luego publicación OAuth → luego loop de analítica.

## Secuencia

No desplaza la cola vigente: ola de deuda actual → fábrica de software en modo sombra sobre Omni → motor del marketplace post-L10n. La fábrica de marketing arranca como repo/servicio propio (no toca el core de Omni); su integración usa la misma superficie OAuth/MCP, por lo que puede desarrollarse en paralelo cuando el owner lo priorice.

## Consecuencias

- Un solo patrón de integración (OAuth/MCP + scopes + gobernanza Omni) sirve a todas las fábricas presentes y futuras.
- El router de modelos por agente de la fábrica y el gateway por-tenant de Omni (ADR-010 §5) convergen en una sola filosofía de configuración de modelos.
