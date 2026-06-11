"""
Backfill de cobertura — apps/agentes/personalizacion_agente.py (plan "Cero Dudas").

Cero llamadas de red: nunca se instancia un cliente Anthropic real (se controla
la variable de entorno y/o se inyecta un mock).

BUG DOCUMENTADO (sin enmascarar):
- ``_analizar_flujo_documentos`` lee ``c.nombre_paso`` pero el modelo
  ``ConfiguracionFlujoDocumentos`` define el campo como ``paso`` → AttributeError
  silencioso cuando la empresa SÍ tiene configuración, que degrada al fallback
  "CONFIGURACION_FLUJO". Ver ``test_bug_nombre_paso_degrada_a_fallback``.
"""
import sys
from decimal import Decimal
from unittest import mock

import pytest

from apps.agentes.personalizacion_agente import (
    AGENTE_ID,
    PersonalizacionCapa2Agent,
    ResultadoPersonalizacionCapa2,
    _analizar_flujo_documentos,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _sin_api_key(monkeypatch):
    """Garantiza cero red: sin API key no se intenta crear cliente LLM."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


# ── Constructor ───────────────────────────────────────────────────────────────


class TestConstructor:
    def test_sin_llm_usa_fallback(self, empresa_a):
        agente = PersonalizacionCapa2Agent(empresa=empresa_a)
        assert agente._usar_llm is False
        assert agente._llm_client is None

    def test_llm_client_inyectado(self, empresa_a):
        fake = mock.Mock()
        agente = PersonalizacionCapa2Agent(empresa=empresa_a, llm_client=fake)
        assert agente._usar_llm is True
        assert agente._llm_client is fake

    def test_api_key_sin_sdk_degrada(self, empresa_a, monkeypatch):
        """Con API key pero sin SDK instalado → ImportError → fallback."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-dummy-no-usar")
        monkeypatch.setitem(sys.modules, "anthropic", None)  # import → ImportError
        agente = PersonalizacionCapa2Agent(empresa=empresa_a)
        assert agente._usar_llm is False

    def test_constantes_del_agente(self):
        assert AGENTE_ID == "personalizacion_capa2"
        assert PersonalizacionCapa2Agent.MODELO_DEFAULT.startswith("claude-")


# ── sugerir_credito (entrada directa, sin BD) ────────────────────────────────


class TestSugerirCredito:
    def _agente(self, empresa_a):
        return PersonalizacionCapa2Agent(empresa=empresa_a)

    def test_mora_alta_reduce_30pct(self, empresa_a):
        s = self._agente(empresa_a).sugerir_credito(
            "ACME", Decimal("1000.00"), cxc_vencidas=4, cxc_pagadas=6
        )
        assert s.riesgo == "alto"
        assert s.limite_sugerido == Decimal("700.00")
        assert "40%" in s.razonamiento

    def test_buen_historial_aumenta_25pct(self, empresa_a):
        s = self._agente(empresa_a).sugerir_credito(
            "ACME", Decimal("1000.00"), cxc_vencidas=0, cxc_pagadas=5
        )
        assert s.riesgo == "bajo"
        assert s.limite_sugerido == Decimal("1250.00")

    def test_historial_mixto_mantiene_limite(self, empresa_a):
        s = self._agente(empresa_a).sugerir_credito(
            "ACME", Decimal("500.00"), cxc_vencidas=1, cxc_pagadas=9
        )
        assert s.riesgo == "medio"
        assert s.limite_sugerido == Decimal("500.00")

    def test_sin_historial_mantiene_limite(self, empresa_a):
        """total=0 → tasa_mora 0 pero cxc_pagadas < 5 → riesgo medio."""
        s = self._agente(empresa_a).sugerir_credito(
            "Nuevo", Decimal("100.00"), cxc_vencidas=0, cxc_pagadas=0
        )
        assert s.riesgo == "medio"
        assert s.limite_sugerido == Decimal("100.00")


# ── analizar() contra la BD ───────────────────────────────────────────────────


@pytest.fixture
def unidad(db, empresa_a):
    from apps.inventario.models import UnidadMedida
    return UnidadMedida.objects.create(id_empresa=empresa_a, nombre="Unidad", abreviatura="UN")


@pytest.fixture
def categoria(db, empresa_a):
    from apps.inventario.models import CategoriaProducto
    return CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat Agente")


def _producto(empresa, unidad, categoria, moneda, nombre, costo, precio):
    from apps.inventario.models import Producto
    return Producto.objects.create(
        id_empresa=empresa,
        nombre_producto=nombre,
        id_unidad_medida_base=unidad,
        id_categoria=categoria,
        id_moneda_precio=moneda,
        costo_promedio=costo,
        precio_venta_sugerido=precio,
    )


def _cliente(empresa, nombre, rif, limite):
    from apps.crm.models import Cliente
    return Cliente.objects.create(
        id_empresa=empresa,
        razon_social=nombre,
        rif=rif,
        tipo_cliente="CREDITO",
        limite_credito=limite,
    )


def _cxc(empresa, cliente, estado, monto="100.00"):
    from datetime import date
    from apps.cuentas_por_cobrar.models import CuentaPorCobrar
    return CuentaPorCobrar.objects.create(
        cliente=cliente,
        empresa=empresa,
        monto=Decimal(monto),
        fecha_emision=date(2026, 1, 1),
        fecha_vencimiento=date(2026, 2, 1),
        estado=estado,
    )


class TestAnalizar:
    def test_empresa_vacia_sin_sugerencias(self, empresa_a):
        res = PersonalizacionCapa2Agent(empresa=empresa_a).analizar()
        assert isinstance(res, ResultadoPersonalizacionCapa2)
        assert res.flujo_documentos == []
        assert res.listas_precios == []
        assert res.credito_clientes == []
        assert res.modelo_llm == "fallback-reglas"

    def test_producto_bajo_margen_sugiere_ajuste(self, empresa_a, unidad, categoria, moneda_usd):
        # Margen 5% (< 15%) → sugerencia
        _producto(empresa_a, unidad, categoria, moneda_usd, "Bajo margen",
                  Decimal("100.0000"), Decimal("105.0000"))
        # Margen 50% → sin sugerencia adicional
        _producto(empresa_a, unidad, categoria, moneda_usd, "Buen margen",
                  Decimal("100.0000"), Decimal("150.0000"))

        res = PersonalizacionCapa2Agent(empresa=empresa_a).analizar()
        assert len(res.listas_precios) == 1
        sugerencia = res.listas_precios[0]
        assert sugerencia.aplicar_a == "productos_bajo_margen"
        assert sugerencia.ajuste_porcentual == Decimal("10.00")
        assert "1 producto(s)" in sugerencia.descripcion

    def test_credito_buen_pagador_y_moroso(self, empresa_a, moneda_usd):
        bueno = _cliente(empresa_a, "Buen Pagador", "J-11111111", Decimal("1000.00"))
        for _ in range(5):
            _cxc(empresa_a, bueno, "pagada")

        moroso = _cliente(empresa_a, "Moroso", "J-22222222", Decimal("2000.00"))
        for _ in range(4):
            _cxc(empresa_a, moroso, "vencida")
        _cxc(empresa_a, moroso, "pagada")

        # Sin historial ni límite → no genera sugerencia
        _cliente(empresa_a, "Nuevo", "J-33333333", Decimal("0.00"))

        res = PersonalizacionCapa2Agent(empresa=empresa_a).analizar()
        por_nombre = {s.cliente_nombre: s for s in res.credito_clientes}
        assert set(por_nombre) == {"Buen Pagador", "Moroso"}

        assert por_nombre["Buen Pagador"].riesgo == "bajo"
        assert por_nombre["Buen Pagador"].limite_sugerido == Decimal("1250.00")
        assert por_nombre["Moroso"].riesgo == "alto"
        assert por_nombre["Moroso"].limite_sugerido == Decimal("1400.00")

    def test_cliente_con_limite_pero_sin_cxc_se_omite(self, empresa_a):
        _cliente(empresa_a, "Sin Historial", "J-44444444", Decimal("500.00"))
        res = PersonalizacionCapa2Agent(empresa=empresa_a).analizar()
        assert res.credito_clientes == []

    def test_cliente_con_historial_pero_sin_limite_se_omite(self, empresa_a):
        """limite_credito <= 0 → no se sugiere nada aunque tenga historial."""
        cliente = _cliente(empresa_a, "Sin Límite", "J-55555555", Decimal("0.00"))
        for _ in range(5):
            _cxc(empresa_a, cliente, "pagada")
        res = PersonalizacionCapa2Agent(empresa=empresa_a).analizar()
        assert res.credito_clientes == []

    def test_analisis_resiliente_a_excepciones_internas(self, monkeypatch):
        """Si un analizador revienta, analizar() lo registra en advertencias."""
        import apps.agentes.personalizacion_agente as mod

        empresa = mock.Mock(pk="emp-x")
        monkeypatch.setattr(
            mod, "_analizar_flujo_documentos", mock.Mock(side_effect=RuntimeError("f"))
        )
        monkeypatch.setattr(
            mod, "_analizar_listas_precios", mock.Mock(side_effect=RuntimeError("p"))
        )
        monkeypatch.setattr(
            mod, "_analizar_credito_clientes", mock.Mock(side_effect=RuntimeError("c"))
        )
        res = PersonalizacionCapa2Agent(empresa=empresa).analizar()
        assert len(res.advertencias) == 3
        assert any(a.startswith("Flujo documentos:") for a in res.advertencias)
        assert any(a.startswith("Listas de precios:") for a in res.advertencias)
        assert any(a.startswith("Crédito clientes:") for a in res.advertencias)

    def test_analizadores_degradan_con_empresa_invalida(self):
        """Las funciones por dominio capturan su propia excepción y devuelven []."""
        from apps.agentes.personalizacion_agente import (
            _analizar_credito_clientes,
            _analizar_listas_precios,
        )
        assert _analizar_listas_precios(object()) == []
        assert _analizar_credito_clientes(object()) == []


class TestFlujoDocumentos:
    def test_bug_nombre_paso_degrada_a_fallback(self, empresa_a):
        """BUG documentado: el análisis usa ``c.nombre_paso`` pero el campo real es
        ``paso`` → AttributeError capturado por el except genérico, que devuelve la
        sugerencia fallback CONFIGURACION_FLUJO aunque la empresa SÍ tiene config.
        Si se corrige el nombre del campo, este test debe actualizarse para
        verificar las sugerencias reales (APROBACION_PEDIDO / COTIZACION).
        """
        from apps.core.models import ConfiguracionFlujoDocumentos
        ConfiguracionFlujoDocumentos.objects.create(
            id_empresa=empresa_a,
            tipo_documento="VENTAS",
            paso="COTIZACION",
            obligatorio=False,
        )
        sugerencias = _analizar_flujo_documentos(empresa_a)
        assert len(sugerencias) == 1
        assert sugerencias[0].paso == "CONFIGURACION_FLUJO"
        assert sugerencias[0].prioridad == "alta"

    def test_empresa_invalida_devuelve_fallback(self):
        """Cualquier excepción degrada al fallback de revisión manual."""
        sugerencias = _analizar_flujo_documentos(object())
        assert len(sugerencias) == 1
        assert sugerencias[0].paso == "CONFIGURACION_FLUJO"
        assert sugerencias[0].accion == "revisar"
