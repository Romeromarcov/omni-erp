import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchUsuarios } from '../../../services/users';
import type { Usuario } from '../../../services/users';
import { fetchUsuarioRoles } from '../../../services/usuarioRoles';
import type { UsuarioRol } from '../../../services/usuarioRoles';
import PageLayout from '../../../components/PageLayout';

const UserDetailPage: React.FC = () => {
  const { id_empresa, id } = useParams<{ id_empresa: string; id: string }>();
  const [usuario, setUsuario] = useState<Usuario | null>(null);
  const [usuarioRoles, setUsuarioRoles] = useState<UsuarioRol[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<{ first_name: string; last_name: string; email: string; empresas: string[]; sucursales: string[]; departamentos: string[] }>({ first_name: '', last_name: '', email: '', empresas: [], sucursales: [], departamentos: [] });
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [oldPassword, setOldPassword] = useState('');
  const [showOldPassword, setShowOldPassword] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState('');
  const [sucursales, setSucursales] = useState<{ id_sucursal: string; nombre: string }[]>([]);
  const [empresas, setEmpresas] = useState<{ id_empresa: string; nombre_legal: string; nombre_comercial?: string }[]>([]);
  const [departamentos, setDepartamentos] = useState<{ id_departamento: string; nombre_departamento: string }[]>([]);
  // Quitar validación de admin, todos pueden editar

  useEffect(() => {
    setLoading(true);
    let token = localStorage.getItem('token') || '';
    token = token.trim().replace(/^"|"$/g, '').replace(/\n/g, '');
    const headers: HeadersInit = {};
    if (token) {
      (headers as Record<string, string>).Authorization = `Bearer ${token}`;
    }
    function safeJsonFetch(url: string, options: RequestInit = {}) {
      return fetch(url, options).then(async r => {
        const rawText = await r.text();
        if (!r.ok) {
          throw new Error(`Error en ${url}: status ${r.status} - ${rawText.slice(0, 100)}`);
        }
        try {
          return JSON.parse(rawText);
        } catch {
          throw new Error(`Respuesta no es JSON en ${url}: ${rawText.slice(0, 100)}`);
        }
      });
    }
    Promise.all([
      fetchUsuarios(id_empresa),
      fetchUsuarioRoles(id || ''),
      safeJsonFetch('/api/core/empresas/', { headers }),
      safeJsonFetch('/api/core/sucursales/', { headers }),
      safeJsonFetch('/api/core/departamentos/', { headers })
    ])
      .then(async ([usuariosRaw, usuarioRoles, empresasDataRaw, sucursalesDataRaw, departamentosDataRaw]) => {
        // Normalizar usuarios
        let usuarios: Usuario[] = [];
        if (Array.isArray(usuariosRaw)) usuarios = usuariosRaw;
        else if (
          usuariosRaw &&
          typeof usuariosRaw === 'object' &&
          usuariosRaw !== null &&
          'results' in usuariosRaw &&
          Array.isArray((usuariosRaw as { results?: unknown }).results)
        ) {
          usuarios = (usuariosRaw as { results: Usuario[] }).results;
        }
        // Normalizar empresas
        let empresasData: { id_empresa: string; nombre_legal: string; nombre_comercial?: string }[] = [];
        if (Array.isArray(empresasDataRaw)) empresasData = empresasDataRaw;
        else if (
          empresasDataRaw &&
          typeof empresasDataRaw === 'object' &&
          empresasDataRaw !== null &&
          'results' in empresasDataRaw &&
          Array.isArray((empresasDataRaw as { results?: unknown }).results)
        ) {
          empresasData = (empresasDataRaw as { results: typeof empresasData }).results;
        }
        // Normalizar sucursales
        let sucursalesData: { id_sucursal: string; nombre: string }[] = [];
        if (Array.isArray(sucursalesDataRaw)) sucursalesData = sucursalesDataRaw;
        else if (
          sucursalesDataRaw &&
          typeof sucursalesDataRaw === 'object' &&
          sucursalesDataRaw !== null &&
          'results' in sucursalesDataRaw &&
          Array.isArray((sucursalesDataRaw as { results?: unknown }).results)
        ) {
          sucursalesData = (sucursalesDataRaw as { results: typeof sucursalesData }).results;
        }
        // Normalizar departamentos
        let departamentosData: { id_departamento: string; nombre_departamento: string }[] = [];
        if (Array.isArray(departamentosDataRaw)) departamentosData = departamentosDataRaw;
        else if (
          departamentosDataRaw &&
          typeof departamentosDataRaw === 'object' &&
          departamentosDataRaw !== null &&
          'results' in departamentosDataRaw &&
          Array.isArray((departamentosDataRaw as { results?: unknown }).results)
        ) {
          departamentosData = (departamentosDataRaw as { results: typeof departamentosData }).results;
        }
        const user = usuarios.find(u => u.id === id) || null;
        setUsuario(user);
        setUsuarioRoles(usuarioRoles);
        setEmpresas(empresasData);
        setSucursales(sucursalesData);
        setDepartamentos(departamentosData);
        if (user) {
          setForm({
            first_name: user.first_name,
            last_name: user.last_name,
            email: user.email,
            empresas: Array.isArray(user.empresas) ? user.empresas.map(e => typeof e === 'string' ? e : String(e.id_empresa)) : [],
            sucursales: Array.isArray(user.sucursales) ? user.sucursales.map(s => typeof s === 'string' ? s : String(s.id_sucursal)) : [],
            departamentos: Array.isArray(user.departamentos) ? user.departamentos.map(d => typeof d === 'string' ? d : String(d.id_departamento)) : []
          });
        }
      })
      .catch(error => {
        setLoading(false);
        // Mostrar el error en pantalla y consola
        console.error('Error cargando datos:', error);
        alert(`Error cargando datos: ${error.message}`);
      })
      .finally(() => setLoading(false));
  }, [id, id_empresa]);

  if (loading) return <p>Cargando...</p>;
  if (!usuario) return <p>Usuario no encontrado</p>;

  return (
    <PageLayout maxWidth={540}>
      <h2 style={{ marginBottom: 24, color: '#1a237e', fontWeight: 700, fontSize: 26, textAlign: 'center' }}>Detalle/Edición de Usuario</h2>
      <form style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Username
          <input value={usuario.username} readOnly style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15, background: '#f5f5f5' }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Email
          <input value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Nombre
          <input value={form.first_name} onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Apellido
          <input value={form.last_name} onChange={e => setForm(f => ({ ...f, last_name: e.target.value }))} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2, display: 'flex', alignItems: 'center', gap: 8 }}>
          <input type="checkbox" checked={usuario.is_active} readOnly style={{ marginTop: 0 }} /> Activo
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>
          Empresas
          <div style={{ margin: '4px 0 4px 0', fontSize: 13, color: '#1976d2' }}>
            <b>Asignadas:</b> {empresas.filter(e => form.empresas.includes(String(e.id_empresa))).map(e => e.nombre_comercial || e.nombre_legal).join(', ') || <span style={{color:'#888'}}>Ninguna</span>}
          </div>
          <select
            multiple
            value={form.empresas}
            onChange={e => setForm(f => ({ ...f, empresas: Array.from(e.target.selectedOptions, opt => opt.value) }))}
            style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15, minHeight: 60 }}
            title={'Mantén presionada la tecla Ctrl (Windows) o Cmd (Mac) para seleccionar varias opciones'}
          >
            {empresas.map(e => (
              <option key={e.id_empresa} value={e.id_empresa}>{e.nombre_comercial || e.nombre_legal}</option>
            ))}
          </select>
          <span style={{ fontSize: 12, color: '#888', marginTop: 2, display: 'block' }}>
            {'Mantén presionada la tecla Ctrl (Windows) o Cmd (Mac) para seleccionar varias opciones.'}
          </span>
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>
          Sucursales
          <div style={{ margin: '4px 0 4px 0', fontSize: 13, color: '#1976d2' }}>
            <b>Asignadas:</b> {sucursales.filter(s => form.sucursales.includes(String(s.id_sucursal))).map(s => s.nombre).join(', ') || <span style={{color:'#888'}}>Ninguna</span>}
          </div>
          <select
            multiple
            value={form.sucursales}
            onChange={e => setForm(f => ({ ...f, sucursales: Array.from(e.target.selectedOptions, opt => opt.value) }))}
            style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15, minHeight: 60 }}
            title={'Mantén presionada la tecla Ctrl (Windows) o Cmd (Mac) para seleccionar varias opciones'}
          >
            {sucursales.map(s => (
              <option key={s.id_sucursal} value={s.id_sucursal}>{s.nombre}</option>
            ))}
          </select>
          <span style={{ fontSize: 12, color: '#888', marginTop: 2, display: 'block' }}>
            {'Mantén presionada la tecla Ctrl (Windows) o Cmd (Mac) para seleccionar varias opciones.'}
          </span>
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>
          Departamentos
          <div style={{ margin: '4px 0 4px 0', fontSize: 13, color: '#1976d2' }}>
            <b>Asignados:</b> {departamentos.filter(d => form.departamentos.includes(String(d.id_departamento))).map(d => d.nombre_departamento).join(', ') || <span style={{color:'#888'}}>Ninguno</span>}
          </div>
          <select
            multiple
            value={form.departamentos}
            onChange={e => setForm(f => ({ ...f, departamentos: Array.from(e.target.selectedOptions, opt => opt.value) }))}
            style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15, minHeight: 60 }}
            title={'Mantén presionada la tecla Ctrl (Windows) o Cmd (Mac) para seleccionar varias opciones'}
          >
            {departamentos.map(d => (
              <option key={d.id_departamento} value={d.id_departamento}>{d.nombre_departamento}</option>
            ))}
          </select>
          <span style={{ fontSize: 12, color: '#888', marginTop: 2, display: 'block' }}>
            {'Mantén presionada la tecla Ctrl (Windows) o Cmd (Mac) para seleccionar varias opciones.'}
          </span>
        </label>
        <button
          type="button"
          style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 0', fontWeight: 600, fontSize: 16, marginTop: 10, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}
          onClick={async () => {
            if (!usuario) return;
            try {
              const { updateUsuario } = await import('../../../services/users');
              await updateUsuario(usuario.id, {
                first_name: form.first_name,
                last_name: form.last_name,
                email: form.email,
                empresas: form.empresas,
                sucursales: form.sucursales,
                departamentos: form.departamentos
              });
              // Volver a cargar los datos del usuario y sus asignaciones
              setLoading(true);
              let token = localStorage.getItem('token') || '';
              token = token.trim().replace(/^"|"$/g, '').replace(/\n/g, '');
              const headers: HeadersInit = {};
              if (token) {
                (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
              }
              function safeJsonFetch(url: string, options: RequestInit = {}): Promise<unknown> {
                return fetch(url, options).then(async r => {
                  const rawText = await r.text();
                  if (!r.ok) {
                    throw new Error(`Error en ${url}: status ${r.status} - ${rawText.slice(0, 100)}`);
                  }
                  try {
                    return JSON.parse(rawText);
                  } catch {
                    throw new Error(`Respuesta no es JSON en ${url}: ${rawText.slice(0, 100)}`);
                  }
                });
              }
              const [usuarios, usuarioRoles, empresasData, sucursalesData, departamentosData] = await Promise.all([
                fetchUsuarios(id_empresa),
                fetchUsuarioRoles(id || ''),
                safeJsonFetch('/api/core/empresas/', { headers }),
                safeJsonFetch('/api/core/sucursales/', { headers }),
                safeJsonFetch('/api/core/departamentos/', { headers })
              ]);
              const user = usuarios.find(u => u.id === id) || null;
              setUsuario(user);
              setUsuarioRoles(usuarioRoles);
              setEmpresas(empresasData as { id_empresa: string; nombre_legal: string; nombre_comercial?: string }[]);
              setSucursales(sucursalesData as { id_sucursal: string; nombre: string }[]);
              setDepartamentos(departamentosData as { id_departamento: string; nombre_departamento: string }[]);
              if (user) {
                setForm({
                  first_name: user.first_name,
                  last_name: user.last_name,
                  email: user.email,
                  empresas: user.empresas ? user.empresas.map(e => String(e.id_empresa)) : [],
                  sucursales: user.sucursales ? user.sucursales.map(s => String(s.id_sucursal)) : [],
                  departamentos: user.departamentos ? user.departamentos.map(d => String(d.id_departamento)) : []
                });
              }
              setLoading(false);
              alert('Usuario actualizado correctamente');
            } catch {
              setLoading(false);
              alert('Error al actualizar usuario');
            }
          }}
        >Guardar cambios</button>
      </form>
      <h4 style={{ marginTop: 32, color: '#1a237e', fontWeight: 600, fontSize: 18 }}>Roles asignados</h4>
      <ul style={{ margin: '12px 0 24px 0', padding: 0, listStyle: 'none', color: '#333', fontSize: 15 }}>
        {usuarioRoles.map(ur => (
          <li key={ur.id_usuario_rol} style={{ marginBottom: 4 }}>{ur.id_rol_nombre}</li>
        ))}
      </ul>
      <button
        style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '8px 24px', fontWeight: 500, fontSize: 15, marginBottom: 12, cursor: 'pointer' }}
        onClick={() => setShowChangePassword(s => !s)}
      >
        {showChangePassword ? 'Ocultar cambio de contraseña' : 'Cambiar contraseña'}
      </button>
      {showChangePassword && (
        <form
          style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'flex-start', width: '100%' }}
          onSubmit={async e => {
            e.preventDefault();
            setPasswordMessage('');
            if (!oldPassword) {
              setPasswordMessage('Debe ingresar la contraseña actual');
              return;
            }
            if (newPassword !== confirmPassword) {
              setPasswordMessage('Las contraseñas no coinciden');
              return;
            }
            if (!newPassword || newPassword.length < 6) {
              setPasswordMessage('La contraseña debe tener al menos 6 caracteres');
              return;
            }
            try {
              const { changeUserPassword } = await import('../../../services/users');
              await changeUserPassword(oldPassword, newPassword);
              setPasswordMessage('Contraseña actualizada correctamente');
              setOldPassword('');
              setNewPassword('');
              setConfirmPassword('');
            } catch (e) {
              let msg = 'Error al actualizar la contraseña';
              if (e instanceof Error) {
                try {
                  const errObj = JSON.parse(e.message);
                  msg = errObj.error || errObj.message || msg;
                } catch {
                  // No hacer nada, usar mensaje por defecto
                }
              }
              setPasswordMessage(msg);
            }
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
            <input
              type={showOldPassword ? 'text' : 'password'}
              placeholder="Contraseña actual"
              value={oldPassword}
              onChange={e => setOldPassword(e.target.value)}
              style={{ width: '50%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', fontSize: 15 }}
            />
            <button
              type="button"
              onClick={() => setShowOldPassword(v => !v)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#1976d2', fontWeight: 500 }}
              tabIndex={-1}
            >
              {showOldPassword ? 'Ocultar' : 'Ver'}
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
            <input
              type={showNewPassword ? 'text' : 'password'}
              placeholder="Nueva contraseña"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              style={{ width: '50%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', fontSize: 15 }}
            />
            <button
              type="button"
              onClick={() => setShowNewPassword(v => !v)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#1976d2', fontWeight: 500 }}
              tabIndex={-1}
            >
              {showNewPassword ? 'Ocultar' : 'Ver'}
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%' }}>
            <input
              type={showConfirmPassword ? 'text' : 'password'}
              placeholder="Confirmar contraseña"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              style={{ width: '50%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', fontSize: 15,
                borderColor: confirmPassword && newPassword !== confirmPassword ? '#d32f2f' : '#cfd8dc' }}
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword(v => !v)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#1976d2', fontWeight: 500 }}
              tabIndex={-1}
            >
              {showConfirmPassword ? 'Ocultar' : 'Ver'}
            </button>
          </div>
          {confirmPassword && newPassword !== confirmPassword && (
            <span style={{ color: '#d32f2f', fontSize: 13 }}>Las contraseñas no coinciden</span>
          )}
          {passwordMessage && (
            <span style={{ color: passwordMessage.includes('correctamente') ? '#388e3c' : '#d32f2f', fontSize: 13 }}>{passwordMessage}</span>
          )}
          <button
            type="submit"
            style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '8px 18px', fontWeight: 500, fontSize: 15, cursor: 'pointer' }}
          >Guardar nueva contraseña</button>
        </form>
      )}
    </PageLayout>
  );
};

export default UserDetailPage;
