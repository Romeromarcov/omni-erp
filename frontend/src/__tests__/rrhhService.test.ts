import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}));

import { get, post, patch } from '../services/api';
import { rrhhService } from '../services/rrhhService';
import type { Empleado } from '../services/rrhhService';

const empleado: Empleado = {
  id: 1,
  empresa: 'emp-1',
  referencia_externa: null,
  documento_json: { salario_mensual: '500.00' },
  nombre: 'Ana',
  apellido: 'Pérez',
  cedula: 'V-12345678',
  cargo: 3,
  fecha_ingreso: '2024-01-15',
  activo: true,
  contacto: null,
};

describe('rrhhService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('getEmpleadosPaginated pasa la página y devuelve la respuesta DRF', async () => {
    vi.mocked(get).mockResolvedValue({ count: 1, next: null, previous: null, results: [empleado] });
    const res = await rrhhService.getEmpleadosPaginated(2);
    expect(get).toHaveBeenCalledWith('/rrhh/empleados/?page=2');
    expect(res.count).toBe(1);
    expect(res.results[0].cedula).toBe('V-12345678');
  });

  it('getEmpleadosPaginated normaliza listas directas', async () => {
    vi.mocked(get).mockResolvedValue([empleado]);
    const res = await rrhhService.getEmpleadosPaginated();
    expect(get).toHaveBeenCalledWith('/rrhh/empleados/?page=1');
    expect(res).toEqual({ count: 1, next: null, previous: null, results: [empleado] });
  });

  it('getEmpleado consulta el detalle por id', async () => {
    vi.mocked(get).mockResolvedValue(empleado);
    const res = await rrhhService.getEmpleado(1);
    expect(get).toHaveBeenCalledWith('/rrhh/empleados/1/');
    expect(res.nombre).toBe('Ana');
  });

  it('getEmpleadosDeEmpresa camina las páginas y filtra por empresa', async () => {
    const ajeno = { ...empleado, id: 9, empresa: 'emp-OTRA' };
    const inactivo = { ...empleado, id: 2, activo: false };
    vi.mocked(get)
      .mockResolvedValueOnce({ count: 3, next: 'pag2', previous: null, results: [empleado, ajeno] })
      .mockResolvedValueOnce({ count: 3, next: null, previous: null, results: [inactivo] });
    const res = await rrhhService.getEmpleadosDeEmpresa('emp-1');
    expect(get).toHaveBeenNthCalledWith(1, '/rrhh/empleados/?page=1');
    expect(get).toHaveBeenNthCalledWith(2, '/rrhh/empleados/?page=2');
    // Incluye inactivos (nombran recibos históricos), excluye otras empresas.
    expect(res.map((e) => e.id)).toEqual([1, 2]);
  });

  it('crearEmpleado postea el payload con documento_json de salario string', async () => {
    vi.mocked(post).mockResolvedValue(empleado);
    await rrhhService.crearEmpleado({
      empresa: 'emp-1',
      nombre: 'Ana',
      apellido: 'Pérez',
      cedula: 'V-12345678',
      cargo: 3,
      fecha_ingreso: '2024-01-15',
      activo: true,
      documento_json: { salario_mensual: '500.00' },
    });
    expect(post).toHaveBeenCalledWith('/rrhh/empleados/', {
      empresa: 'emp-1',
      nombre: 'Ana',
      apellido: 'Pérez',
      cedula: 'V-12345678',
      cargo: 3,
      fecha_ingreso: '2024-01-15',
      activo: true,
      documento_json: { salario_mensual: '500.00' },
    });
  });

  it('actualizarEmpleado hace PATCH parcial sin exigir empresa', async () => {
    vi.mocked(patch).mockResolvedValue({ ...empleado, apellido: 'García' });
    const res = await rrhhService.actualizarEmpleado(1, { apellido: 'García' });
    expect(patch).toHaveBeenCalledWith('/rrhh/empleados/1/', { apellido: 'García' });
    expect(res.apellido).toBe('García');
  });

  it('getCargos camina las páginas del catálogo (incluye cargos globales)', async () => {
    const cargo = { id: 3, empresa: null, nombre: 'Vendedor', descripcion: null, activo: true };
    vi.mocked(get)
      .mockResolvedValueOnce({ count: 2, next: 'pag2', previous: null, results: [cargo] })
      .mockResolvedValueOnce({
        count: 2,
        next: null,
        previous: null,
        results: [{ ...cargo, id: 4, nombre: 'Cajero', empresa: 'emp-1' }],
      });
    const res = await rrhhService.getCargos();
    expect(get).toHaveBeenNthCalledWith(1, '/rrhh/cargos/?page=1');
    expect(get).toHaveBeenNthCalledWith(2, '/rrhh/cargos/?page=2');
    expect(res.map((c) => c.nombre)).toEqual(['Vendedor', 'Cajero']);
  });

  it('getCargos corta en una lista directa (sin next)', async () => {
    vi.mocked(get).mockResolvedValue([
      { id: 3, empresa: null, nombre: 'Vendedor', descripcion: null, activo: true },
    ]);
    const res = await rrhhService.getCargos();
    expect(get).toHaveBeenCalledTimes(1);
    expect(res).toHaveLength(1);
  });
});
