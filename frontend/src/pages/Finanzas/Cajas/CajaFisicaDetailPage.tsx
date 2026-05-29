import React from 'react';
import PageLayout from '../../../components/PageLayout';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { cajasFisicasService, type CajaFisica } from '../../../services/cajasFisicasService';
import { Alert, Box, Button, Card, CardActions, CardContent, Chip, Divider, Paper, Typography } from '@mui/material';
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet';
import CreditCardIcon from '@mui/icons-material/CreditCard';

interface CajaVirtual {
  id_caja: string;
  nombre: string;
  tipo_caja: string;
  tipo_caja_display: string;
  descripcion?: string;
  moneda_codigo_iso: string;
  activa: boolean;
  empresa_nombre?: string;
  sucursal_nombre?: string;
  saldo_actual: number;
  fecha_creacion: string;
}

interface Datafono {
  id_datafono: string;
  nombre: string;
  serial: string;
  activo: boolean;
  saldo_actual: number;
  ultima_conexion?: string;
  empresa_nombre?: string;
  sucursal_nombre?: string;
  cuenta_bancaria_nombre?: string;
  fecha_creacion: string;
}

const CajaFisicaDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: cajaFisica, isLoading, isError } = useQuery<CajaFisica>({
    queryKey: ['/finanzas/cajas-fisicas/', id],
    queryFn: () => cajasFisicasService.getCajaFisica(id!),
    enabled: !!id,
  });

  const { data: cajasVirtuales = [] } = useQuery<CajaVirtual[]>({
    queryKey: ['/finanzas/cajas-fisicas/', id, 'cajas-virtuales'],
    queryFn: () => cajasFisicasService.getCajasVirtualesAsociadas(id!) as Promise<CajaVirtual[]>,
    enabled: !!id,
  });

  const { data: datafonos = [] } = useQuery<Datafono[]>({
    queryKey: ['/finanzas/cajas-fisicas/', id, 'datafonos'],
    queryFn: () => cajasFisicasService.getDatafonosAsociados(id!) as Promise<Datafono[]>,
    enabled: !!id,
  });

  const formatCurrency = (amount: number, currency: string = 'VES') => {
    return new Intl.NumberFormat('es-VE', {
      style: 'currency',
      currency: currency,
      minimumFractionDigits: 2
    }).format(amount);
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Nunca';
    return new Date(dateString).toLocaleString('es-VE');
  };

  if (isLoading) {
    return (
      <PageLayout>
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '200px' }}>
          <Typography>Cargando...</Typography>
        </Box>
      </PageLayout>
    );
  }

  if (isError || !cajaFisica) {
    return (
      <PageLayout>
        <Box sx={{ mb: 2 }}>
          <Button
            variant="outlined"
            onClick={() => navigate('/finanzas/cajas-fisicas')}
          >
            ← Volver al listado
          </Button>
        </Box>
        <Alert severity="error">
          {isError ? 'Error al cargar los detalles de la caja física' : 'Caja física no encontrada'}
        </Alert>
      </PageLayout>
    );
  }

  return (
    <PageLayout>
      <Box sx={{ mb: 3 }}>
        <Button
          variant="outlined"
          onClick={() => navigate('/finanzas/cajas-fisicas')}
          sx={{ mb: 2 }}
        >
          ← Volver al listado
        </Button>

        <Typography variant="h5" gutterBottom>
          Detalle de Caja Física
        </Typography>
      </Box>

      {/* Información General de la Caja */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <AccountBalanceWalletIcon />
          Información General
        </Typography>
        <Divider sx={{ mb: 2 }} />

        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 3 }}>
          <Box>
            <Typography variant="subtitle2" color="text.secondary">Nombre</Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>{cajaFisica.nombre}</Typography>

            <Typography variant="subtitle2" color="text.secondary">Tipo de Caja</Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>{cajaFisica.tipo_caja_display}</Typography>

            <Typography variant="subtitle2" color="text.secondary">Estado</Typography>
            <Chip
              label={cajaFisica.activa ? 'Activa' : 'Inactiva'}
              color={cajaFisica.activa ? 'success' : 'error'}
              size="small"
              sx={{ mb: 2 }}
            />
          </Box>

          <Box>
            <Typography variant="subtitle2" color="text.secondary">Empresa</Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>{cajaFisica.empresa_nombre}</Typography>

            <Typography variant="subtitle2" color="text.secondary">Sucursal</Typography>
            <Typography variant="body1" sx={{ mb: 2 }}>{cajaFisica.sucursal_nombre || 'No asignada'}</Typography>

            <Typography variant="subtitle2" color="text.secondary">Identificador de Dispositivo</Typography>
            <Typography variant="body1" sx={{ mb: 2, fontFamily: 'monospace' }}>
              {cajaFisica.identificador_dispositivo || 'No asignado'}
            </Typography>
          </Box>

          <Box sx={{ gridColumn: { xs: '1', md: '1 / -1' } }}>
            <Typography variant="subtitle2" color="text.secondary">Descripción</Typography>
            <Typography variant="body1">{cajaFisica.descripcion || 'Sin descripción'}</Typography>
          </Box>
        </Box>
      </Paper>

      {/* Cajas Virtuales Asociadas */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <AccountBalanceWalletIcon />
          Cajas Virtuales Asociadas
        </Typography>
        <Divider sx={{ mb: 2 }} />

        {cajasVirtuales.length === 0 ? (
          <Typography color="text.secondary">No hay cajas virtuales asociadas</Typography>
        ) : (
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
            {cajasVirtuales.map((caja) => (
              <Card key={caja.id_caja} variant="outlined">
                <CardContent>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                    <Typography variant="h6">{caja.nombre}</Typography>
                    <Chip
                      label={caja.activa ? 'Activa' : 'Inactiva'}
                      color={caja.activa ? 'success' : 'error'}
                      size="small"
                    />
                  </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Moneda: {caja.moneda_codigo_iso}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Tipo: {caja.tipo_caja_display}
                    </Typography>
                  <Typography variant="h5" color="primary">
                    {formatCurrency(caja.saldo_actual, caja.moneda_codigo_iso)}
                  </Typography>
                </CardContent>
                <CardActions>
                  <Button
                    onClick={() => navigate(`/cajas/${caja.id_caja}`)}
                  >
                    Ver Detalle
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={() => navigate(`/cajas/${caja.id_caja}/movimientos-caja-banco`)}
                  >
                    Ver Movimientos
                  </Button>
                </CardActions>
              </Card>
            ))}
          </Box>
        )}
      </Paper>

      {/* Datafonos Asociados */}
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <CreditCardIcon />
          Datafonos Asociados
        </Typography>
        <Divider sx={{ mb: 2 }} />

        {datafonos.length === 0 ? (
          <Typography color="text.secondary">No hay datafonos asociados</Typography>
        ) : (
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
            {datafonos.map((datafono) => (
              <Card key={datafono.id_datafono} variant="outlined">
                <CardContent>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                    <Typography variant="h6">{datafono.nombre}</Typography>
                    <Chip
                      label={datafono.activo ? 'Activo' : 'Inactivo'}
                      color={datafono.activo ? 'success' : 'error'}
                      size="small"
                    />
                  </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Serial: {datafono.serial}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Última conexión: {formatDate(datafono.ultima_conexion)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      Cuenta bancaria: {datafono.cuenta_bancaria_nombre || 'No asignada'}
                    </Typography>
                  <Typography variant="h5" color="primary">
                    {formatCurrency(datafono.saldo_actual)}
                  </Typography>
                </CardContent>
                <CardActions>
                  <Button
                    onClick={() => navigate(`/finanzas/datafonos/${datafono.id_datafono}`)}
                  >
                    Ver Detalle
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={() => navigate(`/finanzas/datafonos/${datafono.id_datafono}/movimientos`)}
                  >
                    Ver Movimientos
                  </Button>
                </CardActions>
              </Card>
            ))}
          </Box>
        )}
      </Paper>
    </PageLayout>
  );
};

export default CajaFisicaDetailPage;
