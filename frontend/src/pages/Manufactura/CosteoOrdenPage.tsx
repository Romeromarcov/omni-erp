/**
 * Costeo real de la OF (1.I): desglose materiales (snapshot del movimiento de
 * inventario) + mano de obra (etapas) + overhead → costo total y unitario.
 * Los montos llegan como string decimal y se formatean con decimal.js
 * (R-CODE-4) — nunca aritmética float.
 */
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { manufacturaService } from '../../services/manufacturaService';
import { manufacturaKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { D, toFixedStr, type DecimalInput } from '../../lib/decimal';
import { PageContainer, PageHeader } from '../../components/ui';

/** Participación % de una partida en el total — con decimal.js, sin float. */
function participacion(parte: DecimalInput, total: DecimalInput): string {
  const t = D(total);
  if (t.isZero()) return '0.0';
  return D(parte).div(t).times(100).toFixed(1);
}

export default function CosteoOrdenPage() {
  const { id = '' } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: manufacturaKeys.costeo(id),
    queryFn: () => manufacturaService.getCosteo(id),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <PageContainer>
        <Stack alignItems="center" sx={{ py: 8 }}>
          <CircularProgress />
        </Stack>
      </PageContainer>
    );
  }

  if (error || !data) {
    return (
      <PageContainer>
        <Alert severity="error">{mensajeDeError(error, t('manufactura.costeo.error'))}</Alert>
      </PageContainer>
    );
  }

  const { costo, etapas } = data;
  const partidas = [
    { key: 'materiales', label: t('manufactura.costeo.materiales'), monto: costo.costo_materiales },
    { key: 'manoObra', label: t('manufactura.costeo.manoObra'), monto: costo.mano_obra },
    { key: 'overhead', label: t('manufactura.costeo.overhead'), monto: costo.costos_indirectos },
  ];
  const etapasCompletadas = etapas.filter((e) => e.estado === 'completada');

  return (
    <PageContainer>
      <PageHeader
        title={t('manufactura.costeo.title')}
        subtitle={t('manufactura.costeo.subtitle')}
        actions={
          <Button variant="outlined" onClick={() => navigate(`/manufactura/ordenes/${id}`)}>
            {t('common.back')}
          </Button>
        }
      />

      <TableContainer component={Paper} variant="outlined" sx={{ mb: 3 }}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>{t('manufactura.costeo.partida')}</TableCell>
              <TableCell align="right">{t('manufactura.comun.monto')}</TableCell>
              <TableCell align="right">{t('manufactura.costeo.participacion')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {partidas.map((p) => (
              <TableRow key={p.key}>
                <TableCell>{p.label}</TableCell>
                <TableCell align="right">{toFixedStr(p.monto)}</TableCell>
                <TableCell align="right">{participacion(p.monto, costo.costo_total)}%</TableCell>
              </TableRow>
            ))}
            <TableRow>
              <TableCell>
                <Typography fontWeight={700}>{t('manufactura.costeo.total')}</Typography>
              </TableCell>
              <TableCell align="right">
                <Typography fontWeight={700}>{toFixedStr(costo.costo_total)}</Typography>
              </TableCell>
              <TableCell align="right">100.0%</TableCell>
            </TableRow>
            <TableRow>
              <TableCell>
                <Typography fontWeight={700}>{t('manufactura.costeo.unitario')}</Typography>
              </TableCell>
              <TableCell align="right">
                <Typography fontWeight={700}>{toFixedStr(costo.costo_unitario, 4)}</Typography>
              </TableCell>
              <TableCell />
            </TableRow>
          </TableBody>
        </Table>
      </TableContainer>

      <Typography variant="h6" sx={{ mb: 1 }}>
        {t('manufactura.costeo.detalleEtapas')}
      </Typography>
      <TableContainer component={Paper} variant="outlined">
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>{t('manufactura.costeo.etapa')}</TableCell>
              <TableCell align="right">{t('manufactura.costeo.horas')}</TableCell>
              <TableCell align="right">{t('manufactura.costeo.tarifa')}</TableCell>
              <TableCell align="right">{t('manufactura.costeo.destajo')}</TableCell>
              <TableCell align="right">{t('manufactura.costeo.costoMO')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {etapasCompletadas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} align="center">
                  <Typography variant="body2" color="text.secondary">
                    {t('manufactura.comun.sinDatos')}
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              etapasCompletadas.map((e) => (
                <TableRow key={e.id}>
                  <TableCell>
                    {e.orden}. {e.etapa_nombre}
                  </TableCell>
                  <TableCell align="right">{e.horas_trabajadas}</TableCell>
                  <TableCell align="right">{toFixedStr(e.tarifa_hora)}</TableCell>
                  <TableCell align="right">{toFixedStr(e.pago_destajo)}</TableCell>
                  <TableCell align="right">{toFixedStr(e.costo_mano_obra)}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </PageContainer>
  );
}
