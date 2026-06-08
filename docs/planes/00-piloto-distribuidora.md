# Plan 0 — Piloto distribuidora en producción (online)

| Campo | Valor |
|-------|-------|
| **Objetivo** | Poner Omni a operar en la distribuidora: `.exe` instalable + primeros usuarios + seguimiento desde la oficina principal por API. |
| **Modalidad** | SaaS multi-tenant compartido (una sola DB), **online** (offline diferido → Plan A). |
| **Sub-fase del Plan Maestro** | 1.F — "Distribuidora en producción". |
| **Esfuerzo** | ~3–4 días. |
| **Prerrequisito bloqueante** | Cerrar Semana 1 de auditoría de seguridad (multi-tenancy stop-the-bleed). |

## Contexto

El software de negocio que necesita una distribuidora ya está completo y testeado:
ventas (con factura fiscal VE), inventario, caja diaria multimoneda, cobranza (CxC),
CxP, tesorería, contabilidad y fiscal (IVA/IGTF, Libros SENIAT). No falta construir
features para el piloto; falta **endurecer seguridad, empaquetar y cargar datos**.

El **offline-first NO existe** (ver Plan A). Este piloto asume **internet estable** en
el local de la distribuidora; si se cae la red, tras ~5 min de caché la app deja de operar.

## Tareas

| # | Tarea | Detalle / archivos | Esfuerzo |
|---|-------|--------------------|----------|
| 0.1 ✅ | **Cerrar Seguridad Semana-1** | CRIT-1/2/3 + H-SEC-1/2 (aislamiento multi-tenant, R-CODE-1). **HECHO en `main`:** DetailViews paralelos eliminados (tests en `backend/tests/tenant/`), `config/settings.py` fail-closed, sin `SECRET_KEY` débil en `settings_dev.py`. | ~4 PRs / 1–2 días |
| 0.2 | **Compilar `.exe` apuntando a producción** | `cd frontend && VITE_API_URL=https://<backend-railway>/api npm run electron:build` → genera `release/OmniERP-*.exe` (NSIS + portable). Config: `frontend/electron-builder.json`, `frontend/electron/main.cjs`. | 0.5 día |
| 0.3 | **Decisión de firma de código** | Para piloto interno: **diferir firma** y aceptar aviso de SmartScreen (instalación manual). Firma EV Authenticode → Plan B / [CTF-010](../ctf/CTF-010.md). | decisión |
| 0.4 ✅ | **Crear primeros usuarios + empresa** | **Tooling HECHO:** `python manage.py seed_empresa_inicial` crea `Empresa` + admin + sucursal + caja física/virtual (idempotente, password vía `--admin-password`/`OMNI_SEED_ADMIN_PASSWORD` validada, R-CODE-8). `create_initial_data` queda dev-only (bloqueado fuera de DEBUG). Falta solo **ejecutarlo** con los datos reales de la distribuidora. | 0.5 día |
| 0.5 | **Seguimiento desde oficina principal** | Multi-tenant en DB única: la oficina principal accede con un usuario con visibilidad de esa empresa (`get_empresas_visible`, `apps/core/viewsets.py`) o `es_superusuario_omni`, y consume la web/API en lectura. **Sin código nuevo.** Opcional: marcar la distribuidora como `empresa_matriz` para jerarquía. | 0.5 día |
| 0.6 | **Smoke test del ciclo real** | Contra el `.exe` instalado: login → factura fiscal → cobro en caja → CxC → cierre de caja. Usar skill `verify`. | 0.5 día |

## Definition of Done

- [x] Semana 1 de seguridad cerrada (PRs mergeados, tests de aislamiento verdes en CI).
- [ ] `.exe` instalado y operativo en una máquina de la distribuidora, apuntando a la API de producción.
- [ ] Empresa + usuarios iniciales creados; login funcional. *(Tooling listo: `seed_empresa_inicial`; falta correrlo con datos reales — ver [`runbook-arranque-piloto.md`](runbook-arranque-piloto.md).)*
- [ ] Oficina principal puede consultar datos de la distribuidora por web/API (lectura).
- [ ] Ciclo venta→cobro→CxC→cierre de caja verificado manualmente sin errores.
- [ ] Gate de cierre ([`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md)) ejecutado en cada PR.

## Métrica de cierre de la sub-fase 1.F

Operación real **30 días continuos sin recaída** (definición del Plan Maestro §5.2).
Es trabajo operativo + acompañamiento, fuera del alcance puramente técnico de este plan.

## Riesgos / notas

- **Sin offline:** corte de red prolongado detiene la operación. Mitigación: Plan A.
- **Sin firma:** SmartScreen mostrará advertencia; aceptable en piloto controlado.
- **Datos reales:** la migración de clientes/productos/saldos es trabajo operativo del dueño.
