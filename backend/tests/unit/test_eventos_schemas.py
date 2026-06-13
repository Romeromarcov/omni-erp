"""
Cobertura de apps/eventos/schemas.py — dataclasses puras del envelope de eventos.

Verifica construcción, defaults (field(default_factory=list)) y que asdict()
produzca el payload serializable esperado para el bus de eventos.
"""
from dataclasses import asdict, fields

from apps.eventos.schemas import (
    EventoBase,
    FacturaCreadaPayload,
    MovimientoCreadoPayload,
    PagoRegistradoPayload,
    PedidoActualizadoPayload,
    PedidoCreadoPayload,
)
import pytest

pytestmark = pytest.mark.unit


class TestEventoBase:
    def test_envelope_completo(self):
        ev = EventoBase(
            event_id="evt-1",
            event_type="omni.ventas.pedido.creado",
            timestamp="2026-06-09T12:00:00Z",
            empresa_id="emp-1",
            version="1.0",
            payload={"pedido_id": 7},
        )
        assert asdict(ev) == {
            "event_id": "evt-1",
            "event_type": "omni.ventas.pedido.creado",
            "timestamp": "2026-06-09T12:00:00Z",
            "empresa_id": "emp-1",
            "version": "1.0",
            "payload": {"pedido_id": 7},
        }

    def test_empresa_id_acepta_none(self):
        ev = EventoBase(
            event_id="e", event_type="t", timestamp="ts",
            empresa_id=None, version="1.0", payload={},
        )
        assert ev.empresa_id is None


class TestPayloadsVentas:
    def test_pedido_creado(self):
        p = PedidoCreadoPayload(
            pedido_id=1, numero="P-001", cliente_id=2, total=100.5,
            moneda="USD", estado="PENDIENTE", fecha_pedido="2026-06-09",
        )
        assert asdict(p) == {
            "pedido_id": 1, "numero": "P-001", "cliente_id": 2, "total": 100.5,
            "moneda": "USD", "estado": "PENDIENTE", "fecha_pedido": "2026-06-09",
        }

    def test_pedido_actualizado_default_campos_modificados(self):
        p = PedidoActualizadoPayload(pedido_id=1, numero="P-001", estado="APROBADO")
        assert p.campos_modificados == []

        # default_factory: cada instancia tiene su propia lista
        p2 = PedidoActualizadoPayload(pedido_id=2, numero=None, estado=None)
        p.campos_modificados.append("estado")
        assert p2.campos_modificados == []

    def test_pedido_actualizado_con_campos(self):
        p = PedidoActualizadoPayload(
            pedido_id=9, numero="P-009", estado="ANULADO",
            campos_modificados=["estado", "observaciones"],
        )
        assert p.campos_modificados == ["estado", "observaciones"]

    def test_factura_creada(self):
        f = FacturaCreadaPayload(
            factura_id=3, numero_factura="FAC-00000001", cliente_id=2,
            total=250.0, moneda="VES", estado="EMITIDA", pedido_id=1,
        )
        assert f.numero_factura == "FAC-00000001"
        assert f.pedido_id == 1
        assert {f.name for f in fields(FacturaCreadaPayload)} == {
            "factura_id", "numero_factura", "cliente_id", "total",
            "moneda", "estado", "pedido_id",
        }


class TestPayloadInventario:
    def test_movimiento_creado(self):
        m = MovimientoCreadoPayload(
            movimiento_id=5, tipo_movimiento="ENTRADA", producto_id=8,
            cantidad=12.5, almacen_id=4, referencia="OC-77", fecha="2026-06-09",
        )
        assert asdict(m) == {
            "movimiento_id": 5, "tipo_movimiento": "ENTRADA", "producto_id": 8,
            "cantidad": 12.5, "almacen_id": 4, "referencia": "OC-77",
            "fecha": "2026-06-09",
        }

    def test_campos_opcionales_aceptan_none(self):
        m = MovimientoCreadoPayload(
            movimiento_id=1, tipo_movimiento=None, producto_id=None,
            cantidad=None, almacen_id=None, referencia=None, fecha=None,
        )
        assert m.tipo_movimiento is None
        assert m.cantidad is None


class TestPayloadFinanzas:
    def test_pago_registrado(self):
        p = PagoRegistradoPayload(
            pago_id=11, monto=99.99, moneda="USD", metodo_pago_id=2,
            referencia="ZELLE-123", fecha_pago="2026-06-09", pedido_id=None,
        )
        assert p.pago_id == 11
        assert p.monto == 99.99
        assert p.referencia == "ZELLE-123"
        assert p.pedido_id is None
