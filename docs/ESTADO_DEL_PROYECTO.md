# Estado del Proyecto — Omni ERP

> Corte: 2026-06-19. Documento de situación para retomar el trabajo con contexto
> completo. La planificación canónica sigue siendo
> [`PLAN_MAESTRO_UNICO.md`](PLAN_MAESTRO_UNICO.md); esto es una foto del avance.

## 1. Resumen ejecutivo

El núcleo transaccional del ERP (ventas, compras, inventario, finanzas, fiscal
Venezuela, contabilidad, CxC/CxP, tesorería, RRHH/nómina base, comisiones,
manufactura base) está implementado con API multi-tenant, dinero en `Decimal`
(R-CODE-4), aislamiento por `id_empresa` (R-CODE-1), idempotencia en escrituras
financieras y suite de tests verde con gate de cobertura (~94 % backend, gate de
servicios frontend). CI/CD a Railway (`develop`=staging, `main`=producción).

Las dos grandes capacidades trabajadas más recientemente:

- **Offline-first del POS (ADR-001 / CTF-008 / ADR-012)** — base completa:
  pull de catálogo, outbox idempotente del cliente, y **endpoint atómico de
  venta POS** (`POST /api/sync/push/ventas/`) que crea nota + detalles +
  entrega + pagos en una sola transacción idempotente.
- **Disciplina de dinero en el frontend (FE-HIGH-7 / BUG-M6)** — barrido
  completo a `decimal.js` en todos los flujos de pago/vuelto, totales de
  documentos y libros fiscales.

## 2. Avances completados recientemente (PRs mergeados a `develop`)

| Área | Entregable | PR |
| --- | --- | --- |
| Offline POS | ADR-012 (modelo transaccional de venta offline) | #157 |
| Offline POS | Contrato + builder del sobre `VentaOffline` | #160 |
| Offline POS | Hook `useOutboxFlush` (reenvío al reconectar) | #161 |
| Offline POS | Outbox de ventas (`salesOutbox`) | #156 |
| **Offline POS** | **Endpoint atómico `POST /api/sync/push/ventas/` (dinero)** | **#171** |
| Dinero FE | `decimal.js` en ModalPago/ResumenPago (pago/vuelto) | #165 |
| Dinero FE | `decimal.js` en los 4 formularios de venta | #167 |
| Dinero FE | `decimal.js` en detalles de venta + libros fiscales SENIAT | #168 |
| Dinero FE | `decimal.js` en sumas de inventario | #169 |
| Calidad FE | `react-hook-form`+`zod` en formularios (FE-CRIT-1) | #152, #153 |
| Cobertura | Servicios FE: transacción financiera, cuenta bancaria, pagos, devoluciones POS | #154, #155, #162, #163 |

(Detalle cronológico completo en [`../ORCHESTRATOR_LOG.md`](../ORCHESTRATOR_LOG.md).)

## 3. Lo que queda pendiente para el 100 %

Tomado de `PLAN_MAESTRO_UNICO.md` §5.2. Ordenado por lo que habilita el piloto.

### 3.1 Offline POS — cerrar el ciclo (continuación de ADR-012)
- [ ] **Frontend**: `PosPage` arma el sobre `VentaOffline`, lo encola en
  `salesOutbox` al fallar la red y hace **flush al reconectar** reconciliando
  `client_uuid → id_nota_venta`.
- [ ] **Frontend**: UI de cola para el cajero (ventas "por confirmar" /
  "requiere revisión").
- [ ] Devoluciones offline y política de stock insuficiente (config de tenant)
  — explícitamente fuera de ADR-012, decisión posterior.

### 3.2 Seguridad / endurecimiento (gate de producción)
- [ ] **CTF-012** (vence 2026-08-01): rol de BD no-dueño → `RLS_ENABLED=True`
  en staging→prod; extender RLS de ~15 a ~92 tablas. **Acción de owner/infra.**
- [ ] P1: throttling DRF global · django-axes · revocación JWT · auditoría
  inmutable · pasada IDOR · **backups con restore probado**.
- [ ] **Branch protection en GitHub** — acción exclusiva del owner.
- [ ] Gates finales: `trivy` y `schemathesis` bloqueantes; `npm audit` al cerrar CTF-007.

### 3.3 Frontend (calidad / cobertura)
- [ ] Ratchet de cobertura frontend 55 %→80 % por escalones + `eslint-plugin-security`.
- [ ] FE-HIGH-13 (JWT fuera de `localStorage`), FE-HIGH-11 (interceptor 401+refresh),
  FE-HIGH-3/4/15 (TanStack donde aún se usa `useEffect`+fetch).
- [ ] UI faltante de módulos hoy API-only cuando el piloto la exija (compras, CxP,
  contabilidad, tesorería, RRHH/nómina).

### 3.4 Piloto distribuidora (puesta en producción real)
- [ ] **Migración de datos reales** (clientes, productos, inventario inicial,
  saldos CxC) vía `apps/migracion_datos`, validación fila por fila.
- [ ] Caja diaria operativa (apertura/cierre, pagos mixtos VES+USD, cuadre).
- [ ] Datos fiscales reales (config fiscal, correlativos, primera factura SENIAT
  + libro de ventas del mes).
- [ ] Capacitación + arranque controlado + acompañamiento intensivo.
- [ ] Agente de cobranza en modo sugerencia sobre cartera real.

### 3.5 Fases mayores de producto
- [ ] **1.G POS de mostrador** (táctil, código de barras USB, recibo térmico 80 mm),
  comisiones de vendedores, devoluciones/NC en flujo POS, despacho/entrega.
- [ ] **1.H Onboarding fábrica + BOM** y **1.I OF y costeo** (manufactura: MRP,
  órdenes de producción con etapas, costeo real).
- [ ] **Nómina venezolana completa** (LOTTT: utilidades, vacaciones, antigüedad,
  ISLR progresivo, cestaticket multimoneda).
- [ ] Observabilidad: Prometheus/Grafana (Sentry ya integrado).
- [ ] Service Workers / offline real en portales (Nivel 2).

## 4. Salud técnica / cómo retomar

- **Gate de cierre** obligatorio antes de cada "listo":
  [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md).
- **Flujo**: rama desde `develop` → PR (autoaprobable con CI verde + gate) →
  staging → PR `develop`→`main` (revisión humana del owner) → prod.
- **Deuda técnica fechada**: ver [`ctf/`](ctf/) y [`tech-debt/`](tech-debt/).
- Mapas de superficie autogenerados en [`audit/`](audit/) (`manage.py mapa_superficie`).
