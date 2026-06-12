import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Box, Button, Card, FormControlLabel, MenuItem, Stack, Switch, TextField,
} from '@mui/material';
import { PageContainer, PageHeader } from '../../components/ui';
import {
  fetchPlan, createPlan, updatePlan,
  PLAN_NIVELES, PLAN_SOPORTES,
  type PlanPayload,
} from '../../services/saasService';

const EMPTY: PlanPayload = {
  nombre: '',
  nivel: 'STARTER',
  descripcion: '',
  precio_mensual: '0',
  precio_anual: '0',
  max_usuarios: 5,
  max_empresas: 1,
  max_documentos_mes: 100,
  permite_ia: false,
  permite_api: false,
  permite_reportes_avanzados: false,
  permite_multimoneda: false,
  soporte: 'email',
  activo: true,
};

// Acepta enteros/decimales con punto, hasta 2 decimales. Rechaza negativos.
// eslint-disable-next-line security/detect-unsafe-regex -- FP del heurístico star-height de safe-regex: `\.` y `\d` son disjuntos, no hay backtracking ambiguo (matching lineal)
const DECIMAL_RE = /^\d+(\.\d{1,2})?$/;

const PlanFormPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { id_plan } = useParams<{ id_plan: string }>();
  const isEdit = Boolean(id_plan);

  const [form, setForm] = useState<PlanPayload>(EMPTY);
  const [error, setError] = useState('');

  const { data: existing, isLoading: loadingPlan } = useQuery({
    queryKey: ['saas/planes', 'detail', id_plan],
    queryFn: () => fetchPlan(id_plan as string),
    enabled: isEdit,
  });

  useEffect(() => {
    if (existing) {
      setForm({
        nombre: existing.nombre,
        nivel: existing.nivel,
        descripcion: existing.descripcion,
        precio_mensual: existing.precio_mensual,
        precio_anual: existing.precio_anual,
        max_usuarios: existing.max_usuarios,
        max_empresas: existing.max_empresas,
        max_documentos_mes: existing.max_documentos_mes,
        permite_ia: existing.permite_ia,
        permite_api: existing.permite_api,
        permite_reportes_avanzados: existing.permite_reportes_avanzados,
        permite_multimoneda: existing.permite_multimoneda,
        soporte: existing.soporte,
        activo: existing.activo,
      });
    }
  }, [existing]);

  const mutation = useMutation({
    mutationFn: (data: PlanPayload) =>
      isEdit ? updatePlan(id_plan as string, data) : createPlan(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saas/planes'] });
      navigate('/admin-saas/planes');
    },
    onError: (e: Error) => setError(e.message || 'No se pudo guardar el plan.'),
  });

  const set = <K extends keyof PlanPayload>(key: K, value: PlanPayload[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const validate = (): string | null => {
    if (!form.nombre.trim()) return 'El nombre es obligatorio.';
    if (!DECIMAL_RE.test(form.precio_mensual)) return 'Precio mensual inválido (use formato 0.00, sin negativos).';
    if (!DECIMAL_RE.test(form.precio_anual)) return 'Precio anual inválido (use formato 0.00, sin negativos).';
    if (form.max_usuarios < 0 || form.max_empresas < 0 || form.max_documentos_mes < 0) {
      return 'Los límites no pueden ser negativos (use 0 para ilimitado).';
    }
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

  if (isEdit && loadingPlan) {
    return (
      <PageContainer>
        <PageHeader title="Editar plan" />
        <Box>Cargando…</Box>
      </PageContainer>
    );
  }

  return (
    <PageContainer maxWidth={760}>
      <PageHeader title={isEdit ? 'Editar plan' : 'Nuevo plan'} />

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Card sx={{ p: 3 }}>
        <Box component="form" onSubmit={handleSubmit}>
          <Stack spacing={2}>
            <TextField
              label="Nombre"
              value={form.nombre}
              onChange={(e) => set('nombre', e.target.value)}
              required
              fullWidth
            />
            <TextField
              select
              label="Nivel"
              value={form.nivel}
              onChange={(e) => set('nivel', e.target.value as PlanPayload['nivel'])}
              fullWidth
            >
              {PLAN_NIVELES.map((n) => (
                <MenuItem key={n} value={n}>{n}</MenuItem>
              ))}
            </TextField>
            <TextField
              label="Descripción"
              value={form.descripcion}
              onChange={(e) => set('descripcion', e.target.value)}
              multiline
              minRows={2}
              fullWidth
            />

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label="Precio mensual"
                value={form.precio_mensual}
                onChange={(e) => set('precio_mensual', e.target.value)}
                inputProps={{ inputMode: 'decimal' }}
                fullWidth
              />
              <TextField
                label="Precio anual"
                value={form.precio_anual}
                onChange={(e) => set('precio_anual', e.target.value)}
                inputProps={{ inputMode: 'decimal' }}
                fullWidth
              />
            </Stack>

            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label="Máx. usuarios (0 = ilimitado)"
                type="number"
                value={form.max_usuarios}
                onChange={(e) => set('max_usuarios', Number(e.target.value))}
                inputProps={{ min: 0 }}
                fullWidth
              />
              <TextField
                label="Máx. empresas (0 = ilimitado)"
                type="number"
                value={form.max_empresas}
                onChange={(e) => set('max_empresas', Number(e.target.value))}
                inputProps={{ min: 0 }}
                fullWidth
              />
              <TextField
                label="Máx. docs/mes (0 = ilimitado)"
                type="number"
                value={form.max_documentos_mes}
                onChange={(e) => set('max_documentos_mes', Number(e.target.value))}
                inputProps={{ min: 0 }}
                fullWidth
              />
            </Stack>

            <TextField
              select
              label="Soporte"
              value={form.soporte}
              onChange={(e) => set('soporte', e.target.value as PlanPayload['soporte'])}
              fullWidth
            >
              {PLAN_SOPORTES.map((s) => (
                <MenuItem key={s} value={s}>{s}</MenuItem>
              ))}
            </TextField>

            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' }, gap: 1 }}>
              <FormControlLabel
                control={<Switch checked={form.permite_ia} onChange={(e) => set('permite_ia', e.target.checked)} />}
                label="Permite IA / agentes"
              />
              <FormControlLabel
                control={<Switch checked={form.permite_api} onChange={(e) => set('permite_api', e.target.checked)} />}
                label="Permite API REST"
              />
              <FormControlLabel
                control={<Switch checked={form.permite_reportes_avanzados} onChange={(e) => set('permite_reportes_avanzados', e.target.checked)} />}
                label="Reportes avanzados"
              />
              <FormControlLabel
                control={<Switch checked={form.permite_multimoneda} onChange={(e) => set('permite_multimoneda', e.target.checked)} />}
                label="Multimoneda"
              />
              <FormControlLabel
                control={<Switch checked={form.activo} onChange={(e) => set('activo', e.target.checked)} />}
                label="Activo"
              />
            </Box>

            <Stack direction="row" spacing={2} justifyContent="flex-end">
              <Button onClick={() => navigate('/admin-saas/planes')}>Cancelar</Button>
              <Button type="submit" variant="contained" disabled={mutation.isPending}>
                {mutation.isPending ? 'Guardando…' : 'Guardar'}
              </Button>
            </Stack>
          </Stack>
        </Box>
      </Card>
    </PageContainer>
  );
};

export default PlanFormPage;
