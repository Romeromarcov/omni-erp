# Omni Cobranza — Standalone (ADR-008 / Plan D — Fase D4)

Distribución **standalone** del dominio de **Cobranza (CxC)**, pensada para
clientes como **Lubrikca** que leen su cartera desde **Odoo** vía el Integration
Hub y no usan el resto del ERP (ventas, inventario, fiscal, etc.).

No es un código aparte: es el **mismo frontend** (`/frontend`) compilado con un
**perfil de producto** que recorta los módulos no imprescindibles. Esto evita
duplicar la app y mantiene un solo origen de verdad (ADR-008).

## Qué incluye el perfil `cobranza`

| Incluido (imprescindible)                | Excluido (prescindible)        |
|------------------------------------------|--------------------------------|
| Auth / sesión                            | Ventas                         |
| Core (empresas, usuarios, configuración) | Inventario                     |
| Finanzas (monedas, tasas, pagos)         | Fiscal                         |
| **Cobranza (CxC)**                       | Escáner                        |
| Integraciones (Hub → Odoo)               |                                |
| Panel SaaS (solo proveedor, por rol)     |                                |

El recorte lo controla [`frontend/src/config/appProfile.ts`](../../frontend/src/config/appProfile.ts):
`navigation.tsx` filtra las secciones y `router.tsx` no monta los grupos de
rutas excluidos. En el perfil `full` (default) no cambia nada.

## Cómo se compila

```bash
cd frontend
npm ci
npm run build:cobranza      # vite build --mode cobranza  → carga frontend/.env.cobranza
```

El artefacto sale en `frontend/dist/` y arranca **solo** el dominio de cobranza.
La variable que activa el perfil es `VITE_APP_PROFILE=cobranza`
(en [`frontend/.env.cobranza`](../../frontend/.env.cobranza)).

Para un build full normal: `npm run build`.

## Backend

El standalone usa el **mismo backend** Omni. Apps imprescindibles del dominio:
`core`, `finanzas`, `cxc`, `cuentas_por_cobrar`, `integration_hub`,
`configuracion_motor`, `contabilidad` (tolerante).

Para Lubrikca, la cartera se lee de Odoo (Mode A). Provisión y validación de la
conexión (Plan D — D2):

```bash
cd backend
python manage.py configurar_conector_odoo --empresa <id_o_rif> \
    --host https://lubrikca.odoo.com --db lubrikca --user api@lubrikca.com \
    --api-key <clave> --datasource-odoo --test
python manage.py validar_conector_odoo --empresa <id_o_rif>
```

## Estado

- D1 — Desacople del ledger (FK `cliente` opcional): ✅
- D2 — Conexión Odoo + tooling + sync programado: ✅ (validación contra el Odoo
  real de Lubrikca = acción de ops con credenciales reales).
- D3 — Push a Odoo (outbound): ⏸️ diferido → [CTF-011](../../docs/ctf/CTF-011.md).
- D4 — Shell frontend standalone (este perfil): ✅
