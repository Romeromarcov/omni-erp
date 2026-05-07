import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { get } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import type { ParametroSistema } from '../../../types/configuracion';
import { Button } from '@mui/material';

const ParametroSistemaListPage: React.FC = () => {
  const [parametros, setParametros] = useState<ParametroSistema[]>([]);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    get('/configuracion_motor/parametros-sistema/')
      .then(res => {
        let data: ParametroSistema[] = [];
        if (Array.isArray(res)) data = res;
        else if (
          res &&
          typeof res === 'object' &&
          res !== null &&
          'results' in res &&
          Array.isArray((res as { results?: unknown }).results)
        ) {
          data = (res as { results: ParametroSistema[] }).results;
        }
        setParametros(data);
      })
      .catch(() => setParametros([]));
  }, []);

  const filtered = parametros.filter(p =>
    p.nombre_parametro.toLowerCase().includes(search.toLowerCase()) ||
    p.codigo_parametro.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <PageLayout>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Parámetros del Sistema</h2>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24, gap: 16 }}>
        <input
          type="text"
          placeholder="Buscar parámetro..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', width: 260, fontSize: '1rem', background: '#f6fafd' }}
        />
        <Button onClick={() => navigate('/configuracion/parametros-sistema/new')} style={{ fontWeight: 500, background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 24px', fontSize: 15, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}>+ Nuevo Parámetro</Button>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
          <thead>
            <tr style={{ background: '#e3f0ff' }}>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Código</th>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Nombre</th>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Valor</th>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Tipo de Dato</th>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Empresa</th>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Activo</th>
              <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: 32, color: '#888' }}>No se encontraron parámetros del sistema.</td>
              </tr>
            ) : (
              filtered.map(p => (
                <tr key={p.id_parametro} style={{ background: '#fff', borderBottom: '1px solid #e3f0ff' }}>
                  <td style={{ padding: '10px 8px' }}>{p.codigo_parametro}</td>
                  <td style={{ padding: '10px 8px' }}>{p.nombre_parametro}</td>
                  <td style={{ padding: '10px 8px', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.valor_parametro}</td>
                  <td style={{ padding: '10px 8px' }}>{p.tipo_dato}</td>
                  <td style={{ padding: '10px 8px' }}>{p.id_empresa ? 'Específica' : 'Global'}</td>
                  <td style={{ padding: '10px 8px' }}>{p.activo ? <span style={{ color: '#1976d2', fontWeight: 600 }}>Sí</span> : <span style={{ color: '#d32f2f', fontWeight: 600 }}>No</span>}</td>
                  <td style={{ padding: '10px 8px' }}>
                    <Button onClick={() => navigate(`/configuracion/parametros-sistema/${p.id_parametro}`)} style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '6px 18px', fontWeight: 500, fontSize: 14, cursor: 'pointer', marginRight: 8 }}>Ver/Editar</Button>
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

export default ParametroSistemaListPage;