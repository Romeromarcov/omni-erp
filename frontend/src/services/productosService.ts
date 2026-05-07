import { get } from './api';

export interface Producto {
  id_producto: string;
  nombre_producto: string;
  precio_venta_sugerido?: number;
  sku?: string;
}

export async function fetchProductos(empresaId: string): Promise<Producto[] | { results: Producto[] }> {
  return get<Producto[] | { results: Producto[] }>(`/inventario/productos/?empresa=${empresaId}`);
}
