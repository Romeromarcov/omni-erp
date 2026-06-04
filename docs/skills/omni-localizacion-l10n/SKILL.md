---
name: omni-localizacion-l10n
description: Use this skill whenever you write or modify code with country-specific behavior in the Omni project — taxes, legal documents, payroll rules, fiscal books, exchange-rate sources, local payment methods. Triggers include any work touching `apps/localizacion/` (ports, registry), `apps/localizacion_ve/`, anything that would hardcode Venezuela (IVA/IGTF/RIF/SENIAT/BCV) into the core, `Empresa.pais` / `localizacion_legal_activa` / `localizacion_mercado_activa` flags, or implementing ADR-007 (two-layer pluggable localization). Apply it as an ACTIVE RULE on every new country-specific feature so the core stays agnostic. Do NOT use for purely generic core logic with no country specificity, or frontend.
---

# Skill: Arquitectura de Localización (l10n de dos capas, ADR-007)

## Cuándo usar esta skill

Cargá esta skill **siempre que escribas lógica específica de un país**:
- Impuestos (IVA, IGTF, retenciones), documentos legales (factura fiscal, notas), libros (SENIAT).
- Nómina legal (LOTTT, parafiscales), plan de cuentas sugerido por país.
- Tasas de cambio de mercado, métodos de pago locales (Pago Móvil, Zelle, USDT).

Es una **regla activa, no una fase**: aunque la extracción completa sea gradual, **todo código país-específico nuevo entra por un puerto de localización desde hoy** (R-PROC-1). No la cargués para lógica de core genérica sin país, ni para frontend.

## El principio rector

> **El núcleo no conoce ningún país.** Venezuela es la **primera** localización, no la base. Nada específico de un país se incrusta en el core: vive en un paquete de localización que se activa/desactiva por empresa.

"Venezuela-first" ≠ "Venezuela-hardcoded". El sistema debe poder operar **genérico** para una empresa no venezolana (una moneda, factura simple, sin IGTF, sin doble tasa) sin arrastrar la tropicalización VE.

## Las dos capas de una localización

| Capa | Qué es | Ejemplos VE | Flag |
|---|---|---|---|
| **A — Legal/Regulatoria** | Lo que el Estado exige por ley | IVA, IGTF, retenciones, factura fiscal, libros SENIAT, nómina LOTTT, parafiscales | `localizacion_legal_activa` |
| **B — Dinámica de mercado** | Lo que la realidad económica obliga aunque no sea ley | multimoneda real, doble tasa BCV/paralela, métodos de pago mixtos, pagos de terceros, cambios de divisa, ventas con/sin factura, libro maestro de caja | `localizacion_mercado_activa` |

Se activan **por separado**: una empresa formal VE activa ambas; una bodega informal podría activar solo la Capa B; una empresa de otro país, ninguna de las dos venezolanas.

## Mecanismo: puertos + registro

El core invoca **interfaces abstractas (puertos)**; las localizaciones las implementan y se registran por código ISO de país. El core nunca importa `localizacion_ve` directamente.

### Los seis puertos (`apps/localizacion/ports.py`)

**Capa A (legal):**
- `MotorImpuestos.calcular(subtotal, empresa, contexto) -> dict`
- `GeneradorDocumentoLegal.emitir(documento, empresa) -> dict`
- `CalculadoraNomina.calcular(empleado, periodo, empresa) -> dict`
- `LibroLegal.generar(empresa, periodo, tipo)`

**Capa B (mercado):**
- `ProveedorTasas.obtener_tasa(origen, destino) -> Decimal | None`
- `MetodosPagoLocales.listar(empresa) -> list[dict]`

Cada puerto tiene una implementación **No-Op** para cuando la capa está desactivada (ej. `MotorImpuestosNoOp` devuelve impuestos en cero).

### Registro (`apps/localizacion/registry.py`)

```python
from apps.localizacion import registry
from apps.localizacion_ve.adapters import MotorImpuestosVE, CalculadoraNominaVE

registry.register("VE", {
    "MotorImpuestos": MotorImpuestosVE(),
    "CalculadoraNomina": CalculadoraNominaVE(),
})
```

### Resolución desde el core

El core obtiene la implementación por empresa (vía `apps/localizacion/services.py`), nunca hardcodea el país:

```python
# CORE — agnóstico
from apps.localizacion.services import get_localizacion

def calcular_impuestos_operacion(empresa, subtotal):
    loc = get_localizacion(empresa)                 # resuelve por Empresa.pais + flags
    motor = loc.get("MotorImpuestos", MotorImpuestosNoOp())
    return motor.calcular(subtotal=subtotal, empresa=empresa)
```

Si la empresa no es venezolana (o tiene la capa legal off), el resolver devuelve el No-Op y el core opera genérico.

## La regla activa desde hoy (costo cero)

1. **Todo código nuevo con lógica de un país entra por un puerto, nunca hardcodeado en el core.** Si tu feature pregunta "¿es Venezuela?" o usa `0.16`/`IGTF`/`RIF`/`SENIAT` dentro de un módulo del core, está mal: eso va en `localizacion_ve` detrás de un puerto.
2. **Toda regla de cálculo (dinero, IVA, IGTF, scoring) que escribas debe ser pura** (sin I/O): pre-condición para extraerla a un paquete reutilizable y para testearla sin BD.
3. **Strangler fig, sin big-bang:** la lógica VE hoy dispersa (`apps/fiscal`, IGTF en `apps/ventas`, libros SENIAT) se migra gradualmente hacia `localizacion_ve` detrás de los puertos. No se reescribe de golpe, pero **no se agrega acoplamiento nuevo**.

## Patrón: implementar un puerto en una localización

```python
# apps/localizacion_ve/adapters.py
from decimal import Decimal
from apps.localizacion.ports import MotorImpuestos

class MotorImpuestosVE(MotorImpuestos):
    def calcular(self, *, subtotal: Decimal, empresa, contexto: dict | None = None) -> dict:
        # Puede delegar en apps.fiscal (strangler fig) con import perezoso:
        from apps.fiscal.services import calcular_iva_igtf  # noqa: PLC0415
        return calcular_iva_igtf(subtotal=subtotal, empresa=empresa, contexto=contexto or {})
```

> El import perezoso dentro del método evita romper el arranque de apps y mantiene el registro seguro durante la carga.

## Criterio de salida de la extracción

Una empresa de prueba **no venezolana** opera el ciclo comercial completo (cotización→factura→cobro→asiento) **sin ver IGTF, doble tasa ni métodos de pago venezolanos**, y una empresa venezolana sigue teniendo todo. Eso prueba que la localización es realmente enchufable.

## Anti-patrones

### Anti-patrón 1: preguntar por el país en el core
```python
# MAL — el core conoce Venezuela
if empresa.pais == "VE":
    iva = subtotal * Decimal("0.16")

# BIEN — el core pide al puerto; la lógica VE vive en localizacion_ve
motor = get_localizacion(empresa).get("MotorImpuestos", MotorImpuestosNoOp())
resultado = motor.calcular(subtotal=subtotal, empresa=empresa)
```

### Anti-patrón 2: hardcodear constantes de país en un módulo del core
```python
# MAL — IGTF/RIF/SENIAT/0.16 dentro de apps/ventas, apps/inventario, etc.
# BIEN — esas constantes y reglas viven en apps/localizacion_ve detrás de un puerto
```

### Anti-patrón 3: lógica de cálculo con I/O incrustado
```python
# MAL — la regla de IVA lee la BD adentro; no es pura, no se puede extraer ni testear sola
def calcular_iva(factura):
    rate = TasaIVAEmpresa.objects.get(...)   # I/O mezclado con cálculo

# BIEN — función pura; el I/O se hace afuera y se pasa el rate como Decimal
def calcular_iva(base: Decimal, alicuota: Decimal) -> Decimal: ...
```

### Anti-patrón 4: el core importa la localización directamente
```python
# MAL
from apps.localizacion_ve.adapters import MotorImpuestosVE   # acopla el core a VE

# BIEN — el core usa el registry/resolver; solo el registro conoce las localizaciones
```

## Checklist final

- [ ] Ninguna rama `if pais == "VE"` ni constante VE (IVA/IGTF/RIF/SENIAT) vive en el core.
- [ ] La lógica país-específica nueva entra por uno de los seis puertos.
- [ ] Las reglas de cálculo nuevas son puras (sin I/O) y testeables sin BD.
- [ ] El core resuelve la implementación con `get_localizacion(empresa)`, no por import directo.
- [ ] Si la capa está desactivada, el No-Op deja al core operar genérico.
- [ ] Empresa no venezolana puede completar el ciclo comercial sin ver tropicalización VE.

## Referencias

- Código: `apps/localizacion/ports.py` (puertos + No-Op), `apps/localizacion/registry.py`, `apps/localizacion/services.py`, `apps/localizacion_ve/adapters.py`.
- Skill: `omni-venezuela-fiscal` (Capa A), `omni-multimoneda-tasas` (Capa B), `omni-decimal-money`.
- ADR-007 (localización de dos capas), Plan Maestro §3.7 y §5.2-bis.

## Changelog

### v1.0
- Versión inicial, basada en `apps/localizacion/` y `apps/localizacion_ve/`.
