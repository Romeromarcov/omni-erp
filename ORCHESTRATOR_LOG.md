# Orchestrator Log — Omni ERP

Registro append-only de los ítems cerrados por el loop autónomo.

- 2026-06-18 ✅ CTF-005 — whitelist explícita de campos en serializers (ventas/compras/core); elimina `fields="__all__"` (CWE-915, defensa en profundidad) + test guard. Rama `claude/funny-albattani-cqsuck`.
[2026-06-18T13:01:23Z] ✅ CTF-005 whitelist serializers PR#140 merged
[2026-06-18T13:11:02Z] ✅ CTF-005 fase 2 (finanzas+nomina whitelist) commit 7872c7c
[2026-06-18T13:30:08Z] ✅ CTF-005 fase 2 (finanzas+nomina) PR#141 merged
[2026-06-18T13:36:34Z] ✅ CTF-005 fase 3 (contabilidad/tesoreria/fiscal/cxc/cxp/gastos/costos whitelist)
[2026-06-18T13:56:26Z] ✅ CTF-005 fase 3 PR#142 merged
[2026-06-18T18:23:40Z] ✅ CTF-005 fase 4 (cierre total, 68 serializers, 18 apps) commit 5f852a0
[2026-06-18T18:46:59Z] ✅ CTF-005 fase 4 (cierre total) + fix CVE undici PR#143 merged — 0 __all__ en todo el proyecto
[2026-06-18T19:03:30Z] ✅ CTF-008 Nivel 1 réplica local IndexedDB (persistencia caché) commit 661a317
[2026-06-18T19:23:05Z] ✅ CTF-008 Nivel 1 réplica local IndexedDB PR#144 merged
[2026-06-18T19:48:48Z] ✅ 1.I costeo real persistido (CostoProduccion) commit c412772
[2026-06-18T20:14:03Z] ✅ CTF-008 Nivel 2 backend pull de deltas (apps/sync) commit 9a4561f
[2026-06-18T20:38:06Z] ✅ CTF-008 Nivel 2 pull de deltas (apps/sync) PR#147 merged
[2026-06-18T20:51:17Z] ✅ CTF-008 N2 replay idempotente ventas POS (test+doc) commit 3676654
[2026-06-18T21:09:45Z] ✅ CTF-008 N2 replay idempotente ventas POS PR#149 merged
[2026-06-18T21:16:16Z] ✅ CTF-008 N2 sync pull variantes_producto commit b806686
