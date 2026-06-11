# Auditoría integral — 2026-06-10

**Alcance:** toda la documentación de planificación (`docs/`), verificación del estado real
del código contra lo planificado, auditoría de seguridad del backend (38 apps) y auditoría
de bugs/correctness con énfasis en el dominio financiero. Ejecutada con agentes en paralelo
y **verificación manual de los hallazgos críticos** (línea por línea) antes de publicarlos.

**Veredicto ejecutivo:**

1. La base es sólida: cobertura backend 93.25%, mutation ≥80% en módulos críticos,
   aislamiento multi-tenant verificado por guards automáticos, 0 secretos en código,
   0 inyección SQL, configuración prod fail-closed.
2. **Pero hay una fuga cross-tenant activa y explotable** (métodos de pago, hallazgos
   SEC-A1/A2/A3) y **dos bugs críticos de integridad financiera** (abonos CxC por CRUD
   abierto, pagos que no mueven saldos). Son el P0 del nuevo roadmap.
3. La documentación es honesta pero estaba fragmentada en 4 fuentes de estado y el
   plan maestro llevaba ~10 días por detrás de la realidad. Esta auditoría consolida
   todo en [`docs/PLAN_MAESTRO_UNICO.md`](../PLAN_MAESTRO_UNICO.md) (ver su §5.2).

---

## 1. Gate de verificación (estado real medido)

| Verificación | Resultado |
|---|---|
| `manage.py check` | ✅ verde (0 issues) |
| `makemigrations --check --dry-run` | ✅ sin migraciones pendientes |
| Suite backend completa (`tests/` + `tests_api/`, `-n auto`, Postgres real) | ✅ **3620 passed, 12 skipped, 0 failed** · cobertura **92.97%** (gate 92 superado) · 10m03s |
| Frontend `tsc -b` | ✅ verde |
| Frontend `npm run lint` | ✅ verde (0 findings) |
| Frontend `npm test -- --run` | ✅ 205/205 tests verdes (40 archivos) |
| CI (`.github/workflows/ci.yml`) | ✅ gates bloqueantes: check+migraciones+mapa_superficie, pytest (Postgres 17), diff-cover ≥95 (PR), tsc+eslint+drift OpenAPI+vitest ≥60, agent-eval ≥80, gitleaks, pip-audit, npm critical, bandit MEDIUM+, semgrep ERROR, ruff, mypy dinero. No bloqueantes aún: trivy, schemathesis, E2E (Fase 5 cero-dudas) |
| Ramas | `main` = prod, árbol limpio. **`develop` está 6 commits detrás de `main`** — pendiente sincronizar (FLUJO_DE_TRABAJO: "no dejarlo divergir") |

**Divergencias docs↔código detectadas** (el código está *por delante* de la doc, no al revés):
plan maestro decía 850 tests/cov 65% (real: ~3.5k tests, ratchet 92); conector **Google Sheets**
del Hub existe (backend+Celery+UI) y no figuraba en el plan; `apps/localizacion_ve` no es app
Django instalada sino paquete de adapters consumido vía el registry de `apps/localizacion`;
frontend sin páginas para compras/CxP/contabilidad/tesorería/RRHH (API-only, consistente con
R-CODE-7). **Acción operativa pendiente:** verificar el secret `BACKUP_DB_HOST` en GitHub —
si falta, `backup.yml` se omite en silencio y el backup nocturno declarado no corre (GAP-4-bis).
Nada declarado "completo" en los docs resultó inexistente en el código.

## 2. Auditoría documental — resultado y acciones tomadas

### 2.1 Estado declarado vs real (divergencias corregidas en esta entrega)

| Documento | Problema encontrado | Acción |
|---|---|---|
| `PLAN_MAESTRO_UNICO.md` | §3.8 decía ADR-007 "por redactar" (aceptado 2026-06-01) y faltaba ADR-009; §4.1 decía "850 tests / cobertura ≥65%" (real: 3534 / 93.25%); §3.1 marcaba security headers "pendiente" (hechos); §5.2 Paso 0 marcaba bloqueante la Semana 1 de la auditoría 06-01 (cerrada) | **Actualizado** — §5.2 reescrito como roadmap único consolidado con DoD |
| `docs/README.md` | Índice sin ADR-007/008/009, sin `planes/`, `audit/`, `auditorias/`; describía `ctf/` como "retos de seguridad" (son Compromisos Técnicos Fechados) | **Reescrito** |
| `planes/README.md` | Plan C "PLANIFICADO" (C1–C3 completas), Plan D "APROBADO" (D1/D2/D4 hechas), Plan 0 "PLANIFICADO" (0.1/0.4 hechas) | **Estados actualizados** |
| `ctf/README.md` | CTF-007 (picomatch, abierto) ausente del índice | **Añadido** |
| `audit/HANDOFF_CERO_DUDAS_2026-06-07.md` | Superado en 48h por `ESTADO_PLAN_CERO_DUDAS.md` (decía 71% cobertura / "Fase 3 arrancada" vs 93.25% / "Fase 3 CERRADA") | **Archivado** en `_archive/` (su contenido vigente —branch protection pendiente del owner, comandos mutmut locales— ya está en ESTADO) |
| `auditorias/PLAN_TRABAJO_AUDITORIA_2026-06-01.md` | 127 ítems sin tablero de cierre; Sem-1 y varios GAP/TRACK ya ejecutados sin marcar | **Cerrado y archivado** con nota de cierre; su §11 (frontend) migra como workstream F del plan maestro §5.2 |
| `audit/CVE_REMEDIACION_2026-06-02.md` | Decía 4 bumps major pendientes "(CTF)" sin CTF; hoy `mcp>=1.23`, `lxml 6.1.0`, `cryptography 46.0.7` y Django 5.2.15 ya están en requirements | Sin acción de código; constancia aquí: **los bumps ya se hicieron**, no se requiere CTF |
| `tech-debt/INVENTORY.md` | Enlace roto a `AUDITORIA_2026-06-02.md` (movida a `_archive/`); no recogía los ~30 bugs del backfill Fase 3 | **Actualizado** |

### 2.2 CTFs (a 2026-06-10)

5 cerrados (001–004, 009), **9 abiertos, 0 vencidos**. Próximos a vencer:
**CTF-006** y **CTF-012** (2026-08-01), **CTF-013** (2026-08-15). CTF-012 (rol BD no-dueño)
es el de mayor impacto: bloquea `RLS_ENABLED=True` en producción.

### 2.3 ADRs

Los 9 ADRs están redactados y aceptados. ADR-001 (offline) es el único con
implementación pendiente (Plan A / CTF-008).

---

## 3. Auditoría de seguridad (backend)

> Verificación previa: los hallazgos de `docs/audit/SECURITY_REVIEW_2026-06-02.md`
> (SEC-NEW-1..6) siguen resueltos, salvo que el patrón `str(exc)` reapareció en otros
> módulos (SEC-M4). CTF-005 (`fields="__all__"`) sigue abierto y **dejó de ser teórico**
> (ver SEC-A3).

### ALTO — fuga cross-tenant activa en métodos de pago (verificada manualmente)

**SEC-A1 — IDOR de lectura: `MetodoPagoViewSet.get_object` sin scope para `reutilizar`** (CWE-639)
`apps/finanzas/views.py:260-264` — bypasea `get_queryset()` deliberadamente: cualquier
usuario autenticado que conozca el UUID de un `MetodoPago` privado de otra empresa puede
operarlo. El serializer expone `documento_json` y `referencia_externa` (config de pago).
**Fix:** eliminar el override; si "reutilizar" requiere fuentes ajenas, limitarlas a
`es_publico=True | es_generico=True`.

**SEC-A2 — Escritura cross-tenant: `reutilizar` no valida la empresa destino** (CWE-639)
`apps/finanzas/views.py:324-330` — `Empresa.objects.get(id_empresa=...)` con el id del
body **sin contrastar con `get_empresas_visible`**: se puede crear `MetodoPago` en
cualquier empresa, copiando `documento_json` ajeno. El 409 (línea ~350) además filtra
nombres de métodos del tenant víctima.
**Fix:** `get_empresas_visible(request.user).filter(pk=id_empresa)` → 404 si no.

**SEC-A3 — Exposición cross-tenant por diseño: `buscar_reutilizar`** (CWE-200)
`apps/finanzas/views.py:285-307` — el queryset incluye `~Q(empresa__in=excluir) & ~Q(empresa=None)`,
es decir, **los métodos de pago privados de TODOS los demás tenants**, serializados con
`__all__`. Explotable con un GET autenticado, sin necesidad de UUIDs.
**Fix:** restringir a `es_publico=True | es_generico=True` y proyectar solo campos no sensibles.

### MEDIO

**SEC-M1 — Sistémico: FKs relacionadas sin scope de tenant en serializers** (CWE-639)
`apps/ventas/serializers.py:35-36,59,221,240,272,304,336,369,416`, `apps/finanzas/serializers.py:548-549,889-891`
y todo ModelSerializer con FK writable (DRF autogenera el campo con el manager completo).
Ejemplo: `POST /api/ventas/detalle-pedidos/` con `id_pedido` ajeno inserta líneas en el
pedido de otro tenant; `POST /api/ventas/pedidos/` con `id_cliente` ajeno devuelve
nombre/RIF/teléfono del cliente víctima. Mitigantes: UUIDv7 no adivinables; RLS solo en
15 tablas piloto y con `RLS_ENABLED=False` por defecto. Los tests de aislamiento cubren
GET/PATCH/DELETE pero **no la inyección de FK en CREATE**.
**Fix:** mixin estándar que acote el `queryset` de toda FK tenant-aware a
`get_empresas_visible` + test paramétrico "POST con FK ajena → 400".

**SEC-M2 — `MetodoPagoEmpresaActivaSerializer` acepta `empresa` del cliente**
`apps/finanzas/serializers.py:31-53` — `empresa` writable; `create()` solo inyecta la del
usuario si el cliente no la envió. **Fix:** `empresa` read-only + inyección estilo `EmpresaInjectMixin`.

**SEC-M3 — Superusuario `admin/admin123` hardcodeado** (CWE-798)
`apps/core/management/commands/create_initial_data.py:54-62`. Existe alternativa segura
(`seed_empresa_inicial`). **Fix:** borrar el comando o gate `if not settings.DEBUG: raise CommandError`.

**SEC-M4 — Reaparición de `str(exc)` al cliente** (CWE-209)
`apps/integration_hub/views.py:114,120,302,335` (errores de conectores crudos),
`apps/cxc/api/agente.py:83` (SSE emite `str(exc)` de cualquier excepción),
`apps/ventas/views.py:634,745` y `apps/cuentas_por_cobrar/views.py:129` (ImportError, bajo).
**Fix:** mensaje genérico + `logger.exception` (patrón ya aplicado en `agentes/views.py`).

### BAJO

- **SEC-B1** — guard TEST-1 no cubre modelos "detalle" (FK a Empresa a 2 saltos):
  `tests/tenant/test_aislamiento_cobertura.py:36-41`. Extender `_empresa_fk_field`.
- **SEC-B2** — `fiscal/views.py:46`: `id__in` sobre `Empresa` (pk es `id_empresa`) probablemente
  lanza `FieldError` (500). Falla cerrado, pero es bug.
- **SEC-B3** — `monedas_info` acepta `?empresa=` sin validar (catálogo, sensibilidad baja).
- **SEC-B4** — higiene local: `backend/db.sqlite3` y `backend/sqlite-tools/` en el árbol
  (no trackeados); borrar por R-CODE-2.

### Áreas verificadas limpias

AuthN/AuthZ global (DRF `IsAuthenticated` default + guard anti-`AllowAny` + JWT con refresh
httpOnly rotado + throttling login/refresh/signup) · aislamiento del grueso de los 159
`get_queryset` (muestreo amplio) · 0 raw SQL/eval/exec/subprocess en `apps/` · 0 secretos
reales en código/git · settings prod fail-closed (HSTS, SSL redirect, cookies Secure,
guard anti CORS-all) · uploads validados (extensión, magic bytes, S3 prefirmado por empresa) ·
dependencias al día (Django 5.2.15, DRF 3.16, celery 5.6.3, mcp≥1.23, lxml 6.1, cryptography 46) ·
Celery/MCP/commands sin input de usuario sin validar (MCP exige capability token con scope y empresa fija).

---

## 4. Auditoría de bugs / correctness (dominio financiero)

### CRÍTICO

**BUG-C1 — CRUD abierto de `AbonoCxC` bypassa toda la lógica de abonos (y cruza tenants)**
`apps/cuentas_por_cobrar/views_abono.py:7-15` + `serializers_abono.py` (`fields="__all__"`).
`AbonoCxCViewSet` es ModelViewSet completo sin `perform_create`: por POST se crea un abono
sin lock, sin tope de saldo, sin actualizar `cxc.estado`, con monto negativo o mayor al
saldo, y apuntando a una CxC de **otra empresa** (el create no valida tenant). DELETE deja
la CxC en `pagada` con saldo pendiente. Toda la lógica correcta vive solo en
`registrar_abono` (`services.py:32`, que sí es atómico y con lock).
**Fix:** `ReadOnlyModelViewSet`, o delegar create a `registrar_abono` + validar tenant + bloquear update/delete.

**BUG-C2 — Side-effects de Pago en el ViewSet equivocado: los pagos no mueven saldos**
`apps/finanzas/views.py:985-1061` — el `perform_create` que crea `TransaccionFinanciera` +
`MovimientoCajaBanco` + actualización de `saldo_actual` está en **`CajaFisicaViewSet`**
(trata el objeto creado como `pago`; `CajaFisica` no tiene esos campos → todo POST de caja
física revienta con AttributeError 500). El `perform_create` real de **`PagoViewSet`**
(`views.py:1091-1107`) solo emite una notificación: al crear un `Pago` por API **nunca** se
crea transacción ni movimiento ni se actualizan saldos.
**Fix:** mover el bloque a un service llamado desde `PagoViewSet` con `transaction.atomic`
+ `select_for_update` sobre caja/cuenta.

### ALTO

**BUG-A1 — `transferencia_entre_cajas` sin atomicidad, sin lock, sin validaciones**
`apps/finanzas/utils_transferencias.py:8-49` — sin `transaction.atomic` (si falla la
entrada, la salida ya descontó), sin `select_for_update` (carreras pierden actualizaciones),
no valida `monto > 0`, ni saldo suficiente, ni que origen y destino tengan la misma moneda
(transfiere USD→VES sumando sin conversión).

**BUG-A2 — Pago de cuotas de acuerdo: sobrescritura de parciales + carrera + moneda sin convertir**
`apps/cxc/api/acuerdos.py:146-154` + `api/serializers.py:87-94` — `monto_pagado = data["monto"]`
**sobrescribe** en vez de acumular (pagos parciales se pierden); `monto` sin `min_value`
(acepta ≤0); el check "ya pagada" ocurre fuera del `atomic` y sin lock (doble cobro
concurrente); compara monto en la moneda del pago contra la moneda del acuerdo sin convertir
(100 VES "saldan" una cuota de 100 USD).

**BUG-A3 — Asiento `CAMBIO_DIVISA` con tipo inexistente + saldos falsos**
`apps/tesoreria/serializers.py:193` invoca `generar_asiento("CAMBIO_DIVISA")` pero ese tipo
**no está en `TIPOS_ASIENTO`** (`contabilidad/services.py:30-42`) → con contabilidad activa
toda operación de cambio de divisa falla; sin ella, jamás se genera asiento. Además
`OperacionCambioDivisaSerializer.create` y `MovimientoInternoFondoSerializer.create` no son
atómicos y crean `MovimientoCajaBanco` con `saldo_anterior=0, saldo_nuevo=0` sin actualizar
`saldo_actual`. (Amplía lo ya registrado en CTF-013.)

**BUG-A4 — CxC duplicada (crédito) / CxC ausente (contado con pedido)**
`apps/ventas/services.py:183, 303-318, 485-502` — cliente CREDITO: `confirmar_pedido` crea
CxC por el subtotal y `emitir_factura_fiscal` crea **otra** por el total (el cliente aparece
debiendo ~2x). `entregar_nota_venta` decide "ya tiene CxC" con solo verificar que el pedido
tiene cliente (no que se creó CxC): venta CONTADO con pedido, entregada y no facturada,
queda **sin** CxC.

**BUG-A5 — Conversión de moneda invertida en `crear_transaccion_financiera_pago`**
`apps/ventas/views.py:150-160` — divide por la tasa cuando la semántica del proyecto
(`convertir_monto`) es multiplicar. Mitigante: hoy es código muerto (`PedidoPago` eliminado
en `ventas/0008`), pero hay tests de backfill que consagran el comportamiento; si se
reactiva, corrompe `monto_base_empresa`.

### MEDIO

- **BUG-M1** — `apps/nomina/views.py:177-178`: `sum or 0 / max(n,1)` (precedencia) →
  `promedio_sueldo` devuelve la **suma**. Fix: `(sum or 0) / max(n,1)`.
- **BUG-M2** — N+1 en saldos CxC: `_saldo_pendiente` por instancia ignora el prefetch
  (`cuentas_por_cobrar/services.py:27`, usado por aging y el list serializer). Fix: `annotate(Coalesce(Sum(...)))`.
- **BUG-M3** — `generar_cuotas` (`cxc/services/cuotas.py:88-113`): con `monto_cuota` fijo
  puede emitir cuotas por más del total (cuota negativa final se omite, intermedias no se capean);
  el serializer no valida `monto_total>0` ni coherencia cuota/total ni tenant del FK `cxc`.
- **BUG-M4** — cierre de caja física (`finanzas/models.py:306-316`): compara `DateField` con
  datetime del último cierre → movimientos del mismo día mal clasificados; `saldo_teorico`
  puede doble-contar.
- **BUG-M5** — conciliación automática sin lock (`tesoreria/services.py:189-231`): dos
  ejecuciones concurrentes pueden conciliar el mismo Pago contra dos movimientos.
- **BUG-M6** — frontend: dinero como `Number`/float en el flujo de pago/vuelto
  (`ModalPago.tsx:138-149`, `SeccionVuelto.tsx:89-98`, `PedidoFormPage.tsx:308`,
  `PedidoDetailPage.tsx:195`, `NotaVentaDetailPage.tsx:161`). Coincide con FE-HIGH-7 pendiente.

### BAJO

Fechas "hoy" en UTC en aging y búsqueda de tasas (corrimiento tras 20:00 Caracas) ·
`registrar_abono` no genera asiento `PAGO_CXC` (asimetría con acuerdos) ·
`CuentaPorCobrarViewSet` permite PATCH directo de `monto`/`estado` ·
`Decimal(monto)` sin validar en `finanzas/views.py:112-121` (500 en vez de 400).

### Áreas verificadas limpias

`fiscal/services.py` (IVA/IGTF Decimal + quantize; correlativos con lock) ·
`cuentas_por_pagar/services.py` y `registrar_abono` (atómicos y con lock — el problema es el
bypass C1) · `generar_asiento` (debe=haber por construcción) · `convertir_monto`/tasas
(Decimal puro) · fraccionamiento CxC (locks correctos) · stock (locks correctos).

---

## 5. Conclusión y destino de los hallazgos

Todos los hallazgos pasan al roadmap consolidado del
[`PLAN_MAESTRO_UNICO.md` §5.2](../PLAN_MAESTRO_UNICO.md) como workstream **P0 — Correcciones
de auditoría 2026-06-10** (seguridad + integridad financiera), con DoD por paquete de
trabajo. Ningún hallazgo nuevo requiere CTF: o se corrige ya (P0) o ya tiene CTF (005, 012, 013).

> Convención: esta auditoría queda como **activa** en `docs/auditorias/` hasta cerrar el
> workstream P0; entonces se mueve a `archivo/`.
