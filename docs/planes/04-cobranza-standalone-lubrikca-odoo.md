# Plan D — Standalone de Cobranza en Lubrikca, integrado a Odoo por el Hub

| Campo | Valor |
|-------|-------|
| **Objetivo** | Desplegar **Omni Cobranza standalone** en Lubrikca, leyendo la cartera desde **Odoo** vía Integration Hub. Escritura de vuelta a Odoo **prevista a futuro**. |
| **Estado** | **APROBADO** por el cliente. Base técnica sorprendentemente avanzada. |
| **Base de decisión** | ADR-002 (Omni Cobranza = primer standalone / wedge), ADR-003 (Integration Hub), ADR-008 (`clients/cobranza-standalone`), ADR-009 (separación `cuentas_por_cobrar` / `cxc`). |
| **Esfuerzo** | ~2–3 semanas (sin push) · +1 semana si push a Odoo en este alcance. |

## Punto de partida (verificado en código) — lo que YA existe

- **Conector Odoo XML-RPC funcional** (`apps/integration_hub/connectors/odoo/`): cliente robusto (Odoo 8–18+, `defusedxml`), `pull_*` de contactos/productos/pedidos/facturas/pagos/inventario y **`pull_cartera_vencida`** con aging (`al_dia`/`1_30`/`31_60`/`61_90`/`mas_90`).
- **Sync inbound operativo** (`services/sync_engine.py`): deduplicación por `EntidadSincronizada` + checksum SHA-256, sync incremental, Celery async, credenciales cifradas (`EncryptedJSONField`, Fernet).
- **Abstracción `CarteraProvider`** (`apps/cuentas_por_cobrar/services_cartera_provider.py`): implementaciones `OdooCarteraProvider` y `NativeCarteraProvider`, conmutables por parámetro `cxc.datasource`.
- **`GestionCobranza.cliente_id` es string flexible** (no FK): admite IDs externos de Odoo sin migrar.
- **Agente IA de cobranza agnóstico** (`apps/cxc/agents/cobranza_agent.py`): consume `CarteraProvider`, no conoce si la fuente es Omni u Odoo.
- Cobranza es **hoja del árbol de dependencias**: ningún otro módulo depende de ella.

## Lo que falta

### Fase D1 — Desacople final del ledger · ~3–4 días
- `apps/cuentas_por_cobrar/models.py`: la FK `cliente → crm.Cliente` es **obligatoria**. Hacerla **nullable** y operar con `cliente_id` string (mismo patrón que `GestionCobranza`), para que una cuenta por cobrar pueda nacer de Odoo sin CRM de Omni.
- Feature-flag para **omitir el asiento contable** si la empresa no usa contabilidad de Omni (el flujo ya es tolerante en `apps/cxc/api/acuerdos.py`).
- **DoD:** crear/gestionar una cuenta por cobrar con cliente externo (Odoo) sin `crm.Cliente`.

### Fase D2 — Conexión Odoo real de Lubrikca · ~3–4 días
- Configurar `ConectorInstancia` de Lubrikca (host/db/user/api_key cifrados).
- **Validar `OdooCarteraProvider` contra el Odoo real** (hoy solo hay tests con mocks, sin integración real).
- Programar sync inbound (cartera vencida + pagos de cliente) vía Celery.
- **DoD:** la cartera vencida real de Lubrikca aparece en Omni y el agente la prioriza.

### Fase D3 — Push de resultados a Odoo · ~1 semana — **PREVISTO A FUTURO**
- El `SyncEngine` **no implementa outbound** (corta con error si `direccion="outbound"`). Para devolver pagos/gestiones a Odoo hay que implementar `_ejecutar_push()` + manejo de conflictos + reintentos granulares.
- Los métodos `push_contacto`/`push_producto` del conector existen como base; faltan los de pagos/gestiones de cobranza.
- **El cliente confirmó que la escritura se requerirá a futuro** → planificar, no necesariamente en el MVP. Abrir CTF cuando se comprometa fecha.
- **DoD:** un pago registrado en Omni se refleja en Odoo de forma idempotente.

### Fase D4 — Shell frontend standalone · ~1 semana
- `clients/cobranza-standalone` (ADR-008): empaquetar solo `{cxc, core, finanzas, auth, i18n}`, sin ventas/inventario/fiscal.
- **DoD:** build standalone que arranca solo el dominio de cobranza.

## Apps imprescindibles vs prescindibles (standalone)

- **Imprescindibles:** `core` (Empresa/Usuarios), `finanzas` (Pago/Moneda/Tasa), `cxc`, `integration_hub`, `configuracion_motor`, `contabilidad` (tolerante).
- **Prescindibles:** `crm`, `ventas`, `fiscal`, `inventario`, `compras`, `rrhh`, `nomina`, `manufactura`, etc.

## Definition of Done (MVP standalone, sin push)

- [x] FK `cliente` desacoplada (nullable + `cliente_externo_id` string), migración 0002 + tests.
- [~] `OdooCarteraProvider` validado contra el Odoo real de Lubrikca. — Tooling listo (`validar_conector_odoo`); la validación final es acción de ops con credenciales reales.
- [x] Sync inbound programado y operativo (cartera + pagos). — `sync_automatico_todos` (15 min, pagos/entidades) + `sync_cartera_odoo_todos` (30 min, cache de cartera Mode A) en `CELERY_BEAT_SCHEDULE`. Fix de la task `sync_cartera_odoo` (estaba rota por import).
- [x] Shell frontend standalone funcional. — Perfil de build `cobranza` (`npm run build:cobranza`); ver `clients/cobranza-standalone/`.
- [x] Tests de aislamiento multi-tenant verdes; gate de cierre por PR.
- [x] Push a Odoo (D3) documentado como siguiente hito con CTF fechado. — [CTF-011](../ctf/CTF-011.md) (vence 2026-09-01).

### Estado de avance (2026-06-07)

- **D1 — Desacople del ledger:** ✅ FK opcional + `cliente_externo_id`/`cliente_externo_nombre` + CheckConstraint; providers, aging, pagos, serializer y admin operan con el deudor agnóstico. El asiento contable ya es tolerante vía `Empresa.contabilidad_activa`.
- **D2 — Conexión Odoo:** ✅ comandos `configurar_conector_odoo` / `validar_conector_odoo`, sync inbound programado, fix de task. Validación contra el Odoo real = acción de ops.
- **D3 — Push a Odoo:** ⏸️ diferido → [CTF-011](../ctf/CTF-011.md).
- **D4 — Shell standalone:** ✅ perfil de build `cobranza` (recorta ventas/inventario/fiscal/escáner).
