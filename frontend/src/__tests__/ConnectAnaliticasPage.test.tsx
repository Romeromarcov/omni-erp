import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  API_URL: '/api',
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  fetchBlob: vi.fn(),
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'emp-1' }));

import { get, post } from '../services/api';
import ConnectAnaliticasPage from '../pages/Connect/ConnectAnaliticasPage';
import { connectRoutes } from '../routes/connectRoutes';
import { buildNavigation } from '../config/navigation';
import {
  calificarLeadConnect,
  getAnaliticasConnect,
  proponerSeguimientoConnect,
  type ConnectAnaliticasResponse,
  type ConnectPerfil,
} from '../services/connectService';

const perfilesFixture: ConnectPerfil[] = [
  {
    id_perfil: 'perf-1',
    id_empresa: 'emp-1',
    usuario: 'usr-1',
    slug: 'ana-gomez',
    nombre_publico: 'Ana Gómez',
    cargo: 'Gerente Comercial',
    bio: '',
    telefono_publico: '',
    email_publico: 'ana@omni.com',
    tema: 'CORPORATIVO',
    botones: [],
    plantilla_bloqueada: false,
    activo: true,
    fecha_creacion: '2026-11-01T10:00:00Z',
    fecha_actualizacion: '2026-11-01T10:00:00Z',
  },
];

const analiticas30Fixture: ConnectAnaliticasResponse = {
  periodo: { desde: '2026-10-23', hasta: '2026-11-21', dias: 30 },
  perfil_id: null,
  total_toques: 120,
  visitantes_unicos: 85,
  total_leads: 24,
  leads_convertidos: 6,
  tasa_conversion_pct: '20.00',
  tasa_cierre_pct: '25.00',
  por_origen: { NFC: 70, QR: 30, ENLACE: 20 },
  por_dispositivo: { IOS: 60, ANDROID: 40, ESCRITORIO: 15, OTRO: 5 },
  serie_diaria: [
    { fecha: '2026-11-20', toques: 50, leads: 10 },
    { fecha: '2026-11-21', toques: 70, leads: 14 },
  ],
  top_perfiles: [
    {
      id_perfil: 'perf-1',
      slug: 'ana-gomez',
      nombre_publico: 'Ana Gómez',
      toques: 90,
      visitantes_unicos: 64,
      leads: 18,
      leads_convertidos: 5,
      tasa_conversion_pct: '20.00',
    },
  ],
};

const analiticas7Fixture: ConnectAnaliticasResponse = {
  ...analiticas30Fixture,
  periodo: { desde: '2026-11-15', hasta: '2026-11-21', dias: 7 },
  total_toques: 32,
  visitantes_unicos: 28,
  total_leads: 8,
  leads_convertidos: 2,
  tasa_conversion_pct: '25.00',
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ConnectAnaliticasPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ConnectAnaliticasPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('carga KPIs, desglose por origen/dispositivo, top perfiles y serie diaria', async () => {
    vi.mocked(get).mockImplementation(async (url: string) => {
      if (url.startsWith('/connect/perfiles/')) return { results: perfilesFixture };
      return analiticas30Fixture;
    });

    renderPage();

    expect(await screen.findByText('120')).toBeInTheDocument();
    expect(screen.getByText('85')).toBeInTheDocument();
    expect(screen.getByText('24')).toBeInTheDocument();
    expect(screen.getByText('6')).toBeInTheDocument();
    expect(screen.getAllByText('20.00%').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Tasa de cierre: 25.00%/i)).toBeInTheDocument();

    expect(screen.getByText('Tarjeta NFC')).toBeInTheDocument();
    expect(screen.getByText('Código QR')).toBeInTheDocument();
    expect(screen.getByText('Enlace directo')).toBeInTheDocument();
    expect(screen.getByText('iOS')).toBeInTheDocument();
    expect(screen.getByText('Android')).toBeInTheDocument();
    expect(screen.getByText('Escritorio')).toBeInTheDocument();

    expect(screen.getByText('Ana Gómez')).toBeInTheDocument();
    expect(screen.getByText('/c/ana-gomez')).toBeInTheDocument();
    expect(screen.getByText('2026-11-20')).toBeInTheDocument();
    expect(screen.getByText('2026-11-21')).toBeInTheDocument();

    expect(get).toHaveBeenCalledWith('/connect/analiticas/?empresa_id=emp-1&dias=30');
  });

  it('cambia el periodo entre 7, 30 y 90 días y filtra por perfil', async () => {
    vi.mocked(get).mockImplementation(async (url: string) => {
      if (url.startsWith('/connect/perfiles/')) return perfilesFixture;
      if (url.includes('dias=7')) return analiticas7Fixture;
      return analiticas30Fixture;
    });

    renderPage();
    expect(await screen.findByText('120')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '7 días' }));
    expect(await screen.findByText('32')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/connect/analiticas/?empresa_id=emp-1&dias=7');

    fireEvent.click(screen.getByRole('button', { name: '90 días' }));
    await waitFor(() => {
      expect(get).toHaveBeenCalledWith('/connect/analiticas/?empresa_id=emp-1&dias=90');
    });

    // Filtrar por perfil específico
    fireEvent.mouseDown(screen.getByLabelText(/^perfil$/i));
    fireEvent.click(await screen.findByRole('option', { name: /Ana Gómez/i }));
    await waitFor(() => {
      expect(get).toHaveBeenCalledWith('/connect/analiticas/?empresa_id=emp-1&dias=90&perfil_id=perf-1');
    });
  });

  it('muestra alerta de error cuando falla la API y permite reintentar', async () => {
    let attempts = 0;
    vi.mocked(get).mockImplementation(async (url: string) => {
      if (url.startsWith('/connect/perfiles/')) return [];
      attempts += 1;
      if (attempts === 1) {
        throw Object.assign(new Error('Error del servidor de analíticas'), { status: 500 });
      }
      return {
        ...analiticas30Fixture,
        total_toques: 0,
        visitantes_unicos: 0,
        total_leads: 0,
        leads_convertidos: 0,
        tasa_conversion_pct: '0.00',
        tasa_cierre_pct: '0.00',
        por_origen: {},
        por_dispositivo: {},
        serie_diaria: [],
        top_perfiles: [],
      };
    });

    renderPage();

    expect(await screen.findByRole('alert')).toHaveTextContent('Error del servidor de analíticas');

    fireEvent.click(screen.getByRole('button', { name: /reintentar/i }));

    expect(await screen.findByText('Sin datos de origen en este periodo.')).toBeInTheDocument();
    expect(screen.getByText('Sin datos de dispositivos en este periodo.')).toBeInTheDocument();
    expect(screen.getByText('Sin actividad de perfiles en el periodo seleccionado.')).toBeInTheDocument();
    expect(screen.getByText('No hay registros diarios en el periodo seleccionado.')).toBeInTheDocument();
  });

  it('expone rutas/navegación de Omni Connect y helpers de servicio S10/S12', async () => {
    const sections = buildNavigation('emp-1', { esSuperusuarioOmni: false });
    const connectSec = sections.find((s) => s.id === 'connect');
    expect(connectSec?.items?.map((i) => i.path)).toEqual([
      '/connect/perfil',
      '/connect/tarjetas',
      '/connect/analiticas',
    ]);

    vi.mocked(get).mockImplementation(async (url: string) => {
      if (url.startsWith('/connect/perfiles/')) return [];
      return analiticas30Fixture;
    });
    vi.mocked(post).mockResolvedValue({
      id_ejecucion: 'ej-1',
      agente: 'connect_calificador',
      estado: 'pendiente',
    });

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/connect/analiticas']}>
          <Routes>{connectRoutes()}</Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole('heading', { name: /analíticas omni connect/i })).toBeInTheDocument();

    await getAnaliticasConnect({ desde: '2026-11-01', hasta: '2026-11-21' });
    expect(get).toHaveBeenCalledWith('/connect/analiticas/?desde=2026-11-01&hasta=2026-11-21');

    await calificarLeadConnect('lead-1');
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/calificar-lead-connect/', {
      lead_id: 'lead-1',
    });

    await proponerSeguimientoConnect('lead-1');
    expect(post).toHaveBeenCalledWith('/agentes/predicciones/proponer-seguimiento-connect/', {
      lead_id: 'lead-1',
    });
  });
});
