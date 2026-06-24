import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../services/api', () => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
}));

import { get, post, patch, del } from '../services/api';
import {
  categoriasTicketService,
  ticketsSoporteService,
  interaccionesTicketService,
  articulosConocimientoService,
  feedbackClienteService,
  ticketEstaCerrado,
  ESTADOS_TICKET,
  PRIORIDADES_TICKET,
  type CategoriaTicketPayload,
  type TicketSoportePayload,
  type InteraccionTicketPayload,
  type BaseConocimientoArticuloPayload,
  type FeedbackClientePayload,
} from '../services/servicioClienteService';

const categoriaPayload: CategoriaTicketPayload = {
  id_empresa: 'e1',
  nombre_categoria: 'Soporte técnico',
  descripcion: 'desc',
  activo: true,
};

const ticketPayload: TicketSoportePayload = {
  id_empresa: 'e1',
  numero_ticket: 'T-001',
  asunto: 'No enciende',
  descripcion: 'El equipo no enciende',
  id_categoria_ticket: 'cat1',
  prioridad: 'ALTA',
  estado_ticket: 'ABIERTO',
  id_cliente_temp: null,
  id_agente_asignado_temp: null,
  sla_vencimiento: null,
};

const interaccionPayload: InteraccionTicketPayload = {
  id_ticket: 't1',
  tipo_interaccion: 'COMENTARIO',
  contenido: 'Revisando',
};

const articuloPayload: BaseConocimientoArticuloPayload = {
  id_empresa: 'e1',
  titulo: 'Cómo reiniciar',
  contenido: 'Mantén el botón 10s',
  id_categoria_ticket: 'cat1',
  palabras_clave: 'reinicio,energía',
  visibilidad: 'PUBLICA',
  activo: true,
};

const feedbackPayload: FeedbackClientePayload = {
  id_empresa: 'e1',
  tipo_feedback: 'ENCUESTA_SATISFACCION',
  calificacion: 5,
  comentarios: 'Excelente',
  id_cliente_temp: null,
  id_ticket_origen: null,
};

beforeEach(() => vi.clearAllMocks());

// ── Constantes y helpers puros ────────────────────────────────────────────────

describe('constantes y helpers', () => {
  it('ticketEstaCerrado solo es true en CERRADO', () => {
    expect(ticketEstaCerrado('CERRADO')).toBe(true);
    expect(ticketEstaCerrado('ABIERTO')).toBe(false);
    expect(ticketEstaCerrado('RESUELTO')).toBe(false);
    expect(ticketEstaCerrado('ESCALADO')).toBe(false);
  });

  it('expone los catálogos de estados y prioridades', () => {
    expect(ESTADOS_TICKET).toContain('ABIERTO');
    expect(ESTADOS_TICKET).toContain('CERRADO');
    expect(ESTADOS_TICKET.length).toBe(7);
    expect(PRIORIDADES_TICKET).toEqual(['BAJA', 'MEDIA', 'ALTA', 'URGENTE']);
  });
});

// ── categoriasTicketService ───────────────────────────────────────────────────

describe('categoriasTicketService', () => {
  it('getAll arma el querystring con empresa y search', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_categoria_ticket: 'c1' }] });
    const r = await categoriasTicketService.getAll({ empresa: 'e1', search: 'tec' });
    expect(get).toHaveBeenCalledWith('/servicio-cliente/categorias-ticket/?id_empresa=e1&search=tec');
    expect(r).toEqual([{ id_categoria_ticket: 'c1' }]);
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await categoriasTicketService.getAll();
    expect(get).toHaveBeenCalledWith('/servicio-cliente/categorias-ticket/');
  });

  it('getAll con objeto vacío pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await categoriasTicketService.getAll({});
    expect(get).toHaveBeenCalledWith('/servicio-cliente/categorias-ticket/');
  });

  it('getAll solo con search', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await categoriasTicketService.getAll({ search: 'x' });
    expect(get).toHaveBeenCalledWith('/servicio-cliente/categorias-ticket/?search=x');
  });

  it('getAll normaliza respuesta inesperada a []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await categoriasTicketService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_categoria_ticket: 'c1' });
    await categoriasTicketService.getById('c1');
    expect(get).toHaveBeenCalledWith('/servicio-cliente/categorias-ticket/c1/');
  });

  it('activas normaliza un array directo', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_categoria_ticket: 'c1' }]);
    const r = await categoriasTicketService.activas();
    expect(get).toHaveBeenCalledWith('/servicio-cliente/categorias-ticket/activas/');
    expect(r.length).toBe(1);
  });

  it('estadisticas pega al endpoint de detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ total_tickets: 3 });
    const r = await categoriasTicketService.estadisticas('c1');
    expect(get).toHaveBeenCalledWith('/servicio-cliente/categorias-ticket/c1/estadisticas/');
    expect(r.total_tickets).toBe(3);
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_categoria_ticket: 'c1' });
    await categoriasTicketService.create(categoriaPayload);
    expect(post).toHaveBeenCalledWith('/servicio-cliente/categorias-ticket/', categoriaPayload);
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValueOnce({ id_categoria_ticket: 'c1' });
    await categoriasTicketService.update('c1', categoriaPayload);
    expect(patch).toHaveBeenCalledWith('/servicio-cliente/categorias-ticket/c1/', categoriaPayload);
  });

  it('remove elimina por id', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await categoriasTicketService.remove('c1');
    expect(del).toHaveBeenCalledWith('/servicio-cliente/categorias-ticket/c1/');
  });

  it('create propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('duplicado'));
    await expect(categoriasTicketService.create(categoriaPayload)).rejects.toThrow('duplicado');
  });
});

// ── ticketsSoporteService ─────────────────────────────────────────────────────

describe('ticketsSoporteService getAll', () => {
  it('arma el querystring con todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_ticket: 't1' }] });
    const r = await ticketsSoporteService.getAll({
      empresa: 'e1',
      estado: 'ABIERTO',
      prioridad: 'ALTA',
      categoria: 'cat1',
      search: 'enciende',
    });
    expect(get).toHaveBeenCalledWith(
      '/servicio-cliente/tickets-soporte/?id_empresa=e1&estado_ticket=ABIERTO&prioridad=ALTA&id_categoria_ticket=cat1&search=enciende',
    );
    expect(r).toEqual([{ id_ticket: 't1' }]);
  });

  it('sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await ticketsSoporteService.getAll();
    expect(get).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/');
  });

  it('con objeto vacío pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await ticketsSoporteService.getAll({});
    expect(get).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/');
  });

  it('solo con estado', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await ticketsSoporteService.getAll({ estado: 'CERRADO' });
    expect(get).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/?estado_ticket=CERRADO');
  });

  it('solo con prioridad', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await ticketsSoporteService.getAll({ prioridad: 'URGENTE' });
    expect(get).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/?prioridad=URGENTE');
  });

  it('normaliza respuesta inesperada a []', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as never);
    expect(await ticketsSoporteService.getAll()).toEqual([]);
  });
});

describe('ticketsSoporteService acciones', () => {
  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_ticket: 't1' });
    await ticketsSoporteService.getById('t1');
    expect(get).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/');
  });

  it('abiertos sin agente pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_ticket: 't1' }]);
    const r = await ticketsSoporteService.abiertos();
    expect(get).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/abiertos/');
    expect(r.length).toBe(1);
  });

  it('abiertos con agente agrega el query param', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [] });
    await ticketsSoporteService.abiertos('ag1');
    expect(get).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/abiertos/?agente_id=ag1');
  });

  it('porPrioridad agrega el query param', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await ticketsSoporteService.porPrioridad('ALTA');
    expect(get).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/por_prioridad/?prioridad=ALTA');
  });

  it('dashboard sin agente pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce({ total_tickets: 0 });
    await ticketsSoporteService.dashboard();
    expect(get).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/dashboard/');
  });

  it('dashboard con agente agrega el query param', async () => {
    vi.mocked(get).mockResolvedValueOnce({ total_tickets: 1 });
    const r = await ticketsSoporteService.dashboard('ag1');
    expect(get).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/dashboard/?agente_id=ag1');
    expect(r.total_tickets).toBe(1);
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_ticket: 't1' });
    await ticketsSoporteService.create(ticketPayload);
    expect(post).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/', ticketPayload);
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValueOnce({ id_ticket: 't1' });
    await ticketsSoporteService.update('t1', ticketPayload);
    expect(patch).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/', ticketPayload);
  });

  it('remove elimina por id', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await ticketsSoporteService.remove('t1');
    expect(del).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/');
  });

  it('asignarAgente postea el agente_id', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_ticket: 't1', estado_ticket: 'ASIGNADO' });
    await ticketsSoporteService.asignarAgente('t1', 'ag1');
    expect(post).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/asignar_agente/', {
      agente_id: 'ag1',
    });
  });

  it('cambiarEstado sin comentario manda solo estado', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_ticket: 't1' });
    await ticketsSoporteService.cambiarEstado('t1', 'EN_PROGRESO');
    expect(post).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/cambiar_estado/', {
      estado: 'EN_PROGRESO',
    });
  });

  it('cambiarEstado con comentario lo incluye', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_ticket: 't1' });
    await ticketsSoporteService.cambiarEstado('t1', 'RESUELTO', 'Listo');
    expect(post).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/cambiar_estado/', {
      estado: 'RESUELTO',
      comentario: 'Listo',
    });
  });

  it('cambiarEstado con comentario vacío lo omite (rama falsy)', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_ticket: 't1' });
    await ticketsSoporteService.cambiarEstado('t1', 'CERRADO', '');
    expect(post).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/cambiar_estado/', {
      estado: 'CERRADO',
    });
  });

  it('escalar sin datos manda cuerpo vacío', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_ticket: 't1', estado_ticket: 'ESCALADO' });
    await ticketsSoporteService.escalar('t1');
    expect(post).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/escalar/', {});
  });

  it('escalar con razón y nuevo agente los incluye', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_ticket: 't1' });
    await ticketsSoporteService.escalar('t1', { razon: 'sin solución', nuevo_agente_id: 'ag2' });
    expect(post).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/escalar/', {
      razon: 'sin solución',
      nuevo_agente_id: 'ag2',
    });
  });

  it('escalar con campos vacíos los omite (ramas falsy)', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_ticket: 't1' });
    await ticketsSoporteService.escalar('t1', { razon: '', nuevo_agente_id: null });
    expect(post).toHaveBeenCalledWith('/servicio-cliente/tickets-soporte/t1/escalar/', {});
  });

  it('cambiarEstado propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('estado inválido'));
    await expect(ticketsSoporteService.cambiarEstado('t1', 'CERRADO')).rejects.toThrow('inválido');
  });
});

// ── interaccionesTicketService ────────────────────────────────────────────────

describe('interaccionesTicketService', () => {
  it('getAll filtra por ticket en cliente y arma query', async () => {
    vi.mocked(get).mockResolvedValueOnce([
      { id_interaccion: 'i1', id_ticket: 't1' },
      { id_interaccion: 'i2', id_ticket: 'otro' },
    ]);
    const r = await interaccionesTicketService.getAll({ ticket: 't1' });
    expect(get).toHaveBeenCalledWith('/servicio-cliente/interacciones-ticket/?id_ticket=t1');
    expect(r.map((i) => i.id_interaccion)).toEqual(['i1']);
  });

  it('getAll filtra sobre respuesta paginada', async () => {
    vi.mocked(get).mockResolvedValueOnce({
      results: [
        { id_interaccion: 'i1', id_ticket: 't1' },
        { id_interaccion: 'i2', id_ticket: 'otro' },
      ],
    });
    const r = await interaccionesTicketService.getAll({ ticket: 't1' });
    expect(r.map((i) => i.id_interaccion)).toEqual(['i1']);
  });

  it('getAll con ticket y tipo arma ambos params', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_interaccion: 'i1', id_ticket: 't1' }]);
    await interaccionesTicketService.getAll({ ticket: 't1', tipo: 'COMENTARIO' });
    expect(get).toHaveBeenCalledWith(
      '/servicio-cliente/interacciones-ticket/?id_ticket=t1&tipo_interaccion=COMENTARIO',
    );
  });

  it('getAll sin ticket devuelve la lista completa', async () => {
    vi.mocked(get).mockResolvedValueOnce([{ id_interaccion: 'i1', id_ticket: 't1' }]);
    const r = await interaccionesTicketService.getAll();
    expect(get).toHaveBeenCalledWith('/servicio-cliente/interacciones-ticket/');
    expect(r.length).toBe(1);
  });

  it('getAll solo con tipo arma el query', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await interaccionesTicketService.getAll({ tipo: 'LLAMADA' });
    expect(get).toHaveBeenCalledWith(
      '/servicio-cliente/interacciones-ticket/?tipo_interaccion=LLAMADA',
    );
  });

  it('getAll ante respuesta inesperada devuelve []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await interaccionesTicketService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_interaccion: 'i1' });
    await interaccionesTicketService.getById('i1');
    expect(get).toHaveBeenCalledWith('/servicio-cliente/interacciones-ticket/i1/');
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_interaccion: 'i1' });
    await interaccionesTicketService.create(interaccionPayload);
    expect(post).toHaveBeenCalledWith(
      '/servicio-cliente/interacciones-ticket/',
      interaccionPayload,
    );
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValueOnce({ id_interaccion: 'i1' });
    await interaccionesTicketService.update('i1', interaccionPayload);
    expect(patch).toHaveBeenCalledWith(
      '/servicio-cliente/interacciones-ticket/i1/',
      interaccionPayload,
    );
  });

  it('remove elimina por id', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await interaccionesTicketService.remove('i1');
    expect(del).toHaveBeenCalledWith('/servicio-cliente/interacciones-ticket/i1/');
  });

  it('agregarComentario postea ticket_id y contenido', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_interaccion: 'i1' });
    await interaccionesTicketService.agregarComentario('t1', 'Hola');
    expect(post).toHaveBeenCalledWith('/servicio-cliente/interacciones-ticket/agregar_comentario/', {
      ticket_id: 't1',
      contenido: 'Hola',
    });
  });

  it('agregarComentario propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('contenido requerido'));
    await expect(interaccionesTicketService.agregarComentario('t1', '')).rejects.toThrow(
      'requerido',
    );
  });
});

// ── articulosConocimientoService ──────────────────────────────────────────────

describe('articulosConocimientoService', () => {
  it('getAll arma el querystring con todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_articulo: 'a1' }] });
    const r = await articulosConocimientoService.getAll({
      empresa: 'e1',
      visibilidad: 'PUBLICA',
      categoria: 'cat1',
      search: 'reiniciar',
    });
    expect(get).toHaveBeenCalledWith(
      '/servicio-cliente/articulos-conocimiento/?id_empresa=e1&visibilidad=PUBLICA&id_categoria_ticket=cat1&search=reiniciar',
    );
    expect(r).toEqual([{ id_articulo: 'a1' }]);
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await articulosConocimientoService.getAll();
    expect(get).toHaveBeenCalledWith('/servicio-cliente/articulos-conocimiento/');
  });

  it('getAll solo con visibilidad', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await articulosConocimientoService.getAll({ visibilidad: 'INTERNA' });
    expect(get).toHaveBeenCalledWith('/servicio-cliente/articulos-conocimiento/?visibilidad=INTERNA');
  });

  it('getAll normaliza respuesta inesperada a []', async () => {
    vi.mocked(get).mockResolvedValueOnce(undefined as unknown as never);
    expect(await articulosConocimientoService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_articulo: 'a1' });
    await articulosConocimientoService.getById('a1');
    expect(get).toHaveBeenCalledWith('/servicio-cliente/articulos-conocimiento/a1/');
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_articulo: 'a1' });
    await articulosConocimientoService.create(articuloPayload);
    expect(post).toHaveBeenCalledWith('/servicio-cliente/articulos-conocimiento/', articuloPayload);
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValueOnce({ id_articulo: 'a1' });
    await articulosConocimientoService.update('a1', articuloPayload);
    expect(patch).toHaveBeenCalledWith(
      '/servicio-cliente/articulos-conocimiento/a1/',
      articuloPayload,
    );
  });

  it('remove elimina por id', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await articulosConocimientoService.remove('a1');
    expect(del).toHaveBeenCalledWith('/servicio-cliente/articulos-conocimiento/a1/');
  });

  it('create propaga el error del backend', async () => {
    vi.mocked(post).mockRejectedValueOnce(new Error('título requerido'));
    await expect(articulosConocimientoService.create(articuloPayload)).rejects.toThrow('requerido');
  });
});

// ── feedbackClienteService ────────────────────────────────────────────────────

describe('feedbackClienteService', () => {
  it('getAll arma el querystring con todos los filtros', async () => {
    vi.mocked(get).mockResolvedValueOnce({ results: [{ id_feedback: 'f1' }] });
    const r = await feedbackClienteService.getAll({ empresa: 'e1', tipo: 'QUEJA', ticket: 't1' });
    expect(get).toHaveBeenCalledWith(
      '/servicio-cliente/feedback-cliente/?id_empresa=e1&tipo_feedback=QUEJA&id_ticket_origen=t1',
    );
    expect(r).toEqual([{ id_feedback: 'f1' }]);
  });

  it('getAll sin parámetros pega al endpoint base', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await feedbackClienteService.getAll();
    expect(get).toHaveBeenCalledWith('/servicio-cliente/feedback-cliente/');
  });

  it('getAll solo con tipo', async () => {
    vi.mocked(get).mockResolvedValueOnce([]);
    await feedbackClienteService.getAll({ tipo: 'SUGERENCIA' });
    expect(get).toHaveBeenCalledWith('/servicio-cliente/feedback-cliente/?tipo_feedback=SUGERENCIA');
  });

  it('getAll normaliza respuesta inesperada a []', async () => {
    vi.mocked(get).mockResolvedValueOnce(null as unknown as never);
    expect(await feedbackClienteService.getAll()).toEqual([]);
  });

  it('getById pega al detalle', async () => {
    vi.mocked(get).mockResolvedValueOnce({ id_feedback: 'f1' });
    await feedbackClienteService.getById('f1');
    expect(get).toHaveBeenCalledWith('/servicio-cliente/feedback-cliente/f1/');
  });

  it('create postea el payload', async () => {
    vi.mocked(post).mockResolvedValueOnce({ id_feedback: 'f1' });
    await feedbackClienteService.create(feedbackPayload);
    expect(post).toHaveBeenCalledWith('/servicio-cliente/feedback-cliente/', feedbackPayload);
  });

  it('update parchea por id', async () => {
    vi.mocked(patch).mockResolvedValueOnce({ id_feedback: 'f1' });
    await feedbackClienteService.update('f1', feedbackPayload);
    expect(patch).toHaveBeenCalledWith('/servicio-cliente/feedback-cliente/f1/', feedbackPayload);
  });

  it('remove elimina por id', async () => {
    vi.mocked(del).mockResolvedValueOnce(undefined);
    await feedbackClienteService.remove('f1');
    expect(del).toHaveBeenCalledWith('/servicio-cliente/feedback-cliente/f1/');
  });

  it('remove propaga el error del backend', async () => {
    vi.mocked(del).mockRejectedValueOnce(new Error('no encontrado'));
    await expect(feedbackClienteService.remove('f1')).rejects.toThrow('encontrado');
  });
});
