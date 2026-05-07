import React, { useEffect, useState } from 'react';
import { fetchUsuarios } from '../../../services/users';
import type { Usuario } from '../../../services/users';
import PageLayout from '../../../components/PageLayout';

const UserListPage: React.FC = () => {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const id_empresa = localStorage.getItem('id_empresa');

  useEffect(() => {
    setLoading(true);
    fetchUsuarios(id_empresa || undefined)
      .then(res => {
        let data: Usuario[] = [];
        if (Array.isArray(res)) data = res;
        else if (
          res &&
          typeof res === 'object' &&
          res !== null &&
          'results' in res &&
          Array.isArray((res as { results?: unknown }).results)
        ) {
          data = (res as { results: Usuario[] }).results;
        }
        setUsuarios(data);
      })
      .finally(() => setLoading(false));
  }, [id_empresa]);

  return (
    <PageLayout>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Listado de Usuarios</h2>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24, gap: 16 }}>
        <input
          type="text"
          placeholder="Buscar usuario..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', width: 260, fontSize: '1rem', background: '#f6fafd' }}
        />
        <button
          onClick={() => window.location.href = `/empresas/${id_empresa}/usuarios/new`}
          style={{ fontWeight: 500, background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 24px', fontSize: 15, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}
        >+ Nuevo usuario</button>
      </div>
      {loading ? (
        <div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <thead>
              <tr style={{ background: '#e3f0ff' }}>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Username</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Email</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Nombre</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Apellido</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Activo</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Último login</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {usuarios.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: 32, color: '#888' }}>No se encontraron usuarios.</td>
                </tr>
              ) : (
                usuarios
                  .filter(u =>
                    u.username.toLowerCase().includes(search.toLowerCase()) ||
                    u.email.toLowerCase().includes(search.toLowerCase()) ||
                    (u.first_name && u.first_name.toLowerCase().includes(search.toLowerCase())) ||
                    (u.last_name && u.last_name.toLowerCase().includes(search.toLowerCase()))
                  )
                  .map(u => (
                    <tr key={u.id} style={{ background: '#fff', borderBottom: '1px solid #e3f0ff' }}>
                      <td style={{ padding: '10px 8px' }}>{u.username}</td>
                      <td style={{ padding: '10px 8px' }}>{u.email}</td>
                      <td style={{ padding: '10px 8px' }}>{u.first_name}</td>
                      <td style={{ padding: '10px 8px' }}>{u.last_name}</td>
                      <td style={{ padding: '10px 8px' }}>{u.is_active ? <span style={{ color: '#1976d2', fontWeight: 600 }}>Sí</span> : <span style={{ color: '#d32f2f', fontWeight: 600 }}>No</span>}</td>
                      <td style={{ padding: '10px 8px' }}>{u.fecha_ultimo_login ? new Date(u.fecha_ultimo_login).toLocaleString() : '-'}</td>
                      <td style={{ padding: '10px 8px' }}>
                        <button
                          style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '6px 14px', fontWeight: 500, cursor: 'pointer' }}
                          onClick={() => window.location.href = `/empresas/${id_empresa}/usuarios/${u.id}`}
                        >Ver/Editar</button>
                        {/* <button style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '6px 14px', fontWeight: 500, cursor: 'pointer' }}>Resetear contraseña</button> */}
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

export default UserListPage;
