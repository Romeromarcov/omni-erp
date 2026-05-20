import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchRoles } from '../../../services/roles';
import { fetchEmpresas } from '../../../services/empresas';
import type { Rol } from '../../../services/roles';
import { toList } from '../../../utils/api';
import PageLayout from '../../../components/PageLayout';
import type { Empresa } from '../../../services/empresas';

// Define types for API responses
type EmpresaWithOptional = {
  id_empresa: string;
  nombre_legal?: string;
  nombre?: string;
};

type RolEmpresa = string | EmpresaWithOptional | null;

type RolWithEmpresa = Omit<Rol, 'id_empresa'> & { id_empresa: RolEmpresa };

type RolApiResponse = RolWithEmpresa[] | { results: RolWithEmpresa[] };
type EmpresaApiResponse = Empresa[] | { results: Empresa[] };


const RoleListPage: React.FC = () => {
  const [search, setSearch] = useState('');

  const { data: roles = [], isLoading: loadingRoles, isError: errorRoles } = useQuery<RolApiResponse, Error, RolWithEmpresa[]>({
    queryKey: ['/core/roles/'],
    queryFn: fetchRoles as () => Promise<RolApiResponse>,
    select: toList,
  });

  const { data: empresas = [], isLoading: loadingEmpresas } = useQuery<EmpresaApiResponse, Error, Empresa[]>({
    queryKey: ['/core/empresas/'],
    queryFn: fetchEmpresas as () => Promise<EmpresaApiResponse>,
    select: toList,
  });

  const loading = loadingRoles || loadingEmpresas;

  const filteredRoles = roles.filter(r =>
    (r.nombre_rol?.toLowerCase() || '').includes(search.toLowerCase()) ||
    (r.descripcion || '').toLowerCase().includes(search.toLowerCase())
  );

  // Diccionario id_empresa -> nombre
  const empresaNombreDict = useMemo(() => {
    const dict: Record<string, string> = {};
    empresas.forEach(e => {
      dict[e.id_empresa] = e.nombre_legal || '';
    });
    return dict;
  }, [empresas]);

  return (
    <PageLayout>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Listado de Roles</h2>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
        <input
          type="text"
          placeholder="Buscar rol..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ flex: 1, maxWidth: 320, padding: '8px 12px', borderRadius: 6, border: '1px solid #cfd8dc', fontSize: 15 }}
        />
        <button
          style={{ marginLeft: 16, background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 18px', fontWeight: 600, fontSize: 15, cursor: 'pointer' }}
          onClick={() => window.location.href = '/roles/new'}
        >+ Nuevo rol</button>
      </div>
      {loading ? (
        <div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div>
      ) : errorRoles ? (
        <div style={{ textAlign: 'center', color: '#d32f2f', padding: 32, fontWeight: 500 }}>Error al cargar roles</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <thead>
              <tr style={{ background: '#e3f0ff' }}>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Nombre</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Descripción</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Activo</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Empresa</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {filteredRoles.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: 32, color: '#888' }}>No se encontraron roles.</td>
                </tr>
              ) : (
                filteredRoles.map(r => (
                  <tr key={r.id_rol} style={{ background: '#fff', borderBottom: '1px solid #e3f0ff' }}>
                    <td style={{ padding: '10px 8px' }}>{r.nombre_rol}</td>
                    <td style={{ padding: '10px 8px' }}>{r.descripcion}</td>
                    <td style={{ padding: '10px 8px' }}>{r.activo ? <span style={{ color: '#1976d2', fontWeight: 600 }}>Sí</span> : <span style={{ color: '#d32f2f', fontWeight: 600 }}>No</span>}</td>
                    <td style={{ padding: '10px 8px' }}>{
                      (typeof r.id_empresa === 'object' && r.id_empresa !== null)
                        ? ((r.id_empresa as EmpresaWithOptional).nombre_legal || (r.id_empresa as EmpresaWithOptional).nombre || '-')
                        : (typeof r.id_empresa === 'string' && empresaNombreDict[r.id_empresa])
                          ? empresaNombreDict[r.id_empresa]
                          : '-'
                    }</td>
                    <td style={{ padding: '10px 8px' }}>
                      <button
                        style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '6px 14px', fontWeight: 500, cursor: 'pointer' }}
                        onClick={() => window.location.href = `/roles/${r.id_rol}`}
                      >Ver/Editar</button>
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

export default RoleListPage;
