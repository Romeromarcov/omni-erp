import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { DispositivoInfo } from '../types/dispositivos';

// ── Mocks ─────────────────────────────────────────────────────────────────────
const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

const loginMock = vi.fn();
const setAuthDispositivoInfoMock = vi.fn();
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    login: loginMock,
    setDispositivoInfo: setAuthDispositivoInfoMock,
    user: null,
    token: null,
    isLoading: false,
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const getMock = vi.fn();
vi.mock('../services/api', () => ({
  get: (...a: unknown[]) => getMock(...a),
  post: vi.fn(),
  patch: vi.fn(),
}));

// DeviceActionModal se simplifica para poder disparar sus callbacks sin red.
vi.mock('../components/DeviceActionModal', () => ({
  DeviceActionModal: ({
    onActionComplete,
    onClose,
    dispositivoInfo,
  }: {
    dispositivoInfo: DispositivoInfo;
    onActionComplete: (success: boolean, info?: DispositivoInfo) => void;
    onClose: () => void;
  }) => (
    <div data-testid="device-modal">
      <button onClick={() => onActionComplete(true, dispositivoInfo)}>completar-accion</button>
      <button onClick={() => onActionComplete(false)}>fallar-accion</button>
      <button onClick={onClose}>cerrar-modal</button>
    </div>
  ),
}));

// Import after mocks
import LoginPage from '../pages/Core/Login/LoginPage';

const EMPRESAS = [
  { id_empresa: 'emp-1', nombre_legal: 'ACME CA' },
  { id_empresa: 'emp-2', nombre_legal: 'Globex CA' },
];
const SUCURSALES = [
  { id_sucursal: 'suc-1', nombre: 'Principal', id_empresa: 'emp-1' },
  { id_sucursal: 'suc-2', nombre: 'Este', id_empresa: 'emp-2' },
];

function setupGetRouting() {
  getMock.mockImplementation((url: string) => {
    // empresas viene paginado ({results}) y sucursales como array plano para
    // cubrir ambas ramas de normalización.
    if (url.includes('/core/empresas/')) return Promise.resolve({ results: EMPRESAS });
    if (url.includes('/core/sucursales/')) return Promise.resolve(SUCURSALES);
    return Promise.resolve([]);
  });
}

function renderLoginPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/login']}>
        <LoginPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function doLogin() {
  fireEvent.change(screen.getByLabelText(/usuario/i), { target: { value: 'user1' } });
  fireEvent.change(screen.getByLabelText(/contraseña/i), { target: { value: 'pass1' } });
  fireEvent.click(screen.getByRole('button', { name: /ingresar/i }));
}

async function selectMuiOption(comboboxIndex: number, optionName: RegExp) {
  const combos = screen.getAllByRole('combobox');
  fireEvent.mouseDown(combos[comboboxIndex]);
  const listbox = await screen.findByRole('listbox');
  fireEvent.click(within(listbox).getByText(optionName));
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    setupGetRouting();
    loginMock.mockResolvedValue(null);
  });

  it('renders login form with username and password fields', () => {
    renderLoginPage();
    expect(screen.getByLabelText(/usuario/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/contraseña/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /ingresar/i })).toBeInTheDocument();
  });

  it('limpia la selección de empresa/sucursal persistida al montar', () => {
    localStorage.setItem('id_empresa', 'emp-x');
    localStorage.setItem('id_sucursal', 'suc-x');
    renderLoginPage();
    expect(localStorage.getItem('id_empresa')).toBeNull();
    expect(localStorage.getItem('id_sucursal')).toBeNull();
  });

  it('shows error message when login fails with bad credentials', async () => {
    loginMock.mockRejectedValue(new Error(JSON.stringify({ error: 'Credenciales inválidas' })));
    renderLoginPage();

    fireEvent.change(screen.getByLabelText(/usuario/i), { target: { value: 'baduser' } });
    fireEvent.change(screen.getByLabelText(/contraseña/i), { target: { value: 'badpass' } });
    fireEvent.click(screen.getByRole('button', { name: /ingresar/i }));

    await waitFor(() => {
      expect(screen.getByText(/credenciales inválidas/i)).toBeInTheDocument();
    });
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it('muestra el error genérico cuando el mensaje del backend no es JSON', async () => {
    loginMock.mockRejectedValue(new Error('boom no-json'));
    renderLoginPage();
    await doLogin();
    await waitFor(() => {
      expect(screen.getByText(/credenciales inválidas/i)).toBeInTheDocument();
    });
  });

  it('flujo completo: login → selección de empresa y sucursal → dashboard', async () => {
    renderLoginPage();
    await doLogin();

    // Paso 2: selección de contexto.
    await screen.findByText(/selecciona empresa y sucursal/i);
    expect(getMock).toHaveBeenCalledWith('/core/empresas/');
    expect(getMock).toHaveBeenCalledWith('/core/sucursales/');

    await selectMuiOption(0, /acme ca/i);
    // La sucursal se filtra por la empresa elegida.
    await selectMuiOption(1, /principal/i);

    fireEvent.click(screen.getByRole('button', { name: /continuar/i }));

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/dashboard'));
    expect(localStorage.getItem('id_empresa')).toBe('emp-1');
    expect(localStorage.getItem('id_sucursal')).toBe('suc-1');
  });

  it('va directo al dashboard cuando el dispositivo abre sesión automáticamente', async () => {
    const dispositivo = {
      accion: 'abrir_sesion_automatico',
      sesion_abierta: { id_sesion: 'ses-1' },
    } as unknown as DispositivoInfo;
    loginMock.mockResolvedValue(dispositivo);
    renderLoginPage();
    await doLogin();

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/dashboard'));
    expect(setAuthDispositivoInfoMock).toHaveBeenCalledWith(dispositivo);
    // No pasa por el paso de selección.
    expect(screen.queryByText(/selecciona empresa y sucursal/i)).not.toBeInTheDocument();
  });

  it('muestra el modal de dispositivo cuando la acción es preguntar_caja y navega al completar', async () => {
    const dispositivo = { accion: 'preguntar_caja' } as unknown as DispositivoInfo;
    loginMock.mockResolvedValue(dispositivo);
    renderLoginPage();
    await doLogin();

    await screen.findByText(/selecciona empresa y sucursal/i);
    fireEvent.click(screen.getByRole('button', { name: /continuar/i }));

    const modal = await screen.findByTestId('device-modal');
    expect(modal).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /completar-accion/i }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/dashboard'));
    expect(setAuthDispositivoInfoMock).toHaveBeenCalledWith(dispositivo);
  });

  it('si la acción del dispositivo falla muestra error pero permite continuar al dashboard', async () => {
    loginMock.mockResolvedValue({ accion: 'abrir_sesion' } as unknown as DispositivoInfo);
    renderLoginPage();
    await doLogin();

    await screen.findByText(/selecciona empresa y sucursal/i);
    fireEvent.click(screen.getByRole('button', { name: /continuar/i }));
    await screen.findByTestId('device-modal');

    fireEvent.click(screen.getByRole('button', { name: /fallar-accion/i }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/dashboard'));
    expect(setAuthDispositivoInfoMock).not.toHaveBeenCalled();
  });

  it('cerrar el modal de dispositivo también navega al dashboard', async () => {
    loginMock.mockResolvedValue({ accion: 'preguntar_caja' } as unknown as DispositivoInfo);
    renderLoginPage();
    await doLogin();

    await screen.findByText(/selecciona empresa y sucursal/i);
    fireEvent.click(screen.getByRole('button', { name: /continuar/i }));
    await screen.findByTestId('device-modal');

    fireEvent.click(screen.getByRole('button', { name: /cerrar-modal/i }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/dashboard'));
  });
});
