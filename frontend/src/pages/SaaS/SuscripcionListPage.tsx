import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Alert, Box, Button, MenuItem, TextField } from '@mui/material';
import { PageContainer, PageHeader, DataTable, StatusChip, type Column } from '../../components/ui';
import {
  fetchSuscripciones, activarSuscripcion, suspenderSuscripcion, cancelarSuscripcion,
  SUSCRIPCION_ESTADOS,
  type Suscripcion, type SuscripcionEstado,
} from '../../services/saasService';
import { fetchEmpresas } from '../../services/empresas';

const SuscripcionListPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [estado, setEstado] = useState<SuscripcionEstado | ''>('');
  const [error, setError] = useState('');

  const { data: suscripciones = [], isLoading } = useQuery<Suscripcion[], Error>({
    queryKey: ['saas/suscripciones', estado || 'todas'],
    queryFn: () => fetchSuscripciones(estado ? { estado } : {}),
  });

  const { data: empresas = [] } = useQuery({
    queryKey: ['empresas', 'visible'],
    queryFn: fetchEmpresas,
  });

  const empresaNombre = useMemo(() => {
    const map = new Map<string, string>();
    for (const e of empresas) {
      map.set(e.id_empresa, e.nombre_comercial || e.nombre_legal);
    }
    return map;
  }, [empresas]);

  const onMutationError = (e: Error) => setError(e.message || 'No se pudo actualizar la suscripción.');
  const onMutationSuccess = () => {
    setError('');
    queryClient.invalidateQueries({ queryKey: ['saas/suscripciones'] });
  };

  const activar = useMutation({ mutationFn: activarSuscripcion, onSuccess: onMutationSuccess, onError: onMutationError });
  const suspender = useMutation({ mutationFn: suspenderSuscripcion, onSuccess: onMutationSuccess, onError: onMutationError });
  const cancelar = useMutation({
    mutationFn: (id: string) => cancelarSuscripcion(id),
    onSuccess: onMutationSuccess,
    onError: onMutationError,
  });

  const busy = activar.isPending || suspender.isPending || cancelar.isPending;

  const columns: Column<Suscripcion>[] = [
    {
      key: 'empresa',
      header: 'Tenant',
      render: (s) => empresaNombre.get(s.id_empresa) ?? s.id_empresa,
    },
    { key: 'plan', header: 'Plan', render: (s) => s.plan_nombre },
    { key: 'estado', header: 'Estado', render: (s) => <StatusChip value={s.estado.toLowerCase()} label={s.estado} /> },
    { key: 'periodo', header: 'Periodo', render: (s) => s.periodo },
    { key: 'fecha_fin', header: 'Vence', render: (s) => s.fecha_fin },
    { key: 'dias', header: 'Días rest.', align: 'right', render: (s) => s.dias_restantes },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (s) => {
        const puedeActivar = s.estado === 'SUSPENDIDA' || s.estado === 'VENCIDA';
        const puedeSuspender = s.estado === 'ACTIVA' || s.estado === 'TRIAL';
        const puedeCancelar = s.estado !== 'CANCELADA';
        return (
          <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
            {puedeActivar && (
              <Button size="small" color="success" disabled={busy} onClick={() => activar.mutate(s.id_suscripcion)}>
                Activar
              </Button>
            )}
            {puedeSuspender && (
              <Button size="small" color="warning" disabled={busy} onClick={() => suspender.mutate(s.id_suscripcion)}>
                Suspender
              </Button>
            )}
            {puedeCancelar && (
              <Button
                size="small"
                color="error"
                disabled={busy}
                onClick={() => {
                  if (window.confirm('¿Cancelar definitivamente esta suscripción?')) {
                    cancelar.mutate(s.id_suscripcion);
                  }
                }}
              >
                Cancelar
              </Button>
            )}
          </Box>
        );
      },
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Suscripciones"
        subtitle="Suscripciones de todos los tenants. Activar, suspender o cancelar."
        actions={
          <Button variant="contained" onClick={() => navigate('/admin-saas/suscripciones/new')}>
            + Nueva suscripción
          </Button>
        }
      />

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Box sx={{ mb: 2, maxWidth: 240 }}>
        <TextField
          select
          size="small"
          label="Filtrar por estado"
          value={estado}
          onChange={(e) => setEstado(e.target.value as SuscripcionEstado | '')}
          fullWidth
        >
          <MenuItem value="">Todos</MenuItem>
          {SUSCRIPCION_ESTADOS.map((es) => (
            <MenuItem key={es} value={es}>{es}</MenuItem>
          ))}
        </TextField>
      </Box>

      <DataTable
        columns={columns}
        rows={suscripciones}
        getRowKey={(s) => s.id_suscripcion}
        loading={isLoading}
        emptyMessage="No hay suscripciones."
      />
    </PageContainer>
  );
};

export default SuscripcionListPage;
