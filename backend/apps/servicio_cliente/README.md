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
| `POST tickets-soporte/agregar-comentario/` | Agregar comentario. |
| `GET articulos-conocimiento/publicos/` · `buscar/` | Base de conocimiento pública / búsqueda. |
| `GET feedback-cliente/estadisticas-satisfaccion/` · `por-tipo/` · `quejas-sugerencias/` | Reportes de feedback. |
| `POST feedback-cliente/{id}/actualizar-revision/` | Actualizar revisión de feedback. |
