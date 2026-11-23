import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AccessStudioMatrix from '../components/core/AccessStudioMatrix';
import * as accessStudioService from '../services/accessStudio';

vi.mock('../services/accessStudio', async () => {
  const actual = await vi.importActual<typeof import('../services/accessStudio')>('../services/accessStudio');
  return {
    ...actual,
    fetchMatrizRol: vi.fn(),
    guardarMatrizRol: vi.fn(),
    aplicarPlantillaRol: vi.fn(),
  };
});

const mockCatalogo: accessStudioService.CatalogoRbac = {
  modulos: [
    { codigo: 'ventas', etiqueta: 'Ventas' },
    { codigo: 'contabilidad', etiqueta: 'Contabilidad' },
  ],
  acciones: [
    { codigo: 'VER', etiqueta: 'Ver' },
    { codigo: 'CREAR', etiqueta: 'Crear' },
  ],
  ambitos: [
    { codigo: 'FISCAL', etiqueta: 'Fiscal' },
    { codigo: 'GERENCIAL', etiqueta: 'Gerencial' },
    { codigo: 'AMBOS', etiqueta: 'Ambos (Fiscal y Gerencial)' },
  ],
  alcances: [
    { codigo: 'PROPIO', etiqueta: 'Solo registros propios' },
    { codigo: 'EMPRESA', etiqueta: 'Toda la empresa' },
  ],
  campos_sensibles: [
    { codigo: 'costo_unitario', etiqueta: 'Costo unitario', modulo: 'inventario' },
    { codigo: 'margen', etiqueta: 'Margen de ganancia', modulo: 'ventas' },
  ],
  plantillas: [
    {
      codigo: 'CONTADOR_FISCAL',
      nombre: 'Contador Fiscal',
      descripcion: 'Solo ámbito FISCAL',
      total_politicas: 2,
    },
    {
      codigo: 'VENDEDOR',
      nombre: 'Vendedor',
      descripcion: 'Operación comercial propia',
      total_politicas: 2,
    },
  ],
};

function renderWithQuery(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe('AccessStudioMatrix', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(accessStudioService.fetchMatrizRol).mockResolvedValue({
      id_rol: 'rol-1',
      nombre_rol: 'Vendedor Senior',
      id_empresa: 'emp-1',
      politicas: [
        {
          id_politica: 'pol-1',
          modulo: 'ventas',
          accion: 'VER',
          ambito: 'FISCAL',
          alcance: 'EMPRESA',
          permitido: true,
          campos_ocultos: [],
        },
      ],
      permisos_asignados: [],
      catalogo: mockCatalogo,
    });
    vi.mocked(accessStudioService.guardarMatrizRol).mockResolvedValue({
      id_rol: 'rol-1',
      id_empresa: 'emp-1',
      politicas: [],
    });
    vi.mocked(accessStudioService.aplicarPlantillaRol).mockResolvedValue({
      id_rol: 'rol-1',
      id_empresa: 'emp-1',
      codigo_plantilla: 'CONTADOR_FISCAL',
      politicas: [
        {
          id_politica: 'pol-f1',
          modulo: 'contabilidad',
          accion: 'VER',
          ambito: 'FISCAL',
          alcance: 'EMPRESA',
          permitido: true,
          campos_ocultos: [],
        },
      ],
    });
  });

  it('carga la matriz, permite editar permisos/campos sensibles y guardar via PUT', async () => {
    renderWithQuery(<AccessStudioMatrix idRol="rol-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('access-studio-matrix')).toBeInTheDocument();
    });

    // Activar permiso Crear en ventas
    const toggleCrear = screen.getByLabelText('Permitir ventas CREAR') as HTMLInputElement;
    expect(toggleCrear.checked).toBe(false);
    fireEvent.click(toggleCrear);
    expect(toggleCrear.checked).toBe(true);

    // Ocultar campo sensible costo_unitario en ventas:VER
    fireEvent.click(screen.getByTestId('chip-ventas-VER-costo_unitario'));

    // Cambiar ámbito y alcance en ventas:VER via listbox de MUI
    fireEvent.mouseDown(screen.getByTestId('ambito-ventas-VER'));
    fireEvent.click(await screen.findByRole('option', { name: 'Gerencial' }));

    fireEvent.mouseDown(screen.getByTestId('alcance-ventas-VER'));
    fireEvent.click(await screen.findByRole('option', { name: 'Solo registros propios' }));

    // Guardar matriz
    fireEvent.click(screen.getByTestId('access-studio-save'));

    await waitFor(() => {
      expect(accessStudioService.guardarMatrizRol).toHaveBeenCalledTimes(1);
    });

    const [rolArg, payloadArg] = vi.mocked(accessStudioService.guardarMatrizRol).mock.calls[0];
    expect(rolArg).toBe('rol-1');
    expect(payloadArg.id_empresa).toBe('emp-1');
    expect(payloadArg.politicas).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          modulo: 'ventas',
          accion: 'VER',
          ambito: 'GERENCIAL',
          alcance: 'PROPIO',
          permitido: true,
          campos_ocultos: ['costo_unitario'],
        }),
        expect.objectContaining({
          modulo: 'ventas',
          accion: 'CREAR',
          permitido: true,
        }),
      ]),
    );
    expect(await screen.findByTestId('access-studio-feedback')).toHaveTextContent(
      'Matriz RBAC/ABAC guardada correctamente.',
    );
  });

  it('aplica plantilla predefinida y actualiza el feedback', async () => {
    renderWithQuery(<AccessStudioMatrix idRol="rol-1" />);

    await waitFor(() => {
      expect(screen.getByTestId('preset-btn-CONTADOR_FISCAL')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('preset-btn-CONTADOR_FISCAL'));

    await waitFor(() => {
      expect(accessStudioService.aplicarPlantillaRol).toHaveBeenCalledWith(
        'rol-1',
        'CONTADOR_FISCAL',
        'emp-1',
      );
    });

    expect(await screen.findByTestId('access-studio-feedback')).toHaveTextContent(
      'Plantilla CONTADOR_FISCAL aplicada.',
    );
  });
});
