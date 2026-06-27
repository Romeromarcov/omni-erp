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

/**
 * Devuelve el id de una moneda por su código ISO; si no existe la crea (pública,
 * fiat). `seed_empresa_inicial` sólo siembra la moneda base (USD), así que los
 * flujos de tesorería que necesitan una segunda moneda (VES) la crean aquí.
 */
export async function asegurarMoneda(
  api: ApiE2E,
  codigoIso: string,
  datos: { nombre: string; simbolo: string },
): Promise<string> {
  const monedas = aLista<MonedaApi>(await api.get('/finanzas/monedas/'));
  const existente = monedas.find((m) => m.codigo_iso === codigoIso);
  if (existente) return existente.id_moneda;
  const creada = await api.post<MonedaApi>('/finanzas/monedas/', {
    codigo_iso: codigoIso,
    nombre: datos.nombre,
    simbolo: datos.simbolo,
    tipo_moneda: 'fiat',
    decimales: 2,
    es_publica: true,
  });
  return creada.id_moneda;
}

export interface CuentaBancariaSembrada {
  cuentaId: string;
  nombreBanco: string;
  numeroCuenta: string;
}

/** Crea una CuentaBancariaEmpresa en la moneda indicada (selector/filtros de tesorería). */
export async function crearCuentaBancaria(
  api: ApiE2E,
  datos: { empresaId: string; monedaId: string; nombreBanco: string; sufijo?: string },
): Promise<CuentaBancariaSembrada> {
  // numero_cuenta es unique GLOBAL → se hace único por corrida (máx. 20 díg.),
  // independiente de `datos.sufijo` (que puede compartirse entre cuentas).
  const numeroCuenta = `${Date.now()}${Math.floor(Math.random() * 1000)}`.slice(0, 20);
  const cuenta = await api.post<{ id_cuenta_bancaria: string }>(
    '/finanzas/cuentas-bancarias-empresa/',
    {
      id_empresa: datos.empresaId,
      nombre_banco: datos.nombreBanco,
      numero_cuenta: numeroCuenta,
      tipo_cuenta: 'CORRIENTE',
      id_moneda: datos.monedaId,
    },
  );
  return { cuentaId: cuenta.id_cuenta_bancaria, nombreBanco: datos.nombreBanco, numeroCuenta };
}

/** Registra una TasaCambio origen→destino vigente al día (prerequisito del cambio de divisa). */
export async function crearTasaCambio(
  api: ApiE2E,
  datos: { empresaId: string; monedaOrigenId: string; monedaDestinoId: string; valor: string },
): Promise<void> {
  await api.post('/finanzas/tasas-cambio/', {
    id_empresa: datos.empresaId,
    id_moneda_origen: datos.monedaOrigenId,
    id_moneda_destino: datos.monedaDestinoId,
    valor_tasa: datos.valor,
    fecha_tasa: new Date().toISOString().slice(0, 10),
    tipo_tasa: 'FIJA',
  });
}

export interface MetodoPagoSembrado {
  metodoId: string;
  nombre: string;
}

/** Crea un MetodoPago electrónico para la empresa (egreso/ingreso del cambio). */
export async function crearMetodoPago(
  api: ApiE2E,
  datos: { empresaId: string; tipo?: string; sufijo?: string },
): Promise<MetodoPagoSembrado> {
  const suf = datos.sufijo ?? sufijoUnico();
  const nombre = `Transferencia E2E ${suf}`;
  const metodo = await api.post<{ id_metodo_pago: string }>('/finanzas/metodos-pago/', {
    empresa: datos.empresaId,
    nombre_metodo: nombre,
    tipo_metodo: datos.tipo ?? 'ELECTRONICO',
  });
  return { metodoId: metodo.id_metodo_pago, nombre };
}

/**
 * Registra un Pago de INGRESO atado a una cuenta bancaria, SIN documento real
 * (tipo_documento AJUSTE con id_documento aleatorio: no dispara efectos de saldo
 * sobre pedidos/facturas). Sirve de contraparte interna para que la conciliación
 * automática empareje un MovimientoBancario CREDITO del mismo monto/cuenta/fecha.
 */
export async function crearPagoIngresoBancario(
  api: ApiE2E,
  datos: {
    cuentaBancariaId: string;
    monedaId: string;
    metodoPagoId: string;
    monto: string;
    referencia: string;
    fecha?: string;
  },
): Promise<{ id_pago: string }> {
  const idDocumento = (
    globalThis.crypto?.randomUUID?.() ?? `00000000-0000-4000-8000-${Date.now()}`
  ).slice(0, 36);
  return api.post<{ id_pago: string }>('/finanzas/pagos/', {
    tipo_operacion: 'INGRESO',
    tipo_documento: 'AJUSTE',
    id_documento: idDocumento,
    fecha_pago: datos.fecha ?? new Date().toISOString().slice(0, 10),
    monto: datos.monto,
    id_moneda: datos.monedaId,
    tasa: '1.00',
    id_metodo_pago: datos.metodoPagoId,
    id_cuenta_bancaria: datos.cuentaBancariaId,
    referencia: datos.referencia,
  });
}

/**
 * Registra un MovimientoBancario (línea de extracto) vía API. El estado nace
 * PENDIENTE (read_only en el serializer). `tipo` CREDITO es el único que la
 * conciliación automática empareja contra pagos INGRESO.
 */
export async function crearMovimientoBancario(
  api: ApiE2E,
  datos: {
    empresaId: string;
    cuentaBancariaId: string;
    descripcion: string;
    monto: string;
    referencia: string;
    fecha?: string;
    tipo?: 'CREDITO' | 'DEBITO';
  },
): Promise<{ id: string }> {
  return api.post<{ id: string }>('/tesoreria/movimientos-bancarios/', {
    id_empresa: datos.empresaId,
    id_cuenta_bancaria: datos.cuentaBancariaId,
    fecha_mov: datos.fecha ?? new Date().toISOString().slice(0, 10),
    descripcion: datos.descripcion,
    tipo: datos.tipo ?? 'CREDITO',
    monto: datos.monto,
    referencia: datos.referencia,
  });
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

export interface PrereqProduccion {
  /** Producto terminado a fabricar. */
  productoTerminadoId: string;
  productoTerminadoNombre: string;
  /** Materia prima con stock inicial. */
  materiaPrimaId: string;
  materiaPrimaNombre: string;
  /** Cantidad de materia prima requerida por unidad de producto terminado. */
  cantidadPorUnidad: string;
  /** Lista de materiales (BOM) que liga terminado ↔ materia prima. */
  listaMaterialesId: string;
  almacenId: string;
  almacenNombre: string;
}

/**
 * Siembra los prerequisitos de una orden de producción (Produce-to-Cost):
 *   - un producto terminado,
 *   - una materia prima con stock inicial (movimiento AJUSTE de entrada),
 *   - un almacén,
 *   - una BOM (ListaMateriales + 1 detalle) que consume `cantidadPorUnidad`
 *     unidades de la materia prima por cada unidad de producto terminado.
 *
 * Todo vía API: `seed_empresa_inicial` no siembra catálogo de manufactura.
 */
export async function crearPrereqProduccion(
  api: ApiE2E,
  empresaId: string,
  opciones: { stockMateriaPrima: string; cantidadPorUnidad: string; sufijo?: string },
): Promise<PrereqProduccion> {
  const suf = opciones.sufijo ?? sufijoUnico();
  const usdId = await monedaUsd(api);

  // Unidad de medida compartida por terminado y materia prima.
  const unidad = await api.post<{ id_unidad_medida: string }>('/inventario/unidades-medida/', {
    id_empresa: empresaId,
    nombre: `Unidad MFG ${suf}`,
    abreviatura: `UM${suf}`.slice(0, 10),
    tipo: 'CANTIDAD',
  });
  const categoria = await api.post<{ id_categoria_producto: string }>(
    '/inventario/categorias-producto/',
    { id_empresa: empresaId, nombre_categoria: `Categoría MFG ${suf}` },
  );

  const crearProd = async (nombre: string, costo: string): Promise<string> => {
    const p = await api.post<{ id_producto: string }>('/inventario/productos/', {
      id_empresa: empresaId,
      nombre_producto: nombre,
      id_unidad_medida_base: unidad.id_unidad_medida,
      id_categoria: categoria.id_categoria_producto,
      id_moneda_precio: usdId,
      precio_venta_sugerido: '100.00',
      costo_promedio: costo,
    });
    return p.id_producto;
  };

  const productoTerminadoNombre = `Mueble Terminado ${suf}`;
  const materiaPrimaNombre = `Madera MP ${suf}`;
  const productoTerminadoId = await crearProd(productoTerminadoNombre, '0.00');
  const materiaPrimaId = await crearProd(materiaPrimaNombre, '7.00');

  const almacenNombre = `Almacén MFG ${suf}`;
  const almacen = await api.post<{ id_almacen: string }>('/almacenes/almacenes/', {
    id_empresa: empresaId,
    nombre_almacen: almacenNombre,
    codigo_almacen: `MFG${suf}`.slice(0, 10),
  });

  // Stock inicial de la materia prima (entrada por AJUSTE).
  await api.post('/inventario/movimientos-inventario/', {
    id_empresa: empresaId,
    id_producto: materiaPrimaId,
    tipo_movimiento: 'AJUSTE',
    cantidad: opciones.stockMateriaPrima,
    fecha_hora_movimiento: new Date().toISOString(),
    id_almacen_destino: almacen.id_almacen,
    costo_unitario_movimiento: '7.00',
    observaciones: `Carga inicial MP producción ${suf}`,
  });

  // BOM: ListaMateriales del producto terminado + 1 componente (la materia prima).
  const lista = await api.post<{ id: string }>('/manufactura/listas-materiales/', {
    nombre: `BOM ${productoTerminadoNombre}`,
    producto_final: productoTerminadoId,
    descripcion: `BOM E2E ${suf}`,
  });
  await api.post('/manufactura/listas-materiales-detalle/', {
    id_lista_materiales: lista.id,
    id_producto: materiaPrimaId,
    id_unidad_medida: unidad.id_unidad_medida,
    cantidad_requerida: opciones.cantidadPorUnidad,
    es_opcional: false,
  });

  return {
    productoTerminadoId,
    productoTerminadoNombre,
    materiaPrimaId,
    materiaPrimaNombre,
    cantidadPorUnidad: opciones.cantidadPorUnidad,
    listaMaterialesId: lista.id,
    almacenId: almacen.id_almacen,
    almacenNombre,
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

export interface PrereqNomina {
  /** PK entera del empleado sembrado (las claves del body de procesar usan String(id)). */
  empleadoId: number;
  empleadoNombre: string;
  empleadoApellido: string;
  /** Salario mensual del empleado, como string decimal (R-CODE-4). */
  salarioMensual: string;
  /** Período de nómina ABIERTO. */
  periodoId: string;
  periodoNombre: string;
}

/**
 * Siembra los prerequisitos del flujo Hire-to-Pay vía API:
 *   - un empleado activo con salario mensual (documento_json.salario_mensual,
 *     el puente que lee el motor de nómina) y fecha de ingreso;
 *   - un período de nómina MENSUAL en estado ABIERTO (default del modelo).
 *
 * `seed_empresa_inicial` no siembra empleados ni períodos: los crea el spec.
 * Los conceptos de nómina los crea el motor LOTTT al procesar (no requieren
 * seed manual: `procesar_proceso_nomina` calcula con `ParametroSistema`).
 */
export async function crearPrereqNomina(
  api: ApiE2E,
  empresaId: string,
  opciones: { salarioMensual: string; sufijo?: string },
): Promise<PrereqNomina> {
  const suf = opciones.sufijo ?? sufijoUnico();
  const empleadoNombre = `Nomina${suf}`.slice(0, 20);
  const empleadoApellido = `Test${suf}`.slice(0, 20);

  const empleado = await api.post<{ id: number }>('/rrhh/empleados/', {
    empresa: empresaId,
    nombre: empleadoNombre,
    apellido: empleadoApellido,
    cedula: `V-${String(Date.now()).slice(-8)}`,
    fecha_ingreso: new Date().toISOString().slice(0, 10),
    activo: true,
    documento_json: { salario_mensual: opciones.salarioMensual },
  });

  const hoy = new Date();
  const fin = new Date(hoy.getTime() + 29 * 24 * 3600 * 1000);
  const periodoNombre = `Período E2E ${suf}`;
  const periodo = await api.post<{ id_periodo_nomina: string }>('/nomina/periodos-nomina/', {
    id_empresa: empresaId,
    nombre_periodo: periodoNombre,
    tipo_periodo: 'MENSUAL',
    fecha_inicio: hoy.toISOString().slice(0, 10),
    fecha_fin: fin.toISOString().slice(0, 10),
    fecha_pago: fin.toISOString().slice(0, 10),
  });

  return {
    empleadoId: empleado.id,
    empleadoNombre,
    empleadoApellido,
    salarioMensual: opciones.salarioMensual,
    periodoId: periodo.id_periodo_nomina,
    periodoNombre,
  };
}

export interface PrereqGasto {
  /** Categoría de gasto activa, con cuenta de gasto (DEUDORA) por defecto. */
  categoriaId: string;
  categoriaNombre: string;
  /** Cuenta contable de gasto (DEUDORA) — destino de las líneas de imputación. */
  cuentaGastoId: string;
  cuentaGastoCodigo: string;
  /** Moneda base (USD) del gasto. */
  monedaUsdId: string;
  /** Método de pago activo de la empresa (para el reembolso). */
  metodoPagoId: string;
  metodoPagoNombre: string;
}

/**
 * Siembra los prerequisitos del flujo Gasto Completo vía API:
 *   - una cuenta contable de GASTO (DEUDORA) para las líneas de imputación,
 *   - una CategoriaGasto activa que la usa por defecto (NO exige factura, para
 *     que el gasto sin respaldo se apruebe igual),
 *   - un MetodoPago activo de la empresa (la creación lo activa para el tenant,
 *     ver MetodoPagoSerializer.create) para poder pagar el reembolso.
 *
 * `seed_empresa_inicial` no siembra catálogo de gastos: lo crea el spec.
 */
export async function crearPrereqGasto(
  api: ApiE2E,
  empresaId: string,
  opciones?: { sufijo?: string },
): Promise<PrereqGasto> {
  const suf = opciones?.sufijo ?? sufijoUnico();
  const usdId = await monedaUsd(api);

  // Cuenta de gasto (DEUDORA). El código es único por empresa; se acota a 20 díg.
  const cuentaGastoCodigo = `6${String(Date.now()).slice(-7)}`.slice(0, 20);
  const cuenta = await api.post<{ id_cuenta_contable: string }>('/contabilidad/plan-cuentas/', {
    id_empresa: empresaId,
    codigo_cuenta: cuentaGastoCodigo,
    nombre_cuenta: `Gasto E2E ${suf}`,
    tipo_cuenta: 'GASTO',
    naturaleza: 'DEUDORA',
    nivel: 1,
  });

  const categoriaNombre = `Categoría Gasto E2E ${suf}`;
  const categoria = await api.post<{ id_categoria_gasto: string }>(
    '/gastos/categorias-gasto/',
    {
      id_empresa: empresaId,
      nombre_categoria: categoriaNombre,
      descripcion: `Categoría sembrada E2E ${suf}`,
      id_cuenta_contable: cuenta.id_cuenta_contable,
      requiere_factura: false,
      activo: true,
    },
  );

  const metodo = await crearMetodoPago(api, { empresaId, sufijo: suf });

  return {
    categoriaId: categoria.id_categoria_gasto,
    categoriaNombre,
    cuentaGastoId: cuenta.id_cuenta_contable,
    cuentaGastoCodigo,
    monedaUsdId: usdId,
    metodoPagoId: metodo.metodoId,
    metodoPagoNombre: metodo.nombre,
  };
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
