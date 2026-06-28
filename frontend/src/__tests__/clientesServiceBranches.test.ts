import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post } from '../services/api';
import {
  contactosClienteService,
  direccionesClienteService,
} from '../services/clientesService';

// Cobertura de las ramas "sin cliente" (querystring vacío + sin filtro local) y
// rutas de error, que el suite principal de clientesService no ejercita.

describe('contactosClienteService — ramas sin cliente / errores', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll sin cliente pega al endpoint base y no filtra', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_contacto: 'k1', id_cliente: 'c1' },
      { id_contacto: 'k2', id_cliente: 'c2' },
    ]);
    const r = await contactosClienteService.getAll();
    expect(get).toHaveBeenCalledWith('/crm/contactos-cliente/');
    expect(r.map((c) => c.id_contacto)).toEqual(['k1', 'k2']);
  });

  it('getAll normaliza respuesta paginada sin filtro de cliente', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_contacto: 'k1', id_cliente: 'c1' }] });
    expect((await contactosClienteService.getAll()).length).toBe(1);
  });

  it('create propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('dup'));
    await expect(
      contactosClienteService.create({
        id_empresa: 'e1',
        id_cliente: 'c1',
        nombre_contacto: 'Ana',
        apellido_contacto: 'Pérez',
        cargo: null,
        telefono_directo: null,
        telefono_movil: null,
        email_contacto: 'ana@x.com',
        es_contacto_principal: false,
        observaciones: null,
      }),
    ).rejects.toThrow('dup');
  });
});

describe('direccionesClienteService — ramas sin cliente / errores', () => {
  beforeEach(() => vi.clearAllMocks());

  it('getAll sin cliente pega al endpoint base y no filtra', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_direccion: 'd1', id_cliente: 'c1' },
      { id_direccion: 'd2', id_cliente: 'c2' },
    ]);
    const r = await direccionesClienteService.getAll();
    expect(get).toHaveBeenCalledWith('/crm/direcciones-cliente/');
    expect(r.map((d) => d.id_direccion)).toEqual(['d1', 'd2']);
  });

  it('getAll con cliente arma el querystring y filtra localmente', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [
        { id_direccion: 'd1', id_cliente: 'c1' },
        { id_direccion: 'd2', id_cliente: 'otro' },
      ],
    });
    const r = await direccionesClienteService.getAll({ cliente: 'c1' });
    expect(get).toHaveBeenCalledWith('/crm/direcciones-cliente/?id_cliente=c1');
    expect(r.map((d) => d.id_direccion)).toEqual(['d1']);
  });

  it('create propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('boom'));
    await expect(
      direccionesClienteService.create({
        id_empresa: 'e1',
        id_cliente: 'c1',
        tipo_direccion: 'FISCAL',
        direccion_completa: 'Av. X',
        ciudad: 'Caracas',
        estado_provincia: 'DC',
        codigo_postal: null,
        pais: 'VE',
        telefono: null,
        persona_contacto: null,
        es_direccion_principal: false,
        observaciones: null,
      }),
    ).rejects.toThrow('boom');
  });
});
