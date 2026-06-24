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
import ProveedoresPage from '../pages/Proveedores/ProveedoresPage';

const proveedorApi = {
  id_proveedor: 'prov-1',
  id_empresa: 'e1',
  razon_social: 'ACME Suministros C.A.',
  nombre_comercial: 'ACME',
  rif: 'J-12345678',
  direccion: null,
  telefono: '04141234567',
  email: 'ventas@acme.com',
  referencia_externa: null,
  activo: true,
};

const monedasApi = [{ id_moneda: 'm1', nombre: 'Bolívar', codigo_iso: 'VES' }];

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ProveedoresPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockGet(opts: { contactos?: unknown[]; cuentas?: unknown[] } = {}) {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/proveedores/contactos-proveedor')) {
      return Promise.resolve(opts.contactos ?? []);
    }
    if (url.startsWith('/proveedores/cuentas-bancarias-proveedor')) {
      return Promise.resolve(opts.cuentas ?? []);
    }
    if (url.startsWith('/finanzas/monedas')) return Promise.resolve(monedasApi);
    if (url.startsWith('/proveedores/proveedores')) return Promise.resolve([proveedorApi]);
    return Promise.resolve([]);
  });
}

describe('ProveedoresPage — lista y formulario', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet();
  });

  it('lista los proveedores con su RIF y email', async () => {
    renderPage();
    expect(await screen.findByText('ACME Suministros C.A.')).toBeInTheDocument();
    expect(screen.getByText('J-12345678')).toBeInTheDocument();
    expect(screen.getByText('ventas@acme.com')).toBeInTheDocument();
  });

  it('filtra por búsqueda (arma el querystring con search)', async () => {
    renderPage();
    await screen.findByText('ACME Suministros C.A.');
    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'acme' } });
    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        expect.stringContaining('/proveedores/proveedores/?empresa=e1&search=acme'),
      ),
    );
  });

  it('valida razón social y RIF requeridos al crear', async () => {
    renderPage();
    await screen.findByText('ACME Suministros C.A.');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo proveedor' }));
    expect(await screen.findByText('Nuevo proveedor', { selector: 'h2' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/Complete la razón social y el RIF/)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un proveedor capturando todos los campos opcionales', async () => {
    vi.mocked(post).mockResolvedValue({ id_proveedor: 'prov-2' });
    renderPage();
    await screen.findByText('ACME Suministros C.A.');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo proveedor' }));
    fireEvent.change(await screen.findByLabelText(/Razón social/), {
      target: { value: 'Proveedor Nuevo' },
    });
    fireEvent.change(screen.getByLabelText(/RIF/), { target: { value: 'V-99999999' } });
    fireEvent.change(screen.getByLabelText(/Nombre comercial/), { target: { value: 'PN' } });
    fireEvent.change(screen.getByLabelText(/Teléfono/), { target: { value: '02125551212' } });
    fireEvent.change(screen.getByLabelText(/Email/), { target: { value: 'info@pn.com' } });
    fireEvent.change(screen.getByLabelText(/Dirección/), { target: { value: 'Calle 1' } });
    fireEvent.change(screen.getByLabelText(/Referencia externa/), { target: { value: 'EXT-9' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/proveedores/proveedores/',
        expect.objectContaining({
          id_empresa: 'e1',
          razon_social: 'Proveedor Nuevo',
          rif: 'V-99999999',
          nombre_comercial: 'PN',
          telefono: '02125551212',
          email: 'info@pn.com',
          direccion: 'Calle 1',
          referencia_externa: 'EXT-9',
        }),
      ),
    );
  });

  it('editar un proveedor envía el payload por id', async () => {
    vi.mocked(patch).mockResolvedValue({ id_proveedor: 'prov-1' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Editar' }));
    const razon = await screen.findByLabelText(/Razón social/);
    fireEvent.change(razon, { target: { value: 'ACME Editado' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/proveedores/proveedores/prov-1/',
        expect.objectContaining({ razon_social: 'ACME Editado', rif: 'J-12345678' }),
      ),
    );
  });

  it('eliminar un proveedor pide confirmación y llama al servicio', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(del).mockResolvedValue(undefined);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/proveedores/proveedores/prov-1/'));
    confirmSpy.mockRestore();
  });

  it('no elimina si el usuario cancela la confirmación', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar' }));
    expect(del).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('cierra el diálogo con Cancelar', async () => {
    renderPage();
    await screen.findByText('ACME Suministros C.A.');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo proveedor' }));
    await screen.findByText('Nuevo proveedor', { selector: 'h2' });
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    await waitFor(() =>
      expect(screen.queryByText('Nuevo proveedor', { selector: 'h2' })).not.toBeInTheDocument(),
    );
  });

  it('muestra error al fallar el guardado de un proveedor (mensajeDeError)', async () => {
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ rif: ['RIF inválido.'] })));
    renderPage();
    await screen.findByText('ACME Suministros C.A.');
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo proveedor' }));
    fireEvent.change(await screen.findByLabelText(/Razón social/), {
      target: { value: 'Proveedor X' },
    });
    fireEvent.change(screen.getByLabelText(/RIF/), { target: { value: 'X-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }));
    expect(await screen.findByText(/rif: RIF inválido\./)).toBeInTheDocument();
  });
});

// ── Drawer de detalle ─────────────────────────────────────────────────────────

async function abrirDetalle() {
  renderPage();
  fireEvent.click(await screen.findByRole('button', { name: 'Detalle' }));
  await screen.findByText('Contactos');
}

describe('ProveedoresPage — drawer de detalle', () => {
  beforeEach(() => vi.clearAllMocks());

  it('abre el detalle mostrando las secciones', async () => {
    mockGet();
    await abrirDetalle();
    expect(screen.getByText('Contactos')).toBeInTheDocument();
    expect(screen.getByText('Cuentas bancarias')).toBeInTheDocument();
  });

  it('cierra el drawer con el botón de cerrar', async () => {
    mockGet();
    await abrirDetalle();
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar detalle' }));
    await waitFor(() => expect(screen.queryByText('Contactos')).not.toBeInTheDocument());
  });
});

describe('ProveedoresPage — CRUD inline de Contactos', () => {
  beforeEach(() => vi.clearAllMocks());

  const contactoApi = {
    id_contacto: 'k1',
    id_proveedor: 'prov-1',
    nombre: 'Ana',
    apellido: 'Pérez',
    cargo: 'Ventas',
    telefono: '04140000000',
    email: 'ana@acme.com',
    es_contacto_principal: true,
    area_responsabilidad: 'Comercial',
    observaciones: null,
  };

  it('valida los campos requeridos del contacto', async () => {
    mockGet();
    await abrirDetalle();
    fireEvent.click(screen.getByRole('button', { name: 'Agregar contacto' }));
    expect(
      await screen.findByText(/Complete nombre y apellido del contacto/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea un contacto con el payload correcto (incluye opcionales)', async () => {
    mockGet();
    vi.mocked(post).mockResolvedValue({ id_contacto: 'k-new' });
    await abrirDetalle();
    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Luis' } });
    fireEvent.change(screen.getByLabelText('Apellido'), { target: { value: 'Gómez' } });
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'luis@acme.com' } });
    fireEvent.change(screen.getByLabelText('Cargo'), { target: { value: 'Gerente' } });
    fireEvent.change(screen.getByLabelText('Teléfono'), { target: { value: '04149998877' } });
    fireEvent.change(screen.getByLabelText(/Área de responsabilidad/), {
      target: { value: 'Compras' },
    });
    fireEvent.click(screen.getByLabelText('Contacto principal'));
    fireEvent.click(screen.getByRole('button', { name: 'Agregar contacto' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/proveedores/contactos-proveedor/',
        expect.objectContaining({
          id_proveedor: 'prov-1',
          nombre: 'Luis',
          apellido: 'Gómez',
          email: 'luis@acme.com',
          cargo: 'Gerente',
          telefono: '04149998877',
          area_responsabilidad: 'Compras',
          es_contacto_principal: true,
        }),
      ),
    );
  });

  it('edita un contacto existente (precarga y hace PATCH)', async () => {
    mockGet({ contactos: [contactoApi] });
    vi.mocked(patch).mockResolvedValue({ id_contacto: 'k1' });
    await abrirDetalle();
    expect(await screen.findByText(/Ana Pérez/)).toBeInTheDocument();
    const editButtons = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editButtons[editButtons.length - 1]);
    const nombre = screen.getByLabelText('Nombre') as HTMLInputElement;
    await waitFor(() => expect(nombre.value).toBe('Ana'));
    fireEvent.change(nombre, { target: { value: 'Ana María' } });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar contacto' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/proveedores/contactos-proveedor/k1/',
        expect.objectContaining({ nombre: 'Ana María' }),
      ),
    );
  });

  it('elimina un contacto', async () => {
    mockGet({ contactos: [contactoApi] });
    vi.mocked(del).mockResolvedValue(undefined);
    await abrirDetalle();
    await screen.findByText(/Ana Pérez/);
    const delButtons = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(delButtons[delButtons.length - 1]);
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/proveedores/contactos-proveedor/k1/'),
    );
  });

  it('entra en edición y cancela (reset del formulario inline)', async () => {
    mockGet({ contactos: [contactoApi] });
    await abrirDetalle();
    await screen.findByText(/Ana Pérez/);
    const editButtons = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editButtons[editButtons.length - 1]);
    const cancelar = await screen.findByRole('button', { name: 'Cancelar' });
    fireEvent.click(cancelar);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Agregar contacto' })).toBeInTheDocument(),
    );
  });

  it('muestra error al fallar la creación de un contacto', async () => {
    mockGet();
    vi.mocked(post).mockRejectedValue(new Error(JSON.stringify({ detail: 'Email duplicado.' })));
    await abrirDetalle();
    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Luis' } });
    fireEvent.change(screen.getByLabelText('Apellido'), { target: { value: 'Gómez' } });
    fireEvent.click(screen.getByRole('button', { name: 'Agregar contacto' }));
    expect(await screen.findByText(/Email duplicado\./)).toBeInTheDocument();
  });
});

describe('ProveedoresPage — CRUD inline de Cuentas bancarias', () => {
  beforeEach(() => vi.clearAllMocks());

  const cuentaApi = {
    id_cuenta_bancaria: 'b1',
    id_proveedor: 'prov-1',
    nombre_banco: 'Banco X',
    numero_cuenta: '0102-0000-0000000000',
    tipo_cuenta: 'CORRIENTE',
    moneda: 'm1',
    titular_cuenta: 'ACME C.A.',
    identificacion_titular: 'J-12345678',
    es_cuenta_principal: true,
    observaciones: null,
  };

  it('valida banco, número de cuenta y moneda requeridos', async () => {
    mockGet();
    await abrirDetalle();
    fireEvent.click(screen.getByRole('button', { name: 'Agregar cuenta' }));
    expect(
      await screen.findByText(/Complete banco, número de cuenta y moneda/),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('crea una cuenta con el payload correcto (selecciona tipo y moneda)', async () => {
    mockGet();
    vi.mocked(post).mockResolvedValue({ id_cuenta_bancaria: 'b-new' });
    await abrirDetalle();
    fireEvent.change(screen.getByLabelText('Banco'), { target: { value: 'Banco Z' } });
    fireEvent.change(screen.getByLabelText('Número de cuenta'), {
      target: { value: '0105-1111' },
    });
    // Seleccionar moneda (revela la opción del catálogo).
    fireEvent.mouseDown(screen.getByLabelText('Moneda'));
    fireEvent.click(await screen.findByRole('option', { name: /VES — Bolívar/ }));
    // Cambiar tipo de cuenta.
    fireEvent.mouseDown(screen.getByLabelText(/Tipo de cuenta/));
    fireEvent.click(await screen.findByRole('option', { name: 'Ahorro' }));
    fireEvent.change(screen.getByLabelText('Titular'), { target: { value: 'ACME' } });
    fireEvent.change(screen.getByLabelText(/Identificación titular/), {
      target: { value: 'J-1' },
    });
    fireEvent.click(screen.getByLabelText('Cuenta principal'));
    fireEvent.click(screen.getByRole('button', { name: 'Agregar cuenta' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/proveedores/cuentas-bancarias-proveedor/',
        expect.objectContaining({
          id_proveedor: 'prov-1',
          nombre_banco: 'Banco Z',
          numero_cuenta: '0105-1111',
          tipo_cuenta: 'AHORRO',
          moneda: 'm1',
          titular_cuenta: 'ACME',
          identificacion_titular: 'J-1',
          es_cuenta_principal: true,
        }),
      ),
    );
  });

  it('edita una cuenta existente (precarga y hace PATCH)', async () => {
    mockGet({ cuentas: [cuentaApi] });
    vi.mocked(patch).mockResolvedValue({ id_cuenta_bancaria: 'b1' });
    await abrirDetalle();
    expect(await screen.findByText(/Banco X/)).toBeInTheDocument();
    const editButtons = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editButtons[editButtons.length - 1]);
    const banco = screen.getByLabelText('Banco') as HTMLInputElement;
    await waitFor(() => expect(banco.value).toBe('Banco X'));
    fireEvent.change(banco, { target: { value: 'Banco Mercantil' } });
    fireEvent.click(screen.getByRole('button', { name: 'Actualizar cuenta' }));

    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/proveedores/cuentas-bancarias-proveedor/b1/',
        expect.objectContaining({ nombre_banco: 'Banco Mercantil' }),
      ),
    );
  });

  it('elimina una cuenta', async () => {
    mockGet({ cuentas: [cuentaApi] });
    vi.mocked(del).mockResolvedValue(undefined);
    await abrirDetalle();
    await screen.findByText(/Banco X/);
    const delButtons = screen.getAllByRole('button', { name: 'Eliminar' });
    fireEvent.click(delButtons[delButtons.length - 1]);
    await waitFor(() =>
      expect(del).toHaveBeenCalledWith('/proveedores/cuentas-bancarias-proveedor/b1/'),
    );
  });

  it('entra en edición y cancela (reset del formulario inline)', async () => {
    mockGet({ cuentas: [cuentaApi] });
    await abrirDetalle();
    await screen.findByText(/Banco X/);
    const editButtons = screen.getAllByRole('button', { name: 'Editar' });
    fireEvent.click(editButtons[editButtons.length - 1]);
    const cancelar = await screen.findByRole('button', { name: 'Cancelar' });
    fireEvent.click(cancelar);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Agregar cuenta' })).toBeInTheDocument(),
    );
  });

  it('muestra error al fallar la creación de una cuenta', async () => {
    mockGet();
    vi.mocked(post).mockRejectedValue(
      new Error(JSON.stringify({ detail: 'Cuenta duplicada.' })),
    );
    await abrirDetalle();
    fireEvent.change(screen.getByLabelText('Banco'), { target: { value: 'Banco Z' } });
    fireEvent.change(screen.getByLabelText('Número de cuenta'), {
      target: { value: '0105-1111' },
    });
    fireEvent.mouseDown(screen.getByLabelText('Moneda'));
    fireEvent.click(await screen.findByRole('option', { name: /VES — Bolívar/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Agregar cuenta' }));
    expect(await screen.findByText(/Cuenta duplicada\./)).toBeInTheDocument();
  });
});
