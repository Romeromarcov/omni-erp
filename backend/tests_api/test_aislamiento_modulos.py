"""
Tests de aislamiento multi-tenant — módulos adicionales.

Verifica que cada módulo filtre correctamente por empresa:
un usuario de Empresa A NUNCA puede ver ni modificar datos de Empresa B.

Si alguno de estos tests falla, hay un leak de datos entre tenants.

Módulos cubiertos:
  contabilidad, auditoria, control_asistencia, servicio_cliente,
  almacenes, manufactura, gestion_aprobaciones, integracion_b2b,
  banca_electronica, personalizacion, tesoreria

Módulos omitidos (requieren demasiados FK obligatorios para construir fixtures simples):
  costos        — CostoProduccion requiere manufactura.OrdenProduccion + inventario.Producto
  despacho      — Despacho requiere ventas.Pedido / compras.OrdenCompra + almacenes.Almacen
  migracion_datos — ProcesoMigracion requiere PlantillaMigracion + Usuarios; PlantillaMigracion
                    no tiene FK de empresa, por lo que no aplica el patrón de aislamiento.
"""

import pytest

from rest_framework.test import APIClient

from apps.contabilidad.models import PlanCuentas
from apps.auditoria.models import LogAuditoria
from apps.control_asistencia.models import HorarioTrabajo
from apps.servicio_cliente.models import CategoriaTicket
from apps.almacenes.models import Almacen
from apps.manufactura.models import CentroTrabajo
from apps.gestion_aprobaciones.models import TipoAprobacion
from apps.integracion_b2b.models import ConfiguracionIntegracion
from apps.banca_electronica.models import CuentaBancariaEmpresa
from apps.personalizacion.models import PersonalizacionConfig
from apps.finanzas.models import Caja


# ---------------------------------------------------------------------------
# 1. Contabilidad — PlanCuentas
# ---------------------------------------------------------------------------

URL_PLAN_CUENTAS = "/api/contabilidad/plan-cuentas/"


@pytest.fixture
def plan_cuentas_a(db, empresa_a):
    return PlanCuentas.objects.create(
        id_empresa=empresa_a,
        codigo_cuenta="1.0.0",
        nombre_cuenta="Activos",
        tipo_cuenta="ACTIVO",
        naturaleza="DEUDORA",
        nivel=1,
    )


@pytest.fixture
def plan_cuentas_b(db, empresa_b):
    return PlanCuentas.objects.create(
        id_empresa=empresa_b,
        codigo_cuenta="1.0.0",
        nombre_cuenta="Activos Beta",
        tipo_cuenta="ACTIVO",
        naturaleza="DEUDORA",
        nivel=1,
    )


@pytest.mark.django_db
class TestAislamientoContabilidad:
    def test_listado_solo_devuelve_datos_de_empresa_propia(self, user_a, user_b, plan_cuentas_a, plan_cuentas_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(URL_PLAN_CUENTAS)
        assert response.status_code == 200
        data = response.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_cuenta_contable"]) for r in resultados}
        assert str(plan_cuentas_a.id_cuenta_contable) in ids
        assert str(plan_cuentas_b.id_cuenta_contable) not in ids, (
            "LEAK: datos de Empresa B visibles para Empresa A"
        )

    def test_get_objeto_de_otra_empresa_devuelve_404(self, user_a, plan_cuentas_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(f"{URL_PLAN_CUENTAS}{plan_cuentas_b.id_cuenta_contable}/")
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )

    def test_patch_objeto_de_otra_empresa_devuelve_404(self, user_a, plan_cuentas_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.patch(
            f"{URL_PLAN_CUENTAS}{plan_cuentas_b.id_cuenta_contable}/",
            {"nombre_cuenta": "Hackeado"},
            format="json",
        )
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )
        plan_cuentas_b.refresh_from_db()
        assert plan_cuentas_b.nombre_cuenta == "Activos Beta", (
            "CRÍTICO: nombre de cuenta de Empresa B fue modificado desde Empresa A."
        )


# ---------------------------------------------------------------------------
# 2. Auditoría — LogAuditoria (solo lectura)
# ---------------------------------------------------------------------------

URL_LOGS_AUDITORIA = "/api/auditoria/logs-auditoria/"


@pytest.fixture
def log_auditoria_a(db, empresa_a):
    return LogAuditoria.objects.create(
        id_empresa=empresa_a,
        modulo="Test",
        tipo_accion="CREATE",
        descripcion_accion="test log empresa A",
    )


@pytest.fixture
def log_auditoria_b(db, empresa_b):
    return LogAuditoria.objects.create(
        id_empresa=empresa_b,
        modulo="Test",
        tipo_accion="CREATE",
        descripcion_accion="test log empresa B",
    )


@pytest.mark.django_db
class TestAislamientoAuditoria:
    """Auditoria es de solo lectura; se verifica únicamente el listado."""

    def test_listado_solo_devuelve_datos_de_empresa_propia(self, user_a, user_b, log_auditoria_a, log_auditoria_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(URL_LOGS_AUDITORIA)
        assert response.status_code == 200
        data = response.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_log_auditoria"]) for r in resultados}
        assert str(log_auditoria_a.id_log_auditoria) in ids
        assert str(log_auditoria_b.id_log_auditoria) not in ids, (
            "LEAK: logs de Empresa B visibles para Empresa A"
        )

    def test_get_log_de_otra_empresa_devuelve_404(self, user_a, log_auditoria_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(f"{URL_LOGS_AUDITORIA}{log_auditoria_b.id_log_auditoria}/")
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )


# ---------------------------------------------------------------------------
# 3. Control de Asistencia — HorarioTrabajo
# ---------------------------------------------------------------------------

URL_HORARIOS_TRABAJO = "/api/control-asistencia/horarios-trabajo/"


@pytest.fixture
def horario_a(db, empresa_a):
    return HorarioTrabajo.objects.create(
        id_empresa=empresa_a,
        nombre_horario="Horario A",
        total_horas_semanales=40,
    )


@pytest.fixture
def horario_b(db, empresa_b):
    return HorarioTrabajo.objects.create(
        id_empresa=empresa_b,
        nombre_horario="Horario B",
        total_horas_semanales=40,
    )


@pytest.mark.django_db
class TestAislamientoControlAsistencia:
    def test_listado_solo_devuelve_datos_de_empresa_propia(self, user_a, user_b, horario_a, horario_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(URL_HORARIOS_TRABAJO)
        assert response.status_code == 200
        data = response.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_horario"]) for r in resultados}
        assert str(horario_a.id_horario) in ids
        assert str(horario_b.id_horario) not in ids, (
            "LEAK: datos de Empresa B visibles para Empresa A"
        )

    def test_get_objeto_de_otra_empresa_devuelve_404(self, user_a, horario_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(f"{URL_HORARIOS_TRABAJO}{horario_b.id_horario}/")
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )

    def test_patch_objeto_de_otra_empresa_devuelve_404(self, user_a, horario_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.patch(
            f"{URL_HORARIOS_TRABAJO}{horario_b.id_horario}/",
            {"nombre_horario": "Hackeado"},
            format="json",
        )
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )
        horario_b.refresh_from_db()
        assert horario_b.nombre_horario == "Horario B", (
            "CRÍTICO: nombre de horario de Empresa B fue modificado desde Empresa A."
        )


# ---------------------------------------------------------------------------
# 4. Servicio al Cliente — CategoriaTicket
# ---------------------------------------------------------------------------

URL_CATEGORIAS_TICKET = "/api/servicio-cliente/categorias-ticket/"


@pytest.fixture
def categoria_ticket_a(db, empresa_a):
    return CategoriaTicket.objects.create(
        id_empresa=empresa_a,
        nombre_categoria="Soporte Alpha",
    )


@pytest.fixture
def categoria_ticket_b(db, empresa_b):
    return CategoriaTicket.objects.create(
        id_empresa=empresa_b,
        nombre_categoria="Soporte Beta",
    )


@pytest.mark.django_db
class TestAislamientoServicioCliente:
    def test_listado_solo_devuelve_datos_de_empresa_propia(
        self, user_a, user_b, categoria_ticket_a, categoria_ticket_b
    ):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(URL_CATEGORIAS_TICKET)
        assert response.status_code == 200
        data = response.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_categoria_ticket"]) for r in resultados}
        assert str(categoria_ticket_a.id_categoria_ticket) in ids
        assert str(categoria_ticket_b.id_categoria_ticket) not in ids, (
            "LEAK: datos de Empresa B visibles para Empresa A"
        )

    def test_get_objeto_de_otra_empresa_devuelve_404(self, user_a, categoria_ticket_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(f"{URL_CATEGORIAS_TICKET}{categoria_ticket_b.id_categoria_ticket}/")
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )

    def test_patch_objeto_de_otra_empresa_devuelve_404(self, user_a, categoria_ticket_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.patch(
            f"{URL_CATEGORIAS_TICKET}{categoria_ticket_b.id_categoria_ticket}/",
            {"nombre_categoria": "Hackeado"},
            format="json",
        )
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )
        categoria_ticket_b.refresh_from_db()
        assert categoria_ticket_b.nombre_categoria == "Soporte Beta", (
            "CRÍTICO: nombre de categoría de Empresa B fue modificado desde Empresa A."
        )


# ---------------------------------------------------------------------------
# 5. Almacenes — Almacen
# ---------------------------------------------------------------------------

URL_ALMACENES = "/api/almacenes/almacenes/"


@pytest.fixture
def almacen_a(db, empresa_a):
    return Almacen.objects.create(
        id_empresa=empresa_a,
        nombre_almacen="Almacén Alpha",
        codigo_almacen="ALM-A",
    )


@pytest.fixture
def almacen_b(db, empresa_b):
    return Almacen.objects.create(
        id_empresa=empresa_b,
        nombre_almacen="Almacén Beta",
        codigo_almacen="ALM-B",
    )


@pytest.mark.django_db
class TestAislamientoAlmacenes:
    def test_listado_solo_devuelve_datos_de_empresa_propia(self, user_a, user_b, almacen_a, almacen_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(URL_ALMACENES)
        assert response.status_code == 200
        data = response.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_almacen"]) for r in resultados}
        assert str(almacen_a.id_almacen) in ids
        assert str(almacen_b.id_almacen) not in ids, (
            "LEAK: datos de Empresa B visibles para Empresa A"
        )

    def test_get_objeto_de_otra_empresa_devuelve_404(self, user_a, almacen_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(f"{URL_ALMACENES}{almacen_b.id_almacen}/")
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )

    def test_patch_objeto_de_otra_empresa_devuelve_404(self, user_a, almacen_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.patch(
            f"{URL_ALMACENES}{almacen_b.id_almacen}/",
            {"nombre_almacen": "Hackeado"},
            format="json",
        )
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )
        almacen_b.refresh_from_db()
        assert almacen_b.nombre_almacen == "Almacén Beta", (
            "CRÍTICO: nombre de almacén de Empresa B fue modificado desde Empresa A."
        )


# ---------------------------------------------------------------------------
# 6. Manufactura — CentroTrabajo
#    (preferido sobre ListaMateriales/OrdenProduccion porque tiene empresa FK directo
#     y no requiere otros FK obligatorios)
# ---------------------------------------------------------------------------

URL_CENTROS_TRABAJO = "/api/manufactura/centros-trabajo/"


@pytest.fixture
def centro_trabajo_a(db, empresa_a):
    return CentroTrabajo.objects.create(
        id_empresa=empresa_a,
        codigo_centro="CT-A",
        nombre_centro="Centro Alpha",
        tipo_centro="MANUAL",
    )


@pytest.fixture
def centro_trabajo_b(db, empresa_b):
    return CentroTrabajo.objects.create(
        id_empresa=empresa_b,
        codigo_centro="CT-B",
        nombre_centro="Centro Beta",
        tipo_centro="MANUAL",
    )


@pytest.mark.django_db
class TestAislamientoManufactura:
    def test_listado_solo_devuelve_datos_de_empresa_propia(
        self, user_a, user_b, centro_trabajo_a, centro_trabajo_b
    ):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(URL_CENTROS_TRABAJO)
        assert response.status_code == 200
        data = response.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_centro_trabajo"]) for r in resultados}
        assert str(centro_trabajo_a.id_centro_trabajo) in ids
        assert str(centro_trabajo_b.id_centro_trabajo) not in ids, (
            "LEAK: datos de Empresa B visibles para Empresa A"
        )

    def test_get_objeto_de_otra_empresa_devuelve_404(self, user_a, centro_trabajo_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(f"{URL_CENTROS_TRABAJO}{centro_trabajo_b.id_centro_trabajo}/")
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )

    def test_patch_objeto_de_otra_empresa_devuelve_404(self, user_a, centro_trabajo_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.patch(
            f"{URL_CENTROS_TRABAJO}{centro_trabajo_b.id_centro_trabajo}/",
            {"nombre_centro": "Hackeado"},
            format="json",
        )
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )
        centro_trabajo_b.refresh_from_db()
        assert centro_trabajo_b.nombre_centro == "Centro Beta", (
            "CRÍTICO: nombre de centro de trabajo de Empresa B fue modificado desde Empresa A."
        )


# ---------------------------------------------------------------------------
# 7. Gestión de Aprobaciones — TipoAprobacion
# ---------------------------------------------------------------------------

URL_TIPOS_APROBACION = "/api/gestion-aprobaciones/tipos-aprobacion/"


@pytest.fixture
def tipo_aprobacion_a(db, empresa_a):
    return TipoAprobacion.objects.create(
        id_empresa=empresa_a,
        codigo_tipo="APRO-A",
        nombre_tipo="Aprobación Alpha",
        modulo_origen="ventas",
    )


@pytest.fixture
def tipo_aprobacion_b(db, empresa_b):
    return TipoAprobacion.objects.create(
        id_empresa=empresa_b,
        codigo_tipo="APRO-B",
        nombre_tipo="Aprobación Beta",
        modulo_origen="ventas",
    )


@pytest.mark.django_db
class TestAislamientoGestionAprobaciones:
    def test_listado_solo_devuelve_datos_de_empresa_propia(
        self, user_a, user_b, tipo_aprobacion_a, tipo_aprobacion_b
    ):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(URL_TIPOS_APROBACION)
        assert response.status_code == 200
        data = response.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_tipo_aprobacion"]) for r in resultados}
        assert str(tipo_aprobacion_a.id_tipo_aprobacion) in ids
        assert str(tipo_aprobacion_b.id_tipo_aprobacion) not in ids, (
            "LEAK: datos de Empresa B visibles para Empresa A"
        )

    def test_get_objeto_de_otra_empresa_devuelve_404(self, user_a, tipo_aprobacion_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(f"{URL_TIPOS_APROBACION}{tipo_aprobacion_b.id_tipo_aprobacion}/")
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )

    def test_patch_objeto_de_otra_empresa_devuelve_404(self, user_a, tipo_aprobacion_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.patch(
            f"{URL_TIPOS_APROBACION}{tipo_aprobacion_b.id_tipo_aprobacion}/",
            {"nombre_tipo": "Hackeado"},
            format="json",
        )
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )
        tipo_aprobacion_b.refresh_from_db()
        assert tipo_aprobacion_b.nombre_tipo == "Aprobación Beta", (
            "CRÍTICO: nombre de tipo de aprobación de Empresa B fue modificado desde Empresa A."
        )


# ---------------------------------------------------------------------------
# 8. Integración B2B — ConfiguracionIntegracion
# ---------------------------------------------------------------------------

URL_CONFIG_INTEGRACION = "/api/integracion-b2b/configuracion-integracion/"


@pytest.fixture
def config_integracion_a(db, empresa_a):
    return ConfiguracionIntegracion.objects.create(
        id_empresa=empresa_a,
        nombre_integracion="Integración Alpha",
        tipo_integracion="REST",
        formato_datos="JSON",
    )


@pytest.fixture
def config_integracion_b(db, empresa_b):
    return ConfiguracionIntegracion.objects.create(
        id_empresa=empresa_b,
        nombre_integracion="Integración Beta",
        tipo_integracion="REST",
        formato_datos="JSON",
    )


@pytest.mark.django_db
class TestAislamientoIntegracionB2B:
    def test_listado_solo_devuelve_datos_de_empresa_propia(
        self, user_a, user_b, config_integracion_a, config_integracion_b
    ):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(URL_CONFIG_INTEGRACION)
        assert response.status_code == 200
        data = response.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_configuracion"]) for r in resultados}
        assert str(config_integracion_a.id_configuracion) in ids
        assert str(config_integracion_b.id_configuracion) not in ids, (
            "LEAK: datos de Empresa B visibles para Empresa A"
        )

    def test_get_objeto_de_otra_empresa_devuelve_404(self, user_a, config_integracion_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(f"{URL_CONFIG_INTEGRACION}{config_integracion_b.id_configuracion}/")
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )

    def test_patch_objeto_de_otra_empresa_devuelve_404(self, user_a, config_integracion_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.patch(
            f"{URL_CONFIG_INTEGRACION}{config_integracion_b.id_configuracion}/",
            {"nombre_integracion": "Hackeado"},
            format="json",
        )
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )
        config_integracion_b.refresh_from_db()
        assert config_integracion_b.nombre_integracion == "Integración Beta", (
            "CRÍTICO: nombre de integración de Empresa B fue modificado desde Empresa A."
        )


# ---------------------------------------------------------------------------
# 9. Banca Electrónica — CuentaBancariaEmpresa
#    Nota: el campo empresa FK se llama `empresa` (no `id_empresa`).
#    La PK es el `id` auto-integer de Django (no tiene pk UUID explícita).
# ---------------------------------------------------------------------------

URL_CUENTAS_BANCARIAS = "/api/banca-electronica/cuentas-bancarias-empresa/"


@pytest.fixture
def cuenta_bancaria_a(db, empresa_a, moneda_usd):
    return CuentaBancariaEmpresa.objects.create(
        empresa=empresa_a,
        banco="Banco Alpha",
        numero_cuenta="0102-1111-11-1111111111",
        tipo_cuenta="corriente",
        moneda=moneda_usd,
    )


@pytest.fixture
def cuenta_bancaria_b(db, empresa_b, moneda_usd):
    return CuentaBancariaEmpresa.objects.create(
        empresa=empresa_b,
        banco="Banco Beta",
        numero_cuenta="0102-2222-22-2222222222",
        tipo_cuenta="corriente",
        moneda=moneda_usd,
    )


@pytest.mark.django_db
class TestAislamientoBancaElectronica:
    def test_listado_solo_devuelve_datos_de_empresa_propia(
        self, user_a, user_b, cuenta_bancaria_a, cuenta_bancaria_b
    ):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(URL_CUENTAS_BANCARIAS)
        assert response.status_code == 200
        data = response.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id"]) for r in resultados}
        assert str(cuenta_bancaria_a.id) in ids
        assert str(cuenta_bancaria_b.id) not in ids, (
            "LEAK: datos de Empresa B visibles para Empresa A"
        )

    def test_get_objeto_de_otra_empresa_devuelve_404(self, user_a, cuenta_bancaria_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(f"{URL_CUENTAS_BANCARIAS}{cuenta_bancaria_b.id}/")
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )

    def test_patch_objeto_de_otra_empresa_devuelve_404(self, user_a, cuenta_bancaria_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.patch(
            f"{URL_CUENTAS_BANCARIAS}{cuenta_bancaria_b.id}/",
            {"banco": "Hackeado"},
            format="json",
        )
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )
        cuenta_bancaria_b.refresh_from_db()
        assert cuenta_bancaria_b.banco == "Banco Beta", (
            "CRÍTICO: banco de Empresa B fue modificado desde Empresa A."
        )


# ---------------------------------------------------------------------------
# 10. Personalización — PersonalizacionConfig
# ---------------------------------------------------------------------------

URL_PERSONALIZACION = "/api/personalizacion/configuraciones/"


@pytest.fixture
def personalizacion_config_a(db, empresa_a):
    return PersonalizacionConfig.objects.create(
        id_empresa=empresa_a,
        version=1,
        config_yaml="campos: []",
        config_dict={},
        activo=True,
    )


@pytest.fixture
def personalizacion_config_b(db, empresa_b):
    return PersonalizacionConfig.objects.create(
        id_empresa=empresa_b,
        version=1,
        config_yaml="campos: []",
        config_dict={},
        activo=True,
    )


@pytest.mark.django_db
class TestAislamientoPersonalizacion:
    def test_listado_solo_devuelve_datos_de_empresa_propia(
        self, user_a, user_b, personalizacion_config_a, personalizacion_config_b
    ):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(URL_PERSONALIZACION)
        assert response.status_code == 200
        data = response.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_config"]) for r in resultados}
        assert str(personalizacion_config_a.id_config) in ids
        assert str(personalizacion_config_b.id_config) not in ids, (
            "LEAK: datos de Empresa B visibles para Empresa A"
        )

    def test_get_objeto_de_otra_empresa_devuelve_404(self, user_a, personalizacion_config_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(f"{URL_PERSONALIZACION}{personalizacion_config_b.id_config}/")
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )

    def test_patch_objeto_de_otra_empresa_devuelve_404(self, user_a, personalizacion_config_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.patch(
            f"{URL_PERSONALIZACION}{personalizacion_config_b.id_config}/",
            {"config_yaml": "campos: [hackeado]"},
            format="json",
        )
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )
        personalizacion_config_b.refresh_from_db()
        assert personalizacion_config_b.config_yaml == "campos: []", (
            "CRÍTICO: config_yaml de Empresa B fue modificado desde Empresa A."
        )


# ---------------------------------------------------------------------------
# 11. Tesorería — Caja (finanzas.Caja, accedida vía /api/tesoreria/cajas/)
#     Nota: el campo empresa FK se llama `empresa` (no `id_empresa`).
#     La PK es `id_caja` (UUID).
# ---------------------------------------------------------------------------

URL_CAJAS = "/api/tesoreria/cajas/"


@pytest.fixture
def caja_a(db, empresa_a, moneda_usd):
    return Caja.objects.create(
        empresa=empresa_a,
        nombre="Caja Alpha",
        tipo_caja="REGISTRADORA",
        moneda=moneda_usd,
    )


@pytest.fixture
def caja_b(db, empresa_b, moneda_usd):
    return Caja.objects.create(
        empresa=empresa_b,
        nombre="Caja Beta",
        tipo_caja="REGISTRADORA",
        moneda=moneda_usd,
    )


@pytest.mark.django_db
class TestAislamientoTesoreria:
    def test_listado_solo_devuelve_datos_de_empresa_propia(self, user_a, user_b, caja_a, caja_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(URL_CAJAS)
        assert response.status_code == 200
        data = response.data
        resultados = data["results"] if isinstance(data, dict) and "results" in data else data
        ids = {str(r["id_caja"]) for r in resultados}
        assert str(caja_a.id_caja) in ids
        assert str(caja_b.id_caja) not in ids, (
            "LEAK: datos de Empresa B visibles para Empresa A"
        )

    def test_get_objeto_de_otra_empresa_devuelve_404(self, user_a, caja_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.get(f"{URL_CAJAS}{caja_b.id_caja}/")
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )

    def test_patch_objeto_de_otra_empresa_devuelve_404(self, user_a, caja_b):
        client = APIClient()
        client.force_authenticate(user=user_a)
        response = client.patch(
            f"{URL_CAJAS}{caja_b.id_caja}/",
            {"nombre": "Hackeado"},
            format="json",
        )
        assert response.status_code == 404, (
            f"LEAK: status {response.status_code}, esperado 404"
        )
        caja_b.refresh_from_db()
        assert caja_b.nombre == "Caja Beta", (
            "CRÍTICO: nombre de caja de Empresa B fue modificado desde Empresa A."
        )
