import React, { useEffect, useState } from 'react';
import PageLayout from '../../../components/PageLayout';
import { useNavigate } from 'react-router-dom';
import { notaCreditoVentaService } from '../../../services/ventas';
import type { NotaCreditoVenta } from '../../../types/ventas';
import { Button } from '@mui/material';

const NotasCreditoVentaListPage: React.FC = () => {
  const [notasCredito, setNotasCredito] = useState<NotaCreditoVenta[]>([]);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    loadNotasCredito();
  }, []);

  const loadNotasCredito = async () => {
    setLoading(true);
    try {
      const data = await notaCreditoVentaService.getAll();
      setNotasCredito(data);
    } catch (error) {
      console.error('Error loading notas de crédito de venta:', error);
      setNotasCredito([]);
    } finally {
      setLoading(false);
    }
  };

  const handleAplicar = async (notaCredito: NotaCreditoVenta) => {
    try {
      await notaCreditoVentaService.aplicar(notaCredito.id_nota_credito);
      await loadNotasCredito(); // Recargar la lista
    } catch (error) {
      console.error('Error aplicando nota de crédito:', error);
      alert('Error al aplicar la nota de crédito');
    }
  };

  const getEstadoColor = (estado: string) => {
    switch (estado) {
      case 'PENDIENTE': return '#ffc107';
      case 'APLICADA': return '#28a745';
      case 'ANULADA': return '#dc3545';
      default: return '#6c757d';
    }
  };

  return (
    <PageLayout>
      <div style={{ padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h1>Notas de Crédito de Venta</h1>
          <Button variant="contained" onClick={() => navigate('new')}>
            Nueva Nota de Crédito
          </Button>
        </div>

        {loading ? (
          <div>Cargando...</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', backgroundColor: 'white', borderRadius: '8px', overflow: 'hidden', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8f9fa' }}>
                  <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>N° Nota</th>
                  <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Fecha</th>
                  <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Cliente</th>
                  <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Motivo</th>
                  <th style={{ padding: '12px', textAlign: 'left', borderBottom: '1px solid #dee2e6' }}>Estado</th>
                  <th style={{ padding: '12px', textAlign: 'right', borderBottom: '1px solid #dee2e6' }}>Monto</th>
                  <th style={{ padding: '12px', textAlign: 'center', borderBottom: '1px solid #dee2e6' }}>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {notasCredito.map((notaCredito) => (
                  <tr key={notaCredito.id_nota_credito} style={{ borderBottom: '1px solid #dee2e6' }}>
                    <td style={{ padding: '12px' }}>{notaCredito.numero_nota_credito}</td>
                    <td style={{ padding: '12px' }}>{new Date(notaCredito.fecha_emision).toLocaleDateString()}</td>
                    <td style={{ padding: '12px' }}>
                      {notaCredito.id_cliente ? (
                        <div>
                          <div style={{ fontWeight: 'bold' }}>{notaCredito.id_cliente.nombre}</div>
                          <div style={{ fontSize: '12px', color: '#6c757d' }}>
                            {notaCredito.id_cliente.razon_social} - {notaCredito.id_cliente.rif}
                          </div>
                        </div>
                      ) : (
                        <span style={{ color: '#dc3545' }}>Cliente no encontrado</span>
                      )}
                    </td>
                    <td style={{ padding: '12px' }}>{notaCredito.motivo}</td>
                    <td style={{ padding: '12px' }}>
                      <span style={{
                        padding: '4px 8px',
                        borderRadius: '4px',
                        backgroundColor: getEstadoColor(notaCredito.estado || 'PENDIENTE'),
                        color: 'white',
                        fontSize: '12px'
                      }}>
                        {notaCredito.estado || 'PENDIENTE'}
                      </span>
                    </td>
                    <td style={{ padding: '12px', textAlign: 'right' }}>
                      {notaCredito.monto_total?.toLocaleString('es-VE', { style: 'currency', currency: 'VES' })}
                    </td>
                    <td style={{ padding: '12px', textAlign: 'center' }}>
                      <Button
                        variant="contained" color="secondary"
                        onClick={() => navigate(`${notaCredito.id_nota_credito}`)}
                        style={{ marginRight: '8px' }}
                      >
                        Ver
                      </Button>
                      <Button
                        variant="contained" color="secondary"
                        onClick={() => navigate(`${notaCredito.id_nota_credito}/edit`)}
                        style={{ marginRight: '8px' }}
                      >
                        Editar
                      </Button>
                      {notaCredito.estado !== 'APLICADA' && (
                        <Button
                          variant="contained"
                          onClick={() => handleAplicar(notaCredito)}
                        >
                          Aplicar
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PageLayout>
  );
};

export default NotasCreditoVentaListPage;