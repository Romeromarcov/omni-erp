import React from 'react';
import { useTranslation } from 'react-i18next';
import PageLayout from '../../../components/PageLayout';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { pedidoService } from '../../../services/ventas';
import type { Pedido } from '../../../types/ventas';
import { Button } from '@mui/material';

const PedidosListPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: pedidos = [], isLoading } = useQuery<Pedido[]>({
    queryKey: ['pedidos'],
    queryFn: () => pedidoService.getAll() as Promise<Pedido[]>,
  });

  const convertirMutation = useMutation({
    mutationFn: (pedidoId: string) => pedidoService.convertirANotaVenta(pedidoId, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pedidos'] });
    },
    onError: () => {
      alert('Error al convertir el pedido a nota de venta');
    },
  });

  const handleConvertirANotaVenta = (pedido: Pedido) => {
    if (!pedido.convertido_a_nota_venta) {
      convertirMutation.mutate(pedido.id_pedido);
    }
  };

  return (
    <PageLayout>
      <h2 style={{ marginBottom: 16 }}>Gestión de Pedidos</h2>
      <div style={{ marginBottom: 16 }}>
        <Button variant="contained" onClick={() => navigate('new')}>Nuevo Pedido</Button>
      </div>

      {isLoading ? (
        <div>Cargando pedidos...</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: '#f8f9fa' }}>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Número</th>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Fecha</th>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Estado</th>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Cliente</th>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Origen</th>
                <th style={{ padding: '12px', textAlign: 'center', borderBottom: '1px solid #dee2e6' }}>Acciones</th>
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
                      <span style={{ color: '#dc3545' }}>Cliente no encontrado</span>
                    )}
                  </td>
                  <td style={{ padding: '12px' }}>
                    {pedido.id_cotizacion_origen ? (
                      <span style={{ color: '#007bff', fontSize: '12px' }}>
                        ✓ De Cotización
                      </span>
                    ) : (
                      <span style={{ color: '#6c757d', fontSize: '12px' }}>
                        Manual
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '12px', textAlign: 'center' }}>
                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                      <Button
                        variant="contained" color="secondary"
                        onClick={() => navigate(pedido.id_pedido)}
                      >
                        Ver
                      </Button>
                      <Button
                        variant="contained" color="secondary"
                        onClick={() => navigate(`${pedido.id_pedido}/edit`)}
                      >
                        Editar
                      </Button>
                      {!pedido.convertido_a_nota_venta && pedido.estado === 'APROBADO' && (
                        <Button
                          variant="contained"
                          disabled={convertirMutation.isPending}
                          onClick={() => handleConvertirANotaVenta(pedido)}
                        >
                          Convertir a Nota Venta
                        </Button>
                      )}
                      {pedido.convertido_a_nota_venta && (
                        <span style={{ color: '#28a745', fontSize: '12px' }}>
                          ✓ Convertido
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
              No hay pedidos registrados
            </div>
          )}
        </div>
      )}
    </PageLayout>
  );
};

export default PedidosListPage;
