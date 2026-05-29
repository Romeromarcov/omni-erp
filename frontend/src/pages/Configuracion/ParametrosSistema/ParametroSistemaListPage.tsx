import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, TextField, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { get } from '../../../services/api';
import { toList } from '../../../utils/api';
import type { ParametroSistema } from '../../../types/configuracion';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../../components/ui';
import type { Column } from '../../../components/ui';

type ParametroSistemaApiResponse = ParametroSistema[] | { results: ParametroSistema[] };

export default function ParametroSistemaListPage() {
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  const { data: parametros = [], isLoading, isError } = useQuery<ParametroSistemaApiResponse, Error, ParametroSistema[]>({
    queryKey: ['/configuracion_motor/parametros-sistema/'],
    queryFn: () => get<ParametroSistemaApiResponse>('/configuracion_motor/parametros-sistema/'),
    select: toList,
  });

  const q = search.toLowerCase();
  const filtered = parametros.filter(
    (p) => p.nombre_parametro.toLowerCase().includes(q) || p.codigo_parametro.toLowerCase().includes(q),
  );

  const columns: Column<ParametroSistema>[] = [
    { key: 'codigo', header: 'Código', render: (p) => <Typography variant="body2" fontWeight={600}>{p.codigo_parametro}</Typography> },
    { key: 'nombre', header: 'Nombre', render: (p) => p.nombre_parametro },
    {
      key: 'valor',
      header: 'Valor',
      render: (p) => (
        <Typography variant="body2" sx={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {p.valor_parametro}
        </Typography>
      ),
    },
    { key: 'tipo', header: 'Tipo de Dato', render: (p) => p.tipo_dato },
    { key: 'ambito', header: 'Ámbito', render: (p) => (p.id_empresa ? 'Específica' : 'Global') },
    { key: 'activo', header: 'Activo', align: 'center', render: (p) => <StatusChip value={p.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (p) => (
        <Button size="small" variant="outlined" onClick={(e) => { e.stopPropagation(); navigate(`/configuracion/parametros-sistema/${p.id_parametro}`); }}>
          Ver / Editar
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Parámetros del Sistema"
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('/configuracion/parametros-sistema/new')}>
            Nuevo parámetro
          </Button>
        }
      />
      <TextField
        size="small"
        placeholder="Buscar parámetro…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 2, width: { xs: '100%', sm: 320 } }}
      />
      {isError ? (
        <Alert severity="error">Error al cargar parámetros.</Alert>
      ) : (
        <DataTable
          columns={columns}
          rows={filtered}
          getRowKey={(p) => p.id_parametro}
          loading={isLoading}
          emptyMessage="No se encontraron parámetros."
          onRowClick={(p) => navigate(`/configuracion/parametros-sistema/${p.id_parametro}`)}
        />
      )}
    </PageContainer>
  );
}
