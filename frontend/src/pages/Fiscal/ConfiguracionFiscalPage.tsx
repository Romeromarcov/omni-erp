import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  FormControlLabel,
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
import { useAuth } from '../../contexts/AuthContext';
import { PageContainer, PageHeader } from '../../components/ui';
import {
  configuracionFiscalService,
  tasaIVAService,
  type ConfiguracionFiscalEmpresa,
  type TasaIVAEmpresa,
} from '../../services/fiscalService';

interface FiscalForm {
  contribuyente_iva: boolean;
  aplica_igtf: boolean;
  tasa_igtf: string;
}

const TIPOS_IVA = ['GENERAL', 'REDUCIDO', 'EXENTO', 'ADICIONAL'] as const;

const ConfiguracionFiscalPage: React.FC = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const empresaId = user?.empresas?.[0]?.id_empresa ?? '';

  const [form, setForm] = useState<FiscalForm>({
    contribuyente_iva: true,
    aplica_igtf: true,
    tasa_igtf: '0.03',
  });
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // ── Load existing config ──────────────────────────────────────────────────

  const { data: config, isLoading } = useQuery<ConfiguracionFiscalEmpresa | null>({
    queryKey: ['configuracion-fiscal', empresaId],
    queryFn: () => configuracionFiscalService.getByEmpresa(empresaId),
    enabled: !!empresaId,
  });

  const { data: tasas = [] } = useQuery<TasaIVAEmpresa[]>({
    queryKey: ['tasas-iva', empresaId],
    queryFn: () => tasaIVAService.getByEmpresa(empresaId),
    enabled: !!empresaId,
  });

  useEffect(() => {
    if (config) {
      setForm({
        contribuyente_iva: config.contribuyente_iva,
        aplica_igtf: config.aplica_igtf,
        tasa_igtf: config.tasa_igtf,
      });
    }
  }, [config]);

  // ── Mutations ─────────────────────────────────────────────────────────────

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!empresaId) throw new Error('No hay empresa activa.');
      const payload = {
        ...form,
        tasa_igtf: parseFloat(form.tasa_igtf).toFixed(4),
        id_empresa: empresaId,
      };
      if (config) {
        return configuracionFiscalService.update(config.id, payload);
      }
      return configuracionFiscalService.create(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['configuracion-fiscal', empresaId] });
      setSuccessMsg('Configuración fiscal guardada correctamente.');
      setErrorMsg('');
    },
    onError: (err: Error) => {
      setErrorMsg(err.message);
      setSuccessMsg('');
    },
  });

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <PageContainer maxWidth={700}>
      <PageHeader
        title="Configuración Fiscal"
        subtitle="Parámetros de IVA e IGTF para la empresa."
      />

      {successMsg && <Alert severity="success" sx={{ mb: 2 }}>{successMsg}</Alert>}
      {errorMsg && <Alert severity="error" sx={{ mb: 2 }}>{errorMsg}</Alert>}

      {isLoading ? (
        <Box display="flex" justifyContent="center" py={4}><CircularProgress /></Box>
      ) : (
        <Box component="form" onSubmit={(e) => { e.preventDefault(); saveMutation.mutate(); }}>
          <Stack spacing={3}>
            {/* Section: IVA */}
            <Paper variant="outlined" sx={{ p: 2.5 }}>
              <Typography variant="h6" color="primary" mb={2}>Impuesto al Valor Agregado (IVA)</Typography>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={form.contribuyente_iva}
                    onChange={(e) => setForm((f) => ({ ...f, contribuyente_iva: e.target.checked }))}
                  />
                }
                label={
                  <Box>
                    <Typography component="span" fontWeight={600}>Contribuyente ordinario de IVA</Typography>
                    <Typography variant="body2" color="text.secondary">
                      La empresa está inscrita como contribuyente del IVA ante el SENIAT.
                    </Typography>
                  </Box>
                }
              />
            </Paper>

            {/* Section: IGTF */}
            <Paper variant="outlined" sx={{ p: 2.5 }}>
              <Typography variant="h6" sx={{ color: 'warning.dark' }} mb={2}>
                Impuesto a las Grandes Transacciones Financieras (IGTF)
              </Typography>
              <FormControlLabel
                sx={{ mb: 2 }}
                control={
                  <Checkbox
                    checked={form.aplica_igtf}
                    onChange={(e) => setForm((f) => ({ ...f, aplica_igtf: e.target.checked }))}
                  />
                }
                label={
                  <Box>
                    <Typography component="span" fontWeight={600}>Aplicar IGTF en pagos en divisas/crypto</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Se aplica IGTF cuando el cliente paga en moneda extranjera o criptomoneda.
                    </Typography>
                  </Box>
                }
              />
              {form.aplica_igtf && (
                <Stack direction="row" spacing={1} alignItems="center">
                  <TextField
                    label="Alícuota IGTF (decimal, ej: 0.03 = 3%)"
                    type="number"
                    inputProps={{ min: 0, max: 1, step: 0.001 }}
                    value={form.tasa_igtf}
                    onChange={(e) => setForm((f) => ({ ...f, tasa_igtf: e.target.value }))}
                    sx={{ maxWidth: 280 }}
                  />
                  <Typography variant="body2" color="text.secondary">
                    = {(parseFloat(form.tasa_igtf || '0') * 100).toFixed(1)}%
                  </Typography>
                </Stack>
              )}
            </Paper>

            {/* Section: Tasas IVA */}
            {tasas.length > 0 && (
              <Paper variant="outlined" sx={{ p: 2.5 }}>
                <Typography variant="h6" sx={{ color: 'success.dark' }} mb={1.5}>Tasas de IVA configuradas</Typography>
                <TableContainer sx={{ width: '100%', overflowX: 'auto' }}>
                  <Table size="small" sx={{ minWidth: 360 }}>
                    <TableHead>
                      <TableRow>
                        <TableCell>Tipo</TableCell>
                        <TableCell>Nombre</TableCell>
                        <TableCell>Tasa</TableCell>
                        <TableCell>Estado</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {tasas.map((t) => (
                        <TableRow key={t.id}>
                          <TableCell>
                            <Chip
                              size="small"
                              label={t.tipo}
                              color={TIPOS_IVA.indexOf(t.tipo) === 0 ? 'primary' : 'default'}
                            />
                          </TableCell>
                          <TableCell>{t.nombre}</TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>{(parseFloat(t.tasa) * 100).toFixed(0)}%</TableCell>
                          <TableCell>
                            <Chip size="small" label={t.activo ? 'Activo' : 'Inactivo'} color={t.activo ? 'success' : 'error'} variant="outlined" />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Paper>
            )}

            <Stack direction="row" justifyContent="flex-start">
              <Button type="submit" variant="contained" disabled={saveMutation.isPending || !empresaId}>
                {saveMutation.isPending ? 'Guardando…' : 'Guardar configuración'}
              </Button>
            </Stack>
          </Stack>
        </Box>
      )}
    </PageContainer>
  );
};

export default ConfiguracionFiscalPage;
