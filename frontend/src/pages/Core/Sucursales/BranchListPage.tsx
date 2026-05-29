import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Button, TextField } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useApiQuery } from '../../../hooks/useApiQuery';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../../components/ui';
import type { Column } from '../../../components/ui';

interface Sucursal {
  id_sucursal: string;
  nombre: string;
  direccion: string;
  telefono: string;
  activo: boolean;
}

type SucursalesApiResponse = Sucursal[] | { results: Sucursal[] };

export default function BranchListPage() {
  const { id_empresa } = useParams<{ id_empresa: string }>();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data: sucursales = [], isLoading } = useApiQuery<SucursalesApiResponse>(
    `/core/sucursales/?id_empresa=${id_empresa}`,
    {
      enabled: !!id_empresa,
      select: (raw): Sucursal[] => (Array.isArray(raw) ? raw : raw.results ?? []),
    },
  );

  const filtered = (sucursales as Sucursal[]).filter((s) =>
    s.nombre.toLowerCase().includes(search.toLowerCase()),
  );

  const columns: Column<Sucursal>[] = [
    { key: 'nombre', header: 'Nombre', render: (s) => s.nombre },
    { key: 'direccion', header: 'Dirección', render: (s) => s.direccion },
    { key: 'telefono', header: 'Teléfono', render: (s) => s.telefono },
    { key: 'activo', header: 'Activo', render: (s) => <StatusChip value={s.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (s) => (
        <Button size="small" variant="outlined" onClick={(e) => { e.stopPropagation(); navigate(`/sucursales/${s.id_sucursal}`); }}>
          Ver / Editar
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Sucursales"
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate(`/empresas/${id_empresa}/sucursales/new`)}>
            Nueva sucursal
          </Button>
        }
      />
      <TextField
        size="small"
        placeholder="Buscar sucursal…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 2, width: { xs: '100%', sm: 320 } }}
      />
      <DataTable
        columns={columns}
        rows={filtered}
        getRowKey={(s) => s.id_sucursal}
        loading={isLoading}
        emptyMessage="No se encontraron sucursales."
        onRowClick={(s) => navigate(`/sucursales/${s.id_sucursal}`)}
      />
    </PageContainer>
  );
}
