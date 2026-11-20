import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'emp-1' }));

import { get, post, patch, del } from '../services/api';
import {
  reglasReabastecimientoService,
  lotesProductoService,
} from '../services/inventarioMaestrosService';
import { stockUbicacionesService } from '../services/almacenesService';
import AlmacenesPage from '../pages/Inventario/AlmacenesPage';
import ProductosPage from '../pages/Inventario/ProductosPage';
import UbicacionesAlmacenPage from '../pages/Inventario/UbicacionesAlmacenPage';
import InventarioMaestrosPage from '../pages/Inventario/InventarioMaestrosPage';

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

const almZonificado = {
  id_almacen: 'alm-z',
  id_empresa: 'emp-1',
  nombre_almacen: 'Almacén Zonificado',
  codigo_almacen: 'ALM-Z',
  direccion: 'Zona Industrial',
  usa_ubicaciones: true,
  activo: true,
};

const almSimple = {
  id_almacen: 'alm-s',
  id_empresa: 'emp-1',
  nombre_almacen: 'Almacén Simple',
  codigo_almacen: 'ALM-S',
  direccion: '',
  usa_ubicaciones: false,
  activo: true,
};

const ubicPick = {
  id_ubicacion: 'ub-pick',
  id_empresa: 'emp-1',
  id_almacen: 'alm-z',
  codigo_ubicacion: 'A-01',
  nombre_ubicacion: 'Picking A1',
  tipo_ubicacion: 'PICKING',
  pasillo: 'A',
  estante: '1',
  nivel: '1',
  posicion: '1',
  capacidad_maxima: null,
  unidad_capacidad: null,
  temperatura_minima: null,
  temperatura_maxima: null,
  activo: true,
  requiere_autorizacion: false,
  observaciones: null,
};

const ubicCuarentena = {
  ...ubicPick,
  id_ubicacion: 'ub-cua',
  codigo_ubicacion: 'C-01',
  nombre_ubicacion: 'Bóveda Cuarentena',
  tipo_ubicacion: 'CUARENTENA',
  requiere_autorizacion: true,
};

const producto1 = {
  id_producto: 'prod-1',
  id_empresa: 'emp-1',
  nombre_producto: 'Resina Epóxica',
  sku: 'RES-001',
  id_categoria: 'cat-1',
  id_unidad_medida_base: 'um-1',
  id_moneda_precio: 'mon-1',
  tipo_producto: 'FISICO',
  maneja_lotes: true,
  maneja_seriales: false,
  estrategia_salida: 'FEFO' as const,
  costo_promedio: '20.0000',
  precio_venta_sugerido: '35.0000',
  punto_reorden: '5.0000',
  activo: true,
};

const stockUbic1 = {
  id_stock_ubicacion: 'su-1',
  id_empresa: 'emp-1',
  id_almacen: 'alm-z',
  almacen_nombre: 'Almacén Zonificado',
  id_ubicacion: 'ub-pick',
  ubicacion_codigo: 'A-01',
  ubicacion_nombre: 'Picking A1',
  requiere_autorizacion: false,
  id_producto: 'prod-1',
  producto_nombre: 'Resina Epóxica',
  producto_sku: 'RES-001',
  id_variante: null,
  cantidad_disponible: '20.0000',
  cantidad_reservada: '3.0000',
  cantidad_libre: '17.0000',
  activo: true,
};

const regla1 = {
  id_regla: 'reg-1',
  id_empresa: 'emp-1',
  id_producto: 'prod-1',
  producto_nombre: 'Resina Epóxica',
  producto_sku: 'RES-001',
  id_variante: null,
  id_almacen: 'alm-z',
  almacen_nombre: 'Almacén Zonificado',
  stock_minimo: '10.0000',
  stock_maximo: '40.0000',
  cantidad_multiplo: '5.0000',
  ruta: 'COMPRA' as const,
  id_proveedor_preferido: 'prov-1',
  proveedor_nombre: 'Química Alfa C.A.',
  id_almacen_origen: null,
  almacen_origen_nombre: null,
  activo: true,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Servicios PR-16 (Reabastecimiento, Lotes, StockUbicacion)', () => {
  it('llama endpoints y parámetros correctos en reglasReabastecimientoService, lotesProductoService y stockUbicacionesService', async () => {
    vi.mocked(get).mockResolvedValue({ results: [] });
    vi.mocked(post).mockResolvedValue({ resultados: [] });
    vi.mocked(patch).mockResolvedValue({});
    vi.mocked(del).mockResolvedValue(undefined);

    await reglasReabastecimientoService.getAll({ almacen: 'alm-z', producto: 'prod-1' });
    expect(get).toHaveBeenCalledWith(
      '/inventario/reglas-reabastecimiento/?almacen=alm-z&producto=prod-1'
    );

    await reglasReabastecimientoService.evaluar({ almacen: 'alm-z', incluir_ok: true });
    expect(post).toHaveBeenCalledWith('/inventario/reglas-reabastecimiento/evaluar/', {
      incluir_ok: true,
      almacen: 'alm-z',
    });

    await reglasReabastecimientoService.generarBorrador('reg-1', { cantidad: '15.0000' });
    expect(post).toHaveBeenCalledWith('/inventario/reglas-reabastecimiento/reg-1/generar-borrador/', {
      cantidad: '15.0000',
    });

    await lotesProductoService.getAll({
      almacen: 'alm-z',
      producto: 'prod-1',
      por_vencer_dias: 30,
      solo_con_stock: true,
    });
    expect(get).toHaveBeenCalledWith(
      '/inventario/lotes-producto/?almacen=alm-z&producto=prod-1&por_vencer_dias=30&solo_con_stock=true'
    );

    await stockUbicacionesService.getAll({ almacen: 'alm-z', ubicacion: 'ub-pick' });
    expect(get).toHaveBeenCalledWith(
      '/almacenes/stock-ubicaciones/?almacen=alm-z&ubicacion=ub-pick'
    );

    await stockUbicacionesService.transferir({
      id_almacen: 'alm-z',
      id_ubicacion_origen: 'ub-pick',
      id_ubicacion_destino: 'ub-cua',
      id_producto: 'prod-1',
      cantidad: '4',
    });
    expect(post).toHaveBeenCalledWith('/almacenes/stock-ubicaciones/transferir/', {
      id_almacen: 'alm-z',
      id_ubicacion_origen: 'ub-pick',
      id_ubicacion_destino: 'ub-cua',
      id_producto: 'prod-1',
      cantidad: '4',
    });

    await stockUbicacionesService.reservar({
      id_almacen: 'alm-z',
      id_ubicacion: 'ub-pick',
      id_producto: 'prod-1',
      cantidad: '2',
      liberar: true,
    });
    expect(post).toHaveBeenCalledWith('/almacenes/stock-ubicaciones/reservar/', {
      id_almacen: 'alm-z',
      id_ubicacion: 'ub-pick',
      id_producto: 'prod-1',
      cantidad: '2',
      liberar: true,
    });
  });
});

describe('AlmacenesPage & ProductosPage opt-in PR-16', () => {
  it('AlmacenesPage muestra badges Activas/Simple y envía usa_ubicaciones al crear', async () => {
    vi.mocked(get).mockResolvedValue({ results: [almZonificado, almSimple] });
    vi.mocked(post).mockResolvedValue({ ...almZonificado, id_almacen: 'alm-new' });

    wrap(<AlmacenesPage />);
    expect(await screen.findByText('Activas')).toBeInTheDocument();
    expect(screen.getByText('Simple')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Nuevo almacén/i }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/^Nombre/i), {
      target: { value: 'Almacén Logístico' },
    });
    fireEvent.change(within(dialog).getByLabelText(/^Código/i), {
      target: { value: 'ALM-LOG' },
    });
    fireEvent.click(within(dialog).getByLabelText(/Usa ubicaciones internas/i));
    fireEvent.click(within(dialog).getByRole('button', { name: /Guardar/i }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        '/almacenes/almacenes/',
        expect.objectContaining({
          nombre_almacen: 'Almacén Logístico',
          usa_ubicaciones: true,
        })
      );
    });
  });

  it('ProductosPage muestra selector estrategia_salida al activar maneja_lotes', async () => {
    vi.mocked(get).mockImplementation(async (url: string) => {
      if (url.startsWith('/inventario/productos/')) return { results: [producto1] };
      if (url.startsWith('/inventario/categorias')) return { results: [{ id_categoria_producto: 'cat-1', nombre_categoria: 'Químicos' }] };
      if (url.startsWith('/inventario/unidades')) return { results: [{ id_unidad_medida: 'um-1', nombre: 'Litro', abreviatura: 'L' }] };
      if (url.startsWith('/finanzas/monedas/')) return [{ id_moneda: 'mon-1', nombre: 'Dólar', codigo_iso: 'USD' }];
      return { results: [] };
    });
    vi.mocked(post).mockResolvedValue({ ...producto1, id_producto: 'prod-new' });

    wrap(<ProductosPage />);
    expect(await screen.findByText('Resina Epóxica')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Nuevo producto/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).queryByLabelText(/Estrategia de salida de lotes/i)).toBeNull();

    fireEvent.click(within(dialog).getByLabelText(/Maneja lotes/i));
    expect(within(dialog).getByLabelText(/Estrategia de salida de lotes/i)).toBeInTheDocument();
  });
});

describe('UbicacionesAlmacenPage Stock por Ubicación y Autorización', () => {
  beforeEach(() => {
    vi.mocked(get).mockImplementation(async (url: string) => {
      if (url.startsWith('/almacenes/almacenes/')) return { results: [almZonificado, almSimple] };
      if (url.startsWith('/almacenes/ubicaciones-almacen/')) return { results: [ubicPick, ubicCuarentena] };
      if (url.startsWith('/almacenes/stock-ubicaciones/')) return { results: [stockUbic1] };
      if (url.startsWith('/inventario/productos/')) return { results: [producto1] };
      return { results: [] };
    });
  });

  it('cambia a Stock por Ubicación, alerta sobre autorización en cuarentena y ejecuta transferencia + reserva', async () => {
    vi.mocked(post).mockResolvedValue({ ...stockUbic1, cantidad_reservada: '5.0000', cantidad_libre: '15.0000' });

    wrap(<UbicacionesAlmacenPage />);
    expect(await screen.findByText('Picking A1')).toBeInTheDocument();
    expect(screen.getByText('Requiere autorización')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Stock por Ubicación' }));
    expect(await screen.findByText(/Resina Epóxica/)).toBeInTheDocument();

    // Transferir desde fila -> abrir modal, seleccionar destino Bóveda Cuarentena -> warning Alert aparece
    fireEvent.click(screen.getByRole('button', { name: /^Transferir$/i }));
    const dialogT = await screen.findByRole('dialog');
    expect(within(dialogT).getByText('Transferir entre ubicaciones')).toBeInTheDocument();

    const destSelect = within(dialogT).getByLabelText(/Ubicación destino/i);
    fireEvent.mouseDown(destSelect);
    const optCuarentena = await screen.findByRole('option', { name: /C-01 — Bóveda Cuarentena/i });
    fireEvent.click(optCuarentena);

    expect(
      await within(dialogT).findByText(/una de las ubicaciones seleccionadas requiere autorización/i)
    ).toBeInTheDocument();

    fireEvent.change(within(dialogT).getByLabelText(/^Cantidad$/i), { target: { value: '5' } });
    fireEvent.click(within(dialogT).getByRole('button', { name: /Confirmar transferencia/i }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        '/almacenes/stock-ubicaciones/transferir/',
        expect.objectContaining({
          id_almacen: 'alm-z',
          id_ubicacion_origen: 'ub-pick',
          id_ubicacion_destino: 'ub-cua',
          cantidad: '5',
        })
      );
    });
    expect(await screen.findByText(/Transferencia entre ubicaciones registrada/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    // Reservar / Liberar
    fireEvent.click(screen.getByRole('button', { name: /Reservar \/ Liberar/i }));
    const dialogR = await screen.findByRole('dialog');
    fireEvent.change(within(dialogR).getByLabelText(/^Cantidad$/i), { target: { value: '2' } });
    fireEvent.click(within(dialogR).getByRole('button', { name: /Aplicar/i }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        '/almacenes/stock-ubicaciones/reservar/',
        expect.objectContaining({
          id_almacen: 'alm-z',
          id_ubicacion: 'ub-pick',
          id_producto: 'prod-1',
          cantidad: '2',
          liberar: false,
        })
      );
    });
  });

  it('muestra alerta informativa cuando el almacén seleccionado no tiene usa_ubicaciones', async () => {
    vi.mocked(get).mockImplementation(async (url: string) => {
      if (url.startsWith('/almacenes/almacenes/')) return { results: [almSimple] };
      if (url.startsWith('/almacenes/ubicaciones-almacen/')) return { results: [] };
      if (url.startsWith('/almacenes/stock-ubicaciones/')) return { results: [] };
      if (url.startsWith('/inventario/productos/')) return { results: [producto1] };
      return { results: [] };
    });

    wrap(<UbicacionesAlmacenPage />);
    fireEvent.click(await screen.findByRole('tab', { name: 'Stock por Ubicación' }));

    const selects = await screen.findAllByLabelText(/^Almacén$/i);
    fireEvent.mouseDown(selects[0]);
    const optSimple = await screen.findByRole('option', { name: /Almacén Simple/i });
    fireEvent.click(optSimple);

    expect(await screen.findByText(/no tiene activado/i)).toBeInTheDocument();
  });
});

describe('InventarioMaestrosPage Tabs Reabastecimiento y Lotes', () => {
  const hoy = new Date();
  const vencidoIso = new Date(hoy.getTime() - 5 * 86400_000).toISOString().slice(0, 10);
  const porVencerIso = new Date(hoy.getTime() + 10 * 86400_000).toISOString().slice(0, 10);
  const vigenteIso = new Date(hoy.getTime() + 180 * 86400_000).toISOString().slice(0, 10);

  beforeEach(() => {
    vi.mocked(get).mockImplementation(async (url: string) => {
      if (url.startsWith('/inventario/variantes')) return { results: [] };
      if (url.startsWith('/inventario/productos/')) return { results: [producto1] };
      if (url.startsWith('/almacenes/almacenes/')) return { results: [almZonificado, almSimple] };
      if (url.startsWith('/proveedores/proveedores/')) return { results: [{ id_proveedor: 'prov-1', razon_social: 'Química Alfa C.A.' }] };
      if (url.startsWith('/inventario/reglas-reabastecimiento/')) return { results: [regla1] };
      if (url.startsWith('/inventario/lotes-producto/')) {
        return {
          results: [
            {
              id_lote: 'lote-1',
              id_empresa: 'emp-1',
              id_producto: 'prod-1',
              producto_nombre: 'Resina Epóxica',
              producto_sku: 'RES-001',
              id_variante: null,
              id_almacen: 'alm-z',
              almacen_nombre: 'Almacén Zonificado',
              numero_lote: 'L-VENC',
              fecha_fabricacion: null,
              fecha_vencimiento: vencidoIso,
              cantidad_disponible: '3.0000',
              cantidad_reservada: '0.0000',
              cantidad_libre: '3.0000',
              activo: true,
            },
            {
              id_lote: 'lote-2',
              id_empresa: 'emp-1',
              id_producto: 'prod-1',
              producto_nombre: 'Resina Epóxica',
              producto_sku: 'RES-001',
              id_variante: null,
              id_almacen: 'alm-z',
              almacen_nombre: 'Almacén Zonificado',
              numero_lote: 'L-PRONTO',
              fecha_fabricacion: null,
              fecha_vencimiento: porVencerIso,
              cantidad_disponible: '8.0000',
              cantidad_reservada: '2.0000',
              cantidad_libre: '6.0000',
              activo: true,
            },
            {
              id_lote: 'lote-3',
              id_empresa: 'emp-1',
              id_producto: 'prod-1',
              producto_nombre: 'Resina Epóxica',
              producto_sku: 'RES-001',
              id_variante: null,
              id_almacen: 'alm-z',
              almacen_nombre: 'Almacén Zonificado',
              numero_lote: 'L-OK',
              fecha_fabricacion: null,
              fecha_vencimiento: vigenteIso,
              cantidad_disponible: '20.0000',
              cantidad_reservada: '0.0000',
              cantidad_libre: '20.0000',
              activo: true,
            },
          ],
        };
      }
      return { results: [] };
    });
  });

  it('Tab Reabastecimiento evalúa reglas, muestra déficit y genera borrador', async () => {
    vi.mocked(post).mockImplementation(async (url: string) => {
      if (url === '/inventario/reglas-reabastecimiento/evaluar/') {
        return {
          resultados: [
            {
              id_regla: 'reg-1',
              id_producto: 'prod-1',
              producto_nombre: 'Resina Epóxica',
              producto_sku: 'RES-001',
              id_variante: null,
              id_almacen: 'alm-z',
              almacen_nombre: 'Almacén Zonificado',
              ruta: 'COMPRA',
              id_proveedor_preferido: 'prov-1',
              id_almacen_origen: null,
              stock_disponible: '6.0000',
              cantidad_comprometida: '0.0000',
              cantidad_en_transito: '0.0000',
              stock_libre: '6.0000',
              stock_proyectado: '6.0000',
              stock_minimo: '10.0000',
              stock_maximo: '40.0000',
              cantidad_multiplo: '5.0000',
              requiere_reabastecimiento: true,
              deficit: '34.0000',
              cantidad_sugerida: '35.0000',
            },
          ],
        };
      }
      if (url === '/inventario/reglas-reabastecimiento/reg-1/generar-borrador/') {
        return {
          ruta: 'COMPRA',
          tipo_documento: 'REQUISICION_COMPRA',
          id_documento: 'req-99',
          numero: 'REQ-0099',
          estado: 'BORRADOR',
          cantidad: '35.0000',
        };
      }
      return {};
    });

    wrap(<InventarioMaestrosPage />);
    fireEvent.click(screen.getByRole('tab', { name: 'Reabastecimiento' }));
    expect(await screen.findByText('Resina Epóxica')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Evaluar reabastecimiento/i }));
    expect(await screen.findByText('Déficit: 34.0000')).toBeInTheDocument();
    expect(screen.getByText('Sugerida: 35.0000')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Generar borrador/i }));
    expect(await screen.findByText(/REQ-0099/)).toBeInTheDocument();
  });

  it('Tab Lotes muestra badges de vencimiento y filtra Por vencer <= 30d', async () => {
    wrap(<InventarioMaestrosPage />);
    fireEvent.click(screen.getByRole('tab', { name: 'Lotes' }));

    expect(await screen.findByText('L-VENC')).toBeInTheDocument();
    expect(screen.getByText('Vencido')).toBeInTheDocument();
    expect(screen.getByText('Por vencer')).toBeInTheDocument();
    expect(screen.getByText('Vigente')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Por vencer <= 30d/i));
    await waitFor(() => {
      expect(get).toHaveBeenCalledWith(
        '/inventario/lotes-producto/?por_vencer_dias=30&solo_con_stock=true'
      );
    });
  });
});
