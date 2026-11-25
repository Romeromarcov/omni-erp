import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  API_URL: 'http://localhost:8000/api',
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'e1' }));

import { get, post } from '../services/api';
import PortalVendedorPage from '../pages/Ventas/PortalVendedorPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PortalVendedorPage />
    </QueryClientProvider>,
  );
}

describe('PortalVendedorPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.includes('/portal-vendedor/cartera/')) {
        return Promise.resolve({
          empresa_id: 'e1',
          clientes: [
            {
              id_cliente: 'cli-1',
              razon_social: 'Distribuidora Beta',
              rif: 'J-12345678',
              tipo_cliente: 'CREDITO',
              limite_credito: '5000.00',
              saldo_pendiente: '120.00',
              cuentas_vencidas: 1,
              bloquear_por_mora: true,
            },
          ],
        });
      }
      if (url.includes('/portal-vendedor/catalogo/')) {
        return Promise.resolve({
          empresa_id: 'e1',
          productos: [
            {
              id_producto: 'prod-1',
              sku: 'OIL-20W50',
              codigo_barras: '75900011',
              nombre_producto: 'Aceite 20W50 Galón',
              stock_disponible: '35.0000',
              precio: '25.0000',
              moneda_precio: 'USD',
              equivalencias_trimonetarias: {
                base: '25.0000',
                base_iso: 'USD',
                pais_fiscal: '1125.0000',
                pais_fiscal_iso: 'VES',
                referencia: '25.0000',
                referencia_iso: 'USDT',
              },
            },
          ],
        });
      }
      if (url.includes('/portal-vendedor/metas-comisiones/')) {
        return Promise.resolve({
          empresa_id: 'e1',
          total_devengado: '150.0000',
          total_liquidado: '50.0000',
          esquemas: [
            {
              id_esquema_comision: 'esq-1',
              porcentaje_base: '5.0000',
              meta_mensual_monto: '1000.0000',
              bono_meta_porcentaje: '2.0000',
              modalidad_devengo: 'COBRO_EFECTIVO',
            },
          ],
          comisiones: [
            {
              id_comision_venta: 'com-1',
              nota_venta: 'NV-001',
              monto: '75.0000',
              estado: 'DEVENGADA',
              origen_devengo: 'COBRO',
              fecha_devengo: '2026-11-24',
            },
          ],
        });
      }
      if (url.includes('/finanzas/monedas/')) {
        return Promise.resolve([{ id_moneda: 'm-usd', codigo_iso: 'USD', nombre: 'Dólar', simbolo: '$' }]);
      }
      if (url.includes('/finanzas/metodos-pago/')) {
        return Promise.resolve([{ id_metodo_pago: 'mp-1', nombre_metodo: 'Efectivo', tipo_metodo: 'EFECTIVO' }]);
      }
      return Promise.resolve([]);
    });
  });

  it('muestra cartera, agrega producto del catálogo trimonetario y envía check-in, pedido y revisa metas', async () => {
    vi.mocked(post).mockImplementation((url: string) => {
      if (url.includes('/checkin/')) {
        return Promise.resolve({ id_visita: 'v1', fecha_visita: '2026-11-24', distancia_cliente_m: '15.00', resultado: 'EFECTIVA' });
      }
      if (url.includes('/pedidos/')) {
        return Promise.resolve({ id_pedido: 'ped-1', numero_pedido: 'PED-SFA-01', estado: 'PENDIENTE', total_estimado: '25.0000' });
      }
      return Promise.resolve({ id_pago_portal: 'pp-1', estado: 'PENDIENTE', monto: '50', moneda: 'USD' });
    });

    renderPage();
    expect(await screen.findByText('Distribuidora Beta')).toBeInTheDocument();
    expect(screen.getByText('En mora')).toBeInTheDocument();

    // Seleccionar cliente hacia Check-in GPS
    fireEvent.click(screen.getByRole('button', { name: 'Operar cliente' }));
    expect(screen.getByText(/Check-in GPS en Cliente/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Registrar Check-in GPS' }));
    await waitFor(() => {
      expect(screen.getByText(/Check-in registrado/i)).toBeInTheDocument();
    });

    // Ir a Catálogo y agregar producto
    fireEvent.click(screen.getByRole('tab', { name: /Catálogo/i }));
    expect(await screen.findByText('Aceite 20W50 Galón')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Agregar al pedido' }));

    // Enviar pedido
    fireEvent.click(screen.getByRole('tab', { name: /Pedido y Cobro/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Enviar Pedido' }));
    await waitFor(() => {
      expect(screen.getByText(/Pedido PED-SFA-01 creado/i)).toBeInTheDocument();
    });

    // Reportar cobro en campo
    fireEvent.change(screen.getByLabelText('Monto cobrado'), { target: { value: '50.00' } });
    fireEvent.mouseDown(screen.getByLabelText('Moneda'));
    fireEvent.click(await screen.findByText('USD - Dólar'));
    fireEvent.mouseDown(screen.getByLabelText('Método de pago'));
    fireEvent.click(await screen.findByText('Efectivo (EFECTIVO)'));
    fireEvent.change(screen.getByLabelText('Referencia'), { target: { value: 'REF-100' } });
    fireEvent.click(screen.getByRole('button', { name: 'Registrar Cobro' }));
    await waitFor(() => {
      expect(screen.getByText(/Cobro pp-1 reportado/i)).toBeInTheDocument();
    });

    // Ver metas y comisiones
    fireEvent.click(screen.getByRole('tab', { name: /Metas y Comisiones/i }));
    expect(await screen.findByText('$150.0000')).toBeInTheDocument();
    expect(screen.getByText(/COBRO_EFECTIVO/i)).toBeInTheDocument();
  });
});
