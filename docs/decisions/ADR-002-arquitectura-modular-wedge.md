# ADR-002: Arquitectura Modular y Estrategia Wedge

**Estado:** Aceptado
**Fecha:** 2026-05-14
**Autor:** Responsable del proyecto
**Categoría:** Arquitectura y comercialización
**Reemplaza:** ninguno
**Relacionado con:** ADR-003 (Integration Hub), ADR-004 (gestion-cxc-V2 como primer standalone)

---

## Contexto

Durante la planificación del proyecto, surgió una decisión estratégica importante sobre cómo comercializar Omni. Hay dos modelos posibles:

**Modelo monolítico:** Omni se vende como producto único. El cliente compra "el ERP completo" y se compromete a migrar todo su sistema actual.

**Modelo modular/wedge:** ciertos módulos de Omni se pueden vender por separado, integrándose al ERP existente del cliente. Esto baja la barrera de entrada y permite captar clientes que no están listos para reemplazar todo su sistema.

La realidad de venta de ERPs en Latam confirma que la barrera de entrada de cambiar de sistema es enorme. Una pyme con Profit, Odoo, SAP B1 o sistemas similares funcionando es muy difícil de convencer para cambiar completo. Pero sí puede aceptar agregarle a su sistema actual una pieza que le resuelva un dolor específico.

Adicionalmente, esta estrategia tiene beneficio inmediato: el responsable del proyecto tiene acceso a una empresa donde trabaja como gerente, que potencialmente adoptaría Omni Cobranza standalone como primer cliente externo. Eso es un wedge real, no hipotético.

---

## Decisión

**Adoptar estrategia de comercialización híbrida con dos modalidades:**

1. **Omni ERP completo:** producto principal, vendido como SaaS integrado. Reemplaza completamente al ERP anterior del cliente.

2. **Productos Omni standalone:** módulos específicos vendidos por separado, integrables al ERP existente del cliente vía Integration Hub (ver ADR-003).

**Adicionalmente, todos los módulos de Omni se construyen con principios modulares desde el día 1**, aunque la mayoría se entreguen solo como parte del ERP integrado.

---

## Clasificación de módulos

Los módulos se clasifican en tres categorías según su potencial standalone:

### Categoría A — Núcleo del ERP (NUNCA standalone)

Estos módulos son el corazón del ERP. Venderlos sueltos genera conflictos con el sistema principal del cliente.

- Catálogo de productos, clientes, proveedores.
- Inventario y movimientos.
- Facturación fiscal (Venezuela y otros países).
- Cuentas por cobrar y por pagar (a nivel transaccional).
- Caja diaria.

**Razón:** estos módulos definen el corazón del sistema. Tener dos sistemas haciendo lo mismo (Omni y el ERP del cliente) es ingobernable.

### Categoría B — Candidatos a standalone (potencial wedge)

Estos módulos resuelven dolores específicos que pueden vivir en paralelo a un ERP existente.

- **Cobranza inteligente** (Omni Cobranza): persecución de CxC, agentes de cobranza automatizados, scoring de cobrabilidad. **Primer standalone confirmado.**
- **Logística inteligente** (Omni Routes): packing lists, optimización de rutas, app de chofer.
- **Conciliación bancaria automatizada** (Omni Conciliación): procesamiento de extractos bancarios.
- **Personalización conversacional** (Omni Adapt): el DSL de personalización Capa 3-4 como producto separable.
- **POS y kioscos especializados** (Omni POS): para retail que ya tiene ERP pero quiere mejor experiencia en punto de venta.

**Razón:** estos módulos agregan capacidades nuevas que no necesariamente compiten con lo que el ERP del cliente ya hace. Son extensiones, no reemplazos.

### Categoría C — Ambivalentes (decisión caso por caso)

Estos módulos pueden ir en cualquiera de las dos categorías según el contexto.

- CRM.
- Reportes y BI.
- Manufactura/BOM.

**Razón:** dependen mucho del cliente. Algunos clientes ya tienen CRM funcionando y no quieren reemplazarlo; otros no tienen CRM y aceptarían el de Omni standalone.

---

## Arquitectura técnica de un módulo modular

Todo módulo de Omni, sin importar su categoría, se construye con esta arquitectura de tres capas:

```
┌─────────────────────────────────────────────┐
│ Capa 1 — Core de dominio                    │
│ Lógica de negocio pura                       │
│ Modelos canónicos                            │
│ Servicios sin acoplamiento al data source    │
└─────────────────────────────────────────────┘
            ↓                    ↓
┌──────────────────────┐ ┌──────────────────────┐
│ Capa 2A — Shell      │ │ Capa 2B — Shell      │
│ Integrado en Omni    │ │ Standalone           │
│                      │ │                      │
│ Lee de modelos Omni  │ │ Lee de su BD propia, │
│ vía service layer    │ │ sincronizada con ERP │
│                      │ │ destino vía Hub      │
└──────────────────────┘ └──────────────────────┘
                              ↓
                        ┌──────────────────────┐
                        │ Capa 3 — Integration │
                        │ Hub                  │
                        │ (Ver ADR-003)        │
                        └──────────────────────┘
```

**Principios clave:**

1. **Capa 1 nunca importa modelos de Django directamente** (no `from apps.crm.models import Cliente`). Siempre va vía service layer (`customer_service.get(...)`). Esto permite que el mismo código sirva para los dos shells.

2. **Solo los módulos de Categoría B implementan la Capa 2B**. Los de Categoría A solo tienen 2A. Esto evita over-engineering.

3. **La Capa 3 (Integration Hub) se construye una vez** y la usan todos los standalone.

---

## Criterios para decidir si un módulo se vende standalone

Antes de extraer un módulo como standalone, debe cumplir TODOS estos criterios:

1. **Está en Categoría B o C**, no en A.

2. **Existe un cliente concreto comprometido a usarlo.** No se construye standalone para "clientes hipotéticos futuros". Compromiso = intención de uso firmada, adelanto, o equivalente.

3. **La versión integrada en Omni ERP ya funciona y está validada** con al menos un cliente real durante 60+ días.

4. **El responsable tiene capacidad técnica disponible** para mantener el standalone sin abandonar el ERP integrado.

5. **Hay valor económico claro:** el standalone se puede vender por suficiente como para justificar el esfuerzo de construirlo y mantenerlo.

**Si alguno de estos 5 no se cumple, el módulo no se extrae como standalone, sin importar lo atractiva que sea la idea comercial.**

---

## Excepción explícita: gestion-cxc-V2

Existe una excepción específica al criterio #3 anterior. El proyecto gestion-cxc-V2 ya existe como sistema separado, con integración Odoo funcional, en evaluación por la empresa donde el responsable trabaja como gerente.

Por esta razón, **Omni Cobranza se construye como standalone desde su nacimiento en Omni**, sin tener una versión integrada validada previamente. Esto es deuda asumida conscientemente. Ver ADR-004 para detalles.

---

## Consecuencias

### Positivas

- **Bajamos la barrera de entrada** para clientes que no quieren cambiar todo su ERP.
- **Generamos revenue antes** del ERP completo (vendiendo módulos sueltos).
- **Validamos demanda** por módulos específicos con poco riesgo.
- **Aprovechamos al máximo el acceso** a la empresa donde el responsable es gerente.
- **Construimos disciplina modular** desde el día 1 (buena arquitectura de todas formas).

### Negativas

- **Costo de construcción mayor:** los módulos modulares con Capa 2B son más caros que los puros integrados. Estimado: +30-50% en módulos que se vuelven standalone.
- **Riesgo de fragmentación:** vender muchos módulos sueltos puede llevar a abandonar la visión del ERP completo.
- **Complejidad operativa:** cada standalone tiene su propio ciclo de venta, soporte, mantenimiento.
- **Tentación de "todo es standalone":** hay que resistir aplicar el modelo a módulos de Categoría A.

### Neutras

- Cada módulo necesita decisión explícita: ¿integrado, ambos, o solo standalone?
- Las skills del proyecto deben reflejar la división entre integrated/standalone (puede requerir skill nueva).
- El Integration Hub (ADR-003) es prerequisito para cualquier standalone.

---

## Cómo se mide el éxito de esta decisión

Indicadores que sugieren que esta decisión está funcionando bien:

- En 18 meses, 1-2 productos standalone tienen al menos 3 clientes externos pagando cada uno.
- Al menos 1 cliente que empezó con un standalone migró al ERP completo dentro de 12 meses.
- El revenue total de standalone representa entre 10-30% del total (no más, no menos).

Indicadores que sugieren que la decisión necesita reconsiderarse:

- 80%+ del revenue viene de standalone después de 24 meses (señal de fragmentación).
- Ningún cliente standalone migra al ERP completo (los wedge no convierten).
- El responsable termina dedicando más tiempo a soporte de standalone que a construcción de Omni.

Estos indicadores se revisan en checkpoints trimestrales.

---

## Cómo revisitar esta decisión

Esta decisión debería revisarse explícitamente si:

- Tras 18 meses, los productos standalone no generan revenue significativo.
- La carga de mantenimiento de múltiples standalone supera la capacidad operativa del proyecto.
- Aparece una oportunidad de inversión que requiera foco 100% en ERP completo.

En cualquier caso, modificar esta decisión requiere ADR nuevo que la reemplace explícitamente.

---

## Referencias

- ADR-003: Integration Hub centralizado (necesario para implementar standalone).
- ADR-004: gestion-cxc-V2 como primer standalone de Omni.
- ADR-005: Estrategia híbrida con prioridad móvil (cómo se ejecutan ERP y Cobranza standalone en paralelo).
- Plan v2.0 sección 1.2: propiedades irrenunciables del producto.
- Norte Estrella (Apéndice C): visión wedge a largo plazo.

## Changelog

### v1.0 — 2026-05-14
- Versión inicial. Decisión tomada y documentada.
