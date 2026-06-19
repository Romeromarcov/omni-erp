# apps/core/serializers.py
from rest_framework import serializers


class BaseModelSerializer(serializers.ModelSerializer):
    """Serializer base para lógica común y validaciones reutilizables."""

    def validate(self, data):
        # Lógica de validación global aquí si aplica
        return super().validate(data)


from .models import (
    Departamento,
    Dispositivo,
    Empresa,
    Permisos,
    RegistroAuditoria,
    Roles,
    RolPermisos,
    Sucursal,
    UsuarioRoles,
    Usuarios,
)


class EmpresaSerializer(BaseModelSerializer):
    def validate(self, data):
        # Validación: la moneda país debe coincidir con el país de la empresa y el país de la moneda
        id_moneda_pais = data.get("id_moneda_pais", getattr(self.instance, "id_moneda_pais", None))
        pais_empresa = data.get("pais_codigo_iso", getattr(self.instance, "pais_codigo_iso", None))
        if id_moneda_pais and pais_empresa:
            from apps.finanzas.models import Moneda

            try:
                moneda = Moneda.objects.get(
                    id_moneda=id_moneda_pais.id_moneda if hasattr(id_moneda_pais, "id_moneda") else id_moneda_pais
                )
                if moneda.pais_codigo_iso != pais_empresa:
                    raise serializers.ValidationError(
                        {
                            "id_moneda_pais": f"La moneda seleccionada ({moneda.codigo_iso}) no corresponde al país de la empresa ({pais_empresa})."
                        }
                    )
            except Moneda.DoesNotExist:
                raise serializers.ValidationError({"id_moneda_pais": "La moneda país seleccionada no existe."})
        return super().validate(data)

    id_moneda_pais = serializers.UUIDField(source="id_moneda_pais.id_moneda", read_only=True)
    moneda_pais_codigo_iso = serializers.CharField(source="id_moneda_pais.codigo_iso", read_only=True)
    moneda_pais_nombre = serializers.CharField(source="id_moneda_pais.nombre", read_only=True)

    class Meta:
        model = Empresa
        # SEC-NEW-6: ocultar campos internos de integración del API.
        exclude = ("referencia_externa", "documento_json")
        extra_fields = ["id_moneda_pais", "moneda_pais_codigo_iso", "moneda_pais_nombre"]


class SucursalSerializer(BaseModelSerializer):
    id_sucursal = serializers.UUIDField(read_only=True)
    id_empresa = serializers.UUIDField(source="id_empresa.id_empresa")

    class Meta:
        model = Sucursal
        fields = [
            "id_sucursal",
            "id_empresa",
            "nombre",
            "codigo_sucursal",
            "direccion",
            "telefono",
            "email_contacto",
            "ubicacion_gps_json",
            "activo",
            "fecha_creacion",
            "referencia_externa",
            "documento_json",
        ]

    def create(self, validated_data):
        # Extraer el UUID de empresa correctamente
        empresa_id = validated_data.pop("id_empresa", None)
        if isinstance(empresa_id, dict):
            empresa_id = empresa_id.get("id_empresa")
        from .models import Empresa

        empresa = Empresa.objects.get(id_empresa=empresa_id)
        sucursal = Sucursal.objects.create(id_empresa=empresa, **validated_data)
        return sucursal


class DepartamentoSerializer(BaseModelSerializer):
    class Meta:
        model = Departamento
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_departamento",
            "nombre_departamento",
            "descripcion",
            "departamento_general",
            "id_empresa",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
            "referencia_externa",
            "documento_json",
        ]


class UsuariosSerializer(BaseModelSerializer):
    empresas = EmpresaSerializer(many=True, read_only=True)
    sucursales = SucursalSerializer(many=True, read_only=True)
    departamentos = serializers.PrimaryKeyRelatedField(queryset=Departamento.objects.all(), many=True, required=False)
    roles = serializers.SerializerMethodField()
    es_superusuario_omni = serializers.BooleanField(required=False)

    def get_roles(self, obj):
        from .models import UsuarioRoles

        roles_qs = UsuarioRoles.objects.filter(id_usuario=obj)
        return [
            {"id": str(ur.id_rol.id_rol), "name": ur.id_rol.nombre_rol} for ur in roles_qs.select_related("id_rol")
        ]

    def update(self, instance, validated_data):
        user = self.context["request"].user if "request" in self.context else None
        # Solo superusuarios Innova pueden modificar este campo
        if "es_superusuario_omni" in validated_data:
            if not user or not getattr(user, "es_superusuario_omni", False):
                validated_data.pop("es_superusuario_omni")
        return super().update(instance, validated_data)

    def create(self, validated_data):
        user = self.context["request"].user if "request" in self.context else None
        # Solo superusuarios Innova pueden asignar este campo
        if "es_superusuario_omni" in validated_data:
            if not user or not getattr(user, "es_superusuario_omni", False):
                validated_data.pop("es_superusuario_omni")
        return super().create(validated_data)

    class Meta:
        model = Usuarios
        # H-API-3: whitelist explícita. NUNCA exponer ni aceptar desde el cliente
        # is_superuser, is_staff, last_login, groups ni user_permissions (escalación
        # de privilegios). El hash de password es write_only.
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "password",
            "empresas",
            "sucursales",
            "departamentos",
            "roles",
            "es_superusuario_omni",
            "id_sucursal_predeterminada",
            "fecha_ultimo_login",
            "date_joined",
            "referencia_externa",
            "documento_json",
        ]
        read_only_fields = ["id", "fecha_ultimo_login", "date_joined", "roles"]
        extra_kwargs = {
            "password": {"write_only": True},  # S#6 — never expose hash in responses
        }


class RolesSerializer(BaseModelSerializer):
    class Meta:
        model = Roles
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_rol",
            "nombre_rol",
            "descripcion",
            "id_empresa",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
            "referencia_externa",
            "documento_json",
        ]


class PermisosSerializer(BaseModelSerializer):
    class Meta:
        model = Permisos
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_permiso",
            "codigo_permiso",
            "nombre_permiso",
            "descripcion",
            "modulo",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
            "referencia_externa",
            "documento_json",
        ]


class RolPermisosSerializer(BaseModelSerializer):
    # Para mostrar el nombre del rol y el permiso en lugar de solo los IDs
    id_rol_nombre = serializers.CharField(source="id_rol.nombre_rol", read_only=True)
    id_permiso_nombre = serializers.CharField(source="id_permiso.nombre_permiso", read_only=True)

    class Meta:
        model = RolPermisos
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_rol_permiso",
            "id_rol",
            "id_permiso",
            "id_rol_nombre",
            "id_permiso_nombre",
            "fecha_asignacion",
        ]


class UsuarioRolesSerializer(serializers.ModelSerializer):
    # Para mostrar el nombre de usuario y el nombre del rol
    id_usuario_username = serializers.CharField(source="id_usuario.username", read_only=True)
    id_rol_nombre = serializers.CharField(source="id_rol.nombre_rol", read_only=True)

    class Meta:
        model = UsuarioRoles
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_usuario_rol",
            "id_usuario",
            "id_rol",
            "id_usuario_username",
            "id_rol_nombre",
            "fecha_asignacion",
        ]


class RegistroAuditoriaSerializer(serializers.ModelSerializer):
    # Para mostrar el nombre de usuario que realizó la acción
    id_usuario_username = serializers.CharField(source="id_usuario.username", read_only=True)

    class Meta:
        model = RegistroAuditoria
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_log_auditoria",
            "tipo_evento",
            "modulo_afectado",
            "nombre_modelo_afectado",
            "id_registro_afectado",
            "descripcion_accion",
            "cambios_json",
            "fecha_hora_accion",
            "direccion_ip",
            "navegador_info",
            "resultado_evento",
            "mensaje_error",
            "id_empresa",
            "id_usuario",
            "id_usuario_username",
        ]
        read_only_fields = ("fecha_accion",)  # La fecha de acción se genera automáticamente


class DispositivoSerializer(BaseModelSerializer):
    """
    Serializer para el modelo Dispositivo.
    """

    # Campos relacionados
    empresa_nombre = serializers.CharField(source="empresa.nombre_comercial", read_only=True)
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", read_only=True)
    creado_por_username = serializers.CharField(source="creado_por.username", read_only=True)

    # Información de caja física asociada (si existe)
    caja_fisica_id = serializers.UUIDField(source="caja_fisica.id_caja_fisica", read_only=True)
    caja_fisica_nombre = serializers.CharField(source="caja_fisica.nombre", read_only=True)

    class Meta:
        model = Dispositivo
        fields = [
            "id_dispositivo",
            "fingerprint",
            "user_agent",
            "ip_address",
            "nombre_dispositivo",
            "caja_fisica",
            "empresa",
            "sucursal",
            "creado_por",
            "preguntar_crear_caja",
            "ultima_pregunta_caja",
            "activo",
            "fecha_registro",
            "ultimo_login",
            # Campos relacionados
            "empresa_nombre",
            "sucursal_nombre",
            "creado_por_username",
            "caja_fisica_id",
            "caja_fisica_nombre",
        ]
        read_only_fields = ["id_dispositivo", "fecha_registro", "ultimo_login"]

    def create(self, validated_data):
        # Asegurar que el usuario que crea es el que está autenticado
        request = self.context.get("request")
        if request and request.user:
            validated_data["creado_por"] = request.user
        return super().create(validated_data)


# ── Contacto ──────────────────────────────────────────────────────────────────

from .models import ConfiguracionFlujoDocumentos, Contacto  # noqa: E402


class ConfiguracionFlujoDocumentosSerializer(BaseModelSerializer):
    class Meta:
        model = ConfiguracionFlujoDocumentos
        fields = [
            "id_configuracion",
            "id_empresa",
            "tipo_documento",
            "paso",
            "obligatorio",
            "orden",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ["id_configuracion", "id_empresa", "fecha_creacion", "fecha_actualizacion"]


class ContactoSerializer(BaseModelSerializer):
    nombre_completo = serializers.ReadOnlyField()

    class Meta:
        model = Contacto
        fields = [
            "id_contacto", "id_empresa", "tipo_persona",
            "nombre", "apellido", "nombre_comercial", "nombre_completo",
            "rif", "cedula", "email", "telefono", "direccion_fiscal",
            "es_cliente", "es_proveedor", "es_empleado", "es_usuario",
            "tipo_credito", "limite_credito", "dias_credito", "lista_precio",
            "dias_pago", "usuario", "activo", "fecha_creacion",
        ]
        read_only_fields = ["id_contacto", "id_empresa", "fecha_creacion"]


from .models import Notificacion  # noqa: E402


class NotificacionSerializer(BaseModelSerializer):
    class Meta:
        model = Notificacion
        # CTF-005: whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_notificacion",
            "tipo",
            "titulo",
            "mensaje",
            "leida",
            "fecha_lectura",
            "url_accion",
            "metadata",
            "fecha_creacion",
            "fecha_expiracion",
            "id_empresa",
            "id_usuario",
        ]
        read_only_fields = ["id_notificacion", "fecha_creacion"]
        ref_name = "NotificacionCore"  # evita colisión OpenAPI con notificaciones.NotificacionSerializer
