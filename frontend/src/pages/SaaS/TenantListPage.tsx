import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Button } from '@mui/material';
import { PageContainer, PageHeader, DataTable, StatusChip, type Column } from '../../components/ui';
import { fetchSuscripciones, type Suscripcion } from '../../services/saasService';
import { fetchEmpresas, type Empresa } from '../../services/empresas';

const ESTADOS_VIGENTES = ['ACTIVA', 'TRIAL'];

const TenantListPage: React.FC = () => {
  const navigate = useNavigate();

  const { data: empresas = [], isLoading } = useQuery<Empresa[], Error>({
    queryKey: ['empresas', 'visible'],
    queryFn: fetchEmpresas,
  });
  const { data: suscripciones = [] } = useQuery<Suscripcion[], Error>({
    queryKey: ['saas/suscripciones'],
    queryFn: () => fetchSuscripciones(),
  });

  // Suscripción vigente más representativa por empresa (vigente primero).
  const vigentePorEmpresa = useMemo(() => {
    const map = new Map<string, Suscripcion>();
    for (const s of suscripciones) {
      const actual = map.get(s.id_empresa);
      const sEsVigente = ESTADOS_VIGENTES.includes(s.estado);
      if (!actual) {
        map.set(s.id_empresa, s);
      } else if (sEsVigente && !ESTADOS_VIGENTES.includes(actual.estado)) {
        map.set(s.id_empresa, s);
      }
    }
    return map;
  }, [suscripciones]);

  const columns: Column<Empresa>[] = [
    { key: 'nombre', header: 'Tenant', render: (e) => e.nombre_comercial || e.nombre_legal },
    { key: 'rif', header: 'Identificador fiscal', render: (e) => e.identificador_fiscal || '—' },
    { key: 'email', header: 'Email', render: (e) => e.email_contacto || '—' },
    {
      key: 'plan',
      header: 'Plan actual',
      render: (e) => vigentePorEmpresa.get(e.id_empresa)?.plan_nombre ?? '—',
    },
    {
      key: 'estado',
      header: 'Suscripción',
      render: (e) => {
        const s = vigentePorEmpresa.get(e.id_empresa);
        return s ? <StatusChip value={s.estado.toLowerCase()} label={s.estado} /> : <StatusChip value="no" label="Sin suscripción" />;
      },
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (e) => (
        <Box onClick={(ev) => ev.stopPropagation()}>
          <Button
            size="small"
            variant="outlined"
            onClick={() => navigate(`/admin-saas/suscripciones/new?empresa=${e.id_empresa}`)}
          >
            Asignar plan
          </Button>
        </Box>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Tenants"
        subtitle="Todas las empresas registradas en la plataforma y su suscripción vigente."
      />
      <DataTable
        columns={columns}
        rows={empresas}
        getRowKey={(e) => e.id_empresa}
        loading={isLoading}
        emptyMessage="No hay empresas registradas."
        onRowClick={() => navigate('/admin-saas/suscripciones')}
      />
    </PageContainer>
  );
};

export default TenantListPage;
