/**
 * Detalle de asiento contable (workstream F + Ola B1) — cabecera + líneas debe/haber con
 * totales calculados con decimal.js, verificación visual de balance y reversión
 * atómica por contra-asiento. Nunca aritmética float sobre montos (R-CODE-4).
 */
import { useContext, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined';
import UndoOutlined from '@mui/icons-material/UndoOutlined';
import { contabilidadService, type AsientoContable } from '../../services/contabilidadService';
import { contabilidadKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { sumDecimals, toFixedStr } from '../../lib/decimal';
import { FeedbackContext } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader, StatusChip } from '../../components/ui';

export default function AsientoContableDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const feedback = useContext(FeedbackContext);
  const { id = '' } = useParams<{ id: string }>();

  const [revertirOpen, setRevertirOpen] = useState(false);
  const [motivo, setMotivo] = useState('');
  const [fechaReversion, setFechaReversion] = useState('');
  const [errorRevertir, setErrorRevertir] = useState('');
  const [contraGenerado, setContraGenerado] = useState<AsientoContable | null>(null);

  const {
    data: asiento,
    isLoading,
    error,
  } = useQuery({
    queryKey: contabilidadKeys.asiento(id),
    queryFn: () => contabilidadService.getAsiento(id),
    enabled: !!id,
  });

  const { data: planCuentas = [] } = useQuery({
    queryKey: contabilidadKeys.planCuentas(),
    queryFn: () => contabilidadService.getPlanCuentas(),
  });

  const revertirMutation = useMutation({
    mutationFn: () =>
      contabilidadService.revertirAsiento(id, {
        motivo: motivo.trim(),
        fecha_reversion: fechaReversion || null,
      }),
    onSuccess: (contra) => {
      setContraGenerado(contra);
      setRevertirOpen(false);
      setMotivo('');
      setFechaReversion('');
      feedback?.snackbar.success(t('contabilidad.detalle.revertidoOk', { numero: contra.numero_asiento }));
      void queryClient.invalidateQueries({ queryKey: contabilidadKeys.asiento(id) });
      void queryClient.invalidateQueries({ queryKey: contabilidadKeys.asientosAll() });
    },
    onError: (err: unknown) => {
      setErrorRevertir(mensajeDeError(err, t('contabilidad.detalle.errorRevertir')));
    },
  });

  if (isLoading) {
    return (
      <PageContainer>
        <CircularProgress />
      </PageContainer>
    );
  }

  if (error || !asiento) {
    return (
      <PageContainer>
        <Alert severity="error">{mensajeDeError(error, t('contabilidad.detalle.errorCargar'))}</Alert>
      </PageContainer>
    );
  }

  const detalles = asiento.detalles ?? [];
  // Totales con decimal.js — la verificación de balance jamás usa float.
  const totalDebe = sumDecimals(detalles.map((d) => d.debe));
  const totalHaber = sumDecimals(detalles.map((d) => d.haber));
  const cuadrado = totalDebe.equals(totalHaber);
  const tieneContactos = detalles.some((d) => Boolean(d.contacto_nombre || d.id_contacto));
  const puedeRevertir =
    asiento.estado_asiento === 'APROBADO' && !asiento.contra_asiento_id && !asiento.asiento_revertido;

  const nombreCuenta = (cuentaId: string): string => {
    const cuenta = planCuentas.find((c) => c.id_cuenta_contable === cuentaId);
    return cuenta ? `${cuenta.codigo_cuenta} — ${cuenta.nombre_cuenta}` : cuentaId;
  };

  return (
    <PageContainer>
      <PageHeader
        title={`${t('contabilidad.detalle.title')} ${asiento.numero_asiento}`}
        subtitle={asiento.descripcion}
        actions={
          <Stack direction="row" spacing={1}>
            {puedeRevertir && (
              <Button
                variant="outlined"
                color="warning"
                startIcon={<UndoOutlined />}
                onClick={() => {
                  setErrorRevertir('');
                  setRevertirOpen(true);
                }}
              >
                {t('contabilidad.detalle.revertir')}
              </Button>
            )}
            <Button startIcon={<ArrowBackOutlined />} onClick={() => navigate('/contabilidad/asientos')}>
              {t('common.back')}
            </Button>
          </Stack>
        }
      />

      {contraGenerado && (
        <Alert
          severity="success"
          sx={{ mb: 2 }}
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => navigate(`/contabilidad/asientos/${contraGenerado.id_asiento}`)}
            >
              {t('contabilidad.detalle.verContraAsiento')}
            </Button>
          }
        >
          {t('contabilidad.detalle.revertidoOk', { numero: contraGenerado.numero_asiento })}
        </Alert>
      )}

      {asiento.contra_asiento_id && !contraGenerado && (
        <Alert
          severity="info"
          sx={{ mb: 2 }}
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => navigate(`/contabilidad/asientos/${asiento.contra_asiento_id}`)}
            >
              {t('contabilidad.detalle.verContraAsiento')}
            </Button>
          }
        >
          {t('contabilidad.detalle.asientoYaRevertido')}
        </Alert>
      )}

      {asiento.asiento_revertido && (
        <Alert
          severity="info"
          sx={{ mb: 2 }}
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => navigate(`/contabilidad/asientos/${asiento.asiento_revertido}`)}
            >
              {t('contabilidad.detalle.verAsientoOriginal')}
            </Button>
          }
        >
          {t('contabilidad.detalle.esContraAsientoDe')}
        </Alert>
      )}

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3} alignItems={{ sm: 'center' }} flexWrap="wrap">
          <Typography variant="body2">
            <strong>{t('contabilidad.asientos.fecha')}:</strong> {asiento.fecha_asiento}
          </Typography>
          <Typography variant="body2">
            <strong>{t('contabilidad.asientos.origen')}:</strong>{' '}
            {asiento.nombre_modelo_origen || t('contabilidad.asientos.manual')}
          </Typography>
          {asiento.diario_nombre && (
            <Typography variant="body2">
              <strong>{t('contabilidad.detalle.diario')}:</strong> {asiento.diario_nombre}
            </Typography>
          )}
          <StatusChip value={asiento.estado_asiento} />
          <Chip
            size="small"
            color={cuadrado ? 'success' : 'error'}
            label={cuadrado ? t('contabilidad.detalle.cuadrado') : t('contabilidad.detalle.descuadrado')}
          />
          {asiento.asiento_revertido && (
            <Chip size="small" color="info" label={t('contabilidad.detalle.contraAsientoBadge')} />
          )}
          {asiento.es_cierre && (
            <Chip size="small" color="secondary" label={t('contabilidad.detalle.cierreBadge')} />
          )}
        </Stack>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          {t('contabilidad.detalle.lineas')}
        </Typography>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('contabilidad.detalle.cuenta')}</TableCell>
              {tieneContactos && <TableCell>{t('contabilidad.detalle.tercero')}</TableCell>}
              <TableCell>{t('contabilidad.detalle.descripcion')}</TableCell>
              <TableCell align="right">{t('contabilidad.detalle.debe')}</TableCell>
              <TableCell align="right">{t('contabilidad.detalle.haber')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {detalles.length === 0 && (
              <TableRow>
                <TableCell colSpan={tieneContactos ? 5 : 4}>
                  <Typography variant="body2" color="text.secondary">
                    {t('contabilidad.detalle.sinLineas')}
                  </Typography>
                </TableCell>
              </TableRow>
            )}
            {detalles.map((d) => (
              <TableRow key={d.id_detalle_asiento}>
                <TableCell>{nombreCuenta(d.id_cuenta_contable)}</TableCell>
                {tieneContactos && <TableCell>{d.contacto_nombre || d.id_contacto || '—'}</TableCell>}
                <TableCell>{d.descripcion_detalle || '—'}</TableCell>
                <TableCell align="right">{toFixedStr(d.debe)}</TableCell>
                <TableCell align="right">{toFixedStr(d.haber)}</TableCell>
              </TableRow>
            ))}
            <TableRow>
              <TableCell colSpan={tieneContactos ? 3 : 2}>
                <Typography variant="body2" fontWeight={700}>
                  {t('contabilidad.detalle.totales')}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Typography variant="body2" fontWeight={700}>
                  {toFixedStr(totalDebe)}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Typography variant="body2" fontWeight={700}>
                  {toFixedStr(totalHaber)}
                </Typography>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
        {!cuadrado && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {t('contabilidad.detalle.alertaDescuadre', {
              diferencia: toFixedStr(totalDebe.minus(totalHaber)),
            })}
          </Alert>
        )}
      </Paper>

      <Dialog open={revertirOpen} onClose={() => setRevertirOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('contabilidad.detalle.revertirTitulo')}</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            {t('contabilidad.detalle.revertirDescripcion')}
          </Alert>
          {errorRevertir && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {errorRevertir}
            </Alert>
          )}
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('contabilidad.detalle.motivoReversion')}
              fullWidth
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
            />
            <TextField
              label={t('contabilidad.detalle.fechaReversion')}
              type="date"
              fullWidth
              InputLabelProps={{ shrink: true }}
              value={fechaReversion}
              onChange={(e) => setFechaReversion(e.target.value)}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRevertirOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            color="warning"
            disabled={revertirMutation.isPending}
            onClick={() => {
              setErrorRevertir('');
              revertirMutation.mutate();
            }}
          >
            {t('contabilidad.detalle.confirmarReversion')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageContainer>
  );
}
