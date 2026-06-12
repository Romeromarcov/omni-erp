/**
 * Mapeos contables (workstream F) — configura qué cuentas usa cada tipo de
 * asiento automático (FACTURA_VENTA, CAMBIO_DIVISA, …). Sin la fila del tipo,
 * los flujos automáticos responden 422 "falta mapeo X": esta pantalla es la
 * que destranca esos errores.
 */
import { useState } from 'react';
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
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { contabilidadService } from '../../services/contabilidadService';
import type { MapeoContable } from '../../services/contabilidadService';
import { mapeoContableSchema, type MapeoContableInput } from '../../schemas/contabilidad.schemas';
import { contabilidadKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { getEmpresaId } from '../../utils/empresa';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

export default function MapeosContablesPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<MapeoContable | null>(null);
  const [errorGeneral, setErrorGeneral] = useState('');
  const empresaId = getEmpresaId() || '';

  const { data: mapeos = [], isLoading } = useQuery({
    queryKey: contabilidadKeys.mapeosAll(),
    queryFn: () => contabilidadService.getMapeos(),
  });

  const { data: tipos = [] } = useQuery({
    queryKey: contabilidadKeys.tiposAsiento(),
    queryFn: () => contabilidadService.getTiposAsiento(),
  });

  const { data: cuentas = [] } = useQuery({
    queryKey: contabilidadKeys.planCuentas(),
    queryFn: () => contabilidadService.getPlanCuentas(),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<MapeoContableInput>({
    resolver: zodResolver(mapeoContableSchema),
    defaultValues: { tipo_asiento: '', cuenta_debe: '', cuenta_haber: '', descripcion_plantilla: '' },
  });

  const abrirCrear = () => {
    setEditando(null);
    reset({ tipo_asiento: '', cuenta_debe: '', cuenta_haber: '', descripcion_plantilla: '' });
    setErrorGeneral('');
    setDialogOpen(true);
  };

  const abrirEditar = (m: MapeoContable) => {
    setEditando(m);
    reset({
      tipo_asiento: m.tipo_asiento,
      cuenta_debe: m.cuenta_debe,
      cuenta_haber: m.cuenta_haber,
      descripcion_plantilla: m.descripcion_plantilla,
    });
    setErrorGeneral('');
    setDialogOpen(true);
  };

  const guardarMutation = useMutation({
    mutationFn: (input: MapeoContableInput) => {
      if (editando) {
        return contabilidadService.actualizarMapeo(editando.id_mapeo, {
          cuenta_debe: input.cuenta_debe,
          cuenta_haber: input.cuenta_haber,
          descripcion_plantilla: input.descripcion_plantilla || '{tipo} - {numero}',
        });
      }
      return contabilidadService.crearMapeo({
        id_empresa: empresaId,
        tipo_asiento: input.tipo_asiento,
        cuenta_debe: input.cuenta_debe,
        cuenta_haber: input.cuenta_haber,
        descripcion_plantilla: input.descripcion_plantilla || '{tipo} - {numero}',
      });
    },
    onSuccess: () => {
      snackbar.success(t('contabilidad.mapeos.guardado'));
      void queryClient.invalidateQueries({ queryKey: contabilidadKeys.mapeosAll() });
      setDialogOpen(false);
    },
    onError: (err: unknown) => {
      setErrorGeneral(mensajeDeError(err, t('contabilidad.mapeos.errorGuardar')));
    },
  });

  const columns: Column<MapeoContable>[] = [
    {
      key: 'tipo',
      header: t('contabilidad.mapeos.tipo'),
      render: (m) => m.tipo_asiento_display || m.tipo_asiento,
    },
    {
      key: 'debe',
      header: t('contabilidad.mapeos.cuentaDebe'),
      render: (m) => m.cuenta_debe_nombre || m.cuenta_debe,
    },
    {
      key: 'haber',
      header: t('contabilidad.mapeos.cuentaHaber'),
      render: (m) => m.cuenta_haber_nombre || m.cuenta_haber,
    },
    {
      key: 'activo',
      header: t('contabilidad.mapeos.activo'),
      render: (m) => <StatusChip value={m.activo} />,
    },
    {
      key: 'acciones',
      header: t('common.actions'),
      render: (m) => (
        <Button size="small" onClick={() => abrirEditar(m)}>
          {t('common.edit')}
        </Button>
      ),
    },
  ];

  // Tipos sin mapeo todavía (los únicos elegibles al crear: unique por empresa+tipo).
  const tiposDisponibles = tipos.filter((tp) => !mapeos.some((m) => m.tipo_asiento === tp.value));

  return (
    <PageContainer>
      <PageHeader
        title={t('contabilidad.mapeos.title')}
        subtitle={t('contabilidad.mapeos.subtitle')}
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            {t('contabilidad.mapeos.nuevo')}
          </Button>
        }
      />
      {tiposDisponibles.length > 0 && !isLoading && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {t('contabilidad.mapeos.faltantes', {
            tipos: tiposDisponibles.map((tp) => tp.label).join(', '),
          })}
        </Alert>
      )}
      <DataTable
        columns={columns}
        rows={mapeos}
        getRowKey={(m) => m.id_mapeo}
        loading={isLoading}
        emptyMessage={t('contabilidad.mapeos.empty')}
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <form
          onSubmit={handleSubmit((input) => {
            setErrorGeneral('');
            guardarMutation.mutate(input);
          })}
          noValidate
        >
          <DialogTitle>
            {editando ? t('contabilidad.mapeos.editar') : t('contabilidad.mapeos.nuevo')}
          </DialogTitle>
          <DialogContent>
            {errorGeneral && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {errorGeneral}
              </Alert>
            )}
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField
                select
                label={t('contabilidad.mapeos.tipo')}
                fullWidth
                required
                disabled={!!editando}
                defaultValue={editando?.tipo_asiento ?? ''}
                error={!!errors.tipo_asiento}
                helperText={errors.tipo_asiento?.message}
                {...register('tipo_asiento')}
              >
                {(editando ? tipos : tiposDisponibles).map((tp) => (
                  <MenuItem key={tp.value} value={tp.value}>
                    {tp.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label={t('contabilidad.mapeos.cuentaDebe')}
                fullWidth
                required
                defaultValue={editando?.cuenta_debe ?? ''}
                error={!!errors.cuenta_debe}
                helperText={errors.cuenta_debe?.message}
                {...register('cuenta_debe')}
              >
                {cuentas.map((c) => (
                  <MenuItem key={c.id_cuenta_contable} value={c.id_cuenta_contable}>
                    {c.codigo_cuenta} — {c.nombre_cuenta}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label={t('contabilidad.mapeos.cuentaHaber')}
                fullWidth
                required
                defaultValue={editando?.cuenta_haber ?? ''}
                error={!!errors.cuenta_haber}
                helperText={errors.cuenta_haber?.message}
                {...register('cuenta_haber')}
              >
                {cuentas.map((c) => (
                  <MenuItem key={c.id_cuenta_contable} value={c.id_cuenta_contable}>
                    {c.codigo_cuenta} — {c.nombre_cuenta}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label={t('contabilidad.mapeos.plantilla')}
                fullWidth
                placeholder="{tipo} - {numero}"
                error={!!errors.descripcion_plantilla}
                helperText={errors.descripcion_plantilla?.message || t('contabilidad.mapeos.plantillaHint')}
                {...register('descripcion_plantilla')}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDialogOpen(false)}>{t('common.cancel')}</Button>
            <Button type="submit" variant="contained" disabled={guardarMutation.isPending}>
              {t('common.save')}
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </PageContainer>
  );
}
