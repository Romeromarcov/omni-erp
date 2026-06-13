/**
 * Formulario de Empleado (workstream F): crear y editar.
 *
 * - Crear: POST /rrhh/empleados/ con `empresa` = empresa activa (SEC-M1 valida
 *   que sea visible para el usuario).
 * - Editar: PATCH parcial sin `empresa` (no se mueve de tenant).
 * - El salario mensual se guarda como STRING decimal en
 *   `documento_json.salario_mensual` (puente que lee el motor de nómina LOTTT),
 *   preservando las demás claves del documento_json al editar.
 */
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  CircularProgress,
  FormControlLabel,
  MenuItem,
  Paper,
  Stack,
  Switch,
  TextField,
} from '@mui/material';
import { rrhhService } from '../../services/rrhhService';
import type { DocumentoEmpleado, Empleado, EmpleadoPayload } from '../../services/rrhhService';
import { empleadoSchema, type EmpleadoInput } from '../../schemas/rrhh.schemas';
import { rrhhKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { getEmpresaId } from '../../utils/empresa';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader } from '../../components/ui';

const SIN_CARGO = '';

function formDesdeEmpleado(e: Empleado): EmpleadoInput {
  const salario = e.documento_json?.salario_mensual;
  return {
    nombre: e.nombre,
    apellido: e.apellido,
    cedula: e.cedula,
    cargo: e.cargo === null ? SIN_CARGO : String(e.cargo),
    fecha_ingreso: e.fecha_ingreso,
    salario_mensual: typeof salario === 'string' ? salario : '',
    activo: e.activo,
  };
}

/**
 * documento_json resultante: preserva las claves existentes y fija/borra solo
 * `salario_mensual` (string decimal, R-CODE-4).
 */
function documentoConSalario(
  base: DocumentoEmpleado | null,
  salario: string,
): DocumentoEmpleado | null {
  const doc: DocumentoEmpleado = { ...(base ?? {}) };
  if (salario) {
    doc.salario_mensual = salario;
  } else {
    delete doc.salario_mensual;
  }
  return Object.keys(doc).length > 0 ? doc : null;
}

export default function EmpleadoFormPage() {
  const { id } = useParams<{ id: string }>();
  const esEdicion = Boolean(id);
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [errorGeneral, setErrorGeneral] = useState('');
  const empresaId = getEmpresaId() || '';

  const { data: cargos = [] } = useQuery({
    queryKey: rrhhKeys.cargos(),
    queryFn: () => rrhhService.getCargos(),
  });

  const { data: empleado, isLoading: cargandoEmpleado } = useQuery({
    queryKey: rrhhKeys.empleado(id ?? ''),
    queryFn: () => rrhhService.getEmpleado(id ?? ''),
    enabled: esEdicion,
  });

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<EmpleadoInput>({
    resolver: zodResolver(empleadoSchema),
    defaultValues: {
      nombre: '',
      apellido: '',
      cedula: '',
      cargo: SIN_CARGO,
      fecha_ingreso: '',
      salario_mensual: '',
      activo: true,
    },
  });

  // En edición, el formulario se rellena cuando llega el empleado.
  useEffect(() => {
    if (empleado) reset(formDesdeEmpleado(empleado));
  }, [empleado, reset]);

  const guardarMutation = useMutation({
    mutationFn: async (input: EmpleadoInput): Promise<Empleado> => {
      const comunes = {
        nombre: input.nombre,
        apellido: input.apellido,
        cedula: input.cedula,
        cargo: input.cargo === SIN_CARGO ? null : Number(input.cargo),
        fecha_ingreso: input.fecha_ingreso,
        activo: input.activo,
      };
      if (esEdicion && id) {
        const payload: Partial<EmpleadoPayload> = {
          ...comunes,
          documento_json: documentoConSalario(
            empleado?.documento_json ?? null,
            input.salario_mensual,
          ),
        };
        return rrhhService.actualizarEmpleado(id, payload);
      }
      const payload: EmpleadoPayload = {
        ...comunes,
        empresa: empresaId,
        documento_json: documentoConSalario(null, input.salario_mensual),
      };
      return rrhhService.crearEmpleado(payload);
    },
    onSuccess: (guardado) => {
      snackbar.success(esEdicion ? t('rrhh.form.actualizado') : t('rrhh.form.creado'));
      void queryClient.invalidateQueries({ queryKey: rrhhKeys.empleadosAll() });
      navigate(`/rrhh/empleados/${guardado.id}`);
    },
    onError: (err: unknown) => {
      // 400 del backend (p. ej. cédula duplicada en la empresa) visible en la página.
      setErrorGeneral(mensajeDeError(err, t('rrhh.form.error')));
    },
  });

  if (esEdicion && cargandoEmpleado) {
    return (
      <PageContainer>
        <Stack alignItems="center" sx={{ py: 8 }}>
          <CircularProgress />
        </Stack>
      </PageContainer>
    );
  }

  const sinEmpresa = !esEdicion && !empresaId;

  return (
    <PageContainer>
      <PageHeader
        title={esEdicion ? t('rrhh.form.titleEditar') : t('rrhh.form.titleNuevo')}
        subtitle={t('rrhh.form.subtitle')}
      />
      <form
        onSubmit={handleSubmit((input) => {
          setErrorGeneral('');
          guardarMutation.mutate(input);
        })}
        noValidate
      >
        <Paper variant="outlined" sx={{ p: 3, mb: 2 }}>
          {errorGeneral && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {errorGeneral}
            </Alert>
          )}
          {sinEmpresa && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              {t('rrhh.form.sinEmpresa')}
            </Alert>
          )}
          <Stack spacing={2}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label={t('rrhh.form.nombre')}
                fullWidth
                required
                error={!!errors.nombre}
                helperText={errors.nombre?.message}
                {...register('nombre')}
              />
              <TextField
                label={t('rrhh.form.apellido')}
                fullWidth
                required
                error={!!errors.apellido}
                helperText={errors.apellido?.message}
                {...register('apellido')}
              />
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label={t('rrhh.form.cedula')}
                fullWidth
                required
                error={!!errors.cedula}
                helperText={errors.cedula?.message}
                {...register('cedula')}
              />
              <Controller
                name="cargo"
                control={control}
                render={({ field }) => (
                  <TextField
                    select
                    label={t('rrhh.form.cargo')}
                    fullWidth
                    error={!!errors.cargo}
                    helperText={errors.cargo?.message}
                    {...field}
                  >
                    <MenuItem value={SIN_CARGO}>{t('rrhh.form.sinCargo')}</MenuItem>
                    {cargos.map((c) => (
                      <MenuItem key={c.id} value={String(c.id)}>
                        {c.nombre}
                      </MenuItem>
                    ))}
                  </TextField>
                )}
              />
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label={t('rrhh.form.fechaIngreso')}
                type="date"
                fullWidth
                required
                InputLabelProps={{ shrink: true }}
                error={!!errors.fecha_ingreso}
                helperText={errors.fecha_ingreso?.message}
                {...register('fecha_ingreso')}
              />
              <TextField
                label={t('rrhh.form.salario')}
                fullWidth
                inputMode="decimal"
                error={!!errors.salario_mensual}
                helperText={errors.salario_mensual?.message ?? t('rrhh.form.salarioAyuda')}
                {...register('salario_mensual')}
              />
            </Stack>
            <Controller
              name="activo"
              control={control}
              render={({ field }) => (
                <FormControlLabel
                  control={
                    <Switch
                      checked={field.value}
                      onChange={(_, checked) => field.onChange(checked)}
                    />
                  }
                  label={t('rrhh.form.activo')}
                />
              )}
            />
          </Stack>
        </Paper>

        <Stack direction="row" spacing={2} justifyContent="flex-end">
          <Button onClick={() => navigate('/rrhh/empleados')} disabled={guardarMutation.isPending}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            variant="contained"
            disabled={guardarMutation.isPending || sinEmpresa}
            startIcon={guardarMutation.isPending ? <CircularProgress size={16} /> : undefined}
          >
            {esEdicion ? t('rrhh.form.guardar') : t('rrhh.form.crear')}
          </Button>
        </Stack>
      </form>
    </PageContainer>
  );
}
