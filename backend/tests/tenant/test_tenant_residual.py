"""
Tests de aislamiento residual (H-SEC-7..12, FE-HIGH-12).

Cubre los endpoints que recibían pk/empresa_id crudos o ``request.user.empresa``
sin acotar a las empresas visibles del usuario.
"""

from decimal import Decimal

import pytest

from django.utils import timezone
from rest_framework.test import APIClient


# ── H-SEC-7 · Permisos globales solo modificables por superusuario ─────────


@pytest.mark.django_db
def test_permisos_globales_no_modificables_por_no_superuser(user_a):
    from apps.core.models import Permisos

    client = APIClient()
    client.force_authenticate(user=user_a)
    resp = client.post(
        "/api/core/permisos/",
        {"codigo_permiso": "test.crear", "nombre_permiso": "Test", "modulo": "core"},
        format="json",
    )
    assert resp.status_code == 403
    assert not Permisos.objects.filter(codigo_permiso="test.crear").exists()


@pytest.mark.django_db
def test_permisos_globales_modificables_por_superuser(db):
    from django.contrib.auth import get_user_model
    from apps.core.models import Permisos

    User = get_user_model()
    su = User.objects.create_user(username="su_omni", password="x", is_active=True)
    su.es_superusuario_omni = True
    su.save()

    client = APIClient()
    client.force_authenticate(user=su)
    resp = client.post(
        "/api/core/permisos/",
        {"codigo_permiso": "test.crear", "nombre_permiso": "Test", "modulo": "core"},
        format="json",
    )
    assert resp.status_code == 201
    assert Permisos.objects.filter(codigo_permiso="test.crear").exists()


# ── H-SEC-9 · marcar_asistencia valida tenant del empleado ─────────────────


@pytest.fixture
def empleado_b(db, empresa_b):
    from apps.rrhh.models import Empleado

    return Empleado.objects.create(
        empresa=empresa_b,
        nombre="Beta",
        apellido="Empleado",
        cedula="V-99999999",
        fecha_ingreso=timezone.now().date(),
    )


@pytest.mark.django_db
def test_no_puedo_marcar_asistencia_de_empleado_otro_tenant(user_a, empleado_b):
    client = APIClient()
    client.force_authenticate(user=user_a)
    resp = client.post(
        "/api/control-asistencia/registros-asistencia/marcar_asistencia/",
        {"empleado_id": str(empleado_b.pk), "tipo_marcado": "ENTRADA"},
        format="json",
    )
    assert resp.status_code == 404
    from apps.control_asistencia.models import RegistroAsistencia

    assert not RegistroAsistencia.objects.filter(id_empleado=empleado_b).exists()


# ── H-SEC-10 · balance_comprobacion valida empresa_id ──────────────────────


@pytest.mark.django_db
def test_balance_comprobacion_empresa_ajena_404(user_a, empresa_b):
    client = APIClient()
    client.force_authenticate(user=user_a)
    resp = client.get(
        f"/api/contabilidad/asientos-contables/balance_comprobacion/?empresa_id={empresa_b.id_empresa}"
    )
    assert resp.status_code == 404


# ── FE-HIGH-12 · TransaccionFinanciera cross-tenant ────────────────────────


@pytest.fixture
def metodo_pago_b(db, empresa_b):
    from apps.finanzas.models import MetodoPago

    return MetodoPago.objects.create(empresa=empresa_b, nombre_metodo="Efectivo", tipo_metodo="EFECTIVO")


@pytest.fixture
def transaccion_b(db, empresa_b, moneda_usd, metodo_pago_b, user_b):
    from apps.finanzas.models import TransaccionFinanciera

    return TransaccionFinanciera.objects.create(
        id_empresa=empresa_b,
        fecha_hora_transaccion=timezone.now(),
        tipo_transaccion="INGRESO",
        monto_transaccion=Decimal("100.00"),
        id_moneda_transaccion=moneda_usd,
        monto_base_empresa=Decimal("100.00"),
        id_metodo_pago=metodo_pago_b,
        id_usuario_registro=user_b,
    )


@pytest.mark.django_db
def test_transaccion_financiera_cross_tenant_no_lista(user_a, empresa_b, transaccion_b):
    client = APIClient()
    client.force_authenticate(user=user_a)
    # Aun pasando el id_empresa ajeno explícito, no debe filtrarse el dato.
    resp = client.get(f"/api/finanzas/transacciones-financieras/?id_empresa={empresa_b.id_empresa}")
    assert resp.status_code == 200
    data = resp.data["results"] if isinstance(resp.data, dict) and "results" in resp.data else resp.data
    ids = {str(r.get("id_transaccion")) for r in data}
    assert str(transaccion_b.id_transaccion) not in ids, "LEAK: transacción de otra empresa visible."
