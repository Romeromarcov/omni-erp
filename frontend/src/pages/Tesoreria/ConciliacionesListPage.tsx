/**
 * Conciliaciones bancarias (workstream F) — sesiones de conciliación por cuenta
 * y período. Crear una sesión abre el detalle con el matching de movimientos.
 * La diferencia banco/libro se muestra con decimal.js (R-CODE-4).
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
import { tesoreriaService } from '../../services/tesoreriaService';
import type { ConciliacionBancaria } from '../../services/tesoreriaService';
import { conciliacionSchema, type ConciliacionInput } from '../../schemas/tesoreria.schemas';
import { tesoreriaKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { D, toFixedStr } from '../../lib/decimal';
import { getEmpresaId } from '../../utils/empresa';
import { useSnackbar } from '../../contexts/feedbackTypes';
import Pagination from '../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

const PAGE_SIZE = 20;
const hoy = () => new Date().toISOString().slice(0, 10);

export default function ConciliacionesListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const empresaId = getEmpresaId() || '';
  const [page, setPage] = useState(1);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [errorGeneral, setErrorGeneral] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: tesoreriaKeys.conciliaciones(page),
    queryFn: () => tesoreriaService.getConciliacionesPaginated(page, PAGE_SIZE),
  });

  const { data: cuentasBancarias = [] } = useQuery({
    queryKey: tesoreriaKeys.cuentasBancarias(empresaId),
    queryFn: () => tesoreriaService.getCuentasBancarias(empresaId),
    enabled: !!empresaId,
  });

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<ConciliacionInput>({
    resolver: zodResolver(conciliacionSchema),
    defaultValues: {
      id_cuenta_bancaria: '',
      periodo_inicio: hoy(),
      periodo_fin: hoy(),
      saldo_banco: '',
      saldo_libro: '',
      observaciones: '',
    },
  });

  const saldoBancoWatch = watch('saldo_banco');
  const saldoLibroWatch = watch('saldo_libro');
  // Diferencia banco−libro con decimal.js: previsualización exacta, jamás float.
  const diferencia = D(saldoBancoWatch).minus(D(saldoLibroWatch));

  const crearMutation = useMutation({
    mutationFn: (input: ConciliacionInput) =>
      tesoreriaService.crearConciliacion({
        id_empresa: empresaId,
        id_cuenta_bancaria: input.id_cuenta_bancaria,
        periodo_inicio: input.periodo_inicio,
        periodo_fin: input.periodo_fin,
        saldo_banco: input.saldo_banco,
        saldo_libro: input.saldo_libro,
        observaciones: input.observaciones || '',
      }),
    onSuccess: (conciliacion) => {
      snackbar.success(t('tesoreria.conciliaciones.creada'));
      void queryClient.invalidateQueries({ queryKey: tesoreriaKeys.conciliacionesAll() });
      navigate(`/tesoreria/conciliaciones/${conciliacion.id}`);
    },
    onError: (err: unknown) => {
      setErrorGeneral(mensajeDeError(err, t('tesoreria.conciliaciones.errorCrear')));
    },
  });

  const conciliaciones = data?.results ?? [];
  const count = data?.count ?? 0;

  const nombreCuenta = (id: string): string => {
    const cb = cuentasBancarias.find((c) => c.id_cuenta_bancaria === id);
    return cb ? `${cb.nombre_banco} ${cb.numero_cuenta}` : id;
  };

  const columns: Column<ConciliacionBancaria>[] = [
    { key: 'cuenta', header: t('tesoreria.conciliaciones.cuenta'), render: (c) => nombreCuenta(c.id_cuenta_bancaria) },
    {
      key: 'periodo',
      header: t('tesoreria.conciliaciones.periodo'),
      render: (c) => `${c.periodo_inicio} → ${c.periodo_fin}`,
    },
    {
      key: 'saldoBanco',
      header: t('tesoreria.conciliaciones.saldoBanco'),
      align: 'right',
      render: (c) => toFixedStr(c.saldo_banco),
    },
    {
      key: 'saldoLibro',
      header: t('tesoreria.conciliaciones.saldoLibro'),
      align: 'right',
      render: (c) => toFixedStr(c.saldo_libro),
    },
    {
      key: 'diferencia',
      header: t('tesoreria.conciliaciones.diferencia'),
      align: 'right',
      render: (c) => (
        <Typography
          variant="body2"
          color={D(c.diferencia).isZero() ? 'success.main' : 'error.main'}
          fontWeight={600}
        >
          {toFixedStr(c.diferencia)}
        </Typography>
      ),
    },
    {
      key: 'estado',
      header: t('tesoreria.conciliaciones.estado'),
      render: (c) => <StatusChip value={c.estado} />,
    },
    {
      key: 'acciones',
      header: t('common.actions'),
      render: (c) => (
        <Button size="small" onClick={() => navigate(`/tesoreria/conciliaciones/${c.id}`)}>
          {t('tesoreria.conciliaciones.ver')}
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('tesoreria.conciliaciones.title')}
        subtitle={t('tesoreria.conciliaciones.subtitle')}
        actions={
          <Button
            variant="contained"
            startIcon={<AddOutlined />}
            onClick={() => {
              setErrorGeneral('');
              setDialogOpen(true);
            }}
          >
            {t('tesoreria.conciliaciones.nueva')}
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={conciliaciones}
        getRowKey={(c) => c.id}
        loading={isLoading}
        emptyMessage={t('tesoreria.conciliaciones.empty')}
        onRowClick={(c) => navigate(`/tesoreria/conciliaciones/${c.id}`)}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={setPage} />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <form
          onSubmit={handleSubmit((input) => {
            setErrorGeneral('');
            crearMutation.mutate(input);
          })}
          noValidate
        >
          <DialogTitle>{t('tesoreria.conciliaciones.nueva')}</DialogTitle>
          <DialogContent>
            {errorGeneral && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {errorGeneral}
              </Alert>
            )}
            <Stack spacing={2} sx={{ mt: 1 }}>
              <TextField
                select
                label={t('tesoreria.conciliaciones.cuenta')}
                fullWidth
                required
                defaultValue=""
                error={!!errors.id_cuenta_bancaria}
                helperText={errors.id_cuenta_bancaria?.message}
                {...register('id_cuenta_bancaria')}
              >
                {cuentasBancarias.map((cb) => (
                  <MenuItem key={cb.id_cuenta_bancaria} value={cb.id_cuenta_bancaria}>
                    {cb.nombre_banco} — {cb.numero_cuenta}
                  </MenuItem>
                ))}
              </TextField>
              <Stack direction="row" spacing={2}>
                <TextField
                  label={t('tesoreria.conciliaciones.inicio')}
                  type="date"
                  fullWidth
                  required
                  InputLabelProps={{ shrink: true }}
                  error={!!errors.periodo_inicio}
                  helperText={errors.periodo_inicio?.message}
                  {...register('periodo_inicio')}
                />
                <TextField
                  label={t('tesoreria.conciliaciones.fin')}
                  type="date"
                  fullWidth
                  required
                  InputLabelProps={{ shrink: true }}
                  error={!!errors.periodo_fin}
                  helperText={errors.periodo_fin?.message}
                  {...register('periodo_fin')}
                />
              </Stack>
              <Stack direction="row" spacing={2}>
                <TextField
                  label={t('tesoreria.conciliaciones.saldoBanco')}
                  fullWidth
                  required
                  inputProps={{ inputMode: 'decimal' }}
                  error={!!errors.saldo_banco}
                  helperText={errors.saldo_banco?.message}
                  {...register('saldo_banco')}
                />
                <TextField
                  label={t('tesoreria.conciliaciones.saldoLibro')}
                  fullWidth
                  required
                  inputProps={{ inputMode: 'decimal' }}
                  error={!!errors.saldo_libro}
                  helperText={errors.saldo_libro?.message}
                  {...register('saldo_libro')}
                />
              </Stack>
              <Typography variant="body2" color={diferencia.isZero() ? 'success.main' : 'warning.main'}>
                {t('tesoreria.conciliaciones.diferenciaPreview', { monto: toFixedStr(diferencia) })}
              </Typography>
              <TextField
                label={t('tesoreria.conciliaciones.observaciones')}
                fullWidth
                multiline
                rows={2}
                error={!!errors.observaciones}
                helperText={errors.observaciones?.message}
                {...register('observaciones')}
              />
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
