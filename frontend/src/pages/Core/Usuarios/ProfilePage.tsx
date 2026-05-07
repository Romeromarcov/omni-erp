import React, { useState } from 'react';
// import './usuarios.css';
import ProfileForm from '../../../components/ProfileForm';
import RoleList from '../../../components/RoleList';

type Role = { id: number; name: string };
type User = {
  first_name: string;
  last_name: string;
  email: string;
  id_sucursal_predeterminada: string;
  roles: Role[];
};

interface ProfilePageProps {
  user: User;
  onUpdate: (values: {
    first_name: string;
    last_name: string;
    email: string;
    id_sucursal_predeterminada: string;
  }) => void;
}

const ProfilePage: React.FC<ProfilePageProps> = ({ user, onUpdate }) => {
  const [showChangePassword, setShowChangePassword] = useState(false);
  const cardStyle: React.CSSProperties = {
    width: '100%',
    maxWidth: 500,
    background: '#fff',
    borderRadius: 16,
    boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
    padding: '32px 24px',
    margin: '16px',
    display: 'flex',
    flexDirection: 'column',
    gap: 24,
  };
  return (
    <div className="vertical-center">
      <div className="centered-container" style={{ background: 'linear-gradient(135deg, #e3f0ff 0%, #f6fafd 100%)', padding: '24px 0' }}>
        <div style={cardStyle}>
          <h2 style={{ textAlign: 'center', marginBottom: 8, color: '#1976d2' }}>Perfil de usuario</h2>
          <ProfileForm
            initialValues={{
              first_name: user.first_name,
              last_name: user.last_name,
              email: user.email,
              id_sucursal_predeterminada: user.id_sucursal_predeterminada,
            }}
            onSubmit={onUpdate}
          />
          <h4 style={{ marginTop: 16 }}>Roles asignados</h4>
          <RoleList roles={user.roles} />
          <button style={{ marginTop: 16, alignSelf: 'center', background: '#1976d2', color: '#fff', borderRadius: 8, padding: '8px 16px', border: 'none' }} onClick={() => setShowChangePassword(s => !s)}>
            {showChangePassword ? 'Ocultar cambio de contraseña' : 'Cambiar contraseña'}
          </button>
          {showChangePassword && (
            <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {/* Aquí iría el formulario de cambio de contraseña */}
              <input type="password" placeholder="Nueva contraseña" style={{ padding: 8, borderRadius: 6, border: '1px solid #ccc' }} />
              <button style={{ background: '#1976d2', color: '#fff', borderRadius: 8, padding: '8px 16px', border: 'none' }}>Guardar nueva contraseña</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProfilePage;