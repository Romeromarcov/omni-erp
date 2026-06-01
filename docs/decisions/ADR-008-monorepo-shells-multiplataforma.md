# ADR-008: Monorepo de Clientes + Shells Mobile y Desktop sobre la Capa 1

**Estado:** Aceptado
**Fecha:** 2026-06-01
**Autor:** Marco Romero (founder) + asistencia Claude Code
**Categoría:** Arquitectura de clientes y empaquetado
**Reemplaza:** ninguno
**Relacionado con:** ADR-001 (offline-first en 3 niveles), ADR-002 (modularidad + wedge), ADR-003 (Integration Hub), ADR-004 (gestion-cxc-V2 standalone)

---

## Contexto

A la fecha, OmniERP tiene un único cliente: una SPA web React 19 + Vite + MUI que vive en `frontend/`. Esa SPA está empezando a comportarse como **PWA de Nivel 1** de ADR-001 (vite-plugin-pwa con `NetworkFirst` para `/api/`), pero sin outbox para escrituras, sin almacenamiento local de eventos y sin shell nativo en mobile ni desktop.

Tres presiones convergen sobre esta limitación:

1. **Cronograma de ADR-001.** Define hitos concretos que requieren shells que la web por sí sola no cubre: POS distribuidora (mes 7), kioscos (mes 8-9), app vendedores en calle (mes 9), captura de OF en planta (mes 11-12). Esos casos de uso exigen ejecución nativa (impresora térmica, cámara, GPS, operación sostenida sin red).
2. **Estrategia wedge de ADR-002.** El primer producto standalone confirmado (Omni Cobranza, ADR-004) necesita un empaquetado diferenciado del ERP completo. Hoy no hay forma de extraer un subconjunto del frontend sin duplicar código.
3. **Realidad operativa de los clientes objetivo.** La distribuidora necesita un POS robusto en mostrador (desktop) y una app de vendedores (mobile). La fábrica necesita captura de avance en planta (mobile o tablet). Ningún cliente compra "una PWA".

Adicionalmente, la auditoría del código actual reveló acoplamientos que impiden portar el frontend tal cual a otros runtimes:

- `frontend/src/services/api.ts` usa `localStorage` y `window.location` directamente — no portable a React Native.
- Los servicios por dominio mezclan transporte HTTP con lógica de dominio.
- Los tipos TS viven solo en `frontend/src/types`; no se generan desde el contrato del backend.
- No hay frontera entre "código común" y "código de la web": cualquier nuevo cliente duplicaría schemas Zod, reglas de cálculo, hooks de datos.

Sin una decisión arquitectónica explícita, construir mobile/desktop por simple copy-paste llevaría a tres codebases divergentes y a la imposibilidad de cumplir el cronograma de ADR-001.

---

## Decisión

### 1. Adoptar un monorepo TypeScript para todos los clientes

Se reorganiza el código de clientes en dos directorios de primer nivel bajo la raíz del repo:

```
omni-erp/
├── backend/                        # sin cambios estructurales
├── clients/                        # shells de cliente (uno por empaquetado)
│   ├── web/                        # ← migración de frontend/ (shell Omni ERP, MUI)
│   ├── desktop/                    # Tauri 2 envolviendo el build de clients/web
│   ├── mobile/                     # Expo / React Native
│   └── cobranza-standalone/        # Shell de Omni Cobranza standalone (ADR-002/004)
├── packages/                       # código compartido por todos los shells
│   ├── domain/                     # Capa 1 pura: tipos, schemas Zod, reglas (cero I/O)
│   ├── api-client/                 # SDK TS sobre endpoints DRF
│   ├── offline/                    # Implementación de los 3 Niveles de ADR-001
│   ├── auth/                       # AuthService + SecureStorage interface
│   ├── i18n/                       # Recursos compartidos
│   └── config/                     # eslint, tsconfig, prettier compartidos
```

**Gestor:** `pnpm` workspaces + `turborepo` para builds incrementales.

### 2. Mapeo a las Capas de ADR-002

- **`packages/domain`** materializa la **Capa 1 (Core de dominio)** de ADR-002 del lado cliente. Cero I/O, cero JSX, cero dependencias de plataforma. Es el único lugar donde viven schemas Zod, tipos derivados y reglas puras (cálculo de IVA, IGTF, totales, scoring, etc.).
- **`packages/api-client`**, **`packages/auth`**, **`packages/offline`**, **`packages/i18n`** son utilidades de **Capa 2** reutilizables entre shells. No definen UI.
- **`clients/web`**, **`clients/desktop`**, **`clients/mobile`** son shells de **Capa 2A** (parte del Omni ERP integrado).
- **`clients/cobranza-standalone`** es un shell de **Capa 2B** (standalone), que importa solo los módulos `cxc`, `crm`, `auth`, `i18n` desde `packages/`.

### 3. Stack por shell

| Shell | Stack | Notas |
|---|---|---|
| **web** | React 19 + Vite + **MUI 7** (heredado, mandatorio por §3.1 del Plan Maestro) | Migración 1:1 del `frontend/` actual. |
| **desktop** | **Tauri 2** envolviendo el build de `clients/web` | Reusa 100% el código web. Adaptadores nativos: `tauri-plugin-sql` (SQLite), `tauri-plugin-stronghold` (secrets), `tauri-plugin-printer` (térmica), `tauri-plugin-updater` (OTA). |
| **mobile** | **React Native + Expo (SDK 52+)** + `expo-router` + (RN Paper **o** Tamagui — decisión final en Fase 4 del workstream) | Comparte React, hooks, React Query, Zod, `packages/*`. Adaptadores nativos: `expo-secure-store`, `op-sqlite`. |
| **cobranza-standalone** | Mismo stack del shell que lo empaquete (web / desktop / mobile) | Solo cambia qué módulos importa. |

### 4. Sin librería de componentes JSX común

§3.1 del Plan Maestro impone MUI v7 como única UI permitida en la web sin wrappers propios. Esa regla **no se reabre**. Por consecuencia: **no se construye `packages/ui-kit` ni componentes JSX comunes entre web y mobile.** MUI no corre en React Native y un wrapper headless propio violaría §3.1.

Lo que se comparte entre shells es:
- Schemas, tipos, reglas (`packages/domain`).
- Cliente HTTP, autenticación, i18n (`packages/api-client`, `auth`, `i18n`).
- Motor offline (`packages/offline`).
- Hooks de datos basados en React Query (en `packages/` cuando sean platform-agnostic; en cada shell cuando dependan del runtime).

Lo que **no** se comparte: JSX, theming, navegación, componentes visuales.

### 5. Offline-first: implementación de los 3 Niveles de ADR-001

ADR-001 define los niveles. Este ADR define **dónde vive el código**:

- **`packages/offline`** expone una interfaz `LocalStore` y un motor de outbox + event sourcing único, configurable por feature. Cada feature declara su política (`read-cached`, `write-queueable`, `write-online-only`, `read-realtime`).
- **Adaptadores por plataforma:**
  - Web → IndexedDB vía Dexie.js.
  - Desktop → SQLite vía `tauri-plugin-sql`.
  - Mobile → SQLite vía `op-sqlite`.
- La estrategia de **resolución de conflictos** es exactamente la de ADR-001 § "Resolución de conflictos en sincronización" (event sourcing + LWW + auditoría + bloques de numeración fiscal). No se redefine.
- **Cambios mínimos en el backend** para habilitarlo:
  - Endpoints aceptan `client_id` (UUID generado por cliente) para idempotencia.
  - Endpoints devuelven `updated_at` server para LWW.
  - Endpoint genérico `/api/sync/pull?since=...&entities=...` para hidratación y diff.
  - Reusar `apps/core/events.py` como base de event sourcing del lado cliente.

**Nivel 3 (versión lite multi-día) queda explícitamente fuera del alcance de este ADR.** Se construye cuando aparezca un cliente concreto que lo necesite (ADR-001 § "Cuándo se construye cada nivel").

### 6. Generación de tipos desde el contrato del backend

Se adopta `drf-spectacular` en el backend + `openapi-typescript` en CI para regenerar `packages/api-client/src/generated/` ante cada cambio del contrato. El CI falla si hay diff sin commit. Esto cierra el drift documentado en la auditoría.

### 7. Auth y secretos

- **Web:** `httpOnly cookie` (refresh) + token en memoria. Se elimina el uso de `localStorage` para JWT que existe hoy en `services/api.ts`.
- **Desktop:** `tauri-plugin-stronghold` o keyring del SO.
- **Mobile:** `expo-secure-store` (Keychain/Keystore).

Todos los shells implementan la interfaz `SecureStorage` de `packages/auth`.

### 8. Subordinación al roadmap del Plan Maestro

**Ninguna fase de este ADR arranca si pone en riesgo la sub-fase 1.F (distribuidora en producción)** — R-PROC-8 + §5.2 del Plan Maestro. El cronograma operativo (triggers, fases) vive en el workstream §5.2-ter del Plan Maestro, no en este ADR.

La única excepción: **completar el Nivel 1 en la PWA web ya existente puede arrancar en paralelo a 1.F**, porque es deuda técnica abierta (§4.3 del Plan Maestro: "Service Workers / offline real pendiente") y no introduce un shell nuevo.

---

## Por qué se decidió así

### Por qué monorepo (no repos separados)

1. **Capa 1 es uno y solo uno.** Schemas, reglas y tipos deben tener una fuente de verdad. Repos separados generan drift garantizado.
2. **Cambios atómicos en el contrato.** Un cambio en `packages/domain` debe poder forzar re-build de todos los shells en el mismo PR.
3. **Refactor seguro.** Renombrar un símbolo en `packages/` con feedback inmediato de TS en los 4 shells es invaluable.
4. **CI unificado.** Una sola matriz de jobs por workspace, un solo lockfile.

### Por qué Tauri 2 en desktop (no Electron)

1. **Binarios <15MB** (Electron 80-150MB). La distribuidora no tiene infraestructura para empujar 150MB a cada caja por OTA.
2. **Mejor consumo de RAM** — relevante en hardware pyme.
3. **Reusa el build de `clients/web`** sin reescritura.
4. **Plan B documentado:** Electron solo para el shell de "caja" si Tauri 2 da problemas con periféricos específicos (impresoras fiscales).

### Por qué React Native + Expo en mobile (no Flutter, no nativo)

1. **Reusa React, hooks, React Query, Zod** ya dominados.
2. **Reusa 100% de `packages/*`** (es TS).
3. **Expo simplifica build, OTA, push notifications** — crítico para un founder solo.
4. **Flutter exigiría reescribir todo en Dart** y duplicar la Capa 1. Inviable con 15-25 h/semana.

### Por qué no UI-kit común

§3.1 lo prohíbe en web. Construir uno solo para mobile no genera reuso. Construir uno headless propio para los dos es exactamente el "wrapper propio" que §3.1 prohíbe. La separación correcta es **lógica común, JSX por shell**.

### Por qué `clients/cobranza-standalone` desde el día 1 del monorepo

ADR-002 + ADR-004 ya confirmaron Omni Cobranza standalone como producto. Diseñar el monorepo sin ese shell desde el inicio obligaría a refactorizar a los pocos meses. El costo marginal de declararlo ahora es cero — solo importa un subset de `packages/`.

---

## Alternativas consideradas

### Alternativa A: Mantener un solo frontend web y empaquetarlo como PWA en todas las plataformas (rechazada)
- No cubre los casos de uso de ADR-001 que requieren ejecución nativa sostenida (impresora térmica, sensores, GPS).
- En iOS, las PWAs tienen límites severos de storage y background tasks.
- No diferencia el shell standalone del integrado.

### Alternativa B: Repos separados por shell (rechazada)
- Garantiza drift de tipos y reglas — el problema más caro que tenemos hoy y que la auditoría detectó.
- Multiplica CI/CD, releases, dependencias.

### Alternativa C: Flutter para mobile + Electron para desktop (rechazada)
- Flutter exige reescribir todo en Dart y mantener dos versiones de cada regla.
- Electron es 10x el tamaño de Tauri y consume el doble de RAM.

### Alternativa D: React Native Web para unificar web y mobile (considerada, no elegida)
- Obligaría a abandonar MUI en web y violar §3.1 del Plan Maestro.
- Madurez de RN Web en componentes complejos (tablas grandes, formularios fiscales) es insuficiente para el caso de uso.

### Alternativa E: Capacitor envolviendo la web actual (considerada, no elegida)
- Más rápido a corto plazo, pero rendimiento mobile insuficiente para el flujo de toma de pedidos offline.
- No habilita el Nivel 2 real (SQLite + sync engine eficiente).

---

## Consecuencias

### Positivas

- **Una sola fuente de verdad** para schemas, reglas y tipos de cliente (Capa 1).
- **Costo marginal de nueva plataforma bajo** una vez establecido el monorepo: una feature nueva se toca una vez en `packages/` y se compone por shell.
- **Habilita el cronograma de ADR-001** (POS, kioscos, app vendedores, captura OF) sin reinventar arquitectura por cada caso.
- **Permite ejecutar la estrategia wedge** de ADR-002 con `clients/cobranza-standalone` desde el día 1.
- **Elimina el drift de tipos cliente/server** con generación automática desde DRF.
- **Reduce el JWT en `localStorage`** que es un punto débil de seguridad hoy.

### Negativas

- **Costo de bootstrap.** Migrar `frontend/` → `clients/web/` + extraer `packages/` es semanas de refactor del founder. Mitigación: ejecutar **solo después** del DoD de 1.F; nunca compite por horas con la distribuidora en producción.
- **Complejidad operativa.** 4 shells implican 4 pipelines de build, 4 releases, 4 tiendas (App Store, Play Store, instaladores desktop, web). Mitigación: turborepo y CI matricial.
- **Curva de Tauri y RN** para el founder. Mitigación: empezar por desktop (Tauri reusa el código web → menor riesgo) antes de mobile.
- **Sin componentes JSX comunes** = duplicación visual entre web y mobile. Aceptada conscientemente: la lógica es lo caro, no el JSX.

### Neutras

- El backend debe añadir `client_id`, `updated_at` en respuestas, y el endpoint `/api/sync/pull`. Es trabajo acotado y reusable por todos los shells.
- El stack de cada shell tiene su propio test runner (Vitest, Jest/Expo, tauri-driver). Se acepta.

---

## Cómo se mide el éxito de esta decisión

Indicadores de que la decisión está funcionando:

- **Reutilización de código:** >70% del LOC de cualquier feature vive en `packages/*` (no en los shells).
- **Tiempo de paridad por feature:** ≤3 días end-to-end (web + mobile + desktop) tras Fase 6 del workstream.
- **Offline real cumplido:** vendedor en ruta opera 8 horas sin red y sincroniza sin pérdida ni duplicados (Nivel 2 de ADR-001).
- **Tamaño binarios:** mobile <40MB, desktop <15MB.
- **Cobertura tests:** ≥60% en cada workspace.
- **Sin drift:** CI rompe ante diff de tipos generados desde DRF.

Indicadores de que la decisión necesita reconsiderarse:

- Tauri 2 incapaz de manejar periféricos clave (impresoras fiscales SENIAT). → Considerar Electron solo para el shell "caja".
- Mobile no logra Nivel 2 estable en 6 meses de Fase 4. → Considerar Capacitor + PWA reforzada como interim.
- El founder dedica >40% de su tiempo a mantenimiento de los 4 shells. → Reducir a 2 shells (web + uno nativo).

---

## Cómo revisitar esta decisión

Esta decisión debería reconsiderarse explícitamente si:

- Aparece un requisito de rendimiento o de plataforma que Tauri/Expo no resuelven.
- El cronograma de ADR-001 se acelera y exige un atajo que el monorepo no permita.
- Un cliente paga por una versión Nivel 3 (lite multi-día) — entraría como ADR nuevo, no modificación de este.

Modificar esta decisión requiere ADR nuevo que la reemplace explícitamente (no cambios incrementales silenciosos).

---

## Tareas relacionadas

- Workstream operativo: `PLAN_MAESTRO_UNICO.md` §5.2-ter (cronograma de fases, triggers, DoDs).
- Actualizar §3.8 del Plan Maestro: añadir ADR-008 al índice.
- Añadir `drf-spectacular` al backend y configurar `openapi-typescript` en CI antes de la Fase 1.
- Decisión final RN Paper vs Tamagui antes de iniciar la Fase 4 (queda como sub-decisión menor del workstream, no como ADR).

---

## Referencias

- ADR-001: niveles de offline-first y cronograma de módulos críticos.
- ADR-002: capas (1, 2A, 2B, 3) y estrategia wedge / standalone.
- ADR-003: Integration Hub (relevante para `clients/cobranza-standalone` integrándose a ERPs externos).
- ADR-004: gestion-cxc-V2 como primer standalone confirmado.
- Plan Maestro §3.1: "MUI v7 — única UI permitida en web".
- Plan Maestro §4.3: deuda técnica "Service Workers / offline real pendiente".
- Plan Maestro §5.2: 1.F como hito que manda.
- Auditoría 2026-06-01 de `frontend/src/services/api.ts` (uso directo de `localStorage`/`window`).

## Changelog

### v1.0 — 2026-06-01
- Versión inicial. Decisión tomada y documentada. Absorbe y reemplaza el documento provisional `docs/PLAN_APPS_MULTIPLATAFORMA.md` (eliminado).
