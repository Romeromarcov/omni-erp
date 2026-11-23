"""Vistas REST SENIAT 360°: Retenciones IVA (.txt/PDF), ISLR (.xml/PDF), Imprenta Digital, IGTF/ITF y Libro Art. 177."""

from __future__ import annotations

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.compras.models import FacturaCompra
from apps.contabilidad.services import AsientoError
from apps.core.exceptions import domain_error_response
from apps.core.idempotency import idempotent
from apps.core.models import Contacto
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import (
    ActiveFilterMixin,
    NulSafeFilterMixin,
    get_empresas_visible,
    validar_uuid_param,
)
from apps.localizacion_ve.imprenta_digital import (
    ImprentaDigitalError,
    anular_en_imprenta_digital,
    emitir_en_imprenta_digital,
)
from apps.ventas.models import FacturaFiscal

from .models import (
    ComprobanteRetencionISLR,
    ComprobanteRetencionIVA,
    ConceptoRetencionISLR,
    DocumentoImprentaDigital,
)
from .serializers_seniat import (
    CalcularIGTFITFInputSerializer,
    ComprobanteRetencionISLRSerializer,
    ComprobanteRetencionIVASerializer,
    ConceptoRetencionISLRSerializer,
    DocumentoImprentaDigitalSerializer,
    EmitirImprentaDigitalInputSerializer,
    EmitirRetencionISLRInputSerializer,
    EmitirRetencionIVAInputSerializer,
)
from .services_retenciones import (
    RetencionFiscalError,
    anular_retencion_islr,
    anular_retencion_iva,
    calcular_igtf_y_itf_bancario,
    emitir_retencion_islr,
    emitir_retencion_iva,
    generar_libro_inventario_art177,
    generar_pdf_comprobante_retencion_islr,
    generar_pdf_comprobante_retencion_iva,
    generar_txt_retenciones_iva_seniat,
    generar_xml_retenciones_islr_seniat,
)
from .views_libros import _resolver_empresa, _resolver_rango


def _resolver_empresa_mutacion(user, raw_empresa_id=None):
    empresas = get_empresas_visible(user)
    if raw_empresa_id:
        uid = validar_uuid_param(str(raw_empresa_id), "id_empresa")
        empresa = empresas.filter(pk=uid).first()
        if empresa is None:
            raise ValidationError({"id_empresa": "Empresa no encontrada o sin acceso."})
        return empresa
    empresa = empresas.first()
    if empresa is None:
        raise ValidationError({"id_empresa": "No tiene una empresa activa asignada."})
    return empresa


def _no_nul(valor: str | None, campo: str) -> str | None:
    if valor is None or valor == "":
        return None
    if "\x00" in str(valor):
        raise ValidationError({campo: "Parámetro inválido."})
    return str(valor).strip()


class ConceptoRetencionISLRViewSet(NulSafeFilterMixin, viewsets.ReadOnlyModelViewSet):
    """Catálogo global Decreto 1808 de conceptos de retención ISLR."""

    queryset = ConceptoRetencionISLR.objects.filter(activo=True).order_by("codigo")
    serializer_class = ConceptoRetencionISLRSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["codigo", "nombre", "tipo_persona_fiscal"]
    ordering_fields = ["codigo", "porcentaje_retencion"]
    ordering = ["codigo"]

    def get_queryset(self):
        qs = super().get_queryset()
        tipo = _no_nul(self.request.query_params.get("tipo_persona_fiscal"), "tipo_persona_fiscal")
        if tipo:
            qs = qs.filter(tipo_persona_fiscal=tipo.upper())
        return qs


class ComprobanteRetencionIVAViewSet(NulSafeFilterMixin, ActiveFilterMixin, viewsets.ReadOnlyModelViewSet):
    """Comprobantes de Retención IVA: emisión, anulación, PDF y exportador TXT 16 columnas SENIAT."""

    queryset = ComprobanteRetencionIVA.objects.all()
    serializer_class = ComprobanteRetencionIVASerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["numero_comprobante", "numero_documento", "contacto__nombre", "contacto__rif"]
    ordering_fields = ["fecha_emision", "numero_comprobante", "monto_retenido"]
    ordering = ["-fecha_emision", "-numero_comprobante"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("contacto", "id_empresa")
        qs = qs.filter(id_empresa__in=get_empresas_visible(self.request.user))
        periodo = _no_nul(self.request.query_params.get("periodo"), "periodo")
        if periodo:
            qs = qs.filter(periodo_impositivo=periodo)
        estado = _no_nul(self.request.query_params.get("estado"), "estado")
        if estado:
            qs = qs.filter(estado=estado.upper())
        tipo_op = _no_nul(self.request.query_params.get("tipo_operacion"), "tipo_operacion")
        if tipo_op:
            qs = qs.filter(tipo_operacion=tipo_op.upper())
        return qs

    @idempotent(scope="fiscal:ret_iva")
    @action(
        detail=False,
        methods=["post"],
        throttle_classes=[*viewsets.ReadOnlyModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def emitir(self, request):
        """Emite atómicamente un Comprobante de Retención de IVA."""
        inp = EmitirRetencionIVAInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        vd = inp.validated_data
        empresa = _resolver_empresa_mutacion(request.user, vd.get("id_empresa"))

        contacto = Contacto.objects.filter(pk=vd["contacto"], id_empresa=empresa, activo=True).first()
        if contacto is None:
            raise ValidationError({"contacto": "Contacto no encontrado en la empresa activa."})

        fc = None
        if vd.get("factura_compra"):
            fc = FacturaCompra.objects.filter(pk=vd["factura_compra"], id_empresa=empresa, activo=True).first()
            if fc is None:
                raise ValidationError({"factura_compra": "Factura de compra no encontrada en la empresa activa."})

        fv = None
        if vd.get("factura_venta"):
            fv = FacturaFiscal.objects.filter(pk=vd["factura_venta"], id_empresa=empresa, activo=True).first()
            if fv is None:
                raise ValidationError({"factura_venta": "Factura fiscal no encontrada en la empresa activa."})

        try:
            comp = emitir_retencion_iva(
                empresa=empresa,
                contacto=contacto,
                fecha_emision=vd.get("fecha_emision") or timezone.localdate(),
                numero_documento=vd["numero_documento"],
                base_imponible=vd["base_imponible"],
                monto_total_documento=vd.get("monto_total_documento"),
                monto_exento=vd.get("monto_exento", 0),
                alicuota_iva=vd.get("alicuota_iva", 16),
                monto_iva=vd.get("monto_iva"),
                porcentaje_retencion=vd.get("porcentaje_retencion"),
                numero_control=vd.get("numero_control", ""),
                numero_documento_afectado=vd.get("numero_documento_afectado", "0"),
                tipo_operacion=vd.get("tipo_operacion", "COMPRA"),
                tipo_transaccion=vd.get("tipo_transaccion", "01"),
                factura_compra=fc,
                factura_venta=fv,
                usuario=request.user,
            )
        except AsientoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except (RetencionFiscalError, ValueError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(ComprobanteRetencionIVASerializer(comp).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        """Anula lógicamente un Comprobante de Retención IVA."""
        comp = self.get_object()
        try:
            anulado = anular_retencion_iva(comp, usuario=request.user)
        except AsientoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except RetencionFiscalError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(ComprobanteRetencionIVASerializer(anulado).data)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        """Descarga PDF del comprobante de retención IVA."""
        comp = self.get_object()
        contenido = generar_pdf_comprobante_retencion_iva(comp)
        resp = HttpResponse(contenido, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="retencion_iva_{comp.numero_comprobante}.pdf"'
        return resp

    @action(detail=False, methods=["get"], url_path="exportar-txt")
    def exportar_txt(self, request):
        """Exporta relación TXT SENIAT de 16 columnas para el período ?periodo=AAAAMM."""
        emp_id = request.query_params.get("id_empresa") or request.query_params.get("empresa")
        empresa = _resolver_empresa_mutacion(request.user, emp_id)
        periodo = _no_nul(request.query_params.get("periodo"), "periodo") or f"{timezone.localdate():%Y%m}"
        try:
            txt = generar_txt_retenciones_iva_seniat(empresa, periodo)
        except RetencionFiscalError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        resp = HttpResponse(txt, content_type="text/plain; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="retenciones_iva_{periodo}.txt"'
        return resp


class ComprobanteRetencionISLRViewSet(NulSafeFilterMixin, ActiveFilterMixin, viewsets.ReadOnlyModelViewSet):
    """Comprobantes de Retención ISLR (Decreto 1808): emisión, anulación, PDF y exportador XML SENIAT."""

    queryset = ComprobanteRetencionISLR.objects.all()
    serializer_class = ComprobanteRetencionISLRSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["numero_comprobante", "numero_factura", "contacto__nombre", "concepto__codigo"]
    ordering_fields = ["fecha_emision", "numero_comprobante", "monto_retenido"]
    ordering = ["-fecha_emision", "-numero_comprobante"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("contacto", "concepto", "id_empresa")
        qs = qs.filter(id_empresa__in=get_empresas_visible(self.request.user))
        periodo = _no_nul(self.request.query_params.get("periodo"), "periodo")
        if periodo:
            qs = qs.filter(periodo_impositivo=periodo)
        estado = _no_nul(self.request.query_params.get("estado"), "estado")
        if estado:
            qs = qs.filter(estado=estado.upper())
        return qs

    @idempotent(scope="fiscal:ret_islr")
    @action(
        detail=False,
        methods=["post"],
        throttle_classes=[*viewsets.ReadOnlyModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def emitir(self, request):
        """Emite atómicamente un Comprobante de Retención ISLR (Decreto 1808)."""
        inp = EmitirRetencionISLRInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        vd = inp.validated_data
        empresa = _resolver_empresa_mutacion(request.user, vd.get("id_empresa"))

        contacto = Contacto.objects.filter(pk=vd["contacto"], id_empresa=empresa, activo=True).first()
        if contacto is None:
            raise ValidationError({"contacto": "Contacto no encontrado en la empresa activa."})

        concepto = ConceptoRetencionISLR.objects.filter(pk=vd["concepto"], activo=True).first()
        if concepto is None:
            raise ValidationError({"concepto": "Concepto ISLR no encontrado o inactivo."})

        fc = None
        if vd.get("factura_compra"):
            fc = FacturaCompra.objects.filter(pk=vd["factura_compra"], id_empresa=empresa, activo=True).first()
            if fc is None:
                raise ValidationError({"factura_compra": "Factura de compra no encontrada en la empresa activa."})

        try:
            comp = emitir_retencion_islr(
                empresa=empresa,
                contacto=contacto,
                concepto=concepto,
                fecha_emision=vd.get("fecha_emision") or timezone.localdate(),
                numero_factura=vd["numero_factura"],
                monto_operacion=vd["monto_operacion"],
                numero_control=vd.get("numero_control", ""),
                factura_compra=fc,
                valor_ut=vd.get("valor_ut"),
                omitir_exencion=bool(vd.get("omitir_exencion", False)),
                usuario=request.user,
            )
        except AsientoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except (RetencionFiscalError, ValueError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(ComprobanteRetencionISLRSerializer(comp).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        """Anula lógicamente un Comprobante de Retención ISLR."""
        comp = self.get_object()
        try:
            anulado = anular_retencion_islr(comp, usuario=request.user)
        except AsientoError as exc:
            return domain_error_response(exc, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except RetencionFiscalError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(ComprobanteRetencionISLRSerializer(anulado).data)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        """Descarga PDF del comprobante de retención ISLR."""
        comp = self.get_object()
        contenido = generar_pdf_comprobante_retencion_islr(comp)
        resp = HttpResponse(contenido, content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="retencion_islr_{comp.numero_comprobante}.pdf"'
        return resp

    @action(detail=False, methods=["get"], url_path="exportar-xml")
    def exportar_xml(self, request):
        """Exporta XML SENIAT de retenciones ISLR para ?periodo=AAAAMM."""
        emp_id = request.query_params.get("id_empresa") or request.query_params.get("empresa")
        empresa = _resolver_empresa_mutacion(request.user, emp_id)
        periodo = _no_nul(request.query_params.get("periodo"), "periodo") or f"{timezone.localdate():%Y%m}"
        try:
            xml_str = generar_xml_retenciones_islr_seniat(empresa, periodo)
        except RetencionFiscalError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        resp = HttpResponse(xml_str, content_type="application/xml; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="retenciones_islr_{periodo}.xml"'
        return resp


class DocumentoImprentaDigitalViewSet(NulSafeFilterMixin, ActiveFilterMixin, viewsets.ReadOnlyModelViewSet):
    """Emisión y anulación ante Imprenta Digital SENIAT (Providencia 000102/000121)."""

    queryset = DocumentoImprentaDigital.objects.all()
    serializer_class = DocumentoImprentaDigitalSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["referencia_documento", "numero_control_asignado", "codigo_validacion"]
    ordering_fields = ["emitido_en", "tipo_documento", "estado"]
    ordering = ["-emitido_en"]

    def get_queryset(self):
        qs = super().get_queryset().filter(id_empresa__in=get_empresas_visible(self.request.user))
        tipo_doc = _no_nul(self.request.query_params.get("tipo_documento"), "tipo_documento")
        if tipo_doc:
            qs = qs.filter(tipo_documento=tipo_doc.upper())
        return qs

    @idempotent(scope="fiscal:imprenta_digital")
    @action(
        detail=False,
        methods=["post"],
        throttle_classes=[*viewsets.ReadOnlyModelViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def emitir(self, request):
        """Emite documento ante la Imprenta Digital configurada (Simulado o Unidigital)."""
        inp = EmitirImprentaDigitalInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        vd = inp.validated_data
        empresa = _resolver_empresa_mutacion(request.user, vd.get("id_empresa"))
        try:
            doc = emitir_en_imprenta_digital(
                empresa=empresa,
                tipo_documento=vd["tipo_documento"],
                referencia_documento=vd["referencia_documento"],
                payload=vd.get("payload"),
                proveedor_override=vd.get("proveedor"),
            )
        except (ImprentaDigitalError, ValueError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(DocumentoImprentaDigitalSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        """Anula una emisión fiscal previa ante la Imprenta Digital."""
        doc = self.get_object()
        motivo = str(request.data.get("motivo") or "") if isinstance(request.data, dict) else ""
        try:
            anulado = anular_en_imprenta_digital(doc, motivo=motivo)
        except (ImprentaDigitalError, ValueError) as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(DocumentoImprentaDigitalSerializer(anulado).data)


class LibroInventarioArt177View(APIView):
    """GET /api/fiscal/libro-inventario-art177/?empresa=<uuid>&periodo=YYYY-MM."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        empresa, err = _resolver_empresa(request)
        if err:
            return err
        inicio, fin, err = _resolver_rango(request)
        if err:
            return err
        try:
            data = generar_libro_inventario_art177(empresa, inicio, fin)
        except RetencionFiscalError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(data)


class CalcularIGTFITFView(APIView):
    """POST /api/fiscal/calcular-igtf-itf/ — desglosa IGTF 3% (divisa) e ITF bancario 2% (SPE)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        inp = CalcularIGTFITFInputSerializer(data=request.data)
        inp.is_valid(raise_exception=True)
        vd = inp.validated_data
        try:
            res = calcular_igtf_y_itf_bancario(
                vd["monto"],
                vd["moneda_iso"],
                es_contribuyente_especial=bool(vd.get("es_contribuyente_especial", False)),
                es_debito_bancario=bool(vd.get("es_debito_bancario", False)),
                alicuota_igtf=vd.get("alicuota_igtf", 3),
                alicuota_itf=vd.get("alicuota_itf", 2),
            )
        except RetencionFiscalError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        return Response(res)
