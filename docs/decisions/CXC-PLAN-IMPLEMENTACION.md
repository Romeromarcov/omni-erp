# PLAN DE IMPLEMENTACIÓN — Omni CxC (`apps/cxc_cobranza/`)
**Módulo: Cuentas por Cobrar & Cobranza Inteligente**
**Estrategia: Opción A — Integrado en Omni desde el día 1, sin deployment separado**
**Fecha:** 2026-05-28
**Estado:** Aprobado

---

## 0. PRINCIPIOS DE EJECUCIÓN

| Principio | Detalle |
|-----------|---------|
| **Ritmo** | 15–25 h/semana, founder solo |
| **Unidad mínima** | Cada sesión termina con algo que corre en producción |
| **Sin regresión** | Cada bloque tiene tests antes de avanzar |
| **R-CODE compliance** | R-CODE-1 (multi-tenant) · R-CODE-4 (Decimal) · R-CODE-5 (UUIDv7) · R-CODE-6 (soft delete) · R-CODE-7 (MCP co-requisito) · R-CODE-11 (AsientoContable) |
| **Hub-first** | Toda conexión externa va por el Integration Hub — ninguna llamada HTTP directa desde `apps/cxc/` |
| **Sin duplicación** | CxC extiende infraestructura existente; no crea modelos paralelos a finanzas, crm o cuentas_por_cobrar |

---

## REGLA DE ORO — CHECKLIST ANTES DE CADA COMMIT EN `apps/cxc/`

```
□ ¿Este import es de apps.finanzas, apps.crm, apps.cuentas_por_cobrar?
  → Bien. Estamos reutilizando infraestructura.

□ ¿Este import es de apps.integration_hub?
  → Bien, pero solo a través del CarteraProvider — CxC no llama al Hub directamente.

□ ¿Este código hace una llamada HTTP a una API externa (BCV, Binance, Odoo)?
  → MAL. Eso va en integration_hub/connectors/. Mover inmediatamente.

□ ¿Este código duplica un modelo que ya existe en finanzas o cuentas_por_cobrar?
  → MAL. Usar el modelo existente y agregar FK o servicio si falta funcionalidad.

□ ¿Este servicio implementa algo que debería estar en cuentas_por_cobrar?
  → Si es aging, scoring o cartera_provider: sí, mover allá.
  → Si es específico de acuerdos o gestiones de cobranza: queda en cxc.
```

---

## MAPA DE INFRAESTRUCTURA — QUÉ YA EXISTE EN OMNI

| Concepto | Ya existe | Dónde |
|----------|-----------|-------|
| `TasaCambio` (OFICIAL_BCV, PROMEDIO_MERCADO, etc.) | ✅ | `apps/finanzas/models.py` |
| `Moneda` | ✅ | `apps/finanzas/models.py` |
| `MetodoPago` | ✅ | `apps/finanzas/models.py` |
| `Pago` genérico (multi-tipo, multi-moneda) | ✅ | `apps/finanzas/models.py` |
| `CuentaPorCobrar` | ✅ | `apps/cuentas_por_cobrar/models.py` |
| `AbonoCxC` | ✅ | `apps/cuentas_por_cobrar/models.py` |
| `Cliente` | ✅ | `apps/crm/models.py` |
| Comando BCV | ✅ | `apps/finanzas/management/commands/update_bcv_exchange.py` |
| `BaseConnector` Hub | ✅ | `apps/integration_hub/connectors/base.py` |
| Conector Odoo | ✅ | `apps/integration_hub/connectors/odoo/` |

---

## ARQUITECTURA DE RESPONSABILIDADES

```
┌─────────────────────────────────────────────────────────────────┐
│  Integration Hub                                                 │
│  ┌─────────────────────┐  ┌──────────────────────────────────┐  │
│  │ connectors/odoo/    │  │ connectors/tasas_ve/  [NUEVO]    │  │
│  │ + pull_cartera()    │  │ BCV (cascade 3 fuentes)          │  │
│  │ + pull_aging()      │  │ Binance P2P (5BUY+5SELL promedio)│  │
│  │ [ampliar existente] │  │                                  │  │
│  └─────────────────────┘  └──────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────┘
                         │ consume
┌────────────────────────▼────────────────────────────────────────┐
│  apps/finanzas/  [EXTENSIÓN mínima]                             │
│  TasaCambio ya existe → usar tipo PROMEDIO_MERCADO para Binance │
│  Task: sync_tasas_ve via Hub → persiste en TasaCambio           │
└────────────────────────┬────────────────────────────────────────┘
                         │ consume
┌────────────────────────▼────────────────────────────────────────┐
│  apps/cuentas_por_cobrar/  [EXTENSIÓN de servicios]             │
│  CuentaPorCobrar (ya existe)                                     │
│  + services/aging.py          ← portado de GestionCxC           │
│  + services/scoring.py        ← portado de GestionCxC           │
│  + services/cartera_provider.py ← abstracción Mode A/B          │
└────────────────────────┬────────────────────────────────────────┘
                         │ consume
┌────────────────────────▼────────────────────────────────────────┐
│  apps/cxc/  [SOLO DOMINIO PROPIO DE COBRANZA]                   │
│  GestionCobranza + PlantillaCobranza                             │
│  AcuerdoPago + CuotaAcuerdo + generar_cuotas()                  │
│  Fraccionamiento (feature-flagged)                               │
│  MCP Server cobranza                                            │
│  Agente IA cobranza                                              │
│  ViewSets + Frontend                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## ESTRUCTURA DE DIRECTORIOS — `apps/cxc/`

```
apps/cxc/
├── __init__.py
├── apps.py
├── models/
│   ├── __init__.py
│   ├── base.py               # CxcBaseModel (usa uuid7 de core)
│   ├── cobranza.py           # GestionCobranza, PlantillaCobranza
│   ├── acuerdos.py           # AcuerdoPago, CuotaAcuerdo
│   └── fraccionamiento.py    # LoteFraccionado, VentaFraccionada (feature-flagged)
├── services/
│   ├── __init__.py
│   └── cuotas.py             # generar_cuotas() — algoritmo propio de CxC
├── api/
│   ├── __init__.py
│   ├── router.py
│   ├── cobranza.py           # ViewSet GestionCobranza
│   ├── acuerdos.py           # ViewSet AcuerdoPago
│   ├── cartera.py            # Dashboard cartera (usa cuentas_por_cobrar.services)
│   └── fraccionamiento.py
├── mcp/
│   ├── __init__.py
│   └── server.py             # MCPServer("cxc") — R-CODE-7
├── agents/
│   └── cobranza_agent.py     # Agente IA (usa MCP server de cxc)
├── migrations/
│   └── 0001_initial.py
└── tests/
    ├── test_models.py
    ├── test_services.py
    ├── test_api.py
    └── test_mcp.py
```

---

## BLOQUE 0 — AUDITORÍA ANTES DE ESCRIBIR UNA LÍNEA
**Duración: 0.5 semanas · ~6 h**

### Sesión 0-A · Auditar finanzas (2 h)

Leer en detalle:
- `apps/finanzas/services.py` — ¿Tiene lógica de conversión de monedas?
- `apps/finanzas/views_extra/tasa_oficial_bcv.py` — ¿Cómo se actualiza BCV hoy?
- `apps/finanzas/management/commands/update_bcv_exchange.py` — ¿Qué fuente usa?
- `apps/finanzas/mcp.py` — ¿Qué tools ya expone?

**Preguntas clave:**
1. ¿El comando BCV ya usa múltiples fuentes o solo una?
2. ¿Existe ya tipo `BINANCE_P2P` en `TasaCambio` o se usa `PROMEDIO_MERCADO`?
3. ¿Existe servicio `convertir(monto, origen, destino)` en finanzas?
4. ¿Qué `tipo_documento` usar en `finanzas.Pago` para abonos de CxC?

### Sesión 0-B · Auditar cxc, crm, integration_hub (2 h)

Leer en detalle:
- `apps/cuentas_por_cobrar/services.py` — ¿Qué lógica ya tiene?
- `apps/crm/models.py` — ¿Cómo está definido Cliente?
- `apps/integration_hub/connectors/odoo/connector.py` — ¿Qué pull_* ya tiene?
- `apps/integration_hub/services/sync_engine.py` — ¿Cómo orquesta syncs?
- `apps/integration_hub/tasks.py` — ¿Qué Celery tasks ya hay?
- `apps/configuracion_motor/` — ¿Cómo se lee config por tenant/módulo?

**Preguntas clave:**
1. ¿El conector Odoo ya tiene `pull_facturas_venta()` con aging?
2. ¿`CuentaPorCobrar` tiene algún servicio de aging implementado?
3. ¿`ConectorInstancia` mapea empresa → Odoo creds? ¿Cómo se consulta?
4. ¿`configuracion_motor` tiene `get_config_modulo(empresa, 'cxc')`?

### Sesión 0-C · Documentar brechas (2 h)

Producir `docs/decisions/CXC-GAP-ANALYSIS.md` con:
- Lo que ya existe y se usa tal cual
- Lo que existe y necesita extensión mínima
- Lo que es genuinamente nuevo (solo en apps/cxc/)
- Orden de implementación con dependencias

---

## BLOQUE 1 — EXTENDER INTEGRATION HUB
**Duración: 1.5 semanas · ~20 h**

Todo lo que toca APIs externas vive aquí. Nunca en `apps/cxc/`.

### Sesión 1-A · Conector `tasas_ve` — BCV + Binance P2P (5 h)

```
apps/integration_hub/connectors/tasas_ve/
├── __init__.py
├── connector.py        # TasasVeConnector(BaseConnector)
├── sources/
│   ├── __init__.py
│   ├── dolarapi.py         # Fuente 1: ve.dolarapi.com
│   ├── exchangedynamic.py  # Fuente 2: api.exchangedynamic.com
│   ├── bcv_scrape.py       # Fuente 3: bcv.org.ve (SSL workaround documentado)
│   └── binance_p2p.py      # 5 BUY + 5 SELL → promedio
└── tests/
    └── test_tasas_ve.py
```

**`connector.py`** — implementa `pull_tasa_bcv()` con cascade de 3 fuentes
y `pull_tasa_binance_p2p()` con promedio 5+5.

**Cascade BCV (portado de GestionCxC):**
1. `dolarapi.py` → `https://ve.dolarapi.com/v1/dolares` (filtra fuente='bcv')
2. `exchangedynamic.py` → `https://api.exchangedynamic.com/v1/rates?base=USD&target=VES`
3. `bcv_scrape.py` → `https://www.bcv.org.ve/` con:
   - `httpx.AsyncClient(verify=False)` — SSL workaround probado en producción
   - BeautifulSoup → `div#dolar > strong`
   - Regex fallback: `r'USD[^\d]*(\d{1,3}[.,]\d{2,4})'`

**Binance P2P (portado de GestionCxC):**
- `POST https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search`
- Obtiene 5 BUY + 5 SELL → promedio de 10 precios con `Decimal`
- Persiste como tipo `PROMEDIO_MERCADO` en `finanzas.TasaCambio`

**Registrar en el registry del Hub:**
```python
# apps/integration_hub/connectors/registry.py
CONNECTOR_REGISTRY = {
    'odoo':     OdooConnector,      # ya existe
    'tasas_ve': TasasVeConnector,   # NUEVO
}
```

### Sesión 1-B · Extender conector Odoo con cartera (4 h)

Agregar métodos al conector Odoo existente:

```python
# apps/integration_hub/connectors/odoo/connector.py — AGREGAR métodos

def pull_cartera_vencida(self, desde=None, solo_vencidas=True) -> list[dict]:
    """
    Portado de GestionCxC/backend/odoo_client.py → get_ventas_extendidas()
    Devuelve dicts normalizados con keys estándar canónico Omni:
    cliente_id, cliente_nombre, orden_ref, monto_total, monto_pendiente,
    fecha_vencimiento, fecha_entrega, estado_pago, dias_termino,
    dias_vencida, vencida, bucket
    """

def pull_pagos_cliente(self, partner_id: str) -> list[dict]:
    """Pagos normalizados de un cliente específico."""

@staticmethod
def _aging_bucket(dias: int) -> str:
    if dias == 0:    return 'al_dia'
    if dias <= 30:   return '1_30'
    if dias <= 60:   return '31_60'
    if dias <= 90:   return '61_90'
    return 'mas_90'
```

**Nota sobre `_term_days_map()`:** el método de GestionCxC que extrae días numéricos
de `account.payment.term` con regex fallback cuando `nb_days=0` debe portarse
como método privado del conector Odoo, no de CxC.

### Sesión 1-C · Celery Tasks en Integration Hub (3 h)

Agregar al `apps/integration_hub/tasks.py` existente:

```python
@shared_task(name='integration_hub.sync_tasas_ve', bind=True, max_retries=3)
def sync_tasas_ve(self):
    """
    Sincroniza BCV + Binance P2P.
    Persiste en apps.finanzas.TasaCambio (modelo compartido).
    Reemplaza los APScheduler jobs de GestionCxC.
    """
    # 1. Instanciar TasasVeConnector (sin ConectorInstancia — APIs públicas)
    # 2. pull_tasa_bcv() → cascade 3 fuentes
    # 3. pull_tasa_binance_p2p()
    # 4. TasaCambio.objects.update_or_create(...) para cada resultado
    # 5. Retry si BCV falla todas las fuentes
```

**Celery Beat schedule** (agregar a la config existente):
```python
'hub-sync-tasas-bcv-manana':  crontab(hour=13, minute=0),   # 9:00 AM VE (UTC-4)
'hub-sync-tasas-bcv-tarde':   crontab(hour=19, minute=0),   # 3:00 PM VE
'hub-sync-binance-p2p':       crontab(minute='*/30'),        # cada 30 min
```

### Sesión 1-D · Sync cartera para Mode A (3 h)

```python
@shared_task(name='integration_hub.sync_cartera_odoo')
def sync_cartera_odoo(empresa_id: str):
    """
    Para tenants Mode A: refresca cache de aging desde Odoo.
    No persiste la cartera (siempre es live desde el provider).
    Solo actualiza el cache de Redis para el dashboard.
    """
    # 1. get_cartera_provider(empresa) → OdooCarteraProvider
    # 2. provider.get_partidas()
    # 3. calcular_aging(partidas)
    # 4. cache.set(f'cxc:aging:{empresa_id}', resumen, timeout=900)
```

### Sesión 1-E · Tests Hub (3 h)

- `test_cascade_bcv_fuente1_ok` — dolarapi responde → usa esa
- `test_cascade_bcv_fuente1_falla` → intenta exchangedynamic
- `test_cascade_bcv_todas_fallan` → devuelve None, task hace retry
- `test_binance_p2p_promedio` — mock 5 BUY + 5 SELL → Decimal correcto
- `test_pull_cartera_vencida_normaliza` — dict Odoo raw → keys canónicas
- `test_aging_bucket_limites` — valores 0, 1, 30, 31, 60, 61, 90, 91
- `test_sync_tasas_ve_persiste` — verifica update_or_create idempotente

---

## BLOQUE 2 — EXTENDER `apps/cuentas_por_cobrar/`
**Duración: 1 semana · ~14 h**

### Sesión 2-A · `services/aging.py` (3 h)

```python
# apps/cuentas_por_cobrar/services/aging.py

@dataclass
class PartidaCartera:
    """
    Representación canónica agnóstica al origen (Omni nativo u Odoo via Hub).
    Calcula dias_vencida, vencida y bucket automáticamente en __post_init__.
    """
    cliente_id:        str
    cliente_nombre:    str
    orden_ref:         str
    monto_total:       Decimal
    monto_pendiente:   Decimal
    fecha_vencimiento: Optional[date]
    estado_pago:       str
    # Calculados:
    dias_vencida:  int   # field(init=False)
    vencida:       bool  # field(init=False)
    bucket:        str   # field(init=False)

    @classmethod
    def from_omni(cls, cxc) -> 'PartidaCartera':
        """Construye desde CuentaPorCobrar nativo de Omni."""

    @classmethod
    def from_hub_dict(cls, d: dict) -> 'PartidaCartera':
        """Construye desde dict normalizado del Hub."""


def calcular_aging(partidas: list[PartidaCartera]) -> dict:
    """
    Resumen ejecutivo por bucket:
    {buckets: {al_dia, 1_30, 31_60, 61_90, mas_90},
     total_pendiente, total_partidas, partidas_vencidas}
    """

BUCKETS = ['al_dia', '1_30', '31_60', '61_90', 'mas_90']
```

### Sesión 2-B · `services/scoring.py` (2 h)

```python
# apps/cuentas_por_cobrar/services/scoring.py
"""
Fórmula portada de GestionCxC:
score = (dias_vencida × 3) + (monto_pendiente / 100) + (intentos_sin_respuesta × 5)
"""

@dataclass
class ScoreInput:
    dias_vencida:           int
    monto_pendiente:        Decimal
    intentos_sin_respuesta: int = 0

def calcular_score(inp: ScoreInput) -> Decimal: ...

def priorizar(partidas: list[PartidaCartera], intentos_map: dict = None) -> list[dict]:
    """
    Filtra solo vencidas, calcula score para cada una,
    devuelve lista de dicts ordenados por score DESC.
    intentos_map: {cliente_id: n_sin_respuesta}
    """
```

### Sesión 2-C · `services/cartera_provider.py` (4 h)

```python
# apps/cuentas_por_cobrar/services/cartera_provider.py
"""
Fábrica Mode A / Mode B.
CxC nunca llama al Hub ni a CuentaPorCobrar directamente.
Siempre pasa por aquí.
"""

def get_cartera_provider(empresa) -> CarteraProvider:
    """Lee config del tenant (configuracion_motor) y devuelve el provider."""
    cfg = get_config_modulo(empresa, 'cxc')
    if cfg.get('datasource') == 'odoo':
        return OdooCarteraProvider(empresa)
    return NativeCarteraProvider(empresa)


class OdooCarteraProvider(CarteraProvider):
    """
    Mode A: usa ConectorInstancia de Odoo del tenant → connector.pull_cartera_vencida()
    Nunca llama a Odoo directamente.
    """
    def get_partidas(self, solo_vencidas=False, fecha_desde=None) -> list[PartidaCartera]: ...
    def get_pagos_cliente(self, cliente_id: str) -> list[dict]: ...


class NativeCarteraProvider(CarteraProvider):
    """Mode B: consulta CuentaPorCobrar nativo de Omni."""
    def get_partidas(self, solo_vencidas=False, fecha_desde=None) -> list[PartidaCartera]: ...
    def get_pagos_cliente(self, cliente_id: str) -> list[dict]: ...
```

### Sesión 2-D · Tests cuentas_por_cobrar (3 h)

- `test_partida_from_omni` — conversión desde modelo nativo
- `test_partida_from_hub_dict` — conversión desde dict del Hub
- `test_calcular_aging_todos_buckets`
- `test_priorizar_ignora_no_vencidas`
- `test_priorizar_orden_score_desc`
- `test_get_provider_odoo` — con config `datasource: odoo`
- `test_get_provider_native` — con config `datasource: native`

---

## BLOQUE 3 — `apps/cxc/` — SOLO DOMINIO PROPIO
**Duración: 1.5 semanas · ~20 h**

### Lo que CxC NO incluye (eliminado del plan original)

| Eliminado | Ahora vive en |
|-----------|---------------|
| `TasaCambio` model | `apps/finanzas/` (ya existe) |
| `fetch_tasa_bcv()` | `integration_hub/connectors/tasas_ve/` |
| `fetch_binance_p2p()` | `integration_hub/connectors/tasas_ve/` |
| `convertir()` helper | `apps/finanzas/services.py` |
| `DatasourceRouter` | `apps/cuentas_por_cobrar/services/cartera_provider.py` |
| `PartidaCartera` dataclass | `apps/cuentas_por_cobrar/services/aging.py` |
| `calcular_score()` | `apps/cuentas_por_cobrar/services/scoring.py` |
| `PagoVE` model | `apps/finanzas/Pago` (ya existe) |
| Tasks BCV/Binance | `apps/integration_hub/tasks.py` |

### Sesión 3-A · Modelos propios de CxC (4 h)

**`GestionCobranza`** — registro de una acción de cobranza:
- `empresa` FK a `core.Empresa`
- `cliente_id` CharField (referencia flexible: Omni o externo vía Hub)
- `cxc` FK opcional a `cuentas_por_cobrar.CuentaPorCobrar` (Mode B)
- `canal`: whatsapp | email | llamada | visita | carta
- `resultado`: contactado | sin_respuesta | promesa_pago | negativa | acuerdo_logrado
- `score` Decimal calculado al guardar
- `gestionado_por` FK a `core.Usuarios`
- `deleted_at` soft delete

**`PlantillaCobranza`** — mensajes reutilizables con variables:
- Variables: `{cliente}` `{orden}` `{monto}` `{vencimiento}` `{dias_vencida}`

**`AcuerdoPago`** — acuerdo de pago en cuotas:
- `periodicidad`: unico | semanal | quincenal | mensual
- `monto_cuota` O `porcentaje_abono` (uno de los dos)
- `estado`: vigente | cumplido | roto | cancelado

**`CuotaAcuerdo`** — cuota individual del acuerdo:
- `pago` FK opcional a `finanzas.Pago` (el pago efectivo va en finanzas)
- `estado`: pendiente | pagado | parcial | vencido

### Sesión 3-B · `services/cuotas.py` — algoritmo portado (2 h)

```python
# apps/cxc/services/cuotas.py
"""
Portado de GestionCxC/backend/routers/acuerdos_pago.py → _generar_cuotas()
Sin efectos secundarios — el caller hace bulk_create en @transaction.atomic.
"""

def generar_cuotas(
    acuerdo,
    fecha_inicio:     date,
    plazo_total_dias: int,
    periodicidad:     str,       # unico | semanal | quincenal | mensual
    monto_total:      Decimal,
    monto_cuota:      Optional[Decimal] = None,
    porcentaje_abono: Optional[Decimal] = None,
) -> list[dict]:
    """
    Devuelve lista de dicts para CuotaAcuerdo.objects.bulk_create().
    - Si periodicidad='unico': 1 cuota con monto_total completo
    - Si monto_cuota: monto fijo, ajuste de redondeo en última cuota
    - Si porcentaje_abono: monto = total × %, ajuste en última
    - Si ninguno: divide total / num_cuotas, ajuste en última
    """
```

### Sesión 3-C · Fraccionamiento (feature-flagged) (4 h)

```
apps/cxc/models/fraccionamiento.py

LoteFraccionado:
  - producto_id: str (ref Odoo o Omni nativo)
  - cantidad_inicial/actual: Decimal
  - unidad_base / unidad_venta / factor_conversion
  - precio_venta_unit: Decimal
  - estado: activo | agotado | cerrado

VentaFraccionada:
  - lote FK → LoteFraccionado
  - estado: pendiente | confirmada | anulada
  - Confirmación → descuenta stock del lote en @transaction.atomic
  - El pago va a finanzas.Pago (no modelo propio)
```

**Feature flag:** solo aparece si `get_config_modulo(empresa, 'cxc').get('fraccionamiento', False)`.

### Sesión 3-D · Migración inicial + tests (4 h)

```bash
python manage.py makemigrations cxc
python manage.py migrate cxc
```

Tests obligatorios:
- Crear `GestionCobranza` → verifica UUIDv7, soft delete
- Crear `AcuerdoPago` + `generar_cuotas()` mensual 90 días → 3 cuotas, ajuste redondeo
- Crear `AcuerdoPago` periodicidad unico → 1 cuota exacta
- `CuotaAcuerdo.pago` FK a `finanzas.Pago` → guarda correctamente

---

## BLOQUE 4 — API REST (ViewSets)
**Duración: 1.5 semanas · ~20 h**

### Sesión 4-A · `CarteraDashboardView` (3 h)

```python
# apps/cxc/api/cartera.py
class CarteraDashboardView(APIView):
    """
    Dashboard de cartera. Toda la lógica la delega a cuentas_por_cobrar.services.
    CxC no implementa aging ni scoring — los consume.
    """
    def get(self, request):
        empresa   = request.user.empresa
        cache_key = f'cxc:aging:{empresa.pk}'
        resumen   = cache.get(cache_key)

        if not resumen:
            provider = get_cartera_provider(empresa)
            partidas = provider.get_partidas()
            resumen  = calcular_aging(partidas)

            # Intentos sin respuesta del historial CxC
            intentos_map = {GestionCobranza query...}
            resumen['top_prioridades'] = priorizar(partidas, intentos_map)[:10]
            cache.set(cache_key, resumen, timeout=900)

        # Tasa del día desde finanzas.TasaCambio — no duplicar
        tasa_hoy = TasaCambio.objects.filter(
            fecha_tasa=date.today(),
            tipo_tasa='OFICIAL_BCV',
            id_moneda_origen__codigo_iso='USD',
            id_moneda_destino__codigo_iso='VES',
        ).order_by('-fecha_creacion').first()
        resumen['tasa_bcv_hoy'] = str(tasa_hoy.valor_tasa) if tasa_hoy else None

        return Response(resumen)
```

### Sesión 4-B · `AcuerdoPagoViewSet` (4 h)

Endpoints:
- `POST /api/cxc/acuerdos/` → crea acuerdo + genera cuotas en `@transaction.atomic`
- `GET /api/cxc/acuerdos/{id}/` → acuerdo con `prefetch_related('cuotas')`
- `POST /api/cxc/acuerdos/{id}/registrar-pago/` →
  1. Actualiza estado de `CuotaAcuerdo`
  2. Crea `finanzas.Pago` (no duplica modelo)
  3. Linkea cuota con el pago via FK
  4. Auto-completa acuerdo si todas las cuotas = `pagado`
- `GET /api/cxc/acuerdos/vencimientos-proximos/?dias=7` → cuotas próximas

### Sesión 4-C · `GestionCobranzaViewSet` (3 h)

Endpoints:
- `POST /api/cxc/gestiones/` → crea gestión + calcula score automáticamente
- `GET /api/cxc/gestiones/prioridades/` → delega a `cuentas_por_cobrar.services.scoring.priorizar()`
- `GET /api/cxc/gestiones/agenda/?dias=7` → gestiones con próxima acción
- `GET /api/cxc/gestiones/plantillas/` → plantillas activas del tenant
- `POST /api/cxc/gestiones/{id}/preview-plantilla/` → renderiza variables en plantilla

### Sesión 4-D · Otros ViewSets (4 h)

**`PlantillaCobranzaViewSet`** — CRUD básico con scope por empresa.

**`LoteFraccionadoViewSet`** (feature-flagged):
- `POST /api/cxc/lotes/` → crea lote
- `POST /api/cxc/ventas-fraccionadas/{id}/confirmar/` → descuenta stock en `@transaction.atomic`
- `GET /api/cxc/fraccionamiento/resumen/` → KPIs: lotes_activos, ventas_mes, pendiente_cobro

### Sesión 4-E · Router central + URLs (2 h)

```python
# apps/cxc/api/router.py
router = DefaultRouter()
router.register('gestiones',             GestionCobranzaViewSet,   basename='cxc-cobranza')
router.register('acuerdos',              AcuerdoPagoViewSet,        basename='cxc-acuerdos')
router.register('plantillas-cobranza',   PlantillaCobranzaViewSet,  basename='cxc-plantillas')
router.register('lotes',                 LoteFraccionadoViewSet,    basename='cxc-lotes')
router.register('ventas-fraccionadas',   VentaFraccionadaViewSet,   basename='cxc-ventas-frac')
# Views sueltas:
# GET /api/cxc/cartera/dashboard/  → CarteraDashboardView
# POST /api/cxc/agente/             → CobranzaAgenteView (streaming)
```

En `omni/urls.py`:
```python
path('api/cxc/', include('apps.cxc.api.router')),
```

### Sesión 4-F · Tests API (4 h)

Para cada ViewSet:
- `401` sin token
- Tenant isolation: empresa A no ve datos de empresa B
- CRUD completo
- Soft delete: `DELETE` → `deleted_at` relleno, no aparece en listados
- `registrar_pago` → verifica que `finanzas.Pago` se crea correctamente
- `prioridades` → verifica orden DESC por score

---

## BLOQUE 5 — MCP SERVER (R-CODE-7)
**Duración: 1 semana · ~12 h**

### Sesión 5-A · MCP Server CxC (5 h)

```python
# apps/cxc/mcp/server.py
mcp = OmniMCPServer(name='cxc', description='Cobranza inteligente — Omni CxC')
```

**Tools implementadas:**

| Tool | Descripción | Delega a |
|------|-------------|----------|
| `get_cartera_vencida` | Cartera vencida priorizada | `cuentas_por_cobrar.services` |
| `get_aging_summary` | Resumen por bucket (con cache) | `cuentas_por_cobrar.services` |
| `get_tasa_cambio_hoy` | Tasa BCV del día | `finanzas.TasaCambio` |
| `registrar_gestion_cobranza` | Crea GestionCobranza con score | `cxc.models.cobranza` |
| `get_acuerdos_vigentes` | Acuerdos activos del cliente | `cxc.models.acuerdos` |
| `get_cuotas_proximas` | Cuotas por vencer en N días | `cxc.models.acuerdos` |

**Principio:** el MCP Server **no implementa lógica** — es bridge entre el agente y los servicios existentes. Si una tool necesita lógica de negocio, esa lógica vive en el servicio correspondiente, no en el tool.

### Sesión 5-B · Tests MCP (3 h)

- Schema de cada tool es válido
- Mock de providers para tests sin DB
- Verificar que el servidor arranca al importar el módulo
- `get_tasa_cambio_hoy` devuelve error descriptivo si no hay tasa hoy
- `get_cartera_vencida` respeta tenant isolation

---

## BLOQUE 6 — AGENTE IA DE COBRANZA
**Duración: 1 semana · ~15 h**

### Sesión 6-A · Diseño del flujo (2 h)

**Flujo del agente (herramienta: Anthropic SDK + MCP Server CxC):**

1. `get_cartera_vencida` → obtiene top N por score
2. Para cada cliente relevante: `get_acuerdos_vigentes` → ¿ya tiene acuerdo activo?
3. `get_tasa_cambio_hoy` → convierte montos si necesario
4. Genera recomendaciones por cliente usando `PlantillaCobranza` + variables reales
5. `registrar_gestion_cobranza` → persiste cada gestión recomendada
6. Devuelve resumen con plan de acción

**Reglas del sistema:**
- Priorizar score alto (más días vencida + monto + intentos sin respuesta)
- Si cliente tiene acuerdo vigente → solo seguimiento de cuotas, no nueva gestión
- Sugerir acuerdo de pago para montos > $500 con más de 30 días vencidos
- Tono profesional pero cercano, nunca amenazante
- Siempre registrar la gestión al final

### Sesión 6-B · Implementación (5 h)

```python
# apps/cxc/agents/cobranza_agent.py
import anthropic

class CobranzaAgent:
    def __init__(self, empresa_id: str, mcp_server_url: str):
        self.empresa_id     = empresa_id
        self.client         = anthropic.Anthropic()
        self.mcp_server_url = mcp_server_url

    async def analizar_cartera(self, top_n: int = 10) -> AsyncIterator[str]:
        """Análisis y recomendaciones de cobranza con streaming."""
        async with self.client.beta.messages.stream(
            model    = 'claude-opus-4-5',
            max_tokens = 4096,
            system   = SYSTEM_PROMPT,
            messages = [{'role': 'user', 'content': f'Analiza cartera tenant {self.empresa_id}...'}],
            mcp_servers = [{'type': 'url', 'url': self.mcp_server_url, 'name': 'cxc'}],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def gestionar_cliente(self, cliente_id: str, usuario_id: str,
                                 instrucciones: str = '') -> AsyncIterator[str]:
        """Gestión específica de un cliente con contexto completo."""
```

### Sesión 6-C · Endpoint de streaming (3 h)

```python
# apps/cxc/api/agente.py
class CobranzaAgenteView(APIView):
    """Server-Sent Events para el agente de cobranza."""
    def post(self, request):
        # Retorna StreamingHttpResponse con content_type='text/event-stream'
        # Acciones: 'analizar_cartera' | 'gestionar_cliente'
```

### Sesión 6-D · Tests agente (2 h)

Solo mocks — no llamadas reales a Anthropic:
- Mock del streaming → verifica que SSE se formatea correctamente
- Mock de tools MCP → verifica que el agente las llama en orden esperado

---

## BLOQUE 7 — FRONTEND (React + TypeScript + MUI v7)
**Duración: 3 semanas · ~40 h**

### Estructura de componentes

```
apps/cxc/frontend/
├── index.ts                         # exports para router de Omni
├── routes.ts                        # rutas del módulo
├── pages/
│   ├── DashboardCxCPage.tsx         # KPIs + aging chart + top prioridades
│   ├── CarteraPage.tsx              # Lista completa + filtros
│   ├── CobranzaPage.tsx             # CRM cobranza (gestiones + agenda)
│   ├── AcuerdosPage.tsx             # Acuerdos + cuotas timeline
│   └── FraccionamientoPage.tsx      # Módulo fraccionamiento (feature-flagged)
├── components/
│   ├── aging/
│   │   ├── AgingChart.tsx           # Gráfico barras por bucket
│   │   └── AgingTable.tsx           # Tabla con colores semáforo
│   ├── cobranza/
│   │   ├── GestionForm.tsx          # Formulario nueva gestión
│   │   ├── AgendaView.tsx           # Vista agenda/próximas acciones
│   │   ├── PlantillaSelector.tsx    # Selector con preview de plantilla
│   │   └── PrioridadesTable.tsx     # Top clientes por score
│   ├── acuerdos/
│   │   ├── AcuerdoWizard.tsx        # Wizard 3 pasos (MUI Stepper)
│   │   ├── CuotasTimeline.tsx       # Timeline visual de cuotas
│   │   └── PagoModal.tsx            # Modal registro de pago
│   ├── agente/
│   │   ├── AgenteCobranzaChat.tsx   # Chat streaming SSE con el agente
│   │   └── RecomendacionCard.tsx
│   └── shared/
│       ├── MonedaDisplay.tsx        # Muestra USD + VES equivalente
│       └── TasaWidget.tsx           # Widget tasa del día (usa finanzas API)
├── hooks/
│   ├── useTasaHoy.ts                # SWR → GET /api/finanzas/tasas/ (NO /api/cxc/)
│   ├── useCartera.ts                # SWR → GET /api/cxc/cartera/dashboard/
│   ├── useAcuerdos.ts               # SWR → GET /api/cxc/acuerdos/
│   └── useAgenteStream.ts           # SSE → POST /api/cxc/agente/
└── api/
    └── cxcClient.ts                 # Axios instance para /api/cxc/
```

### Sesión 7-A · DashboardCxCPage + AgingChart (4 h)

Grid MUI v7 con:
- 4 KPI cards (total pendiente, partidas vencidas, tasa BCV, más 90 días)
- `AgingChart` — gráfico de barras con Recharts o MUI Charts
- `PrioridadesTable` — top 10 clientes por score con columnas: cliente, monto, días, score, acción rápida

**Importante:** `useTasaHoy` apunta a `/api/finanzas/tasas/` (endpoint existente de finanzas),
no a un endpoint propio de CxC.

### Sesión 7-B · CobranzaPage + GestionForm (5 h)

`GestionForm` (React Hook Form + MUI):
- Selector de canal (whatsapp, email, llamada, visita, carta)
- Selector de resultado
- `PlantillaSelector` → carga plantillas, muestra preview con variables del cliente al hacer hover
- Campo `proxima_accion` (DatePicker) solo visible si resultado = `promesa_pago`
- Al guardar → POST `/api/cxc/gestiones/` + invalida cache de prioridades

### Sesión 7-C · AcuerdosPage + Wizard (5 h)

**Wizard 3 pasos (MUI Stepper):**
1. **Datos básicos:** cliente (autocomplete), monto, orden referencia
2. **Estructura de pago:** periodicidad, plazo, monto_cuota vs porcentaje_abono
3. **Resumen + Preview cuotas:** tabla de cuotas calculadas en el frontend (TypeScript port de `generar_cuotas`) antes de confirmar

```typescript
// Función TypeScript que replica generar_cuotas() para preview instantáneo
// Sin llamada al backend — solo para mostrar antes de confirmar
function calcularCuotasPreview(params: CuotasParams): CuotaPreview[]
```

`CuotasTimeline` — MUI Timeline con color por estado:
- pendiente → gris
- pagado → verde
- vencido → rojo
- parcial → amarillo

### Sesión 7-D · AgenteCobranzaChat (4 h)

```tsx
// SSE streaming con EventSource
// Botones: "Analizar Cartera" | "Gestionar Cliente"
// Mientras streaming → CircularProgress + texto parcial acumulándose
// Historial de mensajes en Paper scrollable
```

### Sesión 7-E · Tests frontend (5 h)

- Vitest + Testing Library
- MSW para mockear API
- `AgingChart` renderiza con datos vacíos
- `GestionForm` muestra `proxima_accion` solo cuando resultado = `promesa_pago`
- `AcuerdoWizard` navega correctamente entre 3 pasos
- `calcularCuotasPreview` — valores conocidos → cuotas correctas con ajuste redondeo
- `useTasaHoy` — SWR apunta a `/api/finanzas/tasas/`

---

## BLOQUE 8 — CONFIG DSL POR TENANT
**Duración: 0.5 semanas · ~8 h**

### Sesión 8-A · Esquema DSL para CxC (3 h)

Usando el sistema `configuracion_motor` existente en Omni:

```yaml
# Config de un tenant Mode A (Odoo via Hub)
modules:
  cxc:
    enabled: true
    datasource: odoo           # "odoo" | "native"
    cobranza:
      canales: [whatsapp, email, llamada]
      agente_ia: true
    tasas:
      moneda_display: USD
    acuerdos_pago:
      max_plazo_dias: 365
      periodicidades: [semanal, quincenal, mensual, unico]
    fraccionamiento:
      enabled: false           # feature flag

# Config de un tenant Mode B (Omni nativo)
modules:
  cxc:
    enabled: true
    datasource: native
    cobranza:
      agente_ia: false
    fraccionamiento:
      enabled: true
```

### Sesión 8-B · Validación + tests (2 h)

- Pydantic schema para validar el DSL de CxC
- Test que `datasource: odoo` activa `OdooCarteraProvider`
- Test que `datasource: native` activa `NativeCarteraProvider`
- Test que fraccionamiento no aparece en UI si `enabled: false`

---

## BLOQUE 9 — HARDENING + PRODUCCIÓN
**Duración: 1 semana · ~15 h**

### Sesión 9-A · R-CODE-11 (AsientoContable) (4 h)

Todo movimiento con impacto contable genera `AsientoContable` en la misma `@transaction.atomic`.

Aplica a:
- `registrar_pago` en `AcuerdoPagoViewSet` → pago de cuota → asiento contable
- `confirmar` en `VentaFraccionadaViewSet` → venta confirmada → asiento contable
- `aplicar` en nota de crédito → asiento de ajuste

```python
# En cada operación con impacto contable:
with transaction.atomic():
    pago = Pago.objects.create(...)
    from apps.contabilidad.services.asientos import crear_asiento
    crear_asiento(
        id_empresa       = empresa,
        concepto         = f'Cuota acuerdo pago - {acuerdo.cliente_nombre}',
        lineas           = [...],
        referencia_tipo  = 'CuotaAcuerdo',
        referencia_id    = str(cuota.id),
        usuario_id       = str(usuario.id),
    )
```

### Sesión 9-B · Rate limiting + seguridad (2 h)

- Rate limiting endpoint agente IA: máx 10 llamadas/hora por tenant
- Validar que `empresa` del JWT coincide con datos accedidos en CADA ViewSet
- No exponer `cliente_id` de otros tenants vía filtros
- Rate limiting en trigger manual de tasas: 2x/día máximo

### Sesión 9-C · Performance + índices (2 h)

Índices compuestos para queries frecuentes:
```python
# En GestionCobranza.Meta.indexes:
models.Index(fields=['empresa', 'cliente_id'])
models.Index(fields=['empresa', 'proxima_accion'])
models.Index(fields=['empresa', 'resultado', 'fecha_gestion'])

# En CuotaAcuerdo.Meta.indexes:
models.Index(fields=['acuerdo__empresa', 'fecha_vencimiento', 'estado'])
```

### Sesión 9-D · Observabilidad (2 h)

Structured logging con `structlog` para operaciones críticas:
```python
logger.info('gestion_registrada',
    empresa=str(empresa.pk),
    cliente_id=gestion.cliente_id,
    canal=gestion.canal,
    resultado=gestion.resultado,
    score=str(gestion.score),
)
```

Health check: `GET /api/cxc/health/` → verifica DB, Hub, cache, tasa_hoy.

### Sesión 9-E · Documentación técnica (2 h)

- Docstrings en todos los servicios
- OpenAPI auto-generado (DRF Spectacular si aplica)
- `CHANGELOG.md` del módulo con versión `1.0.0`

---

## BLOQUE 10 — MIGRACIÓN DE DATOS + ONBOARDING
**Duración: 0.5 semanas · ~8 h**

### Sesión 10-A · Script de migración GestionCxC → Omni (3 h)

Script one-time para el cliente en producción de GestionCxC:

```python
# scripts/migrate_gestioncxc_to_omni.py
"""
Migra datos de GestionCxC (PostgreSQL/SQLite) a Omni CxC.
Tablas migradas:
- tasas_cambio → finanzas.TasaCambio (históricas)
- cobranza_gestiones → cxc.GestionCobranza
- acuerdos_pago → cxc.AcuerdoPago
- acuerdos_pago_cuotas → cxc.CuotaAcuerdo
- cobranza_plantillas → cxc.PlantillaCobranza
"""
```

### Sesión 10-B · Onboarding checklist + smoke tests (3 h)

```
Checklist de activación por tenant:
□ DSL YAML configurado (datasource + módulos)
□ ConectorInstancia de Odoo activa (si Mode A)
□ Primera sync de tasas exitosa (BCV + Binance)
□ Primera sync de cartera exitosa (Mode A)
□ Dashboard CxC carga sin errores
□ Gestión de cobranza de prueba registrada
□ Acuerdo de pago de prueba + cuotas generadas
□ Pago de cuota registrado → finanzas.Pago creado
□ Agente IA responde correctamente (si habilitado)
□ MCP Server responde a get_cartera_vencida
```

### Sesión 10-C · Monitoreo post-deploy (2 h)

- Alertas Sentry para exceptions en tasks Celery de CxC/Hub
- Alertas si `sync_tasas_ve` falla más de 2 veces consecutivas
- Dashboard Celery Beat: verificar que tasks corren en horario

---

## RESUMEN EJECUTIVO

| Bloque | Contenido | Código en | Horas |
|--------|-----------|-----------|-------|
| 0 | Auditoría estado real de Omni | Lectura | 6 h |
| 1 | Hub: conector `tasas_ve` + extensión Odoo + tasks | `integration_hub/` | 20 h |
| 2 | Extender `cuentas_por_cobrar` (aging, scoring, provider) | `cuentas_por_cobrar/` | 14 h |
| 3 | Modelos propios CxC + `generar_cuotas()` + migraciones | `cxc/` | 20 h |
| 4 | ViewSets CxC (consumen servicios compartidos) | `cxc/api/` | 20 h |
| 5 | MCP Server CxC (R-CODE-7) | `cxc/mcp/` | 12 h |
| 6 | Agente IA cobranza (Anthropic SDK + streaming) | `cxc/agents/` | 15 h |
| 7 | Frontend React + TypeScript + MUI v7 | `frontend/` | 40 h |
| 8 | DSL config por tenant | `configuracion_motor/` | 8 h |
| 9 | Hardening: R-CODE-11, perf, observabilidad | Transversal | 15 h |
| 10 | Migración GestionCxC → Omni + onboarding | `scripts/` | 8 h |
| **Total** | | | **~178 h** |

**A 15 h/semana → ~12 semanas · A 25 h/semana → ~7 semanas**

---

## PRIORIDAD DE EJECUCIÓN (Si hay que ajustar scope)

### MVP (primeras 7 semanas)
Bloques 0 → 1 → 2 → 3 → 4 (solo Cartera + Cobranza + Acuerdos) → 7 (solo Dashboard + Cobranza + Acuerdos)

### Valor diferencial (semanas 7-10)
Bloque 5 (MCP) + Bloque 6 (Agente IA) — aquí está el moat vs. GestionCxC

### Completitud (semanas 10-12)
Bloque 7 completo (Fraccionamiento) + Bloque 8 + Bloque 9 + Bloque 10

---

## DEPENDENCIAS TÉCNICAS CON OMNI (CONFIRMAR EN BLOQUE 0)

| Necesidad | Dónde en Omni | Acción |
|-----------|--------------|--------|
| `OmniMCPServer` base class | `core/mcp/base.py` | Verificar que existe y tiene API pública |
| `ConectorInstancia` por tenant | `integration_hub/models.py` | Verificar cómo se consulta por empresa + proveedor |
| `crear_asiento()` (R-CODE-11) | `apps/contabilidad/services/` | Verificar API pública del servicio |
| `get_config_modulo(empresa, 'cxc')` | `apps/configuracion_motor/` | Verificar si existe o crear wrapper |
| `request.user.empresa` en DRF | Middleware de Omni | Verificar que está inyectado en el JWT/middleware |
| `uuid7` utility | `apps/core/uuid.py` | Confirmado — ya se usa en finanzas |
| Storage comprobantes | `core/storage` | Verificar si es S3 o local, y cómo usar |
| Celery Beat config existente | `config/celery_beat.py` | Verificar formato y cómo agregar tasks |
| `finanzas.Pago.tipo_documento` | `apps/finanzas/models.py` | Verificar qué valor usar para abonos CxC |

---

## REFERENCIAS

- `GestionCxC/backend/odoo_client.py` — lógica portada a `integration_hub/connectors/odoo/`
- `GestionCxC/backend/services/tasas_cambio.py` — portada a `integration_hub/connectors/tasas_ve/`
- `GestionCxC/backend/services/binance_p2p.py` — portada a `integration_hub/connectors/tasas_ve/sources/binance_p2p.py`
- `GestionCxC/backend/routers/cobranza.py` — score formula portada a `cuentas_por_cobrar/services/scoring.py`
- `GestionCxC/backend/routers/acuerdos_pago.py` — `_generar_cuotas()` portado a `cxc/services/cuotas.py`
- ADR-002: Arquitectura modular y estrategia wedge
- ADR-003: Integration Hub centralizado con MCP bidireccional
- ADR-006: Asientos contables automáticos (R-CODE-11)

---

## CHANGELOG

### v1.0 — 2026-05-28
- Plan inicial elaborado en sesión de análisis comparativo GestionCxC vs Omni.
- Corrección arquitectural crítica: eliminada toda duplicación de infraestructura.
- Toda conexión externa redirigida a Integration Hub.
- Aging, scoring y cartera_provider movidos a `apps/cuentas_por_cobrar/`.
- `apps/cxc/` limitado al dominio exclusivo de cobranza.
