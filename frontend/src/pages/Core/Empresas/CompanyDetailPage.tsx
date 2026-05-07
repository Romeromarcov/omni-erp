import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { get, put } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';

interface Empresa {
  id_empresa: string;
  nombre_legal: string;
  nombre_comercial: string;
  identificador_fiscal: string;
  email_contacto: string;
  activo: boolean;
  fecha_registro: string;
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

const CompanyDetailPage: React.FC = () => {
  const { id_empresa } = useParams<{ id_empresa: string }>();
  const [empresa, setEmpresa] = useState<Empresa | null>(null);
  const [monedas, setMonedas] = useState<Array<{ id_moneda: string; nombre: string; codigo_iso: string }>>([]);
  const navigate = useNavigate();


  useEffect(() => {
    if (!id_empresa) return;
    const cleanId = id_empresa.replace(':', '');
    get<Empresa>(`/core/empresas/${cleanId}/`)
      .then(data => setEmpresa({
        ...data,
        activo: Boolean(data.activo),
        id_moneda_base: data.id_moneda_base ?? ""
      }))
      .catch(() => setEmpresa(null));
    // Cargar monedas activas
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
  }, [id_empresa]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    if (!empresa) return;
    const { name, value } = e.target;
    if (name === 'activo') {
      setEmpresa({ ...empresa, activo: value === 'true' });
    } else if (name === 'id_moneda_base') {
      setEmpresa({ ...empresa, id_moneda_base: value.toString() });
    } else {
      setEmpresa({ ...empresa, [name]: value });
    }
  };

  const handleSave = () => {
    if (!empresa) return;
    const cleanId = empresa.id_empresa.replace(':', '');
    const empresaToSave = { ...empresa, activo: !!empresa.activo };
    put(`/core/empresas/${cleanId}/`, empresaToSave)
      .then(() => alert('Empresa actualizada'))
      .catch(() => alert('Error al actualizar'));
  };

  if (!empresa) return <PageLayout><div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div></PageLayout>;

  return (
    <PageLayout maxWidth={480}>
      <h2 style={{ marginBottom: 24, color: '#1a237e', fontWeight: 700, fontSize: 26, textAlign: 'center' }}>Detalle de empresa</h2>
      {(!monedas || monedas.length === 0) && (
        <div style={{ color: '#d32f2f', fontSize: 13, marginBottom: 12, textAlign: 'center' }}>
          No se encontraron monedas disponibles.
        </div>
      )}
      <form style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Nombre legal
          <input name="nombre_legal" value={empresa.nombre_legal} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Nombre comercial
          <input name="nombre_comercial" value={empresa.nombre_comercial} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Identificador fiscal
          <input name="identificador_fiscal" value={empresa.identificador_fiscal} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Email contacto
          <input name="email_contacto" value={empresa.email_contacto} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Activo
          <select name="activo" value={empresa.activo ? 'true' : 'false'} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }}>
            <option value="true">Sí</option>
            <option value="false">No</option>
          </select>
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Moneda base
          <select name="id_moneda_base" value={empresa.id_moneda_base?.toString() ?? ""} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }}>
            <option value="">Seleccione moneda</option>
            {(Array.isArray(monedas) ? monedas : []).map(moneda => (
              <option key={moneda.id_moneda} value={moneda.id_moneda}>
                {moneda.nombre} ({moneda.codigo_iso})
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={handleSave} style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 0', fontWeight: 600, fontSize: 16, marginTop: 10, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}>Guardar cambios</button>
      </form>
      <div style={{ marginTop: 28, textAlign: 'center' }}>
        <button onClick={() => navigate('/empresas')} style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '8px 24px', fontWeight: 500, fontSize: 15, cursor: 'pointer' }}>Volver a la lista</button>
      </div>
    </PageLayout>
  );
};

export default CompanyDetailPage;
