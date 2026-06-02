/**
 * Fábrica central de query keys para TanStack Query.
 *
 * Mantener las keys aquí evita strings opacos (endpoint + querystring) y keys
 * hardcoded duplicadas dispersas por las páginas. Cada grupo expone factories
 * que devuelven tuplas `readonly` estables; los prefijos (p. ej. `notasVenta.all`)
 * permiten invalidar familias completas con `invalidateQueries`.
 */

export const inventarioKeys = {
  stockActualAll: () => ['stock-actual-all'] as const,
  productosInventario: () => ['productos-inventario'] as const,
  producto: (productoId: string) => ['producto', productoId] as const,
  kardex: (productoId?: string, fechaDesde?: string, fechaHasta?: string) =>
    ['kardex', productoId, fechaDesde, fechaHasta] as const,
  kardexAll: () => ['kardex'] as const,
};

export const notasVentaKeys = {
  all: () => ['notas-venta'] as const,
  detail: (id: string) => ['notas-venta', id] as const,
};

export const pagosKeys = {
  all: () => ['pagos'] as const,
  porDocumento: (tipoDocumento: string, idDocumento: string) =>
    ['pagos', tipoDocumento, idDocumento] as const,
};

export const productosKeys = {
  all: () => ['productos'] as const,
  porEmpresa: (empresaId: string) => ['productos', empresaId] as const,
};
