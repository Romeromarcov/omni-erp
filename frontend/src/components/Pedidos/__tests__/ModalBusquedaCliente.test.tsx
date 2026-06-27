/**
 * Tests exhaustivos de ModalBusquedaCliente.
 *
 * Modal de búsqueda de cliente. A diferencia del de producto, consulta el
 * backend (buscarClientes) de forma asíncrona conforme se teclea. Se mockea
 * el servicio y se verifican: query con idEmpresa, manejo de respuesta no-array,
 * limpieza al vaciar el input y selección/cierre.
 */
import type React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { Cliente } from '../../../services/clientesService';

type Mock = ReturnType<typeof vi.fn>;

const buscarClientesMock = vi.fn();
vi.mock('../../../services/clientesService', () => ({
  buscarClientes: (...a: unknown[]) => buscarClientesMock(...a),
}));

import ModalBusquedaCliente from '../ModalBusquedaCliente';

type CProps = React.ComponentProps<typeof ModalBusquedaCliente>;

const CLIENTES: Cliente[] = [
  { id_cliente: 'c1', razon_social: 'ACME C.A.', rif: 'J-111', telefono: '0212' },
  { id_cliente: 'c2', razon_social: 'Globex SA', rif: 'J-222', telefono: '0414' },
];

function renderModal(overrides: Partial<{
  open: boolean;
  idEmpresa: string;
  onSelect: Mock;
  onClose: Mock;
}> = {}) {
  const onSelect = overrides.onSelect ?? vi.fn();
  const onClose = overrides.onClose ?? vi.fn();
  const utils = render(
    <ModalBusquedaCliente
      open={overrides.open ?? true}
      idEmpresa={overrides.idEmpresa ?? 'emp-1'}
      onSelect={onSelect as unknown as CProps['onSelect']}
      onClose={onClose as unknown as CProps['onClose']}
    />,
  );
  return { ...utils, onSelect, onClose };
}

describe('ModalBusquedaCliente', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    buscarClientesMock.mockResolvedValue(CLIENTES);
  });

  it('no renderiza contenido cuando open=false', () => {
    renderModal({ open: false });
    expect(screen.queryByText('Buscar cliente existente')).not.toBeInTheDocument();
  });

  it('renderiza el título e input vacío sin resultados iniciales', () => {
    renderModal();
    expect(screen.getByText('Buscar cliente existente')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Buscar por nombre, RIF...')).toHaveValue('');
  });

  it('teclear consulta buscarClientes con el query y el idEmpresa', async () => {
    renderModal({ idEmpresa: 'emp-99' });
    fireEvent.change(screen.getByPlaceholderText('Buscar por nombre, RIF...'), { target: { value: 'acme' } });
    await waitFor(() => expect(buscarClientesMock).toHaveBeenCalledWith('acme', 'emp-99'));
  });

  it('muestra los resultados devueltos con RIF y teléfono', async () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText('Buscar por nombre, RIF...'), { target: { value: 'a' } });
    await waitFor(() => expect(screen.getByText('ACME C.A.')).toBeInTheDocument());
    expect(screen.getByText('Globex SA')).toBeInTheDocument();
    expect(screen.getByText(/RIF: J-111 \| Tel: 0212/)).toBeInTheDocument();
  });

  it('input vacío NO consulta y limpia los resultados', async () => {
    renderModal();
    const input = screen.getByPlaceholderText('Buscar por nombre, RIF...');
    fireEvent.change(input, { target: { value: 'acme' } });
    await waitFor(() => expect(screen.getByText('ACME C.A.')).toBeInTheDocument());

    buscarClientesMock.mockClear();
    fireEvent.change(input, { target: { value: '' } });
    await waitFor(() => expect(screen.queryByText('ACME C.A.')).not.toBeInTheDocument());
    expect(buscarClientesMock).not.toHaveBeenCalled();
  });

  it('input solo con espacios no consulta (trim vacío)', async () => {
    renderModal();
    fireEvent.change(screen.getByPlaceholderText('Buscar por nombre, RIF...'), { target: { value: '   ' } });
    // dar tiempo a un posible await
    await Promise.resolve();
    expect(buscarClientesMock).not.toHaveBeenCalled();
  });

  it('respuesta no-array se trata como lista vacía (sin crash)', async () => {
    buscarClientesMock.mockResolvedValue({ results: [] } as unknown as Cliente[]);
    renderModal();
    fireEvent.change(screen.getByPlaceholderText('Buscar por nombre, RIF...'), { target: { value: 'x' } });
    await waitFor(() => expect(buscarClientesMock).toHaveBeenCalled());
    expect(screen.getByText('No se encontraron clientes.')).toBeInTheDocument();
  });

  it('el botón Seleccionar invoca onSelect con el cliente y cierra', async () => {
    const { onSelect, onClose } = renderModal();
    fireEvent.change(screen.getByPlaceholderText('Buscar por nombre, RIF...'), { target: { value: 'a' } });
    await waitFor(() => expect(screen.getByText('ACME C.A.')).toBeInTheDocument());
    fireEvent.click(screen.getAllByRole('button', { name: 'Seleccionar' })[0]);
    expect(onSelect).toHaveBeenCalledWith(CLIENTES[0]);
    expect(onClose).toHaveBeenCalled();
  });

  it('el botón Cerrar invoca onClose', () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
