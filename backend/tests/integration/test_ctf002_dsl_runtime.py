"""
Tests de integración — CTF-002: DSL runtime completo (R-CODE-12).

Cubre:
  1. entidades — aplicar_config persiste definiciones; crear_instancia_entidad/listar_instancias_entidad
  2. estados   — aplicar_config persiste estados en DB; get_estados_personalizados/es_estado_valido
  3. reglas    — aplicar_config registra reglas; ejecutar_reglas() las evalúa (ya implementado)
  4. vistas    — aplicar_config persiste vistas en DB; get_columnas_vista/get_filtros_vista
  5. Verificar que aplicar_config NO emite advertencias para estas primitivas
  6. 2 configs distintas por primitiva

Requiere: pytest-django, modelo EntidadInstancia/EstadoPersonalizado/VistaPersonalizada migraciones listas.
"""

import pytest

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def empresa(db, empresa_a):
    return empresa_a


# ── Helpers ───────────────────────────────────────────────────────────────────


def _aplicar(config, empresa):
    from apps.personalizacion.dsl import aplicar_config
    return aplicar_config(config, empresa)


# ═══════════════════════════════════════════════════════════════════════════════
# PRIMITIVA: entidades
# ═══════════════════════════════════════════════════════════════════════════════


class TestDSLEntidades:
    """
    CTF-002 — Primitiva 'entidades':
    - aplicar_config almacena la definición y no emite advertencias
    - crear_instancia_entidad crea instancias EAV
    - listar_instancias_entidad devuelve las instancias de la empresa
    """

    CONFIG_EQUIPOS = {
        "entidades": [
            {
                "nombre": "Equipo",
                "campos": [
                    {"nombre": "nombre", "tipo": "text"},
                    {"nombre": "numero_serie", "tipo": "text"},
                    {"nombre": "costo", "tipo": "decimal"},
                ],
            }
        ]
    }

    CONFIG_PROYECTOS = {
        "entidades": [
            {
                "nombre": "Proyecto",
                "campos": [
                    {"nombre": "titulo", "tipo": "text"},
                    {"nombre": "presupuesto", "tipo": "decimal"},
                    {"nombre": "activo", "tipo": "boolean"},
                ],
            },
            {
                "nombre": "Tarea",
                "campos": [
                    {"nombre": "descripcion", "tipo": "text"},
                    {"nombre": "completada", "tipo": "boolean"},
                ],
            },
        ]
    }

    def test_aplicar_config_entidades_no_emite_advertencias(self, empresa):
        resultado = _aplicar(self.CONFIG_EQUIPOS, empresa)
        assert not any("advertencia" in a.lower() for a in resultado.get("advertencias", [])), (
            "aplicar_config no debe emitir advertencias para 'entidades'"
        )

    def test_aplicar_config_entidades_reporta_en_aplicadas(self, empresa):
        resultado = _aplicar(self.CONFIG_EQUIPOS, empresa)
        assert any("entidad" in a.lower() for a in resultado["aplicadas"]), (
            "aplicar_config debe reportar entidades en 'aplicadas'"
        )

    def test_crear_instancia_entidad_config1(self, empresa):
        """Config 1: entidad Equipo — crear y listar instancias."""
        from apps.personalizacion.dsl import crear_instancia_entidad, listar_instancias_entidad

        _aplicar(self.CONFIG_EQUIPOS, empresa)

        inst = crear_instancia_entidad(
            empresa, "Equipo", {"nombre": "Laptop Pro", "numero_serie": "SN-001", "costo": 1500.00}
        )
        assert inst.nombre_entidad == "Equipo"
        assert inst.datos["nombre"] == "Laptop Pro"
        assert inst.datos["numero_serie"] == "SN-001"

        lista = listar_instancias_entidad(empresa, "Equipo")
        assert lista.filter(id_instancia=inst.id_instancia).exists()

    def test_crear_instancia_entidad_config2(self, empresa):
        """Config 2: entidades Proyecto y Tarea — crear instancias de ambas."""
        from apps.personalizacion.dsl import crear_instancia_entidad, listar_instancias_entidad

        _aplicar(self.CONFIG_PROYECTOS, empresa)

        proyecto = crear_instancia_entidad(empresa, "Proyecto", {"titulo": "Sistema ERP", "presupuesto": 50000, "activo": True})
        tarea = crear_instancia_entidad(empresa, "Tarea", {"descripcion": "Fase de análisis", "completada": False})

        assert listar_instancias_entidad(empresa, "Proyecto").count() == 1
        assert listar_instancias_entidad(empresa, "Tarea").count() == 1
        assert proyecto.datos["titulo"] == "Sistema ERP"
        assert not tarea.datos["completada"]

    def test_instancias_aisladas_por_empresa(self, empresa, empresa_b):
        """Las instancias de empresa A no son visibles para empresa B."""
        from apps.personalizacion.dsl import crear_instancia_entidad, listar_instancias_entidad

        _aplicar(self.CONFIG_EQUIPOS, empresa)
        crear_instancia_entidad(empresa, "Equipo", {"nombre": "Equipo A"})

        lista_b = listar_instancias_entidad(empresa_b, "Equipo")
        assert lista_b.count() == 0, "empresa_b no debe ver instancias de empresa_a"


# ═══════════════════════════════════════════════════════════════════════════════
# PRIMITIVA: estados
# ═══════════════════════════════════════════════════════════════════════════════


class TestDSLEstados:
    """
    CTF-002 — Primitiva 'estados':
    - aplicar_config persiste EstadoPersonalizado en DB
    - get_estados_personalizados devuelve los estados de la empresa
    - es_estado_valido combina base + personalizado
    """

    CONFIG_ESTADOS_PEDIDO = {
        "estados": [
            {"modelo": "Pedido", "nombre": "EN_REVISION", "etiqueta": "En Revisión"},
            {"modelo": "Pedido", "nombre": "RETENIDO", "etiqueta": "Retenido por Compliance"},
        ]
    }

    CONFIG_ESTADOS_GASTO = {
        "estados": [
            {"modelo": "Gasto", "nombre": "PENDIENTE_DIRECTOR", "etiqueta": "Pendiente Aprobación Director"},
        ]
    }

    def test_aplicar_config_estados_no_emite_advertencias(self, empresa):
        resultado = _aplicar(self.CONFIG_ESTADOS_PEDIDO, empresa)
        assert not any("advertencia" in a.lower() for a in resultado.get("advertencias", [])), (
            "aplicar_config no debe emitir advertencias para 'estados'"
        )

    def test_aplicar_config_estados_config1_persiste_en_db(self, empresa):
        """Config 1: estados de Pedido — persisten en EstadoPersonalizado."""
        from apps.personalizacion.dsl import get_estados_personalizados

        _aplicar(self.CONFIG_ESTADOS_PEDIDO, empresa)

        estados = get_estados_personalizados(empresa, "Pedido")
        nombres = {e["nombre"] for e in estados}
        assert "EN_REVISION" in nombres
        assert "RETENIDO" in nombres
        assert len(estados) == 2

    def test_aplicar_config_estados_config2_persiste_en_db(self, empresa):
        """Config 2: estado de Gasto — persiste en DB."""
        from apps.personalizacion.dsl import get_estados_personalizados

        _aplicar(self.CONFIG_ESTADOS_GASTO, empresa)

        estados = get_estados_personalizados(empresa, "Gasto")
        nombres = {e["nombre"] for e in estados}
        assert "PENDIENTE_DIRECTOR" in nombres

    def test_es_estado_valido_con_estado_personalizado(self, empresa):
        """es_estado_valido retorna True para estado personalizado registrado."""
        from apps.personalizacion.dsl import es_estado_valido

        _aplicar(self.CONFIG_ESTADOS_PEDIDO, empresa)

        # Estados base del modelo Pedido
        estados_base = ["PENDIENTE", "APROBADO", "ENTREGADO"]

        assert es_estado_valido(empresa, "Pedido", "PENDIENTE", estados_base)  # base
        assert es_estado_valido(empresa, "Pedido", "EN_REVISION", estados_base)  # personalizado
        assert es_estado_valido(empresa, "Pedido", "RETENIDO", estados_base)  # personalizado
        assert not es_estado_valido(empresa, "Pedido", "ESTADO_INEXISTENTE", estados_base)

    def test_estados_aislados_por_empresa(self, empresa, empresa_b):
        """Los estados de empresa A no aparecen en empresa B."""
        from apps.personalizacion.dsl import get_estados_personalizados

        _aplicar(self.CONFIG_ESTADOS_PEDIDO, empresa)

        estados_b = get_estados_personalizados(empresa_b, "Pedido")
        assert len(estados_b) == 0, "empresa_b no debe ver estados de empresa_a"


# ═══════════════════════════════════════════════════════════════════════════════
# PRIMITIVA: reglas
# ═══════════════════════════════════════════════════════════════════════════════


class TestDSLReglas:
    """
    CTF-002 — Primitiva 'reglas':
    - aplicar_config registra reglas sin advertencias
    - ejecutar_reglas() evalúa las reglas contra instancias de modelo
    """

    CONFIG_REGLAS_PEDIDO = {
        "reglas": [
            {
                "entidad": "Pedido",
                "campo": "cantidad",
                "operador": "mayor_que",
                "valor": 0,
                "mensaje_error": "La cantidad del pedido debe ser mayor que cero",
            },
        ]
    }

    CONFIG_REGLAS_MULTIPLE = {
        "reglas": [
            {
                "entidad": "Pedido",
                "campo": "estado",
                "operador": "distinto_de",
                "valor": "CANCELADO",
                "mensaje_error": "No se puede procesar un pedido cancelado",
            },
            {
                "entidad": "Cliente",
                "campo": "rif",
                "operador": "distinto_de",
                "valor": None,
                "mensaje_error": "El RIF del cliente es obligatorio",
            },
        ]
    }

    def test_aplicar_config_reglas_no_emite_advertencias(self, empresa):
        resultado = _aplicar(self.CONFIG_REGLAS_PEDIDO, empresa)
        assert not any("advertencia" in a.lower() for a in resultado.get("advertencias", [])), (
            "aplicar_config no debe emitir advertencias para 'reglas'"
        )

    def test_ejecutar_reglas_config1_pasa(self, empresa):
        """Config 1: regla cantidad>0 — instancia válida no retorna errores."""
        from apps.personalizacion.dsl import ejecutar_reglas

        _aplicar(self.CONFIG_REGLAS_PEDIDO, empresa)

        class PedidoMock:
            cantidad = 5

        errores = ejecutar_reglas("Pedido", PedidoMock(), empresa)
        assert errores == [], f"Se esperaban 0 errores, se obtuvieron: {errores}"

    def test_ejecutar_reglas_config1_falla(self, empresa):
        """Config 1: regla cantidad>0 — instancia con cantidad=0 retorna error."""
        from apps.personalizacion.dsl import ejecutar_reglas

        _aplicar(self.CONFIG_REGLAS_PEDIDO, empresa)

        class PedidoMock:
            cantidad = 0

        errores = ejecutar_reglas("Pedido", PedidoMock(), empresa)
        assert len(errores) == 1
        assert "mayor que cero" in errores[0]

    def test_ejecutar_reglas_config2_multiple_entidades(self, empresa):
        """Config 2: reglas para Pedido y Cliente — se evalúan independientemente."""
        from apps.personalizacion.dsl import ejecutar_reglas

        _aplicar(self.CONFIG_REGLAS_MULTIPLE, empresa)

        class PedidoCancelado:
            estado = "CANCELADO"

        class PedidoActivo:
            estado = "ACTIVO"

        errores_cancelado = ejecutar_reglas("Pedido", PedidoCancelado(), empresa)
        assert len(errores_cancelado) == 1
        assert "cancelado" in errores_cancelado[0].lower()

        errores_activo = ejecutar_reglas("Pedido", PedidoActivo(), empresa)
        assert errores_activo == []

    def test_aplicar_config_reglas_config2_reporta_en_aplicadas(self, empresa):
        resultado = _aplicar(self.CONFIG_REGLAS_MULTIPLE, empresa)
        assert any("reglas" in a.lower() for a in resultado["aplicadas"])


# ═══════════════════════════════════════════════════════════════════════════════
# PRIMITIVA: vistas
# ═══════════════════════════════════════════════════════════════════════════════


class TestDSLVistas:
    """
    CTF-002 — Primitiva 'vistas':
    - aplicar_config persiste VistaPersonalizada en DB
    - get_columnas_vista / get_filtros_vista retornan la configuración
    """

    CONFIG_VISTA_CLIENTES = {
        "vistas": [
            {
                "entidad": "Cliente",
                "columnas": ["razon_social", "rif", "tipo_cliente", "limite_credito"],
                "filtros": {"tipo_cliente": "CREDITO"},
            }
        ]
    }

    CONFIG_VISTA_PEDIDOS = {
        "vistas": [
            {
                "entidad": "Pedido",
                "columnas": ["numero_pedido", "fecha_pedido", "estado", "total"],
            },
            {
                "entidad": "Producto",
                "columnas": ["nombre_producto", "sku", "precio_venta_sugerido"],
                "filtros": {"activo": True},
            },
        ]
    }

    def test_aplicar_config_vistas_no_emite_advertencias(self, empresa):
        resultado = _aplicar(self.CONFIG_VISTA_CLIENTES, empresa)
        assert not any("advertencia" in a.lower() for a in resultado.get("advertencias", [])), (
            "aplicar_config no debe emitir advertencias para 'vistas'"
        )

    def test_aplicar_config_vistas_config1_persiste_columnas(self, empresa):
        """Config 1: vista de clientes — columnas y filtros persisten en DB."""
        from apps.personalizacion.dsl import get_columnas_vista, get_filtros_vista

        _aplicar(self.CONFIG_VISTA_CLIENTES, empresa)

        columnas = get_columnas_vista(empresa, "Cliente")
        assert "razon_social" in columnas
        assert "rif" in columnas
        assert "limite_credito" in columnas
        assert len(columnas) == 4

        filtros = get_filtros_vista(empresa, "Cliente")
        assert filtros.get("tipo_cliente") == "CREDITO"

    def test_aplicar_config_vistas_config2_multiple_vistas(self, empresa):
        """Config 2: vistas de Pedido y Producto — ambas persisten en DB."""
        from apps.personalizacion.dsl import get_columnas_vista, get_filtros_vista

        _aplicar(self.CONFIG_VISTA_PEDIDOS, empresa)

        col_pedido = get_columnas_vista(empresa, "Pedido")
        assert "numero_pedido" in col_pedido
        assert "estado" in col_pedido

        col_producto = get_columnas_vista(empresa, "Producto")
        assert "nombre_producto" in col_producto

        filtros_producto = get_filtros_vista(empresa, "Producto")
        assert filtros_producto.get("activo") is True

    def test_get_columnas_vista_retorna_lista_vacia_sin_config(self, empresa):
        """Sin configuración previa, get_columnas_vista retorna []."""
        from apps.personalizacion.dsl import get_columnas_vista

        columnas = get_columnas_vista(empresa, "EntidadSinVista")
        assert columnas == []

    def test_vistas_aisladas_por_empresa(self, empresa, empresa_b):
        """Las vistas de empresa A no son visibles para empresa B."""
        from apps.personalizacion.dsl import get_columnas_vista

        _aplicar(self.CONFIG_VISTA_CLIENTES, empresa)

        columnas_b = get_columnas_vista(empresa_b, "Cliente")
        assert columnas_b == [], "empresa_b no debe ver vistas de empresa_a"

    def test_aplicar_config_vistas_idempotente(self, empresa):
        """Aplicar el mismo config dos veces actualiza en lugar de duplicar."""
        from apps.personalizacion.models import VistaPersonalizada
        from apps.personalizacion.dsl import get_columnas_vista

        _aplicar(self.CONFIG_VISTA_CLIENTES, empresa)
        _aplicar(self.CONFIG_VISTA_CLIENTES, empresa)

        # Solo debe haber UNA vista para Cliente en esta empresa
        count = VistaPersonalizada.objects.filter(id_empresa=empresa, entidad="Cliente").count()
        assert count == 1, f"Se esperaba 1 VistaPersonalizada, se encontraron {count}"

        columnas = get_columnas_vista(empresa, "Cliente")
        assert len(columnas) == 4
