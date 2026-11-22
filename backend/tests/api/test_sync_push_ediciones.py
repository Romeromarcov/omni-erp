"""
Push optimista de ediciones offline (POST /api/sync/push/ + MCP) — CTF-008 Nivel 2.

Cubre:
  - Edición individual sobre entidades whitelistadas (``clientes``, ``productos``).
  - Control de concurrencia optimista (``expected_fecha_actualizacion`` + ``select_for_update``):
    HTTP 409 ``CONFLICTO_VERSION`` con ``registro_servidor`` sin sobrescribir datos recientes,
    y reintento exitoso usando el nuevo cursor del servidor.
  - Lotes atómicos (``mutaciones``): éxito multi-ítem y rollback total si un ítem genera 409.
  - Idempotencia vía ``Idempotency-Key``: replay 200 no duplica; 409 no consume la clave;
    payload distinto con misma clave → 422.
  - Seguridad / R-CODE-1: campos no editables (``CAMPO_NO_EDITABLE``), entidades solo
    lectura (``ENTIDAD_NO_EDITABLE``), aislamiento cross-tenant (404 sin fuga), NUL bytes,
    validación Decimal/bool.
  - Paridad MCP: ``sync_aplicar_actualizacion_optimista`` (scope ``sync:write``).
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import CapabilityToken
from apps.crm.models import Cliente
from apps.inventario.models import CategoriaProducto, Producto, UnidadMedida

pytestmark = pytest.mark.django_db

URL = "/api/sync/push/"


@pytest.fixture
def cliente_sync(db, empresa_a):
    return Cliente.objects.create(
        id_empresa=empresa_a,
        razon_social="Cliente Original S.A.",
        nombre_comercial="Original",
        rif="J-111111111",
        telefono="0414-0000001",
        email="orig@cliente.test",
        tipo_cliente="CONTADO",
    )


@pytest.fixture
def producto_sync(db, empresa_a, moneda_usd):
    unidad = UnidadMedida.objects.create(
        id_empresa=empresa_a, nombre="Unidad Sync", abreviatura="UN-SYNC", tipo="CANTIDAD"
    )
    categoria = CategoriaProducto.objects.create(id_empresa=empresa_a, nombre_categoria="Cat Sync")
    return Producto.objects.create(
        id_empresa=empresa_a,
        nombre_producto="Filtro Sync",
        sku="SKU-SYNC-01",
        id_categoria=categoria,
        id_unidad_medida_base=unidad,
        id_moneda_precio=moneda_usd,
        costo_promedio=Decimal("10.0000"),
        precio_venta_sugerido=Decimal("18.5000"),
    )


def test_sync_push_requiere_auth_y_empresa(db):
    anon = APIClient()
    resp = anon.post(URL, {}, format="json")
    assert resp.status_code == 401


def test_sync_push_usuario_sin_empresa_retorna_403(db):
    from apps.core.models import Usuarios

    sin_emp = Usuarios.objects.create_user(
        username="sync_sin_emp",
        email="sync_sin_emp@test.local",
        password="TestUser#Sync2026!",
        is_active=True,
    )
    client = APIClient()
    client.force_authenticate(user=sin_emp)
    resp = client.post(URL, {"entity": "clientes"}, format="json")
    assert resp.status_code == 403


def test_sync_push_edicion_individual_exitosa_clientes_y_productos(client_a, cliente_sync, producto_sync):
    cursor_cli_inicial = cliente_sync.fecha_actualizacion.isoformat()
    resp_cli = client_a.post(
        URL,
        {
            "entity": "clientes",
            "id": str(cliente_sync.id_cliente),
            "expected_fecha_actualizacion": cursor_cli_inicial,
            "cambios": {
                "telefono": "0412-9998877",
                "nombre_comercial": "Original Editado",
            },
        },
        format="json",
    )
    assert resp_cli.status_code == 200, resp_cli.json()
    body_cli = resp_cli.json()
    assert body_cli["entity"] == "clientes"
    assert body_cli["id"] == str(cliente_sync.id_cliente)
    assert body_cli["registro"]["telefono"] == "0412-9998877"
    assert body_cli["registro"]["nombre_comercial"] == "Original Editado"
    assert "server_time" in body_cli

    cliente_sync.refresh_from_db()
    assert cliente_sync.telefono == "0412-9998877"
    assert cliente_sync.fecha_actualizacion.isoformat() == body_cli["registro"]["fecha_actualizacion"]

    cursor_prod = producto_sync.fecha_actualizacion.isoformat()
    resp_prod = client_a.post(
        URL,
        {
            "entity": "productos",
            "id": str(producto_sync.id_producto),
            "expected_fecha_actualizacion": cursor_prod,
            "cambios": {"precio_venta_sugerido": "24.7500", "nombre_producto": "Filtro Sync Pro"},
        },
        format="json",
    )
    assert resp_prod.status_code == 200, resp_prod.json()
    producto_sync.refresh_from_db()
    assert producto_sync.precio_venta_sugerido == Decimal("24.7500")
    assert producto_sync.nombre_producto == "Filtro Sync Pro"


def test_sync_push_conflicto_409_no_pisar_y_reintento_con_cursor_servidor(client_a, cliente_sync):
    cursor_offline = cliente_sync.fecha_actualizacion.isoformat()

    # Otro usuario actualiza el cliente en el servidor mientras este cliente estaba offline.
    cliente_sync.telefono = "0424-7776655"
    cliente_sync.nombre_comercial = "Actualizado en Servidor"
    cliente_sync.save()
    # Garantizar avance determinista del timestamp en plataformas con resolución gruesa (Windows)
    Cliente.objects.filter(pk=cliente_sync.pk).update(
        fecha_actualizacion=cliente_sync.fecha_actualizacion + datetime.timedelta(seconds=5)
    )
    cliente_sync.refresh_from_db()

    # El cliente offline intenta empujar usando su cursor viejo y clave de idempotencia.
    idem_key = f"push-edit-{uuid.uuid4()}"
    resp_conflict = client_a.post(
        URL,
        {
            "entity": "clientes",
            "id": str(cliente_sync.id_cliente),
            "expected_fecha_actualizacion": cursor_offline,
            "cambios": {"telefono": "0414-0009999"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=idem_key,
    )
    assert resp_conflict.status_code == 409
    err = resp_conflict.json()
    assert err["codigo"] == "CONFLICTO_VERSION"
    assert err["entity"] == "clientes"
    assert err["id"] == str(cliente_sync.id_cliente)
    assert err["registro_servidor"]["telefono"] == "0424-7776655"
    assert err["registro_servidor"]["nombre_comercial"] == "Actualizado en Servidor"

    # El registro en BD NO fue pisado por la edición offline obsoleta.
    cliente_sync.refresh_from_db()
    assert cliente_sync.telefono == "0424-7776655"

    # Reintento usando el nuevo cursor devuelto en `registro_servidor` (la clave 409 no se consumió).
    nuevo_cursor = err["registro_servidor"]["fecha_actualizacion"]
    resp_ok = client_a.post(
        URL,
        {
            "entity": "clientes",
            "id": str(cliente_sync.id_cliente),
            "expected_fecha_actualizacion": nuevo_cursor,
            "cambios": {"telefono": "0414-0009999"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=idem_key,
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["registro"]["telefono"] == "0414-0009999"

    # Replay idempotente de la respuesta 200.
    resp_replay = client_a.post(
        URL,
        {
            "entity": "clientes",
            "id": str(cliente_sync.id_cliente),
            "expected_fecha_actualizacion": nuevo_cursor,
            "cambios": {"telefono": "0414-0009999"},
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY=idem_key,
    )
    assert resp_replay.status_code == 200
    assert resp_replay.json() == resp_ok.json()


def test_sync_push_lote_atomico_exito_y_rollback_en_conflicto(client_a, cliente_sync, producto_sync):
    cursor_cli = cliente_sync.fecha_actualizacion.isoformat()
    cursor_prod_stale = producto_sync.fecha_actualizacion.isoformat()

    # Modificamos el producto en servidor para provocar conflicto en el ítem 1 del lote.
    producto_sync.nombre_producto = "Filtro Modificado Concurrente"
    producto_sync.save()
    Producto.objects.filter(pk=producto_sync.pk).update(
        fecha_actualizacion=producto_sync.fecha_actualizacion + datetime.timedelta(seconds=5)
    )
    producto_sync.refresh_from_db()

    resp_fail = client_a.post(
        URL,
        {
            "mutaciones": [
                {
                    "entity": "clientes",
                    "id": str(cliente_sync.id_cliente),
                    "expected_fecha_actualizacion": cursor_cli,
                    "cambios": {"telefono": "0416-1112233"},
                },
                {
                    "entity": "productos",
                    "id": str(producto_sync.id_producto),
                    "expected_fecha_actualizacion": cursor_prod_stale,
                    "cambios": {"precio_venta_sugerido": "99.0000"},
                },
            ]
        },
        format="json",
    )
    assert resp_fail.status_code == 409
    err = resp_fail.json()
    assert err["codigo"] == "CONFLICTO_VERSION"
    assert err["index"] == 1
    assert err["entity"] == "productos"

    # Rollback atómico: ni siquiera el cliente (ítem 0) debe haberse modificado.
    cliente_sync.refresh_from_db()
    producto_sync.refresh_from_db()
    assert cliente_sync.telefono == "0414-0000001"
    assert producto_sync.precio_venta_sugerido == Decimal("18.5000")

    # Ahora enviamos el lote con el cursor actual del producto → éxito 200.
    resp_ok = client_a.post(
        URL,
        {
            "mutaciones": [
                {
                    "entity": "clientes",
                    "id": str(cliente_sync.id_cliente),
                    "expected_fecha_actualizacion": cliente_sync.fecha_actualizacion.isoformat(),
                    "cambios": {"telefono": "0416-1112233"},
                },
                {
                    "entity": "productos",
                    "id": str(producto_sync.id_producto),
                    "expected_fecha_actualizacion": producto_sync.fecha_actualizacion.isoformat(),
                    "cambios": {"precio_venta_sugerido": "29.9000"},
                },
            ]
        },
        format="json",
    )
    assert resp_ok.status_code == 200
    body = resp_ok.json()
    assert body["count"] == 2
    assert len(body["results"]) == 2
    cliente_sync.refresh_from_db()
    producto_sync.refresh_from_db()
    assert cliente_sync.telefono == "0416-1112233"
    assert producto_sync.precio_venta_sugerido == Decimal("29.9000")


def test_sync_push_seguridad_whitelist_y_aislamiento_tenant(client_a, client_b, empresa_b, cliente_sync):
    cursor = cliente_sync.fecha_actualizacion.isoformat()

    # 1. Campo fuera de whitelist (ej. `id_empresa` o `rif`) → 422 CAMPO_NO_EDITABLE
    resp_campo = client_a.post(
        URL,
        {
            "entity": "clientes",
            "id": str(cliente_sync.id_cliente),
            "expected_fecha_actualizacion": cursor,
            "cambios": {"rif": "J-99999999-9"},
        },
        format="json",
    )
    assert resp_campo.status_code == 422
    assert resp_campo.json()["codigo"] == "CAMPO_NO_EDITABLE"

    # 2. Entidad de solo lectura → 422 ENTIDAD_NO_EDITABLE
    resp_ro = client_a.post(
        URL,
        {
            "entity": "unidades_medida",
            "id": str(uuid.uuid4()),
            "expected_fecha_actualizacion": cursor,
            "cambios": {"nombre": "X"},
        },
        format="json",
    )
    assert resp_ro.status_code == 422
    assert resp_ro.json()["codigo"] == "ENTIDAD_NO_EDITABLE"

    # 3. Aislamiento multi-tenant (R-CODE-1): usuario B intenta mutar cliente de empresa A → 404
    resp_cross = client_b.post(
        URL,
        {
            "entity": "clientes",
            "id": str(cliente_sync.id_cliente),
            "expected_fecha_actualizacion": cursor,
            "cambios": {"telefono": "0414-HACKEADO"},
        },
        format="json",
    )
    assert resp_cross.status_code == 404
    assert resp_cross.json()["codigo"] == "NO_ENCONTRADO"
    cliente_sync.refresh_from_db()
    assert cliente_sync.telefono == "0414-0000001"

    # 4. NUL byte rechazado → 400
    resp_nul = client_a.post(
        URL,
        {
            "entity": "clientes",
            "id": str(cliente_sync.id_cliente),
            "expected_fecha_actualizacion": cursor,
            "cambios": {"telefono": "0414\x00123"},
        },
        format="json",
    )
    assert resp_nul.status_code == 400
    assert resp_nul.json()["codigo"] == "CARACTER_INVALIDO"


def test_sync_push_validaciones_tipos_y_lote(client_a, cliente_sync, producto_sync):
    # Lista en lugar de dict → 400
    assert client_a.post(URL, [], format="json").status_code == 400

    # Entidad inexistente → 422
    resp_ent = client_a.post(
        URL,
        {
            "entity": "no_existe",
            "id": str(cliente_sync.id_cliente),
            "expected_fecha_actualizacion": timezone.now().isoformat(),
            "cambios": {"activo": False},
        },
        format="json",
    )
    assert resp_ent.status_code == 422

    # Timestamp inválido → 422
    resp_ts = client_a.post(
        URL,
        {
            "entity": "clientes",
            "id": str(cliente_sync.id_cliente),
            "expected_fecha_actualizacion": "no-es-fecha",
            "cambios": {"telefono": "123"},
        },
        format="json",
    )
    assert resp_ts.status_code == 422
    assert resp_ts.json()["codigo"] == "VERSION_INVALIDA"

    # Boolean inválido / Decimal inválido → 422
    resp_bool = client_a.post(
        URL,
        {
            "entity": "clientes",
            "id": str(cliente_sync.id_cliente),
            "expected_fecha_actualizacion": cliente_sync.fecha_actualizacion.isoformat(),
            "cambios": {"activo": "si"},
        },
        format="json",
    )
    assert resp_bool.status_code == 422

    resp_dec = client_a.post(
        URL,
        {
            "entity": "productos",
            "id": str(producto_sync.id_producto),
            "expected_fecha_actualizacion": producto_sync.fecha_actualizacion.isoformat(),
            "cambios": {"precio_venta_sugerido": "NaN"},
        },
        format="json",
    )
    assert resp_dec.status_code == 422

    # Validación full_clean() falla ante email inválido → 422 VALIDACION_FALLIDA
    resp_email = client_a.post(
        URL,
        {
            "entity": "clientes",
            "id": str(cliente_sync.id_cliente),
            "expected_fecha_actualizacion": cliente_sync.fecha_actualizacion.isoformat(),
            "cambios": {"email": "no-es-un-email"},
        },
        format="json",
    )
    assert resp_email.status_code == 422
    assert resp_email.json()["codigo"] == "VALIDACION_FALLIDA"


def test_mcp_sync_aplicar_actualizacion_optimista(empresa_a, empresa_b, cliente_sync):
    from apps.sync.mcp import sync_aplicar_actualizacion_optimista

    tok_write = CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="sync-write",
        scopes=["sync:write"],
        activo=True,
    )
    tok_read = CapabilityToken.objects.create(
        empresa=empresa_a,
        nombre="sync-read",
        scopes=["sync:read"],
        activo=True,
    )

    cursor = cliente_sync.fecha_actualizacion.isoformat()

    # Éxito vía MCP
    res_ok = sync_aplicar_actualizacion_optimista(
        capability_token=str(tok_write.token),
        entity="clientes",
        record_id=str(cliente_sync.id_cliente),
        expected_fecha_actualizacion=cursor,
        cambios={"telefono": "0412-5550000"},
    )
    assert res_ok["ok"] is True
    assert res_ok["registro"]["telefono"] == "0412-5550000"

    # Conflicto con cursor viejo vía MCP
    res_conflict = sync_aplicar_actualizacion_optimista(
        capability_token=str(tok_write.token),
        entity="clientes",
        record_id=str(cliente_sync.id_cliente),
        expected_fecha_actualizacion=cursor,
        cambios={"telefono": "0412-9999999"},
    )
    assert res_conflict["ok"] is False
    assert res_conflict["codigo"] == "CONFLICTO_VERSION"
    assert res_conflict["registro_servidor"]["telefono"] == "0412-5550000"

    # Scope insuficiente / cross-tenant
    with pytest.raises(PermissionError):
        sync_aplicar_actualizacion_optimista(
            capability_token=str(tok_read.token),
            entity="clientes",
            record_id=str(cliente_sync.id_cliente),
            expected_fecha_actualizacion=res_conflict["registro_servidor"]["fecha_actualizacion"],
            cambios={"telefono": "0412-1111111"},
        )

    with pytest.raises(PermissionError):
        sync_aplicar_actualizacion_optimista(
            capability_token=str(tok_write.token),
            entity="clientes",
            record_id=str(cliente_sync.id_cliente),
            expected_fecha_actualizacion=res_conflict["registro_servidor"]["fecha_actualizacion"],
            cambios={"telefono": "0412-1111111"},
            empresa_id=str(empresa_b.pk),
        )

    with pytest.raises(ValueError):
        sync_aplicar_actualizacion_optimista(
            capability_token=str(tok_write.token),
            entity="clientes",
            record_id=str(cliente_sync.id_cliente),
            expected_fecha_actualizacion=res_conflict["registro_servidor"]["fecha_actualizacion"],
            cambios={"telefono": "0412-1111111"},
            empresa_id="no-es-uuid",
        )

    with pytest.raises(ValueError):
        sync_aplicar_actualizacion_optimista(
            capability_token=str(tok_write.token),
            entity="clientes",
            record_id=str(cliente_sync.id_cliente),
            expected_fecha_actualizacion=res_conflict["registro_servidor"]["fecha_actualizacion"],
            cambios={"rif": "J-999"},
        )


def test_sync_push_validaciones_exhaustivas_campos_y_lote(client_a, cliente_sync, producto_sync):
    from django.db import models
    from apps.sync.services import (
        SyncPushError,
        _normalizar_campo,
        _parse_expected_timestamp,
        _timestamps_coinciden,
        contiene_nul,
    )

    cursor = cliente_sync.fecha_actualizacion.isoformat()

    # UUID inválido (no-str / no-uuid) y expected timestamp ausente
    assert (
        client_a.post(
            URL,
            {"entity": "clientes", "id": 123, "expected_fecha_actualizacion": cursor, "cambios": {"activo": True}},
            format="json",
        ).status_code
        == 422
    )
    assert (
        client_a.post(
            URL,
            {
                "entity": "clientes",
                "id": "mal-uuid",
                "expected_fecha_actualizacion": cursor,
                "cambios": {"activo": True},
            },
            format="json",
        ).status_code
        == 422
    )
    assert (
        client_a.post(
            URL,
            {"entity": "clientes", "id": str(cliente_sync.id_cliente), "cambios": {"activo": True}},
            format="json",
        ).status_code
        == 422
    )

    # Naive timestamp normalizado a UTC y contiene_nul recursivo en listas
    dt_naive = _parse_expected_timestamp("2026-11-22T10:00:00")
    assert dt_naive.tzinfo is not None
    assert _timestamps_coinciden(None, dt_naive) is False
    assert contiene_nul(["ok", "bad\x00"]) is True
    assert _normalizar_campo(models.IntegerField(), 5, "cant") == 5
    assert _normalizar_campo(models.DecimalField(max_digits=10, decimal_places=2), Decimal("1.23"), "x") == Decimal(
        "1.23"
    )
    with pytest.raises(SyncPushError):
        _normalizar_campo(models.CharField(max_length=10), "ok\x00", "x")

    # `cambios` vacío
    assert (
        client_a.post(
            URL,
            {
                "entity": "clientes",
                "id": str(cliente_sync.id_cliente),
                "expected_fecha_actualizacion": cursor,
                "cambios": {},
            },
            format="json",
        ).status_code
        == 422
    )

    # Null aceptado en campo nullable (nombre_comercial) y rechazado en no-nullable (razon_social)
    r_null_bad = client_a.post(
        URL,
        {
            "entity": "clientes",
            "id": str(cliente_sync.id_cliente),
            "expected_fecha_actualizacion": cursor,
            "cambios": {"razon_social": None},
        },
        format="json",
    )
    assert r_null_bad.status_code == 422

    r_null_ok = client_a.post(
        URL,
        {
            "entity": "clientes",
            "id": str(cliente_sync.id_cliente),
            "expected_fecha_actualizacion": cursor,
            "cambios": {"nombre_comercial": None},
        },
        format="json",
    )
    assert r_null_ok.status_code == 200
    assert r_null_ok.json()["registro"]["nombre_comercial"] is None

    # Decimal bool / texto no numérico y CharField no string
    cursor_prod = producto_sync.fecha_actualizacion.isoformat()
    assert (
        client_a.post(
            URL,
            {
                "entity": "productos",
                "id": str(producto_sync.id_producto),
                "expected_fecha_actualizacion": cursor_prod,
                "cambios": {"precio_venta_sugerido": True},
            },
            format="json",
        ).status_code
        == 422
    )
    assert (
        client_a.post(
            URL,
            {
                "entity": "productos",
                "id": str(producto_sync.id_producto),
                "expected_fecha_actualizacion": cursor_prod,
                "cambios": {"precio_venta_sugerido": "no-numero"},
            },
            format="json",
        ).status_code
        == 422
    )
    assert (
        client_a.post(
            URL,
            {
                "entity": "productos",
                "id": str(producto_sync.id_producto),
                "expected_fecha_actualizacion": cursor_prod,
                "cambios": {"nombre_producto": 999},
            },
            format="json",
        ).status_code
        == 422
    )

    # Lote vacío, excedido (>100) o con elemento no-dict
    assert client_a.post(URL, {"mutaciones": []}, format="json").status_code == 422
    assert client_a.post(URL, {"mutaciones": [{}] * 101}, format="json").status_code == 422
    assert client_a.post(URL, {"mutaciones": ["invalido"]}, format="json").status_code == 422
