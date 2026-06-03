# Auditorías

Documentación relacionada con las auditorías del proyecto: planificación, logs de ejecución, diagnósticos y planes post-auditoría.

## Estructura

- **`docs/auditorias/`** (raíz) — auditoría **activa / en curso**.
  - `PLAN_TRABAJO_AUDITORIA_2026-06-01.md` — plan de trabajo de la auditoría vigente (branch `fix/audit-2026-06-01`).
- **`docs/auditorias/archivo/`** — auditorías **finalizadas**. Aquí se archivan los planes, diagnósticos y logs de auditorías ya cerradas.
  - `DIAGNOSTICO_INICIAL.md` — diagnóstico inicial del proyecto.
  - `PLAN_TRABAJO_POST_AUDIT.md` — plan de trabajo post-auditoría previo.

## Convención

1. Mientras una auditoría está en curso, su planificación y logs viven en la raíz de `docs/auditorias/`.
2. Al cerrar una auditoría, mover sus documentos a `archivo/` (usar `git mv` para preservar historial).
3. Nombrar los planes con la fecha de inicio: `PLAN_TRABAJO_AUDITORIA_AAAA-MM-DD.md`.
