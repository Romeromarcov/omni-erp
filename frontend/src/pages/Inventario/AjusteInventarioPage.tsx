import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  MenuItem,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import PageLayout from '../../components/PageLayout';
import {
  productoInventarioService,
  stockActualService,
  movimientoService,
} from '../../services/inventarioService';
import { inventarioKeys } from '../../lib/queryKeys';

type TipoAjuste = 'ENTRADA' | 'SALIDA';

interface FormState {
  id_producto: string;
  id_almacen: string;
  tipo_ajuste: TipoAjuste;
  cantidad: string;
  costo_unitario: string;
  observaciones: string;
  fecha_hora: string;
}

function nowISOLocal(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

const AjusteInventarioPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();

  const [form, setForm] = useState<FormState>({
    id_producto: searchParams.get('producto') ?? '',
    id_almacen: searchParams.get('almacen') ?? '',
    tipo_ajuste: 'ENTRADA',
    cantidad: '',
    costo_unitario: '',
    observaciones: '',
    fecha_hora: nowISOLocal(),
  });
  const [successMsg, setSuccessMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const { data: productos = [] } = useQuery({
    queryKey: inventarioKeys.productosInventario(),
    queryFn: () => productoInventarioService.getAll(),
  });

  const { data: stockList = [] } = useQuery({
    queryKey: inventarioKeys.stockActualAll(),
    queryFn: () => stockActualService.getAll(),
  });

  const almacenes = [
    ...new Map(
      stockList.map((s) => [s.id_almacen, s.almacen_nombre ?? s.id_almacen]),
    ).entries(),
  ];

  const stockActual = stockList.find(
    (s) => s.id_producto === form.id_producto && s.id_almacen === form.id_almacen,
  );

  const empresaId = stockList[0]?.id_empresa ?? '';

  const ajusteMutation = useMutation({
    mutationFn: () => {
      const cantidad = parseFloat(form.cantidad);
      if (isNaN(cantidad) || cantidad <= 0) throw new Error('La cantidad debe ser mayor a 0.');
      if (!form.id_producto) throw new Error('Seleccione un producto.');
      if (!form.id_almacen) throw new Error('Seleccione un almacén.');

      return movimientoService.registrarAjuste({
        id_empresa: empresaId,
        id_producto: form.id_producto,
        tipo_movimiento: 'AJUSTE',
        cantidad: form.tipo_ajuste === 'SALIDA' ? -cantidad : cantidad,
        fecha_hora_movimiento: new Date(form.fecha_hora).toISOString(),
        observaciones: form.observaciones || undefined,
        costo_unitario_movimiento: form.costo_unitario ? parseFloat(form.costo_unitario) : undefined,
        ...(form.tipo_ajuste === 'ENTRADA'
          ? { id_almacen_destino: form.id_almacen }
          : { id_almacen_origen: form.id_almacen }),
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: inventarioKeys.stockActualAll() });
      queryClient.invalidateQueries({ queryKey: inventarioKeys.kardexAll() });
      setSuccessMsg('Ajuste registrado correctamente.');
      setErrorMsg('');
      setForm((f) => ({
        ...f,
        cantidad: '',
        costo_unitario: '',
        observaciones: '',
        fecha_hora: nowISOLocal(),
      }));
    },
    onError: (err: Error) => {
      setErrorMsg(err.message);
      setSuccessMsg('');
    },
  });

  function handleChange(field: keyof FormState, value: string) {
    setForm((f) => ({ ...f, [field]: value }));
    setSuccessMsg('');
    setErrorMsg('');
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    ajusteMutation.mutate();
  }

  return (
    <PageLayout maxWidth={640}>
      <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/inventario/stock')} sx={{ mb: 1 }}>
        Volver al stock
      </Button>
      <Typography variant="h5" fontWeight={700}>Ajuste Manual de Inventario</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Registra una entrada o salida de ajuste con motivo documentado.
      </Typography>

      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={2.5}>
          {successMsg && <Alert severity="success">{successMsg}</Alert>}
          {errorMsg && <Alert severity="error">{errorMsg}</Alert>}

          <TextField select label="Producto" value={form.id_producto} onChange={(e) => handleChange('id_producto', e.target.value)} required fullWidth>
            <MenuItem value="">— Seleccionar producto —</MenuItem>
            {productos.map((p) => (
              <MenuItem key={p.id_producto} value={p.id_producto}>
                {p.nombre_producto} {p.sku ? `(${p.sku})` : ''}
              </MenuItem>
            ))}
          </TextField>

          <TextField select label="Almacén" value={form.id_almacen} onChange={(e) => handleChange('id_almacen', e.target.value)} required fullWidth>
            <MenuItem value="">— Seleccionar almacén —</MenuItem>
            {almacenes.map(([id, nombre]) => (
              <MenuItem key={id} value={id}>{nombre}</MenuItem>
            ))}
          </TextField>

          {stockActual && (
            <Alert severity="info" icon={false}>
              <strong>Stock actual:</strong>{' '}
              {parseFloat(stockActual.cantidad_disponible).toLocaleString()} unidades disponibles · Mínimo:{' '}
              {parseFloat(stockActual.cantidad_minima).toLocaleString()}
            </Alert>
          )}

          <Box>
            <Typography variant="body2" fontWeight={600} mb={1}>Tipo de ajuste *</Typography>
            <ToggleButtonGroup
              exclusive
              value={form.tipo_ajuste}
              onChange={(_, val) => val && handleChange('tipo_ajuste', val)}
              fullWidth
              color="primary"
            >
              <ToggleButton value="ENTRADA">📦 Entrada de inventario</ToggleButton>
              <ToggleButton value="SALIDA">📤 Salida de inventario</ToggleButton>
            </ToggleButtonGroup>
          </Box>

          <TextField type="number" label="Cantidad" value={form.cantidad} onChange={(e) => handleChange('cantidad', e.target.value)} required placeholder="Ej: 50" inputProps={{ min: '0.0001', step: 'any' }} fullWidth />

          <TextField type="number" label="Costo unitario (opcional)" value={form.costo_unitario} onChange={(e) => handleChange('costo_unitario', e.target.value)} placeholder="Ej: 12.50" inputProps={{ min: '0', step: 'any' }} fullWidth />

          <TextField type="datetime-local" label="Fecha y hora del movimiento" value={form.fecha_hora} onChange={(e) => handleChange('fecha_hora', e.target.value)} required fullWidth InputLabelProps={{ shrink: true }} />

          <TextField label="Motivo / Observaciones" value={form.observaciones} onChange={(e) => handleChange('observaciones', e.target.value)} placeholder="Describe el motivo del ajuste (conteo físico, merma, daño, etc.)" multiline minRows={3} fullWidth />

          <Stack direction="row" spacing={1}>
            <Button type="submit" variant="contained" disabled={ajusteMutation.isPending} sx={{ flex: 1 }}>
              {ajusteMutation.isPending ? 'Registrando…' : 'Registrar ajuste'}
            </Button>
            <Button type="button" variant="outlined" onClick={() => navigate('/inventario/stock')}>
              Cancelar
            </Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
};

export default AjusteInventarioPage;
