---
name: omni-integration-hub
description: Use this skill whenever you connect Omni to any external system or fetch data from an external API/service. Triggers include any need to call an external HTTP API (BCV/Binance rates, Odoo, banks, WhatsApp, payment gateways), write or modify a connector under `apps/integration_hub/connectors/`, use the `SyncEngine`, normalize external data to a canonical form, or implement ADR-003 (single integration point, no direct HTTP from business modules). Apply it whenever you are tempted to write `requests.get(...)` inside a business module. Do NOT use for internal-only logic, REST/MCP tools exposing Omni's own data, or frontend.
---

# Skill: Integration Hub — Punto Único de Integración Externa (ADR-003)

## Cuándo usar esta skill

Cargá esta skill cuando Omni necesita **hablar con un sistema externo**:
- Obtener tasas (BCV cascade, Binance P2P) — conector `tasas_ve`.
- Sincronizar con Odoo (XML-RPC).
- Bancos, pasarelas de pago, WhatsApp, cualquier API de terceros.

No la cargués para lógica interna, ni para tools REST/MCP que exponen datos propios de Omni (eso es `omni-mcp-capacidades`).

## La regla inviolable de integración

> **Ninguna app de negocio llama HTTP directo a una API externa.** Toda conexión externa pasa por el `apps/integration_hub` (ADR-003).

Si estás por escribir `requests.get("https://...")` o `xmlrpc.client.ServerProxy(...)` dentro de `apps/ventas`, `apps/finanzas`, `apps/cxc`, etc. — **pará**. Eso va en un conector del Hub.

## Por qué un punto único

- **Un solo lugar** para credenciales, reintentos, rate limiting, manejo de fallos y logging de integraciones.
- **Normalización canónica:** los datos externos se traducen a una forma única que el resto del sistema entiende, sin acoplar los módulos a la forma de cada proveedor.
- **Resiliencia:** fallos de un proveedor (timeout, SSL, formato) se manejan en el Hub (cascade/fallback) sin tumbar la operación de negocio.
- **Auditabilidad:** toda llamada externa queda registrada en un solo subsistema.

## Estructura

```
apps/integration_hub/
├── connectors/
│   ├── base.py        # contrato base de conector
│   ├── registry.py    # registro/descubrimiento de conectores
│   ├── odoo/          # conector Odoo (XML-RPC, todas las versiones)
│   └── tasas_ve/      # conector de tasas VE (BCV cascade + Binance P2P)
├── services/
│   └── sync_engine.py # SyncEngine: orquesta sincronizaciones
├── mcp.py             # capacidades MCP del Hub
├── models.py          # config de conexiones, logs de sync, checksums
└── tasks.py           # Celery tasks de sincronización
```

## Patrón: consumir una integración desde negocio

El módulo de negocio pide al Hub, no a la API:

```python
# apps/finanzas/services.py  (CORRECTO)
from apps.integration_hub.connectors.registry import get_connector

def actualizar_tasa_bcv(empresa):
    connector = get_connector("tasas_ve")          # el Hub conoce la API, no finanzas
    tasa = connector.obtener_tasa(origen="USD", destino="VES", fuente="BCV")
    # tasa ya viene normalizada (Decimal); persistir snapshot (ver omni-multimoneda-tasas)
    return tasa
```

A término, las tasas se piden a través del puerto `ProveedorTasas` de la localización (ver `omni-localizacion-l10n`), que internamente usa el conector del Hub.

## Patrón: escribir un conector

Un conector hereda del contrato base, encapsula la API externa y **devuelve datos canónicos** (Decimal para dinero/tasas, tipos del dominio, no JSON crudo del proveedor):

```python
# apps/integration_hub/connectors/<proveedor>/connector.py
from decimal import Decimal
from apps.integration_hub.connectors.base import BaseConnector

class MiProveedorConnector(BaseConnector):
    nombre = "mi_proveedor"

    def obtener_algo(self, **kwargs) -> dict:
        try:
            raw = self._http_get("/endpoint", params=kwargs)   # HTTP encapsulado aquí
        except Exception as exc:
            self._log_fallo(exc)        # el Hub maneja el fallo; no revienta el negocio
            return self._fallback(**kwargs)
        return self._normalizar(raw)    # → forma canónica

    @staticmethod
    def _normalizar(raw) -> dict:
        return {"valor": Decimal(str(raw["value"]))}   # Decimal vía string, nunca float
```

### Cascade / fallback

Patrón clave del conector `tasas_ve`: varias fuentes en cascada (dolarapi → exchangedynamic → scrape con workaround SSL). Si una falla, se intenta la siguiente; solo si todas fallan se reporta error. **Implementá el fallback en el conector**, no en el módulo de negocio.

## SyncEngine

Para sincronizaciones grandes (Odoo), `services/sync_engine.py` orquesta:
- Pull/push con normalización canónica.
- **Checksum incremental:** solo procesa lo que cambió.
- Se dispara vía Celery tasks (`tasks.py`), que reciben `empresa_id` (multi-tenant).

No reimplementes sincronización a mano: usá el SyncEngine.

## Multi-tenant y secretos

- Las credenciales de integración viven en config del Hub / variables de entorno, **nunca en código ni en logs** (R-CODE-8).
- Las tasks de sync reciben `empresa_id` y operan dentro de esa empresa (ver `omni-multi-tenant-isolation`).
- Los logs de integración no exponen tokens ni payloads sensibles.

## Anti-patrones

### Anti-patrón 1: HTTP directo desde negocio
```python
# MAL — apps/finanzas llama la API directamente
import requests
tasa = requests.get("https://ve.dolarapi.com/...").json()["promedio"]

# BIEN — pasa por el Hub
tasa = get_connector("tasas_ve").obtener_tasa(origen="USD", destino="VES")
```

### Anti-patrón 2: devolver JSON crudo del proveedor
```python
# MAL — el módulo de negocio queda acoplado a la forma de la API externa
return raw_response.json()

# BIEN — normalizar a forma canónica (Decimal, tipos del dominio)
return {"valor": Decimal(str(raw["value"]))}
```

### Anti-patrón 3: float en montos/tasas externas
```python
# MAL
return float(raw["rate"])
# BIEN
return Decimal(str(raw["rate"]))
```

### Anti-patrón 4: manejar el fallo en el módulo de negocio
```python
# MAL — try/except de red dentro de apps/finanzas
# BIEN — el conector implementa cascade/fallback y reporta un resultado limpio
```

### Anti-patrón 5: credenciales en código o logs
```python
# MAL — api_key="sk-..." hardcodeado, o logueado en el sync
# BIEN — credenciales en env/config del Hub; logs sin secretos (R-CODE-8)
```

## Checklist final

- [ ] Ninguna app de negocio hace HTTP/XML-RPC directo a un externo.
- [ ] La integración nueva es un conector bajo `apps/integration_hub/connectors/`.
- [ ] El conector devuelve datos canónicos (Decimal para dinero/tasas, vía string).
- [ ] Fallos y fallback (cascade) se manejan dentro del conector.
- [ ] Sincronizaciones grandes usan el SyncEngine con checksum incremental.
- [ ] Tasks de sync reciben `empresa_id`; multi-tenant respetado.
- [ ] Credenciales en env/config, nunca en código ni logs (R-CODE-8).

## Referencias

- Código: `apps/integration_hub/connectors/` (`base.py`, `registry.py`, `odoo/`, `tasas_ve/`), `apps/integration_hub/services/sync_engine.py`, `apps/integration_hub/mcp.py`.
- Skill: `omni-multimoneda-tasas`, `omni-localizacion-l10n`, `omni-mcp-capacidades`, `omni-multi-tenant-isolation`.
- ADR-003 (Integration Hub centralizado con MCP), Plan Maestro §3.5.

## Changelog

### v1.0
- Versión inicial, basada en `apps/integration_hub/`.
