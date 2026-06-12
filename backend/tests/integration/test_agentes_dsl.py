"""
Tests: WS-4 (Agente clasificador de gastos) y WS-5 (DSL Personalización).
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.integration


# ── WS-4: Agente Clasificador de Gastos ──────────────────────────────────────

@pytest.mark.django_db
class TestClasificadorGastosFallback:
    """Modo fallback (sin LLM): determinista, 100% testeable sin API key."""

    def test_clasifica_alimentacion(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        agente = ClasificadorGastos(empresa=empresa_a)
        r = agente.clasificar("Almuerzo de trabajo con cliente", persistir=False)
        assert r.categoria == "alimentacion"
        assert 0.0 < r.confianza <= 1.0
        assert r.modelo_llm == "fallback-keywords"

    def test_clasifica_transporte(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        agente = ClasificadorGastos(empresa=empresa_a)
        r = agente.clasificar("Taxi al aeropuerto", persistir=False)
        assert r.categoria == "transporte"

    def test_clasifica_tecnologia(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        agente = ClasificadorGastos(empresa=empresa_a)
        r = agente.clasificar("Suscripción mensual Slack", persistir=False)
        assert r.categoria == "tecnologia_software"

    def test_clasifica_sin_match_devuelve_otros(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        agente = ClasificadorGastos(empresa=empresa_a)
        r = agente.clasificar("xyzxyz concepto desconocido abc", persistir=False)
        assert r.categoria == "otros"
        assert r.confianza < 0.5

    def test_confianza_en_rango_valido(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        agente = ClasificadorGastos(empresa=empresa_a)
        for desc in ["hotel", "gasolina", "impuesto", "papel"]:
            r = agente.clasificar(desc, persistir=False)
            assert 0.0 <= r.confianza <= 1.0, f"confianza fuera de rango: {r.confianza}"

    def test_retorna_alternativas(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        agente = ClasificadorGastos(empresa=empresa_a)
        r = agente.clasificar("Almuerzo con cliente en restaurante", persistir=False)
        assert isinstance(r.alternativas, list)

    def test_latencia_registrada(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        agente = ClasificadorGastos(empresa=empresa_a)
        r = agente.clasificar("Hotel para viaje", persistir=False)
        assert r.latencia_ms >= 0


@pytest.mark.django_db
class TestClasificadorGastosLLMMock:
    """Modo LLM: inyectar cliente mock para testear integración sin API key real."""

    def _make_mock_client(self, categoria="alimentacion", confianza=0.92):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=(
            f'{{"categoria": "{categoria}", "confianza": {confianza}, '
            f'"razonamiento": "Test reason", "alternativas": []}}'
        ))]
        mock_client.messages.create.return_value = mock_response
        return mock_client

    def test_usa_llm_cuando_se_inyecta_cliente(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        mock_client = self._make_mock_client("alimentacion", 0.95)
        agente = ClasificadorGastos(empresa=empresa_a, llm_client=mock_client)
        r = agente.clasificar("Almuerzo con equipo", persistir=False)
        assert r.categoria == "alimentacion"
        assert r.confianza == 0.95
        assert mock_client.messages.create.called

    def test_llm_usa_modelo_haiku(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        mock_client = self._make_mock_client()
        agente = ClasificadorGastos(empresa=empresa_a, llm_client=mock_client)
        agente.clasificar("Cena", persistir=False)
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "claude-haiku" in call_kwargs["model"]

    def test_llm_fallback_en_error_json(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        mock_client = MagicMock()
        mock_client.messages.create.return_value.content = [MagicMock(text="NO ES JSON")]
        agente = ClasificadorGastos(empresa=empresa_a, llm_client=mock_client)
        r = agente.clasificar("Almuerzo", persistir=False)
        # debe caer a fallback sin levantar excepción
        assert isinstance(r.categoria, str)
        assert "fallback-error" in r.modelo_llm

    def test_llm_fallback_en_excepcion_red(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = ConnectionError("timeout")
        agente = ClasificadorGastos(empresa=empresa_a, llm_client=mock_client)
        r = agente.clasificar("Hotel", persistir=False)
        assert isinstance(r.categoria, str)


@pytest.mark.django_db
class TestClasificadorGastosPersistencia:
    """Modo shadow: la predicción se persiste en BD sin modificar Gasto."""

    def test_persistir_crea_prediccion(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        from apps.agentes.models import PrediccionAgente

        count_antes = PrediccionAgente.objects.count()
        agente = ClasificadorGastos(empresa=empresa_a)
        agente.clasificar("Taxi al aeropuerto", monto=Decimal("22.00"), persistir=True)
        assert PrediccionAgente.objects.count() == count_antes + 1

    def test_prediccion_tiene_empresa_correcta(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        from apps.agentes.models import PrediccionAgente

        agente = ClasificadorGastos(empresa=empresa_a)
        agente.clasificar("Almuerzo", persistir=True)
        pred = PrediccionAgente.objects.filter(id_empresa=empresa_a).last()
        assert pred is not None
        assert pred.id_empresa_id == empresa_a.pk

    def test_prediccion_shadow_no_modifica_gastos(self, empresa_a):
        """Verificar que clasificar no crea ni modifica registros Gasto."""
        from apps.agentes.clasificador import ClasificadorGastos
        from apps.gastos.models import Gasto

        count_gastos_antes = Gasto.objects.filter(id_empresa=empresa_a).count()
        agente = ClasificadorGastos(empresa=empresa_a)
        agente.clasificar("Hotel viaje negocios", monto=Decimal("150.00"), persistir=True)
        assert Gasto.objects.filter(id_empresa=empresa_a).count() == count_gastos_antes

    def test_estado_inicial_pendiente(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        from apps.agentes.models import PrediccionAgente

        agente = ClasificadorGastos(empresa=empresa_a)
        agente.clasificar("Café reunión", persistir=True)
        pred = PrediccionAgente.objects.filter(id_empresa=empresa_a).last()
        assert pred.resultado_humano == "pendiente"


@pytest.mark.django_db
class TestClasificadorGastosEvalSuite:
    """
    Runner del eval suite: verifica que el agente supera PRECISION_MINIMA
    en los 50 casos dorados usando el modo fallback determinista.
    """

    def test_precision_sobre_dataset_completo(self, empresa_a):
        from apps.agentes.clasificador import ClasificadorGastos
        from apps.agentes.eval_dataset import CASOS_DORADOS, PRECISION_MINIMA

        agente = ClasificadorGastos(empresa=empresa_a)
        aciertos = 0
        for caso in CASOS_DORADOS:
            r = agente.clasificar(caso["descripcion"], monto=caso["monto"], persistir=False)
            if r.categoria == caso["categoria"]:
                aciertos += 1

        precision = aciertos / len(CASOS_DORADOS)
        assert precision >= PRECISION_MINIMA, (
            f"Precisión {precision:.1%} por debajo del mínimo {PRECISION_MINIMA:.1%}. "
            f"Aciertos: {aciertos}/{len(CASOS_DORADOS)}"
        )

    def test_dataset_tiene_50_casos(self):
        from apps.agentes.eval_dataset import CASOS_DORADOS
        assert len(CASOS_DORADOS) == 50

    def test_todas_las_categorias_tienen_casos(self):
        from apps.agentes.eval_dataset import CASOS_DORADOS, CATEGORIAS_CANONICAS
        categorias_en_dataset = {c["categoria"] for c in CASOS_DORADOS}
        # al menos 10 de las 14 categorías deben estar representadas
        assert len(categorias_en_dataset) >= 10


# ── WS-5: DSL de Personalización ─────────────────────────────────────────────

class TestDSLValidacion:
    """Tests del validador de configs DSL — sin DB, puramente unitarios."""

    def test_config_vacio_es_invalido(self):
        from apps.personalizacion.dsl import validar_config
        errores = validar_config({})
        assert any("vacío" in e for e in errores)

    def test_clave_desconocida_es_error(self):
        from apps.personalizacion.dsl import validar_config
        errores = validar_config({"clave_invalida": []})
        assert any("no reconocidas" in e for e in errores)

    def test_campo_renombrar_valido(self):
        from apps.personalizacion.dsl import validar_config
        config = {"campos": [{"entidad": "Cliente", "campo": "razon_social", "accion": "renombrar", "nuevo_nombre": "Nombre Comercial"}]}
        assert validar_config(config) == []

    def test_campo_renombrar_sin_nuevo_nombre_falla(self):
        from apps.personalizacion.dsl import validar_config
        config = {"campos": [{"entidad": "Cliente", "campo": "rif", "accion": "renombrar"}]}
        errores = validar_config(config)
        assert any("nuevo_nombre" in e for e in errores)

    def test_campo_agregar_valido(self):
        from apps.personalizacion.dsl import validar_config
        config = {"campos": [{"entidad": "Cliente", "campo": "segmento", "accion": "agregar", "tipo": "select", "opciones": ["A", "B", "C"]}]}
        assert validar_config(config) == []

    def test_campo_agregar_tipo_invalido(self):
        from apps.personalizacion.dsl import validar_config
        config = {"campos": [{"entidad": "Cliente", "campo": "x", "accion": "agregar", "tipo": "blob"}]}
        errores = validar_config(config)
        assert any("tipo" in e for e in errores)

    def test_campo_select_sin_opciones_falla(self):
        from apps.personalizacion.dsl import validar_config
        config = {"campos": [{"entidad": "Cliente", "campo": "x", "accion": "agregar", "tipo": "select"}]}
        errores = validar_config(config)
        assert any("opciones" in e for e in errores)

    def test_entidad_desconocida_falla(self):
        from apps.personalizacion.dsl import validar_config
        config = {"campos": [{"entidad": "Ovni", "campo": "nombre", "accion": "ocultar"}]}
        errores = validar_config(config)
        assert any("Ovni" in e for e in errores)

    def test_estado_personalizado_valido(self):
        from apps.personalizacion.dsl import validar_config
        config = {"estados": [{"modelo": "Gasto", "nombre": "EN_REVISION", "etiqueta": "En Revisión Contable"}]}
        assert validar_config(config) == []

    def test_estado_modelo_sin_soporte_falla(self):
        from apps.personalizacion.dsl import validar_config
        config = {"estados": [{"modelo": "Producto", "nombre": "X", "etiqueta": "X"}]}
        errores = validar_config(config)
        assert errores

    def test_regla_valida(self):
        from apps.personalizacion.dsl import validar_config
        config = {"reglas": [{"entidad": "Gasto", "campo": "monto", "operador": "mayor_que", "valor": 0, "mensaje_error": "El monto debe ser positivo"}]}
        assert validar_config(config) == []

    def test_regla_operador_invalido(self):
        from apps.personalizacion.dsl import validar_config
        config = {"reglas": [{"entidad": "Gasto", "campo": "monto", "operador": "contiene", "mensaje_error": "x"}]}
        errores = validar_config(config)
        assert any("operador" in e for e in errores)

    def test_vista_valida(self):
        from apps.personalizacion.dsl import validar_config
        config = {"vistas": [{"entidad": "Cliente", "columnas": ["razon_social", "rif", "limite_credito"]}]}
        assert validar_config(config) == []

    def test_conector_valido(self):
        from apps.personalizacion.dsl import validar_config
        config = {"conectores": [{"nombre": "ERP Legacy", "url": "https://legacy.internal/api/sync", "metodo": "POST", "evento_origen": "ventas.pedido.confirmado"}]}
        assert validar_config(config) == []

    def test_conector_metodo_invalido(self):
        from apps.personalizacion.dsl import validar_config
        config = {"conectores": [{"nombre": "x", "url": "http://x.com", "metodo": "ENVIAR", "evento_origen": "x.y.z"}]}
        errores = validar_config(config)
        assert any("metodo" in e for e in errores)

    def test_config_completo_multi_primitiva(self):
        from apps.personalizacion.dsl import validar_config
        config = {
            "campos": [{"entidad": "Cliente", "campo": "rif", "accion": "renombrar", "nuevo_nombre": "NIT"}],
            "estados": [{"modelo": "Gasto", "nombre": "AUDITADO", "etiqueta": "Auditado"}],
            "vistas": [{"entidad": "Proveedor", "columnas": ["razon_social", "rif"]}],
        }
        assert validar_config(config) == []


@pytest.mark.django_db
class TestDSLAplicador:
    """Tests del aplicador de config (PoC — primitiva campos)."""

    def test_aplicar_renombrar_retorna_aplicadas(self, empresa_a):
        from apps.personalizacion.dsl import aplicar_config
        config = {"campos": [{"entidad": "Cliente", "campo": "rif", "accion": "renombrar", "nuevo_nombre": "NIT"}]}
        resultado = aplicar_config(config, empresa_a)
        assert any("renombrar" in a for a in resultado["aplicadas"])

    def test_aplicar_primitivas_estados_procesa_sin_advertencia(self, empresa_a):
        """CTF-002: estados se procesa en DB — ya no genera advertencia, aparece en 'aplicadas'."""
        from apps.personalizacion.dsl import aplicar_config
        config = {
            "estados": [{"modelo": "Gasto", "nombre": "X", "etiqueta": "X"}],
        }
        resultado = aplicar_config(config, empresa_a)
        # La primitiva debe aparecer en aplicadas (procesada), no en advertencias
        assert any("estados" in a for a in resultado["aplicadas"]), (
            f"Se esperaba 'estados' en aplicadas; aplicadas={resultado['aplicadas']}"
        )
        assert not any("estados" in w for w in resultado["advertencias"]), (
            "La primitiva 'estados' no debe generar advertencia tras CTF-002"
        )

    def test_aplicar_config_invalido_lanza_error(self, empresa_a):
        from apps.personalizacion.dsl import aplicar_config
        with pytest.raises(ValueError, match="Config inválido"):
            aplicar_config({}, empresa_a)

    def test_aplicar_config_completo(self, empresa_a):
        from apps.personalizacion.dsl import aplicar_config
        config = {
            "campos": [
                {"entidad": "Cliente", "campo": "razon_social", "accion": "renombrar", "nuevo_nombre": "Nombre"},
                {"entidad": "Producto", "campo": "codigo", "accion": "ocultar"},
                {"entidad": "Cliente", "campo": "segmento", "accion": "agregar", "tipo": "select", "opciones": ["A", "B"]},
            ],
            "vistas": [{"entidad": "Cliente", "columnas": ["razon_social", "rif"]}],
        }
        resultado = aplicar_config(config, empresa_a)
        assert len(resultado["aplicadas"]) >= 4


@pytest.mark.django_db
class TestPersonalizacionModel:
    """Tests del modelo de persistencia de configs."""

    def test_crear_config(self, empresa_a):
        from apps.personalizacion.models import PersonalizacionConfig
        config = PersonalizacionConfig.objects.create(
            id_empresa=empresa_a,
            version=1,
            descripcion="Config inicial",
            config_yaml="campos:\n  - entidad: Cliente",
            config_dict={"campos": [{"entidad": "Cliente", "campo": "rif", "accion": "ocultar"}]},
        )
        assert config.activo is True
        assert config.version == 1

    def test_unicidad_empresa_version(self, empresa_a):
        from django.db import IntegrityError
        from apps.personalizacion.models import PersonalizacionConfig
        PersonalizacionConfig.objects.create(
            id_empresa=empresa_a, version=1,
            config_yaml="x", config_dict={},
        )
        with pytest.raises(IntegrityError):
            PersonalizacionConfig.objects.create(
                id_empresa=empresa_a, version=1,
                config_yaml="y", config_dict={},
            )
