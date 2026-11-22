/**
 * Detalle de conciliación bancaria (workstream F) — saldos banco/libro con
 * diferencia exacta (decimal.js), matching automático de movimientos contra
 * pagos (conciliar-auto) y cierre de la sesión.
 */
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import AccountBalanceWalletOutlined from '@mui/icons-material/AccountBalanceWalletOutlined';
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined';
import JoinInnerOutlined from '@mui/icons-material/JoinInnerOutlined';
import LinkOutlined from '@mui/icons-material/LinkOutlined';
import LockOutlined from '@mui/icons-material/LockOutlined';
import ConciliacionContactoDialog from '../../components/Finanzas/ConciliacionContactoDialog';
import { get } from '../../services/api';
import { tesoreriaService } from '../../services/tesoreriaService';
import type { MovimientoBancario } from '../../services/tesoreriaService';
import { tesoreriaKeys } from '../../lib/queryKeys';
import { mensajeDeError, toList, type PaginatedResponse } from '../../utils/api';
import { D, toFixedStr } from '../../lib/decimal';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader, DataTable, StatusChip, KpiCard } from '../../components/ui';
import type { Column } from '../../components/ui';

export default function ConciliacionDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const { id = '' } = useParams<{ id: string }>();

  interface ContactoSelectorItem {
    id_contacto: string;
    nombre_completo?: string;
    nombre?: string;
    rif?: string;
  }

  const [contactoConciliar, setContactoConciliar] = useState<string | null>(null);
  const [pagoInicialConciliar, setPagoInicialConciliar] = useState<string | null>(null);
  const [selectorContactoOpen, setSelectorContactoOpen] = useState(false);
  const [contactoSeleccionadoModal, setContactoSeleccionadoModal] = useState('');

  const { data: contactosData, isLoading: cargandoContactos } = useQuery({
    queryKey: ['core', 'contactos', 'conciliacion-selector'],
    queryFn: () =>
      get<PaginatedResponse<ContactoSelectorItem> | ContactoSelectorItem[]>(
        '/core/contactos/?page_size=100',
      ),
    enabled: selectorContactoOpen,
  });
  const contactosDisponibles = toList<ContactoSelectorItem>(contactosData);

  const abrirConciliacionContacto = (contactoId: string, pagoId?: string | null) => {
    setContactoConciliar(contactoId);
    setPagoInicialConciliar(pagoId ?? null);
  };

  const {
    data: conciliacion,
    isLoading,
    error,
  } = useQuery({
    queryKey: tesoreriaKeys.conciliacion(id),
    queryFn: () => tesoreriaService.getConciliacion(id),
    enabled: !!id,
  });

  // Movimientos de la cuenta conciliada (matching visual pendiente/conciliado).
  const cuentaId = conciliacion?.id_cuenta_bancaria ?? '';
  const { data: movimientosData } = useQuery({
    queryKey: tesoreriaKeys.movimientos(1, { cuenta: cuentaId }),
    queryFn: () => tesoreriaService.getMovimientosBancariosPaginated(1, 100, { cuenta: cuentaId }),
    enabled: !!cuentaId,
  });

  const conciliarAutoMutation = useMutation({
    mutationFn: () => tesoreriaService.conciliarAuto(cuentaId),
    onSuccess: (resultado) => {
      snackbar.success(
        t('tesoreria.conciliacionDetalle.conciliados', { count: Number(resultado.conciliados ?? 0) }),
      );
      void queryClient.invalidateQueries({ queryKey: tesoreriaKeys.movimientosAll() });
      void queryClient.invalidateQueries({ queryKey: tesoreriaKeys.conciliacionesAll() });
    },
    onError: (err: unknown) => {
      snackbar.error(mensajeDeError(err, t('tesoreria.conciliacionDetalle.errorConciliar')));
    },
  });

  const cerrarMutation = useMutation({
    mutationFn: () => tesoreriaService.cerrarConciliacion(id),
    onSuccess: () => {
      snackbar.success(t('tesoreria.conciliacionDetalle.cerrada'));
      void queryClient.invalidateQueries({ queryKey: tesoreriaKeys.conciliacionesAll() });
    },
    onError: (err: unknown) => {
      snackbar.error(mensajeDeError(err, t('tesoreria.conciliacionDetalle.errorCerrar')));
    },
  });

  if (isLoading) {
    return (
      <PageContainer>
        <CircularProgress />
      </PageContainer>
    );
  }

  if (error || !conciliacion) {
    return (
      <PageContainer>
        <Alert severity="error">{mensajeDeError(error, t('tesoreria.conciliacionDetalle.errorCargar'))}</Alert>
      </PageContainer>
    );
  }

  const abierta = conciliacion.estado === 'ABIERTA';
  const movimientos = movimientosData?.results ?? [];
  const diferencia = D(conciliacion.diferencia);

  const columns: Column<MovimientoBancario>[] = [
    { key: 'fecha', header: t('tesoreria.movimientos.fecha'), render: (m) => m.fecha_mov },
    { key: 'descripcion', header: t('tesoreria.movimientos.descripcion'), render: (m) => m.descripcion },
    { key: 'tipo', header: t('tesoreria.movimientos.tipo'), render: (m) => m.tipo },
    {
      key: 'monto',
      header: t('tesoreria.movimientos.monto'),
      align: 'right',
      render: (m) => toFixedStr(m.monto),
    },
    { key: 'referencia', header: t('tesoreria.movimientos.referencia'), render: (m) => m.referencia || '—' },
    {
      key: 'estado',
      header: t('tesoreria.movimientos.estado'),
      render: (m) => <StatusChip value={m.estado} />,
    },
    {
      key: 'acciones',
      header: t('common.actions'),
      align: 'right',
      render: (m) =>
        m.pago_contacto_id ? (
          <Button
            size="small"
            variant="outlined"
            startIcon={<LinkOutlined />}
            onClick={() => abrirConciliacionContacto(m.pago_contacto_id!, m.id_pago_conciliado)}
          >
            {t('tesoreria.conciliacionDetalle.conciliarPago')}
          </Button>
        ) : (
          '—'
        ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('tesoreria.conciliacionDetalle.title')}
        subtitle={`${conciliacion.periodo_inicio} → ${conciliacion.periodo_fin}`}
        actions={
          <>
            <Button startIcon={<ArrowBackOutlined />} onClick={() => navigate('/tesoreria/conciliaciones')}>
              {t('common.back')}
            </Button>
            {abierta && (
              <Button
                variant="outlined"
                startIcon={<AccountBalanceWalletOutlined />}
                onClick={() => setSelectorContactoOpen(true)}
              >
                {t('tesoreria.conciliacionDetalle.conciliarPorContacto')}
              </Button>
            )}
            {abierta && (
              <Button
                variant="outlined"
                startIcon={<JoinInnerOutlined />}
                disabled={conciliarAutoMutation.isPending}
                onClick={() => conciliarAutoMutation.mutate()}
              >
                {t('tesoreria.conciliacionDetalle.conciliarAuto')}
              </Button>
            )}
            {abierta && (
              <Button
                variant="contained"
                color="warning"
                startIcon={<LockOutlined />}
                disabled={cerrarMutation.isPending}
                onClick={() => cerrarMutation.mutate()}
              >
                {t('tesoreria.conciliacionDetalle.cerrar')}
              </Button>
            )}
          </>
        }
      />

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <KpiCard
          label={t('tesoreria.conciliaciones.saldoBanco')}
          value={toFixedStr(conciliacion.saldo_banco)}
        />
        <KpiCard
          label={t('tesoreria.conciliaciones.saldoLibro')}
          value={toFixedStr(conciliacion.saldo_libro)}
        />
        <KpiCard
          label={t('tesoreria.conciliaciones.diferencia')}
          value={toFixedStr(diferencia)}
          tone={diferencia.isZero() ? 'success' : 'error'}
        />
      </Stack>

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3} alignItems={{ sm: 'center' }}>
          <StatusChip value={conciliacion.estado} />
          <Typography variant="body2">
            <strong>{t('tesoreria.conciliacionDetalle.movConciliados')}:</strong>{' '}
            {conciliacion.movimientos_conciliados}
          </Typography>
          <Typography variant="body2">
            <strong>{t('tesoreria.conciliacionDetalle.movPendientes')}:</strong>{' '}
            {conciliacion.movimientos_pendientes}
          </Typography>
          {conciliacion.observaciones && (
            <Typography variant="body2" color="text.secondary">
              {conciliacion.observaciones}
            </Typography>
          )}
        </Stack>
      </Paper>

      <Typography variant="h6" sx={{ mb: 1 }}>
        {t('tesoreria.conciliacionDetalle.movimientosCuenta')}
      </Typography>
      <DataTable
        columns={columns}
        rows={movimientos}
        getRowKey={(m) => m.id}
        emptyMessage={t('tesoreria.movimientos.empty')}
      />

      <Dialog
        open={selectorContactoOpen}
        onClose={() => setSelectorContactoOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('tesoreria.conciliacionDetalle.conciliarPorContacto')}</DialogTitle>
        <DialogContent dividers>
          {cargandoContactos ? (
            <Stack alignItems="center" sx={{ py: 3 }}>
              <CircularProgress size={28} />
            </Stack>
          ) : (
            <FormControl fullWidth size="small" sx={{ mt: 1 }}>
              <InputLabel id="tesoreria-selector-contacto-label">Contacto</InputLabel>
              <Select
                labelId="tesoreria-selector-contacto-label"
                label="Contacto"
                value={contactoSeleccionadoModal}
                onChange={(e) => setContactoSeleccionadoModal(e.target.value)}
              >
                {contactosDisponibles.map((c) => (
                  <MenuItem key={c.id_contacto} value={c.id_contacto}>
                    {c.nombre_completo || c.nombre || c.id_contacto}
                    {c.rif ? ` (${c.rif})` : ''}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectorContactoOpen(false)}>{t('common.cancel', { defaultValue: 'Cancelar' })}</Button>
          <Button
            variant="contained"
            disabled={!contactoSeleccionadoModal}
            onClick={() => {
              setSelectorContactoOpen(false);
              abrirConciliacionContacto(contactoSeleccionadoModal);
            }}
          >
            {t('tesoreria.conciliacionDetalle.conciliarPago')}
          </Button>
        </DialogActions>
      </Dialog>

      <ConciliacionContactoDialog
        open={Boolean(contactoConciliar)}
        contactoId={contactoConciliar}
        pagoInicialId={pagoInicialConciliar}
        onClose={() => {
          setContactoConciliar(null);
          setPagoInicialConciliar(null);
        }}
      />
    </PageContainer>
  );
}
