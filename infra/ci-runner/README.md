# Self-hosted runner de CI en Railway (servicio `ci-runner`)

Runner de **GitHub Actions siempre encendido** en Railway, pensado para los jobs
que deben correr **horas o días** sin el tope de 6 h de los runners alojados por
GitHub y sin depender de tu laptop ni de una sesión de Claude.

Los workflows que usan `runs-on: [self-hosted, omni]` (p. ej.
[`.github/workflows/long-tests.yml`](../../.github/workflows/long-tests.yml)) se
ejecutan aquí. El resto del CI normal sigue en los runners de GitHub.

> ⚠️ **Costo:** es un contenedor 24/7. Si no lo necesitas de forma continua,
> pausa o elimina el servicio en el dashboard de Railway.

> 🔐 **Seguridad:** el `ACCESS_TOKEN` (PAT) vive como variable del servicio en
> Railway, **nunca en el repositorio**.

---

## Qué incluye

- Runner oficial de GitHub Actions (`actions/runner`).
- Python 3.11, Node 22, cliente de PostgreSQL, `git`, `jq`, `ripgrep`.
- Se registra solo contra `Romeromarcov/omni-erp` con labels `self-hosted,omni`
  y se da de baja limpio en cada redeploy.

## Variables del servicio

| Variable | Obligatoria | Valor |
|---|---|---|
| `ACCESS_TOKEN` | sí | PAT (classic) con scope `repo`, para registrar el runner |
| `GH_OWNER` | no | por defecto `Romeromarcov` |
| `GH_REPO` | no | por defecto `omni-erp` |
| `RUNNER_NAME` | no | por defecto `railway-ci-runner` |
| `RUNNER_LABELS` | no | por defecto `self-hosted,omni` |

Si el runner debe correr la suite contra una base de datos, añade también las
variables `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` apuntando a
un **Postgres de pruebas dedicado** (otro servicio Railway), nunca a staging/prod.

## Despliegue (una sola vez)

### Opción A — Dashboard (recomendada)

1. Proyecto **Omni-ERP** → **New** → **GitHub Repo** → `Romeromarcov/omni-erp`.
2. Servicio nuevo → **Settings**:
   - **Root Directory**: `infra/ci-runner`
   - **Build**: usa el `Dockerfile` de esa carpeta (autodetectado).
   - Quita cualquier **Healthcheck** / **Start Command** (es un worker, no web).
   - **Networking**: NO generes dominio público.
3. **Variables** → añade `ACCESS_TOKEN` con tu PAT.
4. Renombra el servicio a `ci-runner`.

### Opción B — CLI

```bash
railway add --service ci-runner --repo Romeromarcov/omni-erp
# En el dashboard fija Root Directory = infra/ci-runner.
railway variables --service ci-runner --set "ACCESS_TOKEN=ghp_..."  # tu PAT
railway up --service ci-runner
```

## Verificar

En GitHub: **Settings → Actions → Runners** debe aparecer `railway-ci-runner`
en estado *Idle*. Luego lanza el workflow de tests largos
(**Actions → Long tests → Run workflow**) y comprobará que toma el job.
