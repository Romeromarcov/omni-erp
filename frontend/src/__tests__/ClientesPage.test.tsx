import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'e1' }));

import { get, post, patch, del } from '../services/api';
import ClientesPage from '../pages/CRM/ClientesPage';

const clienteApi = {
  id_cliente: 'cli-1',
  id_empresa: 'e1',
  razon_social: 'ACME C.A.',
  nombre_comercial: 'ACME',
  rif: 'J-12345678',
  direccion: null,
  telefono: '04141234567',
  email: 'ventas@acme.com',
  tipo_cliente: 'CREDITO',
  limite_credito: '1000.00',
  dias_credito: 30,
  activo: true,
  contacto: null,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ClientesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ClientesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/crm/clientes/cli-1/credito-disponible')) {
        return Promise.resolve({
          credito_disponible: '700.00',
          limite_credito: '1000.00',
          saldo_pendiente: '300.00',
          bloqueado: false,
        });
      }
      if (url.startsWith('/crm/clientes/cli-1/historial-ventas')) {
        return Promise.resolve({ cliente_id: 'cli-1', pedidos: [] });
      }
      if (url.startsWith('/crm/contactos-cliente')) return Promise.resolve([]);
      if (url.startsWith('/crm/direcciones-cliente')) return Promise.resolve([]);
      if (url.startsWith('/crm/clientes')) return Promise.resolve([clienteApi]);
      return Promise.resolve([]);
    });
  });

  it('lista los clientes con su RIF y tipo', async () => {
    renderPage();
    expect(await screen.findByText('ACME C.A.')).toBeInTheDocument();
    expect(screen.getByText('J-12345678')).toBeInTheDocument();
    expect(screen.getByText('CREDITO')).toBeInTheDocument();
  });

  it('valida razón social y RIF requeridos al crear', async () => {
    renderPage();
    await screen.findByText('ACME C.A.');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }));
    expect(await screen.findByText('Nuevo cliente', { selector: 'h2' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete la razón social y el RIF/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un cliente de contado sin enviar límite/días de crédito', async () => {
    vi.mocked(post).mockResolvedValue({ id_cliente: 'cli-2' });
    renderPage();
    await screen.findByText('ACME C.A.');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }));
    fireEvent.change(await screen.findByLabelText(/Razón social/), {
      target: { value: 'Nuevo Cliente' },
    });
    fireEvent.change(screen.getByLabelText(/RIF/), { target: { value: 'V-99999999' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/crm/clientes/',
        expect.objectContaining({
          id_empresa: 'e1',
          razon_social: 'Nuevo Cliente',
          rif: 'V-99999999',
          tipo_cliente: 'CONTADO',
          limite_credito: '0',
          dias_credito: 0,
        }),
      ),
    );
  });

  it('editar un cliente envía el payload por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_cliente: 'cli-1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const razon = await screen.findByLabelText(/Razón social/);
    fireEvent.change(razon, { target: { value: 'ACME Editado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/crm/clientes/cli-1/',
        expect.objectContaining({
          razon_social: 'ACME Editado',
          tipo_cliente: 'CREDITO',
          limite_credito: '1000.00',
          dias_credito: 30,
        }),
      ),
    );
  });

  it('eliminar un cliente pide confirmación y llama al servicio', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/crm/clientes/cli-1/'));
    confirmSpy.mockRestore();
  });

  it('no elimina si el usuario cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('abre el detalle y muestra el crédito disponible', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Detalle' }));
    expect(await screen.findByText('Crédito disponible')).toBeInTheDocument();
    expect(await screen.findByText(/Disponible: 700.00/)).toBeInTheDocument();
    expect(screen.getByText('Contactos')).toBeInTheDocument();
    expect(screen.getByText('Direcciones')).toBeInTheDocument();
  });

  it('muestra error al fallar el guardado de un cliente (mensajeDeError)', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ rif: ['RIF inválido.'] })));
    renderPage();
    await screen.findByText('ACME C.A.');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }));
    fireEvent.change(await screen.findByLabelText(/Razón social/), {
      target: { value: 'Cliente X' },
    });
    fireEvent.change(screen.getByLabelText(/RIF/), { target: { value: 'X-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/rif: RIF inválido\./)).toBeInTheDocument();
  });

  it('captura todos los campos opcionales del formulario de cliente', async () => {
    vi.mocked(post).mockResolvedValue({ id_cliente: 'cli-9' });
    renderPage();
    await screen.findByText('ACME C.A.');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }));
    fireEvent.change(await screen.findByLabelText(/Razón social/), {
      target: { value: 'Cliente Completo' },
    });
    fireEvent.change(screen.getByLabelText(/RIF/), { target: { value: 'J-10101010' } });
    fireEvent.change(screen.getByLabelText(/Nombre comercial/), { target: { value: 'CC' } });
    fireEvent.change(screen.getByLabelText(/Teléfono/), { target: { value: '02125551212' } });
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: 'info@cc.com' } });
    fireEvent.change(screen.getByLabelText(/Dirección/), { target: { value: 'Calle 1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/crm/clientes/',
        expect.objectContaining({
          razon_social: 'Cliente Completo',
          nombre_comercial: 'CC',
          telefono: '02125551212',
          email: 'info@cc.com',
          direccion: 'Calle 1',
        }),
      ),
    );
  });

  it('cierra el diálogo de cliente con Cancelar', async () => {
    renderPage();
    await screen.findByText('ACME C.A.');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }));
    await screen.findByText('Nuevo cliente', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    await waitFor(() =>
      expect(screen.queryByText('Nuevo cliente', { selector: 'h2' })).not.toBeInTheDocument(),
    );
  });

  it('crea un cliente de crédito enviando límite y días', async () => {
    vi.mocked(post).mockResolvedValue({ id_cliente: 'cli-3' });
    renderPage();
    await screen.findByText('ACME C.A.');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }));
    fireEvent.change(await screen.findByLabelText(/Razón social/), {
      target: { value: 'Cliente Crédito' },
    });
    fireEvent.change(screen.getByLabelText(/RIF/), { target: { value: 'J-77777777' } });
    // Cambiar a tipo CREDITO revela los campos de límite/días.
    fireEvent.mouseDown(screen.getByLabelText(/Tipo de cliente/));
    fireEvent.click(await screen.findByRole('option', { name: 'Crédito' }));
    fireEvent.change(await screen.findByLabelText(/Límite de crédito/), {
      target: { value: '500.50' },
    });
    fireEvent.change(screen.getByLabelText(/Días de crédito/), { target: { value: '15' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/crm/clientes/',
        expect.objectContaining({
          razon_social: 'Cliente Crédito',
          tipo_cliente: 'CREDITO',
          limite_credito: '500.50',
          dias_credito: 15,
        }),
      ),
    );
  });
});

// ── Drawer de Detalle: crédito de contado e historial con pedidos ─────────────

describe('ClientesPage — detalle (contado e historial)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/crm/clientes/cli-1/credito-disponible')) {
        return Promise.resolve({ credito_disponible: null, detalle: 'Cliente de contado.' });
      }
      if (url.startsWith('/crm/clientes/cli-1/historial-ventas')) {
        return Promise.resolve({
          cliente_id: 'cli-1',
          pedidos: [
            { id_pedido: 'p1', numero_pedido: 'PED-001', fecha_pedido: '2026-06-01', estado: 'CONFIRMADO' },
          ],
        });
      }
      if (url.startsWith('/crm/contactos-cliente')) return Promise.resolve([]);
      if (url.startsWith('/crm/direcciones-cliente')) return Promise.resolve([]);
      if (url.startsWith('/crm/clientes')) return Promise.resolve([clienteApi]);
      return Promise.resolve([]);
    });
  });

  it('muestra el detalle de contado y un pedido del historial', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Detalle' }));
    expect(await screen.findByText('Cliente de contado.')).toBeInTheDocument();
    expect(await screen.findByText(/PED-001 · 2026-06-01 · CONFIRMADO/)).toBeInTheDocument();
  });

  it('cierra el drawer con el botón de cerrar', async () => {
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Detalle' }));
    await screen.findByText('Cliente de contado.');
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar detalle' }));
    await waitFor(() =>
      expect(screen.queryByText('Cliente de contado.')).not.toBeInTheDocument(),
    );
  });
});

// ── Drawer de Detalle: CRUD inline de contactos y direcciones ─────────────────

const contactoApi = {
  id_contacto: 'k1',
  id_empresa: 'e1',
  id_cliente: 'cli-1',
  nombre_contacto: 'Ana',
  apellido_contacto: 'Pérez',
  cargo: 'Compras',
  telefono_directo: null,
  telefono_movil: '04140000000',
  email_contacto: 'ana@acme.com',
  es_contacto_principal: true,
  observaciones: null,
};

const direccionApi = {
  id_direccion: 'd1',
  id_empresa: 'e1',
  id_cliente: 'cli-1',
  tipo_direccion: 'FISCAL',
  direccion_completa: 'Av. Principal, Edif. X',
  ciudad: 'Caracas',
  estado_provincia: 'Distrito Capital',
  codigo_postal: null,
  pais: 'Venezuela',
  telefono: null,
  persona_contacto: null,
  es_direccion_principal: true,
  observaciones: null,
};

function mockDetalle(opts: { contactos?: unknown[]; direcciones?: unknown[] } = {}) {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/crm/clientes/cli-1/credito-disponible')) {
      return Promise.resolve({ credito_disponible: null, detalle: 'Cliente de contado.' });
    }
    if (url.startsWith('/crm/clientes/cli-1/historial-ventas')) {
      return Promise.resolve({ cliente_id: 'cli-1', pedidos: [] });
    }
    if (url.startsWith('/crm/contactos-cliente')) return Promise.resolve(opts.contactos ?? []);
    if (url.startsWith('/crm/direcciones-cliente')) return Promise.resolve(opts.direcciones ?? []);
    if (url.startsWith('/crm/clientes')) return Promise.resolve([clienteApi]);
    return Promise.resolve([]);
  });
}

async function abrirDetalle() {
  renderPage();
  fireEvent.click(await screen.findByRole('button', { name: 'Detalle' }));
  await screen.findByText('Contactos');
}

describe('ClientesPage — CRUD inline de Contactos', () => {
  beforeEach(() => vi.clearAllMocks());

  it('valida los campos requeridos del contacto', async () => {
    mockDetalle();
    await abrirDetalle();
    fireEvent.click(screen.getByRole('button', { name: 'Agregar contacto' }));
    expect(
      await screen.findByText(/Complete nombre, apellido y email del contacto/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un contacto con el payload correcto', async () => {
    mockDetalle();
    vi.mocked(post).mockResolvedValue({ id_contacto: 'k-new' });
    await abrirDetalle();
    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Luis' } });
    fireEvent.change(screen.getByLabelText('Apellido'), { target: { value: 'Gómez' } });
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'luis@acme.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar contacto' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/crm/contactos-cliente/',
        expect.objectContaining({
          id_empresa: 'e1',
          id_cliente: 'cli-1',
          nombre_contacto: 'Luis',
          apellido_contacto: 'Gómez',
          email_contacto: 'luis@acme.com',
          es_contacto_principal: false,
        }),
      ),
    );
  });

  it('edita un contacto existente (precarga el formulario y hace PATCH)', async () => {
    mockDetalle({ contactos: [contactoApi] });
    vi.mocked(patch).mockResolvedValue({ id_contacto: 'k1' });
    await abrirDetalle();
    expect(await screen.findByText(/Ana Pérez/)).toBeInTheDocument();
    // Hay un "Editar" de cliente en la fila y otro en el contacto; el del contacto
    // está dentro del drawer — tomamos el último.
    const editButtons = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editButtons[editButtons.length - 1]);
    const nombre = screen.getByLabelText('Nombre') as HTMLInputElement;
    await waitFor(() => expect(nombre.value).toBe('Ana'));
    fireEvent.change(nombre, { target: { value: 'Ana María' } });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar contacto' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/crm/contactos-cliente/k1/',
        expect.objectContaining({ nombre_contacto: 'Ana María' }),
      ),
    );
  });

  it('elimina un contacto', async () => {
    mockDetalle({ contactos: [contactoApi] });
    vi.mocked(del).mockResolvedValue(undefined);
    await abrirDetalle();
    await screen.findByText(/Ana Pérez/);
    const delButtons = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(delButtons[delButtons.length - 1]);
    await waitFor(() => expect(del).toHaveBeenCalledWith('/crm/contactos-cliente/k1/'));
  });

  it('muestra error al fallar la creación de un contacto', async () => {
    mockDetalle();
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ detail: 'Email duplicado.' })));
    await abrirDetalle();
    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Luis' } });
    fireEvent.change(screen.getByLabelText('Apellido'), { target: { value: 'Gómez' } });
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'luis@acme.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar contacto' }));
    expect(await screen.findByText(/Email duplicado\./)).toBeInTheDocument();
  });

  it('captura cargo, móvil y principal y permite cancelar la edición', async () => {
    mockDetalle({ contactos: [contactoApi] });
    await abrirDetalle();
    await screen.findByText(/Ana Pérez/);
    // Rellena campos opcionales del formulario de contacto.
    fireEvent.change(screen.getByLabelText('Cargo'), { target: { value: 'Gerente' } });
    fireEvent.change(screen.getByLabelText('Móvil'), { target: { value: '04149998877' } });
    fireEvent.click(screen.getByLabelText('Contacto principal'));
    // Entra en modo edición y luego cancela (cubre reset + botón Cancelar inline).
    const editButtons = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editButtons[editButtons.length - 1]);
    const cancelar = await screen.findByRole('button', { name: 'Cancelar' });
    fireEvent.click(cancelar);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Agregar contacto' })).toBeInTheDocument(),
    );
  });
});

describe('ClientesPage — CRUD inline de Direcciones', () => {
  beforeEach(() => vi.clearAllMocks());

  it('valida los campos requeridos de la dirección', async () => {
    mockDetalle();
    await abrirDetalle();
    fireEvent.click(screen.getByRole('button', { name: 'Agregar dirección' }));
    expect(
      await screen.findByText(/Complete dirección, ciudad y estado\/provincia/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una dirección con el payload correcto', async () => {
    mockDetalle();
    vi.mocked(post).mockResolvedValue({ id_direccion: 'd-new' });
    await abrirDetalle();
    fireEvent.change(screen.getByLabelText('Dirección completa'), {
      target: { value: 'Calle 5, Casa 10' },
    });
    fireEvent.change(screen.getByLabelText('Ciudad'), { target: { value: 'Valencia' } });
    fireEvent.change(screen.getByLabelText('Estado/Provincia'), { target: { value: 'Carabobo' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar dirección' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/crm/direcciones-cliente/',
        expect.objectContaining({
          id_empresa: 'e1',
          id_cliente: 'cli-1',
          tipo_direccion: 'FISCAL',
          direccion_completa: 'Calle 5, Casa 10',
          ciudad: 'Valencia',
          estado_provincia: 'Carabobo',
          pais: 'Venezuela',
        }),
      ),
    );
  });

  it('edita una dirección existente (precarga y hace PATCH)', async () => {
    mockDetalle({ direcciones: [direccionApi] });
    vi.mocked(patch).mockResolvedValue({ id_direccion: 'd1' });
    await abrirDetalle();
    expect(await screen.findByText(/Av. Principal, Edif. X/)).toBeInTheDocument();
    const editButtons = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editButtons[editButtons.length - 1]);
    const ciudad = screen.getByLabelText('Ciudad') as HTMLInputElement;
    await waitFor(() => expect(ciudad.value).toBe('Caracas'));
    fireEvent.change(ciudad, { target: { value: 'Maracay' } });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar dirección' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/crm/direcciones-cliente/d1/',
        expect.objectContaining({ ciudad: 'Maracay' }),
      ),
    );
  });

  it('elimina una dirección', async () => {
    mockDetalle({ direcciones: [direccionApi] });
    vi.mocked(del).mockResolvedValue(undefined);
    await abrirDetalle();
    await screen.findByText(/Av. Principal, Edif. X/);
    const delButtons = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(delButtons[delButtons.length - 1]);
    await waitFor(() => expect(del).toHaveBeenCalledWith('/crm/direcciones-cliente/d1/'));
  });

  it('cambia el tipo de dirección, marca principal y cancela la edición', async () => {
    mockDetalle({ direcciones: [direccionApi] });
    await abrirDetalle();
    await screen.findByText(/Av. Principal, Edif. X/);
    // Cambia el select de tipo de dirección (cubre su onChange).
    fireEvent.mouseDown(screen.getByLabelText(/Tipo de dirección/));
    fireEvent.click(await screen.findByRole('option', { name: 'Entrega' }));
    fireEvent.click(screen.getByLabelText('Dirección principal'));
    // Entra en edición y cancela (cubre reset + botón Cancelar inline).
    const editButtons = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editButtons[editButtons.length - 1]);
    const cancelar = await screen.findByRole('button', { name: 'Cancelar' });
    fireEvent.click(cancelar);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Agregar dirección' })).toBeInTheDocument(),
    );
  });

  it('muestra error al fallar la creación de una dirección', async () => {
    mockDetalle();
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ detail: 'Dirección inválida.' })));
    await abrirDetalle();
    fireEvent.change(screen.getByLabelText('Dirección completa'), {
      target: { value: 'Calle 5' },
    });
    fireEvent.change(screen.getByLabelText('Ciudad'), { target: { value: 'Valencia' } });
    fireEvent.change(screen.getByLabelText('Estado/Provincia'), { target: { value: 'Carabobo' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar dirección' }));
    expect(await screen.findByText(/Dirección inválida\./)).toBeInTheDocument();
  });
});
