import React from 'react';
import { Box, Button, Card, CardContent, Chip, Typography, Stack } from '@mui/material';
import { Business, Store, AccountCircle, Logout, SwitchAccount } from '@mui/icons-material';
import { getEmpresaId } from '../../../utils/empresa';
import SugerenciasWidget from '../../../components/SugerenciasWidget';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../../contexts/AuthContext';

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

  const handleLogout = () => { logout(); navigate('/login'); };
  const handleProfile = () => {
    const id_empresa = getEmpresaId();
    if (id_empresa) navigate(`/empresas/${id_empresa}/usuarios/${user.id}`);
  };
  const handleChangeEmpresaSucursal = () => { logout(); navigate('/login'); };

  const empresaNombre = empresa.nombre_legal || empresa.nombre_comercial || empresa.nombre || '—';

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 960, mx: 'auto' }}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3} flexWrap="wrap" gap={1}>
        <Box>
          <Typography variant="h5" color="primary">
            Bienvenido, {user.first_name} {user.last_name}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {empresaNombre} · {sucursal.nombre}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" size="small" startIcon={<AccountCircle />} onClick={handleProfile}>
            Perfil
          </Button>
          <Button variant="outlined" size="small" startIcon={<SwitchAccount />} onClick={handleChangeEmpresaSucursal}>
            Cambiar empresa
          </Button>
          <Button variant="contained" color="error" size="small" startIcon={<Logout />} onClick={handleLogout}>
            Salir
          </Button>
        </Stack>
      </Box>

      {/* Info cards */}
      <Box display="flex" gap={2} mb={3} flexWrap="wrap">
        <Card sx={{ flex: 1, minWidth: 180 }}>
          <CardContent>
            <Stack direction="row" spacing={1} alignItems="center" mb={0.5}>
              <Business fontSize="small" color="primary" />
              <Typography variant="caption" color="text.secondary" fontWeight={600}>EMPRESA</Typography>
            </Stack>
            <Typography variant="subtitle1">{empresaNombre}</Typography>
          </CardContent>
        </Card>
        <Card sx={{ flex: 1, minWidth: 180 }}>
          <CardContent>
            <Stack direction="row" spacing={1} alignItems="center" mb={0.5}>
              <Store fontSize="small" color="primary" />
              <Typography variant="caption" color="text.secondary" fontWeight={600}>SUCURSAL</Typography>
            </Stack>
            <Typography variant="subtitle1">{sucursal.nombre}</Typography>
          </CardContent>
        </Card>
        <Card sx={{ flex: 1, minWidth: 180 }}>
          <CardContent>
            <Typography variant="caption" color="text.secondary" fontWeight={600} display="block" mb={1}>ROLES</Typography>
            <Box display="flex" gap={0.5} flexWrap="wrap">
              {(user.roles || []).map(role => (
                <Chip key={role.id} label={role.name} size="small" color="primary" variant="outlined" />
              ))}
              {(!user.roles || user.roles.length === 0) && (
                <Typography variant="body2" color="text.secondary">Sin roles asignados</Typography>
              )}
            </Box>
          </CardContent>
        </Card>
      </Box>

      {/* Recent activity */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="subtitle1" mb={1.5}>Actividad reciente</Typography>
          {actividades.length === 0 ? (
            <Typography variant="body2" color="text.secondary">Sin actividad reciente.</Typography>
          ) : (
            <Stack spacing={1}>
              {actividades.map(act => (
                <Box key={act.id} display="flex" justifyContent="space-between">
                  <Typography variant="body2">{act.descripcion}</Typography>
                  <Typography variant="caption" color="text.secondary">{act.fecha}</Typography>
                </Box>
              ))}
            </Stack>
          )}
        </CardContent>
      </Card>

      {/* AI suggestions */}
      <Card>
        <CardContent>
          <SugerenciasWidget />
        </CardContent>
      </Card>
    </Box>
  );
};

export default DashboardUserPage;
