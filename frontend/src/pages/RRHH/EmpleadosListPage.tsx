/**
 * Listado de Empleados (workstream F) — punto de entrada del módulo RRHH:
 * desde aquí se navega al detalle y al formulario de creación/edición.
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Button, Typography } from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { rrhhService } from '../../services/rrhhService';
import type { Empleado } from '../../services/rrhhService';
import { rrhhKeys } from '../../lib/queryKeys';
import Pagination from '../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

const PAGE_SIZE = 20;

export default function EmpleadosListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: rrhhKeys.empleados(page),
    queryFn: () => rrhhService.getEmpleadosPaginated(page),
  });

  const { data: cargos = [] } = useQuery({
    queryKey: rrhhKeys.cargos(),
    queryFn: () => rrhhService.getCargos(),
  });

  const nombreCargo = useMemo(() => {
    const mapa = new Map<number, string>();
    for (const c of cargos) mapa.set(c.id, c.nombre);
    return (cargoId: number | null) => (cargoId === null ? '—' : (mapa.get(cargoId) ?? '—'));
  }, [cargos]);

  const empleados = data?.results ?? [];
  const count = data?.count ?? 0;

  const columns: Column<Empleado>[] = [
    {
      key: 'nombre',
      header: t('rrhh.empleados.nombre'),
      render: (e) => (
        <Typography variant="body2" fontWeight={600}>
          {e.nombre} {e.apellido}
        </Typography>
      ),
    },
    { key: 'cedula', header: t('rrhh.empleados.cedula'), render: (e) => e.cedula },
    { key: 'cargo', header: t('rrhh.empleados.cargo'), render: (e) => nombreCargo(e.cargo) },
    {
      key: 'ingreso',
      header: t('rrhh.empleados.fechaIngreso'),
      render: (e) => e.fecha_ingreso,
    },
    {
      key: 'activo',
      header: t('rrhh.empleados.estado'),
      render: (e) => (
        <StatusChip
          value={e.activo}
          label={e.activo ? t('common.active') : t('common.inactive')}
        />
      ),
    },
    {
      key: 'acciones',
      header: t('common.actions'),
      align: 'right',
      render: (e) => (
        <Button size="small" onClick={() => navigate(`/rrhh/empleados/${e.id}`)}>
          {t('rrhh.empleados.ver')}
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('rrhh.empleados.title')}
        subtitle={t('rrhh.empleados.subtitle')}
        actions={
          <Button
            variant="contained"
            startIcon={<AddOutlined />}
            onClick={() => navigate('/rrhh/empleados/nuevo')}
          >
            {t('rrhh.empleados.nuevo')}
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={empleados}
        getRowKey={(e) => String(e.id)}
        loading={isLoading}
        emptyMessage={t('rrhh.empleados.empty')}
        onRowClick={(e) => navigate(`/rrhh/empleados/${e.id}`)}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={setPage} />
    </PageContainer>
  );
}
