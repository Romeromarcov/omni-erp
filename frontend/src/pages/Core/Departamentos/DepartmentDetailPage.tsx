import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { get, put } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';

interface Departamento {
  id_departamento: string;
  nombre_departamento: string;
  descripcion: string;
  activo: boolean;
}

const DepartmentDetailPage: React.FC = () => {
  const { id_departamento } = useParams<{ id_departamento: string }>();
  const navigate = useNavigate();
  const [departamento, setDepartamento] = useState<Departamento | null>(null);
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState<Departamento | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    get<Departamento>(`/core/departamentos/${id_departamento}/`)
      .then(data => {
        setDepartamento(data);
        setForm(data);
      })
      .finally(() => setLoading(false));
  }, [id_departamento]);

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setLoading(true);
    try {
      await put(`/core/departamentos/${id_departamento}/`, { ...form } as Record<string, unknown>);
      setDepartamento(form);
      setEdit(false);
      alert('Departamento actualizado');
    } catch {
      alert('Error al actualizar');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <p>Cargando...</p>;
  if (!departamento) return <p>No encontrado</p>;

  return (
    <PageLayout maxWidth={480}>
      <h2 style={{ marginBottom: 24, color: '#1a237e', fontWeight: 700, fontSize: 26, textAlign: 'center' }}>Detalle de departamento</h2>
      {!edit ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <p><b>Nombre:</b> {departamento.nombre_departamento}</p>
          <p><b>Descripción:</b> {departamento.descripcion}</p>
          <p><b>Activo:</b> {departamento.activo ? <span style={{ color: '#1976d2', fontWeight: 600 }}>Sí</span> : <span style={{ color: '#d32f2f', fontWeight: 600 }}>No</span>}</p>
          <div style={{ display: 'flex', gap: 12, marginTop: 18 }}>
            <button onClick={() => setEdit(true)} style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 24px', fontWeight: 500, fontSize: 15, cursor: 'pointer' }}>Editar</button>
            <button onClick={() => navigate(-1)} style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '8px 24px', fontWeight: 500, fontSize: 15, cursor: 'pointer' }}>Volver</button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleUpdate} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Nombre
            <input value={form?.nombre_departamento || ''} onChange={e => setForm(f => f ? { ...f, nombre_departamento: e.target.value } : f)} placeholder="Nombre" required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
          </label>
          <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Descripción
            <input value={form?.descripcion || ''} onChange={e => setForm(f => f ? { ...f, descripcion: e.target.value } : f)} placeholder="Descripción" required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
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

export default DepartmentDetailPage;
