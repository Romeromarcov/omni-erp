from decimal import Decimal

from rest_framework import serializers

from apps.core.models import Sucursal

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
        request = self.context.get("request")
        if request and not validated_data.get("empresa"):
            user = request.user
            empresas = getattr(user, "empresas", None)
            if empresas and empresas.exists():
                validated_data["empresa"] = empresas.first()

        metodo_pago_value = validated_data.pop("metodo_pago", None)
        if isinstance(metodo_pago_value, dict) and "id_metodo_pago" in metodo_pago_value:
            metodo_pago_uuid = metodo_pago_value["id_metodo_pago"]
        else:
            metodo_pago_uuid = metodo_pago_value
        if metodo_pago_uuid:
            from .models import MetodoPago

            validated_data["metodo_pago"] = MetodoPago.objects.get(id_metodo_pago=metodo_pago_uuid)

        return super().create(validated_data)

    class Meta:
        model = MetodoPagoEmpresaActiva
        fields = ["id", "empresa", "metodo_pago", "activa", "nombre"]


from rest_framework import serializers

from .models import (
    CuentaBancariaEmpresa,
    MetodoPago,
    Moneda,
    MonedaEmpresaActiva,
    MovimientoCajaBanco,
    TasaCambio,
    TransaccionFinanciera,
)


class MonedaSerializer(serializers.ModelSerializer):
    pais_codigo_iso = serializers.CharField(read_only=True)
    pais_nombre = serializers.CharField(read_only=True)

    class Meta:
        model = Moneda
        fields = "__all__"
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
        # Si no es superusuario, fuerza empresa y flags
        if not getattr(user, "es_superusuario_omni", False):
            empresas = user.empresas.all()
            validated_data["empresa"] = empresas.first() if empresas.exists() else None
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


class TasaCambioSerializer(serializers.ModelSerializer):
    moneda_origen_nombre = serializers.CharField(source="id_moneda_origen.nombre", read_only=True)
    moneda_destino_nombre = serializers.CharField(source="id_moneda_destino.nombre", read_only=True)
    usuario_registro_username = serializers.CharField(source="id_usuario_registro.username", read_only=True)

    class Meta:
        model = TasaCambio
        fields = "__all__"
        read_only_fields = ("moneda_origen_nombre", "moneda_destino_nombre", "usuario_registro_username")


from rest_framework.reverse import reverse


class MetodoPagoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    aplicado = serializers.SerializerMethodField()

    class Meta:
        model = MetodoPago
        fields = "__all__"

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
        # Forzar empresa si no viene en el payload
        if request and not validated_data.get("empresa"):
            user = request.user
            empresas = getattr(user, "empresas", None)
            if empresas and empresas.exists():
                validated_data["empresa"] = empresas.first()
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
        # Forzar empresa si no viene en el payload
        if request and not validated_data.get("empresa"):
            user = request.user
            empresas = getattr(user, "empresas", None)
            if empresas and empresas.exists():
                validated_data["empresa"] = empresas.first()
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
        metodos_empresa = MetodoPago.objects.filter(empresa=id_empresa_actual, tipo_metodo=obj.tipo_metodo)
        for mp in metodos_empresa:
            nombre_db = normalizar(mp.nombre_metodo)
            sim = ratio(nombre_actual, nombre_db)
            dist = Levenshtein.distance(nombre_actual, nombre_db)
            if sim >= 55 or dist <= 3 or nombre_actual in nombre_db or nombre_db in nombre_actual:
                return True
        return False


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
        from .models import Caja, CuentaBancariaEmpresa, MetodoPago, Moneda, MovimientoCajaBanco, TasaCambio

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
                from datetime import date

                hoy = date.today()
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
        fields = "__all__"


class CuentaBancariaEmpresaSerializer(serializers.ModelSerializer):
    moneda_codigo_iso = serializers.CharField(source="id_moneda.codigo_iso", read_only=True)
    metodos_pago = serializers.PrimaryKeyRelatedField(queryset=MetodoPago.objects.all(), many=True)
    monedas = serializers.PrimaryKeyRelatedField(queryset=Moneda.objects.all(), many=True, required=False)

    class Meta:
        model = CuentaBancariaEmpresa
        fields = "__all__"
        read_only_fields = ["moneda_codigo_iso"]


class MonedaEmpresaActivaSerializer(serializers.ModelSerializer):
    empresa_nombre = serializers.CharField(source="empresa.nombre_comercial", read_only=True)
    moneda_codigo_iso = serializers.CharField(source="moneda.codigo_iso", read_only=True)
    moneda_nombre = serializers.CharField(source="moneda.nombre", read_only=True)
    moneda = serializers.UUIDField(source="moneda.id_moneda")
    es_base = serializers.SerializerMethodField()
    es_pais = serializers.SerializerMethodField()

    def get_es_base(self, obj):
        # Lógica: la moneda base de la empresa es la que está marcada como base en core
        # Suponiendo que Empresa tiene un campo moneda_base (ForeignKey a Moneda)
        empresa = getattr(obj, "empresa", None)
        moneda = getattr(obj, "moneda", None)
        if empresa and moneda:
            return getattr(empresa, "moneda_base_id", None) == getattr(moneda, "id_moneda", None)
        return False

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

        return super().create(validated_data)

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
    caja_fisica = serializers.PrimaryKeyRelatedField(queryset=Caja.objects.all())
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
        fields = "__all__"
        read_only_fields = ["datafono_nombre", "estado_display", "usuario_registro_nombre", "sesion_datafono_info"]


class SesionDatafonoSerializer(serializers.ModelSerializer):
    datafono_nombre = serializers.CharField(source="datafono.nombre", read_only=True)
    usuario_apertura_nombre = serializers.CharField(source="usuario_apertura.username", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    cantidad_transacciones = serializers.SerializerMethodField()

    def get_cantidad_transacciones(self, obj):
        return obj.transacciones_datafono.count()

    class Meta:
        model = SesionDatafono
        fields = "__all__"
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
        fields = "__all__"
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

    def create(self, validated_data):
        # Asignar empresa automáticamente si no viene en el payload
        request = self.context.get("request")
        if request and not validated_data.get("id_empresa"):
            user = request.user
            empresas = getattr(user, "empresas", None)
            if empresas and hasattr(empresas, "first") and empresas.exists():
                validated_data["id_empresa"] = empresas.first()

        # Asignar usuario de registro
        if request and request.user.is_authenticated:
            validated_data["id_usuario_registro"] = request.user

        return super().create(validated_data)

    class Meta:
        model = Pago
        fields = "__all__"
        read_only_fields = [
            "id_pago",
            "fecha_creacion",
            "fecha_actualizacion",
            "empresa_nombre",
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
        fields = "__all__"
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
        fields = "__all__"
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
        fields = "__all__"
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
