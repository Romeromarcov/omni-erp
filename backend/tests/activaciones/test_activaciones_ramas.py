"""Activaciones: ramas de borde de modelos, servicios, serializadores, vistas y tareas.

Complementa ``test_activaciones.py`` (capacidad, API feliz y aislamiento) con los caminos de
error y de configuración que ese archivo no ejercita.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from rest_framework.test import APIClient

from apps.activaciones import services, tasks
from apps.activaciones.models import (
    CalendarioActivacion,
    EventoActivacion,
    RecursoActivacion,
)

pytestmark = [pytest.mark.django_db]

BASE = "/api/activaciones"
T0 = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)


def h(n: int) -> datetime:
    return T0 + timedelta(hours=n)


@pytest.fixture
def cal(empresa_a):
    c = CalendarioActivacion.objects.create(
        id_empresa=empresa_a, nombre="Activaciones", es_predeterminado=True
    )
    RecursoActivacion.objects.create(
        id_empresa=empresa_a, calendario=c, codigo="promotoras", nombre="Promotoras", capacidad=2
    )
    return c


@pytest.fixture
def staff(user_a):
    user_a.is_staff = True
    user_a.save()
    return user_a


@pytest.fixture
def api_staff(staff):
    c = APIClient()
    c.force_authenticate(user=staff)
    return c


def _evento(empresa, cal, a=0, b=2, **usos):
    return services.crear_evento(
        empresa=empresa,
        calendario=cal,
        cliente_nombre="Bodega X",
        ubicacion="Av. 1",
        inicio=h(a),
        fin=h(b),
        usos=usos,
    )


def _payload(a, b, **usos):
    return {
        "cliente_nombre": "Bodega X",
        "vendedor_nombre": "Ana",
        "ubicacion": "Av. 1",
        "inicio": h(a).isoformat(),
        "fin": h(b).isoformat(),
        "usos": usos,
    }


# ── Modelos ──────────────────────────────────────────────────────────────────


def test_representaciones_de_texto(empresa_a, cal):
    rec = cal.recursos.get(codigo="promotoras")
    ev = _evento(empresa_a, cal)
    assert str(cal) == "Activaciones"
    assert str(rec) == "Promotoras (2)"
    assert "Bodega X" in str(ev) and "2026-12-01 08:00" in str(ev)


# ── Servicios ────────────────────────────────────────────────────────────────


def test_disponibilidad_puede_excluir_un_evento(empresa_a, cal):
    """Al editar un evento su propio uso no debe contarse contra la capacidad."""
    ev = _evento(empresa_a, cal, 0, 4, promotoras=2)
    con = {d.codigo: d for d in services.disponibilidad(cal, h(0), h(4))}
    sin = {
        d.codigo: d for d in services.disponibilidad(cal, h(0), h(4), excluir_evento=ev)
    }
    assert con["promotoras"].libres == 0
    assert sin["promotoras"].libres == 2


def test_un_uso_con_cantidad_cero_se_ignora(empresa_a, cal):
    """Cantidad <= 0 no consume ni valida el recurso (ni siquiera uno inexistente)."""
    services.verificar_capacidad(cal, h(0), h(1), {"promotoras": 0, "fantasma": 0})


def test_sync_de_un_evento_cancelado_borra_en_google(empresa_a, cal):
    cal.google_calendar_id = "abc@group.calendar.google.com"
    cal.save()
    ev = _evento(empresa_a, cal, promotoras=1)
    ev.estado = EventoActivacion.Estado.CANCELADO
    ev.google_event_id = "gid-9"
    ev.save()
    with (
        patch("apps.activaciones.google_calendar.configurado", return_value=True),
        patch("apps.activaciones.google_calendar.borrar") as borrar,
        patch("apps.activaciones.google_calendar.upsert") as upsert,
    ):
        services.sincronizar_google(ev.pk)
    borrar.assert_called_once()
    upsert.assert_not_called()


def test_sync_de_un_cancelado_sin_id_de_google_no_llama_a_google(empresa_a, cal):
    cal.google_calendar_id = "abc@group.calendar.google.com"
    cal.save()
    ev = _evento(empresa_a, cal, promotoras=1)
    ev.estado = EventoActivacion.Estado.CANCELADO
    ev.save()
    with (
        patch("apps.activaciones.google_calendar.configurado", return_value=True),
        patch("apps.activaciones.google_calendar.borrar") as borrar,
    ):
        services.sincronizar_google(ev.pk)
    borrar.assert_not_called()


# ── Tareas Celery ────────────────────────────────────────────────────────────


def test_la_tarea_delega_en_el_servicio():
    with patch("apps.activaciones.services.sincronizar_google") as sync:
        tasks.sincronizar_google_task("evt-1")
    sync.assert_called_once_with("evt-1")


def test_encolar_sync_encola_con_el_id_como_texto():
    with patch.object(tasks.sincronizar_google_task, "delay") as delay:
        tasks.encolar_sync(123)
    delay.assert_called_once_with("123")


def test_encolar_sync_no_propaga_un_broker_caido():
    with patch.object(
        tasks.sincronizar_google_task, "delay", side_effect=ConnectionError("broker")
    ) as delay:
        tasks.encolar_sync("evt-2")  # no lanza: el evento ya está guardado
    delay.assert_called_once_with("evt-2")


# ── Serializadores (vía API, como staff) ─────────────────────────────────────


def test_calendario_con_nombre_repetido_da_400(api_staff, cal):
    r = api_staff.post(f"{BASE}/calendarios/", {"nombre": "Activaciones"}, format="json")
    assert r.status_code == 400
    assert "nombre" in r.data


def test_un_nuevo_predeterminado_reemplaza_al_anterior(api_staff, cal):
    r = api_staff.post(
        f"{BASE}/calendarios/",
        {"nombre": "Eventos 2027", "es_predeterminado": True},
        format="json",
    )
    assert r.status_code == 201, r.data
    cal.refresh_from_db()
    assert cal.es_predeterminado is False
    nuevo = CalendarioActivacion.objects.get(nombre="Eventos 2027")
    assert nuevo.es_predeterminado is True


def test_editar_el_calendario_no_choca_consigo_mismo(api_staff, cal):
    r = api_staff.patch(
        f"{BASE}/calendarios/{cal.id_calendario}/", {"zona_horaria": "America/Caracas"}, format="json"
    )
    assert r.status_code == 200, r.data


def test_recurso_con_codigo_repetido_en_el_calendario_da_400(api_staff, cal):
    r = api_staff.post(
        f"{BASE}/recursos/",
        {"calendario": str(cal.id_calendario), "codigo": "promotoras", "nombre": "Otra", "capacidad": 1},
        format="json",
    )
    assert r.status_code == 400
    assert "codigo" in r.data


# ── Vistas ───────────────────────────────────────────────────────────────────


def test_borrar_un_calendario_es_borrado_logico(api_staff, cal):
    r = api_staff.delete(f"{BASE}/calendarios/{cal.id_calendario}/")
    assert r.status_code == 204
    cal.refresh_from_db()
    assert cal.activo is False


def test_borrar_un_recurso_es_borrado_logico(api_staff, cal):
    rec = cal.recursos.get(codigo="promotoras")
    r = api_staff.delete(f"{BASE}/recursos/{rec.id_recurso}/")
    assert r.status_code == 204
    rec.refresh_from_db()
    assert rec.activo is False


@pytest.mark.parametrize(
    "params",
    [{}, {"inicio": "no-es-fecha", "fin": "tampoco"}, {"inicio": h(2).isoformat(), "fin": h(1).isoformat()}],
)
def test_disponibilidad_con_parametros_invalidos_da_400(api_staff, cal, params):
    r = api_staff.get(f"{BASE}/calendarios/{cal.id_calendario}/disponibilidad/", params)
    assert r.status_code == 400
    assert "error" in r.data


@pytest.mark.tenant
def test_no_se_puede_crear_un_recurso_en_el_calendario_de_otra_empresa(api_staff, empresa_b):
    ajeno = CalendarioActivacion.objects.create(
        id_empresa=empresa_b, nombre="Ajeno", es_predeterminado=True
    )
    r = api_staff.post(
        f"{BASE}/recursos/",
        {"calendario": str(ajeno.id_calendario), "codigo": "p", "nombre": "P", "capacidad": 1},
        format="json",
    )
    assert r.status_code in (400, 403, 404)
    assert not RecursoActivacion.objects.filter(calendario=ajeno).exists()


def test_el_listado_de_eventos_filtra_por_estado_y_por_rango(client_a, empresa_a, cal):
    prog = _evento(empresa_a, cal, 0, 2, promotoras=1)
    canc = _evento(empresa_a, cal, 10, 12, promotoras=1)
    services.cancelar_evento(canc)

    def ids(**params):
        return {x["id_evento"] for x in client_a.get(f"{BASE}/eventos/", params).data["results"]}

    assert ids(estado="PROGRAMADO") == {str(prog.pk)}
    assert ids(estado="CANCELADO") == {str(canc.pk)}
    # `desde` descarta eventos que terminan antes; `hasta`, los que empiezan después.
    assert ids(desde=h(5).isoformat()) == {str(canc.pk)}
    assert ids(hasta=h(5).isoformat()) == {str(prog.pk)}


def test_un_usuario_sin_empresa_no_puede_crear_eventos(cal):
    from tests.factories import UsuariosFactory

    huerfano = UsuariosFactory(username="sin_empresa", email="sin@empresa.test")
    c = APIClient()
    c.force_authenticate(user=huerfano)
    r = c.post(f"{BASE}/eventos/", _payload(0, 1, promotoras=1), format="json")
    assert r.status_code == 403


def test_crear_un_evento_con_un_recurso_inexistente_da_400(client_a, cal):
    r = client_a.post(f"{BASE}/eventos/", _payload(0, 1, fantasma=1), format="json")
    assert r.status_code == 400
    assert "fantasma" in r.data["error"]


# ── Alta de recursos y calendarios predeterminados ───────────────────────────


def test_staff_crea_un_recurso_en_su_calendario(api_staff, cal, empresa_a):
    r = api_staff.post(
        f"{BASE}/recursos/",
        {"calendario": str(cal.id_calendario), "codigo": "igloos", "nombre": "Igloos", "capacidad": 3},
        format="json",
    )
    assert r.status_code == 201, r.data
    recurso = RecursoActivacion.objects.get(calendario=cal, codigo="igloos")
    assert recurso.id_empresa_id == empresa_a.pk  # la empresa sale del calendario, no del cliente


@pytest.mark.tenant
def test_la_vista_de_recursos_bloquea_por_si_misma_un_calendario_ajeno(user_a, empresa_b):
    """Segunda defensa: aunque el serializador dejara pasar el calendario, la vista lo bloquea."""
    from types import SimpleNamespace

    from rest_framework.exceptions import PermissionDenied

    from apps.activaciones.views import RecursoActivacionViewSet

    ajeno = CalendarioActivacion.objects.create(id_empresa=empresa_b, nombre="Ajeno")
    vista = RecursoActivacionViewSet()
    vista.request = SimpleNamespace(user=user_a)
    with pytest.raises(PermissionDenied):
        vista.perform_create(SimpleNamespace(validated_data={"calendario": ajeno}))


def test_marcar_como_predeterminado_un_calendario_existente_desplaza_al_anterior(
    api_staff, cal, empresa_a
):
    otro = CalendarioActivacion.objects.create(id_empresa=empresa_a, nombre="Segundo")
    r = api_staff.patch(
        f"{BASE}/calendarios/{otro.id_calendario}/", {"es_predeterminado": True}, format="json"
    )
    assert r.status_code == 200, r.data
    cal.refresh_from_db()
    otro.refresh_from_db()
    assert cal.es_predeterminado is False
    assert otro.es_predeterminado is True
