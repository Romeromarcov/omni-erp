import { useState } from 'react';
import { Box, Button, Card, CardContent, Typography, Chip, Grid2, TextField, MenuItem, Alert, CircularProgress, Stepper, Step, StepLabel, Table, TableBody, TableCell, TableHead, TableRow, TableContainer } from '@mui/material';
import { Add as AddIcon } from '@mui/icons-material';
import { post } from '../../services/api';
import { useAcuerdos } from '../../hooks/useCxC';
import { calcularCuotasPreview } from '../../utils/cuotasPreview';
import type { AcuerdoPago, CuotaPreview } from '../../types/cxc';

const PERIODICIDAD_OPTIONS = ['unico', 'semanal', 'quincenal', 'mensual'] as const;
const PERIODICIDAD_LABELS: Record<string, string> = {
  unico: 'Pago Único', semanal: 'Semanal', quincenal: 'Quincenal', mensual: 'Mensual',
};

const ESTADO_COLORS: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  vigente: 'success', cumplido: 'default', roto: 'error', cancelado: 'warning',
};

const CUOTA_ESTADO_COLORS: Record<string, string> = {
  pendiente: '#9e9e9e', pagado: '#4caf50', parcial: '#ff9800', vencido: '#f44336',
};

type WizardStep = 0 | 1 | 2;

interface AcuerdoForm {
  cliente_id: string;
  cliente_nombre: string;
  monto_total: string;
  periodicidad: typeof PERIODICIDAD_OPTIONS[number];
  plazo_total_dias: string;
  fecha_inicio: string;
  monto_cuota: string;
  porcentaje_abono: string;
  moneda_codigo: string;
  observaciones: string;
}

export default function AcuerdosPage() {
  const { data, loading, error, refresh } = useAcuerdos();
  const [step, setStep] = useState<WizardStep>(0);
  const [showWizard, setShowWizard] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [form, setForm] = useState<AcuerdoForm>({
    cliente_id: '', cliente_nombre: '', monto_total: '',
    periodicidad: 'mensual', plazo_total_dias: '90',
    fecha_inicio: new Date().toISOString().split('T')[0],
    monto_cuota: '', porcentaje_abono: '', moneda_codigo: 'USD', observaciones: '',
  });

  const previewCuotas: CuotaPreview[] = form.monto_total && parseFloat(form.monto_total) > 0
    ? calcularCuotasPreview({
        fechaInicio: form.fecha_inicio,
        plazoTotalDias: parseInt(form.plazo_total_dias) || 30,
        periodicidad: form.periodicidad,
        montoTotal: parseFloat(form.monto_total),
        montoCuota: form.monto_cuota ? parseFloat(form.monto_cuota) : undefined,
        porcentajeAbono: form.porcentaje_abono ? parseFloat(form.porcentaje_abono) : undefined,
      })
    : [];

  const handleCreate = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await post('/cobranza/acuerdos/', {
        ...form,
        monto_total: parseFloat(form.monto_total),
        plazo_total_dias: parseInt(form.plazo_total_dias),
        monto_cuota: form.monto_cuota ? parseFloat(form.monto_cuota) : null,
        porcentaje_abono: form.porcentaje_abono ? parseFloat(form.porcentaje_abono) : null,
      });
      setShowWizard(false);
      setStep(0);
      refresh();
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : 'Error');
    } finally {
      setSaving(false);
    }
  };

  const acuerdos = data?.results || [];

  return (
    <Box p={3}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h5" fontWeight="bold">Acuerdos de Pago</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setShowWizard(true)}>
          Nuevo Acuerdo
        </Button>
      </Box>

      {/* Wizard */}
      {showWizard && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Stepper activeStep={step} sx={{ mb: 3 }}>
              <Step><StepLabel>Datos Básicos</StepLabel></Step>
              <Step><StepLabel>Estructura de Pago</StepLabel></Step>
              <Step><StepLabel>Resumen y Confirmar</StepLabel></Step>
            </Stepper>

            {saveError && <Alert severity="error" sx={{ mb: 2 }}>{saveError}</Alert>}

            {step === 0 && (
              <Grid2 container spacing={2}>
                <Grid2 size={{ xs: 12, sm: 6 }}>
                  <TextField fullWidth label="ID Cliente" value={form.cliente_id} onChange={e => setForm(f => ({ ...f, cliente_id: e.target.value }))} />
                </Grid2>
                <Grid2 size={{ xs: 12, sm: 6 }}>
                  <TextField fullWidth label="Nombre Cliente" value={form.cliente_nombre} onChange={e => setForm(f => ({ ...f, cliente_nombre: e.target.value }))} />
                </Grid2>
                <Grid2 size={{ xs: 12, sm: 6 }}>
                  <TextField fullWidth label="Monto Total" type="number" value={form.monto_total} onChange={e => setForm(f => ({ ...f, monto_total: e.target.value }))} />
                </Grid2>
                <Grid2 size={{ xs: 12, sm: 6 }}>
                  <TextField fullWidth select label="Moneda" value={form.moneda_codigo} onChange={e => setForm(f => ({ ...f, moneda_codigo: e.target.value }))}>
                    <MenuItem value="USD">USD</MenuItem>
                    <MenuItem value="VES">VES</MenuItem>
                  </TextField>
                </Grid2>
                <Grid2 size={{ xs: 12 }}>
                  <Box display="flex" justifyContent="flex-end" gap={1}>
                    <Button onClick={() => setShowWizard(false)}>Cancelar</Button>
                    <Button variant="contained" onClick={() => setStep(1)} disabled={!form.cliente_id || !form.monto_total}>Siguiente</Button>
                  </Box>
                </Grid2>
              </Grid2>
            )}

            {step === 1 && (
              <Grid2 container spacing={2}>
                <Grid2 size={{ xs: 12, sm: 6 }}>
                  <TextField fullWidth select label="Periodicidad" value={form.periodicidad} onChange={e => setForm(f => ({ ...f, periodicidad: e.target.value as typeof PERIODICIDAD_OPTIONS[number] }))}>
                    {PERIODICIDAD_OPTIONS.map(p => <MenuItem key={p} value={p}>{PERIODICIDAD_LABELS[p]}</MenuItem>)}
                  </TextField>
                </Grid2>
                {form.periodicidad !== 'unico' && (
                  <Grid2 size={{ xs: 12, sm: 6 }}>
                    <TextField fullWidth label="Plazo Total (días)" type="number" value={form.plazo_total_dias} onChange={e => setForm(f => ({ ...f, plazo_total_dias: e.target.value }))} />
                  </Grid2>
                )}
                <Grid2 size={{ xs: 12, sm: 6 }}>
                  <TextField fullWidth type="date" label="Fecha Inicio" value={form.fecha_inicio} onChange={e => setForm(f => ({ ...f, fecha_inicio: e.target.value }))} InputLabelProps={{ shrink: true }} />
                </Grid2>
                {form.periodicidad !== 'unico' && (
                  <>
                    <Grid2 size={{ xs: 12, sm: 6 }}>
                      <TextField fullWidth label="Monto por Cuota (opcional)" type="number" value={form.monto_cuota} onChange={e => setForm(f => ({ ...f, monto_cuota: e.target.value, porcentaje_abono: '' }))} />
                    </Grid2>
                    <Grid2 size={{ xs: 12, sm: 6 }}>
                      <TextField fullWidth label="% por Cuota (opcional)" type="number" value={form.porcentaje_abono} onChange={e => setForm(f => ({ ...f, porcentaje_abono: e.target.value, monto_cuota: '' }))} />
                    </Grid2>
                  </>
                )}
                <Grid2 size={{ xs: 12 }}>
                  <Box display="flex" justifyContent="flex-end" gap={1}>
                    <Button onClick={() => setStep(0)}>Atrás</Button>
                    <Button variant="contained" onClick={() => setStep(2)}>Siguiente</Button>
                  </Box>
                </Grid2>
              </Grid2>
            )}

            {step === 2 && (
              <Box>
                <Typography variant="subtitle2" mb={2}>
                  Acuerdo: {form.cliente_nombre} — ${form.monto_total} {form.moneda_codigo} — {PERIODICIDAD_LABELS[form.periodicidad]}
                </Typography>
                <Typography variant="subtitle2" mb={1}>Preview de cuotas ({previewCuotas.length} cuotas):</Typography>
                <TableContainer sx={{ maxHeight: 300 }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        <TableCell>#</TableCell>
                        <TableCell>Fecha Vencimiento</TableCell>
                        <TableCell align="right">Monto</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {previewCuotas.map(c => (
                        <TableRow key={c.numero}>
                          <TableCell>{c.numero}</TableCell>
                          <TableCell>{c.fecha_vencimiento}</TableCell>
                          <TableCell align="right">${c.monto.toFixed(2)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
                <TextField fullWidth multiline rows={2} label="Observaciones" value={form.observaciones} onChange={e => setForm(f => ({ ...f, observaciones: e.target.value }))} sx={{ mt: 2 }} />
                <Box display="flex" justifyContent="flex-end" gap={1} mt={2}>
                  <Button onClick={() => setStep(1)}>Atrás</Button>
                  <Button variant="contained" color="success" onClick={handleCreate} disabled={saving}>
                    {saving ? <CircularProgress size={20} /> : 'Confirmar Acuerdo'}
                  </Button>
                </Box>
              </Box>
            )}
          </CardContent>
        </Card>
      )}

      {loading && <CircularProgress />}
      {error && <Alert severity="error">{error}</Alert>}

      {acuerdos.map((ac: AcuerdoPago) => (
        <Card key={ac.id} sx={{ mb: 2 }}>
          <CardContent>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
              <Typography fontWeight="bold">{ac.cliente_nombre}</Typography>
              <Chip label={ac.estado} size="small" color={ESTADO_COLORS[ac.estado] || 'default'} />
            </Box>
            <Typography variant="body2" color="text.secondary">
              ${parseFloat(ac.monto_total).toFixed(2)} {ac.moneda_codigo} — {PERIODICIDAD_LABELS[ac.periodicidad]} — desde {ac.fecha_inicio}
            </Typography>
            {/* Timeline de cuotas */}
            {ac.cuotas && ac.cuotas.length > 0 && (
              <Box display="flex" gap={0.5} mt={1} flexWrap="wrap">
                {ac.cuotas.map(c => (
                  <Box
                    key={c.id}
                    sx={{
                      width: 12, height: 12, borderRadius: '50%',
                      bgcolor: CUOTA_ESTADO_COLORS[c.estado] || '#9e9e9e',
                    }}
                    title={`Cuota ${c.numero_cuota}: ${c.estado} — $${c.monto}`}
                  />
                ))}
              </Box>
            )}
          </CardContent>
        </Card>
      ))}
    </Box>
  );
}
