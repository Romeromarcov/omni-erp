---
name: omni-decimal-money
description: Use this skill whenever you write code that handles money, prices, amounts, rates, percentages affecting financial values, currency conversions, taxes, discounts, or accounting calculations in the Omni project. Triggers include any task involving DecimalField, monetary computations, IVA/IGTF/retention calculations, multi-currency conversions (USD/VES), price lists, totals, subtotals, payment amounts, change calculations (vuelto), or any operation where rounding errors could affect financial outcomes. Do NOT use for tasks unrelated to financial values such as quantities of items (use IntegerField), dates, or text fields.
---

# Skill: Manejo Correcto de Dinero con Decimal

## Cuándo usar esta skill

Cargá esta skill cuando trabajés con cualquier valor que represente:
- Precio, monto, total, subtotal.
- Tasa de cambio, tipo de cambio.
- Porcentaje que afecta valores monetarios (IVA, descuento, comisión).
- Cantidad de impuesto, retención.
- Saldo, deuda, crédito.
- Comisiones, márgenes, costos.

No la cargués para:
- Cantidades de items (usar `IntegerField` o `PositiveIntegerField`).
- Pesos físicos, longitudes (usar `DecimalField` pero sin las reglas de dinero).
- Fechas, horas, identificadores.

## La regla central

**Para dinero: SIEMPRE Decimal. NUNCA float. Punto.**

```python
# MAL
monto = 100.50
total = precio * 0.16  # IVA

# BIEN
from decimal import Decimal
monto = Decimal('100.50')
iva_rate = Decimal('0.16')
total = precio * iva_rate
```

## Por qué float está prohibido

Float usa representación binaria que no puede expresar exactamente muchos valores decimales. El clásico ejemplo:

```python
>>> 0.1 + 0.2
0.30000000000000004
```

En código de negocio:

```python
>>> precio = 100.10
>>> cantidad = 3
>>> total = precio * cantidad
>>> total
300.29999999999995
```

Esos errores se acumulan. Tres céntimos perdidos en una factura, multiplicados por miles de transacciones, son problemas reales con clientes y con la SUNDDE/SENIAT.

**Regla R-CODE-4 del proyecto: Decimal siempre.**

## Precisión por tipo de campo

Diferentes contextos necesitan distinta precisión:

| Tipo de valor | DecimalField recomendado | Decimales | Cuándo usar |
|----------------|--------------------------|-----------|-------------|
| **Monto general** | `max_digits=18, decimal_places=4` | 4 | Subtotales, líneas de factura, costos |
| **Total cliente final** | `max_digits=18, decimal_places=2` | 2 | Total a cobrar, total a pagar |
| **Tasa de cambio** | `max_digits=18, decimal_places=8` | 8 | BCV, paralelo, cualquier conversión |
| **Porcentaje** | `max_digits=7, decimal_places=4` | 4 | IVA, descuento, comisión (16.0000%) |
| **Cripto USDT/etc** | `max_digits=18, decimal_places=8` | 8 | Valores en blockchain |
| **Cantidad x Precio (cálculo intermedio)** | usar Decimal nativo, no Field | — | Cálculos en código |

### Cómo elegir

**Para guardar en BD:** ¿hasta cuántos decimales tiene sentido para el caso?
- Total a cobrar al cliente: 2 (céntimos).
- Subtotal de línea: 4 (porque al multiplicar por cantidad, 4 dec evita pérdida de precisión).
- Tasa de cambio: 8 (BCV usa 4-8, otros pueden usar más).

**Para trabajar en código:** Decimal con la precisión del dato más preciso que estés usando, redondear solo al final.

## Ejemplos de modelos

### Modelo de producto con precio

```python
class Producto(BaseModel):
    nombre = models.CharField(max_length=200)

    # Precio: 4 decimales (subtotal en línea de factura)
    precio_unitario = models.DecimalField(
        max_digits=18,
        decimal_places=4,
    )

    # Costo: 4 decimales
    costo_unitario = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal('0.0000'),
    )

    # Margen porcentual: 4 decimales (puede ser 33.3333%)
    margen_porcentaje = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal('0.0000'),
    )
```

### Modelo de factura

```python
from decimal import Decimal

class Factura(BaseModel):
    numero = models.CharField(max_length=20)
    cliente = models.ForeignKey('crm.Cliente', on_delete=models.PROTECT)

    # Subtotal: 4 decimales (suma de líneas)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4)

    # IVA aplicado (alícuota): 4 decimales
    iva_porcentaje = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal('16.0000'),  # 16% por defecto en VE
    )

    # Monto del IVA: 4 decimales
    iva_monto = models.DecimalField(max_digits=18, decimal_places=4)

    # IGTF (3% en VE para divisas)
    igtf_porcentaje = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal('0.0000'),
    )
    igtf_monto = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal('0.0000'),
    )

    # Total final al cliente: 2 decimales (lo que se cobra)
    total = models.DecimalField(max_digits=18, decimal_places=2)
```

### Modelo de tasa de cambio

```python
class TasaCambio(BaseModel):
    moneda_origen = models.CharField(max_length=3)  # 'USD'
    moneda_destino = models.CharField(max_length=3)  # 'VES'
    fuente = models.CharField(max_length=20)  # 'BCV', 'PARALELO', 'INTERNA'
    fecha = models.DateField()

    # Tasa: 8 decimales (BCV usa hasta 8)
    tasa = models.DecimalField(
        max_digits=18,
        decimal_places=8,
    )

    class Meta:
        unique_together = [['id_empresa', 'moneda_origen', 'moneda_destino', 'fuente', 'fecha']]
```

## Cómo hacer aritmética con Decimal

### Crear Decimals

```python
from decimal import Decimal

# CORRECTO: desde string (preserva precisión exacta)
precio = Decimal('100.50')
iva_rate = Decimal('0.16')

# INCORRECTO: desde float (heredás los errores de float)
precio = Decimal(100.50)  # MAL
# Resultado: Decimal('100.5000000000000056843418860808...')
```

### Operaciones básicas

```python
# Suma, resta, multiplicación: directas
subtotal = Decimal('100.50') + Decimal('25.30')  # Decimal('125.80')
total = subtotal * Decimal('1.16')  # Aplica IVA 16%

# División: cuidado con la precisión
porcentaje = Decimal('25') / Decimal('100')  # Decimal('0.25')

# Mezclar Decimal con int es OK
total = Decimal('100.50') * 3  # Decimal('301.50')

# Mezclar Decimal con float ES ERROR
total = Decimal('100.50') * 1.16  # TypeError o pérdida de precisión
```

### Redondeo con `quantize`

```python
from decimal import Decimal, ROUND_HALF_UP

# Redondear a 2 decimales para mostrar al cliente
monto = Decimal('100.5678')
monto_final = monto.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
# Resultado: Decimal('100.57')

# Redondear a 4 decimales para almacenamiento intermedio
monto_4dec = monto.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
```

### Modos de redondeo importantes en VE

```python
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_DOWN

# ROUND_HALF_UP: 0.5 redondea hacia arriba (uso comercial común)
# 100.555 -> 100.56

# ROUND_HALF_EVEN: 0.5 redondea al par más cercano (uso bancario)
# 100.555 -> 100.56, pero 100.565 -> 100.56

# ROUND_DOWN: trunca hacia 0 (truncar para impuestos donde la ley exige)
# 100.567 -> 100.56
```

**Default recomendado para Omni: ROUND_HALF_UP.** Verificá normativa SENIAT cuando se trate de cálculo fiscal específico.

## Ejemplos de cálculos típicos

### Cálculo de IVA

```python
def calcular_iva(base_imponible, alicuota_porcentaje):
    """
    base_imponible: Decimal con 4 decimales
    alicuota_porcentaje: Decimal en formato 16.0000 (no 0.16)

    Returns: Decimal con 4 decimales (monto del IVA)
    """
    if not isinstance(base_imponible, Decimal):
        raise TypeError('base_imponible debe ser Decimal')
    if not isinstance(alicuota_porcentaje, Decimal):
        raise TypeError('alicuota_porcentaje debe ser Decimal')

    # Convertir porcentaje a fracción
    fraccion = alicuota_porcentaje / Decimal('100')

    # Calcular IVA
    iva = base_imponible * fraccion

    # Redondear a 4 decimales
    return iva.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


# Uso
base = Decimal('100.0000')
iva = calcular_iva(base, Decimal('16.0000'))  # Decimal('16.0000')
```

### Cálculo de total con IVA y IGTF

```python
def calcular_total_factura(subtotal, iva_porcentaje, igtf_porcentaje=Decimal('0')):
    """
    subtotal: Decimal con 4 decimales
    iva_porcentaje: Decimal (ej: 16.0000)
    igtf_porcentaje: Decimal (ej: 3.0000 si aplica para divisas)

    Returns: dict con subtotal, iva, igtf, total (todos Decimal)
    """
    iva = calcular_iva(subtotal, iva_porcentaje)
    base_para_igtf = subtotal + iva
    igtf = calcular_iva(base_para_igtf, igtf_porcentaje) if igtf_porcentaje > 0 else Decimal('0.0000')

    total_4dec = subtotal + iva + igtf
    total_2dec = total_4dec.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    return {
        'subtotal': subtotal,
        'iva': iva,
        'igtf': igtf,
        'total_4dec': total_4dec,
        'total': total_2dec,  # Lo que se cobra
    }
```

### Cálculo de cambio de moneda

```python
def convertir_moneda(monto, tasa):
    """
    monto: Decimal en moneda origen
    tasa: Decimal con tasa de cambio (ej: 36.50000000 USD->VES)

    Returns: Decimal en moneda destino, con 4 decimales
    """
    resultado = monto * tasa
    return resultado.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


# Uso: USD a VES
monto_usd = Decimal('100.0000')
tasa_bcv = Decimal('36.50000000')
monto_ves = convertir_moneda(monto_usd, tasa_bcv)  # Decimal('3650.0000')
```

## Anti-patrones críticos

### Anti-patrón 1: Mezclar float y Decimal

```python
# MAL
total = Decimal('100.50') * 1.16  # 1.16 es float

# BIEN
total = Decimal('100.50') * Decimal('1.16')
```

### Anti-patrón 2: Crear Decimal desde float

```python
# MAL
tasa = Decimal(36.50)  # Hereda imprecisión de float

# BIEN
tasa = Decimal('36.50')  # Desde string

# BIEN si viene de fuente externa
tasa = Decimal(str(valor_de_api))  # Convertir primero a string
```

### Anti-patrón 3: Redondeo prematuro

```python
# MAL
def calcular_factura(items):
    subtotal = Decimal('0')
    for item in items:
        # Redondeás cada línea: pierde precisión acumulada
        linea = (item.precio * item.cantidad).quantize(Decimal('0.01'))
        subtotal += linea
    return subtotal

# BIEN
def calcular_factura(items):
    subtotal = Decimal('0')
    for item in items:
        # Acumulás con precisión completa
        linea = item.precio * item.cantidad
        subtotal += linea
    # Redondeás solo al final, donde mostrás al usuario
    return subtotal.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
```

### Anti-patrón 4: Comparación con float

```python
# MAL
if precio == 100.50:  # comparación con float

# BIEN
if precio == Decimal('100.50'):
```

### Anti-patrón 5: Usar precisión inconsistente

```python
# MAL: el modelo guarda 4 decimales, pero el cálculo usa 2
class Factura(models.Model):
    monto = models.DecimalField(max_digits=18, decimal_places=4)

def calcular(monto):
    return monto.quantize(Decimal('0.01'))  # Reduce precisión innecesariamente

# BIEN: respetá la precisión del modelo en cálculos intermedios
def calcular(monto):
    return monto.quantize(Decimal('0.0001'))  # Coincide con el modelo
```

### Anti-patrón 6: No documentar la moneda

```python
# MAL
class Factura(models.Model):
    monto = models.DecimalField(...)  # ¿USD? ¿VES?

# BIEN
class Factura(models.Model):
    monto = models.DecimalField(...)
    moneda = models.CharField(max_length=3, choices=[('USD', 'USD'), ('VES', 'Bolívares')])
    tasa_cambio_aplicada = models.DecimalField(...)  # Para auditoría
```

### Anti-patrón 7: Sumar montos en distintas monedas

```python
# MAL
total_factura = monto_usd + monto_ves  # Sumando monedas distintas

# BIEN
total_ves = monto_ves + (monto_usd * tasa_cambio)
total_usd = monto_usd + (monto_ves / tasa_cambio)
# Decidir explícitamente en qué moneda expresar el total
```

## Casos venezolanos específicos

### IVA estándar (16%)

```python
IVA_ALICUOTA_GENERAL = Decimal('16.0000')
```

### Alícuota reducida (8% para algunos productos)

```python
IVA_ALICUOTA_REDUCIDA = Decimal('8.0000')
```

### Alícuota adicional (31% para suntuarios)

```python
IVA_ALICUOTA_ADICIONAL = Decimal('31.0000')
```

### IGTF (3% para pagos en divisas)

```python
IGTF_ALICUOTA = Decimal('3.0000')
```

### Tasa BCV

Cuando obtenés la tasa BCV (vía API o scraping), **siempre convertí a Decimal vía string**:

```python
# Resultado de la API:
respuesta_api = {'tasa': '36.5012345'}

# Convertir
tasa_bcv = Decimal(respuesta_api['tasa'])  # Funciona, Decimal acepta string

# Si la API devuelve float (peor caso)
respuesta_api_mal = {'tasa': 36.5012345}
tasa_bcv = Decimal(str(respuesta_api_mal['tasa']))  # Forzar conversión vía string
```

## Almacenar el snapshot de tasa

**Para auditoría fiscal, cuando convertís moneda, guardá la tasa usada:**

```python
class FacturaPago(BaseModel):
    factura = models.ForeignKey('Factura', on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=18, decimal_places=4)
    moneda = models.CharField(max_length=3)

    # Snapshot de tasa al momento del pago
    tasa_cambio_aplicada = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        null=True, blank=True,  # null si la moneda coincide con la base
    )
    tasa_cambio_fuente = models.CharField(
        max_length=20,
        null=True, blank=True,
    )
    tasa_cambio_fecha = models.DateField(
        null=True, blank=True,
    )
```

Esto te permite reconstruir auditorías fiscales meses después.

## Checklist final

Antes de cerrar PR que toca dinero:

- [ ] No hay un solo `float` para valores monetarios.
- [ ] Todos los DecimalField tienen precisión apropiada (4 dec para intermedios, 2 dec para totales finales).
- [ ] Los Decimals se crean desde string, no desde float.
- [ ] No hay redondeo prematuro en cálculos intermedios.
- [ ] El redondeo final usa ROUND_HALF_UP (o documentado si es otro).
- [ ] Si hay conversión de moneda, se guarda snapshot de la tasa.
- [ ] Si hay IVA/IGTF/retenciones, los porcentajes vienen como Decimal.
- [ ] No se suman montos de distintas monedas sin convertir.
- [ ] Hay tests con casos límite (montos con muchos decimales, redondeos).

## Tests recomendados

```python
class TestCalculoFactura(TestCase):
    def test_iva_simple(self):
        base = Decimal('100.0000')
        iva = calcular_iva(base, Decimal('16.0000'))
        self.assertEqual(iva, Decimal('16.0000'))

    def test_iva_con_decimales(self):
        base = Decimal('123.4567')
        iva = calcular_iva(base, Decimal('16.0000'))
        # 123.4567 * 0.16 = 19.753072 -> 19.7531 (HALF_UP)
        self.assertEqual(iva, Decimal('19.7531'))

    def test_no_acepta_float(self):
        with self.assertRaises(TypeError):
            calcular_iva(100.0, Decimal('16'))

    def test_total_factura_redondeo(self):
        resultado = calcular_total_factura(
            subtotal=Decimal('99.9999'),
            iva_porcentaje=Decimal('16.0000'),
        )
        # Subtotal + IVA = 99.9999 + 15.9999... = 115.9999
        # Total a 2 decimales: 116.00
        self.assertEqual(resultado['total'], Decimal('116.00'))
```

## Errores históricos del proyecto

[Documentar acá errores reales detectados en producción o en review, como recordatorio.]

## Referencias

- Skill: `omni-venezuela-fiscal` (cálculos fiscales VE).
- Decisión inmutable A-007: Decimal para dinero.
- Regla R-CODE-4: Decimal para dinero, Float prohibido.
- Documentación Python: https://docs.python.org/3/library/decimal.html

## Changelog

### v1.0 — Día 1
- Versión inicial.
