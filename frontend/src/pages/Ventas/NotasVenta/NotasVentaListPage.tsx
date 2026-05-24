import React from 'react';
import PageLayout from '../../../components/PageLayout';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { notaVentaService } from '../../../services/ventas';
import type { NotaVenta } from '../../../types/ventas';
import { Button } from '@mui/material';

const NotasVentaListPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  const { data: notasVenta = [], isLoading: loading } = useQuery<NotaVenta[]>({
    queryKey: ['/ventas/notas-venta/'],
    queryFn: () => notaVentaService.getAll(),
  });

  const convertirMutation = useMutation({
    mutationFn: (id: string) => notaVentaService.convertirAFactura(id, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/ventas/notas-venta/'] });
    },
    onError: () => alert(t('ventas.notasVenta.errorConvertir')),
  });

  const handleConvertirAFactura = (notaVenta: NotaVenta) => {
    if (!notaVenta.convertido_a_factura) {
      convertirMutation.mutate(notaVenta.id_nota_venta);
    }
  };

  const getEstadoColor = (estado: string) => {
    switch (estado) {
      case 'BORRADOR': return '#6c757d';
      case 'ENTREGADA': return '#007bff';
      case 'FACTURADA': return '#28a745';
      case 'ANULADA': return '#dc3545';
      default: return '#6c757d';
    }
  };

  return (
    <PageLayout>
      <h2 style={{ marginBottom: 16 }}>{t('ventas.notasVenta.title')}</h2>
      <div style={{ marginBottom: 16 }}>
        <Button variant="contained" onClick={() => navigate('new')}>{t('ventas.notasVenta.nuevo')}</Button>
      </div>

      {loading ? (
        <div>{t('ventas.notasVenta.cargando')}</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: '#f8f9fa' }}>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>{t('ventas.tabla.numero')}</th>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>{t('ventas.tabla.fecha')}</th>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>{t('ventas.tabla.estado')}</th>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>{t('ventas.tabla.cliente')}</th>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>{t('ventas.tabla.origen')}</th>
                <th style={{ padding: '12px', textAlign: 'center', borderBottom: '1px solid #dee2e6' }}>{t('ventas.tabla.acciones')}</th>
              </tr>
            </thead>
            <tbody>
              {notasVenta.map((notaVenta) => (
                <tr key={notaVenta.id_nota_venta} style={{ borderBottom: '1px solid #dee2e6' }}>
                  <td style={{ padding: '12px' }}>{notaVenta.numero_nota}</td>
                  <td style={{ padding: '12px' }}>{notaVenta.fecha_nota ? new Date(notaVenta.fecha_nota).toLocaleDateString() : '-'}</td>
                  <td style={{ padding: '12px' }}>
                    <span style={{
                      padding: '4px 8px',
                      borderRadius: '4px',
                      backgroundColor: getEstadoColor(notaVenta.estado),
                      color: 'white',
                      fontSize: '12px'
                    }}>
                      {notaVenta.estado}
                    </span>
                  </td>
                  <td style={{ padding: '12px' }}>
                    {notaVenta.id_cliente ? (
                      <div>
                        <div style={{ fontWeight: 'bold' }}>{notaVenta.id_cliente.nombre}</div>
                        <div style={{ fontSize: '12px', color: '#6c757d' }}>
                          {notaVenta.id_cliente.razon_social} - {notaVenta.id_cliente.rif}
                        </div>
                      </div>
                    ) : (
                      <span style={{ color: '#dc3545' }}>{t('ventas.tabla.clienteNoEncontrado')}</span>
                    )}
                  </td>
                  <td style={{ padding: '12px' }}>
                    {notaVenta.id_pedido_origen ? (
                      <span style={{ color: '#007bff', fontSize: '12px' }}>
                        {t('ventas.notasVenta.dePedido')}
                      </span>
                    ) : (
                      <span style={{ color: '#6c757d', fontSize: '12px' }}>
                        {t('ventas.tabla.manual')}
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '12px', textAlign: 'center' }}>
                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                      <Button
                        variant="contained" color="secondary"
                        onClick={() => navigate(notaVenta.id_nota_venta)}
                      >
                        {t('ventas.tabla.ver')}
                      </Button>
                      <Button
                        variant="contained" color="secondary"
                        onClick={() => navigate(`${notaVenta.id_nota_venta}/edit`)}
                      >
                        {t('common.edit')}
                      </Button>
                      {!notaVenta.convertido_a_factura && notaVenta.estado === 'ENTREGADA' && (
                        <Button
                          variant="contained"
                          onClick={() => handleConvertirAFactura(notaVenta)}
                        >
                          {t('ventas.notasVenta.convertirAFactura')}
                        </Button>
                      )}
                      {notaVenta.convertido_a_factura && (
                        <span style={{ color: '#28a745', fontSize: '12px' }}>
                          {t('ventas.tabla.convertido')}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {notasVenta.length === 0 && (
            <div style={{ textAlign: 'center', padding: '40px', color: '#6c757d' }}>
              {t('ventas.notasVenta.sinRegistros')}
            </div>
          )}
        </div>
      )}
    </PageLayout>
  );
};

export default NotasVentaListPage;