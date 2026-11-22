"""
Tests de integración para reglas departamentales, SLA en horas, escalación periódica
aislada por tenant (RLS fail-closed) y API REST de ``gestion_aprobaciones`` (Plan 08 §B.2).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
import uuid

import pytest
from django.conf import settings
from django.db import connection
from django.test import override_settings
from django.utils import timezone

from apps.core import rls
from apps.core.models import Departamento, Notificacion, Roles, UsuarioRoles, Usuarios
from apps.gestion_aprobaciones.models import FlujoAprobacion, SolicitudAprobacion, TipoAprobacion
from apps.gestion_aprobaciones.services import (
    APROBADA,
    PENDIENTE,
    RECHAZADA,
    AprobacionError,
    crear_solicitud,
    escalar_solicitudes_vencidas,
    evaluar_etapas,
    registrar_decision,
)
from apps.gestion_aprobaciones.tasks import escalar_solicitudes_vencidas as tarea_escalar_sla

pytestmark = [pytest.mark.django_db]


class _DocDummy:
    nombre_modelo_aprobacion = "OrdenCompra"

    def __init__(self, doc_pk=None):
        self.pk = doc_pk or uuid.uuid4()


def _crear_usuario_empresa(username: str, empresa):
    u = Usuarios.objects.create_user(username=username, password="x")
    u.empresas.add(empresa)
    return u


class TestReglasDepartamentalesYMultiEtapa:
    def test_prioriza_etapas_departamentales_y_cae_a_general(self, empresa_a, empresa_b, user_a):
        dep_it = Departamento.objects.create(id_empresa=empresa_a, nombre_departamento="IT")
        dep_rrhh = Departamento.objects.create(id_empresa=empresa_a, nombre_departamento="RRHH")
        dep_b = Departamento.objects.create(id_empresa=empresa_b, nombre_departamento="IT B")

        tipo = TipoAprobacion.objects.create(
            id_empresa=empresa_a,
            codigo_tipo="ORDEN_COMPRA",
            nombre_tipo="OC",
            modulo_origen="compras",
            activo=True,
        )
        # Flujo general (sin departamento): umbral >= 100
        FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            id_departamento=None,
            orden_etapa=1,
            nombre_etapa="General L1",
            monto_minimo=Decimal("100.00"),
            activo=True,
        )
        # Flujo departamental para IT: 2 etapas desde monto 500
        rol_it_1 = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Líder IT")
        rol_it_2 = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Director IT")
        e_it_1 = FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            id_departamento=dep_it,
            orden_etapa=1,
            nombre_etapa="IT Etapa 1",
            rol_aprobador=rol_it_1,
            monto_minimo=Decimal("500.00"),
            sla_horas=2,
            activo=True,
        )
        e_it_2 = FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            id_departamento=dep_it,
            orden_etapa=2,
            nombre_etapa="IT Etapa 2",
            rol_aprobador=rol_it_2,
            monto_minimo=Decimal("500.00"),
            sla_horas=6,
            activo=True,
        )

        # Para IT con monto 200: existe flujo IT (>= 500), por lo tanto NO cae al flujo general (>= 100)
        assert evaluar_etapas(empresa_a, "ORDEN_COMPRA", Decimal("200.00"), departamento=dep_it) == []
        # Para IT con monto 800: usa exclusivamente las etapas de IT
        etapas_it = evaluar_etapas(empresa_a, "ORDEN_COMPRA", Decimal("800.00"), departamento=dep_it)
        assert [e.pk for e in etapas_it] == [e_it_1.pk, e_it_2.pk]
        # Para RRHH (sin etapas configuradas): cae al flujo general
        etapas_rrhh = evaluar_etapas(empresa_a, "ORDEN_COMPRA", Decimal("200.00"), departamento=dep_rrhh)
        assert [e.nombre_etapa for e in etapas_rrhh] == ["General L1"]
        # Departamento de otra empresa -> error explícito
        with pytest.raises(AprobacionError, match="departamento no pertenece"):
            evaluar_etapas(empresa_a, "ORDEN_COMPRA", Decimal("200.00"), departamento=dep_b)

        # Flujo multi-etapa resetea reloj SLA y escalada al avanzar de etapa
        u_it1 = _crear_usuario_empresa("aprob_it_1", empresa_a)
        u_it2 = _crear_usuario_empresa("aprob_it_2", empresa_a)
        UsuarioRoles.objects.create(id_usuario=u_it1, id_rol=rol_it_1)
        UsuarioRoles.objects.create(id_usuario=u_it2, id_rol=rol_it_2)

        doc = _DocDummy()
        sol = crear_solicitud(doc, empresa_a, user_a, "ORDEN_COMPRA", Decimal("900.00"), departamento=dep_it)
        assert sol.etapa_actual_flujo_id == e_it_1.pk
        assert sol.id_departamento_id == dep_it.pk

        # Simulamos que etapa 1 había vencido y escalado
        t_viejo = timezone.now() - timedelta(hours=5)
        SolicitudAprobacion.objects.filter(pk=sol.pk).update(
            fecha_inicio_etapa=t_viejo,
            escalada=True,
            fecha_escalacion=timezone.now(),
        )
        sol.refresh_from_db()

        registrar_decision(sol, u_it1, aprobado=True, comentarios="Avanza a IT 2")
        sol.refresh_from_db()
        assert sol.estado_solicitud == PENDIENTE
        assert sol.etapa_actual_flujo_id == e_it_2.pk
        assert sol.escalada is False
        assert sol.fecha_escalacion is None
        assert sol.fecha_inicio_etapa > t_viejo

        # Rechazo en etapa 2 cierra como RECHAZADA
        registrar_decision(sol, u_it2, aprobado=False, comentarios="Presupuesto insuficiente")
        sol.refresh_from_db()
        assert sol.estado_solicitud == RECHAZADA
        assert sol.etapa_actual_flujo is None


class TestSLAYEscalacionCelery:
    def test_escalacion_autoriza_usuario_y_rol_escalado_y_emite_notificaciones(self, empresa_a, user_a):
        aprob_orig = _crear_usuario_empresa("orig_aprob", empresa_a)
        dest_usuario = _crear_usuario_empresa("esc_user", empresa_a)
        dest_rol_user = _crear_usuario_empresa("esc_rol_user", empresa_a)
        rol_esc = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Gerente Escalación")
        UsuarioRoles.objects.create(id_usuario=dest_rol_user, id_rol=rol_esc)

        tipo = TipoAprobacion.objects.create(
            id_empresa=empresa_a,
            codigo_tipo="GASTO",
            nombre_tipo="Gasto SLA",
            modulo_origen="gastos",
            activo=True,
        )
        etapa_u = FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            orden_etapa=1,
            nombre_etapa="SLA Usuario",
            id_usuario_aprobador=aprob_orig,
            sla_horas=4,
            escalar_a_usuario=dest_usuario,
            activo=True,
        )
        etapa_r = FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            orden_etapa=2,
            nombre_etapa="SLA Rol",
            id_usuario_aprobador=aprob_orig,
            monto_minimo=Decimal("100.00"),
            sla_horas=1,
            escalar_a_rol=rol_esc,
            activo=True,
        )
        etapa_broadcast = FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            orden_etapa=3,
            nombre_etapa="SLA Broadcast",
            id_usuario_aprobador=aprob_orig,
            monto_minimo=Decimal("200.00"),
            sla_horas=1,
            activo=True,
        )

        # Solicitud 1 (etapa_u) aún dentro de SLA
        sol1 = SolicitudAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            id_entidad_origen=uuid.uuid4(),
            nombre_modelo_origen="Gasto",
            id_usuario_solicitante=user_a,
            estado_solicitud=PENDIENTE,
            etapa_actual_flujo=etapa_u,
            monto=Decimal("50.00"),
            fecha_inicio_etapa=timezone.now() - timedelta(hours=2),
        )
        # Antes de escalar, dest_usuario NO puede decidir
        with pytest.raises(AprobacionError, match="aprobador designado"):
            registrar_decision(sol1, dest_usuario, aprobado=True)

        # Solicitud 2 (etapa_r) vencida hace 2h
        sol2 = SolicitudAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            id_entidad_origen=uuid.uuid4(),
            nombre_modelo_origen="Gasto",
            id_usuario_solicitante=user_a,
            estado_solicitud=PENDIENTE,
            etapa_actual_flujo=etapa_r,
            monto=Decimal("150.00"),
            fecha_inicio_etapa=timezone.now() - timedelta(hours=3),
        )
        # Solicitud 3 (etapa_broadcast sin destinatario) vencida
        sol3 = SolicitudAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            id_entidad_origen=uuid.uuid4(),
            nombre_modelo_origen="Gasto",
            id_usuario_solicitante=user_a,
            estado_solicitud=PENDIENTE,
            etapa_actual_flujo=etapa_broadcast,
            monto=Decimal("250.00"),
            fecha_inicio_etapa=timezone.now() - timedelta(hours=3),
        )

        # A las +3h desde inicio de sol1 (no ha llegado a 4h), sol1 no debe escalar; sol2 y sol3 sí
        res = escalar_solicitudes_vencidas()
        assert res["escaladas"] == 2
        assert res["alertas_emitidas"] == 2
        assert res["errores"] == 0

        sol1.refresh_from_db()
        sol2.refresh_from_db()
        sol3.refresh_from_db()
        assert sol1.escalada is False
        assert sol2.escalada is True
        assert sol3.escalada is True

        # Idempotencia: segunda corrida inmediata no re-escala ni duplica notificaciones
        res_dup = escalar_solicitudes_vencidas()
        assert res_dup["escaladas"] == 0

        # dest_rol_user ahora sí puede decidir sol2
        registrar_decision(sol2, dest_rol_user, aprobado=True, comentarios="Atendido por rol escalado")
        sol2.refresh_from_db()
        assert sol2.estado_solicitud == APROBADA

        # Ahora simulamos que pasa el SLA de sol1 (ahora = +5h)
        res_u = escalar_solicitudes_vencidas(ahora=timezone.now() + timedelta(hours=5))
        assert res_u["escaladas"] == 1
        assert Notificacion.objects.filter(id_empresa=empresa_a, id_usuario=dest_usuario).count() == 1
        assert Notificacion.objects.filter(id_empresa=empresa_a, id_usuario__isnull=True).count() == 1

        sol1.refresh_from_db()
        assert sol1.escalada is True
        registrar_decision(sol1, dest_usuario, aprobado=True, comentarios="Atendido por usuario escalado")
        sol1.refresh_from_db()
        assert sol1.estado_solicitud == APROBADA

    def test_escalacion_multi_tenant_con_rls_habilitado_y_tarea_celery(
        self, empresa_a, empresa_b, user_a, user_b, rls_test_role, monkeypatch
    ):
        assert "aprobaciones-escalar-vencidas" in settings.CELERY_BEAT_SCHEDULE
        assert (
            settings.CELERY_BEAT_SCHEDULE["aprobaciones-escalar-vencidas"]["task"]
            == "gestion_aprobaciones.escalar_solicitudes_vencidas"
        )

        tipo_a = TipoAprobacion.objects.create(
            id_empresa=empresa_a, codigo_tipo="T-A", nombre_tipo="Tipo A", modulo_origen="compras"
        )
        tipo_b = TipoAprobacion.objects.create(
            id_empresa=empresa_b, codigo_tipo="T-B", nombre_tipo="Tipo B", modulo_origen="compras"
        )
        etapa_a = FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo_a,
            orden_etapa=1,
            nombre_etapa="E-A",
            sla_horas=1,
            escalar_a_usuario=user_a,
        )
        etapa_b = FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo_b,
            orden_etapa=1,
            nombre_etapa="E-B",
            sla_horas=1,
            escalar_a_usuario=user_b,
        )

        SolicitudAprobacion.objects.create(
            id_tipo_aprobacion=tipo_a,
            id_entidad_origen=uuid.uuid4(),
            nombre_modelo_origen="OrdenCompra",
            id_usuario_solicitante=user_a,
            estado_solicitud=PENDIENTE,
            etapa_actual_flujo=etapa_a,
            monto=Decimal("100.00"),
            fecha_inicio_etapa=timezone.now() - timedelta(hours=3),
        )
        SolicitudAprobacion.objects.create(
            id_tipo_aprobacion=tipo_b,
            id_entidad_origen=uuid.uuid4(),
            nombre_modelo_origen="OrdenCompra",
            id_usuario_solicitante=user_b,
            estado_solicitud=PENDIENTE,
            etapa_actual_flujo=etapa_b,
            monto=Decimal("200.00"),
            fecha_inicio_etapa=timezone.now() - timedelta(hours=3),
        )

        # Ejecutar bajo RLS fail-closed real (sin superusuario PostgreSQL si hay rol no-bypass)
        with override_settings(RLS_ENABLED=True):
            with connection.cursor() as cur:
                if rls_test_role is not None:
                    cur.execute(f'SET ROLE "{rls_test_role}"')
                try:
                    res_task = tarea_escalar_sla()
                finally:
                    rls.apply_system_default()
                    if rls_test_role is not None:
                        cur.execute("RESET ROLE")

        assert res_task["empresas_procesadas"] >= 2
        assert res_task["escaladas"] == 2
        assert res_task["errores"] == 0
        assert Notificacion.objects.filter(id_empresa=empresa_a, id_usuario=user_a).count() == 1
        assert Notificacion.objects.filter(id_empresa=empresa_b, id_usuario=user_b).count() == 1

        # Si crear_notificacion falla, la escalación NO se revierte
        sol_a2 = SolicitudAprobacion.objects.create(
            id_tipo_aprobacion=tipo_a,
            id_entidad_origen=uuid.uuid4(),
            nombre_modelo_origen="OrdenCompra",
            id_usuario_solicitante=user_a,
            estado_solicitud=PENDIENTE,
            etapa_actual_flujo=etapa_a,
            monto=Decimal("300.00"),
            fecha_inicio_etapa=timezone.now() - timedelta(hours=3),
        )
        monkeypatch.setattr(
            "apps.core.models.crear_notificacion", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("SMTP down"))
        )
        res_err_notif = escalar_solicitudes_vencidas()
        sol_a2.refresh_from_db()
        assert res_err_notif["escaladas"] == 1
        assert res_err_notif["alertas_emitidas"] == 0
        assert sol_a2.escalada is True


class TestAprobacionesRestAPIAvanzada:
    def test_flujos_departamentales_sla_validaciones_y_filtros(self, client_a, empresa_a, empresa_b, user_a, user_b):
        dep_a = Departamento.objects.create(id_empresa=empresa_a, nombre_departamento="Operaciones")
        dep_b = Departamento.objects.create(id_empresa=empresa_b, nombre_departamento="Operaciones B")
        rol_a = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Gerente Op")
        rol_b = Roles.objects.create(id_empresa=empresa_b, nombre_rol="Gerente B")
        UsuarioRoles.objects.create(id_usuario=user_a, id_rol=rol_a)

        tipo = TipoAprobacion.objects.create(
            id_empresa=empresa_a, codigo_tipo="OP_A", nombre_tipo="Op A", modulo_origen="compras"
        )

        # Validaciones cross-tenant en FlujoAprobacionSerializer
        for campo, valor in (
            ("id_departamento", str(dep_b.pk)),
            ("rol_aprobador", str(rol_b.pk)),
            ("escalar_a_rol", str(rol_b.pk)),
            ("id_usuario_aprobador", str(user_b.pk)),
            ("escalar_a_usuario", str(user_b.pk)),
        ):
            r_bad = client_a.post(
                "/api/gestion-aprobaciones/flujos-aprobacion/",
                {
                    "id_tipo_aprobacion": str(tipo.pk),
                    "orden_etapa": 1,
                    "nombre_etapa": "E1",
                    campo: valor,
                },
                format="json",
            )
            assert r_bad.status_code == 400, (campo, r_bad.json())
            assert campo in r_bad.json()

        r_rango = client_a.post(
            "/api/gestion-aprobaciones/flujos-aprobacion/",
            {
                "id_tipo_aprobacion": str(tipo.pk),
                "orden_etapa": 1,
                "nombre_etapa": "Rango Bad",
                "monto_minimo": "500.00",
                "monto_maximo": "100.00",
            },
            format="json",
        )
        assert r_rango.status_code == 400

        # Creación válida con departamento, SLA y escalación
        r_ok = client_a.post(
            "/api/gestion-aprobaciones/flujos-aprobacion/",
            {
                "id_tipo_aprobacion": str(tipo.pk),
                "id_departamento": str(dep_a.pk),
                "orden_etapa": 1,
                "nombre_etapa": "Jefe Op",
                "rol_aprobador": str(rol_a.pk),
                "sla_horas": 12,
                "escalar_a_usuario": str(user_a.pk),
                "monto_minimo": "100.00",
                "activo": True,
            },
            format="json",
        )
        assert r_ok.status_code == 201, r_ok.json()
        flujo_id = r_ok.json()["id_flujo_aprobacion"]

        # Crear solicitud por servicio y ejercitar endpoints + filtros + decidir
        sol = crear_solicitud(_DocDummy(), empresa_a, user_a, "OP_A", Decimal("250.00"), departamento=dep_a)
        assert (
            client_a.get(
                f"/api/gestion-aprobaciones/tipos-aprobacion/?id_empresa={empresa_a.pk}&modulo_origen=compras"
            ).status_code
            == 200
        )
        assert (
            client_a.get(
                f"/api/gestion-aprobaciones/flujos-aprobacion/?id_tipo_aprobacion={tipo.pk}&id_departamento={dep_a.pk}"
            ).status_code
            == 200
        )
        assert (
            client_a.get(
                f"/api/gestion-aprobaciones/solicitudes-aprobacion/?id_tipo_aprobacion={tipo.pk}&estado_solicitud=PENDIENTE&escalada=false"
            ).status_code
            == 200
        )
        assert (
            client_a.get(
                f"/api/gestion-aprobaciones/registros-aprobacion/?id_solicitud_aprobacion={sol.pk}"
            ).status_code
            == 200
        )

        # Guarda \x00 y UUID inválido
        assert client_a.get("/api/gestion-aprobaciones/flujos-aprobacion/?id_departamento=bad").status_code == 400
        assert client_a.get("/api/gestion-aprobaciones/flujos-aprobacion/?search=a%00b").status_code == 400
        assert client_a.get("/api/gestion-aprobaciones/flujos-aprobacion/?a%00b=1").status_code == 400
        assert flujo_id is not None

        # Decidir por API validando errores y éxito
        assert (
            client_a.post(
                f"/api/gestion-aprobaciones/solicitudes-aprobacion/{sol.pk}/decidir/", {}, format="json"
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                f"/api/gestion-aprobaciones/solicitudes-aprobacion/{sol.pk}/decidir/",
                {"aprobado": "no-bool"},
                format="json",
            ).status_code
            == 400
        )
        r_dec = client_a.post(
            f"/api/gestion-aprobaciones/solicitudes-aprobacion/{sol.pk}/decidir/",
            {"aprobado": True, "comentarios": "Aprobado vía API"},
            format="json",
        )
        assert r_dec.status_code == 200
        assert r_dec.json()["estado_solicitud"] == "APROBADA"
        assert (
            client_a.post(
                f"/api/gestion-aprobaciones/solicitudes-aprobacion/{sol.pk}/decidir/",
                {"aprobado": False},
                format="json",
            ).status_code
            == 400
        )

    def test_edge_cases_servicio_y_serializer_aprobaciones(self, empresa_a, empresa_b, user_a, user_b, monkeypatch):
        from apps.gestion_aprobaciones.serializers import FlujoAprobacionSerializer
        from apps.gestion_aprobaciones.services import (
            _etapa_aplica,
            _resolver_entidad_uuid,
            _usuario_en_empresa,
            _verificar_aprobador,
        )

        # _resolver_entidad_uuid con PK entero y con cadena no-UUID
        class _DocInt:
            nombre_modelo_aprobacion = "OperacionCambioDivisa"
            pk = 42

        u1 = _resolver_entidad_uuid(_DocInt())
        u2 = _resolver_entidad_uuid(_DocInt())
        assert u1 == u2

        # _usuario_en_empresa superusuario / objeto sin .empresas
        class _DummyAnon:
            pass

        class _DummySuper:
            es_superusuario_omni = True

        assert _usuario_en_empresa(_DummyAnon(), empresa_a.pk) is False
        assert _usuario_en_empresa(_DummySuper(), empresa_a.pk) is True

        # _verificar_aprobador usuario ajeno
        tipo = TipoAprobacion.objects.create(
            id_empresa=empresa_a, codigo_tipo="EDG_1", nombre_tipo="Edge", modulo_origen="compras"
        )
        etapa = FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            orden_etapa=1,
            nombre_etapa="E-Edge",
            sla_horas=1,
        )
        with pytest.raises(AprobacionError, match="no pertenece"):
            _verificar_aprobador(etapa, user_b)

        # _etapa_aplica con monto=None
        assert _etapa_aplica(etapa, None) is True
        etapa_tope = FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            orden_etapa=2,
            nombre_etapa="E-Tope",
            monto_minimo=Decimal("10"),
        )
        assert _etapa_aplica(etapa_tope, None) is False

        # Solicitud pendiente sin etapa actual -> AprobacionError
        sol_sin_etapa = SolicitudAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            id_entidad_origen=uuid.uuid4(),
            nombre_modelo_origen="OrdenCompra",
            id_usuario_solicitante=user_a,
            estado_solicitud=PENDIENTE,
            etapa_actual_flujo=None,
        )
        with pytest.raises(AprobacionError, match="no tiene etapa actual"):
            registrar_decision(sol_sin_etapa, user_a, True)

        # Escalación con usuario inactivo en escalar_a_usuario -> 0 alertas sin fallar
        u_inact = Usuarios.objects.create_user(username="inact_esc", password="x", is_active=False)
        u_inact.empresas.add(empresa_a)
        etapa_inact = FlujoAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            orden_etapa=3,
            nombre_etapa="E-Inact",
            sla_horas=1,
            escalar_a_usuario=u_inact,
        )
        SolicitudAprobacion.objects.create(
            id_tipo_aprobacion=tipo,
            id_entidad_origen=uuid.uuid4(),
            nombre_modelo_origen="OrdenCompra",
            id_usuario_solicitante=user_a,
            estado_solicitud=PENDIENTE,
            etapa_actual_flujo=etapa_inact,
            fecha_inicio_etapa=timezone.now() - timedelta(hours=3),
        )
        res_inact = escalar_solicitudes_vencidas()
        assert res_inact["escaladas"] == 1
        assert res_inact["alertas_emitidas"] == 0

        # FlujoAprobacionSerializer directo cubre validación cross-tenant en serializer.validate()
        dep_b = Departamento.objects.create(id_empresa=empresa_b, nombre_departamento="Dep B Ser")
        rol_b = Roles.objects.create(id_empresa=empresa_b, nombre_rol="Rol B Ser")
        for campo, valor in (
            ("id_departamento", str(dep_b.pk)),
            ("rol_aprobador", str(rol_b.pk)),
            ("escalar_a_rol", str(rol_b.pk)),
            ("id_usuario_aprobador", str(user_b.pk)),
            ("escalar_a_usuario", str(user_b.pk)),
        ):
            ser = FlujoAprobacionSerializer(
                data={"id_tipo_aprobacion": str(tipo.pk), "orden_etapa": 9, "nombre_etapa": "X", campo: valor}
            )
            assert not ser.is_valid()
            assert campo in ser.errors

        # Error por tenant aislado en escalar_solicitudes_vencidas
        monkeypatch.setattr(
            "apps.gestion_aprobaciones.models.SolicitudAprobacion.objects.select_related",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("DB timeout simulado")),
        )
        res_err = escalar_solicitudes_vencidas()
        assert res_err["errores"] >= 1

    def test_patch_flujo_cambiando_solo_tipo_a_subsidiaria_bloquea_corrupcion_fk(
        self, client_a, empresa_a, moneda_usd, user_a
    ):
        """[B-1] PATCH cambiando solo id_tipo_aprobacion a subsidiaria debe rechazar FKs heredados de Matriz."""
        from apps.core.models import Empresa

        sub = Empresa.objects.create(
            nombre_legal="Subsidiaria Aprob S.A.",
            identificador_fiscal="J-77700011-2",
            id_moneda_base=moneda_usd,
            empresa_matriz=empresa_a,
        )
        dep_m = Departamento.objects.create(id_empresa=empresa_a, nombre_departamento="Compras Matriz")
        rol_m = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Rol Matriz")
        tipo_m = TipoAprobacion.objects.create(
            id_empresa=empresa_a, codigo_tipo="OC_MATRIZ", nombre_tipo="OC M", modulo_origen="compras"
        )
        tipo_s = TipoAprobacion.objects.create(
            id_empresa=sub, codigo_tipo="OC_SUB", nombre_tipo="OC S", modulo_origen="compras"
        )

        # Cada uno de los 5 FKs de Matriz debe bloquear al intentar mover la etapa a tipo_sub via PATCH
        for campo, fk_obj in (
            ("id_departamento", dep_m),
            ("rol_aprobador", rol_m),
            ("escalar_a_rol", rol_m),
            ("id_usuario_aprobador", user_a),
            ("escalar_a_usuario", user_a),
        ):
            flujo = FlujoAprobacion.objects.create(
                id_tipo_aprobacion=tipo_m,
                orden_etapa=10,
                nombre_etapa=f"Etapa {campo}",
                **{campo: fk_obj},
            )
            r_patch = client_a.patch(
                f"/api/gestion-aprobaciones/flujos-aprobacion/{flujo.pk}/",
                {"id_tipo_aprobacion": str(tipo_s.pk)},
                format="json",
            )
            assert r_patch.status_code == 400, (campo, r_patch.json())
            assert campo in r_patch.json()
            flujo.refresh_from_db()
            assert flujo.id_tipo_aprobacion_id == tipo_m.pk
