# Auditoría integral — Omni ERP — 2026-06-21

> Auditoría de estado real verificada **contra el código** (no contra lo declarado).
> Método: 4 CODE_READERs por cluster + DOC_AUDITOR + cruce de consistencia, sobre `main`.
> Sesión de solo lectura de código + escritura de documentación. **No se modificó código de aplicación.**

## Resumen ejecutivo

1. El proyecto está **más avanzado de lo que declaraba el Plan Maestro**: nómina LOTTT, manufactura
   (BOM/OF/MRP/costeo) y despacho —marcados "pendiente/parcial"— están **implementados y testeados**.
2. El **núcleo transaccional completo** (ventas, compras, inventario, finanzas, fiscal VE, contabilidad,
   CxC/CxP, tesorería) es **REAL_DONE** con multi-tenant, Decimal e idempotencia; los fixes del P0 de la
   auditoría 2026-06-10 están **verificados presentes en disco**.
3. La auditoría descubrió **deuda nueva no registrada**, la más grave: el **cierre de período fiscal no se
   hace cumplir** (flag cosmético → riesgo fiscal) y `AbonoCxPViewSet` es **CRUD libre** (mismo bug que el
   P0 ya corregido en CxC, sin corregir en CxP).
4. La documentación está **sana**: solo se archivaron 4 snapshots fechados obsoletos; CTFs y ADRs son
   registros vivos. Se corrigieron enlaces rotos y se actualizó el Plan Maestro al estado verificado.
5. El siguiente hito (**1.F distribuidora en producción**) ya **no requiere construir software**: el
   backend está listo; falta carga de datos reales + UI puntual + operación. El trabajo de código pendiente
   son features acotados, ejecutables de forma autónoma.

## Salud técnica (verificada localmente)

- `python manage.py check` → **sin issues**.
- `makemigrations --check --dry-run` → **sin cambios pendientes**.
- Suite real en `backend/tests/` (capas unit/api/integration/tenant/e2e, ~188 archivos). **Corrida
  completa localmente en esta auditoría (2026-06-21): `5224 passed, 19 skipped`, exit 0** (~33 min serie).
  Ratchet de cobertura `--cov-fail-under=92` (~92.97–94 % medido). El CI la exige verde en cada PR.
- **Aviso de entorno:** la suite vive en `backend/tests/`, **no** en `tests_api/` (CTF-014 la migró por
  capas; `tests_api/` quedó casi vacío y correrlo da ~27 % cov + errores RLS). El gate canónico es
  `python -m pytest` (usa `testpaths` de `pytest.ini`). CLAUDE.md y DEFINITION_OF_DONE.md ya apuntan a `tests/`.

## Tabla de verdad — features verificados

| Feature / módulo | Estado | Prueba que lo confirma |
|---|---|---|
| `core` (Empresa, Contacto, CapabilityToken, MCP server, event store, uuid7) | REAL_DONE | `tests/integration/test_core_models_cobertura.py`, `test_mcp_server_scope.py`, `test_ai_primitives.py` |
| `integration_hub` (Odoo XML-RPC + Google Sheets + SyncEngine + checksum + MCP) | REAL_DONE | `tests/integration/test_hub_sync_engine.py`, `tests/unit/test_google_sheets_connector.py` |
| `personalizacion` (DSL runtime) · `agentes` (niveles, eval suite, clasificador) | REAL_DONE | `test_ctf002_dsl_runtime.py`, `test_m9_agentes.py`, `tests_eval/test_eval_cobranza.py` |
| `ventas` ciclo completo + **CxC única al facturar** (P0) | REAL_DONE | `tests/e2e/test_e2e_ciclo_venta.py`, `test_p05_ventas_cxc_unica.py` |
| `fiscal` IVA/IGTF config-driven + Libros SENIAT TXT+PDF | REAL_DONE | `test_fiscal_calculos.py`, `test_sesion_k_libros_seniat.py` |
| `contabilidad` `generar_asiento()` en `@transaction.atomic` (R-CODE-11) | REAL_DONE | `test_rcode11_centralizado.py`, `test_ctf001_asientos_contables.py` |
| `cuentas_por_cobrar` abono atómico (lock+tope) + aging + scoring | REAL_DONE | `tests/integration/test_cxc_abono_concurrencia.py`, `test_cxc_viewset_guard.py` |
| **P0 verificado:** AbonoCxC no-CRUD · pagos mueven saldos · acuerdos acumulan con lock · conciliación con lock | REAL_DONE | `test_cxc_viewset_guard.py`, `finanzas/views.py` PagoViewSet, `test_cxc_acuerdos_concurrencia.py` |
| `tesoreria` conciliación con lock + `OperacionCambioDivisa` | REAL_DONE | `test_cambio_divisa_atomicidad.py`, `test_sesion_m_tesoreria.py` |
| **nómina LOTTT** (ISLR tramos, SSO/FAOV/RPE, provisiones, aportes) | REAL_DONE *(plan decía pendiente)* | `tests/unit/test_nomina_lottt.py`, `tests/integration/test_nomina_proceso.py` |
| **manufactura** (BOM, OF con etapas, costeo, MRP) | REAL_DONE *(plan decía 🔲)* | 6 archivos en `tests/{unit,api,integration,tenant}` de manufactura |
| **despacho** (services + PDF nota de entrega) | REAL_DONE *(plan decía 🔲)* | tests API/integración de despacho |
| **Offline POS** endpoint atómico `POST /api/sync/push/ventas/` (ADR-012) | REAL_DONE | PR `#171`; outbox/builder `#156/#160/#161` |
| `localizacion` framework (6 puertos ABC + registry) | REAL_DONE | `test_localizacion`; `localizacion/ports.py`, `registry.py` |
| `localizacion_ve` adapters | PARTIAL (2/6 puertos) | `localizacion_ve/adapters.py` (`MotorImpuestosVE`, `CalculadoraNominaVE`) |
| `almacenes`, `costos`, `gastos`, `servicio_cliente`, `migracion_datos` | PARTIAL | modelos + CRUD/commands; sin capa de servicios completa |
| `banca_electronica`, `integracion_b2b`, `gestion_aprobaciones` | SCAFFOLD | CRUD sin lógica de negocio ni tests propios |

> Ninguna feature declarada resultó **MISSING**. La discrepancia dominante fue en sentido **positivo**
> (el plan subestimaba lo hecho).

## Deuda técnica nueva descubierta (no estaba registrada)

| # | Severidad | Hallazgo | Ubicación |
|---|---|---|---|
| 1 | ✅ **RESUELTO** (2026-06-21) | ~~Cierre de período fiscal no se hace cumplir~~ — corregido: `validar_periodo_abierto(empresa, fecha)` (`apps/fiscal/services.py`) bloquea emisión de factura y devolución/NC en período cerrado; 7 tests en `tests/api/test_periodo_fiscal_enforcement.py` verdes (multi-tenant incluido). | `apps/fiscal/services.py`, `apps/ventas/services.py` |
| 2 | 🟠 Media | **`AbonoCxPViewSet` CRUD libre** — permite PUT/PATCH/DELETE; `create` no usa `registrar_abono_cxp` atómico (mismo bug que el P0 de CxC, sin corregir en CxP). | `apps/cuentas_por_pagar/views_abono.py` |
| 3 | 🟡 Baja | CxP de compras nunca re-vinculada a `FacturaCompra` (`id_factura_compra` NULL). | `apps/compras/services.py` |
| 4 | 🟡 Baja | `AsientoContable` sin FK de usuario real (`id_usuario_registro_temp` UUID). | `apps/contabilidad/models.py` |
| 5 | 🟡 Baja | `registrar_efectos_pago` sin conversión FX (fuerza moneda base = moneda del pago). | `apps/finanzas/services.py` |
| 6 | 🟢 Cosmética | `apps/cxc/mcp/__init__.py` vacío (tools en `core/mcp_server.py`); `uuid7` sin test dedicado. | — |

> Deuda fechada vigente: **CTF-008** (offline), **CTF-010** (firma apps), **CTF-011** (push Odoo),
> **CTF-012** (RLS prod). 11 CTFs cerrados.

## Docs archivados (movidos a `docs/archive/2026-06-21/`)

| Documento | Razón |
|---|---|
| `audit/SECURITY_REVIEW_2026-06-02.md` | Snapshot de seguridad superado; hallazgos cerrados o en CTF |
| `audit/CVE_REMEDIACION_2026-06-02.md` | CVEs remediados; CTF-007 cerrado |
| `audit/R-CODE_CHECKLIST_A3.md` | Checklist puntual ya consumado |
| `decisions/REGISTRO_SESION_2026-06-12.md` | Registro de sesión; contenido consumado en PROJECT_LOG/ADRs/CTFs |

> Se **conservaron en sitio** (son registros vivos por diseño, no se archivan): los CTFs (registro fechado
> de deuda, R-PROC-6), los ADRs, los mapas autogenerados `audit/MAPA_*`, y todo `docs/planes/`.
> `docs/_archive/` y `docs/auditorias/archivo/` ya estaban archivados.

## Docs vigentes (propósito)

| Documento | Propósito |
|---|---|
| `docs/PLAN_MAESTRO_UNICO.md` | Única fuente de verdad (actualizado a estado verificado en esta auditoría) |
| `docs/AUDITORIA_2026-06-21.md` | Este reporte |
| `docs/ESTADO_DEL_PROYECTO.md` | Foto de avance reciente (2026-06-19) |
| `CLAUDE.md` / `AGENTS.md` / `docs/DEFINITION_OF_DONE.md` | Puerta de entrada de agentes + gate de cierre |
| `docs/FLUJO_DE_TRABAJO.md` / `docs/DESPLIEGUE_RAILWAY.md` / `docs/ENTORNO_DE_TRABAJO.md` | Branching, despliegue, entorno |
| `docs/planes/*` | Planes de ejecución vivos (README ahora con roadmap por features) |
| `docs/ctf/*` (4 abiertos) · `docs/decisions/ADR-*` (012 ADRs) | Deuda fechada + decisiones de arquitectura |
| `docs/audit/ESTADO_PLAN_CERO_DUDAS.md` + `MAPA_*` · `docs/tech-debt/INVENTORY.md` · `docs/runbooks/*` | Estado de calidad, mapas de superficie, deuda menor, runbooks |
| `backend/PROJECT_LOG.md` · `ORCHESTRATOR_LOG.md` | Bitácoras append-only |

## Cambios en PLAN_MAESTRO_UNICO (v1.1 → v1.2)

- **§4 reescrito al estado verificado**: nueva estructura (Estado actual / Módulos verificados con
  REAL_DONE-PARTIAL-SCAFFOLD / Deuda activa). Reclasificados a ✅: nómina LOTTT, manufactura, despacho.
- **§5.1** árbol de sub-fases: 1.G–1.I marcados 🔶 (backend hecho; falta UI/datos/operación).
- **§5.1-bis nuevo**: Reglas de implementación autónoma (rama → PR `develop` → QA_AGENT+SEC_AGENT →
  automerge con CI verde; humano solo en escalación tras 3 fallos o acciones de owner).
- **§3.8**: añadidos ADR-010/011/012. Header v1.2, fecha 2026-06-21, footer y enlaces de auditoría.
- Enlaces rotos corregidos en `docs/README.md` y `docs/planes/05-seguridad-hardening.md` (apuntaban a una
  auditoría "activa" que ya está archivada). ADR-010/011/012 añadidos al índice de `docs/README.md`.

## Próximos 3 features a implementar (autónomos, sin bloqueantes)

1. ✅ ~~**Enforcement de cierre de período fiscal.**~~ **HECHO 2026-06-21** (rama `fix/periodo-fiscal-enforcement`):
   emitir factura/devolución en período `CERRADO` → 400; 7 tests verdes. **Siguiente feature pendiente: el #2.**
2. **`AbonoCxPViewSet` write-guard (paridad con CxC).**
   *Done cuando:* PUT/PATCH/DELETE → 405 y `create` delega en `registrar_abono_cxp` atómico (lock+tope);
   test de concurrencia y de tenant en verde.
3. **Offline POS — cerrar ciclo en frontend (CTF-008).**
   *Done cuando:* `PosPage` encola el sobre `VentaOffline` en `salesOutbox` al fallar la red y hace flush
   al reconectar reconciliando `client_uuid → id_nota_venta`; test de frontend en verde. (Backend `#171` ya REAL_DONE.)

## Instrucción para el agente implementador

> Leer `AUDITORIA_2026-06-21.md` y `PLAN_MAESTRO_UNICO.md` (§4 estado, §5.1-bis reglas autónomas,
> §5.2 roadmap).
> Iniciar por el primer feature PENDING sin bloqueantes de la tabla "Roadmap por features" en
> `docs/planes/README.md` — hoy: **enforcement de cierre de período fiscal**.
> Rama `fix/periodo-fiscal-enforcement` desde `main` (es corrección de deuda) → PR draft.
> `QA_AGENT` (correctness/atomicidad/tests) + `SEC_AGENT` (multi-tenant/authz) como revisores.
> Gate completo de `DEFINITION_OF_DONE.md`. Automerge con CI verde + ambos revisores; escalar al owner
> solo tras 3 fallos o si toca una acción exclusiva del owner (RLS prod, secrets, branch protection, firma, billing).
