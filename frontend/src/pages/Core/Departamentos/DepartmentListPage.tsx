import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getEmpresaId } from '../../../utils/empresa';
import { get } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';

interface Departamento {
  id_departamento: string;
  nombre_departamento: string;
  descripcion: string;
  activo: boolean;
}

const DepartmentListPage: React.FC = () => {
  let { id_empresa } = useParams<{ id_empresa: string }>();
  if (!id_empresa) id_empresa = getEmpresaId() || '';
  const [departamentos, setDepartamentos] = useState<Departamento[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    setLoading(true);
    get(`/core/departamentos/?id_empresa=${id_empresa}`)
      .then(res => {
        let data: Departamento[] = [];
        if (Array.isArray(res)) data = res;
        else if (
          res &&
          typeof res === 'object' &&
          res !== null &&
          'results' in res &&
          Array.isArray((res as { results?: unknown }).results)
        ) {
          data = (res as { results: Departamento[] }).results;
        }
        setDepartamentos(data);
      })
      .finally(() => setLoading(false));
  }, [id_empresa]);

  const filtered = departamentos.filter(dep =>
    dep &&
    (dep.nombre_departamento?.toLowerCase().includes(search.toLowerCase()) ||
     dep.descripcion?.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <PageLayout maxWidth={900}>
      <h2 style={{ textAlign: 'center', color: '#1a237e', fontWeight: 700, fontSize: 26, marginBottom: 24 }}>Departamentos</h2>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24, gap: 16 }}>
        <input
          type="text"
          placeholder="Buscar departamento..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', width: 260, fontSize: '1rem', background: '#f6fafd' }}
        />
        <button onClick={() => navigate(`/empresas/${id_empresa}/departamentos/new`)} style={{ fontWeight: 500, background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 24px', fontSize: 15, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}>+ Nuevo departamento</button>
      </div>
      {loading ? <p style={{ textAlign: 'center', color: '#888' }}>Cargando...</p> : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <thead>
              <tr style={{ background: '#e3f0ff' }}>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Nombre</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Descripción</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Activo</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={4} style={{ textAlign: 'center', padding: 32, color: '#888' }}>No se encontraron departamentos.</td>
                </tr>
              ) : (
                filtered.map((dep, idx) => (
                  <tr key={dep.id_departamento || idx} style={{ background: '#fff', borderBottom: '1px solid #e3f0ff' }}>
                    <td style={{ padding: '10px 8px' }}>{dep.nombre_departamento}</td>
                    <td style={{ padding: '10px 8px' }}>{dep.descripcion}</td>
                    <td style={{ padding: '10px 8px' }}>{dep.activo ? <span style={{ color: '#1976d2', fontWeight: 600 }}>Sí</span> : <span style={{ color: '#d32f2f', fontWeight: 600 }}>No</span>}</td>
                    <td style={{ padding: '10px 8px' }}>
                      <button onClick={() => navigate(`/departamentos/${dep.id_departamento}`)} style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '6px 18px', fontWeight: 500, fontSize: 14, cursor: 'pointer' }}>Ver/Editar</button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </PageLayout>
  );
};

export default DepartmentListPage;
