# App `cxc` — Cobranza Inteligente

Módulo de **Cobranza Inteligente**: gestión proactiva de la cartera de cobranza, acuerdos de pago, fraccionamiento de ventas y un agente de IA de cobranza. Nació de un sistema previo real (GestionCxC) que se está absorbiendo dentro de Omni.

**Prefijo API:** `/api/cobranza/`

> Es distinta de [`cuentas_por_cobrar`](../cuentas_por_cobrar/README.md) (`/api/cxc/`), que es el ledger de saldos. Esta app gestiona la *acción de cobrar*.

## Estructura

A diferencia de las apps planas, `cxc` está organizada en submódulos:

```
cxc/
├── models/        acuerdos.py, cobranza.py, fraccionamiento.py, base.py
├── api/           router.py, cartera.py, cobranza.py, acuerdos.py, fraccionamiento.py, agente.py, serializers.py
├── services/      cuotas.py (cálculo de cuotas)
├── agents/        cobranza_agent.py (agente IA de cobranza)
└── mcp/           exposición MCP
```

## Modelos

| Modelo | Descripción |
|---|---|
| `CxcBaseModel` | Modelo base de los modelos de cobranza. |
| `GestionCobranza` | Gestión/actividad de cobranza sobre una cuenta. |
| `PlantillaCobranza` | Plantilla de mensaje de cobranza. |
| `AcuerdoPago` | Acuerdo de pago con un cliente. |
| `CuotaAcuerdo` | Cuota de un acuerdo de pago. |
| `LoteFraccionado` | Lote para fraccionamiento de ventas. |
| `VentaFraccionada` | Venta fraccionada en cuotas. |

## Endpoints

Recursos REST (CRUD vía router): `gestiones/`, `acuerdos/`, `plantillas/`, `lotes/`, `ventas-fraccionadas/`.

Rutas y acciones adicionales:

| Ruta | Descripción |
|---|---|
| `GET cartera/dashboard/` | Dashboard de cartera de cobranza. |
| `POST agente/` | Invocar el agente IA de cobranza. |
| `GET health/` | Health check del módulo (DB, cache, tasa del día). |
| `GET gestiones/prioridades/` | Gestiones priorizadas. |
| `GET gestiones/agenda/` | Agenda de cobranza. |
| `POST gestiones/{id}/preview-plantilla/` | Previsualizar plantilla de mensaje. |
| `POST acuerdos/{id}/registrar-pago/` | Registrar pago de un acuerdo. |
| `GET acuerdos/vencimientos-proximos/` | Vencimientos próximos. |
| `GET ventas-fraccionadas/resumen/` | Resumen de ventas fraccionadas. |
| `POST lotes/{id}/...` | Operaciones sobre lotes fraccionados. |
