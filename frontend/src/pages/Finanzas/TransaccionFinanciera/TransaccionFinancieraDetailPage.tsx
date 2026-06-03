import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getTransaccionFinancieraDetail, printTransaccionFinanciera } from '../../../services/transaccionFinancieraService';
import { PageContainer, PageHeader } from '../../../components/ui';
import { Box, Button, Divider, Stack, Typography } from '@mui/material';

type TransaccionFinancieraDetail = {
  id: string;
  fecha_hora_transaccion: string;
  tipo_transaccion: string;
  monto_transaccion: number;
  id_moneda_transaccion__codigo_iso: string;
  monto_base_empresa: number;
  id_metodo_pago__nombre_metodo: string;
  referencia_pago: string;
  descripcion: string;
  id_usuario_registro__username: string;
  conciliada?: boolean;
  id_empresa?: string;
  id_empresa_nombre?: string;
  id_usuario_registro?: string;
  id_caja?: string;
  id_caja_nombre?: string;
  id_cuenta_bancaria?: string;
  id_cuenta_bancaria_nombre?: string;
  tipo_documento?: string;
  nro_documento?: string;
  [key: string]: string | number | boolean | undefined;
};

const Row: React.FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <Box sx={{ display: 'flex', gap: 1, py: 0.75 }}>
    <Typography sx={{ fontWeight: 'bold', minWidth: 200 }}>{label}</Typography>
    <Typography>{value}</Typography>
  </Box>
);

const TransaccionFinancieraDetailPage: React.FC = () => {
  const { id_transaccion } = useParams<{ id_transaccion: string }>();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery<TransaccionFinancieraDetail>({
    queryKey: [`/finanzas/transacciones-financieras/${id_transaccion}/`],
    queryFn: () => getTransaccionFinancieraDetail(id_transaccion!) as Promise<TransaccionFinancieraDetail>,
    enabled: !!id_transaccion,
  });

  if (!id_transaccion) {
    return (
      <PageContainer>
        <PageHeader title="Detalle de Transacción Financiera" />
        <Typography mb={2}>No se encontró el ID de la transacción.</Typography>
        <Button variant="outlined" onClick={() => navigate(-1)}>Volver</Button>
      </PageContainer>
    );
  }

  if (isLoading || !data) {
    return (
      <PageContainer>
        <PageHeader title="Detalle de Transacción Financiera" />
        <Typography color="text.secondary">Cargando...</Typography>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="Detalle de Transacción Financiera"
        actions={
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" onClick={() => navigate(-1)}>Volver</Button>
            <Button variant="contained" onClick={() => printTransaccionFinanciera(id_transaccion || '')}>Imprimir</Button>
          </Stack>
        }
      />
      <Box>
        <Row label="ID Transacción" value={data.id} />
        <Divider />
        <Row label="ID Empresa" value={data.id_empresa || '-'} />
        <Divider />
        <Row label="Nombre Empresa" value={data.id_empresa_nombre || '-'} />
        <Divider />
        <Row label="Usuario Registro" value={data.id_usuario_registro_username || data.id_usuario_registro__username || '-'} />
        <Divider />
        <Row label="Fecha/Hora" value={data.fecha_hora_transaccion} />
        <Divider />
        <Row label="Tipo de Transacción" value={data.tipo_transaccion} />
        <Divider />
        <Row label="Monto" value={data.monto_transaccion} />
        <Divider />
        <Row label="Moneda" value={data.id_moneda_transaccion__codigo_iso} />
        <Divider />
        <Row label="Moneda Base" value={data.id_moneda_base__codigo_iso} />
        <Divider />
        <Row label="Monto Base Empresa" value={data.monto_base_empresa} />
        <Divider />
        <Row label="Moneda País Empresa" value={data.id_moneda_pais_empresa__codigo_iso} />
        <Divider />
        <Row label="Monto Moneda País" value={data.monto_moneda_pais} />
        <Divider />
        <Row label="Método de Pago" value={data.id_metodo_pago__nombre_metodo} />
        <Divider />
        <Row label="Referencia de Pago" value={data.referencia_pago} />
        <Divider />
        <Row label="Descripción" value={data.descripcion} />
        <Divider />
        <Row label="Caja" value={data.id_caja_nombre || data.id_caja || '-'} />
        <Divider />
        <Row label="Cuenta Bancaria" value={data.id_cuenta_bancaria_nombre || data.id_cuenta_bancaria || '-'} />
        <Divider />
        <Row label="Tipo de Documento" value={data.tipo_documento || '-'} />
        <Divider />
        <Row label="Nro. Documento" value={data.nro_documento || '-'} />
        <Divider />
        <Row label="Conciliada" value={data.conciliada ? 'Sí' : 'No'} />
      </Box>
    </PageContainer>
  );
};

export default TransaccionFinancieraDetailPage;
