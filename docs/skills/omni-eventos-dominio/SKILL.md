---
name: omni-eventos-dominio
description: Use this skill whenever you emit, consume, or modify domain events in the Omni project. Triggers include any task that creates or changes a business state worth broadcasting (pedido confirmado, factura emitida, stock bajo, pago registrado, CxC vencida), any work touching `apps/core/events.py`, `apps/eventos/`, a module's `events.py`, calls to `build_event()`/`publish()`, event catalogs (`VentasEvents`, `CobranzaEvents`, etc.), or Kafka/Redpanda topics. Apply it whenever a service finishes a meaningful business action and other parts of the system (agentes, notificaciones, integraciones) might need to react. Do NOT use for pure CRUD with no business meaning, frontend work, or infra/CI changes.
---

# Skill: Eventos de Dominio (Event Store AI-nativo)

## Cuándo usar esta skill

Cargá esta skill cuando:
- Una operación de negocio cambia un estado relevante (pedido confirmado, factura emitida, pago registrado, stock bajo, CxC vencida).
- Vas a emitir un evento desde un `service` o `signal`.
- Agregás un evento nuevo a un catálogo (`VentasEvents`, `CobranzaEvents`, …).
- Escribís un consumidor de eventos en `apps/eventos/consumers.py`.

No la cargués para CRUD sin significado de negocio, frontend, o infra.

## Por qué los eventos son una primitiva AI-nativa

Omni es **AI-nativo**: los agentes, notificaciones e integraciones reaccionan a lo que pasa en el negocio. El event store es el canal que lo hace posible. Un evento bien emitido hoy habilita un agente o una automatización mañana **sin tocar el código que lo emitió**.

El event store usa **Redpanda** (Kafka-compatible). En dev sin broker opera en **modo stub** (loguea y sigue). La pieza vive en `apps/core/events.py`.

## La regla de oro

**El event store NUNCA rompe la transacción de negocio.**

`publish()` ya está diseñado para no fallar: si no hay broker o la publicación falla, loguea y retorna el sobre. **No envuelvas tu lógica de negocio en un try/except por culpa de los eventos, ni hagas que el éxito del evento sea condición del éxito de la operación.**

## Convención de nombres (topics)

```
omni.{modulo}.{entidad}.{accion}
```

Ejemplos: `omni.ventas.pedido.confirmado`, `omni.inventario.movimiento.registrado`, `omni.cobranza.cxc.vencida`. La acción va en **participio pasado** (algo que **ya ocurrió**): `creada`, `confirmado`, `emitida`, `registrado`. Un evento describe un hecho consumado, no una orden.

## Estructura canónica del evento

`build_event()` arma el sobre; nunca lo construyas a mano:

```python
{
    "event_id":       "<uuid>",
    "event_type":     "omni.ventas.pedido.confirmado",
    "schema_version": "1.0",
    "occurred_at":    "<ISO8601 UTC>",
    "tenant_id":      "<id_empresa>",   # SIEMPRE el id de la empresa (multi-tenant)
    "actor_id":       "<id_usuario | 'system'>",
    "payload":        { ... },          # datos del evento
    "metadata":       { ... },          # trace_id, request_id, contexto
}
```

## Patrón correcto: emitir desde un service

Centralizá la emisión en un helper del módulo (`apps/<modulo>/events.py`) que envuelve `publish()` con el catálogo y el payload correctos. El service llama al helper:

```python
# apps/ventas/events.py
from apps.core.events import publish, VentasEvents

def emitir_pedido_confirmado(pedido) -> None:
    publish(
        event_type=VentasEvents.PEDIDO_CONFIRMADO,
        tenant_id=str(pedido.id_empresa_id),          # nunca omitir el tenant
        actor_id=str(getattr(pedido, "id_usuario_confirmacion_id", "system")),
        payload={
            "id_pedido": str(pedido.id_pedido),
            "numero_pedido": pedido.numero_pedido,
            "id_cliente": str(pedido.id_cliente_id),
            "total": str(pedido.total),               # Decimal → str, nunca float
        },
    )
```

```python
# apps/ventas/services.py
@transaction.atomic
def confirmar_pedido(empresa, usuario, pedido_id):
    pedido = Pedido.objects.select_for_update().get(pk=pedido_id, id_empresa=empresa)
    pedido.estado = "APROBADO"
    pedido.save(update_fields=["estado"])
    # ... lógica de negocio (stock, asiento contable, etc.) ...
    emitir_pedido_confirmado(pedido)   # al final, después de que la operación es válida
    return pedido
```

### ¿Dónde emitir: dentro o fuera de la `@transaction.atomic`?

- Emití **después** de que el estado de negocio quedó válido (idealmente como última línea del service).
- Como `publish()` nunca lanza, ubicarlo dentro de la transacción es seguro. Pero conceptualmente un evento anuncia un hecho **ya consumado**: si la transacción puede revertirse después del `publish`, preferí emitir justo antes del `return`, cuando ya no queda lógica que pueda fallar.

## Payload: qué incluir y qué no

| Incluir | NO incluir |
|---|---|
| IDs (`id_pedido`, `id_cliente`) como `str` | Objetos Django enteros |
| Montos como `str` de Decimal | `float` (pierde precisión) |
| Campos mínimos que un consumidor necesita | Secretos, tokens, datos sensibles (R-CODE-8) |
| `tenant_id` siempre | Datos cross-tenant |

El consumidor que necesite más datos los busca por ID **filtrando por `tenant_id`**.

## Catálogos de eventos

Centralizá los nombres en clases del catálogo para evitar typos y permitir búsqueda. Viven en `apps/core/events.py`:

```python
class VentasEvents:
    PEDIDO_CREADO = "omni.ventas.pedido.creado"
    PEDIDO_CONFIRMADO = "omni.ventas.pedido.confirmado"
    FACTURA_EMITIDA = "omni.ventas.factura.emitida"
```

Al crear un evento nuevo: agregalo al catálogo del módulo, nunca pases el string crudo a `publish()`.

## Anti-patrones

### Anti-patrón 1: hacer fallar la operación por el evento
```python
# MAL
try:
    confirmar_pedido(...)
    publish(...)   # si esto fallara, el pedido ya está confirmado pero "falla" la request
except Exception:
    raise

# BIEN — publish() ya es seguro; no lo trates como crítico
confirmar_pedido(...)   # incluye la emisión adentro
```

### Anti-patrón 2: omitir el tenant_id
```python
# MAL — evento sin contexto multi-tenant; inservible y peligroso
publish(event_type=..., tenant_id="", payload=...)

# BIEN
publish(event_type=..., tenant_id=str(obj.id_empresa_id), payload=...)
```

### Anti-patrón 3: float o secretos en el payload
```python
# MAL
payload={"total": float(factura.total), "token_pago": token}

# BIEN
payload={"total": str(factura.total)}   # Decimal→str; sin secretos (R-CODE-8)
```

### Anti-patrón 4: string crudo en vez del catálogo
```python
# MAL
publish(event_type="omni.ventas.pedido.confirmado", ...)   # typo silencioso

# BIEN
publish(event_type=VentasEvents.PEDIDO_CONFIRMADO, ...)
```

### Anti-patrón 5: evento en tiempo imperativo
```python
# MAL — suena a orden, no a hecho
"omni.ventas.pedido.confirmar"

# BIEN — participio: el hecho ya ocurrió
"omni.ventas.pedido.confirmado"
```

## Tests

Como `publish()` retorna el sobre, es fácil de testear sin broker:

```python
def test_confirmar_pedido_emite_evento(self):
    with mock.patch("apps.ventas.events.publish") as pub:
        confirmar_pedido(self.empresa, self.user, self.pedido.pk)
    pub.assert_called_once()
    kwargs = pub.call_args.kwargs
    assert kwargs["event_type"] == VentasEvents.PEDIDO_CONFIRMADO
    assert kwargs["tenant_id"] == str(self.empresa.id_empresa)
```

## Checklist final

- [ ] El `event_type` viene de un catálogo, no es string crudo.
- [ ] El nombre sigue `omni.{modulo}.{entidad}.{accion}` con la acción en participio.
- [ ] `tenant_id` es el `id_empresa`, siempre presente.
- [ ] El payload tiene IDs como `str`, montos como `str` de Decimal, sin `float`.
- [ ] El payload no contiene secretos ni datos cross-tenant (R-CODE-8).
- [ ] La emisión no condiciona el éxito de la operación de negocio.
- [ ] Hay test que verifica que el evento se emite con el tipo y tenant correctos.

## Referencias

- Código: `apps/core/events.py` (`build_event`, `publish`, catálogos), `apps/eventos/`.
- Skill: `omni-multi-tenant-isolation` (tenant_id), `omni-decimal-money` (montos), `omni-agentes-autonomia` (consumidores típicos).
- Plan Maestro §3.5 (primitivas AI-nativas).

## Changelog

### v1.0
- Versión inicial, basada en `apps/core/events.py`.
