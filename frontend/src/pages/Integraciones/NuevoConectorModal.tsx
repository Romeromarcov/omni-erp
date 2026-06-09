import React, { useMemo, useState } from 'react';
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
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import {
  getProveedores,
  getConectores,
  crearConector,
  type ConectorProveedor,
  type ConectorInstanciaCreate,
} from '../../services/integrationHubService';
import { parseServiceAccount } from './serviceAccount';

interface Props {
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

const NuevoConectorModal: React.FC<Props> = ({ onClose }) => {
  const qc = useQueryClient();
  const [paso, setPaso] = useState<1 | 2>(1);
  const [proveedor, setProveedor] = useState<ConectorProveedor | null>(null);
  const [form, setForm] = useState({
    nombre: '',
    // Odoo / API
    host: '',
    db: '',
    user: '',
    api_key: '',
    timeout: 30,
    // Google Sheets
    service_account_raw: '',
    source_instancia_id: '',
    drive_folder_id: '',
    spreadsheet_id: '',
    titulo: '',
    // comunes
    entidades_activas: [] as string[],
    intervalo_sync_minutos: 60,
  });
  const [error, setError] = useState('');

  const { data: provData } = useQuery({
    queryKey: ['/integration-hub/proveedores/'],
    queryFn: getProveedores,
  });
  const proveedores = provData?.results ?? [];

  // Instancias existentes — para poblar el selector de origen del conector Sheets.
  const { data: instanciasData } = useQuery({
    queryKey: ['/integration-hub/instancias/'],
    queryFn: getConectores,
  });
  const esSheets = proveedor?.codigo === PROVEEDOR_SHEETS;
  const instanciasOrigen = useMemo(
    () => (instanciasData?.results ?? []).filter(i => i.proveedor_codigo !== PROVEEDOR_SHEETS),
    [instanciasData],
  );

  const mutation = useMutation({
    mutationFn: () => {
      let configuracion: ConectorInstanciaCreate['configuracion'];
      if (esSheets) {
        const parsed = parseServiceAccount(form.service_account_raw);
        if (!parsed.ok) throw new Error(parsed.error);
        configuracion = {
          service_account: parsed.value,
          source_instancia_id: form.source_instancia_id,
          drive_folder_id: form.drive_folder_id || undefined,
          spreadsheet_id: form.spreadsheet_id || undefined,
          titulo: form.titulo || undefined,
        };
      } else {
        configuracion = {
          host: form.host,
          db: form.db || undefined,
          user: form.user,
          api_key: form.api_key,
          timeout: form.timeout,
        };
      }
      return crearConector({
        id_proveedor: proveedor!.id_proveedor,
        nombre: form.nombre,
        entidades_activas: form.entidades_activas,
        intervalo_sync_minutos: form.intervalo_sync_minutos,
        configuracion,
      });
    },
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

  // Validez del botón "Crear" según el tipo de conector.
  const sheetsValido =
    !!form.nombre &&
    !!form.service_account_raw.trim() &&
    !!form.source_instancia_id;
  const apiValido = !!form.nombre && !!form.host && !!form.user && !!form.api_key;
  const puedeCrear = esSheets ? sheetsValido : apiValido;

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
              placeholder={esSheets ? 'Export a Google Sheets' : 'Mi Odoo Producción'}
              value={form.nombre}
              onChange={e => setForm(f => ({ ...f, nombre: e.target.value }))}
              fullWidth
            />

            {/* ── Google Sheets ─────────────────────────────────────────────── */}
            {esSheets ? (
              <>
                <Alert severity="info">
                  Este conector <strong>exporta</strong> los datos de otro conector (p. ej.
                  Odoo) a una planilla de Google Sheets, una pestaña por entidad.
                </Alert>
                <TextField
                  label="Conector de origen"
                  required
                  select
                  helperText={
                    instanciasOrigen.length === 0
                      ? 'Crea primero un conector de origen (p. ej. Odoo) para poder exportar.'
                      : 'Los datos a exportar provienen de este conector.'
                  }
                  value={form.source_instancia_id}
                  onChange={e => setForm(f => ({ ...f, source_instancia_id: e.target.value }))}
                  fullWidth
                >
                  {instanciasOrigen.map(i => (
                    <MenuItem key={i.id_conector} value={i.id_conector}>
                      {i.nombre} — {i.proveedor_nombre}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  label="Service Account JSON"
                  required
                  multiline
                  minRows={4}
                  placeholder='{ "type": "service_account", "project_id": "…", … }'
                  helperText="Pega el JSON de la cuenta de servicio de Google. Se guarda cifrado y no se vuelve a mostrar."
                  value={form.service_account_raw}
                  onChange={e => setForm(f => ({ ...f, service_account_raw: e.target.value }))}
                  fullWidth
                />
                <TextField
                  label="ID de carpeta de Drive (opcional)"
                  placeholder="1A2b3C…"
                  helperText="Carpeta donde se creará la planilla si no existe."
                  value={form.drive_folder_id}
                  onChange={e => setForm(f => ({ ...f, drive_folder_id: e.target.value }))}
                  fullWidth
                />
                <TextField
                  label="ID de planilla existente (opcional)"
                  placeholder="abc123…"
                  helperText="Si ya tienes una planilla, pega su ID para escribir en ella."
                  value={form.spreadsheet_id}
                  onChange={e => setForm(f => ({ ...f, spreadsheet_id: e.target.value }))}
                  fullWidth
                />
                <TextField
                  label="Título de la planilla (opcional)"
                  placeholder="Omni Export"
                  value={form.titulo}
                  onChange={e => setForm(f => ({ ...f, titulo: e.target.value }))}
                  fullWidth
                />
              </>
            ) : (
              /* ── Odoo / API ──────────────────────────────────────────────── */
              <>
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
              </>
            )}

            <Box>
              <Typography variant="body2" fontWeight={600} mb={0.5}>
                {esSheets ? 'Entidades a exportar' : 'Entidades a sincronizar'}
              </Typography>
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
            disabled={mutation.isPending || !puedeCrear}
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
