import React, { useEffect, useState } from 'react';
import PageLayout from '../../../components/PageLayout';
import { useNavigate } from 'react-router-dom';
import { pedidoService } from '../../../services/ventas';
import type { Pedido } from '../../../types/ventas';
import { Button } from '@mui/material';

const PedidosListPage: React.FC = () => {
  const [pedidos, setPedidos] = useState<Pedido[]>([]);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    loadPedidos();
  }, []);

  const loadPedidos = async () => {
    setLoading(true);
    try {
      const data = await pedidoService.getAll();
      setPedidos(data);
    } catch (error) {
      console.error('Error loading pedidos:', error);
      setPedidos([]);
    } finally {
      setLoading(false);
    }
  };

  const handleConvertirANotaVenta = async (pedido: Pedido) => {
    if (!pedido.convertido_a_nota_venta) {
      try {
        await pedidoService.convertirANotaVenta(pedido.id_pedido, {});
        await loadPedidos(); // Recargar la lista
      } catch (error) {
        console.error('Error convirtiendo pedido a nota de venta:', error);
        alert('Error al convertir el pedido a nota de venta');
      }
    }
  };

  return (
    <PageLayout>
      <h2 style={{ marginBottom: 16 }}>Gestión de Pedidos</h2>
      <div style={{ marginBottom: 16 }}>
        <Button variant="contained" onClick={() => navigate('new')}>Nuevo Pedido</Button>
      </div>

      {loading ? (
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
