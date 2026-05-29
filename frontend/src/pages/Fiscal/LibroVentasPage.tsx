import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import DownloadIcon from '@mui/icons-material/Download';
import { useAuth } from '../../contexts/AuthContext';
import PageLayout from '../../components/PageLayout';
import { libroService, type LibroEntry } from '../../services/fiscalService';

function currentPeriodo(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

const LibroVentasPage: React.FC = () => {
  const { user } = useAuth();
  const empresaId = user?.empresas?.[0]?.id_empresa ?? '';

  const [periodo, setPeriodo] = useState(currentPeriodo());
  const [queryPeriodo, setQueryPeriodo] = useState('');
  const [downloadError, setDownloadError] = useState('');
  const [downloading, setDownloading] = useState(false);

  const { data: entries = [], isLoading, isError, error } = useQuery<LibroEntry[]>({
    queryKey: ['libro-ventas', empresaId, queryPeriodo],
    queryFn: () => libroService.fetchLibroVentasTxt(empresaId, queryPeriodo),
    enabled: !!empresaId && !!queryPeriodo,
  });

  function handleConsultar() {
    if (periodo) setQueryPeriodo(periodo);
  }

  async function handleDownload() {
    setDownloadError('');
    setDownloading(true);
    try {
      await libroService.downloadLibroVentasTxt(empresaId, queryPeriodo);
    } catch (e) {
      setDownloadError((e as Error).message);
    } finally {
      setDownloading(false);
    }
  }

  const totalBase = entries.reduce((s, e) => s + parseFloat(e.base_imponible || '0'), 0);
  const totalIva = entries.reduce((s, e) => s + parseFloat(e.iva || '0'), 0);
  const totalTotal = entries.reduce((s, e) => s + parseFloat(e.total || '0'), 0);

  const fmt = (n: number) => n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <PageLayout maxWidth={1100}>
      <Typography variant="h5">Libro de Ventas — SENIAT</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Consulta y exporta el libro de ventas en formato TXT SENIAT.
      </Typography>

      {/* Filter bar */}
      <Stack direction="row" spacing={1.5} alignItems="flex-end" flexWrap="wrap" useFlexGap mb={3}>
        <TextField
          type="month"
          label="Período (AAAA-MM)"
          value={periodo}
          onChange={(e) => setPeriodo(e.target.value)}
          InputLabelProps={{ shrink: true }}
          size="small"
        />
        <Button variant="contained" onClick={handleConsultar} disabled={!periodo || !empresaId}>
          Consultar
        </Button>
        {queryPeriodo && entries.length > 0 && (
          <Button variant="contained" color="success" startIcon={<DownloadIcon />} onClick={handleDownload} disabled={downloading}>
            {downloading ? 'Descargando…' : 'Exportar TXT'}
          </Button>
        )}
      </Stack>

      {downloadError && <Alert severity="error" sx={{ mb: 2 }}>{downloadError}</Alert>}

      {isLoading && <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>}

      {isError && (
        <Alert severity="error">{(error as Error)?.message ?? 'Error al cargar el libro de ventas.'}</Alert>
      )}

      {!isLoading && !isError && queryPeriodo && entries.length === 0 && (
        <Typography align="center" color="text.secondary" py={4}>
          No hay facturas en el período {queryPeriodo}.
        </Typography>
      )}

      {entries.length > 0 && (
        <>
          {/* Summary cards */}
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 3 }}>
            {[
              { label: 'Facturas', value: String(entries.length), color: 'primary.main' },
              { label: 'Base imponible', value: fmt(totalBase), color: 'success.main' },
              { label: 'IVA', value: fmt(totalIva), color: 'warning.dark' },
              { label: 'Total', value: fmt(totalTotal), color: 'secondary.main' },
            ].map((c) => (
              <Card key={c.label} variant="outlined" sx={{ flex: '1 1 140px' }}>
                <CardContent>
                  <Typography variant="caption" color="text.secondary">{c.label}</Typography>
                  <Typography variant="h6" sx={{ fontWeight: 700, color: c.color }}>{c.value}</Typography>
                </CardContent>
              </Card>
            ))}
          </Box>

          {/* Table */}
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>RIF Emisor</TableCell>
                  <TableCell>RIF Receptor</TableCell>
                  <TableCell>Fecha</TableCell>
                  <TableCell align="right">Nro. Control</TableCell>
                  <TableCell align="right">Nro. Factura</TableCell>
                  <TableCell align="right">Base Imponible</TableCell>
                  <TableCell align="right">IVA</TableCell>
                  <TableCell align="right">Total</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {entries.map((e, idx) => (
                  <TableRow key={idx}>
                    <TableCell>{e.rif_emisor}</TableCell>
                    <TableCell>{e.rif_receptor}</TableCell>
                    <TableCell>{e.fecha}</TableCell>
                    <TableCell align="right">{e.nro_ctrl}</TableCell>
                    <TableCell align="right">{e.nro_fac}</TableCell>
                    <TableCell align="right">{fmt(parseFloat(e.base_imponible || '0'))}</TableCell>
                    <TableCell align="right">{fmt(parseFloat(e.iva || '0'))}</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600 }}>{fmt(parseFloat(e.total || '0'))}</TableCell>
                  </TableRow>
                ))}
                <TableRow sx={{ '& td': { fontWeight: 700 } }}>
                  <TableCell colSpan={5}>TOTALES</TableCell>
                  <TableCell align="right">{fmt(totalBase)}</TableCell>
                  <TableCell align="right">{fmt(totalIva)}</TableCell>
                  <TableCell align="right">{fmt(totalTotal)}</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}
    </PageLayout>
  );
};

export default LibroVentasPage;
