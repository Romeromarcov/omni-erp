import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, TextField, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { get } from '../../../services/api';
import { toList } from '../../../utils/api';
import type { CatalogoValor } from '../../../types/configuracion';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../../components/ui';
import type { Column } from '../../../components/ui';

type CatalogoValorApiResponse = CatalogoValor[] | { results: CatalogoValor[]; count: number };

export default function CatalogoValorListPage() {
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  const { data: catalogos = [], isLoading, isError } = useQuery<CatalogoValorApiResponse, Error, CatalogoValor[]>({
    queryKey: ['/configuracion_motor/catalogos-valor/'],
    queryFn: () => get<CatalogoValorApiResponse>('/configuracion_motor/catalogos-valor/'),
    select: toList,
  });

  const q = search.toLowerCase();
  const filtered = catalogos.filter(
    (c) => c.valor.toLowerCase().includes(q) || c.codigo_catalogo.toLowerCase().includes(q),
  );

  const grouped = filtered.reduce((acc, c) => {
    (acc[c.codigo_catalogo] ||= []).push(c);
    return acc;
  }, {} as Record<string, CatalogoValor[]>);

  const columns: Column<CatalogoValor>[] = [
    { key: 'valor', header: 'Valor', render: (c) => c.valor },
    { key: 'descripcion', header: 'Descripción', render: (c) => c.descripcion || '—' },
    { key: 'orden', header: 'Orden', align: 'center', render: (c) => c.orden },
    { key: 'activo', header: 'Activo', align: 'center', render: (c) => <StatusChip value={c.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (c) => (
        <Button size="small" variant="outlined" onClick={(e) => { e.stopPropagation(); navigate(`/configuracion/catalogos-valor/${c.id_catalogo_valor}`); }}>
          Ver / Editar
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Catálogos de Valor"
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('/configuracion/catalogos-valor/new')}>
            Nuevo valor
          </Button>
        }
      />
      <TextField
        size="small"
        placeholder="Buscar catálogo o valor…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 2, width: { xs: '100%', sm: 320 } }}
      />
      {isError ? (
        <Alert severity="error">Error al cargar catálogos.</Alert>
      ) : isLoading ? (
        <DataTable columns={columns} rows={[]} getRowKey={() => ''} loading emptyMessage="" />
      ) : Object.keys(grouped).length === 0 ? (
        <Alert severity="info">No se encontraron catálogos de valor.</Alert>
      ) : (
        Object.entries(grouped).map(([codigo, valores]) => (
          <Box key={codigo} sx={{ mb: 3 }}>
            <Typography variant="subtitle1" sx={{ mb: 1, color: 'primary.main' }}>
              Catálogo: {codigo}
            </Typography>
            <DataTable
              columns={columns}
              rows={valores}
              getRowKey={(c) => c.id_catalogo_valor}
              onRowClick={(c) => navigate(`/configuracion/catalogos-valor/${c.id_catalogo_valor}`)}
            />
          </Box>
        ))
      )}
    </PageContainer>
  );
}
