import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MfaConfigSection } from '../MfaConfigSection';

const getMfaEstadoMock = vi.fn();
const iniciarMfaMock = vi.fn();
const confirmarMfaMock = vi.fn();
const regenerarCodigosMfaMock = vi.fn();
const desactivarMfaMock = vi.fn();

vi.mock('../../../services/mfa', () => ({
  getMfaEstado: () => getMfaEstadoMock(),
  iniciarMfa: () => iniciarMfaMock(),
  confirmarMfa: (c: string) => confirmarMfaMock(c),
  regenerarCodigosMfa: (c: string) => regenerarCodigosMfaMock(c),
  desactivarMfa: (p: string, c: string) => desactivarMfaMock(p, c),
}));

describe('MfaConfigSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('muestra aviso de política, inicia QR SVG y confirma códigos de respaldo', async () => {
    getMfaEstadoMock
      .mockResolvedValueOnce({
        habilitado: false,
        confirmado_en: null,
        codigos_respaldo_restantes: 0,
        requerido_por_politica: true,
      })
      .mockResolvedValueOnce({
        habilitado: true,
        confirmado_en: '2026-11-22T12:00:00Z',
        codigos_respaldo_restantes: 8,
        requerido_por_politica: true,
      });

    iniciarMfaMock.mockResolvedValue({
      otpauth_uri: 'otpauth://totp/Omni%20ERP:demo?secret=JBSWY3DPEHPK3PXP',
      qr_svg: '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h2v2z"/></svg>',
      secret_manual: 'JBSWY3DPEHPK3PXP',
    });

    confirmarMfaMock.mockResolvedValue({
      habilitado: true,
      confirmado_en: '2026-11-22T12:00:00Z',
      codigos_respaldo: ['AAAA-1111', 'BBBB-2222'],
    });

    render(<MfaConfigSection />);

    expect(await screen.findByText(/exige 2FA activo/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /configurar 2fa/i }));

    const qrImg = await screen.findByAltText('Código QR 2FA');
    expect(qrImg.getAttribute('src')).toMatch(/^data:image\/svg\+xml;base64,/);
    expect(screen.getByDisplayValue('JBSWY3DPEHPK3PXP')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/código de verificación/i), { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: /confirmar y activar 2fa/i }));

    expect(await screen.findByText('AAAA-1111')).toBeInTheDocument();
    expect(screen.getByText('BBBB-2222')).toBeInTheDocument();
  });

  it('permite regenerar códigos y desactivar 2FA cuando ya está activo', async () => {
    getMfaEstadoMock.mockResolvedValue({
      habilitado: true,
      confirmado_en: '2026-11-22T12:00:00Z',
      codigos_respaldo_restantes: 5,
      requerido_por_politica: false,
    });
    regenerarCodigosMfaMock.mockResolvedValue({ codigos_respaldo: ['CCCC-3333'] });
    desactivarMfaMock.mockResolvedValue({ habilitado: false });

    render(<MfaConfigSection />);

    expect(await screen.findByText(/Códigos de respaldo restantes: 5/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /regenerar códigos/i }));
    fireEvent.change(screen.getByLabelText(/código totp actual/i), { target: { value: '654321' } });
    fireEvent.click(screen.getByRole('button', { name: /generar nuevos códigos/i }));

    expect(await screen.findByText('CCCC-3333')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /desactivar 2fa/i }));
    fireEvent.change(screen.getByLabelText(/contraseña actual/i), { target: { value: 'MiPass!' } });
    fireEvent.change(screen.getByLabelText(/código totp o respaldo/i), { target: { value: 'CCCC-3333' } });
    fireEvent.click(screen.getByRole('button', { name: /confirmar desactivación/i }));

    await waitFor(() => {
      expect(desactivarMfaMock).toHaveBeenCalledWith('MiPass!', 'CCCC-3333');
    });
  });
});
