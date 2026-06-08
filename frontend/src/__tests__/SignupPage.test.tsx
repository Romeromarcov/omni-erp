import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const loginMock = vi.fn();
const navigateMock = vi.fn();

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ login: loginMock }),
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock('../services/saasService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/saasService')>();
  return { ...actual, signup: vi.fn() };
});

import { signup } from '../services/saasService';
import SignupPage from '../pages/Core/Signup/SignupPage';

function renderPage() {
  return render(
    <MemoryRouter>
      <SignupPage />
    </MemoryRouter>,
  );
}

describe('SignupPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renderiza el formulario de registro', () => {
    renderPage();
    expect(screen.getByText(/crea tu cuenta/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /crear cuenta y empezar/i })).toBeInTheDocument();
  });

  it('valida que las contraseñas coincidan antes de llamar al backend', async () => {
    renderPage();
    fireEvent.change(screen.getByLabelText(/nombre legal/i), { target: { value: 'Prospecto SA' } });
    fireEvent.change(screen.getByLabelText(/^usuario/i), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText(/^email/i), { target: { value: 'a@b.com' } });
    fireEvent.change(screen.getByLabelText(/^contraseña/i), { target: { value: 'ContraseñaSegura123' } });
    fireEvent.change(screen.getByLabelText(/confirmar contraseña/i), { target: { value: 'otra-distinta' } });

    fireEvent.click(screen.getByRole('button', { name: /crear cuenta y empezar/i }));

    await waitFor(() => {
      expect(screen.getByText(/no coinciden/i)).toBeInTheDocument();
    });
    expect(signup).not.toHaveBeenCalled();
  });

  it('envía el registro y hace auto-login cuando los datos son válidos', async () => {
    vi.mocked(signup).mockResolvedValue({
      empresa_id: 'e1', usuario_id: 'u1', username: 'admin', suscripcion_id: 's1',
      plan: 'Free', estado: 'TRIAL', trial_fin: '2026-07-07',
    });
    loginMock.mockResolvedValue(null);
    renderPage();

    fireEvent.change(screen.getByLabelText(/nombre legal/i), { target: { value: 'Prospecto SA' } });
    fireEvent.change(screen.getByLabelText(/^usuario/i), { target: { value: 'admin' } });
    fireEvent.change(screen.getByLabelText(/^email/i), { target: { value: 'a@b.com' } });
    fireEvent.change(screen.getByLabelText(/^contraseña/i), { target: { value: 'ContraseñaSegura123' } });
    fireEvent.change(screen.getByLabelText(/confirmar contraseña/i), { target: { value: 'ContraseñaSegura123' } });

    fireEvent.click(screen.getByRole('button', { name: /crear cuenta y empezar/i }));

    await waitFor(() => {
      expect(signup).toHaveBeenCalledTimes(1);
      expect(loginMock).toHaveBeenCalledWith('admin', 'ContraseñaSegura123');
      expect(navigateMock).toHaveBeenCalledWith('/dashboard');
    });
  });
});
