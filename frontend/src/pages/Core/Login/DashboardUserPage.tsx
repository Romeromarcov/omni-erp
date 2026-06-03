import React from 'react';
import { Box, Button, Card, Chip, Typography, Stack } from '@mui/material';
import BusinessOutlined from '@mui/icons-material/BusinessOutlined';
import StorefrontOutlined from '@mui/icons-material/StorefrontOutlined';
import AccountCircleOutlined from '@mui/icons-material/AccountCircleOutlined';
import LogoutOutlined from '@mui/icons-material/LogoutOutlined';
import SwitchAccountOutlined from '@mui/icons-material/SwitchAccountOutlined';
import { getEmpresaId } from '../../../utils/empresa';
import SugerenciasWidget from '../../../components/SugerenciasWidget';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../../contexts/AuthContext';
import { PageContainer, BrandMark, KpiCard, SectionTitle } from '../../../components/ui';

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
    <PageContainer maxWidth={1100}>
      {/* Cabecera con saludo + acciones */}
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: { xs: 'flex-start', sm: 'center' },
          flexDirection: { xs: 'column', sm: 'row' },
          gap: 1.5,
          mb: 3,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <BrandMark size={34} />
          <Box>
            <Typography variant="h5">
              Bienvenido, {user.first_name} {user.last_name}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {empresaNombre} · {sucursal.nombre}
            </Typography>
          </Box>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" size="small" startIcon={<AccountCircleOutlined />} onClick={handleProfile}>
            Perfil
          </Button>
          <Button variant="outlined" size="small" startIcon={<SwitchAccountOutlined />} onClick={handleChangeEmpresaSucursal}>
            Cambiar empresa
          </Button>
          <Button variant="contained" color="error" size="small" startIcon={<LogoutOutlined />} onClick={handleLogout}>
            Salir
          </Button>
        </Stack>
      </Box>

      {/* Tarjetas de contexto */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' },
          gap: 2,
          mb: 3,
        }}
      >
        <KpiCard label="Empresa" value={empresaNombre} icon={<BusinessOutlined />} tone="brand" />
        <KpiCard label="Sucursal" value={sucursal.nombre || '—'} icon={<StorefrontOutlined />} tone="tint" />
        <Card sx={{ p: 2 }}>
          <Typography
            sx={{ fontWeight: 700, fontSize: 10, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'text.secondary', mb: 1 }}
          >
            Roles
          </Typography>
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {(user.roles || []).map((role) => (
              <Chip key={role.id} label={role.name} size="small" color="primary" variant="outlined" />
            ))}
            {(!user.roles || user.roles.length === 0) && (
              <Typography variant="body2" color="text.secondary">Sin roles asignados</Typography>
            )}
          </Box>
        </Card>
      </Box>

      {/* Actividad reciente */}
      <Card sx={{ p: 2.5, mb: 3 }}>
        <SectionTitle>Actividad reciente</SectionTitle>
        {actividades.length === 0 ? (
          <Typography variant="body2" color="text.secondary">Sin actividad reciente.</Typography>
        ) : (
          <Stack>
            {actividades.map((act, i) => (
              <Box
                key={act.id}
                sx={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  py: 1.25,
                  borderTop: i ? '1px solid' : 'none',
                  borderColor: 'divider',
                }}
              >
                <Typography variant="body2">{act.descripcion}</Typography>
                <Typography variant="caption" color="text.secondary">{act.fecha}</Typography>
              </Box>
            ))}
          </Stack>
        )}
      </Card>

      {/* Sugerencias IA */}
      <Card sx={{ p: 2.5 }}>
        <SugerenciasWidget />
      </Card>
    </PageContainer>
  );
};

export default DashboardUserPage;
