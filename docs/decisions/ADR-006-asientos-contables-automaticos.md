# ADR-006: Asientos Contables Automáticos Obligatorios (R-CODE-11)

**Estado:** Aceptado
**Fecha:** 2026-05-16
**Autor(es):** Marco Romero, Claude Sonnet 4.6

## Contexto

Durante la auditoría de código previa a Fase 1 se detectó que ningún módulo existente genera asientos contables automáticamente. La aprobación de facturas, la recepción de mercancías y los pagos modifican el estado operativo del sistema pero dejan la contabilidad en blanco. Esto obliga a una doble entrada manual que es propensa a errores, inconsistente con el enfoque AI-nativo del sistema y bloqueante para cualquier cliente real.

Los módulos con impacto contable identificados:
- `ventas`: emisión de FacturaFiscal → ingreso + CxC
- `compras`: aprobación de FacturaCompra → gasto + CxP; RecepcionMercancia → valuación de inventario
- `cuentas_por_cobrar`: abono/pago → CxC vs. caja/banco
- `inventario`: AjusteInventario → pérdida/ganancia de inventario
- `rrhh/nomina` (Fase 2): nómina → gasto sueldos + pasivos

La alternativa de "asientos batch" o "asientos manuales" se descartó porque en el contexto venezolano (alta inflación, fiscalización SENIAT, auditorías frecuentes) la divergencia entre movimientos operativos y registros contables crea riesgo legal real.

## Decisión

**Todo módulo que genere una transacción con contrapartida contable debe crear su `AsientoContable` dentro de la misma transacción Django (`@transaction.atomic`). Esta regla es R-CODE-11 y bloquea merge.**

Implementación estándar:

```python
# contabilidad/services.py
@transaction.atomic
def generar_asiento(tipo: str, documento, empresa) -> AsientoContable:
    """
    tipo: 'FACTURA_VENTA' | 'FACTURA_COMPRA' | 'RECEPCION_MERCANCIA' |
          'AJUSTE_INVENTARIO' | 'PAGO_CXC' | 'PAGO_CXP' | ...
    """
    asiento = AsientoContable.objects.create(
        id_empresa=empresa,
        tipo=tipo,
        id_documento_origen=documento.pk,
        nombre_modelo_origen=documento.__class__.__name__,
        estado='BORRADOR',
    )
    _poblar_detalles(asiento, tipo, documento)
    if empresa.contabilidad_auto_aprobar:
        asiento.estado = 'APROBADO'
        asiento.save(update_fields=['estado'])
    return asiento
```

El servicio del módulo de origen llama a `generar_asiento()` dentro de su propio `@transaction.atomic`. Si `generar_asiento()` lanza excepción, toda la transacción (incluyendo el documento de origen) se revierte.

El campo `empresa.contabilidad_auto_aprobar` (booleano, default `False`) permite que empresas avanzadas aprueben asientos inmediatamente; empresas conservadoras los revisan primero en estado `BORRADOR`.

## Alternativas consideradas

1. **Asientos batch (cron nocturno)** — descartada. Genera divergencia temporal entre estado operativo y contable. En Venezuela, una auditoría puede llegar sin aviso; el sistema debe estar conciliado en todo momento.
2. **Asientos manuales post-operación** — descartada. Doble trabajo, propensa a olvidos, incompatible con el objetivo AI-nativo. Si el usuario debe hacer algo dos veces, el sistema falla en su promesa.
3. **Señales Django (post_save signals)** — descartada. Las señales no garantizan que corran dentro de la misma transacción que el evento que las dispara, y son difíciles de testear aisladamente. La llamada explícita al servicio es más predecible.
4. **ORM hooks / overrides de `save()`** — descartada. Acoplamiento excesivo; dificulta migraciones y datos de seed en tests.

## Consecuencias

**Positivas:**
- Consistencia garantizada: si el documento existe, el asiento existe. Si el asiento falló, el documento no existe.
- Auditoría inmediata: en cualquier momento, el estado contable refleja el estado operativo.
- Testeable: `generar_asiento()` es una función pura con respecto a sus efectos secundarios; se prueba con un documento fixture y se verifica el asiento resultante.
- Compatible con SENIAT: los libros de compra/venta se generan directamente de los asientos, no de los documentos operativos.

**Negativas:**
- Requiere que el Plan de Cuentas esté configurado antes de operar cualquier módulo con impacto contable. El onboarding debe cubrir esto.
- El primer setup de mapeo cuenta-tipo_asiento es trabajo de configuración no trivial (mitigado por el wizard de onboarding de Fase 1).
- Errores en la lógica de asientos bloquean operaciones — hay que mantener la lógica de generación robusta y con manejo de errores claro.

**Neutrales:**
- `empresa.contabilidad_auto_aprobar=False` (default) permite que el sistema funcione aunque el contador no haya configurado el plan de cuentas completo — los asientos quedan en BORRADOR hasta que alguien los apruebe manualmente.

## Cómo revisitar esta decisión

Si en Fase 2 aparecen módulos de alta frecuencia (ej.: IoT con miles de movimientos por hora), se evalúa un modo "asiento diferido con garantía de consistencia" para ese módulo específico — pero como excepción explícita con ADR propio, no como regla general.
