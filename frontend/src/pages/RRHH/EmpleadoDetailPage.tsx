/**
 * Detalle de Empleado (workstream F): datos básicos, cargo, salario mensual
 * (string decimal del documento_json, formateado con decimal.js) y estado.
 */
import { useMemo, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Box, Button, CircularProgress, Paper, Stack, Typography } from '@mui/material';
import EditOutlined from '@mui/icons-material/EditOutlined';
import { rrhhService } from '../../services/rrhhService';
import { rrhhKeys } from '../../lib/queryKeys';
import { toFixedStr } from '../../lib/decimal';
import { PageContainer, PageHeader, StatusChip } from '../../components/ui';

interface CampoProps {
  label: string;
  value: ReactNode;
}

function Campo({ label, value }: CampoProps) {
  return (
    <Box sx={{ minWidth: 180 }}>
      <Typography variant="caption" color="text.secondary" display="block">
        {label}
      </Typography>
      <Typography variant="body1" component="div">
        {value}
      </Typography>
    </Box>
  );
}

export default function EmpleadoDetailPage() {
  const { id = '' } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data: empleado, isLoading } = useQuery({
    queryKey: rrhhKeys.empleado(id),
    queryFn: () => rrhhService.getEmpleado(id),
    enabled: !!id,
  });

  const { data: cargos = [] } = useQuery({
    queryKey: rrhhKeys.cargos(),
    queryFn: () => rrhhService.getCargos(),
  });

  const nombreCargo = useMemo(() => {
    if (!empleado || empleado.cargo === null) return '—';
    return cargos.find((c) => c.id === empleado.cargo)?.nombre ?? '—';
  }, [cargos, empleado]);

  if (isLoading) {
    return (
      <PageContainer>
        <Stack alignItems="center" sx={{ py: 8 }}>
          <CircularProgress />
        </Stack>
      </PageContainer>
    );
  }

  const salario = empleado?.documento_json?.salario_mensual;

  return (
    <PageContainer>
      <PageHeader
        title={empleado ? `${empleado.nombre} ${empleado.apellido}` : t('rrhh.detalle.title')}
        subtitle={empleado ? `${t('rrhh.empleados.cedula')}: ${empleado.cedula}` : undefined}
        actions={
          <>
            <Button variant="outlined" onClick={() => navigate('/rrhh/empleados')}>
              {t('common.back')}
            </Button>
            <Button
              variant="contained"
              startIcon={<EditOutlined />}
              onClick={() => navigate(`/rrhh/empleados/${id}/editar`)}
              disabled={!empleado}
            >
              {t('common.edit')}
            </Button>
          </>
        }
      />
      {empleado && (
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Stack direction="row" spacing={4} useFlexGap flexWrap="wrap">
            <Campo label={t('rrhh.empleados.cargo')} value={nombreCargo} />
            <Campo label={t('rrhh.empleados.fechaIngreso')} value={empleado.fecha_ingreso} />
            <Campo
              label={t('rrhh.form.salario')}
              value={
                typeof salario === 'string' && salario !== '' ? (
                  <Typography component="span" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                    {toFixedStr(salario)}
                  </Typography>
                ) : (
                  t('rrhh.detalle.sinSalario')
                )
              }
            />
            <Campo
              label={t('rrhh.empleados.estado')}
              value={
                <StatusChip
                  value={empleado.activo}
                  label={empleado.activo ? t('common.active') : t('common.inactive')}
                />
              }
            />
          </Stack>
        </Paper>
      )}
    </PageContainer>
  );
}
