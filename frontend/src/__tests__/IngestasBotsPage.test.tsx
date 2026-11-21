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

import { get, post, patch, del } from '../services/api';
import {
  botsControlService,
  botUsuariosService,
  ingestasService,
} from '../services/botsIngestService';
import IngestasBotsPage from '../pages/Bots/IngestasBotsPage';
import { etiquetaBot, formatearHaceSegundos, resumenIngesta } from '../pages/Bots/utils';

const base = {
  odoo_ref: '',
  fecha_creacion: '2026-12-01T10:00:00Z',
  fecha_actualizacion: '2026-12-01T10:00:00Z',
  resultado: {},
};

const pagoIncompleto = {
  ...base,
  id_ingesta: 'i1',
  kind: 'pago',
  estado: 'INCOMPLETO',
  incompleto: ['referencia'],
  auto: true,
  idempotency_key: 'k1',
  payload: { cliente: 'Taller Rojas', monto: '50', moneda: 'USD' },
};

const pedido = {
  ...base,
  id_ingesta: 'i2',
  kind: 'pedido',
  estado: 'PROCESADO',
  incompleto: [],
  auto: false,
  idempotency_key: 'k2',
  resultado: { numero: 'PED-00001' },
  payload: { cliente: 'Bodega Sur', rif: 'J-123456789' },
};

const gastoCompra = {
  ...base,
  id_ingesta: 'i3',
  kind: 'gasto',
  estado: 'PROCESADO',
  incompleto: [],
  auto: false,
  error: 'Falta diario de compras en Odoo.',
  idempotency_key: 'k3',
  resultado: { gasto_id: 'GA-001' },
  payload: { proveedor: 'Papelería Central', monto_total: '35.50', moneda: 'USD' },
};

const facturaIncompleta = {
  ...base,
  id_ingesta: 'i4/esp',
  kind: 'factura_proveedor',
  estado: 'INCOMPLETO',
  incompleto: ['numero_control'],
  auto: false,
  idempotency_key: 'k4',
  resultado: {},
  payload: { proveedor: 'Distribuidora Norte', monto_total: '120.00', moneda: 'USD' },
};

const usuarios = [
  {
    id: 'u1',
    username: 'ana',
    email: 'a@x.com',
    first_name: 'Ana',
    last_name: 'Pérez',
    is_active: true,
    es_superusuario_omni: false,
  },
];

const botPedidos = {
  bot: 'pedidos',
  nombre: 'Ventas y Pedidos',
  habilitado: true,
  en_linea: true,
  ultimo_latido: '2026-12-01T10:00:00Z',
  hace_segundos: 25,
  visto_alguna_vez: true,
  version: '1.2',
  estado: {
    modo: 'polling',
    gemini: 'ok',
    omni: 'ok',
    mensajes_hoy: 14,
    errores_hoy: 1,
    ultimo_error: 'Timeout temporal hacia API',
  },
  parametros: { auto_envio_min: 10, gemini_model: 'gemini-2.5-flash' },
  chats: { grupo: -100555, respaldo: null },
  url_panel: '',
  mensaje: '',
  actualizado_por: 'ana@x.com',
  actualizado_en: '2026-12-01T10:00:00Z',
  n_usuarios: 2,
};

const detallePedidos = {
  ...botPedidos,
  usuarios: [{ id_bot_usuario: 'b1', telegram_user_id: 111222333, email: 'a@x.com', nombre: 'Ana TG', bots: ['pedidos'] }],
  ingestas_recientes: [],
  historial: [{ dia: '2026-12-01', latidos: 40, mensajes: 14, errores: 1 }],
  bitacora: [],
  modelos_sugeridos: ['gemini-2.5-flash', 'gemini-2.5-pro'],
};

const destinosMock = {
  omni: { estado: 'ok', por_bot: { pedidos: 'ok' } },
  cxc: { estado: 'desactivado', por_bot: {} },
  gemini: { estado: 'ok', por_bot: { pedidos: 'ok' } },
  outbox_pendientes: 0,
  ingestas: { PROCESADO: 2, BORRADOR: 0, INCOMPLETO: 2, SINCRONIZADO: 4, ERROR: 0 },
  bots_en_linea: 1,
  bots_total: 5,
};

const bitacoraMock = {
  items: [
    {
      id: 'bit-1',
      entidad: 'bot:pedidos',
      accion: 'actualizar',
      antes: { habilitado: true },
      despues: { habilitado: false },
      actor: 'ana@x.com',
      en: '2026-12-01T10:05:00Z',
    },
    {
      id: 'bit-2',
      entidad: 'usuario:111222333',
      accion: 'alta',
      antes: {},
      despues: { telegram_user_id: 111222333 },
      actor: 'ana@x.com',
      en: '2026-12-01T10:06:00Z',
    },
  ],
};

function setupGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/bots/ingest/')) {
      if (url.includes('estado=INCOMPLETO')) {
        return Promise.resolve([pagoIncompleto, facturaIncompleta]);
      }
      if (url.includes('kind=gasto')) {
        return Promise.resolve([gastoCompra]);
      }
      return Promise.resolve([pagoIncompleto, pedido, gastoCompra, facturaIncompleta]);
    }
    if (url === '/bots/control/') {
      return Promise.resolve({ items: [botPedidos] });
    }
    if (url.startsWith('/bots/control/pedidos/')) {
      return Promise.resolve(detallePedidos);
    }
    if (url === '/bots/destinos/') {
      return Promise.resolve(destinosMock);
    }
    if (url.startsWith('/bots/bitacora/')) {
      return Promise.resolve(bitacoraMock);
    }
    if (url.startsWith('/bots/usuarios/')) {
      return Promise.resolve([
        {
          id_bot_usuario: 'b1',
          id_empresa: 'e1',
          telegram_user_id: 111222333,
          usuario: 'u1',
          nombre: 'Ana TG',
          bots: ['pedidos'],
          activo: true,
        },
      ]);
    }
    if (url.startsWith('/core/usuarios/')) return Promise.resolve(usuarios);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <IngestasBotsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('IngestasBotsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupGet();
  });

  it('lista las ingestas (incluidos gastos y facturas de compra) y filtra por estado o tipo', async () => {
    renderPage();
    expect(await screen.findByText('Taller Rojas · 50 USD')).toBeInTheDocument();
    expect(screen.getByText('Bodega Sur')).toBeInTheDocument();
    expect(screen.getByText('Papelería Central · 35.50 USD')).toBeInTheDocument();
    expect(screen.getByText('Distribuidora Norte · 120.00 USD')).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByLabelText('Tipo'));
    fireEvent.click(await screen.findByRole('option', { name: 'Gasto' }));
    await waitFor(() => expect(screen.queryByText('Bodega Sur')).not.toBeInTheDocument());
    expect(vi.mocked(get).mock.calls.map((c) => c[0])).toContain('/bots/ingest/?kind=gasto');

    fireEvent.click(screen.getByRole('button', { name: 'Ver incompletas' }));
    await waitFor(() => {
      expect(vi.mocked(get).mock.calls.map((c) => c[0])).toContain('/bots/ingest/?estado=INCOMPLETO&kind=gasto');
    });
  });

  it('muestra el detalle del borrador, nota de sincronización y permite reintentar envío a Odoo', async () => {
    vi.mocked(post).mockResolvedValue({ ...gastoCompra, estado: 'SINCRONIZADO' });
    renderPage();
    const filaGasto = (await screen.findByText('Papelería Central · 35.50 USD')).closest('tr') as HTMLElement;
    fireEvent.click(within(filaGasto).getByRole('button', { name: 'Ver' }));
    const dialogo = await screen.findByRole('dialog');
    expect(within(dialogo).getByText(/Falta diario de compras en Odoo/)).toBeInTheDocument();
    expect(within(dialogo).getByText(/GA-001/)).toBeInTheDocument();
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Cerrar' }));

    fireEvent.click(within(filaGasto).getByRole('button', { name: 'Enviar a Odoo' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/bots/ingest/i3/sincronizar/', {}));
    expect(await screen.findByText(/Empuje a Odoo encolado/)).toBeInTheDocument();
  });

  it('completa pagos y facturas de proveedor incompletas codificando el id en la ruta', async () => {
    vi.mocked(post).mockResolvedValue({ ...facturaIncompleta, estado: 'PROCESADO', incompleto: [] });
    renderPage();
    const filaPedido = (await screen.findByText('Bodega Sur')).closest('tr') as HTMLElement;
    expect(within(filaPedido).queryByRole('button', { name: 'Completar' })).not.toBeInTheDocument();

    const filaFactura = screen.getByText('Distribuidora Norte · 120.00 USD').closest('tr') as HTMLElement;
    fireEvent.click(within(filaFactura).getByRole('button', { name: 'Completar' }));
    const dialogo = await screen.findByRole('dialog');
    const guardar = within(dialogo).getByRole('button', { name: 'Guardar cambios' });
    expect(guardar).toBeDisabled();
    fireEvent.change(within(dialogo).getByLabelText('Número de control'), { target: { value: '00-889900' } });
    expect(guardar).toBeEnabled();
    fireEvent.click(guardar);
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/bots/ingest/i4%2Fesp/completar/', {
        cambios: { numero_control: '00-889900' },
      }),
    );
  });

  it('muestra el error del backend al completar', async () => {
    vi.mocked(post).mockRejectedValue(new Error('{"error":"Esta ingesta ya fue sincronizada; edítala en Odoo."}'));
    renderPage();
    const fila = (await screen.findByText('Taller Rojas · 50 USD')).closest('tr') as HTMLElement;
    fireEvent.click(within(fila).getByRole('button', { name: 'Completar' }));
    const dialogo = await screen.findByRole('dialog');
    fireEvent.change(within(dialogo).getByLabelText('Referencia'), { target: { value: 'X1' } });
    fireEvent.click(within(dialogo).getByRole('button', { name: 'Guardar cambios' }));
    expect(await within(dialogo).findByText(/edítala en Odoo/)).toBeInTheDocument();
  });

  it('administra la flota en «Flota y Control»: KPIs, pausa rápida, validaciones de chat y error de detalle', async () => {
    vi.mocked(patch).mockResolvedValue({ ...detallePedidos, habilitado: false });
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Flota y Control' }));
    expect(await screen.findByText('1 / 5')).toBeInTheDocument();
    expect(screen.getByText('En línea')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('switch', { name: 'Habilitar Ventas y Pedidos' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/bots/control/pedidos/', { habilitado: false }),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Configurar' }));
    const dialogo = await screen.findByRole('dialog');
    expect(await within(dialogo).findByText(/2026-12-01: 14 msg/)).toBeInTheDocument();
    expect(within(dialogo).getByText(/Timeout temporal hacia API/)).toBeInTheDocument();

    const campoGrupo = within(dialogo).getByLabelText(/^ID chat de grupo/);
    const botonGuardar = within(dialogo).getByRole('button', { name: 'Guardar configuración' });
    fireEvent.change(campoGrupo, { target: { value: '1e5' } });
    expect(botonGuardar).toBeDisabled();
    fireEvent.change(campoGrupo, { target: { value: '-100777' } });
    expect(botonGuardar).toBeEnabled();

    fireEvent.change(within(dialogo).getByLabelText('Mensaje de pausa (opcional)'), {
      target: { value: 'Ventana de mantenimiento' },
    });
    fireEvent.click(botonGuardar);
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/bots/control/pedidos/',
        expect.objectContaining({
          nombre: 'Ventas y Pedidos',
          mensaje: 'Ventana de mantenimiento',
          parametros: { auto_envio_min: 10, gemini_model: 'gemini-2.5-flash' },
          chats: { grupo: -100777, respaldo: null },
        }),
      ),
    );
  });

  it('muestra alerta en el diálogo si falla la carga de configuración de un bot', async () => {
    vi.mocked(get).mockImplementation((url: string) => {
      if (url === '/bots/control/') return Promise.resolve({ items: [botPedidos] });
      if (url.startsWith('/bots/control/pedidos/')) {
        return Promise.reject(new Error('{"error":"Sin permiso para ver este bot."}'));
      }
      if (url === '/bots/destinos/') return Promise.resolve(destinosMock);
      return Promise.resolve([]);
    });
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Flota y Control' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Configurar' }));
    const dialogo = await screen.findByRole('dialog');
    expect(await within(dialogo).findByText(/Sin permiso para ver este bot/)).toBeInTheDocument();
  });

  it('administra usuarios de Telegram: alta con safe integer, edición de alcance de bots y baja', async () => {
    vi.mocked(post).mockResolvedValue({});
    vi.mocked(patch).mockResolvedValue({});
    vi.mocked(del).mockResolvedValue(undefined as never);
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Usuarios de Telegram' }));
    expect(await screen.findByText('111222333')).toBeInTheDocument();
    expect(await screen.findByText('Ana Pérez (ana)')).toBeInTheDocument();
    expect(screen.getByText('Ventas y Pedidos')).toBeInTheDocument();

    // Alta validando Number.isSafeInteger
    fireEvent.click(screen.getByRole('button', { name: 'Autorizar usuario' }));
    const dialogoAlta = await screen.findByRole('dialog');
    const guardarAlta = within(dialogoAlta).getByRole('button', { name: 'Guardar' });
    fireEvent.mouseDown(within(dialogoAlta).getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: 'Ana Pérez (ana)' }));
    fireEvent.change(within(dialogoAlta).getByLabelText(/^ID numérico/), {
      target: { value: '99999999999999999999' },
    });
    expect(guardarAlta).toBeDisabled();
    fireEvent.change(within(dialogoAlta).getByLabelText(/^ID numérico/), { target: { value: '555' } });
    fireEvent.click(within(dialogoAlta).getByText('Cobranzas'));
    fireEvent.click(guardarAlta);
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/bots/usuarios/', {
        telegram_user_id: 555,
        usuario: 'u1',
        nombre: '',
        bots: ['cobranza'],
      }),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    // Edición quitando restricción de bot -> vuelve a [] («Todos los bots»)
    const fila = (await screen.findByText('111222333')).closest('tr') as HTMLElement;
    fireEvent.click(await within(fila).findByRole('button', { name: 'Editar' }));
    const dialogoEdicion = await screen.findByRole('dialog');
    fireEvent.click(within(dialogoEdicion).getByText('Ventas y Pedidos'));
    fireEvent.click(within(dialogoEdicion).getByRole('button', { name: 'Guardar' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith('/bots/usuarios/b1/', {
        telegram_user_id: 111222333,
        usuario: 'u1',
        nombre: 'Ana TG',
        bots: [],
      }),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    // Baja con confirmación
    const filaBaja = (await screen.findByText('111222333')).closest('tr') as HTMLElement;
    fireEvent.click(await within(filaBaja).findByRole('button', { name: 'Quitar' }));
    const dialogoBorrar = await screen.findByRole('dialog');
    fireEvent.click(within(dialogoBorrar).getByRole('button', { name: 'Quitar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/bots/usuarios/b1/'));
  });

  it('consulta la bitácora mostrando antes → después y permite filtrar por entidades usuario:*', async () => {
    renderPage();
    fireEvent.click(screen.getByRole('tab', { name: 'Bitácora' }));
    expect(await screen.findByText('bot:pedidos')).toBeInTheDocument();
    expect(screen.getByText('{"habilitado":true} → {"habilitado":false}')).toBeInTheDocument();
    expect(screen.getByText('usuario:111222333')).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: /Usuario Telegram 111222333/ }));
    await waitFor(() => {
      const urls = vi.mocked(get).mock.calls.map((c) => c[0]);
      expect(urls).toContain('/bots/bitacora/?entidad=usuario%3A111222333&limite=50');
    });
  });
});

describe('resumenIngesta, helpers y servicios de bots', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('prioriza cliente, nombre, proveedor, título o rif y soporta monto o monto_total', () => {
    expect(resumenIngesta({ payload: { nombre: 'Pedro' } })).toBe('Pedro');
    expect(resumenIngesta({ payload: { titulo: 'Promo PDV' } })).toBe('Promo PDV');
    expect(resumenIngesta({ payload: { proveedor: 'Lubri SA', monto: '900', moneda: 'USD' } })).toBe('Lubri SA · 900 USD');
    expect(resumenIngesta({ payload: { proveedor: 'Suministros', monto_total: '45', moneda: 'VES' } })).toBe('Suministros · 45 VES');
    expect(resumenIngesta({ payload: {} })).toBe('—');
    expect(etiquetaBot('pedidos')).toBe('Ventas y Pedidos');
    expect(etiquetaBot('custom_bot')).toBe('custom_bot');
    expect(formatearHaceSegundos(null)).toBe('Sin latidos');
    expect(formatearHaceSegundos(30)).toBe('Hace 30 s');
    expect(formatearHaceSegundos(180)).toBe('Hace 3 min');
    expect(formatearHaceSegundos(7200)).toBe('Hace 2 h');
    expect(formatearHaceSegundos(172800)).toBe('Hace 2 d');
  });

  it('cubre ramas de botsIngestService (extraerItems con arreglo/paginado y argumentos por defecto)', async () => {
    vi.mocked(get)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([botPedidos])
      .mockResolvedValueOnce({ results: bitacoraMock.items });
    vi.mocked(patch).mockResolvedValue({
      id_bot_usuario: 'b2',
      id_empresa: 'e1',
      telegram_user_id: 9,
      usuario: 'u1',
      nombre: 'Solo nombre',
      activo: true,
    });

    await expect(ingestasService.getAll()).resolves.toEqual([]);
    await expect(botsControlService.listarFlota()).resolves.toEqual([botPedidos]);
    await expect(botsControlService.listarBitacora()).resolves.toEqual(bitacoraMock.items);
    await botUsuariosService.update('id con espacio', { nombre: 'Solo nombre' });

    expect(get).toHaveBeenNthCalledWith(1, '/bots/ingest/');
    expect(get).toHaveBeenNthCalledWith(2, '/bots/control/');
    expect(get).toHaveBeenNthCalledWith(3, '/bots/bitacora/');
    expect(patch).toHaveBeenCalledWith('/bots/usuarios/id%20con%20espacio/', { nombre: 'Solo nombre' });
  });
});
