"""Tests de integración Plan 09 Ola 2B: RBAC/ABAC Granular y Access Studio (Fase 7.1)."""

from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.test import RequestFactory
from rest_framework.test import APIClient

from apps.core import rls
from apps.core.models import Permisos, Roles
from tests.factories import UsuariosFactory

pytestmark = [pytest.mark.django_db]


# ---------------------------------------------------------------------------
# 1. PostgreSQL RLS y Aislamiento Multi-Tenant en PoliticaAccesoRol
# ---------------------------------------------------------------------------


class TestRbacAbacRLSYAislamiento:
    def test_rls_aislamiento_politica_acceso_rol(self, rls_test_role, empresa_a, empresa_b, moneda_usd):
        from apps.core.models import PoliticaAccesoRol

        with connection.cursor() as cur:
            cur.execute("SELECT policyname FROM pg_policies WHERE tablename = 'core_politica_acceso_rol';")
            assert rls.POLICY_NAME in [row[0] for row in cur.fetchall()]

        with rls.rls_bypass():
            rol_a = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Rol RLS A")
            rol_b = Roles.objects.create(id_empresa=empresa_b, nombre_rol="Rol RLS B")
            pol_a = PoliticaAccesoRol.objects.create(
                id_empresa=empresa_a,
                id_rol=rol_a,
                modulo="ventas",
                accion="VER",
                ambito="FISCAL",
                alcance="PROPIO",
                campos_ocultos=["costo_unitario"],
            )
            pol_b = PoliticaAccesoRol.objects.create(
                id_empresa=empresa_b,
                id_rol=rol_b,
                modulo="ventas",
                accion="VER",
                ambito="GERENCIAL",
                alcance="EMPRESA",
            )

        if rls_test_role is not None:
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(f'SET LOCAL ROLE "{rls_test_role}"')
                    cur.execute(f"SELECT set_config('{rls.GUC_BYPASS}', 'off', true)")
                    cur.execute(f"SELECT set_config('{rls.GUC_EMPRESAS}', '', true)")
                    assert PoliticaAccesoRol.objects.count() == 0

                    cur.execute(f"SELECT set_config('{rls.GUC_EMPRESAS}', %s, true)", [str(empresa_a.id_empresa)])
                    visibles_a = list(PoliticaAccesoRol.objects.values_list("id_politica", flat=True))
                    assert pol_a.id_politica in visibles_a
                    assert pol_b.id_politica not in visibles_a

                    cur.execute(f"SELECT set_config('{rls.GUC_EMPRESAS}', %s, true)", [str(empresa_b.id_empresa)])
                    visibles_b = list(PoliticaAccesoRol.objects.values_list("id_politica", flat=True))
                    assert pol_b.id_politica in visibles_b
                    assert pol_a.id_politica not in visibles_b

    def test_api_aislamiento_politicas_acceso(self, client_a, empresa_a, empresa_b, user_a):
        from apps.core.models import PoliticaAccesoRol

        rol_a = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Rol API A")
        rol_b = Roles.objects.create(id_empresa=empresa_b, nombre_rol="Rol API B")
        pol_a = PoliticaAccesoRol.objects.create(id_empresa=empresa_a, id_rol=rol_a, modulo="crm", accion="VER")
        pol_b = PoliticaAccesoRol.objects.create(id_empresa=empresa_b, id_rol=rol_b, modulo="crm", accion="VER")

        r_list = client_a.get("/api/core/politicas-acceso/")
        assert r_list.status_code == 200
        items = r_list.data["results"] if "results" in r_list.data else r_list.data
        ids = {row["id_politica"] for row in items}
        assert str(pol_a.id_politica) in ids
        assert str(pol_b.id_politica) not in ids

        assert client_a.get(f"/api/core/politicas-acceso/{pol_b.id_politica}/").status_code == 404

        user_a.is_staff = True
        user_a.save(update_fields=["is_staff"])
        r_cross = client_a.post(
            "/api/core/politicas-acceso/",
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_rol": str(rol_b.id_rol),
                "modulo": "ventas",
                "accion": "VER",
            },
            format="json",
        )
        assert r_cross.status_code == 400


# ---------------------------------------------------------------------------
# 2. Motor RBAC/ABAC, Plantillas, Precedencia Multi-Rol y Auditoría
# ---------------------------------------------------------------------------


class TestAccessStudioYMotorEvaluacion:
    def test_guard_admin_403_plantillas_ambito_y_auditoria(self, client_a, empresa_a, empresa_b, user_a):
        from apps.core.models import RegistroAuditoria, RolPermisos, UsuarioRoles
        from apps.core.services_rbac import enmascarar_campos_sensibles

        rol_cont = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Contador VE")
        rol_vend = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Vendedor VE")

        # 1. Usuario no admin recibe 403 en todas las mutaciones de RBAC/ABAC
        assert not user_a.is_staff
        assert (
            client_a.put(
                f"/api/core/roles/{rol_cont.id_rol}/matriz-acceso/",
                {"politicas": []},
                format="json",
            ).status_code
            == 403
        )
        assert (
            client_a.post(
                f"/api/core/roles/{rol_cont.id_rol}/aplicar-plantilla/",
                {"codigo_plantilla": "CONTADOR_FISCAL"},
                format="json",
            ).status_code
            == 403
        )
        assert (
            client_a.post(
                f"/api/core/roles/{rol_cont.id_rol}/asignar-permisos/",
                {"permisos_ids": []},
                format="json",
            ).status_code
            == 403
        )
        assert (
            client_a.post(
                "/api/core/politicas-acceso/",
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "id_rol": str(rol_cont.id_rol),
                    "modulo": "ventas",
                    "accion": "VER",
                },
                format="json",
            ).status_code
            == 403
        )

        # 2. Admin aplica CONTADOR_FISCAL + catálogo + asignar permisos
        user_a.is_staff = True
        user_a.save(update_fields=["is_staff"])

        r_cat = client_a.get("/api/core/politicas-acceso/catalogo/")
        assert r_cat.status_code == 200
        assert len(r_cat.data["modulos"]) == 12
        assert len(r_cat.data["acciones"]) == 7
        assert len(r_cat.data["plantillas"]) == 4

        r_tpl = client_a.post(
            f"/api/core/roles/{rol_cont.id_rol}/aplicar-plantilla/",
            {"codigo_plantilla": "CONTADOR_FISCAL"},
            format="json",
        )
        assert r_tpl.status_code == 200, r_tpl.data
        assert r_tpl.data["codigo_plantilla"] == "CONTADOR_FISCAL"
        assert RegistroAuditoria.objects.filter(
            id_empresa=empresa_a, tipo_evento="ACCESO_MATRIZ_ACTUALIZADA", id_registro_afectado=str(rol_cont.pk)
        ).exists()

        perm = Permisos.objects.create(
            codigo_permiso="fiscal.ver_libros_test", nombre_permiso="Ver Libros", modulo="fiscal"
        )
        r_perm = client_a.post(
            f"/api/core/roles/{rol_cont.id_rol}/asignar-permisos/",
            {"permisos_ids": [str(perm.id_permiso)]},
            format="json",
        )
        assert r_perm.status_code == 200
        assert RolPermisos.objects.filter(id_rol=rol_cont, id_permiso=perm).exists()

        r_get_mat = client_a.get(f"/api/core/roles/{rol_cont.id_rol}/matriz-acceso/")
        assert r_get_mat.status_code == 200
        assert str(perm.id_permiso) in r_get_mat.data["permisos_asignados"]
        assert len(r_get_mat.data["politicas"]) > 0

        # 3. Operador con CONTADOR_FISCAL: pasa FISCAL, rechaza GERENCIAL y módulo no otorgado
        user_op = UsuariosFactory(username="operador_fiscal", email="op_fiscal@alpha.test", empresa=empresa_a)
        UsuarioRoles.objects.create(id_usuario=user_op, id_rol=rol_cont)
        op_client = APIClient()
        op_client.force_authenticate(user=user_op)

        r_ev_f = op_client.post(
            "/api/core/politicas-acceso/evaluar/",
            {"modulo": "contabilidad", "accion": "VER", "ambito": "FISCAL"},
            format="json",
        )
        assert r_ev_f.status_code == 200
        assert r_ev_f.data["permitido"] is True
        assert r_ev_f.data["ambito_efectivo"] == "FISCAL"

        r_ev_g = op_client.post(
            "/api/core/politicas-acceso/evaluar/",
            {"modulo": "contabilidad", "accion": "VER", "ambito": "GERENCIAL"},
            format="json",
        )
        assert r_ev_g.status_code == 200
        assert r_ev_g.data["permitido"] is False
        assert r_ev_g.data["codigo"] == "AMBITO_NO_AUTORIZADO"

        r_ev_den = op_client.post(
            "/api/core/politicas-acceso/evaluar/",
            {"modulo": "despacho", "accion": "VER"},
            format="json",
        )
        assert r_ev_den.status_code == 200
        assert r_ev_den.data["permitido"] is False
        assert r_ev_den.data["codigo"] == "ACCESO_DENEGADO"

        # 4. Operador VENDEDOR: alcance PROPIO vs EMPRESA y enmascaramiento de campos sensibles
        r_tpl_v = client_a.post(
            f"/api/core/roles/{rol_vend.id_rol}/aplicar-plantilla/",
            {"codigo_plantilla": "VENDEDOR"},
            format="json",
        )
        assert r_tpl_v.status_code == 200
        user_v = UsuariosFactory(username="vendedor_ve", email="vend@alpha.test", empresa=empresa_a)
        UsuarioRoles.objects.create(id_usuario=user_v, id_rol=rol_vend)
        vend_client = APIClient()
        vend_client.force_authenticate(user=user_v)

        r_ev_prop = vend_client.post(
            "/api/core/politicas-acceso/evaluar/",
            {"modulo": "ventas", "accion": "VER", "ambito": "FISCAL", "alcance_requerido": "PROPIO"},
            format="json",
        )
        assert r_ev_prop.status_code == 200
        assert r_ev_prop.data["permitido"] is True
        assert set(["costo_unitario", "costo_reposicion_usd", "margen", "precio_compra"]).issubset(
            set(r_ev_prop.data["campos_ocultos"])
        )

        r_ev_emp = vend_client.post(
            "/api/core/politicas-acceso/evaluar/",
            {"modulo": "ventas", "accion": "VER", "alcance_requerido": "EMPRESA"},
            format="json",
        )
        assert r_ev_emp.status_code == 200
        assert r_ev_emp.data["permitido"] is False
        assert r_ev_emp.data["codigo"] == "ALCANCE_INSUFICIENTE"

        payload_orig = {
            "producto": "Aceite 20W50",
            "precio_venta": "12.50",
            "costo_unitario": "7.00",
            "margen": "44%",
            "detalle": [{"sku": "A1", "costo_reposicion_usd": "7.20", "precio_compra": "6.80"}],
        }
        enmascarado = enmascarar_campos_sensibles(payload_orig, r_ev_prop.data["campos_ocultos"])
        assert "costo_unitario" not in enmascarado
        assert "margen" not in enmascarado
        assert "costo_reposicion_usd" not in enmascarado["detalle"][0]
        assert "precio_compra" not in enmascarado["detalle"][0]
        assert enmascarado["precio_venta"] == "12.50"
        assert "costo_unitario" in payload_orig  # no muta la estructura original

        # Plantillas ALMACENISTA y GERENTE_GENERAL
        assert (
            client_a.post(
                f"/api/core/roles/{rol_vend.id_rol}/aplicar-plantilla/",
                {"codigo_plantilla": "ALMACENISTA"},
                format="json",
            ).status_code
            == 200
        )
        assert (
            client_a.post(
                f"/api/core/roles/{rol_vend.id_rol}/aplicar-plantilla/",
                {"codigo_plantilla": "GERENTE_GENERAL"},
                format="json",
            ).status_code
            == 200
        )

    def test_precedencia_multiroles_opt_in_y_multiempresa(self, client_a, empresa_a, empresa_b, user_a):
        from apps.core.models import PoliticaAccesoRol, UsuarioRoles
        from apps.core.services_rbac import obtener_matriz_acceso_usuario, verificar_acceso

        user_multi = UsuariosFactory(username="multi_rol", email="multi@alpha.test", empresa=empresa_a)
        # Opt-in: usuario sin políticas explícitas mantiene acceso por compatibilidad
        res_sin = verificar_acceso(user_multi, empresa_a, "ventas", "VER")
        assert res_sin["permitido"] is True
        assert res_sin["codigo"] == "SIN_POLITICAS_EXPLICITAS"

        rol_1 = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Rol Fiscal Propio")
        rol_2 = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Rol Gerencial Sucursal")
        PoliticaAccesoRol.objects.create(
            id_empresa=empresa_a,
            id_rol=rol_1,
            modulo="ventas",
            accion="VER",
            ambito="FISCAL",
            alcance="PROPIO",
            permitido=True,
            campos_ocultos=["costo_unitario", "margen"],
        )
        PoliticaAccesoRol.objects.create(
            id_empresa=empresa_a,
            id_rol=rol_2,
            modulo="ventas",
            accion="VER",
            ambito="GERENCIAL",
            alcance="SUCURSAL",
            permitido=True,
            campos_ocultos=["margen", "precio_compra"],
        )
        UsuarioRoles.objects.create(id_usuario=user_multi, id_rol=rol_1)
        UsuarioRoles.objects.create(id_usuario=user_multi, id_rol=rol_2)

        matriz = obtener_matriz_acceso_usuario(user_multi, empresa_a)
        assert matriz["tiene_politicas_explicitas"] is True
        entry = matriz["modulos"]["ventas"]["VER"]
        assert entry["permitido"] is True
        assert entry["ambito"] == "AMBOS"
        assert entry["alcance"] == "SUCURSAL"
        assert entry["campos_ocultos"] == ["margen"]

        # Deny explícito gana sobre cualquier permiso de otro rol
        rol_deny = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Rol Bloqueo")
        PoliticaAccesoRol.objects.create(
            id_empresa=empresa_a,
            id_rol=rol_deny,
            modulo="ventas",
            accion="VER",
            permitido=False,
        )
        UsuarioRoles.objects.create(id_usuario=user_multi, id_rol=rol_deny)
        res_deny = verificar_acceso(user_multi, empresa_a, "ventas", "VER")
        assert res_deny["permitido"] is False
        assert res_deny["codigo"] == "ACCESO_DENEGADO"

        # GET /mi-matriz/ con empresa autorizada vs no autorizada + admin bypass
        user_a.is_staff = True
        user_a.save(update_fields=["is_staff"])
        r_admin = client_a.get("/api/core/politicas-acceso/mi-matriz/")
        assert r_admin.status_code == 200
        assert r_admin.data["es_admin_total"] is True

        assert (
            client_a.get(f"/api/core/politicas-acceso/mi-matriz/?id_empresa={empresa_b.id_empresa}").status_code == 400
        )
        user_a.empresas.add(empresa_b)
        assert (
            client_a.get(f"/api/core/politicas-acceso/mi-matriz/?id_empresa={empresa_b.id_empresa}").status_code == 200
        )


# ---------------------------------------------------------------------------
# 3. HasGranularAccess y Validaciones Negativas / Borde
# ---------------------------------------------------------------------------


class TestHasGranularAccessYValidacionesNegativas:
    def test_has_granular_access_permission_class(self, empresa_a):
        from apps.core.models import PoliticaAccesoRol, UsuarioRoles
        from apps.core.permissions import HasGranularAccess

        perm = HasGranularAccess()
        rf = RequestFactory()

        class ViewSinModulo:
            action = "list"

        class ViewFiscal:
            rbac_modulo = "contabilidad"
            rbac_alcance_requerido = "EMPRESA"
            action = "list"

        # Usuario anónimo
        req_anon = rf.get("/api/x/")
        req_anon.query_params = req_anon.GET
        assert perm.has_permission(req_anon, ViewFiscal()) is False

        user_op = UsuariosFactory(username="perm_op", email="perm_op@alpha.test", empresa=empresa_a)
        rol = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Contabilidad Fiscal")
        PoliticaAccesoRol.objects.create(
            id_empresa=empresa_a,
            id_rol=rol,
            modulo="contabilidad",
            accion="VER",
            ambito="FISCAL",
            alcance="EMPRESA",
            permitido=True,
        )
        UsuarioRoles.objects.create(id_usuario=user_op, id_rol=rol)

        # Vista sin rbac_modulo -> True
        req_opt = rf.get("/api/x/")
        req_opt.user = user_op
        req_opt.query_params = req_opt.GET
        assert perm.has_permission(req_opt, ViewSinModulo()) is True

        # Header X-Empresa-ID malformado -> False limpio (no 500)
        req_bad_hdr = rf.get("/api/x/", HTTP_X_EMPRESA_ID="no-es-uuid")
        req_bad_hdr.user = user_op
        req_bad_hdr.query_params = req_bad_hdr.GET
        assert perm.has_permission(req_bad_hdr, ViewFiscal()) is False

        # Ámbito FISCAL permitido -> True y setea request.rbac_resultado
        req_ok = rf.get("/api/x/?ambito=FISCAL", HTTP_X_EMPRESA_ID=str(empresa_a.id_empresa))
        req_ok.user = user_op
        req_ok.query_params = req_ok.GET
        assert perm.has_permission(req_ok, ViewFiscal()) is True
        assert req_ok.rbac_resultado["ambito_efectivo"] == "FISCAL"

        # Ámbito GERENCIAL rechazado -> False
        req_no = rf.get("/api/x/?ambito=GERENCIAL")
        req_no.user = user_op
        req_no.query_params = req_no.GET
        assert perm.has_permission(req_no, ViewFiscal()) is False
        assert "AMBITO_NO_AUTORIZADO" in perm.message

        # Ámbito desconocido cae en AMBOS; IsAdminOrReadOnly anónimo -> False; usuario sin empresas -> False
        from apps.core.permissions import IsAdminOrReadOnly

        assert IsAdminOrReadOnly().has_permission(req_anon, None) is False
        req_amb_inv = rf.get("/api/x/?ambito=DESCONOCIDO", HTTP_X_EMPRESA_ID=str(empresa_a.id_empresa))
        req_amb_inv.user = user_op
        req_amb_inv.query_params = req_amb_inv.GET
        assert perm.has_permission(req_amb_inv, ViewFiscal()) is True

        user_sin_emp = UsuariosFactory(username="sin_emp_perm", email="sin@alpha.test", empresa=empresa_a)
        user_sin_emp.empresas.clear()
        req_sin_emp = rf.get("/api/x/")
        req_sin_emp.user = user_sin_emp
        req_sin_emp.query_params = req_sin_emp.GET
        assert perm.has_permission(req_sin_emp, ViewFiscal()) is False

    def test_validaciones_modelo_crud_y_errores_400(self, client_a, empresa_a, empresa_b, user_a):
        from apps.core.models import PoliticaAccesoRol
        from apps.core.services_rbac import verificar_acceso

        user_a.is_staff = True
        user_a.save(update_fields=["is_staff"])

        rol_a = Roles.objects.create(id_empresa=empresa_a, nombre_rol="Rol Neg A")
        rol_b = Roles.objects.create(id_empresa=empresa_b, nombre_rol="Rol Neg B")

        # clean() rechaza rol de otra empresa y campos_ocultos inválidos; normaliza duplicados
        pol_bad_emp = PoliticaAccesoRol(id_empresa=empresa_a, id_rol=rol_b, modulo="ventas", accion="VER")
        with pytest.raises(ValidationError):
            pol_bad_emp.full_clean()

        pol_bad_campo = PoliticaAccesoRol(
            id_empresa=empresa_a,
            id_rol=rol_a,
            modulo="ventas",
            accion="VER",
            campos_ocultos=["NoValido!"],
        )
        with pytest.raises(ValidationError):
            pol_bad_campo.full_clean()

        pol_dup = PoliticaAccesoRol(
            id_empresa=empresa_a,
            id_rol=rol_a,
            modulo="ventas",
            accion="VER",
            campos_ocultos=["margen", "margen", "costo_unitario"],
        )
        pol_dup.full_clean()
        assert pol_dup.campos_ocultos == ["margen", "costo_unitario"]

        # CRUD completo en /api/core/politicas-acceso/ + activar/desactivar como admin
        r_create = client_a.post(
            "/api/core/politicas-acceso/",
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_rol": str(rol_a.id_rol),
                "modulo": "ventas",
                "accion": "VER",
                "ambito": "FISCAL",
                "alcance": "PROPIO",
                "campos_ocultos": ["margen", "margen"],
            },
            format="json",
        )
        assert r_create.status_code == 201, r_create.data
        pid = r_create.data["id_politica"]
        assert (
            client_a.patch(f"/api/core/politicas-acceso/{pid}/", {"alcance": "SUCURSAL"}, format="json").status_code
            == 200
        )
        assert client_a.post(f"/api/core/politicas-acceso/{pid}/desactivar/", {}, format="json").status_code == 200
        assert client_a.post(f"/api/core/politicas-acceso/{pid}/activar/", {}, format="json").status_code == 200
        assert client_a.delete(f"/api/core/politicas-acceso/{pid}/").status_code == 204

        # Rutas negativas 400
        assert (
            client_a.post(
                f"/api/core/roles/{rol_a.id_rol}/aplicar-plantilla/",
                {"codigo_plantilla": "INEXISTENTE"},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.put(
                f"/api/core/roles/{rol_a.id_rol}/matriz-acceso/",
                {
                    "politicas": [
                        {"modulo": "ventas", "accion": "VER"},
                        {"modulo": "ventas", "accion": "VER"},
                    ]
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                f"/api/core/roles/{rol_a.id_rol}/asignar-permisos/",
                {"permisos_ids": [str(uuid.uuid4())]},
                format="json",
            ).status_code
            == 400
        )
        assert client_a.get("/api/core/politicas-acceso/?modulo=bad\x00").status_code == 400
        assert client_a.get("/api/core/politicas-acceso/?ambito=FIS\x00CAL").status_code == 400

        # Empresa de rol inconsistente en matriz-acceso
        assert (
            client_a.put(
                f"/api/core/roles/{rol_a.id_rol}/matriz-acceso/",
                {"id_empresa": str(empresa_b.id_empresa), "politicas": []},
                format="json",
            ).status_code
            == 400
        )

        # Enum inválido en verificar_acceso
        with pytest.raises(ValueError, match="Módulo RBAC inválido"):
            verificar_acceso(user_a, empresa_a, "inexistente", "VER")
        with pytest.raises(ValueError, match="Acción RBAC inválida"):
            verificar_acceso(user_a, empresa_a, "ventas", "HACK")
        with pytest.raises(ValueError, match="Ámbito RBAC inválido"):
            verificar_acceso(user_a, empresa_a, "ventas", "VER", ambito="OTRO")
        with pytest.raises(ValueError, match="Alcance RBAC inválido"):
            verificar_acceso(user_a, empresa_a, "ventas", "VER", alcance_requerido="GLOBAL")

        # Cobertura de borde en modelo, serializer y viewsets
        from apps.core.serializers import PoliticaAccesoRolSerializer

        pol_none = PoliticaAccesoRol(
            id_empresa=empresa_a, id_rol=rol_a, modulo="ventas", accion="VER", campos_ocultos=None
        )
        pol_none.clean()
        assert pol_none.campos_ocultos == []
        assert "PERMITIR" in str(pol_none)
        pol_deny_str = PoliticaAccesoRol(
            id_empresa=empresa_a, id_rol=rol_a, modulo="ventas", accion="VER", permitido=False
        )
        assert "DENEGAR" in str(pol_deny_str)

        pol_str_bad = PoliticaAccesoRol(
            id_empresa=empresa_a, id_rol=rol_a, modulo="ventas", accion="VER", campos_ocultos="bad"
        )
        with pytest.raises(ValidationError):
            pol_str_bad.clean()

        ser_helper = PoliticaAccesoRolSerializer()
        assert ser_helper.validate_campos_ocultos(None) == []

        for bad_campos in ("no-list", ["Invalido!"]):
            ser_bad = PoliticaAccesoRolSerializer(
                data={
                    "id_empresa": str(empresa_a.id_empresa),
                    "id_rol": str(rol_a.id_rol),
                    "modulo": "ventas",
                    "accion": "VER",
                    "campos_ocultos": bad_campos,
                }
            )
            assert not ser_bad.is_valid()

        ser_cross = PoliticaAccesoRolSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "id_rol": str(rol_b.id_rol),
                "modulo": "ventas",
                "accion": "VER",
            }
        )
        assert not ser_cross.is_valid()

        # Filtros, X-Forwarded-For, id_empresa ajeno en plantilla, y usuario sin empresas
        assert (
            client_a.post(
                f"/api/core/roles/{rol_a.id_rol}/aplicar-plantilla/",
                {"codigo_plantilla": "VENDEDOR"},
                format="json",
                HTTP_X_FORWARDED_FOR="10.0.0.1, 10.0.0.2",
            ).status_code
            == 200
        )
        assert (
            client_a.get(f"/api/core/politicas-acceso/?id_rol={rol_a.id_rol}&modulo=ventas&ambito=AMBOS").status_code
            == 200
        )
        assert (
            client_a.post(
                f"/api/core/roles/{rol_a.id_rol}/aplicar-plantilla/",
                {"id_empresa": str(empresa_b.id_empresa), "codigo_plantilla": "VENDEDOR"},
                format="json",
            ).status_code
            == 400
        )

        user_zero = UsuariosFactory(username="sin_emp_view", email="zero@alpha.test", empresa=empresa_a)
        user_zero.empresas.clear()
        zero_client = APIClient()
        zero_client.force_authenticate(user=user_zero)
        assert zero_client.get("/api/core/politicas-acceso/mi-matriz/").status_code == 400
