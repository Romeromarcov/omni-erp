# MVP Scope — Análisis de los Dos Negocios Piloto

**Versión:** 1.0
**Propósito:** Aterrizar exactamente qué construye Omni AI-Native en su primer ciclo de 9-15 meses, basado en dos clientes piloto reales: fábrica de muebles artesanales y distribuidora de materiales de tapicería.

> **Cómo usar este documento:** Es la fuente de verdad para qué sí y qué no entra al MVP. Cuando dudes "¿esta feature va o no?", la respuesta está acá. Si no está, no va.

---

## ÍNDICE

- [PARTE 1 — Por qué estos dos negocios son una combinación afortunada](#parte-1)
- [PARTE 2 — Análisis del Negocio A: Fábrica de Muebles Artesanales](#parte-2)
- [PARTE 3 — Análisis del Negocio B: Distribuidora de Tapicería](#parte-3)
- [PARTE 4 — Lo que tienen en común (esto es tu MVP)](#parte-4)
- [PARTE 5 — Lo que es específico de cada uno (esto entra después)](#parte-5)
- [PARTE 6 — Alcance final del MVP](#parte-6)
- [PARTE 7 — Lo que NO entra al MVP, con razones](#parte-7)
- [PARTE 8 — Roadmap detallado mes a mes](#parte-8)
- [PARTE 9 — Preguntas que debes hacerle a cada negocio antes de empezar](#parte-9)

---

# PARTE 1 — Por qué estos dos negocios son una combinación afortunada

Antes de los detalles, vale la pena que entiendas por qué tu situación es mejor de lo que parece.

## 1.1 Son complementarios sin ser idénticos

**La fábrica produce, la distribuidora distribuye.** Uno es manufactura discreta a pedido; el otro es comercio mayorista/minorista. Si construís bien para los dos, tu sistema cubre el espectro completo de operaciones que vas a ver en pymes venezolanas:

- Fabricación bajo pedido con BOM (lista de materiales).
- Inventario de materias primas y producto terminado.
- Ventas al detalle (B2C) y al mayor (B2B).
- Distribución con múltiples niveles de cliente.
- Cobranza con plazos.
- Multimoneda real (compras importadas, ventas locales).

Si construís solo para uno, hacés un producto vertical chico. Construyendo para los dos, descubrís las primitivas que sirven para 80% de las pymes que vas a vender después.

## 1.2 Son verticalmente conectados

Una fábrica de muebles **compra materiales de tapicería** (telas, espumas, hilos, herrajes). Una distribuidora de tapicería **vende a fábricas de muebles**. Es probable que en algún punto, **el negocio B le venda al negocio A**, o que tengan proveedores y clientes en común.

Esto te da una oportunidad única: **podés modelar la relación entre ambos en tu sistema**. Cuando A compra a B, en tu sistema una venta de B es automáticamente una compra de A, con el mismo pedido sincronizado. Eso es parte de la visión de Platform Spaces, pero acá lo descubrís de manera orgánica con dos clientes reales.

**No metas Platform Spaces en el MVP**, pero sí dejá la arquitectura preparada para que esa conexión sea natural cuando llegue el momento.

## 1.3 Combinan complejidades distintas

| Dimensión | Fábrica de muebles | Distribuidora |
|-----------|--------------------|--------------------|
| Volumen de transacciones | Bajo | Alto |
| Complejidad por transacción | Alta (cada mueble es distinto) | Baja (catálogo) |
| Manejo de inventario | Materias primas + WIP + terminados | Solo terminados |
| Cliente típico | B2C particular o B2B mediano | Mix B2B y B2C |
| Forma de pago dominante | Adelanto + saldo | Crédito mayoristas, contado detal |
| Predictibilidad | Baja (proyectos) | Alta (recurrencia) |

Si tu sistema sirve a estos dos extremos, sirve a la mayoría del medio.

## 1.4 Son tuyos

Esto es lo más importante. Tenés acceso real, conocimiento del negocio (probablemente algo, dado que sos gerente y son familiares), tolerancia al error, y libertad para experimentar. Ningún cliente externo te va a dar eso en los primeros 12 meses.

**No subestimes esta ventaja.** Es la diferencia entre construir con feedback real semanal vs construir basado en supuestos.

---

# PARTE 2 — Análisis del Negocio A: Fábrica de Muebles Artesanales

> **Nota importante:** este análisis se basa en supuestos típicos de fábricas artesanales en VE. Antes de construir, **vos validás cada punto con el dueño/operador** usando las preguntas de la PARTE 9.

## 2.1 Operación típica

Una fábrica artesanal de muebles funciona aproximadamente así:

1. **Cliente llega con un pedido.** Puede ser:
   - Un mueble específico del catálogo de la fábrica.
   - Un mueble a medida (modificación de uno del catálogo o totalmente custom).
2. **Cotización.** El maestro carpintero o el dueño calcula:
   - Materiales necesarios (madera, herrajes, tela, espuma, etc.).
   - Tiempo estimado de fabricación.
   - Precio (que mezcla materiales, mano de obra, margen).
3. **Acuerdo y adelanto.** Cliente paga 50% al firmar, saldo contra entrega o despacho.
4. **Producción.** Pasa por etapas: corte de madera, ensamble, lijado, pintado/laqueado, tapizado, control final. Cada etapa puede tomar de horas a días.
5. **Entrega/despacho.** Cliente busca o se le lleva. Se cobra el saldo.
6. **Postventa.** Garantía, ajustes, reparaciones eventuales.

## 2.2 Dolores típicos (lo que duele de verdad)

- **Cotizaciones inconsistentes.** Cada cotización se calcula a mano, varían según humor del que cotice, errores de cálculo, márgenes inconsistentes.
- **No saben cuánto cuesta cada mueble realmente.** Costean por intuición. Algunos productos están perdiendo plata sin que lo sepan.
- **Inventario de materias primas descontrolado.** "Se acabó el barniz" en la mitad de un trabajo. Compras de emergencia caras.
- **No saben qué trabajo tienen.** Pedidos se anotan en cuaderno, en WhatsApp, en hoja suelta. Se pierden.
- **Plazos incumplidos.** Prometen 15 días, entregan en 30. No por mala fe, sino porque no tienen visibilidad real de la carga del taller.
- **Cobranza descuidada.** Saldos pendientes no se persiguen. Adelantos a veces no se registran.
- **No saben qué piezas están en qué etapa.** Si el cliente pregunta "¿cómo va mi mueble?", respuesta vaga.
- **Multimoneda.** Compran materiales en USD (importados, alza por dólar), venden en VES o USD según cliente, llevan cuentas mixtas.
- **Personal informal.** Carpinteros que cobran por trabajo hecho, no salario fijo. Cálculo de pago a destajo.

## 2.3 Lo que NO duele tanto (y muchos sistemas asumen que sí)

- Reportes financieros sofisticados. El dueño quiere saber "cuánto gané este mes", no análisis multidimensional.
- Integración con autoridades fiscales (en una fábrica artesanal pequeña, puede ser informal o régimen simplificado).
- Múltiples sucursales. Casi seguro hay una sola.
- E-commerce avanzado. Las ventas son por contacto directo, redes sociales, referidos.

## 2.4 Volumen y escala

Una fábrica artesanal típica venezolana procesa entre **5 y 30 pedidos por mes**, con tickets que van desde $100 (un par de sillas) a $3.000+ (un juego de comedor o una sala completa). Personal: dueño + 2-8 operarios. Computadoras: probablemente 1, en la oficina.

Esto te dice que **el sistema no necesita ser ultra-rápido ni masivamente concurrente**. Necesita ser confiable, claro, y útil.

## 2.5 Lo que el sistema debe resolver, en orden de dolor

1. **Cotización estructurada y reusable.** Que cuando alguien pregunte "¿cuánto vale una mesa de comedor con tablero de cedro y patas torneadas?", la cotización se arme con plantillas, salga en 5 minutos, y todos los cálculos sean trazables.
2. **Registro único de pedidos.** Un solo lugar donde están todos los trabajos, su estado, plazo, cliente.
3. **Lista de materiales (BOM) por producto.** Para que la cotización use materiales reales con precios actualizados, y para que el inventario se descuente al producir.
4. **Control de inventario de materias primas.** Para que no se queden sin barniz a media producción.
5. **Estado del trabajo por etapa.** Que el dueño y el cliente sepan en qué fase va cada mueble.
6. **Cobranza con adelantos y saldos.** Que sepan a quién deben cobrar y cuánto.
7. **Costeo real por producto.** Para saber qué muebles dan plata y cuáles no.
8. **Pago a destajo.** Cálculo automático de cuánto le toca a cada operario por los trabajos completados.

## 2.6 Lo que ese sistema te enseña a construir

Si Omni resuelve bien esos ocho puntos para esta fábrica, vos terminás con primitivas que sirven para:

- Cualquier negocio de fabricación bajo pedido (carpintería, herrería, costura, talleres mecánicos).
- Cualquier negocio basado en proyectos con etapas (construcción pequeña, eventos).
- Cualquier negocio con costeo por producto/proyecto.
- Cualquier negocio con personal a destajo o por proyecto.

Eso es un mercado enorme en Venezuela.

---

# PARTE 3 — Análisis del Negocio B: Distribuidora de Tapicería

> **Nota:** misma advertencia que la PARTE 2. Validá todo con el dueño antes de construir.

## 3.1 Operación típica

Una distribuidora de materiales de tapicería al mayor y detal funciona aproximadamente así:

1. **Compra a proveedores.** Generalmente importadores o fabricantes nacionales. Compras grandes, probablemente en USD, pago a 30/60 días o contado con descuento.
2. **Recepción y almacén.** Mercancía entra, se cuenta, se almacena por familia (telas, espumas, herrajes, hilos, accesorios).
3. **Venta al mayor.** Clientes son fábricas de muebles, talleres de tapicería, otros distribuidores chicos. Compran cantidades, piden crédito, esperan despacho. Volúmenes grandes por transacción.
4. **Venta al detal.** Clientes son particulares o tapiceros pequeños. Compran cantidades chicas, generalmente al contado, llevan en el momento.
5. **Cobranza mayoristas.** Seguimiento de cuentas por cobrar a 30/60 días, llamadas, renegociaciones.
6. **Reposición.** Re-ordenar inventario antes de que se acabe lo que más rota.

## 3.2 Dolores típicos

- **Stock real vs stock en sistema diferente.** Falta inventario físico que el sistema dice que hay; o al revés. Por ventas no registradas, mermas, errores de carga.
- **Listas de precios descontroladas.** Precios mayoristas, detal, especiales para ciertos clientes, descuentos por volumen. Calcular el precio correcto para cada cliente es lío.
- **Multimoneda.** Compras en USD, vender en VES o USD según cliente, manejar tasa BCV vs tasa interna.
- **Cobranza al mayor.** Clientes mayoristas siempre están pidiendo plazo, atrasándose, renegociando. Sin visibilidad clara de quién debe cuánto y desde cuándo, se pierde plata.
- **Despacho al mayor.** Pedidos grandes que necesitan despacharse en camión propio o tercerizado, con guía de despacho, factura, documentos.
- **Punto de venta para detal.** En el local físico, ventas pequeñas y rápidas. Necesita POS ágil que también descuente del mismo inventario que usa el mayoreo.
- **Reposición intuitiva.** "Se está acabando el yute", "hay mucha espuma de la 25", sin datos sólidos.
- **Vendedores con comisión.** Si tienen vendedores externos, calcular comisiones por cobranza efectiva (no por venta facturada).
- **Devoluciones y notas de crédito.** Mercancía defectuosa, error de despacho, devolución por garantía.

## 3.3 Lo que NO duele tanto

- Manufactura (no fabrican, distribuyen).
- E-commerce sofisticado (venden por contacto, redes, locales).
- Múltiples almacenes de gran complejidad (probablemente uno o dos).
- Trazabilidad por lote o serie (no es industria farmacéutica).

## 3.4 Volumen y escala

Una distribuidora típica venezolana procesa entre **20 y 200 transacciones por día** (mezcla mayor y detal), con tickets desde $5 (un metro de tela al detal) a $5.000+ (un pedido mayorista grande). Personal: dueño + 2-10 personas (vendedores, almacenista, despachador, cobrador). Computadoras: probablemente 2-3 (oficina, mostrador, almacén).

Esto te dice que **el sistema necesita ser ágil para POS al detal**, robusto para inventario, y prolijo en cobranza al mayor.

## 3.5 Lo que el sistema debe resolver, en orden de dolor

1. **Inventario en tiempo real con stock confiable.** Cada venta (al mayor o detal) descuenta. Cada compra suma. Conteos cíclicos para conciliar físico vs sistema.
2. **Listas de precios múltiples.** Mayor, detal, especial por cliente, por volumen, con fechas de vigencia.
3. **POS ágil para mostrador.** Búsqueda rápida, código de barras o búsqueda por nombre, cobro multimoneda, ticket impreso.
4. **Pedidos al mayor con cotización, despacho y factura.** Flujo: cotización → pedido → despacho con guía → factura.
5. **Cuentas por cobrar con aging.** Quién debe cuánto, desde cuándo, con vista clara para perseguir.
6. **Multimoneda automático.** Compras en USD se contabilizan, ventas en VES o USD según el cliente, BCV se actualiza automático.
7. **Reposición sugerida.** Basado en rotación histórica y stock actual, qué hay que pedir.
8. **Comisiones de vendedores por cobranza.** No por facturación, por dinero que efectivamente entró.

## 3.6 Lo que ese sistema te enseña a construir

Si Omni resuelve bien esos ocho puntos, terminás con primitivas que sirven para:

- Cualquier negocio de distribución/comercialización.
- Comercios al detal con manejo de inventario serio.
- Cualquier negocio con cobranza mayorista.
- Cualquier negocio con vendedores externos comisionables.

Otra vez, mercado enorme en VE.

---

# PARTE 4 — Lo que tienen en común (esto es tu MVP)

Cuando comparás las dos listas, aparece un núcleo común que sirve a ambos. **Ese núcleo es tu MVP.**

## 4.1 Capacidades compartidas

| # | Capacidad | Necesaria para fábrica | Necesaria para distribuidora |
|---|-----------|------------------------|------------------------------|
| 1 | Catálogo de productos con código, nombre, categoría, unidad | ✅ | ✅ |
| 2 | Catálogo de clientes con datos fiscales, contacto, condiciones | ✅ | ✅ |
| 3 | Catálogo de proveedores | ✅ | ✅ |
| 4 | Inventario con stock por ubicación, movimientos, kardex | ✅ (materias primas + WIP + terminados) | ✅ (terminados) |
| 5 | Cotización → pedido → factura → cobro | ✅ | ✅ |
| 6 | Multimoneda (USD/VES) con tasa BCV automática | ✅ | ✅ |
| 7 | IVA, IGTF y retenciones venezolanas | ✅ | ✅ |
| 8 | Ciclo de compras: solicitud → OC → recepción → factura → pago | ✅ | ✅ |
| 9 | Cuentas por cobrar con aging | ✅ | ✅ |
| 10 | Cuentas por pagar | ✅ | ✅ |
| 11 | Métodos de pago VE (efectivo USD/VES, Pago Móvil, transferencia, USDT, Zelle) | ✅ | ✅ |
| 12 | Caja / arqueo diario | ✅ | ✅ |
| 13 | Listas de precios (al menos mayor y detal) | ✅ (precio cliente final vs precio mayorista) | ✅ |
| 14 | Reportes básicos: ventas, compras, inventario, cobranza | ✅ | ✅ |
| 15 | Personalización conversacional Capa 1-2 (preferencias y configuración) | ✅ | ✅ |
| 16 | Multi-tenant | ✅ | ✅ |
| 17 | Auditoría de cambios | ✅ | ✅ |

**Estos 17 puntos son tu MVP no-negociable.** Sin ellos, ninguno de los dos negocios usa el sistema.

## 4.2 Capacidades AI básicas que aplican a ambos

Mantenete extremadamente moderado acá. Para el MVP, dos agentes en modo "sugerir":

| Agente | Qué hace | Valor para fábrica | Valor para distribuidora |
|--------|----------|--------------------|--------------------------|
| **Asistente de cobranza** | Cada mañana revisa CxC, identifica cuentas a perseguir, sugiere el mensaje a enviar (WhatsApp). El humano revisa y envía. | Adelantos pendientes, saldos | CxC de mayoristas |
| **Asistente de stock** | Detecta productos por debajo de mínimo, sugiere reposición. El humano aprueba la OC. | Materias primas que se acaban | Productos de alta rotación |

Solo dos. Cualquier otro agente que se te ocurra agregar al MVP, **resistilo**. Después.

## 4.3 Personalización conversacional Capa 1-2 (qué incluye en MVP)

El usuario puede pedirle al agente:

- Cambiar nombres de campos (etiquetar "RIF" como "Cédula" si vende mucho a particulares).
- Cambiar moneda de despliegue.
- Definir condiciones de pago propias ("contado", "15 días", "30 días", "50/50").
- Crear listas de precios.
- Crear categorías de productos/clientes.
- Configurar alertas (por WhatsApp, email).
- Configurar plantillas de mensajes (cobranza, agradecimiento por compra).
- Personalizar el formato de factura/cotización (logo, datos, términos).

**No se incluye en MVP la Capa 3+** (creación de campos custom, entidades nuevas, reglas complejas). Eso viene después.

---

# PARTE 5 — Lo que es específico de cada uno (esto entra después del MVP base)

Después de tener el núcleo común corriendo, agregás los específicos. Probablemente en este orden:

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

## 5.2 Específicos de la fábrica (entran después, son más complejos)

| # | Capacidad | Por qué después |
|---|-----------|------------------|
| 1 | BOM (lista de materiales) por producto | Requiere modelo más rico |
| 2 | Cotización con cálculo desde BOM y mano de obra | Construye sobre BOM |
| 3 | Órdenes de fabricación con etapas y estado | Modelo de proceso |
| 4 | Costeo real por orden de fabricación | Después de OF |
| 5 | Pago a destajo a operarios | Construye sobre OF |
| 6 | Proyectos / pedidos a medida | Más complejo |

## 5.3 Por qué este orden

Aunque emocionalmente puedas querer empezar por la fábrica (porque es más interesante técnicamente), **es estratégicamente mejor empezar por la distribuidora**. Razones:

1. **Volumen alto de transacciones** te genera datos rápidos para detectar bugs y mejorar.
2. **Caso de uso más estandarizado** = construye primitivas que sirven para más clientes futuros.
3. **POS y CxC son features universales** que todo distribuidor venezolano necesita.
4. **La fábrica usa el mismo sistema** (con el núcleo común) durante esta fase. Solo le faltan las features específicas, que llegan en mes 6-9.

Esto también te da una ventaja: en los meses iniciales, el dueño de la fábrica usa el sistema para llevar lo que sí funciona (catálogo, ventas, inventario de muebles terminados, cobranza). Va familiarizándose. Cuando agregás OF, BOM, costeo, ya está acostumbrado al sistema.

---

# PARTE 6 — Alcance final del MVP

## 6.1 Definición precisa del MVP (lo que se entrega antes de buscar cliente externo)

**Mes 0-6: MVP Base.** El sistema cubre los 17 puntos de la PARTE 4.1 + dos agentes de la PARTE 4.2 + personalización Capa 1-2.
**Hito:** la distribuidora opera diariamente sin volver a su sistema anterior.

**Mes 6-9: MVP + Específicos Distribuidora.** Se agregan las 5 capacidades de la PARTE 5.1.
**Hito:** la distribuidora reemplaza completamente lo que use hoy. La fábrica usa lo que aplica.

**Mes 9-15: MVP + Específicos Fábrica.** Se agregan las 6 capacidades de la PARTE 5.2.
**Hito:** la fábrica también opera completamente. Tenés un producto realmente vendible.

**Mes 15+: Buscar primer cliente externo.** No antes. Si no podés mostrar a un cliente externo dos negocios reales operando en producción, no tenés caso.

## 6.2 Definition of Done por hito

### Hito 1 (Mes 6) — MVP Base operando

- [ ] La distribuidora carga su catálogo completo (productos, clientes, proveedores).
- [ ] Hace ventas al detal y al mayor en el sistema, no en cuaderno ni Excel.
- [ ] Inventario se actualiza correctamente en tiempo real.
- [ ] Genera cotizaciones y facturas con IVA correcto, IGTF cuando aplica.
- [ ] Hay al menos 30 días continuos de uso diario sin volver al sistema anterior.
- [ ] Dueño puede ver al cierre del día: ventas del día, cobranza pendiente, productos bajos.
- [ ] Multimoneda funciona: compras en USD se reflejan, ventas en mix se contabilizan.
- [ ] Agente de cobranza sugiere acciones mañaneras y se aceptan al menos el 60% de sus sugerencias.

### Hito 2 (Mes 9) — Distribuidora completa

- [ ] POS de mostrador en uso real con código de barras.
- [ ] Vendedores cobran comisión calculada por el sistema.
- [ ] Devoluciones y notas de crédito procesadas en sistema.
- [ ] Despachos al mayor con guía documentada.
- [ ] Conteo cíclico arrojó diferencias que el sistema ayudó a conciliar.

### Hito 3 (Mes 12-15) — Fábrica completa

- [ ] BOM completo de los 10 productos más vendidos cargado.
- [ ] Cotización a medida arma BOM + mano de obra automáticamente.
- [ ] OF (orden de fabricación) creada para cada pedido aprobado.
- [ ] Estado de etapas actualizado por operarios (probablemente vía interfaz simple, móvil o tablet).
- [ ] Costeo real de OF concilia con costeo estimado en cotización (con tolerancia).
- [ ] Pago a destajo calculado automáticamente al cierre de cada quincena.
- [ ] Inventario de materias primas se descuenta cuando OF empieza.

## 6.3 Métrica única que importa por encima de las features

**El dueño de cada negocio usa el sistema como su herramienta principal de gestión, sin volver a Excel ni cuaderno ni el sistema anterior.**

Si llegás al mes 6 con todas las features y los dueños siguen usando Excel para "lo importante", **fracasaste el MVP**. La adopción real es la métrica, no la cantidad de features.

---

# PARTE 7 — Lo que NO entra al MVP, con razones

Acá está la lista que vas a querer violar. Te explico por qué cada cosa NO entra y qué hacer si surge la tentación.

## 7.1 No entra al MVP

| Capacidad | Razón |
|-----------|-------|
| **Manufactura compleja con MRP** | La fábrica artesanal no es industrial. OF simple basta. |
| **WMS (gestión de bodega avanzada)** | El volumen no lo justifica. Inventario simple basta. |
| **Contabilidad completa** | Se difiere. El cliente seguirá usando contador externo + Excel para libros formales hasta el mes 12. |
| **Nómina** | Pago a destajo es simple. Nómina formal completa no es prioridad. |
| **Reportes financieros sofisticados** | El dueño quiere "cuánto gané"; eso lo dan reportes simples. |
| **CRM con pipeline de ventas** | La fábrica vende por contacto; la distribuidora vende por mostrador. No hay pipeline B2B clásico. |
| **Marketing automation** | Distracción total. |
| **E-commerce / tienda online** | Otro día. Mes 18+. |
| **Integración con SENIAT (libros electrónicos)** | El régimen de estos negocios probablemente no lo exige todavía, o se hace manual. Después. |
| **Facturación electrónica** | Si SENIAT no lo exige aún para estos negocios, no es prioridad. |
| **App móvil** | PWA básica si necesario. App nativa, no. |
| **Multi-sucursal** | Cada negocio probablemente tiene una. |
| **Multi-empresa con consolidación** | No, hasta que aparezca un cliente que lo necesite. |
| **Análisis predictivo / forecasting con IA** | Exagerado para MVP. |
| **Workflow / aprobaciones complejas** | El dueño aprueba todo verbalmente hoy. |
| **Notificaciones push complejas** | WhatsApp basta. |
| **Integración bancaria automática** | Conciliación manual + sugerencia del agente. Auto-conciliación es Fase 2. |
| **Visión por computador** | Lejísimos. |
| **IoT** | No. |
| **Blockchain** | No. |
| **Platform Spaces / Marketplace** | NO. NUNCA EN ESTA FASE. |
| **Web pública / app de cliente final** | No. |
| **MCP servers públicos** | No. Internos sí, públicos no. |
| **Multi-idioma** | Solo español. |
| **Multi-país** | Solo Venezuela. |

## 7.2 Excepciones permitidas

Solo dos casos donde podés violar la lista anterior:

1. **Si el dueño de uno de los dos negocios dice "sin esto no uso el sistema".** Eso es bloqueante. Pero validá: ¿realmente lo necesita o le gustaría tenerlo? Distinguí.
2. **Si descubris que algo del "núcleo común" requiere esa feature.** Ejemplo hipotético: tal vez para que el inventario de la fábrica funcione bien necesitás un tipo de movimiento que también es útil en la distribuidora. Eso entra.

Cualquier otra cosa, **anótala en un archivo `BACKLOG_FUTURO.md` y sigue.**

## 7.3 La regla del 100

Cuando sientas la tentación de agregar X, contá: ¿esto me lo van a pedir 100 clientes futuros, o solo este uno o dos? Si es solo uno, no entra al core. **Va al BACKLOG_FUTURO o, mejor todavía, va como personalización del cliente cuando construyamos el DSL.** No mezcles personalización específica con producto core. Es la regla más importante de toda la PARTE 7.

---

# PARTE 8 — Roadmap detallado mes a mes

> **Nota: estos timelines asumen 15-25 horas semanales de trabajo, con AI ayudando. Si tu ritmo real es distinto, ajustá proporcionalmente. No te frustres si vas más lento; reajustá expectativas.**

## Mes 1 — Fundaciones técnicas

**Trabajo:**
- Setup completo: Postgres, Docker, CI básico, tests.
- Saldar deuda técnica del Master Plan original (sección 2.4).
- Decidir si reescribís o adaptás lo que ya tenés en Omni (recomendación: adaptás core, reescribís lo que no funciona).
- Diagnóstico inicial (PARTE 8 del protocolo del agente).

**Hito de fin de mes:** la build pasa, los tests corren, el sistema arranca, el agente IA está operando con disciplina.

## Mes 2 — Núcleo común parte 1

**Trabajo:**
- Catálogo de productos, clientes, proveedores.
- Inventario básico con movimientos.
- Multi-tenant impecable.
- Auditoría.
- Multimoneda básica (USD/VES, tasa BCV).

**Hito:** podés cargar productos, clientes, hacer un movimiento de inventario manual y verlo correctamente.

## Mes 3 — Núcleo común parte 2

**Trabajo:**
- Cotización → pedido → factura.
- IVA, IGTF, retenciones.
- Cobranza básica con aging.
- Métodos de pago VE.

**Hito:** podés crear una venta completa para la distribuidora, generar factura con cálculos correctos, y registrar el cobro.

## Mes 4 — Núcleo común parte 3

**Trabajo:**
- Ciclo de compras.
- Cuentas por pagar.
- Caja diaria.
- Listas de precios.
- Reportes básicos.

**Hito:** la distribuidora puede operar el ciclo comercial completo: comprar a proveedor, recibir, vender, cobrar, ver caja.

## Mes 5 — Personalización Capa 1-2 + agentes

**Trabajo:**
- DSL declarativo de personalización (versión simple, solo Capas 1-2).
- Agente conversacional para aplicar personalizaciones.
- Agente de cobranza (modo sugerir).
- Agente de stock (modo sugerir).
- WhatsApp Business integrado (envío de mensajes desde sistema, recepción simple).

**Hito:** el dueño de la distribuidora puede pedirle al agente "cambia el nombre del campo X" y el agente lo aplica. Cada mañana le llega sugerencia de cobranza.

## Mes 6 — Distribuidora en producción

**Trabajo:**
- Migración de datos del sistema actual de la distribuidora (clientes, productos, deudas pendientes, stock inicial).
- Capacitación al dueño y al equipo.
- Acompañamiento intensivo primeras 2 semanas.
- Bugfixing en caliente.
- Pequeñas adaptaciones que surjan.

**Hito 1:** la distribuidora opera 30 días continuos en el sistema sin volver al anterior.

## Mes 7-9 — Específicos distribuidora + onboarding fábrica

**Trabajo:**
- POS de mostrador con código de barras (mes 7).
- Vendedores y comisiones (mes 8).
- Devoluciones, notas de crédito (mes 8).
- Despacho con guía (mes 9).
- Conteo cíclico (mes 9).
- En paralelo: onboarding básico de la fábrica con el núcleo común (catálogo, clientes, ventas de muebles ya hechos, cobranza).

**Hito 2:** la distribuidora reemplaza completamente lo que tenía. La fábrica usa el sistema para gestión comercial básica.

## Mes 10-12 — Fábrica parte 1

**Trabajo:**
- BOM (lista de materiales) por producto (mes 10).
- Cotización con cálculo desde BOM (mes 10-11).
- Órdenes de fabricación con etapas (mes 11).
- Estado de OF actualizable por operarios (mes 12).

**Hito:** la fábrica puede cotizar un mueble, abrir OF, ver en qué etapa está cada trabajo.

## Mes 13-15 — Fábrica parte 2 + estabilización

**Trabajo:**
- Costeo real por OF (mes 13).
- Pago a destajo (mes 13).
- Inventario de materias primas con consumo desde OF (mes 14).
- Bugfixing intensivo, estabilización, documentación (mes 15).

**Hito 3:** la fábrica opera completamente. Hay 9-12 meses de datos reales en producción de los dos negocios. Tenés algo vendible.

## Mes 16+ — Primer cliente externo

**Trabajo:**
- Identificar candidato (red de contactos, un negocio cercano).
- Hacer demos con datos reales de tus dos negocios actuales.
- Cerrar venta. Idealmente plan inicial de $30-50/mes.
- Onboarding de cliente externo (esto te enseña dónde están las fricciones del producto).

**Hito:** primer cliente externo pagando.

---

# PARTE 9 — Preguntas para hacerle a cada negocio antes de empezar

Esta sección es para vos, no para un agente. Sentate con el dueño de cada negocio una hora y respondé estas preguntas. **No empieces a construir hasta no tener estas respuestas concretas.**

## 9.1 Preguntas para la fábrica de muebles

### Sobre el negocio
1. ¿Cuántos muebles producen al mes en promedio? Rango: ¿el más lento y el más activo?
2. ¿Qué porcentaje son del catálogo vs hechos a medida?
3. ¿Qué moneda predomina en las ventas? ¿Cómo se decide la moneda con cada cliente?
4. ¿Cuál es el ticket promedio? ¿El más bajo y el más alto?
5. ¿Cuántos operarios tienen? ¿Salario fijo, destajo, mixto?
6. ¿Tienen vendedores externos o todas las ventas son por contacto directo?

### Sobre operación actual
7. ¿Cómo registran hoy los pedidos? (cuaderno, Excel, software, mezcla)
8. ¿Cómo cotizan? ¿Tienen plantillas? ¿Cuánto tarda hacer una cotización?
9. ¿Cómo saben cuánto material tienen?
10. ¿Cómo le pagan a los operarios? ¿Cuándo? ¿Quién calcula?
11. ¿Cómo siguen el estado de un trabajo?
12. ¿Qué pasa cuando un cliente pregunta "¿cómo va mi mueble?"
13. ¿Tienen idea de cuánto cuesta cada mueble realmente? ¿Cómo lo calculan?

### Sobre dolores
14. Si pudieras eliminar un dolor del negocio mañana, ¿cuál sería?
15. ¿Qué cosa sí o sí necesita estar en el sistema o no lo van a usar?
16. ¿Qué cosa NO te interesa nada que esté en el sistema?
17. ¿Quién va a ser el usuario principal del sistema? (vos, esposa/o, hijo, gerente, secretaria)
18. ¿Cuánta tecnología maneja la persona que va a usar el sistema?

### Sobre el experimento
19. ¿Cuándo podríamos empezar a usarlo en serio? ¿Hay algún momento mejor que otro?
20. ¿Estás dispuesto a usar el sistema en paralelo al actual durante 1-2 meses?
21. ¿Quién decide si seguimos usándolo o lo abandonamos?

## 9.2 Preguntas para la distribuidora

### Sobre el negocio
1. ¿Cuántas transacciones hacen por día (mayor + detal)?
2. ¿Qué porcentaje de la facturación es mayor vs detal?
3. ¿Cuántos productos manejan en catálogo? Aproximado.
4. ¿Cuántos clientes activos? ¿Mayoristas vs minoristas?
5. ¿Cuántos proveedores?
6. ¿Cuántas personas trabajan? ¿Roles?
7. ¿Tienen vendedores externos? ¿Cómo les pagan?

### Sobre operación actual
8. ¿Qué sistema usan hoy? (otro ERP, software hecho, Excel, mezcla)
9. ¿Cuál es la mayor frustración con el sistema actual?
10. ¿Cómo manejan el inventario? ¿Conteos físicos cada cuánto?
11. ¿Cuántas listas de precios tienen activas?
12. ¿Qué porcentaje de las ventas es a crédito? ¿A qué plazo?
13. ¿Cómo persiguen las cuentas por cobrar hoy?
14. ¿Tienen punto de venta físico? ¿Cuántos puestos de cobro?
15. ¿Manejan código de barras o búsqueda por nombre/código manual?
16. ¿Compran en USD? ¿Pagan en USD o VES?

### Sobre dolores
17. Si pudieras eliminar un dolor del negocio mañana, ¿cuál sería?
18. ¿Qué cosa sí o sí necesita estar en el sistema?
19. ¿Qué cosa NO te interesa que esté?
20. ¿Quién va a ser el usuario principal? ¿Cuántas personas distintas usarían el sistema?
21. ¿Qué tan tecnológicas son las personas que van a usar el sistema?

### Sobre el experimento
22. ¿Cuándo podríamos empezar?
23. ¿Estás dispuesto a 1-2 meses de uso paralelo con el sistema actual?
24. ¿Tenés tu data actual exportable de algún lado?

## 9.3 Cómo usar las respuestas

Las respuestas a estas preguntas:
1. **Confirman o ajustan los supuestos** de las PARTES 2 y 3.
2. **Te indican qué priorizar** dentro del MVP. Si 5 dolores son los mismos en ambos, esos son los que primero atacás.
3. **Te muestran red flags.** Si el dueño no quiere usar el sistema en paralelo, no es un buen piloto. Si solo querés dejar el sistema actual, querés migración limpia (más riesgo).
4. **Te dan baseline para medir éxito.** Si hoy hacer cotización tarda 30 minutos y tu sistema lo baja a 5, eso es el ROI tangible.
5. **Te enseñan vocabulario del negocio.** Cómo lo nombran, cómo lo piden. Eso lo usás en la UI y en los prompts del agente.

**Hacé estas preguntas antes de la primera línea de código orientada a estos negocios. Es la inversión de 2 horas que te ahorra 2 meses.**

---

# Cierre del documento

Tu MVP no es "el ERP AI-nativo universal". Tu MVP es **el sistema mínimo que estos dos negocios necesitan para reemplazar lo que usan hoy, construido de manera que las primitivas sirvan después para 100 clientes parecidos**.

Esa frase es la diferencia entre llegar y no llegar. Releela cuando dudes si una feature entra o no.

Mucho éxito. Hay tres documentos que se complementan con este: el plan operativo y disciplina, el protocolo del agente, y la guía founder solo + AI. Léelos en ese orden y arranca.

---

*Documento vivo. Actualizable cuando las respuestas a la PARTE 9 lo justifiquen, o cuando uno de los dos negocios cambie su realidad. No actualizable por capricho ni por ambición.*
