import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { get } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import { Button } from '@mui/material';

interface Empresa {
  id_empresa: string;
  nombre_legal: string;
  nombre_comercial: string;
  identificador_fiscal: string;
  email_contacto: string;
  activo: boolean;
  fecha_registro: string;
}

const CompanyListPage: React.FC = () => {
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    get('/core/empresas/')
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
        setEmpresas(data.map(e => ({
          ...e,
          activo:
            e.activo === true ||
            String(e.activo).toLowerCase() === 'true' ||
            String(e.activo) === '1'
        })));
      })
      .catch(() => setEmpresas([]));
  }, []);

  const filtered = empresas.filter(e =>
    e.nombre_legal.toLowerCase().includes(search.toLowerCase()) ||
    e.nombre_comercial.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <PageLayout>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Empresas registradas</h2>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24, gap: 16 }}>
        <input
          type="text"
          placeholder="Buscar empresa..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', width: 260, fontSize: '1rem', background: '#f6fafd' }}
        />
        <Button onClick={() => navigate('/empresas/new')} style={{ fontWeight: 500, background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 24px', fontSize: 15, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}>+ Nueva empresa</Button>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
          <thead>
            <tr style={{ background: '#e3f0ff' }}>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Nombre legal</th>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Nombre comercial</th>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Identificador fiscal</th>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Email contacto</th>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Activo</th>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Fecha registro</th>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: 32, color: '#888' }}>No se encontraron empresas.</td>
              </tr>
            ) : (
              filtered.map(e => (
                <tr key={e.id_empresa} style={{ background: '#fff', borderBottom: '1px solid #e3f0ff' }}>
                  <td style={{ padding: '10px 8px' }}>{e.nombre_legal}</td>
                  <td style={{ padding: '10px 8px' }}>{e.nombre_comercial}</td>
                  <td style={{ padding: '10px 8px' }}>{e.identificador_fiscal}</td>
                  <td style={{ padding: '10px 8px' }}>{e.email_contacto}</td>
                  <td style={{ padding: '10px 8px' }}>{e.activo ? <span style={{ color: '#1976d2', fontWeight: 600 }}>Sí</span> : <span style={{ color: '#d32f2f', fontWeight: 600 }}>No</span>}</td>
                  <td style={{ padding: '10px 8px' }}>{e.fecha_registro}</td>
                  <td style={{ padding: '10px 8px' }}>
                    <Button onClick={() => navigate(`/empresas/${e.id_empresa}`)} style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '6px 18px', fontWeight: 500, fontSize: 14, cursor: 'pointer', marginRight: 8 }}>Ver/Editar</Button>
                    {/* <Button color="error">Eliminar</Button> */}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </PageLayout>
  );
};

export default CompanyListPage;
