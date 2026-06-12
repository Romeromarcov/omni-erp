"""
Herramientas MCP del dominio nómina (ADR-003, R-CODE-7) — CTF-013.

Llamadas directo como funciones con CapabilityToken reales (patrón de
``test_ventas_mcp_cobertura.py``):

- ``nomina_procesar_proceso``: happy path (recibos + totales), proceso no
  encontrado, ya COMPLETADO → error, scope faltante, empresa_id ≠ tenant,
  aislamiento cross-tenant (R-CODE-1).
- ``nomina_resumen_proceso``: totales y recibos, scope faltante.
- Export ``MCP_TOOLS`` para el auto-discovery del servidor.
"""
import datetime
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.models import CapabilityToken
from apps.nomina.mcp import MCP_TOOLS, nomina_procesar_proceso, nomina_resumen_proceso
from apps.nomina.models import Nomina, PeriodoNomina, ProcesoNomina
from apps.rrhh.models import Empleado

pytestmark = pytest.mark.django_db


def _token(empresa, scopes):
    return CapabilityToken.objects.create(empresa=empresa, nombre="tok-nomina-test", scopes=scopes)


@pytest.fixture
def proceso_a(empresa_a):
    periodo = PeriodoNomina.objects.create(
        id_empresa=empresa_a,
        nombre_periodo="Junio 2026 MCP",
        fecha_inicio=datetime.date(2026, 6, 1),
        fecha_fin=datetime.date(2026, 6, 30),
        fecha_pago=datetime.date(2026, 7, 1),
        tipo_periodo="MENSUAL",
    )
    return ProcesoNomina.objects.create(
        id_empresa=empresa_a,
        id_periodo_nomina=periodo,
        numero_proceso="PROC-MCP-001",
        fecha_proceso=timezone.now(),
        estado="EN_PROCESO",
    )


@pytest.fixture
def empleado_a(empresa_a):
    return Empleado.objects.create(
        empresa=empresa_a,
        nombre="Pedro",
        apellido="Perez",
        cedula="V-55555555",
        fecha_ingreso=datetime.date(2024, 1, 1),
        documento_json={"salario_mensual": "600.00"},
    )


class TestProcesarProceso:
    def test_happy_path(self, empresa_a, proceso_a, empleado_a):
        tok = _token(empresa_a, ["nomina:write"])
        res = nomina_procesar_proceso(str(tok.token), str(empresa_a.id_empresa), str(proceso_a.pk))
        assert "error" not in res
        assert res["estado"] == "COMPLETADO"
        assert res["total_empleados"] == 1
        # 600: SSO 24.00 + FAOV 6.00 + RPE 3.00 = 33.00 → neto 567.00
        assert Decimal(res["total_deducciones"]) == Decimal("33.00")
        assert Decimal(res["total_neto"]) == Decimal("567.00")
        assert Nomina.objects.filter(id_proceso_nomina=proceso_a).count() == 1

    def test_proceso_no_encontrado(self, empresa_a):
        tok = _token(empresa_a, ["nomina:write"])
        res = nomina_procesar_proceso(str(tok.token), str(empresa_a.id_empresa), str(uuid.uuid4()))
        assert "error" in res

    def test_ya_completado_devuelve_error(self, empresa_a, proceso_a, empleado_a):
        proceso_a.estado = "COMPLETADO"
        proceso_a.save(update_fields=["estado"])
        tok = _token(empresa_a, ["nomina:write"])
        res = nomina_procesar_proceso(str(tok.token), str(empresa_a.id_empresa), str(proceso_a.pk))
        assert "COMPLETADO" in res["error"]

    def test_scope_faltante(self, empresa_a, proceso_a):
        tok = _token(empresa_a, ["nomina:read"])  # write requerido
        with pytest.raises(PermissionError):
            nomina_procesar_proceso(str(tok.token), str(empresa_a.id_empresa), str(proceso_a.pk))

    def test_empresa_distinta_al_token(self, empresa_a, empresa_b, proceso_a):
        tok = _token(empresa_a, ["nomina:write"])
        with pytest.raises(PermissionError):
            nomina_procesar_proceso(str(tok.token), str(empresa_b.id_empresa), str(proceso_a.pk))

    def test_cross_tenant_no_encuentra_proceso_ajeno(self, empresa_a, empresa_b, proceso_a):
        """R-CODE-1: token de B no procesa procesos de A."""
        tok_b = _token(empresa_b, ["nomina:write"])
        res = nomina_procesar_proceso(str(tok_b.token), str(empresa_b.id_empresa), str(proceso_a.pk))
        assert "error" in res
        proceso_a.refresh_from_db()
        assert proceso_a.estado == "EN_PROCESO"


class TestResumenProceso:
    def test_resumen_con_recibos(self, empresa_a, proceso_a, empleado_a):
        tok = _token(empresa_a, ["nomina:write", "nomina:read"])
        nomina_procesar_proceso(str(tok.token), str(empresa_a.id_empresa), str(proceso_a.pk))
        res = nomina_resumen_proceso(str(tok.token), str(empresa_a.id_empresa), str(proceso_a.pk))
        assert res["estado"] == "COMPLETADO"
        assert len(res["recibos"]) == 1
        recibo = res["recibos"][0]
        assert recibo["empleado"] == "Pedro Perez"
        assert Decimal(recibo["total_neto"]) == Decimal("567.00")

    def test_scope_faltante(self, empresa_a, proceso_a):
        tok = _token(empresa_a, ["nomina:write"])  # read requerido
        with pytest.raises(PermissionError):
            nomina_resumen_proceso(str(tok.token), str(empresa_a.id_empresa), str(proceso_a.pk))


def test_mcp_tools_exporta_las_dos_herramientas():
    nombres = {t["name"] for t in MCP_TOOLS}
    assert nombres == {"nomina_procesar_proceso", "nomina_resumen_proceso"}
    assert all("scope" in t and callable(t["fn"]) for t in MCP_TOOLS)
