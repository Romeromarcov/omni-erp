import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
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
import { DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  ingestasService,
  ESTADOS_INGESTA,
  KINDS_COMPLETABLES,
  KINDS_INGESTA,
  type EstadoIngesta,
  type Ingesta,
  type KindIngesta,
} from '../../services/botsIngestService';
import { botsKeys } from '../../lib/queryKeys';
import { mensajeActivacion } from '../Activaciones/utils';
import { resumenIngesta, texto } from './utils';

const KIND_LABEL = new Map<string, string>([
  ['contacto', 'Contacto'],
  ['cotizacion', 'Cotización'],
  ['pedido', 'Pedido'],
  ['pago', 'Pago de cliente'],
  ['pago_proveedor', 'Pago a proveedor'],
  ['evento', 'Evento'],
]);

const ESTADO_LABEL = new Map<string, string>([
  ['PROCESADO', 'Procesado'],
  ['BORRADOR', 'Borrador (por confirmar en Odoo)'],
  ['INCOMPLETO', 'Incompleto'],
  ['SINCRONIZADO', 'Sincronizado'],
  ['ERROR', 'Error'],
]);

const ESTADO_COLOR: Record<string, 'success' | 'warning' | 'error' | 'info' | 'default'> = {
  procesado: 'success',
  borrador: 'info',
  incompleto: 'warning',
  sincronizado: 'success',
  error: 'error',
};

/** Campos del borrador de un pago que se pueden completar/corregir desde aquí. */
const CAMPOS_PAGO: { key: string; label: string; proveedor?: boolean; cliente?: boolean }[] = [
  { key: 'cliente', label: 'Cliente', cliente: true },
  { key: 'rif', label: 'RIF', cliente: true },
  { key: 'pedido_ref', label: 'Pedido que cancela', cliente: true },
  { key: 'proveedor', label: 'Proveedor', proveedor: true },
  { key: 'factura_ref', label: 'Factura', proveedor: true },
  { key: 'monto', label: 'Monto' },
  { key: 'moneda', label: 'Moneda (USD/VES)' },
  { key: 'metodo_pago', label: 'Método de pago' },
  { key: 'referencia', label: 'Referencia' },
  { key: 'banco', label: 'Banco' },
  { key: 'fecha_pago', label: 'Fecha (AAAA-MM-DD)' },
];

const esCompletable = (i: Ingesta): boolean =>
  (KINDS_COMPLETABLES as readonly string[]).includes(i.kind) &&
  (i.estado === 'INCOMPLETO' || i.estado === 'BORRADOR');

const IngestasTab: React.FC = () => {
  const [estado, setEstado] = useState<EstadoIngesta | ''>('');
  const [kind, setKind] = useState<KindIngesta | ''>('');
  const [detalle, setDetalle] = useState<Ingesta | null>(null);
  const [completando, setCompletando] = useState<Ingesta | null>(null);

  const { data: ingestas = [], isLoading } = useQuery({
    queryKey: botsKeys.ingestas(estado, kind),
    queryFn: () => ingestasService.getAll({ estado, kind }),
  });

  const columns: Column<Ingesta>[] = [
    {
      key: 'estado',
      header: 'Estado',
      render: (i) => <StatusChip value={i.estado} label={ESTADO_LABEL.get(i.estado) ?? i.estado} colorMap={ESTADO_COLOR} />,
    },
    { key: 'kind', header: 'Tipo', render: (i) => KIND_LABEL.get(i.kind) ?? i.kind },
    { key: 'resumen', header: 'Resumen', render: (i) => resumenIngesta(i) },
    {
      key: 'faltan',
      header: 'Falta',
      render: (i) =>
        i.incompleto.length ? (
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {i.incompleto.map((f) => (
              <Chip key={f} size="small" color="warning" variant="outlined" label={f} />
            ))}
          </Stack>
        ) : (
          '—'
        ),
    },
    {
      key: 'auto',
      header: 'Envío',
      render: (i) => <Chip size="small" variant="outlined" label={i.auto ? 'Automático' : 'Confirmado'} />,
    },
    { key: 'fecha', header: 'Fecha', render: (i) => new Date(i.fecha_creacion).toLocaleString('es-VE') },
    {
      key: 'acc',
      header: 'Acciones',
      render: (i) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalle(i)}>
            Ver
          </Button>
          {esCompletable(i) && (
            <Button size="small" variant="outlined" onClick={() => setCompletando(i)}>
              Completar
            </Button>
          )}
        </Stack>
      ),
    },
  ];

  return (
    <Box>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          size="small"
          label="Estado"
          value={estado}
          onChange={(e) => setEstado(e.target.value as EstadoIngesta | '')}
          sx={{ minWidth: 240 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {ESTADOS_INGESTA.map((s) => (
            <MenuItem key={s} value={s}>
              {ESTADO_LABEL.get(s) ?? s}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="Tipo"
          value={kind}
          onChange={(e) => setKind(e.target.value as KindIngesta | '')}
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {KINDS_INGESTA.map((k) => (
            <MenuItem key={k} value={k}>
              {KIND_LABEL.get(k) ?? k}
            </MenuItem>
          ))}
        </TextField>
        <Button onClick={() => setEstado('INCOMPLETO')}>Ver incompletas</Button>
      </Stack>

      <DataTable
        columns={columns}
        rows={ingestas}
        getRowKey={(i) => i.id_ingesta}
        loading={isLoading}
        emptyMessage="Sin ingestas con esos filtros."
      />

      {detalle && <DetalleDialog ingesta={detalle} onClose={() => setDetalle(null)} />}
      {completando && <CompletarDialog ingesta={completando} onClose={() => setCompletando(null)} />}
    </Box>
  );
};

// ── Detalle ─────────────────────────────────────────────────────────────────

const DetalleDialog: React.FC<{ ingesta: Ingesta; onClose: () => void }> = ({ ingesta, onClose }) => (
  <Dialog open onClose={onClose} fullWidth maxWidth="md">
    <DialogTitle>
      {KIND_LABEL.get(ingesta.kind) ?? ingesta.kind} · {ESTADO_LABEL.get(ingesta.estado) ?? ingesta.estado}
    </DialogTitle>
    <DialogContent>
      {ingesta.incompleto.length > 0 && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Falta: {ingesta.incompleto.join(', ')}
        </Alert>
      )}
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        Borrador enviado
      </Typography>
      <Box component="pre" sx={{ m: 0, mb: 2, p: 1.5, bgcolor: 'action.hover', borderRadius: 1, overflow: 'auto', fontSize: 13 }}>
        {JSON.stringify(ingesta.payload, null, 2)}
      </Box>
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        Resultado en Omni
      </Typography>
      <Box component="pre" sx={{ m: 0, p: 1.5, bgcolor: 'action.hover', borderRadius: 1, overflow: 'auto', fontSize: 13 }}>
        {JSON.stringify(ingesta.resultado, null, 2)}
      </Box>
      {ingesta.odoo_ref && (
        <Typography variant="body2" sx={{ mt: 1 }}>
          Referencia Odoo: {ingesta.odoo_ref}
        </Typography>
      )}
    </DialogContent>
    <DialogActions>
      <Button onClick={onClose}>Cerrar</Button>
    </DialogActions>
  </Dialog>
);

// ── Completar pago ──────────────────────────────────────────────────────────

const CompletarDialog: React.FC<{ ingesta: Ingesta; onClose: () => void }> = ({ ingesta, onClose }) => {
  const qc = useQueryClient();
  const esProveedor = ingesta.kind === 'pago_proveedor';
  const campos = CAMPOS_PAGO.filter((c) => (esProveedor ? !c.cliente : !c.proveedor));
  const [valores, setValores] = useState<Record<string, string>>(() =>
    Object.fromEntries(campos.map((c) => [c.key, texto(ingesta.payload[c.key])])),
  );
  const [errorMsg, setErrorMsg] = useState('');

  // Solo se envía lo que el usuario cambió y no quedó vacío (no se pisa lo confirmado).
  const cambios: Record<string, string> = {};
  for (const c of campos) {
    const nuevo = (valores[c.key] ?? '').trim();
    if (nuevo !== '' && nuevo !== texto(ingesta.payload[c.key])) cambios[c.key] = nuevo;
  }

  const completar = useMutation({
    mutationFn: () => ingestasService.completar(ingesta.id_ingesta, cambios),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: botsKeys.ingestasAll() });
      onClose();
    },
    onError: (e: unknown) => setErrorMsg(mensajeActivacion(e, 'No se pudo completar el pago.')),
  });

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Completar {KIND_LABEL.get(ingesta.kind)?.toLowerCase()}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {ingesta.incompleto.length > 0 && (
            <Alert severity="warning">Falta: {ingesta.incompleto.join(', ')}</Alert>
          )}
          {errorMsg && <Alert severity="error">{errorMsg}</Alert>}
          {campos.map((c) => (
            <TextField
              key={c.key}
              size="small"
              label={c.label}
              value={valores[c.key] ?? ''}
              onChange={(e) => setValores((v) => ({ ...v, [c.key]: e.target.value }))}
            />
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cerrar</Button>
        <Button
          variant="contained"
          disabled={Object.keys(cambios).length === 0 || completar.isPending}
          onClick={() => completar.mutate()}
        >
          Guardar cambios
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default IngestasTab;
