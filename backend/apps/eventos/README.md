# App `eventos`

Event store / bus de eventos del sistema sobre Kafka/Redpanda. Permite publicar eventos de dominio (pedido creado, factura creada, pago registrado, etc.) y consumirlos de forma desacoplada. Habilita la arquitectura orientada a eventos entre módulos.

**App de infraestructura — sin router HTTP** (no se monta en `config/urls.py`).

## Componentes

| Archivo | Rol |
|---|---|
| `producer.py` | Publicación de eventos: `publicar_evento(...)`, derivación de topic, broker config. |
| `consumers.py` | Consumidor: `run_consumer(...)`, registro de handlers (`register_handler`) y procesamiento de mensajes. |
| `schemas.py` | Esquemas (payloads) de eventos: `EventoBase`, `PedidoCreadoPayload`, `PedidoActualizadoPayload`, `FacturaCreadaPayload`, `MovimientoCreadoPayload`, `PagoRegistradoPayload`. |
| `signals.py` | Señales Django que disparan publicación de eventos. |
| `management/` | Comandos de gestión (p. ej. arrancar el consumidor). |

## Eventos definidos

`pedido.creado`, `pedido.actualizado`, `factura.creada`, `movimiento.creado`, `pago.registrado` (ver handlers en `consumers.py`).
