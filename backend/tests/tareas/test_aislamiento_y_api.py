"""Tests de API REST, flujos Kanban, dependencias, autenticación CapabilityToken y aislamiento multi-tenant (R-CODE-1)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.core.models import CapabilityToken, Departamento
from apps.tareas import services
from apps.tareas.models import (
    EstadoTarea,
    PlantillaTareaRecurrente,
    PrioridadTarea,
    Proyecto,
    SeccionProyecto,
    Tarea,
)

pytestmark = [pytest.mark.django_db]

BASE = "/api/tareas"


def test_aislamiento_multitenant_estricto_en_todos_los_endpoints(empresa_a, empresa_b, user_a, user_b, client_a):
    area_b = services.crear_area_operativa(empresa=empresa_b, nombre="Ventas B", lider=user_b)
    proy_b = services.crear_proyecto_con_secciones(
        empresa=empresa_b, nombre="Tablero B", area=area_b, propietario=user_b
    )
    sec_b = proy_b.secciones.first()
    tarea_b, _ = services.crear_tarea(
        empresa=empresa_b,
        titulo="Cobrar factura secreta B",
        proyecto=proy_b,
        area=area_b,
        asignado_a=user_b,
    )
    rec_b = PlantillaTareaRecurrente.objects.create(
        id_empresa=empresa_b,
        titulo="Cierre diario B",
        frecuencia=PlantillaTareaRecurrente.Frecuencia.DIARIA,
        proxima_ejecucion=date(2026, 11, 20),
    )
    min_b = services.crear_minuta_borrador(
        empresa=empresa_b,
        titulo="Comité B",
        items_propuestos=[{"titulo": "Revisar stock B"}],
    )

    assert client_a.get(f"{BASE}/areas/").data["results"] == []
    assert client_a.get(f"{BASE}/proyectos/").data["results"] == []
    assert client_a.get(f"{BASE}/secciones/").data["results"] == []
    assert client_a.get(f"{BASE}/items/").data["results"] == []
    assert client_a.get(f"{BASE}/recurrentes/").data["results"] == []
    assert client_a.get(f"{BASE}/minutas/").data["results"] == []

    assert client_a.get(f"{BASE}/areas/{area_b.id_area}/").status_code == 404
    assert client_a.get(f"{BASE}/proyectos/{proy_b.id_proyecto}/").status_code == 404
    assert client_a.get(f"{BASE}/items/{tarea_b.id_tarea}/").status_code == 404
    assert client_a.get(f"{BASE}/recurrentes/{rec_b.id_plantilla_recurrente}/").status_code == 404
    assert client_a.get(f"{BASE}/minutas/{min_b.id_minuta}/").status_code == 404

    # Intentos de referencia cross-tenant al crear en empresa_a se rechazan por TenantFKScopeMixin (400 SEC-M1)
    assert (
        client_a.post(
            f"{BASE}/items/",
            {"titulo": "Intento fuga", "proyecto": str(proy_b.id_proyecto)},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client_a.post(
            f"{BASE}/items/",
            {"titulo": "Intento fuga seccion", "seccion": str(sec_b.id_seccion)},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client_a.post(
            f"{BASE}/items/",
            {"titulo": "Intento fuga usuario", "asignado_a": str(user_b.pk)},
            format="json",
        ).status_code
        == 400
    )
    assert client_a.post(
        f"{BASE}/secciones/",
        {"proyecto": str(proy_b.id_proyecto), "nombre": "Intrusa"},
        format="json",
    ).status_code in (400, 403)


def test_flujo_completo_area_tablero_kanban_subtareas_comentarios_y_entidad_erp(empresa_a, user_a, client_a):
    depto = Departamento.objects.create(id_empresa=empresa_a, nombre_departamento="Operaciones")
    r_area = client_a.post(
        f"{BASE}/areas/",
        {
            "nombre": "Logística y Almacén",
            "color": "#D85A30",
            "departamento": str(depto.id_departamento),
            "lider": str(user_a.pk),
            "palabras_clave": ["despacho", "camion"],
            "miembros": [str(user_a.pk)],
        },
        format="json",
    )
    assert r_area.status_code == 201
    area_id = r_area.data["id_area"]
    assert r_area.data["slug"] == "logistica-y-almacen"
    assert len(r_area.data["miembros"]) == 1

    # Duplicado de área activa responde 409
    assert client_a.post(f"{BASE}/areas/", {"nombre": "Logistica y Almacen"}, format="json").status_code == 409

    # Sincronización de miembros por endpoint dedicado
    r_sync = client_a.post(
        f"{BASE}/areas/{area_id}/miembros/",
        {"usuarios": [str(user_a.pk)]},
        format="json",
    )
    assert r_sync.status_code == 200

    # Tablero personal idempotente
    r_personal_1 = client_a.post(f"{BASE}/proyectos/mi-tablero/", {}, format="json")
    r_personal_2 = client_a.post(f"{BASE}/proyectos/mi-tablero/", {}, format="json")
    assert r_personal_1.status_code == 200
    assert r_personal_1.data["id_proyecto"] == r_personal_2.data["id_proyecto"]
    assert len(r_personal_1.data["secciones"]) == 5

    # Crear tarea vinculada a una entidad del ERP con idempotency_key
    pedido_fake_id = str(uuid.uuid4())
    payload_tarea = {
        "titulo": "Resolver diferencia de conciliación pedido SO-104",
        "descripcion": "Validar soporte Zelle con tesorería",
        "prioridad": PrioridadTarea.ALTA,
        "area": area_id,
        "asignado_a": str(user_a.pk),
        "fecha_inicio": "2026-11-16",
        "fecha_vencimiento": "2026-11-20",
        "entidad_tipo": "cxc_lubrikca.PedidoLubrikca",
        "entidad_id": pedido_fake_id,
        "idempotency_key": "bot-tg-msg-991",
    }
    r_t1 = client_a.post(f"{BASE}/items/", payload_tarea, format="json")
    assert r_t1.status_code == 201
    tarea_id = str(r_t1.data["id_tarea"])
    assert str(r_t1.data["proyecto"]) == str(r_personal_1.data["id_proyecto"])
    assert r_t1.data["seccion_nombre"] == "Pendiente"

    # Reintento con misma idempotency_key devuelve 200 y no duplica
    r_t1_retry = client_a.post(f"{BASE}/items/", payload_tarea, format="json")
    assert r_t1_retry.status_code == 200
    assert str(r_t1_retry.data["id_tarea"]) == tarea_id

    # Subtarea hija
    r_sub = client_a.post(
        f"{BASE}/items/",
        {"titulo": "Solicitar capture al vendedor", "tarea_padre": tarea_id},
        format="json",
    )
    assert r_sub.status_code == 201

    # Mover tarjeta en Kanban a 'En revisión' actualiza estado automáticamente
    sec_revision = next(s for s in r_personal_1.data["secciones"] if s["estado_destino"] == "EN_REVISION")
    r_mov = client_a.post(
        f"{BASE}/items/{tarea_id}/mover/",
        {"seccion": sec_revision["id_seccion"], "orden_tablero": 2},
        format="json",
    )
    assert r_mov.status_code == 200
    assert r_mov.data["estado"] == EstadoTarea.EN_REVISION
    assert r_mov.data["orden_tablero"] == 2

    # Completar tarea por cambiar-estado sincroniza sección 'Completada' y completada_en
    r_comp = client_a.post(
        f"{BASE}/items/{tarea_id}/cambiar-estado/",
        {"estado": EstadoTarea.COMPLETADA, "motivo": "Conciliado en banco"},
        format="json",
    )
    assert r_comp.status_code == 200
    assert r_comp.data["completada_en"] is not None
    assert r_comp.data["seccion_nombre"] == "Completada"

    # Comentarios (incluye los de sistema + comentario humano)
    r_com = client_a.post(
        f"{BASE}/items/{tarea_id}/comentarios/",
        {"cuerpo": "Verificado con extracto Banesco."},
        format="json",
    )
    assert r_com.status_code == 201
    lista_com = client_a.get(f"{BASE}/items/{tarea_id}/comentarios/").data
    assert len(lista_com) >= 3

    # Filtro por entidad del ERP
    por_entidad = client_a.get(
        f"{BASE}/items/?entidad_tipo=cxc_lubrikca.PedidoLubrikca&entidad_id={pedido_fake_id}"
    ).data["results"]
    assert [str(x["id_tarea"]) for x in por_entidad] == [tarea_id]

    # Resumen ejecutivo y configuración de seguimiento
    r_resumen = client_a.get(f"{BASE}/resumen/?fecha=2026-11-16")
    assert r_resumen.status_code == 200
    assert r_resumen.data["totales"]["completadas"] == 1

    r_cfg_get = client_a.get(f"{BASE}/configuracion/")
    assert r_cfg_get.status_code == 200
    r_cfg_patch = client_a.patch(
        f"{BASE}/configuracion/",
        {"horas_bloqueo_vencida": 48, "gerente": str(user_a.pk)},
        format="json",
    )
    assert r_cfg_patch.status_code == 200
    assert r_cfg_patch.data["horas_bloqueo_vencida"] == 48

    # Soft delete (R-CODE-6)
    assert client_a.delete(f"{BASE}/items/{r_sub.data['id_tarea']}/").status_code == 204
    sub_db = Tarea.objects.get(pk=r_sub.data["id_tarea"])
    assert sub_db.activo is False


def test_dependencias_detectan_autodependencia_y_ciclos(empresa_a, client_a):
    t1, _ = services.crear_tarea(empresa=empresa_a, titulo="Paso 1")
    t2, _ = services.crear_tarea(empresa=empresa_a, titulo="Paso 2")
    t3, _ = services.crear_tarea(empresa=empresa_a, titulo="Paso 3")

    assert (
        client_a.post(
            f"{BASE}/items/{t2.id_tarea}/dependencias/",
            {"depende_de": str(t1.id_tarea)},
            format="json",
        ).status_code
        == 201
    )
    assert (
        client_a.post(
            f"{BASE}/items/{t3.id_tarea}/dependencias/",
            {"depende_de": str(t2.id_tarea)},
            format="json",
        ).status_code
        == 201
    )
    # Ciclo t1 -> t3 (cuando t3 -> t2 -> t1) debe rechazarse con 409
    r_ciclo = client_a.post(
        f"{BASE}/items/{t1.id_tarea}/dependencias/",
        {"depende_de": str(t3.id_tarea)},
        format="json",
    )
    assert r_ciclo.status_code == 409

    # Autodependencia rechazada con 400
    r_self = client_a.post(
        f"{BASE}/items/{t1.id_tarea}/dependencias/",
        {"depende_de": str(t1.id_tarea)},
        format="json",
    )
    assert r_self.status_code == 400
    assert len(client_a.get(f"{BASE}/items/{t2.id_tarea}/dependencias/").data) == 1


def test_autenticacion_capability_token_scopes_lectura_y_escritura(empresa_a, user_a):
    tok_read = CapabilityToken.objects.create(
        empresa=empresa_a,
        creado_por=user_a,
        scopes=["tareas:read"],
    )
    tok_write = CapabilityToken.objects.create(
        empresa=empresa_a,
        creado_por=user_a,
        scopes=["tareas:write"],
    )
    tok_otro = CapabilityToken.objects.create(
        empresa=empresa_a,
        creado_por=user_a,
        scopes=["bots:heartbeat"],
    )

    cli_otro = APIClient()
    cli_otro.credentials(HTTP_X_CAPABILITY_TOKEN=str(tok_otro.token))
    assert cli_otro.get(f"{BASE}/items/").status_code == 403

    cli_read = APIClient()
    cli_read.credentials(HTTP_X_CAPABILITY_TOKEN=str(tok_read.token))
    assert cli_read.get(f"{BASE}/items/").status_code == 200
    assert cli_read.post(f"{BASE}/items/", {"titulo": "No permitido"}, format="json").status_code == 403

    cli_write = APIClient()
    cli_write.credentials(HTTP_X_CAPABILITY_TOKEN=str(tok_write.token))
    r_crear = cli_write.post(
        f"{BASE}/items/",
        {"titulo": "Creada por bot de Telegram", "origen": "BOT"},
        format="json",
    )
    assert r_crear.status_code == 201
    assert cli_write.get(f"{BASE}/items/").data["count"] == 1


def test_validaciones_de_modelo_clean(empresa_a, empresa_b):
    proy_a = services.crear_proyecto_con_secciones(empresa=empresa_a, nombre="P-A")
    proy_b = services.crear_proyecto_con_secciones(empresa=empresa_b, nombre="P-B")
    sec_b = proy_b.secciones.first()

    # Proyecto personal sin propietario falla clean()
    p_invalido = Proyecto(id_empresa=empresa_a, nombre="Personal sin dueño", es_personal=True)
    with pytest.raises(ValidationError):
        p_invalido.full_clean()

    # Tarea con entidad_tipo sin entidad_id falla clean()
    t_ent = Tarea(id_empresa=empresa_a, titulo="Incompleta", entidad_tipo="ventas.Pedido")
    with pytest.raises(ValidationError):
        t_ent.full_clean()

    # Tarea con fecha_vencimiento < fecha_inicio falla clean()
    t_fechas = Tarea(
        id_empresa=empresa_a,
        titulo="Fechas invertidas",
        fecha_inicio=date(2026, 11, 20),
        fecha_vencimiento=date(2026, 11, 18),
    )
    with pytest.raises(ValidationError):
        t_fechas.full_clean()

    # Tarea con sección de otro proyecto falla clean()
    sec_otra_a = SeccionProyecto.objects.create(
        id_empresa=empresa_a,
        proyecto=services.crear_proyecto_con_secciones(empresa=empresa_a, nombre="Otro A"),
        nombre="Extra",
    )
    t_sec = Tarea(id_empresa=empresa_a, titulo="Desalineada", proyecto=proy_a, seccion=sec_otra_a)
    with pytest.raises(ValidationError):
        t_sec.full_clean()

    # Cross-tenant en clean()
    t_cross = Tarea(id_empresa=empresa_a, titulo="Cross", seccion=sec_b)
    with pytest.raises(ValidationError):
        t_cross.full_clean()
