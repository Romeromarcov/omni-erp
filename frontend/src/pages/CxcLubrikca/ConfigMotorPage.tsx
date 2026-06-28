/**
 * Configuración del Motor — CxC Lubrikca.
 *
 * Página con pestañas (una por entidad de configuración del motor). Cada
 * pestaña lista la entidad (DataTable), permite crear/editar vía Dialog con
 * react-hook-form + zodResolver y hace soft-delete. Los porcentajes se muestran
 * como % pero se guardan/envían como fracción string (0.03 = 3 %).
 */
import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Alert,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  Tab,
  Tabs,
  TextField,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import EditOutlined from '@mui/icons-material/EditOutlined';
import DeleteOutline from '@mui/icons-material/DeleteOutline';
import { cxcLubrikcaService } from '../../services/cxcLubrikcaService';
import { cxcLubrikcaKeys } from '../../lib/queryKeys';
import {
  descuentoMarcaSchema,
  descuentoBcvSchema,
  promocionSchema,
  reglaRecurrenciaSchema,
  feriadoSchema,
  metodoPagoSchema,
  configConciliacionSchema,
} from '../../schemas/cxcLubrikca.schemas';
import { mensajeDeError } from '../../utils/api';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import type { ZodTypeAny } from 'zod';

// ── Tipos de definición de pestaña ──────────────────────────────────────────

type FieldType = 'text' | 'number' | 'percent' | 'date' | 'select' | 'switch';

interface FieldDef {
  name: string;
  label: string;
  type: FieldType;
  options?: { value: string; label: string }[];
  optional?: boolean;
}

interface TabDef {
  key: string;
  label: string;
  schema: ZodTypeAny;
  queryKey: readonly unknown[];
  list: () => Promise<Record<string, unknown>[]>;
  create: (data: Record<string, unknown>) => Promise<unknown>;
  update: (id: number | string, data: Record<string, unknown>) => Promise<unknown>;
  remove: (id: number | string) => Promise<void>;
  columns: Column<Record<string, unknown>>[];
  fields: FieldDef[];
  /** Valores por defecto del formulario de creación. */
  defaults: Record<string, unknown>;
}

// Las opciones de los selects reflejan los TextChoices del backend.
const TIPO_DESCUENTO_OPTS = [{ value: 'contado', label: 'Contado' }];
const CONDICION_OPTS = [
  { value: 'primera_compra', label: 'Primera compra' },
  { value: 'recompra', label: 'Recompra' },
];
const TIPO_BENEFICIO_OPTS = [
  { value: 'nota_credito', label: 'Nota de crédito' },
  { value: 'porcentaje', label: 'Porcentaje' },
];
const TIPO_FERIADO_OPTS = [
  { value: 'nacional', label: 'Nacional' },
  { value: 'regional', label: 'Regional' },
  { value: 'bancario', label: 'Bancario' },
];
const MONEDA_OPTS = [
  { value: 'USD', label: 'USD' },
  { value: 'VES', label: 'VES' },
];
const TIPO_TASA_OPTS = [
  { value: 'BCV', label: 'BCV' },
  { value: 'Binance', label: 'Binance' },
  { value: 'N_A', label: 'N/A' },
];

const str = (v: unknown): string => (v == null ? '—' : String(v));
// Fracción string → "%": 0.03 → "3%".
const pct = (v: unknown): string => {
  const n = parseFloat(String(v ?? '0'));
  if (Number.isNaN(n)) return '—';
  return `${(n * 100).toLocaleString('es-VE', { maximumFractionDigits: 4 })}%`;
};
const boolChip = (v: unknown) => <StatusChip value={Boolean(v)} />;

const vigenciaCols: Column<Record<string, unknown>>[] = [
  { key: 'desde', header: 'Desde', render: (r) => str(r.vigencia_desde) },
  { key: 'hasta', header: 'Hasta', render: (r) => str(r.vigencia_hasta) },
  { key: 'activo', header: 'Activo', render: (r) => boolChip(r.activo) },
];

const vigenciaFields: FieldDef[] = [
  { name: 'vigencia_desde', label: 'Vigencia desde', type: 'date' },
  { name: 'vigencia_hasta', label: 'Vigencia hasta', type: 'date', optional: true },
  { name: 'activo', label: 'Activo', type: 'switch', optional: true },
];

function buildTabs(svc: typeof cxcLubrikcaService): TabDef[] {
  return [
    {
      key: 'descuentos-marca',
      label: 'Descuentos Marca/Categoría',
      schema: descuentoMarcaSchema,
      queryKey: cxcLubrikcaKeys.descuentosMarcaAll(),
      list: () => svc.listDescuentosMarca() as unknown as Promise<Record<string, unknown>[]>,
      create: (d) => svc.crearDescuentoMarca(d),
      update: (id, d) => svc.actualizarDescuentoMarca(id, d),
      remove: (id) => svc.eliminarDescuentoMarca(id),
      columns: [
        { key: 'marca', header: 'Marca', render: (r) => str(r.marca) },
        { key: 'categoria', header: 'Categoría', render: (r) => str(r.categoria) },
        { key: 'tipo', header: 'Tipo', render: (r) => str(r.tipo_descuento) },
        { key: 'porcentaje', header: 'Descuento', align: 'right', render: (r) => pct(r.porcentaje) },
        ...vigenciaCols,
      ],
      fields: [
        { name: 'marca', label: 'Marca', type: 'text' },
        { name: 'categoria', label: 'Categoría', type: 'text' },
        { name: 'tipo_descuento', label: 'Tipo de descuento', type: 'select', options: TIPO_DESCUENTO_OPTS },
        { name: 'porcentaje', label: 'Porcentaje (fracción, 0.03 = 3%)', type: 'percent' },
        ...vigenciaFields,
      ],
      defaults: {
        marca: '*',
        categoria: '*',
        tipo_descuento: 'contado',
        porcentaje: '',
        vigencia_desde: '',
        vigencia_hasta: '',
        activo: true,
      },
    },
    {
      key: 'descuentos-bcv',
      label: 'BCV-Completo',
      schema: descuentoBcvSchema,
      queryKey: cxcLubrikcaKeys.descuentosBcvAll(),
      list: () => svc.listDescuentosBcv() as unknown as Promise<Record<string, unknown>[]>,
      create: (d) => svc.crearDescuentoBcv(d),
      update: (id, d) => svc.actualizarDescuentoBcv(id, d),
      remove: (id) => svc.eliminarDescuentoBcv(id),
      columns: [
        { key: 'porcentaje', header: 'Descuento', align: 'right', render: (r) => pct(r.porcentaje) },
        ...vigenciaCols,
      ],
      fields: [
        { name: 'porcentaje', label: 'Porcentaje (fracción, 0.03 = 3%)', type: 'percent' },
        ...vigenciaFields,
      ],
      defaults: { porcentaje: '', vigencia_desde: '', vigencia_hasta: '', activo: true },
    },
    {
      key: 'promociones',
      label: 'Promos 1ra compra',
      schema: promocionSchema,
      queryKey: cxcLubrikcaKeys.promocionesAll(),
      list: () => svc.listPromociones() as unknown as Promise<Record<string, unknown>[]>,
      create: (d) => svc.crearPromocion(d),
      update: (id, d) => svc.actualizarPromocion(id, d),
      remove: (id) => svc.eliminarPromocion(id),
      columns: [
        { key: 'producto', header: 'Producto', render: (r) => str(r.producto) },
        ...vigenciaCols,
      ],
      fields: [
        { name: 'producto', label: 'Producto', type: 'text' },
        ...vigenciaFields,
      ],
      defaults: { producto: '', vigencia_desde: '', vigencia_hasta: '', activo: true },
    },
    {
      key: 'recurrencia',
      label: 'Recurrencia',
      schema: reglaRecurrenciaSchema,
      queryKey: cxcLubrikcaKeys.recurrenciaAll(),
      list: () => svc.listReglasRecurrencia() as unknown as Promise<Record<string, unknown>[]>,
      create: (d) => svc.crearReglaRecurrencia(d),
      update: (id, d) => svc.actualizarReglaRecurrencia(id, d),
      remove: (id) => svc.eliminarReglaRecurrencia(id),
      columns: [
        { key: 'condicion', header: 'Condición', render: (r) => str(r.condicion) },
        { key: 'beneficio', header: 'Beneficio', render: (r) => str(r.tipo_beneficio) },
        { key: 'valor', header: 'Valor', align: 'right', render: (r) => str(r.valor) },
        ...vigenciaCols,
      ],
      fields: [
        { name: 'condicion', label: 'Condición', type: 'select', options: CONDICION_OPTS },
        { name: 'tipo_beneficio', label: 'Tipo de beneficio', type: 'select', options: TIPO_BENEFICIO_OPTS },
        { name: 'valor', label: 'Valor', type: 'number' },
        ...vigenciaFields,
      ],
      defaults: {
        condicion: 'primera_compra',
        tipo_beneficio: 'nota_credito',
        valor: '',
        vigencia_desde: '',
        vigencia_hasta: '',
        activo: true,
      },
    },
    {
      key: 'feriados',
      label: 'Feriados',
      schema: feriadoSchema,
      queryKey: cxcLubrikcaKeys.feriadosAll(),
      list: () => svc.listFeriados() as unknown as Promise<Record<string, unknown>[]>,
      create: (d) => svc.crearFeriado(d),
      update: (id, d) => svc.actualizarFeriado(id, d),
      remove: (id) => svc.eliminarFeriado(id),
      columns: [
        { key: 'fecha', header: 'Fecha', render: (r) => str(r.fecha) },
        { key: 'descripcion', header: 'Descripción', render: (r) => str(r.descripcion) },
        { key: 'tipo', header: 'Tipo', render: (r) => str(r.tipo) },
        { key: 'activo', header: 'Activo', render: (r) => boolChip(r.activo) },
      ],
      fields: [
        { name: 'fecha', label: 'Fecha', type: 'date' },
        { name: 'descripcion', label: 'Descripción', type: 'text' },
        { name: 'tipo', label: 'Tipo', type: 'select', options: TIPO_FERIADO_OPTS },
        { name: 'activo', label: 'Activo', type: 'switch', optional: true },
      ],
      defaults: { fecha: '', descripcion: '', tipo: 'nacional', activo: true },
    },
    {
      key: 'metodos-pago',
      label: 'Métodos de Pago',
      schema: metodoPagoSchema,
      queryKey: cxcLubrikcaKeys.metodosPagoAll(),
      list: () => svc.listMetodosPago() as unknown as Promise<Record<string, unknown>[]>,
      create: (d) => svc.crearMetodoPago(d),
      update: (id, d) => svc.actualizarMetodoPago(id, d),
      remove: (id) => svc.eliminarMetodoPago(id),
      columns: [
        { key: 'codigo', header: 'Código', render: (r) => str(r.codigo) },
        { key: 'nombre', header: 'Nombre', render: (r) => str(r.nombre) },
        { key: 'moneda', header: 'Moneda', render: (r) => str(r.moneda) },
        { key: 'tasa', header: 'Tasa', render: (r) => str(r.tipo_tasa) },
        { key: 'contado', header: 'Contado', render: (r) => boolChip(r.es_contado) },
        { key: 'activo', header: 'Activo', render: (r) => boolChip(r.activo) },
      ],
      fields: [
        { name: 'codigo', label: 'Código', type: 'text' },
        { name: 'nombre', label: 'Nombre', type: 'text' },
        { name: 'moneda', label: 'Moneda', type: 'select', options: MONEDA_OPTS },
        { name: 'tipo_tasa', label: 'Tipo de tasa', type: 'select', options: TIPO_TASA_OPTS },
        { name: 'es_contado', label: 'Es contado', type: 'switch', optional: true },
        { name: 'activo', label: 'Activo', type: 'switch', optional: true },
      ],
      defaults: {
        codigo: '',
        nombre: '',
        moneda: 'USD',
        tipo_tasa: 'BCV',
        es_contado: false,
        activo: true,
      },
    },
    {
      key: 'config-conciliacion',
      label: 'Tolerancias Conciliación',
      schema: configConciliacionSchema,
      queryKey: cxcLubrikcaKeys.configConciliacionAll(),
      list: () => svc.listConfigConciliacion() as unknown as Promise<Record<string, unknown>[]>,
      create: (d) => svc.crearConfigConciliacion(d),
      update: (id, d) => svc.actualizarConfigConciliacion(id, d),
      remove: (id) => svc.eliminarConfigConciliacion(id),
      columns: [
        { key: 'rounding', header: 'Tolerancia redondeo', align: 'right', render: (r) => str(r.tolerance_rounding) },
        { key: 'red', header: 'Tolerancia roja', align: 'right', render: (r) => str(r.tolerance_red) },
      ],
      fields: [
        { name: 'tolerance_rounding', label: 'Tolerancia de redondeo', type: 'number' },
        { name: 'tolerance_red', label: 'Tolerancia roja', type: 'number' },
      ],
      defaults: { tolerance_rounding: '', tolerance_red: '' },
    },
  ];
}

// ── Componente de pestaña (lista + diálogo CRUD) ────────────────────────────

function ConfigTab({ def }: { def: TabDef }) {
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Record<string, unknown> | null>(null);
  const [errorGeneral, setErrorGeneral] = useState('');

  const { data: rows = [], isLoading } = useQuery({
    queryKey: def.queryKey,
    queryFn: def.list,
  });

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors },
  } = useForm<Record<string, unknown>>({
    resolver: zodResolver(def.schema),
    defaultValues: def.defaults,
  });

  const mutation = useMutation({
    mutationFn: (values: Record<string, unknown>) => {
      // vigencia_hasta vacía → null (el backend espera null, no "").
      const payload: Record<string, unknown> = { ...values };
      if ('vigencia_hasta' in payload && payload.vigencia_hasta === '') {
        payload.vigencia_hasta = null;
      }
      return editing
        ? def.update(editing.id as number | string, payload)
        : def.create(payload);
    },
    onSuccess: () => {
      snackbar.success(editing ? 'Registro actualizado.' : 'Registro creado.');
      cerrar();
      queryClient.invalidateQueries({ queryKey: def.queryKey });
    },
    onError: (err: unknown) => {
      setErrorGeneral(mensajeDeError(err, 'No se pudo guardar el registro.'));
    },
  });

  const removeMutation = useMutation({
    mutationFn: (id: number | string) => def.remove(id),
    onSuccess: () => {
      snackbar.success('Registro eliminado.');
      queryClient.invalidateQueries({ queryKey: def.queryKey });
    },
    onError: (err: unknown) => {
      snackbar.error(mensajeDeError(err, 'No se pudo eliminar el registro.'));
    },
  });

  function abrirCrear() {
    setEditing(null);
    setErrorGeneral('');
    reset(def.defaults);
    setDialogOpen(true);
  }

  function abrirEditar(row: Record<string, unknown>) {
    setEditing(row);
    setErrorGeneral('');
    // Normaliza nulls a "" para los inputs controlados/registrados.
    const values: Record<string, unknown> = { ...def.defaults };
    for (const f of def.fields) {
      const raw = row[f.name];
      values[f.name] = raw == null ? (f.type === 'switch' ? false : '') : raw;
    }
    reset(values);
    setDialogOpen(true);
  }

  function cerrar() {
    setDialogOpen(false);
    setEditing(null);
    setErrorGeneral('');
  }

  const columns: Column<Record<string, unknown>>[] = [
    ...def.columns,
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (row) => (
        <Stack direction="row" spacing={1} justifyContent="flex-end">
          <Button size="small" startIcon={<EditOutlined />} onClick={() => abrirEditar(row)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            startIcon={<DeleteOutline />}
            disabled={removeMutation.isPending}
            onClick={() => removeMutation.mutate(row.id as number | string)}
          >
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <>
      <Stack direction="row" justifyContent="flex-end" sx={{ mb: 2 }}>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nuevo
        </Button>
      </Stack>
      <DataTable
        columns={columns}
        rows={rows}
        getRowKey={(r) => String(r.id)}
        loading={isLoading}
        emptyMessage="No hay registros configurados."
      />

      <Dialog
        open={dialogOpen}
        onClose={() => !mutation.isPending && cerrar()}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle>{editing ? 'Editar registro' : 'Nuevo registro'}</DialogTitle>
        <form onSubmit={handleSubmit((values) => mutation.mutate(values))} noValidate>
          <DialogContent>
            {errorGeneral && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {errorGeneral}
              </Alert>
            )}
            <Stack spacing={2}>
              {def.fields.map((field) => {
                const fieldError = errors[field.name]?.message as string | undefined;
                if (field.type === 'switch') {
                  return (
                    <Controller
                      key={field.name}
                      name={field.name}
                      control={control}
                      render={({ field: f }) => (
                        <FormControlLabel
                          control={
                            <Switch checked={Boolean(f.value)} onChange={(e) => f.onChange(e.target.checked)} />
                          }
                          label={field.label}
                        />
                      )}
                    />
                  );
                }
                if (field.type === 'select') {
                  return (
                    <TextField
                      key={field.name}
                      select
                      label={field.label}
                      fullWidth
                      error={!!fieldError}
                      helperText={fieldError}
                      defaultValue={(def.defaults[field.name] as string) ?? ''}
                      {...register(field.name)}
                    >
                      {(field.options ?? []).map((opt) => (
                        <MenuItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </MenuItem>
                      ))}
                    </TextField>
                  );
                }
                return (
                  <TextField
                    key={field.name}
                    label={field.label}
                    fullWidth
                    type={field.type === 'date' ? 'date' : 'text'}
                    inputMode={field.type === 'number' || field.type === 'percent' ? 'decimal' : undefined}
                    InputLabelProps={field.type === 'date' ? { shrink: true } : undefined}
                    error={!!fieldError}
                    helperText={fieldError}
                    {...register(field.name)}
                  />
                );
              })}
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={cerrar} disabled={mutation.isPending}>
              Cancelar
            </Button>
            <Button
              type="submit"
              variant="contained"
              disabled={mutation.isPending}
              startIcon={mutation.isPending ? <CircularProgress size={16} /> : undefined}
            >
              Guardar
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </>
  );
}

export default function ConfigMotorPage() {
  const tabs = useMemo(() => buildTabs(cxcLubrikcaService), []);
  const [active, setActive] = useState(0);
  // eslint-disable-next-line security/detect-object-injection -- `active` es un índice numérico del estado local (0..tabs.length-1), no input arbitrario
  const def = tabs[active];

  return (
    <PageContainer>
      <PageHeader
        title="Configuración del Motor"
        subtitle="Descuentos, promociones, recurrencia, feriados, métodos de pago y tolerancias"
      />
      <Tabs
        value={active}
        onChange={(_e, v) => setActive(v as number)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ mb: 3 }}
      >
        {tabs.map((t) => (
          <Tab key={t.key} label={t.label} />
        ))}
      </Tabs>
      <ConfigTab key={def.key} def={def} />
    </PageContainer>
  );
}
