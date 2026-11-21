import React, { useMemo, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Drawer,
  IconButton,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import CheckCircleOutlineOutlined from '@mui/icons-material/CheckCircleOutlineOutlined';
import CloseOutlined from '@mui/icons-material/CloseOutlined';
import ReplayOutlined from '@mui/icons-material/ReplayOutlined';
import { PageContainer, PageHeader } from '../../components/ui';
import { crmKeys } from '../../lib/queryKeys';
import {
  crmCrmService,
  type CrmActividad,
  type CrmEtapa,
  type CrmLead,
  type CrmPipeline,
  type FuenteLead,
  type TipoActividad,
  type TipoEtapa,
} from '../../services/crmCrmService';
import { mensajeDeError } from '../../utils/api';
import { getEmpresaId } from '../../utils/empresa';

const FUENTE_OPCIONES: Array<{ value: '' | FuenteLead; label: string }> = [
  { value: '', label: 'Todas las fuentes' },
  { value: 'NFC', label: 'Tarjeta NFC' },
  { value: 'QR', label: 'Código QR' },
  { value: 'ENLACE', label: 'Enlace' },
  { value: 'MANUAL', label: 'Manual' },
  { value: 'IMPORTACION', label: 'Importación' },
];

const TIPO_ACTIVIDAD_OPCIONES: Array<{ value: TipoActividad; label: string }> = [
  { value: 'LLAMADA', label: 'Llamada' },
  { value: 'CORREO', label: 'Correo' },
  { value: 'REUNION', label: 'Reunión' },
  { value: 'NOTA', label: 'Nota' },
  { value: 'WHATSAPP', label: 'WhatsApp' },
];

const ETAPA_TIPO_META = new Map<
  TipoEtapa,
  { label: string; color: 'default' | 'primary' | 'success' | 'error' }
>([
  ['ABIERTA', { label: 'Abierta', color: 'primary' }],
  ['GANADA', { label: 'Ganada', color: 'success' }],
  ['PERDIDA', { label: 'Perdida', color: 'error' }],
]);

const ACTIVIDAD_LABEL = new Map<TipoActividad, string>(
  TIPO_ACTIVIDAD_OPCIONES.map((item) => [item.value, item.label]),
);

const LEAD_FORM_VACIO = {
  nombre: '',
  apellido: '',
  empresa_nombre: '',
  email: '',
  telefono: '',
  mensaje: '',
  etapa: '',
};

const ACTIVIDAD_FORM_VACIO = {
  tipo: 'LLAMADA' as TipoActividad,
  asunto: '',
  descripcion: '',
  fecha_vencimiento: '',
};

function formatearFecha(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('es-VE', {
    dateStyle: 'short',
    timeStyle: 'short',
  });
}

const CrmPipelineKanbanPage: React.FC = () => {
  const empresaId = getEmpresaId() || null;
  const qc = useQueryClient();

  const [pipelineSelId, setPipelineSelId] = useState<string>('');
  const [busqueda, setBusqueda] = useState('');
  const [fuenteFiltro, setFuenteFiltro] = useState<'' | FuenteLead>('');
  const [errorMsg, setErrorMsg] = useState('');

  const [dialogLeadOpen, setDialogLeadOpen] = useState(false);
  const [leadForm, setLeadForm] = useState(LEAD_FORM_VACIO);
  const [leadFormError, setLeadFormError] = useState('');

  const [leadDetalleId, setLeadDetalleId] = useState<string | null>(null);
  const [actividadForm, setActividadForm] = useState(ACTIVIDAD_FORM_VACIO);
  const [actividadError, setActividadError] = useState('');
  const [draggingLeadId, setDraggingLeadId] = useState<string | null>(null);

  const pipelinesQuery = useQuery({
    queryKey: crmKeys.pipelinesAll(empresaId),
    queryFn: () => crmCrmService.getPipelines(empresaId),
  });

  const pipelines = useMemo(() => pipelinesQuery.data ?? [], [pipelinesQuery.data]);

  const pipelineActivo: CrmPipeline | null = useMemo(() => {
    if (pipelines.length === 0) return null;
    if (pipelineSelId) {
      const encontrado = pipelines.find((p) => p.id_pipeline === pipelineSelId);
      if (encontrado) return encontrado;
    }
    return pipelines.find((p) => p.es_predeterminado) ?? pipelines.at(0) ?? null;
  }, [pipelines, pipelineSelId]);

  const pipelineActivoId = pipelineActivo?.id_pipeline ?? '';

  const etapasOrdenadas: CrmEtapa[] = useMemo(() => {
    const raw = pipelineActivo?.etapas ?? [];
    return [...raw].sort((a, b) => (a.orden ?? 0) - (b.orden ?? 0));
  }, [pipelineActivo]);

  const leadsQuery = useQuery({
    queryKey: crmKeys.leads(empresaId, {
      pipeline: pipelineActivoId || null,
      fuente: fuenteFiltro || null,
      search: busqueda.trim() || null,
    }),
    queryFn: () =>
      crmCrmService.getLeads({
        empresa: empresaId,
        pipeline: pipelineActivoId,
        fuente: fuenteFiltro || undefined,
        search: busqueda.trim() || undefined,
      }),
    enabled: Boolean(pipelineActivoId),
  });

  const leads = useMemo(() => leadsQuery.data ?? [], [leadsQuery.data]);

  const leadDetalle: CrmLead | null = useMemo(() => {
    if (!leadDetalleId) return null;
    return leads.find((l) => l.id_lead === leadDetalleId) ?? null;
  }, [leads, leadDetalleId]);

  const actividadesQuery = useQuery({
    queryKey: crmKeys.actividades(empresaId, leadDetalleId),
    queryFn: () =>
      crmCrmService.getActividades({
        empresa: empresaId,
        lead: leadDetalleId,
      }),
    enabled: Boolean(leadDetalleId),
  });

  const leadsPorEtapa = useMemo(() => {
    const mapa = new Map<string, CrmLead[]>();
    for (const etapa of etapasOrdenadas) {
      if (etapa.id_etapa) {
        mapa.set(etapa.id_etapa, []);
      }
    }
    for (const lead of leads) {
      const key = lead.etapa ?? '';
      const lista = mapa.get(key);
      if (lista) {
        lista.push(lead);
      }
    }
    return mapa;
  }, [etapasOrdenadas, leads]);

  const invalidarTablero = () => {
    void qc.invalidateQueries({ queryKey: crmKeys.pipelinesAll(empresaId) });
    void qc.invalidateQueries({ queryKey: crmKeys.leadsAll(empresaId) });
  };

  const asegurarPipelineMutation = useMutation({
    mutationFn: () => crmCrmService.asegurarPipelinePredeterminado(empresaId),
    onSuccess: (pipe) => {
      setErrorMsg('');
      if (pipe.id_pipeline) {
        setPipelineSelId(pipe.id_pipeline);
      }
      invalidarTablero();
    },
    onError: (err) => {
      setErrorMsg(mensajeDeError(err, 'No se pudo inicializar el pipeline predeterminado.'));
    },
  });

  const moverEtapaMutation = useMutation({
    mutationFn: ({ leadId, etapaId }: { leadId: string; etapaId: string }) =>
      crmCrmService.moverEtapaLead(leadId, etapaId),
    onSuccess: () => {
      setErrorMsg('');
      void qc.invalidateQueries({ queryKey: crmKeys.leadsAll(empresaId) });
    },
    onError: (err) => {
      setErrorMsg(mensajeDeError(err, 'No se pudo mover el lead de etapa.'));
    },
  });

  const crearLeadMutation = useMutation({
    mutationFn: () =>
      crmCrmService.createLead({
        id_empresa: empresaId ?? undefined,
        nombre: leadForm.nombre.trim(),
        apellido: leadForm.apellido.trim(),
        empresa_nombre: leadForm.empresa_nombre.trim(),
        email: leadForm.email.trim(),
        telefono: leadForm.telefono.trim(),
        mensaje: leadForm.mensaje.trim(),
        fuente: 'MANUAL',
        pipeline: pipelineActivoId || undefined,
        etapa: leadForm.etapa || undefined,
      }),
    onSuccess: () => {
      setDialogLeadOpen(false);
      setLeadForm(LEAD_FORM_VACIO);
      setLeadFormError('');
      setErrorMsg('');
      invalidarTablero();
    },
    onError: (err) => {
      setLeadFormError(mensajeDeError(err, 'No se pudo crear el lead.'));
    },
  });

  const crearActividadMutation = useMutation({
    mutationFn: () => {
      if (!leadDetalleId) {
        throw new Error('Selecciona un lead para registrar la actividad.');
      }
      const fechaVenc = actividadForm.fecha_vencimiento.trim()
        ? new Date(actividadForm.fecha_vencimiento).toISOString()
        : null;
      return crmCrmService.createActividad({
        id_empresa: empresaId ?? undefined,
        lead: leadDetalleId,
        tipo: actividadForm.tipo,
        asunto: actividadForm.asunto.trim(),
        descripcion: actividadForm.descripcion.trim(),
        fecha_vencimiento: fechaVenc,
      });
    },
    onSuccess: () => {
      setActividadForm(ACTIVIDAD_FORM_VACIO);
      setActividadError('');
      void qc.invalidateQueries({ queryKey: crmKeys.actividades(empresaId, leadDetalleId) });
      void qc.invalidateQueries({ queryKey: crmKeys.leadsAll(empresaId) });
    },
    onError: (err) => {
      setActividadError(mensajeDeError(err, 'No se pudo registrar la actividad.'));
    },
  });

  const completarActividadMutation = useMutation({
    mutationFn: ({ id, completada }: { id: string; completada: boolean }) =>
      crmCrmService.completarActividad(id, completada),
    onSuccess: () => {
      setActividadError('');
      void qc.invalidateQueries({ queryKey: crmKeys.actividades(empresaId, leadDetalleId) });
      void qc.invalidateQueries({ queryKey: crmKeys.leadsAll(empresaId) });
    },
    onError: (err) => {
      setActividadError(mensajeDeError(err, 'No se pudo actualizar el estado de la actividad.'));
    },
  });

  function abrirNuevoLead() {
    const primeraAbierta =
      etapasOrdenadas.find((e) => e.tipo === 'ABIERTA')?.id_etapa ??
      etapasOrdenadas.at(0)?.id_etapa ??
      '';
    setLeadForm({ ...LEAD_FORM_VACIO, etapa: primeraAbierta });
    setLeadFormError('');
    setDialogLeadOpen(true);
  }

  function handleCrearLeadSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLeadFormError('');
    if (!leadForm.nombre.trim()) {
      setLeadFormError('El nombre del lead es obligatorio.');
      return;
    }
    crearLeadMutation.mutate();
  }

  function handleCrearActividadSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setActividadError('');
    if (!actividadForm.asunto.trim()) {
      setActividadError('El asunto de la actividad es obligatorio.');
      return;
    }
    crearActividadMutation.mutate();
  }

  return (
    <PageContainer>
      <PageHeader
        title="Pipeline Kanban (CRM)"
        subtitle="Gestiona leads capturados por Omni Connect o carga manual, avanza etapas y registra actividades de seguimiento."
        actions={
          <Button
            variant="contained"
            startIcon={<AddOutlined />}
            onClick={abrirNuevoLead}
          >
            Nuevo lead
          </Button>
        }
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={1.5}
        alignItems={{ md: 'center' }}
        justifyContent="space-between"
        sx={{ mb: 2.5 }}
      >
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} flexWrap="wrap" useFlexGap>
          <TextField
            select
            size="small"
            label="Pipeline"
            value={pipelineActivoId}
            onChange={(ev) => setPipelineSelId(ev.target.value)}
            sx={{ minWidth: 220 }}
            disabled={pipelines.length === 0}
          >
            {pipelines.map((pipe) => (
              <MenuItem key={pipe.id_pipeline} value={pipe.id_pipeline ?? ''}>
                {pipe.nombre}
                {pipe.es_predeterminado ? ' (Predeterminado)' : ''}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            size="small"
            label="Buscar leads"
            placeholder="Nombre, empresa, correo o teléfono"
            value={busqueda}
            onChange={(ev) => setBusqueda(ev.target.value)}
            sx={{ minWidth: 240 }}
          />

          <TextField
            select
            size="small"
            label="Fuente"
            value={fuenteFiltro}
            onChange={(ev) => setFuenteFiltro(ev.target.value as '' | FuenteLead)}
            sx={{ minWidth: 170 }}
          >
            {FUENTE_OPCIONES.map((opt) => (
              <MenuItem key={opt.value || 'ALL'} value={opt.value}>
                {opt.label}
              </MenuItem>
            ))}
          </TextField>
        </Stack>

        <Button
          variant="outlined"
          disabled={asegurarPipelineMutation.isPending}
          onClick={() => asegurarPipelineMutation.mutate()}
        >
          Pipeline predeterminado
        </Button>
      </Stack>

      {pipelinesQuery.isLoading ? (
        <Box sx={{ py: 6, textAlign: 'center' }}>
          <CircularProgress size={28} />
        </Box>
      ) : pipelinesQuery.isError ? (
        <Alert severity="error">
          {mensajeDeError(pipelinesQuery.error, 'No se pudieron cargar los pipelines del CRM.')}
        </Alert>
      ) : !pipelineActivo ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="subtitle1" gutterBottom>
            Aún no hay pipelines configurados en esta empresa.
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Inicializa el pipeline predeterminado con sus etapas (Nuevo, Contactado, Calificado, Ganado, Perdido).
          </Typography>
          <Button
            variant="contained"
            disabled={asegurarPipelineMutation.isPending}
            onClick={() => asegurarPipelineMutation.mutate()}
          >
            Inicializar pipeline predeterminado
          </Button>
        </Paper>
      ) : (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: 2,
            alignItems: 'start',
          }}
        >
          {etapasOrdenadas.map((etapa) => {
            const etapaId = etapa.id_etapa ?? '';
            const tarjetas = leadsPorEtapa.get(etapaId) ?? [];
            const tipoInfo = ETAPA_TIPO_META.get(etapa.tipo ?? 'ABIERTA') ?? {
              label: etapa.tipo ?? 'Abierta',
              color: 'default' as const,
            };
            return (
              <Paper
                key={etapaId}
                variant="outlined"
                data-testid={`kanban-col-${etapaId}`}
                onDragOver={(ev) => ev.preventDefault()}
                onDrop={(ev) => {
                  ev.preventDefault();
                  const droppedId = ev.dataTransfer?.getData('text/plain') || draggingLeadId;
                  setDraggingLeadId(null);
                  if (!droppedId || !etapaId) return;
                  const leadOrig = leads.find((l) => l.id_lead === droppedId);
                  if (leadOrig && leadOrig.etapa !== etapaId) {
                    moverEtapaMutation.mutate({ leadId: droppedId, etapaId });
                  }
                }}
                sx={{ p: 1.5, bgcolor: 'background.default', minHeight: 300 }}
              >
                <Stack
                  direction="row"
                  justifyContent="space-between"
                  alignItems="center"
                  spacing={1}
                  sx={{ mb: 1.5 }}
                >
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography variant="subtitle2" fontWeight={700}>
                      {etapa.nombre}
                    </Typography>
                    <Chip size="small" label={tarjetas.length} />
                  </Stack>
                  <Chip
                    size="small"
                    variant="outlined"
                    color={tipoInfo.color}
                    label={tipoInfo.label}
                  />
                </Stack>

                {leadsQuery.isLoading ? (
                  <CircularProgress size={20} />
                ) : tarjetas.length === 0 ? (
                  <Typography variant="caption" color="text.secondary">
                    Sin leads en esta etapa.
                  </Typography>
                ) : (
                  <Stack spacing={1.25}>
                    {tarjetas.map((lead) => {
                      const leadId = lead.id_lead ?? '';
                      const nombreCompleto = `${lead.nombre} ${lead.apellido ?? ''}`.trim();
                      const pendientes = lead.actividades_pendientes ?? 0;
                      const vencidas = lead.actividades_vencidas ?? 0;
                      return (
                        <Card
                          key={leadId}
                          variant="outlined"
                          draggable
                          onDragStart={(ev) => {
                            setDraggingLeadId(leadId);
                            ev.dataTransfer?.setData('text/plain', leadId);
                          }}
                          onDragEnd={() => setDraggingLeadId(null)}
                        >
                          <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
                            <Stack
                              direction="row"
                              justifyContent="space-between"
                              alignItems="flex-start"
                              spacing={1}
                              sx={{ mb: 0.75 }}
                            >
                              <Typography
                                variant="body2"
                                fontWeight={700}
                                sx={{ cursor: 'pointer' }}
                                onClick={() => {
                                  setActividadError('');
                                  setLeadDetalleId(leadId);
                                }}
                              >
                                {nombreCompleto}
                              </Typography>
                              <Chip
                                size="small"
                                label={lead.fuente ?? 'MANUAL'}
                                color={lead.fuente === 'NFC' ? 'primary' : 'default'}
                                variant="outlined"
                              />
                            </Stack>

                            {lead.empresa_nombre && (
                              <Typography variant="caption" color="text.secondary" display="block" mb={0.75}>
                                {lead.empresa_nombre}
                              </Typography>
                            )}

                            <Stack
                              direction="row"
                              spacing={0.5}
                              flexWrap="wrap"
                              useFlexGap
                              sx={{ mb: 1 }}
                            >
                              {lead.propietario_nombre && (
                                <Chip size="small" variant="outlined" label={lead.propietario_nombre} />
                              )}
                              {pendientes > 0 && (
                                <Chip
                                  size="small"
                                  color="info"
                                  variant="outlined"
                                  label={`${pendientes} act.`}
                                />
                              )}
                              {vencidas > 0 && (
                                <Chip
                                  size="small"
                                  color="error"
                                  label={`${vencidas} venc.`}
                                />
                              )}
                            </Stack>

                            <Stack direction="row" spacing={1} alignItems="center">
                              <TextField
                                select
                                size="small"
                                label="Mover a etapa"
                                value={lead.etapa ?? etapaId}
                                onChange={(ev) => {
                                  const destId = ev.target.value;
                                  if (destId && destId !== lead.etapa) {
                                    moverEtapaMutation.mutate({ leadId, etapaId: destId });
                                  }
                                }}
                                sx={{ flexGrow: 1 }}
                              >
                                {etapasOrdenadas.map((dest) => (
                                  <MenuItem key={dest.id_etapa} value={dest.id_etapa ?? ''}>
                                    {dest.nombre}
                                  </MenuItem>
                                ))}
                              </TextField>
                              <Button
                                size="small"
                                onClick={() => {
                                  setActividadError('');
                                  setLeadDetalleId(leadId);
                                }}
                              >
                                Detalle
                              </Button>
                            </Stack>
                          </CardContent>
                        </Card>
                      );
                    })}
                  </Stack>
                )}
              </Paper>
            );
          })}
        </Box>
      )}

      {/* Diálogo Nuevo Lead Manual */}
      <Dialog
        open={dialogLeadOpen}
        onClose={() => {
          setLeadFormError('');
          setDialogLeadOpen(false);
        }}
        maxWidth="sm"
        fullWidth
      >
        <Box component="form" onSubmit={handleCrearLeadSubmit} noValidate>
          <DialogTitle>Nuevo lead manual</DialogTitle>
          <DialogContent>
            {leadFormError && (
              <Alert severity="error" sx={{ mt: 1, mb: 1 }} onClose={() => setLeadFormError('')}>
                {leadFormError}
              </Alert>
            )}
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                <TextField
                  label="Nombre"
                  required
                  fullWidth
                  value={leadForm.nombre}
                  onChange={(ev) => setLeadForm({ ...leadForm, nombre: ev.target.value })}
                />
                <TextField
                  label="Apellido"
                  fullWidth
                  value={leadForm.apellido}
                  onChange={(ev) => setLeadForm({ ...leadForm, apellido: ev.target.value })}
                />
              </Stack>
              <TextField
                label="Empresa"
                fullWidth
                value={leadForm.empresa_nombre}
                onChange={(ev) => setLeadForm({ ...leadForm, empresa_nombre: ev.target.value })}
              />
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
                <TextField
                  label="Correo electrónico"
                  type="email"
                  fullWidth
                  value={leadForm.email}
                  onChange={(ev) => setLeadForm({ ...leadForm, email: ev.target.value })}
                />
                <TextField
                  label="Teléfono"
                  fullWidth
                  value={leadForm.telefono}
                  onChange={(ev) => setLeadForm({ ...leadForm, telefono: ev.target.value })}
                />
              </Stack>
              {etapasOrdenadas.length > 0 && (
                <TextField
                  select
                  label="Etapa inicial"
                  fullWidth
                  value={leadForm.etapa}
                  onChange={(ev) => setLeadForm({ ...leadForm, etapa: ev.target.value })}
                >
                  {etapasOrdenadas.map((etapa) => (
                    <MenuItem key={etapa.id_etapa} value={etapa.id_etapa ?? ''}>
                      {etapa.nombre}
                    </MenuItem>
                  ))}
                </TextField>
              )}
              <TextField
                label="Notas / Mensaje"
                multiline
                minRows={2}
                fullWidth
                value={leadForm.mensaje}
                onChange={(ev) => setLeadForm({ ...leadForm, mensaje: ev.target.value })}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button
              type="button"
              onClick={() => {
                setLeadFormError('');
                setDialogLeadOpen(false);
              }}
            >
              Cancelar
            </Button>
            <Button
              type="submit"
              variant="contained"
              disabled={crearLeadMutation.isPending}
            >
              {crearLeadMutation.isPending ? 'Guardando…' : 'Guardar lead'}
            </Button>
          </DialogActions>
        </Box>
      </Dialog>

      {/* Drawer Detalle del Lead + Actividades */}
      <Drawer
        anchor="right"
        open={Boolean(leadDetalle)}
        onClose={() => setLeadDetalleId(null)}
        PaperProps={{ sx: { width: { xs: '100%', sm: 440 }, p: 2.5 } }}
      >
        {leadDetalle && (
          <Stack spacing={2}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Box>
                <Typography variant="h6" fontWeight={700}>
                  {`${leadDetalle.nombre} ${leadDetalle.apellido ?? ''}`.trim()}
                </Typography>
                {leadDetalle.empresa_nombre && (
                  <Typography variant="body2" color="text.secondary">
                    {leadDetalle.empresa_nombre}
                  </Typography>
                )}
              </Box>
              <IconButton
                aria-label="Cerrar detalle"
                onClick={() => setLeadDetalleId(null)}
              >
                <CloseOutlined />
              </IconButton>
            </Stack>

            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Chip size="small" label={leadDetalle.fuente ?? 'MANUAL'} color="primary" variant="outlined" />
              {leadDetalle.etapa_nombre && (
                <Chip size="small" label={leadDetalle.etapa_nombre} />
              )}
              {leadDetalle.propietario_nombre && (
                <Chip size="small" variant="outlined" label={`Propietario: ${leadDetalle.propietario_nombre}`} />
              )}
            </Stack>

            <Stack spacing={0.5}>
              {leadDetalle.email && (
                <Typography variant="body2">Correo: {leadDetalle.email}</Typography>
              )}
              {leadDetalle.telefono && (
                <Typography variant="body2">Teléfono: {leadDetalle.telefono}</Typography>
              )}
              {leadDetalle.mensaje && (
                <Typography variant="body2" color="text.secondary">
                  {leadDetalle.mensaje}
                </Typography>
              )}
            </Stack>

            <TextField
              select
              size="small"
              label="Etapa actual"
              value={leadDetalle.etapa ?? ''}
              onChange={(ev) => {
                const dest = ev.target.value;
                if (dest && leadDetalle.id_lead && dest !== leadDetalle.etapa) {
                  moverEtapaMutation.mutate({ leadId: leadDetalle.id_lead, etapaId: dest });
                }
              }}
            >
              {etapasOrdenadas.map((etapa) => (
                <MenuItem key={etapa.id_etapa} value={etapa.id_etapa ?? ''}>
                  {etapa.nombre}
                </MenuItem>
              ))}
            </TextField>

            <Divider />

            <Typography variant="subtitle1" fontWeight={700}>
              Registrar actividad
            </Typography>

            {actividadError && (
              <Alert severity="error" onClose={() => setActividadError('')}>
                {actividadError}
              </Alert>
            )}

            <Box component="form" onSubmit={handleCrearActividadSubmit} noValidate>
              <Stack spacing={1.5}>
                <TextField
                  select
                  size="small"
                  label="Tipo de actividad"
                  value={actividadForm.tipo}
                  onChange={(ev) =>
                    setActividadForm({ ...actividadForm, tipo: ev.target.value as TipoActividad })
                  }
                >
                  {TIPO_ACTIVIDAD_OPCIONES.map((opt) => (
                    <MenuItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </MenuItem>
                  ))}
                </TextField>
                <TextField
                  size="small"
                  label="Asunto"
                  required
                  value={actividadForm.asunto}
                  onChange={(ev) =>
                    setActividadForm({ ...actividadForm, asunto: ev.target.value })
                  }
                />
                <TextField
                  size="small"
                  label="Descripción"
                  multiline
                  minRows={2}
                  value={actividadForm.descripcion}
                  onChange={(ev) =>
                    setActividadForm({ ...actividadForm, descripcion: ev.target.value })
                  }
                />
                <TextField
                  size="small"
                  label="Fecha de vencimiento"
                  type="datetime-local"
                  slotProps={{ inputLabel: { shrink: true } }}
                  value={actividadForm.fecha_vencimiento}
                  onChange={(ev) =>
                    setActividadForm({ ...actividadForm, fecha_vencimiento: ev.target.value })
                  }
                />
                <Button
                  type="submit"
                  variant="contained"
                  disabled={crearActividadMutation.isPending}
                >
                  {crearActividadMutation.isPending ? 'Registrando…' : 'Registrar actividad'}
                </Button>
              </Stack>
            </Box>

            <Divider />

            <Typography variant="subtitle1" fontWeight={700}>
              Historial de actividades
            </Typography>

            {actividadesQuery.isLoading ? (
              <CircularProgress size={20} />
            ) : actividadesQuery.isError ? (
              <Alert severity="error">
                {mensajeDeError(actividadesQuery.error, 'No se pudieron cargar las actividades.')}
              </Alert>
            ) : (actividadesQuery.data ?? []).length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                Aún no hay actividades registradas para este lead.
              </Typography>
            ) : (
              <Stack spacing={1.25}>
                {(actividadesQuery.data ?? []).map((act: CrmActividad) => {
                  const actId = act.id_actividad ?? '';
                  const completada = Boolean(act.completada);
                  const tipoLabel =
                    ACTIVIDAD_LABEL.get(act.tipo ?? 'NOTA') ?? act.tipo ?? 'Nota';
                  return (
                    <Paper key={actId} variant="outlined" sx={{ p: 1.5 }}>
                      <Stack
                        direction="row"
                        justifyContent="space-between"
                        alignItems="center"
                        spacing={1}
                        sx={{ mb: 0.5 }}
                      >
                        <Stack direction="row" spacing={0.75} alignItems="center">
                          <Chip size="small" label={tipoLabel} variant="outlined" />
                          <Chip
                            size="small"
                            color={completada ? 'success' : 'warning'}
                            label={completada ? 'Completada' : 'Pendiente'}
                          />
                        </Stack>
                        <Button
                          size="small"
                          color={completada ? 'inherit' : 'success'}
                          startIcon={
                            completada ? <ReplayOutlined /> : <CheckCircleOutlineOutlined />
                          }
                          disabled={completarActividadMutation.isPending}
                          onClick={() =>
                            completarActividadMutation.mutate({
                              id: actId,
                              completada: !completada,
                            })
                          }
                        >
                          {completada ? 'Reabrir' : 'Completar'}
                        </Button>
                      </Stack>
                      <Typography variant="body2" fontWeight={600}>
                        {act.asunto}
                      </Typography>
                      {act.descripcion && (
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
                          {act.descripcion}
                        </Typography>
                      )}
                      {act.fecha_vencimiento && (
                        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                          Vence: {formatearFecha(act.fecha_vencimiento)}
                        </Typography>
                      )}
                      {act.fecha_completada && (
                        <Typography variant="caption" color="success.main" display="block">
                          Completada: {formatearFecha(act.fecha_completada)}
                        </Typography>
                      )}
                    </Paper>
                  );
                })}
              </Stack>
            )}
          </Stack>
        )}
      </Drawer>
    </PageContainer>
  );
};

export default CrmPipelineKanbanPage;
