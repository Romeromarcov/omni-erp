import React, { useState } from 'react';
import { Button, Stack, TextField } from '@mui/material';
import ProfileForm from '../../../components/ProfileForm';
import RoleList from '../../../components/RoleList';
import PageLayout from '../../../components/PageLayout';
import { PageHeader, SectionTitle } from '../../../components/ui';

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
  return (
    <PageLayout maxWidth={500}>
      <PageHeader
        title="Perfil de usuario"
        subtitle={`${user.first_name} ${user.last_name}`.trim() || undefined}
      />
      <Stack spacing={3}>
        <ProfileForm
          initialValues={{
            first_name: user.first_name,
            last_name: user.last_name,
            email: user.email,
            id_sucursal_predeterminada: user.id_sucursal_predeterminada,
          }}
          onSubmit={onUpdate}
        />
        <SectionTitle>Roles asignados</SectionTitle>
        <RoleList roles={user.roles} />
        <Button variant="contained" sx={{ alignSelf: 'center' }} onClick={() => setShowChangePassword(s => !s)}>
          {showChangePassword ? 'Ocultar cambio de contraseña' : 'Cambiar contraseña'}
        </Button>
        {showChangePassword && (
          <Stack spacing={2}>
            {/* Aquí iría el formulario de cambio de contraseña */}
            <TextField type="password" label="Nueva contraseña" fullWidth />
            <Button variant="contained">Guardar nueva contraseña</Button>
          </Stack>
        )}
      </Stack>
    </PageLayout>
  );
};

export default ProfilePage;
