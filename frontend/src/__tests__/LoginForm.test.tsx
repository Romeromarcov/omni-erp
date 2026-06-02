import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LoginForm from '../components/LoginForm';

describe('LoginForm (react-hook-form + zod)', () => {
  it('shows per-field errors and does not submit when empty', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<LoginForm onSubmit={onSubmit} />);
    await user.click(screen.getByRole('button', { name: /ingresar/i }));
    await waitFor(() => {
      expect(screen.getByText(/el usuario es obligatorio/i)).toBeInTheDocument();
      expect(screen.getByText(/la contraseña es obligatoria/i)).toBeInTheDocument();
    });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('calls onSubmit once with username and password when valid', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<LoginForm onSubmit={onSubmit} />);
    await user.type(screen.getByLabelText(/usuario/i), 'marco');
    await user.type(screen.getByLabelText(/contraseña/i), 'secret');
    await user.click(screen.getByRole('button', { name: /ingresar/i }));
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });
    expect(onSubmit).toHaveBeenCalledWith('marco', 'secret');
  });
});
