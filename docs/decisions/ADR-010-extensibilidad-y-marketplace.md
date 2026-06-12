# ADR-010 — Arquitectura de extensibilidad: escalera de customización y marketplace

| Campo | Valor |
|---|---|
| **Estado** | Aceptado — 2026-06-12 (decisión del owner en sesión, registrada por el agente) |
| **Contexto** | Principio fundacional: ERP IA-native, customizable al máximo por el usuario vía agentes conversacionales. Dos modos de despliegue: SaaS multi-tenant y entorno dedicado del cliente (servidor de Omni o del cliente, con licencias y conectado a la API de Omni). |

## Decisión

### 1. La escalera de customización (niveles)

| Nivel | Qué es | Base ya existente |
|---|---|---|
| **L0 — Configuración** | Flags de módulos, parámetros, overrides por caja/sucursal, plantillas | `appProfile`/`isModuleEnabled`, `ParametroSistema`, patrón overrides (PR #103) |
| **L1 — Declarativo** | Campos personalizados, fórmulas sandboxed, reglas, reportes/documentos | `documento_json`, DSL de fórmulas (nómina) |
| **L2 — Automatización/agentes** | Agentes custom por tenant, tools MCP por empresa, webhooks, conectores OAuth | `personalizacion_agente`, MCP server (R-CODE-7), Integration Hub |
| **L3 — Plugins (marketplace)** | Código empaquetado de terceros con manifiesto, permisos y sandbox | A construir (esta ADR) |
| **L4 — Código a medida real** | Apps/lógica propia del cliente | Solo en dedicado, vía puertos (nunca fork) |

### 2. Niveles por modo de despliegue

- **SaaS multi-tenant: L0–L3.** **Línea roja inviolable: nada de L4** — código arbitrario de un tenant jamás corre en el proceso compartido (rompería R-CODE-1 sin importar el sandbox).
- **Dedicado: L0–L4**, pero el core NO se toca: el L4 vive en un repo de extensiones del cliente conectado por los mismos puertos del plugin system (el fork mata los upgrades — lección Odoo/SAP). Licencia validada contra la API de Omni. Un plugin nacido en dedicado puede publicarse al marketplace SaaS (revisión mediante).

### 3. Dos carriles sobre una sola plataforma

- **Carril de creación** ("request al admin"): el usuario co-diseña con el agente conversacional → spec → feature en entorno de preview del tenant (patrón PR-envs Railway) → aprobación → si es generalizable entra al **core detrás de flag** (gobernado por el pipeline PR+CI+revisor existente); si es nicho se empaqueta como **plugin privado** del tenant.
- **Carril de distribución** (marketplace): plugins de Omni gratis, de terceros con revenue share, curaduría obligatoria (revisión de seguridad por agentes + humana), firma de paquetes, versionado semver, **kill-switch remoto por plugin**, activación/desactivación self-service.

### 4. Mecánica de plugins

1. **Manifiesto**: nombre, versión, firma, **permisos = scopes ya existentes** (`finanzas:read`, …), superficie aportada (páginas UI, tools MCP, webhooks, jobs), **declaración de comportamiento offline** (degradación).
2. **Sandbox real**: el backend de un plugin nunca corre en el proceso — corre como (a) configuración declarativa L0/L1, (b) servicio externo del vendor vía **OAuth client credentials + API/MCP con scopes**, o (c) DSL sandboxed. Frontend: módulos remotos bajo la CSP estricta (P2-5).
3. **Conectores estilo Anthropic**: exponer el **MCP server por tenant con OAuth** (authorization code + scopes aprobados por el usuario) = conector universal para apps y agentes externos. Integration Hub suma la capa OAuth2.
4. **Gobernanza**: registro por tenant de plugins/versión/permisos, auditoría inmutable, telemetría, pipeline de promoción tenant→core con aprobación humana de Omni.

### 5. Agentes custom del cliente (L2) y elección de modelos

- **`ProveedorLLMEmpresa`**: proveedor, base_url, modelo, **API key del cliente cifrada en reposo** (R-CODE-8). El gateway LLM (PR #99) resuelve: config del tenant → **router de Omni por defecto**. Soporta *BYO-key* (cliente paga su consumo) y *Omni-metered* (P2-3 persiste consumo por tenant → facturable).
- **`AgenteDefinicion`** por empresa (datos, no código): prompt/propósito, tools MCP permitidas (scopes), modelo preferido, triggers (conversacional / Celery programado / evento), presupuesto de tokens y rate limits.
- Salvaguardas: **modo sugerencia por defecto** (escrituras requieren aprobación humana hasta promoción), endpoints idempotentes + auditoría inmutable, **mini-eval de ingreso** con el harness de `tests_eval/` (patrón precision@1) antes de activar, kill-switch por agente y tenant.

## Secuencia

La plataforma de extensión se construye **después de la fase L10n** (§3.7): L10n crea exactamente la maquinaria de puertos y resolución por empresa que el plugin system necesita — la localización venezolana será el primer "plugin" del sistema. Prerrequisitos técnicos de agentes custom: P2-2 (Celery) y P2-3 (consumo persistido), ya en cola.

## Consecuencias

- Una sola plataforma sirve a ambos modos y ambos carriles; la diferencia es qué niveles se habilitan y quién aprueba.
- RLS (CTF-012) se vuelve aún más crítica con plugins de terceros en SaaS.
- Los plugins declarativos (L0/L1) funcionan offline gratis; los de servicio externo declaran su degradación (directriz offline-first del owner, 2026-06-12).
