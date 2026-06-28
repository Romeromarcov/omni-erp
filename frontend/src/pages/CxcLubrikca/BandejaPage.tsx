/**
 * Bandeja de facturación — CxC Lubrikca (Fase 6b).
 *
 * Lista las bandejas calculadas por el motor. Permite proponer el cierre (solo
 * si la bandeja es candidata y está en estado `calculado`) y confirmarlo
 * (aprobado=true con comentarios). Los 400 (no candidata, rol denegado, etc.)
 * se muestran vía snackbar.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import SendOutlined from '@mui/icons-material/SendOutlined';
import CheckCircleOutline from '@mui/icons-material/CheckCircleOutline';
import { cxcLubrikcaService } from '../../services/cxcLubrikcaService';
import type { BandejaFacturacion } from '../../services/cxcLubrikcaService';
import { cxcLubrikcaKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

const money = (v: string | number) =>
  `$${parseFloat(String(v)).toLocaleString('es-VE', { minimumFractionDigits: 2 })}`;

function puedeProponer(b: BandejaFacturacion): boolean {
  return b.candidata_a_cierre && b.estado === 'calculado';
}

export default function BandejaPage() {
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [confirmar, setConfirmar] = useState<BandejaFacturacion | null>(null);
  const [comentarios, setComentarios] = useState('');

  const { data: bandejas = [], isLoading } = useQuery({
    queryKey: cxcLubrikcaKeys.bandejaAll(),
    queryFn: () => cxcLubrikcaService.listBandeja(),
  });

  const invalidar = () => {
    queryClient.invalidateQueries({ queryKey: cxcLubrikcaKeys.bandejaAll() });
    queryClient.invalidateQueries({ queryKey: cxcLubrikcaKeys.pedidosAll() });
  };

  const proponer = useMutation({
    mutationFn: (id: string) => cxcLubrikcaService.proponerCierre(id),
    onSuccess: (res) => {
      snackbar.success(
        res.solicitud ? 'Cierre propuesto: requiere aprobación.' : 'Cierre propuesto.',
      );
      invalidar();
    },
    onError: (err: unknown) => {
      snackbar.error(mensajeDeError(err, 'No se pudo proponer el cierre.'));
    },
  });

  const confirmarMut = useMutation({
    mutationFn: (id: string) =>
      cxcLubrikcaService.confirmarCierre(id, { aprobado: true, comentarios }),
    onSuccess: () => {
      snackbar.success('Cierre confirmado.');
      cerrar();
      invalidar();
    },
    onError: (err: unknown) => {
      snackbar.error(mensajeDeError(err, 'No se pudo confirmar el cierre.'));
    },
  });

  function abrirConfirmar(b: BandejaFacturacion) {
    setConfirmar(b);
    setComentarios('');
  }

  function cerrar() {
    setConfirmar(null);
    setComentarios('');
  }

  const columns: Column<BandejaFacturacion>[] = [
    { key: 'pedido', header: 'Pedido', render: (b) => b.pedido },
    { key: 'lista', header: 'Lista', render: (b) => b.lista_aplicada || '—' },
    { key: 'base', header: 'Precio base', align: 'right', render: (b) => money(b.precio_base_calculado) },
    { key: 'desc', header: 'Descuentos', align: 'right', render: (b) => money(b.total_descuentos) },
    { key: 'motor', header: 'Total motor', align: 'right', render: (b) => money(b.total_motor) },
    {
      key: 'revision',
      header: 'Revisión',
      render: (b) => (b.requiere_revision ? <StatusChip value="Requiere" label="Requiere" colorMap={{ requiere: 'warning' }} /> : <StatusChip value={false} />),
    },
    { key: 'candidata', header: 'Candidata', render: (b) => <StatusChip value={b.candidata_a_cierre} /> },
    { key: 'estado', header: 'Estado', render: (b) => <StatusChip value={b.estado} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (b) => (
        <Stack direction="row" spacing={1} justifyContent="flex-end">
          <Button
            size="small"
            startIcon={<SendOutlined />}
            disabled={!puedeProponer(b) || proponer.isPending}
            onClick={() => proponer.mutate(b.id)}
          >
            Proponer cierre
          </Button>
          <Button
            size="small"
            variant="contained"
            startIcon={<CheckCircleOutline />}
            onClick={() => abrirConfirmar(b)}
          >
            Confirmar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader title="Bandeja de Facturación" subtitle="Cierres calculados por el motor" />
      <DataTable
        columns={columns}
        rows={bandejas}
        getRowKey={(b) => b.id}
        loading={isLoading}
        emptyMessage="No hay bandejas calculadas."
      />

      <Dialog open={!!confirmar} onClose={() => !confirmarMut.isPending && cerrar()} fullWidth maxWidth="xs">
        <DialogTitle>Confirmar cierre</DialogTitle>
        <DialogContent>
          {confirmar && (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Pedido {confirmar.pedido} · total motor {money(confirmar.total_motor)}
            </Typography>
          )}
          <TextField
            label="Comentarios"
            fullWidth
            multiline
            rows={2}
            value={comentarios}
            onChange={(e) => setComentarios(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={cerrar} disabled={confirmarMut.isPending}>
            Cancelar
          </Button>
          <Button
            variant="contained"
            disabled={confirmarMut.isPending}
            startIcon={confirmarMut.isPending ? <CircularProgress size={16} /> : undefined}
            onClick={() => confirmar && confirmarMut.mutate(confirmar.id)}
          >
            Confirmar cierre
          </Button>
        </DialogActions>
      </Dialog>
    </PageContainer>
  );
}
