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
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import CloseOutlined from '@mui/icons-material/CloseOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  requisicionesService,
  detallesRequisicionService,
  solicitudesCotizacionService,
  detallesSolicitudService,
  ofertasProveedorService,
  detallesOfertaService,
  type RequisicionCompra,
  type RequisicionCompraPayload,
  type DetalleRequisicion,
  type DetalleRequisicionPayload,
  type SolicitudCotizacion,
  type SolicitudCotizacionPayload,
  type DetalleSolicitud,
  type DetalleSolicitudPayload,
  type OfertaProveedor,
  type OfertaProveedorPayload,
  type DetalleOferta,
  type DetalleOfertaPayload,
} from '../../services/aprovisionamientoService';
import { productoInventarioService, type Producto } from '../../services/inventarioService';
import { proveedoresService, type Proveedor } from '../../services/proveedoresService';
import { fetchDepartamentos } from '../../services/departamentos';
import { aprovisionamientoKeys } from '../../lib/queryKeys';
import { getEmpresaId } from '../../utils/empresa';
import { getSessionUsuarioId } from '../../services/session';
import { mensajeDeError } from '../../utils/api';

const PRIORIDAD_OPCIONES = ['BAJA', 'MEDIA', 'ALTA', 'URGENTE'];
const ESTADO_REQ_OPCIONES = ['BORRADOR', 'PENDIENTE', 'APROBADA', 'RECHAZADA', 'PROCESADA', 'ANULADA'];
const ESTADO_SOL_OPCIONES = ['BORRADOR', 'ENVIADA', 'RESPONDIDA', 'VENCIDA', 'ANULADA'];
const ESTADO_OFE_OPCIONES = ['RECIBIDA', 'EVALUADA', 'ACEPTADA', 'RECHAZADA', 'VENCIDA'];

const hoy = () => new Date().toISOString().slice(0, 10);

// Catálogo de productos compartido por los tres drawers.
function useProductos() {
  const empresaId = getEmpresaId() || '';
  return useQuery({
    queryKey: ['productos', empresaId],
    queryFn: () => productoInventarioService.getAll(empresaId ? { empresa: empresaId } : undefined),
  });
}

const nombreProducto = (productos: Producto[], id: string): string => {
  const p = productos.find((prod) => prod.id_producto === id);
  return p ? `${p.nombre_producto}${p.sku ? ` (${p.sku})` : ''}` : id;
};

const AprovisionamientoPage: React.FC = () => {
  const [tab, setTab] = useState(0);
  return (
    <PageContainer>
      <PageHeader
        title="Aprovisionamiento"
        subtitle="Source-to-PO: requisiciones, solicitudes de cotización (RFQ) y ofertas de proveedor previas a la orden de compra."
      />
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Requisiciones" />
        <Tab label="Solicitudes de Cotización" />
        <Tab label="Ofertas de Proveedor" />
      </Tabs>
      {tab === 0 && <RequisicionesTab />}
      {tab === 1 && <SolicitudesTab />}
      {tab === 2 && <OfertasTab />}
    </PageContainer>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Requisiciones
// ─────────────────────────────────────────────────────────────────────────────

interface RequisicionForm {
  numero_requisicion: string;
  fecha_requisicion: string;
  fecha_necesidad: string;
  prioridad: string;
  estado: string;
  justificacion: string;
  id_departamento: string;
  observaciones: string;
}

const REQ_VACIO: RequisicionForm = {
  numero_requisicion: '',
  fecha_requisicion: hoy(),
  fecha_necesidad: hoy(),
  prioridad: 'MEDIA',
  estado: 'BORRADOR',
  justificacion: '',
  id_departamento: '',
  observaciones: '',
};

const RequisicionesTab: React.FC = () => {
  const queryClient = useQueryClient();
  const [estado, setEstado] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<RequisicionCompra | null>(null);
  const [form, setForm] = useState<RequisicionForm>(REQ_VACIO);
  const [errorMsg, setErrorMsg] = useState('');
  const [detalle, setDetalle] = useState<RequisicionCompra | null>(null);

  const { data: requisiciones = [], isLoading } = useQuery({
    queryKey: aprovisionamientoKeys.requisiciones(estado || null),
    queryFn: () => requisicionesService.getAll({ estado: estado || undefined }),
  });

  const { data: departamentos = [] } = useQuery({
    queryKey: ['core', 'departamentos'],
    queryFn: fetchDepartamentos,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: aprovisionamientoKeys.requisicionesAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(REQ_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (r: RequisicionCompra) => {
    setEditando(r);
    setForm({
      numero_requisicion: r.numero_requisicion,
      fecha_requisicion: r.fecha_requisicion,
      fecha_necesidad: r.fecha_necesidad,
      prioridad: r.prioridad,
      estado: r.estado,
      justificacion: r.justificacion,
      id_departamento: r.id_departamento ?? '',
      observaciones: r.observaciones ?? '',
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: RequisicionCompraPayload) =>
      editando
        ? requisicionesService.update(editando.id_requisicion, payload)
        : requisicionesService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la requisición.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => requisicionesService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la requisición.')),
  });

  const handleGuardar = () => {
    if (!form.numero_requisicion.trim() || !form.justificacion.trim()) {
      setErrorMsg('Complete el número de requisición y la justificación.');
      return;
    }
    const payload: RequisicionCompraPayload = {
      id_solicitante: editando ? editando.id_solicitante : getSessionUsuarioId(),
      id_departamento: form.id_departamento || null,
      numero_requisicion: form.numero_requisicion.trim(),
      fecha_requisicion: form.fecha_requisicion,
      estado: form.estado,
      prioridad: form.prioridad,
      fecha_necesidad: form.fecha_necesidad,
      justificacion: form.justificacion.trim(),
      observaciones: form.observaciones.trim() || null,
    };
    guardar.mutate(payload);
  };

  const handleEliminar = (r: RequisicionCompra) => {
    if (window.confirm(`¿Eliminar la requisición "${r.numero_requisicion}"?`)) {
      eliminar.mutate(r.id_requisicion);
    }
  };

  const columns: Column<RequisicionCompra>[] = [
    { key: 'numero', header: 'Número', render: (r) => r.numero_requisicion },
    { key: 'fecha', header: 'Fecha', render: (r) => r.fecha_requisicion },
    { key: 'prioridad', header: 'Prioridad', render: (r) => r.prioridad },
    { key: 'estado', header: 'Estado', render: (r) => <StatusChip value={r.estado} label={r.estado} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (r) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalle(r)}>
            Líneas
          </Button>
          <Button size="small" onClick={() => abrirEditar(r)}>
            Editar
          </Button>
          <Button size="small" color="error" disabled={eliminar.isPending} onClick={() => handleEliminar(r)}>
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <TextField
          select
          label="Estado"
          value={estado}
          onChange={(e) => setEstado(e.target.value)}
          size="small"
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {ESTADO_REQ_OPCIONES.map((s) => (
            <MenuItem key={s} value={s}>
              {s}
            </MenuItem>
          ))}
        </TextField>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva requisición
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={requisiciones}
        getRowKey={(r) => r.id_requisicion}
        loading={isLoading}
        emptyMessage="Sin requisiciones. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar requisición' : 'Nueva requisición'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Número de requisición"
              value={form.numero_requisicion}
              onChange={(e) => setForm((f) => ({ ...f, numero_requisicion: e.target.value }))}
              required
              fullWidth
            />
            <Stack direction="row" spacing={1}>
              <TextField
                label="Fecha de requisición"
                type="date"
                value={form.fecha_requisicion}
                onChange={(e) => setForm((f) => ({ ...f, fecha_requisicion: e.target.value }))}
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <TextField
                label="Fecha de necesidad"
                type="date"
                value={form.fecha_necesidad}
                onChange={(e) => setForm((f) => ({ ...f, fecha_necesidad: e.target.value }))}
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
              />
            </Stack>
            <Stack direction="row" spacing={1}>
              <TextField
                select
                label="Prioridad"
                value={form.prioridad}
                onChange={(e) => setForm((f) => ({ ...f, prioridad: e.target.value }))}
                fullWidth
              >
                {PRIORIDAD_OPCIONES.map((p) => (
                  <MenuItem key={p} value={p}>
                    {p}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="Estado"
                value={form.estado}
                onChange={(e) => setForm((f) => ({ ...f, estado: e.target.value }))}
                fullWidth
              >
                {ESTADO_REQ_OPCIONES.map((s) => (
                  <MenuItem key={s} value={s}>
                    {s}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <TextField
              select
              label="Departamento"
              value={form.id_departamento}
              onChange={(e) => setForm((f) => ({ ...f, id_departamento: e.target.value }))}
              fullWidth
            >
              <MenuItem value="">Sin departamento</MenuItem>
              {departamentos.map((d) => (
                <MenuItem key={d.id_departamento} value={d.id_departamento}>
                  {d.nombre_departamento}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Justificación"
              value={form.justificacion}
              onChange={(e) => setForm((f) => ({ ...f, justificacion: e.target.value }))}
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
        {detalle && <DetalleRequisicionDrawer requisicion={detalle} onClose={() => setDetalle(null)} />}
      </Drawer>
    </Stack>
  );
};

interface DetalleReqForm {
  id_producto: string;
  cantidad_solicitada: string;
  precio_estimado: string;
  justificacion: string;
}

const DET_REQ_VACIO: DetalleReqForm = {
  id_producto: '',
  cantidad_solicitada: '1',
  precio_estimado: '',
  justificacion: '',
};

const DetalleRequisicionDrawer: React.FC<{ requisicion: RequisicionCompra; onClose: () => void }> = ({
  requisicion,
  onClose,
}) => {
  const queryClient = useQueryClient();
  const reqId = requisicion.id_requisicion;
  const [form, setForm] = useState<DetalleReqForm>(DET_REQ_VACIO);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: detalles = [] } = useQuery({
    queryKey: aprovisionamientoKeys.detallesRequisicion(reqId),
    queryFn: () => detallesRequisicionService.getAll({ requisicion: reqId }),
  });
  const { data: productos = [] } = useProductos();

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: aprovisionamientoKeys.detallesRequisicion(reqId) });

  const reset = () => {
    setForm(DET_REQ_VACIO);
    setEditId(null);
    setError('');
  };

  const guardar = useMutation({
    mutationFn: (payload: DetalleRequisicionPayload) =>
      editId
        ? detallesRequisicionService.update(editId, payload)
        : detallesRequisicionService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar la línea.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => detallesRequisicionService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar la línea.')),
  });

  const editar = (d: DetalleRequisicion) => {
    setEditId(d.id_detalle_requisicion);
    setForm({
      id_producto: d.id_producto,
      cantidad_solicitada: d.cantidad_solicitada,
      precio_estimado: d.precio_estimado ?? '',
      justificacion: d.justificacion ?? '',
    });
    setError('');
  };

  const handleGuardar = () => {
    if (!form.id_producto || !form.cantidad_solicitada.trim()) {
      setError('Seleccione un producto e indique la cantidad.');
      return;
    }
    guardar.mutate({
      id_requisicion: reqId,
      id_producto: form.id_producto,
      cantidad_solicitada: form.cantidad_solicitada.trim(),
      precio_estimado: form.precio_estimado.trim() || null,
      justificacion: form.justificacion.trim() || null,
      observaciones: null,
    });
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">{requisicion.numero_requisicion}</Typography>
        <IconButton onClick={onClose} aria-label="Cerrar detalle">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {requisicion.estado} · {requisicion.prioridad}
      </Typography>
      <Divider />
      <Typography variant="subtitle2">Líneas de la requisición</Typography>

      {error && (
        <Alert severity="error" onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      <Stack spacing={1}>
        {detalles.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin líneas cargadas.
          </Typography>
        ) : (
          detalles.map((d) => (
            <Stack key={d.id_detalle_requisicion} direction="row" alignItems="center" justifyContent="space-between">
              <Typography variant="body2">
                {nombreProducto(productos, d.id_producto)} · {d.cantidad_solicitada}
                {d.precio_estimado ? ` · est. ${d.precio_estimado}` : ''}
              </Typography>
              <Stack direction="row" spacing={0.5}>
                <Button size="small" onClick={() => editar(d)}>
                  Editar
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={eliminar.isPending}
                  onClick={() => eliminar.mutate(d.id_detalle_requisicion)}
                >
                  Eliminar
                </Button>
              </Stack>
            </Stack>
          ))
        )}
      </Stack>

      <Divider />

      <Stack spacing={1}>
        <TextField
          select
          label="Producto"
          value={form.id_producto}
          onChange={(e) => setForm((f) => ({ ...f, id_producto: e.target.value }))}
          size="small"
          fullWidth
        >
          {productos.map((p) => (
            <MenuItem key={p.id_producto} value={p.id_producto}>
              {p.nombre_producto}
              {p.sku ? ` (${p.sku})` : ''}
            </MenuItem>
          ))}
        </TextField>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Cantidad"
            value={form.cantidad_solicitada}
            onChange={(e) => setForm((f) => ({ ...f, cantidad_solicitada: e.target.value }))}
            inputMode="decimal"
            size="small"
            fullWidth
          />
          <TextField
            label="Precio estimado"
            value={form.precio_estimado}
            onChange={(e) => setForm((f) => ({ ...f, precio_estimado: e.target.value }))}
            inputMode="decimal"
            size="small"
            fullWidth
          />
        </Stack>
        <TextField
          label="Justificación"
          value={form.justificacion}
          onChange={(e) => setForm((f) => ({ ...f, justificacion: e.target.value }))}
          size="small"
          fullWidth
        />
        <Stack direction="row" spacing={1}>
          <Button variant="contained" size="small" onClick={handleGuardar} disabled={guardar.isPending}>
            {editId ? 'Actualizar línea' : 'Agregar línea'}
          </Button>
          {editId && (
            <Button size="small" onClick={reset}>
              Cancelar
            </Button>
          )}
        </Stack>
      </Stack>
    </Stack>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Solicitudes de Cotización (RFQ)
// ─────────────────────────────────────────────────────────────────────────────

interface SolicitudForm {
  numero_solicitud: string;
  fecha_solicitud: string;
  fecha_vencimiento: string;
  estado: string;
  observaciones: string;
}

const SOL_VACIO: SolicitudForm = {
  numero_solicitud: '',
  fecha_solicitud: hoy(),
  fecha_vencimiento: hoy(),
  estado: 'BORRADOR',
  observaciones: '',
};

const SolicitudesTab: React.FC = () => {
  const queryClient = useQueryClient();
  const [estado, setEstado] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<SolicitudCotizacion | null>(null);
  const [form, setForm] = useState<SolicitudForm>(SOL_VACIO);
  const [errorMsg, setErrorMsg] = useState('');
  const [detalle, setDetalle] = useState<SolicitudCotizacion | null>(null);

  const { data: solicitudes = [], isLoading } = useQuery({
    queryKey: aprovisionamientoKeys.solicitudes(estado || null),
    queryFn: () => solicitudesCotizacionService.getAll({ estado: estado || undefined }),
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: aprovisionamientoKeys.solicitudesAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm(SOL_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (s: SolicitudCotizacion) => {
    setEditando(s);
    setForm({
      numero_solicitud: s.numero_solicitud,
      fecha_solicitud: s.fecha_solicitud,
      fecha_vencimiento: s.fecha_vencimiento,
      estado: s.estado,
      observaciones: s.observaciones ?? '',
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: SolicitudCotizacionPayload) =>
      editando
        ? solicitudesCotizacionService.update(editando.id_solicitud_cotizacion, payload)
        : solicitudesCotizacionService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la solicitud.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => solicitudesCotizacionService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la solicitud.')),
  });

  const handleGuardar = () => {
    if (!form.numero_solicitud.trim()) {
      setErrorMsg('Complete el número de solicitud.');
      return;
    }
    guardar.mutate({
      numero_solicitud: form.numero_solicitud.trim(),
      fecha_solicitud: form.fecha_solicitud,
      fecha_vencimiento: form.fecha_vencimiento,
      estado: form.estado,
      observaciones: form.observaciones.trim() || null,
    });
  };

  const handleEliminar = (s: SolicitudCotizacion) => {
    if (window.confirm(`¿Eliminar la solicitud "${s.numero_solicitud}"?`)) {
      eliminar.mutate(s.id_solicitud_cotizacion);
    }
  };

  const columns: Column<SolicitudCotizacion>[] = [
    { key: 'numero', header: 'Número', render: (s) => s.numero_solicitud },
    { key: 'fecha', header: 'Fecha', render: (s) => s.fecha_solicitud },
    { key: 'vence', header: 'Vence', render: (s) => s.fecha_vencimiento },
    { key: 'estado', header: 'Estado', render: (s) => <StatusChip value={s.estado} label={s.estado} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (s) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalle(s)}>
            Líneas
          </Button>
          <Button size="small" onClick={() => abrirEditar(s)}>
            Editar
          </Button>
          <Button size="small" color="error" disabled={eliminar.isPending} onClick={() => handleEliminar(s)}>
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <TextField
          select
          label="Estado"
          value={estado}
          onChange={(e) => setEstado(e.target.value)}
          size="small"
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {ESTADO_SOL_OPCIONES.map((s) => (
            <MenuItem key={s} value={s}>
              {s}
            </MenuItem>
          ))}
        </TextField>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva solicitud
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={solicitudes}
        getRowKey={(s) => s.id_solicitud_cotizacion}
        loading={isLoading}
        emptyMessage="Sin solicitudes de cotización. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar solicitud' : 'Nueva solicitud'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Número de solicitud"
              value={form.numero_solicitud}
              onChange={(e) => setForm((f) => ({ ...f, numero_solicitud: e.target.value }))}
              required
              fullWidth
            />
            <Stack direction="row" spacing={1}>
              <TextField
                label="Fecha de solicitud"
                type="date"
                value={form.fecha_solicitud}
                onChange={(e) => setForm((f) => ({ ...f, fecha_solicitud: e.target.value }))}
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <TextField
                label="Fecha de vencimiento"
                type="date"
                value={form.fecha_vencimiento}
                onChange={(e) => setForm((f) => ({ ...f, fecha_vencimiento: e.target.value }))}
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
              />
            </Stack>
            <TextField
              select
              label="Estado"
              value={form.estado}
              onChange={(e) => setForm((f) => ({ ...f, estado: e.target.value }))}
              fullWidth
            >
              {ESTADO_SOL_OPCIONES.map((s) => (
                <MenuItem key={s} value={s}>
                  {s}
                </MenuItem>
              ))}
            </TextField>
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
        {detalle && <DetalleSolicitudDrawer solicitud={detalle} onClose={() => setDetalle(null)} />}
      </Drawer>
    </Stack>
  );
};

interface DetalleSolForm {
  id_producto: string;
  cantidad: string;
  especificaciones: string;
}

const DET_SOL_VACIO: DetalleSolForm = { id_producto: '', cantidad: '1', especificaciones: '' };

const DetalleSolicitudDrawer: React.FC<{ solicitud: SolicitudCotizacion; onClose: () => void }> = ({
  solicitud,
  onClose,
}) => {
  const queryClient = useQueryClient();
  const solId = solicitud.id_solicitud_cotizacion;
  const [form, setForm] = useState<DetalleSolForm>(DET_SOL_VACIO);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: detalles = [] } = useQuery({
    queryKey: aprovisionamientoKeys.detallesSolicitud(solId),
    queryFn: () => detallesSolicitudService.getAll({ solicitud: solId }),
  });
  const { data: productos = [] } = useProductos();

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: aprovisionamientoKeys.detallesSolicitud(solId) });

  const reset = () => {
    setForm(DET_SOL_VACIO);
    setEditId(null);
    setError('');
  };

  const guardar = useMutation({
    mutationFn: (payload: DetalleSolicitudPayload) =>
      editId
        ? detallesSolicitudService.update(editId, payload)
        : detallesSolicitudService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar la línea.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => detallesSolicitudService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar la línea.')),
  });

  const editar = (d: DetalleSolicitud) => {
    setEditId(d.id_detalle_solicitud);
    setForm({
      id_producto: d.id_producto,
      cantidad: d.cantidad,
      especificaciones: d.especificaciones ?? '',
    });
    setError('');
  };

  const handleGuardar = () => {
    if (!form.id_producto || !form.cantidad.trim()) {
      setError('Seleccione un producto e indique la cantidad.');
      return;
    }
    guardar.mutate({
      id_solicitud_cotizacion: solId,
      id_producto: form.id_producto,
      cantidad: form.cantidad.trim(),
      especificaciones: form.especificaciones.trim() || null,
      observaciones: null,
    });
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">{solicitud.numero_solicitud}</Typography>
        <IconButton onClick={onClose} aria-label="Cerrar detalle">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {solicitud.estado}
      </Typography>
      <Divider />
      <Typography variant="subtitle2">Líneas de la solicitud</Typography>

      {error && (
        <Alert severity="error" onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      <Stack spacing={1}>
        {detalles.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin líneas cargadas.
          </Typography>
        ) : (
          detalles.map((d) => (
            <Stack key={d.id_detalle_solicitud} direction="row" alignItems="center" justifyContent="space-between">
              <Typography variant="body2">
                {nombreProducto(productos, d.id_producto)} · {d.cantidad}
              </Typography>
              <Stack direction="row" spacing={0.5}>
                <Button size="small" onClick={() => editar(d)}>
                  Editar
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={eliminar.isPending}
                  onClick={() => eliminar.mutate(d.id_detalle_solicitud)}
                >
                  Eliminar
                </Button>
              </Stack>
            </Stack>
          ))
        )}
      </Stack>

      <Divider />

      <Stack spacing={1}>
        <TextField
          select
          label="Producto"
          value={form.id_producto}
          onChange={(e) => setForm((f) => ({ ...f, id_producto: e.target.value }))}
          size="small"
          fullWidth
        >
          {productos.map((p) => (
            <MenuItem key={p.id_producto} value={p.id_producto}>
              {p.nombre_producto}
              {p.sku ? ` (${p.sku})` : ''}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          label="Cantidad"
          value={form.cantidad}
          onChange={(e) => setForm((f) => ({ ...f, cantidad: e.target.value }))}
          inputMode="decimal"
          size="small"
          fullWidth
        />
        <TextField
          label="Especificaciones"
          value={form.especificaciones}
          onChange={(e) => setForm((f) => ({ ...f, especificaciones: e.target.value }))}
          size="small"
          fullWidth
        />
        <Stack direction="row" spacing={1}>
          <Button variant="contained" size="small" onClick={handleGuardar} disabled={guardar.isPending}>
            {editId ? 'Actualizar línea' : 'Agregar línea'}
          </Button>
          {editId && (
            <Button size="small" onClick={reset}>
              Cancelar
            </Button>
          )}
        </Stack>
      </Stack>
    </Stack>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// Ofertas de Proveedor
// ─────────────────────────────────────────────────────────────────────────────

interface OfertaForm {
  id_solicitud_cotizacion: string;
  id_proveedor: string;
  numero_oferta: string;
  fecha_oferta: string;
  fecha_vencimiento: string;
  estado: string;
  monto_total: string;
  condiciones_pago: string;
  tiempo_entrega: string;
  observaciones: string;
}

const OFE_VACIO: OfertaForm = {
  id_solicitud_cotizacion: '',
  id_proveedor: '',
  numero_oferta: '',
  fecha_oferta: hoy(),
  fecha_vencimiento: hoy(),
  estado: 'RECIBIDA',
  monto_total: '0',
  condiciones_pago: '',
  tiempo_entrega: '',
  observaciones: '',
};

const OfertasTab: React.FC = () => {
  const queryClient = useQueryClient();
  const [solicitudFiltro, setSolicitudFiltro] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<OfertaProveedor | null>(null);
  const [form, setForm] = useState<OfertaForm>(OFE_VACIO);
  const [errorMsg, setErrorMsg] = useState('');
  const [detalle, setDetalle] = useState<OfertaProveedor | null>(null);

  const { data: ofertas = [], isLoading } = useQuery({
    queryKey: aprovisionamientoKeys.ofertas(solicitudFiltro || null, null),
    queryFn: () => ofertasProveedorService.getAll({ solicitud: solicitudFiltro || undefined }),
  });

  const { data: solicitudes = [] } = useQuery({
    queryKey: aprovisionamientoKeys.solicitudesAll(),
    queryFn: () => solicitudesCotizacionService.getAll(),
  });

  const { data: proveedores = [] } = useQuery({
    queryKey: ['compras', 'proveedores'],
    queryFn: () => proveedoresService.getAll(),
  });

  const numeroSolicitud = (id: string) =>
    solicitudes.find((s) => s.id_solicitud_cotizacion === id)?.numero_solicitud ?? id;
  const nombreProveedor = (id: string) =>
    proveedores.find((p: Proveedor) => p.id_proveedor === id)?.razon_social ?? id;

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: aprovisionamientoKeys.ofertasAll() });

  const abrirCrear = () => {
    setEditando(null);
    setForm({ ...OFE_VACIO, id_solicitud_cotizacion: solicitudFiltro });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (o: OfertaProveedor) => {
    setEditando(o);
    setForm({
      id_solicitud_cotizacion: o.id_solicitud_cotizacion,
      id_proveedor: o.id_proveedor,
      numero_oferta: o.numero_oferta,
      fecha_oferta: o.fecha_oferta,
      fecha_vencimiento: o.fecha_vencimiento,
      estado: o.estado,
      monto_total: o.monto_total,
      condiciones_pago: o.condiciones_pago ?? '',
      tiempo_entrega: o.tiempo_entrega ?? '',
      observaciones: o.observaciones ?? '',
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: OfertaProveedorPayload) =>
      editando
        ? ofertasProveedorService.update(editando.id_oferta, payload)
        : ofertasProveedorService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidate();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la oferta.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => ofertasProveedorService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la oferta.')),
  });

  const handleGuardar = () => {
    if (!form.numero_oferta.trim() || !form.id_solicitud_cotizacion || !form.id_proveedor) {
      setErrorMsg('Complete el número de oferta, la solicitud y el proveedor.');
      return;
    }
    guardar.mutate({
      id_solicitud_cotizacion: form.id_solicitud_cotizacion,
      id_proveedor: form.id_proveedor,
      numero_oferta: form.numero_oferta.trim(),
      fecha_oferta: form.fecha_oferta,
      fecha_vencimiento: form.fecha_vencimiento,
      estado: form.estado,
      monto_total: form.monto_total.trim() || '0',
      condiciones_pago: form.condiciones_pago.trim() || null,
      tiempo_entrega: form.tiempo_entrega.trim() || null,
      observaciones: form.observaciones.trim() || null,
    });
  };

  const handleEliminar = (o: OfertaProveedor) => {
    if (window.confirm(`¿Eliminar la oferta "${o.numero_oferta}"?`)) {
      eliminar.mutate(o.id_oferta);
    }
  };

  const columns: Column<OfertaProveedor>[] = [
    { key: 'numero', header: 'Número', render: (o) => o.numero_oferta },
    { key: 'proveedor', header: 'Proveedor', render: (o) => nombreProveedor(o.id_proveedor) },
    { key: 'solicitud', header: 'Solicitud', render: (o) => numeroSolicitud(o.id_solicitud_cotizacion) },
    { key: 'monto', header: 'Monto', render: (o) => o.monto_total },
    { key: 'estado', header: 'Estado', render: (o) => <StatusChip value={o.estado} label={o.estado} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (o) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDetalle(o)}>
            Líneas
          </Button>
          <Button size="small" onClick={() => abrirEditar(o)}>
            Editar
          </Button>
          <Button size="small" color="error" disabled={eliminar.isPending} onClick={() => handleEliminar(o)}>
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <TextField
          select
          label="Solicitud"
          value={solicitudFiltro}
          onChange={(e) => setSolicitudFiltro(e.target.value)}
          size="small"
          sx={{ minWidth: 240 }}
        >
          <MenuItem value="">Todas</MenuItem>
          {solicitudes.map((s) => (
            <MenuItem key={s.id_solicitud_cotizacion} value={s.id_solicitud_cotizacion}>
              {s.numero_solicitud}
            </MenuItem>
          ))}
        </TextField>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
          Nueva oferta
        </Button>
      </Stack>

      {errorMsg && (
        <Alert severity="error" onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <DataTable
        columns={columns}
        rows={ofertas}
        getRowKey={(o) => o.id_oferta}
        loading={isLoading}
        emptyMessage="Sin ofertas de proveedor. Crea la primera."
      />

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar oferta' : 'Nueva oferta'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Número de oferta"
              value={form.numero_oferta}
              onChange={(e) => setForm((f) => ({ ...f, numero_oferta: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              select
              label="Solicitud de cotización"
              value={form.id_solicitud_cotizacion}
              onChange={(e) => setForm((f) => ({ ...f, id_solicitud_cotizacion: e.target.value }))}
              required
              fullWidth
            >
              {solicitudes.map((s) => (
                <MenuItem key={s.id_solicitud_cotizacion} value={s.id_solicitud_cotizacion}>
                  {s.numero_solicitud}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Proveedor"
              value={form.id_proveedor}
              onChange={(e) => setForm((f) => ({ ...f, id_proveedor: e.target.value }))}
              required
              fullWidth
            >
              {proveedores.map((p: Proveedor) => (
                <MenuItem key={p.id_proveedor} value={p.id_proveedor}>
                  {p.razon_social}
                </MenuItem>
              ))}
            </TextField>
            <Stack direction="row" spacing={1}>
              <TextField
                label="Fecha de oferta"
                type="date"
                value={form.fecha_oferta}
                onChange={(e) => setForm((f) => ({ ...f, fecha_oferta: e.target.value }))}
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
              />
              <TextField
                label="Fecha de vencimiento"
                type="date"
                value={form.fecha_vencimiento}
                onChange={(e) => setForm((f) => ({ ...f, fecha_vencimiento: e.target.value }))}
                fullWidth
                slotProps={{ inputLabel: { shrink: true } }}
              />
            </Stack>
            <Stack direction="row" spacing={1}>
              <TextField
                select
                label="Estado"
                value={form.estado}
                onChange={(e) => setForm((f) => ({ ...f, estado: e.target.value }))}
                fullWidth
              >
                {ESTADO_OFE_OPCIONES.map((s) => (
                  <MenuItem key={s} value={s}>
                    {s}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Monto total"
                value={form.monto_total}
                onChange={(e) => setForm((f) => ({ ...f, monto_total: e.target.value }))}
                inputMode="decimal"
                fullWidth
              />
            </Stack>
            <TextField
              label="Condiciones de pago"
              value={form.condiciones_pago}
              onChange={(e) => setForm((f) => ({ ...f, condiciones_pago: e.target.value }))}
              fullWidth
            />
            <TextField
              label="Tiempo de entrega"
              value={form.tiempo_entrega}
              onChange={(e) => setForm((f) => ({ ...f, tiempo_entrega: e.target.value }))}
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
        {detalle && <DetalleOfertaDrawer oferta={detalle} onClose={() => setDetalle(null)} />}
      </Drawer>
    </Stack>
  );
};

interface DetalleOfeForm {
  id_producto: string;
  cantidad: string;
  precio_unitario: string;
  tiempo_entrega: string;
}

const DET_OFE_VACIO: DetalleOfeForm = {
  id_producto: '',
  cantidad: '1',
  precio_unitario: '0',
  tiempo_entrega: '',
};

const DetalleOfertaDrawer: React.FC<{ oferta: OfertaProveedor; onClose: () => void }> = ({
  oferta,
  onClose,
}) => {
  const queryClient = useQueryClient();
  const ofertaId = oferta.id_oferta;
  const [form, setForm] = useState<DetalleOfeForm>(DET_OFE_VACIO);
  const [editId, setEditId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: detalles = [] } = useQuery({
    queryKey: aprovisionamientoKeys.detallesOferta(ofertaId),
    queryFn: () => detallesOfertaService.getAll({ oferta: ofertaId }),
  });
  const { data: productos = [] } = useProductos();

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: aprovisionamientoKeys.detallesOferta(ofertaId) });

  const reset = () => {
    setForm(DET_OFE_VACIO);
    setEditId(null);
    setError('');
  };

  // Subtotal = cantidad × precio_unitario (montos como string, R-CODE-4).
  const calcularSubtotal = (cantidad: string, precio: string): string => {
    const c = Number(cantidad);
    const p = Number(precio);
    if (!Number.isFinite(c) || !Number.isFinite(p)) return '0';
    return (c * p).toFixed(4);
  };

  const guardar = useMutation({
    mutationFn: (payload: DetalleOfertaPayload) =>
      editId
        ? detallesOfertaService.update(editId, payload)
        : detallesOfertaService.create(payload),
    onSuccess: () => {
      reset();
      invalidate();
    },
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo guardar la línea.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => detallesOfertaService.remove(id),
    onSuccess: invalidate,
    onError: (e: unknown) => setError(mensajeDeError(e, 'No se pudo eliminar la línea.')),
  });

  const editar = (d: DetalleOferta) => {
    setEditId(d.id_detalle_oferta);
    setForm({
      id_producto: d.id_producto,
      cantidad: d.cantidad,
      precio_unitario: d.precio_unitario,
      tiempo_entrega: d.tiempo_entrega ?? '',
    });
    setError('');
  };

  const handleGuardar = () => {
    if (!form.id_producto || !form.cantidad.trim() || !form.precio_unitario.trim()) {
      setError('Seleccione un producto e indique cantidad y precio.');
      return;
    }
    guardar.mutate({
      id_oferta: ofertaId,
      id_producto: form.id_producto,
      cantidad: form.cantidad.trim(),
      precio_unitario: form.precio_unitario.trim(),
      subtotal: calcularSubtotal(form.cantidad, form.precio_unitario),
      tiempo_entrega: form.tiempo_entrega.trim() || null,
      observaciones: null,
    });
  };

  return (
    <Stack spacing={2}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="h6">{oferta.numero_oferta}</Typography>
        <IconButton onClick={onClose} aria-label="Cerrar detalle">
          <CloseOutlined />
        </IconButton>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        {oferta.estado} · {oferta.monto_total}
      </Typography>
      <Divider />
      <Typography variant="subtitle2">Líneas de la oferta</Typography>

      {error && (
        <Alert severity="error" onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      <Stack spacing={1}>
        {detalles.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin líneas cargadas.
          </Typography>
        ) : (
          detalles.map((d) => (
            <Stack key={d.id_detalle_oferta} direction="row" alignItems="center" justifyContent="space-between">
              <Typography variant="body2">
                {nombreProducto(productos, d.id_producto)} · {d.cantidad} × {d.precio_unitario} = {d.subtotal}
              </Typography>
              <Stack direction="row" spacing={0.5}>
                <Button size="small" onClick={() => editar(d)}>
                  Editar
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={eliminar.isPending}
                  onClick={() => eliminar.mutate(d.id_detalle_oferta)}
                >
                  Eliminar
                </Button>
              </Stack>
            </Stack>
          ))
        )}
      </Stack>

      <Divider />

      <Stack spacing={1}>
        <TextField
          select
          label="Producto"
          value={form.id_producto}
          onChange={(e) => setForm((f) => ({ ...f, id_producto: e.target.value }))}
          size="small"
          fullWidth
        >
          {productos.map((p) => (
            <MenuItem key={p.id_producto} value={p.id_producto}>
              {p.nombre_producto}
              {p.sku ? ` (${p.sku})` : ''}
            </MenuItem>
          ))}
        </TextField>
        <Stack direction="row" spacing={1}>
          <TextField
            label="Cantidad"
            value={form.cantidad}
            onChange={(e) => setForm((f) => ({ ...f, cantidad: e.target.value }))}
            inputMode="decimal"
            size="small"
            fullWidth
          />
          <TextField
            label="Precio unitario"
            value={form.precio_unitario}
            onChange={(e) => setForm((f) => ({ ...f, precio_unitario: e.target.value }))}
            inputMode="decimal"
            size="small"
            fullWidth
          />
        </Stack>
        <TextField
          label="Tiempo de entrega"
          value={form.tiempo_entrega}
          onChange={(e) => setForm((f) => ({ ...f, tiempo_entrega: e.target.value }))}
          size="small"
          fullWidth
        />
        <Stack direction="row" spacing={1}>
          <Button variant="contained" size="small" onClick={handleGuardar} disabled={guardar.isPending}>
            {editId ? 'Actualizar línea' : 'Agregar línea'}
          </Button>
          {editId && (
            <Button size="small" onClick={reset}>
              Cancelar
            </Button>
          )}
        </Stack>
      </Stack>
    </Stack>
  );
};

export default AprovisionamientoPage;
