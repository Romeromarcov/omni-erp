import { useNavigate } from 'react-router-dom';
import { Alert, Button } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useApiQuery } from '../../../hooks/useApiQuery';
import { PageContainer, PageHeader, DataTable } from '../../../components/ui';
import type { Column } from '../../../components/ui';

interface Role {
  id_rol: string;
  nombre: string;
  descripcion?: string;
}

type RolesApiResponse = Role[] | { results: Role[] };

export default function RoleListPage() {
  const navigate = useNavigate();

  const { data: roles = [], isLoading, isError, error } = useApiQuery<RolesApiResponse>(
    '/core/roles/',
    { select: (raw): Role[] => (Array.isArray(raw) ? raw : raw.results ?? []) },
  );

  const columns: Column<Role>[] = [
    { key: 'nombre', header: 'Nombre', render: (r) => r.nombre },
    { key: 'descripcion', header: 'Descripción', render: (r) => r.descripcion || '—' },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (r) => (
        <Button size="small" variant="outlined" onClick={(e) => { e.stopPropagation(); navigate(`/roles/${r.id_rol}`); }}>
          Ver / Editar
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Roles"
        subtitle="Gestión de roles y sus permisos"
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('/roles/new')}>
            Nuevo rol
          </Button>
        }
      />
      {isError ? (
        <Alert severity="error">{error instanceof Error ? error.message : 'Error al cargar roles.'}</Alert>
      ) : (
        <DataTable
          columns={columns}
          rows={roles as Role[]}
          getRowKey={(r) => r.id_rol}
          loading={isLoading}
          emptyMessage="No se encontraron roles."
          onRowClick={(r) => navigate(`/roles/${r.id_rol}`)}
        />
      )}
    </PageContainer>
  );
}
