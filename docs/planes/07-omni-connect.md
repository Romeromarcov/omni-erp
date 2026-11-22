# Plan 07 — Omni Connect: Tarjetas NFC, Perfil Público y CRM Ligero (S2–S12)

> Plan de ejecución técnico derivado de [`ADR-014`](../decisions/ADR-014-omni-connect-nfc-crm-en-omni.md)
> y [`PLAN_MAESTRO_UNICO.md`](../PLAN_MAESTRO_UNICO.md).
> Alineado con las reglas inviolables R-CODE / R-PROC / R-PROD (§2) y el gate
> [`DEFINITION_OF_DONE.md`](../DEFINITION_OF_DONE.md).

| Campo | Valor |
|---|---|
| **Estado** | ✅ COMPLETADO 100% — `S1`–`S12` cerradas (`#261` + PR-26..PR-30) |
| **Fecha** | 2026-11-22 (cierre integral `S1`–`S12`) |
| **Apps involucradas** | `apps/connect`, `apps/crm`, `apps/core`, `apps/ventas`, `apps/tareas`, `apps/integration_hub`, `apps/agentes`, `apps/gestion_aprobaciones` |
| **Entrega** | 6 PRs focales (`#261`, PR-26 `#313`, PR-27 `#314`, PR-28 `#315`, PR-29 `#316`, PR-30 `S10–S12`) |

---

## Resumen de cierre (`S1`–`S12` — 100% completado)

| Bloque | Historias | PR | Alcance entregado |
|---|---|---|---|
| Base de esquema | `S1` | `#261` | Modelos `connect` (`Perfil`, `Tarjeta`, `Toque`) y `crm` (`Pipeline`, `Etapa`, `Lead`) con RLS forzada (`apps/core/rls.py`) y validadores `validar_botones` / `normalizar_uid_chip`. |
| Perfil público y leads | `S2`–`S3` | **PR-26** (`#313`) | Endpoints públicos `AllowAny` (`/api/public/connect/<slug>/`, `vcard/`, `leads/`) con `rls_bypass()` acotado, `ip_hash` HMAC, consentimiento obligatorio, anti-spam (`ConnectLeadThrottle` + honeypot), `/c/:slug` y editor `/connect/perfil`. |
| Actividades y Kanban | `S4` | **PR-27** (`#314`) | Modelo `crm.Actividad` (+ RLS), ViewSets/acciones Kanban (`mover_etapa`, `reordenar`, `resumen_kanban`), paridad MCP (`crm_*`) y tablero interactivo `/crm/pipeline`. |
| Dedup y conversión | `S5`–`S6` | **PR-28** (`#315`) | Normalización e índices en `core.Contacto`, deduplicación multi-tenant, anonimización PII (derecho al olvido) y conversión atómica `Lead` → `crm.Cliente` (+ borrador `ventas.Cotizacion` opcional) + MCP. |
| Outbox y Odoo `crm.lead` | `S7`–`S9` | **PR-29** (`#316`) | `integration_hub.EventoOutbox` multi-tenant + RLS, dispatcher Celery idempotente con advisory lock/backoff y `push_lead` opt-in hacia `crm.lead` en Odoo (`OdooXMLRPCClient`). |
| Analíticas, tarjetas y agentes IA | `S10`–`S12` | **PR-30** (`feat/connect-s10-s12-analiticas-tarjetas-agentes`) | Analíticas ORM agregadas (`GET /api/connect/analiticas/`, `/connect/analiticas`) + purga Celery Beat (`connect.purgar_toques_antiguos`); CRUD + ciclo de vida de tarjetas NFC y códigos QR SVG/PNG (`/connect/tarjetas`); agentes `connect_calificador` y `connect_seguimiento` en `apps/agentes` con gate obligatorio `gestion_aprobaciones` (`CONNECT_ENVIO_EXTERNO`), MCP y evals dorados (`tests_eval/test_eval_connect.py`). |

---

## 0. Base ya implementada en `develop` (`S1` — PR `#261`)

Modelos existentes en código (con RLS forzada registrada en `apps/core/rls.py`):

- **`apps/connect/models.py` (`connect_perfil`, `connect_tarjeta`, `connect_toque`):**
  - `Perfil`: `id_perfil` (UUIDv7), `id_empresa` (FK `core.Empresa`), `usuario` (FK `core.Usuarios`, único por empresa), `slug` (único global, normalizado minúsculas, `CheckConstraint` `connect_perfil_slug_normalizado` contra `SLUGS_RESERVADOS`), `nombre_publico`, `cargo`, `bio`, `telefono_publico`, `email_publico`, `tema`, `botones` (JSON validado por `validar_botones` en `apps/connect/validators.py` con allowlist `BOTONES_URL | BOTONES_TELEFONO | BOTONES_CORREO` y máximo `BOTONES_MAX=30`), `plantilla_bloqueada`, `activo`.
  - `Tarjeta`: `id_tarjeta` (UUIDv7), `id_empresa`, `perfil` (FK nullable a `Perfil`), `uid_chip` (único global, hex `8–20` chars normalizado mayúsculas), `tipo` (`PVC` | `METAL` | `PULSERA`), `estado` (`INVENTARIO` | `ACTIVA` | `DESACTIVADA` | `PERDIDA`), `fecha_activacion`, `notas`, `activo`; `CheckConstraint` `connect_tarjeta_activa_con_perfil`.
  - `Toque`: `id_toque` (UUIDv7), `id_empresa`, `perfil`, `tarjeta` (nullable), `origen` (`NFC` | `QR` | `ENLACE`), `dispositivo` (`IOS` | `ANDROID` | `ESCRITORIO` | `OTRO`), `fecha_toque`, `ip_hash` (nunca IP en claro).
- **`apps/crm/models.py` (`crm_pipeline`, `crm_etapa`, `crm_lead`, `crm_cliente`):**
  - `Pipeline`: `id_pipeline`, `id_empresa`, `nombre`, `es_predeterminado` (único activo por empresa), `activo`.
  - `Etapa`: `id_etapa`, `id_empresa`, `pipeline`, `nombre`, `orden` (no único para permitir reordenar kanban), `tipo` (`ABIERTA` | `GANADA` | `PERDIDA`), `activo`.
  - `Lead`: `id_lead`, `id_empresa`, `nombre`, `apellido`, `empresa_nombre`, `email`, `telefono`, `email_normalizado`, `telefono_normalizado`, `mensaje`, `fuente` (`NFC` | `QR` | `ENLACE` | `MANUAL` | `IMPORTACION`), `tarjeta`, `perfil`, `pipeline`, `etapa`, `propietario` (`core.Usuarios`), `contacto` (`core.Contacto`, nullable hasta `S5`), `consentimiento_aceptado`, `consentimiento_fecha`, `consentimiento_texto`; `CheckConstraint` `crm_lead_consentimiento_completo` y `crm_lead_publico_requiere_consentimiento`.
  - `Cliente`: `id_cliente`, `id_empresa`, `razon_social`, `nombre_comercial`, `rif`, `direccion`, `telefono`, `email`, `tipo_cliente` (`CONTADO` | `CREDITO`), `limite_credito`, `dias_credito`, `contacto` (`OneToOneField` a `core.Contacto`).

> **Regla transversal heredada de S1:** todo servicio que cree o modifique registros de `connect` o `crm` debe invocar `full_clean()` dentro de `@transaction.atomic`, porque las validaciones cross-tenant de FKs (`validar_misma_empresa`) viven en `clean()` y `objects.create()` no las ejecuta.

---

## 1. Desglose de historias `S2` a `S12`

### Historia `S2` — Perfil público NFC, vCard y registro de `Toque`

> **Prerrequisito de seguridad (Plan 06 Fase 2 / Tarea 4.4):** la vista pública anónima debe funcionar de forma segura tanto con `bypass='on'` actual como con `bypass='off'` en un rol no-dueño.

- **Contratos de backend (`apps/connect/`):**
  - Servicio `resolver_perfil_publico(slug: str, uid_chip: str | None = None)`:
    - Ejecuta **exclusivamente** la consulta por `slug` (y opcionalmente `uid_chip`) dentro de `with rls.rls_bypass():` (`apps/core/rls.py`), proyectando con `.only(...)` / `.values(...)` únicamente los campos públicos (`id_perfil`, `id_empresa_id`, `slug`, `nombre_publico`, `cargo`, `bio`, `telefono_publico`, `email_publico`, `tema`, `botones`). **Nunca** expone `id_empresa`, `usuario_id` ni notas internas en la respuesta pública.
    - Si se pasa `uid_chip` (ej. `/c/<slug>?uid=...` o ruta `/t/<uid_chip>`): busca la `Tarjeta` normalizando `normalizar_uid_chip(uid_chip)`. Solo es válida si `tarjeta.estado == Tarjeta.Estado.ACTIVA`, `tarjeta.activo is True`, `tarjeta.perfil_id == perfil.id_perfil` y `perfil.activo is True`. Si está `PERDIDA`, `DESACTIVADA` o `INVENTARIO`, responde **404** (sin filtrar estado interno).
    - Si se accede directo por `/c/<slug>` (QR o enlace), exige `perfil.activo is True` y verifica que el tenant esté habilitado.
  - Servicio `registrar_toque_publico(*, perfil, tarjeta=None, origen, user_agent, client_ip)` dentro de `rls.rls_bypass()` + `full_clean()`:
    - Calcula `ip_hash = hmac.new(settings.SECRET_KEY.encode(), f"{perfil.id_empresa_id}:{client_ip}".encode(), hashlib.sha256).hexdigest()`.
    - Deduplica ráfagas de recarga en ventana corta (p. ej. mismo `(ip_hash, perfil, origen)` en <60 s vía `CACHES`) para no inflar `Toque`.
    - Deriva `dispositivo` (`IOS`, `ANDROID`, `ESCRITORIO`, `OTRO`) desde `User-Agent`.
  - Servicio `generar_vcard(perfil_publico: dict) -> str`: genera vCard 3.0/4.0 escapando `\r`, `\n`, `;`, `,` y validando que todas las URLs cumplan `validar_botones` (prevención de inyección de propiedades vCard).
- **Endpoints REST:**
  - `GET /api/connect/publico/<slug>/` (`AllowAny`, throttle anónimo dedicado `ConnectPublicoThrottle`): devuelve JSON proyectado público + bandera `acepta_leads`.
  - `GET /api/connect/publico/tarjeta/<uid_chip>/`: resuelve tarjeta `ACTIVA` → devuelve proyección pública o redirige al perfil público `/c/<slug>?uid=<uid_chip>`.
  - `GET /api/connect/publico/<slug>/vcard/`: devuelve `text/vcard; charset=utf-8` con `Content-Disposition: attachment; filename="<slug>.vcf"`.
  - `GET/PATCH /api/connect/mi-perfil/` y `PerfilViewSet` (`BaseModelViewSet`, autenticado multi-tenant): gestión del perfil propio y corporativo (respeta `plantilla_bloqueada`).
- **Frontend:**
  - Ruta pública `/c/:slug` (sin requerir JWT en `AuthContext`, layout minimalista responsive, descarga de `.vcf`, renderizado con escapado estricto de React sin `dangerouslySetInnerHTML` y `rel="noopener noreferrer"` en enlaces externos) + vista de edición de perfil en el ERP (`/connect/perfil`).
- **Criterios de Done / Tests:**
  - Tests de aislamiento RLS (`bypass='off'`): request anónimo a `/api/connect/publico/<slug>/` responde 200 solo si `perfil.activo=True`; si llega `uid` en estado `PERDIDA`/`DESACTIVADA`/`INVENTARIO` → 404.
  - Test de vCard contra inyección de saltos de línea (`\nTEL:...`) y XSS en `botones`.
  - Test de `Toque`: `ip_hash` nunca guarda IP en claro; `Toque.clean()` rechaza tarjeta de otro perfil o de otra empresa.

---

### Historia `S3` — Captura pública de lead con consentimiento obligatorio y anti-spam

- **Contratos de backend (`apps/connect/` + `apps/crm/`):**
  - Versión/texto vigente de aviso de privacidad por empresa (`TEXTO_CONSENTIMIENTO_DEFAULT` o parametrizado en configuración Connect de empresa).
  - Servicio `capturar_lead_publico(*, slug, uid_chip=None, datos, client_ip)`:
    - Valida `consentimiento_aceptado is True` explícito; si es `False` o falta, rechaza con `400` antes de tocar BD (reforzado en BD por `crm_lead_publico_requiere_consentimiento` y `crm_lead_consentimiento_completo`).
    - Resuelve `perfil` (y `tarjeta` si viene `uid_chip`, exigiendo `ACTIVA`) dentro de `rls.rls_bypass()`.
    - Garantiza existencia de `Pipeline` predeterminado (`es_predeterminado=True`) y su primera `Etapa` abierta (`orden` mínimo, `tipo=Etapa.Tipo.ABIERTA`) mediante helper idempotente `asegurar_pipeline_predeterminado(empresa)`.
    - Normaliza `email_normalizado` (`strip().lower()`) y `telefono_normalizado` (dígitos E.164 sin separadores) en la creación.
    - Crea `Lead` con `fuente` = `NFC` (si `tarjeta` activa), `QR` o `ENLACE`, `propietario = perfil.usuario`, `consentimiento_fecha = timezone.now()`, `consentimiento_texto = texto_vigente`, llamando **`lead.full_clean()`** antes de `save()`.
    - Emite notificación interna `core.Notificacion` al `perfil.usuario` y evento de dominio `crm.lead.capturado` (`apps/core/events.py`).
- **Anti-spam y rate-limit:**
  - `ConnectLeadThrottle` en `POST /api/connect/publico/<slug>/leads/` (p. ej. `10/min` por IP y `30/hora` por `(ip_hash, perfil)` usando `CACHES` Redis).
  - Campo *honeypot* opcional (`website` / `campo_oculto`) rechazado silenciosamente o con `400`; validación estricta de longitud y formato en serializer público (DRF).
- **Endpoint y UI:**
  - `POST /api/connect/publico/<slug>/leads/` (`AllowAny`): payload `{nombre, apellido, empresa_nombre, email, telefono, mensaje, fuente, uid_chip, consentimiento_aceptado}`.
  - Modal/formulario integrado en `/c/:slug` ("Compartir mi contacto") con checkbox obligatorio de consentimiento y enlace al texto completo de tratamiento de datos.
- **Criterios de Done / Tests:**
  - `POST` sin `consentimiento_aceptado=True` → `400` (y BD rechaza `Lead` público sin fecha/texto).
  - Rate-limit excedido → `429`.
  - Lead asignado al `id_empresa` del `Perfil` (nunca aceptado desde el payload público) y visible solo para usuarios de esa empresa.

---

### Historia `S4` — `crm.Actividad`, Kanban interactivo y capacidades MCP

- **Modelo `crm.Actividad` (inspirado en `mail.activity` de Odoo):**
  - Ubicación: `backend/apps/crm/models.py` (hereda de `OmniBaseModel`, PK `id_actividad = UUIDField(primary_key=True, default=uuid7)`).
  - Campos:
    - `id_empresa`: FK `core.Empresa` (registrada en `apps/core/rls.py` → `RLS_TABLES["crm_actividad"] = "id_empresa_id"` con migración reversible `FORCE ROW LEVEL SECURITY`).
    - `lead`: FK nullable `crm.Lead` (`on_delete=models.CASCADE`, `related_name="actividades"`).
    - `cliente`: FK nullable `crm.Cliente` (`on_delete=models.CASCADE`, `related_name="actividades"`). `CheckConstraint` o `clean()` exigiendo al menos uno de `lead` o `cliente`, ambos de la misma empresa (`validar_misma_empresa`).
    - `tipo`: `LLAMADA` | `REUNION` | `WHATSAPP` | `CORREO` | `TAREA`.
    - `resumen`: `CharField(max_length=200)`.
    - `nota_resultado`: `TextField(blank=True, default="")`.
    - `fecha_limite`: `DateField()`.
    - `asignado_a`: FK `core.Usuarios` (validado en `clean()` que pertenezca a `id_empresa`).
    - `estado`: `PENDIENTE` | `COMPLETADA` | `CANCELADA`.
    - `fecha_completada`: `DateTimeField(null=True, blank=True)`.
    - **Integración opcional con `apps/tareas` (`ADR-015`):** cuando el usuario marque "crear seguimiento operativo", se puede generar una `tareas.Tarea` con vínculo polimórfico `entidad_tipo="crm.Actividad"`, `entidad_id=actividad.id_actividad`, sin crear dependencia circular en modelos de `crm`.
- **Endpoints REST (`apps/crm/`):**
  - `PipelineViewSet`, `EtapaViewSet` (incluyendo `@action reordenar` atómica), `LeadViewSet` (`BaseModelViewSet` + `@action mover_etapa`, `@action resumen_kanban`) y `ActividadViewSet` (`BaseModelViewSet` + `@action completar`, `@action cancelar`, filtro `?vencidas=true`).
  - `TenantFKScopeMixin` en todos los serializers de escritura para acotar FKs por `get_empresas_visible()`.
- **Capacidades MCP (`apps/crm/mcp.py`, scopes `crm:read` / `crm:write`, `R-CODE-7`):**
  - `crm_listar_leads`, `crm_mover_lead_etapa`, `crm_crear_actividad`, `crm_completar_actividad`.
- **Frontend:**
  - `CrmPipelineKanbanPage` (`/crm/pipeline`): columnas por `Etapa` ordenadas por `orden`, tarjetas de `Lead` con fuente (`NFC`/`QR`/`ENLACE`/`MANUAL`), propietario, indicador de actividades vencidas/pendientes, cambio de etapa (drag-and-drop / menú accesible), drawer lateral de detalle del `Lead` con timeline de `Actividad` y alta manual de leads.
- **Criterios de Done / Tests:**
  - Aislamiento multi-tenant y RLS en `crm_actividad`, `crm_pipeline`, `crm_etapa`, `crm_lead`.
  - Validación cross-tenant de `etapa.pipeline_id == lead.pipeline_id` y `asignado_a` en `id_empresa`.
  - `tests/api/test_crm_kanban_actividades.py` + `e2e/crm-kanban.flow.spec.ts` verdes.

---

### Historia `S5` — Deduplicación y resolución hacia `core.Contacto`

- **Lógica de normalización y resolución (`apps/crm/services_dedup.py`):**
  - Normalizadores puros y reutilizables: `normalizar_email(email)` y `normalizar_telefono(telefono, codigo_pais_default="58")`.
  - Regla de resolución multi-tenant (`id_empresa` estricto):
    1. Nota de esquema: `core.Contacto` (`backend/apps/core/models.py:874-875`) actualmente solo define `email` y `telefono` (a diferencia de `crm.Lead`, que ya incluye `email_normalizado` y `telefono_normalizado`). En `S5` se añaden `email_normalizado` y `telefono_normalizado` (+ índices compuestos por `id_empresa`) a `core.Contacto` con migración de backfill —o bien normalización indexada sobre `email`/`telefono`— para ejecutar match exacto en la misma empresa sin full scan.
    2. Búsqueda de candidatos en otros `crm.Lead` activos o `crm.Cliente` de la misma empresa para evitar duplicar leads en un mismo toque repetido o múltiples formularios.
  - Acción explícita o automática `vincular_lead_a_contacto(lead, contacto=None, crear_si_no_existe=False)`: dentro de `@transaction.atomic` + `select_for_update()` sobre `lead`, enlaza `lead.contacto` sin sobreescribir campos verificados del `Contacto` salvo los vacíos, o permite fusionar dos leads duplicados conservando `actividades` y `toques`/origen.
  - **Derecho al olvido / supresión de datos (`R-CODE-6` excepción legal documentada):** acción `anonimizar_lead(lead, usuario, motivo)` que limpia PII (`nombre="Anonimizado"`, `apellido=""`, `email=""`, `telefono=""`, `email_normalizado=""`, `telefono_normalizado=""`, `mensaje=""`), marca `activo=False`, registra auditoría en `RegistroAuditoria` y encola evento de borrado para `S7`.
- **UI y Tests:**
  - Banner en drawer del `Lead`: "Posible contacto/lead coincidente" con botones "Vincular a contacto existente" / "Crear contacto nuevo".
  - Tests de no-colisión cross-tenant (mismo email/teléfono en Empresa A y Empresa B nunca se enlazan ni revelan existencia).

---

### Historia `S6` — Conversión atómica de `Lead` ganado a `crm.Cliente` facturable

- **Servicio `convertir_lead_a_cliente(lead, *, usuario, datos_fiscales, crear_cotizacion=False)` (`apps/crm/services.py`):**
  - Ejecutado en `@transaction.atomic` con `Lead.objects.select_for_update()`.
  - Flujo:
    1. Resuelve o crea el `core.Contacto` (si `lead.contacto` es nulo, ejecuta `S5` y marca `contacto.es_cliente = True`).
    2. Si ya existe un `crm.Cliente` en `id_empresa` con el mismo `contacto` o el mismo `rif` normalizado, **reutiliza** ese `Cliente` (no duplica entidad) o falla con error de dominio claro si hay conflicto explícito de RIF con otro contacto.
    3. Si no existe, crea `crm.Cliente` (`full_clean()`, `razon_social`, `rif` validado por `validar_rif` / localización, `email`, `telefono`, `tipo_cliente`, `contacto=contacto`).
    4. Mueve el `Lead` a la etapa `Etapa.Tipo.GANADA` del mismo `Pipeline` (si existe; si no, error explícito) y registra una `Actividad` de cierre o marca trazabilidad en `Lead`.
    5. Si `crear_cotizacion=True`, invoca el servicio de `apps/ventas` para crear borrador de `ventas.Cotizacion` pre-cargado con ese `Cliente`.
    6. Emite evento `crm.lead.convertido` (`apps/core/events.py`).
- **Endpoint & MCP (`R-CODE-7`):**
  - `POST /api/crm/leads/<id>/convertir-cliente/` + tool MCP `crm_convertir_lead_cliente`.
- **UI:**
  - Modal "Ganar y convertir a Cliente" desde la tarjeta/drawer del Kanban (pre-llena razón social/email/teléfono desde el lead y solicita RIF/dirección fiscal/condición de pago).
- **Criterios de Done / Tests:**
  - Doble click concurrente sobre `convertir-cliente` no crea 2 `crm.Cliente` (`select_for_update` + constraint `(id_empresa, rif)`).
  - Un `Cliente` creado puede facturarse inmediatamente en `ventas` (IVA/IGTF intactos).

---

### Historias `S7–S9` — Outbox de eventos Connect sobre `ConectorInstancia` + `push_lead` a Odoo (`crm.lead`)

> Conforme a [`ADR-014`](../decisions/ADR-014-omni-connect-nfc-crm-en-omni.md): toda integración externa pasa por `apps/integration_hub` sobre `ConectorInstancia`. Connect **no** llama HTTP/XML-RPC directo y **solo** empuja hacia `crm.lead` en Odoo (nunca `res.partner` automáticamente para no disparar `l10n_ve_full`).

- **S7 — Outbox multi-tenant en `apps/integration_hub` (o `connect` delegando al Hub):**
  - Modelo `integration_hub.EventoOutbox` (multi-tenant `id_empresa`, FK `conector_instancia` a `ConectorInstancia`, `tipo_evento` ej. `connect.lead.creado` | `connect.lead.etapa_cambiada` | `connect.lead.anonimizado`, `modelo_origen`, `id_entidad_origen`, `payload_json`, `idempotency_key` único por `(conector_instancia, idempotency_key)`, `estado` `PENDIENTE` | `PROCESANDO` | `ENVIADO` | `ERROR` | `DESCARTADO`, `intentos`, `max_intentos`, `proximo_reintento`, `ultimo_error` sanitizado sin `str(e)` ni secretos — `R-CODE-8`).
  - Registrado en `rls.RLS_TABLES`.
- **S8 — Worker Celery de despacho idempotente:**
  - Tarea Celery `integration_hub.despachar_outbox` con backoff exponencial, `select_for_update(skip_locked=True)` para evitar doble envío entre workers, y registro de mapeo en `EntidadSincronizada` (`tipo_entidad="leads"`, `id_externo` ↔ `id_omni`).
- **S9 — `push_lead` hacia `crm.lead` en `OdooXMLRPCClient` / `OdooConnector`:**
  - Extensión de `OdooXMLRPCClient` (`apps/integration_hub/connectors/odoo/client.py`): métodos `crear_lead_crm(vals: dict) -> int` y `actualizar_lead_crm(lead_id: int, vals: dict) -> bool` sobre el modelo `crm.lead` de Odoo (`name`, `contact_name`, `partner_name`, `email_from`, `phone`, `description`, `x_omni_lead_id` o `ref`/etiqueta trazable).
  - Interruptor opt-in explícito en `ConectorInstancia.configuracion` (p. ej. `empujar_connect_leads: true`) y soporte de credencial de escritura dedicada (`write_user`/`write_api_key`) heredado del patrón de `bots_ingest`.
  - Mapeo opcional de etapas Omni (`Etapa`) ↔ `crm.stage` en Odoo mediante diccionario en configuración del conector.
- **Criterios de Done / Tests:**
  - Suite unit/integración con fake/mock de `OdooXMLRPCClient` probando idempotencia (reintento tras timeout no duplica `crm.lead`), manejo de errores sin filtrar credenciales (`R-CODE-8`) y respeto al flag `empujar_connect_leads`.
  - Validación de contrato real contra Odoo de prueba (staging/test) usando `validar_conector_odoo`.

---

### Historia `S10` — Analíticas de `Toque` y política de retención

- **Analíticas (`apps/connect/`):**
  - Endpoint `GET /api/connect/analiticas/` (tenant-scoped, optimizado con agregaciones ORM `TruncDate`/`Count`, sin N+1):
    - Total de toques por período (`NFC` vs `QR` vs `ENLACE`), toques únicos aproximados (`Count("ip_hash", distinct=True)`), desglose por `dispositivo` (`IOS`/`ANDROID`/`ESCRITORIO`), ranking por `Tarjeta` / `Perfil`, tasa de conversión `leads / toques` y `clientes_ganados / leads`.
  - Dashboard en frontend (`/connect/analiticas`) con KPIs y tabla por tarjeta/vendedor.
- **Política de retención y purga programada (`ADR-014`):**
  - Configuración por empresa (`dias_retencion_toques`, default p. ej. `365` días; resumen agregado mensual previo opcional).
  - Tarea periódica Celery Beat (`connect.purgar_toques_antiguos`) con `with rls.rls_bypass():` que consolida o elimina registros `Toque` vencidos en lotes pequeños (`batch_size=1000`) sin bloquear la tabla, auditada en logs estructurados.

---

### Historias `S11–S12` — Gestión de tarjetas físicas y Agentes IA Connect con aprobación

- **S11 — Ciclo de vida de tarjetas físicas (`apps/connect/`):**
  - Endpoints y acciones atómicas en `TarjetaViewSet` (`BaseModelViewSet`):
    - Alta/lote de inventario (`estado=INVENTARIO`, `uid_chip` único normalizado).
    - `@action asignar_y_activar(perfil_id)`: valida que el perfil pertenezca al mismo tenant (`clean()` / `full_clean()`), cambia a `ACTIVA` y fija `fecha_activacion`.
    - `@action reportar_perdida` / `@action desactivar`: cambia a `PERDIDA` / `DESACTIVADA` (el perfil conserva su historial y puede recibir una nueva tarjeta sin cambiar de `slug`).
    - Generación de código QR SVG/PNG descargable para cada `Perfil` apuntando a `/c/<slug>?src=qr`.
  - UI `/connect/tarjetas`: tabla de inventario/asignación de chips, cambio de estado con confirmación y visor/descarga QR.
- **S12 — Agentes IA Connect registrados en `apps/agentes` con `gestion_aprobaciones`:**
  - Registro de nuevos agentes ampliando **tanto** los `choices` inline de `ConfigAgente.agente` (`apps/agentes/models.py:38-43`) **como** `PrediccionAgente.AGENTE_CHOICES` (`apps/agentes/models.py:80`, idealmente consolidando ambos en una única constante compartida `AGENTE_CHOICES` + migración):
    - `connect_calificador`: analiza `Lead` recién capturado + `Toque` + historial en `core.Contacto` vía `llm_gateway.get_gateway()` (`apps/core/llm_gateway.py`), propone prioridad, score y siguiente `Actividad` en `PrediccionAgente`.
    - `connect_seguimiento`: redacta borrador de mensaje de seguimiento (WhatsApp/correo) para leads sin respuesta.
  - **Regla estricta v1 (`ADR-014`):** usando `NivelAutonomia` (`SOMBRA` / `SUGERENCIA` por defecto), **ningún agente envía mensajes externos al lead ni escribe en Odoo sin aprobación humana**. Toda propuesta de envío externo crea una `gestion_aprobaciones.SolicitudAprobacion` (`crear_solicitud(..., codigo_tipo="CONNECT_ENVIO_EXTERNO")`) y solo se ejecuta tras `registrar_decision(..., aprobado=True)` + bitácora completa (`R-PROD-5`).
  - Casos dorados en `backend/tests_eval/` manteniendo `precision@1 >= 80%`.

---

## 2. Secuenciación recomendada y Definition of Done

```
S1 (✅ #261)
  ├──► S2 (Perfil público NFC + vCard + Toque + rls_bypass acotado)
  │      └──► S3 (Captura pública de lead + consentimiento + rate-limit)
  │             ├──► S4 (crm.Actividad + Kanban interactivo + MCP)
  │             │      ├──► S5 (Dedup core.Contacto + derecho de olvido)
  │             │      │      └──► S6 (Conversión atómica Lead → crm.Cliente + ventas)
  │             │      └──► S10 (Analíticas Toque + retención Celery Beat)
  │             └──► S7–S9 (EventoOutbox + Celery + Odoo push_lead crm.lead)
  ├──► S11 (Gestión física de tarjetas + QR)
  └──► S12 (Agentes Connect en ConfigAgente + gate gestion_aprobaciones)
```

Cada historia entra en **1–2 PRs pequeños y focales (R-PROC-2)** hacia `develop` cumpliendo:
1. `manage.py check`, `makemigrations --check --dry-run` y `mapa_superficie --check` en verde.
2. Registro RLS en `apps/core/rls.py` + migración reversible para toda tabla nueva con `id_empresa` (p. ej. `crm_actividad`, `integration_hub_evento_outbox`).
3. Suite `tests/` (incl. aislamiento cross-tenant + `diff-cover ≥95%` vs `origin/main`), `tsc -b`, `npm run lint`, `check:api-drift` y Vitest/Playwright en verde.
4. Dictamen **`APROBADO`** de revisor independiente (`QA + Seguridad`) en el PR antes de marcar `ready` y mergear a `develop`.
