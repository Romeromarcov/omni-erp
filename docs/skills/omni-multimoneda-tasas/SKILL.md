---
name: omni-multimoneda-tasas
description: Use this skill whenever you write or modify code involving multiple currencies, exchange rates, or mixed payment methods in the Omni project (Capa B — market dynamics). Triggers include any work with VES/USD/USDT amounts, dual rate (BCV official + parallel/real), rate snapshots, `TasaCambio`, BCV cascade / Binance P2P sources, currency conversion, mixed Venezuelan payment methods (Pago Móvil, Zelle, USDT, divisas efectivo), IGTF triggered by payment method, third-party payments (Zelle de terceros), or `OperacionCambioDivisa`. Apply it whenever an operation records value that must be expressed in more than one currency or rate. Do NOT use for single-currency generic logic, pure fiscal tax math (use omni-venezuela-fiscal), or frontend.
---

# Skill: Multimoneda y Tasas de Cambio (Capa B — dinámica de mercado)

## Cuándo usar esta skill

Cargá esta skill cuando trabajés con:
- Montos en más de una moneda (VES, USD, USDT) en la misma operación.
- Doble tasa: oficial (BCV) + custom/paralela (real).
- Snapshot de tasa para auditoría.
- Métodos de pago mixtos venezolanos y su efecto (IGTF por método).
- Pagos de terceros (Zelle/nómina de terceros), cambios de divisa.

No la cargués para lógica de una sola moneda, cálculo fiscal puro (usá `omni-venezuela-fiscal`), ni frontend.

## Dónde encaja

Esto es **Capa B (dinámica de mercado)** de la localización (ver `omni-localizacion-l10n`): no es ley, pero la operación real venezolana lo exige. Es un **diferenciador clave** de Omni frente a un ERP importado. A término vive detrás de los puertos `ProveedorTasas` y `MetodosPagoLocales` de `localizacion_ve`.

## Reglas centrales

1. **Dinero = Decimal, siempre.** Nunca `float`. Tasas con 8 decimales, montos con 4 (intermedios) / 2 (cliente final). Ver `omni-decimal-money`.
2. **Doble tasa en cada operación relevante:** cada movimiento registra su equivalente en USD a **tasa oficial (BCV)** y a **tasa real/paralela**. Campos tipo `tasa_bcv`/`monto_usd_bcv` + `tasa_real`/`monto_real_usd`.
3. **Snapshot obligatorio:** cuando convertís, **guardás la tasa usada** (valor, fuente, fecha). Sin eso, una auditoría a 6 meses no puede reconstruir el cálculo.
4. **No sumar monedas distintas sin convertir.** Decidí explícitamente la moneda base del total.
5. **El total a cobrar al cliente se expresa en la moneda base de la empresa**, con los equivalentes registrados.

## Modelo con doble tasa (patrón)

```python
from decimal import Decimal

class MovimientoCaja(BaseModel):
    monto = models.DecimalField(max_digits=18, decimal_places=4)
    moneda = models.CharField(max_length=3)          # 'VES' | 'USD' | 'USDT'

    # Snapshot de tasa OFICIAL (BCV)
    tasa_bcv = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    monto_usd_bcv = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)

    # Snapshot de tasa REAL (paralela / custom)
    tasa_real = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    monto_real_usd = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)

    tasa_fuente = models.CharField(max_length=20, blank=True)   # 'BCV' | 'BINANCE_P2P' | 'CUSTOM'
    tasa_fecha = models.DateField(null=True, blank=True)
```

> `null=True` aquí es legítimo cuando la moneda del movimiento ya es la base (no hay conversión). Para campos lógicamente obligatorios, sigue aplicando R-CODE-10.

## Fuentes de tasa (cascade)

Las tasas vienen multi-fuente, con fallback en cascada (conector `tasas_ve` del Integration Hub):
- **BCV oficial:** dolarapi → exchangedynamic → scrape `bcv.org.ve` (workaround SSL). En cascada: si una fuente falla, se intenta la siguiente.
- **Paralelo/real:** Binance P2P (promedio de 5 órdenes BUY + 5 SELL).
- Pares: `USD_VES`, `EUR_VES`, con tasa en fecha histórica.

**Nunca pegues HTTP directo a estas APIs desde un módulo de negocio** — pasa por el Integration Hub (ver `omni-integration-hub`). Y al recibir el valor, convertilo a Decimal **vía string**:

```python
tasa = Decimal(str(respuesta_api["tasa"]))   # nunca Decimal(float)
```

## Conversión y snapshot (patrón)

```python
from decimal import Decimal, ROUND_HALF_UP

def registrar_con_doble_tasa(movimiento, tasa_bcv: Decimal, tasa_real: Decimal):
    """Calcula y persiste los equivalentes USD a ambas tasas (snapshot)."""
    if movimiento.moneda == "VES":
        movimiento.tasa_bcv = tasa_bcv
        movimiento.monto_usd_bcv = (movimiento.monto / tasa_bcv).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP)
        movimiento.tasa_real = tasa_real
        movimiento.monto_real_usd = (movimiento.monto / tasa_real).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP)
        movimiento.tasa_fuente = "BCV+BINANCE_P2P"
        movimiento.tasa_fecha = timezone.now().date()
    movimiento.save()
```

## Métodos de pago mixtos e IGTF

El método de pago determina si aplica **IGTF (3% sobre divisas/crypto)** — no el monto, ni la moneda sola. Ver detalle fiscal en `omni-venezuela-fiscal`.

```python
METODOS_QUE_GENERAN_IGTF = {
    "EFECTIVO_USD", "TRANSFERENCIA_USD", "ZELLE",
    "USDT_TRC20", "BINANCE_PAY", "TARJETA_INTERNACIONAL",
}
# Pago en VES (efectivo VES, Pago Móvil, transferencia VES) → NO IGTF.
```

## Pagos de terceros (dinámica clave VE)

Por restricciones de USD, un pago se recibe/emite a través de la cuenta de un proveedor. Acciones:
- **Abonar:** reduce CxP del proveedor como pago en USD.
- **Solicitar reintegro:** genera CxC contra el proveedor (comisión opcional + asiento contable).
- **Asociar proveedor** a un cobro originado en caja.

Aplica a **Zelle de terceros** y a nómina/proveedores de terceros. Cada movimiento de estos genera su asiento (ver `omni-asientos-contables`) y, si convierte moneda, su snapshot de tasa.

## Cambios de divisa

`OperacionCambioDivisa` (`apps/tesoreria`, con comisiones y CRUD) modela la conversión moneda→moneda con **doble registro** (egreso en una moneda + ingreso en otra) y su asiento contable. Usá esa primitiva, no sumes/restes saldos a mano.

## Libro maestro de flujo de caja

El "maestro de operaciones" es un ledger unificado que normaliza ingresos/egresos de **todos** los orígenes (ventas, compras, nómina, gastos, pagos fiscales, cambios de divisa, Zelle de terceros) con su **doble equivalencia en USD**. Si tu feature genera un movimiento de caja, debe poder reflejarse ahí con sus dos equivalencias.

## Anti-patrones

### Anti-patrón 1: float o Decimal(float) para tasas
```python
# MAL
tasa = Decimal(36.50)            # imprecisión de float
monto_usd = monto_ves / 36.50    # float

# BIEN
tasa = Decimal("36.50000000")
monto_usd = (monto_ves / tasa).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
```

### Anti-patrón 2: no guardar el snapshot de tasa
```python
# MAL — usa la tasa de hoy y no la persiste; auditoría imposible
factura.total_ves = factura.total_usd * tasa_bcv_actual()

# BIEN — persistí valor, fuente y fecha de la tasa usada
factura.tasa_cambio_aplicada = tasa.valor
factura.tasa_cambio_fuente = "BCV"
factura.tasa_cambio_fecha = tasa.fecha
```

### Anti-patrón 3: sumar monedas distintas
```python
# MAL
total = monto_usd + monto_ves   # sin convertir

# BIEN
total_usd = monto_usd + (monto_ves / tasa)   # moneda base explícita
```

### Anti-patrón 4: registrar una sola tasa cuando la operación exige doble
```python
# MAL — solo BCV; se pierde la realidad del paralelo
# BIEN — monto_usd_bcv (oficial) Y monto_real_usd (paralelo), ambos snapshot
```

### Anti-patrón 5: IGTF por monto/moneda en vez de por método
```python
# MAL
if moneda == "USD": igtf = base * Decimal("0.03")

# BIEN
if metodo_pago in METODOS_QUE_GENERAN_IGTF: igtf = base * Decimal("0.03")
```

### Anti-patrón 6: HTTP directo a la API de tasas
```python
# MAL — requests.get("https://dolarapi...") dentro de un service de negocio
# BIEN — pedir la tasa al Integration Hub / ProveedorTasas (ver omni-integration-hub)
```

## Checklist final

- [ ] Todos los montos y tasas son Decimal (tasas 8 dec; creadas desde string).
- [ ] Operaciones relevantes registran doble equivalente USD (BCV oficial + real/paralelo).
- [ ] Se guarda snapshot: valor de tasa, fuente y fecha.
- [ ] No se suman monedas distintas sin convertir; la moneda base del total es explícita.
- [ ] IGTF se decide por método de pago, no por monto/moneda.
- [ ] Las tasas se obtienen vía Integration Hub / `ProveedorTasas`, no HTTP directo.
- [ ] Pagos de terceros / cambios de divisa usan las primitivas existentes (con su asiento).
- [ ] Tests con redondeos y casos límite (tasas con muchos decimales).

## Referencias

- Código: `apps/finanzas/` (`TasaCambio`, `MetodoPago`, conversión), `apps/tesoreria/` (`OperacionCambioDivisa`), conector `tasas_ve` en `apps/integration_hub/`.
- Skill: `omni-decimal-money`, `omni-venezuela-fiscal`, `omni-localizacion-l10n`, `omni-asientos-contables`, `omni-integration-hub`.
- Plan Maestro §3.7 (Capa B), §6 (localización VE). Insumos en proyecto `GestionCxC`.

## Changelog

### v1.0
- Versión inicial.
