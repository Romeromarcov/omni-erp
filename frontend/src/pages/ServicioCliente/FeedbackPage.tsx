import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  feedbackClienteService,
  type FeedbackCliente,
  type FeedbackClientePayload,
  type TipoFeedback,
} from '../../services/servicioClienteService';
import { servicioClienteKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const TIPO_OPCIONES: { value: TipoFeedback; label: string }[] = [
  { value: 'ENCUESTA_SATISFACCION', label: 'Encuesta satisfacción' },
  { value: 'SUGERENCIA', label: 'Sugerencia' },
  { value: 'QUEJA', label: 'Queja' },
  { value: 'OTRO', label: 'Otro' },
];

// Lookup por valor sin indexación dinámica (security/detect-object-injection).
const TIPO_LABEL = new Map<string, string>(TIPO_OPCIONES.map((o) => [o.value, o.label]));
const labelTipo = (t: TipoFeedback): string => TIPO_LABEL.get(t) ?? t;

const TIPO_COLOR: Record<string, 'success' | 'info' | 'error' | 'default'> = {
  'encuesta satisfacción': 'success',
  sugerencia: 'info',
  queja: 'error',
  otro: 'default',
};

interface FormState {
  tipo_feedback: TipoFeedback;
  calificacion: string;
  comentarios: string;
}

const FORM_VACIO: FormState = {
  tipo_feedback: 'ENCUESTA_SATISFACCION',
  calificacion: '',
  comentarios: '',
};

const FeedbackPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroTipo, setFiltroTipo] = useState<TipoFeedback | ''>('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<FormState>(FORM_VACIO);
  const [errorMsg, setErrorMsg] = useState('');

  const { data: feedback = [], isLoading } = useQuery({
    queryKey: servicioClienteKeys.feedback(empresaId, filtroTipo),
    queryFn: () =>
      feedbackClienteService.getAll({
        empresa: empresaId || undefined,
        tipo: filtroTipo || undefined,
      }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: servicioClienteKeys.feedbackAll() });

  const abrirCrear = () => {
    setForm(FORM_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: FeedbackClientePayload) => feedbackClienteService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo registrar el feedback.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => feedbackClienteService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el feedback.')),
  });

  const handleGuardar = () => {
    const cal = form.calificacion.trim();
    if (cal) {
      const n = Number(cal);
      if (!Number.isInteger(n) || n < 1 || n > 5) {
        setErrorMsg('La calificación debe ser un entero del 1 al 5.');
        return;
      }
    }
    guardar.mutate({
      id_empresa: empresaId,
      tipo_feedback: form.tipo_feedback,
      calificacion: cal ? Number(cal) : null,
      comentarios: form.comentarios.trim() || null,
      id_cliente_temp: null,
      id_ticket_origen: null,
    });
  };

  const handleEliminar = (f: FeedbackCliente) => {
    if (window.confirm('¿Eliminar este feedback?')) {
      eliminar.mutate(f.id_feedback);
    }
  };

  const columns: Column<FeedbackCliente>[] = [
    {
      key: 'tipo_feedback',
      header: 'Tipo',
      render: (f) => (
        <StatusChip value={f.tipo_feedback} label={labelTipo(f.tipo_feedback)} colorMap={TIPO_COLOR} />
      ),
    },
    {
      key: 'calificacion',
      header: 'Calificación',
      render: (f) => (f.calificacion != null ? `${f.calificacion}/5` : '—'),
    },
    { key: 'comentarios', header: 'Comentarios', render: (f) => f.comentarios || '—' },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (f) => (
        <Button
          size="small"
          color="error"
          disabled={eliminar.isPending}
          onClick={() => handleEliminar(f)}
        >
          Eliminar
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Feedback del cliente"
        subtitle="Encuestas de satisfacción, sugerencias y quejas de los clientes."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nuevo feedback
          </Button>
        }
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <TextField
        select
        label="Tipo"
        value={filtroTipo}
        onChange={(e) => setFiltroTipo(e.target.value as TipoFeedback | '')}
        size="small"
        sx={{ mb: 2, minWidth: 240 }}
      >
        <MenuItem value="">Todos</MenuItem>
        {TIPO_OPCIONES.map((o) => (
          <MenuItem key={o.value} value={o.value}>
            {o.label}
          </MenuItem>
        ))}
      </TextField>

      <DataTable
        columns={columns}
        rows={feedback}
        getRowKey={(f) => f.id_feedback}
        loading={isLoading}
        emptyMessage="Sin feedback registrado."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Nuevo feedback</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Tipo"
              value={form.tipo_feedback}
              onChange={(e) => setForm((f) => ({ ...f, tipo_feedback: e.target.value as TipoFeedback }))}
              fullWidth
            >
              {TIPO_OPCIONES.map((o) => (
                <MenuItem key={o.value} value={o.value}>
                  {o.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Calificación (1-5)"
              type="number"
              value={form.calificacion}
              onChange={(e) => setForm((f) => ({ ...f, calificacion: e.target.value }))}
              slotProps={{ htmlInput: { min: 1, max: 5 } }}
              helperText="Opcional, solo para encuestas de satisfacción."
              fullWidth
            />
            <TextField
              label="Comentarios"
              value={form.comentarios}
              onChange={(e) => setForm((f) => ({ ...f, comentarios: e.target.value }))}
              multiline
              minRows={3}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleGuardar} disabled={guardar.isPending}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </PageContainer>
  );
};

export default FeedbackPage;
