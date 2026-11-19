# Runbook — Activar el rol de aplicación no-dueño para RLS (CTF-012)

**Objetivo:** que el runtime (web + workers) conecte a PostgreSQL con el rol
`omni_app` (`NOSUPERUSER NOBYPASSRLS`, **no-dueño** de las tablas) mientras las
migraciones siguen corriendo con el rol dueño actual. Con eso PostgreSQL aplica
las políticas RLS al runtime **por construcción** (defensa en profundidad del
aislamiento multi-tenant), sin depender de que todo path pase por el middleware.

**Cuándo:** primero en **staging** (al mergear a `develop`), validación
end-to-end, y después en **producción** (lo ejecuta el owner). Reversible en
cualquier momento (paso 6).

> Las políticas RLS + `FORCE ROW LEVEL SECURITY` ya están desplegadas en las
> 124 tablas tenant por migraciones (lotes 1–3) y son inertes para el rol dueño
> conviviendo con el default `bypass='on'` por conexión. Este runbook solo
> cambia *con qué rol conecta el runtime*.

## Pasos (staging; producción es idéntico servicio a servicio)

1. **Generar la contraseña** del rol (fuera del repo, nunca en código/commits):

   ```bash
   openssl rand -base64 32
   ```

2. **Definir variables en el servicio web** (Railway → servicio backend →
   Variables):
   - `OMNI_APP_DB_PASSWORD` = la contraseña generada (solo la necesita la
     primera vez para crear el rol; puede retirarse después).
   - `MIGRATIONS_DATABASE_URL` = el `DATABASE_URL` **actual** (rol dueño). El
     entrypoint usará esta URL para `migrate` y para reaplicar GRANTs del rol
     en cada deploy (`configurar_rol_rls` es idempotente).

3. **Crear el rol** con un one-off en el servicio web (o redeploy: el
   entrypoint lo corre tras `migrate` cuando `MIGRATIONS_DATABASE_URL` existe):

   ```bash
   railway run python manage.py configurar_rol_rls
   ```

   El comando crea/actualiza `omni_app` con `LOGIN NOSUPERUSER NOBYPASSRLS`
   y GRANTs mínimos (CRUD en tablas + secuencias + default privileges). No
   imprime la contraseña.

4. **Cambiar `DATABASE_URL` del runtime** en web, worker y beat: misma URL que
   la actual pero con usuario/contraseña del rol nuevo:

   ```
   postgresql://omni_app:<OMNI_APP_DB_PASSWORD>@<host>:<puerto>/<db>
   ```

   (En worker/beat **no** definir `MIGRATIONS_DATABASE_URL`: no migran;
   `migrate --check` del arranque solo necesita SELECT y el rol lo tiene.)

5. **Validar en staging**:
   - Deploy verde: `migrate` (rol dueño) + arranque web (rol `omni_app`).
   - Smoke de flujos críticos: login, listar/crear venta, inventario, reportes,
     una tarea Celery (p. ej. auditoría) — todo igual que antes (el default
     `bypass='on'` por conexión sigue rigiendo los paths de sistema).
   - Verificación del rol: `railway run python manage.py shell -c
     "from django.db import connection; c=connection.cursor(); c.execute('select current_user'); print(c.fetchone())"`
     → debe imprimir `omni_app`.
   - (Opcional, prueba de fail-closed real) `psql` con el rol `omni_app` sin
     fijar GUCs: `SELECT count(*) FROM crm_cliente;` → `0` filas.

6. **Rollback:** revertir `DATABASE_URL` al valor original (rol dueño) en los
   servicios afectados y redeploy. Las políticas y el rol pueden quedarse: son
   inocuos con el rol dueño + default de conexión.

7. **Producción (owner):** repetir 2–5 sobre los servicios de prod tras validar
   staging.

## Fase 2 — Activar `RLS_ENABLED=True` (endurecimiento fail-closed, Plan 06 · 2.1)

Una vez completada la Fase 1 (`omni_app` activo en staging/prod y
`MIGRATIONS_DATABASE_URL` configurada con el rol dueño):

1. **Verificar prerrequisitos**:
   - Runtime (`web`, `worker`, `beat`) conectado como `omni_app` (`current_user = omni_app`).
   - Web posee `MIGRATIONS_DATABASE_URL` con credenciales del rol dueño (`migrate` y
     `configurar_rol_rls` corren con él; además los signals `pre_migrate`/`post_migrate`
     envuelven las migraciones en `rls_bypass()` cuando `RLS_ENABLED=True`).

2. **Activar `RLS_ENABLED=True`** en las variables de entorno de `web`, `worker` y `beat`:

   - Conexiones nuevas (`connection_created`) y `apply_system_default()` arrancan
     **fail-closed** (`omni.rls_bypass='off'`, `omni.rls_empresas=''`). Toda consulta
     directa sobre tablas tenant fuera de un contexto explícito devuelve **0 filas**.
   - `RLSContextMiddleware` resuelve usuario/visibilidad brevemente dentro de
     `rls_bypass()`, aplica luego el contexto del tenant (fail-closed para anónimo o
     token inválido; `bypass=True` para `es_superusuario_omni`) y lo restaura al cerrar
     la respuesta (incluyendo streams SSE). `get_empresas_visible(user)` queda memoizada
     por ciclo de request (`ContextVar`, invalidada por signals de membresía).
   - Los flujos HTTP pre-autenticación (`login_view`, `SignupView`) y el servidor MCP
     (`apps/core/mcp_server.py` + `apps/*/mcp.py`) validan `CapabilityToken` mediante un
     `rls_bypass()` acotado en `_resolve_token` y ejecutan cada tool dentro de
     `mcp_tenant_context` / `rls_tenant_context([context["empresa_id"]])` sin abrir
     ventanas globales al resto de la petición ni dejar estado residual.
   - Todas las tareas Celery (`@shared_task`), el consumidor de eventos y los
     management commands aplican explícitamente `rls_tenant_context([empresa_id])` por
     tenant o `rls_bypass()` acotado para catálogos globales/búsqueda por PK antes de
     aislar el tenant (`rls_bypass()` y `rls_tenant_context()` preservan y restauran el
     GUC previo para soportar anidamiento seguro).

3. **Validar tras el deploy** (`RLS_ENABLED=True`):
   - `python manage.py shell -c "from apps.core import rls; from apps.crm.models import Cliente; rls.apply_system_default(); print(Cliente.objects.count())"` → debe imprimir `0`.
   - Login (`POST /api/auth/login/`), endpoints autenticados de módulo tenant, una tarea
     Celery periódica (`tareas.ejecutar_ciclo_todos`) y un comando (`seed_catalogo_monedas`)
     deben completar en verde.

4. **Rollback de emergencia**: fijar `RLS_ENABLED=False` en `web`, `worker` y `beat` y
   redeploy. Devuelve el default de conexión a `bypass='on'` preservando el rol `omni_app`
   y todas las políticas RLS en BD sin migraciones ni pérdida de datos.

## Qué hace y qué NO hace este runbook

- **No** elimina el rol dueño para migraciones (`MIGRATIONS_DATABASE_URL` sigue siendo
  necesaria para `migrate` y `ALTER TABLE` / políticas RLS).
- Con `RLS_ENABLED=False` (paso 1–7 inicial), `bypass='on'` mantiene compatibilidad total
  durante la transición al rol `omni_app`. Activar `RLS_ENABLED=True` cierra el modo
  fail-closed en PostgreSQL para web, Celery workers y comandos CLI.

## Referencias

- `docs/ctf/CTF-012.md` (condición de cierre y estado).
- `backend/apps/core/rls.py` (context managers `rls_bypass` / `rls_tenant_context`, GUCs, registro).
- `backend/apps/core/signals.py` (`connection_created`, `pre_migrate`/`post_migrate`, invalidación cache).
- `backend/apps/core/middleware.py` (`RLSContextMiddleware`).
- `backend/apps/core/management/commands/configurar_rol_rls.py`.
- `backend/entrypoint.sh` (soporte `MIGRATIONS_DATABASE_URL`).
