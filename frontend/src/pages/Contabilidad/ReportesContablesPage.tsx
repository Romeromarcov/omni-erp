/**
 * Reportes Financieros Canónicos (PR-14 · Ola B2):
 *   - Balance de Comprobación (saldo inicial + período + acumulado + jerarquía)
 *   - Estado de Resultados (P&L operativo, excluye es_cierre=True)
 *   - Balance General (verificando Activos = Pasivos + Patrimonio + Resultado)
 *   - Libro Mayor Auxiliar (cuenta / contacto / diario + saldo corrido Decimal)
 *
 * Incluye switch de equivalentes USD y exportación CSV / PDF ReportLab.
 */
import { useContext, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControlLabel,
  MenuItem,
  Paper,
  Stack,
  Switch,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import DownloadOutlined from '@mui/icons-material/DownloadOutlined';
import PictureAsPdfOutlined from '@mui/icons-material/PictureAsPdfOutlined';
import AccountBalanceOutlined from '@mui/icons-material/AccountBalanceOutlined';
import TrendingUpOutlined from '@mui/icons-material/TrendingUpOutlined';
import BalanceOutlined from '@mui/icons-material/BalanceOutlined';
import MenuBookOutlined from '@mui/icons-material/MenuBookOutlined';
import {
  contabilidadService,
  type BalanceComprobacionReport,
  type BalanceGeneralReport,
  type EstadoFinancieroCuenta,
  type EstadoResultadosReport,
  type FormatoExportReporte,
  type LibroMayorAuxiliarReport,
  type TipoReporteContable,
} from '../../services/contabilidadService';
import { contabilidadKeys } from '../../lib/queryKeys';
import { D, toFixedStr, type DecimalInput } from '../../lib/decimal';
import { mensajeDeError } from '../../utils/api';
import { getEmpresaId } from '../../utils/empresa';
import { FeedbackContext } from '../../contexts/feedbackTypes';
import { KpiCard, PageContainer, PageHeader } from '../../components/ui';

export type ReporteTabSlug =
  | 'balance-comprobacion'
  | 'estado-resultados'
  | 'balance-general'
  | 'mayor-auxiliar';

interface ReportesContablesPageProps {
  initialTab?: ReporteTabSlug;
}

function normalizarTabSlug(raw?: string | null): ReporteTabSlug {
  switch ((raw ?? '').trim().toLowerCase()) {
    case 'estado-resultados':
      return 'estado-resultados';
    case 'balance-general':
      return 'balance-general';
    case 'mayor-auxiliar':
    case 'libro-mayor-auxiliar':
      return 'mayor-auxiliar';
    default:
      return 'balance-comprobacion';
  }
}

function tabToBackendTipo(tab: ReporteTabSlug): TipoReporteContable {
  return tab === 'mayor-auxiliar' ? 'libro-mayor-auxiliar' : tab;
}

function fmtMonto(valor: DecimalInput): string {
  return toFixedStr(D(valor), 2);
}

function hoyIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function inicioAnioIso(): string {
  return `${new Date().getFullYear()}-01-01`;
}

export default function ReportesContablesPage({ initialTab }: ReportesContablesPageProps) {
  const { t } = useTranslation();
  const { tab: tabParam } = useParams<{ tab?: string }>();
  const feedback = useContext(FeedbackContext);
  const empresaId = getEmpresaId() || '';

  const resolvedInitial = normalizarTabSlug(initialTab ?? tabParam);
  const [tab, setTab] = useState<ReporteTabSlug>(resolvedInitial);

  useEffect(() => {
    if (initialTab || tabParam) {
      setTab(normalizarTabSlug(initialTab ?? tabParam));
    }
  }, [initialTab, tabParam]);

  // ── Filtros globales y por pestaña ───────────────────────────────────────
  const [incluirUsd, setIncluirUsd] = useState(false);
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');
  const [pnlDesde, setPnlDesde] = useState(() => inicioAnioIso());
  const [pnlHasta, setPnlHasta] = useState(() => hoyIso());
  const [fechaCorte, setFechaCorte] = useState(() => hoyIso());

  const [diarioId, setDiarioId] = useState('');
  const [cuentaId, setCuentaId] = useState('');
  const [contactoId, setContactoId] = useState('');
  const [mayorDesde, setMayorDesde] = useState('');
  const [mayorHasta, setMayorHasta] = useState('');

  const [exportando, setExportando] = useState<FormatoExportReporte | null>(null);
  const [exportError, setExportError] = useState('');

  // ── Catálogos para filtros ───────────────────────────────────────────────
  const { data: diarios = [] } = useQuery({
    queryKey: contabilidadKeys.diarios(),
    queryFn: () => contabilidadService.getDiarios(),
    enabled: Boolean(empresaId),
  });

  const { data: cuentasPlan = [] } = useQuery({
    queryKey: contabilidadKeys.planCuentas(),
    queryFn: () => contabilidadService.getPlanCuentas(),
    enabled: Boolean(empresaId),
  });

  const { data: contactos = [] } = useQuery({
    queryKey: contabilidadKeys.contactosSelector(empresaId),
    queryFn: () => contabilidadService.getContactosSelector(),
    enabled: Boolean(empresaId),
  });

  const cuentasOrdenadas = useMemo(
    () => [...cuentasPlan].sort((a, b) => a.codigo_cuenta.localeCompare(b.codigo_cuenta)),
    [cuentasPlan],
  );

  // ── Queries por reporte ──────────────────────────────────────────────────
  const bcQuery = useQuery<BalanceComprobacionReport>({
    queryKey: contabilidadKeys.balanceComprobacion({
      empresaId,
      fechaDesde,
      fechaHasta,
      idDiario: diarioId,
      incluirUsd,
    }),
    queryFn: () =>
      contabilidadService.getBalanceComprobacion({
        empresa_id: empresaId,
        fecha_desde: fechaDesde || undefined,
        fecha_hasta: fechaHasta || undefined,
        id_diario: diarioId || undefined,
        incluir_equivalentes_usd: incluirUsd,
      }),
    enabled: Boolean(empresaId) && tab === 'balance-comprobacion',
  });

  const pnlQuery = useQuery<EstadoResultadosReport>({
    queryKey: contabilidadKeys.estadoResultados({
      empresaId,
      fechaDesde: pnlDesde,
      fechaHasta: pnlHasta,
      incluirUsd,
    }),
    queryFn: () =>
      contabilidadService.getEstadoResultados({
        empresa_id: empresaId,
        fecha_desde: pnlDesde || undefined,
        fecha_hasta: pnlHasta || undefined,
        incluir_equivalentes_usd: incluirUsd,
      }),
    enabled: Boolean(empresaId) && tab === 'estado-resultados',
  });

  const bgQuery = useQuery<BalanceGeneralReport>({
    queryKey: contabilidadKeys.balanceGeneral({
      empresaId,
      fechaCorte,
      incluirUsd,
    }),
    queryFn: () =>
      contabilidadService.getBalanceGeneral({
        empresa_id: empresaId,
        fecha_corte: fechaCorte || undefined,
        incluir_equivalentes_usd: incluirUsd,
      }),
    enabled: Boolean(empresaId) && tab === 'balance-general',
  });

  const mayorQuery = useQuery<LibroMayorAuxiliarReport>({
    queryKey: contabilidadKeys.libroMayorAuxiliar({
      empresaId,
      idCuenta: cuentaId,
      idContacto: contactoId,
      idDiario: diarioId,
      fechaDesde: mayorDesde,
      fechaHasta: mayorHasta,
      incluirUsd,
    }),
    queryFn: () =>
      contabilidadService.getLibroMayorAuxiliar({
        empresa_id: empresaId,
        id_cuenta_contable: cuentaId || undefined,
        id_contacto: contactoId || undefined,
        id_diario: diarioId || undefined,
        fecha_desde: mayorDesde || undefined,
        fecha_hasta: mayorHasta || undefined,
        incluir_equivalentes_usd: incluirUsd,
      }),
    enabled: Boolean(empresaId) && tab === 'mayor-auxiliar',
  });

  const activeMeta =
    tab === 'balance-comprobacion'
      ? bcQuery.data
      : tab === 'estado-resultados'
        ? pnlQuery.data
        : tab === 'balance-general'
          ? bgQuery.data
          : mayorQuery.data;

  const activeError =
    tab === 'balance-comprobacion'
      ? bcQuery.error
      : tab === 'estado-resultados'
        ? pnlQuery.error
        : tab === 'balance-general'
          ? bgQuery.error
          : mayorQuery.error;

  const activeLoading =
    tab === 'balance-comprobacion'
      ? bcQuery.isLoading
      : tab === 'estado-resultados'
        ? pnlQuery.isLoading
        : tab === 'balance-general'
          ? bgQuery.isLoading
          : mayorQuery.isLoading;

  const mostrarColUsd = Boolean(incluirUsd && activeMeta?.usd_disponible);

  const handleExport = async (formato: FormatoExportReporte) => {
    if (!empresaId) return;
    setExportError('');
    setExportando(formato);
    const tipoBackend = tabToBackendTipo(tab);
    let filtros: Record<string, string | number | boolean | undefined>;
    if (tab === 'balance-comprobacion') {
      filtros = {
        empresa_id: empresaId,
        fecha_desde: fechaDesde || undefined,
        fecha_hasta: fechaHasta || undefined,
        id_diario: diarioId || undefined,
        incluir_equivalentes_usd: incluirUsd,
      };
    } else if (tab === 'estado-resultados') {
      filtros = {
        empresa_id: empresaId,
        fecha_desde: pnlDesde || undefined,
        fecha_hasta: pnlHasta || undefined,
        incluir_equivalentes_usd: incluirUsd,
      };
    } else if (tab === 'balance-general') {
      filtros = {
        empresa_id: empresaId,
        fecha_corte: fechaCorte || undefined,
        incluir_equivalentes_usd: incluirUsd,
      };
    } else {
      filtros = {
        empresa_id: empresaId,
        id_cuenta_contable: cuentaId || undefined,
        id_contacto: contactoId || undefined,
        id_diario: diarioId || undefined,
        fecha_desde: mayorDesde || undefined,
        fecha_hasta: mayorHasta || undefined,
        incluir_equivalentes_usd: incluirUsd,
      };
    }

    try {
      const blob = await contabilidadService.exportarReporteBlob(tipoBackend, formato, filtros);
      const url = URL.createObjectURL(blob);
      const enlace = document.createElement('a');
      enlace.href = url;
      enlace.download = `${tipoBackend}.${formato}`;
      document.body.appendChild(enlace);
      enlace.click();
      document.body.removeChild(enlace);
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      const msg = mensajeDeError(err, t('contabilidad.reportes.errorExportar'));
      setExportError(msg);
      feedback?.snackbar.error(msg);
    } finally {
      setExportando(null);
    }
  };

  const renderGrupoEstadoFinanciero = (
    titulo: string,
    filas: EstadoFinancieroCuenta[],
    totalBase: string,
    totalUsd?: string | null,
  ) => (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>
        {titulo}
      </Typography>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{t('contabilidad.reportes.codigo')}</TableCell>
              <TableCell>{t('contabilidad.reportes.nombreCuenta')}</TableCell>
              <TableCell align="right">{t('contabilidad.reportes.debe')}</TableCell>
              <TableCell align="right">{t('contabilidad.reportes.haber')}</TableCell>
              <TableCell align="right">{t('contabilidad.reportes.saldoFinal')}</TableCell>
              {mostrarColUsd && <TableCell align="right">{t('contabilidad.reportes.saldoUsd')}</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            {filas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={mostrarColUsd ? 6 : 5} align="center">
                  <Typography variant="body2" color="text.secondary">
                    {t('contabilidad.reportes.sinMovimientos')}
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              filas.map((c) => (
                <TableRow key={c.id_cuenta_contable}>
                  <TableCell>
                    <Typography variant="body2" fontFamily="monospace">
                      {c.codigo_cuenta}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ pl: Math.max(0, (c.nivel ?? 1) - 1) * 2 }}>
                      {c.nombre_cuenta}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">{fmtMonto(c.debe)}</TableCell>
                  <TableCell align="right">{fmtMonto(c.haber)}</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    {fmtMonto(c.saldo)}
                  </TableCell>
                  {mostrarColUsd && <TableCell align="right">{fmtMonto(c.saldo_usd ?? '0')}</TableCell>}
                </TableRow>
              ))
            )}
            <TableRow sx={{ '& td': { fontWeight: 700, bgcolor: 'action.hover' } }}>
              <TableCell colSpan={4}>
                {t('contabilidad.reportes.totales')} {titulo}
              </TableCell>
              <TableCell align="right">{fmtMonto(totalBase)}</TableCell>
              {mostrarColUsd && <TableCell align="right">{fmtMonto(totalUsd ?? '0')}</TableCell>}
            </TableRow>
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );

  return (
    <PageContainer>
      <PageHeader
        title={t('contabilidad.reportes.title')}
        subtitle={t('contabilidad.reportes.subtitle')}
        actions={
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              startIcon={<DownloadOutlined />}
              disabled={!empresaId || exportando !== null}
              onClick={() => void handleExport('csv')}
            >
              {t('contabilidad.reportes.exportarCsv')}
            </Button>
            <Button
              variant="contained"
              startIcon={<PictureAsPdfOutlined />}
              disabled={!empresaId || exportando !== null}
              onClick={() => void handleExport('pdf')}
            >
              {t('contabilidad.reportes.exportarPdf')}
            </Button>
          </Stack>
        }
      />

      {!empresaId && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {t('contabilidad.reportes.sinEmpresa')}
        </Alert>
      )}

      {exportError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {exportError}
        </Alert>
      )}

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs
          value={tab}
          onChange={(_e, next: ReporteTabSlug) => setTab(next)}
          variant="scrollable"
          scrollButtons="auto"
        >
          <Tab value="balance-comprobacion" label={t('contabilidad.reportes.tabBalanceComprobacion')} />
          <Tab value="estado-resultados" label={t('contabilidad.reportes.tabEstadoResultados')} />
          <Tab value="balance-general" label={t('contabilidad.reportes.tabBalanceGeneral')} />
          <Tab value="mayor-auxiliar" label={t('contabilidad.reportes.tabMayorAuxiliar')} />
        </Tabs>
      </Box>

      {/* Barra de filtros por reporte + switch USD */}
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }} flexWrap="wrap" useFlexGap>
          {tab === 'balance-comprobacion' && (
            <>
              <TextField
                size="small"
                type="date"
                label={t('contabilidad.reportes.desde')}
                value={fechaDesde}
                onChange={(e) => setFechaDesde(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                size="small"
                type="date"
                label={t('contabilidad.reportes.hasta')}
                value={fechaHasta}
                onChange={(e) => setFechaHasta(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                select
                size="small"
                label={t('contabilidad.reportes.diario')}
                value={diarioId}
                onChange={(e) => setDiarioId(e.target.value)}
                sx={{ minWidth: 200 }}
              >
                <MenuItem value="">{t('contabilidad.reportes.todosDiarios')}</MenuItem>
                {diarios.map((d) => (
                  <MenuItem key={d.id_diario} value={d.id_diario}>
                    {d.codigo} — {d.nombre}
                  </MenuItem>
                ))}
              </TextField>
            </>
          )}

          {tab === 'estado-resultados' && (
            <>
              <TextField
                size="small"
                type="date"
                label={t('contabilidad.reportes.desde')}
                value={pnlDesde}
                onChange={(e) => setPnlDesde(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                size="small"
                type="date"
                label={t('contabilidad.reportes.hasta')}
                value={pnlHasta}
                onChange={(e) => setPnlHasta(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
            </>
          )}

          {tab === 'balance-general' && (
            <TextField
              size="small"
              type="date"
              label={t('contabilidad.reportes.fechaCorte')}
              value={fechaCorte}
              onChange={(e) => setFechaCorte(e.target.value)}
              InputLabelProps={{ shrink: true }}
            />
          )}

          {tab === 'mayor-auxiliar' && (
            <>
              <TextField
                select
                size="small"
                label={t('contabilidad.reportes.cuenta')}
                value={cuentaId}
                onChange={(e) => setCuentaId(e.target.value)}
                sx={{ minWidth: 220 }}
              >
                <MenuItem value="">{t('contabilidad.reportes.todasCuentas')}</MenuItem>
                {cuentasOrdenadas.map((c) => (
                  <MenuItem key={c.id_cuenta_contable} value={c.id_cuenta_contable}>
                    {c.codigo_cuenta} — {c.nombre_cuenta}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                size="small"
                label={t('contabilidad.reportes.contacto')}
                value={contactoId}
                onChange={(e) => setContactoId(e.target.value)}
                sx={{ minWidth: 200 }}
              >
                <MenuItem value="">{t('contabilidad.reportes.todosContactos')}</MenuItem>
                {contactos.map((c) => (
                  <MenuItem key={c.id_contacto} value={c.id_contacto}>
                    {c.nombre_completo || c.nombre || c.id_contacto}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                size="small"
                label={t('contabilidad.reportes.diario')}
                value={diarioId}
                onChange={(e) => setDiarioId(e.target.value)}
                sx={{ minWidth: 180 }}
              >
                <MenuItem value="">{t('contabilidad.reportes.todosDiarios')}</MenuItem>
                {diarios.map((d) => (
                  <MenuItem key={d.id_diario} value={d.id_diario}>
                    {d.codigo} — {d.nombre}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                size="small"
                type="date"
                label={t('contabilidad.reportes.desde')}
                value={mayorDesde}
                onChange={(e) => setMayorDesde(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                size="small"
                type="date"
                label={t('contabilidad.reportes.hasta')}
                value={mayorHasta}
                onChange={(e) => setMayorHasta(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
            </>
          )}

          <FormControlLabel
            control={<Switch checked={incluirUsd} onChange={(e) => setIncluirUsd(e.target.checked)} />}
            label={t('contabilidad.reportes.mostrarUsd')}
          />

          {activeMeta?.moneda_base && incluirUsd && activeMeta.usd_disponible && activeMeta.tasa_usd && (
            <Chip
              size="small"
              color="info"
              variant="outlined"
              label={t('contabilidad.reportes.tasaUsdInfo', {
                moneda: activeMeta.moneda_base,
                tasa: activeMeta.tasa_usd,
              })}
            />
          )}
        </Stack>
      </Paper>

      {incluirUsd && activeMeta && !activeMeta.usd_disponible && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {activeMeta.usd_mensaje || t('contabilidad.reportes.sinTasaUsd')}
        </Alert>
      )}

      {activeError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {mensajeDeError(activeError, t('contabilidad.reportes.errorCargar'))}
        </Alert>
      )}

      {activeLoading && (
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress />
        </Box>
      )}

      {/* ── Tab 1: Balance de Comprobación ─────────────────────────────────── */}
      {!activeLoading && tab === 'balance-comprobacion' && bcQuery.data && (
        <TableContainer component={Paper} variant="outlined" sx={{ overflowX: 'auto' }}>
          <Table size="small" sx={{ minWidth: 850 }}>
            <TableHead>
              <TableRow>
                <TableCell>{t('contabilidad.reportes.codigo')}</TableCell>
                <TableCell>{t('contabilidad.reportes.nombreCuenta')}</TableCell>
                <TableCell>{t('contabilidad.reportes.tipo')}</TableCell>
                <TableCell align="right">{t('contabilidad.reportes.saldoInicial')}</TableCell>
                <TableCell align="right">{t('contabilidad.reportes.debe')}</TableCell>
                <TableCell align="right">{t('contabilidad.reportes.haber')}</TableCell>
                <TableCell align="right">{t('contabilidad.reportes.debeAcum')}</TableCell>
                <TableCell align="right">{t('contabilidad.reportes.haberAcum')}</TableCell>
                <TableCell align="right">{t('contabilidad.reportes.saldoFinal')}</TableCell>
                {mostrarColUsd && <TableCell align="right">{t('contabilidad.reportes.debeUsd')}</TableCell>}
                {mostrarColUsd && <TableCell align="right">{t('contabilidad.reportes.haberUsd')}</TableCell>}
                {mostrarColUsd && <TableCell align="right">{t('contabilidad.reportes.saldoUsd')}</TableCell>}
              </TableRow>
            </TableHead>
            <TableBody>
              {bcQuery.data.cuentas.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={mostrarColUsd ? 12 : 9} align="center">
                    <Typography variant="body2" color="text.secondary" py={2}>
                      {t('contabilidad.reportes.sinMovimientos')}
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                bcQuery.data.cuentas.map((c) => (
                  <TableRow key={c.id_cuenta_contable}>
                    <TableCell>
                      <Typography variant="body2" fontFamily="monospace" fontWeight={600}>
                        {c.codigo_cuenta}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ pl: Math.max(0, (c.nivel ?? 1) - 1) * 2 }}>
                        {c.nombre_cuenta}
                      </Typography>
                    </TableCell>
                    <TableCell>{c.tipo_cuenta}</TableCell>
                    <TableCell align="right">{fmtMonto(c.saldo_inicial)}</TableCell>
                    <TableCell align="right">{fmtMonto(c.debe_periodo)}</TableCell>
                    <TableCell align="right">{fmtMonto(c.haber_periodo)}</TableCell>
                    <TableCell align="right">{fmtMonto(c.debe_final_acum)}</TableCell>
                    <TableCell align="right">{fmtMonto(c.haber_final_acum)}</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600 }}>
                      {fmtMonto(c.saldo)}
                    </TableCell>
                    {mostrarColUsd && <TableCell align="right">{fmtMonto(c.debe_usd ?? '0')}</TableCell>}
                    {mostrarColUsd && <TableCell align="right">{fmtMonto(c.haber_usd ?? '0')}</TableCell>}
                    {mostrarColUsd && <TableCell align="right">{fmtMonto(c.saldo_usd ?? '0')}</TableCell>}
                  </TableRow>
                ))
              )}
              <TableRow sx={{ '& td': { fontWeight: 700, bgcolor: 'action.hover' } }}>
                <TableCell colSpan={4}>{t('contabilidad.reportes.totales')}</TableCell>
                <TableCell align="right">{fmtMonto(bcQuery.data.total_debe)}</TableCell>
                <TableCell align="right">{fmtMonto(bcQuery.data.total_haber)}</TableCell>
                <TableCell align="right">{fmtMonto(bcQuery.data.total_debe_final_acum)}</TableCell>
                <TableCell align="right">{fmtMonto(bcQuery.data.total_haber_final_acum)}</TableCell>
                <TableCell align="right">—</TableCell>
                {mostrarColUsd && (
                  <TableCell align="right">{fmtMonto(bcQuery.data.total_debe_usd ?? '0')}</TableCell>
                )}
                {mostrarColUsd && (
                  <TableCell align="right">{fmtMonto(bcQuery.data.total_haber_usd ?? '0')}</TableCell>
                )}
                {mostrarColUsd && <TableCell align="right">—</TableCell>}
              </TableRow>
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* ── Tab 2: Estado de Resultados (P&L) ──────────────────────────────── */}
      {!activeLoading && tab === 'estado-resultados' && pnlQuery.data && (
        <Box>
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 2, mb: 3 }}>
            <KpiCard
              label={t('contabilidad.reportes.totalIngresos')}
              value={fmtMonto(pnlQuery.data.total_ingresos)}
              caption={mostrarColUsd ? `USD ${fmtMonto(pnlQuery.data.total_ingresos_usd ?? '0')}` : undefined}
              icon={<TrendingUpOutlined />}
              tone="success"
            />
            <KpiCard
              label={t('contabilidad.reportes.totalCostos')}
              value={fmtMonto(pnlQuery.data.total_costos)}
              caption={mostrarColUsd ? `USD ${fmtMonto(pnlQuery.data.total_costos_usd ?? '0')}` : undefined}
              icon={<BalanceOutlined />}
              tone="warning"
            />
            <KpiCard
              label={t('contabilidad.reportes.utilidadBruta')}
              value={fmtMonto(pnlQuery.data.utilidad_bruta)}
              caption={mostrarColUsd ? `USD ${fmtMonto(pnlQuery.data.utilidad_bruta_usd ?? '0')}` : undefined}
              icon={<AccountBalanceOutlined />}
              tone="tint"
            />
            <KpiCard
              label={t('contabilidad.reportes.resultadoNeto')}
              value={fmtMonto(pnlQuery.data.resultado_neto)}
              caption={mostrarColUsd ? `USD ${fmtMonto(pnlQuery.data.resultado_neto_usd ?? '0')}` : undefined}
              icon={<TrendingUpOutlined />}
              tone={D(pnlQuery.data.resultado_neto).gte(0) ? 'brand' : 'error'}
              emphasizeError={D(pnlQuery.data.resultado_neto).lt(0)}
            />
          </Box>
          {renderGrupoEstadoFinanciero(
            t('contabilidad.reportes.ingresos'),
            pnlQuery.data.ingresos,
            pnlQuery.data.total_ingresos,
            pnlQuery.data.total_ingresos_usd,
          )}
          {renderGrupoEstadoFinanciero(
            t('contabilidad.reportes.costos'),
            pnlQuery.data.costos,
            pnlQuery.data.total_costos,
            pnlQuery.data.total_costos_usd,
          )}
          {renderGrupoEstadoFinanciero(
            t('contabilidad.reportes.gastos'),
            pnlQuery.data.gastos,
            pnlQuery.data.total_gastos,
            pnlQuery.data.total_gastos_usd,
          )}
        </Box>
      )}

      {/* ── Tab 3: Balance General ─────────────────────────────────────────── */}
      {!activeLoading && tab === 'balance-general' && bgQuery.data && (
        <Box>
          <Alert severity={bgQuery.data.ecuacion_cuadrada ? 'success' : 'error'} sx={{ mb: 2 }}>
            {bgQuery.data.ecuacion_cuadrada
              ? t('contabilidad.reportes.ecuacionCuadrada')
              : t('contabilidad.reportes.ecuacionDescuadrada')}{' '}
            ({fmtMonto(bgQuery.data.total_activos)} ={' '}
            {fmtMonto(bgQuery.data.total_pasivo_patrimonio_y_resultado)})
          </Alert>
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 2, mb: 3 }}>
            <KpiCard
              label={t('contabilidad.reportes.totalActivos')}
              value={fmtMonto(bgQuery.data.total_activos)}
              caption={mostrarColUsd ? `USD ${fmtMonto(bgQuery.data.total_activos_usd ?? '0')}` : undefined}
              icon={<AccountBalanceOutlined />}
              tone="brand"
            />
            <KpiCard
              label={t('contabilidad.reportes.totalPasivos')}
              value={fmtMonto(bgQuery.data.total_pasivos)}
              caption={mostrarColUsd ? `USD ${fmtMonto(bgQuery.data.total_pasivos_usd ?? '0')}` : undefined}
              icon={<BalanceOutlined />}
              tone="warning"
            />
            <KpiCard
              label={t('contabilidad.reportes.totalPatrimonio')}
              value={fmtMonto(bgQuery.data.total_patrimonio)}
              caption={mostrarColUsd ? `USD ${fmtMonto(bgQuery.data.total_patrimonio_usd ?? '0')}` : undefined}
              icon={<BalanceOutlined />}
              tone="tint"
            />
            <KpiCard
              label={t('contabilidad.reportes.resultadoPeriodo')}
              value={fmtMonto(bgQuery.data.resultado_periodo)}
              caption={
                mostrarColUsd ? `USD ${fmtMonto(bgQuery.data.resultado_periodo_usd ?? '0')}` : undefined
              }
              icon={<TrendingUpOutlined />}
              tone="success"
            />
          </Box>
          {renderGrupoEstadoFinanciero(
            t('contabilidad.reportes.activos'),
            bgQuery.data.activos,
            bgQuery.data.total_activos,
            bgQuery.data.total_activos_usd,
          )}
          {renderGrupoEstadoFinanciero(
            t('contabilidad.reportes.pasivos'),
            bgQuery.data.pasivos,
            bgQuery.data.total_pasivos,
            bgQuery.data.total_pasivos_usd,
          )}
          {renderGrupoEstadoFinanciero(
            t('contabilidad.reportes.patrimonio'),
            bgQuery.data.patrimonio,
            bgQuery.data.total_patrimonio,
            bgQuery.data.total_patrimonio_usd,
          )}
        </Box>
      )}

      {/* ── Tab 4: Libro Mayor Auxiliar ────────────────────────────────────── */}
      {!activeLoading && tab === 'mayor-auxiliar' && mayorQuery.data && (
        <Box>
          {mayorQuery.data.truncado && (
            <Alert severity="info" sx={{ mb: 2 }}>
              {t('contabilidad.reportes.truncadoAviso', { limit: mayorQuery.data.limit })}
            </Alert>
          )}
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 2, mb: 3 }}>
            <KpiCard
              label={t('contabilidad.reportes.saldoInicial')}
              value={fmtMonto(mayorQuery.data.saldo_inicial)}
              caption={mostrarColUsd ? `USD ${fmtMonto(mayorQuery.data.saldo_inicial_usd ?? '0')}` : undefined}
              icon={<MenuBookOutlined />}
              tone="tint"
            />
            <KpiCard
              label={t('contabilidad.reportes.debe')}
              value={fmtMonto(mayorQuery.data.total_debe)}
              caption={mostrarColUsd ? `USD ${fmtMonto(mayorQuery.data.total_debe_usd ?? '0')}` : undefined}
              icon={<TrendingUpOutlined />}
              tone="success"
            />
            <KpiCard
              label={t('contabilidad.reportes.haber')}
              value={fmtMonto(mayorQuery.data.total_haber)}
              caption={mostrarColUsd ? `USD ${fmtMonto(mayorQuery.data.total_haber_usd ?? '0')}` : undefined}
              icon={<BalanceOutlined />}
              tone="warning"
            />
            <KpiCard
              label={t('contabilidad.reportes.saldoFinalMayor')}
              value={fmtMonto(mayorQuery.data.saldo_final)}
              caption={mostrarColUsd ? `USD ${fmtMonto(mayorQuery.data.saldo_final_usd ?? '0')}` : undefined}
              icon={<AccountBalanceOutlined />}
              tone="brand"
            />
          </Box>
          <TableContainer component={Paper} variant="outlined" sx={{ overflowX: 'auto' }}>
            <Table size="small" sx={{ minWidth: 900 }}>
              <TableHead>
                <TableRow>
                  <TableCell>{t('contabilidad.reportes.fecha')}</TableCell>
                  <TableCell>{t('contabilidad.reportes.asiento')}</TableCell>
                  <TableCell>{t('contabilidad.reportes.diario')}</TableCell>
                  <TableCell>{t('contabilidad.reportes.nombreCuenta')}</TableCell>
                  <TableCell>{t('contabilidad.reportes.contacto')}</TableCell>
                  <TableCell>{t('contabilidad.reportes.descripcion')}</TableCell>
                  <TableCell align="right">{t('contabilidad.reportes.debe')}</TableCell>
                  <TableCell align="right">{t('contabilidad.reportes.haber')}</TableCell>
                  <TableCell align="right">{t('contabilidad.reportes.saldoCorrido')}</TableCell>
                  {mostrarColUsd && <TableCell align="right">{t('contabilidad.reportes.saldoUsd')}</TableCell>}
                </TableRow>
              </TableHead>
              <TableBody>
                {mayorQuery.data.movimientos.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={mostrarColUsd ? 10 : 9} align="center">
                      <Typography variant="body2" color="text.secondary" py={2}>
                        {t('contabilidad.reportes.sinMovimientos')}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  mayorQuery.data.movimientos.map((m) => (
                    <TableRow key={m.id_detalle_asiento}>
                      <TableCell>{m.fecha_asiento}</TableCell>
                      <TableCell>
                        <Typography variant="body2" fontFamily="monospace">
                          {m.numero_asiento}
                        </Typography>
                      </TableCell>
                      <TableCell>{m.diario_codigo || m.diario_nombre || '—'}</TableCell>
                      <TableCell>
                        {m.codigo_cuenta} — {m.nombre_cuenta}
                      </TableCell>
                      <TableCell>{m.contacto_nombre || '—'}</TableCell>
                      <TableCell>{m.descripcion_detalle || m.descripcion_asiento}</TableCell>
                      <TableCell align="right">{fmtMonto(m.debe)}</TableCell>
                      <TableCell align="right">{fmtMonto(m.haber)}</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                        {fmtMonto(m.saldo_corrido)}
                      </TableCell>
                      {mostrarColUsd && <TableCell align="right">{fmtMonto(m.saldo_corrido_usd ?? '0')}</TableCell>}
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}
    </PageContainer>
  );
}
