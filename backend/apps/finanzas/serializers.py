from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.core.models import Sucursal
from apps.core.serializer_mixins import (
    empresa_efectiva_contexto,
    empresas_visibles_contexto,
    validar_fk_empresa,
)

# --- Sesión de Caja ---
from .models import (
    Caja,
    CajaFisica,
    CajaFisicaUsuario,
    CajaMetodoPagoOverride,
    CajaUsuario,
    CajaVirtualAuto,
    CajaVirtualUsuario,
    Datafono,
    DepositoDatafono,
    MetodoPagoEmpresaActiva,
    Pago,
    PlantillaMaestroCajasVirtuales,
    SesionCajaFisica,
    SesionDatafono,
    TransaccionDatafono,
)


class MetodoPagoEmpresaActivaSerializer(serializers.ModelSerializer):
    metodo_pago = serializers.UUIDField(source="metodo_pago.id_metodo_pago")
    nombre = serializers.CharField(source="metodo_pago.nombre_metodo", read_only=True)

    def create(self, validated_data):
        # SEC-M2 (auditoría 2026-06-10): `empresa` es read-only — se inyecta
        # SIEMPRE la empresa primaria del usuario (estilo EmpresaInjectMixin),
        # ignorando cualquier valor enviado por el cliente (R-CODE-1).
        from django.db import models as django_models

        from apps.core.viewsets import get_empresa_primaria, get_empresas_visible

        validated_data.pop("empresa", None)
        request = self.context.get("request")
        empresa = get_empresa_primaria(request.user) if request else None
        if empresa is None:
            raise serializers.ValidationError({"empresa": "El usuario no tiene empresa asignada."})
        validated_data["empresa"] = empresa

        metodo_pago_value = validated_data.pop("metodo_pago", None)
        if isinstance(metodo_pago_value, dict) and "id_metodo_pago" in metodo_pago_value:
            metodo_pago_uuid = metodo_pago_value["id_metodo_pago"]
        else:
            metodo_pago_uuid = metodo_pago_value
        if metodo_pago_uuid:
            from .models import MetodoPago

            # R-CODE-1: solo se pueden activar métodos visibles para el usuario
            # (genéricos, públicos, sin empresa o de sus empresas) — no los
            # privados de otro tenant.
            visibles = MetodoPago.objects.filter(
                django_models.Q(es_generico=True)
                | django_models.Q(es_publico=True)
                | django_models.Q(empresa__isnull=True)
                | django_models.Q(empresa__in=get_empresas_visible(request.user))
            )
            try:
                validated_data["metodo_pago"] = visibles.get(id_metodo_pago=metodo_pago_uuid)
            except MetodoPago.DoesNotExist:
                raise serializers.ValidationError({"metodo_pago": ["Método de pago no encontrado."]})

        return super().create(validated_data)

    class Meta:
        model = MetodoPagoEmpresaActiva
        fields = ["id", "empresa", "metodo_pago", "activa", "nombre"]
        # SEC-M2: el cliente no decide la empresa destino.
        read_only_fields = ["empresa"]


from django.db import transaction
from rest_framework import serializers

from .models import (
    CuentaBancariaEmpresa,
    MetodoPago,
    Moneda,
    MonedaEmpresaActiva,
    MovimientoCajaBanco,
    TasaCambio,
    TipoTasaCambio,
    TransaccionFinanciera,
)


class MonedaSerializer(serializers.ModelSerializer):
    pais_codigo_iso = serializers.CharField(read_only=True)
    pais_nombre = serializers.CharField(read_only=True)

    class Meta:
        model = Moneda
        # CTF-005 (fase 2): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_moneda",
            "pais_codigo_iso",
            "pais_nombre",
            "tipo_moneda",
            "codigo_iso",
            "nombre",
            "referencia_externa",
            "documento_json",
            "tipo_operacion",
            "fecha_cierre_estimada",
            "simbolo",
            "decimales",
            "activo",
            "fecha_creacion",
            "es_generica",
            "es_publica",
            "empresa",
        ]
        read_only_fields = ["pais_codigo_iso", "pais_nombre"]

    def to_representation(self, instance):
        # Oculta campos sensibles para usuarios normales
        rep = super().to_representation(instance)
        user = self.context.get("request").user if self.context.get("request") else None
        if not getattr(user, "es_superusuario_omni", False):
            rep.pop("es_generica", None)
            rep.pop("empresa", None)
        return rep

    def validate(self, data):
        user = self.context["request"].user if "request" in self.context else None
        tipo_moneda = data.get("tipo_moneda", getattr(self.instance, "tipo_moneda", None))
        codigo_iso = data.get("codigo_iso", getattr(self.instance, "codigo_iso", None))
        # Validación de código ISO
        if tipo_moneda == "crypto":
            if not (4 <= len(codigo_iso) <= 5):
                raise serializers.ValidationError(
                    {"codigo_iso": "Para monedas cripto, el código ISO debe tener 4 o 5 caracteres."}
                )
        else:
            if len(codigo_iso) > 3:
                raise serializers.ValidationError(
                    {"codigo_iso": "Para monedas fiat u otro, el código ISO debe tener máximo 3 caracteres."}
                )
        # Solo superusuario puede modificar monedas genéricas
        if self.instance and self.instance.es_generica and not getattr(user, "es_superusuario_omni", False):
            raise serializers.ValidationError("No puede modificar una moneda genérica del sistema.")
        # Solo superusuario puede marcar como genérica o pública o cambiar empresa
        if (data.get("es_generica") or data.get("es_publica") or data.get("empresa")) and not getattr(
            user, "es_superusuario_omni", False
        ):
            raise serializers.ValidationError(
                "Solo el superusuario puede crear o modificar monedas genéricas, públicas o de otra empresa."
            )

        # Validar unicidad de codigo_iso por empresa si no es genérica
        es_generica = data.get("es_generica", getattr(self.instance, "es_generica", False))
        empresa = data.get("empresa", getattr(self.instance, "empresa", None))
        if not es_generica:
            qs = Moneda.objects.filter(codigo_iso=codigo_iso, es_generica=False, empresa=empresa)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"codigo_iso": "Ya existe una moneda con este código ISO para esta empresa."}
                )
        return data

    def create(self, validated_data):
        user = self.context["request"].user if "request" in self.context else None
        # Si no es superusuario, fuerza empresa y flags (sin permitir empresa=None si no tiene empresas)
        if not getattr(user, "es_superusuario_omni", False):
            from rest_framework.exceptions import PermissionDenied

            from apps.core.viewsets import get_empresas_visible

            empresas = get_empresas_visible(user) if user is not None else None
            if not empresas or not empresas.exists():
                raise PermissionDenied("El usuario no tiene ninguna empresa visible asignada.")
            validated_data["empresa"] = empresas.first()
            validated_data["es_generica"] = False
            validated_data["es_publica"] = False
        return super().create(validated_data)

    def update(self, instance, validated_data):
        user = self.context["request"].user if "request" in self.context else None
        # Si no es superusuario, no puede cambiar empresa ni flags
        if not getattr(user, "es_superusuario_omni", False):
            validated_data.pop("empresa", None)
            validated_data.pop("es_generica", None)
            validated_data.pop("es_publica", None)
        return super().update(instance, validated_data)


_TIPOS_TASA_LEGACY_VALIDOS = frozenset(
    {"OFICIAL_BCV", "ESPECIAL_USUARIO", "PROMEDIO_MERCADO", "FIJA", "PERSONALIZADA"}
)


class TipoTasaCambioSerializer(serializers.ModelSerializer):
    """Serializer para tipos de tasa de cambio extensibles por empresa o globales."""

    id_empresa = serializers.PrimaryKeyRelatedField(
        queryset=Moneda._meta.get_field("empresa").related_model.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = TipoTasaCambio
        fields = [
            "id_tipo_tasa",
            "id_empresa",
            "codigo",
            "nombre",
            "descripcion",
            "es_oficial_fiscal",
            "prioridad",
            "activo",
            "fecha_creacion",
            "fecha_actualizacion",
        ]
        read_only_fields = ("id_tipo_tasa", "fecha_creacion", "fecha_actualizacion")
        validators = []

    def validate_codigo(self, value: str) -> str:
        codigo = (value or "").strip().upper()
        if not codigo:
            raise serializers.ValidationError("El código del tipo de tasa no puede estar vacío.")
        return codigo

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        es_super = bool(getattr(user, "es_superusuario_omni", False))

        if self.instance is not None and self.instance.id_empresa_id is None and not es_super:
            raise serializers.ValidationError("No tiene permiso para modificar un tipo de tasa global del sistema.")

        if self.instance is not None:
            empresa = self.instance.id_empresa
            if es_super and "id_empresa" in attrs:
                empresa = attrs["id_empresa"]
        else:
            if es_super:
                empresa = attrs.get("id_empresa")
            else:
                from apps.core.viewsets import get_empresa_primaria

                empresa = get_empresa_primaria(user) if user is not None else None
                if empresa is None:
                    raise serializers.ValidationError(
                        {"id_empresa": "El usuario no tiene una empresa visible asignada."}
                    )

        codigo = attrs.get("codigo", getattr(self.instance, "codigo", ""))
        codigo = (codigo or "").strip().upper()
        if codigo:
            qs = TipoTasaCambio.objects.filter(codigo=codigo, id_empresa=empresa)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"codigo": f"Ya existe un tipo de tasa con el código '{codigo}' para este alcance."}
                )
        return attrs

    def create(self, validated_data: dict[str, Any]) -> TipoTasaCambio:
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if not getattr(user, "es_superusuario_omni", False):
            from apps.core.viewsets import get_empresa_primaria

            empresa = get_empresa_primaria(user) if user is not None else None
            if empresa is None:
                raise serializers.ValidationError({"id_empresa": "El usuario no tiene una empresa visible asignada."})
            validated_data["id_empresa"] = empresa
        return super().create(validated_data)

    def update(self, instance: TipoTasaCambio, validated_data: dict[str, Any]) -> TipoTasaCambio:
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if not getattr(user, "es_superusuario_omni", False):
            validated_data.pop("id_empresa", None)
        return super().update(instance, validated_data)


class TasaCambioSerializer(serializers.ModelSerializer):
    moneda_origen_nombre = serializers.CharField(source="id_moneda_origen.nombre", read_only=True)
    moneda_destino_nombre = serializers.CharField(source="id_moneda_destino.nombre", read_only=True)
    usuario_registro_username = serializers.CharField(source="id_usuario_registro.username", read_only=True)
    tipo_tasa_codigo = serializers.SerializerMethodField()
    tipo_tasa_nombre = serializers.CharField(source="id_tipo_tasa.nombre", read_only=True)
    tipo_tasa = serializers.ChoiceField(
        choices=TasaCambio._meta.get_field("tipo_tasa").choices,
        required=False,
        allow_blank=True,
    )

    def get_tipo_tasa_codigo(self, obj: TasaCambio) -> str:
        if obj.id_tipo_tasa_id and obj.id_tipo_tasa is not None:
            return obj.id_tipo_tasa.codigo
        return obj.tipo_tasa

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        tipo_obj = attrs.get("id_tipo_tasa", getattr(self.instance, "id_tipo_tasa", None))

        if tipo_obj is not None and user is not None and not getattr(user, "es_superusuario_omni", False):
            from apps.core.viewsets import get_empresas_visible

            if tipo_obj.id_empresa_id is not None and tipo_obj.id_empresa_id not in set(
                get_empresas_visible(user).values_list("id_empresa", flat=True)
            ):
                raise serializers.ValidationError({"id_tipo_tasa": "El tipo de tasa no pertenece a su empresa."})

        tipo_legacy = attrs.get("tipo_tasa")
        if tipo_obj is not None and not tipo_legacy:
            codigo = (tipo_obj.codigo or "").strip().upper()
            attrs["tipo_tasa"] = codigo if codigo in _TIPOS_TASA_LEGACY_VALIDOS else "PERSONALIZADA"
        elif self.instance is None and not tipo_legacy and tipo_obj is None:
            raise serializers.ValidationError({"tipo_tasa": "Debe especificar tipo_tasa o id_tipo_tasa."})
        return attrs

    class Meta:
        model = TasaCambio
        # CTF-005 (fase 2): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_tasa_cambio",
            "moneda_origen_nombre",
            "moneda_destino_nombre",
            "usuario_registro_username",
            "id_tipo_tasa",
            "tipo_tasa_codigo",
            "tipo_tasa_nombre",
            "tipo_tasa",
            "valor_tasa",
            "fecha_tasa",
            "hora_tasa",
            "referencia_externa",
            "documento_json",
            "tipo_operacion",
            "fecha_cierre_estimada",
            "fecha_creacion",
            "id_empresa",
            "id_moneda_origen",
            "id_moneda_destino",
            "id_usuario_registro",
        ]
        read_only_fields = (
            "moneda_origen_nombre",
            "moneda_destino_nombre",
            "usuario_registro_username",
            "tipo_tasa_codigo",
            "tipo_tasa_nombre",
        )


class EquivalenciasTrimonetariasInputSerializer(serializers.Serializer):
    """Parámetros de entrada para el cálculo trimonetario simultáneo."""

    monto = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=Decimal("0"))
    moneda_origen = serializers.CharField(max_length=40)
    fecha = serializers.DateField(required=False, allow_null=True, default=None)
    codigo_tipo_tasa_base = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    codigo_tipo_tasa_referencia = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")


from rest_framework.reverse import reverse


class MetodoPagoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    aplicado = serializers.SerializerMethodField()

    class Meta:
        model = MetodoPago
        # CTF-005 (fase 2): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_metodo_pago",
            "url",
            "aplicado",
            "referencia_externa",
            "documento_json",
            "nombre_metodo",
            "tipo_metodo",
            "activo",
            "fecha_creacion",
            "es_generico",
            "es_publico",
            "empresa",
            "monedas",
        ]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        user = self.context.get("request").user if self.context.get("request") else None
        if not getattr(user, "es_superusuario_omni", False):
            rep.pop("es_generico", None)
            rep.pop("empresa", None)
            rep.pop("es_publico", None)
        return rep

    def validate(self, data):
        user = self.context["request"].user if "request" in self.context else None
        # Solo superusuario puede modificar métodos genéricos
        if (
            self.instance
            and getattr(self.instance, "es_generico", False)
            and not getattr(user, "es_superusuario_omni", False)
        ):
            raise serializers.ValidationError("No puede modificar un método de pago genérico del sistema.")
        # Solo superusuario puede marcar como genérico o público o cambiar empresa
        if (data.get("es_generico") or data.get("es_publico") or data.get("empresa")) and not getattr(
            user, "es_superusuario_omni", False
        ):
            raise serializers.ValidationError(
                "Solo el superusuario puede crear o modificar métodos de pago genéricos, públicos o de otra empresa."
            )
        # Validar unicidad de nombre_metodo por empresa y tipo_metodo si no es genérico
        es_generico = data.get("es_generico", getattr(self.instance, "es_generico", False))
        empresa = data.get("empresa", getattr(self.instance, "empresa", None))
        nombre_metodo = data.get("nombre_metodo", getattr(self.instance, "nombre_metodo", None))
        tipo_metodo = data.get("tipo_metodo", getattr(self.instance, "tipo_metodo", None))
        from .models import MetodoPago

        if not es_generico and empresa and nombre_metodo and tipo_metodo:
            qs = MetodoPago.objects.filter(
                nombre_metodo=nombre_metodo, es_generico=False, empresa=empresa, tipo_metodo=tipo_metodo
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"nombre_metodo": "Ya existe un método de pago con este nombre para esta empresa y tipo."}
                )
        monedas = data.get("monedas", getattr(self.instance, "monedas", []))
        tipo_metodo = data.get("tipo_metodo", getattr(self.instance, "tipo_metodo", None))
        empresa = data.get("empresa", getattr(self.instance, "empresa", None))
        es_generico = data.get("es_generico", getattr(self.instance, "es_generica", False))
        es_publico = data.get("es_publico", getattr(self.instance, "es_publico", False))
        # Validar monedas asociadas
        if monedas:
            monedas_objs = Moneda.objects.filter(
                id_moneda__in=[m.id_moneda if hasattr(m, "id_moneda") else m for m in monedas]
            )
            # Efectivo y Cheque: solo fiat, nunca crypto
            if tipo_metodo in ["EFECTIVO", "CHEQUE"]:
                for moneda in monedas_objs:
                    if moneda.tipo_moneda == "crypto":
                        raise serializers.ValidationError(
                            f"No se puede asociar la moneda {moneda.nombre} ({moneda.codigo_iso}) a '{tipo_metodo}'. Solo monedas fiat están permitidas."
                        )
            # Efectivo: debe estar asociado a todas las fiat públicas
            if tipo_metodo == "EFECTIVO":
                fiat_publicas = Moneda.objects.filter(tipo_moneda="fiat", es_publica=True)
                fiat_ids = set(fiat_publicas.values_list("id_moneda", flat=True))
                monedas_ids = set([m.id_moneda for m in monedas_objs])
                if not fiat_ids.issubset(monedas_ids):
                    raise serializers.ValidationError(
                        "El método de pago 'Efectivo' debe estar asociado a todas las monedas fiat públicas."
                    )
            # Cheque: solo fiat
            if tipo_metodo == "CHEQUE":
                for moneda in monedas_objs:
                    if moneda.tipo_moneda != "fiat":
                        raise serializers.ValidationError(
                            f"No se puede asociar la moneda {moneda.nombre} a 'Cheque'. Solo monedas fiat están permitidas."
                        )
            # Monedas privadas solo si pertenecen a la empresa
            if empresa:
                privadas = monedas_objs.filter(es_publica=False, es_generica=False)
                for moneda in privadas:
                    if moneda.empresa_id != str(empresa.id):
                        raise serializers.ValidationError(
                            f"La moneda privada {moneda.nombre} no pertenece a la empresa seleccionada."
                        )
        return data

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        # Si no es superusuario, fuerza empresa visible (incluye subsidiarias) y flags privadas
        if not getattr(user, "es_superusuario_omni", False):
            from rest_framework.exceptions import PermissionDenied

            from apps.core.viewsets import get_empresas_visible

            empresas = get_empresas_visible(user) if user is not None else None
            if not empresas or not empresas.exists():
                raise PermissionDenied("El usuario no tiene ninguna empresa visible asignada.")
            validated_data["empresa"] = empresas.first()
            validated_data["es_generico"] = False
            validated_data["es_publico"] = False
        instance = super().create(validated_data)
        # Logging para depuración
        import logging

        logger = logging.getLogger("django")
        logger.info(
            f"Creando MetodoPagoEmpresaActiva para empresa={getattr(instance, 'empresa', None)} y metodo_pago={instance}"
        )
        # Sincroniza activos por empresa
        if getattr(instance, "empresa", None):
            obj, created = MetodoPagoEmpresaActiva.objects.get_or_create(
                empresa=instance.empresa, metodo_pago=instance, defaults={"activa": True}
            )
            logger.info(f"MetodoPagoEmpresaActiva creado={created}, id={getattr(obj, 'id', None)}")
        else:
            logger.warning(
                f"No se pudo crear MetodoPagoEmpresaActiva porque empresa es None para metodo_pago={instance}"
            )
        return instance

    def update(self, instance, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        if not getattr(user, "es_superusuario_omni", False):
            validated_data.pop("empresa", None)
            validated_data.pop("es_generico", None)
            validated_data.pop("es_publico", None)
        instance = super().update(instance, validated_data)
        import logging

        logger = logging.getLogger("django")
        logger.info(
            f"Actualizando MetodoPagoEmpresaActiva para empresa={getattr(instance, 'empresa', None)} y metodo_pago={instance}"
        )
        if getattr(instance, "empresa", None):
            obj, created = MetodoPagoEmpresaActiva.objects.get_or_create(
                empresa=instance.empresa, metodo_pago=instance, defaults={"activa": True}
            )
            logger.info(f"MetodoPagoEmpresaActiva creado={created}, id={getattr(obj, 'id', None)}")
        else:
            logger.warning(
                f"No se pudo crear MetodoPagoEmpresaActiva porque empresa es None para metodo_pago={instance}"
            )
        return instance

    def get_url(self, obj):
        request = self.context.get("request")
        return reverse("metodopago-detail", args=[obj.id_metodo_pago], request=request)

    def get_aplicado(self, obj):
        # El id_empresa_actual se pasa por context desde la view
        id_empresa_actual = self.context.get("id_empresa_actual")
        if not id_empresa_actual:
            return False
        # Buscar si existe un método similar (fuzzy) para la empresa actual usando rapidfuzz
        import unicodedata

        from rapidfuzz.distance import Levenshtein
        from rapidfuzz.fuzz import ratio

        from .models import MetodoPago

        def normalizar(s):
            s = s.lower().replace(" ", "")
            s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
            return s

        nombre_actual = normalizar(obj.nombre_metodo)
        metodos_por_tipo = self.context.get("metodos_empresa_por_tipo")
        if metodos_por_tipo is not None:
            nombres_empresa = metodos_por_tipo.get(obj.tipo_metodo, ())
        else:
            nombres_empresa = MetodoPago.objects.filter(
                empresa=id_empresa_actual, tipo_metodo=obj.tipo_metodo
            ).values_list("nombre_metodo", flat=True)
        for nombre_metodo_db in nombres_empresa:
            nombre_db = normalizar(nombre_metodo_db)
            sim = ratio(nombre_actual, nombre_db)
            dist = Levenshtein.distance(nombre_actual, nombre_db)
            if sim >= 55 or dist <= 3 or nombre_actual in nombre_db or nombre_db in nombre_actual:
                return True
        return False


class MetodoPagoReutilizableSerializer(MetodoPagoSerializer):
    """
    Proyección segura para `buscar_reutilizar` (SEC-A3, auditoría 2026-06-10).

    Solo expone campos no sensibles del catálogo: NUNCA `documento_json`,
    `referencia_externa` ni metadatos de tenant de terceros.
    """

    class Meta:
        model = MetodoPago
        fields = ["id_metodo_pago", "nombre_metodo", "tipo_metodo", "activo", "url", "aplicado"]


class TransaccionFinancieraSerializer(serializers.ModelSerializer):
    def validate(self, data):
        tipo_transaccion = data.get("tipo_transaccion")
        id_caja = data.get("id_caja")
        id_cuenta_bancaria = data.get("id_cuenta_bancaria")
        id_metodo_pago = data.get("id_metodo_pago")
        id_moneda_transaccion = data.get("id_moneda_transaccion")
        # Validar método de pago permitido para caja/cuenta bancaria
        if tipo_transaccion in ["INGRESO", "EGRESO"]:
            if id_caja:
                metodos_permitidos = getattr(id_caja, "metodos_pago", None)
                if metodos_permitidos and id_metodo_pago not in metodos_permitidos.all():
                    raise serializers.ValidationError(
                        {"id_metodo_pago": "El método de pago no está permitido para la caja seleccionada."}
                    )
                if id_moneda_transaccion and id_caja.moneda != id_moneda_transaccion:
                    raise serializers.ValidationError(
                        {"id_moneda_transaccion": "La moneda no coincide con la moneda de la caja."}
                    )
            if id_cuenta_bancaria:
                metodos_permitidos = getattr(id_cuenta_bancaria, "metodos_pago", None)
                if metodos_permitidos and id_metodo_pago not in metodos_permitidos.all():
                    raise serializers.ValidationError(
                        {"id_metodo_pago": "El método de pago no está permitido para la cuenta bancaria seleccionada."}
                    )
                if id_moneda_transaccion and id_cuenta_bancaria.id_moneda != id_moneda_transaccion:
                    raise serializers.ValidationError(
                        {"id_moneda_transaccion": "La moneda no coincide con la moneda de la cuenta bancaria."}
                    )
        # Validar moneda permitida para el método de pago
        if id_metodo_pago and id_moneda_transaccion:
            monedas_permitidas = getattr(id_metodo_pago, "monedas", None)
            if monedas_permitidas and id_moneda_transaccion not in monedas_permitidas.all():
                raise serializers.ValidationError(
                    {"id_moneda_transaccion": "La moneda no está permitida para el método de pago seleccionado."}
                )
        return data

    id_empresa_nombre = serializers.CharField(source="id_empresa.nombre_comercial", read_only=True)
    id_usuario_registro_username = serializers.CharField(source="id_usuario_registro.username", read_only=True)
    id = serializers.UUIDField(source="id_transaccion", read_only=True)
    id_moneda_transaccion__codigo_iso = serializers.CharField(
        source="id_moneda_transaccion.codigo_iso", read_only=True
    )
    id_moneda_base__codigo_iso = serializers.CharField(source="id_moneda_base.codigo_iso", read_only=True)
    id_moneda_pais_empresa__codigo_iso = serializers.CharField(
        source="id_moneda_pais_empresa.codigo_iso", read_only=True
    )
    id_metodo_pago__nombre_metodo = serializers.CharField(source="id_metodo_pago.nombre_metodo", read_only=True)
    id_usuario_registro__username = serializers.CharField(source="id_usuario_registro.username", read_only=True)
    tasa_cambio = serializers.CharField(write_only=True, required=False)
    monto_base = serializers.CharField(write_only=True, required=False)
    monto_moneda_pais = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, allow_null=True)

    class Meta:
        model = TransaccionFinanciera
        fields = [
            "id",
            "id_transaccion",
            "id_empresa",
            "id_empresa_nombre",
            "fecha_hora_transaccion",
            "tipo_transaccion",
            "monto_transaccion",
            "id_moneda_transaccion",
            "id_moneda_base",
            "id_moneda_pais_empresa",
            "monto_moneda_pais",
            "monto_base_empresa",
            "id_metodo_pago",
            "referencia_pago",
            "descripcion",
            "tipo_documento_asociado",
            "nro_documento_asociado",
            "id_caja",
            "id_cuenta_bancaria",
            "id_usuario_registro",
            "id_usuario_registro_username",
            "fecha_creacion",
            "id_moneda_transaccion__codigo_iso",
            "id_moneda_base__codigo_iso",
            "id_moneda_pais_empresa__codigo_iso",
            "id_metodo_pago__nombre_metodo",
            "id_usuario_registro__username",
            "tasa_cambio",
            "monto_base",
        ]
        extra_fields = [
            "tasa_cambio",
            "monto_base",
            "id_moneda_base__codigo_iso",
            "id_moneda_pais_empresa__codigo_iso",
            "monto_moneda_pais",
        ]
        read_only_fields = (
            "id",
            "id_moneda_transaccion__codigo_iso",
            "id_moneda_base__codigo_iso",
            "id_moneda_pais_empresa__codigo_iso",
            "id_metodo_pago__nombre_metodo",
            "id_usuario_registro__username",
        )

    def create(self, validated_data):
        # Mapear monto_base del frontend a monto_base_empresa del modelo
        monto_base = validated_data.pop("monto_base", None)
        if monto_base is not None:
            validated_data["monto_base_empresa"] = monto_base
        # El campo tasa_cambio solo se usa para validación, no se guarda
        validated_data.pop("tasa_cambio", None)
        # Asignar usuario autenticado si no viene en el payload
        request = self.context.get("request")
        if request and not validated_data.get("id_usuario_registro"):
            user = request.user
            validated_data["id_usuario_registro"] = user
        # Asignar empresa si no viene en el payload y el usuario tiene empresas
        if request and not validated_data.get("id_empresa"):
            user = request.user
            empresas = getattr(user, "empresas", None)
            if empresas and empresas.exists():
                validated_data["id_empresa"] = empresas.first()
        # Convertir id_moneda_transaccion, id_moneda_base y id_metodo_pago a instancias si vienen como UUID
        from .models import MetodoPago, Moneda, MovimientoCajaBanco, TasaCambio

        for moneda_field in ["id_moneda_transaccion", "id_moneda_base"]:
            moneda_value = validated_data.get(moneda_field)
            if isinstance(moneda_value, str):
                try:
                    validated_data[moneda_field] = Moneda.objects.get(id_moneda=moneda_value)
                except Moneda.DoesNotExist:
                    validated_data[moneda_field] = None
        metodo_value = validated_data.get("id_metodo_pago")
        if isinstance(metodo_value, str):
            validated_data["id_metodo_pago"] = MetodoPago.objects.get(id_metodo_pago=metodo_value)

        # Obtener moneda país desde la empresa
        empresa = validated_data.get("id_empresa")
        if empresa and hasattr(empresa, "id_moneda_pais") and empresa.id_moneda_pais:
            validated_data["id_moneda_pais_empresa"] = empresa.id_moneda_pais
        else:
            validated_data["id_moneda_pais_empresa"] = None

        # Calcular monto_moneda_pais usando la tasa de cambio del día solo si no viene del frontend
        if "monto_moneda_pais" not in validated_data or validated_data["monto_moneda_pais"] is None:
            moneda_transaccion = validated_data.get("id_moneda_transaccion")
            moneda_pais = validated_data.get("id_moneda_pais_empresa")
            monto_transaccion = validated_data.get("monto_transaccion")
            monto_moneda_pais = None
            if moneda_transaccion and moneda_pais and monto_transaccion:
                from django.utils import timezone

                # localdate() = hoy en TIME_ZONE (Caracas), no en UTC: con
                # date.today() la tasa del día no se encontraba tras las 20:00
                # Caracas y monto_moneda_pais quedaba en None.
                hoy = timezone.localdate()
                tasa = (
                    TasaCambio.objects.filter(
                        id_moneda_origen=moneda_transaccion, id_moneda_destino=moneda_pais, fecha_tasa=hoy
                    )
                    .order_by("-fecha_tasa")
                    .first()
                )
                if tasa:
                    monto_moneda_pais = Decimal(str(monto_transaccion)) * Decimal(str(tasa.valor_tasa))
            validated_data["monto_moneda_pais"] = monto_moneda_pais

        # Crear la transacción financiera
        transaccion = super().create(validated_data)

        # Validar que toda transacción tenga documento asociado (null=True para migración)
        if "tipo_documento_asociado" not in validated_data:
            validated_data["tipo_documento_asociado"] = None
        if "nro_documento_asociado" not in validated_data:
            validated_data["nro_documento_asociado"] = None
        # Crear automáticamente el MovimientoCajaBanco asociado
        tipo_movimiento = "INGRESO" if transaccion.tipo_transaccion == "INGRESO" else "EGRESO"
        movimiento_data = {
            "id_empresa": transaccion.id_empresa,
            "fecha_movimiento": transaccion.fecha_hora_transaccion.date(),
            "hora_movimiento": transaccion.fecha_hora_transaccion.time(),
            "tipo_movimiento": tipo_movimiento,
            "monto": transaccion.monto_transaccion,
            "id_moneda": transaccion.id_moneda_transaccion,
            "concepto": transaccion.descripcion or "",
            "referencia": transaccion.referencia_pago or "",
            "id_caja": transaccion.id_caja,
            "id_cuenta_bancaria": transaccion.id_cuenta_bancaria,
            "id_transaccion_financiera": transaccion,
            "saldo_anterior": 0,  # Se puede calcular en la view/model si aplica
            "saldo_nuevo": 0,  # Se puede calcular en la view/model si aplica
            "id_usuario_registro": transaccion.id_usuario_registro,
        }
        MovimientoCajaBanco.objects.create(**movimiento_data)

        return transaccion


class MovimientoCajaBancoSerializer(serializers.ModelSerializer):
    moneda_codigo_iso = serializers.CharField(source="id_moneda.codigo_iso", read_only=True)
    caja_nombre = serializers.CharField(source="id_caja.nombre", read_only=True)
    sucursal_nombre = serializers.CharField(source="id_caja.sucursal.nombre", read_only=True)
    empresa_nombre = serializers.CharField(source="id_caja.empresa.nombre_comercial", read_only=True)
    usuario_registro_username = serializers.CharField(source="id_usuario_registro.username", read_only=True)

    class Meta:
        model = MovimientoCajaBanco
        # CTF-005 (fase 2): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_movimiento",
            "moneda_codigo_iso",
            "caja_nombre",
            "sucursal_nombre",
            "empresa_nombre",
            "usuario_registro_username",
            "fecha_movimiento",
            "hora_movimiento",
            "tipo_movimiento",
            "monto",
            "concepto",
            "referencia",
            "saldo_anterior",
            "saldo_nuevo",
            "fecha_creacion",
            "id_empresa",
            "id_moneda",
            "id_caja",
            "id_caja_fisica",
            "id_cuenta_bancaria",
            "id_transaccion_financiera",
            "id_usuario_registro",
        ]


class CuentaBancariaEmpresaSerializer(serializers.ModelSerializer):
    moneda_codigo_iso = serializers.CharField(source="id_moneda.codigo_iso", read_only=True)
    metodos_pago = serializers.PrimaryKeyRelatedField(queryset=MetodoPago.objects.all(), many=True, required=False)
    monedas = serializers.PrimaryKeyRelatedField(queryset=Moneda.objects.all(), many=True, required=False)

    class Meta:
        model = CuentaBancariaEmpresa
        # CTF-005 (fase 2): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_cuenta_bancaria",
            "moneda_codigo_iso",
            "metodos_pago",
            "monedas",
            "nombre_banco",
            "numero_cuenta",
            "tipo_cuenta",
            "saldo_actual",
            "activo",
            "fecha_creacion",
            "id_empresa",
            "id_moneda",
        ]
        read_only_fields = ["moneda_codigo_iso"]
        ref_name = "CuentaBancariaEmpresaFinanzas"  # evita colisión OpenAPI con banca_electronica

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs = super().validate(attrs)
        instance = self.instance if isinstance(self.instance, CuentaBancariaEmpresa) else None
        if instance is not None and "id_empresa" in attrs:
            nueva_emp = attrs["id_empresa"]
            if nueva_emp is None or nueva_emp.pk != instance.id_empresa_id:
                raise serializers.ValidationError(
                    {"id_empresa": "No se puede cambiar la empresa de una cuenta bancaria existente."}
                )

        emp = attrs["id_empresa"] if "id_empresa" in attrs else getattr(instance, "id_empresa", None)
        empresa_ref = str(emp.pk) if emp is not None else empresa_efectiva_contexto(self)
        visibles = empresas_visibles_contexto(self)
        if emp is not None and visibles is not None and str(emp.pk) not in visibles:
            raise serializers.ValidationError({"id_empresa": "No tiene permisos sobre la empresa indicada."})

        moneda = attrs["id_moneda"] if "id_moneda" in attrs else getattr(instance, "id_moneda", None)
        if moneda is not None and not (
            getattr(moneda, "es_generica", False)
            or getattr(moneda, "es_publica", False)
            or getattr(moneda, "empresa_id", None) is None
        ):
            validar_fk_empresa(
                moneda,
                "id_moneda",
                empresa_ref,
                visibles,
                etiqueta="Moneda",
                empresa_attr="empresa_id",
            )

        metodos = attrs.get("metodos_pago")
        if metodos:
            for metodo in metodos:
                if not (
                    getattr(metodo, "es_generico", False)
                    or getattr(metodo, "es_publico", False)
                    or getattr(metodo, "empresa_id", None) is None
                ):
                    validar_fk_empresa(
                        metodo,
                        "metodos_pago",
                        empresa_ref,
                        visibles,
                        etiqueta="Método de pago",
                        empresa_attr="empresa_id",
                    )

        monedas_extra = attrs.get("monedas")
        if monedas_extra:
            for mon in monedas_extra:
                if not (
                    getattr(mon, "es_generica", False)
                    or getattr(mon, "es_publica", False)
                    or getattr(mon, "empresa_id", None) is None
                ):
                    validar_fk_empresa(
                        mon,
                        "monedas",
                        empresa_ref,
                        visibles,
                        etiqueta="Moneda",
                        empresa_attr="empresa_id",
                    )

        if "numero_cuenta" in attrs:
            numero = str(attrs["numero_cuenta"] or "").replace("\x00", "").strip()
            if not numero:
                raise serializers.ValidationError({"numero_cuenta": "El número de cuenta no puede estar vacío."})
            if numero != attrs["numero_cuenta"]:
                qs = CuentaBancariaEmpresa.objects.filter(numero_cuenta=numero)
                if instance is not None:
                    qs = qs.exclude(pk=instance.pk)
                if qs.exists():
                    raise serializers.ValidationError(
                        {"numero_cuenta": "Ya existe una cuenta bancaria con este número."}
                    )
            attrs["numero_cuenta"] = numero

        if "saldo_actual" in attrs and attrs["saldo_actual"] is not None:
            saldo = attrs["saldo_actual"]
            if isinstance(saldo, Decimal) and not saldo.is_finite():
                raise serializers.ValidationError({"saldo_actual": "El saldo actual debe ser finito."})

        return attrs


class MonedaEmpresaActivaSerializer(serializers.ModelSerializer):
    empresa_nombre = serializers.CharField(source="empresa.nombre_comercial", read_only=True)
    moneda_codigo_iso = serializers.CharField(source="moneda.codigo_iso", read_only=True)
    moneda_nombre = serializers.CharField(source="moneda.nombre", read_only=True)
    moneda = serializers.UUIDField(source="moneda.id_moneda")
    es_base = serializers.SerializerMethodField()
    es_pais = serializers.SerializerMethodField()

    def get_es_base(self, obj):
        # Lógica: la moneda base de la empresa está en Empresa.id_moneda_base
        empresa = getattr(obj, "empresa", None)
        moneda = getattr(obj, "moneda", None)
        if not (empresa and moneda):
            return False
        base_id = getattr(empresa, "id_moneda_base_id", None) or getattr(empresa, "moneda_base_id", None)
        return base_id == getattr(moneda, "id_moneda", None)

    def get_es_pais(self, obj):
        # Lógica: la moneda país de la empresa está en Empresa.id_moneda_pais
        empresa = getattr(obj, "empresa", None)
        moneda = getattr(obj, "moneda", None)
        if not (empresa and moneda):
            return False
        # Compatibilidad: intentar tanto atributo FK directo como sufijo _id
        moneda_pais_id = getattr(empresa, "id_moneda_pais_id", None)
        if moneda_pais_id is None:
            moneda_pais = getattr(empresa, "id_moneda_pais", None)
            moneda_pais_id = getattr(moneda_pais, "id_moneda", None)
        return moneda_pais_id == getattr(moneda, "id_moneda", None)

    @staticmethod
    def _limpiar_otra_referencia(instancia: MonedaEmpresaActiva) -> None:
        if instancia.es_moneda_referencia and instancia.activa:
            MonedaEmpresaActiva.objects.filter(
                empresa=instancia.empresa,
                es_moneda_referencia=True,
                activa=True,
            ).exclude(pk=instancia.pk).update(es_moneda_referencia=False)

    def create(self, validated_data):
        # Asignar empresa si no viene en el payload (opcional, según tu lógica)
        request = self.context.get("request")
        if request and not validated_data.get("empresa"):
            user = request.user
            empresas = getattr(user, "empresas", None)
            if empresas and empresas.exists():
                validated_data["empresa"] = empresas.first()

        # Obtener la instancia de Moneda usando el UUID recibido
        moneda_value = validated_data.pop("moneda", None)
        if isinstance(moneda_value, dict) and "id_moneda" in moneda_value:
            moneda_uuid = moneda_value["id_moneda"]
        else:
            moneda_uuid = moneda_value
        if moneda_uuid:
            from .models import Moneda

            try:
                validated_data["moneda"] = Moneda.objects.get(id_moneda=moneda_uuid)
            except Moneda.DoesNotExist:
                raise serializers.ValidationError({"moneda": "Moneda no encontrada"})

        with transaction.atomic():
            if validated_data.get("es_moneda_referencia") and validated_data.get("activa", True):
                MonedaEmpresaActiva.objects.filter(
                    empresa=validated_data["empresa"],
                    es_moneda_referencia=True,
                    activa=True,
                ).update(es_moneda_referencia=False)
            instancia = super().create(validated_data)
            self._limpiar_otra_referencia(instancia)
            return instancia

    def update(self, instance, validated_data):
        moneda_value = validated_data.pop("moneda", None)
        if isinstance(moneda_value, dict) and "id_moneda" in moneda_value:
            moneda_uuid = moneda_value["id_moneda"]
        else:
            moneda_uuid = moneda_value
        if moneda_uuid:
            from .models import Moneda

            try:
                validated_data["moneda"] = Moneda.objects.get(id_moneda=moneda_uuid)
            except Moneda.DoesNotExist:
                raise serializers.ValidationError({"moneda": "Moneda no encontrada"})

        with transaction.atomic():
            nuevo_ref = validated_data.get("es_moneda_referencia", instance.es_moneda_referencia)
            nuevo_activa = validated_data.get("activa", instance.activa)
            if nuevo_ref and nuevo_activa:
                MonedaEmpresaActiva.objects.filter(
                    empresa=instance.empresa,
                    es_moneda_referencia=True,
                    activa=True,
                ).exclude(pk=instance.pk).update(es_moneda_referencia=False)
            instancia = super().update(instance, validated_data)
            self._limpiar_otra_referencia(instancia)
            return instancia

    class Meta:
        model = MonedaEmpresaActiva
        fields = [
            "id",
            "empresa",
            "empresa_nombre",
            "moneda",
            "moneda_codigo_iso",
            "moneda_nombre",
            "activa",
            "es_moneda_referencia",
            "es_base",
            "es_pais",
        ]
        read_only_fields = [
            "empresa_nombre",
            "moneda_codigo_iso",
            "moneda_nombre",
            "es_base",
            "es_pais",
        ]


class CajaUsuarioSerializer(serializers.ModelSerializer):
    caja = serializers.UUIDField(source="caja.id_caja", read_only=True)
    caja_nombre = serializers.CharField(source="caja.nombre", read_only=True)
    caja_moneda = serializers.CharField(source="caja.moneda.codigo_iso", read_only=True)
    caja_sucursal = serializers.CharField(source="caja.sucursal.nombre", read_only=True)

    class Meta:
        model = CajaUsuario
        fields = [
            "id",
            "usuario",
            "caja",
            "es_predeterminada",
            "fecha_asignacion",
            "caja_nombre",
            "caja_moneda",
            "caja_sucursal",
        ]
        read_only_fields = ["id", "fecha_asignacion"]


class CajaVirtualUsuarioSerializer(serializers.ModelSerializer):
    caja_virtual = serializers.UUIDField(source="caja_virtual.id_caja", read_only=True)
    caja_virtual_nombre = serializers.CharField(source="caja_virtual.nombre", read_only=True)
    caja_virtual_moneda = serializers.CharField(source="caja_virtual.moneda.codigo_iso", read_only=True)
    caja_virtual_sucursal = serializers.CharField(source="caja_virtual.sucursal.nombre", read_only=True)

    class Meta:
        model = CajaVirtualUsuario
        fields = [
            "id",
            "usuario",
            "caja_virtual",
            "es_predeterminada",
            "fecha_asignacion",
            "caja_virtual_nombre",
            "caja_virtual_moneda",
            "caja_virtual_sucursal",
        ]
        read_only_fields = ["id", "fecha_asignacion"]


class CajaVirtualDisponibleSerializer(serializers.Serializer):
    """
    Serializer para cajas virtuales disponibles para un usuario basado en la jerarquía física.
    Compatible con la interfaz CajaUsuario del frontend.
    """

    id = serializers.UUIDField(source="id_caja", read_only=True)
    usuario = serializers.SerializerMethodField()
    caja = serializers.UUIDField(source="id_caja", read_only=True)  # Alias para compatibilidad
    caja_nombre = serializers.CharField(source="nombre", read_only=True)
    caja_moneda = serializers.CharField(source="moneda.codigo_iso", read_only=True)
    caja_sucursal = serializers.CharField(source="sucursal.nombre", read_only=True)
    es_predeterminada = serializers.SerializerMethodField()
    fecha_asignacion = serializers.SerializerMethodField()

    # Campos adicionales del nuevo formato
    tipo_caja = serializers.CharField(read_only=True)
    moneda_nombre = serializers.CharField(source="moneda.nombre", read_only=True)
    caja_fisica_id = serializers.UUIDField(source="caja_fisica.id_caja_fisica", read_only=True)
    caja_fisica_nombre = serializers.CharField(source="caja_fisica.nombre", read_only=True)

    # Campos para compatibilidad con filtrado por método de pago y moneda
    metodos_pago = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    monedas = serializers.SerializerMethodField()

    def get_usuario(self, obj):
        """Devuelve el ID del usuario actual para compatibilidad."""
        request = self.context.get("request")
        if request and hasattr(request, "user") and request.user.is_authenticated:
            return str(request.user.id)
        return None

    def get_es_predeterminada(self, obj):
        """
        Determina si esta caja es predeterminada para el usuario.
        Por ahora, la primera caja registradora disponible será la predeterminada.
        """
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            # Obtener la primera caja registradora asignada al usuario
            primera_caja = request.user.get_cajas_virtuales_disponibles().filter(tipo_caja="REGISTRADORA").first()
            if primera_caja:
                return primera_caja.id_caja == obj.id_caja

            # Si no hay registradoras, usar la primera caja disponible
            primera_caja_general = request.user.get_cajas_virtuales_disponibles().first()
            return primera_caja_general and primera_caja_general.id_caja == obj.id_caja
        return False

    def get_fecha_asignacion(self, obj):
        """Devuelve la fecha actual para compatibilidad."""
        from django.utils import timezone

        return timezone.now().isoformat()

    def get_monedas(self, obj):
        """Devuelve la moneda de la caja como lista para compatibilidad."""
        return [str(obj.moneda.id_moneda)]


class CajaFisicaUsuarioSerializer(serializers.ModelSerializer):
    caja = serializers.UUIDField(source="caja_fisica.id_caja", read_only=True)
    caja_nombre = serializers.CharField(source="caja_fisica.nombre", read_only=True)
    caja_moneda = serializers.CharField(source="caja_fisica.moneda.codigo_iso", read_only=True)
    caja_sucursal = serializers.CharField(source="caja_fisica.sucursal.nombre", read_only=True)

    class Meta:
        model = CajaFisicaUsuario
        fields = [
            "id",
            "usuario",
            "caja",
            "es_predeterminada",
            "fecha_asignacion",
            "puede_abrir_sesion",
            "puede_cerrar_sesion",
            "caja_nombre",
            "caja_moneda",
            "caja_sucursal",
        ]
        read_only_fields = ["id", "fecha_asignacion"]


class PlantillaMaestroCajasVirtualesSerializer(serializers.ModelSerializer):
    id_plantilla = serializers.UUIDField(source="id_plantilla_maestro", read_only=True)
    monedas = serializers.SerializerMethodField()
    metodos_pago = serializers.SerializerMethodField()
    empresa = serializers.StringRelatedField(read_only=True)
    creada_por = serializers.StringRelatedField(read_only=True)

    def get_monedas(self, obj):
        return [str(obj.moneda_base.id_moneda)]

    def get_metodos_pago(self, obj):
        return [str(mp.id_metodo_pago) for mp in obj.metodos_pago_base.all()]

    class Meta:
        model = PlantillaMaestroCajasVirtuales
        fields = [
            "id_plantilla",
            "empresa",
            "nombre",
            "descripcion",
            "monedas",
            "metodos_pago",
            "aplicar_a_todas_cajas_fisicas",
            "aplicar_a_empleados_con_rol",
            "activa",
            "creada_por",
            "fecha_creacion",
            "fecha_modificacion",
        ]
        read_only_fields = ["id_plantilla", "fecha_creacion", "fecha_modificacion"]

    def create(self, validated_data):
        request = self.context.get("request")

        # Extraer campos personalizados
        monedas = validated_data.pop("monedas", [])
        metodos_pago = validated_data.pop("metodos_pago", [])

        # Asignar empresa si no viene
        if request and not validated_data.get("empresa"):
            user = request.user
            empresas = getattr(user, "empresas", None)
            if empresas and hasattr(empresas, "first") and empresas.exists():
                validated_data["empresa"] = empresas.first()

        if request and not validated_data.get("creada_por"):
            validated_data["creada_por"] = request.user

        # Crear la instancia
        instance = super().create(validated_data)

        # Asignar moneda_base (tomar la primera de monedas)
        if monedas:
            from .models import Moneda

            try:
                moneda = Moneda.objects.get(id_moneda=monedas[0])
                instance.moneda_base = moneda
            except Moneda.DoesNotExist:
                pass

        # Asignar metodos_pago_base
        if metodos_pago:
            from .models import MetodoPago

            metodos_objs = MetodoPago.objects.filter(id_metodo_pago__in=metodos_pago)
            instance.metodos_pago_base.set(metodos_objs)

        instance.save()
        return instance

    def update(self, instance, validated_data):
        # Extraer campos personalizados
        monedas = validated_data.pop("monedas", None)
        metodos_pago = validated_data.pop("metodos_pago", None)

        # Actualizar campos normales
        instance = super().update(instance, validated_data)

        # Actualizar moneda_base si viene
        if monedas is not None and monedas:
            from .models import Moneda

            try:
                moneda = Moneda.objects.get(id_moneda=monedas[0])
                instance.moneda_base = moneda
            except Moneda.DoesNotExist:
                pass

        # Actualizar metodos_pago_base si viene
        if metodos_pago is not None:
            from .models import MetodoPago

            metodos_objs = MetodoPago.objects.filter(id_metodo_pago__in=metodos_pago)
            instance.metodos_pago_base.set(metodos_objs)

        instance.save()
        return instance


class CajaVirtualAutoSerializer(serializers.ModelSerializer):
    caja_fisica = serializers.StringRelatedField(read_only=True)
    empleado = serializers.StringRelatedField(read_only=True)
    plantilla_maestro = serializers.StringRelatedField(read_only=True)
    moneda = serializers.StringRelatedField(read_only=True)
    metodo_pago = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = CajaVirtualAuto
        fields = [
            "id_caja_virtual",
            "caja_fisica",
            "empleado",
            "plantilla_maestro",
            "moneda",
            "metodo_pago",
            "activa",
            "creada_automaticamente",
            "fecha_creacion",
            "fecha_modificacion",
        ]
        read_only_fields = ["id_caja_virtual", "fecha_creacion", "fecha_modificacion"]


class CajaMetodoPagoOverrideSerializer(serializers.ModelSerializer):
    id_sucursal = serializers.CharField(source="sucursal.id_sucursal", read_only=True)
    id_metodo_pago = serializers.CharField(source="metodo_pago.id_metodo_pago", read_only=True)
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", read_only=True)
    metodo_pago_nombre = serializers.CharField(source="metodo_pago.nombre", read_only=True)
    # FIX (lote 2): el queryset apuntaba a Caja (virtual) aunque el FK del
    # modelo es CajaFisica → ningún id real era aceptado (400 siempre).
    caja_fisica = serializers.PrimaryKeyRelatedField(queryset=CajaFisica.objects.all())
    metodo_pago = serializers.PrimaryKeyRelatedField(queryset=MetodoPago.objects.all())
    sucursal = serializers.PrimaryKeyRelatedField(queryset=Sucursal.objects.all())
    creado_por = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = CajaMetodoPagoOverride
        fields = [
            "id_override",
            "caja_fisica",
            "metodo_pago",
            "sucursal",
            "id_sucursal",
            "id_metodo_pago",
            "sucursal_nombre",
            "metodo_pago_nombre",
            "deshabilitado",
            "motivo",
            "creado_por",
            "fecha_creacion",
        ]
        read_only_fields = [
            "id_override",
            "fecha_creacion",
            "id_sucursal",
            "id_metodo_pago",
            "sucursal_nombre",
            "metodo_pago_nombre",
        ]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and not validated_data.get("creado_por"):
            validated_data["creado_por"] = request.user

        return super().create(validated_data)


# --- Serializers para Datafono ---


class TransaccionDatafonoSerializer(serializers.ModelSerializer):
    datafono_nombre = serializers.CharField(source="id_datafono.nombre", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    usuario_registro_nombre = serializers.CharField(source="id_usuario_registro.username", read_only=True)
    sesion_datafono_info = serializers.SerializerMethodField()

    def get_sesion_datafono_info(self, obj):
        if obj.sesion_datafono:
            return {
                "id_sesion": str(obj.sesion_datafono.id_sesion),
                "estado": obj.sesion_datafono.estado,
                "fecha_apertura": obj.sesion_datafono.fecha_apertura,
            }
        return None

    class Meta:
        model = TransaccionDatafono
        # CTF-005 (fase 2): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_transaccion_datafono",
            "datafono_nombre",
            "estado_display",
            "usuario_registro_nombre",
            "sesion_datafono_info",
            "monto",
            "referencia_bancaria",
            "estado",
            "lote_bancario",
            "fecha_hora_transaccion",
            "fecha_envio_banco",
            "fecha_conciliacion",
            "conciliada",
            "id_datafono",
            "sesion_datafono",
            "id_transaccion_financiera_origen",
            "id_usuario_registro",
        ]
        read_only_fields = ["datafono_nombre", "estado_display", "usuario_registro_nombre", "sesion_datafono_info"]


class SesionDatafonoSerializer(serializers.ModelSerializer):
    datafono_nombre = serializers.CharField(source="datafono.nombre", read_only=True)
    usuario_apertura_nombre = serializers.CharField(source="usuario_apertura.username", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    cantidad_transacciones = serializers.SerializerMethodField()

    def get_cantidad_transacciones(self, obj):
        anotado = getattr(obj, "_cantidad_transacciones", None)
        if anotado is not None:
            return anotado
        return obj.transacciones_datafono.count()

    class Meta:
        model = SesionDatafono
        # CTF-005 (fase 2): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_sesion",
            "datafono_nombre",
            "usuario_apertura_nombre",
            "estado_display",
            "cantidad_transacciones",
            "fecha_apertura",
            "fecha_cierre",
            "estado",
            "total_transacciones",
            "comision_calculada",
            "neto_esperado",
            "observaciones",
            "fecha_creacion",
            "fecha_modificacion",
            "datafono",
            "usuario_apertura",
        ]
        read_only_fields = ["datafono_nombre", "usuario_apertura_nombre", "estado_display", "cantidad_transacciones"]


class DepositoDatafonoSerializer(serializers.ModelSerializer):
    datafono_nombre = serializers.CharField(source="datafono.nombre", read_only=True)
    sesion_datafono_info = serializers.SerializerMethodField()
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    usuario_envio_nombre = serializers.CharField(source="usuario_envio.username", read_only=True)
    usuario_conciliacion_nombre = serializers.CharField(source="usuario_conciliacion.username", read_only=True)
    movimiento_banco_info = serializers.SerializerMethodField()

    def get_sesion_datafono_info(self, obj):
        return {
            "id_sesion": str(obj.sesion_datafono.id_sesion),
            "fecha_apertura": obj.sesion_datafono.fecha_apertura,
            "fecha_cierre": obj.sesion_datafono.fecha_cierre,
        }

    def get_movimiento_banco_info(self, obj):
        if obj.movimiento_banco:
            return {
                "id_movimiento": str(obj.movimiento_banco.id_movimiento),
                "fecha": obj.movimiento_banco.fecha_movimiento,
                "monto": obj.movimiento_banco.monto,
            }
        return None

    class Meta:
        model = DepositoDatafono
        # CTF-005 (fase 2): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_deposito",
            "datafono_nombre",
            "sesion_datafono_info",
            "estado_display",
            "usuario_envio_nombre",
            "usuario_conciliacion_nombre",
            "movimiento_banco_info",
            "lote_bancario",
            "fecha_envio",
            "fecha_recepcion_banco",
            "fecha_conciliacion",
            "estado",
            "total_bruto",
            "comision_banco",
            "total_neto",
            "referencia_banco",
            "observaciones",
            "fecha_creacion",
            "fecha_modificacion",
            "datafono",
            "sesion_datafono",
            "movimiento_banco",
            "usuario_envio",
            "usuario_conciliacion",
        ]
        read_only_fields = [
            "datafono_nombre",
            "sesion_datafono_info",
            "estado_display",
            "usuario_envio_nombre",
            "usuario_conciliacion_nombre",
            "movimiento_banco_info",
        ]


# Serializer para el modelo genérico de Pago
class PagoSerializer(serializers.ModelSerializer):
    # Campos de solo lectura para mostrar información relacionada
    empresa_nombre = serializers.CharField(source="id_empresa.nombre_comercial", read_only=True)
    contacto_nombre = serializers.CharField(
        source="id_contacto.nombre_completo", read_only=True, allow_blank=True, default=""
    )
    metodo_pago_nombre = serializers.CharField(source="id_metodo_pago.nombre_metodo", read_only=True)
    moneda_codigo = serializers.CharField(source="id_moneda.codigo_iso", read_only=True)
    caja_fisica_nombre = serializers.CharField(source="id_caja_fisica.nombre", read_only=True)
    caja_virtual_nombre = serializers.CharField(source="id_caja_virtual.nombre", read_only=True)
    cuenta_bancaria_nombre = serializers.CharField(source="id_cuenta_bancaria.nombre_banco", read_only=True)
    datafono_nombre = serializers.CharField(source="id_datafono.nombre", read_only=True)
    banco_destino_nombre = serializers.CharField(source="banco_destino.nombre_banco", read_only=True)
    usuario_registro_nombre = serializers.CharField(source="id_usuario_registro.username", read_only=True)

    # Información de la transacción financiera asociada
    transaccion_financiera_info = serializers.SerializerMethodField()

    def get_transaccion_financiera_info(self, obj):
        """Retorna información de la transacción financiera asociada"""
        if obj.id_transaccion_financiera:
            return {
                "id_transaccion": str(obj.id_transaccion_financiera.id_transaccion),
                "tipo_transaccion": obj.id_transaccion_financiera.tipo_transaccion,
                "monto": obj.id_transaccion_financiera.monto_transaccion,
                "fecha": obj.id_transaccion_financiera.fecha_hora_transaccion,
            }
        return None

    # Información del documento relacionado
    documento_info = serializers.SerializerMethodField()

    def get_documento_info(self, obj):
        """Retorna información del documento relacionado"""
        doc = obj.documento_relacionado
        if doc:
            if obj.tipo_documento == "PEDIDO":
                return {
                    "numero_pedido": getattr(doc, "numero_pedido", ""),
                    "cliente": getattr(doc.id_cliente, "nombre", "") if hasattr(doc, "id_cliente") else "",
                    "total": getattr(doc, "total", 0),
                }
            elif obj.tipo_documento == "CXP":
                return {
                    "numero_documento": getattr(doc, "numero_documento", ""),
                    "proveedor": getattr(doc.id_proveedor, "nombre", "") if hasattr(doc, "id_proveedor") else "",
                    "monto_total": getattr(doc, "monto_total", 0),
                }
            elif obj.tipo_documento == "IMPUESTO":
                return {
                    "tipo_impuesto": getattr(doc, "tipo_impuesto", ""),
                    "periodo": getattr(doc, "periodo", ""),
                    "monto_calculado": getattr(doc, "monto_calculado", 0),
                }
        return None

    @staticmethod
    def _derivar_contacto(validated_data):
        for field_name, rel_name in (
            ("id_factura", "id_cliente"),
            ("id_pedido", "id_cliente"),
            ("id_nota_venta", "id_cliente"),
            ("id_cxp", "id_proveedor"),
        ):
            doc = validated_data.get(field_name)
            if doc is None:
                continue
            tercero = getattr(doc, rel_name, None)
            if tercero is None:
                continue
            contacto = getattr(tercero, "contacto", None)
            if contacto is not None:
                return contacto
        return None

    def validate(self, attrs):
        attrs = super().validate(attrs)
        from apps.core.viewsets import get_empresas_visible

        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        es_super = bool(getattr(user, "es_superusuario_omni", False))
        empresas_visibles = (
            get_empresas_visible(user) if user is not None and getattr(user, "is_authenticated", False) else None
        )

        empresa_explicita = attrs.get("id_empresa")
        if (
            empresa_explicita is not None
            and empresas_visibles is not None
            and not es_super
            and not empresas_visibles.filter(pk=empresa_explicita.pk).exists()
        ):
            raise serializers.ValidationError({"id_empresa": "No tiene permisos sobre la empresa indicada."})

        empresa = empresa_explicita or getattr(self.instance, "id_empresa", None)
        if empresa is None and empresas_visibles is not None:
            empresa = empresas_visibles.first()
        if empresa is None:
            raise serializers.ValidationError(
                {"id_empresa": "Debe especificar una empresa válida o el usuario debe tener una empresa asignada."}
            )

        contacto = attrs["id_contacto"] if "id_contacto" in attrs else getattr(self.instance, "id_contacto", None)
        if contacto is not None:
            if (
                empresas_visibles is not None
                and not es_super
                and not empresas_visibles.filter(pk=contacto.id_empresa_id).exists()
            ):
                raise serializers.ValidationError(
                    {"id_contacto": "El contacto no pertenece a una empresa visible para el usuario."}
                )
            if contacto.id_empresa_id != empresa.pk:
                raise serializers.ValidationError(
                    {"id_contacto": "El contacto debe pertenecer a la misma empresa del pago."}
                )

        if (
            self.instance is not None
            and "id_contacto" in attrs
            and (contacto.pk if contacto is not None else None) != self.instance.id_contacto_id
            and self.instance.asignaciones.filter(estado="ACTIVA", activo=True).exists()
        ):
            raise serializers.ValidationError(
                {"id_contacto": "No se puede cambiar el contacto de un pago que ya tiene asignaciones activas."}
            )

        # R-CODE-1: toda FK documental poblada (o preservada en instance durante PATCH/PUT)
        # debe pertenecer a la empresa resuelta del pago; evita ValueError -> HTTP 500
        # cuando un usuario de matriz envía documentos de una subsidiaria visible.
        for fk_field in ("id_pedido", "id_nota_venta", "id_factura", "id_cxp", "id_gasto", "id_reembolso_gasto"):
            doc = attrs[fk_field] if fk_field in attrs else getattr(self.instance, fk_field, None)
            if doc is not None and doc.id_empresa_id != empresa.pk:
                raise serializers.ValidationError({fk_field: "El documento no pertenece a la empresa del pago."})

        nomina = attrs["id_nomina"] if "id_nomina" in attrs else getattr(self.instance, "id_nomina", None)
        if nomina is not None and nomina.id_proceso_nomina.id_empresa_id != empresa.pk:
            raise serializers.ValidationError({"id_nomina": "La nómina no pertenece a la empresa del pago."})

        contribucion = (
            attrs["id_contribucion"] if "id_contribucion" in attrs else getattr(self.instance, "id_contribucion", None)
        )
        if (
            contribucion is not None
            and contribucion.empresa_id is not None
            and not contribucion.es_publico
            and contribucion.empresa_id != empresa.pk
        ):
            raise serializers.ValidationError(
                {"id_contribucion": "La contribución parafiscal no pertenece a la empresa del pago."}
            )

        return attrs

    def create(self, validated_data):
        from apps.core.viewsets import get_empresas_visible

        # Asignar empresa automáticamente si no viene en el payload
        request = self.context.get("request")
        if request and not validated_data.get("id_empresa"):
            user = getattr(request, "user", None)
            if user is not None:
                empresa = get_empresas_visible(user).first()
                if empresa is not None:
                    validated_data["id_empresa"] = empresa

        if not validated_data.get("id_empresa"):
            raise serializers.ValidationError(
                {"id_empresa": "Debe especificar una empresa válida o el usuario debe tener una empresa asignada."}
            )

        # Auto-derivar id_contacto desde el documento relacionado si no viene en el payload
        if not validated_data.get("id_contacto"):
            empresa_pago = validated_data.get("id_empresa")
            candidato = self._derivar_contacto(validated_data)
            if candidato is not None and empresa_pago is not None and candidato.id_empresa_id == empresa_pago.pk:
                validated_data["id_contacto"] = candidato

        # Asignar usuario de registro
        if request and request.user.is_authenticated:
            validated_data["id_usuario_registro"] = request.user

        return super().create(validated_data)

    class Meta:
        model = Pago
        # CTF-005 (fase 2): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_pago",
            "empresa_nombre",
            "contacto_nombre",
            "metodo_pago_nombre",
            "moneda_codigo",
            "caja_fisica_nombre",
            "caja_virtual_nombre",
            "cuenta_bancaria_nombre",
            "datafono_nombre",
            "banco_destino_nombre",
            "usuario_registro_nombre",
            "transaccion_financiera_info",
            "documento_info",
            "tipo_operacion",
            "tipo_documento",
            "id_documento",
            "fecha_pago",
            "monto",
            "tasa",
            "referencia",
            "observaciones",
            "fecha_creacion",
            "fecha_actualizacion",
            "id_empresa",
            "id_contacto",
            "id_moneda",
            "id_metodo_pago",
            "id_caja_fisica",
            "id_caja_virtual",
            "id_cuenta_bancaria",
            "id_datafono",
            "banco_destino",
            "id_transaccion_financiera",
            "id_pedido",
            "id_nota_venta",
            "id_factura",
            "id_cxp",
            "id_gasto",
            "id_reembolso_gasto",
            "id_nomina",
            "id_contribucion",
            "id_usuario_registro",
        ]
        read_only_fields = [
            "id_pago",
            "fecha_creacion",
            "fecha_actualizacion",
            "empresa_nombre",
            "contacto_nombre",
            "metodo_pago_nombre",
            "moneda_codigo",
            "caja_fisica_nombre",
            "caja_virtual_nombre",
            "cuenta_bancaria_nombre",
            "datafono_nombre",
            "banco_destino_nombre",
            "usuario_registro_nombre",
            "documento_info",
            "transaccion_financiera_info",
        ]


class CajaSerializer(serializers.ModelSerializer):
    # Campos relacionados
    empresa_nombre = serializers.CharField(source="empresa.nombre_comercial", read_only=True)
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", read_only=True)
    moneda_codigo_iso = serializers.CharField(source="moneda.codigo_iso", read_only=True)
    tipo_caja_display = serializers.CharField(source="get_tipo_caja_display", read_only=True)
    caja_fisica_nombre = serializers.CharField(source="caja_fisica.nombre", read_only=True)

    class Meta:
        model = Caja
        # CTF-005 (fase 2): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_caja",
            "empresa_nombre",
            "sucursal_nombre",
            "moneda_codigo_iso",
            "tipo_caja_display",
            "caja_fisica_nombre",
            "nombre",
            "tipo_caja",
            "descripcion",
            "activa",
            "referencia_externa",
            "documento_json",
            "fecha_creacion",
            "saldo_actual",
            "empresa",
            "sucursal",
            "moneda",
            "caja_fisica",
            "plantilla_maestro",
            "metodos_pago",
        ]
        ref_name = "CajaFinanzas"  # evita colisión OpenAPI con tesoreria.CajaSerializer
        read_only_fields = [
            "empresa_nombre",
            "sucursal_nombre",
            "moneda_codigo_iso",
            "tipo_caja_display",
            "caja_fisica_nombre",
        ]


class DatafonoSerializer(serializers.ModelSerializer):
    # Campos relacionados
    empresa_nombre = serializers.CharField(source="empresa.nombre_comercial", read_only=True)
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", read_only=True)
    caja_fisica_nombre = serializers.CharField(source="id_caja_fisica.nombre", read_only=True)
    cuenta_bancaria_nombre = serializers.CharField(source="id_cuenta_bancaria.nombre_banco", read_only=True)

    class Meta:
        model = Datafono
        # CTF-005 (fase 2): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_datafono",
            "empresa_nombre",
            "sucursal_nombre",
            "caja_fisica_nombre",
            "cuenta_bancaria_nombre",
            "nombre",
            "serial",
            "comision_porcentaje",
            "saldo_temporal",
            "fecha_ultimo_cierre",
            "activo",
            "fecha_creacion",
            "id_empresa",
            "id_sucursal",
            "id_caja_fisica",
            "id_cuenta_bancaria_asociada",
            "metodos_pago",
            "monedas",
        ]
        read_only_fields = ["empresa_nombre", "sucursal_nombre", "caja_fisica_nombre", "cuenta_bancaria_nombre"]


class CajaFisicaSerializer(serializers.ModelSerializer):
    # Campos relacionados
    empresa_nombre = serializers.CharField(source="empresa.nombre_comercial", read_only=True)
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", read_only=True)
    tipo_caja_display = serializers.CharField(source="get_tipo_caja_display", read_only=True)
    tipo_dispositivo_display = serializers.CharField(source="get_tipo_dispositivo_display", read_only=True)

    # Campos calculados
    cajas_virtuales = serializers.SerializerMethodField()
    datafonos = serializers.SerializerMethodField()
    esta_abierta = serializers.SerializerMethodField()
    estado_sesion_display = serializers.SerializerMethodField()
    nombre_usuario_actual = serializers.SerializerMethodField()

    def get_cajas_virtuales(self, obj):
        """Retorna las cajas virtuales asociadas a esta caja física"""
        cajas = obj.cajas_virtuales.all()
        return CajaSerializer(cajas, many=True, context=self.context).data

    def get_datafonos(self, obj):
        """Retorna los datafonos asociados a esta caja física"""
        datafonos = obj.datafonos.all()
        return DatafonoSerializer(datafonos, many=True, context=self.context).data

    def get_esta_abierta(self, obj):
        return obj.esta_abierta

    def get_estado_sesion_display(self, obj):
        return obj.estado_sesion_display

    def get_nombre_usuario_actual(self, obj):
        return obj.nombre_usuario_actual

    class Meta:
        model = CajaFisica
        # CTF-005 (fase 2): whitelist explícita (defensa en profundidad CWE-915).
        fields = [
            "id_caja_fisica",
            "empresa_nombre",
            "sucursal_nombre",
            "tipo_caja_display",
            "tipo_dispositivo_display",
            "cajas_virtuales",
            "datafonos",
            "esta_abierta",
            "estado_sesion_display",
            "nombre_usuario_actual",
            "nombre",
            "tipo_caja",
            "descripcion",
            "activa",
            "referencia_externa",
            "documento_json",
            "fecha_creacion",
            "nombre_dispositivo",
            "tipo_dispositivo",
            "identificador_dispositivo",
            "descripcion_dispositivo",
            "ultima_conexion_dispositivo",
            "requiere_sesion_activa",
            "empresa",
            "sucursal",
        ]
        read_only_fields = [
            "empresa_nombre",
            "sucursal_nombre",
            "tipo_caja_display",
            "tipo_dispositivo_display",
            "cajas_virtuales",
            "datafonos",
            "esta_abierta",
            "estado_sesion_display",
            "nombre_usuario_actual",
        ]


# Serializers para respuestas específicas de cajas virtuales y datafonos asociados
class CajaVirtualAsociadaSerializer(serializers.ModelSerializer):
    """Serializer para cajas virtuales asociadas a una caja física"""

    empresa_nombre = serializers.CharField(source="empresa.nombre_comercial", read_only=True)
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", read_only=True)
    moneda_codigo_iso = serializers.CharField(source="moneda.codigo_iso", read_only=True)
    tipo_caja_display = serializers.CharField(source="get_tipo_caja_display", read_only=True)
    saldo_actual = serializers.SerializerMethodField()

    def get_saldo_actual(self, obj):
        """Calcula el saldo actual de la caja virtual"""
        # Aquí puedes implementar la lógica para calcular el saldo actual
        # Por ahora retornamos un valor calculado o 0
        return getattr(obj, "saldo_calculado", 0)

    class Meta:
        model = Caja
        fields = [
            "id_caja",
            "nombre",
            "tipo_caja",
            "tipo_caja_display",
            "descripcion",
            "moneda_codigo_iso",
            "activa",
            "empresa_nombre",
            "sucursal_nombre",
            "saldo_actual",
            "fecha_creacion",
        ]


class DatafonoAsociadoSerializer(serializers.ModelSerializer):
    """Serializer para datafonos asociados a una caja física"""

    empresa_nombre = serializers.CharField(source="id_empresa.nombre_comercial", read_only=True)
    sucursal_nombre = serializers.CharField(source="id_sucursal.nombre", read_only=True)
    cuenta_bancaria_nombre = serializers.CharField(source="id_cuenta_bancaria_asociada.nombre_banco", read_only=True)
    saldo_actual = serializers.SerializerMethodField()
    ultima_conexion = serializers.SerializerMethodField()

    def get_saldo_actual(self, obj):
        """Retorna el saldo temporal del datafono"""
        return obj.saldo_temporal

    def get_ultima_conexion(self, obj):
        """Retorna la fecha de última conexión (puedes implementar lógica específica)"""
        # Aquí puedes implementar lógica para obtener la última conexión
        return obj.fecha_ultimo_cierre or obj.fecha_creacion

    class Meta:
        model = Datafono
        fields = [
            "id_datafono",
            "nombre",
            "serial",
            "activo",
            "saldo_actual",
            "ultima_conexion",
            "empresa_nombre",
            "sucursal_nombre",
            "cuenta_bancaria_nombre",
            "fecha_creacion",
        ]


class SesionCajaFisicaSerializer(serializers.ModelSerializer):
    usuario = serializers.SerializerMethodField()
    caja_fisica_principal = serializers.SerializerMethodField()

    def get_usuario(self, obj):
        return {
            "id": obj.usuario.id,
            "username": obj.usuario.username,
            "first_name": obj.usuario.first_name,
            "last_name": obj.usuario.last_name,
        }

    def get_caja_fisica_principal(self, obj):
        """Retorna la información completa de la caja física con sucursal y empresa"""
        return {
            "id_caja": str(obj.caja_fisica.id_caja_fisica),
            "nombre": obj.caja_fisica.nombre,
            "sucursal": {
                "id_sucursal": str(obj.sucursal.id_sucursal) if obj.sucursal else None,
                "nombre": obj.sucursal.nombre if obj.sucursal else None,
                "empresa": {
                    "id_empresa": str(obj.empresa.id_empresa),
                    "nombre": obj.empresa.nombre_comercial,
                },
            },
        }

    class Meta:
        model = SesionCajaFisica
        fields = ["id_sesion", "usuario", "caja_fisica_principal", "estado", "fecha_apertura", "notas"]
        # FIX (bugs lote 4): el estado de la sesión SOLO transiciona por sus
        # endpoints (abrir-sesion / cerrar) — con `estado` writable, un PATCH
        # podía "reabrir" una sesión CERRADA saltándose el cierre de cajas y
        # la constraint de una sola sesión abierta. DRF ignora los campos
        # read-only en la entrada: PATCH con estado no lo cambia.
        read_only_fields = ["estado", "fecha_apertura"]
