from rest_framework import serializers

from apps.core.viewsets import get_empresa_primaria

from .models import (
    CalendarioActivacion,
    EventoActivacion,
    RecursoActivacion,
    UsoRecursoEvento,
)


class CalendarioActivacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalendarioActivacion
        fields = [
            "id_calendario",
            "id_empresa",
            "nombre",
            "google_calendar_id",
            "zona_horaria",
            "es_predeterminado",
            "activo",
        ]
        read_only_fields = ["id_empresa"]
        validators = []  # las constraints condicionales rompen el validador de DRF en PATCH; se validan abajo

    def validate(self, attrs):
        inst = self.instance
        nombre = attrs.get("nombre", getattr(inst, "nombre", None))
        empresa = getattr(inst, "id_empresa", None) or get_empresa_primaria(
            self.context["request"].user
        )
        dup = CalendarioActivacion.objects.filter(
            id_empresa=empresa, nombre=nombre, activo=True
        )
        if inst:
            dup = dup.exclude(pk=inst.pk)
        if dup.exists():
            raise serializers.ValidationError(
                {"nombre": "Ya existe un calendario activo con ese nombre."}
            )
        if attrs.get("es_predeterminado"):
            otros = CalendarioActivacion.objects.filter(
                id_empresa=empresa, es_predeterminado=True, activo=True
            )
            if inst:
                otros = otros.exclude(pk=inst.pk)
            otros.update(
                es_predeterminado=False
            )  # el nuevo predeterminado reemplaza al anterior
        return attrs


class RecursoActivacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecursoActivacion
        fields = [
            "id_recurso",
            "id_empresa",
            "calendario",
            "codigo",
            "nombre",
            "capacidad",
            "activo",
        ]
        read_only_fields = ["id_empresa"]
        validators = []

    def validate(self, attrs):
        inst = self.instance
        cal = attrs.get("calendario", getattr(inst, "calendario", None))
        codigo = attrs.get("codigo", getattr(inst, "codigo", None))
        dup = RecursoActivacion.objects.filter(
            calendario=cal, codigo=codigo, activo=True
        )
        if inst:
            dup = dup.exclude(pk=inst.pk)
        if dup.exists():
            raise serializers.ValidationError(
                {"codigo": "Ya existe ese recurso en el calendario."}
            )
        return attrs


class UsoRecursoEventoSerializer(serializers.ModelSerializer):
    recurso_codigo = serializers.CharField(source="recurso.codigo", read_only=True)

    class Meta:
        model = UsoRecursoEvento
        fields = ["recurso", "recurso_codigo", "cantidad"]


class EventoActivacionSerializer(serializers.ModelSerializer):
    usos = UsoRecursoEventoSerializer(many=True, read_only=True)

    class Meta:
        model = EventoActivacion
        fields = [
            "id_evento",
            "id_empresa",
            "calendario",
            "cliente",
            "cliente_nombre",
            "vendedor",
            "vendedor_nombre",
            "ubicacion",
            "inicio",
            "fin",
            "materiales",
            "notas",
            "estado",
            "origen",
            "google_event_id",
            "sync_error",
            "usos",
        ]
        read_only_fields = fields


class EventoCrearSerializer(serializers.Serializer):
    """Entrada de creación. ``usos`` es {codigo_recurso: cantidad}, p. ej. {"promotoras": 1, "igloos": 2}."""

    calendario = serializers.UUIDField(required=False)
    cliente = serializers.UUIDField(required=False, allow_null=True)
    cliente_nombre = serializers.CharField(max_length=255)
    vendedor_nombre = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    ubicacion = serializers.CharField(max_length=500)
    inicio = serializers.DateTimeField()
    fin = serializers.DateTimeField()
    materiales = serializers.ListField(
        child=serializers.CharField(max_length=120), required=False, default=list
    )
    notas = serializers.CharField(required=False, allow_blank=True, default="")
    usos = serializers.DictField(
        child=serializers.IntegerField(min_value=0), required=False, default=dict
    )
