import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button, TextField } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useApiQuery } from '../../../hooks/useApiQuery';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../../components/ui';
import type { Column } from '../../../components/ui';

interface Departamento {
  id_departamento: string;
  nombre_departamento: string;
  descripcion?: string;
  activo: boolean;
}

type DepartamentosApiResponse = Departamento[] | { results: Departamento[] };

export default function DepartmentListPage() {
  const { id_empresa } = useParams<{ id_empresa: string }>();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data: departamentos = [], isLoading } = useApiQuery<DepartamentosApiResponse>(
    `/core/departamentos/?id_empresa=${id_empresa}`,
    {
      enabled: !!id_empresa,
      select: (raw): Departamento[] => (Array.isArray(raw) ? raw : raw.results ?? []),
    },
  );

  const filtered = (departamentos as Departamento[]).filter((d) =>
    d.nombre_departamento.toLowerCase().includes(search.toLowerCase()),
  );

  const columns: Column<Departamento>[] = [
    { key: 'nombre', header: 'Nombre', render: (d) => d.nombre_departamento },
    { key: 'descripcion', header: 'Descripción', render: (d) => d.descripcion || '—' },
    { key: 'activo', header: 'Activo', render: (d) => <StatusChip value={d.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (d) => (
        <Button size="small" variant="outlined" onClick={(e) => { e.stopPropagation(); navigate(`/departamentos/${d.id_departamento}`); }}>
          Ver / Editar
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Departamentos"
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate(`/empresas/${id_empresa}/departamentos/new`)}>
            Nuevo departamento
          </Button>
        }
      />
      <TextField
        size="small"
        placeholder="Buscar departamento…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 2, width: { xs: '100%', sm: 320 } }}
      />
      <DataTable
        columns={columns}
        rows={filtered}
        getRowKey={(d) => d.id_departamento}
        loading={isLoading}
        emptyMessage="No se encontraron departamentos."
        onRowClick={(d) => navigate(`/departamentos/${d.id_departamento}`)}
      />
    </PageContainer>
  );
}
