# Plan A — Offline-first real (por niveles)

| Campo | Valor |
|-------|-------|
| **Objetivo** | Que la app opere sin conexión y sincronice al reconectar, por niveles de ADR-001. |
| **Base de decisión** | [`docs/decisions/ADR-001-postgres-server-offline-clients.md`](../decisions/ADR-001-postgres-server-offline-clients.md) (ACEPTADO, **no implementado**). |
| **Estado actual** | App **online pura**. PWA solo cachea assets + API por 5 min (`NetworkFirst`). Sin almacén local, sin cola, sin sync. |
| **Esfuerzo** | ~6–8 semanas (frontend **y** backend). |
| **Deuda** | [CTF-008](../ctf/CTF-008.md). |

## Punto de partida (verificado en código)

- `frontend/vite.config.ts`: Workbox precachea assets y aplica `NetworkFirst` a `/api/` con
  `maxAgeSeconds: 300`. No hay Background Sync ni outbox.
- `frontend/src/contexts/AuthContext.tsx`: **purga** datos de negocio de `localStorage`
  (solo guarda IDs de UI). No hay IndexedDB/SQLite.
- Backend: `fecha_creacion`/`fecha_actualizacion` existen (auditoría), pero **no** hay
  endpoints de sync, deltas ni idempotencia por UUID de cliente.
- `apps/integration_hub` tiene patrones reutilizables (checksums, `EntidadSincronizada`,
  mapeo de IDs) que sirven de inspiración para el motor de sync de clientes.

## Fases

### Fase A1 — Resiliencia de red (Nivel 1) · ~1 semana
- Banner global online/offline (`navigator.onLine` + eventos `online`/`offline`); badge "datos desactualizados".
- Reintento de mutaciones con backoff en la capa de servicios HTTP (`frontend/src/services/`), **sin** outbox completo.
- Endurecer la PWA: cobertura de caché, política de expiración, fallback offline navegable.
- **DoD:** un corte de 5 min no rompe consultas; los reintentos completan al volver la red.

### Fase A2 — Almacén local + outbox (Nivel 2, módulos críticos) · ~3–4 semanas
- Frontend: **IndexedDB** (Dexie) con réplica de catálogo, precios, clientes asignados y stock al último sync.
- **Outbox** de mutaciones (ventas, cobros) con IDs **UUIDv7 generados en cliente** (el backend ya acepta UUID).
- Cola persistente + replay ordenado al reconectar; **Background Sync API**.
- Alcance acotado a módulos de campo/POS: ventas, cobros, consulta de stock/precio.
- **DoD:** un vendedor/caja opera 8–24 h sin red y sincroniza al volver, sin pérdida de datos.

### Fase A3 — Backend de sincronización · ~2 semanas (parcial en paralelo con A2)
- Endpoints de **sync con deltas/cursores** (`updated_at`/`version`), **idempotencia** de escrituras por UUID de cliente.
- **Resolución de conflictos** ("último gana" + bitácora; merge donde aplique).
- Reutilizar patrones de `apps/integration_hub` (checksums, tabla de mapeo).
- **DoD:** dos clientes offline editando el mismo dato se reconcilian sin pérdida ni duplicados.

### Fase A4 — Versión lite (Nivel 3) · futuro
- Subset funcional para días sin red (vender, consultar stock, cobrar) sin IA ni integraciones externas.
- **No construir especulativamente**; abrir solo si un cliente lo exige.

## Dependencias y orden

- A1 es independiente y aporta valor inmediato (se puede hacer junto al piloto).
- A2 depende de A1 (capa de servicios robusta) y avanza en paralelo con A3.
- A3 debe estar lista antes de declarar A2 "operativo en producción".

## Definition of Done (global)

- [ ] Niveles 1 y 2 implementados y verificados con cortes de red reales.
- [ ] Suite de tests de sync (conflictos, idempotencia, replay) verde en CI.
- [ ] Documentación de la arquitectura de sync (qué se replica, política de conflictos).
- [ ] [CTF-008](../ctf/CTF-008.md) cerrado con fecha real.
