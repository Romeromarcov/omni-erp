import React, { useEffect, useState } from 'react';
import { fetchPermisos } from '../../../services/permissions';
import type { Permiso } from '../../../services/permissions';
import PageLayout from '../../../components/PageLayout';

const PermissionListPage: React.FC = () => {
  const [permisos, setPermisos] = useState<Permiso[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchPermisos().then(setPermisos).finally(() => setLoading(false));
  }, []);

  return (
    <PageLayout>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Listado de Permisos</h2>
      {loading ? (
        <div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <thead>
              <tr style={{ background: '#e3f0ff' }}>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Código</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Nombre</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Descripción</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Módulo</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Activo</th>
              </tr>
            </thead>
            <tbody>
              {permisos.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: 32, color: '#888' }}>No se encontraron permisos.</td>
                </tr>
              ) : (
                permisos.map(p => (
                  <tr key={p.id_permiso} style={{ background: '#fff', borderBottom: '1px solid #e3f0ff' }}>
                    <td style={{ padding: '10px 8px' }}>{p.codigo_permiso}</td>
                    <td style={{ padding: '10px 8px' }}>{p.nombre_permiso}</td>
                    <td style={{ padding: '10px 8px' }}>{p.descripcion}</td>
                    <td style={{ padding: '10px 8px' }}>{p.modulo}</td>
                    <td style={{ padding: '10px 8px' }}>{p.activo ? <span style={{ color: '#1976d2', fontWeight: 600 }}>Sí</span> : <span style={{ color: '#d32f2f', fontWeight: 600 }}>No</span>}</td>
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

export default PermissionListPage;
