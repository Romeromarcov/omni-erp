"""Cobertura integral PR-27 (Plan 07 — Omni Connect S4: crm.Actividad, Kanban REST y MCP).

Cubre:
- Modelo ``crm.Actividad`` + ``clean()`` cross-tenant (``lead``, ``tareas.Tarea``, ``asignado_a``, ``creado_por``).
- Cobertura PostgreSQL RLS fail-closed para ``crm_actividad`` (``rls_test_role`` + ``rls_tenant_context``).
- Servicios transaccionales (``mover_lead_etapa``, ``completar_actividad``, ``reordenar_etapas_pipeline``, ``crear_lead_crm``, ``registrar_actividad_crm``).
- Endpoints REST ``/api/crm/pipelines/``, ``/api/crm/etapas/``, ``/api/crm/leads/``, ``/api/crm/actividades/``
  (CRUD, filtros, acciones ``asegurar-predeterminado``, ``reordenar-etapas``, ``mover-etapa``, ``completar``,
  ``id_empresa`` inmutable, rechazo ``\\x00``/UUID inválido, aislamiento multi-tenant y R-CODE-8).
- Paridad MCP (5 tools con scopes ``crm:read`` / ``crm:write``, validación cross-tenant, UUIDs y NUL).
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest import mock
import uuid

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, connection, transaction
from django.db.utils import ProgrammingError
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core import mcp_server, rls
from apps.core.models import CapabilityToken, Contacto, Usuarios
from apps.crm import mcp as crm_mcp
from apps.crm.models import Actividad, Cliente, Etapa, Lead, Pipeline
from apps.crm.serializers import ActividadSerializer, LeadSerializer
from apps.crm.services import (
    CrmError,
    asegurar_pipeline_empresa,
    completar_actividad,
    crear_lead_crm,
    mover_lead_etapa,
    registrar_actividad_crm,
    reordenar_etapas_pipeline,
)
from apps.crm.views import ActividadViewSet, EtapaViewSet, LeadViewSet, PipelineViewSet
from apps.tareas.models import Tarea
from tests.connect.builders import crear_etapa, crear_lead, crear_perfil, crear_pipeline, crear_tarjeta

pytestmark = [pytest.mark.django_db]


def _token(empresa, scopes: list[str], *, creado_por=None) -> str:
    tok = CapabilityToken.objects.create(
        empresa=empresa,
        nombre="tok-crm-s4",
        scopes=scopes,
        activo=True,
        creado_por=creado_por,
    )
    return str(tok.token)


# ── 1. Modelo Actividad + PostgreSQL RLS ──────────────────────────────────────


class TestActividadModeloYRls:
    def test_actividad_clean_valida_misma_empresa_en_lead_tarea_y_usuarios(self, empresa_a, empresa_b, user_a, user_b):
        lead_a = crear_lead(empresa_a, propietario=user_a)
        tarea_a = Tarea.objects.create(id_empresa=empresa_a, titulo="Llamar prospecto")
        tarea_b = Tarea.objects.create(id_empresa=empresa_b, titulo="Tarea ajena")
        lead_b = crear_lead(empresa_b, propietario=user_b)

        act_ok = Actividad(
            id_empresa=empresa_a,
            lead=lead_a,
            tipo=Actividad.Tipo.LLAMADA,
            asunto="Seguimiento inicial",
            asignado_a=user_a,
            creado_por=user_a,
            tarea=tarea_a,
        )
        act_ok.full_clean()
        assert str(act_ok) == "LLAMADA · Seguimiento inicial"

        act_bad = Actividad(
            id_empresa=empresa_a,
            lead=lead_b,
            tipo=Actividad.Tipo.CORREO,
            asunto="Cross-tenant",
            asignado_a=user_b,
            creado_por=user_b,
            tarea=tarea_b,
        )
        with pytest.raises(DjangoValidationError) as exc:
            act_bad.full_clean()
        assert {"lead", "tarea"} <= set(exc.value.message_dict)

        act_user_bad = Actividad(
            id_empresa=empresa_a,
            lead=lead_a,
            tipo=Actividad.Tipo.WHATSAPP,
            asunto="Usuario ajeno",
            asignado_a=user_b,
        )
        with pytest.raises(DjangoValidationError) as exc_u:
            act_user_bad.full_clean()
        assert "asignado_a" in exc_u.value.message_dict

        act_tarea_bad = Actividad(
            id_empresa=empresa_a,
            lead=lead_a,
            tipo=Actividad.Tipo.REUNION,
            asunto="Tarea ajena",
            tarea=tarea_b,
        )
        with pytest.raises(DjangoValidationError) as exc_t:
            act_tarea_bad.full_clean()
        assert "tarea" in exc_t.value.message_dict

    @pytest.mark.tenant
    def test_crm_actividad_registrada_en_rls_y_aislada_en_postgresql(
        self, empresa_a, empresa_b, user_a, user_b, rls_test_role
    ):
        assert rls.RLS_TABLES.get("crm_actividad") == "id_empresa_id"
        assert "crm_actividad" not in rls.RLS_SHARED_NULL_TABLES

        lead_a = crear_lead(empresa_a, propietario=user_a)
        lead_b = crear_lead(empresa_b, propietario=user_b)
        act_a = Actividad.objects.create(
            id_empresa=empresa_a,
            lead=lead_a,
            tipo=Actividad.Tipo.NOTA,
            asunto="Nota A",
        )
        act_b = Actividad.objects.create(
            id_empresa=empresa_b,
            lead=lead_b,
            tipo=Actividad.Tipo.NOTA,
            asunto="Nota B",
        )

        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            rls.apply_context([empresa_a.id_empresa], bypass=False)
            assert set(Actividad.objects.values_list("pk", flat=True)) == {act_a.pk}

            rls.apply_context([empresa_b.id_empresa], bypass=False)
            assert set(Actividad.objects.values_list("pk", flat=True)) == {act_b.pk}

            # Sin contexto -> fail-closed (0 filas)
            rls.apply_context([], bypass=False)
            assert Actividad.objects.count() == 0

            # WITH CHECK bloquea insertar/mover fila hacia otra empresa
            rls.apply_context([empresa_a.id_empresa], bypass=False)
            with pytest.raises((IntegrityError, ProgrammingError)), transaction.atomic():
                Actividad.objects.create(
                    id_empresa=empresa_b,
                    lead=lead_b,
                    tipo=Actividad.Tipo.LLAMADA,
                    asunto="Inyección B",
                )
            with pytest.raises((IntegrityError, ProgrammingError)), transaction.atomic():
                Actividad.objects.filter(pk=act_a.pk).update(id_empresa=empresa_b)
        finally:
            rls.apply_system_default()
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")


# ── 2. Servicios transaccionales CRM ──────────────────────────────────────────


class TestServiciosCrm:
    def test_mover_lead_etapa_reordenar_y_completar_actividad(self, empresa_a, empresa_b, user_a, user_b):
        pipeline = asegurar_pipeline_empresa(empresa_a)
        etapas = list(Etapa.objects.filter(pipeline=pipeline, activo=True).order_by("orden"))
        assert len(etapas) == 5

        lead = crear_lead_crm(
            empresa=empresa_a,
            nombre="María",
            apellido="Rojas",
            empresa_nombre="Inversiones Sur",
            email="  Maria.Rojas@Ejemplo.COM ",
            telefono="0414-222-3344",
            propietario=user_a,
        )
        assert lead.email_normalizado == "maria.rojas@ejemplo.com"
        assert lead.telefono_normalizado == "584142223344"
        assert lead.pipeline_id == pipeline.id_pipeline
        assert lead.etapa_id == etapas[0].id_etapa

        # Mover a otra etapa del mismo pipeline
        movido = mover_lead_etapa(lead, etapas[1], user_a)
        assert movido.etapa_id == etapas[1].id_etapa

        # Error si etapa es de otro pipeline en misma empresa
        otro_pipe = crear_pipeline(empresa_a, nombre="Corporativo")
        etapa_otro_pipe = crear_etapa(empresa_a, otro_pipe, nombre="Inicial", orden=1)
        with pytest.raises(CrmError, match="no pertenece al pipeline"):
            mover_lead_etapa(movido, etapa_otro_pipe, user_a)

        # Error si etapa es de otra empresa
        pipe_b = crear_pipeline(empresa_b, nombre="B")
        etapa_b = crear_etapa(empresa_b, pipe_b, nombre="B1", orden=1)
        with pytest.raises(CrmError, match="otra empresa"):
            mover_lead_etapa(movido, etapa_b, user_a)

        # Error si etapa está inactiva
        etapa_inactiva = crear_etapa(empresa_a, pipeline, nombre="Archivada", orden=99, activo=False)
        with pytest.raises(CrmError, match="inactiva"):
            mover_lead_etapa(movido, etapa_inactiva, user_a)

        # Error si usuario sin acceso a la empresa
        with pytest.raises(CrmError, match="no tiene acceso"):
            mover_lead_etapa(movido, etapas[2], user_b)

        # Error si lead está inactivo
        movido.soft_delete()
        with pytest.raises(CrmError, match="lead inactivo"):
            mover_lead_etapa(movido, etapas[2], user_a)
        movido.restore()

        # Reordenar etapas
        invertidas = [e.id_etapa for e in reversed(etapas)]
        ordenadas = reordenar_etapas_pipeline(pipeline, invertidas)
        assert [e.id_etapa for e in ordenadas] == invertidas
        assert [e.orden for e in ordenadas] == [1, 2, 3, 4, 5]

        # Validaciones de reordenar
        with pytest.raises(CrmError, match="duplicadas"):
            reordenar_etapas_pipeline(pipeline, [etapas[0].id_etapa, etapas[0].id_etapa])
        with pytest.raises(CrmError, match="no pertenecen"):
            reordenar_etapas_pipeline(pipeline, [etapa_otro_pipe.id_etapa])
        with pytest.raises(CrmError, match="incluir todas"):
            reordenar_etapas_pipeline(pipeline, [etapas[0].id_etapa])

        pipeline.soft_delete()
        with pytest.raises(CrmError, match="pipeline inactivo"):
            reordenar_etapas_pipeline(pipeline, invertidas)
        pipeline.restore()

        # Registrar y completar/reabrir actividad
        act = registrar_actividad_crm(
            empresa=empresa_a,
            lead=movido,
            tipo=Actividad.Tipo.LLAMADA,
            asunto="Primera llamada",
            descripcion="Solicitó propuesta",
            asignado_a=user_a,
            creado_por=user_a,
        )
        assert act.completada is False and act.fecha_completada is None

        act_done = completar_actividad(act, completada=True, descripcion="Llamada exitosa")
        assert act_done.completada is True
        assert act_done.fecha_completada is not None
        assert act_done.descripcion == "Llamada exitosa"

        act_reopen = completar_actividad(act_done, completada=False)
        assert act_reopen.completada is False
        assert act_reopen.fecha_completada is None

        act_reopen.soft_delete()
        with pytest.raises(CrmError, match="actividad inactiva"):
            completar_actividad(act_reopen, completada=True)

    def test_crear_lead_crm_validaciones_borde(self, empresa_a, empresa_b, user_a):
        with pytest.raises(CrmError, match="nombre"):
            crear_lead_crm(empresa=empresa_a, nombre="   ", propietario=user_a)

        pipe_vacio = crear_pipeline(empresa_a, nombre="Sin etapas")
        with pytest.raises(CrmError, match="no tiene etapas"):
            crear_lead_crm(empresa=empresa_a, nombre="SinEtapa", propietario=user_a, pipeline=pipe_vacio)

        pipe_b = crear_pipeline(empresa_b, nombre="Ajeno")
        with pytest.raises(CrmError, match="no pertenece"):
            crear_lead_crm(empresa=empresa_a, nombre="PipeAjeno", propietario=user_a, pipeline=pipe_b)

        etapa_b = crear_etapa(empresa_b, pipe_b, nombre="EB")
        with pytest.raises(CrmError, match="no pertenece"):
            crear_lead_crm(empresa=empresa_a, nombre="EtapaAjena", propietario=user_a, etapa=etapa_b)

        pipe_a = asegurar_pipeline_empresa(empresa_a)
        pipe_a2 = crear_pipeline(empresa_a, nombre="Otro A")
        etapa_a2 = crear_etapa(empresa_a, pipe_a2, nombre="EA2")
        with pytest.raises(CrmError, match="al pipeline indicado"):
            crear_lead_crm(
                empresa=empresa_a,
                nombre="Mismatch",
                propietario=user_a,
                pipeline=pipe_a,
                etapa=etapa_a2,
            )

        with pytest.raises(CrmError, match="consentimiento"):
            crear_lead_crm(empresa=empresa_a, nombre="Publico", propietario=user_a, fuente=Lead.Fuente.QR)

        with pytest.raises(CrmError, match="texto de consentimiento"):
            crear_lead_crm(
                empresa=empresa_a,
                nombre="Publico2",
                propietario=user_a,
                fuente=Lead.Fuente.QR,
                consentimiento_aceptado=True,
                consentimiento_texto="  ",
            )

        lead_publico = crear_lead_crm(
            empresa=empresa_a,
            nombre="Publico OK",
            propietario=user_a,
            fuente=Lead.Fuente.ENLACE,
            etapa=etapa_a2,
            consentimiento_aceptado=True,
            consentimiento_texto="Acepto",
        )
        assert lead_publico.pipeline_id == pipe_a2.id_pipeline
        assert lead_publico.consentimiento_fecha is not None

        lead_b = crear_lead(empresa_b)
        with pytest.raises(CrmError, match="no existe"):
            registrar_actividad_crm(
                empresa=empresa_a,
                lead=lead_b,
                tipo=Actividad.Tipo.NOTA,
                asunto="Ajeno",
            )
        lead_publico.soft_delete()
        with pytest.raises(CrmError, match="inactivo"):
            registrar_actividad_crm(
                empresa=empresa_a,
                lead=lead_publico,
                tipo=Actividad.Tipo.NOTA,
                asunto="Inactivo",
            )
        lead_publico.restore()
        with pytest.raises(CrmError, match="asunto"):
            registrar_actividad_crm(
                empresa=empresa_a,
                lead=lead_publico,
                tipo=Actividad.Tipo.NOTA,
                asunto="   ",
            )


# ── 3. Endpoints REST Kanban y Actividades ────────────────────────────────────


class TestCrmKanbanActividadesAPI:
    def test_requiere_autenticacion_y_preserva_clientes_existentes(self, api_client, client_a, empresa_a):
        assert api_client.get("/api/crm/pipelines/").status_code == 401
        assert api_client.get("/api/crm/etapas/").status_code == 401
        assert api_client.get("/api/crm/leads/").status_code == 401
        assert api_client.get("/api/crm/actividades/").status_code == 401

        Cliente.objects.create(id_empresa=empresa_a, razon_social="Cliente Preservado C.A.", rif="J-12345678-0")
        resp_cli = client_a.get("/api/crm/clientes/")
        assert resp_cli.status_code == 200
        assert client_a.get("/api/crm/contactos-cliente/").status_code == 200
        assert client_a.get("/api/crm/direcciones-cliente/").status_code == 200

    def test_flujo_api_completo_pipeline_etapas_leads_actividades(self, client_a, empresa_a, user_a):
        # 1) Inicializar pipeline predeterminado vía acción
        r_init = client_a.post("/api/crm/pipelines/asegurar-predeterminado/", {}, format="json")
        assert r_init.status_code == 200, r_init.content
        pipe_id = r_init.data["id_pipeline"]
        assert len(r_init.data["etapas"]) == 5

        # Idempotente + filtro ?empresa=
        r_list_pipes = client_a.get(f"/api/crm/pipelines/?empresa={empresa_a.pk}")
        assert r_list_pipes.status_code == 200
        items_pipe = r_list_pipes.data["results"] if "results" in r_list_pipes.data else r_list_pipes.data
        assert len(items_pipe) == 1

        # Crear pipeline secundario + etapa custom + actualizar + reordenar
        r_pipe2 = client_a.post("/api/crm/pipelines/", {"nombre": "Distribuidores"}, format="json")
        assert r_pipe2.status_code == 201
        pipe2_id = r_pipe2.data["id_pipeline"]
        assert client_a.patch(f"/api/crm/pipelines/{pipe2_id}/", {"nombre": "B2B"}, format="json").status_code == 200

        r_et1 = client_a.post(
            "/api/crm/etapas/",
            {"pipeline": pipe2_id, "nombre": "Prospecto", "orden": 1, "tipo": "ABIERTA"},
            format="json",
        )
        r_et2 = client_a.post(
            "/api/crm/etapas/",
            {"pipeline": pipe2_id, "nombre": "Cierre", "orden": 2, "tipo": "GANADA"},
            format="json",
        )
        assert r_et1.status_code == 201 and r_et2.status_code == 201
        et1_id, et2_id = r_et1.data["id_etapa"], r_et2.data["id_etapa"]
        assert (
            client_a.patch(f"/api/crm/etapas/{et1_id}/", {"nombre": "Prospecto B2B"}, format="json").status_code == 200
        )

        r_et_list = client_a.get(f"/api/crm/etapas/?empresa={empresa_a.pk}&pipeline={pipe2_id}")
        assert r_et_list.status_code == 200

        r_reord = client_a.post(
            f"/api/crm/pipelines/{pipe2_id}/reordenar-etapas/",
            {"etapas": [et2_id, et1_id]},
            format="json",
        )
        assert r_reord.status_code == 200
        assert [e["id_etapa"] for e in r_reord.data["etapas"]] == [et2_id, et1_id]

        # Reordenar inválido devuelve 400 vía domain_error_response
        r_reord_bad = client_a.post(
            f"/api/crm/pipelines/{pipe2_id}/reordenar-etapas/",
            {"etapas": [et2_id]},
            format="json",
        )
        assert r_reord_bad.status_code == 400
        assert "error" in r_reord_bad.data

        # 2) Crear lead manual (auto-asigna pipeline predeterminado si se omite)
        r_lead = client_a.post(
            "/api/crm/leads/",
            {
                "nombre": "Carlos",
                "apellido": "Méndez",
                "empresa_nombre": "Méndez C.A.",
                "email": "  Carlos@Mendez.COM ",
                "telefono": "0412-555-7788",
                "mensaje": "Interesado en plan anual",
            },
            format="json",
        )
        assert r_lead.status_code == 201, r_lead.content
        lead_id = r_lead.data["id_lead"]
        assert r_lead.data["fuente"] == "MANUAL"
        assert str(r_lead.data["pipeline"]) == str(pipe_id)
        assert r_lead.data["email_normalizado"] == "carlos@mendez.com"
        assert r_lead.data["telefono_normalizado"] == "584125557788"

        # PATCH recalcula normalizados
        r_patch_lead = client_a.patch(
            f"/api/crm/leads/{lead_id}/",
            {"email": "  NUEVO@Mendez.COM ", "telefono": "+58 414-000-1122"},
            format="json",
        )
        assert r_patch_lead.status_code == 200
        assert r_patch_lead.data["email_normalizado"] == "nuevo@mendez.com"
        assert r_patch_lead.data["telefono_normalizado"] == "584140001122"

        # Mover de etapa dentro del mismo pipeline
        etapas_default = r_init.data["etapas"]
        r_mover = client_a.post(
            f"/api/crm/leads/{lead_id}/mover-etapa/",
            {"etapa": etapas_default[1]["id_etapa"]},
            format="json",
        )
        assert r_mover.status_code == 200
        assert str(r_mover.data["etapa"]) == str(etapas_default[1]["id_etapa"])
        assert r_mover.data["etapa_nombre"] == "Contactado"

        # Mover a etapa de otro pipeline en misma empresa -> 400 domain_error_response
        r_mover_bad = client_a.post(
            f"/api/crm/leads/{lead_id}/mover-etapa/",
            {"etapa": et1_id},
            format="json",
        )
        assert r_mover_bad.status_code == 400
        assert "pipeline" in r_mover_bad.data["error"].lower()

        # 3) Crear actividades (una vencida, otra completada) + filtros + completar
        vencida_iso = (timezone.now() - timedelta(days=1)).isoformat()
        tarea_a = Tarea.objects.create(id_empresa=empresa_a, titulo="Preparar demo CRM")
        r_act = client_a.post(
            "/api/crm/actividades/",
            {
                "lead": lead_id,
                "tipo": "LLAMADA",
                "asunto": "Llamar para demo",
                "descripcion": "Confirmar horario",
                "fecha_vencimiento": vencida_iso,
                "asignado_a": str(user_a.pk),
                "tarea": str(tarea_a.pk),
            },
            format="json",
        )
        assert r_act.status_code == 201, r_act.content
        act_id = r_act.data["id_actividad"]
        assert r_act.data["completada"] is False
        assert str(r_act.data["creado_por"]) == str(user_a.pk)
        assert r_act.data["asignado_a_nombre"] != ""
        assert r_act.data["lead_nombre"] != ""

        # Lead refleja conteo pendiente y vencida
        r_lead_get = client_a.get(
            f"/api/crm/leads/?empresa={empresa_a.pk}&pipeline={pipe_id}"
            f"&etapa={etapas_default[1]['id_etapa']}&propietario={user_a.pk}&fuente=MANUAL&search=Méndez"
        )
        assert r_lead_get.status_code == 200
        lead_items = r_lead_get.data["results"] if "results" in r_lead_get.data else r_lead_get.data
        assert len(lead_items) == 1
        assert lead_items[0]["actividades_pendientes"] == 1
        assert lead_items[0]["actividades_vencidas"] == 1

        # Filtros de Actividad (incluyendo completada=true/false/invalido)
        assert (
            client_a.get(
                f"/api/crm/actividades/?empresa={empresa_a.pk}&lead={lead_id}"
                f"&asignado_a={user_a.pk}&tipo=LLAMADA&completada=false"
            ).status_code
            == 200
        )
        assert client_a.get(f"/api/crm/actividades/?empresa={empresa_a.pk}&completada=true").status_code == 200
        assert client_a.get("/api/crm/actividades/?completada=invalido").status_code == 400

        # Completar y reabrir vía acción /completar/ y PATCH
        r_comp = client_a.post(
            f"/api/crm/actividades/{act_id}/completar/",
            {"completada": True, "descripcion": "Demo realizada"},
            format="json",
        )
        assert r_comp.status_code == 200
        assert r_comp.data["completada"] is True
        assert r_comp.data["fecha_completada"] is not None
        assert r_comp.data["descripcion"] == "Demo realizada"

        r_patch_act = client_a.patch(
            f"/api/crm/actividades/{act_id}/",
            {"completada": False},
            format="json",
        )
        assert r_patch_act.status_code == 200
        assert r_patch_act.data["completada"] is False
        assert r_patch_act.data["fecha_completada"] is None

        # Soft-delete y reactivar
        assert client_a.delete(f"/api/crm/actividades/{act_id}/").status_code == 204
        assert client_a.get(f"/api/crm/actividades/{act_id}/").status_code == 404
        assert client_a.post(f"/api/crm/actividades/{act_id}/activar/", {}, format="json").status_code == 200
        assert client_a.delete(f"/api/crm/leads/{lead_id}/").status_code == 204
        assert client_a.delete(f"/api/crm/etapas/{et1_id}/").status_code == 204
        assert client_a.delete(f"/api/crm/pipelines/{pipe2_id}/").status_code == 204

    def test_aislamiento_cross_tenant_inmutabilidad_empresa_y_rechazo_nul_uuid(
        self, client_a, client_b, empresa_a, empresa_b, user_a, user_b
    ):
        pipe_a = asegurar_pipeline_empresa(empresa_a)
        etapa_a = Etapa.objects.filter(pipeline=pipe_a).order_by("orden").first()
        lead_a = crear_lead_crm(empresa=empresa_a, nombre="Lead A", propietario=user_a, pipeline=pipe_a, etapa=etapa_a)
        act_a = registrar_actividad_crm(
            empresa=empresa_a,
            lead=lead_a,
            tipo=Actividad.Tipo.NOTA,
            asunto="Privado A",
        )
        tarea_b = Tarea.objects.create(id_empresa=empresa_b, titulo="Tarea B")

        # B no ve ni puede modificar/eliminar recursos de A
        assert client_b.get(f"/api/crm/pipelines/{pipe_a.pk}/").status_code == 404
        assert client_b.get(f"/api/crm/etapas/{etapa_a.pk}/").status_code == 404
        assert client_b.get(f"/api/crm/leads/{lead_a.pk}/").status_code == 404
        assert client_b.patch(f"/api/crm/leads/{lead_a.pk}/", {"nombre": "Hack"}, format="json").status_code == 404
        assert client_b.delete(f"/api/crm/leads/{lead_a.pk}/").status_code == 404
        assert (
            client_b.post(
                f"/api/crm/leads/{lead_a.pk}/mover-etapa/",
                {"etapa": str(etapa_a.pk)},
                format="json",
            ).status_code
            == 404
        )
        assert client_b.get(f"/api/crm/actividades/{act_a.pk}/").status_code == 404
        assert client_b.post(f"/api/crm/actividades/{act_a.pk}/completar/", {}, format="json").status_code == 404
        assert client_b.get(f"/api/crm/pipelines/?empresa={empresa_a.pk}").status_code == 200
        assert (
            client_b.post(f"/api/crm/pipelines/asegurar-predeterminado/?empresa={empresa_a.pk}", {}).status_code == 403
        )

        # B no puede inyectar FKs de A ni A puede inyectar FKs de B
        assert (
            client_a.post(
                "/api/crm/actividades/",
                {"lead": str(lead_a.pk), "asunto": "X", "tarea": str(tarea_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/crm/leads/",
                {"nombre": "X", "propietario": str(user_b.pk)},
                format="json",
            ).status_code
            == 400
        )

        # Incluso si user_a pertenece a ambas empresas, id_empresa es inmutable en UPDATE
        user_a.empresas.add(empresa_b)
        assert (
            client_a.patch(
                f"/api/crm/pipelines/{pipe_a.pk}/",
                {"id_empresa": str(empresa_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.patch(
                f"/api/crm/etapas/{etapa_a.pk}/",
                {"id_empresa": str(empresa_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.patch(
                f"/api/crm/leads/{lead_a.pk}/",
                {"id_empresa": str(empresa_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.patch(
                f"/api/crm/actividades/{act_a.pk}/",
                {"id_empresa": str(empresa_b.pk)},
                format="json",
            ).status_code
            == 400
        )

        # Coherencia cross-FK cuando usuario multi-empresa intenta mezclar empresas visibles
        pipe_b = asegurar_pipeline_empresa(empresa_b)
        etapa_b = Etapa.objects.filter(pipeline=pipe_b).first()
        assert (
            client_a.post(
                "/api/crm/etapas/",
                {"id_empresa": str(empresa_a.pk), "pipeline": str(pipe_b.pk), "nombre": "Cross"},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/crm/leads/",
                {"id_empresa": str(empresa_a.pk), "nombre": "Cross", "pipeline": str(pipe_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/crm/leads/",
                {"id_empresa": str(empresa_a.pk), "nombre": "Cross2", "etapa": str(etapa_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/crm/actividades/",
                {"id_empresa": str(empresa_b.pk), "lead": str(lead_a.pk), "asunto": "Cross"},
                format="json",
            ).status_code
            == 400
        )

        # Validaciones NUL y UUIDs inválidos
        assert client_a.get("/api/crm/leads/no-es-uuid/").status_code == 400
        assert client_a.post("/api/crm/leads/no-es-uuid/activar/", {}).status_code == 400
        assert client_a.get("/api/crm/leads/?search=abc%00def").status_code == 400
        assert client_a.get("/api/crm/leads/?pipeline=no-uuid").status_code == 400
        assert (
            client_a.post(
                "/api/crm/leads/",
                {"nombre": "Bad\x00Name"},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/crm/leads/",
                {"k\x00ey": "val", "nombre": "Ana"},
                format="json",
            ).status_code
            == 400
        )

        # Validaciones de tarjeta/perfil/contacto/consentimiento en LeadSerializer
        perfil_a = crear_perfil(empresa_a, usuario=user_a, slug="lead-perfil-a")
        perfil_b = crear_perfil(empresa_b, usuario=user_b, slug="lead-perfil-b")
        tarjeta_b = crear_tarjeta(empresa_b, perfil=perfil_b, estado="ACTIVA")
        contacto_b = Contacto.objects.create(id_empresa=empresa_b, nombre="Contacto B")
        assert (
            client_a.post(
                "/api/crm/leads/",
                {"id_empresa": str(empresa_a.pk), "nombre": "TarjB", "tarjeta": str(tarjeta_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/crm/leads/",
                {"id_empresa": str(empresa_a.pk), "nombre": "PerfB", "perfil": str(perfil_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/crm/leads/",
                {"id_empresa": str(empresa_a.pk), "nombre": "ContB", "contacto": str(contacto_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        tarjeta_a_otro = crear_tarjeta(empresa_a, perfil=None, estado="INVENTARIO")
        assert (
            client_a.post(
                "/api/crm/leads/",
                {
                    "id_empresa": str(empresa_a.pk),
                    "nombre": "MismatchTarj",
                    "perfil": str(perfil_a.pk),
                    "tarjeta": str(tarjeta_a_otro.pk),
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/crm/leads/",
                {"nombre": "SinConsent", "fuente": "QR"},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/crm/leads/",
                {"nombre": "SinTextoConsent", "fuente": "QR", "consentimiento_aceptado": True},
                format="json",
            ).status_code
            == 400
        )
        r_consent = client_a.post(
            "/api/crm/leads/",
            {
                "id_empresa": str(empresa_a.pk),
                "nombre": "ConConsent",
                "fuente": "QR",
                "consentimiento_aceptado": True,
                "consentimiento_texto": "Acepto política",
            },
            format="json",
        )
        assert r_consent.status_code == 201
        assert r_consent.data["consentimiento_fecha"] is not None

        # Multi-empresa: validaciones cross-FK de segunda capa (LeadSerializer & ActividadSerializer) + espacios vacíos
        assert (
            client_a.post(
                "/api/crm/actividades/",
                {
                    "id_empresa": str(empresa_a.pk),
                    "lead": str(lead_a.pk),
                    "asunto": "CrossTarea2",
                    "tarea": str(tarea_b.pk),
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/crm/actividades/",
                {
                    "id_empresa": str(empresa_a.pk),
                    "lead": str(lead_a.pk),
                    "asunto": "CrossUserB",
                    "asignado_a": str(user_b.pk),
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/crm/leads/",
                {
                    "id_empresa": str(empresa_a.pk),
                    "nombre": "CrossEtapaPipe",
                    "pipeline": str(pipe_a.pk),
                    "etapa": str(etapa_b.pk),
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/crm/leads/",
                {"id_empresa": str(empresa_a.pk), "nombre": "CrossPropB", "propietario": str(user_b.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert client_a.post("/api/crm/pipelines/", {"nombre": "   "}, format="json").status_code == 400
        assert (
            client_a.post("/api/crm/etapas/", {"pipeline": str(pipe_a.pk), "nombre": "   "}, format="json").status_code
            == 400
        )
        assert client_a.post("/api/crm/leads/", {"nombre": "   "}, format="json").status_code == 400
        assert (
            client_a.post(
                "/api/crm/actividades/", {"lead": str(lead_a.pk), "asunto": "   "}, format="json"
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                f"/api/crm/pipelines/asegurar-predeterminado/?empresa={empresa_a.pk}",
                {"id_empresa": str(empresa_a.pk)},
                format="json",
            ).status_code
            == 200
        )

        # Etapa de otro pipeline en la misma empresa + duplicado en _guardar_validado + serialización directa sin anotaciones
        pipe_a_extra = Pipeline.objects.create(id_empresa=empresa_a, nombre="Canal Secundario")
        etapa_a_extra = Etapa.objects.create(id_empresa=empresa_a, pipeline=pipe_a_extra, nombre="Inicio", orden=1)
        assert (
            client_a.post(
                "/api/crm/leads/",
                {
                    "id_empresa": str(empresa_a.pk),
                    "nombre": "CrossEtapaMismaEmpresa",
                    "pipeline": str(pipe_a.pk),
                    "etapa": str(etapa_a_extra.pk),
                },
                format="json",
            ).status_code
            == 400
        )
        # Nombre duplicado de pipeline dispara IntegrityError/ValidationError en _guardar_validado -> HTTP 400
        assert (
            client_a.post(
                "/api/crm/pipelines/",
                {"id_empresa": str(empresa_a.pk), "nombre": "Canal Secundario"},
                format="json",
            ).status_code
            == 400
        )
        lead_ser = LeadSerializer(lead_a).data
        assert isinstance(lead_ser["actividades_pendientes"], int)
        assert isinstance(lead_ser["actividades_vencidas"], int)
        act_ser = ActividadSerializer(act_a).data
        assert act_ser["asignado_a_nombre"] == ""

        # Hallazgos Ronda 1 (#1 y #4):
        # 1) NUL en filtros (?fuente=, ?tipo= en activar) + ?empresa=invalid en POST sin evaluación post-commit
        assert client_a.get("/api/crm/leads/?fuente=a%00b").status_code == 400
        leads_antes = Lead.objects.filter(id_empresa=empresa_a).count()
        assert (
            client_a.post(
                "/api/crm/leads/?fuente=a%00b",
                {"id_empresa": str(empresa_a.pk), "nombre": "NoDebeCrearse"},
                format="json",
            ).status_code
            == 400
        )
        assert Lead.objects.filter(id_empresa=empresa_a).count() == leads_antes

        r_post_invalid_q = client_a.post(
            "/api/crm/leads/?empresa=invalid",
            {"id_empresa": str(empresa_a.pk), "nombre": "LeadConQueryIrrelevante"},
            format="json",
        )
        assert r_post_invalid_q.status_code == 201
        assert r_post_invalid_q.data["actividades_pendientes"] == 0
        assert r_post_invalid_q.data["actividades_vencidas"] == 0

        assert (
            client_a.post(
                f"/api/crm/actividades/{act_a.pk}/activar/?tipo=a%00b",
                {},
                format="json",
            ).status_code
            == 400
        )

        # 4) PATCH/POST rechazando pipeline/etapa/lead con activo=False
        pipe_inactivo = Pipeline.objects.create(id_empresa=empresa_a, nombre="Pipe Inactivo", activo=False)
        etapa_inactiva = Etapa.objects.create(
            id_empresa=empresa_a, pipeline=pipe_a, nombre="Etapa Inactiva", orden=99, activo=False
        )
        lead_inactivo = Lead.objects.create(
            id_empresa=empresa_a,
            nombre="Lead Inactivo",
            pipeline=pipe_a,
            etapa=etapa_a,
            propietario=user_a,
            activo=False,
        )
        assert (
            client_a.patch(
                f"/api/crm/leads/{lead_a.pk}/",
                {"pipeline": str(pipe_inactivo.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.patch(
                f"/api/crm/leads/{lead_a.pk}/",
                {"etapa": str(etapa_inactiva.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.patch(
                f"/api/crm/actividades/{act_a.pk}/",
                {"lead": str(lead_inactivo.pk)},
                format="json",
            ).status_code
            == 400
        )

    def test_viewsets_swagger_fake_view_y_usuario_sin_empresa(self, empresa_a):
        for vs_cls in (PipelineViewSet, EtapaViewSet, LeadViewSet, ActividadViewSet):
            vs = vs_cls()
            vs.swagger_fake_view = True
            assert vs.get_queryset().count() == 0

        sin_emp = Usuarios.objects.create_user(username="crm_sin_emp", password=None)
        client_sin = APIClient()
        client_sin.force_authenticate(user=sin_emp)
        assert client_sin.post("/api/crm/pipelines/", {"nombre": "X"}, format="json").status_code == 403
        assert client_sin.post("/api/crm/pipelines/asegurar-predeterminado/", {}, format="json").status_code == 403
        assert client_sin.post("/api/crm/leads/", {"nombre": "X"}, format="json").status_code == 403


# ── 4. Paridad MCP (5 tools CRM) ─────────────────────────────────────────────


class TestCrmMcpTools:
    def test_mcp_crm_registradas_en_autodiscovery_settings_y_fastmcp(self):
        nombres_esperados = {
            "crm_listar_pipelines",
            "crm_listar_leads",
            "crm_crear_lead",
            "crm_mover_etapa_lead",
            "crm_registrar_actividad",
        }
        assert {item["name"] for item in crm_mcp.MCP_TOOLS} == nombres_esperados
        assert set(mcp_server._DISCOVERED_TOOLS.keys()).issuperset(nombres_esperados)
        assert "apps.crm.mcp" in mcp_server._MCP_DEFAULT_MODULE_PATHS
        assert "apps.crm.mcp" in settings.MCP_AGENT_CAPABILITIES["module_paths"]
        assert {"crm:read", "crm:write"} <= set(settings.MCP_AGENT_CAPABILITIES["scopes"])

        registradas = {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}
        assert nombres_esperados <= registradas

    @pytest.mark.tenant
    def test_mcp_crm_flujo_completo_rls_aislamiento_y_validaciones(
        self, empresa_a, empresa_b, user_a, user_b, rls_test_role
    ):
        tok_read_a = _token(empresa_a, ["crm:read"], creado_por=user_a)
        tok_write_a = _token(empresa_a, ["crm:write"], creado_por=user_a)
        tok_read_b = _token(empresa_b, ["crm:read"], creado_por=user_b)

        # Scopes insuficientes -> PermissionError
        with pytest.raises(PermissionError):
            crm_mcp.crm_listar_pipelines(tok_write_a)
        with pytest.raises(PermissionError):
            crm_mcp.crm_listar_leads(tok_write_a)
        with pytest.raises(PermissionError):
            crm_mcp.crm_crear_lead(tok_read_a, nombre="Sin permiso")
        with pytest.raises(PermissionError):
            crm_mcp.crm_mover_etapa_lead(tok_read_a, lead_id=str(uuid.uuid4()), etapa_id=str(uuid.uuid4()))
        with pytest.raises(PermissionError):
            crm_mcp.crm_registrar_actividad(tok_read_a, lead_id=str(uuid.uuid4()), asunto="Sin permiso")

        # Cross-tenant empresa_id -> PermissionError
        with pytest.raises(PermissionError):
            crm_mcp.crm_listar_pipelines(tok_read_a, empresa_id=str(empresa_b.pk))

        # Validaciones UUID / NUL / fechas inválidas -> ValueError
        with pytest.raises(ValueError, match="UUID"):
            crm_mcp.crm_listar_leads(tok_read_a, pipeline_id="no-uuid")
        with pytest.raises(ValueError, match="inválidos"):
            crm_mcp.crm_listar_leads(tok_read_a, buscar="bad\x00")
        with pytest.raises(ValueError, match="inválidos"):
            crm_mcp.crm_crear_lead(tok_write_a, nombre="Bad\x00")
        with pytest.raises(ValueError, match="UUID"):
            crm_mcp.crm_mover_etapa_lead(tok_write_a, lead_id="bad", etapa_id=str(uuid.uuid4()))
        with pytest.raises(ValueError, match="ISO"):
            crm_mcp.crm_registrar_actividad(
                tok_write_a,
                lead_id=str(uuid.uuid4()),
                asunto="Test",
                fecha_vencimiento="no-fecha",
            )

        # Cross-tenant propietario -> PermissionError
        with pytest.raises(PermissionError):
            crm_mcp.crm_crear_lead(tok_write_a, nombre="Hack", propietario_id=str(user_b.pk))

        pipe_b = asegurar_pipeline_empresa(empresa_b)
        etapa_b = Etapa.objects.filter(pipeline=pipe_b).first()
        lead_b = crear_lead_crm(empresa=empresa_b, nombre="Lead B", propietario=user_b, pipeline=pipe_b, etapa=etapa_b)
        tarea_b = Tarea.objects.create(id_empresa=empresa_b, titulo="Tarea B")

        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            with override_settings(RLS_ENABLED=True):
                # 1) Crear lead en A (auto-crea pipeline predeterminado en A)
                creado = crm_mcp.crm_crear_lead(
                    tok_write_a,
                    empresa_id=str(empresa_a.pk),
                    nombre="Lucía",
                    apellido="Vargas",
                    empresa_nombre="Grupo Vargas",
                    email="lucia@vargas.test",
                    telefono="+584129876543",
                )
                assert creado["nombre"] == "Lucía"
                assert creado["etapa_nombre"] == "Nuevo"
                lead_id = creado["id_lead"]

                # 2) Listar pipelines y leads de A
                pipes_a = crm_mcp.crm_listar_pipelines(tok_read_a)
                assert len(pipes_a) == 1
                assert len(pipes_a[0]["etapas"]) == 5
                etapa_destino_id = pipes_a[0]["etapas"][1]["id_etapa"]

                leads_a = crm_mcp.crm_listar_leads(
                    tok_read_a,
                    pipeline_id=pipes_a[0]["id_pipeline"],
                    fuente="MANUAL",
                    buscar="Lucía",
                )
                assert len(leads_a) == 1
                assert leads_a[0]["id_lead"] == lead_id

                # B no ve leads de A (solo su propio lead B)
                leads_b = crm_mcp.crm_listar_leads(tok_read_b)
                assert [item["id_lead"] for item in leads_b] == [str(lead_b.pk)]

                # 3) Mover etapa lead vía MCP
                movido = crm_mcp.crm_mover_etapa_lead(tok_write_a, lead_id=lead_id, etapa_id=etapa_destino_id)
                assert movido["etapa_id"] == etapa_destino_id
                assert movido["etapa_nombre"] == "Contactado"

                leads_filtrados_etapa = crm_mcp.crm_listar_leads(tok_read_a, etapa_id=etapa_destino_id)
                assert [item["id_lead"] for item in leads_filtrados_etapa] == [lead_id]

                # Crear lead especificando pipeline_id, etapa_id y propietario_id válidos de A
                creado_con_pipe = crm_mcp.crm_crear_lead(
                    tok_write_a,
                    nombre="Pedro",
                    pipeline_id=pipes_a[0]["id_pipeline"],
                    etapa_id=etapa_destino_id,
                    propietario_id=str(user_a.pk),
                )
                assert creado_con_pipe["etapa_id"] == etapa_destino_id

                # Validaciones extra UUID / NUL / vacío en helpers MCP y fallback propietario sin creado_por
                with pytest.raises(ValueError, match="inválidos"):
                    crm_mcp.crm_mover_etapa_lead(tok_write_a, lead_id="ab\x00cd", etapa_id=etapa_destino_id)
                with pytest.raises(ValueError, match="UUID"):
                    crm_mcp.crm_mover_etapa_lead(tok_write_a, lead_id="   ", etapa_id=etapa_destino_id)
                with pytest.raises(ValueError, match="inválidos"):
                    crm_mcp.crm_listar_leads(tok_read_a, pipeline_id="x\x00y")
                assert len(crm_mcp.crm_listar_leads(tok_read_a, pipeline_id="  ")) >= 1

                tok_sin_creador = _token(empresa_a, ["crm:write"], creado_por=None)
                creado_fallback = crm_mcp.crm_crear_lead(tok_sin_creador, nombre="FallbackProp")
                assert creado_fallback["nombre"] == "FallbackProp"

                # Segundo pipeline en A para probar error de transición cross-pipeline vía MCP
                pipe_a2 = Pipeline.objects.create(id_empresa=empresa_a, nombre="Canal Aliados")
                etapa_a2 = Etapa.objects.create(id_empresa=empresa_a, pipeline=pipe_a2, nombre="Alta", orden=1)
                err_cross_pipe = crm_mcp.crm_mover_etapa_lead(tok_write_a, lead_id=lead_id, etapa_id=str(etapa_a2.pk))
                assert "error" in err_cross_pipe

                # Cross-tenant: A no puede mover lead de B ni usar etapa de B
                err_lead_b = crm_mcp.crm_mover_etapa_lead(
                    tok_write_a, lead_id=str(lead_b.pk), etapa_id=etapa_destino_id
                )
                assert "error" in err_lead_b
                err_etapa_b = crm_mcp.crm_mover_etapa_lead(tok_write_a, lead_id=lead_id, etapa_id=str(etapa_b.pk))
                assert "error" in err_etapa_b

                # 4) Registrar actividad vía MCP (con fecha ISO y usuario A)
                act = crm_mcp.crm_registrar_actividad(
                    tok_write_a,
                    lead_id=lead_id,
                    tipo="WHATSAPP",
                    asunto="Enviar brochure",
                    descripcion="Catálogo 2026",
                    fecha_vencimiento="2026-12-01",
                    asignado_a_id=str(user_a.pk),
                )
                assert act["tipo"] == "WHATSAPP"
                assert act["asunto"] == "Enviar brochure"
                assert act["fecha_vencimiento"] is not None

                # Error de dominio al registrar actividad sin asunto
                err_act_vacio = crm_mcp.crm_registrar_actividad(tok_write_a, lead_id=lead_id, asunto="")
                assert "error" in err_act_vacio

                # Cross-tenant en registrar_actividad -> dict error sin filtrar ni mutar
                assert "error" in crm_mcp.crm_registrar_actividad(tok_write_a, lead_id=str(lead_b.pk), asunto="Ajeno")
                assert "error" in crm_mcp.crm_registrar_actividad(
                    tok_write_a, lead_id=lead_id, asunto="User B", asignado_a_id=str(user_b.pk)
                )
                assert "error" in crm_mcp.crm_registrar_actividad(
                    tok_write_a, lead_id=lead_id, asunto="Tarea B", tarea_id=str(tarea_b.pk)
                )
                assert "error" in crm_mcp.crm_crear_lead(tok_write_a, nombre="Pipe B", pipeline_id=str(pipe_b.pk))
                assert "error" in crm_mcp.crm_crear_lead(tok_write_a, nombre="Etapa B", etapa_id=str(etapa_b.pk))
                assert "error" in crm_mcp.crm_crear_lead(tok_write_a, nombre="SinConsent", fuente="QR")

                # Error inesperado de BD oculto por R-CODE-8 (sanitize_mcp_error)
                with mock.patch(
                    "apps.crm.services.crear_lead_crm",
                    side_effect=IntegrityError("DETAIL: Key (email)=(secret) already exists"),
                ):
                    res_err = crm_mcp.crm_crear_lead(tok_write_a, nombre="Fallo")
                assert "secret" not in res_err["error"]
                assert "DETAIL" not in res_err["error"]

                # Token cuyo creado_por está inactivo NO debe asignarlo como creador de la actividad
                user_inactivo = Usuarios.objects.create_user(
                    username="crm_mcp_inactivo",
                    password=None,
                    is_active=False,
                )
                user_inactivo.empresas.add(empresa_a)
                tok_creador_inactivo = _token(empresa_a, ["crm:write"], creado_por=user_inactivo)
                act_sin_creador = crm_mcp.crm_registrar_actividad(
                    tok_creador_inactivo,
                    lead_id=lead_id,
                    asunto="Sin creador inactivo",
                )
                assert act_sin_creador["asunto"] == "Sin creador inactivo"
                assert Actividad.objects.get(pk=act_sin_creador["id_actividad"]).creado_por is None
        finally:
            rls.apply_system_default()
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")
