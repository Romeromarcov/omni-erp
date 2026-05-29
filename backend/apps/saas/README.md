# App `saas`

Capa SaaS multi-tenant: planes comerciales y suscripciones de las empresas al sistema.

**Prefijo API:** `/api/saas/`

## Modelos

| Modelo | Descripción |
|---|---|
| `Plan` | Plan comercial (features, límites, precio). |
| `Suscripcion` | Suscripción de una empresa a un plan. |

## Endpoints

Recursos REST (CRUD vía router): `planes/`, `suscripciones/`.

Acciones personalizadas:

| Ruta | Descripción |
|---|---|
| `GET suscripciones/activa/` | Suscripción activa de la empresa. |
| `POST suscripciones/{id}/cancelar/` | Cancelar suscripción. |
| `POST suscripciones/{id}/suspender/` | Suspender suscripción. |
