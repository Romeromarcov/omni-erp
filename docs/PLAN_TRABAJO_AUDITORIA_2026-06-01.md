# Plan de Trabajo — Auditoría 2026-06-01

**Fuente:** auditoría multi-agente (203 agentes, 162 hallazgos confirmados, 71 items gap) + ejecución de validaciones del 2026-06-01.
**Fuente de verdad de planificación:** este documento solo lista trabajo derivado de la auditoría; el roadmap mayor sigue en [`PLAN_MAESTRO_UNICO.md`](PLAN_MAESTRO_UNICO.md).
**Responsable:** Marco + agente IA co-desarrollador.
**Convenciones:** PRs pequeños y focales (R-PROC-2). Cada PR debe cerrar 1–N items de este plan y dejar CI verde. ID de item se cita en el commit (`fix(audit): CRIT-1 ...`).

---

## 0. Tablero ejecutivo

| Semana | Foco | Items | DoD del bloque |
|---|---|---|---|
| **Sem 1** | Stop the bleed multi-tenant | CRIT-1..3, H-SEC-1, H-SEC-2, H-API-1..3 | Ningún endpoint con `.objects.all()` sin filtro tenant en core/ventas/compras |
| **Sem 2** | Integridad contable y monetaria | H-BUG-1..4, H-RCODE-1, NEW-MIG-1 | R-CODE-11 sin tragar excepciones; integración Odoo con Decimal |
| **Sem 3** | Hardening de seguridad de superficie | H-SEC-3..9 | TLS, secretos, JWT, uploads, capability tokens |
| **Sem 4** | Hardening de seguridad profunda + medios/bajos | H-SEC-10..13, M-1..15 | Headers nginx, CSP, defaults de docker-compose |
| **Sem 5** | Limpieza de bugs medios y bajos | M-16..30, NEW-PAG-1 | Sin `except Exception: pass` en lógica de negocio |
| **Sem 6** | Gap del plan + alineación documental | GAP-1..6 | Plan refleja realidad; ADR-007 redactado |
| **Sem 7+** | Sub-fase 1.F (distribuidora) | TRACK-1F-* | Bloqueante real desbloqueado |

Carga estimada total: **120–180 h** (3–4 semanas a 40 h, o 6–9 semanas a 20 h/sem según R-PROC quincenal).

---

## 1. Críticos (Semana 1, antes que nada)

> Los tres comparten archivo, patrón y test. Cierran en una sola PR `fix(audit): CRIT-1..3 — eliminar DetailViews paralelas en core`.

### CRIT-1 · `EmpresaDetailView` sin filtro tenant
- **Riesgo:** cualquier usuario autenticado puede modificar cualquier `Empresa` conociendo UUID. Hoy el router gana el URL match, pero el endpoint registrado es bomba de retardo.
- **Archivos:** [`backend/apps/core/views.py:89`](../backend/apps/core/views.py#L89), [`backend/apps/core/urls.py:49`](../backend/apps/core/urls.py#L49)
- **Pasos:**
  1. Eliminar la clase `EmpresaDetailView` (líneas ~89–120).
  2. Eliminar la línea de registro en `urls.py:49`.
  3. Eliminar imports residuales si los hubiera.
- **Tests:** agregar `tests_api/test_core_tenant_isolation.py::test_no_existe_endpoint_detail_paralelo_empresa` que haga `reverse("empresa-detail-legacy")` y espere `NoReverseMatch`.
- **DoD:** `grep -r "EmpresaDetailView" backend/` → 0 hits. Test de aislamiento de empresa en cross-tenant sigue verde.
- **Esfuerzo:** S (30 min).

### CRIT-2 · `UsuarioDetailView` sin filtro tenant
- **Riesgo:** escalación de privilegios; `UsuariosSerializer` con `fields="__all__"` agrava (H-API-3).
- **Archivos:** [`backend/apps/core/views.py:48`](../backend/apps/core/views.py#L48), [`backend/apps/core/urls.py:51`](../backend/apps/core/urls.py#L51)
- **Pasos:** mismos que CRIT-1 sobre `UsuarioDetailView` y su `path`. **Verificar** que `UsuariosViewSet` del router cubra GET/PUT/DELETE con filtro `get_empresas_visible`.
- **Tests:** `test_usuario_cross_tenant_no_puede_modificar` y `test_usuario_cross_tenant_no_puede_eliminar` contra `UsuariosViewSet`.
- **DoD:** ídem CRIT-1.
- **Esfuerzo:** S (30 min).

### CRIT-3 · `SucursalDetailView` sin filtro tenant
- **Riesgo:** IDOR cross-tenant Retrieve/Update/Delete.
- **Archivos:** [`backend/apps/core/views.py:212`](../backend/apps/core/views.py#L212), [`backend/apps/core/urls.py:50`](../backend/apps/core/urls.py#L50)
- **Pasos:** ídem CRIT-1.
- **Tests:** `test_sucursal_cross_tenant_no_puede_acceder` contra el ViewSet del router.
- **DoD:** ídem.
- **Esfuerzo:** S (30 min).

---

## 2. Altos — Seguridad (Sem 1 cont. + Sem 3)

### H-SEC-1 · Fail-closed en `settings.py`
- **Riesgo:** `DJANGO_ENV=production` (typo) cae a `settings_dev` con DEBUG y CORS abierto.
- **Archivo:** [`backend/config/settings.py:3`](../backend/config/settings.py#L3)
- **Pasos:**
  1. Reemplazar `env = os.environ.get("DJANGO_ENV", "dev")` por:
     ```python
     env = os.environ.get("DJANGO_ENV")
     if env not in ("dev", "prod"):
         raise ImproperlyConfigured(
             f"DJANGO_ENV debe ser 'dev' o 'prod', recibido: {env!r}"
         )
     ```
  2. Actualizar README de backend y `.env.example` para documentar el valor explícito.
- **Tests:** `tests_api/test_settings_failclose.py` con `monkeypatch.setenv("DJANGO_ENV", "production")` reimportando módulo y esperando `ImproperlyConfigured`.
- **DoD:** test verde; arranque local sigue funcionando con `.env` correcto.
- **Esfuerzo:** S (1 h).
- **PR conjunto con H-SEC-2.**

### H-SEC-2 · Quitar `setdefault SECRET_KEY` débil
- **Riesgo:** staging sin var firma JWTs con clave conocida.
- **Archivo:** [`backend/config/settings_dev.py:3`](../backend/config/settings_dev.py#L3)
- **Pasos:**
  1. Quitar `os.environ.setdefault("SECRET_KEY", "dev-secret-key-...")`.
  2. Forzar lectura: `SECRET_KEY = os.environ["SECRET_KEY"]` con guard.
  3. Generar SECRET_KEY local en `.env.example` con comentario explicativo.
- **DoD:** correr backend sin `SECRET_KEY` en env explota con `KeyError` claro.
- **Esfuerzo:** S (30 min).

### H-SEC-3 · Validar TLS en scrape BCV
- **Riesgo:** MITM inyecta tasa BCV falsa → factura+contabilidad+SENIAT contaminados.
- **Archivo:** [`backend/apps/integration_hub/connectors/tasas_ve/sources/bcv_scrape.py:22`](../backend/apps/integration_hub/connectors/tasas_ve/sources/bcv_scrape.py#L22)
- **Pasos:**
  1. Quitar `verify=False`; pasar a `verify=True` por default.
  2. Si certbundle del sitio rota: empaquetar CA intermedia en `infra/certs/bcv-chain.pem` y usar `verify="infra/certs/bcv-chain.pem"`.
  3. En `sync_tasas_ve` agregar validación cruzada: si la tasa BCV desvía >5% de la mediana de `dolarapi`+`exchangedynamic`, rechazar y emitir alerta (Sentry).
- **Tests:** `test_bcv_scrape_falla_certificado_invalido` con `httpx` mock.
- **DoD:** la fuente sigue sincronizando en producción tras desplegar (verificar `TasaCambio.fuente='BCV_SCRAPE'` actualizada).
- **Esfuerzo:** M (½ día).

### H-SEC-4 · Cifrar `IntegracionERP.configuracion`
- **Archivo:** [`backend/apps/integration_hub/models.py:122`](../backend/apps/integration_hub/models.py#L122)
- **Pasos:**
  1. Añadir `django-cryptography==1.1` a requirements; configurar `CRYPTOGRAPHY_KEY` en settings (Fernet, leída de env).
  2. Cambiar `configuracion = models.JSONField(...)` por `EncryptedTextField` que serialice JSON internamente (helper en `apps/core/fields.py`).
  3. Migración data-migration: leer plano → cifrar → guardar. Reverse: descifrar → plano.
  4. **Rotar todas las credenciales actuales** (Odoo, BCV API keys si las hay) tras desplegar.
- **Tests:** `test_integracion_configuracion_encrypted_in_db` que verifica que un `psql SELECT` devuelve texto cifrado, no JSON plano.
- **DoD:** todos los `IntegracionERP` existentes son legibles vía ORM tras migración; dump SQL no expone secretos.
- **Esfuerzo:** L (2 días, incluye rotación coordinada).

### H-SEC-5 · Whitelist de extensiones en uploads
- **Archivos:** [`backend/apps/core/storage.py:84`](../backend/apps/core/storage.py#L84), [`backend/apps/gestion_documental/views.py:95`](../backend/apps/gestion_documental/views.py#L95)
- **Pasos:**
  1. Reemplazar blacklist por whitelist en `storage.py`:
     ```python
     ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp",
                            ".docx", ".xlsx", ".csv", ".txt", ".zip"}
     ```
  2. Forzar `Content-Disposition: attachment; filename="..."` en las URLs prefirmadas (parámetro en `boto3 generate_presigned_url`).
  3. Bonus: validación de magic bytes con `python-magic` para los uploads más sensibles (factura, comprobante de retención).
- **Tests:** `test_upload_html_rechazado`, `test_upload_svg_rechazado`, `test_download_force_attachment`.
- **DoD:** uploads existentes siguen accesibles; nuevos `.html`/`.svg` rechazados con 400.
- **Esfuerzo:** M (½ día).

### H-SEC-6 · Tenant en `configuracion_motor` y `migracion_datos`
- **Archivos:** [`backend/apps/configuracion_motor/views.py:21,40`](../backend/apps/configuracion_motor/views.py#L21), [`backend/apps/migracion_datos/views.py:20`](../backend/apps/migracion_datos/views.py#L20)
- **Pasos:**
  1. `TipoDocumento`: agregar campo `id_empresa = FK(Empresa, null=True)` (null para globales). Migración data: marca actuales como globales. ViewSet: `get_queryset` filtra a globales (`id_empresa__isnull=True`) + tenant del user.
  2. `CatalogoValor`: mismo patrón.
  3. `PlantillaMigracion`: FK obligatoria a empresa.
  4. `ParametroSistema`: ya tiene `id_empresa`. Sobreescribir `perform_update`/`perform_destroy` exigiendo `es_superusuario_omni` cuando `instance.id_empresa is None` (cierra S-13 medio).
  5. Mientras no se haga la migración: gate temporal en `POST/PATCH/DELETE` exigiendo `request.user.es_superusuario_omni` para los tres modelos (mitigación rápida, una PR).
- **Tests:** `test_catalogo_cross_tenant_no_lista`, `test_parametro_sistema_global_solo_modificable_por_superusuario`.
- **DoD:** test de aislamiento en cada uno de los 3 modelos. Plan §4.3 actualizado.
- **Esfuerzo:** L (1.5 días, dato sensible — coordinar con Marco antes).

### H-SEC-7 · `usuario_roles_view` y `PermisosViewSet`
- **Archivos:** [`backend/apps/core/views.py:31`](../backend/apps/core/views.py#L31), [`backend/apps/core/viewsets.py:374`](../backend/apps/core/viewsets.py#L374)
- **Pasos:** filtrar `UsuarioRoles.objects.filter(id_usuario__empresas__in=get_empresas_visible(request.user))`. Para `PermisosViewSet` (catálogo global), restringir POST/PATCH/DELETE a superusuario.
- **Tests:** `test_usuario_roles_no_lista_de_otra_empresa`, `test_permisos_globales_no_modificables_por_no_superuser`.
- **Esfuerzo:** S (2 h).

### H-SEC-8 · Actions de `MovimientoCajaBanco` con `pk` crudo
- **Archivo:** [`backend/apps/finanzas/views.py:517,567`](../backend/apps/finanzas/views.py#L517)
- **Pasos:** dentro de los `@action` reemplazar `caja_id = pk` por `caja = self.get_object()` (Django REST aplica filtro de queryset automáticamente).
- **Tests:** `test_movimientos_caja_banco_cross_tenant_404` y equivalente para `movimientos_cuenta_bancaria`.
- **Esfuerzo:** S (1 h).

### H-SEC-9 · `marcar_asistencia` valida tenant del empleado
- **Archivo:** [`backend/apps/control_asistencia/views.py:138`](../backend/apps/control_asistencia/views.py#L138)
- **Pasos:** antes de crear `RegistroAsistencia`, validar `Empleado.objects.filter(pk=empleado_id, empresa__in=get_empresas_visible(request.user)).exists()` o `404`.
- **Tests:** `test_no_puedo_marcar_asistencia_de_empleado_otro_tenant`.
- **Esfuerzo:** S (1 h).

### H-SEC-10 · `balance_comprobacion` valida `empresa_id`
- **Archivo:** [`backend/apps/contabilidad/views.py:107`](../backend/apps/contabilidad/views.py#L107)
- **Pasos:** validar `empresa_id` contra `get_empresas_visible(request.user)` antes del filtro; devolver 404 si no.
- **Tests:** `test_balance_comprobacion_empresa_ajena_404`.
- **Esfuerzo:** S (30 min).

### H-SEC-11 · `compras.recepcionar` valida tenant en `Almacen` y `Producto`
- **Archivo:** [`backend/apps/compras/views.py:105`](../backend/apps/compras/views.py#L105)
- **Pasos:** agregar `id_empresa__in=_empresas(request)` a las queries de `Almacen.objects.get(...)` y `Producto.objects.get(...)`.
- **Tests:** `test_recepcion_no_acepta_almacen_de_otra_empresa`, `test_recepcion_no_acepta_producto_de_otra_empresa`.
- **Esfuerzo:** S (1 h).

### H-SEC-12 · Patrón `user.empresa` en `cxc/api/acuerdos.py`
- **Archivo:** [`backend/apps/cxc/api/acuerdos.py:31,41,159`](../backend/apps/cxc/api/acuerdos.py#L31)
- **Pasos:** reemplazar `request.user.empresa` por `get_empresas_visible(request.user)` en `get_queryset`, `perform_create` y `registrar_pago`. Auditar otros usos similares con grep `\.user\.empresa\b`.
- **Tests:** `test_acuerdo_cross_tenant_usuario_multi_empresa`.
- **Esfuerzo:** S (2 h).

### H-SEC-13 · `ParametroSistema` globales protegidos (parte alta de H-SEC-6)
Resuelto en H-SEC-6. Tracking aquí para checklist.

---

## 3. Altos — Bugs / R-CODE (Sem 2)

### H-BUG-1 · `compras` y `ventas` no tragan `MapeoContableNoEncontrado`
- **Archivos:**
  - [`backend/apps/compras/services.py:132`](../backend/apps/compras/services.py#L132) (`registrar_recepcion`)
  - [`backend/apps/compras/services.py:168`](../backend/apps/compras/services.py#L168) (`registrar_factura_compra`)
  - [`backend/apps/ventas/services.py:347`](../backend/apps/ventas/services.py#L347) (`confirmar_nota_venta`)
- **Pasos:**
  1. Definir política: empresa con `contabilidad_activa=True` y `id_mapeo_contable_default` configurado → fallo hard si no hay mapeo. Empresa sin contabilidad → operación procede sin asiento (caso bodega informal, R-PROD-3).
  2. Eliminar `except MapeoContableNoEncontrado: pass`; en su lugar, `if empresa.contabilidad_activa: raise` para que la `@transaction.atomic` reverse.
  3. Endpoint que invoca devuelve `400` con mensaje claro: "Configure Mapeo Contable para tipo X antes de operar."
- **Tests:** `test_recepcion_falla_si_falta_mapeo_y_contabilidad_activa`, `test_recepcion_ok_sin_mapeo_si_contabilidad_inactiva`, equivalentes para ventas.
- **Esfuerzo:** M (1 día). PR conjunta con H-BUG-2.

### H-BUG-2 · `emitir_factura_fiscal` no traga `AsientoError`
- **Archivo:** [`backend/apps/ventas/services.py:429`](../backend/apps/ventas/services.py#L429)
- **Pasos:**
  1. Eliminar `except AsientoError`; solo dejar `except MapeoContableNoEncontrado` y con condición `if not empresa.contabilidad_activa`.
  2. Si `empresa.es_contribuyente_iva and factura.monto_iva > 0`: mapeo de cuenta IVA es obligatorio; falla con `400`.
- **Tests:** `test_factura_fiscal_falla_si_falta_mapeo_iva`, `test_factura_fiscal_ok_sin_mapeo_iva_si_no_contribuyente`.
- **DoD:** ninguna factura SENIAT puede quedar "emitida" sin asiento si la empresa es contribuyente.
- **Esfuerzo:** M (½ día).

### H-BUG-3 · `OdooConnector` usa `_safe_float` para monetarios (R-CODE-4)
- **Archivos:**
  - [`backend/apps/integration_hub/connectors/base.py:202`](../backend/apps/integration_hub/connectors/base.py#L202) (`_safe_float`)
  - [`backend/apps/integration_hub/connectors/odoo/connector.py`](../backend/apps/integration_hub/connectors/odoo/connector.py) — líneas 339-341, 393-395, 441-444, 484, 672-673, 720
- **Pasos:**
  1. En `base.py`, añadir `_safe_decimal(value) -> Decimal: return Decimal(str(value)) if value not in (None, "", False) else Decimal("0")`.
  2. Reemplazar todas las invocaciones en `connector.py` (subtotal, impuestos, total, saldo_pendiente, amount_residual, amount). Mantener `_safe_float` solo para campos no monetarios si los hay.
  3. Verificar consumidores aguas abajo (`apps/cxc`, `apps/cuentas_por_cobrar`) — deberían aceptar Decimal ya.
- **Tests:** `test_odoo_pull_facturas_devuelve_decimal`, `test_odoo_pull_cartera_vencida_devuelve_decimal`, fixtures con XML-RPC mockeado.
- **DoD:** `grep -nP "_safe_float\b" backend/apps/integration_hub/connectors/odoo/` solo devuelve campos no monetarios documentados.
- **Esfuerzo:** M (1 día con tests).

### H-BUG-4 · `entregar_nota_venta` captura `Exception` genérico
- **Archivo:** [`backend/apps/ventas/services.py:265`](../backend/apps/ventas/services.py#L265)
- **Pasos:** reemplazar `except Exception` por `except (StockActual.DoesNotExist, ReservaInsuficienteError)`. Re-raise el resto con `logger.exception("Error liberando reserva ...")`.
- **Tests:** `test_entregar_nota_venta_re_raise_deadlock_simulado` (con `transaction.atomic` que falle).
- **Esfuerzo:** S (1 h).

---

## 4. Altos — API (Sem 1 cont.)

### H-API-1 · Mixin `EmpresaInjectMixin` para `ventas`
- **Archivos:** [`backend/apps/ventas/serializers.py:49+`](../backend/apps/ventas/serializers.py#L49), [`backend/apps/ventas/views.py`](../backend/apps/ventas/views.py)
- **Pasos:**
  1. En `apps/core/viewsets.py` agregar:
     ```python
     class EmpresaInjectMixin:
         def perform_create(self, serializer):
             serializer.save(id_empresa=get_empresa_primaria(self.request.user))
     ```
  2. Aplicarlo a los 16 ViewSets de ventas: `CotizacionViewSet`, `PedidoViewSet`, `NotaVentaViewSet`, `FacturaFiscalViewSet`, `NotaCreditoVentaViewSet`, `NotaCreditoFiscalViewSet`, `DevolucionVentaViewSet`, `ListaPrecioViewSet`, `DetallePrecioViewSet`, y los demás `DetalleXxxViewSet`.
  3. En cada serializer de `serializers.py`, sustituir `fields="__all__"` por whitelist explícita; añadir `read_only_fields = ["id_empresa", "<pk>", "fecha_creacion", "fecha_actualizacion"]`.
- **Tests:** `tests_api/test_ventas_tenant_isolation.py` con uno por modelo: `test_no_puedo_crear_pedido_con_id_empresa_ajena` etc.
- **DoD:** intento de `POST {"id_empresa": "<UUID otra empresa>", ...}` resulta en pedido con empresa del user (no la inyectada).
- **Esfuerzo:** L (2 días — son 16 serializers + tests).

### H-API-2 · Mixin para `compras` (12 serializers)
- **Archivos:** [`backend/apps/compras/serializers.py:22+`](../backend/apps/compras/serializers.py#L22), [`backend/apps/compras/views.py`](../backend/apps/compras/views.py)
- **Pasos:** mismo patrón, sobre 12 ViewSets/serializers (`OrdenCompra`, `Recepcion`, `FacturaCompra`, `Requisicion`, `OfertaProveedor`, sus detalles).
- **Tests:** ídem H-API-1 para compras.
- **Esfuerzo:** L (1.5 días).

### H-API-3 · `UsuariosSerializer` whitelist explícita
- **Archivo:** [`backend/apps/core/serializers.py:129`](../backend/apps/core/serializers.py#L129)
- **Pasos:** reemplazar `fields="__all__"` por lista explícita; excluir `is_superuser`, `is_staff`, `last_login`, `groups`, `user_permissions`, hashes. Para escritura de password mantener `write_only`.
- **Tests:** `test_usuario_serializer_no_expone_is_superuser`, `test_usuario_serializer_no_acepta_is_staff_desde_cliente`.
- **Esfuerzo:** S (1 h).

---

## 5. Medios y bajos (Sem 4–5)

> Lista priorizada. Cada item lleva archivo y tipo de cambio. Agrupar en PRs por familia ("seguridad-headers", "exception-handling", "scope-tenant-residual").

### Seguridad

| ID | Acción | Archivo | Esfuerzo |
|---|---|---|---|
| M-SEC-1 | Mover defaults débiles de docker-compose a `.env.example` (no en YAML) | `docker-compose.yml:59-74` | S |
| M-SEC-2 | Forzar HTTPS en Odoo XML-RPC (`https://` requerido salvo `DEBUG`) | `odoo/connector.py:627` | S |
| M-SEC-3 | Cookie `refresh_token` con `SameSite="Strict"` + `Secure` en prod | `core/auth_views.py:275` | S |
| M-SEC-4 | Reducir `ACCESS_TOKEN_LIFETIME` a 15 min (refresh sigue 7d) | `config/settings_base.py:199` | S |
| M-SEC-5 | Headers nginx: añadir `Content-Security-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` | `infra/nginx/nginx.prod.conf:36` | M |
| M-SEC-6 | `server_name` específico (no `_` wildcard) | `infra/nginx/nginx.prod.conf:25` | S |
| M-SEC-7 | Rate-limit nginx `burst=10 nodelay` con throttle más estricto | `infra/nginx/nginx.prod.conf:75` | S |
| M-SEC-8 | Validar magic bytes en uploads sensibles (factura, retención) | `gestion_documental/views.py:95` | M |
| M-SEC-9 | `CapabilityToken` con expiración obligatoria; scope `*` solo para superusuario | `core/models.py:634` + viewset | M |
| M-SEC-10 | MCP `actor_id` validado como UUID con `Usuarios.objects.filter(...).exists()` antes de FK | `core/mcp_server.py:662` | S |
| M-SEC-11 | `login_view` deja de loguear `username` en texto plano (usar hash truncado) | `core/auth_views.py:122` | S |
| M-SEC-12 | `S3_ACCESS_KEY` sin default `minioadmin` (fail si no está en env en prod) | `config/settings_base.py:299` | S |
| M-SEC-13 | Rate-limit por cuenta en `/api/auth/refresh` (django-ratelimit con key=user_or_ip) | `core/auth_views.py:413` | S |
| M-SEC-14 | `ALLOWED_HOSTS` en prod con guard si está vacío | `config/settings_prod.py:4` | S |
| M-SEC-15 | Revisar si CSRF middleware tiene sentido en API JWT-only (mantener para admin); documentar | `config/settings_dev.py:19` | S |

### Bugs

| ID | Acción | Archivo | Esfuerzo |
|---|---|---|---|
| M-BUG-1 | `inventario/mcp.py` retornar Decimal (no float) en respuestas MCP | `inventario/mcp.py:73` | S |
| M-BUG-2 | `fiscal.siguiente_numero` usar `select_for_update()` en el get inicial (R-CODE-4 implícito) | `fiscal/services.py:218` | S |
| M-BUG-3 | `confirmar_pedido` capturar excepción específica de reserva | `ventas/services.py:160` | S |
| M-BUG-4 | `gestion_documental.eliminar_archivo` migrar a soft delete (extender `SoftDeleteMixin` en `Documento`) | `gestion_documental/views.py:158` + models | M |
| M-BUG-5 | `core/viewsets.perform_destroy` quitar fallback a hard delete (R-CODE-6) | `core/viewsets.py:89` | S |
| M-BUG-6 | `finanzas/0020_migrate_pagos_data.py` reverse_code: documentar limitación o cambiar a noop seguro | `finanzas/migrations/0020:149` | S |
| M-BUG-7 | `cxc/cobranza` capturar `(ScoringError, DivisionByZero)` en lugar de `Exception` | `cxc/api/cobranza.py:67` | S |
| M-BUG-8 | `fraccionamiento.confirmar` debe reservar stock al crear venta pendiente | `cxc/api/fraccionamiento.py:81` | M |
| M-BUG-9 | `acuerdos.registrar_pago` calcular tasa real (`finanzas.obtener_tasa_actual`) en vez de hardcode 1 | `cxc/api/acuerdos.py:102` | S |
| M-BUG-10 | `acuerdos.registrar_pago` no tragar `Exception` en `generar_asiento` | `cxc/api/acuerdos.py:132` | S |
| M-BUG-11 | `liberar_reserva` manejar `DoesNotExist` y loguear, no silenciar | `inventario/services.py:150` | S |
| M-BUG-12 | `contabilidad._numero_asiento` usar `timezone.now().date()` en vez de `date.today()` | `contabilidad/services.py:73` | S |
| M-BUG-13 | `auth_views` blacklist token quitar `except Exception: pass` | `core/auth_views.py:404` | S |
| M-BUG-14 | `libros_seniat.py` no tragar parse errors; emitir warning Sentry | `fiscal/libros_seniat.py:246` | S |
| M-BUG-15 | `OdooConnector.pull_cartera_vencida` distinguir `dias_vencida=0` (al día) vs `None` (fecha inválida) | `odoo/connector.py:663` | S |

### API y duplicación

| ID | Acción | Archivo | Esfuerzo |
|---|---|---|---|
| M-API-1 | Eliminar code zombie restante en `core/urls.py` (verificar tras CRIT-1..3) | `apps/core/urls.py:41` | S |
| M-API-2 | `configuracion_motor` ViewSets — completar tenant gate (cierra residual de H-SEC-6) | `configuracion_motor/views.py:14` | S |
| M-API-3 | Reemplazar `str(exc)` por código de error en respuestas | `cxc/api/acuerdos.py:91` y similares | M |
| M-DUP-1 | Decidir y documentar: `apps/cxc` vs `apps/cuentas_por_cobrar` (mantener separación o unir) en ADR-009 | repo-wide | M (ADR + migración) |

---

## 6. Hallazgos NUEVOS (de la validación ejecutable 2026-06-01)

### NEW-MIG-1 · Migraciones pendientes sin commitear en `ventas` e `integration_hub`
- **Detectado por:** `manage.py makemigrations --check --dry-run` el 2026-06-01.
- **Cambios detectados:**
  - `ventas/0013_alter_*`: alter de PKs UUIDv7 sobre 16 modelos (`Cotizacion`, `DetalleCotizacion`, `Pedido`, etc.).
  - `integration_hub/0002_remove_*`: cambios en constraints `unique_together` + renombre de índices a naming Django + alteraciones de varios campos JSONField y FK.
- **Riesgo:** migraciones autodetectadas no commiteadas = drift entre modelo y BD. Próximo deploy fallará o aplicará migración silenciosa generada en CI.
- **Pasos:**
  1. Revisar el motivo: ¿alguien cambió `default=uuid7` recientemente? Revisar `git log -p` sobre `models.py` de ventas e integration_hub.
  2. Si los cambios son intencionales: `python manage.py makemigrations` y commitear las migraciones generadas con mensaje explicando el motivo.
  3. Si son incidentales (typo `verbose_name`, etc.): revertir el cambio en `models.py`.
  4. Añadir `makemigrations --check --dry-run` como step en CI (probablemente ya está; verificar `.github/workflows/ci.yml`).
- **DoD:** `makemigrations --check --dry-run` exit 0.
- **Esfuerzo:** M (½ día — depende de qué se decida con cada cambio).

### NEW-PAG-1 · `OrdenProduccion` pagination sin `ordering`
- **Detectado por:** warning `UnorderedObjectListWarning` en pytest sobre `apps.manufactura.models.OrdenProduccion`.
- **Pasos:** añadir `class Meta: ordering = ["-fecha_creacion"]` a `OrdenProduccion`, o `queryset = OrdenProduccion.objects.all().order_by("-fecha_creacion")` en el ViewSet.
- **Esfuerzo:** S (15 min).

### NEW-DOC-1 · Plan obsoleto vs realidad — `OperacionCambioDivisa` ya implementado
- **Detectado por:** grep dirigido el 2026-06-01.
- **Hallazgo:** [`backend/apps/tesoreria/models.py:41`](../backend/apps/tesoreria/models.py#L41) tiene `OperacionCambioDivisa` con ViewSet, serializer y comisiones. El plan §3.7 y §6.6 lo declaran pendiente.
- **Acción:** ya parcialmente corregido en este commit en `PLAN_MAESTRO_UNICO.md` §4.3. Pendiente:
  - Verificar si el patrón cumple R-CODE-11 (asiento contable automático en `serializers.create`).
  - Migrar a `apps/localizacion_ve` cuando se ejecute GAP-2.
- **Esfuerzo:** S verificación + L migración (mover a localización va en GAP-2).

### NEW-DOC-2 · Plan obsoleto — `auditoria` no tiene su propio `signals.py`
- Los signals viven en `core/signals.py`. Plan ya corregido en §4.2 en este commit.
- **Acción opcional (no bloqueante):** mover los signals a `apps/auditoria/signals.py` y registrar en `auditoria/apps.py` para consistencia. Esfuerzo S.

---

## 7. Gap del plan vs realidad (Sem 6)

> Estos no son bugs; son ajustes al plan derivados de la auditoría. Cierran la deuda de "plan refleja realidad".

### GAP-1 · Redactar **ADR-007** (arquitectura localización 2 capas)
- **Por qué ahora:** prerequisito de cualquier código país-específico en 1.F. Sin ADR-007, cada PR de la distribuidora va a hardcodear VE.
- **Pasos:**
  1. Crear `docs/decisions/ADR-007-arquitectura-localizacion-dos-capas.md` (template de README de decisions).
  2. Contenido base: tomar §3.7 y §6 de PLAN_MAESTRO_UNICO; añadir contrato de los 6 puertos (`MotorImpuestos`, `GeneradorDocumentoLegal`, `CalculadoraNomina`, `ProveedorTasas`, `MetodosPagoLocales`, `LibroLegal`); definir mecanismo de registro de localizaciones (`apps/localizacion/registry.py` planeado).
  3. Actualizar tabla §3.8 (cambiar 📝 → ✅).
  4. Actualizar tabla `docs/decisions/README.md`.
- **DoD:** ADR aceptado y vinculado desde PLAN_MAESTRO_UNICO §3.7.
- **Esfuerzo:** M (½ día redacción).

### GAP-2 · Crear `apps/localizacion/` framework + migrar `vzla_localizacion` → `localizacion_ve`
- **Pasos:**
  1. `apps/localizacion/`: `registry.py`, `ports.py` (abstract base classes para los 6 puertos), `services.py` (`get_localizacion(empresa)`).
  2. Renombrar `apps/vzla_localizacion` → `apps/localizacion_ve` (mover archivos, ajustar `INSTALLED_APPS`, migración `--rename-app`).
  3. Mover utilidades existentes (validators RIF/cédula, feriados VE, zona horaria, formatos) a `localizacion_ve/`.
  4. Implementar adaptador puente: `MotorImpuestosVE` que llama a las funciones actuales de `apps/fiscal/` (no mover lógica todavía — strangler fig).
  5. Añadir `Empresa.localizacion_legal_activa` y `localizacion_mercado_activa` (BooleanField, default True para empresas existentes — mantener compatibilidad).
- **Tests:** `test_localizacion_resuelve_por_empresa_pais`, `test_empresa_sin_localizacion_no_aplica_igtf`.
- **DoD:** Una `Empresa` con `pais_codigo_iso="CO"` y flags off no recibe IGTF al emitir factura.
- **Esfuerzo:** XL (1 semana, candidato a quincena impar R-PROC-7).
- **Dependencia:** GAP-1 aprobado.

### GAP-3 · Reescribir §5.2 (1.F–1.J) con sub-items "datos / lógica / UI" desglosados
- **Por qué:** la auditoría mostró que el plan está pesimista. Hay capas (modelos, services) ya construidas que el plan declara pendientes.
- **Items a desglosar:**
  - **1.F** "Caja diaria operativa" → software: ✅; carga datos: ⬜; operación 30 días: ⬜.
  - **1.G** "Devoluciones POS" → modelos: ✅; flujo POS UI: ⬜.
  - **1.H** "BOM" → modelos: ✅; UI + carga: ⬜.
  - **1.I** "Manufactura OF + costeo" → modelos: ✅; services: ⬜; UI: ⬜.
- **Esfuerzo:** S (editar plan; 1 h).

### GAP-4 · Backup automático PostgreSQL
- **Item de plan §4.3 y §1.J.** No existe scripts ni jobs.
- **Pasos:**
  1. Crear `infra/backup/pg_dump_omni.sh`: pg_dump con compresión, retención (semana = diarios; mes = 1 semanal; año = 1 mensual).
  2. Sube a S3/MinIO bucket `omni-erp-backups` con encriptación SSE-S3.
  3. Cron en docker-compose.prod.yml (sidecar) o GitHub Actions workflow (`schedule: cron`).
  4. Healthcheck: alerta Sentry si el último backup tiene >25 h.
  5. Documentar restore en `infra/backup/README.md` con `restore_dryrun.sh` que valida integridad.
- **DoD:** simulacro de restore desde último backup funciona en máquina dev.
- **Esfuerzo:** M (1 día).

### GAP-5 · SSL automático (Let's Encrypt)
- **Item §1.J.** `infra/nginx/nginx.prod.conf:109-113` lo tiene comentado.
- **Pasos:**
  1. Añadir `certbot` sidecar al `docker-compose.prod.yml`.
  2. Descomentar y completar bloque server SSL en `nginx.prod.conf`.
  3. Variables: `LETSENCRYPT_EMAIL`, `LETSENCRYPT_DOMAIN` en `.env`.
  4. Renovación automática vía cron.
  5. Headers HSTS, `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`.
- **DoD:** `curl -I https://<dominio>` devuelve 200 con cert válido.
- **Esfuerzo:** M (½ día — más fricción de DNS/dominio).

### GAP-6 · Archivar `PROJECT_LOG.md` de la raíz
- **Estado:** el plan §10 ya lo marca como obsoleto. Verificar si el archivo aún existe en raíz; si sí, moverlo a `docs/_archive/PROJECT_LOG_root_obsoleto.md`.
- **Esfuerzo:** XS (5 min — pero hacerlo ya).

---

## 8. Bloqueante real de 1.F — `migracion_datos` management commands (Sem 7)

> Este es el **bloqueante real declarado** por el plan §5.2 y confirmado por la auditoría. No es deuda; es trabajo de feature directo.

### TRACK-1F-1 · Management command `importar_clientes`
- **Archivo nuevo:** `backend/apps/migracion_datos/management/commands/importar_clientes.py`
- **Pasos:**
  1. Acepta argumento `--archivo` (CSV/XLSX) y `--empresa` (UUID o slug).
  2. Validación fila-por-fila con `apps/crm` serializers; dry-run primero, ejecución real con `--confirm`.
  3. Reporte: filas OK, filas con error con número de línea y mensaje.
  4. Idempotente: si `cliente.rif` ya existe en la empresa, actualiza en vez de duplicar.
- **DoD:** importa CSV ejemplo de 100 clientes en <30 s con reporte claro.
- **Esfuerzo:** M (1 día).

### TRACK-1F-2 · `importar_productos`
- Patrón análogo a TRACK-1F-1, modelo `inventario.Producto`. Esfuerzo M.

### TRACK-1F-3 · `importar_inventario_inicial`
- Carga `StockActual` por almacén; opcional movimiento ajuste-inventario con `tipo_movimiento=AJUSTE_INICIAL`. Esfuerzo M.

### TRACK-1F-4 · `importar_saldos_cxc`
- Crea `CuentaCobrar` con saldo inicial y `aging_inicial`. Vincula a `Cliente` por RIF. Esfuerzo M.

### TRACK-1F-5 · Smoke test integral
- Test que ejecuta los 4 management commands con fixtures CSV de la distribuidora real (anonimizadas) y verifica conteos. Esfuerzo S.

---

## 9. Workstream paralelo — ADR-008 (monorepo + shells)

> Trabajo del founder en el working tree al 2026-06-01. **No depende de este plan**, pero comparte CI. Se considera Phase 2 de ADR-008 (PWA Nivel 1 hardening) como **co-elegible** con Sem 5 si hay holgura.

Items no se enumeran aquí (los tiene ADR-008 §"Fases con DoD").

---

## 10. Checklist de cierre (al terminar todas las semanas)

- [ ] `git grep -nP "\.objects\.all\(\)" backend/apps/` revisado caso por caso; ningún ViewSet expone `.all()` sin filtro tenant.
- [ ] `grep -nrP "_safe_float\b" backend/apps/integration_hub/connectors/` solo en campos no monetarios documentados.
- [ ] `grep -nrP "except\s+Exception\s*:\s*pass" backend/apps/` con cero ocurrencias en código de negocio.
- [ ] `grep -nrP "fields\s*=\s*[\"']__all__[\"']" backend/apps/` revisado; serializers expuestos a clientes con whitelist.
- [ ] `python manage.py check --deploy --settings=config.settings` sin warnings en `DJANGO_ENV=prod`.
- [ ] `python manage.py makemigrations --check --dry-run` exit 0.
- [ ] `pytest -q` 850+ verde; `npm run tsc --noEmit` exit 0; `npm run test` verde.
- [ ] Backup PostgreSQL automatizado con restore simulado verde.
- [ ] SSL prod con HSTS y Let's Encrypt activo.
- [ ] ADR-007 aceptado; `apps/localizacion/` con framework de puertos; al menos `MotorImpuestos` portado.
- [ ] PLAN_MAESTRO_UNICO §5.2 desglosado por capa (datos/lógica/UI).
- [ ] PROJECT_LOG de raíz archivado.

---

## Apéndice A — Mapeo de items a PRs sugeridos

| PR | Items | Branch sugerido |
|---|---|---|
| `fix/audit-crit-1-3` | CRIT-1, CRIT-2, CRIT-3 | `fix/audit-detailviews-tenant` |
| `fix/audit-settings-failclose` | H-SEC-1, H-SEC-2 | `fix/audit-settings-failclose` |
| `fix/audit-tenant-views-residual` | H-SEC-6, H-SEC-7, H-SEC-8, H-SEC-9, H-SEC-10, H-SEC-11, H-SEC-12 | `fix/audit-tenant-views-batch` |
| `feat/audit-encrypt-integraciones` | H-SEC-4 | `feat/audit-encrypt-integraciones` |
| `feat/audit-upload-whitelist` | H-SEC-5 | `feat/audit-upload-whitelist` |
| `fix/audit-bcv-tls` | H-SEC-3 | `fix/audit-bcv-tls` |
| `fix/audit-rcode11-asientos-hard` | H-BUG-1, H-BUG-2 | `fix/audit-rcode11-asientos-hard` |
| `fix/audit-odoo-decimal` | H-BUG-3 | `fix/audit-odoo-decimal` |
| `fix/audit-empresa-inject-mixin` | H-API-1, H-API-2, H-API-3 | `fix/audit-empresa-inject-mixin` |
| `fix/audit-bugs-misc` | H-BUG-4, M-BUG-1..15 | `fix/audit-bugs-misc` |
| `fix/audit-security-headers` | M-SEC-1..15 | `fix/audit-security-headers` |
| `fix/audit-migrations-drift` | NEW-MIG-1 | `fix/audit-migrations-drift` |
| `chore/audit-pag-ordering` | NEW-PAG-1 | `chore/audit-pag-ordering` |
| `docs/audit-plan-cleanup` | NEW-DOC-1, NEW-DOC-2, GAP-3, GAP-6 | `docs/audit-plan-cleanup` |
| `docs/adr-007-localizacion` | GAP-1 | `docs/adr-007-localizacion` |
| `feat/localizacion-framework` | GAP-2 | `feat/localizacion-framework` |
| `feat/infra-backup-postgres` | GAP-4 | `feat/infra-backup-postgres` |
| `feat/infra-ssl-letsencrypt` | GAP-5 | `feat/infra-ssl-letsencrypt` |
| `feat/migracion-datos-cmds` | TRACK-1F-1..5 | `feat/migracion-datos-cmds` |

---

## Apéndice B — Resumen cuantitativo

- **Críticos:** 3 (cierran en 1.5 h)
- **Altos seguridad:** 13
- **Altos bugs:** 4
- **Altos API:** 3
- **Medios seguridad:** 15
- **Medios bugs:** 15
- **Medios API/dup:** 4
- **Nuevos (validación 2026-06-01):** 4
- **Gap del plan:** 6
- **Track 1.F (no es deuda, es feature):** 5

**Total items planeables:** 72.

---

*Documento generado a partir del workflow `omni-erp-full-audit` (run_id `wf_032f2ca2-ef8`) y validaciones ejecutables del 2026-06-01.*
*Próxima revisión: al cierre de Semana 1 o tras desplegar fix de los 3 críticos.*
