import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'emp-1' }));
vi.mock('../services/session', () => ({ getSessionUsuarioId: () => 'usr-1' }));

import { get, post } from '../services/api';
import AprovisionamientoPage from '../pages/Compras/AprovisionamientoPage';

const reqBorrador = {
  id_requisicion: 'req-borrador',
  id_empresa: 'emp-1',
  id_solicitante: 'usr-1',
  id_departamento: 'dep-1',
  numero_requisicion: 'REQ-BOR-01',
  fecha_requisicion: '2026-11-20',
  estado: 'BORRADOR',
  prioridad: 'ALTA',
  fecha_necesidad: '2026-11-28',
  justificacion: 'Compra resmas',
  observaciones: null,
};

const reqPendiente = {
  ...reqBorrador,
  id_requisicion: 'req-pendiente',
  numero_requisicion: 'REQ-PEN-01',
  estado: 'PENDIENTE',
};

const reqAprobada = {
  ...reqBorrador,
  id_requisicion: 'req-aprobada',
  numero_requisicion: 'REQ-APR-01',
  estado: 'APROBADA',
};

const solicitud1 = {
  id_solicitud_cotizacion: 'rfq-1',
  id_empresa: 'emp-1',
  numero_solicitud: 'RFQ-001',
  fecha_solicitud: '2026-11-20',
  fecha_vencimiento: '2026-11-30',
  estado: 'ENVIADA',
  observaciones: null,
};

const oferta1 = {
  id_oferta: 'ofe-1',
  id_solicitud_cotizacion: 'rfq-1',
  id_proveedor: 'prov-1',
  numero_oferta: 'OF-ALFA-01',
  fecha_oferta: '2026-11-20',
  fecha_vencimiento: '2026-11-29',
  estado: 'RECIBIDA',
  monto_total: '120.0000',
  condiciones_pago: '30 días',
  tiempo_entrega: '3 días',
  observaciones: null,
};

const proveedor1 = { id_proveedor: 'prov-1', razon_social: 'Suministros Alfa C.A.' };
const proveedor2 = { id_proveedor: 'prov-2', razon_social: 'Distribuidora Beta S.A.' };
const almacen1 = { id_almacen: 'alm-1', nombre_almacen: 'Almacén Central', codigo_almacen: 'AC-01' };
const producto1 = {
  id_producto: 'prod-1',
  nombre_producto: 'Resma Carta',
  sku: 'RES-001',
};

const comparativoMock = {
  rfq_id: 'rfq-1',
  numero_solicitud: 'RFQ-001',
  estado: 'ENVIADA',
  fecha_solicitud: '2026-11-20',
  fecha_vencimiento: '2026-11-30',
  mejor_oferta_id: 'ofe-1',
  ofertas: [
    {
      id_oferta: 'ofe-1',
      numero_oferta: 'OF-ALFA-01',
      id_proveedor: 'prov-1',
      proveedor_nombre: 'Suministros Alfa C.A.',
      estado: 'RECIBIDA',
      monto_total: '120.0000',
      tiempo_entrega: '3 días',
      condiciones_pago: '30 días',
      es_mejor_total: true,
    },
    {
      id_oferta: 'ofe-2',
      numero_oferta: 'OF-BETA-01',
      id_proveedor: 'prov-2',
      proveedor_nombre: 'Distribuidora Beta S.A.',
      estado: 'EVALUADA',
      monto_total: '150.0000',
      tiempo_entrega: '5 días',
      condiciones_pago: 'Contado',
      es_mejor_total: false,
    },
  ],
  productos: [
    {
      id_producto: 'prod-1',
      producto_nombre: 'Resma Carta',
      sku: 'RES-001',
      cantidad_solicitada: '10.0000',
      especificaciones: 'Tamaño carta 75g',
      mejor_precio_unitario: '12.0000',
      cotizaciones: [
        {
          id_oferta: 'ofe-1',
          id_proveedor: 'prov-1',
          proveedor_nombre: 'Suministros Alfa C.A.',
          cantidad: '10.0000',
          precio_unitario: '12.0000',
          subtotal: '120.0000',
          tiempo_entrega: '3 días',
          es_mejor_precio: true,
        },
        {
          id_oferta: 'ofe-2',
          id_proveedor: 'prov-2',
          proveedor_nombre: 'Distribuidora Beta S.A.',
          cantidad: '10.0000',
          precio_unitario: '15.0000',
          subtotal: '150.0000',
          tiempo_entrega: '5 días',
          es_mejor_precio: false,
        },
      ],
    },
  ],
};

function setupDefaultMocks() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.includes('/comparar-ofertas/')) return Promise.resolve(comparativoMock);
    if (url.startsWith('/compras/requisiciones-compra')) {
      return Promise.resolve([reqBorrador, reqPendiente, reqAprobada]);
    }
    if (url.startsWith('/compras/solicitudes-cotizacion')) return Promise.resolve([solicitud1]);
    if (url.startsWith('/compras/ofertas-proveedor')) return Promise.resolve([oferta1]);
    if (url.startsWith('/compras/detalles-oferta-proveedor')) {
      return Promise.resolve([
        {
          id_detalle_oferta: 'det-ofe-1',
          id_oferta: 'ofe-1',
          id_producto: 'prod-1',
          cantidad: '10.0000',
          precio_unitario: '12.0000',
          subtotal: '120.0000',
          observaciones: null,
        },
      ]);
    }
    if (url.startsWith('/proveedores/proveedores')) return Promise.resolve([proveedor1, proveedor2]);
    if (url.startsWith('/almacenes/almacenes')) return Promise.resolve([almacen1]);
    if (url.startsWith('/inventario/productos')) return Promise.resolve([producto1]);
    if (url.startsWith('/core/departamentos')) return Promise.resolve([]);
    return Promise.resolve([]);
  });
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AprovisionamientoPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('AprovisionamientoPage — Flujo transaccional Source-to-PO', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  it('envía a aprobación BORRADOR, confirma PENDIENTE y genera RFQ desde requisiciones APROBADA', async () => {
    vi.mocked(post)
      .mockResolvedValueOnce({ ...reqBorrador, estado: 'PENDIENTE' })
      .mockResolvedValueOnce({ ...reqPendiente, estado: 'APROBADA' })
      .mockResolvedValueOnce({ ...solicitud1, numero_solicitud: 'RFQ-CONS-99' });

    renderPage();

    await screen.findByText('REQ-BOR-01');
    expect(screen.getByLabelText('Seleccionar REQ-BOR-01')).toBeDisabled();
    expect(screen.getByLabelText('Seleccionar REQ-APR-01')).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: 'Enviar a aprobación' }));
    await waitFor(() => {
      expect(post).toHaveBeenCalledWith('/compras/requisiciones-compra/req-borrador/enviar-aprobacion/', {});
    });
    expect(await screen.findByText(/REQ-BOR-01 enviada a aprobación/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Confirmar aprobación' }));
    await waitFor(() => {
      expect(post).toHaveBeenCalledWith('/compras/requisiciones-compra/req-pendiente/confirmar-aprobacion/', {});
    });
    expect(await screen.findByText(/REQ-PEN-01 aprobada/i)).toBeInTheDocument();

    // Seleccionar requisición APROBADA y abrir diálogo Generar RFQ
    fireEvent.click(screen.getByLabelText('Seleccionar REQ-APR-01'));
    const btnGenerarRfq = screen.getByRole('button', { name: 'Generar RFQ' });
    expect(btnGenerarRfq).toBeEnabled();
    fireEvent.click(btnGenerarRfq);

    const dialog = await screen.findByRole('dialog');
    // Validación sin proveedores seleccionados
    fireEvent.click(within(dialog).getByRole('button', { name: 'Generar RFQ' }));
    expect(await within(dialog).findByText(/Seleccione al menos un proveedor/i)).toBeInTheDocument();

    // Seleccionar proveedor, número opcional y observaciones
    fireEvent.click(within(dialog).getByLabelText('Suministros Alfa C.A.'));
    fireEvent.change(within(dialog).getByLabelText(/Número de solicitud/i), {
      target: { value: 'RFQ-CONS-99' },
    });
    fireEvent.change(within(dialog).getByLabelText('Observaciones'), {
      target: { value: 'Urgente compras' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Generar RFQ' }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        '/compras/solicitudes-cotizacion/desde-requisiciones/',
        expect.objectContaining({
          requisicion_ids: ['req-aprobada'],
          proveedores_ids: ['prov-1'],
          numero_solicitud: 'RFQ-CONS-99',
          observaciones: 'Urgente compras',
        }),
      );
    });
    expect(await screen.findByText(/RFQ-CONS-99 generada y enviada/i)).toBeInTheDocument();
  });

  it('abre comparativo lado a lado de ofertas y adjudica parcialmente a Orden de Compra', async () => {
    vi.mocked(post).mockResolvedValueOnce({
      id_orden_compra: 'oc-new-1',
      numero_orden: 'OC-2026-001',
      estado_orden: 'BORRADOR',
      monto_total: '60.0000',
      oferta_id: 'ofe-1',
      oferta_estado: 'ACEPTADA',
      rfq_id: 'rfq-1',
      rfq_estado: 'ENVIADA',
      lineas: 1,
    });

    renderPage();

    fireEvent.click(screen.getByRole('tab', { name: /Solicitudes/i }));
    await screen.findByText('RFQ-001');

    fireEvent.click(screen.getByRole('button', { name: 'Comparar ofertas' }));
    const dialog = await screen.findByRole('dialog');

    expect(await within(dialog).findByText('Suministros Alfa C.A.')).toBeInTheDocument();
    expect(within(dialog).getByText('Mejor total')).toBeInTheDocument();
    expect(within(dialog).getByText('Mejor precio')).toBeInTheDocument();
    expect(within(dialog).getByText('Resma Carta')).toBeInTheDocument();

    // Sin almacén destino → alerta de validación
    fireEvent.click(within(dialog).getByRole('button', { name: 'Adjudicar OF-ALFA-01' }));
    expect(await within(dialog).findByText(/Seleccione el almacén destino/i)).toBeInTheDocument();

    // Seleccionar almacén
    fireEvent.mouseDown(within(dialog).getByLabelText(/Almacén destino/i));
    const listbox = await screen.findByRole('listbox');
    fireEvent.click(within(listbox).getByText('Almacén Central'));

    // Activar adjudicación parcial y validar error si cantidad supera ofertada
    fireEvent.click(within(dialog).getByLabelText(/Adjudicación parcial/i));
    const inputParcial = within(dialog).getByLabelText(/Cant\. parcial \(Resma Carta\)/i);
    fireEvent.change(inputParcial, { target: { value: '25' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Adjudicar OF-ALFA-01' }));
    expect(await within(dialog).findByText(/Las cantidades parciales deben ser mayores a 0/i)).toBeInTheDocument();

    // Ingresar cantidad válida 5 y desmarcar rechazar competidoras
    fireEvent.change(inputParcial, { target: { value: '5' } });
    fireEvent.click(within(dialog).getByLabelText(/Rechazar ofertas competidoras/i));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Adjudicar OF-ALFA-01' }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith('/compras/ofertas-proveedor/ofe-1/adjudicar/', {
        id_almacen_destino: 'alm-1',
        rechazar_competidoras: false,
        adjudicacion_parcial: [{ id_producto: 'prod-1', cantidad: '5.0000' }],
      });
    });
    expect(await screen.findByText(/Orden de compra OC-2026-001 generada en BORRADOR/i)).toBeInTheDocument();
  });

  it('adjudica oferta directamente desde la pestaña Ofertas a Orden de Compra', async () => {
    vi.mocked(post).mockResolvedValueOnce({
      id_orden_compra: 'oc-new-2',
      numero_orden: 'OC-2026-002',
      estado_orden: 'BORRADOR',
      monto_total: '120.0000',
      oferta_id: 'ofe-1',
      oferta_estado: 'ACEPTADA',
      rfq_id: 'rfq-1',
      rfq_estado: 'RESPONDIDA',
      lineas: 1,
    });

    renderPage();

    fireEvent.click(screen.getByRole('tab', { name: /Ofertas/i }));
    await screen.findByText('OF-ALFA-01');

    fireEvent.click(screen.getByRole('button', { name: /Adjudicar → Orden de Compra/i }));
    const dialog = await screen.findByRole('dialog');

    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirmar adjudicación' }));
    expect(await within(dialog).findByText(/Seleccione el almacén destino/i)).toBeInTheDocument();

    fireEvent.mouseDown(within(dialog).getByLabelText(/Almacén destino/i));
    const listbox = await screen.findByRole('listbox');
    fireEvent.click(within(listbox).getByText('Almacén Central'));

    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirmar adjudicación' }));
    await waitFor(() => {
      expect(post).toHaveBeenCalledWith('/compras/ofertas-proveedor/ofe-1/adjudicar/', {
        id_almacen_destino: 'alm-1',
        rechazar_competidoras: true,
      });
    });
    expect(await screen.findByText(/Orden de compra OC-2026-002 generada en BORRADOR/i)).toBeInTheDocument();
  });
});
