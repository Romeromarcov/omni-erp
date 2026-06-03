import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, put } from '../../../services/api';
import { toList } from '../../../utils/api';
import { fetchMonedas } from '../../../services/monedas';
import type { Moneda } from '../../../services/monedas';
import { fetchEmpresas } from '../../../services/empresas';
import type { Empresa } from '../../../services/empresas';
import { PageContainer, PageHeader } from '../../../components/ui';
import {
  Alert,
  Box,
  Button,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

type TasaCambioDetail = {
  id_tasa_cambio: string;
  id_empresa: string;
  id_moneda_origen: string;
  id_moneda_destino: string;
  tipo_tasa: string;
  valor_tasa: string;
  fecha_tasa: string;
  hora_tasa?: string;
  id_usuario_registro__username?: string;
  empresa_nombre?: string;
};

const TasaCambioDetailPage: React.FC = () => {
  const { id_tasa_cambio } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tasa, setTasa] = useState<TasaCambioDetail | null>(null);
  const [edit, setEdit] = useState(false);
  const [error, setError] = useState('');

  const { data: tasaData, isLoading } = useQuery<TasaCambioDetail>({
    queryKey: [`/finanzas/tasas-cambio/${id_tasa_cambio}/`],
    queryFn: () => get(`/finanzas/tasas-cambio/${id_tasa_cambio}/`) as Promise<TasaCambioDetail>,
    enabled: !!id_tasa_cambio,
  });

  useEffect(() => {
    if (tasaData) setTasa(tasaData);
  }, [tasaData]);

  const { data: monedas = [] } = useQuery<Moneda[], Error, Moneda[]>({
    queryKey: ['/finanzas/monedas/'],
    queryFn: () => fetchMonedas(),
  });

  const { data: empresas = [] } = useQuery<unknown, Error, Empresa[]>({
    queryKey: ['/core/empresas/'],
    queryFn: () => fetchEmpresas(),
    select: toList,
  });

  const updateMutation = useMutation({
    mutationFn: (payload: TasaCambioDetail) => put(`/finanzas/tasas-cambio/${id_tasa_cambio}/`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [`/finanzas/tasas-cambio/${id_tasa_cambio}/`] });
      setEdit(false);
    },
    onError: () => setError('Error al actualizar tasa de cambio'),
  });

  const loading = isLoading || updateMutation.isPending;

  const handleUpdate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!tasa) return;
    setError('');
    updateMutation.mutate(tasa);
  };

  if (isLoading) {
    return (
      <PageContainer>
        <Typography align="center" color="text.secondary" sx={{ py: 4 }}>Cargando...</Typography>
      </PageContainer>
    );
  }
  if (!tasa) {
    return (
      <PageContainer>
        <Typography align="center" color="text.secondary" sx={{ py: 4 }}>No encontrada</Typography>
      </PageContainer>
    );
  }

  // Helpers para mostrar nombres/códigos
  const monedaOrigen = monedas.find(m => m.id_moneda === tasa.id_moneda_origen);
  const monedaDestino = monedas.find(m => m.id_moneda === tasa.id_moneda_destino);
  const empresa = empresas.find(e => e.id_empresa === tasa.id_empresa);

  return (
    <PageContainer>
      <PageHeader
        title="Detalle de Tasa de Cambio"
        actions={<Button variant="outlined" onClick={() => navigate(-1)}>Volver</Button>}
      />
      {!edit ? (
        <Stack spacing={1.5}>
          <Box><Typography component="span" fontWeight="bold">Empresa:</Typography> {empresa ? (empresa.nombre_comercial || empresa.nombre_legal) : (tasa.empresa_nombre || tasa.id_empresa)}</Box>
          <Box><Typography component="span" fontWeight="bold">Moneda Origen:</Typography> {monedaOrigen ? `${monedaOrigen.nombre} (${monedaOrigen.codigo_iso})` : tasa.id_moneda_origen}</Box>
          <Box><Typography component="span" fontWeight="bold">Moneda Destino:</Typography> {monedaDestino ? `${monedaDestino.nombre} (${monedaDestino.codigo_iso})` : tasa.id_moneda_destino}</Box>
          <Box><Typography component="span" fontWeight="bold">Tipo Tasa:</Typography> {tasa.tipo_tasa}</Box>
          <Box><Typography component="span" fontWeight="bold">Valor:</Typography> {tasa.valor_tasa}</Box>
          <Box><Typography component="span" fontWeight="bold">Fecha:</Typography> {tasa.fecha_tasa}</Box>
          <Box><Typography component="span" fontWeight="bold">Hora:</Typography> {tasa.hora_tasa || '-'}</Box>
          <Box><Typography component="span" fontWeight="bold">Usuario:</Typography> {tasa.id_usuario_registro__username || '-'}</Box>
          <Stack direction="row" justifyContent="flex-end">
            <Button variant="contained" onClick={() => setEdit(true)}>Editar</Button>
          </Stack>
        </Stack>
      ) : (
        <Box component="form" onSubmit={handleUpdate}>
          <Stack spacing={2}>
            <Box><Typography component="span" fontWeight="bold">Empresa:</Typography> {empresa ? (empresa.nombre_comercial || empresa.nombre_legal) : (tasa.empresa_nombre || tasa.id_empresa)}</Box>
            <TextField
              select
              label="Moneda Origen"
              value={tasa.id_moneda_origen}
              onChange={e => setTasa({ ...tasa, id_moneda_origen: e.target.value })}
              fullWidth
            >
              <MenuItem value="">Seleccione moneda</MenuItem>
              {monedas.map(m => (
                <MenuItem key={m.id_moneda} value={m.id_moneda}>{m.nombre} ({m.codigo_iso})</MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Moneda Destino"
              value={tasa.id_moneda_destino}
              onChange={e => setTasa({ ...tasa, id_moneda_destino: e.target.value })}
              fullWidth
            >
              <MenuItem value="">Seleccione moneda</MenuItem>
              {monedas.map(m => (
                <MenuItem key={m.id_moneda} value={m.id_moneda}>{m.nombre} ({m.codigo_iso})</MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Tipo Tasa"
              value={tasa.tipo_tasa}
              onChange={e => setTasa({ ...tasa, tipo_tasa: e.target.value })}
              fullWidth
            >
              <MenuItem value="">Seleccione tipo</MenuItem>
              <MenuItem value="OFICIAL_BCV">Oficial BCV</MenuItem>
              <MenuItem value="ESPECIAL_USUARIO">Especial Usuario</MenuItem>
              <MenuItem value="PROMEDIO_MERCADO">Promedio Mercado</MenuItem>
              <MenuItem value="FIJA">Fija</MenuItem>
            </TextField>
            <TextField
              label="Valor"
              value={tasa.valor_tasa}
              onChange={e => setTasa({ ...tasa, valor_tasa: e.target.value })}
              fullWidth
            />
            <TextField
              label="Fecha"
              type="date"
              value={tasa.fecha_tasa}
              onChange={e => setTasa({ ...tasa, fecha_tasa: e.target.value })}
              slotProps={{ inputLabel: { shrink: true } }}
              fullWidth
            />
            <TextField
              label="Hora"
              type="time"
              value={tasa.hora_tasa || ''}
              onChange={e => setTasa({ ...tasa, hora_tasa: e.target.value })}
              slotProps={{ inputLabel: { shrink: true } }}
              fullWidth
            />
            <Box><Typography component="span" fontWeight="bold">Usuario:</Typography> {tasa.id_usuario_registro__username || '-'}</Box>
            {error && <Alert severity="error">{error}</Alert>}
            <Stack direction="row" spacing={1} justifyContent="flex-end">
              <Button type="button" variant="outlined" onClick={() => setEdit(false)}>Cancelar</Button>
              <Button type="submit" variant="contained" disabled={loading}>{loading ? 'Actualizando...' : 'Actualizar'}</Button>
            </Stack>
          </Stack>
        </Box>
      )}
    </PageContainer>
  );
};

export default TasaCambioDetailPage;
