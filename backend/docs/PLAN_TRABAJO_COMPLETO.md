# Plan de Trabajo Completo — Omni ERP
> Generado: 2026-05-25 — Post-Audit exhaustivo de seguridad, bugs, tests, masterplan y deuda técnica.  
> Estado del proyecto al momento de este plan: **Fase 1 ~60% completa**, CI verde, 71.66% cobertura.

---

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Estado actual confirmado](#2-estado-actual-confirmado)
3. [Seguridad](#3-seguridad)
4. [Bugs](#4-bugs)
5. [Tests](#5-tests)
6. [Gaps vs Masterplan Fase 1](#6-gaps-vs-masterplan-fase-1)
7. [Deuda técnica](#7-deuda-técnica)
8. [Roadmap por semanas](#8-roadmap-por-semanas)
9. [Criterios de "Fase 1 completa"](#9-criterios-de-fase-1-completa)

---

## 1. Resumen ejecutivo

| Categoría | Total ítems | Críticos | Completados en audit |
|-----------|-------------|----------|----------------------|
| Seguridad | 6 | 2 | 1 (SEC-01) |
| Bugs | 8 | 3 | 2 (BUG-01, BUG-07) |
| Tests | 5 | 1 | 1 (TEST-FAIL-01) |
| Gaps Masterplan | 13 | 3 | 0 |
| Deuda técnica | 7 | 0 | 0 |
| **Total** | **39** | **9** | **4** |

**Tiempo estimado total:** ~6–8 semanas (1 desarrollador).  
**Bloqueante principal para producción:** GAP-01 (factura fiscal no conecta impuestos ni asiento contable).

---

## 2. Estado actual confirmado

### ✅ Completado en esta sesión de audit

| ID | Descripción | Archivo |
|----|-------------|---------|
| SEC-01 / BUG-01 | `SuscripcionActivaMiddleware` usaba `user.id_empresa` (siempre `None`) → corregido a `user.empresas.first()` | `apps/saas/middleware.py:89` |
| BUG-07 | `PlanViewSet.perform_update` sin protección → cualquier usuario podía modificar planes SaaS → corregido con `es_superusuario_omni` | `apps/saas/views.py` |
| TEST-FAIL-01 | 8 tests SENIAT TXT libro de ventas fallando → ahora 10/10 verdes | `tests_api/test_fiscal_m8.py` |

### ✅ Completado en sesiones anteriores (confirmado en audit)

- Multi-tenant filtros en: `contabilidad`, `auditoria`, `control_asistencia`, `servicio_cliente`
- Bugs `unique=True` en: `ventas`, `rrhh`, `contabilidad`, `almacenes`
- TanStack Query v5 migración completa en frontend
- MCP Server con CapabilityToken y scope enforcement
- Event Store (Redpanda/Kafka) con graceful degradation
- Servicio `generar_asiento()` en contabilidad (`MapeoContable`)
- Inventario services (`StockActual`, `MovimientoInventario`, `kardex`)
- CRM básico con `PipelineVentas`, `OportunidadNegocio`, `Actividad`
- Fiscal venezolano: IVA, IGTF, retenciones, SENIAT TXT

---

## 3. Seguridad

### SEC-01 ✅ RESUELTO
**`SuscripcionActivaMiddleware` siempre bypasseado**  
Ya corregido: `user.empresas.first()`.

---

### SEC-02 🔴 CRÍTICO — Endpoint sin autenticación
**Archivo:** `backend/apps/finanzas/views.py` ~línea 1096  
**Descripción:** `tipo_caja_choices` tiene `permission_classes=[]` — cualquier cliente sin autenticar puede consumir el endpoint.  
**Fix:**
```python
# Eliminar permission_classes=[] del decorador
@action(detail=False, methods=["get"], url_path="tipo-caja-choices")
def tipo_caja_choices(self, request):
    ...
```
**Esfuerzo:** 5 minutos  
**Riesgo si no se corrige:** Bajo (solo expone nombres de enums internos), pero viola el principio de menor privilegio y puede usarse para fingerprinting.

---

### SEC-03 🟠 MEDIO — Refresh token en localStorage (XSS risk)
**Archivo:** `frontend/src/contexts/AuthContext.tsx`  
**Descripción:** Access token Y refresh token almacenados en `localStorage`. Si hay cualquier XSS, el atacante puede robar ambos tokens y mantener acceso indefinido (el refresh tiene 7 días de vida).  
**Fix ideal:** Mover el refresh token a una cookie `httpOnly; Secure; SameSite=Strict` servida por el backend. El access token puede quedar en memoria (no localStorage).  
**Fix mínimo rápido:** Al menos remover el refresh de localStorage y almacenarlo en `sessionStorage` (persiste solo en la pestaña, se borra al cerrar).  
**Esfuerzo:** Fix mínimo 2h / Fix ideal 1 día (requiere endpoint dedicado de refresh en backend que setee la cookie).  
**Riesgo si no se corrige:** Medio-Alto en producción con usuarios reales.

---

### SEC-04 🟠 MEDIO — Detalles internos expuestos en errores 500
**Archivo:** `backend/apps/core/auth_views.py` líneas ~514, ~565  
**Descripción:** Bloques `except Exception as e: return Response({"error": str(e)}, 500)`. En producción esto puede revelar rutas de archivos, nombres de tablas, queries SQL parciales.  
**Fix:**
```python
# Antes
except Exception as e:
    return Response({"error": str(e)}, status=500)

# Después
except Exception as e:
    logger.exception("Error inesperado en login: %s", e)
    return Response(
        {"error": "Error interno del servidor. Contacte al administrador."},
        status=500,
    )
```
**Esfuerzo:** 15 minutos  
**Archivos afectados adicionales:** Buscar con `grep -r "str(e)" apps/` para encontrar todos los casos.

---

### SEC-05 🟡 BAJO-MEDIO — Swagger/ReDoc accesibles en producción
**Archivo:** `backend/config/urls.py`  
**Descripción:** La documentación API (`/api/docs/`, `/api/redoc/`) está accesible para cualquier usuario autenticado en producción. Esto facilita el trabajo de un atacante que ya tiene credenciales.  
**Fix:**
```python
# Restringir a DEBUG=True o a is_staff
if settings.DEBUG or (request.user and request.user.is_staff):
    urlpatterns += [path("api/docs/", ...)]
```
**Esfuerzo:** 10 minutos

---

### SEC-06 🟡 BAJO — CORS abierto con DEBUG=True
**Archivo:** `backend/config/settings_base.py`  
**Descripción:** `CORS_ALLOW_ALL_ORIGINS = DEBUG`. Si alguien configura el servidor con `DEBUG=True` en producción (error común), CORS queda completamente abierto.  
**Fix:** Documentar explícitamente en `settings_prod.py` y agregar validación:
```python
# settings_prod.py
if CORS_ALLOW_ALL_ORIGINS:
    raise ValueError("CORS_ALLOW_ALL_ORIGINS=True no está permitido en producción.")
```
**Esfuerzo:** 15 minutos

---

### SEC-07 🟠 MEDIO — Sin rate limiting en login (fuerza bruta)
> También listado como GAP-05 en la sección de Masterplan.  
**Archivo:** `backend/apps/core/auth_views.py`  
**Descripción:** El endpoint `/api/auth/login/` no tiene ningún límite de intentos. Un atacante puede hacer fuerza bruta de contraseñas sin restricción.  
**Fix:** Implementar `django-ratelimit` o configurar límites a nivel de nginx/proxy.
```python
# Con django-ratelimit:
from django_ratelimit.decorators import ratelimit

@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def login(self, request):
    ...
```
**Alternativa:** Configurar en nginx: `limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m`  
**Esfuerzo:** 2-4 horas (instalación + tests)

---

## 4. Bugs

### BUG-01 ✅ RESUELTO
**SuscripcionActivaMiddleware** — ver SEC-01.

---

### BUG-02 ✅ RESUELTO (sesión anterior)
**Multi-tenant leakage** en contabilidad, auditoria, control_asistencia, servicio_cliente — confirmado corregido.

---

### BUG-03 🔴 CRÍTICO — `gastos/` sin filtro multi-tenant
**Archivo:** `backend/apps/gastos/views.py`  
**Descripción:** `CategoriaGastoViewSet`, `GastoViewSet` y `ReembolsoGastoViewSet` heredan de `viewsets.ModelViewSet` directamente, **no de `BaseModelViewSet`**. Consecuencias:
1. Sin `permission_classes = [IsAuthenticated]` explícito (depende del global, riesgoso).
2. Sin filtro por empresa — un usuario de Empresa A puede ver gastos de Empresa B.
3. Sin paginación estándar del sistema.

**Fix:**
```python
# Antes
class GastoViewSet(viewsets.ModelViewSet):
    queryset = Gasto.objects.all()
    ...

# Después
class GastoViewSet(BaseModelViewSet):
    queryset = Gasto.objects.all()

    def get_queryset(self):
        return Gasto.objects.filter(
            id_empresa__in=get_empresas_visible(self.request.user)
        )
```
**Aplicar a:** `CategoriaGastoViewSet`, `GastoViewSet`, `ReembolsoGastoViewSet`  
**Esfuerzo:** 30 minutos + tests

---

### BUG-04 ✅ RESUELTO (sesión anterior)
**`unique=True` sin `unique_together`** en ventas, rrhh, contabilidad, almacenes — confirmado corregido.

---

### BUG-05 🟠 MEDIO — `id_empleado_temp` frágil en control_asistencia
**Archivo:** `backend/apps/control_asistencia/models.py` (y views.py)  
**Descripción:** Al corregir multi-tenant en sesión anterior, se usó un UUID hardcodeado temporal (`id_empleado_temp`) para el filtro de tenant. Este parche es frágil y puede romperse en casos edge o consultas cruzadas.  
**Fix:** Restaurar la FK real `empleado → rrhh.Empleado → empresa` y filtrar por ella:
```python
def get_queryset(self):
    return Asistencia.objects.filter(
        empleado__empresa__in=get_empresas_visible(self.request.user)
    )
```
**Prerequisito:** Verificar que la migración FK esté creada y no hay datos huérfanos.  
**Esfuerzo:** 2-4 horas

---

### BUG-06 🟠 MEDIO — SaaS middleware fail-open en excepciones
**Archivo:** `backend/apps/saas/middleware.py` líneas 108-111  
**Descripción:** Si ocurre cualquier excepción al verificar la suscripción (ej: base de datos caída, modelo corrupto), el middleware hace **fail-open** — permite el paso. Para un sistema de billing, esto significa que una excepción técnica puede permitir acceso sin suscripción paga.  
**Fix:** Evaluar la política correcta para el negocio:
```python
except Exception as exc:
    logger.error("saas_middleware ERROR: %s", exc, exc_info=True)
    # Opción A: fail-open (actual) — favorece disponibilidad
    return None
    # Opción B: fail-closed — favorece control de billing
    return HttpResponse(
        content=json.dumps({
            "detail": "No se pudo verificar la suscripción. Intente más tarde.",
            "codigo": "VERIFICACION_FALLIDA",
        }),
        content_type="application/json",
        status=503,
    )
```
**Esfuerzo:** 20 minutos + decisión de negocio  
**Nota adicional:** `SAAS_VERIFICAR_SUSCRIPCION` aún defaultea en `False` — el middleware está corregido pero nunca activo. Activar cuando se tenga la lógica de suscripción completa.

---

### BUG-07 ✅ RESUELTO
**`PlanViewSet.perform_update` desprotegido** — ya corregido con `es_superusuario_omni`.

---

### BUG-08 🟡 BAJO — `_get_object_any_state()` muta QueryDict inmutable
**Archivo:** `backend/apps/core/viewsets.py`  
**Descripción:** `_get_object_any_state()` intenta mutar `request.data` (que es un `QueryDict` inmutable en Django para ciertos content-types). Puede crashear silenciosamente en edge cases con requests multipart.  
**Fix:** Hacer una copia mutable antes de modificar:
```python
data = request.data.copy()  # QueryDict.copy() retorna mutable
```
**Esfuerzo:** 1 hora (incluye test del edge case)

---

## 5. Tests

### TEST-FAIL-01 ✅ RESUELTO
**8 tests SENIAT TXT fallando** — ahora 10/10 verdes.

---

### TEST-01 — Estado de cobertura (aclaración)
**Cobertura real:** 71.66% (no 26% — ese número era de `--collect-only`).  
**Umbral actual:** `--cov-fail-under=30` (muy bajo).  
**Acción recomendada:** Subir el umbral gradualmente:
```ini
# pytest.ini
addopts = --cov=apps --cov-fail-under=75
```
Subir a 75 ahora, 80 en Fase 2.  
**Esfuerzo:** 5 minutos de config + identificar módulos que bajan el promedio.

---

### TEST-02 🟠 MEDIO — Suite de auth incompleta
**Archivo:** `backend/tests_api/test_auth.py` (solo 2 tests actualmente)  
**Tests faltantes:**
- `test_logout_blacklists_token` — verificar que el refresh token queda en blacklist post-logout
- `test_refresh_rotation` — POST a `/api/token/refresh/` retorna nuevo token y blacklistea el viejo
- `test_expired_access_token_rejected` — token expirado devuelve 401
- `test_login_wrong_password` — 401 con credenciales incorrectas
- `test_change_password_invalidates_tokens` — cambio de contraseña invalida sesiones previas
- `test_inactive_user_rejected` — `is_active=False` devuelve 401
- `test_rate_limit_login` — (cuando SEC-07 esté implementado) 6to intento devuelve 429

**Esfuerzo:** 3-4 horas

---

### TEST-03 🔴 CRÍTICO — Sin test E2E del chain ventas→fiscal→contabilidad→CxC
**Descripción:** El flujo más crítico del sistema (emitir factura → calcular impuestos → generar asiento contable → crear CxC) no tiene un test de integración end-to-end. Si alguien rompe cualquier eslabón de esta cadena, no hay detección automática.  
**Tests a crear en** `tests_api/test_e2e_ciclo_venta.py`:
```
1. Crear cliente + empresa con configuración IVA
2. Crear pedido de venta → verificar estado PENDIENTE
3. Aprobar pedido → verificar transición a APROBADO
4. Emitir factura → verificar:
   a. IVA calculado correctamente (base × 0.12)
   b. AsientoContable creado (crédito ingresos, débito CxC)
   c. CuentaCobrar creada con monto correcto
   d. StockActual decrementado (si aplica)
5. Registrar pago → verificar:
   a. CxC marcada COBRADA
   b. Asiento de cobro generado
   c. Saldo caja/banco incrementado
```
**Prerequisito:** GAP-01 debe estar resuelto primero.  
**Esfuerzo:** 1-2 días

---

### TEST-04 🟠 MEDIO — `gastos/` sin tests de tenant isolation
**Descripción:** Consecuencia directa de BUG-03. Una vez corregido el viewset, agregar tests:
- Usuario A no puede ver gastos de Empresa B
- Usuario A no puede crear gastos en Empresa B
- Filtros de queryset correctamente aplicados

**Esfuerzo:** 2-3 horas (puede hacerse junto con BUG-03)

---

### TEST-05 🟡 BAJO — Frontend sin coverage gate
**Archivo:** `frontend/package.json` y `.github/workflows/ci.yml`  
**Descripción:** Los tests de Vitest corren en CI pero no hay umbral de cobertura. Una regresión en componentes críticos pasaría sin ser detectada.  
**Fix:**
```json
// vitest.config.ts
coverage: {
  thresholds: {
    branches: 60,
    functions: 60,
    lines: 60,
  }
}
```
**Esfuerzo:** 1 hora de config + ver cuántos tests nuevos se necesitan

---

## 6. Gaps vs Masterplan Fase 1

### GAP-01 🔴 BLOQUEANTE — Factura fiscal no conecta impuestos ni contabilidad
**Archivo:** `backend/apps/ventas/services.py` (función `emitir_factura_fiscal()` o equivalente)  
**Descripción:** El servicio de emisión de facturas NO llama:
- `fiscal_services.calcular_impuestos()` — los impuestos (IVA 12%, IGTF 3%) no se calculan ni registran
- `contabilidad_services.generar_asiento()` — no se genera el asiento contable automático
- La CxC (`CuentaCobrar`) no se crea al emitir

Estos tres servicios YA EXISTEN y fueron implementados en sesiones anteriores — simplemente no están conectados al flujo de emisión de facturas.  
**Fix requerido:**
```python
@transaction.atomic
def emitir_factura(pedido, usuario):
    # 1. Crear la factura
    factura = FacturaVenta.objects.create(...)

    # 2. Calcular impuestos (ya existe)
    impuestos = fiscal_services.calcular_impuestos(
        empresa=pedido.id_empresa,
        items=pedido.items.all(),
        forma_pago=pedido.forma_pago,
    )
    factura.monto_iva = impuestos["iva"]
    factura.monto_igtf = impuestos["igtf"]
    factura.save()

    # 3. Generar asiento contable (ya existe)
    contabilidad_services.generar_asiento(
        empresa=pedido.id_empresa,
        tipo="FACTURA_VENTA",
        referencia=factura,
        monto=factura.total,
        usuario=usuario,
    )

    # 4. Crear CxC
    CuentaCobrar.objects.create(
        id_empresa=pedido.id_empresa,
        factura=factura,
        cliente=pedido.cliente,
        monto=factura.total,
        fecha_vencimiento=calcular_vencimiento(factura),
    )

    return factura
```
**Esfuerzo:** 2-3 días (incluye tests exhaustivos)  
**Nota:** Este es el GAP más crítico del sistema. Sin él, el ERP no puede usarse por empresas que necesiten contabilidad formal.

---

### GAP-02 🔴 ALTO — Verificar recepción compras → actualiza StockActual
**Archivo:** `backend/apps/compras/services.py` — función `registrar_recepcion()`  
**Descripción:** El servicio existe pero no está confirmado que llame a `inventario_services.registrar_entrada()` para actualizar `StockActual`. Si esta conexión falta, las recepciones de compra no actualizan el inventario.  
**Acción:** Auditar y si no existe, conectar:
```python
@transaction.atomic
def registrar_recepcion(orden_compra, items_recibidos, usuario):
    recepcion = RecepcionCompra.objects.create(...)
    
    # Verificar que esto existe:
    for item in items_recibidos:
        inventario_services.registrar_entrada(
            empresa=orden_compra.id_empresa,
            producto=item.producto,
            cantidad=item.cantidad_recibida,
            costo_unitario=item.precio_unitario,
            referencia=recepcion,
        )
    return recepcion
```
**Esfuerzo:** 2-4 horas (auditoría + fix si falta + test)

---

### GAP-03 🟠 MEDIO — Migración Contacto no ejecutada
**Descripción:** El modelo `Contacto` fue creado como parte del strangler fig pattern para unificar `Cliente` y `Proveedor`. La estructura existe pero los datos de clientes y proveedores existentes no tienen `Contacto` vinculado.  
**Acciones:**
1. Crear script de migración de datos: `python manage.py migrar_contactos`
2. Verificar que los endpoints de CRM que consumen `Contacto` funcionen correctamente
3. Agregar test de integridad: todos los `Cliente` deben tener `contacto` asociado

**Esfuerzo:** 1 día

---

### GAP-04 🟠 MEDIO — Redis/Celery ausentes en docker-compose.prod.yml
**Archivo:** `docker-compose.prod.yml` (o equivalente)  
**Descripción:** Las tareas async de Celery (notificaciones, reportes pesados, recordatorios de cobranza) no funcionarán en producción si Redis y el worker de Celery no están en el compose de producción.  
**Fix:**
```yaml
# Agregar a docker-compose.prod.yml:
redis:
  image: redis:7-alpine
  restart: unless-stopped
  volumes:
    - redis_data:/data

celery_worker:
  build: ./backend
  command: celery -A config worker -l info --concurrency=4
  env_file: .env.prod
  depends_on: [postgres, redis]
  restart: unless-stopped

celery_beat:
  build: ./backend
  command: celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
  env_file: .env.prod
  depends_on: [postgres, redis]
  restart: unless-stopped
```
**Esfuerzo:** 2-4 horas

---

### GAP-05 🟠 MEDIO — Sin rate limiting en login
> Ver SEC-07 para detalle completo.  
**Esfuerzo:** 2-4 horas

---

### GAP-06 🔴 ALTO — Inventario sin UI
**Descripción:** El módulo de inventario tiene servicios completos en el backend (`StockActual`, `MovimientoInventario`, `kardex`, ajustes manuales) pero **cero páginas en el frontend**.  
**Páginas a crear:**
- `/inventario` — Dashboard con stock bajo mínimo, alertas, KPIs
- `/inventario/kardex/:productoId` — Historial de movimientos del producto
- `/inventario/ajustes` — Formulario de ajuste manual con motivo y autorización
- `/inventario/stock` — Tabla de stock actual con filtros por almacén/categoría

**Esfuerzo:** 3-5 días (dependiendo de complejidad de UI)

---

### GAP-07 🔴 ALTO — Fiscal sin UI de configuración
**Descripción:** La configuración fiscal (alícuota IVA, condición de agente de retención, datos SENIAT, activación IGTF) no tiene ninguna página frontend. Un administrador no puede configurar el sistema sin acceso directo a la base de datos.  
**Páginas a crear:**
- `/configuracion/fiscal` — Formulario de configuración fiscal por empresa:
  - Alícuota IVA actual (default 12%)
  - ¿Es agente de retención de IVA? ¿De ISLR?
  - RIF empresa, datos para libros SENIAT
  - Activar/desactivar IGTF y su alícuota (default 3%)
- `/fiscal/libro-ventas` — Tabla con exportación a TXT SENIAT
- `/fiscal/libro-compras` — Tabla con exportación a TXT SENIAT
- `/fiscal/retenciones` — Gestión de comprobantes de retención

**Esfuerzo:** 2-3 días

---

### GAP-08 🟠 MEDIO — Paginación frontend incompleta
**Descripción:** La mayoría de las tablas del frontend consumen el primer resultado de TanStack Query sin manejar paginación. Con datos reales de producción (cientos/miles de registros), las tablas mostrarán solo los primeros 20 registros y no habrá forma de ver el resto.  
**Módulos afectados:** ventas, compras, CRM, gastos, contabilidad, reportes.  
**Fix:** Implementar paginación usando la respuesta paginada de DRF (`count`, `next`, `previous`, `results`):
```typescript
// Patrón con TanStack Query
const { data } = useQuery({
  queryKey: ['facturas', page, filters],
  queryFn: () => api.get(`/ventas/facturas/?page=${page}&page_size=20`),
});
// Renderizar <Pagination count={data?.count} page={page} onChange={setPage} />
```
**Esfuerzo:** 1-2 días (afecta múltiples componentes)

---

### GAP-09 🟡 BAJO-MEDIO — SaaS middleware activo pero siempre desactivado
**Archivo:** `backend/config/settings_base.py`  
**Descripción:** `SAAS_VERIFICAR_SUSCRIPCION = False`. El middleware fue corregido en esta sesión pero nunca se activa. Para un modelo SaaS, el cobro depende de que esto esté activo.  
**Acciones:**
1. Crear test de integración que verifique el comportamiento con suscripción activa/inactiva/expirada
2. Activar en staging para validar que no rompe ningún flujo
3. Activar en producción con flag de feature toggle

**Esfuerzo:** 1-2 días (principalmente tests)

---

### GAP-10 🟡 BAJO-MEDIO — Sentry no configurado
**Descripción:** Sentry fue mencionado en la Fase 0 del Masterplan pero no está instalado ni configurado. En producción, los errores no reportados son invisibles.  
**Fix:**
```python
# settings_prod.py
import sentry_sdk
sentry_sdk.init(
    dsn=env("SENTRY_DSN"),
    traces_sample_rate=0.1,
    environment="production",
)
```
```
pip install sentry-sdk[django]
```
**Esfuerzo:** 2-4 horas

---

### GAP-11 🟡 BAJO — Sin validación client-side en formularios críticos
**Descripción:** Los formularios de ventas, compras y fiscal confían completamente en la validación del backend. Errores como "cantidad negativa" o "fecha de vencimiento anterior a hoy" solo se detectan después del POST.  
**Fix:** Agregar validación con `react-hook-form` + `zod` (ya presente en el proyecto para algunos formularios):
```typescript
const schema = z.object({
  cantidad: z.number().positive("La cantidad debe ser mayor a 0"),
  precio: z.number().positive("El precio debe ser mayor a 0"),
  fecha_vencimiento: z.date().min(new Date(), "La fecha debe ser futura"),
});
```
**Esfuerzo:** 2-3 días (múltiples formularios)

---

### GAP-12 🟡 BAJO — API docs en producción sin restricción
> Ver SEC-05 para detalle completo.

---

### GAP-13 🔵 BACKLOG — 2FA / SSO
**Descripción:** Pendiente para Core Fase 2. No bloquea Fase 1.  
**Tecnologías a evaluar:** `django-allauth` (SSO), `django-otp` (2FA TOTP), o Keycloak.  
**Esfuerzo:** 1-2 semanas cuando llegue el momento

---

## 7. Deuda técnica

### TD-01 🟡 — `ModalPago.tsx` demasiado grande
**Archivo:** `frontend/src/components/ventas/ModalPago.tsx`  
**Descripción:** Componente monolítico con lógica de UI, cálculos de cambio, selección de método de pago y manejo de IGTF mezclados. Es difícil de testear y mantener.  
**Refactor propuesto:**
```
ModalPago/
  index.tsx              — orquestador, solo state y layout
  MetodoPagoSelector.tsx — selección de efectivo/tarjeta/crypto/etc.
  ResumenPago.tsx        — subtotal, IVA, IGTF, total
  CambioCalculator.tsx   — lógica de vuelto (solo para efectivo)
  hooks/
    useMetodoPago.ts
    useCambioCalculator.ts
```
**Esfuerzo:** 4-6 horas

---

### TD-02 🟡 — Hooks de formularios de venta duplicados
**Archivos:**  
- `frontend/src/hooks/usePedidoForm.ts`
- `frontend/src/hooks/useFacturaFiscalForm.ts`
- `frontend/src/hooks/useCotizacionForm.ts`
- `frontend/src/hooks/useNotaVentaForm.ts`

**Descripción:** Los cuatro hooks son estructuralmente idénticos: `items[]`, `calcularSubtotal()`, `calcularImpuestos()`, `agregarItem()`, `removerItem()`. El 80% del código está duplicado.  
**Refactor propuesto:**
```typescript
// useDocumentoVentaForm.ts — genérico
function useDocumentoVentaForm<T extends DocumentoVenta>(config: {
  tipo: 'pedido' | 'factura' | 'cotizacion' | 'nota';
  onSubmit: (doc: T) => Promise<void>;
}) { ... }
```
**Esfuerzo:** 1 día

---

### TD-03 🟠 — `id_empleado_temp` en control_asistencia
> Ver BUG-05 para detalle completo. Esta es la misma corrección vista desde el ángulo de deuda técnica.

---

### TD-04 🟡 — Threshold de cobertura demasiado bajo
**Archivo:** `backend/pytest.ini`  
**Descripción:** `--cov-fail-under=30` cuando la cobertura real es 71.66%. El threshold no protege contra regresiones — se puede bajar a 26% y CI seguiría verde.  
**Fix:** Subir a 75 ahora, target 80 para Fase 2.  
**Esfuerzo:** 5 minutos

---

### TD-05 🟡 — Importaciones circulares potenciales entre apps
**Descripción:** Varios servicios hacen imports inline (`from apps.fiscal.services import ...` dentro de funciones) para evitar circular imports. Esto es una señal de que la arquitectura de dependencias entre apps necesita ser revisada.  
**Acción:** Mapear el grafo de dependencias entre apps y definir capas claras:
```
core → (sin dependencias internas)
finanzas → core
ventas → core, finanzas, fiscal, inventario
compras → core, finanzas, fiscal, inventario
fiscal → core, finanzas
contabilidad → core, finanzas
```
**Esfuerzo:** 1 día (análisis + refactor de imports)

---

### TD-06 🟡 — Falta `__all__` en `__init__.py` de apps grandes
**Descripción:** Apps como `finanzas`, `ventas` y `core` tienen `__init__.py` vacíos. Definir `__all__` explícito mejora la navegabilidad del código y previene imports accidentales de símbolos privados.  
**Esfuerzo:** 2-3 horas

---

### TD-07 🟡 — `PROJECT_LOG.md` necesita mantenimiento
**Archivo:** `backend/PROJECT_LOG.md`  
**Descripción:** El log de proyecto tiene entradas de sesiones anteriores pero no refleja los cambios de esta sesión de audit (BUG-01, BUG-07, TEST-FAIL-01 corregidos). Mantenerlo actualizado es valioso como documentación histórica.  
**Acción:** Agregar entrada de Sesión 9 (Audit) con los ítems corregidos.  
**Esfuerzo:** 30 minutos

---

## 8. Roadmap por semanas

### Semana 1 — Seguridad rápida + Bug crítico de tenant
**Objetivo:** Eliminar las vulnerabilidades de bajo esfuerzo y el bug de tenant en gastos.

| Día | Tarea | ID |
|-----|-------|----|
| Lun | SEC-02: quitar `permission_classes=[]` de `tipo_caja_choices` | SEC-02 |
| Lun | SEC-04: sanitizar `str(e)` en `auth_views.py` | SEC-04 |
| Lun | SEC-05: restringir Swagger/ReDoc a `DEBUG=True` | SEC-05 |
| Lun | SEC-06: validación CORS en `settings_prod.py` | SEC-06 |
| Mar | BUG-03: `gastos/views.py` → `BaseModelViewSet` + tests | BUG-03, TEST-04 |
| Mié | BUG-06: decidir política fail-open vs fail-closed en SaaS middleware | BUG-06 |
| Mié | TD-04: subir threshold de cobertura a 75% | TD-04 |
| Jue | TD-07: actualizar `PROJECT_LOG.md` con sesión audit | TD-07 |
| Vie | TEST-02: suite de tests de autenticación completa | TEST-02 |

**CI al final de semana 1:** Verde, 73%+ cobertura.

---

### Semana 2 — GAP-01: Conectar el ciclo ventas→fiscal→contabilidad
**Objetivo:** El ítem más crítico del sistema. Sin esto no hay ERP completo.

| Día | Tarea | ID |
|-----|-------|----|
| Lun-Mar | Auditar `emitir_factura_fiscal()` y mapear exactamente qué falta conectar | GAP-01 |
| Mar-Jue | Implementar las 3 conexiones: impuestos + asiento + CxC | GAP-01 |
| Vie | TEST-03: test E2E del ciclo completo | TEST-03 |

**Al final de semana 2:** El flujo factura→impuesto→asiento→CxC funciona y tiene test E2E.

---

### Semana 3 — GAP-02, GAP-04, SEC-07
**Objetivo:** Completar la infraestructura de producción y seguridad de acceso.

| Día | Tarea | ID |
|-----|-------|----|
| Lun-Mar | GAP-02: auditar y conectar `registrar_recepcion()` → `StockActual` | GAP-02 |
| Mié | GAP-04: Redis + Celery en `docker-compose.prod.yml` | GAP-04 |
| Jue-Vie | SEC-07 / GAP-05: rate limiting en login con `django-ratelimit` | SEC-07 |

---

### Semana 4 — UI Inventario (GAP-06)
**Objetivo:** Primera UI completa para un módulo sin frontend.

| Día | Tarea | ID |
|-----|-------|----|
| Lun | Dashboard de inventario con alertas de stock bajo mínimo | GAP-06 |
| Mar | Página de kárdex por producto | GAP-06 |
| Mié | Formulario de ajuste manual | GAP-06 |
| Jue | Tabla de stock actual con filtros | GAP-06 |
| Vie | Tests de Vitest para los nuevos componentes | TEST-05 |

---

### Semana 5 — UI Fiscal (GAP-07) + Paginación (GAP-08)
**Objetivo:** Completar la UI de fiscal y corregir la paginación.

| Día | Tarea | ID |
|-----|-------|----|
| Lun-Mar | Formulario de configuración fiscal por empresa | GAP-07 |
| Mar-Mié | Páginas de libro de ventas y compras con exportación TXT | GAP-07 |
| Jue-Vie | Implementar paginación estándar en tablas del frontend | GAP-08 |

---

### Semana 6 — Bugs restantes + deuda técnica
**Objetivo:** Limpiar los bugs de menor prioridad y deuda técnica.

| Día | Tarea | ID |
|-----|-------|----|
| Lun-Mar | BUG-05: restaurar FK real en `control_asistencia` (= TD-03) | BUG-05 |
| Mié | BUG-08: corregir mutación de `QueryDict` en `_get_object_any_state()` | BUG-08 |
| Jue-Vie | TD-01: split de `ModalPago.tsx` en subcomponentes | TD-01 |

---

### Semana 7 — SEC-03, GAP-09, GAP-10, TD-02
**Objetivo:** Seguridad de tokens, activación SaaS, observabilidad.

| Día | Tarea | ID |
|-----|-------|----|
| Lun-Mar | SEC-03: migrar refresh token de localStorage a httpOnly cookie | SEC-03 |
| Mié-Jue | GAP-09: tests de integración para SaaS middleware + activar en staging | GAP-09 |
| Vie | GAP-10: configurar Sentry en producción | GAP-10 |

---

### Semana 8 — Deuda técnica restante + preparar Fase 2
**Objetivo:** Cerrar Fase 1 con calidad.

| Día | Tarea | ID |
|-----|-------|----|
| Lun-Mar | TD-02: refactor hooks de formularios de venta | TD-02 |
| Mié | GAP-03: script de migración de datos Contacto | GAP-03 |
| Jue | TD-05: mapear y limpiar importaciones circulares | TD-05 |
| Vie | GAP-11: validación client-side básica en formularios críticos | GAP-11 |
| Vie | Revisar criterios de "Fase 1 completa" y planificar Fase 2 | — |

---

## 9. Criterios de "Fase 1 completa"

La Fase 1 se considera completa cuando se cumplen **todos** estos criterios:

### Funcionalidad core
- [ ] **GAP-01**: `emitir_factura_fiscal()` conecta con `calcular_impuestos()` + `generar_asiento()` + crea `CuentaCobrar`
- [ ] **GAP-02**: `registrar_recepcion()` actualiza `StockActual`
- [ ] **GAP-06**: Existe UI de inventario (kárdex + ajuste manual)
- [ ] **GAP-07**: Existe UI de configuración fiscal
- [ ] **GAP-08**: Todas las tablas del frontend tienen paginación funcional
- [ ] **GAP-04**: Redis + Celery en `docker-compose.prod.yml`

### Seguridad
- [ ] **SEC-02**: Sin endpoints con `permission_classes=[]`
- [ ] **SEC-04**: Sin `str(e)` en respuestas de error de producción
- [ ] **SEC-05**: Swagger restringido en producción
- [ ] **SEC-07 / GAP-05**: Rate limiting activo en `/api/auth/login/`

### Calidad
- [ ] **TEST-02**: Suite de auth con ≥ 8 tests
- [ ] **TEST-03**: Test E2E del ciclo ventas→fiscal→contabilidad→CxC
- [ ] **TEST-04**: Tests de tenant isolation para `gastos/`
- [ ] **TD-04**: Cobertura ≥ 75%, umbral configurado
- [ ] **BUG-03**: `gastos/` usando `BaseModelViewSet`

### Observabilidad
- [ ] **GAP-10**: Sentry configurado y recibiendo eventos de producción
- [ ] **GAP-04**: Celery Beat con tareas programadas funcionando

---

## Apéndice — Resumen de IDs por prioridad

### 🔴 Crítico / Bloqueante (hacer primero)
`GAP-01` `BUG-03` `SEC-02` `TEST-03` `GAP-02`

### 🟠 Alto (semanas 2-4)
`SEC-07/GAP-05` `GAP-04` `GAP-06` `GAP-07` `TEST-02` `BUG-05` `BUG-06`

### 🟡 Medio (semanas 5-7)
`SEC-03` `SEC-04` `SEC-05` `GAP-08` `GAP-09` `GAP-10` `GAP-11` `TD-01` `TD-02` `TD-04` `TEST-05`

### 🔵 Backlog (Fase 2)
`GAP-03` `GAP-13` `TD-05` `TD-06` `BUG-08` `SEC-06`

---

*Última actualización: 2026-05-25*  
*Próxima revisión sugerida: al completar Semana 2 (GAP-01 resuelto)*
