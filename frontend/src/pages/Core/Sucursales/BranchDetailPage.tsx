import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { get, put } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import { Button } from '@mui/material';

interface Sucursal {
  id_sucursal: string;
  nombre: string;
  codigo_sucursal: string;
  direccion: string;
  telefono: string;
  email_contacto: string;
  ubicacion_gps_json: string;
  activo: boolean;
  id_empresa: string;
}

const BranchDetailPage: React.FC = () => {
  const { id_sucursal } = useParams<{ id_sucursal: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const isEditRoute = location.pathname.endsWith('/edit');
  const [sucursal, setSucursal] = useState<Sucursal | null>(null);
  const [edit, setEdit] = useState(isEditRoute);
  const [form, setForm] = useState<Sucursal | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    get<Sucursal>(`/core/sucursales/${id_sucursal}/`)
      .then(data => {
        setSucursal(data);
        setForm(data);
      })
      .finally(() => setLoading(false));
  }, [id_sucursal]);

  useEffect(() => {
    setEdit(isEditRoute);
  }, [isEditRoute]);

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setLoading(true);
    try {
      await put(`/core/sucursales/${id_sucursal}/`, { ...form } as Record<string, unknown>);
      setSucursal(form);
      setEdit(false);
      alert('Sucursal actualizada');
    } catch {
      alert('Error al actualizar');
    } finally {
      setLoading(false);
    }
  };

if (loading) return (
  <PageLayout><div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div></PageLayout>
);
  if (!sucursal) return (
    <PageLayout><div style={{ textAlign: 'center', color: '#888', padding: 32 }}>No encontrada</div></PageLayout>
  );

  return (
    <PageLayout maxWidth={480}>
      <h2 style={{ marginBottom: 24, color: '#1a237e', fontWeight: 700, fontSize: 26, textAlign: 'center' }}>Detalle de sucursal</h2>
      {!edit ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <p><b>Nombre:</b> {sucursal.nombre}</p>
          <p><b>Código:</b> {sucursal.codigo_sucursal}</p>
          <p><b>Dirección:</b> {sucursal.direccion}</p>
          <p><b>Teléfono:</b> {sucursal.telefono}</p>
          <p><b>Email:</b> {sucursal.email_contacto}</p>
          <p><b>Ubicación GPS:</b> {sucursal.ubicacion_gps_json}</p>
          <p><b>Activo:</b> {sucursal.activo ? <span style={{ color: '#1976d2', fontWeight: 600 }}>Sí</span> : <span style={{ color: '#d32f2f', fontWeight: 600 }}>No</span>}</p>
          <div style={{ display: 'flex', gap: 12, marginTop: 18 }}>
            <Button onClick={() => setEdit(true)}>Editar</Button>
            <Button onClick={() => navigate(-1)} style={{ background: '#e3eafc', color: '#1976d2' }}>Volver</Button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleUpdate} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Nombre
            <input value={form?.nombre || ''} onChange={e => setForm(f => f ? { ...f, nombre: e.target.value } : f)} placeholder="Nombre" required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
          </label>
          <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Código
            <input value={form?.codigo_sucursal || ''} onChange={e => setForm(f => f ? { ...f, codigo_sucursal: e.target.value } : f)} placeholder="Código" required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
          </label>
          <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Dirección
            <input value={form?.direccion || ''} onChange={e => setForm(f => f ? { ...f, direccion: e.target.value } : f)} placeholder="Dirección" required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
          </label>
          <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Teléfono
            <input value={form?.telefono || ''} onChange={e => setForm(f => f ? { ...f, telefono: e.target.value } : f)} placeholder="Teléfono" required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
          </label>
          <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Email
            <input value={form?.email_contacto || ''} onChange={e => setForm(f => f ? { ...f, email_contacto: e.target.value } : f)} placeholder="Email" style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
          </label>
          <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Ubicación GPS
            <input value={form?.ubicacion_gps_json || ''} onChange={e => setForm(f => f ? { ...f, ubicacion_gps_json: e.target.value } : f)} placeholder="Ubicación GPS (JSON)" style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
          </label>
          <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Activo
            <select value={form?.activo ? 'true' : 'false'} onChange={e => setForm(f => f ? { ...f, activo: e.target.value === 'true' } : f)} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }}>
              <option value="true">Sí</option>
              <option value="false">No</option>
            </select>
          </label>
          <button type="submit" style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 0', fontWeight: 600, fontSize: 16, marginTop: 10, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}>Guardar</button>
          <button type="button" onClick={() => setEdit(false)} style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '8px 24px', fontWeight: 500, fontSize: 15, marginTop: 8, cursor: 'pointer' }}>Cancelar</button>
        </form>
      )}
    </PageLayout>
  );
};

export default BranchDetailPage;
