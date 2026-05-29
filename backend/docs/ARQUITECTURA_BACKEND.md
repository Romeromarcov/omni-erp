# Arquitectura del Backend — Omni ERP

Backend Django + Django REST Framework que expone toda la lógica de negocio como API REST (y, por diseño AI-nativo, invocable también vía MCP). Este documento es el mapa de entrada: qué app hace qué, cómo se enrutan los endpoints y qué convenciones siguen todas las apps.

> Fuente de verdad del producto: [`docs/PLAN_MAESTRO_UNICO.md`](../../docs/PLAN_MAESTRO_UNICO.md).
> Cada app tiene su propio `README.md` con el detalle de modelos y endpoints.

---

## Stack

| Componente | Tecnología |
|---|---|
| Framework | Django 5 + Django REST Framework |
| Auth | JWT (SimpleJWT) — ver endpoints `/api/auth/*` |
| Base de datos | PostgreSQL (SQLite no soportado) |
| Tareas async | Celery (ver `config/celery.py`) |
| Event store | Kafka/Redpanda vía `apps.eventos` |
| Docs API | drf-yasg — Swagger en `/api/docs/`, ReDoc en `/api/redoc/` (solo `DEBUG`) |
| Multi-tenant | Aislamiento por `Empresa` (FK + mixins en `core`) |

`config/` contiene la configuración del proyecto: `settings_base.py` + overrides `settings_dev.py` / `settings_prod.py`, `urls.py` (routing raíz), `celery.py`, `asgi.py`/`wsgi.py`.

---

## Convenciones comunes a todas las apps

- **Estructura estándar Django:** `models.py`, `serializers.py`, `views.py` (o `viewsets.py`), `urls.py`, `admin.py`, `apps.py`, `tests.py`, `migrations/`.
- **Routing:** cada app monta un `DefaultRouter` en su `urls.py` y se incluye en `config/urls.py` bajo un prefijo `/api/<modulo>/`. Los ViewSets dan CRUD estándar (`list`, `create`, `retrieve`, `update`, `partial_update`, `destroy`) más `@action` personalizados.
- **Modelos base:** muchos modelos heredan de `OmniBaseModel` / `TimeStampedModel` (en `apps.core.base_models`) que aportan UUID7 como PK, timestamps y campos de auditoría. `IntegrationFieldsMixin` añade campos para sincronización externa (Integration Hub).
- **Aislamiento multi-tenant:** las entidades de negocio referencian `Empresa`; los querysets se filtran por la empresa del usuario autenticado.
- **Localización:** lo específico de Venezuela vive en `vzla_localizacion` y `fiscal` como capa activable, no hardcodeado en el núcleo.

---

## Endpoints globales de autenticación

Definidos directamente en [`config/urls.py`](../config/urls.py) (no pertenecen a una app de negocio):

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/auth/login/` | Login con credenciales → tokens JWT |
| POST | `/api/auth/logout/` | Cierre de sesión |
| POST | `/api/auth/token/` | Obtener par de tokens (access + refresh) |
| POST | `/api/auth/token/refresh/` | Refrescar access token |
| POST | `/api/auth/token/verify/` | Verificar validez de un token |
| GET | `/api/auth/profile/` | Perfil del usuario autenticado |
| PUT/PATCH | `/api/auth/profile/update/` | Actualizar perfil |
| POST | `/api/auth/change-password/` | Cambiar contraseña |

---

## Catálogo de apps y prefijos de routing

Cada fila enlaza al README de la app. El prefijo es el que monta `config/urls.py`; "—" indica una app sin router HTTP propio (librería interna o infraestructura).

### Núcleo y plataforma

| App | Prefijo API | Rol |
|---|---|---|
| [`core`](../apps/core/README.md) | `/api/core/` | Usuarios, empresas, sucursales, roles/permisos, dispositivos, notificaciones, auditoría base. Modelos base del sistema. |
| [`configuracion_motor`](../apps/configuracion_motor/README.md) | `/api/configuracion/` | Tipos de documento, parámetros del sistema, catálogos de valores. |
| [`personalizacion`](../apps/personalizacion/README.md) | `/api/personalizacion/` | DSL declarativo de personalización por empresa (entidades, estados y vistas custom). |
| [`saas`](../apps/saas/README.md) | `/api/saas/` | Planes y suscripciones (capa SaaS multi-tenant). |
| [`auditoria`](../apps/auditoria/README.md) | `/api/auditoria/` | Log de auditoría transversal. |
| [`notificaciones`](../apps/notificaciones/README.md) | `/api/notificaciones/` | Plantillas, eventos, suscripciones y log de notificaciones. |
| [`gestion_documental`](../apps/gestion_documental/README.md) | `/api/gestion-documental/` | Carpetas, documentos, vínculos y permisos documentales. |
| [`gestion_aprobaciones`](../apps/gestion_aprobaciones/README.md) | `/api/gestion-aprobaciones/` | Flujos y solicitudes de aprobación. |
| [`eventos`](../apps/eventos/README.md) | — | Event store (productor/consumidor Kafka). |
| [`agentes`](../apps/agentes/README.md) | `/api/agentes/` | Configuración de agentes IA y predicciones/sugerencias. |

### Comercial y clientes

| App | Prefijo API | Rol |
|---|---|---|
| [`crm`](../apps/crm/README.md) | `/api/crm/` | Clientes, contactos y direcciones. |
| [`ventas`](../apps/ventas/README.md) | `/api/ventas/` | Pedidos, cotizaciones, notas de venta, facturas fiscales, notas de crédito, devoluciones, listas de precio. |
| [`cuentas_por_cobrar`](../apps/cuentas_por_cobrar/README.md) | `/api/cxc/` | Cuentas por cobrar y abonos (aging, estado de cuenta). |
| [`cxc`](../apps/cxc/README.md) | `/api/cobranza/` | Cobranza Inteligente: gestiones, acuerdos de pago, fraccionamiento, agente de cobranza. |
| [`servicio_cliente`](../apps/servicio_cliente/README.md) | `/api/servicio-cliente/` | Tickets de soporte, base de conocimiento, feedback. |

### Compras y proveedores

| App | Prefijo API | Rol |
|---|---|---|
| [`proveedores`](../apps/proveedores/README.md) | `/api/proveedores/` | Proveedores, contactos y cuentas bancarias de proveedor. |
| [`compras`](../apps/compras/README.md) | `/api/compras/` | Órdenes de compra, recepciones, facturas de compra, requisiciones, solicitudes y ofertas de cotización. |
| [`cuentas_por_pagar`](../apps/cuentas_por_pagar/README.md) | `/api/cuentas-por-pagar/` | Cuentas por pagar y abonos (aging). |

### Inventario y operaciones

| App | Prefijo API | Rol |
|---|---|---|
| [`inventario`](../apps/inventario/README.md) | `/api/inventario/` | Productos, variantes, categorías, unidades, stock, movimientos (kardex), consignación. |
| [`almacenes`](../apps/almacenes/README.md) | `/api/almacenes/` | Almacenes y ubicaciones físicas. |
| [`despacho`](../apps/despacho/README.md) | `/api/despacho/` | Despachos y detalles de despacho. |
| [`manufactura`](../apps/manufactura/README.md) | `/api/manufactura/` | BOM, rutas, órdenes de producción, consumos, centros de trabajo. |
| [`costos`](../apps/costos/README.md) | `/api/costos/` | Costos de producción, costo estándar, análisis de variación. |

### Finanzas y contabilidad

| App | Prefijo API | Rol |
|---|---|---|
| [`finanzas`](../apps/finanzas/README.md) | `/api/finanzas/` | Monedas, tasas de cambio, métodos de pago, cajas (físicas/virtuales), datáfonos, transacciones, pagos. |
| [`tesoreria`](../apps/tesoreria/README.md) | `/api/tesoreria/` | Movimientos internos, cambio de divisa, movimientos bancarios, conciliación. |
| [`banca_electronica`](../apps/banca_electronica/README.md) | `/api/banca-electronica/` | Cuentas bancarias de empresa para banca electrónica. |
| [`contabilidad`](../apps/contabilidad/README.md) | `/api/contabilidad/` | Plan de cuentas, asientos contables, mapeo contable automático. |
| [`gastos`](../apps/gastos/README.md) | `/api/gastos/` | Categorías de gasto, gastos, reembolsos. |
| [`fiscal`](../apps/fiscal/README.md) | `/api/fiscal/` | Impuestos, IVA, IGTF, retenciones, parafiscales, libros de ventas/compras, períodos fiscales (localización VE). |

### Personas

| App | Prefijo API | Rol |
|---|---|---|
| [`rrhh`](../apps/rrhh/README.md) | `/api/rrhh/` | Empleados, cargos, beneficios, licencias. |
| [`nomina`](../apps/nomina/README.md) | `/api/nomina/` | Períodos, conceptos, procesos y recibos de nómina (incl. extrasalarial). |
| [`control_asistencia`](../apps/control_asistencia/README.md) | `/api/control-asistencia/` | Horarios, asignaciones, registros y resúmenes de asistencia. |

### Integración y datos

| App | Prefijo API | Rol |
|---|---|---|
| [`integration_hub`](../apps/integration_hub/README.md) | `/api/integration-hub/` | Conectores a sistemas externos, instancias, jobs y logs de sincronización. |
| [`integracion_b2b`](../apps/integracion_b2b/README.md) | `/api/integracion-b2b/` | Configuración de integraciones B2B, mapeo de campos, logs. |
| [`migracion_datos`](../apps/migracion_datos/README.md) | `/api/migracion-datos/` | Plantillas y procesos de migración/importación de datos. |

### Localización

| App | Prefijo API | Rol |
|---|---|---|
| [`vzla_localizacion`](../apps/vzla_localizacion/README.md) | — | Utilidades de Venezuela: validación RIF/cédula, feriados, formato Bs/USD, zona horaria, número de control. |

---

## Cómo explorar la API en vivo

Con `DEBUG=True`:

- **Swagger UI:** http://localhost:8000/api/docs/ — explorar y probar cada endpoint.
- **ReDoc:** http://localhost:8000/api/redoc/ — referencia legible.

El esquema OpenAPI se genera automáticamente desde los ViewSets y serializers, por lo que es la documentación de contrato siempre actualizada. Los README de cada app describen el *propósito* de cada endpoint; Swagger describe el *contrato* (parámetros, payloads, respuestas).
