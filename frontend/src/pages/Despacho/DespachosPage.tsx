import React, { useState } from 'react';
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
  Link,
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
  despachoService,
  detalleDespachoService,
  puedeTransicionar,
  type Despacho,
  type EstadoDespacho,
  type DetalleDespacho,
} from '../../services/despachoService';
import { notaVentaService } from '../../services/ventas';
import type { NotaVenta } from '../../types/ventas';
import { almacenesService } from '../../services/almacenesService';
import { despachoKeys, notasVentaKeys, almacenesKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const ESTADOS: { value: EstadoDespacho | ''; label: string }[] = [
  { value: '', label: 'Todos' },
  { value: 'PENDIENTE', label: 'Pendiente' },
  { value: 'EN_RUTA', label: 'En ruta' },
  { value: 'ENTREGADO', label: 'Entregado' },
  { value: 'DEVUELTO', label: 'Devuelto' },
  { value: 'CANCELADO', label: 'Cancelado' },
];

const ESTADO_LABEL: Record<EstadoDespacho, string> = {
  PENDIENTE: 'Pendiente',
  EN_RUTA: 'En ruta',
  ENTREGADO: 'Entregado',
  DEVUELTO: 'Devuelto',
  CANCELADO: 'Cancelado',
};

const ESTADO_COLOR: Record<string, 'warning' | 'success' | 'error' | 'info' | 'default'> = {
  pendiente: 'warning',
  en_ruta: 'info',
  entregado: 'success',
  devuelto: 'error',
  cancelado: 'default',
};

// Notas de venta elegibles para despachar (espejo de ESTADOS_NOTA_DESPACHABLES).
const ESTADOS_NOTA_DESPACHABLES = ['ENTREGADA', 'FACTURADA'];

interface CrearForm {
  id_nota_venta: string;
  almacen_id: string;
  direccion_entrega: string;
  observaciones: string;
}

const crearVacio = (): CrearForm => ({
  id_nota_venta: '',
  almacen_id: '',
  direccion_entrega: '',
  observaciones: '',
});

const DespachosPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [filtroEstado, setFiltroEstado] = useState<EstadoDespacho | ''>('');
  const [crearOpen, setCrearOpen] = useState(false);
  const [form, setForm] = useState<CrearForm>(crearVacio());
  const [errorMsg, setErrorMsg] = useState('');
  const [detalle, setDetalle] = useState<Despacho | null>(null);

  const { data: despachos = [], isLoading } = useQuery({
    queryKey: despachoKeys.despachos(empresaId, filtroEstado),
    queryFn: () =>
      despachoService.getAll({
        empresa: empresaId || undefined,
        estado: filtroEstado || undefined,
      }),
  });

  // Notas de venta para el selector de "Crear desde nota de venta": solo las
  // ENTREGADAS/FACTURADAS pueden originar un despacho.
  const { data: notasVenta = [] } = useQuery({
    queryKey: notasVentaKeys.all(),
    queryFn: () => notaVentaService.getAll(),
  });
  const notasElegibles = (notasVenta as NotaVenta[]).filter((n) =>
    ESTADOS_NOTA_DESPACHABLES.includes(n.estado),
  );

  const { data: almacenes = [] } = useQuery({
    queryKey: almacenesKeys.all(),
    queryFn: () => almacenesService.getAll(),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: despachoKeys.despachosAll() });

  const abrirCrear = () => {
    setForm(crearVacio());
    setErrorMsg('');
    setCrearOpen(true);
  };

  const crear = useMutation({
    mutationFn: (f: CrearForm) =>
      despachoService.desdeNotaVenta({
        id_nota_venta: f.id_nota_venta,
        almacen_id: f.almacen_id,
        direccion_entrega: f.direccion_entrega.trim(),
        observaciones: f.observaciones.trim() || undefined,
      }),
    onSuccess: () => {
      setCrearOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo crear el despacho.')),
  });

  const iniciarRuta = useMutation({
    mutationFn: (id: string) => despachoService.iniciarRuta(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo iniciar la ruta.')),
  });

  const entregar = useMutation({
    mutationFn: ({ id, receptor }: { id: string; receptor: string }) =>
      despachoService.entregar(id, { receptor }),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo registrar la entrega.')),
  });

  const devolver = useMutation({
    mutationFn: ({ id, motivo }: { id: string; motivo: string }) =>
      despachoService.devolver(id, motivo),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo registrar la devolución.')),
  });

  const cancelar = useMutation({
    mutationFn: ({ id, motivo }: { id: string; motivo: string }) =>
      despachoService.cancelar(id, motivo),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo cancelar el despacho.')),
  });

  const handleCrear = () => {
    if (!form.id_nota_venta || !form.almacen_id || !form.direccion_entrega.trim()) {
      setErrorMsg('Seleccione la nota de venta, el almacén de origen y la dirección de entrega.');
      return;
    }
    crear.mutate(form);
  };

  const handleIniciarRuta = (d: Despacho) => {
    if (window.confirm(`¿Iniciar la ruta del despacho ${d.numero_despacho}?`)) {
      iniciarRuta.mutate(d.id_despacho);
    }
  };

  const handleEntregar = (d: Despacho) => {
    const receptor = window.prompt('Nombre de quien recibe la mercancía:');
    if (receptor && receptor.trim()) {
      entregar.mutate({ id: d.id_despacho, receptor: receptor.trim() });
    }
  };

  const handleDevolver = (d: Despacho) => {
    const motivo = window.prompt('Motivo de la devolución:');
    if (motivo && motivo.trim()) {
      devolver.mutate({ id: d.id_despacho, motivo: motivo.trim() });
    }
  };

  const handleCancelar = (d: Despacho) => {
    const motivo = window.prompt('Motivo de la cancelación:');
    if (motivo && motivo.trim()) {
      cancelar.mutate({ id: d.id_despacho, motivo: motivo.trim() });
    }
  };

  const transicionando =
    iniciarRuta.isPending || entregar.isPending || devolver.isPending || cancelar.isPending;

  const columns: Column<Despacho>[] = [
    { key: 'numero_despacho', header: 'Número', render: (d) => d.numero_despacho },
    {
      key: 'numero_nota_venta',
      header: 'Nota de venta',
      render: (d) => d.numero_nota_venta ?? '—',
    },
    { key: 'fecha_despacho', header: 'Fecha', render: (d) => d.fecha_despacho?.slice(0, 10) },
    { key: 'direccion_destino', header: 'Destino', render: (d) => d.direccion_destino },
    {
      key: 'estado_despacho',
      header: 'Estado',
      render: (d) => (
        <StatusChip
          value={d.estado_despacho}
          label={ESTADO_LABEL[d.estado_despacho] ?? d.estado_despacho}
          colorMap={ESTADO_COLOR}
        />
      ),
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (d) => {
        const estado = d.estado_despacho;
        return (
          <Stack direction="row" spacing={1}>
            <Button size="small" onClick={() => setDetalle(d)}>
              Detalle
            </Button>
            <Button
              size="small"
              color="info"
              disabled={!puedeTransicionar(estado, 'EN_RUTA') || transicionando}
              onClick={() => handleIniciarRuta(d)}
            >
              Iniciar ruta
            </Button>
            <Button
              size="small"
              color="success"
              disabled={!puedeTransicionar(estado, 'ENTREGADO') || transicionando}
              onClick={() => handleEntregar(d)}
            >
              Entregar
            </Button>
            <Button
              size="small"
              color="warning"
              disabled={!puedeTransicionar(estado, 'DEVUELTO') || transicionando}
              onClick={() => handleDevolver(d)}
            >
              Devolver
            </Button>
            <Button
              size="small"
              color="error"
              disabled={!puedeTransicionar(estado, 'CANCELADO') || transicionando}
              onClick={() => handleCancelar(d)}
            >
              Cancelar
            </Button>
          </Stack>
        );
      },
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Despachos"
        subtitle="Logística de salida: entrega de ventas con máquina de estados (pendiente → en ruta → entregado)."
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
            Crear desde nota de venta
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
        label="Estado"
        value={filtroEstado}
        onChange={(e) => setFiltroEstado(e.target.value as EstadoDespacho | '')}
        size="small"
        sx={{ mb: 2, minWidth: 260 }}
      >
        {ESTADOS.map((e) => (
          <MenuItem key={e.value || 'todos'} value={e.value}>
            {e.label}
          </MenuItem>
        ))}
      </TextField>

      <DataTable
        columns={columns}
        rows={despachos}
        getRowKey={(d) => d.id_despacho}
        loading={isLoading}
        emptyMessage="Sin despachos. Crea el primero desde una nota de venta entregada."
      />

      <Dialog open={crearOpen} onClose={() => setCrearOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Crear despacho desde nota de venta</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Nota de venta"
              value={form.id_nota_venta}
              onChange={(e) => setForm((f) => ({ ...f, id_nota_venta: e.target.value }))}
              required
              fullWidth
              helperText="Solo notas ENTREGADAS o FACTURADAS pueden originar un despacho."
            >
              {notasElegibles.length === 0 ? (
                <MenuItem value="" disabled>
                  No hay notas de venta elegibles
                </MenuItem>
              ) : (
                notasElegibles.map((n) => (
                  <MenuItem key={n.id_nota_venta} value={n.id_nota_venta}>
                    {n.numero_nota_venta ?? n.numero_nota ?? n.id_nota_venta} — {n.estado}
                  </MenuItem>
                ))
              )}
            </TextField>
            <TextField
              select
              label="Almacén de origen"
              value={form.almacen_id}
              onChange={(e) => setForm((f) => ({ ...f, almacen_id: e.target.value }))}
              required
              fullWidth
            >
              {almacenes.map((a) => (
                <MenuItem key={a.id_almacen} value={a.id_almacen}>
                  {a.nombre_almacen}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Dirección de entrega"
              value={form.direccion_entrega}
              onChange={(e) => setForm((f) => ({ ...f, direccion_entrega: e.target.value }))}
              required
              multiline
              minRows={2}
              fullWidth
            />
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
          <Button onClick={() => setCrearOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleCrear} disabled={crear.isPending}>
            Crear despacho
          </Button>
        </DialogActions>
      </Dialog>

      <Drawer
        anchor="right"
        open={Boolean(detalle)}
        onClose={() => setDetalle(null)}
        slotProps={{ paper: { sx: { width: { xs: '100%', sm: 560 }, p: 3 } } }}
      >
        {detalle && <DetalleDespachoDrawer despacho={detalle} onClose={() => setDetalle(null)} />}
      </Drawer>
    </PageContainer>
  );
};

// ── Detalle del despacho (encabezado + líneas read-only + PDF) ────────────────

interface DetalleDespachoDrawerProps {
  despacho: Despacho;
  onClose: () => void;
}

const DetalleDespachoDrawer: React.FC<DetalleDespachoDrawerProps> = ({ despacho, onClose }) => {
  const { data: lineas = [] } = useQuery({
    queryKey: despachoKeys.detalles(despacho.id_despacho),
    queryFn: () => detalleDespachoService.getAll({ despacho: despacho.id_despacho }),
  });

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">Despacho {despacho.numero_despacho}</Typography>
        <IconButton onClick={onClose} aria-label="Cerrar detalle">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {despacho.numero_nota_venta ? `Nota de venta ${despacho.numero_nota_venta} · ` : ''}
        {ESTADO_LABEL[despacho.estado_despacho] ?? despacho.estado_despacho}
      </Typography>
      <Typography variant="body2">{despacho.direccion_destino}</Typography>

      <Link
        href={despachoService.pdfUrl(despacho.id_despacho)}
        target="_blank"
        rel="noopener noreferrer"
      >
        Ver nota de entrega (PDF)
      </Link>

      <Divider />

      <Typography variant="subtitle2">Líneas del despacho</Typography>
      {lineas.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          Sin líneas registradas.
        </Typography>
      ) : (
        <Stack spacing={1}>
          {lineas.map((l: DetalleDespacho) => (
            <Typography key={l.id_detalle_despacho} variant="body2">
              {l.nombre_producto ?? l.id_producto} · {l.cantidad_despachada}
              {l.unidad_medida ? ` ${l.unidad_medida}` : ''}
              {l.lote ? ` · Lote ${l.lote}` : ''}
            </Typography>
          ))}
        </Stack>
      )}
    </Stack>
  );
};

export default DespachosPage;
