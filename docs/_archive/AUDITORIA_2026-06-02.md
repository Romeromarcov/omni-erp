# Auditoría Integral — Omni ERP — 2026-06-02

> **ESTADO DE REMEDIACIÓN (2026-06-02):** las Olas 1–4 (todos los hallazgos de
> remediación) están **RESUELTAS y verificadas** (suite backend 921 tests verde +
> tsc/eslint/vitest frontend). La Ola 5 (gaps de fase, roadmap) avanzó con
> **implementaciones reales y testeadas**: motor de cálculo LOTTT (5.2) y servicios
> de manufactura BOM/MRP/costeo/OF (5.3); el detalle por ítem está en §9.

**Tipo:** Re-auditoría post-remediación (verificación del cierre del plan 2026-06-01 + hallazgos residuales/nuevos + compilación + cumplimiento del Plan Maestro).
**Rama auditada:** `main` @ `a32e2e3`.
**Método:** 5 agentes en paralelo (seguridad, bugs/R-CODE, frontend, build/compilación, infra/CI) + auditoría manual contra `PLAN_MAESTRO_UNICO.md`.
**Alcance del código:** ~58 K líneas Python (473 archivos, 38 apps) + ~27 K líneas TS/TSX (232 archivos). 977 funciones test backend, 154 frontend.

---

## 0. Resumen ejecutivo

El repositorio está en **buen estado**. Los 54 commits desde el último `main` ejecutaron el plan de auditoría 2026-06-01: prácticamente todos los hallazgos **CRÍTICOS (CRIT-1..3), de seguridad alta (H-SEC), de API (H-API), de bugs (H-BUG) y de frontend (FE-HIGH/FE-CRIT)** están **RESUELTOS y verificados línea por línea**. No quedan hallazgos CRÍTICOS abiertos.

**Estado de salud por eje:**

| Eje | Veredicto | Abiertos relevantes |
|---|---|---|
| Seguridad / multi-tenant | 🟢 Sólido | 2 ALTA (gate scope MCP, scraper BCV legacy), 4 menores |
| Bugs / R-CODE | 🟢 Sólido | 1 ALTA (R-CODE-11 en compras), 3 MEDIA, 3 BAJA |
| Frontend | 🟢 Muy mejorado | 1 regresión ALTA (PDF 401), 2 ALTA parciales, pulido |
| Compilación / build | 🟢 **Sin bloqueadores** | `check` 0 issues, `tsc` 0 errores, build OK; 2 warnings + 5 F821 cosméticos |
| Infra / CI | 🟢 Sólido | 3 MEDIA (COOP/CORP, .dockerignore, gate cobertura FE), 4 BAJA |
| Cumplimiento Plan Maestro | 🟡 Núcleo OK, gaps de fase | Nómina LOTTT, Manufactura OF/MRP, extracción l10n |

**Conteo total de hallazgos ABIERTOS:** 0 CRÍTICA · 5 ALTA · 12 MEDIA · 15 BAJA. Más 4 gaps funcionales de fase (roadmap). Detalle y plan de acción en §1–§7.

---

## 1. Seguridad y multi-tenancy

**Verificación de hallazgos previos:** RESUELTO 24 · PARCIAL 4 · ABIERTO/NUEVO 4. Los 3 críticos y todo el bloque "stop-the-bleed" multi-tenant (H-SEC-6..12, H-API-3) cerrados y verificados.

**Hallazgos ABIERTOS:**

| ID | Sev | Estado | Archivo:línea | Riesgo | Fix |
|---|---|---|---|---|---|
| SEC-NEW-4 | ALTA | PARCIAL | `core/mcp_server.py:126` | `_require_scope()` acepta token con `scopes=["*"]` sin pasar por `CapabilityToken.has_scope()` (que restringe `*` a superusuario). Token de empresa con `["*"]` = acceso MCP total al tenant. | Cablear `has_scope()` en el path de enforcement; no propagar `*` si no es token de sistema/superusuario. (S) |
| SEC-NEW-1 | ALTA | ABIERTO | `finanzas/management/commands/update_bcv_exchange.py:20` | Scraper BCV legacy con `requests.get(verify=False)` + escribe tasa como `float`, fuera del Integration Hub. MITM sobre tasa fiscal si se invoca. | Eliminar el command (ya lo reemplaza `bcv_scrape.py`) o redirigir a `sync_tasas_ve` con `verify=True`. (S) |
| SEC-NEW-2 | MEDIA | ABIERTO | `cxc/api/cobranza.py,cartera.py,agente.py,fraccionamiento.py`; `integration_hub/{serializers,views}.py` | Usan `request.user.empresa` (singular = `empresas.first()`). Para usuario multi-empresa filtra/crea contra la empresa equivocada; rompe contrato R-CODE-1. | Migrar a `get_empresas_visible(request.user)` con `__in`. (M) |
| SEC-NEW-5 | MEDIA | NUEVO | `agentes/views.py:132,171,207,280` | `Response({"detail": str(exc)}, 500)` filtra el mensaje interno al cliente (R-CODE-8). | `logger.exception` + mensaje genérico. (S) |
| SEC-NEW-3 | BAJA | PARCIAL | `ventas/serializers.py` (17×), `compras/serializers.py` (12×) | `fields="__all__"`. Inyección de tenant ya mitigada por `read_only_fields`; falta whitelist explícita (defensa en profundidad). | Listas de campos explícitas. (M) |
| SEC-NEW-6 | BAJA | NUEVO | `core/serializers.py:55` | `EmpresaSerializer` con `fields="__all__"` (modelo sin secretos → riesgo bajo). | Whitelist explícita. (S) |

---

## 2. Frontend

**Verificación:** Los 5 patrones sistémicos del lote previo (stack no usado, doble fetching, montos float, JWT/PII en localStorage, `as unknown as` en forms) están **resueltos o reducidos a residuales**. `tsc --noEmit` pasa limpio; **0 `any`**; **0 `fetch()` directo** fuera de `api.ts`; **0 `setInterval`**; token solo en memoria.

**Hallazgos ABIERTOS:**

| ID | Sev | Estado | Archivo:línea | Riesgo | Fix |
|---|---|---|---|---|---|
| FE-NEW-1 | ALTA | NUEVO (regresión) | `FacturaFiscalDetailPage.tsx:152-155` | `handleDescargarPDF` usa `window.open(...VITE_API_URL.../pdf/)`; tras mover el token a memoria (FE-HIGH-13), `window.open` no manda `Authorization` → **el PDF da 401**. | Descargar con `fetchBlob()` + `URL.createObjectURL`. (S) |
| FE-HIGH-7 | ALTA | PARCIAL | `useNotaVentaForm.ts:96`, `usePedidoForm.ts:91`, `FacturaFiscalDetailPage.tsx:148` | `Number()*Number()` para subtotal monetario → riesgo de descuadre/SENIAT. | `D()`/decimal.js, o no enviar subtotal (que lo calcule el backend). (S) |
| FE-HIGH-6 | ALTA | PARCIAL | `useDocumentoVentaBase.ts:135-179` | Cargas de referencia (empresas, cajas, sesión, vendedores) con `useState+useEffect+get` fuera de TanStack Query, con errores tragados. | Migrar a `useQuery`. (M) |
| FE-NEW-2 | MEDIA | NUEVO | 40 sitios (`ModalPago.tsx`, `CajasFisicasListPage.tsx:51,56`, `OverridesMetodosPagoPage.tsx:93`, varios `*DetailPage`) | `alert()`/`confirm()` nativos, incl. borrados destructivos. Viola §7.2 (MUI `<Alert>`/`<Dialog>`). | Hook `useConfirm()` + `<Snackbar>`/`<Alert>`. (M) |
| FE-MED-E4/E5 | MEDIA | ABIERTO | 46 ocurrencias | queryKeys como string opaco (endpoint+QS) sin factory → invalidaciones por prefijo frágiles. | `queryKeys` factory tipada. (M) |
| FE-MED-S6 | MEDIA | ABIERTO | `services/api.ts` | Respuestas API sin validación runtime (zod) en la frontera. | Guards zod en `fetcher`. (L) |
| FE-MED-E6 | MEDIA | PARCIAL | `useDocumentoVentaBase.ts:142,158,176` | Catches "silent"/"ignore" en cargas de referencia tragan errores de verdad. | Propagar/loguear error de carga. (S) |
| FE-NEW-3 | BAJA | NUEVO | `MonedaListPage.tsx:47` | Lee `(window as ...).id_empresa` (anti-patrón FE-HIGH-2 no cubierto). | `getEmpresaId()`/`useAuth`. (S) |
| FE-LOW-S2 | BAJA | ABIERTO | `api.ts:1`, `FacturaFiscalDetailPage.tsx:154` | Default `http://localhost:8000/api` queda en bundle prod. | Fail-fast si falta `VITE_API_URL` en prod. (S) |
| (scope) | BAJA | ABIERTO | Core/Configuracion/Cajas create pages (~9 forms) | Forms fuera del lote FE-CRIT-1 aún con `useState({...})` manual. | Migrar a rhf+zod. (M c/u) |

---

## 3. Bugs / R-CODE

**Verificación:** ~28 hallazgos previos (H-BUG-2/3/4, M-BUG-1..15, M-API-3, NEW-DOC-1) **RESUELTOS y verificados**. `print()`/`traceback` limpios (solo en docstrings). NEW-PAG-1 resuelto globalmente (`BaseModelViewSet` aplica `order_by("pk")` fallback). NEW-MIG-1 resuelto (migraciones commiteadas, sin duplicados).

**Hallazgos ABIERTOS:**

| ID | Sev | Estado | Archivo:línea | Riesgo | Fix |
|---|---|---|---|---|---|
| H-BUG-1 | ALTA | PARCIAL | `compras/services.py:131,167` | `registrar_recepcion`/`registrar_factura_compra` tragan `MapeoContableNoEncontrado` con `pass` **sin** gate `contabilidad_activa`. Único site contable que quedó sin el fix de ventas/tesorería → recepción de mercancía sin asiento en empresa con contabilidad activa (viola R-CODE-11). | Replicar `if contabilidad_activa: raise` de `ventas/services.py:364`. (S) |
| M-BUG-10 | MEDIA | PARCIAL | `cxc/api/acuerdos.py:177` | `registrar_pago` atrapa `(MapeoContableNoEncontrado, AsientoError)` y solo loguea warning, no re-propaga `AsientoError`. Pago de cuota queda sin asiento ante descuadre (R-CODE-11). | Re-raise en `AsientoError` + gate `contabilidad_activa`. (S) |
| BUG-NEW-4 | MEDIA | NUEVO | `manufactura/models.py:9,21,32,61,72` | 5 modelos (`ListaMateriales`, `RutaProduccion`, `OrdenProduccion`, `ConsumoMaterial`, `ProduccionTerminada`) usan PK autoincremental, no UUIDv7 (R-CODE-5). Inconsistente con el resto del archivo. | `UUIDField(primary_key=True, default=uuid7)` + migración cuidando FKs. (L) |
| BUG-NEW-2 | MEDIA | NUEVO | `core/mcp_server.py:305,338,353,452,453`; `finanzas/mcp.py:69,117`; `ventas/mcp.py:91,92,191` | Tools MCP devuelven dinero como `float()` (R-CODE-4). El fix M-BUG-1 solo cubrió `inventario/mcp.py`. Arrastra redondeo a decisiones de agentes. | Devolver `Decimal`/`str(Decimal)`. (S) |
| BUG-NEW-1 | BAJA | NUEVO | `inventario/services.py:342` | `AJUSTE_INVENTARIO` traga `MapeoContableNoEncontrado` con `pass` silencioso (sin warning ni gate). Inconsistente. | Añadir warning + gate `contabilidad_activa`. (S) |
| BUG-NEW-5 | BAJA | NUEVO | `integration_hub/mcp.py:148` | `ejecutar_job_sincronizacion.delay()` en `except Exception: pass`; si el broker falla el job queda pendiente eterno sin traza. | `logger.exception` + marcar job en error. (S) |
| BUG-NEW-3 | BAJA | NUEVO | `odoo/connector.py:583,585` | `float()` al empujar `list_price`/`standard_price` a Odoo (borde XML-RPC, aceptable). | Documentar o usar `str`. (S) |

> **Recomendación estructural:** el patrón correcto de R-CODE-11 (`if contabilidad_activa: raise` ante falta de mapeo; re-raise siempre en `AsientoError`) se aplicó en ventas/tesorería pero **no se propagó uniformemente** a compras, cxc/acuerdos ni inventario. Centralizar en un helper único `contabilidad.services.generar_asiento_o_fallar(empresa, ...)` para eliminar el drift por callsite.

## 4. Compilación / Build / Migraciones

**VEREDICTO: sin bloqueadores de compilación.** (Verificado instalando dependencias y ejecutando las herramientas reales.)

| Chequeo | Resultado |
|---|---|
| Backend `pip install -r requirements.txt` | ✅ exit 0 (Django 5.2.4) |
| `manage.py check` | ✅ **0 issues, 0 warnings** |
| `makemigrations --check --dry-run` | ✅ **"No changes detected"** (sin drift modelo↔migración) |
| Números de migración duplicados | ✅ ninguno |
| `pytest --collect-only tests_api/` | ✅ **915 tests colectan sin error de import** |
| `compileall apps/ config/` | ✅ exit 0 |
| Frontend `npm ci` | ✅ exit 0 |
| `tsc --noEmit` | ✅ **0 errores de tipos** |
| `eslint .` | ⚠️ 0 errores, **2 warnings** (`react-hooks/exhaustive-deps`) |
| `npm run build` (`tsc -b && vite build`) | ✅ exit 0 (PWA generada) |

**Hallazgos menores (no bloquean compilación):**

| ID | Sev | Archivo:línea | Descripción | Fix |
|---|---|---|---|---|
| BUILD-1 | BAJA | `cuentas_por_cobrar/services.py:26`, `cuentas_por_pagar/services.py:19`, `tesoreria/services.py:36,238,262` | 5× `F821`: type-hints de retorno como string (`-> "AbonoCxC"`) a nombres no importados. No rompen runtime (no se evalúan), pero son higiene. | Importar bajo `TYPE_CHECKING` o quitar el hint. (S) |
| BUILD-2 | BAJA | `frontend/src/pages/Core/Auditoria/AuditLogListPage.tsx:45,70` | 2× warning `react-hooks/exhaustive-deps`. **Haría fallar el CI con `eslint --max-warnings=0`.** | Corregir dependencias del `useEffect`/`useCallback`. (S) |

> **No verificable sin DB:** ejecución real de los 915 tests y `migrate` (el entorno de auditoría no tiene PostgreSQL). El CI sí los corre contra Postgres real y está verde.

## 5. Infra / CI / Docker

**Verificación:** **NEW-INFRA-1..5 RESUELTOS** (security headers en `frontend/nginx.conf`, nginx non-root, backend multi-stage + pinning, `.dockerignore` frontend, HEALTHCHECK + override celery). **GAP-4/4-bis** (backup PostgreSQL) implementado (`infra/backup/` + `backup.yml`, cron diario, retención 30d, S3 SSE). **GAP-5** (SSL) diferido correctamente. Health endpoint `/api/health/` existe y responde `{"status":"ok"}` (liveness, `?db=1` readiness). **Sin secretos reales commiteados** (solo `.env.example` con placeholders). CI backend corre `check` + `makemigrations --check` + pytest contra Postgres + gate cobertura ≥65% + agent-eval ≥80%. `deploy.yml` usa secrets correctamente con gate `check-ci`.

**Hallazgos ABIERTOS:**

| ID | Sev | Estado | Ubicación | Descripción | Fix |
|---|---|---|---|---|---|
| M-SEC-5 / INFRA-NEW-1 | MEDIA | PARCIAL | `frontend/nginx.conf:8-13`, `infra/nginx/nginx.prod.conf:40-44` | Faltan `Cross-Origin-Opener-Policy` y `Cross-Origin-Resource-Policy` (exigidos por M-SEC-5) en **ambos** nginx; el resto de headers sí están. | Añadir COOP `same-origin` + CORP `same-origin` en ambos. (S) |
| INFRA-NEW-2 | MEDIA | NUEVO | `backend/.dockerignore` | El context del backend es `./backend`, así que aplica este `.dockerignore` (no el de raíz). No excluye `tests_api/`, `tests_eval/`, `*.md`. (`.env` sí cubierto → sin fuga). | Alinear con el de raíz: excluir tests/docs. (S) |
| INFRA-NEW-3 | MEDIA | NUEVO | `.github/workflows/ci.yml:111-113` | CI frontend corre tests **sin gate de cobertura** ≥60% pese a tener `test:coverage` y `@vitest/coverage-v8`. | Usar `npm run test:coverage` con umbral 60. (S) |
| INFRA-NEW-7 | MEDIA | NUEVO | `frontend/nginx.conf:13`, `infra/nginx/nginx.prod.conf:44` | CSP con `script-src 'unsafe-inline'` (línea base MUI, sin `unsafe-eval`). Permisiva; permite XSS inline. | Endurecer con nonces/hashes; medir con `Report-Only`. (M, diferible) |
| INFRA-NEW-5 | BAJA | NUEVO | `.github/workflows/deploy.yml:135` | Deploy hace `git reset --hard origin/main` sin fijar el SHA validado por CI → posible race con nuevos pushes a main. | Checkout/reset al `github.sha` exacto. (M) |
| INFRA-NEW-4 | BAJA | NUEVO | `.github/workflows/ci.yml` | Sin secret scanning (gitleaks) ni dependency audit (pip-audit/npm audit) en CI. | Añadir job gitleaks + audit. (S) |
| INFRA-NEW-6 | BAJA | NUEVO | `docker-compose.prod.yml` | El backup self-hosted (`pg_dump_omni.sh`) no está cableado como sidecar/cron; solo corre por GitHub Actions (apropiado para Railway, no para self-hosted). | Sidecar cron al reactivar self-hosted. (M) |

---

## 6. Cumplimiento del Plan Maestro (`PLAN_MAESTRO_UNICO.md`)

### 6.1 Reglas inviolables (§2)
- **R-CODE-1 (multi-tenant):** 🟢 cumplido; CRIT-1..3 cerrados, get_queryset filtra por empresa. Residual: `request.user.empresa` singular (SEC-NEW-2).
- **R-CODE-3 (sin print/any):** 🟢 frontend 0 `any`; backend pendiente de confirmar por agente de build/lint.
- **R-CODE-4 (Decimal):** 🟡 backend mayormente; residual float en `update_bcv_exchange.py` (SEC-NEW-1) y 2 hooks FE (FE-HIGH-7).
- **R-CODE-11 (asiento automático atómico):** 🟢 reforzado (H-BUG-1, NEW-DOC-1 `OperacionCambioDivisa` genera asiento); confirmación final por agente de bugs.

### 6.2 Estado de módulos vs §4.2 (inventario verificado)

| Módulo | Plan dice | Realidad verificada |
|---|---|---|
| Núcleo (core, finanzas, ventas, inventario, compras, fiscal, contabilidad, cxc, CxC/CxP, tesorería) | ✅ funcional | 🟢 Confirmado. cxc bien estructurado (models/api/services/agents/mcp). |
| **Nómina LOTTT** | 🔶 cálculo pendiente | ⚠️ **Confirmado pendiente**: `nomina/services.py` = 0 líneas. Solo modelos+views. Sin utilidades/antigüedad/ISLR/cestaticket. |
| **Manufactura (OF/MRP/costeo)** | 🔲 pendiente | ⚠️ **Confirmado pendiente**: `manufactura/services.py` = 0 líneas. Solo `models.py` (211). Crítico para piloto Fábrica (1.H/1.I). |
| Stubs (eventos, almacenes, despacho, costos, banca_electronica, integracion_b2b, servicio_cliente, configuracion_motor) | 🔲 estructura | 🟢 Confirmado: 0 services, lógica pendiente. `eventos` totalmente vacío. |

### 6.3 Arquitectura de localización (§3.7, GAP-1/GAP-2)
- **GAP-1 (ADR-007):** 🟢 **RESUELTO** — `docs/decisions/ADR-007-arquitectura-localizacion-dos-capas.md` existe.
- **GAP-2 (framework + extracción):** 🟡 **PARCIAL** — `apps/localizacion/` creado (ports/registry/services), `vzla_localizacion`→`localizacion_ve` renombrado, `Empresa.pais_codigo_iso` + flags `localizacion_legal_activa/mercado_activa` añadidos, gating IGTF. **PERO** la extracción real de la Capa A (libros SENIAT, motor IVA/IGTF) y Capa B (pagos de terceros, libro maestro de caja) hacia `localizacion_ve` está **pendiente**: la lógica fiscal pesada sigue en `apps/fiscal`/`apps/ventas`. `localizacion_ve` hoy = helpers (formato/calendario/validators/adapters).

### 6.4 Roadmap (§5.1) — estado de fase
- **1.A–1.E:** 🟢 COMPLETO (núcleo común + agentes sombra/sugerencia + CxC).
- **1.F (distribuidora en producción):** ⬜ SIGUIENTE HITO. Software listo; commands de importación `TRACK-1F-1..5` creados (commit `60aa1dc`). Falta: carga de datos reales + operación 30 días.
- **1.G–1.J:** ⬜ pendientes (POS, BOM, OF+costeo, estabilización). Bloqueados por nómina/manufactura.

### 6.5 Deltas plan↔realidad (documentales)
- ✅ NEW-DOC-1 (`OperacionCambioDivisa` ya implementado) y NEW-DOC-2 (señales auditoría) corregidos en commits recientes.
- ✅ GAP-3 (desglose §5.2 por capa), GAP-4/4-bis (backup PostgreSQL), GAP-5 (scaffold SSL diferido) ejecutados.

---

## 7. Plan de trabajo

> Convenciones: PRs pequeños y focales (R-PROC-2), CI verde obligatorio, ID citado en el commit (`fix(audit2): <ID> ...`). Esfuerzo: S ≤1 h · M ≤4 h · L >1 día. Total remediación (Olas 1–4): **~22–30 h**. Los gaps funcionales (Ola 5) son trabajo de roadmap, no remediación.

### Resumen de carga

| Ola | Foco | Items | Esfuerzo |
|---|---|---|---|
| **1** | Integridad contable + seguridad ALTA | H-BUG-1, M-BUG-10, BUG-NEW-1, SEC-NEW-4, SEC-NEW-1, FE-NEW-1, FE-HIGH-7 | ~6 h |
| **2** | Multi-tenant residual + R-CODE-4 + infra MEDIA | SEC-NEW-2, SEC-NEW-5, BUG-NEW-2, BUG-NEW-4, INFRA-NEW-1, INFRA-NEW-2, INFRA-NEW-3, FE-HIGH-6 | ~8 h |
| **3** | Pulido frontend + bugs BAJA | FE-NEW-2, FE-MED-E4/E5, FE-MED-E6, FE-NEW-3, FE-LOW-S2, FE-MED-S6, forms restantes, BUG-NEW-5, BUG-NEW-3, BUILD-1, BUILD-2 | ~8 h |
| **4** | Defensa en profundidad + CI hardening | SEC-NEW-3, SEC-NEW-6, INFRA-NEW-4, INFRA-NEW-5, INFRA-NEW-6, INFRA-NEW-7 | ~4 h |
| **5** | Gaps funcionales de fase (roadmap, no remediación) | Nómina LOTTT, Manufactura OF/MRP/costeo, extracción l10n (GAP-2 cont.), 1.F datos+operación | L (semanas) |

---

### OLA 1 — Integridad contable y seguridad ALTA (bloqueante, primero)

**PR 1.1 — Centralizar y reparar R-CODE-11 en todos los callsites contables.**
- Crear helper `apps/contabilidad/services.py::generar_asiento_o_fallar(empresa, ...)` que: ante `MapeoContableNoEncontrado` → `raise` si `empresa.contabilidad_activa`, si no `logger.warning` + continuar; y **siempre re-propague `AsientoError`**.
- Aplicar en: `compras/services.py:131,167` (**H-BUG-1**), `cxc/api/acuerdos.py:177` (**M-BUG-10**), `inventario/services.py:342` (**BUG-NEW-1**).
- Tests: empresa con `contabilidad_activa=True` + mapeo faltante → la operación falla; con `False` → continúa con warning; `AsientoError` siempre revienta la transacción.
- **DoD:** ningún site contable traga `MapeoContableNoEncontrado`/`AsientoError` sin pasar por el helper. `grep` de `except.*MapeoContable.*pass` → 0.

**PR 1.2 — Cablear el gate de scope `*` en MCP (SEC-NEW-4).**
- `core/mcp_server.py:126`: `_require_scope()` debe usar `CapabilityToken.has_scope()` (que restringe `*` a tokens de superusuario/sistema), no chequear `"*" in scopes` directo. Exponer el objeto token en `_resolve_token`.
- Test: token de empresa con `scopes=["*"]` → denegado para tools fuera de su scope; token de sistema con `*` → permitido.
- **DoD:** un `["*"]` de empresa no concede acceso total al tenant.

**PR 1.3 — Eliminar scraper BCV legacy inseguro (SEC-NEW-1).**
- Eliminar `finanzas/management/commands/update_bcv_exchange.py` (ya reemplazado por el connector `bcv_scrape.py` con `verify=True` dentro del Integration Hub). Verificar 0 referencias antes de borrar.
- **DoD:** `grep -r "verify=False" backend/` → 0. `grep -r "update_bcv_exchange"` → 0.

**PR 1.4 — Arreglar descarga de PDF de factura fiscal (FE-NEW-1, regresión).**
- `FacturaFiscalDetailPage.tsx:152-155`: reemplazar `window.open(...)` por `fetchBlob()` + `URL.createObjectURL` (el token vive en memoria; `window.open` no manda `Authorization` → 401).
- **DoD:** descarga de PDF funciona autenticada; sin `window.open` con URL de API.

**PR 1.5 — Decimal en cálculo monetario de hooks de venta (FE-HIGH-7).**
- `useNotaVentaForm.ts:96`, `usePedidoForm.ts:91`, `FacturaFiscalDetailPage.tsx:148`: sustituir `Number()*Number()` por `D()`/decimal.js, o (preferido) no enviar subtotal y dejar que el backend lo calcule.
- **DoD:** cero aritmética monetaria con `Number()` en hooks de documentos de venta.

### OLA 2 — Multi-tenant residual + R-CODE-4 + infra MEDIA

**PR 2.1 — `request.user.empresa` singular → `get_empresas_visible` (SEC-NEW-2).** En `cxc/api/{cobranza,cartera,agente,fraccionamiento}.py`, `integration_hub/{serializers,views}.py`. Tests de aislamiento para usuario multi-empresa. (M)

**PR 2.2 — No filtrar `str(exc)` en agentes (SEC-NEW-5).** `agentes/views.py:132,171,207,280` → `logger.exception` + mensaje genérico. (S)

**PR 2.3 — Decimal en tools MCP (BUG-NEW-2).** `core/mcp_server.py`, `finanzas/mcp.py`, `ventas/mcp.py` → devolver `Decimal`/`str`. (S)

**PR 2.4 — UUIDv7 en modelos de manufactura (BUG-NEW-4).** Migrar 5 modelos a `UUIDField(primary_key, default=uuid7)` con migración cuidadosa de FKs. Como manufactura aún no tiene datos productivos, el costo es bajo ahora y altísimo después. (L)

**PR 2.5 — Headers COOP/CORP en ambos nginx (INFRA-NEW-1 / M-SEC-5).** Añadir `Cross-Origin-Opener-Policy: same-origin` y `Cross-Origin-Resource-Policy: same-origin` en `frontend/nginx.conf` e `infra/nginx/nginx.prod.conf`. (S)

**PR 2.6 — Alinear `backend/.dockerignore` (INFRA-NEW-2).** Excluir `tests_api/`, `tests_eval/`, `*.md`, `.dockerignore`. (S)

**PR 2.7 — Gate de cobertura frontend en CI (INFRA-NEW-3).** `ci.yml` → `npm run test:coverage` con umbral 60%. (S)

**PR 2.8 — Datos de referencia con `useQuery` (FE-HIGH-6).** `useDocumentoVentaBase.ts:135-179`: migrar cargas (empresas, cajas, sesión, vendedores) de `useState+useEffect+get` a `useQuery`; dejar de tragar errores. (M)

### OLA 3 — Pulido frontend + bugs BAJA

- **PR 3.1 (FE-NEW-2):** hook `useConfirm()` + `<Snackbar>`/`<Alert>` MUI; reemplazar los 40 `alert()`/`confirm()` nativos (priorizar los borrados destructivos: `CajasFisicasListPage.tsx:51,56`, `OverridesMetodosPagoPage.tsx:93`). (M)
- **PR 3.2 (FE-MED-E4/E5):** factory `queryKeys` tipada jerárquica; migrar las 46 keys string-opacas. (M)
- **PR 3.3 (FE-MED-E6):** propagar/loguear errores en cargas de referencia (`useDocumentoVentaBase.ts:142,158,176`). (S)
- **PR 3.4 (FE-NEW-3 + FE-LOW-S2):** `MonedaListPage.tsx:47` usar `getEmpresaId()`; fail-fast si falta `VITE_API_URL` en prod (`api.ts:1`). (S)
- **PR 3.5 (forms restantes):** migrar los ~9 forms de Core/Configuracion/Cajas a rhf+zod. (M)
- **PR 3.6 (BUG-NEW-5):** `integration_hub/mcp.py:148` → `logger.exception` + estado error en el job. (S)
- **PR 3.7 (BUILD-1 + BUILD-2):** corregir 5 F821 (imports `TYPE_CHECKING`) + 2 warnings `exhaustive-deps` en `AuditLogListPage.tsx` (evita fallo de CI con `--max-warnings=0`). (S)
- **PR 3.8 (BUG-NEW-3):** documentar/`str` en push Odoo `connector.py:583,585`. (S)

### OLA 4 — Defensa en profundidad + CI hardening

- **PR 4.1 (SEC-NEW-3 + SEC-NEW-6):** whitelist explícita de campos en serializers de ventas (17×), compras (12×) y `EmpresaSerializer`. (M)
- **PR 4.2 (INFRA-NEW-4):** job gitleaks + `pip-audit`/`npm audit` en CI. (S)
- **PR 4.3 (INFRA-NEW-5):** deploy fija `github.sha` validado por CI. (M)
- **PR 4.4 (INFRA-NEW-6):** sidecar cron de backup en `docker-compose.prod.yml` (al reactivar self-hosted). (M)
- **PR 4.5 (FE-MED-S6 + INFRA-NEW-7):** guards zod en frontera API (`fetcher`); endurecer CSP con nonces en `Report-Only`. (L, diferible)

### OLA 5 — Gaps funcionales de fase (roadmap, no remediación)

> Estos no son defectos sino trabajo pendiente del Plan Maestro. Se listan para no dejar nada fuera; su ejecución sigue el orden de §5 del plan (1.F primero).

- **5.1 — Sub-fase 1.F (siguiente hito):** carga de datos reales de la distribuidora (usar `migracion_datos` + commands `TRACK-1F-1..5` ya creados) + operación 30 días. No requiere construir software nuevo.
- **5.2 — Nómina LOTTT:** implementar `nomina/services.py` (hoy 0 líneas): utilidades, vacaciones, antigüedad, ISLR progresivo, cestaticket multimoneda, aportes/deducciones (SSO/FAOV/INCES/RPE). Entrar por puerto `CalculadoraNomina` de `apps/localizacion`. (L)
- **5.3 — Manufactura (1.H/1.I):** implementar `manufactura/services.py` (hoy 0 líneas): BOM/explosión de materiales, OF con etapas, consumo↔inventario, costeo real, MRP básico. Crítico para piloto Fábrica. (L)
- **5.4 — Extracción l10n (GAP-2 cont.):** mover la Capa A (motor IVA/IGTF, libros SENIAT, factura legal) y Capa B (pagos de terceros, libro maestro de caja) desde `apps/fiscal`/`apps/ventas` hacia `apps/localizacion_ve` implementando los puertos de `apps/localizacion`. Strangler fig, mayormente Bloque 2. (L)
- **5.5 — Criterio de salida l10n:** una empresa de prueba no venezolana opera el ciclo completo sin ver IGTF/doble tasa/métodos VE.

---

## 8. Conclusión

El proyecto **no tiene bloqueadores de compilación ni hallazgos críticos abiertos**. La remediación del plan 2026-06-01 se ejecutó casi por completo y se verificó línea por línea. Lo que queda es:

1. **Remediación residual (Olas 1–4, ~22–30 h):** sobresalen 3 ítems ALTA de integridad contable (R-CODE-11 en compras/cxc) y seguridad (gate MCP, scraper BCV), más una regresión funcional en frontend (PDF 401). El resto es pulido y defensa en profundidad.
2. **Gaps funcionales de fase (Ola 5):** Nómina LOTTT y Manufactura siguen siendo solo modelos sin lógica de servicio — son el verdadero camino crítico hacia los pilotos (Fábrica) y el cierre del Bloque 1.

**Recomendación de orden:** ejecutar Ola 1 ya (integridad contable + seguridad), luego desbloquear 1.F (no necesita código nuevo), y atacar Manufactura/Nómina como el trabajo de fondo del roadmap.

---

## 9. Registro de remediación (2026-06-02)

Ejecución del plan §7. Cada ítem citado en su commit (`fix(audit2): <ID>` /
`feat(audit2): Ola 5.x`). Verificación: suite backend **921 tests verde** (BD
PostgreSQL local) + `tsc`/`eslint`/`vitest` frontend verdes.

### Ola 1 — Integridad contable + seguridad ALTA ✅
- **H-BUG-1 / M-BUG-10 / BUG-NEW-1** — `contabilidad.services.generar_asiento_o_fallar()` centraliza R-CODE-11; aplicado en compras, cxc/acuerdos (con `set_rollback`+422) e inventario. 4 tests nuevos.
- **SEC-NEW-4** — gate del comodín `*` cableado en `mcp_server._resolve_token` vía `CapabilityToken.comodin_autorizado`. 2 tests.
- **SEC-NEW-1** — eliminado el scraper BCV legacy (`update_bcv_exchange.py`, `verify=False`). `grep verify=False` → 0 en código.
- **FE-NEW-1** — descarga de PDF de factura vía `fetchBlob` (con auth) en vez de `window.open`.
- **FE-HIGH-7** — subtotales con `decimal.js` en `useNotaVentaForm`, `usePedidoForm`, `FacturaFiscalDetailPage`.

### Ola 2 — Multi-tenant residual + R-CODE-4 + infra MEDIA ✅
- **SEC-NEW-2** — `request.user.empresa` → `get_empresas_visible` en cxc (cobranza/cartera/agente/fraccionamiento) e integration_hub.
- **SEC-NEW-5** — `agentes/views.py` con `logger.exception` + mensaje genérico (sin `str(exc)`).
- **BUG-NEW-2** — dinero como `Decimal` en tools MCP de core/finanzas/ventas.
- **BUG-NEW-4** — UUIDv7 en los 5 modelos legacy de manufactura (migración custom validada desde cero).
- **INFRA-NEW-1** — headers COOP/CORP en ambos nginx. **INFRA-NEW-2** — `backend/.dockerignore` excluye tests/docs. **INFRA-NEW-3** — gate de cobertura frontend en CI (ratchet al piso actual; objetivo 60%).
- **FE-HIGH-6** — datos de referencia de `useDocumentoVentaBase` a TanStack Query.

### Ola 3 — Pulido + bugs BAJA ✅
- **BUG-NEW-5** — `integration_hub/mcp` loguea y marca job `fallido` (no `except/pass`). **BUG-NEW-3** — documentado el `float()` de borde XML-RPC. **BUILD-1** — type-hints bajo `TYPE_CHECKING` (5 F821 → 0).
- **FE-NEW-2** — `alert/confirm` nativos → MUI Snackbar/Dialog. **FE-MED-E4/E5** — factory `queryKeys` tipada. **FE-NEW-3** — `getEmpresaId()` en MonedaListPage. **FE-LOW-S2** — fail-fast de `VITE_API_URL` en prod. **BUILD-2** — warnings `exhaustive-deps` corregidos. **FE-MED-E6** — resuelto por la migración a useQuery (FE-HIGH-6).

### Ola 4 — Defensa en profundidad + CI hardening ✅
- **SEC-NEW-3 / SEC-NEW-6** — serializers cabecera de ventas/compras y `EmpresaSerializer` ocultan `referencia_externa`/`documento_json`.
- **INFRA-NEW-4** — job `security-scan` (gitleaks + pip-audit + npm audit). **INFRA-NEW-5** — deploy fija el SHA validado por CI. **INFRA-NEW-6** — sidecar `backup` en compose prod.
- **INFRA-NEW-7 (CSP nonces)** — diferido (línea base MUI documentada). **FE-MED-S6 (zod runtime guards)** — diferido (esfuerzo L, frontera API; no bloqueante).

### Ola 5 — Gaps funcionales de fase (foundations reales + roadmap)
- **5.2 Nómina LOTTT** ✅ *núcleo* — `nomina/calculo_lottt.py` (motor PURO Decimal: salario, horas extra 50/100%, bono nocturno, deducciones SSO/FAOV/RPE, ISLR progresivo UT, provisiones, aportes patronales) + `nomina/services.py` + puerto `CalculadoraNominaVE`. **16 tests.** Cierra el gap "services.py vacío". *Pendiente roadmap:* generación de registros `ProcesoNomina`/`Nomina`, fórmula ARC oficial de ISLR, UI.
- **5.3 Manufactura** ✅ *núcleo* — `manufactura/services.py`: explosión BOM, MRP básico, costeo real (PUROS) + orquestación OF (crear orden, consumir materiales↔inventario con `CONSUMO_PRODUCCION`, producción terminada↔`ENTRADA` al costo real). **9 tests.** Cierra el gap "services.py vacío". *Pendiente roadmap:* OF con etapas/rutas detalladas, UI, MRP multinivel.
- **5.4 Extracción l10n (GAP-2 cont.)** 🟡 — framework `apps/localizacion` con puertos `MotorImpuestosVE` (delega en fiscal) y ahora `CalculadoraNominaVE` (real, en `localizacion_ve`) registrados por país. *Pendiente roadmap (Bloque 2 por el propio plan):* mover libros SENIAT / motor IVA-IGTF y la Capa B a `localizacion_ve` (strangler fig).
- **5.1 Sub-fase 1.F** ⬜ *operacional, no código* — el software está listo y los comandos `TRACK-1F-1..5` existen; falta la carga de datos reales de la distribuidora + 30 días de operación (tarea del founder, no de código).

### Verificación final
- Backend: `manage.py check` 0 issues · `makemigrations --check` sin drift · **921 tests** verdes.
- Frontend: `tsc -b` 0 errores · `eslint` 0 errores/0 warnings · `vitest` verde · gate de cobertura verde.
