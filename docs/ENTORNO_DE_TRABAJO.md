# Entorno de trabajo en la nube (Claude web + GitHub Actions + Railway)

Cómo trabajar en Omni ERP **desde cualquier parte, sin depender de tu laptop**,
con tests que pueden correr el tiempo que haga falta y resultados que entran al
flujo de Git. No hace falta una "réplica" de la app en Railway: el trabajo se
reparte en tres planos, cada uno con su herramienta.

## Los tres planos

| Necesidad | Herramienta | Persistente |
|---|---|---|
| Pedirle algo a Claude desde el móvil/web y que lo ejecute → push → PR | **Claude Code en la web** | Efímero (está bien) |
| Tests/linters "en la nube", desacoplados de tu laptop | **GitHub Actions** (`.github/workflows/ci.yml`) | Por run |
| Tests que corren **horas o días** | **Self-hosted runner en Railway** (`infra/ci-runner/`) | 24/7 |
| Desplegar `develop`→staging, `main`→prod | **Railway** (`deploy.yml`) | 24/7 |

El flujo de Git manda (ver [`FLUJO_DE_TRABAJO.md`](FLUJO_DE_TRABAJO.md)):
`feature/*` → PR a `develop` (staging) → PR `develop`→`main` (producción).

## 1. Sesiones reproducibles (Claude web / Codespaces)

- **SessionStart hook** (`.claude/hooks/session-start.sh`): al abrir una sesión
  remota instala dependencias de backend (en un venv en `backend/.venv`) y de
  frontend. Registrado en `.claude/settings.json`.
- **Devcontainer** (`.devcontainer/`): mismo entorno para GitHub Codespaces o VS
  Code, **con un PostgreSQL de pruebas** (`postgres:17-alpine`, espejo de CI) ya
  levantado, para poder correr la suite que necesita base de datos real.

Tras abrir la sesión, los comandos del gate (ver
[`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md)) funcionan sin setup manual.

## 2. Tests normales — GitHub Actions

`ci.yml` ya corre en cada push/PR (backend pytest contra Postgres, frontend,
agent-eval, security-scan, static-analysis, contract). Corre en infra de GitHub:
si se cae tu conexión o se sobrecarga tu equipo, **da igual, sigue**.

## 3. Tests largos (horas/días) — runner en Railway

Los runners alojados por GitHub topan en **6 h por job**. Para cargas más largas:

1. Despliega una vez el servicio `ci-runner` (ver
   [`infra/ci-runner/README.md`](../infra/ci-runner/README.md)).
2. Lanza el workflow desde cualquier parte: **Actions → Long tests → Run
   workflow** (`.github/workflows/long-tests.yml`).
3. Corre en el runner de Railway con timeout configurable (def. 24 h) y deja los
   resultados como **artefacto** y, opcionalmente, **commiteados** a la rama
   `ci/long-test-reports`. Así el resultado queda en el repo y en el flujo.

> Usa un **Postgres de pruebas dedicado** (otro servicio Railway) para el runner.
> **Nunca** apuntes los tests a staging o producción.

## Costos / higiene

Tanto `ci-runner` como la caja interactiva `claude-railway` son contenedores
24/7. Si no los usas de forma continua, **páusalos o elimínalos** en el dashboard
de Railway para no acumular consumo.
