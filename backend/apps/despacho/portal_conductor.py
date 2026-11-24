"""Portal / App Independiente de Conductores y Logística de Campo (Plan 09 Fase 7.4).

Provee:
- ``GET /api/despacho/portal-conductor/mis-rutas/``: rutas activas con paradas ordenadas VRP y enlaces 1-tap Waze/Maps.
- ``POST /api/despacho/portal-conductor/paradas/<pk>/escanear-bulto/``: validación de código/SKU de bulto entregado.
- ``POST /api/despacho/portal-conductor/paradas/<pk>/epod/``: captura ePOD (foto/firma/GPS) y cobro contra entrega offline-safe.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.exceptions import domain_error_response
from apps.core.idempotency import idempotent
from apps.core.throttling import EscrituraRateThrottle
from apps.core.viewsets import get_empresa_primaria, get_empresas_visible, validar_uuid_param

from .models import Conductor, DetalleDespacho, ParadaEntrega, RutaDespacho
from .serializers_tms import ParadaEntregaSerializer, RegistrarEPODInputSerializer
from .services_tms import TMSError, registrar_epod_parada


class EscanearBultoInputSerializer(serializers.Serializer):
    codigo_bulto = serializers.CharField(max_length=120)
    observacion = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


def _resolver_empresa_conductor(request):
    visibles = get_empresas_visible(request.user)
    raw_emp = request.query_params.get("empresa") or (
        request.data.get("id_empresa") if isinstance(request.data, dict) else None
    )
    if raw_emp:
        uid = validar_uuid_param(str(raw_emp), "id_empresa")
        emp = visibles.filter(pk=uid).first()
        if emp is None:
            raise ValidationError({"id_empresa": "Empresa fuera de su alcance."})
        return emp
    emp = get_empresa_primaria(request.user) or visibles.first()
    if emp is None:
        raise ValidationError({"id_empresa": "Usuario sin empresa asignada."})
    return emp


def _links_navegacion(lat: Any, lng: Any) -> dict[str, str | None]:
    if lat is None or lng is None:
        return {"waze_url": None, "google_maps_url": None}
    return {
        "waze_url": f"https://waze.com/ul?ll={lat},{lng}&navigate=yes",
        "google_maps_url": f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}",
    }


class PortalConductorViewSet(viewsets.ViewSet):
    """App operativa del Conductor: rutas VRP asignadas, Waze/Maps 1-tap, escaneo de bultos y ePOD."""

    permission_classes = [permissions.IsAuthenticated]

    def _parada_del_conductor(self, request, pk: str) -> ParadaEntrega:
        uid = validar_uuid_param(str(pk), "parada")
        visibles = get_empresas_visible(request.user)
        parada = (
            ParadaEntrega.objects.select_related("id_ruta", "id_ruta__id_conductor", "id_despacho", "id_empresa")
            .filter(pk=uid, id_empresa__in=visibles, activo=True, id_ruta__activo=True)
            .first()
        )
        if parada is None:
            raise ValidationError({"detail": "Parada no encontrada."})
        cond = parada.id_ruta.id_conductor
        es_admin = bool(
            getattr(request.user, "es_superusuario_omni", False)
            or getattr(request.user, "is_superuser", False)
            or getattr(request.user, "is_staff", False)
        )
        if cond is not None and cond.id_usuario_id and cond.id_usuario_id != request.user.pk and not es_admin:
            raise ValidationError({"detail": "Esta parada está asignada a otro conductor."})
        return parada

    @action(detail=False, methods=["get"], url_path="mis-rutas")
    def mis_rutas(self, request):
        """Lista rutas PLANIFICADA/EN_CURSO asignadas al conductor autenticado (o todas si es supervisor)."""
        empresa = _resolver_empresa_conductor(request)
        qs = (
            RutaDespacho.objects.filter(
                id_empresa=empresa,
                activo=True,
                estado__in=("PLANIFICADA", "EN_CURSO"),
            )
            .select_related("id_vehiculo", "id_conductor")
            .prefetch_related("paradas__id_despacho")
            .order_by("fecha_ruta", "-fecha_creacion")
        )
        conductor_param = request.query_params.get("conductor")
        es_admin = bool(
            getattr(request.user, "es_superusuario_omni", False)
            or getattr(request.user, "is_superuser", False)
            or getattr(request.user, "is_staff", False)
        )
        if conductor_param:
            cid = validar_uuid_param(conductor_param, "conductor")
            qs = qs.filter(id_conductor_id=cid)
        else:
            cond = Conductor.objects.filter(id_empresa=empresa, id_usuario=request.user, activo=True).first()
            if cond is not None:
                qs = qs.filter(id_conductor=cond)
            elif not es_admin:
                qs = qs.none()

        rutas_out = []
        for r in qs[:20]:
            paradas_out = []
            for p in r.paradas.filter(activo=True).order_by("secuencia"):
                nav = _links_navegacion(p.latitud, p.longitud)
                paradas_out.append(
                    {
                        "id_parada": str(p.pk),
                        "secuencia": p.secuencia,
                        "estado": p.estado,
                        "despacho_numero": p.id_despacho.numero_despacho,
                        "direccion_texto": p.direccion_texto,
                        "latitud": str(p.latitud) if p.latitud is not None else None,
                        "longitud": str(p.longitud) if p.longitud is not None else None,
                        "eta_estimada": p.eta_estimada.isoformat() if p.eta_estimada else None,
                        "waze_url": nav["waze_url"],
                        "google_maps_url": nav["google_maps_url"],
                    }
                )
            rutas_out.append(
                {
                    "id_ruta": str(r.pk),
                    "codigo": r.codigo,
                    "estado": r.estado,
                    "fecha_ruta": r.fecha_ruta.isoformat(),
                    "vehiculo_placa": r.id_vehiculo.placa if r.id_vehiculo else None,
                    "paradas": paradas_out,
                }
            )
        return Response({"empresa_id": str(empresa.pk), "rutas": rutas_out})

    @swagger_auto_schema(request_body=EscanearBultoInputSerializer)
    @idempotent(scope="portal_conductor:escanear_bulto")
    @action(
        detail=False,
        methods=["post"],
        url_path=r"paradas/(?P<parada_id>[^/.]+)/escanear-bulto",
        throttle_classes=[*viewsets.ViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def escanear_bulto(self, request, parada_id=None):
        """Valida el código de barras o SKU del bulto contra los productos del despacho."""
        parada = self._parada_del_conductor(request, parada_id)
        ser = EscanearBultoInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        codigo = ser.validated_data["codigo_bulto"].strip()

        with transaction.atomic():
            parada_locked = ParadaEntrega.objects.select_for_update(of=("self",)).get(pk=parada.pk)
            detalles = list(
                DetalleDespacho.objects.filter(id_despacho=parada_locked.id_despacho).select_related("id_producto")
            )
            coincide = any(
                (det.id_producto.codigo_barras or "").strip().lower() == codigo.lower()
                or (det.id_producto.sku or "").strip().lower() == codigo.lower()
                for det in detalles
            )
            if not coincide:
                return Response(
                    {"detail": f"El código '{codigo}' no corresponde a ningún producto del despacho."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            sello = f"[SCAN {timezone.now().strftime('%Y-%m-%d %H:%M')} codigo={codigo}]"
            prev = (parada_locked.epod_observaciones or "").strip()
            parada_locked.epod_observaciones = f"{prev}\n{sello}".strip() if prev else sello
            parada_locked.save(update_fields=["epod_observaciones", "fecha_actualizacion"])

        return Response(
            {"id_parada": str(parada.pk), "codigo_bulto": codigo, "verificado": True},
            status=status.HTTP_200_OK,
        )

    @swagger_auto_schema(request_body=RegistrarEPODInputSerializer)
    @idempotent(scope="portal_conductor:epod")
    @action(
        detail=False,
        methods=["post"],
        url_path=r"paradas/(?P<parada_id>[^/.]+)/epod",
        throttle_classes=[*viewsets.ViewSet.throttle_classes, EscrituraRateThrottle],
    )
    def registrar_epod(self, request, parada_id=None):
        """Registra ePOD (foto, firma, GPS) y cobro en sitio tolerante a reintentos offline."""
        parada = self._parada_del_conductor(request, parada_id)
        ser = RegistrarEPODInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        try:
            res = registrar_epod_parada(
                parada,
                request.user,
                resultado=vd["resultado"],
                receptor_nombre=vd["receptor_nombre"],
                receptor_cedula=vd["receptor_cedula"],
                firma_base64=vd["firma_base64"],
                foto_url=vd["foto_url"],
                latitud=vd.get("latitud"),
                longitud=vd.get("longitud"),
                observaciones=vd["observaciones"],
                motivo_rechazo=vd["motivo_rechazo"],
                cobro=vd.get("cobro"),
            )
        except TMSError as exc:
            return domain_error_response(exc, status_code=status.HTTP_400_BAD_REQUEST, key="detail")
        parada.refresh_from_db()
        return Response(
            {
                "parada": ParadaEntregaSerializer(parada, context={"request": request}).data,
                "despacho_estado": res["despacho_estado"],
                "pago_id": res["pago_id"],
                "ruta_completada": res["ruta_completada"],
            },
            status=status.HTTP_200_OK,
        )
