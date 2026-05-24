---
name: omni-venezuela-fiscal
description: Use this skill whenever you write or modify code that touches Venezuelan tax calculations, fiscal documents, or SENIAT-related functionality in the Omni project. Triggers include any work involving IVA (VAT), IGTF (financial transactions tax in foreign currency), retentions (retenciones de IVA o ISLR), libros fiscales (purchase/sales books for SENIAT), facturas fiscales (fiscal invoices), notas de débito/crédito, RIF validation, fiscal serial numbers, contribuyente especial logic, or any tax-related calculation specific to Venezuela. Apply this skill carefully whenever fiscal accuracy matters legally. Do NOT use for non-fiscal financial calculations (use omni-decimal-money instead) or for fiscal regulations of other countries.
---

# Skill: Fiscalidad Venezolana en Omni

## Cuándo usar esta skill

Cargá esta skill cuando trabajés en:
- Cálculo de IVA (alícuota general, reducida, adicional, exento, exonerado).
- Cálculo de IGTF (3% sobre divisas y crypto).
- Retenciones de IVA (75% o 100% según contribuyente).
- Retenciones de ISLR.
- Generación de facturas fiscales.
- Notas de crédito y notas de débito.
- Libros de compras y ventas para SENIAT.
- Validación de RIF.
- Lógica de contribuyentes especiales.
- Series y numeración fiscal.

No la cargués para:
- Cálculos no fiscales (usar `omni-decimal-money`).
- Fiscalidad de otros países (usar skills correspondientes cuando se creen).

## Por qué esta skill es crítica

**Errores en cálculos fiscales generan multas SENIAT, problemas con clientes, y potencialmente cierre del negocio del cliente.** Esto no es exageración; en Venezuela las sanciones por facturación incorrecta son severas.

Adicionalmente, muchas de las reglas son contraintuitivas y específicas. El agente IA no las conoce sin esta skill.

## Marco general: el sistema fiscal venezolano

### Alícuotas de IVA vigentes

| Tipo | Alícuota | Cuándo aplica |
|------|----------|----------------|
| **General** | 16% | Mayoría de bienes y servicios |
| **Reducida** | 8% | Lista taxativa: alimentos básicos, medicamentos esenciales, vivienda, transporte (verificar lista actual) |
| **Adicional** | 31% | Bienes suntuarios (autos de lujo, joyas, licores premium, etc.) |
| **Exento** | 0% | Operaciones explícitamente exentas por ley |
| **Exonerado** | 0% | Operaciones exoneradas por decreto temporal |
| **No sujeto** | 0% | Operaciones fuera del ámbito del IVA |

**Importante:** "Exento" y "Exonerado" se reportan distinto en libros fiscales aunque el IVA sea 0 en ambos.

### Constantes recomendadas

```python
from decimal import Decimal

# Alícuotas de IVA
IVA_ALICUOTA_GENERAL = Decimal('16.0000')
IVA_ALICUOTA_REDUCIDA = Decimal('8.0000')
IVA_ALICUOTA_ADICIONAL = Decimal('31.0000')
IVA_EXENTO = Decimal('0.0000')

# IGTF
IGTF_ALICUOTA = Decimal('3.0000')

# Retenciones
RETENCION_IVA_75 = Decimal('75.0000')  # Porcentaje del IVA
RETENCION_IVA_100 = Decimal('100.0000')

# Estos valores deben venir del paquete de localización VE,
# no hardcoded en módulos. Acá los nombro para referencia.
```

**No hardcodear estos valores en código de negocio.** Vienen del paquete de localización (módulo `localizacion_vzla` o similar).

## IGTF (Impuesto a las Grandes Transacciones Financieras)

### Cuándo aplica

El IGTF aplica al 3% en estas operaciones:
- Pagos en moneda extranjera (USD, EUR) hechos por personas no contribuyentes especiales.
- Pagos en cripto (USDT, BTC, etc.).
- Transferencias en divisas a cuentas extranjeras.
- Retiros en divisas de cuentas en bancos venezolanos.

**Cuándo NO aplica:**
- Pagos en bolívares.
- Pagos en divisas a contribuyentes especiales (que ya retienen el IVA al 100%).
- Algunas excepciones específicas (verificar normativa vigente).

### Cálculo

```python
def calcular_igtf(base_imponible, aplica_igtf):
    """
    base_imponible: monto sobre el cual se calcula (típicamente subtotal + IVA).
    aplica_igtf: bool indicando si la operación está sujeta a IGTF.

    Returns: monto del IGTF a aplicar.
    """
    if not aplica_igtf:
        return Decimal('0.0000')

    return (base_imponible * IGTF_ALICUOTA / Decimal('100')).quantize(
        Decimal('0.0001'),
        rounding=ROUND_HALF_UP,
    )
```

### Cuándo decidir si aplica

Lógica típica:

```python
def aplica_igtf_a_pago(metodo_pago, cliente, empresa):
    """
    Decide si un pago debe llevar IGTF.
    """
    # Empresas contribuyentes especiales se autorretienen IVA al 100%
    # y eso reemplaza al IGTF en algunos casos.
    if empresa.es_contribuyente_especial:
        return False

    # Por método de pago
    metodos_con_igtf = ['EFECTIVO_USD', 'TRANSFERENCIA_USD', 'ZELLE',
                         'USDT_TRC20', 'BINANCE_PAY', 'TARJETA_INTERNACIONAL']

    return metodo_pago in metodos_con_igtf
```

## Retenciones de IVA

### Quién retiene a quién

En VE, los **contribuyentes especiales** son los que retienen IVA al pagarle a sus proveedores (que no son contribuyentes especiales).

Flujo típico:
1. Empresa A (contribuyente especial) compra $1.000 + 16% IVA = $1.160 a Empresa B (no especial).
2. Empresa A paga solamente $1.040 a Empresa B (le retiene 75% del IVA = $120).
3. Empresa A entera al SENIAT esos $120 retenidos en su declaración.
4. Empresa B se acredita esa retención al hacer su propia declaración.

### Porcentajes

| Caso | Retención sobre IVA |
|------|---------------------|
| Operación general entre contribuyente especial y no especial | 75% |
| Operación con casos específicos (servicios profesionales, alquiler, etc.) | 100% |

### Cálculo

```python
def calcular_retencion_iva(monto_iva, porcentaje_retencion):
    """
    monto_iva: el IVA total de la operación.
    porcentaje_retencion: 75.0000 o 100.0000 según el caso.

    Returns: monto retenido.
    """
    retencion = monto_iva * porcentaje_retencion / Decimal('100')
    return retencion.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


# Uso típico
iva_factura = Decimal('160.0000')  # 16% sobre 1000
retencion = calcular_retencion_iva(iva_factura, Decimal('75.0000'))
# retencion = Decimal('120.0000')
monto_a_pagar = monto_factura - retencion
```

### Comprobantes de retención

Toda retención requiere generar un **Comprobante de Retención de IVA** con su propia numeración correlativa, datos fiscales completos, y referencia a la factura original.

## Retenciones de ISLR

### Cuándo aplica

ISLR (Impuesto Sobre La Renta) se retiene en operaciones específicas:
- Pago de honorarios profesionales.
- Pago de servicios técnicos.
- Pago de alquileres.
- Pago a contratistas.
- Otros casos específicos.

**Las tasas y mínimos cambian frecuentemente. Siempre consultá normativa vigente o usá el paquete de localización actualizado.**

### Cálculo simplificado

```python
def calcular_retencion_islr(monto, tipo_servicio, persona_natural=False):
    """
    Estructura general del cálculo. Las tasas y mínimos
    deben venir del paquete de localización VE actualizado.
    """
    config = obtener_config_islr_vigente(tipo_servicio, persona_natural)

    # Verificar mínimo no sujeto
    if monto < config.minimo_no_sujeto:
        return Decimal('0.0000')

    # Calcular sobre el excedente del mínimo
    base = monto - config.minimo_no_sujeto if config.aplica_descuento else monto

    retencion = base * config.tasa / Decimal('100')

    # Restar sustraendo si aplica
    if config.sustraendo:
        retencion -= config.sustraendo

    return max(Decimal('0.0000'), retencion).quantize(
        Decimal('0.0001'),
        rounding=ROUND_HALF_UP,
    )
```

## Estructura de Factura Fiscal

### Datos obligatorios

Toda factura fiscal venezolana debe incluir:

**Encabezado:**
- Razón social del emisor.
- RIF del emisor.
- Dirección fiscal.
- Domicilio fiscal.
- Nombre o razón social del receptor.
- RIF o cédula del receptor.
- Dirección del receptor.
- Número de factura (consecutivo).
- Número de control (de la imprenta digital o SENIAT).
- Fecha de emisión.
- Condición de pago (contado/crédito).

**Cuerpo:**
- Descripción de bienes o servicios.
- Cantidad.
- Precio unitario.
- Total por línea.
- Descuento por línea (si aplica).
- Impuestos por línea o agrupados.

**Pie:**
- Subtotal antes de IVA.
- IVA discriminado por alícuota (importante: si hay productos al 16% y al 8%, mostrar separado).
- IGTF si aplica.
- Total exento (si aplica).
- Total general.
- Forma de pago.

### Numeración correlativa

```python
class SecuenciaFiscal(BaseModel):
    """
    Cada empresa puede tener varias secuencias fiscales activas
    (factura, nota de crédito, nota de débito, comprobante de retención).
    """
    tipo_documento = models.CharField(
        max_length=30,
        choices=[
            ('FACTURA', 'Factura'),
            ('NOTA_CREDITO', 'Nota de Crédito'),
            ('NOTA_DEBITO', 'Nota de Débito'),
            ('COMPROBANTE_RETENCION_IVA', 'Comprobante de Retención IVA'),
            ('COMPROBANTE_RETENCION_ISLR', 'Comprobante de Retención ISLR'),
        ],
    )
    serie = models.CharField(max_length=10, default='A')
    numero_actual = models.IntegerField(default=0)
    numero_inicial = models.IntegerField()
    numero_final = models.IntegerField()

    # Datos de imprenta digital (si aplica)
    rif_imprenta = models.CharField(max_length=15, blank=True)
    fecha_autorizacion = models.DateField(null=True, blank=True)


def obtener_siguiente_numero(empresa, tipo_documento):
    """
    Asegura unicidad y secuencialidad usando select_for_update.
    """
    with transaction.atomic():
        secuencia = SecuenciaFiscal.objects.select_for_update().get(
            id_empresa=empresa,
            tipo_documento=tipo_documento,
            activo=True,
        )

        if secuencia.numero_actual >= secuencia.numero_final:
            raise ValidationError(
                f'Secuencia fiscal de {tipo_documento} agotada. '
                'Solicitar nueva imprenta.'
            )

        secuencia.numero_actual += 1
        secuencia.save()

        return f'{secuencia.serie}-{secuencia.numero_actual:08d}'
```

**Crítico:** la numeración fiscal NUNCA puede tener saltos. Si una factura se anula, no se "reusa" el número; se emite nota de crédito y se sigue con el siguiente número.

## Validación de RIF

### Estructura

Un RIF válido tiene formato `X-NNNNNNNN-N` donde:
- `X`: letra inicial (V, E, J, P, G, R, C, etc.).
- `NNNNNNNN`: 8 dígitos.
- `N`: dígito verificador (0-9).

### Implementación

```python
import re

LETRAS_RIF_VALIDAS = ['V', 'E', 'J', 'P', 'G', 'R', 'C']
PESOS_DIGITO_VERIFICADOR = [3, 2, 7, 6, 5, 4, 3, 2]
PESO_LETRA = {
    'V': 1, 'E': 2, 'J': 3, 'P': 4, 'G': 5, 'R': 6, 'C': 7,
}


def validar_rif(rif):
    """
    Valida formato y dígito verificador de RIF venezolano.

    Returns: True si es válido, False si no.
    """
    rif = rif.strip().upper().replace('-', '')

    # Formato: una letra + 9 dígitos
    if not re.match(r'^[A-Z]\d{9}$', rif):
        return False

    letra = rif[0]
    if letra not in LETRAS_RIF_VALIDAS:
        return False

    digitos = [int(d) for d in rif[1:9]]
    digito_verificador_dado = int(rif[9])

    # Cálculo del dígito verificador
    suma = PESO_LETRA[letra] * 4
    for digito, peso in zip(digitos, PESOS_DIGITO_VERIFICADOR):
        suma += digito * peso

    resto = suma % 11

    if resto < 2:
        digito_calculado = 0 if resto == 0 else 1
    else:
        digito_calculado = 11 - resto

    return digito_calculado == digito_verificador_dado


def formatear_rif(rif):
    """
    Devuelve RIF en formato canónico: X-NNNNNNNN-N
    """
    rif_limpio = rif.strip().upper().replace('-', '')
    return f'{rif_limpio[0]}-{rif_limpio[1:9]}-{rif_limpio[9]}'
```

### Reglas de uso por tipo de letra

| Letra | Quién |
|-------|-------|
| V | Personas naturales venezolanas |
| E | Personas naturales extranjeras |
| J | Personas jurídicas (empresas) |
| P | Pasaporte |
| G | Gobierno |
| R | Reformulado (poco común) |
| C | Comunidades |

## Libros Fiscales SENIAT

### Libro de Compras

Estructura de columnas obligatorias:

| Columna | Contenido |
|---------|-----------|
| 1. Fecha de operación | Fecha de la factura |
| 2. RIF del proveedor | RIF |
| 3. Nombre o razón social | Razón social del proveedor |
| 4. Tipo de documento | F (Factura), NC (Nota Crédito), ND (Nota Débito) |
| 5. Número de documento | Número de la factura |
| 6. Número de control | De la imprenta |
| 7. Total de la operación | Total con IVA |
| 8. Compras sin derecho a crédito fiscal | Si aplica |
| 9. Base imponible | Base sobre la que se calculó IVA |
| 10. Crédito fiscal | El IVA que vas a tomar como crédito |
| 11. IVA retenido | Si aplica |

### Libro de Ventas

Similar estructura con énfasis en:
- Ventas exentas vs gravadas.
- Discriminación por alícuota.
- IVA cobrado.
- IVA retenido por contribuyentes especiales.

### Generación

```python
def generar_libro_compras(empresa, año, mes):
    """
    Genera el libro de compras del mes solicitado.

    Returns: queryset con datos para exportar a Excel/CSV en formato SENIAT.
    """
    facturas = FacturaCompra.objects.filter(
        id_empresa=empresa,
        fecha_emision__year=año,
        fecha_emision__month=mes,
        activo=True,
    ).select_related('proveedor').order_by('fecha_emision', 'numero')

    # Mapping a estructura de libro
    return [
        {
            'fecha_operacion': f.fecha_emision,
            'rif_proveedor': f.proveedor.rif,
            'razon_social': f.proveedor.razon_social,
            'tipo_documento': f.tipo_documento,
            'numero': f.numero,
            'numero_control': f.numero_control,
            'total': f.total,
            'sin_credito_fiscal': f.monto_sin_credito_fiscal,
            'base_imponible': f.base_imponible,
            'credito_fiscal': f.iva_monto,
            'iva_retenido': f.iva_retenido,
        }
        for f in facturas
    ]
```

**Notar:** estos libros se exportan típicamente en Excel con formato exacto que el contador del cliente ya sabe. El paquete de localización VE incluye plantillas.

## Anti-patrones específicos

### Anti-patrón 1: Hardcodear alícuotas

```python
# MAL — la alícuota puede cambiar por ley
iva = subtotal * Decimal('0.16')

# BIEN — viene de configuración
iva = subtotal * (alicuota_iva / Decimal('100'))
```

### Anti-patrón 2: No discriminar IVA por alícuota

```python
# MAL — sumás todo en un campo iva_total
factura.iva_total = sum(linea.iva for linea in lineas)

# BIEN — discriminás por alícuota
factura.iva_general = sum(l.iva for l in lineas if l.alicuota == 16)
factura.iva_reducido = sum(l.iva for l in lineas if l.alicuota == 8)
factura.iva_adicional = sum(l.iva for l in lineas if l.alicuota == 31)
```

### Anti-patrón 3: Reusar números de factura

```python
# MAL — anulás factura 100 y reusás el número 100 en la próxima
# Cuando SENIAT audita y ve duplicidad, multa.

# BIEN — número 100 queda anulado para siempre, próxima factura es 101.
# Si necesitás corregir, emitís nota de crédito (con su propia numeración).
```

### Anti-patrón 4: Aplicar IGTF en bolívares

```python
# MAL
if monto > 0:
    igtf = monto * Decimal('0.03')

# BIEN
if metodo_pago in METODOS_QUE_GENERAN_IGTF:
    igtf = monto * Decimal('0.03')
else:
    igtf = Decimal('0')
```

### Anti-patrón 5: No guardar la tasa BCV usada

```python
# MAL
factura.total_ves = factura.total_usd * tasa_bcv_actual()
# Si auditan en 6 meses, ¿qué tasa se usó?

# BIEN
tasa = obtener_tasa_bcv(fecha=factura.fecha_emision)
factura.total_ves = factura.total_usd * tasa.valor
factura.tasa_cambio_aplicada = tasa.valor
factura.tasa_cambio_fuente = 'BCV'
factura.tasa_cambio_fecha = tasa.fecha
factura.save()
```

### Anti-patrón 6: No validar RIF antes de guardar

```python
# MAL
cliente.rif = rif_input
cliente.save()

# BIEN
if not validar_rif(rif_input):
    raise ValidationError('RIF inválido.')
cliente.rif = formatear_rif(rif_input)
cliente.save()
```

### Anti-patrón 7: Mezclar libros fiscales con reportes gerenciales

```python
# MAL — un solo "reporte de ventas" que sirve para todo
def reporte_ventas(empresa, mes):
    # ...

# BIEN — separar
def libro_ventas_seniat(empresa, año, mes):
    """Para SENIAT, formato exacto regulatorio."""
    pass

def reporte_gerencial_ventas(empresa, año, mes):
    """Para el dueño, con métricas de negocio."""
    pass
```

### Anti-patrón 8: Confundir contribuyente especial con regular

La condición de contribuyente especial cambia toda la lógica de retenciones. Es un atributo crítico del cliente y de la empresa.

```python
class Empresa(BaseModel):
    # ...
    es_contribuyente_especial = models.BooleanField(default=False)
    fecha_designacion_contribuyente_especial = models.DateField(null=True, blank=True)

class Cliente(BaseModel):
    # ...
    es_contribuyente_especial = models.BooleanField(default=False)
```

## Casos límite y dudas comunes

### "Mi cliente paga en USD pero quiere factura en VES"

Estructura común:
- La factura se emite en VES con tasa BCV del día.
- En notas se indica equivalente USD.
- El pago en USD se contabiliza con la tasa del día del pago (puede haber diferencia en cambio).
- Si aplica IGTF, se calcula sobre el monto en VES.

### "Operación entre dos contribuyentes especiales"

Cuando ambas empresas son contribuyentes especiales:
- IVA se factura normalmente.
- NO hay retención de IVA (se autorretienen en su declaración).
- El IGTF puede aplicar o no según el método de pago.

### "Factura anulada el mismo día"

- El número fiscal se mantiene anulado (no se reusa).
- Si el cliente ya pagó, se emite nota de crédito por el monto.
- Si nadie pagó nada, basta con marcar la factura como anulada (con motivo documentado).

## Checklist final

Antes de cerrar PR que toca código fiscal:

- [ ] Las alícuotas vienen de configuración, no hardcoded.
- [ ] El IVA se discrimina por alícuota cuando aplica.
- [ ] El IGTF se aplica solo cuando corresponde (método de pago, tipo de empresa).
- [ ] Las retenciones se calculan correctamente según contribuyente.
- [ ] La numeración fiscal es secuencial y no reutilizable.
- [ ] Si hay conversión USD/VES, se guarda snapshot de tasa.
- [ ] Validación de RIF aplicada en inputs de clientes/proveedores.
- [ ] Si tocaste libros fiscales, el formato coincide con requerimiento SENIAT.
- [ ] Tests cubren casos típicos y casos límite.
- [ ] Validación cruzada con un contador real cuando hay duda regulatoria.

## Cuándo escalar al humano

**Siempre escalar antes de implementar cuando:**
- Aparece un caso fiscal nuevo no cubierto en esta skill.
- La normativa SENIAT cambió recientemente y no estás seguro de la versión vigente.
- El cálculo da un resultado que parece raro (incluso si parece "matemáticamente correcto").
- El cliente piloto reporta que un cálculo no coincide con lo que su contador esperaba.

**El responsable o un contador externo deben validar antes de mergear.**

## Referencias

- Skill: `omni-decimal-money` (manejo de Decimal en cálculos).
- Skill: `omni-bcv-rates` (cuando se cree, manejo de tasas BCV).
- Skill: `omni-localization-pack` (cuando se cree, empaquetado de la localización VE).
- Documento: `OMNI_ERP_MASTER_PLAN.md` sección 6.1 (fiscalidad VE detallada del proyecto).
- SENIAT: portal oficial, normativa vigente.
- Providencias administrativas SENIAT (consultar las vigentes para imprenta digital, libros, etc.).

## Disclaimer importante

**Esta skill es referencia para implementación, no asesoramiento fiscal.** Las regulaciones cambian. Cuando haya duda regulatoria, consultar con contador venezolano vigente. La validación legal de cualquier cálculo es responsabilidad del cliente y su contador, no del software.

## Changelog

### v1.0 — Día 1
- Versión inicial.
