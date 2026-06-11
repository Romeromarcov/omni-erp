import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  post: vi.fn(),
}));

import { post } from '../services/api';
import { DispositivoService } from '../services/dispositivoService';

const mockPost = post as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockPost.mockReset();
  mockPost.mockResolvedValue({ success: true, mensaje: 'ok' });
});

describe('DispositivoService', () => {
  it('ejecutarAccion hace POST al endpoint de acciones con el payload completo', async () => {
    const data = { id_dispositivo: 'd1', accion: 'abrir_sesion' as const };
    const res = await DispositivoService.ejecutarAccion(data);

    expect(mockPost).toHaveBeenCalledWith('/core/dispositivos/accion/', data);
    expect(res).toEqual({ success: true, mensaje: 'ok' });
  });

  it('crearCajaFisica usa REGISTRADORA como tipo por defecto', async () => {
    await DispositivoService.crearCajaFisica('d1', 'Caja Principal');

    expect(mockPost).toHaveBeenCalledWith('/core/dispositivos/accion/', {
      id_dispositivo: 'd1',
      accion: 'crear_caja_fisica',
      nombre_caja: 'Caja Principal',
      tipo_caja: 'REGISTRADORA',
    });
  });

  it('crearCajaFisica respeta el tipo de caja explícito', async () => {
    await DispositivoService.crearCajaFisica('d1', 'Caja Móvil', 'MOVIL');

    expect(mockPost).toHaveBeenCalledWith(
      '/core/dispositivos/accion/',
      expect.objectContaining({ tipo_caja: 'MOVIL' })
    );
  });

  it('noPreguntarCaja envía la acción correcta', async () => {
    await DispositivoService.noPreguntarCaja('d9');

    expect(mockPost).toHaveBeenCalledWith('/core/dispositivos/accion/', {
      id_dispositivo: 'd9',
      accion: 'no_preguntar_caja',
    });
  });

  it('abrirSesion envía la acción correcta', async () => {
    await DispositivoService.abrirSesion('d9');

    expect(mockPost).toHaveBeenCalledWith('/core/dispositivos/accion/', {
      id_dispositivo: 'd9',
      accion: 'abrir_sesion',
    });
  });

  it('propaga el error del backend sin tragarlo', async () => {
    mockPost.mockRejectedValueOnce(new Error('403'));
    await expect(DispositivoService.abrirSesion('d9')).rejects.toThrow('403');
  });
});
