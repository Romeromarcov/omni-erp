import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getEmpresaId } from '../../../utils/empresa';
import { get } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import { Button } from '@mui/material';

interface Sucursal {
  id_sucursal: string;
  nombre: string;
  codigo_sucursal: string;
  direccion: string;
  telefono: string;
  activo: boolean;
}

const BranchListPage: React.FC = () => {
  let { id_empresa } = useParams<{ id_empresa: string }>();
  if (!id_empresa) id_empresa = getEmpresaId() || '';
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!id_empresa) return;
    setLoading(true);
    get(`/core/sucursales/?id_empresa=${id_empresa}`)
      .then(res => {
        let data: Sucursal[] = [];
        if (Array.isArray(res)) data = res;
        else if (
          res &&
          typeof res === 'object' &&
          res !== null &&
          'results' in res &&
          Array.isArray((res as { results?: unknown }).results)
        ) {
          data = (res as { results: Sucursal[] }).results;
        }
        setSucursales(data);
      })
      .finally(() => setLoading(false));
  }, [id_empresa]);

  const filtered = sucursales.filter(suc =>
    suc.nombre.toLowerCase().includes(search.toLowerCase()) ||
    suc.codigo_sucursal.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <PageLayout>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Sucursales de la empresa</h2>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24, gap: 16 }}>
        <input
          type="text"
          placeholder="Buscar sucursal..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', width: 260, fontSize: '1rem', background: '#f6fafd' }}
        />
        <Button
          onClick={() => {
            if (id_empresa) {
              navigate(`/empresas/${id_empresa}/sucursales/new`);
            } else {
              alert('Seleccione una empresa válida');
            }
          }}
          style={{ fontWeight: 500, background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 24px', fontSize: 15, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}
        >
          + Nueva sucursal
        </Button>
      </div>
      {!id_empresa ? (
        <p style={{ textAlign: 'center', color: '#d32f2f', fontWeight: 500, fontSize: 18 }}>Seleccione una empresa para ver sus sucursales.</p>
      ) : loading ? <p style={{ textAlign: 'center', color: '#888' }}>Cargando...</p> : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <thead>
              <tr style={{ background: '#e3f0ff' }}>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Nombre</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Código</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Dirección</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Teléfono</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Activo</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: 32, color: '#888' }}>No se encontraron sucursales.</td>
                </tr>
              ) : (
                filtered.map(suc => (
                  <tr key={suc.id_sucursal} style={{ background: '#fff', borderBottom: '1px solid #e3f0ff' }}>
                    <td style={{ padding: '10px 8px' }}>{suc.nombre}</td>
                    <td style={{ padding: '10px 8px' }}>{suc.codigo_sucursal}</td>
                    <td style={{ padding: '10px 8px' }}>{suc.direccion}</td>
                    <td style={{ padding: '10px 8px' }}>{suc.telefono}</td>
                    <td style={{ padding: '10px 8px' }}>{suc.activo ? <span style={{ color: '#1976d2', fontWeight: 600 }}>Sí</span> : <span style={{ color: '#d32f2f', fontWeight: 600 }}>No</span>}</td>
                    <td style={{ padding: '10px 8px' }}>
                      <Button onClick={() => navigate(`/sucursales/${suc.id_sucursal}`)} style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '6px 18px', fontWeight: 500, fontSize: 14, cursor: 'pointer' }}>Ver/Editar</Button>
                      {/* Botón Eliminar (deshabilitado por ahora) */}
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

export default BranchListPage;
