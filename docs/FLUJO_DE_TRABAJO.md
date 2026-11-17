# Flujo de trabajo y despliegue — Omni ERP

> **Regla de oro: Git manda.** El estado de cada entorno = un commit real en GitHub.
> Nada se edita "en vivo" dentro de un contenedor de Railway (es efímero y se pierde).

Este documento define **cómo entra el código a cada entorno**. El *gate de calidad* de cada
cambio vive en [`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md); aquí se define el *ruteo*.

## Ramas y entornos

| Rama | Entorno Railway | Despliegue |
|---|---|---|
| **`main`** | **producción** | automático al hacer merge (integración GitHub→Railway) |
| **`develop`** | **staging** (DB/Redis propios, aislados de prod) | automático al hacer merge |
| `feature/*` · `fix/*` · `hotfix/*` · `chore/*` · `docs/*` | — (preview opcional por PR) | — |

Convención de ramas: `feature/<slug>`, `fix/<slug>`, `hotfix/<slug>`, `chore/<slug>`,
`docs/<slug>`. Commits en español, imperativo (`agrega…`, `corrige…`).

## Principio único: TODO nace de `develop`

**Toda rama de trabajo —feature, fix, hotfix, chore, docs— nace de `develop` y hace PR a
`develop`.** No existe el camino "fix directo a `main`": producción solo recibe código que
ya pasó por `develop`/staging. Esto mantiene a `develop` como la única línea de integración
y elimina la divergencia entre ramas.

---

## 1. Camino único de cualquier cambio (Git manda)

```
feature|fix|hotfix|docs|chore/<slug>  (desde develop)
   │  PR (draft) → develop → Gate DoD → Revisor QA+Sec APROBADO → ready → CI 100 % verde → merge
   ▼
develop  ──► Railway despliega STAGING  ──► validar en staging
   │  PR (draft) → main    → revisión y aprobación humana del owner obligatoria (R-PROC-3)
   ▼
main     ──► Railway despliega PRODUCCIÓN
```

1. Rama `feature/<slug>` (o `fix/`, `hotfix/`, `chore/`, `docs/`) **desde `develop`**.
2. Implementar + pasar el **Definition of Done** (build, tests, seguridad, gaps, cero deuda).
3. **Abrir PR en `draft` hacia `develop`**.
4. **Loop autónomo hacia `develop` (autorizado por el owner el 2026-06-11 y ampliado el 2026-11-17):**
   1. Tras pasar el **Gate DoD completo**, un **agente revisor independiente y distinto del autor** (`QA + Seguridad`) revisa el diff y deja dictamen **`APROBADO`** evidenciado en un comentario del PR.
   2. Con ese dictamen **`APROBADO`**, el agente/orquestador **marca el PR `ready`**.
   3. Se espera a que todos los checks de **CI estén 100 % verdes** (ningún check obligatorio en rojo o pendiente).
   4. Con CI 100 % verde y el dictamen **`APROBADO`** en el PR, el agente/orquestador ejecuta el **merge a `develop`**.
   *(Tras el merge a `develop`, actualizar el grafo local con `graphify update .`.)*
5. Merge → **staging despliega solo** → **validar ahí** (datos/servicios reales, sin riesgo a prod).
6. Cuando staging está sano → **PR `develop` → `main`** (en `draft`) → **revisión y aprobación humana obligatoria del owner (`R-PROC-3`)** → merge → **producción despliega**. **Ningún agente marca `ready` ni mergea a `main` sin aprobación humana.**

> Un cambio **nunca** salta directo a `main`. El control humano vive en la puerta
> `develop`→`main`, que es la única que toca producción.

## 2. Hotfix urgente de producción

Un bug en producción **también se corrige sobre `develop`**: rama `hotfix/<slug>` desde
`develop` → PR a `develop` (loop autónomo con Gate DoD + revisor independiente `APROBADO` + CI 100 % verde) → validar en staging → PR
`develop`→`main` con revisión y aprobación humana **expedita** del owner. Si `develop` contiene trabajo aún no
validado que no debe llegar a prod, el PR `develop`→`main` se arma con cherry-picks en una
rama `release/<slug>` desde `main` — pero el fix **siempre** se integra primero a `develop`.

## 3. Diagnóstico en staging / producción (sin cambios)

Para **investigar** (logs, datos, reproducir un bug) **no se crea rama ni se edita código en
el contenedor**. Acceso **solo lectura** vía Railway CLI. Ver la skill
[`docs/skills/diagnostico-railway/`](skills/diagnostico-railway/SKILL.md) y
[`DESPLIEGUE_RAILWAY.md`](DESPLIEGUE_RAILWAY.md) §Diagnóstico.

- ✅ Permitido: `railway logs`, `railway status`, `railway service list`,
  `railway environment config`, `railway ssh` para `python manage.py shell` de **lectura**.
- ⛔ Prohibido: editar archivos en el contenedor, `migrate`/escrituras destructivas a la BD
  de prod, `railway up`/`redeploy`/`variables --set`/borrar servicios sin proceso.
- Si el diagnóstico revela un fix → rama `fix/*` **desde `develop`** (flujo 1). Lo que se
  aprende mirando staging/prod se **arregla por Git**, no en caliente.

---

## Resumen en una frase

- **Todo cambio** (feature, fix, hotfix) → rama desde `develop` → PR `draft` a `develop`
  (Gate DoD + revisor independiente `QA + Seguridad` `APROBADO` → `ready` → CI 100 % verde → merge) → staging → PR `develop`→`main` (**revisión y aprobación humana obligatoria**) → prod.
- **Diagnóstico** → solo lectura en staging/prod, **cero edición en caliente**; el cambio
  siempre vuelve por Git.
