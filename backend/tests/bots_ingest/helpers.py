"""Utilidades compartidas de los tests de ``bots_ingest`` (envío de borradores y borradores de ejemplo)."""

from __future__ import annotations

URL = "/api/bots/ingest/"
TG = 111222333
UBIC = {"latitud": 10.4806, "longitud": -66.9036, "precision_m": 12.5}


def enviar(api, kind, draft, key="k1", tg=TG, **fuente):
    """POST de un borrador confirmado, como lo haría un bot."""
    return api.post(
        URL,
        {
            "kind": kind,
            "draft": draft,
            "source": {"telegram_user_id": tg, **fuente},
            "idempotency_key": key,
        },
        format="json",
    )


def pedido_draft(**kw):
    """Borrador de pedido completo (cliente nuevo, entrega igual a la fiscal, 2 unidades de AC-20W50)."""
    base = {
        "cliente": "Taller Nuevo",
        "rif": "j-12345678-9",
        "email": "t@x.com",
        "telefono": "04141234567",
        "direccion_fiscal": "Av. Principal",
        "entrega_igual_fiscal": True,
        "ubicacion": UBIC,
        "lineas": [{"producto": "AC-20W50", "cantidad": "2"}],
    }
    base.update(kw)
    return base
