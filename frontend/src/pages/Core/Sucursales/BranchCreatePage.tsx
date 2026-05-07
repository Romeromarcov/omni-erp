import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getEmpresaId } from '../../../utils/empresa';
import { post } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';

interface Sucursal {
  nombre: string;
  codigo_sucursal: string;
  direccion: string;
  telefono: string;
  email_contacto: string;
  ubicacion_gps_json: string;
  activo: boolean;
  id_empresa: string;
}

const BranchCreatePage: React.FC = () => {
  let { id_empresa } = useParams<{ id_empresa: string }>();
  if (!id_empresa) id_empresa = getEmpresaId() || '';
  const navigate = useNavigate();
  const [form, setForm] = useState<Sucursal>({
    nombre: '',
    codigo_sucursal: '',
    direccion: '',
    telefono: '',
    email_contacto: '',
    ubicacion_gps_json: '',
    activo: true,
    id_empresa: id_empresa || '',
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await post('/core/sucursales/', { ...form } as Record<string, unknown>);
      alert('Sucursal creada');
      navigate(`/empresas/${id_empresa}/sucursales`);
    } catch {
      alert('Error al crear sucursal');
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout maxWidth={480}>
      <h2 style={{ marginBottom: 24, color: '#1a237e', fontWeight: 700, fontSize: 26, textAlign: 'center' }}>Nueva sucursal</h2>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Nombre
          <input value={form.nombre} onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))} placeholder="Nombre" required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Código
          <input value={form.codigo_sucursal} onChange={e => setForm(f => ({ ...f, codigo_sucursal: e.target.value }))} placeholder="Código" required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Dirección
          <input value={form.direccion} onChange={e => setForm(f => ({ ...f, direccion: e.target.value }))} placeholder="Dirección" required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Teléfono
          <input value={form.telefono} onChange={e => setForm(f => ({ ...f, telefono: e.target.value }))} placeholder="Teléfono" required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Email
          <input value={form.email_contacto} onChange={e => setForm(f => ({ ...f, email_contacto: e.target.value }))} placeholder="Email" style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Ubicación GPS
          <input value={form.ubicacion_gps_json} onChange={e => setForm(f => ({ ...f, ubicacion_gps_json: e.target.value }))} placeholder="Ubicación GPS (JSON)" style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Activo
          <select value={form.activo ? 'true' : 'false'} onChange={e => setForm(f => ({ ...f, activo: e.target.value === 'true' }))} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }}>
            <option value="true">Sí</option>
            <option value="false">No</option>
          </select>
        </label>
        <button type="submit" disabled={loading} style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 0', fontWeight: 600, fontSize: 16, marginTop: 10, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}>Crear sucursal</button>
      </form>
      <div style={{ marginTop: 28, textAlign: 'center' }}>
        <button type="button" onClick={() => navigate(-1)} style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '8px 24px', fontWeight: 500, fontSize: 15, cursor: 'pointer' }}>Cancelar</button>
      </div>
    </PageLayout>
  );
};

export default BranchCreatePage;
