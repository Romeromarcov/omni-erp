# App `crm`

Gestión de clientes: el maestro de clientes, sus contactos y direcciones. Punto de entrada de la relación comercial; alimenta ventas, CxC y cobranza.

**Prefijo API:** `/api/crm/`

## Modelos

| Modelo | Descripción |
|---|---|
| `Cliente` | Maestro de cliente (RIF/cédula, crédito, datos fiscales). |
| `ContactoCliente` | Contactos del cliente. |
| `DireccionCliente` | Direcciones (facturación/entrega). |
| `Pipeline` | Embudo de ventas configurable por empresa. |
| `Etapa` | Etapas ordenadas de cada pipeline (`ABIERTA`, `GANADA`, `PERDIDA`). |
| `Lead` | Prospectos capturados (NFC, QR, enlace, manual, importación). |
| `Actividad` | Actividades comerciales de seguimiento sobre leads (llamada, correo, reunión, nota, WhatsApp). |

## Endpoints

Recursos REST (CRUD vía router): `clientes/`, `contactos-cliente/`, `direcciones-cliente/`, `pipelines/`, `etapas/`, `leads/`, `actividades/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET clientes/buscar-por-rif/` | Buscar cliente por RIF. |
| `GET clientes/{id}/historial-ventas/` | Historial de ventas del cliente. |
| `GET clientes/{id}/credito-disponible/` | Crédito disponible del cliente. |
| `POST pipelines/asegurar-predeterminado/` | Obtiene o inicializa el pipeline predeterminado con sus etapas base. |
| `POST pipelines/{id}/reordenar-etapas/` | Reordena atómicamente las etapas activas del pipeline. |
| `POST leads/{id}/mover-etapa/` | Mueve el lead a otra etapa dentro de su pipeline. |
| `POST actividades/{id}/completar/` | Marca o reabre una actividad como completada. |
