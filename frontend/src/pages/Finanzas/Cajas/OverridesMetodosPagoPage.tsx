import React, { useState } from 'react';
import PageLayout from '../../../components/PageLayout';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getOverridesMetodosPago, createOverrideMetodoPago, updateOverrideMetodoPago, deleteOverrideMetodoPago, type CajaMetodoPagoOverride } from '../../../services/plantillasService';
import { fetchMetodosPagoEmpresaActivos } from '../../../services/metodosPagoEmpresaActiva';
import { fetchSucursales } from '../../../services/sucursales';
import { useConfirm } from '../../../contexts/feedbackTypes';
import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, InputLabel, MenuItem, Paper, Select, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';

interface MetodoPago {
  id_metodo_pago: string;
  nombre: string;
}

interface Sucursal {
  id_sucursal: string;
  nombre: string;
}

const OverridesMetodosPagoPage: React.FC = () => {
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showDialog, setShowDialog] = useState(false);
  const [editingOverride, setEditingOverride] = useState<CajaMetodoPagoOverride | null>(null);

  const [form, setForm] = useState({
    id_sucursal: '',
    id_metodo_pago: '',
    deshabilitado: true,
  });

  const idEmpresa = localStorage.getItem('id_empresa') || '';

  const { data: overrides = [], isLoading } = useQuery<CajaMetodoPagoOverride[]>({
    queryKey: ['/finanzas/overrides-metodos-pago/', idEmpresa],
    queryFn: () => getOverridesMetodosPago(idEmpresa),
    enabled: !!idEmpresa,
  });

  const { data: metodosPago = [] } = useQuery<MetodoPago[]>({
    queryKey: ['/finanzas/metodos-pago-empresa-activas/', idEmpresa],
    queryFn: () => fetchMetodosPagoEmpresaActivos(idEmpresa) as unknown as Promise<MetodoPago[]>,
    enabled: !!idEmpresa,
  });

  const { data: sucursales = [] } = useQuery<Sucursal[]>({
    queryKey: ['/core/sucursales/', idEmpresa],
    queryFn: () => fetchSucursales(idEmpresa) as Promise<Sucursal[]>,
    enabled: !!idEmpresa,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteOverrideMetodoPago(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/finanzas/overrides-metodos-pago/', idEmpresa] });
      setSuccess('Override eliminado exitosamente');
    },
    onError: () => setError('Error al eliminar el override'),
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      if (editingOverride) {
        return updateOverrideMetodoPago(editingOverride.id_override, form);
      }
      return createOverrideMetodoPago(form);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/finanzas/overrides-metodos-pago/', idEmpresa] });
      setSuccess(editingOverride ? 'Override actualizado exitosamente' : 'Override creado exitosamente');
      setShowDialog(false);
    },
    onError: () => setError('Error al guardar el override'),
  });

  const handleCreate = () => {
    setEditingOverride(null);
    setForm({ id_sucursal: '', id_metodo_pago: '', deshabilitado: true });
    setShowDialog(true);
  };

  const handleEdit = (override: CajaMetodoPagoOverride) => {
    setEditingOverride(override);
    setForm({
      id_sucursal: override.id_sucursal,
      id_metodo_pago: override.id_metodo_pago,
      deshabilitado: override.deshabilitado,
    });
    setShowDialog(true);
  };

  const handleDelete = async (id: string) => {
    const ok = await confirm({
      title: 'Eliminar override',
      message: '¿Está seguro de que desea eliminar este override?',
      confirmText: 'Eliminar',
      destructive: true,
    });
    if (!ok) return;
    deleteMutation.mutate(id);
  };

  const handleSubmit = () => {
    if (!form.id_sucursal || !form.id_metodo_pago) {
      setError('Debe seleccionar sucursal y método de pago');
      return;
    }
    setError('');
    setSuccess('');
    saveMutation.mutate();
  };

  const getSucursalNombre = (idSucursal: string) => {
    const sucursal = sucursales.find(s => s.id_sucursal === idSucursal);
    return sucursal?.nombre || idSucursal;
  };

  const getMetodoPagoNombre = (idMetodoPago: string) => {
    const metodo = metodosPago.find(m => m.id_metodo_pago === idMetodoPago);
    return metodo?.nombre || idMetodoPago;
  };

  return (
    <PageLayout>
      <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h5">Overrides de Métodos de Pago por Sucursal</Typography>
        <Button variant="contained" onClick={handleCreate}>
          Nuevo Override
        </Button>
      </Box>

      <Alert severity="info" sx={{ mb: 2 }}>
        Los overrides permiten deshabilitar métodos de pago específicos en sucursales particulares,
        anulando las configuraciones de las plantillas maestras.
      </Alert>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

      <Paper variant="outlined" sx={{ p: 2 }}>
        {isLoading ? (
          <Typography>Cargando...</Typography>
        ) : overrides.length === 0 ? (
          <Typography>No hay overrides configurados</Typography>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Sucursal</TableCell>
                  <TableCell>Método de Pago</TableCell>
                  <TableCell>Estado</TableCell>
                  <TableCell>Fecha Creación</TableCell>
                  <TableCell>Acciones</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {overrides.map((override) => (
                  <TableRow key={override.id_override}>
                    <TableCell>{getSucursalNombre(override.id_sucursal)}</TableCell>
                    <TableCell>{getMetodoPagoNombre(override.id_metodo_pago)}</TableCell>
                    <TableCell>
                      <Chip
                        label={override.deshabilitado ? 'Deshabilitado' : 'Habilitado'}
                        color={override.deshabilitado ? 'error' : 'success'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>{new Date(override.fecha_creacion).toLocaleDateString()}</TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', gap: 1 }}>
                        <Button variant="outlined" onClick={() => handleEdit(override)}>Editar</Button>
                        <Button variant="outlined" onClick={() => handleDelete(override.id_override)}>Eliminar</Button>
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>

      <Dialog open={showDialog} onClose={() => setShowDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingOverride ? 'Editar Override' : 'Nuevo Override'}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
            <FormControl fullWidth>
              <InputLabel>Sucursal</InputLabel>
              <Select
                value={form.id_sucursal}
                onChange={(e) => setForm(prev => ({ ...prev, id_sucursal: e.target.value }))}
                label="Sucursal"
              >
                {sucursales.map((sucursal) => (
                  <MenuItem key={sucursal.id_sucursal} value={sucursal.id_sucursal}>
                    {sucursal.nombre}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl fullWidth>
              <InputLabel>Método de Pago</InputLabel>
              <Select
                value={form.id_metodo_pago}
                onChange={(e) => setForm(prev => ({ ...prev, id_metodo_pago: e.target.value }))}
                label="Método de Pago"
              >
                {metodosPago.map((metodo) => (
                  <MenuItem key={metodo.id_metodo_pago} value={metodo.id_metodo_pago}>
                    {metodo.nombre}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl fullWidth>
              <InputLabel>Estado</InputLabel>
              <Select
                value={form.deshabilitado ? 'deshabilitado' : 'habilitado'}
                onChange={(e) => setForm(prev => ({ ...prev, deshabilitado: e.target.value === 'deshabilitado' }))}
                label="Estado"
              >
                <MenuItem value="habilitado">Habilitado</MenuItem>
                <MenuItem value="deshabilitado">Deshabilitado</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button variant="outlined" onClick={() => setShowDialog(false)}>
            Cancelar
          </Button>
          <Button variant="contained" onClick={handleSubmit}>
            {editingOverride ? 'Actualizar' : 'Crear'}
          </Button>
        </DialogActions>
      </Dialog>
    </PageLayout>
  );
};

export default OverridesMetodosPagoPage;
