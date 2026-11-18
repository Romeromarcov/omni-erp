"""Pruebas unitarias y guardia estructural de saneamiento de errores HTTP y MCP (R-CODE-8)."""

from __future__ import annotations

import ast
import json
import logging
import re
import uuid
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import RequestFactory
from rest_framework import status

from apps.core.exceptions import (
    CONTROLLED_DOMAIN_ERROR_TYPES,
    DomainError,
    _extract_safe_message,
    domain_error_response,
    is_controlled_domain_error,
    sanitize_mcp_error,
    unexpected_error_response,
)

pytestmark = pytest.mark.unit

BACKEND_DIR = Path(__file__).resolve().parents[2]
APPS_DIR = BACKEND_DIR / "apps"
SECRET_LEAK = "SELECT * FROM secret password=abc123"


# ── Helpers de apps/core/exceptions.py ───────────────────────────────────────


class TestCoreExceptionsHelpers:
    def test_controlled_domain_error_detection(self):
        class CustomDomain(DomainError):
            pass

        assert DomainError in CONTROLLED_DOMAIN_ERROR_TYPES
        assert is_controlled_domain_error(CustomDomain("fallo")) is True
        assert is_controlled_domain_error(ValueError("invalido")) is False
        assert is_controlled_domain_error(ValueError("invalido"), (ValueError,)) is True

    def test_extract_safe_message_normal_y_vacio(self):
        assert (
            _extract_safe_message(
                DomainError("  Saldo insuficiente.  "),
                default_message="Por defecto",
            )
            == "Saldo insuficiente."
        )
        assert (
            _extract_safe_message(DomainError("   \n  "), default_message="Por defecto")
            == "Por defecto"
        )

    @pytest.mark.parametrize(
        "mensaje_inseguro",
        [
            "Traceback (most recent call last):\n  File \"x.py\", line 1",
            "duplicate key value\nDETAIL:  Key (id)=(1) already exists.",
            "CONTEXT:  PL/pgSQL function foo() line 3",
            'Error en File "/app/apps/core/views.py", line 42',
            f"Fallo SQL: {SECRET_LEAK}",
            "INSERT INTO auth_user VALUES ('x')",
            "UPDATE core_empresa SET activo = false",
            "Error conectando con api_key=supersecreta",
        ],
    )
    def test_extract_safe_message_filtra_trazas_tecnicas_y_sql(
        self, mensaje_inseguro
    ):
        from apps.core import exceptions as exc_mod

        with patch.object(
            exc_mod._logger, "warning", wraps=exc_mod._logger.warning
        ) as warn_mock:
            res = _extract_safe_message(
                ValueError(mensaje_inseguro),
                default_message="Operación inválida.",
            )
        assert res == "Operación inválida."
        warn_mock.assert_called_once()
        assert warn_mock.call_args.args[1] == "ValueError"
        logged_args = " ".join(str(a) for a in warn_mock.call_args.args)
        assert "abc123" not in logged_args
        assert "supersecreta" not in logged_args

    def test_domain_error_response_respeta_key_status_y_extra_sin_sobrescribir(self):
        resp = domain_error_response(
            DomainError("Capacidad superada"),
            status_code=status.HTTP_409_CONFLICT,
            key="error",
            extra={"detalle": {"recurso": "mesa"}, "error": "INTENTO_SOBRESCRIBIR"},
        )
        assert resp.status_code == 409
        assert resp.data == {"error": "Capacidad superada", "detalle": {"recurso": "mesa"}}

    def test_domain_error_response_key_detail_y_vacio(self):
        resp = domain_error_response(
            ValueError(""),
            status_code=422,
            key="detail",
            default_message="No se pudo procesar.",
        )
        assert resp.status_code == 422
        assert resp.data == {"detail": "No se pudo procesar."}

    def test_unexpected_error_response_oculta_excepcion_y_loguea(self, caplog):
        test_logger = logging.getLogger("test.unexpected")
        try:
            raise RuntimeError(SECRET_LEAK)
        except RuntimeError as exc:
            with caplog.at_level(logging.ERROR):
                resp = unexpected_error_response(
                    exc,
                    logger=test_logger,
                    context="mi_vista.accion",
                    status_code=500,
                    key="detail",
                    public_message="Error interno controlado.",
                )
        assert resp.status_code == 500
        assert resp.data == {"detail": "Error interno controlado."}
        assert "password=abc123" not in json.dumps(resp.data)
        assert "SELECT *" not in json.dumps(resp.data)
        assert "Error inesperado en mi_vista.accion" in caplog.text

    def test_sanitize_mcp_error_controlado_vs_inesperado(self, caplog):
        test_logger = logging.getLogger("test.mcp")
        assert (
            sanitize_mcp_error(
                ValueError("Cantidad inválida."),
                logger=test_logger,
                tool_name="omni_test",
                controlled_types=(ValueError,),
            )
            == "Cantidad inválida."
        )
        assert (
            sanitize_mcp_error(
                DomainError("Regla de dominio."),
                logger=test_logger,
                tool_name="omni_test",
                controlled_types=(),
            )
            == "Regla de dominio."
        )
        try:
            raise RuntimeError(SECRET_LEAK)
        except RuntimeError as exc:
            with caplog.at_level(logging.ERROR):
                msg = sanitize_mcp_error(
                    exc,
                    logger=test_logger,
                    tool_name="omni_test",
                    controlled_types=(ValueError,),
                )
        assert msg == "No se pudo completar la operación solicitada."
        assert "password=abc123" not in msg
        assert "SELECT *" not in msg
        assert "Error inesperado en tool MCP omni_test" in caplog.text


# ── Guardia estructural AST/regex sobre backend/apps/ ────────────────────────


class TestGuardiaEstructuralSinFugas:
    def test_ningun_response_expone_str_exc_ni_health_fstring(self):
        """Falla si reaparece Response({... str(e|exc|err) ...}) o f'error: {e}' en health checks."""
        violaciones: list[str] = []
        regex_str_exc = re.compile(r"\bstr\s*\(\s*(e|exc|err)\s*\)")
        regex_health_leak = re.compile(r"""["']error:\s*\{[^}]+\}["']""")

        for archivo in sorted(APPS_DIR.rglob("*.py")):
            if "migrations" in archivo.parts or "tests" in archivo.parts:
                continue
            rel = archivo.relative_to(APPS_DIR)
            src = archivo.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(archivo))

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    nombre = (
                        fn.id
                        if isinstance(fn, ast.Name)
                        else (fn.attr if isinstance(fn, ast.Attribute) else None)
                    )
                    if nombre in ("Response", "JsonResponse", "HttpResponse"):
                        seg = ast.get_source_segment(src, node) or ""
                        if regex_str_exc.search(seg):
                            violaciones.append(
                                f"{rel}:{node.lineno} Response con str(e|exc|err): {seg}"
                            )

                if isinstance(node, ast.ExceptHandler) and node.name:
                    var = node.name
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Call):
                            fn = sub.func
                            nombre = (
                                fn.id
                                if isinstance(fn, ast.Name)
                                else (fn.attr if isinstance(fn, ast.Attribute) else None)
                            )
                            if nombre in ("Response", "JsonResponse", "HttpResponse"):
                                for ref in ast.walk(sub):
                                    if isinstance(ref, ast.Name) and ref.id == var:
                                        seg = ast.get_source_segment(src, sub) or ""
                                        # Excepción explícita documentada: change_password_view usa list(e.messages)
                                        if "list(e.messages)" not in seg:
                                            violaciones.append(
                                                f"{rel}:{sub.lineno} Response referencia '{var}': {seg}"
                                            )
                                        break

            if "router.py" in archivo.name or "health" in src:
                for idx, linea in enumerate(src.splitlines(), start=1):
                    if regex_health_leak.search(linea):
                        violaciones.append(f"{rel}:{idx} Health check interpola error: {linea.strip()}")

        assert not violaciones, "Fugas detectadas en backend/apps/:\n" + "\n".join(violaciones)


# ── Fugas cerradas en MCP, CSV import y CxC health check ─────────────────────


class TestCierreFugasConductual:
    def _ctx(self, scope: str, actor_uuid: str | None = None) -> dict:
        uid = actor_uuid or str(uuid.uuid4())
        return {
            "tenant_id": "emp-1",
            "empresa_id": "emp-1",
            "actor_id": f"mcp-token:{uid}",
            "scopes": [scope],
        }

    def test_mcp_crear_pedido_oculta_runtimeerror_y_permite_controlado(self):
        from apps.core import mcp_server
        from apps.ventas.services import VentaError

        ctx = self._ctx("ventas:write")
        productos = [{"id_producto": "p1", "cantidad": "1", "precio_unitario": "10"}]

        with (
            patch.object(mcp_server, "_resolve_token", return_value=ctx),
            patch("django.db.transaction.atomic", return_value=nullcontext()),
            patch(
                "apps.ventas.models.Pedido.objects.create",
                side_effect=RuntimeError(SECRET_LEAK),
            ),
        ):
            res = mcp_server.omni_crear_pedido("tok", "emp-1", "cli-1", productos)
        assert "error" in res
        assert "password=abc123" not in res["error"]
        assert "SELECT *" not in res["error"]

        with (
            patch.object(mcp_server, "_resolve_token", return_value=ctx),
            patch("django.db.transaction.atomic", return_value=nullcontext()),
            patch(
                "apps.ventas.models.Pedido.objects.create",
                side_effect=VentaError("Cliente bloqueado por crédito."),
            ),
        ):
            res_ctrl = mcp_server.omni_crear_pedido("tok", "emp-1", "cli-1", productos)
        assert res_ctrl == {"error": "Cliente bloqueado por crédito."}

    def test_mcp_get_pedidos_oculta_runtimeerror(self):
        from apps.core import mcp_server

        with (
            patch.object(mcp_server, "_resolve_token", return_value=self._ctx("ventas:read")),
            patch(
                "apps.ventas.models.Pedido.objects.filter",
                side_effect=RuntimeError(SECRET_LEAK),
            ),
        ):
            res = mcp_server.omni_get_pedidos("tok", "emp-1")
        assert isinstance(res, list) and len(res) == 1
        assert "password=abc123" not in res[0]["error"]
        assert "SELECT *" not in res[0]["error"]

    def test_mcp_registrar_movimiento_oculta_runtimeerror_y_permite_stock(self):
        from apps.core import mcp_server
        from apps.inventario.services import StockInsuficienteError

        actor_uuid = str(uuid.uuid4())
        ctx = self._ctx("inventario:write", actor_uuid=actor_uuid)
        qs_mock = MagicMock()
        qs_mock.exists.return_value = True

        with (
            patch.object(mcp_server, "_resolve_token", return_value=ctx),
            patch("apps.core.models.Usuarios.objects.filter", return_value=qs_mock),
            patch(
                "apps.inventario.models.MovimientoInventario.objects.create",
                side_effect=RuntimeError(SECRET_LEAK),
            ),
        ):
            res = mcp_server.omni_registrar_movimiento_inventario(
                "tok", "emp-1", "prod-1", "ENTRADA", "5", almacen_destino_id="alm-1"
            )
        assert "password=abc123" not in res["error"]
        assert "SELECT *" not in res["error"]

        with (
            patch.object(mcp_server, "_resolve_token", return_value=ctx),
            patch("apps.core.models.Usuarios.objects.filter", return_value=qs_mock),
            patch(
                "apps.inventario.models.MovimientoInventario.objects.create",
                side_effect=StockInsuficienteError("Stock insuficiente en almacén."),
            ),
        ):
            res_ctrl = mcp_server.omni_registrar_movimiento_inventario(
                "tok", "emp-1", "prod-1", "SALIDA", "5", almacen_origen_id="alm-1"
            )
        assert res_ctrl == {"error": "Stock insuficiente en almacén."}

    def test_mcp_correlativo_fiscal_y_buscar_cliente_ocultan_runtimeerror(self):
        from apps.core import mcp_server

        with (
            patch.object(mcp_server, "_resolve_token", return_value=self._ctx("fiscal:read")),
            patch(
                "apps.fiscal.models.NumeroCorrelativo.objects.get",
                side_effect=RuntimeError(SECRET_LEAK),
            ),
        ):
            res_corr = mcp_server.omni_get_correlativo_fiscal("tok", "emp-1", "FACTURA")
        assert "password=abc123" not in res_corr["error"]
        assert "SELECT *" not in res_corr["error"]

        with (
            patch.object(mcp_server, "_resolve_token", return_value=self._ctx("crm:read")),
            patch(
                "apps.crm.models.Cliente.objects.filter",
                side_effect=RuntimeError(SECRET_LEAK),
            ),
        ):
            res_cli = mcp_server.omni_buscar_cliente("tok", "emp-1", "orinoco")
        assert isinstance(res_cli, list) and len(res_cli) == 1
        assert "password=abc123" not in res_cli[0]["error"]
        assert "SELECT *" not in res_cli[0]["error"]

    def test_ventas_importar_masivo_csv_oculta_runtimeerror_y_controla_errores(self):
        from apps.inventario.models import Producto
        from apps.ventas.views import ListaPrecioViewSet

        class _ListaStub:
            id_empresa = "emp-1"

            def __str__(self):
                return "Lista Base"

        vs = ListaPrecioViewSet()
        vs.get_object = lambda: _ListaStub()

        csv_ok = (
            "codigo_producto,precio,precio_minimo\n"
            "SKU-1,10.00,5.00\n"
        ).encode("utf-8")

        def _req(raw_bytes: bytes):
            archivo = SimpleUploadedFile("precios.csv", raw_bytes, content_type="text/csv")
            return SimpleNamespace(FILES={"archivo": archivo})

        # 1) RuntimeError buscando Producto -> mensaje genérico sin secreto
        with patch.object(
            Producto.objects, "get", side_effect=RuntimeError(SECRET_LEAK)
        ):
            resp = vs.importar_masivo(_req(csv_ok))
        assert resp.status_code == 207
        assert resp.data["errores"] == [
            {"fila": 2, "error": "Error inesperado al buscar el producto."}
        ]
        assert "password=abc123" not in json.dumps(resp.data)

        # 2) Producto.MultipleObjectsReturned -> mensaje controlado
        with patch.object(
            Producto.objects,
            "get",
            side_effect=Producto.MultipleObjectsReturned("2 rows"),
        ):
            resp_dup = vs.importar_masivo(_req(csv_ok))
        assert resp_dup.status_code == 207
        assert "2 rows" not in json.dumps(resp_dup.data)

        # 3) Errores en DetallePrecio: InvalidOperation, IntegrityError, DjangoValidationError y RuntimeError
        csv_varios = (
            "codigo_producto,precio,precio_minimo\n"
            "SKU-1,no-num,5.00\n"
            "SKU-2,10.00,5.00\n"
            "SKU-3,11.00,5.00\n"
            "SKU-4,12.00,6.00\n"
        ).encode("utf-8")
        with (
            patch.object(Producto.objects, "get", return_value=SimpleNamespace(pk="p1")),
            patch(
                "apps.ventas.views.DetallePrecio.objects.update_or_create",
                side_effect=[
                    IntegrityError("DETAIL: Key (id)=(1) already exists."),
                    DjangoValidationError("Fecha inválida"),
                    RuntimeError(SECRET_LEAK),
                ],
            ),
        ):
            resp_mix = vs.importar_masivo(_req(csv_varios))
        assert resp_mix.status_code == 207
        assert len(resp_mix.data["errores"]) == 4
        assert resp_mix.data["errores"][0]["error"] == "Precio o precio mínimo numérico inválido."
        assert resp_mix.data["errores"][1]["error"] == "Datos inválidos o conflicto al registrar el precio."
        assert resp_mix.data["errores"][2]["error"] == "Datos inválidos o conflicto al registrar el precio."
        assert resp_mix.data["errores"][3]["error"] == "Error inesperado al procesar la fila."
        payload_txt = json.dumps(resp_mix.data)
        assert "password=abc123" not in payload_txt
        assert "SELECT *" not in payload_txt
        assert "DETAIL:" not in payload_txt

    def test_cxc_health_check_no_filtra_excepciones(self):
        from apps.cxc.api import router as cxc_router

        req = RequestFactory().get("/api/cxc/health/")
        with (
            patch(
                "apps.cxc.models.GestionCobranza.objects.exists",
                side_effect=RuntimeError(SECRET_LEAK),
            ),
            patch(
                "django.core.cache.cache.set",
                side_effect=RuntimeError(SECRET_LEAK),
            ),
            patch(
                "apps.finanzas.models.TasaCambio.objects.filter",
                side_effect=RuntimeError(SECRET_LEAK),
            ),
            patch.object(
                cxc_router.logger, "warning", wraps=cxc_router.logger.warning
            ) as warn_mock,
        ):
            resp = cxc_router._health_check_view(req)

        assert resp.status_code == 200
        body = json.loads(resp.content.decode("utf-8"))
        assert body == {
            "status": "degraded",
            "checks": {"db": "error", "cache": "error", "tasa_hoy": "error"},
        }
        assert "password=abc123" not in resp.content.decode("utf-8")
        assert "SELECT *" not in resp.content.decode("utf-8")
        assert warn_mock.call_count == 3

    def test_compras_recepcionar_does_not_exist_no_filtra_ingles(self):
        from apps.compras.models import OrdenCompra
        from apps.compras.views import RecepcionMercanciaViewSet

        vs = RecepcionMercanciaViewSet()
        req = SimpleNamespace(
            data={
                "orden_compra_id": str(uuid.uuid4()),
                "almacen_id": str(uuid.uuid4()),
                "items": [{"producto_id": str(uuid.uuid4()), "cantidad": 1}],
            },
            user=SimpleNamespace(),
        )
        with (
            patch("apps.compras.views._empresas", return_value=[]),
            patch.object(
                OrdenCompra.objects,
                "get",
                side_effect=OrdenCompra.DoesNotExist("OrdenCompra matching query does not exist."),
            ),
        ):
            resp = vs.recepcionar(req)
        assert resp.status_code == 404
        assert resp.data == {"detail": "Orden de compra o almacén no encontrado."}

    def test_vistas_saneadas_preservan_contrato_y_filtran_trazas(self):
        from apps.compras.models import RecepcionMercancia
        from apps.compras.services import CompraError
        from apps.compras.views import FacturaCompraViewSet
        from apps.contabilidad.services import AsientoError
        from apps.cxc_lubrikca.api.operacion_viewsets import PedidoLubrikcaViewSet
        from apps.cxc_lubrikca.services.sync import SyncError
        from apps.gestion_aprobaciones.services import AprobacionError
        from apps.gestion_aprobaciones.views import SolicitudAprobacionViewSet
        from apps.gestion_documental.views import DocumentoViewSet
        from apps.nomina.views import ProcesoNominaViewSet
        from apps.tesoreria.preconciliacion import PreconciliacionError
        from apps.tesoreria.views import (
            OperacionCambioDivisaViewSet,
            PropuestaConciliacionBancariaViewSet,
        )

        # 1) compras.facturar -> 400 key="detail"
        vs_fac = FacturaCompraViewSet()
        req_fac = SimpleNamespace(
            data={"recepcion_id": str(uuid.uuid4()), "numero_factura": "F-1"},
            user=SimpleNamespace(),
        )
        with (
            patch("apps.compras.views._empresas", return_value=[]),
            patch.object(RecepcionMercancia.objects, "get", return_value=SimpleNamespace()),
            patch(
                "apps.compras.services.registrar_factura_compra",
                side_effect=CompraError("Recepción ya facturada."),
            ),
        ):
            r_fac = vs_fac.facturar(req_fac)
        assert r_fac.status_code == 400
        assert r_fac.data == {"detail": "Recepción ya facturada."}

        # 2) cxc_lubrikca.sincronizar -> 400 key="detail"
        vs_lub = PedidoLubrikcaViewSet()
        vs_lub._empresa_usuario = lambda: SimpleNamespace(pk="emp-1")
        with patch(
            "apps.cxc_lubrikca.api.operacion_viewsets.sincronizar_empresa",
            side_effect=SyncError("Odoo no disponible"),
        ):
            r_lub = vs_lub.sincronizar(SimpleNamespace(data={}))
        assert r_lub.status_code == 400
        assert r_lub.data == {"detail": "Odoo no disponible"}

        # 3) gestion_aprobaciones.decidir -> 400 key="error"
        vs_apr = SolicitudAprobacionViewSet()
        vs_apr.get_object = lambda: SimpleNamespace()
        with patch(
            "apps.gestion_aprobaciones.services.registrar_decision",
            side_effect=AprobacionError("Solicitud ya decidida."),
        ):
            r_apr = vs_apr.decidir(
                SimpleNamespace(data={"aprobado": True}, user=SimpleNamespace())
            )
        assert r_apr.status_code == 400
        assert r_apr.data == {"error": "Solicitud ya decidida."}

        # 4) gestion_documental.subir -> 400 key="error"
        vs_doc = DocumentoViewSet()
        archivo = SimpleUploadedFile("malo.exe", b"MZ", content_type="application/octet-stream")
        emp_qs = MagicMock()
        emp_qs.values_list.return_value = ["emp-1"]
        storage_mock = MagicMock()
        storage_mock.upload_file.side_effect = ValueError("Extensión no permitida.")
        with (
            patch("apps.gestion_documental.views._empresas", return_value=emp_qs),
            patch(
                "apps.gestion_documental.views.StorageService",
                return_value=storage_mock,
            ),
        ):
            r_doc = vs_doc.subir(
                SimpleNamespace(
                    FILES={"archivo": archivo},
                    data={"empresa_id": "emp-1"},
                    user=SimpleNamespace(),
                )
            )
        assert r_doc.status_code == 400
        assert r_doc.data == {"error": "Extensión no permitida."}

        # 5) nomina.procesar AsientoError -> 422 key="error"
        vs_nom = ProcesoNominaViewSet()
        vs_nom.get_object = lambda: SimpleNamespace()
        with patch(
            "apps.nomina.services.procesar_proceso_nomina",
            side_effect=AsientoError("Falta mapeo NOMINA."),
        ):
            r_nom = vs_nom.procesar(SimpleNamespace(data={}, user=SimpleNamespace()))
        assert r_nom.status_code == 422
        assert r_nom.data == {"error": "Falta mapeo NOMINA."}

        # 6) tesoreria.OperacionCambioDivisaViewSet.create AsientoError -> 422 key="error"
        vs_cam = OperacionCambioDivisaViewSet()
        with patch(
            "rest_framework.mixins.CreateModelMixin.create",
            side_effect=AsientoError("Falta mapeo CAMBIO_DIVISA."),
        ):
            r_cam = vs_cam.create(SimpleNamespace())
        assert r_cam.status_code == 422
        assert r_cam.data == {"error": "Falta mapeo CAMBIO_DIVISA."}

        # 7) tesoreria.PropuestaConciliacionBancariaViewSet.decidir PreconciliacionError -> 404 key="error"
        vs_pre = PropuestaConciliacionBancariaViewSet()
        vs_pre.get_object = lambda: SimpleNamespace(pk=uuid.uuid4(), id_empresa=SimpleNamespace())
        with patch(
            "apps.tesoreria.preconciliacion.decidir_propuesta_conciliacion",
            side_effect=PreconciliacionError("Propuesta no encontrada."),
        ):
            r_pre = vs_pre.decidir(
                SimpleNamespace(data={"accion": "RECHAZAR"}, user=SimpleNamespace())
            )
        assert r_pre.status_code == 404
        assert r_pre.data == {"error": "Propuesta no encontrada."}
