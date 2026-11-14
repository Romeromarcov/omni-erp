"""Ingesta desde bots: contactos/CRM, cotización, pedido, pagos, eventos, idempotencia y aislamiento."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from apps.activaciones.models import (
    CalendarioActivacion,
    EventoActivacion,
    RecursoActivacion,
)
from apps.bots_ingest.models import BotUsuario, IngestaBot
from apps.core.models import Contacto
from apps.crm.models import Cliente, DireccionCliente, Etapa, Lead, Pipeline
from apps.ventas.models import Cotizacion, DetallePrecio, ListaPrecio, Pedido
from tests.factories.comercial import ProductoFactory

pytestmark = [pytest.mark.django_db]

URL = "/api/bots/ingest/"
TG = 111222333
UBIC = {"latitud": 10.4806, "longitud": -66.9036, "precision_m": 12.5}


@pytest.fixture
def servicio(user_a):
    user_a.user_permissions.add(
        Permission.objects.get(
            codename="ingestar", content_type__app_label="bots_ingest"
        )
    )
    return user_a


@pytest.fixture
def api(servicio):
    c = APIClient()
    c.force_authenticate(user=servicio)
    return c


@pytest.fixture
def bot_usuario(servicio, empresa_a):
    return BotUsuario.objects.create(
        id_empresa=empresa_a, telegram_user_id=TG, usuario=servicio, nombre="Vendedor"
    )


def enviar(api, kind, draft, key="k1", tg=TG, **fuente):
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


# ── autorización ─────────────────────────────────────────────────────────────


def test_requiere_permiso_de_ingesta(bot_usuario, empresa_a):
    from tests.factories.core import UsuariosFactory

    sin_permiso = APIClient()
    sin_permiso.force_authenticate(user=UsuariosFactory(empresa=empresa_a))
    r = enviar(sin_permiso, "contacto", {"nombre": "A"})
    assert r.status_code == 403


def test_telegram_desconocido_es_403(api, bot_usuario):
    assert enviar(api, "contacto", {"nombre": "A"}, tg=999).status_code == 403


# ── contacto / CRM ───────────────────────────────────────────────────────────


def test_contacto_exige_nombre_telefono_y_ubicacion(api, bot_usuario):
    r = enviar(api, "contacto", {"nombre": "Pedro", "telefono": "0414-1234567"})
    assert r.status_code == 422 and "ubicacion" in r.data["faltan"]
    assert Contacto.objects.count() == 0 and IngestaBot.objects.count() == 0


def test_contacto_crea_contacto_con_gps_y_lead(api, bot_usuario, empresa_a):
    p = Pipeline.objects.create(
        id_empresa=empresa_a, nombre="Ventas", es_predeterminado=True
    )
    Etapa.objects.create(id_empresa=empresa_a, pipeline=p, nombre="Nuevo", orden=1)
    r = enviar(
        api,
        "contacto",
        {
            "nombre": "Pedro",
            "telefono": "0414-1234567",
            "ubicacion": UBIC,
            "email": "p@x.com",
        },
    )
    assert r.status_code == 201, r.data
    c = Contacto.objects.get(id_empresa=empresa_a, nombre="Pedro")
    assert (
        c.latitud == Decimal("10.480600")
        and c.longitud == Decimal("-66.903600")
        and c.email == "p@x.com"
    )
    assert Lead.objects.filter(contacto=c).count() == 1
    assert r.data["estado"] == "PROCESADO"


def test_contacto_no_duplica_por_telefono(api, bot_usuario, empresa_a):
    enviar(
        api,
        "contacto",
        {"nombre": "Pedro", "telefono": "0414-1234567", "ubicacion": UBIC},
        key="a",
    )
    enviar(
        api,
        "contacto",
        {"nombre": "Pedro", "telefono": "04141234567", "ubicacion": UBIC},
        key="b",
    )
    assert Contacto.objects.filter(id_empresa=empresa_a).count() == 1


def test_gps_fuera_de_rango_es_rechazado(api, bot_usuario):
    r = enviar(
        api,
        "contacto",
        {
            "nombre": "P",
            "telefono": "04141234567",
            "ubicacion": {"latitud": 99, "longitud": 0},
        },
    )
    assert r.status_code == 422


def test_idempotencia_misma_clave_no_duplica(api, bot_usuario, empresa_a):
    d = {"nombre": "Pedro", "telefono": "04141234567", "ubicacion": UBIC}
    r1, r2 = (
        enviar(api, "contacto", d, key="same"),
        enviar(api, "contacto", d, key="same"),
    )
    assert r1.status_code == 201 and r2.status_code == 200
    assert r1.data["id_ingesta"] == r2.data["id_ingesta"]
    assert IngestaBot.objects.filter(id_empresa=empresa_a).count() == 1


# ── cotización y pedido ──────────────────────────────────────────────────────


@pytest.fixture
def catalogo(empresa_a, moneda_usd):
    lista = ListaPrecio.objects.create(
        id_empresa=empresa_a,
        nombre="Lista 1",
        codigo="L1",
        es_referencia=True,
        id_moneda=moneda_usd,
    )
    prod = ProductoFactory(
        id_empresa=empresa_a, nombre_producto="Aceite 20W50", sku="AC-20W50"
    )
    DetallePrecio.objects.create(
        id_lista=lista, id_producto=prod, precio=Decimal("12.50")
    )
    return lista, prod


def test_cotizacion_solo_con_nombre_crea_cliente_provisional(
    api, bot_usuario, catalogo, empresa_a
):
    r = enviar(
        api,
        "cotizacion",
        {
            "cliente": "Taller Nuevo",
            "lineas": [{"producto": "aceite 20w50", "cantidad": "4"}],
        },
    )
    assert r.status_code == 201, r.data
    cot = Cotizacion.objects.get(id_empresa=empresa_a)
    assert cot.monto_total == Decimal("50.0000") and cot.estado == "BORRADOR"
    assert (
        cot.id_cliente.rif.startswith("PEND-")
        and r.data["resultado"]["cliente_provisional"] is True
    )


def test_cotizacion_producto_desconocido_se_rechaza(api, bot_usuario, catalogo):
    r = enviar(
        api,
        "cotizacion",
        {
            "cliente": "X",
            "lineas": [{"producto": "Grasa inexistente", "cantidad": "1"}],
        },
    )
    assert r.status_code == 422 and "no encontrado" in r.data["error"]


def _pedido(**kw):
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


def test_pedido_completa_ficha_y_guarda_gps(api, bot_usuario, catalogo, empresa_a):
    enviar(
        api,
        "cotizacion",
        {
            "cliente": "Taller Nuevo",
            "lineas": [{"producto": "AC-20W50", "cantidad": "1"}],
        },
        key="c",
    )
    r = enviar(api, "pedido", _pedido(), key="p")
    assert r.status_code == 201, r.data
    cliente = Cliente.objects.get(
        id_empresa=empresa_a, razon_social="Taller Nuevo"
    )  # el provisional se reutiliza
    assert cliente.rif == "J-123456789" and cliente.email == "t@x.com"
    assert (cliente.documento_json or {}).get("provisional") is False
    d = DireccionCliente.objects.get(id_cliente=cliente, tipo_direccion="FISCAL")
    assert d.latitud == Decimal("10.480600")
    ped = Pedido.objects.get(id_empresa=empresa_a)
    assert ped.estado == "PENDIENTE" and ped.id_vendedor_id == bot_usuario.usuario_id
    assert ped.detalles.get().subtotal == Decimal("25.0000")


def test_pedido_con_direccion_de_entrega_distinta(
    api, bot_usuario, catalogo, empresa_a
):
    r = enviar(
        api, "pedido", _pedido(entrega_igual_fiscal=False, direccion_entrega="Galpón 3")
    )
    assert r.status_code == 201, r.data
    ent = DireccionCliente.objects.get(tipo_direccion="ENTREGA")
    assert ent.direccion_completa == "Galpón 3" and ent.latitud is not None
    assert DireccionCliente.objects.get(tipo_direccion="FISCAL").latitud is None


@pytest.mark.parametrize("quitar", ["rif", "email", "direccion_fiscal", "ubicacion"])
def test_pedido_exige_ficha_completa(api, bot_usuario, catalogo, quitar):
    d = _pedido()
    d.pop(quitar)
    r = enviar(api, "pedido", d)
    assert r.status_code == 422 and quitar in r.data["faltan"]
    assert Pedido.objects.count() == 0


def test_pedido_exige_direccion_de_entrega(api, bot_usuario, catalogo):
    r = enviar(api, "pedido", _pedido(entrega_igual_fiscal=None))
    assert r.status_code == 422 and "direccion_entrega" in r.data["faltan"]


def test_pedido_rif_invalido(api, bot_usuario, catalogo):
    assert enviar(api, "pedido", _pedido(rif="ABC")).status_code == 422


def test_pedido_con_rif_existente_reutiliza_ese_cliente(
    api, bot_usuario, catalogo, empresa_a
):
    existente = Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Otro S.A.", rif="J-123456789"
    )
    r = enviar(api, "pedido", _pedido(cliente="Taller Nuevo"))
    assert r.status_code == 201, r.data
    assert (
        Cliente.objects.filter(id_empresa=empresa_a).count() == 1
    )  # el RIF identifica al cliente
    assert Pedido.objects.get().id_cliente_id == existente.id_cliente


# ── pagos ────────────────────────────────────────────────────────────────────


def test_pago_identificado_por_rif(api, bot_usuario, empresa_a):
    c = Cliente.objects.create(
        id_empresa=empresa_a, razon_social="Taller", rif="J-123456789"
    )
    r = enviar(
        api,
        "pago",
        {"rif": "J-12345678-9", "monto": "100", "moneda": "USD", "referencia": "R1"},
    )
    assert r.status_code == 201 and r.data["estado"] == "BORRADOR"
    assert r.data["resultado"]["cliente_id"] == str(c.id_cliente)


def test_pago_identificado_por_pedido(api, bot_usuario, catalogo, empresa_a):
    enviar(api, "pedido", _pedido(), key="p")
    num = Pedido.objects.get().numero_pedido
    r = enviar(
        api,
        "pago",
        {"pedido_ref": num, "monto": "25", "moneda": "USD", "referencia": "R2"},
    )
    assert r.data["estado"] == "BORRADOR" and "pedido_id" in r.data["resultado"]


def test_pago_incompleto_se_registra_y_se_completa_despues(api, bot_usuario):
    r = enviar(
        api, "pago", {"cliente": "Alguien", "monto": "50", "moneda": "USD"}, auto=True
    )
    assert (
        r.status_code == 201
        and r.data["estado"] == "INCOMPLETO"
        and "referencia" in r.data["incompleto"]
    )
    assert r.data["auto"] is True
    r2 = api.post(
        f"{URL}{r.data['id_ingesta']}/completar/",
        {"cambios": {"referencia": "ABC123"}},
        format="json",
    )
    assert (
        r2.status_code == 200
        and r2.data["estado"] == "BORRADOR"
        and r2.data["incompleto"] == []
    )
    assert r2.data["payload"]["referencia"] == "ABC123"


def test_pago_sin_identificacion_queda_incompleto(api, bot_usuario):
    r = enviar(api, "pago", {"monto": "50", "moneda": "USD", "referencia": "R"})
    assert any("cliente" in x for x in r.data["incompleto"])


def test_monto_no_positivo_se_rechaza(api, bot_usuario):
    assert (
        enviar(
            api,
            "pago",
            {"cliente": "A", "monto": "-5", "moneda": "USD", "referencia": "R"},
        ).status_code
        == 422
    )


def test_pago_proveedor_incompleto_y_listado(api, bot_usuario):
    r = enviar(api, "pago_proveedor", {"proveedor": "Lubricantes SA", "monto": "900"})
    assert r.data["estado"] == "INCOMPLETO" and "moneda" in r.data["incompleto"]
    lst = api.get(URL, {"estado": "INCOMPLETO"})
    assert lst.status_code == 200 and len(lst.data["results"]) == 1


def test_no_se_completa_una_ingesta_que_no_es_pago(api, bot_usuario):
    r = enviar(
        api, "contacto", {"nombre": "P", "telefono": "04141234567", "ubicacion": UBIC}
    )
    assert (
        api.post(
            f"{URL}{r.data['id_ingesta']}/completar/",
            {"cambios": {"nombre": "Q"}},
            format="json",
        ).status_code
        == 422
    )


# ── eventos ──────────────────────────────────────────────────────────────────


@pytest.fixture
def calendario(empresa_a):
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


def _evento(**kw):
    base = {
        "cliente": "Bodega X",
        "vendedor": "Ana",
        "ubicacion": "Av. 1",
        "fecha": "2026-12-05",
        "hora_inicio": "09:00",
        "hora_fin": "13:00",
        "promotoras": 1,
        "igloos": 1,
        "materiales": ["toldo"],
    }
    base.update(kw)
    return base


def test_evento_se_reserva_y_aplica_capacidad(api, bot_usuario, calendario, empresa_a):
    assert enviar(api, "evento", _evento(), key="e1").status_code == 201
    assert (
        enviar(api, "evento", _evento(hora_inicio="10:00"), key="e2").status_code == 201
    )  # 1+1 promotoras
    r = enviar(api, "evento", _evento(hora_inicio="11:00"), key="e3")  # 3ª promotora
    assert r.status_code == 409 and "promotoras" in r.data["error"].lower()
    assert EventoActivacion.objects.filter(id_empresa=empresa_a).count() == 2
    assert not IngestaBot.objects.filter(
        idempotency_key="e3"
    ).exists()  # reintento posible tras editar
    ev = EventoActivacion.objects.first()
    assert ev.origen == "BOT"
    # 09:00 hora de Caracas (UTC-4) = 13:00 UTC: el calendario fija la zona del evento.
    assert ev.inicio.astimezone(timezone.utc) == datetime(
        2026, 12, 5, 13, 0, tzinfo=timezone.utc
    )


def test_evento_dos_promotoras_bloquean_el_horario(api, bot_usuario, calendario):
    assert (
        enviar(api, "evento", _evento(promotoras=2, igloos=0), key="e1").status_code
        == 201
    )
    assert (
        enviar(
            api,
            "evento",
            _evento(promotoras=1, igloos=0, hora_inicio="12:00"),
            key="e2",
        ).status_code
        == 409
    )


def test_evento_exige_promotoras_e_igloos(api, bot_usuario, calendario):
    d = _evento()
    d["promotoras"] = None
    r = enviar(api, "evento", d)
    assert r.status_code == 422 and "promotoras" in r.data["faltan"]


def test_evento_sin_calendario_predeterminado(api, bot_usuario):
    assert enviar(api, "evento", _evento()).status_code == 422


# ── aislamiento ─────────────────────────────────────────────────────────────


@pytest.mark.tenant
def test_no_lista_ingestas_de_otra_empresa(api, bot_usuario, empresa_b, user_b):
    ajeno = BotUsuario.objects.create(
        id_empresa=empresa_b, telegram_user_id=555, usuario=user_b
    )
    IngestaBot.objects.create(
        id_empresa=empresa_b,
        bot_usuario=ajeno,
        kind="pago",
        idempotency_key="z",
        payload={},
    )
    assert api.get(URL).data["results"] == []


@pytest.mark.tenant
def test_usuario_telegram_de_otra_empresa_no_resuelve(
    api, bot_usuario, empresa_b, user_b
):
    BotUsuario.objects.create(
        id_empresa=empresa_b, telegram_user_id=555, usuario=user_b
    )
    assert enviar(api, "contacto", {"nombre": "A"}, tg=555).status_code == 403


# ── permisos de administración ──────────────────────────────────────────────


def test_bot_usuarios_solo_staff(client_a, user_a, empresa_a):
    r = client_a.get("/api/bots/usuarios/")
    assert r.status_code == 403
    user_a.is_staff = True
    user_a.save()
    ok = client_a.post(
        "/api/bots/usuarios/",
        {"telegram_user_id": 42, "usuario": str(user_a.pk), "nombre": "V"},
        format="json",
    )
    assert ok.status_code == 201, ok.data
    assert BotUsuario.objects.get(telegram_user_id=42).id_empresa_id == empresa_a.pk


def test_staff_consulta_ingestas_pero_no_envia(client_a, user_a, empresa_a):
    user_a.is_staff = True
    user_a.save()
    assert client_a.get(URL).status_code == 200
    r = client_a.post(
        URL,
        {
            "kind": "pago",
            "draft": {},
            "source": {"telegram_user_id": 1},
            "idempotency_key": "k",
        },
        format="json",
    )
    assert r.status_code == 403
