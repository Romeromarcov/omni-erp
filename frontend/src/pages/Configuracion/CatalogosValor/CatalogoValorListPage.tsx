import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { get } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import type { CatalogoValor } from '../../../types/configuracion';
import { Button } from '@mui/material';

const CatalogoValorListPage: React.FC = () => {
  const [catalogos, setCatalogos] = useState<CatalogoValor[]>([]);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    get('/configuracion_motor/catalogos-valor/')
      .then(res => {
        let data: CatalogoValor[] = [];
        if (Array.isArray(res)) data = res;
        else if (
          res &&
          typeof res === 'object' &&
          res !== null &&
          'results' in res &&
          Array.isArray((res as { results?: unknown }).results)
        ) {
          data = (res as { results: CatalogoValor[] }).results;
        }
        setCatalogos(data);
      })
      .catch(() => setCatalogos([]));
  }, []);

  const filtered = catalogos.filter(c =>
    c.valor.toLowerCase().includes(search.toLowerCase()) ||
    c.codigo_catalogo.toLowerCase().includes(search.toLowerCase())
  );

  // Agrupar por código de catálogo
  const groupedCatalogos = filtered.reduce((acc, catalogo) => {
    if (!acc[catalogo.codigo_catalogo]) {
      acc[catalogo.codigo_catalogo] = [];
    }
    acc[catalogo.codigo_catalogo].push(catalogo);
    return acc;
  }, {} as Record<string, CatalogoValor[]>);

  return (
    <PageLayout>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Catálogos de Valor</h2>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24, gap: 16 }}>
        <input
          type="text"
          placeholder="Buscar catálogo o valor..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', width: 260, fontSize: '1rem', background: '#f6fafd' }}
        />
        <Button onClick={() => navigate('/configuracion/catalogos-valor/new')} style={{ fontWeight: 500, background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 24px', fontSize: 15, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}>+ Nuevo Valor de Catálogo</Button>
      </div>

      {Object.keys(groupedCatalogos).length === 0 ? (
        <div style={{ textAlign: 'center', padding: 32, color: '#888' }}>No se encontraron catálogos de valor.</div>
      ) : (
        Object.entries(groupedCatalogos).map(([codigoCatalogo, valores]) => (
          <div key={codigoCatalogo} style={{ marginBottom: 32 }}>
            <h3 style={{ color: '#1976d2', marginBottom: 16, borderBottom: '2px solid #e3f0ff', paddingBottom: 8 }}>
              Catálogo: {codigoCatalogo}
            </h3>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
                <thead>
                  <tr style={{ background: '#e3f0ff' }}>
                    <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Valor</th>
                    <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Descripción</th>
                    <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Orden</th>
                    <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Activo</th>
                    <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {valores.map(c => (
                    <tr key={c.id_catalogo_valor} style={{ background: '#fff', borderBottom: '1px solid #e3f0ff' }}>
                      <td style={{ padding: '10px 8px' }}>{c.valor}</td>
                      <td style={{ padding: '10px 8px' }}>{c.descripcion || '-'}</td>
                      <td style={{ padding: '10px 8px' }}>{c.orden}</td>
                      <td style={{ padding: '10px 8px' }}>{c.activo ? <span style={{ color: '#1976d2', fontWeight: 600 }}>Sí</span> : <span style={{ color: '#d32f2f', fontWeight: 600 }}>No</span>}</td>
                      <td style={{ padding: '10px 8px' }}>
                        <Button onClick={() => navigate(`/configuracion/catalogos-valor/${c.id_catalogo_valor}`)} style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '6px 18px', fontWeight: 500, fontSize: 14, cursor: 'pointer', marginRight: 8 }}>Ver/Editar</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))
      )}
    </PageLayout>
  );
};

export default CatalogoValorListPage;