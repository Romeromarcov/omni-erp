"""Cliente mínimo de Google Calendar (REST + cuenta de servicio). Credenciales por entorno (R-CODE-8).

``GOOGLE_CALENDAR_SA_JSON``: JSON de la cuenta de servicio. El calendario debe estar compartido con
su correo con permiso de edición. Si falta, la sincronización se omite silenciosamente.
"""

from __future__ import annotations

import json
import os

import requests

_SCOPE = ["https://www.googleapis.com/auth/calendar"]
_BASE = "https://www.googleapis.com/calendar/v3/calendars"
_TIMEOUT = 15


def configurado() -> bool:
    return bool(os.environ.get("GOOGLE_CALENDAR_SA_JSON"))


def _headers() -> dict:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_CALENDAR_SA_JSON"]), scopes=_SCOPE
    )
    creds.refresh(Request())
    return {"Authorization": f"Bearer {creds.token}"}


def _cuerpo(evento) -> dict:
    tz = evento.calendario.zona_horaria
    usos = ", ".join(f"{u.recurso.nombre}: {u.cantidad}" for u in evento.usos.all())
    lineas = [
        f"Vendedor: {evento.vendedor_nombre}" if evento.vendedor_nombre else "",
        "Llevar: " + ", ".join(evento.materiales) if evento.materiales else "",
        f"Recursos: {usos}" if usos else "",
        evento.notas,
    ]
    return {
        "summary": f"Activación {evento.cliente_nombre}",
        "location": evento.ubicacion,
        "description": "\n".join(x for x in lineas if x),
        "start": {"dateTime": evento.inicio.isoformat(), "timeZone": tz},
        "end": {"dateTime": evento.fin.isoformat(), "timeZone": tz},
    }


def upsert(evento) -> str:
    cal, h = evento.calendario.google_calendar_id, _headers()
    if evento.google_event_id:
        r = requests.put(
            f"{_BASE}/{cal}/events/{evento.google_event_id}",
            json=_cuerpo(evento),
            headers=h,
            timeout=_TIMEOUT,
        )
    else:
        r = requests.post(
            f"{_BASE}/{cal}/events", json=_cuerpo(evento), headers=h, timeout=_TIMEOUT
        )
    r.raise_for_status()
    return r.json()["id"]


def borrar(evento) -> None:
    r = requests.delete(
        f"{_BASE}/{evento.calendario.google_calendar_id}/events/{evento.google_event_id}",
        headers=_headers(),
        timeout=_TIMEOUT,
    )
    if r.status_code not in (200, 204, 404, 410):
        r.raise_for_status()
