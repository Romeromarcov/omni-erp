/**
 * Tests exhaustivos de FormularioCliente.
 *
 * Formulario inline de datos del cliente para el POS. Componente de presentación
 * controlado: se prueban render condicional, normalización del RIF y delegación
 * de callbacks (onChange/onKeyDown/onBlur/onBuscar) con los args correctos.
 */
import type React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import FormularioCliente from '../FormularioCliente';

type Mock = ReturnType<typeof vi.fn>;
type CProps = React.ComponentProps<typeof FormularioCliente>;

type ClienteManual = {
  razon_social: string;
  rif: string;
  telefono: string;
  direccion?: string;
  correo?: string;
  codigo_cliente?: string;
};

const baseCliente: ClienteManual = {
  razon_social: 'ACME C.A.',
  rif: 'J-12345678',
  telefono: '04141234567',
  direccion: 'Av. Principal',
  correo: 'acme@example.com',
};

function renderForm(overrides: Partial<{
  clienteManual: ClienteManual;
  onChange: Mock;
  onKeyDown: Mock;
  onBlur: Mock;
  onBuscar: Mock;
}> = {}) {
  const onChange = overrides.onChange ?? vi.fn();
  const onKeyDown = overrides.onKeyDown ?? vi.fn();
  const onBlur = overrides.onBlur ?? vi.fn();
  const onBuscar = overrides.onBuscar ?? vi.fn();
  const utils = render(
    <FormularioCliente
      clienteManual={overrides.clienteManual ?? baseCliente}
      onChange={onChange as unknown as CProps['onChange']}
      onKeyDown={onKeyDown as unknown as CProps['onKeyDown']}
      onBlur={onBlur as unknown as CProps['onBlur']}
      onBuscar={onBuscar as unknown as CProps['onBuscar']}
    />,
  );
  return { ...utils, onChange, onKeyDown, onBlur, onBuscar };
}

describe('FormularioCliente', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renderiza los campos y el botón de búsqueda', () => {
    renderForm();
    expect(screen.getByLabelText(/Razón Social/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Teléfono/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Dirección/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Correo electrónico/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Número RIF/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Buscar cliente existente' })).toBeInTheDocument();
  });

  it('refleja los valores del clienteManual', () => {
    renderForm();
    expect(screen.getByLabelText(/Razón Social/)).toHaveValue('ACME C.A.');
    expect(screen.getByLabelText(/Teléfono/)).toHaveValue('04141234567');
    expect(screen.getByLabelText(/Número RIF/)).toHaveValue('12345678');
  });

  it('descompone el RIF: prefijo en el Select y numero en el TextField', () => {
    renderForm({ clienteManual: { ...baseCliente, rif: 'V-9999' } });
    expect(screen.getByLabelText(/Número RIF/)).toHaveValue('9999');
    // El prefijo V se muestra en el combobox
    expect(screen.getByRole('combobox')).toHaveTextContent('V');
  });

  it('RIF vacío no rompe el split (prefijo y numero vacíos)', () => {
    renderForm({ clienteManual: { ...baseCliente, rif: '' } });
    expect(screen.getByLabelText(/Número RIF/)).toHaveValue('');
  });

  it('NO muestra Código de Cliente cuando no está presente', () => {
    renderForm();
    expect(screen.queryByLabelText(/Código de Cliente/)).not.toBeInTheDocument();
  });

  it('muestra Código de Cliente (readOnly) cuando viene en el cliente', () => {
    renderForm({ clienteManual: { ...baseCliente, codigo_cliente: 'CLI-007' } });
    const campo = screen.getByLabelText(/Código de Cliente/);
    expect(campo).toHaveValue('CLI-007');
    expect(campo).toHaveAttribute('readonly');
  });

  it('cambiar Razón Social delega en onChange', () => {
    const { onChange } = renderForm();
    fireEvent.change(screen.getByLabelText(/Razón Social/), { target: { value: 'Nueva SA' } });
    expect(onChange).toHaveBeenCalled();
  });

  it('Razón Social dispara onKeyDown y onBlur', () => {
    const { onKeyDown, onBlur } = renderForm();
    const campo = screen.getByLabelText(/Razón Social/);
    fireEvent.keyDown(campo, { key: 'Enter' });
    fireEvent.blur(campo);
    expect(onKeyDown).toHaveBeenCalledTimes(1);
    expect(onBlur).toHaveBeenCalledTimes(1);
  });

  it('Número RIF normaliza eliminando no-dígitos antes de onChange', () => {
    const { onChange } = renderForm();
    fireEvent.change(screen.getByLabelText(/Número RIF/), { target: { value: '12a3b4' } });
    expect(onChange).toHaveBeenCalledTimes(1);
    const evt = onChange.mock.calls[0][0];
    expect(evt.target.name).toBe('rif_numero');
    expect(evt.target.value).toBe('1234');
  });

  it('Número RIF dispara onKeyDown y onBlur', () => {
    const { onKeyDown, onBlur } = renderForm();
    const campo = screen.getByLabelText(/Número RIF/);
    fireEvent.keyDown(campo, { key: 'Tab' });
    fireEvent.blur(campo);
    expect(onKeyDown).toHaveBeenCalledTimes(1);
    expect(onBlur).toHaveBeenCalledTimes(1);
  });

  it('Teléfono, Dirección y Correo delegan en onChange', () => {
    const { onChange } = renderForm();
    fireEvent.change(screen.getByLabelText(/Teléfono/), { target: { value: '0212' } });
    fireEvent.change(screen.getByLabelText(/Dirección/), { target: { value: 'Calle 1' } });
    fireEvent.change(screen.getByLabelText(/Correo electrónico/), { target: { value: 'a@b.com' } });
    expect(onChange).toHaveBeenCalledTimes(3);
  });

  it('cambiar el prefijo del RIF emite onChange con name=rif_prefijo', () => {
    const { onChange } = renderForm({ clienteManual: { ...baseCliente, rif: '-1' } });
    // Abrir el Select y elegir una opción
    fireEvent.mouseDown(screen.getByRole('combobox'));
    fireEvent.click(screen.getByRole('option', { name: 'J — Empresa' }));
    expect(onChange).toHaveBeenCalled();
    const evt = onChange.mock.calls[0][0];
    expect(evt.target.name).toBe('rif_prefijo');
    expect(evt.target.value).toBe('J');
  });

  it('el botón Buscar invoca onBuscar', () => {
    const { onBuscar } = renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'Buscar cliente existente' }));
    expect(onBuscar).toHaveBeenCalledTimes(1);
  });

  it('campos opcionales (dirección/correo) con undefined usan string vacío', () => {
    renderForm({ clienteManual: { razon_social: 'X', rif: 'V-1', telefono: '1' } });
    expect(screen.getByLabelText(/Dirección/)).toHaveValue('');
    expect(screen.getByLabelText(/Correo electrónico/)).toHaveValue('');
  });
});
