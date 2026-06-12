/**
 * Plan de Cuentas (workstream F) — lista jerárquica de solo lectura (indentación
 * por nivel, orden por código) + creación de cuentas nuevas.
 */
import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { contabilidadService } from '../../services/contabilidadService';
import type { CuentaContable } from '../../services/contabilidadService';
import { cuentaContableSchema, type CuentaContableInput } from '../../schemas/contabilidad.schemas';
import { contabilidadKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { getEmpresaId } from '../../utils/empresa';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

const TIPOS_CUENTA = ['ACTIVO', 'PASIVO', 'PATRIMONIO', 'INGRESO', 'GASTO', 'COSTO'] as const;
const NATURALEZAS = ['DEUDORA', 'ACREEDORA'] as const;

/** Ordena por código (la jerarquía contable está codificada en el código). */
function ordenarPlan(cuentas: CuentaContable[]): CuentaContable[] {
  return [...cuentas].sort((a, b) => a.codigo_cuenta.localeCompare(b.codigo_cuenta));
}

export default function PlanCuentasPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [errorGeneral, setErrorGeneral] = useState('');
  const empresaId = getEmpresaId() || '';

  const { data: cuentasRaw, isLoading } = useQuery({
    queryKey: contabilidadKeys.planCuentas(),
    queryFn: () => contabilidadService.getPlanCuentas(),
  });
  const cuentas = useMemo(() => ordenarPlan(cuentasRaw ?? []), [cuentasRaw]);

  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors },
  } = useForm<CuentaContableInput>({
    resolver: zodResolver(cuentaContableSchema),
    defaultValues: {
      codigo_cuenta: '',
      nombre_cuenta: '',
      tipo_cuenta: '',
      naturaleza: '',
      id_cuenta_padre: '',
    },
  });
  const padreSeleccionado = watch('id_cuenta_padre');

  const crearMutation = useMutation({
    mutationFn: (input: CuentaContableInput) => {
      const padre = cuentas.find((c) => c.id_cuenta_contable === input.id_cuenta_padre);
      return contabilidadService.crearCuenta({
        id_empresa: empresaId,
        codigo_cuenta: input.codigo_cuenta,
        nombre_cuenta: input.nombre_cuenta,
        tipo_cuenta: input.tipo_cuenta,
        naturaleza: input.naturaleza,
        id_cuenta_padre: input.id_cuenta_padre || null,
        // El nivel se deriva del padre: raíz = 1, hija = nivel del padre + 1.
        nivel: padre ? padre.nivel + 1 : 1,
      });
    },
    onSuccess: () => {
      snackbar.success(t('contabilidad.plan.creada'));
      void queryClient.invalidateQueries({ queryKey: contabilidadKeys.planCuentas() });
      setDialogOpen(false);
      reset();
    },
    onError: (err: unknown) => {
      setErrorGeneral(mensajeDeError(err, t('contabilidad.plan.errorCrear')));
    },
  });

  const columns: Column<CuentaContable>[] = [
    {
      key: 'codigo',
      header: t('contabilidad.plan.codigo'),
      render: (c) => (
        <Typography variant="body2" fontFamily="monospace">
          {c.codigo_cuenta}
        </Typography>
      ),
    },
    {
      key: 'nombre',
      header: t('contabilidad.plan.nombre'),
      render: (c) => (
        // Indentación por nivel: representación visual de la jerarquía.
        <Typography variant="body2" sx={{ pl: Math.max(0, (c.nivel ?? 1) - 1) * 2 }}>
          {c.nombre_cuenta}
        </Typography>
      ),
    },
    { key: 'tipo', header: t('contabilidad.plan.tipo'), render: (c) => c.tipo_cuenta },
    { key: 'naturaleza', header: t('contabilidad.plan.naturaleza'), render: (c) => c.naturaleza },
    { key: 'nivel', header: t('contabilidad.plan.nivel'), align: 'right', render: (c) => String(c.nivel) },
    {
      key: 'activo',
      header: t('contabilidad.plan.activo'),
      render: (c) => <StatusChip value={c.activo} />,
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('contabilidad.plan.title')}
        subtitle={t('contabilidad.plan.subtitle')}
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={() => setDialogOpen(true)}>
            {t('contabilidad.plan.nueva')}
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={cuentas}
        getRowKey={(c) => c.id_cuenta_contable}
        loading={isLoading}
        emptyMessage={t('contabilidad.plan.empty')}
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <form
          onSubmit={handleSubmit((input) => {
            setErrorGeneral('');
            crearMutation.mutate(input);
          })}
          noValidate
        >
          <DialogTitle>{t('contabilidad.plan.nueva')}</DialogTitle>
          <DialogContent>
            {errorGeneral && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {errorGeneral}
              </Alert>
            )}
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField
                label={t('contabilidad.plan.codigo')}
                fullWidth
                required
                error={!!errors.codigo_cuenta}
                helperText={errors.codigo_cuenta?.message}
                {...register('codigo_cuenta')}
              />
              <TextField
                label={t('contabilidad.plan.nombre')}
                fullWidth
                required
                error={!!errors.nombre_cuenta}
                helperText={errors.nombre_cuenta?.message}
                {...register('nombre_cuenta')}
              />
              <TextField
                select
                label={t('contabilidad.plan.tipo')}
                fullWidth
                required
                defaultValue=""
                error={!!errors.tipo_cuenta}
                helperText={errors.tipo_cuenta?.message}
                {...register('tipo_cuenta')}
              >
                {TIPOS_CUENTA.map((tipo) => (
                  <MenuItem key={tipo} value={tipo}>
                    {tipo}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label={t('contabilidad.plan.naturaleza')}
                fullWidth
                required
                defaultValue=""
                error={!!errors.naturaleza}
                helperText={errors.naturaleza?.message}
                {...register('naturaleza')}
              >
                {NATURALEZAS.map((n) => (
                  <MenuItem key={n} value={n}>
                    {n}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label={t('contabilidad.plan.cuentaPadre')}
                fullWidth
                defaultValue=""
                helperText={
                  padreSeleccionado
                    ? t('contabilidad.plan.nivelHijo', {
                        nivel:
                          (cuentas.find((c) => c.id_cuenta_contable === padreSeleccionado)?.nivel ?? 0) + 1,
                      })
                    : t('contabilidad.plan.nivelRaiz')
                }
                {...register('id_cuenta_padre')}
              >
                <MenuItem value="">{t('contabilidad.plan.sinPadre')}</MenuItem>
                {cuentas.map((c) => (
                  <MenuItem key={c.id_cuenta_contable} value={c.id_cuenta_contable}>
                    {c.codigo_cuenta} — {c.nombre_cuenta}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDialogOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" variant="contained" disabled={crearMutation.isPending}>
              {t('common.save')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </PageContainer>
  );
}
