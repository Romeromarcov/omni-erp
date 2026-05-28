import React, { useState } from 'react';
import PageLayout from '../../../components/PageLayout';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { pedidoService } from '../../../services/ventas';
import type { Pedido } from '../../../types/ventas';
import type { PaginatedResponse } from '../../../services/ventas';
import { Button } from '@mui/material';
import Pagination from '../../../components/Pagination';

const PAGE_SIZE = 20;

const PedidosListPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<PaginatedResponse<Pedido>>({
    queryKey: ['pedidos', page],
    queryFn: () => pedidoService.getAllPaginated(page, PAGE_SIZE),
  });

  const pedidos = data?.results ?? [];
  const count = data?.count ?? 0;

  const convertirMutation = useMutation({
    mutationFn: (pedidoId: string) => pedidoService.convertirANotaVenta(pedidoId, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pedidos'] });
    },
    onError: () => {
      alert(t('ventas.pedidos.errorConvertir'));
    },
  });

  const handleConvertirANotaVenta = (pedido: Pedido) => {
    if (!pedido.convertido_a_nota_venta) {
      convertirMutation.mutate(pedido.id_pedido);
    }
  };

  return (
    <PageLayout>
      <h2 style={{ marginBottom: 16 }}>{t('ventas.pedidos.title')}</h2>
      <div style={{ marginBottom: 16 }}>
        <Button variant="contained" onClick={() => navigate('new')}>{t('ventas.pedidos.nuevo')}</Button>
      </div>

      {isLoading ? (
        <div>{t('ventas.pedidos.cargando')}</div>
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
              {pedidos.map((pedido) => (
                <tr key={pedido.id_pedido} style={{ borderBottom: '1px solid #dee2e6' }}>
                  <td style={{ padding: '12px' }}>{pedido.numero_pedido}</td>
                  <td style={{ padding: '12px' }}>{new Date(pedido.fecha_pedido).toLocaleDateString()}</td>
                  <td style={{ padding: '12px' }}>
                    <span style={{
                      padding: '4px 8px',
                      borderRadius: '4px',
                      backgroundColor: pedido.estado === 'PENDIENTE' ? '#ffc107' :
                                       pedido.estado === 'APROBADO' ? '#28a745' : '#6c757d',
                      color: 'white',
                      fontSize: '12px'
                    }}>
                      {pedido.estado}
                    </span>
                  </td>
                  <td style={{ padding: '12px' }}>
                    {pedido.id_cliente ? (
                      <div>
                        <div style={{ fontWeight: 'bold' }}>{pedido.id_cliente.nombre}</div>
                        <div style={{ fontSize: '12px', color: '#6c757d' }}>
                          {pedido.id_cliente.razon_social} - {pedido.id_cliente.rif}
                        </div>
                      </div>
                    ) : (
                      <span style={{ color: '#dc3545' }}>{t('ventas.tabla.clienteNoEncontrado')}</span>
                    )}
                  </td>
                  <td style={{ padding: '12px' }}>
                    {pedido.id_cotizacion_origen ? (
                      <span style={{ color: '#007bff', fontSize: '12px' }}>
                        {t('ventas.pedidos.deCotizacion')}
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
                        onClick={() => navigate(pedido.id_pedido)}
                      >
                        {t('ventas.tabla.ver')}
                      </Button>
                      <Button
                        variant="contained" color="secondary"
                        onClick={() => navigate(`${pedido.id_pedido}/edit`)}
                      >
                        {t('common.edit')}
                      </Button>
                      {!pedido.convertido_a_nota_venta && pedido.estado === 'APROBADO' && (
                        <Button
                          variant="contained"
                          disabled={convertirMutation.isPending}
                          onClick={() => handleConvertirANotaVenta(pedido)}
                        >
                          {t('ventas.pedidos.convertirANotaVenta')}
                        </Button>
                      )}
                      {pedido.convertido_a_nota_venta && (
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

          {pedidos.length === 0 && (
            <div style={{ textAlign: 'center', padding: '40px', color: '#6c757d' }}>
              {t('ventas.pedidos.sinRegistros')}
            </div>
          )}

          <Pagination
            page={page}
            count={count}
            pageSize={PAGE_SIZE}
            onChange={(p) => { setPage(p); window.scrollTo(0, 0); }}
          />
        </div>
      )}
    </PageLayout>
  );
};

export default PedidosListPage;
