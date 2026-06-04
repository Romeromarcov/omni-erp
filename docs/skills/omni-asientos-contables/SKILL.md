---
name: omni-asientos-contables
description: Use this skill whenever you write or modify code that creates, confirms, or reverses a business document with accounting impact in the Omni project — invoices (sale/purchase), inventory movements, payments (CxC/CxP), receptions, adjustments. Triggers include any work calling `generar_asiento`/`generar_asiento_o_fallar`, touching `apps/contabilidad/`, `AsientoContable`/`DetalleAsiento`/`MapeoContable`, or implementing R-CODE-11 (every accounting movement auto-generates its journal entry inside the same `@transaction.atomic`). Apply it whenever money or stock changes hands in a way the ledger must reflect. Do NOT use for read-only reports, non-accounting CRUD, or frontend.
---

# Skill: Asientos Contables Automáticos (R-CODE-11)

## Cuándo usar esta skill

Cargá esta skill cuando una operación de negocio tiene **impacto contable**:
- Emitir factura de venta o de compra.
- Registrar un movimiento de inventario (recepción, ajuste, salida interna).
- Registrar un pago de CxC o CxP.
- Cualquier documento que el libro mayor deba reflejar.

No la cargués para reportes de solo lectura, CRUD sin impacto contable, ni frontend.

## La regla inviolable: R-CODE-11

> **Todo movimiento contable genera su asiento automáticamente, en la MISMA `@transaction.atomic` del documento origen. Si el asiento falla, la transacción principal falla.**

No hay "registrar la factura ahora y el asiento después". O ambos quedan, o ninguno. Esto garantiza que la contabilidad **nunca** se desincronice de la operación.

## El service central: `generar_asiento_o_fallar`

Vive en `apps/contabilidad/services.py`. **Usá `generar_asiento_o_fallar` en los callsites de negocio**, no `generar_asiento` directo: encapsula la política de "contabilidad activa vs. inactiva" de forma uniforme.

```python
from django.db import transaction
from apps.contabilidad.services import generar_asiento_o_fallar


@transaction.atomic
def emitir_factura(empresa, usuario, datos):
    factura = FacturaFiscal.objects.create(id_empresa=empresa, estado="EMITIDA", ...)
    # ... descontar stock, actualizar CxC, etc. ...

    # Asiento en la MISMA transacción. Si falla con la empresa en contabilidad
    # activa, rompe todo y revierte la factura:
    asiento, asiento_error = generar_asiento_o_fallar("FACTURA_VENTA", factura, empresa)

    return factura
```

### Política que aplica `generar_asiento_o_fallar`

| Situación | Comportamiento |
|---|---|
| `AsientoError` (descuadre, monto ≤ 0, error real) | **Siempre** se propaga → rompe la transacción. |
| `MapeoContableNoEncontrado` **y** `empresa.contabilidad_activa=True` | Se re-lanza como `AsientoError` → rompe la transacción (la empresa exige contabilidad y falta el mapeo). |
| `MapeoContableNoEncontrado` **y** `empresa.contabilidad_activa=False` | Se loguea WARNING y **continúa sin asiento** (bodega informal, R-PROD-3). Devuelve `(None, str(error))`. |

Esto implementa la filosofía de Omni: una **bodega informal** opera sin plan de cuentas; una **empresa formal** tiene contabilidad automática completa y no puede facturar sin su mapeo configurado.

## Tipos de asiento soportados

Solo estos valores son válidos (`TIPOS_ASIENTO` en `services.py`):

```
FACTURA_VENTA · FACTURA_VENTA_IVA · NOTA_VENTA · FACTURA_COMPRA ·
RECEPCION_MERCANCIA · AJUSTE_INVENTARIO · SALIDA_INTERNA · PAGO_CXC · PAGO_CXP
```

Pasar un tipo fuera de esta lista lanza `AsientoError`. Si necesitás un tipo nuevo: agregalo a `TIPOS_ASIENTO`, creá el `MapeoContable` correspondiente y documentá el par debe/haber.

## Cómo funciona `generar_asiento` por dentro

1. Valida que `tipo` esté en `TIPOS_ASIENTO`.
2. Infiere `empresa` y `monto` del documento si no se pasan (`_extraer_empresa`, `_extraer_monto`).
3. **`monto` debe ser > 0** (Decimal); si no, `AsientoError`.
4. Busca `MapeoContable` activo para `(empresa, tipo)`. Si no existe → `MapeoContableNoEncontrado`.
5. Crea `AsientoContable` (estado `BORRADOR`) + dos `DetalleAsiento` (debe/haber por `monto`).
6. Si `empresa.contabilidad_auto_aprobar=True`, pasa el asiento a `APROBADO`.

El **número de asiento** se genera automáticamente (`AST-<tipo>-<YYYYMMDD>-<hex>`, TZ-aware). El **enlace al documento origen** se guarda como `id_documento_origen` (UUID) + `nombre_modelo_origen` (relación polimórfica del proyecto: no usa `ContentType`).

## Monto explícito (IVA, parciales)

Cuando el monto del asiento no es el total del documento (p. ej. el IVA va a un asiento separado, `FACTURA_VENTA_IVA`), pasalo explícito:

```python
generar_asiento_o_fallar("FACTURA_VENTA", factura, empresa, monto=factura.subtotal)
generar_asiento_o_fallar("FACTURA_VENTA_IVA", factura, empresa, monto=factura.iva_monto)
```

El monto siempre es **Decimal** (ver skill `omni-decimal-money`). `generar_asiento` hace `Decimal(str(monto))` defensivamente, pero pasá Decimal de origen.

## Patrón correcto completo

```python
@transaction.atomic
def confirmar_recepcion(empresa, usuario, recepcion_id):
    recepcion = RecepcionMercancia.objects.select_for_update().get(
        pk=recepcion_id, id_empresa=empresa,
    )
    recepcion.estado = "CONFIRMADA"
    recepcion.save(update_fields=["estado"])

    # Actualizar stock (otra escritura en la misma transacción)
    aplicar_entrada_stock(recepcion)

    # Asiento — si falla con contabilidad activa, revierte recepción + stock
    generar_asiento_o_fallar("RECEPCION_MERCANCIA", recepcion, empresa)

    return recepcion
```

## Anti-patrones

### Anti-patrón 1: asiento fuera de la transacción
```python
# MAL — la factura se guarda aunque el asiento falle: contabilidad desincronizada
factura.save()
generar_asiento_o_fallar("FACTURA_VENTA", factura, empresa)  # sin @transaction.atomic

# BIEN — todo dentro de @transaction.atomic; si el asiento rompe, revierte la factura
```

### Anti-patrón 2: asiento "para después"
```python
# MAL — "registro la venta ahora y genero el asiento en un Celery task nocturno"
# Viola R-CODE-11. El asiento es síncrono y atómico con el documento.
```

### Anti-patrón 3: tragarse el AsientoError
```python
# MAL — silencia un descuadre real
try:
    generar_asiento(...)
except Exception:
    pass   # ¡la operación queda sin contabilidad y nadie se entera!

# BIEN — usar generar_asiento_o_fallar, que propaga AsientoError y respeta la política
```

### Anti-patrón 4: llamar generar_asiento directo en negocio
```python
# MAL — no maneja el caso bodega informal; revienta donde debería continuar
generar_asiento("FACTURA_VENTA", factura, empresa)

# BIEN — el wrapper aplica la política contabilidad_activa correctamente
generar_asiento_o_fallar("FACTURA_VENTA", factura, empresa)
```

### Anti-patrón 5: monto cero o negativo
```python
# MAL — asiento de monto 0 (AsientoError); revisá la lógica que produjo ese monto
# BIEN — garantizá monto > 0 antes; si legítimamente es 0, no generes asiento
```

## Tests

```python
class TestAsientoFacturaVenta(TestCase):
    def setUp(self):
        self.empresa = EmpresaFactory(contabilidad_activa=True, contabilidad_auto_aprobar=False)
        MapeoContableFactory(id_empresa=self.empresa, tipo_asiento="FACTURA_VENTA")

    def test_genera_asiento_en_borrador(self):
        factura = FacturaFiscalFactory(id_empresa=self.empresa, total=Decimal("116.00"))
        asiento, err = generar_asiento_o_fallar("FACTURA_VENTA", factura, self.empresa)
        self.assertIsNone(err)
        self.assertEqual(asiento.estado_asiento, "BORRADOR")
        self.assertEqual(asiento.detalles.count(), 2)

    def test_sin_mapeo_con_contabilidad_activa_rompe(self):
        empresa = EmpresaFactory(contabilidad_activa=True)  # sin mapeo
        factura = FacturaFiscalFactory(id_empresa=empresa, total=Decimal("100"))
        with self.assertRaises(AsientoError):
            generar_asiento_o_fallar("FACTURA_VENTA", factura, empresa)

    def test_sin_mapeo_bodega_informal_continua(self):
        empresa = EmpresaFactory(contabilidad_activa=False)  # bodega informal
        factura = FacturaFiscalFactory(id_empresa=empresa, total=Decimal("100"))
        asiento, err = generar_asiento_o_fallar("FACTURA_VENTA", factura, empresa)
        self.assertIsNone(asiento)
        self.assertIsNotNone(err)   # operación continúa sin asiento

    def test_atomicidad_revierte_factura_si_asiento_falla(self):
        # Si el asiento rompe, la factura no debe quedar en BD.
        ...
```

## Checklist final

- [ ] El asiento se genera **dentro** de la misma `@transaction.atomic` del documento.
- [ ] Se usa `generar_asiento_o_fallar` (no `generar_asiento` directo) en código de negocio.
- [ ] El `tipo` está en `TIPOS_ASIENTO`; si es nuevo, hay `MapeoContable` y se documentó.
- [ ] El `monto` es Decimal y > 0.
- [ ] No se traga `AsientoError`.
- [ ] Hay tests para: asiento OK, sin mapeo + contabilidad activa (rompe), sin mapeo + bodega informal (continúa), atomicidad (revierte si falla).

## Referencias

- Código: `apps/contabilidad/services.py` (`generar_asiento`, `generar_asiento_o_fallar`, `TIPOS_ASIENTO`), `apps/contabilidad/models.py` (`AsientoContable`, `DetalleAsiento`, `MapeoContable`).
- Skill: `omni-decimal-money`, `omni-multi-tenant-isolation`, `omni-django-module`.
- Regla R-CODE-11, ADR-006 (asientos automáticos), CTF-001 (asiento separado de IVA).

## Changelog

### v1.0
- Versión inicial, basada en `apps/contabilidad/services.py`.
