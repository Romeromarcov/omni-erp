# ADR-001: PostgreSQL en Servidor + Offline-First en Clientes

**Estado:** Aceptado
**Fecha:** [Fecha de aplicación]
**Autor:** Responsable del proyecto + asesoría externa
**Categoría:** Arquitectura fundacional

---

## Contexto

Durante la fase inicial del proyecto, surgió una preocupación legítima sobre cómo el sistema debe operar en condiciones de conectividad inestable, que es la realidad de Venezuela y de muchas zonas de Latam.

La preocupación inicial planteó si la migración a PostgreSQL (regla R-CODE-2 del proyecto) era compatible con la necesidad de operación offline. Específicamente, si "offline-first" requería usar SQLite localmente en lugar de PostgreSQL.

Después de análisis, se identificó que **offline-first y "tipo de BD del servidor" son problemas independientes** que se confunden frecuentemente.

Adicionalmente, la realidad operativa de los negocios target (especialmente en VE) muestra tres escenarios distintos de conectividad que requieren tratamiento diferenciado:

1. **Negocios con conexión razonable en oficina pero no en planta/galpón** (típico de fábricas).
2. **Negocios en zonas con conexión muy inestable o ausente** (típico de comercio en interior del país).
3. **Cualquier negocio puede sufrir cortes temporales de internet** (caída del proveedor, problemas eléctricos).

La barrera de adopción de sistemas 100% online (Odoo SaaS, Fina, Holded, etc.) en VE/Latam es real y documentada: los dueños de pymes desconfían por la inestabilidad del servicio. Esta es una **oportunidad de diferenciación competitiva**, no solo una restricción técnica.

---

## Decisión

### Arquitectura de dos capas independientes

**Capa de servidor (backend):**
- PostgreSQL como única base de datos del servidor.
- Multi-tenant Row-Level con `id_empresa`.
- Event sourcing como verdad de los eventos de negocio.
- Sin excepciones: no se usa SQLite en servidor en ningún entorno.

**Capa de cliente (frontend, móvil, POS):**
- Almacenamiento local apropiado al contexto: IndexedDB (web/PWA), SQLite-as-local-storage (móvil nativo si aplica).
- Service Workers para caché agresivo.
- Sincronización diferida con el servidor cuando hay conexión.
- Tres niveles de resiliencia según necesidad operativa del módulo.

### Los tres niveles de resiliencia

**Nivel 1 — Resiliencia básica (todos los clientes, desde el día 1).**

El cliente cachea agresivamente datos recientes. Ante cortes de minutos:
- El usuario puede seguir consultando lo que ya cargó.
- Las acciones que requieren servidor (crear, modificar, sincronizar agentes) muestran indicador claro y se reintentan al volver conexión.
- No requiere arquitectura adicional, solo buen uso de Service Workers + cache HTTP.

**Nivel 2 — Offline-first operativo (módulos críticos).**

Módulos diseñados para operar sin conexión por horas, con sincronización diferida:
- POS de mostrador.
- App de vendedores en calle.
- Captura de avance de OF en planta industrial.
- Kioscos de autoservicio para clientes finales.

Características:
- Réplica local de datos relevantes (catálogo, precios, clientes asignados, stock al último sync).
- Cola de operaciones pendientes (ventas, cobros, registros).
- Sincronización oportunista al detectar conexión.
- Resolución de conflictos basada en event sourcing (cliente emite eventos locales, servidor reconcilia).
- UI clara que indica estado online/offline.

**Nivel 3 — Versión lite (zonas sin conectividad confiable).**

Subset funcional completo que opera durante días sin conexión:
- Mismo codebase que la versión completa.
- Modo activado por configuración del tenant.
- Funciones disponibles: vender, consultar stock, cobrar, imprimir, tomar pedidos, consultar clientes y saldos.
- Funciones NO disponibles offline: personalización conversacional (requiere LLM), agentes IA, conciliación bancaria automática, sincronización con servicios externos en tiempo real, reportes que requieren cálculo de servidor.
- Sincronización cuando se conecta (puede ser horas o días después).

### Resolución de conflictos en sincronización

Cuando el cliente sincroniza eventos generados offline, pueden surgir conflictos. Estrategia:

- **Default:** event sourcing con timestamps lógicos. Los eventos del cliente se aplican en orden de generación local, validándose contra reglas de negocio en el servidor.
- **Stock:** si dos clientes vendieron el mismo producto que ya no había en stock real, prioriza el evento más antiguo y genera alerta de discrepancia para revisión humana.
- **Numeración fiscal:** los números fiscales se reservan en bloques al cliente offline. Cuando sincroniza, los usa en orden. Si dos clientes recibieron el mismo bloque por error, el sistema detecta y alerta (no debería pasar con buen diseño).
- **Cambios al mismo registro:** last-write-wins por default, con auditoría de qué se sobrescribió.

### Cuándo se construye cada nivel

**Nivel 1:** desde Fase 0. Es propiedad transversal del frontend.

**Nivel 2:** en cada módulo que lo requiera. Cronograma estimado:
- POS distribuidora: mes 7.
- Modo kiosco autoservicio: mes 8-9.
- App vendedores en calle: mes 9.
- Captura de OF en planta: mes 11-12.

**Nivel 3:** cuando aparezca el primer cliente concreto que lo necesite. Estimado: mes 12+. **No se construye especulativamente.**

---

## Por qué se decidió así (razones específicas)

### Por qué Postgres en servidor (no SQLite)

1. **Bugs documentados.** El proyecto Omni original (ver Master Plan sección 2.3, bugs corregidos) sufrió problemas por diferencias entre SQLite y Postgres. Mantener Postgres elimina esa categoría de bugs.

2. **Concurrencia real.** Multi-tenant + multi-usuario simultáneos requiere las garantías de Postgres (MVCC, locks granulares).

3. **Tipos avanzados.** El proyecto va a usar JSON fields para personalización, posiblemente tipos array y custom, que SQLite no soporta robustamente.

4. **Replicación y backup.** Postgres tiene ecosistema maduro para backup, replicación, recovery. SQLite no es solución para SaaS multi-tenant.

5. **Performance bajo carga.** Cuando el proyecto crezca a decenas o cientos de clientes, SQLite no escala.

### Por qué offline-first en clientes (no servidor monolítico distribuido)

1. **Realidad operativa de VE/Latam.** La conectividad inestable no es excepción, es norma. Construir alrededor de eso es necesario.

2. **Diferenciación competitiva.** Odoo, Fina, Holded son 100% online. La objeción de venta más común en VE es "y si se va el internet". Tener respuesta concreta es ventaja real.

3. **Complejidad acotada.** Sincronización de eventos cliente→servidor es complejo pero conocido. Distribución verdadera (servidor distribuido replicado en cada cliente) es exponencialmente más complejo y no necesaria para los casos de uso.

4. **Costo razonable.** Implementar bien Nivel 1 y Nivel 2 son trabajo de semanas, no años. Nivel 3 es trabajo de meses cuando llegue el momento.

### Por qué no se construye Nivel 3 ahora

1. **Los pilotos no lo necesitan.** Ambos negocios familiares tienen conexión razonable en oficina. El POS de la distribuidora puede usar Nivel 2.

2. **Es complejidad sin cliente concreto.** Construir Nivel 3 antes de tener cliente que lo pida es especulativo.

3. **La arquitectura permite agregarlo después.** Con event sourcing y Nivel 2 bien hechos, agregar Nivel 3 es extensión, no rediseño.

---

## Alternativas consideradas

### Alternativa A: SQLite en servidor (rechazada)
Razones del rechazo: incompatible con multi-tenant SaaS serio, bugs documentados, no escala.

### Alternativa B: Sistema 100% online sin offline (rechazada)
Razones del rechazo: pierde la oportunidad de diferenciación en VE/Latam, no resuelve la objeción de venta más común.

### Alternativa C: Distribución completa (replicación maestro-maestro de servidor en cada cliente) (rechazada)
Razones del rechazo: complejidad exponencialmente mayor, no necesaria para los casos de uso reales, ningún sistema empresarial serio lo hace así para multi-tenant.

### Alternativa D: Híbrido CouchDB / PouchDB (considerada, no elegida)
CouchDB + PouchDB tiene buena historia para offline-first nativo. Razones por las que no se eligió:
- Migración del stack actual sería brutal (Django + Postgres ya existe).
- Modelo de documentos no encaja bien con la naturaleza relacional de un ERP.
- Comunidad y mantenimiento más débil que Postgres.
- Podría reconsiderarse para módulos específicos en el futuro si vale la pena.

---

## Consecuencias

### Positivas

- **Diferenciación competitiva clara** en VE/Latam frente a competidores 100% online.
- **Servidor sólido y simple** sin las complicaciones de SQLite multi-tenant.
- **Flexibilidad de construir resiliencia gradualmente** según necesidad real de cada módulo.
- **Compatibilidad con la arquitectura event-sourced** ya planificada.
- **Las objeciones de venta** sobre "y si se va el internet" tienen respuesta concreta.

### Negativas

- **Complejidad adicional en módulos offline-first.** Cada módulo Nivel 2 requiere lógica de sincronización, manejo de conflictos, testing offline.
- **Sincronización es difícil de debuggear.** Bugs en sync son los más complejos de reproducir.
- **Storage local del cliente tiene límites.** IndexedDB tiene cuotas; hay que diseñar qué se cachea y qué no.
- **UX más compleja.** El usuario debe entender el estado online/offline. Indicadores claros son críticos.

### Neutras

- El servidor debe ser diseñado para tolerar batches grandes de eventos (cliente sincronizando 8 horas de operación de golpe).
- El frontend debe manejar Service Workers, lo cual añade complejidad técnica pero ya es estándar en web moderna.

---

## Cómo revisitar esta decisión

Esta decisión debería reconsiderarse si:

- Aparece un módulo donde Nivel 2 no es suficiente y se necesita lógica más sofisticada (multi-master, real-time collaboration tipo Google Docs).
- La regulación venezolana exige replicación en territorio nacional o data sovereignty que cambie el modelo.
- Un cliente piloto demuestra que su realidad operativa es radicalmente distinta a la asumida.

En cualquier caso, **modificar esta decisión requiere ADR nuevo que la reemplace explícitamente**, no cambios incrementales silenciosos.

---

## Tareas relacionadas

- Agregar Propiedad Irrenunciable #6 al `02_PLAN_EJECUCION_FOUNDER_SOLO.md`.
- Actualizar `01_MVP_SCOPE_NEGOCIOS_PILOTO.md` con kioscos de autoservicio.
- Diseñar Service Workers básicos durante Fase 0 (Nivel 1).
- Planificar arquitectura de sincronización antes de empezar el POS (mes 6).

---

## Referencias

- Master Plan sección 2.3: bugs documentados por diferencias SQLite/Postgres.
- Regla R-CODE-2: no SQLite en servidor.
- Plan v2.0 sección 1.2: propiedades irrenunciables del producto.
- Discusión externa con asesor: análisis de competidores en VE/Latam y barreras de adopción.

## Changelog

### v1.0 — [Fecha]
- Versión inicial. Decisión tomada y documentada.
