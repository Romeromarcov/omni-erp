/**
 * Movimientos bancarios (workstream F) — líneas del extracto bancario con
 * filtros por cuenta y estado, e import de extracto CSV
 * (fecha,descripcion,tipo,monto,referencia).
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
import UploadFileOutlined from '@mui/icons-material/UploadFileOutlined';
import { tesoreriaService } from '../../services/tesoreriaService';
import type { MovimientoBancario } from '../../services/tesoreriaService';
import { tesoreriaKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { toFixedStr } from '../../lib/decimal';
import { getEmpresaId } from '../../utils/empresa';
import { useSnackbar } from '../../contexts/feedbackTypes';
import Pagination from '../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

const PAGE_SIZE = 20;
const ESTADOS = ['PENDIENTE', 'CONCILIADO', 'DESCARTADO'] as const;

export default function MovimientosBancariosPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const empresaId = getEmpresaId() || '';
  const [page, setPage] = useState(1);
  const [cuenta, setCuenta] = useState('');
  const [estado, setEstado] = useState('');
  const [importOpen, setImportOpen] = useState(false);
  const [cuentaImport, setCuentaImport] = useState('');
  const [archivo, setArchivo] = useState<File | null>(null);
  const [errorImport, setErrorImport] = useState('');

  const filtros = { cuenta, estado };
  const { data, isLoading } = useQuery({
    queryKey: tesoreriaKeys.movimientos(page, filtros),
    queryFn: () => tesoreriaService.getMovimientosBancariosPaginated(page, PAGE_SIZE, filtros),
  });

  const { data: cuentasBancarias = [] } = useQuery({
    queryKey: tesoreriaKeys.cuentasBancarias(empresaId),
    queryFn: () => tesoreriaService.getCuentasBancarias(empresaId),
    enabled: !!empresaId,
  });

  const importMutation = useMutation({
    mutationFn: ({ cuentaId, file }: { cuentaId: string; file: File }) =>
      tesoreriaService.importarCsv(empresaId, cuentaId, file),
    onSuccess: (resultado) => {
      snackbar.success(
        t('tesoreria.movimientos.importados', { count: Number(resultado.importados ?? 0) }),
      );
      void queryClient.invalidateQueries({ queryKey: tesoreriaKeys.movimientosAll() });
      setImportOpen(false);
      setArchivo(null);
    },
    onError: (err: unknown) => {
      setErrorImport(mensajeDeError(err, t('tesoreria.movimientos.errorImportar')));
    },
  });

  const movimientos = data?.results ?? [];
  const count = data?.count ?? 0;

  const nombreCuenta = (id: string): string => {
    const cb = cuentasBancarias.find((c) => c.id_cuenta_bancaria === id);
    return cb ? `${cb.nombre_banco} ${cb.numero_cuenta}` : id;
  };

  const columns: Column<MovimientoBancario>[] = [
    { key: 'fecha', header: t('tesoreria.movimientos.fecha'), render: (m) => m.fecha_mov },
    {
      key: 'descripcion',
      header: t('tesoreria.movimientos.descripcion'),
      render: (m) => (
        <Typography variant="body2" fontWeight={500}>
          {m.descripcion}
        </Typography>
      ),
    },
    { key: 'cuenta', header: t('tesoreria.movimientos.cuenta'), render: (m) => nombreCuenta(m.id_cuenta_bancaria) },
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
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('tesoreria.movimientos.title')}
        subtitle={t('tesoreria.movimientos.subtitle')}
        actions={
          <Button
            variant="contained"
            startIcon={<UploadFileOutlined />}
            onClick={() => {
              setErrorImport('');
              setImportOpen(true);
            }}
          >
            {t('tesoreria.movimientos.importarCsv')}
          </Button>
        }
      />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          size="small"
          label={t('tesoreria.movimientos.cuenta')}
          value={cuenta}
          onChange={(e) => {
            setCuenta(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 220 }}
        >
          <MenuItem value="">{t('tesoreria.movimientos.todas')}</MenuItem>
          {cuentasBancarias.map((cb) => (
            <MenuItem key={cb.id_cuenta_bancaria} value={cb.id_cuenta_bancaria}>
              {cb.nombre_banco} — {cb.numero_cuenta}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label={t('tesoreria.movimientos.estado')}
          value={estado}
          onChange={(e) => {
            setEstado(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">{t('tesoreria.movimientos.todos')}</MenuItem>
          {ESTADOS.map((e) => (
            <MenuItem key={e} value={e}>
              {e}
            </MenuItem>
          ))}
        </TextField>
      </Stack>
      <DataTable
        columns={columns}
        rows={movimientos}
        getRowKey={(m) => m.id}
        loading={isLoading}
        emptyMessage={t('tesoreria.movimientos.empty')}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={setPage} />

      <Dialog open={importOpen} onClose={() => setImportOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('tesoreria.movimientos.importarCsv')}</DialogTitle>
        <DialogContent>
          {errorImport && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {errorImport}
            </Alert>
          )}
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t('tesoreria.movimientos.formatoCsv')}
          </Typography>
          <Stack spacing={2}>
            <TextField
              select
              label={t('tesoreria.movimientos.cuenta')}
              fullWidth
              required
              value={cuentaImport}
              onChange={(e) => setCuentaImport(e.target.value)}
            >
              {cuentasBancarias.map((cb) => (
                <MenuItem key={cb.id_cuenta_bancaria} value={cb.id_cuenta_bancaria}>
                  {cb.nombre_banco} — {cb.numero_cuenta}
                </MenuItem>
              ))}
            </TextField>
            <Button variant="outlined" component="label">
              {archivo ? archivo.name : t('tesoreria.movimientos.elegirArchivo')}
              <input
                hidden
                type="file"
                accept=".csv,text/csv"
                aria-label={t('tesoreria.movimientos.elegirArchivo')}
                onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
              />
            </Button>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setImportOpen(false)}>{t('common.cancel')}</Button>
          <Button
            variant="contained"
            disabled={!cuentaImport || !archivo || importMutation.isPending}
            onClick={() => {
              if (cuentaImport && archivo) {
                setErrorImport('');
                importMutation.mutate({ cuentaId: cuentaImport, file: archivo });
              }
            }}
          >
            {t('tesoreria.movimientos.importar')}
          </Button>
        </DialogActions>
      </Dialog>
    </PageContainer>
  );
}
