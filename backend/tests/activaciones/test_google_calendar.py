"""Cliente de Google Calendar: cuerpo del evento, alta/edición/borrado y credenciales.

Nunca se llama a Google: se sustituyen ``requests`` y la autenticación de la cuenta de servicio.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from apps.activaciones import google_calendar, services
from apps.activaciones.models import CalendarioActivacion, RecursoActivacion

pytestmark = [pytest.mark.django_db]

T0 = datetime(2026, 12, 1, 8, 0, tzinfo=timezone.utc)
CAL_ID = "abc@group.calendar.google.com"


@pytest.fixture
def evento(empresa_a):
    cal = CalendarioActivacion.objects.create(
        id_empresa=empresa_a,
        nombre="Activaciones",
        es_predeterminado=True,
        google_calendar_id=CAL_ID,
        zona_horaria="America/Caracas",
    )
    RecursoActivacion.objects.create(
        id_empresa=empresa_a, calendario=cal, codigo="promotoras", nombre="Promotoras", capacidad=3
    )
    return services.crear_evento(
        empresa=empresa_a,
        calendario=cal,
        cliente_nombre="Bodega X",
        vendedor_nombre="Ana",
        ubicacion="Av. 1",
        inicio=T0,
        fin=T0 + timedelta(hours=2),
        usos={"promotoras": 2},
        materiales=["toldo", "mesa"],
        notas="Llegar temprano",
    )


def _respuesta(json=None, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json or {}
    return r


# ── Configuración y credenciales ─────────────────────────────────────────────


def test_configurado_depende_de_la_variable_de_entorno(monkeypatch):
    monkeypatch.delenv("GOOGLE_CALENDAR_SA_JSON", raising=False)
    assert google_calendar.configurado() is False
    monkeypatch.setenv("GOOGLE_CALENDAR_SA_JSON", "{}")
    assert google_calendar.configurado() is True


def test_los_encabezados_llevan_el_token_de_la_cuenta_de_servicio(monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_SA_JSON", '{"type": "service_account"}')
    creds = MagicMock(token="tok-123")
    with (
        patch(
            "google.oauth2.service_account.Credentials.from_service_account_info",
            return_value=creds,
        ) as desde_info,
        patch("google.auth.transport.requests.Request"),
    ):
        headers = google_calendar._headers()
    assert headers == {"Authorization": "Bearer tok-123"}
    creds.refresh.assert_called_once()
    assert desde_info.call_args.kwargs["scopes"] == google_calendar._SCOPE


# ── Cuerpo del evento ────────────────────────────────────────────────────────


def test_el_cuerpo_del_evento_resume_vendedor_materiales_recursos_y_notas(evento):
    cuerpo = google_calendar._cuerpo(evento)
    assert cuerpo["summary"] == "Activación Bodega X"
    assert cuerpo["location"] == "Av. 1"
    for fragmento in ("Vendedor: Ana", "Llevar: toldo, mesa", "Recursos: Promotoras: 2", "Llegar temprano"):
        assert fragmento in cuerpo["description"]
    assert cuerpo["start"]["timeZone"] == "America/Caracas"
    assert cuerpo["start"]["dateTime"] == evento.inicio.isoformat()
    assert cuerpo["end"]["dateTime"] == evento.fin.isoformat()


def test_el_cuerpo_omite_las_lineas_vacias(evento):
    evento.vendedor_nombre, evento.materiales, evento.notas = "", [], ""
    evento.usos.all().delete()
    assert google_calendar._cuerpo(evento)["description"] == ""


# ── Alta, edición y borrado ──────────────────────────────────────────────────


def test_un_evento_nuevo_se_crea_con_post_y_devuelve_el_id_de_google(evento):
    evento.google_event_id = ""
    with (
        patch.object(google_calendar, "_headers", return_value={"Authorization": "Bearer x"}),
        patch.object(google_calendar.requests, "post", return_value=_respuesta({"id": "gid-1"})) as post,
        patch.object(google_calendar.requests, "put") as put,
    ):
        assert google_calendar.upsert(evento) == "gid-1"
    put.assert_not_called()
    assert post.call_args.args[0].endswith(f"/{CAL_ID}/events")
    assert post.call_args.kwargs["json"]["summary"] == "Activación Bodega X"


def test_un_evento_ya_sincronizado_se_actualiza_con_put(evento):
    evento.google_event_id = "gid-7"
    with (
        patch.object(google_calendar, "_headers", return_value={}),
        patch.object(google_calendar.requests, "put", return_value=_respuesta({"id": "gid-7"})) as put,
        patch.object(google_calendar.requests, "post") as post,
    ):
        assert google_calendar.upsert(evento) == "gid-7"
    post.assert_not_called()
    assert put.call_args.args[0].endswith(f"/{CAL_ID}/events/gid-7")


def test_un_error_http_al_guardar_se_propaga(evento):
    evento.google_event_id = ""
    fallo = _respuesta({"id": "x"}, status=500)
    fallo.raise_for_status.side_effect = RuntimeError("500")
    with (
        patch.object(google_calendar, "_headers", return_value={}),
        patch.object(google_calendar.requests, "post", return_value=fallo),
    ):
        with pytest.raises(RuntimeError):
            google_calendar.upsert(evento)  # el servicio lo captura y lo guarda en sync_error


@pytest.mark.parametrize("estado", [200, 204, 404, 410])
def test_borrar_acepta_los_estados_que_significan_ya_borrado(evento, estado):
    evento.google_event_id = "gid-9"
    r = _respuesta(status=estado)
    with (
        patch.object(google_calendar, "_headers", return_value={}),
        patch.object(google_calendar.requests, "delete", return_value=r) as delete,
    ):
        google_calendar.borrar(evento)
    assert delete.call_args.args[0].endswith(f"/{CAL_ID}/events/gid-9")
    r.raise_for_status.assert_not_called()


def test_borrar_propaga_un_error_real_de_google(evento):
    evento.google_event_id = "gid-9"
    r = _respuesta(status=500)
    r.raise_for_status.side_effect = RuntimeError("500")
    with (
        patch.object(google_calendar, "_headers", return_value={}),
        patch.object(google_calendar.requests, "delete", return_value=r),
    ):
        with pytest.raises(RuntimeError):
            google_calendar.borrar(evento)
