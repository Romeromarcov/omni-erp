import React, { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  FormGroup,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import {
  actualizarConector,
  type ConectorInstancia,
  type ConectorInstanciaUpdate,
} from '../../services/integrationHubService';

interface Props {
  conector: ConectorInstancia;
  onClose: () => void;
}

const PROVEEDOR_SHEETS = 'google_sheets';

const INTERVALOS = [
  { value: 0, label: 'Manual (sin sync automático)' },
  { value: 15, label: 'Cada 15 minutos' },
  { value: 30, label: 'Cada 30 minutos' },
  { value: 60, label: 'Cada hora' },
  { value: 360, label: 'Cada 6 horas' },
  { value: 1440, label: 'Diario' },
];

/**
 * Modal de edición de un conector existente. Para conectores tipo Odoo/API
 * permite cambiar host, base de datos, usuario y (opcionalmente) la API key.
 * La API key se deja en blanco para conservar la guardada (el backend nunca la
 * devuelve por seguridad). Para Google Sheets solo se editan nombre, entidades
 * e intervalo (las credenciales se gestionan recreando el conector).
 */
const EditarConectorModal: React.FC<Props> = ({ conector, onClose }) => {
  const qc = useQueryClient();
  const esSheets = conector.proveedor_codigo === PROVEEDOR_SHEETS;
  const cfg = conector.configuracion_publica ?? {};

  const [form, setForm] = useState({
    nombre: conector.nombre,
    host: cfg.host ?? '',
    db: cfg.db ?? '',
    user: cfg.user ?? '',
    api_key: '', // en blanco = conservar la actual
    entidades_activas: [...conector.entidades_activas],
    intervalo_sync_minutos: conector.intervalo_sync_minutos,
  });
  const [error, setError] = useState('');

  const mutation = useMutation({
    mutationFn: () => {
      const data: ConectorInstanciaUpdate = {
        nombre: form.nombre,
        entidades_activas: form.entidades_activas,
        intervalo_sync_minutos: form.intervalo_sync_minutos,
      };
      if (!esSheets) {
        const configuracion: ConectorInstanciaUpdate['configuracion'] = {
          host: form.host,
          db: form.db || undefined,
          user: form.user,
        };
        // Solo enviar api_key si el usuario escribió una nueva; en blanco se
        // conserva la existente (el backend ignora secretos vacíos).
        if (form.api_key.trim()) {
          (configuracion as { api_key?: string }).api_key = form.api_key;
        }
        data.configuracion = configuracion;
      }
      return actualizarConector(conector.id_conector, data);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [`/integration-hub/instancias/${conector.id_conector}/`] });
      qc.invalidateQueries({ queryKey: ['/integration-hub/instancias/'] });
      onClose();
    },
    onError: (e: Error) => {
      try {
        setError(JSON.stringify(JSON.parse(e.message), null, 2));
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

  const apiValido = esSheets ? !!form.nombre : !!form.nombre && !!form.host && !!form.user;

  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        Editar conector — {conector.proveedor_nombre}
        <IconButton onClick={onClose} edge="end"><CloseIcon /></IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <TextField
            label="Nombre del conector"
            required
            value={form.nombre}
            onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))}
            fullWidth
          />

          {!esSheets && (
            <>
              <TextField
                label="URL del servidor"
                required
                placeholder="https://mi-empresa.odoo.com"
                helperText="Solo el dominio base, sin /web/login ni rutas."
                value={form.host}
                onChange={e => setForm(f => ({ ...f, host: e.target.value }))}
                fullWidth
              />
              <TextField
                label="Base de datos (opcional)"
                placeholder="nombre_db"
                helperText="Opcional en Odoo SaaS (autodetecta). Requerido en Odoo.sh / on-premise."
                value={form.db}
                onChange={e => setForm(f => ({ ...f, db: e.target.value }))}
                fullWidth
              />
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
                type="password"
                placeholder="••••••••  (en blanco = conservar la actual)"
                helperText="Déjalo en blanco para mantener la credencial guardada."
                value={form.api_key}
                onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))}
                fullWidth
              />
            </>
          )}

          {esSheets && (
            <Alert severity="info">
              Las credenciales de Google Sheets no se editan aquí. Para cambiarlas,
              recrea el conector.
            </Alert>
          )}

          <Box>
            <Typography variant="body2" fontWeight={600} mb={0.5}>
              {esSheets ? 'Entidades a exportar' : 'Entidades a sincronizar'}
            </Typography>
            <FormGroup row>
              {conector.proveedor_capacidades.map(cap => (
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
            label="Intervalo de sync"
            select
            value={form.intervalo_sync_minutos}
            onChange={e => setForm(f => ({ ...f, intervalo_sync_minutos: Number(e.target.value) }))}
            fullWidth
          >
            {INTERVALOS.map(opt => (
              <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
            ))}
          </TextField>

          {error && <Alert severity="error" sx={{ whiteSpace: 'pre-wrap' }}>{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button variant="outlined" onClick={onClose}>Cancelar</Button>
        <Button
          variant="contained"
          disabled={mutation.isPending || !apiValido}
          onClick={() => { setError(''); mutation.mutate(); }}
        >
          {mutation.isPending ? 'Guardando…' : 'Guardar cambios'}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default EditarConectorModal;
