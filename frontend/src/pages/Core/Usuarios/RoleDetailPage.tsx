import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchRol, updateRol } from '../../../services/roles';
import type { Rol } from '../../../services/roles';
import PageLayout from '../../../components/PageLayout';

const RoleDetailPage: React.FC = () => {
  const { id_rol } = useParams<{ id_rol: string }>();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Partial<Rol>>({});
  const [message, setMessage] = useState('');

  const { data: rol, isLoading } = useQuery<Rol>({
    queryKey: ['/core/roles/', id_rol],
    queryFn: () => fetchRol(id_rol!),
    enabled: !!id_rol,
  });

  useEffect(() => {
    if (rol) {
      setForm(rol);
    }
  }, [rol]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
  };

  const updateMutation = useMutation({
    mutationFn: (data: Partial<Rol>) => updateRol(id_rol!, data),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['/core/roles/', id_rol] });
      queryClient.invalidateQueries({ queryKey: ['/core/roles/'] });
      setForm(updated);
      setMessage('Rol actualizado');
    },
    onError: () => {
      setMessage('Error al actualizar rol');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!id_rol) return;
    updateMutation.mutate(form);
  };

  if (isLoading) return <PageLayout><div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div></PageLayout>;
  if (!rol) return <PageLayout><div style={{ textAlign: 'center', color: '#d32f2f', padding: 32 }}>Rol no encontrado</div></PageLayout>;

  return (
    <PageLayout maxWidth={480}>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Detalle/Edición de Rol</h2>
      <form onSubmit={handleSubmit} style={{ background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)', padding: 32, display: 'flex', flexDirection: 'column', gap: 18, maxWidth: 400, margin: '0 auto' }}>
        <label style={{ color: '#1976d2', fontWeight: 600, marginBottom: 6 }}>Nombre
          <input name="nombre_rol" value={form.nombre_rol || ''} onChange={handleChange} required style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #cfd8dc', fontSize: 15, marginTop: 4 }} />
        </label>
        <label style={{ color: '#1976d2', fontWeight: 600, marginBottom: 6 }}>Descripción
          <input name="descripcion" value={form.descripcion || ''} onChange={handleChange} style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #cfd8dc', fontSize: 15, marginTop: 4 }} />
        </label>
        <label style={{ color: '#1976d2', fontWeight: 600, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
          <input name="activo" type="checkbox" checked={!!form.activo} onChange={handleChange} style={{ marginRight: 8 }} /> Activo
        </label>
        <button type="submit" disabled={updateMutation.isPending} style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 0', fontWeight: 600, fontSize: 16, marginTop: 10, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}>Actualizar rol</button>
        {message && <p style={{ marginTop: 12, color: message.includes('actualizado') ? '#388e3c' : '#d32f2f', textAlign: 'center', fontWeight: 500 }}>{message}</p>}
      </form>
      {/* Aquí iría la gestión de permisos asignados al rol */}
    </PageLayout>
  );
};

export default RoleDetailPage;
