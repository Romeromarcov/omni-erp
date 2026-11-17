"""Vistas REST del módulo ``apps/tareas`` (humano JWT/Session + máquina ``CapabilityToken``)."""

from __future__ import annotations

import uuid

from django.utils.dateparse import parse_date
from rest_framework import permissions, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.capability_auth import (
    CapabilityPrincipal,
    CapabilityTokenAuthentication,
    tiene_scope_capacidad,
)
from apps.core.models import Usuarios
from apps.core.viewsets import (
    BaseModelViewSet,
    EmpresaInjectMixin,
    get_empresa_primaria,
    get_empresas_visible,
)

from . import services
from .models import (
    AreaOperativa,
    MinutaReunion,
    PlantillaTareaRecurrente,
    Proyecto,
    RegistroAlertaTarea,
    SeccionProyecto,
    Tarea,
)
from .serializers import (
    AreaOperativaSerializer,
    ComentarioInputSerializer,
    ComentarioTareaSerializer,
    ConfiguracionSeguimientoTareasSerializer,
    DependenciaInputSerializer,
    DependenciaTareaSerializer,
    MinutaConfirmarInputSerializer,
    MinutaReunionSerializer,
    PlantillaTareaRecurrenteSerializer,
    ProyectoSerializer,
    RegistroAlertaTareaSerializer,
    SeccionProyectoSerializer,
    TareaEstadoInputSerializer,
    TareaMoverInputSerializer,
    TareaSerializer,
)

_AUTH_HUMANO_Y_CAPACIDAD = [
    JWTAuthentication,
    SessionAuthentication,
    CapabilityTokenAuthentication,
]


class PermisoTareas(permissions.BasePermission):
    """Autoriza usuarios humanos autenticados o ``CapabilityToken`` con scopes ``tareas:read/write``."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if isinstance(user, CapabilityPrincipal):
            if request.method in permissions.SAFE_METHODS:
                return tiene_scope_capacidad(user, "tareas:read") or tiene_scope_capacidad(
                    user, "tareas:write"
                )
            return tiene_scope_capacidad(user, "tareas:write")
        return True


def _actor_humano(request) -> Usuarios | None:
    return request.user if isinstance(request.user, Usuarios) else None


def _empresa_activa_o_403(request):
    empresa = get_empresa_primaria(request.user)
    if empresa is None:
        raise PermissionDenied("El usuario o token no tiene empresa activa asignada.")
    return empresa


def _respuesta_error_dominio(exc: services.TareaError) -> Response:
    return Response({"error": exc.args[0]}, status=exc.status)


def _resolver_usuario_tenant(empresa, usuario_id) -> Usuarios | None:
    if not usuario_id:
        return None
    usuario = Usuarios.objects.filter(pk=usuario_id, empresas=empresa, is_active=True).first()
    if usuario is None:
        raise NotFound("Usuario no encontrado en la empresa.")
    return usuario


class _BaseTareasViewSet(EmpresaInjectMixin, BaseModelViewSet):
    authentication_classes = _AUTH_HUMANO_Y_CAPACIDAD
    permission_classes = [PermisoTareas]
    model = None
    search_fields: list[str] = []
    lookup_value_regex = r"[0-9a-fA-F-]{36}"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.model.objects.none()
        return self.model.objects.filter(
            id_empresa__in=get_empresas_visible(self.request.user),
            activo=True,
        )

    def perform_destroy(self, instance):
        instance.soft_delete()


class AreaOperativaViewSet(_BaseTareasViewSet):
    model = AreaOperativa
    serializer_class = AreaOperativaSerializer
    search_fields = ["nombre", "slug"]
    ordering_fields = ["nombre", "fecha_creacion"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("departamento", "lider")
            .prefetch_related("miembros__usuario")
        )

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        empresa = _empresa_activa_o_403(request)
        raw_miembros = request.data.get("miembros") or []
        if not isinstance(raw_miembros, list):
            return Response(
                {"miembros": ["Debe ser una lista de UUIDs."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        miembros: list[Usuarios] = []
        for raw_uid in raw_miembros:
            try:
                uid = uuid.UUID(str(raw_uid))
            except (ValueError, TypeError):
                return Response(
                    {"miembros": ["UUID de usuario inválido."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            u = _resolver_usuario_tenant(empresa, uid)
            if u is not None:
                miembros.append(u)
        try:
            area = services.crear_area_operativa(
                empresa=empresa,
                nombre=d["nombre"],
                color=d.get("color", "#378ADD"),
                departamento=d.get("departamento"),
                lider=d.get("lider"),
                palabras_clave=d.get("palabras_clave") or [],
                miembros=miembros,
            )
        except services.TareaError as exc:
            return _respuesta_error_dominio(exc)
        return Response(AreaOperativaSerializer(area).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="miembros")
    def sincronizar_miembros(self, request, pk=None):
        area = self.get_object()
        raw_ids = request.data.get("usuarios")
        if not isinstance(raw_ids, list):
            return Response(
                {"error": "El campo 'usuarios' debe ser una lista de UUIDs."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        usuarios: list[Usuarios] = []
        for raw_uid in raw_ids:
            try:
                uid = uuid.UUID(str(raw_uid))
            except (ValueError, TypeError):
                return Response(
                    {"error": "UUID de usuario inválido en 'usuarios'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            u = _resolver_usuario_tenant(area.id_empresa, uid)
            if u is not None:
                usuarios.append(u)
        try:
            services.sincronizar_miembros_area(
                empresa=area.id_empresa, area=area, usuarios=usuarios
            )
        except services.TareaError as exc:
            return _respuesta_error_dominio(exc)
        area.refresh_from_db()
        return Response(AreaOperativaSerializer(area).data)


class ProyectoViewSet(_BaseTareasViewSet):
    model = Proyecto
    serializer_class = ProyectoSerializer
    search_fields = ["nombre", "descripcion"]
    ordering_fields = ["nombre", "fecha_creacion"]

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("area", "propietario")
            .prefetch_related("secciones")
        )
        archivado = self.request.query_params.get("archivado")
        if archivado in ("true", "1"):
            qs = qs.filter(archivado=True)
        elif archivado in ("false", "0"):
            qs = qs.filter(archivado=False)
        return qs

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        empresa = _empresa_activa_o_403(request)
        propietario = d.get("propietario") or _actor_humano(request)
        try:
            proyecto = services.crear_proyecto_con_secciones(
                empresa=empresa,
                nombre=d["nombre"],
                descripcion=d.get("descripcion", ""),
                color=d.get("color", "#1D9E75"),
                vista_predeterminada=d.get(
                    "vista_predeterminada", Proyecto.VistaPredeterminada.TABLERO
                ),
                area=d.get("area"),
                propietario=propietario,
            )
        except services.TareaError as exc:
            return _respuesta_error_dominio(exc)
        return Response(ProyectoSerializer(proyecto).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="mi-tablero")
    def mi_tablero(self, request):
        empresa = _empresa_activa_o_403(request)
        usuario_id = request.data.get("usuario")
        usuario = (
            _resolver_usuario_tenant(empresa, usuario_id)
            if usuario_id
            else _actor_humano(request)
        )
        if usuario is None:
            return Response(
                {"error": "Indica un usuario válido para asegurar su tablero personal."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            proyecto = services.asegurar_proyecto_personal(empresa=empresa, usuario=usuario)
        except services.TareaError as exc:
            return _respuesta_error_dominio(exc)
        return Response(ProyectoSerializer(proyecto).data)


class SeccionProyectoViewSet(_BaseTareasViewSet):
    model = SeccionProyecto
    serializer_class = SeccionProyectoSerializer
    search_fields = ["nombre"]
    ordering_fields = ["orden", "nombre"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("proyecto")
        proyecto_id = self.request.query_params.get("proyecto")
        if proyecto_id:
            try:
                uuid.UUID(str(proyecto_id))
                qs = qs.filter(proyecto_id=proyecto_id)
            except (ValueError, TypeError):
                return qs.none()
        return qs

    def perform_create(self, serializer):
        empresa = _empresa_activa_o_403(self.request)
        proyecto = serializer.validated_data["proyecto"]
        if proyecto.id_empresa_id != empresa.pk or not proyecto.activo:
            raise PermissionDenied("El proyecto no pertenece a tu empresa.")
        serializer.save(id_empresa=empresa)


class TareaViewSet(_BaseTareasViewSet):
    model = Tarea
    serializer_class = TareaSerializer
    search_fields = ["titulo", "descripcion", "entidad_tipo"]
    ordering_fields = ["orden_tablero", "fecha_vencimiento", "prioridad", "fecha_creacion"]

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("proyecto", "seccion", "area", "asignado_a", "creado_por")
        )
        p = self.request.query_params
        if p.get("estado"):
            qs = qs.filter(estado=p["estado"])
        if p.get("prioridad"):
            qs = qs.filter(prioridad=p["prioridad"])
        for param, field in (
            ("proyecto", "proyecto_id"),
            ("seccion", "seccion_id"),
            ("area", "area_id"),
            ("asignado_a", "asignado_a_id"),
            ("tarea_padre", "tarea_padre_id"),
            ("entidad_id", "entidad_id"),
        ):
            val = p.get(param)
            if val:
                try:
                    uuid.UUID(str(val))
                    qs = qs.filter(**{field: val})
                except (ValueError, TypeError):
                    return qs.none()
        if p.get("entidad_tipo"):
            qs = qs.filter(entidad_tipo=p["entidad_tipo"])
        if p.get("vencidas") in ("true", "1"):
            from django.utils import timezone as dj_tz  # noqa: PLC0415

            qs = qs.exclude(estado__in=["COMPLETADA", "CANCELADA"]).filter(
                fecha_vencimiento__lt=dj_tz.localdate()
            )
        desde = parse_date(p.get("vencimiento_desde") or "")
        if desde:
            qs = qs.filter(fecha_vencimiento__gte=desde)
        hasta = parse_date(p.get("vencimiento_hasta") or "")
        if hasta:
            qs = qs.filter(fecha_vencimiento__lte=hasta)
        return qs

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        empresa = _empresa_activa_o_403(request)

        try:
            tarea, creada = services.crear_tarea(
                empresa=empresa,
                titulo=d["titulo"],
                descripcion=d.get("descripcion", ""),
                estado=d.get("estado", "PENDIENTE"),
                prioridad=d.get("prioridad", "MEDIA"),
                origen=d.get("origen", Tarea.Origen.WEB),
                proyecto=d.get("proyecto"),
                seccion=d.get("seccion"),
                area=d.get("area"),
                tarea_padre=d.get("tarea_padre"),
                asignado_a=d.get("asignado_a"),
                creado_por=_actor_humano(request),
                fecha_inicio=d.get("fecha_inicio"),
                fecha_vencimiento=d.get("fecha_vencimiento"),
                hora_vencimiento=d.get("hora_vencimiento"),
                entidad_tipo=d.get("entidad_tipo") or "",
                entidad_id=d.get("entidad_id"),
                idempotency_key=d.get("idempotency_key") or "",
                usar_tablero_personal_si_falta=d.get(
                    "usar_tablero_personal_si_falta", True
                ),
            )
        except services.TareaError as exc:
            return _respuesta_error_dominio(exc)

        codigo_http = status.HTTP_201_CREATED if creada else status.HTTP_200_OK
        return Response(TareaSerializer(tarea).data, status=codigo_http)

    @action(detail=True, methods=["post"], url_path="cambiar-estado")
    def cambiar_estado(self, request, pk=None):
        tarea = self.get_object()
        ser = TareaEstadoInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            actualizada = services.cambiar_estado_tarea(
                tarea=tarea,
                nuevo_estado=ser.validated_data["estado"],
                actor=_actor_humano(request),
                motivo=ser.validated_data["motivo"],
            )
        except services.TareaError as exc:
            return _respuesta_error_dominio(exc)
        return Response(TareaSerializer(actualizada).data)

    @action(detail=True, methods=["post"], url_path="mover")
    def mover(self, request, pk=None):
        tarea = self.get_object()
        ser = TareaMoverInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        seccion = SeccionProyecto.objects.filter(
            pk=ser.validated_data["seccion"],
            id_empresa_id=tarea.id_empresa_id,
            activo=True,
        ).first()
        if seccion is None:
            raise NotFound("Sección destino no encontrada en la empresa.")
        try:
            actualizada = services.mover_tarea(
                tarea=tarea,
                seccion_destino=seccion,
                orden_tablero=ser.validated_data.get("orden_tablero"),
                actor=_actor_humano(request),
            )
        except services.TareaError as exc:
            return _respuesta_error_dominio(exc)
        return Response(TareaSerializer(actualizada).data)

    @action(detail=True, methods=["get", "post"], url_path="comentarios")
    def comentarios(self, request, pk=None):
        tarea = self.get_object()
        if request.method == "GET":
            qs = tarea.comentarios.filter(activo=True).order_by("fecha_creacion")
            return Response(ComentarioTareaSerializer(qs, many=True).data)

        ser = ComentarioInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            comentario = services.agregar_comentario(
                tarea=tarea,
                cuerpo=ser.validated_data["cuerpo"],
                autor=_actor_humano(request),
                autor_nombre=ser.validated_data["autor_nombre"],
            )
        except services.TareaError as exc:
            return _respuesta_error_dominio(exc)
        return Response(
            ComentarioTareaSerializer(comentario).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["get", "post"], url_path="dependencias")
    def dependencias(self, request, pk=None):
        tarea = self.get_object()
        if request.method == "GET":
            qs = tarea.dependencias_entrantes.filter(activo=True).select_related(
                "depende_de"
            )
            return Response(DependenciaTareaSerializer(qs, many=True).data)

        ser = DependenciaInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        depende_de = Tarea.objects.filter(
            pk=ser.validated_data["depende_de"],
            id_empresa_id=tarea.id_empresa_id,
            activo=True,
        ).first()
        if depende_de is None:
            raise NotFound("Tarea prerrequisito no encontrada en la empresa.")
        try:
            dep = services.agregar_dependencia(
                empresa=tarea.id_empresa,
                tarea=tarea,
                depende_de=depende_de,
            )
        except services.TareaError as exc:
            return _respuesta_error_dominio(exc)
        return Response(
            DependenciaTareaSerializer(dep).data, status=status.HTTP_201_CREATED
        )


class PlantillaTareaRecurrenteViewSet(_BaseTareasViewSet):
    model = PlantillaTareaRecurrente
    serializer_class = PlantillaTareaRecurrenteSerializer
    search_fields = ["titulo", "descripcion"]
    ordering_fields = ["proxima_ejecucion", "titulo", "fecha_creacion"]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("proyecto", "area", "asignado_a", "creado_por")
        )

    def perform_create(self, serializer):
        empresa = _empresa_activa_o_403(self.request)
        for campo in ("proyecto", "area"):
            rel = serializer.validated_data.get(campo)
            if rel is not None and rel.id_empresa_id != empresa.pk:
                raise PermissionDenied(f"El campo '{campo}' pertenece a otra empresa.")
        asignado = serializer.validated_data.get("asignado_a")
        if asignado is not None:
            _resolver_usuario_tenant(empresa, asignado.pk)
        serializer.save(id_empresa=empresa, creado_por=_actor_humano(self.request))

    @action(detail=False, methods=["post"], url_path="materializar")
    def materializar(self, request):
        empresa = _empresa_activa_o_403(request)
        fecha = parse_date(str(request.data.get("fecha") or ""))
        try:
            res = services.generar_tareas_recurrentes_pendientes(
                empresa, fecha_hoy=fecha
            )
        except services.TareaError as exc:
            return _respuesta_error_dominio(exc)
        return Response(res)


class MinutaReunionViewSet(_BaseTareasViewSet):
    model = MinutaReunion
    serializer_class = MinutaReunionSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]
    search_fields = ["titulo", "texto_fuente"]
    ordering_fields = ["fecha_reunion", "fecha_creacion"]

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        empresa = _empresa_activa_o_403(request)
        try:
            minuta = services.crear_minuta_borrador(
                empresa=empresa,
                titulo=d["titulo"],
                fecha_reunion=d.get("fecha_reunion"),
                texto_fuente=d.get("texto_fuente") or "",
                documento_adjunto=d.get("documento_adjunto"),
                items_propuestos=d.get("items_propuestos") or [],
                creado_por=_actor_humano(request),
            )
        except services.TareaError as exc:
            return _respuesta_error_dominio(exc)
        return Response(
            MinutaReunionSerializer(minuta).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["post"], url_path="confirmar")
    def confirmar(self, request, pk=None):
        minuta = self.get_object()
        ser = MinutaConfirmarInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        proyecto = None
        if d.get("proyecto"):
            proyecto = Proyecto.objects.filter(
                pk=d["proyecto"], id_empresa_id=minuta.id_empresa_id, activo=True
            ).first()
            if proyecto is None:
                raise NotFound("Proyecto no encontrado en la empresa.")
        try:
            tareas = services.confirmar_minuta(
                minuta=minuta,
                items_confirmados=d.get("items_confirmados"),
                actor=_actor_humano(request),
                proyecto=proyecto,
            )
        except services.TareaError as exc:
            return _respuesta_error_dominio(exc)
        minuta.refresh_from_db()
        return Response(
            {
                "minuta": MinutaReunionSerializer(minuta).data,
                "tareas_creadas": TareaSerializer(tareas, many=True).data,
            }
        )


class ConfiguracionSeguimientoView(APIView):
    authentication_classes = _AUTH_HUMANO_Y_CAPACIDAD
    permission_classes = [PermisoTareas]

    def get(self, request):
        empresa = _empresa_activa_o_403(request)
        cfg = services.obtener_o_crear_configuracion_seguimiento(empresa)
        return Response(ConfiguracionSeguimientoTareasSerializer(cfg).data)

    def patch(self, request):
        empresa = _empresa_activa_o_403(request)
        cfg = services.obtener_o_crear_configuracion_seguimiento(empresa)
        if "gerente" in request.data and request.data.get("gerente"):
            try:
                ger_uid = uuid.UUID(str(request.data["gerente"]))
            except (ValueError, TypeError):
                return Response(
                    {"error": "UUID de gerente inválido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            _resolver_usuario_tenant(empresa, ger_uid)
        ser = ConfiguracionSeguimientoTareasSerializer(
            cfg, data=request.data, partial=True
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class ResumenEjecutivoTareasView(APIView):
    authentication_classes = _AUTH_HUMANO_Y_CAPACIDAD
    permission_classes = [PermisoTareas]

    def get(self, request):
        empresa = _empresa_activa_o_403(request)
        fecha = parse_date(request.query_params.get("fecha") or "")
        return Response(services.resumen_ejecutivo_equipo(empresa, hoy=fecha))


class EjecutarSeguimientoView(APIView):
    authentication_classes = _AUTH_HUMANO_Y_CAPACIDAD
    permission_classes = [PermisoTareas]

    def post(self, request):
        empresa = _empresa_activa_o_403(request)
        momento = str(request.data.get("momento") or "AUTO").upper()
        if momento not in ("MANANA", "TARDE", "AUTO"):
            return Response(
                {"error": "momento debe ser MANANA, TARDE o AUTO."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(services.ejecutar_seguimiento_empresa(empresa, momento=momento))


class RegistroAlertaTareaViewSet(_BaseTareasViewSet):
    model = RegistroAlertaTarea
    serializer_class = RegistroAlertaTareaSerializer
    http_method_names = ["get", "head", "options"]
    search_fields = ["clave_alerta", "detalle"]
    ordering_fields = ["fecha_creacion"]

    def get_queryset(self):
        return super().get_queryset().select_related("tarea", "destinatario")
