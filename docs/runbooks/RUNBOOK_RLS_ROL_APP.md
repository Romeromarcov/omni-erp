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
> 122 tablas tenant por migraciones (lotes 1–3) y son inertes para el rol dueño
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
   staging. `RLS_ENABLED=True` (enforcement por request del middleware) es un
   paso separado y posterior, también gobernado por CTF-012.

## Qué NO hace este runbook

- No activa `RLS_ENABLED` (enforcement por request): eso se decide después de
  validar el rol en staging/prod.
- No cambia el default `bypass='on'` por conexión (Celery/comandos siguen
  viendo todo); endurecerlo es el siguiente paso del CTF-012 una vez el rol
  esté en uso.
- No toca el rol dueño ni los datos.

## Referencias

- `docs/ctf/CTF-012.md` (condición de cierre y estado).
- `backend/apps/core/management/commands/configurar_rol_rls.py`.
- `backend/apps/core/rls.py` (políticas, registro de tablas, exclusiones).
- `backend/entrypoint.sh` (soporte `MIGRATIONS_DATABASE_URL`).
