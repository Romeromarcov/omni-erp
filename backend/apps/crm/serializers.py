"""Serializers del módulo CRM (maestro de clientes + pipeline/etapas/leads/actividades)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from drf_yasg.utils import swagger_serializer_method
from rest_framework import serializers

from apps.connect.models import Perfil, Tarjeta
from apps.core.models import Contacto, Empresa, Usuarios
from apps.core.validators import normalizar_email, normalizar_telefono
from apps.tareas.models import Tarea

from .models import Actividad, Cliente, ContactoCliente, DireccionCliente, Etapa, Lead, Pipeline
from .services import validar_sin_nul_recursivo


class _NulSafeSerializerMixin:
    """Rechaza bytes NUL recursivamente en payloads entrantes."""

    def to_internal_value(self, data: Any) -> Any:
        try:
            validar_sin_nul_recursivo(data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return super().to_internal_value(data)  # type: ignore[misc]


def _empresa_desde_contexto(serializer: serializers.BaseSerializer) -> Empresa | None:
    request = serializer.context.get("request") if hasattr(serializer, "context") else None
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    from apps.core.viewsets import get_empresa_primaria  # noqa: PLC0415

    return get_empresa_primaria(user)


def _nombre_usuario(usuario: Usuarios | None) -> str:
    if usuario is None:
        return ""
    nombre = f"{usuario.first_name} {usuario.last_name}".strip()
    return nombre or usuario.username


class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_cliente",
            "fecha_creacion",
            "fecha_actualizacion",
            "activo",
            "referencia_externa",
            "documento_json",
            "razon_social",
            "nombre_comercial",
            "rif",
            "direccion",
            "telefono",
            "email",
            "tipo_cliente",
            "limite_credito",
            "dias_credito",
            "dias_gracia_mora",
            "bloquear_por_mora",
            "id_empresa",
            "contacto",
        ]


class ContactoClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactoCliente
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_contacto",
            "fecha_creacion",
            "fecha_actualizacion",
            "activo",
            "nombre_contacto",
            "apellido_contacto",
            "cargo",
            "telefono_directo",
            "telefono_movil",
            "email_contacto",
            "fecha_nacimiento",
            "es_contacto_principal",
            "observaciones",
            "id_empresa",
            "id_cliente",
        ]


class DireccionClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = DireccionCliente
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_direccion",
            "fecha_creacion",
            "fecha_actualizacion",
            "activo",
            "tipo_direccion",
            "direccion_completa",
            "ciudad",
            "estado_provincia",
            "codigo_postal",
            "pais",
            "telefono",
            "persona_contacto",
            "es_direccion_principal",
            "observaciones",
            "latitud",
            "longitud",
            "gps_precision_m",
            "gps_capturado_en",
            "ventana_entrega_inicio",
            "ventana_entrega_fin",
            "referencia_gps",
            "id_empresa",
            "id_cliente",
        ]


# ── CRM ligero (Omni Connect S4): Pipeline, Etapa, Lead y Actividad ───────────


class EtapaSerializer(_NulSafeSerializerMixin, serializers.ModelSerializer):
    """Serializer multi-tenant para ``crm.Etapa``."""

    id_empresa = serializers.PrimaryKeyRelatedField(queryset=Empresa.objects.all(), required=False)
    pipeline = serializers.PrimaryKeyRelatedField(queryset=Pipeline.objects.all())

    class Meta:
        model = Etapa
        fields = [
            "id_etapa",
            "id_empresa",
            "pipeline",
            "nombre",
            "orden",
            "tipo",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_etapa", "fecha_creacion", "fecha_actualizacion"]
        validators: list[Any] = []

    def validate_nombre(self, value: str) -> str:
        limpio = (value or "").strip()
        if not limpio:
            raise serializers.ValidationError("El nombre de la etapa es obligatorio.")
        return limpio

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        inst = self.instance if isinstance(self.instance, Etapa) else None
        if inst is not None and "id_empresa" in attrs and attrs["id_empresa"].pk != inst.id_empresa_id:
            raise serializers.ValidationError({"id_empresa": "La empresa de la etapa es inmutable."})

        pipeline = attrs.get("pipeline") or (inst.pipeline if inst is not None else None)
        empresa = (
            inst.id_empresa
            if inst is not None
            else attrs.get("id_empresa")
            or (pipeline.id_empresa if pipeline is not None else None)
            or _empresa_desde_contexto(self)
        )
        if pipeline is not None and empresa is not None and pipeline.id_empresa_id != empresa.pk:
            raise serializers.ValidationError({"pipeline": "El pipeline no pertenece a la empresa."})
        return attrs


class PipelineSerializer(_NulSafeSerializerMixin, serializers.ModelSerializer):
    """Serializer multi-tenant para ``crm.Pipeline`` con etapas activas ordenadas."""

    id_empresa = serializers.PrimaryKeyRelatedField(queryset=Empresa.objects.all(), required=False)
    etapas = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Pipeline
        fields = [
            "id_pipeline",
            "id_empresa",
            "nombre",
            "es_predeterminado",
            "activo",
            "etapas",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_pipeline", "etapas", "fecha_creacion", "fecha_actualizacion"]
        validators: list[Any] = []

    @swagger_serializer_method(serializer_or_field=EtapaSerializer(many=True))
    def get_etapas(self, obj: Pipeline) -> list[Any]:
        prefetched = getattr(obj, "_prefetched_objects_cache", {})
        if "etapas" in prefetched:
            etapas = [e for e in obj.etapas.all() if e.activo]
            etapas.sort(key=lambda e: (e.orden, e.nombre))
        else:
            etapas = list(obj.etapas.filter(activo=True).order_by("orden", "nombre"))
        return list(EtapaSerializer(etapas, many=True).data)

    def validate_nombre(self, value: str) -> str:
        limpio = (value or "").strip()
        if not limpio:
            raise serializers.ValidationError("El nombre del pipeline es obligatorio.")
        return limpio

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        inst = self.instance if isinstance(self.instance, Pipeline) else None
        if inst is not None and "id_empresa" in attrs and attrs["id_empresa"].pk != inst.id_empresa_id:
            raise serializers.ValidationError({"id_empresa": "La empresa del pipeline es inmutable."})
        return attrs


class AsegurarPipelineInputSerializer(_NulSafeSerializerMixin, serializers.Serializer):
    """Payload opcional para inicializar el pipeline predeterminado de una empresa."""

    id_empresa = serializers.PrimaryKeyRelatedField(queryset=Empresa.objects.all(), required=False)


class ReordenarEtapasSerializer(_NulSafeSerializerMixin, serializers.Serializer):
    """Payload para reordenar etapas de un pipeline."""

    etapas = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)


class LeadSerializer(_NulSafeSerializerMixin, serializers.ModelSerializer):
    """Serializer multi-tenant para ``crm.Lead`` (CTF-005 whitelist + normalización)."""

    id_empresa = serializers.PrimaryKeyRelatedField(queryset=Empresa.objects.all(), required=False)
    pipeline = serializers.PrimaryKeyRelatedField(queryset=Pipeline.objects.all(), required=False)
    etapa = serializers.PrimaryKeyRelatedField(queryset=Etapa.objects.all(), required=False)
    propietario = serializers.PrimaryKeyRelatedField(queryset=Usuarios.objects.all(), required=False)
    tarjeta = serializers.PrimaryKeyRelatedField(queryset=Tarjeta.objects.all(), required=False, allow_null=True)
    perfil = serializers.PrimaryKeyRelatedField(queryset=Perfil.objects.all(), required=False, allow_null=True)
    contacto = serializers.PrimaryKeyRelatedField(queryset=Contacto.objects.all(), required=False, allow_null=True)

    pipeline_nombre = serializers.CharField(source="pipeline.nombre", read_only=True)
    etapa_nombre = serializers.CharField(source="etapa.nombre", read_only=True)
    etapa_tipo = serializers.CharField(source="etapa.tipo", read_only=True)
    propietario_nombre = serializers.SerializerMethodField(read_only=True)
    actividades_pendientes = serializers.SerializerMethodField(read_only=True)
    actividades_vencidas = serializers.SerializerMethodField(read_only=True)
    cliente_convertido_nombre = serializers.SerializerMethodField(read_only=True)
    cliente_convertido_rif = serializers.SerializerMethodField(read_only=True)
    ya_convertido = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Lead
        fields = [
            "id_lead",
            "id_empresa",
            "nombre",
            "apellido",
            "empresa_nombre",
            "email",
            "telefono",
            "email_normalizado",
            "telefono_normalizado",
            "mensaje",
            "fuente",
            "tarjeta",
            "perfil",
            "pipeline",
            "pipeline_nombre",
            "etapa",
            "etapa_nombre",
            "etapa_tipo",
            "propietario",
            "propietario_nombre",
            "contacto",
            "cliente_convertido",
            "cliente_convertido_nombre",
            "cliente_convertido_rif",
            "fecha_conversion",
            "cotizacion_convertida_id",
            "ya_convertido",
            "anonimizado",
            "fecha_anonimizacion",
            "consentimiento_aceptado",
            "consentimiento_fecha",
            "consentimiento_texto",
            "actividades_pendientes",
            "actividades_vencidas",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_lead",
            "email_normalizado",
            "telefono_normalizado",
            "pipeline_nombre",
            "etapa_nombre",
            "etapa_tipo",
            "propietario_nombre",
            "cliente_convertido",
            "cliente_convertido_nombre",
            "cliente_convertido_rif",
            "fecha_conversion",
            "cotizacion_convertida_id",
            "ya_convertido",
            "anonimizado",
            "fecha_anonimizacion",
            "actividades_pendientes",
            "actividades_vencidas",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    @swagger_serializer_method(serializer_or_field=serializers.CharField())
    def get_propietario_nombre(self, obj: Lead) -> str:
        return _nombre_usuario(obj.propietario)

    @swagger_serializer_method(serializer_or_field=serializers.IntegerField())
    def get_actividades_pendientes(self, obj: Lead) -> int:
        anotado = getattr(obj, "actividades_pendientes_count", None)
        if anotado is not None:
            return int(anotado)
        return obj.actividades.filter(activo=True, completada=False).count()

    @swagger_serializer_method(serializer_or_field=serializers.IntegerField())
    def get_actividades_vencidas(self, obj: Lead) -> int:
        anotado = getattr(obj, "actividades_vencidas_count", None)
        if anotado is not None:
            return int(anotado)
        return obj.actividades.filter(activo=True, completada=False, fecha_vencimiento__lt=timezone.now()).count()

    @swagger_serializer_method(serializer_or_field=serializers.CharField())
    def get_cliente_convertido_nombre(self, obj: Lead) -> str:
        return obj.cliente_convertido.razon_social if obj.cliente_convertido_id and obj.cliente_convertido else ""

    @swagger_serializer_method(serializer_or_field=serializers.CharField())
    def get_cliente_convertido_rif(self, obj: Lead) -> str:
        return obj.cliente_convertido.rif if obj.cliente_convertido_id and obj.cliente_convertido else ""

    @swagger_serializer_method(serializer_or_field=serializers.BooleanField())
    def get_ya_convertido(self, obj: Lead) -> bool:
        return bool(obj.cliente_convertido_id)

    def validate_nombre(self, value: str) -> str:
        limpio = (value or "").strip()
        if not limpio:
            raise serializers.ValidationError("El nombre del lead es obligatorio.")
        return limpio

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        inst = self.instance if isinstance(self.instance, Lead) else None
        if inst is not None and inst.anonimizado:
            raise serializers.ValidationError({"detail": "No se puede modificar un lead anonimizado."})
        if inst is not None and "id_empresa" in attrs and attrs["id_empresa"].pk != inst.id_empresa_id:
            raise serializers.ValidationError({"id_empresa": "La empresa del lead es inmutable."})

        empresa = inst.id_empresa if inst is not None else attrs.get("id_empresa") or _empresa_desde_contexto(self)

        if "pipeline" in attrs and attrs["pipeline"] is not None and not attrs["pipeline"].activo:
            raise serializers.ValidationError({"pipeline": "El pipeline seleccionado está inactivo."})
        if "etapa" in attrs and attrs["etapa"] is not None and not attrs["etapa"].activo:
            raise serializers.ValidationError({"etapa": "La etapa seleccionada está inactiva."})

        etapa = attrs.get("etapa") or (inst.etapa if inst is not None else None)
        pipeline = attrs.get("pipeline") or (inst.pipeline if inst is not None else None)
        if inst is None and pipeline is None and etapa is not None:
            pipeline = etapa.pipeline
            attrs["pipeline"] = pipeline

        if pipeline is not None and empresa is not None and pipeline.id_empresa_id != empresa.pk:
            raise serializers.ValidationError({"pipeline": "El pipeline no pertenece a la empresa del lead."})
        if etapa is not None:
            if empresa is not None and etapa.id_empresa_id != empresa.pk:
                raise serializers.ValidationError({"etapa": "La etapa no pertenece a la empresa del lead."})
            if pipeline is not None and etapa.pipeline_id != pipeline.pk:
                raise serializers.ValidationError({"etapa": "La etapa no pertenece al pipeline del lead."})

        propietario = attrs.get("propietario") or (inst.propietario if inst is not None else None)
        if propietario is not None and empresa is not None:
            if not propietario.empresas.filter(pk=empresa.pk).exists():
                raise serializers.ValidationError(
                    {"propietario": "El propietario no pertenece a la empresa del lead."}
                )

        tarjeta = attrs.get("tarjeta") if "tarjeta" in attrs else (inst.tarjeta if inst is not None else None)
        perfil = attrs.get("perfil") if "perfil" in attrs else (inst.perfil if inst is not None else None)
        contacto = attrs.get("contacto") if "contacto" in attrs else (inst.contacto if inst is not None else None)

        if empresa is not None:
            if tarjeta is not None and tarjeta.id_empresa_id != empresa.pk:
                raise serializers.ValidationError({"tarjeta": "La tarjeta pertenece a otra empresa."})
            if perfil is not None and perfil.id_empresa_id != empresa.pk:
                raise serializers.ValidationError({"perfil": "El perfil pertenece a otra empresa."})
            if contacto is not None and contacto.id_empresa_id != empresa.pk:
                raise serializers.ValidationError({"contacto": "El contacto pertenece a otra empresa."})

        if tarjeta is not None and perfil is not None and tarjeta.perfil_id != perfil.pk:
            raise serializers.ValidationError({"tarjeta": "La tarjeta no pertenece al perfil seleccionado."})

        fuente = attrs.get("fuente", inst.fuente if inst is not None else Lead.Fuente.MANUAL)
        consent_aceptado = attrs.get(
            "consentimiento_aceptado",
            inst.consentimiento_aceptado if inst is not None else False,
        )
        consent_texto = attrs.get(
            "consentimiento_texto",
            inst.consentimiento_texto if inst is not None else "",
        )
        consent_fecha = attrs.get(
            "consentimiento_fecha",
            inst.consentimiento_fecha if inst is not None else None,
        )

        if fuente not in (Lead.Fuente.MANUAL, Lead.Fuente.IMPORTACION) and not consent_aceptado:
            raise serializers.ValidationError(
                {"consentimiento_aceptado": "Los leads públicos requieren consentimiento aceptado."}
            )
        if consent_aceptado:
            if not (consent_texto or "").strip():
                raise serializers.ValidationError(
                    {"consentimiento_texto": "Debe indicar el texto legal de consentimiento."}
                )
            if consent_fecha is None:
                attrs["consentimiento_fecha"] = timezone.now()

        if inst is None or "email" in attrs:
            email_val = attrs.get("email", inst.email if inst is not None else "")
            attrs["email_normalizado"] = normalizar_email(email_val)
        if inst is None or "telefono" in attrs:
            tel_val = attrs.get("telefono", inst.telefono if inst is not None else "")
            attrs["telefono_normalizado"] = normalizar_telefono(tel_val)

        return attrs


class MoverEtapaSerializer(_NulSafeSerializerMixin, serializers.Serializer):
    """Payload para mover un lead a otra etapa dentro de su pipeline."""

    etapa = serializers.PrimaryKeyRelatedField(queryset=Etapa.objects.filter(activo=True), required=True)


class AnonimizarLeadInputSerializer(_NulSafeSerializerMixin, serializers.Serializer):
    """Payload opcional para anonimizar PII de un ``Lead`` (derecho al olvido)."""

    motivo = serializers.CharField(required=False, allow_blank=True, max_length=300)


class ConvertirLeadInputSerializer(_NulSafeSerializerMixin, serializers.Serializer):
    """Payload para convertir un ``Lead`` en ``crm.Cliente`` (+ ``Cotizacion`` opcional)."""

    razon_social = serializers.CharField(required=False, allow_blank=True, max_length=255)
    nombre_comercial = serializers.CharField(required=False, allow_blank=True, max_length=255)
    rif = serializers.CharField(required=False, allow_blank=True, max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True, max_length=254)
    telefono = serializers.CharField(required=False, allow_blank=True, max_length=50)
    direccion = serializers.CharField(required=False, allow_blank=True)
    tipo_cliente = serializers.ChoiceField(
        choices=[("CONTADO", "Contado"), ("CREDITO", "Crédito")],
        required=False,
        default="CONTADO",
    )
    limite_credito = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        default=Decimal("0"),
    )
    dias_credito = serializers.IntegerField(min_value=0, max_value=3650, required=False, default=0)
    reutilizar_cliente_existente = serializers.BooleanField(required=False, default=True)
    crear_cotizacion = serializers.BooleanField(required=False, default=False)
    id_moneda = serializers.UUIDField(required=False, allow_null=True)
    fecha_cotizacion = serializers.DateField(required=False, allow_null=True)
    fecha_vencimiento = serializers.DateField(required=False, allow_null=True)
    observaciones_cotizacion = serializers.CharField(required=False, allow_blank=True)


class ConvertirLeadResponseSerializer(serializers.Serializer):
    """Respuesta estructurada de ``POST /api/crm/leads/{id}/convertir-cliente/``."""

    ya_convertido = serializers.BooleanField()
    lead = LeadSerializer()
    cliente = ClienteSerializer()
    cotizacion_id = serializers.UUIDField(allow_null=True)
    numero_cotizacion = serializers.CharField(allow_null=True)


class ActividadSerializer(_NulSafeSerializerMixin, serializers.ModelSerializer):
    """Serializer multi-tenant para ``crm.Actividad`` (CTF-005 whitelist)."""

    id_empresa = serializers.PrimaryKeyRelatedField(queryset=Empresa.objects.all(), required=False)
    lead = serializers.PrimaryKeyRelatedField(queryset=Lead.objects.all())
    asignado_a = serializers.PrimaryKeyRelatedField(
        queryset=Usuarios.objects.all(),
        required=False,
        allow_null=True,
    )
    creado_por: serializers.PrimaryKeyRelatedField[Any] = serializers.PrimaryKeyRelatedField(read_only=True)
    tarea = serializers.PrimaryKeyRelatedField(
        queryset=Tarea.objects.all(),
        required=False,
        allow_null=True,
    )

    lead_nombre = serializers.SerializerMethodField(read_only=True)
    asignado_a_nombre = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Actividad
        fields = [
            "id_actividad",
            "id_empresa",
            "lead",
            "lead_nombre",
            "tipo",
            "asunto",
            "descripcion",
            "fecha_vencimiento",
            "completada",
            "fecha_completada",
            "asignado_a",
            "asignado_a_nombre",
            "creado_por",
            "tarea",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_actividad",
            "lead_nombre",
            "asignado_a_nombre",
            "creado_por",
            "fecha_completada",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    @swagger_serializer_method(serializer_or_field=serializers.CharField())
    def get_lead_nombre(self, obj: Actividad) -> str:
        return str(obj.lead) if obj.lead_id else ""

    @swagger_serializer_method(serializer_or_field=serializers.CharField())
    def get_asignado_a_nombre(self, obj: Actividad) -> str:
        return _nombre_usuario(obj.asignado_a)

    def validate_asunto(self, value: str) -> str:
        limpio = (value or "").strip()
        if not limpio:
            raise serializers.ValidationError("El asunto de la actividad es obligatorio.")
        return limpio

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        inst = self.instance if isinstance(self.instance, Actividad) else None
        if inst is not None and "id_empresa" in attrs and attrs["id_empresa"].pk != inst.id_empresa_id:
            raise serializers.ValidationError({"id_empresa": "La empresa de la actividad es inmutable."})

        lead = attrs.get("lead") or (inst.lead if inst is not None else None)
        if "lead" in attrs and attrs["lead"] is not None and not attrs["lead"].activo:
            raise serializers.ValidationError({"lead": "El lead seleccionado está inactivo."})
        empresa = (
            inst.id_empresa
            if inst is not None
            else attrs.get("id_empresa")
            or (lead.id_empresa if lead is not None else None)
            or _empresa_desde_contexto(self)
        )

        if lead is not None and empresa is not None and lead.id_empresa_id != empresa.pk:
            raise serializers.ValidationError({"lead": "El lead pertenece a otra empresa."})

        tarea = attrs.get("tarea") if "tarea" in attrs else (inst.tarea if inst is not None else None)
        if tarea is not None and empresa is not None and tarea.id_empresa_id != empresa.pk:
            raise serializers.ValidationError({"tarea": "La tarea vinculada pertenece a otra empresa."})

        asignado_a = (
            attrs.get("asignado_a") if "asignado_a" in attrs else (inst.asignado_a if inst is not None else None)
        )
        if (
            asignado_a is not None
            and empresa is not None
            and not (getattr(asignado_a, "es_superusuario_omni", False) or getattr(asignado_a, "is_superuser", False))
            and not asignado_a.empresas.filter(pk=empresa.pk).exists()
        ):
            raise serializers.ValidationError({"asignado_a": "El usuario asignado no pertenece a esta empresa."})

        return attrs


class CompletarActividadSerializer(_NulSafeSerializerMixin, serializers.Serializer):
    """Payload para completar o reabrir una ``Actividad``."""

    completada = serializers.BooleanField(required=False, default=True)
    descripcion = serializers.CharField(required=False, allow_blank=True)
