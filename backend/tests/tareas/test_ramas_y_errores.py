"""Cobertura exhaustiva de ramas de negocio, casos borde, filtros REST y errores MCP de ``apps/tareas``."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import CapabilityToken, Usuarios
from apps.tareas import mcp as tareas_mcp
from apps.tareas import services
from apps.tareas.models import (
    AreaOperativa,
    ComentarioTarea,
    DependenciaTarea,
    EstadoTarea,
    MiembroAreaOperativa,
    MinutaReunion,
    PlantillaTareaRecurrente,
    RegistroAlertaTarea,
)
from apps.tareas.services.minutas import resolver_fecha_humana

pytestmark = [pytest.mark.django_db]
CARACAS = ZoneInfo("America/Caracas")
BASE = "/api/tareas"


def test_str_y_clean_en_todos_los_modelos(empresa_a, empresa_b, user_a, user_b):
    area = services.crear_area_operativa(
        empresa=empresa_a, nombre="Finanzas", lider=user_a, miembros=[user_a]
    )
    assert "Finanzas" in str(area)
    miembro = MiembroAreaOperativa.objects.get(area=area, usuario=user_a)
    assert str(user_a.pk) in str(miembro)

    proy = services.crear_proyecto_con_secciones(
        empresa=empresa_a, nombre="Cierre Mensual", area=area, propietario=user_a
    )
    assert str(proy) == "Cierre Mensual"
    sec = proy.secciones.first()
    assert "Pendiente" in str(sec)

    rec = PlantillaTareaRecurrente.objects.create(
        id_empresa=empresa_a,
        titulo="Cuadre diario",
        frecuencia=PlantillaTareaRecurrente.Frecuencia.SEMANAL,
        dias_semana=[0, 4],
        proxima_ejecucion=date(2026, 11, 16),
    )
    rec.full_clean()
    assert "Cuadre diario" in str(rec)

    minuta = services.crear_minuta_borrador(
        empresa=empresa_a,
        titulo="Minuta Finanzas",
        items_propuestos=[{"titulo": "Pagar proveedores"}],
    )
    assert "Minuta Finanzas" in str(minuta)

    t1, _ = services.crear_tarea(
        empresa=empresa_a, titulo="Tarea 1", proyecto=proy, asignado_a=user_a
    )
    t2, _ = services.crear_tarea(empresa=empresa_a, titulo="Tarea 2", proyecto=proy)
    assert "Tarea 1" in str(t1)

    dep = services.agregar_dependencia(empresa=empresa_a, tarea=t2, depende_de=t1)
    assert str(t1.pk) in str(dep)

    com = services.agregar_comentario(tarea=t1, cuerpo="Nota", autor=user_a)
    assert str(t1.pk) in str(com)

    cfg = services.obtener_o_crear_configuracion_seguimiento(empresa_a)
    cfg.full_clean()
    assert str(empresa_a.pk) in str(cfg)

    alerta = RegistroAlertaTarea.objects.create(
        id_empresa=empresa_a, tarea=t1, clave_alerta="test_k", destinatario=user_a
    )
    alerta.full_clean()
    assert "test_k" in str(alerta)

    # Usuario de otra empresa rechazado en clean()
    bad_area = AreaOperativa(id_empresa=empresa_a, nombre="X", slug="x", lider=user_b)
    with pytest.raises(ValidationError):
        bad_area.full_clean()

    # Autoreferencia subtarea y dependencia
    t1.tarea_padre = t1
    with pytest.raises(ValidationError):
        t1.full_clean()
    t1.tarea_padre = None

    bad_dep = DependenciaTarea(id_empresa=empresa_a, tarea=t1, depende_de=t1)
    with pytest.raises(ValidationError):
        bad_dep.full_clean()

    bad_com = ComentarioTarea(id_empresa=empresa_b, tarea=t1, cuerpo="Fuga")
    with pytest.raises(ValidationError):
        bad_com.full_clean()

    # Superusuario Omni permitido en cualquier empresa
    su = Usuarios.objects.create_user(
        username="super_omni_test", password="TestPassword123!", es_superusuario_omni=True
    )
    cfg.gerente = su
    cfg.full_clean()


def test_recurrencia_semanal_quincenal_errores_de_hora_y_frecuencia(empresa_a):
    # Semanal con días específicos: lunes(0) -> viernes(4)
    sig_sem = services.calcular_siguiente_fecha(
        frecuencia=PlantillaTareaRecurrente.Frecuencia.SEMANAL,
        actual=date(2026, 11, 16),  # lunes
        dias_semana=[0, 4],
    )
    assert sig_sem == date(2026, 11, 20)  # viernes

    # Semanal sin lista -> +7 días
    sig_sem_7 = services.calcular_siguiente_fecha(
        frecuencia=PlantillaTareaRecurrente.Frecuencia.SEMANAL,
        actual=date(2026, 11, 16),
        dias_semana=[],
    )
    assert sig_sem_7 == date(2026, 11, 23)

    # Quincenal -> +14 días; Mensual diciembre -> enero año siguiente
    assert services.calcular_siguiente_fecha(
        frecuencia=PlantillaTareaRecurrente.Frecuencia.QUINCENAL,
        actual=date(2026, 11, 1),
    ) == date(2026, 11, 15)
    assert services.calcular_siguiente_fecha(
        frecuencia=PlantillaTareaRecurrente.Frecuencia.MENSUAL,
        actual=date(2026, 12, 15),
    ) == date(2027, 1, 15)

    with pytest.raises(services.TareaError):
        services.calcular_siguiente_fecha(frecuencia="ANUAL", actual=date(2026, 11, 16))

    PlantillaTareaRecurrente.objects.create(
        id_empresa=empresa_a,
        titulo="Hora mala",
        frecuencia=PlantillaTareaRecurrente.Frecuencia.INTRADIA,
        horas_dia=["25:99"],
        proxima_ejecucion=date(2026, 11, 16),
    )
    with pytest.raises(services.TareaError):
        services.generar_tareas_recurrentes_pendientes(
            empresa_a, fecha_hoy=date(2026, 11, 16)
        )


def test_escalacion_recurrentes_y_tramos_intermedios_24h_48h(empresa_a, user_a):
    # Preventivos de recurrentes (mensual/quincenal/semanal/diaria)
    assert len(
        services.evaluar_alertas_tarea(
            fecha_creacion=date(2026, 11, 1),
            fecha_vencimiento=date(2026, 11, 16),
            ahora_local=datetime(2026, 11, 1, 9, 0, tzinfo=CARACAS),
            frecuencia_recurrente="MENSUAL",
        )
    ) == 1
    assert len(
        services.evaluar_alertas_tarea(
            fecha_creacion=date(2026, 11, 9),
            fecha_vencimiento=date(2026, 11, 16),
            ahora_local=datetime(2026, 11, 9, 9, 0, tzinfo=CARACAS),
            frecuencia_recurrente="QUINCENAL",
        )
    ) == 1
    assert len(
        services.evaluar_alertas_tarea(
            fecha_creacion=date(2026, 11, 13),
            fecha_vencimiento=date(2026, 11, 16),
            ahora_local=datetime(2026, 11, 13, 9, 0, tzinfo=CARACAS),
            frecuencia_recurrente="SEMANAL",
        )
    ) == 1
    assert (
        services.evaluar_alertas_tarea(
            fecha_creacion=date(2026, 11, 16),
            fecha_vencimiento=None,
            ahora_local=datetime(2026, 11, 16, 9, 0, tzinfo=CARACAS),
        )
        == []
    )

    # Tarde del mismo día en tarea corta (plazo <= 1d) -> recordatorio_tarde_0d
    acc_0d = services.evaluar_alertas_tarea(
        fecha_creacion=date(2026, 11, 16),
        fecha_vencimiento=date(2026, 11, 16),
        ahora_local=datetime(2026, 11, 16, 15, 30, tzinfo=CARACAS),
    )
    assert [a.clave_alerta for a in acc_0d] == ["recordatorio_tarde_0d"]

    # Mañana del día siguiente (-1d) y 26h vencida -> vencida_manana_1d + escalacion_24h
    acc_1d = services.evaluar_alertas_tarea(
        fecha_creacion=date(2026, 11, 10),
        fecha_vencimiento=date(2026, 11, 15),
        ahora_local=datetime(2026, 11, 16, 9, 0, tzinfo=CARACAS),
        momento="MANANA",
    )
    assert [a.clave_alerta for a in acc_1d] == ["vencida_manana_1d"]

    acc_50h = services.evaluar_alertas_tarea(
        fecha_creacion=date(2026, 11, 10),
        fecha_vencimiento=date(2026, 11, 14),
        ahora_local=datetime(2026, 11, 16, 20, 30, tzinfo=CARACAS),
        alertas_ya_enviadas={"escalacion_24h"},
    )
    assert [a.clave_alerta for a in acc_50h] == ["escalacion_48h"]

    # Zona horaria inválida cae a America/Caracas sin explotar
    cfg = services.obtener_o_crear_configuracion_seguimiento(empresa_a)
    cfg.zona_horaria = "Zona/Inexistente"
    cfg.save()
    services.crear_tarea(
        empresa=empresa_a,
        titulo="Vencida ayer",
        asignado_a=user_a,
        fecha_vencimiento=date(2026, 11, 15),
    )
    res = services.ejecutar_seguimiento_empresa(
        empresa_a,
        ahora=datetime(2026, 11, 16, 9, 0, tzinfo=CARACAS),
        momento="MANANA",
    )
    assert res["alertas_emitidas"] >= 1


def test_minutas_fechas_relativas_y_casos_borde(empresa_a, user_a):
    hoy = date(2026, 11, 16)  # lunes
    assert resolver_fecha_humana("hoy", hoy=hoy) == hoy
    assert resolver_fecha_humana("pasado mañana", hoy=hoy) == date(2026, 11, 18)
    assert resolver_fecha_humana("próxima semana", hoy=hoy) == date(2026, 11, 23)
    assert resolver_fecha_humana("viernes", hoy=hoy) == date(2026, 11, 20)
    assert resolver_fecha_humana("sin fecha", hoy=hoy) is None

    area = services.crear_area_operativa(
        empresa=empresa_a, nombre="Ventas", miembros=[user_a]
    )
    borrador = services.enriquecer_borrador_minuta(
        empresa_a,
        [
            {"titulo": ""},
            {
                "titulo": "Enviar cotización cliente nuevo",
                "area": area.slug,
                "prioridad": "INVALIDA",
            },
        ],
        fecha_referencia=hoy,
    )
    assert len(borrador) == 1
    assert borrador[0]["asignado_a_id"] == str(user_a.pk)
    assert borrador[0]["prioridad"] == "MEDIA"

    minuta_vacia = services.crear_minuta_borrador(empresa=empresa_a, titulo="Vacía")
    with pytest.raises(services.TareaError):
        services.confirmar_minuta(minuta=minuta_vacia)

    minuta_vacia.estado = MinutaReunion.Estado.DESCARTADA
    minuta_vacia.save()
    with pytest.raises(services.TareaError):
        services.confirmar_minuta(minuta=minuta_vacia)


def test_endpoints_filtros_validaciones_y_mcp_ramas_error(empresa_a, user_a, client_a):
    proy = services.crear_proyecto_con_secciones(
        empresa=empresa_a, nombre="Tablero Ventas", propietario=user_a
    )
    t1, _ = services.crear_tarea(
        empresa=empresa_a,
        titulo="Bloqueada manual",
        proyecto=proy,
        asignado_a=user_a,
        fecha_vencimiento=date(2020, 1, 1),
    )
    # Bloquear y desbloquear vía cambiar-estado
    r_bloq = client_a.post(
        f"{BASE}/items/{t1.id_tarea}/cambiar-estado/",
        {"estado": EstadoTarea.BLOQUEADA, "motivo": "Falta RIF"},
        format="json",
    )
    assert r_bloq.status_code == 200
    assert r_bloq.data["motivo_bloqueo"] == "Falta RIF"

    r_desbloq = client_a.post(
        f"{BASE}/items/{t1.id_tarea}/cambiar-estado/",
        {"estado": EstadoTarea.EN_EJECUCION},
        format="json",
    )
    assert r_desbloq.data["motivo_bloqueo"] == ""

    # Filtros de listado + UUID inválido en query params devuelve lista vacía sin 500
    assert (
        client_a.get(
            f"{BASE}/items/?estado=EN_EJECUCION&prioridad=MEDIA&vencidas=true&vencimiento_desde=2019-01-01&vencimiento_hasta=2025-01-01"
        ).data["count"]
        == 1
    )
    assert client_a.get(f"{BASE}/items/?proyecto=no-es-uuid").data["results"] == []
    assert client_a.get(f"{BASE}/secciones/?proyecto=no-es-uuid").data["results"] == []
    assert client_a.get(f"{BASE}/proyectos/?archivado=false").data["count"] >= 1
    assert client_a.get(f"{BASE}/proyectos/?archivado=true").data["count"] == 0

    # Ejecutar seguimiento desde endpoint REST y listar bitácora de alertas
    assert (
        client_a.post(
            f"{BASE}/seguimiento/ejecutar/", {"momento": "INVALIDO"}, format="json"
        ).status_code
        == 400
    )
    r_seg = client_a.post(
        f"{BASE}/seguimiento/ejecutar/", {"momento": "TARDE"}, format="json"
    )
    assert r_seg.status_code == 200
    assert client_a.get(f"{BASE}/alertas/").status_code == 200

    # Errores de entrada en endpoints
    area = services.crear_area_operativa(
        empresa=empresa_a, nombre="Soporte", miembros=[user_a]
    )
    assert (
        client_a.post(
            f"{BASE}/areas/{area.id_area}/miembros/",
            {"usuarios": "no-lista"},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client_a.post(
            f"{BASE}/areas/{area.id_area}/miembros/",
            {"usuarios": ["uuid-invalido"]},
            format="json",
        ).status_code
        == 400
    )
    # Quitar miembro deja lista vacía (soft delete del miembro previo)
    r_vacio = client_a.post(
        f"{BASE}/areas/{area.id_area}/miembros/", {"usuarios": []}, format="json"
    )
    assert r_vacio.status_code == 200
    assert r_vacio.data["miembros"] == []
    # Reagregar restaura el miembro inactivo
    r_rest = client_a.post(
        f"{BASE}/areas/{area.id_area}/miembros/",
        {"usuarios": [str(user_a.pk)]},
        format="json",
    )
    assert len(r_rest.data["miembros"]) == 1

    assert (
        client_a.patch(
            f"{BASE}/configuracion/", {"gerente": "no-uuid"}, format="json"
        ).status_code
        == 400
    )

    # MCP ramas de error controlado
    tok = CapabilityToken.objects.create(
        empresa=empresa_a, creado_por=user_a, scopes=["tareas:read", "tareas:write"]
    )
    with pytest.raises(PermissionError):
        tareas_mcp.tareas_listar(str(tok.token), "no-es-uuid")

    fake_uuid = str(uuid.uuid4())
    assert "error" in tareas_mcp.tareas_crear(
        str(tok.token), str(empresa_a.id_empresa), titulo="X", asignado_a_id=fake_uuid
    )
    assert "error" in tareas_mcp.tareas_crear(
        str(tok.token), str(empresa_a.id_empresa), titulo="X", area_id=fake_uuid
    )
    assert "error" in tareas_mcp.tareas_crear(
        str(tok.token), str(empresa_a.id_empresa), titulo="X", proyecto_id=fake_uuid
    )
    assert "error" in tareas_mcp.tareas_cambiar_estado(
        str(tok.token),
        str(empresa_a.id_empresa),
        tarea_id=fake_uuid,
        nuevo_estado="COMPLETADA",
    )
    assert "error" in tareas_mcp.tareas_confirmar_minuta(
        str(tok.token), str(empresa_a.id_empresa), minuta_id=fake_uuid
    )


def test_cobertura_completa_endpoints_proyectos_errores_mcp_y_tasks(
    empresa_a, empresa_b, user_a, client_a, monkeypatch
):
    fake_uuid = str(uuid.uuid4())
    area = services.crear_area_operativa(empresa=empresa_a, nombre="Calidad", lider=user_a)

    # POST /proyectos/ (éxito y área inexistente 400 por PrimaryKeyRelatedField)
    assert (
        client_a.post(
            f"{BASE}/proyectos/",
            {"nombre": "P1", "area": fake_uuid},
            format="json",
        ).status_code
        == 400
    )
    r_proy = client_a.post(
        f"{BASE}/proyectos/",
        {
            "nombre": "Plan Calidad Q4",
            "descripcion": "Auditorías internas",
            "area": str(area.id_area),
            "vista_predeterminada": "LISTA",
        },
        format="json",
    )
    assert r_proy.status_code == 201
    proy_id = str(r_proy.data["id_proyecto"])

    # Crear sección manual vía POST /secciones/
    r_sec = client_a.post(
        f"{BASE}/secciones/",
        {"proyecto": proy_id, "nombre": "Backlog", "orden": 9},
        format="json",
    )
    assert r_sec.status_code == 201

    # mi-tablero con CapabilityToken sin indicar usuario responde 400
    from rest_framework.test import APIClient

    tok = CapabilityToken.objects.create(
        empresa=empresa_a, creado_por=user_a, scopes=["tareas:read", "tareas:write"]
    )
    cli_bot = APIClient()
    cli_bot.credentials(HTTP_X_CAPABILITY_TOKEN=str(tok.token))
    assert cli_bot.post(f"{BASE}/proyectos/mi-tablero/", {}, format="json").status_code == 400
    assert (
        cli_bot.post(
            f"{BASE}/proyectos/mi-tablero/", {"usuario": str(user_a.pk)}, format="json"
        ).status_code
        == 200
    )

    # Errores de dominio y 404 en TareaViewSet, MinutaViewSet y servicios
    assert (
        client_a.post(
            f"{BASE}/items/", {"titulo": "   "}, format="json"
        ).status_code
        == 400
    )
    assert (
        client_a.post(
            f"{BASE}/items/", {"titulo": "X", "area": fake_uuid}, format="json"
        ).status_code
        == 400
    )
    assert (
        client_a.post(
            f"{BASE}/items/", {"titulo": "X", "tarea_padre": fake_uuid}, format="json"
        ).status_code
        == 400
    )
    t_ok = client_a.post(
        f"{BASE}/items/",
        {"titulo": "Auditar lote", "proyecto": proy_id},
        format="json",
    ).data
    tid = str(t_ok["id_tarea"])

    assert (
        client_a.post(
            f"{BASE}/items/{tid}/mover/", {"seccion": fake_uuid}, format="json"
        ).status_code
        == 404
    )
    assert (
        client_a.post(
            f"{BASE}/items/{tid}/dependencias/", {"depende_de": fake_uuid}, format="json"
        ).status_code
        == 404
    )
    assert (
        client_a.post(
            f"{BASE}/items/{tid}/comentarios/", {"cuerpo": "   "}, format="json"
        ).status_code
        == 400
    )
    assert (
        client_a.post(
            f"{BASE}/minutas/",
            {"titulo": "Minuta doc malo", "documento_adjunto": fake_uuid},
            format="json",
        ).status_code
        == 400
    )
    min_b = services.crear_minuta_borrador(
        empresa=empresa_a,
        titulo="Minuta parcial",
        items_propuestos=[
            {
                "titulo": "Verificar calibración",
                "asignado_a_id": str(user_a.pk),
                "fecha_vencimiento": "2026-11-28",
            },
            {
                "titulo": "Revisar certificado",
                "asignado_nombre": user_a.username[:4],
            },
        ],
    )
    assert (
        client_a.post(
            f"{BASE}/minutas/{min_b.id_minuta}/confirmar/",
            {"proyecto": fake_uuid},
            format="json",
        ).status_code
        == 404
    )

    # Restauración de dependencia desactivada y errores directos de servicios
    from apps.tareas.models import Tarea
    from apps.tareas.services.proyectos import slugificar_area

    t2, _ = services.crear_tarea(empresa=empresa_a, titulo="Previa")
    dep = services.agregar_dependencia(
        empresa=empresa_a, tarea=Tarea.objects.get(pk=tid), depende_de=t2
    )
    dep.soft_delete()
    dep_rest = services.agregar_dependencia(
        empresa=empresa_a, tarea=Tarea.objects.get(pk=tid), depende_de=t2
    )
    assert dep_rest.activo is True

    with pytest.raises(services.TareaError):
        slugificar_area("!!!")
    with pytest.raises(services.TareaError):
        services.crear_area_operativa(empresa=empresa_a, nombre="   ")
    with pytest.raises(services.TareaError):
        services.crear_proyecto_con_secciones(empresa=empresa_a, nombre="   ")
    with pytest.raises(services.TareaError):
        services.cambiar_estado_tarea(tarea=t2, nuevo_estado="NO_EXISTE")

    # Filtros adicionales en MCP tareas_listar y ramas TareaError en MCP
    ent_uuid = str(uuid.uuid4())
    tareas_mcp.tareas_crear(
        str(tok.token),
        str(empresa_a.id_empresa),
        titulo="Enlazada MCP",
        asignado_a_id=str(user_a.pk),
        entidad_tipo="ventas.Pedido",
        entidad_id=ent_uuid,
    )
    filtradas = tareas_mcp.tareas_listar(
        str(tok.token),
        str(empresa_a.id_empresa),
        asignado_a_id=str(user_a.pk),
        entidad_tipo="ventas.Pedido",
        entidad_id=ent_uuid,
    )
    assert len(filtradas) == 1
    assert "error" in tareas_mcp.tareas_crear(
        str(tok.token), str(empresa_a.id_empresa), titulo="   "
    )
    assert "error" in tareas_mcp.tareas_cambiar_estado(
        str(tok.token),
        str(empresa_a.id_empresa),
        tarea_id=tid,
        nuevo_estado="ESTADO_MALO",
    )
    assert "error" in tareas_mcp.tareas_crear_minuta_borrador(
        str(tok.token),
        str(empresa_a.id_empresa),
        titulo="   ",
        items_propuestos=[],
    )

    # Resiliencia de ejecutar_ciclo_todos ante fallo aislado en una empresa
    from apps.tareas import tasks as tareas_tasks

    def _fallar_una(emp_id: str, momento: str = "AUTO"):
        if emp_id == str(empresa_b.id_empresa):
            raise RuntimeError("Fallo simulado")
        return {"ok": True}

    monkeypatch.setattr(tareas_tasks, "ejecutar_ciclo_empresa", _fallar_una)
    res_lote = tareas_tasks.ejecutar_ciclo_todos("MANANA")
    assert res_lote["errores"] == 1
    assert res_lote["empresas_procesadas"] >= 1


def test_validaciones_cruzadas_en_servicios_proyectos(empresa_a, empresa_b, user_a, user_b):
    area_a = services.crear_area_operativa(empresa=empresa_a, nombre="Legal")
    proy_b = services.crear_proyecto_con_secciones(empresa=empresa_b, nombre="B")
    sec_b = proy_b.secciones.first()

    # Cross-tenant en crear_area_operativa y sincronizar_miembros_area
    with pytest.raises(services.TareaError):
        services.crear_area_operativa(empresa=empresa_a, nombre="MalLider", lider=user_b)
    with pytest.raises(services.TareaError):
        services.sincronizar_miembros_area(empresa=empresa_b, area=area_a, usuarios=[])
    with pytest.raises(services.TareaError):
        services.sincronizar_miembros_area(
            empresa=empresa_a, area=area_a, usuarios=[user_b]
        )

    # Validación y unicidad de proyecto personal en crear_proyecto_con_secciones
    with pytest.raises(services.TareaError):
        services.crear_proyecto_con_secciones(
            empresa=empresa_a, nombre="Sin dueño", es_personal=True
        )
    services.crear_proyecto_con_secciones(
        empresa=empresa_a, nombre="Personal 1", es_personal=True, propietario=user_a
    )
    with pytest.raises(services.TareaError):
        services.crear_proyecto_con_secciones(
            empresa=empresa_a, nombre="Personal 2", es_personal=True, propietario=user_a
        )
    with pytest.raises(services.TareaError):
        services.crear_proyecto_con_secciones(
            empresa=empresa_a,
            nombre="Sección inválida",
            secciones=[("Sec", "ESTADO_INEXISTENTE")],
        )

    # crear_tarea con sección explícita sin proyecto y fallback de sección cuando estado no tiene columna
    proy_a = services.crear_proyecto_con_secciones(
        empresa=empresa_a,
        nombre="Simple",
        secciones=[("Por hacer", EstadoTarea.PENDIENTE), ("Hecho", EstadoTarea.COMPLETADA)],
    )
    sec_hecho = proy_a.secciones.filter(estado_destino=EstadoTarea.COMPLETADA).first()
    t_sec, _ = services.crear_tarea(
        empresa=empresa_a, titulo="Directo a sección", seccion=sec_hecho
    )
    assert t_sec.proyecto_id == proy_a.id_proyecto

    t_fallback, _ = services.crear_tarea(
        empresa=empresa_a,
        titulo="Estado sin columna dedicada",
        proyecto=proy_a,
        estado=EstadoTarea.EN_REVISION,
    )
    assert t_fallback.seccion_id is not None

    # mover_tarea desde COMPLETADA limpia completada_en; cross-tenant falla
    services.mover_tarea(tarea=t_fallback, seccion_destino=sec_hecho)
    assert t_fallback.completada_en is not None
    sec_pend = proy_a.secciones.filter(estado_destino=EstadoTarea.PENDIENTE).first()
    services.mover_tarea(tarea=t_fallback, seccion_destino=sec_pend)
    assert t_fallback.completada_en is None

    with pytest.raises(services.TareaError):
        services.mover_tarea(tarea=t_fallback, seccion_destino=sec_b)

    t_b, _ = services.crear_tarea(empresa=empresa_b, titulo="Ajena")
    with pytest.raises(services.TareaError):
        services.agregar_dependencia(empresa=empresa_a, tarea=t_fallback, depende_de=t_b)


