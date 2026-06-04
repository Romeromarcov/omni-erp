# Claude Code en Railway (servicio `claude-dev`)

Caja de desarrollo **siempre encendida** en Railway para abrir sesiones de
**Claude Code interactivas** sobre el repositorio `omni-erp`, ejecutándose en la
infraestructura de Railway (no en la nube de Claude). Entras por `railway ssh`.

> ⚠️ **Costo:** es un contenedor que corre 24/7 mientras exista el servicio.
> Si solo lo usas a ratos, **elimina el servicio** (o ponlo en pausa desde el
> dashboard) cuando termines para no acumular consumo.

> 🔐 **Seguridad:** la `ANTHROPIC_API_KEY` se guarda como variable del servicio
> en Railway, **nunca en el repositorio**. El filesystem del contenedor es
> efímero salvo el volumen montado en `/workspace`.

---

## Qué incluye el contenedor

- Node 22 + `@anthropic-ai/claude-code`
- `git`, `gh` (GitHub CLI), `python3`, `ripgrep`, `jq`, build-essential
- Clona el repo en `/workspace/omni-erp` (volumen persistente) al arrancar
- Queda vivo (`sleep infinity`) para `railway ssh`

## Variables del servicio

| Variable | Obligatoria | Valor |
|---|---|---|
| `ANTHROPIC_API_KEY` | sí | Tu API key de Anthropic (la pegas tú en Railway) |
| `GIT_REPO_URL` | no | Por defecto `https://github.com/Romeromarcov/omni-erp.git` |

## Despliegue (una sola vez)

### Opción A — Dashboard (recomendada)

1. Proyecto **Omni-ERP** → **New** → **GitHub Repo** → `Romeromarcov/omni-erp`.
2. En el servicio nuevo → **Settings**:
   - **Root Directory**: `infra/claude-railway`
   - **Build**: usa el `Dockerfile` de esa carpeta (autodetectado).
   - Quita cualquier **Healthcheck** / **Start Command** (es un worker, no web).
3. **Settings → Volumes** → añade un volumen montado en `/workspace`.
4. **Variables** → añade `ANTHROPIC_API_KEY` con tu key.
5. **Settings → Networking** → NO generes dominio público (no expone puerto).
6. Renombra el servicio a `claude-dev` para que coincida con los comandos.

### Opción B — CLI

```bash
railway add --service claude-dev --repo Romeromarcov/omni-erp
# Luego, en el dashboard del servicio, fija Root Directory = infra/claude-railway
# y añade el volumen en /workspace (los volúmenes no se crean por CLI de forma fiable).
railway variables --service claude-dev --set "ANTHROPIC_API_KEY=sk-ant-..."  # tu key
railway up --service claude-dev
```

## Uso diario

```bash
railway ssh --service claude-dev
cd /workspace/omni-erp
git pull
claude
```

Dentro de la sesión puedes autenticar GitHub para hacer `push`/PRs:

```bash
gh auth login   # o exporta un GITHUB_TOKEN
```
