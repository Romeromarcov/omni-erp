import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { post, get } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';

interface Empresa {
  nombre_legal: string;
  nombre_comercial: string;
  identificador_fiscal: string;
  email_contacto: string;
  activo: boolean;
  id_moneda_base: string;
}

interface Moneda {
  id_moneda: string;
  nombre: string;
  codigo_iso: string;
}

interface MonedaPaginatedResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Moneda[];
}

const CompanyCreatePage: React.FC = () => {
  const [empresa, setEmpresa] = useState<Empresa>({
    nombre_legal: '',
    nombre_comercial: '',
    identificador_fiscal: '',
    email_contacto: '',
    activo: true,
    id_moneda_base: '',
  });
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  useEffect(() => {
    get<Moneda[] | MonedaPaginatedResponse>('/finanzas/monedas/activas/')
      .then(data => {
        if (Array.isArray(data)) {
          setMonedas(data);
        } else if (data && Array.isArray(data.results)) {
          setMonedas(data.results);
        } else {
          setMonedas([]);
        }
      })
      .catch(() => setMonedas([]));
  }, []);
  const navigate = useNavigate();

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    if (name === 'activo') {
      setEmpresa({ ...empresa, activo: value === 'true' });
    } else {
      setEmpresa({ ...empresa, [name]: value });
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    post('/core/empresas/', { ...empresa })
      .then(() => {
        alert('Empresa creada');
        navigate('/empresas');
      })
      .catch(() => alert('Error al crear empresa'));
  };

  return (
    <PageLayout maxWidth={480}>
      <h2 style={{ marginBottom: 24, color: '#1a237e', fontWeight: 700, fontSize: 26, textAlign: 'center' }}>Nueva empresa</h2>
      {(!monedas || monedas.length === 0) && (
        <div style={{ color: '#d32f2f', fontSize: 13, marginBottom: 12, textAlign: 'center' }}>
          No se encontraron monedas disponibles.
        </div>
      )}
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Nombre legal
          <input name="nombre_legal" value={empresa.nombre_legal} onChange={handleChange} required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Nombre comercial
          <input name="nombre_comercial" value={empresa.nombre_comercial} onChange={handleChange} required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Identificador fiscal
          <input name="identificador_fiscal" value={empresa.identificador_fiscal} onChange={handleChange} required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Email contacto
          <input name="email_contacto" value={empresa.email_contacto} onChange={handleChange} required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Activo
          <select name="activo" value={empresa.activo ? 'true' : 'false'} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }}>
            <option value="true">Sí</option>
            <option value="false">No</option>
          </select>
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Moneda base
          <select name="id_moneda_base" value={empresa.id_moneda_base} onChange={handleChange} required style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }}>
            <option value="">Seleccione moneda</option>
            {(Array.isArray(monedas) ? monedas : []).map(m => (
              <option key={m.id_moneda} value={m.id_moneda}>{m.nombre} ({m.codigo_iso})</option>
            ))}
          </select>
        </label>
        <button type="submit" style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 0', fontWeight: 600, fontSize: 16, marginTop: 10, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}>Crear empresa</button>
      </form>
      <div style={{ marginTop: 28, textAlign: 'center' }}>
        <button type="button" onClick={() => navigate('/empresas')} style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '8px 24px', fontWeight: 500, fontSize: 15, cursor: 'pointer' }}>Cancelar</button>
      </div>
    </PageLayout>
  );
};

export default CompanyCreatePage;
