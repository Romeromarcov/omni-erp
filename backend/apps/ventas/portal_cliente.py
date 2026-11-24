"""Portal / App Independiente para Clientes B2B/B2C Self-Service (Plan 09 Fase 7.3).

Incluye:
- Autenticación OTP por WhatsApp/Email con código hasheado (PBKDF2), tope de 5 intentos y token de sesión SHA-256.
- Autenticación DRF dedicada ``PortalClienteTokenAuthentication`` + ``rls_tenant_context`` por empresa.
- Historial de compras (facturas fiscales y notas de venta), estado de cuenta trimonetario (USD/VES/USDT),
  reporte de pagos con OCR/IA vía ``llm_gateway``, realización de pedidos y tracking en vivo de despachos.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import uuid
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from rest_framework import authentication, permissions, serializers, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core.exceptions import domain_error_response
from apps.core.idempotency import idempotent
from apps.core.llm_gateway import LLMGateway, LLMUnavailable
from apps.core.rls import apply_context, rls_bypass
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import validar_uuid_param
from apps.crm.models import Cliente
from apps.cuentas_por_cobrar.models import CuentaPorCobrar
from apps.despacho.models import Despacho, ParadaEntrega
from apps.finanzas.models import MetodoPago, Moneda
from apps.inventario.models import Producto

from .models import DetallePedido, FacturaFiscal, NotaVenta, PagoPortalCliente, Pedido, TokenPortalCliente
from .portal_vendedor import _equivalencias_seguras
from .services import obtener_precio
from .services_credito import _saldo_neto_cxc, evaluar_credito_cliente

logger = logging.getLogger(__name__)

_Q2 = Decimal("0.01")
_Q4 = Decimal("0.0001")
_CERO = Decimal("0")
_OTP_TTL_MINUTOS = 15
_SESION_TTL_HORAS = 24
_MAX_INTENTOS_OTP = 5


class PortalClienteError(Exception):
    """Error de dominio en el Portal de Clientes Self-Service."""


def _sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _enmascarar_destino(destino: str) -> str:
    limpio = (destino or "").strip()
    if len(limpio) <= 4:
        return "****"
    return f"{limpio[:2]}***{limpio[-2:]}"


def extraer_comprobante_pago_ocr(
    texto_comprobante: str, *, empresa=None, llm_gateway: LLMGateway | None = None
) -> dict[str, Any]:
    """Extrae monto, moneda, referencia y fecha de un comprobante vía LLMGateway con fallback determinista."""
    texto = (texto_comprobante or "").strip()
    if not texto:
        return {"fuente": "VACIO", "monto": None, "moneda": None, "referencia": None}

    gw = llm_gateway or LLMGateway()
    if gw.disponible():
        try:
            prompt = (
                "Extrae exclusivamente en JSON válido con claves {monto, moneda, referencia, fecha} "
                f"los datos de este comprobante bancario/pago:\n{texto[:1500]}"
            )
            res = gw.generate(prompt=prompt, max_tokens=200, uso="PORTAL_OCR_COMPROBANTE", empresa=empresa)
            parsed = json.loads(res.text.strip())
            if isinstance(parsed, dict):
                return {
                    "fuente": "LLM_GATEWAY",
                    "monto": parsed.get("monto"),
                    "moneda": parsed.get("moneda"),
                    "referencia": parsed.get("referencia"),
                    "fecha": parsed.get("fecha"),
                }
        except (LLMUnavailable, ValueError, TypeError, json.JSONDecodeError):
            logger.info("portal_cliente ocr fallback determinista | motivo=llm_no_disponible_o_invalido")

    # Fallback determinista por expresiones regulares (sin llamada externa).
    m_monto = re.search(r"(?:USD|VES|USDT|BS|\$|€)?\s*([0-9]+(?:[.,][0-9]{1,4})?)", texto, re.IGNORECASE)
    m_moneda = re.search(r"\b(USDT|USD|VES|BS)\b", texto, re.IGNORECASE)
    m_ref = re.search(r"(?:ref(?:erencia)?|nro|operacion)[:#\s\-]*([A-Z0-9\-]{4,24})", texto, re.IGNORECASE)
    if m_ref is None:
        m_ref = re.search(r"\b([0-9]{6,20})\b", texto)

    return {
        "fuente": "REGEX_DETERMINISTA",
        "monto": m_monto.group(1).replace(",", ".") if m_monto else None,
        "moneda": m_moneda.group(1).upper() if m_moneda else None,
        "referencia": m_ref.group(1) if m_ref else None,
    }


class PortalClientePrincipal:
    """Principal ligero autenticado vía ``TokenPortalCliente``."""

    def __init__(self, cliente: Cliente, empresa, token_obj: TokenPortalCliente) -> None:
        self.cliente = cliente
        self.empresa = empresa
        self.token_obj = token_obj
        self.pk = cliente.pk
        self.id = cliente.pk
        self.is_authenticated = True
        self.is_active = True
        self.username = f"portal:{cliente.rif}"


class PortalClienteTokenAuthentication(authentication.BaseAuthentication):
    """Autenticación por token opaco SHA-256 emitido tras verificar OTP del cliente."""

    def authenticate(self, request):
        raw = request.headers.get("X-Portal-Cliente-Token", "").strip()
        if not raw:
            auth_hdr = request.headers.get("Authorization", "").strip()
            if auth_hdr.startswith("PortalCliente "):
                raw = auth_hdr[len("PortalCliente ") :].strip()
        if not raw:
            return None

        token_hash = _sha256_hex(raw)
        ahora = timezone.now()
        with rls_bypass():
            tok = (
                TokenPortalCliente.objects.select_related("id_empresa", "id_cliente")
                .filter(
                    sesion_token_hash=token_hash,
                    usado=True,
                    revocado=False,
                    activo=True,
                    expira_en__gt=ahora,
                    id_cliente__activo=True,
                    id_empresa__activo=True,
                )
                .first()
            )
            if tok is None:
                raise AuthenticationFailed("Token del Portal de Clientes inválido o expirado.")

        # Acotar conexión PostgreSQL al tenant del cliente autenticado (fail-closed).
        apply_context([tok.id_empresa_id], bypass=False)
        principal = PortalClientePrincipal(tok.id_cliente, tok.id_empresa, tok)
        return (principal, tok)


class IsPortalClienteAuthenticated(permissions.BasePermission):
    def has_permission(self, request, view):
        return isinstance(getattr(request, "user", None), PortalClientePrincipal)


class SolicitarOTPPortalInputSerializer(serializers.Serializer):
    rif = serializers.CharField(max_length=20)
    id_empresa = serializers.UUIDField(required=False, allow_null=True)
    canal = serializers.ChoiceField(choices=["WHATSAPP", "EMAIL"], required=False, default="WHATSAPP")
    destino = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")


class VerificarOTPPortalInputSerializer(serializers.Serializer):
    id_token = serializers.UUIDField(required=False, allow_null=True)
    rif = serializers.CharField(max_length=20)
    codigo = serializers.CharField(min_length=6, max_length=8)
    id_empresa = serializers.UUIDField(required=False, allow_null=True)


class PagoPortalClienteInputSerializer(serializers.Serializer):
    monto = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0.0001"))
    id_moneda = serializers.UUIDField()
    id_metodo_pago = serializers.UUIDField()
    tasa = serializers.DecimalField(
        max_digits=18, decimal_places=4, required=False, default=Decimal("1.0000"), min_value=Decimal("0.0001")
    )
    referencia = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    comprobante_url = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    texto_comprobante_ocr = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    observaciones = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class LineaPedidoClienteInputSerializer(serializers.Serializer):
    id_producto = serializers.UUIDField()
    cantidad = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0.0001"))


class PedidoPortalClienteInputSerializer(serializers.Serializer):
    observaciones = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    lineas = LineaPedidoClienteInputSerializer(many=True, allow_empty=False)


class SolicitarOTPPortalView(APIView):
    """Solicita un OTP efímero de acceso por WhatsApp o Email sin filtrar el código en la respuesta."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    @swagger_auto_schema(request_body=SolicitarOTPPortalInputSerializer)
    def post(self, request):
        ser = SolicitarOTPPortalInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        rif_norm = vd["rif"].strip().upper()

        with rls_bypass():
            qs = Cliente.objects.select_related("id_empresa").filter(
                rif__iexact=rif_norm, activo=True, id_empresa__activo=True
            )
            if vd.get("id_empresa"):
                qs = qs.filter(id_empresa_id=validar_uuid_param(str(vd["id_empresa"]), "id_empresa"))
            cliente = qs.first()
            if cliente is None:
                return Response(
                    {"detail": "Si el RIF está registrado, se enviará el código de verificación."},
                    status=status.HTTP_200_OK,
                )

            TokenPortalCliente.objects.filter(
                id_empresa=cliente.id_empresa, id_cliente=cliente, usado=False, revocado=False
            ).update(revocado=True)

            codigo = f"{secrets.randbelow(900000) + 100000:06d}"
            destino = (vd["destino"] or cliente.telefono or cliente.email or "").strip()
            tok = TokenPortalCliente.objects.create(
                id_empresa=cliente.id_empresa,
                id_cliente=cliente,
                canal=vd["canal"],
                destino=_enmascarar_destino(destino),
                codigo_hash=make_password(codigo),
                expira_en=timezone.now() + timedelta(minutes=_OTP_TTL_MINUTOS),
            )
            logger.info(
                "portal_cliente otp generado | empresa=%s | cliente=%s | canal=%s | destino=%s",
                cliente.id_empresa_id,
                cliente.pk,
                vd["canal"],
                tok.destino,
            )

        return Response(
            {
                "id_token": str(tok.pk),
                "canal": tok.canal,
                "destino_enmascarado": tok.destino,
                "expira_en": tok.expira_en.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class VerificarOTPPortalView(APIView):
    """Verifica OTP (máx 5 intentos) y entrega token de sesión opaco para el Portal de Clientes."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    @swagger_auto_schema(request_body=VerificarOTPPortalInputSerializer)
    def post(self, request):
        ser = VerificarOTPPortalInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        rif_norm = vd["rif"].strip().upper()
        ahora = timezone.now()

        with rls_bypass():
            with transaction.atomic():
                qs = (
                    TokenPortalCliente.objects.select_for_update(of=("self",))
                    .select_related("id_empresa", "id_cliente")
                    .filter(
                        id_cliente__rif__iexact=rif_norm,
                        usado=False,
                        revocado=False,
                        activo=True,
                        expira_en__gt=ahora,
                    )
                )
                if vd.get("id_token"):
                    qs = qs.filter(pk=vd["id_token"])
                if vd.get("id_empresa"):
                    qs = qs.filter(id_empresa_id=vd["id_empresa"])
                tok = qs.order_by("-fecha_creacion").first()
                if tok is None:
                    return domain_error_response(
                        PortalClienteError("Código OTP inválido o expirado."),
                        status_code=status.HTTP_400_BAD_REQUEST,
                        key="detail",
                    )

                if not check_password(vd["codigo"].strip(), tok.codigo_hash):
                    tok.intentos += 1
                    update_fields = ["intentos", "fecha_actualizacion"]
                    if tok.intentos >= _MAX_INTENTOS_OTP:
                        tok.revocado = True
                        update_fields.append("revocado")
                    tok.save(update_fields=update_fields)
                    return domain_error_response(
                        PortalClienteError("Código OTP incorrecto."),
                        status_code=status.HTTP_400_BAD_REQUEST,
                        key="detail",
                    )

                raw_session = secrets.token_urlsafe(32)
                tok.sesion_token_hash = _sha256_hex(raw_session)
                tok.usado = True
                tok.expira_en = ahora + timedelta(hours=_SESION_TTL_HORAS)
                tok.save(update_fields=["sesion_token_hash", "usado", "expira_en", "fecha_actualizacion"])

                cliente = tok.id_cliente
                empresa = tok.id_empresa

        return Response(
            {
                "session_token": raw_session,
                "expira_en": tok.expira_en.isoformat(),
                "cliente": {
                    "id_cliente": str(cliente.pk),
                    "razon_social": cliente.razon_social,
                    "rif": cliente.rif,
                    "empresa_id": str(empresa.pk),
                    "empresa_nombre": getattr(empresa, "nombre_comercial", None)
                    or getattr(empresa, "razon_social", str(empresa)),
                },
            },
            status=status.HTTP_200_OK,
        )


class PortalClienteResumenView(APIView):
    """Resumen del cliente B2B/B2C: historial de facturas/notas, estado de cuenta trimonetario y PDFs."""

    authentication_classes = [PortalClienteTokenAuthentication]
    permission_classes = [IsPortalClienteAuthenticated]

    def get(self, request):
        principal: PortalClientePrincipal = request.user
        empresa = principal.empresa
        cliente = principal.cliente

        cred = evaluar_credito_cliente(cliente, empresa)
        saldo_total = Decimal(str(cred["saldo_pendiente"])).quantize(_Q2, rounding=ROUND_HALF_UP)
        cxc_pendientes = [
            c
            for c in CuentaPorCobrar.objects.filter(
                empresa=empresa, cliente=cliente, estado__in=("pendiente", "vencida", "parcial")
            ).order_by("fecha_vencimiento")
            if _saldo_neto_cxc(c) > _CERO
        ]
        moneda_base = getattr(empresa, "id_moneda_base", None)
        eq_saldo = _equivalencias_seguras(saldo_total, moneda_base, empresa)

        facturas = [
            {
                "id_factura": str(f.pk),
                "numero_factura": f.numero_factura,
                "numero_control": f.numero_control,
                "fecha_emision": f.fecha_emision.isoformat(),
                "monto_total": str(f.monto_total),
                "moneda": f.id_moneda.codigo_iso,
                "estado": f.estado,
                "pdf_url": f"/api/ventas/facturas-fiscales/{f.pk}/pdf/",
            }
            for f in FacturaFiscal.objects.filter(id_empresa=empresa, id_cliente=cliente, activo=True)
            .select_related("id_moneda")
            .order_by("-fecha_emision")[:25]
        ]

        notas = [
            {
                "id_nota_venta": str(n.pk),
                "numero_nota": n.numero_nota,
                "fecha_nota": n.fecha_nota.isoformat(),
                "estado": n.estado,
                "ambito": n.ambito,
                "pdf_url": f"/api/ventas/notas-venta/{n.pk}/pdf/",
            }
            for n in NotaVenta.objects.filter(id_empresa=empresa, id_cliente=cliente, activo=True).order_by(
                "-fecha_nota"
            )[:25]
        ]

        pagos_reportados = [
            {
                "id_pago_portal": str(p.pk),
                "monto": str(p.monto),
                "moneda": p.id_moneda.codigo_iso,
                "referencia": p.referencia,
                "estado": p.estado,
                "fecha_creacion": p.fecha_creacion.isoformat(),
            }
            for p in PagoPortalCliente.objects.filter(id_empresa=empresa, id_cliente=cliente, activo=True)
            .select_related("id_moneda")
            .order_by("-fecha_creacion")[:20]
        ]

        return Response(
            {
                "cliente": {
                    "id_cliente": str(cliente.pk),
                    "razon_social": cliente.razon_social,
                    "rif": cliente.rif,
                },
                "estado_cuenta_trimonetario": {
                    "saldo_pendiente": str(saldo_total),
                    "equivalencias": eq_saldo,
                    "documentos_pendientes": len(cxc_pendientes),
                    "cuentas_vencidas": int(cred["cxc_vencidas"]),
                },
                "facturas_fiscales": facturas,
                "notas_venta": notas,
                "pagos_reportados": pagos_reportados,
            }
        )


class PortalClientePagosView(APIView):
    """Carga de pagos por el cliente con soporte OCR/IA determinista de comprobantes."""

    authentication_classes = [PortalClienteTokenAuthentication]
    permission_classes = [IsPortalClienteAuthenticated]
    throttle_classes = [EscrituraRateThrottle]

    @swagger_auto_schema(request_body=PagoPortalClienteInputSerializer)
    @idempotent(scope="portal_cliente:pagos")
    def post(self, request):
        principal: PortalClientePrincipal = request.user
        empresa = principal.empresa
        cliente = principal.cliente

        ser = PagoPortalClienteInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data

        moneda = (
            Moneda.objects.filter(pk=vd["id_moneda"], activo=True)
            .filter(Q(es_generica=True) | Q(es_publica=True) | Q(empresa__isnull=True) | Q(empresa=empresa))
            .first()
        )
        metodo = (
            MetodoPago.objects.filter(pk=vd["id_metodo_pago"], activo=True)
            .filter(Q(es_generico=True) | Q(es_publico=True) | Q(empresa__isnull=True) | Q(empresa=empresa))
            .first()
        )
        if moneda is None or metodo is None:
            return domain_error_response(
                PortalClienteError("Moneda o método de pago inválido."),
                status_code=status.HTTP_400_BAD_REQUEST,
                key="detail",
            )

        url = (vd.get("comprobante_url") or "").strip()
        if url and not url.startswith(("https://", "http://")):
            return domain_error_response(
                PortalClienteError("La URL del comprobante debe iniciar con http:// o https://."),
                status_code=status.HTTP_400_BAD_REQUEST,
                key="detail",
            )

        ocr_json = {}
        if vd.get("texto_comprobante_ocr"):
            ocr_json = extraer_comprobante_pago_ocr(vd["texto_comprobante_ocr"], empresa=empresa)

        pago_portal = PagoPortalCliente.objects.create(
            id_empresa=empresa,
            id_cliente=cliente,
            monto=vd["monto"],
            id_moneda=moneda,
            id_metodo_pago=metodo,
            tasa=vd["tasa"],
            referencia=vd["referencia"] or str(ocr_json.get("referencia") or ""),
            comprobante_url=url,
            ocr_extraido_json=ocr_json,
            observaciones=vd["observaciones"],
        )
        return Response(
            {
                "id_pago_portal": str(pago_portal.pk),
                "estado": pago_portal.estado,
                "monto": str(pago_portal.monto),
                "referencia": pago_portal.referencia,
                "ocr_extraido": ocr_json,
            },
            status=status.HTTP_201_CREATED,
        )


class PortalClientePedidosView(APIView):
    """Permite al cliente autenticado generar pedidos self-service en estado PENDIENTE."""

    authentication_classes = [PortalClienteTokenAuthentication]
    permission_classes = [IsPortalClienteAuthenticated]
    throttle_classes = [EscrituraRateThrottle]

    @swagger_auto_schema(request_body=PedidoPortalClienteInputSerializer)
    @idempotent(scope="portal_cliente:pedidos")
    def post(self, request):
        principal: PortalClientePrincipal = request.user
        empresa = principal.empresa
        cliente = principal.cliente

        ser = PedidoPortalClienteInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data

        with transaction.atomic():
            prod_ids = [line["id_producto"] for line in vd["lineas"]]
            prods = {
                p.pk: p
                for p in Producto.objects.filter(id_empresa=empresa, activo=True, es_vendible=True, pk__in=prod_ids)
            }
            if len(prods) != len(set(prod_ids)):
                return Response(
                    {"lineas": "Uno o más productos no existen o no están disponibles."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            ped = Pedido.objects.create(
                id_empresa=empresa,
                id_cliente=cliente,
                numero_pedido=f"PED-B2B-{uuid.uuid4().hex[:8].upper()}",
                fecha_pedido=timezone.localdate(),
                estado="PENDIENTE",
                observaciones=vd["observaciones"] or "Pedido self-service Portal Clientes",
            )
            total = _CERO
            detalles = []
            for line in vd["lineas"]:
                prod = prods[line["id_producto"]]
                pu = Decimal(str(obtener_precio(prod, empresa, contacto=cliente.contacto))).quantize(
                    _Q4, rounding=ROUND_HALF_UP
                )
                sub = (line["cantidad"] * pu).quantize(_Q4, rounding=ROUND_HALF_UP)
                total += sub
                detalles.append(
                    DetallePedido(
                        id_pedido=ped,
                        id_producto=prod,
                        cantidad=line["cantidad"],
                        precio_unitario=pu,
                        subtotal=sub,
                    )
                )
            DetallePedido.objects.bulk_create(detalles)

        return Response(
            {
                "id_pedido": str(ped.pk),
                "numero_pedido": ped.numero_pedido,
                "estado": ped.estado,
                "total_estimado": str(total.quantize(_Q4, rounding=ROUND_HALF_UP)),
            },
            status=status.HTTP_201_CREATED,
        )


class PortalClienteTrackingView(APIView):
    """Despachos y paradas en curso del cliente autenticado (sin exponer PII ni otros clientes)."""

    authentication_classes = [PortalClienteTokenAuthentication]
    permission_classes = [IsPortalClienteAuthenticated]

    def get(self, request):
        principal: PortalClientePrincipal = request.user
        empresa = principal.empresa
        cliente = principal.cliente

        despachos = list(
            Despacho.objects.filter(
                id_empresa=empresa,
                id_nota_venta__id_cliente=cliente,
                activo=True,
            ).order_by("-fecha_despacho")[:20]
        )
        paradas_map: dict[Any, ParadaEntrega] = {
            p.id_despacho_id: p
            for p in ParadaEntrega.objects.filter(
                id_empresa=empresa,
                id_despacho__in=despachos,
                activo=True,
                id_ruta__activo=True,
            ).select_related("id_ruta")
        }
        items = []
        for d in despachos:
            parada = paradas_map.get(d.pk)
            items.append(
                {
                    "id_despacho": str(d.pk),
                    "numero_despacho": d.numero_despacho,
                    "estado_despacho": d.estado_despacho,
                    "fecha_despacho": d.fecha_despacho.isoformat(),
                    "token_tracking": str(parada.token_tracking) if parada else None,
                    "parada_estado": parada.estado if parada else None,
                    "eta_estimada": parada.eta_estimada.isoformat() if parada and parada.eta_estimada else None,
                    "tracking_url_publico": (f"/api/despacho/tracking/{parada.token_tracking}/" if parada else None),
                }
            )
        return Response({"despachos": items})
