import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getTransaccionFinancieraDetail, printTransaccionFinanciera } from '../../../services/transaccionFinancieraService';
import PageLayout from '../../../components/PageLayout';
import { Button, Paper } from '@mui/material';

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

const TransaccionFinancieraDetailPage: React.FC = () => {
  const { id_transaccion } = useParams<{ id_transaccion: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<TransaccionFinancieraDetail | null>(null);
  // const [editMode, setEditMode] = useState(false);

  useEffect(() => {
    if (!id_transaccion) return; // Evita el fetch si no hay ID
    getTransaccionFinancieraDetail(id_transaccion).then(result => setData(result as TransaccionFinancieraDetail));
  }, [id_transaccion]);

  if (!id_transaccion) {
    return (
      <PageLayout>
        <h2 style={{ marginBottom: 16 }}>Detalle de Transacción Financiera</h2>
        <div>No se encontró el ID de la transacción.</div>
        <Button onClick={() => navigate(-1)}>Volver</Button>
      </PageLayout>
    );
  }

  if (!data) return <PageLayout><h2 style={{ marginBottom: 16 }}>Detalle de Transacción Financiera</h2><div>Cargando...</div></PageLayout>;

  return (
    <PageLayout>
      <h2 style={{ marginBottom: 16 }}>Detalle de Transacción Financiera</h2>
      <Paper sx={{ p: 2 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 16 }}>
          <tbody>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>ID Transacción</td>
              <td style={{ padding: '4px 8px' }}>{data.id}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>ID Empresa</td>
              <td style={{ padding: '4px 8px' }}>{data.id_empresa || '-'}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Nombre Empresa</td>
              <td style={{ padding: '4px 8px' }}>{data.id_empresa_nombre || '-'}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Usuario Registro</td>
              <td style={{ padding: '4px 8px' }}>{data.id_usuario_registro_username || data.id_usuario_registro__username || '-'}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Fecha/Hora</td>
              <td style={{ padding: '4px 8px' }}>{data.fecha_hora_transaccion}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Tipo de Transacción</td>
              <td style={{ padding: '4px 8px' }}>{data.tipo_transaccion}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Monto</td>
              <td style={{ padding: '4px 8px' }}>{data.monto_transaccion}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Moneda</td>
              <td style={{ padding: '4px 8px' }}>{data.id_moneda_transaccion__codigo_iso}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Moneda Base</td>
              <td style={{ padding: '4px 8px' }}>{data.id_moneda_base__codigo_iso}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Monto Base Empresa</td>
              <td style={{ padding: '4px 8px' }}>{data.monto_base_empresa}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Moneda País Empresa</td>
              <td style={{ padding: '4px 8px' }}>{data.id_moneda_pais_empresa__codigo_iso}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Monto Moneda País</td>
              <td style={{ padding: '4px 8px' }}>{data.monto_moneda_pais}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Método de Pago</td>
              <td style={{ padding: '4px 8px' }}>{data.id_metodo_pago__nombre_metodo}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Referencia de Pago</td>
              <td style={{ padding: '4px 8px' }}>{data.referencia_pago}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Descripción</td>
              <td style={{ padding: '4px 8px' }}>{data.descripcion}</td>
            </tr>
            {/* Caja asociada */}
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Caja</td>
              <td style={{ padding: '4px 8px' }}>{data.id_caja_nombre || data.id_caja || '-'}</td>
            </tr>
            {/* Cuenta bancaria asociada */}
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Cuenta Bancaria</td>
              <td style={{ padding: '4px 8px' }}>{data.id_cuenta_bancaria_nombre || data.id_cuenta_bancaria || '-'}</td>
            </tr>
            {/* Tipo de documento asociado */}
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Tipo de Documento</td>
              <td style={{ padding: '4px 8px' }}>{data.tipo_documento || '-'}</td>
            </tr>
            {/* Número de documento asociado */}
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Nro. Documento</td>
              <td style={{ padding: '4px 8px' }}>{data.nro_documento || '-'}</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 'bold', padding: '4px 8px', background: '#f6fafd' }}>Conciliada</td>
              <td style={{ padding: '4px 8px' }}>{data.conciliada ? 'Sí' : 'No'}</td>
            </tr>
          </tbody>
        </table>
        <div style={{ display: 'flex', gap: 8 }}>
          {/* <Button onClick={() => setEditMode(true)} disabled={!!data.conciliada}>Editar</Button> */}
          <Button onClick={() => printTransaccionFinanciera(id_transaccion || '')}>Imprimir</Button>
          <Button onClick={() => navigate(-1)}>Volver</Button>
        </div>
        {/* Si editMode, mostrar formulario de edición limitada aquí */}
      </Paper>
    </PageLayout>
  );
};

export default TransaccionFinancieraDetailPage;
