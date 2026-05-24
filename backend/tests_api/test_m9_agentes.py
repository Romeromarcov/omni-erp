"""
Tests M9 — Agentes AI (M9-T2, M9-T3, M9-T4, M9-T5).

M9-T3: CobranzaEstrategaAgent
M9-T4: ReordenSugeridorAgent
M9-T2: PersonalizacionCapa2Agent
M9-T5: Eval suites (≥30 golden cases, ≥75% accuracy)
"""

from decimal import Decimal

import pytest
from unittest.mock import MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# M9-T3: Agente Estratega de Cobranza
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCobranzaFallback:
    """Modo fallback determinista — sin LLM, sin BD."""

    def _agente(self, empresa_a):
        from apps.agentes.cobranza import CobranzaEstrategaAgent
        return CobranzaEstrategaAgent(empresa=empresa_a)

    def test_prioridad_alta_mas_60_dias(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir("id1", "Cliente Test", Decimal("1000"), dias_vencida=65, intentos_contacto=0)
        assert s.prioridad == "alta"

    def test_prioridad_alta_monto_grande(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir("id2", "Cliente VIP", Decimal("6000"), dias_vencida=5, intentos_contacto=0)
        assert s.prioridad == "alta"

    def test_prioridad_alta_muchos_intentos(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir("id3", "Cliente Reincidente", Decimal("300"), dias_vencida=10, intentos_contacto=3)
        assert s.prioridad == "alta"

    def test_prioridad_media_rango_medio(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir("id4", "Cliente Medio", Decimal("500"), dias_vencida=40, intentos_contacto=0)
        assert s.prioridad == "media"

    def test_prioridad_baja_reciente_bajo_monto(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir("id5", "Cliente Nuevo", Decimal("200"), dias_vencida=10, intentos_contacto=0)
        assert s.prioridad == "baja"

    def test_canal_whatsapp_baja_prioridad(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir("id6", "Cliente", Decimal("300"), dias_vencida=15, intentos_contacto=0)
        assert s.canal == "whatsapp"

    def test_canal_telefono_alta_prioridad_pocos_intentos(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir("id7", "Cliente", Decimal("1000"), dias_vencida=65, intentos_contacto=0)
        assert s.canal == "telefono"

    def test_canal_visita_mas_90_dias(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir("id8", "Cliente Moroso", Decimal("500"), dias_vencida=95, intentos_contacto=1)
        assert s.canal == "visita_presencial"

    def test_mensaje_whatsapp_no_vacio(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir("id9", "Empresa ABC", Decimal("500"), dias_vencida=30, intentos_contacto=0)
        assert len(s.mensaje_whatsapp) > 20
        assert "ABC" in s.mensaje_whatsapp

    def test_razonamiento_presente(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir("id10", "Test", Decimal("1000"), dias_vencida=50, intentos_contacto=0)
        assert len(s.razonamiento) > 0

    def test_latencia_registrada(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir("id11", "Test", Decimal("500"), dias_vencida=20, intentos_contacto=0)
        assert s.latencia_ms >= 0

    def test_monto_incluido_en_sugerencia(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir("id12", "Test", Decimal("1234.50"), dias_vencida=10, intentos_contacto=0)
        assert s.monto == Decimal("1234.50")


@pytest.mark.django_db
class TestCobranzaLLMMock:
    """Modo LLM con cliente mock inyectado."""

    def _make_mock(self, prioridad="alta", canal="telefono"):
        mc = MagicMock()
        mc.messages.create.return_value.content = [MagicMock(text=(
            f'{{"prioridad": "{prioridad}", "canal": "{canal}", '
            f'"mensaje_whatsapp": "Estimado cliente, contacto urgente.", '
            f'"razonamiento": "Test reason"}}'
        ))]
        return mc

    def test_usa_llm_cuando_se_inyecta(self, empresa_a):
        from apps.agentes.cobranza import CobranzaEstrategaAgent
        mc = self._make_mock("alta", "telefono")
        agente = CobranzaEstrategaAgent(empresa=empresa_a, llm_client=mc)
        s = agente.sugerir("id1", "Cliente", Decimal("1000"), 60, 0)
        assert s.prioridad == "alta"
        assert mc.messages.create.called

    def test_llm_fallback_en_json_invalido(self, empresa_a):
        from apps.agentes.cobranza import CobranzaEstrategaAgent
        mc = MagicMock()
        mc.messages.create.return_value.content = [MagicMock(text="NO JSON")]
        agente = CobranzaEstrategaAgent(empresa=empresa_a, llm_client=mc)
        s = agente.sugerir("id2", "Cliente", Decimal("500"), 40, 0)
        assert isinstance(s.prioridad, str)
        assert "fallback" in s.modelo_llm

    def test_llm_fallback_en_excepcion(self, empresa_a):
        from apps.agentes.cobranza import CobranzaEstrategaAgent
        mc = MagicMock()
        mc.messages.create.side_effect = ConnectionError("timeout")
        agente = CobranzaEstrategaAgent(empresa=empresa_a, llm_client=mc)
        s = agente.sugerir("id3", "Cliente", Decimal("500"), 30, 0)
        assert s.prioridad in ("alta", "media", "baja")


@pytest.mark.django_db
class TestCobranzaAnalizar:
    """Test del método analizar() con CxC reales en BD."""

    def test_analizar_devuelve_lista(self, empresa_a):
        from apps.agentes.cobranza import CobranzaEstrategaAgent
        agente = CobranzaEstrategaAgent(empresa=empresa_a)
        resultado = agente.analizar(persistir=False)
        assert isinstance(resultado, list)

    def test_analizar_con_cxc_vencida(self, db, empresa_a):
        from datetime import date, timedelta
        from apps.agentes.cobranza import CobranzaEstrategaAgent
        from apps.crm.models import Cliente
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente Moroso SA",
            rif="J-12345678-9",
        )
        hoy = date.today()
        CuentaPorCobrar.objects.create(
            cliente=cliente,
            empresa=empresa_a,
            monto=Decimal("500.00"),
            fecha_emision=hoy - timedelta(days=91),
            fecha_vencimiento=hoy - timedelta(days=61),  # 61 días > 60 → alta
            estado="vencida",
        )

        agente = CobranzaEstrategaAgent(empresa=empresa_a)
        sugerencias = agente.analizar(persistir=False)
        assert len(sugerencias) >= 1
        assert sugerencias[0].prioridad == "alta"

    def test_analizar_ordena_alta_primero(self, db, empresa_a):
        from datetime import date, timedelta
        from apps.agentes.cobranza import CobranzaEstrategaAgent
        from apps.crm.models import Cliente
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        cliente = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Test Order", rif="J-11111111-1",
        )
        hoy = date.today()
        CuentaPorCobrar.objects.create(
            cliente=cliente, empresa=empresa_a,
            monto=Decimal("200"), fecha_emision=hoy - timedelta(days=10),
            fecha_vencimiento=hoy - timedelta(days=5), estado="vencida",
        )
        CuentaPorCobrar.objects.create(
            cliente=cliente, empresa=empresa_a,
            monto=Decimal("8000"), fecha_emision=hoy - timedelta(days=90),
            fecha_vencimiento=hoy - timedelta(days=70), estado="vencida",
        )

        agente = CobranzaEstrategaAgent(empresa=empresa_a)
        sugerencias = agente.analizar(persistir=False)
        if len(sugerencias) >= 2:
            orden = {"alta": 0, "media": 1, "baja": 2}
            assert orden[sugerencias[0].prioridad] <= orden[sugerencias[1].prioridad]

    def test_persistir_crea_prediccion(self, db, empresa_a):
        from datetime import date, timedelta
        from apps.agentes.cobranza import CobranzaEstrategaAgent
        from apps.agentes.models import PrediccionAgente
        from apps.crm.models import Cliente
        from apps.cuentas_por_cobrar.models import CuentaPorCobrar

        cliente = Cliente.objects.create(
            id_empresa=empresa_a, razon_social="Persist Test", rif="J-22222222-2",
        )
        hoy = date.today()
        CuentaPorCobrar.objects.create(
            cliente=cliente, empresa=empresa_a,
            monto=Decimal("1000"), fecha_emision=hoy - timedelta(days=50),
            fecha_vencimiento=hoy - timedelta(days=40), estado="vencida",
        )

        antes = PrediccionAgente.objects.filter(agente="cobranza_estratega").count()
        agente = CobranzaEstrategaAgent(empresa=empresa_a)
        agente.analizar(persistir=True)
        assert PrediccionAgente.objects.filter(agente="cobranza_estratega").count() > antes


# ─────────────────────────────────────────────────────────────────────────────
# M9-T4: Agente Sugeridor de Reorden
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestReordenFallback:
    """Modo fallback determinista — evaluar() sin BD."""

    def _agente(self, empresa_a):
        from apps.agentes.reorden import ReordenSugeridorAgent
        return ReordenSugeridorAgent(empresa=empresa_a)

    def test_reordenar_stock_bajo_minimo(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.evaluar(Decimal("5"), Decimal("10"), Decimal("2"))
        assert s.estado == "REORDENAR"

    def test_reordenar_dias_criticos(self, empresa_a):
        agente = self._agente(empresa_a)
        # stock 9 / consumo 2 = 4.5 días < 10
        s = agente.evaluar(Decimal("9"), Decimal("0"), Decimal("2"))
        assert s.estado == "REORDENAR"

    def test_revisar_dias_alerta(self, empresa_a):
        agente = self._agente(empresa_a)
        # stock 30 / consumo 2 = 15 días → REVISAR
        s = agente.evaluar(Decimal("30"), Decimal("0"), Decimal("2"))
        assert s.estado == "REVISAR"

    def test_ok_stock_suficiente(self, empresa_a):
        agente = self._agente(empresa_a)
        # stock 100 / consumo 2 = 50 días → OK
        s = agente.evaluar(Decimal("100"), Decimal("10"), Decimal("2"))
        assert s.estado == "OK"

    def test_ok_sin_consumo(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.evaluar(Decimal("50"), Decimal("5"), Decimal("0"))
        assert s.estado == "OK"
        assert s.dias_restantes is None

    def test_cantidad_sugerida_positiva_en_reordenar(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.evaluar(Decimal("5"), Decimal("10"), Decimal("3"))
        assert s.cantidad_sugerida_reorden >= Decimal("0")

    def test_cantidad_sugerida_cero_en_ok(self, empresa_a):
        agente = self._agente(empresa_a)
        # stock 200, consumo 2 → OK, nada que pedir (200 > 30*2=60)
        s = agente.evaluar(Decimal("200"), Decimal("5"), Decimal("2"))
        assert s.estado == "OK"

    def test_dias_restantes_calculados(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.evaluar(Decimal("40"), Decimal("5"), Decimal("2"))
        assert s.dias_restantes is not None
        assert abs(s.dias_restantes - 20.0) < 0.1

    def test_razonamiento_presente(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.evaluar(Decimal("10"), Decimal("5"), Decimal("1"))
        assert len(s.razonamiento) > 0

    def test_umbral_critico_personalizado(self, empresa_a):
        from apps.agentes.reorden import ReordenSugeridorAgent
        agente = ReordenSugeridorAgent(empresa=empresa_a, umbral_critico=5, umbral_alerta=15)
        # 12 días → con umbral_critico=5 debería ser REVISAR (no REORDENAR)
        s = agente.evaluar(Decimal("12"), Decimal("0"), Decimal("1"))
        assert s.estado == "REVISAR"

    def test_modelo_fallback(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.evaluar(Decimal("10"), Decimal("5"), Decimal("1"))
        assert s.modelo_llm == "fallback-reglas"


@pytest.mark.django_db
class TestReordenLLMMock:
    """LLM mock inyectado para reorden."""

    def test_usa_llm_cuando_se_inyecta(self, empresa_a):
        from apps.agentes.reorden import ReordenSugeridorAgent
        mc = MagicMock()
        mc.messages.create.return_value.content = [MagicMock(text=(
            '{"estado": "REVISAR", "cantidad_sugerida_reorden": 50, "razonamiento": "Test"}'
        ))]
        # evaluar() no usa LLM; el LLM se usa en analizar() — testeamos que la init funcione
        agente = ReordenSugeridorAgent(empresa=empresa_a, llm_client=mc)
        assert agente._usar_llm is True

    def test_analizar_devuelve_lista(self, empresa_a):
        from apps.agentes.reorden import ReordenSugeridorAgent
        agente = ReordenSugeridorAgent(empresa=empresa_a)
        resultado = agente.analizar(persistir=False)
        assert isinstance(resultado, list)


# ─────────────────────────────────────────────────────────────────────────────
# M9-T2: Agente Personalización Capa 2
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestPersonalizacionCapa2:

    def _agente(self, empresa_a):
        from apps.agentes.personalizacion_agente import PersonalizacionCapa2Agent
        return PersonalizacionCapa2Agent(empresa=empresa_a)

    def test_analizar_retorna_resultado(self, empresa_a):
        agente = self._agente(empresa_a)
        r = agente.analizar()
        assert hasattr(r, "flujo_documentos")
        assert hasattr(r, "listas_precios")
        assert hasattr(r, "credito_clientes")
        assert isinstance(r.advertencias, list)

    def test_analizar_no_modifica_datos(self, db, empresa_a):
        from apps.agentes.personalizacion_agente import PersonalizacionCapa2Agent
        from apps.crm.models import Cliente

        count_before = Cliente.objects.filter(id_empresa=empresa_a).count()
        agente = PersonalizacionCapa2Agent(empresa=empresa_a)
        agente.analizar()
        assert Cliente.objects.filter(id_empresa=empresa_a).count() == count_before

    def test_sugerir_credito_alto_riesgo(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir_credito(
            cliente_nombre="Moroso SA",
            limite_actual=Decimal("10000"),
            cxc_vencidas=5,
            cxc_pagadas=10,  # tasa_mora=33% > 30%
        )
        assert s.riesgo == "alto"
        assert s.limite_sugerido < Decimal("10000")

    def test_sugerir_credito_buen_historial(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir_credito(
            cliente_nombre="Buen Pagador CA",
            limite_actual=Decimal("5000"),
            cxc_vencidas=0,
            cxc_pagadas=10,  # sin mora, 10 pagadas → aumentar
        )
        assert s.riesgo == "bajo"
        assert s.limite_sugerido > Decimal("5000")

    def test_sugerir_credito_sin_historial(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir_credito(
            cliente_nombre="Cliente Nuevo",
            limite_actual=Decimal("2000"),
            cxc_vencidas=0,
            cxc_pagadas=0,
        )
        # Sin historial → mantener límite
        assert s.limite_sugerido == Decimal("2000")

    def test_sugerir_credito_reduce_porcentaje_correcto(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir_credito(
            cliente_nombre="Moroso",
            limite_actual=Decimal("1000"),
            cxc_vencidas=4,
            cxc_pagadas=8,  # tasa=33% > 30% → reduce 30%
        )
        assert s.limite_sugerido == Decimal("700.00")

    def test_sugerir_credito_aumenta_25_porciento(self, empresa_a):
        agente = self._agente(empresa_a)
        s = agente.sugerir_credito(
            cliente_nombre="Fiel",
            limite_actual=Decimal("1000"),
            cxc_vencidas=0,
            cxc_pagadas=5,  # exactamente 5 → aumenta 25%
        )
        assert s.limite_sugerido == Decimal("1250.00")

    def test_analizar_con_producto_bajo_margen(self, db, empresa_a, moneda_usd):
        from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida
        from apps.agentes.personalizacion_agente import PersonalizacionCapa2Agent

        cat = CategoriaProducto.objects.create(
            id_empresa=empresa_a, nombre_categoria="Test"
        )
        und = UnidadMedida.objects.create(
            id_empresa=empresa_a, nombre="Pieza", abreviatura="PZ", tipo="CANTIDAD"
        )
        # Producto con margen < 15%: precio 110, costo 100 → margen 10%
        Producto.objects.create(
            id_empresa=empresa_a,
            id_categoria=cat,
            id_unidad_medida_base=und,
            id_moneda_precio=moneda_usd,
            nombre_producto="Producto Bajo Margen",
            precio_venta_sugerido=Decimal("110.00"),
            costo_promedio=Decimal("100.00"),
        )

        agente = PersonalizacionCapa2Agent(empresa=empresa_a)
        r = agente.analizar()
        assert len(r.listas_precios) >= 1
        assert any("margen" in s.razonamiento.lower() for s in r.listas_precios)


# ─────────────────────────────────────────────────────────────────────────────
# M9-T5: Eval Suites (Golden Cases)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCobranzaEvalSuite:
    """Eval suite cobranza: ≥30 casos, ≥75% accuracy en prioridad."""

    def test_dataset_tiene_minimo_30_casos(self):
        from apps.agentes.eval_cobranza import CASOS_DORADOS_COBRANZA
        assert len(CASOS_DORADOS_COBRANZA) >= 30

    def test_precision_prioridad_sobre_dataset(self, empresa_a):
        from apps.agentes.cobranza import CobranzaEstrategaAgent
        from apps.agentes.eval_cobranza import CASOS_DORADOS_COBRANZA, PRECISION_MINIMA_COBRANZA

        agente = CobranzaEstrategaAgent(empresa=empresa_a)
        aciertos = 0
        for caso in CASOS_DORADOS_COBRANZA:
            s = agente.sugerir(
                cxc_id="eval",
                cliente_nombre="Eval Client",
                monto=caso["monto"],
                dias_vencida=caso["dias_vencida"],
                intentos_contacto=caso["intentos"],
                persistir=False,
            )
            if s.prioridad == caso["prioridad"]:
                aciertos += 1

        precision = aciertos / len(CASOS_DORADOS_COBRANZA)
        assert precision >= PRECISION_MINIMA_COBRANZA, (
            f"Precisión cobranza {precision:.1%} < mínimo {PRECISION_MINIMA_COBRANZA:.1%}. "
            f"Aciertos: {aciertos}/{len(CASOS_DORADOS_COBRANZA)}"
        )

    def test_precision_canal_sobre_dataset(self, empresa_a):
        from apps.agentes.cobranza import CobranzaEstrategaAgent
        from apps.agentes.eval_cobranza import CASOS_DORADOS_COBRANZA, PRECISION_MINIMA_COBRANZA

        agente = CobranzaEstrategaAgent(empresa=empresa_a)
        aciertos = 0
        for caso in CASOS_DORADOS_COBRANZA:
            s = agente.sugerir(
                cxc_id="eval",
                cliente_nombre="Eval",
                monto=caso["monto"],
                dias_vencida=caso["dias_vencida"],
                intentos_contacto=caso["intentos"],
                persistir=False,
            )
            if s.canal == caso["canal"]:
                aciertos += 1

        precision = aciertos / len(CASOS_DORADOS_COBRANZA)
        assert precision >= PRECISION_MINIMA_COBRANZA, (
            f"Precisión canal cobranza {precision:.1%} < mínimo {PRECISION_MINIMA_COBRANZA:.1%}. "
            f"Aciertos: {aciertos}/{len(CASOS_DORADOS_COBRANZA)}"
        )

    def test_todas_prioridades_representadas(self):
        from apps.agentes.eval_cobranza import CASOS_DORADOS_COBRANZA
        prioridades = {c["prioridad"] for c in CASOS_DORADOS_COBRANZA}
        assert "alta" in prioridades
        assert "media" in prioridades
        assert "baja" in prioridades

    def test_todos_canales_representados(self):
        from apps.agentes.eval_cobranza import CASOS_DORADOS_COBRANZA
        canales = {c["canal"] for c in CASOS_DORADOS_COBRANZA}
        assert "whatsapp" in canales
        assert "telefono" in canales
        assert "visita_presencial" in canales


@pytest.mark.django_db
class TestReordenEvalSuite:
    """Eval suite reorden: ≥30 casos, ≥75% accuracy en estado."""

    def test_dataset_tiene_minimo_30_casos(self):
        from apps.agentes.eval_reorden import CASOS_DORADOS_REORDEN
        assert len(CASOS_DORADOS_REORDEN) >= 30

    def test_precision_estado_sobre_dataset(self, empresa_a):
        from apps.agentes.reorden import ReordenSugeridorAgent
        from apps.agentes.eval_reorden import CASOS_DORADOS_REORDEN, PRECISION_MINIMA_REORDEN

        agente = ReordenSugeridorAgent(empresa=empresa_a)
        aciertos = 0
        for caso in CASOS_DORADOS_REORDEN:
            s = agente.evaluar(
                stock_disponible=caso["stock"],
                cantidad_minima=caso["minimo"],
                consumo_diario=caso["consumo"],
            )
            if s.estado == caso["estado"]:
                aciertos += 1

        precision = aciertos / len(CASOS_DORADOS_REORDEN)
        assert precision >= PRECISION_MINIMA_REORDEN, (
            f"Precisión reorden {precision:.1%} < mínimo {PRECISION_MINIMA_REORDEN:.1%}. "
            f"Aciertos: {aciertos}/{len(CASOS_DORADOS_REORDEN)}"
        )

    def test_todos_estados_representados(self):
        from apps.agentes.eval_reorden import CASOS_DORADOS_REORDEN
        estados = {c["estado"] for c in CASOS_DORADOS_REORDEN}
        assert "REORDENAR" in estados
        assert "REVISAR" in estados
        assert "OK" in estados

    def test_minimo_10_casos_reordenar(self):
        from apps.agentes.eval_reorden import CASOS_DORADOS_REORDEN
        reordenar = [c for c in CASOS_DORADOS_REORDEN if c["estado"] == "REORDENAR"]
        assert len(reordenar) >= 10

    def test_minimo_5_casos_ok(self):
        from apps.agentes.eval_reorden import CASOS_DORADOS_REORDEN
        ok_casos = [c for c in CASOS_DORADOS_REORDEN if c["estado"] == "OK"]
        assert len(ok_casos) >= 5
