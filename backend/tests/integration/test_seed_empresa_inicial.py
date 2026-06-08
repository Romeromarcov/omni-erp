"""
Plan 0 · Tarea 0.4 — Tests del comando ``seed_empresa_inicial``.

Verifican que el seed de arranque de producción:
  1. Crea la estructura completa (Empresa → admin → sucursal → caja física+virtual).
  2. Es idempotente (relanzarlo no duplica).
  3. Rechaza contraseñas débiles (AUTH_PASSWORD_VALIDATORS) sin escribir nada.
  4. Nunca pisa la contraseña de un admin ya existente.
  5. No incrusta secretos: la contraseña viene de --admin-password / env.
"""

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError

from apps.core.models import Empresa, Sucursal, Usuarios
from apps.finanzas.models import Caja, CajaFisica

RIF = "J-40999888-7"
PASSWORD = "Sup3rS3gura_2026!"

BASE_ARGS = dict(
    nombre_legal="Distribuidora Test C.A.",
    rif=RIF,
    admin_username="admin_dist",
    admin_email="admin@dist.test",
)


def _run(**overrides):
    call_command("seed_empresa_inicial", **{**BASE_ARGS, **overrides})


@pytest.mark.django_db
def test_crea_estructura_completa(monkeypatch):
    monkeypatch.setenv("OMNI_SEED_ADMIN_PASSWORD", PASSWORD)
    _run()

    empresa = Empresa.objects.get(identificador_fiscal=RIF)
    assert empresa.nombre_legal == "Distribuidora Test C.A."
    assert empresa.id_moneda_base is not None

    sucursal = Sucursal.objects.get(id_empresa=empresa)
    assert empresa.cajas_fisicas.count() == 1
    caja = Caja.objects.get(empresa=empresa)
    assert caja.moneda == empresa.id_moneda_base
    assert caja.caja_fisica is not None

    admin = Usuarios.objects.get(username="admin_dist")
    assert empresa in admin.empresas.all()
    assert sucursal in admin.sucursales.all()
    assert admin.id_sucursal_predeterminada == sucursal
    assert admin.check_password(PASSWORD)
    # Por defecto el admin de la empresa NO es superusuario Omni (proveedor).
    assert admin.es_superusuario_omni is False


@pytest.mark.django_db
def test_idempotente(monkeypatch):
    monkeypatch.setenv("OMNI_SEED_ADMIN_PASSWORD", PASSWORD)
    _run()
    _run()

    assert Empresa.objects.filter(identificador_fiscal=RIF).count() == 1
    assert Usuarios.objects.filter(username="admin_dist").count() == 1
    assert CajaFisica.objects.filter(empresa__identificador_fiscal=RIF).count() == 1
    assert Caja.objects.filter(empresa__identificador_fiscal=RIF).count() == 1
    assert Sucursal.objects.filter(id_empresa__identificador_fiscal=RIF).count() == 1


@pytest.mark.django_db
def test_password_debil_rechazada_sin_escribir(monkeypatch):
    monkeypatch.delenv("OMNI_SEED_ADMIN_PASSWORD", raising=False)
    with pytest.raises(CommandError):
        _run(admin_password="123")
    # La validación ocurre antes de tocar la BD: no debe quedar nada creado.
    assert not Empresa.objects.filter(identificador_fiscal=RIF).exists()
    assert not Usuarios.objects.filter(username="admin_dist").exists()


@pytest.mark.django_db
def test_no_pisa_password_de_admin_existente(monkeypatch):
    monkeypatch.setenv("OMNI_SEED_ADMIN_PASSWORD", PASSWORD)
    _run()
    # Segunda corrida con OTRA contraseña: el admin ya existe → no se cambia.
    _run(admin_password="Otra_Cosa_Distinta_9!")
    admin = Usuarios.objects.get(username="admin_dist")
    assert admin.check_password(PASSWORD)
    assert not admin.check_password("Otra_Cosa_Distinta_9!")


@pytest.mark.django_db
def test_flag_superusuario_omni(monkeypatch):
    monkeypatch.setenv("OMNI_SEED_ADMIN_PASSWORD", PASSWORD)
    _run(es_superusuario_omni=True)
    admin = Usuarios.objects.get(username="admin_dist")
    assert admin.es_superusuario_omni is True


# ── create_initial_data deprecado: bloqueado fuera de DEBUG ─────────────────


@pytest.mark.django_db
def test_create_initial_data_bloqueado_en_produccion(settings):
    """El seed demo (admin/admin123) no debe poder correr con DEBUG=False."""
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("create_initial_data")
    assert not Usuarios.objects.filter(username="admin").exists()


@pytest.mark.django_db
def test_create_initial_data_funciona_en_dev(settings):
    """En DEBUG=True sigue sirviendo para bootstrap de desarrollo."""
    settings.DEBUG = True
    call_command("create_initial_data")
    assert Usuarios.objects.filter(username="admin").exists()
