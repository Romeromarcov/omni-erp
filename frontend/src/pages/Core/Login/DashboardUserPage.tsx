import React from 'react';
import { getEmpresaId } from '../../../utils/empresa';
import { DashboardCard } from '../../../components/DashboardCard';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../../contexts/AuthContext';
import { Paper } from '@mui/material';

interface DashboardPageProps {
  user: {
    id: number;
    first_name: string;
    last_name: string;
    roles: { id: number; name: string }[];
  };
  empresa: { nombre?: string; nombre_legal?: string; nombre_comercial?: string };
  sucursal: { nombre: string };
  actividades: { id: number; descripcion: string; fecha: string }[];
}

const DashboardUserPage: React.FC<DashboardPageProps> = ({ user, empresa, sucursal, actividades }) => {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const handleLogout = () => {
    logout();
    navigate('/login');
  };
  const handleProfile = () => {
    const id_empresa = getEmpresaId();
    if (id_empresa) {
      navigate(`/empresas/${id_empresa}/usuarios/${user.id}`);
    }
  };
  const handleChangeEmpresaSucursal = () => {
    logout();
    navigate('/login');
  };
  return (
    <div className="vertical-center">
      <div className="centered-container" style={{ background: 'linear-gradient(135deg, #e3f0ff 0%, #f6fafd 100%)', padding: '24px 0' }}>
        <div style={{
          width: '100%',
          maxWidth: 900,
          background: '#fff',
          borderRadius: 16,
          boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
          padding: '32px 24px',
          margin: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 24
        }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginBottom: 8 }}>
            <button onClick={handleProfile} style={{ padding: '8px 16px', borderRadius: 6, background: '#1976d2', color: '#fff', border: 'none', cursor: 'pointer' }}>Perfil</button>
            <button onClick={handleChangeEmpresaSucursal} style={{ padding: '8px 16px', borderRadius: 6, background: '#e3f0ff', color: '#1976d2', border: 'none', cursor: 'pointer' }}>Cambiar empresa/sucursal</button>
            <button onClick={handleLogout} style={{ padding: '8px 16px', borderRadius: 6, background: '#d32f2f', color: '#fff', border: 'none', cursor: 'pointer' }}>Cerrar sesión</button>
          </div>
          <h2 style={{ textAlign: 'center', marginBottom: 8, color: '#1976d2' }}>
            Bienvenido, {user.first_name} {user.last_name}
          </h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginBottom: 24 }}>
            <DashboardCard title="Empresa" value={empresa.nombre_legal || empresa.nombre || ''} />
            <DashboardCard title="Sucursal" value={sucursal.nombre} />
            <Paper sx={{ p: 2 }}>
              <h4>Roles asignados</h4>
              <ul style={{ paddingLeft: 0, margin: 0 }}>
                {(user.roles || []).map((role) => (
                  <li key={role.id} style={{ listStyle: 'none', marginBottom: 4 }}>
                    <span style={{ background: '#e3f0ff', borderRadius: 4, padding: '2px 8px' }}>{role.name}</span>
                  </li>
                ))}
              </ul>
            </Paper>
          </div>
          <Paper sx={{ p: 2 }}>
            <h4>Actividades recientes</h4>
            <ul style={{ paddingLeft: 0, margin: 0 }}>
              {actividades.map((act) => (
                <li key={act.id} style={{ listStyle: 'none', marginBottom: 4 }}>
                  <span style={{ color: '#1976d2', fontWeight: 500 }}>{act.descripcion}</span> - {act.fecha}
                </li>
              ))}
            </ul>
          </Paper>
          <Paper sx={{ p: 2 }}>
            <h4>Módulos y páginas</h4>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {/* Aquí puedes agregar enlaces a otros módulos */}
              <button style={{ padding: '8px 16px', borderRadius: 6, background: '#e3f0ff', color: '#1976d2', border: 'none', cursor: 'pointer' }} disabled>Ventas</button>
              <button style={{ padding: '8px 16px', borderRadius: 6, background: '#e3f0ff', color: '#1976d2', border: 'none', cursor: 'pointer' }} disabled>Compras</button>
              <button style={{ padding: '8px 16px', borderRadius: 6, background: '#e3f0ff', color: '#1976d2', border: 'none', cursor: 'pointer' }} disabled>Inventario</button>
              {/* Agrega más módulos aquí */}
            </div>
          </Paper>
        </div>
      </div>
    </div>
  );
};
export default DashboardUserPage;

