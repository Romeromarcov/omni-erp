import React, { useState } from 'react';
import { Box, Button, Stack, TextField, Typography } from '@mui/material';
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
  return (
    <Box sx={{ p: { xs: 2, md: 3 }, display: 'flex', justifyContent: 'center' }}>
      <Box
        sx={{
          width: '100%',
          maxWidth: 500,
          bgcolor: 'background.paper',
          borderRadius: 2,
          boxShadow: 3,
          p: { xs: 3, md: 4 },
          m: 2,
        }}
      >
        <Stack spacing={3}>
          <Typography variant="h5" align="center">Perfil de usuario</Typography>
          <ProfileForm
            initialValues={{
              first_name: user.first_name,
              last_name: user.last_name,
              email: user.email,
              id_sucursal_predeterminada: user.id_sucursal_predeterminada,
            }}
            onSubmit={onUpdate}
          />
          <Typography variant="h6">Roles asignados</Typography>
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
      </Box>
    </Box>
  );
};

export default ProfilePage;
