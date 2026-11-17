import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

const useAuthMock = vi.fn(() => ({
  user: {
    id: 'u1',
    username: 'ana',
    empresas: [{ id_empresa: 'e1', nombre: 'Empresa 1' }],
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => useAuthMock(),
}));

import { get, post, patch, del } from '../services/api';
import TareasPage from '../pages/Tareas/TareasPage';
import {
  esTareaVencida,
  etiquetaEstadoTarea,
  etiquetaFrecuencia,
  etiquetaOrigenTarea,
  etiquetaPrioridadTarea,
  mensajeTareas,
  parsearLineasMinuta,
} from '../pages/Tareas/utils';

const areaMock = {
  id_area: 'a1',
  id_empresa: 'e1',
  nombre: 'Tesorería',
  slug: 'tesoreria',
  color: '#378ADD',
  departamento: null,
  lider: 'u1',
  lider_nombre: 'Ana Pérez',
  palabras_clave: ['banco', 'conciliación'],
  miembros: [],
  activo: true,
  fecha_creacion: '2026-11-17T10:00:00Z',
  fecha_actualizacion: '2026-11-17T10:00:00Z',
};

const proyectoMock = {
  id_proyecto: 'p1',
  id_empresa: 'e1',
  nombre: 'Tablero Cierre Contable',
  descripcion: 'Cierre mensual',
  color: '#1D9E75',
  vista_predeterminada: 'TABLERO' as const,
  es_personal: false,
  archivado: false,
  area: 'a1',
  area_nombre: 'Tesorería',
  propietario: 'u1',
  propietario_nombre: 'Ana Pérez',
  secciones: [
    {
      id_seccion: 's-pend',
      id_empresa: 'e1',
      proyecto: 'p1',
      nombre: 'Pendiente',
      estado_destino: 'PENDIENTE' as const,
      orden: 0,
      activo: true,
    },
    {
      id_seccion: 's-comp',
      id_empresa: 'e1',
      proyecto: 'p1',
      nombre: 'Completada',
      estado_destino: 'COMPLETADA' as const,
      orden: 4,
      activo: true,
    },
  ],
  activo: true,
  fecha_creacion: '2026-11-17T10:00:00Z',
  fecha_actualizacion: '2026-11-17T10:00:00Z',
};

const tareaMock = {
  id_tarea: 't1',
  id_empresa: 'e1',
  titulo: 'Conciliar Mercantil USD',
  descripcion: 'Revisar extracto bancario',
  estado: 'PENDIENTE' as const,
  prioridad: 'ALTA' as const,
  origen: 'WEB' as const,
  proyecto: 'p1',
  proyecto_nombre: 'Tablero Cierre Contable',
  seccion: 's-pend',
  seccion_nombre: 'Pendiente',
  area: 'a1',
  area_nombre: 'Tesorería',
  tarea_padre: null,
  asignado_a: 'u1',
  asignado_nombre: 'Ana Pérez',
  creado_por: 'u1',
  fecha_inicio: '2026-11-01',
  fecha_vencimiento: '2020-01-01',
  hora_vencimiento: null,
  completada_en: null,
  bloqueada_por_escalacion: true,
  motivo_bloqueo: 'Vencida > 72h',
  entidad_tipo: 'cxc.factura',
  entidad_id: '01950000-0000-7000-8000-000000000001',
  plantilla_recurrente: null,
  minuta_origen: null,
  idempotency_key: '',
  orden_tablero: 1,
  activo: true,
  fecha_creacion: '2026-11-17T10:00:00Z',
  fecha_actualizacion: '2026-11-17T10:00:00Z',
};

const tareaAuxMock = {
  ...tareaMock,
  id_tarea: 't2',
  titulo: 'Descargar movimientos BCV',
  bloqueada_por_escalacion: false,
  motivo_bloqueo: '',
};

const minutaMock = {
  id_minuta: 'm1',
  id_empresa: 'e1',
  titulo: 'Comité Operativo Lunes',
  fecha_reunion: '2026-11-17',
  texto_fuente: 'Revisión semanal de saldos',
  documento_adjunto: null,
  borrador_tareas: [
    {
      indice: 0,
      titulo: 'Enviar corte CxC',
      prioridad: 'URGENTE' as const,
      asignado_nombre: 'Ana Pérez',
      area_id: 'a1',
      area_nombre: 'Tesorería',
      fecha_vencimiento: '2026-11-18',
      incompleto: [],
    },
  ],
  estado: 'BORRADOR' as const,
  creado_por: 'u1',
  confirmada_en: null,
  activo: true,
  fecha_creacion: '2026-11-17T10:00:00Z',
  fecha_actualizacion: '2026-11-17T10:00:00Z',
};

const recurrenteMock = {
  id_plantilla_recurrente: 'r1',
  id_empresa: 'e1',
  titulo: 'Cierre diario de caja',
  descripcion: '',
  prioridad: 'MEDIA' as const,
  frecuencia: 'DIARIA' as const,
  dias_semana: [],
  dia_mes: null,
  horas_dia: [],
  proxima_ejecucion: '2026-11-18',
  ultima_generacion_en: null,
  proyecto: 'p1',
  area: 'a1',
  asignado_a: 'u1',
  asignado_nombre: 'Ana Pérez',
  creado_por: 'u1',
  activo: true,
  fecha_creacion: '2026-11-17T10:00:00Z',
  fecha_actualizacion: '2026-11-17T10:00:00Z',
};

const resumenMock = {
  fecha_corte: '2026-11-17',
  totales: {
    pendientes: 2,
    en_ejecucion: 1,
    en_revision: 0,
    bloqueadas: 1,
    completadas: 3,
    canceladas: 0,
    abiertas: 4,
    vencidas: 1,
    vencen_hoy: 2,
    bloqueadas_por_escalacion: 1,
    completadas_hoy: 3,
  },
  por_area: [{ area_id: 'a1', area_nombre: 'Tesorería', abiertas: 4, vencidas: 1, bloqueadas: 1 }],
  por_responsable: [
    {
      usuario_id: 'u1',
      username: 'ana',
      nombre: 'Ana Pérez',
      abiertas: 4,
      vencidas: 1,
      bloqueadas: 1,
    },
  ],
};

const configMock = {
  id_config_seguimiento: 'cfg1',
  id_empresa: 'e1',
  zona_horaria: 'America/Caracas',
  hora_recordatorio_manana: '09:00:00',
  hora_recordatorio_tarde: '15:00:00',
  hora_reporte_gerencial: '16:00:00',
  horas_bloqueo_vencida: 72,
  gerente: 'u1',
  activo: true,
  fecha_creacion: '2026-11-17T10:00:00Z',
  fecha_actualizacion: '2026-11-17T10:00:00Z',
};

function configurarMocksGet() {
  vi.mocked(get).mockImplementation((url: string) => {
    if (url.startsWith('/tareas/proyectos/')) return Promise.resolve([proyectoMock]);
    if (url.startsWith('/tareas/areas/')) return Promise.resolve([areaMock]);
    if (url.startsWith('/core/usuarios/'))
      return Promise.resolve([
        {
          id: 'u1',
          username: 'ana',
          email: 'ana@omni.test',
          first_name: 'Ana',
          last_name: 'Pérez',
          is_active: true,
          es_superusuario_omni: false,
        },
      ]);
    if (url.startsWith('/tareas/items/t1/comentarios/'))
      return Promise.resolve([
        {
          id_comentario: 'c1',
          id_empresa: 'e1',
          tarea: 't1',
          autor: 'u1',
          autor_nombre: 'Ana Pérez',
          cuerpo: 'Pendiente extracto final',
          es_sistema: false,
          fecha_creacion: '2026-11-17T11:00:00Z',
        },
      ]);
    if (url.startsWith('/tareas/items/t1/dependencias/'))
      return Promise.resolve([
        {
          id_dependencia: 'd1',
          id_empresa: 'e1',
          tarea: 't1',
          depende_de: 't2',
          depende_de_titulo: 'Descargar movimientos BCV',
          depende_de_estado: 'PENDIENTE',
          activo: true,
          fecha_creacion: '2026-11-17T11:00:00Z',
        },
      ]);
    if (url.startsWith('/tareas/items/t1/')) return Promise.resolve(tareaMock);
    if (url.startsWith('/tareas/items/')) return Promise.resolve([tareaMock, tareaAuxMock]);
    if (url.startsWith('/tareas/minutas/')) return Promise.resolve([minutaMock]);
    if (url.startsWith('/tareas/recurrentes/')) return Promise.resolve([recurrenteMock]);
    if (url.startsWith('/tareas/resumen/')) return Promise.resolve(resumenMock);
    if (url.startsWith('/tareas/configuracion/')) return Promise.resolve(configMock);
    return Promise.resolve([]);
  });
}

function renderizarRuta(rutaInicial = '/tareas', qcExterno?: QueryClient) {
  const qc = qcExterno ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[rutaInicial]}>
        <Routes>
          <Route path="/tareas" element={<TareasPage />} />
          <Route path="/tareas/:tareaId" element={<TareasPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('TareasPage y utilidades', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('id_empresa', 'e1');
    configurarMocksGet();
  });

  it('utilidades formatean etiquetas, vencimiento, líneas de minuta y errores JSON', () => {
    expect(etiquetaEstadoTarea('EN_EJECUCION')).toBe('En ejecución');
    expect(etiquetaEstadoTarea('OTRO')).toBe('OTRO');
    expect(etiquetaPrioridadTarea('URGENTE')).toBe('Urgente');
    expect(etiquetaFrecuencia('QUINCENAL')).toBe('Quincenal');
    expect(etiquetaOrigenTarea('MINUTA_IA')).toBe('Minuta IA');
    expect(etiquetaOrigenTarea('RECURRENCIA')).toBe('Recurrente');
    expect(etiquetaOrigenTarea('ERP_EVENTO')).toBe('Evento ERP');

    expect(
      esTareaVencida({ estado: 'PENDIENTE', fecha_vencimiento: '2026-11-10' }, '2026-11-17'),
    ).toBe(true);
    expect(
      esTareaVencida({ estado: 'COMPLETADA', fecha_vencimiento: '2026-11-10' }, '2026-11-17'),
    ).toBe(false);
    expect(esTareaVencida({ estado: 'PENDIENTE', fecha_vencimiento: null }, '2026-11-17')).toBe(
      false,
    );

    const items = parsearLineasMinuta(
      '- Conciliar banco | Ana | mañana | ALTA\n• Revisar saldo | | | DESCONOCIDA\n   ',
    );
    expect(items).toEqual([
      {
        titulo: 'Conciliar banco',
        asignado_nombre: 'Ana',
        fecha_vencimiento: 'mañana',
        prioridad: 'ALTA',
      },
      {
        titulo: 'Revisar saldo',
        prioridad: 'MEDIA',
      },
    ]);

    expect(mensajeTareas(new Error('{"error":"Ciclo detectado"}'), 'Fallback')).toBe(
      'Ciclo detectado',
    );
    expect(mensajeTareas(new Error('{"detail":"No permitido"}'), 'Fallback')).toBe('No permitido');
    const msgAnidado = mensajeTareas(
      new Error('{"horas_dia":{"0":["Formato HH:MM requerido"]},"items_propuestos":[{"titulo":["Requerido"]}]}'),
      'Fallback',
    );
    expect(msgAnidado).toContain('horas_dia: Formato HH:MM requerido');
    expect(msgAnidado).not.toContain('[object Object]');
    expect(mensajeTareas('nada', 'Fallback')).toBe('Fallback');
  });

  it('renderiza Kanban, crea tarea, abre detalle con comentarios/dependencias e inicializa tablero personal', async () => {
    vi.mocked(post).mockResolvedValue(tareaMock);
    renderizarRuta();

    expect(await screen.findByText('Conciliar Mercantil USD')).toBeInTheDocument();
    expect(screen.getAllByText('cxc.factura').length).toBeGreaterThan(0);

    // Asegurar mi tablero personal
    vi.mocked(post).mockResolvedValueOnce({ ...proyectoMock, id_proyecto: 'p-pers' });
    fireEvent.click(screen.getByRole('button', { name: 'Mi tablero personal' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/tareas/proyectos/mi-tablero/', {}),
    );

    // Crear nueva tarea desde Kanban
    fireEvent.click(screen.getByRole('button', { name: 'Nueva tarea' }));
    const dlgNueva = await screen.findByRole('dialog');
    fireEvent.change(within(dlgNueva).getByLabelText(/^Título/), {
      target: { value: 'Validar retenciones IVA' },
    });
    fireEvent.click(within(dlgNueva).getByRole('button', { name: 'Guardar tarea' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/tareas/items/',
        expect.objectContaining({ titulo: 'Validar retenciones IVA' }),
      ),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    // Abrir detalle y publicar comentario + estado
    const botonesDetalle = await screen.findAllByRole('button', { name: 'Detalle' });
    fireEvent.click(botonesDetalle[0]);
    const dlgDetalle = await screen.findByRole('dialog');
    expect(await within(dlgDetalle).findByText('Pendiente extracto final')).toBeInTheDocument();
    expect(
      within(dlgDetalle).getByText(/Depende de: Descargar movimientos BCV/),
    ).toBeInTheDocument();

    fireEvent.change(within(dlgDetalle).getByLabelText('Nuevo comentario'), {
      target: { value: 'Extracto conciliado al 100%' },
    });
    fireEvent.click(within(dlgDetalle).getByRole('button', { name: 'Comentar' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/tareas/items/t1/comentarios/', {
        cuerpo: 'Extracto conciliado al 100%',
      }),
    );

    fireEvent.click(within(dlgDetalle).getByRole('button', { name: 'Marcar completada' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/tareas/items/t1/cambiar-estado/', {
        estado: 'COMPLETADA',
        motivo: '',
      }),
    );
  });

  it('navega por Lista, Minutas, Recurrentes y Resumen Ejecutivo ejecutando sus mutaciones', async () => {
    renderizarRuta();
    await screen.findByText('Conciliar Mercantil USD');

    // Pestaña 1: Lista y Seguimiento (archivar tarea)
    fireEvent.click(screen.getByRole('tab', { name: 'Lista y Seguimiento' }));
    expect(await screen.findByRole('button', { name: 'Solo vencidas' })).toBeInTheDocument();
    const botonesArchivar = await screen.findAllByRole('button', { name: 'Archivar' });
    fireEvent.click(botonesArchivar[0]);
    const dlgArch = await screen.findByRole('dialog');
    vi.mocked(del).mockResolvedValueOnce(undefined);
    fireEvent.click(within(dlgArch).getByRole('button', { name: 'Confirmar archivo' }));
    await waitFor(() => expect(del).toHaveBeenCalledWith('/tareas/items/t1/'));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    // Pestaña 2: Minutas y Acuerdos (crear borrador + confirmar minuta)
    fireEvent.click(screen.getByRole('tab', { name: 'Minutas y Acuerdos' }));
    expect(await screen.findByText('Comité Operativo Lunes')).toBeInTheDocument();
    expect(screen.getByText('Tesorería')).toBeInTheDocument();
    vi.mocked(post).mockResolvedValueOnce({
      minuta: { ...minutaMock, estado: 'CONFIRMADA' },
      tareas_creadas: [tareaMock],
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar y crear tareas' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/tareas/minutas/m1/confirmar/', {}),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Nueva minuta' }));
    const dlgMin = await screen.findByRole('dialog');
    fireEvent.change(within(dlgMin).getByLabelText(/^Título de la reunión/), {
      target: { value: 'Comité Viernes' },
    });
    fireEvent.change(within(dlgMin).getByLabelText(/^Acuerdos propuestos/), {
      target: { value: 'Cerrar libro compras | Ana | viernes | ALTA' },
    });
    vi.mocked(post).mockResolvedValueOnce(minutaMock);
    fireEvent.click(within(dlgMin).getByRole('button', { name: 'Previsualizar borrador' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/tareas/minutas/',
        expect.objectContaining({ titulo: 'Comité Viernes' }),
      ),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

    // Pestaña 3: Recurrentes (materializar + crear)
    fireEvent.click(screen.getByRole('tab', { name: 'Recurrentes' }));
    expect(await screen.findByText('Cierre diario de caja')).toBeInTheDocument();
    vi.mocked(post).mockResolvedValueOnce({
      fecha: '2026-11-17',
      tareas_creadas: 2,
      ids_creadas: ['x', 'y'],
      omitidas_idempotencia: 0,
      errores: 0,
    });
    fireEvent.click(screen.getByRole('button', { name: 'Materializar pendientes de hoy' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/tareas/recurrentes/materializar/', {}),
    );

    // Pestaña 4: Resumen y Equipos (ejecutar ciclo + guardar reglas + crear área)
    fireEvent.click(screen.getByRole('tab', { name: 'Resumen y Equipos' }));
    expect(await screen.findByText('Carga por área operativa')).toBeInTheDocument();
    vi.mocked(post).mockResolvedValueOnce({
      momento: 'MANANA',
      instante: '2026-11-17T09:00:00-04:00',
      alertas_emitidas: 2,
      tareas_bloqueadas: 1,
    });
    fireEvent.click(screen.getByRole('button', { name: 'Ejecutar ciclo de seguimiento' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/tareas/seguimiento/ejecutar/', { momento: 'AUTO' }),
    );
    expect(
      await screen.findByText(
        'Ciclo ejecutado (MANANA): 2 alertas emitidas, 1 tareas bloqueadas automáticamente.',
      ),
    ).toBeInTheDocument();

    vi.mocked(patch).mockResolvedValueOnce(configMock);
    fireEvent.click(screen.getByRole('button', { name: 'Guardar reglas' }));
    await waitFor(() =>
      expect(patch).toHaveBeenCalledWith(
        '/tareas/configuracion/',
        expect.objectContaining({ horas_bloqueo_vencida: 72 }),
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: 'Nueva área operativa' }));
    const dlgArea = await screen.findByRole('dialog');
    fireEvent.change(within(dlgArea).getByLabelText(/^Nombre del área/), {
      target: { value: 'Logística' },
    });
    vi.mocked(post).mockResolvedValueOnce(areaMock);
    fireEvent.click(within(dlgArea).getByRole('button', { name: 'Crear área' }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        '/tareas/areas/',
        expect.objectContaining({ nombre: 'Logística' }),
      ),
    );
  });

  it('abre automáticamente el diálogo de detalle al entrar por enlace profundo /tareas/:tareaId y avisa si falla', async () => {
    const { unmount } = renderizarRuta('/tareas/t1');
    const dlg = await screen.findByRole('dialog');
    expect(within(dlg).getByText('Revisar extracto bancario')).toBeInTheDocument();
    unmount();

    vi.mocked(get).mockImplementation((url: string) => {
      if (url.startsWith('/tareas/items/inexistente/')) {
        return Promise.reject(new Error('{"detail":"No encontrado."}'));
      }
      return Promise.resolve([]);
    });
    renderizarRuta('/tareas/inexistente');
    expect(await screen.findByText('No encontrado.')).toBeInTheDocument();
  });

  it('aísla el caché de tareas entre empresas distintas sobre el mismo QueryClient y usa fallback de AuthContext', async () => {
    const qcCompartido = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 60_000 } },
    });

    localStorage.removeItem('id_empresa');
    useAuthMock.mockReturnValue({
      user: {
        id: 'u1',
        username: 'ana',
        empresas: [{ id_empresa: 'e1', nombre: 'Empresa Alpha' }],
      },
    });
    const vistaE1 = renderizarRuta('/tareas', qcCompartido);
    expect(await screen.findByText('Conciliar Mercantil USD')).toBeInTheDocument();
    vistaE1.unmount();

    // Cambia a empresa e2 (vacía) sobre el mismo QueryClient con staleTime alto: no debe filtrar datos de e1
    localStorage.setItem('id_empresa', 'e2');
    vi.mocked(get).mockResolvedValue([]);
    renderizarRuta('/tareas', qcCompartido);
    expect(
      await screen.findByText('Aún no tienes tableros activos en esta empresa.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Conciliar Mercantil USD')).not.toBeInTheDocument();
    expect(qcCompartido.getQueryData(['tareas', 'e1', 'proyectos', false])).toBeDefined();
    expect(qcCompartido.getQueryData(['tareas', 'e2', 'proyectos', false])).toEqual([]);
  });
});
