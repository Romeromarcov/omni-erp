import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import PageLayout from '../../components/PageLayout';
import {
  productoInventarioService,
  stockActualService,
  movimientoService,
} from '../../services/inventarioService';

type TipoAjuste = 'ENTRADA' | 'SALIDA';

interface FormState {
  id_producto: string;
  id_almacen: string;
  tipo_ajuste: TipoAjuste;
  cantidad: string;
  costo_unitario: string;
  observaciones: string;
  fecha_hora: string;
}

function nowISOLocal(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

const AjusteInventarioPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();

  const [form, setForm] = useState<FormState>({
    id_producto: searchParams.get('producto') ?? '',
    id_almacen: searchParams.get('almacen') ?? '',
    tipo_ajuste: 'ENTRADA',
    cantidad: '',
    costo_unitario: '',
    observaciones: '',
    fecha_hora: nowISOLocal(),
  });
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const { data: productos = [] } = useQuery({
    queryKey: ['productos-inventario'],
    queryFn: () => productoInventarioService.getAll(),
  });

  const { data: stockList = [] } = useQuery({
    queryKey: ['stock-actual-all'],
    queryFn: () => stockActualService.getAll(),
  });

  // Extract unique warehouses from stock data
  const almacenes = [
    ...new Map(
      stockList.map((s) => [s.id_almacen, s.almacen_nombre ?? s.id_almacen])
    ).entries(),
  ];

  // Current stock for the selected product+warehouse
  const stockActual = stockList.find(
    (s) => s.id_producto === form.id_producto && s.id_almacen === form.id_almacen
  );

  // Get empresa from the first stock entry (for the payload)
  const empresaId = stockList[0]?.id_empresa ?? '';

  const ajusteMutation = useMutation({
    mutationFn: () => {
      const cantidad = parseFloat(form.cantidad);
      if (isNaN(cantidad) || cantidad <= 0) throw new Error('La cantidad debe ser mayor a 0.');
      if (!form.id_producto) throw new Error('Seleccione un producto.');
      if (!form.id_almacen) throw new Error('Seleccione un almacén.');

      return movimientoService.registrarAjuste({
        id_empresa: empresaId,
        id_producto: form.id_producto,
        tipo_movimiento: 'AJUSTE',
        cantidad: form.tipo_ajuste === 'SALIDA' ? -cantidad : cantidad,
        fecha_hora_movimiento: new Date(form.fecha_hora).toISOString(),
        observaciones: form.observaciones || undefined,
        costo_unitario_movimiento: form.costo_unitario ? parseFloat(form.costo_unitario) : undefined,
        ...(form.tipo_ajuste === 'ENTRADA'
          ? { id_almacen_destino: form.id_almacen }
          : { id_almacen_origen: form.id_almacen }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stock-actual-all'] });
      queryClient.invalidateQueries({ queryKey: ['kardex'] });
      setSuccessMsg('Ajuste registrado correctamente.');
      setErrorMsg('');
      setForm((f) => ({
        ...f,
        cantidad: '',
        costo_unitario: '',
        observaciones: '',
        fecha_hora: nowISOLocal(),
      }));
    },
    onError: (err: Error) => {
      setErrorMsg(err.message);
      setSuccessMsg('');
    },
  });

  function handleChange(field: keyof FormState, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
    setSuccessMsg('');
    setErrorMsg('');
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    ajusteMutation.mutate();
  }

  return (
    <PageLayout maxWidth={640}>
      <div style={{ marginBottom: 20 }}>
        <button
          onClick={() => navigate('/inventario/stock')}
          style={{ background: 'none', border: 'none', color: '#1976d2', cursor: 'pointer', fontSize: 14, padding: 0 }}
        >
          ← Volver al stock
        </button>
        <h2 style={{ margin: '8px 0 4px', fontSize: 22, fontWeight: 700 }}>Ajuste Manual de Inventario</h2>
        <p style={{ color: '#6c757d', fontSize: 14, margin: 0 }}>
          Registra una entrada o salida de ajuste con motivo documentado.
        </p>
      </div>

      {successMsg && (
        <div
          style={{
            background: '#e8f5e9',
            border: '1px solid #4caf50',
            borderRadius: 8,
            padding: '12px 16px',
            marginBottom: 20,
            color: '#2e7d32',
            fontWeight: 600,
          }}
        >
          ✅ {successMsg}
        </div>
      )}

      {errorMsg && (
        <div
          style={{
            background: '#ffebee',
            border: '1px solid #f44336',
            borderRadius: 8,
            padding: '12px 16px',
            marginBottom: 20,
            color: '#c62828',
          }}
        >
          ⚠️ {errorMsg}
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        {/* Producto */}
        <div>
          <label style={{ fontSize: 14, fontWeight: 600, display: 'block', marginBottom: 4 }}>
            Producto *
          </label>
          <select
            value={form.id_producto}
            onChange={(e) => handleChange('id_producto', e.target.value)}
            required
            style={{ width: '100%', padding: '9px 12px', border: '1px solid #dee2e6', borderRadius: 8, fontSize: 14 }}
          >
            <option value="">— Seleccionar producto —</option>
            {productos.map((p) => (
              <option key={p.id_producto} value={p.id_producto}>
                {p.nombre_producto} {p.sku ? `(${p.sku})` : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Almacén */}
        <div>
          <label style={{ fontSize: 14, fontWeight: 600, display: 'block', marginBottom: 4 }}>
            Almacén *
          </label>
          <select
            value={form.id_almacen}
            onChange={(e) => handleChange('id_almacen', e.target.value)}
            required
            style={{ width: '100%', padding: '9px 12px', border: '1px solid #dee2e6', borderRadius: 8, fontSize: 14 }}
          >
            <option value="">— Seleccionar almacén —</option>
            {almacenes.map(([id, nombre]) => (
              <option key={id} value={id}>
                {nombre}
              </option>
            ))}
          </select>
        </div>

        {/* Current stock info */}
        {stockActual && (
          <div
            style={{
              background: '#e3f2fd',
              border: '1px solid #90caf9',
              borderRadius: 8,
              padding: '10px 14px',
              fontSize: 14,
            }}
          >
            <span style={{ fontWeight: 600 }}>Stock actual: </span>
            <span style={{ fontWeight: 700, color: '#1565c0' }}>
              {parseFloat(stockActual.cantidad_disponible).toLocaleString()}
            </span>{' '}
            unidades disponibles · Mínimo:{' '}
            {parseFloat(stockActual.cantidad_minima).toLocaleString()}
          </div>
        )}

        {/* Tipo de ajuste */}
        <div>
          <label style={{ fontSize: 14, fontWeight: 600, display: 'block', marginBottom: 8 }}>
            Tipo de ajuste *
          </label>
          <div style={{ display: 'flex', gap: 12 }}>
            {(['ENTRADA', 'SALIDA'] as TipoAjuste[]).map((tipo) => (
              <label
                key={tipo}
                style={{
                  flex: 1,
                  padding: '10px',
                  border: `2px solid ${form.tipo_ajuste === tipo ? (tipo === 'ENTRADA' ? '#4caf50' : '#f44336') : '#dee2e6'}`,
                  borderRadius: 8,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 14,
                  fontWeight: form.tipo_ajuste === tipo ? 700 : 400,
                  background: form.tipo_ajuste === tipo
                    ? tipo === 'ENTRADA' ? '#e8f5e9' : '#ffebee'
                    : '#fff',
                  transition: 'all 0.15s',
                }}
              >
                <input
                  type="radio"
                  name="tipo_ajuste"
                  value={tipo}
                  checked={form.tipo_ajuste === tipo}
                  onChange={() => handleChange('tipo_ajuste', tipo)}
                  style={{ display: 'none' }}
                />
                {tipo === 'ENTRADA' ? '📦 Entrada de inventario' : '📤 Salida de inventario'}
              </label>
            ))}
          </div>
        </div>

        {/* Cantidad */}
        <div>
          <label style={{ fontSize: 14, fontWeight: 600, display: 'block', marginBottom: 4 }}>
            Cantidad *
          </label>
          <input
            type="number"
            min="0.0001"
            step="any"
            value={form.cantidad}
            onChange={(e) => handleChange('cantidad', e.target.value)}
            required
            placeholder="Ej: 50"
            style={{ width: '100%', padding: '9px 12px', border: '1px solid #dee2e6', borderRadius: 8, fontSize: 14, boxSizing: 'border-box' }}
          />
        </div>

        {/* Costo unitario */}
        <div>
          <label style={{ fontSize: 14, fontWeight: 600, display: 'block', marginBottom: 4 }}>
            Costo unitario (opcional)
          </label>
          <input
            type="number"
            min="0"
            step="any"
            value={form.costo_unitario}
            onChange={(e) => handleChange('costo_unitario', e.target.value)}
            placeholder="Ej: 12.50"
            style={{ width: '100%', padding: '9px 12px', border: '1px solid #dee2e6', borderRadius: 8, fontSize: 14, boxSizing: 'border-box' }}
          />
        </div>

        {/* Fecha y hora */}
        <div>
          <label style={{ fontSize: 14, fontWeight: 600, display: 'block', marginBottom: 4 }}>
            Fecha y hora del movimiento *
          </label>
          <input
            type="datetime-local"
            value={form.fecha_hora}
            onChange={(e) => handleChange('fecha_hora', e.target.value)}
            required
            style={{ width: '100%', padding: '9px 12px', border: '1px solid #dee2e6', borderRadius: 8, fontSize: 14, boxSizing: 'border-box' }}
          />
        </div>

        {/* Observaciones */}
        <div>
          <label style={{ fontSize: 14, fontWeight: 600, display: 'block', marginBottom: 4 }}>
            Motivo / Observaciones
          </label>
          <textarea
            value={form.observaciones}
            onChange={(e) => handleChange('observaciones', e.target.value)}
            placeholder="Describe el motivo del ajuste (conteo físico, merma, daño, etc.)"
            rows={3}
            style={{
              width: '100%',
              padding: '9px 12px',
              border: '1px solid #dee2e6',
              borderRadius: 8,
              fontSize: 14,
              resize: 'vertical',
              boxSizing: 'border-box',
            }}
          />
        </div>

        {/* Submit */}
        <div style={{ display: 'flex', gap: 12, paddingTop: 4 }}>
          <button
            type="submit"
            disabled={ajusteMutation.isPending}
            style={{
              flex: 1,
              padding: '12px',
              background: ajusteMutation.isPending ? '#bdbdbd' : '#1976d2',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              cursor: ajusteMutation.isPending ? 'not-allowed' : 'pointer',
              fontWeight: 700,
              fontSize: 15,
            }}
          >
            {ajusteMutation.isPending ? 'Registrando…' : 'Registrar ajuste'}
          </button>
          <button
            type="button"
            onClick={() => navigate('/inventario/stock')}
            style={{
              padding: '12px 24px',
              background: 'transparent',
              border: '1px solid #dee2e6',
              borderRadius: 8,
              cursor: 'pointer',
              fontSize: 15,
            }}
          >
            Cancelar
          </button>
        </div>
      </form>
    </PageLayout>
  );
};

export default AjusteInventarioPage;
