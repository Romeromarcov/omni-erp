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
  categoriasProducto: () => ['inv-categorias-producto'] as const,
  unidadesMedida: () => ['inv-unidades-medida'] as const,
  kardex: (productoId?: string, fechaDesde?: string, fechaHasta?: string) =>
    ['kardex', productoId, fechaDesde, fechaHasta] as const,
  kardexAll: () => ['kardex'] as const,
  recepciones: () => ['inv-recepciones'] as const,
  entregas: () => ['inv-entregas'] as const,
  valoracion: () => ['inv-valoracion'] as const,
  pasosOperacion: (almacen: string, tipo: string) =>
    ['inv-pasos-operacion', almacen, tipo] as const,
};

// ── Inventario: Datos Maestros (variantes, conversiones UM, consignación) ─────
// Prefijo compartido `['inventario-maestros', <recurso>]` para que invalidar la
// familia de un recurso refresque su lista y variantes (filtros) a la vez.
export const inventarioMaestrosKeys = {
  all: () => ['inventario-maestros'] as const,
  variantesAll: () => ['inventario-maestros', 'variantes'] as const,
  variantes: (producto?: string | null) =>
    ['inventario-maestros', 'variantes', 'list', producto ?? null] as const,
  conversionesAll: () => ['inventario-maestros', 'conversiones'] as const,
  conversiones: (producto?: string | null) =>
    ['inventario-maestros', 'conversiones', 'list', producto ?? null] as const,
  consignacionClienteAll: () => ['inventario-maestros', 'consignacion-cliente'] as const,
  consignacionCliente: (cliente?: string | null, estado?: string | null) =>
    ['inventario-maestros', 'consignacion-cliente', 'list', cliente ?? null, estado ?? null] as const,
  consignacionProveedorAll: () => ['inventario-maestros', 'consignacion-proveedor'] as const,
  consignacionProveedor: (proveedor?: string | null, estado?: string | null) =>
    ['inventario-maestros', 'consignacion-proveedor', 'list', proveedor ?? null, estado ?? null] as const,
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

export const pedidosKeys = {
  // Prefijo compartido con la lista paginada (`['pedidos', page]`) para que
  // `invalidateQueries({queryKey: all()})` refresque lista y detalle a la vez.
  all: () => ['pedidos'] as const,
  detail: (id: string) => ['pedidos', 'detail', id] as const,
};

export const almacenesKeys = {
  all: () => ['almacenes'] as const,
};

export const productosKeys = {
  all: () => ['productos'] as const,
  porEmpresa: (empresaId: string) => ['productos', empresaId] as const,
};

// ── Ventas ────────────────────────────────────────────────────────────────────
// Factory jerárquica para los documentos de venta. Cada familia comparte un
// prefijo estable (`['ventas', <recurso>]`) para que `invalidateQueries` sobre el
// prefijo siga afectando a todas las queries hijas (lista, detalle, etc.).
export const ventasKeys = {
  clientes: (empresaId?: string | null) => ['ventas', 'clientes', empresaId ?? null] as const,
  productos: (empresaId?: string | null) => ['ventas', 'productos', empresaId ?? null] as const,
  devoluciones: {
    all: () => ['ventas', 'devoluciones-venta'] as const,
    detail: (id: string) => ['ventas', 'devoluciones-venta', id] as const,
  },
  notasCreditoVenta: {
    all: () => ['ventas', 'notas-credito-venta'] as const,
    detail: (id: string) => ['ventas', 'notas-credito-venta', id] as const,
  },
  notasCreditoFiscal: {
    all: () => ['ventas', 'notas-credito-fiscal'] as const,
    detail: (id: string) => ['ventas', 'notas-credito-fiscal', id] as const,
  },
  cotizaciones: {
    all: () => ['ventas', 'cotizaciones'] as const,
    detail: (id: string) => ['ventas', 'cotizaciones', id] as const,
  },
};

// ── Listas de Precio (ventas) ─────────────────────────────────────────────────
// Prefijo compartido `['listas-precio', ...]` para que invalidar la familia
// refresque la lista de listas y los detalles (precios) de cada una a la vez.
export const listasPrecioKeys = {
  all: () => ['listas-precio'] as const,
  list: (search?: string | null) => ['listas-precio', 'list', search ?? null] as const,
  detalles: (listaId: string) => ['listas-precio', 'detalles', listaId] as const,
};

// ── Comisiones de ventas ──────────────────────────────────────────────────────
// Prefijo compartido `['comisiones', ...]` para que invalidar la familia
// refresque esquemas, overrides por categoría, devengadas y el resumen a la vez.
export const comisionesKeys = {
  all: () => ['comisiones'] as const,
  esquemas: () => ['comisiones', 'esquemas'] as const,
  categorias: (esquemaId: string) => ['comisiones', 'categorias', esquemaId] as const,
  devengadas: (params?: Record<string, string | undefined>) =>
    ['comisiones', 'devengadas', params ?? null] as const,
  resumen: (params?: Record<string, string | undefined>) =>
    ['comisiones', 'resumen', params ?? null] as const,
};

// ── CxC (Cuentas por Cobrar) ──────────────────────────────────────────────────
export const cxcKeys = {
  carteraDashboard: () => ['cxc', 'cartera', 'dashboard'] as const,
  carteraAll: () => ['cxc', 'cartera'] as const,
  tasasHoy: () => ['cxc', 'tasas', 'hoy'] as const,
  tasasAll: () => ['cxc', 'tasas'] as const,
  acuerdos: (estado?: string | null) => ['cxc', 'acuerdos', estado ?? null] as const,
  acuerdosAll: () => ['cxc', 'acuerdos'] as const,
  cuentas: (page?: number) => ['cxc', 'cuentas', page ?? 1] as const,
  cuentasAll: () => ['cxc', 'cuentas'] as const,
};

// ── CRM (maestro de Clientes) ─────────────────────────────────────────────────
// Prefijo compartido `['crm', 'clientes']` para que invalidar la familia refresque
// la lista y los detalles (contactos, direcciones, crédito, historial) a la vez.
export const crmKeys = {
  clientesAll: () => ['crm', 'clientes'] as const,
  clientes: (empresaId?: string | null, search?: string | null) =>
    ['crm', 'clientes', 'list', empresaId ?? null, search ?? null] as const,
  cliente: (id: string) => ['crm', 'clientes', 'detail', id] as const,
  contactos: (clienteId: string) => ['crm', 'clientes', 'contactos', clienteId] as const,
  direcciones: (clienteId: string) => ['crm', 'clientes', 'direcciones', clienteId] as const,
  creditoDisponible: (clienteId: string) =>
    ['crm', 'clientes', 'credito-disponible', clienteId] as const,
  historialVentas: (clienteId: string) =>
    ['crm', 'clientes', 'historial-ventas', clienteId] as const,
};

// ── Gestión documental (carpetas, documentos, vínculos, permisos) ─────────────
// Prefijo compartido `['gestion-documental']` para invalidar la familia completa.
export const gestionDocumentalKeys = {
  all: () => ['gestion-documental'] as const,
  carpetas: (empresaId?: string | null, padre?: string | null, search?: string | null) =>
    ['gestion-documental', 'carpetas', empresaId ?? null, padre ?? null, search ?? null] as const,
  documentos: (empresaId?: string | null, carpeta?: string | null, search?: string | null) =>
    ['gestion-documental', 'documentos', empresaId ?? null, carpeta ?? null, search ?? null] as const,
  vinculos: (documentoId: string) => ['gestion-documental', 'vinculos', documentoId] as const,
  permisos: (documentoId: string) => ['gestion-documental', 'permisos', documentoId] as const,
};

// ── Proveedores (maestro de Proveedores) ──────────────────────────────────────
// Prefijo compartido `['proveedores', 'maestro']` para que invalidar la familia
// refresque la lista y los detalles (contactos, cuentas bancarias) a la vez.
export const proveedoresKeys = {
  proveedoresAll: () => ['proveedores', 'maestro'] as const,
  proveedores: (empresaId?: string | null, search?: string | null) =>
    ['proveedores', 'maestro', 'list', empresaId ?? null, search ?? null] as const,
  proveedor: (id: string) => ['proveedores', 'maestro', 'detail', id] as const,
  contactos: (proveedorId: string) =>
    ['proveedores', 'maestro', 'contactos', proveedorId] as const,
  cuentasBancarias: (proveedorId: string) =>
    ['proveedores', 'maestro', 'cuentas-bancarias', proveedorId] as const,
};

// ── Gastos (workflow de aprobación + asiento contable) ────────────────────────
// Prefijo compartido `['gastos', <recurso>]` para que invalidar la familia
// refresque lista, detalle y pendientes a la vez tras aprobar/rechazar.
export const gastosKeys = {
  gastosAll: () => ['gastos', 'gastos'] as const,
  gastos: (empresaId?: string | null, estado?: string | null, search?: string | null) =>
    ['gastos', 'gastos', 'list', empresaId ?? null, estado ?? null, search ?? null] as const,
  gasto: (id: string) => ['gastos', 'gastos', 'detail', id] as const,
  detalles: (gastoId: string) => ['gastos', 'gastos', 'detalles', gastoId] as const,
  categoriasAll: () => ['gastos', 'categorias'] as const,
  categorias: (empresaId?: string | null, search?: string | null) =>
    ['gastos', 'categorias', 'list', empresaId ?? null, search ?? null] as const,
  categoriasActivas: () => ['gastos', 'categorias', 'activas'] as const,
  reembolsosAll: () => ['gastos', 'reembolsos'] as const,
  reembolsos: (empresaId?: string | null, estado?: string | null) =>
    ['gastos', 'reembolsos', 'list', empresaId ?? null, estado ?? null] as const,
};

// ── Despacho (logística de salida con máquina de estados) ─────────────────────
// Prefijo compartido `['despacho', 'despachos']` para que invalidar la familia
// refresque lista, detalle y líneas a la vez tras cada transición de estado.
export const despachoKeys = {
  despachosAll: () => ['despacho', 'despachos'] as const,
  despachos: (empresaId?: string | null, estado?: string | null) =>
    ['despacho', 'despachos', 'list', empresaId ?? null, estado ?? null] as const,
  despacho: (id: string) => ['despacho', 'despachos', 'detail', id] as const,
  detalles: (despachoId: string) => ['despacho', 'despachos', 'detalles', despachoId] as const,
};

// ── Finanzas ──────────────────────────────────────────────────────────────────
export const finanzasKeys = {
  monedas: {
    all: () => ['finanzas', 'monedas'] as const,
    detail: (id: string) => ['finanzas', 'monedas', id] as const,
    activas: () => ['finanzas', 'monedas', 'activas'] as const,
    // Variante "list completa" (?limit=1000) usada por selectores de formularios.
    listFull: () => ['finanzas', 'monedas', 'list-full'] as const,
    empresaActivas: (empresaId?: string | null) =>
      ['finanzas', 'monedas-empresa-activas', empresaId ?? null] as const,
  },
  pagos: {
    porDocumento: (tipoDocumento: string, idDocumento: string) =>
      ['finanzas', 'pagos', tipoDocumento, idDocumento] as const,
  },
  cajasFisicas: {
    all: () => ['finanzas', 'cajas-fisicas'] as const,
    list: (empresaId?: string | null) => ['finanzas', 'cajas-fisicas', empresaId ?? null] as const,
    detail: (id: string) => ['finanzas', 'cajas-fisicas', id] as const,
    virtuales: (id: string) => ['finanzas', 'cajas-fisicas', id, 'cajas-virtuales'] as const,
    datafonos: (id: string) => ['finanzas', 'cajas-fisicas', id, 'datafonos'] as const,
    // Catálogo estático de tipos de caja: fuera del prefijo `cajas-fisicas` para
    // que las invalidaciones por familia no lo refresquen innecesariamente.
    tipoChoices: () => ['finanzas', 'cajas-fisicas-tipo-choices'] as const,
  },
  overridesMetodosPago: {
    all: () => ['finanzas', 'overrides-metodos-pago'] as const,
    list: (empresaId?: string | null) =>
      ['finanzas', 'overrides-metodos-pago', empresaId ?? null] as const,
  },
  metodosPagoEmpresaActivas: (empresaId?: string | null) =>
    ['finanzas', 'metodos-pago-empresa-activas', empresaId ?? null] as const,
};

// ── Compras (workstream F) ────────────────────────────────────────────────────
// Prefijo compartido `['compras', 'ordenes']` para invalidar lista, detalle,
// líneas y recepciones de una OC a la vez tras aprobar/recepcionar/facturar.
export const comprasKeys = {
  ordenesAll: () => ['compras', 'ordenes'] as const,
  ordenes: (page?: number) => ['compras', 'ordenes', 'list', page ?? 1] as const,
  orden: (id: string) => ['compras', 'ordenes', 'detail', id] as const,
  detalles: (ordenId: string) => ['compras', 'ordenes', 'detalles', ordenId] as const,
  recepciones: (ordenId: string) => ['compras', 'ordenes', 'recepciones', ordenId] as const,
  proveedores: () => ['compras', 'proveedores'] as const,
};

// ── Aprovisionamiento (source-to-PO: requisiciones, RFQ, ofertas) ─────────────
// Prefijo compartido `['aprovisionamiento', <recurso>]` para que invalidar la
// familia de un recurso refresque su lista y los detalles (líneas) a la vez.
export const aprovisionamientoKeys = {
  all: () => ['aprovisionamiento'] as const,
  requisicionesAll: () => ['aprovisionamiento', 'requisiciones'] as const,
  requisiciones: (estado?: string | null) =>
    ['aprovisionamiento', 'requisiciones', 'list', estado ?? null] as const,
  detallesRequisicion: (requisicionId: string) =>
    ['aprovisionamiento', 'requisiciones', 'detalles', requisicionId] as const,
  solicitudesAll: () => ['aprovisionamiento', 'solicitudes'] as const,
  solicitudes: (estado?: string | null) =>
    ['aprovisionamiento', 'solicitudes', 'list', estado ?? null] as const,
  detallesSolicitud: (solicitudId: string) =>
    ['aprovisionamiento', 'solicitudes', 'detalles', solicitudId] as const,
  ofertasAll: () => ['aprovisionamiento', 'ofertas'] as const,
  ofertas: (solicitud?: string | null, estado?: string | null) =>
    ['aprovisionamiento', 'ofertas', 'list', solicitud ?? null, estado ?? null] as const,
  detallesOferta: (ofertaId: string) =>
    ['aprovisionamiento', 'ofertas', 'detalles', ofertaId] as const,
};

// ── CxP (Cuentas por Pagar) ───────────────────────────────────────────────────
export const cxpKeys = {
  cuentasAll: () => ['cxp', 'cuentas'] as const,
  cuentas: (page?: number, estado?: string | null) =>
    ['cxp', 'cuentas', page ?? 1, estado ?? null] as const,
  agingAll: () => ['cxp', 'aging'] as const,
  aging: (empresaId?: string | null) => ['cxp', 'aging', empresaId ?? null] as const,
};

// ── RRHH (workstream F) ───────────────────────────────────────────────────────
// Prefijo compartido `['rrhh', 'empleados']` para invalidar lista, detalle y
// la variante por-empresa de una vez tras crear/editar un empleado.
export const rrhhKeys = {
  empleadosAll: () => ['rrhh', 'empleados'] as const,
  empleados: (page?: number) => ['rrhh', 'empleados', 'list', page ?? 1] as const,
  empleado: (id: string) => ['rrhh', 'empleados', 'detail', id] as const,
  empleadosDeEmpresa: (empresaId?: string | null) =>
    ['rrhh', 'empleados', 'empresa', empresaId ?? null] as const,
  cargos: () => ['rrhh', 'cargos'] as const,
};

// ── RRHH: Beneficios y Licencias (catálogo + asignaciones + tipos + licencias) ─
// Prefijo compartido `['beneficios-licencias', <recurso>]` para que invalidar la
// familia de un recurso refresque su lista y variantes (por empleado/estado).
export const beneficiosLicenciasKeys = {
  all: () => ['beneficios-licencias'] as const,
  beneficiosAll: () => ['beneficios-licencias', 'beneficios'] as const,
  beneficios: () => ['beneficios-licencias', 'beneficios', 'list'] as const,
  asignacionesAll: () => ['beneficios-licencias', 'asignaciones'] as const,
  asignaciones: (empleadoId?: number | string | null) =>
    ['beneficios-licencias', 'asignaciones', 'list', empleadoId ?? null] as const,
  tiposAll: () => ['beneficios-licencias', 'tipos-licencia'] as const,
  tipos: () => ['beneficios-licencias', 'tipos-licencia', 'list'] as const,
  licenciasAll: () => ['beneficios-licencias', 'licencias'] as const,
  licencias: (empleadoId?: number | string | null, estado?: string | null) =>
    ['beneficios-licencias', 'licencias', 'list', empleadoId ?? null, estado ?? null] as const,
};

// ── Control de Asistencia (horarios, asignaciones, marcaje, resúmenes) ────────
// Prefijo compartido `['control-asistencia', <recurso>]` para que invalidar la
// familia de un recurso refresque su lista y variantes (activos/hoy) a la vez.
export const controlAsistenciaKeys = {
  horariosAll: () => ['control-asistencia', 'horarios'] as const,
  horarios: (empresaId?: string | null, search?: string | null) =>
    ['control-asistencia', 'horarios', 'list', empresaId ?? null, search ?? null] as const,
  horariosActivos: () => ['control-asistencia', 'horarios', 'activos'] as const,
  asignacionesAll: () => ['control-asistencia', 'asignaciones'] as const,
  asignaciones: (empleadoId?: number | string | null) =>
    ['control-asistencia', 'asignaciones', 'list', empleadoId ?? null] as const,
  registrosAll: () => ['control-asistencia', 'registros'] as const,
  registros: (empleadoId?: number | string | null, fechaInicio?: string | null, fechaFin?: string | null) =>
    [
      'control-asistencia',
      'registros',
      'list',
      empleadoId ?? null,
      fechaInicio ?? null,
      fechaFin ?? null,
    ] as const,
  registrosHoy: (empleadoId?: number | string | null) =>
    ['control-asistencia', 'registros', 'hoy', empleadoId ?? null] as const,
  resumenesAll: () => ['control-asistencia', 'resumenes'] as const,
  resumenes: (empleadoId?: number | string | null, fecha?: string | null, estado?: string | null) =>
    [
      'control-asistencia',
      'resumenes',
      'list',
      empleadoId ?? null,
      fecha ?? null,
      estado ?? null,
    ] as const,
};

// ── Nómina (workstream F) ─────────────────────────────────────────────────────
// Prefijo compartido `['nomina', 'procesos']` para que procesar invalide lista,
// detalle y recibos del proceso a la vez.
export const nominaKeys = {
  procesosAll: () => ['nomina', 'procesos'] as const,
  procesos: (page?: number) => ['nomina', 'procesos', 'list', page ?? 1] as const,
  proceso: (id: string) => ['nomina', 'procesos', 'detail', id] as const,
  recibos: (procesoId: string) => ['nomina', 'procesos', 'recibos', procesoId] as const,
  periodos: () => ['nomina', 'periodos'] as const,
};

// ── Nómina Extrasalarial + Conceptos (catálogo) ──────────────────────────────
// Prefijo compartido `['nomina-extras', <recurso>]` para que invalidar la familia
// de un recurso refresque su lista y variantes (filtro por tipo / recibos) a la vez.
export const nominaExtrasKeys = {
  all: () => ['nomina-extras'] as const,
  conceptosAll: () => ['nomina-extras', 'conceptos'] as const,
  conceptos: (tipo?: string | null) =>
    ['nomina-extras', 'conceptos', 'list', tipo ?? null] as const,
  procesosAll: () => ['nomina-extras', 'procesos'] as const,
  procesos: () => ['nomina-extras', 'procesos', 'list'] as const,
  recibos: (procesoId: string) => ['nomina-extras', 'procesos', 'recibos', procesoId] as const,
};

// ── Manufactura (1.I) ─────────────────────────────────────────────────────────
// Prefijo compartido `['manufactura', 'ordenes']` para que la invalidación por
// familia refresque lista, detalle, etapas y costeo de una OF a la vez.
export const manufacturaKeys = {
  ordenesAll: () => ['manufactura', 'ordenes'] as const,
  ordenes: (page?: number) => ['manufactura', 'ordenes', 'list', page ?? 1] as const,
  orden: (id: string) => ['manufactura', 'ordenes', 'detail', id] as const,
  etapas: (ordenId: string) => ['manufactura', 'ordenes', 'etapas', ordenId] as const,
  costeo: (ordenId: string) => ['manufactura', 'ordenes', 'costeo', ordenId] as const,
  mrp: (ordenId: string, almacenId?: string | null) =>
    ['manufactura', 'ordenes', 'mrp', ordenId, almacenId ?? null] as const,
  listasMateriales: () => ['manufactura', 'listas-materiales'] as const,
};

// ── Manufactura: Datos Maestros (BOM, rutas, centros de trabajo, operaciones) ─
// Prefijo compartido `['manufactura-maestros', <recurso>]` para que invalidar la
// familia de un recurso refresque su lista y los detalles (componentes/pasos).
export const manufacturaMaestrosKeys = {
  all: () => ['manufactura-maestros'] as const,
  bomsAll: () => ['manufactura-maestros', 'boms'] as const,
  componentes: (bomId: string) => ['manufactura-maestros', 'boms', 'componentes', bomId] as const,
  rutasAll: () => ['manufactura-maestros', 'rutas'] as const,
  pasos: (rutaId: string) => ['manufactura-maestros', 'rutas', 'pasos', rutaId] as const,
  centrosAll: () => ['manufactura-maestros', 'centros'] as const,
  operacionesAll: () => ['manufactura-maestros', 'operaciones'] as const,
};

// ── Costos (costeo de producción — complementa Manufactura) ───────────────────
// Prefijo compartido `['costos', <recurso>]` para que invalidar la familia
// refresque lista y detalle de cada entidad a la vez.
export const costosKeys = {
  produccionAll: () => ['costos', 'produccion'] as const,
  produccion: (empresaId?: string | null, ordenId?: string | null) =>
    ['costos', 'produccion', 'list', empresaId ?? null, ordenId ?? null] as const,
  estandarAll: () => ['costos', 'estandar'] as const,
  estandar: (empresaId?: string | null, productoId?: string | null) =>
    ['costos', 'estandar', 'list', empresaId ?? null, productoId ?? null] as const,
  variacionAll: () => ['costos', 'variacion'] as const,
  variacion: (empresaId?: string | null, productoId?: string | null) =>
    ['costos', 'variacion', 'list', empresaId ?? null, productoId ?? null] as const,
};

// ── Contabilidad (workstream F) ───────────────────────────────────────────────
// Prefijo `['contabilidad', …]` por recurso; `asientosAll`/`mapeosAll` permiten
// invalidar la familia completa tras crear cuentas, asientos o mapeos.
export const contabilidadKeys = {
  planCuentas: () => ['contabilidad', 'plan-cuentas'] as const,
  asientosAll: () => ['contabilidad', 'asientos'] as const,
  asientos: (page?: number, filtros?: { estado?: string; fechaDesde?: string; fechaHasta?: string }) =>
    [
      'contabilidad',
      'asientos',
      'list',
      page ?? 1,
      filtros?.estado ?? null,
      filtros?.fechaDesde ?? null,
      filtros?.fechaHasta ?? null,
    ] as const,
  asiento: (id: string) => ['contabilidad', 'asientos', 'detail', id] as const,
  detallesAsiento: (asientoId: string) => ['contabilidad', 'asientos', 'detalles', asientoId] as const,
  mapeosAll: () => ['contabilidad', 'mapeos'] as const,
  tiposAsiento: () => ['contabilidad', 'tipos-asiento'] as const,
};

// ── Tesorería (workstream F) ──────────────────────────────────────────────────
export const tesoreriaKeys = {
  movimientosAll: () => ['tesoreria', 'movimientos-bancarios'] as const,
  movimientos: (page?: number, filtros?: { cuenta?: string; estado?: string }) =>
    [
      'tesoreria',
      'movimientos-bancarios',
      'list',
      page ?? 1,
      filtros?.cuenta ?? null,
      filtros?.estado ?? null,
    ] as const,
  conciliacionesAll: () => ['tesoreria', 'conciliaciones'] as const,
  conciliaciones: (page?: number) => ['tesoreria', 'conciliaciones', 'list', page ?? 1] as const,
  conciliacion: (id: string) => ['tesoreria', 'conciliaciones', 'detail', id] as const,
  operacionesCambioAll: () => ['tesoreria', 'operaciones-cambio'] as const,
  operacionesCambio: (page?: number) => ['tesoreria', 'operaciones-cambio', 'list', page ?? 1] as const,
  cuentasBancarias: (empresaId?: string | null) =>
    ['tesoreria', 'cuentas-bancarias', empresaId ?? null] as const,
  cajas: (empresaId?: string | null) => ['tesoreria', 'cajas', empresaId ?? null] as const,
};

// ── Servicio al Cliente (mesa de ayuda: tickets, interacciones, KB, feedback) ─
// Prefijo compartido `['servicio-cliente', <recurso>]` para que invalidar la
// familia de un recurso refresque su lista y variantes a la vez tras cada acción.
export const servicioClienteKeys = {
  ticketsAll: () => ['servicio-cliente', 'tickets'] as const,
  tickets: (
    empresaId?: string | null,
    estado?: string | null,
    prioridad?: string | null,
    search?: string | null,
  ) =>
    [
      'servicio-cliente',
      'tickets',
      'list',
      empresaId ?? null,
      estado ?? null,
      prioridad ?? null,
      search ?? null,
    ] as const,
  ticket: (id: string) => ['servicio-cliente', 'tickets', 'detail', id] as const,
  interacciones: (ticketId: string) =>
    ['servicio-cliente', 'tickets', 'interacciones', ticketId] as const,
  dashboard: (agenteId?: string | null) =>
    ['servicio-cliente', 'tickets', 'dashboard', agenteId ?? null] as const,
  categoriasAll: () => ['servicio-cliente', 'categorias'] as const,
  categorias: (empresaId?: string | null, search?: string | null) =>
    ['servicio-cliente', 'categorias', 'list', empresaId ?? null, search ?? null] as const,
  categoriasActivas: () => ['servicio-cliente', 'categorias', 'activas'] as const,
  articulosAll: () => ['servicio-cliente', 'articulos'] as const,
  articulos: (empresaId?: string | null, visibilidad?: string | null, search?: string | null) =>
    [
      'servicio-cliente',
      'articulos',
      'list',
      empresaId ?? null,
      visibilidad ?? null,
      search ?? null,
    ] as const,
  feedbackAll: () => ['servicio-cliente', 'feedback'] as const,
  feedback: (empresaId?: string | null, tipo?: string | null) =>
    ['servicio-cliente', 'feedback', 'list', empresaId ?? null, tipo ?? null] as const,
};

// ── Gestión de Aprobaciones (motor configurable: tipos, flujos, solicitudes) ──
// Prefijo compartido `['aprobaciones', <recurso>]`; los `*All` invalidan la
// familia completa de un recurso tras crear/editar/decidir.
export const aprobacionesKeys = {
  tiposAll: () => ['aprobaciones', 'tipos'] as const,
  tipos: (empresaId?: string | null, modulo?: string | null) =>
    ['aprobaciones', 'tipos', 'list', empresaId ?? null, modulo ?? null] as const,
  flujosAll: () => ['aprobaciones', 'flujos'] as const,
  flujos: (tipoId?: string | null) => ['aprobaciones', 'flujos', 'list', tipoId ?? null] as const,
  solicitudesAll: () => ['aprobaciones', 'solicitudes'] as const,
  solicitudes: (tipoId?: string | null, estado?: string | null) =>
    ['aprobaciones', 'solicitudes', 'list', tipoId ?? null, estado ?? null] as const,
  registros: (solicitudId: string) =>
    ['aprobaciones', 'solicitudes', 'registros', solicitudId] as const,
};

// ── Banca Electrónica (cuentas bancarias de la empresa) ───────────────────────
// Prefijo compartido `['banca-electronica', 'cuentas']` para que invalidar la
// familia refresque la lista y el detalle a la vez tras crear/editar/eliminar.
export const bancaElectronicaKeys = {
  cuentasAll: () => ['banca-electronica', 'cuentas'] as const,
  cuentas: (empresaId?: string | null) =>
    ['banca-electronica', 'cuentas', 'list', empresaId ?? null] as const,
  cuenta: (id: string) => ['banca-electronica', 'cuentas', 'detail', id] as const,
};

// ── Migración de Datos (plantillas globales + procesos + errores) ─────────────
// Prefijo compartido `['migracion-datos', <recurso>]`; los `*All` invalidan la
// familia completa de un recurso tras crear/editar/eliminar.
export const migracionDatosKeys = {
  plantillasAll: () => ['migracion-datos', 'plantillas'] as const,
  plantillas: (activo?: boolean | null) =>
    ['migracion-datos', 'plantillas', 'list', activo ?? null] as const,
  procesosAll: () => ['migracion-datos', 'procesos'] as const,
  procesos: (empresaId?: string | null, estado?: string | null) =>
    ['migracion-datos', 'procesos', 'list', empresaId ?? null, estado ?? null] as const,
  erroresAll: () => ['migracion-datos', 'errores'] as const,
  errores: (procesoId?: string | null) =>
    ['migracion-datos', 'errores', 'list', procesoId ?? null] as const,
};

// ── Personalización (versiones del DSL de personalización por empresa) ────────
// Prefijo compartido `['personalizacion', <recurso>]`; los `*All` invalidan la
// familia completa (activa + historial + lista) tras crear/activar/eliminar.
export const personalizacionKeys = {
  all: () => ['personalizacion'] as const,
  activa: (empresaId?: string | null) =>
    ['personalizacion', 'activa', empresaId ?? null] as const,
  historial: (empresaId?: string | null) =>
    ['personalizacion', 'historial', empresaId ?? null] as const,
};

// ── Integración B2B (configuraciones + mapeo de campos + logs) ────────────────
// Prefijo compartido `['integracion-b2b', <recurso>]`; los `*All` invalidan la
// familia completa de un recurso tras crear/editar/eliminar.
export const integracionB2bKeys = {
  configuracionesAll: () => ['integracion-b2b', 'configuraciones'] as const,
  configuraciones: (empresaId?: string | null) =>
    ['integracion-b2b', 'configuraciones', 'list', empresaId ?? null] as const,
  configuracion: (id: string) =>
    ['integracion-b2b', 'configuraciones', 'detail', id] as const,
  mapeosAll: () => ['integracion-b2b', 'mapeos'] as const,
  mapeos: (configuracionId?: string | null) =>
    ['integracion-b2b', 'mapeos', 'list', configuracionId ?? null] as const,
  logsAll: () => ['integracion-b2b', 'logs'] as const,
  logs: (configuracionId?: string | null) =>
    ['integracion-b2b', 'logs', 'list', configuracionId ?? null] as const,
};

// ── Agentes IA (predicciones, sugerencias, métricas del clasificador) ─────────
// Prefijo compartido `['agentes', <recurso>]` para que invalidar una familia
// refresque lista y variantes (sugerencias, métricas) a la vez tras responder/evaluar.
export const agentesKeys = {
  all: () => ['agentes'] as const,
  predicciones: (agente?: string | null, resultado?: string | null) =>
    ['agentes', 'predicciones', 'list', agente ?? null, resultado ?? null] as const,
  prediccionesAll: () => ['agentes', 'predicciones'] as const,
  sugerenciasActivas: (limite?: number | null) =>
    ['agentes', 'sugerencias-activas', limite ?? null] as const,
  metricasClasificador: () => ['agentes', 'metricas-clasificador'] as const,
};

// ── Notificaciones (centro de notificaciones del usuario) ─────────────────────
// Prefijo compartido `['notificaciones', ...]` para invalidar lista e indicador
// (campana) a la vez tras marcar como leída. El parámetro distingue la vista de
// "solo no leídas" de la vista completa.
export const notificacionesKeys = {
  all: () => ['notificaciones'] as const,
  mis: (soloNoLeidas: boolean) => ['notificaciones', 'mis', soloNoLeidas] as const,
};
