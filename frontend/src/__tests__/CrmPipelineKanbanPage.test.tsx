import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));
vi.mock('../utils/empresa', () => ({ getEmpresaId: () => 'emp-1' }));

import { get, post, patch } from '../services/api';
import { buildNavigation } from '../config/navigation';
import { crmKeys } from '../lib/queryKeys';
import { crmRoutes } from '../routes/crmRoutes';
import { crmCrmService } from '../services/crmCrmService';
import CrmPipelineKanbanPage from '../pages/CRM/CrmPipelineKanbanPage';

const etapaNuevo = {
  id_etapa: 'et-1',
  id_empresa: 'emp-1',
  pipeline: 'pipe-1',
  nombre: 'Nuevo',
  orden: 1,
  tipo: 'ABIERTA' as const,
  activo: true,
};

const etapaContactado = {
  id_etapa: 'et-2',
  id_empresa: 'emp-1',
  pipeline: 'pipe-1',
  nombre: 'Contactado',
  orden: 2,
  tipo: 'ABIERTA' as const,
  activo: true,
};

const etapaGanado = {
  id_etapa: 'et-3',
  id_empresa: 'emp-1',
  pipeline: 'pipe-1',
  nombre: 'Ganado',
  orden: 3,
  tipo: 'GANADA' as const,
  activo: true,
};

const etapaPerdido = {
  id_etapa: 'et-4',
  id_empresa: 'emp-1',
  pipeline: 'pipe-1',
  nombre: 'Perdido',
  orden: 4,
  tipo: 'PERDIDA' as const,
  activo: true,
};

const pipelineMock = {
  id_pipeline: 'pipe-1',
  id_empresa: 'emp-1',
  nombre: 'Ventas Connect',
  es_predeterminado: true,
  activo: true,
  etapas: [etapaNuevo, etapaContactado, etapaGanado, etapaPerdido],
};

const pipelineSecundarioMock = {
  id_pipeline: 'pipe-2',
  id_empresa: 'emp-1',
  nombre: 'Corporativo',
  es_predeterminado: false,
  activo: true,
  etapas: [
    {
      id_etapa: 'et-20',
      id_empresa: 'emp-1',
      pipeline: 'pipe-2',
      nombre: 'Calificación',
      orden: 1,
      tipo: 'ABIERTA' as const,
      activo: true,
    },
  ],
};

const leadMock = {
  id_lead: 'lead-1',
  id_empresa: 'emp-1',
  nombre: 'Ana',
  apellido: 'Martínez',
  empresa_nombre: 'Tech Norte C.A.',
  email: 'ana@technorte.test',
  telefono: '+584121234567',
  mensaje: 'Solicita demo NFC',
  fuente: 'NFC' as const,
  pipeline: 'pipe-1',
  pipeline_nombre: 'Ventas Connect',
  etapa: 'et-1',
  etapa_nombre: 'Nuevo',
  etapa_tipo: 'ABIERTA',
  propietario: 'usr-1',
  propietario_nombre: 'Carlos Vendedor',
  actividades_pendientes: 1,
  actividades_vencidas: 1,
  activo: true,
};

const actividadPendienteMock = {
  id_actividad: 'act-1',
  id_empresa: 'emp-1',
  lead: 'lead-1',
  lead_nombre: 'Ana Martínez',
  tipo: 'LLAMADA' as const,
  asunto: 'Llamada inicial',
  descripcion: 'Confirmar presupuesto',
  fecha_vencimiento: '2026-11-22T14:00:00Z',
  completada: false,
  fecha_completada: null,
  asignado_a: 'usr-1',
  asignado_a_nombre: 'Carlos Vendedor',
  activo: true,
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CrmPipelineKanbanPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockApiDefault(opts?: { pipelines?: unknown[]; leads?: unknown[]; actividades?: unknown[] }) {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/crm/pipelines/')) {
      return Promise.resolve(opts?.pipelines ?? [pipelineMock, pipelineSecundarioMock]);
    }
    if (url.startsWith('/crm/leads/')) {
      return Promise.resolve(opts?.leads ?? [leadMock]);
    }
    if (url.startsWith('/crm/actividades/')) {
      return Promise.resolve(opts?.actividades ?? [actividadPendienteMock]);
    }
    return Promise.resolve([]);
  });
}

describe('CrmPipelineKanbanPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiDefault();
  });

  it('muestra estado vacío e inicializa el pipeline predeterminado cuando no hay pipelines', async () => {
    mockApiDefault({ pipelines: [] });
    vi.mocked(post).mockResolvedValueOnce(pipelineMock);

    renderPage();

    expect(
      await screen.findByText(/aún no hay pipelines configurados en esta empresa/i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /inicializar pipeline predeterminado/i }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/crm/pipelines/asegurar-predeterminado/', {
        id_empresa: 'emp-1',
      }),
    );
  });

  it('carga columnas por etapa ordenadas, tarjetas de lead y permite mover de etapa por selector y drag-and-drop', async () => {
    renderPage();

    expect(await screen.findByText('Ana Martínez')).toBeInTheDocument();
    expect(screen.getByText('Tech Norte C.A.')).toBeInTheDocument();
    expect(screen.getByText('NFC')).toBeInTheDocument();
    expect(screen.getByText('Carlos Vendedor')).toBeInTheDocument();
    expect(screen.getByText('1 act.')).toBeInTheDocument();
    expect(screen.getByText('1 venc.')).toBeInTheDocument();
    expect(screen.getByText('Ganado')).toBeInTheDocument();
    expect(screen.getByText('Perdido')).toBeInTheDocument();

    // Mover etapa vía selector rápido en tarjeta
    vi.mocked(post).mockResolvedValueOnce({
      ...leadMock,
      etapa: 'et-2',
      etapa_nombre: 'Contactado',
    });

    const moverInput = screen.getByLabelText('Mover a etapa');
    fireEvent.mouseDown(moverInput);
    fireEvent.click(await screen.findByRole('option', { name: 'Contactado' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/crm/leads/lead-1/mover-etapa/', { etapa: 'et-2' }),
    );

    // Mover etapa vía drag-and-drop hacia columna Ganado
    vi.mocked(post).mockResolvedValueOnce({
      ...leadMock,
      etapa: 'et-3',
      etapa_nombre: 'Ganado',
    });
    const colGanado = screen.getByTestId('kanban-col-et-3');
    const cardTitle = screen.getByText('Ana Martínez');
    fireEvent.dragStart(cardTitle.closest('[draggable="true"]')!, {
      dataTransfer: { setData: vi.fn(), getData: () => 'lead-1' },
    });
    fireEvent.dragOver(colGanado);
    fireEvent.drop(colGanado, {
      dataTransfer: { getData: () => 'lead-1' },
    });

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/crm/leads/lead-1/mover-etapa/', { etapa: 'et-3' }),
    );
  });

  it('permite crear un lead manual desde el diálogo validando nombre obligatorio', async () => {
    renderPage();
    await screen.findByText('Ana Martínez');

    fireEvent.click(screen.getByRole('button', { name: 'Nuevo lead' }));
    const dialog = await screen.findByRole('dialog');

    // Intento sin nombre muestra validación cliente sin POST
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar lead' }));
    expect(
      await within(dialog).findByText('El nombre del lead es obligatorio.'),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();

    vi.mocked(post).mockResolvedValueOnce({
      ...leadMock,
      id_lead: 'lead-2',
      nombre: 'Pedro',
      apellido: 'Pérez',
      fuente: 'MANUAL',
    });

    fireEvent.change(within(dialog).getByLabelText(/^Nombre/), { target: { value: 'Pedro' } });
    fireEvent.change(within(dialog).getByLabelText(/^Apellido/), { target: { value: 'Pérez' } });
    fireEvent.change(within(dialog).getByLabelText(/^Empresa/), { target: { value: 'Pérez LLC' } });
    fireEvent.change(within(dialog).getByLabelText(/^Correo electrónico/), {
      target: { value: 'pedro@perez.test' },
    });
    fireEvent.change(within(dialog).getByLabelText(/^Teléfono/), {
      target: { value: '+584140001122' },
    });
    fireEvent.change(within(dialog).getByLabelText(/^Notas \/ Mensaje/), {
      target: { value: 'Referido' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar lead' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/crm/leads/',
        expect.objectContaining({
          id_empresa: 'emp-1',
          nombre: 'Pedro',
          apellido: 'Pérez',
          empresa_nombre: 'Pérez LLC',
          email: 'pedro@perez.test',
          telefono: '+584140001122',
          mensaje: 'Referido',
          fuente: 'MANUAL',
          pipeline: 'pipe-1',
          etapa: 'et-1',
        }),
      ),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('abre el detalle del lead, registra una actividad y la marca completada', async () => {
    renderPage();
    await screen.findByText('Ana Martínez');

    fireEvent.click(screen.getByRole('button', { name: 'Detalle' }));

    expect(await screen.findByText('Llamada inicial')).toBeInTheDocument();
    expect(screen.getByText('Correo: ana@technorte.test')).toBeInTheDocument();
    expect(screen.getByText('Teléfono: +584121234567')).toBeInTheDocument();

    // Validación de asunto requerido
    fireEvent.click(screen.getByRole('button', { name: 'Registrar actividad' }));
    expect(await screen.findByText('El asunto de la actividad es obligatorio.')).toBeInTheDocument();

    // Crear actividad tipo WHATSAPP con vencimiento
    vi.mocked(post).mockResolvedValueOnce({
      ...actividadPendienteMock,
      id_actividad: 'act-2',
      tipo: 'WHATSAPP',
      asunto: 'Enviar propuesta WhatsApp',
    });

    fireEvent.mouseDown(screen.getByLabelText('Tipo de actividad'));
    fireEvent.click(await screen.findByRole('option', { name: 'WhatsApp' }));
    fireEvent.change(screen.getByLabelText(/^Asunto/), {
      target: { value: 'Enviar propuesta WhatsApp' },
    });
    fireEvent.change(screen.getByLabelText(/^Descripción/), {
      target: { value: 'Plan corporativo' },
    });
    fireEvent.change(screen.getByLabelText(/^Fecha de vencimiento/), {
      target: { value: '2026-12-01T10:30' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Registrar actividad' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/crm/actividades/',
        expect.objectContaining({
          id_empresa: 'emp-1',
          lead: 'lead-1',
          tipo: 'WHATSAPP',
          asunto: 'Enviar propuesta WhatsApp',
          descripcion: 'Plan corporativo',
        }),
      ),
    );

    // Completar actividad existente
    vi.mocked(post).mockResolvedValueOnce({
      ...actividadPendienteMock,
      completada: true,
      fecha_completada: '2026-11-21T20:00:00Z',
    });
    fireEvent.click(screen.getByRole('button', { name: 'Completar' }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/crm/actividades/act-1/completar/', { completada: true }),
    );

    // Cerrar drawer
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar detalle' }));
    await waitFor(() =>
      expect(screen.queryByText('Registrar actividad')).not.toBeInTheDocument(),
    );
  });

  it('filtra por búsqueda/fuente, cambia de pipeline, expone ruta /crm/pipeline, navegación y servicio CRM', async () => {
    const sections = buildNavigation('emp-1', { esSuperusuarioOmni: false });
    const crmSec = sections.find((s) => s.id === 'crm');
    expect(crmSec?.items).toEqual(
      expect.arrayContaining([
        { label: 'Clientes', path: '/crm/clientes' },
        { label: 'Pipeline Kanban', path: '/crm/pipeline' },
      ]),
    );

    expect(crmKeys.etapas('emp-1', 'pipe-1')).toEqual(['crm', 'etapas', 'emp-1', 'pipe-1']);

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={['/crm/pipeline']}>
          <Routes>{crmRoutes()}</Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Ana Martínez')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Buscar leads'), { target: { value: 'Norte' } });
    fireEvent.mouseDown(screen.getByLabelText('Fuente'));
    fireEvent.click(await screen.findByRole('option', { name: 'Tarjeta NFC' }));

    await waitFor(() =>
      expect(get).toHaveBeenCalledWith(
        expect.stringContaining('/crm/leads/?empresa=emp-1&pipeline=pipe-1&fuente=NFC&search=Norte'),
      ),
    );

    // Cambiar pipeline
    fireEvent.mouseDown(screen.getByLabelText('Pipeline'));
    fireEvent.click(await screen.findByRole('option', { name: 'Corporativo' }));
    expect(await screen.findByText('Calificación')).toBeInTheDocument();

    // Cubrir endpoints restantes de crmCrmService
    vi.mocked(post).mockResolvedValue({});
    vi.mocked(patch).mockResolvedValue({});
    await crmCrmService.createPipeline({ nombre: 'Nuevo' });
    await crmCrmService.reordenarEtapas('pipe-1', ['et-2', 'et-1']);
    await crmCrmService.getEtapas({ empresa: 'emp-1', pipeline: 'pipe-1' });
    await crmCrmService.createEtapa({ pipeline: 'pipe-1', nombre: 'Demo' });
    await crmCrmService.updateLead('lead-1', { apellido: 'Actualizado' });
    await crmCrmService.completarActividad('act-1', false, 'Reabierta');

    expect(post).toHaveBeenCalledWith('/crm/pipelines/', { nombre: 'Nuevo' });
    expect(post).toHaveBeenCalledWith('/crm/pipelines/pipe-1/reordenar-etapas/', {
      etapas: ['et-2', 'et-1'],
    });
    expect(get).toHaveBeenCalledWith('/crm/etapas/?empresa=emp-1&pipeline=pipe-1');
    expect(post).toHaveBeenCalledWith('/crm/etapas/', { pipeline: 'pipe-1', nombre: 'Demo' });
    expect(patch).toHaveBeenCalledWith('/crm/leads/lead-1/', { apellido: 'Actualizado' });
    expect(post).toHaveBeenCalledWith('/crm/actividades/act-1/completar/', {
      completada: false,
      descripcion: 'Reabierta',
    });
  });

  it('muestra alerta de error cuando leadsQuery falla y no renderiza columnas vacías falsas', async () => {
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/crm/pipelines/')) {
        return Promise.resolve([pipelineMock]);
      }
      if (url.startsWith('/crm/leads/')) {
        return Promise.reject(new Error('Fallo de red cargando leads'));
      }
      return Promise.resolve([]);
    });

    renderPage();

    expect(await screen.findByText('Fallo de red cargando leads')).toBeInTheDocument();
    expect(screen.queryByText('Sin leads en esta etapa.')).not.toBeInTheDocument();
  });

  it('reinicia el borrador del formulario de actividad al cerrar el detalle o cambiar de lead', async () => {
    const leadSegundo = {
      ...leadMock,
      id_lead: 'lead-2',
      nombre: 'Luis',
      apellido: 'Rojas',
      empresa_nombre: 'Rojas Imports',
    };
    mockApiDefault({ leads: [leadMock, leadSegundo], actividades: [] });

    renderPage();
    await screen.findByText('Ana Martínez');
    await screen.findByText('Luis Rojas');

    const botonesDetalle = screen.getAllByRole('button', { name: 'Detalle' });
    fireEvent.click(botonesDetalle[0]);
    expect(
      await screen.findByRole('button', { name: 'Registrar actividad' }),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/^Asunto/), { target: { value: 'Borrador lead 1' } });
    fireEvent.change(screen.getByLabelText(/^Descripción/), { target: { value: 'Nota sin guardar' } });

    fireEvent.click(screen.getByRole('button', { name: 'Cerrar detalle' }));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Registrar actividad' })).not.toBeInTheDocument(),
    );

    // Abrir el segundo lead debe iniciar con el formulario completamente vacío
    fireEvent.click(screen.getAllByRole('button', { name: 'Detalle' })[1]);
    expect(
      await screen.findByRole('button', { name: 'Registrar actividad' }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/^Asunto/)).toHaveValue('');
    expect(screen.getByLabelText(/^Descripción/)).toHaveValue('');
  });

  it('recorre todas las páginas DRF cuando el pipeline supera 20 leads y advierte si queda truncado', async () => {
    const leadPag2 = {
      ...leadMock,
      id_lead: 'lead-21',
      nombre: 'María',
      apellido: 'Cárdenas',
      empresa_nombre: 'Cárdenas C.A.',
    };
    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/crm/pipelines/')) {
        return Promise.resolve([pipelineMock]);
      }
      if (url.includes('page=2')) {
        return Promise.resolve({
          count: 21,
          next: null,
          previous: '/crm/leads/?pipeline=pipe-1',
          results: [leadPag2],
        });
      }
      if (url.startsWith('/crm/leads/')) {
        return Promise.resolve({
          count: 21,
          next: '/crm/leads/?pipeline=pipe-1&page=2',
          previous: null,
          results: [leadMock],
        });
      }
      return Promise.resolve([]);
    });

    renderPage();

    expect(await screen.findByText('Ana Martínez')).toBeInTheDocument();
    expect(await screen.findByText('María Cárdenas')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(expect.stringContaining('page=2'));

    // Si el límite de páginas no alcanza para `next`, reporta truncado y alerta en el Kanban
    const todosLeads = await crmCrmService.getLeads({ empresa: 'emp-1', pipeline: 'pipe-1' });
    expect(todosLeads).toHaveLength(2);
    const truncadoRes = await crmCrmService.getLeadsKanban({ empresa: 'emp-1', pipeline: 'pipe-1' }, 1);
    expect(truncadoRes.truncado).toBe(true);
    expect(truncadoRes.total).toBe(21);

    const spyKanban = vi.spyOn(crmCrmService, 'getLeadsKanban').mockResolvedValueOnce({
      items: [leadMock],
      total: 520,
      truncado: true,
    });
    renderPage();
    expect(
      await screen.findByText(/Se muestran los primeros 1 de 520 leads del pipeline/i),
    ).toBeInTheDocument();
    spyKanban.mockRestore();
  });
});
