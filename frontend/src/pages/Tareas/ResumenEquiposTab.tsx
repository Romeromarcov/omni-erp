import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { DataTable, KpiCard, SectionTitle } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  areasTareasService,
  proyectosTareasService,
  seguimientoTareasService,
  type AreaOperativa,
  type ResumenPorArea,
  type ResumenPorResponsable,
} from '../../services/tareasService';
import { fetchUsuarios } from '../../services/users';
import { tareasKeys } from '../../lib/queryKeys';
import { mensajeTareas } from './utils';

interface ResumenEquiposTabProps {
  empresaId: string | null;
}

const FORM_AREA_VACIO = {
  nombre: '',
  lider: '',
  palabras_clave_csv: '',
};

const FORM_PROY_VACIO = {
  nombre: '',
  descripcion: '',
  area: '',
  vista_predeterminada: 'TABLERO' as 'TABLERO' | 'LISTA',
};

const ResumenEquiposTab: React.FC<ResumenEquiposTabProps> = ({ empresaId }) => {
  const qc = useQueryClient();
  const [dialogArea, setDialogArea] = useState(false);
  const [dialogProy, setDialogProy] = useState(false);
  const [formArea, setFormArea] = useState(FORM_AREA_VACIO);
  const [formProy, setFormProy] = useState(FORM_PROY_VACIO);
  const [horasBloqueoEdit, setHorasBloqueoEdit] = useState<string>('');
  const [gerenteEdit, setGerenteEdit] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [infoMsg, setInfoMsg] = useState('');

  const { data: resumen, isLoading: cargandoResumen } = useQuery({
    queryKey: tareasKeys.resumen(empresaId),
    queryFn: () => seguimientoTareasService.getResumen(),
  });

  const { data: areas = [] } = useQuery({
    queryKey: tareasKeys.areas(empresaId),
    queryFn: () => areasTareasService.getAll(),
  });

  const { data: config } = useQuery({
    queryKey: tareasKeys.configuracion(empresaId),
    queryFn: () => seguimientoTareasService.getConfiguracion(),
  });

  const { data: usuarios = [] } = useQuery({
    queryKey: ['core', 'usuarios', empresaId ?? null],
    queryFn: () => fetchUsuarios(empresaId ?? undefined),
  });

  const invalidar = () => {
    void qc.invalidateQueries({ queryKey: tareasKeys.porEmpresa(empresaId) });
  };

  const ejecutarCiclo = useMutation({
    mutationFn: () => seguimientoTareasService.ejecutarCiclo('AUTO'),
    onSuccess: (res) => {
      setErrorMsg('');
      setInfoMsg(
        `Ciclo ejecutado (${res.momento}): ${res.recordatorios_preventivos} preventivos, ${res.escalaciones_vencidas} escalaciones, ${res.bloqueadas_automaticamente} bloqueos 72h, ${res.recurrentes_creadas} recurrentes.`,
      );
      invalidar();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo ejecutar el ciclo de seguimiento.'));
    },
  });

  const crearArea = useMutation({
    mutationFn: () =>
      areasTareasService.create({
        nombre: formArea.nombre.trim(),
        lider: formArea.lider || undefined,
        palabras_clave: formArea.palabras_clave_csv
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      }),
    onSuccess: () => {
      setDialogArea(false);
      setFormArea(FORM_AREA_VACIO);
      setErrorMsg('');
      setInfoMsg('Área operativa creada.');
      invalidar();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo crear el área operativa.'));
    },
  });

  const crearProyecto = useMutation({
    mutationFn: () =>
      proyectosTareasService.create({
        nombre: formProy.nombre.trim(),
        descripcion: formProy.descripcion.trim(),
        area: formProy.area || undefined,
        vista_predeterminada: formProy.vista_predeterminada,
      }),
    onSuccess: () => {
      setDialogProy(false);
      setFormProy(FORM_PROY_VACIO);
      setErrorMsg('');
      setInfoMsg('Proyecto creado con sus 5 secciones Kanban estándar.');
      invalidar();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo crear el proyecto.'));
    },
  });

  const guardarConfig = useMutation({
    mutationFn: () => {
      const horasNum = horasBloqueoEdit
        ? Number(horasBloqueoEdit)
        : (config?.horas_bloqueo_vencida ?? 72);
      const gerenteVal = gerenteEdit !== null ? gerenteEdit || null : (config?.gerente ?? null);
      return seguimientoTareasService.updateConfiguracion({
        horas_bloqueo_vencida: horasNum,
        gerente: gerenteVal,
      });
    },
    onSuccess: () => {
      setErrorMsg('');
      setInfoMsg('Parámetros de seguimiento actualizados.');
      invalidar();
    },
    onError: (e: unknown) => {
      setErrorMsg(mensajeTareas(e, 'No se pudo actualizar la configuración de seguimiento.'));
    },
  });

  const colsArea: Column<ResumenPorArea>[] = [
    { key: 'area', header: 'Área operativa', render: (r) => r.area_nombre },
    { key: 'abiertas', header: 'Abiertas', align: 'right', render: (r) => r.abiertas },
    { key: 'vencidas', header: 'Vencidas', align: 'right', render: (r) => r.vencidas },
    { key: 'bloqueadas', header: 'Bloqueadas', align: 'right', render: (r) => r.bloqueadas },
  ];

  const colsResp: Column<ResumenPorResponsable>[] = [
    { key: 'nombre', header: 'Responsable', render: (r) => r.nombre },
    { key: 'abiertas', header: 'Abiertas', align: 'right', render: (r) => r.abiertas },
    { key: 'vencidas', header: 'Vencidas', align: 'right', render: (r) => r.vencidas },
    { key: 'bloqueadas', header: 'Bloqueadas', align: 'right', render: (r) => r.bloqueadas },
  ];

  const colsCatalogoAreas: Column<AreaOperativa>[] = [
    { key: 'nombre', header: 'Nombre', render: (a) => a.nombre },
    { key: 'lider', header: 'Líder', render: (a) => a.lider_nombre || 'Sin líder' },
    {
      key: 'keywords',
      header: 'Palabras clave IA',
      render: (a) =>
        a.palabras_clave.length > 0 ? (
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {a.palabras_clave.map((kw) => (
              <Chip key={kw} size="small" variant="outlined" label={kw} />
            ))}
          </Stack>
        ) : (
          '—'
        ),
    },
  ];

  const tot = resumen?.totales;
  const horasActuales =
    horasBloqueoEdit !== '' ? horasBloqueoEdit : String(config?.horas_bloqueo_vencida ?? 72);
  const gerenteActual = gerenteEdit !== null ? gerenteEdit : (config?.gerente ?? '');

  return (
    <Box>
      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}
      {infoMsg && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setInfoMsg('')}>
          {infoMsg}
        </Alert>
      )}

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1.5}
        justifyContent="space-between"
        sx={{ mb: 2.5 }}
      >
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button variant="outlined" onClick={() => setDialogArea(true)}>
            Nueva área operativa
          </Button>
          <Button variant="outlined" onClick={() => setDialogProy(true)}>
            Nuevo proyecto
          </Button>
        </Stack>
        <Button
          variant="contained"
          disabled={ejecutarCiclo.isPending}
          onClick={() => ejecutarCiclo.mutate()}
        >
          Ejecutar ciclo de seguimiento
        </Button>
      </Stack>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: 2,
          mb: 3,
        }}
      >
        <KpiCard label="Abiertas" value={tot?.abiertas ?? 0} tone="brand" />
        <KpiCard
          label="Vencidas"
          value={tot?.vencidas ?? 0}
          tone="error"
          emphasizeError={Boolean(tot && tot.vencidas > 0)}
        />
        <KpiCard label="Vencen hoy" value={tot?.vencen_hoy ?? 0} tone="warning" />
        <KpiCard
          label="Bloqueadas 72h+"
          value={tot?.bloqueadas_por_escalacion ?? 0}
          tone="error"
        />
        <KpiCard label="Completadas hoy" value={tot?.completadas_hoy ?? 0} tone="success" />
      </Box>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' },
          gap: 2.5,
          mb: 3,
        }}
      >
        <Box>
          <SectionTitle>Carga por área operativa</SectionTitle>
          <DataTable
            columns={colsArea}
            rows={resumen?.por_area ?? []}
            getRowKey={(r) => r.area_id ?? r.area_nombre}
            loading={cargandoResumen}
            emptyMessage="Sin tareas abiertas agrupadas por área."
          />
        </Box>
        <Box>
          <SectionTitle>Carga por responsable</SectionTitle>
          <DataTable
            columns={colsResp}
            rows={resumen?.por_responsable ?? []}
            getRowKey={(r) => r.usuario_id ?? r.username}
            loading={cargandoResumen}
            emptyMessage="Sin tareas abiertas asignadas."
          />
        </Box>
      </Box>

      <Box sx={{ mb: 3 }}>
        <SectionTitle>Áreas operativas registradas</SectionTitle>
        <DataTable
          columns={colsCatalogoAreas}
          rows={areas}
          getRowKey={(a) => a.id_area}
          emptyMessage="Aún no hay áreas operativas registradas."
        />
      </Box>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle1" fontWeight={700} gutterBottom>
            Reglas de escalación y seguimiento determinístico
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Zona horaria activa: {config?.zona_horaria ?? 'America/Caracas'} · Recordatorios:{' '}
            {config?.hora_recordatorio_manana ?? '09:00:00'} y{' '}
            {config?.hora_recordatorio_tarde ?? '15:00:00'}.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }}>
            <TextField
              size="small"
              type="number"
              label="Horas vencida para bloqueo automático"
              value={horasActuales}
              onChange={(ev) => setHorasBloqueoEdit(ev.target.value)}
              sx={{ minWidth: 260 }}
            />
            <TextField
              select
              size="small"
              label="Gerente receptor de escalación"
              value={gerenteActual}
              onChange={(ev) => setGerenteEdit(ev.target.value)}
              sx={{ minWidth: 260 }}
            >
              <MenuItem value="">Sin gerente asignado</MenuItem>
              {usuarios.map((u) => (
                <MenuItem key={u.id} value={u.id}>
                  {`${u.first_name} ${u.last_name}`.trim() || u.username}
                </MenuItem>
              ))}
            </TextField>
            <Button
              variant="contained"
              disabled={guardarConfig.isPending}
              onClick={() => guardarConfig.mutate()}
            >
              Guardar reglas
            </Button>
          </Stack>
        </CardContent>
      </Card>

      {/* Diálogo Nueva Área */}
      <Dialog open={dialogArea} onClose={() => setDialogArea(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Nueva área operativa</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Nombre del área"
              required
              fullWidth
              value={formArea.nombre}
              onChange={(ev) => setFormArea({ ...formArea, nombre: ev.target.value })}
            />
            <TextField
              select
              label="Líder del área"
              fullWidth
              value={formArea.lider}
              onChange={(ev) => setFormArea({ ...formArea, lider: ev.target.value })}
            >
              <MenuItem value="">Sin líder asignado</MenuItem>
              {usuarios.map((u) => (
                <MenuItem key={u.id} value={u.id}>
                  {`${u.first_name} ${u.last_name}`.trim() || u.username}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Palabras clave para clasificación IA (separadas por coma)"
              placeholder="conciliación, banco, cobranza"
              fullWidth
              value={formArea.palabras_clave_csv}
              onChange={(ev) =>
                setFormArea({ ...formArea, palabras_clave_csv: ev.target.value })
              }
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogArea(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={!formArea.nombre.trim() || crearArea.isPending}
            onClick={() => crearArea.mutate()}
          >
            Crear área
          </Button>
        </DialogActions>
      </Dialog>

      {/* Diálogo Nuevo Proyecto */}
      <Dialog open={dialogProy} onClose={() => setDialogProy(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Nuevo proyecto / tablero</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Nombre del proyecto"
              required
              fullWidth
              value={formProy.nombre}
              onChange={(ev) => setFormProy({ ...formProy, nombre: ev.target.value })}
            />
            <TextField
              label="Descripción"
              multiline
              minRows={2}
              fullWidth
              value={formProy.descripcion}
              onChange={(ev) => setFormProy({ ...formProy, descripcion: ev.target.value })}
            />
            <TextField
              select
              label="Área operativa"
              fullWidth
              value={formProy.area}
              onChange={(ev) => setFormProy({ ...formProy, area: ev.target.value })}
            >
              <MenuItem value="">Transversal / Sin área</MenuItem>
              {areas.map((a) => (
                <MenuItem key={a.id_area} value={a.id_area}>
                  {a.nombre}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogProy(false)}>Cancelar</Button>
          <Button
            variant="contained"
            disabled={!formProy.nombre.trim() || crearProyecto.isPending}
            onClick={() => crearProyecto.mutate()}
          >
            Crear proyecto
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ResumenEquiposTab;
