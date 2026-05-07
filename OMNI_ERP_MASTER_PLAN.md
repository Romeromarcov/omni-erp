# Omni ERP â€” Plan Maestro del Proyecto
**VersiÃ³n:** 2.0 â€” Documento Ãšnico Consolidado  
**Autor:** Marco Â· Caracas, Venezuela  
**Ãšltima actualizaciÃ³n:** Abril 2026  
**Este documento reemplaza:** Resumen BD ERP 60M.txt Â· Resumen ERP 2.txt Â· Tablas y campos detallados.txt Â· implementation_plan.md Â· task.md

> *Cualquier persona que se incorpore al proyecto â€”desarrollador, diseÃ±ador, inversor, socioâ€” debe comenzar aquÃ­ y solo aquÃ­.*

---

## ÃNDICE

- [PARTE I â€” VisiÃ³n y Estrategia](#parte-i--visiÃ³n-y-estrategia)
- [PARTE II â€” Estado Actual del Proyecto](#parte-ii--estado-actual-del-proyecto)
- [PARTE III â€” Arquitectura TÃ©cnica](#parte-iii--arquitectura-tÃ©cnica)
- [PARTE IV â€” CatÃ¡logo de MÃ³dulos](#parte-iv--catÃ¡logo-de-mÃ³dulos)
- [PARTE V â€” Plan de Fases](#parte-v--plan-de-fases)
- [PARTE VI â€” Especificaciones del Mercado Venezolano](#parte-vi--especificaciones-del-mercado-venezolano)
- [PARTE VII â€” Ruta de ExpansiÃ³n Global](#parte-vii--ruta-de-expansiÃ³n-global)
- [PARTE VIII â€” EstÃ¡ndares TÃ©cnicos](#parte-viii--estÃ¡ndares-tÃ©cnicos)
- [PARTE IX â€” GuÃ­a de IncorporaciÃ³n al Equipo](#parte-ix--guÃ­a-de-incorporaciÃ³n-al-equipo)

---

# PARTE I â€” VisiÃ³n y Estrategia

## 1.1 QuÃ© es Omni ERP

Omni ERP es un sistema de gestiÃ³n empresarial (ERP) integral, modular y altamente adaptable, construido desde Venezuela para el mundo. No es un clon de SAP ni de Odoo: es un sistema diseÃ±ado desde cero para operar en entornos de alta complejidad monetaria, fiscalidad cambiante e informalidad gestionada â€” las condiciones reales del mercado venezolano y de buena parte de LatinoamÃ©rica.

**FilosofÃ­a central:**
- **Modular sin fricciÃ³n:** cada empresa activa Ãºnicamente los mÃ³dulos que necesita, sin que el resto exista para ella.
- **Sin rigidez contable impuesta:** una bodega informal puede vender, cobrar y controlar stock sin necesidad de plan de cuentas ni asientos contables.
- **Venezuela-first, world-ready:** el sistema nace resolviendo los problemas mÃ¡s difÃ­ciles del mundo (multimoneda real, pagos mixtos, fiscalidad inestable) y por eso funciona en cualquier otro contexto.
- **Escalable por diseÃ±o:** desde un microemprendimiento unipersonal hasta una corporaciÃ³n con 50 sucursales y 500 usuarios.

## 1.2 Propuesta de Valor

| Segmento | Problema que resuelve | Diferenciador vs. alternativas |
|---|---|---|
| PYME venezolana | Controlar ventas en USD+VES+crypto, retenciones, IVA | Nativo multimoneda, no adaptado |
| Empresa mediana | GestiÃ³n de nÃ³mina venezolana, RRHH, CxC/CxP | Fiscalidad VE completa de fÃ¡brica |
| Retail / Restaurante | POS multimoneda, manejo de divisas en caja | Sin configuraciÃ³n extra |
| Empresa con vendedores de campo | Portal de vendedores con operaciÃ³n offline | Funciona sin internet |
| Empresa con delivery propio | GestiÃ³n tipo Uber para Ãºltima milla | MÃ³dulo nativo, no integraciÃ³n |
| Empresa manufacturera | ProducciÃ³n + costos + calidad integrados | Sin mÃ³dulos separados que no hablan entre sÃ­ |
| Multinacional en VE | Cumplimiento fiscal local + reporting global | Multi-idioma, multi-moneda, multi-paÃ­s |

## 1.3 Mercado Objetivo

**Corto plazo (MVP â†’ AÃ±o 1):**
- PYMEs venezolanas con 5-100 empleados
- Sectores: retail, distribuciÃ³n, servicios, restauraciÃ³n
- Ticket promedio: suscripciÃ³n SaaS mensual o licencia on-premise

**Mediano plazo (AÃ±o 2-3):**
- Empresas medianas venezolanas (100-500 empleados)
- Distribuidores/revendedores que lleven Omni ERP a sus clientes
- Empresas en Colombia, Ecuador, PerÃº (contextos similares)

**Largo plazo (AÃ±o 4+):**
- Corporaciones multinacionales con operaciÃ³n en LATAM
- Mercado global hispanohablante como competidor directo de Odoo Community
- ExpansiÃ³n a mercados anglohablantes de alta complejidad fiscal

## 1.4 Principios de DiseÃ±o (No Negociables)

1. **Multi-tenant por defecto:** toda tabla de negocio tiene `id_empresa`. Sin excepciones.
2. **UUID como PK:** todos los modelos usan `UUIDField` como primary key. Sin auto-increment integers en producciÃ³n.
3. **AuditorÃ­a universal:** toda acciÃ³n que modifique datos de negocio genera un `LogAuditoria`. AutomÃ¡tico vÃ­a signals de Django.
4. **API-first:** toda la lÃ³gica de negocio es accesible vÃ­a API REST antes de que exista UI.
5. **Offline-capable:** los mÃ³dulos crÃ­ticos (POS, portal vendedores, portal conductores) funcionan sin conexiÃ³n y sincronizan al reconectarse.
6. **Soft delete:** los registros importantes no se eliminan fÃ­sicamente. Tienen `activo=False` o `estado=ANULADO`.
7. **ConfiguraciÃ³n sin cÃ³digo:** el comportamiento del sistema se configura desde la UI, no modificando cÃ³digo fuente.
8. **Failing loudly en desarrollo, silently en producciÃ³n:** errores detallados en dev, mensajes amigables en prod, siempre logueados.

---

# PARTE II â€” Estado Actual del Proyecto

## 2.1 Stack TecnolÃ³gico

### Backend
| Componente | TecnologÃ­a | VersiÃ³n | Estado |
|---|---|---|---|
| Framework | Django | 4.x | âœ… ProducciÃ³n |
| API | Django REST Framework | 3.x | âœ… ProducciÃ³n |
| Auth | SimpleJWT | latest | âœ… Implementado |
| Filtros | django-filter | 25.2 | âœ… Corregido path |
| Base de datos | SQLite (dev) / PostgreSQL (prod) | â€” | âš ï¸ Migrar a Postgres |
| Permisos | Sistema propio por roles | â€” | âœ… Funcional |
| AuditorÃ­a | Django Signals â†’ LogAuditoria | â€” | âœ… Implementado |
| Tareas async | â€” | â€” | âŒ Pendiente (Celery) |
| Cache | â€” | â€” | âŒ Pendiente (Redis) |
| Storage archivos | Local | â€” | âŒ Pendiente (S3/MinIO) |

### Frontend
| Componente | TecnologÃ­a | VersiÃ³n | Estado |
|---|---|---|---|
| Framework | React | 19 | âœ… |
| Lenguaje | TypeScript | strict mode | âœ… |
| Build tool | Vite | latest | âœ… |
| UI Library | MUI (Material UI) | v7 | âœ… Ãšnico permitido |
| Routing | React Router | v7 | âœ… |
| Estado global | Context API | â€” | âœ… (AuthContext, SidebarContext) |
| Estado server | â€” | â€” | âŒ Pendiente (React Query / TanStack) |
| i18n | â€” | â€” | âŒ Pendiente |
| PWA | â€” | â€” | âŒ Pendiente |
| Tests | â€” | â€” | âŒ Pendiente |

### Infraestructura
| Componente | Estado | Notas |
|---|---|---|
| Docker Compose | âœ… Definido | Backend + PostgreSQL |
| CI/CD | âŒ Pendiente | GitHub Actions |
| Monitoreo | âŒ Pendiente | Sentry + Prometheus |
| Backup automÃ¡tico | âŒ Pendiente | â€” |
| CDN | âŒ Pendiente | Para assets estÃ¡ticos |

## 2.2 MÃ³dulos Implementados (Estado Real)

### Completamente funcionales (lÃ³gica + API + UI)
- `core` â€” Empresa, Sucursal, Usuario, Rol, Permiso, Departamento
- `finanzas` â€” Monedas, MetodoPago, TransaccionFinanciera, CajaFÃ­sica, CajaVirtual, Datafono, SesionCaja, MovimientoCajaBanco, TasaBCV
- `ventas` â€” Cotizacion, Pedido, NotaVenta, FacturaFiscal, NotaCreditoVenta, NotaCreditoFiscal, DevolucionVenta (completo con detalles y pagos)
- `configuracion_motor` â€” TipoDocumento, ParametroSistema, CatalogoValor
- `auditoria` â€” LogAuditoria con signals automÃ¡ticos
- `inventario` â€” Producto, Categoria, UnidadMedida (parcial â€” sin movimientos de stock aÃºn)

### Parcialmente implementados (backend sin UI completa o viceversa)
- `finanzas.pagos` â€” PagosService unificado funcional, pero UI del ModalPago tiene deuda tÃ©cnica
- `compras` â€” Modelos definidos, API bÃ¡sica, sin UI
- `cuentas_por_cobrar` â€” Modelos definidos, sin UI
- `cuentas_por_pagar` â€” Modelos definidos, sin UI
- `manufactura` â€” Modelos bÃ¡sicos (ListaMateriales, OrdenProduccion), sin UI
- `fiscal` â€” App creada, sin modelos ni lÃ³gica
- `rrhh` â€” Modelos bÃ¡sicos de Empleado, sin nÃ³mina
- `nomina` â€” Modelos definidos, sin cÃ¡lculos
- `almacenes` â€” Modelos definidos, sin UI

### Solo estructura (app creada, sin lÃ³gica real)
- `crm`, `servicio_cliente`, `despacho`, `logistica_transporte`, `flota`
- `control_calidad`, `costos`, `gastos`, `tesoreria`
- `gestion_documental`, `gestion_aprobaciones`
- `control_asistencia`, `gestion_talento_rrhh`
- `banca_electronica`, `integracion_b2b`
- `migracion_datos`, `compliance`, `auditoria_cumplimiento`
- `proveedores`, `mantenimiento`, `wms_avanzado`

### No existe aÃºn (visiÃ³n futura)
- `saas_core` â€” GestiÃ³n del propio negocio Omni ERP como SaaS
- `notificaciones` â€” Motor de notificaciones (WhatsApp, email, push)
- `retail_pos` / `restaurante_pos` â€” POS dedicado
- `portal_clientes` / `portal_vendedores` / `portal_empleados`
- `portal_proveedores` / `portal_conductores_delivery`
- `delivery_general`, `servicios_proyectos`, `gestion_propiedades`
- `ml_ops`, `inteligencia_artificial_aplicada`, `analitica_negocio`, `iot_data`
- `planificacion_financiera`, `activos_fijos`, `reclutamiento_seleccion`
- `salud_seguridad_ocupacional`, `comedor_empleados`
- `comunicacion_interna`, `gestion_tareas_colaborativas`, `productividad_personal`
- `gestion_solicitudes_internas`, `gestion_procesos_negocio`
- `motor_reglas_negocio`, `gestion_api_externas`, `gestion_analitica_avanzada`
- `asistente_ia` â€” Copiloto conversacional (nueva recomendaciÃ³n)
- `reportes` â€” Motor de generaciÃ³n de documentos PDF (nueva recomendaciÃ³n)

## 2.3 Bugs y Deuda TÃ©cnica Conocida (Corregida en AuditorÃ­a Reciente)

Los siguientes problemas fueron identificados y corregidos durante la auditorÃ­a tÃ©cnica de Abril 2026:

| Problema | Archivo afectado | CorrecciÃ³n aplicada |
|---|---|---|
| `unique_together=['caja_fisica','estado']` impedÃ­a cerrar cajas mÃ¡s de una vez | `finanzas/models.py` | `UniqueConstraint` con `condition=Q(estado='ABIERTA')` |
| `codigo_centro` y `codigo_operacion` globalmente Ãºnicos (multi-tenant roto) | `manufactura/models.py` | `unique_together=['id_empresa','codigo_xxx']` |
| Import de `del` en `django_filters` con path incorrecto | `config/settings_base.py` | Corregido a `django_filters.rest_framework` |
| `logger` definido despuÃ©s de su primer uso | `ventas/views.py` | Movido al top; imports duplicados eliminados |
| `traceback.print_exc()` en producciÃ³n | `ventas/views.py` | `logger.exception()` + `raise` simple |
| Componentes wrapper MUI sin valor aÃ±adido | `components/Button,Input,Card,TextArea` | Eliminados; MUI directo |
| Import de `api.ts` en servicios usando `fetch` raw con `localhost:8000` hardcodeado | `cajasFisicasService.ts`, `auditoria.ts`, `tasaBCV.ts` | Migrados a `get/del` de `api.ts` |
| `cajasService.ts` nunca importado (cÃ³digo muerto) | `services/cajasService.ts` | Eliminado |
| `SidebarContext.tsx` duplicado (versiÃ³n muerta en `/contexts/`) | `contexts/SidebarContext.tsx` | Eliminado |
| Import de `api.ts` usando `localhost:8000` hardcodeado | `api.ts` | `import.meta.env.VITE_API_URL` con fallback |
| `.env.*` en `.gitignore` excluÃ­a `.env.example` | `.gitignore` | Agregadas excepciones `!.env.example` |
| `cajaService.ts` import despuÃ©s de primera funciÃ³n (sintaxis invÃ¡lida) | `cajaService.ts` | Reordenado; spreads redundantes eliminados |
| Servicios con `import('./api')` dinÃ¡mico innecesario | `metodosPagoEmpresaActiva.ts`, `monedasEmpresaActiva.ts` | ImportaciÃ³n estÃ¡tica + tipos propios |
| `bare except:` en utils | `finanzas/utils.py` | `except Exception:` |
| `debug_api.py`, `temp_views.py`, `bcv_debug.html`, `check_*.py` en repositorio | root + backend | Eliminados + `.gitignore` actualizado |
| `node_modules/` y `package.json` duplicados en raÃ­z | root | Eliminados |
| Router de 272 lÃ­neas con IIFEs en JSX | `router.tsx` | Dividido en 4 archivos de routes por dominio |
| ~80 sentencias `console.log/warn` de debug en producciÃ³n | mÃºltiples | Eliminados todos |
| Interfaz `Pago` duplicada antes de imports en ModalPago | `ModalPago.tsx` | Primera declaraciÃ³n eliminada |

## 2.4 Deuda TÃ©cnica Pendiente (No Corregida AÃºn)

### Alta prioridad
- [ ] **SQLite en desarrollo** â†’ migrar a PostgreSQL desde el dÃ­a 1 (el comportamiento de `unique_together` y constraints parciales difiere)
- [ ] **Sin TanStack Query / React Query** â†’ todas las pÃ¡ginas hacen fetch manual con `useEffect`. Causa: sin cache, sin re-fetch automÃ¡tico, sin estados de loading/error uniformes
- [ ] **`any` types restantes** (~12 ocurrencias en pÃ¡ginas de detalle) â†’ deben tipificarse con interfaces de respuesta API
- [ ] **Sin tests** (0% cobertura frontend y backend) â†’ crÃ­tico antes de primer cliente en producciÃ³n
- [ ] **ModalPago.tsx demasiado grande** (~600 lÃ­neas) â†’ debe dividirse en subcomponentes
- [ ] **Sin Celery** â†’ tareas largas (cÃ¡lculo de nÃ³mina, exportaciÃ³n de reportes, envÃ­o de emails) bloquean el hilo principal
- [ ] **Sin Redis** â†’ sin cache de sesiones, sin broker para Celery
- [ ] **Hooks `usePedidoForm`, `useFacturaFiscalForm`, `useCotizacionForm`, `useNotaVentaForm`** son casi idÃ©nticos â†’ deben unificarse en `useDocumentoVentaBase` completamente

### Media prioridad
- [ ] **Sin paginaciÃ³n en frontend** â†’ listas que pueden tener miles de registros cargan todo
- [ ] **Sin bÃºsqueda/filtros en la mayorÃ­a de listas** â†’ UX bloqueante para empresas con mucho volumen
- [ ] **Sin validaciÃ³n de formularios client-side** â†’ solo se valida en backend, errores lentos
- [ ] **Campos `null=True, blank=True` excesivos** en `manufactura/models.py` para FKs obligatorios
- [ ] **`documento_json` y `referencia_externa`** en modelos de manufactura sin propÃ³sito claro â†’ limpiar o documentar

---

# PARTE III â€” Arquitectura TÃ©cnica

## 3.1 VisiÃ³n General de la Arquitectura

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                    CLIENTES / USUARIOS                   â”‚
â”‚  Browser SPA  â”‚  PWA Mobile  â”‚  API externa  â”‚  IoT     â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
        â”‚              â”‚               â”‚
        â–¼              â–¼               â–¼
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚                    CDN / Reverse Proxy (Nginx)             â”‚
â”‚              SSL termination, rate limiting                â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                            â”‚
           â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
           â–¼                â–¼                â–¼
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚  React SPA  â”‚  â”‚ Django API  â”‚  â”‚  Celery      â”‚
    â”‚  (Vite/MUI) â”‚  â”‚ (DRF + JWT) â”‚  â”‚  Workers     â”‚
    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”˜
                            â”‚                â”‚
           â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
           â–¼                â–¼                â–¼
    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
    â”‚ PostgreSQL  â”‚  â”‚    Redis    â”‚  â”‚  S3/MinIO    â”‚
    â”‚   (datos)   â”‚  â”‚(cache+queue)â”‚  â”‚  (archivos)  â”‚
    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

## 3.2 Estrategia Multi-Tenant

**DecisiÃ³n arquitectural:** Single Database + Row-Level Tenancy (compartida con `id_empresa`).

**Por quÃ©:**
- Simple de implementar y mantener
- Funciona correctamente hasta ~1000 tenants con volumen moderado
- PostgreSQL Row-Level Security puede agregarse sin cambio de arquitectura
- MigraciÃ³n a schema-per-tenant posible en el futuro sin cambio de modelos

**Reglas obligatorias:**
1. Todo modelo de negocio tiene `id_empresa = ForeignKey('core.Empresa', ...)`
2. Todo ViewSet filtra por `empresa` del usuario autenticado en `get_queryset()`
3. NingÃºn endpoint devuelve datos de otra empresa jamÃ¡s
4. Tests de aislamiento deben existir para cada mÃ³dulo

**ExcepciÃ³n documentada:** Modelos globales de catÃ¡logo (`Moneda`, `MetodoPago` con `es_generico=True`, `Permiso`) pueden ser globales o por empresa segÃºn flag.

**MigraciÃ³n futura a escala:**
- Cuando supere 500 tenants activos â†’ evaluar PostgreSQL schemas por tenant
- Cuando supere 5000 tenants â†’ evaluar DB por tenant con proxy de enrutamiento

## 3.3 Modelo de Datos â€” Convenciones Universales

```python
# Todo modelo de negocio sigue este patrÃ³n base:

class BaseModel(models.Model):
    id_[nombre] = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    id_empresa = models.ForeignKey('core.Empresa', on_delete=models.CASCADE)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    activo = models.BooleanField(default=True)  # soft delete

    class Meta:
        abstract = True

# Campos opcionales comunes:
    referencia_externa = models.CharField(max_length=100, null=True, blank=True)
    # Para integraciones B2B â€” ID del registro en sistema externo

    observaciones = models.TextField(null=True, blank=True)
    # Notas libres del operador

    estado = models.CharField(max_length=30, choices=ESTADO_CHOICES, default='PENDIENTE')
    # Siempre con choices explÃ­citos, nunca texto libre
```

**Unique constraints â€” Regla de Oro:**
- `unique=True` solo para campos verdaderamente Ãºnicos globalmente (UUID, cÃ³digo ISO de moneda, etc.)
- Cualquier otro campo "Ãºnico" debe ser `unique_together = ['id_empresa', 'campo']`

**Relaciones polimÃ³rficas:**
```python
# Para vincular cualquier modelo a cualquier otro (auditorÃ­a, documentos, aprobaciones):
id_entidad_origen = models.UUIDField()
modelo_origen = models.CharField(max_length=100)  # Ej: 'ventas.Pedido'
# NO usar ContentType de Django â€” demasiado acoplado al ORM
```

## 3.4 API Design

**Base URL:** `/api/v1/`

**AutenticaciÃ³n:** JWT via `Authorization: Bearer <token>`

**Formato de respuesta estÃ¡ndar:**
```json
{
  "count": 150,
  "next": "/api/v1/ventas/pedidos/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

**Errores estÃ¡ndar:**
```json
{
  "error": "CODIGO_ERROR",
  "message": "DescripciÃ³n legible por humanos",
  "details": { "campo": ["El campo es requerido."] }
}
```

**Versioning:** `/api/v1/` por URL. Cuando haya breaking changes â†’ `/api/v2/` con perÃ­odo de deprecaciÃ³n de 6 meses.

**Rate limiting:** 1000 requests/hora por usuario autenticado (implementar con Django Ratelimit o Nginx).

## 3.5 Seguridad

- **AutenticaciÃ³n:** JWT con refresh tokens, blacklist en logout y cambio de contraseÃ±a
- **AutorizaciÃ³n:** Permisos por rol + permiso especÃ­fico (`ventas.crear_pedido`)
- **CORS:** Solo orÃ­genes explÃ­citamente permitidos (no `*` en producciÃ³n)
- **HTTPS:** Obligatorio en producciÃ³n, redirigir HTTP â†’ HTTPS
- **Secrets:** Nunca en cÃ³digo. Solo en variables de entorno.
- **InyecciÃ³n SQL:** ORM de Django previene esto. No usar `.raw()` sin parÃ¡metros sanitizados.
- **XSS:** React escapa por defecto. No usar `dangerouslySetInnerHTML`.
- **CSRF:** Desactivado para API REST stateless (JWT). Activo si se usan sesiones Django.
- **Datos sensibles en logs:** JamÃ¡s logear contraseÃ±as, tokens, o datos de pago completos.

---

# PARTE IV â€” CatÃ¡logo de MÃ³dulos

## Leyenda de Estado

| Ãcono | Significado |
|---|---|
| âœ… | Implementado y funcional |
| ðŸ”¶ | Parcialmente implementado |
| ðŸ”² | Planificado, no iniciado |
| ðŸ’¡ | Nuevo â€” recomendado en esta auditorÃ­a |
| ðŸŒ | Fase global / largo plazo |

## Leyenda de Prioridad MVP

| Nivel | DescripciÃ³n |
|---|---|
| ðŸ”´ MVP | Necesario para cerrar el primer cliente de pago |
| ðŸŸ  Fase 2 | Necesario para retener clientes y crecer |
| ðŸŸ¡ Fase 3 | DiferenciaciÃ³n competitiva importante |
| ðŸŸ¢ Fase 4 | Liderazgo tÃ©cnico avanzado |
| ðŸ”µ Global | ExpansiÃ³n internacional |

---

## GRUPO I â€” MÃ³dulos Fundamentales

### `core` â€” NÃºcleo del Sistema
**Estado:** âœ… | **Prioridad:** ðŸ”´ MVP

GestiÃ³n de la estructura organizativa completa.

**Modelos clave:**
```
Empresa          â†’ id_empresa (UUID PK), nombre_legal, rif, id_moneda_base
Sucursal         â†’ id_sucursal, id_empresa, nombre, codigo_sucursal [unique_together empresa]
Departamento     â†’ id_departamento, id_empresa, nombre, id_jefe_departamento
Usuarios         â†’ id (int PK Django), id_empresa, username, email, roles
Rol              â†’ id_rol (UUID), id_empresa, nombre_rol
Permiso          â†’ id_permiso (UUID), codigo_permiso [global], modulo
RolPermiso       â†’ relaciÃ³n M2M
UsuarioRol       â†’ relaciÃ³n M2M con fecha_asignacion
```

**Pendiente:**
- [ ] Soporte de foto de perfil de usuario (URL a S3)
- [ ] 2FA opcional por empresa (TOTP)
- [ ] Login con Google / Microsoft SSO (para empresas medianas)
- [ ] LÃ­mite de sesiones activas por usuario configurable

---

### `configuracion_motor` â€” ConfiguraciÃ³n General
**Estado:** âœ… | **Prioridad:** ðŸ”´ MVP

**Modelos clave:**
```
TipoDocumento    â†’ codigo [global], prefijo_correlativo, ultimo_correlativo
ParametroSistema â†’ id_empresa (nullable), codigo_parametro, valor, tipo_dato
CatalogoValor    â†’ codigo_catalogo, valor, orden [por empresa]
```

**Pendiente:**
- [ ] UI para que el cliente configure parÃ¡metros sin soporte tÃ©cnico
- [ ] Versionado de parÃ¡metros (historial de cambios)
- [ ] ValidaciÃ³n de `tipo_dato` al guardar `valor_parametro`

---

### `auditoria` â€” Registro de AuditorÃ­a
**Estado:** âœ… | **Prioridad:** ðŸ”´ MVP

AutomÃ¡tico via Django Signals. Registra CREAR, ACTUALIZAR, ELIMINAR en todos los modelos crÃ­ticos.

**Pendiente:**
- [ ] UI de bÃºsqueda/filtro de logs (existe pero bÃ¡sica)
- [ ] RetenciÃ³n configurable por empresa (ej: 2 aÃ±os)
- [ ] ExportaciÃ³n de logs en formato CSV/Excel para auditorÃ­as externas
- [ ] Alertas automÃ¡ticas por patrones sospechosos (muchos logins fallidos, eliminaciÃ³n masiva)

---

### `gestion_documental` â€” GestiÃ³n de Documentos
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

**Modelos clave:**
```
Carpeta          â†’ id_empresa, nombre, id_carpeta_padre (recursivo), es_publica
Documento        â†’ ruta_almacenamiento, tipo_contenido, tamano_bytes, version
VinculoDocumento â†’ id_documento, id_entidad_origen (UUID), modelo_origen (str)
PermisoDocumento â†’ id_documento, id_usuario/id_rol, puede_ver/editar/eliminar
```

**Recomendaciones adicionales:**
- IntegraciÃ³n con MinIO (self-hosted S3-compatible) para instalaciones on-premise
- IntegraciÃ³n con Google Drive / Dropbox para empresas que lo requieran
- Firma digital de documentos (DocuSign API o equivalente)
- Preview de PDF/imÃ¡genes en el navegador sin descarga

---

### `gestion_aprobaciones` â€” Flujos de AprobaciÃ³n
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

**Modelos clave:**
```
TipoAprobacion   â†’ id_empresa, codigo_tipo [unique_per_empresa], modulo_origen
FlujoAprobacion  â†’ id_tipo_aprobacion, orden_etapa, rol_aprobador/usuario, montos
SolicitudAprobacion â†’ id_entidad_origen (UUID), modelo_origen, estado, etapa_actual
RegistroAprobacion  â†’ decision (APROBADO/RECHAZADO/DELEGADO), comentarios
```

**Recomendaciones adicionales:**
- NotificaciÃ³n automÃ¡tica al aprobador cuando llega solicitud
- AprobaciÃ³n desde el email (link firmado con token temporal)
- AprobaciÃ³n desde WhatsApp (bot)
- Escalado automÃ¡tico si no hay respuesta en X horas

---

### `notificaciones` â€” Motor de Notificaciones
**Estado:** ðŸ’¡ Nuevo | **Prioridad:** ðŸ”´ MVP

> **Este mÃ³dulo no existÃ­a en la visiÃ³n original y es crÃ­tico para la adopciÃ³n.**

**DescripciÃ³n:** Canal centralizado para todas las notificaciones del sistema hacia usuarios internos, clientes, proveedores y conductores.

**Modelos clave:**
```
PlantillaNotificacion â†’ codigo_plantilla, asunto, cuerpo_html, cuerpo_texto
                        canal (INAPP/EMAIL/WHATSAPP/TELEGRAM/PUSH)
                        variables_json (lista de variables disponibles)

EventoNotificacion    â†’ codigo_evento (ej: PEDIDO_CREADO, PAGO_RECIBIDO)
                        id_empresa, activo
                        
SuscripcionNotificacion â†’ id_evento, id_usuario/id_rol, canal, activo

LogNotificacion       â†’ id_plantilla, destinatario, canal, estado (ENVIADO/FALLIDO/PENDIENTE)
                        intentos, fecha_envio, error_mensaje
```

**Canales a implementar (en orden de prioridad):**
1. **In-App** (notificaciones en el navbar) â€” inmediato
2. **Email** (SMTP/SendGrid) â€” semana 1
3. **WhatsApp Business API** (Meta Cloud API) â€” mes 1 â­ crÃ­tico para VE
4. **Telegram Bot** â€” mes 2
5. **Push Notifications** (Web Push / PWA) â€” mes 3

**Eventos iniciales crÃ­ticos:**
- Nuevo pedido creado
- Pago recibido
- AprobaciÃ³n pendiente
- Stock bajo mÃ­nimo
- Factura vencida
- SesiÃ³n de caja abierta/cerrada
- Error en integraciÃ³n externa

---

### `migracion_datos` â€” MigraciÃ³n e ImportaciÃ³n
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Herramienta para carga inicial de datos (clientes, productos, inventario, empleados) desde Excel/CSV.

**Pendiente:**
- [ ] UI para subir archivo y previsualizar datos antes de importar
- [ ] ValidaciÃ³n fila por fila con reporte de errores descargable
- [ ] Rollback de migraciÃ³n si hay errores crÃ­ticos
- [ ] Templates de Excel descargables por mÃ³dulo

---

### `compliance` â€” Cumplimiento Normativo
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

GestiÃ³n de regulaciones, auditorÃ­as y actividades de cumplimiento.

---

### `gestion_procesos_negocio` â€” BPM
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

Motor de flujos de trabajo configurables sin cÃ³digo (similar a Zapier/n8n interno). Permite a las empresas definir automatizaciones entre mÃ³dulos.

---

### `motor_reglas_negocio` â€” Reglas de Negocio
**Estado:** ðŸ’¡ Nuevo | **Prioridad:** ðŸŸ¡ Fase 3

Centraliza la lÃ³gica condicional: validar operaciones, bloquear flujos, generar alertas segÃºn parÃ¡metros configurables (ej: "bloquear venta si el cliente tiene mÃ¡s de X dÃ­as de mora").

---

## GRUPO II â€” MÃ³dulos Financieros

### `finanzas` â€” Finanzas Generales
**Estado:** âœ… (80%) | **Prioridad:** ðŸ”´ MVP

**Lo que funciona:**
- Monedas (global + por empresa)
- MÃ©todos de pago por empresa con monedas asociadas
- TransaccionFinanciera unificada
- CajaFÃ­sica + CajaVirtual + Datafono
- SesionCaja con constraint parcial (solo una ABIERTA por caja)
- MovimientoCajaBanco
- TasaBCV automÃ¡tica

**Pendiente:**
- [ ] IntegraciÃ³n BCV mÃ¡s robusta (falla silenciosamente si el BCVL no responde)
- [ ] Tasa paralela (mercado informal) como campo configurable separado de BCV
- [ ] ConciliaciÃ³n automÃ¡tica de movimientos de caja al cierre de sesiÃ³n
- [ ] Cuadre de caja con diferencias (sobrante/faltante)
- [ ] Transferencias entre cajas UI completa
- [ ] Criptomonedas como mÃ©todo de pago (USDT TRC-20, BTC) con validaciÃ³n de wallet

---

### `fiscal` â€” Fiscalidad Venezolana
**Estado:** ðŸ”¶ (app creada, sin lÃ³gica) | **Prioridad:** ðŸ”´ MVP

> **Este es el mÃ³dulo mÃ¡s subestimado del proyecto. Sin Ã©l no se puede vender a empresas formales.**

**DescripciÃ³n:** GestiÃ³n completa de la fiscalidad venezolana y la base para cumplimiento fiscal en otros paÃ­ses.

**Modelos clave:**
```
ConfiguracionFiscalEmpresa
  â†’ id_empresa, es_agente_retencion_iva, es_agente_retencion_islr
  â†’ alicuota_iva_general (default: 16.00)
  â†’ alicuota_iva_reducida (default: 8.00)
  â†’ aplica_igtf (BooleanField)
  â†’ alicuota_igtf (default: 3.00)
  â†’ numero_control_desde, numero_control_hasta

TipoImpuesto
  â†’ codigo (IVA_GENERAL, IVA_REDUCIDO, IVA_EXENTO, ISLR_HONORARIOS,
             ISLR_SERVICIOS, IGTF, RETIVA_75, RETIVA_100)
  â†’ nombre, porcentaje, activo

RetencionImpuesto
  â†’ id_empresa, id_documento_origen (UUID), modelo_origen
  â†’ tipo_retencion (IVA/ISLR/IGTF)
  â†’ monto_base, porcentaje_retencion, monto_retenido
  â†’ numero_comprobante_retencion
  â†’ estado (PENDIENTE/EMITIDA/ENTREGADA)

LibroFiscal
  â†’ id_empresa, tipo (COMPRAS/VENTAS), periodo (YYYY-MM)
  â†’ estado (ABIERTO/CERRADO/DECLARADO)
  â†’ total_ventas_gravadas, total_credito_fiscal, total_debito_fiscal
  
DetalleLibroFiscal
  â†’ id_libro, id_documento_origen, numero_factura, rif_cliente
  â†’ base_imponible, alicuota, monto_impuesto
```

**Funcionalidades requeridas:**
1. CÃ¡lculo automÃ¡tico de IVA en ventas y compras
2. **IGTF:** detectar automÃ¡ticamente cuÃ¡ndo aplica (pago en divisas/crypto) y calcular el 3%
3. Comprobantes de RetenciÃ³n de IVA e ISLR (PDF con nÃºmero de comprobante)
4. Libro de Compras y Libro de Ventas con formato SENIAT
5. ExportaciÃ³n a Excel en formato de declaraciÃ³n mensual
6. Factura Fiscal con todos los campos obligatorios venezolanos:
   - NÃºmero de control, nÃºmero de factura
   - Datos del emisor completos (RIF, direcciÃ³n fiscal)
   - DescripciÃ³n + precio unitario + cantidad + base imponible + IVA + total
   - Leyenda de retenciÃ³n si aplica
   - QR code de verificaciÃ³n (futuro)

---

### `contabilidad` â€” Contabilidad General
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Plan de cuentas, asientos contables automÃ¡ticos desde transacciones, estados financieros.

**DiseÃ±o crÃ­tico:** La contabilidad debe ser **opcional por empresa**. Las empresas informales no deben ver contabilidad. ActivaciÃ³n desde `configuracion_motor`.

**Modelos clave:**
```
PlanCuentas      â†’ id_empresa, codigo_cuenta, nombre, tipo (ACTIVO/PASIVO/...)
                   nivel, id_cuenta_padre (recursivo)
AsientoContable  â†’ id_empresa, fecha, concepto, estado (BORRADOR/PUBLICADO/ANULADO)
                   id_documento_origen (UUID), modelo_origen
DetalleAsiento   â†’ id_asiento, id_cuenta, debe, haber
CierreContable   â†’ id_empresa, periodo (YYYY-MM), estado, fecha_cierre
```

---

### `cuentas_por_cobrar` â€” CxC
**Estado:** ðŸ”¶ | **Prioridad:** ðŸ”´ MVP

GestiÃ³n de saldos pendientes de clientes.

**Pendiente:**
- [ ] AntigÃ¼edad de cartera (aging report) â€” crÃ­tico para cobranza
- [ ] Estados de cuenta por cliente
- [ ] Alertas de vencimiento automÃ¡ticas
- [ ] Notas de crÃ©dito aplicadas a facturas pendientes
- [ ] Retenciones recibidas de clientes

---

### `cuentas_por_pagar` â€” CxP
**Estado:** ðŸ”¶ | **Prioridad:** ðŸŸ  Fase 2

GestiÃ³n de saldos a proveedores.

---

### `tesoreria` â€” TesorerÃ­a
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Flujo de efectivo, conciliaciÃ³n bancaria, operaciones de cambio.

---

### `banca_electronica` â€” Banca ElectrÃ³nica
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

IntegraciÃ³n con bancos venezolanos para conciliaciÃ³n automÃ¡tica de movimientos.

**Bancos prioritarios para Venezuela:**
- Bancamiga API
- Banesco en lÃ­nea (scraping si no hay API oficial)
- Mercantil
- BBVA Provincial

---

### `gastos` â€” GestiÃ³n de Gastos
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Gastos operativos, reembolsos a empleados, vinculaciÃ³n con cuentas contables.

---

### `planificacion_financiera` â€” Presupuestos
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

Presupuestos anuales/mensuales con comparativo real vs. presupuestado.

---

### `activos_fijos` â€” Activos Fijos
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

Ciclo de vida de activos: adquisiciÃ³n, depreciaciÃ³n, disposiciÃ³n.

---

### `saas_core` â€” GestiÃ³n del Propio Negocio Omni ERP
**Estado:** ðŸ’¡ Nuevo | **Prioridad:** ðŸ”´ MVP

> **No existÃ­a en la visiÃ³n original. Es el ERP del ERP.**

**DescripciÃ³n:** MÃ³dulo separado (posiblemente en una instalaciÃ³n separada) para gestionar los clientes de Omni ERP como producto.

**Modelos clave:**
```
PlanSuscripcion  â†’ nombre (Free/Starter/Pro/Enterprise), precio_mensual
                   modulos_incluidos (JSONField con lista de mÃ³dulos)
                   limite_usuarios, limite_almacenamiento_gb, soporte_nivel

ClienteOmni ERP â†’ nombre_empresa, rif, contacto_principal, email_facturacion
                   plan_actual, fecha_inicio, fecha_vencimiento
                   estado (TRIAL/ACTIVO/SUSPENDIDO/CANCELADO)

Reseller         â†’ nombre, margen_porcentaje, clientes (M2M a ClienteOmni ERP)

LicenciaModulo   â†’ id_cliente, modulo, activo, fecha_activacion
                   configuracion_json (lÃ­mites especÃ­ficos del mÃ³dulo)

UsageMetric      â†’ id_cliente, metrica (usuarios_activos, transacciones_mes,
                   almacenamiento_usado), valor, fecha

FacturaSaaS      â†’ id_cliente, periodo, monto, estado (PENDIENTE/PAGADA/VENCIDA)
                   metodo_pago, referencia_pago
```

---

## GRUPO III â€” Cadena de Suministro y LogÃ­stica

### `inventario` â€” Inventario
**Estado:** ðŸ”¶ | **Prioridad:** ðŸ”´ MVP

**Lo que funciona:** Producto, Categoria, UnidadMedida

**Pendiente urgente:**
- [ ] **Movimientos de stock** (entrada, salida, ajuste, traslado)
- [ ] **Stock por sucursal/almacÃ©n** (StockUbicacion)
- [ ] **Lotes y seriales** para productos que lo requieran
- [ ] **Stock mÃ­nimo/mÃ¡ximo** con alertas automÃ¡ticas
- [ ] **ValoraciÃ³n de inventario** (PEPS, promedio ponderado)
- [ ] Inventario fÃ­sico (conteo) vs. inventario teÃ³rico

**Modelos faltantes:**
```
MovimientoInventario â†’ tipo (ENTRADA/SALIDA/AJUSTE/TRASLADO)
                       id_producto, id_almacen, cantidad, costo_unitario
                       id_documento_origen (UUID), modelo_origen

StockActual         â†’ id_producto, id_almacen, cantidad_disponible
                      cantidad_reservada, costo_promedio

Lote                â†’ id_producto, numero_lote, fecha_vencimiento, cantidad

StockConsignacion   â†’ id_producto, tipo (CLIENTE/PROVEEDOR)
                      id_cliente_o_proveedor, cantidad_en_consignacion
```

---

### `almacenes` â€” GestiÃ³n de Almacenes
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Estructura fÃ­sica: almacÃ©n â†’ pasillo â†’ estante â†’ nivel â†’ posiciÃ³n.

---

### `compras` â€” Compras
**Estado:** ðŸ”¶ | **Prioridad:** ðŸ”´ MVP

**Pendiente:**
- [ ] UI completa del ciclo: Solicitud â†’ CotizaciÃ³n proveedores â†’ OC â†’ RecepciÃ³n â†’ Factura
- [ ] ComparaciÃ³n de cotizaciones de mÃºltiples proveedores
- [ ] OC en mÃºltiples monedas (crucial para Venezuela)
- [ ] RecepciÃ³n parcial de OC

---

### `proveedores` â€” GestiÃ³n de Proveedores
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Equivalente al CRM pero para proveedores. Datos maestros, historial, evaluaciÃ³n.

---

### `despacho` â€” Despacho de MercancÃ­as
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

---

### `logistica_transporte` â€” LogÃ­stica
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

---

### `flota` â€” GestiÃ³n de Flota
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

---

### `wms_avanzado` â€” WMS Avanzado
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¢ Fase 4

---

### `mantenimiento` â€” GestiÃ³n de Mantenimiento
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

---

### `planificacion_recursos_capacidad`
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¢ Fase 4

---

## GRUPO IV â€” Ventas y Clientes

### `crm` â€” CRM BÃ¡sico (Clientes)
**Estado:** ðŸ”¶ | **Prioridad:** ðŸ”´ MVP

Datos maestros de clientes: RIF, razÃ³n social, direcciÃ³n, contactos, crÃ©dito disponible.

**Pendiente:**
- [ ] BÃºsqueda por RIF con autocompletado
- [ ] Historial completo de compras por cliente
- [ ] LÃ­mite de crÃ©dito con bloqueo automÃ¡tico
- [ ] GeolocalizaciÃ³n de clientes (mapa de cartera)
- [ ] CalificaciÃ³n crediticia interna

---

### `ventas` â€” GestiÃ³n de Ventas
**Estado:** âœ… (85%) | **Prioridad:** ðŸ”´ MVP

**Lo que funciona:** CotizaciÃ³n â†’ Pedido â†’ Nota de Venta â†’ Factura Fiscal, con detalles, descuentos, pagos mixtos y notas de crÃ©dito.

**Pendiente crÃ­tico:**
- [ ] IntegraciÃ³n con `inventario.MovimientoInventario` â€” actualmente no descuenta stock
- [ ] IntegraciÃ³n con `fiscal` â€” no calcula IVA, IGTF ni retenciones
- [ ] IntegraciÃ³n con `contabilidad` â€” no genera asientos
- [ ] IntegraciÃ³n con `cuentas_por_cobrar` â€” no genera saldo pendiente
- [ ] Correlativo automÃ¡tico de nÃºmeros de documento por empresa/sucursal
- [ ] Descuento por cliente/volumen automÃ¡tico
- [ ] Lista de precios mÃºltiples por moneda
- [ ] Reserva de stock al crear pedido

---

### `servicio_cliente` â€” Mesa de Ayuda
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Tickets de soporte con SLA, base de conocimiento, seguimiento.

---

### `crm_ventas_marketing` â€” CRM Avanzado
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

Pipeline de ventas, oportunidades, campaÃ±as de marketing, seguimiento de prospectos.

---

### `retail_pos` â€” Punto de Venta Retail
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

POS tactil optimizado para retail. Modo offline obligatorio.

**Requerimientos especÃ­ficos:**
- Interface tactil optimizada (no la UI general del ERP)
- Apertura/cierre de caja rÃ¡pida
- Lectura de cÃ³digo de barras (USB y cÃ¡mara)
- Pago mixto en mÃºltiples monedas en < 30 segundos
- Recibo tÃ©rmico (impresora de 80mm)
- Modo offline con sincronizaciÃ³n posterior

---

### `restaurante_pos` â€” Punto de Venta Restaurante
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

GestiÃ³n de mesas, comandas, cocina (pantalla KDS), divisiÃ³n de cuenta.

---

### Portales de Stakeholders

#### `portal_clientes` â€” Portal de Clientes
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

Autoservicio para clientes finales: historial, estado de pedidos, pagos, CxC.

#### `portal_vendedores` â€” Portal de Vendedores
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

App web (PWA futura) para vendedores de campo. Offline crÃ­tico.

**Funcionalidades:**
- Ver cartera de clientes asignados
- Crear pedidos / cotizaciones en campo
- Confirmar pagos recibidos (foto de comprobante)
- Ver estado de cuenta del cliente
- Ruta de visitas del dÃ­a
- Funciona sin internet (queue local + sync)

#### `portal_empleados` â€” Portal de Empleados
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Autoservicio para empleados: recibo de sueldo, solicitud de permisos, informaciÃ³n personal.

#### `portal_proveedores` â€” Portal de Proveedores
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

Ver OCs, subir facturas, consultar estado de pagos.

---

## GRUPO V â€” Manufactura y Calidad

### `manufactura` â€” Manufactura
**Estado:** ðŸ”¶ | **Prioridad:** ðŸŸ  Fase 2

**Lo que existe:** ListaMateriales, RutaProduccion, OrdenProduccion, CentroTrabajo, OperacionProduccion.

**Pendiente:**
- [ ] UI completa de gestiÃ³n de Ã³rdenes
- [ ] MRP automÃ¡tico (cÃ¡lculo de materiales necesarios para producir X unidades)
- [ ] Disponibilidad de materiales al crear OrdProd
- [ ] IntegraciÃ³n con inventario (consumo y producciÃ³n terminada)

---

### `costos` â€” Costeo
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

Costeo estÃ¡ndar, real, por lote. AnÃ¡lisis de variaciones.

---

### `control_calidad` â€” Control de Calidad
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

Planes de inspecciÃ³n, no conformidades, acciones correctivas (CAPA).

---

## GRUPO VI â€” Recursos Humanos

### `rrhh` â€” RRHH BÃ¡sico
**Estado:** ðŸ”¶ | **Prioridad:** ðŸ”´ MVP

**Modelos faltantes o incompletos:**
```
Empleado         â†’ datos personales, cargo, departamento, fecha_ingreso
                   tipo_contrato, salario_base, id_usuario (FK a core.Usuarios)
Cargo            â†’ id_empresa, nombre_cargo, nivel, descripcion
BeneficioLegal   â†’ tipo (CESTATICKET, HCM, ALIMENTACION, TRANSPORTE)
                   monto, periodicidad
```

---

### `nomina` â€” NÃ³mina
**Estado:** ðŸ”¶ | **Prioridad:** ðŸ”´ MVP para empresas con empleados

**Este es uno de los mÃ³dulos mÃ¡s complejos del sistema dado el contexto venezolano.**

**Especificaciones Venezuela:**
```
Componentes salariales:
  - Salario base (en VES + equivalente USD)
  - Cestaticket (monto fijo en USD o BCV)
  - Bono de alimentaciÃ³n
  - Bono de transporte
  - Horas extras (50% diurnas, 100% nocturnas)
  - Bono nocturno (30% del salario diurno proporcional)
  - Utilidades (15 dÃ­as mÃ­nimo, 120 dÃ­as mÃ¡ximo segÃºn LOTTT)
  - Vacaciones + bono vacacional
  - AntigÃ¼edad (5 dÃ­as por aÃ±o + 2 dÃ­as adicionales)

Deducciones:
  - SSO (4% empleado)
  - FAOV (1% empleado)
  - RPE (1% empleado)
  - ISLR (tabla progresiva en UT)
  - PrÃ©stamos y anticipos internos
  - Comedor de empleados

ProcesoNomina    â†’ id_empresa, periodo (quincenal/mensual), tipo (REGULAR/EXTRA)
                   estado (CALCULADO/APROBADO/PAGADO/CONTABILIZADO)

LineaNomina      â†’ id_proceso, id_empleado, concepto, monto, tipo (INGRESO/DEDUCCION)
```

**Pendiente:**
- [ ] Tabla de ISLR actualizable por SENIAT
- [ ] GeneraciÃ³n de ARC (constancias para ISLR)
- [ ] NÃ³mina en mÃºltiples monedas (salario en VES, cestaticket en USD)
- [ ] ExportaciÃ³n para pago bancario masivo
- [ ] IntegraciÃ³n con bancos para nÃ³mina electrÃ³nica

---

### `control_asistencia` â€” Asistencia
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Marcajes, ausencias, horas extras. IntegraciÃ³n con biomÃ©tricos.

---

### `gestion_talento_rrhh` â€” GestiÃ³n del Talento
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

Evaluaciones de desempeÃ±o, planes de desarrollo, capacitaciones.

---

### `reclutamiento_seleccion`
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

---

### `salud_seguridad_ocupacional`
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

---

### `comedor_empleados`
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

---

## GRUPO VII â€” Productividad

### `comunicacion_interna`
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Chat interno en tiempo real (WebSockets). Canales por departamento.

---

### `gestion_tareas_colaborativas`
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Tablero Kanban, sprints, asignaciÃ³n de tareas entre equipos.

---

### `gestion_solicitudes_internas`
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Requerimientos entre departamentos (tipo ticket interno).

---

### `productividad_personal`
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

Calendario personal, agenda, integraciÃ³n con Google Calendar.

---

## GRUPO VIII â€” Delivery

### `delivery_general` â€” GestiÃ³n de Entregas
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Modelo tipo Uber para asignaciÃ³n de entregas a conductores internos/externos.

---

### `portal_conductores_delivery`
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

PWA para conductores. GPS tracking, confirmaciÃ³n de entrega, foto de comprobante.

---

## GRUPO IX â€” Inteligencia y AutomatizaciÃ³n

### `reportes` â€” Motor de Documentos y Reportes
**Estado:** ðŸ’¡ Nuevo | **Prioridad:** ðŸ”´ MVP

> **Este mÃ³dulo no existÃ­a en la visiÃ³n original. Es el primero que los clientes evalÃºan visualmente.**

**DescripciÃ³n:** GeneraciÃ³n de documentos PDF configurables y reportes exportables.

**Funcionalidades:**
- Plantillas PDF de: Factura Fiscal, CotizaciÃ³n, OC, Nota de Entrega, Recibo de NÃ³mina
- ConfiguraciÃ³n de logo, colores y datos de la empresa por empresa
- Motor de reportes con filtros: ventas del perÃ­odo, aging de cartera, stock actual, etc.
- ExportaciÃ³n a PDF y Excel de cualquier reporte
- Reportes programados enviados por email
- Constructor visual de reportes personalizados (Fase 3)

**Stack recomendado:**
- `WeasyPrint` o `ReportLab` para PDF en Django
- `openpyxl` para Excel
- Templates HTML/CSS â†’ PDF via WeasyPrint

---

### `analitica_negocio` â€” Business Intelligence
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ  Fase 2

Dashboard ejecutivo con KPIs en tiempo real. GrÃ¡ficas de ventas, cobros, stock, nÃ³mina.

**Stack recomendado:**
- Charts: Recharts o ApexCharts (React)
- Agregaciones pesadas: views materializadas en PostgreSQL o Celery periodic tasks
- Dashboard configurable: drag & drop de widgets por usuario

---

### `inteligencia_artificial_aplicada` â€” IA Aplicada
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¢ Fase 4

Predicciones, recomendaciones y alertas basadas en ML. Consume resultados de `ml_ops`.

---

### `asistente_ia` â€” Copiloto Conversacional
**Estado:** ðŸ’¡ Nuevo | **Prioridad:** ðŸŸ¢ Fase 4

> **El diferenciador mÃ¡s poderoso para 2026+.**

**DescripciÃ³n:** Interfaz conversacional en lenguaje natural para interactuar con el ERP.

```
Usuario: "Â¿CuÃ¡l fue mi producto mÃ¡s vendido este mes?"
IA:      "El Producto X con 3.420 unidades vendidas. Â¿Quieres compararlo con el mes anterior?"

Usuario: "Necesito crear una orden de compra a Proveedor Y"
IA:      [Muestra formulario pre-llenado con datos del proveedor, espera confirmaciÃ³n]
```

**ImplementaciÃ³n:** RAG (Retrieval Augmented Generation) sobre datos del ERP + LLM (GPT-4o, Claude, o modelo local via Ollama para empresas con datos sensibles).

---

### `ml_ops` â€” Machine Learning Operations
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¢ Fase 4

GestiÃ³n del ciclo de vida de modelos ML: entrenamiento, versionado, despliegue.

---

### `iot_data` â€” Datos de IoT
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¢ Fase 4

Ingesta de telemetrÃ­a de sensores, biomÃ©tricos, GPS de flota.

---

### `integracion_b2b` â€” IntegraciÃ³n B2B
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

Intercambio estructurado de datos con socios comerciales, bancos, pasarelas.

---

### `gestion_api_externas` â€” Gobernanza de APIs Externas
**Estado:** ðŸ’¡ Nuevo | **Prioridad:** ðŸŸ¡ Fase 3

Trazabilidad, rate limiting y circuit breaker para llamadas a APIs externas.

---

### `gestion_analitica_avanzada`
**Estado:** ðŸ’¡ Nuevo | **Prioridad:** ðŸŸ¡ Fase 3

KPIs inteligentes, simulaciÃ³n de escenarios, alertas de desviaciÃ³n vs. presupuesto.

---

## GRUPO X â€” MÃ³dulos EspecÃ­ficos de Industria

### `gestion_propiedades` â€” GestiÃ³n de Propiedades
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

Inmuebles en renta, contratos de arrendamiento, mantenimiento, ingresos por alquiler.

---

### `servicios_proyectos` â€” Servicios y Proyectos
**Estado:** ðŸ”² | **Prioridad:** ðŸŸ¡ Fase 3

GestiÃ³n de proyectos, hitos, registro de horas, facturaciÃ³n por avance.

---

## MÃ“DULOS FUTUROS (Verticales de Industria)

| MÃ³dulo | DescripciÃ³n |
|---|---|
| `gestion_clinica` | Pacientes, historia clÃ­nica, citas, facturaciÃ³n mÃ©dica |
| `servicios_freelance` | CotizaciÃ³n, entrega, cobro para freelancers |
| `gestion_academica` | Cursos, alumnos, evaluaciÃ³n, certificaciÃ³n |
| `gestion_hotelera` | Habitaciones, reservas, housekeeping |
| `gestion_transporte_publico` | Rutas, boletos, conductores |

---

# PARTE V â€” Plan de Fases

## Principio de PriorizaciÃ³n

> **Un ERP que hace 5 cosas perfectas gana a uno que hace 50 cosas mal.**
> El MVP no es un producto incompleto â€” es la versiÃ³n mÃ¡s delgada del producto que puede cerrar un cliente de pago real.

---

## FASE 0 â€” FundaciÃ³n TÃ©cnica
**DuraciÃ³n estimada:** 2-3 semanas  
**Objetivo:** El sistema compila, es testeble, y estÃ¡ listo para recibir funcionalidad real.

### Tareas

#### Backend
- [ ] Migrar de SQLite a PostgreSQL en entorno de desarrollo local
- [ ] Configurar `docker-compose.yml` completo (Django + PostgreSQL + Redis + Celery)
- [ ] Instalar y configurar Celery + Redis para tareas asÃ­ncronas
- [ ] Crear base class `BaseModel` abstracta con `id_empresa`, `fecha_creacion`, `activo`
- [ ] Implementar filtro automÃ¡tico por `id_empresa` en `BaseModelViewSet` (sin repetir en cada viewset)
- [ ] Configurar Sentry para captura automÃ¡tica de errores en producciÃ³n
- [ ] Configurar logging a archivo rotativo (no solo consola)
- [ ] Setup de pytest + pytest-django para tests
- [ ] Escribir test de aislamiento de tenants (empresa A no ve datos de empresa B)
- [ ] Configurar `pre-commit` hooks (black, flake8, isort)

#### Frontend
- [ ] Instalar TanStack Query (React Query) y refactorizar todos los `useEffect` de fetch
- [ ] Crear `useApi<T>` hook estÃ¡ndar que use TanStack Query
- [ ] Implementar i18next con idioma espaÃ±ol por defecto y estructura para inglÃ©s futuro
- [ ] Crear sistema de notificaciones In-App (toasts + navbar badge)
- [ ] Configurar Vitest para tests de componentes
- [ ] Escribir tests para componentes crÃ­ticos: ModalPago, TablaProductos, ResumenTotales
- [ ] Dividir ModalPago.tsx en subcomponentes (< 200 lÃ­neas cada uno)
- [ ] Implementar Error Boundary global para capturar errores de React
- [ ] Configurar ESLint con reglas estrictas (no-any, exhaustive-deps)

#### DevOps
- [ ] Crear `docker-compose.prod.yml` con Nginx + Gunicorn
- [ ] Configurar GitHub Actions: lint â†’ test â†’ build en cada PR
- [ ] Crear script de setup del entorno de desarrollo (un solo comando)
- [ ] Documentar variables de entorno requeridas en `.env.example`

---

## FASE 1 â€” MVP Vendible
**DuraciÃ³n estimada:** 2-3 meses  
**Objetivo:** Un cliente real puede usar el sistema para su operaciÃ³n diaria de ventas, cobros y control de inventario bÃ¡sico.

**Criterio de Ã©xito:** Al menos 1 empresa de 5-50 empleados usando el sistema diariamente, pagando una suscripciÃ³n mensual.

### MÃ³dulos a completar en Fase 1

#### 1. `ventas` â€” Completar integraciones
- [ ] Al confirmar venta â†’ descuenta stock en `inventario.MovimientoInventario`
- [ ] Al confirmar venta â†’ genera saldo en `cuentas_por_cobrar` (si es a crÃ©dito)
- [ ] Al confirmar venta â†’ calcula IVA y lo registra en `fiscal`
- [ ] Correlativo automÃ¡tico de documentos por empresa+sucursal
- [ ] Lista de precios mÃºltiples (al menos en VES y USD)
- [ ] Estado del pedido en tiempo real (Pendiente â†’ Confirmado â†’ Entregado â†’ Cobrado)

#### 2. `inventario` â€” Stock funcional
- [ ] Movimientos de inventario (entrada manual, salida por venta, ajuste)
- [ ] Stock actual por sucursal/almacÃ©n
- [ ] Alertas de stock mÃ­nimo vÃ­a `notificaciones`
- [ ] Kardex de producto (historial de movimientos)
- [ ] RecepciÃ³n de compra â†’ entrada de inventario

#### 3. `fiscal` â€” MÃ­nimo venezolano
- [ ] ConfiguraciÃ³n fiscal por empresa (alÃ­cuota IVA, si es agente de retenciÃ³n)
- [ ] CÃ¡lculo automÃ¡tico de IVA en ventas
- [ ] **IGTF:** detecciÃ³n automÃ¡tica en pagos en divisas/crypto y cÃ¡lculo del 3%
- [ ] Factura Fiscal PDF con campos obligatorios venezolanos
- [ ] Comprobante de retenciÃ³n de IVA PDF
- [ ] Libro de Ventas en Excel (exportable)

#### 4. `reportes` â€” Documentos bÃ¡sicos
- [ ] Plantilla PDF configurable para Factura Fiscal
- [ ] Plantilla PDF para CotizaciÃ³n/Presupuesto
- [ ] Plantilla PDF para Nota de Entrega
- [ ] Logo + colores + datos de empresa configurables desde UI

#### 5. `notificaciones` â€” Canal bÃ¡sico
- [ ] Notificaciones In-App (navbar)
- [ ] Notificaciones por email (SMTP)
- [ ] Eventos: pedido creado, pago recibido, stock bajo, aprobaciÃ³n pendiente

#### 6. `compras` â€” Ciclo bÃ¡sico
- [ ] Solicitud de compra â†’ Orden de compra â†’ RecepciÃ³n
- [ ] OC en mÃºltiples monedas
- [ ] RecepciÃ³n parcial

#### 7. `crm` â€” Clientes completo
- [ ] BÃºsqueda por RIF con autocompletado
- [ ] Historial de compras por cliente
- [ ] LÃ­mite de crÃ©dito configurable con alerta/bloqueo

#### 8. `cuentas_por_cobrar` â€” BÃ¡sico
- [ ] Saldo por cliente generado desde ventas
- [ ] Registro de abonos y pagos
- [ ] AntigÃ¼edad de cartera (aging report) exportable
- [ ] Estado de cuenta por cliente PDF

#### 9. `saas_core` â€” GestiÃ³n interna mÃ­nima
- [ ] Modelo de planes de suscripciÃ³n
- [ ] Registro de clientes de Omni ERP
- [ ] ActivaciÃ³n/desactivaciÃ³n de mÃ³dulos por empresa
- [ ] ExpiraciÃ³n de suscripciÃ³n con perÃ­odo de gracia

---

## FASE 2 â€” RetenciÃ³n y Crecimiento
**DuraciÃ³n estimada:** 3-4 meses  
**Objetivo:** El sistema es suficientemente completo para retener clientes 12+ meses y para referidos activos.

### MÃ³dulos a completar en Fase 2

- **`rrhh` + `nomina`:** Empleados completos + cÃ¡lculo de nÃ³mina venezolana con todos los componentes
- **`control_asistencia`:** Marcajes, ausencias, horas extras
- **`portal_vendedores`:** PWA funcional offline para vendedores de campo
- **`portal_empleados`:** Recibo de sueldo, solicitud de permisos, datos personales
- **`delivery_general`:** AsignaciÃ³n y seguimiento de entregas
- **`contabilidad`:** Plan de cuentas + asientos automÃ¡ticos desde ventas/compras/nÃ³mina
- **`gastos`:** Registro y reembolso de gastos operativos
- **`tesoreria`:** ConciliaciÃ³n bancaria bÃ¡sica
- **`cuentas_por_pagar`:** Ciclo completo de pagos a proveedores
- **`gestion_documental`:** Adjuntar archivos a cualquier entidad
- **`gestion_aprobaciones`:** Flujos configurables para OC, gastos, permisos
- **`analitica_negocio`:** Dashboard ejecutivo con KPIs clave
- **`comunicacion_interna`:** Chat interno en tiempo real
- **`gestion_tareas_colaborativas`:** Kanban bÃ¡sico
- **`notificaciones` WhatsApp:** IntegraciÃ³n WhatsApp Business API
- **`migracion_datos`:** UI para importar datos iniciales desde Excel
- **`retail_pos`:** POS bÃ¡sico con operaciÃ³n offline

---

## FASE 3 â€” DiferenciaciÃ³n Competitiva
**DuraciÃ³n estimada:** 4-6 meses  
**Objetivo:** Omni ERP es la mejor opciÃ³n del mercado venezolano, con ventajas claras sobre Odoo y SAP B1.

### MÃ³dulos y funcionalidades a desarrollar

- **`manufactura` completa:** MRP, centros de trabajo, Ã³rdenes de producciÃ³n integradas
- **`control_calidad`:** Planes de inspecciÃ³n, no conformidades
- **`costos`:** Costeo estÃ¡ndar y real con anÃ¡lisis de variaciones
- **`servicio_cliente`:** Mesa de ayuda con SLA y base de conocimiento
- **`crm_ventas_marketing`:** Pipeline de ventas, campaÃ±as
- **`restaurante_pos`:** POS especializado para restaurantes
- **`portal_clientes`:** Autoservicio para clientes finales
- **`portal_proveedores`:** Autoservicio para proveedores
- **`compliance`:** GestiÃ³n de normativas venezolanas
- **`gestion_procesos_negocio`:** BPM sin cÃ³digo
- **`motor_reglas_negocio`:** Reglas configurables de negocio
- **`reportes`:** Constructor visual de reportes personalizados
- **`gestion_propiedades`:** Para empresas con inmuebles
- **`servicios_proyectos`:** FacturaciÃ³n por proyectos
- **`banca_electronica`:** ConciliaciÃ³n automÃ¡tica con bancos VE
- **`notificaciones` Telegram + Push:** Canales adicionales
- **`planificacion_financiera`:** Presupuestos con comparativo real
- **`activos_fijos`:** DepreciaciÃ³n y ciclo de vida

---

## FASE 4 â€” Liderazgo TÃ©cnico Avanzado
**DuraciÃ³n estimada:** 6-12 meses  
**Objetivo:** Omni ERP tiene capacidades que ningÃºn ERP de la regiÃ³n tiene.

- **`asistente_ia`:** Copiloto conversacional en lenguaje natural
- **`inteligencia_artificial_aplicada`:** Predicciones de demanda, detecciÃ³n de fraude, scoring crediticio
- **`ml_ops`:** Ciclo de vida de modelos ML
- **`iot_data`:** TelemetrÃ­a de dispositivos y sensores
- **`wms_avanzado`:** OptimizaciÃ³n de almacÃ©n con picking, putaway
- **`planificacion_recursos_capacidad`:** OptimizaciÃ³n global de recursos
- **`marketplace`:** Plataforma para mÃ³dulos y extensiones de terceros
- **`developer_portal`:** DocumentaciÃ³n, webhooks configurables, SDK

---

## FASE 5 â€” ExpansiÃ³n Global
**DuraciÃ³n estimada:** 12-24 meses desde Fase 4  
**Objetivo:** Omni ERP opera en mÃºltiples paÃ­ses con adaptaciÃ³n fiscal local.

- **i18n completo:** InglÃ©s + EspaÃ±ol (base), luego PortuguÃ©s, FrancÃ©s
- **MÃ³dulos fiscales por paÃ­s:** Colombia (DIAN + CUFE), MÃ©xico (SAT + CFDI), Ecuador (SRI), PerÃº (SUNAT)
- **Multi-divisa global:** Todas las monedas ISO 4217 + principales criptos
- **Compliance internacional:** GDPR (Europa), SOC 2 (EEUU), LGPD (Brasil)
- **Infraestructura multi-regiÃ³n:** AWS/GCP con CDN global
- **Arquitectura multi-tenant escalable:** MigraciÃ³n a schema-per-tenant para clientes enterprise

---

# PARTE VI â€” Especificaciones del Mercado Venezolano

## 6.1 Fiscalidad Venezolana â€” Referencia TÃ©cnica

### IVA (Impuesto al Valor Agregado)
| Concepto | Valor | Notas |
|---|---|---|
| AlÃ­cuota general | 16% | MayorÃ­a de bienes y servicios |
| AlÃ­cuota reducida | 8% | Bienes de primera necesidad |
| AlÃ­cuota cero | 0% | Exportaciones |
| Exento | Sin IVA | Medicamentos, alimentos bÃ¡sicos, etc. |

### IGTF (Impuesto a las Grandes Transacciones Financieras)
| Concepto | Valor | Notas |
|---|---|---|
| AlÃ­cuota | 3% | Aplicable desde 2022 |
| Aplica a | Pagos en divisas, criptos, oro | No aplica a pagos en bolÃ­vares |
| Responsable | El pagador | Debe discriminarse en factura |
| Base | Monto total de la operaciÃ³n en divisas | |

**ImplementaciÃ³n en cÃ³digo:**
```python
def calcular_igtf(monto_divisas: Decimal, empresa: Empresa) -> Decimal:
    config = empresa.configuracion_fiscal
    if not config.aplica_igtf:
        return Decimal('0')
    return (monto_divisas * config.alicuota_igtf / 100).quantize(Decimal('0.01'))
```

### Retenciones
| Tipo | Porcentaje | Aplica |
|---|---|---|
| Ret. IVA 75% | 75% del IVA | Agentes de retenciÃ³n a proveedores no agentes |
| Ret. IVA 100% | 100% del IVA | Agentes de retenciÃ³n a proveedores personas naturales |
| Ret. ISLR | Variable (tabla) | Por tipo de actividad econÃ³mica |

### Documentos Fiscales Obligatorios
- **Factura:** Con nÃºmero de control, nÃºmero de factura, datos del receptor (RIF)
- **Nota de DÃ©bito / CrÃ©dito:** Vinculadas a factura original
- **Comprobante de RetenciÃ³n:** NÃºmero correlativo, perÃ­odo, monto retenido
- **Libro de Compras:** Mensual, formato SENIAT
- **Libro de Ventas:** Mensual, formato SENIAT

## 6.2 MÃ©todos de Pago Venezolanos

| MÃ©todo | Moneda | Notas de implementaciÃ³n |
|---|---|---|
| Efectivo VES | VES | EstÃ¡ndar |
| Efectivo USD | USD | Aplica IGTF si empresa es agente |
| Pago MÃ³vil | VES | Banco a banco vÃ­a RIF/telÃ©fono. Validar formato |
| Transferencia VES | VES | Interbancaria o mismo banco |
| Transferencia USD | USD | Aplica IGTF |
| Zelle | USD | Muy comÃºn, sin API â€” solo registro manual |
| Tarjeta dÃ©bito | VES | Via datafono, puede haber IGTF si es tarjeta en USD |
| Tarjeta crÃ©dito | VES/USD | Verificar moneda de cobro |
| USDT (TRC-20) | USDT | Cripto mÃ¡s usada en VE, aplica IGTF |
| Bitcoin | BTC | Menor frecuencia |
| Punto de venta internacional | USD | Aplica IGTF |
| Divisas en efectivo (EUR, COP) | EUR/COP | Aplica IGTF |
| Cheque | VES | En desuso pero existe |

## 6.3 Multimoneda Venezolana

```
VES (BolÃ­var) â†’ Moneda base legal
USD           â†’ Moneda de referencia operativa
USDT          â†’ Cripto de reserva de valor mÃ¡s usada

Tasas de cambio:
  BCV_OFICIAL   â†’ API del Banco Central de Venezuela (automÃ¡tica)
  PARALELO      â†’ Configurada manualmente o via monitor USD (referencial)
  USUARIO_LIBRE â†’ Tasa especÃ­fica negociada para una transacciÃ³n
```

**Regla de negocio crÃ­tica:** El sistema debe mostrar precios en la moneda que el cliente desee (VES, USD, o ambas), pero todos los totales deben convertirse a la moneda base de la empresa para contabilidad y reportes.

## 6.4 NÃ³mina Venezolana â€” ParÃ¡metros Legales

```python
LOTTT_PARAMETROS = {
    # Salario mÃ­nimo (actualizar mensualmente via ParametroSistema)
    'salario_minimo_mensual': Decimal('130.00'),  # VES - verificar valor actual

    # Cestaticket
    'cestaticket_minimo_mensual': Decimal('0.00'),  # configurable
    
    # Utilidades
    'dias_utilidades_minimo': 15,
    'dias_utilidades_maximo': 120,
    
    # Vacaciones
    'dias_vacaciones_primer_aÃ±o': 15,
    'dias_adicionales_por_aÃ±o': 1,  # +1 dÃ­a por cada aÃ±o adicional
    
    # Bono vacacional
    'dias_bono_vacacional_minimo': 7,
    'dias_bono_adicional_por_aÃ±o': 1,
    
    # AntigÃ¼edad
    'dias_antigÃ¼edad_por_aÃ±o': 5,
    'dias_antigÃ¼edad_adicional_despues_3_aÃ±os': 2,
    
    # Aportes del empleador
    'sso_patronal': Decimal('9.00'),      # %
    'faov_patronal': Decimal('2.00'),      # %
    'inces_patronal': Decimal('2.00'),     # %
    'rpe_patronal': Decimal('2.00'),       # %
    
    # Aportes del empleado
    'sso_empleado': Decimal('4.00'),      # %
    'faov_empleado': Decimal('1.00'),     # %
    'rpe_empleado': Decimal('0.50'),      # %
}
```

---

# PARTE VII â€” Ruta de ExpansiÃ³n Global

## 7.1 InternacionalizaciÃ³n (i18n) â€” Arquitectura

### Frontend (React + i18next)
```typescript
// Estructura de archivos de traducciÃ³n
locales/
  es/           // EspaÃ±ol (base)
    common.json
    ventas.json
    finanzas.json
    ...
  en/           // InglÃ©s (segunda prioridad)
  pt/           // PortuguÃ©s (tercera)

// Uso en componentes
const { t } = useTranslation('ventas');
return <Typography>{t('pedido.nuevo')}</Typography>;
```

### Backend (Django)
```python
# Campos con traducciÃ³n (usar django-modeltranslation)
from modeltranslation.translator import register, TranslationOptions

@register(TipoDocumento)
class TipoDocumentoTranslationOptions(TranslationOptions):
    fields = ('nombre', 'descripcion')
# Genera: nombre_es, nombre_en, nombre_pt en la tabla
```

**DecisiÃ³n crÃ­tica:** Implementar i18n en el frontend desde Fase 1 (es solo agregar llaves de traducciÃ³n). En el backend, solo cuando se planifique expansiÃ³n internacional activa â€” los modelos de catÃ¡logo requieren migraciÃ³n.

## 7.2 Adaptaciones Fiscales por PaÃ­s

| PaÃ­s | Sistema fiscal | API oficial | Prioridad |
|---|---|---|---|
| Venezuela | SENIAT (IVA + ISLR + IGTF) | Sin API pÃºblica oficial | âœ… Actual |
| Colombia | DIAN (IVA + Renta + Factura electrÃ³nica) | DIAN API (habilitadores) | ðŸŸ¡ Fase 5 |
| MÃ©xico | SAT (IVA + ISR + CFDI 4.0) | SAT PAC | ðŸŸ¡ Fase 5 |
| Ecuador | SRI (IVA + Renta + Factura electrÃ³nica) | SRI API | ðŸŸ¡ Fase 5 |
| PerÃº | SUNAT (IGV + Renta + UBL 2.1) | SUNAT API | ðŸŸ¢ Futuro |
| Argentina | AFIP (IVA + Ganancias) | AFIP WebServices | ðŸŸ¢ Futuro |

## 7.3 Compliance Internacional

| RegulaciÃ³n | Aplica en | Requerimiento tÃ©cnico |
|---|---|---|
| GDPR | UniÃ³n Europea | Right to erasure, portabilidad de datos, consentimiento explÃ­cito |
| LGPD | Brasil | Similar a GDPR |
| CCPA | California, EEUU | Opt-out de venta de datos |
| SOC 2 Type II | Empresas EEUU | AuditorÃ­a de seguridad y disponibilidad |
| PCI DSS | Cualquiera con tarjetas | No almacenar datos de tarjeta (usar tokenizaciÃ³n) |

---

# PARTE VIII â€” EstÃ¡ndares TÃ©cnicos

## 8.1 Backend â€” Convenciones de CÃ³digo

### Estructura de un ViewSet estÃ¡ndar
```python
from apps.core.viewsets import BaseModelViewSet
from .models import Pedido
from .serializers import PedidoSerializer
from .filters import PedidoFilter

class PedidoViewSet(BaseModelViewSet):
    serializer_class = PedidoSerializer
    filterset_class = PedidoFilter
    search_fields = ['numero_pedido', 'id_cliente__razon_social']
    ordering_fields = ['fecha_pedido', 'total']
    ordering = ['-fecha_pedido']

    # NO es necesario definir get_queryset si BaseModelViewSet
    # ya filtra por empresa del usuario autenticado
```

### BaseModelViewSet (implementar en Fase 0)
```python
class BaseModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        empresa = self.request.user.empresa
        if empresa is None:
            return self.queryset.none()
        return super().get_queryset().filter(id_empresa=empresa)

    def perform_create(self, serializer):
        serializer.save(
            id_empresa=self.request.user.empresa,
            id_usuario_creacion=self.request.user
        )
```

### Serializers
```python
class PedidoSerializer(serializers.ModelSerializer):
    # Campos de solo lectura para representaciÃ³n
    cliente_nombre = serializers.CharField(
        source='id_cliente.razon_social', read_only=True
    )

    class Meta:
        model = Pedido
        fields = '__all__'
        read_only_fields = ['id_pedido', 'id_empresa', 'fecha_creacion',
                            'numero_pedido', 'fecha_modificacion']
```

### Logging estÃ¡ndar
```python
import logging
logger = logging.getLogger(__name__)  # Siempre al top del archivo

# En funciones:
logger.info("Pedido %s creado por usuario %s", pedido.numero_pedido, usuario.username)
logger.warning("Stock insuficiente para producto %s: disponible %s, requerido %s",
               producto.codigo, stock_actual, cantidad_requerida)
logger.error("Error al procesar pago %s: %s", pago_id, str(e))
logger.exception("Error crÃ­tico en cÃ¡lculo de nÃ³mina")  # Incluye traceback
```

### Tests
```python
# Cada mÃ³dulo debe tener:
# tests/test_models.py      â†’ validaciones, constraints, mÃ©todos del modelo
# tests/test_views.py       â†’ endpoints, permisos, respuestas
# tests/test_serializers.py â†’ validaciÃ³n de datos de entrada
# tests/test_isolation.py   â†’ empresa A no ve datos de empresa B

class TestPedidoViewSet(TestCase):
    def setUp(self):
        self.empresa_a = EmpresaFactory.create()
        self.empresa_b = EmpresaFactory.create()
        self.user_a = UsuarioFactory.create(empresa=self.empresa_a)
        self.pedido_a = PedidoFactory.create(id_empresa=self.empresa_a)
        self.pedido_b = PedidoFactory.create(id_empresa=self.empresa_b)

    def test_usuario_no_ve_datos_de_otra_empresa(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get('/api/v1/ventas/pedidos/')
        ids = [p['id_pedido'] for p in response.data['results']]
        self.assertIn(str(self.pedido_a.id_pedido), ids)
        self.assertNotIn(str(self.pedido_b.id_pedido), ids)
```

## 8.2 Frontend â€” Convenciones de CÃ³digo

### Estructura de directorios
```
frontend/src/
  pages/          â†’ Una carpeta por mÃ³dulo de negocio
    Ventas/
      Pedidos/
        PedidosListPage.tsx
        PedidoFormPage.tsx
        PedidoDetailPage.tsx
  components/     â†’ Componentes compartidos entre mÃ³dulos
    Pedidos/      â†’ Componentes especÃ­ficos de un dominio
  hooks/          â†’ Custom hooks
    usePedidoForm.ts
    useDocumentoVentaBase.ts   â† unificaciÃ³n de hooks similares
  services/       â†’ ComunicaciÃ³n con API
    api.ts         â† funciÃ³n base, ÃšNICA fuente de fetch
    ventasService.ts
    finanzasService.ts
  routes/         â†’ DefiniciÃ³n de rutas por dominio
  contexts/       â†’ Estado global
  types/          â†’ Interfaces TypeScript compartidas
```

### Reglas de hooks y servicios
```typescript
// âœ… Correcto â€” usar TanStack Query
const { data: pedidos, isLoading, error } = useQuery({
  queryKey: ['pedidos', filters],
  queryFn: () => pedidoService.getAll(filters),
});

// âŒ Incorrecto â€” useEffect manual para fetching
useEffect(() => {
  fetch('/api/ventas/pedidos/').then(r => r.json()).then(setPedidos);
}, []);

// âœ… Correcto â€” toda llamada API pasa por api.ts
import { get, post } from '../services/api';
export const pedidoService = {
  getAll: (filters?) => get('/ventas/pedidos/', filters),
  create: (data) => post('/ventas/pedidos/', data),
};

// âŒ Incorrecto â€” fetch() directo en componentes o servicios
fetch('http://localhost:8000/api/ventas/pedidos/', { ... })
```

### Tipado estricto
```typescript
// âœ… Tipos explÃ­citos para respuestas de API
interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// âŒ Prohibido â€” any
const [data, setData] = useState<any>(null);

// âœ… Correcto
const [data, setData] = useState<Pedido | null>(null);
```

### Componentes de pÃ¡gina estÃ¡ndar
```tsx
// Estructura mÃ­nima de una pÃ¡gina lista
const PedidosListPage: React.FC = () => {
  const { data, isLoading, error } = useQuery(...);
  const navigate = useNavigate();

  if (isLoading) return <LinearProgress />;
  if (error) return <Alert severity="error">{error.message}</Alert>;

  return (
    <PageLayout>
      <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between' }}>
        <Typography variant="h4">Pedidos</Typography>
        <Button variant="contained" onClick={() => navigate('/ventas/pedidos/nuevo')}>
          Nuevo Pedido
        </Button>
      </Box>
      {/* tabla */}
    </PageLayout>
  );
};
```

## 8.3 Base de Datos

### Campos obligatorios en todo modelo de negocio
```python
id_[nombre]       = UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
id_empresa        = ForeignKey('core.Empresa', on_delete=CASCADE)
fecha_creacion    = DateTimeField(auto_now_add=True)
fecha_modificacion = DateTimeField(auto_now=True)
activo            = BooleanField(default=True)  # soft delete
```

### Reglas de unique constraints
```python
# âœ… Correcto â€” por empresa
unique_together = ['id_empresa', 'codigo_referencia']

# âŒ Incorrecto â€” global en sistema multi-tenant
codigo_referencia = CharField(unique=True)  # rompe multi-tenancy
```

### Campos monetarios
```python
# Siempre Decimal, nunca Float
precio = DecimalField(max_digits=18, decimal_places=4)
# max_digits=18 para montos grandes en VES (inflaciÃ³n)
# decimal_places=4 para tasas de cambio y conversiones precisas
# decimal_places=2 para montos finales al cliente
```

### Ãndices recomendados
```python
class Meta:
    indexes = [
        models.Index(fields=['id_empresa', 'fecha_creacion']),  # listados por empresa
        models.Index(fields=['id_empresa', 'estado']),           # filtros por estado
        models.Index(fields=['id_empresa', 'id_cliente']),       # ventas por cliente
    ]
```

## 8.4 Proceso de Desarrollo

```
main (producciÃ³n)
  â””â”€â”€ develop (integraciÃ³n)
        â””â”€â”€ feature/nombre-descriptivo (desarrollo)
        â””â”€â”€ fix/descripcion-del-bug (correcciÃ³n)
        â””â”€â”€ hotfix/descripcion (correcciÃ³n urgente a main)
```

**Flujo:**
1. Crear rama desde `develop`: `git checkout -b feature/modulo-fiscal-igtf`
2. Desarrollar con commits descriptivos en espaÃ±ol: `feat: implementar cÃ¡lculo IGTF en pagos en divisas`
3. Pull Request a `develop` con descripciÃ³n de cambios y checklist
4. Code review obligatorio (mÃ­nimo 1 aprobador)
5. CI verde (lint + tests) antes de merge
6. Merge a `develop` â†’ deploy automÃ¡tico a staging
7. Release a `main` â†’ deploy a producciÃ³n

**Commits:** Usar Conventional Commits:
- `feat:` nueva funcionalidad
- `fix:` correcciÃ³n de bug
- `refactor:` refactorizaciÃ³n sin cambio de comportamiento
- `test:` aÃ±adir o corregir tests
- `docs:` documentaciÃ³n
- `chore:` mantenimiento (deps, CI, etc.)

---

# PARTE IX â€” GuÃ­a de IncorporaciÃ³n al Equipo

## 9.1 Antes de tu primer dÃ­a

Lee en este orden:
1. Este documento completo (Omni ERP_MASTER_PLAN.md)
2. `README.md` del proyecto (setup bÃ¡sico)
3. Explora el cÃ³digo en este orden: `apps/core/` â†’ `apps/finanzas/` â†’ `apps/ventas/` â†’ `frontend/src/pages/Ventas/`

## 9.2 Setup del Entorno de Desarrollo

### Requisitos
- Python 3.11+
- Node.js 20+
- Docker Desktop
- Git

### InstalaciÃ³n (un solo flujo)
```bash
# 1. Clonar repositorio
git clone https://github.com/[org]/Omni ERP.git
cd Omni ERP

# 2. Variables de entorno
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
# Editar .env con tus valores locales

# 3. Backend
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# 4. Frontend (en otra terminal)
cd frontend
npm install
npm run dev

# 5. (Opcional) Con Docker
docker-compose up --build
```

### URLs de desarrollo
- Frontend: http://localhost:5173
- API: http://localhost:8000/api/
- Admin Django: http://localhost:8000/admin/
- DocumentaciÃ³n API (Swagger): http://localhost:8000/api/docs/

## 9.3 Estructura del Repositorio

```
Omni ERP/
  backend/
    apps/                   â†’ Una carpeta por mÃ³dulo de Django
      core/
        models.py           â†’ Modelos de datos
        views.py            â†’ Views y ViewSets
        serializers.py      â†’ Serializers DRF
        urls.py             â†’ URLs del mÃ³dulo
        admin.py            â†’ ConfiguraciÃ³n del admin
        filters.py          â†’ Filtros para listados
        tests/              â†’ Tests del mÃ³dulo
      finanzas/
      ventas/
      ...
    config/
      settings_base.py      â†’ Settings base (dev y prod)
      settings.py           â†’ Settings locales (en .gitignore)
      settings_prod.py      â†’ Settings de producciÃ³n
      urls.py               â†’ URLs raÃ­z
    manage.py
    requirements.txt
    requirements_prod.txt
  frontend/
    src/
      components/           â†’ Componentes React reutilizables
      contexts/             â†’ Estado global (AuthContext, SidebarContext)
      hooks/                â†’ Custom hooks
      pages/                â†’ PÃ¡ginas por mÃ³dulo
      routes/               â†’ DefiniciÃ³n de rutas
      services/             â†’ Servicios de API
      types/                â†’ Tipos TypeScript
    .env.example
    package.json
    vite.config.ts
  docker-compose.yml
  .gitignore
  Omni ERP_MASTER_PLAN.md  â† EstÃ¡s aquÃ­
```

## 9.4 CÃ³mo Contribuir â€” Checklist para PRs

Antes de abrir un Pull Request, verifica:

**Backend:**
- [ ] Modelos tienen `id_empresa` y usan UUID PK
- [ ] Unique constraints son `unique_together` con `id_empresa`, no `unique=True` global
- [ ] ViewSet hereda de `BaseModelViewSet`
- [ ] No hay `print()` ni `traceback.print_exc()` en el cÃ³digo
- [ ] Logging usa `logger.info/warning/error/exception()` en niveles apropiados
- [ ] Hay al menos un test de aislamiento de empresa
- [ ] MigraciÃ³n creada y verificada si hay cambios de modelos
- [ ] No hay secrets en el cÃ³digo (solo en variables de entorno)

**Frontend:**
- [ ] No hay `console.log()` en el cÃ³digo (solo `console.error()` en catch)
- [ ] No hay tipos `any` (usar `unknown` o interfaces especÃ­ficas)
- [ ] Toda llamada a API va a travÃ©s de `services/api.ts`
- [ ] No hay URLs hardcodeadas (usar `import.meta.env.VITE_API_URL`)
- [ ] Componentes usan MUI directamente (no wrappers propios)
- [ ] Errores del usuario se muestran con `Alert` de MUI, no `alert()`
- [ ] Acciones destructivas piden confirmaciÃ³n

**General:**
- [ ] El cÃ³digo compila sin errores (`tsc --noEmit` + `python manage.py check`)
- [ ] Tests pasan (`pytest` + `vitest`)
- [ ] El PR describe quÃ© cambia y por quÃ©

## 9.5 Ãreas de Trabajo Disponibles

### Para desarrolladores backend
- MÃ³dulo `fiscal` â€” mÃ¡xima prioridad
- Movimientos de inventario
- CÃ¡lculo de nÃ³mina venezolana
- Motor de notificaciones (Django + Celery)
- IntegraciÃ³n BCV automÃ¡tica robusta
- Tests de integraciÃ³n

### Para desarrolladores frontend
- RefactorizaciÃ³n con TanStack Query
- UI del mÃ³dulo fiscal
- PWA y capacidad offline (Service Workers)
- Dashboard de analÃ­tica
- Constructor de reportes PDF
- InternacionalizaciÃ³n (i18next)
- Tests con Vitest

### Para diseÃ±adores
- Sistema de diseÃ±o unificado sobre MUI
- Plantillas de documentos PDF (Factura, CotizaciÃ³n, NÃ³mina)
- UX del POS (tactil, accesible, sin conexiÃ³n)
- UX del portal de vendedores mÃ³vil
- IconografÃ­a y brand del producto

### Para DevOps / SRE
- Pipeline CI/CD completo
- ConfiguraciÃ³n de staging automÃ¡tico por PR
- Monitoreo con Prometheus + Grafana
- Backup automÃ¡tico de PostgreSQL
- Certificados SSL automÃ¡ticos (Let's Encrypt)
- Infraestructura como cÃ³digo (Terraform o Pulumi)

---

# ApÃ©ndice A â€” Decisiones TÃ©cnicas Documentadas

| # | DecisiÃ³n | Alternativas consideradas | RazÃ³n |
|---|---|---|---|
| 1 | UUID como PK en todos los modelos | Auto-increment int | Seguridad (no enumerable), distribuciÃ³n, multi-tenant |
| 2 | Row-Level Tenancy (shared DB) | Schema por tenant, DB por tenant | Simplicidad inicial, migraciÃ³n gradual posible |
| 3 | Django REST Framework | FastAPI, Flask | Ecosistema maduro, admin gratuito, autenticaciÃ³n robusta |
| 4 | React + TypeScript + MUI | Vue, Angular, Tailwind | Ecosistema, tipos, componentes enterprise listos |
| 5 | JWT con refresh tokens | Sesiones de Django, OAuth | API-first, stateless, compatible con mobile futuro |
| 6 | Soft delete (`activo=False`) | Hard delete | AuditorÃ­a, recuperaciÃ³n, integridad referencial |
| 7 | `django-filter` para filtros | Filtros manuales | EstÃ¡ndar, integrado con DRF, UI de Swagger automÃ¡tica |
| 8 | WeasyPrint para PDF | ReportLab, wkhtmltopdf | HTML/CSS â†’ PDF, mÃ¡s fÃ¡cil de templating |
| 9 | Celery + Redis para tareas async | Django-Q, APScheduler | EstÃ¡ndar de la industria, escalable |
| 10 | TanStack Query para server state | Redux, Zustand, SWR | CachÃ©, loading states, refetch automÃ¡tico sin boilerplate |
| 11 | WhatsApp Business API (Meta Cloud) | Twilio, 360dialog | Oficial, sin intermediarios, menor costo |
| 12 | i18next para internacionalizaciÃ³n | react-intl, FormatJS | MÃ¡s popular, documentaciÃ³n amplia, lazy loading |

---

# ApÃ©ndice B â€” KPIs del Producto

| MÃ©trica | Objetivo Fase 1 | Objetivo Fase 3 | Objetivo Largo plazo |
|---|---|---|---|
| Clientes activos | 1-5 | 50-200 | 2000+ |
| MÃ³dulos en producciÃ³n | 10 | 30 | 60+ |
| Uptime | 95% | 99% | 99.9% |
| Tiempo de respuesta API (p95) | < 2s | < 500ms | < 200ms |
| Cobertura de tests | 20% | 60% | 80% |
| NPS clientes | N/A | > 40 | > 60 |
| Tiempo de onboarding (dÃ­as) | 30 | 14 | 7 |

---

# ApÃ©ndice C â€” MÃ³dulos No Incluidos y Por QuÃ©

| MÃ³dulo considerado | DecisiÃ³n | RazÃ³n |
|---|---|---|
| MÃ³dulo propio de email marketing | Excluido | Usar integraciones (Mailchimp, SendGrid) vÃ­a `integracion_b2b` |
| MÃ³dulo de videoconferencia | Excluido | Integrar Google Meet/Zoom via `comunicacion_interna` |
| MÃ³dulo de firma electrÃ³nica | IntegraciÃ³n | DocuSign API o equivalente, no construir desde cero |
| E-commerce propio | Fuera de alcance | `portal_clientes` cubre el caso B2B; B2C es otro producto |
| App mÃ³vil nativa (iOS/Android) | PWA primero | PWA cubre 90% de los casos; app nativa si la demanda lo justifica |

---

*Documento generado y mantenido como parte del proyecto Omni ERP.*  
*Ãšltima revisiÃ³n tÃ©cnica: AuditorÃ­a de cÃ³digo Abril 2026.*  
*PrÃ³xima revisiÃ³n programada: Al completar Fase 1.*

