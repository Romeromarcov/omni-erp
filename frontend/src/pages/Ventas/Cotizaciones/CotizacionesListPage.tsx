import React, { useState } from 'react';
import PageLayout from '../../../components/PageLayout';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cotizacionService } from '../../../services/ventas';
import type { Cotizacion } from '../../../types/ventas';
import type { PaginatedResponse } from '../../../services/ventas';
import { Button } from '@mui/material';
import Pagination from '../../../components/Pagination';

const PAGE_SIZE = 20;

const CotizacionesListPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);

  const { data, isLoading: loading } = useQuery<PaginatedResponse<Cotizacion>>({
    queryKey: ['/ventas/cotizaciones/', page],
    queryFn: () => cotizacionService.getAllPaginated(page, PAGE_SIZE),
  });

  const cotizaciones = data?.results ?? [];
  const count = data?.count ?? 0;

  const convertirMutation = useMutation({
    mutationFn: (id: string) => cotizacionService.convertirAPedido(id, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/ventas/cotizaciones/'] });
    },
    onError: () => alert('Error al convertir la cotización a pedido'),
  });

  const handleConvertirAPedido = (cotizacion: Cotizacion) => {
    if (!cotizacion.convertido_a_pedido) {
      convertirMutation.mutate(cotizacion.id_cotizacion);
    }
  };

  const getEstadoColor = (estado: string) => {
    switch (estado) {
      case 'BORRADOR': return '#6c757d';
      case 'ENVIADA': return '#007bff';
      case 'ACEPTADA': return '#28a745';
      case 'RECHAZADA': return '#dc3545';
      case 'VENCIDA': return '#ffc107';
      case 'ANULADA': return '#6c757d';
      default: return '#6c757d';
    }
  };

  return (
    <PageLayout>
      <h2 style={{ marginBottom: 16 }}>Gestión de Cotizaciones</h2>
      <div style={{ marginBottom: 16 }}>
        <Button variant="contained" onClick={() => navigate('new')}>Nueva Cotización</Button>
      </div>

      {loading ? (
        <div>Cargando cotizaciones...</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: '#f8f9fa' }}>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Número</th>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Fecha</th>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Vencimiento</th>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Estado</th>
                <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Cliente</th>
                <th style={{ padding: '12px', textAlign: 'right', borderBottom: '1px solid #dee2e6' }}>Monto Total</th>
                <th style={{ padding: '12px', textAlign: 'center', borderBottom: '1px solid #dee2e6' }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {cotizaciones.map((cotizacion) => (
                <tr key={cotizacion.id_cotizacion} style={{ borderBottom: '1px solid #dee2e6' }}>
                  <td style={{ padding: '12px' }}>{cotizacion.numero_cotizacion}</td>
                  <td style={{ padding: '12px' }}>{new Date(cotizacion.fecha_cotizacion).toLocaleDateString()}</td>
                  <td style={{ padding: '12px' }}>{new Date(cotizacion.fecha_vencimiento).toLocaleDateString()}</td>
                  <td style={{ padding: '12px' }}>
                    <span style={{
                      padding: '4px 8px',
                      borderRadius: '4px',
                      backgroundColor: getEstadoColor(cotizacion.estado),
                      color: 'white',
                      fontSize: '12px'
                    }}>
                      {cotizacion.estado}
                    </span>
                  </td>
                  <td style={{ padding: '12px' }}>
                    {cotizacion.id_cliente ? (
                      <div>
                        <div style={{ fontWeight: 'bold' }}>{cotizacion.id_cliente.nombre}</div>
                        <div style={{ fontSize: '12px', color: '#6c757d' }}>
                          {cotizacion.id_cliente.razon_social} - {cotizacion.id_cliente.rif}
                        </div>
                      </div>
                    ) : (
                      <span style={{ color: '#dc3545' }}>Cliente no encontrado</span>
                    )}
                  </td>
                  <td style={{ padding: '12px', textAlign: 'right' }}>
                    {(cotizacion.monto_total ?? 0).toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                  </td>
                  <td style={{ padding: '12px', textAlign: 'center' }}>
                    <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
                      <Button
                        variant="contained" color="secondary"
                        onClick={() => navigate(cotizacion.id_cotizacion)}
                      >
                        Ver
                      </Button>
                      <Button
                        variant="contained" color="secondary"
                        onClick={() => navigate(`${cotizacion.id_cotizacion}/edit`)}
                      >
                        Editar
                      </Button>
                      {!cotizacion.convertido_a_pedido && cotizacion.estado === 'ACEPTADA' && (
                        <Button
                          variant="contained"
                          onClick={() => handleConvertirAPedido(cotizacion)}
                        >
                          Convertir a Pedido
                        </Button>
                      )}
                      {cotizacion.convertido_a_pedido && (
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

          {cotizaciones.length === 0 && (
            <div style={{ textAlign: 'center', padding: '40px', color: '#6c757d' }}>
              No hay cotizaciones registradas
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

export default CotizacionesListPage;
