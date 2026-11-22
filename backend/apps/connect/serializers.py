"""Serializers para Omni Connect (públicos y autenticados)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rest_framework import serializers

from apps.core.models import Empresa, Usuarios

from .models import Perfil, Tarjeta
from .validators import normalizar_slug, normalizar_uid_chip


def _validar_sin_nul_dict(data: Any, campo: str = "error") -> None:
    if isinstance(data, Mapping):
        for key, val in data.items():
            if "\x00" in str(key):
                raise serializers.ValidationError({campo: "Parámetro inválido."})
            _validar_sin_nul_dict(val, str(key))
    elif isinstance(data, (list, tuple)):
        for item in data:
            _validar_sin_nul_dict(item, campo)
    elif isinstance(data, str) and "\x00" in data:
        raise serializers.ValidationError({campo: "El valor contiene caracteres inválidos."})


class ConnectBotonSerializer(serializers.Serializer):
    """Representación pública de un botón de acción del perfil."""

    tipo = serializers.CharField(read_only=True)
    etiqueta = serializers.CharField(read_only=True)
    valor = serializers.CharField(read_only=True)


class PublicPerfilSerializer(serializers.Serializer):
    """Proyección pública segura del perfil Connect (sin IDs internos ni notas)."""

    slug = serializers.CharField(read_only=True)
    nombre_publico = serializers.CharField(read_only=True)
    cargo = serializers.CharField(read_only=True)
    bio = serializers.CharField(read_only=True)
    telefono_publico = serializers.CharField(read_only=True)
    email_publico = serializers.CharField(read_only=True)
    tema = serializers.CharField(read_only=True)
    botones = ConnectBotonSerializer(many=True, read_only=True)
    empresa_nombre = serializers.CharField(read_only=True)
    acepta_leads = serializers.BooleanField(read_only=True)
    consentimiento_texto = serializers.CharField(read_only=True)


class PublicLeadCreateSerializer(serializers.Serializer):
    """Payload público de captura de lead con consentimiento obligatorio y honeypot."""

    nombre = serializers.CharField(max_length=150, required=True, allow_blank=False)
    apellido = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    empresa_nombre = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True, default="")
    telefono = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    mensaje = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    fuente = serializers.ChoiceField(
        choices=["NFC", "QR", "ENLACE"],
        required=False,
        allow_blank=True,
        default="",
    )
    origen = serializers.ChoiceField(
        choices=["NFC", "QR", "ENLACE"],
        required=False,
        allow_blank=True,
        default="",
    )
    uid = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    uid_chip = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    consentimiento_aceptado = serializers.BooleanField(required=True)
    consentimiento_texto = serializers.CharField(max_length=2000, required=True, allow_blank=False)
    website = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    company_url = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def to_internal_value(self, data: Any) -> Any:
        _validar_sin_nul_dict(data)
        return super().to_internal_value(data)

    def validate_consentimiento_aceptado(self, value: bool) -> bool:
        if value is not True:
            raise serializers.ValidationError("Debe aceptar el consentimiento para enviar sus datos.")
        return value

    def validate_consentimiento_texto(self, value: str) -> str:
        texto = (value or "").strip()
        if not texto:
            raise serializers.ValidationError("El texto de consentimiento no puede estar vacío.")
        return texto

    def validate_nombre(self, value: str) -> str:
        limpio = (value or "").strip()
        if not limpio:
            raise serializers.ValidationError("El nombre es obligatorio.")
        return limpio


class PublicLeadCreateResponseSerializer(serializers.Serializer):
    """Respuesta neutra de captura pública de lead."""

    ok = serializers.BooleanField(read_only=True)
    mensaje = serializers.CharField(read_only=True)


class _SlugNormalizerMixin:
    """Normaliza ``slug`` antes de ejecutar validadores de campo DRF."""

    def to_internal_value(self, data: Any) -> Any:
        _validar_sin_nul_dict(data)
        if isinstance(data, dict) and "slug" in data and isinstance(data["slug"], str):
            mutable = dict(data)
            mutable["slug"] = normalizar_slug(mutable["slug"])
            data = mutable
        return super().to_internal_value(data)  # type: ignore[misc]


class PerfilSerializer(_SlugNormalizerMixin, serializers.ModelSerializer):
    """Serializer CRUD multi-tenant para ``connect.Perfil`` (CTF-005 whitelist)."""

    id_empresa = serializers.PrimaryKeyRelatedField(queryset=Empresa.objects.all(), required=False)
    usuario = serializers.PrimaryKeyRelatedField(queryset=Usuarios.objects.all(), required=False)

    class Meta:
        model = Perfil
        fields = [
            "id_perfil",
            "id_empresa",
            "usuario",
            "slug",
            "nombre_publico",
            "cargo",
            "bio",
            "telefono_publico",
            "email_publico",
            "tema",
            "botones",
            "plantilla_bloqueada",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_perfil", "fecha_creacion", "fecha_actualizacion"]
        validators: list[Any] = []


class MiPerfilSerializer(_SlugNormalizerMixin, serializers.ModelSerializer):
    """Serializer del perfil propio (``/api/connect/perfiles/mi-perfil/``)."""

    class Meta:
        model = Perfil
        fields = [
            "id_perfil",
            "id_empresa",
            "usuario",
            "slug",
            "nombre_publico",
            "cargo",
            "bio",
            "telefono_publico",
            "email_publico",
            "tema",
            "botones",
            "plantilla_bloqueada",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_perfil",
            "id_empresa",
            "usuario",
            "fecha_creacion",
            "fecha_actualizacion",
        ]


class _UidNormalizerMixin:
    """Normaliza ``uid_chip`` antes de ejecutar validadores de campo DRF."""

    def to_internal_value(self, data: Any) -> Any:
        _validar_sin_nul_dict(data)
        if isinstance(data, Mapping) and "uid_chip" in data and isinstance(data["uid_chip"], str):
            mutable = dict(data)
            mutable["uid_chip"] = normalizar_uid_chip(mutable["uid_chip"])
            data = mutable
        return super().to_internal_value(data)  # type: ignore[misc]


class TarjetaSerializer(_UidNormalizerMixin, serializers.ModelSerializer):
    """Serializer CRUD multi-tenant para ``connect.Tarjeta`` (CTF-005 whitelist)."""

    id_empresa = serializers.PrimaryKeyRelatedField(queryset=Empresa.objects.all(), required=False)
    perfil = serializers.PrimaryKeyRelatedField(queryset=Perfil.objects.all(), required=False, allow_null=True)
    perfil_slug = serializers.CharField(source="perfil.slug", read_only=True, default=None)
    perfil_nombre = serializers.CharField(source="perfil.nombre_publico", read_only=True, default=None)

    class Meta:
        model = Tarjeta
        fields = [
            "id_tarjeta",
            "id_empresa",
            "perfil",
            "perfil_slug",
            "perfil_nombre",
            "uid_chip",
            "tipo",
            "estado",
            "fecha_activacion",
            "notas",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_tarjeta",
            "perfil_slug",
            "perfil_nombre",
            "fecha_activacion",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        validators: list[Any] = []


class TarjetaAsignarInputSerializer(serializers.Serializer):
    """Payload de asignación de tarjeta física a un ``Perfil`` del mismo tenant."""

    perfil_id = serializers.UUIDField(required=True)
    activar = serializers.BooleanField(required=False, default=False)

    def to_internal_value(self, data: Any) -> Any:
        _validar_sin_nul_dict(data)
        return super().to_internal_value(data)


class ConnectAnaliticasPeriodoSerializer(serializers.Serializer):
    """Rango de fechas evaluado en las analíticas Connect."""

    desde = serializers.DateField(read_only=True)
    hasta = serializers.DateField(read_only=True)
    dias = serializers.IntegerField(read_only=True)


class ConnectAnaliticasSerieDiaSerializer(serializers.Serializer):
    """Punto diario de toques y leads."""

    fecha = serializers.DateField(read_only=True)
    toques = serializers.IntegerField(read_only=True)
    leads = serializers.IntegerField(read_only=True)


class ConnectAnaliticasTopPerfilSerializer(serializers.Serializer):
    """Ranking de perfil público sin datos internos privados."""

    id_perfil = serializers.UUIDField(read_only=True)
    slug = serializers.CharField(read_only=True)
    nombre_publico = serializers.CharField(read_only=True)
    toques = serializers.IntegerField(read_only=True)
    visitantes_unicos = serializers.IntegerField(read_only=True)
    leads = serializers.IntegerField(read_only=True)
    leads_convertidos = serializers.IntegerField(read_only=True)
    tasa_conversion_pct = serializers.CharField(read_only=True)


class ConnectAnaliticasSerializer(serializers.Serializer):
    """Respuesta agregada de ``GET /api/connect/analiticas/``."""

    periodo = ConnectAnaliticasPeriodoSerializer(read_only=True)
    perfil_id = serializers.UUIDField(read_only=True, allow_null=True)
    total_toques = serializers.IntegerField(read_only=True)
    visitantes_unicos = serializers.IntegerField(read_only=True)
    total_leads = serializers.IntegerField(read_only=True)
    leads_convertidos = serializers.IntegerField(read_only=True)
    tasa_conversion_pct = serializers.CharField(read_only=True)
    tasa_cierre_pct = serializers.CharField(read_only=True)
    por_origen = serializers.DictField(child=serializers.IntegerField(), read_only=True)
    por_dispositivo = serializers.DictField(child=serializers.IntegerField(), read_only=True)
    serie_diaria = ConnectAnaliticasSerieDiaSerializer(many=True, read_only=True)
    top_perfiles = ConnectAnaliticasTopPerfilSerializer(many=True, read_only=True)
