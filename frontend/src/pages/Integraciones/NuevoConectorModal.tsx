import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  FormGroup,
  IconButton,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import {
  getProveedores,
  crearConector,
  type ConectorProveedor,
} from '../../services/integrationHubService';

interface Props {
  onClose: () => void;
}

const NuevoConectorModal: React.FC<Props> = ({ onClose }) => {
  const qc = useQueryClient();
  const [paso, setPaso] = useState<1 | 2>(1);
  const [proveedor, setProveedor] = useState<ConectorProveedor | null>(null);
  const [form, setForm] = useState({
    nombre: '',
    host: '',
    db: '',
    user: '',
    api_key: '',
    timeout: 30,
    entidades_activas: [] as string[],
    intervalo_sync_minutos: 60,
  });
  const [error, setError] = useState('');

  const { data: provData } = useQuery({
    queryKey: ['/integration-hub/proveedores/'],
    queryFn: getProveedores,
  });
  const proveedores = provData?.results ?? [];

  const mutation = useMutation({
    mutationFn: () =>
      crearConector({
        id_proveedor: proveedor!.id_proveedor,
        nombre: form.nombre,
        entidades_activas: form.entidades_activas,
        intervalo_sync_minutos: form.intervalo_sync_minutos,
        configuracion: {
          host: form.host,
          db: form.db || undefined,
          user: form.user,
          api_key: form.api_key,
          timeout: form.timeout,
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['/integration-hub/instancias/'] });
      onClose();
    },
    onError: (e: Error) => {
      try {
        const parsed = JSON.parse(e.message);
        setError(JSON.stringify(parsed, null, 2));
      } catch {
        setError(e.message);
      }
    },
  });

  const toggleEntidad = (e: string) =>
    setForm(f => ({
      ...f,
      entidades_activas: f.entidades_activas.includes(e)
        ? f.entidades_activas.filter(x => x !== e)
        : [...f.entidades_activas, e],
    }));

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        {paso === 1 ? 'Seleccionar proveedor' : `Configurar conector — ${proveedor?.nombre}`}
        <IconButton onClick={onClose} edge="end"><CloseIcon /></IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {/* Paso 1 — Selección de proveedor */}
        {paso === 1 && (
          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.5 }}>
            {proveedores.map(p => (
              <Card key={p.id_proveedor} variant="outlined" sx={{ opacity: p.estado === 'activo' ? 1 : 0.5 }}>
                <CardActionArea
                  disabled={p.estado !== 'activo'}
                  onClick={() => { setProveedor(p); setPaso(2); }}
                  sx={{ p: 1.5 }}
                >
                  <Typography sx={{ fontWeight: 700 }}>{p.nombre}</Typography>
                  {p.estado !== 'activo' && (
                    <Typography variant="caption" color="text.secondary">Próximamente</Typography>
                  )}
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                    {p.capacidades.join(', ')}
                  </Typography>
                </CardActionArea>
              </Card>
            ))}
          </Box>
        )}

        {/* Paso 2 — Formulario de configuración */}
        {paso === 2 && proveedor && (
          <Stack spacing={2}>
            <TextField
              label="Nombre del conector"
              required
              placeholder="Mi Odoo Producción"
              value={form.nombre}
              onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))}
              fullWidth
            />
            <TextField
              label="URL del servidor"
              required
              placeholder="https://mi-empresa.odoo.com"
              value={form.host}
              onChange={e => setForm(f => ({ ...f, host: e.target.value }))}
              fullWidth
            />
            {proveedor.requiere_db && (
              <TextField
                label="Base de datos"
                placeholder="nombre_db"
                value={form.db}
                onChange={e => setForm(f => ({ ...f, db: e.target.value }))}
                fullWidth
              />
            )}
            <TextField
              label="Usuario / Email"
              required
              placeholder="admin@empresa.com"
              value={form.user}
              onChange={e => setForm(f => ({ ...f, user: e.target.value }))}
              fullWidth
            />
            <TextField
              label="API Key"
              required
              type="password"
              placeholder="••••••••••••••••"
              value={form.api_key}
              onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
              fullWidth
            />
            <Box>
              <Typography variant="body2" fontWeight={600} mb={0.5}>Entidades a sincronizar</Typography>
              <FormGroup row>
                {proveedor.capacidades.map(cap => (
                  <FormControlLabel
                    key={cap}
                    control={
                      <Checkbox
                        checked={form.entidades_activas.includes(cap)}
                        onChange={() => toggleEntidad(cap)}
                      />
                    }
                    label={cap}
                  />
                ))}
              </FormGroup>
            </Box>
            <TextField
              label="Intervalo de sync (minutos)"
              type="number"
              inputProps={{ min: 5, max: 1440 }}
              value={form.intervalo_sync_minutos}
              onChange={e => setForm(f => ({ ...f, intervalo_sync_minutos: Number(e.target.value) }))}
              fullWidth
            />
            {error && (
              <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{error}</Alert>
            )}
          </Stack>
        )}
      </DialogContent>
      {paso === 2 && proveedor && (
        <DialogActions>
          <Button variant="outlined" onClick={() => setPaso(1)}>Atrás</Button>
          <Button
            variant="contained"
            disabled={mutation.isPending || !form.nombre || !form.host || !form.user || !form.api_key}
            onClick={() => { setError(''); mutation.mutate(); }}
          >
            {mutation.isPending ? 'Guardando…' : 'Crear conector'}
          </Button>
        </DialogActions>
      )}
    </Dialog>
  );
};

export default NuevoConectorModal;
