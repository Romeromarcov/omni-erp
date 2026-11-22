"""Tests de API REST para diarios contables, reversión por contra-asiento,
períodos contables y cierre de ejercicio (PR-13 · B1).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.contabilidad.models import AsientoContable, DetalleAsiento, DiarioContable, PeriodoContable, PlanCuentas
from apps.contabilidad.serializers import (
    AsientoContableSerializer,
    DetalleAsientoSerializer,
    DiarioContableSerializer,
    MapeoContableSerializer,
    PeriodoContableSerializer,
)
from apps.core.models import Contacto
from apps.finanzas.models import Caja, CuentaBancariaEmpresa

pytestmark = pytest.mark.django_db

URL_PLAN = "/api/contabilidad/plan-cuentas/"
URL_DIARIOS = "/api/contabilidad/diarios/"
URL_PERIODOS = "/api/contabilidad/periodos-contables/"
URL_ASIENTOS = "/api/contabilidad/asientos-contables/"
URL_DETALLES = "/api/contabilidad/detalles-asiento/"
URL_MAPEOS = "/api/contabilidad/mapeos-contables/"


def _cuenta(empresa, codigo: str, nombre: str, tipo: str = "ACTIVO", naturaleza: str = "DEUDORA") -> PlanCuentas:
    return PlanCuentas.objects.create(
        id_empresa=empresa,
        codigo_cuenta=codigo,
        nombre_cuenta=nombre,
        tipo_cuenta=tipo,
        naturaleza=naturaleza,
        nivel=2,
    )


class TestDiarioContableAPI:
    def test_crud_y_aislamiento_anti_idor(self, client_a, client_b, empresa_a, empresa_b, moneda_usd):
        assert APIClient().get(URL_DIARIOS).status_code == 401

        cta_debe = _cuenta(empresa_a, "1.1.01", "Caja")
        cta_haber = _cuenta(empresa_a, "4.1.01", "Ventas", tipo="INGRESO", naturaleza="ACREEDORA")
        cta_b = _cuenta(empresa_b, "1.1.01", "Caja B")
        banco_b = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_b,
            nombre_banco="Banco B",
            numero_cuenta="0102-9999-8888",
            tipo_cuenta="CORRIENTE",
            id_moneda=moneda_usd,
        )
        caja_b = Caja.objects.create(empresa=empresa_b, nombre="Caja B", moneda=moneda_usd)

        # Creación válida
        resp = client_a.post(
            URL_DIARIOS,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "codigo": "VTA",
                "nombre": "Diario Ventas",
                "tipo": "VENTAS",
                "prefijo_secuencia": "FV",
                "siguiente_numero": 1,
                "cuenta_defecto_debe": str(cta_debe.pk),
                "cuenta_defecto_haber": str(cta_haber.pk),
            },
            format="json",
        )
        assert resp.status_code == 201, resp.content
        diario_id = resp.json()["id_diario"]

        # Aislamiento: B no ve ni edita ni elimina el diario de A
        assert client_b.get(URL_DIARIOS).json()["count"] == 0
        assert client_b.get(f"{URL_DIARIOS}{diario_id}/").status_code == 404
        assert client_b.patch(f"{URL_DIARIOS}{diario_id}/", {"nombre": "Hack"}, format="json").status_code == 404
        assert client_b.delete(f"{URL_DIARIOS}{diario_id}/").status_code == 404

        # Cross-tenant FKs rechazados (400)
        assert (
            client_a.post(
                URL_DIARIOS,
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "codigo": "BAD1",
                    "nombre": "Bad",
                    "tipo": "VARIOS",
                    "cuenta_defecto_debe": str(cta_b.pk),
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                URL_DIARIOS,
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "codigo": "BAD2",
                    "nombre": "Bad",
                    "tipo": "BANCO",
                    "id_cuenta_bancaria": str(banco_b.pk),
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                URL_DIARIOS,
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "codigo": "BAD3",
                    "nombre": "Bad",
                    "tipo": "CAJA",
                    "id_caja": str(caja_b.pk),
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                URL_DIARIOS,
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "codigo": "BAD4",
                    "nombre": "Bad",
                    "tipo": "VARIOS",
                    "siguiente_numero": 0,
                },
                format="json",
            ).status_code
            == 400
        )

        # Editar y soft-delete (activo=False)
        patch_resp = client_a.patch(f"{URL_DIARIOS}{diario_id}/", {"nombre": "Ventas Principal"}, format="json")
        assert patch_resp.status_code == 200
        assert patch_resp.json()["nombre"] == "Ventas Principal"

        del_resp = client_a.delete(f"{URL_DIARIOS}{diario_id}/")
        assert del_resp.status_code == 204
        diario_db = DiarioContable.objects.get(pk=diario_id)
        assert diario_db.activo is False


class TestAsientosReversionYValidacionesAPI:
    def test_aprobar_anular_revertir_y_validaciones_cross_tenant(self, client_a, client_b, empresa_a, empresa_b):
        c1 = _cuenta(empresa_a, "1.1.01", "Caja")
        c2 = _cuenta(empresa_a, "4.1.01", "Ventas", tipo="INGRESO", naturaleza="ACREEDORA")
        diario_b = DiarioContable.objects.create(id_empresa=empresa_b, codigo="DB", nombre="Diario B", tipo="VARIOS")
        contacto_a = Contacto.objects.create(id_empresa=empresa_a, nombre="Cliente A", rif="J-11111111-1")
        contacto_b = Contacto.objects.create(id_empresa=empresa_b, nombre="Cliente B", rif="J-22222222-2")

        # Asiento con diario ajeno rechazado
        r_bad_asiento = client_a.post(
            URL_ASIENTOS,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "id_diario": str(diario_b.pk),
                "fecha_asiento": "2026-06-15",
                "numero_asiento": "AS-BAD",
                "descripcion": "Bad",
                "estado_asiento": "BORRADOR",
            },
            format="json",
        )
        assert r_bad_asiento.status_code == 400

        # Mapeo con diario ajeno rechazado
        r_bad_mapeo = client_a.post(
            URL_MAPEOS,
            {
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_asiento": "FACTURA_VENTA",
                "id_diario": str(diario_b.pk),
                "cuenta_debe": str(c1.pk),
                "cuenta_haber": str(c2.pk),
            },
            format="json",
        )
        assert r_bad_mapeo.status_code == 400

        asiento = AsientoContable.objects.create(
            id_empresa=empresa_a,
            fecha_asiento=datetime.date(2026, 6, 15),
            numero_asiento="AS-API-1",
            descripcion="Venta API",
            estado_asiento="BORRADOR",
        )

        # Detalle con contacto ajeno rechazado
        r_bad_det = client_a.post(
            URL_DETALLES,
            {
                "id_asiento": str(asiento.pk),
                "id_cuenta_contable": str(c1.pk),
                "id_contacto": str(contacto_b.pk),
                "debe": "50.00",
                "haber": "0.00",
            },
            format="json",
        )
        assert r_bad_det.status_code == 400

        # Aprobar con 1 sola línea -> 400
        DetalleAsiento.objects.create(
            id_asiento=asiento, id_cuenta_contable=c1, id_contacto=contacto_a, debe=Decimal("100.00")
        )
        assert client_a.post(f"{URL_ASIENTOS}{asiento.pk}/aprobar/", {}, format="json").status_code == 400

        # Completar cuadre y aprobar
        DetalleAsiento.objects.create(
            id_asiento=asiento, id_cuenta_contable=c2, id_contacto=contacto_a, haber=Decimal("100.00")
        )
        r_aprobar = client_a.post(f"{URL_ASIENTOS}{asiento.pk}/aprobar/", {}, format="json")
        assert r_aprobar.status_code == 200
        assert r_aprobar.json()["estado_asiento"] == "APROBADO"
        assert r_aprobar.json()["contra_asiento_id"] is None

        # Anular asiento APROBADO falla con 400 indicando usar 'revertir'
        r_anular_aprob = client_a.post(f"{URL_ASIENTOS}{asiento.pk}/anular/", {}, format="json")
        assert r_anular_aprob.status_code == 400
        assert "revertir" in r_anular_aprob.json()["error"].lower()

        # Revertir por B falla con 404 (anti-IDOR)
        assert client_b.post(f"{URL_ASIENTOS}{asiento.pk}/revertir/", {}, format="json").status_code == 404

        # Revertir por A crea contra-asiento (201)
        r_rev = client_a.post(
            f"{URL_ASIENTOS}{asiento.pk}/revertir/",
            {"motivo": "Error de digitación", "fecha_reversion": "2026-06-16"},
            format="json",
        )
        assert r_rev.status_code == 201, r_rev.content
        contra_data = r_rev.json()
        assert contra_data["asiento_revertido"] == str(asiento.pk)
        assert contra_data["estado_asiento"] == "APROBADO"
        assert contra_data["fecha_asiento"] == "2026-06-16"

        # Original ahora expone contra_asiento_id
        det_orig = client_a.get(f"{URL_ASIENTOS}{asiento.pk}/").json()
        assert det_orig["contra_asiento_id"] == contra_data["id_asiento"]

        # Doble reversión -> 400
        assert client_a.post(f"{URL_ASIENTOS}{asiento.pk}/revertir/", {}, format="json").status_code == 400


class TestPeriodosYCierreEjercicioAPI:
    def test_cerrar_reabrir_cerrar_ejercicio_y_anti_idor(self, client_a, client_b, empresa_a, empresa_b):
        c_caja = _cuenta(empresa_a, "1.1.01", "Caja")
        c_ing = _cuenta(empresa_a, "4.1.01", "Ventas", tipo="INGRESO", naturaleza="ACREEDORA")
        c_pat = _cuenta(empresa_a, "3.2.01", "Utilidades", tipo="PATRIMONIO", naturaleza="ACREEDORA")

        # Validación de mes inválido en serializer -> 400 (no 500 CheckConstraint)
        r_bad_mes = client_a.post(
            URL_PERIODOS,
            {"id_empresa": str(empresa_a.id_empresa), "anio": 2026, "mes": 13},
            format="json",
        )
        assert r_bad_mes.status_code == 400

        # Cerrar período por acción de colección (empresa ajena -> 404)
        assert (
            client_b.post(
                f"{URL_PERIODOS}cerrar/",
                {"id_empresa": str(empresa_a.id_empresa), "anio": 2026, "mes": 5},
                format="json",
            ).status_code
            == 404
        )
        r_cerrar = client_a.post(
            f"{URL_PERIODOS}cerrar/",
            {"id_empresa": str(empresa_a.id_empresa), "anio": 2026, "mes": 5, "observaciones": "Mayo OK"},
            format="json",
        )
        assert r_cerrar.status_code == 200, r_cerrar.content
        pid = r_cerrar.json()["id_periodo"]
        assert r_cerrar.json()["estado"] == "CERRADO"

        # Eliminar período cerrado -> 400
        assert client_a.delete(f"{URL_PERIODOS}{pid}/").status_code == 400

        # Reabrir por B -> 404; reabrir por A -> 200; cerrar por detail -> 200
        assert client_b.post(f"{URL_PERIODOS}{pid}/reabrir/", {}, format="json").status_code == 404
        r_reabrir = client_a.post(f"{URL_PERIODOS}{pid}/reabrir/", {"motivo": "Ajuste"}, format="json")
        assert r_reabrir.status_code == 200
        assert r_reabrir.json()["estado"] == "ABIERTO"

        r_cerrar_det = client_a.post(f"{URL_PERIODOS}{pid}/cerrar/", {"observaciones": "Re-cierre"}, format="json")
        assert r_cerrar_det.status_code == 200
        assert r_cerrar_det.json()["estado"] == "CERRADO"

        # Asiento aprobado en 2025 para cierre anual
        asiento = AsientoContable.objects.create(
            id_empresa=empresa_a,
            fecha_asiento=datetime.date(2025, 6, 1),
            numero_asiento="AS-2025-1",
            descripcion="Venta 2025",
            estado_asiento="APROBADO",
        )
        DetalleAsiento.objects.create(id_asiento=asiento, id_cuenta_contable=c_caja, debe=Decimal("500.00"))
        DetalleAsiento.objects.create(id_asiento=asiento, id_cuenta_contable=c_ing, haber=Decimal("500.00"))

        # Cierre ejercicio: empresa ajena -> 404; cuenta no-PATRIMONIO -> 400
        assert (
            client_b.post(
                f"{URL_PERIODOS}cerrar-ejercicio/",
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "anio": 2025,
                    "cuenta_resultado_acumulado": str(c_pat.pk),
                },
                format="json",
            ).status_code
            == 404
        )
        assert (
            client_a.post(
                f"{URL_PERIODOS}cerrar-ejercicio/",
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "anio": 2025,
                    "cuenta_resultado_acumulado": str(c_caja.pk),
                },
                format="json",
            ).status_code
            == 400
        )

        r_ej = client_a.post(
            f"{URL_PERIODOS}cerrar-ejercicio/",
            {
                "id_empresa": str(empresa_a.id_empresa),
                "anio": 2025,
                "cuenta_resultado_acumulado": str(c_pat.pk),
            },
            format="json",
        )
        assert r_ej.status_code == 200, r_ej.content
        body_ej = r_ej.json()
        assert body_ej["anio"] == 2025
        assert Decimal(body_ej["resultado_ejercicio"]) == Decimal("500.00")
        assert body_ej["asiento_cierre"]["es_cierre"] is True
        assert len(body_ej["periodos_cerrados"]) == 12

        # Doble cierre anual -> 400
        assert (
            client_a.post(
                f"{URL_PERIODOS}cerrar-ejercicio/",
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "anio": 2025,
                    "cuenta_resultado_acumulado": str(c_pat.pk),
                },
                format="json",
            ).status_code
            == 400
        )

        # Eliminar período ABIERTO hace soft_delete
        p_abierto = PeriodoContable.objects.create(id_empresa=empresa_a, anio=2027, mes=1, estado="ABIERTO")
        assert client_a.delete(f"{URL_PERIODOS}{p_abierto.pk}/").status_code == 204
        p_abierto.refresh_from_db()
        assert p_abierto.activo is False


class TestSchemathesisSanitizacionQueryParams:
    def test_nul_bytes_y_uuid_invalido_devuelven_400_no_500(self, client_a):
        for url in (URL_PLAN, URL_DIARIOS, URL_PERIODOS, URL_ASIENTOS, URL_DETALLES, URL_MAPEOS):
            assert client_a.get(f"{url}?search=%00abc").status_code == 400
            assert client_a.get(f"{url}?search=ok").status_code == 200

        assert client_a.get(f"{URL_PLAN}por_tipo/?tipo=%00").status_code == 400
        assert client_a.get(f"{URL_ASIENTOS}balance_comprobacion/?empresa_id=not-a-uuid").status_code == 400
        assert client_a.get(f"{URL_ASIENTOS}balance_comprobacion/?empresa_id=%00").status_code == 400


class TestValidacionesDefensivasSerializersYViewsB1:
    def test_serializers_cross_tenant_sin_contexto_request(self, empresa_a, empresa_b, moneda_usd):
        cta_a = _cuenta(empresa_a, "1.1.90", "Caja A")
        cta_b = _cuenta(empresa_b, "1.1.90", "Caja B")
        banco_b = CuentaBancariaEmpresa.objects.create(
            id_empresa=empresa_b,
            nombre_banco="Banco Ajeno",
            numero_cuenta="0102-0000-0001",
            tipo_cuenta="CORRIENTE",
            id_moneda=moneda_usd,
        )
        caja_b = Caja.objects.create(empresa=empresa_b, nombre="Caja Ajena", moneda=moneda_usd)
        diario_b = DiarioContable.objects.create(id_empresa=empresa_b, codigo="DB2", nombre="Diario B2", tipo="VARIOS")
        contacto_a = Contacto.objects.create(id_empresa=empresa_a, nombre="Cli A", rif="J-10101010-1")
        contacto_b = Contacto.objects.create(id_empresa=empresa_b, nombre="Cli B", rif="J-20202020-2")

        s_cta = DiarioContableSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "codigo": "D1",
                "nombre": "D1",
                "tipo": "VARIOS",
                "cuenta_defecto_debe": str(cta_b.pk),
            }
        )
        assert not s_cta.is_valid()
        assert "cuenta_defecto_debe" in s_cta.errors

        s_banco = DiarioContableSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "codigo": "D2",
                "nombre": "D2",
                "tipo": "BANCO",
                "id_cuenta_bancaria": str(banco_b.pk),
            }
        )
        assert not s_banco.is_valid()
        assert "id_cuenta_bancaria" in s_banco.errors

        s_caja = DiarioContableSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "codigo": "D3",
                "nombre": "D3",
                "tipo": "CAJA",
                "id_caja": str(caja_b.pk),
            }
        )
        assert not s_caja.is_valid()
        assert "id_caja" in s_caja.errors

        s_asiento = AsientoContableSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "id_diario": str(diario_b.pk),
                "fecha_asiento": "2026-06-01",
                "numero_asiento": "AS-SER-1",
                "descripcion": "Test",
                "estado_asiento": "BORRADOR",
            }
        )
        assert not s_asiento.is_valid()
        assert "id_diario" in s_asiento.errors

        s_mapeo = MapeoContableSerializer(
            data={
                "id_empresa": str(empresa_a.id_empresa),
                "tipo_asiento": "FACTURA_VENTA",
                "id_diario": str(diario_b.pk),
                "cuenta_debe": str(cta_a.pk),
                "cuenta_haber": str(cta_a.pk),
            }
        )
        assert not s_mapeo.is_valid()
        assert "id_diario" in s_mapeo.errors

        asiento_a = AsientoContable.objects.create(
            id_empresa=empresa_a,
            fecha_asiento=datetime.date(2026, 6, 1),
            numero_asiento="AS-SER-2",
            descripcion="Test",
            estado_asiento="BORRADOR",
        )
        s_det_cta = DetalleAsientoSerializer(
            data={
                "id_asiento": str(asiento_a.pk),
                "id_cuenta_contable": str(cta_b.pk),
                "debe": "10.00",
                "haber": "0.00",
            }
        )
        assert not s_det_cta.is_valid()
        assert "id_cuenta_contable" in s_det_cta.errors

        s_det_cnt = DetalleAsientoSerializer(
            data={
                "id_asiento": str(asiento_a.pk),
                "id_cuenta_contable": str(cta_a.pk),
                "id_contacto": str(contacto_b.pk),
                "debe": "10.00",
                "haber": "0.00",
            }
        )
        assert not s_det_cnt.is_valid()
        assert "id_contacto" in s_det_cnt.errors

        s_det_ok = DetalleAsientoSerializer(
            data={
                "id_asiento": str(asiento_a.pk),
                "id_cuenta_contable": str(cta_a.pk),
                "id_contacto": str(contacto_a.pk),
                "debe": "10.00",
                "haber": "0.00",
            }
        )
        assert s_det_ok.is_valid(), s_det_ok.errors

        s_per_anio = PeriodoContableSerializer(data={"id_empresa": str(empresa_a.id_empresa), "anio": 1800, "mes": 6})
        assert not s_per_anio.is_valid()
        assert "anio" in s_per_anio.errors

    def test_periodos_views_errores_400_borrador_reabrir_abierto_y_cuenta_ajena(self, client_a, empresa_a, empresa_b):
        c_caja = _cuenta(empresa_a, "1.1.95", "Caja Views")
        c_pat_b = _cuenta(empresa_b, "3.2.95", "Patrimonio B", tipo="PATRIMONIO", naturaleza="ACREEDORA")

        # Borrador en 2026-09 impide cerrar tanto por colección como por detalle
        AsientoContable.objects.create(
            id_empresa=empresa_a,
            fecha_asiento=datetime.date(2026, 9, 10),
            numero_asiento="AS-BOR-SEP",
            descripcion="Borrador pendiente",
            estado_asiento="BORRADOR",
        )
        r_cerrar_col = client_a.post(
            f"{URL_PERIODOS}cerrar/",
            {"id_empresa": str(empresa_a.id_empresa), "anio": 2026, "mes": 9},
            format="json",
        )
        assert r_cerrar_col.status_code == 400

        per_sep = PeriodoContable.objects.create(id_empresa=empresa_a, anio=2026, mes=9, estado="ABIERTO")
        assert client_a.post(f"{URL_PERIODOS}{per_sep.pk}/cerrar/", {}, format="json").status_code == 400
        assert client_a.post(f"{URL_PERIODOS}{per_sep.pk}/reabrir/", {}, format="json").status_code == 400

        # Cuenta patrimonio ajena -> TenantFKScope/lookup devuelve 400
        assert (
            client_a.post(
                f"{URL_PERIODOS}cerrar-ejercicio/",
                {
                    "id_empresa": str(empresa_a.id_empresa),
                    "anio": 2026,
                    "cuenta_resultado_acumulado": str(c_pat_b.pk),
                },
                format="json",
            ).status_code
            == 400
        )
        # Mantener c_caja usado para evitar warning de variable sin usar
        assert c_caja.pk is not None
