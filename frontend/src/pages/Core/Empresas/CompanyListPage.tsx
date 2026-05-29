import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, TextField } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useApiQuery } from '../../../hooks/useApiQuery';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../../components/ui';
import type { Column } from '../../../components/ui';

interface Empresa {
  id_empresa: string;
  nombre_legal: string;
  nombre_comercial: string;
  identificador_fiscal: string;
  email_contacto: string;
  activo: boolean;
  fecha_registro: string;
}

type EmpresaApiResponse = Empresa[] | { results: Empresa[] };

function normalizeEmpresas(raw: EmpresaApiResponse): Empresa[] {
  const list = Array.isArray(raw) ? raw : raw.results ?? [];
  return list.map((e) => ({
    ...e,
    activo: e.activo === true || String(e.activo).toLowerCase() === 'true' || String(e.activo) === '1',
  }));
}

export default function CompanyListPage() {
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  const { data: empresas = [], isLoading, isError } = useApiQuery<EmpresaApiResponse>(
    '/core/empresas/',
    { select: normalizeEmpresas },
  );

  const q = search.toLowerCase();
  const filtered = (empresas as Empresa[]).filter(
    (e) => e.nombre_legal.toLowerCase().includes(q) || e.nombre_comercial.toLowerCase().includes(q),
  );

  const columns: Column<Empresa>[] = [
    { key: 'legal', header: 'Nombre legal', render: (e) => e.nombre_legal },
    { key: 'comercial', header: 'Nombre comercial', render: (e) => e.nombre_comercial },
    { key: 'rif', header: 'Identificador fiscal', render: (e) => e.identificador_fiscal },
    { key: 'email', header: 'Email', render: (e) => e.email_contacto },
    { key: 'activo', header: 'Activo', render: (e) => <StatusChip value={e.activo} /> },
    { key: 'fecha', header: 'Fecha registro', render: (e) => e.fecha_registro },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (e) => (
        <Button size="small" variant="outlined" onClick={(ev) => { ev.stopPropagation(); navigate(`/empresas/${e.id_empresa}`); }}>
          Ver / Editar
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Empresas"
        subtitle="Empresas registradas en el sistema"
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('/empresas/new')}>
            Nueva empresa
          </Button>
        }
      />
      <TextField
        size="small"
        placeholder="Buscar empresa…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 2, width: { xs: '100%', sm: 320 } }}
      />
      {isError ? (
        <Alert severity="error">Error al cargar empresas.</Alert>
      ) : (
        <DataTable
          columns={columns}
          rows={filtered}
          getRowKey={(e) => e.id_empresa}
          loading={isLoading}
          emptyMessage="No se encontraron empresas."
          onRowClick={(e) => navigate(`/empresas/${e.id_empresa}`)}
        />
      )}
    </PageContainer>
  );
}
