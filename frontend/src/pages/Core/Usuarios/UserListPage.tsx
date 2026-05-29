import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, TextField } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import type { Usuario } from '../../../services/users';
import { useApiQuery } from '../../../hooks/useApiQuery';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../../components/ui';
import type { Column } from '../../../components/ui';

type UsuariosApiResponse = Usuario[] | { results: Usuario[] };

export default function UserListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const id_empresa = localStorage.getItem('id_empresa');
  const endpoint = `/core/usuarios/${id_empresa ? `?id_empresa=${id_empresa}` : ''}`;

  const { data: usuarios = [], isLoading } = useApiQuery<UsuariosApiResponse>(endpoint, {
    select: (raw): Usuario[] => {
      if (Array.isArray(raw)) return raw;
      if (raw && typeof raw === 'object' && 'results' in raw && Array.isArray(raw.results)) return raw.results;
      return [];
    },
  });

  const q = search.toLowerCase();
  const filtered = (usuarios as Usuario[]).filter(
    (u) =>
      u.username.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      (u.first_name && u.first_name.toLowerCase().includes(q)) ||
      (u.last_name && u.last_name.toLowerCase().includes(q)),
  );

  const columns: Column<Usuario>[] = [
    { key: 'username', header: 'Usuario', render: (u) => u.username },
    { key: 'email', header: 'Email', render: (u) => u.email },
    { key: 'nombre', header: 'Nombre', render: (u) => `${u.first_name || ''} ${u.last_name || ''}`.trim() || '—' },
    { key: 'activo', header: 'Activo', render: (u) => <StatusChip value={u.is_active} /> },
    {
      key: 'login',
      header: 'Último login',
      render: (u) => (u.fecha_ultimo_login ? new Date(u.fecha_ultimo_login).toLocaleString() : '—'),
    },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (u) => (
        <Button size="small" variant="outlined" onClick={(e) => { e.stopPropagation(); navigate(`/empresas/${id_empresa}/usuarios/${u.id}`); }}>
          Ver / Editar
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Usuarios"
        subtitle="Gestiona los usuarios de la empresa"
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate(`/empresas/${id_empresa}/usuarios/new`)}>
            Nuevo usuario
          </Button>
        }
      />
      <TextField
        size="small"
        placeholder="Buscar usuario…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 2, width: { xs: '100%', sm: 320 } }}
      />
      <DataTable
        columns={columns}
        rows={filtered}
        getRowKey={(u) => u.id}
        loading={isLoading}
        emptyMessage="No se encontraron usuarios."
        onRowClick={(u) => navigate(`/empresas/${id_empresa}/usuarios/${u.id}`)}
      />
    </PageContainer>
  );
}
