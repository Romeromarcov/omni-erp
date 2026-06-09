"""Tests del middleware de contexto RLS (``apps.core.middleware``).

Verifican que, con ``RLS_ENABLED=True``, el middleware fija el contexto correcto
según el usuario (normal / superusuario Omni / anónimo) y resuelve el usuario
tanto por sesión como por token JWT. El conjunto visible se observa *durante* el
request (dentro de ``get_response``), porque el middleware restaura el default al
finalizar.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from apps.core import rls
from apps.core.middleware import RLSContextMiddleware
from apps.core.models import Sucursal

pytestmark = [pytest.mark.django_db, pytest.mark.tenant]


@pytest.fixture(autouse=True)
def _enforce_rls_role(rls_test_role):
    """Corre el test bajo un rol sujeto a RLS si el rol de conexión la salta
    (CI superusuario); no-op en dev local. Ver tests_api/conftest.py."""
    if rls_test_role is None:
        yield
        return
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(f'SET ROLE "{rls_test_role}"')
    try:
        yield
    finally:
        with connection.cursor() as cur:
            cur.execute("RESET ROLE")


@pytest.fixture
def sucursales(empresa_a, empresa_b):
    rls.apply_system_default()
    Sucursal.objects.create(id_empresa=empresa_a, nombre="Sede A", codigo_sucursal="A001")
    Sucursal.objects.create(id_empresa=empresa_b, nombre="Sede B", codigo_sucursal="B001")
    yield
    rls.apply_system_default()


def _run(user=None, auth_header=None):
    """Ejecuta el middleware y devuelve el conjunto de id_empresa visibles
    durante el request."""
    captured = {}

    def get_response(request):
        captured["ids"] = set(
            Sucursal.objects.values_list("id_empresa_id", flat=True)
        )
        return HttpResponse("ok")

    mw = RLSContextMiddleware(get_response)
    request = RequestFactory().get("/api/x/")
    request.user = user if user is not None else AnonymousUser()
    if auth_header:
        request.META["HTTP_AUTHORIZATION"] = auth_header
    response = mw(request)
    assert response.status_code == 200
    return captured["ids"]


@override_settings(RLS_ENABLED=True)
def test_usuario_normal_solo_ve_su_empresa(sucursales, user_a, empresa_a):
    assert _run(user=user_a) == {empresa_a.id_empresa}


@override_settings(RLS_ENABLED=True)
def test_superusuario_omni_ve_todas(sucursales, empresa_a, empresa_b):
    User = get_user_model()
    su = User.objects.create_user(
        username="omni_root", password="x", email="root@omni.test",
        is_active=True, es_superusuario_omni=True,
    )
    assert _run(user=su) == {empresa_a.id_empresa, empresa_b.id_empresa}


@override_settings(RLS_ENABLED=True)
def test_anonimo_fail_closed(sucursales):
    assert _run(user=AnonymousUser()) == set()


@override_settings(RLS_ENABLED=True)
def test_resuelve_usuario_por_jwt(sucursales, user_a, empresa_a):
    from rest_framework_simplejwt.tokens import AccessToken

    token = AccessToken.for_user(user_a)
    # request.user anónimo: el middleware debe resolver vía el header JWT.
    assert _run(user=AnonymousUser(), auth_header=f"Bearer {token}") == {
        empresa_a.id_empresa
    }


@override_settings(RLS_ENABLED=True)
def test_jwt_invalido_es_fail_closed(sucursales):
    assert _run(user=AnonymousUser(), auth_header="Bearer token-basura") == set()


@override_settings(RLS_ENABLED=True)
def test_streaming_conserva_contexto_rls(sucursales, user_a, empresa_a):
    """En SSE el cuerpo se genera tras salir del middleware: el contexto RLS no
    debe resetearse o el generador vería todas las empresas (bypass on)."""
    from django.http import StreamingHttpResponse

    seen = {}

    def gen():
        seen["ids"] = set(Sucursal.objects.values_list("id_empresa_id", flat=True))
        yield b"data: x\n\n"

    def get_response(request):
        return StreamingHttpResponse(gen(), content_type="text/event-stream")

    mw = RLSContextMiddleware(get_response)
    request = RequestFactory().get("/api/stream/")
    request.user = user_a
    response = mw(request)
    # El generador corre al consumir el stream (después del middleware).
    list(response.streaming_content)
    assert seen["ids"] == {empresa_a.id_empresa}


@override_settings(RLS_ENABLED=False)
def test_middleware_se_descarta_si_rls_desactivado():
    with pytest.raises(MiddlewareNotUsed):
        RLSContextMiddleware(lambda request: HttpResponse())
