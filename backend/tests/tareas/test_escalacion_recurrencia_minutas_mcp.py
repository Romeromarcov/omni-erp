"""Tests del motor de recordatorios/escalación, recurrencia, minutas IA, Celery y herramientas MCP."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from apps.core.models import CapabilityToken, Notificacion, Usuarios
from apps.tareas import mcp as tareas_mcp
from apps.tareas import services
from apps.tareas.models import (
    EstadoTarea,
    MinutaReunion,
    PlantillaTareaRecurrente,
    RegistroAlertaTarea,
    Tarea,
)
from apps.tareas.tasks import ejecutar_ciclo_empresa, ejecutar_ciclo_todos

pytestmark = [pytest.mark.django_db]

CARACAS = ZoneInfo("America/Caracas")


@pytest.fixture
def admin_user_a(empresa_a):
    u = Usuarios.objects.create_user(
        username="gerente_tareas_a",
        email="gerente_a@omni.test",
        password="TestPassword123!",
        first_name="Marco",
        last_name="Romero",
    )
    u.empresas.add(empresa_a)
    return u


# ── 1. Motor determinístico de recordatorios y escalación ────────────────────


@pytest.mark.parametrize(
    ("plazo_dias", "dias_antes", "esperado"),
    [
        (30, 15, ["preventivo_15d"]),
        (30, 7, ["preventivo_7d"]),
        (14, 7, ["preventivo_7d"]),
        (7, 3, ["preventivo_3d"]),
        (3, 1, ["preventivo_1d"]),
        (3, 2, []),
    ],
)
def test_recordatorios_preventivos_por_plazo(plazo_dias, dias_antes, esperado):
    vencimiento = date(2026, 12, 30)
    creacion = date.fromordinal(vencimiento.toordinal() - plazo_dias)
    hoy = date.fromordinal(vencimiento.toordinal() - dias_antes)
    ahora = datetime(hoy.year, hoy.month, hoy.day, 9, 0, tzinfo=CARACAS)

    acciones = services.evaluar_alertas_tarea(
        fecha_creacion=creacion,
        fecha_vencimiento=vencimiento,
        ahora_local=ahora,
        momento="MANANA",
    )
    assert [a.clave_alerta for a in acciones] == esperado


def test_regla_especial_viernes_previo_a_vencimiento_lunes():
    # 2026-11-23 es lunes; 2026-11-20 es viernes (3 días antes) con plazo corto de 4 días.
    lunes = date(2026, 11, 23)
    creacion = date(2026, 11, 19)
    viernes = date(2026, 11, 20)
    ahora = datetime(viernes.year, viernes.month, viernes.day, 9, 0, tzinfo=CARACAS)

    acciones = services.evaluar_alertas_tarea(
        fecha_creacion=creacion,
        fecha_vencimiento=lunes,
        ahora_local=ahora,
        momento="MANANA",
    )
    assert [a.clave_alerta for a in acciones] == ["viernes_previo_lunes"]


def test_escalacion_progresiva_y_bloqueo_automatico_idempotente(empresa_a, user_a, admin_user_a):
    area = services.crear_area_operativa(empresa=empresa_a, nombre="Cobranza", lider=admin_user_a)
    cfg = services.obtener_o_crear_configuracion_seguimiento(empresa_a)
    cfg.gerente = admin_user_a
    cfg.save()

    tarea, _ = services.crear_tarea(
        empresa=empresa_a,
        titulo="Conciliar cobro vencido cliente VIP",
        area=area,
        asignado_a=user_a,
        fecha_inicio=date(2026, 11, 1),
        fecha_vencimiento=date(2026, 11, 10),
    )

    # Tarde del mismo día de vencimiento -> vencida_tarde_0d
    t_0d = datetime(2026, 11, 10, 15, 30, tzinfo=CARACAS)
    res_0 = services.ejecutar_seguimiento_empresa(empresa_a, ahora=t_0d, momento="TARDE")
    assert res_0["alertas_emitidas"] == 1
    assert res_0["tareas_bloqueadas"] == 0

    # Repetir en el mismo instante es idempotente (0 alertas nuevas)
    res_dup = services.ejecutar_seguimiento_empresa(empresa_a, ahora=t_0d, momento="TARDE")
    assert res_dup["alertas_emitidas"] == 0

    # +73 horas después de las 18:00 del vencimiento -> bloqueo automático
    t_73h = datetime(2026, 11, 13, 19, 30, tzinfo=CARACAS)
    res_bloq = services.ejecutar_seguimiento_empresa(empresa_a, ahora=t_73h, momento="TARDE")
    assert res_bloq["tareas_bloqueadas"] == 1

    tarea.refresh_from_db()
    assert tarea.estado == EstadoTarea.BLOQUEADA
    assert tarea.bloqueada_por_escalacion is True
    assert RegistroAlertaTarea.objects.filter(tarea=tarea).count() == 2
    assert Notificacion.objects.filter(id_empresa=empresa_a).count() >= 2


# ── 2. Tareas recurrentes (intradía, semanal, mensual fin de febrero) ────────


def test_recurrencia_mensual_bisiesto_e_intradia_idempotente(empresa_a, user_a, client_a):
    # Fin de mes: 31 de enero -> 28 de febrero de 2026
    sig_feb = services.calcular_siguiente_fecha(
        frecuencia=PlantillaTareaRecurrente.Frecuencia.MENSUAL,
        actual=date(2026, 1, 31),
        dia_mes=31,
    )
    assert sig_feb == date(2026, 2, 28)

    # Plantilla intradía con 2 horarios
    r_rec = client_a.post(
        "/api/tareas/recurrentes/",
        {
            "titulo": "Actualizar tasa BCV y Binance",
            "frecuencia": PlantillaTareaRecurrente.Frecuencia.INTRADIA,
            "horas_dia": ["09:00", "13:30"],
            "proxima_ejecucion": "2026-11-16",
            "asignado_a": str(user_a.pk),
        },
        format="json",
    )
    assert r_rec.status_code == 201

    r_mat = client_a.post(
        "/api/tareas/recurrentes/materializar/",
        {"fecha": "2026-11-16"},
        format="json",
    )
    assert r_mat.status_code == 200
    assert r_mat.data["tareas_creadas"] == 2

    # Re-ejecutar en la misma fecha no crea duplicados porque proxima_ejecucion avanzó
    r_mat_2 = client_a.post(
        "/api/tareas/recurrentes/materializar/",
        {"fecha": "2026-11-16"},
        format="json",
    )
    assert r_mat_2.data["tareas_creadas"] == 0


# ── 3. Minutas con IA (inferencia de área/responsable + fechas relativas) ────


def test_minutas_enriquecimiento_por_area_y_confirmacion_atomica(empresa_a, user_a, admin_user_a, client_a):
    user_a.first_name = "Pedro"
    user_a.last_name = "Gómez"
    user_a.save()

    services.crear_area_operativa(
        empresa=empresa_a,
        nombre="Almacén",
        lider=user_a,
        palabras_clave=["inventario", "conteo"],
    )
    services.crear_area_operativa(
        empresa=empresa_a,
        nombre="Cobranza",
        lider=admin_user_a,
    )

    r_min = client_a.post(
        "/api/tareas/minutas/",
        {
            "titulo": "Reunión operativa semanal",
            "fecha_reunion": "2026-11-16",
            "texto_fuente": "1. Hacer conteo físico de inventario mañana. 2. Pedro revisar despacho en 3 dias.",
            "items_propuestos": [
                {
                    "task_name": "Hacer conteo físico de inventario",
                    "due_on": "mañana",
                    "notes": "Priorizar lubricantes sintéticos",
                },
                {
                    "titulo": "Revisar guía de despacho",
                    "asignado_nombre": "Pedro",
                    "fecha_vencimiento": "en 3 dias",
                    "prioridad": "ALTA",
                },
            ],
        },
        format="json",
    )
    assert r_min.status_code == 201
    minuta_id = r_min.data["id_minuta"]
    borrador = r_min.data["borrador_tareas"]
    assert len(borrador) == 2
    # El ítem 1 infirió el área Almacén y su líder (Pedro) por palabra clave 'inventario'
    assert borrador[0]["asignado_a_id"] == str(user_a.pk)
    assert borrador[0]["fecha_vencimiento"] == "2026-11-17"
    assert borrador[1]["fecha_vencimiento"] == "2026-11-19"

    r_conf = client_a.post(f"/api/tareas/minutas/{minuta_id}/confirmar/", {}, format="json")
    assert r_conf.status_code == 200
    assert r_conf.data["minuta"]["estado"] == MinutaReunion.Estado.CONFIRMADA
    assert len(r_conf.data["tareas_creadas"]) == 2

    # Confirmar dos veces es idempotente
    r_conf_2 = client_a.post(f"/api/tareas/minutas/{minuta_id}/confirmar/", {}, format="json")
    assert r_conf_2.status_code == 200
    assert len(r_conf_2.data["tareas_creadas"]) == 2


# ── 4. Herramientas MCP + Tareas Celery ──────────────────────────────────────


def test_herramientas_mcp_y_aislamiento_por_token(empresa_a, empresa_b, user_a):
    tok_rw = CapabilityToken.objects.create(
        empresa=empresa_a,
        creado_por=user_a,
        scopes=["tareas:read", "tareas:write"],
    )
    tok_solo_lectura = CapabilityToken.objects.create(
        empresa=empresa_a,
        creado_por=user_a,
        scopes=["tareas:read"],
    )

    # Token inválido o tenant cruzado lanza PermissionError
    with pytest.raises(PermissionError):
        tareas_mcp.tareas_listar("token-invalido", str(empresa_a.id_empresa))

    with pytest.raises(PermissionError):
        tareas_mcp.tareas_listar(str(tok_rw.token), str(empresa_b.id_empresa))

    with pytest.raises(PermissionError):
        tareas_mcp.tareas_crear(
            str(tok_solo_lectura.token),
            str(empresa_a.id_empresa),
            titulo="Sin permiso write",
        )

    creada = tareas_mcp.tareas_crear(
        str(tok_rw.token),
        str(empresa_a.id_empresa),
        titulo="Preparar reporte BCV",
        asignado_a_id=str(user_a.pk),
        fecha_vencimiento="2026-11-25",
        idempotency_key="mcp-1",
    )
    assert creada["creada"] is True
    tarea_id = creada["id_tarea"]

    listado = tareas_mcp.tareas_listar(str(tok_rw.token), str(empresa_a.id_empresa), estado="PENDIENTE")
    assert len(listado) == 1
    assert listado[0]["id_tarea"] == tarea_id

    cambio = tareas_mcp.tareas_cambiar_estado(
        str(tok_rw.token),
        str(empresa_a.id_empresa),
        tarea_id=tarea_id,
        nuevo_estado="COMPLETADA",
    )
    assert cambio["estado"] == "COMPLETADA"

    minuta_res = tareas_mcp.tareas_crear_minuta_borrador(
        str(tok_rw.token),
        str(empresa_a.id_empresa),
        titulo="Minuta vía MCP",
        items_propuestos=[{"titulo": "Validar saldos tesorería", "fecha_vencimiento": "hoy"}],
    )
    conf_res = tareas_mcp.tareas_confirmar_minuta(
        str(tok_rw.token),
        str(empresa_a.id_empresa),
        minuta_id=minuta_res["id_minuta"],
    )
    assert conf_res["estado"] == "CONFIRMADA"
    assert len(conf_res["tareas_creadas"]) == 1

    resumen = tareas_mcp.tareas_resumen_equipo(str(tok_rw.token), str(empresa_a.id_empresa))
    assert resumen["totales"]["completadas"] == 1


def test_tareas_celery_ciclo_empresa_y_todos(empresa_a):
    PlantillaTareaRecurrente.objects.create(
        id_empresa=empresa_a,
        titulo="Revisión apertura de caja",
        frecuencia=PlantillaTareaRecurrente.Frecuencia.DIARIA,
        proxima_ejecucion=date(2020, 1, 1),
    )
    res_emp = ejecutar_ciclo_empresa(str(empresa_a.id_empresa), momento="MANANA")
    assert res_emp["recurrentes_creadas"] == 1

    res_inexistente = ejecutar_ciclo_empresa("00000000-0000-0000-0000-000000000000")
    assert res_inexistente["omitida"] is True

    res_todos = ejecutar_ciclo_todos(momento="AUTO")
    assert res_todos["empresas_procesadas"] >= 1
    assert res_todos["errores"] == 0
    assert Tarea.objects.filter(id_empresa=empresa_a).count() == 1
