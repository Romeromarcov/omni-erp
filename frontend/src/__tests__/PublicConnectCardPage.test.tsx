import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import PublicConnectCardPage from '../pages/Connect/PublicConnectCardPage';
import {
  buildHrefSeguro,
  getPublicProfile,
  getPublicVCardUrl,
  submitPublicLead,
} from '../services/connectService';

function renderPublicCard(initialEntry = '/c/juan-perez') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/c/:slug" element={<PublicConnectCardPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const sampleProfile = {
  slug: 'juan-perez',
  nombre_publico: 'Juan Pérez',
  cargo: 'Director Comercial',
  bio: 'Conectando negocios.',
  telefono_publico: '+584141234567',
  email_publico: 'juan@acme.com',
  tema: 'MODERNO',
  botones: [
    { tipo: 'web', etiqueta: 'Sitio web', valor: 'https://acme.com' },
    { tipo: 'whatsapp', etiqueta: 'WhatsApp', valor: '+584141234567' },
    { tipo: 'web', etiqueta: 'Enlace malicioso', valor: 'javascript:alert(1)' },
  ],
  empresa_nombre: 'ACME Venezuela',
  acepta_leads: true,
  consentimiento_texto: 'Acepto el uso de mis datos para contacto comercial.',
};

describe('connectService (público y validación de botones)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('valida esquemas permitidos y bloquea URLs peligrosas', () => {
    expect(buildHrefSeguro({ tipo: 'web', valor: 'https://omni.link/hola' })).toBe(
      'https://omni.link/hola',
    );
    expect(buildHrefSeguro({ tipo: 'web', valor: 'javascript:alert(1)' })).toBeNull();
    expect(buildHrefSeguro({ tipo: 'web', valor: 'data:text/html,<script>' })).toBeNull();
    expect(buildHrefSeguro({ tipo: 'web', valor: 'not a valid url' })).toBeNull();
    expect(buildHrefSeguro({ tipo: 'whatsapp', valor: '+58 (414) 123-4567' })).toBe(
      'https://wa.me/584141234567',
    );
    expect(buildHrefSeguro({ tipo: 'whatsapp', valor: 'abc' })).toBeNull();
    expect(buildHrefSeguro({ tipo: 'telefono', valor: '+58 414-1234567' })).toBe(
      'tel:+584141234567',
    );
    expect(buildHrefSeguro({ tipo: 'correo', valor: 'hola@omni.com' })).toBe(
      'mailto:hola@omni.com',
    );
    expect(buildHrefSeguro({ tipo: 'correo', valor: 'sin-arroba' })).toBeNull();
    expect(buildHrefSeguro({ tipo: 'web', valor: 'https://acme.com\r\nEvil: 1' })).toBeNull();
    expect(buildHrefSeguro({ tipo: 'desconocido', valor: 'https://acme.com' })).toBeNull();
  });

  it('construye la URL de descarga vCard con uid opcional', () => {
    expect(getPublicVCardUrl('juan-perez')).toContain('/public/connect/juan-perez/vcard/');
    expect(getPublicVCardUrl('juan-perez', '04AABBCCDD')).toContain('uid=04AABBCCDD');
  });

  it('propaga errores HTTP con status desde getPublicProfile y submitPublicLead', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'No existe' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(getPublicProfile('no-existe')).rejects.toMatchObject({
      status: 404,
      message: 'No existe',
    });

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('Too Many Requests', { status: 429 }),
    );

    await expect(
      submitPublicLead('juan-perez', {
        nombre: 'Ana',
        consentimiento_aceptado: true,
        consentimiento_texto: 'Texto',
      }),
    ).rejects.toMatchObject({ status: 429 });

    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ email: ['Correo inválido.'] }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(
      submitPublicLead('juan-perez', {
        nombre: 'Ana',
        consentimiento_aceptado: true,
        consentimiento_texto: 'Texto',
      }),
    ).rejects.toMatchObject({ status: 400, message: 'Correo inválido.' });
  });
});

describe('PublicConnectCardPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renderiza perfil público, enlace vCard y filtra enlaces no seguros', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(sampleProfile), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    renderPublicCard('/c/juan-perez?uid=04A1B2C3D4&origen=NFC');

    expect(await screen.findByRole('heading', { name: 'Juan Pérez' })).toBeInTheDocument();
    expect(screen.getByText('Director Comercial')).toBeInTheDocument();
    expect(screen.getByText('ACME Venezuela')).toBeInTheDocument();
    expect(screen.getByText('Conectando negocios.')).toBeInTheDocument();

    const vcardLink = screen.getByRole('link', { name: /guardar contacto \(\.vcf\)/i });
    expect(vcardLink).toHaveAttribute(
      'href',
      expect.stringContaining('/public/connect/juan-perez/vcard/?uid=04A1B2C3D4'),
    );

    expect(screen.getByRole('link', { name: /sitio web/i })).toHaveAttribute(
      'href',
      'https://acme.com/',
    );
    expect(screen.getByRole('link', { name: /whatsapp/i })).toHaveAttribute(
      'href',
      'https://wa.me/584141234567',
    );
    expect(screen.queryByText('Enlace malicioso')).not.toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/public/connect/juan-perez/?uid=04A1B2C3D4&origen=NFC'),
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('bloquea envío sin consentimiento y envía lead cuando se acepta', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify(sampleProfile), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ ok: true, mensaje: 'Gracias, tus datos fueron enviados.' }),
          { status: 201, headers: { 'Content-Type': 'application/json' } },
        ),
      );

    renderPublicCard('/c/juan-perez?origen=QR');

    await screen.findByRole('heading', { name: 'Juan Pérez' });

    const submitButton = screen.getByRole('button', { name: /enviar mis datos/i });
    expect(submitButton).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/^nombre/i), { target: { value: 'María' } });
    fireEvent.change(screen.getByLabelText(/^correo electrónico/i), {
      target: { value: 'maria@cliente.com' },
    });

    // Sigue deshabilitado mientras no acepte consentimiento.
    expect(submitButton).toBeDisabled();

    // Si alguien envía el form programáticamente sin consentimiento, bloquea y muestra error.
    fireEvent.submit(submitButton.closest('form')!);
    expect(await screen.findByText(/debes aceptar el consentimiento/i)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Al marcar consentimiento, habilita y permite enviar.
    fireEvent.click(screen.getByLabelText('Acepto el consentimiento de contacto'));
    expect(submitButton).toBeEnabled();
    fireEvent.click(submitButton);

    expect(await screen.findByText('Gracias, tus datos fueron enviados.')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [, postInit] = fetchMock.mock.calls[1];
    expect(postInit?.method).toBe('POST');
    const sentBody = JSON.parse(String(postInit?.body ?? '{}'));
    expect(sentBody).toMatchObject({
      nombre: 'María',
      email: 'maria@cliente.com',
      origen: 'QR',
      consentimiento_aceptado: true,
      consentimiento_texto: 'Acepto el uso de mis datos para contacto comercial.',
    });
  });

  it('muestra vista 404 amigable cuando el perfil no existe o está inactivo', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Perfil no encontrado.' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    renderPublicCard('/c/inactivo');

    expect(await screen.findByText('Perfil no disponible')).toBeInTheDocument();
  });

  it('cubre campos opcionales, temas, error de carga 500 y error al enviar lead', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'Error interno' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    renderPublicCard('/c/error-500');
    expect(await screen.findByText('Error interno')).toBeInTheDocument();

    const oscuroProfile = {
      ...sampleProfile,
      slug: 'carlos',
      nombre_publico: 'Carlos',
      tema: 'OSCURO',
    };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify(oscuroProfile), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Rate limit' }), {
          status: 429,
          headers: { 'Content-Type': 'application/json' },
        }),
      );

    renderPublicCard('/c/carlos');
    await screen.findByRole('heading', { name: 'Carlos' });

    const submitButton = screen.getByRole('button', { name: /enviar mis datos/i });
    fireEvent.submit(submitButton.closest('form')!);
    expect(await screen.findByText(/por favor ingresa tu nombre/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/^nombre/i), { target: { value: 'Luis' } });
    fireEvent.change(screen.getByLabelText(/^apellido/i), { target: { value: 'Rojas' } });
    fireEvent.change(screen.getByLabelText(/^empresa/i), { target: { value: 'Beta SA' } });
    fireEvent.change(screen.getByLabelText(/^teléfono/i), { target: { value: '+584140001122' } });
    fireEvent.change(screen.getByLabelText(/^mensaje/i), { target: { value: 'Cotizar servicio' } });
    fireEvent.change(screen.getByLabelText('Website'), { target: { value: '' } });
    fireEvent.click(screen.getByLabelText('Acepto el consentimiento de contacto'));
    fireEvent.click(submitButton);

    expect(await screen.findByText('Rate limit')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
