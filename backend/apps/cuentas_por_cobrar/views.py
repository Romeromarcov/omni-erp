import logging
from decimal import Decimal

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.idempotency import idempotent
from apps.core.viewsets import BaseModelViewSet, get_empresas_visible

from .models import CuentaPorCobrar
from .serializers import CuentaPorCobrarSerializer

logger = logging.getLogger(__name__)


def _empresas(request):
    return get_empresas_visible(request.user)


class CuentaPorCobrarViewSet(BaseModelViewSet):
    queryset = CuentaPorCobrar.objects.all()
    serializer_class = CuentaPorCobrarSerializer

    # Integridad financiera (hallazgo BAJO, auditoría integral 2026-06-10): el
    # `monto`/`estado` de una CxC NO se editan por CRUD directo. El saldo y el
    # estado solo los mueve el flujo de abono atómico (`registrar_abono`, vía la
    # acción `abonar`). Sin esto, un PATCH/PUT directo podía marcar
    # `estado='pagada'` sin abonos o alterar `monto`, saltándose el lock, el tope
    # de saldo y el asiento contable. Se bloquean PUT/PATCH/DELETE (405); quedan
    # los GET (list/retrieve/aging/estado-cuenta), la acción POST `abonar` y el
    # POST de creación (lo usan los flujos de venta/integración y el seed E2E).
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        from django.db.models import DecimalField, Sum
        from django.db.models.functions import Coalesce

        # BUG-M2: anotar el total abonado evita el N+1 del serializer
        # (un aggregate por fila al calcular saldo_pendiente).
        qs = (
            CuentaPorCobrar.objects.filter(empresa__in=_empresas(self.request))
            .select_related("cliente", "empresa")
            .annotate(
                total_abonado_agg=Coalesce(
                    Sum("abonos__monto"),
                    Decimal("0"),
                    output_field=DecimalField(max_digits=18, decimal_places=2),
                )
            )
        )

        empresa_id = self.request.query_params.get("empresa")
        cliente_id = self.request.query_params.get("cliente")
        estado = self.request.query_params.get("estado")

        if empresa_id:
            qs = qs.filter(empresa=empresa_id)
        if cliente_id:
            # Plan D-D1: el filtro acepta el PK del crm.Cliente (FK) o el id
            # externo (Odoo). La FK solo se filtra si el valor es UUID válido.
            import uuid

            from django.db.models import Q

            filtro_cliente = Q(cliente_externo_id=cliente_id)
            try:
                uuid.UUID(str(cliente_id))
                filtro_cliente |= Q(cliente=cliente_id)
            except (ValueError, TypeError, AttributeError):
                pass
            qs = qs.filter(filtro_cliente)
        if estado:
            qs = qs.filter(estado=estado)

        return qs.order_by("fecha_vencimiento")

    @action(detail=False, methods=["get"], url_path="aging")
    def aging(self, request):
        """
        GET /api/cxc/cuentas-por-cobrar/aging/?empresa=<uuid>

        Devuelve el reporte de antigüedad de saldos por empresa.
        """
        from .services import calcular_aging

        empresa_id = request.query_params.get("empresa")
        if not empresa_id:
            return Response(
                {"error": "Parámetro 'empresa' requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if str(empresa_id) not in [str(e.id_empresa) for e in _empresas(request)]:
            return Response(
                {"error": "Empresa no encontrada o sin acceso."},
                status=status.HTTP_403_FORBIDDEN,
            )

        resultado = calcular_aging(empresa_id)
        # Serializar Decimals
        def fmt(d):
            return {k: str(v) if isinstance(v, Decimal) else v for k, v in d.items()}

        return Response(
            {
                "empresa_id": empresa_id,
                "corriente": fmt(resultado["corriente"]),
                "dias_1_30": fmt(resultado["dias_1_30"]),
                "dias_31_60": fmt(resultado["dias_31_60"]),
                "dias_61_90": fmt(resultado["dias_61_90"]),
                "dias_90_mas": fmt(resultado["dias_90_mas"]),
                "total_general": str(resultado["total_general"]),
            }
        )

    @action(detail=False, methods=["get"], url_path="estado-cuenta/(?P<cliente_id>[^/.]+)/pdf")
    def estado_cuenta_pdf(self, request, cliente_id=None):
        """
        GET /api/cxc/cuentas-por-cobrar/estado-cuenta/{cliente_id}/pdf/

        Genera el PDF de estado de cuenta CxC de un cliente para la empresa activa del usuario.
        Query param opcional: ?empresa=<uuid>
        """
        from django.http import HttpResponse
        from apps.cuentas_por_cobrar.pdf_estado_cuenta import generar_pdf_estado_cuenta

        # Resolver empresa (query param o primera empresa visible)
        empresa_id = request.query_params.get("empresa")
        empresas = list(_empresas(request))

        if empresa_id:
            empresa = next((e for e in empresas if str(e.id_empresa) == str(empresa_id)), None)
            if empresa is None:
                return Response({"error": "Empresa no encontrada o sin acceso."}, status=403)
        else:
            if not empresas:
                return Response({"error": "Sin empresas accesibles."}, status=403)
            empresa = empresas[0]

        # Resolver cliente
        try:
            from apps.crm.models import Cliente
            cliente = Cliente.objects.get(
                pk=cliente_id,
                id_empresa__in=[e.id_empresa for e in empresas],
            )
        except Exception:
            return Response({"error": "Cliente no encontrado o sin acceso."}, status=404)

        try:
            pdf_bytes = generar_pdf_estado_cuenta(empresa, cliente)
        except ImportError:
            # SEC-M4 (R-CODE-8): no filtrar el detalle interno al cliente.
            logger.exception("Generación de PDF de estado de cuenta no disponible")
            return Response(
                {"error": "Generación de PDF no disponible en este servidor."}, status=503
            )

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'inline; filename="estado_cuenta_{cliente.rif}.pdf"'
        )
        return response

    @idempotent("cxc:abonar")
    @action(detail=True, methods=["post"], url_path="abonar")
    def abonar(self, request, pk=None):
        """
        POST /api/cxc/cuentas-por-cobrar/{pk}/abonar/
        Body: {"monto": "500.00", "descripcion": "Pago parcial"}

        Idempotente: si se envía la cabecera ``Idempotency-Key``, un reintento con
        la misma clave devuelve el mismo resultado sin registrar un segundo abono.
        """
        from .services import AbonoError, registrar_abono

        cxc = self.get_object()
        monto_raw = request.data.get("monto")
        if not monto_raw:
            raise ValidationError({"monto": "Este campo es requerido."})

        try:
            monto = Decimal(str(monto_raw))
        except Exception:
            raise ValidationError({"monto": "Monto inválido."})

        descripcion = request.data.get("descripcion", "")

        try:
            abono = registrar_abono(
                cxc=cxc,
                monto=monto,
                usuario=request.user,
                descripcion=descripcion,
            )
        except AbonoError as exc:
            raise ValidationError(str(exc)) from exc

        cxc.refresh_from_db()
        return Response(
            {
                "abono_id": str(abono.pk),
                "cxc_id": str(cxc.pk),
                "monto_abonado": str(abono.monto),
                "estado_cxc": cxc.estado,
            },
            status=status.HTTP_201_CREATED,
        )
