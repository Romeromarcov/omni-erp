"""
Cobertura de apps/cxc/agents/cobranza_agent.py — CobranzaAgent (streaming async).

El SDK de Anthropic se mockea SIEMPRE (cero llamadas de red): se parchea
``CobranzaAgent._get_client`` con un cliente falso cuyo ``messages.stream``
es un context manager que emite texto, y se verifica que el contexto que el
agente construye desde la BD (cartera, tasa BCV, acuerdos, historial) llegue
al prompt del modelo.
"""
import sys
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.cxc.agents.cobranza_agent import CobranzaAgent

pytestmark = pytest.mark.django_db


def _collect(agen) -> list[str]:
    """
    Consume un AsyncIterator[str] SIN event loop.

    Los métodos de CobranzaAgent son ``async def`` pero no contienen ningún
    ``await`` real (hacen ORM síncrono — hallazgo: bajo un event loop real
    Django lanza SynchronousOnlyOperation y, además, usaría una conexión
    distinta a la de la transacción de test). Al avanzar el generador con
    ``send(None)`` directamente, el cuerpo corre en el contexto síncrono del
    test, sobre la misma conexión/transacción de pytest-django.
    """
    out: list[str] = []
    while True:
        coro = agen.__anext__()
        try:
            coro.send(None)
        except StopIteration as si:  # __anext__ produjo un chunk
            out.append(si.value)
        except StopAsyncIteration:  # generador agotado
            break
    return out


def _cliente_stream_falso(textos):
    """Cliente Anthropic falso: messages.stream(...) → CM cuyo text_stream emite textos."""
    stream = MagicMock()
    stream.text_stream = iter(textos)
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=stream)
    cm.__exit__ = MagicMock(return_value=False)
    cliente = MagicMock()
    cliente.messages.stream.return_value = cm
    return cliente


@pytest.fixture
def cliente_deudor(empresa_a):
    from tests.factories import ClienteFactory

    return ClienteFactory(id_empresa=empresa_a, razon_social="Deudor Llanero C.A.")


@pytest.fixture
def cxc_vencida(empresa_a, cliente_deudor):
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar

    hoy = date.today()
    return CuentaPorCobrar.objects.create(
        cliente=cliente_deudor,
        empresa=empresa_a,
        monto=Decimal("600.00"),
        fecha_emision=hoy - timedelta(days=45),
        fecha_vencimiento=hoy - timedelta(days=15),
        estado="pendiente",
    )


class TestGetClient:
    def test_sin_sdk_lanza_runtimeerror(self, empresa_a):
        agente = CobranzaAgent(str(empresa_a.id_empresa))
        with patch.dict(sys.modules, {"anthropic": None}):
            with pytest.raises(RuntimeError, match="anthropic SDK no instalado"):
                agente._get_client()


class TestAnalizarCartera:
    def test_streaming_con_contexto_de_cartera(self, empresa_a, cxc_vencida):
        cliente = _cliente_stream_falso(["Plan de ", "cobranza listo."])
        agente = CobranzaAgent(str(empresa_a.id_empresa))

        with patch.object(CobranzaAgent, "_get_client", return_value=cliente):
            chunks = _collect(agente.analizar_cartera(top_n=5))

        assert chunks == ["Plan de ", "cobranza listo."]

        kwargs = cliente.messages.stream.call_args.kwargs
        prompt_usuario = kwargs["messages"][0]["content"]
        # Contexto real construido desde la BD
        assert "Deudor Llanero C.A." in prompt_usuario
        assert "$600.00" in prompt_usuario
        assert "15 días vencido" in prompt_usuario
        assert "Tasa BCV hoy: N/D" in prompt_usuario  # sin tasa registrada
        assert kwargs["system"].startswith("Eres el Agente de Cobranza Inteligente")

    def test_con_tasa_bcv_del_dia(self, empresa_a, cxc_vencida, moneda_usd):
        from apps.finanzas.models import Moneda, TasaCambio

        ves = Moneda.objects.create(
            nombre="Bolívar", codigo_iso="VES", simbolo="Bs", tipo_moneda="fiat"
        )
        TasaCambio.objects.create(
            id_moneda_origen=moneda_usd, id_moneda_destino=ves,
            tipo_tasa="OFICIAL_BCV", valor_tasa=Decimal("37.12345678"),
            fecha_tasa=date.today(),
        )
        cliente = _cliente_stream_falso(["ok"])
        agente = CobranzaAgent(str(empresa_a.id_empresa))

        with patch.object(CobranzaAgent, "_get_client", return_value=cliente):
            _collect(agente.analizar_cartera())

        prompt_usuario = cliente.messages.stream.call_args.kwargs["messages"][0]["content"]
        assert "37.12345678" in prompt_usuario

    def test_error_no_propaga_sino_que_yield_mensaje(self, db):
        """empresa_id inválido → Empresa.DoesNotExist capturado → texto de error."""
        agente = CobranzaAgent("00000000-0000-0000-0000-000000000000")
        cliente = _cliente_stream_falso(["nunca llega"])

        with patch.object(CobranzaAgent, "_get_client", return_value=cliente):
            chunks = _collect(agente.analizar_cartera())

        assert len(chunks) == 1
        assert chunks[0].startswith("Error al analizar cartera:")
        cliente.messages.stream.assert_not_called()


class TestGestionarCliente:
    def test_contexto_completo_con_acuerdo_historial_e_instrucciones(
        self, empresa_a, cliente_deudor, cxc_vencida
    ):
        from apps.cxc.models import AcuerdoPago, CuotaAcuerdo, GestionCobranza

        acuerdo = AcuerdoPago.objects.create(
            empresa=empresa_a,
            cliente_id=str(cliente_deudor.id_cliente),
            cliente_nombre="Deudor Llanero C.A.",
            monto_total=Decimal("600.0000"),
            periodicidad="quincenal",
            fecha_inicio=date.today(),
        )
        CuotaAcuerdo.objects.create(
            acuerdo=acuerdo, numero_cuota=1,
            fecha_vencimiento=date.today() + timedelta(days=15),
            monto=Decimal("300.0000"), estado="pendiente",
        )
        GestionCobranza.objects.create(
            empresa=empresa_a,
            cliente_id=str(cliente_deudor.id_cliente),
            cliente_nombre="Deudor Llanero C.A.",
            canal="whatsapp",
            resultado="sin_respuesta",
            fecha_gestion=date.today() - timedelta(days=2),
        )

        cliente_llm = _cliente_stream_falso(["Recomendación: ", "seguimiento de cuotas."])
        agente = CobranzaAgent(str(empresa_a.id_empresa))

        with patch.object(CobranzaAgent, "_get_client", return_value=cliente_llm):
            chunks = _collect(
                agente.gestionar_cliente(
                    str(cliente_deudor.id_cliente),
                    instrucciones="Ofrecer descuento por pronto pago",
                )
            )

        assert "".join(chunks) == "Recomendación: seguimiento de cuotas."

        prompt = cliente_llm.messages.stream.call_args.kwargs["messages"][0]["content"]
        assert "Deudor Llanero C.A." in prompt
        assert "Deuda total pendiente: $600.00" in prompt
        assert "Días máximos vencido: 15" in prompt
        assert "ACUERDO VIGENTE: $600.0000 — quincenal" in prompt
        assert "Cuotas pendientes: 1" in prompt
        assert "whatsapp → sin_respuesta" in prompt
        assert "Instrucciones especiales: Ofrecer descuento por pronto pago" in prompt

    def test_cliente_sin_datos_contexto_minimo(self, empresa_a):
        """Sin partidas/acuerdos/historial: solo el encabezado con el id."""
        cliente_llm = _cliente_stream_falso(["sin datos"])
        agente = CobranzaAgent(str(empresa_a.id_empresa))

        with patch.object(CobranzaAgent, "_get_client", return_value=cliente_llm):
            chunks = _collect(agente.gestionar_cliente("cliente-inexistente"))

        assert chunks == ["sin datos"]
        prompt = cliente_llm.messages.stream.call_args.kwargs["messages"][0]["content"]
        assert "Cliente ID: cliente-inexistente" in prompt
        assert "ACUERDO VIGENTE" not in prompt
        assert "Últimas gestiones" not in prompt

    def test_error_yield_mensaje_con_cliente_id(self, db):
        agente = CobranzaAgent("00000000-0000-0000-0000-000000000000")
        chunks = _collect(agente.gestionar_cliente("cli-1"))
        assert len(chunks) == 1
        assert chunks[0].startswith("Error al gestionar cliente cli-1:")
