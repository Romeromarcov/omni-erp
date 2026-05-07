
import React, { useState, useEffect } from 'react';
import { createRol } from '../../../services/roles';
import PageLayout from '../../../components/PageLayout';
import { fetchEmpresas } from '../../../services/empresas';
import type { Empresa } from '../../../services/empresas';

const RoleCreatePage: React.FC = () => {
  const [form, setForm] = useState({
    nombre_rol: '',
    descripcion: '',
    activo: true,
    id_empresa: '',
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [empresaSearch, setEmpresaSearch] = useState('');

  useEffect(() => {
    fetchEmpresas()
      .then(res => {
        let data: Empresa[] = [];
        if (Array.isArray(res)) data = res;
        else if (
          res &&
          typeof res === 'object' &&
          res !== null &&
          'results' in res &&
          Array.isArray((res as { results?: unknown }).results)
        ) {
          data = (res as { results: Empresa[] }).results;
        }
        setEmpresas(data);
      })
      .catch(() => setEmpresas([]));
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value, type, checked } = e.target;
    setForm(f => ({ ...f, [name]: type === 'checkbox' ? checked : value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await createRol(form);
      setMessage('Rol creado exitosamente');
      setForm({ nombre_rol: '', descripcion: '', activo: true, id_empresa: '' });
    } catch {
      setMessage('Error al crear rol');
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageLayout>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Crear Nuevo Rol</h2>
      <div style={{ maxWidth: 480, margin: '0 auto', background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)', padding: 32 }}>
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 18 }}>
            <label style={{ display: 'block', color: '#1976d2', fontWeight: 600, marginBottom: 6 }}>Nombre</label>
            <input
              name="nombre_rol"
              value={form.nombre_rol}
              onChange={handleChange}
              required
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #cfd8dc', fontSize: 15 }}
            />
          </div>
          <div style={{ marginBottom: 18 }}>
            <label style={{ display: 'block', color: '#1976d2', fontWeight: 600, marginBottom: 6 }}>Descripción</label>
            <input
              name="descripcion"
              value={form.descripcion}
              onChange={handleChange}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #cfd8dc', fontSize: 15 }}
            />
          </div>
          <div style={{ marginBottom: 18, display: 'flex', alignItems: 'center' }}>
            <input
              name="activo"
              type="checkbox"
              checked={form.activo}
              onChange={handleChange}
              id="activo"
              style={{ marginRight: 8 }}
            />
            <label htmlFor="activo" style={{ color: '#1976d2', fontWeight: 600 }}>Activo</label>
          </div>
          <div style={{ marginBottom: 24 }}>
            <label style={{ display: 'block', color: '#1976d2', fontWeight: 600, marginBottom: 6 }}>Empresa</label>
            <input
              type="text"
              placeholder="Buscar empresa..."
              value={empresaSearch}
              onChange={e => setEmpresaSearch(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #cfd8dc', fontSize: 15, marginBottom: 8 }}
            />
            <select
              name="id_empresa"
              value={form.id_empresa}
              onChange={e => setForm(f => ({ ...f, id_empresa: e.target.value }))}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #cfd8dc', fontSize: 15 }}
              required
            >
              <option value="">Seleccione una empresa...</option>
              {empresas
                .filter(e =>
                  e.nombre_legal.toLowerCase().includes(empresaSearch.toLowerCase()) ||
                  e.nombre_comercial.toLowerCase().includes(empresaSearch.toLowerCase())
                )
                .map(e => (
                  <option key={e.id_empresa} value={e.id_empresa}>
                    {e.nombre_legal} ({e.nombre_comercial})
                  </option>
                ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={loading}
            style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 28px', fontWeight: 600, fontSize: 16, cursor: 'pointer', width: '100%' }}
          >
            {loading ? 'Creando...' : 'Crear rol'}
          </button>
        </form>
        {message && <p style={{ marginTop: 18, color: message.includes('exitosamente') ? '#388e3c' : '#d32f2f', textAlign: 'center', fontWeight: 500 }}>{message}</p>}
      </div>
    </PageLayout>
  );
};

export default RoleCreatePage;
