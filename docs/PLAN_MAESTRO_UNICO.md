# Omni ERP — Plan Maestro Único

**Versión:** 1.2 — Documento consolidado y única fuente de verdad
**Fecha de consolidación:** 2026-05-28 · **Última actualización integral:** 2026-06-21
(auditoría integral verificada contra el código: ver [`docs/AUDITORIA_2026-06-21.md`](AUDITORIA_2026-06-21.md);
auditoría previa archivada en [`docs/auditorias/archivo/AUDITORIA_INTEGRAL_2026-06-10.md`](auditorias/archivo/AUDITORIA_INTEGRAL_2026-06-10.md))
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
| **R-PROC-3** | Review humano en la puerta a producción | Todo PR `develop`→`main` requiere revisión humana del owner. **PRs a `develop` son autoaprobables con CI verde + gate completo** (un agente revisor distinto del autor revisa el diff antes de aprobar; autorizado por el owner 2026-06-11, ver `docs/FLUJO_DE_TRABAJO.md`). |
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

## 2.5 Gate de cierre (Definition of Done) — obligatorio

Ningún feature, fix o cambio está **terminado** hasta pasar el gate de cierre: **build
verde, tests verdes, revisión de seguridad, revisión de bugs, revisión de gaps y cero deuda
técnica nueva** (o un CTF fechado). El objetivo es que **cada avance quede 100 % sólido y no
haya que retroceder**.

El gate completo, con comandos y checklists, es de lectura obligatoria para todo agente y
vive en **[`docs/DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md)**. La puerta de entrada para
agentes es **[`CLAUDE.md`](../CLAUDE.md)** (y `AGENTS.md`) en la raíz del repo.

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
| Calidad | pytest + pytest-cov (**ratchet `--cov-fail-under=92`**, medido 93.25%), pre-commit (black, isort, flake8), mutation nightly (mutmut, ≥80% en 4 módulos críticos) | ✅ |

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
| Docker Compose prod (`docker-compose.prod.yml`) | ✅ + nginx reverse-proxy con rate limit y headers de seguridad (topología self-hosted) |
| **Deploy Railway (topología activa)** | ✅ `backend/Dockerfile` (con appuser non-root) + `frontend/Dockerfile.prod` + `frontend/nginx.conf` (Railway termina TLS upstream). PRs #3, #4, #5 — 2026-06-01 |
| CI/CD | ✅ GitHub Actions (`.github/workflows/ci.yml`): jobs backend, frontend, agent-eval |
| Monitoreo APM | ⚠️ Sentry configurado; Prometheus/Grafana pendiente |
| Backup automático PostgreSQL | ⚠️ `backup.yml` (pg_dump diario → S3) existe pero **se omite en silencio si falta el secret `BACKUP_DB_HOST`** — verificar secret + restore probado (GAP-4-bis, Plan 05 P1-7) |
| SSL automático (Let's Encrypt) | ⚠️ Railway: TLS upstream automático (cubierto). Self-hosted: diferido (GAP-5) hasta que el negocio justifique la migración |
| Security headers en nginx (Railway) | ✅ hecho — Django prod + nginx con CSP (ver `docs/planes/05-seguridad-hardening.md` #3) |

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
- **`apps/localizacion_ve/`** — app de localización Venezuela (antes llamada `vzla_localizacion`). Implementa los puertos para Venezuela (Capa A y Capa B). La lógica VE hoy dispersa (`apps/fiscal`, detección de IGTF en `apps/ventas`, métodos de pago IGTF, libros SENIAT, conector `tasas_ve` del Hub) se **migra gradualmente** hacia aquí dejando el core agnóstico. No se reescribe de golpe.
- **Futuras localizaciones** (Colombia DIAN/CUFE, México SAT/CFDI, Ecuador SRI, Perú SUNAT) son paquetes nuevos que implementan los mismos puertos. Ninguna toca el core.
- **Regla desde hoy:** todo módulo nuevo con lógica país-específica debe entrar por un puerto de localización, no hardcodear Venezuela. Esto evita aumentar el acoplamiento mientras se completa la extracción.

> Decisión formalizada en **[ADR-007](decisions/ADR-007-arquitectura-localizacion-dos-capas.md)** (aceptado 2026-06-01). Implementación actual: `apps/localizacion` (framework/registry, app instalada) + `apps/localizacion_ve` (paquete de adapters consumido vía el registry; **no** es app Django instalada).

## 3.8 Decisiones arquitectónicas (ADRs)

| ADR | Decisión | Estado |
|---|---|---|
| ADR-001 | PostgreSQL en servidor + offline-first en 3 niveles en clientes | ✅ |
| ADR-002 | Arquitectura modular + estrategia wedge (entrar por un dolor agudo) | ✅ |
| ADR-003 | Integration Hub centralizado con MCP bidireccional | ✅ |
| ADR-004 | Stack de agentes: Anthropic SDK directo (no LangChain/CrewAI/AutoGen) | ✅ |
| ADR-005 | DSL de personalización declarativo (no JSON Schema/Pydantic/parser propio) | ✅ |
| ADR-006 | Asientos contables automáticos (R-CODE-11) | ✅ |
| ADR-007 | **Arquitectura de localización de dos capas (legal + mercado), activable por empresa** | ✅ Aceptado 2026-06-01 |
| ADR-008 | Monorepo de clientes + shells mobile (RN/Expo) y desktop (Tauri 2) sobre la Capa 1 | ✅ |
| ADR-009 | Separar `cuentas_por_cobrar` (ledger) de `cxc` (cobranza IA) | ✅ Aceptado 2026-06-01 |
| ADR-010 | Extensibilidad y marketplace de extensiones | ✅ Aceptado 2026-06-12 |
| ADR-011 | Servicios hermanos / fábricas | ✅ Aceptado 2026-06-12 |
| ADR-012 | Modelo transaccional de venta POS offline | ✅ Aceptado 2026-06-19 (backend implementado) |

---

# 4 — Estado actual real del proyecto

> **Foto verificada contra el código el 2026-06-21** (rama `main`, auditoría integral con
> CODE_READERs por cluster + gate corrido localmente). Reemplaza la foto del 2026-06-10, que
> había quedado **pesimista**: varias capacidades marcadas "pendiente/parcial" estaban en
> realidad implementadas y testeadas. Detalle por feature: [`docs/AUDITORIA_2026-06-21.md`](AUDITORIA_2026-06-21.md).

## 4.1 Estado actual

- **Build:** `manage.py check` sin issues · `makemigrations --check` sin cambios pendientes.
- **Tests backend:** suite real en `backend/tests/` (capas unit/api/integration/tenant/e2e, ~188
  archivos). Corrida completa local 2026-06-21: **5224 passed, 19 skipped** (exit 0). Ratchet de cobertura
  `--cov-fail-under=92` (~92.97–94 %). *Nota:* `tests_api/` quedó casi vacío tras CTF-014 (migración por
  capas) — el comando canónico es `python -m pytest` (usa `testpaths`), no `tests_api/`.
- **Tests frontend:** Vitest + Testing Library, gate de cobertura de servicios; `decimal.js` en
  todos los flujos de pago/vuelto, totales de documentos y libros fiscales (FE-HIGH-7 cerrado).
- **Apps Django instaladas:** ~38 (+ `localizacion_ve` como paquete de adapters, no app instalada).
- **Fase 0 (Fundación AI-nativa): CERRADA.** Tag `v0.1.0-phase0-complete`.
- **Núcleo transaccional COMPLETO y endurecido:** ventas, compras, inventario, finanzas, fiscal VE,
  contabilidad, CxC/CxP, tesorería — con multi-tenant, Decimal, idempotencia en escrituras financieras.
- **Auditoría 2026-06-10 (workstream P0): CÓDIGO CERRADO** (PRs #64–#73). Verificado en disco que los
  fixes están presentes: fuga cross-tenant de métodos de pago tapada, `AbonoCxCViewSet` ya no es CRUD
  libre, pagos por API mueven saldos (service atómico + `select_for_update`), acuerdos acumulan
  `monto_pagado` con lock, conciliación con lock.
- **Planes C (consola SaaS C1–C3) y D (Cobranza standalone D1/D2/D4): completados.** Diferidos C4
  (billing) y D3 (push Odoo, CTF-011). Conector Google Sheets en el Hub.
- **Offline-first del POS (ADR-012 / CTF-008): base completa** — pull de catálogo, outbox idempotente
  del cliente y **endpoint atómico `POST /api/sync/push/ventas/`** (#171). Falta cerrar el ciclo en el
  frontend (encolar + flush al reconectar).

## 4.2 Módulos — estado verificado (CODE_READER 2026-06-21)

**✅ REAL_DONE (código + tests verificados en disco)**

- **Núcleo/plataforma:** `core` (Empresa/Sucursal/Usuario/Rol/Permiso/Contacto/CapabilityToken/
  Notificacion/base_models/MCP server/event store/`uuid7`), `configuracion_motor`, `saas` (middleware
  fail-open + planes), `integration_hub` (Odoo XML-RPC + **Google Sheets** + SyncEngine + checksum +
  Celery + MCP), `personalizacion` (DSL runtime), `agentes` (OmniAgente, niveles, PrediccionAgente,
  eval suite, clasificador de gastos, sugerencias diarias), `notificaciones`, `gestion_documental`.
- **Ciclo comercial:** `ventas` (Cotización→Pedido→NotaVenta→FacturaFiscal→NC/devoluciones, integrado
  stock+IVA/IGTF+asiento+CxC; **CxC única al facturar**, P0 verificado), `inventario` (kardex, tipos de
  movimiento, stock), `compras` (OC→Recepción→Factura + asientos), `crm`/`proveedores` (RIF), `finanzas`
  (Moneda/MetodoPago/Pago/PagoTercero/Cajas/TasaCambio/conversión/MCP), `fiscal` (IVA/IGTF config-driven,
  Libros SENIAT TXT+PDF), `contabilidad` (`generar_asiento()` en `@transaction.atomic`, R-CODE-11).
- **Cobranza/tesorería:** `cuentas_por_cobrar` (abono atómico con lock+tope, aging 5 tramos, scoring,
  PDF), `cuentas_por_pagar` (abonos, aging), `cxc` (GestionCobranza, AcuerdoPago/CuotaAcuerdo,
  fraccionamiento flag, agente IA SSE), `tesoreria` (conciliación con lock, import CSV, `OperacionCambioDivisa`).
- **RRHH/nómina — RECLASIFICADO ✅:** `nomina` **cálculo LOTTT completo** (`calculo_lottt.py`: ISLR por
  tramos, SSO/FAOV/RPE, provisiones utilidades/vacaciones/prestaciones art.142, aportes patronales),
  integrado en `procesar_proceso_nomina` con asiento contable y expuesto por MCP; `rrhh` (Empleado/Cargo/
  Beneficio/Licencia); `control_asistencia` (FK a Empleado, marcajes). *El plan anterior los marcaba
  parciales — es incorrecto.*
- **Manufactura/despacho — RECLASIFICADO ✅:** `manufactura` (13 modelos: BOM, rutas, OF con etapas,
  costeo; services 454 ln; 6 archivos de test) — **MRP/OF NO está pendiente**; `despacho` (services + PDF
  nota de entrega + tests). El plan anterior los marcaba 🔲.
- **Localización (framework):** `localizacion` instalada, con los 6 puertos ABC (`MotorImpuestos`,
  `GeneradorDocumentoLegal`, `CalculadoraNomina`, `LibroLegal`, `ProveedorTasas`, `MetodosPagoLocales`) +
  registry funcional que auto-registra VE. `eventos` (subsistema sin `models.py`, por diseño).

**🔶 PARCIAL (modelos/CRUD, sin capa de servicios completa o cobertura mínima)**
- `almacenes`, `costos`, `gastos` (con aislamiento), `servicio_cliente`, `migracion_datos` (4 importadores
  reales: clientes/productos/inventario/saldos CxC).
- `localizacion_ve` — solo **2 de 6 puertos** implementados (`MotorImpuestosVE`, `CalculadoraNominaVE`,
  como strangler-fig que delegan en `fiscal`/`nomina`). Faltan adapters de documento legal, libro legal,
  proveedor de tasas y métodos de pago.

**🔲 SCAFFOLD (estructura CRUD sin lógica de negocio ni tests propios)**
- `banca_electronica`, `integracion_b2b`, `gestion_aprobaciones`.

## 4.3 Deuda técnica activa (verificada en código)

> Solo deuda **real** que bloquea o degrada features. La deuda fechada vive en `docs/ctf/`
> (4 abiertos: **CTF-008** offline, **CTF-010** firma de apps, **CTF-011** push Odoo, **CTF-012** RLS;
> 11 cerrados). Inventario de baja/media en `docs/tech-debt/INVENTORY.md`.

**Hallazgos nuevos de esta auditoría — todos CERRADOS (loop autónomo 2026-06-22):**
- **✅ Cierre de período fiscal — RESUELTO.** `validar_periodo_abierto(empresa, fecha)` en
  `apps/fiscal/services.py` bloquea la emisión en un período cerrado (multi-tenant por `id_empresa`).
  Cubre **ventas** (factura fiscal, NC, devolución POS) y **compras** (`registrar_recepcion` y
  `registrar_factura_compra`, que postean asientos — PR #182). Antes `PeriodoFiscal.esta_cerrado()` era cosmético.
- **✅ `AbonoCxPViewSet`/`CuentaPorPagarViewSet` CRUD libre — RESUELTO (PR #183).** `http_method_names`
  limita a GET/POST → PUT/PATCH/DELETE devuelven 405; el saldo solo se mueve por la acción atómica
  `abonar` (`registrar_abono_cxp`). Espejo del fix P0 de CxC.
- **✅ CxP de compras re-vinculada a `FacturaCompra` — RESUELTO (PR #184).** Nuevo FK `CuentaPorPagar.id_recepcion`
  (ancla); `registrar_factura_compra` enlaza `id_factura_compra` al registrar la factura (idempotente, multi-tenant).
- **✅ `AsientoContable` con FK de usuario real — RESUELTO infra+compras (PR #185).** FK
  `id_usuario_registro → core.Usuarios` (reemplaza el UUID temporal); `generar_asiento[_o_fallar]` acepta
  `usuario` y el flujo de compras lo registra. *Pendiente incremental:* enhebrar `usuario` en los ~7 callers
  restantes (ventas/cxc/finanzas/fiscal/inventario/nómina/tesorería), 1 app por PR — sin regresión (hoy quedan `NULL`).
- **✅ `registrar_efectos_pago` con conversión FX — RESUELTO (PR #186).** Convierte el `monto_base_empresa`
  a la moneda base de la empresa vía `convertir_monto` (tasa BCV); sin tasa entre monedas distintas se rechaza
  (nunca 1:1). *Pendiente incremental:* mapear `TasaCambioError → 400` en `PagoViewSet`/POS y la misma
  simplificación en `apps/finanzas/models.py:595`.
- **🟢 `apps/cxc/mcp/__init__.py` vacío** — las tools MCP de cobranza viven en `core/mcp_server.py` (la
  descripción "MCP server propio de cxc" es imprecisa). `uuid7` sin test dedicado (cubierto transitivamente).

**Integration Hub — Fase 2 (inbound) y Fase 3 completadas (loop autónomo 2026-06-22):**
- **✅ Fase 2 inbound COMPLETA:** persistencia en Omni de las 7 entidades — contactos, productos,
  pedidos_venta, pedidos_compra, **facturas_venta** (`FacturaFiscal` + líneas, PR #187) y **pagos**
  (`finanzas.Pago`, cobros de cliente reconciliados a factura, *history-only* sin side-effects, PR #188),
  inventario. Detalle y límites en [`docs/integracion-hub/ESTADO.md`](integracion-hub/ESTADO.md).
- **✅ Fase 3:** registry **dinámico** (`ConectorProveedor.clase_conector` cargada vía `import_string`,
  sin re-desplegar; PR #189) + **conector genérico REST** config-driven (`GenericRestConnector`, PR #190).

**Deuda estructural ya conocida (vigente):**
- **Nómina:** el *cálculo* LOTTT está hecho; falta cestaticket multimoneda y casos LOTTT de borde + UI.
- **Backup automático PostgreSQL con restore probado** (P0-9, owner) · **SSL self-hosted** (diferido, GAP-5)
  · **Prometheus/Grafana** (Sentry ya está) · **Service Workers / offline real** en portales.
- **Acoplamiento a Venezuela en el núcleo:** lógica VE dispersa (`fiscal`, IGTF en `ventas`, libros SENIAT);
  migrar a `localizacion_ve` vía strangler-fig (4/6 puertos pendientes).
- **`saas` middleware fail-open** — revisar a fail-closed al activar `SAAS_VERIFICAR_SUSCRIPCION`.

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
├── 1.F Distribuidora en producción .......... ⬜ SIGUIENTE HITO (software listo; falta datos+operación)
├── 1.G Específicos distribuidora (POS,
│        comisiones, devoluciones, despacho) ... 🔶 backend hecho (despacho, NC, POS mostrador); falta UI táctil POS + offline
├── 1.H Onboarding fábrica + BOM ............. 🔶 BOM/modelos de manufactura hechos; falta carga de datos + UI
├── 1.I OF y costeo (manufactura) ............ 🔶 modelos OF/etapas/costeo hechos; falta services costeo real/MRP + UI etapas
└── 1.J Estabilización ....................... ⬜ pendiente
```

**Conclusión:** El núcleo común del MVP (1.A–1.E) está construido y endurecido, y **el backend de las
sub-fases 1.G–1.I también** (manufactura, despacho, POS, costeo — verificado 2026-06-21). **El trabajo
ya no es "construir más módulos en abstracto" — es poner la distribuidora a operar (1.F): carga de datos
reales + UI faltante + 30 días de operación.** Eso es lo que cumple R-PROC-8 y cierra el riesgo de
"60 módulos a medias".

## 5.1-bis Reglas de implementación autónoma

> Cómo un agente ejecuta un feature pendiente sin intervención humana salvo escalación.

1. **Unidad de trabajo = un feature** con criterio de done objetivo (un comando o test que pasa),
   no una fecha ni un sprint. Solo se marca DONE lo que un test/comando confirma en verde.
2. **Rama `feature/<slug>` desde `develop`** (feature nuevo) o `fix/<slug>` desde `main` (corrección/hotfix).
   Un feature **nunca** salta directo a `main`.
3. **PR en draft a `develop`** con el gate completo verde ([`DEFINITION_OF_DONE.md`](DEFINITION_OF_DONE.md)):
   build + tests + `/security-review` + `/code-review` + revisión de gaps + cero deuda nueva (o CTF fechado).
4. **Revisores:** `QA_AGENT` (correctness, casos borde, Decimal, atomicidad, N+1, tests) y `SEC_AGENT`
   (secretos, multi-tenant, authz, `str(e)`, inyección). Un agente revisor **distinto del autor** revisa
   el diff antes de aprobar (autorizado por el owner, R-PROC-3).
5. **Automerge a `develop` cuando CI está verde** y ambos revisores aprueban. El merge `develop`→`main`
   (producción) **siempre** requiere revisión humana del owner.
6. **Escalación a humano** solo tras **3 fallos** del mismo feature en CI/revisión, o si toca una acción
   exclusiva del owner (branch protection, secrets, RLS en prod, firma de apps, billing real).
7. **R-CODE/R-PROC son bloqueantes:** multi-tenant + test de aislamiento, Decimal, UUIDv7, soft delete,
   asiento automático, API-first (REST+MCP), sin secretos/`print`/`any`. Sin esto no hay merge.

## 5.2 Próximos pasos — roadmap consolidado hasta producto vendible

> **Consolidado 2026-06-10.** Esta sección absorbe y ordena TODO el trabajo pendiente declarado en:
> auditoría integral 2026-06-10, plan cero-dudas (Fases 4–5), planes 0/A/B/C/D/05 (`docs/planes/`),
> auditoría 2026-06-01 (su §11 frontend migra aquí como workstream F), CTFs abiertos y §5.2-bis/ter.
> Cada paquete = PRs pequeños y focales (R-PROC-2) que pasan el [gate completo](DEFINITION_OF_DONE.md).
>
> **Definición de "producto soñado listo para vender":** los workstreams P0 + 1.F + S1 + Q1 cerrados
> (seguro y operando con un cliente real) habilitan **vender a pilotos**; Bloque 2 (5+ clientes pagando,
> retención >70%) es el producto vendible a escala.

### P0 — Correcciones de auditoría 2026-06-10 — ✅ CÓDIGO CERRADO (2026-06-11)

> **Cierre 2026-06-11:** los 8 paquetes de código (P0-1…P0-8) están mergeados a `develop`
> con CI verde (PRs #64–#69, #72; extras #71 flaky-fix y #73 cierre de caja física).
> La auditoría se movió a `docs/auditorias/archivo/`. **Queda P0-9 (operativo, owner):**
> verificar el secret `BACKUP_DB_HOST` y probar un restore real.

Hallazgos verificados línea por línea — detalle y explotabilidad en
[`AUDITORIA_INTEGRAL_2026-06-10.md`](auditorias/archivo/AUDITORIA_INTEGRAL_2026-06-10.md). Orden por riesgo:

| # | PR (focal) | Contenido | DoD |
|---|---|---|---|
| P0-1 | `fix/finanzas-metodos-pago-tenant` | SEC-A1/A2/A3 + SEC-M2: quitar override de `get_object`, validar empresa destino contra `get_empresas_visible`, restringir `buscar_reutilizar` a `es_publico\|es_generico` con proyección de campos, `empresa` read-only en `MetodoPagoEmpresaActivaSerializer` | Tests cross-tenant: GET/POST con UUID/empresa ajena → 404/400; `buscar_reutilizar` no expone privados de terceros ni `documento_json`; gate completo verde |
| P0-2 | `fix/cxc-abonos-crud` | BUG-C1: `AbonoCxCViewSet` deja de ser CRUD libre — create delega en `registrar_abono` (atómico+lock+tope) validando tenant; update/delete bloqueados (anulación con proceso) | Test: abono por API actualiza saldo/estado; monto ≤0 o > saldo → 400; CxC ajena → 404; DELETE → 405 |
| P0-3 | `fix/finanzas-pagos-saldos` | BUG-C2 + BUG-A1: mover side-effects (TransaccionFinanciera + MovimientoCajaBanco + saldos) de `CajaFisicaViewSet` a un service invocado por `PagoViewSet`, con `transaction.atomic` + `select_for_update`; `transferencia_entre_cajas` atómica, con lock, validando monto>0, saldo y misma moneda | Test de integración: POST pago → transacción+movimiento+saldo correctos; POST caja física ya no 500; transferencia concurrente no pierde saldo; rollback total ante fallo a mitad |
| P0-4 | `fix/cxc-acuerdos-cuotas` | BUG-A2 + BUG-M3: acumular `monto_pagado` (no sobrescribir), `min_value` en monto, lock + check dentro de `atomic`, conversión de moneda pago→acuerdo, capear `generar_cuotas` al total y validar serializer (total>0, coherencia, tenant del FK `cxc`) | Tests: pagos parciales suman; doble pago concurrente → uno falla; 100 VES no saldan 100 USD; cuotas nunca exceden el total |
| P0-5 | `fix/ventas-cxc-duplicada` | BUG-A4: anular/reutilizar la CxC del pedido al facturar (no crear segunda); crear CxC en entrega de venta CONTADO con pedido no facturada (o decidir y documentar el flujo) | Test flujo crédito: 1 sola CxC por el total; test contado+pedido: CxC presente; `tests/e2e/test_e2e_ciclo_venta` sigue verde |
| P0-6 | `fix/serializers-fk-tenant` | SEC-M1 + SEC-B1 (sistémico): mixin que acota el queryset de toda FK tenant-aware a `get_empresas_visible`; extender guard TEST-1 a modelos "detalle" (FK a Empresa a 2 saltos) | Test paramétrico nuevo "POST con FK ajena → 400" sobre los ViewSets de escritura; guard estructural cubre detalle-ViewSets |
| P0-7 | `fix/fugas-y-comandos` | SEC-M3 + SEC-M4 + SEC-B2/B3: borrar/gatear `create_initial_data` (admin/admin123); `str(exc)`→mensaje genérico + `logger.exception` en integration_hub/cxc-agente/ventas/cuentas_por_cobrar; fix `fiscal/views.py:46` (`id__in`→`id_empresa__in`); validar `?empresa=` en `monedas_info` | Grep guard: 0 `str(exc)` en Responses; comando inseguro inejecutable en prod; tests de los 2 fixes puntuales |
| P0-8 | `fix/correctness-medios` | BUG-M1 (promedio nómina), BUG-M2 (N+1 saldos CxC → annotate), BUG-M4 (ventana de cierre de caja), BUG-M5 (lock en conciliación), BUG-A5 (eliminar código muerto `crear_transaccion_financiera_pago` o corregir la conversión + tests) | Tests unitarios de cada fix; aging sin N+1 (assertNumQueries) |
| P0-9 | Operativo (sin PR de código) | Sincronizar `develop` con `main` (6 commits); verificar secret `BACKUP_DB_HOST` y **probar un restore**; borrar `backend/db.sqlite3` y `sqlite-tools/` locales | `develop` == `main`; un backup nocturno real en S3 + restore documentado en runbook |

**DoD del workstream P0:** los 9 paquetes cerrados con gate completo; re-corrida de la suite de
aislamiento + los tests nuevos de FK-injection en verde; los ~30 bugs del backfill Fase 3 que
solapan con P0 quedan cubiertos y el resto triagéado en `docs/tech-debt/INVENTORY.md`.

### Orden maestro desde P0 (cada flecha = el anterior cierra su DoD)

```
P0 (auditoría, ~1-2 sem) ──→ 1.F Distribuidora en producción (30 días operando)
   ├─ en paralelo: S1 (Plan 05 P0/P1: RLS+CTF-012, throttling, idempotencia, axes, backups)
   ├─ en paralelo: Q1 (cero-dudas Fase 4: frontend 80% + E2E 5 flujos; Fase 5: gates bloqueantes + branch protection)
   └─ en paralelo: CTF-013 (cambio divisa + nómina procesar — solapa con P0-8/BUG-A3)
1.F cerrado ──→ 1.G POS distribuidora · 1.H BOM fábrica · 1.I OF+costeo · 1.J estabilización
   └─ transversales: l10n (§5.2-bis) · monorepo/shells (§5.2-ter, Plan B/CTF-010) · Plan A offline (CTF-008)
Bloque 1 cerrado (DoD: distribuidora 90d + fábrica 60d) ──→ BLOQUE 2: vender (5+ clientes, Plan C4 billing, S2/S3 hardening P2-P3)
```

### S1 — Seguridad para producción real (Plan 05, fases P0–P1) — detalle en [`planes/05-seguridad-hardening.md`](planes/05-seguridad-hardening.md)
- [ ] **CTF-012** (vence 2026-08-01): rol de BD no-dueño → `RLS_ENABLED=True` en staging→prod; extender RLS de 15 a ~92 tablas. **DoD:** RLS activo en prod, suite RLS verde, paths sin middleware fail-closed.
- [ ] P1: throttling DRF global · idempotencia de pagos · django-axes · revocación JWT · auditoría inmutable · pasada IDOR · backups con restore probado. **DoD:** cada ítem con test/verificación según el plan 05.

### Q1 — Calidad "cero dudas" Fases 4–5 — detalle en [`audit/ESTADO_PLAN_CERO_DUDAS.md`](audit/ESTADO_PLAN_CERO_DUDAS.md)
- [ ] Frontend 55%→80% (ratchet por escalones) + `eslint-plugin-security` (CTF-006, vence 2026-08-01) + decimal.js en flujo pago/vuelto (BUG-M6 / FE-HIGH-7).
- [ ] E2E Playwright de los 5 flujos críticos (hoy solo login smoke) → job bloqueante.
- [ ] Gates finales: trivy y schemathesis bloqueantes; `npm audit --audit-level=high` al cerrar CTF-007.
- [ ] **Branch protection en GitHub — acción exclusiva del owner (Marco).**
- **DoD Q1:** los 8 criterios de cierre del plan cero-dudas en 🟢.

### F — Workstream frontend (migrado de la auditoría 2026-06-01 §11, coordinar con Q1 para no duplicar)
- [ ] FE-CRIT-1: react-hook-form+zod en los 14 formularios restantes · FE-HIGH-13: JWT fuera de `localStorage` · FE-HIGH-11: interceptor 401+refresh · FE-HIGH-3/4/15: TanStack en páginas que aún usan `useEffect`+fetch · cola FE-MED/LOW (ver el plan archivado en [`auditorias/archivo/`](auditorias/archivo/PLAN_TRABAJO_AUDITORIA_2026-06-01.md) §11 como referencia de detalle).
- [ ] UI faltante para módulos API-only cuando un piloto la exija: compras, CxP, contabilidad, tesorería, RRHH/nómina (gap detectado 2026-06-10).

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

### 5.2-quater Desglose por capa de 1.F–1.I (GAP-3)

> La auditoría 2026-06-01 mostró que el plan estaba pesimista: hay capas
> (modelos, services, e incluso management commands) ya construidas. Se desglosa
> cada sub-fase en **datos / lógica (software) / UI / operación** para no
> declarar "pendiente" lo que ya existe.

| Sub-fase | Datos (carga) | Lógica / software | UI | Operación |
|---|---|---|---|---|
| **1.F** Caja + migración | ⬜ cargar reales | ✅ caja, fiscal, CxC + **commands TRACK-1F-1..5** (`apps/migracion_datos`) | ✅ (caja/factura) | ⬜ 30 días |
| **1.G** Devoluciones/POS | n/a | ✅ modelos devolución/NC; ✅ `apps/despacho` | ⬜ flujo POS táctil | ⬜ |
| **1.H** BOM | ⬜ cargar BOM | ✅ modelos `apps/manufactura` (ListaMateriales) | ⬜ UI + carga | ⬜ |
| **1.I** OF + costeo | ⬜ | ✅ modelos OF/costos; ⬜ services costeo real/MRP | ⬜ UI etapas | ⬜ |

Implicación: 1.F ya no requiere "construir software"; el trabajo es **carga de
datos reales + operación 30 días** (los importadores ya están, ver
`apps/migracion_datos/management/commands/`).

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

**Lo que un agente NO hace jamás:** mergear a `main` sin revisión humana, mergear a `develop` sin CI verde + revisión de otro agente, borrar datos sin proceso, saltarse el test de aislamiento, introducir SQLite, exponer secretos, llamar APIs externas fuera del Integration Hub, ampliar alcance sin cerrar un flujo.

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
│   ├── tests/           suite por capas: unit, integration, tenant, api, e2e (+factories)
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
| `CLAUDE.md` / `AGENTS.md` | Puerta de entrada para agentes (reglas + gate + flujo) |
| `docs/DEFINITION_OF_DONE.md` | Gate de cierre obligatorio (R-PROC-*) |
| **`docs/FLUJO_DE_TRABAJO.md`** | Branching + despliegue (feature→develop→main; fix→main) |
| `docs/DESPLIEGUE_RAILWAY.md` | Topología y despliegue en Railway (prod + staging) |
| `backend/PROJECT_LOG.md` | Registro cronológico de sesiones (append-only, inmutable) |
| **`docs/planes/*`** | Planes de ejecución que aterrizan este roadmap (0/A/B/C/D/05 + runbook piloto) |
| `docs/PLAN_AUDITORIA_Y_TESTING_CERO_DUDAS.md` | Plan de calidad "cero dudas"; su estado vive en `docs/audit/ESTADO_PLAN_CERO_DUDAS.md` |
| `docs/decisions/ADR-*.md` (001–009, todos aceptados) | Decisiones arquitectónicas |
| `docs/ctf/*` | Compromisos técnicos fechados (R-PROC-6) — único registro de deuda con fecha |
| `docs/skills/*` | Skills del proyecto (incl. `diagnostico-railway` — diagnóstico read-only) |
| `docs/auditorias/*` | Auditoría **activa** en la raíz (hoy: ninguna — P0 cerrado 2026-06-11); cerradas en `archivo/` |
| `docs/audit/*` | Artefactos del plan cero-dudas: estado vivo + mapas A1 auto-generados (`mapa_superficie`) + reportes A2/A3 |
| `docs/tech-debt/INVENTORY.md` | Deuda baja/media sin fecha (la fechada va a CTF) |
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
| `AUDITORIA_2026-06-02.md` | Auditoría integral 2026-06-02 (Olas 1–5 resueltas y verificadas) | histórico; estado vigente en §4 |
| `RAILWAY_TROUBLESHOOTING_2026-06-03.md` | Troubleshooting puntual de Railway | `docs/DESPLIEGUE_RAILWAY.md` |

### Eliminado
- `docs/tmp/*` — duplicados temporales (un ADR-001 duplicado y un borrador de cambios), sin valor histórico.
- `docs/_staging_smoke.md` — marcador de prueba del pipeline de staging (sin valor).

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
*Revisión integral 2026-06-21 (auditoría verificada contra el código, CODE_READERs por cluster; ver [`docs/AUDITORIA_2026-06-21.md`](AUDITORIA_2026-06-21.md)). Próxima revisión: al cerrar la sub-fase 1.F (distribuidora en producción) o al cerrar un CTF abierto.*
