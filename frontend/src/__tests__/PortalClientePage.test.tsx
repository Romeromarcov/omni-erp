import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/portalesService', async () => {
  const actual = await vi.importActual<typeof import('../services/portalesService')>('../services/portalesService');
  return {
    ...actual,
    portalClienteService: {
      solicitarOtp: vi.fn(),
      verificarOtp: vi.fn(),
      getResumen: vi.fn(),
      reportarPago: vi.fn(),
      crearPedido: vi.fn(),
      getTracking: vi.fn(),
    },
  };
});

import { clearPortalClienteSession, portalClienteService } from '../services/portalesService';
import PortalClientePage from '../pages/Ventas/PortalClientePage';

function renderClientePortal() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <PortalClientePage />
    </QueryClientProvider>,
  );
}

describe('PortalClientePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearPortalClienteSession();
  });

  it('autentica vía OTP, muestra estado trimonetario, reporta pago con OCR, crea pedido y consulta tracking', async () => {
    vi.mocked(portalClienteService.solicitarOtp).mockResolvedValue({
      id_token: 'tok-otp',
      canal: 'WHATSAPP',
      destino_enmascarado: '****4567',
      expira_en: '2026-11-24T23:59:00Z',
    });
    vi.mocked(portalClienteService.verificarOtp).mockResolvedValue({
      session_token: 'sess-xyz',
      expira_en: '2026-11-25T23:59:00Z',
      cliente: {
        id_cliente: 'cli-1',
        razon_social: 'Comercial Alpha CA',
        rif: 'J-99887766',
        empresa_id: 'emp-1',
        empresa_nombre: 'Omni Demo',
      },
    });
    vi.mocked(portalClienteService.getResumen).mockResolvedValue({
      cliente: { id_cliente: 'cli-1', razon_social: 'Comercial Alpha CA', rif: 'J-99887766' },
      estado_cuenta_trimonetario: {
        saldo_pendiente: '100.00',
        equivalencias: {
          base: '100.0000',
          base_iso: 'USD',
          pais_fiscal: '4500.0000',
          pais_fiscal_iso: 'VES',
          referencia: '100.0000',
          referencia_iso: 'USDT',
        },
        documentos_pendientes: 1,
        cuentas_vencidas: 0,
      },
      facturas_fiscales: [
        {
          id_factura: 'f1',
          numero_factura: 'F-0001',
          numero_control: '00-0001',
          fecha_emision: '2026-11-20',
          monto_total: '116.0000',
          moneda: 'USD',
          estado: 'EMITIDA',
          pdf_url: '/api/ventas/facturas-fiscales/f1/pdf/',
        },
      ],
      notas_venta: [
        {
          id_nota_venta: 'nv1',
          numero_nota: 'NV-0001',
          fecha_nota: '2026-11-20',
          estado: 'ENTREGADA',
          ambito: 'GERENCIAL',
          pdf_url: '/api/ventas/notas-venta/nv1/pdf/',
        },
      ],
      pagos_reportados: [],
    });
    vi.mocked(portalClienteService.getTracking).mockResolvedValue({
      despachos: [
        {
          id_despacho: 'd1',
          numero_despacho: 'DSP-100',
          estado_despacho: 'EN_RUTA',
          fecha_despacho: '2026-11-24T10:00:00Z',
          token_tracking: 'trk-00000001',
          parada_estado: 'EN_RUTA',
          eta_estimada: '2026-11-24T12:30:00Z',
          tracking_url_publico: 'https://track.omni.test/trk-00000001',
        },
      ],
    });
    vi.mocked(portalClienteService.reportarPago).mockResolvedValue({
      id_pago_portal: 'pp-1',
      estado: 'PENDIENTE',
      monto: '50.00',
      referencia: '998877',
      ocr_extraido: { fuente: 'REGEX_DETERMINISTA', monto: '50.00', moneda: 'USD', referencia: '998877' },
    });
    vi.mocked(portalClienteService.crearPedido).mockResolvedValue({
      id_pedido: 'ped-b2b',
      numero_pedido: 'PED-B2B-01',
      estado: 'PENDIENTE',
      total_estimado: '25.0000',
    });

    renderClientePortal();

    fireEvent.change(screen.getByLabelText(/RIF/i), { target: { value: 'J-99887766' } });
    fireEvent.click(screen.getByRole('button', { name: 'Solicitar código OTP' }));
    await waitFor(() => expect(screen.getByText(/\*\*\*\*4567/)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/Código OTP/i), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: 'Verificar e ingresar' }));

    expect(await screen.findByText('F-0001 (Ctrl 00-0001)')).toBeInTheDocument();
    expect(screen.getByText('4500.0000')).toBeInTheDocument();

    // Reportar pago con OCR
    fireEvent.click(screen.getByRole('tab', { name: /Reportar Pago/i }));
    fireEvent.change(screen.getByLabelText('Monto'), { target: { value: '50.00' } });
    fireEvent.change(screen.getByLabelText('UUID Moneda'), { target: { value: 'm1' } });
    fireEvent.change(screen.getByLabelText('UUID Método de Pago'), { target: { value: 'mp1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar Reporte de Pago' }));
    await waitFor(() => expect(screen.getByText(/OCR \(REGEX_DETERMINISTA\)/i)).toBeInTheDocument());

    // Hacer pedido self-service
    fireEvent.click(screen.getByRole('tab', { name: /Hacer Pedido/i }));
    fireEvent.change(screen.getByLabelText('UUID del Producto'), { target: { value: 'prod-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar Pedido' }));
    await waitFor(() => expect(screen.getByText(/PED-B2B-01/i)).toBeInTheDocument());

    // Tracking
    fireEvent.click(screen.getByRole('tab', { name: /Tracking Despachos/i }));
    expect(await screen.findByText(/DSP-100/)).toBeInTheDocument();

    // Logout
    fireEvent.click(screen.getByRole('button', { name: 'Salir' }));
    expect(screen.getByText('Ingresar con RIF y OTP')).toBeInTheDocument();
  });
});
