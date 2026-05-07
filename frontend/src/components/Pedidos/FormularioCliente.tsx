import React from 'react';

interface FormularioClienteProps {
  clienteManual: { razon_social: string; rif: string; telefono: string; direccion?: string; correo?: string; codigo_cliente?: string };
  onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  onBlur: () => void;
  onBuscar: () => void;
}

const FormularioCliente: React.FC<FormularioClienteProps> = ({ clienteManual, onChange, onKeyDown, onBlur, onBuscar }) => (
  <div style={{ border: '1px solid #cfd8dc', borderRadius: 8, padding: 12, marginBottom: 12 }}>
    <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
      <h4 style={{ margin: 0, marginRight: 12 }}>Datos del cliente</h4>
      <button type="button" onClick={onBuscar} style={{ marginLeft: 0 }}>
        Buscar cliente existente
      </button>
    </div>
    <label>Razón Social
      <input name="razon_social" value={clienteManual.razon_social} onChange={onChange} onKeyDown={onKeyDown} onBlur={onBlur} required />
    </label>
    {clienteManual.codigo_cliente && (
      <label>Código de Cliente
        <input name="codigo_cliente" value={clienteManual.codigo_cliente} readOnly />
      </label>
    )}
    <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      RIF
      <div style={{ display: 'flex', gap: 4 }}>
        <select name="rif_prefijo" value={clienteManual.rif.split('-')[0] || ''} onChange={onChange} required>
          <option value="">Seleccione</option>
          <option value="V">V (Persona)</option>
          <option value="J">J (Empresa)</option>
          <option value="E">E (Extranjero)</option>
          <option value="G">G (Gobierno)</option>
          <option value="P">P (Pasaporte)</option>
        </select>
        <input
          name="rif_numero"
          value={clienteManual.rif.split('-')[1] || ''}
          onChange={(e) => {
            const value = e.target.value.replace(/\D/g, ''); // Solo números
            onChange({ ...e, target: { ...e.target, value, name: 'rif_numero' } });
          }}
          onKeyDown={onKeyDown}
          onBlur={onBlur}
          placeholder="Número"
          required
        />
      </div>
    </label>
    <label>Teléfono
      <input name="telefono" value={clienteManual.telefono} onChange={onChange} required />
    </label>
    <label>Dirección (opcional)
      <input name="direccion" value={clienteManual.direccion || ''} onChange={onChange} />
    </label>
    <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      Correo electrónico (opcional)
      <input name="correo" value={clienteManual.correo || ''} onChange={onChange} />
    </label>
  </div>
);

export default FormularioCliente;
