/**
 * Detalle de asiento contable (workstream F) — cabecera + líneas debe/haber con
 * totales calculados con decimal.js y verificación visual de balance
 * (cuadrado/descuadrado). Nunca aritmética float sobre montos (R-CODE-4).
 */
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  Chip,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined';
import { contabilidadService } from '../../services/contabilidadService';
import { contabilidadKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { sumDecimals, toFixedStr } from '../../lib/decimal';
import { PageContainer, PageHeader, StatusChip } from '../../components/ui';

export default function AsientoContableDetailPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id = '' } = useParams<{ id: string }>();

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
          <Button startIcon={<ArrowBackOutlined />} onClick={() => navigate('/contabilidad/asientos')}>
            {t('common.back')}
          </Button>
        }
      />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3} alignItems={{ sm: 'center' }}>
          <Typography variant="body2">
            <strong>{t('contabilidad.asientos.fecha')}:</strong> {asiento.fecha_asiento}
          </Typography>
          <Typography variant="body2">
            <strong>{t('contabilidad.asientos.origen')}:</strong>{' '}
            {asiento.nombre_modelo_origen || t('contabilidad.asientos.manual')}
          </Typography>
          <StatusChip value={asiento.estado_asiento} />
          <Chip
            size="small"
            color={cuadrado ? 'success' : 'error'}
            label={cuadrado ? t('contabilidad.detalle.cuadrado') : t('contabilidad.detalle.descuadrado')}
          />
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
              <TableCell>{t('contabilidad.detalle.descripcion')}</TableCell>
              <TableCell align="right">{t('contabilidad.detalle.debe')}</TableCell>
              <TableCell align="right">{t('contabilidad.detalle.haber')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {detalles.length === 0 && (
              <TableRow>
                <TableCell colSpan={4}>
                  <Typography variant="body2" color="text.secondary">
                    {t('contabilidad.detalle.sinLineas')}
                  </Typography>
                </TableCell>
              </TableRow>
            )}
            {detalles.map((d) => (
              <TableRow key={d.id_detalle_asiento}>
                <TableCell>{nombreCuenta(d.id_cuenta_contable)}</TableCell>
                <TableCell>{d.descripcion_detalle || '—'}</TableCell>
                <TableCell align="right">{toFixedStr(d.debe)}</TableCell>
                <TableCell align="right">{toFixedStr(d.haber)}</TableCell>
              </TableRow>
            ))}
            <TableRow>
              <TableCell colSpan={2}>
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
    </PageContainer>
  );
}
