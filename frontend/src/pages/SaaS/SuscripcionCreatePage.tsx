import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Box, Button, Card, FormControlLabel, MenuItem, Stack, Switch, TextField,
} from '@mui/material';
import { PageContainer, PageHeader } from '../../components/ui';
import {
  fetchPlanes, createSuscripcion,
  SUSCRIPCION_ESTADOS, SUSCRIPCION_PERIODOS,
  type SuscripcionPayload,
} from '../../services/saasService';
import { fetchEmpresas } from '../../services/empresas';

// Acepta enteros/decimales con punto, hasta 2 decimales. Rechaza negativos.
// eslint-disable-next-line security/detect-unsafe-regex -- FP del heurístico star-height de safe-regex: `\.` y `\d` son disjuntos, no hay backtracking ambiguo (matching lineal)
const DECIMAL_RE = /^\d+(\.\d{1,2})?$/;

// fecha_fin por defecto: hoy + 30 días (trial estándar). Evita Date.now en SSR
// usando el reloj del navegador, que aquí es correcto.
function hoyMas(dias: number): string {
  const d = new Date();
  d.setDate(d.getDate() + dias);
  return d.toISOString().slice(0, 10);
}

const SuscripcionCreatePage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState('');

  const { data: empresas = [] } = useQuery({ queryKey: ['empresas', 'visible'], queryFn: fetchEmpresas });
  const { data: planes = [] } = useQuery({ queryKey: ['saas/planes', false], queryFn: () => fetchPlanes(false) });

  const [form, setForm] = useState<SuscripcionPayload>({
    id_empresa: searchParams.get('empresa') ?? '',
    id_plan: '',
    estado: 'TRIAL',
    periodo: 'MENSUAL',
    fecha_inicio: hoyMas(0),
    fecha_fin: hoyMas(30),
    renovacion_automatica: true,
    monto_pagado: '0',
    referencia_pago: '',
    notas: '',
  });

  const set = <K extends keyof SuscripcionPayload>(key: K, value: SuscripcionPayload[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const mutation = useMutation({
    mutationFn: (data: SuscripcionPayload) => createSuscripcion(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saas/suscripciones'] });
      navigate('/admin-saas/suscripciones');
    },
    onError: (e: Error) => setError(e.message || 'No se pudo crear la suscripción.'),
  });

  const validate = (): string | null => {
    if (!form.id_empresa) return 'Seleccione un tenant.';
    if (!form.id_plan) return 'Seleccione un plan.';
    if (!form.fecha_inicio) return 'La fecha de inicio es obligatoria.';
    if (!form.fecha_fin) return 'La fecha de fin es obligatoria.';
    if (form.fecha_fin < form.fecha_inicio) return 'La fecha de fin no puede ser anterior a la de inicio.';
    if (!DECIMAL_RE.test(form.monto_pagado)) return 'Monto pagado inválido (formato 0.00, sin negativos).';
    return null;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const err = validate();
    if (err) {
      setError(err);
      return;
    }
    setError('');
    mutation.mutate(form);
  };

  return (
    <PageContainer maxWidth={680}>
      <PageHeader title="Nueva suscripción" subtitle="Asignar un plan a un tenant." />

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Card sx={{ p: 3 }}>
        <Box component="form" onSubmit={handleSubmit}>
          <Stack spacing={2}>
            <TextField
              select
              label="Tenant (empresa)"
              value={form.id_empresa}
              onChange={(e) => set('id_empresa', e.target.value)}
              required
              fullWidth
            >
              {empresas.length === 0 && <MenuItem value="" disabled>No hay empresas</MenuItem>}
              {empresas.map((emp) => (
                <MenuItem key={emp.id_empresa} value={emp.id_empresa}>
                  {emp.nombre_comercial || emp.nombre_legal}
                </MenuItem>
              ))}
            </TextField>

            <TextField
              select
              label="Plan"
              value={form.id_plan}
              onChange={(e) => set('id_plan', e.target.value)}
              required
              fullWidth
            >
              {planes.length === 0 && <MenuItem value="" disabled>No hay planes activos</MenuItem>}
              {planes.map((p) => (
                <MenuItem key={p.id_plan} value={p.id_plan}>
                  {p.nombre} ({p.nivel})
                </MenuItem>
              ))}
            </TextField>

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                select
                label="Estado"
                value={form.estado}
                onChange={(e) => set('estado', e.target.value as SuscripcionPayload['estado'])}
                fullWidth
              >
                {SUSCRIPCION_ESTADOS.map((es) => (
                  <MenuItem key={es} value={es}>{es}</MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Periodo"
                value={form.periodo}
                onChange={(e) => set('periodo', e.target.value as SuscripcionPayload['periodo'])}
                fullWidth
              >
                {SUSCRIPCION_PERIODOS.map((p) => (
                  <MenuItem key={p} value={p}>{p}</MenuItem>
                ))}
              </TextField>
            </Stack>

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label="Fecha inicio"
                type="date"
                value={form.fecha_inicio}
                onChange={(e) => set('fecha_inicio', e.target.value)}
                InputLabelProps={{ shrink: true }}
                fullWidth
              />
              <TextField
                label="Fecha fin"
                type="date"
                value={form.fecha_fin}
                onChange={(e) => set('fecha_fin', e.target.value)}
                InputLabelProps={{ shrink: true }}
                fullWidth
              />
            </Stack>

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label="Monto pagado"
                value={form.monto_pagado}
                onChange={(e) => set('monto_pagado', e.target.value)}
                inputProps={{ inputMode: 'decimal' }}
                fullWidth
              />
              <TextField
                label="Referencia de pago"
                value={form.referencia_pago}
                onChange={(e) => set('referencia_pago', e.target.value)}
                fullWidth
              />
            </Stack>

            <TextField
              label="Notas"
              value={form.notas}
              onChange={(e) => set('notas', e.target.value)}
              multiline
              minRows={2}
              fullWidth
            />

            <FormControlLabel
              control={
                <Switch
                  checked={form.renovacion_automatica}
                  onChange={(e) => set('renovacion_automatica', e.target.checked)}
                />
              }
              label="Renovación automática"
            />

            <Stack direction="row" spacing={2} justifyContent="flex-end">
              <Button onClick={() => navigate('/admin-saas/suscripciones')}>Cancelar</Button>
              <Button type="submit" variant="contained" disabled={mutation.isPending}>
                {mutation.isPending ? 'Creando…' : 'Crear suscripción'}
              </Button>
            </Stack>
          </Stack>
        </Box>
      </Card>
    </PageContainer>
  );
};

export default SuscripcionCreatePage;
