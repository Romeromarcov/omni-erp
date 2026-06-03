import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, TextField, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { useApiQuery } from '../../../hooks/useApiQuery';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../../components/ui';
import type { Column } from '../../../components/ui';

interface TipoDocumento {
  id_tipo_documento: string;
  codigo: string;
  nombre: string;
  categoria: string;
  activo: boolean;
}

type TiposResponse = TipoDocumento[] | { results: TipoDocumento[] };

export default function TipoDocumentoListPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data: tipos = [], isLoading, isError } = useApiQuery<TiposResponse>(
    '/configuracion/tipos-documento/',
    { select: (raw): TipoDocumento[] => (Array.isArray(raw) ? raw : raw.results ?? []) },
  );

  const q = search.toLowerCase();
  const filtered = (tipos as TipoDocumento[]).filter(
    (t) => t.nombre.toLowerCase().includes(q) || t.codigo.toLowerCase().includes(q),
  );

  const columns: Column<TipoDocumento>[] = [
    { key: 'codigo', header: 'Código', render: (t) => <Typography variant="body2" fontWeight={600}>{t.codigo}</Typography> },
    { key: 'nombre', header: 'Nombre', render: (t) => t.nombre },
    { key: 'categoria', header: 'Categoría', render: (t) => t.categoria },
    { key: 'activo', header: 'Activo', align: 'center', render: (t) => <StatusChip value={t.activo} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (t) => (
        <Button size="small" variant="outlined" onClick={(e) => { e.stopPropagation(); navigate(`/configuracion/tipos-documento/${t.id_tipo_documento}`); }}>
          Ver / Editar
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Tipos de Documento"
        subtitle="Plantillas de documentos del sistema"
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('/configuracion/tipos-documento/new')}>
            Nuevo tipo
          </Button>
        }
      />
      <TextField
        size="small"
        placeholder="Buscar por nombre o código…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 2, width: { xs: '100%', sm: 320 } }}
      />
      {isError ? (
        <Alert severity="error">Error al cargar tipos.</Alert>
      ) : (
        <DataTable
          columns={columns}
          rows={filtered}
          getRowKey={(t) => t.id_tipo_documento}
          loading={isLoading}
          emptyMessage="No se encontraron tipos."
          onRowClick={(t) => navigate(`/configuracion/tipos-documento/${t.id_tipo_documento}`)}
        />
      )}
    </PageContainer>
  );
}
