# App `servicio_cliente`

Servicio al cliente / mesa de ayuda: tickets de soporte con sus interacciones, base de conocimiento y feedback de clientes (satisfacción, quejas, sugerencias).

**Prefijo API:** `/api/servicio-cliente/`

## Modelos

| Modelo | Descripción |
|---|---|
| `CategoriaTicket` | Categoría de ticket. |
| `TicketSoporte` | Ticket de soporte. |
| `InteraccionTicket` | Interacción/mensaje dentro de un ticket. |
| `BaseConocimientoArticulo` | Artículo de la base de conocimiento. |
| `FeedbackCliente` | Feedback del cliente (satisfacción/queja/sugerencia). |

## Endpoints

Recursos REST (CRUD vía router): `categorias-ticket/`, `tickets-soporte/`, `interacciones-ticket/`, `articulos-conocimiento/`, `feedback-cliente/`.

Acciones personalizadas destacadas:

| Ruta | Descripción |
|---|---|
| `GET tickets-soporte/abiertos/` · `por-prioridad/` · `dashboard/` | Vistas operativas de tickets. |
| `POST tickets-soporte/{id}/asignar-agente/` · `cambiar-estado/` · `escalar/` | Operaciones sobre el ticket. |
| `GET categorias-ticket/activas/` · `{id}/estadisticas/` | Categorías activas y sus estadísticas. |
| `POST interacciones-ticket/agregar-comentario/` | Agregar comentario a un ticket. |
| `GET articulos-conocimiento/publicos/` · `buscar/` · `POST {id}/actualizar-revision/` | Base de conocimiento: público, búsqueda, revisión. |
| `GET feedback-cliente/estadisticas-satisfaccion/` · `por-tipo/` · `quejas-sugerencias/` | Reportes de feedback. |
