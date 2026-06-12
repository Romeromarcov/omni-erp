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

// ── CxP (Cuentas por Pagar) ───────────────────────────────────────────────────
export const cxpKeys = {
  cuentasAll: () => ['cxp', 'cuentas'] as const,
  cuentas: (page?: number, estado?: string | null) =>
    ['cxp', 'cuentas', page ?? 1, estado ?? null] as const,
  agingAll: () => ['cxp', 'aging'] as const,
  aging: (empresaId?: string | null) => ['cxp', 'aging', empresaId ?? null] as const,
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
};
