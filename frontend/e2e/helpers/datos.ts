import { type ApiE2E, aLista } from './sesion';

/**
 * Seeding de datos transaccionales vía API para los specs E2E (TEST-6).
 *
 * Cada spec siembra SUS datos con un sufijo único por corrida, de modo que los
 * tests son re-ejecutables contra una BD persistente (local) o limpia (CI).
 * Los datos base (empresa, admin, sucursal, caja) los crea
 * `manage.py seed_empresa_inicial` antes de correr Playwright.
 */

/** Sufijo único por corrida para nombres/códigos con unique constraints. */
export function sufijoUnico(): string {
  return `${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`;
}

interface MonedaApi {
  id_moneda: string;
  codigo_iso: string;
}

export async function monedaUsd(api: ApiE2E): Promise<string> {
  const monedas = aLista<MonedaApi>(await api.get('/finanzas/monedas/'));
  const usd = monedas.find((m) => m.codigo_iso === 'USD');
  if (!usd) throw new Error('Seed incompleto: no existe la moneda USD.');
  return usd.id_moneda;
}

export interface ProductoSembrado {
  productoId: string;
  productoNombre: string;
}

/**
 * Crea unidad + categoría + producto en la empresa indicada y devuelve su id y
 * nombre. `seed_empresa_inicial` NO siembra productos, así que los specs que
 * necesitan al menos uno deben crearlo vía API (igual que el resto de datos
 * transaccionales).
 */
export async function crearProducto(
  api: ApiE2E,
  empresaId: string,
  sufijo?: string,
): Promise<ProductoSembrado> {
  const suf = sufijo ?? sufijoUnico();
  const usdId = await monedaUsd(api);

  const unidad = await api.post<{ id_unidad_medida: string }>('/inventario/unidades-medida/', {
    id_empresa: empresaId,
    nombre: `Unidad E2E ${suf}`,
    abreviatura: `U${suf}`.slice(0, 10),
    tipo: 'CANTIDAD',
  });
  const categoria = await api.post<{ id_categoria_producto: string }>(
    '/inventario/categorias-producto/',
    { id_empresa: empresaId, nombre_categoria: `Categoría E2E ${suf}` },
  );
  const productoNombre = `Producto E2E ${suf}`;
  const producto = await api.post<{ id_producto: string }>('/inventario/productos/', {
    id_empresa: empresaId,
    nombre_producto: productoNombre,
    id_unidad_medida_base: unidad.id_unidad_medida,
    id_categoria: categoria.id_categoria_producto,
    id_moneda_precio: usdId,
    precio_venta_sugerido: '100.00',
    costo_promedio: '60.00',
  });
  return { productoId: producto.id_producto, productoNombre };
}

export interface CatalogoInventario {
  productoId: string;
  productoNombre: string;
  almacenId: string;
  almacenNombre: string;
  monedaUsdId: string;
}

/**
 * Crea unidad + categoría + producto + almacén y una carga inicial de stock
 * (movimiento AJUSTE de entrada) en la empresa indicada.
 */
export async function crearCatalogoInventario(
  api: ApiE2E,
  empresaId: string,
  opciones: { stockInicial: string; sufijo?: string },
): Promise<CatalogoInventario> {
  const suf = opciones.sufijo ?? sufijoUnico();
  const usdId = await monedaUsd(api);

  const { productoId, productoNombre } = await crearProducto(api, empresaId, suf);
  const almacenNombre = `Almacén E2E ${suf}`;
  const almacen = await api.post<{ id_almacen: string }>('/almacenes/almacenes/', {
    id_empresa: empresaId,
    nombre_almacen: almacenNombre,
    codigo_almacen: `E2E${suf}`.slice(0, 10),
  });
  await api.post('/inventario/movimientos-inventario/', {
    id_empresa: empresaId,
    id_producto: productoId,
    tipo_movimiento: 'AJUSTE',
    cantidad: opciones.stockInicial,
    fecha_hora_movimiento: new Date().toISOString(),
    id_almacen_destino: almacen.id_almacen,
    costo_unitario_movimiento: '60.00',
    observaciones: `Carga inicial E2E ${suf}`,
  });

  return {
    productoId,
    productoNombre,
    almacenId: almacen.id_almacen,
    almacenNombre,
    monedaUsdId: usdId,
  };
}

export interface ClienteSembrado {
  clienteId: string;
  razonSocial: string;
}

export async function crearCliente(
  api: ApiE2E,
  empresaId: string,
  sufijo?: string,
): Promise<ClienteSembrado> {
  const suf = sufijo ?? sufijoUnico();
  const razonSocial = `Cliente E2E ${suf}`;
  // RIF venezolano válido: letra + guion + dígitos (validador del backend).
  const rif = `J-${String(Date.now()).slice(-8)}`;
  const cliente = await api.post<{ id_cliente: string }>('/crm/clientes/', {
    id_empresa: empresaId,
    razon_social: razonSocial,
    rif,
  });
  return { clienteId: cliente.id_cliente, razonSocial };
}

export interface ProveedorSembrado {
  proveedorId: string;
  razonSocial: string;
}

/**
 * Crea un proveedor en la empresa indicada (procure-to-pay). `id_empresa` lo
 * fija el cliente aquí porque el endpoint de proveedores no usa
 * `EmpresaInjectMixin` con la sesión del navegador; el RIF es único por empresa.
 */
export async function crearProveedor(
  api: ApiE2E,
  empresaId: string,
  sufijo?: string,
): Promise<ProveedorSembrado> {
  const suf = sufijo ?? sufijoUnico();
  const razonSocial = `Proveedor E2E ${suf}`;
  // RIF venezolano válido: letra + guion + 8 dígitos (validador del backend),
  // único por empresa (unique_together id_empresa+rif).
  const rif = `J-${String(Date.now()).slice(-8)}`;
  const proveedor = await api.post<{ id_proveedor: string }>('/proveedores/proveedores/', {
    id_empresa: empresaId,
    razon_social: razonSocial,
    rif,
  });
  return { proveedorId: proveedor.id_proveedor, razonSocial };
}

export interface PedidoSembrado {
  pedidoId: string;
  numeroPedido: string;
}

/** Crea un pedido PENDIENTE con un detalle. El número lo genera el backend. */
export async function crearPedido(
  api: ApiE2E,
  datos: { clienteId: string; productoId: string; cantidad: string; precioUnitario: string },
): Promise<PedidoSembrado> {
  const subtotal = (Number(datos.cantidad) * Number(datos.precioUnitario)).toFixed(2);
  const pedido = await api.post<{ id_pedido: string; numero_pedido: string }>('/ventas/pedidos/', {
    id_cliente: datos.clienteId,
    fecha_pedido: new Date().toISOString().slice(0, 10),
    estado: 'PENDIENTE',
    detalles: [
      {
        id_producto: datos.productoId,
        cantidad: datos.cantidad,
        precio_unitario: datos.precioUnitario,
        subtotal,
      },
    ],
  });
  return { pedidoId: pedido.id_pedido, numeroPedido: pedido.numero_pedido };
}

export interface ConfirmacionPedido {
  estado: string;
  cxc_generada: boolean;
  cxc_id: string | null;
  reservas_creadas: number;
}

/** Confirma el pedido: reserva stock y genera la CxC (acción real del backend). */
export async function confirmarPedido(
  api: ApiE2E,
  pedidoId: string,
  almacenId: string,
): Promise<ConfirmacionPedido> {
  return api.post<ConfirmacionPedido>(`/ventas/pedidos/${pedidoId}/confirmar/`, {
    almacen_id: almacenId,
    generar_cxc: true,
  });
}

export interface CuentaPorCobrarApi {
  id: number;
  monto: string;
  saldo_pendiente: string;
  estado: string;
}

export async function crearCuentaPorCobrar(
  api: ApiE2E,
  datos: { empresaId: string; clienteId: string; monto: string; descripcion: string },
): Promise<CuentaPorCobrarApi> {
  const hoy = new Date();
  const vencimiento = new Date(hoy.getTime() + 30 * 24 * 3600 * 1000);
  return api.post<CuentaPorCobrarApi>('/cxc/cuentas-por-cobrar/', {
    empresa: datos.empresaId,
    cliente: datos.clienteId,
    monto: datos.monto,
    fecha_emision: hoy.toISOString().slice(0, 10),
    fecha_vencimiento: vencimiento.toISOString().slice(0, 10),
    estado: 'pendiente',
    descripcion: datos.descripcion,
  });
}

export async function abonarCuentaPorCobrar(
  api: ApiE2E,
  cxcId: number | string,
  monto: string,
): Promise<{ estado_cxc: string; monto_abonado: string }> {
  return api.post(`/cxc/cuentas-por-cobrar/${cxcId}/abonar/`, {
    monto,
    descripcion: 'Abono E2E Playwright',
  });
}

export interface CarteraDashboardApi {
  total_pendiente: string;
  total_partidas: number;
}

export async function carteraDashboard(api: ApiE2E): Promise<CarteraDashboardApi> {
  return api.get<CarteraDashboardApi>('/cobranza/cartera/dashboard/');
}

interface CajaVirtualApi {
  id_caja: string;
  nombre: string;
}

/** Primera caja virtual de la empresa (creada por seed_empresa_inicial). */
export async function cajaVirtualPrincipal(api: ApiE2E, empresaId: string): Promise<CajaVirtualApi> {
  const cajas = aLista<CajaVirtualApi & { empresa: string }>(
    await api.get(`/finanzas/cajas/?empresa=${empresaId}`),
  );
  if (cajas.length === 0) throw new Error('Seed incompleto: la empresa no tiene cajas virtuales.');
  return cajas[0];
}

/** Registra un pago EFECTIVO de un pedido contra una caja virtual. */
export async function registrarPagoEnCaja(
  api: ApiE2E,
  datos: {
    empresaId: string;
    pedidoId: string;
    cajaVirtualId: string;
    monedaUsdId: string;
    monto: string;
  },
): Promise<{ id_pago: string }> {
  const suf = sufijoUnico();
  const metodo = await api.post<{ id_metodo_pago: string }>('/finanzas/metodos-pago/', {
    id_empresa: datos.empresaId,
    nombre_metodo: `Efectivo E2E ${suf}`,
    tipo_metodo: 'EFECTIVO',
  });
  return api.post<{ id_pago: string }>('/finanzas/pagos/', {
    id_empresa: datos.empresaId,
    tipo_documento: 'PEDIDO',
    id_documento: datos.pedidoId,
    id_metodo_pago: metodo.id_metodo_pago,
    id_moneda: datos.monedaUsdId,
    monto: datos.monto,
    tasa: '1.00',
    tipo_operacion: 'INGRESO',
    fecha_pago: new Date().toISOString().slice(0, 10),
    id_caja_virtual: datos.cajaVirtualId,
  });
}
