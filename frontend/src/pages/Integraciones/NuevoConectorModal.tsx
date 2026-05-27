import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getProveedores,
  crearConector,
  type ConectorProveedor,
} from '../../services/integrationHubService';

interface Props {
  onClose: () => void;
}

const NuevoConectorModal: React.FC<Props> = ({ onClose }) => {
  const qc = useQueryClient();
  const [paso, setPaso] = useState<1 | 2>(1);
  const [proveedor, setProveedor] = useState<ConectorProveedor | null>(null);
  const [form, setForm] = useState({
    nombre: '',
    host: '',
    db: '',
    user: '',
    api_key: '',
    timeout: 30,
    entidades_activas: [] as string[],
    intervalo_sync_minutos: 60,
  });
  const [error, setError] = useState('');

  const { data: provData } = useQuery({
    queryKey: ['/integration-hub/proveedores/'],
    queryFn: getProveedores,
  });
  const proveedores = provData?.results ?? [];

  const mutation = useMutation({
    mutationFn: () =>
      crearConector({
        id_proveedor: proveedor!.id_proveedor,
        nombre: form.nombre,
        entidades_activas: form.entidades_activas,
        intervalo_sync_minutos: form.intervalo_sync_minutos,
        configuracion: {
          host: form.host,
          db: form.db || undefined,
          user: form.user,
          api_key: form.api_key,
          timeout: form.timeout,
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['/integration-hub/instancias/'] });
      onClose();
    },
    onError: (e: Error) => {
      try {
        const parsed = JSON.parse(e.message);
        setError(JSON.stringify(parsed, null, 2));
      } catch {
        setError(e.message);
      }
    },
  });

  const toggleEntidad = (e: string) =>
    setForm(f => ({
      ...f,
      entidades_activas: f.entidades_activas.includes(e)
        ? f.entidades_activas.filter(x => x !== e)
        : [...f.entidades_activas, e],
    }));

  const overlay: React.CSSProperties = {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
  };
  const modal: React.CSSProperties = {
    background: '#fff', borderRadius: 12, padding: '28px 32px',
    width: '100%', maxWidth: 540, maxHeight: '90vh', overflowY: 'auto',
    boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
  };
  const input: React.CSSProperties = {
    width: '100%', padding: '8px 12px', borderRadius: 6,
    border: '1px solid #d1d5db', fontSize: 14, boxSizing: 'border-box', marginBottom: 12,
  };
  const btn = (primary?: boolean): React.CSSProperties => ({
    padding: '8px 18px', borderRadius: 6, border: 'none', cursor: 'pointer',
    fontWeight: 600, fontSize: 14,
    background: primary ? '#2563eb' : '#f3f4f6',
    color: primary ? '#fff' : '#374151',
  });

  return (
    <div style={overlay} onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={modal}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
          <h3 style={{ margin: 0, fontSize: 18 }}>
            {paso === 1 ? 'Seleccionar proveedor' : `Configurar conector — ${proveedor?.nombre}`}
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', lineHeight: 1 }}>×</button>
        </div>

        {/* Paso 1 — Selección de proveedor */}
        {paso === 1 && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {proveedores.map(p => (
              <div
                key={p.id_proveedor}
                onClick={() => p.estado === 'activo' && (setProveedor(p), setPaso(2))}
                style={{
                  border: '2px solid',
                  borderColor: p.estado === 'activo' ? '#2563eb' : '#e5e7eb',
                  borderRadius: 8, padding: 14,
                  cursor: p.estado === 'activo' ? 'pointer' : 'not-allowed',
                  opacity: p.estado === 'activo' ? 1 : 0.5,
                  transition: 'background 0.1s',
                }}
              >
                <div style={{ fontWeight: 700, fontSize: 14 }}>{p.nombre}</div>
                {p.estado !== 'activo' && (
                  <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>Próximamente</div>
                )}
                <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4 }}>
                  {p.capacidades.join(', ')}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Paso 2 — Formulario de configuración */}
        {paso === 2 && proveedor && (
          <>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
              Nombre del conector *
            </label>
            <input
              style={input}
              placeholder="Mi Odoo Producción"
              value={form.nombre}
              onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))}
            />

            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
              URL del servidor *
            </label>
            <input
              style={input}
              placeholder="https://mi-empresa.odoo.com"
              value={form.host}
              onChange={e => setForm(f => ({ ...f, host: e.target.value }))}
            />

            {proveedor.requiere_db && (
              <>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
                  Base de datos
                </label>
                <input
                  style={input}
                  placeholder="nombre_db"
                  value={form.db}
                  onChange={e => setForm(f => ({ ...f, db: e.target.value }))}
                />
              </>
            )}

            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
              Usuario / Email *
            </label>
            <input
              style={input}
              placeholder="admin@empresa.com"
              value={form.user}
              onChange={e => setForm(f => ({ ...f, user: e.target.value }))}
            />

            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
              API Key *
            </label>
            <input
              type="password"
              style={input}
              placeholder="••••••••••••••••"
              value={form.api_key}
              onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
            />

            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 8 }}>
              Entidades a sincronizar
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
              {proveedor.capacidades.map(cap => (
                <label key={cap} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={form.entidades_activas.includes(cap)}
                    onChange={() => toggleEntidad(cap)}
                  />
                  {cap}
                </label>
              ))}
            </div>

            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
              Intervalo de sync (minutos)
            </label>
            <input
              type="number"
              style={input}
              min={5}
              max={1440}
              value={form.intervalo_sync_minutos}
              onChange={e => setForm(f => ({ ...f, intervalo_sync_minutos: Number(e.target.value) }))}
            />

            {error && (
              <pre style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: 6, padding: 10, fontSize: 12, color: '#b91c1c', marginBottom: 12, whiteSpace: 'pre-wrap' }}>
                {error}
              </pre>
            )}

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button style={btn()} onClick={() => setPaso(1)}>Atrás</button>
              <button
                style={btn(true)}
                disabled={mutation.isPending || !form.nombre || !form.host || !form.user || !form.api_key}
                onClick={() => { setError(''); mutation.mutate(); }}
              >
                {mutation.isPending ? 'Guardando…' : 'Crear conector'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default NuevoConectorModal;
