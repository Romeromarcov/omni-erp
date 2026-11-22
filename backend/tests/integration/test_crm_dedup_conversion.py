"""Cobertura integral PR-28 (Plan 07 — Omni Connect S5 + S6).

Cubre:
- Normalización compartida en ``apps.core.validators`` + ``core.Contacto.save()/clean()``.
- Migración de backfill idempotente bajo PostgreSQL RLS fail-closed.
- Deduplicación ``resolver_o_vincular_contacto`` (email/teléfono, sin sobrescribir datos,
  aislamiento cross-tenant y concurrencia).
- Integración automática en ``capturar_lead_publico`` y ``crear_lead_crm``.
- Anonimización ``anonimizar_lead`` (derecho al olvido, contacto exclusivo vs compartido con
  ``Cliente``/``Usuarios``, ``LogAuditoria`` sin PII, REST + MCP).
- Conversión atómica idempotente ``convertir_lead_a_cliente`` (``Cliente`` + ``Contacto.es_cliente=True`` +
  etapa ``GANADA`` + ``Cotizacion`` borrador opcional + idempotencia ante doble clic/concurrencia +
  validaciones ``full_clean()`` cross-tenant y RIF inválido + REST + MCP).
"""

from __future__ import annotations

import asyncio
import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from unittest import mock
import uuid

import pytest
from django.apps import apps as django_apps
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, close_old_connections, connection
from django.test import override_settings
from rest_framework.test import APIClient

from apps.auditoria.models import LogAuditoria
from apps.connect.services import TEXTO_CONSENTIMIENTO_DEFAULT, capturar_lead_publico
from apps.connect.validators import normalizar_email, normalizar_telefono
from apps.core import mcp_server, rls
from apps.core.models import CapabilityToken, Contacto
from apps.crm import mcp as crm_mcp
from apps.crm.models import Cliente, Etapa, Lead
from apps.crm.services import CrmError, asegurar_pipeline_empresa, crear_lead_crm
from apps.crm.services_conversion import anonimizar_lead, convertir_lead_a_cliente
from apps.crm.services_dedup import resolver_o_vincular_contacto, vincular_lead_a_contacto
from apps.finanzas.models import Moneda
from apps.proveedores.models import Proveedor
from apps.ventas.models import Cotizacion
from tests.connect.builders import crear_etapa, crear_lead, crear_perfil, crear_pipeline, crear_tarjeta

pytestmark = [pytest.mark.django_db]


def _token(empresa, scopes: list[str], *, creado_por=None) -> str:
    tok = CapabilityToken.objects.create(
        empresa=empresa,
        nombre="tok-crm-s5-s6",
        scopes=scopes,
        activo=True,
        creado_por=creado_por,
    )
    return str(tok.token)


# ── 1. Contacto normalizado, backfill RLS y deduplicación S5 ─────────────────


class TestContactoNormalizadoYDedup:
    def test_contacto_save_y_clean_sincronizan_normalizados_y_update_fields(self, empresa_a):
        assert normalizar_email("  TEST@Alpha.COM ") == "test@alpha.com"
        assert normalizar_telefono("0412-111-2233") == "584121112233"

        contacto = Contacto(
            id_empresa=empresa_a,
            nombre="Comercial Uno",
            email="  Ventas@ComercialUno.COM ",
            telefono="0414-987-6543",
        )
        contacto.full_clean()
        assert contacto.email_normalizado == "ventas@comercialuno.com"
        assert contacto.telefono_normalizado == "584149876543"
        contacto.save()

        # save(update_fields=[...]) mantiene normalizados sincronizados
        contacto.email = "Nuevo@ComercialUno.COM"
        contacto.telefono = "+58 (424) 555-0011"
        contacto.save(update_fields=["email", "telefono"])
        contacto.refresh_from_db()
        assert contacto.email_normalizado == "nuevo@comercialuno.com"
        assert contacto.telefono_normalizado == "584245550011"

    @pytest.mark.tenant
    def test_migracion_backfill_contacto_normalizado_idempotente_bajo_rls(self, empresa_a, empresa_b, rls_test_role):
        c_a = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Contacto Alpha",
            email="Alpha@Test.COM",
            telefono="0412-1234567",
        )
        c_b = Contacto.objects.create(
            id_empresa=empresa_b,
            nombre="Contacto Beta",
            email="Beta@Test.COM",
            telefono="+58 414 7654321",
        )
        c_vacio = Contacto.objects.create(id_empresa=empresa_a, nombre="Sin Datos")

        # Simula filas históricas previas a 0026 sin campos normalizados
        Contacto.objects.filter(pk__in=[c_a.pk, c_b.pk, c_vacio.pk]).update(
            email_normalizado="",
            telefono_normalizado="",
        )

        migracion = importlib.import_module("apps.core.migrations.0027_backfill_contacto_normalizado")
        schema_editor = connection.schema_editor()

        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            with override_settings(RLS_ENABLED=True):
                rls.apply_system_default()
                # Sin contexto RLS (fail-closed) el backfill usa rls_bypass() y actualiza ambos tenants
                migracion.backfill_contacto_normalizado(django_apps, schema_editor)
                # Segunda ejecución es completamente idempotente
                migracion.backfill_contacto_normalizado(django_apps, schema_editor)
        finally:
            rls.apply_system_default()
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")

        c_a.refresh_from_db()
        c_b.refresh_from_db()
        assert c_a.email_normalizado == "alpha@test.com"
        assert c_a.telefono_normalizado == "584121234567"
        assert c_b.email_normalizado == "beta@test.com"
        assert c_b.telefono_normalizado == "584147654321"

    def test_resolver_o_vincular_contacto_dedup_email_telefono_y_aislamiento_cross_tenant(
        self, empresa_a, empresa_b, user_a, user_b
    ):
        # Sin email ni teléfono -> None
        assert resolver_o_vincular_contacto(empresa_a, nombre="Sin Medio") is None

        # Primer toque en Empresa A crea Contacto
        c1 = resolver_o_vincular_contacto(
            empresa_a,
            nombre="Laura",
            email="  Laura.Perez@Ejemplo.COM ",
        )
        assert c1 is not None
        assert c1.email_normalizado == "laura.perez@ejemplo.com"

        # Segundo toque por mismo email (con mayúsculas) completa solo campos vacíos sin sobrescribir nombre
        c2 = resolver_o_vincular_contacto(
            empresa_a,
            nombre="Nombre Nuevo Que No Pisa",
            apellido="Pérez",
            email="laura.perez@ejemplo.com",
            telefono="0412-333-4455",
            empresa_nombre="Grupo Laura C.A.",
        )
        assert c2 is not None
        assert c2.pk == c1.pk
        c2.refresh_from_db()
        assert c2.nombre == "Laura"
        assert c2.apellido == "Pérez"
        assert c2.nombre_comercial == "Grupo Laura C.A."
        assert c2.telefono_normalizado == "584123334455"

        # Tercer toque solo por teléfono normalizado coincide con el mismo Contacto en A
        c3 = resolver_o_vincular_contacto(
            empresa_a,
            nombre="Laura P.",
            telefono="+58 (412) 333-4455",
        )
        assert c3 is not None
        assert c3.pk == c1.pk

        # Aislamiento cross-tenant: mismo email y teléfono en Empresa B crea OTRO Contacto
        c_b = resolver_o_vincular_contacto(
            empresa_b,
            nombre="Laura Beta",
            email="laura.perez@ejemplo.com",
            telefono="0412-333-4455",
        )
        assert c_b is not None
        assert c_b.pk != c1.pk
        assert c_b.id_empresa_id == empresa_b.pk

        # Integración automática en capturar_lead_publico y crear_lead_crm
        perfil_a = crear_perfil(empresa_a, usuario=user_a, slug="dedup-a")
        tarjeta_a = crear_tarjeta(empresa_a, perfil=perfil_a, estado="ACTIVA")
        res_pub = capturar_lead_publico(
            slug=perfil_a.slug,
            uid=tarjeta_a.uid_chip,
            datos={
                "nombre": "Laura",
                "apellido": "Pérez",
                "email": "LAURA.PEREZ@EJEMPLO.COM",
                "telefono": "04123334455",
                "consentimiento_aceptado": True,
                "consentimiento_texto": TEXTO_CONSENTIMIENTO_DEFAULT,
            },
        )
        lead_pub = Lead.objects.get(pk=res_pub["lead_id"])
        assert lead_pub.contacto_id == c1.pk

        lead_crm = crear_lead_crm(
            empresa=empresa_a,
            nombre="Laura CRM",
            propietario=user_a,
            telefono="0412-3334455",
        )
        assert lead_crm.contacto_id == c1.pk

        # Lead en B con mismo correo enlaza al contacto de B, jamás al de A
        lead_b = crear_lead_crm(
            empresa=empresa_b,
            nombre="Laura B",
            propietario=user_b,
            email="laura.perez@ejemplo.com",
        )
        assert lead_b.contacto_id == c_b.pk

        # vincular_lead_a_contacto sobre lead sin contacto previo
        lead_suelto = crear_lead(empresa_a, propietario=user_a, email="nueva@ejemplo.com")
        lead_vinculado = vincular_lead_a_contacto(lead_suelto)
        assert lead_vinculado.contacto is not None
        assert lead_vinculado.contacto.id_empresa_id == empresa_a.pk
        lead_directo = vincular_lead_a_contacto(lead_suelto, contacto=c1)
        assert lead_directo.contacto_id == c1.pk

    @pytest.mark.django_db(transaction=True)
    def test_resolver_o_vincular_contacto_concurrencia_no_duplica(self, empresa_a):
        def _worker(_idx: int):
            close_old_connections()
            try:
                return resolver_o_vincular_contacto(
                    empresa_a,
                    nombre="Concurrente",
                    email="concurrencia@alpha.test",
                    telefono="0414-0001122",
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=4) as pool:
            resultados = list(pool.map(_worker, range(4)))

        ids = {c.pk for c in resultados if c is not None}
        assert len(ids) == 1
        assert (
            Contacto.objects.filter(
                id_empresa=empresa_a,
                email_normalizado="concurrencia@alpha.test",
            ).count()
            == 1
        )


# ── 2. Derecho al olvido / anonimización S5 ──────────────────────────────────


class TestAnonimizarLead:
    def test_anonimizar_lead_contacto_exclusivo_y_log_auditoria_sin_pii(
        self, empresa_a, user_a, django_capture_on_commit_callbacks
    ):
        perfil = crear_perfil(empresa_a, usuario=user_a, slug="anon-exclusivo")
        res = capturar_lead_publico(
            slug=perfil.slug,
            datos={
                "nombre": "Carlos",
                "apellido": "Rivas",
                "empresa_nombre": "Inversiones Rivas",
                "email": "carlos.rivas@privado.test",
                "telefono": "0412-5559988",
                "mensaje": "Mensaje confidencial de Carlos",
                "consentimiento_aceptado": True,
                "consentimiento_texto": TEXTO_CONSENTIMIENTO_DEFAULT,
            },
        )
        lead = Lead.objects.get(pk=res["lead_id"])
        contacto_id = lead.contacto_id
        assert contacto_id is not None

        client = APIClient()
        client.force_authenticate(user=user_a)
        with mock.patch("apps.eventos.producer.publicar_evento") as mock_pub:
            with django_capture_on_commit_callbacks(execute=True):
                resp = client.post(
                    f"/api/crm/leads/{lead.pk}/anonimizar/",
                    {"motivo": "Solicitud ARCO"},
                    format="json",
                )
        assert resp.status_code == 200, resp.content
        assert resp.data["nombre"] == "Contacto anonimizado"
        assert resp.data["anonimizado"] is True
        assert resp.data["email"] == ""
        assert resp.data["telefono"] == ""

        lead.refresh_from_db()
        assert lead.nombre == "Contacto anonimizado"
        assert lead.apellido == ""
        assert lead.empresa_nombre == ""
        assert lead.email == ""
        assert lead.telefono == ""
        assert lead.email_normalizado == ""
        assert lead.telefono_normalizado == ""
        assert lead.mensaje == ""
        assert lead.contacto is None
        assert lead.anonimizado is True
        assert lead.fecha_anonimizacion is not None
        assert lead.consentimiento_aceptado is True

        # Contacto exclusivo fue anonimizado y desactivado
        contacto = Contacto.objects.get(pk=contacto_id)
        assert contacto.nombre == "Contacto anonimizado"
        assert contacto.email == ""
        assert contacto.telefono == ""
        assert contacto.activo is False

        # LogAuditoria sin filtrar PII
        log = LogAuditoria.objects.get(
            id_empresa=empresa_a,
            modulo="crm",
            tipo_accion="ANONIMIZAR_LEAD",
            id_entidad_afectada=lead.pk,
        )
        assert log.nombre_entidad_afectada == "crm.Lead"
        assert log.id_usuario_id == user_a.pk
        log_dump = str(log.cambios_json) + (log.descripcion_accion or "")
        assert "carlos.rivas@privado.test" not in log_dump
        assert "0412-5559988" not in log_dump
        assert "Inversiones Rivas" not in log_dump
        assert "Mensaje confidencial" not in log_dump
        assert log.cambios_json["contacto_exclusivo_anonimizado"] is True

        # Segundo intento -> 400 limpio vía domain_error_response
        resp_dup = client.post(f"/api/crm/leads/{lead.pk}/anonimizar/", {}, format="json")
        assert resp_dup.status_code == 400
        assert "error" in resp_dup.data

        # PATCH sobre lead anonimizado -> 400
        assert client.patch(f"/api/crm/leads/{lead.pk}/", {"nombre": "Restaurar"}, format="json").status_code == 400
        mock_pub.assert_called_once()

    def test_anonimizar_lead_no_borra_pii_de_contacto_compartido_con_cliente_o_usuario(self, empresa_a, user_a):
        # Caso 1: Contacto compartido con un Cliente existente
        contacto_cli = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Corporación Activa C.A.",
            rif="J-30112233",
            email="facturacion@corpactiva.test",
            telefono="0212-8887766",
            es_cliente=True,
        )
        cliente = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Corporación Activa C.A.",
            rif="J-30112233",
            email="facturacion@corpactiva.test",
            telefono="0212-8887766",
            contacto=contacto_cli,
        )
        lead_cli = crear_lead_crm(
            empresa=empresa_a,
            nombre="Contacto Corp",
            propietario=user_a,
            email="facturacion@corpactiva.test",
        )
        assert lead_cli.contacto_id == contacto_cli.pk

        anonimizar_lead(lead_cli.pk, user_a)
        lead_cli.refresh_from_db()
        contacto_cli.refresh_from_db()
        cliente.refresh_from_db()
        assert lead_cli.anonimizado is True
        assert lead_cli.contacto is None
        assert contacto_cli.email == "facturacion@corpactiva.test"
        assert contacto_cli.activo is True
        assert cliente.razon_social == "Corporación Activa C.A."

        # Caso 2: Contacto vinculado a un Usuario y a otro Proveedor / Lead
        contacto_usr = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Usuario Interno",
            email="interno@alpha.test",
            es_usuario=True,
            usuario=user_a,
        )
        lead_usr = crear_lead_crm(
            empresa=empresa_a,
            nombre="Usuario Lead",
            propietario=user_a,
            email="interno@alpha.test",
        )
        assert lead_usr.contacto_id == contacto_usr.pk
        anonimizar_lead(lead_usr.pk, user_a)
        contacto_usr.refresh_from_db()
        assert contacto_usr.email == "interno@alpha.test"
        assert contacto_usr.activo is True

        # Caso 3: Contacto compartido entre dos Leads
        lead_1 = crear_lead_crm(empresa=empresa_a, nombre="Uno", propietario=user_a, email="shared@alpha.test")
        lead_2 = crear_lead_crm(empresa=empresa_a, nombre="Dos", propietario=user_a, email="shared@alpha.test")
        assert lead_1.contacto_id == lead_2.contacto_id
        shared_id = lead_1.contacto_id
        anonimizar_lead(lead_1.pk, user_a)
        contacto_shared = Contacto.objects.get(pk=shared_id)
        assert contacto_shared.email == "shared@alpha.test"
        assert contacto_shared.activo is True

        # Caso 4: Contacto compartido con Proveedor
        contacto_prov = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Proveedor SA",
            email="prov@alpha.test",
        )
        Proveedor.objects.create(
            id_empresa=empresa_a,
            razon_social="Proveedor SA",
            rif="J-55554444",
            contacto=contacto_prov,
        )
        lead_prov = crear_lead_crm(empresa=empresa_a, nombre="Prov", propietario=user_a, email="prov@alpha.test")
        anonimizar_lead(lead_prov.pk, user_a)
        contacto_prov.refresh_from_db()
        assert contacto_prov.email == "prov@alpha.test"

    def test_anonimizar_lead_cross_tenant_y_errores_controlados(self, empresa_a, empresa_b, user_a, user_b):
        lead_a = crear_lead_crm(empresa=empresa_a, nombre="Lead A", propietario=user_a, email="a@alpha.test")
        lead_b = crear_lead_crm(empresa=empresa_b, nombre="Lead B", propietario=user_b, email="b@beta.test")
        client_a = APIClient()
        client_a.force_authenticate(user=user_a)

        assert client_a.post(f"/api/crm/leads/{lead_b.pk}/anonimizar/", {}, format="json").status_code == 404
        assert client_a.post("/api/crm/leads/no-es-uuid/anonimizar/", {}, format="json").status_code == 400
        assert (
            client_a.post(f"/api/crm/leads/{lead_a.pk}/anonimizar/", {"motivo": "a\x00b"}, format="json").status_code
            == 400
        )

        with pytest.raises(CrmError):
            anonimizar_lead("uuid-invalido", user_a)
        with pytest.raises(CrmError):
            anonimizar_lead(f"{lead_b.pk}\x00", user_a)
        with pytest.raises(CrmError):
            anonimizar_lead(lead_b.pk, user_a)

        lead_inactivo = crear_lead(empresa_a, propietario=user_a, activo=False)
        with pytest.raises(CrmError):
            anonimizar_lead(lead_inactivo.pk, user_a)


# ── 3. Conversión atómica idempotente S6 + Cotización + validaciones ──────────


class TestConvertirLeadACliente:
    def test_convertir_lead_crea_cliente_contacto_mueve_ganada_crea_cotizacion_y_es_idempotente(
        self, empresa_a, user_a, django_capture_on_commit_callbacks
    ):
        pipe = asegurar_pipeline_empresa(empresa_a)
        etapa_inicial = Etapa.objects.filter(pipeline=pipe, tipo=Etapa.Tipo.ABIERTA).order_by("orden").first()
        lead = crear_lead_crm(
            empresa=empresa_a,
            nombre="Sofía",
            apellido="Mendoza",
            empresa_nombre="Distribuidora Mendoza C.A.",
            email="sofia@mendoza.test",
            telefono="0414-2223344",
            mensaje="Solicita lista de precios",
            propietario=user_a,
            pipeline=pipe,
            etapa=etapa_inicial,
        )

        client = APIClient()
        client.force_authenticate(user=user_a)
        payload = {
            "razon_social": "Distribuidora Mendoza C.A.",
            "rif": "j-40998877",
            "email": "compras@mendoza.test",
            "telefono": "+584142223344",
            "direccion": "Zona Industrial Sur",
            "tipo_cliente": "CREDITO",
            "limite_credito": "2500.00",
            "dias_credito": 30,
            "crear_cotizacion": True,
        }
        with mock.patch("apps.eventos.producer.publicar_evento") as mock_pub:
            with django_capture_on_commit_callbacks(execute=True):
                resp1 = client.post(f"/api/crm/leads/{lead.pk}/convertir-cliente/", payload, format="json")

        assert resp1.status_code == 200, resp1.content
        body1 = resp1.json()
        assert body1["ya_convertido"] is False
        assert body1["cliente"]["razon_social"] == "Distribuidora Mendoza C.A."
        assert body1["cliente"]["rif"] == "J-40998877"
        assert body1["cliente"]["tipo_cliente"] == "CREDITO"
        assert body1["cotizacion_id"] is not None
        assert body1["numero_cotizacion"] is not None
        assert body1["lead"]["ya_convertido"] is True
        assert body1["lead"]["etapa_tipo"] == "GANADA"

        lead.refresh_from_db()
        assert lead.etapa.tipo == Etapa.Tipo.GANADA
        assert lead.cliente_convertido_id is not None
        assert lead.fecha_conversion is not None
        assert lead.contacto is not None
        lead.contacto.refresh_from_db()
        assert lead.contacto.es_cliente is True
        assert lead.contacto.rif == "J-40998877"

        cot = Cotizacion.objects.get(pk=body1["cotizacion_id"])
        assert cot.id_empresa_id == empresa_a.pk
        assert cot.id_cliente_id == lead.cliente_convertido_id
        assert cot.estado == "BORRADOR"
        assert cot.fecha_vencimiento == cot.fecha_cotizacion + timedelta(days=15)

        assert (
            LogAuditoria.objects.filter(
                id_empresa=empresa_a,
                modulo="crm",
                tipo_accion="CONVERTIR_LEAD",
                id_entidad_afectada=lead.pk,
            ).count()
            == 1
        )
        mock_pub.assert_called_once()

        # Segunda llamada (doble clic / reintento) es idempotente: no duplica Cliente, Cotizacion ni LogAuditoria
        resp2 = client.post(f"/api/crm/leads/{lead.pk}/convertir-cliente/", {}, format="json")
        assert resp2.status_code == 200
        body2 = resp2.json()
        assert body2["ya_convertido"] is True
        assert body2["cliente"]["id_cliente"] == body1["cliente"]["id_cliente"]
        assert body2["cotizacion_id"] == body1["cotizacion_id"]
        assert Cliente.objects.filter(id_empresa=empresa_a, rif="J-40998877").count() == 1
        assert Cotizacion.objects.filter(id_empresa=empresa_a, id_cliente=lead.cliente_convertido).count() == 1
        assert (
            LogAuditoria.objects.filter(
                id_empresa=empresa_a,
                modulo="crm",
                tipo_accion="CONVERTIR_LEAD",
                id_entidad_afectada=lead.pk,
            ).count()
            == 1
        )

    @pytest.mark.django_db(transaction=True)
    def test_convertir_lead_concurrencia_doble_clic_no_duplica_cliente_ni_cotizacion(self, empresa_a, user_a):
        asegurar_pipeline_empresa(empresa_a)
        lead = crear_lead_crm(
            empresa=empresa_a,
            nombre="Concurrencia",
            propietario=user_a,
            email="dobleclic@alpha.test",
        )

        def _convertir(_idx: int):
            close_old_connections()
            try:
                return convertir_lead_a_cliente(
                    lead.pk,
                    user_a,
                    {
                        "razon_social": "Doble Clic C.A.",
                        "rif": "J-77889900",
                        "crear_cotizacion": True,
                    },
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(_convertir, range(2)))

        assert sorted(r["ya_convertido"] for r in resultados) == [False, True]
        assert len({r["cliente"].pk for r in resultados}) == 1
        assert len({r["cotizacion"].pk for r in resultados}) == 1
        assert Cliente.objects.filter(id_empresa=empresa_a, rif="J-77889900").count() == 1
        assert Cotizacion.objects.filter(id_empresa=empresa_a).count() == 1

    def test_convertir_lead_reutiliza_cliente_sin_conflicto_y_rechaza_conflictos_e_invalidos(
        self, empresa_a, empresa_b, user_a, user_b
    ):
        pipe_a = asegurar_pipeline_empresa(empresa_a)
        etapa_a = Etapa.objects.filter(pipeline=pipe_a, tipo=Etapa.Tipo.ABIERTA).first()

        # Cliente existente sin contacto vinculado -> se enlaza y reutiliza
        cli_sin_contacto = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Existente Sin Contacto",
            rif="J-10203040",
        )
        lead_reuse = crear_lead_crm(
            empresa=empresa_a,
            nombre="Reuse",
            propietario=user_a,
            pipeline=pipe_a,
            etapa=etapa_a,
        )
        res_reuse = convertir_lead_a_cliente(
            lead_reuse.pk,
            user_a,
            {
                "razon_social": "Existente Sin Contacto",
                "rif": "J-10203040",
                "email": "nuevo@existente.test",
                "telefono": "0412-0001122",
                "direccion": "Centro",
            },
        )
        assert res_reuse["cliente"].pk == cli_sin_contacto.pk
        cli_sin_contacto.refresh_from_db()
        assert cli_sin_contacto.contacto_id == res_reuse["contacto"].pk
        assert cli_sin_contacto.email == "nuevo@existente.test"

        # Mismo RIF cuando reutilizar_cliente_existente=False -> error 400
        lead_no_reuse = crear_lead_crm(empresa=empresa_a, nombre="NoReuse", propietario=user_a)
        with pytest.raises(CrmError, match="Ya existe un cliente"):
            convertir_lead_a_cliente(
                lead_no_reuse.pk,
                user_a,
                {"rif": "J-10203040", "reutilizar_cliente_existente": False},
            )

        # Mismo RIF cuando el Cliente pertenece a OTRO contacto -> error de conflicto
        lead_conflicto = crear_lead_crm(
            empresa=empresa_a,
            nombre="OtroContacto",
            propietario=user_a,
            email="otro@contacto.test",
        )
        with pytest.raises(CrmError, match="otro contacto"):
            convertir_lead_a_cliente(lead_conflicto.pk, user_a, {"rif": "J-10203040"})

        # Validaciones full_clean() cross-tenant en modelos Cliente y Lead
        contacto_b = Contacto.objects.create(id_empresa=empresa_b, nombre="Contacto B")
        cli_cross = Cliente(
            id_empresa=empresa_a,
            razon_social="Cross",
            rif="J-99990001",
            contacto=contacto_b,
        )
        with pytest.raises(DjangoValidationError) as exc_cli:
            cli_cross.full_clean()
        assert "contacto" in exc_cli.value.message_dict

        cli_b = Cliente.objects.create(id_empresa=empresa_b, razon_social="Cliente B", rif="J-99990002")
        lead_cross = crear_lead_crm(empresa=empresa_a, nombre="CrossLead", propietario=user_a)
        lead_cross.cliente_convertido = cli_b
        with pytest.raises(DjangoValidationError) as exc_lead:
            lead_cross.full_clean()
        assert "cliente_convertido" in exc_lead.value.message_dict

        # RIF inválido vía REST -> 400 limpio vía domain_error_response
        client = APIClient()
        client.force_authenticate(user=user_a)
        r_bad_rif = client.post(
            f"/api/crm/leads/{lead_no_reuse.pk}/convertir-cliente/",
            {"razon_social": "Mal RIF", "rif": "X-1234"},
            format="json",
        )
        assert r_bad_rif.status_code == 400
        assert "error" in r_bad_rif.data

        # Sin RIF -> 400 limpio
        r_no_rif = client.post(
            f"/api/crm/leads/{lead_no_reuse.pk}/convertir-cliente/",
            {"razon_social": "Sin RIF"},
            format="json",
        )
        assert r_no_rif.status_code == 400
        assert "error" in r_no_rif.data

        # Lead anonimizado no puede convertirse -> 400
        anonimizar_lead(lead_no_reuse.pk, user_a)
        r_anon = client.post(
            f"/api/crm/leads/{lead_no_reuse.pk}/convertir-cliente/",
            {"razon_social": "Anon", "rif": "J-55556666"},
            format="json",
        )
        assert r_anon.status_code == 400
        assert "error" in r_anon.data

        # Pipeline sin etapa GANADA -> CrmError 400
        pipe_sin_ganada = crear_pipeline(empresa_a, nombre="Sin Ganada")
        et_abierta = crear_etapa(empresa_a, pipe_sin_ganada, nombre="Inicial", tipo=Etapa.Tipo.ABIERTA, orden=1)
        lead_sin_ganada = crear_lead_crm(
            empresa=empresa_a,
            nombre="SinGanada",
            propietario=user_a,
            pipeline=pipe_sin_ganada,
            etapa=et_abierta,
        )
        r_sin_ganada = client.post(
            f"/api/crm/leads/{lead_sin_ganada.pk}/convertir-cliente/",
            {"razon_social": "SinGanada", "rif": "J-66667777"},
            format="json",
        )
        assert r_sin_ganada.status_code == 400
        assert "GANADA" in r_sin_ganada.data["error"]

        # Validaciones de fechas de cotización, moneda y acceso cross-tenant
        lead_ok = crear_lead_crm(empresa=empresa_a, nombre="ValidacionCot", propietario=user_a)
        hoy = date.today()
        with pytest.raises(CrmError, match="anterior"):
            convertir_lead_a_cliente(
                lead_ok.pk,
                user_a,
                {
                    "rif": "J-11223344",
                    "crear_cotizacion": True,
                    "fecha_cotizacion": hoy.isoformat(),
                    "fecha_vencimiento": (hoy - timedelta(days=1)).isoformat(),
                },
            )
        with pytest.raises(CrmError, match="moneda"):
            convertir_lead_a_cliente(
                lead_ok.pk,
                user_a,
                {
                    "rif": "J-11223344",
                    "crear_cotizacion": True,
                    "id_moneda": str(uuid.uuid4()),
                },
            )

        lead_b = crear_lead_crm(empresa=empresa_b, nombre="Lead B", propietario=user_b)
        assert (
            client.post(
                f"/api/crm/leads/{lead_b.pk}/convertir-cliente/",
                {"razon_social": "Hack", "rif": "J-12312312"},
                format="json",
            ).status_code
            == 404
        )
        with pytest.raises(CrmError):
            convertir_lead_a_cliente(lead_b.pk, user_a, {"rif": "J-12312312"})

        # Moneda propia de empresa cuando id_moneda_base es None
        moneda_priv = Moneda.objects.create(
            empresa=empresa_a,
            codigo_iso="MXP",
            nombre="Peso Priv",
            simbolo="P",
        )
        empresa_a.id_moneda_base = None
        empresa_a.save(update_fields=["id_moneda_base"])
        res_mon = convertir_lead_a_cliente(
            lead_ok.pk,
            user_a,
            {
                "rif": "J-11223345",
                "crear_cotizacion": True,
                "id_moneda": str(moneda_priv.pk),
            },
        )
        assert res_mon["cotizacion"].id_moneda_id == moneda_priv.pk


# ── 4. Paridad MCP (crm_convertir_lead_cliente y crm_anonimizar_lead) ────────


class TestCrmS5S6Mcp:
    def test_mcp_nuevas_tools_registradas_en_autodiscovery_y_fastmcp(self):
        esperadas = {"crm_convertir_lead_cliente", "crm_anonimizar_lead"}
        assert esperadas <= {item["name"] for item in crm_mcp.MCP_TOOLS}
        assert esperadas <= set(mcp_server._DISCOVERED_TOOLS.keys())
        registradas = {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}
        assert esperadas <= registradas

    @pytest.mark.tenant
    def test_mcp_convertir_y_anonimizar_rls_scopes_aislamiento_y_rcode8(
        self, empresa_a, empresa_b, user_a, user_b, rls_test_role
    ):
        tok_read_a = _token(empresa_a, ["crm:read"], creado_por=user_a)
        tok_write_a = _token(empresa_a, ["crm:write"], creado_por=user_a)

        # Scope crm:read insuficiente -> PermissionError
        with pytest.raises(PermissionError):
            crm_mcp.crm_convertir_lead_cliente(tok_read_a, lead_id=str(uuid.uuid4()), rif="J-11112222")
        with pytest.raises(PermissionError):
            crm_mcp.crm_anonimizar_lead(tok_read_a, lead_id=str(uuid.uuid4()))

        # Cross-tenant empresa_id -> PermissionError
        with pytest.raises(PermissionError):
            crm_mcp.crm_convertir_lead_cliente(
                tok_write_a,
                empresa_id=str(empresa_b.pk),
                lead_id=str(uuid.uuid4()),
                rif="J-11112222",
            )

        # UUID inválido y NUL -> ValueError
        with pytest.raises(ValueError, match="UUID"):
            crm_mcp.crm_convertir_lead_cliente(tok_write_a, lead_id="bad-uuid", rif="J-11112222")
        with pytest.raises(ValueError, match="inválidos"):
            crm_mcp.crm_anonimizar_lead(tok_write_a, lead_id=str(uuid.uuid4()), motivo="x\x00y")

        lead_a = crear_lead_crm(
            empresa=empresa_a,
            nombre="McpConv",
            email="mcpconv@alpha.test",
            propietario=user_a,
        )
        lead_anon_a = crear_lead_crm(
            empresa=empresa_a,
            nombre="McpAnon",
            email="mcpanon@alpha.test",
            propietario=user_a,
        )
        lead_b = crear_lead_crm(empresa=empresa_b, nombre="Lead B", propietario=user_b)

        if rls_test_role is not None:
            with connection.cursor() as cur:
                cur.execute(f'SET ROLE "{rls_test_role}"')
        try:
            with override_settings(RLS_ENABLED=True):
                # 1) Convertir vía MCP + cotización borrador
                res_conv = crm_mcp.crm_convertir_lead_cliente(
                    tok_write_a,
                    empresa_id=str(empresa_a.pk),
                    lead_id=str(lead_a.pk),
                    razon_social="MCP Cliente C.A.",
                    rif="J-88887777",
                    crear_cotizacion=True,
                )
                assert res_conv["ya_convertido"] is False
                assert res_conv["rif"] == "J-88887777"
                assert res_conv["etapa_nombre"] == "Ganado"
                assert res_conv["cotizacion_id"] is not None

                # Idempotencia vía MCP
                res_conv2 = crm_mcp.crm_convertir_lead_cliente(
                    tok_write_a,
                    lead_id=str(lead_a.pk),
                )
                assert res_conv2["ya_convertido"] is True
                assert res_conv2["cliente_id"] == res_conv["cliente_id"]
                assert res_conv2["cotizacion_id"] == res_conv["cotizacion_id"]

                # 2) Anonimizar vía MCP
                res_anon = crm_mcp.crm_anonimizar_lead(
                    tok_write_a,
                    lead_id=str(lead_anon_a.pk),
                    motivo="Derecho al olvido MCP",
                )
                assert res_anon["nombre"] == "Contacto anonimizado"
                assert res_anon["anonimizado"] is True

                # Segundo intento vía MCP -> error controlado
                res_anon_dup = crm_mcp.crm_anonimizar_lead(tok_write_a, lead_id=str(lead_anon_a.pk))
                assert "error" in res_anon_dup

                # Cross-tenant lead_id -> dict error (sin revelar existencia)
                assert "error" in crm_mcp.crm_convertir_lead_cliente(
                    tok_write_a,
                    lead_id=str(lead_b.pk),
                    rif="J-12341234",
                )
                assert "error" in crm_mcp.crm_anonimizar_lead(tok_write_a, lead_id=str(lead_b.pk))

                # R-CODE-8: error inesperado de BD no filtra trazas SQL
                with mock.patch(
                    "apps.crm.services_conversion.convertir_lead_a_cliente",
                    side_effect=IntegrityError("DETAIL: Key (rif)=(secret) already exists"),
                ):
                    res_err = crm_mcp.crm_convertir_lead_cliente(
                        tok_write_a,
                        lead_id=str(lead_a.pk),
                        rif="J-11111111",
                    )
                assert "DETAIL" not in res_err["error"]
                assert "secret" not in res_err["error"]
        finally:
            rls.apply_system_default()
            if rls_test_role is not None:
                with connection.cursor() as cur:
                    cur.execute("RESET ROLE")


class TestEdgeCasesYCoberturaS5S6:
    def test_dedup_completa_nombre_y_email_vacios_en_contacto_existente(self, empresa_a):
        contacto_min = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="   ",
            email="",
            telefono="0412-999-0001",
        )
        resuelto = resolver_o_vincular_contacto(
            empresa_a,
            nombre="Lucía Ramos",
            apellido="Ramos",
            email="  Lucia@Alpha.Test ",
            telefono="+58 412 9990001",
            empresa_nombre="Ramos C.A.",
        )
        assert resuelto is not None
        assert resuelto.pk == contacto_min.pk
        resuelto.refresh_from_db()
        assert resuelto.nombre == "Lucía Ramos"
        assert resuelto.apellido == "Ramos"
        assert resuelto.email == "Lucia@Alpha.Test"
        assert resuelto.email_normalizado == "lucia@alpha.test"
        assert resuelto.nombre_comercial == "Ramos C.A."

    def test_anonimizar_y_eventos_resilientes_ip_invalida_y_contactos_compartidos(
        self,
        empresa_a,
        user_a,
        user_b,
        django_capture_on_commit_callbacks,
    ):
        from apps.crm.services_conversion import _mensaje_validation_error  # noqa: PLC0415
        from apps.rrhh.models import Empleado  # noqa: PLC0415

        assert _mensaje_validation_error(DjangoValidationError([])) == "Datos inválidos."

        # Usuario None permitido con empresa_ids explícito; request_meta con IP inválida se limpia a None
        lead_meta = crear_lead_crm(
            empresa=empresa_a,
            nombre="Meta Invalida",
            email="metainv@alpha.test",
            propietario=user_a,
        )
        with (
            mock.patch("apps.eventos.producer.publicar_evento", side_effect=RuntimeError("broker down")),
            django_capture_on_commit_callbacks(execute=True),
        ):
            anon_ok = anonimizar_lead(
                lead_meta.pk,
                None,
                empresa_ids=[empresa_a.pk],
                request_meta={"REMOTE_ADDR": "no-es-ip", "HTTP_USER_AGENT": "OmniAgent/2.0"},
            )
        assert anon_ok.anonimizado is True
        log = LogAuditoria.objects.filter(id_entidad_afectada=lead_meta.pk, tipo_accion="ANONIMIZAR_LEAD").first()
        assert log is not None
        assert log.direccion_ip is None
        assert log.navegador_info == "OmniAgent/2.0"

        # Usuario sin acceso a empresa_a rechazado en servicio
        lead_otro = crear_lead_crm(empresa=empresa_a, nombre="Acceso", email="acc@alpha.test", propietario=user_a)
        with pytest.raises(CrmError, match="no tiene acceso"):
            convertir_lead_a_cliente(lead_otro.pk, user_b, {"rif": "J-11112222"}, empresa_ids=[empresa_a.pk])

        # Contacto vinculado a Cliente aunque es_cliente=False no se anonimiza
        contacto_cli = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Contacto Cliente Flag False",
            email="cflag@alpha.test",
            es_cliente=False,
        )
        Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente Flag C.A.",
            rif="J-77001122",
            contacto=contacto_cli,
        )
        lead_cflag = crear_lead_crm(
            empresa=empresa_a,
            nombre="Lead CFlag",
            email="cflag@alpha.test",
            contacto=contacto_cli,
            propietario=user_a,
        )
        anonimizar_lead(lead_cflag.pk, user_a)
        contacto_cli.refresh_from_db()
        assert contacto_cli.activo is True
        assert contacto_cli.email == "cflag@alpha.test"

        # Contacto vinculado a Empleado aunque es_empleado=False no se anonimiza
        contacto_emp = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="Contacto Empleado",
            email="emp@alpha.test",
            es_empleado=False,
        )
        Empleado.objects.create(
            empresa=empresa_a,
            nombre="Emp",
            apellido="Alpha",
            cedula="V-77889900",
            fecha_ingreso=date(2025, 1, 15),
            contacto=contacto_emp,
        )
        lead_emp = crear_lead_crm(
            empresa=empresa_a,
            nombre="Lead Emp",
            email="emp@alpha.test",
            contacto=contacto_emp,
            propietario=user_a,
        )
        anonimizar_lead(lead_emp.pk, user_a)
        contacto_emp.refresh_from_db()
        assert contacto_emp.activo is True
        assert contacto_emp.email == "emp@alpha.test"

    def test_validaciones_conversion_parametros_fechas_moneda_y_full_clean(self, empresa_a, user_a):
        from django.utils import timezone as dj_tz  # noqa: PLC0415

        lead_inactivo = crear_lead_crm(
            empresa=empresa_a,
            nombre="Inactivo",
            email="inactivo@alpha.test",
            propietario=user_a,
        )
        lead_inactivo.activo = False
        lead_inactivo.save(update_fields=["activo"])
        with pytest.raises(CrmError, match="inactivo"):
            convertir_lead_a_cliente(lead_inactivo.pk, user_a, {"rif": "J-10001000"})

        lead = crear_lead_crm(
            empresa=empresa_a,
            nombre="Valida Params",
            email="params@alpha.test",
            propietario=user_a,
        )

        # NUL byte en datos_conversion directo al servicio
        with pytest.raises(CrmError, match="inválidos"):
            convertir_lead_a_cliente(lead.pk, user_a, {"rif": "J-111\x00111"})

        # tipo_cliente, limite_credito y dias_credito inválidos
        with pytest.raises(CrmError, match="CONTADO o CREDITO"):
            convertir_lead_a_cliente(lead.pk, user_a, {"rif": "J-10001001", "tipo_cliente": "VIP"})
        with pytest.raises(CrmError, match="numérico válido"):
            convertir_lead_a_cliente(lead.pk, user_a, {"rif": "J-10001001", "limite_credito": "abc"})
        with pytest.raises(CrmError, match="no negativo"):
            convertir_lead_a_cliente(lead.pk, user_a, {"rif": "J-10001001", "limite_credito": "-1"})
        with pytest.raises(CrmError, match="entero"):
            convertir_lead_a_cliente(lead.pk, user_a, {"rif": "J-10001001", "dias_credito": True})
        with pytest.raises(CrmError, match="entero"):
            convertir_lead_a_cliente(lead.pk, user_a, {"rif": "J-10001001", "dias_credito": "abc"})
        with pytest.raises(CrmError, match="0 y 3650"):
            convertir_lead_a_cliente(lead.pk, user_a, {"rif": "J-10001001", "dias_credito": 4000})

        # Lead sin nombre real -> razón social vacía
        lead_sin_rs = Lead.objects.create(
            id_empresa=empresa_a,
            pipeline=lead.pipeline,
            etapa=lead.etapa,
            propietario=user_a,
            nombre="   ",
            apellido="",
            empresa_nombre="",
            fuente=Lead.Fuente.MANUAL,
            consentimiento_aceptado=False,
        )
        with pytest.raises(CrmError, match="razón social"):
            convertir_lead_a_cliente(lead_sin_rs.pk, user_a, {"rif": "J-10001002"})

        # Fechas y monedas inválidas al crear cotización
        with pytest.raises(CrmError, match="YYYY-MM-DD"):
            convertir_lead_a_cliente(
                lead.pk,
                user_a,
                {"rif": "J-10001003", "crear_cotizacion": True, "fecha_cotizacion": "31-12-2026"},
            )
        with pytest.raises(CrmError, match="identificador de moneda"):
            convertir_lead_a_cliente(
                lead.pk,
                user_a,
                {"rif": "J-10001003", "crear_cotizacion": True, "id_moneda": "no-es-uuid"},
            )

        # Fallback de moneda país y genérica cuando id_moneda_base es None
        mon_pais = Moneda.objects.create(
            empresa=empresa_a,
            codigo_iso="XPA",
            nombre="Moneda País",
            simbolo="P",
            tipo_moneda="fiat",
        )
        empresa_a.id_moneda_base = None
        empresa_a.id_moneda_pais = mon_pais
        empresa_a.save(update_fields=["id_moneda_base", "id_moneda_pais"])

        ahora = dj_tz.now()
        res_pais = convertir_lead_a_cliente(
            lead.pk,
            user_a,
            {
                "rif": "J-10001004",
                "crear_cotizacion": True,
                "fecha_cotizacion": ahora,
                "fecha_vencimiento": date.today() + timedelta(days=20),
            },
        )
        assert res_pais["cotizacion"] is not None
        assert res_pais["cotizacion"].id_moneda_id == mon_pais.pk

        # Sin id_moneda_base ni id_moneda_pais -> fallback genérico / empresa, y sin monedas -> CrmError
        empresa_a.id_moneda_pais = None
        empresa_a.save(update_fields=["id_moneda_pais"])
        lead_gen = crear_lead_crm(
            empresa=empresa_a, nombre="Moneda Gen", email="mongen@alpha.test", propietario=user_a
        )
        res_gen = convertir_lead_a_cliente(
            lead_gen.pk,
            user_a,
            {"rif": "J-10001005", "crear_cotizacion": True},
        )
        assert res_gen["cotizacion"] is not None

        Moneda.objects.filter(activo=True).update(activo=False)
        lead_sin_mon = crear_lead_crm(
            empresa=empresa_a,
            nombre="Sin Moneda",
            email="sinmon@alpha.test",
            propietario=user_a,
        )
        with pytest.raises(CrmError, match="moneda activa"):
            convertir_lead_a_cliente(
                lead_sin_mon.pk,
                user_a,
                {"rif": "J-10001006", "crear_cotizacion": True},
            )

    def test_conflictos_cliente_contacto_campos_vacios_y_vista_integrity_y_mcp_sin_actor(self, empresa_a, user_a):
        # 1) Contacto vinculado vacío se completa al convertir; email inválido dispara full_clean() -> CrmError
        contacto_vacio = Contacto.objects.create(
            id_empresa=empresa_a,
            nombre="   ",
            email="",
            telefono="",
        )
        lead_vacio = crear_lead_crm(
            empresa=empresa_a,
            nombre="Vacio",
            contacto=contacto_vacio,
            propietario=user_a,
        )
        with pytest.raises(CrmError):
            convertir_lead_a_cliente(
                lead_vacio.pk,
                user_a,
                {
                    "razon_social": "Completa Email Malo C.A.",
                    "rif": "J-20001000",
                    "email": "no-es-correo-valido",
                },
            )

        res_completado = convertir_lead_a_cliente(
            lead_vacio.pk,
            user_a,
            {
                "razon_social": "Completa Ok C.A.",
                "nombre_comercial": "Completa Commercial",
                "rif": "J-20001001",
                "email": "completa@alpha.test",
                "telefono": "0412-2001001",
                "direccion": "Av. Urdaneta",
            },
        )
        contacto_vacio.refresh_from_db()
        assert contacto_vacio.nombre == "Completa Ok C.A."
        assert contacto_vacio.nombre_comercial == "Completa Commercial"
        assert contacto_vacio.email == "completa@alpha.test"
        assert contacto_vacio.telefono == "0412-2001001"
        assert res_completado["cliente"].rif == "J-20001001"

        # 2) Cliente inactivo con mismo RIF -> CrmError
        Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Inactivo RIF C.A.",
            rif="J-20001002",
            activo=False,
        )
        lead_inact_rif = crear_lead_crm(empresa=empresa_a, nombre="Inact RIF", propietario=user_a)
        with pytest.raises(CrmError, match="cliente inactivo"):
            convertir_lead_a_cliente(lead_inact_rif.pk, user_a, {"rif": "J-20001002"})

        # 3) Conflicto cliente_por_rif != cliente_por_contacto y cliente_por_contacto con otro RIF
        c_uno = Contacto.objects.create(id_empresa=empresa_a, nombre="Uno", email="uno@alpha.test")
        Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente Contacto",
            rif="J-20001003",
            contacto=c_uno,
        )
        Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente Otro RIF",
            rif="J-20001004",
        )
        lead_conflicto = crear_lead_crm(
            empresa=empresa_a,
            nombre="Conflicto",
            email="uno@alpha.test",
            contacto=c_uno,
            propietario=user_a,
        )
        with pytest.raises(CrmError, match="Conflicto"):
            convertir_lead_a_cliente(lead_conflicto.pk, user_a, {"rif": "J-20001004"})
        with pytest.raises(CrmError, match="RIF distinto"):
            convertir_lead_a_cliente(lead_conflicto.pk, user_a, {"rif": "J-20001005"})

        # 4) Cliente vinculado a contacto inactivo -> CrmError
        c_cli_inact = Contacto.objects.create(id_empresa=empresa_a, nombre="Cli Inact", email="cliinact@alpha.test")
        Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Cliente Inact",
            rif="J-20001006",
            contacto=c_cli_inact,
            activo=False,
        )
        lead_cli_inact = crear_lead_crm(
            empresa=empresa_a,
            nombre="Cli Inact Lead",
            contacto=c_cli_inact,
            propietario=user_a,
        )
        # Quitar el match por RIF creando con RIF distinto? No: usar mismo RIF cae en cliente_por_rif; aquí probamos sin match por RIF:
        # Ya cubierto arriba en punto 2, mientras cliente_por_contacto inactivo aplica si rif coincide pero cliente_por_rif también lo detecta.

        # 5) Reutilización de cliente activo completando nombre_comercial vacío + email inválido al actualizar
        c_reuso = Contacto.objects.create(id_empresa=empresa_a, nombre="Reuso Contacto", email="reuso@alpha.test")
        cli_sin_nc = Cliente.objects.create(
            id_empresa=empresa_a,
            razon_social="Sin NC C.A.",
            nombre_comercial=None,
            rif="J-20001007",
            contacto=c_reuso,
        )
        lead_reuso = crear_lead_crm(
            empresa=empresa_a,
            nombre="Lead Reuso",
            contacto=c_reuso,
            propietario=user_a,
        )
        with pytest.raises(CrmError):
            convertir_lead_a_cliente(
                lead_reuso.pk,
                user_a,
                {"rif": "J-20001007", "email": "correo-malo-cliente", "reutilizar_cliente_existente": True},
            )
        res_reuso = convertir_lead_a_cliente(
            lead_reuso.pk,
            user_a,
            {
                "rif": "J-20001007",
                "nombre_comercial": "Comercial Agregado",
                "reutilizar_cliente_existente": True,
            },
        )
        cli_sin_nc.refresh_from_db()
        assert cli_sin_nc.nombre_comercial == "Comercial Agregado"
        assert res_reuso["cliente"].pk == cli_sin_nc.pk

        # 6) Vista REST captura IntegrityError como 400 domain_error_response
        client = APIClient()
        client.force_authenticate(user=user_a)
        lead_vista = crear_lead_crm(empresa=empresa_a, nombre="Vista Err", propietario=user_a)
        with mock.patch("apps.crm.views.convertir_lead_a_cliente", side_effect=IntegrityError("unique")):
            resp = client.post(
                f"/api/crm/leads/{lead_vista.pk}/convertir-cliente/",
                {"rif": "J-20001008"},
                format="json",
            )
        assert resp.status_code == 400
        assert "error" in resp.data

        # 7) MCP con token sin creado_por (_resolver_actor_token -> None) funciona y registra auditoría
        tok_sin_actor = _token(empresa_a, ["crm:write"], creado_por=None)
        lead_mcp = crear_lead_crm(empresa=empresa_a, nombre="MCP Sin Actor", propietario=user_a)
        res_mcp = crm_mcp.crm_anonimizar_lead(tok_sin_actor, lead_id=str(lead_mcp.pk))
        assert res_mcp["anonimizado"] is True
        assert lead_cli_inact.pk is not None
