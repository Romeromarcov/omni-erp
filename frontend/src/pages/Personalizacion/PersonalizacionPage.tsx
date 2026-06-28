import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  personalizacionConfigService,
  ACTIVO_COLOR,
  type PersonalizacionConfig,
  type PersonalizacionConfigPayload,
} from '../../services/personalizacionService';
import { personalizacionKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

// ── Formulario de nueva versión ───────────────────────────────────────────────

interface ConfigForm {
  descripcion: string;
  config_yaml: string;
  config_dict: string;
}

const CONFIG_VACIA: ConfigForm = {
  descripcion: '',
  config_yaml: '',
  config_dict: '{}',
};

const PersonalizacionPage: React.FC = () => {
  const empresaId = getEmpresaId() || '';
  const queryClient = useQueryClient();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<ConfigForm>(CONFIG_VACIA);
  const [errorMsg, setErrorMsg] = useState('');
  const [detalle, setDetalle] = useState<PersonalizacionConfig | null>(null);

  const { data: activa = null } = useQuery({
    queryKey: personalizacionKeys.activa(empresaId),
    queryFn: () => personalizacionConfigService.activa(empresaId || undefined),
  });

  const { data: historial = [], isLoading } = useQuery({
    queryKey: personalizacionKeys.historial(empresaId),
    queryFn: () => personalizacionConfigService.historial(empresaId || undefined),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: personalizacionKeys.all() });

  const abrirCrear = () => {
    setForm(CONFIG_VACIA);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: PersonalizacionConfigPayload) =>
      personalizacionConfigService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo crear la versión.')),
  });

  const activar = useMutation({
    mutationFn: (id: string) => personalizacionConfigService.activar(id),
    onSuccess: invalidate,
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo activar la versión.')),
  });

  const handleGuardar = () => {
    if (!empresaId) {
      setErrorMsg('Seleccione una empresa para crear una versión.');
      return;
    }
    let dict: unknown;
    try {
      dict = JSON.parse(form.config_dict || '{}');
    } catch {
      setErrorMsg('El config_dict (JSON) no es válido.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      descripcion: form.descripcion.trim(),
      config_yaml: form.config_yaml,
      config_dict: dict,
    });
  };

  const handleActivar = (c: PersonalizacionConfig) => {
    setErrorMsg('');
    if (
      window.confirm(
        `¿Activar la versión ${c.version}? Esta acción es un rollback: desactiva la versión actualmente activa.`,
      )
    ) {
      activar.mutate(c.id_config);
    }
  };

  const columns: Column<PersonalizacionConfig>[] = [
    { key: 'version', header: 'Versión', render: (c) => `v${c.version}` },
    { key: 'descripcion', header: 'Descripción', render: (c) => c.descripcion || '—' },
    {
      key: 'activo',
      header: 'Activa',
      render: (c) => <StatusChip value={c.activo} colorMap={ACTIVO_COLOR} />,
    },
    {
      key: 'fecha_creacion',
      header: 'Creada',
      render: (c) => (c.fecha_creacion ?? '').slice(0, 10) || '—',
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (c) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalle(c)}>
            Ver detalle
          </Button>
          {!c.activo && (
            <Button
              size="small"
              color="primary"
              disabled={activar.isPending}
              onClick={() => handleActivar(c)}
            >
              Activar
            </Button>
          )}
        </Stack>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Personalización"
        subtitle="Versiones del DSL de personalización por empresa: activa, historial y rollback."
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      {/* Configuración activa */}
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="subtitle2" color="text.secondary" gutterBottom>
            Configuración activa
          </Typography>
          {activa ? (
            <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
              <Typography variant="h6">Versión {activa.version}</Typography>
              <StatusChip value={activa.activo} colorMap={ACTIVO_COLOR} />
              <Typography variant="body2" color="text.secondary">
                {activa.descripcion || 'Sin descripción'}
              </Typography>
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No hay ninguna configuración activa para esta empresa. Crea una versión
              y actívala.
            </Typography>
          )}
        </CardContent>
      </Card>

      {/* Historial de versiones */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h6">Historial de versiones</Typography>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva versión
        </Button>
      </Stack>

      <DataTable
        columns={columns}
        rows={historial}
        getRowKey={(c) => c.id_config}
        loading={isLoading}
        emptyMessage="Sin versiones de configuración. Crea la primera."
      />

      {/* Dialog: crear nueva versión */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Nueva versión</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Descripción"
              value={form.descripcion}
              onChange={(e) => setForm((f) => ({ ...f, descripcion: e.target.value }))}
              fullWidth
            />
            <TextField
              label="config_yaml (DSL)"
              value={form.config_yaml}
              onChange={(e) => setForm((f) => ({ ...f, config_yaml: e.target.value }))}
              multiline
              minRows={6}
              helperText="El DSL de personalización en formato YAML."
              fullWidth
            />
            <TextField
              label="config_dict (JSON)"
              value={form.config_dict}
              onChange={(e) => setForm((f) => ({ ...f, config_dict: e.target.value }))}
              multiline
              minRows={4}
              helperText="Representación serializada del DSL como JSON."
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

      {/* Dialog: detalle de una versión */}
      <Dialog open={!!detalle} onClose={() => setDetalle(null)} fullWidth maxWidth="md">
        <DialogTitle>
          {detalle ? `Versión ${detalle.version}` : 'Detalle'}
        </DialogTitle>
        <DialogContent>
          {detalle && (
            <Stack spacing={2} sx={{ mt: 1 }}>
              <Typography variant="body2" color="text.secondary">
                {detalle.descripcion || 'Sin descripción'}
              </Typography>
              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  config_yaml
                </Typography>
                <Box
                  component="pre"
                  sx={{
                    m: 0,
                    p: 1.5,
                    bgcolor: 'action.hover',
                    borderRadius: 1,
                    overflow: 'auto',
                    fontSize: 13,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {detalle.config_yaml || '—'}
                </Box>
              </Box>
              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  config_dict
                </Typography>
                <Box
                  component="pre"
                  sx={{
                    m: 0,
                    p: 1.5,
                    bgcolor: 'action.hover',
                    borderRadius: 1,
                    overflow: 'auto',
                    fontSize: 13,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {JSON.stringify(detalle.config_dict ?? {}, null, 2)}
                </Box>
              </Box>
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetalle(null)}>Cerrar</Button>
        </DialogActions>
      </Dialog>
    </PageContainer>
  );
};

export default PersonalizacionPage;
