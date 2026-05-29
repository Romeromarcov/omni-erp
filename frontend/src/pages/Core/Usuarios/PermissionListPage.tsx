import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchPermisos } from '../../../services/permissions';
import type { Permiso } from '../../../services/permissions';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../../components/ui';
import type { Column } from '../../../components/ui';

const PermissionListPage: React.FC = () => {
  const { data: permisos = [], isLoading } = useQuery<Permiso[]>({
    queryKey: ['/permisos/'],
    queryFn: fetchPermisos,
  });

  const columns: Column<Permiso>[] = [
    { key: 'codigo', header: 'Código', render: (p) => p.codigo_permiso },
    { key: 'nombre', header: 'Nombre', render: (p) => p.nombre_permiso },
    { key: 'descripcion', header: 'Descripción', render: (p) => p.descripcion },
    { key: 'modulo', header: 'Módulo', render: (p) => p.modulo },
    { key: 'activo', header: 'Activo', render: (p) => <StatusChip value={p.activo} /> },
  ];

  return (
    <PageContainer>
      <PageHeader title="Listado de Permisos" />
      <DataTable
        columns={columns}
        rows={permisos}
        getRowKey={(p) => p.id_permiso}
        loading={isLoading}
        emptyMessage="No se encontraron permisos."
      />
    </PageContainer>
  );
};

export default PermissionListPage;
