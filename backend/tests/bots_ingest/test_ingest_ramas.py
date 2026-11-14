"""Ingesta de bots: ramas de borde de modelos, serializadores, vistas y servicio de ingesta.

Complementa ``test_ingest.py`` (flujo feliz, idempotencia y aislamiento) con los caminos de
error: permisos, filtros, ``completar`` fuera de estado, alta de usuarios de Telegram y la
carrera de idempotencia.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from tests.bots_ingest.helpers import TG, UBIC, URL
from tests.factories import UsuariosFactory

from django.db import IntegrityError
from rest_framework.test import APIClient

from apps.bots_ingest.models import BotUsuario, IngestaBot
from apps.bots_ingest.services import ingesta as svc
from apps.crm.models import Etapa, Pipeline

pytestmark = [pytest.mark.django_db]

USUARIOS = "/api/bots/usuarios/"


def _ingesta(bot_usuario, *, kind=IngestaBot.Kind.PAGO, estado=IngestaBot.Estado.INCOMPLETO, key="k"):
    return IngestaBot.objects.create(
        id_empresa=bot_usuario.id_empresa,
        bot_usuario=bot_usuario,
        kind=kind,
        idempotency_key=key,
        payload={"monto": "10"},
        estado=estado,
    )


# ── Modelos ──────────────────────────────────────────────────────────────────


def test_representaciones_de_texto(bot_usuario):
    ing = _ingesta(bot_usuario, key="clave-7")
    assert str(bot_usuario).startswith(str(TG))
    assert str(ing) == "pago INCOMPLETO clave-7"


# ── Permisos y serializador de entrada ───────────────────────────────────────


def test_sin_autenticar_no_puede_consultar():
    r = APIClient().get(URL)
    assert r.status_code in (401, 403)


def test_la_fuente_debe_traer_telegram_user_id(api, bot_usuario):
    r = api.post(
        URL,
        {"kind": "contacto", "draft": {"nombre": "A"}, "source": {}, "idempotency_key": "k1"},
        format="json",
    )
    assert r.status_code == 400
    assert "source" in r.data


def test_un_telegram_user_id_no_numerico_es_403(api, bot_usuario):
    r = api.post(
        URL,
        {
            "kind": "contacto",
            "draft": {"nombre": "A"},
            "source": {"telegram_user_id": "no-es-un-numero"},
            "idempotency_key": "k2",
        },
        format="json",
    )
    assert r.status_code == 403


# ── Listado y filtros ────────────────────────────────────────────────────────


def test_el_listado_filtra_por_tipo_y_por_estado(api, bot_usuario):
    pago = _ingesta(bot_usuario, kind=IngestaBot.Kind.PAGO, key="a")
    ped = _ingesta(
        bot_usuario, kind=IngestaBot.Kind.PEDIDO, estado=IngestaBot.Estado.BORRADOR, key="b"
    )

    def ids(**params):
        return {x["id_ingesta"] for x in api.get(URL, params).data["results"]}

    assert ids(kind="pago") == {str(pago.pk)}
    assert ids(kind="pedido") == {str(ped.pk)}
    assert ids(estado="BORRADOR") == {str(ped.pk)}


# ── completar ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("cuerpo", [{}, {"cambios": {}}, {"cambios": "texto"}, {"cambios": ["x"]}])
def test_completar_exige_cambios_con_al_menos_un_campo(api, bot_usuario, cuerpo):
    ing = _ingesta(bot_usuario)
    r = api.post(f"{URL}{ing.pk}/completar/", cuerpo, format="json")
    assert r.status_code == 400
    assert "cambios" in r.data["error"]


def test_completar_una_ingesta_ya_sincronizada_da_409(api, bot_usuario):
    ing = _ingesta(bot_usuario, estado=IngestaBot.Estado.SINCRONIZADO)
    r = api.post(f"{URL}{ing.pk}/completar/", {"cambios": {"referencia": "9"}}, format="json")
    assert r.status_code == 409
    ing.refresh_from_db()
    assert ing.estado == IngestaBot.Estado.SINCRONIZADO  # no se tocó


# ── Carrera de idempotencia ──────────────────────────────────────────────────


def _ingerir(servicio, key):
    return svc.ingerir(
        servicio=servicio,
        kind="contacto",
        draft={"nombre": "Carrera", "telefono": "0414-1234567", "ubicacion": UBIC},
        fuente={"telegram_user_id": TG},
        idempotency_key=key,
    )


def test_si_otra_peticion_gano_la_carrera_se_devuelve_su_ingesta(servicio, bot_usuario, empresa_a):
    """Dos envíos simultáneos con la misma clave: el perdedor recibe la ingesta ganadora."""
    pipe = Pipeline.objects.create(id_empresa=empresa_a, nombre="Ventas", es_predeterminado=True)
    Etapa.objects.create(id_empresa=empresa_a, pipeline=pipe, nombre="Nuevo", orden=1)
    ganadora = _ingesta(bot_usuario, kind=IngestaBot.Kind.CONTACTO, key="k-carrera")
    real_filter = IngestaBot.objects.filter
    llamadas = {"n": 0}

    def filtro(*args, **kwargs):
        llamadas["n"] += 1
        # La comprobación previa de idempotencia aún no ve a la ganadora; la posterior sí.
        return real_filter(pk__in=[]) if llamadas["n"] == 1 else real_filter(*args, **kwargs)

    with (
        patch.object(IngestaBot.objects, "filter", side_effect=filtro),
        patch.object(IngestaBot.objects, "create", side_effect=IntegrityError("duplicada")),
    ):
        ing, creada = _ingerir(servicio, "k-carrera")

    assert ing.pk == ganadora.pk
    assert creada is False


def test_un_conflicto_que_no_es_de_idempotencia_no_se_enmascara(servicio, bot_usuario, empresa_a):
    """Si tras el IntegrityError no existe ninguna ingesta con esa clave, el error real sube."""
    pipe = Pipeline.objects.create(id_empresa=empresa_a, nombre="Ventas", es_predeterminado=True)
    Etapa.objects.create(id_empresa=empresa_a, pipeline=pipe, nombre="Nuevo", orden=1)
    with patch.object(IngestaBot.objects, "create", side_effect=IntegrityError("otra restriccion")):
        with pytest.raises(IntegrityError):
            _ingerir(servicio, "k-inexistente")


# ── Usuarios de Telegram (administración) ────────────────────────────────────


@pytest.fixture
def api_staff(user_a):
    user_a.is_staff = True
    user_a.save()
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


def test_alta_de_un_usuario_de_telegram(api_staff, user_a, empresa_a):
    r = api_staff.post(
        USUARIOS,
        {"telegram_user_id": 777, "usuario": str(user_a.pk), "nombre": "Ana"},
        format="json",
    )
    assert r.status_code == 201, r.data
    assert BotUsuario.objects.get(telegram_user_id=777).id_empresa_id == empresa_a.pk


@pytest.mark.tenant
def test_la_api_no_acepta_vincular_un_usuario_de_otra_empresa(api_staff, empresa_b):
    """El campo `usuario` ya se acota a las empresas visibles: el ajeno ni siquiera existe."""
    ajeno = UsuariosFactory(username="ajeno_b", email="ajeno@beta.test", empresa=empresa_b)
    r = api_staff.post(
        USUARIOS, {"telegram_user_id": 888, "usuario": str(ajeno.pk)}, format="json"
    )
    assert r.status_code == 400
    assert "usuario" in r.data
    assert not BotUsuario.objects.filter(telegram_user_id=888).exists()


@pytest.mark.tenant
def test_la_vista_rechaza_por_si_misma_a_un_usuario_de_otra_empresa(user_a, empresa_b):
    """Segunda defensa: aunque el serializador dejara pasar al usuario, la vista lo bloquea."""
    from types import SimpleNamespace

    from rest_framework.exceptions import PermissionDenied

    from apps.bots_ingest.views import BotUsuarioViewSet

    ajeno = UsuariosFactory(username="ajeno_c", email="ajeno_c@beta.test", empresa=empresa_b)
    vista = BotUsuarioViewSet()
    vista.request = SimpleNamespace(user=user_a)
    serializer = SimpleNamespace(validated_data={"usuario": ajeno})
    with pytest.raises(PermissionDenied):
        vista.perform_create(serializer)


def test_borrar_un_usuario_de_telegram_es_borrado_logico(api_staff, user_a, empresa_a):
    bu = BotUsuario.objects.create(id_empresa=empresa_a, telegram_user_id=999, usuario=user_a)
    r = api_staff.delete(f"{USUARIOS}{bu.pk}/")
    assert r.status_code == 204
    bu.refresh_from_db()
    assert bu.activo is False


# ── Tareas Celery ────────────────────────────────────────────────────────────


def test_la_tarea_de_sync_envia_la_ingesta_a_odoo(bot_usuario):
    from apps.bots_ingest import tasks

    ing = _ingesta(
        bot_usuario, kind=IngestaBot.Kind.PEDIDO, estado=IngestaBot.Estado.BORRADOR, key="t1"
    )
    with patch("apps.bots_ingest.services.odoo_push.sincronizar") as sync:
        tasks.sincronizar_odoo_task(str(ing.pk))
    sync.assert_called_once()
    assert sync.call_args.args[0].pk == ing.pk


def test_la_tarea_de_sync_ignora_una_ingesta_que_ya_no_existe():
    import uuid

    from apps.bots_ingest import tasks

    with patch("apps.bots_ingest.services.odoo_push.sincronizar") as sync:
        tasks.sincronizar_odoo_task(str(uuid.uuid4()))
    sync.assert_not_called()


def test_encolar_sync_encola_con_el_id_como_texto():
    from apps.bots_ingest import tasks

    with patch.object(tasks.sincronizar_odoo_task, "delay") as delay:
        tasks.encolar_sync(42)
    delay.assert_called_once_with("42")


def test_encolar_sync_no_propaga_un_broker_caido():
    from apps.bots_ingest import tasks

    with patch.object(
        tasks.sincronizar_odoo_task, "delay", side_effect=ConnectionError("broker")
    ) as delay:
        tasks.encolar_sync("ing-1")  # la ingesta ya está confirmada: no debe fallar
    delay.assert_called_once_with("ing-1")
