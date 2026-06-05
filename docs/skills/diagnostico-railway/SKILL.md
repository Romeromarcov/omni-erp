---
name: diagnostico-railway
description: Diagnosticar staging/producción de Omni ERP en Railway de forma SOLO LECTURA (logs, estado, datos). Usar cuando se investiga un bug, deploy fallido, servicio caído o comportamiento en un entorno real. NUNCA editar código ni datos en el contenedor.
---

# Diagnóstico en Railway (solo lectura)

Para **investigar** staging o producción sin tocar nada. El estado lo cambia Git, no el
contenedor (ver `docs/FLUJO_DE_TRABAJO.md`). El filesystem del contenedor es efímero.

## Contexto del proyecto

- Proyecto Railway: **Omni-ERP** (`f5c956c3-39dd-4b0c-9e9f-25f14283463d`).
- Environments: **production** y **staging** (cada uno con su Postgres y Redis propios).
- Servicios: `omni-erp-backend`, `omni-erp-frontend`, `omni-erp-worker`, `omni-erp-beat`,
  `Postgres`, `Redis`.
- Health backend: `GET /api/health/` → `{"status":"ok"}`.
- Celery: worker escucha colas `celery,auditoria`; beat usa `DatabaseScheduler` (1 réplica).

## Comandos permitidos (solo lectura)

```bash
railway link -p f5c956c3-39dd-4b0c-9e9f-25f14283463d   # vincular el repo al proyecto
railway status                                          # entorno/servicio vinculado
railway service list -e production                      # estado de servicios (o -e staging)
railway logs -e production -s omni-erp-worker           # logs runtime (deploy)
railway logs -e production -s omni-erp-backend -b       # logs de BUILD (-b)
railway environment config --json -e staging            # config por servicio (start, source…)
```

Siempre **especifica el environment** (`-e production` / `-e staging`) para no confundirte.
Para inspeccionar **datos** sin escribir: `railway ssh -e staging -s omni-erp-backend` y
dentro `python manage.py shell` (solo consultas de lectura), o `dbshell` con `SELECT`.

## Prohibido (cambia estado → va por Git/PR)

- ⛔ Editar archivos del código en el contenedor (efímero; se pierde y causa drift).
- ⛔ `migrate` o escrituras a la BD de **producción** desde el shell.
- ⛔ `railway up` / `redeploy` / `variables --set` / `environment edit` / borrar servicios
  como "arreglo en caliente".

## Si el diagnóstico encuentra un fix

Vuelve al flujo de Git (`docs/FLUJO_DE_TRABAJO.md`):
- Bug en prod → rama `fix/<slug>` desde `main` → PR a `main` → sincronizar `develop`.
- Mejora/feature → rama `feature/<slug>` desde `develop` → PR → staging → main.

## Lecciones registradas

- **Worker/beat "Failed" en "scheduling build" sin logs:** servicio en estado de build
  corrupto en Railway. Remedio: **recrear el servicio** (no se arregla con redeploy). Verifica
  que tenga `startCommand` de celery (no arrancar como web), `SKIP_MIGRATIONS=1`, y
  `REDIS_URL`/`DATABASE_URL` del entorno correcto. Ver `DESPLIEGUE_RAILWAY.md`.
- `sync_tasas_ve: Monedas USD/VES no encontradas en BD` → faltan sembrar monedas USD/VES
  (no es fallo de infra, es dato de la app).
