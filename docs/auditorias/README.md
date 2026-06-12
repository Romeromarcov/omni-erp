# Auditorías

Documentación relacionada con las auditorías del proyecto: planificación, logs de ejecución, diagnósticos y planes post-auditoría.

## Estructura

- **`docs/auditorias/`** (raíz) — auditoría **activa / en curso**.
  - (ninguna activa — la integral 2026-06-10 se archivó al cerrar su workstream P0 el 2026-06-11; ver `archivo/AUDITORIA_INTEGRAL_2026-06-10.md`)
- **`docs/auditorias/archivo/`** — auditorías **finalizadas**. Aquí se archivan los planes, diagnósticos y logs de auditorías ya cerradas.
  - `PLAN_TRABAJO_AUDITORIA_2026-06-01.md` — plan de la auditoría 2026-06-01 (cerrado 2026-06-10; su §11 frontend migró al Plan Maestro §5.2 workstream F).
  - `DIAGNOSTICO_INICIAL.md` — diagnóstico inicial del proyecto.
  - `PLAN_TRABAJO_POST_AUDIT.md` — plan de trabajo post-auditoría previo.

## Convención

1. Mientras una auditoría está en curso, su planificación y logs viven en la raíz de `docs/auditorias/`.
2. Al cerrar una auditoría, mover sus documentos a `archivo/` (usar `git mv` para preservar historial).
3. Nombrar los planes con la fecha de inicio: `PLAN_TRABAJO_AUDITORIA_AAAA-MM-DD.md`.
