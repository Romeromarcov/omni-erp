# ADR-007: Arquitectura de Localización en Dos Capas

**Estado:** Aceptado
**Fecha:** 2026-06-01
**Autor(es):** Marco Romero, Claude Opus 4.8

## Contexto

Omni ERP nace para el mercado venezolano (IVA, IGTF, RIF, libros SENIAT,
quincenas de nómina, multimoneda con tasa BCV) pero su objetivo de producto es
expandirse a otros países. Si la lógica país-específica se hardcodea en los
módulos núcleo (`ventas`, `fiscal`, `nomina`, `finanzas`), cada nuevo país
obliga a cirugía invasiva y el sistema queda atado a Venezuela.

La auditoría 2026-06-01 confirmó el riesgo: utilidades VE (validadores RIF/
cédula, feriados, formatos, IGTF, IVA) viven hoy dispersas en `apps/fiscal` y
`apps/vzla_localizacion`, acopladas al núcleo. Sin un contrato claro, cualquier
PR de la sub-fase 1.F (distribuidora) tendería a hardcodear "VE" en el núcleo.

Además, el negocio necesita **activar/desactivar** la localización por empresa:
una bodega informal en Venezuela puede no ser contribuyente de IVA, y una
empresa en otro país no debe recibir IGTF jamás.

## Decisión

**El núcleo es agnóstico de país. La lógica país-específica se aísla detrás de
una capa de localización con dos sub-capas activables de forma independiente
por empresa, y se accede SOLO a través de seis puertos (interfaces) abstractos.**

### Dos capas

1. **Capa legal** (`localizacion_legal_activa`): obligaciones del Estado —
   impuestos (IVA/IGTF), documentos legales (factura fiscal, nota de crédito),
   libros legales (SENIAT), reglas de nómina obligatorias. Es lo que un país
   *exige*.
2. **Capa dinámica de mercado** (`localizacion_mercado_activa`): prácticas de
   mercado que cambian sin ley — proveedores de tasas (BCV, paralelo, Binance
   P2P), métodos de pago locales (Zelle, Pago Móvil), redondeos de uso común.
   Es lo que el mercado *usa*.

Cada `Empresa` lleva dos flags booleanos independientes (default `True` para las
empresas VE existentes, preservando compatibilidad). Una `Empresa` con
`pais_codigo_iso="CO"` y ambos flags en `False` no recibe IGTF ni IVA VE.

### Seis puertos

Toda interacción del núcleo con lo país-específico pasa por una de estas
interfaces abstractas (ABC en `apps/localizacion/ports.py`):

| Puerto | Responsabilidad | Capa |
|--------|-----------------|------|
| `MotorImpuestos` | Calcular impuestos de una operación (IVA, IGTF, retenciones) | Legal |
| `GeneradorDocumentoLegal` | Emitir el documento fiscal del país (factura, NC) | Legal |
| `CalculadoraNomina` | Conceptos y deducciones obligatorias de nómina | Legal |
| `LibroLegal` | Libros/declaraciones para el fisco (libros SENIAT) | Legal |
| `ProveedorTasas` | Obtener tasas de cambio del mercado | Mercado |
| `MetodosPagoLocales` | Métodos de pago propios del país/mercado | Mercado |

El núcleo nunca importa `apps/localizacion_ve`; importa los puertos y obtiene la
implementación concreta vía un **registry**.

### Registro y resolución

- `apps/localizacion/registry.py`: cada localización se registra con su
  `pais_codigo_iso` y las implementaciones de los puertos que provee.
- `apps/localizacion/services.py::get_localizacion(empresa)`: resuelve la
  localización aplicable según `empresa.pais_codigo_iso` y los flags de capa;
  si una capa está desactivada, devuelve un *no-op* (p. ej. `MotorImpuestos`
  que retorna cero impuestos).
- Venezuela se implementa en `apps/localizacion_ve` (renombre de
  `apps/vzla_localizacion`, ver GAP-2) como el primer adaptador concreto.

### Estrategia de migración (strangler fig)

No se reescribe la lógica fiscal de golpe. `MotorImpuestosVE` y los demás
adaptadores VE inicialmente **delegan** en las funciones actuales de
`apps/fiscal/` y `apps/finanzas/`. La lógica se va moviendo a `localizacion_ve`
de forma incremental sin romper el núcleo.

## Consecuencias

**Positivas**
- El núcleo deja de conocer Venezuela; agregar un país es implementar puertos.
- IGTF/IVA VE se pueden apagar por empresa (bodega informal, empresa extranjera).
- Contrato explícito que evita hardcodear "VE" en cada PR de 1.F.

**Negativas / costos**
- Indirección extra (puerto + registry) para cada llamada país-específica.
- Requiere disciplina: ningún módulo núcleo puede importar `localizacion_ve`.
- La migración strangler fig convive temporalmente con la lógica vieja en
  `apps/fiscal`.

## Implementación

- **GAP-2** crea `apps/localizacion/` (`ports.py`, `registry.py`, `services.py`),
  renombra `vzla_localizacion → localizacion_ve`, añade los flags a `Empresa` y
  el adaptador puente `MotorImpuestosVE`.
- DoD de cierre: una `Empresa` con `pais_codigo_iso="CO"` y flags en `False` no
  recibe IGTF al emitir factura (`test_empresa_sin_localizacion_no_aplica_igtf`).

## Referencias

- `PLAN_MAESTRO_UNICO.md` §3.7 y §6 (arquitectura de localización).
- `PLAN_TRABAJO_AUDITORIA_2026-06-01.md` GAP-1 (este ADR) y GAP-2 (framework).
- Memoria del proyecto: localización l10n de dos capas.
