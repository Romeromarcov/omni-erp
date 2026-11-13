"""Activaciones: capacidad simultánea de recursos, API y aislamiento multi-tenant (R-CODE-1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.activaciones import services
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
        id_empresa=empresa_a,
        calendario=c,
        codigo="promotoras",
        nombre="Promotoras",
        capacidad=2,
    )
    RecursoActivacion.objects.create(
        id_empresa=empresa_a,
        calendario=c,
        codigo="igloos",
        nombre="Igloos",
        capacidad=3,
    )
    return c


def crear(empresa, cal, a, b, **usos):
    return services.crear_evento(
        empresa=empresa,
        calendario=cal,
        cliente_nombre="Bodega X",
        ubicacion="Av. 1",
        inicio=h(a),
        fin=h(b),
        usos=usos,
    )


def test_un_evento_con_todas_las_promotoras_bloquea_el_horario(empresa_a, cal):
    crear(empresa_a, cal, 0, 4, promotoras=2)
    with pytest.raises(services.CapacidadExcedida):
        crear(empresa_a, cal, 1, 3, promotoras=1)


def test_un_evento_con_una_promotora_permite_otro_solapado(empresa_a, cal):
    crear(empresa_a, cal, 0, 4, promotoras=1)
    crear(empresa_a, cal, 1, 3, promotoras=1)
    with pytest.raises(services.CapacidadExcedida):
        crear(empresa_a, cal, 2, 3, promotoras=1)


def test_igloos_se_controlan_por_separado(empresa_a, cal):
    crear(empresa_a, cal, 0, 4, igloos=2)
    crear(empresa_a, cal, 0, 4, igloos=1)
    with pytest.raises(services.CapacidadExcedida) as e:
        crear(empresa_a, cal, 0, 4, igloos=1)
    assert e.value.detalle["libres"] == 0


def test_eventos_no_coincidentes_entre_si_no_se_acumulan(empresa_a, cal):
    crear(empresa_a, cal, 0, 2, promotoras=1)
    crear(empresa_a, cal, 3, 5, promotoras=1)
    # El nuevo (1-4) toca a ambos, pero nunca coinciden entre sí: pico = 1 → cabe 1 más.
    crear(empresa_a, cal, 1, 4, promotoras=1)


def test_exceder_el_total_existente_se_rechaza_aun_sin_eventos(empresa_a, cal):
    with pytest.raises(services.CapacidadExcedida):
        crear(empresa_a, cal, 0, 1, promotoras=3)


def test_evento_cancelado_libera_capacidad(empresa_a, cal):
    ev = crear(empresa_a, cal, 0, 4, promotoras=2)
    services.cancelar_evento(ev)
    crear(empresa_a, cal, 0, 4, promotoras=2)


def test_horarios_contiguos_no_se_solapan(empresa_a, cal):
    crear(empresa_a, cal, 0, 2, promotoras=2)
    crear(empresa_a, cal, 2, 4, promotoras=2)


def test_fin_anterior_a_inicio_es_error(empresa_a, cal):
    with pytest.raises(services.ActivacionError):
        crear(empresa_a, cal, 3, 1, promotoras=1)


def test_recurso_inexistente_es_error(empresa_a, cal):
    with pytest.raises(services.ActivacionError):
        crear(empresa_a, cal, 0, 1, sillas=1)


# ── API ──────────────────────────────────────────────────────────────────────


def _payload(a, b, **usos):
    return {
        "cliente_nombre": "Bodega X",
        "ubicacion": "Av. 1",
        "inicio": h(a).isoformat(),
        "fin": h(b).isoformat(),
        "usos": usos,
        "materiales": ["toldo"],
    }


def test_api_crear_y_conflicto_409(client_a, cal):
    r = client_a.post(f"{BASE}/eventos/", _payload(0, 4, promotoras=2), format="json")
    assert r.status_code == 201, r.data
    assert r.data["usos"][0]["cantidad"] == 2
    r2 = client_a.post(f"{BASE}/eventos/", _payload(1, 2, promotoras=1), format="json")
    assert r2.status_code == 409
    assert "promotoras" in r2.data["error"].lower()


def test_api_disponibilidad(client_a, cal, empresa_a):
    crear(empresa_a, cal, 0, 4, promotoras=1, igloos=2)
    r = client_a.get(
        f"{BASE}/calendarios/{cal.id_calendario}/disponibilidad/",
        {"inicio": h(1).isoformat(), "fin": h(2).isoformat()},
    )
    assert r.status_code == 200
    por = {x["codigo"]: x for x in r.data}
    assert por["promotoras"]["libres"] == 1 and por["igloos"]["libres"] == 1


def test_api_cancelar(client_a, cal):
    ev = client_a.post(
        f"{BASE}/eventos/", _payload(0, 1, promotoras=1), format="json"
    ).data
    r = client_a.post(f"{BASE}/eventos/{ev['id_evento']}/cancelar/")
    assert r.status_code == 200 and r.data["estado"] == "CANCELADO"
    assert (
        client_a.post(f"{BASE}/eventos/{ev['id_evento']}/cancelar/").status_code == 400
    )


def test_api_configurar_capacidad_solo_staff(client_a, user_a, cal):
    rec = RecursoActivacion.objects.get(calendario=cal, codigo="promotoras")
    url = f"{BASE}/recursos/{rec.id_recurso}/"
    assert client_a.patch(url, {"capacidad": 5}, format="json").status_code == 403
    assert (
        client_a.get(url).status_code == 200
    )  # lectura abierta al usuario autenticado
    user_a.is_staff = True
    user_a.save()
    r = client_a.patch(url, {"capacidad": 5}, format="json")
    assert r.status_code == 200
    rec.refresh_from_db()
    assert rec.capacidad == 5


def test_sin_calendario_predeterminado_da_400(client_a):
    r = client_a.post(f"{BASE}/eventos/", _payload(0, 1), format="json")
    assert r.status_code == 400


# ── Aislamiento ─────────────────────────────────────────────────────────────


@pytest.mark.tenant
def test_no_ve_ni_usa_calendarios_ajenos(client_a, user_a, empresa_b):
    user_a.is_staff = True
    user_a.save()
    ajeno = CalendarioActivacion.objects.create(
        id_empresa=empresa_b, nombre="Ajeno", es_predeterminado=True
    )
    EventoActivacion.objects.create(
        id_empresa=empresa_b,
        calendario=ajeno,
        cliente_nombre="X",
        ubicacion="Y",
        inicio=h(0),
        fin=h(1),
    )
    assert client_a.get(f"{BASE}/calendarios/").data["results"] == []
    assert client_a.get(f"{BASE}/eventos/").data["results"] == []
    assert client_a.get(f"{BASE}/calendarios/{ajeno.id_calendario}/").status_code == 404
    r = client_a.post(
        f"{BASE}/eventos/",
        {**_payload(0, 1), "calendario": str(ajeno.id_calendario)},
        format="json",
    )
    assert r.status_code == 404
    rr = client_a.post(
        f"{BASE}/recursos/",
        {
            "calendario": str(ajeno.id_calendario),
            "codigo": "p",
            "nombre": "P",
            "capacidad": 1,
        },
        format="json",
    )
    assert rr.status_code in (400, 403)


# ── Sincronización con Google Calendar ──────────────────────────────────────


def test_crear_y_cancelar_encolan_la_sync(
    empresa_a, cal, django_capture_on_commit_callbacks
):
    from unittest.mock import patch

    with patch("apps.activaciones.services.encolar_sync") as encolar:
        with django_capture_on_commit_callbacks(execute=True):
            ev = crear(empresa_a, cal, 0, 1, promotoras=1)
        with django_capture_on_commit_callbacks(execute=True):
            services.cancelar_evento(ev)
    assert encolar.call_count == 2


def test_sync_guarda_id_de_google_y_registra_fallos(empresa_a, cal):
    from unittest.mock import patch

    cal.google_calendar_id = "abc@group.calendar.google.com"
    cal.save()
    ev = crear(empresa_a, cal, 0, 1, promotoras=1)
    with patch("apps.activaciones.google_calendar.configurado", return_value=True):
        with patch("apps.activaciones.google_calendar.upsert", return_value="gid-1"):
            services.sincronizar_google(ev.pk)
        ev.refresh_from_db()
        assert ev.google_event_id == "gid-1" and ev.sync_error == ""
        with patch(
            "apps.activaciones.google_calendar.upsert", side_effect=RuntimeError("boom")
        ):
            services.sincronizar_google(ev.pk)  # nunca lanza
        ev.refresh_from_db()
        assert (
            ev.sync_error and "boom" not in ev.sync_error
        )  # sin filtrar detalles internos


def test_sync_sin_credenciales_se_omite(empresa_a, cal):
    cal.google_calendar_id = "abc@group.calendar.google.com"
    cal.save()
    ev = crear(empresa_a, cal, 0, 1, promotoras=1)
    services.sincronizar_google(ev.pk)
    ev.refresh_from_db()
    assert ev.google_event_id == "" and ev.sync_error == ""
