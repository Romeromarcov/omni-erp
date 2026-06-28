import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  patch: vi.fn(),
}));

import { get, patch } from '../services/api';
import {
  notificacionesService,
  type Notificacion,
} from '../services/notificacionesService';

const notif: Notificacion = {
  id_notificacion: 'n1',
  tipo: 'INFO',
  titulo: 'Hola',
  mensaje: 'Tienes una notificación',
  leida: false,
  fecha_lectura: null,
  url_accion: '',
  metadata: null,
  fecha_creacion: '2026-06-24T10:00:00Z',
};

describe('notificacionesService.misNotificaciones', () => {
  beforeEach(() => vi.clearAllMocks());

  it('llama al endpoint sin querystring por defecto y normaliza lista directa', async () => {
    vi.mocked(get).mockResolvedValueOnce([notif]);
    const r = await notificacionesService.misNotificaciones();
    expect(get).toHaveBeenCalledWith('/notificaciones/notificaciones/mis-notificaciones/');
    expect(r).toEqual([notif]);
  });

  it('agrega ?no_leidas=true cuando soloNoLeidas es true', async () => {
    vi.mocked(get).mockResolvedValueOnce([notif]);
    await notificacionesService.misNotificaciones(true);
    expect(get).toHaveBeenCalledWith(
      '/notificaciones/notificaciones/mis-notificaciones/?no_leidas=true',
    );
  });

  it('normaliza una respuesta paginada {results} a un arreglo', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [notif], count: 1 });
    const r = await notificacionesService.misNotificaciones();
    expect(r).toEqual([notif]);
  });

  it('devuelve [] ante una respuesta vacía/no reconocida', async () => {
    vi.mocked(get).mockResolvedValueOnce(null);
    const r = await notificacionesService.misNotificaciones();
    expect(r).toEqual([]);
  });

  it('propaga el error de red', async () => {
    vi.mocked(get).mockRejectedValueOnce(new Error('fallo de red'));
    await expect(notificacionesService.misNotificaciones()).rejects.toThrow('fallo de red');
  });
});

describe('notificacionesService.marcarLeida', () => {
  beforeEach(() => vi.clearAllMocks());

  it('hace PATCH con cuerpo vacío al endpoint marcar-leida', async () => {
    const leida = { ...notif, leida: true, fecha_lectura: '2026-06-24T11:00:00Z' };
    vi.mocked(patch).mockResolvedValueOnce(leida);
    const r = await notificacionesService.marcarLeida('n1');
    expect(patch).toHaveBeenCalledWith(
      '/notificaciones/notificaciones/n1/marcar-leida/',
      {},
    );
    expect(r).toEqual(leida);
  });

  it('propaga el error', async () => {
    vi.mocked(patch).mockRejectedValueOnce(new Error('404'));
    await expect(notificacionesService.marcarLeida('x')).rejects.toThrow('404');
  });
});
