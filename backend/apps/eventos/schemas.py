"""
Schemas de eventos definidos con dataclasses.

Cada evento de dominio sigue el envelope estándar (EventoBase) más
un payload tipado específico del contexto de negocio.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Envelope base ─────────────────────────────────────────────────────────────

@dataclass
class EventoBase:
    event_id: str
    event_type: str
    timestamp: str
    empresa_id: str | None
    version: str
    payload: dict[str, Any]


# ── Payloads de Ventas ────────────────────────────────────────────────────────

@dataclass
class PedidoCreadoPayload:
    pedido_id: int
    numero: str | None
    cliente_id: int | None
    total: float | None
    moneda: str | None
    estado: str | None
    fecha_pedido: str | None


@dataclass
class PedidoActualizadoPayload:
    pedido_id: int
    numero: str | None
    estado: str | None
    campos_modificados: list[str] = field(default_factory=list)


@dataclass
class FacturaCreadaPayload:
    factura_id: int
    numero_factura: str | None
    cliente_id: int | None
    total: float | None
    moneda: str | None
    estado: str | None
    pedido_id: int | None


# ── Payloads de Inventario ────────────────────────────────────────────────────

@dataclass
class MovimientoCreadoPayload:
    movimiento_id: int
    tipo_movimiento: str | None
    producto_id: int | None
    cantidad: float | None
    almacen_id: int | None
    referencia: str | None
    fecha: str | None


# ── Payloads de Finanzas ──────────────────────────────────────────────────────

@dataclass
class PagoRegistradoPayload:
    pago_id: int
    monto: float | None
    moneda: str | None
    metodo_pago_id: int | None
    referencia: str | None
    fecha_pago: str | None
    pedido_id: int | None
