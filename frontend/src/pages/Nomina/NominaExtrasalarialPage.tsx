import React, { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import CloseOutlined from '@mui/icons-material/CloseOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  procesosNominaExtrasalarialService,
  nominasExtrasalarialService,
  type ProcesoNominaExtrasalarial,
  type ProcesoNominaExtrasalarialPayload,
  type NominaExtrasalarial,
} from '../../services/nominaExtrasService';
import { rrhhService, type Empleado } from '../../services/rrhhService';
import { nominaExtrasKeys, rrhhKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const TIPOS: { value: string; label: string }[] = [
  { value: 'AGUINALDO', label: 'Aguinaldo / Utilidades' },
  { value: 'VACACIONES', label: 'Bono vacacional' },
  { value: 'PRESTACIONES', label: 'Prestaciones sociales' },
  { value: 'LIQUIDACION', label: 'Liquidación' },
  { value: 'BONO_ESPECIAL', label: 'Bono especial' },
];

const ESTADO_COLOR: Record<string, 'warning' | 'info' | 'success' | 'error' | 'default'> = {
  en_proceso: 'warning',
  completado: 'info',
  aprobado: 'success',
  pagado: 'default',
  cancelado: 'error',
};

const RECIBO_COLOR: Record<string, 'warning' | 'success' | 'default'> = {
  calculada: 'warning',
  aprobada: 'success',
  pagada: 'default',
};

const etiquetaTipo = (v: string) => TIPOS.find((t) => t.value === v)?.label ?? v;
const hoy = () => new Date().toISOString().slice(0, 10);

interface FormState {
  numero_proceso: string;
  tipo_proceso: string;
  fecha_proceso: string;
  fecha_corte: string;
  observaciones: string;
}

const formVacio = (): FormState => ({
  numero_proceso: '',
  tipo_proceso: 'AGUINALDO',
  fecha_proceso: hoy(),
  fecha_corte: hoy(),
  observaciones: '',
});

const NominaExtrasalarialPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<ProcesoNominaExtrasalarial | null>(null);
  const [form, setForm] = useState<FormState>(formVacio());
  const [errorMsg, setErrorMsg] = useState('');
  const [detalle, setDetalle] = useState<ProcesoNominaExtrasalarial | null>(null);

  const { data: procesos = [], isLoading } = useQuery({
    queryKey: nominaExtrasKeys.procesos(),
    queryFn: () => procesosNominaExtrasalarialService.getAll(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: nominaExtrasKeys.procesosAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(formVacio());
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (p: ProcesoNominaExtrasalarial) => {
    setEditando(p);
    setForm({
      numero_proceso: p.numero_proceso,
      tipo_proceso: p.tipo_proceso,
      fecha_proceso: p.fecha_proceso.slice(0, 10),
      fecha_corte: p.fecha_corte,
      observaciones: p.observaciones ?? '',
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: ProcesoNominaExtrasalarialPayload) =>
      editando
        ? procesosNominaExtrasalarialService.update(editando.id_proceso_extrasalarial, payload)
        : procesosNominaExtrasalarialService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el proceso.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => procesosNominaExtrasalarialService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el proceso.')),
  });

  const procesar = useMutation({
    mutationFn: (id: string) => procesosNominaExtrasalarialService.procesar(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo procesar el proceso.')),
  });

  const aprobar = useMutation({
    mutationFn: (id: string) => procesosNominaExtrasalarialService.aprobar(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo aprobar el proceso.')),
  });

  const handleGuardar = () => {
    if (!form.numero_proceso.trim()) {
      setErrorMsg('Indique el número del proceso.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      numero_proceso: form.numero_proceso.trim(),
      tipo_proceso: form.tipo_proceso,
      fecha_proceso: new Date(form.fecha_proceso).toISOString(),
      fecha_corte: form.fecha_corte,
      observaciones: form.observaciones.trim() || null,
    });
  };

  const handleEliminar = (p: ProcesoNominaExtrasalarial) => {
    if (window.confirm(`¿Eliminar el proceso "${p.numero_proceso}"?`)) {
      eliminar.mutate(p.id_proceso_extrasalarial);
    }
  };

  const handleProcesar = (p: ProcesoNominaExtrasalarial) => {
    if (window.confirm('¿Procesar este proceso extrasalarial?')) {
      procesar.mutate(p.id_proceso_extrasalarial);
    }
  };

  const handleAprobar = (p: ProcesoNominaExtrasalarial) => {
    if (window.confirm('¿Aprobar este proceso? Sus recibos pasarán a aprobados.')) {
      aprobar.mutate(p.id_proceso_extrasalarial);
    }
  };

  const columns: Column<ProcesoNominaExtrasalarial>[] = [
    { key: 'numero_proceso', header: 'Número', render: (p) => p.numero_proceso },
    { key: 'tipo_proceso', header: 'Tipo', render: (p) => etiquetaTipo(p.tipo_proceso) },
    { key: 'fecha_corte', header: 'Corte', render: (p) => p.fecha_corte },
    { key: 'total_empleados', header: 'Empleados', render: (p) => p.total_empleados },
    { key: 'total_monto', header: 'Monto', render: (p) => p.total_monto },
    {
      key: 'estado',
      header: 'Estado',
      render: (p) => <StatusChip value={p.estado} label={p.estado} colorMap={ESTADO_COLOR} />,
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (p) => {
        const enProceso = p.estado === 'EN_PROCESO';
        const completado = p.estado === 'COMPLETADO';
        return (
          <Stack direction="row" spacing={1}>
            <Button size="small" onClick={() => setDetalle(p)}>
              Recibos
            </Button>
            <Button size="small" disabled={!enProceso} onClick={() => abrirEditar(p)}>
              Editar
            </Button>
            <Button
              size="small"
              color="info"
              disabled={!enProceso || procesar.isPending}
              onClick={() => handleProcesar(p)}
            >
              Procesar
            </Button>
            <Button
              size="small"
              color="success"
              disabled={!completado || aprobar.isPending}
              onClick={() => handleAprobar(p)}
            >
              Aprobar
            </Button>
            <Button
              size="small"
              color="error"
              disabled={!enProceso || eliminar.isPending}
              onClick={() => handleEliminar(p)}
            >
              Eliminar
            </Button>
          </Stack>
        );
      },
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Nómina Extrasalarial"
        subtitle="Procesos de pagos no salariales (utilidades, bono vacacional, prestaciones, liquidaciones) con su flujo de procesar y aprobar."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nuevo proceso
          </Button>
        }
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={procesos}
        getRowKey={(p) => p.id_proceso_extrasalarial}
        loading={isLoading}
        emptyMessage="Sin procesos extrasalariales. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar proceso' : 'Nuevo proceso extrasalarial'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Número de proceso"
              value={form.numero_proceso}
              onChange={(e) => setForm((f) => ({ ...f, numero_proceso: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              select
              label="Tipo de proceso"
              value={form.tipo_proceso}
              onChange={(e) => setForm((f) => ({ ...f, tipo_proceso: e.target.value }))}
              fullWidth
            >
              {TIPOS.map((t) => (
                <MenuItem key={t.value} value={t.value}>
                  {t.label}
                </MenuItem>
              ))}
            </TextField>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Fecha del proceso"
                type="date"
                value={form.fecha_proceso}
                onChange={(e) => setForm((f) => ({ ...f, fecha_proceso: e.target.value }))}
                slotProps={{ inputLabel: { shrink: true } }}
                fullWidth
              />
              <TextField
                label="Fecha de corte"
                type="date"
                value={form.fecha_corte}
                onChange={(e) => setForm((f) => ({ ...f, fecha_corte: e.target.value }))}
                slotProps={{ inputLabel: { shrink: true } }}
                fullWidth
              />
            </Stack>
            <TextField
              label="Observaciones"
              value={form.observaciones}
              onChange={(e) => setForm((f) => ({ ...f, observaciones: e.target.value }))}
              multiline
              minRows={2}
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

      <Drawer
        anchor="right"
        open={Boolean(detalle)}
        onClose={() => setDetalle(null)}
        slotProps={{ paper: { sx: { width: { xs: '100%', sm: 640 }, p: 3 } } }}
      >
        {detalle && (
          <RecibosDrawer
            proceso={detalle}
            empresaId={empresaId}
            onClose={() => setDetalle(null)}
          />
        )}
      </Drawer>
    </PageContainer>
  );
};

// ── Recibos del proceso (lista + acciones de workflow) ───────────────────────

interface RecibosDrawerProps {
  proceso: ProcesoNominaExtrasalarial;
  empresaId: string;
  onClose: () => void;
}

const RecibosDrawer: React.FC<RecibosDrawerProps> = ({ proceso, empresaId, onClose }) => {
  const queryClient = useQueryClient();
  const procesoId = proceso.id_proceso_extrasalarial;
  const [error, setError] = useState('');

  const { data: recibos = [], isLoading } = useQuery({
    queryKey: nominaExtrasKeys.recibos(procesoId),
    queryFn: () => nominasExtrasalarialService.getAll({ proceso: procesoId }),
  });

  const { data: empleados = [] } = useQuery({
    queryKey: rrhhKeys.empleadosDeEmpresa(empresaId),
    queryFn: () => rrhhService.getEmpleadosDeEmpresa(empresaId),
    enabled: Boolean(empresaId),
  });

  const empleadoPorId = useMemo(() => {
    const mapa = new Map<number, Empleado>();
    for (const e of empleados) mapa.set(e.id, e);
    return mapa;
  }, [empleados]);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: nominaExtrasKeys.recibos(procesoId) });

  const aprobar = useMutation({
    mutationFn: (id: string) => nominasExtrasalarialService.aprobar(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo aprobar el recibo.')),
  });

  const marcarPagada = useMutation({
    mutationFn: (id: string) => nominasExtrasalarialService.marcarPagada(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo marcar el recibo como pagado.')),
  });

  const nombreEmpleado = (id: number) => {
    const e = empleadoPorId.get(id);
    return e ? `${e.nombre} ${e.apellido}` : `Empleado ${id}`;
  };

  const columns: Column<NominaExtrasalarial>[] = [
    { key: 'empleado', header: 'Empleado', render: (r) => nombreEmpleado(r.id_empleado) },
    { key: 'monto_calculado', header: 'Calculado', render: (r) => r.monto_calculado },
    { key: 'deducciones', header: 'Deducciones', render: (r) => r.deducciones },
    { key: 'monto_neto', header: 'Neto', render: (r) => r.monto_neto },
    {
      key: 'estado',
      header: 'Estado',
      render: (r) => <StatusChip value={r.estado} label={r.estado} colorMap={RECIBO_COLOR} />,
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (r) => (
        <Stack direction="row" spacing={1}>
          <Button
            size="small"
            color="success"
            disabled={r.estado !== 'CALCULADA' || aprobar.isPending}
            onClick={() => aprobar.mutate(r.id_nomina_extrasalarial)}
          >
            Aprobar
          </Button>
          <Button
            size="small"
            disabled={r.estado !== 'APROBADA' || marcarPagada.isPending}
            onClick={() => marcarPagada.mutate(r.id_nomina_extrasalarial)}
          >
            Pagar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">{proceso.numero_proceso}</Typography>
        <IconButton onClick={onClose} aria-label="Cerrar recibos">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {etiquetaTipo(proceso.tipo_proceso)} · corte {proceso.fecha_corte}
      </Typography>
      <Divider />

      {error && (
        <Alert severity="error" onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={recibos}
        getRowKey={(r) => r.id_nomina_extrasalarial}
        loading={isLoading}
        emptyMessage="Sin recibos. Procesa el proceso para generarlos."
      />
    </Stack>
  );
};

export default NominaExtrasalarialPage;
