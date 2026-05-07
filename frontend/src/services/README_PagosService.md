# Servicio de Pagos Unificado

Este documento explica cómo usar el nuevo servicio unificado de pagos que reemplaza los servicios específicos de cada módulo.

## 🎯 Visión General

El servicio `pagosService` proporciona una API unificada para manejar pagos en todo el ERP, eliminando la necesidad de servicios específicos por módulo.

## 📋 Tipos de Documentos Soportados

| Tipo de Documento | Operación | Descripción |
|-------------------|-----------|-------------|
| `PEDIDO` | INGRESO | Pagos de pedidos de venta |
| `NOTA_VENTA` | INGRESO | Pagos de notas de venta |
| `FACTURA` | INGRESO | Pagos de facturas fiscales |
| `CXP` | EGRESO | Pagos de cuentas por pagar |
| `GASTO` | EGRESO | Pagos de gastos |
| `REEMBOLSO_GASTO` | EGRESO | Pagos de reembolsos de gastos |
| `NOMINA` | EGRESO | Pagos de nóminas |
| `IMPUESTO` | EGRESO | Pagos de impuestos/contribuciones |

## 🚀 Uso Básico

### Importar el servicio

```typescript
import { pagosService } from '../services/pagosService';
```

### Crear un pago genérico

```typescript
// Crear pago para cualquier documento
const pago = await pagosService.createPagoDocumento('PEDIDO', 'pedido-123', {
  monto: 100.50,
  id_metodo_pago: 'metodo-456',
  id_moneda: 'moneda-789',
  tasa: 1.0,
  referencia: 'Pago parcial',
  observaciones: 'Pago realizado en efectivo'
});
```

### Crear pago usando método específico

```typescript
// Para pedidos (método legacy, pero funcional)
const pagoPedido = await pagosService.createPagoPedido('pedido-123', {
  monto: 100.50,
  id_metodo_pago: 'metodo-456',
  id_moneda: 'moneda-789',
  tasa: 1.0
});

// Para cuentas por pagar
const pagoCXP = await pagosService.createPagoCXP('cxp-456', {
  monto: 500.00,
  id_metodo_pago: 'metodo-transfer',
  id_moneda: 'moneda-ves',
  tasa: 35.5,
  referencia: 'Transferencia bancaria'
});
```

## 📖 API Reference

### Métodos Principales

#### `createPagoDocumento(tipoDocumento, idDocumento, pagoData)`

Método genérico para crear pagos de cualquier tipo de documento.

**Parámetros:**
- `tipoDocumento`: string - Tipo de documento (ver tabla arriba)
- `idDocumento`: string - ID único del documento
- `pagoData`: object - Datos del pago

**Retorna:** `Promise<Pago>`

#### `getPagos(filters?)`

Obtener lista de pagos con filtros opcionales.

```typescript
// Todos los pagos
const todosPagos = await pagosService.getPagos();

// Pagos de un tipo específico
const pagosPedidos = await pagosService.getPagos({ tipo_documento: 'PEDIDO' });

// Pagos en un rango de fechas
const pagosRecientes = await pagosService.getPagos({
  fecha_desde: '2025-01-01',
  fecha_hasta: '2025-12-31'
});
```

#### `getPagosByTipoDocumento(tipoDocumento, idDocumento?)`

Obtener pagos filtrados por tipo de documento.

```typescript
// Todos los pagos de pedidos
const pagosPedidos = await pagosService.getPagosByTipoDocumento('PEDIDO');

// Pagos de un pedido específico
const pagosPedidoEspecifico = await pagosService.getPagosByTipoDocumento('PEDIDO', 'pedido-123');
```

### Métodos Específicos por Tipo

- `createPagoPedido(idPedido, pagoData)` - Para pedidos
- `createPagoCXP(idCXP, pagoData)` - Para cuentas por pagar
- `createPagoGasto(idGasto, pagoData)` - Para gastos
- `createPagoNomina(idNomina, pagoData)` - Para nóminas
- `createPagoImpuesto(idContribucion, pagoData)` - Para impuestos

## 🔧 Estructura de Datos

### Interfaz Pago

```typescript
interface Pago {
  id_pago?: string;
  id_empresa: string;
  tipo_operacion: 'INGRESO' | 'EGRESO';
  tipo_documento: string;
  id_documento: string;
  fecha_pago: string;
  monto: number;
  id_moneda: string;
  tasa: number;
  id_metodo_pago: string;
  referencia?: string;
  observaciones?: string;
  // Campos opcionales de ubicación financiera
  id_caja_fisica?: string;
  id_caja_virtual?: string;
  id_cuenta_bancaria?: string;
  id_datafono?: string;
  banco_destino?: string;
  // Relaciones específicas por tipo de documento
  id_pedido?: string;
  id_cxp?: string;
  // ... otros campos específicos
}
```

## 🎨 Ejemplos de Uso en Componentes

### En un componente de pedido

```typescript
import { pagosService } from '../../../services/pagosService';

const handlePagoPedido = async (idPedido: string, datosPago: any) => {
  try {
    const pago = await pagosService.createPagoDocumento('PEDIDO', idPedido, {
      monto: datosPago.monto,
      id_metodo_pago: datosPago.metodo,
      id_moneda: datosPago.moneda,
      tasa: datosPago.tasa,
      referencia: datosPago.referencia
    });

    console.log('Pago creado:', pago);
    // Recargar lista de pagos
    loadPagos();
  } catch (error) {
    console.error('Error al crear pago:', error);
  }
};
```

### En un componente de gastos

```typescript
const handlePagoGasto = async (idGasto: string, datosPago: any) => {
  const pago = await pagosService.createPagoDocumento('GASTO', idGasto, {
    monto: datosPago.monto,
    id_metodo_pago: datosPago.metodo,
    id_moneda: datosPago.moneda,
    tasa: datosPago.tasa
  });
};
```

## 🔄 Migración desde APIs antiguas

### Antes (APIs específicas)
```typescript
// Pagos de pedidos
await post('/ventas/pagos-pedido/', pagoData);

// Pagos de CxP
await post('/cuentas-por-pagar/pagos/', pagoData);
```

### Ahora (API unificada)
```typescript
// Un solo endpoint para todos los pagos
await pagosService.createPagoDocumento('PEDIDO', idPedido, pagoData);
await pagosService.createPagoDocumento('CXP', idCXP, pagoData);
```

## ⚡ Beneficios

1. **Consistencia**: Una sola API para todos los pagos
2. **Mantenibilidad**: Código centralizado y reutilizable
3. **Escalabilidad**: Fácil agregar nuevos tipos de documento
4. **Type Safety**: Interfaces TypeScript completas
5. **Documentación**: API bien documentada con ejemplos

## 🚨 Notas Importantes

- El servicio determina automáticamente si es INGRESO o EGRESO basado en el tipo de documento
- Se obtienen automáticamente los datos de empresa del documento relacionado
- Los pagos crean automáticamente transacciones financieras en el backend
- Mantener compatibilidad con métodos específicos por un tiempo de transición