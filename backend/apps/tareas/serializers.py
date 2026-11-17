"""Serializers DRF del módulo ``apps/tareas``."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.serializers import BaseModelSerializer

from .models import (
    AreaOperativa,
    ComentarioTarea,
    ConfiguracionSeguimientoTareas,
    DependenciaTarea,
    EstadoTarea,
    MiembroAreaOperativa,
    MinutaReunion,
    PlantillaTareaRecurrente,
    PrioridadTarea,
    Proyecto,
    RegistroAlertaTarea,
    SeccionProyecto,
    Tarea,
)


class MiembroAreaOperativaSerializer(BaseModelSerializer):
    usuario_username = serializers.CharField(source="usuario.username", read_only=True)
    usuario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = MiembroAreaOperativa
        fields = [
            "id_miembro_area",
            "id_empresa",
            "area",
            "usuario",
            "usuario_username",
            "usuario_nombre",
            "activo",
            "fecha_creacion",
        ]
        read_only_fields = ["id_miembro_area", "id_empresa", "activo", "fecha_creacion"]

    def get_usuario_nombre(self, obj: MiembroAreaOperativa) -> str:
        if not obj.usuario_id or not obj.usuario:
            return ""
        return obj.usuario.get_full_name().strip() or obj.usuario.username


class AreaOperativaSerializer(BaseModelSerializer):
    lider_nombre = serializers.SerializerMethodField()
    miembros = serializers.SerializerMethodField()

    class Meta:
        model = AreaOperativa
        fields = [
            "id_area",
            "id_empresa",
            "nombre",
            "slug",
            "color",
            "departamento",
            "lider",
            "lider_nombre",
            "palabras_clave",
            "miembros",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_area",
            "id_empresa",
            "slug",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def get_lider_nombre(self, obj: AreaOperativa) -> str:
        if not obj.lider_id or not obj.lider:
            return ""
        return obj.lider.get_full_name().strip() or obj.lider.username

    def get_miembros(self, obj: AreaOperativa) -> list[dict]:
        qs = obj.miembros.filter(activo=True).select_related("usuario")
        return MiembroAreaOperativaSerializer(qs, many=True).data


class AreaCrearActualizarSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=120)
    color = serializers.CharField(max_length=16, required=False, default="#378ADD")
    departamento = serializers.UUIDField(required=False, allow_null=True)
    lider = serializers.UUIDField(required=False, allow_null=True)
    palabras_clave = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list,
    )
    miembros = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_null=True,
    )


class SeccionProyectoSerializer(BaseModelSerializer):
    class Meta:
        model = SeccionProyecto
        fields = [
            "id_seccion",
            "id_empresa",
            "proyecto",
            "nombre",
            "estado_destino",
            "orden",
            "activo",
        ]
        read_only_fields = ["id_seccion", "id_empresa", "activo"]


class ProyectoSerializer(BaseModelSerializer):
    secciones = serializers.SerializerMethodField()
    propietario_nombre = serializers.SerializerMethodField()
    area_nombre = serializers.CharField(source="area.nombre", read_only=True, default="")

    class Meta:
        model = Proyecto
        fields = [
            "id_proyecto",
            "id_empresa",
            "nombre",
            "descripcion",
            "color",
            "vista_predeterminada",
            "es_personal",
            "archivado",
            "area",
            "area_nombre",
            "propietario",
            "propietario_nombre",
            "secciones",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_proyecto",
            "id_empresa",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def get_secciones(self, obj: Proyecto) -> list[dict]:
        qs = obj.secciones.filter(activo=True).order_by("orden", "pk")
        return SeccionProyectoSerializer(qs, many=True).data

    def get_propietario_nombre(self, obj: Proyecto) -> str:
        if not obj.propietario_id or not obj.propietario:
            return ""
        return obj.propietario.get_full_name().strip() or obj.propietario.username


class ProyectoCrearSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=160)
    descripcion = serializers.CharField(required=False, allow_blank=True, default="")
    color = serializers.CharField(max_length=16, required=False, default="#1D9E75")
    vista_predeterminada = serializers.ChoiceField(
        choices=Proyecto.VistaPredeterminada.choices,
        required=False,
        default=Proyecto.VistaPredeterminada.TABLERO,
    )
    area = serializers.UUIDField(required=False, allow_null=True)
    propietario = serializers.UUIDField(required=False, allow_null=True)


class ComentarioTareaSerializer(BaseModelSerializer):
    class Meta:
        model = ComentarioTarea
        fields = [
            "id_comentario",
            "id_empresa",
            "tarea",
            "autor",
            "autor_nombre",
            "cuerpo",
            "es_sistema",
            "fecha_creacion",
        ]
        read_only_fields = [
            "id_comentario",
            "id_empresa",
            "tarea",
            "autor",
            "es_sistema",
            "fecha_creacion",
        ]


class DependenciaTareaSerializer(BaseModelSerializer):
    depende_de_titulo = serializers.CharField(source="depende_de.titulo", read_only=True)
    depende_de_estado = serializers.CharField(source="depende_de.estado", read_only=True)

    class Meta:
        model = DependenciaTarea
        fields = [
            "id_dependencia",
            "id_empresa",
            "tarea",
            "depende_de",
            "depende_de_titulo",
            "depende_de_estado",
            "activo",
            "fecha_creacion",
        ]
        read_only_fields = [
            "id_dependencia",
            "id_empresa",
            "tarea",
            "activo",
            "fecha_creacion",
        ]


class TareaSerializer(BaseModelSerializer):
    asignado_nombre = serializers.SerializerMethodField()
    proyecto_nombre = serializers.CharField(source="proyecto.nombre", read_only=True, default="")
    seccion_nombre = serializers.CharField(source="seccion.nombre", read_only=True, default="")
    area_nombre = serializers.CharField(source="area.nombre", read_only=True, default="")

    class Meta:
        model = Tarea
        fields = [
            "id_tarea",
            "id_empresa",
            "titulo",
            "descripcion",
            "estado",
            "prioridad",
            "origen",
            "proyecto",
            "proyecto_nombre",
            "seccion",
            "seccion_nombre",
            "area",
            "area_nombre",
            "tarea_padre",
            "asignado_a",
            "asignado_nombre",
            "creado_por",
            "fecha_inicio",
            "fecha_vencimiento",
            "hora_vencimiento",
            "completada_en",
            "bloqueada_por_escalacion",
            "motivo_bloqueo",
            "entidad_tipo",
            "entidad_id",
            "plantilla_recurrente",
            "minuta_origen",
            "idempotency_key",
            "orden_tablero",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_tarea",
            "id_empresa",
            "creado_por",
            "completada_en",
            "bloqueada_por_escalacion",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def get_asignado_nombre(self, obj: Tarea) -> str:
        if not obj.asignado_a_id or not obj.asignado_a:
            return ""
        return obj.asignado_a.get_full_name().strip() or obj.asignado_a.username


class TareaCrearSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=240)
    descripcion = serializers.CharField(required=False, allow_blank=True, default="")
    estado = serializers.ChoiceField(
        choices=EstadoTarea.choices, required=False, default=EstadoTarea.PENDIENTE
    )
    prioridad = serializers.ChoiceField(
        choices=PrioridadTarea.choices, required=False, default=PrioridadTarea.MEDIA
    )
    origen = serializers.ChoiceField(
        choices=Tarea.Origen.choices, required=False, default=Tarea.Origen.WEB
    )
    proyecto = serializers.UUIDField(required=False, allow_null=True)
    seccion = serializers.UUIDField(required=False, allow_null=True)
    area = serializers.UUIDField(required=False, allow_null=True)
    tarea_padre = serializers.UUIDField(required=False, allow_null=True)
    asignado_a = serializers.UUIDField(required=False, allow_null=True)
    fecha_inicio = serializers.DateField(required=False, allow_null=True)
    fecha_vencimiento = serializers.DateField(required=False, allow_null=True)
    hora_vencimiento = serializers.TimeField(required=False, allow_null=True)
    entidad_tipo = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    entidad_id = serializers.UUIDField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )
    usar_tablero_personal_si_falta = serializers.BooleanField(required=False, default=True)


class TareaEstadoInputSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=EstadoTarea.choices)
    motivo = serializers.CharField(max_length=280, required=False, allow_blank=True, default="")


class TareaMoverInputSerializer(serializers.Serializer):
    seccion = serializers.UUIDField()
    orden_tablero = serializers.IntegerField(min_value=0, required=False, allow_null=True)


class ComentarioInputSerializer(serializers.Serializer):
    cuerpo = serializers.CharField()
    autor_nombre = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )


class DependenciaInputSerializer(serializers.Serializer):
    depende_de = serializers.UUIDField()


class PlantillaTareaRecurrenteSerializer(BaseModelSerializer):
    asignado_nombre = serializers.SerializerMethodField()

    class Meta:
        model = PlantillaTareaRecurrente
        fields = [
            "id_plantilla_recurrente",
            "id_empresa",
            "titulo",
            "descripcion",
            "prioridad",
            "frecuencia",
            "dias_semana",
            "dia_mes",
            "horas_dia",
            "proxima_ejecucion",
            "ultima_generacion_en",
            "proyecto",
            "area",
            "asignado_a",
            "asignado_nombre",
            "creado_por",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_plantilla_recurrente",
            "id_empresa",
            "ultima_generacion_en",
            "creado_por",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def get_asignado_nombre(self, obj: PlantillaTareaRecurrente) -> str:
        if not obj.asignado_a_id or not obj.asignado_a:
            return ""
        return obj.asignado_a.get_full_name().strip() or obj.asignado_a.username


class MinutaItemPropuestoSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    task_name = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    descripcion = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    prioridad = serializers.ChoiceField(
        choices=PrioridadTarea.choices, required=False, default=PrioridadTarea.MEDIA
    )
    asignado_a_id = serializers.UUIDField(required=False, allow_null=True)
    asignado_nombre = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    assignee_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    area = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    area_id = serializers.UUIDField(required=False, allow_null=True)
    fecha_vencimiento = serializers.CharField(
        max_length=40, required=False, allow_blank=True, allow_null=True
    )
    due_on = serializers.CharField(
        max_length=40, required=False, allow_blank=True, allow_null=True
    )


class MinutaReunionSerializer(BaseModelSerializer):
    class Meta:
        model = MinutaReunion
        fields = [
            "id_minuta",
            "id_empresa",
            "titulo",
            "fecha_reunion",
            "texto_fuente",
            "documento_adjunto",
            "borrador_tareas",
            "estado",
            "creado_por",
            "confirmada_en",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_minuta",
            "id_empresa",
            "estado",
            "creado_por",
            "confirmada_en",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]


class MinutaCrearInputSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=200)
    fecha_reunion = serializers.DateField(required=False, allow_null=True)
    texto_fuente = serializers.CharField(required=False, allow_blank=True, default="")
    documento_adjunto = serializers.UUIDField(required=False, allow_null=True)
    items_propuestos = MinutaItemPropuestoSerializer(many=True, required=False, default=list)


class MinutaConfirmarInputSerializer(serializers.Serializer):
    proyecto = serializers.UUIDField(required=False, allow_null=True)
    items_confirmados = MinutaItemPropuestoSerializer(
        many=True, required=False, allow_null=True
    )


class ConfiguracionSeguimientoTareasSerializer(BaseModelSerializer):
    class Meta:
        model = ConfiguracionSeguimientoTareas
        fields = [
            "id_config_seguimiento",
            "id_empresa",
            "zona_horaria",
            "hora_recordatorio_manana",
            "hora_recordatorio_tarde",
            "hora_reporte_gerencial",
            "horas_bloqueo_vencida",
            "gerente",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_config_seguimiento",
            "id_empresa",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]


class RegistroAlertaTareaSerializer(BaseModelSerializer):
    tarea_titulo = serializers.CharField(source="tarea.titulo", read_only=True)

    class Meta:
        model = RegistroAlertaTarea
        fields = [
            "id_alerta_tarea",
            "id_empresa",
            "tarea",
            "tarea_titulo",
            "clave_alerta",
            "destinatario",
            "canal",
            "detalle",
            "fecha_creacion",
        ]
        read_only_fields = fields
