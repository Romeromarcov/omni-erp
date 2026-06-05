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
| `feature/*` · `fix/*` · `hotfix/*` · `chore/*` | — (preview opcional por PR) | — |

Convención de ramas: `feature/<slug>`, `fix/<slug>`, `hotfix/<slug>`, `chore/<slug>`,
`docs/<slug>`. Commits en español, imperativo (`agrega…`, `corrige…`).

---

## 1. Feature nuevo → camino completo (Git manda)

```
feature/<slug>  (desde develop)
   │  PR  → develop        → CI + gate (DEFINITION_OF_DONE) → merge
   ▼
develop  ──► Railway despliega STAGING  ──► validar en staging
   │  PR  → main           → revisión humana (tier ALTO obligatoria)
   ▼
main     ──► Railway despliega PRODUCCIÓN
```

1. Rama `feature/<slug>` **desde `develop`**.
2. Implementar + pasar el **Definition of Done** (build, tests, seguridad, gaps, cero deuda).
3. **PR a `develop`** (en draft; el humano marca "ready" — R-PROC-3). CI verde obligatorio.
4. Merge → **staging despliega solo** → **validar ahí** (datos/servicios reales, sin riesgo a prod).
5. Cuando staging está sano → **PR `develop` → `main`** → merge → **producción despliega**.

> Un feature **nunca** salta directo a `main` sin pasar por `develop`/staging.

## 2. Auditoría · fix · hotfix → puede trabajar sobre `main`

Para **arreglar algo que ya está en producción** (bug, vulnerabilidad, hotfix), o una
**auditoría que produce correcciones puntuales**, se permite trabajar contra `main`:

1. Rama `fix/<slug>` o `hotfix/<slug>` **desde `main`**.
2. Pasar el Definition of Done (el gate aplica igual; un hotfix no es excusa para saltarlo).
3. **PR a `main`** → revisión humana → merge → producción.
4. **Sincronizar `develop`:** `git merge main` (o cherry-pick) hacia `develop` para que
   staging no quede atrás. **No dejar `develop` divergido de `main`.**

> Diferencia clave: el **feature** explora algo nuevo → va por staging primero.
> El **fix/audit** corrige lo que ya corre en prod → puede ir directo a `main` (con PR).

## 3. Diagnóstico en staging / producción (sin cambios)

Para **investigar** (logs, datos, reproducir un bug) **no se crea rama ni se edita código en
el contenedor**. Acceso **solo lectura** vía Railway CLI. Ver la skill
[`docs/skills/diagnostico-railway/`](skills/diagnostico-railway/SKILL.md) y
[`DESPLIEGUE_RAILWAY.md`](DESPLIEGUE_RAILWAY.md) §Diagnóstico.

- ✅ Permitido: `railway logs`, `railway status`, `railway service list`,
  `railway environment config`, `railway ssh` para `python manage.py shell` de **lectura**.
- ⛔ Prohibido: editar archivos en el contenedor, `migrate`/escrituras destructivas a la BD
  de prod, `railway up`/`redeploy`/`variables --set`/borrar servicios sin proceso.
- Si el diagnóstico revela un fix → se vuelve al **flujo 2** (rama + PR). Lo que se aprende
  mirando staging/prod se **arregla por Git**, no en caliente.

---

## Resumen en una frase

- **Feature** → `feature/*` → **develop (staging)** → **main (prod)**.
- **Audit/Fix/Hotfix** → `fix|hotfix/*` → **main (prod)** (+ sincronizar develop).
- **Diagnóstico** → solo lectura en staging/prod, **cero edición en caliente**; el cambio
  siempre vuelve por Git.
