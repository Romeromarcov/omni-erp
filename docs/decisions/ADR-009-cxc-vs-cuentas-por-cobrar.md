# ADR-009: Separación entre `cuentas_por_cobrar` y `cxc`

**Estado:** Aceptado
**Fecha:** 2026-06-01
**Autor(es):** Marco Romero, Claude Opus 4.8

## Contexto

La auditoría (M-DUP-1) marcó la coexistencia de dos apps con nombres similares:

- **`apps/cuentas_por_cobrar`** — el LIBRO contable de CxC: modelos
  `CuentaPorCobrar` y `AbonoCxC`, estados de cuenta (PDF), serializers/admin.
  Es la fuente de verdad del saldo por cobrar de cada cliente.
- **`apps/cxc`** — "Cobranza Inteligente" (Bloques 0–10): agentes, servidor MCP,
  acuerdos de pago (`AcuerdoPago`/`CuotaAcuerdo`), plantillas y gestión de
  cobranza (`PlantillaCobranza`/`GestionCobranza`), fraccionamiento
  (`LoteFraccionado`/`VentaFraccionada`), scoring y cartera vencida.

La duda era si se trata de duplicación a unificar o de una separación
intencional.

## Decisión

**Se mantienen separadas. Son dos contextos acotados distintos:**

- `cuentas_por_cobrar` es la **capa contable/ledger** (qué se debe).
- `cxc` es la **capa de proceso de cobranza asistida por IA** (cómo se cobra:
  acuerdos, recordatorios, scoring, fraccionamiento) que se apoya en el ledger.

No se fusionan porque tienen ciclos de cambio, riesgo y dependencias diferentes:
el ledger es estable y crítico para contabilidad; la cobranza inteligente itera
rápido y depende de agentes/MCP. Fusionarlas acoplaría el núcleo contable a la
volatilidad del módulo de IA.

## Consecuencias

- **Regla de dependencia:** `cxc` puede leer/referir el ledger de
  `cuentas_por_cobrar`; `cuentas_por_cobrar` NO debe depender de `cxc`.
- Los nombres se mantienen por compatibilidad de migraciones y URLs ya
  desplegadas (`/api/cuentas-por-pagar/`, `/api/cxc/`, `/api/cobranza/`).
- Si en el futuro la frontera se difumina, se revisita con un ADR nuevo (no se
  edita éste).

## Referencias

- `PLAN_TRABAJO_AUDITORIA_2026-06-01.md` M-DUP-1.
- Apps: `backend/apps/cuentas_por_cobrar/`, `backend/apps/cxc/`.
