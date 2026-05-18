# Plan de Trabajo — Post-Auditoría Fase 1
**Versión:** 1.0  
**Fecha:** 2026-05-17  
**Origen:** Auditoría completa del codebase contra `PLAN_FASE1_DETALLADO.md` y `OMNI_ERP_MASTER_PLAN.md`  
**Tests al inicio:** 496 passed, 2 skipped  
**Módulos con DoD completo:** M2, M3, M6, M7, M9 (5/10)

---

## Resumen ejecutivo

La auditoría encontró **tres categorías de trabajo pendiente**:

1. **Deuda de seguridad** — fuga de datos entre tenants en múltiples módulos (afecta producción directamente)
2. **Integridad de datos** — campos `unique=True` globales que rompen multi-tenancy a nivel de base de datos
3. **Completitud del plan** — tareas del plan original no implementadas o implementadas parcialmente

El trabajo está dividido en **4 fases** ordenadas por impacto/riesgo. Una PR por fase.

---

## Fase A — Seguridad crítica (hacer antes de cualquier despliegue)

**Objetivo:** Cerrar todas las fugas de datos entre tenants.  
**Estimado:** 2–3 días  
**Criterio de salida:** `grep -r "queryset = .*objects.all()" apps/` sin ViewSets sin `get_queryset()`

### A-1 — Multi-tenant en `contabilidad/views.py`

**Problema:** `PlanCuentasViewSet.listar_por_tipo()` y `arbol_cuentas()` usan `self.queryset.filter(...)` en lugar de `self.get_queryset()`. Devuelven datos de **todas las empresas**.

**Fix:**
- `apps/contabilidad/views.py` — reemplazar `self.queryset` → `self.get_queryset()` en las 3 líneas afectadas
- Agregar `get_queryset()` con `id_empresa__in=get_empresas_visible(...)` a los 3 ViewSets (`PlanCuentasViewSet`, `AsientoContableViewSet`, `DetalleAsientoViewSet`)
- Agregar tests de aislamiento para contabilidad

**Archivos:** `apps/contabilidad/views.py`, `tests_api/test_contabilidad_isolation.py` (nuevo)

---

### A-2 — Multi-tenant en `control_asistencia/views.py`

**Problema:** 7 acciones custom con `self.queryset.filter(...)` sin filtro de empresa:
- `TurnoViewSet` L34, `HorarioViewSet` L74, `AsignacionHorarioViewSet` L85
- `RegistroAsistenciaViewSet` L159, L173, `ReporteAsistenciaViewSet` L289, L303

**Fix:**
- Agregar `get_queryset()` con filtro de empresa a todos los ViewSets del módulo
- Reemplazar `self.queryset` → `self.get_queryset()` en todas las acciones custom
- Agregar tests de aislamiento

**Archivos:** `apps/control_asistencia/views.py`, `tests_api/test_asistencia_isolation.py` (nuevo)

---

### A-3 — Multi-tenant en `servicio_cliente/views.py`

**Problema:** `TicketSoporteViewSet.filtrar()` L213 construye `queryset = self.queryset.filter(**filters)` — devuelve tickets de todas las empresas.

**Fix:**
- Agregar `get_queryset()` con filtro empresa a todos los ViewSets
- Cambiar `self.queryset` → `self.get_queryset()` en acción `filtrar`
- Agregar tests de aislamiento

**Archivos:** `apps/servicio_cliente/views.py`, `tests_api/test_servicio_cliente_isolation.py` (nuevo)

---

### A-4 — Multi-tenant en `auditoria/views.py`

**Problema:** `LogAuditoriaViewSet` usa `LogAuditoria.objects.all()` sin filtro — logs de auditoría de **todas las empresas** son visibles para cualquier usuario autenticado.

**Fix:**
- Agregar `get_queryset()` filtrando por `id_empresa__in=get_empresas_visible(request.user)`
- Agregar tests de aislamiento

**Archivos:** `apps/auditoria/views.py`, `tests_api/test_auditoria_isolation.py` (nuevo)

---

### A-5 — Multi-tenant en 8 apps sin `get_queryset()`

**Problema:** Los siguientes módulos tienen ViewSets con `queryset = Modelo.objects.all()` y **ningún override** de `get_queryset()`:

| App | ViewSets afectados |
|-----|-------------------|
| `almacenes` | `AlmacenViewSet`, `UbicacionViewSet`, `ZonaViewSet` |
| `banca_electronica` | `CuentaBancariaViewSet`, `TransaccionBEViewSet` |
| `configuracion_motor` | `TipoDocumentoViewSet`, `ParametroSistemaViewSet`, `CatalogoValorViewSet` |
| `costos` | Todos los ViewSets |
| `despacho` | `DespachoViewSet`, `DetalleDespachoViewSet` |
| `gestion_aprobaciones` | `FlujoAprobacionViewSet`, `SolicitudAprobacionViewSet` |
| `integracion_b2b` | Todos los ViewSets |
| `manufactura` | `OrdenProduccionViewSet` y relacionados |
| `migracion_datos` | Todos los ViewSets |
| `tesoreria` | `OperacionCambioViewSet`, `CierreCajaViewSet` |

**Fix:**
- Para cada app: agregar `get_empresas_visible` import + `get_queryset()` en cada ViewSet
- `configuracion_motor/views.py`: cambiar herencia a `BaseModelViewSet`
- Agregar tests de aislamiento por módulo (al menos 2 tests por app)

**Archivos:** 10 archivos `views.py` + tests

---

### A-6 — `personalizacion/views.py` — sin API

**Problema:** La app `personalizacion` tiene modelos y DSL pero ningún `views.py` ni `urls.py`. El agente M9-T2 puede modificar `PersonalizacionConfig` pero no hay endpoint para que el frontend gestione estas configuraciones.

**Fix:**
- Crear `apps/personalizacion/views.py` con `PersonalizacionConfigViewSet` + `get_queryset()` con filtro empresa
- Crear `apps/personalizacion/urls.py`
- Registrar en `config/urls.py`

**Archivos:** `apps/personalizacion/views.py` (nuevo), `apps/personalizacion/urls.py` (nuevo), `config/urls.py`

---

## Fase B — Integridad de datos (antes del primer cliente real)

**Objetivo:** Eliminar todos los `unique=True` globales que impiden que dos empresas distintas tengan los mismos valores en campos que son normales repetir.  
**Estimado:** 1–2 días  
**Nota crítica:** Cada cambio requiere una migración Django. Ejecutar en orden, sin datos en producción o con backup previo.

### B-1 — `ventas/models.py` — números de documento globalmente únicos

**Problema:** Tres campos con `unique=True` que deberían ser únicos **por empresa**:
- L31: `numero_pedido = models.CharField(..., unique=True)` → `unique_together = ["id_empresa", "numero_pedido"]`
- L95: `numero_nota = models.CharField(..., unique=True)` → `unique_together = ["id_empresa", "numero_nota"]`
- L311: `numero_nota_credito = models.CharField(..., unique=True)` → `unique_together = ["id_empresa", "numero_nota_credito"]`

**Fix:** Quitar `unique=True`, agregar `Meta.unique_together`, generar migración.

**Archivos:** `apps/ventas/models.py`, nueva migración

---

### B-2 — `rrhh/models.py` — `cedula` globalmente única en `Empleado`

**Problema:** L26: `cedula = models.CharField(..., unique=True)`. Un empleado con la misma cédula no puede trabajar en dos empresas distintas del sistema.

**Fix:** Quitar `unique=True`, agregar `unique_together = ["empresa", "cedula"]`, generar migración.

**Archivos:** `apps/rrhh/models.py`, nueva migración

---

### B-3 — `contabilidad/models.py` — código de cuenta y número de asiento globales

**Problema:**
- L9: `codigo_cuenta = models.CharField(..., unique=True)` → `unique_together = ["id_empresa", "codigo_cuenta"]`
- L36: `numero_asiento = models.CharField(..., unique=True)` → `unique_together = ["id_empresa", "numero_asiento"]`

**Fix:** Quitar `unique=True`, agregar `unique_together`, generar migración.

**Archivos:** `apps/contabilidad/models.py`, nueva migración

---

### B-4 — `almacenes/models.py` — códigos de almacén y ubicación globales

**Problema:**
- L10: `codigo_almacen = unique=True` → `unique_together = ["id_empresa", "codigo_almacen"]`
- L39: `codigo_ubicacion = unique=True` → `unique_together = ["id_almacen", "codigo_ubicacion"]` (la ubicación ya está acotada al almacén)

**Fix:** Quitar `unique=True`, agregar `unique_together`, generar migración.

**Archivos:** `apps/almacenes/models.py`, nueva migración

---

### B-5 — Otros modelos con `unique=True` problemáticos

| App | Modelo | Campo | Fix |
|-----|--------|-------|-----|
| `tesoreria` | `OperacionCambio` | `numero_operacion` | `unique_together = ["id_empresa", "numero_operacion"]` |
| `servicio_cliente` | `TicketSoporte` | `numero_ticket` | `unique_together = ["id_empresa", "numero_ticket"]` |
| `gestion_aprobaciones` | `TipoAprobacion` | `codigo_tipo` | `unique_together = ["id_empresa", "codigo_tipo"]` |
| `configuracion_motor` | `ParametroSistema` | `codigo_parametro` | `unique_together = ["id_empresa", "codigo_parametro"]` |

**Fix para cada uno:** Quitar `unique=True`, agregar `unique_together`, generar migración.

---

## Fase C — URLs faltantes (funcionalidad incompleta)

**Objetivo:** Registrar las 11 apps que tienen `urls.py` pero no están incluidas en `config/urls.py`.  
**Estimado:** 2–4 horas  
**Prerrequisito:** Completar Fase A (para que las vistas tengan aislamiento antes de exponerlas)

### C-1 — Registrar apps en `config/urls.py`

Agregar al archivo `config/urls.py`:

```python
path("api/almacenes/",          include("apps.almacenes.urls")),
path("api/despacho/",           include("apps.despacho.urls")),
path("api/tesoreria/",          include("apps.tesoreria.urls")),
path("api/banca-electronica/",  include("apps.banca_electronica.urls")),
path("api/costos/",             include("apps.costos.urls")),
path("api/manufactura/",        include("apps.manufactura.urls")),
path("api/asistencia/",         include("apps.control_asistencia.urls")),
path("api/servicio-cliente/",   include("apps.servicio_cliente.urls")),
path("api/aprobaciones/",       include("apps.gestion_aprobaciones.urls")),
path("api/b2b/",                include("apps.integracion_b2b.urls")),
path("api/migracion/",          include("apps.migracion_datos.urls")),
path("api/personalizacion/",    include("apps.personalizacion.urls")),  # creada en A-6
```

**Nota:** Solo registrar después de que cada app tenga `get_queryset()` correcto (Fase A). No registrar una app sin aislamiento.

---

## Fase D — Completitud del plan original

**Objetivo:** Cerrar los gaps de funcionalidad detectados en los módulos M1, M4, M5, M8, M10.  
**Estimado:** 5–8 días (mayor esfuerzo, menor riesgo de seguridad)

### D-1 — M1-T2: Migración de datos `Cliente/Proveedor → Contacto`

**Problema:** El modelo `Contacto` existe y `Cliente`/`Proveedor` tienen FK nullable al mismo, pero **ningún dato existente tiene esa FK conectada**. El strangler fig está estructuralmente listo pero vacío.

**Fix:**
1. Crear `apps/core/management/commands/migrar_contactos.py`
2. Comando que por cada `Cliente` existente sin `contacto_id`: crea un `Contacto` con los datos del `Cliente` y enlaza la FK
3. Mismo para `Proveedor`
4. Mismo para `Empleado` (FK a `Contacto`)
5. Agregar tests: después de correr el comando, `Cliente.objects.filter(contacto__isnull=True).count() == 0`

**Archivos:** `apps/core/management/commands/migrar_contactos.py` (nuevo), `tests_api/test_migracion_contactos.py` (nuevo)

**DoD M1-T2:** Cero clientes/proveedores/empleados sin su Contacto enlazado.

---

### D-2 — M4-T4: `importar_masivo` en `ListaPrecio`

**Problema:** No existe el endpoint `POST /api/ventas/listas-precio/{pk}/importar_masivo/` requerido por el plan.

**Fix:**
1. En `apps/ventas/views.py`, agregar `@action(detail=True, methods=["post"], url_path="importar_masivo")` a `ListaPrecioViewSet`
2. Acepta `multipart/form-data` con CSV: columnas `codigo_producto,precio,moneda`
3. Parsear, validar, crear/actualizar `DetallePrecio` dentro de `@transaction.atomic`
4. Retornar `{"creados": N, "actualizados": M, "errores": [...]}`
5. Agregar tests: subir CSV válido → precios actualizados; CSV con errores → 400 con detalle

**Archivos:** `apps/ventas/views.py`, `tests_api/test_lista_precios_masivo.py` (nuevo)

---

### D-3 — M5-T3: Completar control de salidas de inventario

**Problema:** `TIPOS_SALIDA_CONTROLADA = frozenset({"SALIDA_INTERNA"})` en `inventario/services.py`. El plan requería también validar:
- `DESPACHO_VENTA` → debe venir de una `NotaVenta` en estado `ENTREGADA`
- `AJUSTE_INVENTARIO` → debe venir de un `AjusteInventario` en estado `APROBADO`

**Fix:**
1. En `apps/inventario/services.py`, función `_validar_documento_origen(movimiento)`:
   - Si `tipo == "DESPACHO_VENTA"`: verificar que `movimiento.documento_ref` sea una `NotaVenta` con `estado == "ENTREGADA"`
   - Si `tipo == "AJUSTE_INVENTARIO"`: verificar que sea un `AjusteInventario` aprobado
2. Llamar a `_validar_documento_origen()` desde `registrar_movimiento()` antes de crear el movimiento
3. Agregar tests: intentar `DESPACHO_VENTA` sin `NotaVenta` → `MovimientoError`; con `NotaVenta` correcta → ok

**Archivos:** `apps/inventario/services.py`, `tests_api/test_salidas_inventario.py` (extender)

---

### D-4 — M8-T6: Test de concurrencia de correlativos fiscales

**Problema:** `fiscal/services.py` usa `select_for_update()` para correlativos, pero no hay test que verifique que dos hilos simultáneos no generan el mismo número.

**Fix:**
1. Agregar `tests_api/test_fiscal_concurrencia.py`
2. Test con `threading.Thread` × 10 hilos llamando `obtener_siguiente_correlativo()` simultáneamente
3. Assert: lista de correlativos retornados tiene todos valores únicos (sin colisiones)
4. Timeout de 5s para prevenir deadlocks en CI

**Archivos:** `tests_api/test_fiscal_concurrencia.py` (nuevo)

---

### D-5 — M10-T4: Endpoint de notificaciones in-app

**Problema:** `core/models.py` define `Notificacion` con todos los campos necesarios, pero no hay ViewSet ni endpoint expuesto.

**Fix:**
1. En `apps/core/viewsets.py`, agregar `NotificacionViewSet`:
   - `get_queryset()` filtra por `id_empresa__in=empresas_visibles` Y `id_usuario=request.user`
   - Acción `POST /{pk}/marcar-leida/` → setea `leida=True`, `fecha_lectura=now()`
   - Acción `POST /marcar-todas-leidas/` → bulk update
   - Filtro por `?leida=false` para obtener solo no leídas
2. Registrar en `apps/core/urls.py`
3. Agregar tests: crear notificación → aparece en listado; marcar leída → `leida=True`

**Archivos:** `apps/core/viewsets.py`, `apps/core/urls.py`, `tests_api/test_notificaciones.py` (nuevo)

---

### D-6 — M10-T6: Convertir `vzla_localizacion` en Django app instalable

**Problema:** `vzla_localizacion/` funciona como paquete de utilidades Python puro pero el plan lo requería como Django app instalable con `AppConfig` en `INSTALLED_APPS`.

**Fix:**
1. Crear `apps/vzla_localizacion/apps.py` con `VzlaLocalizacionConfig`
2. Agregar `__init__.py` con `default_app_config`
3. Agregar `"apps.vzla_localizacion"` a `INSTALLED_APPS` en `settings_base.py`
4. (No requiere modelos ni migraciones — solo el `AppConfig`)

**Archivos:** `apps/vzla_localizacion/apps.py` (nuevo), `config/settings_base.py`

---

### D-7 — Limpieza: eliminar archivos `*_backup.py`

**Problema:** 8 archivos de backup vivos en el repositorio que confunden a futuros colaboradores y pueden importarse accidentalmente:
- `apps/contabilidad/admin_backup.py`
- `apps/contabilidad/models_backup.py`
- `apps/control_asistencia/admin_backup.py`
- `apps/control_asistencia/models_backup.py`
- `apps/gastos/admin_backup.py`
- `apps/gastos/models_backup.py`
- `apps/servicio_cliente/admin_backup.py`
- `apps/servicio_cliente/models_backup.py`

**Fix:** `git rm` de los 8 archivos.

---

## Tabla resumen — Todos los items

| ID | Fase | Descripción | Impacto | Esfuerzo | Archivos afectados |
|----|------|-------------|---------|----------|--------------------|
| A-1 | A | Multi-tenant contabilidad/views.py | 🔴 Crítico | 2h | 2 |
| A-2 | A | Multi-tenant control_asistencia/views.py | 🔴 Crítico | 3h | 2 |
| A-3 | A | Multi-tenant servicio_cliente/views.py | 🔴 Crítico | 2h | 2 |
| A-4 | A | Multi-tenant auditoria/views.py | 🔴 Crítico | 1h | 2 |
| A-5 | A | Multi-tenant 8 apps sin get_queryset() | 🔴 Crítico | 1d | 10+ |
| A-6 | A | Crear views/urls para personalizacion | 🟠 Alto | 2h | 3 |
| B-1 | B | ventas: unique → unique_together | 🔴 Crítico | 1h | 2 |
| B-2 | B | rrhh: cedula unique → unique_together | 🔴 Crítico | 1h | 2 |
| B-3 | B | contabilidad: unique → unique_together | 🔴 Crítico | 1h | 2 |
| B-4 | B | almacenes: unique → unique_together | 🟠 Alto | 1h | 2 |
| B-5 | B | tesoreria, servicio_cliente, otros | 🟠 Alto | 2h | 8 |
| C-1 | C | Registrar 11 apps en config/urls.py | 🟠 Alto | 30min | 1 |
| D-1 | D | M1-T2: comando migrar_contactos | 🟡 Medio | 4h | 2 |
| D-2 | D | M4-T4: importar_masivo en ListaPrecio | 🟡 Medio | 3h | 2 |
| D-3 | D | M5-T3: control DESPACHO_VENTA/AJUSTE | 🟡 Medio | 3h | 2 |
| D-4 | D | M8-T6: test concurrencia correlativos | 🟡 Medio | 2h | 1 |
| D-5 | D | M10-T4: NotificacionViewSet + endpoint | 🟡 Medio | 3h | 3 |
| D-6 | D | M10-T6: vzla_localizacion como app | 🟢 Bajo | 30min | 2 |
| D-7 | D | Eliminar archivos *_backup.py | 🟢 Bajo | 15min | 8 |

**Total estimado:** ~4–6 días de trabajo enfocado

---

## Orden de ejecución recomendado

```
Día 1–2:  Fase A (A-1 → A-5) — seguridad primero
Día 2:    Fase B (B-1 → B-5) — migraciones de integridad
Día 3:    Fase C (C-1)       — registrar URLs + smoke tests
Día 4–6:  Fase D (D-1 → D-7) — completitud del plan
```

**Regla:** No avanzar a siguiente fase hasta que el test suite esté en verde.

---

## Criterios de salida del plan completo

- [ ] `grep -rn "queryset = .*objects.all()" apps/*/views.py` → cero resultados sin `get_queryset()` override
- [ ] `grep -rn "self\.queryset\." apps/*/views.py` → cero resultados (todos usan `self.get_queryset()`)
- [ ] `grep -rn "unique=True" apps/*/models.py` → revisados, todos justificados o convertidos a `unique_together`
- [ ] `config/urls.py` incluye las 19 apps originales + las 11 nuevas = 30 prefijos
- [ ] Tests: ≥ 550 passed (cubre todas las apps con al menos test de aislamiento)
- [ ] Cero archivos `*_backup.py` en el repo
- [ ] M1, M4, M5, M8, M10 con DoD cumplido
- [ ] `python manage.py check --deploy` sin warnings críticos

---

## Notas para el desarrollador

### Por qué `unique_together` en vez de `unique=True`

Un `unique=True` en un campo del modelo Django crea un índice `UNIQUE` a nivel de base de datos **global** — no hay forma de restringirlo por empresa en el mismo índice. En un sistema multi-tenant, esto hace que dos empresas distintas no puedan tener el mismo valor (p.ej. `numero_pedido = "001"`), lo cual es completamente normal y esperado. La solución siempre es `unique_together = ["id_empresa", "campo"]` o `UniqueConstraint(fields=["id_empresa", "campo"])`.

### Por qué `get_queryset()` y no `queryset =`

El atributo `queryset = Modelo.objects.all()` se evalúa **una sola vez** al cargar el módulo y es compartido entre todos los requests. Las acciones custom que hacen `self.queryset.filter(...)` bypasean cualquier override de `get_queryset()` definido en el ViewSet, lo que crea una brecha de seguridad donde filtros por empresa definidos en `get_queryset()` son ignorados. Siempre usar `self.get_queryset()` dentro de las acciones.

### Checklist por cada ViewSet nuevo o modificado

```python
class MiViewSet(BaseModelViewSet):
    queryset = MiModelo.objects.all()       # requerido por DRF para el router
    serializer_class = MiSerializer

    def get_queryset(self):                 # OBLIGATORIO — R-CODE-1
        empresas = get_empresas_visible(self.request.user)
        return MiModelo.objects.filter(id_empresa__in=empresas)

    @action(detail=True, methods=["post"])
    def mi_accion(self, request, pk=None):
        obj = self.get_object()             # usa get_queryset() internamente ✅
        # NO: obj = self.queryset.get(pk=pk)  ❌
```
