# Cambios a Aplicar — Documentos del Proyecto

**Propósito:** especificación exacta de los cambios a hacer en los documentos existentes del proyecto. Para que el agente los aplique sin ambigüedad.

---

## Cambio 1: Agregar Propiedad Irrenunciable #6 al plan v2.0

**Archivo:** `docs/02_PLAN_EJECUCION_FOUNDER_SOLO.md`
**Sección a modificar:** PARTE I — La Visión Perpetua, sección 1.2 "Las cinco propiedades irrenunciables del producto"

**Acción:** cambiar el título de la sección de "cinco" a "seis" y agregar la propiedad #6.

### Texto actual a buscar

```markdown
## 1.2 Las cinco propiedades irrenunciables del producto

1. **Conversacional primero, no como añadidura.**
2. **Determinista donde la ley lo exige, agéntico donde el juicio paga.**
3. **Personalizable por conversación, no por consultoría.**
4. **Cada empresa es potencialmente un emisor de software.**
5. **Localización y regulación son ciudadanos de primera clase.**
```

### Texto nuevo (reemplazar el anterior)

```markdown
## 1.2 Las seis propiedades irrenunciables del producto

1. **Conversacional primero, no como añadidura.**
2. **Determinista donde la ley lo exige, agéntico donde el juicio paga.**
3. **Personalizable por conversación, no por consultoría.**
4. **Cada empresa es potencialmente un emisor de software.**
5. **Localización y regulación son ciudadanos de primera clase.**
6. **Resiliencia ante conectividad inestable.** El sistema opera funciones esenciales sin conexión donde la realidad operativa lo requiere. Tres niveles: (1) caché agresivo en todos los clientes; (2) offline-first operativo en módulos críticos (POS, vendedores en calle, captura en planta, kioscos); (3) versión lite para zonas sin conectividad confiable, activable por tenant. El servidor sigue siendo PostgreSQL; el offline vive en los clientes con sincronización diferida via event sourcing.
```

---

## Cambio 2: Agregar referencia al ADR-001 en la sección de Decisiones Inmutables

**Archivo:** `docs/02_PLAN_EJECUCION_FOUNDER_SOLO.md`
**Sección a modificar:** APÉNDICE A — Decisiones Inmutables (si existe en v2.0; si no, agregar)

**Acción:** agregar entrada en la tabla de decisiones inmutables.

### Texto a agregar (al final de la tabla)

```markdown
| A-021 | Postgres en servidor + offline-first en clientes (3 niveles) | Diferenciación competitiva en VE/Latam; objeción de venta común resuelta. | [Fecha de aplicación] |
```

**Si el Apéndice A no existe en v2.0** (porque heredó del v1), entonces hacer referencia al Apéndice A del v1 y agregar la decisión A-021 ahí.

---

## Cambio 3: Actualizar la regla R-CODE-2

**Archivo:** `docs/02_PLAN_EJECUCION_FOUNDER_SOLO.md`
**Sección a modificar:** PARTE II — Reglas Inviolables, R-CODE-2

**Acción:** reemplazar el texto de la regla para que sea más preciso.

### Texto actual a buscar

```markdown
### R-CODE-2: Sin SQLite en ningún entorno
Desarrollo, staging, producción: PostgreSQL. La diferencia en comportamiento de constraints parciales y transacciones ya costó bugs documentados. SQLite no vuelve a entrar.
```

### Texto nuevo (reemplazar)

```markdown
### R-CODE-2: PostgreSQL en servidor, sin SQLite en backend
Desarrollo, staging, producción del **servidor**: PostgreSQL. La diferencia en comportamiento de constraints parciales y transacciones ya costó bugs documentados. SQLite no vuelve a entrar al backend.

**Excepción explícita:** SQLite-as-local-storage en el cliente (apps móviles nativas para almacenamiento local offline-first) es aceptable, porque no es la BD del servidor. Ver ADR-001 para arquitectura completa. IndexedDB es la opción default para clientes web/PWA.
```

---

## Cambio 4: Agregar kioscos al MVP Scope

**Archivo:** `docs/01_MVP_SCOPE_NEGOCIOS_PILOTO.md`
**Sección a modificar:** PARTE 5 — Lo que es específico de cada uno, subsección 5.1 (específicos de la distribuidora)

**Acción:** agregar fila a la tabla de capacidades específicas.

### Texto actual a buscar

```markdown
## 5.1 Específicos de la distribuidora (entran primero, son más simples)

| # | Capacidad | Por qué primero |
|---|-----------|-----------------|
| 1 | POS ágil para mostrador con código de barras | Es uso diario, frecuente, alto valor. |
| 2 | Vendedores con comisión por cobranza | Necesario si tienen vendedores |
| 3 | Notas de crédito y devoluciones | Frecuente en distribución |
| 4 | Despacho con guía y manejo de flota mínimo | Si despachan al mayorista |
| 5 | Conteo cíclico guiado | Para conciliar inventario |
```

### Texto nuevo (reemplazar)

```markdown
## 5.1 Específicos de la distribuidora (entran primero, son más simples)

| # | Capacidad | Por qué primero |
|---|-----------|-----------------|
| 1 | POS ágil para mostrador con código de barras | Es uso diario, frecuente, alto valor. |
| 2 | POS en modo kiosco autoservicio para clientes finales | Diferenciación; misma arquitectura del POS con perfil distinto |
| 3 | Vendedores con comisión por cobranza | Necesario si tienen vendedores |
| 4 | Notas de crédito y devoluciones | Frecuente en distribución |
| 5 | Despacho con guía y manejo de flota mínimo | Si despachan al mayorista |
| 6 | Conteo cíclico guiado | Para conciliar inventario |

**Sobre el modo kiosco autoservicio (capacidad 2):**

El POS no se construye dos veces. Se construye una vez con perfiles configurables:

- **Perfil "mostrador":** uso por personal de la distribuidora. Acceso a precios, descuentos, modificaciones, devoluciones.
- **Perfil "kiosco cliente":** el cliente mayorista (dueño de bodega/colmado) se loguea con su RIF/cédula. Ve solo su catálogo, sus precios negociados, su estado de cuenta. Puede hacer pedidos, ver historial, cargar comprobantes de pago. No puede modificar precios ni ver datos de otros clientes.

**Por qué esto importa:**
- Permite a distribuidoras ofrecer autoservicio a sus mejores clientes (menos cola, mejor experiencia).
- Es ventaja competitiva real frente a Odoo/Fina.
- Sienta arquitectura para el caso futuro de "app del cliente final" si se decide construir.
- Cero costo adicional de construcción si se planifica desde el inicio del POS.

**Cuándo:** mes 8-9 (después de validar el POS modo mostrador en mes 7).
```

---

## Cambio 5: Actualizar la sección de hitos del año 1

**Archivo:** `docs/02_PLAN_EJECUCION_FOUNDER_SOLO.md`
**Sección a modificar:** PARTE V — Mes a Mes del Año 1, sección 5.7 "Hitos del año 1 resumidos"

**Acción:** agregar hito relacionado con offline-first en el mes correspondiente.

### Texto actual a buscar (la tabla de hitos)

```markdown
| Mes | Hito | Riesgo principal |
|-----|------|------------------|
| 1 | Fundación técnica sólida | Que la deuda técnica te tome 2 meses en lugar de 1 |
| 3 | Ciclo comercial completo en sistema | Errores fiscales VE |
| 5 | Agentes operando, personalización Capa 1-2 | Costo de inferencia descontrolado |
| 6 | Distribuidora operando 30 días continuos | Migración de datos sale mal |
| 9 | Distribuidora completa (con POS, comisiones, despacho) | Que aparezca un bug crítico que tumbe la operación |
| 12 | Fábrica con OF y BOM | Complejidad de manufactura subestimada |
| 15 | Ambos negocios operando con sistema completo | Burnout |
```

### Texto nuevo (reemplazar)

```markdown
| Mes | Hito | Riesgo principal |
|-----|------|------------------|
| 1 | Fundación técnica sólida + Service Workers básicos (Nivel 1 offline) | Que la deuda técnica te tome 2 meses en lugar de 1 |
| 3 | Ciclo comercial completo en sistema | Errores fiscales VE |
| 5 | Agentes operando, personalización Capa 1-2 | Costo de inferencia descontrolado |
| 6 | Distribuidora operando 30 días continuos | Migración de datos sale mal |
| 7 | POS distribuidora con código de barras (Nivel 2 offline) | Sincronización de eventos no resuelta bien |
| 8-9 | POS modo kiosco autoservicio + vendedores comisión + despacho | Que el modo kiosco confunda a los clientes |
| 12 | Fábrica con OF y BOM | Complejidad de manufactura subestimada |
| 15 | Ambos negocios operando con sistema completo | Burnout |
```

---

## Cambio 6: Agregar nota sobre la idea Cashea al Apéndice C (Norte Estrella)

**Archivo:** `docs/02_PLAN_EJECUCION_FOUNDER_SOLO.md`
**Sección a modificar:** APÉNDICE C — Norte Estrella, sección C.1 "La Visión a 10+ Años"

**Acción:** agregar al final de la lista actual una idea adicional con su nota de advertencia.

### Texto a agregar (al final de la lista de C.1)

```markdown
8. **Plataforma de crédito al consumidor a través de la red de bodegas** (modelo Cashea, pero diferenciado). En estado maduro, la red de bodegas que usan Omni podría ofrecer crédito al consumidor final con scoring basado en historial real de consumo, en partnership con un proveedor financiero regulado. Omni cobra fee de plataforma, no spread financiero.

**ADVERTENCIA EXPLÍCITA SOBRE ESTA IDEA:**

Esta idea tiene mucho upside pero también riesgos enormes. Antes de cualquier movimiento en esta dirección:

- Omni NO debe convertirse en empresa financiera ni dar crédito propio. El crédito debe darlo un partner regulado.
- Requiere masa crítica significativa (estimado: 50+ distribuidoras con sus bodegas usando Omni) antes de tener relevancia para un partner financiero.
- Requiere análisis legal-fiscal venezolano profundo antes de cualquier paso.
- NO entra al plan de Bloques 1, 2, ni 3.A. Solo se considera en Bloque 3.B o posterior, y solo si hay tracción que lo justifique.

Lo que SÍ se puede hacer ahora para preparar el camino sin pavimentarlo:
- Modelar las bodegas como tenants potenciales de Omni (no solo clientes de la distribuidora).
- Diseñar el módulo de clientes finales pensando en posible identidad cross-tenant futura.
- NO construir nada de la app del consumidor final. Solo asegurar que la arquitectura no lo prohíba.
```

---

## Cambio 7: Crear índice de ADRs

**Archivo nuevo:** `docs/decisions/README.md`

**Acción:** crear archivo con el índice de Architectural Decision Records.

### Contenido del archivo

```markdown
# Architectural Decision Records (ADRs)

Esta carpeta contiene las decisiones arquitectónicas mayores del proyecto Omni AI-Native, documentadas según el patrón ADR.

## Cuándo se crea un ADR

Se crea un ADR cuando se toma una decisión que:
- Afecta el comportamiento futuro del sistema en formas difíciles de revertir.
- Establece un patrón que se va a aplicar en muchos lugares.
- Resuelve una tensión o duda significativa que apareció en el proyecto.
- Es Nivel 3 del árbol de decisiones del plan operativo.

## Índice

| # | Título | Fecha | Estado |
|---|--------|-------|--------|
| 001 | PostgreSQL en Servidor + Offline-First en Clientes | [Fecha] | Aceptado |

## Cómo se escriben

Ver plantilla en el plan operativo del proyecto, Apéndice B.2.

## Cómo se revisitan

Los ADRs se revisan en cada checkpoint trimestral. Si una decisión necesita cambiar, se crea un ADR nuevo que la reemplaza explícitamente; no se modifica el ADR original (es histórico).
```

---

## Resumen de archivos afectados

1. **Crear:** `docs/decisions/ADR-001-postgres-server-offline-clients.md` (contenido completo en archivo separado).
2. **Crear:** `docs/decisions/README.md` (contenido arriba).
3. **Modificar:** `docs/02_PLAN_EJECUCION_FOUNDER_SOLO.md` (cambios 1, 2, 3, 5, 6).
4. **Modificar:** `docs/01_MVP_SCOPE_NEGOCIOS_PILOTO.md` (cambio 4).

Total: 2 archivos nuevos, 2 modificaciones.

---

## Verificación post-aplicación

Después de aplicar los cambios, verificar:

- [ ] El archivo ADR-001 existe en `docs/decisions/`.
- [ ] El README de decisions existe y referencia el ADR-001.
- [ ] El plan v2.0 sección 1.2 menciona 6 propiedades (no 5).
- [ ] La regla R-CODE-2 menciona explícitamente la excepción de cliente local.
- [ ] El MVP scope tiene 6 capacidades en sección 5.1 (no 5).
- [ ] El kiosco autoservicio está documentado con su justificación.
- [ ] La tabla de hitos del año 1 incluye los nuevos items relacionados con offline-first.
- [ ] El Apéndice C tiene la idea de Cashea con su advertencia.

Si algo no coincide, revertir y consultar antes de seguir.
