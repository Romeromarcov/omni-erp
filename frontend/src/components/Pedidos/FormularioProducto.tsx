import React, { useState } from 'react';
import { Button } from '../Button';
import type { Producto } from '../../services/productosService';
import type { PedidoDetalleForm } from './TablaProductos';

interface FormularioProductoProps {
  productos: Producto[];
  detalleForm: PedidoDetalleForm;
  onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => void;
  onAdd: (e: React.FormEvent) => void;
  onSelectProducto?: (prod: Producto) => void;
}


const FormularioProducto: React.FC<FormularioProductoProps> = ({ productos, detalleForm, onChange, onAdd, onSelectProducto }) => {
  const [busquedaSku, setBusquedaSku] = useState('');
  const [showSugerenciasSku, setShowSugerenciasSku] = useState(false);
  const [busquedaNombre, setBusquedaNombre] = useState('');
  const [showSugerenciasNombre, setShowSugerenciasNombre] = useState(false);
  const sugerenciasSku = busquedaSku.length > 0
    ? productos.filter(p => (p.sku || '').toLowerCase().includes(busquedaSku.trim().toLowerCase()))
    : [];
  const sugerenciasNombre = busquedaNombre.length > 0
    ? productos.filter(p => p.nombre_producto.toLowerCase().includes(busquedaNombre.trim().toLowerCase()))
    : [];

  // Sincroniza los inputs con el estado global detalleForm
  React.useEffect(() => {
    setBusquedaSku(detalleForm.sku || '');
    setBusquedaNombre(detalleForm.producto || '');
  }, [detalleForm.sku, detalleForm.producto]);

  const handleInputChangeSku = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setBusquedaSku(value);
    setShowSugerenciasSku(true);
    onChange({
      ...e,
      target: { ...e.target, value }
    });
  };

  const handleInputChangeNombre = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setBusquedaNombre(value);
    setShowSugerenciasNombre(true);
    onChange({
      ...e,
      target: { ...e.target, value }
    });
  };

  const handleSelectProducto = (prod: Producto) => {
    setShowSugerenciasSku(false);
    setShowSugerenciasNombre(false);
    if (onSelectProducto) onSelectProducto(prod);
    // Actualiza el id_producto, precio y sku en el estado del formulario
    onChange({
      target: { name: 'id_producto', value: prod.id_producto }
    } as React.ChangeEvent<HTMLInputElement>);
    onChange({
      target: { name: 'precio_unitario', value: prod.precio_venta_sugerido ?? '' }
    } as React.ChangeEvent<HTMLInputElement>);
    onChange({
      target: { name: 'sku', value: prod.sku ?? '' }
    } as React.ChangeEvent<HTMLInputElement>);
    onChange({
      target: { name: 'producto', value: prod.nombre_producto }
    } as React.ChangeEvent<HTMLInputElement>);
  };

  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, position: 'relative' }}>
      {/* SKU autocomplete */}
      <div style={{ minWidth: 120, position: 'relative' }}>
        <input
          name="sku"
          type="text"
          value={detalleForm.sku || ''}
          onChange={handleInputChangeSku}
          placeholder="Buscar SKU..."
          autoComplete="off"
          style={{ width: '100%' }}
          onFocus={() => setShowSugerenciasSku(true)}
          onBlur={() => setTimeout(() => setShowSugerenciasSku(false), 150)}
        />
        {showSugerenciasSku && sugerenciasSku.length > 0 && (
          <ul style={{ position: 'absolute', top: '100%', left: 0, right: 0, background: '#fff', border: '1px solid #ccc', zIndex: 10, maxHeight: 180, overflowY: 'auto', margin: 0, padding: 0, listStyle: 'none' }}>
            {sugerenciasSku.map(prod => (
              <li key={prod.id_producto} style={{ padding: 6, cursor: 'pointer' }} onMouseDown={() => handleSelectProducto(prod)}>
                {prod.sku} - {prod.nombre_producto}
              </li>
            ))}
          </ul>
        )}
      </div>
      {/* Nombre autocomplete */}
      <div style={{ minWidth: 160, position: 'relative' }}>
        <input
          name="producto"
          type="text"
          value={detalleForm.producto || ''}
          onChange={handleInputChangeNombre}
          placeholder="Buscar producto..."
          autoComplete="off"
          style={{ width: '100%' }}
          onFocus={() => setShowSugerenciasNombre(true)}
          onBlur={() => setTimeout(() => setShowSugerenciasNombre(false), 150)}
        />
        {showSugerenciasNombre && sugerenciasNombre.length > 0 && (
          <ul style={{ position: 'absolute', top: '100%', left: 0, right: 0, background: '#fff', border: '1px solid #ccc', zIndex: 10, maxHeight: 180, overflowY: 'auto', margin: 0, padding: 0, listStyle: 'none' }}>
            {sugerenciasNombre.map(prod => (
              <li key={prod.id_producto} style={{ padding: 6, cursor: 'pointer' }} onMouseDown={() => handleSelectProducto(prod)}>
                {prod.nombre_producto} {prod.sku ? `(${prod.sku})` : ''}
              </li>
            ))}
          </ul>
        )}
      </div>
  <input name="cantidad" type="number" min="0.01" step="0.01" value={detalleForm.cantidad} onChange={onChange} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); onAdd(e as any); } }} placeholder="Cantidad" style={{ width: 80 }} />
  <input name="precio_unitario" type="number" min="0.01" step="0.01" value={detalleForm.precio_unitario} onChange={onChange} placeholder="Precio" style={{ width: 80 }} />
  <input name="descuento_porcentaje" type="number" min="0" max="100" step="0.01" value={detalleForm.descuento_porcentaje || ''} onChange={onChange} placeholder="% Desc." style={{ width: 80 }} />
  <textarea name="comentarios" value={detalleForm.comentarios || ''} onChange={onChange} placeholder="Comentarios (opcional)" style={{ width: 180, minHeight: 40, resize: 'vertical' }} maxLength={500} />
  <Button type="button" variant="primary" onClick={onAdd}>Agregar</Button>
    </div>
  );
};

export default FormularioProducto;
