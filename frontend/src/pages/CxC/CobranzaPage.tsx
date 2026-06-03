import { useState } from 'react';
import { Box, Button, Card, CardContent, Typography, Grid, TextField, MenuItem, Alert, CircularProgress, Paper } from '@mui/material';
import { Add as AddIcon } from '@mui/icons-material';
import { post } from '../../services/api';
import { useApiQuery } from '../../hooks/useApiQuery';
import type { GestionCobranza } from '../../types/cxc';
import { PageContainer, PageHeader, StatusChip } from '../../components/ui';

const CANAL_OPTIONS = ['whatsapp', 'email', 'llamada', 'visita', 'carta'];
const RESULTADO_OPTIONS = ['contactado', 'sin_respuesta', 'promesa_pago', 'negativa', 'acuerdo_logrado'];

const RESULTADO_LABELS: Record<string, string> = {
  contactado: 'Contactado',
  sin_respuesta: 'Sin Respuesta',
  promesa_pago: 'Promesa de Pago',
  negativa: 'Negativa',
  acuerdo_logrado: 'Acuerdo Logrado',
};

export default function CobranzaPage() {
  const { data, isLoading: loading, error } = useApiQuery<{ results: GestionCobranza[] }>('/cobranza/gestiones/');
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [form, setForm] = useState({
    cliente_id: '', cliente_nombre: '', orden_ref: '',
    canal: 'llamada', resultado: 'contactado',
    notas: '', fecha_gestion: new Date().toISOString().split('T')[0],
    proxima_accion: '',
  });

  const handleSubmit = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await post('/cobranza/gestiones/', {
        ...form,
        proxima_accion: form.proxima_accion || null,
      });
      setShowForm(false);
      window.location.reload();
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : 'Error al guardar');
    } finally {
      setSaving(false);
    }
  };

  return (
    <PageContainer>
      <PageHeader
        title="Gestiones de Cobranza"
        subtitle="Registro y seguimiento de gestiones de cobro"
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setShowForm(!showForm)}>
            Nueva Gestión
          </Button>
        }
      />

      {showForm && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="subtitle1" fontWeight="bold" mb={2}>Registrar Gestión</Typography>
            {saveError && <Alert severity="error" sx={{ mb: 2 }}>{saveError}</Alert>}
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField fullWidth label="ID Cliente" value={form.cliente_id} onChange={e => setForm(f => ({ ...f, cliente_id: e.target.value }))} />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField fullWidth label="Nombre Cliente" value={form.cliente_nombre} onChange={e => setForm(f => ({ ...f, cliente_nombre: e.target.value }))} />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField fullWidth label="Ref. Orden/Factura" value={form.orden_ref} onChange={e => setForm(f => ({ ...f, orden_ref: e.target.value }))} />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField fullWidth select label="Canal" value={form.canal} onChange={e => setForm(f => ({ ...f, canal: e.target.value }))}>
                  {CANAL_OPTIONS.map(c => <MenuItem key={c} value={c}>{c.charAt(0).toUpperCase() + c.slice(1)}</MenuItem>)}
                </TextField>
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField fullWidth select label="Resultado" value={form.resultado} onChange={e => setForm(f => ({ ...f, resultado: e.target.value }))}>
                  {RESULTADO_OPTIONS.map(r => <MenuItem key={r} value={r}>{RESULTADO_LABELS[r]}</MenuItem>)}
                </TextField>
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <TextField fullWidth type="date" label="Fecha Gestión" value={form.fecha_gestion} onChange={e => setForm(f => ({ ...f, fecha_gestion: e.target.value }))} InputLabelProps={{ shrink: true }} />
              </Grid>
              {form.resultado === 'promesa_pago' && (
                <Grid size={{ xs: 12, sm: 6 }}>
                  <TextField fullWidth type="date" label="Próxima Acción" value={form.proxima_accion} onChange={e => setForm(f => ({ ...f, proxima_accion: e.target.value }))} InputLabelProps={{ shrink: true }} />
                </Grid>
              )}
              <Grid size={{ xs: 12 }}>
                <TextField fullWidth multiline rows={3} label="Notas" value={form.notas} onChange={e => setForm(f => ({ ...f, notas: e.target.value }))} />
              </Grid>
              <Grid size={{ xs: 12 }}>
                <Button variant="contained" onClick={handleSubmit} disabled={saving}>
                  {saving ? <CircularProgress size={20} /> : 'Guardar Gestión'}
                </Button>
                <Button sx={{ ml: 1 }} onClick={() => setShowForm(false)}>Cancelar</Button>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      )}

      {loading && <CircularProgress />}
      {error && <Alert severity="error">{error.message}</Alert>}

      {data?.results?.map(g => (
        <Paper key={g.id} sx={{ p: 2, mb: 1 }}>
          <Box display="flex" justifyContent="space-between" alignItems="flex-start">
            <Box>
              <Typography fontWeight="bold">{g.cliente_nombre}</Typography>
              <Typography variant="body2" color="text.secondary">
                {g.canal} — {g.fecha_gestion}
                {g.orden_ref && ` — ${g.orden_ref}`}
              </Typography>
              {g.notas && <Typography variant="body2" mt={0.5}>{g.notas}</Typography>}
            </Box>
            <Box textAlign="right">
              <StatusChip value={g.resultado} label={RESULTADO_LABELS[g.resultado] || g.resultado} colorMap={{ contactado: 'success', acuerdo_logrado: 'success', promesa_pago: 'info', sin_respuesta: 'warning', negativa: 'error' }} />
              {g.proxima_accion && (
                <Typography variant="caption" display="block" color="text.secondary" mt={0.5}>
                  Próxima: {g.proxima_accion}
                </Typography>
              )}
            </Box>
          </Box>
        </Paper>
      ))}
    </PageContainer>
  );
}
