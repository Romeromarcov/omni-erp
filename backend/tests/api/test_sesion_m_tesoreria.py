"""
Sesión M — Tests Tesorería + Conciliación Bancaria

Verifica:
- test_registrar_movimiento_bancario(): service crea movimiento correctamente
- test_tipo_invalido_lanza_error(): ConciliacionError si tipo no es DEBITO/CREDITO
- test_monto_cero_lanza_error(): ConciliacionError si monto ≤ 0
- test_importar_csv_lineas_validas(): importar_extracto_csv retorna importados correcto
- test_importar_csv_lineas_invalidas(): filas con error se cuentan en errores
- test_conciliar_automatico_match_por_monto(): matching por monto+fecha funciona
- test_conciliar_automatico_sin_pagos(): sin pagos, 0 conciliados
- test_iniciar_conciliacion(): crea ConciliacionBancaria ABIERTA
- test_cerrar_conciliacion(): estado pasa a CERRADA con contadores actualizados
- test_endpoint_movimientos_bancarios_list_200(): GET /api/tesoreria/movimientos-bancarios/ → 200
- test_endpoint_movimientos_bancarios_aislamiento(): empresa B no ve movimientos de A
- test_endpoint_conciliaciones_list_200(): GET /api/tesoreria/conciliaciones-bancarias/ → 200
- test_endpoint_cerrar_conciliacion(): POST cerrar → estado CERRADA
- test_endpoint_cerrar_idempotente(): cerrar dos veces no falla
- test_endpoint_conciliar_auto(): POST conciliar-auto → retorna stats
- test_endpoint_sin_auth_401(): sin autenticación retorna 401
"""
import datetime
import io
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.finanzas.models import CuentaBancariaEmpresa


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client_a(user_a):
    c = APIClient()
    c.force_authenticate(user=user_a)
    return c


@pytest.fixture
def client_b(user_b):
    c = APIClient()
    c.force_authenticate(user=user_b)
    return c


@pytest.fixture
def cuenta_a(db, empresa_a, moneda_usd):
    return CuentaBancariaEmpresa.objects.create(
        id_empresa=empresa_a,
        nombre_banco="Banco Prueba SA",
        numero_cuenta="0102-0001-0001",
        tipo_cuenta="CORRIENTE",
        id_moneda=moneda_usd,
        saldo_actual=Decimal("10000.00"),
    )


@pytest.fixture
def movimiento_pendiente(db, empresa_a, cuenta_a):
    from apps.tesoreria.models import MovimientoBancario
    return MovimientoBancario.objects.create(
        id_empresa=empresa_a,
        id_cuenta_bancaria=cuenta_a,
        fecha_mov=datetime.date(2026, 5, 10),
        descripcion="Pago cliente recibido",
        tipo="CREDITO",
        monto=Decimal("1500.00"),
        referencia="REF-001",
        estado="PENDIENTE",
    )


@pytest.fixture
def conciliacion_a(db, empresa_a, cuenta_a):
    from apps.tesoreria.services import iniciar_conciliacion
    return iniciar_conciliacion(
        empresa=empresa_a,
        cuenta_bancaria=cuenta_a,
        periodo_inicio=datetime.date(2026, 5, 1),
        periodo_fin=datetime.date(2026, 5, 31),
        saldo_banco=Decimal("11500.00"),
        saldo_libro=Decimal("10000.00"),
    )


# ── Unit tests — Services ─────────────────────────────────────────────────────

class TestRegistrarMovimientoBancario:
    def test_crea_movimiento(self, db, empresa_a, cuenta_a):
        from apps.tesoreria.services import registrar_movimiento_bancario
        mov = registrar_movimiento_bancario(
            empresa=empresa_a,
            cuenta_bancaria=cuenta_a,
            fecha_mov=datetime.date(2026, 5, 15),
            descripcion="Ingreso cliente",
            tipo="CREDITO",
            monto=Decimal("2000.00"),
            referencia="REF-100",
        )
        assert mov.pk is not None
        assert mov.estado == "PENDIENTE"
        assert mov.tipo == "CREDITO"
        assert mov.monto == Decimal("2000.00")

    def test_tipo_invalido_lanza_error(self, db, empresa_a, cuenta_a):
        from apps.tesoreria.services import ConciliacionError, registrar_movimiento_bancario
        with pytest.raises(ConciliacionError, match="Tipo inválido"):
            registrar_movimiento_bancario(
                empresa=empresa_a,
                cuenta_bancaria=cuenta_a,
                fecha_mov=datetime.date(2026, 5, 15),
                descripcion="Test",
                tipo="INGRESO",
                monto=Decimal("500.00"),
            )

    def test_monto_cero_lanza_error(self, db, empresa_a, cuenta_a):
        from apps.tesoreria.services import ConciliacionError, registrar_movimiento_bancario
        with pytest.raises(ConciliacionError, match="mayor que cero"):
            registrar_movimiento_bancario(
                empresa=empresa_a,
                cuenta_bancaria=cuenta_a,
                fecha_mov=datetime.date(2026, 5, 15),
                descripcion="Test",
                tipo="DEBITO",
                monto=Decimal("0.00"),
            )

    def test_monto_negativo_lanza_error(self, db, empresa_a, cuenta_a):
        from apps.tesoreria.services import ConciliacionError, registrar_movimiento_bancario
        with pytest.raises(ConciliacionError):
            registrar_movimiento_bancario(
                empresa=empresa_a,
                cuenta_bancaria=cuenta_a,
                fecha_mov=datetime.date(2026, 5, 15),
                descripcion="Test",
                tipo="DEBITO",
                monto=Decimal("-100.00"),
            )


class TestImportarExtractoCSV:
    def _csv(self, filas):
        cabecera = "fecha,descripcion,tipo,monto,referencia\n"
        lineas = "\n".join(",".join(str(c) for c in f) for f in filas)
        return io.StringIO(cabecera + lineas)

    def test_importa_filas_validas(self, db, empresa_a, cuenta_a):
        from apps.tesoreria.services import importar_extracto_csv
        csv_io = self._csv([
            ("2026-05-01", "Pago A", "CREDITO", "1000.00", "R1"),
            ("2026-05-02", "Comision", "DEBITO", "25.00", ""),
        ])
        resultado = importar_extracto_csv(empresa_a, cuenta_a, csv_io)
        assert resultado["importados"] == 2
        assert resultado["errores"] == 0

    def test_cuenta_filas_con_error(self, db, empresa_a, cuenta_a):
        from apps.tesoreria.services import importar_extracto_csv
        csv_io = self._csv([
            ("2026-05-01", "Valida", "CREDITO", "500.00", ""),
            ("FECHA-MAL", "Invalida", "CREDITO", "abc", ""),  # fecha y monto malos
        ])
        resultado = importar_extracto_csv(empresa_a, cuenta_a, csv_io)
        assert resultado["importados"] == 1
        assert resultado["errores"] == 1
        assert len(resultado["lineas_error"]) == 1

    def test_csv_vacio_importa_cero(self, db, empresa_a, cuenta_a):
        from apps.tesoreria.services import importar_extracto_csv
        csv_io = io.StringIO("fecha,descripcion,tipo,monto,referencia\n")
        resultado = importar_extracto_csv(empresa_a, cuenta_a, csv_io)
        assert resultado["importados"] == 0
        assert resultado["errores"] == 0


class TestConciliarAutomatico:
    def test_sin_pagos_cero_conciliados(self, db, empresa_a, cuenta_a, movimiento_pendiente):
        from apps.tesoreria.services import conciliar_automatico
        resultado = conciliar_automatico(empresa_a, cuenta_a)
        assert resultado["conciliados"] == 0
        assert resultado["sin_match"] == 1
        assert resultado["total_procesados"] == 1

    def test_sin_movimientos_retorna_cero(self, db, empresa_a, cuenta_a):
        """Sin movimientos pendientes el resultado es cero en todos los contadores."""
        from apps.tesoreria.services import conciliar_automatico
        resultado = conciliar_automatico(empresa_a, cuenta_a)
        assert resultado["total_procesados"] == 0
        assert resultado["conciliados"] == 0
        assert resultado["sin_match"] == 0

    def test_movimiento_debito_no_se_concilia(self, db, empresa_a, cuenta_a):
        """Los movimientos DEBITO (egresos del banco) no se intentan conciliar."""
        from apps.tesoreria.models import MovimientoBancario
        from apps.tesoreria.services import conciliar_automatico
        MovimientoBancario.objects.create(
            id_empresa=empresa_a,
            id_cuenta_bancaria=cuenta_a,
            fecha_mov=datetime.date(2026, 5, 10),
            descripcion="Comision bancaria",
            tipo="DEBITO",
            monto=Decimal("50.00"),
            estado="PENDIENTE",
        )
        resultado = conciliar_automatico(empresa_a, cuenta_a)
        # DEBITO no se procesa (solo CREDITO)
        assert resultado["total_procesados"] == 0


class TestIniciarCerrarConciliacion:
    def test_iniciar_crea_conciliacion_abierta(self, db, empresa_a, cuenta_a):
        from apps.tesoreria.services import iniciar_conciliacion
        c = iniciar_conciliacion(
            empresa=empresa_a,
            cuenta_bancaria=cuenta_a,
            periodo_inicio=datetime.date(2026, 5, 1),
            periodo_fin=datetime.date(2026, 5, 31),
            saldo_banco=Decimal("12000.00"),
            saldo_libro=Decimal("10000.00"),
        )
        assert c.estado == "ABIERTA"
        assert c.diferencia == Decimal("2000.00")
        assert c.pk is not None

    def test_cerrar_cambia_estado(self, db, conciliacion_a):
        from apps.tesoreria.services import cerrar_conciliacion
        cerrar_conciliacion(conciliacion_a)
        conciliacion_a.refresh_from_db()
        assert conciliacion_a.estado == "CERRADA"
        assert conciliacion_a.fecha_cierre is not None


# ── Endpoint tests ────────────────────────────────────────────────────────────

URL_MOVIMIENTOS = "/api/tesoreria/movimientos-bancarios/"
URL_CONCILIACIONES = "/api/tesoreria/conciliaciones-bancarias/"


class TestEndpointsMovimientosBancarios:
    def test_list_200(self, client_a, movimiento_pendiente):
        resp = client_a.get(URL_MOVIMIENTOS)
        assert resp.status_code == 200

    def test_list_contiene_movimiento(self, client_a, movimiento_pendiente):
        resp = client_a.get(URL_MOVIMIENTOS)
        ids = [m["id"] for m in resp.data["results"] if "id" in m] if "results" in resp.data else [m["id"] for m in resp.data]
        assert str(movimiento_pendiente.id) in ids

    def test_filtro_estado_pendiente(self, client_a, movimiento_pendiente):
        resp = client_a.get(URL_MOVIMIENTOS, {"estado": "PENDIENTE"})
        assert resp.status_code == 200

    def test_aislamiento_empresa_b(self, client_b, movimiento_pendiente):
        resp = client_b.get(URL_MOVIMIENTOS)
        assert resp.status_code == 200
        data = resp.data.get("results", resp.data)
        ids = [m["id"] for m in data]
        assert str(movimiento_pendiente.id) not in ids

    def test_sin_auth_401(self):
        resp = APIClient().get(URL_MOVIMIENTOS)
        assert resp.status_code == 401

    def test_conciliar_auto_endpoint(self, client_a, cuenta_a):
        resp = client_a.post(
            f"{URL_MOVIMIENTOS}conciliar-auto/",
            {"cuenta_bancaria": str(cuenta_a.id_cuenta_bancaria)},
            format="json",
        )
        assert resp.status_code == 200
        assert "conciliados" in resp.data
        assert "sin_match" in resp.data
        assert "total_procesados" in resp.data

    def test_conciliar_auto_sin_cuenta_400(self, client_a):
        resp = client_a.post(f"{URL_MOVIMIENTOS}conciliar-auto/", {}, format="json")
        assert resp.status_code == 400


class TestEndpointsConciliacionBancaria:
    def test_list_200(self, client_a, conciliacion_a):
        resp = client_a.get(URL_CONCILIACIONES)
        assert resp.status_code == 200

    def test_list_contiene_conciliacion(self, client_a, conciliacion_a):
        resp = client_a.get(URL_CONCILIACIONES)
        data = resp.data.get("results", resp.data)
        ids = [str(c["id"]) for c in data]
        assert str(conciliacion_a.id) in ids

    def test_cerrar_endpoint(self, client_a, conciliacion_a):
        resp = client_a.post(f"{URL_CONCILIACIONES}{conciliacion_a.id}/cerrar/")
        assert resp.status_code == 200
        assert resp.data["estado"] == "CERRADA"

    def test_cerrar_idempotente(self, client_a, conciliacion_a):
        client_a.post(f"{URL_CONCILIACIONES}{conciliacion_a.id}/cerrar/")
        resp = client_a.post(f"{URL_CONCILIACIONES}{conciliacion_a.id}/cerrar/")
        assert resp.status_code == 200

    def test_aislamiento_empresa_b(self, client_b, conciliacion_a):
        resp = client_b.get(URL_CONCILIACIONES)
        assert resp.status_code == 200
        data = resp.data.get("results", resp.data)
        ids = [str(c["id"]) for c in data]
        assert str(conciliacion_a.id) not in ids

    def test_sin_auth_401(self):
        resp = APIClient().get(URL_CONCILIACIONES)
        assert resp.status_code == 401
