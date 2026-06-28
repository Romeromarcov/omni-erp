import { get } from './api';

export interface Producto {
  id_producto: string;
  nombre_producto: string;
  precio_venta_sugerido?: number;
  sku?: string;
}

interface ProductosPaginados {
  results: Producto[];
  next?: string | null;
}

/**
 * Catálogo de productos de la empresa. Recorre TODAS las páginas: los selectores
 * (p. ej. "Producto terminado" de una orden de producción) necesitan el catálogo
 * completo. Con sólo la página 1 (20 ítems), una empresa con muchos productos no
 * podría seleccionar los más recientes. Devuelve siempre un array plano (los
 * consumidores ya lo normalizan con `toList`).
 */
export async function fetchProductos(empresaId: string): Promise<Producto[]> {
  const acumulado: Producto[] = [];
  for (let page = 1; page <= 50; page++) {
    const data = await get<Producto[] | ProductosPaginados>(
      `/inventario/productos/?empresa=${empresaId}&page=${page}`,
    );
    if (Array.isArray(data)) {
      acumulado.push(...data);
      break;
    }
    if (data && Array.isArray(data.results)) {
      acumulado.push(...data.results);
      if (!data.next) break;
    } else {
      break;
    }
  }
  return acumulado;
}
