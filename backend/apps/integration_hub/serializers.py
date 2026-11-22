"""
Serializers del Integration Hub.
"""

from rest_framework import serializers

from apps.core.models import Empresa

from .models import (
    ConectorInstancia,
    ConectorProveedor,
    EntidadSincronizada,
    EventoOutbox,
    JobSincronizacion,
    LogDetalleSincronizacion,
)


class ConectorProveedorSerializer(serializers.ModelSerializer):
    """Catálogo de proveedores.

    Lectura: cualquier usuario autenticado. Escritura: solo superusuario Omni
    (SaaS owner) — el gate vive en el ViewSet (SuperuserWriteMixin), no aquí.
    """

    class Meta:
        model = ConectorProveedor
        fields = [
            "id_proveedor",
            "codigo",
            "nombre",
            "descripcion",
            "icono_url",
            "versiones_soportadas",
            "capacidades",
            "requiere_url",
            "requiere_db",
            "estado",
            "activo",
            "orden",
        ]
        read_only_fields = ["id_proveedor"]

    def validate_codigo(self, value: str) -> str:
        """El código es un slug (identifica al conector en el registry)."""
        import re

        slug = (value or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9_]+", slug):
            raise serializers.ValidationError(
                "El código solo admite minúsculas, números y guion bajo "
                "(ej: 'odoo', 'google_sheets'). Debe coincidir con el conector."
            )
        return slug

    def validate_capacidades(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Capacidades debe ser una lista.")
        return value

    def validate_versiones_soportadas(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Versiones soportadas debe ser una lista.")
        return value


class ConectorInstanciaSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(source="id_proveedor.nombre", read_only=True)
    proveedor_codigo = serializers.CharField(source="id_proveedor.codigo", read_only=True)
    proveedor_capacidades = serializers.JSONField(source="id_proveedor.capacidades", read_only=True)
    # Nunca serializar configuracion completa — R-CODE-8
    # Solo mostrar campos seguros (host, user) sin api_key ni password
    configuracion_publica = serializers.SerializerMethodField()

    class Meta:
        model = ConectorInstancia
        fields = [
            "id_conector",
            "id_empresa",
            "id_proveedor",
            "proveedor_nombre",
            "proveedor_codigo",
            "proveedor_capacidades",
            "nombre",
            "configuracion_publica",
            "estado",
            "mensaje_estado",
            "ultimo_test_conexion",
            "ultimo_sync",
            "intervalo_sync_minutos",
            "entidades_activas",
            "version_detectada",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = [
            "id_conector",
            "id_empresa",
            "proveedor_nombre",
            "proveedor_codigo",
            "proveedor_capacidades",
            "configuracion_publica",
            "estado",
            "mensaje_estado",
            "ultimo_test_conexion",
            "ultimo_sync",
            "version_detectada",
            "fecha_creacion",
            "fecha_actualizacion",
        ]

    def get_configuracion_publica(self, obj) -> dict:
        """Retorna solo campos seguros de configuracion (sin secretos — R-CODE-8)."""
        cfg = obj.get_config()
        diario_default = cfg.get("diario_pagos_default_id")
        pub = {
            "host": cfg.get("host", ""),
            "db": cfg.get("db", ""),
            "user": cfg.get("user", ""),
            "timeout": cfg.get("timeout", 30),
            "push_habilitado": bool(cfg.get("push_habilitado", False)),
            "push_modo_pago": cfg.get("push_modo_pago") or "borrador",
            "write_user": cfg.get("write_user", "") or "",
            "tiene_write_api_key": bool(str(cfg.get("write_api_key") or "").strip()),
            "diario_pagos_default_id": diario_default if diario_default not in ("", None) else None,
            # api_key, write_api_key, password, service_account: nunca (R-CODE-8)
        }
        if "empujar_connect_leads" in cfg:
            pub["empujar_connect_leads"] = cfg.get("empujar_connect_leads") is True
        return pub


class ConectorInstanciaCreateSerializer(serializers.ModelSerializer):
    """Serializer de creación/edición que acepta configuracion completa."""

    # Claves secretas que nunca se devuelven al cliente (R-CODE-8). Al editar, si
    # llegan vacías se conserva el valor cifrado existente (no se sobreescriben).
    SECRET_KEYS = ("api_key", "write_api_key", "password", "service_account")

    id_empresa = serializers.PrimaryKeyRelatedField(
        queryset=Empresa.objects.filter(activo=True),
        required=False,
    )

    class Meta:
        model = ConectorInstancia
        # La unicidad (id_empresa, nombre) se valida explícitamente en validate_nombre
        # para permitir omitir id_empresa en creación (resuelto vía request/perform_create).
        validators = []
        extra_kwargs = {
            "configuracion": {"write_only": True},
        }
        fields = [
            "id_empresa",
            "id_proveedor",
            "nombre",
            "configuracion",
            "intervalo_sync_minutos",
            "entidades_activas",
            "activo",
        ]

    def to_representation(self, instance):
        """Devuelve siempre la representación pública segura sin secretos tras POST/PUT/PATCH (R-CODE-8)."""
        return ConectorInstanciaSerializer(instance, context=self.context).data

    def validate_id_empresa(self, value):
        """Mantiene id_empresa inmutable en PATCH/PUT y valida alcance Matriz→Subsidiaria en alta."""
        if getattr(self, "instance", None) is not None:
            if value is not None and value.pk != self.instance.id_empresa_id:
                raise serializers.ValidationError("id_empresa es inmutable y no puede modificarse.")
            return value

        if value is not None:
            request = self.context.get("request")
            user = getattr(request, "user", None) if request is not None else None
            if user is not None and getattr(user, "is_authenticated", False):
                from apps.core.viewsets import get_empresas_visible

                if not get_empresas_visible(user).filter(pk=value.pk).exists():
                    raise serializers.ValidationError(
                        "No tiene permisos para configurar conectores en la empresa indicada."
                    )
        return value

    def validate_configuracion(self, value: dict) -> dict:
        """Valida que la configuracion sea un objeto JSON."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("La configuración debe ser un objeto JSON.")
        return value

    def validate(self, attrs: dict) -> dict:
        """Valida los campos mínimos de configuracion según el proveedor y parámetros outbound."""
        configuracion = attrs.get("configuracion")
        if configuracion is None:
            return attrs  # PATCH parcial sin configuracion: nada que validar

        instancia = getattr(self, "instance", None)
        proveedor = attrs.get("id_proveedor") or (instancia.id_proveedor if instancia else None)
        codigo = getattr(proveedor, "codigo", "")

        # En edición, un campo secreto que llega vacío se conserva del valor
        # existente (el cliente nunca recibe la api_key/write_api_key). Por eso,
        # para validar "campo presente", consideramos tanto lo entrante como lo guardado.
        existente = instancia.get_config() if instancia is not None else {}

        def _tiene_valor(val) -> bool:
            return bool(val.strip()) if isinstance(val, str) else bool(val)

        def presente(campo: str) -> bool:
            if campo in configuracion:
                if _tiene_valor(configuracion.get(campo)):
                    return True
                # En edición, las claves secretas omitidas o vacías conservan el valor previo;
                # en campos no secretos (host, user) los espacios en blanco se rechazan.
                if campo in self.SECRET_KEYS:
                    return _tiene_valor(existente.get(campo))
                return False
            return _tiene_valor(existente.get(campo))

        if codigo == "google_sheets":
            sa = configuracion.get("service_account")
            sa_ok = isinstance(sa, dict) and sa.get("client_email")
            # En edición se admite conservar la cuenta de servicio ya guardada.
            if not sa_ok and not existente.get("service_account"):
                raise serializers.ValidationError(
                    {
                        "configuracion": (
                            "Se requiere 'service_account' (JSON de la cuenta de "
                            "servicio de Google, con 'client_email')."
                        )
                    }
                )
            if not presente("source_instancia_id"):
                raise serializers.ValidationError(
                    {
                        "configuracion": (
                            "Se requiere 'source_instancia_id' (instancia origen "
                            "de la que exportar, p. ej. el conector Odoo)."
                        )
                    }
                )
        else:
            for campo in ("host", "user", "api_key"):
                if not presente(campo):
                    raise serializers.ValidationError({"configuracion": f"Se requiere el campo '{campo}'."})

        # Fail-closed: simetría estricta entre write_user y write_api_key.
        if "write_user" in configuracion:
            write_user_final = str(configuracion.get("write_user") or "").strip()
        else:
            write_user_final = str(existente.get("write_user") or "").strip()

        raw_write_key = configuracion.get("write_api_key")
        if raw_write_key is not None and str(raw_write_key).strip():
            write_key_final = str(raw_write_key).strip()
        else:
            write_key_final = str(existente.get("write_api_key") or "").strip()

        if bool(write_user_final) != bool(write_key_final):
            raise serializers.ValidationError(
                {
                    "configuracion": (
                        "Configuración de escritura asimétrica: 'write_user' y 'write_api_key' "
                        "deben configurarse juntos."
                    )
                }
            )

        if "push_modo_pago" in configuracion and configuracion.get("push_modo_pago") not in (
            "borrador",
            "confirmado",
        ):
            raise serializers.ValidationError({"configuracion": "push_modo_pago debe ser 'borrador' o 'confirmado'."})

        if "push_habilitado" in configuracion and not isinstance(configuracion.get("push_habilitado"), bool):
            raise serializers.ValidationError({"configuracion": "push_habilitado debe ser un valor booleano."})

        if "empujar_connect_leads" in configuracion and not isinstance(
            configuracion.get("empujar_connect_leads"), bool
        ):
            raise serializers.ValidationError({"configuracion": "empujar_connect_leads debe ser un valor booleano."})

        if "empujar_connect_leads" in configuracion:
            empujar_connect_leads_final = configuracion.get("empujar_connect_leads")
        else:
            empujar_connect_leads_final = existente.get("empujar_connect_leads", False)

        if empujar_connect_leads_final is True and (not write_user_final or not write_key_final):
            raise serializers.ValidationError(
                {
                    "configuracion": (
                        "Activar 'empujar_connect_leads' requiere configurar 'write_user' y 'write_api_key'."
                    )
                }
            )

        if "mapa_etapas_odoo" in configuracion and configuracion.get("mapa_etapas_odoo") is not None:
            if not isinstance(configuracion.get("mapa_etapas_odoo"), dict):
                raise serializers.ValidationError({"configuracion": "mapa_etapas_odoo debe ser un objeto JSON."})

        if "diario_pagos_default_id" in configuracion:
            diario_val = configuracion.get("diario_pagos_default_id")
            if diario_val not in (None, ""):
                if isinstance(diario_val, bool):
                    raise serializers.ValidationError(
                        {"configuracion": "diario_pagos_default_id debe ser un entero positivo."}
                    )
                try:
                    diario_int = int(diario_val)
                except (TypeError, ValueError) as exc:
                    raise serializers.ValidationError(
                        {"configuracion": "diario_pagos_default_id debe ser un entero positivo."}
                    ) from exc
                if diario_int <= 0:
                    raise serializers.ValidationError(
                        {"configuracion": "diario_pagos_default_id debe ser mayor que cero."}
                    )

        return attrs

    def update(self, instance, validated_data):
        """Edición: fusiona la configuración nueva sobre la existente sin perder
        secretos (api_key, write_api_key, etc.) cuando llegan vacíos, y no permite
        cambiar el proveedor ni la empresa de una instancia ya creada."""
        validated_data.pop("id_proveedor", None)  # el proveedor es inmutable
        validated_data.pop("id_empresa", None)  # la empresa es inmutable

        nueva_config = validated_data.pop("configuracion", None)
        if nueva_config is not None:
            config = dict(instance.get_config())
            for clave, valor in nueva_config.items():
                # No sobreescribir un secreto con vacío: permite editar el resto
                # de campos sin re-tipear la credencial.
                vacio = not valor or (isinstance(valor, str) and not valor.strip())
                if clave in self.SECRET_KEYS and vacio:
                    continue
                config[clave] = valor
            instance.configuracion = config

        return super().update(instance, validated_data)

    def validate_nombre(self, value: str) -> str:
        """El nombre debe ser único por empresa."""
        # SEC-NEW-2: empresa vía el helper vetado get_empresas_visible.
        from apps.core.viewsets import get_empresas_visible

        instancia = getattr(self, "instance", None)
        if instancia is not None:
            empresa = instancia.id_empresa
        else:
            request = self.context.get("request") if hasattr(self, "context") else None
            user = getattr(request, "user", None) if request is not None else None
            if user is None or not getattr(user, "is_authenticated", False):
                return value
            visibles = get_empresas_visible(user)
            emp_id = self.initial_data.get("id_empresa") if hasattr(self, "initial_data") else None
            try:
                empresa = visibles.filter(pk=emp_id).first() if emp_id else None
            except (ValueError, TypeError):
                empresa = None
            if empresa is None:
                empresa = visibles.first()

        qs = ConectorInstancia.objects.filter(id_empresa=empresa, nombre=value)
        if instancia is not None:
            qs = qs.exclude(pk=instancia.pk)
        if qs.exists():
            raise serializers.ValidationError(f"Ya existe un conector con el nombre '{value}' en esta empresa.")
        return value


class JobSincronizacionSerializer(serializers.ModelSerializer):
    instancia_nombre = serializers.CharField(source="id_instancia.nombre", read_only=True)
    duracion_segundos = serializers.FloatField(read_only=True)
    iniciado_por_nombre = serializers.SerializerMethodField()

    class Meta:
        model = JobSincronizacion
        fields = [
            "id_job",
            "id_instancia",
            "instancia_nombre",
            "tipo_entidad",
            "direccion",
            "estado",
            "total_registros",
            "procesados",
            "creados",
            "actualizados",
            "omitidos",
            "fallidos",
            "resumen_errores",
            "iniciado_en",
            "completado_en",
            "duracion_segundos",
            "iniciado_por",
            "iniciado_por_nombre",
            "parametros",
        ]
        read_only_fields = [f for f in fields if f not in ("tipo_entidad", "direccion", "parametros")]

    def get_iniciado_por_nombre(self, obj) -> str:
        if obj.iniciado_por:
            return getattr(obj.iniciado_por, "get_full_name", lambda: "")() or str(obj.iniciado_por)
        return "Automático"


class JobSincronizacionTriggerSerializer(serializers.Serializer):
    """Serializer para disparar un job manualmente."""

    tipo_entidad = serializers.ChoiceField(
        choices=[
            "contactos",
            "productos",
            "pedidos_venta",
            "pedidos_compra",
            "facturas_venta",
            "facturas_compra",
            "pagos",
            "gestiones_cobranza",
            "inventario",
        ]
    )
    direccion = serializers.ChoiceField(
        choices=["inbound", "outbound", "bidireccional"],
        default="inbound",
    )
    sync_completo = serializers.BooleanField(
        default=False,
        help_text="True = ignorar último sync, traer todos los registros.",
    )
    desde = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Fecha ISO desde la cual sincronizar (opcional).",
    )


class PushCobranzaInputSerializer(serializers.Serializer):
    """Serializer para disparar push outbound de cobranza (pagos y/o gestiones)."""

    tipo = serializers.ChoiceField(
        choices=["pagos", "gestiones_cobranza", "todos"],
        default="todos",
        required=False,
    )
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    push_modo_pago = serializers.ChoiceField(
        choices=["borrador", "confirmado"],
        required=False,
        allow_null=True,
    )
    journal_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    sync_completo = serializers.BooleanField(default=False, required=False)


class PushCobranzaResponseSerializer(serializers.Serializer):
    """Respuesta 202 al disparar push outbound de cobranza."""

    mensaje = serializers.CharField()
    job_id = serializers.UUIDField(allow_null=True, required=False)
    jobs = JobSincronizacionSerializer(many=True)


class LogDetalleSincronizacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LogDetalleSincronizacion
        fields = [
            "id_log",
            "id_job",
            "id_externo",
            "id_omni",
            "operacion",
            "resumen_externo",
            "mensaje_error",
            "creado_en",
        ]
        read_only_fields = fields


class EntidadSincronizadaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntidadSincronizada
        fields = [
            "id_entidad_sync",
            "id_instancia",
            "tipo_entidad",
            "id_externo",
            "id_omni",
            "modelo_omni",
            "ultimo_sync",
            "activo",
        ]
        read_only_fields = fields


class EventoOutboxSerializer(serializers.ModelSerializer):
    """Serializer de solo lectura para eventos de la cola Outbox multi-tenant."""

    class Meta:
        model = EventoOutbox
        fields = [
            "id_evento",
            "id_empresa",
            "tipo_evento",
            "entidad_tipo",
            "entidad_id",
            "clave_idempotencia",
            "payload",
            "estado",
            "intentos",
            "max_intentos",
            "proximo_intento_en",
            "procesado_en",
            "ultimo_error",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = fields
