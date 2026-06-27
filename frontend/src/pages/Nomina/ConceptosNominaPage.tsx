import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  conceptosNominaService,
  type ConceptoNomina,
  type ConceptoNominaPayload,
} from '../../services/nominaExtrasService';
import { nominaExtrasKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const TIPOS: { value: ConceptoNomina['tipo_concepto'] | ''; label: string }[] = [
  { value: '', label: 'Todos' },
  { value: 'DEVENGADO', label: 'Devengado' },
  { value: 'DEDUCCION', label: 'Deducción' },
  { value: 'APORTE_PATRONAL', label: 'Aporte patronal' },
];

const TIPO_OPCIONES = TIPOS.filter((t) => t.value !== '');

const CATEGORIAS: { value: string; label: string }[] = [
  { value: 'SUELDO_BASE', label: 'Sueldo base' },
  { value: 'HORAS_EXTRAS', label: 'Horas extras' },
  { value: 'COMISION', label: 'Comisión' },
  { value: 'BONO', label: 'Bono' },
  { value: 'VACACIONES', label: 'Vacaciones' },
  { value: 'PRESTACIONES', label: 'Prestaciones' },
  { value: 'SEGURO_SOCIAL', label: 'Seguro social' },
  { value: 'IMPUESTO_RENTA', label: 'Impuesto sobre la renta' },
  { value: 'OTROS', label: 'Otros' },
];

const TIPO_COLOR: Record<string, 'success' | 'error' | 'warning' | 'default'> = {
  devengado: 'success',
  deduccion: 'error',
  aporte_patronal: 'warning',
};

const etiquetaTipo = (v: string) => TIPOS.find((t) => t.value === v)?.label ?? v;
const etiquetaCategoria = (v: string) => CATEGORIAS.find((c) => c.value === v)?.label ?? v;

interface FormState {
  codigo_concepto: string;
  nombre_concepto: string;
  tipo_concepto: string;
  categoria: string;
  formula_calculo: string;
  es_fijo: boolean;
  monto_fijo: string;
  es_porcentaje: boolean;
  porcentaje: string;
  activo: boolean;
}

const formVacio = (): FormState => ({
  codigo_concepto: '',
  nombre_concepto: '',
  tipo_concepto: 'DEVENGADO',
  categoria: 'OTROS',
  formula_calculo: '',
  es_fijo: false,
  monto_fijo: '',
  es_porcentaje: false,
  porcentaje: '',
  activo: true,
});

const ConceptosNominaPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroTipo, setFiltroTipo] = useState<ConceptoNomina['tipo_concepto'] | ''>('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<ConceptoNomina | null>(null);
  const [form, setForm] = useState<FormState>(formVacio());
  const [errorMsg, setErrorMsg] = useState('');

  const { data: conceptos = [], isLoading } = useQuery({
    queryKey: nominaExtrasKeys.conceptos(filtroTipo),
    queryFn: () =>
      filtroTipo
        ? conceptosNominaService.porTipo(filtroTipo)
        : conceptosNominaService.getAll(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: nominaExtrasKeys.conceptosAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(formVacio());
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (c: ConceptoNomina) => {
    setEditando(c);
    setForm({
      codigo_concepto: c.codigo_concepto,
      nombre_concepto: c.nombre_concepto,
      tipo_concepto: c.tipo_concepto,
      categoria: c.categoria,
      formula_calculo: c.formula_calculo ?? '',
      es_fijo: c.es_fijo,
      monto_fijo: c.monto_fijo ?? '',
      es_porcentaje: c.es_porcentaje,
      porcentaje: c.porcentaje ?? '',
      activo: c.activo,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: ConceptoNominaPayload) =>
      editando
        ? conceptosNominaService.update(editando.id_concepto_nomina, payload)
        : conceptosNominaService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar el concepto.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => conceptosNominaService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar el concepto.')),
  });

  const handleGuardar = () => {
    if (!form.codigo_concepto.trim() || !form.nombre_concepto.trim()) {
      setErrorMsg('Complete el código y el nombre del concepto.');
      return;
    }
    guardar.mutate({
      id_empresa: empresaId,
      codigo_concepto: form.codigo_concepto.trim(),
      nombre_concepto: form.nombre_concepto.trim(),
      tipo_concepto: form.tipo_concepto,
      categoria: form.categoria,
      formula_calculo: form.formula_calculo.trim() || null,
      es_fijo: form.es_fijo,
      monto_fijo: form.es_fijo ? form.monto_fijo.trim() || '0' : null,
      es_porcentaje: form.es_porcentaje,
      porcentaje: form.es_porcentaje ? form.porcentaje.trim() || '0' : null,
      activo: form.activo,
    });
  };

  const handleEliminar = (c: ConceptoNomina) => {
    if (window.confirm(`¿Eliminar el concepto "${c.nombre_concepto}"?`)) {
      eliminar.mutate(c.id_concepto_nomina);
    }
  };

  const columns: Column<ConceptoNomina>[] = [
    { key: 'codigo_concepto', header: 'Código', render: (c) => c.codigo_concepto },
    { key: 'nombre_concepto', header: 'Nombre', render: (c) => c.nombre_concepto },
    {
      key: 'tipo_concepto',
      header: 'Tipo',
      render: (c) => (
        <StatusChip value={c.tipo_concepto} label={etiquetaTipo(c.tipo_concepto)} colorMap={TIPO_COLOR} />
      ),
    },
    { key: 'categoria', header: 'Categoría', render: (c) => etiquetaCategoria(c.categoria) },
    {
      key: 'valor',
      header: 'Valor',
      render: (c) =>
        c.es_fijo
          ? `Fijo ${c.monto_fijo ?? '0'}`
          : c.es_porcentaje
            ? `${c.porcentaje ?? '0'}%`
            : c.formula_calculo
              ? 'Fórmula'
              : '—',
    },
    { key: 'activo', header: 'Activo', render: (c) => <StatusChip value={c.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (c) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(c)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(c)}
          >
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Conceptos de Nómina"
        subtitle="Catálogo de devengados, deducciones y aportes patronales: la configuración base que usan los procesos de nómina."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Nuevo concepto
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
        onChange={(e) => setFiltroTipo(e.target.value as ConceptoNomina['tipo_concepto'] | '')}
        size="small"
        sx={{ mb: 2, minWidth: 240 }}
      >
        {TIPOS.map((t) => (
          <MenuItem key={t.value || 'todos'} value={t.value}>
            {t.label}
          </MenuItem>
        ))}
      </TextField>

      <DataTable
        columns={columns}
        rows={conceptos}
        getRowKey={(c) => c.id_concepto_nomina}
        loading={isLoading}
        emptyMessage="Sin conceptos. Crea el primero."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar concepto' : 'Nuevo concepto'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Código"
                value={form.codigo_concepto}
                onChange={(e) => setForm((f) => ({ ...f, codigo_concepto: e.target.value }))}
                required
                fullWidth
              />
              <TextField
                select
                label="Tipo"
                value={form.tipo_concepto}
                onChange={(e) => setForm((f) => ({ ...f, tipo_concepto: e.target.value }))}
                fullWidth
              >
                {TIPO_OPCIONES.map((t) => (
                  <MenuItem key={t.value} value={t.value}>
                    {t.label}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <TextField
              label="Nombre"
              value={form.nombre_concepto}
              onChange={(e) => setForm((f) => ({ ...f, nombre_concepto: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              select
              label="Categoría"
              value={form.categoria}
              onChange={(e) => setForm((f) => ({ ...f, categoria: e.target.value }))}
              fullWidth
            >
              {CATEGORIAS.map((c) => (
                <MenuItem key={c.value} value={c.value}>
                  {c.label}
                </MenuItem>
              ))}
            </TextField>
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.es_fijo}
                  onChange={(e) => setForm((f) => ({ ...f, es_fijo: e.target.checked }))}
                />
              }
              label="Monto fijo"
            />
            {form.es_fijo && (
              <TextField
                label="Valor del monto fijo"
                value={form.monto_fijo}
                onChange={(e) => setForm((f) => ({ ...f, monto_fijo: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
            )}
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.es_porcentaje}
                  onChange={(e) => setForm((f) => ({ ...f, es_porcentaje: e.target.checked }))}
                />
              }
              label="Porcentaje"
            />
            {form.es_porcentaje && (
              <TextField
                label="Porcentaje (%)"
                value={form.porcentaje}
                onChange={(e) => setForm((f) => ({ ...f, porcentaje: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
            )}
            <TextField
              label="Fórmula de cálculo"
              value={form.formula_calculo}
              onChange={(e) => setForm((f) => ({ ...f, formula_calculo: e.target.value }))}
              helperText="Opcional: expresión usada por el motor de nómina."
              multiline
              minRows={2}
              fullWidth
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.activo}
                  onChange={(e) => setForm((f) => ({ ...f, activo: e.target.checked }))}
                />
              }
              label="Activo"
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

export default ConceptosNominaPage;
