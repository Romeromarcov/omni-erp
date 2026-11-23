"""Tests de integración Plan 09 Ola 3B: Nómina Dual VE (LOTTT + Paquete Objetivo/Bonificaciones)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.core import rls

pytestmark = [pytest.mark.django_db]


# ---------------------------------------------------------------------------
# 1. PostgreSQL RLS en las 3 tablas nuevas + modelos Dual VE
# ---------------------------------------------------------------------------


class TestRLSYModelosNominaDual:
    def test_rls_tres_tablas_y_validaciones_modelo(self, rls_test_role, empresa_a, empresa_b, moneda_usd):
        from apps.nomina.models import (
            DispersionPagoNomina,
            FichaSalarialDual,
            Nomina,
            PeriodoNomina,
            PrestamoEmpleado,
            ProcesoNomina,
        )
        from apps.rrhh.models import Empleado

        with connection.cursor() as cur:
            for tabla in (
                "nomina_ficha_salarial_dual",
                "nomina_prestamo_empleado",
                "nomina_dispersion_pago",
            ):
                cur.execute(
                    "SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename=%s",
                    [tabla],
                )
                assert cur.fetchone()[0] >= 1, f"Falta política RLS en {tabla}"

        emp_a = Empleado.objects.create(
            empresa=empresa_a, nombre="Carlos", apellido="Mendoza", cedula="V-10111222", fecha_ingreso=date(2021, 3, 1)
        )
        emp_b = Empleado.objects.create(
            empresa=empresa_b, nombre="Luis", apellido="Rojas", cedula="V-20222333", fecha_ingreso=date(2022, 5, 1)
        )
        ficha_a = FichaSalarialDual.objects.create(
            id_empresa=empresa_a,
            id_empleado=emp_a,
            salario_base_formal_ves=Decimal("4500.0000"),
            cestaticket_mensual_ves=Decimal("1800.0000"),
            paquete_objetivo_mensual=Decimal("400.0000"),
            moneda_paquete=moneda_usd,
        )
        ficha_b = FichaSalarialDual.objects.create(
            id_empresa=empresa_b,
            id_empleado=emp_b,
            salario_base_formal_ves=Decimal("3000.0000"),
            paquete_objetivo_mensual=Decimal("250.0000"),
            moneda_paquete=moneda_usd,
        )
        pres_a = PrestamoEmpleado.objects.create(
            id_empresa=empresa_a,
            id_empleado=emp_a,
            ambito_descuento="GERENCIAL",
            moneda=moneda_usd,
            monto_principal=Decimal("100.0000"),
            cuotas_totales=2,
            monto_cuota=Decimal("50.0000"),
            saldo_pendiente=Decimal("100.0000"),
            fecha_otorgamiento=date(2026, 11, 1),
        )
        assert "FichaDual" in str(ficha_a)
        assert "Prestamo" in str(pres_a)

        per_a = PeriodoNomina.objects.create(
            id_empresa=empresa_a,
            nombre_periodo="Nov 2026 RLS",
            fecha_inicio=date(2026, 11, 1),
            fecha_fin=date(2026, 11, 15),
            fecha_pago=date(2026, 11, 15),
            tipo_periodo="QUINCENAL",
        )
        proc_a = ProcesoNomina.objects.create(
            id_empresa=empresa_a,
            id_periodo_nomina=per_a,
            numero_proceso="NP-RLS-1",
            fecha_proceso=timezone.now(),
        )
        nom_a = Nomina.objects.create(
            id_proceso_nomina=proc_a,
            id_empleado=emp_a,
            sueldo_base=Decimal("4500.0000"),
            total_devengado=Decimal("2250.0000"),
            total_neto=Decimal("2000.0000"),
            fecha_calculo=timezone.now(),
        )
        disp_a = DispersionPagoNomina.objects.create(
            id_empresa=empresa_a,
            id_proceso_nomina=proc_a,
            id_nomina=nom_a,
            id_empleado=emp_a,
            monto=Decimal("2000.0000"),
        )
        assert "Disp(" in str(disp_a)

        # Validaciones cross-empresa clean()
        with pytest.raises(ValidationError):
            FichaSalarialDual(id_empresa=empresa_a, id_empleado=emp_b).clean()
        with pytest.raises(ValidationError):
            PrestamoEmpleado(
                id_empresa=empresa_a,
                id_empleado=emp_b,
                monto_principal=Decimal("10"),
                monto_cuota=Decimal("10"),
                saldo_pendiente=Decimal("10"),
                fecha_otorgamiento=date(2026, 11, 1),
            ).clean()
        with pytest.raises(ValidationError):
            DispersionPagoNomina(
                id_empresa=empresa_a, id_proceso_nomina=proc_a, id_nomina=nom_a, id_empleado=emp_b, monto=Decimal("10")
            ).clean()
        per_b = PeriodoNomina.objects.create(
            id_empresa=empresa_b,
            nombre_periodo="Nov 2026 B",
            fecha_inicio=date(2026, 11, 1),
            fecha_fin=date(2026, 11, 15),
            fecha_pago=date(2026, 11, 15),
            tipo_periodo="QUINCENAL",
        )
        proc_b = ProcesoNomina.objects.create(
            id_empresa=empresa_b, id_periodo_nomina=per_b, numero_proceso="NP-RLS-B", fecha_proceso=timezone.now()
        )
        with pytest.raises(ValidationError):
            DispersionPagoNomina(
                id_empresa=empresa_a, id_proceso_nomina=proc_b, id_nomina=nom_a, id_empleado=emp_a, monto=Decimal("10")
            ).clean()

        # Aislamiento RLS real bajo rol sin BYPASSRLS
        if rls_test_role is not None:
            with transaction.atomic(), connection.cursor() as cur:
                cur.execute(f'SET LOCAL ROLE "{rls_test_role}"')
                cur.execute(f"SELECT set_config('{rls.GUC_BYPASS}', 'off', true)")
                cur.execute(f"SELECT set_config('{rls.GUC_EMPRESAS}', '', true)")
                assert FichaSalarialDual.objects.count() == 0
                assert PrestamoEmpleado.objects.count() == 0
                assert DispersionPagoNomina.objects.count() == 0

                cur.execute(f"SELECT set_config('{rls.GUC_EMPRESAS}', %s, true)", [str(empresa_a.pk)])
                assert list(FichaSalarialDual.objects.values_list("pk", flat=True)) == [ficha_a.pk]
                assert ficha_b.pk not in list(FichaSalarialDual.objects.values_list("pk", flat=True))
                assert PrestamoEmpleado.objects.count() == 1
                assert DispersionPagoNomina.objects.count() == 1


# ---------------------------------------------------------------------------
# 2. Flujo E2E Nómina Dual VE + Asistencia + Préstamos + Arqueo USD + Contabilidad Dual
# ---------------------------------------------------------------------------


class TestNominaDualCompletaYExportadoresVE:
    def test_procesar_nomina_dual_contabilidad_asistencia_prestamos_y_exportadores(
        self, client_a, client_b, empresa_a, empresa_b, moneda_usd, user_a
    ):
        from apps.contabilidad.models import AsientoContable, MapeoContable, PeriodoContable, PlanCuentas
        from apps.control_asistencia.models import ResumenAsistenciaDiario
        from apps.nomina.models import DispersionPagoNomina, Nomina, PeriodoNomina, PrestamoEmpleado, ProcesoNomina
        from apps.rrhh.models import Empleado
        from tests.factories import MonedaFactory

        moneda_ves = MonedaFactory(codigo_iso="VES", nombre="Bolívar", simbolo="Bs")
        empresa_a.id_moneda_base = moneda_usd
        empresa_a.id_moneda_pais = moneda_ves
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["id_moneda_base", "id_moneda_pais", "contabilidad_activa"])

        hoy = timezone.localdate()
        PeriodoContable.objects.create(id_empresa=empresa_a, anio=hoy.year, mes=hoy.month, estado="ABIERTO")
        cta_gasto = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="6.1.01.01",
            nombre_cuenta="Gastos de Nómina",
            tipo_cuenta="GASTO",
            naturaleza="DEUDORA",
            nivel=4,
        )
        cta_pasivo = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="2.1.02.01",
            nombre_cuenta="Nómina por Pagar",
            tipo_cuenta="PASIVO",
            naturaleza="ACREEDORA",
            nivel=4,
        )
        MapeoContable.objects.create(
            id_empresa=empresa_a, tipo_asiento="NOMINA", cuenta_debe=cta_gasto, cuenta_haber=cta_pasivo
        )
        MapeoContable.objects.create(
            id_empresa=empresa_a, tipo_asiento="NOMINA_GERENCIAL", cuenta_debe=cta_gasto, cuenta_haber=cta_pasivo
        )

        # Empleados + Ficha Dual via API
        emp1 = Empleado.objects.create(
            empresa=empresa_a, nombre="Ana", apellido="Vargas", cedula="V-14555666", fecha_ingreso=date(2020, 1, 10)
        )
        emp2 = Empleado.objects.create(
            empresa=empresa_a, nombre="Pedro", apellido="Silva", cedula="V-18777888", fecha_ingreso=date(2024, 6, 1)
        )

        r_f1 = client_a.post(
            "/api/nomina/fichas-salariales-dual/",
            {
                "id_empresa": str(empresa_a.pk),
                "id_empleado": str(emp1.pk),
                "salario_base_formal_ves": "4500.0000",
                "cestaticket_mensual_ves": "1800.0000",
                "porcentaje_ari": "5.00",
                "banco_formal": "BANESCO",
                "cuenta_bancaria_formal": "01340011223344556677",
                "paquete_objetivo_mensual": "400.0000",
                "moneda_paquete": str(moneda_usd.pk),
                "bono_fijo_gerencial": "50.0000",
                "canal_pago_gerencial": "EFECTIVO_USD",
                "referencia_pago_gerencial": "Sobre Efectivo",
            },
            format="json",
        )
        assert r_f1.status_code == 201, r_f1.data
        r_f2 = client_a.post(
            "/api/nomina/fichas-salariales-dual/",
            {
                "id_empresa": str(empresa_a.pk),
                "id_empleado": str(emp2.pk),
                "salario_base_formal_ves": "9000.0000",
                "cestaticket_mensual_ves": "1800.0000",
                "porcentaje_ari": "0.00",
                "banco_formal": "MERCANTIL",
                "cuenta_bancaria_formal": "01050011223344556677",
                "paquete_objetivo_mensual": "300.0000",
                "moneda_paquete": str(moneda_usd.pk),
                "canal_pago_gerencial": "ZELLE",
                "referencia_pago_gerencial": "pedro@zelle.test",
            },
            format="json",
        )
        assert r_f2.status_code == 201

        assert client_a.get("/api/nomina/fichas-salariales-dual/?canal_pago_gerencial=EFECTIVO_USD").data["count"] == 1

        # Novedades de asistencia para emp1 (2 horas extra diurnas) y emp2 (1 ausencia)
        per = PeriodoNomina.objects.create(
            id_empresa=empresa_a,
            nombre_periodo="1ra Quincena Nov 2026",
            fecha_inicio=date(hoy.year, hoy.month, 1),
            fecha_fin=date(hoy.year, hoy.month, 15),
            fecha_pago=date(hoy.year, hoy.month, 15),
            tipo_periodo="QUINCENAL",
            estado="ABIERTO",
        )
        ResumenAsistenciaDiario.objects.create(
            id_empleado=emp1,
            fecha=date(hoy.year, hoy.month, 2),
            horas_trabajadas_netas=Decimal("8.00"),
            horas_extras_normal=Decimal("2.00"),
        )
        ResumenAsistenciaDiario.objects.create(
            id_empleado=emp2,
            fecha=date(hoy.year, hoy.month, 3),
            es_ausencia=True,
        )

        # Préstamos: emp1 gerencial 1 sola cuota (se marca PAGADO al procesar); emp2 pendiente en empresa_b no se toca
        r_p1 = client_a.post(
            "/api/nomina/prestamos-empleados/",
            {
                "id_empresa": str(empresa_a.pk),
                "id_empleado": str(emp1.pk),
                "ambito_descuento": "GERENCIAL",
                "moneda": str(moneda_usd.pk),
                "monto_principal": "25.0000",
                "cuotas_totales": 1,
                "monto_cuota": "25.0000",
                "saldo_pendiente": "25.0000",
                "fecha_otorgamiento": per.fecha_inicio.isoformat(),
            },
            format="json",
        )
        assert r_p1.status_code == 201
        pres_1_id = r_p1.data["id_prestamo"]

        # Procesar nómina dual con Idempotency-Key (y verificar replay)
        payload_dual = {
            "id_empresa": str(empresa_a.pk),
            "id_periodo_nomina": str(per.pk),
            "tasa_bcv": "45.00000000",
            "incluir_asistencia": True,
            "amortizar_prestamos": True,
            "generar_dispersion": True,
        }
        r_run1 = client_a.post(
            "/api/nomina/procesos-nomina/procesar-dual/",
            payload_dual,
            format="json",
            HTTP_IDEMPOTENCY_KEY="nom-dual-run-1",
        )
        assert r_run1.status_code == 201, r_run1.data
        r_run2 = client_a.post(
            "/api/nomina/procesos-nomina/procesar-dual/",
            payload_dual,
            format="json",
            HTTP_IDEMPOTENCY_KEY="nom-dual-run-1",
        )
        assert r_run2.status_code == 201
        assert r_run1.data["proceso_fiscal"]["id_proceso_nomina"] == r_run2.data["proceso_fiscal"]["id_proceso_nomina"]

        proc_f_id = r_run1.data["proceso_fiscal"]["id_proceso_nomina"]
        proc_g_id = r_run1.data["proceso_gerencial"]["id_proceso_nomina"]
        assert r_run1.data["proceso_fiscal"]["ambito"] == "FISCAL"
        assert r_run1.data["proceso_gerencial"]["ambito"] == "GERENCIAL"
        assert r_run1.data["total_dispersiones"] == 4

        # Asientos contables segregados por ámbito
        asiento_f = AsientoContable.objects.get(pk=r_run1.data["asiento_fiscal_id"])
        asiento_g = AsientoContable.objects.get(pk=r_run1.data["asiento_gerencial_id"])
        assert asiento_f.ambito == "FISCAL"
        assert asiento_g.ambito == "GERENCIAL"

        # Préstamo amortizado a PAGADO
        pres_1 = PrestamoEmpleado.objects.get(pk=pres_1_id)
        assert pres_1.estado == "PAGADO"
        assert pres_1.saldo_pendiente == Decimal("0.0000")
        assert pres_1.cuotas_pagadas == 1
        assert (
            client_a.post(f"/api/nomina/prestamos-empleados/{pres_1_id}/anular/", {}, format="json").status_code == 400
        )

        # Arqueo de efectivo USD ($100..$1) y marcar-pagado en dispersión
        r_arq = client_a.get(f"/api/nomina/dispersiones-nomina/arqueo-efectivo/?id_proceso_nomina={proc_g_id}")
        assert r_arq.status_code == 200
        assert Decimal(r_arq.data["total_efectivo_usd"]) > 0
        assert len(r_arq.data["empleados"]) == 1
        disp_usd = DispersionPagoNomina.objects.filter(
            id_empresa=empresa_a, id_proceso_nomina_id=proc_g_id, canal_pago="EFECTIVO_USD"
        ).first()
        assert disp_usd is not None and "billetes" in disp_usd.desglose_denominaciones

        assert (
            client_a.post(
                f"/api/nomina/dispersiones-nomina/{disp_usd.pk}/marcar-pagado/", {}, format="json"
            ).status_code
            == 200
        )
        assert (
            client_a.post(
                f"/api/nomina/dispersiones-nomina/{disp_usd.pk}/marcar-pagado/", {}, format="json"
            ).status_code
            == 400
        )

        # Exportadores bancarios TXT
        for bco in ("BANESCO_TXT", "MERCANTIL_TXT", "BDV_TXT"):
            r_bco = client_a.get(f"/api/nomina/procesos-nomina/{proc_f_id}/exportar-banco/?banco={bco}")
            assert r_bco.status_code == 200
            assert "14555666" in r_bco.content.decode("utf-8")
        assert client_a.get(f"/api/nomina/procesos-nomina/{proc_f_id}/exportar-banco/?banco=OTRO").status_code == 400

        # Exportadores parafiscales VE
        for ente in ("FAOV", "IVSS_TIUNA", "INCES", "ISLR_ARC"):
            r_ent = client_a.get(f"/api/nomina/procesos-nomina/{proc_f_id}/exportar-parafiscal/?ente={ente}")
            assert r_ent.status_code == 200
            assert len(r_ent.content.decode("utf-8").strip()) > 0
        assert (
            client_a.get(f"/api/nomina/procesos-nomina/{proc_f_id}/exportar-parafiscal/?ente=FOO").status_code == 400
        )

        # Recibo PDF SEPARADO vs CONSOLIDADO
        nom_emp1_f = Nomina.objects.get(id_proceso_nomina_id=proc_f_id, id_empleado=emp1)
        r_pdf_sep = client_a.get(f"/api/nomina/nominas/{nom_emp1_f.pk}/recibo-pdf/?modo=SEPARADO")
        r_pdf_con = client_a.get(f"/api/nomina/nominas/{nom_emp1_f.pk}/recibo-pdf/?modo=CONSOLIDADO")
        assert r_pdf_sep.status_code == 200 and r_pdf_sep.content.startswith(b"%PDF")
        assert r_pdf_con.status_code == 200 and r_pdf_con.content.startswith(b"%PDF")
        assert client_a.get(f"/api/nomina/nominas/{nom_emp1_f.pk}/recibo-pdf/?modo=X").status_code == 400

        # Simulador de Liquidación LOTTT (Art. 142 garantía vs retroactividad, Art. 92 y préstamos)
        PrestamoEmpleado.objects.create(
            id_empresa=empresa_a,
            id_empleado=emp1,
            ambito_descuento="GERENCIAL",
            moneda=moneda_usd,
            monto_principal=Decimal("50.0000"),
            cuotas_totales=1,
            monto_cuota=Decimal("50.0000"),
            saldo_pendiente=Decimal("50.0000"),
            fecha_otorgamiento=hoy,
        )
        r_liq = client_a.post(
            "/api/nomina/simulador-liquidacion/",
            {
                "id_empresa": str(empresa_a.pk),
                "id_empleado": str(emp1.pk),
                "salario_mensual_integral": "300.0000",
                "fecha_egreso": date(2026, 11, 20).isoformat(),
                "dias_vacaciones_pendientes": 5,
                "despido_injustificado": True,
            },
            format="json",
        )
        assert r_liq.status_code == 200, r_liq.data
        assert r_liq.data["regimen_aplicado"] == "GARANTIA_ART142_AB"
        assert Decimal(r_liq.data["indemnizacion_art92"]) == Decimal(r_liq.data["prestaciones_aplicadas"])
        assert Decimal(r_liq.data["deduccion_prestamos_pendientes"]) == Decimal("50.00")

        emp_retro = Empleado.objects.create(
            empresa=empresa_a, nombre="Mario", apellido="Diaz", cedula="V-30111222", fecha_ingreso=date(2026, 5, 1)
        )
        r_liq_r = client_a.post(
            "/api/nomina/simulador-liquidacion/",
            {
                "id_empresa": str(empresa_a.pk),
                "id_empleado": emp_retro.pk,
                "salario_mensual_integral": "300.0000",
                "fecha_egreso": date(2026, 11, 20).isoformat(),
                "tasa_interes_prestaciones": "0.0000",
            },
            format="json",
        )
        assert r_liq_r.status_code == 200, r_liq_r.data
        assert r_liq_r.data["regimen_aplicado"] == "RETROACTIVIDAD_ART142_C"

        # Cross-tenant empresa B bloqueada (404 / 400)
        assert (
            client_b.get(f"/api/nomina/procesos-nomina/{proc_f_id}/exportar-banco/?banco=BANESCO_TXT").status_code
            == 404
        )
        assert client_b.get(f"/api/nomina/dispersiones-nomina/{disp_usd.pk}/").status_code == 404
        assert ProcesoNomina.objects.filter(id_empresa=empresa_b).count() == 0


# ---------------------------------------------------------------------------
# 3. Validaciones negativas, ramas edge y errores de dominio
# ---------------------------------------------------------------------------


class TestValidacionesYErroresNominaDual:
    def test_validaciones_errores_y_ramas(self, client_a, empresa_a, empresa_b, moneda_usd):
        from apps.nomina.models import PeriodoNomina, PrestamoEmpleado
        from apps.nomina.services_dual import NominaDualError, calcular_arqueo_efectivo_usd
        from apps.rrhh.models import Empleado

        hoy = timezone.localdate()
        emp_a = Empleado.objects.create(
            empresa=empresa_a, nombre="Eva", apellido="Luna", cedula="V-99111222", fecha_ingreso=date(2025, 1, 1)
        )
        emp_b = Empleado.objects.create(
            empresa=empresa_b, nombre="Ot", apellido="Ajeno", cedula="V-99333444", fecha_ingreso=date(2025, 1, 1)
        )
        per_a = PeriodoNomina.objects.create(
            id_empresa=empresa_a,
            nombre_periodo="Mensual Err",
            fecha_inicio=date(hoy.year, hoy.month, 1),
            fecha_fin=date(hoy.year, hoy.month, 28),
            fecha_pago=date(hoy.year, hoy.month, 28),
            tipo_periodo="MENSUAL",
            estado="CERRADO",
        )

        # Arqueo negativo -> NominaDualError
        with pytest.raises(NominaDualError):
            calcular_arqueo_efectivo_usd([{"empleado_id": "1", "monto": Decimal("-5.00")}])

        # Cross-empresa serializer / préstamo saldo > principal
        assert (
            client_a.post(
                "/api/nomina/fichas-salariales-dual/",
                {"id_empresa": str(empresa_a.pk), "id_empleado": str(emp_b.pk), "salario_base_formal_ves": "100"},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/nomina/prestamos-empleados/",
                {
                    "id_empresa": str(empresa_a.pk),
                    "id_empleado": str(emp_a.pk),
                    "monto_principal": "50.00",
                    "monto_cuota": "10.00",
                    "saldo_pendiente": "80.00",
                    "fecha_otorgamiento": hoy.isoformat(),
                },
                format="json",
            ).status_code
            == 400
        )

        # Anular préstamo activo exitosamente
        p_ok = PrestamoEmpleado.objects.create(
            id_empresa=empresa_a,
            id_empleado=emp_a,
            monto_principal=Decimal("40.00"),
            monto_cuota=Decimal("20.00"),
            saldo_pendiente=Decimal("40.00"),
            fecha_otorgamiento=hoy,
        )
        assert (
            client_a.post(f"/api/nomina/prestamos-empleados/{p_ok.pk}/anular/", {}, format="json").status_code == 200
        )

        # Período cerrado -> 400; sin fichas -> 400; egreso anterior a ingreso -> 400; NUL bytes -> 400
        assert (
            client_a.post(
                "/api/nomina/procesos-nomina/procesar-dual/",
                {"id_periodo_nomina": str(per_a.pk), "tasa_bcv": "40.00"},
                format="json",
            ).status_code
            == 400
        )
        per_a.estado = "ABIERTO"
        per_a.save(update_fields=["estado"])
        assert (
            client_a.post(
                "/api/nomina/procesos-nomina/procesar-dual/",
                {"id_periodo_nomina": str(per_a.pk), "tasa_bcv": "40.00"},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/nomina/simulador-liquidacion/",
                {
                    "id_empleado": str(emp_a.pk),
                    "salario_mensual_integral": "200.00",
                    "fecha_egreso": date(2024, 1, 1).isoformat(),
                },
                format="json",
            ).status_code
            == 400
        )
        assert client_a.get("/api/nomina/dispersiones-nomina/?estado=PEN\x00DIENTE").status_code == 400
        assert (
            client_a.post(
                "/api/nomina/dispersiones-nomina/",
                {"id_empresa": str(empresa_a.pk)},
                format="json",
            ).status_code
            == 405
        )
        assert uuid.UUID(str(per_a.pk))

    def test_ramas_tasa_automatica_periodos_contabilidad_y_simulacion_corta(
        self, client_a, empresa_a, empresa_b, moneda_usd, user_a
    ):
        from apps.contabilidad.models import MapeoContable, PeriodoContable, PlanCuentas
        from apps.finanzas.models import TasaCambio, TipoTasaCambio
        from apps.nomina.models import FichaSalarialDual, PeriodoNomina, PrestamoEmpleado
        from apps.nomina.services_dual import (
            NominaDualError,
            calcular_paquete_dual_empleado,
            extraer_novedades_asistencia,
            procesar_nomina_dual,
            simular_liquidacion_lottt,
        )
        from apps.rrhh.models import Empleado
        from tests.factories import MonedaFactory

        hoy = timezone.localdate()
        moneda_ves = MonedaFactory(codigo_iso="VES", nombre="Bolívar", simbolo="Bs")
        empresa_a.id_moneda_base = moneda_usd
        empresa_a.id_moneda_pais = moneda_ves
        empresa_a.contabilidad_activa = True
        empresa_a.save(update_fields=["id_moneda_base", "id_moneda_pais", "contabilidad_activa"])

        # Sin tasa_bcv y sin TasaCambio -> 400; tasa <= 0 -> 400
        emp = Empleado.objects.create(
            empresa=empresa_a,
            nombre="Sofía",
            apellido="Paredes",
            cedula="V-25111222",
            fecha_ingreso=hoy - timedelta(days=95),
        )
        emp_b = Empleado.objects.create(
            empresa=empresa_b, nombre="Ajeno", apellido="Dos", cedula="V-25999000", fecha_ingreso=hoy
        )
        ficha = FichaSalarialDual.objects.create(
            id_empresa=empresa_a,
            id_empleado=emp,
            salario_base_formal_ves=Decimal("5000.0000"),
            paquete_objetivo_mensual=Decimal("300.0000"),
            moneda_paquete=moneda_usd,
        )
        per_sem = PeriodoNomina.objects.create(
            id_empresa=empresa_a,
            nombre_periodo="Semanal 1",
            fecha_inicio=hoy - timedelta(days=6),
            fecha_fin=hoy,
            fecha_pago=hoy,
            tipo_periodo="SEMANAL",
            estado="ABIERTO",
        )
        per_men = PeriodoNomina.objects.create(
            id_empresa=empresa_a,
            nombre_periodo="Mensual 1",
            fecha_inicio=date(hoy.year, hoy.month, 1),
            fecha_fin=hoy,
            fecha_pago=hoy,
            tipo_periodo="MENSUAL",
            estado="ABIERTO",
        )

        # Filtros GET en prestamos-empleados y dispersiones-nomina
        assert (
            client_a.get("/api/nomina/prestamos-empleados/?estado=ACTIVO&ambito_descuento=FISCAL").status_code == 200
        )
        assert (
            client_a.get("/api/nomina/dispersiones-nomina/?canal_pago=EFECTIVO_USD&estado=PENDIENTE").status_code
            == 200
        )

        # Periodo inexistente -> 404; empresa ajena -> 400; sin tasa BCV -> 400; tasa <= 0 -> 400
        assert (
            client_a.post(
                "/api/nomina/procesos-nomina/procesar-dual/",
                {"id_periodo_nomina": str(uuid.uuid4()), "tasa_bcv": "40"},
                format="json",
            ).status_code
            == 404
        )
        assert (
            client_a.post(
                "/api/nomina/procesos-nomina/procesar-dual/",
                {"id_empresa": str(empresa_b.pk), "id_periodo_nomina": str(per_sem.pk), "tasa_bcv": "40"},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/nomina/procesos-nomina/procesar-dual/",
                {"id_periodo_nomina": str(per_sem.pk)},
                format="json",
            ).status_code
            == 400
        )
        assert (
            client_a.post(
                "/api/nomina/procesos-nomina/procesar-dual/",
                {"id_periodo_nomina": str(per_sem.pk), "tasa_bcv": "0"},
                format="json",
            ).status_code
            == 400
        )

        # Configurar TasaCambio oficial BCV para resolución automática sin pasar tasa_bcv explícita
        tipo_bcv = TipoTasaCambio.objects.create(
            id_empresa=empresa_a, codigo="OFICIAL_BCV", nombre="BCV Oficial", es_oficial_fiscal=True
        )
        TasaCambio.objects.create(
            id_empresa=empresa_a,
            id_moneda_origen=moneda_usd,
            id_moneda_destino=moneda_ves,
            tipo_tasa="OFICIAL_BCV",
            id_tipo_tasa=tipo_bcv,
            valor_tasa=Decimal("48.00000000"),
            fecha_tasa=hoy,
        )

        # Contabilidad activa sin MapeoContable NOMINA -> 422 AsientoError
        assert (
            client_a.post(
                "/api/nomina/procesos-nomina/procesar-dual/",
                {"id_periodo_nomina": str(per_sem.pk)},
                format="json",
            ).status_code
            == 422
        )

        # Solo mapeo NOMINA (sin NOMINA_GERENCIAL) -> fallback limpio a NOMINA con ambito="GERENCIAL"
        PeriodoContable.objects.create(id_empresa=empresa_a, anio=hoy.year, mes=hoy.month, estado="ABIERTO")
        cta_d = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="6.1.02.01",
            nombre_cuenta="Gasto Nom",
            tipo_cuenta="GASTO",
            naturaleza="DEUDORA",
            nivel=4,
        )
        cta_h = PlanCuentas.objects.create(
            id_empresa=empresa_a,
            codigo_cuenta="2.1.02.02",
            nombre_cuenta="Nom Pagar",
            tipo_cuenta="PASIVO",
            naturaleza="ACREEDORA",
            nivel=4,
        )
        MapeoContable.objects.create(
            id_empresa=empresa_a, tipo_asiento="NOMINA", cuenta_debe=cta_d, cuenta_haber=cta_h
        )

        # Préstamo parcial (2 cuotas -> queda ACTIVO con 1/2 cuotas y saldo reducido) + ejecución semanal auto-tasa
        pres = PrestamoEmpleado.objects.create(
            id_empresa=empresa_a,
            id_empleado=emp,
            ambito_descuento="FISCAL",
            moneda=moneda_ves,
            monto_principal=Decimal("200.00"),
            cuotas_totales=2,
            monto_cuota=Decimal("100.00"),
            saldo_pendiente=Decimal("200.00"),
            fecha_otorgamiento=hoy,
        )
        res_sem = procesar_nomina_dual(empresa_a, per_sem, incluir_asistencia=False, usuario=user_a)
        assert Decimal(res_sem["tasa_bcv_aplicada"]) == Decimal("48")
        pres.refresh_from_db()
        assert pres.estado == "ACTIVO" and pres.cuotas_pagadas == 1 and pres.saldo_pendiente == Decimal("100.0000")

        # Cálculo puro MENSUAL + errores de servicio (tasa <= 0, dias < 0, salario <= 0)
        res_men = calcular_paquete_dual_empleado(ficha=ficha, empleado=emp, periodo=per_men, tasa_bcv=Decimal("48"))
        assert res_men["dias_trabajados"] == 30
        with pytest.raises(NominaDualError):
            calcular_paquete_dual_empleado(ficha=ficha, empleado=emp, periodo=per_men, tasa_bcv=Decimal("0"))
        with pytest.raises(NominaDualError):
            calcular_paquete_dual_empleado(
                ficha=ficha, empleado=emp, periodo=per_men, tasa_bcv=Decimal("48"), dias_trabajados=-1
            )
        with pytest.raises(NominaDualError):
            simular_liquidacion_lottt(
                empleado=emp, salario_mensual_integral=Decimal("0"), fecha_egreso=hoy, empresa=empresa_a
            )
        assert extraer_novedades_asistencia(empresa_b, per_men) == {}

        # Simulador empleado < 6 meses -> GARANTIA_ART142_AB; cross-tenant id_empleado -> 400
        r_short = client_a.post(
            "/api/nomina/simulador-liquidacion/",
            {"id_empleado": emp.pk, "salario_mensual_integral": "200.00", "fecha_egreso": hoy.isoformat()},
            format="json",
        )
        assert r_short.status_code == 200
        assert r_short.data["regimen_aplicado"] == "GARANTIA_ART142_AB"
        assert (
            client_a.post(
                "/api/nomina/simulador-liquidacion/",
                {"id_empleado": emp_b.pk, "salario_mensual_integral": "200.00", "fecha_egreso": hoy.isoformat()},
                format="json",
            ).status_code
            == 400
        )
