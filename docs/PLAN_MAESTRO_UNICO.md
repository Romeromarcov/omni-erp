# Omni ERP — Plan Maestro Único

**Versión:** 1.0 — Documento consolidado y única fuente de verdad
**Fecha de consolidación:** 2026-05-28
**Autor del proyecto:** Marco · Caracas, Venezuela
**Mantenido por:** founder + agentes de IA co-desarrolladores

---

## CÓMO USAR ESTE DOCUMENTO

> Este es el **único documento que necesitas leer para entender Omni ERP y poder incorporarte en cualquier etapa.**
> Cualquier persona —desarrollador, diseñador, inversor, socio o agente de IA— empieza aquí.

Este plan **consolida y reemplaza como fuente de verdad operativa** a todos los documentos de planificación previos, que quedan como material histórico (ver [§10 Mapa de documentos](#10--mapa-de-documentos-vigencia)). En adelante, conforme a la regla **R-PROC-1 (una sola fuente de verdad por dominio)**:

- Lo que se construye **desde ahora** se planifica y se mide contra este documento.
- El registro cronológico de trabajo sigue en `backend/PROJECT_LOG.md` (inmutable, append-only).
- Las decisiones arquitectónicas siguen en `docs/decisions/ADR-*.md`.
- Este documento se actualiza al cerrar cada sub-fase.

### Índice

1. [Qué es Omni ERP — Visión y negocio](#1--qué-es-omni-erp--visión-y-negocio)
2. [Reglas inviolables del proyecto](#2--reglas-inviolables-del-proyecto)
3. [Arquitectura técnica](#3--arquitectura-técnica)
4. [Estado actual real del proyecto](#4--estado-actual-real-del-proyecto)
5. [Roadmap unificado — desde hoy hasta la culminación](#5--roadmap-unificado)
6. [Especificaciones del mercado venezolano](#6--especificaciones-del-mercado-venezolano)
7. [Estándares de código y proceso de desarrollo](#7--estándares-de-código-y-proceso)
8. [Protocolo de trabajo por sesión (founder + IA)](#8--protocolo-de-trabajo-por-sesión)
9. [Guía de incorporación al equipo](#9--guía-de-incorporación)
10. [Mapa de documentos (vigencia)](#10--mapa-de-documentos-vigencia)
11. [Glosario](#11--glosario)

---

# 1 — Qué es Omni ERP — Visión y negocio

## 1.1 En una frase

Omni ERP es un sistema de gestión empresarial **modular, multi-tenant y AI-nativo**, construido desde Venezuela para operar en entornos de alta complejidad monetaria (multimoneda real, pagos mixtos, fiscalidad cambiante) y, por diseño, listo para cualquier otro mercado de LATAM y el mundo hispanohablante.

No es un clon de SAP ni de Odoo. Su diferenciador es ser **AI-nativo**: cada capacidad de negocio existe primero como una API invocable (REST + MCP), de modo que agentes de IA pueden operar el sistema, sugerir acciones y, con autonomía graduada, ejecutarlas con supervisión humana.

## 1.2 Filosofía central

- **Modular sin fricción:** cada empresa activa solo los módulos que necesita.
- **Sin rigidez contable impuesta:** una bodega informal puede vender, cobrar y controlar stock sin plan de cuentas; una empresa formal tiene contabilidad automática completa.
- **Venezuela-first, world-ready:** resolver lo más difícil (IVA + IGTF + retenciones + multimoneda + nómina LOTTT) hace que funcione en cualquier contexto más simple. **Pero "Venezuela-first" no significa "Venezuela-hardcoded":** todo lo específico de Venezuela vive en una **localización activable/desactivable**, no incrustado en el núcleo (ver [§3.7](#37--arquitectura-de-localización-l10n-de-dos-capas)). El sistema debe poder operar de forma genérica para una empresa no venezolana sin arrastrar la tropicalización venezolana.
- **Núcleo agnóstico + localizaciones enchufables:** el core no conoce ningún país. Las reglas, documentos y dinámicas de cada país son paquetes de localización que el core descubre y activa por empresa.
- **AI-nativo, no "AI-powered":** la IA no es un chatbot pegado encima; es la forma de operar el sistema (R-PROD-1).
- **La complejidad se esconde, no se elimina** (R-PROD-3).

## 1.3 Modelo de ejecución: founder solo + IA

El proyecto lo desarrolla **un founder trabajando 15–25 h/semana con agentes de IA como co-desarrolladores**. Esto define el ritmo (bloques de meses, no sprints de equipo) y la disciplina (cada sesión termina con algo que corre; code review humano obligatorio aunque el código lo escriba la IA — R-PROC-3).

## 1.4 Los dos negocios piloto (el MVP se define por ellos)

El MVP no se diseña en abstracto: se construye para **dos negocios familiares reales** con acceso directo y tolerancia al error:

| | **Negocio A — Fábrica de muebles artesanales** | **Negocio B — Distribuidora de tapicería** |
|---|---|---|
| Tipo | Manufactura discreta bajo pedido | Comercio mayorista/minorista |
| Volumen | Bajo, alta complejidad por transacción | Alto, baja complejidad por transacción |
| Inventario | Materias primas + WIP + terminados | Solo terminados |
| Cliente | B2C / B2B mediano | Mix B2B y B2C |
| Pago dominante | Adelanto 50% + saldo | Crédito mayoristas, contado detal |

**Por qué esta combinación es afortunada:** son complementarios (uno produce, otro distribuye), verticalmente conectados (la fábrica compra tapicería; la distribuidora vende a fábricas), y combinan los dos extremos de complejidad. Si el sistema sirve a ambos, sirve al 80% de las pymes venezolanas. **Lo común entre ambos = el núcleo del MVP. Lo específico de cada uno entra después.**

> `apps/cxc` (Cobranza Inteligente) nació de un tercer sistema real previo (GestionCxC) que se está absorbiendo dentro de Omni.

## 1.5 Propuesta de valor por segmento

| Segmento | Problema que resuelve | Diferenciador |
|---|---|---|
| PYME venezolana | Ventas USD+VES+crypto, IVA, IGTF, retenciones | Nativo multimoneda y fiscal VE |
| Empresa mediana | Nómina venezolana (LOTTT), RRHH, CxC/CxP | Fiscalidad VE de fábrica |
| Retail / restaurante | POS multimoneda, divisas en caja | Sin configuración extra |
| Vendedores de campo | Portal offline | Funciona sin internet |
| Manufactura | Producción + costos + calidad integrados | Módulos que sí se hablan entre sí |

## 1.6 Mercado objetivo

- **Bloque 1 (MVP→piloto):** los dos negocios familiares.
- **Bloque 2 (producto):** 5–10 PYMEs venezolanas externas (5–100 empleados).
- **Bloque 3+ (expansión):** empresas medianas VE, luego Colombia/Ecuador/Perú, y finalmente mercado global hispanohablante como competidor de Odoo Community.

---

# 2 — Reglas inviolables del proyecto

> Estas son reglas **operativas**. La violación de cualquiera **bloquea la entrega (no hay merge).** Son la defensa contra la deriva de visión y la "muerte por 60 módulos a medias".

## 2.1 Reglas de código (R-CODE)

| # | Regla | Resumen |
|---|---|---|
| **R-CODE-1** | Multi-tenant siempre | Todo modelo de negocio tiene `id_empresa`/`empresa` (FK a `core.Empresa`). Todo ViewSet filtra por la empresa del usuario en `get_queryset()`. **Cada PR incluye un test de aislamiento.** Sin los tres, no hay merge. |
| **R-CODE-2** | Sin SQLite, nunca | PostgreSQL en dev, staging y prod. Las diferencias de constraints parciales y transacciones ya costaron bugs. Excepción única: SQLite como *local storage* en cliente móvil nativo. |
| **R-CODE-3** | Sin `any` (TS) ni `print()` (Python prod) | TypeScript estricto. Python usa `logger`, nunca `print`/`traceback.print_exc()`. Chequeado en CI. |
| **R-CODE-4** | Decimal para dinero, siempre | Nunca `float`. `DecimalField(max_digits=18, decimal_places=4)` general; `2` para totales al cliente; `8` para crypto y tasas. |
| **R-CODE-5** | UUIDv7, no UUIDv4 | PK ordenable temporalmente. Implementación propia en `apps/core/uuid.py` (`uuid7`). |
| **R-CODE-6** | Soft delete, no hard delete | `activo=False` / `estado='ANULADO'`. Excepción: borrado obligado por ley (GDPR/LGPD) con proceso documentado y auditado. |
| **R-CODE-7** | API-first | Toda lógica existe primero como capacidad invocable (**REST + MCP**) antes de tener UI. UI sobre lógica sin API → PR rechazado. |
| **R-CODE-8** | Sin secretos en código ni en logs | Variables de entorno / vault. Logs jamás contienen tokens, contraseñas, datos de tarjeta, claves ni datos médicos. |
| **R-CODE-9** | Tests de integración para flujos críticos antes de merge | Flujo crítico = crear venta → factura → descontar stock → asiento contable → saldo CxC. El e2e debe seguir verde. |
| **R-CODE-10** | Prohibido `null=True, blank=True` en campos lógicamente obligatorios | Si un campo debe tener valor, es obligatorio; la migración resuelve los datos heredados. |
| **R-CODE-11** | Todo movimiento contable genera su asiento automáticamente | En la misma `@transaction.atomic`. Asiento en `BORRADOR`, auto-aprobado si `empresa.contabilidad_auto_aprobar=True`. Si el asiento falla, la transacción principal falla. |

## 2.2 Reglas de proceso (R-PROC)

| # | Regla | Resumen |
|---|---|---|
| **R-PROC-1** | Una sola fuente de verdad por dominio | Este documento es la fuente de verdad de lo que se construye desde ahora. No se duplica documentación; se enlaza. |
| **R-PROC-2** | PRs pequeños, focales | Un PR hace una cosa. >800 líneas (sin tests/migraciones/locks) → se divide. Excepción: refactors mecánicos marcados como tales. |
| **R-PROC-3** | Code review humano obligatorio | Aunque el código lo escriba un agente. **Auto-merge desde PR de agente está prohibido.** |
| **R-PROC-4** | CI verde es no-negociable | Tests + lint + type-check + build. Flaky = bug que se arregla, no se ignora. |
| **R-PROC-5** | Migraciones reversibles | Toda migración Django se prueba en reverse, o se documenta explícitamente por qué no lo es. |
| **R-PROC-6** | Los compromisos técnicos se vencen | Toda excepción a una regla es un "Compromiso técnico fechado" con `vence_en` y `dueño`. Se rastrean en `docs/ctf/`. |
| **R-PROC-7** | La quincena impar es de pago de deuda | ~30% del tiempo va a deuda técnica, refactor, tests y documentación. No se pospone. |
| **R-PROC-8** | Un cliente real desde el día 90 | Un design partner real usando el sistema en producción para algo, como defensa contra la deriva de visión. |

## 2.3 Reglas de producto (R-PROD)

| # | Regla |
|---|---|
| **R-PROD-1** | Nada se llama "AI-powered" si no es AI-nativo. |
| **R-PROD-2** | Personalización del usuario (conversacional) antes que personalización por consultoría técnica. |
| **R-PROD-3** | La complejidad se esconde, no se elimina (fiscalidad, crypto, etc. invisibles para el usuario). |
| **R-PROD-4** | Reversibilidad por defecto: el usuario deshace cualquier acción (suya o de un agente) en un plazo configurable (default 30 días). Co-requisito del agentic. |
| **R-PROD-5** | Transparencia de la IA: toda acción de un agente queda registrada (prompt, herramientas, datos, decisión, humano que aprobó) y es explicable en lenguaje natural. |

## 2.4 Árbol de decisión cuando hay dudas

1. ¿Viola una regla inviolable (§2)? → No se hace.
2. ¿Sirve a alguno de los dos pilotos en su operación real? → Si no, probablemente no entra al MVP (ver [§1.4](#14-los-dos-negocios-piloto-el-mvp-se-define-por-ellos)).
3. ¿Existe ya infraestructura que lo resuelve? → Reutilizar, no duplicar (ver mapa de infraestructura del Integration Hub / finanzas).
4. ¿Aumenta el alcance sin cerrar un flujo? → Cerrar el flujo primero.
5. Cuando un agente proponga algo razonable que incomoda → escalar a revisión humana (R-PROC-3).

---

# 3 — Arquitectura técnica

## 3.1 Stack tecnológico

**Backend**
| Componente | Tecnología | Estado |
|---|---|---|
| Framework | Django 4.x + Django REST Framework 3.x | ✅ |
| Auth | SimpleJWT (access en body, **refresh en cookie httpOnly**) | ✅ |
| Base de datos | PostgreSQL (único, sin SQLite) | ✅ |
| Tareas async | Celery 5.6 + Redis 7 (broker) | ✅ |
| Scheduler | django-celery-beat (DatabaseScheduler) | ✅ |
| Resultados Celery | django-celery-results (PostgreSQL) | ✅ |
| Storage archivos | django-storages + boto3 → MinIO/S3 (toggle `USE_S3`) | ✅ |
| Event store | Redpanda (Kafka-compatible) vía `apps/core/events.py` (modo stub si no hay broker) | ✅ |
| MCP runtime | FastMCP (`mcp>=1.9`) — servidores por módulo | ✅ |
| Agentes IA | Anthropic SDK directo (ver ADR-004) | ✅ parcial |
| PDF | ReportLab (activo); WeasyPrint evaluado (ADR/A-019) | ✅ |
| Monitoreo | Sentry (`sentry-sdk[django]`) en `settings_prod.py` | ✅ |
| Rate limiting | django-ratelimit (login) + nginx (prod) | ✅ |
| Calidad | pytest + pytest-cov (gate 75%), pre-commit (black, isort, flake8) | ✅ |

**Frontend**
| Componente | Tecnología | Estado |
|---|---|---|
| Framework | React 19 + TypeScript estricto | ✅ |
| Build | Vite | ✅ |
| UI | MUI v7 (**única librería UI permitida**, sin wrappers propios) | ✅ |
| Routing | React Router v7 (rutas por dominio en `src/routes/`) | ✅ |
| Estado servidor | TanStack Query v5 (`useQuery`/`useMutation`; nada de `useEffect`+fetch) | ✅ |
| Estado global | Context API (`AuthContext`, `SidebarContext`) | ✅ |
| i18n | react-i18next (es/en) | ✅ |
| PWA | vite-plugin-pwa | ✅ |
| Validación formularios | react-hook-form + zod (`src/schemas/`) | ✅ |
| Tests | Vitest + Testing Library (gate cobertura 60%) | ✅ |

**Infraestructura**
| Componente | Estado |
|---|---|
| Docker Compose dev (`docker-compose.yml`) | ✅ db, redis, backend, frontend, celery_worker/beat, minio, redpanda + console |
| Docker Compose prod (`docker-compose.prod.yml`) | ✅ + nginx reverse-proxy con rate limit y headers de seguridad |
| CI/CD | ✅ GitHub Actions (`.github/workflows/ci.yml`): jobs backend, frontend, agent-eval |
| Monitoreo APM | ⚠️ Sentry configurado; Prometheus/Grafana pendiente |
| Backup automático PostgreSQL | ❌ pendiente |
| SSL automático (Let's Encrypt) | ❌ pendiente (sección comentada en nginx.prod.conf) |

## 3.2 Estrategia multi-tenant

**Decisión (ADR-002):** Single Database + Row-Level Tenancy. Todo modelo de negocio tiene `id_empresa`. Migración futura a schema-per-tenant posible sin cambiar modelos (>500 tenants).

Reglas obligatorias: ver **R-CODE-1**. Excepción documentada: catálogos globales (`Moneda`, `Permiso`, `MetodoPago` genérico).

## 3.3 Convenciones del modelo de datos

```python
# apps/core/base_models.py — librería de modelos abstractos
TimeStampedModel       # fecha_creacion (auto_now_add) + fecha_actualizacion (auto_now)
SoftDeleteModel        # activo + soft_delete()/restore()/hard_delete()
IntegrationFieldsMixin # referencia_externa + documento_json
OmniBaseModel          # TimeStampedModel + SoftDeleteModel (combo estándar)
TenantModel            # OmniBaseModel para entidades tenant-aware
```

- **PK:** `UUIDField(primary_key=True, default=uuid7)` (R-CODE-5).
- **Unicidad:** `unique_together = ['id_empresa', 'campo']`, nunca `unique=True` global (rompe multi-tenancy).
- **Dinero:** `DecimalField` (R-CODE-4).
- **Relaciones polimórficas:** `id_entidad_origen` (UUID) + `modelo_origen` (str, ej. `'ventas.Pedido'`). No se usa `ContentType` de Django.

## 3.4 API design

- **Base URL:** `/api/...` (por app). Auth: `Authorization: Bearer <access>`.
- Respuesta paginada DRF estándar (`count`, `next`, `previous`, `results`); el frontend normaliza con `toList()`/`toCount()`.
- Errores: `{ "error": CODIGO, "message": ..., "details": {...} }`. En 500, **nunca** se filtra `str(e)` al cliente (R-CODE-8); se loguea con `logger.exception`.
- Swagger/ReDoc solo accesibles con `DEBUG=True`.

## 3.5 Primitivas AI-nativas (el moat del producto)

| Primitiva | Dónde | Qué hace |
|---|---|---|
| **Event store** | `apps/core/events.py` | `build_event()` + `publish()` a Redpanda. **Nunca rompe la transacción de negocio** (stub si no hay broker). Catálogos `VentasEvents`, `CobranzaEvents`, etc. |
| **MCP runtime** | `apps/core/mcp_server.py` + `apps/<modulo>/mcp.py` | Servidor FastMCP con auto-discovery de `MCP_TOOLS` por módulo. Comando `python manage.py run_mcp_server`. |
| **Capability tokens** | `apps/core.CapabilityToken` | Tokens con `scopes` (ej. `cxc:read`), expiración y auditoría de uso. Toda tool MCP valida scope + tenant. |
| **Agentes** | `apps/agentes/` | `OmniAgente` base con niveles de autonomía **SOMBRA / SUGERENCIA / AUTONOMO**. Solo ejecuta si `nivel=AUTONOMO` y `confianza ≥ umbral`. `PrediccionAgente` registra cada predicción + feedback humano. |
| **Eval suite** | `tests_eval/` | Casos dorados con `precision@1 ≥ 80%` en CI (cobranza y reorden). |
| **DSL de personalización** | `apps/personalizacion/` | 6 primitivas (campos, entidades, estados, reglas, vistas, conectores). Runtime: `EntidadInstancia`, `EstadoPersonalizado`, `VistaPersonalizada`. |
| **Integration Hub** | `apps/integration_hub/` | Punto único para toda conexión externa (ADR-003). Conector Odoo (XML-RPC, todas versiones), normalización canónica, checksum incremental, SyncEngine. **Ninguna app llama HTTP directo a APIs externas.** |

### Niveles de autonomía de agentes
1. **Sombra:** el agente predice y se guarda la predicción; no toca datos. (Estado actual de los agentes.)
2. **Sugerencia:** el agente propone, el humano acepta/rechaza en UI (`SugerenciasWidget`).
3. **Autónomo:** el agente ejecuta dentro de límites (umbral de confianza, máx. acciones/día), siempre reversible (R-PROD-4) y transparente (R-PROD-5).

## 3.7 Arquitectura de localización (l10n de dos capas)

> **Principio rector:** el ERP es internacionalizable por diseño. Venezuela es la **primera** localización, no la única ni la base. Nada específico de un país se incrusta en el núcleo: vive en un **paquete de localización** que se activa/desactiva por empresa según su país de operación.

### Dos planos ortogonales

- **i18n (internacionalización):** idioma y formato (es/en/pt; formatos de fecha, número y moneda). Ya implementado parcialmente con react-i18next. Es presentación, no comportamiento.
- **l10n (localización):** **comportamiento** específico de país. Es la arquitectura que se describe aquí.

### Cada localización tiene DOS capas

Una localización (ej. `l10n_ve`) se divide explícitamente en dos capas independientes que se activan por separado:

**Capa A — Regulatoria / Legal (obligatoria por ley del país)**
Lo que el Estado exige. Si cambia la ley, cambia esta capa.
- **Fiscal:** impuestos (IVA general/reducido/exento, IGTF), retenciones (IVA 75%/100%, ISLR), condición de agente de retención, alícuotas.
- **Documentos legales:** factura fiscal (número de control, RIF emisor/receptor, pie legal), notas de crédito/débito, comprobantes de retención.
- **Libros y declaraciones:** Libro de Compras / Libro de Ventas formato SENIAT (TXT + PDF), períodos fiscales, declaraciones mensuales.
- **Contabilidad:** plan de cuentas sugerido y mapeos contables del país.
- **Nómina legal:** parámetros LOTTT (utilidades, vacaciones, antigüedad, bono vacacional), aportes/deducciones (SSO, FAOV, INCES, RPE, ISLR), pagos parafiscales (Alcaldía, INCES, Aseo Urbano, SENIAT, SSO).

**Capa B — Dinámica de mercado (tropicalización; no es ley, pero la operación real la exige)**
Lo que la realidad económica del país obliga aunque ninguna ley lo pida. Es el conocimiento de negocio que diferencia a Omni de un ERP importado.
- **Multimoneda real:** VES/USD/USDT simultáneas; precios en cualquiera; totales convertidos a la moneda base.
- **Doble tasa en cada operación:** oficial (BCV) + custom/paralela. **Cada movimiento registra su equivalente en USD a tasa oficial y a tasa real** (campos tipo `tasa_bcv`/`monto_usd_bcv` + `tasa_real`/`monto_real_usd`). Tasas multi-fuente: cascade BCV (dolarapi → exchangedynamic → scrape bcv.org.ve con workaround SSL) + Binance P2P (promedio 5 BUY + 5 SELL). Pares `USD_VES`, `EUR_VES`, con tasa en fecha histórica.
- **Métodos de pago mixtos venezolanos:** efectivo VES/USD, Pago Móvil, transferencia VES/USD, Zelle, USDT (TRC-20), datáfono, divisas en efectivo.
- **Pagos de terceros** (dinámica clave por restricciones de USD): un pago se recibe/emite a través de la cuenta de un proveedor. Acciones: **abonar** (reduce CxP del proveedor como pago en USD), **solicitar reintegro** (CxC contra el proveedor, con comisión opcional y asiento contable), **asociar proveedor** a un cobro originado en caja. Aplica a **Zelle de terceros** y a **nómina/proveedores de terceros**.
- **Cambios de divisa:** operación de conversión moneda→moneda con doble registro (egreso + ingreso) y asiento contable.
- **Ventas con / sin factura:** control de lo facturado vs. no facturado (realidad de la informalidad gestionada).
- **Ventas en etapas:** adelanto (ej. 50%) + saldo contra entrega/despacho.
- **Fraccionamiento de lotes, descuentos y promociones por volumen.**
- **Libro maestro de flujo de caja** ("maestro de operaciones"): ledger unificado que normaliza ingresos/egresos de **todos** los orígenes (ventas, compras, nómina, gastos, pagos fiscales, cambios de divisa, Zelle de terceros) con su doble equivalencia en USD. Es la vista real de caja que el dueño necesita.

### Mecanismo de activación

- `Empresa.pais` (ISO 3166) determina qué localización aplica.
- Flags independientes por capa: `localizacion_legal_activa` y `localizacion_mercado_activa` (granularizables vía DSL en `configuracion_motor`). Una empresa venezolana formal activa ambas; una bodega informal podría activar solo la Capa B; una empresa de otro país, ninguna de las dos venezolanas.
- **Empresa NO venezolana → el core opera genérico:** una moneda, factura simple, métodos de pago estándar, sin IGTF, sin doble tasa, sin pagos de terceros. La UI, la API y los agentes muestran/ocultan capacidades según las capas activas.

### Implementación recomendada (strangler fig, sin big-bang)

- **`apps/localizacion/`** — framework base: registro de localizaciones, resolución por empresa, definición de **puertos/interfaces** neutrales que el core invoca: `MotorImpuestos`, `GeneradorDocumentoLegal`, `CalculadoraNomina`, `ProveedorTasas`, `MetodosPagoLocales`, `LibroLegal`.
- **`apps/localizacion_ve/`** — expansión de la app ya existente `vzla_localizacion`. Implementa los puertos para Venezuela (Capa A y Capa B). La lógica VE hoy dispersa (`apps/fiscal`, detección de IGTF en `apps/ventas`, métodos de pago IGTF, libros SENIAT, conector `tasas_ve` del Hub) se **migra gradualmente** hacia aquí dejando el core agnóstico. No se reescribe de golpe.
- **Futuras localizaciones** (Colombia DIAN/CUFE, México SAT/CFDI, Ecuador SRI, Perú SUNAT) son paquetes nuevos que implementan los mismos puertos. Ninguna toca el core.
- **Regla desde hoy:** todo módulo nuevo con lógica país-específica debe entrar por un puerto de localización, no hardcodear Venezuela. Esto evita aumentar el acoplamiento mientras se completa la extracción.

> Esta decisión debe formalizarse en **ADR-007 — Arquitectura de localización de dos capas** (pendiente de redactar).

## 3.8 Decisiones arquitectónicas (ADRs)

| ADR | Decisión | Estado |
|---|---|---|
| ADR-001 | PostgreSQL en servidor + offline-first en 3 niveles en clientes | ✅ |
| ADR-002 | Arquitectura modular + estrategia wedge (entrar por un dolor agudo) | ✅ |
| ADR-003 | Integration Hub centralizado con MCP bidireccional | ✅ |
| ADR-004 | Stack de agentes: Anthropic SDK directo (no LangChain/CrewAI/AutoGen) | ✅ |
| ADR-005 | DSL de personalización declarativo (no JSON Schema/Pydantic/parser propio) | ✅ |
| ADR-006 | Asientos contables automáticos (R-CODE-11) | ✅ |
| ADR-007 | **Arquitectura de localización de dos capas (legal + mercado), activable por empresa** | 📝 Por redactar |
| ADR-008 | Monorepo de clientes + shells mobile (RN/Expo) y desktop (Tauri 2) sobre la Capa 1 | ✅ |

---

# 4 — Estado actual real del proyecto

> Esta sección es la **foto verificada** del proyecto al 2026-05-28 (rama `main`, último commit `463c502`, tag `v0.1.0-phase0-complete`). Reemplaza los campos de estado desactualizados del antiguo Master Plan §2.2.

## 4.1 Resumen ejecutivo

- **Fase 0 (Fundación AI-nativa): CERRADA al 100%.** Tag `v0.1.0-phase0-complete`.
- **Fase 1 / Bloque 1 — núcleo común (M1–M10): COMPLETO** (M9 agentes solo en modo sombra/sugerencia).
- **Plan de hardening post-auditoría (39 ítems, `PLAN_TRABAJO_COMPLETO`): TODO COMPLETO.** Seguridad, tests, infra prod, Sentry, rate limiting, cookies httpOnly, paginación, validación zod.
- **Módulo `cxc` (Cobranza Inteligente): implementado** (Bloques 0–10 del plan CxC); frontend shell ERP moderno + asistente IA shippeado en commit `84f7ab4` (2026-05-31).
- **~37 apps Django**, **850 tests backend verdes** (verificado 2026-06-01, exit 0 en pytest) + eval suite, **~92 tests frontend**, cobertura backend gate ≥65% / frontend ≥60%.

## 4.2 Módulos — estado verificado

**Núcleo y plataforma (✅ funcional)**
- `core` — Empresa, Sucursal, Usuario, Rol, Permiso, Departamento, `Contacto` unificado, `CapabilityToken`, `Notificacion`, `ConfiguracionFlujoDocumentos`, base_models, MCP server, event store.
- `configuracion_motor` — TipoDocumento, ParametroSistema, CatalogoValor.
- `auditoria` — `RegistroAuditoria` (modelo + admin); los signals viven en `core/signals.py` (no en `auditoria/signals.py`). Pendiente consolidar en su app de origen.
- `saas` — middleware de suscripción (fail-open documentado, desactivable), planes.
- `integration_hub` — conector Odoo completo + SyncEngine + Celery tasks + MCP.
- `personalizacion` — DSL runtime (entidades/estados/reglas/vistas).
- `agentes` — `OmniAgente`, niveles de autonomía, `PrediccionAgente`, eval suite, clasificador de gastos (sombra), sugerencias diarias.
- `notificaciones` — in-app (badge + polling 30s) + email Celery + emisión automática en ventas/pagos.
- `gestion_documental` — upload/download S3 con URLs prefirmadas.

**Ciclo comercial (✅ funcional)**
- `ventas` — Cotización → Pedido → Nota de Venta → Factura Fiscal → Notas de crédito/devoluciones. Integrado con stock, fiscal (IVA/IGTF), contabilidad (asientos), CxC. Listas de precios. PDF con pie legal venezolano.
- `inventario` — Producto, movimientos (entrada/salida/ajuste/traslado/reserva/salida interna), StockActual, kardex, alertas de stock mínimo. UI completa (dashboard, stock, kardex, ajustes).
- `compras` — OC → Recepción → Factura, CxP, asientos automáticos.
- `crm` — Cliente con RIF, límite/días de crédito, historial, búsqueda por RIF.
- `proveedores` — datos maestros, búsqueda por RIF.
- `finanzas` — Monedas, MetodoPago, Pago genérico multi-moneda, Cajas/Sesiones, TasaCambio (BCV), conversión multimoneda, MCP.
- `fiscal` — ConfiguracionFiscalEmpresa, TasaIVAEmpresa, cálculo IVA/IGTF, Libros SENIAT (TXT + PDF), PeriodoFiscal con cierre, UI de configuración y libros.
- `contabilidad` — PlanCuentas, AsientoContable, MapeoContable, `generar_asiento()` (R-CODE-11).
- `cuentas_por_cobrar` — saldos, abonos, aging (5 tramos), estado de cuenta PDF; servicios de aging/scoring/cartera_provider para CxC.
- `cuentas_por_pagar` — AbonoCxP, abonos, aging.
- `tesoreria` — MovimientoBancario, ConciliacionBancaria (matching automático), import CSV.
- `cxc` — Cobranza Inteligente: GestionCobranza, PlantillaCobranza, AcuerdoPago/CuotaAcuerdo, fraccionamiento (feature-flag), MCP server, agente IA de cobranza, dashboard/aging frontend. Conector `tasas_ve` (BCV cascade + Binance P2P) en el Hub.

**RRHH (🔶 parcial)**
- `rrhh` — Empleado, Cargo, Beneficio (modelos + tests).
- `nomina` — PeriodoNomina, ConceptoNomina (modelos + tests; cálculo LOTTT completo pendiente).
- `control_asistencia` — FK reales a Empleado restauradas; marcajes básicos.

**Estructura creada, lógica pendiente (🔲)**
- `almacenes`, `despacho`, `logistica_transporte`, `flota`, `control_calidad`, `costos`, `gastos` (con aislamiento), `manufactura` (modelos + multi-tenant; MRP/OF pendiente), `servicio_cliente`, `banca_electronica`, `integracion_b2b`, `migracion_datos`, `vzla_localizacion`, `eventos`.

## 4.3 Deuda técnica conocida y abierta

- **Nómina venezolana completa** (LOTTT: utilidades, vacaciones, antigüedad, ISLR progresivo, cestaticket multimoneda) — pendiente.
- **Manufactura completa** (MRP, órdenes de producción con etapas, costeo real) — pendiente; crítico para el piloto Fábrica.
- **Backup automático de PostgreSQL** y **SSL automático** — pendiente.
- **Prometheus/Grafana** — pendiente (Sentry ya está).
- **`saas` middleware fail-open** — revisar a fail-closed al activar `SAAS_VERIFICAR_SUSCRIPCION`.
- **Service Workers / offline real** (portales) — pendiente.
- **Acoplamiento a Venezuela en el núcleo** — hoy la lógica VE está dispersa y semi-incrustada (`apps/fiscal`, detección de IGTF en `apps/ventas`, métodos de pago IGTF, libros SENIAT). Debe migrarse a la arquitectura de localización de dos capas (ver [§3.7](#37--arquitectura-de-localización-l10n-de-dos-capas)) vía strangler fig. La app `apps/vzla_localizacion` ya existe como punto de partida pero está casi vacía.
- **Capa B (dinámica de mercado) parcialmente cubierta** — multimoneda, tasas, CxC, métodos de pago y **`OperacionCambioDivisa` (apps/tesoreria, con comisiones y CRUD)** existen, pero faltan como capacidades de localización formalizadas: pagos de terceros (Zelle/nómina), doble tasa universal en cada operación, libro maestro de flujo de caja, ventas con/sin factura. Insumos disponibles en el proyecto `GestionCxC` (ver [§6](#6--localización-venezuela-l10n-ve)).
- **Dos `PROJECT_LOG.md` divergentes** (raíz vs `backend/`) — consolidar: `backend/PROJECT_LOG.md` es el vigente; el de la raíz debe archivarse.
- **Encoding (mojibake)** en `docs/_archive/OMNI_ERP_MASTER_PLAN.md` — documento archivado; su contenido vigente ya está consolidado aquí.

Los compromisos técnicos fechados (CTF) viven en `docs/ctf/` con `vence_en` y dueño (R-PROC-6). CTF-001 a CTF-004 están CERRADOS.

---

# 5 — Roadmap unificado

> **Reconciliación de marcos.** El proyecto se ha descrito con tres vocabularios distintos. Este es el mapeo único de aquí en adelante:
>
> | Marco | Equivalencia |
> |---|---|
> | "Fases 0–5" (Master Plan / AI-Native) | Hitos técnicos del producto |
> | "Bloques 1–3" (Founder Solo) | Hitos de negocio (la métrica que importa) |
> | "Sub-fases 1.A–1.J / Sesiones / M1–M10" | Unidades de ejecución |
>
> **A partir de ahora usamos los Bloques de negocio como guía maestra**, porque la métrica única (un negocio operando en producción) es lo que cierra cada bloque, no una checklist de features.

## 5.1 Dónde estamos

```
BLOQUE 1 — De idea a primer cliente piloto  [EN CURSO]
├── 1.A Fundación técnica .................... ✅ COMPLETO (Fase 0 cerrada)
├── 1.B Núcleo común parte 1 (catálogos,
│        inventario, multimoneda) ............ ✅ COMPLETO
├── 1.C Núcleo común parte 2 (ciclo comercial,
│        fiscal VE) ........................... ✅ COMPLETO
├── 1.D Núcleo común parte 3 (compras, CxP,
│        listas precios, reportes/PDF) ........ ✅ COMPLETO
├── 1.E Personalización + agentes (DSL,
│        agentes en modo sugerir) ............. ✅ COMPLETO (sombra/sugerencia)
│        + Cobranza Inteligente (apps/cxc) ..... ✅ COMPLETO (backend + frontend shippeado en 84f7ab4)
├── 1.F Distribuidora en producción .......... ⬜ SIGUIENTE HITO
├── 1.G Específicos distribuidora (POS,
│        comisiones, devoluciones, despacho) ... ⬜ pendiente
├── 1.H Onboarding fábrica + BOM ............. ⬜ pendiente
├── 1.I OF y costeo (manufactura) ............ ⬜ pendiente
└── 1.J Estabilización ....................... ⬜ pendiente
```

**Conclusión:** El núcleo común del MVP (sub-fases 1.A–1.E) está construido y endurecido. **El trabajo ya no es "construir más módulos en abstracto" — es poner la distribuidora a operar (1.F).** Eso es lo que cumple R-PROC-8 y cierra el riesgo de "60 módulos a medias".

## 5.2 Próximos pasos inmediatos (orden recomendado)

### Paso 0 — Higiene de documentación (esta entrega)
- [x] Consolidar planificación en este documento único.
- [ ] Archivar planes ejecutados y el `PROJECT_LOG.md` de la raíz (ver §10).
- [x] Frontend shell ERP moderno + asistente IA shippeado en `84f7ab4` (2026-05-31). Cierra ítem "pulido cxc" del plan original.
- [ ] **Auditoría 2026-06-01:** ejecutar `docs/PLAN_TRABAJO_AUDITORIA_2026-06-01.md` (33 hallazgos + 4 deltas vs plan). Bloqueante de pasos siguientes para ítems CRIT-1..3 y H-SEC-1..2.

### Sub-fase 1.F — Distribuidora en producción (PRÓXIMO, métrica que cierra Bloque 1 parcial)
**Objetivo único:** la distribuidora opera diariamente con Omni durante **30 días continuos** sin volver a su sistema anterior.
- [ ] **Migración de datos reales** de la distribuidora (clientes, productos, inventario inicial, saldos CxC). Usar `apps/migracion_datos` / management commands; validación fila por fila.
- [ ] **Caja diaria operativa**: apertura/cierre rápido, pagos mixtos VES+USD en <30s, cuadre con sobrante/faltante.
- [ ] **Datos fiscales reales**: configuración fiscal de la empresa, correlativos, primera factura fiscal real válida + libro de ventas SENIAT del mes.
- [ ] **Capacitación + arranque controlado** (operación en paralelo con el sistema viejo unos días).
- [ ] **Acompañamiento intensivo**: bugfixing en caliente, ajustes de UX según uso real.
- [ ] **Agente de cobranza en modo sugerencia** activo sobre la cartera real (CxC ya está).

**DoD 1.F:** distribuidora factura, cobra, controla stock y consulta cartera con Omni, 30 días sin recaída.

### Sub-fase 1.G — Específicos de la distribuidora
- [ ] POS de mostrador (táctil, código de barras USB, recibo térmico 80mm).
- [ ] Comisiones de vendedores.
- [ ] Devoluciones y notas de crédito en flujo POS.
- [ ] Despacho/entrega (`apps/despacho`).
- [ ] Offline nivel 2 (Service Workers) si el punto de venta lo requiere.

### Sub-fase 1.H — Onboarding fábrica + BOM
- [ ] La fábrica usa el núcleo común (ventas, compras, inventario, fiscal).
- [ ] **BOM (Lista de Materiales)** cargado en `apps/manufactura`.
- [ ] Cotización de mueble a medida que estalla materiales + mano de obra + margen.

### Sub-fase 1.I — Órdenes de fabricación y costeo
- [ ] **OF con etapas** (corte → ensamble → lijado → pintura → tapizado → control final).
- [ ] Consumo de materiales y producto terminado integrado con inventario.
- [ ] **Costeo real** por OF; pago a destajo.
- [ ] MRP básico (materiales necesarios para producir X).

### Sub-fase 1.J — Estabilización (cierre de Bloque 1)
- [ ] Bugfixing y documentación del producto al día.
- [ ] Backlog de feedback de pilotos categorizado.
- [ ] Demo grabada de ambos negocios operando + caso de éxito con métricas reales.
- [ ] Backup automático PostgreSQL + SSL en producción.

**DoD Bloque 1:** distribuidora 90 días continuos + fábrica 60 días con OF y costeo.

## 5.2-bis Workstream transversal — Arquitectura de localización (l10n)

> Es **transversal**, no una fase. No frena la sub-fase 1.F (la distribuidora se pone en producción con la lógica VE actual), pero **gobierna cómo se escribe todo código país-específico desde ahora** (R-PROC-1) para no profundizar el acoplamiento.

**Desde ahora (regla activa, costo cero):**
- [ ] Todo código nuevo con lógica de un país entra por un **puerto de localización**, nunca hardcodeado en el core (ver [§3.7](#37--arquitectura-de-localización-l10n-de-dos-capas)).
- [ ] Redactar **ADR-007** (arquitectura de localización de dos capas).

**Extracción gradual (mayormente en Bloque 2, strangler fig):**
- [ ] Crear `apps/localizacion/` (framework: registro, resolución por empresa, puertos `MotorImpuestos`/`GeneradorDocumentoLegal`/`CalculadoraNomina`/`ProveedorTasas`/`MetodosPagoLocales`/`LibroLegal`).
- [ ] Expandir `apps/vzla_localizacion` → `localizacion_ve`: mover Capa A (fiscal, libros SENIAT, factura legal, nómina LOTTT, pagos parafiscales) y Capa B (multimoneda, doble tasa, métodos de pago, pagos de terceros, cambios de divisa, ventas con/sin factura, libro maestro de caja).
- [ ] Añadir `Empresa.pais` + flags `localizacion_legal_activa` / `localizacion_mercado_activa`; el core opera genérico si están off.
- [ ] Portar insumos de `GestionCxC` que aún no están en Omni (ver [§6.8](#68--backlog-de-tropicalización-desde-gestioncxc)).

**Criterio de salida:** una empresa de prueba **no venezolana** opera el ciclo comercial completo (cotización→factura→cobro→asiento) sin ver IGTF, doble tasa, ni métodos de pago venezolanos, y una empresa venezolana sigue teniendo todo. Eso prueba que la localización es realmente enchufable.

## 5.2-ter Workstream transversal — Monorepo + shells mobile/desktop (ADR-008)

> Este workstream **ejecuta operativamente** la decisión arquitectónica de [ADR-008](decisions/ADR-008-monorepo-shells-multiplataforma.md). Es transversal y **subordinado a 1.F**: ninguna fase de aquí arranca si pone en riesgo la distribuidora en producción (R-PROC-8). Para el racional, las alternativas descartadas y los criterios de éxito, ver ADR-008. Esta sección solo lista fases con triggers y DoD.

### Mapeo al roadmap del proyecto

| Fase de este workstream | Cuándo arranca | Subordinada a |
|---|---|---|
| **Fase 0–1** (monorepo + extracción Capa 1 a `packages/`) | Después de 1.F en producción 30 días | 1.J o paralelo a 1.G si hay holgura |
| **Fase 2** (cerrar Nivel 1 de ADR-001 en la PWA web existente) | **Puede arrancar ya** — es deuda técnica de §4.3, no toca arquitectura | — |
| **Fase 3** (shell Desktop con Tauri 2) | Tras Fase 1 | Habilita POS de 1.G |
| **Fase 4** (shell Mobile + Nivel 2 de ADR-001) | Tras Fase 3, demanda real | Cronograma ADR-001: ~mes 9 (app vendedores) |
| **Fase 5** (`clients/cobranza-standalone`) | Tras Fase 4 | Ejecuta wedge de ADR-002/004 |
| **Fase 6** (paridad y release 1.0 multiplataforma) | Bloque 2 | — |

### Fases con DoD

**Fase 0 — Bootstrap monorepo** (trigger: 1.F DoD cumplido).
- Migrar `frontend/` → `clients/web/`; configurar pnpm workspaces + turborepo.
- `drf-spectacular` en backend + `openapi-typescript` en CI; falla el build ante diff sin commit.
- CI con jobs por workspace.
- **DoD:** monorepo verde en CI; `clients/web` se comporta idéntica para el usuario.

**Fase 1 — Extracción de Capa 1 a `packages/`** (trigger: Fase 0 cerrada).
- `packages/domain` (schemas Zod, tipos, reglas puras), `packages/api-client` (HTTP con `HttpAdapter` + `TokenStorage` inyectables — elimina `localStorage`/`window` directos de `services/api.ts`), `packages/auth` (`SecureStorage` interface), `packages/i18n`.
- Refactor de `clients/web` para consumir packages.
- **DoD:** 0 imports relativos a archivos compartidos desde `clients/web`; cobertura ≥60% mantenida.

**Fase 2 — Nivel 1 de ADR-001 en la web** (trigger: ya; no depende de Fase 0/1).
- Auditar y endurecer la PWA actual (cobertura de caché, expiración, fallback offline).
- Reintento de mutaciones con backoff (sin outbox completo).
- Banner global de estado online/offline + badge "datos stale".
- **DoD:** un corte de 5 minutos no rompe consultas y los reintentos completan al volver la red. Cierra la deuda "Service Workers / offline real" de [§4.3](#43-deuda-técnica-conocida-y-abierta).

**Fase 3 — Shell Desktop (Tauri 2)** (trigger: Fase 1 cerrada).
- `clients/desktop` envolviendo el build de `clients/web`.
- Adaptadores Tauri: `tauri-plugin-sql` (SQLite), `tauri-plugin-stronghold` (secrets), `tauri-plugin-printer` (térmica 80mm), `tauri-plugin-updater` (OTA).
- Implementación de `packages/offline` para Tauri (LocalStore + outbox sobre SQLite).
- Instaladores firmados: `.msi`, `.dmg`, `.AppImage`/`.deb`.
- **DoD:** caja de la distribuidora opera 8 h sin red y sincroniza al final del día (Nivel 2 de ADR-001 sobre POS).

**Fase 4 — Shell Mobile (RN + Expo) + Nivel 2** (trigger: Fase 3 cerrada y demanda real de vendedor en ruta).
- Decisión RN Paper vs Tamagui antes de empezar (sub-decisión menor, no requiere ADR).
- `clients/mobile` con `expo-router`, `expo-secure-store`, `op-sqlite`.
- Pantallas piloto: Pedidos, Clientes, Productos, Cobranza, Asistencia.
- Push notifications (Expo) atadas a `apps/notificaciones`.
- Build TestFlight + Internal Track Play Store.
- **DoD:** vendedor en ruta toma pedido sin red y sincroniza al volver sin conflictos.

**Fase 5 — `clients/cobranza-standalone`** (trigger: Fase 4 cerrada y/o gestion-cxc-V2 listo para sustituirse).
- Shell que solo importa `cxc`, `crm`, `auth`, `i18n` de `packages/`.
- Empaquetado en las 3 plataformas reusando los shells.
- Modo "integración con ERP destino" vía Integration Hub (Capa 3).
- **DoD:** la empresa donde el founder es gerente usa Omni Cobranza standalone sobre su ERP existente.

**Fase 6 — Paridad y release 1.0 multiplataforma** (trigger: Bloque 2).
- Migrar dominios restantes (fiscal, inventario, finanzas, configuración) a mobile/desktop.
- E2E: Detox (mobile), Playwright (web), tauri-driver (desktop).
- UI de resolución de conflictos.
- Telemetría unificada (Sentry en los 3 shells).
- **DoD:** release **1.0 multiplataforma** con paridad funcional.

### Regla activa desde ahora (costo cero)

- Todo cambio nuevo en `frontend/` debe ser **portable** a `packages/domain` cuando llegue la Fase 1. Concretamente: no añadir lógica de negocio dentro de componentes; vivirá en hooks/servicios; no usar `localStorage`/`window` directamente fuera de un adaptador.
- Toda regla de cálculo de dinero, IVA, IGTF, scoring que se escriba desde hoy debe ser **pura** (sin I/O) — pre-condición para vivir en `packages/domain`.

## 5.3 Bloque 2 — De piloto a producto (Mes 16–33 aprox.)
**Métrica única:** 5+ clientes externos pagando con retención >70%, y el founder puede pasar 2 semanas sin tocar el sistema sin que se rompa.
- 2.A Primer cliente externo (onboarding real, no familiar tolerante).
- 2.B Estabilización seria (no más hotfix a las 2am).
- 2.C Crecimiento controlado (5–10 clientes).
- 2.D Decisión de Bloque 3.
- Features probables: multi-sucursal, conciliación/banca electrónica real, nómina completa, WhatsApp Business API, dashboard de analítica (`analitica_negocio`), constructor de reportes.
- **NO entra:** Platform Spaces, blockchain, multi-país, levantar capital.

## 5.4 Bloque 3 — Bifurcación
Al cerrar Bloque 2 se elige un camino: **A)** lifestyle business · **B)** levantar capital · **C)** vender a un consolidador. Cada uno tiene su propio plan que se redactará en su momento.

## 5.5 Visión de largo plazo (post-Bloque 2, referencial)
Del catálogo del Master Plan, en orden de prioridad histórica:
- **Diferenciación competitiva:** manufactura completa, control de calidad, costos, servicio al cliente con SLA, CRM avanzado, restaurante POS, portales (clientes, vendedores, proveedores, conductores delivery), BPM/motor de reglas, planificación financiera, activos fijos.
- **Liderazgo técnico:** `asistente_ia` (copiloto conversacional), IA aplicada (predicción de demanda, scoring crediticio, detección de fraude), ml_ops, iot_data, wms_avanzado, marketplace de extensiones, developer portal.
- **Expansión global:** i18n completo (en/pt/fr), módulos fiscales por país (DIAN, SAT/CFDI, SRI, SUNAT), compliance internacional (GDPR/LGPD/SOC2), multi-región, schema-per-tenant para enterprise.

> El catálogo completo de ~60 módulos y sus prioridades originales se conserva archivado en `docs/_archive/OMNI_ERP_MASTER_PLAN.md` (Parte IV) como **referencia de visión**, no como compromiso de roadmap.

---

# 6 — Localización Venezuela (l10n-ve)

> Esta sección es el **catálogo de la localización venezolana**, organizada en las dos capas de [§3.7](#37--arquitectura-de-localización-l10n-de-dos-capas). Todo lo de aquí se activa/desactiva por empresa y, a término, vive en `apps/localizacion_ve`, no en el núcleo.

## CAPA A — Regulatoria / Legal

## 6.1 Fiscalidad (SENIAT)

**IVA:** general 16%, reducida 8%, cero 0% (exportaciones), exento. **IGTF:** 3% sobre pagos en divisas/crypto/oro (no aplica a VES); lo paga el pagador; se discrimina en factura. **Retenciones:** IVA 75%/100%, ISLR (tabla por actividad).

```python
def calcular_igtf(monto_divisas: Decimal, empresa) -> Decimal:
    config = empresa.configuracion_fiscal
    if not config.aplica_igtf:
        return Decimal('0')
    return (monto_divisas * config.alicuota_igtf / 100).quantize(Decimal('0.01'))
```

Métodos de pago con IGTF (implementados): `DIVISA_EFECTIVO`, `DIVISA_TRANSFERENCIA`, `CRYPTO`, `PETRO`.

**Documentos fiscales:** Factura con número de control + número de factura + RIF receptor; Notas de débito/crédito vinculadas; Comprobantes de retención; **Libro de Compras y Libro de Ventas mensuales formato SENIAT** (TXT pipe-delimited con cabecera + PDF, ya implementados).

## 6.2 Nómina venezolana (LOTTT) — pendiente de implementación completa
Componentes: salario base (VES + equiv. USD), cestaticket (USD/BCV), bono alimentación/transporte, horas extra (50% diurnas / 100% nocturnas), bono nocturno, utilidades (15–120 días), vacaciones + bono vacacional, antigüedad (5 días/año + 2 adicionales tras 3 años). Deducciones: SSO 4%, FAOV 1%, RPE 0.5%, ISLR progresivo (UT), préstamos, comedor. Aportes patronales: SSO 9%, FAOV 2%, INCES 2%, RPE 2%. Salario mínimo y UT actualizables vía `ParametroSistema`.

## 6.3 Pagos parafiscales (Capa A)
Pagos al Estado más allá de IVA/ISLR: **Alcaldía, INCES, Aseo Urbano, SENIAT, SSO**, cada uno con su cuenta de gasto y diario contable configurable. Genera egreso en el libro de caja + asiento contable automático (R-CODE-11).

---

## CAPA B — Dinámica de mercado (tropicalización)

## 6.4 Multimoneda y doble tasa

```
VES → moneda base legal
USD → moneda de referencia operativa
USDT → reserva de valor más usada
Tasas: OFICIAL_BCV (cascade 3 fuentes + scrape) · PROMEDIO_MERCADO (Binance P2P 5+5) · USUARIO_LIBRE
```
- **Doble tasa universal:** cada operación monetaria registra su equivalente en USD a **tasa oficial (BCV)** y a **tasa real/custom (paralela)** — campos tipo `tasa_bcv`/`monto_usd_bcv` + `tasa_real`/`monto_real_usd`. Esto permite reportes "a tasa oficial" y "a tasa real" simultáneos, que es lo que el dueño realmente necesita.
- Tasas multi-fuente sincronizadas por el Integration Hub (`sync_tasas_ve`, ya implementado): cascade BCV (dolarapi → exchangedynamic → scrape `bcv.org.ve` con workaround SSL) + Binance P2P (promedio 5 BUY + 5 SELL). Pares `USD_VES`, `EUR_VES`. Soporta tasa en fecha histórica. Persiste en `finanzas.TasaCambio`.
- Regla crítica: mostrar precios en la moneda que el cliente desee, pero **todos los totales se convierten a la moneda base** para contabilidad y reportes.

## 6.5 Métodos de pago y dinámicas comerciales
- Métodos mixtos: efectivo VES/USD, Pago Móvil, transferencia VES/USD, Zelle, USDT (TRC-20), datáfono, divisas en efectivo.
- **Ventas con / sin factura:** control separado de lo facturado vs. no facturado.
- **Ventas en etapas:** adelanto (ej. 50%) + saldo contra entrega.
- Fraccionamiento de lotes, descuentos y promociones por volumen.

## 6.6 Pagos de terceros y cambios de divisa
Dinámica forzada por las restricciones para recibir/emitir USD en Venezuela:
- **Pago de terceros (Zelle y nómina/proveedores):** un cobro o pago pasa por la cuenta de un proveedor. Acciones modeladas: **abonar** (reduce CxP del proveedor como pago USD + asiento), **solicitar reintegro** (genera CxC contra el proveedor, con comisión opcional y su asiento), **asociar proveedor** a un cobro originado en caja, **marcar reintegrado**. Estados: `pendiente → abonado | reintegro_pendiente → reintegrado | anulado`.
- **Cambios de divisa:** operación de conversión moneda→moneda con doble registro (egreso + ingreso) en el libro de caja y asiento contable; flujo borrador → validado → enviado a contabilidad, con aprobación.

## 6.7 Libro maestro de flujo de caja
Ledger unificado ("maestro de operaciones") que normaliza **ingresos y egresos de todos los orígenes** (ventas, compras, nómina, gastos, pagos fiscales, cambios de divisa, pagos de terceros) en una sola vista, cada uno con su doble equivalencia USD (oficial + real). Es la radiografía de caja diaria que el dueño consulta y la base de los reportes financieros tropicalizados.

## 6.8 Backlog de tropicalización desde GestionCxC

`C:\Users\PC\Proyectos\GestionCxC` es un sistema previo (FastAPI + Odoo) con lógica venezolana madura y probada en producción. La conexión Odoo y las CxC/cobranza **ya se portaron** a Omni (`apps/integration_hub`, `apps/cxc`, `apps/cuentas_por_cobrar`). Quedan como insumos a portar hacia `apps/localizacion_ve` (Capa B, salvo lo fiscal que es Capa A):

| Origen en GestionCxC | Concepto a portar | Capa | Destino sugerido en Omni |
|---|---|---|---|
| `routers/zelle_terceros.py` | Zelle de terceros (abonar / reintegro+comisión / asociar proveedor) | B | `localizacion_ve` + `finanzas`/`cuentas_por_pagar` |
| `routers/nomina.py` (terceros) | Nómina de terceros (pago vía proveedor, descuento AP) | B | `localizacion_ve` + `nomina` |
| `routers/nomina.py` | Nómina manual/import + config de cuentas por tipo | A/B | `nomina` + `localizacion_ve` |
| `routers/cambios_divisa.py` | Cambios de divisa (doble registro + asiento + aprobación) | B | `localizacion_ve` + `tesoreria`/`finanzas` |
| `routers/pagos_fiscales.py` | Pagos parafiscales (Alcaldía, INCES, Aseo, IVA, ISLR, SENIAT, SSO) | A | `localizacion_ve` + `contabilidad` |
| `routers/gastos.py` | Gastos únicos/recurrentes/servicios públicos + config contable por categoría | B | `gastos` |
| `routers/cuentas_por_pagar.py` | CxP con dinámica VE | B | `cuentas_por_pagar` |
| `routers/creditos.py`, `fraccionamiento.py`, `descuentos.py`, `promociones.py`, `precios.py` | Crédito, fraccionamiento, descuentos/promos por volumen | B | `ventas`/`cxc`/`localizacion_ve` |
| `services/tasas_cambio.py`, `binance_p2p.py` | Tasas multi-fuente + doble tasa | B | ✅ ya en `integration_hub/connectors/tasas_ve` |
| `maestro_operaciones` (modelo) | Libro maestro de flujo de caja con doble equivalencia | B | nuevo en `tesoreria` o `localizacion_ve` |

> Al portar: respetar R-CODE (multi-tenant, Decimal, UUIDv7, soft delete, asiento automático) y entrar por puertos de localización, no replicar el acoplamiento de GestionCxC. La lógica de negocio (algoritmos, estados, flujos) es el insumo; la arquitectura es la de Omni.

---

# 7 — Estándares de código y proceso

## 7.1 Backend (Django/DRF)
- ViewSets heredan de `BaseModelViewSet` (aplica `IsAuthenticated` + filtro por empresa). `perform_create` inyecta `empresa` y usuario.
- `read_only_fields` incluye PK, `id_empresa`, fechas y correlativos.
- `logger = logging.getLogger(__name__)` al top. Niveles: info/warning/error/exception. Nunca `print`.
- Cada módulo: `models.py`, `views.py`, `serializers.py`, `urls.py`, `services.py` (lógica de negocio), `mcp.py` (tools), `tests` (incluido test de aislamiento).
- Toda lógica de negocio en `services.py` con `@transaction.atomic` y `select_for_update` donde haya carreras.
- Índices: `(id_empresa, fecha_creacion)`, `(id_empresa, estado)`, `(id_empresa, id_cliente)`.

## 7.2 Frontend (React/TS)
- Toda llamada a API pasa por `services/api.ts`; nunca `fetch()` directo ni URLs hardcodeadas (`import.meta.env.VITE_API_URL`).
- TanStack Query para server state; QueryKeys incluyen filtros/paginación para refetch automático.
- MUI directo; errores con `<Alert>`, no `alert()`. Acciones destructivas piden confirmación.
- Formularios con react-hook-form + zod (`src/schemas/`).
- Sin `any`; interfaces tipadas para respuestas API.

## 7.3 Git y PRs
- Ramas: `feature/...`, `fix/...`, `chore/...`, `hotfix/...`. Conventional Commits en español (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`).
- Checklist PR: ver R-CODE/R-PROC §2 + checklist de incorporación §9.4. CI verde obligatorio.

## 7.4 Definition of Done de un módulo nuevo
Modelos con `id_empresa`+UUIDv7 · unique_together correcto · ViewSet `BaseModelViewSet` · servicios con `@transaction.atomic` · R-CODE-11 si tiene impacto contable · tool MCP (R-CODE-7) · test de aislamiento · migración reversible · sin secretos/`print`/`any` · UI conectada al sidebar · entrada en `backend/PROJECT_LOG.md`.

---

# 8 — Protocolo de trabajo por sesión

> Cada sesión de trabajo (founder + IA) es la unidad básica. El protocolo original se conserva en `docs/_archive/AGENTE_IA_PROTOCOLO_EJECUCION.md`; lo esencial está aquí.

1. **Arranque:** leer `backend/PROJECT_LOG.md` (últimas sesiones) + este plan; verificar repo limpio y CI verde.
2. **Planear:** elegir la tarea más pequeña que avance la sub-fase actual (hoy: 1.F). Confirmar que no viola §2.
3. **Ejecutar:** una cosa, con tests. `@transaction.atomic`, R-CODE-* aplicadas.
4. **Verificar:** `pytest` + `tsc --noEmit` + `vitest` verdes; `python manage.py check` sin issues.
5. **Auto-checklist del PR:** qué cambia, conexión con el plan, reglas verificadas, eventos/MCP expuestos, decisiones, compromisos técnicos fechados creados, riesgos.
6. **Cerrar:** commit con Conventional Commits; **append** al `backend/PROJECT_LOG.md` (nunca editar/borrar entradas previas).
7. **Ritual del lunes:** responder en 5 min — ¿qué se construyó la semana pasada y sirve a un piloto? ¿qué se construye esta semana? ¿qué regla podría romperse y cómo se evita?

**Lo que un agente NO hace jamás:** auto-merge, borrar datos sin proceso, saltarse el test de aislamiento, introducir SQLite, exponer secretos, llamar APIs externas fuera del Integration Hub, ampliar alcance sin cerrar un flujo.

---

# 9 — Guía de incorporación

## 9.1 Lee en este orden
1. Este documento completo.
2. `backend/PROJECT_LOG.md` (últimas 5 sesiones) para el contexto reciente.
3. `docs/decisions/` (ADRs).
4. El código: `apps/core/` → `apps/finanzas/` → `apps/ventas/` → `apps/cxc/` → `frontend/src/pages/Ventas/`.

## 9.2 Requisitos
Python 3.11+, Node 20+, Docker Desktop, Git, PostgreSQL (o usar el de Docker).

## 9.3 Setup
```bash
git clone <repo> && cd omni-erp
cp backend/.env.example backend/.env       # editar valores locales
cp frontend/.env.example frontend/.env

# Opción A — local
cd backend && python -m venv .venv && source .venv/bin/activate   # Win: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate && python manage.py createsuperuser && python manage.py runserver
cd ../frontend && npm install && npm run dev

# Opción B — Docker (stack completo)
docker compose up --build
```
**URLs dev:** Frontend `:5173` · API `:8000/api/` · Admin `:8000/admin/` · Swagger `:8000/api/docs/` (solo DEBUG) · Redpanda console `:8080` · MinIO `:9001`.
**Notas de puertos:** PostgreSQL nativo del dev en `5433`; PostgreSQL de Docker expuesto en `5434` (evita colisión). MCP server: `python manage.py run_mcp_server [--sse --port N]`.

## 9.4 Estructura del repositorio
```
omni-erp/
├── backend/
│   ├── apps/<modulo>/   models, views, serializers, urls, services, mcp, tests, migrations
│   ├── config/          settings_base/prod, urls, celery
│   ├── tests_api/       tests de integración y aislamiento (47 archivos)
│   ├── tests_eval/      eval suite de agentes
│   ├── PROJECT_LOG.md   ← registro cronológico VIGENTE
│   ├── docs/            análisis técnicos (ej. CIRCULAR_IMPORTS_ANALYSIS)
│   └── requirements.txt
├── frontend/
│   └── src/  pages, components, contexts, hooks, services, routes, schemas, i18n, __tests__
├── docs/                PLAN_MAESTRO_UNICO (este), decisions/ (ADRs), skills/, ctf/, _archive/ (planes históricos)
├── infra/               nginx, redpanda config
├── docker-compose.yml · docker-compose.prod.yml
└── .github/workflows/ci.yml
```

## 9.5 Áreas de trabajo abiertas hoy
- **Backend:** nómina LOTTT completa, manufactura (OF + costeo + MRP), promover agentes a modo sugerencia/autónomo sobre datos reales.
- **Frontend:** terminar UI de `cxc`, POS de mostrador, Service Workers offline, dashboard de analítica.
- **DevOps:** backup automático PostgreSQL, SSL Let's Encrypt, Prometheus/Grafana.
- **Datos:** migración de la distribuidora real (sub-fase 1.F).

---

# 10 — Mapa de documentos (vigencia)

**Este es el único documento de planificación vivo.** Toda la planificación previa fue consolidada aquí y archivada. Lo que permanece vivo son registros operativos, no planes.

### Documentación viva

| Documento | Rol |
|---|---|
| **`docs/PLAN_MAESTRO_UNICO.md`** (este) | Único documento de planificación — fuente de verdad |
| `backend/PROJECT_LOG.md` | Registro cronológico de sesiones (append-only, inmutable) |
| `docs/decisions/ADR-*.md` (001–006, +007 por redactar) | Decisiones arquitectónicas |
| `docs/ctf/*` | Compromisos técnicos fechados (R-PROC-6) |
| `docs/skills/*` | Skills de codificación del proyecto |
| `backend/docs/CIRCULAR_IMPORTS_ANALYSIS.md` | Análisis técnico puntual (no es plan) |

### Archivado en `docs/_archive/` (consolidado en este documento)

Planes históricos, conservados solo como referencia de origen. **No se actualizan ni se usan para planificar.**

| Archivado | Era | Su contenido vive ahora en |
|---|---|---|
| `OMNI_ERP_MASTER_PLAN.md` | Catálogo de ~60 módulos y visión | §1, §3, §5.5, §6 |
| `01_MVP_SCOPE_NEGOCIOS_PILOTO.md` | Alcance MVP por pilotos | §1.4 |
| `02_PLAN_EJECUCION_FOUNDER_SOLO.md` | Metodología founder + Bloques | §1, §5, §8 |
| `OMNI_AI_NATIVE_EXECUTION_PLAN.md` | Reglas R-CODE/R-PROC/R-PROD + DoD | §2 |
| `AGENTE_IA_PROTOCOLO_EJECUCION.md` | Protocolo por sesión | §8 |
| `CXC-PLAN-IMPLEMENTACION.md` | Plan del módulo CxC (ejecutado) | §4.2, §6.8 |
| `PLAN_FASE1_DETALLADO.md` | Plan M1–M10 (ejecutado) | §4 |
| `PLAN_TRABAJO_POST_AUDIT.md` | Plan Fases A–D (ejecutado) | §4 |
| `PLAN_TRABAJO_COMPLETO.md` | 39 ítems hardening (completo) | §4 |
| `DIAGNOSTICO_INICIAL.md` | Diagnóstico Sesión 1 (obsoleto) | — |
| `CHANGELOG_FASE1.md` | Changelog M1–M7 (histórico) | `backend/PROJECT_LOG.md` |
| `05_PLAN_CREACION_SKILLS.md`, `06_PLANTILLAS_PROMPTS_SKILLS.md` | Planes de creación de skills | `docs/skills/*` |
| `PROJECT_LOG_root_obsoleto.md` | Log divergente de la raíz (paró en Sesión 18) | `backend/PROJECT_LOG.md` |

### Eliminado
- `docs/tmp/*` — duplicados temporales (un ADR-001 duplicado y un borrador de cambios), sin valor histórico.

---

# 11 — Glosario

- **AI-nativo:** la IA opera el sistema vía capacidades invocables, no es un chatbot superpuesto.
- **MCP:** Model Context Protocol; servidores que exponen "tools" para que agentes operen el ERP.
- **Capability token:** credencial con scopes y expiración que autoriza a un agente sobre un tenant.
- **Event store:** registro de eventos de dominio (Redpanda) que nunca rompe la transacción de negocio.
- **DSL de personalización:** lenguaje declarativo (6 primitivas) para personalizar el sistema sin código.
- **Integration Hub:** punto único de toda integración externa (Odoo, BCV, Binance…).
- **CTF:** Compromiso Técnico Fechado (excepción a una regla con fecha de vencimiento y dueño).
- **Mode A / Mode B (CxC):** datasource Odoo (vía Hub) vs. datos nativos de Omni.
- **Aging / scoring (cobranza):** clasificación de cartera por antigüedad y priorización por score.
- **Bloque vs Fase vs Sub-fase:** Bloque = hito de negocio; Fase = hito técnico; Sub-fase/M# = unidad de ejecución.

---

*Documento consolidado a partir de: OMNI_ERP_MASTER_PLAN, OMNI_AI_NATIVE_EXECUTION_PLAN, 02_PLAN_EJECUCION_FOUNDER_SOLO, 01_MVP_SCOPE_NEGOCIOS_PILOTO, AGENTE_IA_PROTOCOLO_EJECUCION, PLAN_FASE1_DETALLADO, PLAN_TRABAJO_POST_AUDIT, PLAN_TRABAJO_COMPLETO, CXC-PLAN-IMPLEMENTACION, ADR-001…006, DIAGNOSTICO_INICIAL y ambos PROJECT_LOG. Verificado contra el estado real del código (37 apps, tag v0.1.0-phase0-complete, commit 463c502).*
*Próxima revisión: al cerrar la sub-fase 1.F (distribuidora en producción).*
