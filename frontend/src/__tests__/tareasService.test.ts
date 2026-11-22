import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  areasTareasService,
  proyectosTareasService,
  seccionesTareasService,
  tareasService,
  recurrentesTareasService,
  minutasTareasService,
  seguimientoTareasService,
} from '../services/tareasService';

describe('tareasService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('areasTareasService lista, crea con whitelist, sincroniza miembros y elimina', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_area: 'a1', nombre: 'Tesorería' }] });
    const areas = await areasTareasService.getAll();
    expect(areas).toHaveLength(1);
    expect(get).toHaveBeenCalledWith('/tareas/areas/');

    vi.mocked(post).mockResolvedValueOnce({ id_area: 'a1' });
    await areasTareasService.create({ nombre: 'Tesorería' });
    expect(post).toHaveBeenCalledWith('/tareas/areas/', {
      nombre: 'Tesorería',
      color: '#378ADD',
      palabras_clave: [],
    });

    vi.mocked(post).mockResolvedValueOnce({ id_area: 'a2' });
    await areasTareasService.create({
      nombre: 'Ventas',
      color: '#00AA55',
      lider: 'u1',
      palabras_clave: ['pedido'],
    });
    expect(post).toHaveBeenLastCalledWith('/tareas/areas/', {
      nombre: 'Ventas',
      color: '#00AA55',
      palabras_clave: ['pedido'],
      lider: 'u1',
    });

    vi.mocked(post).mockResolvedValueOnce({ id_area: 'a1' });
    await areasTareasService.sincronizarMiembros('a1', ['u1', 'u2']);
    expect(post).toHaveBeenLastCalledWith('/tareas/areas/a1/miembros/', {
      usuarios: ['u1', 'u2'],
    });

    vi.mocked(del).mockResolvedValueOnce(undefined);
    await areasTareasService.remove('a1');
    expect(del).toHaveBeenCalledWith('/tareas/areas/a1/');
  });

  it('proyectosTareasService y seccionesTareasService cubren filtros y tablero personal', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await proyectosTareasService.getAll();
    expect(get).toHaveBeenCalledWith('/tareas/proyectos/');

    vi.mocked(get).mockResolvedValueOnce([]);
    await proyectosTareasService.getAll(false);
    expect(get).toHaveBeenLastCalledWith('/tareas/proyectos/?archivado=false');

    vi.mocked(post).mockResolvedValueOnce({ id_proyecto: 'p1' });
    await proyectosTareasService.create({ nombre: 'Cierre Mes' });
    expect(post).toHaveBeenLastCalledWith('/tareas/proyectos/', {
      nombre: 'Cierre Mes',
      descripcion: '',
      color: '#1D9E75',
      vista_predeterminada: 'TABLERO',
    });

    vi.mocked(post).mockResolvedValueOnce({ id_proyecto: 'p2' });
    await proyectosTareasService.create({
      nombre: 'Auditoría',
      descripcion: 'Q4',
      color: '#112233',
      vista_predeterminada: 'LISTA',
      area: 'a1',
      propietario: 'u1',
    });
    expect(post).toHaveBeenLastCalledWith('/tareas/proyectos/', {
      nombre: 'Auditoría',
      descripcion: 'Q4',
      color: '#112233',
      vista_predeterminada: 'LISTA',
      area: 'a1',
      propietario: 'u1',
    });

    vi.mocked(post).mockResolvedValueOnce({ id_proyecto: 'pers-1' });
    await proyectosTareasService.miTablero();
    expect(post).toHaveBeenLastCalledWith('/tareas/proyectos/mi-tablero/', {});

    vi.mocked(post).mockResolvedValueOnce({ id_proyecto: 'pers-2' });
    await proyectosTareasService.miTablero('u9');
    expect(post).toHaveBeenLastCalledWith('/tareas/proyectos/mi-tablero/', { usuario: 'u9' });

    vi.mocked(del).mockResolvedValueOnce(undefined);
    await proyectosTareasService.remove('p1');
    expect(del).toHaveBeenCalledWith('/tareas/proyectos/p1/');

    vi.mocked(get).mockResolvedValueOnce([]);
    await seccionesTareasService.getPorProyecto('p1');
    expect(get).toHaveBeenLastCalledWith('/tareas/secciones/?proyecto=p1');

    vi.mocked(post).mockResolvedValueOnce({ id_seccion: 's1' });
    await seccionesTareasService.create('p1', 'Backlog');
    expect(post).toHaveBeenLastCalledWith('/tareas/secciones/', {
      proyecto: 'p1',
      nombre: 'Backlog',
      orden: 10,
    });

    vi.mocked(post).mockResolvedValueOnce({ id_seccion: 's2' });
    await seccionesTareasService.create('p1', 'Urgente', 1);
    expect(post).toHaveBeenLastCalledWith('/tareas/secciones/', {
      proyecto: 'p1',
      nombre: 'Urgente',
      orden: 1,
    });
  });

  it('tareasService cubre CRUD, filtros, transiciones, comentarios y dependencias', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await tareasService.getAll();
    expect(get).toHaveBeenLastCalledWith('/tareas/items/');

    vi.mocked(get).mockResolvedValueOnce([]);
    await tareasService.getAll({
      proyecto: 'p1',
      estado: 'PENDIENTE',
      prioridad: 'ALTA',
      area: 'a1',
      asignado_a: 'u1',
      vencidas: true,
      search: 'bcv',
    });
    expect(get).toHaveBeenLastCalledWith(
      '/tareas/items/?proyecto=p1&estado=PENDIENTE&prioridad=ALTA&area=a1&asignado_a=u1&vencidas=true&search=bcv',
    );

    vi.mocked(get).mockResolvedValueOnce({ id_tarea: 't1' });
    await tareasService.getById('t1');
    expect(get).toHaveBeenLastCalledWith('/tareas/items/t1/');

    vi.mocked(post).mockResolvedValueOnce({ id_tarea: 't1' });
    await tareasService.create({ titulo: 'Simple' });
    expect(post).toHaveBeenLastCalledWith('/tareas/items/', {
      titulo: 'Simple',
      descripcion: '',
      prioridad: 'MEDIA',
    });

    vi.mocked(post).mockResolvedValueOnce({ id_tarea: 't2' });
    await tareasService.create({
      titulo: 'Completa',
      descripcion: 'Desc',
      prioridad: 'URGENTE',
      estado: 'EN_EJECUCION',
      proyecto: 'p1',
      seccion: 's1',
      area: 'a1',
      tarea_padre: 't1',
      asignado_a: 'u1',
      fecha_inicio: '2026-11-17',
      fecha_vencimiento: '2026-11-20',
      entidad_tipo: 'cxc.factura',
      entidad_id: 'f1',
    });
    expect(post).toHaveBeenLastCalledWith('/tareas/items/', {
      titulo: 'Completa',
      descripcion: 'Desc',
      prioridad: 'URGENTE',
      estado: 'EN_EJECUCION',
      proyecto: 'p1',
      seccion: 's1',
      area: 'a1',
      tarea_padre: 't1',
      asignado_a: 'u1',
      fecha_inicio: '2026-11-17',
      fecha_vencimiento: '2026-11-20',
      entidad_tipo: 'cxc.factura',
      entidad_id: 'f1',
    });

    vi.mocked(patch).mockResolvedValueOnce({ id_tarea: 't1' });
    await tareasService.update('t1', {});
    expect(patch).toHaveBeenLastCalledWith('/tareas/items/t1/', {});

    vi.mocked(patch).mockResolvedValueOnce({ id_tarea: 't1' });
    await tareasService.update('t1', {
      titulo: 'Nuevo',
      descripcion: 'Nueva desc',
      prioridad: 'BAJA',
      area: 'a1',
      asignado_a: 'u2',
      fecha_inicio: '2026-11-18',
      fecha_vencimiento: '2026-11-25',
    });
    expect(patch).toHaveBeenLastCalledWith('/tareas/items/t1/', {
      titulo: 'Nuevo',
      descripcion: 'Nueva desc',
      prioridad: 'BAJA',
      area: 'a1',
      asignado_a: 'u2',
      fecha_inicio: '2026-11-18',
      fecha_vencimiento: '2026-11-25',
    });

    vi.mocked(post).mockResolvedValueOnce({ id_tarea: 't1', estado: 'COMPLETADA' });
    await tareasService.cambiarEstado('t1', 'COMPLETADA');
    expect(post).toHaveBeenLastCalledWith('/tareas/items/t1/cambiar-estado/', {
      estado: 'COMPLETADA',
      motivo: '',
    });

    vi.mocked(post).mockResolvedValueOnce({ id_tarea: 't1' });
    await tareasService.mover('t1', 's2');
    expect(post).toHaveBeenLastCalledWith('/tareas/items/t1/mover/', { seccion: 's2' });

    vi.mocked(post).mockResolvedValueOnce({ id_tarea: 't1' });
    await tareasService.mover('t1', 's2', 3);
    expect(post).toHaveBeenLastCalledWith('/tareas/items/t1/mover/', {
      seccion: 's2',
      orden_tablero: 3,
    });

    vi.mocked(del).mockResolvedValueOnce(undefined);
    await tareasService.remove('t1');
    expect(del).toHaveBeenLastCalledWith('/tareas/items/t1/');

    vi.mocked(get).mockResolvedValueOnce([]);
    await tareasService.listarComentarios('t1');
    expect(get).toHaveBeenLastCalledWith('/tareas/items/t1/comentarios/');

    vi.mocked(post).mockResolvedValueOnce({ id_comentario: 'c1' });
    await tareasService.agregarComentario('t1', 'Listo banco');
    expect(post).toHaveBeenLastCalledWith('/tareas/items/t1/comentarios/', {
      cuerpo: 'Listo banco',
    });

    vi.mocked(get).mockResolvedValueOnce([]);
    await tareasService.listarDependencias('t1');
    expect(get).toHaveBeenLastCalledWith('/tareas/items/t1/dependencias/');

    vi.mocked(post).mockResolvedValueOnce({ id_dependencia: 'd1' });
    await tareasService.agregarDependencia('t1', 't0');
    expect(post).toHaveBeenLastCalledWith('/tareas/items/t1/dependencias/', { depende_de: 't0' });
  });

  it('recurrentesTareasService, minutasTareasService y seguimientoTareasService cubren todas sus ramas', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await recurrentesTareasService.getAll();
    expect(get).toHaveBeenLastCalledWith('/tareas/recurrentes/');

    vi.mocked(post).mockResolvedValueOnce({ id_plantilla_recurrente: 'r1' });
    await recurrentesTareasService.create({
      titulo: 'Corte diario',
      frecuencia: 'DIARIA',
      proxima_ejecucion: '2026-11-20',
    });
    expect(post).toHaveBeenLastCalledWith('/tareas/recurrentes/', {
      titulo: 'Corte diario',
      descripcion: '',
      prioridad: 'MEDIA',
      frecuencia: 'DIARIA',
      proxima_ejecucion: '2026-11-20',
      dias_semana: [],
      horas_dia: [],
    });

    vi.mocked(post).mockResolvedValueOnce({ id_plantilla_recurrente: 'r2' });
    await recurrentesTareasService.create({
      titulo: 'Cierre mensual',
      descripcion: 'Mes',
      prioridad: 'ALTA',
      frecuencia: 'MENSUAL',
      proxima_ejecucion: '2026-12-01',
      dia_mes: 28,
      proyecto: 'p1',
      area: 'a1',
      asignado_a: 'u1',
    });
    expect(post).toHaveBeenLastCalledWith('/tareas/recurrentes/', {
      titulo: 'Cierre mensual',
      descripcion: 'Mes',
      prioridad: 'ALTA',
      frecuencia: 'MENSUAL',
      proxima_ejecucion: '2026-12-01',
      dias_semana: [],
      horas_dia: [],
      dia_mes: 28,
      proyecto: 'p1',
      area: 'a1',
      asignado_a: 'u1',
    });

    vi.mocked(post).mockResolvedValueOnce({ tareas_creadas: 1 });
    await recurrentesTareasService.materializar();
    expect(post).toHaveBeenLastCalledWith('/tareas/recurrentes/materializar/', {});

    vi.mocked(post).mockResolvedValueOnce({ tareas_creadas: 0 });
    await recurrentesTareasService.materializar('2026-11-20');
    expect(post).toHaveBeenLastCalledWith('/tareas/recurrentes/materializar/', {
      fecha: '2026-11-20',
    });

    vi.mocked(del).mockResolvedValueOnce(undefined);
    await recurrentesTareasService.remove('r1');
    expect(del).toHaveBeenLastCalledWith('/tareas/recurrentes/r1/');

    // Minutas
    vi.mocked(get).mockResolvedValueOnce([]);
    await minutasTareasService.getAll();
    expect(get).toHaveBeenLastCalledWith('/tareas/minutas/');

    vi.mocked(post).mockResolvedValueOnce({ id_minuta: 'm1' });
    await minutasTareasService.create({
      titulo: 'Comité semanal',
      items_propuestos: [{ titulo: 'Acuerdo 1' }],
    });
    expect(post).toHaveBeenLastCalledWith('/tareas/minutas/', {
      titulo: 'Comité semanal',
      texto_fuente: '',
      items_propuestos: [{ titulo: 'Acuerdo 1' }],
    });

    vi.mocked(post).mockResolvedValueOnce({ id_minuta: 'm2' });
    await minutasTareasService.create({
      titulo: 'Comité cierre',
      fecha_reunion: '2026-11-17',
      texto_fuente: 'Notas',
      items_propuestos: [{ titulo: 'Acuerdo 2' }],
    });
    expect(post).toHaveBeenLastCalledWith('/tareas/minutas/', {
      titulo: 'Comité cierre',
      fecha_reunion: '2026-11-17',
      texto_fuente: 'Notas',
      items_propuestos: [{ titulo: 'Acuerdo 2' }],
    });

    vi.mocked(post).mockResolvedValueOnce({ minuta: {}, tareas_creadas: [] });
    await minutasTareasService.confirmar('m1');
    expect(post).toHaveBeenLastCalledWith('/tareas/minutas/m1/confirmar/', {});

    vi.mocked(post).mockResolvedValueOnce({ minuta: {}, tareas_creadas: [] });
    await minutasTareasService.confirmar('m1', {
      proyecto: 'p1',
      items_confirmados: [{ titulo: 'Editado' }],
    });
    expect(post).toHaveBeenLastCalledWith('/tareas/minutas/m1/confirmar/', {
      proyecto: 'p1',
      items_confirmados: [{ titulo: 'Editado' }],
    });

    vi.mocked(del).mockResolvedValueOnce(undefined);
    await minutasTareasService.remove('m1');
    expect(del).toHaveBeenLastCalledWith('/tareas/minutas/m1/');

    // Seguimiento y resumen
    vi.mocked(get).mockResolvedValueOnce({ totales: {} });
    await seguimientoTareasService.getResumen();
    expect(get).toHaveBeenLastCalledWith('/tareas/resumen/');

    vi.mocked(get).mockResolvedValueOnce({ totales: {} });
    await seguimientoTareasService.getResumen('2026-11-20');
    expect(get).toHaveBeenLastCalledWith('/tareas/resumen/?fecha=2026-11-20');

    vi.mocked(get).mockResolvedValueOnce({ zona_horaria: 'America/Caracas' });
    await seguimientoTareasService.getConfiguracion();
    expect(get).toHaveBeenLastCalledWith('/tareas/configuracion/');

    vi.mocked(patch).mockResolvedValueOnce({});
    await seguimientoTareasService.updateConfiguracion({});
    expect(patch).toHaveBeenLastCalledWith('/tareas/configuracion/', {});

    vi.mocked(patch).mockResolvedValueOnce({});
    await seguimientoTareasService.updateConfiguracion({
      zona_horaria: 'America/Caracas',
      hora_recordatorio_manana: '08:30:00',
      hora_recordatorio_tarde: '15:30:00',
      hora_reporte_gerencial: '16:30:00',
      horas_bloqueo_vencida: 48,
      gerente: 'u1',
    });
    expect(patch).toHaveBeenLastCalledWith('/tareas/configuracion/', {
      zona_horaria: 'America/Caracas',
      hora_recordatorio_manana: '08:30:00',
      hora_recordatorio_tarde: '15:30:00',
      hora_reporte_gerencial: '16:30:00',
      horas_bloqueo_vencida: 48,
      gerente: 'u1',
    });

    vi.mocked(post).mockResolvedValueOnce({
      momento: 'AUTO',
      instante: '2026-11-17T09:00:00-04:00',
      alertas_emitidas: 1,
      tareas_bloqueadas: 0,
    });
    await seguimientoTareasService.ejecutarCiclo();
    expect(post).toHaveBeenLastCalledWith('/tareas/seguimiento/ejecutar/', { momento: 'AUTO' });
  });
});
